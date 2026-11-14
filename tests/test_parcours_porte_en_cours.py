"""Repasser la porte en cours de passe (`porte_entree.repassages_max`) : sur option, borné, sans action, tracé.

Le laissez-passer d'une protection expire (le cookie de défi de l'Arena vit une heure) : une passe plus longue est
redéfiée en plein travail. Sans l'option, ce défi arrête la passe, comme avant. Avec l'option, il est attendu SANS
AUCUNE action (comme à la porte d'entrée), au plus `repassages_max` fois, jamais moins de `ecart_min_s` après le
passage précédent (entrée comprise), et chaque passage est tracé et compté.

Pilote factice qui se comporte comme un navigateur (JavaScript, page relue sans nouvelle requête) : ni réseau ni
navigateur. Temps figé : l'horloge factice avance d'un pas fixe à chaque page demandée et l'horodatage la suit (l'écart
entre deux passages se compte sur l'horodatage, qui survit à une reprise). Les pages de défi sont écrites à la main.
"""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta

import pytest
from outils_recolte import GRAINE, RECETTE_VITRINE, TAILLE, Horloge, PiloteFactice, creer_client, fabriquer, lu

from shadowlab import notation
from shadowlab.engines.noezia import recettes
from shadowlab.engines.noezia.etat import Etat
from shadowlab.site import vitrine

PAGE_ARENA = (
    "<!doctype html><html><head><title>Vérification — ShadowLab</title></head>"
    '<body data-arena="defi"><main class="arena"><h1>Vérification</h1><div id="defi" hidden></div></main></body></html>'
)
DEBUT = datetime(2026, 11, 14, 8, 0, tzinfo=UTC)
LISTE = "=/lab/vitrine/annonces"  # 1re page de la passe
CINQUIEME = "AN-000004"  # 5e page : la liste, puis AN-000001 à AN-000004
BASE_SITE = "http://127.0.0.1:8770"
BASE_ARENA = "https://localhost:8743"
JETON = "ab" * 16


class PiloteNavigateur(PiloteFactice):
    """Se comporte comme `DriverNoezia` (comme le pilote de `test_sentinelle.py`) : exécute du JavaScript, la page
    peut changer sans nouvelle requête. `apres_attente` : l'état de la page (statut, contenu) à chaque relecture, dans
    l'ordre ; vide, la page reste celle de la dernière navigation, statut compris (comme `etat_page` d'un vrai
    Chrome)."""

    runtime = "navigateur"
    executes_javascript = True

    def __init__(self, client, horloge: Horloge | None = None, pas_s: float = 0.0):
        super().__init__(client)
        self.horloge = horloge or Horloge()
        self.apres_attente: list[tuple[int, str]] = []
        self.relectures = 0
        self._courant: int | None = None
        self._frais = False
        avancer_a_chaque_page(self, pas_s)

    def navigate(self, url):
        resultat = super().navigate(url)
        self._frais = True  # le premier `etat_page` qui suit est celui de `MoteurDriver.lire` (en-têtes)
        self._courant = resultat.status
        return resultat

    def etat_page(self):
        if self._frais:
            self._frais = False
            return self._courant, self.urls[-1], {}
        self.relectures += 1
        if self.apres_attente:
            self._courant, self._texte = self.apres_attente.pop(0)
        return self._courant, self.urls[-1], {}


class PiloteNoezia(PiloteNavigateur):
    """Le même, vu par une campagne comme `noezia` en identité native (le moteur `navigateur` de la récolte)."""

    name = "noezia"

    def __init__(self, client):
        super().__init__(client)
        self.options = {"headless": False, "channel": "chrome", "identite_native": True}
        self.hotes_navigation = None


def avancer_a_chaque_page(pilote, pas_s: float) -> None:
    """Chaque page demandée (hors robots.txt) prend `pas_s` secondes sur l'horloge factice du pilote."""

    def avancer() -> None:
        pilote.horloge.t += pas_s

    pilote.pendant = avancer


