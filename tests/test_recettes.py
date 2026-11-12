"""Recettes de récolte : corrections de l'analyseur, lecture et contrôle d'une recette, extraction d'une page."""

from __future__ import annotations

import textwrap
from dataclasses import replace
from pathlib import Path

import pytest

from shadowlab.engines.noezia import recettes
from shadowlab.engines.noezia.analyseur import Analyseur
from shadowlab.engines.noezia.extraction import Signatures
from shadowlab.site import vitrine

GRAINE = 20261111
TAILLE = 45
BASE = "http://127.0.0.1:8770"
RECETTE_VITRINE = Path(__file__).resolve().parents[1] / "configs" / "recettes" / "vitrine.yaml"


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


# --- La recette de la vitrine contre le site de la vitrine --------------------------------------


@pytest.fixture(scope="module")
def recette_vitrine():
    return recettes.lire(RECETTE_VITRINE)


def _donnees_notees(enregistrement) -> dict:
    """Les champs de la vérité : les adresses de photos ne sont pas notées (§ 3 du document)."""
    return {k: v for k, v in enregistrement.donnees.items() if k != "photos"}


def test_la_recette_de_la_vitrine_se_lit(recette_vitrine):
    assert recette_vitrine.nom == "vitrine-annonces"
    assert set(recette_vitrine.pages) == {"liste", "fiche"}
    assert recette_vitrine.pages["fiche"].revisiter == "jamais"
    assert recette_vitrine.pages["liste"].revisiter == "toujours"


def test_les_fiches_egalent_la_verite(recette_vitrine):
    verite = vitrine.verite(GRAINE, TAILLE)
    lues = []
    for annonce in vitrine.generer(GRAINE, TAILLE):
        adresse = f"{BASE}/lab/vitrine/annonces/{annonce.reference}?sl=jeton"
        resultat = recettes.extraire(recette_vitrine, vitrine.page_fiche("jeton", annonce), adresse, "fiche")
        assert resultat.conforme and resultat.alertes == [], resultat.alertes
        assert resultat.liens == []
        assert len(resultat.enregistrements) == 1
        enregistrement = resultat.enregistrements[0]
        assert enregistrement.collection == "annonces"
        assert enregistrement.cle == (annonce.reference,)
        assert enregistrement.relocalises == ()
        lues.append(_donnees_notees(enregistrement))
    assert len(lues) == TAILLE
    assert lues == verite["annonces"]


def test_les_photos_sont_des_adresses_absolues(recette_vitrine):
    annonce = vitrine.generer(GRAINE, TAILLE)[6]
    adresse = f"{BASE}/lab/vitrine/annonces/{annonce.reference}"
    resultat = recettes.extraire(recette_vitrine, vitrine.page_fiche("jeton", annonce), adresse, "fiche")
    photos = resultat.enregistrements[0].donnees["photos"]
    assert photos == [f"{BASE}/lab/vitrine/photos/{annonce.reference}/{n}.svg" for n in range(1, annonce.nb_photos + 1)]


def test_la_liste_donne_les_fiches_puis_la_page_suivante(recette_vitrine):
    annonces = vitrine.generer(GRAINE, TAILLE)
    for page in (1, 2, 3):
        adresse = f"{BASE}/lab/vitrine/annonces?page={page}&sl=jeton"
        resultat = recettes.extraire(recette_vitrine, vitrine.page_liste("jeton", annonces, page), adresse, "liste")
        assert resultat.conforme and resultat.alertes == [], resultat.alertes
        assert resultat.enregistrements == []
        attendues = [f"{BASE}/lab/vitrine/annonces/{a.reference}" for a in vitrine.page_annonces(annonces, page)]
        suite = [] if page == 3 else [f"{BASE}/lab/vitrine/annonces?page={page + 1}"]
        # l'ordre des règles : les fiches de la page, puis la page suivante
        assert [(lien.type, lien.adresse) for lien in resultat.liens] == [("fiche", a) for a in attendues] + [
            ("liste", a) for a in suite
        ]


def test_la_page_de_depart_sans_parametre_est_une_liste(recette_vitrine):
    annonces = vitrine.generer(GRAINE, TAILLE)
    resultat = recettes.extraire(
        recette_vitrine, vitrine.page_liste("jeton", annonces, 1), f"{BASE}/lab/vitrine/annonces", "liste"
    )
    assert resultat.conforme


