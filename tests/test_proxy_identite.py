"""Proxy par identité (étape 3.2), sans navigateur : `docs/recherche/proxy-par-identite-2026-11-17.md` §§ 3 et 4.

Écrits AVANT le code (`engines/noezia/proxy_identite.py` ; `declarer_proxy`, `lire_proxy`, `FICHIER_PROXY` dans
`identite.py` ; `identite_proxy` dans `configuration()`), puis vus en échec. Les aides (`outils_proxy.py`) ont leurs
propres tests (`test_outils_proxy.py`) : elles ne dépendent de rien de ce qui est testé ici.

Le module à tester est importé par la fixture `px` et non en tête : tant qu'il n'existe pas, les tests qui s'en servent
échouent un par un en `ModuleNotFoundError`, au lieu d'une seule erreur de collecte qui cache le reste. Ceux qui n'ont
besoin que de `identite.py` ou de `configuration()` échouent en `AttributeError` (`declarer_proxy`, `lire_proxy`) ou en
`KeyError` (`identite_proxy`). `test_aucune_option_de_campagne_ne_porte_le_proxy` est une garde : elle passe déjà.

Lectures du document choisies quand il se tait (la plus simple) :
- `Demande.methode` est la méthode HTTP telle que le client l'a écrite (`CONNECT`, `GET`) ;
- un proxy amont qui répond par un refus (407, SOCKS5 d'échec, 502…) donne `refusee_amont`, un proxy qu'on n'atteint pas
  (éteint) donne `echec_amont` ; un délai dépassé chez un amont muet donne l'un ou l'autre (non tranché) ;
- `with RelaisProxy(...) as relais` démarre le relais et rend `relais` ;
- le port d'une adresse proxy absent, ou non numérique, n'est pas testé : seul « hors de 1 à 65535 » est écrit ;
- « propriétaire autre » (`lire_proxy` refuse un fichier d'un autre utilisateur) n'est pas testé : il faudrait `chown`,
  donc être root.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import importlib
import ipaddress
import json
import logging
import os
import socket
import threading
import time
from urllib.parse import urlsplit

import pytest
from outils_proxy import (
    AmontMuet,
    CibleDeTest,
    ProxyHttpDeTest,
    ProxySocks5DeTest,
    attendre,
    echanger,
    ecrire_proxy,
    get_absolu,
    get_dans_le_tunnel,
    lire_jusqu_a_fin,
    lire_reponse,
    lire_tete,
    ouvrir_connexion,
    ouvrir_tunnel,
    port_ferme,
    statut_de,
)

from shadowlab.engines import registre
from shadowlab.engines.noezia import identite as ident
from shadowlab.engines.noezia import moteur

NATIVE = {"identite_native": True, "headless": False, "channel": "chrome"}
NOMS_DU_PROXY = {"cible-dns.test": "127.0.0.1"}  # un nom que seuls les faux proxys connaissent


@pytest.fixture(scope="module")
def px():
    """Le module à tester (importé ici : voir l'en-tête)."""
    return importlib.import_module("shadowlab.engines.noezia.proxy_identite")


@pytest.fixture
def racine(tmp_path, monkeypatch):
    dossier = tmp_path / "identites"
    monkeypatch.setenv("SHADOWLAB_IDENTITES", str(dossier))
    return dossier


# ── analyser, ProxyIdentite, masque ────────────────────────────────────────


def test_proxy_invalide_est_une_valeur_invalide(px):
    assert issubclass(px.ProxyInvalide, ValueError)


def test_analyser_http(px):
    p = px.analyser("http://proxy.exemple:3128", "u", "secret-x")
    assert (p.schema, p.hote, p.port, p.utilisateur, p.mot_de_passe) == ("http", "proxy.exemple", 3128, "u", "secret-x")


def test_analyser_socks5(px):
    p = px.analyser("socks5://127.0.0.1:1080", "u", "secret-x")
    assert (p.schema, p.hote, p.port, p.utilisateur, p.mot_de_passe) == ("socks5", "127.0.0.1", 1080, "u", "secret-x")


def test_analyser_identifiants_hors_adresse_et_facultatifs(px):
    p = px.analyser("http://h:3128")
    assert (p.utilisateur, p.mot_de_passe) == (None, None)
    assert px.analyser("http://h:1").port == 1 and px.analyser("http://h:65535").port == 65535


def test_proxy_identite_est_immuable(px):
    p = px.analyser("http://h:3128", "u", "p")
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.port = 1  # type: ignore[misc]


@pytest.mark.parametrize(
    "serveur",
    [
        "https://h:3128",
        "ftp://h:21",
        "socks4://h:1080",
        "socks5h://h:1080",
        "h:3128",
        "",
        "http://:3128",
        "http://h:0",
        "http://h:70000",
        "http://h:-1",
    ],
)
def test_analyser_refuse(px, serveur):
    with pytest.raises(px.ProxyInvalide):
        px.analyser(serveur, "u", "p")


@pytest.mark.parametrize(
    "serveur",
    ["http://u:secret-dans-adresse@h:3128", "http://u@h:3128", "socks5://:secret-dans-adresse@h:1080"],
)
def test_analyser_refuse_les_identifiants_dans_l_adresse_sans_les_repeter(px, serveur):
    with pytest.raises(px.ProxyInvalide) as erreur:
        px.analyser(serveur)
    assert "secret-dans-adresse" not in str(erreur.value), "le message d'erreur ne répète pas l'adresse"


def test_analyser_message_sans_le_mot_de_passe_donne_a_part(px):
    with pytest.raises(px.ProxyInvalide) as erreur:
        px.analyser("https://h:3128", "a-user", "secret-param")
    assert "secret-param" not in str(erreur.value)


def test_masque_avec_identifiants(px):
    p = px.analyser("http://127.0.0.1:3128", "a-user", "secret-a")
    assert p.masque() == "http://***:***@127.0.0.1:3128"
    assert repr(p) == str(p) == p.masque() == f"{p}"
    assert px.analyser("socks5://h:1080", "u", "p").masque() == "socks5://***:***@h:1080"


def test_masque_sans_identifiants(px):
    p = px.analyser("http://h:3128")
    assert p.masque() == "http://h:3128" and repr(p) == str(p) == "http://h:3128"


def test_ni_le_mot_de_passe_ni_l_utilisateur_dans_aucune_forme_texte(px):
    p = px.analyser("http://127.0.0.1:3128", "a-user", "secret-a")
    formes = [repr(p), str(p), p.masque(), f"{p!r}", format(p), repr([p]), repr({"p": p}), repr((p,))]
    for forme in formes:
        assert "secret-a" not in forme and "a-user" not in forme, forme
    champs = {champ.name: champ.repr for champ in dataclasses.fields(p)}
    assert champs["mot_de_passe"] is False, "le champ est hors du repr généré (repr=False)"


# ── declarer_proxy / lire_proxy ────────────────────────────────────────────


def test_declarer_ecrit_proxy_json_en_0600_dans_un_dossier_0700(racine):
    chemin = ident.declarer_proxy("a", "http://127.0.0.1:3128", "a-user", "secret-a")
    assert ident.FICHIER_PROXY == "proxy.json"
    assert chemin == racine / "a" / "proxy.json"
    assert chemin.stat().st_mode & 0o777 == 0o600
    assert chemin.parent.stat().st_mode & 0o777 == 0o700
    assert json.loads(chemin.read_text(encoding="utf-8")) == {
        "serveur": "http://127.0.0.1:3128",
        "utilisateur": "a-user",
        "mot_de_passe": "secret-a",
    }


@pytest.mark.parametrize("umask", [0o000, 0o022, 0o077])
def test_declarer_n_depend_pas_de_l_umask(racine, umask):
    ancien = os.umask(umask)
    try:
        chemin = ident.declarer_proxy("a", "http://h:3128", "u", "p")
    finally:
        os.umask(ancien)
    assert chemin.stat().st_mode & 0o777 == 0o600 and chemin.parent.stat().st_mode & 0o777 == 0o700


def test_declarer_puis_lire_redonne_le_meme_proxy(racine, px):
    ident.declarer_proxy("a", "socks5://127.0.0.1:1080", "u", "p")
    lu = ident.lire_proxy("a")
    assert isinstance(lu, px.ProxyIdentite)
    assert (lu.schema, lu.hote, lu.port, lu.utilisateur, lu.mot_de_passe) == ("socks5", "127.0.0.1", 1080, "u", "p")
    assert lu == px.analyser("socks5://127.0.0.1:1080", "u", "p")


def test_declarer_sans_identifiants(racine):
    ident.declarer_proxy("a", "http://h:3128")
    lu = ident.lire_proxy("a")
    assert (lu.utilisateur, lu.mot_de_passe) == (None, None) and lu.masque() == "http://h:3128"


def test_declarer_valide_avec_analyser_et_n_ecrit_rien_si_invalide(racine, px):
    with pytest.raises(px.ProxyInvalide):
        ident.declarer_proxy("a", "https://h:3128", "u", "p")
    with pytest.raises(px.ProxyInvalide):
        ident.declarer_proxy("a", "http://u:p@h:3128")
    assert not (racine / "a" / "proxy.json").exists()


@pytest.mark.parametrize("nom", ["../evade", "Majuscule", "a/b", ""])
def test_declarer_et_lire_refusent_un_nom_d_identite_invalide(racine, tmp_path, nom):
    with pytest.raises(ValueError):
        ident.declarer_proxy(nom, "http://h:3128", "u", "p")
    with pytest.raises(ValueError):
        ident.lire_proxy(nom)
    assert not (tmp_path / "evade").exists()
    assert not racine.exists() or not any(racine.iterdir()), "rien n'est créé pour un nom refusé"


def test_declarer_remplace_un_fichier_existant_et_remet_0600(racine):
    ecrire_proxy(racine, "a", "http://ancien:1", "u", "ancien-mdp", mode=0o644)
    ident.declarer_proxy("a", "http://nouveau:2", "u2", "nouveau-mdp")
    chemin = racine / "a" / "proxy.json"
    assert chemin.stat().st_mode & 0o777 == 0o600, "un fichier laissé en 0644 repasse en 0600"
    lu = ident.lire_proxy("a")
    assert (lu.hote, lu.port, lu.utilisateur, lu.mot_de_passe) == ("nouveau", 2, "u2", "nouveau-mdp")
    assert "ancien" not in chemin.read_text(encoding="utf-8")


def test_declarer_laisse_l_identite_ouvrable_et_le_proxy_lisible(racine):
    ident.declarer_proxy("a", "http://h:3128", "u", "p")
    ident.ouvrir("a").liberer()
    assert ident.lire_proxy("a") is not None
    assert (racine / "a").stat().st_mode & 0o777 == 0o700


def test_deux_identites_deux_proxys_jamais_melanges(racine):
    ident.declarer_proxy("a", "http://hote-a:1", "ua", "pa")
    ident.declarer_proxy("b", "socks5://hote-b:2", "ub", "pb")
    assert ident.lire_proxy("a").hote == "hote-a" and ident.lire_proxy("b").hote == "hote-b"
    assert ident.lire_proxy("c") is None


def test_lire_proxy_rend_none_sans_fichier_et_ne_cree_rien(racine):
    assert ident.lire_proxy("absente") is None
    assert not (racine / "absente").exists(), "lire ne crée rien (comme `lire_etat`)"
    ident.ouvrir("existe").liberer()  # une identité sans proxy : aucun fichier proxy.json
    assert ident.lire_proxy("existe") is None
    assert not (racine / "existe" / "proxy.json").exists()


def test_lire_proxy_lit_un_fichier_ecrit_a_la_main(racine, px):
    ecrire_proxy(racine, "a", "http://h:3128", "u", "p")
    assert ident.lire_proxy("a") == px.analyser("http://h:3128", "u", "p")


@pytest.mark.parametrize("mode", [0o600, 0o400])
def test_lire_proxy_accepte_les_droits_du_proprietaire_seul(racine, mode):
    ecrire_proxy(racine, "a", "http://h:3128", "u", "p", mode=mode)
    assert ident.lire_proxy("a") is not None


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o604, 0o660, 0o666])
def test_lire_proxy_refuse_un_fichier_lisible_par_le_groupe_ou_les_autres(racine, px, mode):
    ecrire_proxy(racine, "a", "http://h:3128", "a-user", "secret-fichier", mode=mode)
    with pytest.raises(px.ProxyInvalide) as erreur:
        ident.lire_proxy("a")
    assert "secret-fichier" not in str(erreur.value) and "a-user" not in str(erreur.value)