@pytest.fixture
def site(reglages, monkeypatch):
    with creer_client(monkeypatch) as client:
        yield client


@pytest.fixture
def dossier(tmp_path):
    return tmp_path / "recoltes" / "vitrine-annonces"


def recette(repassages_max=None, ecart_min_s=None, attendre_s=15):
    """La recette de la vitrine avec une porte d'entrée ; les clés de repassage seulement si elles sont données."""
    lignes = ["porte_entree:", f"  attendre_s: {attendre_s}"]
    if repassages_max is not None:
        lignes.append(f"  repassages_max: {repassages_max}")
    if ecart_min_s is not None:
        lignes.append(f"  ecart_min_s: {ecart_min_s}")
    return RECETTE_VITRINE.read_text(encoding="utf-8") + "\n" + "\n".join(lignes) + "\n"


def parcours(dossier, pilote, texte):
    """Un parcours dont l'horodatage suit l'horloge factice du pilote."""
    h = pilote.horloge
    return fabriquer(
        dossier,
        pilote,
        texte=texte,
        horloge=h,
        horodatage=lambda: (DEBUT + timedelta(seconds=h.t)).isoformat(timespec="seconds"),
    )


def vraie(pilote, ref=None):
    """La vraie page (la liste, ou la fiche `ref`) telle que le site l'envoie."""
    return pilote.client.get("/lab/vitrine/annonces" + (f"/{ref}" if ref else "")).text


def demandes_de(pilote, fragment):
    return sum(fragment in d for d in pilote.demandes)


def repassages_traces(dossier, passe=1):
    etat = Etat(dossier / "etat.sqlite3")
    try:
        return [e["detail"] for e in etat.evenements(passe) if e["genre"] == "porte_repassage"]
    finally:
        etat.fermer()


def verifier_complet(dossier, pilote):
    """48 pages faites, 45 annonces exactes, aucune page demandée deux fois, la page du défi lue comme les autres."""
    etat = Etat(dossier / "etat.sqlite3")
    try:
        note = notation.noter_recolte(etat.enregistrements("annonces"), vitrine.verite(GRAINE, TAILLE))
        assert note["completude"] == 1 and note["exactitude"] == 1
        c = etat.compteurs(1)
        assert c["faites"] == 48 and c["a_faire"] == 0 and c["echecs"] == 0 and c["anormales"] == 0
        ligne = next(p for p in etat.lignes_pages(1) if p["adresse"].endswith(CINQUIEME))
        assert ligne["statut"] == 200 and ligne["decision"] == "ok"
    finally:
        etat.fermer()
    pages = [d for d in pilote.demandes if not d.startswith("/robots.txt")]
    assert len(pages) == len(set(pages)) == 48, "une page a été demandée deux fois"


def verifier_arret_sans_suite(dossier, pilote, adresse_en_file):
    """La page du défi reste à faire, rien n'est demandé après elle."""
    etat = Etat(dossier / "etat.sqlite3")
    try:
        assert etat.pages(1, "en_cours") == 0 and etat.pages(1, "a_faire") > 0
        assert not any(adresse_en_file in a for a in etat.adresses_lues(1))
    finally:
        etat.fermer()
    assert pilote.demandes[-1].endswith(adresse_en_file)


# --- (a) Sans l'option : comme avant ----------------------------------------------------------


@pytest.mark.parametrize(
    ("porte", "statut", "signe"),
    [(False, 403, "statut"), (True, 403, "statut"), (True, 200, "defi")],
    ids=["sans-porte-403", "porte-sans-repassage-403", "porte-sans-repassage-200"],
)
def test_sans_l_option_un_defi_a_la_cinquieme_page_arrete_comme_avant(dossier, site, porte, statut, signe):
    pilote = PiloteNavigateur(site, pas_s=100)
    pilote.reponses[CINQUIEME] = (statut, PAGE_ARENA)
    pilote.apres_attente = [(200, vraie(pilote, CINQUIEME))]  # le défi se lèverait : sans l'option, on ne regarde pas
    p = parcours(dossier, pilote, recette() if porte else RECETTE_VITRINE.read_text(encoding="utf-8"))
    bilan = p.lancer()
    assert bilan.code == 3 and bilan.statut == "arretee" and bilan.arret["signe"] == signe
    if signe == "statut":
        assert bilan.arret["detail"] == "statut 403"
    assert pilote.relectures == 0 and p.horloge_factice.pauses == []
    verifier_arret_sans_suite(dossier, pilote, CINQUIEME)
    assert lu(dossier).get("porte_repassages") is None


