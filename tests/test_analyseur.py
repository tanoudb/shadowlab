"""Tests de l'analyseur HTML (fetcher-agnostique), extraction adaptative sans navigateur."""

from __future__ import annotations

from shadowlab.engines.noezia import extraction
from shadowlab.engines.noezia.analyseur import Analyseur

HTML = """<html><body>
<ul id="articles">
  <li class="article" data-id="A1">Alpha</li>
  <li class="article" data-id="A2">Beta</li>
</ul>
<div class="fiche"><span class="prix gros" id="p1">123 €</span>
<span class="titre">Produit</span></div>
</body></html>"""


def test_css_textes():
    a = Analyseur(HTML)
    assert a.css("li.article") == ["Alpha", "Beta"]
    assert a.css_un("span.prix") == "123 €"


def test_attribut_et_xpath():
    a = Analyseur(HTML)
    assert a.attribut("li.article", "data-id") == "A1"
    assert a.xpath("//span[@class='titre']/text()") == ["Produit"]


def test_tout_le_texte():
    a = Analyseur(HTML)
    t = a.tout_le_texte()
    assert "Alpha" in t and "123 €" in t


def test_extraction_adaptative_sans_navigateur(tmp_path):
    sigs = extraction.Signatures(tmp_path / "s.json")
    url = "http://exemple.test/produit"
    # 1) extraction normale → mémorise la signature
    a1 = Analyseur(HTML, url=url, signatures=sigs)
    assert a1.extraire_adaptatif("span.prix", "prix") == "123 €"
    # 2) le site renomme la classe .prix → .cout : le sélecteur casse, on relocalise
    html2 = HTML.replace('class="prix gros"', 'class="cout gros"')
    a2 = Analyseur(html2, url=url, signatures=sigs)
    assert a2.css_un("span.prix") is None  # sélecteur cassé
    assert a2.extraire_adaptatif("span.prix", "prix") == "123 €"  # relocalisé


def test_adaptatif_sans_store_renvoie_none_si_casse(tmp_path):
    a = Analyseur("<div><b>x</b></div>", url="http://exemple.test/")
    assert a.extraire_adaptatif("span.absent", "k") is None
