"""Fabrique de l'application publique : site vitrine, réseau social fictif, sessions humaines consenties et collecte.
Rien d'autre.

Ni l'API du laboratoire, ni /labo, ni /tableau, ni le gardien, le frontal, les détecteurs ou les moteurs :
ils ne sont même pas importés. Toute route qui n'est pas déclarée ici répond 404. Voir docs/site-public.md.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import re
import secrets
import sqlite3
import sys
import time
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response

from ..arena import secret as signature
from ..config import ReglagesPublics
from ..site import vitrine
from . import donnees, messages, pages, social
from .textes import LANGUES

STATIQUES = Path(__file__).resolve().parents[1] / "site" / "static"
# Liste fermée : rien d'autre du dossier statique du laboratoire n'est servi.
FICHIERS_STATIQUES = {
    "observateur.js": "text/javascript",
    "vendor/botd-2.0.0.esm.js": "text/javascript",
    "vitrine.css": "text/css",
    "vitrine.js": "text/javascript",
}
# Fichiers propres à l'application publique (pages de l'étude, réseau social), servis sous /public/static/ : liste
# fermée aussi.
STATIQUES_PUBLICS = Path(__file__).resolve().parent / "static"
FICHIERS_PUBLICS = {"public.css": "text/css", "social.css": "text/css", "social.js": "text/javascript"}
PREFIXE_LANGUE = re.compile(r"/(fr|en)(?:/|$)")  # « /fr », « /en/information » ; pas « /english »
CSP = (
    "default-src 'self'; script-src 'self'; worker-src 'self' blob:; connect-src 'self'; img-src 'self' data:; "
    "style-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)
SIGNATURE = re.compile(r"[0-9a-f]{64}")
HOTE = re.compile(r"(?P<nom>[a-z0-9.-]+|\[[0-9a-f:.]+\])(?::[0-9]{1,5})?")  # nom[:port], rien d'autre
TAILLE_FORMULAIRE = 4096
OCTETS_PAR_CARACTERE = 12  # un caractère de 4 octets, une fois encodé dans un formulaire (%F0%9F…)
PROFONDEUR_MAX = 32  # imbrication d'un envoi ; 5 au plus sur les 3000 derniers envois du labo (12/11/2026)
UNE_JOURNEE_S = 24 * 3600
# Journal tournant : 5 Mio par fichier, le courant et 3 anciens, donc 20 Mio au plus en tout.
ROTATION_JOURNAL = (5 * 1024 * 1024, 3)
# Le journal ne garde que les réponses d'erreur (code 400 ou plus) : une requête réussie ou redirigée n'écrit rien.
# Même parmi les erreurs, jamais les pages de contact (feuille de style comprise, servie sous /contact/) ni ce que
# le navigateur charge avec une page (fichiers statiques, icône) : horodatées à la milliseconde, rapprochées des
# requêtes notées d'une session, ces lignes dateraient un message, que D-57 ne garde qu'au jour.
NON_JOURNALISES = ("/contact", "/lab/static/", "/public/static/", "/favicon.ico")
journal = logging.getLogger("shadowlab.public")


def langue_de(request: Request) -> str:
    """Langue d'une page, dans l'ordre du cadrage du 13/11/2026 (« Langue ») : le préfixe de l'adresse (`/fr`, `/en`) ;
    sinon la langue notée avec l'accord de la session en cours (`request.state.langue_session`, posée par la garde) ;
    sinon la langue préférée d'`Accept-Language` parmi `LANGUES` ; sinon le français. Aucun cookie de plus."""
    prefixe = PREFIXE_LANGUE.match(getattr(getattr(request, "url", None), "path", "") or "")
    if prefixe:
        return prefixe.group(1)
    session = getattr(getattr(request, "state", None), "langue_session", None)
    if session in LANGUES:
        return session
    choix: list[tuple[float, int, str]] = []
    for rang, morceau in enumerate(request.headers.get("accept-language", "").split(",")):
        etiquette, *parametres = (p.strip() for p in morceau.split(";"))
        langue = etiquette.lower().split("-")[0]
        poids = 1.0
        for parametre in parametres:
            cle, _, valeur = parametre.partition("=")
            if cle.strip().lower() == "q":
                try:
                    poids = float(valeur)
                except ValueError:
                    poids = 0.0
        if langue in LANGUES and poids > 0:
            choix.append((-poids, rang, langue))
    return min(choix)[2] if choix else "fr"


