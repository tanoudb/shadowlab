"""Le site d'annonces (« Habitat Démo », `/lab/vitrine/…`) est caché par défaut sur le site public (demande du client,
14/11/2026 : « masque l'autre site d'annonces, on s'en fout »).

Caché : ses cinq adresses répondent 404 (la page d'erreur de n'importe quelle adresse inconnue) et plus aucune page ne
le cite ni ne suppose deux sites. Réglage `SHADOWLAB_PUBLIC_VITRINE=1` (`ReglagesPublics.vitrine`) : le comportement
d'avant, avec la notice qui décrit les deux sites. Le laboratoire garde son site d'annonces
(`tests/test_labo_inchange.py`).
"""

from __future__ import annotations

import os
import re
from collections import deque
from dataclasses import replace
from html import unescape

import pytest
from fastapi.testclient import TestClient
from parsel import Selector
from test_public import CONTACT, HOTE, IP, ORIGINE, fabriquer, jeton_csrf

from shadowlab import config
from shadowlab.config import ReglagesPublics, charger_public
from shadowlab.public.social import MARQUE as MARQUE_SOCIAL
from shadowlab.site import vitrine

ACCEPT = {"fr": "fr-FR,fr;q=0.9", "en": "en-US,en;q=0.9"}
LANGUES = ("fr", "en")
REFERENCE = vitrine.generer(20261111, 45)[0].reference
CINQ_ADRESSES = [
    "/lab/vitrine",
    "/lab/vitrine/annonces",
    f"/lab/vitrine/annonces/{REFERENCE}",
    f"/lab/vitrine/photos/{REFERENCE}/1.svg",
    f"/lab/vitrine/api/annonces/{REFERENCE}/similaires",
]
# Ce qu'aucune page d'un site caché ne doit contenir (en minuscules, sur le texte visible comme sur le HTML).
INTERDITS_CACHE = (
    "habitat",
    "/lab/vitrine",
    "deux sites",
    "two sites",
    "two demonstration sites",
    "sites de démonstration",
    "demonstration sites",
    "autre site",
    "other site",
    "listing",
    "vraies annonces",
)
INTERDITS_REGEX = re.compile(r"\b(?:les|ces|the|these) sites\b")


@pytest.fixture
def reglages_publics(tmp_path) -> ReglagesPublics:
    """Les réglages par défaut : rien sur le site d'annonces (`vitrine` n'est pas donné)."""
    return ReglagesPublics(
        hotes=(HOTE,),
        contact=CONTACT,
        conservation_jours=90,
        https=True,
        port=8771,
        base_donnees=tmp_path / "public" / "public.sqlite3",
        entete_ip="X-Forwarded-For",
        vitrine_graine=20261111,
        vitrine_taille=45,
        social_taille=12,
    )


@pytest.fixture
def reglages_cachee(reglages_publics) -> ReglagesPublics:
    return reglages_publics


@pytest.fixture
def client_cache(reglages_cachee):
    with fabriquer(reglages_cachee) as c:
        yield c


@pytest.fixture
def client_visible(reglages_publics):
    with fabriquer(replace(reglages_publics, vitrine=True)) as c:
        yield c


