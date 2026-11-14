"""Réseau social fictif « Mosaïk Démo » de l'application publique : univers généré et pages HTML (squelette).

Tout est inventé et généré à partir d'une graine, comme la vitrine : auteurs au nom manifestement fictif (liste fixe
`AUTEURS`, ni prénom ni nom de famille), avatars dessinés (initiales et formes, jamais un visage), publications,
commentaires, étiquettes. Textes en français et en anglais : chaque fonction de rendu prend la langue. Les photos
viennent d'un manifeste (`static/social/photos/manifeste.json`) ; le site marche avec n'importe quel nombre de photos,
au moins une, que les publications se partagent.

Forme imposée par la mesure (cadrage du 13/11/2026, v2) : de vraies pages courtes, sans défilement infini ; aucune
écriture venant du visiteur (« j'aime », commentaire et recherche restent dans la page : `static/social.js`) ; aucun
formulaire hors le bouton « Terminer ma session » du bandeau ; aucun script ni style dans la page. Tout texte passe
par `html.escape`. Aucun module du laboratoire n'est importé (seul `site.vitrine`, déjà servi par l'application).
"""

# ruff: noqa: E501  (gabarits HTML et textes : lignes longues voulues)
from __future__ import annotations

import json
import math
import random
import re
import unicodedata
import zlib
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from ..site.vitrine import MARQUE as MARQUE_VITRINE
from ..site.vitrine import Habillage

MARQUE = "Mosaïk Démo"  # nom de travail, manifestement fictif ; à changer ici seulement
DOSSIER_PHOTOS = Path(__file__).resolve().parent / "static" / "social" / "photos"
TAILLES_PHOTO = (1080, 480)  # largeurs servies : `<id>-1080.jpg` (fil, publication) et `<id>-480.jpg` (grilles)
PAR_PAGE_FIL = 6
PAR_PAGE_GRILLE = 12  # explorer, profil, étiquette, crédits : 12 vignettes au plus par page (plafonds d'une session)
NB_AUTRES = 4  # autres publications de l'auteur, sur la page d'une publication
NB_VOISINES = 4  # publications voisines dans le fil, sur la page d'une publication
RE_IDENTIFIANT_PHOTO = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # identifiants de publication, sans caractère ambigu
ORIGINE_DATES = datetime(2026, 11, 10, 19, 0)  # date de la publication la plus récente
# Seuls hôtes vers lesquels le site fait un lien (page de crédits : page d'origine de la photo, texte de sa licence).
HOTES_CREDITS = frozenset({"commons.wikimedia.org", "creativecommons.org"})

Texte = tuple[str, str]  # (français, anglais)

# --- Vocabulaire (tout est inventé) ------------------------------------------------------------

