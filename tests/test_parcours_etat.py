"""État d'une récolte (SQLite) : adresse canonique, file en profondeur d'abord, une page = une transaction."""

import sqlite3

import pytest

from shadowlab.engines.noezia.etat import Etat, canonique
from shadowlab.engines.noezia.recettes import Enregistrement

QUAND = "2026-11-12T10:00:00+00:00"


@pytest.fixture
def etat(tmp_path):
    e = Etat(tmp_path / "etat.sqlite3")
    yield e
    e.fermer()


@pytest.fixture
def passe(etat):
    return etat.ouvrir_passe(
        recette="essai",
        empreinte="sha256:abc",
        texte_recette="recette: 1\n",
        chemin_recette="configs/recettes/essai.yaml",
        moteur={"nom": "http"},
        options={"tranche": {}},
        quand=QUAND,
    )


# --- Adresse canonique -------------------------------------------------------------------------


def test_canonique_schema_hote_port_et_fragment():
    assert canonique("HTTP://Exemple.TEST:80/a/b#haut") == "http://exemple.test/a/b"
    assert canonique("https://exemple.test:443/a") == "https://exemple.test/a"
    assert canonique("http://exemple.test:8080/a") == "http://exemple.test:8080/a"
    assert canonique("http://exemple.test") == "http://exemple.test/"


def test_canonique_retire_les_parametres_ignores_et_trie_les_autres():
    assert canonique("http://h/a?sl=jeton&page=2&b=1", ignores=["sl"]) == "http://h/a?b=1&page=2"
    assert canonique("http://h/a?b=1&page=2", ["sl"]) == canonique("http://h/a?page=2&b=1&sl=x", ["sl"])
    assert canonique("http://h/a?sl=jeton", ["sl"]) == "http://h/a"


def test_canonique_garde_les_parametres_vides_et_le_chemin_tel_quel():
    assert canonique("http://h/a?x=&y=1") == "http://h/a?x=&y=1"
    assert canonique("http://h/A/b%20c") == "http://h/A/b%20c"  # la casse du chemin compte


def test_canonique_ne_confond_pas_page_1_et_sans_page():
    # limite connue et assumée (§ 5) : deux adresses pour la même page sont lues deux fois
    assert canonique("http://h/annonces") != canonique("http://h/annonces?page=1")


# --- Passes ------------------------------------------------------------------------------------


def test_les_passes_sont_numerotees_a_partir_de_1(etat, passe):
    assert passe == 1
    assert etat.ouvrir_passe("essai", "sha256:abc", "t", "c", {"nom": "http"}, {}, QUAND) == 2
    ligne = etat.passe(1)
    assert ligne["statut"] == "en_cours" and ligne["empreinte"] == "sha256:abc"
    assert ligne["moteur"] == {"nom": "http"} and ligne["texte_recette"] == "recette: 1\n"
    assert etat.derniere_passe()["numero"] == 2


def test_pas_de_passe_dans_une_base_neuve(etat):
    assert etat.derniere_passe() is None


def test_terminer_une_passe(etat, passe):
    etat.terminer_passe(passe, "arretee", {"signe": "statut", "statut": 429}, QUAND)
    ligne = etat.passe(passe)
    assert ligne["statut"] == "arretee" and ligne["arret"]["statut"] == 429 and ligne["fin"] == QUAND


# --- File : profondeur d'abord, dédoublonnage -------------------------------------------------


def adresses(etat, passe, n=100):
    """Dépile jusqu'à n pages et rend leurs adresses, dans l'ordre."""
    rendues = []
    while len(rendues) < n and (page := etat.prochaine(passe)) is not None:
        rendues.append(page.adresse)
    return rendues


def test_la_file_est_vide_au_depart(etat, passe):
    assert etat.prochaine(passe) is None


