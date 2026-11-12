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
PLAFOND_DELAIS_SOURIS = 50  # observateur.js ne garde que les 50 premiers délais de souris d'une page

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
    correlation: dict[str, dict] | None = None  # données cross-session (rempli par le gardien)

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


def _annonce_headless(obs_http: dict[str, Any]) -> bool:
    """« HeadlessChrome » dans le User-Agent ou dans les marques annoncées (`sec-ch-ua`) d'une requête."""
    e = _entetes(obs_http)
    return any("headlesschrome" in e.get(nom, "").lower() for nom in ("user-agent", "sec-ch-ua"))


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
    """Règles sur les en-têtes HTTP des requêtes de pages, sans JavaScript.

    V2.1 (12/11/2026) : « HeadlessChrome » cherché dans toutes les requêtes de la session, pas seulement dans
    la première page. Un moteur qui réécrit son identité laisse passer des requêtes non réécrites
    (campagne 94 : 182 requêtes de NOEZIA sur 1 160). Aucun vrai navigateur n'envoie ce mot.
    """

    name = "regles-http"
    version = "2.1"

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
        else:
            fuites = sum(1 for o in obs.http if _annonce_headless(o))
            if fuites:
                description = f"« HeadlessChrome » dans les en-têtes de {fuites} requête(s) sur {len(obs.http)}"
                signaux.append(Signal("headless_dans_une_requete", description, 1.0))
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
    """Analyse approfondie du ClientHello TLS : profils navigateur, cohérence UA/TLS,
    détection de piles de bibliothèques, anomalies structurelles.

    V2 : 17 règles couvrant GREASE, ALPN, chiffrements (compte, ordre, TLS 1.3),
    extensions (Chrome/Firefox-spécifiques, comptage), groupes (courbes, ordre),
    signatures, version TLS, et détection OpenSSL.
    V2.1 (12/11/2026) : ALPS reconnu sous ses deux numéros ; la V2 signalait tout Chrome récent.
    """

    name = "tls"
    version = "2.1"

    _TLS13_SUITES = frozenset({"1301", "1302", "1303"})
    _CIPHERS_NAVIGATEUR = frozenset({"1301", "1302", "1303", "c02b", "c02f"})
    _EXT_NAVIGATEUR = frozenset({"0000", "000a", "000b", "000d", "002b", "0033"})
    _EXT_CHROME_OBLIGATOIRES = frozenset({"001b"})
    # ALPS (application_settings) : ancien numéro 17513, puis 17613 dans les Chrome récents (seul vu en campagne 93).
    _EXT_ALPS = frozenset({"4469", "44cd"})
    _EXT_CHROME_SPECIFIQUES = _EXT_ALPS | {"001b"}
    _GRP_X25519 = "001d"
    _GRP_P256 = "0017"
    _GRP_FFDHE = "0100"

    def classer(self, obs: Observations) -> Classement:
        t = obs.tls
        if t is None:
            return _indetermine(self.name, self.version, "sans_tls", "session hors Arena : TLS non observé")
        documents = obs.documents
        ua = _entetes(documents[0]).get("user-agent", "").lower() if documents else ""

        grease = t.get("grease")
        alpn = t.get("alpn") or []
        chiffrements = t.get("chiffrements", [])
        extensions = t.get("extensions", [])
        groupes = t.get("groupes", [])
        signatures = t.get("signatures", [])
        versions = t.get("versions", [])
        nb_chiffr = t.get("nb_chiffrements", len(chiffrements))
        nb_ext = t.get("nb_extensions", len(extensions))

        chrome = "chrome/" in ua and "edg/" not in ua
        edge = "edg/" in ua
        firefox = "firefox/" in ua
        safari = "safari/" in ua and "chrome/" not in ua
        navigateur = chrome or edge or firefox or safari

        ext_set = frozenset(extensions)
        cipher_set = frozenset(chiffrements)
        groupe_set = frozenset(groupes)

        signaux: list[Signal] = []

        # ── GREASE ──
        if (chrome or edge) and not grease:
            signaux.append(
                Signal(
                    "chrome_sans_grease",
                    "Chrome/Edge annoncé sans valeur GREASE dans le ClientHello",
                    0.7,
                )
            )
        if firefox and grease:
            signaux.append(
                Signal(
                    "firefox_avec_grease",
                    "Firefox annoncé avec valeurs GREASE (Firefox n'en envoie pas)",
                    0.7,
                )
            )

        # ── ALPN (HTTP/2) ──
        if navigateur and "h2" not in alpn:
            signaux.append(
                Signal(
                    "navigateur_sans_h2",
                    f"navigateur annoncé sans HTTP/2 dans l'ALPN : {alpn}",
                    0.6,
                )
            )
        if not navigateur and not grease and "h2" not in alpn:
            signaux.append(
                Signal(
                    "pile_non_navigateur",
                    "ni GREASE ni HTTP/2 : pile TLS de bibliothèque",
                    0.5,
                )
            )

        # ── Comptage de chiffrements ──
        if nb_chiffr < 5:
            signaux.append(
                Signal(
                    "peu_de_chiffrements",
                    f"seulement {nb_chiffr} chiffrements (navigateur moderne : 15+)",
                    0.5,
                )
            )
        elif navigateur and nb_chiffr < 10:
            signaux.append(
                Signal(
                    "chiffrements_insuffisants",
                    f"{nb_chiffr} chiffrements pour un navigateur (attendu : 15+)",
                    0.4,
                )
            )

        # ── Comptage d'extensions ──
        if nb_ext < 5:
            signaux.append(
                Signal(
                    "peu_d_extensions",
                    f"seulement {nb_ext} extensions TLS (navigateur : 13+)",
                    0.5,
                )
            )
        elif navigateur and nb_ext < 10:
            signaux.append(
                Signal(
                    "extensions_insuffisantes",
                    f"{nb_ext} extensions pour un navigateur (attendu : 13+)",
                    0.4,
                )
            )

        # ── Suites TLS 1.3 ──
        tls13 = cipher_set & self._TLS13_SUITES
        if navigateur and not tls13:
            signaux.append(
                Signal(
                    "sans_tls13_suites",
                    "navigateur annoncé sans suite TLS 1.3",
                    0.6,
                )
            )
        elif tls13 and chiffrements and chiffrements[0] not in self._TLS13_SUITES and navigateur:
            signaux.append(
                Signal(
                    "tls13_pas_en_tete",
                    f"première suite = {chiffrements[0]}, pas TLS 1.3 (navigateurs : TLS 1.3 en tête)",
                    0.4,
                )
            )

        # ── Extensions Chrome obligatoires ──
        if chrome or edge:
            manquantes = self._EXT_CHROME_OBLIGATOIRES - ext_set
            if manquantes:
                signaux.append(
                    Signal(
                        "chrome_ext_manquantes",
                        f"Chrome/Edge sans compress_certificate ({', '.join(sorted(manquantes))})",
                        0.5,
                    )
                )
            if not self._EXT_ALPS & ext_set:
                signaux.append(
                    Signal(
                        "chrome_sans_alps",
                        "Chrome annoncé sans extension ALPS (application_settings)",
                        0.3,
                    )
                )

        # ── Extensions Firefox ──
        if firefox:
            if "001c" not in ext_set:
                signaux.append(
                    Signal(
                        "firefox_sans_record_size",
                        "Firefox annoncé sans record_size_limit",
                        0.3,
                    )
                )
            if "001b" in ext_set:
                signaux.append(
                    Signal(
                        "firefox_avec_compress_cert",
                        "Firefox annoncé avec compress_certificate (extension Chrome, pas Firefox)",
                        0.5,
                    )
                )

        # ── Confusion cross-navigateur ──
        if not chrome and not edge and firefox:
            if self._EXT_CHROME_SPECIFIQUES & ext_set:
                signaux.append(
                    Signal(
                        "firefox_ext_chrome",
                        "Firefox annoncé avec extensions Chrome-only (ALPS/compress_certificate)",
                        0.5,
                    )
                )

        # ── Groupes (courbes elliptiques) ──
        if navigateur and groupes:
            if self._GRP_X25519 not in groupe_set:
                signaux.append(
                    Signal(
                        "sans_x25519",
                        "navigateur annoncé sans x25519 dans les groupes",
                        0.5,
                    )
                )
            if (chrome or edge) and self._GRP_FFDHE in groupe_set:
                signaux.append(
                    Signal(
                        "chrome_avec_ffdhe",
                        "Chrome annoncé avec ffdhe2048 (groupe Firefox, pas Chrome)",
                        0.4,
                    )
                )
            if firefox and self._GRP_FFDHE not in groupe_set:
                signaux.append(
                    Signal(
                        "firefox_sans_ffdhe",
                        "Firefox annoncé sans ffdhe2048",
                        0.3,
                    )
                )

        # ── Ordre des groupes ──
        if navigateur and self._GRP_X25519 in groupe_set and self._GRP_P256 in groupe_set:
            if groupes.index(self._GRP_X25519) > groupes.index(self._GRP_P256):
                signaux.append(
                    Signal(
                        "groupes_desordre",
                        "x25519 après P-256 (navigateurs : x25519 d'abord)",
                        0.3,
                    )
                )

        # ── Extensions navigateur standard manquantes ──
        if navigateur:
            manquantes_std = self._EXT_NAVIGATEUR - ext_set
            nb_manq = len(manquantes_std)
            if nb_manq >= 3:
                signaux.append(
                    Signal(
                        "extensions_std_manquantes",
                        f"{nb_manq} extensions standard manquantes : {', '.join(sorted(manquantes_std))}",
                        0.5,
                    )
                )
            elif nb_manq >= 1:
                signaux.append(
                    Signal(
                        "extensions_std_partielles",
                        f"extension(s) standard manquante(s) : {', '.join(sorted(manquantes_std))}",
                        0.2,
                    )
                )

        # ── Chiffrements navigateur communs manquants ──
        if navigateur and len(self._CIPHERS_NAVIGATEUR - cipher_set) >= 3:
            signaux.append(
                Signal(
                    "ciphers_communs_manquants",
                    f"{len(self._CIPHERS_NAVIGATEUR - cipher_set)} chiffrements navigateur de base manquants",
                    0.4,
                )
            )

        # ── supported_versions absent ──
        if navigateur and "002b" not in ext_set:
            signaux.append(
                Signal(
                    "sans_supported_versions",
                    "navigateur annoncé sans extension supported_versions",
                    0.5,
                )
            )

        # ── Signatures ──
        if navigateur and not signatures:
            signaux.append(
                Signal(
                    "sans_signatures",
                    "navigateur annoncé sans algorithmes de signature",
                    0.5,
                )
            )
        elif navigateur and len(signatures) < 5:
            signaux.append(
                Signal(
                    "peu_de_signatures",
                    f"seulement {len(signatures)} algorithmes de signature (navigateur : 8+)",
                    0.3,
                )
            )

        # ── Version TLS maximale ──
        if navigateur and versions and max(versions) < 0x0304:
            signaux.append(
                Signal(
                    "pas_tls13_version",
                    "navigateur annoncé sans support TLS 1.3 dans supported_versions",
                    0.5,
                )
            )

        # ── Empreinte OpenSSL (TLS_AES_256_GCM en tête) ──
        if not grease and "h2" not in alpn and chiffrements and chiffrements[0] == "1302":
            signaux.append(
                Signal(
                    "pile_openssl",
                    "ordre chiffrements caractéristique OpenSSL (AES-256-GCM en tête, pas AES-128-GCM)",
                    0.4,
                )
            )

        return _verdict(self.name, self.version, signaux)


