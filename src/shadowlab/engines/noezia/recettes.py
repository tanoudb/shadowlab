"""Recettes de récolte : un fichier YAML décrit un site (pages, champs à lire, liens à suivre).

Deux parties, sans réseau ni parcours de site :

- `lire` / `lire_texte` lisent une recette et la contrôlent. Une recette fautive est refusée avec un message
  qui nomme la clé fautive, son chemin (`pages.fiche.enregistrements[0].champs.prix.format`) et sa ligne.
- `extraire` lit UNE page (HTML, adresse, type de page) : ses enregistrements et les liens à suivre.

Format : `docs/recherche/recolte-generale-2026-11-12.md` § 4. Rappels qui comptent à la lecture du code :
- le texte d'un champ est celui de l'élément entier, espaces réduites à une (règle d'`Element.texte`) ;
- un texte vide est une valeur absente (`None`) ;
- l'extraction adaptative n'a lieu que pour un champ qui porte `adaptatif: true`, et chaque relocalisation
  est signalée dans l'enregistrement (`relocalises`).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urldefrag, urljoin, urlsplit

import yaml
from parsel import Selector
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from .analyseur import Analyseur, Element
from .extraction import Signatures

# ═══ Lecture et contrôle d'une recette ═════════════════════════════════════════════════════════

_RE_IDENTIFIANT = re.compile(r"^[a-z][a-z0-9_]*$")
_RE_VARIABLE = re.compile(r"\{(\w+)\}")
_HOTES_LOCAUX = {"127.0.0.1", "localhost", "::1", "[::1]"}


class RecetteInvalide(ValueError):
    """La recette est illisible ou fautive ; le message dit quoi, où (chemin et ligne)."""


def _css_valide(selecteur: str) -> str:
    if not selecteur.strip():
        raise ValueError("sélecteur CSS vide")
    try:
        Selector(text="<html></html>").css(selecteur)
    except Exception as erreur:
        raise ValueError(f"sélecteur CSS invalide « {selecteur} » ({erreur})") from erreur
    return selecteur


def _motif_valide(motif: str, nature: str) -> str:
    """Contrôle une expression régulière ; `nature` dit à quoi elle sert (message d'erreur)."""
    try:
        compile_ = re.compile(motif)
    except re.error as erreur:
        raise ValueError(f"motif {nature} invalide « {motif} » ({erreur})") from erreur
    if nature != "d'adresse de page" and compile_.groups < 1:
        raise ValueError(f"motif {nature} sans groupe « {motif} » : le groupe 1 donne la valeur gardée")
    return motif


def _est_local(hote: str) -> bool:
    return hote in _HOTES_LOCAUX or hote.endswith((".localhost", ".test"))


class _Modele(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Champ(_Modele):
    """Comment lire une valeur : `'sélecteur'` seul, ou le détail (§ 4, « Désigner un champ »)."""

    css: str | None = None
    attribut: str | None = None
    adresse: str | None = None
    colonne: str | int | None = None
    motif: str | None = None
    format: Literal["texte", "entier", "nombre", "duree_ms"] = "texte"
    vide_si: list[str] = []
    tous: bool = False
    lien: bool = False
    present: bool = False
    adaptatif: bool = False

    @model_validator(mode="before")
    @classmethod
    def depuis_un_selecteur(cls, donnees: Any) -> Any:
        return {"css": donnees} if isinstance(donnees, str) else donnees

    @field_validator("css")
    @classmethod
    def css_lisible(cls, valeur: str | None) -> str | None:
        return None if valeur is None else _css_valide(valeur)

    @field_validator("attribut")
    @classmethod
    def attribut_non_vide(cls, valeur: str | None) -> str | None:
        if valeur is not None and not valeur.strip():
            raise ValueError("nom d'attribut vide")
        return valeur

    @field_validator("adresse")
    @classmethod
    def adresse_lisible(cls, valeur: str | None) -> str | None:
        return None if valeur is None else _motif_valide(valeur, "d'adresse de champ")

    @field_validator("motif")
    @classmethod
    def motif_lisible(cls, valeur: str | None) -> str | None:
        return None if valeur is None else _motif_valide(valeur, "de valeur")

    @field_validator("colonne")
    @classmethod
    def colonne_lisible(cls, valeur: str | int | None) -> str | int | None:
        if isinstance(valeur, bool) or (isinstance(valeur, int) and valeur < 1):
            raise ValueError("colonne : un nom d'en-tête, ou un rang entier à partir de 1")
        if isinstance(valeur, str) and not valeur.strip():
            raise ValueError("nom de colonne vide")
        return valeur

    @model_validator(mode="after")
    def coherent(self) -> Champ:
        if self.css is None and self.adresse is None and self.colonne is None:
            raise ValueError("champ sans moyen de le lire : donner css, adresse ou colonne")
        if self.adresse is not None:
            autres = [n for n in ("css", "colonne", "attribut") if getattr(self, n) is not None]
            autres += [n for n in ("tous", "present", "adaptatif", "lien") if getattr(self, n)]
            if autres:
                raise ValueError(f"adresse ne se combine pas avec {', '.join(autres)}")
        if self.present:
            autres = [n for n in ("attribut", "motif") if getattr(self, n) is not None]
            autres += [n for n in ("tous", "adaptatif", "lien", "vide_si") if getattr(self, n)]
            autres += ["format"] if self.format != "texte" else []
            if autres:
                raise ValueError(f"present ne se combine pas avec {', '.join(autres)}")
        if self.adaptatif:
            if self.css is None:
                raise ValueError("adaptatif demande un css (relocalisation d'un élément)")
            autres = [n for n in ("colonne", "attribut") if getattr(self, n) is not None]
            autres += ["tous"] if self.tous else []
            if autres:
                raise ValueError(f"adaptatif ne lit que le texte d'un élément : pas {', '.join(autres)}")
        if self.lien and self.attribut is None:
            raise ValueError("lien demande un attribut (href, src…) : c'est son adresse qu'on rend absolue")
        return self


class RegleEnregistrement(_Modele):
    """Un enregistrement par page, ou un par ligne de tableau (`lignes`), ou un par bloc (`similaires`)."""

    collection: str
    cle: list[str]
    champs: dict[str, Champ]
    lignes: str | None = None
    similaires: str | None = None

    @field_validator("collection")
    @classmethod
    def collection_lisible(cls, valeur: str) -> str:
        if not _RE_IDENTIFIANT.match(valeur):
            raise ValueError("nom de collection : minuscules, chiffres et _, commençant par une lettre")
        return valeur

    @field_validator("cle", mode="before")
    @classmethod
    def cle_en_liste(cls, valeur: Any) -> Any:
        return [valeur] if isinstance(valeur, str) else valeur

    @field_validator("cle")
    @classmethod
    def cle_non_vide(cls, valeur: list[str]) -> list[str]:
        if not valeur or len(set(valeur)) != len(valeur):
            raise ValueError("cle : un champ ou une liste de champs, sans doublon")
        return valeur

    @field_validator("champs")
    @classmethod
    def champs_nommes(cls, valeur: dict[str, Champ]) -> dict[str, Champ]:
        if not valeur:
            raise ValueError("champs : au moins un champ")
        for nom in valeur:
            if not _RE_IDENTIFIANT.match(str(nom)):
                raise ValueError(f"nom de champ « {nom} » : minuscules, chiffres et _ (« _ » initial réservé)")
        return valeur

    @field_validator("lignes", "similaires")
    @classmethod
    def selecteur_lisible(cls, valeur: str | None) -> str | None:
        return None if valeur is None else _css_valide(valeur)

    @model_validator(mode="after")
    def coherent(self) -> RegleEnregistrement:
        if self.lignes and self.similaires:
            raise ValueError("lignes et similaires s'excluent : un seul des deux")
        for nom in self.cle:
            if nom not in self.champs:
                raise ValueError(f"cle : le champ « {nom} » n'existe pas dans champs")
            if self.champs[nom].tous:
                raise ValueError(f"cle : le champ « {nom} » est une liste (tous), il ne peut pas servir de clé")
        for nom, champ in self.champs.items():
            if champ.colonne is not None and not self.lignes:
                raise ValueError(f"champ « {nom} » : colonne n'a de sens que dans un enregistrement à lignes")
            if champ.adaptatif and (self.lignes or self.similaires):
                raise ValueError(f"champ « {nom} » : adaptatif ne marche pas dans lignes ni dans similaires")
        return self


class GarderSi(_Modele):
    contient: str
    contexte: str | None = None

    @field_validator("contexte")
    @classmethod
    def contexte_lisible(cls, valeur: str | None) -> str | None:
        return None if valeur is None else _css_valide(valeur)


class RegleSuivre(_Modele):
    liens: str
    vers: str
    garder_si: GarderSi | None = None

    @model_validator(mode="before")
    @classmethod
    def garder_tout(cls, donnees: Any) -> Any:
        """`garder_si: '*'` veut dire « tout garder » : comme ne rien écrire."""
        if isinstance(donnees, dict) and donnees.get("garder_si") == "*":
            return {k: v for k, v in donnees.items() if k != "garder_si"}
        return donnees

    @field_validator("liens")
    @classmethod
    def liens_lisibles(cls, valeur: str) -> str:
        return _css_valide(valeur)


class TypePage(_Modele):
    url: str
    requis: str | None = None
    attendre: str | None = None
    revisiter: str | None = None
    enregistrements: list[RegleEnregistrement] = []
    suivre: list[RegleSuivre] = []

    @field_validator("url")
    @classmethod
    def url_lisible(cls, valeur: str) -> str:
        return _motif_valide(valeur, "d'adresse de page")

    @field_validator("requis", "attendre")
    @classmethod
    def selecteur_lisible(cls, valeur: str | None) -> str | None:
        return None if valeur is None else _css_valide(valeur)

    @field_validator("revisiter")
    @classmethod
    def revisiter_lisible(cls, valeur: str | None) -> str | None:
        if valeur is not None and not re.fullmatch(r"toujours|jamais|\d+j", valeur):
            raise ValueError("revisiter : toujours, jamais ou un nombre de jours (7j)")
        return valeur

    @model_validator(mode="after")
    def revisiter_par_defaut(self) -> TypePage:
        if self.revisiter is None:
            self.revisiter = "toujours" if self.suivre else "jamais"
        return self


class Depart(_Modele):
    url: str
    type: str


class Robots(_Modele):
    agent: str = "noezia"


class PorteEntree(_Modele):
    attendre_s: float

    @field_validator("attendre_s")
    @classmethod
    def positif(cls, valeur: float) -> float:
        if valeur <= 0:
            raise ValueError("attendre_s : un nombre de secondes positif")
        return valeur


class Bornes(_Modele):
    pages_max: int | None = None
    par_type: dict[str, int] = {}

    @field_validator("pages_max")
    @classmethod
    def pages_max_positif(cls, valeur: int | None) -> int | None:
        if valeur is not None and valeur < 1:
            raise ValueError("pages_max : au moins 1")
        return valeur


class Recette(_Modele):
    recette: Literal[1]
    nom: str
    autorisation: str | None = None
    moteur: Literal["http", "navigateur"] = "http"
    hotes: list[str]
    depart: list[Depart]
    variables: dict[str, str] = {}
    parametres_ignores: list[str] = []
    rythme: str | dict[str, Any] | None = None  # `libre`, `prudent` ou le détail : lu par le parcours (étape 2)
    robots: Robots = Robots()
    porte_entree: PorteEntree | None = None
    bornes: Bornes = Bornes()
    pages: dict[str, TypePage]

    @field_validator("nom")
    @classmethod
    def nom_de_dossier(cls, valeur: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", valeur):
            raise ValueError("nom court en minuscules, chiffres, - et _ (il sert de dossier de sortie)")
        return valeur

    @field_validator("hotes")
    @classmethod
    def hotes_non_vides(cls, valeur: list[str]) -> list[str]:
        if not valeur or any(not h.strip() for h in valeur):
            raise ValueError("hotes : au moins un hôte, sans élément vide")
        return [h.strip().lower() for h in valeur]

    @field_validator("depart")
    @classmethod
    def depart_non_vide(cls, valeur: list[Depart]) -> list[Depart]:
        if not valeur:
            raise ValueError("depart : au moins une adresse de départ")
        return valeur

    @field_validator("variables")
    @classmethod
    def variables_nommees(cls, valeur: dict[str, str]) -> dict[str, str]:
        for nom in valeur:
            if not re.fullmatch(r"\w+", str(nom)):
                raise ValueError(f"nom de variable « {nom} » : lettres, chiffres et _")
        return valeur

    @field_validator("rythme")
    @classmethod
    def rythme_lisible(cls, valeur: Any) -> Any:
        if isinstance(valeur, str) and valeur not in ("libre", "prudent"):
            raise ValueError("rythme : libre, prudent, ou le détail sous forme de tableau")
        return valeur

    @field_validator("pages")
    @classmethod
    def pages_nommees(cls, valeur: dict[str, TypePage]) -> dict[str, TypePage]:
        if not valeur:
            raise ValueError("pages : au moins un type de page")
        for nom in valeur:
            if not _RE_IDENTIFIANT.match(str(nom)):
                raise ValueError(f"nom de type de page « {nom} » : minuscules, chiffres et _")
        return valeur


@dataclass(frozen=True)
class _Faute:
    chemin: tuple[str | int, ...]
    message: str
    plein: bool = False  # vrai : afficher le chemin en entier, même si la clé n'existe pas dans le fichier


def _controles_croises(recette: Recette) -> list[_Faute]:
    """Ce que la validation clé par clé ne voit pas : renvois d'un type à l'autre, hôtes, variables."""
    fautes: list[_Faute] = []
    if not recette.autorisation:
        for i, hote in enumerate(recette.hotes):
            if not _est_local(hote):
                fautes.append(
                    _Faute(("hotes", i), f"autorisation obligatoire : l'hôte « {hote} » n'est pas local (D-30)")
                )
    for i, depart in enumerate(recette.depart):
        morceaux = urlsplit(depart.url)
        if morceaux.scheme not in ("http", "https") or not morceaux.hostname:
            fautes.append(_Faute(("depart", i, "url"), f"adresse http(s) complète attendue, reçu « {depart.url} »"))
        elif morceaux.hostname.lower() not in recette.hotes:
            fautes.append(
                _Faute(("depart", i, "url"), f"l'hôte « {morceaux.hostname} » n'est pas dans hotes ({recette.hotes})")
            )
        if depart.type not in recette.pages:
            fautes.append(_Faute(("depart", i, "type"), f"type de page « {depart.type} » absent de pages"))
    for type_page in recette.bornes.par_type:
        if type_page not in recette.pages:
            fautes.append(_Faute(("bornes", "par_type", type_page), "type de page absent de pages"))
    for nom, page in recette.pages.items():
        for i, regle in enumerate(page.suivre):
            if regle.vers not in recette.pages:
                fautes.append(
                    _Faute(
                        ("pages", nom, "suivre", i, "vers"),
                        f"type de page « {regle.vers} » absent de pages (connus : {', '.join(recette.pages)})",
                    )
                )
            if regle.garder_si is not None:
                for variable in _RE_VARIABLE.findall(regle.garder_si.contient):
                    if variable not in recette.variables:
                        fautes.append(
                            _Faute(
                                ("pages", nom, "suivre", i, "garder_si", "contient"),
                                f"variable « {variable} » non déclarée dans variables",
                            )
                        )
    return fautes


_TYPES_PYDANTIC = {
    "string_type": "un texte est attendu",
    "int_type": "un entier est attendu",
    "float_type": "un nombre est attendu",
    "bool_type": "vrai ou faux est attendu",
    "list_type": "une liste est attendue",
    "dict_type": "un tableau (clé: valeur) est attendu",
    "model_type": "un tableau (clé: valeur) est attendu",
    "too_short": "ne peut pas être vide",
}


def _faute_pydantic(erreur: Mapping[str, Any]) -> _Faute:
    chemin = tuple(erreur["loc"])
    genre = erreur["type"]
    if genre == "extra_forbidden":
        return _Faute(chemin, "clé inconnue", plein=True)
    if genre == "missing":
        return _Faute(chemin, "clé obligatoire absente", plein=True)
    if genre == "literal_error":
        return _Faute(chemin, f"valeur admise : {erreur['ctx']['expected']}")
    if genre == "value_error":
        return _Faute(chemin, str(erreur["msg"]).removeprefix("Value error, "))
    return _Faute(chemin, _TYPES_PYDANTIC.get(genre, str(erreur["msg"])))


def _ligne(racine: yaml.Node | None, chemin: Iterable[str | int]) -> tuple[int | None, int]:
    """Ligne (à partir de 1) du dernier élément du chemin présent dans le fichier, et combien d'éléments existent."""
    noeud = racine
    ligne = None if racine is None else racine.start_mark.line + 1
    trouves = 0
    for etape in chemin:
        if isinstance(noeud, yaml.MappingNode) and isinstance(etape, str):
            suivant = next(((k, v) for k, v in noeud.value if getattr(k, "value", None) == etape), None)
            if suivant is None:
                break
            ligne, noeud = suivant[0].start_mark.line + 1, suivant[1]
        elif isinstance(noeud, yaml.SequenceNode) and isinstance(etape, int) and etape < len(noeud.value):
            noeud = noeud.value[etape]
            ligne = noeud.start_mark.line + 1
        else:
            break
        trouves += 1
    return ligne, trouves


def _chemin_texte(chemin: Iterable[str | int]) -> str:
    texte = ""
    for etape in chemin:
        texte += f"[{etape}]" if isinstance(etape, int) else (f".{etape}" if texte else str(etape))
    return texte


def _refus(source: str, fautes: list[_Faute], racine: yaml.Node | None) -> RecetteInvalide:
    lignes = [f"recette fautive ({source}) :"]
    for faute in fautes:
        ligne, trouves = _ligne(racine, faute.chemin)
        chemin = faute.chemin if faute.plein else faute.chemin[:trouves]
        lieu = f" (ligne {ligne})" if ligne else ""
        lignes.append(f"  - {_chemin_texte(chemin) or '(racine)'}{lieu} : {faute.message}")
    return RecetteInvalide("\n".join(lignes))


def lire_texte(texte: str, source: str = "recette") -> Recette:
    """Lit et contrôle le texte d'une recette. `RecetteInvalide` dit la clé, le chemin et la ligne fautifs."""
    from shadowlab.campaigns import charger_yaml  # import tardif : campaigns importe les moteurs

    try:
        brut = charger_yaml(texte)
        racine = yaml.compose(texte, Loader=yaml.SafeLoader)
    except yaml.YAMLError as erreur:
        marque = getattr(erreur, "problem_mark", None)
        lieu = f" (ligne {marque.line + 1})" if marque is not None else ""
        raise RecetteInvalide(
            f"recette illisible ({source}) : YAML invalide{lieu} : {getattr(erreur, 'problem', None) or erreur}"
        ) from erreur
    try:
        recette = Recette.model_validate(brut)
    except ValidationError as erreur:
        raise _refus(source, [_faute_pydantic(e) for e in erreur.errors()], racine) from erreur
    fautes = _controles_croises(recette)
    if fautes:
        raise _refus(source, fautes, racine)
    return recette


def lire(chemin: Path | str) -> Recette:
    """Lit et contrôle le fichier d'une recette."""
    chemin = Path(chemin)
    try:
        texte = chemin.read_text(encoding="utf-8")
    except OSError as erreur:
        raise RecetteInvalide(f"recette introuvable ou illisible : {chemin} ({erreur})") from erreur
    return lire_texte(texte, source=str(chemin))


# ═══ Extraction d'une page ═════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Lien:
    adresse: str  # absolue, sans fragment
    type: str  # type de page de la cible (`vers`)
    texte: str


@dataclass
class Enregistrement:
    collection: str
    cle: tuple[Any, ...]
    donnees: dict[str, Any]
    relocalises: tuple[str, ...] = ()  # champs `adaptatif` retrouvés par ressemblance : à signaler


@dataclass
class Resultat:
    """Ce que dit une page. `conforme` faux : l'adresse ou la page n'est pas celle du type attendu (rien n'est lu)."""

    enregistrements: list[Enregistrement] = field(default_factory=list)
    liens: list[Lien] = field(default_factory=list)
    alertes: list[str] = field(default_factory=list)
    conforme: bool = True

    @property
    def relocalisations(self) -> int:
        return sum(len(e.relocalises) for e in self.enregistrements)


def _nettoyer(texte: str) -> str:
    return " ".join(texte.split())


def chemin_et_parametres(adresse: str, ignores: Iterable[str] = ()) -> str:
    """Chemin et paramètres d'une adresse, sans les `ignores` : ce que le motif `url` d'un type de page compare."""
    morceaux = urlsplit(adresse)
    ignores = set(ignores)
    gardes = [p for p in morceaux.query.split("&") if p and p.split("=", 1)[0] not in ignores]
    return (morceaux.path or "/") + (f"?{'&'.join(gardes)}" if gardes else "")


def _entier(valeur: str) -> int | None:
    chiffres = re.sub(r"\D", "", valeur)
    return int(chiffres) if chiffres else None


def _nombre(valeur: str) -> float | None:
    """« 142,6 km » → 142.6 ; « 1 234,5 » → 1234.5 (le point est un séparateur de milliers s'il y a une virgule)."""
    texte = re.sub(r"[^\d,.\-]", "", valeur)
    if "," in texte and "." in texte:
        texte = texte.replace(".", "")
    try:
        return float(texte.replace(",", "."))
    except ValueError:
        return None


_RE_DUREE = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{1,2}(?:[.,]\d+)?)")


def _duree_ms(valeur: str) -> int | None:
    """`9:58.7` → 598700 ; `1:02:03.4` → 3723400."""
    trouve = _RE_DUREE.fullmatch(valeur)
    if trouve is None:
        return None
    heures, minutes, secondes = trouve.groups()
    total = Decimal(heures or 0) * 3600 + Decimal(minutes) * 60 + Decimal(secondes.replace(",", "."))
    return int((total * 1000).to_integral_value())


_CONVERSIONS = {"entier": _entier, "nombre": _nombre, "duree_ms": _duree_ms}


def _noeud(element: Element) -> Any:
    """Nœud lxml d'un `Element` (pour remonter les ancêtres et lire les cellules d'un tableau)."""
    return element._sel.root


def _cellules(ligne: Any) -> list[Any]:
    return [c for c in ligne if isinstance(c.tag, str) and c.tag in ("td", "th")]


def _element(noeud: Any) -> Element:
    return Element(Selector(root=noeud))


@dataclass
class _Portee:
    """Où se lisent les champs d'un enregistrement : la page, un bloc, ou une ligne de tableau."""

    contexte: Any  # Analyseur ou Element : tous deux ont `.elements(css)`
    cellules: list[Element] | None = None
    entetes: list[str] | None = None


class _Lecteur:
    def __init__(self, recette: Recette, type_page: str, adresse: str, analyseur: Analyseur) -> None:
        self.recette = recette
        self.type = type_page
        self.adresse = adresse
        self.cible = chemin_et_parametres(adresse, recette.parametres_ignores)
        self.analyseur = analyseur
        self.alertes: list[str] = []
        self._relocalises: list[str] = []

    def alerter(self, message: str) -> None:
        if message not in self.alertes:
            self.alertes.append(message)

    # ── Enregistrements ─────────────────────────────────────────────────
    def enregistrements(self, regle: RegleEnregistrement) -> list[Enregistrement]:
        lus = []
        for portee in self._portees(regle):
            self._relocalises = []
            donnees = {nom: self._champ(champ, nom, regle, portee) for nom, champ in regle.champs.items()}
            cle = tuple(donnees[nom] for nom in regle.cle)
            vides = [nom for nom, valeur in zip(regle.cle, cle, strict=True) if valeur is None]
            if vides:
                self.alerter(f"enregistrement « {regle.collection} » ignoré : clé « {vides[0]} » sans valeur")
                continue
            lus.append(Enregistrement(regle.collection, cle, donnees, tuple(self._relocalises)))
        return lus

    def _portees(self, regle: RegleEnregistrement) -> list[_Portee]:
        if regle.lignes:
            return self._lignes(regle.lignes)
        if regle.similaires:
            return [_Portee(bloc) for bloc in self.analyseur.similaires(regle.similaires)]
        return [_Portee(self.analyseur)]

    def _lignes(self, selecteur: str) -> list[_Portee]:
        """Les lignes à cellules `td` ; l'en-tête est la première ligne à cellules `th` de la même table."""
        entetes_par_table: dict[Any, list[str] | None] = {}
        portees = []
        for ligne in self.analyseur.elements(selecteur):
            noeud = _noeud(ligne)
            cellules = _cellules(noeud)
            if not any(c.tag == "td" for c in cellules):
                continue
            table = next(noeud.iterancestors("table"), None)
            if table not in entetes_par_table:
                entetes_par_table[table] = self._entetes(table)
            portees.append(_Portee(ligne, [_element(c) for c in cellules], entetes_par_table[table]))
        return portees

    @staticmethod
    def _entetes(table: Any) -> list[str] | None:
        if table is None:
            return None
        for ligne in table.iter("tr"):
            cellules = _cellules(ligne)
            if any(c.tag == "th" for c in cellules):
                return [_nettoyer(_element(c).texte) for c in cellules]
        return None

    def _cellule(self, colonne: str | int, portee: _Portee) -> Element | None:
        cellules = portee.cellules or []
        if isinstance(colonne, int):
            rang = colonne - 1
        else:
            nom = _nettoyer(colonne)
            if portee.entetes is None:
                self.alerter(f"colonne « {nom} » : le tableau n'a pas de ligne d'en-tête (cellules th)")
                return None
            if nom not in portee.entetes:
                self.alerter(f"colonne « {nom} » absente de l'en-tête ({', '.join(portee.entetes)})")
                return None
            rang = portee.entetes.index(nom)
        return cellules[rang] if rang < len(cellules) else None

    # ── Champs ──────────────────────────────────────────────────────────
    def _champ(self, champ: Champ, nom: str, regle: RegleEnregistrement, portee: _Portee) -> Any:
        if champ.adresse is not None:
            trouve = re.search(champ.adresse, self.cible)
            return self._finir(champ, nom, [trouve.group(1)] if trouve and trouve.group(1) else [])
        if champ.adaptatif:
            return self._finir(champ, nom, self._adaptatif(champ, nom, regle))
        if champ.colonne is not None:
            cellule = self._cellule(champ.colonne, portee)
            if cellule is None:
                cibles: list[Element] = []
            else:
                cibles = [cellule] if champ.css is None else cellule.elements(champ.css)
        else:
            cibles = portee.contexte.elements(champ.css)
        if champ.present:
            return bool(cibles)
        if not champ.tous:
            cibles = cibles[:1]
        brutes = []
        for cible in cibles:
            valeur = cible.attribut(champ.attribut) if champ.attribut else cible.texte
            if valeur is not None:
                brutes.append(valeur)
        return self._finir(champ, nom, brutes)

    def _adaptatif(self, champ: Champ, nom: str, regle: RegleEnregistrement) -> list[str]:
        existe = bool(self.analyseur.elements(champ.css))
        texte = self.analyseur.extraire_adaptatif(champ.css, f"{self.type}/{regle.collection}/{nom}")
        if texte is None:
            return []
        if not existe:
            self._relocalises.append(nom)
        return [texte]

    def _finir(self, champ: Champ, nom: str, brutes: list[str]) -> Any:
        valeurs = [v for v in (self._convertir(champ, nom, b) for b in brutes) if v is not None]
        if champ.tous:
            return valeurs
        return valeurs[0] if valeurs else None

    def _convertir(self, champ: Champ, nom: str, brut: str) -> Any:
        """Nettoyage, valeurs « vides », adresse absolue, motif, puis format."""
        valeur = _nettoyer(brut)
        if not valeur or valeur in {_nettoyer(v) for v in champ.vide_si}:
            return None
        if champ.lien:
            valeur = urljoin(self.adresse, valeur)
        if champ.motif:
            trouve = re.search(champ.motif, valeur)
            valeur = (trouve.group(1) or "") if trouve else ""
            if not valeur:
                return None
        if champ.format == "texte":
            return valeur
        converti = _CONVERSIONS[champ.format](valeur)
        if converti is None:
            self.alerter(f"champ « {nom} » : « {valeur} » n'est pas lisible en {champ.format}")
        return converti

    # ── Liens ───────────────────────────────────────────────────────────
    def liens(self, regle: RegleSuivre, variables: Mapping[str, str]) -> list[Lien]:
        attendu = self._attendu(regle, variables)
        contexte = regle.garder_si.contexte if regle.garder_si else None
        contextes = {_noeud(c): c for c in self.analyseur.elements(contexte)} if contexte else {}
        liens = []
        for element in self.analyseur.elements(regle.liens):
            href = (element.attribut("href") or "").strip()
            if not href or href.startswith("#"):
                continue
            adresse = urldefrag(urljoin(self.adresse, href))[0]
            if urlsplit(adresse).scheme not in ("http", "https"):
                continue
            if attendu is not None:
                zone = element
                if contexte:
                    zone = next((contextes[a] for a in _noeud(element).iterancestors() if a in contextes), None)
                if zone is None or attendu not in _nettoyer(zone.texte):
                    continue
            liens.append(Lien(adresse, regle.vers, _nettoyer(element.texte)))
        return liens

    @staticmethod
    def _attendu(regle: RegleSuivre, variables: Mapping[str, str]) -> str | None:
        """Texte que doit contenir le lien (ou sa ligne) ; `None` : tout garder (pas de règle, ou valeur `*`)."""
        if regle.garder_si is None:
            return None
        modele = regle.garder_si.contient
        if modele == "*" or any(variables[v] == "*" for v in _RE_VARIABLE.findall(modele)):
            return None
        return _nettoyer(_RE_VARIABLE.sub(lambda m: variables[m.group(1)], modele))


def extraire(
    recette: Recette,
    html: str,
    adresse: str,
    type_page: str,
    variables: Mapping[str, str] | None = None,
    signatures: Signatures | None = None,
) -> Resultat:
    """Lit UNE page : ses enregistrements et les liens à suivre. Ne fait aucune requête.

    `variables` remplace la valeur par défaut des variables de la recette (`*` = tout garder).
    `signatures` donne la mémoire de l'extraction adaptative (sans elle, aucun champ n'est relocalisé).
    Une page dont l'adresse ne correspond pas au motif `url` du type, ou sans son sélecteur `requis`, est
    `conforme=False` : rien n'est lu, l'appelant décide (page anormale, alerte).
    """
    if type_page not in recette.pages:
        raise ValueError(f"type de page inconnu : « {type_page} » (connus : {', '.join(recette.pages)})")
    valeurs = dict(recette.variables)
    for nom, valeur in (variables or {}).items():
        if nom not in recette.variables:
            raise ValueError(f"variable inconnue : « {nom} » (déclarées : {', '.join(recette.variables) or 'aucune'})")
        valeurs[nom] = valeur

    page = recette.pages[type_page]
    analyseur = Analyseur(html, url=adresse, signatures=signatures)
    lecteur = _Lecteur(recette, type_page, adresse, analyseur)
    resultat = Resultat()
    if not re.search(page.url, lecteur.cible):
        resultat.conforme = False
        resultat.alertes.append(f"adresse {lecteur.cible} hors du motif url du type « {type_page} » ({page.url})")
        return resultat
    if page.requis and not analyseur.elements(page.requis):
        resultat.conforme = False
        resultat.alertes.append(f"sélecteur requis absent de la page « {type_page} » : {page.requis}")
        return resultat

    for regle in page.enregistrements:
        resultat.enregistrements += lecteur.enregistrements(regle)
    for regle in page.suivre:
        resultat.liens += lecteur.liens(regle, valeurs)
    resultat.alertes += lecteur.alertes
    return resultat
