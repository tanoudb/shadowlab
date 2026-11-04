"""Pages HTML du site de test. Chaque page a un résultat attendu connu, vérifié par les scénarios."""

from __future__ import annotations

from html import escape

NB_PAGES_CATALOGUE = 5
ARTICLES_PAR_PAGE = 10
REFERENCES_STATIQUES = [f"SL-{n:03d}" for n in range(1, 11)]
MODELES = ["Rally2", "Rally3", "Rally4", "Rally5"]
TEXTE_DYNAMIQUE = "contenu-dynamique-ok"

NAVIGATION = [
    ("/lab/", "Accueil"),
    ("/lab/statique", "HTML simple"),
    ("/lab/dynamique", "JavaScript"),
    ("/lab/catalogue", "Pagination"),
    ("/lab/formulaire", "Formulaire"),
    ("/lab/session", "Session"),
    ("/lab/empreinte", "Empreinte"),
    ("/lab/detection", "Détection"),
    ("/lab/api/articles", "API JSON"),
]


HONEYPOT_LIEN = '<a class="sl-hp" href="/lab/piege" tabindex="-1" aria-hidden="true">offres</a>'


def gabarit(titre: str, corps: str, jeton: str, scripts: tuple[str, ...] = (), honeypot: bool = False) -> str:
    """Page complète : navigation, jeton de session et observateur JavaScript."""
    liens = "".join(f'<a href="{href}">{escape(nom)}</a>' for href, nom in NAVIGATION)
    balises = "".join(f'<script type="module" src="/lab/static/{nom}"></script>' for nom in scripts)
    piege = HONEYPOT_LIEN if honeypot else ""
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="sl-session" content="{escape(jeton)}">
<title>{escape(titre)} — ShadowLab</title>
<link rel="stylesheet" href="/lab/static/lab.css">
</head>
<body>
<header><strong>ShadowLab · site de test</strong><nav>{liens}</nav></header>
<main data-page="{escape(titre)}">
<h1>{escape(titre)}</h1>
{corps}
{piege}
</main>
<footer>Site d'expérimentation local. Aucune donnée n'en sort. · <a href="/manuel/terminer">Terminer une session manuelle</a></footer>
<script type="module" src="/lab/static/observateur.js"></script>
{balises}
</body>
</html>"""


def accueil(jeton: str, honeypot: bool = False) -> str:
    corps = """<p>Ce site sert de terrain d'essai aux moteurs de navigation. Chaque page produit un résultat
attendu que les scénarios vérifient.</p>
<ul>
<li><a href="/lab/statique">HTML simple</a> : texte, liens, tableau</li>
<li><a href="/lab/dynamique">JavaScript</a> : contenu ajouté après chargement</li>
<li><a href="/lab/catalogue">Pagination</a> : cinq pages liées</li>
<li><a href="/lab/formulaire">Formulaire</a> : champ texte, liste et bouton</li>
<li><a href="/lab/session">Session</a> : cookie et compteur de visites</li>
<li><a href="/lab/empreinte">Empreinte</a> : propriétés observables du navigateur</li>
<li><a href="/lab/detection">Détection</a> : verdict des détecteurs pour cette session</li>
<li><a href="/lab/api/articles">API JSON</a></li>
</ul>"""
    return gabarit("Accueil", corps, jeton, honeypot=honeypot)


def statique(jeton: str, honeypot: bool = False) -> str:
    lignes = "".join(
        f"<tr><td class='reference'>{ref}</td><td>Pièce {n}</td><td>{100 + n * 7} €</td></tr>"
        for n, ref in enumerate(REFERENCES_STATIQUES, start=1)
    )
    corps = f"""<p>Page statique. Les dix références ci-dessous sont dans le HTML envoyé par le serveur.</p>
<table id="tableau-references"><thead><tr><th>Référence</th><th>Désignation</th><th>Prix</th></tr></thead>
<tbody>{lignes}</tbody></table>
<p><a href="/lab/catalogue">Voir le catalogue</a></p>"""
    return gabarit("HTML simple", corps, jeton, honeypot=honeypot)


def dynamique(jeton: str, honeypot: bool = False) -> str:
    corps = """<p>Le bloc ci-dessous est rempli par JavaScript 400 ms après le chargement.</p>