class DetecteurComportement:
    """Analyse comportementale avancée : signaux classiques + analyse de naturalité.

    V2 ajoute des signaux de « comportement trop parfait » : un humain réel a des
    patterns imparfaits (ratio mousemove/click élevé, hover erratique, micro-pauses
    dans les trajectoires, retours en arrière). L'absence de ces imperfections est
    elle-même un signal.
    V2.1 (12/11/2026) : `pas_de_scroll` ne compte que les pages qui pouvaient défiler (`page_defilable`) ;
    la V2 classait aussi la molette tournée sur une page plus courte que la fenêtre (campagne 94).
    """

    name = "comportement"
    version = "2.1"

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
        if not releves:
            if obs.empreinte_js is None:
                return _indetermine(self.name, self.version, "sans_releve", "aucun relevé de comportement reçu")
            return _verdict(self.name, self.version, signaux)

        evenements = [r.get("evenements", {}) for r in releves]
        total_moves = sum(e.get("mousemove", 0) for e in evenements)
        total_clicks = sum(e.get("click", 0) for e in evenements)
        interactions = sum(sum(e.values()) for e in evenements)
        duree = sum(r.get("duree_page_ms") or 0 for r in releves)

        if interactions == 0:
            signaux.append(Signal("aucune_interaction", "aucun mouvement, clic, touche ni défilement", 0.5))
        elif total_moves == 0 and total_clicks > 0:
            signaux.append(Signal("clic_sans_souris", "des clics sans aucun mouvement de souris", 0.5))

        if duree and duree < SEUIL_DUREE_PAGE_MS * len(releves):
            signaux.append(Signal("pages_eclair", f"moins de {SEUIL_DUREE_PAGE_MS} ms par page en moyenne", 0.5))

        # --- Signaux de naturalité (v2) ---
        # Un humain produit typiquement 30-200 mousemove par clic.
        # Un bot Bézier fait des trajectoires directes : ratio < 10 est suspect.
        if total_clicks > 0 and total_moves > 0:
            ratio_move_click = total_moves / total_clicks
            if ratio_move_click < 8:
                signaux.append(
                    Signal(
                        "ratio_move_click_faible",
                        f"ratio mousemove/click = {ratio_move_click:.1f} (< 8 = trajectoire directe)",
                        0.5,
                    )
                )

        # Absence totale de scroll sur des pages longues : un humain scrolle pour lire.
        # Seules comptent les pages qui pouvaient défiler (`page_defilable`, lu par l'observateur à la sortie de la
        # page) : sur une page plus courte que la fenêtre, la molette ne produit aucun événement `scroll`, pour un
        # humain comme pour un robot. Un relevé ancien, sans ce champ, n'est pas compté : la règle ne conclut pas.
        defilables = [r.get("evenements", {}) for r in releves if r.get("page_defilable") is True]
        moves_defilables = sum(e.get("mousemove", 0) for e in defilables)
        scrolls_defilables = sum(e.get("scroll", 0) for e in defilables)
        if moves_defilables > 20 and scrolls_defilables == 0 and len(defilables) >= 2:
            signaux.append(
                Signal(
                    "pas_de_scroll",
                    "mouvements souris sans aucun défilement sur plusieurs pages plus hautes que la fenêtre",
                    0.35,
                )
            )

        # Analyse des pauses inter-pages : un humain a des durées de page très variables
        durees_pages = [r.get("duree_page_ms") or 0 for r in releves if (r.get("duree_page_ms") or 0) > 0]
        if len(durees_pages) >= 3:
            import statistics

            moy = statistics.mean(durees_pages)
            if moy > 0:
                cv_duree = statistics.stdev(durees_pages) / moy
                if cv_duree < 0.2:
                    signaux.append(
                        Signal(
                            "duree_pages_reguliere",
                            f"CV durée des pages = {cv_duree:.2f} (< 0.2 = timing trop régulier)",
                            0.4,
                        )
                    )

        # Pas de retour arrière (revisiter la même page) : un humain revient souvent en arrière
        chemins = [d["path"] for d in documents if not d["path"].startswith(CHEMINS_TECHNIQUES)]
        if len(chemins) >= 4 and len(chemins) == len(set(chemins)):
            signaux.append(
                Signal(
                    "navigation_lineaire",
                    f"{len(chemins)} pages toutes distinctes (pas de retour en arrière)",
                    0.25,
                )
            )

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
    - deviceMemory doit être dans {0.25, 0.5, 1, 2, 4, 8, 16, 32}

    V1.1 (12/11/2026) : deviceMemory 16 et 32 acceptés ; la V1 signalait tout humain sur une machine de 16 Go ou plus.
    """

    name = "coherence-profonde"
    version = "1.1"

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

        # hardwareConcurrency : les CPU Intel sont des puissances de 2, mais Apple Silicon
        # a des valeurs non-puissance-de-2 (M1 Pro=10, M2 Pro=12, M4 Pro=14…).
        # On ne flag que les valeurs qui ne sont ni puissance de 2 ni connues Apple Silicon.
        hwc = nav.get("hardwareConcurrency")
        _HWC_APPLE_SILICON = {10, 11, 12, 14, 16, 18, 20, 24}
        if isinstance(hwc, int) and hwc > 0:
            est_puissance_2 = hwc & (hwc - 1) == 0
            if not est_puissance_2 and hwc not in _HWC_APPLE_SILICON:
                signaux.append(
                    Signal(
                        "hwc_non_puissance2",
                        f"hardwareConcurrency={hwc} n'est ni puissance de 2 ni Apple Silicon connu",
                        0.25,
                    )
                )
            if hwc > 128:
                signaux.append(Signal("hwc_excessif", f"hardwareConcurrency={hwc} > 128", 0.5))

        # deviceMemory : Chrome a relevé ses paliers en 2026 (2, 4, 8, 16, 32 hors Android) ; le Chromium 156
        # piloté sans réglage annonce 32 sur une machine de 64 Go (campagne 94).
        dm = nav.get("deviceMemory")
        if isinstance(dm, (int, float)) and dm not in (0.25, 0.5, 1, 2, 4, 8, 16, 32, "unknown"):
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


def _plus_longue_pause(releve: dict[str, Any], delais: list[float]) -> float | None:
    """Plus grand délai entre deux mouvements de souris sur toute la page ; None si le relevé ne le dit pas.

    Relevé récent : `delai_souris_max_ms`, tenu par l'observateur sur toute la page. Relevé ancien, sans ce champ :
    sous le plafond, la liste contient tous les délais de la page et son maximum fait foi ; plafonnée, la suite de
    la page est inconnue et la règle ne conclut pas.
    """
    maximum = releve.get("delai_souris_max_ms")
    if isinstance(maximum, (int, float)) and not isinstance(maximum, bool):
        return maximum
    if not delais or len(delais) >= PLAFOND_DELAIS_SOURIS:
        return None
    return max(delais)


class DetecteurEntropieInteraction:
    """Analyse l'entropie temporelle des interactions souris.

    Un humain a une distribution de délais entre mouvements souris qui suit
    approximativement une loi log-normale. Un robot a des délais trop réguliers
    (faible écart-type) ou trop uniformément distribués.
    V1.1 (12/11/2026) : `pas_de_pause` juge la page entière (`delai_souris_max_ms`) ; la V1 ne lisait que les
    50 premiers délais, soit un seul geste continu d'environ 1,5 s (campagne 94).
    """

    name = "entropie-interaction"
    version = "1.1"

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

            # Aucune pause entre deux mouvements de souris sur toute la page → pas de pause humaine
            plus_longue = _plus_longue_pause(r, delais)
            if len(delais) > 20 and plus_longue is not None and plus_longue < 80:
                signaux.append(
                    Signal("pas_de_pause", f"max délai souris = {plus_longue:.0f}ms (pas de pause humaine)", 0.5)
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
    """Vérifie la présence et cohérence des API chrome.* que les vrais Chrome exposent.

    V1.1 (12/11/2026) : `chrome.runtime` n'est plus exigé. Un vrai Chrome ne l'expose pas sur une page ordinaire
    (campagnes 96 et 97 : absent dans tous les relevés de Google Chrome 156 avec interface, comme chez les témoins
    sans interface) ; l'exiger classait tout vrai Chrome et ne laissait passer que l'imitation d'anciens outils.
    `runtime_incomplet` ne juge plus qu'un chrome.runtime présent sans `PlatformOs` : une imitation partielle.
    """

    name = "chrome-apis"
    version = "1.1"

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
            if chrome.get("chrome_runtime") and not chrome.get("runtime_PlatformOs"):
                signaux.append(
                    Signal("runtime_incomplet", "chrome.runtime présent sans PlatformOs (imitation partielle)", 0.5)
                )

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
    """Détecte les signaux spécifiques à un navigateur headless.

    V1.1 (12/11/2026) : `voices_vide` ne juge que des voix qui ont eu le temps d'arriver. Chrome charge la liste
    après le premier appel de getVoices() et l'annonce par l'événement `voiceschanged` : lue d'emblée, elle était
    vide chez tout le monde, vrai Chrome 156 avec interface compris (campagnes 96 et 97, tous les relevés).
    L'observateur l'attend désormais (au plus `DELAI_VOIX_MS`) et dit combien de temps elle a eu ; un relevé plus
    ancien ne fait pas conclure la règle.
    """

    name = "headless"
    version = "1.1"
    DELAI_VOIX_MS = 250  # attente maximale de `voiceschanged` dans observateur.js (`DELAI_VOIX_MS`)

    def _voix_attendues(self, hs: dict[str, Any]) -> bool:
        """La liste des voix a eu le temps d'arriver : le navigateur l'a annoncée, ou l'attente maximale est passée."""
        attente = hs.get("voices_attente_ms")
        return hs.get("voices_evenement") is True or (
            isinstance(attente, int | float) and attente >= self.DELAI_VOIX_MS
        )

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
        if hs.get("voices_count") is not None and hs["voices_count"] == 0 and self._voix_attendues(hs):
            signaux.append(
                Signal(
                    "voices_vide",
                    f"speechSynthesis.getVoices() vide après {hs.get('voices_attente_ms')} ms d'attente",
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
                    1.0,
                )
            )

        doc_trouvees = ag.get("doc_trouvees") or []
        if doc_trouvees:
            signaux.append(Signal("doc_automation", f"marqueurs sur document : {', '.join(doc_trouvees[:3])}", 0.8))

        injection = ag.get("injection_globals") or []
        if injection:
            signaux.append(
                Signal(
                    "injection_globals",
                    f"profils d'automation injectés : {', '.join(injection[:3])}",
                    1.0,
                )
            )

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
            signaux.append(Signal("stack_getter_patche", "Error.prototype.stack getter non natif", 0.5))

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
            signaux.append(Signal("raf_all_zero", "tous les deltas rAF à 0 (headless sans vsync)", 0.6))

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
            signaux.append(Signal("raf_trop_rapide", f"rAF moyen {mean}ms (< 4ms, pas de vsync)", 0.5))

        return _verdict(self.name, self.version, signaux)


