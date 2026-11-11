"""Site vitrine à contenu connu : annonces immobilières fictives générées à partir d'une graine.

Le contenu est entièrement déterministe (même graine et même taille = mêmes annonces) : `verite()`
exporte ce qu'un moteur de récolte doit retrouver, page après page. Aucune donnée réelle : communes
réelles autorisées, agences au nom manifestement inventé, téléphones en `01 99 00 xx xx` (plage
réservée à la fiction), aucune adresse précise ni nom de personne.
"""

# ruff: noqa: E501  (gabarits HTML : lignes longues voulues, un balisage par ligne)
from __future__ import annotations

import random
import re
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from functools import lru_cache
from html import escape

from .pages import HONEYPOT_LIEN

PAR_PAGE = 20
NB_A_LA_UNE = 6
NB_SIMILAIRES = 4
RE_REFERENCE = re.compile(r"^AN-(\d{6})$")
ORIGINE_DATES = date(2026, 1, 1)
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre"]
MOIS += ["novembre", "décembre"]

# (commune, code postal, prix moyen au m² indicatif)
VILLES = [
    ("Nantes", "44000", 4300),
    ("Lyon", "69003", 5400),
    ("Lille", "59000", 3900),
    ("Rennes", "35000", 4100),
    ("Bordeaux", "33000", 4700),
    ("Toulouse", "31000", 3800),
    ("Angers", "49000", 3300),
    ("Dijon", "21000", 2900),
    ("Tours", "37000", 3000),
    ("Metz", "57000", 2500),
    ("Grenoble", "38000", 3200),
    ("Brest", "29200", 2300),
]
# (type, surface min, surface max, avec nombre de pièces déduit de la surface)
TYPES = [
    ("Studio", 18, 32),
    ("Appartement", 30, 130),
    ("Maison", 70, 260),
    ("Loft", 60, 160),
    ("Duplex", 55, 140),
]
AGENCES = [
    "Agence Fictive Horizon",
    "Cabinet Imaginaire Ardoise",
    "Immo Exemple Lumière",
    "Maison Factice Girofle",
    "Agence Inventée du Cormoran",
    "Cabinet Démo Cerisier",
    "Immo Imaginaire Quartz",
    "Agence Fictive Balise",
]
ATOUTS = [
    "Lumineux et traversant.",
    "Proche des commerces et des transports.",
    "Cuisine équipée récente.",
    "Parquet ancien conservé.",
    "Calme, sans vis-à-vis.",
    "Cave et place de stationnement incluses.",
    "Balcon exposé plein sud.",
    "Belle hauteur sous plafond.",
    "Salle de bain refaite à neuf.",
    "Quartier prisé, écoles à pied.",
    "Copropriété bien entretenue.",
    "Rangements nombreux.",
]
DPE = "ABCDEFG"
POIDS_DPE = [4, 12, 22, 28, 20, 10, 4]


@dataclass(frozen=True)
class Annonce:
    reference: str
    titre: str
    type_bien: str
    ville: str
    code_postal: str
    surface: int
    pieces: int
    prix: int
    dpe: str
    description: str
    date_publication: str
    nb_photos: int
    agence: str
    telephone: str


# --- Génération --------------------------------------------------------------------------------


