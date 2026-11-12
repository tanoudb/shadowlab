"""Pages de l'application publique : information et consentement, remerciement, suppression, erreurs.

La liste des données relevées suit `site/static/observateur.js` clé par clé : un test vérifie qu'elle couvre
exactement ce que le script envoie. Aucune ressource extérieure, aucun script en ligne.
"""

# ruff: noqa: E501  (gabarits HTML et textes : lignes longues voulues)
from __future__ import annotations

from html import escape

from ..config import ReglagesPublics
from ..site.vitrine import MARQUE
from .donnees import ENTETES_GARDES, PREFIXES_GARDES

# Version du texte d'information : enregistrée avec chaque consentement. À changer quand le texte change.
VERSION_INFORMATION = "2026-11-12.3"

# Empreinte du navigateur : une entrée par clé de `collecter()` dans observateur.js.
DONNEES_RELEVEES: list[tuple[str, str]] = [
    (
        "navigateur",
        "Navigateur : identifiant (user-agent), système, langues, nombre de cœurs du processeur, mémoire approximative, nombre de points tactiles, nombre de modules, marques annoncées, indicateur d'automatisation.",
    ),
    ("ecran", "Écran : taille, zone utile, profondeur des couleurs, densité de pixels."),
    ("fenetre", "Taille de la fenêtre du navigateur, intérieure et extérieure."),
    ("fuseau", "Fuseau horaire et décalage avec l'heure universelle."),
    (
        "apis",
        "Présence (oui ou non) de fonctions du navigateur : Bluetooth, USB, port série, partage, identifiants, périphériques média, synthèse vocale, service worker.",
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
        "Page au premier plan ou non, indicateur d'automatisation, nombre de voix de synthèse, nombre et types de périphériques audio et vidéo (sans leur nom), état des autorisations de localisation, caméra et micro (rien ne vous est demandé).",
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
    ("font_fingerprint", "Polices présentes parmi une liste fixe de 25 polices courantes."),
    ("math_constants", "Résultats de quelques calculs mathématiques, qui varient selon le moteur du navigateur."),
    ("deep_proxy", "Contrôles techniques : fonctions du navigateur imitées ou d'origine."),
    (
        "cdp_detection",
        "Traces d'un pilotage du navigateur par un programme, mémoire de la page, présence d'une première interaction.",
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
    ("angles_segments", "Changements de direction de la souris, en angles (40 au plus). Pas sa position."),
    ("delais_clavier_ms", "Délais entre deux touches (40 au plus). Jamais les touches elles-mêmes."),
    ("delais_scroll_ms", "Délais entre deux défilements (50 au plus)."),
    ("wheel_deltas", "Amplitude des crans de la molette (50 au plus)."),
]


def _duree(secondes: int) -> str:
    heures = secondes // 3600
    if heures and not secondes % 3600:
        return f"{heures} heure{'s' if heures > 1 else ''}"
    return f"{secondes // 60} minutes"


def _page(titre: str, corps: str) -> str:
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="sl-sans-tiers" content="1">
<title>{escape(titre)} — {MARQUE}</title>
<link rel="stylesheet" href="/lab/static/vitrine.css">
</head>
<body class="vitrine">
<header class="entete"><div class="conteneur">
<a class="marque" href="/lab/vitrine">{MARQUE}</a>
<nav aria-label="Navigation principale"><a href="/">Participer</a><a href="/lab/vitrine">Le site</a><a href="/session">Ma session</a></nav>
</div></header>
<main class="conteneur public">
{corps}
</main>
<footer class="pied"><div class="conteneur">Site de démonstration — annonces fictives</div></footer>
</body>
</html>"""


def _bouton_terminer(csrf: str) -> str:
    return f"""<form class="en-ligne" method="post" action="/session/terminer">
<input type="hidden" name="csrf" value="{escape(csrf)}">
<button class="bouton-plein" type="submit">Terminer ma session</button>
</form>"""


def bandeau(csrf: str | None) -> str:
    """Bandeau des pages vitrine. Avec un jeton anti-CSRF (session en cours) : « Ma session » et un bouton pour
    terminer ; sans : invitation à participer."""
    if csrf is not None:
        return f"""<aside class="session-publique en-cours" aria-label="Session d'observation"><div class="conteneur">
<p><span class="pastille" aria-hidden="true"></span>Session d'observation en cours : votre navigation sur ce site est enregistrée. Gardez l'onglet visible.</p>
<div class="actions"><a href="/session">Ma session</a>{_bouton_terminer(csrf)}</div>
</div></aside>"""
    return """<aside class="session-publique" aria-label="Recherche"><div class="conteneur">
<p>Site fictif, sans vraies annonces. Vous visitez sans participer : rien n'est enregistré.</p>
<a href="/">Participer à la recherche</a>
</div></aside>"""


def _liste(donnees: list[tuple[str, str]]) -> str:
    return "".join(f"<dt><code>{escape(cle)}</code></dt><dd>{escape(texte)}</dd>" for cle, texte in donnees)


def information(
    reglages: ReglagesPublics, csrf: str, duree_session_s: int, *, en_cours: bool = False, erreur: str = ""
) -> str:
    entetes = ", ".join(f"<code>{escape(e)}</code>" for e in ENTETES_GARDES)
    prefixes = " et ".join(f"<code>{escape(p)}*</code>" for p in PREFIXES_GARDES)
    contact = escape(reglages.contact)
    jours = reglages.conservation_jours
    alerte = f'<p class="erreur" role="alert">{escape(erreur)}</p>' if erreur else ""
    if en_cours:
        action = """<div class="encadre accord">
<p><strong>Une session est déjà en cours dans ce navigateur.</strong></p>
<p class="actions"><a class="bouton-plein" href="/lab/vitrine">Reprendre la visite</a><a href="/session">Ma session</a></p>
</div>"""
    else:
        action = f"""<form class="encadre accord" method="post" action="/session/commencer">
{alerte}
<input type="hidden" name="csrf" value="{escape(csrf)}">
<label><input type="checkbox" name="consentement" value="oui" required>
<span>J'ai lu ces informations et j'accepte que ma navigation sur ce site soit enregistrée comme décrit ci-dessus, pour cette recherche.</span></label>
<p class="actions"><button class="bouton-plein" type="submit">Commencer la session</button><a href="/lab/vitrine">Visiter le site sans participer</a></p>
</form>"""
    corps = f"""<article class="info">
<h1>Participer à une session d'observation</h1>
<p class="chapeau">Ce site d'annonces immobilières est entièrement fictif. Il sert à un projet de recherche sur la détection des robots sur le Web (NOEZIA ShadowLab). Nous voulons vérifier que nos détecteurs ne prennent pas de vraies personnes pour des robots, et pour cela il nous faut quelques visites réelles.</p>

<section>
<h2>Comment ça se passe</h2>
<ol>
<li>Lisez cette page, cochez la case et commencez.</li>
<li>Parcourez le site librement pendant 5 à 10 minutes, comme un vrai site d'annonces : ouvrez des fiches, faites défiler, changez de page. Gardez l'onglet visible : dans un onglet en arrière-plan, le relevé d'une page ne part que lorsque l'onglet revient au premier plan.</li>
<li>Cliquez sur « Terminer ma session » dans le bandeau en haut de page. Sinon, la session s'arrête d'elle-même au bout de {_duree(duree_session_s)}.</li>
</ol>
<p>Dès le début, la page « Ma session » (lien dans le bandeau) affiche l'identifiant de votre session et permet de la supprimer.</p>
<p>Vous pouvez aussi visiter le site sans participer : dans ce cas, rien n'est relevé.</p>
</section>

<section>
<h2>Ce qui est relevé</h2>
<p>Seulement pendant la session, et seulement sur les pages de ce site :</p>
<ul>
<li><strong>Les caractéristiques de votre navigateur et de votre appareil</strong> : navigateur et système, langues, écran et fenêtre, fuseau horaire, carte graphique, polices installées (parmi 25), quelques empreintes calculées (dessin, son, textes) et des contrôles techniques qui servent à repérer les robots.</li>
<li><strong>Votre façon de naviguer, en chiffres seulement</strong> : nombre de clics, de touches et de défilements, délais entre deux gestes, changements de direction de la souris, temps passé sur chaque page. Jamais ce que vous tapez, ni la position de la souris.</li>
<li><strong>Les pages ouvertes sur ce site</strong> et les fichiers qu'elles chargent (images, styles, scripts), avec l'heure, la méthode, le chemin sans paramètres, la version du protocole, et une partie des en-têtes que votre navigateur envoie : {entetes}, ainsi que les en-têtes {prefixes}. Un référent de ce site est réduit à son chemin ; un référent venu d'un autre site est remplacé par le mot « externe ».</li>
<li><strong>La session elle-même</strong> : un identifiant tiré au hasard, l'heure de votre accord, de début et de fin.</li>
</ul>
<details>
<summary>Liste complète, champ par champ</summary>
<h3>Navigateur et appareil (une fois par page)</h3>
<dl class="donnees">{_liste(DONNEES_RELEVEES)}</dl>
<h3>Comportement (à la sortie de chaque page)</h3>
<dl class="donnees">{_liste(DONNEES_COMPORTEMENT)}</dl>
<p>Chaque envoi indique aussi la page concernée (son chemin sur ce site) et sa nature (empreinte ou comportement).</p>
</details>
</section>

<section>
<h2>Ce qui n'est pas relevé</h2>
<p>Ni votre adresse IP, ni les cookies que votre navigateur envoie, ni votre nom, ni votre adresse e-mail, ni ce que vous tapez, ni la position de la souris, ni votre localisation. Aucune autorisation ne vous est demandée (caméra, micro, position). La page ne fait appel à aucun autre site : ni publicité, ni mesure d'audience, ni service de Google ou de Cloudflare. Dans les traces d'erreur, l'identifiant d'une extension de votre navigateur est masqué avant d'être enregistré.</p>
<p>Comme pour tout site web, l'hébergement (le serveur) et le service placé devant le site pour le protéger voient passer toutes les données en transit pour les acheminer : votre adresse IP, les pages demandées et ce que la page envoie. L'application de recherche, elle, n'enregistre pas votre adresse IP.</p>
<p>Ces données ne disent pas qui vous êtes. Mais une empreinte de navigateur peut, rapprochée d'autres sources, permettre de reconnaître un appareil : c'est pourquoi elles sont traitées comme des données personnelles.</p>
</section>

<section>
<h2>Cookies</h2>
<p>Ce site pose trois cookies techniques, nécessaires à son fonctionnement (sur une connexion sécurisée, leur nom commence par <code>__Host-</code>). Aucun cookie de publicité ni de mesure d'audience.</p>
<ul>
<li><code>slp-csrf</code> : posé dès cette page, avant tout accord. Une valeur au hasard qui empêche un autre site d'envoyer les formulaires de celui-ci à votre place. Jamais enregistrée ; effacée à la fermeture du navigateur.</li>
<li><code>slp-session</code> : posé quand vous commencez. Il relie les pages que vous ouvrez à votre session. {_duree(duree_session_s)} au plus ; effacé quand vous terminez.</li>
<li><code>slp-droits</code> : posé quand vous commencez. Il permet de retrouver et de supprimer votre session depuis la page « Ma session », dans ce navigateur. Il dure {jours} jours, comme la session ; il est effacé quand vous la supprimez.</li>
</ul>
</section>

<section>
<h2>Pourquoi</h2>
<p>Pour mesurer, plus tard et hors ligne, combien de vraies personnes nos détecteurs de robots classent à tort comme des robots, et corriger ceux qui se trompent. Les données ne servent qu'à ce calcul. Elles ne sont ni vendues, ni cédées, ni utilisées pour vous reconnaître ou vous contacter. Aucune décision ne vous concerne : pendant la visite, aucun détecteur ne tourne et rien ne peut vous bloquer.</p>
<p>Base légale : votre consentement, donné en cochant la case ci-dessous.</p>
</section>

<section>
<h2>Combien de temps</h2>
<p>Chaque session est effacée automatiquement {jours} jours après son début.</p>
</section>

<section>
<h2>Qui est responsable</h2>
<p>{contact}</p>
<p>Pour lui écrire : <a href="/contact">formulaire de contact</a>. Votre message est enregistré tel quel, avec sa date et rien d'autre (ni adresse IP, ni lien avec une session), puis effacé au bout de {jours} jours.</p>
</section>

<section>
<h2>Vos droits</h2>
<ul>
<li>La page « Ma session », pendant la session puis dans ce navigateur jusqu'à l'effacement automatique, affiche l'identifiant de votre session et un bouton « Supprimer ma session » qui efface aussitôt toutes les données qui la concernent.</li>
<li>Depuis un autre appareil, si vous avez effacé les cookies de ce site, ou pour toute question (accès, effacement, opposition), écrivez au responsable par le <a href="/contact">formulaire de contact</a> en donnant l'identifiant de session.</li>
<li>Vous pouvez retirer votre consentement à tout moment de la même façon.</li>
<li>Vous pouvez aussi adresser une réclamation à la CNIL.</li>
</ul>
</section>

{action}
</article>"""
    return _page("Participer", corps)


def _encadre_session(jeton: str, suppression: str, csrf: str, jours: int, en_cours: bool) -> str:
    terminer = f'<p class="actions">{_bouton_terminer(csrf)}</p>' if en_cours else ""
    etat = "en cours" if en_cours else "terminée"
    return f"""<div class="encadre">
<p>Identifiant de votre session ({etat}), à donner si vous écrivez au responsable :<br><code class="identifiant">{escape(jeton)}</code></p>
{terminer}
<p>Elle sera effacée automatiquement {jours} jours après son début. Si vous préférez, effacez-la tout de suite :</p>
<form method="post" action="/session/supprimer">
<input type="hidden" name="csrf" value="{escape(csrf)}">
<input type="hidden" name="session" value="{escape(suppression)}">
<button class="bouton-plein bouton-danger" type="submit">Supprimer ma session</button>
</form>
<p class="discret">Vous pourrez aussi la supprimer plus tard depuis la page <a href="/session">Ma session</a>, dans ce navigateur, jusqu'à son effacement automatique. Depuis un autre appareil, ou si vous avez effacé les cookies de ce site, écrivez au responsable par le <a href="/contact">formulaire de contact</a>, avec l'identifiant ci-dessus.</p>
</div>"""


def merci(jeton: str, suppression: str, csrf: str, jours: int) -> str:
    corps = f"""<article class="info">
<h1>Merci !</h1>
<p class="chapeau">Votre session est terminée. Elle aidera à vérifier que nos détecteurs laissent passer les vraies personnes.</p>
{_encadre_session(jeton, suppression, csrf, jours, en_cours=False)}
<p><a href="/lab/vitrine">Revenir au site</a></p>
</article>"""
    return _page("Merci", corps)


def ma_session(jeton: str, suppression: str, csrf: str, jours: int, en_cours: bool) -> str:
    corps = f"""<article class="info">
<h1>Ma session</h1>
{_encadre_session(jeton, suppression, csrf, jours, en_cours)}
<p><a href="/lab/vitrine">Revenir au site</a></p>
</article>"""
    return _page("Ma session", corps)


def aucune_session() -> str:
    corps = """<article class="info">
<h1>Aucune session</h1>
<p>Aucune session d'observation n'est enregistrée pour ce navigateur : vous n'avez pas participé depuis ce navigateur, la session a été supprimée, ou ses cookies ont été effacés.</p>
<p>Pour une session ouverte ailleurs, écrivez au responsable par le <a href="/contact">formulaire de contact</a>, avec son identifiant.</p>
<p class="actions"><a class="bouton-plein" href="/">Participer</a><a href="/lab/vitrine">Revenir au site</a></p>
</article>"""
    return _page("Aucune session", corps)


def contact(csrf: str, jours: int, taille: int, *, erreur: str = "", texte: str = "") -> str:
    """Formulaire pour écrire au responsable. `texte` (échappé) rend au visiteur un message refusé."""
    alerte = f'<p class="erreur" role="alert">{escape(erreur)}</p>' if erreur else ""
    corps = f"""<article class="info">
<h1>Écrire au responsable</h1>
<p class="chapeau">Pour une question, ou pour une demande sur une session ouverte depuis un autre appareil : accès, effacement, retrait de votre accord.</p>
<form class="encadre contact" method="post" action="/contact">
{alerte}
<input type="hidden" name="csrf" value="{escape(csrf)}">
<label for="message">Votre message</label>
<textarea id="message" name="message" rows="8" maxlength="{taille}" required>{escape(texte)}</textarea>
<p class="discret">Pour une demande sur une session, donnez son identifiant (il est affiché sur la page « Ma session »). Si vous attendez une réponse, indiquez comment vous joindre. {taille} caractères au plus.</p>
<p class="actions"><button class="bouton-plein" type="submit">Envoyer</button><a href="/">Revenir à la page d'information</a></p>
</form>
<p class="discret">Votre message est enregistré tel quel, avec sa date et rien d'autre : ni adresse IP, ni navigateur, ni lien avec une session. Il est lu par le responsable du site, puis effacé automatiquement au bout de {jours} jours.</p>
</article>"""
    return _page("Contact", corps)


def contact_envoye() -> str:
    corps = """<article class="info">
<h1>Message envoyé</h1>
<p>Votre message a bien été enregistré. Le responsable le lira ; il ne pourra vous répondre que si vous avez indiqué comment vous joindre.</p>
<p><a href="/lab/vitrine">Revenir au site</a></p>
</article>"""
    return _page("Message envoyé", corps)


def supprimee(existait: bool) -> str:
    message = (
        "Votre session a été supprimée : toutes les données qui la concernaient ont été effacées."
        if existait
        else "Cette session n'existe plus : ses données ont déjà été effacées."
    )
    corps = f"""<article class="info">
<h1>Session supprimée</h1>
<p>{message}</p>
<p><a href="/lab/vitrine">Revenir au site</a></p>
</article>"""
    return _page("Session supprimée", corps)


def erreur(titre: str, message: str) -> str:
    corps = f"""<article class="info">
<h1>{escape(titre)}</h1>
<p>{escape(message)}</p>
<p><a href="/">Revenir à la page d'information</a></p>
</article>"""
    return _page(titre, corps)
