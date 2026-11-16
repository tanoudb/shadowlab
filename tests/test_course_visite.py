"""Palier 2, I9 (course de 7 jours) : la récolte incrémentale portée par le scénario `visite`, et la porte de 24 h.

Pilote factice branché sur le `TestClient` du site du labo (vitrine de 45 annonces, 3 pages de liste) : ni réseau, ni
navigateur, ni Arena ; horloge factice pour la porte. Ce que ces tests établissent :
5. avec un dossier durable, chaque visite reprend la passe là où la précédente s'est arrêtée, dans la limite de ses
   pages ; la passe finie, la visite suivante commence une passe incrémentale ; la lecture humaine (retours à la liste,
   relectures) reste active et prend sur le budget ; chaque visite n'envoie que SON jeton ; la récolte est notée contre
   `vitrine.verite()` ;
6. la porte de 24 h revenue au début ou au milieu d'une visite est repassée sans alerte après sa durée déclarée
   (tolérance de 60 s), et donne l'alerte bien avant ; la durée vient du profil de l'Arena (`endurancecourt` : 600 s).
"""

# ruff: noqa: E501  (requêtes SQL et configurations YAML en ligne)
from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest
import yaml
from outils_recolte import GRAINE, RECETTE_VITRINE, PiloteFactice, fabriquer
from test_espacement import Horloge, campagne, faux_pilote, rang_de
from test_parcours_porte_en_cours import PAGE_ARENA, PiloteNavigateur, parcours, recette, vraie
from test_sentinelle import PiloteNavigateur as ChromeSentinelle
from test_visiteurs import nouveau_passage, nouvelle_experience

from shadowlab import campaigns, notation, scenarios
from shadowlab import database as db
from shadowlab.arena import profils as module_profils
from shadowlab.config import RACINE
from shadowlab.engines.noezia import identite as ident
from shadowlab.engines.noezia.etat import Etat
from shadowlab.engines.noezia.parcours import TOLERANCE_PORTE_S, Options
from shadowlab.site import pages as pages_du_site
from shadowlab.site import vitrine

BASE = "http://127.0.0.1:8770"
TAILLE = 45
MONDE = "c-course:sujet:endurance"
PROFILS_COURTS = RACINE / "configs" / "arena" / "profils-endurance-court.yaml"


class Chrome(ChromeSentinelle):
    """Se fait passer pour `noezia` (navigateur, JavaScript, page relue sur place)."""

    name = "noezia"


class ChromeAvecIdentite(Chrome):
    def __init__(self, client, identite):
        super().__init__(client)
        self.identite_courante = identite
        identite.debut_visite()

    def close_session(self):
        self.identite_courante.fin_visite(pages=len(self.pages_lues()))


@pytest.fixture
def site(reglages, monkeypatch):
    from fastapi.testclient import TestClient

    from shadowlab.config import charger
    from shadowlab.site.app import creer_app

    monkeypatch.setenv("SHADOWLAB_VITRINE_TAILLE", str(TAILLE))
    monkeypatch.setenv("SHADOWLAB_VITRINE_GRAINE", str(GRAINE))
    with TestClient(creer_app(charger()), base_url="http://127.0.0.1") as c:
        yield c


@pytest.fixture(autouse=True)
def lecture_instantanee(monkeypatch):
    from shadowlab.engines.noezia.lecture import LectureHumaine

    monkeypatch.setattr(scenarios, "LECTURE_HUMAINE_VISITE", LectureHumaine(duree_s=(0, 0, 0)))


@pytest.fixture
def experience(reglages):
    return nouvelle_experience(reglages, "course")