class DetecteurWorkerConsistency:
    """Compare navigator dans un Worker vs main thread : toute divergence = bot."""

    name = "worker-consistency"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        wc = p.get("worker_consistency") or {}
        signaux: list[Signal] = []

        if not wc.get("available"):
            return _indetermine(self.name, self.version, "worker_indisponible", "Worker non supporté ou timeout")

        if wc.get("hc_match") is False:
            signaux.append(
                Signal(
                    "worker_hc_mismatch",
                    f"hardwareConcurrency main={wc.get('main_hardwareConcurrency')} "
                    f"vs worker={wc.get('worker_hardwareConcurrency')}",
                    1.0,
                )
            )

        if wc.get("dm_match") is False:
            signaux.append(
                Signal(
                    "worker_dm_mismatch",
                    f"deviceMemory main={wc.get('main_deviceMemory')} vs worker={wc.get('worker_deviceMemory')}",
                    0.8,
                )
            )

        if wc.get("platform_match") is False:
            signaux.append(
                Signal(
                    "worker_platform_mismatch",
                    f"platform main={wc.get('main_platform')} vs worker={wc.get('worker_platform')}",
                    0.9,
                )
            )

        return _verdict(self.name, self.version, signaux)


class DetecteurConnectionDynamic:
    """Vérifie la cohérence de l'API NetworkInformation.

    V1.1 (12/11/2026) : `rtt_zero` retiré. Une latence estimée nulle n'est pas une valeur propre au mode sans
    interface : Chrome l'estime d'après ses échanges réseau, et sur l'Arena, servie en local, le vrai Chrome 156
    avec interface donne 0 ou 50 selon les passages (campagnes 96 et 97), les témoins sans interface 0, comme lui.
    """

    name = "connection-dynamic"
    version = "1.1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        cd = p.get("connection_dynamic") or {}
        signaux: list[Signal] = []

        if not cd.get("available"):
            return _indetermine(self.name, self.version, "api_absente", "NetworkInformation non disponible")

        if cd.get("rtt_type") != "number":
            signaux.append(Signal("rtt_non_number", f"rtt type={cd.get('rtt_type')}", 0.5))
        if cd.get("downlink_type") != "number":
            signaux.append(Signal("downlink_non_number", f"downlink type={cd.get('downlink_type')}", 0.5))

        rtt = cd.get("rtt_1")
        if isinstance(rtt, (int, float)) and rtt > 500:
            signaux.append(Signal("rtt_anormal", f"rtt={rtt} (> 500ms, suspect)", 0.3))

        return _verdict(self.name, self.version, signaux)


