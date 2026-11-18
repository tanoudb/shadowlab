"""Banc hors navigateur : une visite de la course I9 telle que le détecteur `comportement` de l'Arena la juge.

Ce qui s'est passé (course I9, base de la course, passage 19, monde 2, 17/11 à 20:43 UTC) : à la 6ᵉ visite du sujet,
l'Arena bloque une photo de la 3ᵉ page sur le score composite 0,6 (seuil 0,5 du profil `endurance`) :
`pas_de_scroll` (0,35 : au moins deux pages défilables, plus de 20 mouvements de souris en tout, AUCUN `scroll` sur
toutes ces pages) et `navigation_lineaire` (0,25 : au moins 4 pages, appels de données compris, toutes distinctes).
Les pages : fiche AN-000068 (4,2 s, 21 mouvements, 0 défilement, défilable), liste (2,8 s, 31 mouvements,
0 défilement, défilable), fiche AN-000069. Le visiteur est banni (D-92).

Les causes, dans le moteur (l'Arena ne change pas) :
1. une visite qui REPREND la passe (récolte incrémentale de la course, D-96 règle 7) commence sur la fiche suivante
   de la file, pas sur la liste ; le retour obligatoire à la liste après la première fiche (D-94) va donc à une liste
   que cette session n'a jamais vue : dès la 2ᵉ fiche, l'Arena voit 4 chemins distincts (fiche, son appel de données,
   liste, fiche). La propriété de D-94 « un chemin répété dès la quatrième requête » ne tient que si la visite
   commence sur la liste (soirée 131 : toutes les visites commençaient sur la liste) ;
2. une page sous 5 s est parcourue vite (`lecture.py`) ; avec les durées tirées par blocs de trois, les deux premières
   pages d'une visite sont toutes deux légères avec une probabilité de 1/3 × 0,633 = 0,211 ;
3. l'interaction légère (`DriverNoezia._interaction_post_clic_navigation`) ne défile qu'avec une probabilité de 0,4 :
   deux pages légères de suite sans aucun défilement, 0,6 × 0,6 = 0,36.
D'où, pour une visite qui commence sur une fiche : 0,211 × 0,36 = 7,6 % des visites portent l'enchaînement.
4. Trouvé par ce banc : dans une passe incrémentale (la course y serait passée vers son 3ᵉ jour), chaque fiche déjà
   lue, évitée sans requête, prenait quand même une durée au plan de lecture : le tirage par blocs de trois ne valait
   plus pour les pages lues (deux premières pages légères dans 30 % des visites, `duree_pages_reguliere` dans 5 %),
   et `pas_de_scroll` avec `duree_pages_reguliere` (0,75) arrêtait environ 1 visite incrémentale sur 80.

Le banc rejoue des visites avec le code réel : le parcours (`Parcours.visiter`, état durable, lecture humaine de D-94,
pages par visite tirées comme l'ordonnanceur), l'interaction du moteur (`DriverNoezia._interaction_selon_lecture`,
vraie souris et vrai défilement sur une page factice, horloge fictive) et le détecteur (`DetecteurComportement`,
`scoring.score_composite`, seuil composite du profil `endurance`), relu à chaque arrivée de page et de relevé, comme le
gardien le fait à chaque requête protégée.

Modèle (à revoir si le site, l'observateur ou la fenêtre changent) :
- le site vitrine est rendu par les fonctions de `site/vitrine.py` (300 annonces, comme la course), sans serveur ;
- une fiche donne deux pages au sens de l'Arena (le document et son appel de données `.../similaires`), une liste une
  seule ; le chemin est lu sans la requête (`?page=` et `?sl=` ne comptent pas), comme `observations_http.path` ;
- chaque page est défilable (vrai pour la liste et les fiches dans la fenêtre de la course, hauteur intérieure 770) ;
  un coup de molette donne un événement `scroll`, un `mouse.move` un `mousemove` ;
- la durée d'une page vue par l'Arena est la plus longue de la durée voulue par la lecture et de l'interaction ;
- seul le détecteur `comportement` est compté (à la visite 6, lui seul a parlé).
Ce que le banc ne reproduit pas : un vrai Chrome (fusion d'événements, temps de chargement, `scroll` sans coup de
molette), les autres détecteurs, la porte d'entrée.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from outils_recolte import GRAINE, fabriquer
from test_sentinelle import PiloteNavigateur
from test_souris_trajectoire import _Horloge, _SourisPage

from shadowlab import scoring
from shadowlab.arena import profils
from shadowlab.detection import DetecteurComportement, Observations
from shadowlab.engines.noezia.comportement.defilement import SimulateurDefilement
from shadowlab.engines.noezia.comportement.souris import SimulateurSouris
from shadowlab.engines.noezia.lecture import LectureHumaine
from shadowlab.engines.noezia.moteur import DriverNoezia
from shadowlab.engines.noezia.parcours import Options
from shadowlab.engines.noezia.rythme import tirer_lognormal
from shadowlab.site import vitrine

LISTE = "/lab/vitrine/annonces"
TAILLE_COURSE = 300  # vitrine de la course (D-96, règle 8)
PAGES_ORDONNANCEUR = (5, 15, 40)  # `visites.py` : pages par visite (minimum, médiane, maximum)
FENETRE = (1200, 770)  # fenêtre du vrai Chrome de la course (relevé `fenetre`, hauteur intérieure 770)
SEUIL_ENDURANCE = profils.charger().de("endurance").fingerprinting.seuil_composite  # 0,5


# ── Le site vitrine, sans serveur ────────────────────────────────────────────────────────────────────────────────


class ClientVitrine:
    """Les pages de la vitrine rendues par les fonctions du site (`site/app.py` les appelle de même)."""

    def __init__(self, taille: int = TAILLE_COURSE) -> None:
        self.annonces = vitrine.generer(GRAINE, taille)

    def get(self, chemin: str) -> SimpleNamespace:
        morceaux = urlsplit(chemin)
        if morceaux.path == LISTE:
            page = int(parse_qs(morceaux.query).get("page", ["1"])[0])
            return SimpleNamespace(status_code=200, text=vitrine.page_liste("j" * 32, self.annonces, page))
        annonce = vitrine.trouver(self.annonces, morceaux.path.rsplit("/", 1)[-1])
        if morceaux.path.startswith(f"{LISTE}/") and annonce is not None:
            return SimpleNamespace(status_code=200, text=vitrine.page_fiche("j" * 32, annonce))
        return SimpleNamespace(status_code=404, text="")


@dataclass
class PageVue:
    chemin: str  # sans la requête
    legere: bool  # parcourue vite (interaction légère)
    duree_voulue_s: float  # durée choisie par la lecture humaine


class PiloteVisite(PiloteNavigateur):
    """Navigateur factice : note chaque page demandée, sa lecture (vite ou en entier) et sa durée voulue."""

    name = "noezia"

    def __init__(self, client) -> None:
        super().__init__(client)
        self.lecture_legere = False
        self.pages: list[PageVue] = []
        self.parcours = None

    def navigate(self, url):
        if not url.endswith("/robots.txt"):
            duree = getattr(self.parcours, "_duree_voulue", 0.0)
            self.pages.append(PageVue(urlsplit(url).path, self.lecture_legere, duree))
        return super().navigate(url)

    def refus_ressources(self):
        return []


def simuler_visites(dossier, visites: int, graine: int, taille: int = TAILLE_COURSE) -> list[list[PageVue]]:
    """`visites` visites successives d'une même récolte durable (comme le sujet de la course) : chaque visite reprend la
    passe là où la précédente s'est arrêtée, pages par visite tirées comme l'ordonnanceur."""
    client = ClientVitrine(taille)
    alea = random.Random(graine)
    resultat = []
    for _ in range(visites):
        pages = min(max(round(tirer_lognormal(PAGES_ORDONNANCEUR, alea)), PAGES_ORDONNANCEUR[0]), PAGES_ORDONNANCEUR[2])
        pilote = PiloteVisite(client)
        options = Options(pages_max=pages, lecture=LectureHumaine(), entree_a_chaque_lancement=True)
        parcours = fabriquer(dossier, pilote, options=options)
        parcours._alea = random.Random(alea.random())  # un tirage propre à chaque visite (le scénario passe le sien)
        pilote.parcours = parcours
        parcours.visiter(pages)
        resultat.append(pilote.pages)
    return resultat


# ── L'interaction du moteur, sans navigateur ─────────────────────────────────────────────────────────────────────


@dataclass
class Geste:
    mousemove: int
    scroll: int
    duree_s: float  # durée de l'interaction (horloge fictive)


def interagir(pages: list[PageVue], graine: int) -> list[Geste]:
    """Ce que le moteur fait sur chaque page d'UNE visite (un pilote neuf, comme un Chrome relancé), code réel."""
    horloge = _Horloge()
    etat = random.getstate()
    random.seed(graine)
    gestes = []
    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(time, "sleep", horloge.dormir)
            souris_page = _SourisPage(horloge)
            page = SimpleNamespace(mouse=souris_page, evaluate=lambda *_a, **_k: True)  # toute page est défilable
            pilote = DriverNoezia(("*",), {"interaction_post_page": True})
            config = pilote._config
            pilote._page = page
            pilote._souris = SimulateurSouris(
                page,
                viewport_w=FENETRE[0],
                viewport_h=FENETRE[1],
                a=config.souris.fitts_a,
                b=config.souris.fitts_b,
                overshoot_proba=config.souris.overshoot_proba,
                bruit_vitesse=config.souris.bruit_vitesse,
            )
            pilote._defilement = SimulateurDefilement(
                page, mode=config.defilement.mode, pixels_par_tick=config.defilement.pixels_par_tick
            )
            for vue in pages:
                souris_page.mouvements, souris_page.molette = [], []
                debut = horloge.t
                pilote.lecture_legere = vue.legere
                pilote._interaction_selon_lecture()  # ce que fait `navigate` après le chargement
                gestes.append(Geste(len(souris_page.mouvements), len(souris_page.molette), horloge.t - debut))
    finally:
        random.setstate(etat)
    return gestes


