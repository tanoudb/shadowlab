"""Moteur `navigateur` de la récolte : `DriverNoezia` en identité native, derrière l'interface `Moteur` du parcours.

Ce que ce moteur est : le vrai Google Chrome, avec interface (`headless: false`, `channel: chrome`), sans aucun réglage
d'empreinte (`identite_native: true`), avec le comportement humain de NOEZIA (souris, défilement, pauses après chaque
page). Mesuré le 12/11 (campagne 100) : 179 passages sur 180 sur notre Arena dans cette configuration ; en identité
réécrite, le moteur fuit. Aucune autre configuration n'est proposée ici.

Ce qui est contrôlé, ce qui ne l'est pas (à lire avant de viser un site) :
- Chaque page demandée par le parcours passe par `Driver.verifier` (périmètre du labo) ET par la liste `hotes` de la
  recette : aucune adresse hors de ces hôtes n'est jamais demandée comme PAGE.
- Une redirection, elle, est suivie par Chrome lui-même (pas saut par saut comme en HTTP). Garde : le cadre principal
  ne peut demander que les hôtes de la recette (`DriverNoezia.hotes_navigation`), pour autant que `route` de Playwright
  intercepte ce saut (D-07 : il n'intercepte pas toujours les redirections). Dans tous les cas l'adresse d'arrivée
  est contrôlée ensuite par la sentinelle (hôte et motif), et la passe s'arrête. Un premier saut vers un hôte étranger a
  donc pu partir si le périmètre est illimité (`SHADOWLAB_HOTES_AUTORISES=*`) ; en périmètre strict, le verrou réseau le
  coupe.
- Les sous-ressources (images, feuilles de style, scripts, polices, CDN, mesures, widgets) sont chargées par Chrome
  comme pour n'importe quelle page : la règle « hôte de la recette » ne les couvre pas, et le périmètre du labo non plus
  s'il est illimité (défaut de la phase interne). Les bloquer changerait la page et l'empreinte (document § 3).
- `resoudre_defis` n'est actif que si TOUS les hôtes de la recette sont locaux (le labo) : sur un site tiers, il ne
  clique jamais sur un défi et ne résout rien. Là, la sentinelle attend (porte d'entrée) ou arrête.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any

from ...config import Reglages
from .moteur import DriverNoezia
from .parcours import MoteurDriver, RefusParcours
from .recettes import Recette, _est_local

NOM = "navigateur"
CHARGE_DE_LUI_MEME = (
    "sous-ressources de n'importe quel hôte (images, scripts, polices, CDN, widgets) : chargées par Chrome, "
    "hors de la règle « hôte de la recette » ; redirections : suivies par Chrome, garde du cadre principal "
    "sur les hôtes de la recette, adresse d'arrivée contrôlée par la sentinelle"
)


def options_navigateur(recette: Recette) -> dict[str, Any]:
    """Les options du moteur : identité native, comportement humain gardé, TLS et défis selon que le site est local."""
    local = all(_est_local(h) for h in recette.hotes)
    return {
        "headless": False,
        "channel": "chrome",
        "identite_native": True,
        "interaction_post_page": True,
        "verifier_tls": not local,  # un site qui n'est pas à nous : le certificat est vérifié
        "resoudre_defis": local,  # jamais de clic sur un défi d'un site tiers
    }


class MoteurNavigateur(MoteurDriver):
    def __init__(
        self,
        driver: DriverNoezia,
        hotes_recette: tuple[str, ...],
        *,
        empecher_veille: bool = True,
    ) -> None:
        super().__init__(driver, NOM)
        self.hotes_recette = tuple(hotes_recette)
        self._empecher_veille = empecher_veille
        self._veille: subprocess.Popen[bytes] | None = None
        driver.hotes_navigation = tuple(h.lower() for h in hotes_recette)

    @classmethod
    def depuis(cls, recette: Recette, reglages: Reglages, *, empecher_veille: bool = True) -> MoteurNavigateur:
        """Construit le moteur (aucun navigateur lancé) avec le périmètre du labo (`SHADOWLAB_HOTES_AUTORISES`)."""
        pilote = DriverNoezia(reglages.hotes_autorises, options_navigateur(recette))
        return cls(pilote, tuple(recette.hotes), empecher_veille=empecher_veille)

    def ouvrir(self) -> None:
        manque = DriverNoezia.manque()
        if manque:
            raise RefusParcours(f"moteur navigateur indisponible : {manque}")
        self._garder_le_mac_eveille()
        try:
            super().ouvrir()
        except BaseException:
            self._laisser_dormir()
            raise

    def fermer(self) -> None:
        try:
            super().fermer()
        finally:
            self._laisser_dormir()

    def _garder_le_mac_eveille(self) -> None:
        """Le Mac s'endort après 1 minute sans activité : `caffeinate` le tient éveillé tant que cette passe vit
        (il s'arrête seul avec le processus : `-w`). S'il manque, on continue (le document § 6 demande de le dire)."""
        if not self._empecher_veille:
            return
        if shutil.which("caffeinate") is None:
            print("ATTENTION : `caffeinate` introuvable, le Mac peut s'endormir pendant la passe.", flush=True)
            return
        self._veille = subprocess.Popen(  # noqa: S603 — commande fixe, aucun texte du site
            ["caffeinate", "-i", "-w", str(os.getpid())], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    def _laisser_dormir(self) -> None:
        if self._veille is not None:
            self._veille.terminate()
            self._veille = None

    def description(self) -> dict[str, Any]:
        description = super().description()
        description.update(
            {
                "options": dict(self.driver.options),
                "perimetre": list(self.driver.hotes_autorises),
                "hotes_recette": list(self.hotes_recette),
                "charge_de_lui_meme": CHARGE_DE_LUI_MEME,
            }
        )
        return description
