"""Le défi de la porte servi à la place d'une photo n'est pas un bannissement (répétition 2 de la course I9, 16/11).

Ce que la répétition a montré (vraie Arena, profil `endurancecourt`, porte de 600 s par visiteur) : le sujet passe la
porte à 18:23:31 ; à la visite 3, la liste et 18 photos répondent 200, puis, 600,2 s après la porte, deux photos
chargées au défilement répondent 403. L'Arena a écrit `defi-js emis` : c'est le défi de la porte expirée, pas un refus.
Le moteur rangeait tout 403 de ressource du même hôte parmi les refus, la sentinelle en faisait « statut 403 », et, sur
la première page de la passe, `verdict_identite` rendait `banni` : 197 visites perdues, aucune ligne dans
`bannissements`.

Ce que l'Arena sert vraiment à une photo : `gardien._refus` ne rend la page (défi ou refus) qu'à un client qui accepte
`text/html` (une navigation) ; une photo (`Accept` d'une image) ou l'appel de données de `vitrine.js`
(`Accept: application/json`) reçoit le motif en JSON : `{"bloque_par": "defi-js"}`, ou `{"bloque_par": "bannissement"}`
pour un visiteur banni. Les corps de ces tests sont ceux du vrai gardien (`gardien.controler` par le client de test, ou
`gardien._refus`), pas des textes faits à la main.

Ce que ces tests établissent :
1. le moteur reconnaît la nature du défi d'une ressource au moment de rendre ses refus (corps lu hors du gestionnaire
   d'événement), y compris dans un vrai Chromium devant un petit serveur local ; corps illisible : refus franc ;
2. dans le parcours, le défi de la porte de l'Arena sur une ressource est jugé comme le même défi servi en page à ce
   moment : acceptable, aucune alerte, l'identité reste `ok`, et la page suivante repasse la porte par le chemin
   existant (compté, tracé) ; trop tôt, autre nature, porte non repassable : alerte, jamais `banni` ;
3. un refus franc (page de refus de l'Arena, motif `bannissement`, tout autre 403) reste un bannissement sur la première
   page de la passe, en page comme sur une photo : le témoin sentinelle en dépend.
Ce qu'ils ne prouvent pas : un vrai Chrome devant la vraie Arena (frontal TLS, cookie de porte qui expire) ; la
prochaine répétition le dira.
"""

from __future__ import annotations

import threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from outils_recolte import RECETTE_VITRINE, creer_client, fabriquer, lu
from test_bannissement import MONDE, Navigateur, _entetes, experience, nouvelle_session  # noqa: F401 (montages)
from test_parcours_porte_en_cours import PiloteNavigateur, recette
from test_relecture_porte import DUREE_PORTE_S, PAS_S, Chrome, instant
from test_ressources_de_page import _frontal

from shadowlab.arena import bannissements
from shadowlab.engines.noezia import identite as ident
from shadowlab.engines.noezia.etat import Etat
from shadowlab.engines.noezia.moteur import DriverNoezia
from shadowlab.engines.noezia.parcours import TOLERANCE_PORTE_S, MoteurDriver, Options
from shadowlab.engines.noezia.sentinelle import detecter_defi, detecter_defi_ressource
from shadowlab.site import gardien
from shadowlab.site import pages as pages_du_site

# L'en-tête `Accept` d'une image dans Chrome, et celui de l'appel de données de `vitrine.js`.
ACCEPT_IMAGE = "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
ACCEPT_DONNEES = "application/json"
BASE_SITE = "http://127.0.0.1:8770"
PHOTO_19 = f"{BASE_SITE}/lab/vitrine/photos/AN-000019/1.svg"
PHOTO_20 = f"{BASE_SITE}/lab/vitrine/photos/AN-000020/1.svg"
PAGE_DEFI = pages_du_site.page_defi("d" * 32, 18, "L2xhYi92aXRyaW5lL2Fubm9uY2Vz", jeton="ab" * 16)
PAGE_BLOCAGE = pages_du_site.page_blocage()


def servi(html: str, code: str, accept: str = ACCEPT_IMAGE) -> tuple[str, dict[str, str]]:
    """(corps, en-têtes) du refus que le gardien rend à une requête qui envoie `accept` (`gardien._refus`)."""
    reponse = gardien._refus(SimpleNamespace(headers={"accept": accept}), html, code)
    return reponse.body.decode(), dict(reponse.headers)


