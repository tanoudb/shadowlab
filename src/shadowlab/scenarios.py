"""Scénarios : suites d'actions sur le site de test, chacune avec un résultat attendu connu."""

from __future__ import annotations

import json
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .engines.base import Driver, RefusProtection, ResultatNavigation
from .site import pages

DELAI_DEFI_S = 20
NB_REQUETES_RAFALE = 30


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


def _attendre_fin_du_defi(d: Driver) -> None:
    """Un navigateur résout seul le défi, comme pour une personne, puis revient à la page demandée."""
    limite = time.monotonic() + DELAI_DEFI_S
    while time.monotonic() < limite:
        try:
            if not d.texts("body[data-arena='defi']"):
                d.attendre_chargement()
                return
        except Exception:  # noqa: BLE001, S110 — document remplacé pendant la lecture : on relit
            pass
        time.sleep(0.02)


def aller(d: Driver, cible: str) -> ResultatNavigation:
    """Ouvre une page. Si une page de protection reste affichée, le scénario s'arrête là : `RefusProtection`."""
    resultat = d.navigate(cible)
    if resultat.status not in (403, None):
        return resultat
    if d.executes_javascript:
        _attendre_fin_du_defi(d)
    if d.texts("body[data-arena]"):
        raise RefusProtection(f"page de protection à la place de {cible.split('?')[0]}")
    if not d.executes_javascript and resultat.status == 403:
        raise RefusProtection(f"refus 403 sur {cible.split('?')[0]}")
    return resultat


def static_html(d: Driver, base: str, jeton: str, rng: random.Random) -> Issue:
    aller(d, url(base, "/lab/statique", jeton))
    references = [t.strip() for t in d.texts("td.reference")]
    return Issue(references == pages.REFERENCES_STATIQUES, {"references": len(references)})


def javascript_content(d: Driver, base: str, jeton: str, rng: random.Random) -> Issue:
    aller(d, url(base, "/lab/dynamique", jeton))
    texte = d.wait_for_element("#resultat-js", timeout_ms=3000)
    return Issue(texte == pages.TEXTE_DYNAMIQUE, {"texte": texte})


def pagination(d: Driver, base: str, jeton: str, rng: random.Random) -> Issue:
    aller(d, url(base, "/lab/catalogue?page=1", jeton))
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
    aller(d, url(base, "/lab/formulaire", jeton))
    d.fill("#champ-nom", nom)
    d.select("#champ-modele", modele)
    d.click("#bouton-envoyer")
    texte = d.wait_for_element("#confirmation", timeout_ms=3000)
    attendu = f"Merci {nom} — modèle {modele}"
    return Issue(texte == attendu, {"attendu": attendu, "obtenu": texte})


def session_cookies(d: Driver, base: str, jeton: str, rng: random.Random) -> Issue:
    aller(d, url(base, "/lab/session", jeton))
    premier = d.wait_for_element("#compteur-visites")
    d.click("#recharger")
    second = d.wait_for_element("#compteur-visites")
    return Issue((premier, second) == ("1", "2"), {"compteurs": [premier, second]})


def fingerprint_observation(d: Driver, base: str, jeton: str, rng: random.Random) -> Issue:
    aller(d, url(base, "/lab/empreinte", jeton))
    recue = d.wait_for_element("#observation-envoyee", timeout_ms=8000) is not None
    return Issue(recue, {"empreinte_envoyee": recue})


def detection_page(d: Driver, base: str, jeton: str, rng: random.Random) -> Issue:
    aller(d, url(base, "/lab/detection", jeton))
    affiche = d.wait_for_element("#verdict-affiche", timeout_ms=8000) is not None
    return Issue(affiche, {"verdict_affiche": affiche})


def api_json(d: Driver, base: str, jeton: str, rng: random.Random) -> Issue:
    aller(d, url(base, "/lab/api/articles?limite=25", jeton))
    try:
        donnees = json.loads(d.content())
    except ValueError:
        return Issue(False, {"erreur": "réponse non JSON"})
    articles = donnees.get("articles", [])
    return Issue(donnees.get("total") == 25 and len(articles) == 25, {"articles": len(articles)})


def burst_crawl(d: Driver, base: str, jeton: str, rng: random.Random) -> Issue:
    """Suite rapide de pages sans pause : c'est ce scénario qui éprouve la limitation de débit."""
    refus = 0
    for rang in range(NB_REQUETES_RAFALE):
        page = rang % pages.NB_PAGES_CATALOGUE + 1
        try:
            if aller(d, url(base, f"/lab/catalogue?page={page}", jeton)).status != 200:
                refus += 1
        except RefusProtection:
            refus += 1
    return Issue(refus == 0, {"requetes": NB_REQUETES_RAFALE, "refus": refus})


def synthetic_browse(d: Driver, base: str, jeton: str, rng: random.Random) -> Issue:
    """Référence synthétique : parcours scripté avec souris, défilement et pauses tirées au sort.

    Il sert à éprouver les règles de comportement face à un automate qui bouge. Ce n'est PAS une session humaine :
    il reste compté « automatisé » et n'entre jamais dans les faux positifs.
    """

    def pause(minimum: float, maximum: float) -> None:
        time.sleep(rng.uniform(minimum, maximum))

    def gestes(nombre: int) -> None:
        for _ in range(nombre):
            d.deplacer_souris(rng.randint(20, 900), rng.randint(20, 600))
            pause(0.03, 0.12)

    aller(d, url(base, "/lab/", jeton))
    gestes(6)
    d.defiler(rng.randint(120, 400))
    pause(0.2, 0.5)
    d.click("main a[href='/lab/catalogue']")
    gestes(4)
    d.defiler(rng.randint(120, 400))
    pause(0.2, 0.5)
    aller(d, url(base, "/lab/formulaire", jeton))
    gestes(3)
    nom = rng.choice(["Alice", "Bastien", "Chloé", "Driss", "Emma"])
    modele = rng.choice(pages.MODELES)
    d.fill("#champ-nom", nom)
    pause(0.1, 0.3)
    d.select("#champ-modele", modele)
    gestes(2)
    d.click("#bouton-envoyer")
    texte = d.wait_for_element("#confirmation", timeout_ms=3000)
    attendu = f"Merci {nom} — modèle {modele}"
    return Issue(texte == attendu, {"attendu": attendu, "obtenu": texte})


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
        Scenario("burst_crawl", f"Enchaîner {NB_REQUETES_RAFALE} pages sans pause", True, burst_crawl),
        Scenario(
            "synthetic_browse", "Référence synthétique : parcours scripté avec souris et pauses", True, synthetic_browse
        ),
    )
}
