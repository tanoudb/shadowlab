"""Fichiers du laboratoire servis par l'application publique, sans le nom du projet ni celui du laboratoire.

Le site public ne laisse voir ces noms nulle part, code source des scripts compris (demande d'Ethan, 14/11/2026).
`site/static/observateur.js` ne change pourtant pas d'un octet : il sert aux mesures du laboratoire, et le texte
dessiné sur le canvas entre dans une empreinte comparée d'une campagne à l'autre. L'application publique en sert donc
une copie, fabriquée au démarrage par une liste de remplacements exacts, chacun avec le nombre d'occurrences attendu.

Garde : si un remplacement ne trouve pas son compte, ou s'il reste un nom interdit dans un fichier servi, l'application
refuse de démarrer. Une modification future du script du laboratoire ne peut pas remettre le nom en ligne en silence.

Effets connus de la copie :
- le canvas porte un autre texte, donc son hachage diffère de celui du laboratoire ;
- la sonde `noezia_enumerable` et le nom `__NOEZIA_PROFIL__` n'existent plus. Pour un humain ils étaient toujours
  vides ; `detection.DetecteurAutomationGlobals` lit une clé absente comme une liste vide, donc `shadowlab rejeu`
  donne le même verdict. Aucune clé de premier niveau ne change : la notice reste exacte.
"""

from __future__ import annotations

from pathlib import Path

NOMS_INTERDITS = ("noezia", "shadowlab", "shadow lab")

# (texte exact, remplacement, nombre d'occurrences attendu) dans `observateur.js`.
REMPLACEMENTS_OBSERVATEUR: list[tuple[str, str, int]] = [
    ("ctx.fillText('ShadowLab ✓ 2026', 6, 10);", "ctx.fillText('Canvas ✓ 2026', 6, 10);", 1),
    ("window.__shadowlab = empreinte;", "window.__etude = empreinte;", 1),
    ("new CustomEvent('shadowlab:empreinte'", "new CustomEvent('etude:empreinte'", 1),
    ("new Event('shadowlab:collecte-finie')", "new Event('etude:collecte-finie')", 1),
    ("'__NOEZIA_PROFIL__', ", "", 1),
    (
        "  // Noms NOEZIA visibles dans Object.keys ?\n  try {\n"
        "    const noezia = Object.keys(window).filter(k => k.includes('NOEZIA'));\n"
        "    r.noezia_enumerable = noezia;\n  } catch (_) { /* ignore */ }\n",
        "",
        1,
    ),
]


class ScriptPublicInvalide(RuntimeError):
    """Un fichier servi par le site public ne peut pas être rendu sans le nom du projet."""


def noms_trouves(contenu: bytes | str) -> list[str]:
    bas = (contenu.decode("utf-8", "replace") if isinstance(contenu, bytes) else contenu).lower()
    return [nom for nom in NOMS_INTERDITS if nom in bas]


def fabriquer_copie(nom: str, source: str, remplacements: list[tuple[str, str, int]]) -> str:
    for ancien, nouveau, attendu in remplacements:
        trouve = source.count(ancien)
        if trouve != attendu:
            raise ScriptPublicInvalide(
                f"{nom} : le remplacement de {ancien!r} trouve {trouve} occurrence(s), {attendu} attendue(s) ; "
                "le script du laboratoire a changé, la liste de `public/script_public.py` est à revoir."
            )
        source = source.replace(ancien, nouveau)
    return source


def preparer(dossier: Path, fichiers: dict[str, str]) -> dict[str, bytes]:
    """Contenu servi de chaque fichier de `fichiers` (chemin → type de média) : `observateur.js` remplacé, les autres
    tels quels. Refuse s'il reste un nom interdit dans l'un d'eux."""
    prets: dict[str, bytes] = {}
    for chemin in fichiers:
        brut = (dossier / chemin).read_bytes()
        if chemin == "observateur.js":
            brut = fabriquer_copie(chemin, brut.decode("utf-8"), REMPLACEMENTS_OBSERVATEUR).encode("utf-8")
        reste = noms_trouves(brut)
        if reste:
            raise ScriptPublicInvalide(f"{chemin} : nom interdit dans le fichier servi par le site public : {reste}")
        prets[chemin] = brut
    return prets