def test_une_adresse_hors_du_motif_est_anormale(recette_vitrine):
    annonce = vitrine.generer(GRAINE, TAILLE)[0]
    resultat = recettes.extraire(
        recette_vitrine, vitrine.page_fiche("jeton", annonce), f"{BASE}/lab/vitrine/annonces?page=2", "fiche"
    )
    assert not resultat.conforme
    assert resultat.enregistrements == [] and resultat.liens == []
    assert "motif" in resultat.alertes[0] and "fiche" in resultat.alertes[0]


def test_un_selecteur_requis_absent_est_anormal(recette_vitrine):
    resultat = recettes.extraire(
        recette_vitrine,
        "<html><body><p>page vide servie à la place du contenu</p></body></html>",
        f"{BASE}/lab/vitrine/annonces/AN-000001",
        "fiche",
    )
    assert not resultat.conforme
    assert resultat.enregistrements == []
    assert "requis" in resultat.alertes[0] and 'data-champ="reference"' in resultat.alertes[0]


def test_un_type_de_page_inconnu_est_refuse(recette_vitrine):
    with pytest.raises(ValueError, match="type de page inconnu"):
        recettes.extraire(recette_vitrine, "<html></html>", f"{BASE}/x", "rallye")


def test_extraction_adaptative_champ_par_champ(recette_vitrine):
    """`adaptatif: true` relocalise la description quand son sélecteur casse, et la rend entière."""
    description = ("alpha beta gamma " * 20)[:299] + "z"
    annonces = vitrine.generer(GRAINE, TAILLE)
    signatures = Signatures()

    normale = replace(annonces[0], description=description)
    html = vitrine.page_fiche("jeton", normale)
    premiere = recettes.extraire(
        recette_vitrine, html, f"{BASE}/lab/vitrine/annonces/{normale.reference}", "fiche", signatures=signatures
    )
    assert premiere.enregistrements[0].donnees["description"] == description
    assert premiere.relocalisations == 0

    # le site renomme l'attribut : le sélecteur du champ casse, les autres champs tiennent
    muet = html.replace('data-champ="description"', 'data-champ="resume"')
    seconde = recettes.extraire(
        recette_vitrine, muet, f"{BASE}/lab/vitrine/annonces/{normale.reference}", "fiche", signatures=signatures
    )
    enregistrement = seconde.enregistrements[0]
    assert enregistrement.donnees["description"] == description
    assert len(enregistrement.donnees["description"]) == 300
    assert enregistrement.relocalises == ("description",)
    assert seconde.relocalisations == 1

    # sans mémoire de signatures, rien n'est relocalisé : le champ reste vide
    sans = recettes.extraire(recette_vitrine, muet, f"{BASE}/lab/vitrine/annonces/{normale.reference}", "fiche")
    assert sans.enregistrements[0].donnees["description"] is None
    assert sans.relocalisations == 0


# --- Lire des champs et des liens sur de petits HTML --------------------------------------------

ENTETE = """\
recette: 1
nom: essai
hotes: [127.0.0.1]
parametres_ignores: [sl]
depart:
  - url: http://127.0.0.1:8770/p
    type: page
"""


def _recette(corps: str):
    return recettes.lire_texte(ENTETE + textwrap.dedent(corps))


def test_formats_et_options_de_champ():
    recette = _recette(
        """\
        pages:
          page:
            url: '^/p$'
            enregistrements:
              - collection: essais
                cle: id
                champs:
                  id: {adresse: '/(p)$'}
                  prix: {css: 'p.prix', format: entier}
                  km: {css: 'p.km', format: nombre}
                  milliers: {css: 'p.milliers', format: nombre}
                  date: {css: 'time.t', attribut: datetime}
                  t1: {css: 'p.temps', format: duree_ms}
                  t2: {css: 'p.court', format: duree_ms}
                  t3: {css: 'p.vide', format: duree_ms, vide_si: [Abandon]}
                  liens: {css: 'li.x a', attribut: href, tous: true, lien: true}
                  premier: {css: 'li.x a', attribut: href, motif: '/a/(\\d+)', format: entier}
                  annulee: {css: 'p.annulee', present: true}
                  absente: {css: 'p.absente', present: true}
                  rien: 'p.rien'
                  blanc: 'p.blanc'
        """
    )
    html = """<html><body>
    <p class="prix">401 500 €</p>
    <p class="km">142,6 km</p>
    <p class="milliers">1 234,5 m</p>
    <time class="t" datetime="2026-04-18">18 avril</time>
    <p class="temps">1:02:03.4</p>
    <p class="court">9:58.7</p>
    <p class="vide">Abandon</p>
    <ul><li class="x"><a href="/a/1">un</a></li><li class="x"><a href="/a/2">deux</a></li></ul>
    <p class="annulee">Annulée</p>
    <p class="blanc">   </p>
    </body></html>"""
    resultat = recettes.extraire(recette, html, f"{BASE}/p?sl=jeton", "page")
    assert resultat.conforme and resultat.alertes == [], resultat.alertes
    assert [e.donnees for e in resultat.enregistrements] == [
        {
            "id": "p",
            "prix": 401500,
            "km": 142.6,
            "milliers": 1234.5,
            "date": "2026-04-18",
            "t1": 3723400,
            "t2": 598700,
            "t3": None,
            "liens": [f"{BASE}/a/1", f"{BASE}/a/2"],
            "premier": 1,
            "annulee": True,
            "absente": False,
            "rien": None,
            "blanc": None,  # un texte vide est une valeur absente
        }
    ]


