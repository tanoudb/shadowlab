"""Récolte incrémentale : la deuxième passe ne relit que ce que la recette dit de revisiter et ce qui est neuf."""

from __future__ import annotations

import csv
import json
import re

import pytest
from outils_recolte import (
    RECETTE_VITRINE,
    TAILLE,
    PiloteFactice,
    chemin_sans_jeton,
    creer_client,
    fabriquer,
)

from shadowlab.engines.noezia.etat import Etat
from shadowlab.engines.noezia.parcours import Options

PASSE_1 = "2026-11-12T10:00:00+00:00"
PASSE_2 = "2026-11-15T10:00:00+00:00"  # 3 jours plus tard
PASSE_3 = "2026-11-23T10:00:00+00:00"  # 11 jours après la passe 1


@pytest.fixture
def site(reglages, monkeypatch):
    with creer_client(monkeypatch) as client:
        yield client


@pytest.fixture
def dossier(tmp_path):
    return tmp_path / "recoltes" / "vitrine-annonces"


def jsonl(chemin):
    return [json.loads(ligne) for ligne in chemin.read_text(encoding="utf-8").splitlines()]


def recette_fiche(revisiter: str) -> str:
    """Le texte de la recette de la vitrine avec un autre `revisiter` sur les fiches."""
    texte = RECETTE_VITRINE.read_text(encoding="utf-8")
    nouveau = re.sub(r"(    revisiter: )jamais", rf"\g<1>{revisiter}", texte)
    assert nouveau != texte
    return nouveau


def fiche_a_prix(site, reference: str, prix: int) -> str:
    """La fiche telle que le site la sert, avec un autre prix."""
    html = site.get(f"/lab/vitrine/annonces/{reference}").text
    return re.sub(r'(data-champ="prix" data-valeur=")\d+(")', rf"\g<1>{prix}\g<2>", html)


def passe_a(horodatage):
    return lambda: horodatage


# --- Critère de l'étape 7 : 45 puis 50 annonces ----------------------------------------------


def test_vitrine_45_puis_50_la_seconde_passe_lit_3_listes_et_5_fiches(dossier, site, monkeypatch):
    fabriquer(dossier, PiloteFactice(site)).lancer()
    with creer_client(monkeypatch, 50) as site_50:
        second = PiloteFactice(site_50)
        p = fabriquer(dossier, second)
        bilan = p.lancer()
    lues = [chemin_sans_jeton(d) for d in second.pages_lues()]
    assert bilan.passe == 2 and bilan.code == 0
    assert second.requetes_pages == 8 and len(lues) == 8
    assert [d for d in lues if "?page" in d or d.endswith("/annonces")] == [
        "/lab/vitrine/annonces",
        "/lab/vitrine/annonces?page=2",
        "/lab/vitrine/annonces?page=3",
    ]
    assert sorted(d for d in lues if "AN-" in d) == [f"/lab/vitrine/annonces/AN-{i:06d}" for i in range(46, 51)]

    nouveautes = jsonl(dossier / "passe-002" / "nouveautes.jsonl")
    assert [n["reference"] for n in nouveautes] == [f"AN-{i:06d}" for i in range(46, 51)]
    assert {n["_changement"] for n in nouveautes} == {"nouveau"} and {n["_collection"] for n in nouveautes} == {
        "annonces"
    }
    assert len(jsonl(dossier / "passe-002" / "annonces.jsonl")) == 50  # le fichier garde tout ce qui est connu

    incr = bilan.resume["incrementale"]
    assert incr == {
        "active": True,
        "pages_relues": 3,
        "pages_evitees": 45,
        "pages_nouvelles": 5,
        "nouveautes": 5,
        "modifies": 0,
    }
    assert bilan.resume["pages"]["faites"] == 8 and bilan.resume["pages"]["evitees"] == 45
    assert bilan.resume["enregistrements"] == {"annonces": 50}
    assert "nouveautes.jsonl" in bilan.resume["fichiers"] and "nouveautes.csv" in bilan.resume["fichiers"]


def test_la_premiere_passe_ecrit_aussi_ses_nouveautes_tout_est_nouveau(dossier, site):
    bilan = fabriquer(dossier, PiloteFactice(site)).lancer()
    assert len(jsonl(dossier / "passe-001" / "nouveautes.jsonl")) == TAILLE
    assert bilan.resume["incrementale"]["active"] is False
    assert bilan.resume["incrementale"]["pages_evitees"] == 0 and bilan.resume["incrementale"]["nouveautes"] == TAILLE


