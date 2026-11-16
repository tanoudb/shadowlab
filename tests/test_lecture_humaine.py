"""Lecture humaine d'une visite (campagne 128) : retours à la liste, durées de page dispersées, refus d'une ressource.

Le problème mesuré : le moteur `noezia` natif, au profil `endurance`, était arrêté et banni sur le score composite 0,65
(0,4 `duree_pages_reguliere` + 0,25 `navigation_lineaire`, `detection.DetecteurComportement`). L'Arena juge à CHAQUE
requête protégée sur ce qu'elle a déjà reçu : le coefficient de variation (CV) des durées de page est donc lu sur chaque
début de visite (à partir de 3 relevés), pas seulement sur la visite entière. Ces tests le vérifient ainsi.

Ce que ces tests prouvent : la loi de lecture (`lecture.PlanDeLecture`) donne, avec la formule de l'Arena, un CV sous
0,25 sur moins de 0,5 % de 10 000 visites simulées (début de visite compris) ; la récolte revient à la liste en vraies
requêtes prises sur le budget de pages ; un 403 sur une ressource du même hôte arrête avant toute navigation.
Ce qu'ils ne prouvent pas : le comportement d'un vrai Chrome (planchers de durée posés ici comme constantes
mesurées) ni le verdict de l'Arena : cela demande l'essai réel (`configs/experiments/identite-rythme-essai.yaml`).
"""

from __future__ import annotations

import random
import statistics
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from outils_recolte import Horloge, creer_client, fabriquer, lu
from test_sentinelle import PiloteNavigateur

from shadowlab import detection, scenarios
from shadowlab.engines.noezia.lecture import LectureHumaine, PlanDeLecture
from shadowlab.engines.noezia.moteur import DriverNoezia
from shadowlab.engines.noezia.parcours import MoteurDriver, Options

LISTE = "/lab/vitrine/annonces"
# Durée d'une page déjà occupée par l'interaction du moteur, mesurée le 16/11 dans un vrai Chrome (14 essais chacune,
# hors chargement) : interaction complète 7,2 s (écart-type 1,6 ; 4,5 à 9,3 s), interaction légère
# (`_interaction_post_clic_navigation`) 2,8 s (écart-type 0,65 ; 1,7 à 3,9 s).
# Les planchers ci-dessous en sont la moyenne.
PLANCHER_COMPLET_S = 7.2
PLANCHER_LEGER_S = 2.8
# Aujourd'hui (campagne 128, passages réussis) : environ 6,5 s par page.
DUREE_ACTUELLE_S = 6.5
SEUIL_CV_ARENA = 0.2  # `duree_pages_reguliere` : CV < 0,2 (detection.py)
MARGE_CV = 0.25  # l'objectif demandé : sous 0,25 sur moins de 0,5 % des visites


def cv_arena(durees: list[float]) -> float:
    """Le calcul de `DetecteurComportement` (detection.py, « Analyse des pauses inter-pages »)."""
    return statistics.stdev(durees) / statistics.mean(durees)


def durees_de_visite(plan: PlanDeLecture, pages: int, alea: random.Random | None = None) -> list[float]:
    """Durée vue par l'Arena pour chaque page : la durée choisie, sauf si l'interaction du moteur dure plus.

    Sans `alea` le plancher est constant (aucune dispersion du moteur) ; avec, il suit la mesure du vrai Chrome."""
    durees = []
    for _ in range(pages):
        voulue = plan.duree_suivante()
        if alea is None:
            plancher = PLANCHER_LEGER_S if plan.legere(voulue) else PLANCHER_COMPLET_S
        elif plan.legere(voulue):
            plancher = min(max(alea.gauss(2.8, 0.65), 1.7), 3.9)
        else:
            plancher = min(max(alea.gauss(7.2, 1.6), 4.4), 9.4)
        durees.append(max(voulue, plancher))
    return durees


def debut_trop_regulier(durees: list[float], seuil: float = MARGE_CV) -> bool:
    """Vrai si un début de visite d'au moins 3 pages a un CV sous `seuil` (l'Arena juge à chaque requête)."""
    return any(cv_arena(durees[:n]) < seuil for n in range(3, len(durees) + 1))


