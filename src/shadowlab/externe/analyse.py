"""Pont d'analyse : un export de sessions d'un site externe, jugé par les détecteurs des niveaux de l'Arena.

Entrée : un fichier JSONL, une session par ligne, au format de `docs/collecte-externe.md` (« Une session »). Rien n'est
lu sur le réseau ni dans une base : l'export est fourni. Chaque ligne est d'abord contrôlée (clés exactes, formes,
bornes, aucune donnée de personne) ; une ligne hors contrat est refusée avec sa raison, jamais corrigée en silence.

La décision est celle de `shadowlab rejeu` : `rejeu.juger` (même code, mêmes moments, `gardien.motifs_suspicion`) puis
`rejeu.agreger` (mêmes chiffres, intervalle de Wilson). Un détecteur qui n'a pas ses données est écarté et compté
« non évalué », jamais deviné : TLS et HTTP/2 (hors du frontal), `regles-http` (le site ne transmet que quelques
en-têtes), `correlation-session` (pas d'historique de monde), `webrtc` (sonde sautée), `comportement` (aucun relevé).

Les traces (`kind: trace`, `public/trace.py`) sont vérifiées et comptées, mais aucun détecteur ne les lit encore.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .. import rejeu
from ..arena import profils as profils_arena
from ..detection import registre
from ..public import donnees, trace

FORMAT = 1
# Les chemins des pages sont rangés sous ce préfixe pour que `gardien.protegee` et les détecteurs les traitent comme
# les pages du site de test (ils ne reconnaissent une page que sous `/lab`). Le préfixe ne sort jamais du pont.
PREFIXE = "/lab/externe"
TAILLE_MAX_LIGNE = 8 * 1024 * 1024
MAX_PAGES = 5000

RACINE_REQUISE = ("format", "jeton", "debut", "user_agent", "pages", "empreintes")
RACINE_FACULTATIVE = ("entetes", "comportements", "traces", "contexte")
# En-têtes que le site peut transmettre en plus du User-Agent : jamais cookie, jamais d'adresse, jamais de renvoi.
ENTETES_PERMIS = ("accept-language", "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform")
CONTEXTE_PERMIS = ("compte", "chapitres")
CHAPITRE_PERMIS = ("serie", "chapitre", "instant")

JETON = re.compile(r"[A-Za-z0-9_-]{8,64}")
COMPTE = re.compile(r"u_[0-9a-f]{12,64}")  # identifiant masqué : un condensat, jamais un compte lisible
CHEMIN = re.compile(r"/[A-Za-z0-9._~%/@,+-]{0,198}")  # chemin seul : ni requête (?), ni ancre (#)
MOT = re.compile(r"[A-Za-z0-9._-]{1,60}")
COURRIEL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
IPV4 = re.compile(r"(?<![\d.])\d{1,3}(?:\.\d{1,3}){3}(?![\d.])")
IPV6 = re.compile(r"(?i)(?<![0-9a-f:])(?:[0-9a-f]{1,4}:){3,}[0-9a-f]{0,4}")

SANS_COMPORTEMENT = "aucun relevé de comportement reçu (l'envoi de sortie de page est parti, ou non)"
EN_TETES_PARTIELS = "le site externe ne transmet que le User-Agent et quelques en-têtes : règles HTTP non jugeables"
HISTORIQUE_EXTERNE = "le pont ne tient ni visites ni mondes : corrélation entre sessions non évaluée"
SANS_TLS = {
    "tls": "TLS non observé : session faite hors du frontal de l'Arena",
    "h2": "HTTP/2 non observé : session faite hors du frontal de l'Arena",
}
# Règles écartées (même mécanisme que `rejeu.REGLES_PUBLIC`) : le site externe ne relève pas les fichiers que ses pages
# chargent, donc « aucun fichier CSS ou JavaScript réclamé » serait faux pour tout le monde.
REGLES_ECARTEES = {
    "comportement": {"sans_ressources": "le site externe ne relève pas les fichiers chargés par ses pages"}
}
NOTE_TRACES = "vérifiées et comptées ; aucun détecteur de l'Arena ne lit encore les traces (relevé de gestes)"


@dataclass
class SessionExterne:
    """Une session lue, prête pour les détecteurs (formes de `database.observations`)."""

    jeton: str
    http: list[dict]
    js: list[dict]
    non_evalues: dict[str, str]
    traces: int
    comptes: int = 0
    chapitres: int = 0
    contexte: dict = field(default_factory=dict)


class Refus(ValueError):
    """Ligne hors contrat ; le message dit pourquoi."""


def _instant(valeur: object, nom: str) -> str:
    """Instant ISO 8601 avec fuseau, ramené en UTC à la milliseconde (la forme des observations de l'Arena)."""
    if not isinstance(valeur, str):
        raise Refus(f"{nom} : instant ISO 8601 avec fuseau attendu")
    try:
        instant = datetime.fromisoformat(valeur)
    except ValueError:
        raise Refus(f"{nom} : instant ISO 8601 avec fuseau attendu") from None
    if instant.tzinfo is None:
        raise Refus(f"{nom} : instant ISO 8601 avec fuseau attendu")
    return instant.astimezone(UTC).isoformat(timespec="milliseconds")


def _cles(objet: object, nom: str, requises: tuple[str, ...], facultatives: tuple[str, ...] = ()) -> dict:
    if not isinstance(objet, dict):
        raise Refus(f"{nom} : objet attendu")
    for cle in objet:
        if cle not in (*requises, *facultatives):
            raise Refus(f"clé inconnue : {nom + '.' if nom else ''}{cle}")
    for cle in requises:
        if cle not in objet:
            raise Refus(f"clé manquante : {nom + '.' if nom else ''}{cle}")
    return objet


def _chemin(valeur: object, nom: str) -> str:
    if not isinstance(valeur, str) or not CHEMIN.fullmatch(valeur):
        raise Refus(f"{nom} : chemin seul attendu (commence par /, sans ? ni #, 200 caractères au plus)")
    if COURRIEL.search(valeur) or IPV4.search(valeur):
        raise Refus(f"{nom} : donnée de personne probable dans le chemin")
    return valeur


def _messages(liste: object, nom: str, vide_permis: bool) -> list[tuple[str, str, dict]]:
    """Liste de { page, instant, payload } → (instant UTC, page, charge)."""
    if not isinstance(liste, list) or (not liste and not vide_permis) or len(liste) > MAX_PAGES:
        raise Refus(f"{nom} : liste attendue (au plus {MAX_PAGES})")
    sortie = []
    for i, element in enumerate(liste):
        _cles(element, f"{nom}[{i}]", ("page", "instant", "payload"))
        if not isinstance(element["payload"], dict):
            raise Refus(f"{nom}[{i}].payload : objet attendu")
        sortie.append(
            (
                _instant(element["instant"], f"{nom}[{i}].instant"),
                _chemin(element["page"], f"{nom}[{i}].page"),
                element["payload"],
            )
        )
    return sortie


def _contexte(brut: object) -> tuple[dict, int]:
    contexte = _cles(brut, "contexte", (), CONTEXTE_PERMIS)
    compte = contexte.get("compte")
    if compte is not None and not (isinstance(compte, str) and COMPTE.fullmatch(compte)):
        raise Refus("compte : identifiant masqué attendu (u_ puis 12 à 64 chiffres hexadécimaux), ou null")
    chapitres = contexte.get("chapitres", [])
    if not isinstance(chapitres, list) or len(chapitres) > MAX_PAGES:
        raise Refus("chapitres : liste attendue")
    for i, chapitre in enumerate(chapitres):
        _cles(chapitre, f"chapitres[{i}]", ("serie", "chapitre"), ("instant",))
        for cle in ("serie", "chapitre"):
            if not (isinstance(chapitre[cle], str | int) and MOT.fullmatch(str(chapitre[cle]))):
                raise Refus(f"chapitres[{i}].{cle} : identifiant court attendu (lettres, chiffres, . _ -)")
        if "instant" in chapitre:
            _instant(chapitre["instant"], f"chapitres[{i}].instant")
    texte = json.dumps(contexte, ensure_ascii=False)
    if COURRIEL.search(texte) or IPV4.search(texte) or IPV6.search(texte):
        raise Refus("contexte : donnée de personne probable (courriel ou adresse IP)")
    return contexte, 1 if compte else 0


def lire_session(brut: object) -> tuple[SessionExterne | None, str | None]:
    """(session, None) si la ligne respecte le contrat, (None, raison du refus) sinon. N'écrit rien."""
    try:
        return _lire(brut), None
    except Refus as refus:
        return None, str(refus)


def _lire(brut: object) -> SessionExterne:
    session = _cles(brut, "", RACINE_REQUISE, RACINE_FACULTATIVE)
    if session["format"] != FORMAT or type(session["format"]) is not int:
        raise Refus(f"format {session['format']!r} inconnu (attendu : {FORMAT})")
    jeton = session["jeton"]
    if not isinstance(jeton, str) or not JETON.fullmatch(jeton):
        raise Refus("jeton : opaque attendu (8 à 64 caractères : lettres, chiffres, _ -)")
    debut = _instant(session["debut"], "début")
    agent = session["user_agent"]
    if not isinstance(agent, str) or not agent or len(agent) > 512 or not agent.isprintable():
        raise Refus("user_agent : texte imprimable de 512 caractères au plus attendu")
    entetes = _cles(session.get("entetes", {}), "entetes", (), ENTETES_PERMIS)
    for nom, valeur in entetes.items():
        if not isinstance(valeur, str) or len(valeur) > 512 or not valeur.isprintable():
            raise Refus(f"entetes.{nom} : texte imprimable de 512 caractères au plus attendu")
    pages = session["pages"]
    if not isinstance(pages, list) or not pages or len(pages) > MAX_PAGES:
        raise Refus(f"pages : liste d'au moins une page attendue (au plus {MAX_PAGES})")
    paires = [["user-agent", agent], *[[nom, valeur] for nom, valeur in entetes.items()]]
    http = []
    for i, page in enumerate(pages):
        _cles(page, f"pages[{i}]", ("instant", "chemin"))
        http.append(
            {
                "received_at": _instant(page["instant"], f"pages[{i}].instant"),
                "method": "GET",
                "path": PREFIXE + _chemin(page["chemin"], f"pages[{i}].chemin"),
                "http_version": "unknown",
                "headers": paires,
                "cookies": {},
            }
        )
    empreinte = sorted(_messages(session["empreintes"], "empreintes", False), key=lambda m: m[0])
    comportements = _messages(session.get("comportements", []), "comportements", True)
    envois = _messages(session.get("traces", []), "traces", True)
    for i, (_, _, charge) in enumerate(envois):
        if trace.valider(charge) is None:
            raise Refus(f"traces[{i}] : trace invalide (public/trace.py : clés exactes, entiers, bornes)")
    contexte, comptes = _contexte(session.get("contexte", {}))
    js = [
        {"received_at": instant, "kind": kind, "page": PREFIXE + page, "payload": charge}
        for kind, groupe in (("empreinte", empreinte), ("comportement", comportements))
        for instant, page, charge in groupe
    ]
    js.sort(key=lambda o: o["received_at"])
    http.sort(key=lambda o: o["received_at"])
    # Les extensions de navigateur désignent une personne : masquées à la lecture, comme le site public à l'écriture.
    js = json.loads(donnees.masquer_extensions(json.dumps(js, ensure_ascii=False)))
    non_evalues = {"correlation-session": HISTORIQUE_EXTERNE, "regles-http": EN_TETES_PARTIELS, **SANS_TLS}
    if (empreinte[0][2].get("webrtc_test") or {}).get("saute"):
        non_evalues["webrtc"] = rejeu.SONDE_SAUTEE
    if not comportements:
        non_evalues["comportement"] = SANS_COMPORTEMENT
    return SessionExterne(
        jeton=jeton,
        http=http,
        js=js,
        non_evalues=non_evalues,
        traces=len(envois),
        comptes=comptes,
        chapitres=len(contexte.get("chapitres", [])),
        contexte={"debut": debut},
    )


def lire_export(chemin: Path) -> tuple[list[SessionExterne], list[dict]]:
    """Sessions valides et lignes refusées (numéro de ligne, raison) d'un export JSONL."""
    if not chemin.is_file():
        raise ValueError(f"{chemin} : fichier introuvable")
    sessions: list[SessionExterne] = []
    refusees: list[dict] = []
    vus: set[str] = set()
    with chemin.open("rb") as f:
        for numero, ligne in enumerate(f, start=1):
            if not ligne.strip():
                continue
            if len(ligne) > TAILLE_MAX_LIGNE:
                refusees.append({"ligne": numero, "raison": "ligne trop longue"})
                continue
            try:
                brut = json.loads(ligne)
            except ValueError:
                refusees.append({"ligne": numero, "raison": "JSON illisible"})
                continue
            session, raison = lire_session(brut)
            if session is not None and session.jeton in vus:
                session, raison = None, "jeton déjà vu dans cet export"
            if session is None:
                refusees.append({"ligne": numero, "raison": raison})
            else:
                vus.add(session.jeton)
                sessions.append(session)
    return sessions, refusees


def _niveaux(codes: list[str] | None) -> profils_arena.Profils:
    tous = profils_arena.charger()
    if not codes:
        return tous
    choisis = {}
    for code in codes:
        profil = tous.de(code)
        if profil is None:
            raise ValueError(f"niveau inconnu : {code} (niveaux : {', '.join(tous.codes)})")
        choisis[profils_arena.normaliser(code)] = profil
    return profils_arena.Profils(choisis)


def analyser(sessions: list[SessionExterne], refusees: list[dict], codes: list[str] | None = None) -> dict:
    """Même forme que `rejeu.rejouer`, pour les sessions de l'export ; n'écrit rien."""
    niveaux = _niveaux(codes)
    tous = registre()
    for nom, regles in REGLES_ECARTEES.items():
        tous[nom] = rejeu._SansRegles(tous[nom], frozenset(regles))
    detail = []
    for s in sessions:
        verdicts = rejeu.juger(s.http, s.js, None, [], niveaux, True, tous, s.non_evalues)
        detail.append(
            {
                "jeton": s.jeton,
                "statut": "externe",
                "protection": None,
                "niveaux": verdicts,
                "non_evalues": s.non_evalues,
                "pieges_servis": False,
                "regles_ecartees": REGLES_ECARTEES,
                "correlation_historique": None,
            }
        )
    return {
        "base": "externe",
        "sessions": {"total": len(sessions) + len(refusees), "rejouees": len(detail), "refusees": len(refusees)},
        "refusees": refusees,
        "traces": {"recues": sum(s.traces for s in sessions), "note": NOTE_TRACES},
        "comptes_masques": sum(s.comptes for s in sessions),
        "niveaux": [rejeu.agreger(code, profil, detail) for code, profil in niveaux.items()],
        "detail": detail,
    }
