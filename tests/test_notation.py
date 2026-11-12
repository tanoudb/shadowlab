"""Notation d'une récolte : complétude (annonces retrouvées) et exactitude (champs exacts)."""

from copy import deepcopy

from shadowlab.notation import noter_recolte
from shadowlab.site import vitrine

GRAINE = 20261112
TAILLE = 45


def verite():
    return vitrine.verite(GRAINE, TAILLE)


def test_recolte_parfaite():
    v = verite()
    note = noter_recolte(deepcopy(v["annonces"]), v)
    assert note["completude"] == 1 and note["exactitude"] == 1
    assert note["annonces_attendues"] == TAILLE and note["annonces_retrouvees"] == TAILLE
    assert note["champs_attendus"] == note["champs_exacts"] == TAILLE * 14
    assert note["references_manquantes"] == [] and note["annonces_en_trop"] == 0
    assert note["erreurs_par_champ"] == {}


def test_annonce_manquante():
    v = verite()
    recolte = deepcopy(v["annonces"])[1:]
    note = noter_recolte(recolte, v)
    assert note["completude"] == (TAILLE - 1) / TAILLE
    assert note["exactitude"] == 1  # calculée sur les annonces retrouvées seulement
    assert note["references_manquantes"] == [v["annonces"][0]["reference"]]
    assert note["annonces_retrouvees"] == TAILLE - 1


def test_references_manquantes_plafonnees_a_20():
    v = verite()
    note = noter_recolte(deepcopy(v["annonces"])[:5], v)
    assert len(note["references_manquantes"]) == 20
    assert note["annonces_retrouvees"] == 5


def test_champ_faux_et_champ_absent():
    v = verite()
    recolte = deepcopy(v["annonces"])
    recolte[0]["prix"] += 1
    del recolte[1]["telephone"]
    note = noter_recolte(recolte, v)
    assert note["completude"] == 1
    assert note["champs_exacts"] == TAILLE * 14 - 2
    assert note["exactitude"] == (TAILLE * 14 - 2) / (TAILLE * 14)
    assert note["erreurs_par_champ"] == {"prix": 1, "telephone": 1}


def test_normalisation_des_espaces_et_nombres():
    v = verite()
    recolte = deepcopy(v["annonces"])
    recolte[0]["titre"] = f"  {recolte[0]['titre']}\n"
    recolte[0]["prix"] = str(recolte[0]["prix"])  # "300000" == 300000
    recolte[1]["surface"] = float(recolte[1]["surface"])
    note = noter_recolte(recolte, v)
    assert note["exactitude"] == 1
    # La comparaison reste stricte : majuscule, espace interne, nombre non numérique.
    recolte[2]["ville"] = recolte[2]["ville"].upper() + "x"
    recolte[3]["prix"] = "3 000 €"
    note = noter_recolte(recolte, v)
    assert note["erreurs_par_champ"] == {"ville": 1, "prix": 1}


def test_annonces_en_trop_ignorees_et_comptees():
    v = verite()
    recolte = deepcopy(v["annonces"])
    intrus = deepcopy(recolte[0])
    intrus["reference"] = "AN-999999"
    intrus["prix"] = -1
    recolte += [intrus, {"titre": "sans référence"}]
    note = noter_recolte(recolte, v)
    assert note["annonces_en_trop"] == 2
    assert note["completude"] == 1 and note["exactitude"] == 1


def test_doublon_compte_une_fois():
    v = verite()
    recolte = deepcopy(v["annonces"]) + deepcopy(v["annonces"][:3])
    note = noter_recolte(recolte, v)
    assert note["annonces_retrouvees"] == TAILLE and note["annonces_en_trop"] == 0


def test_recolte_vide():
    note = noter_recolte([], verite())
    assert note["completude"] == 0
    assert note["exactitude"] is None
    assert note["annonces_retrouvees"] == 0 and note["champs_attendus"] == 0


# --- Notation générale (récolte générale, étape 3) ---------------------------------------------

import pytest  # noqa: E402

