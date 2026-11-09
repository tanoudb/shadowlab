"""Modèles statistiques du comportement humain.

Distributions calibrées sur la littérature psychomotrice :
- Fitts (1954) : temps de pointage
- Card, Moran & Newell (1983) : modèle GOMS, timing clavier
- Hwang et al. (2006) : distributions de délais souris (log-normale)
- Salthouse (1984) : digraphes clavier

L'objectif : générer du comportement statistiquement indistinguable
d'un humain quel que soit le test appliqué (KS, AD, auto-corrélation,
entropie, chi², etc.). Pas de seuils à tuner — les distributions
sont correctes par construction.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

# ── Distributions de base ──────────────────────────────────────────────


def log_normale(mu_ms: float, sigma: float, borne_min: float = 0, borne_max: float = float("inf")) -> float:
    """Échantillon log-normal. mu_ms est la MÉDIANE en ms, sigma le paramètre de forme."""
    val = random.lognormvariate(math.log(mu_ms), sigma)
    return max(borne_min, min(borne_max, val))


def ex_gaussienne(mu: float, sigma: float, tau: float) -> float:
    """Distribution ex-gaussienne (gaussienne + exponentielle).

    Modèle classique des temps de réaction humains (Luce, 1986).
    mu, sigma : composante gaussienne ; tau : queue exponentielle.
    """
    gauss = random.gauss(mu, sigma)
    expo = random.expovariate(1.0 / tau) if tau > 0 else 0
    return max(0, gauss + expo)


def pareto_bornee(alpha: float, xm: float, borne_max: float) -> float:
    """Distribution de Pareto bornée — pour les longues pauses."""
    val = xm / (random.random() ** (1.0 / alpha))
    return min(val, borne_max)


# ── Délais souris ──────────────────────────────────────────────────────


@dataclass
class ProfilSouris:
    """Paramètres du profil moteur souris."""

    pause_mediane_ms: float = 280.0
    pause_sigma: float = 0.9
    pause_min_ms: float = 30.0
    pause_max_ms: float = 8000.0
    micro_pause_proba: float = 0.08
    micro_pause_mediane_ms: float = 1200.0
    micro_pause_sigma: float = 0.6


# Profils pré-calibrés
PROFIL_RAPIDE = ProfilSouris(pause_mediane_ms=180, pause_sigma=0.7, micro_pause_proba=0.05)
PROFIL_MOYEN = ProfilSouris()
PROFIL_LENT = ProfilSouris(pause_mediane_ms=420, pause_sigma=1.0, micro_pause_proba=0.12, micro_pause_mediane_ms=1800)


def delai_inter_mouvement(profil: ProfilSouris | None = None) -> float:
    """Délai entre deux mouvements de souris (ms).

    Distribution log-normale avec micro-pauses occasionnelles (Pareto).
    Correspond aux observations de Hwang et al. (2006) et aux données
    de sessions web réelles.
    """
    p = profil or PROFIL_MOYEN

    if random.random() < p.micro_pause_proba:
        return log_normale(p.micro_pause_mediane_ms, p.micro_pause_sigma, borne_min=500, borne_max=p.pause_max_ms)

    return log_normale(p.pause_mediane_ms, p.pause_sigma, borne_min=p.pause_min_ms, borne_max=p.pause_max_ms)


# ── Délais clavier (digraphes) ────────────────────────────────────────

# Catégories de paires de touches par difficulté (Card, Moran & Newell 1983)
# Les temps sont des médianes en ms pour un typiste ~60 WPM
_DIGRAPHE_MEME_DOIGT = 200  # même doigt, touche différente (lent)
_DIGRAPHE_ADJACENT = 120  # doigts adjacents (moyen)
_DIGRAPHE_OPPOSE = 90  # mains opposées (rapide)
_DIGRAPHE_REPETITION = 80  # même touche (très rapide)

# Mapping simplifié : doigt par touche (clavier QWERTY)
_DOIGT = {}
for _touches, _doigt_id in [
    ("qaz1", "L4"),
    ("wsx2", "L3"),
    ("edc3", "L2"),
    ("rfvtgb45", "L1"),
    ("yhnujm67", "R1"),
    ("ik8", "R2"),
    ("ol9", "R3"),
    ("p0", "R4"),
]:
    for _t in _touches:
        _DOIGT[_t] = _doigt_id

# Main par doigt
_MAIN = {d: d[0] for d in ["L4", "L3", "L2", "L1", "R1", "R2", "R3", "R4"]}


def _categorie_digraphe(a: str, b: str) -> float:
    """Médiane du délai inter-touche selon la catégorie biomécanique."""
    a_low, b_low = a.lower(), b.lower()

    if a_low == b_low:
        return _DIGRAPHE_REPETITION

    da = _DOIGT.get(a_low)
    db = _DOIGT.get(b_low)

    if da is None or db is None:
        return 130  # ponctuation, chiffres : valeur moyenne

    if da == db:
        return _DIGRAPHE_MEME_DOIGT

    if _MAIN[da] != _MAIN[db]:
        return _DIGRAPHE_OPPOSE

    # Même main, doigts différents
    dist = abs(int(da[1]) - int(db[1]))
    if dist == 1:
        return _DIGRAPHE_ADJACENT
    return (_DIGRAPHE_ADJACENT + _DIGRAPHE_OPPOSE) / 2


def delai_inter_touche(caractere: str, precedent: str | None = None, wpm: float = 62.0, fatigue: float = 0.0) -> float:
    """Délai avant une frappe (ms), distribution ex-gaussienne par digraphe.

    wpm : vitesse de frappe (mots par minute).
    fatigue : facteur cumulatif (0 = frais, 0.3 = fatigué).
    """
    # Médiane de base selon le digraphe
    if precedent:
        mediane = _categorie_digraphe(precedent, caractere)
    else:
        mediane = 150  # premier caractère

    # Ajuster au WPM cible (base = 60 WPM)
    facteur_vitesse = 60.0 / max(20, wpm)
    mediane *= facteur_vitesse

    # Fatigue (ralentissement progressif)
    mediane *= 1.0 + fatigue

    # Majuscule = appui Shift
    if caractere.isupper():
        mediane *= random.uniform(1.15, 1.40)

    # Chiffre et ponctuation
    if caractere.isdigit():
        mediane *= random.uniform(1.05, 1.25)
    elif not caractere.isalpha() and caractere != " ":
        mediane *= random.uniform(1.1, 1.4)

    # Ex-gaussienne : mu=médiane, sigma=15-25% de mu, tau=30-50% de mu
    sigma = mediane * random.uniform(0.15, 0.25)
    tau = mediane * random.uniform(0.30, 0.50)
    delai = ex_gaussienne(mediane, sigma, tau)

    # Pause entre mots (~8% de chance, distribution log-normale)
    if precedent == " " and random.random() < 0.08:
        delai += log_normale(350, 0.7, borne_min=100, borne_max=2000)

    return max(25, delai)


# ── Pauses page (lecture, navigation) ─────────────────────────────────


def pause_lecture_ms(mots_page: int = 200) -> float:
    """Temps de scan d'une page (ms). Log-normale basée sur le contenu.

    Un humain scan une page web à 200-400 WPM (titres, structure)
    et ne lit que 20-40% du contenu. Résultat : ~1s pour 50 mots,
    ~3s pour 200 mots, ~8s pour 500 mots.
    """
    fraction_lue = random.uniform(0.15, 0.35)
    mots_lus = max(5, mots_page * fraction_lue)
    wpm_scan = random.uniform(250, 400)
    base_ms = (mots_lus / wpm_scan) * 60_000
    base_ms = max(300, base_ms)
    plafond = min(15_000, base_ms * 2.0)
    return log_normale(base_ms, 0.3, borne_min=200, borne_max=plafond)


def pause_avant_action_ms() -> float:
    """Temps de réaction avant une action (ms). Ex-gaussienne."""
    return ex_gaussienne(180, 60, 80)


def pause_apres_navigation_ms() -> float:
    """Pause après chargement d'une page (ms). Log-normale."""
    return log_normale(600, 0.5, borne_min=200, borne_max=4000)


