"""Détecteurs du laboratoire : chacun classe une session à partir des observations reçues.

Classement : `automatise`, `humain` ou `indetermine` (le détecteur n'a pas de quoi trancher).
Chaque détecteur rend aussi ses raisons (`signals`) : une liste de signaux avec leur poids.

Ces détecteurs sont des repères pour comparer les moteurs entre eux dans ce laboratoire. Un score ici ne
dit rien de la probabilité d'être repéré par un service externe, qui observe bien d'autres choses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from importlib.metadata import entry_points
from typing import Any, Protocol

SEUIL_AUTOMATISE = 1.0
SEUIL_RYTHME_PAR_S = 4.0
SEUIL_DUREE_PAGE_MS = 500

CHEMINS_TECHNIQUES = ("/lab/collecte", "/lab/static", "/lab/verdict", "/lab/defi", "/lab/captcha")
MARQUEURS_UA_OUTILS = re.compile(r"python|curl|httpx|requests|aiohttp|wget|go-http|java/|okhttp", re.I)


@dataclass
class Signal:
    code: str
    description: str
    poids: float

    def en_dict(self) -> dict[str, Any]:
        return {"code": self.code, "description": self.description, "poids": self.poids}


@dataclass
class Classement:
    detector_name: str
    detector_version: str
    classification: str
    # Score HEURISTIQUE NON CALIBRÉ (somme de poids plafonnée, ou constante 0.6/0.9).
    # Ce n'est pas une probabilité et il n'est utilisé dans aucun taux ni intervalle
    # (voir analytics : seuls `classification` compte). Ne pas l'interpréter comme une
    # confiance calibrée tant qu'aucune calibration empirique n'a été faite (défaut #2).
    confidence: float
    signals: list[Signal] = field(default_factory=list)


@dataclass
class Observations:
    """Tout ce que le site a reçu pour une session."""

    http: list[dict[str, Any]]
    js: list[dict[str, Any]]
    attend_js: bool = True  # faux pour un scénario sans page HTML (API JSON)
    tls: dict[str, Any] | None = None  # empreinte relevée par le frontal de l'Arena ; absente hors Arena
    page_remplacee: bool = False  # une protection a servi sa page à la place du contenu : pas d'observateur

    @property
    def empreinte_js(self) -> dict[str, Any] | None:
        for obs in self.js:
            if obs["kind"] == "empreinte":
                return obs["payload"]
        return None

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Requêtes de pages (hors échanges techniques et fichiers statiques)."""
        return [o for o in self.http if not o["path"].startswith(CHEMINS_TECHNIQUES)]

    @property
    def ressources(self) -> list[dict[str, Any]]:
        """Fichiers statiques réclamés : un navigateur les charge, un client HTTP non."""
        return [o for o in self.http if o["path"].startswith("/lab/static")]


class Detecteur(Protocol):
    name: str
    version: str

    def classer(self, obs: Observations) -> Classement: ...


def _entetes(obs_http: dict[str, Any]) -> dict[str, str]:
    return {nom.lower(): valeur for nom, valeur in obs_http["headers"]}


def _verdict(nom: str, version: str, signaux: list[Signal], appui_humain: float = 0.6) -> Classement:
    # `confidence` ici est un score heuristique non calibré (somme de poids plafonnée,
    # ou `appui_humain` constant). Il sert à trier/afficher, jamais à calculer un taux.
    score = sum(s.poids for s in signaux)
    if score >= SEUIL_AUTOMATISE:
        return Classement(nom, version, "automatise", min(score, 1.0), signaux)
    if score <= 0:
        return Classement(nom, version, "humain", appui_humain, signaux)
    return Classement(nom, version, "indetermine", score, signaux)


def _indetermine(nom: str, version: str, code: str, description: str) -> Classement:
    return Classement(nom, version, "indetermine", 0.0, [Signal(code, description, 0.0)])


class DetecteurBotD:
    """Verdict de BotD (FingerprintJS, MIT), calculé dans la page et renvoyé au serveur."""

    name = "botd"
    version = "2.0.0"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        empreinte = obs.empreinte_js
        if empreinte is None:
            return _indetermine(self.name, self.version, "non_execute", "BotD non exécuté (pas de JavaScript)")
        resultat = empreinte.get("botd") or {}
        if "erreur" in resultat:
            return _indetermine(self.name, self.version, "erreur", f"erreur BotD : {resultat['erreur']}")
        if resultat.get("bot") is True:
            signal = Signal("botd_bot", f"BotD : {resultat.get('botKind', 'inconnu')}", 1.0)
            return Classement(self.name, self.version, "automatise", 0.9, [signal])
        if resultat.get("bot") is False:
            return Classement(self.name, self.version, "humain", 0.6, [Signal("botd_humain", "BotD : aucun bot", 0)])
        return _indetermine(self.name, self.version, "reponse_vide", "réponse BotD illisible")


class DetecteurReglesHttp:
    """Règles sur les en-têtes HTTP des requêtes de pages, sans JavaScript."""

    name = "regles-http"
    version = "2"

    def classer(self, obs: Observations) -> Classement:
        documents = obs.documents
        if not documents:
            return _indetermine(self.name, self.version, "aucune_requete", "aucune requête reçue")
        e = _entetes(documents[0])
        ua = e.get("user-agent", "")
        signaux: list[Signal] = []
        if not ua:
            signaux.append(Signal("ua_absent", "en-tête User-Agent absent", 1.0))
        elif MARQUEURS_UA_OUTILS.search(ua):
            signaux.append(Signal("ua_outil", f"User-Agent d'outil : {ua[:80]}", 1.0))
        if "headlesschrome" in ua.lower():
            signaux.append(Signal("ua_headless", "User-Agent HeadlessChrome", 1.0))
        if "accept-language" not in e:
            signaux.append(Signal("langue_absente", "en-tête Accept-Language absent", 0.5))
        navigateur_annonce = "mozilla/" in ua.lower()
        if navigateur_annonce and not any(k.startswith("sec-fetch-") for k in e):
            signaux.append(Signal("sec_fetch_absent", "navigateur annoncé sans en-têtes Sec-Fetch-*", 0.5))
        if navigateur_annonce and e.get("accept", "*/*") == "*/*":
            signaux.append(Signal("accept_generique", "navigation de page avec Accept: */*", 0.5))
        if "chrome/" in ua.lower() and "sec-ch-ua" not in e:
            signaux.append(Signal("client_hints_absents", "Chrome annoncé sans Sec-CH-UA", 0.25))
        if navigateur_annonce and e.get("upgrade", "").lower() == "h2c":
            signaux.append(Signal("h2c", "passage en HTTP/2 en clair (h2c) demandé : aucun navigateur ne le fait", 1.0))
        ordre = [nom.lower() for nom, _ in documents[0]["headers"]]
        if navigateur_annonce and documents[0]["http_version"] == "1.1" and ordre and ordre[0] != "host":
            signaux.append(Signal("host_tardif", "en HTTP/1.1, Host n'est pas le premier en-tête", 0.5))
        if e.get("sec-fetch-site") == "none" and "referer" in e:
            signaux.append(Signal("referent_incoherent", "Sec-Fetch-Site « none » avec un Referer", 0.5))
        cookies = [o for o in documents[1:] if not o["cookies"]]
        if len(documents) > 1 and len(cookies) == len(documents) - 1:
            signaux.append(Signal("cookies_ignores", "cookies de session jamais renvoyés", 0.5))
        return _verdict(self.name, self.version, signaux)