MAUVAIS_FICHIERS = {
    "json tronqué": '{"serveur": "http://h:1", "utilisateur": "u", "mot_de_passe": "secret-brut"',
    "vide": "",
    "pas un objet (liste)": '["secret-brut"]',
    "pas un objet (texte)": '"secret-brut"',
    "null": "null",
    "schéma inconnu (https)": '{"serveur": "https://h:1", "utilisateur": "u", "mot_de_passe": "secret-brut"}',
    "schéma inconnu (ftp)": '{"serveur": "ftp://h:1", "utilisateur": "u", "mot_de_passe": "secret-brut"}',
    "serveur manquant": '{"utilisateur": "u", "mot_de_passe": "secret-brut"}',
    "serveur pas une chaîne": '{"serveur": 3128, "utilisateur": "u", "mot_de_passe": "secret-brut"}',
    "serveur vide": '{"serveur": "", "utilisateur": "u", "mot_de_passe": "secret-brut"}',
    "identifiants dans l'adresse": '{"serveur": "http://u:secret-brut@h:1"}',
    "port hors limites": '{"serveur": "http://h:70000", "utilisateur": "u", "mot_de_passe": "secret-brut"}',
    "utilisateur pas une chaîne": '{"serveur": "http://h:1", "utilisateur": ["u"], "mot_de_passe": "secret-brut"}',
}


