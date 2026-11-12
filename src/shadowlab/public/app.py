"""Fabrique de l'application publique : site vitrine, sessions humaines consenties et collecte. Rien d'autre.

Ni l'API du laboratoire, ni /labo, ni /tableau, ni le gardien, le frontal, les détecteurs ou les moteurs :
ils ne sont même pas importés. Toute route qui n'est pas déclarée ici répond 404. Voir docs/site-public.md.
"""

from __future__ import annotations

import hashlib
import hmac
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
from . import donnees, messages, pages

STATIQUES = Path(__file__).resolve().parents[1] / "site" / "static"
# Liste fermée : rien d'autre du dossier statique du laboratoire n'est servi.
FICHIERS_STATIQUES = {
    "observateur.js": "text/javascript",
    "vendor/botd-2.0.0.esm.js": "text/javascript",
    "vitrine.css": "text/css",
    "vitrine.js": "text/javascript",
}
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
# Chemins jamais journalisés : les pages de contact, et ce que le navigateur charge avec chacune d'elles (feuille
# de style, icône). Horodatées à la milliseconde, rapprochées des requêtes notées d'une session, ces lignes
# dateraient un message, que D-57 ne garde qu'au jour ; une feuille de style chargée sans page notée trahirait
# aussi une page de contact. Il ne reste qu'une ligne par page, et aucune pour une page de contact.
NON_JOURNALISES = ("/contact", "/lab/static/", "/favicon.ico")
journal = logging.getLogger("shadowlab.public")


@dataclass(frozen=True)
class Limites:
    """Bornes qui protègent le disque et la vie privée. Les valeurs par défaut suffisent pour une dizaine
    de participants ; un humain qui parcourt 100 pages reste loin des quotas d'une session."""

    sessions_par_adresse: int = 6  # ouvertures par heure glissante et par adresse (en mémoire seulement)
    sessions_par_jour: int = 40  # ouvertures par jour UTC, toutes adresses confondues
    envois_par_session: int = 300  # messages de l'observateur (deux par page)
    volume_par_session: int = 4 * 1024 * 1024  # octets de charges JavaScript (~10 Ko par empreinte)
    requetes_par_session: int = 3000  # requêtes HTTP notées (~17 par page, images comprises)
    taille_corps: int = 64 * 1024  # un message de l'observateur
    duree_session_s: int = 2 * 3600  # au-delà, la session n'est plus « en cours »
    taille_max_base: int = 2 * 1024**3  # au-delà, plus aucune session ne s'ouvre et plus rien ne s'écrit
    messages_par_adresse: int = 3  # messages de contact par heure glissante et par adresse (en mémoire seulement)
    messages_par_jour: int = 30  # messages de contact par jour UTC, toutes adresses confondues
    messages_gardes: int = 500  # au-delà, le formulaire refuse jusqu'à la purge (8 Ko au pire par message)
    taille_message: int = 2000  # caractères d'un message de contact