from shadowlab.notation import noter_pages  # noqa: E402


def verite_rallye():
    """Petite vérité en deux collections, à clé composée, avec des valeurs attendues vides."""
    temps = [
        {"rallye": "r1", "speciale": "es1", "numero": 1, "equipage": "A / B", "temps": "9:58.7", "ecart": None},
        {"rallye": "r1", "speciale": "es1", "numero": 2, "equipage": "C / D", "temps": "10:01.2", "ecart": "+2.5"},
        {"rallye": "r1", "speciale": "es2", "numero": 1, "equipage": "A / B", "temps": None, "ecart": None},
        {"rallye": "r2", "speciale": "es1", "numero": 1, "equipage": "E / F", "temps": "1:02:03.4", "ecart": ""},
    ]
    return {"temps": temps, "rallyes": [{"id": "r1", "nom": "Rallye Factice"}, {"id": "r2", "nom": "Autre"}]}


CLE_TEMPS = ("rallye", "speciale", "numero")


def test_appel_actuel_et_cles_inchanges():
    v = verite()
    note = noter_recolte(deepcopy(v["annonces"]), v)
    assert {"completude", "exactitude", "annonces_attendues", "annonces_retrouvees", "champs_attendus"} <= set(note)
    assert note == noter_recolte(deepcopy(v["annonces"]), v, liste="annonces", cle="reference")


def test_cle_composee_recolte_parfaite():
    v = verite_rallye()
    note = noter_recolte(deepcopy(v["temps"]), v, liste="temps", cle=CLE_TEMPS)
    assert note["completude"] == 1 and note["exactitude"] == 1
    assert note["enregistrements_attendus"] == note["enregistrements_retrouves"] == 4
    assert note["champs_attendus"] == note["champs_exacts"] == 4 * 6


def test_cle_composee_enregistrement_manquant_et_en_trop():
    v = verite_rallye()
    recolte = deepcopy(v["temps"])
    manquant = recolte.pop(1)
    recolte.append({**manquant, "numero": 99})  # même rallye et spéciale, autre numéro : un intrus
    note = noter_recolte(recolte, v, liste="temps", cle=CLE_TEMPS)
    assert note["enregistrements_retrouves"] == 3
    assert note["completude"] == 3 / 4
    assert note["annonces_en_trop"] == 1
    assert note["references_manquantes"] == [["r1", "es1", 2]]


def test_cle_composee_distingue_les_parties():
    v = verite_rallye()
    recolte = deepcopy(v["temps"])
    recolte[0]["speciale"] = "es9"  # une partie de la clé change : ce n'est plus le même enregistrement
    note = noter_recolte(recolte, v, liste="temps", cle=CLE_TEMPS)
    assert note["enregistrements_retrouves"] == 3 and note["annonces_en_trop"] == 1


def test_cle_composee_nombre_ou_texte():
    v = verite_rallye()
    recolte = deepcopy(v["temps"])
    for ligne in recolte:
        ligne["numero"] = f" {ligne['numero']} "  # le numéro lu en texte, avec espaces
    note = noter_recolte(recolte, v, liste="temps", cle=CLE_TEMPS)
    assert note["enregistrements_retrouves"] == 4
    assert note["exactitude"] == 1  # le numéro attendu (nombre) se compare en nombre


def test_cle_simple_autre_liste():
    v = verite_rallye()
    note = noter_recolte([{"id": "r1", "nom": "Rallye Factice"}], v, liste="rallyes", cle="id")
    assert note["enregistrements_attendus"] == 2 and note["enregistrements_retrouves"] == 1
    assert note["references_manquantes"] == ["r2"]


def test_attendu_vide_et_rien_lu_est_exact():
    v = verite_rallye()
    for rien in (None, "", "  "):
        recolte = deepcopy(v["temps"])
        recolte[0]["ecart"] = rien
        recolte[2]["temps"] = rien
        note = noter_recolte(recolte, v, liste="temps", cle=CLE_TEMPS)
        assert note["exactitude"] == 1, rien