# (pseudonyme, nom affiché) : des noms de choses, jamais un prénom suivi d'un nom.
AUTEURS: tuple[tuple[str, str], ...] = (
    ("heron.cendre", "Héron cendré"),
    ("carnet.de.sel", "Carnet de sel"),
    ("lumiere.d.octobre", "Lumière d'octobre"),
    ("atelier.lichen", "Atelier lichen"),
    ("brume.du.matin", "Brume du matin"),
    ("petit.phare", "Petit phare"),
    ("grain.de.sable", "Grain de sable"),
    ("ciel.d.ardoise", "Ciel d'ardoise"),
    ("renard.roux", "Renard roux"),
    ("encre.bleue", "Encre bleue"),
    ("cedre.tranquille", "Cèdre tranquille"),
    ("vent.du.large", "Vent du large"),
    ("pomme.de.pin", "Pomme de pin"),
    ("caillou.blanc", "Caillou blanc"),
    ("feuille.d.or", "Feuille d'or"),
    ("nuage.lent", "Nuage lent"),
    ("mousse.et.fougere", "Mousse et fougère"),
    ("sentier.perdu", "Sentier perdu"),
    ("chambre.noire", "Chambre noire"),
    ("ecume", "Écume"),
    ("galet.rond", "Galet rond"),
    ("lune.rousse", "Lune rousse"),
    ("pluie.fine", "Pluie fine"),
    ("tasse.de.the", "Tasse de thé"),
)
BIOS: tuple[Texte, ...] = (
    ("Photos du dimanche, surtout la mer.", "Sunday photos, mostly the sea."),
    ("Je marche, je regarde, je cadre.", "I walk, I look, I frame."),
    ("Petites choses du quotidien.", "Small everyday things."),
    ("Carnet de voyage sans destination.", "A travel diary with no destination."),
    ("Lumière du matin et café noir.", "Morning light and black coffee."),
    ("Couleurs, textures, détails.", "Colours, textures, details."),
    ("Un jour, une image.", "One day, one picture."),
    ("Amateur de ciels changeants.", "Fond of changing skies."),
    ("Ce que je vois depuis ma fenêtre.", "What I see from my window."),
    ("Balades lentes, photos rapides.", "Slow walks, quick photos."),
    ("Ici, rien n'est vrai : c'est un réseau de démonstration.", "Nothing here is real: this is a demo network."),
    ("Collectionneur de cailloux et de nuages.", "Collector of pebbles and clouds."),
)
# Sujet du manifeste → étiquette (identifiant ASCII, le même dans les deux langues).
SUJETS: dict[str, str] = {
    "mer": "mer",
    "plage": "mer",
    "montagne": "montagne",
    "ville": "ville",
    "architecture": "architecture",
    "foret": "foret",
    "lac": "lac",
    "desert": "desert",
    "cuisine": "cuisine",
    "plante": "plantes",
    "plantes": "plantes",
    "fleur": "plantes",
    "animal": "animaux",
    "animaux": "animaux",
    "ciel": "ciel",
    "objet": "objets",
    "objets": "objets",
    "paysage": "paysage",
    "paysages": "paysage",
}
ETIQUETTES: dict[str, Texte] = {
    "mer": ("mer", "sea"),
    "montagne": ("montagne", "mountains"),
    "ville": ("ville", "city"),
    "architecture": ("architecture", "architecture"),
    "foret": ("forêt", "forest"),
    "lac": ("lac", "lake"),
    "desert": ("désert", "desert"),
    "cuisine": ("cuisine", "food"),
    "plantes": ("plantes", "plants"),
    "animaux": ("animaux", "animals"),
    "ciel": ("ciel", "sky"),
    "objets": ("objets", "objects"),
    "paysage": ("paysage", "landscape"),
    # Sujets du manifeste qui ne passent pas par SUJETS (leur étiquette garde le nom du sujet).
    "fleurs": ("fleurs", "flowers"),
    "lacs": ("lacs", "lakes"),
    "routes": ("routes", "roads"),
    "sauvages": ("faune sauvage", "wildlife"),
    "domestiques": ("animaux domestiques", "pets"),
    "lumiere": ("lumière", "light"),
    "matin": ("matin", "morning"),
    "soir": ("soir", "evening"),
    "couleurs": ("couleurs", "colours"),
    "calme": ("calme", "calm"),
    "balade": ("balade", "walk"),
    "details": ("détails", "details"),
    "voyage": ("voyage", "travel"),
    "texture": ("texture", "texture"),
    "minimal": ("minimal", "minimal"),
    "saison": ("saison", "season"),
    "dimanche": ("dimanche", "sunday"),
}
AMBIANCES = (
    "lumiere",
    "matin",
    "soir",
    "couleurs",
    "calme",
    "balade",
    "details",
    "voyage",
    "texture",
    "minimal",
    "saison",
    "dimanche",
)
LEGENDES: dict[str, tuple[Texte, ...]] = {
    "mer": (
        ("Marée basse, ciel immense.", "Low tide, endless sky."),
        ("Le bruit des vagues, en image.", "The sound of the waves, in a picture."),
    ),
    "montagne": (
        ("Au-dessus des nuages.", "Above the clouds."),
        ("Le sentier valait chaque pas.", "The trail was worth every step."),
    ),
    "ville": (
        ("La ville s'allume.", "The city lights up."),
        ("Rues calmes avant l'heure de pointe.", "Quiet streets before rush hour."),
    ),
    "architecture": (
        ("Lignes et ombres.", "Lines and shadows."),
        ("Une façade qui raconte une histoire.", "A facade that tells a story."),
    ),
    "foret": (
        ("Sous les arbres, tout ralentit.", "Under the trees, everything slows down."),
        ("Vert à perte de vue.", "Green as far as the eye can see."),
    ),
    "lac": (
        ("L'eau était un miroir ce matin.", "The water was a mirror this morning."),
        ("Silence au bord du lac.", "Silence by the lake."),
    ),
    "desert": (
        ("Du sable et rien d'autre.", "Sand and nothing else."),
        ("La chaleur se voit presque.", "You can almost see the heat."),
    ),
    "cuisine": (
        ("Fait maison, mangé aussitôt.", "Homemade, eaten right away."),
        ("Le meilleur moment de la journée.", "The best part of the day."),
    ),
    "plantes": (("Elle a enfin fleuri.", "It finally bloomed."), ("Petit coin de verdure.", "A little green corner.")),
    "animaux": (
        ("Il a bien voulu poser.", "It agreed to pose."),
        ("Rencontre au détour du chemin.", "An encounter along the path."),
    ),
    "ciel": (
        ("Le ciel a changé dix fois en une heure.", "The sky changed ten times in an hour."),
        ("Fin de journée en couleurs.", "The day ends in colour."),
    ),
    "objets": (
        ("Les choses simples.", "Simple things."),
        ("Trouvé au marché ce matin.", "Found at the market this morning."),
    ),
    "paysage": (
        ("On s'est arrêtés juste pour ça.", "We stopped just for this."),
        ("Vue imprenable.", "A breathtaking view."),
    ),
}
LEGENDES_GENERIQUES: tuple[Texte, ...] = (
    ("Un instant à garder.", "A moment to keep."),
    ("Rien de spécial, et pourtant.", "Nothing special, and yet."),
    ("Vu en passant.", "Seen in passing."),
    ("Encore un essai de cadrage.", "Another framing experiment."),
)
COMMENTAIRES: tuple[Texte, ...] = (
    ("Superbe lumière !", "Beautiful light!"),
    ("J'adore les couleurs.", "Love the colours."),
    ("On s'y croirait.", "Feels like being there."),
    ("Quel calme.", "So peaceful."),
    ("Très beau cadrage.", "Lovely framing."),
    ("Ça donne envie d'y aller.", "Makes me want to go."),
    ("Magnifique.", "Gorgeous."),
    ("Elle mériterait d'être imprimée.", "This deserves a print."),
    ("Toujours aussi inspirant.", "Inspiring as always."),
    ("Les tons sont parfaits.", "The tones are perfect."),
    ("Où est-ce ?", "Where is this?"),
    ("Belle série !", "Great series!"),
)
MOIS: tuple[Texte, ...] = (
    ("janvier", "January"),
    ("février", "February"),
    ("mars", "March"),
    ("avril", "April"),
    ("mai", "May"),
    ("juin", "June"),
    ("juillet", "July"),
    ("août", "August"),
    ("septembre", "September"),
    ("octobre", "October"),
    ("novembre", "November"),
    ("décembre", "December"),
)
# Textes de l'interface.
T: dict[str, Texte] = {
    "fil": ("Fil", "Feed"),
    "explorer": ("Explorer", "Explore"),
    "navigation": ("Navigation principale", "Main navigation"),
    "pagination": ("Pagination", "Pagination"),
    "voir_plus": ("Voir plus", "See more"),
    "fin": ("Vous avez tout vu.", "You're all caught up."),
    "page": ("page", "page"),
    "j_aime": ("J'aime", "Like"),
    "commenter": ("Commenter", "Comment"),
    "voir_commentaires": ("Voir les {n} commentaires", "View all {n} comments"),
    "voir_commentaire": ("Voir le commentaire", "View 1 comment"),
    "commentaires": ("Commentaires", "Comments"),
    "aucun_commentaire": ("Aucun commentaire pour l'instant.", "No comments yet."),
    "ajouter_commentaire": ("Ajouter un commentaire", "Add a comment"),
    "publier": ("Publier", "Post"),
    "vous": ("Vous", "You"),
    "commentaire_local": (
        "Votre commentaire s'affiche ici seulement : il n'est jamais envoyé ni enregistré.",
        "Your comment only shows up here: it is never sent or stored.",
    ),
    "plus_de": ("Plus de {nom}", "More from {nom}"),
    "voisines": ("Publications voisines", "Nearby posts"),
    "publications": ("publications", "posts"),
    "publication": ("publication", "post"),
    "abonnes": ("abonnés", "followers"),
    "recentes": ("Publications récentes", "Recent posts"),
    "rechercher": ("Rechercher un auteur ou une étiquette sur cette page", "Search this page for an author or a tag"),
    "exemple_recherche": ("mer, renard…", "sea, fox…"),
    "aucun_resultat": ("Aucun résultat sur cette page.", "No results on this page."),
    "aucune_photo": ("Aucune photo de cette page ne correspond.", "No photo on this page matches."),
    "auteurs": ("Auteurs", "Authors"),
    "etiquettes": ("Étiquettes", "Tags"),
    "pied": (
        "Réseau social fictif : personnes, publications et commentaires sont inventés.",
        "A fictional social network: people, posts and comments are made up.",
    ),
    "session": ("Session d'observation", "Observation session"),
    "recherche": ("Recherche", "Research"),
    "en_cours": (
        "Session d'observation en cours : votre navigation sur ce site est enregistrée. Gardez l'onglet visible.",
        "Observation session in progress: your browsing on this site is being recorded. Keep this tab visible.",
    ),
    "ma_session": ("Ma session", "My session"),
    "terminer": ("Terminer ma session", "End my session"),
    "sans_participer": (
        "Site fictif. Vous visitez sans participer : rien n'est relevé sur vous, hors le journal technique des erreurs décrit dans {notice}.",
        "Fictional site. You are browsing without taking part: nothing is collected about you, apart from the technical error log described in {notice}.",
    ),
    "la_notice": ("la notice", "the notice"),
    "participer": ("Participer à la recherche", "Take part in the study"),
    "autre_site": ("Autre site : {nom}", "Other site: {nom}"),
    # Dessin et crédits (14/11/2026).
    "page_sur": ("Page {n} sur {total}", "Page {n} of {total}"),
    "vers_explorer": ("Continuer dans Explorer", "Keep going in Explore"),
    "vers_fil": ("Revenir au fil", "Back to the feed"),
    "a_decouvrir": ("À découvrir", "Discover"),
    "ecrire": ("Écrire un commentaire…", "Write a comment…"),
    "a_l_instant": ("à l'instant", "just now"),
    "credits": ("Crédits des photos", "Photo credits"),
    "credits_intro": (
        "Les photos de {marque} sont de vraies photos, publiées sous licence libre par leurs auteurs sur Wikimedia Commons. Les comptes qui les «\u00a0publient\u00a0» ici sont fictifs.",
        "The photos on {marque} are real photos, shared under a free licence by their authors on Wikimedia Commons. The accounts that “post” them here are fictional.",
    ),
    "credit_ligne": ("Photo\u00a0: {auteur} · {licence} · ", "Photo: {auteur} · {licence} · "),
    "credit_lien": ("crédits", "credits"),
    "credit_auteur": ("Auteur\u00a0: ", "Author: "),
    "credit_licence": ("Licence\u00a0: ", "Licence: "),
    "credit_origine": ("Voir la page d'origine", "View the original page"),
    "pages_credits": ("Pages des crédits", "Credit pages"),
}
# Mention `modifie` du manifeste, traduite ; une valeur inconnue s'affiche telle quelle.
MODIFICATIONS: dict[str, Texte] = {"redimensionnée": ("Image redimensionnée", "Image resized")}
# Teinte de chaque étiquette (tesselle de couleur des puces, bandeau de la page d'étiquette) : six verres de mosaïque.
TONS = (226, 40, 168, 350, 22, 272)  # smalt, or, vert-de-gris, grenat, ocre, améthyste (teintes HSL)
TON_DES_ETIQUETTES: dict[str, int] = {
    "mer": 0,
    "lac": 0,
    "lacs": 0,
    "ciel": 0,
    "calme": 0,
    "objets": 1,
    "animaux": 1,
    "domestiques": 1,
    "lumiere": 1,
    "matin": 1,
    "dimanche": 1,
    "foret": 2,
    "plantes": 2,
    "paysage": 2,
    "balade": 2,
    "saison": 2,
    "fleurs": 3,
    "soir": 3,
    "couleurs": 3,
    "cuisine": 4,
    "desert": 4,
    "routes": 4,
    "voyage": 4,
    "texture": 4,
    "sauvages": 4,
    "montagne": 5,
    "ville": 5,
    "architecture": 5,
    "details": 5,
    "minimal": 5,
}