@pytest.mark.parametrize("brut", MAUVAIS_FICHIERS.values(), ids=MAUVAIS_FICHIERS.keys())
def test_lire_proxy_refuse_un_fichier_invalide_sans_le_mot_de_passe_dans_le_message(racine, px, brut):
    ecrire_proxy(racine, "a", "", brut=brut)  # en 0600 : seul le contenu est en cause
    with pytest.raises(px.ProxyInvalide) as erreur:
        ident.lire_proxy("a")
    assert "secret-brut" not in str(erreur.value), "ni le mot de passe ni le contenu du fichier dans le message"


# ── configuration() du pilote ──────────────────────────────────────────────


def pilote(nom: str | None = "x", **options):
    """Un pilote noezia (identité native, avec interface) : rien n'est lancé, `configuration()` se lit à froid."""
    options = {**NATIVE, **options}
    if nom is not None:
        options["identite"] = nom
    return registre()["noezia"](("127.0.0.1",), options)


def test_configuration_avec_proxy_contient_le_masque_et_aucun_identifiant(racine):
    ecrire_proxy(racine, "x", "http://127.0.0.1:3128", "a-user", "secret-a")  # écrit AVANT de construire le pilote
    conduite = pilote()
    conf = conduite.configuration()
    assert conf["identite_proxy"] == "http://***:***@127.0.0.1:3128"
    assert conf["identite"] == "x"
    for nom, valeur in (("configuration", conf), ("versions", conduite.versions())):
        texte = json.dumps(valeur)
        assert "secret-a" not in texte and "a-user" not in texte, f"{nom} : identifiants en clair"


def test_configuration_sans_proxy_pas_de_cle_et_le_reste_ne_change_pas(racine):
    sans = pilote().configuration()
    assert "identite_proxy" not in sans
    ecrire_proxy(racine, "x", "http://127.0.0.1:3128", "a-user", "secret-a")
    avec = pilote().configuration()
    assert (
        avec.get("identite_proxy") == "http://***:***@127.0.0.1:3128"
    )  # le proxy déclaré apparaît, et lui seul s'ajoute
    # Deux clés s'ajoutent avec un proxy : le masque et les arguments de lancement qu'il impose (voir le test suivant).
    assert {cle: v for cle, v in avec.items() if cle not in ("identite_proxy", "identite_proxy_arguments")} == sans


def test_configuration_chaque_identite_son_masque_et_sans_identite_pas_de_cle(racine):
    ecrire_proxy(racine, "x", "http://127.0.0.1:3128", "a-user", "secret-a")
    ecrire_proxy(racine, "y", "socks5://127.0.0.1:1080", "b-user", "secret-b")
    assert pilote("x").configuration()["identite_proxy"] == "http://***:***@127.0.0.1:3128"
    assert pilote("y").configuration()["identite_proxy"] == "socks5://***:***@127.0.0.1:1080"
    assert "identite_proxy" not in pilote("z").configuration()  # une identité sans fichier
    sans_identite = registre()["noezia"](("127.0.0.1",), {})
    assert "identite_proxy" not in sans_identite.configuration()


def test_configuration_declare_les_arguments_de_lancement_imposes_par_le_proxy(racine):
    """Règle du dépôt : tout réglage imposé est déclaré dans `configuration()` et enregistré avec les résultats."""
    sans = pilote().configuration()
    assert "identite_proxy_arguments" not in sans, "sans proxy déclaré : aucun argument imposé, aucune clé"
    ecrire_proxy(racine, "x", "http://127.0.0.1:3128", "a-user", "secret-a")
    conf = pilote().configuration()
    assert conf["identite_proxy_arguments"] == [moteur.ARGUMENT_WEBRTC_PROXY]
    texte = json.dumps(conf)
    assert "secret-a" not in texte and "a-user" not in texte
    assert "identite_proxy_arguments" not in registre()["noezia"](("127.0.0.1",), {}).configuration()


def test_aucune_option_de_campagne_ne_porte_le_proxy(racine):
    # Le proxy vit dans le dossier de l'identité, jamais dans une option (une campagne est versionnée et enregistrée).
    options = registre()["noezia"].options_permises
    assert not [cle for cle in options if "proxy" in cle]
    with pytest.raises(ValueError, match="option inconnue"):
        pilote(proxy="http://u:p@h:1")


