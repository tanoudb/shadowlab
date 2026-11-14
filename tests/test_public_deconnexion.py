"""Un client qui coupe la connexion pendant l'envoi du corps d'une requête (D-77, ajout du 14/11/2026).

Constaté contre un vrai uvicorn : l'application laissait remonter `starlette.requests.ClientDisconnect`, et uvicorn
écrivait une trace d'erreur complète à chaque fois (onglet fermé, double clic, réseau mobile, script qui ouvre des
requêtes et les abandonne). Le journal promis (erreurs utiles seulement) se remplissait de bruit.

Les essais appellent l'application ASGI directement, avec un `receive` qui rend ce que rend uvicorn quand le client
coupe : `http.disconnect`, éventuellement après un début de corps. Propriété vérifiée, pour chaque point d'entrée
qui attend un corps : aucune exception ne remonte, rien n'est écrit en base (ni session, ni compteur, ni envoi), le
journal reste vide et aucun quota par adresse ou par jour n'est entamé.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from test_public import (
    IP,
    ORIGINE,
    champs_du_formulaire,
    collecter,
    commencer,
    contenu_de_la_base,
    jeton_csrf,
    ouvrir,
    terminer,
)

from shadowlab.config import ReglagesPublics
from shadowlab.public import Limites, creer_app_publique
from shadowlab.public import messages as boite

# Un quota d'un seul passage partout : une requête abandonnée qui en userait un ferait refuser la suivante.
LIMITES = replace(
    Limites(),
    sessions_par_adresse=1,
    sessions_par_jour=1,
    messages_par_adresse=1,
    messages_par_adresse_jour=1,
    messages_par_jour=1,
)


@pytest.fixture
def reglages_publics(tmp_path) -> ReglagesPublics:
    from test_public import CONTACT, HOTE

    return ReglagesPublics(
        hotes=(HOTE,),
        contact=CONTACT,
        conservation_jours=90,
        https=True,
        port=8771,
        base_donnees=tmp_path / "public" / "public.sqlite3",
        entete_ip="X-Forwarded-For",
        vitrine_graine=20261111,
        vitrine_taille=45,
    )


@pytest.fixture
def client(reglages_publics):
    with TestClient(creer_app_publique(reglages_publics, LIMITES), base_url=ORIGINE) as c:
        yield c


def abandonner(client: TestClient, chemin: str, entetes: dict[str, str], debut: bytes = b"") -> list[dict]:
    """POST dont le client coupe pendant l'envoi du corps. Annonce 4 000 octets, en livre `debut` (rien par défaut),
    puis `http.disconnect`, comme uvicorn. Renvoie ce que l'application a envoyé ; toute exception remonte ici."""
    chemin, _, requete = chemin.partition("?")
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": chemin,
        "raw_path": chemin.encode(),
        "query_string": requete.encode(),
        "root_path": "",
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 8771),
        "headers": [(k.lower().encode(), v.encode()) for k, v in {"content-length": "4000", **entetes}.items()],
        "state": {},
    }
    evenements = [{"type": "http.request", "body": debut, "more_body": True}] if debut else []
    evenements.append({"type": "http.disconnect"})
    envoyes: list[dict] = []

    async def receive() -> dict:
        if evenements:
            return evenements.pop(0)
        await asyncio.sleep(3600)  # uvicorn ne rend plus rien après la coupure
        raise AssertionError("receive appelé après la déconnexion")

    async def send(message: dict) -> None:
        envoyes.append(message)

    async def lancer() -> None:
        await asyncio.wait_for(client.app(scope, receive, send), timeout=5)

    asyncio.run(lancer())
    return envoyes


def cookies_de(client: TestClient) -> str:
    return "; ".join(f"{c.name}={c.value}" for c in client.cookies.jar)


FORMULAIRE = b"consentement=oui&csrf="


def entetes_de_formulaire(client: TestClient, **en_plus: str) -> dict[str, str]:
    return {
        "host": "vitrine.test",
        "origin": ORIGINE,
        "content-type": "application/x-www-form-urlencoded",
        "x-forwarded-for": IP,
        "cookie": cookies_de(client),
        **en_plus,
    }


def table(reglages: ReglagesPublics, nom: str) -> list[tuple]:
    cx = ouvrir(reglages)
    try:
        return [tuple(ligne) for ligne in cx.execute(f"SELECT * FROM {nom}")]
    finally:
        cx.close()


def base_avant_apres(reglages: ReglagesPublics, action: Callable[[], object]) -> tuple[str, str]:
    avant = contenu_de_la_base(reglages)
    action()
    return avant, contenu_de_la_base(reglages)


@pytest.fixture(autouse=True)
def journal_complet(caplog):
    caplog.set_level(logging.DEBUG, logger="shadowlab.public")