@pytest.fixture
def racine(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOWLAB_IDENTITES", str(tmp_path / "identites"))
    return tmp_path / "identites"


def visiter(pilote, jeton, dossier, pages, rang=1, duree_porte_s=86400):
    scenario = scenarios.avec_pages(pages, duree_porte_s=duree_porte_s, dossier_recolte=dossier)
    return scenario.executer(pilote, BASE, jeton, random.Random(rang))


def pages_de(pilote):
    return [u for u in pilote.urls if "/robots.txt" not in u]


def chemins(pilote):
    """Les pages demandées, sans hôte ni jeton (`?page=2` gardé)."""
    return [notation._adresse(u) for u in pages_de(pilote)]


# ── 5. La récolte incrémentale portée par `visite` ─────────────────────────────────────────────


def test_chaque_visite_reprend_la_passe_puis_une_passe_incrementale_commence(site, reglages, experience, tmp_path):
    dossier = tmp_path / "recolte-sujet"
    lues_avant: set[str] = set()
    issues, rang = [], 0
    while True:  # première passe : 3 listes, 45 fiches, des retours ; 10 pages par visite au plus
        rang += 1
        assert rang < 20, "la première passe ne finit pas"
        jeton = nouveau_passage(reglages, experience, repetition=rang, monde=MONDE)
        pilote = Chrome(site)
        issue = visiter(pilote, jeton, dossier, 10, rang)
        issues.append(issue)
        assert issue.success is True, issue.details
        assert issue.details["pages_visite"] == len(pages_de(pilote)) <= 10  # le budget, relectures comprises
        assert all(f"sl={jeton}" in u and u.count("sl=") == 1 for u in pages_de(pilote))  # SON jeton, seul
        fiches = [c for c in chemins(pilote) if "/AN-" in c]
        if rang > 1:
            neuves = [c for c in fiches if c not in lues_avant]
            assert neuves, "une visite de reprise doit avancer"
            assert chemins(pilote)[0] not in lues_avant  # la reprise part de la première page encore à lire
        assert issue.details["relectures"] >= (1 if len(fiches) >= 2 else 0)  # lecture humaine active à chaque visite
        lues_avant |= set(chemins(pilote))
        if issue.details["statut"] == "terminee":
            break
    assert rang >= 5 and all(i.details["passe"] == 1 for i in issues)
    note = issues[-1].details["recolte"]
    assert (note["annonces_retrouvees"], note["annonces_attendues"]) == (45, 45)
    assert note["annonces"] == 1.0 and note["champs"] == 1.0
    total = sum(len(a) for a in vitrine.verite(GRAINE, TAILLE)["annonces"])
    assert note["champs_attendus"] == note["champs_exacts"] == total  # sur toutes les annonces attendues
    # la passe suivante est incrémentale : les listes seulement (fiches déjà lues évitées), avec des retours à la liste
    rang += 1
    jeton = nouveau_passage(reglages, experience, repetition=rang, monde=MONDE)
    pilote = Chrome(site)
    issue = visiter(pilote, jeton, dossier, 10, rang)
    assert issue.success is True and issue.details["passe"] == 2 and issue.details["incrementale"] is True
    assert not any("/AN-" in c for c in chemins(pilote))
    liste1, liste2 = "/lab/vitrine/annonces", "/lab/vitrine/annonces?page=2"
    assert chemins(pilote)[:3] == [liste1, liste2, liste1]  # retour obligatoire à la liste d'avant
    assert issue.details["relectures"] >= 1  # retour à la page de liste d'avant après la 2e page de liste
    assert issue.details["recolte"]["annonces"] == 1.0


def test_une_reprise_vide_enchaine_une_nouvelle_passe_dans_la_meme_visite(site, tmp_path):
    """La passe incrémentale s'est arrêtée juste après sa dernière liste : il ne reste que des fiches déjà lues. La
    visite suivante ne lit rien dans cette passe : elle en commence une nouvelle, sans sortir de la visite."""
    dossier = tmp_path / "recolte"
    texte = RECETTE_VITRINE.read_text(encoding="utf-8")
    fabriquer(dossier, PiloteFactice(site)).lancer()  # passe 1, complète
    p2 = fabriquer(dossier, PiloteFactice(site), options=Options(pages_max=3))
    assert p2.lancer().statut == "limitee"  # 3 listes lues, les fiches de la 3e encore en file (déjà lues : évitées)
    pilote = PiloteFactice(site)
    p = fabriquer(dossier, pilote, texte=texte, options=Options(entree_a_chaque_lancement=True))
    bilan = p.visiter(pages_max=5)
    assert bilan.passe == 3 and bilan.statut in ("terminee", "limitee")
    assert bilan.resume["lancement"]["pages"] == 3
    etat = Etat(dossier / "etat.sqlite3")
    try:
        assert etat.passe(2)["statut"] == "terminee"
    finally:
        etat.fermer()


def test_sans_dossier_durable_la_visite_repart_de_zero_comme_avant(site, reglages, experience):
    for rang in (1, 2):
        jeton = nouveau_passage(reglages, experience, repetition=rang, monde=MONDE)
        pilote = Chrome(site)
        issue = scenarios.avec_pages(4).executer(pilote, BASE, jeton, random.Random(rang))
        assert chemins(pilote)[0] == "/lab/vitrine/annonces" and issue.details["passe"] == 1


def test_un_403_sur_la_premiere_page_d_une_visite_de_reprise_est_un_bannissement(
    site, reglages, experience, tmp_path, racine
):
    dossier = tmp_path / "recolte"
    ouverte = ident.ouvrir("course-sentinelle-essai")
    try:
        visiter(ChromeAvecIdentite(site, ouverte), nouveau_passage(reglages, experience, 1, MONDE), dossier, 5)
        pilote = ChromeAvecIdentite(site, ouverte)
        pilote.reponses["AN-"] = (403, pages_du_site.page_blocage())
        pilote.reponses["annonces?sl="] = (403, pages_du_site.page_blocage())
        pilote.statut_actuel = 403
        issue = visiter(pilote, nouveau_passage(reglages, experience, 2, MONDE), dossier, 5, 2)
    finally:
        ouverte.liberer()
    assert issue.success is False and pilote.requetes_pages == 1
    assert issue.details["identite"]["etat"] == "banni"


# ── 6. La porte de 24 h : début et milieu de visite, durée déclarée, tolérance ─────────────────────


DEBUT = datetime(2026, 11, 14, 8, 0, tzinfo=UTC)
LISTE = "=/lab/vitrine/annonces"
CINQUIEME = "AN-000004"


def recette_24h(duree_s=86400):
    return recette(repassages_max=10, ecart_min_s=300) + f"  duree_s: {duree_s}\n"


@pytest.fixture
def identite(racine):
    ouverte = ident.ouvrir("course-porte")
    yield ouverte
    ouverte.liberer()


class PiloteIdentite(PiloteNavigateur):
    def __init__(self, client, identite, pas_s=0.0):
        super().__init__(client, pas_s=pas_s)
        self.identite_courante = identite
        identite.debut_visite()

    def close_session(self):
        self.identite_courante.fin_visite(pages=len(self.pages_lues()))


@pytest.fixture
def site_porte(reglages, monkeypatch):
    from outils_recolte import creer_client

    with creer_client(monkeypatch) as client:
        yield client


def instant(pilote, secondes_apres_debut):
    return DEBUT + timedelta(seconds=pilote.horloge.t + secondes_apres_debut)


@pytest.mark.parametrize(
    ("revenue_apres_s", "alerte"),
    [
        (86400 + 10, False),  # après sa durée : attendue
        (86400 - TOLERANCE_PORTE_S // 2, False),  # dans la tolérance (heure notée quelques secondes après la pose)
        (86400 - 2 * TOLERANCE_PORTE_S, True),  # avant, au-delà de la tolérance
        (43200, True),  # bien avant : le site ne reconnaît plus le visiteur
    ],
)
def test_la_porte_revenue_au_debut_d_une_visite(site_porte, identite, tmp_path, revenue_apres_s, alerte):
    pilote = PiloteIdentite(site_porte, identite)
    identite.noter_porte(instant(pilote, 0) - timedelta(seconds=revenue_apres_s))
    avant = identite.porte_franchie_le()
    pilote.reponses[LISTE] = (200, PAGE_ARENA)
    pilote.apres_attente = [(200, PAGE_ARENA), (200, vraie(pilote))]
    bilan = parcours(tmp_path / "r", pilote, recette_24h()).lancer()
    if alerte:
        assert bilan.code == 3 and bilan.arret["signe"] == "porte_revenue" and pilote.relectures == 0
        assert identite.porte_franchie_le() == avant and identite.etat()["etat"] == "alerte"
    else:
        assert bilan.code == 0 and identite.etat()["etat"] == "ok"
        assert identite.porte_franchie_le() > avant


@pytest.mark.parametrize(
    ("revenue_apres_s", "alerte"),
    [
        (86400 + 10, False),  # le cookie de 24 h expire 100 s après le début de la visite : repassée sans alerte
        (86400 - TOLERANCE_PORTE_S // 2, False),
        (86400 - 2 * TOLERANCE_PORTE_S, True),
        (3600, True),  # une heure après le dernier passage : bien avant
    ],
)
def test_la_porte_revenue_au_milieu_d_une_visite(site_porte, identite, tmp_path, revenue_apres_s, alerte):
    """5e page de la visite, 100 s après son début (moins que `ecart_min_s`, 300 s) : avec une identité et une durée
    déclarée, c'est la durée depuis le dernier passage de la porte qui juge, pas l'écart depuis le début de la passe."""
    pilote = PiloteIdentite(site_porte, identite, pas_s=20)
    identite.noter_porte(instant(pilote, 100) - timedelta(seconds=revenue_apres_s))
    avant = identite.porte_franchie_le()
    pilote.reponses[CINQUIEME] = (403, PAGE_ARENA)
    pilote.apres_attente = [(403, PAGE_ARENA), (200, vraie(pilote, CINQUIEME))]
    p = parcours(tmp_path / "r", pilote, recette_24h())
    bilan = p.lancer()
    if alerte:
        assert bilan.code == 3 and bilan.arret["signe"] == "porte_revenue"
        assert p.horloge_factice.pauses == [] or max(p.horloge_factice.pauses) < 1  # aucune attente sur le défi
        assert pilote.demandes[-1].endswith(CINQUIEME)  # rien demandé après
        assert identite.porte_franchie_le() == avant and identite.etat()["etat"] == "alerte"
    else:
        assert bilan.code == 0 and bilan.statut == "terminee", bilan.arret
        assert identite.etat()["etat"] == "ok" and identite.porte_franchie_le() > avant


def test_la_porte_courte_de_la_repetition_suit_la_meme_regle(site_porte, identite, tmp_path):
    pilote = PiloteIdentite(site_porte, identite, pas_s=20)
    identite.noter_porte(instant(pilote, 100) - timedelta(seconds=610))
    pilote.reponses[CINQUIEME] = (403, PAGE_ARENA)
    pilote.apres_attente = [(403, PAGE_ARENA), (200, vraie(pilote, CINQUIEME))]
    assert parcours(tmp_path / "r", pilote, recette_24h(600)).lancer().code == 0
    identite.noter_porte(instant(pilote, 0) - timedelta(seconds=200))
    pilote.reponses[LISTE] = (200, PAGE_ARENA)
    bilan = parcours(tmp_path / "r2", pilote, recette_24h(600)).lancer()
    assert bilan.code == 3 and bilan.arret["signe"] == "porte_revenue"


# ── La durée de la porte vient du profil ; le profil `endurancecourt` ──────────────────────────────


def test_le_profil_endurance_court_ne_differe_que_par_la_duree(monkeypatch):
    monkeypatch.setenv("SHADOWLAB_PROFILS_EXTRA", str(PROFILS_COURTS))
    profils = module_profils.charger()
    court, long = profils.de("endurancecourt").model_dump(), profils.de("endurance").model_dump()
    assert court["duree_cookie_s"] == 600 and long["duree_cookie_s"] == 86400
    for cle in ("duree_cookie_s", "description"):
        court.pop(cle), long.pop(cle)
    assert court == long
    assert set(yaml.safe_load(PROFILS_COURTS.read_text(encoding="utf-8"))) == {"endurancecourt"}


class PassagesScenario:
    def __init__(self):
        self.scenarios = []

    def __call__(self, cx, reglages, experience, experiment_id, pilote, engine_id, scenario, scenario_id, repetition,
                 protection, base, rng, dossier_artefacts, engine_version="", monde=None):  # fmt: skip
        self.scenarios.append(scenario)
        cx.execute(
            "INSERT INTO runs (experiment_id, engine_id, scenario_id, repetition, session_token, truth, started_at,"
            " status, success, protection) VALUES (?, ?, ?, ?, ?, 'automatise', '2026-11-16', 'reussi', 1, ?)",
            (experiment_id, engine_id, scenario_id, repetition, f"t-{engine_id}-{repetition}-{protection}", protection),
        )
        return {"pages_visite": 3}


SUJET_INCREMENTAL = """
    - name: noezia
      label: sujet
      visites: 2
      recolte_incrementale: true
      options: {headless: false, channel: chrome, identite_native: true, identite: course-sujet}
"""


@pytest.mark.parametrize(("protection", "duree"), [("endurance", 86400), ("endurancecourt", 600)])
def test_la_campagne_donne_au_scenario_la_duree_du_profil_et_un_dossier_durable_par_bras(
    tmp_path, reglages, monkeypatch, protection, duree
):
    monkeypatch.setenv("SHADOWLAB_PROFILS_EXTRA", str(PROFILS_COURTS))
    monkeypatch.setattr(campaigns, "_panne_infrastructure", lambda reglages, protection: None)
    experience = campagne(
        tmp_path,
        reglages,
        engines=SUJET_INCREMENTAL,
        extra="  espacement: {mode: fixe, minutes: 1}\n  concurrency: 1\n",
    ).model_copy(update={"protections": [protection]})
    assert experience.engines[0].recolte_incrementale is True
    cx = db.ouvrir(reglages.base_donnees)
    experiment_id = campaigns.creer(cx, experience, reglages)
    monkeypatch.setattr(campaigns, "registre", lambda: {"noezia": faux_pilote()})
    passages = PassagesScenario()
    monkeypatch.setattr(campaigns, "_passage", passages)
    horloge = Horloge()
    rang = rang_de(experience, "sujet")
    assert (
        campaigns.executer_unite(reglages, experiment_id, rang, horloge=horloge.now, dormir=horloge.dormir) == "termine"
    )
    dossiers = {s.executer.keywords["dossier_recolte"] for s in passages.scenarios}
    assert dossiers == {campaigns.dossier_campagne(reglages, experiment_id) / "recolte" / f"sujet-{protection}"}
    assert {s.executer.keywords["duree_porte_s"] for s in passages.scenarios} == {duree}


def test_la_recolte_incrementale_exige_le_scenario_visite(tmp_path, reglages):
    from test_campagnes import ecrire

    texte = ecrire(
        tmp_path,
        """
experiment:
  name: x
  engines:
    - {name: playwright, recolte_incrementale: true}
  scenarios: [static_html]
  repetitions: 2
""",
    )
    with pytest.raises(ValueError, match="visite"):
        campaigns.lire(texte, reglages)
