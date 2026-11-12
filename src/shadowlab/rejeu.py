"""Rejeu des sessions humaines contre les niveaux de l'Arena (étape 1.7 du plan).

Pour chaque session humaine consentie et chaque niveau, refait la décision de l'Arena avec son propre code
(`gardien.motifs_suspicion` et les réglages `gardien.parametres`), aux mêmes moments qu'elle : à la réception
de chaque empreinte, à chaque page contrôlée, puis sur la session entière. Lecture seule sur la base rejouée.

Un détecteur qui n'a pas ses données pour une session est écarté de son rejeu et compté « non évalué » : il ne
fait ni passer ni tomber personne en silence. De même pour une règle qui lit une donnée que le site public ne
garde pas.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import analytics, correlation, passages
from . import database as db
from .arena import profils as profils_arena
from .detection import Classement, Detecteur, Observations, _verdict, registre
from .public import donnees
from .site import gardien

DELAI_INACTIVITE_S = 600  # sans observation depuis 10 minutes, la personne a fermé l'onglet sans « Terminer »

SANS_FRONTAL = {
    "tls": "TLS non observé : session faite hors du frontal de l'Arena",
    "h2": "HTTP/2 non observé : session faite hors du frontal de l'Arena",
}
HISTORIQUE = "dépend de l'historique de la base (table empreintes_vues), pas de la session"
HISTORIQUE_PUBLIC = "le site public ne tient pas la table empreintes_vues"
SONDE_SAUTEE = "sonde WebRTC sautée par la page (site sans tiers)"
PIEGES_NON_SERVIS = "pièges non servis pendant la session (enregistrée à un niveau sans honeypots)"
# Règles qui lisent ce que le site public ne garde pas (public/donnees.py) : écartées de ses sessions.
REGLES_PUBLIC = {
    "regles-http": {
        "cookies_ignores": "cookies non stockés par le site public",
        "host_tardif": "ordre des en-têtes et version HTTP réécrits par le mandataire HTTPS",
    },
}


class _SansRegles:
    """Le détecteur moins les règles écartées : leurs signaux sont retirés, puis le verdict est refait avec le
    calcul du détecteur (`detection._verdict`, celui de `regles-http`)."""

    def __init__(self, detecteur: Detecteur, codes: frozenset[str]) -> None:
        self.detecteur, self.codes = detecteur, codes
        self.name, self.version = detecteur.name, detecteur.version

    def classer(self, obs: Observations) -> Classement:
        c = self.detecteur.classer(obs)
        gardes = [s for s in c.signals if s.code not in self.codes]
        return c if len(gardes) == len(c.signals) else _verdict(c.detector_name, c.detector_version, gardes)


def ouvrir_publique(chemin: Path) -> sqlite3.Connection:
    """Base du site public en lecture seule. Refuse un fichier absent ou une base qui n'est pas publique."""
    if not chemin.is_file():
        raise ValueError(f"{chemin} : fichier introuvable")
    cx = sqlite3.connect(f"{chemin.resolve().as_uri()}?mode=ro", uri=True)
    cx.row_factory = sqlite3.Row
    try:
        donnees.verifier_base(cx, chemin)
    except ValueError:
        cx.close()
        raise
    return cx


def clore_inactives(cx: sqlite3.Connection, delai_s: int = DELAI_INACTIVITE_S) -> int:
    """Finalise comme « Terminer » (/manuel/terminer) les sessions manuelles en cours restées sans activité.

    Dernière activité : l'observation HTTP ou JavaScript la plus récente, ou le début de la session. Base du labo
    seulement : la base publique n'est jamais écrite par le rejeu.
    """
    limite = (datetime.now(UTC) - timedelta(seconds=delai_s)).isoformat(timespec="milliseconds")
    lignes = cx.execute(
        "SELECT r.id, r.session_token FROM runs r JOIN experiments e ON e.id = r.experiment_id"
        " WHERE e.name = ? AND r.truth = 'humain' AND r.status = 'en_cours' AND MAX(r.started_at,"
        " COALESCE((SELECT MAX(received_at) FROM observations_http WHERE session_token = r.session_token), ''),"
        " COALESCE((SELECT MAX(received_at) FROM observations_js WHERE session_token = r.session_token), '')) < ?",
        (passages.EXPERIENCE_MANUELLE, limite),
    ).fetchall()
    for ligne in lignes:
        passages.finaliser(cx, ligne["id"], ligne["session_token"], status="reussi", success=True, duration_ms=None)
    return len(lignes)