class DetecteurReglesJs:
    """Règles sur les propriétés exposées au JavaScript de la page."""

    name = "regles-js"
    version = "2"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None and obs.page_remplacee:
            return _indetermine(self.name, self.version, "page_remplacee", "observateur non servi : page de protection")
        if p is None:
            # Un visiteur réel sans JavaScript existe : c'est une limite connue de cette règle.
            signal = Signal("sans_javascript", "aucune observation JavaScript reçue", 1.0)
            return Classement(self.name, self.version, "automatise", 0.7, [signal])
        nav = p.get("navigateur", {})
        signaux: list[Signal] = []
        if nav.get("webdriver") is True:
            signaux.append(Signal("webdriver", "navigator.webdriver = true", 1.0))
        if "HeadlessChrome" in nav.get("userAgent", ""):
            signaux.append(Signal("ua_headless", "navigator.userAgent contient HeadlessChrome", 1.0))
        marques = [b.get("brand", "") for b in (nav.get("userAgentData") or {}).get("brands", [])]
        if any("Headless" in m for m in marques):
            signaux.append(Signal("marque_headless", "userAgentData annonce HeadlessChrome", 1.0))
        if not nav.get("languages"):
            signaux.append(Signal("langues_vides", "navigator.languages vide", 0.5))
        fenetre = p.get("fenetre", {})
        if fenetre.get("outerWidth") == 0 or fenetre.get("outerHeight") == 0:
            signaux.append(Signal("fenetre_nulle", "fenêtre extérieure de taille nulle", 0.5))
        if "Chrome/" in nav.get("userAgent", "") and nav.get("plugins", 0) == 0:
            signaux.append(Signal("plugins_vides", "Chrome sans aucun plugin déclaré", 0.25))
        permissions = p.get("permissions", {})
        if permissions.get("notification") == "denied" and permissions.get("query") == "prompt":
            signaux.append(Signal("permissions_incoherentes", "Notification refusée mais requête « prompt »", 0.5))
        renderer = (p.get("webgl") or {}).get("renderer") or ""
        if "swiftshader" in renderer.lower():
            signaux.append(Signal("webgl_logiciel", f"rendu WebGL logiciel : {renderer[:60]}", 0.25))
        canvas = p.get("canvas") or ""
        if isinstance(canvas, str) and canvas.startswith("erreur"):
            signaux.append(Signal("canvas_erreur", f"empreinte canvas en erreur : {canvas[:60]}", 0.5))
        auto = p.get("automation") or {}
        if auto.get("cdc"):
            signaux.append(Signal("cdc_global", f"globales ChromeDriver : {auto['cdc']}", 1.0))
        if auto.get("playwright"):
            signaux.append(Signal("playwright_global", "__playwright détecté dans window", 1.0))
        if auto.get("selenium"):
            signaux.append(Signal("selenium_global", "globales Selenium détectées", 1.0))
        if auto.get("webdriver_patched") is True:
            signaux.append(Signal("webdriver_patche", "navigator.webdriver redéfini (getter non natif)", 0.5))
        if auto.get("callPhantom"):
            signaux.append(Signal("phantom_global", "callPhantom ou _phantom détecté", 1.0))
        return _verdict(self.name, self.version, signaux)


class DetecteurCoherence:
    """Cohérence entre ce que disent les en-têtes HTTP et ce que montre le JavaScript."""

    name = "coherence"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        documents = obs.documents
        if p is None or not documents:
            return _indetermine(self.name, self.version, "incomplet", "observations HTTP ou JavaScript manquantes")
        e = _entetes(documents[0])
        nav = p.get("navigateur", {})
        signaux: list[Signal] = []
        if e.get("user-agent", "") != nav.get("userAgent", ""):
            signaux.append(Signal("ua_divergent", "User-Agent HTTP différent de navigator.userAgent", 1.0))
        langue_http = e.get("accept-language", "").split(",")[0].split(";")[0].strip().lower()
        langue_js = (nav.get("language") or "").lower()
        if langue_http and langue_js and langue_http != langue_js:
            signaux.append(Signal("langue_divergente", f"langue HTTP {langue_http} ≠ JS {langue_js}", 0.5))
        plateforme_http = e.get("sec-ch-ua-platform", "").strip('"').lower()
        plateforme_js = ((nav.get("userAgentData") or {}).get("platform") or "").lower()
        if plateforme_http and plateforme_js and plateforme_http != plateforme_js:
            signaux.append(Signal("plateforme_divergente", "Sec-CH-UA-Platform ≠ userAgentData.platform", 1.0))
        return _verdict(self.name, self.version, signaux)


class DetecteurTls:
    """Cohérence entre le ClientHello TLS et le navigateur annoncé (règles de structure, sans liste d'empreintes)."""

    name = "tls"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        t = obs.tls
        if t is None:
            return _indetermine(self.name, self.version, "sans_tls", "session hors Arena : TLS non observé")
        documents = obs.documents
        ua = _entetes(documents[0]).get("user-agent", "").lower() if documents else ""
        details = t
        grease = details.get("grease")
        alpn = details.get("alpn") or []
        chrome = "chrome/" in ua
        firefox = "firefox/" in ua
        signaux: list[Signal] = []
        if chrome and not grease:
            signaux.append(
                Signal("chrome_sans_grease", "Chrome annoncé, mais aucune valeur GREASE dans le ClientHello", 1.0)
            )
        if firefox and grease:
            signaux.append(
                Signal("firefox_avec_grease", "Firefox annoncé, mais des valeurs GREASE que Firefox n'envoie pas", 1.0)
            )
        if (chrome or firefox) and "h2" not in alpn:
            signaux.append(Signal("navigateur_sans_h2", f"navigateur annoncé sans HTTP/2 dans l'ALPN : {alpn}", 1.0))
        if not grease and "h2" not in alpn and not (chrome or firefox):
            signaux.append(Signal("pile_non_navigateur", "ni GREASE ni HTTP/2 proposé : pile TLS de bibliothèque", 1.0))
        return _verdict(self.name, self.version, signaux)


