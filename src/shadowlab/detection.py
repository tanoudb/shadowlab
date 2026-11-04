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
    version = "1"

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
