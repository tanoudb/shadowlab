"""Pages de l'application publique : accueil de l'étude, notice, session, contact, erreurs, bandeau de la vitrine.

Deux langues (français, anglais) : la structure HTML est écrite une fois ici, les textes sont dans `textes.py`.
La liste des données relevées suit `site/static/observateur.js` et `public/static/releve.js` (D-76) clé par clé, dans
chaque langue : des tests vérifient qu'elle couvre exactement ce que les scripts envoient. Aucune ressource
extérieure, aucun script en ligne.
"""

# ruff: noqa: E501  (gabarits HTML et textes : lignes longues voulues)
from __future__ import annotations

import re
from functools import cache
from html import escape
from pathlib import Path

from ..config import ReglagesPublics
from ..site.vitrine import MARQUE
from . import social as reseau_social
from .donnees import ENTETES_GARDES, PREFIXES_GARDES
from .social import EMBLEME
from .social import MARQUE as MARQUE_SOCIAL
from .textes import ERREURS, LANGUES, RELEVES_TRACE, RESUME_RELEVE, T
from .trace import BALISE as BALISE_RELEVE

# Version du texte d'information : enregistrée avec chaque consentement. À changer quand le texte change.
VERSION_INFORMATION = "2026-11-14.6"

# Empreinte du navigateur : une entrée par clé de `collecter()` dans observateur.js.
DONNEES_RELEVEES: list[tuple[str, str]] = [
    (
        "navigateur",
        "Navigateur : identifiant (user-agent), système, langues, nombre de cœurs du processeur, mémoire approximative, nombre de points tactiles, nombre de modules et de types de fichiers pris en charge, cookies permis ou non, lecteur PDF intégré ou non, marques annoncées et type d'appareil (mobile ou non), indicateur d'automatisation.",
    ),
    ("ecran", "Écran : taille, zone utile, profondeur des couleurs, densité de pixels."),
    ("fenetre", "Taille de la fenêtre du navigateur, intérieure et extérieure."),
    ("fuseau", "Fuseau horaire et décalage avec l'heure universelle."),
    (
        "apis",
        "Présence (oui ou non) de fonctions du navigateur : objet propre à Chrome, Bluetooth, USB, port série, périphériques HID, partage, identifiants, périphériques média, synthèse vocale, service worker.",
    ),
    (
        "permissions",
        "État de l'autorisation des notifications (accordée, refusée ou à demander). Rien ne vous est demandé.",
    ),
    ("webgl", "Fabricant et modèle de la carte graphique, tels que le navigateur les annonce."),
    ("canvas", "Empreinte d'un petit dessin tracé hors écran : un code de 16 caractères, pas l'image."),
    (
        "prototypes",
        "Contrôles techniques : certaines fonctions du navigateur sont-elles d'origine ou modifiées par un script ?",
    ),
    ("integrite", "Contrôles techniques sur les fonctions du navigateur : nom, longueur, forme d'un message d'erreur."),
    (
        "timing",
        "Horloge : date et heure du navigateur, départ du chronomètre de la page, type de navigation (lien, rechargement).",
    ),
    ("chrome_apis", "Présence et forme de fonctions propres à Chrome, et protocole de connexion qu'il annonce."),
    ("media_codecs", "Formats audio et vidéo que le navigateur sait lire."),
    (
        "iframe_test",
        "Cohérence entre la page et un cadre vide créé par le script : mêmes langues, même écran, mêmes fonctions.",
    ),
    ("languages_test", "Langues du navigateur, langue et fuseau du système, éditeur du navigateur, et leur cohérence."),
    ("webrtc_test", "Sonde réseau WebRTC : sautée sur ce site, aucune connexion n'est ouverte vers un autre serveur."),
    (
        "headless_signals",
        "Page au premier plan ou non, indicateur d'automatisation, nombre de voix de synthèse (compté après une attente d'un quart de seconde au plus, dont la durée est notée, avec l'indication que le navigateur a fini de charger leur liste), nombre et types de périphériques audio et vidéo (sans leur nom), état des autorisations de localisation, caméra et micro (rien ne vous est demandé).",
    ),
    ("stack_trace_test", "Forme des messages d'erreur internes du navigateur, pour le script de cette page."),
    ("performance_memory", "Mémoire utilisée par la page et position de la fenêtre sur l'écran."),
    ("paint_timing", "Moments du premier affichage de la page."),
    ("automation_globals", "Recherche de traces laissées par des outils d'automatisation (Selenium, Playwright…)."),
    (
        "css_media",
        "Préférences d'affichage : thème clair ou sombre, animations réduites, type de pointeur (souris ou tactile), mode d'affichage.",
    ),
    ("prototype_chain", "Contrôles techniques sur la structure interne des objets du navigateur."),
    ("timing_precision", "Précision du chronomètre de la page."),
    ("canvas_consistency", "Un dessin tracé deux fois hors écran donne-t-il le même résultat ? (oui ou non)"),
    ("stack_getter", "Contrôles techniques sur les traces d'erreur."),
    ("raf_timing", "Rythme d'affichage : intervalles entre six rafraîchissements de l'écran."),
    ("domrect_fingerprint", "Taille à l'écran de trois courts textes de test (elle dépend des polices et du système)."),
    ("audio_context", "Empreinte d'un son de test calculé sans être joué : un nombre. Le micro n'est jamais utilisé."),
    (
        "font_fingerprint",
        "Polices présentes parmi une liste fixe de 25 polices courantes, repérées par comparaison avec trois familles génériques (chasse fixe, sans empattement, avec empattement), dont la liste est envoyée.",
    ),
    ("math_constants", "Résultats de quelques calculs mathématiques, qui varient selon le moteur du navigateur."),
    ("deep_proxy", "Contrôles techniques : fonctions du navigateur imitées ou d'origine."),
    (
        "cdp_detection",
        "Traces d'un pilotage du navigateur par un programme : marques d'un tel outil dans une trace d'erreur, fichiers chargés à son nom, balises de script vides, fonctions de la console d'origine ou modifiées, règle de sécurité des scripts (Trusted Types) ; part de la mémoire utilisée par la page.",
    ),
    ("worker_consistency", "Cohérence entre la page et un script d'arrière-plan : cœurs, mémoire, système."),
    ("connection_dynamic", "Type de connexion annoncé par le navigateur (4g…), latence et débit qu'il estime."),
    ("uadata_integrity", "Contrôles techniques sur les informations de marque du navigateur."),
    ("enumerable_props", "Contrôles techniques sur la structure des objets du navigateur."),
    ("automation", "Indices d'automatisation : variables laissées par Selenium, Playwright ou PhantomJS."),
    (
        "botd",
        "Résultat de BotD, une bibliothèque libre qui dit « robot ou non ». Elle tourne dans votre navigateur et n'envoie rien ailleurs.",
    ),
    ("fpjs", "Non exécuté sur ce site : valeur toujours vide."),
    ("duree_collecte_ms", "Durée du relevé, en millisecondes."),
]