@dataclass(frozen=True)
class Limites:
    """Bornes qui protègent le disque et la vie privée. Les valeurs par défaut suffisent pour une dizaine
    de participants ; un humain qui parcourt 100 pages reste loin des quotas d'une session."""

    sessions_par_adresse: int = 6  # ouvertures par heure glissante et par adresse (en mémoire seulement)
    # Ouvertures par jour UTC, toutes adresses confondues. En service, le réglage SHADOWLAB_PUBLIC_SESSIONS_PAR_JOUR
    # (`ReglagesPublics.sessions_par_jour`) remplace cette valeur, sauf si des `Limites` sont données (tests).
    sessions_par_jour: int = 40
    envois_par_session: int = 300  # messages de l'observateur (deux par page)
    volume_par_session: int = 4 * 1024 * 1024  # octets de charges JavaScript (~10 Ko par empreinte)
    requetes_par_session: int = 3000  # requêtes HTTP notées (~17 par page, images comprises)
    taille_corps: int = 64 * 1024  # un message de l'observateur
    duree_session_s: int = 2 * 3600  # au-delà, la session n'est plus « en cours »
    taille_max_base: int = 2 * 1024**3  # au-delà, plus aucune session ne s'ouvre et plus rien ne s'écrit
    messages_par_adresse: int = 3  # messages de contact par heure glissante et par adresse (en mémoire seulement)
    # Par 24 h glissantes et par adresse (en mémoire) : un visiteur écrit une ou deux fois. Une adresse seule
    # n'épuise plus le plafond du jour (30), ni la boîte avant la purge (5 × 90 jours = 450 < 500).
    messages_par_adresse_jour: int = 5
    messages_par_jour: int = 30  # messages de contact par jour UTC, toutes adresses confondues
    messages_gardes: int = 500  # au-delà, le formulaire refuse jusqu'à la purge (8 Ko au pire par message)
    taille_message: int = 2000  # caractères d'un message de contact


def bloc_d_adresse(adresse: str) -> str:
    """Ce que comptent les limites par adresse. Une adresse IPv6 compte pour son bloc /64 : un abonné en reçoit au
    moins un entier et y change d'adresse à volonté. Une adresse IPv4, même écrite en IPv6 (`::ffff:a.b.c.d`),
    reste elle-même ; une valeur qui n'est pas une adresse reste telle quelle."""
    try:
        ip = ipaddress.ip_address(adresse)
    except ValueError:
        return adresse
    if isinstance(ip, ipaddress.IPv4Address):
        return adresse
    if ip.ipv4_mapped is not None:
        return str(ip.ipv4_mapped)
    return f"{ipaddress.IPv6Address(int(ip) >> 64 << 64)}/64"  # par l'entier : sans la zone (%eth0) éventuelle


class Limiteur:
    """Actions par adresse (ouvertures de session, messages) sur une fenêtre glissante, une heure par défaut.

    L'adresse n'est jamais écrite : elle n'existe qu'en mémoire, sous forme d'empreinte salée par un sel tiré
    au démarrage, et disparaît au redémarrage. Une adresse IPv6 compte pour son /64 (`bloc_d_adresse`).

    Un balayage (`balayer`), au plus une fois par minute, retire toute empreinte dont la dernière action est sortie
    de la fenêtre. Il a lieu à chaque appel et à chaque requête reçue par l'application (`preparer`) : une empreinte
    quitte la mémoire à la première requête qui suit la fin de sa fenêtre. Elle est salée, mais une adresse IPv4 se
    retrouve par essais à qui lirait la mémoire du processus : elle n'est pas dite « non réversible ».

    Table pleine d'empreintes encore valides, rien n'est effacé : une adresse inconnue est refusée, les adresses
    déjà connues gardent leur compte.
    """

    ADRESSES_MAX = 10_000
    BALAYAGE_S = 60

    def __init__(self, maximum: int, fenetre_s: int = 3600, horloge: Callable[[], float] = time.monotonic) -> None:
        self.maximum = maximum
        self.fenetre_s = fenetre_s
        self._horloge = horloge
        self._sel = secrets.token_bytes(16)
        self._vues: dict[bytes, deque[float]] = {}
        self._dernier_balayage = horloge()

    def balayer(self) -> None:
        maintenant = self._horloge()
        if maintenant - self._dernier_balayage < self.BALAYAGE_S:
            return
        self._dernier_balayage = maintenant
        self._vues = {c: v for c, v in self._vues.items() if v and maintenant - v[-1] < self.fenetre_s}

    def autoriser(self, adresse: str) -> bool:
        maintenant = self._horloge()
        self.balayer()
        cle = hashlib.blake2b(bloc_d_adresse(adresse).encode(), key=self._sel, digest_size=16).digest()
        vues = self._vues.get(cle)
        if vues is None:
            if len(self._vues) >= self.ADRESSES_MAX:  # table pleine d'entrées valides : l'inconnue attend le balayage
                return False
            vues = self._vues[cle] = deque()
        while vues and maintenant - vues[0] >= self.fenetre_s:
            vues.popleft()
        if len(vues) >= self.maximum:
            return False
        vues.append(maintenant)
        return True


def _verifier_reglages(reglages: ReglagesPublics) -> None:
    if not reglages.contact.strip():
        raise ValueError(
            "SHADOWLAB_PUBLIC_CONTACT est vide : la page d'information doit donner le contact du responsable."
        )
    if not reglages.hotes or any("*" in h or not h for h in reglages.hotes):
        raise ValueError("SHADOWLAB_PUBLIC_HOTES doit lister des noms d'hôte exacts, sans « * ».")
    if reglages.conservation_jours < 1:
        raise ValueError("SHADOWLAB_PUBLIC_CONSERVATION_JOURS : la durée de conservation doit valoir au moins 1.")


def _nettoyer(chemin: str) -> str:
    """Chemin lisible et borné pour le journal (jamais la chaîne de requête)."""
    return "".join(c if c.isprintable() and c != " " else "?" for c in chemin[:120])


