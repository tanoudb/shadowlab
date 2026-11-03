"""Scénarios : suites d'actions sur le site de test, chacune avec un résultat attendu connu."""

from __future__ import annotations

import json
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .engines.base import Driver
from .site import pages


@dataclass
class Issue:
    success: bool
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    attend_js: bool  # la page porte l'observateur JavaScript
    executer: Callable[[Driver, str, str, random.Random], Issue]


def url(base: str, chemin: str, jeton: str) -> str:
    separateur = "&" if "?" in chemin else "?"
    return f"{base}{chemin}{separateur}sl={jeton}"


def static_html(d: Driver, base: str, jeton: str, rng: random.Random) -> Issue:
    d.navigate(url(base, "/lab/statique", jeton))
    references = [t.strip() for t in d.texts("td.reference")]
    return Issue(references == pages.REFERENCES_STATIQUES, {"references": len(references)})


def javascript_content(d: Driver, base: str, jeton: str, rng: random.Random) -> Issue:
    d.navigate(url(base, "/lab/dynamique", jeton))
    texte = d.wait_for_element("#resultat-js", timeout_ms=3000)
    return Issue(texte == pages.TEXTE_DYNAMIQUE, {"texte": texte})


def pagination(d: Driver, base: str, jeton: str, rng: random.Random) -> Issue:
    d.navigate(url(base, "/lab/catalogue?page=1", jeton))
    identifiants: list[str] = []
    pages_vues = 0
    while True:
        pages_vues += 1
        identifiants += [t.replace("Article ", "").strip() for t in d.texts("li.article")]
        if d.wait_for_element("a.suivant", timeout_ms=200) is None or pages_vues >= pages.NB_PAGES_CATALOGUE:
            break
        d.click("a.suivant")
    attendus = [f"ART-{n:03d}" for n in range(1, pages.NB_PAGES_CATALOGUE * pages.ARTICLES_PAR_PAGE + 1)]
    return Issue(identifiants == attendus, {"pages": pages_vues, "articles": len(identifiants)})


def form_interaction(d: Driver, base: str, jeton: str, rng: random.Random) -> Issue:
    nom = rng.choice(["Alice", "Bastien", "Chloé", "Driss", "Emma"])
    modele = rng.choice(pages.MODELES)
    d.navigate(url(base, "/lab/formulaire", jeton))
    d.fill("#champ-nom", nom)
    d.select("#champ-modele", modele)
    d.click("#bouton-envoyer")
    texte = d.wait_for_element("#confirmation", timeout_ms=3000)
    attendu = f"Merci {nom} — modèle {modele}"
    return Issue(texte == attendu, {"attendu": attendu, "obtenu": texte})


def session_cookies(d: Driver, base: str, jeton: str, rng: random.Random) -> Issue:
    d.navigate(url(base, "/lab/session", jeton))
    premier = d.wait_for_element("#compteur-visites")
    d.click("#recharger")
    second = d.wait_for_element("#compteur-visites")
    return Issue((premier, second) == ("1", "2"), {"compteurs": [premier, second]})


def fingerprint_observation(d: Driver, base: str, jeton: str, rng: random.Random) -> Issue:
    d.navigate(url(base, "/lab/empreinte", jeton))
    recue = d.wait_for_element("#observation-envoyee", timeout_ms=8000) is not None
    return Issue(recue, {"empreinte_envoyee": recue})


def detection_page(d: Driver, base: str, jeton: str, rng: random.Random) -> Issue:
    d.navigate(url(base, "/lab/detection", jeton))
    affiche = d.wait_for_element("#verdict-affiche", timeout_ms=8000) is not None
    return Issue(affiche, {"verdict_affiche": affiche})


def api_json(d: Driver, base: str, jeton: str, rng: random.Random) -> Issue:
    d.navigate(url(base, "/lab/api/articles?limite=25", jeton))
    try:
        donnees = json.loads(d.content())
    except ValueError:
        return Issue(False, {"erreur": "réponse non JSON"})
    articles = donnees.get("articles", [])
    return Issue(donnees.get("total") == 25 and len(articles) == 25, {"articles": len(articles)})


SCENARIOS: dict[str, Scenario] = {
    s.name: s
    for s in (
        Scenario("static_html", "Page statique : lire les 10 références du tableau", True, static_html),
        Scenario("javascript_content", "Lire un contenu ajouté par JavaScript", True, javascript_content),
        Scenario("pagination", "Parcourir 5 pages liées et lire 50 articles", True, pagination),
        Scenario("form_interaction", "Remplir et envoyer un formulaire", True, form_interaction),
        Scenario("session_cookies", "Garder un cookie de session entre deux pages", True, session_cookies),
        Scenario("fingerprint_observation", "Laisser la page relever l'empreinte", True, fingerprint_observation),
        Scenario("detection_page", "Afficher le verdict des détecteurs", True, detection_page),
        Scenario("api_json", "Lire une API JSON", False, api_json),
    )
}