# Comportement sur chaque page : une entrée par clé de l'envoi « comportement » d'observateur.js.
DONNEES_COMPORTEMENT: list[tuple[str, str]] = [
    (
        "evenements",
        "Nombre de mouvements de souris, de clics, de touches pressées, de défilements et de touchers d'écran.",
    ),
    ("premiere_interaction_ms", "Délai avant votre première action sur la page."),
    ("duree_page_ms", "Temps passé sur la page."),
    ("delais_souris_ms", "Délais entre deux mouvements de souris (50 au plus)."),
    ("delai_souris_max_ms", "Plus long délai entre deux mouvements de souris sur toute la page : un seul nombre."),
    ("angles_segments", "Changements de direction de la souris, en angles (40 au plus). Pas sa position."),
    ("delais_clavier_ms", "Délais entre deux touches (40 au plus). Jamais les touches elles-mêmes."),
    ("delais_scroll_ms", "Délais entre deux défilements (50 au plus)."),
    ("wheel_deltas", "Amplitude des crans de la molette (50 au plus)."),
    ("page_defilable", "La page dépassait-elle la hauteur de la fenêtre quand vous l'avez quittée ? (oui ou non)"),
]


# Les mêmes listes en anglais, clé pour clé, phrase pour phrase.
DONNEES_RELEVEES_EN: list[tuple[str, str]] = [
    (
        "navigateur",
        "Browser: identifier (user agent), operating system, languages, number of processor cores, approximate memory, number of touch points, number of plugins and of supported file types, whether cookies are allowed, whether the built-in PDF viewer is on, declared brands and device type (mobile or not), automation flag.",
    ),
    ("ecran", "Screen: size, usable area, colour depth, pixel density."),
    ("fenetre", "Size of the browser window, inner and outer."),
    ("fuseau", "Time zone and offset from universal time."),
    (
        "apis",
        "Presence (yes or no) of browser features: Chrome-specific object, Bluetooth, USB, serial port, HID devices, sharing, credentials, media devices, speech synthesis, service worker.",
    ),
    (
        "permissions",
        "State of the notification permission (granted, denied or not yet asked). Nothing is asked of you.",
    ),
    ("webgl", "Make and model of the graphics card, as the browser announces them."),
    ("canvas", "Fingerprint of a small drawing made off-screen: a 16-character code, not the image."),
    (
        "prototypes",
        "Technical checks: are certain browser functions original or modified by a script?",
    ),
    ("integrite", "Technical checks on the browser's functions: name, length, form of an error message."),
    (
        "timing",
        "Clock: the browser's date and time, start of the page's timer, type of navigation (link, reload).",
    ),
    ("chrome_apis", "Presence and form of functions specific to Chrome, and the connection protocol it announces."),
    ("media_codecs", "Audio and video formats the browser can play."),
    (
        "iframe_test",
        "Consistency between the page and an empty frame created by the script: same languages, same screen, same functions.",
    ),
    ("languages_test", "Browser languages, system language and time zone, browser vendor, and their consistency."),
    ("webrtc_test", "WebRTC network probe: skipped on this site, no connection is opened to another server."),
    (
        "headless_signals",
        "Whether the page is in the foreground, automation flag, number of speech-synthesis voices (counted after a wait of at most a quarter of a second, whose length is recorded, along with whether the browser has finished loading their list), number and types of audio and video devices (without their names), state of the location, camera and microphone permissions (nothing is asked of you).",
    ),
    ("stack_trace_test", "Form of the browser's internal error messages, for this page's script."),
    ("performance_memory", "Memory used by the page and position of the window on the screen."),
    ("paint_timing", "Moments of the page's first display."),
    ("automation_globals", "Search for traces left by automation tools (Selenium, Playwright…)."),
    (
        "css_media",
        "Display preferences: light or dark theme, reduced motion, pointer type (mouse or touch), display mode.",
    ),
    ("prototype_chain", "Technical checks on the internal structure of the browser's objects."),
    ("timing_precision", "Precision of the page's timer."),
    ("canvas_consistency", "Does a drawing made twice off-screen give the same result? (yes or no)"),
    ("stack_getter", "Technical checks on error traces."),
    ("raf_timing", "Display rhythm: intervals between six screen refreshes."),
    ("domrect_fingerprint", "On-screen size of three short test texts (it depends on the fonts and the system)."),
    (
        "audio_context",
        "Fingerprint of a test sound computed without being played: a number. The microphone is never used.",
    ),
    (
        "font_fingerprint",
        "Fonts present among a fixed list of 25 common fonts, detected by comparison with three generic families (monospace, sans-serif, serif), whose list is sent.",
    ),
    ("math_constants", "Results of a few mathematical calculations, which vary with the browser's engine."),
    ("deep_proxy", "Technical checks: browser functions imitated or original."),
    (
        "cdp_detection",
        "Traces of the browser being driven by a program: marks of such a tool in an error trace, files loaded under its name, empty script tags, console functions original or modified, script security rule (Trusted Types); share of memory used by the page.",
    ),
    ("worker_consistency", "Consistency between the page and a background script: cores, memory, system."),
    (
        "connection_dynamic",
        "Connection type announced by the browser (4g…), and the latency and bandwidth it estimates.",
    ),
    ("uadata_integrity", "Technical checks on the browser's brand information."),
    ("enumerable_props", "Technical checks on the structure of the browser's objects."),
    ("automation", "Automation clues: variables left by Selenium, Playwright or PhantomJS."),
    (
        "botd",
        "Result of BotD, a free library that says “bot or not”. It runs in your browser and sends nothing elsewhere.",
    ),
    ("fpjs", "Not run on this site: value always empty."),
    ("duree_collecte_ms", "Duration of the collection, in milliseconds."),
]

