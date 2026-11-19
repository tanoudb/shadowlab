"""Palier 2, I10 : le moteur et les comptes (D-104). Sentinelle, identité connectée, étape du compte, campagne.

1. La sentinelle lit l'en-tête `X-Arena-Refus: bannissement` d'une PAGE refusée : un bannissement, à toute page de la
   passe (révise D-91 et D-103, qui ne le lisaient que dans le corps du refus d'une ressource). Sans l'en-tête, un 403
   après la première page reste une alerte, comme avant.
2. L'identité note la connexion à un compte (identifiant et date, jamais le mot de passe) : elle survit au verrou et au
   lancement suivant.
3. L'étape du compte du scénario `visite`, jouée sur le vrai code de l'Arena (profil `endurance`, `TestClient`, en-têtes
   du frontal imités) par un navigateur factice qui garde ses cookies comme un profil Chrome :
   - la première visite se connecte, les suivantes lisent l'espace sans se reconnecter (même appareil) ;
   - renvoyé vers la connexion alors qu'on était connecté : alerte, aucune reconnexion, rien après ;
   - compte banni : bannissement de l'identité, aucun réessai, rien après ; depuis une autre identité aussi ;
   - une visite arrêtée ne tente pas la connexion ; aucun mot de passe dans les détails du passage.
4. La campagne : champs `compte` et `identite_apres_bannissement` ; avant la visite voulue, le COMPTE du bras est banni
   (pas son visiteur) puis le pilote est rouvert sur l'autre identité ; le fichier `comptes-essai.yaml`.
"""

# ruff: noqa: E501  (configurations YAML en ligne)
from __future__ import annotations

import json
import random
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest
from outils_recolte import PiloteFactice
from test_bannissement import _entetes
from test_comptes import NavigateurConnecte
from test_espacement import BRAS, Horloge, Passages, campagne, faux_pilote, preparer, rang_de
from test_sentinelle import PiloteIdentite
from test_visiteurs import nouveau_passage, nouvelle_experience

from shadowlab import campaigns, scenarios
from shadowlab import database as db
from shadowlab.arena import bannissements, profils
from shadowlab.arena import comptes as comptes_arena
from shadowlab.config import RACINE
from shadowlab.engines.base import ResultatNavigation
from shadowlab.engines.noezia import identite as ident
from shadowlab.engines.noezia import sentinelle as module_sentinelle
from shadowlab.engines.noezia.lecture import LectureHumaine
from shadowlab.engines.noezia.sentinelle import Sentinelle, verdict_identite
from shadowlab.site import comptes as fixtures
from shadowlab.site import gardien

BASE = "http://127.0.0.1:8770"
MONDE = "c-comptes:sujet:endurance"
FICHE = "http://127.0.0.1:8770/lab/vitrine/annonces/AN-000004?sl=x"
FICHIER_ESSAI = RACINE / "configs" / "experiments" / "comptes-essai.yaml"
MOTS_DE_PASSE = tuple(fixtures.COMPTES.values())


# ═══ 1. La sentinelle lit le motif d'une page refusée ════════════════════════════════════════════════════════


def _examiner(statut, entetes=None):
    return Sentinelle(["127.0.0.1"]).examiner(
        type_page="fiche", adresse=FICHE, statut=statut, adresse_finale=FICHE, dans_le_motif=True,
        html="<html><body data-arena=\"blocage\"></body></html>", entetes=entetes,
    )  # fmt: skip


def test_l_en_tete_de_la_sentinelle_est_celui_que_pose_le_gardien():
    assert module_sentinelle.ENTETE_REFUS == gardien.ENTETE_REFUS.lower()


def test_une_page_refusee_au_motif_bannissement_est_un_bannissement_a_toute_page():
    alerte = _examiner(403, {"x-arena-refus": "bannissement"})
    assert alerte is not None and alerte.signe == "statut" and alerte.statut == 403
    assert alerte.motif == "bannissement" and "motif bannissement" in alerte.detail
    assert verdict_identite(alerte, premiere_page=False) == "banni"
    assert verdict_identite(alerte, premiere_page=True) == "banni"