# ── Les durées de page ───────────────────────────────────────────────────────────────────────────────────────


def test_sur_10000_visites_un_debut_de_visite_trop_regulier_est_plus_rare_que_0_5_pour_cent():
    lecture = LectureHumaine()
    alea = random.Random(20261116)
    visites = 10_000
    trop_regulieres = sum(
        debut_trop_regulier(durees_de_visite(PlanDeLecture(lecture, alea), 15)) for _ in range(visites)
    )
    assert trop_regulieres / visites < 0.005, f"{trop_regulieres} visites sur {visites}"


def test_meme_avec_des_planchers_mesures_dans_un_vrai_chrome_et_des_visites_plus_courtes():
    """Le plancher de l'interaction suit la mesure (écart-type compris), et des visites de 8 à 15 pages."""
    lecture = LectureHumaine()
    alea = random.Random(7)
    pires = 0
    for _ in range(10_000):
        pages = alea.randint(8, 15)
        pires += debut_trop_regulier(durees_de_visite(PlanDeLecture(lecture, alea), pages, alea))
    assert pires / 10_000 < 0.005


def test_la_moyenne_des_durees_reste_proche_de_celle_d_aujourd_hui():
    lecture = LectureHumaine()
    alea = random.Random(11)
    durees = [d for _ in range(2000) for d in durees_de_visite(PlanDeLecture(lecture, alea), 15)]
    moyenne = statistics.mean(durees)
    assert DUREE_ACTUELLE_S * 0.9 <= moyenne <= DUREE_ACTUELLE_S * 1.35, moyenne  # une visite ne doit pas exploser


def test_les_durees_choisies_sont_bornees_et_tres_dispersees():
    lecture = LectureHumaine()
    plan = PlanDeLecture(lecture, random.Random(3))
    tirees = [plan.duree_suivante() for _ in range(5000)]
    minimum, mediane, maximum = lecture.duree_s
    assert min(tirees) >= minimum and max(tirees) <= maximum
    assert statistics.median(tirees) == pytest.approx(mediane, rel=0.1)
    assert statistics.stdev(tirees) / statistics.mean(tirees) > 0.6  # forte dispersion (log-normale)


def test_une_duree_nulle_ne_fait_rien_attendre():
    plan = PlanDeLecture(LectureHumaine(duree_s=(0, 0, 0)), random.Random(1))
    assert [plan.duree_suivante() for _ in range(5)] == [0.0] * 5


def test_la_page_est_legere_sous_le_seuil_seulement():
    lecture = LectureHumaine(seuil_leger_s=5.0)
    plan = PlanDeLecture(lecture, random.Random(1))
    assert plan.legere(4.9) is True and plan.legere(5.0) is False


def _observations(durees_ms: list[int], chemins: list[str]) -> detection.Observations:
    """Une visite telle que l'Arena la reçoit : un relevé de comportement par page, une requête par chemin."""
    debut = datetime(2026, 11, 16, 10, 0, tzinfo=UTC)
    http = [
        {"path": "/lab/static/observateur.js", "received_at": debut.isoformat(), "method": "GET", "headers": []},
        *[
            {
                "path": chemin,
                "received_at": (debut + timedelta(seconds=10 * i)).isoformat(),
                "method": "GET",
                "headers": [],
            }
            for i, chemin in enumerate(chemins)
        ],
    ]
    js = []
    for i, duree in enumerate(durees_ms):
        js.append(
            {
                "kind": "comportement",
                "page": chemins[min(i, len(chemins) - 1)],
                "received_at": (debut + timedelta(seconds=10 * i + 5)).isoformat(),
                "payload": {
                    "evenements": {"mousemove": 60, "click": 2, "scroll": 4},
                    "duree_page_ms": duree,
                    "page_defilable": True,
                },
            }
        )
    return detection.Observations(http=http, js=js)