@pytest.mark.parametrize("cas", ["droits", "json"])
def test_lancement_refuse_si_le_fichier_de_proxy_est_invalide_et_le_verrou_n_est_pas_pris(racine, px, cas):
    if cas == "droits":
        ecrire_proxy(racine, "x", "http://h:3128", "u", "p", mode=0o644)
    else:
        ecrire_proxy(racine, "x", "", brut="{pas du json")
    with pytest.raises(
        px.ProxyInvalide
    ):  # à la construction ou à `open()` : le document ne tranche pas, les deux refusent
        pilote().open()
    ident.ouvrir("x").liberer()  # `open()` lit le proxy AVANT de prendre le verrou de l'identité (§ 3)


def test_open_demarre_le_relais_et_close_l_arrete(px, racine):
    """`_relais` est une CONVENTION DE TEST : l'attribut de `DriverNoezia` qui porte le relais de l'identité (`None`
    sans proxy). Aucun Chrome ici : `open()` ne lance que le pilote Playwright, Chrome part à `start_session()`."""
    with ProxyHttpDeTest("u", "p", nom="C") as proxy:
        ident.declarer_proxy("identite-cycle", proxy.adresse, "u", "p")
        avec = registre()["noezia"](("*",), {**NATIVE, "identite": "identite-cycle"})
        avec.open()
        try:
            assert avec._relais is not None, "`open()` doit démarrer le relais d'une identité qui a un proxy"
            port = int(avec._relais.adresse.rsplit(":", 1)[1])
            ouvrir_connexion(port).close()  # il écoute
        finally:
            avec.close()
        with pytest.raises(OSError):
            socket.create_connection(("127.0.0.1", port), timeout=1)
    sans = registre()["noezia"](("*",), {**NATIVE, "identite": "identite-sans-proxy"})
    sans.open()
    try:
        assert sans._relais is None, "sans proxy déclaré : ni relais, ni changement"
        assert "identite_proxy" not in sans.configuration()
    finally:
        sans.close()


def test_une_identite_refusee_au_lancement_ne_laisse_pas_de_relais_vivant(px, racine):
    ecrire_proxy(racine, "x", "http://127.0.0.1:3128", "u", "p")
    donnees = {"nom": "x", "creee_le": "2026-11-01T10:00:00+00:00", "etat": "banni"}
    (racine / "x" / "identite.json").write_text(json.dumps(donnees), encoding="utf-8")
    avant = set(threading.enumerate())
    with pytest.raises(ident.IdentiteRefusee, match="banni"):
        pilote().open()
    restes = lambda: [fil for fil in set(threading.enumerate()) - avant if fil.is_alive()]  # noqa: E731
    assert attendre(lambda: not restes(), 3), [fil.name for fil in restes()]


# ── Le relais ──────────────────────────────────────────────────────────────


@pytest.fixture
def cible():
    with CibleDeTest() as c:
        yield c


@pytest.fixture(params=["http", "socks5"])
def amont(request):
    """Le faux proxy de l'identité : HTTP puis SOCKS5, identifiants `bon-user` / `bon-mdp`."""
    faux = ProxyHttpDeTest if request.param == "http" else ProxySocks5DeTest
    with faux("bon-user", "bon-mdp", noms_connus=NOMS_DU_PROXY) as proxy:
        yield proxy


def relais_vers(px, amont, hotes, *, supplementaires=(), utilisateur="bon-user", mot_de_passe="bon-mdp", delai_s=15.0):
    return px.RelaisProxy(
        px.analyser(amont.adresse, utilisateur, mot_de_passe),
        hotes,
        hotes_supplementaires=supplementaires,
        delai_s=delai_s,
    )


def port_de(relais) -> int:
    return int(relais.adresse.rsplit(":", 1)[1])


def vues(relais) -> list[tuple]:
    return [tuple(demande) for demande in relais.demandes]


def attendre_demandes(relais, nombre: int) -> None:
    assert attendre(lambda: len(relais.demandes) >= nombre), f"{len(relais.demandes)} demande(s) notée(s) sur {nombre}"


def test_demande_a_les_quatre_champs_du_document(px):
    assert px.Demande._fields == ("methode", "hote", "port", "decision")


def test_connect_avec_les_bons_identifiants_les_octets_passent_jusqu_a_la_cible(px, cible, amont, caplog):
    with caplog.at_level(logging.DEBUG), relais_vers(px, amont, ("127.0.0.1",)) as relais:
        statut, tete, sock = ouvrir_tunnel(port_de(relais), "127.0.0.1", cible.port)
        assert statut == 200 and b"200 Connection Established" in tete
        with sock:
            reponse = get_dans_le_tunnel(sock, "127.0.0.1", cible.port, "/page?id=A")
        attendre_demandes(relais, 1)
        assert vues(relais) == [("CONNECT", "127.0.0.1", cible.port, "transmise")]
    assert statut_de(reponse) == 200 and b"/img.png?id=A" in reponse
    assert amont.refus == 0
    (sortie,) = amont.connexions
    assert (sortie["hote"], sortie["port"]) == ("127.0.0.1", cible.port)
    assert cible.connexions_recues == [sortie["port_source"]], "la cible ne voit que la sortie du proxy"
    (requete,) = [r for r in cible.requetes if r["chemin"].startswith("/page")]
    assert "proxy-authorization" not in requete["entetes"], "rien du proxy ne passe dans le tunnel"
    for secret in ("bon-mdp", "bon-user"):
        for nom, texte in (("tête", tete), ("réponse", reponse), ("demandes", repr(relais.demandes).encode())):
            assert secret.encode() not in texte, f"{secret} dans {nom}"
        assert secret not in caplog.text, f"{secret} dans les journaux"


