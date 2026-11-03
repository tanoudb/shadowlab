"""Mesure de la consommation CPU et mémoire pendant un passage.

On suit l'arbre de processus du lanceur (lui-même et tous ses descendants : pilote Playwright,
navigateur, moteurs de rendu). Limites connues : un processus né puis mort entre deux relevés échappe
à la mesure ; la mémoire d'un navigateur partagé entre passages compte dans chaque passage.
"""

from __future__ import annotations

import os
import threading
import time

import psutil

INTERVALLE_S = 0.1

# Processus à ne pas compter (le site de test lancé à part par la campagne) et leurs descendants.
PIDS_EXCLUS: set[int] = set()


class Echantillonneur:
    def __init__(self, memoire_max_mo: float | None = None) -> None:
        self.memoire_max_mo = memoire_max_mo
        self.depassement = False
        self._arret = threading.Event()
        self._rss: list[float] = []
        self._cpu: dict[int, float] = {}
        self._cpu_initial: dict[int, float] = {}
        self._racine = psutil.Process(os.getpid())

    def _processus(self) -> list[psutil.Process]:
        exclus = set(PIDS_EXCLUS)
        for pid in PIDS_EXCLUS:
            try:
                exclus.update(p.pid for p in psutil.Process(pid).children(recursive=True))
            except psutil.Error:
                continue
        try:
            enfants = self._racine.children(recursive=True)
        except psutil.Error:
            enfants = []
        return [self._racine, *(p for p in enfants if p.pid not in exclus)]

    def _releve(self) -> None:
        total = 0.0
        for proc in self._processus():
            try:
                total += proc.memory_info().rss
                temps = proc.cpu_times()
                self._cpu[proc.pid] = temps.user + temps.system
            except psutil.Error:
                continue
        mo = total / 1024 / 1024
        self._rss.append(mo)
        if self.memoire_max_mo and mo > self.memoire_max_mo:
            self.depassement = True

    def _boucle(self) -> None:
        while not self._arret.wait(INTERVALLE_S):
            self._releve()

    def __enter__(self) -> Echantillonneur:
        self._releve()
        self._cpu_initial = dict(self._cpu)
        self._debut = time.perf_counter()
        self._fil = threading.Thread(target=self._boucle, daemon=True)
        self._fil.start()
        return self

    def __exit__(self, *args) -> None:
        self._arret.set()
        self._fil.join()
        self._releve()
        self.duree_s = time.perf_counter() - self._debut

    def resultat(self) -> dict[str, float]:
        cpu_s = sum(t - self._cpu_initial.get(pid, 0.0) for pid, t in self._cpu.items())
        return {
            # pourcentage moyen d'un cœur sur la durée du passage
            "cpu_usage": round(100 * cpu_s / self.duree_s, 1) if self.duree_s > 0 else 0.0,
            "cpu_time_ms": round(cpu_s * 1000, 1),
            "memory_usage": round(max(self._rss), 1),
            "memory_mean": round(sum(self._rss) / len(self._rss), 1),
        }
