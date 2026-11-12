"""Export des données : un JSON Lines et un CSV par collection, réécrits depuis l'état à chaque arrêt."""

import csv
import json

import pytest
from outils_recolte import GRAINE, QUAND, TAILLE, PiloteFactice, creer_client, fabriquer

from shadowlab.engines.noezia.etat import Etat
from shadowlab.engines.noezia.export import ecrire_exports
from shadowlab.engines.noezia.recettes import Enregistrement
from shadowlab.site import vitrine


@pytest.fixture
def site(reglages, monkeypatch):
    with creer_client(monkeypatch) as client:
        yield client


@pytest.fixture
def dossier(tmp_path):
    return tmp_path / "recoltes" / "vitrine-annonces"


def lignes_jsonl(chemin):
    return [json.loads(ligne) for ligne in chemin.read_text(encoding="utf-8").splitlines()]


def lignes_csv(chemin):
    """Lit le CSV comme Excel en France : UTF-8 avec BOM, point-virgule."""
    with chemin.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


@pytest.fixture
def etat_a_deux_collections(tmp_path):
    etat = Etat(tmp_path / "etat.sqlite3")
    passe = etat.ouvrir_passe("essai", "sha256:x", "t", "c", {}, {}, QUAND)
    etat.empiler(passe, [("http://h/a", "p")])
    page = etat.prochaine(passe)
    etat.terminer_page(
        page,
        etat="faite",
        statut=200,
        decision="ok",
        quand=QUAND,
        enregistrements=[
            Enregistrement("pilotes", (1,), {"id": 1, "nom": "Zoë d'Arc", "note": None, "actif": True}),
            Enregistrement("rallyes", (7,), {"id": 7, "nom": "Rallye du Col", "tags": ["a", "b"]}, ("nom",)),
            Enregistrement("pilotes", (2,), {"id": 2, "nom": "=1+1", "note": 4.5, "actif": False}),
        ],
    )
    yield etat, passe
    etat.fermer()


def test_un_fichier_jsonl_et_un_csv_par_collection(etat_a_deux_collections, tmp_path):
    etat, _ = etat_a_deux_collections
    dossier = tmp_path / "passe-001"
    fichiers = ecrire_exports(etat, dossier)
    assert sorted(fichiers) == ["pilotes.csv", "pilotes.jsonl", "rallyes.csv", "rallyes.jsonl"]
    assert sorted(p.name for p in dossier.iterdir()) == sorted(fichiers)  # pas de fichier temporaire oublié


def test_jsonl_une_ligne_par_enregistrement_avec_les_cles_ajoutees(etat_a_deux_collections, tmp_path):
    etat, passe = etat_a_deux_collections
    ecrire_exports(etat, tmp_path)
    pilotes = lignes_jsonl(tmp_path / "pilotes.jsonl")
    assert [p["id"] for p in pilotes] == [1, 2]
    assert pilotes[0] == {
        "id": 1,
        "nom": "Zoë d'Arc",
        "note": None,
        "actif": True,
        "_page": "http://h/a",
        "_vu_le": QUAND,
        "_passe": passe,
    }
    assert lignes_jsonl(tmp_path / "rallyes.jsonl")[0]["_relocalises"] == ["nom"]
    assert "Zoë" in (tmp_path / "pilotes.jsonl").read_text(encoding="utf-8")  # pas d'échappement ë


def test_csv_en_tete_valeurs_vides_booleens_et_listes(etat_a_deux_collections, tmp_path):
    etat, _ = etat_a_deux_collections
    ecrire_exports(etat, tmp_path)
    lignes = lignes_csv(tmp_path / "pilotes.csv")
    assert list(lignes[0]) == ["id", "nom", "note", "actif", "_page", "_vu_le", "_passe"]
    assert lignes[0]["note"] == "" and lignes[0]["actif"] == "true" and lignes[1]["actif"] == "false"
    assert lignes[1]["note"] == "4,5"
    assert lignes[0]["nom"] == "Zoë d'Arc"
    rallye = lignes_csv(tmp_path / "rallyes.csv")[0]
    assert json.loads(rallye["tags"]) == ["a", "b"]  # une liste : son écriture JSON
    assert rallye["_relocalises"] == '["nom"]'


def test_csv_pour_excel_en_france_bom_point_virgule_virgule_decimale(etat_a_deux_collections, tmp_path):
    etat, _ = etat_a_deux_collections
    ecrire_exports(etat, tmp_path)
    brut = (tmp_path / "pilotes.csv").read_bytes()
    assert brut.startswith(b"\xef\xbb\xbf")  # BOM UTF-8
    with (tmp_path / "pilotes.csv").open(encoding="utf-8-sig", newline="") as f:
        lignes = list(csv.reader(f, delimiter=";"))
    assert lignes[0][:4] == ["id", "nom", "note", "actif"]
    assert lignes[2][2] == "4,5"  # nombre décimal : virgule
    assert lignes[2][0] == "2"  # entier : tel quel
    # le JSON Lines reste la donnée exacte : point décimal
    assert lignes_jsonl(tmp_path / "pilotes.jsonl")[1]["note"] == 4.5