@pytest.mark.parametrize("debut", [b"", b"consentement=ou"], ids=["rien_recu", "corps_commence"])
def test_commencer_abandonne_ne_compte_ni_ne_cree_rien(client, reglages_publics, caplog, debut):
    """`/session/commencer` : ni session, ni « commencées », ni quota par adresse ou par jour entamé."""
    csrf = jeton_csrf(client)  # l'accueil a bien été chargé et compté : c'est la base de comparaison
    entetes = entetes_de_formulaire(client)
    avant, apres = base_avant_apres(
        reglages_publics, lambda: abandonner(client, "/session/commencer", entetes, debut + csrf.encode())
    )
    assert apres == avant, "une requête abandonnée n'écrit rien en base"
    assert caplog.records == [], "et ne laisse aucune ligne au journal"
    # Aucun quota entamé (un passage par heure et par jour) : la vraie ouverture qui suit réussit.
    assert commencer(client, IP)


@pytest.mark.parametrize("debut", [b"", b"csrf=abc"], ids=["rien_recu", "corps_commence"])
def test_terminer_abandonne_ne_compte_aucune_session_terminee(client, reglages_publics, caplog, debut):
    jeton = commencer(client)
    champs = champs_du_formulaire(client.get("/lab/vitrine").text, "/session/terminer")
    caplog.clear()
    entetes = entetes_de_formulaire(client)
    avant, apres = base_avant_apres(
        reglages_publics,
        lambda: abandonner(client, "/session/terminer", entetes, debut + urlencode(champs).encode()),
    )
    # Une requête abandonnée sur /session/ n'est pas notée (seul /lab/ l'est) : la base ne bouge pas du tout.
    assert apres == avant
    assert caplog.records == []
    # La session est toujours ouverte et se termine normalement ensuite, une seule fois.
    assert terminer(client).status_code == 200
    assert [ligne[0] for ligne in table(reglages_publics, "frequentation")] != []
    assert jeton


@pytest.mark.parametrize("debut", [b"", b"csrf=abc"], ids=["rien_recu", "corps_commence"])
def test_supprimer_abandonne_n_efface_rien(client, reglages_publics, caplog, debut):
    commencer(client)
    terminer(client)
    page = client.get("/session").text
    champs = champs_du_formulaire(page, "/session/supprimer")
    caplog.clear()
    entetes = entetes_de_formulaire(client)
    avant, apres = base_avant_apres(
        reglages_publics,
        lambda: abandonner(client, "/session/supprimer", entetes, debut + urlencode(champs).encode()),
    )
    assert apres == avant, "la session n'est pas effacée par une requête qui n'est jamais arrivée au bout"
    assert caplog.records == []
    assert client.post("/session/supprimer", data=champs, headers={"Origin": ORIGINE}).status_code == 200


@pytest.mark.parametrize("debut", [b"", b"message=bonj"], ids=["rien_recu", "corps_commence"])
def test_contact_abandonne_ne_depose_rien_et_n_use_aucun_quota(client, reglages_publics, caplog, debut):
    csrf = jeton_csrf(client)
    caplog.clear()
    entetes = entetes_de_formulaire(client)
    avant, apres = base_avant_apres(
        reglages_publics, lambda: abandonner(client, "/contact", entetes, debut + csrf.encode())
    )
    assert apres == avant
    cx = boite.connexion(boite.chemin(reglages_publics.base_donnees))
    try:
        assert boite.nombre(cx) == 0
    finally:
        cx.close()
    assert caplog.records == []
    # Un message par heure et par jour, un par jour au total : la vraie requête qui suit passe.
    r = client.post(
        "/contact",
        data={"message": "Bonjour", "csrf": csrf},
        headers={"Origin": ORIGINE, "X-Forwarded-For": IP},
        follow_redirects=False,
    )
    assert r.status_code == 303, "le quota n'a pas été entamé par la requête abandonnée"


@pytest.mark.parametrize("debut", [b"", b'{"kind": "empreinte", "pa'], ids=["rien_recu", "corps_commence"])
def test_collecte_abandonnee_n_ecrit_aucun_releve_et_n_use_aucun_quota(client, reglages_publics, caplog, debut):
    jeton = commencer(client)
    caplog.clear()
    entetes = {
        "host": "vitrine.test",
        "content-type": "application/json",
        "x-forwarded-for": IP,
        "cookie": cookies_de(client),
    }
    js_avant = table(reglages_publics, "observations_js")
    sessions_avant = table(reglages_publics, "runs")
    frequentation_avant = table(reglages_publics, "frequentation")
    abandonner(client, f"/lab/collecte?sl={jeton}", entetes, debut)
    assert table(reglages_publics, "observations_js") == js_avant, "aucun relevé écrit"
    assert table(reglages_publics, "runs") == sessions_avant, "aucun envoi compté dans la session"
    assert table(reglages_publics, "frequentation") == frequentation_avant
    assert caplog.records == []
    assert collecter(client, jeton).status_code == 204, "la session et ses quotas sont intacts"
