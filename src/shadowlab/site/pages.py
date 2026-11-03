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


def gabarit(titre: str, corps: str, jeton: str, scripts: tuple[str, ...] = ()) -> str:
    """Page complète : navigation, jeton de session et observateur JavaScript."""
    liens = "".join(f'<a href="{href}">{escape(nom)}</a>' for href, nom in NAVIGATION)
    balises = "".join(f'<script type="module" src="/lab/static/{nom}"></script>' for nom in scripts)
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
<main>
<h1>{escape(titre)}</h1>
{corps}
</main>
<footer>Site d'expérimentation local. Aucune donnée n'en sort. · <a href="/manuel/terminer">Terminer une session manuelle</a></footer>
<script type="module" src="/lab/static/observateur.js"></script>
{balises}
</body>
</html>"""


def accueil(jeton: str) -> str:
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
    return gabarit("Accueil", corps, jeton)


def statique(jeton: str) -> str:
    lignes = "".join(
        f"<tr><td class='reference'>{ref}</td><td>Pièce {n}</td><td>{100 + n * 7} €</td></tr>"
        for n, ref in enumerate(REFERENCES_STATIQUES, start=1)
    )
    corps = f"""<p>Page statique. Les dix références ci-dessous sont dans le HTML envoyé par le serveur.</p>
<table id="tableau-references"><thead><tr><th>Référence</th><th>Désignation</th><th>Prix</th></tr></thead>
<tbody>{lignes}</tbody></table>
<p><a href="/lab/catalogue">Voir le catalogue</a></p>"""
    return gabarit("HTML simple", corps, jeton)


def dynamique(jeton: str) -> str:
    corps = """<p>Le bloc ci-dessous est rempli par JavaScript 400 ms après le chargement.</p>
<div id="zone-dynamique" aria-live="polite">chargement…</div>"""
    return gabarit("JavaScript", corps, jeton, scripts=("dynamique.js",))


def catalogue(jeton: str, page: int) -> str:
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
    return gabarit(f"Catalogue — page {page}", corps, jeton)


def formulaire(jeton: str) -> str:
    options = "".join(f'<option value="{m}">{m}</option>' for m in MODELES)
    corps = f"""<form id="formulaire-essai" method="post" action="/lab/formulaire">
<label>Nom <input id="champ-nom" name="nom" required maxlength="60"></label>
<label>Modèle <select id="champ-modele" name="modele">{options}</select></label>
<button id="bouton-envoyer" type="submit">Envoyer</button>
</form>"""
    return gabarit("Formulaire", corps, jeton)


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
les faux positifs des détecteurs. Elle est enregistrée comme « humain » dans l'expérience
« sessions-manuelles ».</p>
<p>Ouvrez cette page dans votre navigateur habituel, puis parcourez librement le site pendant une minute
(cliquez, faites défiler, remplissez le formulaire) et revenez terminer la session.</p>
<form method="post" action="/manuel/commencer"><button type="submit">Commencer une session manuelle</button></form>"""
    return gabarit("Session manuelle", corps, "")


def fin_manuelle(classements: list[dict]) -> str:
    lignes = "".join(
        f"<tr><td>{escape(c['detector_name'])}</td><td>{escape(c['classification'])}</td></tr>" for c in classements
    )
    corps = f"""<p>Session enregistrée. Verdicts :</p>
<table><thead><tr><th>Détecteur</th><th>Classement</th></tr></thead><tbody>{lignes}</tbody></table>
<p><a href="/manuel">Nouvelle session</a> · <a href="/tableau">Tableau de bord</a></p>"""
    return gabarit("Session manuelle terminée", corps, "")