def test_csv_un_point_virgule_dans_une_valeur_est_protege(tmp_path):
    etat = Etat(tmp_path / "e.sqlite3")
    passe = etat.ouvrir_passe("essai", "sha256:x", "t", "c", {}, {}, QUAND)
    etat.empiler(passe, [("http://h/a", "p")])
    etat.terminer_page(
        etat.prochaine(passe),
        etat="faite",
        statut=200,
        decision="ok",
        quand=QUAND,
        enregistrements=[Enregistrement("c", (1,), {"id": 1, "v": 'a;b"c', "x": -3.25})],
    )
    ecrire_exports(etat, tmp_path / "out")
    ligne = lignes_csv(tmp_path / "out" / "c.csv")[0]
    assert ligne["v"] == 'a;b"c' and ligne["x"] == "-3,25"
    etat.fermer()


def test_csv_neutralise_les_formules_venues_du_site(etat_a_deux_collections, tmp_path):
    etat, _ = etat_a_deux_collections
    ecrire_exports(etat, tmp_path)
    assert lignes_csv(tmp_path / "pilotes.csv")[1]["nom"] == "'=1+1"  # un tableur ne l'exécutera pas
    # le JSON Lines garde la valeur exacte
    assert lignes_jsonl(tmp_path / "pilotes.jsonl")[1]["nom"] == "=1+1"


@pytest.mark.parametrize(
    ("valeur", "ecrit"),
    [
        ("=SOMME(A1)", "'=SOMME(A1)"),
        ("@cmd", "'@cmd"),
        ("+cmd|' /C calc'!A0", "'+cmd|' /C calc'!A0"),
        ("-2+3+cmd", "'-2+3+cmd"),
        ("\t=1", "'\t=1"),
        ("+33 1 99 00 12 34", "+33 1 99 00 12 34"),  # un téléphone n'est pas une formule
        ("-12,5", "-12,5"),
        ("normal = pas au début", "normal = pas au début"),
    ],
)
def test_neutralisation_des_formules(tmp_path, valeur, ecrit):
    etat = Etat(tmp_path / "e.sqlite3")
    passe = etat.ouvrir_passe("essai", "sha256:x", "t", "c", {}, {}, QUAND)
    etat.empiler(passe, [("http://h/a", "p")])
    etat.terminer_page(
        etat.prochaine(passe),
        etat="faite",
        statut=200,
        decision="ok",
        quand=QUAND,
        enregistrements=[Enregistrement("c", (1,), {"id": 1, "v": valeur})],
    )
    ecrire_exports(etat, tmp_path / "out")
    assert lignes_csv(tmp_path / "out" / "c.csv")[0]["v"] == ecrit
    etat.fermer()


def test_pas_de_collection_pas_de_fichier(tmp_path):
    etat = Etat(tmp_path / "e.sqlite3")
    assert ecrire_exports(etat, tmp_path / "out") == []
    etat.fermer()


def test_une_passe_complete_ecrit_les_donnees_exactes(dossier, site):
    bilan = fabriquer(dossier, PiloteFactice(site)).lancer()
    jsonl, csv_ = bilan.dossier_passe / "annonces.jsonl", bilan.dossier_passe / "annonces.csv"
    ecrites = lignes_jsonl(jsonl)
    assert len(ecrites) == TAILLE == len(lignes_csv(csv_))
    verite = {a["reference"]: a for a in vitrine.verite(GRAINE, TAILLE)["annonces"]}
    for ligne in ecrites:
        attendu = verite[ligne["reference"]]
        assert all(ligne[champ] == valeur for champ, valeur in attendu.items() if champ != "photos")
        assert ligne["_passe"] == 1 and ligne["_page"].endswith(ligne["reference"])
        assert all(photo.startswith("http://127.0.0.1") and photo.endswith(".svg") for photo in ligne["photos"])
    assert bilan.resume["fichiers"] == ["annonces.csv", "annonces.jsonl"]
    assert bilan.resume["csv"] == {"separateur": ";", "encodage": "utf-8-sig", "decimale": ","}
    assert json.loads((bilan.dossier_passe / "resume.json").read_text(encoding="utf-8"))["csv"]["separateur"] == ";"
    assert next(row for row in lignes_csv(csv_) if row["reference"] == ecrites[0]["reference"])["prix"] == str(
        ecrites[0]["prix"]
    )  # un entier reste un entier


def test_a_l_arret_les_fichiers_contiennent_ce_qui_est_deja_lu(dossier, site):
    pilote = PiloteFactice(site)
    pilote.reponses["AN-000010"] = (429, "non")
    bilan = fabriquer(dossier, pilote).lancer()
    assert bilan.code == 3
    assert len(lignes_jsonl(bilan.dossier_passe / "annonces.jsonl")) == 9
    assert len(lignes_csv(bilan.dossier_passe / "annonces.csv")) == 9


def test_apres_reprise_les_fichiers_sont_reecrits_depuis_la_base_sans_doublon(dossier, site):
    premier = PiloteFactice(site)
    premier.interruption_a = 20
    fabriquer(dossier, premier).lancer()
    bilan = fabriquer(dossier, PiloteFactice(site)).reprendre()
    ecrites = lignes_jsonl(bilan.dossier_passe / "annonces.jsonl")
    assert len(ecrites) == TAILLE and len({e["reference"] for e in ecrites}) == TAILLE
