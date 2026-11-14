"""Fabrique les 12 images de remplacement du réseau social fictif et leur manifeste (squelette du 13/11/2026).

Dégradés et formes floues, sans texte ni personne. Les vraies photos (domaine public ou CC0, cadrage du site public)
arriveront dans le même format, dans le même dossier :
- deux fichiers par photo, `<id>-1080.jpg` (1 080 pixels de large) et `<id>-480.jpg` (480), sans métadonnées EXIF ;
- une entrée dans `manifeste.json` : `{"photos": [{"id", "sujet", "largeur", "hauteur", "auteur", "licence",
  "origine"}]}`, où `largeur` et `hauteur` sont celles du fichier de 1 080 pixels, et `id` suit `[a-z0-9][a-z0-9-]*`.

Usage : `uv run python scripts/photos-remplacement.py [dossier]` (par défaut, le dossier servi par le site).
Le résultat est le même à chaque lancement.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

DOSSIER = Path(__file__).resolve().parents[1] / "src" / "shadowlab" / "public" / "static" / "social" / "photos"
LARGEURS = (1080, 480)
QUALITE = 82
# (sujet, couleur du haut, couleur du bas, couleur de la forme, rapport hauteur / largeur)
MODELES = [
    ("mer", (150, 196, 224), (20, 70, 118), (250, 240, 214), 1.25),
    ("montagne", (220, 230, 242), (86, 104, 134), (255, 255, 255), 1.0),
    ("ville", (250, 196, 140), (66, 58, 108), (255, 226, 160), 1.25),
    ("foret", (176, 212, 164), (30, 76, 50), (232, 244, 200), 1.25),
    ("lac", (204, 230, 238), (60, 124, 138), (255, 250, 236), 2 / 3),
    ("desert", (252, 224, 172), (194, 116, 66), (255, 246, 214), 2 / 3),
    ("architecture", (232, 232, 228), (114, 116, 126), (250, 250, 246), 1.25),
    ("cuisine", (246, 214, 180), (148, 66, 38), (255, 236, 200), 1.0),
    ("plante", (222, 238, 202), (64, 116, 58), (246, 252, 228), 1.25),
    ("animal", (238, 212, 192), (106, 76, 58), (252, 238, 222), 1.0),
    ("ciel", (255, 202, 172), (86, 106, 188), (255, 236, 190), 2 / 3),
    ("objet", (240, 234, 224), (146, 132, 116), (255, 252, 244), 1.0),
]


def degrade(largeur: int, hauteur: int, haut: tuple, bas: tuple) -> Image.Image:
    """Dégradé vertical de `haut` à `bas`."""
    colonne = Image.new("RGB", (1, hauteur))
    colonne.putdata(
        [
            tuple(round(h + (b - h) * y / max(1, hauteur - 1)) for h, b in zip(haut, bas, strict=True))
            for y in range(hauteur)
        ]
    )
    return colonne.resize((largeur, hauteur))


def image(numero: int, haut: tuple, bas: tuple, forme: tuple, rapport: float) -> Image.Image:
    """Un dégradé et une forme floue (soleil, reflet), placée selon le numéro : déterministe."""
    largeur = LARGEURS[0]
    hauteur = round(largeur * rapport)
    fond = degrade(largeur, hauteur, haut, bas)
    calque = Image.new("L", (largeur, hauteur), 0)
    rayon = 120 + 30 * (numero % 4)
    cx = round(largeur * (0.25 + 0.5 * ((numero * 37) % 100) / 100))
    cy = round(hauteur * (0.2 + 0.4 * ((numero * 53) % 100) / 100))
    ImageDraw.Draw(calque).ellipse((cx - rayon, cy - rayon, cx + rayon, cy + rayon), fill=170)
    calque = calque.filter(ImageFilter.GaussianBlur(60))
    return Image.composite(Image.new("RGB", (largeur, hauteur), forme), fond, calque)


def fabriquer(dossier: Path) -> list[dict]:
    dossier.mkdir(parents=True, exist_ok=True)
    entrees = []
    for numero, (sujet, haut, bas, forme, rapport) in enumerate(MODELES, start=1):
        ident = f"remplacement-{numero:02d}"
        grande = image(numero, haut, bas, forme, rapport)
        for largeur in LARGEURS:
            copie = (
                grande if largeur == grande.width else grande.resize((largeur, round(largeur * rapport)), Image.LANCZOS)
            )
            copie.save(dossier / f"{ident}-{largeur}.jpg", "JPEG", quality=QUALITE, optimize=True)  # sans EXIF
        entrees.append(
            {
                "id": ident,
                "sujet": sujet,
                "largeur": grande.width,
                "hauteur": grande.height,
                "auteur": "image de remplacement (dégradé généré par scripts/photos-remplacement.py)",
                "licence": "CC0",
                "origine": None,
            }
        )
    texte = json.dumps({"photos": entrees}, ensure_ascii=False, indent=2) + "\n"
    (dossier / "manifeste.json").write_text(texte, encoding="utf-8")
    return entrees


if __name__ == "__main__":
    cible = Path(sys.argv[1]) if len(sys.argv) > 1 else DOSSIER
    print(f"{len(fabriquer(cible))} images de remplacement dans {cible}")