class DetecteurProxyUAData:
    """Détection de Proxy sur navigator.userAgentData.

    Un Proxy sur NavigatorUAData est détectable via :
    - Object.prototype.toString.call() ≠ "[object NavigatorUAData]"
    - instanceof NavigatorUAData ≠ true
    - Symbol.toStringTag absent ou différent
    """

    name = "proxy-uadata"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        ua = p.get("uadata_integrity") or {}
        signaux: list[Signal] = []

        if not ua:
            return _indetermine(self.name, self.version, "non_collecte", "données intégrité UA non collectées")

        if ua.get("toString") and "NavigatorUAData" not in str(ua.get("toString", "")):
            signaux.append(
                Signal(
                    "toString_proxy",
                    f"toString retourne {ua['toString']!r} au lieu de [object NavigatorUAData]",
                    0.75,
                )
            )

        if ua.get("instanceof") is False:
            signaux.append(Signal("instanceof_proxy", "userAgentData instanceof NavigatorUAData = false", 0.75))

        if ua.get("toStringTag") and ua["toStringTag"] != "NavigatorUAData":
            signaux.append(
                Signal(
                    "toStringTag_proxy",
                    f"Symbol.toStringTag = {ua['toStringTag']!r}",
                    0.5,
                )
            )

        return _verdict(self.name, self.version, signaux)


