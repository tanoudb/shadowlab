"""Simulation de frappe clavier humaine.

Modélise les caractéristiques d'un typiste réel :
- Vitesse variable (distribution gaussienne des intervalles inter-touches)
- Fatigue progressive (ralentissement sur les longs textes)
- Micro-erreurs avec correction immédiate (backspace + retype)
- Pauses de réflexion entre les mots
- Bursts : les séquences familières sont tapées plus vite
"""

from __future__ import annotations

import random
import time

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
        wpm_moyen: float = 65.0,
        wpm_ecart: float = 12.0,
        proba_erreur: float = 0.02,
        fatigue_par_caractere: float = 0.0003,
    ):
        self._page = page
        self._wpm = wpm_moyen
        self._wpm_ecart = wpm_ecart
        self._proba_erreur = proba_erreur
        self._fatigue = fatigue_par_caractere
        self._caracteres_tapes = 0
        self._rng = random.Random()

    def _delai_base_ms(self) -> float:
        """Intervalle moyen entre deux frappes (ms), basé sur le WPM courant."""
        wpm_actuel = max(20, self._rng.gauss(self._wpm, self._wpm_ecart))
        # 1 mot = 5 caractères en moyenne
        return 60_000.0 / (wpm_actuel * 5.0)

    def _delai_caractere(self, c: str, precedent: str | None) -> float:
        """Délai avant de taper ce caractère, en ms."""
        base = self._delai_base_ms()

        # Fatigue : ralentissement progressif
        facteur_fatigue = 1.0 + self._fatigue * self._caracteres_tapes

        # Les espaces et la ponctuation sont légèrement plus lents
        if c in " \t":
            base *= self._rng.uniform(1.1, 1.4)
        elif c in ".,;:!?":
            base *= self._rng.uniform(1.0, 1.3)

        # Les majuscules sont plus lentes (Shift)
        if c.isupper():
            base *= self._rng.uniform(1.15, 1.35)

        # Les chiffres sont un peu plus lents
        if c.isdigit():
            base *= self._rng.uniform(1.05, 1.2)

        # Répétition de la même touche : plus rapide
        if precedent and c == precedent:
            base *= self._rng.uniform(0.7, 0.85)

        # Variation gaussienne
        delai = max(25, base * facteur_fatigue + self._rng.gauss(0, base * 0.2))

        # Pause occasionnelle entre les mots (réflexion)
        if precedent == " " and self._rng.random() < 0.08:
            delai += self._rng.uniform(150, 600)

        return delai

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
            # Décider si on fait une erreur
            if (
                self._rng.random() < self._proba_erreur
                and c.isalpha()
                and i < len(texte) - 1  # pas d'erreur sur le dernier caractère
            ):
                erreur = self._erreur_voisine(c)
                if erreur:
                    # Taper le mauvais caractère
                    delai_ms = self._delai_caractere(erreur, precedent)
                    time.sleep(delai_ms / 1000.0)
                    self._page.keyboard.type(erreur, delay=0)
                    self._caracteres_tapes += 1

                    # Pause de réalisation
                    time.sleep(self._rng.uniform(0.08, 0.25))

                    # Corriger avec backspace
                    self._page.keyboard.press("Backspace")
                    time.sleep(self._rng.uniform(0.03, 0.08))

            # Taper le bon caractère
            delai_ms = self._delai_caractere(c, precedent)
            time.sleep(delai_ms / 1000.0)
            self._page.keyboard.type(c, delay=0)
            self._caracteres_tapes += 1
            precedent = c

    def taper_dans(self, selector: str, texte: str) -> None:
        """Focus sur un champ, le vide, puis tape le texte."""
        self._page.click(selector)
        time.sleep(self._rng.uniform(0.05, 0.15))
        self._page.keyboard.press("ControlOrMeta+a")
        time.sleep(self._rng.uniform(0.02, 0.06))
        self._page.keyboard.press("Backspace")
        time.sleep(self._rng.uniform(0.05, 0.12))
        self.taper(texte)
