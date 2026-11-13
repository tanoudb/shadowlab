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
import random
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from html import escape
from pathlib import Path

from ..site.vitrine import MARQUE as MARQUE_VITRINE
from ..site.vitrine import Habillage

MARQUE = "Mosaïk Démo"  # nom de travail, manifestement fictif ; à changer ici seulement
DOSSIER_PHOTOS = Path(__file__).resolve().parent / "static" / "social" / "photos"
TAILLES_PHOTO = (1080, 480)  # largeurs servies : `<id>-1080.jpg` (fil, publication) et `<id>-480.jpg` (grilles)
PAR_PAGE_FIL = 6
PAR_PAGE_GRILLE = 12  # explorer, profil, étiquette : 12 vignettes au plus par page (plafonds d'une session)
NB_AUTRES = 4  # autres publications de l'auteur, sur la page d'une publication
NB_VOISINES = 4  # publications voisines dans le fil, sur la page d'une publication
RE_IDENTIFIANT_PHOTO = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # identifiants de publication, sans caractère ambigu
ORIGINE_DATES = datetime(2026, 11, 10, 19, 0)  # date de la publication la plus récente

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
        "Site fictif. Vous visitez sans participer : rien n'est enregistré, hors le journal technique des erreurs décrit sur la page d'information.",
        "Fictional site. You are browsing without taking part: nothing is recorded, apart from the technical error log described on the information page.",
    ),
    "participer": ("Participer à la recherche", "Take part in the study"),
    "autre_site": ("Autre site : {nom}", "Other site: {nom}"),
}


def _t(texte: Texte, langue: str) -> str:
    return texte[1] if langue == "en" else texte[0]


def _ui(cle: str, langue: str, **valeurs: object) -> str:
    """Texte de l'interface, déjà échappé (les valeurs le sont aussi)."""
    return escape(_t(T[cle], langue)).format(**{k: escape(str(v)) for k, v in valeurs.items()})


# --- Photos ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Photo:
    """Une photo du manifeste. `largeur` et `hauteur` sont celles du fichier de 1 080 pixels."""

    id: str
    sujet: str
    largeur: int
    hauteur: int
    auteur: str = ""  # crédit
    licence: str = ""
    origine: str | None = None  # adresse d'origine, pour la page de crédits

    def fichier(self, taille: int) -> str:
        return f"{self.id}-{taille}.jpg"

    def hauteur_pour(self, taille: int) -> int:
        return max(1, round(taille * self.hauteur / self.largeur))


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
    _auteurs: dict[str, Auteur] = field(default_factory=dict, compare=False, repr=False)
    _publications: dict[str, Publication] = field(default_factory=dict, compare=False, repr=False)

    def __post_init__(self) -> None:
        self._auteurs.update((a.pseudonyme, a) for a in self.auteurs)
        self._publications.update((p.identifiant, p) for p in self.publications)

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
    return Univers(auteurs, tuple(publications), tuple(exploration), libelles)


# --- Morceaux de page --------------------------------------------------------------------------


def _nombre(n: int, langue: str) -> str:
    return f"{n:,}" if langue == "en" else f"{n:,}".replace(",", " ")


def _date(iso: str, langue: str) -> str:
    d = datetime.fromisoformat(iso)
    mois = _t(MOIS[d.month - 1], langue)
    return f"{mois} {d.day}, {d.year}" if langue == "en" else f"{d.day} {mois} {d.year}"


def initiales(nom: str) -> str:
    mots = [m.split("'")[-1] for m in nom.split() if m.lower() not in ("de", "du", "et")]
    return "".join(m[0] for m in mots[:2] if m).upper()


def avatar(a: Auteur, taille: int) -> str:
    """Avatar dessiné dans la page (SVG en ligne, sans style ni adresse ni identifiant) : un carré de couleur, un
    motif, les initiales. La feuille de style l'arrondit (`.avatar`)."""
    fond = f"hsl({a.teinte} 48% 52%)"
    clair = f"hsl({(a.teinte + 40) % 360} 70% 80%)"
    motif = (
        f'<circle cx="31" cy="9" r="9" fill="{clair}" opacity=".7"/>',
        f'<rect x="-6" y="26" width="52" height="20" fill="{clair}" opacity=".55" transform="rotate(-12 20 36)"/>',
        f'<polygon points="0,40 14,22 28,40" fill="{clair}" opacity=".6"/>',
        f'<path d="M0 30q10-8 20 0t20 0v10H0z" fill="{clair}" opacity=".6"/>',
    )[a.forme % 4]
    return (
        f'<svg class="avatar" width="{taille}" height="{taille}" viewBox="0 0 40 40" aria-hidden="true">'
        f'<rect width="40" height="40" fill="{fond}"/>{motif}'
        f'<text x="20" y="25" text-anchor="middle" font-family="sans-serif" font-size="14" font-weight="700" fill="#fff">{escape(initiales(a.nom))}</text>'
        "</svg>"
    )


