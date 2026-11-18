"""Course I9, défaut B : après un refus en cours de visite, la visite ne se terminait pas.

Ce qui s'est passé (base de la course, passage 19, 17/11 à 20:43 UTC) : l'Arena bannit le sujet pendant la fiche
AN-000069 ; le document est déjà servi (200), ses photos reçoivent 403, puis son appel de données
`/lab/vitrine/api/annonces/AN-000069/similaires` aussi. Ensuite, plus aucune requête ni aucune ligne de journal : le
passage reste `en_cours` plus de 3 heures, l'identité reste `ok`, Chrome inactif, le fil principal attend dans la
boucle d'événements de Playwright.

Cause (rejouée ici dans un vrai Chrome) : pour juger un refus, le moteur lit le corps de chaque 403 (`Response.text()`).
Playwright n'en donne le corps qu'une fois la requête finie, et attend sans limite. Or le refus de l'Arena porte
`Cache-Control: no-store` (`gardien._refus`) et `vitrine.js` ne lit pas le corps d'une réponse en échec : la requête de
l'appel de données ne finit jamais (aucun événement `requestfinished`), donc `text()` ne revient jamais. Les photos,
elles, finissent : leur corps se lit.

Ce que ces tests établissent :
1. le moteur n'attend le corps d'un refus que s'il est arrivé, ou un temps borné ; sinon le refus est rendu « corps non
   lu » ; un corps arrivé pendant l'attente est lu ;
2. la sentinelle : le motif `bannissement` lu dans le corps d'un refus bannit l'identité, même après la première page
   de la passe ; un corps non lu ne masque pas un corps lu (ni un refus, ni le défi de la porte) ; seul, il reste un
   refus ;
3. de bout en bout, dans un vrai Chrome au réglage de la course, devant le site du labo au profil `endurance` : un
   bannissement écrit pendant une fiche termine la visite en un temps borné, en échec, avec sa cause, l'identité
   `banni`, et aucune page demandée après.
Ce qu'ils ne prouvent pas : la vraie Arena (frontal TLS, Nginx, Coraza) ; une visite de la vraie course.
"""

from __future__ import annotations

import faulthandler
import json
import random
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import psutil
import pytest
from test_bannissement import _entetes
from test_visiteurs import nouveau_passage, nouvelle_experience

from shadowlab import database as db
from shadowlab import scenarios
from shadowlab.arena import bannissements
from shadowlab.config import charger
from shadowlab.engines.noezia import identite as ident
from shadowlab.engines.noezia.lecture import LectureHumaine
from shadowlab.engines.noezia.moteur import DriverNoezia
from shadowlab.engines.noezia.sentinelle import Alerte, RefusRessource, Sentinelle, verdict_identite
from shadowlab.site import gardien, vitrine
from shadowlab.site import pages as pages_du_site

BASE_SITE = "http://127.0.0.1:8770"
FICHE = f"{BASE_SITE}/lab/vitrine/annonces/AN-000069"
PHOTO = f"{BASE_SITE}/lab/vitrine/photos/AN-000069/1.svg"
DONNEES = f"{BASE_SITE}/lab/vitrine/api/annonces/AN-000069/similaires"
NON_LU = "corps-non-lu"  # le motif d'un refus dont le corps n'est jamais arrivé (`sentinelle.MOTIF_NON_LU`)


def servi(code: str, accept: str) -> tuple[str, dict[str, str]]:
    """(corps, en-têtes) du refus que le vrai gardien rend à une ressource (`gardien._refus`)."""
    reponse = gardien._refus(SimpleNamespace(headers={"accept": accept}), pages_du_site.page_blocage(), code)
    return reponse.body.decode(), dict(reponse.headers)


BANNI_PHOTO = servi("bannissement", "image/avif,image/webp,image/*,*/*;q=0.8")
BANNI_DONNEES = servi("bannissement", "application/json")
DEFI_PHOTO = servi("defi-js", "image/avif,image/webp,image/*,*/*;q=0.8")