class DetecteurComportement:
    """Règles expérimentales sur le déroulement de la session. Encore jamais calibrées sur des sessions humaines."""

    name = "comportement"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        documents = obs.documents
        if not documents:
            return _indetermine(self.name, self.version, "aucune_requete", "aucune requête reçue")
        signaux: list[Signal] = []
        if not obs.ressources:
            signaux.append(Signal("sans_ressources", "aucun fichier CSS ou JavaScript réclamé", 0.5))
        rythme = _requetes_par_seconde(documents)
        if rythme is not None and rythme > SEUIL_RYTHME_PAR_S:
            signaux.append(Signal("rythme_soutenu", f"{rythme:.1f} pages par seconde", 0.5))
        releves = [o["payload"] for o in obs.js if o["kind"] == "comportement"]
        if releves:
            evenements = [r.get("evenements", {}) for r in releves]
            interactions = sum(sum(e.values()) for e in evenements)
            duree = sum(r.get("duree_page_ms") or 0 for r in releves)
            if interactions == 0:
                signaux.append(Signal("aucune_interaction", "aucun mouvement, clic, touche ni défilement", 0.5))
            elif sum(e.get("mousemove", 0) for e in evenements) == 0 and sum(e.get("click", 0) for e in evenements) > 0:
                signaux.append(Signal("clic_sans_souris", "des clics sans aucun mouvement de souris", 0.5))
            if duree and duree < SEUIL_DUREE_PAGE_MS * len(releves):
                signaux.append(Signal("pages_eclair", f"moins de {SEUIL_DUREE_PAGE_MS} ms par page en moyenne", 0.5))
        elif obs.empreinte_js is None:
            return _indetermine(self.name, self.version, "sans_releve", "aucun relevé de comportement reçu")
        return _verdict(self.name, self.version, signaux)


class DetecteurPrototypes:
    """Détection d'altération des chaînes de prototypes et de Function.prototype.toString.

    Tout moteur qui modifie toString pour masquer ses overrides doit patcher
    toString elle-même. Si toString.toString() ne renvoie pas [native code] de la
    bonne manière, ou si les descripteurs de propriété sont incohérents, c'est un signal.
    """

    name = "prototypes"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        proto = p.get("prototypes") or {}
        signaux: list[Signal] = []

        # toString de toString elle-même
        ts_self = proto.get("toString_self", "")
        if ts_self and "native code" not in str(ts_self):
            signaux.append(
                Signal(
                    "toString_patche",
                    "Function.prototype.toString ne renvoie pas [native code] pour elle-même",
                    1.0,
                )
            )

        # Canvas toDataURL : si la source n'a pas [native code], le canvas est patché
        if proto.get("canvas_natif") is False:
            signaux.append(Signal("canvas_patche", "HTMLCanvasElement.toDataURL patché (toString ≠ native code)", 0.75))

        # WebGL getParameter patché
        if proto.get("webgl_getParameter_natif") is False:
            signaux.append(Signal("webgl_patche", "WebGLRenderingContext.getParameter patché", 0.75))

        # navigator.plugins défini sur l'instance plutôt que le prototype
        if proto.get("plugins_propre") is True and proto.get("plugins_getter_natif") is False:
            signaux.append(Signal("plugins_patche", "navigator.plugins a un getter non natif", 0.5))

        # hardwareConcurrency sur l'instance plutôt que le prototype
        if proto.get("hwc_instance") is True:
            signaux.append(Signal("hwc_instance", "hardwareConcurrency défini sur navigator (pas le prototype)", 0.5))

        return _verdict(self.name, self.version, signaux)


class DetecteurCoherenceProfonde:
    """Vérifications de cohérence que les patchs simples ne couvrent pas.

    - screen.availWidth doit être ≤ screen.width
    - outerWidth doit être ≥ innerWidth (barre de titre, bordures)
    - devicePixelRatio doit correspondre au type d'écran
    - hardwareConcurrency doit être une puissance de 2 ≤ 128
    - deviceMemory doit être dans {0.25, 0.5, 1, 2, 4, 8}
    """

    name = "coherence-profonde"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        signaux: list[Signal] = []

        ecran = p.get("ecran") or {}
        fenetre = p.get("fenetre") or {}
        nav = p.get("navigateur") or {}

        # screen.availWidth > screen.width → impossible
        sw, aw = ecran.get("width", 0), ecran.get("availWidth", 0)
        sh, ah = ecran.get("height", 0), ecran.get("availHeight", 0)
        if aw and sw and aw > sw:
            signaux.append(Signal("avail_gt_screen", f"availWidth {aw} > width {sw}", 0.75))
        if ah and sh and ah > sh:
            signaux.append(Signal("avail_gt_screen_h", f"availHeight {ah} > height {sh}", 0.75))

        # outerWidth/outerHeight : un vrai navigateur a toujours outer ≥ inner (cadre + barre d'adresse)
        ow = fenetre.get("outerWidth", 0)
        iw = fenetre.get("innerWidth", 0)
        oh = fenetre.get("outerHeight", 0)
        ih = fenetre.get("innerHeight", 0)
        if ow and iw and ow < iw:
            signaux.append(Signal("outer_lt_inner_w", f"outerWidth {ow} < innerWidth {iw}", 0.5))
        if oh and ih and oh < ih:
            signaux.append(Signal("outer_lt_inner_h", f"outerHeight {oh} < innerHeight {ih}", 0.5))
        # En headless : outerWidth == innerWidth (pas de chrome de fenêtre)
        if ow and iw and ow == iw and oh and ih and oh == ih:
            signaux.append(
                Signal(
                    "outer_eq_inner",
                    "outer == inner (pas de chrome de fenêtre = probable headless)",
                    0.5,
                )
            )

        # hardwareConcurrency : doit être puissance de 2 entre 1 et 128
        hwc = nav.get("hardwareConcurrency")
        if isinstance(hwc, int) and hwc > 0:
            if hwc & (hwc - 1) != 0:
                signaux.append(
                    Signal(
                        "hwc_non_puissance2",
                        f"hardwareConcurrency={hwc} n'est pas une puissance de 2",
                        0.25,
                    )
                )
            if hwc > 128:
                signaux.append(Signal("hwc_excessif", f"hardwareConcurrency={hwc} > 128", 0.5))

        # deviceMemory : doit être dans {0.25, 0.5, 1, 2, 4, 8}
        dm = nav.get("deviceMemory")
        if isinstance(dm, (int, float)) and dm not in (0.25, 0.5, 1, 2, 4, 8, "unknown"):
            signaux.append(Signal("device_memory_invalide", f"deviceMemory={dm} invalide", 0.5))

        # colorDepth : doit être 24 ou 30 (HDR)
        cd = ecran.get("colorDepth")
        if isinstance(cd, int) and cd not in (24, 30, 32):
            signaux.append(Signal("color_depth_suspect", f"colorDepth={cd} inattendu", 0.25))

        # DPR cohérence grossière : DPR > 3 est suspect sur desktop
        dpr = ecran.get("devicePixelRatio")
        if isinstance(dpr, (int, float)) and dpr > 3.0 and nav.get("maxTouchPoints", 0) == 0:
            signaux.append(Signal("dpr_excessif", f"DPR={dpr} > 3 sur un appareil sans tactile", 0.5))

        return _verdict(self.name, self.version, signaux)


