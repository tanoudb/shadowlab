"""Scénarios : suites d'actions sur le site de test, chacune avec un résultat attendu connu."""

from __future__ import annotations

import json
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit

from parsel import Selector

from .config import RACINE
from .engines.base import Driver, FonctionIndisponible, RefusProtection, ResultatNavigation
from .engines.noezia.parcours import MoteurDriver, Parcours
from .engines.noezia.recettes import PorteEntree, Recette, lire_texte
from .notation import noter_recolte
from .site import pages, vitrine

DELAI_DEFI_S = 20
NB_REQUETES_RAFALE = 30
PORTE_ENTREE_PASSAGE_S = (
    15  # attente de la porte d'entrée d'une recette lancée par l'Arena (défi d'entrée dès le niveau 04)
)


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


def _resoudre_challenge(d: Driver) -> None:
    """Résout les challenges de l'Arena que le navigateur peut traiter sans intervention humaine.

    - defi (PoW) : résolution automatique par le script defi.js, redirection incluse
    - turnstile (test keys) : le widget auto-valide, le moteur clique Envoyer
    - recaptcha (test keys) : clic sur la checkbox iframe puis Envoyer
    - captcha / blocage : aucune résolution automatique (retour → RefusProtection dans aller)
    """
    limite = time.monotonic() + DELAI_DEFI_S
    recaptcha_clique = False
    while time.monotonic() < limite:
        try:
            if not d.texts("body[data-arena]"):
                d.attendre_chargement()
                return
            if d.texts("body[data-arena='turnstile']"):
                etat = d.texts("#turnstile-etat")
                if etat and "reçue" in etat[0].lower():
                    d.click("#turnstile-envoyer")
                    time.sleep(0.5)
                    recaptcha_clique = False
                    continue
                time.sleep(0.1)
                continue
            if d.texts("body[data-arena='recaptcha']"):
                etat = d.texts("#recaptcha-etat")
                if etat and "reçue" in etat[0].lower():
                    d.click("#recaptcha-envoyer")
                    time.sleep(0.5)
                    recaptcha_clique = False
                    continue
                if not recaptcha_clique and hasattr(d, "_page"):
                    try:
                        fl = d._page.frame_locator("iframe[title='reCAPTCHA']")
                        fl.locator(".recaptcha-checkbox-border").click(timeout=3000)
                        recaptcha_clique = True
                    except Exception:  # noqa: BLE001, S110
                        pass
                time.sleep(0.2)
                continue
            if d.texts("body[data-arena='defi']"):
                time.sleep(0.05)
                continue
            return  # captcha, blocage : pas de résolution automatique
        except Exception:  # noqa: BLE001, S110 — document remplacé pendant la lecture : on relit
            pass
        time.sleep(0.05)


def aller(d: Driver, cible: str) -> ResultatNavigation:
    """Ouvre une page. Si une page de protection reste affichée, le scénario s'arrête là : `RefusProtection`."""
    resultat = d.navigate(cible)
    if resultat.status not in (403, None):
        return resultat
    if d.executes_javascript:
        _resoudre_challenge(d)
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
    marqueur = d.wait_for_element("#observation-envoyee", timeout_ms=8000)
    proprietes = d.wait_for_element("#proprietes", timeout_ms=500) or ""
    envoyee = marqueur is not None
    contenu_valide = envoyee and proprietes != "collecte en cours…" and len(proprietes) > 5
    return Issue(
        contenu_valide,
        {
            "empreinte_envoyee": envoyee,
            "contenu_valide": contenu_valide,
            "longueur_proprietes": len(proprietes),
        },
    )