def test_le_refus_du_gardien_n_est_pas_garde_en_cache_par_le_navigateur():
    """Ce qui empêche la requête de finir quand la page ne lit pas le corps (constat dans un vrai Chrome, partie 3)."""
    assert BANNI_DONNEES[1]["cache-control"] == "no-store"
    assert BANNI_DONNEES[0] == '{"bloque_par":"bannissement"}'


# ═══ 1. Le moteur : le corps d'un refus n'est attendu qu'un temps borné ════════════════════════════════════


class ReponseFactice:
    """Une réponse 403 de Playwright. Tant que sa requête n'est pas finie, `text()` attendrait sans fin (ce que fait
    Playwright) : la réponse factice le note et lève, pour que le test échoue au lieu de bloquer."""

    def __init__(self, url: str, corps: tuple[str, dict[str, str]]):
        self.url, self.status, self.frame = url, 403, None
        self.request = SimpleNamespace(is_navigation_request=lambda: False)
        self._corps, self.headers = corps
        self.finie = False
        self.lectures_bloquantes = 0

    def text(self) -> str:
        if not self.finie:
            self.lectures_bloquantes += 1
            raise TimeoutError("text() d'une requête jamais finie : Playwright attendrait sans fin")
        return self._corps


class PageFactice:
    """La page de Playwright : `wait_for_timeout` note le temps attendu (rien ne dort) ; `pendant` simule ce qui
    arrive pendant l'attente."""

    def __init__(self, pendant=None):
        self.url, self.main_frame = FICHE, object()
        self.attendu_ms = 0
        self._pendant = pendant

    def evaluate(self, _expression):
        return 0

    def wait_for_timeout(self, ms: float) -> None:
        self.attendu_ms += ms
        if self._pendant is not None:
            self._pendant()


def _pilote(page: PageFactice) -> DriverNoezia:
    d = DriverNoezia(("*",), {"interaction_post_page": True, "resoudre_defis": False})
    d._page = page
    return d


def _recue(d: DriverNoezia, reponse: ReponseFactice, *, finie: bool) -> None:
    """Ce que Playwright livre au moteur : l'événement `response`, puis `requestfinished` si la requête finit."""
    d._noter_reponse(reponse)
    if finie:
        _finir(d, reponse)


def _finir(d: DriverNoezia, reponse: ReponseFactice) -> None:
    reponse.finie = True
    d._noter_fin_de_requete(reponse.request)


def test_le_corps_d_un_refus_qui_n_arrive_jamais_n_est_pas_attendu_sans_fin():
    """Le cas de la course : la photo finit (son corps dit `bannissement`), l'appel de données jamais."""
    page = PageFactice()
    d = _pilote(page)
    photo, donnees = ReponseFactice(PHOTO, BANNI_PHOTO), ReponseFactice(DONNEES, BANNI_DONNEES)
    _recue(d, photo, finie=True)
    _recue(d, donnees, finie=False)

    rendus = d.refus_ressources()

    assert donnees.lectures_bloquantes == 0  # jamais `text()` sur une requête qui n'a pas fini
    assert rendus == [RefusRessource(PHOTO, 403, None, "bannissement"), RefusRessource(DONNEES, 403, None, NON_LU)]
    assert 0 < page.attendu_ms <= 5_000  # une attente bornée, quelques secondes au plus
    assert d.refus_ressources() == []


def test_un_corps_arrive_pendant_l_attente_est_lu():
    page = PageFactice()
    d = _pilote(page)
    donnees = ReponseFactice(DONNEES, BANNI_DONNEES)
    _recue(d, donnees, finie=False)
    page._pendant = lambda: _finir(d, donnees)

    assert d.refus_ressources() == [RefusRessource(DONNEES, 403, None, "bannissement")]
    assert donnees.lectures_bloquantes == 0


def test_sans_corps_en_retard_le_moteur_n_attend_pas():
    page = PageFactice()
    d = _pilote(page)
    _recue(d, ReponseFactice(PHOTO, DEFI_PHOTO), finie=True)
    assert d.refus_ressources() == [RefusRessource(PHOTO, 403, "arena", "defi-js")]
    assert page.attendu_ms == 0