def _lien_auteur(a: Auteur, taille_avatar: int | None = None) -> str:
    image = avatar(a, taille_avatar) if taille_avatar else ""
    return f'<a class="auteur" href="/lab/social/u/{escape(a.pseudonyme)}">{image}<span class="auteur-nom">{escape(a.nom)}</span></a>'


def _photo(photo: Photo, taille: int, texte: str, paresseuse: bool) -> str:
    chargement = ' loading="lazy"' if paresseuse else ""
    return (
        f'<img class="photo" src="/lab/social/photos/{escape(photo.fichier(taille))}" alt="{escape(texte)}"'
        f' width="{taille}" height="{photo.hauteur_pour(taille)}"{chargement}>'
    )


def _etiquettes(u: Univers, p: Publication, langue: str) -> str:
    liens = "".join(
        f'<a class="etiquette" href="/lab/social/t/{escape(e)}">#{escape(_t(u.libelles[e], langue))}</a>'
        for e in p.etiquettes
    )
    return f'<p class="etiquettes">{liens}</p>'


def _aime(p: Publication, langue: str) -> str:
    """Bouton « j'aime » : social.js ne change que l'affichage, rien n'est envoyé."""
    return (
        f'<button class="aime" type="button" aria-pressed="false" data-aime="{p.aimes}">'
        f'<span class="coeur" aria-hidden="true">♥</span> <span class="aime-compte">{_nombre(p.aimes, langue)}</span>'
        f' <span class="aime-libelle">{_ui("j_aime", langue)}</span></button>'
    )


def _entete_publication(u: Univers, p: Publication, langue: str) -> str:
    a = u.auteur(p.auteur)
    return (
        f'<header class="publication-entete">{_lien_auteur(a, 36)}'
        f'<time class="date" datetime="{escape(p.date)}">{escape(_date(p.date, langue))}</time></header>'
    )


def _legende(u: Univers, p: Publication, langue: str) -> str:
    a = u.auteur(p.auteur)
    return f'<p class="legende"><a class="auteur-nom" href="/lab/social/u/{escape(a.pseudonyme)}">{escape(a.nom)}</a> {escape(_t(p.legende, langue))}</p>'


def _carte_fil(u: Univers, p: Publication, langue: str, rang: int) -> str:
    ident = escape(p.identifiant)
    n = len(p.commentaires)
    if n == 0:
        commentaires = _ui("commenter", langue)
    elif n == 1:
        commentaires = _ui("voir_commentaire", langue)
    else:
        commentaires = _ui("voir_commentaires", langue, n=n)
    return f"""<article class="publication" data-publication="{ident}">
{_entete_publication(u, p, langue)}
<a class="publication-photo" href="/lab/social/p/{ident}">{_photo(p.photo, 1080, _t(p.legende, langue), paresseuse=rang >= 2)}</a>
<div class="publication-corps">
<div class="publication-actions">{_aime(p, langue)}<a class="commentaires-lien" href="/lab/social/p/{ident}">{commentaires}</a></div>
{_legende(u, p, langue)}
{_etiquettes(u, p, langue)}
</div>
</article>"""


def _vignette(u: Univers, p: Publication, langue: str, cherchable: bool = False) -> str:
    attributs = ""
    if cherchable:
        a = u.auteur(p.auteur)
        cle = " ".join([a.pseudonyme, a.nom, *p.etiquettes, *(_t(u.libelles[e], langue) for e in p.etiquettes)])
        attributs = f' data-cherchable data-texte="{escape(_replier(cle))}"'
    return (
        f'<a class="vignette" href="/lab/social/p/{escape(p.identifiant)}"{attributs}>'
        f"{_photo(p.photo, 480, _t(p.legende, langue), paresseuse=True)}"
        f'<span class="vignette-info"><span class="coeur" aria-hidden="true">♥</span> {_nombre(p.aimes, langue)}</span></a>'
    )


def _grille(u: Univers, publications: list[Publication], langue: str, cherchable: bool = False) -> str:
    return f'<div class="grille">{"".join(_vignette(u, p, langue, cherchable) for p in publications)}</div>'


def _suite(chemin: str, page: int, total: int, langue: str) -> str:
    if page < total:
        lien = f'<a class="voir-plus" rel="next" href="{chemin}?page={page + 1}">{_ui("voir_plus", langue)}</a>'
    else:
        lien = f'<p class="fin">{_ui("fin", langue)}</p>'
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
    return f"""<aside class="session-publique" aria-label="{_ui("recherche", langue)}"><div class="conteneur">
<p>{_ui("sans_participer", langue)}</p>
<div class="actions"><a href="/">{_ui("participer", langue)}</a>{autre}</div>
</div></aside>"""


