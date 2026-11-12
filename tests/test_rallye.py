"""Site de rallye factice à contenu connu : génération déterministe, parcours HTTP complet = vérité à 100 %."""

import json
import re
from collections import defaultdict
from dataclasses import replace

import pytest
from parsel import Selector

from shadowlab.site import rallye

GRAINE = 20261112
TAILLE = 12  # deux saisons : 8 rallyes puis 4 (assez pour la pagination et pour chaque piège)

# Forme des adresses de chaque type de page (celle que la recette de l'étape 6 utilisera).
TYPES_DE_PAGE = {
    "saisons": r"^/lab/rallye/saisons$",
    "calendrier": r"^/lab/rallye/saisons/\d{4}(\?page=\d+)?$",
    "rallye": r"^/lab/rallye/rallyes/\d+$",
    "speciale": r"^/lab/rallye/speciales/\d+$",
    "classement": r"^/lab/rallye/rallyes/\d+/classement$",
    "engages": r"^/lab/rallye/rallyes/\d+/engages$",
    "chassis": r"^/lab/rallye/chassis/[\w-]+$",
    "pilote": r"^/lab/rallye/pilotes/\d+$",
}
# Les liens qu'un parcours suit : le même jeu que la recette du § 4 (b) du document de conception.
LIENS_A_SUIVRE = [
    "ul.saisons a::attr(href)",
    "nav.pages a.suivante::attr(href)",
    "table.calendrier td.rallye a::attr(href)",
    "table.speciales td.nom a::attr(href)",
    "a.classement::attr(href)",
    "a.engages::attr(href)",
    'table.engages td a[href*="/chassis/"]::attr(href)',
    'table.engages td a[href*="/pilotes/"]::attr(href)',
]
COLLECTIONS = ["rallyes", "speciales", "temps", "classements", "engages", "chassis", "historique", "pilotes"]


# --- Génération --------------------------------------------------------------------------------


def test_meme_graine_memes_donnees():
    premiere = rallye.verite(GRAINE, TAILLE)
    rallye.construire.cache_clear()  # sans cache : on regénère vraiment
    assert rallye.verite(GRAINE, TAILLE) == premiere


def test_graine_differente_donnees_differentes():
    assert rallye.verite(1, 8)["collections"] != rallye.verite(2, 8)["collections"]


def test_taille_respectee_et_saisons():
    for taille in (1, 8, 9, 24):
        v = rallye.verite(GRAINE, taille)
        ids = [r["id"] for r in v["collections"]["rallyes"]]
        assert ids == list(range(1, taille + 1))
    v = rallye.verite(GRAINE, 24)
    assert v["nb_saisons"] == 3 and v["rallyes_par_saison"] == 8
    assert rallye.verite(GRAINE, 9)["nb_saisons"] == 2


def test_volumes_dans_les_bornes():
    v = rallye.verite(GRAINE, 24)
    c = v["collections"]
    for r in c["rallyes"]:
        assert 4 <= len([s for s in c["speciales"] if s["rallye"] == r["id"]]) <= 10
        assert 12 <= len([e for e in c["engages"] if e["rallye"] == r["id"]]) <= 30
    assert len({r["id"] for r in c["rallyes"]}) == 24
    assert len({s["id"] for s in c["speciales"]}) == len(c["speciales"])
    assert len({p["id"] for p in c["pilotes"]}) == len(c["pilotes"]) >= 30
    assert len({x["code"] for x in c["chassis"]}) == len(c["chassis"]) >= 30


def test_marques_visiblement_inventees():
    assert "Kestrel" not in {nom for nom, _ in rallye.MARQUES}
    assert len({sigle for _, sigle in rallye.MARQUES}) == len(rallye.MARQUES)


def test_valeurs_plausibles_et_fictives():
    v = rallye.verite(GRAINE, TAILLE)
    c = v["collections"]
    for r in c["rallyes"]:
        assert r["date_debut"] <= r["date_fin"] and re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["date_debut"])
        assert r["surface"] in ("Asphalte", "Terre", "Neige", "Mixte")
        assert r["nom"] and r["lieu"] and r["championnat"] and r["km_chrono"] > 0
    for s in c["speciales"]:
        assert 4.0 <= s["km"] <= 28.0
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", s["depart"])
    for x in c["chassis"]:
        assert re.fullmatch(r"DEMO-[A-Z]{3}-\d{4}", x["code"])
        assert 2000 <= x["annee"] <= 2024
    for e in c["engages"]:
        assert "démo" in e["voiture"]
    assert "démo" in rallye.MARQUE.lower()