def test_attendu_vide_champ_absent_est_exact():
    v = verite_rallye()
    recolte = deepcopy(v["temps"])
    del recolte[0]["ecart"]  # abandon sans écart : le champ n'existe pas dans la récolte
    note = noter_recolte(recolte, v, liste="temps", cle=CLE_TEMPS)
    assert note["exactitude"] == 1


def test_attendu_vide_et_quelque_chose_lu_est_faux():
    v = verite_rallye()
    recolte = deepcopy(v["temps"])
    recolte[2]["temps"] = "0:00.0"
    recolte[3]["ecart"] = "+1.0"
    recolte[0]["ecart"] = 0
    note = noter_recolte(recolte, v, liste="temps", cle=CLE_TEMPS)
    assert note["erreurs_par_champ"] == {"ecart": 2, "temps": 1}


def test_attendu_plein_et_rien_lu_reste_faux():
    v = verite_rallye()
    recolte = deepcopy(v["temps"])
    recolte[1]["ecart"] = None
    recolte[0]["temps"] = ""
    note = noter_recolte(recolte, v, liste="temps", cle=CLE_TEMPS)
    assert note["erreurs_par_champ"] == {"ecart": 1, "temps": 1}


def test_page_lue_au_tableau_a_moitie_lu_se_voit_dans_les_enregistrements():
    v = verite_rallye()
    recolte = deepcopy(v["temps"])[:2]  # seule la moitié des lignes
    note = noter_recolte(recolte, v, liste="temps", cle=CLE_TEMPS)
    assert note["completude"] == 0.5
    assert note["exactitude"] == 1  # les champs ne voient pas le défaut : c'est la mesure des enregistrements


def test_liste_inconnue_ou_cle_attendue_en_double_refusees():
    v = verite_rallye()
    with pytest.raises(ValueError, match="inconnue"):
        noter_recolte([], v, liste="absente", cle="id")
    v["rallyes"].append({"id": "r1", "nom": "Doublon"})
    with pytest.raises(ValueError, match="plusieurs fois"):
        noter_recolte([], v, liste="rallyes", cle="id")


def test_noter_pages_parfait():
    attendues = ["/lab/x", "/lab/x?page=2", "/lab/x/1"]
    note = noter_pages(attendues, list(reversed(attendues)))
    assert note["pages_attendues"] == note["pages_lues"] == 3
    assert note["completude_pages"] == 1
    assert note["pages_manquantes"] == [] and note["pages_en_trop"] == 0


def test_noter_pages_manquantes_doublons_et_en_trop():
    attendues = ["/lab/x", "/lab/x?page=2", "/lab/x/1"]
    lues = ["/lab/x", "/lab/x", "/lab/x/1", "/lab/autre", "/lab/ailleurs"]
    note = noter_pages(attendues, lues)
    assert note["pages_lues"] == 2  # un doublon ne compte qu'une fois
    assert note["completude_pages"] == 2 / 3
    assert note["pages_manquantes"] == ["/lab/x?page=2"]
    assert note["pages_en_trop"] == 2


def test_noter_pages_adresses_absolues_jeton_et_fragment_ignores():
    attendues = ["/lab/x", "/lab/x?page=2", "/lab/x/1"]
    lues = ["http://127.0.0.1:8770/lab/x?sl=abc", "/lab/x?page=2&sl=abc#haut", "/lab/x/1?sl=z"]
    assert noter_pages(attendues, lues)["completude_pages"] == 1


def test_noter_pages_page_un_avec_ou_sans_parametre():
    note = noter_pages(["/lab/x", "/lab/x?page=2"], ["/lab/x?page=1", "/lab/x?page=2"])
    assert note["completude_pages"] == 1


def test_noter_pages_manquantes_plafonnees_et_attendues_vides():
    attendues = [f"/lab/p/{i}" for i in range(50)]
    assert len(noter_pages(attendues, [])["pages_manquantes"]) == 20
    assert noter_pages([], [])["completude_pages"] == 0.0