def test_l_en_tete_se_lit_sans_egard_a_la_casse():
    alerte = _examiner(403, {"X-Arena-Refus": " Bannissement "})
    assert alerte is not None and alerte.motif == "bannissement"
    assert verdict_identite(alerte, premiere_page=False) == "banni"


@pytest.mark.parametrize(
    ("statut", "entetes"),
    [
        (403, None),  # pas d'en-tête : un refus de page sans motif, comme avant D-104
        (403, {}),
        (403, {"x-arena-refus": "autre"}),
        (429, {"x-arena-refus": "bannissement"}),  # seul un 403 est un refus franc
    ],
)
def test_sans_le_motif_un_refus_apres_la_premiere_page_reste_une_alerte(statut, entetes):
    alerte = _examiner(statut, entetes)
    assert alerte is not None and alerte.signe == "statut" and alerte.motif is None
    assert verdict_identite(alerte, premiere_page=False) == "alerte"


class PiloteRefusAvecMotif(PiloteIdentite):
    """`PiloteIdentite` de la sentinelle dont la page `AN-000010` est refusée avec l'en-tête du gardien."""

    def etat_page(self):
        statut, adresse, entetes = super().etat_page()
        if "AN-000010" in adresse:
            return 403, adresse, {"x-arena-refus": "bannissement"}
        return statut, adresse, entetes