def test_verite_coherente_et_serialisable():
    v = rallye.verite(GRAINE, TAILLE)
    assert json.loads(json.dumps(v)) == v
    assert v["graine"] == GRAINE and v["taille"] == TAILLE and v["par_page"] == 6
    assert list(v["collections"]) == COLLECTIONS
    assert v["cles"] == {
        "rallyes": ["id"],
        "speciales": ["id"],
        "temps": ["speciale", "numero"],
        "classements": ["rallye", "numero"],
        "engages": ["rallye", "numero"],
        "chassis": ["code"],
        "historique": ["chassis", "rallye"],
        "pilotes": ["id"],
    }
    for nom, cle in v["cles"].items():
        cles = [tuple(ligne[k] for k in cle) for ligne in v["collections"][nom]]
        assert len(cles) == len(set(cles)), nom  # la clé identifie une ligne et une seule


def test_champs_de_la_verite_sont_ceux_du_contrat():
    """Les noms de champs sont le contrat avec la recette (§ 4 (b) et § 7 du document de conception)."""
    c = rallye.verite(GRAINE, TAILLE)["collections"]
    attendus = {
        "rallyes": {"id", "nom", "date_debut", "date_fin", "championnat", "surface", "lieu", "km_chrono"},
        "speciales": {"id", "rallye", "numero", "nom", "km", "depart", "annulee"},
        "temps": {"speciale", "numero", "rang", "pilote_id", "pilote", "copilote", "voiture", "temps", "temps_ms"},
        "classements": {"rallye", "numero", "rang", "temps_total_ms"},
        "engages": {"rallye", "numero", "pilote_id", "copilote", "voiture", "chassis", "groupe"},
        "chassis": {"code", "marque", "modele", "annee"},
        "historique": {"chassis", "rallye", "date", "pilote_id", "resultat"},
        "pilotes": {"id", "nom", "nationalite"},
    }
    for nom, champs in attendus.items():
        assert c[nom], nom
        for ligne in c[nom]:
            assert set(ligne) == champs, nom


def test_coherence_interne_des_resultats():
    c = rallye.verite(GRAINE, TAILLE)["collections"]
    engages = {(e["rallye"], e["numero"]): e for e in c["engages"]}
    speciales = {s["id"]: s for s in c["speciales"]}
    for t in c["temps"]:
        s = speciales[t["speciale"]]
        assert not s["annulee"]
        e = engages[(s["rallye"], t["numero"])]
        assert (t["pilote_id"], t["copilote"], t["voiture"]) == (e["pilote_id"], e["copilote"], e["voiture"])
        assert (t["temps_ms"] is None) == (t["temps"] == "Abandon") == (t["rang"] is None)
        if t["temps_ms"] is not None:
            assert t["temps_ms"] % 100 == 0 and t["temps_ms"] > 0
    # Le temps total d'un classé est la somme de ses temps de spéciale ; un abandon n'a ni rang ni total.
    for k in c["classements"]:
        lignes = [
            t["temps_ms"]
            for t in c["temps"]
            if speciales[t["speciale"]]["rallye"] == k["rallye"] and t["numero"] == k["numero"]
        ]
        if k["rang"] is None:
            assert k["temps_total_ms"] is None and None in lignes
        else:
            assert k["temps_total_ms"] == sum(lignes)
    # Un historique par engagé, vers un châssis et un pilote qui ont leur page.
    assert len(c["historique"]) == len(c["engages"])
    codes, pilotes = {x["code"] for x in c["chassis"]}, {p["id"] for p in c["pilotes"]}
    assert {e["chassis"] for e in c["engages"]} == codes
    assert {e["pilote_id"] for e in c["engages"]} == pilotes


def test_formats_de_duree():
    assert rallye.duree(598_700) == "9:58.7"
    assert rallye.duree(3_723_400) == "1:02:03.4"
    assert rallye.duree(59_000) == "0:59.0"
    assert rallye.ecart(12_300) == "+0:12.3"
    assert rallye.ecart(3_723_400) == "+1:02:03.4"