def _t(texte: Texte, langue: str) -> str:
    return texte[1] if langue == "en" else texte[0]


def _ui(cle: str, langue: str, **valeurs: object) -> str:
    """Texte de l'interface, déjà échappé (les valeurs le sont aussi)."""
    return escape(_t(T[cle], langue)).format(**{k: escape(str(v)) for k, v in valeurs.items()})


# --- Photos ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Photo:
    """Une photo du manifeste. `largeur` et `hauteur` sont celles du fichier « 1080 » (le plus grand)."""

    id: str
    sujet: str
    largeur: int
    hauteur: int
    auteur: str = ""  # crédit
    licence: str = ""
    origine: str | None = None  # page de la photo sur Commons, pour la page de crédits
    titre: str = ""  # nom du fichier sur Commons
    licence_url: str | None = None  # texte de la licence (absent pour le domaine public)
    modifie: str = ""  # ce qui a été changé (« redimensionnée »)

    def fichier(self, taille: int) -> str:
        return f"{self.id}-{taille}.jpg"

    def dimensions(self, taille: int) -> tuple[int, int]:
        """Dimensions réelles du fichier `taille` : le manifeste donne celles du grand fichier, le petit borne le grand
        côté à `taille` sans jamais agrandir. Elles réservent la place de l'image et donnent les largeurs du `srcset`."""
        echelle = min(1.0, taille / max(self.largeur, self.hauteur))
        return max(1, round(self.largeur * echelle)), max(1, round(self.hauteur * echelle))

    @property
    def portrait(self) -> bool:
        """Portrait ou carré : une case haute dans la mosaïque."""
        return self.largeur < self.hauteur * 1.05


