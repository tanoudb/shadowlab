"""Banc de mesure hors navigateur : la trajectoire de souris de NOEZIA telle que la page de l'Arena la relève.

Campagne 108 : au niveau 05, deux sessions arrêtées par `trajectoire_lineaire` (détecteur `entropie-interaction` :
au moins 10 angles entre segments et moyenne sous 0,08 rad). Le banc rejoue ce que le moteur fait sur une page de
récolte (`DriverNoezia._interaction_post_chargement`, avec la vraie `SimulateurSouris` et le vrai défilement), sans
navigateur, et calcule ce que `observateur.js` relèverait.

Modèle de la page (à revoir si l'observateur, Chrome ou la fenêtre changent) :
- fenêtre de 1200 × 825 px, rapport de pixels 1 : celle des campagnes 105 à 108 (relevé `fenetre` de l'empreinte) ;
- chaque `page.mouse.move(x, y)` donne un événement `mousemove` dont `clientX` et `clientY` sont la partie entière de
  la position envoyée (Chrome donne des pixels entiers ; l'arrondi au plus proche donne la même distribution) ;
- `observateur.js` (lignes 56 à 72) : angle entre les deux derniers segments quand chacun dépasse 3 px, arrondi au
  millième, 40 au plus par page ; les mouvements successifs d'une page se suivent dans la même chaîne de positions,
  qui repart de zéro à chaque page ;
- une session = 21 pages (campagne 108) ; la souris garde sa position d'une page à l'autre ;
- `time.sleep` avance une horloge fictive : aucune attente réelle, les délais entre mouvements sont ceux du moteur.

Validation du modèle sur le moteur d'avant la correction (graine 1, 21 000 pages) contre la base (campagnes 105 à
108, 4 575 pages d'au moins 10 angles) : moyenne des angles par page à 0,1 % / 1 % / 5 % / médiane = 0,076 / 0,128 /
0,310 / 0,728 rad (base : 0,081 / 0,130 / 0,315 / 0,726) ; sous 0,08 : 0,13 % des pages (base : 0,09 %) ; sous 0,15 :
1,5 % (base : 1,4 %) ; angles exactement nuls : 4,8 % (base : 4,9 %) ; pages à 40 angles : 20 % (base : 19 %).

Ce que le banc ne reproduit pas : la cadence d'images de Chrome (événements alignés sur l'image, fusion de deux
mouvements reçus dans la même image), le temps d'aller-retour du protocole CDP, les pages de défi d'entrée et les
gestes vers un élément (`deplacer_vers_element`, `pause_humaine`), absents d'une page de récolte.
"""

from __future__ import annotations

import math
import random
import statistics
import time
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from shadowlab.engines.noezia.comportement.defilement import SimulateurDefilement
from shadowlab.engines.noezia.comportement.souris import SimulateurSouris
from shadowlab.engines.noezia.config import ConfigNoezia
from shadowlab.engines.noezia.moteur import DriverNoezia

FENETRE = (1200, 825)  # innerWidth × innerHeight du vrai Chrome des campagnes 105 à 108
PAGES_PAR_SESSION = 21  # campagne 108 : vitrine à 20 annonces
SESSIONS = 1000  # 21 000 pages
GRAINE = 20261113
SEUIL_DETECTEUR = 0.08  # `trajectoire_lineaire` (detection.py), à ne pas modifier
MARGE = 0.15  # « un humain a un angle moyen > 0.15 rad » (commentaire du détecteur)
SEGMENT_MIN_PX = 3  # observateur.js : seuls comptent les segments de plus de 3 px
ANGLES_MAX = 40  # observateur.js : au plus 40 angles par page


def arrondi_js(valeur: float, decimales: int) -> float:
    """`Math.round(v * 10^d) / 10^d` de JavaScript (demi vers le haut, pas l'arrondi bancaire de Python)."""
    facteur = 10**decimales
    return math.floor(valeur * facteur + 0.5) / facteur


def angles_releves(positions: list[tuple[float, float]]) -> list[float]:
    """Les angles qu'`observateur.js` relève pour la suite de positions envoyées pendant une page."""
    angles: list[float] = []
    avant_derniere = derniere = None
    for x, y in positions:
        pos = (math.floor(x), math.floor(y))  # clientX, clientY entiers
        if avant_derniere is not None and derniere is not None and len(angles) < ANGLES_MAX:
            dx1, dy1 = derniere[0] - avant_derniere[0], derniere[1] - avant_derniere[1]
            dx2, dy2 = pos[0] - derniere[0], pos[1] - derniere[1]
            l1, l2 = math.hypot(dx1, dy1), math.hypot(dx2, dy2)
            if l1 > SEGMENT_MIN_PX and l2 > SEGMENT_MIN_PX:
                cosinus = max(-1.0, min(1.0, (dx1 * dx2 + dy1 * dy2) / (l1 * l2)))
                angles.append(arrondi_js(math.acos(cosinus), 3))
        avant_derniere, derniere = derniere, pos
    return angles


