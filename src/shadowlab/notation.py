"""Notation d'une récolte contre la vérité d'un site de test : pages, enregistrements et champs.

Trois mesures distinctes, chacune à lire séparément :
- pages (`noter_pages`) : adresses attendues / adresses lues ;
- enregistrements (`noter_recolte`, « complétude ») : enregistrements attendus retrouvés par leur clé / attendus ;
- champs (`noter_recolte`, « exactitude ») : champs exacts / champs attendus, sur les enregistrements retrouvés.
Une page lue dont le tableau n'est lu qu'à moitié se voit donc dans les enregistrements, pas dans les champs.

Comparaison stricte, après suppression des espaces de début et de fin ; les nombres se comparent en nombres.
Une valeur attendue vide (`None`, chaîne vide ou d'espaces) est exacte quand rien n'est lu (absent, `None`, vide).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit

MAX_MANQUANTES = 20


def _nombre(valeur: Any) -> float | None:
    if isinstance(valeur, bool):
        return None
    if isinstance(valeur, int | float):
        return float(valeur)
    if isinstance(valeur, str):
        try:
            return float(valeur.strip())
        except ValueError:
            return None
    return None


def _vide(valeur: Any) -> bool:
    return valeur is None or (isinstance(valeur, str) and not valeur.strip())


def _egal(attendu: Any, obtenu: Any) -> bool:
    if _vide(attendu):
        return _vide(obtenu)  # rien d'attendu : exact si rien n'est lu, faux dès que quelque chose est lu
    if obtenu is None:
        return False
    if isinstance(attendu, int | float) and not isinstance(attendu, bool):
        n = _nombre(obtenu)
        return n is not None and n == attendu
    if isinstance(attendu, str):
        return isinstance(obtenu, str) and obtenu.strip() == attendu.strip()
    return obtenu == attendu


def _partie_de_cle(valeur: Any) -> str | None:
    """Une partie de clé sous forme comparable, sans jamais passer par un flottant.

    Un entier et son écriture exacte en texte (`7`, `"7"`, `" 7 "`) sont la même clé ; un `float` entier (`7.0`)
    aussi. Un texte à zéros en tête (`"007"`) reste un texte distinct de `7`. `"1e3"`, `"nan"` ou un grand entier
    ne sont que des textes ou des entiers exacts : aucune erreur, aucune fusion.
    """
    if _vide(valeur) or isinstance(valeur, bool):
        return None
    if isinstance(valeur, int):
        return str(valeur)
    if isinstance(valeur, float):
        return str(int(valeur)) if math.isfinite(valeur) and valeur == int(valeur) else repr(valeur)
    return valeur.strip() if isinstance(valeur, str) else None


def _cle_de(enregistrement: dict, champs: tuple[str, ...]) -> str | None:
    """Clé comparable d'un enregistrement, ou None si une partie manque."""
    parties: list[str] = []
    for champ in champs:
        partie = _partie_de_cle(enregistrement.get(champ))
        if partie is None:
            return None
        parties.append(partie)
    return "\x1f".join(parties)