def charger_photos(dossier: Path) -> tuple[Photo, ...]:
    """Photos du manifeste de `dossier`. Erreur claire si le manifeste est illisible, vide, ou si une photo a un
    identifiant hors de `RE_IDENTIFIANT_PHOTO` ou un fichier manquant : le site ne démarre pas à moitié."""
    fichier = dossier / "manifeste.json"
    try:
        entrees = json.loads(fichier.read_text(encoding="utf-8"))["photos"]
        photos = tuple(
            Photo(
                id=str(e["id"]),
                sujet=str(e["sujet"]),
                largeur=int(e["largeur"]),
                hauteur=int(e["hauteur"]),
                auteur=str(e.get("auteur") or ""),
                licence=str(e.get("licence") or ""),
                origine=str(e["origine"]) if e.get("origine") else None,
                titre=str(e.get("titre") or ""),
                licence_url=str(e["licence_url"]) if e.get("licence_url") else None,
                modifie=str(e.get("modifie") or ""),
            )
            for e in entrees
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as erreur:
        raise ValueError(f"{fichier} illisible : {erreur!r}") from erreur
    if not photos:
        raise ValueError(f"{fichier} : aucune photo, il en faut au moins une")
    if len({p.id for p in photos}) != len(photos):
        raise ValueError(f"{fichier} : identifiant de photo en double")
    for photo in photos:
        if not RE_IDENTIFIANT_PHOTO.fullmatch(photo.id) or photo.largeur <= 0 or photo.hauteur <= 0:
            raise ValueError(f"{fichier} : photo invalide ({photo.id!r})")
        for taille in TAILLES_PHOTO:
            if not (dossier / photo.fichier(taille)).is_file():
                raise ValueError(f"{fichier} : fichier manquant {photo.fichier(taille)}")
    return photos


def fichiers(photos: tuple[Photo, ...]) -> frozenset[str]:
    """Liste blanche des fichiers servis sous /lab/social/photos/ : rien d'autre du dossier."""
    return frozenset(p.fichier(t) for p in photos for t in TAILLES_PHOTO)


def lien_de_credit(adresse: str | None) -> str | None:
    """Adresse d'un lien de crédit, ou None : http(s) seulement, hôte exactement dans HOTES_CREDITS, sans port ni
    identifiants, toujours rendue en https. Un manifeste qui pointerait ailleurs ne produit aucun lien."""
    if not adresse:
        return None
    try:
        morceaux = urlsplit(adresse.strip())
        port = morceaux.port
    except ValueError:
        return None
    if morceaux.scheme not in ("http", "https") or morceaux.hostname not in HOTES_CREDITS:
        return None
    if port is not None or morceaux.username is not None or morceaux.password is not None:
        return None
    return urlunsplit(("https", morceaux.hostname, morceaux.path, morceaux.query, ""))


def titre_affiche(titre: str) -> str:
    """Titre d'une photo pour la page de crédits : le nom du fichier sur Commons, sans son extension."""
    return re.sub(r"\.(?:jpe?g|png|tiff?)$", "", titre, flags=re.I).replace("_", " ").strip()


# --- Univers -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Auteur:
    pseudonyme: str
    nom: str
    bio: Texte
    teinte: int  # couleur de l'avatar
    forme: int  # motif de l'avatar
    abonnes: int


@dataclass(frozen=True)
class Commentaire:
    auteur: str  # pseudonyme
    texte: Texte


@dataclass(frozen=True)
class Publication:
    identifiant: str
    auteur: str  # pseudonyme
    photo: Photo
    legende: Texte
    etiquettes: tuple[str, ...]
    aimes: int
    commentaires: tuple[Commentaire, ...]
    date: str  # ISO, à la minute


@dataclass(frozen=True)
class Univers:
    auteurs: tuple[Auteur, ...]
    publications: tuple[Publication, ...]  # de la plus récente à la plus ancienne : l'ordre du fil
    exploration: tuple[str, ...]  # identifiants, dans l'ordre de la page « explorer »
    libelles: dict[str, Texte]  # étiquettes utilisées → libellé
    photos: tuple[Photo, ...] = ()  # tout le manifeste, dans son ordre : la page de crédits
    _auteurs: dict[str, Auteur] = field(default_factory=dict, compare=False, repr=False)
    _publications: dict[str, Publication] = field(default_factory=dict, compare=False, repr=False)
    _rang_photo: dict[str, int] = field(default_factory=dict, compare=False, repr=False)

    def __post_init__(self) -> None:
        self._auteurs.update((a.pseudonyme, a) for a in self.auteurs)
        self._publications.update((p.identifiant, p) for p in self.publications)
        self._rang_photo.update((p.id, rang) for rang, p in enumerate(self.photos))

    def page_de_credit(self, photo: Photo) -> int:
        """Page de /lab/social/credits où figure la photo."""
        return self._rang_photo.get(photo.id, 0) // PAR_PAGE_GRILLE + 1

    def auteur(self, pseudonyme: str) -> Auteur | None:
        return self._auteurs.get(pseudonyme)

    def publication(self, identifiant: str) -> Publication | None:
        return self._publications.get(identifiant)

    def de_l_auteur(self, pseudonyme: str) -> list[Publication]:
        return [p for p in self.publications if p.auteur == pseudonyme]

    def avec_etiquette(self, etiquette: str) -> list[Publication]:
        return [p for p in self.publications if etiquette in p.etiquettes]


def _replier(texte: str) -> str:
    """Minuscules sans accents : clé de recherche et base des identifiants."""
    return "".join(c for c in unicodedata.normalize("NFKD", texte.lower()) if not unicodedata.combining(c))


def etiquette_du_sujet(sujet: str) -> str:
    """Étiquette d'un sujet du manifeste : connue, sinon tirée du sujet en ASCII (`divers` s'il n'en reste rien)."""
    replie = _replier(sujet).strip()
    if replie in SUJETS:
        return SUJETS[replie]
    return re.sub(r"[^a-z0-9]+", "-", replie).strip("-")[:40].strip("-") or "divers"


def _identifiant(alea: random.Random, pris: set[str]) -> str:
    while True:
        ident = "".join(alea.choice(ALPHABET) for _ in range(7))
        if ident not in pris:
            pris.add(ident)
            return ident


def nb_pages(nombre: int, par_page: int) -> int:
    return max(1, -(-nombre // par_page))


def generer(graine: int, taille: int, photos: tuple[Photo, ...]) -> Univers:
    """L'univers de la graine : toujours le même pour les mêmes arguments. Une publication par photo à tour de rôle
    (ordre tiré de la graine), donc chaque photo sert dès que `taille` atteint leur nombre."""
    if not photos:
        raise ValueError("il faut au moins une photo")
    alea = random.Random(graine)
    nb_auteurs = min(len(AUTEURS), max(1, -(-taille // 5)))
    auteurs = tuple(
        Auteur(p, n, alea.choice(BIOS), alea.randrange(360), alea.randrange(4), alea.randint(12, 4800))
        for p, n in alea.sample(AUTEURS, nb_auteurs)
    )
    ordre_photos = list(photos)
    alea.shuffle(ordre_photos)
    libelles: dict[str, Texte] = {}
    pris: set[str] = set()
    publications = []
    instant = ORIGINE_DATES
    for i in range(taille):
        a = random.Random(graine * 1_000_003 + i)  # sa propre graine : indépendante de la taille demandée
        auteur = auteurs[i].pseudonyme if i < nb_auteurs else a.choice(auteurs).pseudonyme  # chacun publie
        photo = ordre_photos[i % len(ordre_photos)]
        sujet = etiquette_du_sujet(photo.sujet)
        libelles.setdefault(sujet, ETIQUETTES.get(sujet, (photo.sujet, photo.sujet)))
        etiquettes = (sujet, *a.sample([e for e in AMBIANCES if e != sujet], 2))
        for e in etiquettes[1:]:
            libelles.setdefault(e, ETIQUETTES[e])
        autres = [x.pseudonyme for x in auteurs if x.pseudonyme != auteur]
        commentaires = tuple(
            Commentaire(a.choice(autres), a.choice(COMMENTAIRES)) for _ in range(a.randint(0, 4) if autres else 0)
        )
        instant -= timedelta(hours=a.randint(2, 30), minutes=a.randint(0, 59))
        publications.append(
            Publication(
                identifiant=_identifiant(a, pris),
                auteur=auteur,
                photo=photo,
                legende=a.choice(LEGENDES.get(sujet, ()) + LEGENDES_GENERIQUES),
                etiquettes=etiquettes,
                aimes=max(1, min(99_999, round(a.lognormvariate(4.0, 1.1)))),
                commentaires=commentaires,
                date=instant.isoformat(timespec="minutes"),
            )
        )
    exploration = [p.identifiant for p in publications]
    alea.shuffle(exploration)
    return Univers(auteurs, tuple(publications), tuple(exploration), libelles, tuple(photos))


# --- Morceaux de page --------------------------------------------------------------------------
#
# Dessin (14/11/2026) : l'identité tient dans la tesselle (« Mosaïk ») : emblème de quatre tesselles, grilles en vraie
# mosaïque (bandes composées selon le format des photos), bandeaux de profil et d'étiquette en tesselles générées,
# « j'aime » qui éclate en petites tesselles. Tout le style est dans static/social.css ; les SVG de la page n'ont que
# des attributs de présentation (fill, transform), jamais d'attribut `style`.


def _nombre(n: int, langue: str) -> str:
    return f"{n:,}" if langue == "en" else f"{n:,}".replace(",", " ")


def _date(iso: str, langue: str) -> str:
    d = datetime.fromisoformat(iso)
    mois = _t(MOIS[d.month - 1], langue)
    return f"{mois} {d.day}, {d.year}" if langue == "en" else f"{d.day} {mois} {d.year}"


def initiales(nom: str) -> str:
    mots = [m.split("'")[-1] for m in nom.split() if m.lower() not in ("de", "du", "et")]
    return "".join(m[0] for m in mots[:2] if m).upper()


def avatar(a: Auteur, taille: int) -> str:
    """Avatar dessiné dans la page (SVG en ligne, sans style ni adresse ni identifiant) : un carré de couleur, un
    motif, les initiales. La feuille de style en fait une tesselle aux coins arrondis (`.avatar`)."""
    fond = f"hsl({a.teinte} 48% 52%)"
    clair = f"hsl({(a.teinte + 40) % 360} 70% 80%)"
    motif = (
        f'<circle cx="31" cy="9" r="9" fill="{clair}" opacity=".7"/>',
        f'<rect x="-6" y="26" width="52" height="20" fill="{clair}" opacity=".55" transform="rotate(-12 20 36)"/>',
        f'<polygon points="0,40 14,22 28,40" fill="{clair}" opacity=".6"/>',
        f'<path d="M0 30q10-8 20 0t20 0v10H0z" fill="{clair}" opacity=".6"/>',
    )[a.forme % 4]
    return (
        f'<svg class="avatar" width="{taille}" height="{taille}" viewBox="0 0 40 40" aria-hidden="true" focusable="false">'
        f'<rect width="40" height="40" fill="{fond}"/>{motif}'
        f'<text x="20" y="25" text-anchor="middle" font-family="sans-serif" font-size="14" font-weight="700" fill="#fff">{escape(initiales(a.nom))}</text>'
        "</svg>"
    )


# Emblème : quatre tesselles posées à la main (couleurs dans la feuille de style, qui suit le thème).
EMBLEME = (
    '<svg class="embleme" width="30" height="30" viewBox="0 0 32 32" aria-hidden="true" focusable="false">'
    '<rect class="t-smalt" x="2.5" y="2.5" width="12.5" height="12.5" rx="2.6" transform="rotate(-5 8.75 8.75)"/>'
    '<rect class="t-or" x="17" y="3" width="12" height="12" rx="2.6"/>'
    '<rect class="t-vert" x="3" y="17" width="12" height="12" rx="2.6"/>'
    '<rect class="t-grenat" x="17.5" y="17.5" width="11.5" height="11.5" rx="2.6" transform="rotate(8 23.25 23.25)"/>'
    "</svg>"
)
COEUR = '<svg class="coeur" width="22" height="22" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 20.5 4.2 12.9a4.9 4.9 0 0 1 0-7 4.9 4.9 0 0 1 6.9 0l.9.9.9-.9a4.9 4.9 0 0 1 6.9 0 4.9 4.9 0 0 1 0 7Z"/></svg>'
BULLE = '<svg class="icone" width="20" height="20" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M5.5 4h13A2.5 2.5 0 0 1 21 6.5v8a2.5 2.5 0 0 1-2.5 2.5H12l-4.6 3.4c-.5.4-1.2 0-1.2-.6V17h-.7A2.5 2.5 0 0 1 3 14.5v-8A2.5 2.5 0 0 1 5.5 4Z"/></svg>'
LOUPE = '<svg class="icone" width="20" height="20" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/></svg>'
ECLATS = '<span class="eclats" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i></span>'


def _ton(etiquette: str) -> int:
    """Rang de la teinte d'une étiquette dans TONS : fixé pour les étiquettes connues, tiré du nom sinon."""
    return TON_DES_ETIQUETTES.get(etiquette, zlib.crc32(etiquette.encode()) % len(TONS))


def banniere(graine: str, teinte: int) -> str:
    """Bandeau d'en-tête en tesselles (profil, étiquette) : 22 × 5 tesselles irrégulières dans une même teinte, une
    onde de clarté, quelques tesselles d'or. Tiré d'un générateur à part, seedé par une chaîne (jamais `hash()`, salé
    à chaque processus) : la même page octet pour octet à chaque démarrage, sans toucher au tirage de l'univers. Le
    joint suit le thème (`currentColor`)."""
    alea = random.Random(f"banniere/{graine}")
    largeur, hauteur, cote, joint = 704, 160, 32, 3
    phase = alea.uniform(0, 2 * math.pi)
    colonnes, rangees = largeur // cote, hauteur // cote
    tesselles = []
    for r in range(rangees):
        for c in range(colonnes):
            x, y = c * cote, r * cote
            coins = ((joint, joint), (cote - joint, joint), (cote - joint, cote - joint), (joint, cote - joint))
            points = " ".join(
                f"{x + dx + alea.uniform(-2, 2):.0f},{y + dy + alea.uniform(-2, 2):.0f}" for dx, dy in coins
            )
            if alea.random() < 0.035:
                couleur = f"hsl({40 + alea.randint(-4, 4)} 70% {alea.randint(55, 63)}%)"
            else:
                onde = math.sin(c / colonnes * 2.3 * math.pi + phase + r * 0.6)
                clarte = round(55 + 13 * onde + alea.uniform(-5, 5))
                couleur = f"hsl({(teinte + alea.randint(-9, 9)) % 360} {alea.randint(34, 54)}% {clarte}%)"
            tesselles.append(f'<polygon points="{points}" fill="{couleur}"/>')
    return (
        f'<svg class="banniere-motif" viewBox="0 0 {largeur} {hauteur}" preserveAspectRatio="xMidYMid slice"'
        f' aria-hidden="true" focusable="false"><rect width="{largeur}" height="{hauteur}" fill="currentColor"/>'
        f"{''.join(tesselles)}</svg>"
    )


def _lien_auteur(a: Auteur, taille_avatar: int | None = None, classe: str = "auteur") -> str:
    image = avatar(a, taille_avatar) if taille_avatar else ""
    return f'<a class="{classe}" href="/lab/social/u/{escape(a.pseudonyme)}">{image}<span class="auteur-nom">{escape(a.nom)}</span></a>'


def _photo(
    photo: Photo,
    taille: int,
    texte: str,
    paresseuse: bool,
    tailles: str | None = None,
    prioritaire: bool = False,
) -> str:
    """Une image : dimensions réelles du fichier (la place est réservée avant le chargement) ; avec `tailles`, un
    `srcset` des deux fichiers (le navigateur prend le plus petit qui suffit) ; sans, le fichier `taille` seul."""
    largeur, hauteur = photo.dimensions(taille)
    attributs = f' width="{largeur}" height="{hauteur}"'
    if tailles:
        jeu = ", ".join(
            f"/lab/social/photos/{escape(photo.fichier(t))} {photo.dimensions(t)[0]}w" for t in sorted(TAILLES_PHOTO)
        )
        attributs += f' srcset="{jeu}" sizes="{tailles}"'
    if paresseuse:
        attributs += ' loading="lazy"'
    elif prioritaire:
        attributs += ' fetchpriority="high"'
    return (
        f'<img class="photo" src="/lab/social/photos/{escape(photo.fichier(taille))}" alt="{escape(texte)}"'
        f'{attributs} decoding="async">'
    )


def _puce(u: Univers, e: str, langue: str) -> str:
    """Une étiquette : une tesselle de sa couleur et son nom."""
    return (
        f'<a class="etiquette ton-{_ton(e)}" href="/lab/social/t/{escape(e)}">'
        f'<span class="tesselle" aria-hidden="true"></span>{escape(_t(u.libelles[e], langue))}</a>'
    )


def _etiquettes(u: Univers, p: Publication, langue: str) -> str:
    return f'<p class="etiquettes">{"".join(_puce(u, e, langue) for e in p.etiquettes)}</p>'


def _aime(p: Publication, langue: str) -> str:
    """Bouton « j'aime » : social.js ne change que l'affichage (état, compte), la feuille de style anime le cœur et
    l'éclat de tesselles ; rien n'est envoyé."""
    return (
        f'<button class="aime" type="button" aria-pressed="false" data-aime="{p.aimes}">'
        f'<span class="aime-icone">{COEUR}{ECLATS}</span>'
        f'<span class="aime-compte">{_nombre(p.aimes, langue)}</span>'
        f' <span class="aime-libelle">{_ui("j_aime", langue)}</span></button>'
    )


def _date_html(p: Publication, langue: str) -> str:
    return f'<time class="date" datetime="{escape(p.date)}">{escape(_date(p.date, langue))}</time>'


def _carte_fil(u: Univers, p: Publication, langue: str, rang: int) -> str:
    """Carte du fil : la photo d'abord, dans son passe-partout ; puis qui, j'aime, légende, étiquettes, commentaires."""
    ident = escape(p.identifiant)
    a = u.auteur(p.auteur)
    n = len(p.commentaires)
    if n == 0:
        commentaires = _ui("commenter", langue)
    elif n == 1:
        commentaires = _ui("voir_commentaire", langue)
    else:
        commentaires = _ui("voir_commentaires", langue, n=n)
    photo = _photo(
        p.photo,
        1080,
        _t(p.legende, langue),
        paresseuse=rang >= 2,
        tailles="(min-width: 680px) 602px, calc(100vw - 50px)",
    )
    return f"""<article class="publication carte" data-publication="{ident}">
<a class="publication-photo" href="/lab/social/p/{ident}">{photo}</a>
<div class="publication-corps">
<div class="publication-ligne">{_lien_auteur(a, 40)}{_aime(p, langue)}</div>
<p class="legende">{escape(_t(p.legende, langue))}</p>
{_etiquettes(u, p, langue)}
<div class="publication-pied"><a class="commentaires-lien" href="/lab/social/p/{ident}#commentaires">{BULLE}<span>{commentaires}</span></a>{_date_html(p, langue)}</div>
</div>
</article>"""


def _vignette(u: Univers, p: Publication, langue: str, cherchable: bool = False, tailles: str | None = None) -> str:
    """Vignette d'une grille : le petit fichier ; avec `tailles` (grande case d'une mosaïque pleine largeur), un
    `srcset` des deux fichiers, pour qu'elle reste nette sur un écran dense."""
    attributs = ""
    if cherchable:
        a = u.auteur(p.auteur)
        cle = " ".join([a.pseudonyme, a.nom, *p.etiquettes, *(_t(u.libelles[e], langue) for e in p.etiquettes)])
        attributs = f' data-cherchable data-texte="{escape(_replier(cle))}"'
    return (
        f'<a class="vignette" href="/lab/social/p/{escape(p.identifiant)}"{attributs}>'
        f"{_photo(p.photo, 480, _t(p.legende, langue), paresseuse=True, tailles=tailles)}"
        f'<span class="vignette-info">{COEUR}{_nombre(p.aimes, langue)}</span></a>'
    )


# Bandes de la mosaïque : nom → nombre de vignettes. La cellule de base est en 3:2 ; un paysage occupe 1×1 ou 2×2
# cellules, un portrait 1×2 : chaque photo garde à peu près son format (recadrage faible) et aucune bande n'a de trou
# (sauf `p`, un portrait tout seul : une liste d'une seule photo). La feuille de style place les vignettes.
TAILLES_BANDE: dict[str, int] = {
    "solo": 1,
    "duo": 2,
    "trio-g": 3,
    "trio-d": 3,
    "l-p": 2,
    "p-l": 2,
    "ll-p": 3,
    "p-ll": 3,
    "l-pp": 3,
    "pp-l": 3,
    "pp": 2,
    "ppp": 3,
    "p-l-p": 3,
    "p": 1,
}
RYTHME_BANDES = ("trio-g", "duo", "trio-d", "duo")  # suite de paysages : grand à gauche, deux, grand à droite, deux
# Début de la suite des formats (P : portrait, L : paysage) → bande qui le prend ; essayés dans l'ordre.
MOTIFS_BANDE = (
    ("PPP", "ppp"),
    ("PLP", "p-l-p"),
    ("PLL", "p-ll"),
    ("PPL", "pp-l"),
    ("PP", "pp"),
    ("PL", "p-l"),
    ("LLP", "ll-p"),
    ("LPP", "l-pp"),
    ("LP", "l-p"),
)
# Bande d'une vignette de moins, quand la bande choisie laisserait un portrait tout seul en fin de liste.
RACCOURCIS = {
    "trio-g": "duo",
    "trio-d": "duo",
    "ll-p": "duo",
    "p-ll": "p-l",
    "pp-l": "pp",
    "l-pp": "l-p",
    "ppp": "pp",
    "p-l-p": "p-l",
}


def composer_bandes(portraits: Sequence[bool]) -> list[tuple[str, int]]:
    """Découpe une suite de vignettes (True : portrait ou carré) en bandes, dans l'ordre, chaque vignette une fois :
    [(nom de bande, nombre de vignettes), …]. Fonction pure : la mosaïque ne dépend que des formats."""
    bandes: list[tuple[str, int]] = []
    i, tour = 0, 0
    while i < len(portraits):
        formats = "".join("P" if p else "L" for p in portraits[i : i + 3])
        nom = next((n for motif, n in MOTIFS_BANDE if formats.startswith(motif)), None)
        if nom is None:
            if formats in ("P", "L"):
                nom = "p" if formats == "P" else "solo"
            elif formats == "LL" or len(portraits) - i == 4:
                nom = "duo"  # quatre paysages : deux et deux plutôt que trois et un seul
            else:  # trois paysages ou plus : le rythme
                nom = RYTHME_BANDES[tour % len(RYTHME_BANDES)]
                tour += 1
        if len(portraits) - i - TAILLES_BANDE[nom] == 1 and portraits[-1] and nom in RACCOURCIS:
            nom = RACCOURCIS[nom]  # jamais un portrait seul en bout de mosaïque
        bandes.append((nom, TAILLES_BANDE[nom]))
        i += TAILLES_BANDE[nom]
    return bandes


# Grandes cases de chaque bande (rang → genre) : au moins deux fois la petite case, donc trop grandes pour le seul
# fichier de 480 pixels sur un écran dense. Les autres cases gardent le petit fichier.
GRANDES_CASES: dict[str, dict[int, str]] = {
    "solo": {0: "solo"},
    "duo": {},
    "trio-g": {0: "grande"},
    "trio-d": {2: "grande"},
    "l-p": {0: "grande", 1: "portrait"},
    "p-l": {0: "portrait", 1: "grande"},
    "ll-p": {2: "portrait"},
    "p-ll": {0: "portrait"},
    "l-pp": {0: "grande", 1: "portrait", 2: "portrait"},
    "pp-l": {0: "portrait", 1: "portrait", 2: "grande"},
    "p-l-p": {0: "portrait", 1: "grande", 2: "portrait"},
    "pp": {0: "portrait", 1: "portrait"},
    "ppp": {0: "portrait", 1: "portrait", 2: "portrait"},
    "p": {0: "portrait"},
}
TAILLES_CASE = {
    "solo": "(min-width: 1024px) 1000px, 100vw",
    "grande": "(min-width: 1024px) 680px, 66vw",
    "portrait": "(min-width: 1024px) 340px, 50vw",
}


def _grille(
    u: Univers, publications: list[Publication], langue: str, cherchable: bool = False, pleine_largeur: bool = False
) -> str:
    """Mosaïque de vignettes : des bandes composées selon le format des photos (voir `composer_bandes`). En pleine
    largeur (Explorer, profil, étiquette), les grandes cases reçoivent aussi le grand fichier (`srcset`)."""
    morceaux, i = [], 0
    for nom, nombre in composer_bandes([p.photo.portrait for p in publications]):
        grandes = GRANDES_CASES[nom] if pleine_largeur else {}
        vignettes = "".join(
            _vignette(u, p, langue, cherchable, TAILLES_CASE.get(grandes.get(rang, "")))
            for rang, p in enumerate(publications[i : i + nombre])
        )
        morceaux.append(f'<div class="bande bande-{nom}">{vignettes}</div>')
        i += nombre
    return f'<div class="mosaique">{"".join(morceaux)}</div>'


def _etat_page(page: int, total: int, langue: str) -> str:
    return f'<p class="page-n">{_ui("page_sur", langue, n=page, total=total)}</p>' if total > 1 else ""


def _suite(chemin: str, page: int, total: int, langue: str) -> str:
    """« Voir plus » vers la page suivante ; à la dernière, une autre façon de continuer."""
    if page < total:
        lien = f'<a class="voir-plus" rel="next" href="{chemin}?page={page + 1}">{_ui("voir_plus", langue)}</a>'
    else:
        ailleurs = (
            ("/lab/social/fil", "vers_fil")
            if chemin == "/lab/social/explorer"
            else ("/lab/social/explorer", "vers_explorer")
        )
        lien = f'<p class="fin">{_ui("fin", langue)}</p><a class="voir-plus" href="{ailleurs[0]}">{_ui(ailleurs[1], langue)}</a>'
    return f'<nav class="suite" aria-label="{_ui("pagination", langue)}">{lien}</nav>'


def bandeau(langue: str, csrf: str | None) -> str:
    """Bandeau de chaque page, dans la langue de la page. Avec un jeton anti-CSRF (session en cours) : « Ma session »
    et le bouton pour terminer, seul formulaire du réseau social ; sans : invitation à participer. Toujours un lien
    vers l'autre site de démonstration."""
    autre = f'<a class="autre-site" href="/lab/vitrine">{_ui("autre_site", langue, nom=MARQUE_VITRINE)}</a>'
    if csrf is not None:
        return f"""<aside class="session-publique en-cours" aria-label="{_ui("session", langue)}"><div class="conteneur">
<p><span class="pastille" aria-hidden="true"></span>{_ui("en_cours", langue)}</p>
<div class="actions"><a href="/session">{_ui("ma_session", langue)}</a><form class="en-ligne" method="post" action="/session/terminer">
<input type="hidden" name="csrf" value="{escape(csrf)}">
<button class="bouton-plein" type="submit">{_ui("terminer", langue)}</button>
</form>{autre}</div>
</div></aside>"""
    notice = f'<a href="/{"en" if langue == "en" else "fr"}/information">{_ui("la_notice", langue)}</a>'
    return f"""<aside class="session-publique" aria-label="{_ui("recherche", langue)}"><div class="conteneur">
<p>{escape(_t(T["sans_participer"], langue)).format(notice=notice)}</p>
<div class="actions"><a href="/">{_ui("participer", langue)}</a>{autre}</div>
</div></aside>"""


def _gabarit(
    langue: str, titre: str, classe: str, corps: str, jeton: str, habillage: Habillage, actif: str | None = None
) -> str:
    """Gabarit commun. Pendant une session, jeton et observateur du labo chargés comme sur une page de la vitrine
    publique (`vitrine._gabarit`) ; le script et la feuille du réseau social sont servis hors de /lab/. `actif` : la
    rubrique de la navigation où l'on se trouve (« fil » ou « explorer »), marquée `aria-current`."""
    metas = f'<meta name="sl-session" content="{escape(jeton)}">\n' if habillage.observateur else ""
    metas += '<meta name="sl-sans-tiers" content="1">\n' if habillage.sans_tiers else ""
    observateur = '<script type="module" src="/lab/static/observateur.js"></script>\n' if habillage.observateur else ""
    bandeau_page = f"{habillage.bandeau}\n" if habillage.bandeau else ""
    nom, _, suffixe = MARQUE.partition(" ")
    rubriques = "".join(
        f'<a href="/lab/social/{cle}"{' aria-current="page"' if cle == actif else ""}>{_ui(cle, langue)}</a>'
        for cle in ("fil", "explorer")
    )
    return f"""<!doctype html>
<html lang="{"en" if langue == "en" else "fr"}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#edf0f3" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#121a2b" media="(prefers-color-scheme: dark)">
{metas}<title>{escape(titre)} — {escape(MARQUE)}</title>
<link rel="stylesheet" href="/public/static/social.css">
</head>
<body class="social {classe}">
<header class="entete"><div class="conteneur">
<a class="marque" href="/lab/social/fil">{EMBLEME}<span class="marque-nom">{escape(nom)}</span> <span class="marque-demo">{escape(suffixe)}</span></a>
<nav class="navigation" aria-label="{_ui("navigation", langue)}">{rubriques}</nav>
</div></header>
{bandeau_page}<main class="conteneur principal">
{corps}
</main>
<footer class="pied"><div class="conteneur">
<p class="pied-marque">{EMBLEME}<span>{escape(MARQUE)}</span></p>
<p>{_ui("pied", langue)}</p>
<p><a href="/lab/social/credits">{_ui("credits", langue)}</a></p>
</div></footer>
{observateur}<script type="module" src="/public/static/social.js"></script>
</body>
</html>"""


def _titre_pagine(cle: str, page: int, langue: str) -> str:
    titre = _t(T[cle], langue)
    return titre if page == 1 else f"{titre} — {_t(T['page'], langue)} {page}"


def _liste_etiquettes(u: Univers, etiquettes: Sequence[str], langue: str, cherchable: bool = False) -> str:
    elements = []
    for e in etiquettes:
        cle = (
            f' data-cherchable data-texte="{escape(_replier(e + " " + _t(u.libelles[e], langue)))}"'
            if cherchable
            else ""
        )
        elements.append(f"<li{cle}>{_puce(u, e, langue)}</li>")
    return "".join(elements)


def _liste_auteurs(auteurs: Sequence[Auteur], taille: int, classe: str = "auteur", cherchable: bool = False) -> str:
    elements = []
    for a in auteurs:
        cle = f' data-cherchable data-texte="{escape(_replier(a.pseudonyme + " " + a.nom))}"' if cherchable else ""
        elements.append(f"<li{cle}>{_lien_auteur(a, taille, classe)}</li>")
    return "".join(elements)


# --- Pages -------------------------------------------------------------------------------------

HABILLAGE_PUBLIC = Habillage(observateur=False, sans_tiers=True)


def page_fil(jeton: str, u: Univers, page: int, langue: str, habillage: Habillage = HABILLAGE_PUBLIC) -> str:
    """Le fil : PAR_PAGE_FIL publications, de la plus récente à la plus ancienne, et « Voir plus ». Sur un grand
    écran, une colonne « À découvrir » (étiquettes les plus utilisées, auteurs) donne d'autres chemins."""
    total = nb_pages(len(u.publications), PAR_PAGE_FIL)
    morceau = u.publications[(page - 1) * PAR_PAGE_FIL : page * PAR_PAGE_FIL]
    cartes = "\n".join(_carte_fil(u, p, langue, rang) for rang, p in enumerate(morceau))
    usage = Counter(e for p in u.publications for e in p.etiquettes)
    populaires = sorted(u.libelles, key=lambda e: (-usage[e], _replier(_t(u.libelles[e], langue))))[:12]
    auteurs = sorted(u.auteurs, key=lambda a: -a.abonnes)[:6]
    corps = f"""<div class="fil-mise">
<div class="fil-colonne">
<div class="titre-ligne"><h1 class="titre-page">{_ui("fil", langue)}</h1>{_etat_page(page, total, langue)}</div>
<div class="fil">
{cartes}
</div>
{_suite("/lab/social/fil", page, total, langue)}
</div>
<aside class="a-cote" aria-label="{_ui("a_decouvrir", langue)}">
<h2 class="titre-bloc">{_ui("etiquettes", langue)}</h2>
<ul class="puces">{_liste_etiquettes(u, populaires, langue)}</ul>
<h2 class="titre-bloc">{_ui("auteurs", langue)}</h2>
<ul class="auteurs-liste auteurs-colonne">{_liste_auteurs(auteurs, 40)}</ul>
</aside>
</div>"""
    return _gabarit(langue, _titre_pagine("fil", page, langue), "page-fil", corps, jeton, habillage, "fil")


def page_explorer(jeton: str, u: Univers, page: int, langue: str, habillage: Habillage = HABILLAGE_PUBLIC) -> str:
    """La mosaïque (PAR_PAGE_GRILLE vignettes par page), avec une recherche qui filtre dans la page (auteurs,
    étiquettes, vignettes)."""
    total = nb_pages(len(u.exploration), PAR_PAGE_GRILLE)
    morceau = [u.publication(i) for i in u.exploration[(page - 1) * PAR_PAGE_GRILLE : page * PAR_PAGE_GRILLE]]
    auteurs = sorted(u.auteurs, key=lambda a: _replier(a.nom))
    etiquettes = sorted(u.libelles, key=lambda e: _replier(_t(u.libelles[e], langue)))
    corps = f"""<div class="explorer">
<div class="explorer-cote">
<div class="titre-ligne"><h1 class="titre-page">{_ui("explorer", langue)}</h1>{_etat_page(page, total, langue)}</div>
<div class="recherche">
<label for="recherche">{_ui("rechercher", langue)}</label>
<div class="recherche-champ">{LOUPE}<input id="recherche" type="search" autocomplete="off" spellcheck="false" placeholder="{_ui("exemple_recherche", langue)}" data-recherche></div>
<p class="recherche-vide" data-recherche-vide hidden>{_ui("aucun_resultat", langue)}</p>
</div>
<section class="listes">
<div class="liste-bloc">
<h2 class="titre-bloc">{_ui("auteurs", langue)}</h2>
<ul class="auteurs-liste auteurs-bande">{_liste_auteurs(auteurs, 52, "auteur auteur-tuile", cherchable=True)}</ul>
</div>
<div class="liste-bloc">
<h2 class="titre-bloc">{_ui("etiquettes", langue)}</h2>
<ul class="puces puces-bande">{_liste_etiquettes(u, etiquettes, langue, cherchable=True)}</ul>
</div>
</section>
</div>
<div class="explorer-mosaique">
{_grille(u, morceau, langue, cherchable=True, pleine_largeur=True)}
<p class="mosaique-vide">{_ui("aucune_photo", langue)}</p>
{_suite("/lab/social/explorer", page, total, langue)}
</div>
</div>"""
    return _gabarit(
        langue, _titre_pagine("explorer", page, langue), "page-explorer", corps, jeton, habillage, "explorer"
    )


def _commentaire(u: Univers, c: Commentaire, langue: str) -> str:
    a = u.auteur(c.auteur)
    return (
        f'<li class="commentaire">{avatar(a, 36)}<div class="commentaire-corps">'
        f'<a class="auteur-nom" href="/lab/social/u/{escape(a.pseudonyme)}">{escape(a.nom)}</a>'
        f'<p class="commentaire-texte">{escape(_t(c.texte, langue))}</p></div></li>'
    )


def page_publication(
    jeton: str, u: Univers, p: Publication, langue: str, habillage: Habillage = HABILLAGE_PUBLIC
) -> str:
    """Une publication : la photo en grand sur sa scène, légende, étiquettes, crédit de la photo, commentaires (et
    une zone de commentaire qui reste dans la page), autres publications de l'auteur, publications voisines."""
    a = u.auteur(p.auteur)
    ident = escape(p.identifiant)
    rang = u.publications.index(p)
    autres = [x for x in u.de_l_auteur(p.auteur) if x != p][:NB_AUTRES]
    debut = max(0, min(rang - NB_VOISINES // 2, len(u.publications) - NB_VOISINES - 1))
    voisines = [x for x in u.publications[debut : debut + NB_VOISINES + 1] if x != p][:NB_VOISINES]
    commentaires = "".join(_commentaire(u, c, langue) for c in p.commentaires)
    aucun = (
        ""
        if p.commentaires
        else f'<p class="aucun-commentaire" data-aucun-commentaire>{_ui("aucun_commentaire", langue)}</p>'
    )
    sections = ""
    if autres:
        sections += f"""<section class="autres">
<h2 class="titre-section"><a href="/lab/social/u/{escape(a.pseudonyme)}">{_ui("plus_de", langue, nom=a.nom)}</a></h2>
{_grille(u, autres, langue)}
</section>
"""
    if voisines:
        sections += f"""<section class="voisines">
<h2 class="titre-section">{_ui("voisines", langue)}</h2>
{_grille(u, voisines, langue)}
</section>
"""
    photo = p.photo
    credit = (
        f'<p class="credit">{_ui("credit_ligne", langue, auteur=photo.auteur, licence=photo.licence)}'
        f'<a href="{adresse_credits(u.page_de_credit(photo))}#photo-{escape(photo.id)}">{_ui("credit_lien", langue)}</a></p>'
    )
    image = _photo(
        photo,
        1080,
        _t(p.legende, langue),
        paresseuse=False,
        tailles="(min-width: 1180px) 1084px, 100vw",
        prioritaire=True,
    )
    corps = f"""<article class="publication publication-seule" data-publication="{ident}">
<figure class="scene scene-{"portrait" if photo.portrait else "paysage"}">{image}</figure>
<div class="publication-mise">
<div class="publication-principal">
<header class="publication-entete">{_lien_auteur(a, 44)}{_aime(p, langue)}</header>
<p class="legende">{escape(_t(p.legende, langue))}</p>
<p class="publication-meta">{_date_html(p, langue)}</p>
{_etiquettes(u, p, langue)}
{credit}
<section class="commentaires" id="commentaires" aria-labelledby="titre-commentaires">
<h2 id="titre-commentaires">{_ui("commentaires", langue)} <span class="compte" data-compte>{len(p.commentaires)}</span></h2>
{aucun}<ul class="commentaires-liste" data-commentaires>{commentaires}</ul>
<div class="zone-commentaire" data-zone-commentaire data-vous="{_ui("vous", langue)}" data-instant="{_ui("a_l_instant", langue)}">
<span class="avatar avatar-vous" aria-hidden="true">{_ui("vous", langue)[:1]}</span>
<div class="zone-champ">
<label for="commentaire">{_ui("ajouter_commentaire", langue)}</label>
<textarea id="commentaire" rows="2" maxlength="300" placeholder="{_ui("ecrire", langue)}" aria-describedby="commentaire-note" data-commentaire></textarea>
<div class="zone-pied"><p class="discret" id="commentaire-note">{_ui("commentaire_local", langue)}</p><button class="bouton-plein publier" type="button" data-publier disabled>{_ui("publier", langue)}</button></div>
</div>
</div>
</section>
</div>
<aside class="publication-cote">
{sections}</aside>
</div>
</article>"""
    return _gabarit(langue, f"{a.nom} — {_t(p.legende, langue)}", "page-publication", corps, jeton, habillage)


def page_profil(jeton: str, u: Univers, a: Auteur, langue: str, habillage: Habillage = HABILLAGE_PUBLIC) -> str:
    """Un profil : bandeau en tesselles de sa couleur, avatar, nom, pseudonyme, bio, chiffres, et ses
    PAR_PAGE_GRILLE publications les plus récentes en mosaïque."""
    publications = u.de_l_auteur(a.pseudonyme)
    unite = "publication" if len(publications) == 1 else "publications"
    corps = f"""<section class="profil">
<div class="banniere">{banniere("u/" + a.pseudonyme, a.teinte)}</div>
<div class="profil-tete">
{avatar(a, 104)}
<div class="profil-texte">
<h1 class="profil-nom">{escape(a.nom)}</h1>
<p class="profil-pseudo">@{escape(a.pseudonyme)}</p>
</div>
</div>
<p class="profil-bio">{escape(_t(a.bio, langue))}</p>
<p class="profil-chiffres"><span><strong>{_nombre(len(publications), langue)}</strong> {_ui(unite, langue)}</span> <span><strong>{_nombre(a.abonnes, langue)}</strong> {_ui("abonnes", langue)}</span></p>
</section>
<h2 class="titre-section">{_ui("recentes", langue)}</h2>
{_grille(u, publications[:PAR_PAGE_GRILLE], langue, pleine_largeur=True)}"""
    return _gabarit(langue, f"{a.nom} (@{a.pseudonyme})", "page-profil", corps, jeton, habillage)


def page_etiquette(jeton: str, u: Univers, etiquette: str, langue: str, habillage: Habillage = HABILLAGE_PUBLIC) -> str:
    """Une étiquette : bandeau en tesselles de sa couleur, son nom, le nombre de publications et les
    PAR_PAGE_GRILLE plus récentes en mosaïque."""
    publications = u.avec_etiquette(etiquette)
    libelle = _t(u.libelles[etiquette], langue)
    unite = "publication" if len(publications) == 1 else "publications"
    ton = _ton(etiquette)
    corps = f"""<section class="etiquette-entete ton-{ton}">
<div class="banniere">{banniere("t/" + etiquette, TONS[ton])}</div>
<h1 class="titre-page"><span class="tesselle" aria-hidden="true"></span>{escape(libelle)}</h1>
<p class="compteur">{_nombre(len(publications), langue)} {_ui(unite, langue)}</p>
</section>
{_grille(u, publications[:PAR_PAGE_GRILLE], langue, pleine_largeur=True)}"""
    return _gabarit(langue, f"#{libelle}", "page-etiquette", corps, jeton, habillage)


def adresse_credits(page: int) -> str:
    """Une adresse par page de crédits : la première sans paramètre (celle du pied de page)."""
    return "/lab/social/credits" if page == 1 else f"/lab/social/credits?page={page}"


def _entree_credit(p: Photo, langue: str) -> str:
    """Une photo sur la page de crédits : vignette, titre, auteur, licence (liée à son texte quand il existe), page
    d'origine, modification. Les deux seuls liens sortants du site, vérifiés par `lien_de_credit`."""
    titre = titre_affiche(p.titre) or p.id
    adresse_licence, adresse_origine = lien_de_credit(p.licence_url), lien_de_credit(p.origine)
    licence = escape(p.licence)
    if adresse_licence:
        licence = f'<a href="{escape(adresse_licence)}" rel="noopener noreferrer">{licence}</a>'
    origine = (
        f'<a class="credit-origine" href="{escape(adresse_origine)}" rel="noopener noreferrer">{_ui("credit_origine", langue)}</a>'
        if adresse_origine
        else ""
    )
    modifie = escape(_t(MODIFICATIONS.get(p.modifie, (p.modifie, p.modifie)), langue)) if p.modifie else ""
    return f"""<li class="credit-photo" id="photo-{escape(p.id)}">
<span class="credit-vignette">{_photo(p, 480, titre, paresseuse=True)}</span>
<div class="credit-texte">
<p class="credit-titre">{escape(titre)}</p>
<p class="credit-details"><span>{_ui("credit_auteur", langue)}{escape(p.auteur)}</span><span>{_ui("credit_licence", langue)}{licence}</span>{f"<span>{modifie}</span>" if modifie else ""}</p>
{origine}
</div>
</li>"""


def page_credits(jeton: str, u: Univers, page: int, langue: str, habillage: Habillage = HABILLAGE_PUBLIC) -> str:
    """Crédits des photos (toutes celles du manifeste, dans son ordre), PAR_PAGE_GRILLE par page comme les grilles :
    autant de requêtes de photos qu'une page d'Explorer. Pages numérotées, pour que l'ancre d'une photo soit sûre."""
    total = nb_pages(len(u.photos), PAR_PAGE_GRILLE)
    morceau = u.photos[(page - 1) * PAR_PAGE_GRILLE : page * PAR_PAGE_GRILLE]
    numeros = "".join(
        f'<a href="{adresse_credits(n)}"{' aria-current="page"' if n == page else ""}>{n}</a>'
        for n in range(1, total + 1)
    )
    navigation = f'<nav class="pages" aria-label="{_ui("pages_credits", langue)}">{numeros}</nav>' if total > 1 else ""
    corps = f"""<div class="credits">
<div class="titre-ligne"><h1 class="titre-page">{_ui("credits", langue)}</h1>{_etat_page(page, total, langue)}</div>
<p class="credits-intro">{_ui("credits_intro", langue, marque=MARQUE)}</p>
<ul class="credits-liste">
{"".join(_entree_credit(p, langue) for p in morceau)}
</ul>
{navigation}
</div>"""
    return _gabarit(langue, _titre_pagine("credits", page, langue), "page-credits", corps, jeton, habillage)