# ── Le jugement de l'Arena ───────────────────────────────────────────────────────────────────────────────────────


@dataclass
class Jugement:
    bloque: bool
    score: float  # le plus haut score composite du détecteur pendant la visite
    signaux: frozenset[str]  # les signaux de ce moment-là
    vus: frozenset[str]  # tous les signaux levés au moins une fois


def documents_de(chemin: str) -> list[str]:
    """Les pages qu'une page du parcours donne à l'Arena : la fiche et son appel de données, ou la liste."""
    if chemin.startswith(f"{LISTE}/AN-"):
        return [chemin, f"/lab/vitrine/api/annonces/{chemin.rsplit('/', 1)[-1]}/similaires"]
    return [chemin]


def releve(geste: Geste, duree_s: float) -> dict:
    return {
        "evenements": {"mousemove": geste.mousemove, "click": 0, "keydown": 0, "scroll": geste.scroll, "touchstart": 0},
        "duree_page_ms": round(duree_s * 1000),
        "page_defilable": True,
    }


def juger(pages: list[PageVue], gestes: list[Geste], seuil: float = SEUIL_ENDURANCE) -> Jugement:
    """Relit la visite comme le gardien : à chaque page arrivée (document, puis appel de données) et à chaque relevé
    reçu (envoyé en quittant la page), le score composite du détecteur `comportement`."""
    detecteur = DetecteurComportement()
    origine = datetime(2026, 11, 17, 20, 43, tzinfo=UTC)
    instant = 0.0
    http = [{"path": "/lab/static/observateur.js", "received_at": origine.isoformat(), "method": "GET", "headers": []}]
    js: list[dict] = []
    pire, pire_signaux, vus = 0.0, frozenset(), set()

    def relire() -> bool:
        nonlocal pire, pire_signaux
        classement = detecteur.classer(Observations(http=list(http), js=list(js), visite_neuve=False))
        score = scoring.score_composite([classement])
        codes = frozenset(s.code for s in classement.signals)
        vus.update(codes)
        if score > pire:
            pire, pire_signaux = score, codes
        return score >= seuil

    for vue, geste in zip(pages, gestes, strict=True):
        for chemin in documents_de(vue.chemin):
            http.append(
                {
                    "path": chemin,
                    "received_at": (origine + timedelta(seconds=instant)).isoformat(),
                    "method": "GET",
                    "headers": [],
                }
            )
            if relire():
                return Jugement(True, pire, pire_signaux, frozenset(vus))
        duree = max(vue.duree_voulue_s, geste.duree_s)
        instant += duree
        js.append({"kind": "comportement", "page": vue.chemin, "payload": releve(geste, duree)})
        if relire():
            return Jugement(True, pire, pire_signaux, frozenset(vus))
    return Jugement(False, pire, pire_signaux, frozenset(vus))