def test_les_departs_sortent_dans_l_ordre_ecrit(etat, passe):
    etat.empiler(passe, [("http://h/1", "liste"), ("http://h/2", "liste"), ("http://h/3", "liste")])
    assert adresses(etat, passe) == ["http://h/1", "http://h/2", "http://h/3"]


def test_profondeur_d_abord_les_enfants_avant_le_frere(etat, passe):
    etat.empiler(passe, [("http://h/a", "liste"), ("http://h/b", "liste")])
    premiere = etat.prochaine(passe)
    assert premiere.adresse == "http://h/a"
    etat.empiler(passe, [("http://h/a1", "fiche"), ("http://h/a2", "fiche")])
    assert etat.prochaine(passe).adresse == "http://h/a1"
    etat.empiler(passe, [("http://h/a1x", "x")])
    # a1x (enfant de a1) avant a2 (frère de a1), puis a2, puis b
    assert adresses(etat, passe) == ["http://h/a1x", "http://h/a2", "http://h/b"]


def test_une_adresse_canonique_n_entre_qu_une_fois(etat, passe):
    r = etat.empiler(
        passe, [("http://h/a?sl=1", "liste"), ("http://h/a?sl=2", "liste"), ("http://H:80/a#x", "liste")], ["sl"]
    )
    assert r.neufs == 1 and r.deja_vus == 2
    assert adresses(etat, passe) == ["http://h/a?sl=1"]  # la première forme rencontrée est celle qu'on demandera
    # même une page déjà faite ne revient pas
    r = etat.empiler(passe, [("http://h/a", "liste")], ["sl"])
    assert r.neufs == 0 and r.deja_vus == 1


def test_le_dedoublonnage_est_propre_a_la_passe(etat, passe):
    etat.empiler(passe, [("http://h/a", "liste")])
    autre = etat.ouvrir_passe("essai", "sha256:abc", "t", "c", {}, {}, QUAND)
    assert etat.empiler(autre, [("http://h/a", "liste")]).neufs == 1


def test_un_lien_deja_en_file_garde_sa_place(etat, passe):
    etat.empiler(passe, [("http://h/a", "x"), ("http://h/b", "x")])
    etat.prochaine(passe)  # a
    etat.empiler(passe, [("http://h/b", "x"), ("http://h/c", "x")])  # b est déjà en file : seul c est neuf
    assert adresses(etat, passe) == ["http://h/c", "http://h/b"]


def test_plafond_par_type_de_page(etat, passe):
    r = etat.empiler(
        passe,
        [("http://h/r1", "rallye"), ("http://h/r2", "rallye"), ("http://h/r3", "rallye"), ("http://h/p1", "pilote")],
        plafonds={"rallye": 2},
    )
    assert r.neufs == 3 and r.exclus == 1
    assert adresses(etat, passe) == ["http://h/r1", "http://h/r2", "http://h/p1"]


# --- Une page = une transaction ---------------------------------------------------------------


def annonce(ref, **donnees):
    return Enregistrement("annonces", (ref,), {"reference": ref, **donnees})


def test_page_faite_ecrit_page_enregistrements_et_liens_ensemble(etat, passe):
    etat.empiler(passe, [("http://h/liste", "liste")])
    page = etat.prochaine(passe)
    assert etat.pages(passe, "en_cours") == 1
    etat.terminer_page(
        page,
        etat="faite",
        statut=200,
        decision="ok",
        duree_chargement_ms=12.5,
        duree_totale_ms=20.0,
        enregistrements=[annonce("AN-1", prix=100), annonce("AN-2", prix=200)],
        liens=[("http://h/f1", "fiche"), ("http://h/f2", "fiche")],
        quand=QUAND,
    )
    assert etat.pages(passe, "faite") == 1 and etat.pages(passe, "en_cours") == 0
    assert etat.pages(passe, "a_faire") == 2
    lues = etat.enregistrements("annonces")
    assert [e["reference"] for e in lues] == ["AN-1", "AN-2"]
    assert lues[0]["_page"] == "http://h/liste" and lues[0]["_passe"] == passe and lues[0]["_vu_le"] == QUAND
    ligne = etat.lignes_pages(passe)[0]
    assert ligne["statut"] == 200 and ligne["enregistrements"] == 2 and ligne["liens_neufs"] == 2
    assert ligne["duree_chargement_ms"] == 12.5 and ligne["rang_lecture"] == 1