DONNEES_COMPORTEMENT_EN: list[tuple[str, str]] = [
    ("evenements", "Number of mouse movements, clicks, key presses, scrolls and screen touches."),
    ("premiere_interaction_ms", "Delay before your first action on the page."),
    ("duree_page_ms", "Time spent on the page."),
    ("delais_souris_ms", "Delays between two mouse movements (50 at most)."),
    ("delai_souris_max_ms", "Longest delay between two mouse movements over the whole page: a single number."),
    ("angles_segments", "Changes in the mouse's direction, as angles (40 at most). Not its position."),
    ("delais_clavier_ms", "Delays between two keystrokes (40 at most). Never the keys themselves."),
    ("delais_scroll_ms", "Delays between two scrolls (50 at most)."),
    ("wheel_deltas", "Size of the mouse-wheel steps (50 at most)."),
    ("page_defilable", "Was the page taller than the window when you left it? (yes or no)"),
]

# Listes de la notice, par langue : (navigateur et appareil, comportement).
RELEVES: dict[str, tuple[list[tuple[str, str]], list[tuple[str, str]]]] = {
    "fr": (DONNEES_RELEVEES, DONNEES_COMPORTEMENT),
    "en": (DONNEES_RELEVEES_EN, DONNEES_COMPORTEMENT_EN),
}


def langue_sure(langue: str) -> str:
    """Une langue servie (`LANGUES`) ; toute autre valeur donne le français."""
    return langue if langue in LANGUES else "fr"


def _t(langue: str, cle: str, **valeurs: object) -> str:
    """Texte de confiance de `textes.T`, champs remplis par des valeurs déjà échappées (ou des nombres)."""
    texte = T[langue_sure(langue)][cle]
    return texte.format(**valeurs) if valeurs else texte


def _insecable(texte: str) -> str:
    """Espaces insécables de la typographie française, pour les titres : « Humain ou robot ? » ne laisse jamais son
    point d'interrogation, ni un guillemet, seul en début de ligne."""
    for avant, apres in (("« ", "«\u00a0"), (" »", "\u00a0»"), (" ?", "\u00a0?"), (" !", "\u00a0!"), (" :", "\u00a0:")):
        texte = texte.replace(avant, apres)
    return texte


def texte(langue: str, cle: str, **valeurs: object) -> str:
    """Un texte de `textes.T` pour l'application (messages d'erreur d'un formulaire), sans balise."""
    return _t(langue, cle, **valeurs)


