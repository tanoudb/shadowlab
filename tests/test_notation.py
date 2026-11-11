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