# --- (b) (c) Avec l'option : la porte est repassée, sans action -------------------------------


def test_avec_l_option_un_defi_qui_se_leve_seul_a_la_cinquieme_page_la_passe_se_termine(dossier, site):
    pilote = PiloteNavigateur(site, pas_s=100)
    pilote.reponses[CINQUIEME] = (403, PAGE_ARENA)  # l'Arena sert son défi en 403, à l'adresse de la page
    pilote.apres_attente = [(403, PAGE_ARENA), (200, vraie(pilote, CINQUIEME))]
    p = parcours(dossier, pilote, recette(repassages_max=3))
    bilan = p.lancer()
    assert bilan.code == 0 and bilan.statut == "terminee", bilan.arret
    verifier_complet(dossier, pilote)
    assert demandes_de(pilote, CINQUIEME) == 1  # aucune nouvelle requête, aucun rechargement, aucun clic
    assert pilote.relectures == 2 and p.horloge_factice.pauses == [1.0]
    attendu = {
        "adresse": f"{BASE_SITE}/lab/vitrine/annonces/{CINQUIEME}",
        "rang": 5,
        "defi": "arena",
        "franchie": True,
        "attente_s": 1.0,
        "ecart_s": 500.0,  # 5 pages de 100 s depuis le début de la passe (aucune porte à l'entrée)
        "rafale": False,
    }
    assert bilan.resume["porte_repassages"] == {
        "repassages_max": 3,
        "ecart_min_s": 300,
        "nombre": 1,
        "passages": [attendu],
    }
    assert lu(dossier)["porte_repassages"]["nombre"] == 1
    assert repassages_traces(dossier) == [attendu]
    assert bilan.resume["porte_entree"] is None  # la porte d'entrée garde son propre compte
    assert any("Porte repassée" in ligne for ligne in p.sortie_ecran)


def test_avec_l_option_un_statut_perime_en_cours_de_passe_n_arrete_pas(dossier, site):
    # Le défi s'est validé pendant la lecture (en campagne, le pilote de l'Arena le franchit pendant `navigate`) :
    # le statut rendu est celui de la page de défi, la page affichée est déjà la vraie.
    pilote = PiloteNavigateur(site, pas_s=100)
    fiche = vraie(pilote, CINQUIEME)
    pilote.reponses[CINQUIEME] = (403, fiche)
    pilote.apres_attente = [(200, fiche)]
    p = parcours(dossier, pilote, recette(repassages_max=3))
    bilan = p.lancer()
    assert bilan.code == 0 and bilan.statut == "terminee", bilan.arret
    verifier_complet(dossier, pilote)
    assert pilote.relectures == 1 and p.horloge_factice.pauses == []  # un regard sur place, aucune attente
    passage = bilan.resume["porte_repassages"]["passages"][0]
    assert passage["defi"] == "statut 403" and passage["franchie"] is True and passage["attente_s"] == 0.0
    assert passage["rang"] == 5 and bilan.resume["porte_repassages"]["nombre"] == 1


# --- (d) (e) (f) (g) Les bornes : arrêt comme avant ------------------------------------------


