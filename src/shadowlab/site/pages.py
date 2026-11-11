"""Pages HTML du site de test. Chaque page a un résultat attendu connu, vérifié par les scénarios."""

from __future__ import annotations

import json
import random
import string
from html import escape

NB_PAGES_CATALOGUE = 5
ARTICLES_PAR_PAGE = 10
REFERENCES_STATIQUES = [f"SL-{n:03d}" for n in range(1, 11)]
# Page « adaptatif » : annonces dont les classes CSS mutent à chaque requête (obfuscation).
ANNONCES_ADAPTATIVES = [
    {"titre": "Studio Paris 18e", "prix": "245 000 €", "surface": "22 m²"},
    {"titre": "T2 Lyon 3e", "prix": "189 000 €", "surface": "41 m²"},
    {"titre": "T3 Lille Centre", "prix": "167 500 €", "surface": "63 m²"},
    {"titre": "Maison Nantes", "prix": "312 000 €", "surface": "95 m²"},
]
MODELES = ["Rally2", "Rally3", "Rally4", "Rally5"]
TEXTE_DYNAMIQUE = "contenu-dynamique-ok"

NAVIGATION = [
    ("/lab/", "Accueil"),
    ("/lab/statique", "HTML simple"),
    ("/lab/dynamique", "JavaScript"),
    ("/lab/catalogue", "Pagination"),
    ("/lab/formulaire", "Formulaire"),
    ("/lab/connexion", "Connexion"),
    ("/lab/session", "Session"),
    ("/lab/empreinte", "Empreinte"),
    ("/lab/detection", "Détection"),
    ("/lab/api/articles", "API JSON"),
    ("/lab/adaptatif", "Adaptatif"),
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


def _suffixe_aleatoire(longueur: int = 5) -> str:
    return "".join(random.choices(string.ascii_lowercase, k=longueur))


def adaptatif(jeton: str, honeypot: bool = False) -> str:
    """Page qui mute ses classes CSS à chaque requête (simulation d'obfuscation).

    Les données sont fixes (ANNONCES_ADAPTATIVES) mais les noms de classes changent :
    le sélecteur `div.annonce` deviendra `div.annonce-xkqmt` → un sélecteur classique casse,
    mais l'extraction adaptative retrouve les éléments par ressemblance à la signature.
    """
    sfx = _suffixe_aleatoire()
    cls_carte = f"annonce-{sfx}"
    cls_titre = f"titre-{sfx}"
    cls_prix = f"prix-{sfx}"
    cls_surface = f"surface-{sfx}"
    cartes = "".join(
        f"<div class='{cls_carte}'>"
        f"<h3 class='{cls_titre}'>{escape(a['titre'])}</h3>"
        f"<span class='{cls_prix}'>{escape(a['prix'])}</span>"
        f"<span class='{cls_surface}'>{escape(a['surface'])}</span>"
        f"</div>"
        for a in ANNONCES_ADAPTATIVES
    )
    corps = f"""<p>Les classes CSS de cette page changent à chaque requête (obfuscation simulée).</p>
<p id="info-classes" data-carte="{cls_carte}" data-titre="{cls_titre}"
   data-prix="{cls_prix}" data-surface="{cls_surface}">
  Classes actuelles : carte={cls_carte}, titre={cls_titre}, prix={cls_prix}, surface={cls_surface}
</p>
<div id="annonces">{cartes}</div>"""
    return gabarit("Extraction adaptative", corps, jeton, honeypot=honeypot)


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


# Champ piège du formulaire de connexion : un humain ne le remplit jamais (invisible).
HONEYPOT_CONNEXION = (
    '<label class="sl-hp" aria-hidden="true">Site web <input name="sl_site" tabindex="-1" autocomplete="off"></label>'
)


def connexion(jeton: str, honeypot: bool = False, erreur: str = "") -> str:
    """Formulaire de connexion du niveau authentifié (porte la furtivité via l'observateur)."""
    piege = HONEYPOT_CONNEXION if honeypot else ""
    alerte = f'<p id="connexion-erreur" class="erreur" role="alert">{escape(erreur)}</p>' if erreur else ""
    corps = f"""{alerte}<form id="formulaire-connexion" method="post" action="/lab/connexion">
<label>Identifiant <input id="champ-identifiant" name="identifiant" required maxlength="60"
 autocomplete="username"></label>
<label>Mot de passe <input id="champ-mot-de-passe" name="mot_de_passe" type="password" required
 maxlength="120" autocomplete="current-password"></label>
{piege}
<button id="bouton-connexion" type="submit">Se connecter</button>
</form>
<p class="indice">Comptes de test : <code>demo</code>, <code>analyste</code>.</p>"""
    return gabarit("Connexion", corps, jeton, honeypot=honeypot)


def espace(jeton: str, identifiant: str) -> str:
    """Zone réservée servie après une connexion réussie."""
    corps = f"""<p id="espace-prive" data-compte="{escape(identifiant)}">Bienvenue dans l'espace privé,
 {escape(identifiant)}.</p>
<p>Contenu réservé aux sessions authentifiées de l'Arena.</p>
<p><a id="lien-deconnexion" href="/lab/deconnexion">Se déconnecter</a></p>"""
    return gabarit("Espace privé", corps, jeton)


def recaptcha_v3(jeton: str, site_key: str) -> str:
    """Démo reCAPTCHA v3 RÉEL : charge le v3 de Google et affiche le score attribué au navigateur.

    v3 est purement scoré (aucun puzzle) : passer = être perçu comme humain. Les clés viennent
    de l'environnement (`SHADOWLAB_RECAPTCHA_V3_SITE` / `_SECRET`), jamais du code.
    """
    sess = escape(jeton)
    if not site_key:
        bloc = (
            '<div id="v3-resultat" data-pret="0"><p>État : <span id="v3-etat">clés absentes</span></p>'
            '<p>Score : <span id="v3-score"></span></p></div>'
            '<p class="indice">Configure <code>SHADOWLAB_RECAPTCHA_V3_SITE</code> et '
            "<code>SHADOWLAB_RECAPTCHA_V3_SECRET</code> dans <code>.env</code>, autorise "
            "<code>localhost</code> sur la clé, puis recharge.</p>"
        )
        script = ""
    else:
        sk_url = escape(site_key)
        sk_js = json.dumps(site_key)
        bloc = (
            '<div id="v3-resultat" data-pret="0"><p>État : <span id="v3-etat">en cours…</span></p>'
            '<p>Score reCAPTCHA v3 : <span id="v3-score"></span></p></div>'
        )
        script = (
            f'<script src="https://www.google.com/recaptcha/api.js?render={sk_url}"></script>\n'
            "<script>\n"
            "grecaptcha.ready(function(){\n"
            f"  grecaptcha.execute({sk_js}, {{action: 'demo'}}).then(function(token){{\n"
            "    fetch('/lab/recaptcha-v3/verifier', {method:'POST',"
            " headers:{'Content-Type':'application/json'}, body: JSON.stringify({token: token})})\n"
            "      .then(function(r){return r.json();}).then(function(d){\n"
            "        var box=document.getElementById('v3-resultat');\n"
            "        document.getElementById('v3-etat').textContent ="
            " d.success ? 'ok' : ('échec : ' + (d.erreur||''));\n"
            "        document.getElementById('v3-score').textContent ="
            " (d.score==null?'':String(d.score));\n"
            "        if(box){box.dataset.pret='1'; box.dataset.score=(d.score==null?'':String(d.score));"
            " box.dataset.success=String(!!d.success);}\n"
            "      }).catch(function(){document.getElementById('v3-etat').textContent='erreur réseau';});\n"
            "  });\n"
            "});\n"
            "</script>"
        )
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="sl-session" content="{sess}">
<title>reCAPTCHA v3 — ShadowLab</title>
<link rel="stylesheet" href="/lab/static/lab.css"></head>
<body>
<header><strong>ShadowLab · démo reCAPTCHA v3 réel</strong></header>
<main data-page="recaptcha-v3">
<h1>reCAPTCHA v3 (score réel)</h1>
<p>Cette page charge le vrai reCAPTCHA v3 et affiche le score que Google attribue à ce navigateur.
Score élevé = perçu comme humain. Aucune résolution de puzzle : v3 ne fait que noter.</p>
{bloc}
</main>
<script type="module" src="/lab/static/observateur.js"></script>
{script}
</body></html>"""


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
<label class="consentement"><input type="checkbox" name="consentement" value="oui" required>
J'accepte que ma session de navigation soit enregistrée comme référence humaine pour cette recherche.
Les données collectées (empreinte navigateur, séquence de pages, verdicts des détecteurs)
restent sur ce serveur local et ne sont pas transmises à l'extérieur.</label>
<button type="submit">Commencer une session manuelle</button></form>"""
    return gabarit("Session manuelle", corps, "")


def manuel_pret(lien: str) -> str:
    corps = f"""<p>Session prête. Elle passe par l'Arena : votre navigateur signalera un certificat local auto-signé,
à accepter pour continuer.</p>
<p><a id="entrer-arena" href="{escape(lien)}">Entrer dans l'Arena</a></p>"""
    return gabarit("Session manuelle", corps, "")


def _page_arena(type_page: str, titre: str, corps: str, scripts: str = "", jeton: str = "") -> str:
    """Page servie par une protection. Porte l'observateur si un jeton est fourni (collecte l'empreinte
    pendant le challenge pour alimenter le blocage différé)."""
    meta_session = f'\n<meta name="sl-session" content="{escape(jeton)}">' if jeton else ""
    observateur = '\n<script type="module" src="/lab/static/observateur.js"></script>' if jeton else ""
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">{meta_session}
<title>{escape(titre)} — ShadowLab</title>
<link rel="stylesheet" href="/lab/static/lab.css">
</head>
<body data-arena="{type_page}">
<main class="arena">
<h1>{escape(titre)}</h1>
{corps}
</main>
{observateur}{scripts}
</body>
</html>"""


def page_defi(defi: str, difficulte: int, retour: str, jeton: str = "") -> str:
    corps = f"""<p id="etat-defi">Vérification du navigateur en cours…</p>
<noscript><p>Cette vérification demande JavaScript.</p></noscript>
<div id="defi" hidden data-defi="{escape(defi)}" data-difficulte="{difficulte}" data-retour="{escape(retour)}"></div>"""
    return _page_arena(
        "defi", "Vérification", corps, '<script type="module" src="/lab/static/defi.js"></script>', jeton=jeton
    )


def page_captcha(captcha: str, retour: str, erreur: bool = False, jeton: str = "") -> str:
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
    return _page_arena("captcha", "Vérification humaine", corps, jeton=jeton)


def page_turnstile(site_key: str, retour: str, jeton: str = "") -> str:
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
        jeton=jeton,
    )


def page_recaptcha(site_key: str, retour: str, jeton: str = "") -> str:
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
        jeton=jeton,
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
