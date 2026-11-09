"""Récolte parallèle : scraper beaucoup d'URLs vite, à débit contrôlé.

Chaque worker est un **moteur NOEZIA isolé** (son propre navigateur), réutilisé sur son lot d'URLs
pour amortir le démarrage. La parallélisation se fait par **processus** (isolation totale : pas de
problème de thread-safety avec le navigateur, un ban/crash sur une URL n'affecte pas les autres).

Sans toucher au moteur mono-page : c'est une couche de débit par-dessus.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from typing import Any


def repartir(urls: list[str], n: int) -> list[list[str]]:
    """Répartit les URLs en n lots d'à peu près même taille (lots vides écartés)."""
    n = max(1, min(n, len(urls))) if urls else 1
    lots: list[list[str]] = [[] for _ in range(n)]
    for i, url in enumerate(urls):
        lots[i % n].append(url)
    return [lot for lot in lots if lot]


def _traiter_lot(
    lot: list[str], selecteur: str | None, options: dict[str, Any], hotes: tuple[str, ...]
) -> list[dict[str, Any]]:
    """Un moteur isolé traite son lot d'URLs. Exécuté dans un processus worker."""
    from .moteur import DriverNoezia

    moteur = DriverNoezia(hotes, dict(options))
    resultats: list[dict[str, Any]] = []
    try:
        moteur.open()
        for url in lot:
            moteur.start_session()
            try:
                rn = moteur.navigate(url)
                textes = moteur.texts(selecteur) if selecteur else None
                resultats.append({"url": url, "status": rn.status, "textes": textes})
            except Exception as exc:  # noqa: BLE001 — une URL qui échoue ne casse pas le lot
                resultats.append({"url": url, "erreur": str(exc)[:200]})
            finally:
                moteur.close_session()
    finally:
        moteur.close()
    return resultats


def recolter(
    urls: list[str],
    selecteur: str | None = None,
    concurrence: int = 4,
    options: dict[str, Any] | None = None,
    hotes: tuple[str, ...] = ("*",),
) -> list[dict[str, Any]]:
    """Scrape les URLs en parallèle (débit = `concurrence` moteurs isolés).

    Retourne une liste de `{url, status, textes}` (ou `{url, erreur}`), dans l'ordre d'arrivée des lots.
    `selecteur` : si fourni, les `textContent` correspondants sont relevés par page.
    """
    if not urls:
        return []
    lots = repartir(urls, concurrence)
    options = options or {}
    sorties: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=len(lots)) as pool:
        futurs = [pool.submit(_traiter_lot, lot, selecteur, options, tuple(hotes)) for lot in lots]
        for futur in futurs:
            sorties.extend(futur.result())
    return sorties