class DetecteurEntropieInteraction:
    """Analyse l'entropie temporelle des interactions souris.

    Un humain a une distribution de délais entre mouvements souris qui suit
    approximativement une loi log-normale. Un robot a des délais trop réguliers
    (faible écart-type) ou trop uniformément distribués.
    """

    name = "entropie-interaction"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")

        releves = [o["payload"] for o in obs.js if o["kind"] == "comportement"]
        if not releves:
            return _indetermine(self.name, self.version, "sans_releve", "aucun relevé")

        signaux: list[Signal] = []
        for r in releves:
            delais = r.get("delais_souris_ms") or []
            if len(delais) < 10:
                continue

            import statistics

            moyenne = statistics.mean(delais)
            ecart = statistics.stdev(delais) if len(delais) > 1 else 0

            # Coefficient de variation trop faible → timing trop régulier
            if moyenne > 0:
                cv = ecart / moyenne
                if cv < 0.15:
                    signaux.append(
                        Signal("timing_trop_regulier", f"CV des délais souris = {cv:.2f} (< 0.15 = machine)", 0.75)
                    )

            # Vérifier si les délais sont quantifiés (multiples d'une même valeur)
            delais_arrondis = [round(d, 1) for d in delais]
            uniques = len(set(delais_arrondis))
            ratio_unique = uniques / len(delais_arrondis)
            if ratio_unique < 0.3 and len(delais) > 15:
                signaux.append(
                    Signal("timing_quantifie", f"{ratio_unique:.0%} de délais uniques ({uniques}/{len(delais)})", 0.5)
                )

            # Aucun délai long (> 500ms) → pas de pause humaine
            if len(delais) > 20 and max(delais) < 80:
                signaux.append(
                    Signal("pas_de_pause", f"max délai souris = {max(delais):.0f}ms (pas de pause humaine)", 0.5)
                )

            # Trajectoire trop linéaire : angles entre segments consécutifs
            angles = r.get("angles_segments") or []
            if len(angles) >= 10:
                import statistics

                angle_moyen = statistics.mean(angles)
                # Un humain a des changements de direction fréquents (angle moyen > 0.15 rad)
                # Un robot qui fait des lignes droites a un angle moyen très faible
                if angle_moyen < 0.08:
                    signaux.append(
                        Signal(
                            "trajectoire_lineaire",
                            f"angle moyen entre segments = {angle_moyen:.3f} rad (< 0.08 = ligne droite)",
                            0.6,
                        )
                    )
                # Trop d'angles identiques → bruit synthétique régulier
                angles_arr = [round(a, 2) for a in angles]
                uniques_a = len(set(angles_arr))
                ratio_a = uniques_a / len(angles_arr)
                if ratio_a < 0.25:
                    signaux.append(
                        Signal(
                            "courbure_quantifiee",
                            f"{ratio_a:.0%} d'angles uniques ({uniques_a}/{len(angles_arr)})",
                            0.4,
                        )
                    )

            # Rythme de frappe clavier : CV trop faible = timing synthétique
            touches = r.get("delais_clavier_ms") or []
            if len(touches) >= 8:
                import statistics

                m_t = statistics.mean(touches)
                s_t = statistics.stdev(touches) if len(touches) > 1 else 0
                if m_t > 0:
                    cv_t = s_t / m_t
                    if cv_t < 0.12:
                        poids = 1.0 if cv_t < 0.05 else 0.65
                        signaux.append(
                            Signal(
                                "frappe_trop_reguliere",
                                f"CV délais clavier = {cv_t:.2f} (< 0.12 = machine)",
                                poids,
                            )
                        )

        return _verdict(self.name, self.version, signaux)


class DetecteurScroll:
    """Analyse les patterns de défilement (wheel events).

    Un humain scrolle avec des deltas variables (trackpad : bell-curve ; molette : ticks discrets
    mais avec variation). Un robot utilise souvent des deltas identiques (ex: 120px à chaque tick)
    ou des intervalles trop réguliers.
    """

    name = "scroll"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")

        releves = [o["payload"] for o in obs.js if o["kind"] == "comportement"]
        if not releves:
            return _indetermine(self.name, self.version, "sans_releve", "aucun relevé")

        signaux: list[Signal] = []
        for r in releves:
            deltas = r.get("wheel_deltas") or []
            delais = r.get("delais_scroll_ms") or []

            if len(deltas) >= 8:
                import statistics

                # Deltas tous identiques → robot avec pas fixe
                uniques = len(set(round(d, 1) for d in deltas))
                ratio = uniques / len(deltas)
                if ratio < 0.15 and len(deltas) > 10:
                    signaux.append(
                        Signal("deltas_uniformes", f"wheel deltas : {ratio:.0%} uniques ({uniques}/{len(deltas)})", 0.7)
                    )

                # Écart-type des deltas trop faible
                ecart = statistics.stdev(deltas) if len(deltas) > 1 else 0
                moyenne = statistics.mean(abs(d) for d in deltas)
                if moyenne > 0:
                    cv_d = ecart / moyenne
                    if cv_d < 0.1:
                        signaux.append(
                            Signal("scroll_regulier", f"CV des wheel deltas = {cv_d:.2f} (< 0.1 = pas fixe)", 0.6)
                        )

            if len(delais) >= 8:
                import statistics

                m_s = statistics.mean(delais)
                s_s = statistics.stdev(delais) if len(delais) > 1 else 0
                if m_s > 0:
                    cv_s = s_s / m_s
                    if cv_s < 0.1:
                        signaux.append(
                            Signal("scroll_timing_regulier", f"CV délais scroll = {cv_s:.2f} (< 0.1 = machine)", 0.65)
                        )

        return _verdict(self.name, self.version, signaux)