def rejouer(cx: sqlite3.Connection, publique: bool = False, niveaux: profils_arena.Profils | None = None) -> dict:
    """Rejoue les sessions humaines consenties de la base contre chaque niveau. N'écrit rien."""
    niveaux = niveaux or profils_arena.charger()
    experience = donnees.EXPERIENCE if publique else passages.EXPERIENCE_MANUELLE
    lignes = cx.execute(
        "SELECT r.session_token, r.status, r.protection FROM runs r JOIN experiments e ON e.id = r.experiment_id"
        " WHERE e.name = ? AND r.truth = 'humain' AND r.consent_at IS NOT NULL ORDER BY r.id",
        (experience,),
    ).fetchall()
    detail, inutilisables = [], []
    for ligne in lignes:
        session = _rejouer_session(cx, ligne, niveaux, publique)
        if session is None:
            inutilisables.append(ligne["session_token"])
        else:
            detail.append(session)
    return {
        "base": "publique" if publique else "labo",
        "experience": experience,
        "sessions": {"total": len(lignes), "rejouees": len(detail), "inutilisables": len(inutilisables)},
        "inutilisables": inutilisables,
        "niveaux": [_agreger(code, profil, detail) for code, profil in niveaux.items()],
        "detail": detail,
    }


def _moments(http: list[dict], js: list[dict]) -> Iterator[tuple[dict, int, int]]:
    """Instants où l'Arena décide, avec le nombre d'observations HTTP et JS déjà arrivées à cet instant.

    Une empreinte reçue (/lab/collecte), une page contrôlée (`gardien.protegee`), puis la session entière.
    À horodatage égal, la requête passe avant le message : une page est demandée avant que son script ne parle.
    """
    i = j = 0
    while i < len(http) or j < len(js):
        if j == len(js) or (i < len(http) and http[i]["received_at"] <= js[j]["received_at"]):
            requete = http[i]
            i += 1
            if gardien.protegee(requete["path"], requete["method"]):
                yield {"type": "page", "chemin": requete["path"], "instant": requete["received_at"]}, i, j
        else:
            message = js[j]
            j += 1
            if message["kind"] == "empreinte":
                yield {"type": "empreinte", "chemin": message["page"], "instant": message["received_at"]}, i, j
    yield {"type": "fin", "chemin": "", "instant": None}, len(http), len(js)


def _non_evalues(tls: dict | None, empreinte: dict, publique: bool) -> dict[str, str]:
    """Détecteurs qui n'ont pas leurs données pour cette session, avec la raison."""
    raisons = {"correlation-session": HISTORIQUE_PUBLIC if publique else HISTORIQUE}
    if tls is None:
        raisons |= SANS_FRONTAL
    if (empreinte.get("webrtc_test") or {}).get("saute"):
        raisons["webrtc"] = SONDE_SAUTEE
    return raisons


def _historique(cx: sqlite3.Connection, observations: Observations) -> bool:
    """`correlation-session` lu avec l'état actuel de la table empreintes_vues (lecture seule) : à titre
    d'information, car ce verdict dépend des sessions passées et futures de la base, pas de celle-ci."""
    observations.correlation = correlation.correlation_session(cx, observations.empreinte_js)
    return registre()["correlation-session"].classer(observations).classification == "automatise"