def _annonce(graine: int, indice: int) -> Annonce:
    """Annonce n° `indice` (à partir de 1) : sa propre graine, donc indépendante de la taille demandée."""
    alea = random.Random(graine * 1_000_003 + indice)
    type_bien, smin, smax = alea.choice(TYPES)
    ville, code_postal, prix_m2 = alea.choice(VILLES)
    surface = alea.randint(smin, smax)
    pieces = 1 if type_bien == "Studio" else max(2, min(10, round(surface / 28)))
    prix = round(surface * prix_m2 * alea.uniform(0.75, 1.3) / 500) * 500
    dpe = alea.choices(DPE, weights=POIDS_DPE)[0]
    publication = ORIGINE_DATES + timedelta(days=alea.randint(0, 310))
    if type_bien == "Studio":
        titre = f"Studio de {surface} m² à {ville}"
    else:
        titre = f"{type_bien} {pieces} pièces à {ville}"
    description = f"{type_bien} de {surface} m² à {ville}, {pieces} pièce{'s' if pieces > 1 else ''}. " + " ".join(
        alea.sample(ATOUTS, 3)
    )
    return Annonce(
        reference=f"AN-{indice:06d}",
        titre=titre,
        type_bien=type_bien,
        ville=ville,
        code_postal=code_postal,
        surface=surface,
        pieces=pieces,
        prix=prix,
        dpe=dpe,
        description=description,
        date_publication=publication.isoformat(),
        nb_photos=alea.randint(3, 6),
        agence=alea.choice(AGENCES),
        telephone=f"01 99 00 {alea.randint(0, 99):02d} {alea.randint(0, 99):02d}",
    )


@lru_cache(maxsize=8)
def _cache(graine: int, taille: int) -> tuple[Annonce, ...]:
    return tuple(_annonce(graine, i) for i in range(1, taille + 1))


def generer(graine: int, taille: int) -> list[Annonce]:
    """Les `taille` annonces de la graine, toujours identiques pour les mêmes arguments."""
    return list(_cache(graine, taille))