def detection_page(d: Driver, base: str, jeton: str, rng: random.Random) -> Issue:
    aller(d, url(base, "/lab/detection", jeton))
    marqueur = d.wait_for_element("#verdict-affiche", timeout_ms=8000)
    tableau = d.wait_for_element("#verdicts tbody", timeout_ms=500) or ""
    affiche = marqueur is not None
    contenu_valide = affiche and "en attente" not in tableau and len(tableau) > 5
    return Issue(
        contenu_valide,
        {
            "verdict_affiche": affiche,
            "contenu_valide": contenu_valide,
            "longueur_tableau": len(tableau),
        },
    )


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
    ok = 0
    waf = 0
    rate_limit = 0
    erreur_serveur = 0
    protection = 0
    erreur_reseau = 0
    for rang in range(NB_REQUETES_RAFALE):
        page = rang % pages.NB_PAGES_CATALOGUE + 1
        try:
            resultat = aller(d, url(base, f"/lab/catalogue?page={page}", jeton))
            code = resultat.status or 0
            if 200 <= code <= 299:
                ok += 1
            elif code == 403:
                waf += 1
            elif code == 429:
                rate_limit += 1
            elif 500 <= code <= 599:
                erreur_serveur += 1
            else:
                erreur_reseau += 1
        except RefusProtection:
            protection += 1
        except Exception:  # noqa: BLE001
            erreur_reseau += 1
    refus = waf + rate_limit + protection
    return Issue(
        refus == 0 and erreur_serveur == 0,
        {
            "requetes": NB_REQUETES_RAFALE,
            "ok": ok,
            "waf_403": waf,
            "rate_limit_429": rate_limit,
            "erreur_serveur_5xx": erreur_serveur,
            "protection": protection,
            "erreur_reseau": erreur_reseau,
            "refus": refus,
        },
    )


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


def scrape_catalogue(d: Driver, base: str, jeton: str, rng: random.Random) -> Issue:
    """Scraping complet : parcourir toutes les pages du catalogue, extraire chaque article avec son ID."""
    articles_extraits: list[dict[str, str]] = []
    pages_visitees = 0
    for page_num in range(1, pages.NB_PAGES_CATALOGUE + 1):
        aller(d, url(base, f"/lab/catalogue?page={page_num}", jeton))
        pages_visitees += 1
        elements = d.texts("li.article")
        for texte in elements:
            article_id = texte.replace("Article ", "").strip()
            articles_extraits.append({"id": article_id, "page": page_num})
    attendus = [f"ART-{n:03d}" for n in range(1, pages.NB_PAGES_CATALOGUE * pages.ARTICLES_PAR_PAGE + 1)]
    ids_extraits = [a["id"] for a in articles_extraits]
    return Issue(
        ids_extraits == attendus,
        {
            "pages_visitees": pages_visitees,
            "articles_extraits": len(articles_extraits),
            "articles_attendus": len(attendus),
            "complet": ids_extraits == attendus,
        },
    )


def scrape_rapide(d: Driver, base: str, jeton: str, rng: random.Random) -> Issue:
    """Scraping rapide (scalping) : enchaîner des pages et extraire les données sans pause."""
    cibles = [
        ("/lab/statique", "td.reference", pages.REFERENCES_STATIQUES),
        ("/lab/catalogue?page=1", "li.article", [f"Article ART-{n:03d}" for n in range(1, 11)]),
        ("/lab/catalogue?page=2", "li.article", [f"Article ART-{n:03d}" for n in range(11, 21)]),
        ("/lab/catalogue?page=3", "li.article", [f"Article ART-{n:03d}" for n in range(21, 31)]),
        ("/lab/dynamique", "#resultat-js", [pages.TEXTE_DYNAMIQUE]),
    ]
    extractions_ok = 0
    resultats: list[dict] = []
    t0 = time.monotonic()
    for chemin, selecteur, attendu in cibles:
        aller(d, url(base, chemin, jeton))
        if selecteur == "#resultat-js":
            contenu = d.wait_for_element(selecteur, timeout_ms=3000)
            obtenu = [contenu] if contenu else []
        else:
            obtenu = [t.strip() for t in d.texts(selecteur)]
        ok = obtenu == attendu
        if ok:
            extractions_ok += 1
        resultats.append({"chemin": chemin, "ok": ok, "extraits": len(obtenu)})
    duree = time.monotonic() - t0
    return Issue(
        extractions_ok == len(cibles),
        {
            "cibles": len(cibles),
            "extractions_ok": extractions_ok,
            "duree_s": round(duree, 2),
            "resultats": resultats,
        },
    )


