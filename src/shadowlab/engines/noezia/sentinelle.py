"""Sentinelle : arrêt au premier signe d'alerte.

Signes retenus (§ 5 du document de conception) :
1. statut 401, 403, 407, 429 ou 503 ; un 403 sur une ressource de la page (photo, appel de données) du même hôte
   compte aussi (`examiner_ressources`), sauf si son corps est un défi (`detecter_defi_ressource`) : c'est alors le
   signe 2 ;
2. page de défi : `body[data-arena]` (Arena) ; en-tête `cf-mitigated: challenge`, formulaire de défi ou cadre de
   Cloudflare ; cadre reCAPTCHA, hCaptcha ou Turnstile (`detecter_defi`) ;
3. adresse finale hors des hôtes de la recette, ou hors du motif `url` du type de page attendu ;
4. sélecteur `requis` absent sur 3 pages de suite d'un même type ;
5. plus de 5 échecs (réseau, 500, 502, 504) sur les 20 dernières pages ;
6. (identité, `parcours.py`) le défi de la porte d'entrée revenu avant la durée déclarée : `porte_revenue`.
La porte d'entrée (attente sans action d'un défi qui se valide seul, sur la première page) est dans `parcours.py` :
elle utilise `detecter_defi`. Un défi plus tard dans la passe est une alerte, sauf si la recette permet de repasser la
porte (`porte_entree.repassages_max`, borné, même attente sans action, `parcours.py`). Aucun clic, aucune résolution.

La sentinelle ne fait aucune requête et ne décide que d'une chose : y a-t-il une alerte ? Le parcours s'arrête alors,
sans aucun nouvel essai (réessayer aggrave).
"""

from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import NamedTuple
from urllib.parse import urlsplit

STATUTS_ALERTE = frozenset({401, 403, 407, 429, 503})
FENETRE = 20
ECHECS_MAX = 5
NON_CONFORMES_MAX = 3


# Une page de l'Arena est un défi, sauf la page de refus (`blocage`) : elle ne se valide pas seule, il n'y a rien à
# attendre. Reconnue comme un défi, elle ferait attendre la porte d'entrée, et un refus franc deviendrait une alerte.
_ARENA = re.compile(r"<body\b[^>]*\sdata-arena\s*=\s*(?![\"']?blocage[\"'\s>])", re.IGNORECASE)
_FORMULAIRE_DEFI = re.compile(r"<form\b[^>]*\bid\s*=\s*[\"']challenge-form[\"']", re.IGNORECASE)
_CADRE_CLOUDFLARE = re.compile(
    r"<(?:iframe|script)\b[^>]*\bsrc\s*=\s*[\"'][^\"']*challenges\.cloudflare\.com", re.IGNORECASE
)
# (nature, motif) : un cadre ou un script qui charge le service, ou la classe que son widget pose. Un simple texte qui
# nomme le service, ou la balise de mesure `/cdn-cgi/challenge-platform/…` des pages ordinaires de Cloudflare, ne
# comptent pas.
_CAPTCHAS = (
    ("turnstile", re.compile(r"class\s*=\s*[\"'][^\"']*\bcf-turnstile\b", re.IGNORECASE)),
    (
        "recaptcha",
        re.compile(
            r"<(?:iframe|script)\b[^>]*\bsrc\s*=\s*[\"'][^\"']*(?:google\.com/recaptcha|recaptcha\.net|gstatic\.com/recaptcha)",
            re.IGNORECASE,
        ),
    ),
    ("recaptcha", re.compile(r"class\s*=\s*[\"'][^\"']*\bg-recaptcha\b", re.IGNORECASE)),
    ("hcaptcha", re.compile(r"<(?:iframe|script)\b[^>]*\bsrc\s*=\s*[\"'][^\"']*hcaptcha\.com", re.IGNORECASE)),
    ("hcaptcha", re.compile(r"class\s*=\s*[\"'][^\"']*\bh-captcha\b", re.IGNORECASE)),
)


def detecter_defi(html: str, entetes: Mapping[str, str] | None = None) -> str | None:
    """Nature de la page de défi (`arena`, `cloudflare`, `turnstile`, `recaptcha`, `hcaptcha`), ou None.

    Ne fait que reconnaître : la sentinelle n'agit jamais sur un défi (ni clic, ni résolution)."""
    if (entetes or {}).get("cf-mitigated", "").strip().lower() == "challenge":
        return "cloudflare"
    if _ARENA.search(html):
        return "arena"
    if _FORMULAIRE_DEFI.search(html):
        return "cloudflare"
    for nature, motif in _CAPTCHAS:
        if motif.search(html):
            return nature
    if _CADRE_CLOUDFLARE.search(html):
        return "cloudflare"
    return None