def _codes(obs: detection.Observations) -> set[str]:
    return {s.code for s in detection.DetecteurComportement().classer(obs).signals}


def test_la_formule_du_test_est_celle_de_l_arena():
    chemins = [LISTE, f"{LISTE}/AN-000001", "/lab/vitrine/api/annonces/AN-000001/similaires", f"{LISTE}/AN-000002"]
    reguliere = _observations([6500, 6700, 6400, 6600], chemins)
    dispersee = _observations([1800, 9000, 3000, 21000], chemins)
    assert "duree_pages_reguliere" in _codes(reguliere)
    assert "duree_pages_reguliere" not in _codes(dispersee)
    assert cv_arena([6.5, 6.7, 6.4, 6.6]) < SEUIL_CV_ARENA < cv_arena([1.8, 9.0, 3.0, 21.0])


def test_un_retour_a_la_liste_leve_navigation_lineaire_des_la_quatrieme_requete():
    """L'Arena compte les appels de données comme des pages : liste, fiche, appel, puis la liste revue."""
    lineaire = [LISTE, f"{LISTE}/AN-000001", "/lab/vitrine/api/annonces/AN-000001/similaires", f"{LISTE}/AN-000002"]
    avec_retour = [*lineaire[:3], LISTE]
    durees = [6500, 2000, 9000, 4000]
    assert "navigation_lineaire" in _codes(_observations(durees, lineaire))
    assert "navigation_lineaire" not in _codes(_observations(durees, avec_retour))


# ── Les actions entre deux pages ─────────────────────────────────────────────────────────────────────────


def test_apres_la_premiere_fiche_le_retour_a_la_liste_est_obligatoire():
    for graine in range(50):
        plan = PlanDeLecture(LectureHumaine(), random.Random(graine))
        assert plan.action(feuilles_lues=1, restant=10) == "liste"


def test_sans_page_restante_il_n_y_a_aucune_action():
    plan = PlanDeLecture(LectureHumaine(), random.Random(1))
    assert plan.action(feuilles_lues=1, restant=0) is None
    assert all(plan.action(feuilles_lues=5, restant=0) is None for _ in range(50))


def test_les_actions_suivantes_sont_des_retours_ou_des_pages_revues_a_taux_voulu():
    lecture = LectureHumaine(p_retour=0.2, p_revoir=0.08)
    plan = PlanDeLecture(lecture, random.Random(5))
    actions = [plan.action(feuilles_lues=4, restant=None) for _ in range(20_000)]
    assert actions.count("liste") / len(actions) == pytest.approx(0.2, abs=0.015)
    assert actions.count("revoir") / len(actions) == pytest.approx(0.08, abs=0.01)
    assert set(actions) == {"liste", "revoir", None}


def test_une_page_revue_est_une_page_deja_lue_autre_que_la_derniere():
    plan = PlanDeLecture(LectureHumaine(), random.Random(2))
    lues = ["a", "b", "c", "d"]
    assert {plan.feuille_a_revoir(lues) for _ in range(200)} == {"a", "b", "c"}


# ── Dans le parcours ─────────────────────────────────────────────────────────────────────────────────────


class PiloteLecture(PiloteNavigateur):
    """Navigateur factice : note, pour chaque page demandée, si le moteur devait la parcourir vite."""

    name = "noezia"

    def __init__(self, client, hotes=("*",)):
        super().__init__(client, hotes)
        self.lecture_legere = False
        self.modes: list[bool] = []
        self.refus: list[tuple[str, int]] = []

    def navigate(self, url):
        if not url.endswith("/robots.txt"):
            self.modes.append(self.lecture_legere)
        return super().navigate(url)

    def refus_ressources(self):
        refus, self.refus = self.refus, []
        return refus


@pytest.fixture
def site(reglages, monkeypatch):
    with creer_client(monkeypatch) as client:
        yield client


@pytest.fixture
def dossier(tmp_path):
    return tmp_path / "recoltes" / "vitrine-annonces"


def _chemins(pilote) -> list[str]:
    return [urlsplit(u).path for u in pilote.urls if not u.endswith("/robots.txt")]