def noter_recolte(
    recolte: list[dict],
    verite: dict,
    liste: str = "annonces",
    cle: str | Sequence[str] = "reference",
) -> dict[str, Any]:
    """Note les enregistrements récoltés contre `verite[liste]`, retrouvés par `cle`.

    `cle` est un nom de champ ou une suite de noms (clé composée, ex. `("rallye", "speciale", "numero")`).
    Les parties de clé se comparent sans espaces ; un entier et son écriture exacte en texte sont égaux, mais
    `"007"` reste distinct de `7` (voir `_partie_de_cle`). Un doublon
    ne compte qu'une fois ; un enregistrement à clé inconnue ou incomplète est « en trop ». Les clés attendues
    doivent être uniques. Les clés `annonces_*` gardent leur nom d'origine (appel historique de la vitrine) ;
    `enregistrements_*` en sont les noms généraux.

    `exactitude` vaut `None` quand aucun champ n'est comparé (rien retrouvé) : l'appelant doit le gérer avant de
    la comparer à un seuil.
    """
    champs_cle = (cle,) if isinstance(cle, str) else tuple(cle)
    if not champs_cle:
        raise ValueError("la clé est vide")
    if liste not in verite:
        raise ValueError(f"liste inconnue dans la vérité : {liste!r}")
    attendues: dict[str, dict] = {}
    for enregistrement in verite[liste]:
        k = _cle_de(enregistrement, champs_cle)
        if k is None:
            raise ValueError(f"enregistrement attendu sans clé complète {champs_cle} : {enregistrement}")
        if k in attendues:
            raise ValueError(f"clé attendue présente plusieurs fois dans {liste!r} : {k!r}")
        attendues[k] = enregistrement
    retrouvees: dict[str, dict] = {}
    en_trop: set[str] = set()
    for i, enregistrement in enumerate(recolte):
        k = _cle_de(enregistrement, champs_cle)
        if k in attendues:
            retrouvees.setdefault(k, enregistrement)  # un doublon ne compte qu'une fois
        else:
            en_trop.add(k.replace("\x1f", "/") if k else f"#{i}")
    champs_attendus = 0
    champs_exacts = 0
    erreurs: dict[str, int] = {}
    for k, enregistrement in retrouvees.items():
        for champ, attendu in attendues[k].items():
            champs_attendus += 1
            if _egal(attendu, enregistrement.get(champ)):
                champs_exacts += 1
            else:
                erreurs[champ] = erreurs.get(champ, 0) + 1
    manquantes = [
        attendues[k][champs_cle[0]] if len(champs_cle) == 1 else [attendues[k][c] for c in champs_cle]
        for k in attendues
        if k not in retrouvees
    ]
    return {
        "completude": len(retrouvees) / len(attendues) if attendues else 0.0,
        "exactitude": champs_exacts / champs_attendus if champs_attendus else None,
        "annonces_attendues": len(attendues),
        "annonces_retrouvees": len(retrouvees),
        "enregistrements_attendus": len(attendues),
        "enregistrements_retrouves": len(retrouvees),
        "champs_attendus": champs_attendus,
        "champs_exacts": champs_exacts,
        "references_manquantes": manquantes[:MAX_MANQUANTES],
        "annonces_en_trop": len(en_trop),
        "erreurs_par_champ": dict(sorted(erreurs.items())),
    }


def _adresse(adresse: str) -> str:
    """Chemin et paramètres d'une adresse, sans hôte, sans fragment, sans jeton de session `sl` ni `page=1`."""
    morceaux = urlsplit(adresse.strip())
    params = [
        (n, v) for n, v in parse_qsl(morceaux.query, keep_blank_values=True) if n != "sl" and (n, v) != ("page", "1")
    ]
    requete = urlencode(sorted(params))
    return f"{morceaux.path}?{requete}" if requete else morceaux.path


def noter_pages(attendues: Iterable[str], lues: Iterable[str]) -> dict[str, Any]:
    """Compare les adresses lues aux adresses attendues (hôte, fragment, jeton `sl` et `page=1` ignorés).

    Elle compare des adresses, pas des réponses : l'appelant ne doit lui passer que les pages réellement lues
    et conformes (pas une page de blocage, d'erreur ou de défi). Comme l'hôte est ignoré, une page lue sur un
    autre site de même chemin compte comme lue.
    """
    voulues = {_adresse(a): a for a in attendues}
    vues = {_adresse(a) for a in lues}
    trouvees = [a for a in voulues if a in vues]
    manquantes = [voulues[a] for a in voulues if a not in vues]
    return {
        "completude_pages": len(trouvees) / len(voulues) if voulues else 0.0,
        "pages_attendues": len(voulues),
        "pages_lues": len(trouvees),
        "pages_manquantes": manquantes[:MAX_MANQUANTES],
        "pages_en_trop": len([a for a in vues if a not in voulues]),
    }
