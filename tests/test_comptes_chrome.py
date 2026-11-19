"""Palier 2, I10 (D-104) : une identité connectée reste connectée d'un lancement de Chrome à l'autre ; un compte
banni est refusé depuis une autre identité, qui ne demande plus rien. Dans un vrai Chrome au réglage de la course
(identité native, avec interface), devant le site du labo au profil `endurance` (en-têtes du frontal ajoutés par le
contexte, comme `test_visite_refus_en_cours.py`).

Le scénario est celui des campagnes (`scenarios.visite(..., compte=...)`) et le bannissement passe par le même code que
`bannir_avant_visite` (`campaigns._bannir_avant_visite`). Les détecteurs sont coupés (`gardien.suspicion`) : on mesure
la mémoire du compte, pas le comportement ; la porte d'entrée (preuve de travail), le bannissement, le cookie de
connexion durable et l'en-tête du refus sont les vrais.

Ce que ce test ne prouve pas : la vraie Arena (frontal TLS, Nginx, Coraza) ; une « autre empreinte » (deux identités sur
la même machine ont la même empreinte E ; l'autre empreinte est prouvée par `tests/test_comptes.py`).
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest
from test_bannissement import _entetes
from test_visite_refus_en_cours import Chien, site_en_direct  # noqa: F401 — fixture
from test_visiteurs import nouveau_passage, nouvelle_experience

from shadowlab import campaigns, correlation, scenarios
from shadowlab import database as db
from shadowlab.engines.noezia import identite as ident
from shadowlab.engines.noezia.identite import IdentiteRefusee
from shadowlab.engines.noezia.lecture import LectureHumaine
from shadowlab.engines.noezia.moteur import DriverNoezia
from shadowlab.site import gardien

MONDE = "c-comptes-chrome:temoin:endurance"
REGLAGE = {"headless": False, "channel": "chrome", "identite_native": True}
BORNE_S = 240


@pytest.fixture
def isole(site_en_direct, monkeypatch, tmp_path):  # noqa: F811
    monkeypatch.setenv("SHADOWLAB_IDENTITES", str(tmp_path / "identites"))
    monkeypatch.setattr(gardien, "suspicion", lambda *a, **k: [])  # seuls la porte, le bannissement et le compte jugent
    monkeypatch.setattr(scenarios, "LECTURE_HUMAINE_VISITE", LectureHumaine(duree_s=(0.5, 1.0, 2.0)))
    return site_en_direct


def _visiter(site, experience: int, repetition: int, identite: str):
    """Une visite : un Chrome lancé sur l'identité, le scénario `visite` de 2 pages avec le compte `demo`."""
    jeton = nouveau_passage(site, experience, repetition=repetition, monde=MONDE)
    pilote = DriverNoezia(("127.0.0.1",), {**REGLAGE, "identite": identite})
    pilote.open()
    try:
        pilote.start_session()
        pilote._contexte.set_extra_http_headers(_entetes(site, "endurance", jeton))  # ce qu'ajoute le frontal
        issue = scenarios.visite(
            pilote, f"http://127.0.0.1:{site.port}", jeton, random.Random(repetition), pages=2, duree_porte_s=86_400,
            compte="demo",
        )  # fmt: skip
        pilote.close_session()
    finally:
        pilote.close()
    return jeton, issue


def _decisions(site, jeton: str) -> list[dict]:
    cx = db.ouvrir(site.base_donnees)
    try:
        return db.decisions_session(cx, jeton)
    finally:
        cx.close()


def _visiteur_et_empreinte(site, jeton: str) -> tuple[str | None, str | None]:
    cx = db.ouvrir(site.base_donnees)
    try:
        ligne = cx.execute("SELECT visiteur FROM visites WHERE session_token = ?", (jeton,)).fetchone()
        return (ligne["visiteur"] if ligne else None), correlation.empreinte_de_session(cx, jeton)
    finally:
        cx.close()


