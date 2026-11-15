"""Identité persistante du moteur NOEZIA (I4) : un dossier par identité, verrou, état, refus hors identité native."""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from shadowlab.engines import registre
from shadowlab.engines.noezia import identite as ident
from shadowlab.engines.noezia.moteur import DriverNoezia

NATIVE = {"identite_native": True, "headless": False, "channel": "chrome"}


@pytest.fixture
def racine(tmp_path, monkeypatch):
    dossier = tmp_path / "identites"
    monkeypatch.setenv("SHADOWLAB_IDENTITES", str(dossier))
    return dossier


def moteur(**options):
    return DriverNoezia(("127.0.0.1",), options)


# ── Sans navigateur ────────────────────────────────────────────────────


@pytest.mark.parametrize("nom", ["", "Majuscule", "avec espace", "../evade", "a/b", "-debut", "x" * 41, "é"])
def test_nom_invalide_refuse(racine, nom):
    with pytest.raises(ValueError):
        moteur(**NATIVE, identite=nom)


def test_nom_valide_accepte(racine):
    moteur(**NATIVE, identite="vitrine-suivi-2")
    moteur(**NATIVE, identite="x" * 40)


def test_option_declaree_et_typee(racine):
    assert DriverNoezia.options_permises["identite"] is str
    with pytest.raises(ValueError):
        moteur(**NATIVE, identite=3)


def test_refusee_sans_identite_native(racine):
    with pytest.raises(ValueError, match="identite_native"):
        moteur(identite="a", headless=False, channel="chrome")
    with pytest.raises(ValueError, match="identite_native"):
        moteur(identite="a", identite_native=False, headless=False, channel="chrome")


def test_refusee_sans_interface(racine):
    with pytest.raises(ValueError, match="headless"):
        moteur(identite="a", identite_native=True, channel="chrome")  # headless vaut vrai par défaut
    with pytest.raises(ValueError, match="headless"):
        moteur(identite="a", identite_native=True, headless=True, channel="chrome")


def test_nb_essais_force_a_un(racine):
    assert moteur(**NATIVE, identite="a", nb_essais=5)._nb_essais == 1


def test_nb_essais_inchange_sans_identite():
    assert moteur(nb_essais=3)._nb_essais == 3


def test_configuration_enregistre_nom_et_age(racine):
    conf = moteur(**NATIVE, identite="suivi")
    assert conf.configuration()["identite"] == "suivi"
    assert conf.configuration()["identite_age_jours"] == 0
    (racine / "suivi").mkdir(parents=True)
    (racine / "suivi" / "identite.json").write_text(
        json.dumps({"nom": "suivi", "creee_le": "2026-11-01T10:00:00+00:00", "etat": "ok"}), encoding="utf-8"
    )
    age = moteur(**NATIVE, identite="suivi").configuration()["identite_age_jours"]
    assert age >= 14


def test_configuration_sans_identite_sans_cle():
    assert "identite" not in moteur().configuration()


def test_identite_banni_refusee(racine):
    dossier = racine / "grillee"
    dossier.mkdir(parents=True)
    (dossier / "identite.json").write_text(
        json.dumps({"nom": "grillee", "creee_le": "2026-11-01T10:00:00+00:00", "etat": "banni"}), encoding="utf-8"
    )
    pilote = moteur(**NATIVE, identite="grillee")
    with pytest.raises(ident.IdentiteRefusee, match="banni"):
        pilote.open()


def test_verrou_pris_refuse_le_second(racine):
    premiere = ident.ouvrir("a")
    try:
        with pytest.raises(ident.IdentiteRefusee, match="verrou|utilisée"):
            ident.ouvrir("a")
        with pytest.raises(ident.IdentiteRefusee):
            moteur(**NATIVE, identite="a").open()
    finally:
        premiere.liberer()
    ident.ouvrir("a").liberer()  # libéré : de nouveau possible


def test_deux_identites_ne_se_genent_pas(racine):
    a, b = ident.ouvrir("a"), ident.ouvrir("b")
    try:
        assert a.dossier_profil != b.dossier_profil
    finally:
        a.liberer()
        b.liberer()