def connexion(d: Driver, base: str, jeton: str, rng: random.Random) -> Issue:
    """Le moteur se connecte au niveau authentifié et atteint l'espace privé.

    Aux niveaux 05-06, une porte comportementale garde la soumission (empreinte + comportement +
    honeypot + limite de tentatives) : y arriver = franchir un login protégé anti-bot. Le compte
    est une fixture de test (voir site/comptes.py : demo / arena-demo-2026).
    """
    aller(d, url(base, "/lab/connexion", jeton))
    d.fill("#champ-identifiant", "demo")  # jamais le champ piège sl_site (invisible)
    d.fill("#champ-mot-de-passe", "arena-demo-2026")
    d.click("#bouton-connexion")  # POST → 303 → /lab/espace si accepté
    textes = d.texts("#espace-prive")
    contenu = textes[0] if textes else ""
    atteint = "demo" in contenu
    return Issue(atteint, {"espace_atteint": atteint, "contenu": contenu[:120]})


def recaptcha_v3(d: Driver, base: str, jeton: str, rng: random.Random) -> Issue:
    """Démo : charge le vrai reCAPTCHA v3 et relève le score que Google attribue au moteur.

    Aucun puzzle résolu — v3 ne fait que noter. Un score élevé = le moteur est perçu comme humain.
    Nécessite `SHADOWLAB_RECAPTCHA_V3_SITE`/`_SECRET` dans l'environnement du site.
    """
    aller(d, url(base, "/lab/recaptcha-v3", jeton))
    limite = time.monotonic() + 20.0
    score_txt, etat = "", ""
    while time.monotonic() < limite:
        et = d.texts("#v3-etat")
        etat = et[0].strip() if et else ""
        sc = d.texts("#v3-score")
        if sc and sc[0].strip():
            score_txt = sc[0].strip()
            break
        if etat.startswith("échec") or etat.startswith("erreur") or etat == "clés absentes":
            break
        time.sleep(0.3)
    try:
        score = float(score_txt) if score_txt else None
    except ValueError:
        score = None
    return Issue(score is not None, {"score": score, "etat": etat})


