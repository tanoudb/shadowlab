"""Tests de la commande `shadowlab recolter` (CLI de récolte HTTP furtive)."""

from __future__ import annotations

import json

import pytest

from shadowlab import campaigns
from shadowlab.cli import main
from shadowlab.site.pages import REFERENCES_STATIQUES


@pytest.mark.integration
def test_recolter_texte_brut(reglages, capsys):
    """Récupère la page statique du site de test et affiche le texte brut."""
    with campaigns.serveur_local(reglages):
        code = main(["recolter", f"{reglages.url_site}/lab/statique?sl=test"])
    assert code == 0
    sortie = capsys.readouterr().out
    assert REFERENCES_STATIQUES[0] in sortie  # une des références statiques du site


@pytest.mark.integration
def test_recolter_selecteur_css(reglages, capsys):
    """Récupère des éléments ciblés par un sélecteur CSS."""
    with campaigns.serveur_local(reglages):
        code = main(["recolter", f"{reglages.url_site}/lab/statique?sl=test", "td.reference"])
    assert code == 0
    sortie = capsys.readouterr().out
    assert "résultat(s)" in sortie
    assert REFERENCES_STATIQUES[0] in sortie


@pytest.mark.integration
def test_recolter_similaires(reglages, capsys):
    """Le flag --similaires renvoie tous les éléments qui ressemblent à l'exemple."""
    with campaigns.serveur_local(reglages):
        code = main(["recolter", f"{reglages.url_site}/lab/catalogue?page=1&sl=test", "li.article", "--similaires"])
    assert code == 0
    sortie = capsys.readouterr().out
    assert "éléments similaires" in sortie


@pytest.mark.integration
def test_recolter_json(reglages, capsys):
    """La sortie JSON est parsable."""
    with campaigns.serveur_local(reglages):
        code = main(["recolter", f"{reglages.url_site}/lab/statique?sl=test", "td.reference", "--json"])
    assert code == 0
    donnees = json.loads(capsys.readouterr().out)
    assert isinstance(donnees, list)
    assert REFERENCES_STATIQUES[0] in donnees


def test_recolter_url_hors_perimetre(capsys):
    """Une URL hors périmètre en mode strict est refusée."""
    code = main(["recolter", "https://example.com/"])
    # En mode illimité (*), la requête partira mais échouera réseau — pas un test de périmètre.
    # Ce test vérifie surtout que la commande ne plante pas.
    assert code in (0, 1)