def test_une_seconde_passe_sans_rien_de_neuf_ne_lit_que_les_listes(dossier, site):
    fabriquer(dossier, PiloteFactice(site)).lancer()
    second = PiloteFactice(site)
    bilan = fabriquer(dossier, second).lancer()
    assert second.requetes_pages == 3 and bilan.resume["incrementale"]["nouveautes"] == 0
    assert (dossier / "passe-002" / "nouveautes.jsonl").read_text(encoding="utf-8") == ""
    assert bilan.resume["enregistrements"] == {"annonces": TAILLE}


def test_nouveautes_csv_en_francais_avec_le_type_de_changement(dossier, site, monkeypatch):
    fabriquer(dossier, PiloteFactice(site)).lancer()
    with creer_client(monkeypatch, 47) as site_47:
        fabriquer(dossier, PiloteFactice(site_47)).lancer()
    chemin = dossier / "passe-002" / "nouveautes.csv"
    assert chemin.read_bytes().startswith(b"\xef\xbb\xbf")
    with chemin.open(encoding="utf-8-sig", newline="") as f:
        lignes = list(csv.DictReader(f, delimiter=";"))
    assert [(r["_collection"], r["_changement"], r["reference"]) for r in lignes] == [
        ("annonces", "nouveau", "AN-000046"),
        ("annonces", "nouveau", "AN-000047"),
    ]


# --- Ce qui a changé : seulement si la page est relue --------------------------------------------


def test_prix_change_sans_relire_la_fiche_rien_n_est_vu(dossier, site):
    fabriquer(dossier, PiloteFactice(site)).lancer()
    second = PiloteFactice(site)
    second.reponses["=/lab/vitrine/annonces/AN-000005"] = (200, fiche_a_prix(site, "AN-000005", 1))
    bilan = fabriquer(dossier, second).lancer()  # la recette dit « jamais » pour les fiches
    assert second.requetes_pages == 3 and bilan.resume["incrementale"]["modifies"] == 0
    etat = Etat(dossier / "etat.sqlite3")
    assert next(e for e in etat.enregistrements("annonces") if e["reference"] == "AN-000005")["prix"] != 1
    etat.fermer()


def test_fiches_a_revisiter_toujours_un_prix_change_est_distingue_du_neuf(dossier, site):
    texte = recette_fiche("toujours")
    fabriquer(dossier, PiloteFactice(site), texte=texte).lancer()
    ancien = Etat(dossier / "etat.sqlite3")
    avant = next(e for e in ancien.enregistrements("annonces") if e["reference"] == "AN-000005")["prix"]
    ancien.fermer()
    second = PiloteFactice(site)
    second.reponses["=/lab/vitrine/annonces/AN-000005"] = (200, fiche_a_prix(site, "AN-000005", 123456))
    bilan = fabriquer(dossier, second, texte=texte).lancer()
    assert second.requetes_pages == 48
    nouveautes = jsonl(dossier / "passe-002" / "nouveautes.jsonl")
    assert len(nouveautes) == 1
    ligne = nouveautes[0]
    assert ligne["reference"] == "AN-000005" and ligne["prix"] == 123456
    assert ligne["_changement"] == "modifie" and ligne["_champs_modifies"] == {"prix": avant}
    incr = bilan.resume["incrementale"]
    assert incr["pages_relues"] == 48 and incr["pages_evitees"] == 0 and incr["nouveautes"] == 0
    assert incr["modifies"] == 1
    assert bilan.resume["enregistrements"] == {"annonces": TAILLE}  # remplacé, jamais doublé


def test_revisiter_en_jours_relit_les_fiches_assez_anciennes(dossier, site):
    texte = recette_fiche("7j")
    fabriquer(dossier, PiloteFactice(site), texte=texte, horodatage=passe_a(PASSE_1)).lancer()
    deuxieme = PiloteFactice(site)
    fabriquer(dossier, deuxieme, texte=texte, horodatage=passe_a(PASSE_2)).lancer()
    assert deuxieme.requetes_pages == 3  # lues il y a 3 jours : pas encore
    troisieme = PiloteFactice(site)
    bilan = fabriquer(dossier, troisieme, texte=texte, horodatage=passe_a(PASSE_3)).lancer()
    assert troisieme.requetes_pages == 48  # lues il y a 11 jours
    assert bilan.resume["incrementale"]["pages_relues"] == 48