def extraction_adaptative(d: Driver, base: str, jeton: str, rng: random.Random) -> Issue:
    """Extraire des données d'une page qui mute ses classes CSS à chaque requête.

    La page `/lab/adaptatif` génère des noms de classes aléatoires (obfuscation simulée). Au premier
    passage, le sélecteur initial (`div.annonce-*`) fonctionne et l'extracteur mémorise la signature.
    Au deuxième passage, les classes ont changé : le sélecteur casse, mais l'extracteur retrouve les
    éléments par ressemblance. Ce scénario ne nécessite **pas** JavaScript.
    """
    # Premier passage : on apprend les signatures sur la page
    aller(d, url(base, "/lab/adaptatif", jeton))
    html1 = d.content()
    from .engines.noezia.analyseur import Analyseur
    from .engines.noezia.extraction import Signatures

    sigs = Signatures()  # mémoire seule, pas de fichier
    url_page = f"{base}/lab/adaptatif"

    a1 = Analyseur(html1, url=url_page, signatures=sigs)

    # Lire les classes dynamiques du premier passage via l'élément #info-classes
    info = a1.attribut("#info-classes", "data-titre")
    if not info:
        return Issue(False, {"etape": "premier_passage", "erreur": "classes introuvables"})
    cls_titre = info  # ex: "titre-xkqmt"
    cls_prix = a1.attribut("#info-classes", "data-prix") or ""

    # Sélecteurs par classe — ils cassent au prochain passage (classes mutées)
    sel_titre = f"h3.{cls_titre}"
    sel_prix = f"span.{cls_prix}"

    titre1 = a1.extraire_adaptatif(sel_titre, "titre")
    prix1 = a1.extraire_adaptatif(sel_prix, "prix")

    if not titre1:
        return Issue(False, {"etape": "premier_passage", "erreur": "titre introuvable", "selecteur": sel_titre})

    # Deuxième passage : les classes ont muté, les sélecteurs du passage 1 cassent
    aller(d, url(base, "/lab/adaptatif", jeton))
    html2 = d.content()
    a2 = Analyseur(html2, url=url_page, signatures=sigs)

    # Vérifier que le sélecteur est bien cassé
    selecteur_casse = a2.css_un(sel_titre) is None

    # extraire_adaptatif doit retrouver les éléments par ressemblance à la signature
    titre2 = a2.extraire_adaptatif(sel_titre, "titre")
    prix2 = a2.extraire_adaptatif(sel_prix, "prix")

    titres_ok = titre1 and titre2 and pages.ANNONCES_ADAPTATIVES[0]["titre"] in titre1
    prix_ok = prix1 and prix2
    return Issue(
        bool(titres_ok and prix_ok and selecteur_casse),
        {
            "titre_passage_1": titre1,
            "titre_passage_2": titre2,
            "prix_passage_1": prix1,
            "prix_passage_2": prix2,
            "selecteur_casse": selecteur_casse,
            "signatures_memorisees": len(sigs._data),  # noqa: SLF001
        },
    )


def bot_sanity_check(d: Driver, base: str, jeton: str, rng: random.Random) -> Issue:
    """Validation externe : visite bot.incolumitas.com et extrait le score de détection.

    Le site est un détecteur de bot indépendant (NikolaiT). Le moteur doit passer
    les tests fingerprint et comportementaux du site tiers. Le paramètre `base` est ignoré
    (site externe fixe). `attend_js` = True car le site charge JavaScript.

    Structure du site (v0.6.3) :
    - #behavioralScore : score comportemental 0 (bot) → 1 (humain), mis à jour à 4/7/10/15s
    - #detection-tests : JSON avec résultats intoli + fpscanner (OK/FAIL par test)
    - pre : blocs JSON individuels (puppeteer, webdriver, codecs, etc.)
    """
    d.navigate("https://bot.incolumitas.com")
    time.sleep(18)

    resultats: dict[str, Any] = {}

    for sel in ("#behavioralScore", "#detection-tests", "#canvas_fingerprint", "#webgl_fingerprint"):
        try:
            texte = d.wait_for_element(sel, timeout_ms=3000)
            if texte:
                resultats[sel.lstrip("#")] = texte[:1000]
        except Exception:  # noqa: BLE001
            pass

    score_raw = resultats.get("behavioralScore", "")
    if score_raw in ("", "..."):
        for _ in range(6):
            time.sleep(2)
            try:
                texte = d.wait_for_element("#behavioralScore", timeout_ms=2000)
                if texte and texte not in ("", "..."):
                    resultats["behavioralScore"] = texte[:200]
                    break
            except Exception:  # noqa: BLE001
                pass

    try:
        all_text = d.content()
        resultats["page_length"] = len(all_text) if all_text else 0
    except Exception:  # noqa: BLE001
        resultats["page_length"] = 0

    if "detection-tests" in resultats:
        try:
            parsed = json.loads(resultats["detection-tests"])
            resultats["detection_tests_json"] = parsed
            fails = []
            for suite, tests in parsed.items():
                if isinstance(tests, dict):
                    for test_name, result in tests.items():
                        if result == "FAIL":
                            fails.append(f"{suite}.{test_name}")
            resultats["fails"] = fails
            resultats["fail_count"] = len(fails)
            total = sum(len(t) for t in parsed.values() if isinstance(t, dict))
            resultats["total_tests"] = total
            resultats["pass_count"] = total - len(fails)
        except (json.JSONDecodeError, TypeError):
            pass

    score_text = resultats.get("behavioralScore", "")
    try:
        score = float(score_text)
        resultats["behavioral_score_num"] = score
    except (ValueError, TypeError):
        score = None

    if score is not None:
        is_human = score >= 0.5
    else:
        fail_count = resultats.get("fail_count", 0)
        total = resultats.get("total_tests", 0)
        is_human = total > 0 and fail_count == 0

    resultats["verdict_externe"] = "humain" if is_human else "bot"
    return Issue(is_human, resultats)