@pytest.fixture
def racine(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOWLAB_IDENTITES", str(tmp_path / "identites"))
    return tmp_path / "identites"


@pytest.fixture
def site(reglages, monkeypatch):
    from fastapi.testclient import TestClient

    from shadowlab.config import charger
    from shadowlab.site.app import creer_app

    monkeypatch.setenv("SHADOWLAB_VITRINE_TAILLE", "45")
    with TestClient(creer_app(charger()), base_url="http://127.0.0.1") as client:
        yield client


def test_dans_un_parcours_le_refus_d_une_fiche_au_motif_bannissement_bannit_l_identite(site, racine, tmp_path):
    from outils_recolte import fabriquer

    ouverte = ident.ouvrir("refus-motif")
    try:
        pilote = PiloteRefusAvecMotif(site, ouverte)
        pilote.reponses["AN-000010"] = (403, '<html><body data-arena="blocage"></body></html>')
        bilan = fabriquer(tmp_path / "recolte", pilote).lancer()
        pilote.close_session()
    finally:
        ouverte.liberer()
    assert bilan.code == 3 and bilan.arret["signe"] == "statut" and "motif bannissement" in bilan.arret["detail"]
    assert not any("AN-000011" in d for d in pilote.demandes)  # rien après le refus
    assert ident.lire_etat("refus-motif")["etat"] == "banni"


# ═══ 2. L'identité retient sa connexion ══════════════════════════════════════════════════════════════════════


def test_l_identite_retient_la_connexion_au_compte_d_un_lancement_a_l_autre(racine):
    quand = datetime(2026, 11, 19, 9, 30, tzinfo=UTC)
    ouverte = ident.ouvrir("connectee")
    assert ouverte.connectee_a("demo") is None
    ouverte.noter_connexion("demo", quand)
    ouverte.liberer()
    rouverte = ident.ouvrir("connectee")
    try:
        assert rouverte.connectee_a("demo") == quand
        assert rouverte.connectee_a("analyste") is None
        rouverte.marquer("alerte", "essai")  # l'état change, la connexion notée reste
        assert rouverte.connectee_a("demo") == quand
    finally:
        rouverte.liberer()
    texte = (racine / "connectee" / "identite.json").read_text(encoding="utf-8")
    assert not any(m in texte for m in MOTS_DE_PASSE)


# ═══ 3. L'étape du compte du scénario `visite`, sur le vrai code de l'Arena ═════════════════════════════════


class Navigateur(PiloteFactice):
    """Un navigateur factice sur le `TestClient` du site : il garde ses cookies d'une visite à l'autre (comme un profil
    Chrome), envoie les en-têtes du frontal (profil `endurance`), suit les redirections et remplit le formulaire de
    connexion. `demandes` : (méthode, chemin) de chaque requête, redirections comprises."""

    name = "noezia"
    runtime = "navigateur"
    executes_javascript = True

    def __init__(self, client, reglages, profil_chrome, identite=None):
        super().__init__(client)
        self.nav = profil_chrome  # les cookies du « profil Chrome » : partagés par les visites d'une même identité
        self.reglages = reglages
        self.identite_courante = identite
        self.hotes_navigation = None
        self.requetes: list[tuple[str, str]] = []
        self._champs: dict[str, str] = {}
        self._jeton = ""
        self._derniere = None
        self._chemin = ""
        if identite is not None:
            identite.debut_visite()

    def close_session(self):
        if self.identite_courante is not None:
            self.identite_courante.fin_visite(pages=len(self.requetes))

    def _envoyer(self, methode: str, chemin: str, **corps):
        self.nav._preparer()
        self.requetes.append((methode, chemin))
        entetes = _entetes(self.reglages, "endurance", self._jeton)
        entetes["accept"] = "text/html,application/xhtml+xml"
        reponse = self.client.request(
            methode, f"{chemin}?sl={self._jeton}", headers=entetes, follow_redirects=False, **corps
        )
        self.nav._poser(reponse)
        for _ in range(5):  # un navigateur suit les redirections du site
            if reponse.status_code not in (301, 302, 303, 307):
                break
            chemin = urlsplit(reponse.headers["location"]).path
            self.nav._preparer()
            self.requetes.append(("GET", chemin))
            reponse = self.client.get(f"{chemin}?sl={self._jeton}", headers=entetes, follow_redirects=False)
            self.nav._poser(reponse)
        self._derniere, self._chemin = reponse, chemin
        self._texte = reponse.text
        self.demandes.append(chemin)
        self.statuts.append(reponse.status_code)
        return ResultatNavigation(reponse.status_code, self._adresse(), 1.0)

    def _adresse(self) -> str:
        return f"{BASE}{self._chemin}?sl={self._jeton}"

    def navigate(self, url):
        self.verifier(url)
        morceaux = urlsplit(url)
        self._jeton = parse_qs(morceaux.query)["sl"][0]
        self.urls.append(url)
        if morceaux.path.startswith("/robots.txt"):
            self.demandes.append(morceaux.path)
            self.statuts.append(404)
            self._texte = ""
            return ResultatNavigation(404, url, 0.1)
        self.requetes_pages += 1
        return self._envoyer("GET", morceaux.path)

    def fill(self, selector, value):
        self._champs[selector] = value

    def click(self, selector):
        assert selector == "#bouton-connexion", selector
        corps = {
            "identifiant": self._champs.get("#champ-identifiant", ""),
            "mot_de_passe": self._champs.get("#champ-mot-de-passe", ""),
        }
        self._envoyer("POST", "/lab/connexion", data=corps)

    def etat_page(self):
        if self._derniere is None:
            return None, "", {}
        return self._derniere.status_code, self._adresse(), {k.lower(): v for k, v in self._derniere.headers.items()}

    def texts(self, selector):
        from parsel import Selector

        return ["".join(e.css("::text").getall()) for e in Selector(text=self._texte or "<html></html>").css(selector)]


@pytest.fixture(autouse=True)
def lecture_instantanee(monkeypatch):
    monkeypatch.setattr(scenarios, "LECTURE_HUMAINE_VISITE", LectureHumaine(duree_s=(0, 0, 0)))


@pytest.fixture
def sans_suspicion(monkeypatch):
    """Aucun détecteur ne tranche : on isole les comptes (le bannissement et la mémoire des comptes restent vrais)."""
    monkeypatch.setattr(gardien, "suspicion", lambda *a, **k: [])


@pytest.fixture
def experience(reglages):
    return nouvelle_experience(reglages, "comptes-moteur")


@pytest.fixture
def cx(reglages):
    connexion = db.ouvrir(reglages.base_donnees)
    yield connexion
    connexion.close()


class Visites:
    """Les visites d'un essai : un jeton neuf par visite, dans le même monde ; la porte d'entrée franchie d'abord (le
    navigateur factice ne fait pas tourner la preuve de travail : c'est le seul pas qui n'est pas celui du moteur)."""

    def __init__(self, site, reglages, experience):
        self.site, self.reglages, self.experience = site, reglages, experience
        self.rang = 0

    def profil_chrome(self):
        return NavigateurConnecte(self.site, self.reglages)

    def faire(self, profil_chrome, identite, compte="demo", pages=3, porte=True):
        self.rang += 1
        jeton = nouveau_passage(self.reglages, self.experience, repetition=self.rang, monde=MONDE)
        if porte and gardien.COOKIE_DEFI not in profil_chrome.cookies:
            profil_chrome.franchir_la_porte(jeton)
        pilote = Navigateur(self.site, self.reglages, profil_chrome, identite)
        issue = scenarios.visite(
            pilote, BASE, jeton, random.Random(self.rang), pages=pages, duree_porte_s=86_400, compte=compte
        )
        pilote.close_session()
        return jeton, pilote, issue


@pytest.fixture
def visites(site, reglages, experience, sans_suspicion, racine):
    return Visites(site, reglages, experience)


def _ouvrir(nom):
    return ident.ouvrir(nom)


def _sans_mot_de_passe(issue):
    texte = json.dumps(issue.details, ensure_ascii=False, default=str)
    return not any(m in texte for m in MOTS_DE_PASSE)


def _appareils(cx, compte="demo"):
    return cx.execute(
        "SELECT a.* FROM appareils a JOIN comptes c ON c.id = a.compte_id JOIN mondes m ON m.id = c.monde_id"
        " WHERE m.nom = ? AND c.identifiant = ? ORDER BY a.id",
        (MONDE, compte),
    ).fetchall()


def test_la_premiere_visite_se_connecte_puis_atteint_l_espace(visites, cx):
    a = _ouvrir("compte-a")
    try:
        _, pilote, issue = visites.faire(visites.profil_chrome(), a)
        assert issue.success, issue.details
        compte = issue.details["compte"]
        assert compte["identifiant"] == "demo" and compte["tentee"] is True
        assert compte["connexion"] == "nouvelle" and compte["espace_atteint"] is True and compte["refus"] is None
        assert ("POST", "/lab/connexion") in pilote.requetes
        assert pilote.requetes[-1] == ("GET", "/lab/espace")  # la redirection du formulaire, rien après
        assert a.connectee_a("demo") is not None
    finally:
        a.liberer()
    assert _sans_mot_de_passe(issue)
    (appareil,) = _appareils(cx)
    assert appareil["nouvel_appareil"] == 0


def test_la_visite_suivante_atteint_l_espace_sans_se_reconnecter(visites, cx):
    chrome_a = visites.profil_chrome()
    a = _ouvrir("compte-a")
    try:
        visites.faire(chrome_a, a)
        for _ in range(2):  # deux visites de plus, Chrome relancé (même profil), jeton neuf
            _, pilote, issue = visites.faire(chrome_a, a)
            assert issue.success, issue.details
            assert issue.details["compte"]["connexion"] == "gardee"
            assert issue.details["compte"]["espace_atteint"] is True
            assert not any(chemin == "/lab/connexion" for _, chemin in pilote.requetes)  # ni la page, ni le formulaire
            assert pilote.requetes[-1] == ("GET", "/lab/espace")
    finally:
        a.liberer()
    (appareil,) = _appareils(cx)  # la même identité qui revient : un seul appareil, jamais « nouveau »
    assert appareil["nouvel_appareil"] == 0
    assert ident.lire_etat("compte-a")["etat"] == "ok"


def test_renvoye_vers_la_connexion_alors_qu_on_etait_connecte_est_une_alerte_sans_reconnexion(visites):
    chrome_a = visites.profil_chrome()
    a = _ouvrir("compte-a")
    try:
        visites.faire(chrome_a, a)
        chrome_a.cookies.pop(gardien.COOKIE_CONNEXION)  # le site a oublié la connexion, l'identité croit l'avoir
        _, pilote, issue = visites.faire(chrome_a, a)
    finally:
        a.liberer()
    assert issue.success is False
    compte = issue.details["compte"]
    assert compte["signe"] == "hors_motif" and "/lab/connexion" in compte["refus"] and compte["espace_atteint"] is False
    assert ("POST", "/lab/connexion") not in pilote.requetes  # aucune reconnexion automatique
    assert pilote.requetes[-2:] == [("GET", "/lab/espace"), ("GET", "/lab/connexion")]  # la redirection, rien après
    assert ident.lire_etat("compte-a")["etat"] == "alerte"


def test_l_espace_d_un_compte_banni_bannit_l_identite_connectee_sans_rien_demander_apres(visites, cx):
    chrome_a = visites.profil_chrome()
    a = _ouvrir("compte-a")
    try:
        visites.faire(chrome_a, a)
        assert comptes_arena.bannir_compte_connu(cx, MONDE, "demo") is True
        _, pilote, issue = visites.faire(chrome_a, a)
    finally:
        a.liberer()
    assert issue.success is False
    assert issue.details["compte"]["signe"] == "statut" and "motif bannissement" in issue.details["compte"]["refus"]
    assert pilote.requetes[-1] == ("GET", "/lab/espace")  # le refus est la dernière requête
    assert ident.lire_etat("compte-a")["etat"] == "banni"
    assert issue.details["identite"]["etat"] == "banni"


def test_un_compte_banni_est_refuse_a_une_autre_identite_qui_ne_demande_plus_rien(visites, cx):
    a = _ouvrir("compte-a")
    try:
        visites.faire(visites.profil_chrome(), a)
    finally:
        a.liberer()
    assert comptes_arena.bannir_compte_connu(cx, MONDE, "demo") is True
    b = _ouvrir("compte-b")
    try:
        jeton, pilote, issue = visites.faire(visites.profil_chrome(), b)  # autre navigateur : autres cookies
    finally:
        b.liberer()
    assert issue.success is False
    assert issue.details["pages_faites"] >= 1  # la vitrine lue d'abord : ni le visiteur ni l'empreinte ne sont bannis
    assert issue.details["compte"]["connexion"] is None and "motif bannissement" in issue.details["compte"]["refus"]
    assert pilote.requetes[-1] == ("POST", "/lab/connexion")  # le formulaire refusé, rien après
    assert ident.lire_etat("compte-b")["etat"] == "banni"
    decision = [d for d in db.decisions_session(cx, jeton) if d["couche"] == "bannissement"][-1]
    motif = decision["motifs"][0] if isinstance(decision["motifs"], list) else decision["motifs"]
    assert motif["par"] == "compte" and motif["compte"] == "demo"
    assert len(_appareils(cx)) == 1  # le refusé n'est pas un appareil du compte
    assert _sans_mot_de_passe(issue)


def test_une_visite_arretee_ne_tente_pas_la_connexion(visites, cx):
    chrome_a = visites.profil_chrome()
    a = _ouvrir("compte-a")
    try:
        visites.faire(chrome_a, a, compte=None)  # une visite sans compte : le visiteur est connu
        visiteur = chrome_a.cookies["sl_visiteur"].split(".")[0]
        bannissements.bannir_visiteur_connu(cx, MONDE, visiteur)
        _, pilote, issue = visites.faire(chrome_a, a)
    finally:
        a.liberer()
    assert issue.success is False and issue.details["statut"] == "arretee"
    assert issue.details["compte"] == {"identifiant": "demo", "tentee": False}
    assert not any(chemin in ("/lab/connexion", "/lab/espace") for _, chemin in pilote.requetes)


def test_sans_compte_la_visite_reste_celle_d_avant(visites):
    a = _ouvrir("compte-a")
    try:
        _, pilote, issue = visites.faire(visites.profil_chrome(), a, compte=None)
    finally:
        a.liberer()
    assert issue.success and "compte" not in issue.details
    assert not any(chemin in ("/lab/connexion", "/lab/espace") for _, chemin in pilote.requetes)


# ═══ 4. La campagne ══════════════════════════════════════════════════════════════════════════════════════════

BRAS_COMPTES = """
    - name: noezia
      label: sujet-compte
      compte: demo
      options: {headless: false, channel: chrome, identite_native: true, identite: comptes-sujet}
    - name: noezia
      label: temoin-compte
      visites: 4
      compte: analyste
      bannir_avant_visite: 3
      identite_apres_bannissement: comptes-temoin-b
      options: {headless: false, channel: chrome, identite_native: true, identite: comptes-temoin-a}
"""
ESPACEMENT = "  espacement: {mode: fixe, minutes: 1}\n  concurrency: 2\n"


def test_une_campagne_avec_compte_valide(tmp_path, reglages):
    e = campagne(tmp_path, reglages, engines=BRAS_COMPTES, extra=ESPACEMENT)
    sujet, temoin = e.engines
    assert sujet.compte == "demo" and sujet.identite_apres_bannissement is None
    assert temoin.compte == "analyste" and temoin.identite_apres_bannissement == "comptes-temoin-b"


@pytest.mark.parametrize(
    ("bras", "message"),
    [
        (
            "    - {name: noezia, compte: inconnu, options: {headless: false, channel: chrome, identite_native: true, identite: x}}\n",
            "compte",
        ),
        (
            "    - {name: noezia, compte: demo.x, options: {headless: false, channel: chrome, identite_native: true, identite: x}}\n",
            "compte",
        ),
        # l'autre identité sans bannissement, sans identité, invalide, ou la même
        (
            "    - {name: noezia, identite_apres_bannissement: y, options: {headless: false, channel: chrome, identite_native: true, identite: x}}\n",
            "identite_apres_bannissement",
        ),
        (
            "    - {name: noezia, bannir_avant_visite: 2, identite_apres_bannissement: Y!, options: {headless: false, channel: chrome, identite_native: true, identite: x}}\n",
            "identite_apres_bannissement",
        ),
        (
            "    - {name: noezia, bannir_avant_visite: 2, identite_apres_bannissement: x, options: {headless: false, channel: chrome, identite_native: true, identite: x}}\n",
            "identite_apres_bannissement",
        ),
    ],
)
def test_les_champs_du_compte_sont_controles(tmp_path, reglages, bras, message):
    with pytest.raises(ValueError, match=message):
        campagne(tmp_path, reglages, engines="\n" + bras, extra=ESPACEMENT)


def test_un_compte_exige_le_scenario_visite(tmp_path, reglages):
    from test_campagnes import ecrire

    texte = ecrire(
        tmp_path,
        """
experiment:
  name: comptes
  engines:
    - {name: noezia, compte: demo, options: {headless: false, channel: chrome, identite_native: true, identite: x}}
  scenarios: [connexion]
  repetitions: 2
""",
    )
    with pytest.raises(ValueError, match="compte"):
        campaigns.lire(texte, reglages)


def test_le_compte_du_bras_est_passe_au_scenario(tmp_path, reglages):
    e = campagne(tmp_path, reglages, engines=BRAS_COMPTES, extra=ESPACEMENT)
    assert campaigns._reglages_visite(reglages, 1, e.engines[0], "endurance")["compte"] == "demo"
    sans = campagne(
        tmp_path, reglages, engines=BRAS, extra="  espacement: {mode: fixe, minutes: 1}\n  concurrency: 4\n"
    )
    assert campaigns._reglages_visite(reglages, 1, sans.engines[0], "endurance")["compte"] is None
    scenario = scenarios.avec_pages(4, compte="demo")
    assert scenario.name == "visite" and scenario.executer.keywords["compte"] == "demo"


def _pilote_qui_note_ses_options():
    base = faux_pilote()

    class Pilote(base):
        ouverts: list[dict] = []

        def __init__(self, hotes, options=None):
            super().__init__(hotes, options)
            self.options_recues = dict(options or {})
            Pilote.ouverts.append(self.options_recues)

        def configuration(self):
            return {"identite": self.options_recues.get("identite")}

    Pilote.ouverts = []
    return Pilote


def _connecter_le_compte(compte):
    """Ce que fait l'Arena à chaque visite du bras : le visiteur `v1` vu, puis connecté à `compte`."""
    from shadowlab.arena import visiteurs

    def ecrire(cx, monde, repetition):
        cx.execute(
            "INSERT OR IGNORE INTO visites (monde_id, visiteur, session_token, neuve, vue_le) VALUES (?, 'v1', ?, ?, ?)",
            (visiteurs.identifiant_monde(cx, monde), f"s-{monde}-{repetition}", int(repetition == 1), db.maintenant()),
        )
        if not comptes_arena.motif_bannissement(cx, monde, compte):
            comptes_arena.connecter(cx, monde, "v1", compte, profils.Bannissement(actif=True))

    return ecrire


def test_avant_la_visite_voulue_le_compte_est_banni_puis_le_pilote_change_d_identite(
    tmp_path, reglages, monkeypatch, racine
):
    experience, cx, experiment_id = preparer(tmp_path, reglages, monkeypatch, extra=ESPACEMENT, engines=BRAS_COMPTES)
    pilote = _pilote_qui_note_ses_options()
    monkeypatch.setattr(campaigns, "registre", lambda: {"noezia": pilote})
    horloge = Horloge()
    passages = Passages(reglages, horloge, ecrire_visite=_connecter_le_compte("analyste"))
    monkeypatch.setattr(campaigns, "_passage", passages)
    rang = rang_de(experience, "temoin-compte")
    assert (
        campaigns.executer_unite(reglages, experiment_id, rang, horloge=horloge.now, dormir=horloge.dormir) == "termine"
    )
    assert [a["repetition"] for a in passages.appels] == [1, 2, 3, 4]
    assert [a["bannissements"] for a in passages.appels] == [0, 0, 1, 1]
    monde = f"c{experiment_id}:temoin-compte:endurance"
    (ligne,) = cx.execute(
        "SELECT m.nom AS monde, b.visiteur, b.empreinte, b.compte, b.motif FROM bannissements b JOIN mondes m ON m.id = b.monde_id"
    ).fetchall()
    assert (ligne["monde"], ligne["visiteur"], ligne["empreinte"], ligne["compte"], ligne["motif"]) == (
        monde,
        None,
        None,
        "analyste",
        "manuel",
    )  # le compte, pas le visiteur : la visite 3 doit être refusée pour son compte seulement
    assert [o["identite"] for o in pilote.ouverts] == ["comptes-temoin-a", "comptes-temoin-b"]
    assert all(a["scenario"].executer.keywords["compte"] == "analyste" for a in passages.appels)
    moteurs = cx.execute(
        "SELECT json_extract(e.configuration, '$.identite') AS identite, json_extract(e.configuration, '$.label') AS label,"
        " r.repetition FROM runs r JOIN engines e ON e.id = r.engine_id WHERE r.experiment_id = ? ORDER BY r.repetition",
        (experiment_id,),
    ).fetchall()
    assert [(m["label"], m["identite"]) for m in moteurs] == [
        ("temoin-compte", "comptes-temoin-a"), ("temoin-compte", "comptes-temoin-a"),
        ("temoin-compte", "comptes-temoin-b"), ("temoin-compte", "comptes-temoin-b"),
    ]  # fmt: skip


def test_un_compte_jamais_connecte_arrete_le_bras_sans_changer_d_identite(tmp_path, reglages, monkeypatch, racine):
    experience, cx, experiment_id = preparer(tmp_path, reglages, monkeypatch, extra=ESPACEMENT, engines=BRAS_COMPTES)
    pilote = _pilote_qui_note_ses_options()
    monkeypatch.setattr(campaigns, "registre", lambda: {"noezia": pilote})
    horloge = Horloge()
    passages = Passages(reglages, horloge)  # l'Arena n'a vu aucune connexion : le compte est inconnu dans le monde
    monkeypatch.setattr(campaigns, "_passage", passages)
    rang = rang_de(experience, "temoin-compte")
    assert (
        campaigns.executer_unite(reglages, experiment_id, rang, horloge=horloge.now, dormir=horloge.dormir)
        == "interrompu"
    )
    assert [a["repetition"] for a in passages.appels] == [1, 2]
    assert cx.execute("SELECT COUNT(*) FROM bannissements").fetchone()[0] == 0
    assert [o["identite"] for o in pilote.ouverts] == ["comptes-temoin-a"]


def test_a_la_reprise_apres_le_bannissement_le_pilote_s_ouvre_sur_l_autre_identite(
    tmp_path, reglages, monkeypatch, racine
):
    experience, cx, experiment_id = preparer(tmp_path, reglages, monkeypatch, extra=ESPACEMENT, engines=BRAS_COMPTES)
    pilote = _pilote_qui_note_ses_options()
    monkeypatch.setattr(campaigns, "registre", lambda: {"noezia": pilote})
    horloge = Horloge()
    rang = rang_de(experience, "temoin-compte")
    passages = Passages(reglages, horloge, ecrire_visite=_connecter_le_compte("analyste"))
    monkeypatch.setattr(campaigns, "_passage", passages)
    assert (
        campaigns.executer_unite(reglages, experiment_id, rang, horloge=horloge.now, dormir=horloge.dormir) == "termine"
    )
    cx.execute("DELETE FROM runs WHERE repetition = 4")  # la visite 4 n'a pas eu lieu (arrêt de la campagne)
    pilote.ouverts.clear()
    passages.appels.clear()
    assert (
        campaigns.executer_unite(reglages, experiment_id, rang, horloge=horloge.now, dormir=horloge.dormir) == "termine"
    )
    assert [a["repetition"] for a in passages.appels] == [4]
    assert [o["identite"] for o in pilote.ouverts] == ["comptes-temoin-b"]  # directement l'autre identité
    assert cx.execute("SELECT COUNT(*) FROM bannissements").fetchone()[0] == 1  # aucun second bannissement


# ── Le fichier de l'essai ──────────────────────────────────────────────────────────────────────


def test_le_fichier_de_l_essai_des_comptes(reglages):
    e = campaigns.lire(FICHIER_ESSAI, reglages)
    assert e.protections == ["endurance"] and e.scenarios == ["visite"] and e.monde == "serie"
    assert e.espacement is not None  # sans cadence, l'état de l'identité n'est pas relu avant chaque visite
    assert e.concurrency >= len(e.engines) >= 2
    bras = {m.nom_affiche: m for m in e.engines}
    sujet, temoin = bras["sujet-compte"], bras["temoin-compte"]
    assert sujet.compte and sujet.options["identite"] and sujet.bannir_avant_visite is None
    assert e.visites_de(sujet) >= 3
    assert temoin.compte and temoin.compte != sujet.compte  # chacun son compte, chacun son monde
    assert temoin.bannir_avant_visite is not None and temoin.identite_apres_bannissement
    assert temoin.identite_apres_bannissement != temoin.options["identite"]
    assert e.visites_de(temoin) == temoin.bannir_avant_visite + 1  # une visite de l'autre identité après le refus
    # Sous la limite de débit de l'endurance : 240 pages par heure et par visiteur (environ 25 comptées par visite de 15).
    assert e.pages_par_visite <= 10
    # Environ 15 minutes : visites de 1 à 2 minutes, écart fixe compté de la fin de l'une au début de la suivante.
    assert e.espacement.mode == "fixe" and max(e.visites_de(m) for m in e.engines) * (2 + e.espacement.minutes) <= 25
    noms = {sujet.options["identite"], temoin.options["identite"], temoin.identite_apres_bannissement}
    assert len(noms) == 3