class _Horloge:
    """Remplace `time.sleep` : avance une horloge fictive sans attendre."""

    def __init__(self) -> None:
        self.t = 0.0

    def dormir(self, secondes: float) -> None:
        self.t += max(0.0, secondes)


class _SourisPage:
    """`page.mouse` de Playwright : note chaque position envoyée et chaque coup de molette, à l'heure fictive."""

    def __init__(self, horloge: _Horloge) -> None:
        self._horloge = horloge
        self.mouvements: list[tuple[float, float, float]] = []
        self.molette: list[float] = []

    def move(self, x: float, y: float, steps: int = 1) -> None:
        self.mouvements.append((x, y, self._horloge.t))

    def wheel(self, delta_x: float, delta_y: float) -> None:
        self.molette.append(self._horloge.t)


@dataclass
class PageSimulee:
    debut: float  # heure fictive (s) de l'arrivée sur la page
    fin: float
    mouvements: list[tuple[float, float, float]]  # (x, y, heure) de chaque `mouse.move`
    molette: list[float]  # heure de chaque coup de molette
    angles: list[float] = field(init=False)

    def __post_init__(self) -> None:
        self.angles = angles_releves([(x, y) for x, y, _ in self.mouvements])


def simuler(sessions: int, graine: int) -> list[list[PageSimulee]]:
    """Rejoue `sessions` sessions de récolte avec le code réel du moteur (souris, défilement, pauses)."""
    config = ConfigNoezia()
    horloge = _Horloge()
    etat = random.getstate()
    random.seed(graine)
    resultat: list[list[PageSimulee]] = []
    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(time, "sleep", horloge.dormir)
            for _ in range(sessions):
                souris_page = _SourisPage(horloge)
                page = SimpleNamespace(mouse=souris_page)
                # Comme `DriverNoezia.start_session` en identité native (fenêtre réelle, réglages par défaut).
                pilote = SimpleNamespace(
                    _config=config,
                    _souris=SimulateurSouris(
                        page,
                        viewport_w=FENETRE[0],
                        viewport_h=FENETRE[1],
                        a=config.souris.fitts_a,
                        b=config.souris.fitts_b,
                        overshoot_proba=config.souris.overshoot_proba,
                        bruit_vitesse=config.souris.bruit_vitesse,
                    ),
                    _defilement=SimulateurDefilement(
                        page, mode=config.defilement.mode, pixels_par_tick=config.defilement.pixels_par_tick
                    ),
                )
                pages: list[PageSimulee] = []
                for _ in range(PAGES_PAR_SESSION):
                    souris_page.mouvements, souris_page.molette = [], []
                    debut = horloge.t
                    DriverNoezia._interaction_post_chargement(pilote)  # ce que fait `navigate` après chaque page
                    pages.append(PageSimulee(debut, horloge.t, souris_page.mouvements, souris_page.molette))
                resultat.append(pages)
    finally:
        random.setstate(etat)
    return resultat


@pytest.fixture(scope="module")
def sessions() -> list[list[PageSimulee]]:
    resultat = simuler(SESSIONS, GRAINE)
    # `_interaction_post_chargement` avale ses exceptions : une page sans aucun mouvement trahirait un banc cassé.
    assert all(page.mouvements for session in resultat for page in session)
    return resultat


def test_aucune_page_ne_recoit_une_trajectoire_presque_droite(sessions):
    moyennes = [statistics.mean(p.angles) for session in sessions for p in session if len(p.angles) >= 10]
    assert len(moyennes) >= 20_000
    sous_seuil = sum(m < SEUIL_DETECTEUR for m in moyennes)
    sous_marge = sum(m < MARGE for m in moyennes)
    assert sous_marge == 0, (
        f"{sous_marge} pages sur {len(moyennes)} (d'au moins 10 angles) ont une moyenne des angles sous {MARGE} rad, "
        f"dont {sous_seuil} sous {SEUIL_DETECTEUR} rad (seuil de `trajectoire_lineaire`) ; "
        f"la plus basse : {min(moyennes):.3f} rad"
    )