def test_le_texte_d_un_champ_est_celui_de_l_element_entier():
    """`<p><span>X</span><br>Tél. <span>Y</span></p>` : tout le texte, espaces réduites (et non « X »)."""
    recette = _recette(
        """\
        pages:
          page:
            url: '^/p$'
            enregistrements:
              - collection: essais
                cle: id
                champs:
                  id: {adresse: '/(p)$'}
                  agence: 'p.agence'
                  espaces: 'p.espaces'
        """
    )
    html = (
        '<p class="agence"><span>Agence Fictive</span><br>Tél. <span>01 99 00 12 34</span></p>'
        '<p class="espaces">  une   phrase\n   sur deux lignes  </p>'
    )
    donnees = recettes.extraire(recette, html, f"{BASE}/p", "page").enregistrements[0].donnees
    assert donnees["agence"] == "Agence Fictive Tél. 01 99 00 12 34"
    assert donnees["espaces"] == "une phrase sur deux lignes"


def test_blocs_repetes_sans_classe_commune():
    recette = _recette(
        """\
        pages:
          page:
            url: '^/p$'
            enregistrements:
              - collection: cartes
                cle: titre
                similaires: 'article.carte'
                champs:
                  titre: 'h3'
                  prix: {css: 'span.prix', format: entier}
        """
    )
    html = """<html><body><nav class="menu"><a>Accueil</a></nav><div class="grille">
    <article class="carte"><h3>Studio Paris</h3><span class="prix">250000</span></article>
    <article class="carte"><h3>T2 Lyon</h3><span class="prix">190000</span></article>
    <article class="carte"><h3>T3 Lille</h3><span class="prix">165000</span></article>
    </div></body></html>"""
    resultat = recettes.extraire(recette, html, f"{BASE}/p", "page")
    assert [(e.cle, e.donnees) for e in resultat.enregistrements] == [
        (("Studio Paris",), {"titre": "Studio Paris", "prix": 250000}),
        (("T2 Lyon",), {"titre": "T2 Lyon", "prix": 190000}),
        (("T3 Lille",), {"titre": "T3 Lille", "prix": 165000}),
    ]


ENTETE_SUIVI = (
    ENTETE
    + """\
variables:
  saison: '*'
  championnat: '*'
pages:
  page:
    url: '^/p$'
    suivre:
      - liens: 'table.calendrier td.rallye a'
        vers: rallye
        garder_si: {contexte: 'tr', contient: '{championnat}'}
      - liens: 'ul.saisons a'
        vers: saison
        garder_si: {contient: '{saison}'}
      - liens: 'nav.pages a.suivante'
        vers: page
        garder_si: '*'
  rallye:
    url: '^/r/\\d+$'
  saison:
    url: '^/s/\\d{4}$'
"""
)

HTML_SUIVI = """<html><body>
<table class="calendrier">
<tr><th>Rallye</th><th>Championnat</th></tr>
<tr><td class="rallye"><a href="/r/1">Rallye A</a></td><td>Coupe Démo 2025</td></tr>
<tr><td class="rallye"><a href="/r/2">Rallye B</a></td><td>Trophée Démo 2024</td></tr>
<tr><td class="rallye"><a href="/r/3">Rallye C</a></td><td>Coupe Démo 2025</td></tr>
</table>
<ul class="saisons"><li><a href="/s/2025">Saison 2025</a></li><li><a href="/s/2024">Saison 2024</a></li></ul>
<nav class="pages"><a class="suivante" href="?page=2#haut">Suivante</a><a href="javascript:void(0)">x</a></nav>
</body></html>"""


def test_liens_a_suivre_tout_par_defaut():
    recette = recettes.lire_texte(ENTETE_SUIVI)
    resultat = recettes.extraire(recette, HTML_SUIVI, f"{BASE}/p", "page")
    assert [(lien.type, lien.adresse) for lien in resultat.liens] == [
        ("rallye", f"{BASE}/r/1"),
        ("rallye", f"{BASE}/r/2"),
        ("rallye", f"{BASE}/r/3"),
        ("saison", f"{BASE}/s/2025"),
        ("saison", f"{BASE}/s/2024"),
        ("page", f"{BASE}/p?page=2"),  # fragment retiré, adresse absolue
    ]


