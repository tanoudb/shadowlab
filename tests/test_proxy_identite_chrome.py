"""Proxy par identité (étape 3.2) avec un VRAI Google Chrome : `docs/recherche/proxy-par-identite-2026-11-17.md` § 4.

Identité native (`identite_native`, `headless: false`, `channel: chrome`), une cible locale qui note, pour chaque
connexion reçue, le port source, et de faux proxys qui notent, pour chaque connexion sortante, le port local de leur
socket : si le port source vu par la cible est celui d'un proxy, la requête est passée par lui.

Chrome est lent à lancer : le scénario « deux identités » (A, proxy HTTP ; B, proxy SOCKS5) est joué UNE fois par une
fixture de module, puis chaque exigence (a, c, e, g) a son test, son `assert` et son message. D'autres scénarios ont
leur propre lancement : mauvais mot de passe (b), périmètre strict (d, un lancement pour quatre tests), WebRTC (f).

Écarts et lectures du document (voir aussi le compte rendu) :
- La cible est en HTTP simple : Chrome envoie `GET http://…` au relais (pas `CONNECT`). Un refus du relais (`403`
  hors périmètre, `502` proxy qui dit non) n'arrive donc pas comme une exception de la navigation mais comme une
  PAGE d'erreur de statut 403 ou 502 (une exception n'apparaît que pour un `CONNECT` refusé, donc en https). Les tests
  b et d acceptent « exception OU statut d'erreur » et jugent sur le réseau (cible sans connexion, proxy sans connexion
  vers l'hôte interdit, compte des refus).
- `pilote._relais` : le relais de l'identité (`None` sans proxy). C'est une CONVENTION DE TEST, pas une interface du
  document : l'agent qui écrit le code crée cet attribut sur `DriverNoezia`.
- `interaction_post_page: false` (comme `tests/test_identite.py`) : les gestes humains ne regardent pas le réseau.
- La page de test écrit un élément `#fini` (et le titre « fini ») quand son appel de données est revenu : le pilote
  n'attend pas un titre, il attend un élément (`wait_for_element`).
- `SHADOWLAB_PROXY` est réglé sur une adresse morte pendant les scénarios : une identité qui a un proxy ne retombe
  JAMAIS dessus (§ 2.4) ; si le code s'en servait, tout échouerait.
- Sockets (g) : `psutil` sur l'arbre de processus de Chrome, toutes les 0,2 s ; le test saute avec la raison si
  l'échantillonnage est impossible (accès refusé, aucune connexion vers le relais vue).
"""

from __future__ import annotations

import base64
import contextlib
import json
import logging
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pytest
from outils_proxy import (
    CibleDeTest,
    Echantillonneur,
    EcouteStunDeTest,
    ProxyHttpDeTest,
    ProxySocks5DeTest,
    port_ferme,
)

from shadowlab.engines import registre

# `declarer_proxy` est importé en tête : tant qu'il n'existe pas, la collecte échoue (ImportError) pour cette raison.
from shadowlab.engines.noezia.identite import declarer_proxy
from shadowlab.perimetre import DestinationRefusee

pytestmark = pytest.mark.integration

NOMS_DU_PROXY = {"cible-dns.test": "127.0.0.1"}  # un nom que seuls les faux proxys connaissent
SECRETS = ("secret-a", "secret-b", "a-user", "b-user")
EN_BASE64 = tuple(
    base64.b64encode(f"{u}:{p}".encode()).decode() for u, p in (("a-user", "secret-a"), ("b-user", "secret-b"))
)
JETONS = SECRETS + EN_BASE64


def _chrome_installe() -> bool:
    """Google Chrome (pas le Chromium de Playwright) est-il installé ? Même critère que `tests/test_integration.py`."""
    if sys.platform == "darwin":
        return Path("/Applications/Google Chrome.app").exists()
    return any(shutil.which(nom) for nom in ("google-chrome", "google-chrome-stable"))


@pytest.fixture(scope="module")
def chrome_requis():
    if not _chrome_installe():
        pytest.skip("Google Chrome n'est pas installé (channel: chrome)")


def options(nom: str) -> dict:
    return {
        "identite": nom,
        "identite_native": True,
        "headless": False,
        "channel": "chrome",
        "interaction_post_page": False,
    }


def pilote_noezia(hotes: tuple[str, ...], nom: str):
    return registre()["noezia"](hotes, options(nom))