def test_une_erreur_au_milieu_n_ecrit_rien(etat, passe):
    etat.empiler(passe, [("http://h/liste", "liste")])
    page = etat.prochaine(passe)
    with pytest.raises(TypeError):
        etat.terminer_page(
            page,
            etat="faite",
            statut=200,
            decision="ok",
            enregistrements=[annonce("AN-1"), Enregistrement("annonces", ("AN-2",), {"x": object()})],
            liens=[("http://h/f1", "fiche")],
            quand=QUAND,
        )
    assert etat.pages(passe, "en_cours") == 1  # la page n'est pas « faite »
    assert etat.pages(passe, "a_faire") == 0  # ses liens n'existent pas
    assert etat.enregistrements("annonces") == []  # AN-1 non plus


def test_un_enregistrement_relu_est_remplace_jamais_double(etat, passe):
    for numero_page in (1, 2):
        etat.empiler(passe, [(f"http://h/p{numero_page}", "fiche")])
        page = etat.prochaine(passe)
        etat.terminer_page(
            page,
            etat="faite",
            statut=200,
            decision="ok",
            enregistrements=[annonce("AN-1", prix=100 * numero_page)],
            quand=QUAND,
        )
    lues = etat.enregistrements("annonces")
    assert len(lues) == 1 and lues[0]["prix"] == 200 and lues[0]["_page"] == "http://h/p2"


def test_cle_composee_et_collections_distinctes(etat, passe):
    etat.empiler(passe, [("http://h/s1", "speciale")])
    page = etat.prochaine(passe)
    etat.terminer_page(
        page,
        etat="faite",
        statut=200,
        decision="ok",
        enregistrements=[
            Enregistrement("temps", (1, 5), {"speciale": 1, "numero": 5}),
            Enregistrement("temps", (1, 6), {"speciale": 1, "numero": 6}),
            Enregistrement("temps", (2, 5), {"speciale": 2, "numero": 5}),
            Enregistrement("speciales", (1,), {"id": 1}),
        ],
        quand=QUAND,
    )
    assert len(etat.enregistrements("temps")) == 3
    assert etat.collections() == ["speciales", "temps"] or sorted(etat.collections()) == ["speciales", "temps"]
    assert etat.nb_enregistrements() == {"speciales": 1, "temps": 3}


def test_les_relocalisations_sont_gardees_et_comptees(etat, passe):
    etat.empiler(passe, [("http://h/f", "fiche")])
    page = etat.prochaine(passe)
    etat.terminer_page(
        page,
        etat="faite",
        statut=200,
        decision="ok",
        enregistrements=[Enregistrement("annonces", ("AN-1",), {"reference": "AN-1"}, ("description",))],
        quand=QUAND,
    )
    assert etat.enregistrements("annonces")[0]["_relocalises"] == ["description"]
    assert etat.compteurs(passe)["relocalisations"] == 1


def test_les_enregistrements_sans_relocalisation_n_ont_pas_la_cle(etat, passe):
    etat.empiler(passe, [("http://h/f", "fiche")])
    etat.terminer_page(
        etat.prochaine(passe), etat="faite", statut=200, decision="ok", enregistrements=[annonce("AN-1")], quand=QUAND
    )
    assert "_relocalises" not in etat.enregistrements("annonces")[0]


def test_rendre_une_page_la_remet_en_file_en_tete(etat, passe):
    etat.empiler(passe, [("http://h/a", "x"), ("http://h/b", "x")])
    page = etat.prochaine(passe)
    etat.rendre(page)
    assert adresses(etat, passe) == ["http://h/a", "http://h/b"]