# ═══ 2. La sentinelle : le motif lu dans le corps du refus ═════════════════════════════════════════════════


def test_le_motif_bannissement_d_une_ressource_bannit_meme_apres_la_premiere_page():
    s = Sentinelle(["127.0.0.1"])
    alerte = s.examiner_ressources(
        [RefusRessource(DONNEES, 403, None, NON_LU), RefusRessource(PHOTO, 403, None, "bannissement")]
    )
    assert alerte is not None and alerte.signe == "statut" and alerte.statut == 403
    assert alerte.adresse == PHOTO and alerte.motif == "bannissement"
    assert "403" in alerte.detail and "ressource" in alerte.detail
    assert verdict_identite(alerte, premiere_page=False) == "banni"


@pytest.mark.parametrize("motif", ["fingerprinting", "composite-differe", None])
def test_un_autre_refus_franc_reste_une_alerte_apres_la_premiere_page(motif):
    """D-91 inchangé : un refus sans le motif `bannissement` n'est un bannissement que sur la première page."""
    alerte = Sentinelle(["127.0.0.1"]).examiner_ressources([RefusRessource(PHOTO, 403, None, motif)])
    assert alerte is not None and alerte.signe == "statut"
    assert verdict_identite(alerte, premiere_page=False) == "alerte"
    assert verdict_identite(alerte, premiere_page=True) == "banni"


def test_un_corps_non_lu_ne_masque_pas_le_defi_de_la_porte():
    """La porte expire pendant la fiche : la photo dit `defi-js`, l'appel de données n'a pas de corps lu. C'est le défi
    de la porte qui est jugé (le parcours l'excuse quand la porte peut être repassée), pas un refus franc."""
    alerte = Sentinelle(["127.0.0.1"]).examiner_ressources(
        [RefusRessource(DONNEES, 403, None, NON_LU), RefusRessource(PHOTO, 403, "arena", "defi-js")]
    )
    assert alerte is not None and alerte.signe == "defi" and alerte.defi == "arena" and alerte.adresse == PHOTO


def test_un_corps_non_lu_seul_reste_un_refus():
    """Rien d'autre n'est su : prudence, la passe s'arrête comme pour un corps illisible (refus franc), donc `banni`
    sur la première page de la passe (D-91), `alerte` après."""
    alerte = Sentinelle(["127.0.0.1"]).examiner_ressources([RefusRessource(DONNEES, 403, None, NON_LU)])
    assert alerte is not None and alerte.signe == "statut" and alerte.motif == NON_LU
    assert verdict_identite(alerte, premiere_page=False) == "alerte"
    assert verdict_identite(alerte, premiere_page=True) == "banni"


def test_les_refus_de_la_visite_6_donnent_un_bannissement():
    """Ce que la base de la course montre pour la fiche AN-000069 : la 1ʳᵉ photo refusée par la détection (motif
    `fingerprinting`), les trois suivantes par le bannissement, l'appel de données aussi (corps jamais arrivé)."""
    photos = [f"{BASE_SITE}/lab/vitrine/photos/AN-000069/{n}.svg" for n in range(1, 5)]
    refus = [RefusRessource(photos[0], 403, None, "fingerprinting")]
    refus += [RefusRessource(photo, 403, None, "bannissement") for photo in photos[1:]]
    refus.append(RefusRessource(DONNEES, 403, None, NON_LU))
    alerte = Sentinelle(["127.0.0.1"]).examiner_ressources(refus)
    assert alerte is not None and alerte.motif == "bannissement" and alerte.adresse == photos[1]
    assert verdict_identite(alerte, premiere_page=False) == "banni"


def test_une_alerte_sans_motif_se_construit_comme_avant():
    assert Alerte("statut", "statut 403", FICHE, 403).motif is None


# ═══ 3. De bout en bout : un vrai Chrome, le site du labo, un bannissement pendant une fiche ═════════════════

MONDE = "c-refus:sujet:endurance"
CIBLE = "AN-000003"  # la fiche pendant laquelle le visiteur est banni (3ᵉ page de la visite 2, comme AN-000069)
IDENTITE = "refus-en-cours"
COURSE = {"headless": False, "channel": "chrome", "identite_native": True, "identite": IDENTITE}
BORNE_S = 150  # une visite de quelques pages, porte comprise, finit bien avant