def _gabarit(langue: str, titre: str, classe: str, corps: str, jeton: str, habillage: Habillage) -> str:
    """Gabarit commun. Pendant une session, jeton et observateur du labo chargés comme sur une page de la vitrine
    publique (`vitrine._gabarit`) ; le script et la feuille du réseau social sont servis hors de /lab/."""
    metas = f'<meta name="sl-session" content="{escape(jeton)}">\n' if habillage.observateur else ""
    metas += '<meta name="sl-sans-tiers" content="1">\n' if habillage.sans_tiers else ""
    observateur = '<script type="module" src="/lab/static/observateur.js"></script>\n' if habillage.observateur else ""
    bandeau_page = f"{habillage.bandeau}\n" if habillage.bandeau else ""
    return f"""<!doctype html>
<html lang="{"en" if langue == "en" else "fr"}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{metas}<title>{escape(titre)} — {escape(MARQUE)}</title>
<link rel="stylesheet" href="/public/static/social.css">
</head>
<body class="social {classe}">
<header class="entete"><div class="conteneur">
<a class="marque" href="/lab/social/fil">{escape(MARQUE)}</a>
<nav class="navigation" aria-label="{_ui("navigation", langue)}"><a href="/lab/social/fil">{_ui("fil", langue)}</a><a href="/lab/social/explorer">{_ui("explorer", langue)}</a></nav>
</div></header>
{bandeau_page}<main class="conteneur principal">
{corps}
</main>
<footer class="pied"><div class="conteneur">{_ui("pied", langue)}</div></footer>
{observateur}<script type="module" src="/public/static/social.js"></script>
</body>
</html>"""


def _titre_pagine(cle: str, page: int, langue: str) -> str:
    titre = _t(T[cle], langue)
    return titre if page == 1 else f"{titre} — {_t(T['page'], langue)} {page}"


# --- Pages -------------------------------------------------------------------------------------

HABILLAGE_PUBLIC = Habillage(observateur=False, sans_tiers=True)


def page_fil(jeton: str, u: Univers, page: int, langue: str, habillage: Habillage = HABILLAGE_PUBLIC) -> str:
    """Le fil : PAR_PAGE_FIL publications, de la plus récente à la plus ancienne, et « Voir plus »."""
    total = nb_pages(len(u.publications), PAR_PAGE_FIL)
    morceau = u.publications[(page - 1) * PAR_PAGE_FIL : page * PAR_PAGE_FIL]
    cartes = "\n".join(_carte_fil(u, p, langue, rang) for rang, p in enumerate(morceau))
    corps = f"""<h1 class="titre-page">{_ui("fil", langue)}</h1>
<div class="fil">
{cartes}
</div>
{_suite("/lab/social/fil", page, total, langue)}"""
    return _gabarit(langue, _titre_pagine("fil", page, langue), "page-fil", corps, jeton, habillage)


def page_explorer(jeton: str, u: Univers, page: int, langue: str, habillage: Habillage = HABILLAGE_PUBLIC) -> str:
    """Grille de vignettes (PAR_PAGE_GRILLE par page), avec une recherche qui filtre dans la page."""
    total = nb_pages(len(u.exploration), PAR_PAGE_GRILLE)
    morceau = [u.publication(i) for i in u.exploration[(page - 1) * PAR_PAGE_GRILLE : page * PAR_PAGE_GRILLE]]
    auteurs = "".join(
        f'<li data-cherchable data-texte="{escape(_replier(a.pseudonyme + " " + a.nom))}">{_lien_auteur(a)}</li>'
        for a in sorted(u.auteurs, key=lambda a: _replier(a.nom))
    )
    etiquettes = "".join(
        f'<li data-cherchable data-texte="{escape(_replier(e + " " + _t(libelle, langue)))}">'
        f'<a class="etiquette" href="/lab/social/t/{escape(e)}">#{escape(_t(libelle, langue))}</a></li>'
        for e, libelle in sorted(u.libelles.items(), key=lambda e: _replier(_t(e[1], langue)))
    )
    corps = f"""<h1 class="titre-page">{_ui("explorer", langue)}</h1>
<div class="recherche">
<label for="recherche">{_ui("rechercher", langue)}</label>
<input id="recherche" type="search" autocomplete="off" spellcheck="false" placeholder="{_ui("exemple_recherche", langue)}" data-recherche>
<p class="recherche-vide" data-recherche-vide hidden>{_ui("aucun_resultat", langue)}</p>
</div>
<section class="listes">
<h2>{_ui("auteurs", langue)}</h2>
<ul class="puces">{auteurs}</ul>
<h2>{_ui("etiquettes", langue)}</h2>
<ul class="puces">{etiquettes}</ul>
</section>
{_grille(u, morceau, langue, cherchable=True)}
{_suite("/lab/social/explorer", page, total, langue)}"""
    return _gabarit(langue, _titre_pagine("explorer", page, langue), "page-explorer", corps, jeton, habillage)