<div id="zone-dynamique" aria-live="polite">chargement…</div>"""
    return gabarit("JavaScript", corps, jeton, scripts=("dynamique.js",), honeypot=honeypot)


def catalogue(jeton: str, page: int, honeypot: bool = False) -> str:
    debut = (page - 1) * ARTICLES_PAR_PAGE
    articles = "".join(
        f"<li class='article' data-id='ART-{n:03d}'>Article ART-{n:03d}</li>"
        for n in range(debut + 1, debut + ARTICLES_PAR_PAGE + 1)
    )
    precedent = f'<a class="precedent" href="/lab/catalogue?page={page - 1}">Précédent</a>' if page > 1 else ""
    suivant = (
        f'<a class="suivant" href="/lab/catalogue?page={page + 1}">Suivant</a>' if page < NB_PAGES_CATALOGUE else ""
    )
    corps = f"""<p>Page {page} sur {NB_PAGES_CATALOGUE}.</p>
<ul id="articles">{articles}</ul>
<p class="pagination">{precedent} {suivant}</p>"""
    return gabarit(f"Catalogue — page {page}", corps, jeton, honeypot=honeypot)


HONEYPOT_CHAMP = (
    '<label class="sl-hp" aria-hidden="true">Téléphone '
    '<input name="sl_telephone" tabindex="-1" autocomplete="off"></label>'
)


def formulaire(jeton: str, honeypot: bool = False) -> str:
    options = "".join(f'<option value="{m}">{m}</option>' for m in MODELES)
    piege = HONEYPOT_CHAMP if honeypot else ""
    corps = f"""<form id="formulaire-essai" method="post" action="/lab/formulaire">
<label>Nom <input id="champ-nom" name="nom" required maxlength="60"></label>
<label>Modèle <select id="champ-modele" name="modele">{options}</select></label>
{piege}
<button id="bouton-envoyer" type="submit">Envoyer</button>
</form>"""
    return gabarit("Formulaire", corps, jeton, honeypot=honeypot)


def confirmation(jeton: str, nom: str, modele: str) -> str:
    corps = f'<p id="confirmation">Merci {escape(nom)} — modèle {escape(modele)}</p>'
    return gabarit("Formulaire envoyé", corps, jeton)


def session(jeton: str, visites: int) -> str:
    corps = f"""<p>Ce compteur est tenu par un cookie de session.</p>
<p>Visites : <span id="compteur-visites">{visites}</span></p>
<p><a id="recharger" href="/lab/session">Recharger</a></p>"""
    return gabarit("Session", corps, jeton)


def empreinte(jeton: str) -> str:
    corps = """<p>Propriétés que cette page peut lire dans le navigateur. Elles sont envoyées au serveur du
laboratoire, et nulle part ailleurs.</p>
<pre id="proprietes">collecte en cours…</pre>"""
    return gabarit("Empreinte", corps, jeton, scripts=("empreinte.js",))


def detection(jeton: str) -> str:
    corps = """<p>Verdict des détecteurs du laboratoire pour cette session, une fois l'empreinte reçue.</p>
<table id="verdicts"><thead><tr><th>Détecteur</th><th>Classement</th><th>Raisons</th></tr></thead>
<tbody><tr><td colspan="3">en attente…</td></tr></tbody></table>"""
    return gabarit("Détection", corps, jeton, scripts=("verdict.js",))


def manuel() -> str:
    corps = """<p>Une session manuelle sert de <strong>référence humaine</strong> : elle permet de mesurer
les faux positifs des détecteurs et ce que les protections coûtent à une vraie personne. Elle est enregistrée comme
« humain » dans l'expérience « sessions-manuelles ».</p>
<p>Ouvrez cette page dans votre navigateur habituel, puis parcourez librement le site pendant une minute
(cliquez, faites défiler, remplissez le formulaire) et revenez terminer la session.</p>
<form method="post" action="/manuel/commencer">
<label>Protection <select id="choix-protection" name="protection">
<option value="01">01 — Baseline (aucune)</option>
<option value="02">02 — Détection simple</option>
<option value="03">03 — Fingerprinting</option>
<option value="04">04 — Challenges</option>
<option value="05">05 — Protection avancée</option>
<option value="06">06 — Défense multicouche</option>
</select></label>
<button type="submit">Commencer une session manuelle</button></form>"""
    return gabarit("Session manuelle", corps, "")


def manuel_pret(lien: str) -> str:
    corps = f"""<p>Session prête. Elle passe par l'Arena : votre navigateur signalera un certificat local auto-signé,
à accepter pour continuer.</p>
<p><a id="entrer-arena" href="{escape(lien)}">Entrer dans l'Arena</a></p>"""
    return gabarit("Session manuelle", corps, "")