def _rejouer_session(
    cx: sqlite3.Connection, ligne: sqlite3.Row, niveaux: profils_arena.Profils, publique: bool
) -> dict | None:
    """Verdict de chaque niveau pour une session ; None si elle n'a envoyé aucune empreinte (inutilisable)."""
    jeton = ligne["session_token"]
    http, js = db.observations(cx, jeton)
    if not any(o["kind"] == "empreinte" for o in js):
        return None
    tls = db.tls_session(cx, jeton)
    pieges = [
        d["created_at"]
        for d in db.decisions_session(cx, jeton)
        if d["couche"] == "honeypot" and d["decision"] == "declenche"
    ]
    enregistree = niveaux.de(ligne["protection"])
    ecartees = REGLES_PUBLIC if publique else {}
    tous = registre()
    for nom, regles in ecartees.items():
        tous[nom] = _SansRegles(tous[nom], frozenset(regles))
    non_evalues = _non_evalues(tls, Observations(http=http, js=js).empreinte_js, publique)
    verdicts = {code: {"arretee": False, "moment": None, "motifs": [], "classes": {}} for code, _ in niveaux.items()}
    actifs = [(code, profil) for code, profil in niveaux.items() if profil.fingerprinting.actif]
    for moment, nb_http, nb_js in _moments(http, js):
        observations = Observations(http=http[:nb_http], js=js[:nb_js], tls=tls)
        nb_pieges = sum(1 for instant in pieges if moment["instant"] is None or instant <= moment["instant"])
        for code, profil in actifs:
            parametres = gardien.parametres(profil)
            parametres["exclure"] = [*(parametres["exclure"] or []), *non_evalues]
            # Un piège n'existe qu'aux niveaux qui en servent : ailleurs, la personne n'aurait rien pu déclencher.
            servis = nb_pieges if profil.honeypots.actif else 0
            motifs = gardien.motifs_suspicion(observations, servis, tous=tous, **parametres)
            verdict = verdicts[code]
            for motif in motifs:
                codes = verdict["classes"].setdefault(motif["detecteur"], [])
                codes += [s["code"] for s in motif["signaux"] if s["code"] not in codes]
            if motifs and profil.fingerprinting.bloquer != "non" and not verdict["arretee"]:
                verdict.update(arretee=True, moment=moment, motifs=motifs)
    return {
        "jeton": jeton,
        "statut": ligne["status"],
        "protection": ligne["protection"],
        "niveaux": verdicts,
        "non_evalues": non_evalues,
        "pieges_servis": bool(enregistree and enregistree.honeypots.actif),
        "regles_ecartees": ecartees,
        "correlation_historique": None if publique else _historique(cx, Observations(http=http, js=js, tls=tls)),
    }


def _tri(compteur: Counter) -> list[tuple[str, int]]:
    return sorted(compteur.items(), key=lambda e: (-e[1], e[0]))


def _agreger(code: str, profil: profils_arena.Profil, sessions: list[dict]) -> dict:
    """Chiffres d'un niveau : sessions arrêtées (intervalle de Wilson) et sessions classées par détecteur."""
    f = profil.fingerprinting
    consultes = set(f.detecteurs or [*gardien.REGLES_REQUETE, *gardien.REGLES_JAVASCRIPT]) if f.actif else set()
    verdicts = [s["niveaux"][code] for s in sessions]
    arretees = sum(v["arretee"] for v in verdicts)
    classes: Counter = Counter()
    signaux: dict[str, Counter] = {}
    for v in verdicts:
        for detecteur, codes in v["classes"].items():
            classes[detecteur] += 1
            signaux.setdefault(detecteur, Counter()).update(codes)
    manquants: Counter = Counter()
    ecartees: Counter = Counter()
    raisons: dict = {}
    for s in sessions:
        for nom, raison in s["non_evalues"].items():
            if nom in consultes:
                manquants[nom] += 1
                raisons[nom] = raison
        if f.actif and profil.honeypots.actif and not s["pieges_servis"]:
            manquants["honeypot"] += 1
            raisons["honeypot"] = PIEGES_NON_SERVIS
        for nom, regles in s["regles_ecartees"].items():
            for regle, raison in regles.items():
                if nom in consultes:
                    ecartees[(nom, regle)] += 1
                    raisons[(nom, regle)] = raison
    historique = None
    if "correlation-session" in consultes and all(s["correlation_historique"] is not None for s in sessions):
        historique = {"sessions": sum(s["correlation_historique"] for s in sessions), "sur": len(sessions)}
    return {
        "niveau": code,
        "nom": profil.nom,
        "consulte": f.actif,
        "bloque": f.actif and f.bloquer != "non",
        "rejouees": len(verdicts),
        "arretees": arretees,
        "passees": len(verdicts) - arretees,
        "taux_arret": analytics.wilson(arretees, len(verdicts)),
        "classes": [
            {"detecteur": d, "sessions": n, "signaux": [{"code": c, "sessions": k} for c, k in _tri(signaux[d])]}
            for d, n in _tri(classes)
        ],
        "non_evalues": [{"detecteur": d, "raison": raisons[d], "sessions": n} for d, n in _tri(manquants)],
        "regles_ecartees": [
            {"detecteur": d, "regle": r, "raison": raisons[(d, r)], "sessions": n}
            for (d, r), n in sorted(ecartees.items())
        ],
        "correlation_historique": historique,
    }