def _avis_au_responsable(texte: str) -> None:
    """Une ligne à l'écran du responsable, jamais dans le journal. Seulement si la sortie standard est un
    terminal : recueillie (journald sous systemd, fichier), sa ligne horodatée daterait ce qu'elle annonce."""
    with suppress(OSError, ValueError):  # sortie absente ou fermée : l'avis n'est qu'une commodité
        if sys.stdout is not None and sys.stdout.isatty():
            print(texte, flush=True)


def _trop_profond(valeur: object, maximum: int = PROFONDEUR_MAX) -> bool:
    """Imbrication de listes et d'objets au-delà de `maximum`, mesurée sans récursion."""
    pile = [(valeur, 1)]
    while pile:
        element, profondeur = pile.pop()
        enfants = element.values() if isinstance(element, dict) else element if isinstance(element, list) else None
        if enfants is None:
            continue
        if profondeur > maximum:
            return True
        pile.extend((enfant, profondeur + 1) for enfant in enfants)
    return False


def creer_app_publique(reglages: ReglagesPublics, limites: Limites | None = None) -> FastAPI:
    _verifier_reglages(reglages)
    limites = limites or Limites(sessions_par_jour=reglages.sessions_par_jour)
    messages.chemin(reglages.base_donnees)  # refuse une base qui porterait le nom du fichier des messages
    cx = donnees.ouvrir(reglages.base_donnees)  # refuse la base du laboratoire
    try:
        donnees.purger(cx, reglages.conservation_jours)
    finally:
        cx.close()
    secret = signature.charger(reglages.base_donnees.parent)
    hotes = frozenset(reglages.hotes)
    schemas = {"https"} if reglages.https else {"https", "http"}
    prefixe = "__Host-" if reglages.https else ""  # le préfixe interdit à un sous-domaine d'écraser le cookie
    cookie_session, cookie_csrf = f"{prefixe}slp-session", f"{prefixe}slp-csrf"
    cookie_droits = f"{prefixe}slp-droits"  # retrouver et supprimer sa session, dans ce navigateur
    limiteur = Limiteur(limites.sessions_par_adresse)
    limiteur_messages = Limiteur(limites.messages_par_adresse)
    limiteur_messages_jour = Limiteur(limites.messages_par_adresse_jour, fenetre_s=UNE_JOURNEE_S)
    limiteurs = (limiteur, limiteur_messages, limiteur_messages_jour)
    fichier_messages = messages.chemin(reglages.base_donnees)
    taille_formulaire_contact = limites.taille_message * OCTETS_PAR_CARACTERE + 1024
    annonces = vitrine.generer(reglages.vitrine_graine, reglages.vitrine_taille)
    dossier_photos = social.DOSSIER_PHOTOS
    photos = social.charger_photos(dossier_photos)  # refuse un manifeste illisible, vide ou incomplet
    fichiers_photos = social.fichiers(photos)
    univers = social.generer(reglages.social_graine, reglages.social_taille, photos)
    derniere_purge = [time.monotonic()]

    # Sans redirection sur barre oblique finale : elle serait construite en http:// derrière le mandataire.
    app = FastAPI(title="Habitat Démo", docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False)
    app.state.reglages = reglages
    app.state.limiteurs = limiteurs

    @contextmanager
    def base() -> Iterator[sqlite3.Connection]:
        cx = donnees.connexion(reglages.base_donnees)
        try:
            yield cx
        finally:
            cx.close()

    @contextmanager
    def boite() -> Iterator[sqlite3.Connection]:
        """Messages du formulaire de contact : un fichier à part de la base des sessions."""
        cx = messages.connexion(fichier_messages)
        try:
            yield cx
        finally:
            cx.close()

    with boite() as cx:
        messages.purger(cx, reglages.conservation_jours)

    # --- Outils ------------------------------------------------------------------------------------

    def poser(reponse: Response, nom: str, valeur: str, max_age: int | None = None) -> None:
        reponse.set_cookie(nom, valeur, max_age=max_age, path="/", secure=reglages.https, httponly=True, samesite="lax")

    def effacer(reponse: Response, nom: str) -> None:
        reponse.delete_cookie(nom, path="/", secure=reglages.https, httponly=True, samesite="lax")

    def signer(usage: str, jeton: str) -> str:
        return f"{jeton}.{signature.signer(secret, usage, jeton)}"

    def lire_signe(usage: str, valeur: str) -> str | None:
        jeton, _, sceau = valeur.partition(".")
        if (
            donnees.JETON.fullmatch(jeton)
            and SIGNATURE.fullmatch(sceau)
            and signature.verifier(secret, sceau, usage, jeton)
        ):
            return jeton
        return None

    def session_de(request: Request) -> str | None:
        """Jeton de la session consentie en cours, lu dans le seul cookie signé (jamais dans l'URL)."""
        jeton = lire_signe("session", request.cookies.get(cookie_session, ""))
        if jeton is None:
            return None
        with base() as cx:
            return jeton if donnees.session_en_cours(cx, jeton, limites.duree_session_s) else None

    entete_absent_signale = [False]

    def adresse_de(request: Request) -> str:
        """Adresse du visiteur, pour la limite en mémoire : dernière valeur de l'en-tête du mandataire. En-tête
        configuré mais absent : repli sur la connexion (celle du mandataire), donc une limite partagée par tous ;
        un avertissement, une fois par démarrage, sans adresse."""
        if reglages.entete_ip:
            derniere = request.headers.get(reglages.entete_ip, "").split(",")[-1].strip()
            if derniere:
                return derniere
            if not entete_absent_signale[0]:
                entete_absent_signale[0] = True
                journal.warning(
                    "En-tête d'adresse « %s » absent d'une requête : les limites par adresse deviennent communes "
                    "à tous les visiteurs. Vérifier SHADOWLAB_PUBLIC_ENTETE_IP et le mandataire.",
                    _nettoyer(reglages.entete_ip),
                )
        return request.client.host if request.client else ""

    def meme_origine(request: Request) -> bool:
        origine = request.headers.get("origin")
        if origine is None:  # navigateur ancien : on se fie à Sec-Fetch-Site s'il est là
            return request.headers.get("sec-fetch-site") in (None, "same-origin")
        try:
            morceaux = urlsplit(origine)
        except ValueError:
            return False
        return morceaux.scheme in schemas and morceaux.netloc.lower() == request.headers.get("host", "").lower()

    async def lire_corps(request: Request, maximum: int) -> bytes | None:
        """Corps de la requête, ou None s'il dépasse `maximum` (annoncé ou réel)."""
        try:
            if int(request.headers.get("content-length", "0")) > maximum:
                return None
        except ValueError:
            return None
        corps = bytearray()
        async for morceau in request.stream():
            corps += morceau
            if len(corps) > maximum:
                return None
        return bytes(corps)

    async def formulaire(request: Request, maximum: int = TAILLE_FORMULAIRE) -> dict[str, str] | None:
        corps = await lire_corps(request, maximum)
        if corps is None:
            return None
        try:
            champs = parse_qs(corps.decode("utf-8", "replace"), max_num_fields=10)
        except ValueError:
            return None
        return {cle: valeurs[0] for cle, valeurs in champs.items()}

    def csrf_valide(request: Request, champs: dict[str, str]) -> bool:
        attendu, recu = request.cookies.get(cookie_csrf, ""), champs.get("csrf", "")
        return bool(donnees.JETON.fullmatch(attendu) and donnees.JETON.fullmatch(recu)) and hmac.compare_digest(
            attendu, recu
        )

    def avec_csrf(request: Request, page: Callable[[str], str], status_code: int = 200) -> HTMLResponse:
        """Page qui porte un formulaire : le jeton anti-CSRF est posé en cookie et recopié dans la page."""
        csrf = request.cookies.get(cookie_csrf, "")
        neuf = not donnees.JETON.fullmatch(csrf)
        if neuf:
            csrf = secrets.token_hex(16)
        reponse = HTMLResponse(page(csrf), status_code=status_code)
        if neuf:
            poser(reponse, cookie_csrf, csrf)
        return reponse

    def refus(status_code: int, cle: str, langue: str, *, contact: bool = False) -> HTMLResponse:
        return HTMLResponse(pages.erreur(cle, langue, contact=contact), status_code=status_code)

    def plein() -> bool:
        """Base au plafond : plus rien ne s'y écrit, même pour une session déjà ouverte."""
        return donnees.taille(reglages.base_donnees) >= limites.taille_max_base

    def compter(compte: str) -> None:
        """Compte du jour (fréquentation, D-75). Base pleine : rien ne s'écrit. Une panne de la base ne prive personne
        de sa page : le compte est perdu, rien d'autre."""
        if plein():
            return
        with suppress(sqlite3.Error), base() as cx:
            donnees.compter(cx, compte)

    def etat_de_l_accueil(chargement: bool, en_cours: bool) -> tuple[int | None, bool]:
        """En une connexion : compte le chargement de l'accueil (sauf base pleine), lit le total des sessions terminées
        et dit si le plafond du jour est atteint. Base en panne : ni compte ni compteur, et la case d'accord reste
        (l'envoi tranchera)."""
        pleine = plein()
        with suppress(sqlite3.Error), base() as cx:
            if chargement and not pleine:
                donnees.compter(cx, "accueil")
            complet = not en_cours and donnees.sessions_du_jour(cx) >= limites.sessions_par_jour
            return donnees.sessions_terminees(cx), complet
        return None, False

    def total_des_sessions() -> int | None:
        """Sessions terminées depuis le début, pour l'accueil ; None si la base ne répond pas (pas de compteur)."""
        with suppress(sqlite3.Error), base() as cx:
            return donnees.sessions_terminees(cx)
        return None

    # --- Garde : hôte, observation, en-têtes de sécurité, journal ----------------------------------

    def preparer(request: Request) -> None:
        """Ce que la garde lit et écrit en base : purge quotidienne, session du cookie, requête notée. Et le balayage
        des limiteurs : une empreinte d'adresse expirée sort de la mémoire dès la première requête qui suit."""
        for limite_en_memoire in limiteurs:
            limite_en_memoire.balayer()
        if time.monotonic() - derniere_purge[0] > UNE_JOURNEE_S:  # purge quotidienne, même sans tâche planifiée
            derniere_purge[0] = time.monotonic()
            with base() as cx:
                donnees.purger(cx, reglages.conservation_jours)
            with boite() as cx:
                messages.purger(cx, reglages.conservation_jours)
        jeton = session_de(request)
        request.state.session = jeton
        request.state.langue_session = None
        if jeton:
            with base() as cx:
                request.state.langue_session = donnees.langue_de_session(cx, jeton)
        if jeton and request.url.path.startswith("/lab/") and not plein():
            paires = [(n.decode("latin-1"), v.decode("latin-1")) for n, v in request.scope["headers"]]
            entetes = donnees.entetes_gardes(paires, request.headers.get("host", ""))
            with base() as cx:
                donnees.noter_requete(
                    cx,
                    jeton,
                    request.method,
                    request.url.path,
                    request.scope.get("http_version"),
                    entetes,
                    limites.requetes_par_session,
                )

    @app.middleware("http")
    async def garde(request: Request, call_next):
        hote = HOTE.fullmatch(request.headers.get("host", "").lower())
        if hote is None or hote["nom"].strip("[]") not in hotes:
            reponse: Response = PlainTextResponse("hôte non reconnu", status_code=400)
        else:
            try:
                preparer(request)
            except sqlite3.Error:
                reponse = refus(503, "indisponible", langue_de(request))
            else:
                reponse = await call_next(request)
        reponse.headers["Content-Security-Policy"] = CSP
        reponse.headers["X-Content-Type-Options"] = "nosniff"
        # Les pages de contact ne chargent rien sous /lab/ et ne mènent qu'à « / » ou « /contact… » (ni notés en
        # base pendant une session, ni journalisés). Si un lien en sortait quand même, la page suivante ne
        # recevrait que l'origine, sans chemin. Pas `no-referrer` : le navigateur enverrait `Origin: null` au POST
        # du formulaire, que `meme_origine` refuse (403).
        depuis_contact = request.url.path.startswith("/contact")
        reponse.headers["Referrer-Policy"] = "origin" if depuis_contact else "same-origin"
        reponse.headers["X-Frame-Options"] = "DENY"
        reponse.headers.setdefault("Cache-Control", "no-store")
        if reglages.https:
            reponse.headers["Strict-Transport-Security"] = "max-age=31536000"
        # Erreurs seulement (statut 400 ou plus) : ni adresse, ni chaîne de requête (le jeton y passe), ni en-têtes,
        # ni identifiant de session : méthode, chemin, statut. Niveau DEBUG : le fichier tournant le reçoit, l'écran
        # seulement en mode verbeux. Rien pour NON_JOURNALISES.
        if reponse.status_code >= 400 and not request.url.path.startswith(NON_JOURNALISES):
            journal.debug("%s %s %s", _nettoyer(request.method), _nettoyer(request.url.path), reponse.status_code)
        return reponse

    # --- Information et consentement ---------------------------------------------------------------

    # L'accueil de l'étude sous « / » (langue de la session ou du navigateur) et sous chaque préfixe de langue.
    @app.get("/", response_class=HTMLResponse)
    @app.get("/fr", response_class=HTMLResponse)
    @app.get("/en", response_class=HTMLResponse)
    def accueil(request: Request) -> HTMLResponse:
        en_cours, langue = request.state.session is not None, langue_de(request)
        # Un chargement de la page compte ; une requête HEAD, non.
        sessions, complet = etat_de_l_accueil(request.method == "GET", en_cours)
        return avec_csrf(
            request,
            lambda csrf: pages.accueil(csrf, langue, en_cours=en_cours, sessions=sessions, complet=complet),
        )

    # La notice complète, sans formulaire ; « /information » suit la langue de la session ou du navigateur.
    @app.get("/information", response_class=HTMLResponse)
    @app.get("/fr/information", response_class=HTMLResponse)
    @app.get("/en/information", response_class=HTMLResponse)
    def notice(request: Request) -> HTMLResponse:
        return HTMLResponse(pages.notice(reglages, limites.duree_session_s, langue_de(request)))

    @app.post("/session/commencer")
    async def commencer(request: Request) -> Response:
        if not meme_origine(request):
            return refus(403, "origine_accueil", langue_de(request))
        champs = await formulaire(request)
        if champs is None:
            return refus(400, "illisible", langue_de(request))
        # La langue de la page où l'accord est donné (champ caché du formulaire), sinon celle de la requête.
        langue = champs["langue"] if champs.get("langue") in LANGUES else langue_de(request)
        if not csrf_valide(request, champs):
            return refus(403, "expire_accueil", langue)
        if champs.get("consentement") != "oui":
            message, sessions = pages.texte(langue, "accord_manquant"), total_des_sessions()
            return avec_csrf(
                request, lambda csrf: pages.accueil(csrf, langue, erreur=message, sessions=sessions), status_code=422
            )
        if request.state.session is not None:  # double clic, ou session déjà ouverte : on ne recrée rien
            return RedirectResponse(pages.SOCIAL, status_code=303)
        with base() as cx:
            trop = donnees.sessions_du_jour(cx) >= limites.sessions_par_jour
        if plein():
            return refus(503, "complet", langue)
        if trop:  # avant la limite par adresse : un jour plein n'use pas le quota horaire du visiteur
            return refus(429, "complet_du_jour", langue)
        if not limiteur.autoriser(adresse_de(request)):
            return refus(429, "trop_de_sessions", langue)
        with base() as cx:
            accord = {
                "texte_information": pages.VERSION_INFORMATION,
                "conservation_jours": reglages.conservation_jours,
                "langue": langue,
            }
            jeton = donnees.creer_session(cx, accord)
        compter("commencees")
        reponse = RedirectResponse(pages.SOCIAL, status_code=303)  # le site vedette, le réseau social fictif
        poser(reponse, cookie_session, signer("session", jeton), max_age=limites.duree_session_s)
        # Droit d'effacement dès le début : « Ma session » retrouve la session tant qu'elle est conservée.
        poser(reponse, cookie_droits, signer("supprimer", jeton), max_age=reglages.conservation_jours * UNE_JOURNEE_S)
        return reponse

    @app.post("/session/terminer", response_class=HTMLResponse)
    async def terminer(request: Request) -> Response:
        if not meme_origine(request):
            return refus(403, "origine", langue_de(request))
        champs = await formulaire(request)
        if champs is None or not csrf_valide(request, champs):
            return refus(403, "expire", langue_de(request))
        jeton = request.state.session
        if jeton is None:  # déjà terminée ou expirée : la page « Ma session » dit ce qu'il en reste
            return RedirectResponse("/session", status_code=303)
        with base() as cx:
            donnees.clore_session(cx, jeton)
        compter("terminees")
        suppression = signer("supprimer", jeton)
        langue = langue_de(request)
        reponse = avec_csrf(
            request,
            lambda csrf: pages.merci(jeton, suppression, csrf, reglages.conservation_jours, langue),
        )
        effacer(reponse, cookie_session)  # le cookie de droits reste : « Ma session » sert encore à supprimer
        return reponse

    def noter_langue_de(request: Request, cx: sqlite3.Connection, jeton: str) -> None:
        """Une session terminée garde sa langue pour « Ma session » et la suppression, si aucune n'est en cours."""
        if request.state.langue_session is None:
            request.state.langue_session = donnees.langue_de_session(cx, jeton)

    @app.get("/session", response_class=HTMLResponse)
    def ma_session(request: Request) -> HTMLResponse:
        jeton = lire_signe("supprimer", request.cookies.get(cookie_droits, ""))
        if jeton is not None:
            with base() as cx:
                if donnees.session_existe(cx, jeton):
                    noter_langue_de(request, cx, jeton)
                else:
                    jeton = None
        langue = langue_de(request)
        if jeton is None:
            reponse = HTMLResponse(pages.aucune_session(langue))
            if cookie_droits in request.cookies:
                effacer(reponse, cookie_droits)
            return reponse
        suppression, en_cours = signer("supprimer", jeton), request.state.session == jeton
        return avec_csrf(
            request,
            lambda csrf: pages.ma_session(jeton, suppression, csrf, reglages.conservation_jours, en_cours, langue),
        )

    @app.post("/session/supprimer", response_class=HTMLResponse)
    async def supprimer(request: Request) -> HTMLResponse:
        if not meme_origine(request):
            return refus(403, "origine", langue_de(request))
        champs = await formulaire(request)
        if champs is None or not csrf_valide(request, champs):
            return refus(403, "expire_ma_session", langue_de(request))
        jeton = lire_signe("supprimer", champs.get("session", ""))
        if jeton is None:
            return refus(400, "session_inconnue", langue_de(request))
        with base() as cx:
            noter_langue_de(request, cx, jeton)
            existait = donnees.effacer_session(cx, jeton)
        reponse = HTMLResponse(pages.supprimee(existait, langue_de(request)))
        effacer(reponse, cookie_session)
        effacer(reponse, cookie_droits)
        return reponse

    # --- Contact : écrire au responsable sans qu'une adresse soit affichée (D-57) -------------------

    def page_contact(request: Request, erreur: str = "", texte: str = "", status_code: int = 200) -> HTMLResponse:
        """Formulaire de contact ; `erreur` est une clé de `textes.T` (« » : aucune)."""
        jours, taille, langue = reglages.conservation_jours, limites.taille_message, langue_de(request)
        alerte = pages.texte(langue, erreur, taille=taille) if erreur else ""
        return avec_csrf(
            request, lambda csrf: pages.contact(csrf, jours, taille, langue, erreur=alerte, texte=texte), status_code
        )

    @app.get("/contact", response_class=HTMLResponse)
    def contact(request: Request) -> HTMLResponse:
        return page_contact(request)

    @app.get("/contact/envoye", response_class=HTMLResponse)
    def contact_envoye(request: Request) -> HTMLResponse:
        return HTMLResponse(pages.contact_envoye(langue_de(request)))

    @app.get("/contact/style.css")
    def contact_style() -> FileResponse:
        """La feuille des pages de l'étude, servie aussi sous /contact/ : une page de contact ne mène qu'à « / » ou
        « /contact… » et ne charge rien sous /lab/, que la base d'une session en cours noterait (à la milliseconde)."""
        return FileResponse(STATIQUES_PUBLICS / "public.css", media_type="text/css")

    @app.post("/contact")
    async def ecrire(request: Request) -> Response:
        if not meme_origine(request):
            return refus(403, "origine", langue_de(request), contact=True)
        champs = await formulaire(request, taille_formulaire_contact)
        if champs is None:
            return refus(400, "illisible_contact", langue_de(request), contact=True)
        # À partir d'ici, un refus rend le formulaire avec le texte tapé : il n'est jamais perdu.
        texte = messages.nettoyer(champs.get("message", ""))
        if not csrf_valide(request, champs):
            return page_contact(request, "contact_expire", texte, status_code=403)
        if not texte:
            return page_contact(request, "contact_vide", status_code=422)
        if len(texte) > limites.taille_message:
            return page_contact(request, "contact_trop_long", texte, status_code=422)
        with boite() as cx:
            if messages.nombre(cx) >= limites.messages_gardes:
                return page_contact(request, "contact_boite_pleine", texte, status_code=503)
            trop = messages.du_jour(cx) >= limites.messages_par_jour
            adresse = adresse_de(request)
            # L'heure d'abord : un envoi qu'elle refuse ne doit pas user le quota du jour.
            if trop or not limiteur_messages.autoriser(adresse) or not limiteur_messages_jour.autoriser(adresse):
                return page_contact(request, "contact_trop", texte, 429)
            messages.ajouter(cx, texte)
        _avis_au_responsable("message de contact reçu")  # jamais son texte, jamais dans le journal
        return RedirectResponse("/contact/envoye", status_code=303)

    # --- Site vitrine : mêmes chemins que dans le labo ---------------------------------------------

    def page_vitrine(request: Request, rendre: Callable[[str, vitrine.Habillage], str]) -> HTMLResponse:
        """Page vitrine ; pendant une session, observateur et bandeau (avec le bouton « Terminer », d'où le CSRF)."""
        jeton, langue = request.state.session, langue_de(request)
        if jeton is None:
            return HTMLResponse(
                rendre("", vitrine.Habillage(observateur=False, sans_tiers=True, bandeau=pages.bandeau(langue, None)))
            )
        return avec_csrf(
            request,
            lambda csrf: rendre(
                jeton, vitrine.Habillage(observateur=True, sans_tiers=True, bandeau=pages.bandeau(langue, csrf))
            ),
        )

    def annonce_ou_404(reference: str) -> vitrine.Annonce:
        annonce = vitrine.trouver(annonces, reference)
        if annonce is None:
            raise HTTPException(404, "annonce inconnue")
        return annonce

    @app.get("/lab/vitrine", response_class=HTMLResponse)
    def vitrine_accueil(request: Request) -> HTMLResponse:
        return page_vitrine(
            request, lambda jeton, habillage: vitrine.page_accueil(jeton, annonces, habillage=habillage)
        )

    @app.get("/lab/vitrine/annonces", response_class=HTMLResponse)
    def vitrine_liste(request: Request, page: int = 1) -> HTMLResponse:
        if not 1 <= page <= vitrine.nb_pages(len(annonces)):
            raise HTTPException(404, "page inexistante")
        return page_vitrine(
            request, lambda jeton, habillage: vitrine.page_liste(jeton, annonces, page, habillage=habillage)
        )

    @app.get("/lab/vitrine/annonces/{reference}", response_class=HTMLResponse)
    def vitrine_fiche(request: Request, reference: str) -> HTMLResponse:
        annonce = annonce_ou_404(reference)
        return page_vitrine(request, lambda jeton, habillage: vitrine.page_fiche(jeton, annonce, habillage=habillage))

    @app.get("/lab/vitrine/photos/{reference}/{fichier}")
    def vitrine_photo(reference: str, fichier: str) -> Response:
        annonce = annonce_ou_404(reference)
        m = re.fullmatch(r"([1-9]\d?)\.svg", fichier)
        if not m or int(m.group(1)) > annonce.nb_photos:
            raise HTTPException(404, "photo inexistante")
        return Response(
            vitrine.photo_svg(annonce, int(m.group(1))),
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=3600"},
        )

    @app.get("/lab/vitrine/api/annonces/{reference}/similaires")
    def vitrine_similaires(reference: str) -> dict:
        annonce = annonce_ou_404(reference)
        return {"annonces": [vitrine.resume_json(a) for a in vitrine.similaires(annonces, annonce)]}

    @app.get("/lab/static/{chemin:path}")
    def statique(chemin: str) -> FileResponse:
        type_media = FICHIERS_STATIQUES.get(chemin)
        if type_media is None:
            raise HTTPException(404, "fichier inconnu")
        return FileResponse(STATIQUES / chemin, media_type=type_media)

    # --- Réseau social fictif « Mosaïk Démo » (public/social.py) : même traitement que la vitrine -----

    def page_sociale(request: Request, rendre: Callable[[str, str, vitrine.Habillage], str]) -> HTMLResponse:
        """Page du réseau social, dans la langue du visiteur. Pendant une session : jeton, observateur du labo (sans
        tiers) et bandeau avec le bouton « Terminer », d'où le CSRF ; hors session, ni observateur ni cookie."""
        langue = langue_de(request)
        jeton = request.state.session
        if jeton is None:
            habillage = vitrine.Habillage(observateur=False, sans_tiers=True, bandeau=social.bandeau(langue, None))
            return HTMLResponse(rendre(langue, "", habillage))
        return avec_csrf(
            request,
            lambda csrf: rendre(
                langue,
                jeton,
                vitrine.Habillage(observateur=True, sans_tiers=True, bandeau=social.bandeau(langue, csrf)),
            ),
        )

    @app.get("/lab/social")
    def social_accueil() -> RedirectResponse:
        return RedirectResponse("/lab/social/fil", status_code=302)  # adresse relative : jamais http:// en ligne

    @app.get("/lab/social/fil", response_class=HTMLResponse)
    def social_fil(request: Request, page: int = 1) -> HTMLResponse:
        if not 1 <= page <= social.nb_pages(len(univers.publications), social.PAR_PAGE_FIL):
            raise HTTPException(404, "page inexistante")
        return page_sociale(request, lambda langue, jeton, h: social.page_fil(jeton, univers, page, langue, h))

    @app.get("/lab/social/explorer", response_class=HTMLResponse)
    def social_explorer(request: Request, page: int = 1) -> HTMLResponse:
        if not 1 <= page <= social.nb_pages(len(univers.exploration), social.PAR_PAGE_GRILLE):
            raise HTTPException(404, "page inexistante")
        return page_sociale(request, lambda langue, jeton, h: social.page_explorer(jeton, univers, page, langue, h))

    @app.get("/lab/social/p/{identifiant}", response_class=HTMLResponse)
    def social_publication(request: Request, identifiant: str) -> HTMLResponse:
        publication = univers.publication(identifiant)
        if publication is None:
            raise HTTPException(404, "publication inconnue")
        return page_sociale(
            request, lambda langue, jeton, h: social.page_publication(jeton, univers, publication, langue, h)
        )

    @app.get("/lab/social/u/{pseudonyme}", response_class=HTMLResponse)
    def social_profil(request: Request, pseudonyme: str) -> HTMLResponse:
        auteur = univers.auteur(pseudonyme)
        if auteur is None:
            raise HTTPException(404, "profil inconnu")
        return page_sociale(request, lambda langue, jeton, h: social.page_profil(jeton, univers, auteur, langue, h))

    @app.get("/lab/social/t/{etiquette}", response_class=HTMLResponse)
    def social_etiquette(request: Request, etiquette: str) -> HTMLResponse:
        if etiquette not in univers.libelles:
            raise HTTPException(404, "étiquette inconnue")
        return page_sociale(
            request, lambda langue, jeton, h: social.page_etiquette(jeton, univers, etiquette, langue, h)
        )

    @app.get("/lab/social/credits", response_class=HTMLResponse)
    def social_credits(request: Request, page: int = 1) -> HTMLResponse:
        """Crédits des photos (les licences demandent l'attribution) : seule page avec des liens sortants."""
        if not 1 <= page <= social.nb_pages(len(univers.photos), social.PAR_PAGE_GRILLE):
            raise HTTPException(404, "page inexistante")
        return page_sociale(request, lambda langue, jeton, h: social.page_credits(jeton, univers, page, langue, h))

    @app.get("/lab/social/photos/{fichier}")
    def social_photo(fichier: str) -> FileResponse:
        """Seuls les fichiers du manifeste (liste blanche) : jamais un chemin libre, ni le manifeste lui-même."""
        if fichier not in fichiers_photos:
            raise HTTPException(404, "photo inexistante")
        return FileResponse(
            dossier_photos / fichier, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"}
        )

    @app.get("/public/static/{chemin:path}")
    def statique_public(chemin: str) -> FileResponse:
        type_media = FICHIERS_PUBLICS.get(chemin)
        if type_media is None:
            raise HTTPException(404, "fichier inconnu")
        return FileResponse(STATIQUES_PUBLICS / chemin, media_type=type_media)

    # --- Collecte -----------------------------------------------------------------------------------

    @app.post("/lab/collecte", status_code=204)
    async def collecte(request: Request) -> Response:
        jeton = request.state.session
        # Le jeton de l'URL (posé par observateur.js) doit être celui du cookie signé de la session en cours.
        if jeton is None or request.query_params.getlist("sl") != [jeton]:
            raise HTTPException(403, "collecte refusée")
        corps = await lire_corps(request, limites.taille_corps)
        if corps is None:
            raise HTTPException(413, "message trop gros")
        try:
            message = json.loads(corps)
            kind, page, charge = message["kind"], message.get("page", ""), message["payload"]
        except (ValueError, KeyError, TypeError, AttributeError, RecursionError) as erreur:
            raise HTTPException(400, "message illisible") from erreur
        if kind not in ("empreinte", "comportement") or not isinstance(charge, dict) or not isinstance(page, str):
            raise HTTPException(400, "message invalide")
        if _trop_profond(charge):
            raise HTTPException(400, "message trop imbriqué")
        # Les identifiants d'extension (traces d'erreur) sont masqués avant le calcul du volume et l'écriture.
        texte = donnees.masquer_extensions(json.dumps(charge, ensure_ascii=False, sort_keys=True))
        if plein():
            raise HTTPException(503, "service complet")
        with base() as cx:
            envois, volume = donnees.usage(cx, jeton)
            if envois >= limites.envois_par_session or volume + len(texte.encode()) > limites.volume_par_session:
                raise HTTPException(429, "quota de la session atteint")
            donnees.noter_collecte(cx, jeton, kind, donnees.masquer_extensions(page[:200]), texte)
        return Response(status_code=204)

    @app.exception_handler(sqlite3.Error)
    async def base_indisponible(_: Request, __: sqlite3.Error) -> JSONResponse:
        # Jamais le message de SQLite (chemin, état de la base) : seulement l'indisponibilité.
        return JSONResponse({"detail": "service momentanément indisponible"}, status_code=503)

    return app
