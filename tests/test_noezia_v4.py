"""Tests du moteur NOEZIA v4 (modules sans navigateur)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

# ── Profils ────────────────────────────────────────────────────────────


class TestProfilGenerateur:
    def test_profil_complet(self):
        from shadowlab.engines.noezia.profils.generateur import generer_profil

        p = generer_profil("test-gen")
        assert p.nom == "test-gen"
        assert p.os in ("macos", "windows", "linux")
        assert p.user_agent.startswith("Mozilla/5.0")
        assert "HeadlessChrome" not in p.user_agent
        assert p.canvas_seed != p.audio_seed or p.canvas_seed == 0  # très improbable

    def test_profil_os_force(self):
        from shadowlab.engines.noezia.profils.generateur import generer_profil

        p = generer_profil("test-mac", os="macos")
        assert p.os == "macos"
        assert p.platform == "MacIntel"
        assert "Macintosh" in p.user_agent

    def test_profil_reproductible(self):
        import random

        from shadowlab.engines.noezia.profils.generateur import generer_profil

        r1 = random.Random(42)
        r2 = random.Random(42)
        p1 = generer_profil("test-seed", rng=r1)
        p2 = generer_profil("test-seed", rng=r2)
        assert p1.canvas_seed == p2.canvas_seed
        assert p1.gpu_renderer == p2.gpu_renderer
        assert p1.user_agent == p2.user_agent

    def test_viewport(self):
        from shadowlab.engines.noezia.profils.generateur import generer_profil

        p = generer_profil("test-vp")
        vp = p.viewport()
        assert vp["width"] <= 1920
        assert vp["height"] <= 1080
        assert vp["width"] > 0

    def test_digest_deterministe(self):
        import random

        from shadowlab.engines.noezia.profils.generateur import generer_profil

        r = random.Random(99)
        p = generer_profil("test-digest", rng=r)
        d1 = p.digest()
        d2 = p.digest()
        assert d1 == d2
        assert len(d1) == 16

    def test_serialisation(self):
        from shadowlab.engines.noezia.profils.generateur import ProfilNavigateur, generer_profil

        p = generer_profil("test-ser")
        d = p.en_dict()
        p2 = ProfilNavigateur.de_dict(d)
        assert p.nom == p2.nom
        assert p.canvas_seed == p2.canvas_seed
        assert p.user_agent == p2.user_agent

    def test_client_hints(self):
        from shadowlab.engines.noezia.profils.generateur import generer_profil

        p = generer_profil("test-ch")
        assert "Chromium" in p.sec_ch_ua
        assert "Google Chrome" in p.sec_ch_ua
        assert p.chrome_major in p.sec_ch_ua


class TestProfilCoherence:
    def test_profil_genere_coherent(self):
        from shadowlab.engines.noezia.profils.coherence import valider
        from shadowlab.engines.noezia.profils.generateur import generer_profil

        for _ in range(20):
            p = generer_profil()
            anomalies = valider(p)
            erreurs = [a for a in anomalies if a.gravite == "erreur"]
            assert not erreurs, f"Erreurs pour {p.nom} ({p.os}) : {[a.message for a in erreurs]}"


class TestProfilStockage:
    def test_sauvegarder_charger(self):
        from shadowlab.engines.noezia.profils.generateur import generer_profil
        from shadowlab.engines.noezia.profils.stockage import charger, sauvegarder

        p = generer_profil("test-stockage")
        with tempfile.TemporaryDirectory() as tmp:
            dossier = Path(tmp)
            sauvegarder(p, dossier)
            p2 = charger("test-stockage", dossier)
            assert p2 is not None
            assert p2.nom == p.nom
            assert p2.canvas_seed == p.canvas_seed

    def test_charger_inexistant(self):
        from shadowlab.engines.noezia.profils.stockage import charger

        with tempfile.TemporaryDirectory() as tmp:
            assert charger("nexiste-pas", Path(tmp)) is None


# ── Comportement ───────────────────────────────────────────────────────


class TestSouris:
    def test_minimum_jerk_bornes(self):
        from shadowlab.engines.noezia.comportement.souris import minimum_jerk

        assert minimum_jerk(0.0) == pytest.approx(0.0)
        assert minimum_jerk(1.0) == pytest.approx(1.0)
        assert 0.4 < minimum_jerk(0.5) < 0.6

    def test_temps_fitts(self):
        from shadowlab.engines.noezia.comportement.souris import temps_fitts

        t1 = temps_fitts(100, 20)
        t2 = temps_fitts(500, 20)
        assert t2 > t1  # plus loin → plus long
        t3 = temps_fitts(500, 100)
        assert t3 < t2  # cible plus large → plus rapide

    def test_trajectoire_points(self):
        from shadowlab.engines.noezia.comportement.souris import trajectoire

        pts = trajectoire(0, 0, 500, 300, largeur_cible=20)
        assert len(pts) > 10
        assert pts[0].x == pytest.approx(0, abs=5)
        assert pts[0].y == pytest.approx(0, abs=5)
        dernier = pts[-1]
        assert abs(dernier.x - 500) < 15
        assert abs(dernier.y - 300) < 15
        # Temps croissant
        for i in range(1, len(pts)):
            assert pts[i].t >= pts[i - 1].t - 0.001

    def test_trajectoire_courte(self):
        from shadowlab.engines.noezia.comportement.souris import trajectoire

        pts = trajectoire(100, 100, 105, 103, largeur_cible=20)
        assert len(pts) >= 3


class TestClavier:
    def test_voisines(self):
        from shadowlab.engines.noezia.comportement.clavier import VOISINES

        assert "q" in VOISINES["a"]
        assert len(VOISINES) == 26


class TestTempo:
    def test_pause_lecture_bornee(self):
        import time

        from shadowlab.engines.noezia.comportement.tempo import pause_lecture

        debut = time.monotonic()
        pause_lecture(50)
        duree = time.monotonic() - debut
        assert 0.05 < duree < 8.0


# ── Configuration ──────────────────────────────────────────────────────


class TestConfig:
    def test_config_defaut(self):
        from shadowlab.engines.noezia.config import ConfigNoezia

        c = ConfigNoezia()
        assert c.headless is True
        assert c.souris.actif is True
        assert c.furtivite.canvas_noise is True
        assert c.viewport_width == 1920

    def test_config_immutable(self):
        from shadowlab.engines.noezia.config import ConfigNoezia

        c = ConfigNoezia()
        with pytest.raises(AttributeError):
            c.headless = False


# ── Furtivité ──────────────────────────────────────────────────────────


class TestFurtivite:
    def test_scripts_furtivite_count(self):
        from shadowlab.engines.noezia.furtivite.patches import scripts_furtivite
        from shadowlab.engines.noezia.profils.generateur import generer_profil

        p = generer_profil("test-furtif")
        scripts = scripts_furtivite(p)
        # profil + nav + iframes + env + canvas + webgl + audio
        # + codecs + polices + headless + workers + cdp + automation
        assert len(scripts) == 13

    def test_scripts_contiennent_profil(self):
        from shadowlab.engines.noezia.furtivite.patches import scripts_furtivite
        from shadowlab.engines.noezia.profils.generateur import generer_profil

        p = generer_profil("test-profil-injecte")
        scripts = scripts_furtivite(p)
        assert "__NOEZIA_PROFIL__" in scripts[0]
        assert str(p.canvas_seed) in scripts[0]

    def test_scripts_desactivation_selective(self):
        from shadowlab.engines.noezia.furtivite.patches import scripts_furtivite
        from shadowlab.engines.noezia.profils.generateur import generer_profil

        p = generer_profil("test-selective")
        scripts = scripts_furtivite(p, canvas=False, audio=False)
        # profil + nav + iframes + env + webgl + codecs
        # + polices + headless + workers + cdp + automation
        assert len(scripts) == 11


# ── Moteur (sans navigateur) ──────────────────────────────────────────


class TestMoteurSansBrowser:
    def test_import_et_attributs(self):
        from shadowlab.engines.noezia import DriverNoezia

        assert DriverNoezia.name == "noezia"
        assert DriverNoezia.runtime == "navigateur"
        assert DriverNoezia.executes_javascript is True
        assert DriverNoezia.categorie == "anti_detection"

    def test_registre_contient_noezia(self):
        from shadowlab.engines import registre

        r = registre()
        assert "noezia" in r
        assert "noezia-experimental" in r  # v3 toujours là

    def test_options_permises(self):
        from shadowlab.engines.noezia import DriverNoezia

        assert "headless" in DriverNoezia.options_permises
        assert "profil" in DriverNoezia.options_permises
        assert "simuler_souris" in DriverNoezia.options_permises

    def test_option_inconnue_refusee(self):
        from shadowlab.engines.noezia import DriverNoezia

        with pytest.raises(ValueError, match="option inconnue"):
            DriverNoezia(("127.0.0.1",), {"inconnue": True})

    def test_manque_rien(self):
        from shadowlab.engines.noezia import DriverNoezia

        assert DriverNoezia.manque() is None

    def test_configuration(self):
        from shadowlab.engines.noezia import DriverNoezia

        d = DriverNoezia(("127.0.0.1",))
        conf = d.configuration()
        assert conf["browser"] == "chromium-patchright"
        assert conf["headless"] is True
        assert conf["simuler_souris"] is True
        assert conf["furtivite_canvas"] is True


# ── Détecteurs v4 (sans navigateur) ──────────────────────────────────


def _obs_vide(**kw):
    from shadowlab.detection import Observations

    defaults = {"http": [], "js": [], "attend_js": True}
    defaults.update(kw)
    return Observations(**defaults)


def _obs_avec_empreinte(empreinte, **kw):
    return _obs_vide(js=[{"kind": "empreinte", "payload": empreinte}], **kw)


class TestDetecteursV4:
    def test_prototypes_toString_patche(self):
        from shadowlab.detection import DetecteurPrototypes

        d = DetecteurPrototypes()
        obs = _obs_avec_empreinte({"prototypes": {"toString_self": "function faux() {}"}})
        r = d.classer(obs)
        assert r.classification == "automatise"

    def test_prototypes_canvas_patche(self):
        from shadowlab.detection import DetecteurPrototypes

        d = DetecteurPrototypes()
        obs = _obs_avec_empreinte({"prototypes": {"canvas_natif": False}})
        r = d.classer(obs)
        assert any(s.code == "canvas_patche" for s in r.signals)

    def test_prototypes_hwc_instance(self):
        from shadowlab.detection import DetecteurPrototypes

        d = DetecteurPrototypes()
        obs = _obs_avec_empreinte({"prototypes": {"hwc_instance": True}})
        r = d.classer(obs)
        assert any(s.code == "hwc_instance" for s in r.signals)

    def test_coherence_profonde_avail_gt_screen(self):
        from shadowlab.detection import DetecteurCoherenceProfonde

        d = DetecteurCoherenceProfonde()
        obs = _obs_avec_empreinte({"ecran": {"width": 1920, "availWidth": 2000, "height": 1080, "availHeight": 1080}})
        r = d.classer(obs)
        assert any(s.code == "avail_gt_screen" for s in r.signals)

    def test_coherence_profonde_outer_eq_inner(self):
        from shadowlab.detection import DetecteurCoherenceProfonde

        d = DetecteurCoherenceProfonde()
        obs = _obs_avec_empreinte(
            {
                "fenetre": {"outerWidth": 1920, "innerWidth": 1920, "outerHeight": 1080, "innerHeight": 1080},
            }
        )
        r = d.classer(obs)
        assert any(s.code == "outer_eq_inner" for s in r.signals)

    def test_entropie_timing_regulier(self):
        from shadowlab.detection import DetecteurEntropieInteraction

        d = DetecteurEntropieInteraction()
        delais = [16.0] * 30  # parfaitement régulier = machine
        obs = _obs_vide(js=[{"kind": "comportement", "payload": {"delais_souris_ms": delais}}])
        r = d.classer(obs)
        assert any(s.code == "timing_trop_regulier" for s in r.signals)

    def test_canvas_empreinte_patches(self):
        from shadowlab.detection import DetecteurEmpreinteCanvas

        d = DetecteurEmpreinteCanvas()
        obs = _obs_avec_empreinte({"prototypes": {"canvas_natif": False, "webgl_getParameter_natif": False}})
        r = d.classer(obs)
        assert any(s.code == "canvas_webgl_patches" for s in r.signals)

    def test_integrite_function_length(self):
        from shadowlab.detection import DetecteurIntegriteProprietes

        d = DetecteurIntegriteProprietes()
        obs = _obs_avec_empreinte({"integrite": {"toDataURL_length": 3, "toDataURL_name": "toDataURL"}})
        r = d.classer(obs)
        assert any(s.code == "toDataURL_length_incorrect" for s in r.signals)

    def test_integrite_stack_trace(self):
        from shadowlab.detection import DetecteurIntegriteProprietes

        d = DetecteurIntegriteProprietes()
        obs = _obs_avec_empreinte(
            {
                "integrite": {"toDataURL_error_stack": ["TypeError: ...", "    at toDataURL (eval:1:5)", "    at foo"]},
            }
        )
        r = d.classer(obs)
        assert any(s.code == "stack_toDataURL_js" for s in r.signals)

    def test_integrite_outerWidth_patche(self):
        from shadowlab.detection import DetecteurIntegriteProprietes

        d = DetecteurIntegriteProprietes()
        obs = _obs_avec_empreinte({"integrite": {"outerWidth_propre": True, "outerWidth_getter_natif": False}})
        r = d.classer(obs)
        assert any(s.code == "outerWidth_patche" for s in r.signals)

    def test_coherence_env_timezone_offset(self):
        from shadowlab.detection import DetecteurCoherenceEnvironnement

        d = DetecteurCoherenceEnvironnement()
        obs = _obs_avec_empreinte(
            {
                "fuseau": {"zone": "Europe/Paris", "decalage": 480},
                "navigateur": {"language": "fr"},
            }
        )
        r = d.classer(obs)
        assert any(s.code == "timezone_offset_incoherent" for s in r.signals)

    def test_coherence_env_propre(self):
        from shadowlab.detection import DetecteurCoherenceEnvironnement

        d = DetecteurCoherenceEnvironnement()
        obs = _obs_avec_empreinte(
            {
                "fuseau": {"zone": "Europe/Paris", "decalage": -60},
                "navigateur": {"language": "fr-FR"},
                "ecran": {"width": 1920},
                "fenetre": {"innerWidth": 1440},
            }
        )
        r = d.classer(obs)
        assert r.classification == "humain"

    def test_stack_trace_patchright(self):
        from shadowlab.detection import DetecteurStackTrace

        d = DetecteurStackTrace()
        obs = _obs_avec_empreinte({"stack_trace_test": {"contient_patchright": True}})
        r = d.classer(obs)
        assert r.classification == "automatise"
        assert any(s.code == "stack_patchright" for s in r.signals)

    def test_stack_trace_propre(self):
        from shadowlab.detection import DetecteurStackTrace

        d = DetecteurStackTrace()
        obs = _obs_avec_empreinte(
            {
                "stack_trace_test": {
                    "contient_patchright": False,
                    "contient_playwright": False,
                    "contient_puppeteer": False,
                    "contient_cdp": False,
                    "contient_devtools": False,
                    "prepareStackTrace_present": False,
                }
            }
        )
        r = d.classer(obs)
        assert r.classification == "humain"

    def test_position_fenetre_zero(self):
        from shadowlab.detection import DetecteurPositionFenetre

        d = DetecteurPositionFenetre()
        obs = _obs_avec_empreinte({"performance_memory": {"screenX": 0, "screenY": 0}})
        r = d.classer(obs)
        assert any(s.code == "screen_position_zero" for s in r.signals)

    def test_position_fenetre_normale(self):
        from shadowlab.detection import DetecteurPositionFenetre

        d = DetecteurPositionFenetre()
        obs = _obs_avec_empreinte({"performance_memory": {"screenX": 120, "screenY": 45}})
        r = d.classer(obs)
        assert r.classification == "humain"

    def test_automation_globals_detecte(self):
        from shadowlab.detection import DetecteurAutomationGlobals

        d = DetecteurAutomationGlobals()
        obs = _obs_avec_empreinte({"automation_globals": {"globales_trouvees": ["__playwright"], "cdc_keys": []}})
        r = d.classer(obs)
        assert any(s.code == "globales_automation" for s in r.signals)

    def test_automation_globals_propre(self):
        from shadowlab.detection import DetecteurAutomationGlobals

        d = DetecteurAutomationGlobals()
        obs = _obs_avec_empreinte(
            {"automation_globals": {"globales_trouvees": [], "cdc_keys": [], "noezia_enumerable": []}}
        )
        r = d.classer(obs)
        assert r.classification == "humain"

    def test_css_media_headless(self):
        from shadowlab.detection import DetecteurCSSMedia

        d = DetecteurCSSMedia()
        obs = _obs_avec_empreinte(
            {"css_media": {"hover_none": True, "hover_hover": False, "pointer_none": True, "pointer_fine": False}}
        )
        r = d.classer(obs)
        assert any(s.code == "hover_none" for s in r.signals)

    def test_css_media_normal(self):
        from shadowlab.detection import DetecteurCSSMedia

        d = DetecteurCSSMedia()
        obs = _obs_avec_empreinte(
            {"css_media": {"hover_none": False, "hover_hover": True, "pointer_none": False, "pointer_fine": True}}
        )
        r = d.classer(obs)
        assert r.classification == "humain"

    def test_prototype_chain_propre(self):
        from shadowlab.detection import DetecteurPrototypeChain

        d = DetecteurPrototypeChain()
        obs = _obs_avec_empreinte(
            {
                "prototype_chain": {
                    "navigator_own": {
                        "webdriver": {"own": False, "prototype": True},
                        "languages": {"own": False, "prototype": True},
                    },
                    "screen_own_width": False,
                    "screen_own_height": False,
                }
            }
        )
        r = d.classer(obs)
        assert r.classification == "humain"

    def test_prototype_chain_fuite(self):
        from shadowlab.detection import DetecteurPrototypeChain

        d = DetecteurPrototypeChain()
        obs = _obs_avec_empreinte(
            {
                "prototype_chain": {
                    "navigator_own": {
                        "webdriver": {"own": True, "prototype": False},
                    },
                }
            }
        )
        r = d.classer(obs)
        assert any(s.code == "nav_own_webdriver" for s in r.signals)

    def test_timing_precision_normal(self):
        from shadowlab.detection import DetecteurTimingPrecision

        d = DetecteurTimingPrecision()
        obs = _obs_avec_empreinte({"timing_precision": {"perf_now_natif": True, "min_delta": 0.1}})
        r = d.classer(obs)
        assert r.classification == "humain"

    def test_registre_41_detecteurs(self):
        from shadowlab.detection import registre

        r = registre()
        assert len(r) == 41
        assert "scroll" in r
        assert "paint-timing" in r
        assert "canvas-consistency" in r
        assert "stack-getter" in r
        assert "raf-timing" in r
        assert "worker-consistency" in r
        assert "connection-dynamic" in r
        assert "proxy-uadata" in r
        assert "enumerable-props" in r
        assert "audio-context" in r
        assert "polices" in r
        assert "math-constants" in r
        assert "domrect" in r
        assert "iframe-consistency" in r
        assert "deep-proxy" in r
        assert "correlation-session" in r


class TestBlocageRessources:
    """Mode rapide : couper images/médias/polices sans les télécharger (gain de vitesse scraping)."""

    def _faux_route(self, resource_type, url="http://127.0.0.1:8770/a"):
        actions = []

        class Req:
            def __init__(s):
                s.url = url
                s.resource_type = resource_type
                s.headers = {}

            def is_navigation_request(s):
                return False

        class Route:
            request = Req()

            def abort(s, *a):
                actions.append(("abort", a))

            def continue_(s, **k):
                actions.append(("continue", k))

        return Route(), actions

    def _moteur(self, **opts):
        from shadowlab.engines.noezia.moteur import DriverNoezia

        d = DriverNoezia(("127.0.0.1", "localhost"), opts)
        d.mesures.details["requetes_bloquees"] = 0
        d.mesures.details["ressources_bloquees"] = 0
        return d

    def test_image_coupee_en_mode_rapide(self):
        d = self._moteur(bloquer_ressources=True)
        route, actions = self._faux_route("image")
        d._filtrer(route)
        assert actions[0][0] == "abort"
        assert d.mesures.details["ressources_bloquees"] == 1

    def test_document_jamais_coupe(self):
        d = self._moteur(bloquer_ressources=True)
        route, actions = self._faux_route("document")
        d._filtrer(route)
        assert actions[0][0] == "continue"
        assert d.mesures.details["ressources_bloquees"] == 0

    def test_option_off_laisse_passer_les_images(self):
        d = self._moteur(bloquer_ressources=False)
        route, actions = self._faux_route("image")
        d._filtrer(route)
        assert actions[0][0] == "continue"


class _Rep:
    def __init__(self, status):
        self.status = status


class _FakePage:
    def __init__(self, resultats):
        self.resultats = list(resultats)
        self.appels = 0

    def goto(self, url, wait_until=None):
        self.appels += 1
        r = self.resultats.pop(0)
        if r == "exc":
            raise RuntimeError("net::ERR_TEST")
        return _Rep(r)


class TestRetryNavigation:
    """Robustesse : retry avec backoff sur échec transitoire (réseau, 429, 5xx), jamais sur 4xx."""

    def _moteur(self, nb_essais, resultats, monkeypatch):
        from shadowlab.engines.noezia.moteur import DriverNoezia

        monkeypatch.setattr("shadowlab.engines.noezia.moteur.time.sleep", lambda *a: None)
        d = DriverNoezia(("127.0.0.1", "localhost"), {"nb_essais": nb_essais})
        d.mesures.details["navigations_retentees"] = 0
        d._page = _FakePage(resultats)
        return d

    def test_retente_exception_puis_reussit(self, monkeypatch):
        d = self._moteur(3, ["exc", "exc", 200], monkeypatch)
        rep = d._naviguer_avec_essais("http://x/", "load")
        assert rep.status == 200
        assert d.mesures.details["navigations_retentees"] == 2
        assert d._page.appels == 3

    def test_epuise_les_essais_leve(self, monkeypatch):
        d = self._moteur(2, ["exc", "exc"], monkeypatch)
        with pytest.raises(RuntimeError):
            d._naviguer_avec_essais("http://x/", "load")

    def test_retente_sur_statut_transitoire(self, monkeypatch):
        d = self._moteur(2, [503, 200], monkeypatch)
        rep = d._naviguer_avec_essais("http://x/", "load")
        assert rep.status == 200
        assert d.mesures.details["navigations_retentees"] == 1

    def test_pas_de_retente_sur_404(self, monkeypatch):
        d = self._moteur(3, [404], monkeypatch)
        rep = d._naviguer_avec_essais("http://x/", "load")
        assert rep.status == 404
        assert d.mesures.details["navigations_retentees"] == 0


class TestProxyNavigateur:
    """Scraping via proxy : en illimité, SHADOWLAB_PROXY route le navigateur (rotation d'IP)."""

    def _moteur(self, hotes):
        from shadowlab.engines.noezia.moteur import DriverNoezia

        return DriverNoezia(hotes, {})

    def test_mode_strict_garde_le_verrou(self):
        d = self._moteur(("127.0.0.1", "localhost"))
        p = d._proxy_navigateur(("127.0.0.1", "localhost"))
        assert p and "127.0.0.1:9" in p["server"]

    def test_illimite_sans_proxy_aucun(self, monkeypatch):
        monkeypatch.delenv("SHADOWLAB_PROXY", raising=False)
        d = self._moteur(("*",))
        assert d._proxy_navigateur(("*",)) is None

    def test_illimite_avec_proxy_env(self, monkeypatch):
        monkeypatch.setenv("SHADOWLAB_PROXY", "http://proxy.example:8080")
        d = self._moteur(("*",))
        assert d._proxy_navigateur(("*",)) == {"server": "http://proxy.example:8080"}


class TestRecolteRepartir:
    """Répartition des URLs en lots pour la récolte parallèle (logique pure)."""

    def test_repartit_equitablement(self):
        from shadowlab.engines.noezia.recolte import repartir

        lots = repartir([f"u{i}" for i in range(5)], 2)
        assert len(lots) == 2
        assert sorted(len(x) for x in lots) == [2, 3]
        assert sum(len(x) for x in lots) == 5

    def test_concurrence_plafonnee_au_nombre_durls(self):
        from shadowlab.engines.noezia.recolte import repartir

        lots = repartir(["a", "b"], 10)
        assert len(lots) == 2 and all(len(x) == 1 for x in lots)

    def test_vide(self):
        from shadowlab.engines.noezia.recolte import repartir

        assert repartir([], 4) == []