def _lancer(dossier, pilote, pages, lecture=None):
    parcours = fabriquer(dossier, pilote, options=Options(pages_max=pages, lecture=lecture))
    return parcours, parcours.lancer()


def test_la_lecture_humaine_est_eteinte_par_defaut():
    assert Options().lecture is None


def test_la_visite_revient_a_la_liste_apres_la_premiere_fiche_par_une_vraie_requete(site, dossier):
    pilote = PiloteLecture(site)
    _, bilan = _lancer(dossier, pilote, 15, LectureHumaine())
    chemins = _chemins(pilote)
    assert chemins[0] == LISTE and chemins[1].startswith(f"{LISTE}/AN-") and chemins[2] == LISTE
    assert chemins.count(LISTE) >= 2
    assert bilan.statut == "limitee"


def test_les_retours_se_prennent_sur_le_budget_de_pages_jamais_en_plus(site, dossier):
    for pages in (3, 6, 15):
        pilote = PiloteLecture(site)
        _, bilan = _lancer(dossier / f"p{pages}", pilote, pages, LectureHumaine())
        assert pilote.requetes_pages == pages, pages
        resume = lu(dossier / f"p{pages}", bilan.passe)
        assert resume["pages"]["faites"] + resume["lecture_humaine"]["relectures"] == pages


def test_une_visite_de_15_pages_ne_depasse_pas_29_pages_vues_par_l_arena(site, dossier):
    """15 documents et 14 appels de données au plus (aujourd'hui) : une fiche en demande deux, la liste un."""
    pilote = PiloteLecture(site)
    _lancer(dossier, pilote, 15, LectureHumaine())
    fiches = sum(1 for c in _chemins(pilote) if "/AN-" in c)
    listes = sum(1 for c in _chemins(pilote) if c == LISTE or c.startswith(f"{LISTE}?"))
    assert fiches + listes == 15
    assert 15 + fiches <= 29  # un document par page, plus un appel de données par fiche


def test_deux_pages_sans_place_pour_un_retour_n_en_font_pas(site, dossier):
    pilote = PiloteLecture(site)
    _lancer(dossier, pilote, 2, LectureHumaine())
    assert _chemins(pilote)[0] == LISTE and "/AN-" in _chemins(pilote)[1] and pilote.requetes_pages == 2


def test_chaque_page_attend_la_duree_choisie_et_les_pages_rapides_sont_parcourues_vite(site, dossier):
    pilote = PiloteLecture(site)
    parcours, _ = _lancer(dossier, pilote, 15, LectureHumaine())
    pauses = [p for p in parcours.horloge_factice.pauses if p > 0]
    assert len(set(round(p, 3) for p in pauses)) > 5  # des durées toutes différentes
    assert True in pilote.modes and False in pilote.modes  # des pages vues vite, d'autres lues en entier
    assert len(pilote.modes) == 15


def test_sans_lecture_humaine_le_parcours_ne_change_pas(site, dossier):
    pilote = PiloteLecture(site)
    _, bilan = _lancer(dossier, pilote, 6)
    assert _chemins(pilote).count(LISTE) == 1 and "lecture_humaine" not in lu(dossier, bilan.passe)
    assert set(pilote.modes) == {False}


def test_un_refus_au_retour_a_la_liste_arrete_la_visite_sans_autre_requete(site, dossier):
    pilote = PiloteLecture(site)

    def refuser_la_liste_au_retour():
        if pilote.requetes_pages == 3:  # la 3e requête est le retour à la liste
            pilote.reponses["=" + LISTE] = (403, "<html><body><p>refus</p></body></html>")

    pilote.pendant = refuser_la_liste_au_retour
    parcours, bilan = _lancer(dossier, pilote, 15, LectureHumaine())
    assert bilan.statut == "arretee" and bilan.arret["statut"] == 403
    assert pilote.requetes_pages == 3


# ── Un refus sur une ressource ───────────────────────────────────────────────────────────────────────────