DEFI_PHOTO = servi(PAGE_DEFI, "defi-js")  # ce qu'ont reçu AN-000019 et AN-000020
BLOCAGE_PHOTO = servi(PAGE_BLOCAGE, "bannissement")  # ce que reçoit la photo d'un visiteur banni
CLOUDFLARE = (
    '<html><body><form id="challenge-form" action="/x" method="POST"></form></body></html>',
    {"content-type": "text/html"},
)
TURNSTILE_PHOTO = servi(pages_du_site.page_turnstile("cle", "L2xhYi8="), "turnstile")


# ═══ 1. Les corps servis par l'Arena ═════════════════════════════════════════════════════════════════════


def test_la_page_de_refus_de_l_arena_n_est_pas_un_defi():
    assert detecter_defi(PAGE_BLOCAGE) is None and 'data-arena="blocage"' in PAGE_BLOCAGE
    assert detecter_defi_ressource(PAGE_BLOCAGE, {}) is None


@pytest.mark.parametrize(
    ("corps", "attendu"),
    [
        (DEFI_PHOTO, "arena"),  # photo : JSON
        (servi(PAGE_DEFI, "defi-js", ACCEPT_DONNEES), "arena"),  # appel de données : JSON
        (servi(PAGE_DEFI, "defi-js", "text/html,*/*"), "arena"),  # client qui accepte le HTML : la page de défi
        (TURNSTILE_PHOTO, "turnstile"),
        (servi(pages_du_site.page_recaptcha("cle", "L2xhYi8="), "recaptcha"), "recaptcha"),
        (CLOUDFLARE, "cloudflare"),
        (BLOCAGE_PHOTO, None),  # visiteur banni : refus franc
        (servi(PAGE_BLOCAGE, "bannissement", "text/html,*/*"), None),
        (servi(PAGE_BLOCAGE, "fingerprinting"), None),
        (servi(PAGE_BLOCAGE, "composite-differe"), None),
        (('{"bloque_par": "motif-inconnu"}', {}), None),
        (('{"bloque_par": 3}', {}), None),
        (("[1, 2]", {}), None),
        (("Forbidden", {}), None),
        (("", {}), None),
    ],
)
def test_la_nature_du_defi_d_une_ressource(corps, attendu):
    assert detecter_defi_ressource(*corps) == attendu


def test_les_corps_du_test_sont_ceux_que_le_gardien_sert_a_une_photo(client, reglages, nouvelle_session, cx):  # noqa: F811
    """Par `gardien.controler` lui-même : défi de la porte (niveau 04, aucun cookie), puis visiteur banni (endurance) :
    sur sa photo le motif JSON, sur sa page la page de refus."""
    photo = f"/lab/vitrine/photos/AN-000001/1.svg?sl={'0123456789abcdef' * 2}"
    defi = client.get(photo, headers={**_frontal(reglages, "04"), "accept": ACCEPT_IMAGE})
    assert defi.status_code == 403 and defi.text == DEFI_PHOTO[0]
    assert defi.headers["content-type"] == DEFI_PHOTO[1]["content-type"]
    nav = Navigateur(client, reglages)
    jeton = nouvelle_session()
    visiteur = nav.franchir_la_porte(jeton)
    bannissements.bannir(cx, MONDE, visiteur=visiteur, motif="manuel")
    entetes = _entetes(reglages, nav.profil, jeton)
    nav._preparer()
    refus = client.get(f"/lab/vitrine/photos/AN-000001/1.svg?sl={jeton}", headers={**entetes, "accept": ACCEPT_IMAGE})
    assert refus.status_code == 403 and refus.text == BLOCAGE_PHOTO[0]
    nav._preparer()
    page = client.get(f"/lab/vitrine?sl={jeton}", headers={**entetes, "accept": "text/html,*/*"})
    assert page.status_code == 403 and page.text == PAGE_BLOCAGE


@pytest.fixture
def cx(reglages):
    from shadowlab import database as db

    connexion = db.ouvrir(reglages.base_donnees)
    yield connexion
    connexion.close()


# ═══ 2. Le moteur : la nature du défi lue au moment de rendre les refus ══════════════════════════════════


