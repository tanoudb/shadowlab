"""Pool de sessions NOEZIA parallèles.

Gère N instances du moteur avec des profils différents, chacune dans
son propre thread. Chaque session est indépendante (navigateur, profil,
cookies, fingerprint) — aucune corrélation possible entre elles.

Usage :
    from shadowlab.engines.noezia.pool import PoolNoezia

    with PoolNoezia(hotes_autorises=("127.0.0.1",), taille=4) as pool:
        resultats = pool.executer_parallele(urls)
        # resultats = [{"url": ..., "contenu": ..., "session": ...}, ...]
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable

from .moteur import MoteurNoezia

log = logging.getLogger(__name__)


@dataclass
class ResultatSession:
    url: str
    contenu: str | None = None
    status: int = 0
    duree_ms: float = 0
    profil: str = ""
    erreur: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class PoolNoezia:
    """Pool de moteurs NOEZIA parallèles.

    Chaque worker a son propre navigateur Chromium avec un profil unique.
    Les sessions sont recyclées : un worker peut traiter plusieurs URLs
    séquentiellement avant que son navigateur soit fermé et recréé avec
    un nouveau profil (rotation).
    """

    def __init__(
        self,
        hotes_autorises: tuple[str, ...],
        taille: int = 4,
        options: dict[str, Any] | None = None,
        urls_par_profil: int = 10,
    ):
        self._hotes = hotes_autorises
        self._taille = taille
        self._options = options or {}
        self._urls_par_profil = urls_par_profil
        self._moteurs: list[MoteurNoezia] = []
        self._executor: ThreadPoolExecutor | None = None

    def __enter__(self) -> PoolNoezia:
        self.demarrer()
        return self

    def __exit__(self, *args: Any) -> None:
        self.arreter()

    def demarrer(self) -> None:
        log.info("Démarrage du pool NOEZIA (%d workers)", self._taille)
        self._executor = ThreadPoolExecutor(max_workers=self._taille)
        for i in range(self._taille):
            moteur = MoteurNoezia(self._hotes, {**self._options})
            moteur.open()
            self._moteurs.append(moteur)
            log.info("Worker %d prêt (profil=%s)", i, moteur._profil.nom if moteur._profil else "?")

    def arreter(self) -> None:
        for m in self._moteurs:
            try:
                m.close()
            except Exception:
                pass
        self._moteurs.clear()
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None
        log.info("Pool NOEZIA arrêté")

    def _traiter_url(self, moteur: MoteurNoezia, url: str) -> ResultatSession:
        t0 = time.monotonic()
        profil_nom = moteur._profil.nom if moteur._profil else ""
        try:
            moteur.start_session()
            reponse = moteur.aller(url)
            contenu = moteur.contenu()
            moteur.close_session()
            duree = (time.monotonic() - t0) * 1000
            return ResultatSession(
                url=url,
                contenu=contenu,
                status=reponse.status if reponse else 0,
                duree_ms=duree,
                profil=profil_nom,
            )
        except Exception as e:
            try:
                moteur.close_session()
            except Exception:
                pass
            return ResultatSession(
                url=url,
                duree_ms=(time.monotonic() - t0) * 1000,
                profil=profil_nom,
                erreur=str(e),
            )

    def executer_parallele(self, urls: list[str]) -> list[ResultatSession]:
        """Exécute les URLs en parallèle sur les workers du pool.

        Chaque worker traite ses URLs séquentiellement avec le même profil.
        Les URLs sont distribuées round-robin.
        """
        if not self._executor or not self._moteurs:
            raise RuntimeError("Pool non démarré (utiliser demarrer() ou with)")

        # Distribution round-robin
        taches_par_worker: list[list[str]] = [[] for _ in self._moteurs]
        for i, url in enumerate(urls):
            taches_par_worker[i % len(self._moteurs)].append(url)

        futures = {}
        for idx, (moteur, urls_worker) in enumerate(zip(self._moteurs, taches_par_worker)):
            if urls_worker:
                future = self._executor.submit(self._worker_batch, moteur, urls_worker)
                futures[future] = idx

        resultats: list[ResultatSession] = []
        for future in as_completed(futures):
            try:
                batch = future.result()
                resultats.extend(batch)
            except Exception as e:
                log.error("Worker %d en erreur : %s", futures[future], e)

        return resultats

    def _worker_batch(self, moteur: MoteurNoezia, urls: list[str]) -> list[ResultatSession]:
        """Un worker traite une liste d'URLs séquentiellement."""
        resultats = []
        compteur = 0
        for url in urls:
            if compteur >= self._urls_par_profil:
                self._rotation_profil(moteur)
                compteur = 0
            resultats.append(self._traiter_url(moteur, url))
            compteur += 1
        return resultats

    def _rotation_profil(self, moteur: MoteurNoezia) -> None:
        """Ferme et relance le moteur avec un nouveau profil."""
        ancien = moteur._profil.nom if moteur._profil else "?"
        moteur.close()
        moteur.open()
        nouveau = moteur._profil.nom if moteur._profil else "?"
        log.info("Rotation profil : %s → %s", ancien, nouveau)

    def executer_avec_callback(
        self,
        urls: list[str],
        callback: Callable[[ResultatSession], None],
    ) -> None:
        """Exécute les URLs en parallèle, appelle le callback pour chaque résultat."""
        if not self._executor or not self._moteurs:
            raise RuntimeError("Pool non démarré")

        taches_par_worker: list[list[str]] = [[] for _ in self._moteurs]
        for i, url in enumerate(urls):
            taches_par_worker[i % len(self._moteurs)].append(url)

        futures = {}
        for idx, (moteur, urls_worker) in enumerate(zip(self._moteurs, taches_par_worker)):
            for url in urls_worker:
                future = self._executor.submit(self._traiter_url, moteur, url)
                futures[future] = idx

        for future in as_completed(futures):
            try:
                resultat = future.result()
                callback(resultat)
            except Exception as e:
                log.error("Erreur callback worker %d : %s", futures[future], e)
