"""Résultat de fin de session du site public : quels niveaux de l'Arena auraient arrêté cette session.

Refait, avec le code du rejeu (`rejeu._rejouer_session`), la décision des sept niveaux 01 à 07 sur les
observations d'une session publique, puis ne garde que le verdict et les familles de raisons : jamais un nom de
détecteur, un signal, le jeton ni un chemin. Aucune règle n'est recopiée ici.

Le site public ne l'importe jamais : il le lance en sous-processus (`python -m shadowlab.resultat_public`, entrée
JSON `{"base": ..., "jeton": ...}` sur stdin, pour que le jeton ne figure pas dans la liste des processus).
La base est ouverte en lecture seule : rien n'y est écrit.

`SHADOWLAB_PROFILS_EXTRA` est retirée de l'environnement : elle ajoute ou remplace des niveaux (essais d'ablation),
et le résultat montré à un visiteur doit toujours être celui des niveaux officiels.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from . import rejeu
from .arena import profils
from .public import donnees

PAGES_MIN = 4  # pages avec empreinte ; en dessous, pas de verdict
EMPREINTES_MAX = 80  # au-delà, pas de calcul (coût environ quadratique)
NIVEAUX = ("01", "02", "03", "04", "05", "06", "07")  # jamais « endurance » ni un profil ajouté
FAMILLES = ("automatisation", "comportement", "incoherence", "retouche", "cumul", "piege")

_PAR_FAMILLE = {
    "automatisation": ("botd", "automation-globals", "cdp", "headless", "regles-js", "chrome-apis"),
    "comportement": ("comportement", "entropie-interaction", "scroll", "raf-timing"),
    "incoherence": (
        "coherence",
        "coherence-profonde",
        "coherence-environnement",
        "langues",
        "proxy-uadata",
        "regles-http",
        "media-codecs",
        "polices",
        "permissions-etendu",
        "position-fenetre",
        "css-media",
        "connection-dynamic",
        "webrtc",
        "worker-consistency",
        "iframe-consistency",
        "canvas-consistency",
        "tls",
        "h2",
        "correlation-session",
    ),  # fmt: skip
    "retouche": (
        "prototypes",
        "integrite-proprietes",
        "prototype-chain",
        "stack-trace",
        "stack-getter",
        "enumerable-props",
        "deep-proxy",
        "math-constants",
        "domrect",
        "audio-context",
        "canvas-empreinte",
        "timing-precision",
        "paint-timing",
    ),  # fmt: skip
    "cumul": ("composite",),
    "piege": ("honeypot",),
}
# Une entrée pour chaque détecteur, plus les deux motifs que la décision ajoute (`gardien.motifs_suspicion`).
FAMILLE_DE: dict[str, str] = {nom: famille for famille, noms in _PAR_FAMILLE.items() for nom in noms}


def _sans_verdict(raison: str, pages: int) -> dict:
    return {"jugeable": False, "raison": raison, "pages": pages, "pages_min": PAGES_MIN}


def calculer(chemin_base: Path, jeton: str) -> dict:
    """Verdict de la session `jeton` de la base publique `chemin_base`. N'écrit rien."""
    cx = rejeu.ouvrir_publique(Path(chemin_base))
    try:
        ligne = cx.execute(
            "SELECT r.session_token, r.status, r.protection, NULL AS monde_id FROM runs r"
            " JOIN experiments e ON e.id = r.experiment_id"
            " WHERE e.name = ? AND r.truth = 'humain' AND r.consent_at IS NOT NULL AND r.session_token = ?",
            (donnees.EXPERIENCE, jeton),
        ).fetchone()
        if ligne is None:
            return _sans_verdict("inconnue", 0)
        pages = cx.execute(
            "SELECT COUNT(*) FROM observations_js WHERE session_token = ? AND kind = 'empreinte'", (jeton,)
        ).fetchone()[0]
        if pages < PAGES_MIN:
            return _sans_verdict("courte", pages)
        if pages > EMPREINTES_MAX:
            return _sans_verdict("longue", pages)
        niveaux = profils.Profils({code: p for code, p in profils.charger() if code in NIVEAUX})
        session = rejeu._rejouer_session(cx, ligne, niveaux, publique=True)
    finally:
        cx.close()
    if session is None:
        return _sans_verdict("courte", pages)
    sortie = []
    for code in NIVEAUX:
        verdict = session["niveaux"][code]
        presentes = {FAMILLE_DE[m["detecteur"]] for m in verdict["motifs"]} if verdict["arretee"] else set()
        sortie.append({"code": code, "arrete": verdict["arretee"], "familles": [f for f in FAMILLES if f in presentes]})
    return {"jugeable": True, "pages": pages, "pages_min": PAGES_MIN, "niveaux": sortie}


def main() -> int:
    """0 : JSON sur stdout ; 2 : entrée illisible ; 1 : toute autre erreur. Rien sur stderr, jamais."""
    os.nice(10)
    os.environ.pop("SHADOWLAB_PROFILS_EXTRA", None)
    try:
        entree = json.loads(sys.stdin.read())
        base, jeton = entree["base"], entree["jeton"]
        if not (isinstance(base, str) and base and isinstance(jeton, str) and jeton):
            raise ValueError
    except Exception:
        return 2
    try:
        sortie = json.dumps(calculer(Path(base), jeton))
    except Exception:
        return 1
    sys.stdout.write(sortie)
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