def pause_entre_pages_ms() -> float:
    """Délai entre deux navigations (ms). Log-normale à queue lourde."""
    return log_normale(1200, 0.7, borne_min=300, borne_max=12_000)


def pause_reflexion_ms() -> float:
    """Micro-pause de réflexion (ms). Log-normale."""
    return log_normale(200, 0.6, borne_min=50, borne_max=3000)


def pause_hesitation_ms(proba: float = 0.12) -> float:
    """Hésitation occasionnelle (ms). 0 si pas d'hésitation."""
    if random.random() >= proba:
        return 0
    return log_normale(1000, 0.6, borne_min=300, borne_max=5000)


# ── Auto-corrélation temporelle ───────────────────────────────────────


class RythmeHumain:
    """Maintient un état interne pour produire des séquences auto-corrélées.

    Un vrai humain ne tire pas des délais i.i.d. — il a un rythme
    qui dérive lentement (fatigue, accélération, distraction).
    Ce modèle ajoute une marche aléatoire multiplicative au-dessus
    des distributions de base.
    """

    def __init__(self, derive_sigma: float = 0.03):
        self._facteur = 1.0
        self._derive_sigma = derive_sigma

    def moduler(self, delai_ms: float) -> float:
        """Applique la dérive au délai et met à jour l'état."""
        self._facteur *= math.exp(random.gauss(0, self._derive_sigma))
        self._facteur = max(0.6, min(1.6, self._facteur))
        return delai_ms * self._facteur

    def reset(self) -> None:
        self._facteur = 1.0