def test_toute_connexion_recue_par_la_cible_vient_du_proxy_connect_comme_requete_simple(px, cible, amont):
    with relais_vers(px, amont, ("127.0.0.1",)) as relais:
        for chemin in ("/page?id=1", "/img.png?id=1"):
            _, _, sock = ouvrir_tunnel(port_de(relais), "127.0.0.1", cible.port)
            with sock:
                get_dans_le_tunnel(sock, "127.0.0.1", cible.port, chemin)
        assert statut_de(get_absolu(port_de(relais), cible.url("/s.js?id=1"), delai_s=5)) == 200
    assert len(amont.connexions) == 3
    ports_du_proxy = {c["port_source"] for c in amont.connexions}
    assert len(ports_du_proxy) == 3 and set(cible.connexions_recues) == ports_du_proxy
    assert len(cible.connexions_recues) == 3, "aucune connexion de plus : rien n'est parti en direct"


@pytest.mark.parametrize(
    "identifiants",
    [("bon-user", "mdp-faux-xyz"), ("user-faux-xyz", "bon-mdp")],
    ids=["mauvais mot de passe", "mauvais utilisateur"],
)
def test_mauvais_identifiants_502_jamais_407_et_rien_n_arrive_a_la_cible(px, cible, amont, identifiants, caplog):
    utilisateur, mot_de_passe = identifiants
    with (
        caplog.at_level(logging.DEBUG),
        relais_vers(px, amont, ("127.0.0.1",), utilisateur=utilisateur, mot_de_passe=mot_de_passe) as relais,
    ):
        statut, tete, sock = ouvrir_tunnel(port_de(relais), "127.0.0.1", cible.port)
        try:
            reste = lire_jusqu_a_fin(sock, 1.0)
        except TimeoutError:  # le relais peut laisser la connexion ouverte : le document ne dit pas qu'il la ferme
            reste = b""
        sock.close()
        reponse_simple = get_absolu(port_de(relais), cible.url("/page?id=A"), delai_s=5)
        attendre_demandes(relais, 2)
        decisions = vues(relais)
    assert statut == 502 and statut_de(reponse_simple) == 502, "jamais 407 : Chrome demanderait des identifiants"
    tout = tete + reste + reponse_simple
    assert b"proxy-authenticate" not in tout.lower()
    assert amont.refus == 2 and amont.connexions == []
    time.sleep(0.3)
    assert cible.connexions_recues == [], "aucune connexion vers la cible, pas de repli direct"
    assert decisions == [
        ("CONNECT", "127.0.0.1", cible.port, "refusee_amont"),
        ("GET", "127.0.0.1", cible.port, "refusee_amont"),
    ]
    jetons = [utilisateur, mot_de_passe, "bon-user", "bon-mdp", "mdp-faux-xyz", "user-faux-xyz"]
    en_base64 = base64.b64encode(f"{utilisateur}:{mot_de_passe}".encode()).decode()
    for secret in [*jetons, f"{utilisateur}:{mot_de_passe}", en_base64]:
        assert secret.encode() not in tout, f"{secret} dans la réponse"
        assert secret not in repr(relais.demandes), f"{secret} dans `demandes`"
        assert secret not in caplog.text, f"{secret} dans les journaux"


@pytest.mark.parametrize("schema", ["http", "socks5"])
def test_amont_eteint_502_echec_amont_et_aucun_repli_direct_meme_en_mode_illimite(px, cible, schema):
    amont = px.analyser(f"{schema}://127.0.0.1:{port_ferme()}", "u", "p")
    with px.RelaisProxy(amont, ("*",)) as relais:
        statut, _, sock = ouvrir_tunnel(port_de(relais), "127.0.0.1", cible.port)
        sock.close()
        reponse = get_absolu(port_de(relais), cible.url("/page?id=A"), delai_s=5)
        attendre_demandes(relais, 2)
        decisions = vues(relais)
    assert statut == 502 and statut_de(reponse) == 502
    assert [d[3] for d in decisions] == ["echec_amont", "echec_amont"]
    time.sleep(0.3)
    assert cible.connexions_recues == [], "le proxy est éteint : la cible ne reçoit rien (pas de connexion directe)"


@pytest.mark.parametrize("schema", ["http", "socks5"])
def test_amont_muet_502_apres_le_delai_demande(px, cible, schema):
    with AmontMuet() as muet:  # accepte la connexion et ne répond jamais
        amont = px.analyser(muet.adresse.replace("http://", f"{schema}://"), "u", "p")
        with px.RelaisProxy(amont, ("*",), delai_s=0.5) as relais:
            debut = time.monotonic()
            statut, _, sock = ouvrir_tunnel(port_de(relais), "127.0.0.1", cible.port, delai_s=8)
            duree = time.monotonic() - debut
            sock.close()
            attendre_demandes(relais, 1)
            decision = vues(relais)[0][3]
    assert statut == 502 and duree < 5, f"le relais a mis {duree:.1f} s à renoncer (delai_s=0.5)"
    assert decision in ("echec_amont", "refusee_amont")  # délai dépassé : le document ne tranche pas
    time.sleep(0.3)
    assert cible.connexions_recues == []


@pytest.mark.parametrize("hote", ["localhost", "127.0.0.2", "10.1.2.3", "autre.test"])
def test_hors_perimetre_strict_403_et_le_proxy_n_est_jamais_contacte(px, cible, amont, hote):
    with relais_vers(px, amont, ("127.0.0.1",)) as relais:
        statut, _, sock = ouvrir_tunnel(port_de(relais), hote, cible.port)
        sock.close()
        reponse = get_absolu(port_de(relais), f"http://{hote}:{cible.port}/page?id=Z", delai_s=5)
        attendre_demandes(relais, 2)
        decisions = vues(relais)
    assert statut == 403 and statut_de(reponse) == 403
    assert amont.contacts == 0, "le proxy amont n'a reçu aucune connexion"
    assert amont.connexions == [] and amont.refus == 0
    assert decisions == [
        ("CONNECT", hote, cible.port, "refusee_perimetre"),
        ("GET", hote, cible.port, "refusee_perimetre"),
    ]
    time.sleep(0.3)
    assert cible.connexions_recues == []


