"""Recettes de récolte : corrections de l'analyseur, lecture et contrôle d'une recette, extraction d'une page."""

from __future__ import annotations

from shadowlab.engines.noezia.analyseur import Analyseur
from shadowlab.engines.noezia.extraction import Signatures

# --- Corrections de l'analyseur (§ 2 du document de conception) ---------------------------------


def test_adaptatif_rend_un_texte_long_entier():
    """Une description de 300 caractères, retrouvée par ressemblance, n'est pas coupée à 200."""
    description = ("alpha beta gamma " * 20)[:299] + "z"
    assert len(description) == 300
    html = f'<div><p class="description corps">{description}</p></div>'
    signatures = Signatures()
    url = "http://exemple.test/fiche"

    trouve = Analyseur(html, url=url, signatures=signatures)
    assert trouve.extraire_adaptatif("p.description", "d") == description

    mute = Analyseur(html.replace('class="description corps"', 'class="texte corps"'), url=url, signatures=signatures)
    assert mute.css_un("p.description") is None  # le sélecteur a cassé
    assert mute.extraire_adaptatif("p.description", "d") == description  # relocalisé, entier


def test_adaptatif_meme_texte_par_les_deux_chemins():
    """Sélecteur trouvé ou relocalisé : même règle de texte que `Element.texte` (une seule espace)."""
    html = '<div><p class="ref corps">Réf. <span>AN-1</span></p></div>'
    signatures = Signatures()
    url = "http://exemple.test/fiche"

    trouve = Analyseur(html, url=url, signatures=signatures)
    attendu = trouve.elements("p.ref")[0].texte
    assert attendu == "Réf. AN-1"
    assert trouve.extraire_adaptatif("p.ref", "r") == attendu

    mute = Analyseur(html.replace('class="ref corps"', 'class="numero corps"'), url=url, signatures=signatures)
    assert mute.extraire_adaptatif("p.ref", "r") == attendu