@pytest.fixture
def racine(tmp_path, monkeypatch):
    dossier = tmp_path / "identites"
    monkeypatch.setenv("SHADOWLAB_IDENTITES", str(dossier))
    return dossier


@pytest.fixture(scope="module")
def environnement(tmp_path_factory):
    """Les identités des scénarios de module vivent dans un dossier temporaire."""
    racine = tmp_path_factory.mktemp("identites-proxy")
    reglage = pytest.MonkeyPatch()
    reglage.setenv("SHADOWLAB_IDENTITES", str(racine))
    yield racine
    reglage.undo()


@contextlib.contextmanager
def proxy_unique_mort():
    """`SHADOWLAB_PROXY` sur une adresse morte : une identité qui a un proxy ne doit jamais s'en servir (§ 2.4). Pas
    pour le témoin WebRTC ni pour une identité sans proxy : ceux-là s'en serviraient, comme avant."""
    reglage = pytest.MonkeyPatch()
    reglage.setenv("SHADOWLAB_PROXY", f"http://127.0.0.1:{port_ferme()}")
    try:
        yield
    finally:
        reglage.undo()


def charger(pilote, url: str) -> dict:
    """Charge `url` puis attend `#fini` ; rend ce qui s'est passé, sans rien affirmer (les tests affirment)."""
    page: dict = {"url": url, "statut": None, "fini": False, "exception": None}
    try:
        page["statut"] = pilote.navigate(url).status
        if page["statut"] == 200:  # une page d'erreur (403, 502) n'écrira jamais `#fini` : inutile d'attendre
            page["fini"] = pilote.wait_for_element("#fini", 15000) == "fini"
    except Exception as exc:  # noqa: BLE001 — une navigation qui échoue est un résultat, pas une panne du test
        page["exception"] = repr(exc)
    return page


class Journaux(logging.Handler):
    """Tout ce que le code journalise pendant le scénario (niveau DEBUG), pour y chercher les identifiants."""

    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.lignes: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lignes.append(f"{record.name} {record.levelname} {record.getMessage()}")

    def texte(self) -> str:
        return "\n".join(self.lignes)


# ── Scénario « deux identités » : A (proxy HTTP) puis B (proxy SOCKS5) ──────


@dataclass
class Visite:
    lettre: str
    nom: str
    pages: list[dict]
    configuration: dict
    versions: dict
    demandes: list[tuple]
    echantillon: Echantillonneur
    dossier: Path


@dataclass
class Observations:
    visites: dict[str, Visite]
    cible_connexions: list[int]
    cible_requetes: list[dict]
    proxy_connexions: dict[str, list[dict]]
    journaux: str

    def requetes_de(self, lettre: str) -> list[dict]:
        """Les requêtes de la cible qui portent l'identifiant de cette identité (page normale et page par nom DNS)."""
        ids = {f"id={lettre}", f"id=dns-{lettre}"}
        return [r for r in self.cible_requetes if ids & set(r["chemin"].split("?", 1)[-1].split("&"))]

    def ports(self, lettre: str) -> set[int]:
        return {c["port_source"] for c in self.proxy_connexions[lettre]}


def visiter(nom: str, lettre: str, cible: CibleDeTest, racine: Path) -> Visite:
    """Une visite : Chrome s'ouvre sur l'identité, charge la page, puis la même par un nom que seul le proxy connaît."""
    pilote = pilote_noezia(("*",), nom)
    pilote.open()
    echantillon = None
    try:
        pilote.start_session()
        echantillon = Echantillonneur(nom, _port(pilote._relais))
        echantillon.start()
        pages = [
            charger(pilote, cible.url(f"/page?id={lettre}")),
            charger(pilote, f"http://cible-dns.test:{cible.port}/page?id=dns-{lettre}"),
        ]
        echantillon.arreter()
        demandes = [tuple(d) for d in pilote._relais.demandes]
        visite = Visite(
            lettre, nom, pages, pilote.configuration(), pilote.versions(), demandes, echantillon, racine / nom
        )
        pilote.close_session()
    finally:
        if echantillon is not None and echantillon.is_alive():
            echantillon.arreter()
        pilote.close()
    return visite


def _port(relais) -> int:
    return int(relais.adresse.rsplit(":", 1)[1])


