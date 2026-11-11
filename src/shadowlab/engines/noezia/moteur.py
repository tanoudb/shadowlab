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
import os
import platform
import random
import time
from pathlib import Path
from typing import Any

from ...config import RACINE
from ...perimetre import est_autorisee
from ..base import (
    Driver,
    FonctionIndisponible,
    MesuresSession,
    ResultatNavigation,
    proxy_verrou,
)
from . import extraction
from .analyseur import Analyseur
from .comportement import humain, tempo
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


def _detecter_hote_os() -> str:
    """OS de la machine qui exécute le moteur (pour la cohérence GPU réel ↔ profil)."""
    return {"Darwin": "macos", "Windows": "windows", "Linux": "linux"}.get(platform.system(), "linux")


_HOTE_OS = _detecter_hote_os()

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
        "bloquer_ressources": bool,
        "nb_essais": int,
    }

    # Types de ressources coupées en mode rapide (gros gain de vitesse sur un vrai site chargé).
    RESSOURCES_LOURDES = frozenset({"image", "media", "font"})
    # Statuts transitoires qui justifient une nouvelle tentative (jamais 4xx client sauf 429).
    STATUTS_TRANSITOIRES = frozenset({429, 500, 502, 503, 504})

    def __init__(self, hotes_autorises: tuple[str, ...], options: dict[str, Any] | None = None) -> None:
        super().__init__(hotes_autorises, options)
        self._config = self._construire_config(self.options)
        self._bloquer_ressources = bool(self.options.get("bloquer_ressources", False))
        self._nb_essais = max(1, int(self.options.get("nb_essais", 1)))
        self._signatures = extraction.Signatures(RACINE / "outputs" / "signatures_adaptatives.json")
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
            "bloquer_ressources": self._bloquer_ressources,
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
            # Profil cohérent avec l'OS de l'hôte : le GPU réel (Metal sur
            # Apple Silicon) correspond alors au renderer WebGL annoncé.
            self._profil = generer_profil(os=_HOTE_OS)
        log.info(
            "Profil NOEZIA : %s (OS=%s, GPU=%s)",
            self._profil.nom,
            self._profil.os,
            self._profil.gpu_renderer[:50],
        )

        # Démarrer Patchright avec verrou réseau
        self._pw = sync_playwright().start()
        tous_hotes = tuple(self.hotes_autorises) + HOTES_CHALLENGES
        verrou = self._proxy_navigateur(tous_hotes)
        args = [
            "--disable-blink-features=AutomationControlled",
            "--enable-features=NetworkService,NetworkServiceInProcess",
        ]
        # ── GPU / backend graphique : cohérence avec le profil déclaré ──
        if self._profil.os == "macos" and _HOTE_OS == "macos":
            # macOS + profil macOS : Metal réel, cohérent avec renderer Apple.
            args += ["--use-gl=angle", "--use-angle=metal", "--ignore-gpu-blocklist"]
        elif _HOTE_OS == "linux":
            # Linux serveur : /dev/shm souvent petit (Docker), Chrome crashe sans ceci.
            args += ["--disable-dev-shm-usage"]
            # Pas de --disable-gpu : on laisse Chromium utiliser le GPU si disponible
            # (Mesa/NVIDIA natif), sinon il bascule sur SwiftShader automatiquement.
            # Notre webgl.js détecte SwiftShader et masque ses paramètres distinctifs.

        self._navigateur = self._pw.chromium.launch(
            headless=self._config.headless,
            proxy=verrou,
            args=args,
            ignore_default_args=[
                "--disable-extensions",
                "--disable-default-apps",
                "--disable-component-extensions-with-background-pages",
                "--enable-automation",
                # Retirés aussi par rebrowser-patches : ces flags sont absents d'un
                # Chrome normal et constituent des signaux d'automatisation.
                "--disable-popup-blocking",
                "--disable-ipc-flooding-protection",
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
        self.mesures.details["ressources_bloquees"] = 0
        self.mesures.details["navigations_retentees"] = 0
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
                "sec-ch-ua-full-version-list": profil.sec_ch_ua.replace(
                    f'v="{profil.chrome_major}"',
                    f'v="{profil.chrome_full}"',
                ),
                "sec-ch-ua-model": '""',
                "sec-ch-ua-arch": '"x86"' if profil.os != "macos" else '"arm"',
                "sec-ch-ua-bitness": '"64"',
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
            proba_erreur=cfg_c.proba_erreur,
            fatigue_par_caractere=cfg_c.fatigue_par_caractere,
        )
        cfg_d = self._config.defilement
        self._defilement = SimulateurDefilement(
            self._page,
            mode=cfg_d.mode,
            pixels_par_tick=cfg_d.pixels_par_tick,
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
            # Mode rapide : couper les ressources lourdes (images, médias, polices) sans les télécharger.
            if self._bloquer_ressources and route.request.resource_type in self.RESSOURCES_LOURDES:
                self.mesures.details["ressources_bloquees"] += 1
                route.abort()
                return
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

    def _proxy_navigateur(self, tous_hotes: tuple[str, ...]) -> dict[str, str] | None:
        """Proxy de lancement du navigateur.

        - Mode strict : verrou réseau (mandataire bloquant, tout hors liste échoue).
        - Mode illimité : un proxy utilisateur (`SHADOWLAB_PROXY`, pour scraper via proxy / rotation
          d'IP) s'il est défini, sinon aucun proxy. Le proxy vient de l'environnement, jamais du code.
        """
        verrou = proxy_verrou(tous_hotes)
        if verrou is None:
            proxy_user = os.environ.get("SHADOWLAB_PROXY")
            if proxy_user:
                return {"server": proxy_user}
        return verrou

    @staticmethod
    def _backoff(essai: int) -> float:
        """Attente exponentielle plafonnée, avec gigue (évite les rafales synchronisées)."""
        return min(0.5 * (2**essai), 8.0) + random.uniform(0, 0.3)

    def _naviguer_avec_essais(self, url: str, attente: str):
        """goto avec nouvelles tentatives sur échec transitoire (exception réseau, 429, 5xx)."""
        derniere_exc: Exception | None = None
        for essai in range(self._nb_essais):
            try:
                reponse = self._page.goto(url, wait_until=attente)
            except Exception as exc:  # noqa: BLE001 — erreurs réseau Playwright : on retente
                derniere_exc = exc
                if essai + 1 >= self._nb_essais:
                    raise
                self.mesures.details["navigations_retentees"] += 1
                time.sleep(self._backoff(essai))
                continue
            status = reponse.status if reponse is not None else None
            if status in self.STATUTS_TRANSITOIRES and essai + 1 < self._nb_essais:
                self.mesures.details["navigations_retentees"] += 1
                time.sleep(self._backoff(essai))
                continue
            return reponse
        raise derniere_exc  # pragma: no cover

    def navigate(self, url: str) -> ResultatNavigation:
        self.verifier(url)
        debut = time.perf_counter()
        # Mode rapide : DOM prêt suffit (on n'attend pas les ressources, déjà coupées).
        attente = "domcontentloaded" if self._bloquer_ressources else "load"
        reponse = self._naviguer_avec_essais(url, attente)
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
                self._defilement.defiler_bas()
                time.sleep(humain.pause_reflexion_ms() / 1000.0)
            # Comportement oisif : 2-4 micro-interactions (lecture + exploration)
            if self._config.souris.actif and self._souris:
                n_idle = random.randint(2, 4)
                for _ in range(n_idle):
                    tempo.pause_reflexion()
                    self._souris.mouvement_aleatoire()
                    if random.random() < 0.3 and self._defilement:
                        self._defilement.defiler_bas()
        except Exception:
            pass

    def _interaction_post_clic_navigation(self) -> None:
        """Comportement après un clic qui déclenche une navigation.

        Plus léger que _interaction_post_chargement (aller()) : l'humain
        connaît déjà le site, il scanne la nouvelle page rapidement
        avant de continuer. Injecte assez de variabilité dans les délais
        et mouvements souris pour tromper le détecteur d'entropie.
        """
        try:
            tempo.pause_apres_navigation()
            if self._config.souris.actif and self._souris:
                self._souris.mouvement_aleatoire()
                # 1-2 micro-interactions de scan
                n_scan = random.randint(1, 2)
                for _ in range(n_scan):
                    tempo.pause_reflexion()
                    self._souris.mouvement_aleatoire()
                if self._config.defilement.actif and self._defilement and random.random() < 0.4:
                    self._defilement.defiler_bas()
                tempo.hesitation(proba=0.20)
        except Exception:
            pass

    # ── Résolution des défis Arena ─────────────────────────────────────

    def _resoudre_defis(self) -> None:
        """Détecte et résout les défis de protection de l'Arena.

        Détection par URL (redirection vers /lab/defi, /lab/turnstile…) ET par attribut
        ``data-arena`` sur le body (le gardien sert parfois le défi inline, sans redirection).
        """
        url = self._page.url
        try:
            arena = self._page.evaluate("document.body?.dataset?.arena || ''")
        except Exception:
            arena = ""
        if arena:
            log.debug("_resoudre_defis: url=%s, arena=%s", url[:80], arena)

        # PoW (proof-of-work)
        if "/lab/defi" in url or arena == "defi":
            log.debug("Défi PoW détecté (url=%s, arena=%s)", "/lab/defi" in url, arena)
            if defi_pow.attendre_resolution(self._page):
                self.mesures.details["defis_resolus"].append("pow")
                self._page.wait_for_load_state("load")
                self._resoudre_defis()
            return

        # Turnstile
        if "/lab/turnstile" in url or arena == "turnstile":
            log.debug("Défi Turnstile détecté (url=%s, arena=%s)", "/lab/turnstile" in url, arena)
            tempo.pause_reflexion()
            if defi_turnstile.resoudre(self._page, self._souris):
                self.mesures.details["defis_resolus"].append("turnstile_test")
                try:
                    self._page.wait_for_load_state("load", timeout=10000)
                except Exception:
                    pass
                self._resoudre_defis()
            return

        # reCAPTCHA (défi v2 de l'Arena — surtout pas la démo /lab/recaptcha-v3, qui n'est pas un défi)
        if ("/lab/recaptcha" in url and "/lab/recaptcha-v3" not in url) or arena == "recaptcha":
            log.debug("Défi reCAPTCHA détecté (url=%s, arena=%s)", "/lab/recaptcha" in url, arena)
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
        if "/lab/captcha" in url or arena == "captcha":
            log.debug("CAPTCHA demo détecté (url=%s, arena=%s)", "/lab/captcha" in url, arena)
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

        # Pause humaine inter-actions (probabilité croissante si clics rapprochés)
        if self._config.souris.actif and self._souris:
            ecart = time.monotonic() - self._souris._derniere_action
            if ecart < 1.0 and random.random() < 0.60:
                self._souris.pause_humaine()
            elif ecart < 2.0 and random.random() < 0.30:
                self._souris.pause_humaine()

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
            # Comportement post-navigation (lecture, mouvement oisif)
            if self._config.interaction_post_page:
                self._interaction_post_clic_navigation()
            # La page cible peut imposer ses propres défis (ex. /lab/espace après login)
            if self.options.get("resoudre_defis", True):
                self._resoudre_defis()
        else:
            self._page.click(selector)

    def fill(self, selector: str, value: str) -> None:
        if self._config.eviter_pieges and not self._est_visible(selector):
            log.debug("Honeypot évité (fill) : %s", selector)
            return

        if self._config.souris.actif and self._souris:
            ecart = time.monotonic() - self._souris._derniere_action
            if ecart < 2.0 and random.random() < 0.25:
                self._souris.pause_humaine()
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

    def analyser(self) -> Analyseur:
        """Analyseur rapide (parsel) sur le HTML de la page courante, partageant la mémoire de
        signatures du moteur. Le moteur récolte (furtif), l'analyseur extrait (css/xpath/adaptatif)."""
        return Analyseur(self._page.content(), url=self._page.url, signatures=self._signatures)

    def extraire_adaptatif(self, selecteur: str, cle: str) -> str | None:
        """Extrait le texte d'un élément. Si le sélecteur a cassé (site changé), relocalise
        l'élément par ressemblance à la signature mémorisée lors d'une extraction réussie.

        `cle` est un nom logique stable (ex. "prix", "titre") sous lequel la signature est rangée.
        """
        domaine = extraction.domaine_de(self._page.url)
        try:
            feats = self._page.eval_on_selector(selecteur, extraction.CARAC_UN)
        except Exception:  # noqa: BLE001 — sélecteur introuvable : on tentera la relocalisation
            feats = None
        if feats:
            self._signatures.enregistrer(domaine, cle, feats)
            return feats.get("texte")
        # Sélecteur cassé : relocalisation par signature.
        sig = self._signatures.charger(domaine, cle)
        if not sig:
            return None
        try:
            candidats = self._page.eval_on_selector_all(sig["tag"], extraction.CARAC_TOUS)
        except Exception:  # noqa: BLE001
            return None
        meilleur, sc = extraction.meilleur_candidat(sig, candidats)
        if meilleur and sc >= extraction.SEUIL_RELOCALISATION:
            self.mesures.details["relocalisations"] = self.mesures.details.get("relocalisations", 0) + 1
            return meilleur.get("texte")
        return None

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