class IdentiteFactice:
    def __init__(self):
        self.marques: list[tuple[str, str]] = []

    def marquer(self, verdict, detail, quand=None):
        self.marques.append((verdict, detail))

    def noter_porte(self, quand):
        pass


class PiloteAvecIdentite(PiloteLecture):
    def __init__(self, client):
        super().__init__(client)
        self.identite_courante = IdentiteFactice()


PHOTO = "http://127.0.0.1:8770/lab/vitrine/photos/AN-000001/1.svg"
API = "http://127.0.0.1:8770/lab/vitrine/api/annonces/AN-000001/similaires"


@pytest.mark.parametrize("ressource", [PHOTO, API])
def test_un_403_sur_une_ressource_du_meme_hote_arrete_avant_toute_nouvelle_navigation(site, dossier, ressource):
    pilote = PiloteAvecIdentite(site)

    def refuser_pendant_la_deuxieme_page():
        if pilote.requetes_pages == 2:
            pilote.refus = [(ressource, 403)]

    pilote.pendant = refuser_pendant_la_deuxieme_page
    _, bilan = _lancer(dossier, pilote, 15)  # SANS lecture humaine : la sentinelle vaut partout
    assert bilan.statut == "arretee" and bilan.arret["signe"] == "statut" and bilan.arret["statut"] == 403
    assert bilan.arret["adresse"] == ressource
    assert pilote.requetes_pages == 2  # la page suivante n'a jamais été demandée
    assert [v for v, _ in pilote.identite_courante.marques] == ["alerte"]


def test_un_403_sur_une_ressource_de_la_premiere_page_est_un_bannissement(site, dossier):
    pilote = PiloteAvecIdentite(site)
    pilote.pendant = lambda: setattr(pilote, "refus", [(PHOTO, 403)]) if pilote.requetes_pages == 1 else None
    _, bilan = _lancer(dossier, pilote, 15)
    assert bilan.statut == "arretee" and pilote.requetes_pages == 1
    assert [v for v, _ in pilote.identite_courante.marques] == ["banni"]


def test_un_403_d_un_autre_hote_n_arrete_rien(site, dossier):
    pilote = PiloteLecture(site)
    pilote.pendant = lambda: setattr(pilote, "refus", [("https://cdn.exemple.test/x.js", 403)])
    _, bilan = _lancer(dossier, pilote, 4)
    assert bilan.statut == "limitee" and pilote.requetes_pages == 4


def test_un_403_arrive_pendant_la_lecture_arrete_avant_la_page_suivante(site, dossier):
    """Un navigateur reçoit aussi des événements pendant l'attente de lecture : on regarde juste avant de naviguer."""
    pilote = PiloteLecture(site)

    class HorlogeQuiRecoitUnRefus(Horloge):
        def dormir(self, secondes):
            super().dormir(secondes)
            if pilote.requetes_pages == 2:
                pilote.refus = [(API, 403)]

    parcours = fabriquer(
        dossier, pilote, options=Options(pages_max=15, lecture=LectureHumaine()), horloge=HorlogeQuiRecoitUnRefus()
    )
    bilan = parcours.lancer()
    assert bilan.statut == "arretee" and bilan.arret["adresse"] == API
    assert pilote.requetes_pages == 2


# ── Le moteur navigateur ─────────────────────────────────────────────────────────────────────────────────


def _pilote_noezia(url="http://127.0.0.1:8770/lab/vitrine/annonces/AN-000001") -> DriverNoezia:
    d = DriverNoezia(("*",), {"interaction_post_page": True, "resoudre_defis": False})
    d._page = SimpleNamespace(url=url, main_frame=object(), evaluate=lambda _: 0)
    return d


def _reponse(url, statut, navigation=False, cadre=None):
    return SimpleNamespace(
        url=url, status=statut, frame=cadre, request=SimpleNamespace(is_navigation_request=lambda: navigation)
    )