class DetecteurEnumerableProps:
    """Vérifie que les propriétés navigator/screen ont les bons flags enumerable.

    Les patches maladroits oublient souvent enumerable:true sur les getters,
    ce qui les rend invisibles à for..in et Object.keys.
    """

    name = "enumerable-props"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        ep = p.get("enumerable_props") or {}
        signaux: list[Signal] = []

        if not ep:
            return _indetermine(self.name, self.version, "non_collecte", "données enumerable non collectées")

        for prop, is_enum in ep.items():
            if is_enum is False:
                signaux.append(
                    Signal(
                        f"{prop}_non_enum",
                        f"{prop} n'est pas enumerable (patch visible)",
                        0.3,
                    )
                )

        return _verdict(self.name, self.version, signaux)


class DetecteurAudioContext:
    """Empreinte AudioContext : détecte l'absence d'audio (headless), le patching et la randomisation."""

    name = "audio-context"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        ac = p.get("audio_context") or {}
        signaux: list[Signal] = []

        if not ac:
            return _indetermine(self.name, self.version, "non_collecte", "données AudioContext non collectées")

        if ac.get("available") is False:
            signaux.append(Signal("no_audio_api", "OfflineAudioContext indisponible", 0.3))
        if ac.get("constructor_natif") is False:
            signaux.append(Signal("constructor_patche", "OfflineAudioContext.constructor patchée", 0.75))
        if ac.get("startRendering_natif") is False:
            signaux.append(Signal("startRendering_patche", "startRendering patchée", 0.75))
        if ac.get("createOscillator_natif") is False:
            signaux.append(Signal("createOscillator_patche", "createOscillator patchée", 0.5))
        if ac.get("nonzero") is False:
            signaux.append(Signal("audio_zeros", "rendu audio nul (headless sans carte son)", 0.5))
        if ac.get("stable") is False:
            signaux.append(Signal("audio_instable", "hash audio instable entre deux rendus (randomisation)", 0.8))

        return _verdict(self.name, self.version, signaux)


class DetecteurPolices:
    """Empreinte des polices installées : cohérence avec l'OS déclaré et nombre minimal.

    V1.1 (12/11/2026) : `polices_os_manquantes` ne juge qu'un relevé fait contre plusieurs familles de référence
    (`bases`). Comparée au seul `monospace`, la police à chasse fixe par défaut du navigateur paraît absente : Menlo
    dans le vrai Chrome 156 sous macOS (campagnes 96 et 97, tous les relevés), Courier New dans le Chromium sans
    interface des témoins. L'observateur compare désormais à `monospace`, `sans-serif` et `serif`.
    """

    name = "polices"
    version = "1.1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        fp = p.get("font_fingerprint") or {}
        signaux: list[Signal] = []

        if not fp:
            return _indetermine(self.name, self.version, "non_collecte", "données polices non collectées")

        count = fp.get("count", 0)
        if count < 3:
            signaux.append(Signal("tres_peu_polices", f"seulement {count} polices détectées (headless)", 0.5))

        manquantes = fp.get("os_manquantes") or []
        # Un relevé sans `bases` (d'avant le 12/11/2026) ne voit pas la police à chasse fixe par défaut : il ne prouve
        # aucune absence. Une police vue, elle, est là quelle que soit la référence (`os_inattendues` reste jugé).
        if manquantes and len(fp.get("bases") or []) >= 2:
            signaux.append(
                Signal(
                    "polices_os_manquantes",
                    f"polices attendues pour {fp.get('os_declare', '?')} absentes : {', '.join(manquantes)}",
                    0.5,
                )
            )
        inattendues = fp.get("os_inattendues") or []
        if inattendues:
            signaux.append(
                Signal(
                    "polices_os_inattendues",
                    f"polices d'un autre OS présentes : {', '.join(inattendues)}",
                    0.5,
                )
            )

        return _verdict(self.name, self.version, signaux)


class DetecteurMathConstants:
    """Vérifie que les fonctions Math sont natives (non patchées)."""

    name = "math-constants"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        mc = p.get("math_constants") or {}
        signaux: list[Signal] = []

        if not mc:
            return _indetermine(self.name, self.version, "non_collecte", "données Math non collectées")

        if mc.get("cos_natif") is False:
            signaux.append(Signal("cos_patche", "Math.cos patchée", 0.75))
        if mc.get("tan_natif") is False:
            signaux.append(Signal("tan_patche", "Math.tan patchée", 0.75))
        if mc.get("random_natif") is False:
            signaux.append(Signal("random_patche", "Math.random patchée", 0.5))

        return _verdict(self.name, self.version, signaux)


class DetecteurDOMRect:
    """Empreinte DOMRect : patching de getBoundingClientRect, stabilité, sous-pixel."""

    name = "domrect"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        dr = p.get("domrect_fingerprint") or {}
        signaux: list[Signal] = []

        if not dr:
            return _indetermine(self.name, self.version, "non_collecte", "données DOMRect non collectées")

        if dr.get("getBCR_natif") is False:
            signaux.append(Signal("getBCR_patche", "getBoundingClientRect patchée", 0.75))
        if dr.get("stable") is False:
            signaux.append(Signal("domrect_instable", "DOMRect instable entre deux appels (randomisation)", 0.8))

        return _verdict(self.name, self.version, signaux)