# Le motif JSON que l'Arena rend à une ressource (photo, appel de données : `Accept` sans `text/html`) à la place de la
# page qu'elle sert à une navigation (`gardien._refus`). Seuls ceux d'une page de défi sont des défis ; les autres
# (`bannissement`, `fingerprinting`, `composite-differe`…) accompagnent la page de refus : un refus franc.
_MOTIFS_DEFI_ARENA = {"defi-js": "arena", "turnstile": "turnstile", "recaptcha": "recaptcha", "captcha": "captcha"}
# Le motif d'un refus qui dit que le visiteur est banni : un bannissement, à toute page de la passe (D-103).
MOTIF_BANNISSEMENT = "bannissement"
# Le motif d'un refus dont le corps n'est jamais arrivé (attendu un temps borné par le moteur, D-103) : rien n'est su.
MOTIF_NON_LU = "corps-non-lu"


def motif_de_refus(corps: str) -> str | None:
    """Le motif JSON de l'Arena (`{"bloque_par": …}`, `gardien._refus`) lu dans le corps d'un refus, ou None."""
    try:
        donnees = json.loads(corps)
    except ValueError:
        return None
    motif = donnees.get("bloque_par") if isinstance(donnees, dict) else None
    return motif if isinstance(motif, str) else None


def detecter_defi_ressource(corps: str, entetes: Mapping[str, str] | None = None) -> str | None:
    """Nature du défi servi à la place d'une ressource de la page (photo, appel de données), ou None (refus franc).

    Une page de défi (`detecter_defi`), ou le motif JSON d'un défi de l'Arena : `defi-js` (la porte d'entrée) donne
    `arena` ; `turnstile`, `recaptcha`, `captcha` donnent leur nom. Tout autre corps (motif de refus, motif inconnu,
    texte quelconque) : None. Ne fait que reconnaître."""
    defi = detecter_defi(corps, entetes)
    if defi is not None:
        return defi
    motif = motif_de_refus(corps)
    return _MOTIFS_DEFI_ARENA.get(motif) if motif is not None else None


class RefusRessource(NamedTuple):
    """Un 403 reçu pour une ressource de la page (`refus_ressources` du moteur) ; `defi` : la nature du défi servi à sa
    place (`detecter_defi_ressource`), None pour un refus franc ou un corps illisible ; `motif` : le motif JSON de
    l'Arena lu dans le corps (`motif_de_refus`), `MOTIF_NON_LU` si le corps n'est jamais arrivé, sinon None."""

    adresse: str
    statut: int
    defi: str | None = None
    motif: str | None = None


@dataclass(frozen=True)
class Alerte:
    signe: str  # statut | defi | hors_site | hors_motif | page_non_conforme | echecs | porte_revenue
    detail: str
    adresse: str
    statut: int | None = None
    defi: str | None = None  # alerte `defi` d'une ressource (`examiner_ressources`) : la nature du défi
    motif: str | None = None  # refus d'une ressource : le motif lu dans son corps (`RefusRessource.motif`)

    def message(self) -> str:
        return f"signe d'alerte ({self.detail}) sur {self.adresse}"


def verdict_identite(alerte: Alerte, premiere_page: bool) -> str:
    """Ce que l'alerte veut dire pour l'identité (§ 5.5) : `banni` pour un refus franc (403) dès la première page de la
    passe, ou à toute page quand le site dit lui-même que le visiteur est banni (motif `bannissement` lu dans le corps
    du refus d'une ressource, D-103) ; `alerte` pour tout le reste (429 et autres statuts, défi, retour à la connexion,
    hors site, porte revenue trop tôt…). Ne fait que classer : aucune requête, aucune action."""
    if alerte.signe == "statut" and alerte.statut == 403 and (premiere_page or alerte.motif == MOTIF_BANNISSEMENT):
        return "banni"
    return "alerte"