def _motif(decision: dict) -> dict:
    motifs = decision["motifs"]
    return motifs[0] if isinstance(motifs, list) else motifs


@pytest.mark.integration
def test_connectee_d_un_lancement_a_l_autre_puis_compte_banni_refuse_a_une_autre_identite(isole):
    if not Path("/Applications/Google Chrome.app").exists():
        pytest.skip("Google Chrome n'est pas installé (channel: chrome)")
    site = isole
    experience = nouvelle_experience(site, "endurance")
    with Chien(BORNE_S) as chien:
        # Visite 1, identité A : la vitrine, puis la connexion (formulaire), puis l'espace.
        jeton_1, premiere = _visiter(site, experience, 1, "chrome-compte-a")
        assert premiere.success, premiere.details
        assert premiere.details["compte"]["connexion"] == "nouvelle"
        assert ident.lire_etat("chrome-compte-a")["connexions"]["demo"]

        # Visite 2, identité A, Chrome relancé, jeton neuf : l'espace sans se reconnecter.
        jeton_2, seconde = _visiter(site, experience, 2, "chrome-compte-a")
        assert seconde.success, seconde.details
        assert seconde.details["compte"]["connexion"] == "gardee"
        assert not [d for d in _decisions(site, jeton_2) if d["chemin"].startswith("/lab/connexion")]
        visiteur_1, empreinte_1 = _visiteur_et_empreinte(site, jeton_1)
        visiteur_2, empreinte_2 = _visiteur_et_empreinte(site, jeton_2)
        assert visiteur_1 is not None and visiteur_1 == visiteur_2  # même visiteur côté site
        assert empreinte_1 is not None and empreinte_1 == empreinte_2  # même empreinte E côté site
        cx = db.ouvrir(site.base_donnees)
        try:
            appareils = cx.execute("SELECT visiteur, nouvel_appareil FROM appareils").fetchall()
            assert [(a["visiteur"], a["nouvel_appareil"]) for a in appareils] == [(visiteur_1, 0)]
            # Le compte banni à la main entre deux visites, par le code de `bannir_avant_visite`.
            assert campaigns._bannir_avant_visite(cx, MONDE, "temoin", 3, compte="demo")
        finally:
            cx.close()

        # Visite 3, identité B (autre navigateur, autre visiteur) : la vitrine passe, la connexion est refusée.
        jeton_3, troisieme = _visiter(site, experience, 3, "chrome-compte-b")
        assert not troisieme.success
        assert troisieme.details["pages_faites"] >= 1, troisieme.details
        assert "motif bannissement" in troisieme.details["compte"]["refus"], troisieme.details["compte"]
        assert ident.lire_etat("chrome-compte-b")["etat"] == "banni"
        visiteur_3, _ = _visiteur_et_empreinte(site, jeton_3)
        assert visiteur_3 is not None and visiteur_3 != visiteur_1
        decisions = _decisions(site, jeton_3)
        rang = next(i for i, d in enumerate(decisions) if d["couche"] == "bannissement")
        assert _motif(decisions[rang])["par"] == "compte" and _motif(decisions[rang])["compte"] == "demo"
        apres = [d["chemin"] for d in decisions[rang + 1 :]]
        assert all(c == "/lab/collecte" for c in apres), apres  # rien n'est demandé après le refus

        # Visite 4, identité B : refusée avant Chrome, aucune requête.
        jeton_4 = nouveau_passage(site, experience, repetition=4, monde=MONDE)
        pilote = DriverNoezia(("127.0.0.1",), {**REGLAGE, "identite": "chrome-compte-b"})
        with pytest.raises(IdentiteRefusee, match="banni"):
            pilote.open()
            try:
                pilote.start_session()
            finally:
                pilote.close()
        assert _decisions(site, jeton_4) == []
    assert not chien.aboye, f"le test ne s'est pas terminé en {BORNE_S} s"