def test_un_defi_qui_ne_se_leve_pas_dans_le_temps_arrete_la_passe(dossier, site):
    pilote = PiloteNavigateur(site, pas_s=100)
    pilote.reponses[CINQUIEME] = (403, PAGE_ARENA)  # la page reste celle du défi
    p = parcours(dossier, pilote, recette(repassages_max=3))
    bilan = p.lancer()
    assert bilan.code == 3 and bilan.statut == "arretee" and bilan.arret["signe"] == "defi"
    assert "15" in bilan.arret["detail"]
    assert sum(p.horloge_factice.pauses) == pytest.approx(15) and pilote.relectures == 16
    verifier_arret_sans_suite(dossier, pilote, CINQUIEME)
    repassages = lu(dossier)["porte_repassages"]
    assert repassages["nombre"] == 0
    assert repassages["passages"][0]["franchie"] is False and repassages["passages"][0]["attente_s"] == 15.0


def test_un_defi_qui_revient_avant_l_ecart_minimal_arrete_la_passe(dossier, site):
    # Porte d'entrée franchie (page 1), puis un défi 200 s plus tard : hors de la rafale (120 s) et sous l'écart
    # minimal (300 s). La sentinelle arrête avec la même alerte qu'avant.
    pilote = PiloteNavigateur(site, pas_s=50)
    liste, fiche = vraie(pilote), vraie(pilote, CINQUIEME)
    pilote.reponses[LISTE] = (403, liste)
    pilote.reponses[CINQUIEME] = (403, fiche)
    pilote.apres_attente = [(200, liste), (200, fiche)]
    p = parcours(dossier, pilote, recette(repassages_max=3, ecart_min_s=300))
    bilan = p.lancer()
    assert bilan.code == 3 and bilan.arret["signe"] == "statut" and bilan.arret["detail"] == "statut 403"
    assert p.horloge_factice.pauses == []
    verifier_arret_sans_suite(dossier, pilote, CINQUIEME)
    resume = lu(dossier)
    assert resume["porte_entree"]["franchie"] is True
    assert resume["porte_repassages"]["nombre"] == 0
    assert resume["porte_repassages"]["passages"] == [
        {
            "adresse": f"{BASE_SITE}/lab/vitrine/annonces/{CINQUIEME}",
            "rang": 5,
            "defi": "statut 403",
            "franchie": False,
            "attente_s": 0.0,
            "ecart_s": 200.0,
            "rafale": False,
            "refus": "ecart_min_s",
        }
    ]
    assert any("Porte" in ligne and "300" in ligne for ligne in p.sortie_ecran)


def test_les_defis_d_une_meme_rafale_font_un_seul_passage(dossier, site):
    # Une protection pose plusieurs laissez-passer à quelques secondes d'écart (l'Arena : défi, Turnstile, reCAPTCHA),
    # qui expirent de même : un défi 100 s après l'entrée fait partie du même passage, il n'est pas compté.
    pilote = PiloteNavigateur(site, pas_s=50)
    liste, fiche = vraie(pilote), vraie(pilote, "AN-000002")
    pilote.reponses[LISTE] = (403, liste)
    pilote.reponses["AN-000002"] = (403, fiche)  # 3e page
    pilote.apres_attente = [(200, liste), (200, fiche)]
    bilan = parcours(dossier, pilote, recette(repassages_max=1, ecart_min_s=300)).lancer()
    assert bilan.code == 0 and bilan.statut == "terminee", bilan.arret
    repassages = bilan.resume["porte_repassages"]
    assert repassages["nombre"] == 0
    assert [(p["rang"], p["franchie"], p["rafale"], p["ecart_s"]) for p in repassages["passages"]] == [
        (3, True, True, 100.0)
    ]