def test_liens_a_suivre_filtres_par_les_variables():
    recette = recettes.lire_texte(ENTETE_SUIVI)
    variables = {"championnat": "Coupe Démo", "saison": "2025"}
    resultat = recettes.extraire(recette, HTML_SUIVI, f"{BASE}/p", "page", variables=variables)
    assert [(lien.type, lien.adresse) for lien in resultat.liens] == [
        ("rallye", f"{BASE}/r/1"),  # la ligne du tableau contient « Coupe Démo »
        ("rallye", f"{BASE}/r/3"),
        ("saison", f"{BASE}/s/2025"),  # le texte du lien contient « 2025 »
        ("page", f"{BASE}/p?page=2"),
    ]


def test_une_variable_inconnue_est_refusee():
    recette = recettes.lire_texte(ENTETE_SUIVI)
    with pytest.raises(ValueError, match="variable inconnue.*annee"):
        recettes.extraire(recette, HTML_SUIVI, f"{BASE}/p", "page", variables={"annee": "2025"})


# --- Tableaux lus par le nom de leurs colonnes (forme « rallye » du § 4) ------------------------

RECETTE_TABLEAUX = ENTETE.replace("type: page", "type: speciale") + (
    textwrap.dedent(
        """\
        pages:
          speciale:
            url: '^/speciales/\\d+$'
            requis: 'h1.titre'
            enregistrements:
              - collection: speciales
                cle: id
                champs:
                  id: {adresse: '/speciales/(\\d+)$', format: entier}
                  numero: {css: 'h1.titre', motif: '^ES(\\d+)', format: entier}
                  nom: {css: 'h1.titre', motif: '^ES\\d+ · (.+)$'}
              - collection: temps
                lignes: 'table.temps tr'
                cle: [speciale, numero]
                champs:
                  speciale: {adresse: '/speciales/(\\d+)$', format: entier}
                  numero: {colonne: 'N°', format: entier}
                  rang: {colonne: 'Pos.', format: entier, vide_si: ['-']}
                  premiere_colonne: {colonne: 1}
                  pilote_id: {colonne: 'Équipage', css: 'a.pilote', attribut: href, motif: '/pilotes/(\\d+)',
                              format: entier}
                  pilote: {colonne: 'Équipage', css: 'a.pilote'}
                  copilote: {colonne: 'Équipage', css: '.copilote'}
                  voiture: {colonne: 'Voiture'}
                  temps: {colonne: 'Temps'}
                  temps_ms: {colonne: 'Temps', format: duree_ms, vide_si: ['Abandon']}
          classement:
            url: '^/rallyes/\\d+/classement$'
            requis: 'table.classement'
            enregistrements:
              - collection: classements
                lignes: 'table.classement tr'
                cle: [rallye, numero]
                champs:
                  rallye: {adresse: '/rallyes/(\\d+)/', format: entier}
                  numero: {colonne: 'N°', format: entier}
                  rang: {colonne: 'Pos.', format: entier, vide_si: ['Ab.']}
                  temps_total_ms: {colonne: 'Temps total', format: duree_ms, vide_si: ['-']}
        """
    )
)

HTML_SPECIALE = """<html><body>
<h1 class="titre">ES3 · Col de la Brume</h1>
<table class="temps">
<thead><tr><th>Pos.</th><th>N°</th><th>Équipage</th><th>Voiture</th><th>Temps</th></tr></thead>
<tbody>
<tr><td>1</td><td>12</td><td><a class="pilote" href="/lab/rallye/pilotes/5">Léa Moreau</a><br>
<span class="copilote">Hugo Lenoir</span></td><td>Alpine Démo</td><td>9:58.7</td></tr>
<tr><td>1</td><td>14</td><td><a class="pilote" href="/lab/rallye/pilotes/6">Zoé d'Arc</a><br>
<span class="copilote">Noé Berthier</span></td><td>Renault Démo</td><td>9:58.7</td></tr>
<tr><td>3</td><td>7</td><td><a class="pilote" href="/lab/rallye/pilotes/9">Ugo Salvi</a><br>
<span class="copilote">Eva Lanz</span></td><td>Lancia Démo</td><td>1:02:03.4</td></tr>
<tr><td>-</td><td>21</td><td><a class="pilote" href="/lab/rallye/pilotes/4">Ida Roux</a></td>
<td>Opel Démo</td><td>Abandon</td></tr>
</tbody></table></body></html>"""