class Sentinelle:
    def __init__(self, hotes: Iterable[str]) -> None:
        self._hotes = {h.lower() for h in hotes}
        self._recentes: deque[str] = deque(maxlen=FENETRE)  # décisions des dernières pages lues
        self._non_conformes: dict[str, int] = defaultdict(int)  # par type : pages de suite sans `requis`

    def examiner(
        self,
        *,
        type_page: str,
        adresse: str,
        statut: int | None,
        adresse_finale: str,
        dans_le_motif: bool,
        html: str | None = None,
        entetes: Mapping[str, str] | None = None,
    ) -> Alerte | None:
        """Signes 1, 3 et 2 (si le contenu est donné), avant de lire le contenu."""
        if statut in STATUTS_ALERTE:
            return Alerte("statut", f"statut {statut}", adresse, statut)
        hote = (urlsplit(adresse_finale).hostname or "").lower()
        if hote not in self._hotes:
            return Alerte("hors_site", f"redirection vers un autre hôte : {hote or adresse_finale}", adresse, statut)
        defi = detecter_defi(html, entetes) if html is not None else None
        if defi is not None:  # avant le motif : un défi servi à la place de la page est d'abord un défi
            return Alerte("defi", f"page de défi ({defi})", adresse, statut)
        if not dans_le_motif:
            return Alerte(
                "hors_motif", f"adresse finale {adresse_finale} hors du motif du type « {type_page} »", adresse, statut
            )
        return None

    def examiner_ressources(self, refus: Iterable[tuple]) -> Alerte | None:
        """Un 403 reçu pour une ressource de la page (photo, appel de données) du MÊME hôte que la recette est un refus,
        comme celui de la page : les ressources d'un autre hôte (CDN, mesure) ne disent rien de ce site.

        `refus` : des `RefusRessource` (adresse, statut, nature du défi), ou des couples (adresse, statut) d'un pilote
        qui ne lit pas le corps. Un 403 dont le corps est un défi (`detecter_defi_ressource`, lu par le moteur) n'est
        pas un refus franc : alerte `defi` (jamais un bannissement, `verdict_identite`), comme le même défi servi à la
        place d'une page ; le parcours l'excuse quand c'est le défi de sa porte d'entrée et qu'elle peut être repassée.
        Du plus grave au moins grave : un refus au motif `bannissement`, un autre refus franc, un défi d'une autre
        nature, le défi de la porte de l'Arena (`arena`), puis un refus dont le corps n'est jamais arrivé
        (`MOTIF_NON_LU`) : rien n'en est su, il ne compte que seul, comme un refus franc (D-103)."""
        retenu: tuple[int, RefusRessource] | None = None
        for brut in refus:
            r = RefusRessource(*brut)
            if r.statut != 403 or (urlsplit(r.adresse).hostname or "").lower() not in self._hotes:
                continue
            if r.motif == MOTIF_NON_LU:
                gravite = 3
            elif r.defi is None:
                gravite = -1 if r.motif == MOTIF_BANNISSEMENT else 0
            else:
                gravite = 1 if r.defi != "arena" else 2
            if retenu is None or gravite < retenu[0]:
                retenu = (gravite, r)
        if retenu is None:
            return None
        r = retenu[1]
        if r.defi is None:
            precision = {MOTIF_BANNISSEMENT: " (motif bannissement)", MOTIF_NON_LU: " (corps non lu)"}.get(r.motif, "")
            detail = f"statut 403 sur une ressource de la page{precision}"
            return Alerte("statut", detail, r.adresse, 403, motif=r.motif)
        return Alerte("defi", f"page de défi ({r.defi}) sur une ressource de la page", r.adresse, 403, r.defi)

    def noter(self, type_page: str, decision: str, adresse: str = "") -> Alerte | None:
        """Signes 4 et 5, une fois la page lue. `decision` : ok, introuvable, anormale ou echec."""
        self._recentes.append(decision)
        if decision == "anormale":
            self._non_conformes[type_page] += 1
            if self._non_conformes[type_page] >= NON_CONFORMES_MAX:
                return Alerte(
                    "page_non_conforme",
                    f"{NON_CONFORMES_MAX} pages « {type_page} » de suite sans leur sélecteur requis",
                    adresse,
                )
        elif decision == "ok":
            self._non_conformes[type_page] = 0
        if sum(1 for d in self._recentes if d == "echec") > ECHECS_MAX:
            return Alerte("echecs", f"plus de {ECHECS_MAX} échecs sur les {FENETRE} dernières pages", adresse)
        return None

    def rejouer(self, lignes: Iterable[Mapping[str, object]]) -> None:
        """Reprend l'historique (pages déjà lues, dans l'ordre) : la reprise ne repart pas de zéro."""
        for ligne in lignes:
            self.noter(str(ligne["type"]), str(ligne["decision"]))
