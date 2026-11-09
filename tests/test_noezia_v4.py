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
        assert 0.05 < duree < 6.0


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
        assert len(scripts) == 5  # profil + navigateur + canvas + webgl + audio

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
        assert len(scripts) == 3  # profil + navigateur + webgl


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