HTML_CLASSEMENT = """<html><body>
<table class="classement">
<tr><th>N°</th><th>Pos.</th><th>Groupe</th><th>Temps total</th></tr>
<tr><td>12</td><td>1</td><td>A</td><td>1:02:03.4</td></tr>
<tr><td>21</td><td>Ab.</td><td>B</td><td>-</td></tr>
</table></body></html>"""


def test_tableau_lu_par_le_nom_des_colonnes():
    recette = recettes.lire_texte(RECETTE_TABLEAUX)
    resultat = recettes.extraire(recette, HTML_SPECIALE, f"{BASE}/speciales/7?sl=jeton", "speciale")
    assert resultat.conforme and resultat.alertes == [], resultat.alertes

    speciales = [e for e in resultat.enregistrements if e.collection == "speciales"]
    assert [(e.cle, e.donnees) for e in speciales] == [((7,), {"id": 7, "numero": 3, "nom": "Col de la Brume"})]

    def ligne(numero, rang, premiere, pilote_id, pilote, copilote, voiture, temps, temps_ms):
        return {
            "speciale": 7,
            "numero": numero,
            "rang": rang,
            "premiere_colonne": premiere,
            "pilote_id": pilote_id,
            "pilote": pilote,
            "copilote": copilote,
            "voiture": voiture,
            "temps": temps,
            "temps_ms": temps_ms,
        }

    temps = [e for e in resultat.enregistrements if e.collection == "temps"]
    assert [e.cle for e in temps] == [(7, 12), (7, 14), (7, 7), (7, 21)]
    assert [e.donnees for e in temps] == [
        ligne(12, 1, "1", 5, "Léa Moreau", "Hugo Lenoir", "Alpine Démo", "9:58.7", 598700),
        ligne(14, 1, "1", 6, "Zoé d'Arc", "Noé Berthier", "Renault Démo", "9:58.7", 598700),  # ex aequo
        ligne(7, 3, "3", 9, "Ugo Salvi", "Eva Lanz", "Lancia Démo", "1:02:03.4", 3723400),
        ligne(21, None, "-", 4, "Ida Roux", None, "Opel Démo", "Abandon", None),  # abandon, sans copilote
    ]


def test_colonnes_dans_un_autre_ordre_d_un_tableau_a_l_autre():
    recette = recettes.lire_texte(RECETTE_TABLEAUX)
    resultat = recettes.extraire(recette, HTML_CLASSEMENT, f"{BASE}/rallyes/3/classement", "classement")
    assert resultat.conforme and resultat.alertes == [], resultat.alertes
    assert [(e.cle, e.donnees) for e in resultat.enregistrements] == [
        ((3, 12), {"rallye": 3, "numero": 12, "rang": 1, "temps_total_ms": 3723400}),
        ((3, 21), {"rallye": 3, "numero": 21, "rang": None, "temps_total_ms": None}),
    ]


def test_colonne_absente_de_l_entete_donne_une_alerte():
    recette = _recette(
        """\
        pages:
          page:
            url: '^/p$'
            enregistrements:
              - collection: lignes
                lignes: 'table tr'
                cle: numero
                champs:
                  numero: {colonne: 'N°', format: entier}
                  ecart: {colonne: 'Écart'}
        """
    )
    html = "<table><tr><th>N°</th><th>Pos.</th></tr><tr><td>5</td><td>2</td></tr></table>"
    resultat = recettes.extraire(recette, html, f"{BASE}/p", "page")
    assert [e.donnees for e in resultat.enregistrements] == [{"numero": 5, "ecart": None}]
    assert len(resultat.alertes) == 1 and "Écart" in resultat.alertes[0]


def test_ligne_sans_valeur_de_cle_est_ecartee_avec_une_alerte():
    recette = _recette(
        """\
        pages:
          page:
            url: '^/p$'
            enregistrements:
              - collection: lignes
                lignes: 'table tr'
                cle: numero
                champs:
                  numero: {colonne: 'N°', format: entier}
        """
    )
    html = "<table><tr><th>N°</th></tr><tr><td>5</td></tr><tr><td>total</td></tr></table>"
    resultat = recettes.extraire(recette, html, f"{BASE}/p", "page")
    assert [e.cle for e in resultat.enregistrements] == [(5,)]
    assert any("numero" in a for a in resultat.alertes)


# --- Une recette fautive est refusée, avec un message qui nomme la clé et la ligne --------------