CHAMPS_FICHE = [
    "reference",
    "titre",
    "type_bien",
    "ville",
    "code_postal",
    "surface",
    "pieces",
    "prix",
    "dpe",
    "description",
    "date_publication",
    "nb_photos",
    "agence",
    "telephone",
]
CHAMPS_ENTIERS = ("surface", "pieces", "prix", "nb_photos")


def _lire_fiche(html: str) -> dict[str, Any]:
    """Champs présents sur une fiche (`data-champ`) : valeur brute `data-valeur` si elle existe, sinon le texte."""
    sel = Selector(html)
    annonce: dict[str, Any] = {}
    for champ in CHAMPS_FICHE:
        noeud = sel.css(f'[data-champ="{champ}"]')
        if not noeud:
            continue
        valeur = noeud[0].attrib.get("data-valeur")
        if valeur is None:
            valeur = "".join(noeud[0].css("::text").getall()).strip()
        if champ in CHAMPS_ENTIERS:
            try:
                valeur = int(valeur)
            except ValueError:
                pass
        annonce[champ] = valeur
    return annonce


def _avec_jeton(cible: str, jeton: str) -> str:
    return f"{cible}{'&' if '?' in cible else '?'}sl={jeton}"


def recolte_vitrine(d: Driver, base: str, jeton: str, rng: random.Random) -> Issue:
    """Récolte complète du site vitrine : toute la liste (lien « suivante »), puis chaque fiche, 14 champs.

    Le résultat est noté contre la vérité du site (`notation.noter_recolte`) : réussi = complétude 1 et exactitude 1.
    Seule l'interface `Driver` sert (`navigate` via `aller`, puis `dom()` analysé avec parsel) : tous les pilotes
    conviennent, JavaScript ou non. Une protection qui interrompt le parcours laisse une récolte partielle, notée aussi.
    """
    from .config import charger

    reglages = charger()
    verite = vitrine.verite(reglages.vitrine_graine, reglages.vitrine_taille)
    recolte: list[dict[str, Any]] = []
    details: dict[str, Any] = {"pages_liste": 0, "fiches_ouvertes": 0}
    try:
        page_liste = urljoin(f"{base}/", "lab/vitrine/annonces")
        vues: set[str] = set()
        ouvertes: set[str] = set()
        limite_pages = 2 * verite["nb_pages"] + 2  # garde-fou contre une pagination qui boucle
        while page_liste and page_liste not in vues and len(vues) < limite_pages:
            vues.add(page_liste)
            aller(d, _avec_jeton(page_liste, jeton))
            details["pages_liste"] += 1
            sel = Selector(d.dom())
            liens = [urljoin(page_liste, h) for h in sel.css("a.fiche::attr(href)").getall()]
            suivante = sel.css('a[rel="next"]::attr(href)').get()
            suite = urljoin(page_liste, suivante) if suivante else ""
            # Les fiches de la page s'ouvrent avant de passer à la suivante : une récolte interrompue reste partielle.
            for lien in dict.fromkeys(liens):
                if lien in ouvertes:
                    continue
                ouvertes.add(lien)
                aller(d, _avec_jeton(lien, jeton))
                details["fiches_ouvertes"] += 1
                annonce = _lire_fiche(d.dom())
                if annonce:
                    recolte.append(annonce)
            page_liste = suite
    except RefusProtection as exc:
        details["refus"] = str(exc)
    note = noter_recolte(recolte, verite)
    details["recolte"] = note
    return Issue(note["completude"] == 1 and note["exactitude"] == 1, details)


