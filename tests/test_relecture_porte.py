"""La porte revenue sur une relecture de la lecture humaine (retour à la liste, fiche revue) : répétition d'I9.

Ce que la répétition du 16/11 a montré (vraie Arena, profil `endurancecourt`, porte de 600 s) : la porte a expiré
pendant une visite, et la première requête après l'expiration était un RETOUR À LA LISTE de la lecture humaine (D-94).
L'Arena a servi sa page de défi en 403, Chrome l'a franchie seul en une seconde, mais la récolte s'est arrêtée sur
« statut 403 » et a noté l'identité en `alerte`. Les quatre retours de porte d'avant tombaient sur une page lue par le
chemin principal (`_traiter`, qui passe par `_porte_en_cours`) et passaient sans alerte.

Ces tests rejouent ce cas sans navigateur ni Arena : pilote factice qui se comporte comme Chrome (la page change sur
place sans nouvelle requête), page de défi faite par le VRAI gabarit du site (`pages.page_defi`), servie en 403 comme
le fait `gardien._refus`, identité persistante sur disque, horloge factice. Ce qu'ils établissent : sur une relecture,
la porte revenue après sa durée déclarée est repassée par le même chemin que sur une page lue (bornes, trace
`porte_repassage`, `resume.json`), sans alerte ; revenue avant (marge comprise), elle donne `porte_revenue`.
Ce qu'ils ne prouvent pas : le comportement d'un vrai Chrome devant la vraie Arena (la répétition le dira).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from outils_recolte import creer_client, fabriquer, lu
from test_parcours_porte_en_cours import PiloteNavigateur, recette, vraie

from shadowlab.engines.noezia import identite as ident
from shadowlab.engines.noezia.lecture import LectureHumaine
from shadowlab.engines.noezia.parcours import TOLERANCE_PORTE_S, Options
from shadowlab.engines.noezia.sentinelle import detecter_defi
from shadowlab.site import pages as pages_du_site

DEBUT = datetime(2026, 11, 16, 16, 30, tzinfo=UTC)
DUREE_PORTE_S = 600  # profil `endurancecourt`
PAS_S = 20  # chaque page demandée prend 20 s sur l'horloge factice
LISTE = "=/lab/vitrine/annonces"
BASE_SITE = "http://127.0.0.1:8770"
# La page de défi JavaScript telle que l'Arena la sert (gardien.controler → pages.page_defi), statut 403.
DEFI = pages_du_site.page_defi("d" * 32, 18, "L2xhYi92aXRyaW5lL2Fubm9uY2Vz", jeton="ab" * 16)


@pytest.fixture
def site(reglages, monkeypatch):
    with creer_client(monkeypatch) as client:
        yield client


@pytest.fixture
def identite(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOWLAB_IDENTITES", str(tmp_path / "identites"))
    ouverte = ident.ouvrir("relecture-porte")
    yield ouverte
    ouverte.liberer()


class Chrome(PiloteNavigateur):
    """Comme `DriverNoezia` en mode identité : JavaScript, page relue sur place, identité persistante."""

    def __init__(self, client, identite):
        super().__init__(client, pas_s=PAS_S)
        self.identite_courante = identite
        identite.debut_visite()


def instant(secondes_horloge: float) -> datetime:
    return DEBUT + timedelta(seconds=secondes_horloge)


def defi_a_la_requete(pilote, rang: int, fragment: str, servie: tuple[int, str], apres: list[tuple[int, str]]):
    """À la `rang`-ième page demandée (et seulement elle), `fragment` reçoit `servie`, puis la page relue sur place
    devient tour à tour celles de `apres` (Chrome qui franchit le défi seul). L'horloge avance toujours."""
    avancer = pilote.pendant

    def pendant():
        avancer()
        if pilote.requetes_pages == rang:
            pilote.reponses[fragment] = servie
            pilote.apres_attente = list(apres)
        else:
            pilote.reponses.pop(fragment, None)

    pilote.pendant = pendant


def lancer(dossier, pilote, lecture, pages=6):
    h = pilote.horloge
    p = fabriquer(
        dossier,
        pilote,
        texte=recette(repassages_max=10, ecart_min_s=300) + f"  duree_s: {DUREE_PORTE_S}\n",
        options=Options(pages_max=pages, lecture=lecture),
        horloge=h,
        horodatage=lambda: instant(h.t).isoformat(timespec="seconds"),
    )
    return p, p.lancer()


RETOUR = LectureHumaine(duree_s=(0, 0, 0))  # liste, fiche, puis retour obligatoire à la liste (3e requête)
REVOIR = LectureHumaine(duree_s=(0, 0, 0), p_retour=0.0, p_revoir=1.0)  # … puis fiche, et la 1re fiche revue (5e)


def cas(nom, pilote):
    """(rang de la relecture, fragment, adresse, page réelle, lecture) pour `retour` (liste) ou `revoir` (fiche)."""
    if nom == "retour":
        return 3, LISTE, f"{BASE_SITE}/lab/vitrine/annonces", vraie(pilote), RETOUR
    return 5, "AN-000001", f"{BASE_SITE}/lab/vitrine/annonces/AN-000001", vraie(pilote, "AN-000001"), REVOIR