def test_reprendre_une_passe_remet_les_pages_en_cours_a_faire(etat, passe):
    etat.empiler(passe, [("http://h/a", "x"), ("http://h/b", "x"), ("http://h/c", "x")])
    a = etat.prochaine(passe)
    etat.terminer_page(a, etat="faite", statut=200, decision="ok", quand=QUAND)
    etat.prochaine(passe)  # b : « en cours », puis coupure
    assert etat.pages(passe, "en_cours") == 1
    etat.terminer_passe(passe, "interrompue", None, QUAND)
    remises = etat.reprendre_passe(passe)
    assert remises == 1
    assert etat.pages(passe, "en_cours") == 0 and etat.passe(passe)["statut"] == "en_cours"
    assert adresses(etat, passe) == ["http://h/b", "http://h/c"]  # b revient avant c : l'ordre est gardé


def test_compteurs_de_la_passe(etat, passe):
    etat.empiler(passe, [(f"http://h/{i}", "x") for i in range(6)])
    cas = [
        ("faite", 200, "ok", 0, 0),
        ("faite", 404, "introuvable", 0, 0),
        ("faite", 200, "anormale", 0, 0),
        ("echec", 500, "echec", 0, 0),
        ("interdite", None, "interdite", 0, 0),
        ("faite", 200, "ok", 3, 1),  # 3 liens hors site, 1 lien exclu
    ]
    for etat_page, statut, decision, hors, exclus in cas:
        page = etat.prochaine(passe)
        etat.terminer_page(
            page, etat=etat_page, statut=statut, decision=decision, hors_site=hors, exclus=exclus, quand=QUAND
        )
    c = etat.compteurs(passe)
    assert c["faites"] == 4 and c["echecs"] == 1 and c["interdites_robots"] == 1
    assert c["anormales"] == 1 and c["introuvables"] == 1 and c["hors_site"] == 3
    assert c["liens_exclus"] == 1 and c["a_faire"] == 0 and c["lues"] == 5


def test_dernieres_pages_lues_dans_l_ordre_de_lecture(etat, passe):
    etat.empiler(passe, [(f"http://h/{i}", f"t{i}") for i in range(5)])
    for decision in ("ok", "anormale", "echec", "ok", "ok"):
        page = etat.prochaine(passe)
        etat.terminer_page(
            page, etat="echec" if decision == "echec" else "faite", statut=200, decision=decision, quand=QUAND
        )
    dernieres = etat.dernieres_lues(passe, 3)
    assert [(d["type"], d["decision"]) for d in dernieres] == [("t2", "echec"), ("t3", "ok"), ("t4", "ok")]


def test_evenements(etat, passe):
    etat.evenement(passe, "debut", {"moteur": "http"}, QUAND)
    etat.evenement(passe, "arret", {"signe": "statut"}, QUAND)
    assert [(e["genre"], e["detail"]) for e in etat.evenements(passe)] == [
        ("debut", {"moteur": "http"}),
        ("arret", {"signe": "statut"}),
    ]


def test_l_etat_survit_a_la_fermeture(tmp_path):
    chemin = tmp_path / "etat.sqlite3"
    e = Etat(chemin)
    p = e.ouvrir_passe("essai", "sha256:abc", "t", "c", {}, {}, QUAND)
    e.empiler(p, [("http://h/a", "x")])
    e.fermer()
    e = Etat(chemin)
    assert e.derniere_passe()["numero"] == p
    assert e.prochaine(p).adresse == "http://h/a"
    e.fermer()


def test_fichier_qui_n_est_pas_un_etat_est_refuse(tmp_path):
    chemin = tmp_path / "etat.sqlite3"
    cx = sqlite3.connect(chemin)
    cx.execute("CREATE TABLE autre (x)")
    cx.commit()
    cx.close()
    with pytest.raises(ValueError, match="état de récolte"):
        Etat(chemin)