def test_le_moteur_retient_les_403_des_ressources_du_meme_hote_et_les_rend_une_fois():
    d = _pilote_noezia()
    d._noter_reponse(_reponse(PHOTO, 403))
    d._noter_reponse(_reponse(API, 403))
    d._noter_reponse(_reponse(PHOTO, 200))  # une ressource servie : rien
    d._noter_reponse(_reponse("http://127.0.0.1:8770/lab/vitrine/photos/x.svg", 404))  # pas un refus
    d._noter_reponse(_reponse("https://cdn.exemple.test/x.js", 403))  # un autre hôte
    assert d.refus_ressources() == [(PHOTO, 403), (API, 403)]
    assert d.refus_ressources() == []


def test_le_403_de_la_page_elle_meme_n_est_pas_une_ressource():
    d = _pilote_noezia()
    d._noter_reponse(_reponse(LISTE, 403, navigation=True, cadre=d._page.main_frame))
    assert d.refus_ressources() == []


def test_la_navigation_oublie_les_refus_de_la_page_precedente(monkeypatch):
    d = _pilote_noezia()
    d._noter_reponse(_reponse(PHOTO, 403))
    monkeypatch.setattr(d, "_naviguer_avec_essais", lambda url, attente: SimpleNamespace(status=200))
    monkeypatch.setattr(d, "_interaction_post_chargement", lambda: None)
    d.navigate("http://127.0.0.1:8770/lab/vitrine/annonces")
    assert d.refus_ressources() == []


@pytest.mark.parametrize(("legere", "attendu"), [(False, "complete"), (True, "legere")])
def test_la_lecture_legere_choisit_l_interaction_legere(monkeypatch, legere, attendu):
    d = _pilote_noezia()
    appels = []
    monkeypatch.setattr(d, "_naviguer_avec_essais", lambda url, attente: SimpleNamespace(status=200))
    monkeypatch.setattr(d, "_interaction_post_chargement", lambda: appels.append("complete"))
    monkeypatch.setattr(d, "_interaction_post_clic_navigation", lambda: appels.append("legere"))
    d.lecture_legere = legere
    d.navigate("http://127.0.0.1:8770/lab/vitrine/annonces")
    assert appels == [attendu]


def test_le_moteur_de_parcours_transmet_la_lecture_et_les_refus_au_pilote():
    d = _pilote_noezia()
    moteur = MoteurDriver(d, "navigateur")
    moteur.regler_lecture(True)
    assert d.lecture_legere is True
    d._noter_reponse(_reponse(PHOTO, 403))
    assert moteur.refus_ressources() == [(PHOTO, 403)]


def test_un_pilote_sans_ces_fonctions_est_accepte(site):
    moteur = MoteurDriver(PiloteNavigateur(site), "navigateur")
    moteur.regler_lecture(True)  # sans effet, sans erreur
    assert moteur.refus_ressources() == []


# ── Le scénario `visite` ─────────────────────────────────────────────────────────────────────────────────


def _options_prises(monkeypatch, pilote_nom, scenario):
    prises = {}

    def faux(
        d, base, jeton, rng, recette, moteur, *, options=None, duree_porte_s=None, noter=None, dossier_durable=None
    ):
        prises["options"] = options
        bilan = SimpleNamespace(
            statut="limitee",
            arret=None,
            passe=1,
            resume={
                "pages": {"faites": 1, "echecs": 0},
                "lecture_humaine": {"relectures": 2},
                "lancement": {"pages": 1, "echecs": 0, "relectures": 2},  # ce que la visite a lu (I9)
                "incrementale": {"active": False},
            },
        )
        return bilan, None

    monkeypatch.setattr(scenarios, "_lancer_parcours", faux)
    monkeypatch.setattr(scenarios, "_visiteur_vu", lambda jeton: {})
    pilote = SimpleNamespace(name=pilote_nom, runtime="navigateur", identite_courante=None)
    issue = scenario.executer(pilote, "http://127.0.0.1:8770", "ab" * 16, random.Random(1))
    return prises["options"], issue


def test_le_scenario_visite_allume_la_lecture_humaine_pour_noezia(monkeypatch):
    options, issue = _options_prises(monkeypatch, "noezia", scenarios.SCENARIOS["visite"])
    assert options.lecture is scenarios.LECTURE_HUMAINE_VISITE
    assert issue.details["relectures"] == 2