def banc(
    dossier, visites: int, graine: int, taille: int = TAILLE_COURSE
) -> list[tuple[list[PageVue], list[Geste], Jugement]]:
    resultat = []
    for n, pages in enumerate(simuler_visites(dossier, visites, graine, taille)):
        gestes = interagir(pages, graine * 1000 + n)
        assert all(g.mousemove > 0 for g in gestes), "une page sans aucun mouvement : banc cassé"
        resultat.append((pages, gestes, juger(pages, gestes)))
    return resultat


def commence_sur_une_fiche(pages: list[PageVue]) -> bool:
    return pages[0].chemin.startswith(f"{LISTE}/AN-")


# ── Le banc reproduit la visite 6 ────────────────────────────────────────────────────────────────────────────────


def test_le_jugement_du_banc_rend_le_blocage_de_la_visite_6():
    """Les chiffres de la base de la course (relevés 382 et 384, passage 19) : 0,6, les deux mêmes signaux."""
    pages = [
        PageVue(f"{LISTE}/AN-000068", True, 4.155),
        PageVue(LISTE, True, 2.823),
        PageVue(f"{LISTE}/AN-000069", False, 9.0),
    ]
    gestes = [Geste(21, 0, 2.9), Geste(31, 0, 2.8), Geste(40, 12, 7.0)]
    jugement = juger(pages, gestes)
    assert jugement.bloque and jugement.score == pytest.approx(0.6)
    assert jugement.signaux == {"pas_de_scroll", "navigation_lineaire"}
    # Les mêmes pages, la liste défilée (visite 5) : pas de blocage.
    assert not juger(pages, [gestes[0], Geste(47, 58, 12.5), gestes[2]]).bloque