@pytest.fixture(scope="module")
def observations(chrome_requis, environnement) -> Observations:
    journaux = Journaux()
    racine_logs = logging.getLogger()
    niveau = racine_logs.level
    racine_logs.addHandler(journaux)
    racine_logs.setLevel(logging.DEBUG)
    try:
        with (
            proxy_unique_mort(),
            CibleDeTest(delai_xhr_s=0.8) as cible,  # l'appel de données traîne : les connexions restent ouvertes assez
            ProxyHttpDeTest("a-user", "secret-a", nom="A", noms_connus=NOMS_DU_PROXY) as proxy_a,
            ProxySocks5DeTest("b-user", "secret-b", nom="B", noms_connus=NOMS_DU_PROXY) as proxy_b,
        ):
            declarer_proxy("identite-a", proxy_a.adresse, "a-user", "secret-a")
            declarer_proxy("identite-b", proxy_b.adresse, "b-user", "secret-b")
            visites = {
                "A": visiter("identite-a", "A", cible, environnement),
                "B": visiter("identite-b", "B", cible, environnement),
            }
            time.sleep(0.5)  # les dernières connexions se terminent
            return Observations(
                visites=visites,
                cible_connexions=cible.connexions_recues,
                cible_requetes=cible.requetes,
                proxy_connexions={"A": list(proxy_a.connexions), "B": list(proxy_b.connexions)},
                journaux=journaux.texte(),
            )
    finally:
        racine_logs.removeHandler(journaux)
        racine_logs.setLevel(niveau)


# ── a. Deux identités, deux sorties ────────────────────────────────────────


def test_a_les_deux_identites_ont_chargees_leur_page_avec_toutes_ses_ressources(observations):
    for lettre, visite in observations.visites.items():
        for page in visite.pages:
            assert page["exception"] is None, f"{lettre} : {page['url']} a échoué : {page['exception']}"
            assert page["statut"] == 200 and page["fini"], f"{lettre} : page incomplète : {page}"
        chemins = {r["chemin"].split("?")[0] for r in observations.requetes_de(lettre)}
        assert {"/page", "/img.png", "/s.js", "/xhr"} <= chemins, f"{lettre} : la cible n'a reçu que {sorted(chemins)}"


def test_a_chaque_requete_de_chaque_identite_ne_passe_que_par_son_proxy(observations):
    ports_a, ports_b = observations.ports("A"), observations.ports("B")
    assert ports_a, "le proxy A n'a reçu aucune connexion vers la cible"
    assert ports_b, "le proxy B n'a reçu aucune connexion vers la cible"
    assert not ports_a & ports_b, f"les deux jeux de ports sources se recoupent : {ports_a & ports_b}"
    for lettre, propres, autres in (("A", ports_a, ports_b), ("B", ports_b, ports_a)):
        requetes = observations.requetes_de(lettre)
        assert requetes, f"la cible n'a rien reçu de {lettre}"
        for requete in requetes:
            assert requete["port_source"] in propres, f"{lettre} : {requete['chemin']} n'est pas passée par son proxy"
            assert requete["port_source"] not in autres, f"{lettre} : {requete['chemin']} est passée par l'autre proxy"


def test_a_aucune_connexion_directe_de_chrome_vers_la_cible(observations):
    vus = set(observations.cible_connexions)
    sorties = observations.ports("A") | observations.ports("B")
    assert vus, "la cible n'a reçu aucune connexion"
    assert vus <= sorties, f"connexions qui ne viennent d'aucun proxy (donc directes) : {sorted(vus - sorties)}"


def test_a_sans_repli_sur_le_proxy_unique_du_processus(observations):
    # `SHADOWLAB_PROXY` pointe sur une adresse morte pendant ce module : si une identité à proxy s'en servait, ses pages
    # n'arriveraient pas (voir l'en-tête).
    for visite in observations.visites.values():
        assert all(page["fini"] for page in visite.pages), f"{visite.lettre} : {visite.pages}"


def test_a_le_relais_note_des_demandes_transmises_et_aucun_refus_de_perimetre(observations):
    for lettre, visite in observations.visites.items():
        transmises = [d for d in visite.demandes if d[3] == "transmise"]
        assert transmises, f"{lettre} : aucune demande transmise ({visite.demandes[:5]})"
        assert {d[3] for d in visite.demandes} <= {"transmise", "refusee_amont", "echec_amont"}, (
            f"{lettre} : en mode illimité rien n'est refusé pour le périmètre : {visite.demandes}"
        )