def test_une_rafale_est_bornee_en_nombre_de_defis(dossier, site):
    from shadowlab.engines.noezia.parcours import RAFALE_PORTE_MAX, RAFALE_PORTE_S

    # L'entrée puis un défi à chaque page, 10 s d'écart : au-delà de RAFALE_PORTE_MAX défis dans la rafale, le défi
    # suivant est un nouveau passage, soumis à l'écart minimal : arrêt.
    pas = 10
    assert pas * (RAFALE_PORTE_MAX + 1) < RAFALE_PORTE_S
    pilote = PiloteNavigateur(site, pas_s=pas)
    pilote.reponses[LISTE] = (403, vraie(pilote))
    pilote.apres_attente = [(200, vraie(pilote))]
    for n in range(1, RAFALE_PORTE_MAX + 1):  # pages 2 à RAFALE_PORTE_MAX + 1
        fiche = vraie(pilote, f"AN-{n:06d}")
        pilote.reponses[f"AN-{n:06d}"] = (403, fiche)
        pilote.apres_attente.append((200, fiche))
    bilan = parcours(dossier, pilote, recette(repassages_max=3, ecart_min_s=300)).lancer()
    assert bilan.code == 3 and bilan.arret["signe"] == "statut"
    assert bilan.arret["adresse"].endswith(f"AN-{RAFALE_PORTE_MAX:06d}")
    passages = bilan.resume["porte_repassages"]["passages"]
    assert [p["rafale"] for p in passages] == [True] * (RAFALE_PORTE_MAX - 1) + [False]
    assert passages[-1]["refus"] == "ecart_min_s" and bilan.resume["porte_repassages"]["nombre"] == 0


def test_au_dela_de_repassages_max_la_passe_s_arrete_sans_attendre(dossier, site):
    pilote = PiloteNavigateur(site, pas_s=400)  # au-delà de la rafale et de l'écart minimal
    pilote.reponses["AN-000002"] = (403, PAGE_ARENA)  # 3e page : repassée
    pilote.reponses[CINQUIEME] = (403, PAGE_ARENA)  # 5e page : un repassage de trop
    pilote.apres_attente = [(200, vraie(pilote, "AN-000002"))]
    p = parcours(dossier, pilote, recette(repassages_max=1))
    bilan = p.lancer()
    assert bilan.code == 3 and bilan.arret["signe"] == "statut" and bilan.arret["detail"] == "statut 403"
    assert p.horloge_factice.pauses == []  # le défi de trop n'est pas attendu
    verifier_arret_sans_suite(dossier, pilote, CINQUIEME)
    repassages = bilan.resume["porte_repassages"]
    assert repassages["nombre"] == 1
    assert [(p["rang"], p["franchie"], p.get("refus")) for p in repassages["passages"]] == [
        (3, True, None),
        (5, False, "repassages_max"),
    ]


def test_un_moteur_sans_javascript_s_arrete_comme_avant(dossier, site):
    http = PiloteFactice(site)  # `relire()` rend None : rien ne changera tout seul
    http.horloge = Horloge()
    avancer_a_chaque_page(http, 100)
    http.reponses[CINQUIEME] = (403, PAGE_ARENA)
    p = parcours(dossier, http, recette(repassages_max=3))
    bilan = p.lancer()
    assert bilan.code == 3 and bilan.arret["signe"] == "statut" and bilan.arret["detail"] == "statut 403"
    assert p.horloge_factice.pauses == []
    verifier_arret_sans_suite(dossier, http, CINQUIEME)
    assert bilan.resume["porte_repassages"] == {"repassages_max": 3, "ecart_min_s": 300, "nombre": 0, "passages": []}
    assert repassages_traces(dossier) == []


# --- (h) Reprise : compte et horloge cohérents ------------------------------------------------


def test_reprise_le_compte_des_repassages_est_garde(dossier, site):
    pilote = PiloteNavigateur(site, pas_s=400)
    pilote.reponses["AN-000002"] = (403, PAGE_ARENA)  # 3e page : repassée
    pilote.apres_attente = [(200, vraie(pilote, "AN-000002"))]
    pilote.reponses["AN-000006"] = (429, "<html><body>trop de requêtes</body></html>")  # 7e page : arrêt
    texte = recette(repassages_max=1)
    premier = parcours(dossier, pilote, texte).lancer()
    assert premier.code == 3 and premier.arret["detail"] == "statut 429"
    assert premier.resume["porte_repassages"]["nombre"] == 1

    # Reprise : session neuve, la première page est redéfiée. Le maximum (1) est déjà atteint : arrêt.
    pilote.horloge.t += 3600
    pilote.reponses["AN-000006"] = (403, PAGE_ARENA)
    pilote.apres_attente = [(200, vraie(pilote, "AN-000006"))]
    reprise = parcours(dossier, pilote, texte).reprendre(maintenant=True)
    assert reprise.code == 3 and reprise.arret["signe"] == "statut" and reprise.arret["detail"] == "statut 403"
    repassages = reprise.resume["porte_repassages"]
    assert repassages["nombre"] == 1
    assert [(p["rang"], p["franchie"], p.get("refus")) for p in repassages["passages"]] == [
        (3, True, None),
        (7, False, "repassages_max"),
    ]