def test_pages_attendues_de_la_verite():
    v = rallye.verite(GRAINE, TAILLE)
    pages = v["pages"]
    assert pages == rallye.pages_attendues(GRAINE, TAILLE)
    adresses = [p["adresse"] for p in pages]
    assert len(adresses) == len(set(adresses)) == v["nb_pages"]
    for p in pages:
        assert re.fullmatch(TYPES_DE_PAGE[p["type"]], p["adresse"]), p
    c = v["collections"]
    par_type = defaultdict(int)
    for p in pages:
        par_type[p["type"]] += 1
    assert par_type["saisons"] == 1
    par_saison = [
        min(rallye.RALLYES_PAR_SAISON, TAILLE - rallye.RALLYES_PAR_SAISON * k)
        for k in range(-(-TAILLE // rallye.RALLYES_PAR_SAISON))
    ]
    assert par_type["calendrier"] == sum(-(-n // rallye.PAR_PAGE) for n in par_saison)
    assert par_type["rallye"] == par_type["classement"] == par_type["engages"] == TAILLE
    assert par_type["speciale"] == len(c["speciales"])
    assert par_type["chassis"] == len(c["chassis"]) and par_type["pilote"] == len(c["pilotes"])
    assert v["pages_par_type"] == dict(par_type)


# --- Pièges ------------------------------------------------------------------------------------


def test_chaque_piege_est_liste_et_present():
    presents = rallye.pieges_presents(rallye.verite(GRAINE, TAILLE))
    assert set(presents) == set(rallye.PIEGES)
    assert all(rallye.PIEGES[nom] for nom in rallye.PIEGES)  # chacun est décrit
    assert [nom for nom, n in presents.items() if n == 0] == []


def test_pieges_verifies_sans_la_fonction_du_module():
    """Même contrôle, écrit ici directement sur la vérité : le test ne se contente pas de croire le module."""
    c = rallye.verite(GRAINE, TAILLE)["collections"]
    temps = c["temps"]
    # Temps à minutes (9:58.7) dans les spéciales, à heures (1:02:03.4) dans le classement.
    assert any(re.fullmatch(r"\d{1,2}:\d{2}\.\d", t["temps"]) for t in temps)
    assert any(ligne["temps_total_ms"] >= 3_600_000 for ligne in c["classements"] if ligne["rang"])
    assert any(ligne["temps_total_ms"] < 3_600_000 for ligne in c["classements"] if ligne["rang"])
    # Abandons sans temps, dans les spéciales et au classement.
    assert any(t["temps"] == "Abandon" and t["temps_ms"] is None and t["rang"] is None for t in temps)
    assert any(ligne["rang"] is None and ligne["temps_total_ms"] is None for ligne in c["classements"])
    # Ex aequo : même rang et même temps.
    groupes = defaultdict(list)
    for t in temps:
        if t["rang"]:
            groupes[(t["speciale"], t["rang"])].append(t["temps_ms"])
    assert any(len(v) > 1 and len(set(v)) == 1 for v in groupes.values())
    # Spéciale annulée : sans aucun temps.
    annulees = [s["id"] for s in c["speciales"] if s["annulee"]]
    assert annulees and not any(t["speciale"] in annulees for t in temps)
    # Châssis qui passe de pilote en pilote et de saison en saison.
    saison = {r["id"]: r["date_debut"][:4] for r in c["rallyes"]}
    par_chassis = defaultdict(list)
    for h in c["historique"]:
        par_chassis[h["chassis"]].append((saison[h["rallye"]], h["pilote_id"]))
    assert any(len({s for s, _ in v}) >= 2 and len({p for _, p in v}) >= 2 for v in par_chassis.values())
    # Noms à accents et à apostrophes.
    noms = [r["nom"] for r in c["rallyes"]] + [s["nom"] for s in c["speciales"]] + [p["nom"] for p in c["pilotes"]]
    assert any("'" in n for n in noms) and any(re.search(r"[éèêëïôûç]", n, re.I) for n in noms)


def test_pieges_a_la_taille_par_defaut():
    from shadowlab.config import charger

    r = charger()
    presents = rallye.pieges_presents(rallye.verite(r.rallye_graine, r.rallye_taille))
    assert r.rallye_taille == 24
    assert set(presents) == set(rallye.PIEGES)
    assert [nom for nom, n in presents.items() if n == 0] == []


def test_taille_a_partir_de_laquelle_chaque_piege_est_garanti():
    """`GARANTI_A_PARTIR_DE` dit la vérité : présent à toute taille ≥ au seuil, pour plusieurs graines."""
    assert set(rallye.GARANTI_A_PARTIR_DE) == set(rallye.PIEGES)
    for graine in (GRAINE, 1, 2, 3, 42):
        for taille in range(1, 26):
            presents = rallye.pieges_presents(rallye.verite(graine, taille))
            for nom, seuil in rallye.GARANTI_A_PARTIR_DE.items():
                if taille >= seuil:
                    assert presents[nom] > 0, (nom, graine, taille)
    # Le seuil le plus haut est celui du châssis qui change de saison : il faut deux saisons.
    assert rallye.GARANTI_A_PARTIR_DE["chassis_de_pilote_en_pilote_et_de_saison_en_saison"] == (
        rallye.RALLYES_PAR_SAISON + 1
    )


def test_colonnes_dans_un_autre_ordre_entre_temps_et_classement():
    assert rallye.COLONNES_TEMPS != rallye.COLONNES_CLASSEMENT
    communes = [c for c in rallye.COLONNES_TEMPS if c in rallye.COLONNES_CLASSEMENT]
    assert [rallye.COLONNES_TEMPS.index(c) for c in communes] != [rallye.COLONNES_CLASSEMENT.index(c) for c in communes]


# --- Site --------------------------------------------------------------------------------------


@pytest.fixture
def client_rallye(reglages, monkeypatch):
    monkeypatch.setenv("SHADOWLAB_RALLYE_TAILLE", str(TAILLE))
    monkeypatch.setenv("SHADOWLAB_RALLYE_GRAINE", str(GRAINE))
    from fastapi.testclient import TestClient

    from shadowlab.config import charger
    from shadowlab.site.app import creer_app

    with TestClient(creer_app(charger()), base_url="http://127.0.0.1") as c:
        yield c


def parcourir(client) -> dict[str, str]:
    """Suit les liens depuis la page des saisons, comme le ferait une recette : adresse → HTML reçu."""
    vues: dict[str, str] = {}
    a_faire = ["/lab/rallye/saisons"]
    while a_faire:
        adresse = a_faire.pop(0)
        if adresse in vues:
            continue
        r = client.get(adresse)
        assert r.status_code == 200, adresse
        vues[adresse] = r.text
        sel = Selector(r.text)
        for regle in LIENS_A_SUIVRE:
            a_faire += sel.css(regle).getall()
    return vues


def texte(noeud) -> str:
    """Texte d'un nœud (ou d'une liste de nœuds), espaces réduits."""
    return " ".join(" ".join(noeud.xpath(".//text()").getall()).split())


def entier(valeur: str) -> int:
    return int(re.sub(r"\D", "", valeur))


def nombre(valeur: str) -> float:
    return float(re.search(r"[\d.,]+", valeur).group().replace(",", "."))


def duree_ms(valeur: str) -> int:
    morceaux = [float(m) for m in valeur.split(":")]
    secondes = 0.0
    for m in morceaux:
        secondes = secondes * 60 + m
    return round(secondes * 1000)


def lignes(table):
    """Lignes d'un tableau : {nom de colonne: cellule}. L'en-tête est la première ligne à cellules th."""
    toutes = table.css("tr")
    avec_entete = [tr for tr in toutes if tr.css("th")]
    if not avec_entete:  # pas de tableau (spéciale annulée) : aucune ligne, la vérité n'en attend aucune
        return
    entetes = [texte(th) for th in avec_entete[0].css("th")]
    for tr in toutes:
        cellules = tr.css("td")
        if cellules:
            assert len(cellules) == len(entetes)
            yield dict(zip(entetes, cellules, strict=True))


def identifiant(motif: str, adresse: str) -> int:
    return int(re.search(motif, adresse).group(1))


def lire_page(type_page: str, adresse: str, html: str) -> dict[str, list[dict]]:
    """Ce qu'on lit d'une page, écrit ici à partir du seul HTML (aucun attribut `data-champ` sur ce site)."""
    sel = Selector(html)
    lu: dict[str, list[dict]] = defaultdict(list)
    if type_page == "rallye":
        lu["rallyes"].append(
            {
                "id": identifiant(r"/rallyes/(\d+)$", adresse),
                "nom": texte(sel.css("h1.titre")),
                "date_debut": sel.css("p.infos time.debut::attr(datetime)").get(),
                "date_fin": sel.css("p.infos time.fin::attr(datetime)").get(),
                "championnat": texte(sel.css("dl.fiche dd.championnat")),
                "surface": texte(sel.css("dl.fiche dd.surface")),
                "lieu": texte(sel.css("dl.fiche dd.lieu")),
                "km_chrono": nombre(texte(sel.css("dl.fiche dd.km"))),
            }
        )
    elif type_page == "speciale":
        id_speciale = identifiant(r"/speciales/(\d+)$", adresse)
        titre = re.fullmatch(r"ES(\d+) · (.+)", texte(sel.css("h1.titre")))
        lu["speciales"].append(
            {
                "id": id_speciale,
                "rallye": identifiant(r"/rallyes/(\d+)", sel.css("nav.fil a.rallye::attr(href)").get()),
                "numero": int(titre.group(1)),
                "nom": titre.group(2),
                "km": nombre(texte(sel.css("p.details .km"))),
                "depart": sel.css("p.details time::attr(datetime)").get(),
                "annulee": bool(sel.css("p.annulee")),
            }
        )
        for ligne in lignes(sel.css("table.temps")):
            pilote = ligne["Équipage"].css("a.pilote")
            lu["temps"].append(
                {
                    "speciale": id_speciale,
                    "numero": entier(texte(ligne["N°"])),
                    "rang": None if texte(ligne["Pos."]) == "-" else entier(texte(ligne["Pos."])),
                    "pilote_id": identifiant(r"/pilotes/(\d+)", pilote.attrib["href"]),
                    "pilote": texte(pilote),
                    "copilote": texte(ligne["Équipage"].css(".copilote")),
                    "voiture": texte(ligne["Voiture"]),
                    "temps": texte(ligne["Temps"]),
                    "temps_ms": None if texte(ligne["Temps"]) == "Abandon" else duree_ms(texte(ligne["Temps"])),
                }
            )
    elif type_page == "classement":
        id_rallye = identifiant(r"/rallyes/(\d+)/", adresse)
        for ligne in lignes(sel.css("table.classement")):
            lu["classements"].append(
                {
                    "rallye": id_rallye,
                    "numero": entier(texte(ligne["N°"])),
                    "rang": None if texte(ligne["Pos."]) == "Ab." else entier(texte(ligne["Pos."])),
                    "temps_total_ms": None
                    if texte(ligne["Temps total"]) == "-"
                    else duree_ms(texte(ligne["Temps total"])),
                }
            )
    elif type_page == "engages":
        id_rallye = identifiant(r"/rallyes/(\d+)/", adresse)
        for ligne in lignes(sel.css("table.engages")):
            lu["engages"].append(
                {
                    "rallye": id_rallye,
                    "numero": entier(texte(ligne["N°"])),
                    "pilote_id": identifiant(r"/pilotes/(\d+)", ligne["Pilote"].css("a::attr(href)").get()),
                    "copilote": texte(ligne["Copilote"]),
                    "voiture": texte(ligne["Voiture"]),
                    "chassis": texte(ligne["Châssis"]),
                    "groupe": texte(ligne["Groupe"]),
                }
            )
    elif type_page == "chassis":
        code = re.search(r"/chassis/([\w-]+)$", adresse).group(1)
        lu["chassis"].append(
            {
                "code": code,
                "marque": texte(sel.css("dl.fiche dd.marque")),
                "modele": texte(sel.css("dl.fiche dd.modele")),
                "annee": entier(texte(sel.css("dl.fiche dd.annee"))),
            }
        )
        for ligne in lignes(sel.css("table.historique")):
            lu["historique"].append(
                {
                    "chassis": code,
                    "rallye": identifiant(r"/rallyes/(\d+)", ligne["Rallye"].css("a::attr(href)").get()),
                    "date": ligne["Date"].css("time::attr(datetime)").get(),
                    "pilote_id": identifiant(r"/pilotes/(\d+)", ligne["Pilote"].css("a::attr(href)").get()),
                    "resultat": texte(ligne["Résultat"]),
                }
            )
    elif type_page == "pilote":
        lu["pilotes"].append(
            {
                "id": identifiant(r"/pilotes/(\d+)$", adresse),
                "nom": texte(sel.css("h1.titre")),
                "nationalite": texte(sel.css("dl.fiche dd.nationalite")),
            }
        )
    return lu


def type_de(adresse: str) -> str:
    types = [t for t, motif in TYPES_DE_PAGE.items() if re.fullmatch(motif, adresse)]
    assert len(types) == 1, adresse
    return types[0]


def test_parcours_complet_egale_la_verite(client_rallye):
    vues = parcourir(client_rallye)
    verite = rallye.verite(GRAINE, TAILLE)
    # Toutes les pages attendues, et rien d'autre.
    assert sorted(vues) == sorted(p["adresse"] for p in verite["pages"])
    assert len(vues) == verite["nb_pages"]
    for p in verite["pages"]:
        assert type_de(p["adresse"]) == p["type"]
    # Toutes les collections retrouvées, champ pour champ.
    recolte: dict[str, list[dict]] = defaultdict(list)
    for adresse, html in vues.items():
        for nom, donnees in lire_page(type_de(adresse), adresse, html).items():
            recolte[nom] += donnees
    for nom in COLLECTIONS:
        cle = verite["cles"][nom]
        lu = {tuple(ligne[k] for k in cle): ligne for ligne in recolte[nom]}
        assert len(lu) == len(recolte[nom]), f"{nom} : clé en double dans la récolte"
        attendu = {tuple(ligne[k] for k in cle): ligne for ligne in verite["collections"][nom]}
        assert lu == attendu, nom


def test_calendrier_pagine_par_six(client_rallye):
    premiere = Selector(client_rallye.get("/lab/rallye/saisons/2023").text)
    assert len(premiere.css("table.calendrier td.rallye a")) == 6
    assert premiere.css("nav.pages a.suivante::attr(href)").get() == "/lab/rallye/saisons/2023?page=2"
    assert not premiere.css("nav.pages a.precedente")
    seconde = Selector(client_rallye.get("/lab/rallye/saisons/2023?page=2").text)
    assert len(seconde.css("table.calendrier td.rallye a")) == 2
    assert not seconde.css("nav.pages a.suivante")
    assert seconde.css("nav.pages a.precedente::attr(href)").get() == "/lab/rallye/saisons/2023"
    # Une saison de 4 rallyes tient sur une page.
    courte = Selector(client_rallye.get("/lab/rallye/saisons/2024").text)
    assert len(courte.css("table.calendrier td.rallye a")) == 4 and not courte.css("nav.pages a.suivante")
    entetes = [texte(th) for th in premiere.css("table.calendrier th")]
    assert entetes == ["Date", "Rallye", "Championnat", "Surface", "Lieu"]


def test_liste_des_saisons(client_rallye):
    sel = Selector(client_rallye.get("/lab/rallye/saisons").text)
    liens = sel.css("ul.saisons a")
    assert sorted(texte(a) for a in liens) == ["Saison 2023", "Saison 2024"]
    assert sorted(liens.css("::attr(href)").getall()) == ["/lab/rallye/saisons/2023", "/lab/rallye/saisons/2024"]


def test_page_rallye_liens_et_tableau_des_speciales(client_rallye):
    sel = Selector(client_rallye.get("/lab/rallye/rallyes/1").text)
    assert sel.css("a.classement::attr(href)").get() == "/lab/rallye/rallyes/1/classement"
    assert sel.css("a.engages::attr(href)").get() == "/lab/rallye/rallyes/1/engages"
    speciales = [s for s in rallye.verite(GRAINE, TAILLE)["collections"]["speciales"] if s["rallye"] == 1]
    assert len(sel.css("table.speciales td.nom a")) == len(speciales)
    assert sel.css("nav.fil")  # fil d'Ariane


def test_entetes_des_tableaux(client_rallye):
    verite = rallye.verite(GRAINE, TAILLE)["collections"]
    speciale = next(s for s in verite["speciales"] if not s["annulee"])
    sel = Selector(client_rallye.get(f"/lab/rallye/speciales/{speciale['id']}").text)
    assert [texte(th) for th in sel.css("table.temps th")] == rallye.COLONNES_TEMPS == [
        "Pos.", "N°", "Équipage", "Voiture", "Temps", "Écart",
    ]  # fmt: skip
    sel = Selector(client_rallye.get("/lab/rallye/rallyes/1/classement").text)
    assert [texte(th) for th in sel.css("table.classement th")] == rallye.COLONNES_CLASSEMENT == [
        "Pos.", "N°", "Équipage", "Groupe", "Voiture", "Temps total", "Écart",
    ]  # fmt: skip
    sel = Selector(client_rallye.get("/lab/rallye/rallyes/1/engages").text)
    assert [texte(th) for th in sel.css("table.engages th")] == [
        "N°", "Pilote", "Copilote", "Voiture", "Châssis", "Groupe",
    ]  # fmt: skip


def test_equipage_pilote_et_copilote_dans_une_meme_cellule(client_rallye):
    verite = rallye.verite(GRAINE, TAILLE)["collections"]
    speciale = next(s for s in verite["speciales"] if not s["annulee"])
    sel = Selector(client_rallye.get(f"/lab/rallye/speciales/{speciale['id']}").text)
    for ligne in lignes(sel.css("table.temps")):
        cellule = ligne["Équipage"]
        assert len(cellule.css("a.pilote")) == 1 and len(cellule.css(".copilote")) == 1


def test_speciale_annulee_sans_tableau(client_rallye):
    annulee = next(s for s in rallye.verite(GRAINE, TAILLE)["collections"]["speciales"] if s["annulee"])
    r = client_rallye.get(f"/lab/rallye/speciales/{annulee['id']}")
    assert r.status_code == 200
    sel = Selector(r.text)
    assert sel.css("h1.titre") and sel.css("p.annulee") and sel.css("p.details .km")
    assert not sel.css("table.temps") and not sel.css("table")


def test_ex_aequo_meme_rang_et_meme_temps_dans_la_page(client_rallye):
    temps = rallye.verite(GRAINE, TAILLE)["collections"]["temps"]
    groupes = defaultdict(list)
    for t in temps:
        if t["rang"]:
            groupes[(t["speciale"], t["rang"])].append(t)
    ex_aequo = next(v for v in groupes.values() if len(v) > 1)
    sel = Selector(client_rallye.get(f"/lab/rallye/speciales/{ex_aequo[0]['speciale']}").text)
    vus = [
        (texte(ligne["Pos."]), texte(ligne["Temps"]))
        for ligne in lignes(sel.css("table.temps"))
        if entier(texte(ligne["N°"])) in {t["numero"] for t in ex_aequo}
    ]
    assert len(vus) == len(ex_aequo) >= 2 and len(set(vus)) == 1


def test_historique_d_un_chassis_traverse_les_saisons(client_rallye):
    c = rallye.verite(GRAINE, TAILLE)["collections"]
    par_chassis = defaultdict(list)
    for h in c["historique"]:
        par_chassis[h["chassis"]].append(h)
    code = max(par_chassis, key=lambda k: len(par_chassis[k]))
    sel = Selector(client_rallye.get(f"/lab/rallye/chassis/{code}").text)
    assert len(list(lignes(sel.css("table.historique")))) == len(par_chassis[code]) >= 3
    # L'historique pointe vers des rallyes d'autres saisons : de simples liens, que la recette ne suit pas.
    assert len(sel.css("table.historique td a[href*='/rallyes/']")) == len(par_chassis[code])


def test_inconnu_donne_404(client_rallye):
    for adresse in (
        "/lab/rallye/saisons/1999",
        "/lab/rallye/saisons/abcd",
        "/lab/rallye/saisons/2023?page=0",
        "/lab/rallye/saisons/2023?page=3",
        "/lab/rallye/saisons/2024?page=2",
        "/lab/rallye/rallyes/0",
        f"/lab/rallye/rallyes/{TAILLE + 1}",
        "/lab/rallye/rallyes/abc",
        f"/lab/rallye/rallyes/{TAILLE + 1}/classement",
        f"/lab/rallye/rallyes/{TAILLE + 1}/engages",
        "/lab/rallye/rallyes/1/inconnu",
        "/lab/rallye/speciales/0",
        "/lab/rallye/speciales/999999",
        "/lab/rallye/speciales/abc",
        "/lab/rallye/chassis/DEMO-XXX-0000",
        "/lab/rallye/chassis/n-importe-quoi",
        "/lab/rallye/pilotes/999999",
        "/lab/rallye/pilotes/abc",
    ):
        assert client_rallye.get(adresse).status_code == 404, adresse


def test_racine_renvoie_aux_saisons(client_rallye):
    r = client_rallye.get("/lab/rallye", follow_redirects=False)
    assert r.status_code in (301, 302, 303, 307, 308) and r.headers["location"] == "/lab/rallye/saisons"


def test_pages_protegees_comme_le_reste_du_site(client_rallye):
    r = client_rallye.get("/lab/rallye/saisons")
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert 'name="sl-session"' in r.text and "observateur.js" in r.text
    assert 'href="/lab/static/rallye.css"' in r.text
    assert not re.search(r'(?:src|href)="https?://', r.text)  # aucune requête vers un tiers
    assert "data-champ" not in r.text  # du HTML de site ordinaire


def test_pages_servies_par_le_meme_observateur_que_la_vitrine(client_rallye):
    """Le site passe par l'intergiciel de /lab : une visite est observée, comme celle de la vitrine."""
    r_rallye = client_rallye.get("/lab/rallye/saisons")
    r_vitrine = client_rallye.get("/lab/vitrine")
    for r in (r_rallye, r_vitrine):
        assert r.status_code == 200 and 'name="sl-session"' in r.text
        assert r.headers["content-security-policy"] == r_rallye.headers["content-security-policy"]


def test_echappement_html():
    u = rallye.construire(GRAINE, 4)
    pilote = replace(u.pilotes[0], nom="<script>alert(1)</script>", nationalite="a & b <i>")
    page = rallye.page_pilote("", u, pilote)
    assert "<script>alert" not in page and "&lt;script&gt;" in page and "<i>" not in page
    assert Selector(page).css("h1.titre::text").get() == "<script>alert(1)</script>"

    course = replace(u.rallyes[0], nom="<img src=x onerror=1>", lieu="<b>x</b> & y")
    page = rallye.page_rallye("", u, course)
    assert "<img src=x" not in page and "<b>x</b>" not in page
    assert Selector(page).css("h1.titre::text").get() == "<img src=x onerror=1>"
    assert Selector(page).css("dl.fiche dd.lieu::text").get() == "<b>x</b> & y"

    voiture = replace(u.chassis[0], marque="<u>M</u>", modele="\"'><x>")
    page = rallye.page_chassis("", u, voiture)
    assert "<u>M</u>" not in page and "<x>" not in page

    speciale = replace(u.speciales[0], nom="<svg onload=1>")
    page = rallye.page_speciale("", u, speciale)
    assert "<svg onload" not in page and "&lt;svg onload=1&gt;" in page


MAL = '"><script>alert(1)</script>'


def _sans_injection(page: str):
    """Rien de la valeur hostile ne sort brut : ni balise, ni guillemet qui fermerait un attribut."""
    assert MAL not in page
    reste = page.replace('<script type="module" src="/lab/static/observateur.js"></script>', "")
    assert "<script" not in reste and "alert(1)</script>" not in reste
    assert 'href=""><' not in page and '"><script' not in page


def test_echappement_des_attributs_et_des_adresses():
    u = rallye.construire(GRAINE, 4)
    ancien = u.chassis[0].code
    vilain = replace(u.chassis[0], code=MAL)
    pilote_ancien = u.engages[0].pilote_id
    univers = rallye.Univers(
        u.rallyes,
        [replace(s, depart="2024-05-17T08:" + MAL) if s.id == 1 else s for s in u.speciales],
        [
            replace(e, chassis=MAL if e.chassis == ancien else e.chassis, pilote_id=MAL if e.pilote_id == pilote_ancien else e.pilote_id)
            for e in u.engages
        ],
        u.temps,
        u.classements,
        [vilain, *u.chassis[1:]],
        [replace(p, id=MAL) if p.id == pilote_ancien else p for p in u.pilotes],
        [replace(h, chassis=MAL) if h.chassis == ancien else h for h in u.historique],
    )
    rallyes = [r for r in univers.rallyes if any(e.chassis == MAL for e in univers.engages_de(r.id))]
    assert rallyes
    pages = [
        rallye.page_chassis("", univers, vilain),
        rallye.page_pilote("", univers, univers.trouver_pilote(MAL)),
        rallye.page_speciale("", univers, univers.trouver_speciale(1)),
        rallye.page_rallye("", univers, univers.trouver_rallye(1)),
        rallye.page_engages("", univers, rallyes[0]),
        rallye.page_classement("", univers, rallyes[0]),
        rallye.page_saisons('"><script>', univers),
    ]
    for page in pages:
        _sans_injection(page)
    assert "&quot;&gt;&lt;script&gt;" in pages[0]  # le code du châssis sort échappé
    assert "08h" in pages[2]
    # Les fonctions d'adresse elles-mêmes sont sûres : la vérité garde la forme brute, le HTML l'échappe.
    assert rallye.adresse_chassis("a b") == "/lab/rallye/chassis/a b"


def test_reglages_par_defaut(reglages):
    assert reglages.rallye_graine == 20261112
    assert reglages.rallye_taille == 24


def test_reglages_pris_dans_l_environnement(reglages, monkeypatch):
    from shadowlab.config import charger

    monkeypatch.setenv("SHADOWLAB_RALLYE_GRAINE", "7")
    monkeypatch.setenv("SHADOWLAB_RALLYE_TAILLE", "0")
    r = charger()
    assert r.rallye_graine == 7 and r.rallye_taille == 1  # au moins un rallye, comme la vitrine


def test_lien_piege_masque_sur_les_pages_rallye(client_rallye):
    """Le lien piège ne doit jamais être visible d'un humain : la feuille du site porte la règle `.sl-hp`."""
    page = rallye.page_saisons("", rallye.construire(GRAINE, TAILLE), honeypot=True)
    sel = Selector(page)
    assert sel.css("a.sl-hp"), "le lien piège doit être présent quand les honeypots sont actifs"
    css = "".join(client_rallye.get(href).text for href in sel.css('link[rel="stylesheet"]::attr(href)').getall())
    regle = re.search(r"\.sl-hp\s*\{([^}]*)\}", css)
    assert regle, "aucune règle .sl-hp dans les feuilles de style de la page"
    assert "position: absolute" in regle.group(1) and "-9999px" in regle.group(1)
    assert not Selector(rallye.page_saisons("", rallye.construire(GRAINE, TAILLE))).css("a.sl-hp")


def test_feuille_de_style_servie(client_rallye):
    r = client_rallye.get("/lab/static/rallye.css")
    assert r.status_code == 200 and "table" in r.text
