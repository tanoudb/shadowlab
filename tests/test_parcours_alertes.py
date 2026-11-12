"""Alertes de lecture : visibles pendant la passe, gardées dans l'état (bornées), dans resume.json et dans `etat`."""

from __future__ import annotations

import re

import pytest
from outils_recolte import RECETTE_VITRINE, PiloteFactice, creer_client, fabriquer, lu

from shadowlab.engines.noezia.etat import Etat
from shadowlab.engines.noezia.recettes import lire_texte

# Une colonne lue « en entier » alors qu'elle contient du texte : une alerte par fiche, valeur « Lyon », « Paris »…
TEXTE = RECETTE_VITRINE.read_text(encoding="utf-8").replace(
    "ville: '[data-champ=\"ville\"]'", "ville: {css: '[data-champ=\"ville\"]', format: entier}"
)


@pytest.fixture
def site(reglages, monkeypatch):
    with creer_client(monkeypatch) as client:
        yield client


@pytest.fixture
def dossier(tmp_path):
    return tmp_path / "recoltes" / "vitrine-annonces"


def passe_avec_alertes(dossier, site):
    p = fabriquer(dossier, PiloteFactice(site), recette=lire_texte(TEXTE), texte=TEXTE)
    return p, p.lancer()


def test_la_ligne_d_avancement_dit_le_nombre_d_alertes_de_lecture(dossier, site):
    p, _ = passe_avec_alertes(dossier, site)
    avancement = [ligne for ligne in p.sortie_ecran if ligne.startswith("  pages lues")]
    assert avancement and re.search(r"alertes de lecture [1-9]\d*$", avancement[0])


def test_la_fin_de_passe_donne_le_total_et_les_plus_frequentes_avec_un_exemple(dossier, site):
    p, _ = passe_avec_alertes(dossier, site)
    texte = "\n".join(p.sortie_ecran)
    assert "Alertes de lecture : 45 au total, 1 sorte(s) parmi les plus fréquentes :" in texte
    assert "45 × fiche · champ « ville »" in texte and "n'est pas lisible en entier" in texte
    assert "ex. http://127.0.0.1" in texte and "/lab/vitrine/annonces/AN-" in texte


def test_resume_json_porte_les_alertes(dossier, site):
    passe_avec_alertes(dossier, site)
    alertes = lu(dossier)["alertes_lecture"]
    assert alertes["total"] == 45
    groupe = alertes["groupes"][0]
    assert groupe["nb"] == 45 and groupe["type"] == "fiche" and groupe["champ"] == "ville"
    assert "entier" in groupe["message"] and groupe["exemple_adresse"].startswith("http://127.0.0.1")


def test_pas_d_alerte_pas_de_bruit(dossier, site):
    p = fabriquer(dossier, PiloteFactice(site))
    p.lancer()
    assert lu(dossier)["alertes_lecture"] == {"total": 0, "groupes": []}
    assert "Alertes de lecture : aucune." in "\n".join(p.sortie_ecran)


def test_l_etat_regroupe_avec_une_borne(dossier):
    etat = Etat(dossier / "etat.sqlite3")
    passe = etat.ouvrir_passe("r", "sha256:x", "t", "c", {"nom": "http"}, {}, "2026-11-12T10:00:00+00:00")
    for i in range(500):  # 500 messages tous différents (le texte change à chaque fois)
        etat.noter_alertes(passe, "fiche", f"http://h/{i}", [f"champ « c{i} » : « v » n'est pas lisible en entier"])
    resume = etat.alertes_lecture(passe, 5)
    assert resume["total"] == 500 and len(resume["groupes"]) == 5
    assert etat._cx.execute("SELECT COUNT(*) FROM alertes_lecture").fetchone()[0] <= etat.MAX_GROUPES_ALERTES + 1
    etat.fermer()