# ── c. Pas de fuite d'identifiants ─────────────────────────────────────────


def _fichiers(dossier: Path):
    for chemin, _, noms in os.walk(dossier):
        for nom in noms:
            fichier = Path(chemin) / nom
            if not fichier.is_symlink() and fichier.is_file():
                yield fichier


def _autour(contenu: bytes, motif: bytes, marge: int = 40) -> bytes:
    """Quelques dizaines d'octets autour de la première correspondance : de quoi voir si c'est un vrai identifiant ou
    une coïncidence (`a-user` dans `data-user`…), ce qu'un simple « trouvé » ne dit pas."""
    debut = contenu.find(motif)
    return contenu[max(0, debut - marge) : debut + len(motif) + marge]


def test_c_ni_configuration_ni_versions_ni_journaux_ne_contiennent_d_identifiant(observations):
    textes = {"journaux": observations.journaux}
    for lettre, visite in observations.visites.items():
        textes[f"configuration() de {lettre}"] = json.dumps(visite.configuration)
        textes[f"versions() de {lettre}"] = json.dumps(visite.versions)
        textes[f"demandes du relais de {lettre}"] = repr(visite.demandes)
    for nom, texte in textes.items():
        for secret in SECRETS:
            assert secret not in texte, f"{secret!r} apparaît dans {nom} : {_autour(texte.encode(), secret.encode())}"
    for lettre in ("A", "B"):
        masque = observations.visites[lettre].configuration.get("identite_proxy", "")
        assert masque.count("***") == 2, f"{lettre} : le masque est attendu dans configuration() (reçu : {masque!r})"


def test_c_aucun_fichier_de_l_identite_sauf_proxy_json_ne_contient_d_identifiant(observations):
    lus = 0
    for visite in observations.visites.values():
        for fichier in _fichiers(visite.dossier):
            if fichier.name == "proxy.json" and fichier.parent == visite.dossier:
                continue
            try:
                contenu = fichier.read_bytes()
            except OSError:
                continue
            lus += 1
            for secret in SECRETS:
                assert secret.encode() not in contenu, (
                    f"{secret!r} dans {fichier} : {_autour(contenu, secret.encode())}"
                )
    assert lus > 3, "le profil de Chrome et les fichiers de l'identité auraient dû être relus"


def test_c_les_identifiants_ne_sont_ni_dans_les_arguments_de_chrome_ni_du_pilote(observations):
    for lettre, visite in observations.visites.items():
        lignes = visite.echantillon.lignes_de_commande
        if not lignes:
            pytest.skip("aucune ligne de commande lue (psutil refusé) : rien à vérifier")
        for ligne in lignes:
            for secret in JETONS:
                assert secret not in ligne, (
                    f"{lettre} : {secret!r} dans une ligne de commande : {_autour(ligne.encode(), secret.encode(), 80)}"
                )


def test_c_le_fichier_proxy_json_reste_en_0600(observations):
    for visite in observations.visites.values():
        assert (visite.dossier / "proxy.json").stat().st_mode & 0o777 == 0o600
        assert visite.dossier.stat().st_mode & 0o777 == 0o700


# ── e. DNS : un nom que seul le proxy connaît ──────────────────────────────


def test_e_un_nom_que_seul_le_proxy_resout_se_charge_sans_dns_local(observations):
    for lettre, visite in observations.visites.items():
        page = visite.pages[1]
        assert page["exception"] is None and page["statut"] == 200 and page["fini"], (
            f"{lettre} : la page par nom DNS n'a pas chargé : {page}"
        )
        noms = {c["hote"] for c in observations.proxy_connexions[lettre]}
        assert "cible-dns.test" in noms, f"{lettre} : le proxy n'a pas reçu le NOM (reçu : {sorted(noms)})"
        assert any(d[1] == "cible-dns.test" for d in visite.demandes), f"{lettre} : le relais n'a pas vu le nom"
        propres = observations.ports(lettre)
        chemins = [r for r in observations.cible_requetes if f"id=dns-{lettre}" in r["chemin"]]
        assert chemins and all(r["port_source"] in propres for r in chemins)


# ── g. Sockets de l'arbre de processus de Chrome ───────────────────────────