class DetecteurIframeConsistency:
    """Cohérence entre le thread principal et une iframe : patches non propagés."""

    name = "iframe-consistency"
    version = "1"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        it = p.get("iframe_test") or {}
        signaux: list[Signal] = []

        if not it:
            return _indetermine(self.name, self.version, "non_collecte", "données iframe non collectées")

        if it.get("access") is False:
            return _indetermine(self.name, self.version, "no_access", "impossible d'accéder à l'iframe")

        if it.get("ua_match") is False:
            signaux.append(Signal("iframe_ua_diff", "userAgent diffère dans l'iframe", 0.6))
        if it.get("platform_match") is False:
            signaux.append(Signal("iframe_platform_diff", "platform diffère dans l'iframe", 0.6))
        if it.get("hwc_match") is False:
            signaux.append(Signal("iframe_hwc_diff", "hardwareConcurrency diffère dans l'iframe", 0.7))
        if it.get("webdriver_match") is False:
            signaux.append(Signal("iframe_webdriver_diff", "webdriver diffère dans l'iframe", 0.7))
        if it.get("chrome_match") is False:
            signaux.append(Signal("iframe_chrome_diff", "window.chrome diffère dans l'iframe", 0.6))
        if it.get("own_keys_match") is False:
            signaux.append(Signal("iframe_own_keys_diff", "propriétés propres de navigator diffèrent", 0.8))
        if it.get("screen_match") is False:
            signaux.append(Signal("iframe_screen_diff", "screen dimensions diffèrent dans l'iframe", 0.5))
        if it.get("math_tan_match") is False:
            signaux.append(Signal("iframe_math_diff", "Math.tan diffère dans l'iframe (patch non propagé)", 0.9))

        return _verdict(self.name, self.version, signaux)


class DetecteurCDP:
    """Détection d'artefacts Chrome DevTools Protocol (Playwright, Puppeteer, etc.).

    Exploite les données collectées par cdpDetectionTest() dans observateur.js :
    - Runtime.evaluate ou bindings CDP dans la pile d'une erreur
    - Ressources CDP dans les performance entries
    - Scripts vides injectés (addScriptToEvaluateOnNewDocument)
    - console.log patchée par les bindings CDP

    V2 (12/11/2026) : retrait de `debugger_instant` et `no_first_input`, que tout navigateur déclenche
    (outils de développement fermés, relevé fait avant le premier clic) ; la V1 classait humains et moteurs
    à l'identique. L'absence d'interaction reste jugée par `comportement`, en fin de page.
    """

    name = "cdp"
    version = "2"

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        cdp = p.get("cdp_detection") or {}
        signaux: list[Signal] = []

        if not cdp:
            return _indetermine(self.name, self.version, "non_collecte", "données CDP non collectées")

        if cdp.get("stack_has_evaluate"):
            signaux.append(Signal("cdp_evaluate", "Runtime.evaluate dans la stack trace", 1.0))
        if cdp.get("stack_has_cdp_session"):
            signaux.append(Signal("cdp_session", "bindings CDP dans la stack trace", 1.0))

        if (cdp.get("cdp_resource_entries") or 0) > 0:
            signaux.append(Signal("cdp_resources", f"{cdp['cdp_resource_entries']} ressource(s) CDP/DevTools", 0.8))

        empty_scripts = cdp.get("empty_script_tags", 0)
        if empty_scripts > 0:
            signaux.append(
                Signal(
                    "scripts_injectes",
                    f"{empty_scripts} script(s) vide(s) injectés (addScriptToEvaluateOnNewDocument)",
                    0.5,
                )
            )

        if cdp.get("console_log_natif") is False:
            signaux.append(Signal("console_patche", "console.log patchée (bindings CDP)", 0.5))

        return _verdict(self.name, self.version, signaux)


class DetecteurDeepProxy:
    """Détection de Proxy sur les getters natifs du navigateur (toString, illegal invocation, descripteurs)."""

    name = "deep-proxy"
    version = "1"

    _GETTERS = ("hwc", "ua", "wd", "platform", "dm", "screen_w")

    def classer(self, obs: Observations) -> Classement:
        if not obs.attend_js:
            return _indetermine(self.name, self.version, "sans_page", "scénario sans page HTML")
        p = obs.empreinte_js
        if p is None:
            return _indetermine(self.name, self.version, "non_execute", "JavaScript non exécuté")
        dp = p.get("deep_proxy") or {}
        signaux: list[Signal] = []

        if not dp:
            return _indetermine(self.name, self.version, "non_collecte", "données deep proxy non collectées")

        non_natifs = [g for g in self._GETTERS if dp.get(f"{g}_natif") is False]
        if non_natifs:
            signaux.append(
                Signal(
                    "getter_non_natif",
                    f"toString non natif sur : {', '.join(non_natifs)}",
                    0.8,
                )
            )

        pas_invoc = [g for g in self._GETTERS if dp.get(f"{g}_illegal_invoc") is False]
        if pas_invoc:
            signaux.append(
                Signal(
                    "illegal_invoc_absent",
                    f"pas d'illegal invocation sur : {', '.join(pas_invoc)}",
                    0.7,
                )
            )

        desc_diff = [g for g in self._GETTERS if dp.get(f"{g}_desc_match") is False]
        if desc_diff:
            signaux.append(
                Signal(
                    "descripteur_mismatch",
                    f"Object/Reflect descripteur diverge sur : {', '.join(desc_diff)}",
                    0.6,
                )
            )

        if dp.get("navigator_proto") is False:
            signaux.append(Signal("proto_chain_casse", "chaîne prototype navigator altérée", 0.7))
        if dp.get("navigator_constructor") is False:
            signaux.append(Signal("constructor_casse", "navigator.constructor altéré", 0.5))
        if dp.get("toString_natif") is False:
            signaux.append(Signal("toString_patche", "Function.prototype.toString patchée", 0.9))
        if dp.get("error_has_proxy") is True:
            signaux.append(Signal("proxy_dans_stack", "mot 'Proxy' dans la pile d'erreur", 0.8))

        return _verdict(self.name, self.version, signaux)