class ReponseFactice:
    """Une réponse de Playwright : le corps ne se lit que par `text()` (un appel au navigateur)."""

    def __init__(self, url, statut, corps=None, entetes=None):
        self.url, self.status = url, statut
        self.request = SimpleNamespace(is_navigation_request=lambda: False)
        self.frame = None
        self._corps, self.headers = corps, entetes or {}
        self.lectures = 0

    def text(self):
        self.lectures += 1
        if self._corps is None:
            raise RuntimeError("Network.getResponseBody: No resource with given identifier found")
        return self._corps


def _pilote_noezia() -> DriverNoezia:
    d = DriverNoezia(("*",), {"interaction_post_page": True, "resoudre_defis": False})
    d._page = SimpleNamespace(
        url="http://127.0.0.1:8770/lab/vitrine/annonces", main_frame=object(), evaluate=lambda _: 0
    )
    return d


def test_le_moteur_rend_la_nature_du_defi_lue_apres_l_evenement():
    d = _pilote_noezia()
    defi = ReponseFactice(PHOTO_19, 403, *DEFI_PHOTO)
    blocage = ReponseFactice(PHOTO_20, 403, *BLOCAGE_PHOTO)
    d._noter_reponse(defi)
    d._noter_reponse(blocage)
    assert defi.lectures == blocage.lectures == 0  # rien n'est lu dans le gestionnaire d'événement
    assert d.refus_ressources() == [(PHOTO_19, 403, "arena"), (PHOTO_20, 403, None)]
    assert d.refus_ressources() == []


def test_un_corps_illisible_reste_un_refus_franc():
    """Prudence : sans corps lisible, on ne sait pas que c'est un défi ; le refus est traité comme avant."""
    d = _pilote_noezia()
    d._noter_reponse(ReponseFactice(PHOTO_19, 403, corps=None))
    assert d.refus_ressources() == [(PHOTO_19, 403, None)]


def test_le_moteur_de_parcours_transmet_la_nature_du_defi():
    d = _pilote_noezia()
    d._noter_reponse(ReponseFactice(PHOTO_19, 403, *DEFI_PHOTO))
    assert MoteurDriver(d, "navigateur").refus_ressources() == [(PHOTO_19, 403, "arena")]


class _ArenaLocale(BaseHTTPRequestHandler):
    """Une page qui charge une photo et fait un appel de données (comme `vitrine.js`) ; les deux reçoivent le refus
    que construit `gardien._refus` à partir de l'`Accept` réellement envoyé par Chromium (défi ou bannissement)."""

    def do_GET(self):  # noqa: N802
        if self.path == "/":
            corps = (
                b"<!doctype html><title>liste</title><img src='/photo.svg' alt=''><script>"
                b"fetch('/api', {headers: {Accept: 'application/json'}})"
                b".finally(() => { document.body.dataset.fini = '1'; });</script>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        else:
            self.server.accepts[self.path] = self.headers.get("Accept", "")  # type: ignore[attr-defined]
            html, code = self.server.refus  # type: ignore[attr-defined]
            reponse = gardien._refus(SimpleNamespace(headers={"accept": self.headers.get("Accept", "")}), html, code)
            corps = reponse.body
            self.send_response(reponse.status_code)
            self.send_header("Content-Type", reponse.headers["content-type"])
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def log_message(self, *args):
        pass


@pytest.fixture
def arena_locale():
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _ArenaLocale)
    serveur.accepts = {}  # type: ignore[attr-defined]
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    yield serveur
    serveur.shutdown()
    serveur.server_close()


@pytest.mark.integration
@pytest.mark.parametrize(
    ("refus", "attendu"), [((PAGE_DEFI, "defi-js"), "arena"), ((PAGE_BLOCAGE, "bannissement"), None)]
)
def test_dans_un_vrai_chromium_la_nature_du_defi_d_une_photo_et_d_un_appel_de_donnees(arena_locale, refus, attendu):
    arena_locale.refus = refus
    base = f"http://127.0.0.1:{arena_locale.server_port}"
    pilote = DriverNoezia(("127.0.0.1",), {"interaction_post_page": False, "resoudre_defis": False})
    pilote.open()
    try:
        pilote.start_session()
        assert pilote.navigate(f"{base}/").status == 200
        assert pilote.wait_for_element("body[data-fini]") is not None
        rendus = pilote.refus_ressources()
        pilote.close_session()
    finally:
        pilote.close()
    assert sorted(rendus) == [(f"{base}/api", 403, attendu), (f"{base}/photo.svg", 403, attendu)]
    assert "text/html" not in arena_locale.accepts["/photo.svg"]  # d'où le motif JSON, pas la page
    assert arena_locale.accepts["/api"] == ACCEPT_DONNEES