def _descendants_tues() -> int:
    """Tue les processus lancés par ce test (pilote de Playwright, Chrome) : débloque un appel qui n'a pas de fin."""
    tues = 0
    for enfant in psutil.Process().children(recursive=True):
        try:
            enfant.kill()
            tues += 1
        except psutil.Error:
            pass
    return tues


class Chien:
    """Garde-fou d'un test : passé `secondes`, écrit la pile de tous les fils, puis tue Chrome et son pilote. Sans lui,
    une visite qui ne finit pas bloquerait la suite de tests au lieu d'échouer."""

    def __init__(self, secondes: float) -> None:
        self.secondes, self.aboye = secondes, False
        self._fini = threading.Event()
        self._fil = threading.Thread(target=self._garder, daemon=True)

    def _garder(self) -> None:
        if not self._fini.wait(self.secondes):
            self.aboye = True
            faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
            self._piles_des_greenlets()
            _descendants_tues()

    @staticmethod
    def _piles_des_greenlets() -> None:
        """L'API synchrone de Playwright fait tourner le test dans un greenlet : sa pile n'est pas celle du fil."""
        import gc
        import traceback

        import greenlet

        for objet in gc.get_objects():
            if isinstance(objet, greenlet.greenlet) and objet.gr_frame is not None:
                print("--- greenlet en attente :", file=sys.stderr)
                traceback.print_stack(objet.gr_frame, file=sys.stderr)

    def __enter__(self) -> Chien:
        self._fil.start()
        return self

    def __exit__(self, *_exc) -> None:
        self._fini.set()
        self._fil.join()


@pytest.fixture
def site_en_direct(reglages, monkeypatch):
    """Le site du labo (vitrine de 45 annonces) dans ce processus, sur un port libre."""
    import uvicorn

    from shadowlab.site.app import creer_app

    monkeypatch.setenv("SHADOWLAB_VITRINE_TAILLE", "45")
    r = charger()
    serveur = uvicorn.Server(uvicorn.Config(creer_app(r), host="127.0.0.1", port=r.port, log_level="warning"))
    fil = threading.Thread(target=serveur.run, daemon=True)
    fil.start()
    fin = time.monotonic() + 15
    while not serveur.started and time.monotonic() < fin:
        time.sleep(0.05)
    assert serveur.started, "le site du labo n'a pas démarré"
    yield r
    serveur.should_exit = True
    fil.join(timeout=10)


@pytest.fixture
def banni_pendant_la_fiche(site_en_direct, monkeypatch):
    """Le bannissement du visiteur de la session est écrit pendant que le site rend la fiche `CIBLE` : le document est
    déjà passé par le gardien, ses photos et son appel de données ne passeront plus. Rend les jetons bannis."""
    rendre_fiche = vitrine.page_fiche
    bannis: list[str] = []

    def page_fiche(jeton, annonce, **options):
        if annonce.reference == CIBLE and not bannis:
            cx = db.ouvrir(site_en_direct.base_donnees)
            try:
                ligne = cx.execute("SELECT visiteur FROM visites WHERE session_token = ?", (jeton,)).fetchone()
                assert ligne is not None, "le visiteur de la session est inconnu de l'Arena"
                bannissements.bannir(cx, MONDE, visiteur=ligne["visiteur"], motif="detecte:composite")
            finally:
                cx.close()
            bannis.append(jeton)
        return rendre_fiche(jeton, annonce, **options)

    monkeypatch.setattr(vitrine, "page_fiche", page_fiche)
    monkeypatch.setattr(gardien, "suspicion", lambda *a, **k: [])  # seul le bannissement refuse
    # Des pages courtes : le test n'a pas à durer ; l'interaction du moteur reste la vraie.
    monkeypatch.setattr(scenarios, "LECTURE_HUMAINE_VISITE", LectureHumaine(duree_s=(0.5, 1.0, 2.0)))
    return bannis