class _MoteurDuPassage(MoteurDriver):
    """Le pilote du passage vu comme moteur de récolte : il appartient à la campagne (ouvert et fermé par elle,
    ni double ouverture ni session perdue), et chaque adresse demandée porte le jeton du passage.

    Le jeton `sl` est ce qui donne son niveau à la requête : le frontal de l'Arena lit le niveau (01 à 07) dans la
    table des passages, par ce jeton ; sans lui la requête reçoit `PROFIL_SANS_SESSION`.
    """

    def __init__(self, driver: Driver, nom: str, jeton: str) -> None:
        super().__init__(driver, nom)
        self._jeton = jeton

    def ouvrir(self) -> None:
        pass

    def fermer(self) -> None:
        pass

    def lire(self, adresse: str):  # noqa: ANN201 — `Reponse` du parcours
        if "sl" not in parse_qs(urlsplit(adresse).query):  # un seul `sl` : deux jetons = aucune session
            adresse = _avec_jeton(adresse, self._jeton)
        return super().lire(adresse)


def _moteur_de_recolte(d: Driver) -> str:
    """`http` pour curl-cffi, `navigateur` pour noezia en identité native ; tout autre moteur est refusé."""
    if d.name == "curl-cffi":
        return "http"
    if d.name == "noezia":
        if d.configuration().get("identite_native") is True:
            return "navigateur"
        raise FonctionIndisponible(
            "la récolte ne pilote noezia qu'en identité native (`identite_native: true`, vrai Chrome) : "
            "c'est la seule configuration du moteur « navigateur »"
        )
    raise FonctionIndisponible(
        f"la récolte ne sait pas piloter le moteur « {d.name} » : seuls curl-cffi (moteur http) "
        "et noezia en identité native (moteur navigateur) sont pris en charge"
    )


def recette_du_passage(nom: str, base: str) -> tuple[Recette, str]:
    """La recette `configs/recettes/<nom>.yaml` pointée vers l'entrée du passage (`base`, ex. l'Arena), avec le
    paramètre `sl` ignoré dans les adresses canoniques. Rend la recette et le texte du fichier."""
    chemin = RACINE / "configs" / "recettes" / f"{nom}.yaml"
    texte = chemin.read_text(encoding="utf-8")
    recette = lire_texte(texte, source=str(chemin))
    departs = []
    for depart in recette.depart:
        morceaux = urlsplit(depart.url)
        cible = morceaux.path + (f"?{morceaux.query}" if morceaux.query else "")
        departs.append(depart.model_copy(update={"url": urljoin(f"{base}/", cible.lstrip("/"))}))
    ignores = list(dict.fromkeys([*recette.parametres_ignores, "sl"]))
    reglages = {"depart": departs, "hotes": [urlsplit(base).hostname or ""], "parametres_ignores": ignores}
    if (
        recette.porte_entree is None
    ):  # l'Arena sert un défi d'entrée dès le niveau 04 ; la recette du fichier garde la sienne
        reglages["porte_entree"] = PorteEntree(attendre_s=PORTE_ENTREE_PASSAGE_S)
    recette = recette.model_copy(update=reglages)
    return recette, texte