class DetecteurMetaComposite:
    """Méta-détecteur : repère les sessions où TROP de détecteurs retournent « humain »
    avec zéro signal. Un humain réel déclenche toujours quelques faux positifs
    (timing, canvas, scroll, etc.). Une session parfaitement propre est en soi suspecte.

    Ce détecteur ne s'exécute PAS comme les autres (il a besoin des résultats des
    autres). Il est appelé séparément par le pipeline de classification.
    """

    name = "meta-composite"
    version = "1"

    # Détecteurs dont le résultat est analysé (ceux qui ont une chance de générer
    # un signal chez un humain normal)
    _DETECTEURS_PERTINENTS = {
        "comportement",
        "scroll",
        "canvas-empreinte",
        "canvas-consistency",
        "raf-timing",
        "paint-timing",
        "timing-precision",
        "worker-consistency",
        "entropie-interaction",
        "audio-context",
        "polices",
        "math-constants",
        "domrect",
        "cdp",
        "coherence",
        "coherence-profonde",
    }

    def classer_depuis_resultats(self, resultats: list[Classement]) -> Classement:
        """Analyse les résultats des autres détecteurs pour détecter une session trop propre."""
        signaux: list[Signal] = []

        pertinents = [r for r in resultats if r.detector_name in self._DETECTEURS_PERTINENTS]
        if len(pertinents) < 5:
            return _indetermine(self.name, self.version, "trop_peu", "moins de 5 détecteurs pertinents actifs")

        humain_zero = [r for r in pertinents if r.classification == "humain" and len(r.signals) == 0]
        ratio_propre = len(humain_zero) / len(pertinents)

        if ratio_propre >= 0.95:
            signaux.append(
                Signal(
                    "session_parfaite",
                    f"{len(humain_zero)}/{len(pertinents)} détecteurs sans aucun signal ({ratio_propre:.0%})",
                    0.8,
                )
            )
        elif ratio_propre >= 0.80:
            signaux.append(
                Signal(
                    "session_tres_propre",
                    f"{len(humain_zero)}/{len(pertinents)} détecteurs sans signal ({ratio_propre:.0%})",
                    0.5,
                )
            )

        # Aucun détecteur n'a classé "indetermine" ou "automatise" → encore plus suspect
        aucun_doute = all(r.classification == "humain" for r in resultats if r.detector_name != self.name)
        if aucun_doute and len(resultats) >= 15:
            signaux.append(
                Signal(
                    "unanimite_humain",
                    f"les {len(resultats)} détecteurs disent humain — aucun doute nulle part",
                    0.6,
                )
            )

        return _verdict(self.name, self.version, signaux)


class DetecteurCorrelationSession:
    """Même profil ou même canvas vu dans plusieurs sessions de la base (`correlation.py`).

    Compte des sessions (jetons), pas des visiteurs : un humain qui revient avec le même navigateur compte autant
    de fois qu'il revient.
    V1.1 (12/11/2026) : un fait, un signal — un seul signal de comptage, sur le plus grand des deux comptes
    (profil, canvas), au lieu d'un signal chacun pour la même observation ; de même pour le débit. Libellés
    conformes à ce qui est compté (« rotation de fingerprint massive » désignait une empreinte stable revue).
    Débit compté sur les 60 dernières minutes au lieu d'une moyenne sur toute la vie du hash, aveugle sous une
    minute et à 40 par heure pour deux sessions à 3 minutes d'écart. Seuils et poids inchangés.
    """

    name = "correlation-session"
    version = "1.1"

    NOMS = {"profil_complet": "profil", "canvas": "canvas"}  # types de `correlation.hash_session`
    SEUIL_SESSIONS = 5
    SEUIL_RAPIDE = 10
    SEUIL_DEBIT = 30  # sessions commencées dans les 60 dernières minutes

    def classer(self, obs: Observations) -> Classement:
        if obs.correlation is None:
            return _indetermine(self.name, self.version, "pas_de_correlation", "données cross-session absentes")
        signaux: list[Signal] = []
        comptes = {t: d.get("nb_sessions", 1) for t, d in obs.correlation.items()}
        nb = max(comptes.values(), default=0)
        if nb >= self.SEUIL_SESSIONS:
            seuil, poids = (self.SEUIL_RAPIDE, 1.0) if nb >= self.SEUIL_RAPIDE else (self.SEUIL_SESSIONS, 0.7)
            franchis = [(t, n) for t, n in comptes.items() if n >= seuil]
            vus = " et ".join(f"{self.NOMS.get(t, t)} vu dans {n} sessions" for t, n in franchis)
            code = max(franchis, key=lambda f: f[1])[0]  # le plus grand compte ; à égalité, le profil
            signaux.append(Signal(f"recycling_{code}", f"{vus} de la base, celle-ci comprise (seuil {seuil})", poids))
        debits = {t: d.get("sessions_derniere_heure", 0) for t, d in obs.correlation.items()}
        if max(debits.values(), default=0) >= self.SEUIL_DEBIT:
            franchis = [(t, n) for t, n in debits.items() if n >= self.SEUIL_DEBIT]
            parties = " et ".join(
                f"{'' if obs.correlation[t].get('derniere_heure_exacte', False) else 'au moins '}{n} sessions de même"
                f" {self.NOMS.get(t, t)}"
                for t, n in franchis
            )
            code = max(franchis, key=lambda f: f[1])[0]
            signaux.append(
                Signal(
                    f"velocity_{code}",
                    f"{parties} commencées dans les 60 dernières minutes (seuil {self.SEUIL_DEBIT})",
                    0.8,
                )
            )
        return _verdict(self.name, self.version, signaux)


def _requetes_par_seconde(documents: list[dict[str, Any]]) -> float | None:
    if len(documents) < 3:
        return None
    debut = datetime.fromisoformat(documents[0]["received_at"])
    fin = datetime.fromisoformat(documents[-1]["received_at"])
    duree = (fin - debut).total_seconds()
    return (len(documents) - 1) / duree if duree > 0 else None