def test_la_page_de_defi_du_test_est_celle_du_site_et_reconnue():
    assert detecter_defi(DEFI) == "arena" and 'data-arena="defi"' in DEFI and "/lab/static/defi.js" in DEFI


@pytest.mark.parametrize("relecture", ["retour", "revoir"])
@pytest.mark.parametrize("forme", ["defi_qui_se_leve", "statut_perime"])
def test_la_porte_revenue_apres_sa_duree_sur_une_relecture_est_repassee_sans_alerte(
    site, identite, tmp_path, relecture, forme
):
    """`defi_qui_se_leve` : la page lue est le défi (403), il se lève à la relecture sur place. `statut_perime` : Chrome
    l'a déjà franchi pendant la lecture (le DOM est la vraie page, le statut celui du défi) : sans doute le cas réel."""
    pilote = Chrome(site, identite)
    rang, fragment, adresse, page, lecture = cas(relecture, pilote)
    vu = pilote.horloge.t + rang * PAS_S  # heure de la relecture
    identite.noter_porte(instant(vu) - timedelta(seconds=DUREE_PORTE_S + 10))  # le cookie a expiré il y a 10 s
    avant = identite.porte_franchie_le()
    if forme == "defi_qui_se_leve":
        defi_a_la_requete(pilote, rang, fragment, (403, DEFI), [(403, DEFI), (200, page)])
    else:
        defi_a_la_requete(pilote, rang, fragment, (403, page), [(200, page)])
    p, bilan = lancer(tmp_path / "r", pilote, lecture)

    assert bilan.code == 0 and bilan.statut == "limitee", bilan.arret
    assert identite.etat()["etat"] == "ok" and identite.porte_franchie_le() == instant(vu) > avant
    resume = lu(tmp_path / "r")
    repassages = resume["porte_repassages"]
    assert repassages["nombre"] == 1 and len(repassages["passages"]) == 1
    passage = repassages["passages"][0]
    assert passage["adresse"] == adresse and passage["franchie"] is True and passage["relecture"] is True
    assert passage["defi"] == ("arena" if forme == "defi_qui_se_leve" else "statut 403")
    assert passage["attente_s"] == (1.0 if forme == "defi_qui_se_leve" else 0.0)
    assert {"adresse": adresse, "statut": 200} in [
        {k: r[k] for k in ("adresse", "statut")} for r in resume["lecture_humaine"]["pages"]
    ]
    demandee = adresse.removeprefix(BASE_SITE)
    assert sum(d == demandee for d in pilote.demandes) == 2  # lue, puis relue une fois : aucun rechargement, aucun clic
    assert any("Porte repassée" in ligne for ligne in p.sortie_ecran)


@pytest.mark.parametrize("relecture", ["retour", "revoir"])
def test_la_porte_revenue_avant_sa_duree_sur_une_relecture_donne_l_alerte_porte_revenue(
    site, identite, tmp_path, relecture
):
    pilote = Chrome(site, identite)
    rang, fragment, adresse, page, lecture = cas(relecture, pilote)
    vu = pilote.horloge.t + rang * PAS_S
    ecoule = DUREE_PORTE_S - TOLERANCE_PORTE_S - 30  # avant la durée, au-delà de la marge
    identite.noter_porte(instant(vu) - timedelta(seconds=ecoule))
    avant = identite.porte_franchie_le()
    defi_a_la_requete(pilote, rang, fragment, (403, DEFI), [(403, DEFI), (200, page)])
    p, bilan = lancer(tmp_path / "r", pilote, lecture)

    assert bilan.code == 3 and bilan.arret["signe"] == "porte_revenue", bilan.arret
    assert bilan.arret["adresse"] == adresse
    assert p.horloge_factice.pauses == [] and pilote.relectures == 0  # aucune attente, aucun regard sur le défi
    assert pilote.requetes_pages == rang  # rien demandé après
    assert identite.etat()["etat"] == "alerte" and identite.porte_franchie_le() == avant
    passage = lu(tmp_path / "r")["porte_repassages"]["passages"][0]
    assert passage["refus"] == "duree_s" and passage["relecture"] is True and passage["franchie"] is False


def test_un_vrai_refus_sur_une_relecture_arrete_toujours(site, identite, tmp_path):
    """La page de refus de l'Arena (`blocage`) n'est pas une porte : la relecture s'arrête sur le 403, comme avant."""
    pilote = Chrome(site, identite)
    rang, fragment, _, _, lecture = cas("retour", pilote)
    identite.noter_porte(instant(pilote.horloge.t) - timedelta(seconds=DUREE_PORTE_S + 10))
    blocage = pages_du_site.page_blocage()
    defi_a_la_requete(pilote, rang, fragment, (403, blocage), [(403, blocage)])
    _, bilan = lancer(tmp_path / "r", pilote, lecture)
    assert bilan.code == 3 and bilan.arret["signe"] == "statut" and bilan.arret["statut"] == 403
    assert pilote.requetes_pages == rang and identite.etat()["etat"] == "alerte"