def _recolter_avec_recette(
    d: Driver, base: str, jeton: str, rng: random.Random, recette_nom: str, verite: str
) -> Issue:
    """Lance le parcours de `shadowlab recolte` avec la recette `recette_nom` dans le passage, puis le note."""
    import tempfile
    from pathlib import Path

    from . import commande_recolte
    from .config import charger
    from .engines.noezia.etat import Etat

    nom_moteur = _moteur_de_recolte(d)
    reglages = charger()
    recette, texte = recette_du_passage(recette_nom, base)
    moteur = _MoteurDuPassage(d, nom_moteur, jeton)
    avant = getattr(d, "hotes_navigation", None)
    if nom_moteur == "navigateur":  # garde du cadre principal : seuls les hôtes de la recette
        d.hotes_navigation = tuple(h.lower() for h in recette.hotes)  # type: ignore[attr-defined]
    try:
        with tempfile.TemporaryDirectory(prefix="shadowlab-recolte-") as dossier:
            parcours = Parcours(recette, texte, recette_nom, moteur, Path(dossier), ecran=lambda _: None, alea=rng)
            bilan = parcours.lancer()
            etat = Etat(Path(dossier) / "etat.sqlite3")
            try:
                note = commande_recolte.evaluer_passe(etat, bilan.passe, verite, reglages)
            finally:
                etat.fermer()
    finally:
        if nom_moteur == "navigateur":
            d.hotes_navigation = avant  # type: ignore[attr-defined]
    details: dict[str, Any] = {
        "moteur": nom_moteur,
        "recette": recette_nom,
        "statut": bilan.statut,
        "arret": bilan.arret,
        "pages_faites": bilan.resume["pages"]["faites"],
        "pages_en_echec": bilan.resume["pages"]["echecs"],
        "recolte": note,
    }
    if bilan.arret:
        details["refus"] = f"{bilan.arret['detail']} ({bilan.arret['adresse']})"
    return Issue(note["reussi"] and bilan.statut == "terminee", details)


def recolte_recette_vitrine(d: Driver, base: str, jeton: str, rng: random.Random) -> Issue:
    """Récolte générale de la vitrine (recette `vitrine.yaml`) : pages, enregistrements et champs notés, 99 % requis."""
    return _recolter_avec_recette(d, base, jeton, rng, "vitrine", "vitrine")


def recolte_recette_rallye(d: Driver, base: str, jeton: str, rng: random.Random) -> Issue:
    """Récolte générale du site de rallye (recette `rallye-demo.yaml`) : saisons, rallyes, spéciales, temps, pilotes…"""
    return _recolter_avec_recette(d, base, jeton, rng, "rallye-demo", "rallye")


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
        Scenario("scrape_catalogue", "Scraping complet du catalogue (5 pages, 50 articles)", True, scrape_catalogue),
        Scenario("scrape_rapide", "Scraping rapide (scalping) : 5 pages, extraction sans pause", True, scrape_rapide),
        Scenario("recaptcha_v3", "Démo reCAPTCHA v3 réel : relever le score attribué au moteur", True, recaptcha_v3),
        Scenario("connexion", "Se connecter au niveau authentifié et atteindre l'espace privé", True, connexion),
        Scenario(
            "recolte_vitrine",
            "Récolter tout le site vitrine (liste et fiches) et noter complétude et exactitude",
            True,
            recolte_vitrine,
        ),
        Scenario(
            "recolte_recette_vitrine",
            "Récolte générale (recette) du site vitrine, notée en pages, enregistrements et champs",
            True,
            recolte_recette_vitrine,
        ),
        Scenario(
            "recolte_recette_rallye",
            "Récolte générale (recette) du site de rallye, notée en pages, enregistrements et champs",
            True,
            recolte_recette_rallye,
        ),
        Scenario(
            "extraction_adaptative",
            "Extraire des données malgré la mutation des classes CSS (obfuscation)",
            False,
            extraction_adaptative,
        ),
        Scenario(
            "bot_sanity_check",
            "Validation externe : score bot.incolumitas.com (détecteur indépendant)",
            True,
            bot_sanity_check,
        ),
    )
}
