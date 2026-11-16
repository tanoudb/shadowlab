"""Sentinelle : arrêt au premier signe d'alerte.

Signes retenus (§ 5 du document de conception) :
1. statut 401, 403, 407, 429 ou 503 ; un 403 sur une ressource de la page (photo, appel de données) du même hôte
   compte aussi (`examiner_ressources`) ;
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

import re
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
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


@dataclass(frozen=True)
class Alerte:
    signe: str  # statut | defi | hors_site | hors_motif | page_non_conforme | echecs | porte_revenue
    detail: str
    adresse: str
    statut: int | None = None

    def message(self) -> str:
        return f"signe d'alerte ({self.detail}) sur {self.adresse}"


def verdict_identite(alerte: Alerte, premiere_page: bool) -> str:
    """Ce que l'alerte veut dire pour l'identité (§ 5.5) : `banni` pour un refus franc (403) dès la première page de la
    passe, `alerte` pour tout le reste (429 et autres statuts, défi, retour à la connexion, hors site, porte revenue
    trop tôt…). Ne fait que classer : aucune requête, aucune action."""
    if alerte.signe == "statut" and alerte.statut == 403 and premiere_page:
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

    def examiner_ressources(self, refus: Iterable[tuple[str, int]]) -> Alerte | None:
        """Un 403 reçu pour une ressource de la page (photo, appel de données) du MÊME hôte que la recette est un refus,
        comme celui de la page : les ressources d'un autre hôte (CDN, mesure) ne disent rien de ce site."""
        for adresse, statut in refus:
            if statut == 403 and (urlsplit(adresse).hostname or "").lower() in self._hotes:
                return Alerte("statut", "statut 403 sur une ressource de la page", adresse, 403)
        return None

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
