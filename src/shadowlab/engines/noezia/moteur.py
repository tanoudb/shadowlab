"""Orchestrateur du moteur NOEZIA v4.

Moteur anti-détection modulaire construit sur Patchright (Chromium patché).
Chaque session utilise un profil navigateur cohérent, des scripts de furtivité
injectés avant tout JS de la page, et des simulateurs de comportement humain.

⚠️  USAGE RESTREINT — Recherche uniquement.
Ce moteur est conçu pour tester nos propres protections (Arena ShadowLab)
et des domaines que nous contrôlons (voir périmètre D-15, D-16).
"""

from __future__ import annotations

import importlib.metadata
import logging
import random
import time
from pathlib import Path
from typing import Any

from ...perimetre import est_autorisee
from ..base import (
    MANDATAIRE_BLOQUANT,
    Driver,
    FonctionIndisponible,
    MesuresSession,
    ResultatNavigation,
    liste_directe,
)
from .comportement import tempo
from .comportement.clavier import SimulateurClavier
from .comportement.defilement import SimulateurDefilement
from .comportement.souris import SimulateurSouris
from .config import ConfigNoezia
from .defis import pow as defi_pow
from .defis import recaptcha as defi_recaptcha
from .defis import turnstile as defi_turnstile
from .furtivite.patches import injecter as injecter_furtivite
from .profils.generateur import ProfilNavigateur, generer_profil
from .profils.stockage import charger_ou_creer

log = logging.getLogger(__name__)

# Hôtes des widgets CAPTCHA — sous-ressources uniquement, jamais cibles de navigation.
HOTES_CHALLENGES = (
    "challenges.cloudflare.com",
    "www.google.com",
    "www.gstatic.com",
    "www.recaptcha.net",
)