BASE_FAUTES = """\
recette: 1
nom: essai
hotes: [127.0.0.1]
depart:
  - url: http://127.0.0.1:8770/liste
    type: liste
variables:
  saison: '*'
pages:
  liste:
    url: '^/liste$'
    requis: 'a.fiche'
    suivre:
      - liens: 'a.fiche'
        vers: fiche
  fiche:
    url: '^/fiche/(\\d+)$'
    enregistrements:
      - collection: annonces
        cle: id
        champs:
          id: {adresse: '/fiche/(\\d+)$', format: entier}
          titre: 'h1'
"""


def _ligne_de(texte: str, extrait: str) -> int:
    return next(i for i, ligne in enumerate(texte.splitlines(), start=1) if extrait in ligne)


def _refusee(ancien: str, nouveau: str) -> tuple[str, str]:
    """Remplace `ancien` par `nouveau` dans la recette saine ; rend (texte fautif, message de refus)."""
    assert ancien in BASE_FAUTES
    texte = BASE_FAUTES.replace(ancien, nouveau, 1)
    with pytest.raises(recettes.RecetteInvalide) as erreur:
        recettes.lire_texte(texte, source="fautive.yaml")
    return texte, str(erreur.value)


def test_la_recette_saine_de_reference_est_acceptee():
    recette = recettes.lire_texte(BASE_FAUTES)
    assert recette.pages["fiche"].enregistrements[0].cle == ["id"]


def test_cle_inconnue():
    texte, message = _refusee("nom: essai\n", "nom: essai\ncoucou: 1\n")
    assert "coucou" in message and "clé inconnue" in message
    assert f"ligne {_ligne_de(texte, 'coucou')}" in message
    assert "fautive.yaml" in message


def test_cle_inconnue_dans_un_champ():
    texte, message = _refusee("titre: 'h1'", "titre: {css: 'h1', formats: entier}")
    assert "pages.fiche.enregistrements[0].champs.titre.formats" in message
    assert f"ligne {_ligne_de(texte, 'formats')}" in message


def test_motif_d_adresse_invalide():
    texte, message = _refusee("url: '^/fiche/(\\d+)$'", "url: '^/fiche/(\\d+'")
    assert "pages.fiche.url" in message and "motif" in message
    assert f"ligne {_ligne_de(texte, '^/fiche/(')}" in message


def test_motif_de_champ_sans_groupe():
    _, message = _refusee("adresse: '/fiche/(\\d+)$'", "adresse: '/fiche/\\d+$'")
    assert "champs.id.adresse" in message and "groupe" in message


def test_lien_vers_un_type_de_page_absent():
    texte, message = _refusee("vers: fiche", "vers: inexistant")
    assert "pages.liste.suivre[0].vers" in message and "inexistant" in message
    assert f"ligne {_ligne_de(texte, 'inexistant')}" in message


def test_champ_sans_moyen_de_le_lire():
    texte, message = _refusee("titre: 'h1'", "titre: {format: texte}")
    assert "champs.titre" in message and "sans moyen de le lire" in message
    assert f"ligne {_ligne_de(texte, 'titre:')}" in message


def test_valeur_de_format_inconnue():
    _, message = _refusee("titre: 'h1'", "titre: {css: 'h1', format: roman}")
    assert "champs.titre.format" in message and "valeur admise" in message and "duree_ms" in message


def test_selecteur_css_invalide():
    _, message = _refusee("requis: 'a.fiche'", "requis: 'a[['")
    assert "pages.liste.requis" in message and "sélecteur" in message


def test_depart_vers_un_type_absent_ou_un_hote_absent():
    _, message = _refusee("type: liste", "type: absent")
    assert "depart[0].type" in message and "absent" in message
    _, message = _refusee("http://127.0.0.1:8770/liste", "http://exemple.test:8770/liste")
    assert "depart[0].url" in message and "exemple.test" in message


def test_autorisation_obligatoire_hors_du_labo():
    _, message = _refusee("hotes: [127.0.0.1]", "hotes: [127.0.0.1, www.exemple.org]")
    assert "autorisation" in message and "www.exemple.org" in message
    texte = BASE_FAUTES.replace("hotes: [127.0.0.1]", "hotes: [127.0.0.1, www.exemple.org]")
    texte = texte.replace("nom: essai\n", "nom: essai\nautorisation: accord écrit de l'éditeur du 01/01/2026\n")
    assert recettes.lire_texte(texte).autorisation.startswith("accord écrit")


def test_colonne_hors_d_un_tableau():
    _, message = _refusee("titre: 'h1'", "titre: {colonne: 'Nom'}")
    assert "titre" in message and "colonne" in message and "lignes" in message