def _page_arena(type_page: str, titre: str, corps: str, scripts: str = "") -> str:
    """Page servie par une protection à la place du contenu demandé. Elle ne porte pas l'observateur."""
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(titre)} — ShadowLab</title>
<link rel="stylesheet" href="/lab/static/lab.css">
</head>
<body data-arena="{type_page}">
<main class="arena">
<h1>{escape(titre)}</h1>
{corps}
</main>
{scripts}
</body>
</html>"""


def page_defi(defi: str, difficulte: int, retour: str) -> str:
    corps = f"""<p id="etat-defi">Vérification du navigateur en cours…</p>
<noscript><p>Cette vérification demande JavaScript.</p></noscript>
<div id="defi" hidden data-defi="{escape(defi)}" data-difficulte="{difficulte}" data-retour="{escape(retour)}"></div>"""
    return _page_arena("defi", "Vérification", corps, '<script type="module" src="/lab/static/defi.js"></script>')


def page_captcha(captcha: str, retour: str, erreur: bool = False) -> str:
    message = '<p id="captcha-erreur" role="alert">Code incorrect, réessayez.</p>' if erreur else ""
    corps = f"""<p>Cette session demande une vérification humaine (CAPTCHA de démonstration du laboratoire).</p>
{message}
<img id="captcha-image" src="/lab/captcha/image?c={escape(captcha)}" alt="Code à recopier" width="220" height="80">
<form id="captcha-formulaire" method="post" action="/lab/captcha/verifier">
<input type="hidden" name="c" value="{escape(captcha)}">
<input type="hidden" name="retour" value="{escape(retour)}">
<label>Code <input id="captcha-code" name="code" required maxlength="8" autocomplete="off"></label>
<button id="captcha-envoyer" type="submit">Valider</button>
</form>"""
    return _page_arena("captcha", "Vérification humaine", corps)


def page_turnstile(site_key: str, retour: str) -> str:
    corps = f"""<p>Cette session demande une vérification Turnstile (Cloudflare, mode test).</p>
<p id="turnstile-etat">Chargement du widget…</p>
<form id="turnstile-formulaire" method="post" action="/lab/turnstile/verifier">
<input type="hidden" name="retour" value="{escape(retour)}">
<div id="turnstile-widget" class="cf-turnstile" data-sitekey="{escape(site_key)}"
 data-callback="turnstileOk"></div>
<button id="turnstile-envoyer" type="submit" disabled>Valider</button>
</form>
<script>
function turnstileOk(token) {{
  document.getElementById("turnstile-etat").textContent = "Vérification reçue.";
  document.getElementById("turnstile-envoyer").disabled = false;
}}
</script>"""
    return _page_arena(
        "turnstile",
        "Vérification Turnstile",
        corps,
        '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>',
    )


def page_recaptcha(site_key: str, retour: str) -> str:
    corps = f"""<p>Cette session demande une vérification reCAPTCHA v2 (Google, mode test).</p>
<p id="recaptcha-etat">Chargement du widget…</p>
<form id="recaptcha-formulaire" method="post" action="/lab/recaptcha/verifier">
<input type="hidden" name="retour" value="{escape(retour)}">
<div id="recaptcha-widget" class="g-recaptcha" data-sitekey="{escape(site_key)}"
 data-callback="recaptchaOk"></div>
<button id="recaptcha-envoyer" type="submit" disabled>Valider</button>
</form>
<script>
function recaptchaOk(token) {{
  document.getElementById("recaptcha-etat").textContent = "Vérification reçue.";
  document.getElementById("recaptcha-envoyer").disabled = false;
}}
</script>"""
    return _page_arena(
        "recaptcha",
        "Vérification reCAPTCHA",
        corps,
        '<script src="https://www.google.com/recaptcha/api.js" async defer></script>',
    )


def page_blocage() -> str:
    return _page_arena(
        "blocage",
        "Accès refusé",
        "<p>Activité suspecte détectée. L'accès à cette page a été bloqué.</p>",
    )


def fin_manuelle(classements: list[dict]) -> str:
    lignes = "".join(
        f"<tr><td>{escape(c['detector_name'])}</td><td>{escape(c['classification'])}</td></tr>" for c in classements
    )
    corps = f"""<p>Session enregistrée. Verdicts :</p>
<table><thead><tr><th>Détecteur</th><th>Classement</th></tr></thead><tbody>{lignes}</tbody></table>
<p><a href="/manuel">Nouvelle session</a> · <a href="/tableau">Tableau de bord</a></p>"""
    return gabarit("Session manuelle terminée", corps, "")