@pytest.fixture(scope="module")
def visites_reprises(tmp_path_factory):
    """100 visites qui reprennent la première passe (la course en était là à sa 6ᵉ visite) : vitrine assez grande pour
    que la passe ne finisse pas pendant le banc."""
    return banc(tmp_path_factory.mktemp("reprises") / "recolte", 100, 20261117, taille=2000)


@pytest.fixture(scope="module")
def visites_incrementales(tmp_path_factory):
    """60 visites d'une petite vitrine (100 annonces) : la première passe finie, chaque visite est une passe
    incrémentale (la course y serait passée vers son 3ᵉ jour), qui ne relit presque que des listes."""
    return banc(tmp_path_factory.mktemp("incrementales") / "recolte", 60, 20261118, taille=100)


def test_le_banc_rejoue_les_deux_sortes_de_visites_de_la_course(visites_reprises, visites_incrementales):
    """La première visite commence sur la liste ; les autres reprennent la passe (les visites 2 à 6 du sujet), puis,
    la passe finie, les visites incrémentales commencent par la liste et évitent les fiches déjà lues."""
    assert visites_reprises[0][0][0].chemin == LISTE
    assert all(len(pages) >= PAGES_ORDONNANCEUR[0] - 1 for pages, _, _ in visites_reprises)
    fin = visites_incrementales[-20:]
    assert all(pages[0].chemin == LISTE for pages, _, _ in fin)
    assert sum(1 for pages, _, _ in fin for p in pages if p.chemin == LISTE) > sum(
        1 for pages, _, _ in fin for p in pages if p.chemin.startswith(f"{LISTE}/AN-")
    )


# ── Ce que la correction doit garantir ───────────────────────────────────────────────────────────────────────────


def _fautives(visites, signal: str) -> list[int]:
    return [n for n, (_, _, j) in enumerate(visites) if signal in j.vus]


def test_aucune_visite_ne_quitte_toutes_ses_pages_defilables_sans_defilement(visites_reprises, visites_incrementales):
    """`pas_de_scroll` ne se lève jamais : la première page défilable d'une visite est toujours défilée."""
    for nom, visites in (("reprises", visites_reprises), ("incrémentales", visites_incrementales)):
        fautives = _fautives(visites, "pas_de_scroll")
        assert not fautives, f"{nom} : {len(fautives)} visites sur {len(visites)} lèvent pas_de_scroll : {fautives}"


def test_une_visite_qui_reprend_la_passe_voit_un_chemin_repete_des_la_quatrieme_page(visites_reprises):
    """La propriété de D-94 vaut aussi pour une visite qui reprend la passe : elle entre par la liste, donc la liste
    revue après la première fiche est un chemin répété, et `navigation_lineaire` ne se lève jamais."""
    fautives = _fautives(visites_reprises, "navigation_lineaire")
    assert not fautives, f"{len(fautives)} visites sur {len(visites_reprises)} lèvent navigation_lineaire : {fautives}"


def test_chaque_visite_qui_reprend_la_passe_entre_par_la_liste(visites_reprises):
    """La liste d'abord (la dernière lue de la passe), puis la fiche suivante de la file."""
    debuts = [[p.chemin for p in pages[:2]] for pages, _, _ in visites_reprises[1:]]
    fautifs = [d for d in debuts if d[0] != LISTE or not d[1].startswith(f"{LISTE}/AN-")]
    assert not fautifs, f"{len(fautifs)} visites sur {len(debuts)} : {fautifs[:5]}"