def test_cle_d_enregistrement_hors_des_champs():
    _, message = _refusee("cle: id", "cle: [id, numero]")
    assert "numero" in message and "champs" in message


def test_variable_non_declaree():
    ancien = "liens: 'a.fiche'\n        vers: fiche"
    _, message = _refusee(ancien, ancien + "\n        garder_si: {contient: '{annee}'}")
    assert "annee" in message and "variable" in message
    assert "pages.liste.suivre[0].garder_si.contient" in message


def test_adaptatif_seulement_pour_un_texte_de_page():
    _, message = _refusee("titre: 'h1'", "titre: {css: 'h1', attribut: title, adaptatif: true}")
    assert "champs.titre" in message and "adaptatif" in message


def test_plusieurs_fautes_sont_toutes_nommees():
    texte = BASE_FAUTES.replace("nom: essai\n", "nom: essai\ncoucou: 1\n").replace("format: entier", "format: roman")
    with pytest.raises(recettes.RecetteInvalide) as erreur:
        recettes.lire_texte(texte)
    message = str(erreur.value)
    assert "coucou" in message and "champs.id.format" in message


def test_yaml_illisible_donne_la_ligne():
    with pytest.raises(recettes.RecetteInvalide, match=r"cassee.yaml.*ligne 2"):
        recettes.lire_texte("recette: 1\n\tnom: essai\n", source="cassee.yaml")


def test_alias_yaml_refuse():
    with pytest.raises(recettes.RecetteInvalide, match="alias"):
        recettes.lire_texte("recette: 1\nnom: &a essai\nautre: *a\n")


def test_fichier_vide_refuse():
    with pytest.raises(recettes.RecetteInvalide):
        recettes.lire_texte("")


def test_lire_un_fichier_absent_donne_une_erreur_claire(tmp_path):
    with pytest.raises(recettes.RecetteInvalide, match="introuvable"):
        recettes.lire(tmp_path / "absente.yaml")


# --- Relecture : expressions régulières lentes, formats stricts, tableaux piégeux, liens hors site ---


def _page_simple(champs: str, html: str, adresse: str = f"{BASE}/p"):
    """Une page `/p` dont les champs sont `id` (adresse) puis ceux de `champs` (une ligne YAML par champ)."""
    recette = _recette(
        "pages:\n  page:\n    url: '^/p$'\n    enregistrements:\n      - collection: essais\n"
        "        cle: id\n        champs:\n          id: {adresse: '/(p)$'}\n" + textwrap.indent(champs, " " * 10)
    )
    return recettes.extraire(recette, html, adresse, "page")


@pytest.mark.parametrize("motif", ["(a+)+$", "(a*)*b", "(a+)*", "(\\d+)+x", "(a+){2,}"])
def test_motif_a_quantificateurs_imbriques_refuse_a_la_lecture(motif):
    with pytest.raises(recettes.RecetteInvalide) as erreur:
        _recette(
            f"""\
            pages:
              page:
                url: '^/p$'
                enregistrements:
                  - collection: essais
                    cle: id
                    champs:
                      id: {{css: 'b', motif: '{motif}'}}
            """
        )
    message = str(erreur.value)
    assert "champs.id.motif" in message and "imbriqués" in message and "ligne" in message


def test_motif_d_adresse_de_page_a_quantificateurs_imbriques_refuse():
    with pytest.raises(recettes.RecetteInvalide, match=r"pages.page.url.*imbriqués"):
        _recette("pages:\n  page:\n    url: '^/(p+)+$'\n")


def test_un_texte_trop_long_est_borne_avant_le_motif_avec_une_alerte():
    html = f"<html><body><b>{'x' * 20_000}</b></body></html>"
    resultat = _page_simple("long: {css: 'b', motif: '^(x+)'}\n", html)
    assert len(resultat.enregistrements[0].donnees["long"]) == recettes.BORNE_TEXTE
    assert any("coupé" in a for a in resultat.alertes)