def _visiter(site, experience: int, repetition: int, pages: int, dossier: Path):
    """Une visite de la course : un Chrome relancé sur l'identité, le scénario `visite` à état durable."""
    jeton = nouveau_passage(site, experience, repetition=repetition, monde=MONDE)
    pilote = DriverNoezia(("127.0.0.1",), dict(COURSE))
    pilote.open()
    try:
        pilote.start_session()
        pilote._contexte.set_extra_http_headers(_entetes(site, "endurance", jeton))  # ce qu'ajoute le frontal
        issue = scenarios.visite(
            pilote,
            f"http://127.0.0.1:{site.port}",
            jeton,
            random.Random(repetition),
            pages=pages,
            duree_porte_s=86_400,
            dossier_recolte=dossier,
        )
        pilote.close_session()
    finally:
        pilote.close()
    return jeton, issue


def _releves(site, jeton: str) -> list[dict]:
    """Les relevés de comportement envoyés par l'observateur pendant la session."""
    cx = db.ouvrir(site.base_donnees)
    try:
        return [
            json.loads(ligne["payload"])
            for ligne in cx.execute(
                "SELECT payload FROM observations_js WHERE session_token = ? AND kind = 'comportement' ORDER BY id",
                (jeton,),
            )
        ]
    finally:
        cx.close()


@pytest.mark.integration
def test_un_bannissement_pendant_une_fiche_termine_la_visite_sans_autre_page(
    site_en_direct, banni_pendant_la_fiche, tmp_path
):
    if not Path("/Applications/Google Chrome.app").exists():
        pytest.skip("Google Chrome n'est pas installé (channel: chrome)")
    site = site_en_direct
    experience = nouvelle_experience(site, "endurance")
    dossier = tmp_path / "recolte-sujet"
    jeton_1, premiere = _visiter(site, experience, 1, 2, dossier)
    assert premiere.success, premiere.details  # la liste et AN-000001 ; la porte franchie, le visiteur connu
    # Défaut A, dans un vrai Chrome : deux pages courtes (parcourues vite), défilables ; la première défilable l'est.
    releves = _releves(site, jeton_1)
    assert sum(1 for r in releves if r.get("page_defilable")) >= 2, releves
    assert sum(r.get("evenements", {}).get("scroll", 0) for r in releves if r.get("page_defilable")) > 0, releves

    debut = time.monotonic()
    with Chien(BORNE_S) as chien:
        jeton, issue = _visiter(site, experience, 2, 15, dossier)
    duree = time.monotonic() - debut
    assert not chien.aboye, f"la visite ne s'est pas terminée en {BORNE_S} s (pile écrite plus haut)"
    assert banni_pendant_la_fiche == [jeton], "le bannissement n'a pas été écrit pendant la visite 2"

    # La visite est finie, en échec, et dit pourquoi.
    print(f"visite 2 : {duree:.1f} s ; refus : {issue.details['refus']}")
    assert duree < BORNE_S
    assert not issue.success
    assert issue.details["statut"] == "arretee", issue.details
    assert "403" in issue.details["refus"] and "ressource" in issue.details["refus"], issue.details["refus"]
    # L'identité est bannie : l'Arena l'a dit dans le corps du refus d'une photo.
    assert issue.details["identite"]["etat"] == "banni", issue.details["identite"]
    assert ident.lire_etat(IDENTITE)["etat"] == "banni"  # `ouvrir` la refuse désormais

    # Aucune page demandée après le premier refus : rien après les refus de la fiche AN-000003 (ses photos, son appel
    # de données), et aucun document de plus.
    cx = db.ouvrir(site.base_donnees)
    try:
        lignes = cx.execute(
            "SELECT chemin, couche, decision FROM decisions WHERE session_token = ? ORDER BY id", (jeton,)
        ).fetchall()
    finally:
        cx.close()
    premier_refus = next(i for i, ligne in enumerate(lignes) if ligne["couche"] == "bannissement")
    apres = {ligne["chemin"] for ligne in lignes[premier_refus:]}
    assert all(f"/{CIBLE}" in chemin or chemin == "/lab/collecte" for chemin in apres), sorted(apres)