def test_reprise_l_ecart_se_compte_depuis_le_dernier_passage_de_la_passe(dossier, site):
    pilote = PiloteNavigateur(site, pas_s=200)
    fiche5, fiche7 = vraie(pilote, CINQUIEME), vraie(pilote, "AN-000006")
    pilote.reponses[CINQUIEME] = (403, fiche5)  # 5e page, à 1000 s du début : repassée
    pilote.apres_attente = [(200, fiche5)]
    pilote.reponses["AN-000006"] = (429, "<html><body>trop de requêtes</body></html>")  # 7e page : arrêt
    texte = recette(repassages_max=3, ecart_min_s=600)
    premier = parcours(dossier, pilote, texte).lancer()
    assert premier.code == 3 and premier.arret["detail"] == "statut 429"

    # Reprise 100 s plus tard ; sa première page, 200 s après, est redéfiée : 700 s depuis le dernier passage (page
    # 5), au-dessus des 600 s exigés. Compté depuis le début de la reprise, l'écart ne serait que de 200 s.
    pilote.horloge.t += 100
    pilote.reponses["AN-000006"] = (403, fiche7)
    pilote.apres_attente = [(200, fiche7)]
    reprise = parcours(dossier, pilote, texte).reprendre(maintenant=True)
    assert reprise.code == 0 and reprise.statut == "terminee", reprise.arret
    repassages = reprise.resume["porte_repassages"]
    assert repassages["nombre"] == 2
    assert [(p["rang"], p["franchie"], p["ecart_s"]) for p in repassages["passages"]] == [
        (5, True, 1000.0),
        (7, True, 700.0),
    ]
    assert len(repassages_traces(dossier)) == 2
    etat = Etat(dossier / "etat.sqlite3")
    try:
        assert etat.compteurs(1)["faites"] == 48
    finally:
        etat.fermer()


# --- (i) La recette ---------------------------------------------------------------------------


def test_porte_entree_valeurs_par_defaut_et_valeurs_admises():
    porte = recettes.lire_texte(recette()).porte_entree
    assert porte is not None and porte.repassages_max == 0 and porte.ecart_min_s == 300
    porte = recettes.lire_texte(recette(repassages_max=2, ecart_min_s=0)).porte_entree
    assert porte is not None and porte.repassages_max == 2 and porte.ecart_min_s == 0


@pytest.mark.parametrize(
    ("reglage", "motif"),
    [
        ({"repassages_max": -1}, r"porte_entree\.repassages_max.*au moins 0"),
        ({"ecart_min_s": -5}, r"porte_entree\.ecart_min_s.*au moins 0"),
    ],
)
def test_porte_entree_valeurs_negatives_refusees(reglage, motif):
    with pytest.raises(recettes.RecetteInvalide, match=motif):
        recettes.lire_texte(recette(**reglage))


# --- (j) Les campagnes ------------------------------------------------------------------------


def test_la_recette_du_passage_permet_de_repasser_la_porte():
    from shadowlab import scenarios

    recette_passage, _ = scenarios.recette_du_passage("vitrine", BASE_ARENA)
    porte = recette_passage.porte_entree
    assert porte is not None and porte.attendre_s == scenarios.PORTE_ENTREE_PASSAGE_S
    assert porte.repassages_max == scenarios.PORTE_REPASSAGES_PASSAGE > 0
    assert porte.ecart_min_s == scenarios.PORTE_ECART_MIN_PASSAGE_S > 0