def test_un_motif_ordinaire_sur_un_texte_hostile_reste_rapide():
    """Un motif sain (sans quantificateurs imbriqués) ne peut pas être bloqué par un texte long du site."""
    import time

    html = f"<html><body><b>{'a' * 50_000}!</b></body></html>"
    debut = time.monotonic()
    resultat = _page_simple("v: {css: 'b', motif: '(a+)$'}\n", html)
    assert time.monotonic() - debut < 2
    assert len(resultat.enregistrements[0].donnees["v"]) == recettes.BORNE_TEXTE


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        ("401 500 €", 401500),
        ("401 500 €", 401500),
        ("12", 12),
        ("-3", -3),
        ("+7 pièces", 7),
        ("3 pièces", 3),
        ("12,5 km", None),
        ("3-4", None),
        ("1e3", None),
        ("4 500,00", None),
        ("1 2", None),
        ("abc", None),
    ],
)
def test_entier_n_accepte_qu_un_entier(texte, attendu):
    resultat = _page_simple("v: {css: 'b', format: entier}\n", f"<b>{texte}</b>")
    assert resultat.enregistrements[0].donnees["v"] == attendu
    assert bool(resultat.alertes) == (attendu is None)


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        ("142,6 km", 142.6),
        ("1 234,5 m", 1234.5),
        ("1.234,5", 1234.5),
        ("1.234", 1234.0),
        ("12", 12.0),
        ("-0,5", -0.5),
        ("1,234.5", None),
        ("10.5", None),
        ("1,2,3", None),
        ("1e3", None),
    ],
)
def test_nombre_virgule_decimale_et_point_des_milliers(texte, attendu):
    resultat = _page_simple("v: {css: 'b', format: nombre}\n", f"<b>{texte}</b>")
    assert resultat.enregistrements[0].donnees["v"] == attendu
    assert bool(resultat.alertes) == (attendu is None)


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [("13:54.3", 834300), ("1:49:48.6", 6588600), ("9:58.7", 598700), ("0:75.0", None), ("12:99.9", None),
     ("1:60:00.0", None), ("75:10.2", 4510200), ("abc", None)],
)  # fmt: skip
def test_duree_secondes_et_minutes_sous_60_quand_une_unite_superieure_existe(texte, attendu):
    resultat = _page_simple("v: {css: 'b', format: duree_ms}\n", f"<b>{texte}</b>")
    assert resultat.enregistrements[0].donnees["v"] == attendu
    assert bool(resultat.alertes) == (attendu is None)


RECETTE_LIGNES = """\
    pages:
      page:
        url: '^/p$'
        enregistrements:
          - collection: lignes
            lignes: 'table.t tr'
            cle: numero
            champs:
              numero: {colonne: 'N°', format: entier}
              nom: {colonne: 'Nom'}
"""


def _lignes(html: str):
    recette = _recette(RECETTE_LIGNES)
    return recettes.extraire(recette, html, f"{BASE}/p", "page")


def test_deux_colonnes_du_meme_nom_donnent_une_alerte():
    html = (
        "<table class='t'><tr><th>N°</th><th>Nom</th><th>Nom</th></tr><tr><td>1</td><td>a</td><td>b</td></tr></table>"
    )
    resultat = _lignes(html)
    assert resultat.enregistrements[0].donnees["nom"] is None
    assert any("ambiguë" in a and "Nom" in a for a in resultat.alertes)


def test_ligne_dont_le_nombre_de_cellules_differe_des_en_tetes_n_est_pas_lue():
    html = (
        "<table class='t'><tr><th>N°</th><th>Nom</th></tr>"
        "<tr><td>1</td><td>a</td></tr>"
        "<tr><td colspan='2'>fusion</td></tr>"
        "<tr><th>entête de ligne</th><td>2</td><td>b</td></tr></table>"
    )
    resultat = _lignes(html)
    assert [e.donnees for e in resultat.enregistrements] == [{"numero": 1, "nom": "a"}]
    assert sum("cellules" in a for a in resultat.alertes) >= 1


def test_les_lignes_d_un_tableau_imbrique_ne_sont_pas_celles_du_tableau_lu():
    html = (
        "<table class='t'><tr><th>N°</th><th>Nom</th></tr>"
        "<tr><td>1</td><td>a<table class='t'><tr><th>N°</th><th>Nom</th></tr>"
        "<tr><td>99</td><td>z</td></tr></table></td></tr>"
        "<tr><td>2</td><td>b</td></tr></table>"
    )
    resultat = _lignes(html)
    assert [e.cle for e in resultat.enregistrements] == [(1,), (2,)]
    assert resultat.alertes == []


def test_les_liens_vers_un_autre_hote_sont_ecartes_et_comptes():
    recette = recettes.lire_texte(ENTETE_SUIVI)
    html = (
        '<ul class="saisons"><li><a href="/s/2025">Saison 2025</a></li>'
        '<li><a href="http://autre.test/s/2024">Saison 2024</a></li>'
        '<li><a href="//autre.test/q">Saison 2023</a></li>'
        '<li><a href="HTTP://127.0.0.1:8770/s/2022">Saison 2022</a></li></ul>'
    )
    resultat = recettes.extraire(recette, html, f"{BASE}/p", "page")
    assert len(resultat.liens) == 2 and resultat.liens[0].adresse == f"{BASE}/s/2025"
    assert resultat.hors_site == 2
