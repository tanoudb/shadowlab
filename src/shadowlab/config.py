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
    vitrine_graine: int  # graine du site vitrine (contenu connu)
    vitrine_taille: int  # nombre d'annonces du site vitrine
    rallye_graine: int  # graine du site de résultats de rallye (contenu connu)
    rallye_taille: int  # nombre de rallyes du site de résultats de rallye

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


@dataclass(frozen=True)
class ReglagesPublics:
    """Réglages de l'application publique (préfixe `SHADOWLAB_PUBLIC_`), indépendants du laboratoire.

    Les hôtes servis n'ont rien à voir avec le périmètre des moteurs (`SHADOWLAB_HOTES_AUTORISES`), et la
    base est un autre fichier que celle du laboratoire. Voir `docs/site-public.md`.
    """

    hotes: tuple[str, ...]  # noms acceptés dans l'en-tête Host
    contact: str  # responsable et moyen de le joindre, affiché sur la page d'information (obligatoire)
    conservation_jours: int  # durée de conservation d'une session
    https: bool  # cookies `Secure` et en-tête HSTS
    port: int  # écoute sur 127.0.0.1, derrière un mandataire HTTPS
    base_donnees: Path
    entete_ip: str  # en-tête où le mandataire met l'adresse du visiteur ("" = adresse de la connexion)
    vitrine_graine: int
    vitrine_taille: int
    social_graine: int = 20261113  # graine du réseau social fictif « Mosaïk Démo » (public/social.py)
    social_taille: int = 120  # nombre de publications du réseau social fictif
    sessions_par_jour: int = 40  # plafond de sessions ouvertes par jour UTC, toutes adresses (de 1 à 5 000)


def _charger_env(chemin: Path | None = None, acceptes: tuple[str, ...] | None = None) -> None:
    """Charge un fichier `.env` (KEY=VALUE) dans l'environnement s'il existe.

    Les secrets vivent dans `.env` (ignoré par git), jamais dans le code. Une variable déjà
    définie dans l'environnement a priorité (un `export` explicite l'emporte sur `.env`).

    `acceptes` limite ce qui entre dans l'environnement : un nom exact (`SHADOWLAB_SORTIES`) ou un préfixe suivi
    de `*` (`SHADOWLAB_PUBLIC_*`). Sans lui, tout le fichier est chargé (comportement du laboratoire).
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
        if cle and (acceptes is None or any(cle.startswith(a[:-1]) if a.endswith("*") else cle == a for a in acceptes)):
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
        vitrine_graine=int(os.environ.get("SHADOWLAB_VITRINE_GRAINE", "20261111")),
        vitrine_taille=max(1, int(os.environ.get("SHADOWLAB_VITRINE_TAILLE", "500"))),
        rallye_graine=int(os.environ.get("SHADOWLAB_RALLYE_GRAINE", "20261112")),
        rallye_taille=max(1, int(os.environ.get("SHADOWLAB_RALLYE_TAILLE", "24"))),
    )


def charger_public() -> ReglagesPublics:
    """Réglages de l'application publique. Le contact n'a pas de défaut : sans lui, elle refuse de démarrer.

    Elle ne charge de `.env` que les variables qu'elle lit elle-même : les clés propres au laboratoire
    (jeton d'API, clés reCAPTCHA…) n'entrent pas dans son processus, exposé sur Internet."""
    _charger_env(acceptes=("SHADOWLAB_PUBLIC_*", "SHADOWLAB_VITRINE_*", "SHADOWLAB_SORTIES"))
    sorties = Path(os.environ.get("SHADOWLAB_SORTIES", RACINE / "outputs"))
    hotes = os.environ.get("SHADOWLAB_PUBLIC_HOTES", "localhost,127.0.0.1")
    https = os.environ.get("SHADOWLAB_PUBLIC_HTTPS", "1").strip().lower()
    return ReglagesPublics(
        hotes=tuple(h.strip().lower() for h in hotes.split(",") if h.strip()),
        contact=os.environ.get("SHADOWLAB_PUBLIC_CONTACT", "").strip(),
        conservation_jours=int(os.environ.get("SHADOWLAB_PUBLIC_CONSERVATION_JOURS", "90")),
        https=https not in ("0", "non", "false", "no", "off"),  # toute autre valeur garde le mode sûr
        port=int(os.environ.get("SHADOWLAB_PUBLIC_PORT", "8771")),
        base_donnees=Path(os.environ.get("SHADOWLAB_PUBLIC_BASE", sorties / "public" / "public.sqlite3")),
        entete_ip=os.environ.get("SHADOWLAB_PUBLIC_ENTETE_IP", "X-Forwarded-For").strip(),
        vitrine_graine=int(os.environ.get("SHADOWLAB_VITRINE_GRAINE", "20261111")),
        vitrine_taille=max(1, int(os.environ.get("SHADOWLAB_VITRINE_TAILLE", "500"))),
        social_graine=int(os.environ.get("SHADOWLAB_PUBLIC_SOCIAL_GRAINE", "20261113")),
        social_taille=max(1, int(os.environ.get("SHADOWLAB_PUBLIC_SOCIAL_TAILLE", "120"))),
        # Borné : au moins une session par jour ; au plus 5 000 (la base de 2 Gio tient bien moins de sessions au
        # volume maximal, voir docs/site-public.md, « Limites »).
        sessions_par_jour=min(5000, max(1, int(os.environ.get("SHADOWLAB_PUBLIC_SESSIONS_PAR_JOUR", "40")))),
    )