class DetecteurEmpreinteCanvas:
    """Vérifie l'empreinte canvas pour détecter le bruit artificiel.

    Si l'empreinte canvas est identique à celle d'un Chrome headless connu,
    le bruit n'a pas fonctionné. Si elle change à chaque session pour un même
    profil déclaré, c'est du bruit aléatoire non lié à un vrai matériel.
    """

    name = "canvas-empreinte"
    version = "1"

    # Hash connu du canvas sans bruit (Chromium headless par défaut, mesurable)
    HEADLESS_CONNUS: set[str] = set()

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")

        canvas = p.get("canvas")
        signaux: list[Signal] = []

        if isinstance(canvas, str) and canvas.startswith("erreur"):
            signaux.append(Signal("canvas_erreur", f"collecte canvas échouée : {canvas[:60]}", 0.5))
        elif canvas and canvas in self.HEADLESS_CONNUS:
            signaux.append(Signal("canvas_headless_connu", "empreinte canvas identique à un headless connu", 1.0))

        # Vérifier la cohérence avec le WebGL déclaré
        proto = p.get("prototypes") or {}

        # Canvas + WebGL patchés ensemble → forte suspicion d'anti-détection
        if proto.get("canvas_natif") is False and proto.get("webgl_getParameter_natif") is False:
            signaux.append(
                Signal("canvas_webgl_patches", "canvas ET WebGL patchés : probable moteur anti-détection", 0.75)
            )

        return _verdict(self.name, self.version, signaux)


class DetecteurIntegriteProprietes:
    """Vérifie l'intégrité fine des propriétés : .length, .name, stack traces, own keys.

    Les wrappers JS qui remplacent une fonction native oublient souvent de reproduire
    les propriétés secondaires (length, name) ou exposent leur frame dans les stack traces.
    """

    name = "integrite-proprietes"
    version = "1"

    # Valeurs attendues pour les fonctions natives de Chromium
    ATTENDUS = {
        "toDataURL_length": 0,
        "toDataURL_name": "toDataURL",
        "getParameter_length": 1,
        "getParameter_name": "getParameter",
        "toString_length": 0,
        "toString_name": "toString",
    }

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        integ = p.get("integrite") or {}
        signaux: list[Signal] = []

        for cle, attendu in self.ATTENDUS.items():
            val = integ.get(cle)
            if val is not None and val != attendu:
                signaux.append(Signal(f"{cle}_incorrect", f"{cle}={val} (attendu {attendu})", 0.5))

        # Stack trace de toDataURL sur objet invalide : ne devrait PAS contenir de frames JS utilisateur
        stack = integ.get("toDataURL_error_stack") or []
        for frame in stack:
            if frame and "at toDataURL" in frame and "native" not in frame.lower():
                if "<anonymous>" in frame:
                    msg = f"frame init script dans stack toDataURL : {frame[:80]}"
                    signaux.append(Signal("stack_toDataURL_initscript", msg, 0.65))
                else:
                    signaux.append(Signal("stack_toDataURL_js", f"frame JS dans stack toDataURL : {frame[:80]}", 0.75))
                break
        # Stack vide ou anormalement courte : Error.prepareStackTrace filtré ?
        if stack and len(stack) < 2 and not any("native" in f.lower() for f in stack if f):
            signaux.append(Signal("stack_filtre", "stack trace anormalement courte (possible filtrage)", 0.45))

        # Error.prepareStackTrace surchargé
        if integ.get("prepareStackTrace_modifie") is True:
            signaux.append(Signal("prepareStackTrace_patche", "Error.prepareStackTrace surchargé", 0.40))

        # outerWidth redéfini avec un getter non natif
        if integ.get("outerWidth_propre") is True and integ.get("outerWidth_getter_natif") is False:
            signaux.append(Signal("outerWidth_patche", "outerWidth a un getter non natif", 0.5))

        # devicePixelRatio redéfini
        if integ.get("dpr_propre") is True and integ.get("dpr_getter_natif") is False:
            signaux.append(Signal("dpr_patche", "devicePixelRatio a un getter non natif", 0.5))

        # Propriétés inattendues sur navigator (instance)
        own_keys = integ.get("navigator_own_keys") or []
        suspects = [k for k in own_keys if k in ("hardwareConcurrency", "deviceMemory", "plugins", "mimeTypes")]
        if suspects:
            signaux.append(
                Signal(
                    "navigator_own_props",
                    f"propriétés propres sur navigator : {', '.join(suspects)}",
                    0.5,
                )
            )

        return _verdict(self.name, self.version, signaux)


class DetecteurCoherenceEnvironnement:
    """Cohérence entre timezone, locale, screen et viewport.

    Un profil fabriqué peut avoir des incohérences subtiles :
    - Europe/Paris avec en-US comme langue principale
    - screen 3840x2160 mais viewport 800x600
    - outerWidth == innerWidth (headless sans chrome de fenêtre)
    """

    name = "coherence-environnement"
    version = "1"

    TIMEZONE_LOCALES = {
        "Europe/Paris": ("fr",),
        "Europe/Berlin": ("de",),
        "Europe/Madrid": ("es",),
        "Europe/London": ("en",),
        "America/New_York": ("en",),
        "America/Chicago": ("en",),
        "America/Los_Angeles": ("en",),
    }

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        signaux: list[Signal] = []

        fuseau = p.get("fuseau") or {}
        nav = p.get("navigateur") or {}
        ecran = p.get("ecran") or {}
        fenetre = p.get("fenetre") or {}

        # Timezone vs locale
        zone = fuseau.get("zone", "")
        langue = (nav.get("language") or "")[:2].lower()
        attendues = self.TIMEZONE_LOCALES.get(zone) or ()
        if attendues and langue and langue not in attendues:
            signaux.append(
                Signal(
                    "timezone_locale_divergent",
                    f"timezone {zone} avec langue {langue} (attendu : {'/'.join(attendues)})",
                    0.25,
                )
            )

        # Screen vs viewport ratio suspect
        sw = ecran.get("width", 0)
        iw = fenetre.get("innerWidth", 0)
        if sw and iw:
            ratio = iw / sw
            if ratio > 1.0:
                signaux.append(Signal("viewport_gt_screen", f"innerWidth {iw} > screen.width {sw}", 0.75))

        # Timezone offset vs zone name
        decalage = fuseau.get("decalage")
        if zone and decalage is not None:
            # Vérification grossière : Paris/Berlin/Madrid = UTC+1 (offset -60) ou UTC+2 (DST, -120)
            offsets_connus: dict[str, tuple[int, ...]] = {
                "Europe/Paris": (-60, -120),
                "Europe/Berlin": (-60, -120),
                "Europe/Madrid": (-60, -120),
                "Europe/London": (0, -60),
                "America/New_York": (300, 240),
                "America/Chicago": (360, 300),
                "America/Los_Angeles": (480, 420),
            }
            attendus = offsets_connus.get(zone)
            if attendus and decalage not in attendus:
                signaux.append(
                    Signal(
                        "timezone_offset_incoherent",
                        f"zone {zone} avec offset {decalage} (attendu : {attendus})",
                        0.75,
                    )
                )

        return _verdict(self.name, self.version, signaux)


