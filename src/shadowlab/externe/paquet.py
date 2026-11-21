"""Paquet « observateur externe » : les deux scripts d'observation, sans marque, à point d'envoi réglable.

Un site qui n'est pas le nôtre (cas visé : un site d'Ethan avec de vraies sessions humaines consenties) charge ces
deux fichiers et les fait poster vers SA route, par une balise de sa page :

    <meta name="sl-session" content="<jeton opaque>">
    <meta name="sl-collecte" content="/chemin/de/sa/route">   (chemin de la même origine ; sinon `/lab/collecte`)
    <meta name="sl-sans-tiers" content="1">                   (pas de sonde WebRTC vers un serveur STUN extérieur)

- `observateur.js` : la copie sans marque de `site/static/observateur.js` (`public/script_public.py`, mêmes
  remplacements que le site public, D-81), dont l'adresse d'envoi lit `sl-collecte`. Le script du labo ne change pas.
- `vendor/botd-2.0.0.esm.js` (+ licence) : importé par `observateur.js`, à servir à côté de lui ; la page le charge en
  `<script type="module">`.
- `releve.js` : le relevé de comportement du site public, tel quel (il lit `sl-collecte` lui-même).

Aucune adresse de site réel n'est écrite ici : le paquet est neutre. Garde : s'il reste un nom interdit
(`script_public.NOMS_INTERDITS`) ou si un remplacement ne trouve pas son compte, rien n'est écrit.
Contrat des données : `docs/collecte-externe.md`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..public import script_public
from ..public.trace import VERSION as VERSION_TRACE

DOSSIER_LABO = Path(__file__).resolve().parents[1] / "site" / "static"
DOSSIER_PUBLIC = Path(__file__).resolve().parents[1] / "public" / "static"

# Point d'envoi de l'observateur : même règle que `releve.js` (chemin de la même origine, jamais un autre hôte).
ADRESSE_EN_DUR = "  const url = `/lab/collecte?sl=${encodeURIComponent(jeton)}`;\n"
ADRESSE_REGLABLE = (
    "  const declare = document.querySelector('meta[name=\"sl-collecte\"]')?.content || '';\n"
    "  const base = /^\\/(?![\\/\\\\])[^\\s]*$/.test(declare) ? declare : '/lab/collecte';\n"
    "  const url = `${base}${base.includes('?') ? '&' : '?'}sl=${encodeURIComponent(jeton)}`;\n"
)
REMPLACEMENTS_OBSERVATEUR: list[tuple[str, str, int]] = [
    *script_public.REMPLACEMENTS_OBSERVATEUR,
    (ADRESSE_EN_DUR, ADRESSE_REGLABLE, 1),
]


# Bibliothèque tierce importée par `observateur.js` (BotD, MIT) et sa licence. FingerprintJS n'est pas du paquet : le
# script ne le charge que sur deux pages du labo (`PAGES_FPJS`), jamais sur un site externe (`fpjs` y vaut `null`).
VENDOR = ("vendor/botd-2.0.0.esm.js", "vendor/botd-LICENSE.txt")


def fabriquer(dossier: Path) -> dict[str, str]:
    """Écrit les scripts, BotD (`vendor/`) et `manifeste.json` dans `dossier` ; rend le SHA-256 de chaque fichier."""
    observateur = script_public.fabriquer_copie(
        "observateur.js", (DOSSIER_LABO / "observateur.js").read_text("utf-8"), REMPLACEMENTS_OBSERVATEUR
    )
    contenus = {
        "observateur.js": observateur.encode("utf-8"),
        "releve.js": (DOSSIER_PUBLIC / "releve.js").read_bytes(),
        # `observateur.js` l'importe (`./vendor/…`, page chargée en `type="module"`) : à servir à côté de lui.
        **{nom: (DOSSIER_LABO / nom).read_bytes() for nom in VENDOR},
    }
    for nom, brut in contenus.items():
        reste = script_public.noms_trouves(brut)
        if reste:
            raise script_public.ScriptPublicInvalide(f"{nom} : nom interdit dans le paquet externe : {reste}")
    empreintes = {nom: hashlib.sha256(brut).hexdigest() for nom, brut in contenus.items()}
    dossier.mkdir(parents=True, exist_ok=True)
    for nom, brut in contenus.items():
        (dossier / nom).parent.mkdir(parents=True, exist_ok=True)
        (dossier / nom).write_bytes(brut)
    manifeste = {
        "fichiers": empreintes,
        "point_d_envoi": "meta[name=sl-collecte]",
        "jeton": "meta[name=sl-session]",
        "sans_tiers": "meta[name=sl-sans-tiers]",
        "version_trace": VERSION_TRACE,
        "contrat": "docs/collecte-externe.md",
    }
    (dossier / "manifeste.json").write_text(json.dumps(manifeste, indent=2) + "\n", encoding="utf-8")
    return empreintes