def _commentaire(u: Univers, c: Commentaire, langue: str) -> str:
    return f'<li class="commentaire">{_lien_auteur(u.auteur(c.auteur), 28)} <span class="commentaire-texte">{escape(_t(c.texte, langue))}</span></li>'


def page_publication(
    jeton: str, u: Univers, p: Publication, langue: str, habillage: Habillage = HABILLAGE_PUBLIC
) -> str:
    """Une publication : grande photo, légende, étiquettes, commentaires (et une zone de commentaire qui reste dans
    la page), autres publications de l'auteur, publications voisines dans le fil."""
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
<h2 class="titre-section">{_ui("plus_de", langue, nom=a.nom)}</h2>
{_grille(u, autres, langue)}
</section>
"""
    if voisines:
        sections += f"""<section class="voisines">
<h2 class="titre-section">{_ui("voisines", langue)}</h2>
{_grille(u, voisines, langue)}
</section>
"""
    corps = f"""<article class="publication publication-seule" data-publication="{ident}">
{_entete_publication(u, p, langue)}
<figure class="publication-photo">{_photo(p.photo, 1080, _t(p.legende, langue), paresseuse=False)}</figure>
<div class="publication-corps">
<div class="publication-actions">{_aime(p, langue)}</div>
{_legende(u, p, langue)}
{_etiquettes(u, p, langue)}
<section class="commentaires" aria-labelledby="titre-commentaires">
<h2 id="titre-commentaires">{_ui("commentaires", langue)} <span class="compte">({len(p.commentaires)})</span></h2>
{aucun}<ul class="commentaires-liste" data-commentaires>{commentaires}</ul>
<div class="zone-commentaire" data-zone-commentaire data-vous="{_ui("vous", langue)}">
<label for="commentaire">{_ui("ajouter_commentaire", langue)}</label>
<textarea id="commentaire" rows="2" maxlength="300" data-commentaire></textarea>
<button class="bouton-plein publier" type="button" data-publier>{_ui("publier", langue)}</button>
<p class="discret">{_ui("commentaire_local", langue)}</p>
</div>
</section>
</div>
</article>
{sections}"""
    return _gabarit(langue, f"{a.nom} — {_t(p.legende, langue)}", "page-publication", corps, jeton, habillage)


def page_profil(jeton: str, u: Univers, a: Auteur, langue: str, habillage: Habillage = HABILLAGE_PUBLIC) -> str:
    """Un profil : avatar, nom, pseudonyme, bio, chiffres, et ses PAR_PAGE_GRILLE publications les plus récentes."""
    publications = u.de_l_auteur(a.pseudonyme)
    unite = "publication" if len(publications) == 1 else "publications"
    corps = f"""<section class="profil">
{avatar(a, 96)}
<div class="profil-texte">
<h1 class="profil-nom">{escape(a.nom)}</h1>
<p class="profil-pseudo">@{escape(a.pseudonyme)}</p>
<p class="profil-bio">{escape(_t(a.bio, langue))}</p>
<p class="profil-chiffres"><span><strong>{_nombre(len(publications), langue)}</strong> {_ui(unite, langue)}</span> <span><strong>{_nombre(a.abonnes, langue)}</strong> {_ui("abonnes", langue)}</span></p>
</div>
</section>
<h2 class="titre-section">{_ui("recentes", langue)}</h2>
{_grille(u, publications[:PAR_PAGE_GRILLE], langue)}"""
    return _gabarit(langue, f"{a.nom} (@{a.pseudonyme})", "page-profil", corps, jeton, habillage)


def page_etiquette(jeton: str, u: Univers, etiquette: str, langue: str, habillage: Habillage = HABILLAGE_PUBLIC) -> str:
    """Une étiquette : son nom, le nombre de publications et les PAR_PAGE_GRILLE plus récentes."""
    publications = u.avec_etiquette(etiquette)
    libelle = _t(u.libelles[etiquette], langue)
    unite = "publication" if len(publications) == 1 else "publications"
    corps = f"""<section class="etiquette-entete">
<h1 class="titre-page">#{escape(libelle)}</h1>
<p class="compteur">{_nombre(len(publications), langue)} {_ui(unite, langue)}</p>
</section>
{_grille(u, publications[:PAR_PAGE_GRILLE], langue)}"""
    return _gabarit(langue, f"#{libelle}", "page-etiquette", corps, jeton, habillage)