def test_aucune_visite_n_atteint_le_seuil_du_profil_endurance(visites_reprises, visites_incrementales):
    for nom, visites in (("reprises", visites_reprises), ("incrémentales", visites_incrementales)):
        bloquees = [(n, j.score, sorted(j.signaux)) for n, (_, _, j) in enumerate(visites) if j.bloque]
        assert not bloquees, f"{nom} : {len(bloquees)} visites bloquées sur {len(visites)} : {bloquees[:5]}"


def test_seules_les_pages_demandees_tirent_une_duree(tmp_path, monkeypatch):
    """Dans une passe incrémentale, les fiches déjà lues sont évitées sans requête : elles ne doivent pas prendre de
    durée au plan de lecture, sinon le tirage par blocs de trois (D-94) ne vaut plus pour les pages vraiment lues
    (banc : 30 % des visites incrémentales avec deux premières pages légères au lieu de 21 %, `duree_pages_reguliere`
    dans 4,9 % au lieu de moins de 0,5 %)."""
    from shadowlab.engines.noezia.lecture import PlanDeLecture

    tirees = []
    tirer = PlanDeLecture.duree_suivante

    def compter(plan):
        tirees.append(1)
        return tirer(plan)

    monkeypatch.setattr(PlanDeLecture, "duree_suivante", compter)
    visites = simuler_visites(tmp_path / "recolte", 12, 3, taille=45)
    demandees = sum(len(pages) for pages in visites)
    assert len(tirees) == demandees, f"{len(tirees)} durées tirées pour {demandees} pages demandées"


# ── La règle du moteur, page par page ────────────────────────────────────────────────────────────────────────────


class _Molette:
    def __init__(self) -> None:
        self.gestes = 0

    def defiler_bas(self, *_a) -> float:
        self.gestes += 1
        return 100.0


def _pilote_de_regle(monkeypatch, defilables: list[bool]):
    """Un `DriverNoezia` sans navigateur : souris muette, molette comptée, pages défilables ou non dans l'ordre
    donné ; le tirage à 0,4 de l'interaction légère tombe toujours du côté « pas de défilement »."""
    from shadowlab.engines.noezia import moteur

    monkeypatch.setattr(moteur.tempo, "pause_apres_navigation", lambda: None)
    monkeypatch.setattr(moteur.tempo, "pause_reflexion", lambda: None)
    monkeypatch.setattr(moteur.tempo, "pause_avant_clic", lambda: None)
    monkeypatch.setattr(moteur.tempo, "hesitation", lambda **_k: None)
    monkeypatch.setattr(moteur.time, "sleep", lambda _s: None)
    monkeypatch.setattr(moteur.random, "random", lambda: 0.99)
    pilote = DriverNoezia(("*",), {"interaction_post_page": True})
    reponses = iter(defilables)
    pilote._page = SimpleNamespace(evaluate=lambda *_a, **_k: next(reponses))
    pilote._souris = SimpleNamespace(mouvement_aleatoire=lambda: None)
    pilote._defilement = _Molette()
    pilote.lecture_legere = True
    return pilote


def test_la_premiere_page_defilable_d_une_visite_est_defilee_meme_parcourue_vite(monkeypatch):
    pilote = _pilote_de_regle(monkeypatch, [True, True, True])
    pilote._interaction_selon_lecture()
    assert pilote._defilement.gestes == 1
    # Ensuite, la loi de l'interaction légère reprend (0,4) : ici, le tirage dit non.
    pilote._interaction_selon_lecture()
    pilote._interaction_selon_lecture()
    assert pilote._defilement.gestes == 1


def test_une_page_trop_courte_pour_defiler_ne_compte_pas(monkeypatch):
    """Sur une page plus courte que la fenêtre, la molette ne donne aucun `scroll` : la page défilable suivante doit
    l'être."""
    pilote = _pilote_de_regle(monkeypatch, [False, True, True])
    pilote._interaction_selon_lecture()  # page courte : rien ne compte, qu'elle ait reçu la molette ou non
    pilote._interaction_selon_lecture()
    gestes = pilote._defilement.gestes
    pilote._interaction_selon_lecture()
    assert gestes >= 1 and pilote._defilement.gestes == gestes


def test_chaque_visite_repart_de_zero(monkeypatch):
    """Une visite = un Chrome relancé (`start_session`) : sa première page défilable est défilée à son tour."""
    pilote = _pilote_de_regle(monkeypatch, [True, True])
    pilote._interaction_selon_lecture()
    pilote._nouvelle_visite()
    pilote._interaction_selon_lecture()
    assert pilote._defilement.gestes == 2