class DriverNoezia(Driver):
    name = "noezia"
    runtime = "navigateur"
    executes_javascript = True
    categorie = "anti_detection"
    options_permises = {
        "headless": bool,
        "profil": str,
        "locale": str,
        "simuler_souris": bool,
        "simuler_frappe": bool,
        "simuler_defilement": bool,
        "eviter_pieges": bool,
        "interaction_post_page": bool,
        "resoudre_defis": bool,
    }

    def __init__(self, hotes_autorises: tuple[str, ...], options: dict[str, Any] | None = None) -> None:
        super().__init__(hotes_autorises, options)
        self._config = self._construire_config(self.options)
        self._profil: ProfilNavigateur | None = None
        self._pw = None
        self._navigateur = None
        self._contexte = None
        self._page = None
        self._souris: SimulateurSouris | None = None
        self._clavier: SimulateurClavier | None = None
        self._defilement: SimulateurDefilement | None = None

    @staticmethod
    def _construire_config(options: dict[str, Any]) -> ConfigNoezia:
        kwargs: dict[str, Any] = {}
        for cle in ("headless", "locale", "interaction_post_page", "eviter_pieges"):
            if cle in options:
                kwargs[cle] = options[cle]
        if "profil" in options:
            kwargs["profil"] = options["profil"]
        return ConfigNoezia(**kwargs)

    @classmethod
    def manque(cls) -> str | None:
        try:
            importlib.metadata.version("patchright")
        except importlib.metadata.PackageNotFoundError:
            return "patchright non installé (uv pip install patchright)"
        return None

    # ── Configuration et versions ──────────────────────────────────────

    def configuration(self) -> dict[str, Any]:
        conf: dict[str, Any] = {
            "browser": "chromium-patchright",
            "headless": self._config.headless,
            "locale": self._config.locale,
            "viewport": f"{self._config.viewport_width}x{self._config.viewport_height}",
            "simuler_souris": self._config.souris.actif,
            "simuler_frappe": self._config.clavier.actif,
            "simuler_defilement": self._config.defilement.actif,
            "furtivite_canvas": self._config.furtivite.canvas_noise,
            "furtivite_webgl": self._config.furtivite.webgl_spoof,
            "furtivite_audio": self._config.furtivite.audio_noise,
            "furtivite_navigateur": self._config.furtivite.navigator_patches,
            "eviter_pieges": self._config.eviter_pieges,
            "interaction_post_page": self._config.interaction_post_page,
        }
        if self._profil:
            conf["profil"] = self._profil.nom
            conf["profil_os"] = self._profil.os
            conf["profil_gpu"] = self._profil.gpu_renderer
            conf["profil_digest"] = self._profil.digest()
        return conf

    def versions(self) -> dict[str, str]:
        versions = {"patchright": importlib.metadata.version("patchright")}
        if self._navigateur is not None:
            versions["chromium"] = self._navigateur.version
        if self._profil:
            versions["profil"] = self._profil.nom
        return versions

    # ── Cycle de vie ───────────────────────────────────────────────────

    def open(self) -> None:
        from patchright.sync_api import sync_playwright

        # Charger ou générer un profil
        if self._config.profil:
            self._profil = charger_ou_creer(self._config.profil)
        else:
            self._profil = generer_profil()
        log.info(
            "Profil NOEZIA : %s (OS=%s, GPU=%s)",
            self._profil.nom,
            self._profil.os,
            self._profil.gpu_renderer[:50],
        )

        # Démarrer Patchright avec verrou réseau
        self._pw = sync_playwright().start()
        tous_hotes = tuple(self.hotes_autorises) + HOTES_CHALLENGES
        verrou = {
            "server": MANDATAIRE_BLOQUANT,
            "bypass": ",".join(liste_directe(tous_hotes)),
        }
        self._navigateur = self._pw.chromium.launch(
            headless=self._config.headless,
            proxy=verrou,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--enable-features=NetworkService,NetworkServiceInProcess",
            ],
            ignore_default_args=[
                "--disable-extensions",
                "--disable-default-apps",
                "--disable-component-extensions-with-background-pages",
                "--enable-automation",
            ],
        )

    def close(self) -> None:
        if self._navigateur is not None:
            self._navigateur.close()
            self._pw.stop()
            self._navigateur = None
            self._pw = None
        self._profil = None

    def start_session(self) -> None:
        self.mesures = MesuresSession()
        self.mesures.details["requetes_bloquees"] = 0
        self.mesures.details["defis_resolus"] = []

        profil = self._profil
        vp = profil.viewport()

        # Contexte navigateur avec paramètres du profil
        self._contexte = self._navigateur.new_context(
            ignore_https_errors=True,
            locale=profil.locale,
            viewport=vp,
            user_agent=profil.user_agent,
            device_scale_factor=profil.device_pixel_ratio,
            timezone_id=profil.timezone,
            extra_http_headers={
                "sec-ch-ua": profil.sec_ch_ua,
                "sec-ch-ua-platform": profil.sec_ch_ua_platform,
                "sec-ch-ua-mobile": "?0",
                "accept-language": profil.accept_language,
            },
        )

        # Injecter les scripts de furtivité
        injecter_furtivite(
            self._contexte,
            profil,
            canvas=self._config.furtivite.canvas_noise,
            webgl=self._config.furtivite.webgl_spoof,
            audio=self._config.furtivite.audio_noise,
            navigateur=self._config.furtivite.navigator_patches,
        )

        # Filtre réseau : périmètre + widgets de challenge
        self._contexte.route("**/*", self._filtrer)

        # Nouvelle page
        self._page = self._contexte.new_page()
        self._page.on("request", lambda _: self._compter("request_count"))
        self._page.on("requestfailed", lambda _: self._compter("error_count"))
        self._page.on("response", self._noter_reponse)
        self._reponse = None

        # Simulateurs de comportement humain
        cfg_s = self._config.souris
        self._souris = SimulateurSouris(
            self._page,
            viewport_w=vp["width"],
            viewport_h=vp["height"],
            a=cfg_s.fitts_a,
            b=cfg_s.fitts_b,
            overshoot_proba=cfg_s.overshoot_proba,
            bruit_vitesse=cfg_s.bruit_vitesse,
        )
        cfg_c = self._config.clavier
        self._clavier = SimulateurClavier(
            self._page,
            wpm_moyen=cfg_c.wpm_moyen,
            wpm_ecart=cfg_c.wpm_ecart,
            proba_erreur=cfg_c.proba_erreur,
            fatigue_par_caractere=cfg_c.fatigue_par_caractere,
        )
        cfg_d = self._config.defilement
        self._defilement = SimulateurDefilement(
            self._page,
            pixels_par_tick=cfg_d.pixels_par_tick,
            ticks_min=cfg_d.ticks_min,
            ticks_max=cfg_d.ticks_max,
        )

    def close_session(self) -> None:
        if self._contexte is None:
            return
        try:
            self._page.goto("about:blank")
        except Exception:
            pass
        self._contexte.close()
        self._contexte = None
        self._page = None
        self._souris = None
        self._clavier = None
        self._defilement = None

    # ── Filtrage réseau ────────────────────────────────────────────────

    def _filtrer(self, route) -> None:
        url = route.request.url
        autorise = est_autorisee(url, self.hotes_autorises)
        challenge = not autorise and est_autorisee(url, HOTES_CHALLENGES)

        # Les widgets de challenge ne naviguent jamais en top-level
        if challenge and route.request.is_navigation_request():
            frame = route.request.frame
            if frame is not None and frame.parent_frame is None:
                self.mesures.details["requetes_bloquees"] += 1
                route.abort("blockedbyclient")
                return

        if autorise or challenge:
            # Nettoyer les en-têtes qui trahissent Headless
            headers = {**route.request.headers}
            for cle in ("user-agent", "sec-ch-ua"):
                val = headers.get(cle, "")
                if "HeadlessChrome" in val:
                    headers[cle] = val.replace("HeadlessChrome", "Chrome")
            route.continue_(headers=headers)
        else:
            self.mesures.details["requetes_bloquees"] += 1
            route.abort("blockedbyclient")

    def _noter_reponse(self, reponse) -> None:
        if reponse.request.is_navigation_request() and reponse.frame == self._page.main_frame:
            self._reponse = reponse

    def _compter(self, champ: str) -> None:
        setattr(self.mesures, champ, getattr(self.mesures, champ) + 1)

    # ── Navigation ─────────────────────────────────────────────────────

    def navigate(self, url: str) -> ResultatNavigation:
        self.verifier(url)
        debut = time.perf_counter()
        reponse = self._page.goto(url, wait_until="load")
        duree = (time.perf_counter() - debut) * 1000
        self.mesures.navigation_time += duree
        status = reponse.status if reponse is not None else None
        if status is not None and status >= 400:
            self.mesures.error_count += 1

        # Interaction post-chargement (comportement humain)
        if self._config.interaction_post_page:
            self._interaction_post_chargement()

        # Détection et résolution des défis de l'Arena
        if self.options.get("resoudre_defis", True):
            self._resoudre_defis()

        return ResultatNavigation(status, self._page.url, duree)

    def _interaction_post_chargement(self) -> None:
        """Simule un humain qui vient d'arriver sur la page."""
        try:
            tempo.pause_apres_navigation()
            if self._config.souris.actif and self._souris:
                self._souris.mouvement_aleatoire()
                tempo.pause_avant_clic()
            if self._config.defilement.actif and self._defilement:
                self._defilement.defiler_bas(random.randint(60, 350))
                time.sleep(random.uniform(0.1, 0.4))
            # Comportement oisif : 2-4 micro-interactions (lecture + exploration)
            if self._config.souris.actif and self._souris:
                n_idle = random.randint(2, 4)
                for _ in range(n_idle):
                    tempo.pause_reflexion()
                    self._souris.mouvement_aleatoire()
                    if random.random() < 0.3 and self._defilement:
                        self._defilement.defiler_bas(random.randint(40, 200))
        except Exception:
            pass

    # ── Résolution des défis Arena ─────────────────────────────────────

    def _resoudre_defis(self) -> None:
        """Détecte et résout les défis de protection de l'Arena."""
        url = self._page.url

        # PoW (proof-of-work)
        if "/lab/defi" in url:
            log.debug("Défi PoW détecté")
            if defi_pow.attendre_resolution(self._page):
                self.mesures.details["defis_resolus"].append("pow")
                self._page.wait_for_load_state("load")
                self._resoudre_defis()  # Cascade : peut y avoir un autre défi
            return

        # Turnstile
        if "/lab/turnstile" in url:
            log.debug("Défi Turnstile détecté")
            tempo.pause_reflexion()
            if defi_turnstile.resoudre(self._page, self._souris):
                self.mesures.details["defis_resolus"].append("turnstile_test")
                try:
                    self._page.wait_for_load_state("load", timeout=10000)
                except Exception:
                    pass
                self._resoudre_defis()
            return

        # reCAPTCHA
        if "/lab/recaptcha" in url:
            log.debug("Défi reCAPTCHA détecté")
            tempo.pause_reflexion()
            if defi_recaptcha.resoudre(self._page, self._souris):
                self.mesures.details["defis_resolus"].append("recaptcha_test")
                try:
                    self._page.wait_for_load_state("load", timeout=10000)
                except Exception:
                    pass
                self._resoudre_defis()
            return

        # CAPTCHA demo
        if "/lab/captcha" in url:
            log.debug("CAPTCHA demo détecté")
            self._resoudre_captcha_demo()
            return

    def _resoudre_captcha_demo(self) -> None:
        """Résout le CAPTCHA demo de l'Arena (addition simple)."""
        try:
            texte = self._page.text_content("label[for='reponse']") or ""
            if "+" not in texte:
                return
            parties = texte.replace("?", "").strip().split("+")
            if len(parties) != 2:
                return
            resultat = int(parties[0].strip()) + int(parties[1].strip())

            tempo.pause_reflexion()
            champ = 'input[name="reponse"]'
            if self._config.souris.actif and self._souris:
                self._souris.deplacer_vers_element(champ)
                tempo.pause_avant_clic()

            if self._config.clavier.actif and self._clavier:
                self._clavier.taper_dans(champ, str(resultat))
            else:
                self._page.fill(champ, str(resultat))

            tempo.pause_reflexion()

            bouton = 'button[type="submit"]'
            if self._config.souris.actif and self._souris:
                self._souris.deplacer_vers_element(bouton)
                tempo.pause_avant_clic()
            self._page.click(bouton)

            try:
                self._page.wait_for_load_state("load", timeout=10000)
            except Exception:
                pass
            self.mesures.details["defis_resolus"].append("captcha_demo")
            self._resoudre_defis()
        except Exception as e:
            log.warning("Échec résolution CAPTCHA demo : %s", e)

    # ── Actions sur la page ────────────────────────────────────────────

    def click(self, selector: str) -> None:
        # Évitement des honeypots
        if self._config.eviter_pieges and not self._est_visible(selector):
            log.debug("Honeypot évité : %s", selector)
            return

        # Mouvement de souris réaliste vers la cible
        if self._config.souris.actif and self._souris:
            self._souris.deplacer_vers_element(selector)
            tempo.pause_avant_clic()

        # Clic avec gestion de navigation
        navigue = self._page.eval_on_selector(
            selector, "e => (e.tagName === 'A' && !!e.href) || (e.type === 'submit' && !!e.form)"
        )
        if navigue:
            with self._page.expect_navigation(wait_until="load"):
                self._page.click(selector)
        else:
            self._page.click(selector)

    def fill(self, selector: str, value: str) -> None:
        if self._config.eviter_pieges and not self._est_visible(selector):
            log.debug("Honeypot évité (fill) : %s", selector)
            return

        if self._config.souris.actif and self._souris:
            self._souris.deplacer_vers_element(selector)
            tempo.pause_avant_clic()

        if self._config.clavier.actif and self._clavier:
            self._clavier.taper_dans(selector, value)
        else:
            self._page.fill(selector, value)

    def select(self, selector: str, value: str) -> None:
        if self._config.souris.actif and self._souris:
            self._souris.deplacer_vers_element(selector)
            tempo.pause_avant_clic()
        self._page.select_option(selector, value)

    def wait_for_element(self, selector: str, timeout_ms: int = 5000) -> str | None:
        try:
            element = self._page.wait_for_selector(selector, state="attached", timeout=timeout_ms)
        except Exception:
            return None
        return element.text_content() if element is not None else None

    def content(self) -> str:
        return self._reponse.text() if self._reponse is not None else ""

    def dom(self) -> str:
        return self._page.content()

    def texts(self, selector: str) -> list[str]:
        return self._page.locator(selector).all_text_contents()

    def attendre_chargement(self) -> None:
        self._page.wait_for_load_state("load")

    def deplacer_souris(self, x: int, y: int) -> None:
        if self._souris:
            self._souris.deplacer_vers(float(x), float(y))
        else:
            self._page.mouse.move(x, y, steps=8)

    def defiler(self, hauteur: int) -> None:
        if self._config.defilement.actif and self._defilement:
            if hauteur > 0:
                self._defilement.defiler_bas(hauteur)
            else:
                self._defilement.defiler_haut(abs(hauteur))
        else:
            self._page.mouse.wheel(0, hauteur)

    def capture_screenshot(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._page.screenshot(path=str(path), full_page=True)
        return path

    def export_trace(self, path: Path) -> Path:
        raise FonctionIndisponible("noezia : pas de trace (interfère avec la furtivité)")

    def collect_metrics(self) -> MesuresSession:
        return self.mesures

    # ── Honeypot : vérification de visibilité ──────────────────────────

    def _est_visible(self, selector: str) -> bool:
        try:
            return bool(
                self._page.eval_on_selector(
                    selector,
                    """e => {
                        const s = window.getComputedStyle(e);
                        const r = e.getBoundingClientRect();
                        return s.display !== 'none'
                            && s.visibility !== 'hidden'
                            && parseFloat(s.opacity) > 0.01
                            && r.width > 1
                            && r.height > 1;
                    }""",
                )
            )
        except Exception:
            return True

    # ── Scénario natif (le moteur gère lui-même la cascade de défis) ──

    def scenario_natif(self, nom: str, base: str, jeton: str) -> dict[str, Any] | None:
        return None