def test_g_aucune_connexion_tcp_de_chrome_vers_autre_chose_que_le_relais(observations):
    for lettre, visite in observations.visites.items():
        ech = visite.echantillon
        if ech.echantillons == 0:
            pytest.skip(
                f"{lettre} : le processus de Chrome n'a jamais été retrouvé (psutil) : échantillonnage impossible"
            )
        print(
            f"[g] {lettre} : {ech.echantillons} échantillons, {ech.vers_le_relais} connexions vues vers le relais, "
            f"{ech.acces_refuses} accès refusés ; sockets UDP vus (rien d'affirmé) : {sorted(ech.udp)}"
        )
        assert not ech.interdites, (
            f"{lettre} : connexions TCP vers autre chose que le relais : {sorted(ech.interdites)}"
        )
        if ech.vers_le_relais == 0:
            pytest.skip(f"{lettre} : aucune connexion vers le relais vue : l'échantillonnage ne prouve rien ici")


# ── b. Mauvais mot de passe ────────────────────────────────────────────────


@pytest.mark.parametrize("schema", ["http", "socks5"])
def test_b_mauvais_mot_de_passe_la_page_echoue_et_la_cible_ne_recoit_rien(chrome_requis, racine, schema):
    faux = ProxyHttpDeTest if schema == "http" else ProxySocks5DeTest
    with CibleDeTest() as cible, faux("m-user", "bon-mdp", nom="M") as proxy:
        declarer_proxy("identite-m", proxy.adresse, "m-user", "mauvais-mdp")
        pilote = pilote_noezia(("*",), "identite-m")
        pilote.open()
        try:
            pilote.start_session()
            page = charger(pilote, cible.url("/page?id=M"))
            pilote.close_session()
        finally:
            pilote.close()
        time.sleep(0.5)
        connexions_cible = cible.connexions_recues
        refus, connexions_proxy = proxy.refus, list(proxy.connexions)
    # Cible en HTTP simple : le 502 du relais arrive comme une page (statut 502), pas comme une exception (en-tête).
    assert page["exception"] is not None or page["statut"] == 502, f"la navigation aurait dû échouer : {page}"
    assert page["statut"] != 407, "jamais de 407 jusqu'à Chrome : il demanderait des identifiants"
    assert not page["fini"], "la page de la cible ne doit pas avoir fonctionné"
    assert connexions_cible == [], f"la cible a reçu des connexions : {connexions_cible}"
    assert connexions_proxy == [], "le proxy n'a ouvert aucune connexion vers la cible"
    assert refus >= 1, "le proxy aurait dû compter au moins un refus d'authentification"


# ── d. Périmètre strict avec proxy ─────────────────────────────────────────


@dataclass
class ObservationsStrictes:
    page: dict
    refus_exemple: bool
    redirection: dict
    proxy_connexions: list[dict]
    demandes: list[tuple]
    connexions_cible: list[int]
    connexions_cible2: list[int]
    port_cible: int
    port_cible2: int


@pytest.fixture(scope="module")
def strict(chrome_requis, environnement) -> ObservationsStrictes:
    with (
        proxy_unique_mort(),
        CibleDeTest() as cible2,
        CibleDeTest(cible2=cible2) as cible,
        ProxyHttpDeTest("p-user", "secret-p", nom="P") as proxy,
    ):
        declarer_proxy("identite-p", proxy.adresse, "p-user", "secret-p")
        pilote = pilote_noezia(("127.0.0.1",), "identite-p")  # mode strict : `localhost` n'est pas dans la liste
        pilote.open()
        try:
            pilote.start_session()
            page = charger(pilote, cible.url("/page?id=P"))
            try:
                pilote.navigate("https://example.com/")
                refus_exemple = False
            except DestinationRefusee:
                refus_exemple = True
            redirection: dict = {"exception": None, "statut": None, "url": None, "atteint": False}
            try:
                resultat = pilote.navigate(cible.url("/redirige-dehors"))
                redirection.update(statut=resultat.status, url=resultat.url, atteint="cible-atteinte" in pilote.dom())
            except Exception as exc:  # noqa: BLE001 — un échec de la navigation est l'effet voulu
                redirection["exception"] = repr(exc)
            demandes = [tuple(d) for d in pilote._relais.demandes]
            pilote.close_session()
        finally:
            pilote.close()
        time.sleep(0.5)
        return ObservationsStrictes(
            page=page,
            refus_exemple=refus_exemple,
            redirection=redirection,
            proxy_connexions=list(proxy.connexions),
            demandes=demandes,
            connexions_cible=cible.connexions_recues,
            connexions_cible2=cible2.connexions_recues,
            port_cible=cible.port,
            port_cible2=cible2.port,
        )