def test_dossier_cree_en_700_avec_identite_json(racine):
    i = ident.ouvrir("a")
    try:
        assert (racine / "a").stat().st_mode & 0o777 == 0o700
        assert i.dossier_profil == racine / "a" / "chrome"
        donnees = json.loads((racine / "a" / "identite.json").read_text(encoding="utf-8"))
        assert donnees["nom"] == "a" and donnees["etat"] == "ok" and donnees["creee_le"]
    finally:
        i.liberer()


def test_visite_journalisee(racine):
    i = ident.ouvrir("a")
    i.debut_visite({"chrome": "1"})
    i.fin_visite(pages=3, statut="ok")
    i.liberer()
    lignes = (racine / "a" / "visites.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lignes) == 1
    ligne = json.loads(lignes[0])
    assert ligne["pages"] == 3 and ligne["statut"] == "ok" and ligne["debut"] and ligne["fin"]


def test_racine_par_defaut_sous_outputs(monkeypatch):
    monkeypatch.delenv("SHADOWLAB_IDENTITES", raising=False)
    assert ident.racine_identites().parts[-2:] == ("outputs", "identites")


def test_l_option_ne_peut_pas_changer_le_dossier(racine):
    with pytest.raises(ValueError):
        moteur(**NATIVE, identite="a", dossier_identites="/tmp/x")


def test_registre_expose_l_option(racine):
    assert "identite" in registre()["noezia"].options_permises


# ── Avec navigateur : page de test locale qui pose son propre cookie durable ──


class _Page(BaseHTTPRequestHandler):
    visiteurs: list[str]

    def do_GET(self):  # noqa: N802
        cookie = re.search(r"vid=([0-9a-f]+)", self.headers.get("Cookie", ""))
        nouveau = cookie is None
        vid = cookie.group(1) if cookie else __import__("uuid").uuid4().hex
        self.server.vus.append((vid, nouveau))  # type: ignore[attr-defined]
        corps = (
            "<!doctype html><title>t</title><p id='vid'>" + vid + "</p><p id='ls'>?</p><script>"
            "let v=localStorage.getItem('k');if(!v){v=crypto.randomUUID();localStorage.setItem('k',v)}"
            "document.getElementById('ls').textContent=v</script>"
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if nouveau:
            self.send_header("Set-Cookie", f"vid={vid}; Max-Age=86400; Path=/")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def log_message(self, *args):
        pass


@pytest.fixture
def site_cookie():
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _Page)
    serveur.vus = []  # type: ignore[attr-defined]
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    yield serveur
    serveur.shutdown()
    serveur.server_close()


def _visite(nom, serveur) -> tuple[str, str]:
    """Une visite : Chrome s'ouvre sur l'identité, lit la page, se ferme. Rend (cookie vu, localStorage)."""
    pilote = DriverNoezia(("127.0.0.1",), {**NATIVE, "identite": nom, "interaction_post_page": False})
    pilote.open()
    try:
        pilote.start_session()
        pilote.navigate(f"http://127.0.0.1:{serveur.server_port}/")
        html = pilote.dom()
        pilote.close_session()
    finally:
        pilote.close()
    return (
        re.search(r"id=.vid.>([0-9a-f]+)<", html).group(1),
        re.search(r"id=.ls.>([0-9a-f-]+)<", html).group(1),
    )


def _chrome_installe() -> bool:
    from pathlib import Path

    return Path("/Applications/Google Chrome.app").exists()


@pytest.mark.integration
def test_meme_identite_meme_cookie_et_meme_stockage(racine, site_cookie):
    if not _chrome_installe():
        pytest.skip("Google Chrome n'est pas installé")
    cookie1, ls1 = _visite("retour", site_cookie)
    cookie2, ls2 = _visite("retour", site_cookie)
    assert cookie1 == cookie2
    assert ls1 == ls2
    assert [nouveau for _, nouveau in site_cookie.vus] == [True, False]
    assert len((racine / "retour" / "visites.jsonl").read_text(encoding="utf-8").splitlines()) == 2


@pytest.mark.integration
def test_deux_identites_deux_visiteurs(racine, site_cookie):
    if not _chrome_installe():
        pytest.skip("Google Chrome n'est pas installé")
    cookie_a, ls_a = _visite("alice", site_cookie)
    cookie_b, ls_b = _visite("bob", site_cookie)
    assert cookie_a != cookie_b
    assert ls_a != ls_b
    assert all(nouveau for _, nouveau in site_cookie.vus)