# ═══ 3. Le parcours ═══════════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def site(reglages, monkeypatch):
    with creer_client(monkeypatch) as client:
        yield client


@pytest.fixture
def identite(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOWLAB_IDENTITES", str(tmp_path / "identites"))
    ouverte = ident.ouvrir("defi-ressource")
    yield ouverte
    ouverte.liberer()


class ChromeEtSesPhotos(Chrome):
    """Chrome en mode identité (page relue sur place) qui relève aussi les 403 de ses ressources, comme le moteur :
    la nature du défi est lue dans le corps servi (`detecter_defi_ressource`)."""

    def __init__(self, client, identite):
        super().__init__(client, identite)
        self.refus: list[tuple[str, int, str | None]] = []

    def refus_ressources(self):
        refus, self.refus = self.refus, []
        return refus


class NavigateurEtSesPhotos(PiloteNavigateur):
    """Le même sans identité persistante (récolte générale avec porte repassable)."""

    def __init__(self, client):
        super().__init__(client, pas_s=PAS_S)
        self.refus: list[tuple[str, int, str | None]] = []

    def refus_ressources(self):
        refus, self.refus = self.refus, []
        return refus


def a_la_requete(pilote, rang: int, action) -> None:
    """À la `rang`-ième page demandée, `action()` ; l'horloge du pilote avance toujours."""
    avancer = pilote.pendant

    def pendant():
        avancer()
        if pilote.requetes_pages == rang:
            action()

    pilote.pendant = pendant


def photos_refusees(pilote, rang: int, *corps: tuple[str, dict[str, str]]) -> None:
    """Pendant la `rang`-ième page, les photos AN-000019, AN-000020… reçoivent un 403 avec ces corps."""
    refus = [
        (f"{BASE_SITE}/lab/vitrine/photos/AN-{19 + i:06d}/1.svg", 403, detecter_defi_ressource(*c))
        for i, c in enumerate(corps)
    ]
    a_la_requete(pilote, rang, lambda: setattr(pilote, "refus", refus))


def defi_en_page(pilote, rang: int) -> None:
    """La `rang`-ième page demandée reçoit la page de défi de l'Arena (403) ; Chrome la franchit seul (la page relue
    sur place devient la vraie page). Les autres pages sont servies telles quelles."""
    avancer = pilote.pendant

    def pendant():
        avancer()
        if pilote.requetes_pages == rang:
            chemin = pilote.urls[-1].removeprefix(BASE_SITE)
            pilote.reponses["/lab/vitrine/"] = (403, PAGE_DEFI)
            pilote.apres_attente = [(403, PAGE_DEFI), (200, pilote.client.get(chemin).text)]
        else:
            pilote.reponses.pop("/lab/vitrine/", None)

    pilote.pendant = pendant


COURSE = recette(repassages_max=10, ecart_min_s=300) + f"  duree_s: {DUREE_PORTE_S}\n"  # la porte du scénario `visite`


def lancer(dossier, pilote, texte=COURSE, pages=4):
    h = pilote.horloge
    p = fabriquer(
        dossier,
        pilote,
        texte=texte,
        options=Options(pages_max=pages),
        horloge=h,
        horodatage=lambda: instant(h.t).isoformat(timespec="seconds"),
    )
    return p, p.lancer()


def porte_passee_avant_la_premiere_page(pilote, identite, secondes: float) -> None:
    identite.noter_porte(instant(pilote.horloge.t + PAS_S) - timedelta(seconds=secondes))


def evenements(dossier, genre):
    etat = Etat(dossier / "etat.sqlite3")
    try:
        return [e["detail"] for e in etat.evenements(1) if e["genre"] == genre]
    finally:
        etat.fermer()


def test_le_defi_de_la_porte_sur_les_photos_de_la_premiere_page_ne_bannit_pas_et_la_page_suivante_repasse_la_porte(
    site, identite, tmp_path
):
    """Le cas de la répétition 2 : porte passée 590 s avant la première page, elle expire pendant cette page ; deux
    photos reçoivent le défi (JSON de l'Arena). La visite continue SANS recharger la page ; la page suivante reçoit le
    défi en page et la porte est repassée par le chemin existant (`_porte_en_cours`), comptée et tracée."""
    pilote = ChromeEtSesPhotos(site, identite)
    porte_passee_avant_la_premiere_page(pilote, identite, DUREE_PORTE_S - 10)
    avant = identite.porte_franchie_le()
    photos_refusees(pilote, 1, DEFI_PHOTO, DEFI_PHOTO)
    defi_en_page(pilote, 2)
    p, bilan = lancer(tmp_path / "r", pilote)

    assert bilan.code == 0 and bilan.statut == "limitee", bilan.arret
    assert identite.etat()["etat"] == "ok" and identite.porte_franchie_le() > avant
    assert pilote.requetes_pages == 4
    premiere = pilote.urls[next(i for i, u in enumerate(pilote.urls) if not u.endswith("/robots.txt"))]
    assert pilote.urls.count(premiere) == 1  # la page aux photos refusées n'est jamais rechargée
    repassages = lu(tmp_path / "r")["porte_repassages"]
    assert repassages["nombre"] == 1 and len(repassages["passages"]) == 1
    passage = repassages["passages"][0]
    assert passage["franchie"] is True and passage["rang"] == 2 and passage["defi"] == "arena"
    (vu,) = evenements(tmp_path / "r", "porte_ressource")
    assert vu["adresse"] == PHOTO_19 and vu["defi"] == "arena" and "refus" not in vu
    assert any("ressource" in ligne and "Porte" in ligne for ligne in p.sortie_ecran)


def test_le_defi_de_la_porte_sur_une_photo_de_la_derniere_page_laisse_l_identite_ok(site, identite, tmp_path):
    """La visite finit avant toute autre page : rien n'est demandé de plus, la visite suivante passera la porte."""
    pilote = ChromeEtSesPhotos(site, identite)
    porte_passee_avant_la_premiere_page(pilote, identite, DUREE_PORTE_S - 10)
    photos_refusees(pilote, 1, DEFI_PHOTO)
    _, bilan = lancer(tmp_path / "r", pilote, pages=1)
    assert bilan.statut == "limitee" and pilote.requetes_pages == 1
    assert identite.etat()["etat"] == "ok"
    assert lu(tmp_path / "r")["porte_repassages"]["nombre"] == 0


@pytest.mark.parametrize("corps", [BLOCAGE_PHOTO, (PAGE_BLOCAGE, {}), ("Forbidden", {})], ids=["json", "page", "autre"])
def test_le_refus_de_l_arena_sur_une_photo_de_la_premiere_page_reste_un_bannissement(site, identite, tmp_path, corps):
    """Le témoin sentinelle : visiteur banni, l'Arena refuse aussi ses photos ; 0 page demandée après le refus."""
    pilote = ChromeEtSesPhotos(site, identite)
    porte_passee_avant_la_premiere_page(pilote, identite, 60)
    photos_refusees(pilote, 1, corps)
    _, bilan = lancer(tmp_path / "r", pilote)
    assert bilan.code == 3 and bilan.arret["signe"] == "statut" and bilan.arret["statut"] == 403
    assert bilan.arret["adresse"] == PHOTO_19 and pilote.requetes_pages == 1
    assert identite.etat()["etat"] == "banni"


def test_le_refus_de_l_arena_en_page_a_la_premiere_page_reste_un_bannissement(site, identite, tmp_path):
    pilote = ChromeEtSesPhotos(site, identite)
    porte_passee_avant_la_premiere_page(pilote, identite, 60)
    pilote.reponses["/lab/vitrine/"] = (403, PAGE_BLOCAGE)
    _, bilan = lancer(tmp_path / "r", pilote)
    assert bilan.code == 3 and bilan.arret["signe"] == "statut" and bilan.arret["statut"] == 403
    assert pilote.requetes_pages == 1 and identite.etat()["etat"] == "banni"


def test_un_refus_franc_l_emporte_sur_un_defi_dans_la_meme_page(site, identite, tmp_path):
    pilote = ChromeEtSesPhotos(site, identite)
    porte_passee_avant_la_premiere_page(pilote, identite, DUREE_PORTE_S - 10)
    photos_refusees(pilote, 1, DEFI_PHOTO, BLOCAGE_PHOTO)
    _, bilan = lancer(tmp_path / "r", pilote)
    assert bilan.arret["signe"] == "statut" and bilan.arret["adresse"] == PHOTO_20
    assert identite.etat()["etat"] == "banni"


def test_le_defi_de_la_porte_sur_une_photo_trop_tot_donne_porte_revenue_jamais_banni(site, identite, tmp_path):
    pilote = ChromeEtSesPhotos(site, identite)
    porte_passee_avant_la_premiere_page(pilote, identite, DUREE_PORTE_S - TOLERANCE_PORTE_S - 30)
    photos_refusees(pilote, 1, DEFI_PHOTO)
    _, bilan = lancer(tmp_path / "r", pilote)
    assert bilan.code == 3 and bilan.arret["signe"] == "porte_revenue" and bilan.arret["adresse"] == PHOTO_19
    assert pilote.requetes_pages == 1 and identite.etat()["etat"] == "alerte"
    (vu,) = evenements(tmp_path / "r", "porte_ressource")
    assert vu["refus"] == "duree_s"
    assert lu(tmp_path / "r")["porte_repassages"]["passages"] == []  # pas un passage de la porte


@pytest.mark.parametrize(
    ("corps", "nature"), [(CLOUDFLARE, "cloudflare"), (TURNSTILE_PHOTO, "turnstile")], ids=["cloudflare", "turnstile"]
)
def test_un_defi_d_une_autre_nature_sur_une_photo_donne_une_alerte(site, identite, tmp_path, corps, nature):
    pilote = ChromeEtSesPhotos(site, identite)
    porte_passee_avant_la_premiere_page(pilote, identite, DUREE_PORTE_S - 10)
    photos_refusees(pilote, 1, DEFI_PHOTO, corps)  # l'autre nature l'emporte sur le défi de la porte
    _, bilan = lancer(tmp_path / "r", pilote)
    assert bilan.code == 3 and bilan.arret["signe"] == "defi" and nature in bilan.arret["detail"]
    assert bilan.arret["adresse"] == PHOTO_20 and pilote.requetes_pages == 1
    assert identite.etat()["etat"] == "alerte"


@pytest.mark.parametrize(
    "texte",
    [recette() + f"  duree_s: {DUREE_PORTE_S}\n", RECETTE_VITRINE.read_text(encoding="utf-8")],
    ids=["porte-sans-repassage", "sans-porte"],
)
def test_un_defi_sur_une_photo_sans_porte_repassable_donne_une_alerte(site, identite, tmp_path, texte):
    pilote = ChromeEtSesPhotos(site, identite)
    porte_passee_avant_la_premiere_page(pilote, identite, DUREE_PORTE_S - 10)
    photos_refusees(pilote, 1, DEFI_PHOTO)
    _, bilan = lancer(tmp_path / "r", pilote, texte=texte)
    assert bilan.code == 3 and bilan.arret["signe"] == "defi" and "arena" in bilan.arret["detail"]
    assert pilote.requetes_pages == 1 and identite.etat()["etat"] == "alerte"


@pytest.mark.parametrize(("ecart_min_s", "arretee"), [(300, True), (0, False)])
def test_sans_identite_l_ecart_minimal_juge_le_defi_d_une_photo(site, tmp_path, ecart_min_s, arretee):
    """Récolte générale sans identité : l'écart depuis le début de la passe (20 s ici) contre `ecart_min_s`."""
    pilote = NavigateurEtSesPhotos(site)
    photos_refusees(pilote, 1, DEFI_PHOTO)
    defi_en_page(pilote, 2)
    _, bilan = lancer(tmp_path / "r", pilote, texte=recette(repassages_max=10, ecart_min_s=ecart_min_s))
    if arretee:
        assert bilan.code == 3 and bilan.arret["signe"] == "defi" and pilote.requetes_pages == 1
        assert evenements(tmp_path / "r", "porte_ressource")[0]["refus"] == "ecart_min_s"
    else:
        assert bilan.statut == "limitee", bilan.arret
        assert lu(tmp_path / "r")["porte_repassages"]["nombre"] == 1


def test_un_pilote_qui_rend_des_couples_reste_lu_comme_avant(site, tmp_path):
    """Un pilote qui ne donne pas la nature (adresse, statut) : refus franc, comme avant."""
    pilote = NavigateurEtSesPhotos(site)
    a_la_requete(pilote, 1, lambda: setattr(pilote, "refus", [(PHOTO_19, 403)]))
    _, bilan = lancer(tmp_path / "r", pilote, texte=recette(repassages_max=10, ecart_min_s=0))
    assert bilan.arret["signe"] == "statut" and bilan.arret["adresse"] == PHOTO_19
