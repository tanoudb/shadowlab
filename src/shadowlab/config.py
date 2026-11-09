"""Réglages du laboratoire, lus dans l'environnement (préfixe `SHADOWLAB_`)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Reglages:
    base_donnees: Path
    sorties: Path
    hote: str
    port: int
    hotes_autorises: tuple[str, ...]
    jeton_api: str | None
    memoire_max_mo: int
    concurrence_max: int
    port_arena: int  # frontal TLS, point d'entrée de l'Arena
    port_aval: int  # Nginx, publié par la pile Docker de l'Arena

    @property
    def url_site(self) -> str:
        hote = f"[{self.hote}]" if ":" in self.hote else self.hote
        return f"http://{hote}:{self.port}"

    @property
    def url_arena(self) -> str:
        # `localhost` et non 127.0.0.1 : un navigateur envoie alors un SNI, comme vers un vrai site.
        return f"https://localhost:{self.port_arena}"

    @property
    def dossier_arena(self) -> Path:
        return self.sorties / "arena"


def _charger_env(chemin: Path | None = None) -> None:
    """Charge un fichier `.env` (KEY=VALUE) dans l'environnement s'il existe.

    Les secrets vivent dans `.env` (ignoré par git), jamais dans le code. Une variable déjà
    définie dans l'environnement a priorité (un `export` explicite l'emporte sur `.env`).
    """
    fichier = chemin or (RACINE / ".env")
    try:
        contenu = fichier.read_text(encoding="utf-8")
    except OSError:
        return
    for brut in contenu.splitlines():
        ligne = brut.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, _, valeur = ligne.partition("=")
        cle = cle.strip().removeprefix("export ").strip()
        valeur = valeur.strip().strip('"').strip("'")
        if cle:
            os.environ.setdefault(cle, valeur)


def charger() -> Reglages:
    """Construit les réglages ; chaque valeur a un défaut sûr (local, sans jeton)."""
    _charger_env()
    sorties = Path(os.environ.get("SHADOWLAB_SORTIES", RACINE / "outputs"))
    # Phase interne/expérimentale : périmètre illimité par défaut (``*``). Durcissement final =
    # fixer SHADOWLAB_HOTES_AUTORISES à une liste explicite (voir docs/securite-a-finaliser.md).
    hotes = os.environ.get("SHADOWLAB_HOTES_AUTORISES", "*")
    return Reglages(
        base_donnees=Path(os.environ.get("SHADOWLAB_BASE", sorties / "shadowlab.sqlite3")),
        sorties=sorties,
        hote=os.environ.get("SHADOWLAB_HOTE", "127.0.0.1"),
        port=int(os.environ.get("SHADOWLAB_PORT", "8770")),
        hotes_autorises=tuple(h.strip().lower() for h in hotes.split(",") if h.strip()),
        jeton_api=os.environ.get("SHADOWLAB_JETON") or None,
        memoire_max_mo=int(os.environ.get("SHADOWLAB_MEMOIRE_MAX_MO", "4096")),
        concurrence_max=int(os.environ.get("SHADOWLAB_CONCURRENCE_MAX", "4")),
        port_arena=int(os.environ.get("SHADOWLAB_PORT_ARENA", "8743")),
        port_aval=int(os.environ.get("SHADOWLAB_PORT_AVAL", "8781")),
    )