class DetecteurChromeApis:
    """Vérifie la présence et cohérence des API chrome.* que les vrais Chrome exposent."""

    name = "chrome-apis"
    version = "1"

    LOADTIMES_CLES_ATTENDUES = sorted(
        [
            "commitLoadTime",
            "connectionInfo",
            "finishDocumentLoadTime",
            "finishLoadTime",
            "firstPaintAfterLoadTime",
            "firstPaintTime",
            "navigationType",
            "npnNegotiatedProtocol",
            "requestTime",
            "startLoadTime",
            "wasAlternateProtocolAvailable",
            "wasFetchedViaSpdy",
            "wasNpnNegotiated",
        ]
    )

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        chrome = p.get("chrome_apis") or {}
        nav = p.get("navigateur") or {}
        signaux: list[Signal] = []
        is_chrome = "Chrome/" in nav.get("userAgent", "")

        if is_chrome:
            if not chrome.get("chrome_app"):
                signaux.append(Signal("chrome_app_absent", "Chrome annoncé sans chrome.app", 0.5))
            if not chrome.get("chrome_loadTimes"):
                signaux.append(Signal("loadTimes_absent", "Chrome annoncé sans chrome.loadTimes()", 0.5))
            elif chrome.get("loadTimes_keys") != self.LOADTIMES_CLES_ATTENDUES:
                signaux.append(
                    Signal(
                        "loadTimes_incomplet",
                        f"chrome.loadTimes() a des clés inattendues : {chrome.get('loadTimes_keys')}",
                        0.5,
                    )
                )
            if not chrome.get("chrome_csi"):
                signaux.append(Signal("csi_absent", "Chrome annoncé sans chrome.csi()", 0.25))
            if not chrome.get("runtime_PlatformOs"):
                signaux.append(Signal("runtime_incomplet", "chrome.runtime sans PlatformOs (mock partiel)", 0.5))

        return _verdict(self.name, self.version, signaux)


class DetecteurMediaCodecs:
    """Vérifie que canPlayType retourne les bonnes valeurs pour les codecs propriétaires."""

    name = "media-codecs"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        codecs = p.get("media_codecs") or {}
        signaux: list[Signal] = []

        if codecs.get("mp4_avc1") == "":
            signaux.append(Signal("avc1_absent", "canPlayType H.264 = '' (headless sans codecs)", 0.5))
        if codecs.get("audio_aac") == "":
            signaux.append(Signal("aac_absent", "canPlayType AAC = ''", 0.25))
        if codecs.get("canPlayType_natif") is False:
            signaux.append(Signal("canPlayType_patche", "HTMLMediaElement.canPlayType patché", 0.5))

        return _verdict(self.name, self.version, signaux)


class DetecteurLangues:
    """Vérifie la cohérence des langues déclarées et la qualité du patch."""

    name = "langues"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        lang = p.get("languages_test") or {}
        documents = obs.documents
        signaux: list[Signal] = []

        if not lang.get("language_dans_languages"):
            signaux.append(
                Signal(
                    "language_hors_languages",
                    "navigator.language absent de navigator.languages",
                    0.75,
                )
            )
        if lang.get("languages") and not lang.get("languages_gelees"):
            signaux.append(
                Signal(
                    "languages_pas_gelees",
                    "navigator.languages non gelé (Object.freeze manquant)",
                    0.25,
                )
            )
        if lang.get("languages_getter_natif") is False:
            signaux.append(Signal("languages_patche", "navigator.languages a un getter non natif", 0.5))

        if documents:
            e = _entetes(documents[0])
            accept_lang = e.get("accept-language", "").split(",")[0].split(";")[0].strip().lower()
            js_lang = (lang.get("language") or "").lower()
            if accept_lang and js_lang and accept_lang != js_lang:
                signaux.append(
                    Signal(
                        "langue_http_js_divergente",
                        f"Accept-Language principal {accept_lang} ≠ navigator.language {js_lang}",
                        0.5,
                    )
                )

        if lang.get("vendor") != "Google Inc.":
            signaux.append(Signal("vendor_absent", f"navigator.vendor = '{lang.get('vendor')}'", 0.25))

        return _verdict(self.name, self.version, signaux)


class DetecteurHeadless:
    """Détecte les signaux spécifiques à un navigateur headless."""

    name = "headless"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        hs = p.get("headless_signals") or {}
        signaux: list[Signal] = []

        if hs.get("hasFocus") is False:
            signaux.append(
                Signal(
                    "hasFocus_false",
                    "document.hasFocus() retourne false",
                    0.5,
                )
            )
        if hs.get("visibilityState") == "hidden":
            signaux.append(
                Signal(
                    "visibility_hidden",
                    "document.visibilityState = 'hidden'",
                    0.3,
                )
            )
        if hs.get("hidden") is True:
            signaux.append(
                Signal(
                    "document_hidden",
                    "document.hidden = true",
                    0.3,
                )
            )
        if hs.get("webdriver") is True:
            signaux.append(
                Signal(
                    "webdriver_true",
                    "navigator.webdriver = true",
                    1.0,
                )
            )
        if hs.get("webdriver_getter_natif") is False:
            signaux.append(
                Signal(
                    "webdriver_patche",
                    "navigator.webdriver getter non natif",
                    0.4,
                )
            )
        if hs.get("voices_count") is not None and hs["voices_count"] == 0:
            signaux.append(
                Signal(
                    "voices_vide",
                    "speechSynthesis.getVoices() retourne une liste vide",
                    0.4,
                )
            )
        if hs.get("devices_count") is not None and hs["devices_count"] == 0:
            signaux.append(
                Signal(
                    "devices_vide",
                    "mediaDevices.enumerateDevices() retourne une liste vide",
                    0.3,
                )
            )

        return _verdict(self.name, self.version, signaux)


class DetecteurPermissions:
    """Vérifie la cohérence de l'API Permissions sur plusieurs requêtes."""

    name = "permissions-etendu"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(
                self.name,
                self.version,
                "sans_page",
                "scénario sans page HTML",
            )
        p = obs.empreinte_js
        if p is None:
            return _indetermine(
                self.name,
                self.version,
                "non_execute",
                "JavaScript non exécuté",
            )
        hs = p.get("headless_signals") or {}
        perms = hs.get("permissions") or {}
        signaux: list[Signal] = []

        n_granted = sum(1 for v in perms.values() if v == "granted")
        if len(perms) >= 3 and n_granted == len(perms):
            signaux.append(
                Signal(
                    "permissions_all_granted",
                    "Toutes les permissions (geo/cam/mic) granted sans interaction",
                    0.8,
                )
            )
        n_denied = sum(1 for v in perms.values() if v == "denied")
        if len(perms) >= 3 and n_denied == len(perms):
            signaux.append(
                Signal(
                    "permissions_all_denied",
                    "Toutes les permissions denied (headless typique)",
                    0.5,
                )
            )

        return _verdict(self.name, self.version, signaux)