def test_une_page_notee_introuvable_ou_en_echec_est_redemandee(dossier, site):
    premier = PiloteFactice(site)
    premier.reponses["AN-000005"] = (404, "<html><body>introuvable</body></html>")
    fabriquer(dossier, premier).lancer()
    second = PiloteFactice(site)
    bilan = fabriquer(dossier, second).lancer()
    lues = [chemin_sans_jeton(d) for d in second.pages_lues()]
    assert second.requetes_pages == 4 and "/lab/vitrine/annonces/AN-000005" in lues
    assert [n["reference"] for n in jsonl(dossier / "passe-002" / "nouveautes.jsonl")] == ["AN-000005"]
    assert bilan.resume["incrementale"]["pages_nouvelles"] == 1 and bilan.resume["incrementale"]["pages_relues"] == 3


# --- --tout-refaire --------------------------------------------------------------------------------


def test_tout_refaire_relit_tout_et_tout_redevient_nouveau(dossier, site):
    fabriquer(dossier, PiloteFactice(site)).lancer()
    second = PiloteFactice(site)
    bilan = fabriquer(dossier, second, options=Options(tout_refaire=True)).lancer()
    assert second.requetes_pages == 48 and bilan.resume["pages"]["evitees"] == 0
    assert bilan.resume["incrementale"]["active"] is False
    assert len(jsonl(dossier / "passe-002" / "nouveautes.jsonl")) == TAILLE


def test_apres_un_tout_refaire_on_ne_compte_pas_les_pages_d_avant(dossier, site):
    """Les enregistrements ont été effacés par --tout-refaire : une passe plus tard ne doit pas croire lues les
    pages que seules les passes d'avant avaient lues."""
    fabriquer(dossier, PiloteFactice(site)).lancer()
    pilote = PiloteFactice(site)
    pilote.interruption_a = 5
    fabriquer(dossier, pilote, options=Options(tout_refaire=True)).lancer()  # passe 2 coupée
    fabriquer(dossier, PiloteFactice(site)).reprendre()
    etat = Etat(dossier / "etat.sqlite3")
    assert len(etat.enregistrements("annonces")) == TAILLE
    etat.fermer()
    troisieme = PiloteFactice(site)
    fabriquer(dossier, troisieme).lancer()
    assert troisieme.requetes_pages == 3


# --- Reprise ---------------------------------------------------------------------------------------


def test_reprise_apres_coupure_pendant_une_passe_incrementale(dossier, site, monkeypatch):
    fabriquer(dossier, PiloteFactice(site)).lancer()
    with creer_client(monkeypatch, 50) as site_50:
        premier = PiloteFactice(site_50)
        premier.interruption_a = 5  # 3 listes, la 1re fiche neuve, puis Ctrl-C sur la 2e
        bilan = fabriquer(dossier, premier).lancer()
        assert bilan.statut == "interrompue"
        second = PiloteFactice(site_50)
        reprise = fabriquer(dossier, second).reprendre()
    assert reprise.code == 0 and reprise.passe == 2
    lues = [chemin_sans_jeton(d) for p in (premier, second) for d in p.pages_lues()]
    assert len(lues) == len(set(lues)) == 8
    assert [n["reference"] for n in jsonl(dossier / "passe-002" / "nouveautes.jsonl")] == [
        f"AN-{i:06d}" for i in range(46, 51)
    ]
    assert reprise.resume["incrementale"]["pages_evitees"] == 45


def test_reprise_d_une_passe_tout_refaire_reste_complete(dossier, site):
    fabriquer(dossier, PiloteFactice(site)).lancer()
    premier = PiloteFactice(site)
    premier.interruption_a = 10
    fabriquer(dossier, premier, options=Options(tout_refaire=True)).lancer()
    second = PiloteFactice(site)
    reprise = fabriquer(dossier, second).reprendre()  # options de départ : tout_refaire est gardé
    assert reprise.resume["pages"]["evitees"] == 0
    lues = [chemin_sans_jeton(d) for p in (premier, second) for d in p.pages_lues()]
    assert len(lues) == len(set(lues)) == 48


# --- Ce que voit l'utilisateur ---------------------------------------------------------------------


def test_l_ecran_de_fin_dit_relues_evitees_nouveautes(dossier, site, monkeypatch):
    fabriquer(dossier, PiloteFactice(site)).lancer()
    with creer_client(monkeypatch, 50) as site_50:
        p = fabriquer(dossier, PiloteFactice(site_50))
        p.lancer()
    texte = "\n".join(p.sortie_ecran)
    assert "Incrémental : 3 page(s) relue(s), 45 évitée(s), 5 page(s) neuve(s) · 5 nouveauté(s), 0 modifié(s)" in texte