class Limiteur:
    """Ouvertures de session par adresse sur une heure glissante.

    L'adresse n'est jamais écrite : elle n'existe qu'en mémoire, sous forme d'empreinte salée par un sel tiré
    au démarrage, et disparaît au redémarrage.
    """

    FENETRE_S = 3600
    ADRESSES_MAX = 10_000

    def __init__(self, maximum: int, horloge: Callable[[], float] = time.monotonic) -> None:
        self.maximum = maximum
        self._horloge = horloge
        self._sel = secrets.token_bytes(16)
        self._vues: dict[bytes, deque[float]] = {}

    def autoriser(self, adresse: str) -> bool:
        maintenant = self._horloge()
        if len(self._vues) >= self.ADRESSES_MAX:
            self._vues = {c: v for c, v in self._vues.items() if v and maintenant - v[-1] < self.FENETRE_S}
            if len(self._vues) >= self.ADRESSES_MAX:  # inondation : on repart de zéro, le plafond du jour tient
                self._vues.clear()
        cle = hashlib.blake2b(adresse.encode(), key=self._sel, digest_size=16).digest()
        vues = self._vues.setdefault(cle, deque())
        while vues and maintenant - vues[0] >= self.FENETRE_S:
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
    limites = limites or Limites()
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
    fichier_messages = messages.chemin(reglages.base_donnees)
    taille_formulaire_contact = limites.taille_message * OCTETS_PAR_CARACTERE + 1024
    annonces = vitrine.generer(reglages.vitrine_graine, reglages.vitrine_taille)
    derniere_purge = [time.monotonic()]

    # Sans redirection sur barre oblique finale : elle serait construite en http:// derrière le mandataire.
    app = FastAPI(title="Habitat Démo", docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False)
    app.state.reglages = reglages

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

    def adresse_de(request: Request) -> str:
        """Adresse du visiteur, pour la limite en mémoire : dernière valeur de l'en-tête du mandataire."""
        if reglages.entete_ip:
            derniere = request.headers.get(reglages.entete_ip, "").split(",")[-1].strip()
            if derniere:
                return derniere
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

    def refus(status_code: int, titre: str, message: str) -> HTMLResponse:
        return HTMLResponse(pages.erreur(titre, message), status_code=status_code)

    def plein() -> bool:
        """Base au plafond : plus rien ne s'y écrit, même pour une session déjà ouverte."""
        return donnees.taille(reglages.base_donnees) >= limites.taille_max_base

    # --- Garde : hôte, observation, en-têtes de sécurité, journal ----------------------------------

    def preparer(request: Request) -> None:
        """Ce que la garde lit et écrit en base : purge quotidienne, session du cookie, requête notée."""
        if time.monotonic() - derniere_purge[0] > UNE_JOURNEE_S:  # purge quotidienne, même sans tâche planifiée
            derniere_purge[0] = time.monotonic()
            with base() as cx:
                donnees.purger(cx, reglages.conservation_jours)
            with boite() as cx:
                messages.purger(cx, reglages.conservation_jours)
        jeton = session_de(request)
        request.state.session = jeton
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
                reponse = refus(503, "Service indisponible", "Le site est momentanément indisponible. Réessayez.")
            else:
                reponse = await call_next(request)
        reponse.headers["Content-Security-Policy"] = CSP
        reponse.headers["X-Content-Type-Options"] = "nosniff"
        # Depuis une page de contact, la page suivante ne reçoit que l'origine (sans chemin, donc « / » une fois
        # réduite par `donnees._referent`) : une session en cours ne note pas qu'on en vient. Pas `no-referrer` :
        # le navigateur enverrait `Origin: null` au POST du formulaire, que `meme_origine` refuse (403).
        depuis_contact = request.url.path.startswith("/contact")
        reponse.headers["Referrer-Policy"] = "origin" if depuis_contact else "same-origin"
        reponse.headers["X-Frame-Options"] = "DENY"
        reponse.headers.setdefault("Cache-Control", "no-store")
        if reglages.https:
            reponse.headers["Strict-Transport-Security"] = "max-age=31536000"
        # Ni adresse, ni chaîne de requête (le jeton y passe), ni en-têtes : méthode, chemin, statut. Niveau DEBUG :
        # le fichier tournant le reçoit, l'écran seulement en mode verbeux. Rien pour NON_JOURNALISES.
        if not request.url.path.startswith(NON_JOURNALISES):
            journal.debug("%s %s %s", _nettoyer(request.method), _nettoyer(request.url.path), reponse.status_code)
        return reponse

    # --- Information et consentement ---------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    def information(request: Request) -> HTMLResponse:
        en_cours = request.state.session is not None
        return avec_csrf(
            request, lambda csrf: pages.information(reglages, csrf, limites.duree_session_s, en_cours=en_cours)
        )

    @app.post("/session/commencer")
    async def commencer(request: Request) -> Response:
        if not meme_origine(request):
            return refus(403, "Requête refusée", "Ce formulaire doit être envoyé depuis la page d'information du site.")
        champs = await formulaire(request)
        if champs is None:
            return refus(400, "Requête refusée", "Formulaire illisible.")
        if not csrf_valide(request, champs):
            return refus(403, "Requête refusée", "Le formulaire a expiré : rechargez la page d'information.")
        if champs.get("consentement") != "oui":
            message = "Cochez la case pour donner votre accord, ou visitez le site sans participer."
            return avec_csrf(
                request,
                lambda csrf: pages.information(reglages, csrf, limites.duree_session_s, erreur=message),
                status_code=422,
            )
        if request.state.session is not None:  # double clic, ou session déjà ouverte : on ne recrée rien
            return RedirectResponse("/lab/vitrine", status_code=303)
        with base() as cx:
            trop = donnees.sessions_du_jour(cx) >= limites.sessions_par_jour
        if plein():
            return refus(503, "Service complet", "Le site n'accepte plus de nouvelles sessions pour le moment.")
        if trop or not limiteur.autoriser(adresse_de(request)):
            return refus(429, "Trop de sessions", "Trop de sessions ont été ouvertes récemment. Réessayez plus tard.")
        with base() as cx:
            accord = {"texte_information": pages.VERSION_INFORMATION, "conservation_jours": reglages.conservation_jours}
            jeton = donnees.creer_session(cx, accord)
        reponse = RedirectResponse("/lab/vitrine", status_code=303)
        poser(reponse, cookie_session, signer("session", jeton), max_age=limites.duree_session_s)
        # Droit d'effacement dès le début : « Ma session » retrouve la session tant qu'elle est conservée.
        poser(reponse, cookie_droits, signer("supprimer", jeton), max_age=reglages.conservation_jours * UNE_JOURNEE_S)
        return reponse

    @app.post("/session/terminer", response_class=HTMLResponse)
    async def terminer(request: Request) -> Response:
        if not meme_origine(request):
            return refus(403, "Requête refusée", "Ce formulaire doit être envoyé depuis ce site.")
        champs = await formulaire(request)
        if champs is None or not csrf_valide(request, champs):
            return refus(403, "Requête refusée", "Le formulaire a expiré : rechargez la page puis réessayez.")
        jeton = request.state.session
        if jeton is None:  # déjà terminée ou expirée : la page « Ma session » dit ce qu'il en reste
            return RedirectResponse("/session", status_code=303)
        with base() as cx:
            donnees.clore_session(cx, jeton)
        suppression = signer("supprimer", jeton)
        reponse = avec_csrf(
            request,
            lambda csrf: pages.merci(jeton, suppression, csrf, reglages.conservation_jours),
        )
        effacer(reponse, cookie_session)  # le cookie de droits reste : « Ma session » sert encore à supprimer
        return reponse

    @app.get("/session", response_class=HTMLResponse)
    def ma_session(request: Request) -> HTMLResponse:
        jeton = lire_signe("supprimer", request.cookies.get(cookie_droits, ""))
        if jeton is not None:
            with base() as cx:
                if not donnees.session_existe(cx, jeton):
                    jeton = None
        if jeton is None:
            reponse = HTMLResponse(pages.aucune_session())
            if cookie_droits in request.cookies:
                effacer(reponse, cookie_droits)
            return reponse
        suppression, en_cours = signer("supprimer", jeton), request.state.session == jeton
        return avec_csrf(
            request,
            lambda csrf: pages.ma_session(jeton, suppression, csrf, reglages.conservation_jours, en_cours),
        )

    @app.post("/session/supprimer", response_class=HTMLResponse)
    async def supprimer(request: Request) -> HTMLResponse:
        if not meme_origine(request):
            return refus(403, "Requête refusée", "Ce formulaire doit être envoyé depuis ce site.")
        champs = await formulaire(request)
        if champs is None or not csrf_valide(request, champs):
            return refus(
                403, "Requête refusée", "Le formulaire a expiré. Rechargez la page « Ma session » puis réessayez."
            )
        jeton = lire_signe("supprimer", champs.get("session", ""))
        if jeton is None:
            return refus(400, "Requête refusée", "Session inconnue.")
        with base() as cx:
            existait = donnees.effacer_session(cx, jeton)
        reponse = HTMLResponse(pages.supprimee(existait))
        effacer(reponse, cookie_session)
        effacer(reponse, cookie_droits)
        return reponse

    # --- Contact : écrire au responsable sans qu'une adresse soit affichée (D-57) -------------------

    def page_contact(request: Request, erreur: str = "", texte: str = "", status_code: int = 200) -> HTMLResponse:
        jours, taille = reglages.conservation_jours, limites.taille_message
        return avec_csrf(
            request, lambda csrf: pages.contact(csrf, jours, taille, erreur=erreur, texte=texte), status_code
        )

    @app.get("/contact", response_class=HTMLResponse)
    def contact(request: Request) -> HTMLResponse:
        return page_contact(request)

    @app.get("/contact/envoye", response_class=HTMLResponse)
    def contact_envoye() -> HTMLResponse:
        return HTMLResponse(pages.contact_envoye())

    @app.post("/contact")
    async def ecrire(request: Request) -> Response:
        if not meme_origine(request):
            return refus(403, "Requête refusée", "Ce formulaire doit être envoyé depuis ce site.")
        champs = await formulaire(request, taille_formulaire_contact)
        if champs is None:
            return refus(400, "Requête refusée", "Formulaire illisible ou trop long.")
        # À partir d'ici, un refus rend le formulaire avec le texte tapé : il n'est jamais perdu.
        texte = messages.nettoyer(champs.get("message", ""))
        if not csrf_valide(request, champs):
            expire = (
                "Le formulaire a expiré : envoyez-le de nouveau. Si cela se répète, autorisez les cookies de ce site."
            )
            return page_contact(request, expire, texte, status_code=403)
        if not texte:
            return page_contact(request, "Écrivez votre message.", status_code=422)
        if len(texte) > limites.taille_message:
            trop_long = f"Message trop long : {limites.taille_message} caractères au plus."
            return page_contact(request, trop_long, texte, status_code=422)
        with boite() as cx:
            if messages.nombre(cx) >= limites.messages_gardes:
                pleine = "Le formulaire n'accepte plus de message pour le moment. Réessayez dans quelques jours."
                return page_contact(request, pleine, texte, status_code=503)
            trop = messages.du_jour(cx) >= limites.messages_par_jour
            if trop or not limiteur_messages.autoriser(adresse_de(request)):
                return page_contact(request, "Trop de messages ont été envoyés. Réessayez plus tard.", texte, 429)
            messages.ajouter(cx, texte)
        _avis_au_responsable("message de contact reçu")  # jamais son texte, jamais dans le journal
        return RedirectResponse("/contact/envoye", status_code=303)

    # --- Site vitrine : mêmes chemins que dans le labo ---------------------------------------------

    def page_vitrine(request: Request, rendre: Callable[[str, vitrine.Habillage], str]) -> HTMLResponse:
        """Page vitrine ; pendant une session, observateur et bandeau (avec le bouton « Terminer », d'où le CSRF)."""
        jeton = request.state.session
        if jeton is None:
            return HTMLResponse(
                rendre("", vitrine.Habillage(observateur=False, sans_tiers=True, bandeau=pages.bandeau(None)))
            )
        return avec_csrf(
            request,
            lambda csrf: rendre(
                jeton, vitrine.Habillage(observateur=True, sans_tiers=True, bandeau=pages.bandeau(csrf))
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
