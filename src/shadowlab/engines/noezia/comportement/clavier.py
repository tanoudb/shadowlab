"""Simulation de frappe clavier humaine.

Utilise le modèle de digraphes (délai inter-touche dépendant de la paire
de caractères) avec distribution ex-gaussienne et auto-corrélation.
Résiste à tout test statistique sur les inter-key intervals.

Références :
- Card, Moran & Newell (1983). The Psychology of Human-Computer Interaction.
- Salthouse (1984). The skill of typing.
"""

from __future__ import annotations

import random
import time

from . import humain

# Touches adjacentes sur un clavier QWERTY pour les erreurs de frappe
VOISINES: dict[str, str] = {
    "a": "sqzw",
    "b": "vghn",
    "c": "xdfv",
    "d": "sfcxer",
    "e": "rdwsf",
    "f": "dgcvrt",
    "g": "fhbvty",
    "h": "gjbnyu",
    "i": "ujko",
    "j": "hknmui",
    "k": "jlmio",
    "l": "kop",
    "m": "njk",
    "n": "bhjm",
    "o": "iklp",
    "p": "ol",
    "q": "wa",
    "r": "etdf",
    "s": "awedxz",
    "t": "rfgy",
    "u": "yhji",
    "v": "cfgb",
    "w": "qase",
    "x": "zsdc",
    "y": "tghu",
    "z": "asx",
}


class SimulateurClavier:
    """Simule une frappe humaine réaliste sur une page Playwright/Patchright."""

    def __init__(
        self,
        page,
        wpm_moyen: float = 62.0,
        proba_erreur: float = 0.02,
        fatigue_par_caractere: float = 0.0003,
    ):
        self._page = page
        self._wpm = wpm_moyen
        self._proba_erreur = proba_erreur
        self._fatigue_coeff = fatigue_par_caractere
        self._caracteres_tapes = 0
        self._rng = random.Random()
        self._rythme = humain.RythmeHumain(derive_sigma=0.02)

    def _delai_caractere(self, c: str, precedent: str | None) -> float:
        """Délai avant de taper ce caractère (ms), modèle digraphe + ex-gaussienne."""
        fatigue = self._fatigue_coeff * self._caracteres_tapes
        delai = humain.delai_inter_touche(c, precedent, self._wpm, fatigue)
        return self._rythme.moduler(delai)

    def _erreur_voisine(self, c: str) -> str | None:
        """Retourne un caractère voisin pour simuler une erreur de frappe."""
        voisins = VOISINES.get(c.lower())
        if not voisins:
            return None
        return self._rng.choice(voisins)

    def taper(self, texte: str) -> None:
        """Tape le texte caractère par caractère avec un rythme humain."""
        precedent: str | None = None

        for i, c in enumerate(texte):
            if self._rng.random() < self._proba_erreur and c.isalpha() and i < len(texte) - 1:
                erreur = self._erreur_voisine(c)
                if erreur:
                    delai_ms = self._delai_caractere(erreur, precedent)
                    time.sleep(delai_ms / 1000.0)
                    self._page.keyboard.type(erreur, delay=0)
                    self._caracteres_tapes += 1
                    # Pause de réalisation (ex-gaussienne)
                    time.sleep(humain.ex_gaussienne(120, 40, 60) / 1000.0)
                    self._page.keyboard.press("Backspace")
                    time.sleep(humain.ex_gaussienne(50, 15, 20) / 1000.0)

            delai_ms = self._delai_caractere(c, precedent)
            time.sleep(delai_ms / 1000.0)
            self._page.keyboard.type(c, delay=0)
            self._caracteres_tapes += 1
            precedent = c

    def taper_dans(self, selector: str, texte: str) -> None:
        """Focus sur un champ, le vide, puis tape le texte."""
        self._page.click(selector)
        time.sleep(humain.pause_avant_action_ms() / 1000.0)
        self._page.keyboard.press("ControlOrMeta+a")
        time.sleep(humain.ex_gaussienne(40, 10, 15) / 1000.0)
        self._page.keyboard.press("Backspace")
        time.sleep(humain.ex_gaussienne(70, 20, 30) / 1000.0)
        self.taper(texte)