def ouvrir_session(client: TestClient, langue: str = "fr") -> None:
    """Ouvre une session consentie sans passer par une page du site d'annonces (caché, il ne peut pas servir)."""
    r = client.post(
        "/session/commencer",
        data={"consentement": "oui", "csrf": jeton_csrf(client), "langue": langue},
        headers={"Origin": ORIGINE, "X-Forwarded-For": IP, "Accept-Language": ACCEPT[langue]},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text


def _liens_sociaux(html: str) -> list[str]:
    refs = Selector(html).css("a::attr(href)").getall()
    return [r.split("#")[0] for r in refs if r.startswith("/lab/social/")]


def pages_du_site(client: TestClient, langue: str) -> dict[str, str]:
    """Toutes les pages HTML de l'étude et du réseau social, dans une langue, avec l'état courant du client :
    accueil, notice, « Ma session », contact, puis tout ce que le réseau social lie (fil, publications, profils,
    étiquettes, explorer, crédits)."""
    entetes = {"Accept-Language": ACCEPT[langue]}
    pages: dict[str, str] = {}
    a_voir = deque(
        ["/", f"/{langue}", f"/{langue}/information", "/session", "/contact", "/contact/envoye", "/lab/social/fil"]
    )
    while a_voir and len(pages) < 80:
        chemin = a_voir.popleft()
        if chemin in pages:
            continue
        r = client.get(chemin, headers=entetes)
        if not r.headers.get("content-type", "").startswith("text/html"):
            continue
        pages[chemin] = r.text
        if chemin.startswith("/lab/social/"):
            a_voir.extend(lien for lien in _liens_sociaux(r.text) if lien not in pages)
    for debut in ("/lab/social/p/", "/lab/social/u/", "/lab/social/t/", "/lab/social/explorer", "/lab/social/credits"):
        assert any(c.startswith(debut) for c in pages), f"aucune page {debut} parcourue"
    return pages


def _fautes(pages: dict[str, str]) -> list[str]:
    fautes = []
    for chemin, html in pages.items():
        for lieu, texte in (
            ("html", html.lower()),
            ("texte", unescape(" ".join(Selector(html).css("body *::text").getall())).lower()),
        ):
            fautes += [f"{chemin} ({lieu}) : {mot}" for mot in INTERDITS_CACHE if mot in texte]
            fautes += [f"{chemin} ({lieu}) : {m}" for m in INTERDITS_REGEX.findall(texte)]
    return fautes


# === Caché (le défaut) =====================================================================================


def test_le_reglage_est_cache_par_defaut(reglages_cachee):
    assert reglages_cachee.vitrine is False


@pytest.mark.parametrize("en_session", [False, True])
@pytest.mark.parametrize("adresse", CINQ_ADRESSES)
def test_cache_les_cinq_adresses_repondent_404_comme_une_adresse_inconnue(client_cache, adresse, en_session):
    if en_session:
        ouvrir_session(client_cache)
    for langue in LANGUES:
        entetes = {"Accept-Language": ACCEPT[langue]}
        r = client_cache.get(adresse, headers=entetes)
        inconnue = client_cache.get("/lab/inexistante", headers=entetes)
        assert inconnue.status_code == 404
        assert r.status_code == 404, f"{adresse} répond {r.status_code}"
        assert r.text == inconnue.text, "la même page 404 que n'importe quelle adresse inconnue"


@pytest.mark.parametrize("langue", LANGUES)
@pytest.mark.parametrize("en_session", [False, True])
def test_cache_aucune_page_ne_cite_le_site_d_annonces_ni_deux_sites(client_cache, langue, en_session):
    if en_session:
        ouvrir_session(client_cache, langue)
    pages = pages_du_site(client_cache, langue)
    assert _fautes(pages) == []


@pytest.mark.parametrize("langue", LANGUES)
@pytest.mark.parametrize("en_session", [False, True])
def test_cache_le_bandeau_du_reseau_social_n_a_plus_de_lien_autre_site(client_cache, langue, en_session):
    if en_session:
        ouvrir_session(client_cache, langue)
    html = client_cache.get("/lab/social/fil", headers={"Accept-Language": ACCEPT[langue]}).text
    sel = Selector(html)
    assert sel.css("aside.session-publique"), "le bandeau est toujours là"
    assert not sel.css("a.autre-site"), "plus de lien « Autre site »"
    assert not sel.css('a[href^="/lab/vitrine"]')


@pytest.mark.parametrize("langue", LANGUES)
def test_cache_la_notice_decrit_un_seul_site(client_cache, langue):
    html = client_cache.get(f"/{langue}/information", headers={"Accept-Language": ACCEPT[langue]}).text
    chapeau = " ".join(Selector(html).css("p.notice-chapeau *::text, p.notice-chapeau::text").getall())
    assert MARQUE_SOCIAL in chapeau
    assert ("Le site de démonstration" if langue == "fr" else "The demonstration site") in chapeau


# === Visible (SHADOWLAB_PUBLIC_VITRINE=1) : le comportement d'avant ====================================


@pytest.mark.parametrize("adresse", CINQ_ADRESSES)
def test_visible_les_cinq_adresses_sont_servies(client_visible, adresse):
    r = client_visible.get(adresse)
    assert r.status_code == 200, f"{adresse} répond {r.status_code}"


@pytest.mark.parametrize("langue", LANGUES)
@pytest.mark.parametrize("en_session", [False, True])
def test_visible_le_bandeau_du_reseau_social_porte_le_lien_autre_site(client_visible, langue, en_session):
    if en_session:
        ouvrir_session(client_visible, langue)
    html = client_visible.get("/lab/social/fil", headers={"Accept-Language": ACCEPT[langue]}).text
    lien = Selector(html).css('a.autre-site[href="/lab/vitrine"]')
    assert len(lien) == 1
    assert "Habitat Démo" in lien.get()


@pytest.mark.parametrize("langue", LANGUES)
def test_visible_la_notice_decrit_les_deux_sites(client_visible, langue):
    html = client_visible.get(f"/{langue}/information", headers={"Accept-Language": ACCEPT[langue]}).text
    texte = unescape(" ".join(Selector(html).css("main *::text").getall()))
    attendu = "Les deux sites de démonstration" if langue == "fr" else "The two demonstration sites"
    assert attendu in texte
    assert MARQUE_SOCIAL in texte and "Habitat Démo" in texte


@pytest.mark.parametrize("langue", LANGUES)
def test_visible_le_pied_parle_de_sites_au_pluriel(client_visible, langue):
    html = client_visible.get(f"/{langue}", headers={"Accept-Language": ACCEPT[langue]}).text
    pied = " ".join(Selector(html).css("footer p *::text, footer p::text").getall())
    assert ("Sites de démonstration entièrement fictifs." if langue == "fr" else "demonstration sites") in pied


@pytest.mark.parametrize("langue", LANGUES)
def test_cache_le_pied_est_au_singulier(client_cache, langue):
    html = client_cache.get(f"/{langue}", headers={"Accept-Language": ACCEPT[langue]}).text
    pied = " ".join(Selector(html).css("footer p *::text, footer p::text").getall())
    assert (
        "Site de démonstration entièrement fictif." if langue == "fr" else "Entirely fictional demonstration site."
    ) in pied


# === Le réglage lu dans l'environnement =====================================================================


@pytest.mark.parametrize("valeur, attendue", [(None, False), ("", False), ("0", False), ("1", True)])
def test_variable_d_environnement_shadowlab_public_vitrine(monkeypatch, tmp_path, valeur, attendue):
    monkeypatch.setattr(config, "_charger_env", lambda *a, **k: None)
    for variable in [v for v in os.environ if v.startswith("SHADOWLAB_")]:
        monkeypatch.delenv(variable)
    monkeypatch.setenv("SHADOWLAB_SORTIES", str(tmp_path))
    if valeur is not None:
        monkeypatch.setenv("SHADOWLAB_PUBLIC_VITRINE", valeur)
    assert charger_public().vitrine is attendue
