"""Étape 4.2 : la récolte partagée entre identités portée par une campagne (champ `recolte_partagee`).

Chaque bras est une identité persistante ; les bras d'une même `recolte_partagee` se partagent une seule récolte (une file
d'adresses, un dossier durable par protection). Ce que ces tests établissent, sans navigateur ni Arena :
1. la validation : un seul monde pour toute la campagne (`monde: campagne`), le scénario `visite`, noezia en identité
   native avec sa propre identité, jamais deux bras sur la même identité ;
2. le scénario `visite` d'un bras partagé lit la file commune (`Parcours.visiter_partage`) : deux identités font toute la
   vitrine, chaque page une fois ; une identité bannie en route s'arrête, sa page revient, l'autre finit ;
3. le bras : le dossier commun, la graine propre à l'identité (jamais celle de la campagne), l'arrêt quand la récolte
   est finie (aucun passage de plus) ;
4. au lancement, rien de partagé entre les identités d'une récolte (profil, graine, proxy) : refus avant toute visite.
"""

# ruff: noqa: E501  (configurations YAML en ligne)
from __future__ import annotations

import json
import random
import shutil
from datetime import timedelta

import pytest
from outils_identites import PiloteIdentite
from outils_recolte import GRAINE, creer_client
from test_campagnes import ecrire
from test_espacement import Horloge, Passages, faux_pilote, rang_de
from test_visiteurs import nouveau_passage, nouvelle_experience

from shadowlab import campaigns, notation, scenarios
from shadowlab import database as db
from shadowlab.campaigns import lire
from shadowlab.engines.noezia import identite as ident
from shadowlab.engines.noezia.etat import Etat
from shadowlab.engines.noezia.gestionnaire import PartageRefuse, verrou_travailleur
from shadowlab.site import vitrine

BASE = "http://127.0.0.1:8770"
TAILLE = 45
PAGES = TAILLE + 3

BRAS_PARTAGES = """
    - name: noezia
      label: ident-a
      recolte_partagee: vitrine-partagee
      options: {headless: false, channel: chrome, identite_native: true, identite: essai-a}
    - name: noezia
      label: ident-b
      recolte_partagee: vitrine-partagee
      options: {headless: false, channel: chrome, identite_native: true, identite: essai-b}
    - name: noezia
      label: ident-c
      recolte_partagee: vitrine-partagee
      options: {headless: false, channel: chrome, identite_native: true, identite: essai-c}
"""
SUITE = "  espacement: {mode: fixe, minutes: 10}\n  concurrency: 3\n  monde: campagne\n"


def campagne(tmp_path, reglages, *, engines=BRAS_PARTAGES, suite=SUITE, scenarios_="[visite]"):
    return lire(
        ecrire(
            tmp_path,
            f"""
experiment:
  name: identites
  engines:{engines}
  protections: [endurance]
  scenarios: {scenarios_}
  repetitions: 6
  pages_par_visite: 15
  seed: 1
{suite}""",
        ),
        reglages,
    )


