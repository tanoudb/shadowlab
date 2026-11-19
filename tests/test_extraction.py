"""Tests de l'extraction adaptative (logique de similarité et mémoire, sans navigateur)."""

from __future__ import annotations

from shadowlab.engines.noezia import extraction


def _el(tag="span", classes=None, id="", texte="", profondeur=5):
    return {"tag": tag, "classes": classes or [], "id": id, "texte": texte, "profondeur": profondeur}


def test_score_identique_eleve():
    e = _el("span", ["prix"], "p1", "123 €", 5)
    assert extraction.score(e, dict(e)) >= 0.99


def test_score_tag_different_nul():
    a = _el("span", ["prix"], texte="123 €")
    b = _el("div", ["prix"], texte="123 €")
    assert extraction.score(a, b) == 0.0


def test_score_partiel_entre_0_et_1():
    sig = _el("span", ["prix", "gros"], "", "123 €", 5)
    cand = _el("span", ["prix"], "", "124 €", 6)  # classe perdue, texte proche, profondeur décalée
    s = extraction.score(sig, cand)
    assert 0.4 < s < 0.99


def test_meilleur_candidat_choisit_le_plus_proche():
    sig = _el("span", ["prix"], "", "123 €", 5)
    candidats = [
        _el("span", ["titre"], "", "Produit", 3),
        _el("span", ["prix", "promo"], "", "123 €", 5),  # le bon, classe en plus
        _el("span", [], "", "autre", 8),
    ]
    meilleur, sc = extraction.meilleur_candidat(sig, candidats)
    assert meilleur is candidats[1] and sc >= extraction.SEUIL_RELOCALISATION


def test_meilleur_candidat_vide():
    assert extraction.meilleur_candidat(_el(), []) == (None, 0.0)


def test_signatures_persistent(tmp_path):
    chemin = tmp_path / "sig.json"
    s = extraction.Signatures(chemin)
    sig = _el("span", ["prix"], "p1", "123 €", 5)
    s.enregistrer("exemple.test", "prix", sig)
    assert s.charger("exemple.test", "prix") == sig
    # relecture depuis le disque par une nouvelle instance
    s2 = extraction.Signatures(chemin)
    assert s2.charger("exemple.test", "prix") == sig
    assert s2.charger("exemple.test", "absent") is None


def test_signatures_ecrites_d_un_coup(tmp_path, monkeypatch):
    """Plusieurs identités d'une récolte partagée écrivent le même fichier (étape 4.2) : une écriture coupée en route
    laisse l'ancien fichier entier, jamais un fichier à moitié écrit, et aucun fichier temporaire."""
    import os

    chemin = tmp_path / "sig.json"
    extraction.Signatures(chemin).enregistrer("exemple.test", "prix", _el("span", ["prix"]))
    avant = chemin.read_text(encoding="utf-8")

    def coupure(*_args, **_kwargs):
        raise OSError("disque plein")

    monkeypatch.setattr(os, "replace", coupure)
    extraction.Signatures(chemin).enregistrer("exemple.test", "titre", _el("h1", ["titre"]))
    assert chemin.read_text(encoding="utf-8") == avant
    assert sorted(p.name for p in tmp_path.iterdir()) == ["sig.json"]


def test_domaine_de():
    assert extraction.domaine_de("https://www.example.com/a?b=1") == "www.example.com"