def test_le_temoin_classique_reste_classique(monkeypatch):
    options, _ = _options_prises(monkeypatch, "playwright", scenarios.SCENARIOS["visite"])
    assert options.lecture is None


def test_la_lecture_est_aussi_dans_le_scenario_a_pages_comptees(monkeypatch):
    options, _ = _options_prises(monkeypatch, "noezia", scenarios.avec_pages(6))
    assert options.lecture is scenarios.LECTURE_HUMAINE_VISITE and options.pages_max == 6


def test_la_recolte_generale_n_a_pas_de_lecture_humaine(monkeypatch):
    prises = {}

    def faux(d, base, jeton, rng, recette, moteur, *, options=None, duree_porte_s=None, noter=None):
        prises["options"] = options
        bilan = SimpleNamespace(statut="terminee", arret=None, resume={"pages": {"faites": 1, "echecs": 0}})
        return bilan, {"reussi": True}

    monkeypatch.setattr(scenarios, "_lancer_parcours", faux)
    pilote = SimpleNamespace(
        name="noezia", runtime="navigateur", configuration=lambda: {"identite_native": True}, identite_courante=None
    )
    scenarios.recolte_recette_vitrine(pilote, "http://127.0.0.1:8770", "ab" * 16, random.Random(1))
    assert prises["options"] is None


# ── Une relecture respecte robots.txt, son délai et le périmètre des hôtes (D-70) ────────────────────────


class RobotsFactice:
    """Remplace `robots.Robots` : la liste est refusée dès la 2e page demandée si `refuser_la_relecture`."""

    def __init__(self, reel, pilote, crawl_delay=None, refuser_la_relecture=False):
        self._reel = reel
        self._pilote = pilote
        self.crawl_delay = crawl_delay
        self._refuser = refuser_la_relecture

    def __getattr__(self, nom):  # le reste (état, résumé) vient du vrai `Robots`
        return getattr(self._reel, nom)

    def permis(self, chemin):
        if chemin.split("?")[0] == LISTE:
            return not (self._refuser and self._pilote.requetes_pages >= 2)  # la liste est permise à la 1re lecture
        return True


def _parcours_avec_robots(dossier, pilote, pages=3, **reglages):
    parcours = fabriquer(dossier, pilote, options=Options(pages_max=pages, lecture=LectureHumaine()))
    reel = parcours._robots_de
    faux = {}
    parcours._robots_de = lambda adresse: faux.setdefault(adresse, RobotsFactice(reel(adresse), pilote, **reglages))
    return parcours


def test_une_relecture_interdite_par_robots_n_est_pas_demandee(site, dossier):
    pilote = PiloteLecture(site)
    parcours = _parcours_avec_robots(dossier, pilote, refuser_la_relecture=True)
    bilan = parcours.lancer()
    assert bilan.statut == "limitee" and _chemins(pilote).count(LISTE) == 1
    assert pilote.requetes_pages == 3  # la page prévue au retour est lue autrement : une fiche de plus


def test_une_relecture_attend_le_delai_de_robots(site, dossier):
    pilote = PiloteLecture(site)
    parcours = _parcours_avec_robots(dossier, pilote, crawl_delay=1000)
    parcours.lancer()
    assert _chemins(pilote).count(LISTE) == 2  # liste, fiche, liste revue
    assert len([p for p in parcours.horloge_factice.pauses if p >= 900]) == 2  # la fiche ET la relecture


def test_une_relecture_vers_un_autre_hote_n_est_pas_demandee(site, dossier):
    pilote = PiloteLecture(site)
    parcours = fabriquer(dossier, pilote, options=Options(pages_max=3, lecture=LectureHumaine()))
    pilote.pendant = lambda: setattr(parcours, "_hotes", {"autre.test"}) if pilote.requetes_pages == 2 else None
    parcours.lancer()
    assert _chemins(pilote).count(LISTE) == 1 and pilote.requetes_pages == 2