class DetecteurH2:
    """Analyse de l'empreinte HTTP/2 : SETTINGS, WINDOW_UPDATE, PRIORITY.

    Les navigateurs envoient des valeurs SETTINGS caractéristiques (Akamai h2 fingerprint).
    Chrome : 5 settings {1:65536, 2:0, 3:1000, 4:6291456, 6:262144} + WU ~15M.
    Firefox : 3 settings {1:65536, 4:131072, 5:16384} + WU ~12M.
    Les bibliothèques h2 (Python, Go, curl) ont des profils très différents.
    """

    name = "h2"
    version = "1"

    _CHROME_SETTINGS = {1: 65536, 2: 0, 3: 1000, 4: 6291456, 6: 262144}
    _FIREFOX_SETTINGS = {1: 65536, 4: 131072}

    def classer(self, obs: Observations) -> Classement:
        t = obs.tls
        if t is None:
            return _indetermine(self.name, self.version, "sans_tls", "session hors Arena")
        h2 = t.get("h2")
        if h2 is None:
            return _indetermine(self.name, self.version, "sans_h2", "pas de données HTTP/2 (client h1.1)")

        documents = obs.documents
        ua = _entetes(documents[0]).get("user-agent", "").lower() if documents else ""
        chrome = "chrome/" in ua and "edg/" not in ua
        edge = "edg/" in ua
        firefox = "firefox/" in ua
        navigateur = chrome or edge or firefox or ("safari/" in ua and "chrome/" not in ua)

        settings = h2.get("settings", [])
        window_update = h2.get("window_update")
        settings_dict = {s[0]: s[1] for s in settings} if settings else {}
        nb_settings = len(settings)

        signaux: list[Signal] = []

        # ── Nombre de SETTINGS ──
        if nb_settings == 0:
            signaux.append(Signal("h2_pas_de_settings", "aucun SETTINGS envoyé (navigateurs : 3-5)", 0.5))
        elif navigateur and nb_settings < 2:
            signaux.append(
                Signal(
                    "h2_peu_de_settings",
                    f"seulement {nb_settings} SETTINGS (Chrome : 5, Firefox : 2+)",
                    0.4,
                )
            )

        # ── INITIAL_WINDOW_SIZE (setting 4) ──
        iws = settings_dict.get(4)
        if iws is not None:
            if (chrome or edge) and iws != 6291456:
                signaux.append(
                    Signal(
                        "h2_chrome_iws",
                        f"Chrome annoncé avec INITIAL_WINDOW_SIZE={iws} (attendu : 6291456)",
                        0.5,
                    )
                )
            elif firefox and iws != 131072:
                signaux.append(
                    Signal(
                        "h2_firefox_iws",
                        f"Firefox annoncé avec INITIAL_WINDOW_SIZE={iws} (attendu : 131072)",
                        0.4,
                    )
                )

        # ── ENABLE_PUSH (setting 2) ──
        enable_push = settings_dict.get(2)
        if (chrome or edge) and enable_push is None:
            signaux.append(
                Signal(
                    "h2_chrome_sans_push",
                    "Chrome annoncé sans ENABLE_PUSH=0 dans SETTINGS",
                    0.3,
                )
            )

        # ── MAX_CONCURRENT_STREAMS (setting 3) ──
        mcs = settings_dict.get(3)
        if (chrome or edge) and mcs is not None and mcs != 1000:
            signaux.append(
                Signal(
                    "h2_chrome_mcs",
                    f"Chrome annoncé avec MAX_CONCURRENT_STREAMS={mcs} (attendu : 1000)",
                    0.3,
                )
            )

        # ── WINDOW_UPDATE (connexion) ──
        if window_update is not None:
            if (chrome or edge) and abs(window_update - 15663105) > 100000:
                signaux.append(
                    Signal(
                        "h2_chrome_wu",
                        f"Chrome annoncé avec WINDOW_UPDATE={window_update} (attendu : ~15663105)",
                        0.4,
                    )
                )
            elif firefox and abs(window_update - 12517377) > 100000:
                signaux.append(
                    Signal(
                        "h2_firefox_wu",
                        f"Firefox annoncé avec WINDOW_UPDATE={window_update} (attendu : ~12517377)",
                        0.3,
                    )
                )
        elif navigateur:
            signaux.append(
                Signal(
                    "h2_sans_wu",
                    "navigateur annoncé sans WINDOW_UPDATE au niveau connexion",
                    0.4,
                )
            )

        # ── Profil de bibliothèque pure ──
        if nb_settings <= 1 and window_update is None and not navigateur:
            signaux.append(
                Signal(
                    "h2_pile_minimale",
                    f"profil HTTP/2 minimal ({nb_settings} SETTINGS, pas de WU) : bibliothèque",
                    0.5,
                )
            )

        # ── HEADER_TABLE_SIZE (setting 1) ──
        hts = settings_dict.get(1)
        if navigateur and hts is not None and hts != 65536:
            signaux.append(
                Signal(
                    "h2_hts_inattendu",
                    f"HEADER_TABLE_SIZE={hts} (navigateurs : 65536)",
                    0.3,
                )
            )

        return _verdict(self.name, self.version, signaux)


DETECTEURS: dict[str, Detecteur] = {
    d.name: d
    for d in (
        DetecteurBotD(),
        DetecteurReglesHttp(),
        DetecteurReglesJs(),
        DetecteurCoherence(),
        DetecteurTls(),
        DetecteurH2(),
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
        DetecteurWorkerConsistency(),
        DetecteurConnectionDynamic(),
        DetecteurProxyUAData(),
        DetecteurEnumerableProps(),
        DetecteurAudioContext(),
        DetecteurPolices(),
        DetecteurMathConstants(),
        DetecteurDOMRect(),
        DetecteurIframeConsistency(),
        DetecteurDeepProxy(),
        DetecteurCDP(),
        DetecteurCorrelationSession(),
    )
}


def registre() -> dict[str, Detecteur]:
    """Détecteurs intégrés, plus ceux d'un paquet externe (point d'entrée `shadowlab.detectors`)."""
    detecteurs = dict(DETECTEURS)
    for point in entry_points(group="shadowlab.detectors"):
        detecteurs.setdefault(point.name, point.load()())
    return detecteurs


_META_COMPOSITE = DetecteurMetaComposite()


def classer(obs: Observations, noms: list[str] | None = None) -> list[Classement]:
    tous = registre()
    resultats = [tous[nom].classer(obs) for nom in (noms or list(tous))]
    # Le méta-détecteur analyse les résultats des autres détecteurs
    if noms is None or "meta-composite" in (noms or []):
        resultats.append(_META_COMPOSITE.classer_depuis_resultats(resultats))
    return resultats


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