@pytest.mark.parametrize("hote", ["127.0.0.1", "localhost", "cible-dns.test"])
def test_mode_illimite_tout_passe_et_le_nom_part_tel_quel_au_proxy(px, cible, amont, hote):
    with relais_vers(px, amont, ("*",)) as relais:
        statut, _, sock = ouvrir_tunnel(port_de(relais), hote, cible.port)
        with sock:
            via_connect = get_dans_le_tunnel(sock, hote, cible.port, "/page?id=I")
        via_get = get_absolu(port_de(relais), cible.url("/page?id=J", hote=hote), delai_s=5)
        attendre_demandes(relais, 2)
        decisions = vues(relais)
    assert statut == 200 and statut_de(via_connect) == 200 and statut_de(via_get) == 200
    assert decisions == [("CONNECT", hote, cible.port, "transmise"), ("GET", hote, cible.port, "transmise")]
    assert [c["hote"] for c in amont.connexions] == [hote, hote], "le nom est transmis tel quel (pas résolu avant)"


def test_mode_strict_un_nom_de_la_liste_n_est_jamais_resolu_localement(px, cible, amont, monkeypatch):
    """§ 3 : « Aucun nom n'est résolu localement par le relais (le nom part au proxy) ». Un nom autorisé de la liste
    (un hôte de défi, par exemple) n'est donc ni résolu par le relais ni refusé parce que le DNS local l'ignore.
    Point à surveiller à l'écriture : `perimetre.verifier_url` résout lui-même, par `getaddrinfo`, un nom explicitement
    autorisé (garde contre les réseaux internes) ; l'appeler tel quel ferait échouer ce test. Il faut contrôler la liste
    sans cette résolution."""
    resolus: list[str] = []
    vrai = socket.getaddrinfo

    def espion(hote, *args, **kwargs):
        try:
            ipaddress.ip_address(hote)
        except (ValueError, TypeError):
            resolus.append(str(hote))
        return vrai(hote, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", espion)
    with relais_vers(px, amont, ("127.0.0.1", "cible-dns.test")) as relais:
        statut, _, sock = ouvrir_tunnel(port_de(relais), "cible-dns.test", cible.port)
        sock.close()
        reponse = get_absolu(port_de(relais), cible.url("/page?id=D", hote="cible-dns.test"), delai_s=5)
    assert statut == 200 and statut_de(reponse) == 200
    assert "cible-dns.test" not in resolus, f"noms résolus par le relais : {resolus}"


def test_hotes_supplementaires_acceptes_mais_rien_d_autre(px, cible, amont):
    with relais_vers(px, amont, ("127.0.0.1",), supplementaires=("localhost",)) as relais:
        statut, _, sock = ouvrir_tunnel(port_de(relais), "localhost", cible.port)
        sock.close()
        reponse = get_absolu(port_de(relais), cible.url("/page?id=S", hote="localhost"), delai_s=5)
        autre, _, sock = ouvrir_tunnel(port_de(relais), "10.1.2.3", cible.port)
        sock.close()
        attendre_demandes(relais, 3)
        decisions = vues(relais)
    assert statut == 200 and statut_de(reponse) == 200 and autre == 403
    assert [d[3] for d in decisions] == ["transmise", "transmise", "refusee_perimetre"]


def test_requete_simple_http_forme_absolue_par_les_deux_sortes_de_proxy(px, cible, amont):
    entetes_de_chrome = "Connection: keep-alive\r\nProxy-Connection: keep-alive\r\nAccept: text/html\r\n"
    with relais_vers(px, amont, ("127.0.0.1",)) as relais:
        sans_entetes = get_absolu(port_de(relais), cible.url("/page?id=A"), delai_s=5)
        avec_entetes = get_absolu(port_de(relais), cible.url("/page?id=B"), entetes=entetes_de_chrome, delai_s=5)
        attendre_demandes(relais, 2)
        decisions = vues(relais)
    for reponse, identifiant in ((sans_entetes, "A"), (avec_entetes, "B")):
        statut, _, corps = lire_reponse(reponse)  # lue jusqu'à la fermeture : une connexion, une requête
        assert statut == 200 and f"/xhr?id={identifiant}".encode() in corps
        (requete,) = [r for r in cible.requetes if r["chemin"] == f"/page?id={identifiant}"]
        entetes = requete["entetes"]
        assert entetes["connection"] == "close", "le relais impose `Connection: close`"
        assert entetes["host"] == f"127.0.0.1:{cible.port}"
        assert "proxy-authorization" not in entetes and "bon-mdp" not in json.dumps(entetes)
    assert decisions == [("GET", "127.0.0.1", cible.port, "transmise")] * 2
    assert [c["port"] for c in amont.connexions] == [cible.port] * 2 and amont.refus == 0


def test_un_nom_inconnu_du_proxy_donne_502_et_rien_n_arrive_a_la_cible(px, cible, amont):
    with relais_vers(px, amont, ("*",)) as relais:
        statut, _, sock = ouvrir_tunnel(port_de(relais), "inconnu.test", cible.port)
        sock.close()
        attendre_demandes(relais, 1)
        decision = vues(relais)[0][3]
    assert statut == 502 and decision in (
        "refusee_amont",
        "echec_amont",
    )  # le proxy a répondu non ; lequel : non tranché
    time.sleep(0.3)
    assert cible.connexions_recues == [] and amont.connexions == []


def test_un_gros_corps_arrive_en_entier_dans_les_deux_formes(px, cible, amont):
    with relais_vers(px, amont, ("127.0.0.1",)) as relais:
        _, _, sock = ouvrir_tunnel(port_de(relais), "127.0.0.1", cible.port)
        with sock:
            par_tunnel = get_dans_le_tunnel(sock, "127.0.0.1", cible.port, "/gros?n=600000")
        par_get = get_absolu(port_de(relais), cible.url("/gros?n=600000"), delai_s=15)
    for reponse in (par_tunnel, par_get):
        statut, entetes, corps = lire_reponse(reponse)
        assert statut == 200 and len(corps) == 600000 == int(entetes["content-length"])
        assert corps == bytes(i % 251 for i in range(600000))


def test_une_demande_envoyee_en_morceaux_est_comprise(px, cible, amont):
    with relais_vers(px, amont, ("127.0.0.1",)) as relais:
        demande = f"CONNECT 127.0.0.1:{cible.port} HTTP/1.1\r\nHost: 127.0.0.1:{cible.port}\r\n\r\n".encode()
        with ouvrir_connexion(port_de(relais)) as sock:
            for debut in range(0, len(demande), 17):
                sock.sendall(demande[debut : debut + 17])
                time.sleep(0.02)
            reponse = sock.recv(4096)
            assert statut_de(reponse) == 200
            assert statut_de(get_dans_le_tunnel(sock, "127.0.0.1", cible.port, "/page?id=M")) == 200


# ── Une requête simple = une requête : en-tête + exactement `Content-Length` octets, rien de plus ──


@pytest.fixture
def cible2():
    with CibleDeTest() as c:
        yield c


def requete_simple(url: str, methode: str = "GET", corps: bytes | None = None, entetes: str = "") -> bytes:
    """Une requête en forme absolue ; `corps` (même vide) ajoute `Content-Length`."""
    longueur = f"Content-Length: {len(corps)}\r\n" if corps is not None else ""
    tete = f"{methode} {url} HTTP/1.1\r\nHost: {urlsplit(url).netloc}\r\n{entetes}{longueur}\r\n"
    return tete.encode("latin-1") + (corps or b"")


def nombre_de_requetes_vues_par_l_amont(amont) -> int:
    """Combien de lignes de requête (` HTTP/1.1`) ont atteint la cible du faux proxy : les octets, pas les décisions."""
    return amont.octets_du_client.count(b" HTTP/1.1\r\n")


@pytest.mark.parametrize("corps", [None, b"hello"], ids=["sans corps", "avec corps"])
@pytest.mark.parametrize("seconde", ["hors_perimetre", "autre_port_de_la_cible", "meme_hote_et_port"])
def test_une_seconde_requete_envoyee_sur_la_meme_connexion_n_atteint_jamais_l_amont(
    px, cible, cible2, amont, seconde, corps
):
    """Le relais ne compte pas sur `Connection: close` : un client qui désobéit et envoie deux requêtes d'un coup ne
    fait passer que la première. La seconde (hôte hors périmètre, autre port) est jetée, sans décision ni refus."""
    adresses = {
        "hors_perimetre": f"http://10.1.2.3:{cible.port}/page?id=B",
        "autre_port_de_la_cible": cible2.url("/page?id=B"),  # 127.0.0.1 est dans la liste : seul le port change
        "meme_hote_et_port": cible.url("/page?id=B"),
    }
    methode, chemin = ("POST", "/depot?id=A") if corps is not None else ("GET", "/page?id=A")
    with relais_vers(px, amont, ("127.0.0.1",)) as relais:
        premiere = requete_simple(cible.url(chemin), methode, corps)
        with ouvrir_connexion(port_de(relais), 5) as sock:
            sock.sendall(premiere + requete_simple(adresses[seconde]))  # d'un coup, sur une seule connexion
            reponse = lire_jusqu_a_fin(sock, 5)
        attendre_demandes(relais, 1)
        time.sleep(0.5)
        decisions = vues(relais)
    assert statut_de(reponse) == 200 and b"id=B" not in reponse
    assert decisions == [(methode, "127.0.0.1", cible.port, "transmise")], "la seconde n'a ni décision ni refus"
    assert nombre_de_requetes_vues_par_l_amont(amont) == 1, amont.octets_du_client
    assert amont.contacts == 1 and [c["port"] for c in amont.connexions] == [cible.port]
    assert [r["chemin"] for r in cible.requetes] == [chemin] and cible2.connexions_recues == []
    if corps is not None:
        assert cible.corps_recus == [(chemin, corps)] and amont.octets_du_client.endswith(b"\r\n\r\nhello")


def test_un_corps_content_length_arrive_en_entier_meme_gros_et_envoye_en_morceaux(px, cible, amont):
    corps = bytes(i % 251 for i in range(600_000))
    tete = requete_simple(cible.url("/depot?id=G"), "POST", corps)[: -len(corps)]
    with relais_vers(px, amont, ("127.0.0.1",)) as relais, ouvrir_connexion(port_de(relais), 20) as sock:
        sock.sendall(tete + corps[:100])  # l'en-tête et le début du corps, d'un coup
        for debut in range(100, len(corps), 70_000):
            sock.sendall(corps[debut : debut + 70_000])
            time.sleep(0.01)
        reponse = lire_jusqu_a_fin(sock, 20)
    statut, _, resume = lire_reponse(reponse)
    assert statut == 200 and resume == f"recu={len(corps)} sha256={hashlib.sha256(corps).hexdigest()}".encode()
    assert cible.corps_recus == [("/depot?id=G", corps)]
    assert amont.octets_du_client.endswith(corps) and nombre_de_requetes_vues_par_l_amont(amont) == 1


@pytest.mark.parametrize(
    "entetes",
    [
        "Transfer-Encoding: chunked\r\n",
        "transfer-encoding: gzip, chunked\r\n",
        "Transfer-Encoding: chunked\r\nContent-Length: 5\r\n",
    ],
    ids=["chunked", "gzip puis chunked, casse différente", "avec Content-Length"],
)
def test_un_corps_decoupe_est_refuse_en_501_et_rien_ne_part_vers_l_amont(px, cible, amont, entetes):
    demande = requete_simple(cible.url("/depot?id=E"), "POST", entetes=entetes) + b"5\r\nhello\r\n0\r\n\r\n"
    with relais_vers(px, amont, ("127.0.0.1",)) as relais:
        reponse = echanger(port_de(relais), demande, 5)
        decisions = vues(relais)
    statut, _, texte = lire_reponse(reponse)
    assert statut == 501 and b"Transfer-Encoding" in texte, "un texte clair : ce n'est pas pris en charge"
    assert amont.contacts == 0 and amont.connexions == [] and amont.octets_du_client == b""
    assert decisions == [] and cible.connexions_recues == []


@pytest.mark.parametrize(
    "entetes",
    [
        "Content-Length: 5\r\nContent-Length: 5\r\n",
        "Content-Length: 5\r\ncontent-length: 7\r\n",
        "Content-Length: 5, 5\r\n",
        "Content-Length: abc\r\n",
        "Content-Length: -1\r\n",
        "Content-Length: 1e3\r\n",
        "Content-Length: \r\n",
    ],
    ids=["deux identiques", "deux différents", "liste", "texte", "négatif", "exposant", "vide"],
)
def test_un_content_length_invalide_ou_multiple_est_refuse_en_400_et_rien_ne_part_vers_l_amont(
    px, cible, amont, entetes
):
    demande = requete_simple(cible.url("/depot?id=F"), "POST", entetes=entetes) + b"hello"
    with relais_vers(px, amont, ("127.0.0.1",)) as relais:
        reponse = echanger(port_de(relais), demande, 5)
        decisions = vues(relais)
    assert statut_de(reponse) == 400
    assert amont.contacts == 0 and amont.connexions == [] and amont.octets_du_client == b""
    assert decisions == [] and cible.connexions_recues == []


def test_un_tunnel_connect_n_est_pas_limite_a_une_requete(px, cible, amont):
    """La décision d'un `CONNECT` se prend par tunnel : plusieurs requêtes y passent, et le relais ne les lit pas."""
    with relais_vers(px, amont, ("127.0.0.1",)) as relais:
        statut, _, sock = ouvrir_tunnel(port_de(relais), "127.0.0.1", cible.port)
        with sock:
            premiere = b"GET /page?id=U1 HTTP/1.1\r\nHost: x\r\n\r\n"
            sock.sendall(premiere + b"GET /page?id=U2 HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
            reponse = lire_jusqu_a_fin(sock, 5)
    assert statut == 200 and reponse.count(b"HTTP/1.0 200") + reponse.count(b"HTTP/1.1 200") == 2
    assert [r["chemin"] for r in cible.requetes] == ["/page?id=U1", "/page?id=U2"]


@pytest.mark.parametrize(
    "requete",
    [
        b"GET /page HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n",  # forme d'origine : le relais n'est pas un serveur
        b"GARBAGE\r\n\r\n",
        b"CONNECT 127.0.0.1 HTTP/1.1\r\n\r\n",  # pas de port
        b"CONNECT 127.0.0.1:0 HTTP/1.1\r\n\r\n",
        b"CONNECT 127.0.0.1:70000 HTTP/1.1\r\n\r\n",
        b"GET ftp://127.0.0.1:21/x HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n",  # http et https seulement, même en illimité
        b"GET file:///etc/hosts HTTP/1.1\r\nHost: x\r\n\r\n",
    ],
    ids=["forme d'origine", "n'importe quoi", "CONNECT sans port", "port 0", "port 70000", "ftp", "file"],
)
def test_une_demande_invalide_n_est_pas_transmise(px, amont, requete):
    with relais_vers(px, amont, ("*",)) as relais:
        with ouvrir_connexion(port_de(relais), 5) as sock:
            sock.sendall(requete)
            tete, _ = lire_tete(sock)  # un délai dépassé ici : le relais attend la suite d'une demande invalide
    assert tete == b"" or statut_de(tete) >= 400, tete[:80]  # une erreur franche, ou la fermeture sans réponse
    assert amont.contacts == 0 and amont.connexions == [], "rien ne part vers le proxy"


def test_plusieurs_tunnels_en_meme_temps(px, cible, amont):
    resultats: list[tuple[int, int]] = []
    erreurs: list[BaseException] = []

    def un(i: int) -> None:
        try:
            statut, _, sock = ouvrir_tunnel(port_de(relais), "127.0.0.1", cible.port)
            with sock:
                reponse = get_dans_le_tunnel(sock, "127.0.0.1", cible.port, f"/page?id=C{i}")
            resultats.append((statut, statut_de(reponse)))
        except BaseException as exc:  # noqa: BLE001 — rapporté plus bas
            erreurs.append(exc)

    with relais_vers(px, amont, ("127.0.0.1",)) as relais:
        fils = [threading.Thread(target=un, args=(i,)) for i in range(8)]
        for fil in fils:
            fil.start()
        for fil in fils:
            fil.join(timeout=20)
    assert not erreurs, erreurs
    assert resultats == [(200, 200)] * 8
    assert len({c["port_source"] for c in amont.connexions}) == 8


def test_adresse_demarrer_et_contexte(px, amont):
    relais = relais_vers(px, amont, ("127.0.0.1",))
    port = relais.demarrer()
    assert isinstance(port, int) and relais.adresse == f"http://127.0.0.1:{port}"
    relais.arreter()
    with relais_vers(px, amont, ("127.0.0.1",)) as autre:
        assert autre.adresse.startswith("http://127.0.0.1:") and port_de(autre) > 0
        ouvrir_connexion(port_de(autre)).close()
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port_de(autre)), timeout=1)


def test_le_relais_s_arrete_sans_laisser_de_fil_vivant_et_ferme_son_port(px, cible, amont):
    avant = set(threading.enumerate())  # les aides sont déjà démarrées
    relais = relais_vers(px, amont, ("127.0.0.1",))
    port = relais.demarrer()
    _, _, tunnel = ouvrir_tunnel(port, "127.0.0.1", cible.port)  # un tunnel ouvert, laissé ouvert
    muet = ouvrir_connexion(port)  # et une connexion qui ne dit rien
    time.sleep(0.3)
    relais.arreter()

    def vivants() -> list[threading.Thread]:
        return [fil for fil in set(threading.enumerate()) - avant if fil.is_alive()]

    try:
        # Les deux connexions des clients sont ENCORE ouvertes : c'est `arreter` qui doit tout fermer, pas les clients.
        assert attendre(lambda: not vivants(), 5), [fil.name for fil in vivants()]
        with pytest.raises(OSError):
            socket.create_connection(("127.0.0.1", port), timeout=1)
    finally:
        tunnel.close()
        muet.close()