@pytest.fixture
def racine(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOWLAB_IDENTITES", str(tmp_path / "identites"))
    return tmp_path / "identites"


@pytest.fixture(autouse=True)
def sans_arena(monkeypatch):
    """Ni Arena ni site lancés : la vérification d'avant visite d'un bras espacé répond « rien en panne »."""
    monkeypatch.setattr(campaigns, "_panne_infrastructure", lambda reglages, protection: None)


@pytest.fixture(autouse=True)
def lecture_instantanee(monkeypatch):
    from shadowlab.engines.noezia.lecture import LectureHumaine

    monkeypatch.setattr(scenarios, "LECTURE_HUMAINE_VISITE", LectureHumaine(duree_s=(0, 0, 0)))


# ── 1. Validation ────────────────────────────────────────────────────────────────────────────────


def test_campagne_partagee_valide(tmp_path, reglages):
    e = campagne(tmp_path, reglages)
    assert [m.recolte_partagee for m in e.engines] == ["vitrine-partagee"] * 3


@pytest.mark.parametrize(
    ("engines", "suite", "scenarios_", "message"),
    [
        (BRAS_PARTAGES, SUITE.replace("campagne", "serie"), "[visite]", "monde"),
        (BRAS_PARTAGES, SUITE, "[static_html]", "visite"),
        (BRAS_PARTAGES.replace(", identite: essai-c", ""), SUITE, "[visite]", "identite"),
        (
            BRAS_PARTAGES.replace(
                "identite_native: true, identite: essai-c", "identite_native: false, identite: essai-c"
            ),
            SUITE,
            "[visite]",
            "native",
        ),
        (BRAS_PARTAGES.replace("identite: essai-c", "identite: essai-a"), SUITE, "[visite]", "même identité"),
        (
            BRAS_PARTAGES.replace("      label: ident-c\n", "      label: ident-c\n      recolte_incrementale: true\n"),
            SUITE,
            "[visite]",
            "recolte_incrementale",
        ),
        # sans espacement, une identité bannie ou en alerte n'est pas relue avant chaque visite
        (BRAS_PARTAGES, "  concurrency: 3\n  monde: campagne\n", "[visite]", "espacement"),
    ],
)
def test_campagne_partagee_refusee(tmp_path, reglages, engines, suite, scenarios_, message):
    with pytest.raises(ValueError, match=message):
        campagne(tmp_path, reglages, engines=engines, suite=suite, scenarios_=scenarios_)


# ── 2. Le scénario `visite` d'un bras partagé ────────────────────────────────────────────────────


@pytest.fixture
def site(reglages, monkeypatch, racine):
    with creer_client(monkeypatch, TAILLE) as client:
        yield client


def _visite(site, reglages, experience, dossier, nom, rang, pages=10, bannir_a=None):
    """Comme `campaigns._passage` : le pilote du bras ouvert, une session par visite, le scénario `visite`."""
    jeton = nouveau_passage(reglages, experience, repetition=rang, monde=f"c{experience}")
    pilote = PiloteIdentite(site, nom, bannir_a=bannir_a)
    pilote.open()
    try:
        pilote.start_session()
        scenario = scenarios.avec_pages(pages, duree_porte_s=None, dossier_recolte=dossier, identite_partagee=nom)
        issue = scenario.executer(pilote, BASE, jeton, random.Random(rang))
        pilote.close_session()
    finally:
        pilote.close()
    return issue, pilote, jeton


def test_deux_identites_font_toute_la_vitrine_chacune_par_sa_visite(tmp_path, site, reglages, racine):
    experience = nouvelle_experience(reglages, "partage")
    dossier = tmp_path / "recolte"
    issues = []
    for rang in range(1, 30):
        nom = ("essai-a", "essai-b")[rang % 2]
        issue, pilote, jeton = _visite(site, reglages, experience, dossier, nom, rang)
        issues.append(issue)
        assert all(f"sl={jeton}" in u and u.count("sl=") == 1 for u in pilote.urls if "/robots.txt" not in u)
        if issue.details["travail_fini"]:
            break
    assert issues[-1].details["statut"] == "terminee"
    assert all(i.success for i in issues), [i.details for i in issues if not i.success]
    assert {i.details["identite_partagee"] for i in issues} == {"essai-a", "essai-b"}
    note = issues[-1].details["recolte"]
    assert note["annonces"] == 1.0 and note["champs"] == 1.0
    etat = Etat(dossier / "etat.sqlite3")
    try:
        assert etat.compteurs(1)["faites"] == PAGES
        attendues = vitrine.pages_attendues(GRAINE, TAILLE)
        assert notation.noter_pages(attendues, etat.adresses_couvertes(1))["completude_pages"] == 1.0
    finally:
        etat.fermer()


def test_une_identite_bannie_en_route_s_arrete_l_autre_finit(tmp_path, site, reglages, racine):
    experience = nouvelle_experience(reglages, "partage-ban")
    dossier = tmp_path / "recolte"
    _visite(site, reglages, experience, dossier, "essai-a", 1)
    issue, pilote, _ = _visite(site, reglages, experience, dossier, "essai-b", 2, bannir_a=3)
    assert issue.success is False and issue.details["statut"] == "arretee"
    assert issue.details["identite"] == {"nom": "essai-b", "etat": "banni"}
    assert pilote.requetes_pages == 3  # rien demandé après la page refusée
    assert issue.details["travail_fini"] is False
    for rang in range(3, 30):
        issue, _, _ = _visite(site, reglages, experience, dossier, "essai-a", rang)
        if issue.details["travail_fini"]:
            break
    assert issue.details["recolte"]["annonces"] == 1.0 and issue.details["recolte"]["champs"] == 1.0


def test_une_visite_qui_lit_puis_attend_les_autres_reussit_une_visite_vide_est_marquee(
    tmp_path, site, reglages, racine
):
    """Fin de récolte : la file est vide, une autre identité (vivante) tient la dernière page. Une visite qui a lu
    sans échec puis attend est réussie ; une visite qui n'a rien pu prendre le dit (`rien_a_faire`)."""
    experience = nouvelle_experience(reglages, "partage-attente")
    dossier = tmp_path / "recolte"
    _visite(site, reglages, experience, dossier, "essai-a", 1, pages=3)
    verrou = verrou_travailleur(dossier, "essai-z")
    etat = Etat(dossier / "etat.sqlite3")
    try:
        tenues = []
        while (page := etat.prochaine(1, identite="essai-z")) is not None:
            tenues.append(page)
        etat.rendre(tenues[0])  # une seule page reste à prendre
    finally:
        etat.fermer()
    issue, _, _ = _visite(site, reglages, experience, dossier, "essai-b", 2, pages=5)
    assert issue.details["statut"] == "attente" and issue.details["pages_faites"] == 1
    assert issue.success is True and issue.details["rien_a_faire"] is False
    issue, pilote, _ = _visite(site, reglages, experience, dossier, "essai-a", 3, pages=5)
    assert issue.details["statut"] == "attente" and issue.details["pages_faites"] == 0
    assert issue.success is False and issue.details["rien_a_faire"] is True
    assert pilote.requetes_pages == 0
    verrou.close()


# ── 3. Le bras ───────────────────────────────────────────────────────────────────────────────────


def _preparer(tmp_path, reglages, monkeypatch):
    experience = campagne(tmp_path, reglages)
    cx = db.ouvrir(reglages.base_donnees)
    experiment_id = campaigns.creer(cx, experience, reglages)
    pilote = faux_pilote()
    monkeypatch.setattr(campaigns, "registre", lambda: {"noezia": pilote})
    return experience, cx, experiment_id


def test_les_bras_partages_ont_le_meme_dossier_et_chacun_son_identite(tmp_path, reglages, monkeypatch, racine):
    experience, _, experiment_id = _preparer(tmp_path, reglages, monkeypatch)
    vus = [campaigns._reglages_visite(reglages, experiment_id, m, "endurance") for m in experience.engines]
    assert len({str(v["dossier_recolte"]) for v in vus}) == 1
    assert str(vus[0]["dossier_recolte"]).endswith(f"{experiment_id}/recolte/vitrine-partagee-endurance")
    assert [v["identite_partagee"] for v in vus] == ["essai-a", "essai-b", "essai-c"]


def test_le_bras_tire_ses_hasards_de_la_graine_de_son_identite(tmp_path, reglages, monkeypatch, racine):
    experience, _, experiment_id = _preparer(tmp_path, reglages, monkeypatch)
    horloge = Horloge()
    recus = []

    class Note(Passages):
        def __call__(self, cx, reglages_, experience_, experiment_id_, pilote, engine_id, scenario, scenario_id, repetition, protection, base, rng, dossier_artefacts, engine_version="", monde=None):  # fmt: skip
            recus.append((repetition, rng.random(), monde))
            details = super().__call__(cx, reglages_, experience_, experiment_id_, pilote, engine_id, scenario, scenario_id, repetition, protection, base, rng, dossier_artefacts, engine_version, monde)  # fmt: skip
            return {**details, "travail_fini": repetition == 2}

    monkeypatch.setattr(campaigns, "_passage", Note(reglages, horloge))
    rang = rang_de(experience, "ident-b")
    assert (
        campaigns.executer_unite(reglages, experiment_id, rang, horloge=horloge.now, dormir=horloge.dormir) == "termine"
    )
    graine = json.loads((racine / "essai-b" / "identite.json").read_text())["graine"]
    assert [r[0] for r in recus] == [1, 2]  # la récolte finie à la visite 2 : le bras s'arrête là (6 prévues)
    attendu = random.Random(f"{graine}:ident-b:endurance:visite:1").random()
    assert recus[0][1] == attendu
    assert recus[0][1] != random.Random(f"{experience.seed}:ident-b:endurance:visite:1").random()
    assert {r[2] for r in recus} == {f"c{experiment_id}"}  # un seul monde pour toute la campagne


def test_le_bras_ne_lance_rien_quand_la_recolte_est_deja_finie(tmp_path, reglages, monkeypatch, racine):
    experience, _, experiment_id = _preparer(tmp_path, reglages, monkeypatch)
    dossier = campaigns._reglages_visite(reglages, experiment_id, experience.engines[0], "endurance")["dossier_recolte"]
    etat = Etat(dossier / "etat.sqlite3")
    passe = etat.ouvrir_passe(
        "vitrine-annonces", "sha256:x", "", "", {}, {"partagee": True}, "2026-11-19T10:00:00+00:00"
    )
    etat.terminer_passe(passe, "terminee", None, "2026-11-19T11:00:00+00:00")
    etat.fermer()
    horloge = Horloge()
    passages = Passages(reglages, horloge)
    monkeypatch.setattr(campaigns, "_passage", passages)
    rang = rang_de(experience, "ident-c")
    assert (
        campaigns.executer_unite(reglages, experiment_id, rang, horloge=horloge.now, dormir=horloge.dormir) == "termine"
    )
    assert passages.appels == []


def test_le_bras_attend_sans_passage_tant_que_rien_n_est_a_prendre(tmp_path, reglages, monkeypatch, racine):
    """Toutes les pages restantes sont tenues par une autre identité vivante : le bras attend, sans ouvrir de passage
    (aucun Chrome, rien en base), puis visite quand une page revient en file."""
    experience, _, experiment_id = _preparer(tmp_path, reglages, monkeypatch)
    dossier = campaigns._reglages_visite(reglages, experiment_id, experience.engines[0], "endurance")["dossier_recolte"]
    etat = Etat(dossier / "etat.sqlite3")
    passe = etat.ouvrir_passe(
        "vitrine-annonces", "sha256:x", "", "", {}, {"partagee": True}, "2026-11-19T10:00:00+00:00"
    )
    etat.empiler(passe, [("http://127.0.0.1:8750/lab/vitrine/annonces", "liste")])
    tenue = etat.prochaine(passe, identite="essai-z")
    etat.fermer()
    verrou = verrou_travailleur(dossier, "essai-z")
    horloge = Horloge()
    pauses_avant = []

    def dormir(secondes):
        horloge.dormir(secondes)
        pauses_avant.append(secondes)
        if len(pauses_avant) == 3:  # essai-z rend sa page (elle tombe) : il y a de nouveau quelque chose à prendre
            e = Etat(dossier / "etat.sqlite3")
            e.rendre(tenue)
            e.fermer()

    class Fin(Passages):
        def __call__(self, *args, **kwargs):
            details = super().__call__(*args, **kwargs)
            return {**details, "travail_fini": True}

    passages = Fin(reglages, horloge)
    monkeypatch.setattr(campaigns, "_passage", passages)
    rang = rang_de(experience, "ident-a")
    assert campaigns.executer_unite(reglages, experiment_id, rang, horloge=horloge.now, dormir=dormir) == "termine"
    assert len(passages.appels) == 1 and len(pauses_avant) >= 3
    assert all(p == campaigns.ATTENTE_FILE_PARTAGEE_S for p in pauses_avant[:3])
    verrou.close()


def test_une_visite_vide_ne_compte_pas_l_ecart_suivant(tmp_path, reglages, monkeypatch, racine):
    """Au départ, les trois bras voient la page de départ et lancent chacun une visite ; un seul la prend, les deux autres
    n'ont rien pu prendre (`rien_a_faire`, aucune requête). Une telle visite ne compte pas l'écart de l'espacement (10
    min) : le bras relit la file à son rythme et visite dès qu'une page est à prendre, comme dans la commande."""
    experience, _, experiment_id = _preparer(tmp_path, reglages, monkeypatch)
    horloge = Horloge()

    class Vide(Passages):
        def __call__(self, *args, **kwargs):
            details = super().__call__(*args, **kwargs)
            return {**details, "rien_a_faire": len(self.appels) == 1, "travail_fini": len(self.appels) == 2}

    passages = Vide(reglages, horloge)
    monkeypatch.setattr(campaigns, "_passage", passages)
    rang = rang_de(experience, "ident-b")
    assert (
        campaigns.executer_unite(reglages, experiment_id, rang, horloge=horloge.now, dormir=horloge.dormir) == "termine"
    )
    assert len(passages.appels) == 2
    assert passages.appels[1]["quand"] - passages.appels[0]["quand"] < timedelta(minutes=1)


# ── 4. Rien de partagé, contrôlé au lancement ────────────────────────────────────────────────────


def test_au_lancement_deux_identites_au_meme_profil_sont_refusees(tmp_path, reglages, monkeypatch, racine):
    experience, cx, experiment_id = _preparer(tmp_path, reglages, monkeypatch)
    campaigns.controler_recoltes_partagees(cx, experience, reglages, experiment_id)  # tout est propre : rien à redire
    shutil.rmtree(racine / "essai-c" / "chrome")
    shutil.copytree(racine / "essai-a" / "chrome", racine / "essai-c" / "chrome")
    with pytest.raises(PartageRefuse, match="profil Chrome"):
        campaigns.controler_recoltes_partagees(cx, experience, reglages, experiment_id)


def test_a_la_reprise_une_identite_bannie_est_ecartee(tmp_path, reglages, monkeypatch, racine):
    experience, cx, experiment_id = _preparer(tmp_path, reglages, monkeypatch)
    campaigns.controler_recoltes_partagees(cx, experience, reglages, experiment_id)
    ouverte = ident.ouvrir("essai-b")
    ouverte.marquer("banni", "statut 403 (motif bannissement)")
    ouverte.liberer()
    with pytest.raises(PartageRefuse, match="bannie"):
        campaigns.controler_recoltes_partagees(cx, experience, reglages, experiment_id)
    moteur = db.engine_id(cx, "noezia", "1", "navigateur", {"label": "ident-a"})
    scenario = db.scenario_id(cx, "visite", "visite")
    cx.execute(
        "INSERT INTO runs (experiment_id, engine_id, scenario_id, repetition, session_token, truth, started_at, status,"
        " success, protection) VALUES (?, ?, ?, 1, 't-1', 'automatise', '2026-11-19', 'reussi', 1, 'endurance')",
        (experiment_id, moteur, scenario),
    )
    assert campaigns.controler_recoltes_partagees(cx, experience, reglages, experiment_id) == {
        "vitrine-partagee": ["essai-b"]
    }