def _duree(secondes: int, langue: str) -> str:
    heures = secondes // 3600
    if heures and not secondes % 3600:
        return _t(langue, "heures_pluriel" if heures > 1 else "heures", n=heures)
    return _t(langue, "minutes", n=secondes // 60)


SOCIAL = "/lab/social/fil"  # le site vedette : « Commencer », « Reprendre la visite », « Revenir au site » y mènent
# Crédits des photos (auteur, licence, page d'origine) : les licences CC BY et CC BY-SA demandent l'attribution. L'accueil
# y mène sous chaque groupe de photos, et le pied de chaque page de l'étude aussi, sauf les pages de contact.
CREDITS = "/lab/social/credits"
NOM_LANGUE = {"fr": "Français", "en": "English"}

# --- Dessin (14/11/2026) ---------------------------------------------------------------------------
# De la même famille que Mosaïk Démo (static/social.css) : plâtre froid, lapis et or, titres en serif du système,
# la tesselle comme seule audace. Tous les SVG de la page n'ont que des attributs de présentation (ni `style`, ni
# adresse, ni `xmlns`) ; leurs couleurs viennent de public.css, qui suit le thème.

# Marque de l'étude : une tesselle posée à la main (légèrement de travers) et une tesselle tracée à la règle.
MARQUE_ETUDE = (
    '<svg class="marque-etude" width="28" height="28" viewBox="0 0 32 32" aria-hidden="true" focusable="false">'
    '<rect class="m-humain" x="2.5" y="8.5" width="13.5" height="13.5" rx="3" transform="rotate(-9 9.25 15.25)"/>'
    '<rect class="m-robot" x="18.5" y="10" width="11" height="11" rx="1.2"/>'
    "</svg>"
)
# Fragment de mosaïque de la page « Merci » : la session ajoute sa tesselle.
FLEURON = (
    '<svg class="fleuron" width="136" height="48" viewBox="0 0 136 48" aria-hidden="true" focusable="false">'
    '<rect class="t-smalt" x="3" y="4" width="17" height="17" rx="3.5" transform="rotate(-5 11.5 12.5)"/>'
    '<rect class="t-vert" x="24" y="3" width="16" height="16" rx="3.5"/>'
    '<rect class="t-smalt" x="44" y="5" width="16" height="16" rx="3.5" transform="rotate(3 52 13)"/>'
    '<rect class="t-grenat" x="64" y="3" width="17" height="17" rx="3.5"/>'
    '<rect class="t-smalt" x="85" y="4" width="16" height="16" rx="3.5" transform="rotate(-4 93 12)"/>'
    '<rect class="t-vert" x="105" y="2" width="17" height="17" rx="3.5" transform="rotate(6 113.5 10.5)"/>'
    '<rect class="t-grenat" x="6" y="26" width="15" height="15" rx="3.5" transform="rotate(4 13.5 33.5)"/>'
    '<rect class="t-smalt" x="25" y="24" width="17" height="17" rx="3.5"/>'
    '<rect class="t-vert" x="46" y="26" width="15" height="15" rx="3.5" transform="rotate(-6 53.5 33.5)"/>'
    '<rect class="t-or fleuron-nouvelle" x="64" y="23" width="19" height="19" rx="4" transform="rotate(9 73.5 32.5)"/>'
    '<rect class="t-smalt" x="87" y="25" width="16" height="16" rx="3.5" transform="rotate(2 95 33)"/>'
    '<rect class="t-grenat" x="107" y="24" width="16" height="16" rx="3.5" transform="rotate(-3 115 32)"/>'
    "</svg>"
)
# Mosaïque de l'accueil : de vraies photos du réseau social (manifeste), posées comme des tesselles, et deux
# tesselles de couleur. (place dans la mosaïque, identifiant de la photo ou None) ; la place donne la case.
PLACES_MOSAIQUE: tuple[tuple[str, str | None], ...] = (
    ("lac", "lacs-04"),
    ("renard", "sauvages-06"),
    ("or", None),
    ("fleur", "fleurs-02"),
    ("lapis", None),
    ("brioche", "cuisine-01"),
)
# Grandes cases : le fichier de 1080 aussi (`srcset`), pour rester nettes sur un écran dense.
TAILLES_GRANDES_CASES = {"lac": "(min-width: 1000px) 270px, 46vw", "renard": "(min-width: 1000px) 270px, 31vw"}
# Vignettes de la carte du site de démonstration, plus bas dans la page : chargées en différé.
PHOTOS_VEDETTE = ("sauvages-01", "mer-08", "domestiques-08", "ciel-04")
# Textes du dessin, sans engagement envers les participants : description des photos (attribut `alt`) et titre du
# sommaire de la notice.
DESCRIPTIONS_PHOTOS: dict[str, tuple[str, str]] = {
    "lacs-04": (
        "Un sommet enneigé qui se reflète dans un lac de montagne",
        "A snowy peak reflected in a mountain lake",
    ),
    "sauvages-06": ("Deux renardeaux qui jouent", "Two fox cubs playing"),
    "fleurs-02": ("Un tournesol en pleine floraison", "A sunflower in full bloom"),
    "cuisine-01": ("Des brioches à la cardamome dans une corbeille", "Cardamom buns in a basket"),
    "sauvages-01": ("Une petite chouette aux yeux jaunes", "A small owl with yellow eyes"),
    "mer-08": ("Un phare blanc au bord d'une falaise verte", "A white lighthouse on a green clifftop"),
    "domestiques-08": ("Un chiot corgi debout sur ses pattes arrière", "A corgi puppy standing on its hind legs"),
    "ciel-04": ("Une aurore rose et violette au-dessus des arbres", "Pink and purple northern lights above the trees"),
}
SOMMAIRE: dict[str, str] = {"fr": "Sommaire", "en": "Contents"}
MARQUE_SOMMAIRE = "<!-- sommaire -->"
RE_SECTION_NOTICE = re.compile(r'<section class="notice-section" id="([a-z0-9-]+)">\s*<h2>(.*?)</h2>', re.S)


@cache
def _photos_du_manifeste(dossier: Path) -> dict[str, reseau_social.Photo]:
    """Photos du manifeste de `dossier`, par identifiant ; vide si le manifeste est illisible (l'accueil se passe
    alors de photos plutôt que de tomber)."""
    try:
        return {p.id: p for p in reseau_social.charger_photos(dossier)}
    except ValueError:
        return {}


def _image(photo: reseau_social.Photo, langue: str, classe: str, *, tailles: str | None, paresseuse: bool) -> str:
    """Une photo du réseau social, servie sous /lab/social/photos/ : le fichier de 480 (avec celui de 1080 si
    `tailles`), dimensions réelles du fichier (la place est réservée), description dans la langue de la page."""
    largeur, hauteur = photo.dimensions(480)
    attributs = f' width="{largeur}" height="{hauteur}"'
    if tailles:
        jeu = ", ".join(
            f"/lab/social/photos/{escape(photo.fichier(t))} {photo.dimensions(t)[0]}w"
            for t in sorted(reseau_social.TAILLES_PHOTO)
        )
        attributs += f' srcset="{jeu}" sizes="{tailles}"'
    if paresseuse:
        attributs += ' loading="lazy"'
    francais, anglais = DESCRIPTIONS_PHOTOS.get(photo.id, ("", ""))
    texte = anglais if langue == "en" else francais
    return (
        f'<img class="{classe}" src="/lab/social/photos/{escape(photo.fichier(480))}" alt="{escape(texte)}"'
        f'{attributs} decoding="async">'
    )


def _mosaique(langue: str, avec_photos: bool) -> str:
    """Mosaïque du haut de l'accueil. Sans photos (`avec_photos` faux, ou manifeste sans ces identifiants), les
    mêmes cases en tesselles de couleur : pendant une session, l'accueil ne charge rien sous /lab/, où toute requête
    serait notée alors que la notice ne promet un relevé que sur les sites de démonstration."""
    photos = _photos_du_manifeste(reseau_social.DOSSIER_PHOTOS) if avec_photos else {}
    tesselles, montrees = [], 0
    for place, identifiant in PLACES_MOSAIQUE:
        photo = photos.get(identifiant) if identifiant else None
        if photo:
            tesselles.append(
                _image(
                    photo,
                    langue,
                    f"tesselle tesselle-{place}",
                    tailles=TAILLES_GRANDES_CASES.get(place),
                    paresseuse=False,
                )
            )
            montrees += 1
        else:
            vide = " tesselle-vide" if identifiant else ""
            tesselles.append(f'<span class="tesselle tesselle-{place}{vide}" aria-hidden="true"></span>')
    pose = f'<div class="tesselles">{"".join(tesselles)}</div>'
    if not montrees:
        return f'<div class="accueil-visuel"><div class="accueil-mosaique" aria-hidden="true">{pose}</div></div>'
    legende = f'<figcaption class="mosaique-legende">{EMBLEME}<span>{escape(MARQUE_SOCIAL)}</span></figcaption>'
    credits = _lien_credits(langue, "mosaique-credits")  # juste sous les photos, à toutes les largeurs
    return f'<div class="accueil-visuel">\n<figure class="accueil-mosaique">{pose}{legende}</figure>\n{credits}\n</div>'


def _lien_credits(langue: str, classe: str) -> str:
    """« Crédits des photos », sous des photos du réseau social montrées par l'accueil."""
    return f'<p class="credits-photos {classe}"><a href="{CREDITS}">{_t(langue, "credits_photos")}</a></p>'


def _vignettes_vedette(langue: str) -> str:
    photos = _photos_du_manifeste(reseau_social.DOSSIER_PHOTOS)
    images = [
        _image(photos[i], langue, "vedette-photo", tailles=None, paresseuse=True) for i in PHOTOS_VEDETTE if i in photos
    ]
    if not images:
        return ""
    return f'\n<div class="vedette-photos">{"".join(images)}</div>\n{_lien_credits(langue, "vedette-credits")}'


def _sommaire(corps: str, langue: str) -> str:
    """Sommaire de la notice : une entrée par section rendue, dans l'ordre, avec son identifiant et son titre ; sur un
    grand écran, le retour à l'accord y reste en vue (sur un téléphone, `.notice-retour` suit la lecture)."""
    langue = langue_sure(langue)
    entrees = "".join(f'<li><a href="#{ident}">{titre}</a></li>' for ident, titre in RE_SECTION_NOTICE.findall(corps))
    return f"""<nav class="notice-sommaire" aria-labelledby="titre-sommaire">
<p class="sommaire-titre" id="titre-sommaire">{SOMMAIRE[langue]}</p>
<ol>{entrees}</ol>
<p class="sommaire-retour"><a href="/{langue}#participer">{_t(langue, "notice_retour")}</a></p>
</nav>"""


def _page(
    titre: str, corps: str, langue: str, *, classe: str, contact: bool = False, bascule: str | None = None
) -> str:
    """Gabarit des pages de l'étude (accueil, notice, session, contact, erreurs), classe `classe` sur `body`.

    `bascule` : suffixe de l'adresse de la même page dans l'autre langue (« » pour l'accueil, « /information » pour la
    notice) ; sans lui, pas de lien vers l'autre langue. Une page de contact ne charge rien sous /lab/ et ne mène qu'à
    « / » ou « /contact… » : pendant une session, la base noterait toute requête /lab/ (à la milliseconde), donc
    l'ouverture du formulaire. Sa feuille de style, la même, est servie sous /contact/."""
    langue = langue_sure(langue)
    marque = _t(langue, "marque")
    if contact:
        feuille, accueil = "/contact/style.css", "/"
        liens = [("/", _t(langue, "nav_accueil")), ("/contact", _t(langue, "nav_contact"))]
    else:
        feuille, accueil = "/public/static/public.css", f"/{langue}"
        liens = [
            (f"/{langue}/information", _t(langue, "nav_notice")),
            (SOCIAL, escape(MARQUE_SOCIAL)),
            ("/session", _t(langue, "nav_ma_session")),
            ("/contact", _t(langue, "nav_contact")),
        ]
    navigation = "".join(f'<a href="{href}">{texte}</a>' for href, texte in liens)
    autre = "en" if langue == "fr" else "fr"
    lien_langue = (
        f'\n<p class="autre-langue"><a href="/{autre}{bascule}" hreflang="{autre}" lang="{autre}">{NOM_LANGUE[autre]}</a></p>'
        if bascule is not None
        else ""
    )
    entete_titre = escape(titre) if titre == marque else f"{escape(titre)} — {marque}"
    credits = "" if contact else f' <a href="{CREDITS}">{_t(langue, "credits_photos")}</a>'
    return f"""<!doctype html>
<html lang="{langue}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="sl-sans-tiers" content="1">
<title>{entete_titre}</title>
<link rel="stylesheet" href="{feuille}">
</head>
<body class="etude {classe}">
<header class="etude-entete"><div class="conteneur">
<a class="etude-marque" href="{accueil}">{MARQUE_ETUDE}<span>{_insecable(marque)}</span></a>
<nav class="etude-navigation" aria-label="{_t(langue, "nav_aria")}">{navigation}</nav>{lien_langue}
</div></header>
<main class="conteneur etude-principal">
{corps}
</main>
<footer class="etude-pied"><div class="conteneur">{MARQUE_ETUDE}<p>{_t(langue, "pied")}{credits}</p></div></footer>
</body>
</html>"""


def _bouton_terminer(csrf: str, langue: str, classe: str = "bouton-plein") -> str:
    """Bouton « Terminer ma session ». `bouton-plein` : classe de la feuille de la vitrine (bandeau)."""
    return f"""<form class="en-ligne" method="post" action="/session/terminer">
<input type="hidden" name="csrf" value="{escape(csrf)}">
<button class="{classe}" type="submit">{_t(langue, "terminer")}</button>
</form>"""


def bandeau(langue: str, csrf: str | None) -> str:
    """Bandeau des pages vitrine, dans la langue du visiteur. Avec un jeton anti-CSRF (session en cours) : « Ma session »,
    un bouton pour terminer et la balise du relevé enrichi (`releve.js`, D-76) ; sans : invitation à participer.
    Toujours un lien vers l'autre site, le réseau social fictif."""
    langue = langue_sure(langue)
    autre = f'<a class="autre-site" href="/lab/social/fil">{_t(langue, "autre_site", nom=escape(MARQUE_SOCIAL))}</a>'
    if csrf is not None:
        return f"""<aside class="session-publique en-cours" aria-label="{_t(langue, "bandeau_session")}"><div class="conteneur">
<p><span class="pastille" aria-hidden="true"></span>{_t(langue, "bandeau_en_cours")}</p>
<div class="actions"><a href="/session">{_t(langue, "nav_ma_session")}</a>{_bouton_terminer(csrf, langue)}{autre}</div>
</div></aside>
{BALISE_RELEVE}"""
    return f"""<aside class="session-publique" aria-label="{_t(langue, "bandeau_recherche")}"><div class="conteneur">
<p>{_t(langue, "bandeau_sans_participer")}</p>
<div class="actions"><a href="/">{_t(langue, "bandeau_participer")}</a>{autre}</div>
</div></aside>"""


def _liste(donnees: list[tuple[str, str]]) -> str:
    return "".join(f"<dt><code>{escape(cle)}</code></dt><dd>{escape(texte)}</dd>" for cle, texte in donnees)


def _puces(elements: list[str]) -> str:
    return "".join(f"<li>{escape(e)}</li>" for e in elements)


def _compteur(sessions: int, langue: str) -> str:
    """« N sessions enregistrées à ce jour » : singulier pour 0 et 1 en français, pour 1 seulement en anglais."""
    singulier = sessions <= 1 if langue == "fr" else sessions == 1
    nombre = f"{sessions:,}".replace(",", "\u202f" if langue == "fr" else ",")
    cle = "compteur_singulier" if singulier else "compteur"
    return _t(langue, cle, n=f'<strong class="compteur-nombre">{nombre}</strong>')


def accueil(
    csrf: str,
    langue: str,
    *,
    en_cours: bool = False,
    erreur: str = "",
    sessions: int | None = None,
    complet: bool = False,
) -> str:
    """Accueil de l'étude « Humain ou robot ? » (cadrage du 13/11/2026, « Textes de l'accueil »). Le nombre de sessions
    terminées (`sessions`, sans compteur si None), la case d'accord, la notice juste à côté, et la visite sans
    participer ; pendant une session, « Reprendre la visite » à la place de l'accord ; plafond du jour atteint
    (`complet`), l'avis « l'étude a fait le plein pour aujourd'hui » à la place de la case."""
    langue = langue_sure(langue)
    resume = RESUME_RELEVE[langue]
    notice_href = f"/{langue}/information"
    social = escape(MARQUE_SOCIAL)
    compteur = f'\n<p class="accueil-compteur">{_compteur(sessions, langue)}</p>' if sessions is not None else ""
    # Appel du haut de page : mène à l'accord (la case et la notice restent à côté du bouton « Commencer ») ;
    # pendant une session, reprend la visite.
    if en_cours:
        appel = f'<a class="bouton-principal" href="{SOCIAL}">{_t(langue, "reprendre")}</a>'
    else:
        appel = f'<a class="bouton-principal" href="#participer">{_t(langue, "participer")}</a>'
    vignettes = "" if en_cours else _vignettes_vedette(langue)
    nom_social, _, suffixe_social = MARQUE_SOCIAL.partition(" ")
    if en_cours:
        accord = f"""<div class="accord accord-en-cours" id="participer">
<p><strong>{_t(langue, "deja_en_cours")}</strong></p>
<p class="accord-actions"><a class="bouton-principal" href="{SOCIAL}">{_t(langue, "reprendre")}</a><a class="bouton-secondaire" href="/session">{_t(langue, "nav_ma_session")}</a></p>
</div>"""
    elif complet:
        titre, message = ERREURS[langue]["complet_du_jour"]
        accord = f"""<div class="accord accord-complet" id="participer">
<p><strong>{escape(titre)}</strong></p>
<p>{escape(message)}</p>
<p class="accord-actions"><a class="visiter-sans-participer" href="{SOCIAL}">{_t(langue, "visiter_sans_participer")}</a></p>
</div>"""
    else:
        alerte = f'<p class="erreur" role="alert">{escape(erreur)}</p>\n' if erreur else ""
        lien = f'<a class="lien-notice" href="{notice_href}">{_t(langue, "accord_notice_lien")}</a>'
        accord = f"""<form class="accord" id="participer" method="post" action="/session/commencer">
{alerte}<input type="hidden" name="csrf" value="{escape(csrf)}">
<input type="hidden" name="langue" value="{langue}">
<p class="accord-notice">{_t(langue, "accord_notice", lien=lien)}</p>
<div class="accord-case">
<input type="checkbox" id="consentement" name="consentement" value="oui" required>
<label for="consentement">{_t(langue, "accord_case", notice=notice_href)}</label>
</div>
<p class="accord-actions"><button class="bouton-principal" type="submit">{_t(langue, "commencer")}</button><a class="visiter-sans-participer" href="{SOCIAL}">{_t(langue, "visiter_sans_participer")}</a></p>
</form>"""
    corps = f"""<article class="accueil">
<header class="accueil-entete">
<div class="accueil-texte">
<h1 class="accueil-titre">{_insecable(_t(langue, "accueil_titre"))}</h1>
<p class="accueil-sous-titre">{_t(langue, "accueil_sous_titre")}</p>
<p class="accueil-accroche">{_t(langue, "accueil_accroche")}</p>
<div class="accueil-appel">{appel}{compteur}
</div>
</div>
{_mosaique(langue, avec_photos=not en_cours)}
</header>

<section class="accueil-etapes" aria-labelledby="titre-etapes">
<h2 id="titre-etapes">{_t(langue, "h_etapes")}</h2>
<ol class="etapes">
<li class="etape"><h3>{_t(langue, "etape_1_titre")}</h3><p>{_t(langue, "etape_1")}</p></li>
<li class="etape"><h3>{_t(langue, "etape_2_titre")}</h3><p>{_t(langue, "etape_2", social=social)}</p></li>
<li class="etape"><h3>{_t(langue, "etape_3_titre")}</h3><p>{_t(langue, "etape_3")}</p></li>
</ol>
</section>

<section class="accueil-releve" aria-labelledby="titre-releve">
<h2 id="titre-releve">{_t(langue, "h_resume")}</h2>
<p class="releve-franchise">{escape(resume["franchise"])}</p>
<div class="releve-colonnes">
<div class="releve-oui"><h3>{_t(langue, "resume_oui")}</h3><ul>{_puces(resume["oui"])}</ul></div>
<div class="releve-non"><h3>{_t(langue, "resume_non")}</h3><ul>{_puces(resume["non"])}</ul></div>
</div>
<p class="releve-sans-session">{escape(resume["sans_session"])}</p>
<p class="releve-detail"><a href="{notice_href}">{_t(langue, "resume_detail")}</a></p>
<p class="accueil-but">{_t(langue, "accueil_but")}</p>
</section>

<section class="accueil-sites" aria-labelledby="titre-sites">
<h2 id="titre-sites">{_t(langue, "h_sites")}</h2>
<div class="site-vedette">
<h3 class="site-vedette-nom">{EMBLEME}<span class="vedette-nom">{escape(nom_social)}</span> <span class="vedette-demo">{escape(suffixe_social)}</span></h3>
<p>{_t(langue, "vedette")}</p>{vignettes}
</div>
<p class="site-second">{_t(langue, "site_second")}</p>
<p class="fictif">{_t(langue, "fictif")}</p>
</section>

<section class="accueil-participer" aria-labelledby="titre-participer">
<h2 id="titre-participer">{_t(langue, "h_participer")}</h2>
{accord}
</section>
</article>"""
    return _page(_t(langue, "marque"), corps, langue, classe="page-accueil", bascule="")


def notice(reglages: ReglagesPublics, duree_session_s: int, langue: str) -> str:
    """Notice complète, dans une langue : la même structure pour les deux, phrase pour phrase. Sans formulaire :
    l'accord se donne sur l'accueil, vers lequel elle renvoie."""
    langue = langue_sure(langue)
    entetes = ", ".join(f"<code>{escape(e)}</code>" for e in ENTETES_GARDES)
    prefixes = _t(langue, "et").join(f"<code>{escape(p)}*</code>" for p in PREFIXES_GARDES)
    contact = escape(reglages.contact)
    jours = reglages.conservation_jours
    duree = _duree(duree_session_s, langue)
    relevees, comportement = RELEVES[langue]
    gestes = RELEVES_TRACE[langue]
    social, habitat = escape(MARQUE_SOCIAL), escape(MARQUE)
    corps = f"""<article class="notice">
<h1>{_insecable(_t(langue, "notice_h1"))}</h1>
<p class="notice-chapeau">{_t(langue, "notice_chapeau", social=social, vitrine=habitat)}</p>
{MARQUE_SOMMAIRE}

<section class="notice-section" id="deroulement">
<h2>{_t(langue, "h_deroulement")}</h2>
<ol>
<li>{_t(langue, "deroulement_1")}</li>
<li>{_t(langue, "deroulement_2", social=social)}</li>
<li>{_t(langue, "deroulement_3", duree=duree)}</li>
</ol>
<p>{_t(langue, "deroulement_ma_session")}</p>
<p>{_t(langue, "deroulement_sans_participer")}</p>
</section>

<section class="notice-section" id="releve">
<h2>{_t(langue, "h_releve")}</h2>
<p>{_t(langue, "releve_intro")}</p>
<ul>
<li>{_t(langue, "releve_appareil")}</li>
<li>{_t(langue, "releve_navigation")}</li>
<li>{_t(langue, "releve_pages", entetes=entetes, prefixes=prefixes)}</li>
<li>{_t(langue, "releve_session")}</li>
</ul>
<details class="liste-complete">
<summary>{_t(langue, "liste_complete")}</summary>
<h3>{_t(langue, "h_liste_appareil")}</h3>
<dl class="donnees">{_liste(relevees)}</dl>
<h3>{_t(langue, "h_liste_comportement")}</h3>
<dl class="donnees">{_liste(comportement)}</dl>
<h3>{_t(langue, "h_liste_trace")}</h3>
<p>{_t(langue, "liste_trace")}</p>
<dl class="donnees">{_liste(gestes)}</dl>
<p>{_t(langue, "liste_envoi")}</p>
</details>
</section>

<section class="notice-section" id="non-releve">
<h2>{_t(langue, "h_non_releve")}</h2>
<p>{_t(langue, "non_releve")}</p>
<p>{_t(langue, "transit")}</p>
<p>{_t(langue, "journal")}</p>
<p>{_t(langue, "donnees_personnelles")}</p>
</section>

<section class="notice-section" id="frequentation">
<h2>{_t(langue, "h_frequentation")}</h2>
<p>{_t(langue, "frequentation")}</p>
</section>

<section class="notice-section" id="cookies">
<h2>{_t(langue, "h_cookies")}</h2>
<p>{_t(langue, "cookies_intro")}</p>
<ul>
<li>{_t(langue, "cookie_csrf")}</li>
<li>{_t(langue, "cookie_session", duree=duree)}</li>
<li>{_t(langue, "cookie_droits", jours=jours)}</li>
</ul>
</section>

<section class="notice-section" id="pourquoi">
<h2>{_t(langue, "h_pourquoi")}</h2>
<p>{_t(langue, "pourquoi")}</p>
<p>{_t(langue, "base_legale")}</p>
</section>

<section class="notice-section" id="duree">
<h2>{_t(langue, "h_duree")}</h2>
<p>{_t(langue, "duree", jours=jours)}</p>
</section>

<section class="notice-section" id="responsable">
<h2>{_t(langue, "h_responsable")}</h2>
<p>{contact}</p>
<p>{_t(langue, "responsable_ecrire", jours=jours)}</p>
</section>

<section class="notice-section" id="droits">
<h2>{_t(langue, "h_droits")}</h2>
<ul>
<li>{_t(langue, "droits_ma_session")}</li>
<li>{_t(langue, "droits_ecrire")}</li>
<li>{_t(langue, "droits_retrait")}</li>
<li>{_t(langue, "droits_cnil")}</li>
</ul>
</section>

<p class="notice-retour"><a class="bouton-principal" href="/{langue}#participer">{_t(langue, "notice_retour")}</a></p>
</article>"""
    corps = corps.replace(MARQUE_SOMMAIRE, _sommaire(corps, langue), 1)
    return _page(_t(langue, "titre_notice"), corps, langue, classe="page-notice", bascule="/information")


def _encadre_session(jeton: str, suppression: str, csrf: str, jours: int, en_cours: bool, langue: str) -> str:
    terminer = f'<p class="actions">{_bouton_terminer(csrf, langue, "bouton-principal")}</p>' if en_cours else ""
    etat = _t(langue, "etat_en_cours" if en_cours else "etat_terminee")
    return f"""<div class="encadre session-encadre">
<p>{_t(langue, "identifiant", etat=etat)}<br><code class="identifiant">{escape(jeton)}</code></p>
{terminer}
<p>{_t(langue, "effacement_auto", jours=jours)}</p>
<form method="post" action="/session/supprimer">
<input type="hidden" name="csrf" value="{escape(csrf)}">
<input type="hidden" name="session" value="{escape(suppression)}">
<button class="bouton-danger" type="submit">{_t(langue, "supprimer")}</button>
</form>
<p class="discret">{_t(langue, "supprimer_plus_tard")}</p>
</div>"""


def merci(jeton: str, suppression: str, csrf: str, jours: int, langue: str) -> str:
    corps = f"""<article class="message">
<div class="merci-fleuron">{FLEURON}</div>
<h1>{_t(langue, "merci_h1")}</h1>
<p class="chapeau">{_t(langue, "merci_chapeau")}</p>
{_encadre_session(jeton, suppression, csrf, jours, False, langue)}
<p class="message-suite"><a class="bouton-secondaire" href="{SOCIAL}">{_t(langue, "revenir_site")}</a></p>
</article>"""
    return _page(_t(langue, "titre_merci"), corps, langue, classe="page-merci")


def ma_session(jeton: str, suppression: str, csrf: str, jours: int, en_cours: bool, langue: str) -> str:
    corps = f"""<article class="message">
<h1>{_t(langue, "titre_ma_session")}</h1>
{_encadre_session(jeton, suppression, csrf, jours, en_cours, langue)}
<p class="message-suite"><a class="bouton-secondaire" href="{SOCIAL}">{_t(langue, "revenir_site")}</a></p>
</article>"""
    return _page(_t(langue, "titre_ma_session"), corps, langue, classe="page-session")


def aucune_session(langue: str) -> str:
    corps = f"""<article class="message">
<h1>{_t(langue, "titre_aucune_session")}</h1>
<p>{_t(langue, "aucune_session")}</p>
<p>{_t(langue, "aucune_session_ailleurs")}</p>
<p class="actions"><a class="bouton-principal" href="/{langue_sure(langue)}">{_t(langue, "participer")}</a><a href="{SOCIAL}">{_t(langue, "revenir_site")}</a></p>
</article>"""
    return _page(_t(langue, "titre_aucune_session"), corps, langue, classe="page-session")


def contact(csrf: str, jours: int, taille: int, langue: str, *, erreur: str = "", texte: str = "") -> str:
    """Formulaire pour écrire au responsable. `texte` (échappé) rend au visiteur un message refusé."""
    alerte = f'<p class="erreur" role="alert">{escape(erreur)}</p>' if erreur else ""
    corps = f"""<article class="message">
<h1>{_t(langue, "contact_h1")}</h1>
<p class="chapeau">{_t(langue, "contact_chapeau")}</p>
<form class="encadre formulaire-contact" method="post" action="/contact">
{alerte}
<input type="hidden" name="csrf" value="{escape(csrf)}">
<label for="message">{_t(langue, "contact_message")}</label>
<textarea id="message" name="message" rows="8" maxlength="{taille}" required>{escape(texte)}</textarea>
<p class="discret">{_t(langue, "contact_aide", taille=taille)}</p>
<p class="actions"><button class="bouton-principal" type="submit">{_t(langue, "envoyer")}</button><a href="/">{_t(langue, "revenir_information")}</a></p>
</form>
<p class="discret">{_t(langue, "contact_conservation", jours=jours)}</p>
</article>"""
    return _page(_t(langue, "titre_contact"), corps, langue, classe="page-contact", contact=True)


def contact_envoye(langue: str) -> str:
    corps = f"""<article class="message">
<h1>{_t(langue, "titre_envoye")}</h1>
<p>{_t(langue, "envoye")}</p>
<p class="message-suite"><a class="bouton-secondaire" href="/">{_t(langue, "revenir_information")}</a></p>
</article>"""
    return _page(_t(langue, "titre_envoye"), corps, langue, classe="page-contact", contact=True)


def supprimee(existait: bool, langue: str) -> str:
    corps = f"""<article class="message">
<h1>{_t(langue, "titre_supprimee")}</h1>
<p>{_t(langue, "supprimee" if existait else "deja_effacee")}</p>
<p class="message-suite"><a class="bouton-secondaire" href="{SOCIAL}">{_t(langue, "revenir_site")}</a></p>
</article>"""
    return _page(_t(langue, "titre_supprimee"), corps, langue, classe="page-session")


def erreur(cle: str, langue: str, *, contact: bool = False) -> str:
    """Page d'erreur : titre et message de `textes.ERREURS`, dans la langue du visiteur."""
    titre, message = ERREURS[langue_sure(langue)][cle]
    corps = f"""<article class="message message-{escape(cle.replace("_", "-"))}">
<h1>{escape(titre)}</h1>
<p>{escape(message)}</p>
<p class="message-suite"><a class="bouton-secondaire" href="/">{_t(langue, "revenir_information")}</a></p>
</article>"""
    return _page(titre, corps, langue, classe="page-erreur", contact=contact)