class DetecteurWebRTC:
    """Détecte les fuites d'IP locale via WebRTC ou un RTCPeerConnection patché."""

    name = "webrtc"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        rtc = p.get("webrtc_test") or {}
        signaux: list[Signal] = []

        if rtc.get("disponible") is False:
            return _verdict(self.name, self.version, signaux)

        if rtc.get("rtc_natif") is False:
            signaux.append(
                Signal(
                    "rtc_patche",
                    "RTCPeerConnection.toString() non natif",
                    0.4,
                )
            )
        if rtc.get("candidats_host", 0) > 0:
            signaux.append(
                Signal(
                    "rtc_host_leak",
                    f"{rtc['candidats_host']} candidats host exposant l'IP locale",
                    0.0,
                )
            )
        if rtc.get("sdp_host_lines", 0) > 0:
            signaux.append(
                Signal(
                    "sdp_host_leak",
                    f"{rtc['sdp_host_lines']} lignes host dans le SDP",
                    0.0,
                )
            )

        return _verdict(self.name, self.version, signaux)


class DetecteurStackTrace:
    """Détecte les traces d'injection dans les stack traces d'erreur."""

    name = "stack-trace"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        st = p.get("stack_trace_test") or {}
        signaux: list[Signal] = []

        for marqueur in (
            "patchright",
            "playwright",
            "puppeteer",
            "cdp",
            "devtools",
        ):
            if st.get(f"contient_{marqueur}"):
                signaux.append(
                    Signal(
                        f"stack_{marqueur}",
                        f"Stack trace contient '{marqueur}'",
                        1.0,
                    )
                )

        if st.get("prepareStackTrace_present") and not st.get("prepareStackTrace_natif", True):
            signaux.append(
                Signal(
                    "prepareStackTrace_patche",
                    "Error.prepareStackTrace surchargé (filtrage de stack)",
                    0.3,
                )
            )

        return _verdict(self.name, self.version, signaux)


class DetecteurPositionFenetre:
    """Détecte les fenêtres headless (screenX/Y à 0, memory incohérente)."""

    name = "position-fenetre"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        pm = p.get("performance_memory") or {}
        signaux: list[Signal] = []

        if pm.get("screenX") == 0 and pm.get("screenY") == 0:
            signaux.append(
                Signal(
                    "screen_position_zero",
                    "screenX et screenY à 0 (typique headless)",
                    0.4,
                )
            )

        if pm.get("memory_propre") and not pm.get("memory_getter_natif", True):
            signaux.append(
                Signal(
                    "memory_patche",
                    "performance.memory getter surchargé",
                    0.3,
                )
            )

        return _verdict(self.name, self.version, signaux)


class DetecteurAutomationGlobals:
    """Détecte les globales d'automation laissées par Playwright/Selenium/ChromeDriver."""

    name = "automation-globals"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        ag = p.get("automation_globals") or {}
        signaux: list[Signal] = []

        trouvees = ag.get("globales_trouvees") or []
        if trouvees:
            signaux.append(
                Signal(
                    "globales_automation",
                    f"globales d'automation trouvées : {', '.join(trouvees[:5])}",
                    0.9,
                )
            )

        cdc = ag.get("cdc_keys") or []
        if cdc:
            signaux.append(Signal("cdc_keys", f"clés ChromeDriver trouvées : {', '.join(cdc[:3])}", 0.9))

        noezia_enum = ag.get("noezia_enumerable") or []
        if noezia_enum:
            signaux.append(
                Signal(
                    "noezia_enumerable",
                    f"marqueurs NOEZIA énumérables : {', '.join(noezia_enum[:3])}",
                    0.5,
                )
            )

        doc_trouvees = ag.get("doc_trouvees") or []
        if doc_trouvees:
            signaux.append(Signal("doc_automation", f"marqueurs sur document : {', '.join(doc_trouvees[:3])}", 0.8))

        return _verdict(self.name, self.version, signaux)


class DetecteurCSSMedia:
    """Détecte les incohérences CSS media queries typiques de headless."""

    name = "css-media"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        cm = p.get("css_media") or {}
        signaux: list[Signal] = []

        if cm.get("hover_none") and not cm.get("hover_hover"):
            signaux.append(Signal("hover_none", "hover:none — pas de souris (headless ou mobile)", 0.5))

        if cm.get("pointer_none") and not cm.get("pointer_fine"):
            signaux.append(Signal("pointer_none", "pointer:none — pas de périphérique de pointage", 0.5))

        if cm.get("matchMedia_natif") is False:
            signaux.append(Signal("matchMedia_patche", "matchMedia surchargé", 0.3))

        if cm.get("display_mode_browser") is False:
            signaux.append(
                Signal(
                    "display_mode_not_browser",
                    "display-mode:browser retourne false (headless Chrome)",
                    0.5,
                )
            )

        return _verdict(self.name, self.version, signaux)


class DetecteurPrototypeChain:
    """Détecte les propriétés propres inattendues sur navigator/screen."""

    name = "prototype-chain"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        pc = p.get("prototype_chain") or {}
        signaux: list[Signal] = []

        nav_own = pc.get("navigator_own") or {}
        for prop, info in nav_own.items():
            if isinstance(info, dict) and info.get("own") and not info.get("prototype"):
                signaux.append(
                    Signal(
                        f"nav_own_{prop}",
                        f"navigator.{prop} est une propriété propre sans prototype",
                        0.4,
                    )
                )

        if pc.get("screen_own_width"):
            signaux.append(Signal("screen_own_width", "screen.width est une propriété propre", 0.3))
        if pc.get("screen_own_height"):
            signaux.append(Signal("screen_own_height", "screen.height est une propriété propre", 0.3))

        return _verdict(self.name, self.version, signaux)


class DetecteurTimingPrecision:
    """Détecte les anomalies de précision temporelle (timer headless)."""

    name = "timing-precision"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        tp = p.get("timing_precision") or {}
        signaux: list[Signal] = []

        if tp.get("perf_now_natif") is False:
            signaux.append(Signal("perf_now_patche", "performance.now() surchargé", 0.3))

        min_delta = tp.get("min_delta")
        if min_delta is not None and min_delta > 0:
            if min_delta < 0.005:
                signaux.append(
                    Signal(
                        "timer_haute_precision",
                        f"timer avec précision {min_delta:.4f}ms (cross-origin isolation ?)",
                        0.2,
                    )
                )

        return _verdict(self.name, self.version, signaux)