def test_d_en_mode_strict_la_page_de_la_cible_charge_par_le_proxy(strict):
    assert strict.page["exception"] is None and strict.page["statut"] == 200 and strict.page["fini"], strict.page
    ports_proxy = {c["port_source"] for c in strict.proxy_connexions}
    assert ports_proxy, "le proxy n'a reçu aucune connexion : la page est passée en direct"
    assert set(strict.connexions_cible) <= ports_proxy, (
        "des connexions de la cible ne viennent pas du proxy : le mode strict a laissé un chemin direct"
    )


def test_d_une_adresse_hors_perimetre_est_refusee_avant_toute_requete(strict):
    assert strict.refus_exemple, "`navigate('https://example.com/')` aurait dû lever DestinationRefusee"
    assert not [c for c in strict.proxy_connexions if "example.com" in c["hote"]]


def test_d_la_redirection_vers_un_autre_hote_n_atteint_pas_le_second_hote(strict):
    redirection = strict.redirection
    assert redirection["exception"] is not None or redirection["statut"] != 200, (
        f"la redirection vers `localhost` ne devrait pas aboutir à une page normale : {redirection}"
    )
    assert not redirection["atteint"], "la page du second hôte s'est affichée"
    assert strict.connexions_cible2 == [], "le second hôte a reçu une connexion"


def test_d_le_proxy_amont_n_a_recu_aucune_connexion_vers_localhost(strict):
    interdits = [
        c for c in strict.proxy_connexions if c["hote"].lower() == "localhost" or c["port"] == strict.port_cible2
    ]
    assert not interdits, f"connexions du proxy vers le second hôte : {interdits}"
    refusees = [d for d in strict.demandes if d[1] == "localhost" and d[3] == "refusee_perimetre"]
    coupee_avant = strict.redirection["exception"] is not None  # un échec de navigation peut venir d'avant le relais
    assert refusees or coupee_avant, (
        f"le relais aurait dû noter un refus de périmètre pour localhost : {strict.demandes}"
    )


# ── f. WebRTC ──────────────────────────────────────────────────────────────


def _charger_webrtc(nom: str, cible: CibleDeTest) -> dict:
    pilote = pilote_noezia(("*",), nom)
    pilote.open()
    try:
        pilote.start_session()
        page = charger(pilote, cible.url("/webrtc"))
        pilote.close_session()
    finally:
        pilote.close()
    time.sleep(0.5)
    return page


def test_f_webrtc_sans_proxy_le_temoin_voit_la_fuite_avec_proxy_aucun_paquet_udp(chrome_requis, racine, monkeypatch):
    monkeypatch.delenv("SHADOWLAB_PROXY", raising=False)  # le témoin n'a pas de proxy : même pas celui du processus
    with EcouteStunDeTest() as stun_temoin, CibleDeTest(port_stun=stun_temoin.port) as cible_temoin:
        page = _charger_webrtc("identite-temoin", cible_temoin)  # sans proxy : Chrome tel qu'il est
    assert page["exception"] is None and page["fini"], f"la page WebRTC du témoin n'a pas fini : {page}"
    if stun_temoin.paquets == 0:
        pytest.skip(
            "témoin sans effet : aucun paquet UDP n'est arrivé au STUN local sans proxy, le test ne sait pas voir "
            "la fuite sur cette machine"
        )
    with (
        EcouteStunDeTest() as stun,
        CibleDeTest(port_stun=stun.port) as cible,
        ProxyHttpDeTest("w-user", "w-mdp", nom="W") as proxy,
    ):
        declarer_proxy("identite-webrtc", proxy.adresse, "w-user", "w-mdp")
        page = _charger_webrtc("identite-webrtc", cible)
        assert page["exception"] is None and page["fini"], f"la page WebRTC avec proxy n'a pas fini : {page}"
        assert proxy.connexions, "la page n'est pas passée par le proxy"
    assert stun.paquets == 0, (
        f"{stun.paquets} paquet(s) UDP ont atteint le STUN local malgré le proxy (le témoin en a reçu "
        f"{stun_temoin.paquets}) : sources {stun.sources}"
    )