def test_le_scenario_de_campagne_rend_le_compte_des_repassages(site, monkeypatch):
    from shadowlab import scenarios

    # `_recolter_avec_recette` garde l'horloge réelle : l'écart minimal est levé pour ce test.
    monkeypatch.setattr(scenarios, "PORTE_ECART_MIN_PASSAGE_S", 0)
    pilote = PiloteNoezia(site)
    fiche = vraie(pilote, CINQUIEME)
    pilote.reponses[CINQUIEME] = (403, fiche)  # statut périmé : le pilote a franchi le défi pendant `navigate`
    pilote.apres_attente = [(200, fiche)]
    issue = scenarios.SCENARIOS["recolte_recette_vitrine"].executer(pilote, BASE_SITE, JETON, random.Random(1))
    assert issue.success is True and issue.details["statut"] == "terminee", issue.details
    assert issue.details["porte_repassages"] == 1
    liste = issue.details["porte_repassages_liste"]
    assert len(liste) == 1 and set(liste[0]) == {"rang", "attente_s", "ecart_s", "franchie", "rafale", "refus"}
    assert (liste[0]["rang"], liste[0]["attente_s"], liste[0]["franchie"], liste[0]["refus"]) == (5, 0.0, True, None)
    json.dumps(issue.details)  # la campagne l'enregistre en JSON


def test_dans_le_rallye_une_page_rendue_par_la_porte_garde_ses_champs_lus_dans_l_adresse(reglages, monkeypatch):
    """La page rendue par `relire()` porte l'adresse du navigateur, jeton `sl` compris ; le rallye lit des clés dans
    l'adresse (`/speciales/(\\d+)$`) : elles doivent rester lues, sinon tout un tableau de temps serait ignoré."""
    from shadowlab import scenarios
    from shadowlab.engines.base import ResultatNavigation

    class PilotePerime(PiloteNoezia):
        """La première spéciale rend un 403 périmé : vrai contenu, défi déjà franchi pendant `navigate`."""

        fait = False

        def navigate(self, url):
            resultat = super().navigate(url)
            if self.fait or "/lab/rallye/speciales/" not in url:
                return resultat
            self.fait, self.adresse_perimee = True, url
            self.statuts[-1] = self._courant = 403
            self.apres_attente = [(200, self._texte)]
            return ResultatNavigation(403, url, resultat.duration_ms)

    monkeypatch.setattr(scenarios, "PORTE_ECART_MIN_PASSAGE_S", 0)
    monkeypatch.setenv("SHADOWLAB_RALLYE_TAILLE", "3")
    monkeypatch.setenv("SHADOWLAB_RALLYE_GRAINE", str(GRAINE))
    with creer_client(monkeypatch) as client:
        pilote = PilotePerime(client)
        issue = scenarios.SCENARIOS["recolte_recette_rallye"].executer(pilote, BASE_SITE, JETON, random.Random(1))
    assert pilote.fait and issue.details["porte_repassages"] == 1, issue.details
    assert f"sl={JETON}" in pilote.adresse_perimee  # l'adresse relue porte bien le jeton du passage
    note = issue.details["recolte"]
    assert note["pages"] == 1.0 and note["enregistrements"] == 1.0 and note["champs"] == 1.0, note
    assert issue.success is True


# --- `shadowlab recolte etat` -----------------------------------------------------------------


def test_recolte_etat_dit_combien_de_fois_la_porte_a_ete_repassee(dossier, site, capsys):
    from shadowlab.cli import main

    pilote = PiloteNavigateur(site, pas_s=100)
    fiche = vraie(pilote, CINQUIEME)
    pilote.reponses[CINQUIEME] = (403, fiche)
    pilote.apres_attente = [(200, fiche)]
    assert parcours(dossier, pilote, recette(repassages_max=3)).lancer().code == 0
    capsys.readouterr()
    assert main(["recolte", "etat", "vitrine-annonces", "--sortie", str(dossier)]) == 0
    assert "porte repassée en cours de passe : 1 fois" in capsys.readouterr().out
