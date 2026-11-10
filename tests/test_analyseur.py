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

# Liste « réelle » : des cartes de même structure, sans classe commune exploitable par un sélecteur.
HTML_LISTE = """<html><body>
<nav class="menu"><a>Accueil</a><a>Contact</a></nav>
<div class="grille">
  <article class="carte"><h3>Studio Paris</h3><span class="prix">250000</span></article>
  <article class="carte"><h3>T2 Lyon</h3><span class="prix">190000</span></article>
  <article class="carte"><h3>T3 Lille</h3><span class="prix">165000</span></article>
</div>
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


def test_similaires_recupere_toute_la_liste_depuis_un_exemple():
    a = Analyseur(HTML_LISTE)
    cartes = a.similaires("article.carte")
    assert len(cartes) == 3  # on pointe UNE carte, on récupère les trois
    titres = [c.css_un("h3") for c in cartes]
    assert titres == ["Studio Paris", "T2 Lyon", "T3 Lille"]
    prix = [c.css_un("span.prix") for c in cartes]
    assert prix == ["250000", "190000", "165000"]


def test_similaires_ignore_les_elements_sans_ressemblance():
    a = Analyseur(HTML)
    # On pointe un <li> d'article : les <span> de la fiche ne doivent pas remonter.
    items = a.similaires("li.article")
    assert [i.attribut("data-id") for i in items] == ["A1", "A2"]


def test_similaires_selecteur_absent_renvoie_vide():
    a = Analyseur(HTML_LISTE)
    assert a.similaires("table.absente") == []


def test_element_texte_et_attribut():
    a = Analyseur(HTML_LISTE)
    carte = a.similaires("article.carte")[0]
    assert "Studio Paris" in carte.texte and "250000" in carte.texte
    assert a.similaires("article.carte")[1].css_un("h3") == "T2 Lyon"


def test_element_tag_et_attributs():
    a = Analyseur(HTML)
    els = a.elements("li.article")
    assert len(els) == 2
    assert els[0].tag == "li"
    assert els[0].attributs == {"class": "article", "data-id": "A1"}
    assert els[1].attribut("data-id") == "A2"


def test_element_navigation_dom():
    a = Analyseur(HTML_LISTE)
    carte = a.elements("article.carte")[0]
    # parent = div.grille
    p = carte.parent
    assert p is not None
    assert p.tag == "div"
    assert "grille" in (p.attribut("class") or "")
    # enfants = h3 + span
    enf = carte.enfants
    assert len(enf) == 2
    assert enf[0].tag == "h3"
    assert enf[0].texte == "Studio Paris"
    assert enf[1].tag == "span"
    # frères = les 2 autres cartes (même parent, sans soi-même)
    fr = carte.freres
    assert len(fr) == 2
    assert fr[0].css_un("h3") == "T2 Lyon"
    assert fr[1].css_un("h3") == "T3 Lille"


def test_element_elements_descendant():
    a = Analyseur(HTML_LISTE)
    carte = a.elements("article.carte")[1]
    prix = carte.elements("span.prix")
    assert len(prix) == 1
    assert prix[0].texte == "190000"


def test_analyseur_elements():
    """Analyseur.elements() renvoie des Element navigables."""
    a = Analyseur(HTML)
    items = a.elements("li.article")
    assert len(items) == 2
    assert items[0].texte == "Alpha"
    assert items[0].attribut("data-id") == "A1"


def test_http_base_analyseur():
    """Les moteurs HTTP (httpx, scrapling) exposent un `.analyseur()` qui rend un Analyseur."""
    from shadowlab.engines.http_base import DriverHttp, ReponseBrute

    class FauxHttp(DriverHttp):
        name = "faux"

        def _ouvrir_client(self):
            pass

        def _envoyer(self, methode, url, donnees=None):
            return ReponseBrute(200, {"content-type": "text/html"}, HTML_LISTE)

        def close_session(self):
            pass

        def versions(self):
            return {}

    pilote = FauxHttp(("*",))
    pilote.start_session()
    pilote.navigate("http://faux.test/page")
    a = pilote.analyseur()
    assert a.css_un("h3") == "Studio Paris"
    items = a.similaires("article.carte")
    assert len(items) == 3
    assert items[2].css_un("span.prix") == "165000"


def test_extraction_adaptative_relocalise_malgre_mutation():
    """Simule deux pages /lab/adaptatif avec des classes mutées — l'extracteur relocalise."""
    from shadowlab.site.pages import ANNONCES_ADAPTATIVES

    def _page(sfx: str) -> str:
        cartes = "".join(
            f"<div class='annonce-{sfx}'>"
            f"<h3 class='titre-{sfx}'>{a['titre']}</h3>"
            f"<span class='prix-{sfx}'>{a['prix']}</span>"
            f"</div>"
            for a in ANNONCES_ADAPTATIVES
        )
        return f"<html><body><div id='annonces'>{cartes}</div></body></html>"

    sigs = extraction.Signatures()
    url = "http://test.local/lab/adaptatif"

    # Passage 1 : sélecteur exact fonctionne
    a1 = Analyseur(_page("abc"), url=url, signatures=sigs)
    t1 = a1.extraire_adaptatif("h3.titre-abc", "titre")
    assert t1 == "Studio Paris 18e"

    # Passage 2 : les classes ont changé → sélecteur cassé, relocalisation
    a2 = Analyseur(_page("xyz"), url=url, signatures=sigs)
    assert a2.css_un("h3.titre-abc") is None  # sélecteur cassé
    t2 = a2.extraire_adaptatif("h3.titre-abc", "titre")
    assert t2 == "Studio Paris 18e"  # retrouvé par ressemblance


def test_recuperer_respecte_le_perimetre():
    # Le périmètre est vérifié AVANT tout fetch (pas de réseau nécessaire pour ce test).
    import pytest

    from shadowlab.engines.noezia.rapide import recuperer
    from shadowlab.perimetre import DestinationRefusee

    with pytest.raises(DestinationRefusee):
        recuperer("https://example.com/", hotes=("127.0.0.1", "localhost"))