def nb_pages(taille: int) -> int:
    return max(1, -(-taille // PAR_PAGE))


def verite(graine: int, taille: int) -> dict:
    """Export complet de ce que le site publie, sérialisable en JSON."""
    return {
        "graine": graine,
        "taille": taille,
        "par_page": PAR_PAGE,
        "nb_pages": nb_pages(taille),
        "annonces": [asdict(a) for a in generer(graine, taille)],
    }


def trouver(annonces: list[Annonce], reference: str) -> Annonce | None:
    m = RE_REFERENCE.match(reference)
    if not m:
        return None
    indice = int(m.group(1))
    return annonces[indice - 1] if 1 <= indice <= len(annonces) else None


def similaires(annonces: list[Annonce], annonce: Annonce, n: int = NB_SIMILAIRES) -> list[Annonce]:
    """Autres annonces, d'abord de la même ville, puis les plus proches en prix."""
    autres = [a for a in annonces if a.reference != annonce.reference]
    autres.sort(key=lambda a: (a.ville != annonce.ville, abs(a.prix - annonce.prix), a.reference))
    return autres[:n]


def page_annonces(annonces: list[Annonce], page: int) -> list[Annonce]:
    return annonces[(page - 1) * PAR_PAGE : page * PAR_PAGE]


def resume_json(a: Annonce) -> dict:
    """Forme servie par l'API « similaires »."""
    return {
        "reference": a.reference,
        "titre": a.titre,
        "ville": a.ville,
        "prix": a.prix,
        "surface": a.surface,
        "lien": f"/lab/vitrine/annonces/{a.reference}",
        "photo": f"/lab/vitrine/photos/{a.reference}/1.svg",
    }


# --- Images ------------------------------------------------------------------------------------
# Illustrations SVG dessinées à la volée : déterministes, légères, sans fichier externe ni style en
# ligne. La première photo montre la façade, les suivantes les pièces du bien.

VUES = ["Façade", "Séjour", "Cuisine", "Chambre", "Salle de bain", "Extérieur"]
IMMEUBLES = {"Appartement", "Studio", "Loft", "Duplex"}
HERBE = "#9bb38a"
FEUILLAGE = "#7fa878"
BOIS = "#7a5a44"


def legende_photo(n: int) -> str:
    """Ce que montre la photo n° `n` (à partir de 1)."""
    return VUES[(n - 1) % len(VUES)]


def _palette(reference: str) -> dict[str, str]:
    """Couleurs du bien : les mêmes sur toutes ses photos."""
    teinte = random.Random(reference).randint(0, 359)
    oppose = (teinte + 190) % 360
    return {
        "ciel": f"hsl({teinte} 45% 88%)",
        "mur": f"hsl({(teinte + 30) % 360} 22% 93%)",
        "accent": f"hsl({oppose} 32% 38%)",
        "doux": f"hsl({oppose} 30% 74%)",
        "sol": f"hsl({(teinte + 40) % 360} 20% 66%)",
    }


def _dehors(c: dict[str, str]) -> str:
    return f'<rect width="640" height="400" fill="{c["ciel"]}"/><rect y="330" width="640" height="70" fill="{HERBE}"/>'


def _arbre(x: int, rayon: int = 44) -> str:
    return f'<rect x="{x - 6}" y="250" width="12" height="80" fill="{BOIS}"/><circle cx="{x}" cy="{276 - rayon}" r="{rayon}" fill="{FEUILLAGE}"/>'


def _facade_maison(c: dict[str, str], alea: random.Random) -> str:
    x_arbre = alea.choice((88, 552))
    fenetres = "".join(
        f'<rect data-e="fenetre" x="{x}" y="{y}" width="46" height="46" rx="3" fill="#fff" stroke="{c["accent"]}" stroke-width="3"/>'
        for x in (206, 388)
        for y in (196, 262)
    )
    return (
        f'<circle cx="{640 - x_arbre}" cy="72" r="30" fill="#fff" opacity=".75"/>'
        f"{_arbre(x_arbre)}"
        f'<rect x="400" y="96" width="26" height="60" fill="{c["accent"]}"/>'
        f'<rect x="176" y="170" width="288" height="160" fill="{c["mur"]}"/>'
        f'<polygon points="150,172 320,84 490,172" fill="{c["accent"]}"/>'
        f"{fenetres}"
        f'<rect data-e="porte" x="298" y="254" width="44" height="76" rx="3" fill="{c["accent"]}"/>'
        '<circle cx="333" cy="294" r="3" fill="#fff"/>'
    )


def _facade_immeuble(c: dict[str, str], alea: random.Random) -> str:
    fenetres = "".join(
        f'<rect data-e="fenetre" x="{226 + 52 * colonne}" y="{92 + 46 * etage}" width="32" height="30" rx="2"'
        f' fill="{"#ffe9a8" if alea.random() < 0.3 else "#fff"}" stroke="{c["accent"]}" stroke-width="2"/>'
        for etage in range(4)
        for colonne in range(4)
    )
    return (
        f'<rect x="70" y="150" width="120" height="180" fill="{c["doux"]}" opacity=".6"/>'
        f'<rect x="470" y="120" width="110" height="210" fill="{c["doux"]}" opacity=".6"/>'
        f'<rect x="204" y="66" width="232" height="264" fill="{c["mur"]}"/>'
        f'<rect x="196" y="58" width="248" height="12" fill="{c["accent"]}"/>'
        f"{fenetres}"
        f'<rect data-e="porte" x="298" y="278" width="44" height="52" rx="2" fill="{c["accent"]}"/>'
    )


def _piece(c: dict[str, str]) -> str:
    """Fond commun des vues intérieures : mur, sol, fenêtre à croisillons."""
    return (
        f'<rect width="640" height="400" fill="{c["mur"]}"/>'
        f'<rect y="300" width="640" height="100" fill="{c["sol"]}"/>'
        f'<rect x="60" y="70" width="150" height="150" rx="4" fill="{c["ciel"]}" stroke="#fff" stroke-width="10"/>'
        '<path d="M135 70v150M60 145h150" stroke="#fff" stroke-width="6"/>'
    )


def _sejour(c: dict[str, str]) -> str:
    return (
        f'<ellipse cx="405" cy="348" rx="180" ry="24" fill="{c["doux"]}" opacity=".6"/>'
        f'<rect x="270" y="228" width="270" height="86" rx="16" fill="{c["accent"]}"/>'
        f'<rect x="288" y="206" width="112" height="56" rx="12" fill="{c["doux"]}"/>'
        f'<rect x="410" y="206" width="112" height="56" rx="12" fill="{c["doux"]}"/>'
        '<path d="M584 314V172" stroke="#5b6677" stroke-width="5"/><path d="M558 172h52l-13-42h-26z" fill="#ffe9a8"/>'
    )


def _cuisine(c: dict[str, str]) -> str:
    return (
        f'<rect x="250" y="80" width="330" height="72" rx="4" fill="{c["doux"]}"/>'
        '<path d="M360 80v72M470 80v72" stroke="#fff" stroke-width="4"/>'
        f'<rect x="250" y="240" width="330" height="90" fill="{c["accent"]}"/>'
        '<path d="M360 240v90M470 240v90" stroke="#fff" stroke-width="3" opacity=".5"/>'
        '<rect x="244" y="230" width="342" height="12" fill="#fff"/>'
        '<circle cx="505" cy="236" r="9" fill="#5b6677"/><circle cx="545" cy="236" r="9" fill="#5b6677"/>'
        '<path d="M300 230v-34h26" stroke="#5b6677" stroke-width="5" fill="none"/>'
    )


def _chambre(c: dict[str, str]) -> str:
    return (
        f'<rect x="250" y="186" width="320" height="80" rx="10" fill="{c["accent"]}"/>'
        '<rect x="250" y="246" width="320" height="74" rx="10" fill="#fff"/>'
        f'<rect x="274" y="234" width="112" height="36" rx="10" fill="{c["doux"]}"/>'
        f'<rect x="434" y="234" width="112" height="36" rx="10" fill="{c["doux"]}"/>'
        f'<rect x="250" y="282" width="320" height="42" rx="8" fill="{c["doux"]}"/>'
        f'<rect x="588" y="262" width="40" height="62" rx="4" fill="{BOIS}"/>'
        '<circle cx="608" cy="246" r="14" fill="#ffe9a8"/>'
    )


def _salle_de_bain(c: dict[str, str]) -> str:
    return (
        f'<circle cx="430" cy="130" r="56" fill="{c["ciel"]}" stroke="#fff" stroke-width="8"/>'
        '<rect x="380" y="222" width="100" height="16" rx="6" fill="#fff"/>'
        f'<rect x="392" y="238" width="76" height="86" fill="{c["doux"]}"/>'
        '<path d="M430 222v-18h16" stroke="#5b6677" stroke-width="5" fill="none"/>'
        f'<rect x="232" y="252" width="130" height="66" rx="26" fill="#fff" stroke="{c["accent"]}" stroke-width="4"/>'
        f'<rect x="520" y="150" width="14" height="150" rx="6" fill="{c["accent"]}"/>'
        f'<rect x="506" y="176" width="42" height="74" rx="4" fill="{c["doux"]}"/>'
    )


def _exterieur(c: dict[str, str], alea: random.Random) -> str:
    return (
        f"{_dehors(c)}"
        f"{_arbre(126, 40 + alea.randint(0, 14))}{_arbre(512, 40 + alea.randint(0, 14))}"
        f'<path d="M262 262v68M378 262v68" stroke="{c["accent"]}" stroke-width="8"/>'
        f'<rect x="246" y="262" width="148" height="10" rx="3" fill="{c["accent"]}"/>'
        f'<rect x="246" y="288" width="148" height="10" rx="3" fill="{c["accent"]}"/>'
        '<path d="M300 400c10-30 30-50 20-70" stroke="#fff" stroke-width="18" fill="none" opacity=".5"/>'
    )


_INTERIEURS = {"Séjour": _sejour, "Cuisine": _cuisine, "Chambre": _chambre, "Salle de bain": _salle_de_bain}


def photo_svg(a: Annonce, n: int) -> str:
    """Photo n° `n` du bien : façade, pièces puis extérieur. Toujours la même pour les mêmes arguments."""
    alea = random.Random(f"{a.reference}/{n}")
    couleurs = _palette(a.reference)
    vue = legende_photo(n)
    if vue == "Façade":
        facade = _facade_immeuble if a.type_bien in IMMEUBLES else _facade_maison
        dessin = _dehors(couleurs) + facade(couleurs, alea)
    elif vue == "Extérieur":
        dessin = _exterieur(couleurs, alea)
    else:
        dessin = _piece(couleurs) + _INTERIEURS[vue](couleurs)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 400" role="img" '
        f'aria-label="{escape(vue)} — {escape(a.titre)}">'
        f"{dessin}"
        f'<text x="20" y="384" font-family="sans-serif" font-size="15" fill="#44506a">{escape(vue)} · {escape(a.ville)}</text>'
        "</svg>"
    )


# --- Pages HTML --------------------------------------------------------------------------------

MARQUE = "Habitat Démo"  # nom manifestement fictif : le site sera public


def _nombre(valeur: int) -> str:
    return f"{valeur:,}".replace(",", " ")


def _prix(a: Annonce) -> str:
    return f"{_nombre(a.prix)} €"


def _date_fr(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {MOIS[d.month - 1]} {d.year}"


def _gabarit(titre: str, corps: str, jeton: str, scripts: tuple[str, ...] = (), honeypot: bool = False) -> str:
    balises = "".join(f'<script type="module" src="/lab/static/{nom}"></script>' for nom in scripts)
    piege = HONEYPOT_LIEN if honeypot else ""
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="sl-session" content="{escape(jeton)}">
<title>{escape(titre)} — {MARQUE}</title>
<link rel="stylesheet" href="/lab/static/vitrine.css">
</head>
<body class="vitrine">
<header class="entete"><div class="conteneur">
<a class="marque" href="/lab/vitrine">{MARQUE}</a>
<nav aria-label="Navigation principale"><a href="/lab/vitrine">Accueil</a><a href="/lab/vitrine/annonces">Toutes les annonces</a></nav>
</div></header>
<main class="conteneur">
{corps}
{piege}
</main>
<footer class="pied"><div class="conteneur">Site de démonstration — annonces fictives</div></footer>
<script type="module" src="/lab/static/observateur.js"></script>
{balises}
</body>
</html>"""


def _carte(a: Annonce) -> str:
    return f"""<article class="carte" data-reference="{escape(a.reference)}">
<a class="carte-photo" href="/lab/vitrine/annonces/{escape(a.reference)}" tabindex="-1" aria-hidden="true"><img src="/lab/vitrine/photos/{escape(a.reference)}/1.svg" alt="" width="320" height="200" loading="lazy"></a>
<div class="carte-corps">
<h2><a class="fiche" href="/lab/vitrine/annonces/{escape(a.reference)}">{escape(a.titre)}</a></h2>
<p class="carte-prix">{_prix(a)}</p>
<p class="carte-detail">{a.surface} m² · {a.pieces} pièce{"s" if a.pieces > 1 else ""} · DPE {escape(a.dpe)}</p>
<p class="carte-lieu">{escape(a.ville)} ({escape(a.code_postal)})</p>
</div>
</article>"""


def page_accueil(jeton: str, annonces: list[Annonce], honeypot: bool = False) -> str:
    cartes = "".join(_carte(a) for a in annonces[:NB_A_LA_UNE])
    corps = f"""<section class="bandeau">
<h1>Trouvez votre prochain chez-vous</h1>
<p>{len(annonces)} annonces fictives, de la ville à la campagne.</p>
<a class="bouton" href="/lab/vitrine/annonces">Voir toutes les annonces</a>
</section>
<h2 class="titre-section">À la une</h2>
<div class="grille">{cartes}</div>"""
    return _gabarit("Accueil", corps, jeton, honeypot=honeypot)


def page_liste(jeton: str, annonces: list[Annonce], page: int, honeypot: bool = False) -> str:
    total = nb_pages(len(annonces))
    cartes = "".join(_carte(a) for a in page_annonces(annonces, page))
    precedent = (
        f'<a class="precedent" rel="prev" href="/lab/vitrine/annonces?page={page - 1}">← Page précédente</a>'
        if page > 1
        else ""
    )
    suivant = (
        f'<a class="suivant" rel="next" href="/lab/vitrine/annonces?page={page + 1}">Page suivante →</a>'
        if page < total
        else ""
    )
    corps = f"""<h1>Nos annonces</h1>
<p class="compteur">{len(annonces)} biens — page {page} sur {total}</p>
<div class="grille">{cartes}</div>
<nav class="pagination" aria-label="Pagination">{precedent}{suivant}</nav>"""
    return _gabarit(f"Annonces — page {page}", corps, jeton, honeypot=honeypot)


def page_fiche(jeton: str, a: Annonce, honeypot: bool = False) -> str:
    ref = escape(a.reference)
    photos = "".join(
        f'<img src="/lab/vitrine/photos/{ref}/{n}.svg" alt="{escape(legende_photo(n))} — photo {n} sur {a.nb_photos}"'
        f' width="640" height="400"{"" if n == 1 else ' loading="lazy"'}>'
        for n in range(1, a.nb_photos + 1)
    )
    corps = f"""<nav class="fil" aria-label="Fil d'Ariane"><a href="/lab/vitrine">Accueil</a> › <a href="/lab/vitrine/annonces">Annonces</a> › <span>{ref}</span></nav>
<article class="bien">
<h1 data-champ="titre">{escape(a.titre)}</h1>
<p class="bien-ref">Réf. <span data-champ="reference">{ref}</span></p>
<p class="bien-prix" data-champ="prix" data-valeur="{a.prix}">{_prix(a)}</p>
<p class="bien-resume">{a.surface} m² · {a.pieces} pièce{"s" if a.pieces > 1 else ""} · {escape(a.ville)} ({escape(a.code_postal)})</p>
<div class="galerie">{photos}</div>
<div class="bien-colonnes">
<section class="bien-description">
<h2>Description</h2>
<p data-champ="description">{escape(a.description)}</p>
</section>
<aside class="bien-fiche">
<h2>Caractéristiques</h2>
<dl>
<dt>Type de bien</dt><dd data-champ="type_bien">{escape(a.type_bien)}</dd>
<dt>Ville</dt><dd data-champ="ville">{escape(a.ville)}</dd>
<dt>Code postal</dt><dd data-champ="code_postal">{escape(a.code_postal)}</dd>
<dt>Surface</dt><dd data-champ="surface" data-valeur="{a.surface}">{a.surface} m²</dd>
<dt>Pièces</dt><dd data-champ="pieces" data-valeur="{a.pieces}">{a.pieces}</dd>
<dt>Classe DPE</dt><dd><span class="dpe dpe-{escape(a.dpe.lower())}" data-champ="dpe">{escape(a.dpe)}</span></dd>
<dt>Publiée le</dt><dd data-champ="date_publication" data-valeur="{escape(a.date_publication)}">{_date_fr(a.date_publication)}</dd>
<dt>Photos</dt><dd data-champ="nb_photos" data-valeur="{a.nb_photos}">{a.nb_photos}</dd>
</dl>
<h2>Agence</h2>
<p class="agence"><span data-champ="agence">{escape(a.agence)}</span><br>Tél. <span data-champ="telephone">{escape(a.telephone)}</span></p>
</aside>
</div>
</article>
<section class="similaires">
<h2>Annonces similaires</h2>
<div id="similaires" class="grille" data-url="/lab/vitrine/api/annonces/{ref}/similaires" aria-live="polite"></div>
</section>"""
    return _gabarit(a.titre, corps, jeton, scripts=("vitrine.js",), honeypot=honeypot)
