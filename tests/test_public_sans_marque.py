"""Le site public ne cite jamais le nom du projet ni celui du laboratoire (demande d'Ethan, 14/11/2026 :
« tu mentionnes noezia, faut pas du tout »). Ce fichier couvre les textes des deux langues et les feuilles de style
et scripts propres au site public."""

from pathlib import Path

import pytest

from shadowlab.public import textes

NOMS_INTERDITS = ("noezia", "shadowlab", "shadow lab")
STATIQUES = Path(textes.__file__).parent / "static"


def _noms_trouves(texte: str) -> list[str]:
    bas = texte.lower()
    return [nom for nom in NOMS_INTERDITS if nom in bas]


@pytest.mark.parametrize("langue", sorted(textes.T))
def test_aucun_texte_ne_cite_le_projet(langue: str) -> None:
    fautifs = {cle: _noms_trouves(valeur) for cle, valeur in textes.T[langue].items() if _noms_trouves(valeur)}
    assert not fautifs, f"textes « {langue} » qui citent le projet : {fautifs}"


@pytest.mark.parametrize("fichier", sorted(p.name for p in STATIQUES.glob("*.*") if p.suffix in {".css", ".js"}))
def test_aucun_fichier_statique_du_site_public_ne_cite_le_projet(fichier: str) -> None:
    contenu = (STATIQUES / fichier).read_text(encoding="utf-8")
    assert not _noms_trouves(contenu), f"{fichier} cite le projet : {_noms_trouves(contenu)}"