class DetecteurPaintTiming:
    """Détecte l'absence ou les anomalies de PerformancePaintTiming (headless Chrome)."""

    name = "paint-timing"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        pt = p.get("paint_timing") or {}
        signaux: list[Signal] = []

        if pt.get("count") is not None and pt["count"] == 0:
            signaux.append(
                Signal(
                    "no_paint_entries",
                    "aucune entrée paint (first-paint/first-contentful-paint manquantes)",
                    0.5,
                )
            )
        elif not pt.get("has_first_paint"):
            signaux.append(
                Signal(
                    "no_first_paint",
                    "first-paint manquant",
                    0.3,
                )
            )
        elif not pt.get("has_first_contentful_paint"):
            signaux.append(
                Signal(
                    "no_fcp",
                    "first-contentful-paint manquant",
                    0.3,
                )
            )

        fp_time = pt.get("first_paint_time")
        if fp_time is not None and fp_time == 0:
            signaux.append(
                Signal(
                    "fp_zero",
                    "first-paint startTime = 0 (anormal)",
                    0.4,
                )
            )

        if pt.get("getEntriesByType_natif") is False:
            signaux.append(
                Signal(
                    "getEntriesByType_patche",
                    "performance.getEntriesByType() surchargé",
                    0.3,
                )
            )

        return _verdict(self.name, self.version, signaux)


class DetecteurCanvasConsistency:
    """Cohérence entre toDataURL et getImageData — un patch naïf produit des résultats différents."""

    name = "canvas-consistency"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        cc = p.get("canvas_consistency") or {}
        signaux: list[Signal] = []

        if cc.get("toDataURL_stable") is False:
            signaux.append(Signal("toDataURL_instable", "toDataURL() non déterministe entre appels", 0.8))

        if cc.get("getImageData_stable") is False:
            signaux.append(Signal("getImageData_instable", "getImageData() non déterministe entre appels", 0.8))

        return _verdict(self.name, self.version, signaux)


class DetecteurStackGetter:
    """Détecte la modification du getter Error.prototype.stack (filtrage de stack traces)."""

    name = "stack-getter"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        sg = p.get("stack_getter") or {}
        signaux: list[Signal] = []

        if sg.get("stack_has_getter") and sg.get("stack_getter_natif") is False:
            signaux.append(
                Signal("stack_getter_patche", "Error.prototype.stack getter non natif", 0.5)
            )

        if sg.get("stack_has_patchright"):
            signaux.append(Signal("stack_patchright", "patchright visible dans stack trace", 0.9))
        if sg.get("stack_has_playwright"):
            signaux.append(Signal("stack_playwright", "playwright visible dans stack trace", 0.9))

        line_count = sg.get("stack_line_count")
        if isinstance(line_count, int) and line_count < 2:
            signaux.append(Signal("stack_trop_court", f"stack trace de {line_count} ligne(s)", 0.4))

        return _verdict(self.name, self.version, signaux)


class DetecteurRAFTiming:
    """Détecte les anomalies de requestAnimationFrame (timestamps fixes ou à 0 en headless)."""

    name = "raf-timing"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        rt = p.get("raf_timing") or {}
        signaux: list[Signal] = []

        if rt.get("all_zero"):
            signaux.append(
                Signal("raf_all_zero", "tous les deltas rAF à 0 (headless sans vsync)", 0.6)
            )

        if rt.get("all_same") and not rt.get("all_zero"):
            signaux.append(
                Signal(
                    "raf_all_same",
                    f"tous les deltas rAF identiques ({rt.get('mean_delta')}ms)",
                    0.4,
                )
            )

        mean = rt.get("mean_delta")
        if isinstance(mean, (int, float)) and mean > 0 and mean < 4:
            signaux.append(
                Signal("raf_trop_rapide", f"rAF moyen {mean}ms (< 4ms, pas de vsync)", 0.5)
            )

        return _verdict(self.name, self.version, signaux)


def _requetes_par_seconde(documents: list[dict[str, Any]]) -> float | None:
    if len(documents) < 3:
        return None
    debut = datetime.fromisoformat(documents[0]["received_at"])
    fin = datetime.fromisoformat(documents[-1]["received_at"])
    duree = (fin - debut).total_seconds()
    return (len(documents) - 1) / duree if duree > 0 else None


DETECTEURS: dict[str, Detecteur] = {
    d.name: d
    for d in (
        DetecteurBotD(),
        DetecteurReglesHttp(),
        DetecteurReglesJs(),
        DetecteurCoherence(),
        DetecteurTls(),
        DetecteurComportement(),
        DetecteurPrototypes(),
        DetecteurCoherenceProfonde(),
        DetecteurEntropieInteraction(),
        DetecteurScroll(),
        DetecteurEmpreinteCanvas(),
        DetecteurIntegriteProprietes(),
        DetecteurCoherenceEnvironnement(),
        DetecteurChromeApis(),
        DetecteurMediaCodecs(),
        DetecteurLangues(),
        DetecteurHeadless(),
        DetecteurPermissions(),
        DetecteurWebRTC(),
        DetecteurStackTrace(),
        DetecteurPositionFenetre(),
        DetecteurAutomationGlobals(),
        DetecteurCSSMedia(),
        DetecteurPrototypeChain(),
        DetecteurTimingPrecision(),
        DetecteurPaintTiming(),
        DetecteurCanvasConsistency(),
        DetecteurStackGetter(),
        DetecteurRAFTiming(),
    )
}


def registre() -> dict[str, Detecteur]:
    """Détecteurs intégrés, plus ceux d'un paquet externe (point d'entrée `shadowlab.detectors`)."""
    detecteurs = dict(DETECTEURS)
    for point in entry_points(group="shadowlab.detectors"):
        detecteurs.setdefault(point.name, point.load()())
    return detecteurs


def classer(obs: Observations, noms: list[str] | None = None) -> list[Classement]:
    tous = registre()
    return [tous[nom].classer(obs) for nom in (noms or list(tous))]


def proprietes(obs: Observations) -> dict[str, Any]:
    """Empreinte normalisée d'une session, pour la table `fingerprints`."""
    documents = obs.documents
    premier = documents[0] if documents else None
    comportement = [o["payload"] for o in obs.js if o["kind"] == "comportement"]
    return {
        "browser_properties": obs.empreinte_js or {"statut": "not_collected", "raison": "pas de JavaScript"},
        "http_properties": {
            "http_version": premier["http_version"] if premier else "unknown",
            "ordre_entetes": [nom for nom, _ in premier["headers"]] if premier else [],
            "entetes": premier["headers"] if premier else [],  # paires, dans l'ordre reçu
            "requetes": len(obs.http),
        },
        "tls_properties": obs.tls
        or {"statut": "not_collected", "raison": "session hors Arena : le site direct est servi en HTTP local"},
        "session_properties": {
            "pages": [o["path"] for o in documents],
            "cookies_renvoyes": sorted({c for o in documents for c in o["cookies"]}),
            "comportement": comportement[-1] if comportement else {"statut": "not_collected"},
        },
    }
