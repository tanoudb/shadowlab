"""Résultat de fin de session : appel du calcul du laboratoire en sous-processus, contrôle de sa sortie, cache.

Ce module n'importe rien du laboratoire : le calcul (`shadowlab.resultat_public`) se lance par `python -m`, reçoit
`{"base": ..., "jeton": ...}` sur son entrée standard (le jeton ne figure donc jamais dans la liste des processus) et
rend un JSON, vérifié ici clé par clé avant d'être montré. Aucun jeton dans un journal ni dans un message d'erreur.

Le résultat n'est jamais écrit : il reste en mémoire quelques minutes (échecs compris, sinon chaque rechargement
relancerait un calcul), et `Resultats.oublier` l'efface à la suppression de la session.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from pathlib import Path

journal = logging.getLogger("shadowlab.public")

PAGES_MIN = 4  # même valeur que le calcul du laboratoire (un test le vérifie)
ATTENTE_S = 4.0  # attente à « Terminer » et à « Ma session » avant la page « calcul en cours »
DELAI_MAX_S = 30.0  # au-delà, le sous-processus est tué : résultat indisponible
DUREE_CACHE_S = 15 * 60  # en mémoire seulement
DUREE_ECHEC_S = 120  # un échec reste en cache moins longtemps (calcul tué sous la charge : on réessaie vite)
TAILLE_CACHE = 1000
TAILLE_SORTIE_MAX = 64 * 1024
VERSION_MIN = ("2026-11-17", 1)  # première version de notice qui annonce le résultat (« AAAA-MM-JJ.N »)
EN_COURS = object()  # `Resultats.obtenir` : le calcul n'est pas fini

NIVEAUX = ("01", "02", "03", "04", "05", "06", "07")
FAMILLES = ("automatisation", "comportement", "incoherence", "retouche", "cumul", "piege")
RAISONS = ("inconnue", "courte", "longue")
VERSION = re.compile(r"(\d{4}-\d{2}-\d{2})\.(\d{1,6})")


def annonce_resultat(version: str | None) -> bool:
    """Vrai si la notice acceptée annonce le résultat. Le numéro après le point se compare comme un entier."""
    correspondance = VERSION.fullmatch(version) if isinstance(version, str) else None
    return correspondance is not None and (correspondance[1], int(correspondance[2])) >= VERSION_MIN


def _entier(valeur: object) -> bool:
    return isinstance(valeur, int) and not isinstance(valeur, bool) and valeur >= 0


def _niveau_valide(niveau: object, code: str) -> bool:
    if not isinstance(niveau, dict) or set(niveau) != {"code", "arrete", "familles"} or niveau["code"] != code:
        return False
    familles = niveau["familles"]
    if not isinstance(niveau["arrete"], bool) or not isinstance(familles, list):
        return False
    if not all(isinstance(f, str) and f in FAMILLES for f in familles):
        return False
    return bool(familles) is False or niveau["arrete"]  # des raisons seulement pour un niveau arrêté


def valider(sortie: object) -> dict | None:
    """La sortie du calcul si elle a exactement la forme du contrat (clés, niveaux, familles connues), sinon None."""
    if not isinstance(sortie, dict):
        return None
    if sortie.get("jugeable") is False:
        if set(sortie) != {"jugeable", "raison", "pages", "pages_min"}:
            return None
        bon = sortie["raison"] in RAISONS and _entier(sortie["pages"]) and _entier(sortie["pages_min"])
        return sortie if bon else None
    if sortie.get("jugeable") is not True or set(sortie) != {"jugeable", "pages", "pages_min", "niveaux"}:
        return None
    niveaux = sortie["niveaux"]
    if not (_entier(sortie["pages"]) and _entier(sortie["pages_min"]) and isinstance(niveaux, list)):
        return None
    if len(niveaux) != len(NIVEAUX) or not all(_niveau_valide(n, c) for n, c in zip(niveaux, NIVEAUX, strict=True)):
        return None
    return sortie


async def _echanger(processus: asyncio.subprocess.Process, entree: bytes) -> bytes | None:
    """Envoie l'entrée, lit la sortie (64 Kio au plus) ; None si le code de sortie n'est pas 0 ou sortie trop grosse."""
    try:
        processus.stdin.write(entree)
        await processus.stdin.drain()
        processus.stdin.close()
    except (BrokenPipeError, ConnectionResetError):
        pass  # le calcul a fini ou échoué sans lire : son code de sortie le dira
    morceaux: list[bytes] = []
    total = 0
    while bloc := await processus.stdout.read(8192):
        total += len(bloc)
        if total > TAILLE_SORTIE_MAX:
            return None
        morceaux.append(bloc)
    return b"".join(morceaux) if await processus.wait() == 0 else None


async def calculer_par_processus(base: Path, jeton: str) -> dict | None:
    """Lance le calcul du laboratoire en sous-processus. None : échec, délai dépassé (tué) ou sortie invalide."""
    environnement = {cle: valeur for cle, valeur in os.environ.items() if cle != "SHADOWLAB_PROFILS_EXTRA"}
    entree = json.dumps({"base": str(base), "jeton": jeton}).encode()
    try:
        processus = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "shadowlab.resultat_public",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=environnement,
        )
    except OSError as erreur:
        journal.warning("Résultat : le calcul n'a pas pu démarrer (%s)", type(erreur).__name__)
        return None
    try:
        sortie = await asyncio.wait_for(_echanger(processus, entree), DELAI_MAX_S)
    except TimeoutError:
        journal.warning("Résultat : calcul interrompu après %s s", DELAI_MAX_S)
        return None
    finally:
        if processus.returncode is None:
            processus.kill()
            await processus.wait()
    if sortie is None:
        journal.warning("Résultat : le calcul a échoué")
        return None
    try:
        return valider(json.loads(sortie))
    except (ValueError, RecursionError):
        journal.warning("Résultat : sortie du calcul illisible")
        return None


class Resultats:
    """Cache borné des résultats, un calcul à la fois pour tout le site et un seul en vol par jeton.

    `obtenir` attend au plus `attente` secondes (`ATTENTE_S` lue à l'appel si elle n'est pas donnée) : au-delà il
    rend `EN_COURS` et le calcul continue, pour que la page suivante le trouve fait. Un échec (None) est
    gardé aussi, mais `duree_echec` secondes seulement."""

    def __init__(
        self,
        calculer: Callable[[Path, str], Awaitable[dict | None]],
        *,
        attente: float | None = None,
        duree: float = DUREE_CACHE_S,
        duree_echec: float = DUREE_ECHEC_S,
        taille: int = TAILLE_CACHE,
    ) -> None:
        self._calculer, self._attente, self._duree, self._duree_echec, self._taille = (
            calculer,
            attente,
            duree,
            duree_echec,
            taille,
        )
        self._cache: OrderedDict[str, tuple[float, dict | None]] = OrderedDict()
        self._en_vol: dict[str, asyncio.Task] = {}
        self._oublies: set[str] = set()
        self._boucle: asyncio.AbstractEventLoop | None = None
        self._un_a_la_fois = asyncio.Semaphore(1)

    def _verrou(self) -> asyncio.Semaphore:
        boucle = asyncio.get_running_loop()
        if boucle is not self._boucle:  # une autre boucle d'événements (essais) : un verrou neuf
            self._boucle, self._un_a_la_fois = boucle, asyncio.Semaphore(1)
        return self._un_a_la_fois

    async def _lancer(self, base: Path, jeton: str) -> dict | None:
        sortie: dict | None = None
        try:
            async with self._verrou():
                try:
                    sortie = await self._calculer(base, jeton)
                except Exception as erreur:  # noqa: BLE001 - jamais de message : il pourrait contenir le jeton
                    journal.warning("Résultat : calcul en erreur (%s)", type(erreur).__name__)
        finally:
            self._en_vol.pop(jeton, None)
        if jeton in self._oublies:  # session supprimée pendant le calcul : rien ne reste
            self._oublies.discard(jeton)
        else:
            self._cache[jeton] = (time.monotonic(), sortie)
            while len(self._cache) > self._taille:
                self._cache.popitem(last=False)
        return sortie

    async def obtenir(self, base: Path, jeton: str) -> dict | None | object:
        entree = self._cache.get(jeton)
        if entree is not None:
            if time.monotonic() - entree[0] < (self._duree if entree[1] is not None else self._duree_echec):
                self._cache.move_to_end(jeton)
                return entree[1]
            del self._cache[jeton]
        boucle = asyncio.get_running_loop()
        tache = self._en_vol.get(jeton)
        if tache is None or tache.get_loop() is not boucle:
            tache = self._en_vol[jeton] = boucle.create_task(self._lancer(base, jeton))
        attente = ATTENTE_S if self._attente is None else self._attente
        try:
            return await asyncio.wait_for(asyncio.shield(tache), attente)
        except TimeoutError:
            return EN_COURS

    def oublier(self, jeton: str) -> None:
        """Efface le résultat d'une session supprimée, et empêche un calcul en vol de le remettre."""
        self._cache.pop(jeton, None)
        if jeton in self._en_vol:
            self._oublies.add(jeton)
