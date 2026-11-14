"""Quatrième relecture indépendante du site public, avant son annonce (14/11/2026).

Chaque test montre un défaut constaté : il échoue sur le code relu (branche `public-relecture-4`, commit c51c3d9) et
passera une fois le défaut corrigé. Il vérifie la propriété promise, pas une correction particulière. Les courses
sont rejouées dans le processus (client ASGI, `asyncio.gather`), sans port ni attente : elles ont aussi été
observées contre un vrai serveur uvicorn (corps des requêtes envoyé après leurs en-têtes).
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from parsel import Selector
from test_public import AUTRE_IP, CONTACT, HOTE, IP, ORIGINE, champs_du_formulaire, commencer, fabriquer, ouvrir

from shadowlab.config import ReglagesPublics
from shadowlab.public import Limites, creer_app_publique
from shadowlab.public.pages import DONNEES_RELEVEES, DONNEES_RELEVEES_EN
from shadowlab.public.social import DOSSIER_PHOTOS
from shadowlab.public.textes import LANGUES, T

RACINE = Path(__file__).parents[1]


@pytest.fixture
def reglages_publics(tmp_path) -> ReglagesPublics:
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


def client_asgi(reglages: ReglagesPublics, limites: Limites | None = None) -> httpx.AsyncClient:
    app = creer_app_publique(reglages, limites or Limites())
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGINE)


async def csrf_de_l_accueil(c: httpx.AsyncClient) -> str:
    jeton = Selector((await c.get("/")).text).css('input[name="csrf"]::attr(value)').get()
    assert jeton
    return jeton


async def commencer_asgi(c: httpx.AsyncClient, adresse: str = IP) -> str:
    """Ouvre une session et renvoie son jeton (lu dans une page vitrine)."""
    envoi = {"consentement": "oui", "csrf": await csrf_de_l_accueil(c)}
    r = await c.post("/session/commencer", data=envoi, headers={"Origin": ORIGINE, "X-Forwarded-For": adresse})
    assert r.status_code == 303, r.text
    jeton = Selector((await c.get("/lab/vitrine")).text).css('meta[name="sl-session"]::attr(content)').get()
    assert jeton
    return jeton


def compte_des_terminees(reglages: ReglagesPublics) -> int:
    cx = ouvrir(reglages)
    try:
        return int(cx.execute("SELECT COALESCE(SUM(terminees), 0) FROM frequentation").fetchone()[0])
    finally:
        cx.close()


# --- Compteur de l'accueil -----------------------------------------------------------------------


def test_terminer_en_rafale_ne_compte_qu_une_session(reglages_publics):
    """Une seule session, vingt « Terminer » simultanés (même cookie, même jeton anti-CSRF) : le compteur public de
    l'accueil (« N sessions enregistrées à ce jour ») ne doit prendre qu'une unité.

    Constaté : la garde lit la session (encore en cours) avant d'attendre le corps du formulaire ; chaque requête
    appelle ensuite `compter("terminees")` sans vérifier que `clore_session` a bien clos quelque chose
    (`public/app.py`, `terminer`). Contre un vrai uvicorn, 300 requêtes au corps envoyé après les en-têtes ont
    affiché « 300 sessions enregistrées à ce jour ». Un participant, ou un script, gonfle le compteur à volonté."""

    async def scenario() -> str:
        async with client_asgi(reglages_publics) as c:
            await commencer_asgi(c)
            page = (await c.get("/lab/vitrine")).text
            champs = champs_du_formulaire(page, "/session/terminer")
            rafale = [c.post("/session/terminer", data=champs, headers={"Origin": ORIGINE}) for _ in range(20)]
            reponses = await asyncio.gather(*rafale)
            assert all(r.status_code in (200, 303) for r in reponses)
            return (await c.get("/fr")).text

    accueil = asyncio.run(scenario())
    assert compte_des_terminees(reglages_publics) == 1
    compteur = Selector(accueil).css(".accueil-compteur .compteur-nombre::text").get()
    assert compteur == "1", f"l'accueil affiche {compteur} sessions pour une seule session terminée"


def test_double_clic_sur_commencer_n_ouvre_qu_une_session(reglages_publics):
    """Deux « Commencer » simultanés du même navigateur (double clic) : une seule session. Constaté : deux sessions
    (la garde lit l'absence de session avant d'attendre le corps ; `request.state.session` n'est pas relu ensuite).
    La première, orpheline, reste « commencée » sans jamais être terminée et use le quota du jour et de l'adresse.
    `test_double_clic_ne_cree_pas_deux_sessions` (test_public.py) n'essaie que deux envois successifs."""

    async def scenario() -> None:
        async with client_asgi(reglages_publics) as c:
            envoi = {"consentement": "oui", "csrf": await csrf_de_l_accueil(c)}
            entetes = {"Origin": ORIGINE, "X-Forwarded-For": IP}
            reponses = await asyncio.gather(
                *(c.post("/session/commencer", data=envoi, headers=entetes) for _ in range(2))
            )
            assert [r.status_code for r in reponses] == [303, 303]

    asyncio.run(scenario())
    cx = ouvrir(reglages_publics)
    try:
        assert cx.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
    finally:
        cx.close()


# --- Limite par adresse --------------------------------------------------------------------------


def test_limite_par_adresse_lit_la_derniere_ligne_de_l_en_tete(reglages_publics):
    """`adresse_de` promet la « dernière valeur de l'en-tête du mandataire » (docs/site-public.md : « dernière valeur
    lue »). Un mandataire qui AJOUTE sa propre ligne `X-Forwarded-For` au lieu de compléter celle du client met
    l'adresse vraie sur la dernière ligne ; la première est celle que le visiteur a forgée.

    Constaté : `request.headers.get(...)` rend la PREMIÈRE ligne ; un visiteur qui change sa ligne forgée à chaque
    essai ouvre 8 sessions sur 8 depuis la même adresse, au lieu de 6 par heure. Sans effet avec les mandataires
    décrits (Caddy et nginx remplacent l'en-tête, Cloudflare le complète sur une ligne) ; à durcir quand même."""
    app = creer_app_publique(reglages_publics, Limites())
    codes = []
    for i in range(7):
        with TestClient(app, base_url=ORIGINE) as client:
            csrf = Selector(client.get("/").text).css('input[name="csrf"]::attr(value)').get()
            entetes = [("Origin", ORIGINE), ("X-Forwarded-For", f"10.0.0.{i}"), ("X-Forwarded-For", IP)]
            r = client.post(
                "/session/commencer",
                data={"consentement": "oui", "csrf": csrf},
                headers=entetes,
                follow_redirects=False,
            )
            codes.append(r.status_code)
    assert codes == [303] * 6 + [429], codes


# --- Suppression et base pleine ------------------------------------------------------------------


def test_envoi_en_vol_pendant_la_suppression_ne_laisse_rien(reglages_publics):
    """« Supprimer ma session » efface aussitôt toutes les données de la session (notice, « Vos droits »). Un envoi
    de l'observateur ou du relevé encore en vol (corps pas encore reçu, réseau lent, onglet qui passe à
    l'arrière-plan) ne doit rien écrire après la suppression.

    Constaté : la garde valide la session, `collecte` attend le corps, la suppression passe, puis `collecte` écrit
    une ligne `observations_js` portant le jeton d'une session qui n'existe plus. La purge ne la retrouve jamais
    (`donnees.purger` part de `runs`) : elle reste au-delà des 90 jours. Observé aussi contre un vrai uvicorn."""

    async def scenario() -> tuple[str, int]:
        async with client_asgi(reglages_publics) as c:
            jeton = await commencer_asgi(c)
            champs = champs_du_formulaire((await c.get("/session")).text, "/session/supprimer")
            corps_attendu, liberer = asyncio.Event(), asyncio.Event()

            async def corps_lent():
                corps_attendu.set()  # la garde est passée, `collecte` lit le corps
                await liberer.wait()
                yield json.dumps({"kind": "empreinte", "page": "/lab/vitrine", "payload": {"essai": "en vol"}}).encode()

            envoi = asyncio.create_task(
                c.post(f"/lab/collecte?sl={jeton}", content=corps_lent(), headers={"Content-Type": "application/json"})
            )
            await asyncio.wait_for(corps_attendu.wait(), timeout=10)
            suppression = await c.post("/session/supprimer", data=champs, headers={"Origin": ORIGINE})
            assert suppression.status_code == 200
            liberer.set()
            return jeton, (await asyncio.wait_for(envoi, timeout=10)).status_code

    jeton, _ = asyncio.run(scenario())
    cx = ouvrir(reglages_publics)
    try:
        restes = {
            table: cx.execute(f"SELECT COUNT(*) FROM {table} WHERE session_token = ?", (jeton,)).fetchone()[0]
            for table in ("runs", "observations_js", "observations_http")
        }
    finally:
        cx.close()
    assert restes == {"runs": 0, "observations_js": 0, "observations_http": 0}


def test_base_pleine_rouvre_quand_les_sessions_sont_effacees(reglages_publics):
    """Base au plafond, puis la session qui la remplissait est supprimée : l'étude doit rouvrir. La documentation
    le promet (« plus aucune session ne s'ouvre (503) jusqu'à la purge […] ou à une suppression à la main »).

    Constaté : `plein()` compare la taille du FICHIER au plafond ; une suppression (ou la purge) libère des pages
    sans réduire le fichier (ni VACUUM, ni auto_vacuum). Toutes les lignes effacées, la base reste « pleine » et
    « Commencer » répond 503 pour toujours : quelques jours d'abus (sessions remplies à leurs quotas) ferment
    l'étude jusqu'à une intervention à la main que rien ne documente."""
    limites = replace(Limites(), taille_max_base=400_000)
    with TestClient(creer_app_publique(reglages_publics, limites), base_url=ORIGINE) as client:
        jeton = commencer(client)
        gros = json.dumps({"kind": "empreinte", "page": "/lab/vitrine", "payload": {"remplissage": "a" * 60_000}})
        for _ in range(50):
            code = client.post(f"/lab/collecte?sl={jeton}", content=gros, headers={"Content-Type": "application/json"})
            if code.status_code != 204:
                break
        assert code.status_code == 503, "la base devait atteindre son plafond"
        champs = champs_du_formulaire(client.get("/session").text, "/session/supprimer")
        assert client.post("/session/supprimer", data=champs, headers={"Origin": ORIGINE}).status_code == 200
    cx = ouvrir(reglages_publics)
    try:
        assert cx.execute("SELECT COUNT(*) FROM observations_js").fetchone()[0] == 0  # tout est effacé
    finally:
        cx.close()
    with TestClient(creer_app_publique(reglages_publics, limites), base_url=ORIGINE) as autre:
        assert commencer_ou_code(autre, AUTRE_IP) == 303


def commencer_ou_code(client: TestClient, adresse: str) -> int:
    page = client.get("/").text
    csrf = Selector(page).css('input[name="csrf"]::attr(value)').get()
    assert csrf
    r = client.post(
        "/session/commencer",
        data={"consentement": "oui", "csrf": csrf},
        headers={"Origin": ORIGINE, "X-Forwarded-For": adresse},
        follow_redirects=False,
    )
    return r.status_code


# --- Collecte : entrée qui fait tomber la requête ------------------------------------------------


@pytest.mark.parametrize(
    "corps",
    [
        b'{"kind":"empreinte","page":"/lab/vitrine","payload":{"a":"\\ud800"}}',
        b'{"kind":"comportement","page":"/lab/vitrine\\udfff","payload":{}}',
    ],
    ids=["demi-paire-dans-la-charge", "demi-paire-dans-la-page"],
)
def test_collecte_demi_paire_utf16_refusee_proprement(reglages_publics, corps):
    """Une demi-paire UTF-16 (`\\ud800`), JSON valide, dans un envoi : 400 (ou 204), avec les en-têtes de sécurité.

    Constaté : `json.dumps(..., ensure_ascii=False)` garde le caractère, `texte.encode()` lève UnicodeEncodeError,
    non rattrapée (`public/app.py`, `collecte`) : 500 sans politique de sécurité du contenu, la connexion coupée,
    et une trace d'erreur d'une soixantaine de lignes sur la sortie d'erreur d'uvicorn à chaque envoi (observé)."""
    app = creer_app_publique(reglages_publics, Limites())
    with TestClient(app, base_url=ORIGINE, raise_server_exceptions=False) as client:
        jeton = commencer(client)
        r = client.post(f"/lab/collecte?sl={jeton}", content=corps, headers={"Content-Type": "application/json"})
    assert r.status_code < 500, r.text
    assert "content-security-policy" in r.headers


# --- Licences des photos ---------------------------------------------------------------------------


@pytest.mark.parametrize("chemin", ["/fr", "/en", "/"])
def test_accueil_credite_les_photos_qu_il_montre(reglages_publics, chemin):
    """L'accueil de l'étude montre huit photos du manifeste, dont cinq sous CC BY ou CC BY-SA (sauvages-06,
    fleurs-02, sauvages-01, mer-08, ciel-04) : il doit donner leur crédit, ou au moins un lien vers la page des
    crédits. Constaté : ni auteur, ni licence, ni lien vers /lab/social/credits (le pied des pages de l'étude n'en
    a pas). Hors session seulement : pendant une session, l'accueil ne montre aucune photo."""
    with fabriquer(reglages_publics) as client:
        page = client.get(chemin).text
    photos = Selector(page).css('img[src^="/lab/social/photos/"]::attr(src)').getall()
    assert photos, "l'accueil ne montre plus de photo : test sans objet"
    liens = Selector(page).css("a::attr(href)").getall()
    assert any(lien.startswith("/lab/social/credits") for lien in liens), photos


def test_manifeste_credite_le_photographe_d_une_licence_creative_commons():
    """Une licence Creative Commons (créées en 2002) ne peut venir que d'un auteur vivant après 2002 : l'auteur
    crédité d'une photo sous CC doit être celui qui l'a placée sous cette licence (le photographe), pas l'artiste
    de l'œuvre photographiée.

    Constaté (cohérence interne, sans Internet) : `objets-03` (plafond de la salle des Géants, Palazzo Te) crédite
    « Giulio Romano (1499–1546) » sous CC BY-SA 4.0 ; le photographe, titulaire de la licence, n'est pas nommé.
    Le bon nom est sur la page d'origine de la photo (Wikimedia Commons), non consultée ici."""
    entrees = json.loads((DOSSIER_PHOTOS / "manifeste.json").read_text(encoding="utf-8"))["photos"]
    fautifs = []
    for e in entrees:
        vie = re.search(r"\((\d{3,4})\s*[–-]\s*(\d{3,4})\)", e["auteur"])
        if e["licence"].startswith("CC BY") and vie and int(vie.group(2)) < 2002:
            fautifs.append((e["id"], e["auteur"], e["licence"]))
    assert not fautifs


# --- Vérité de la notice ---------------------------------------------------------------------------


def test_notice_ne_dit_pas_qu_aucun_service_de_cloudflare_n_est_utilise():
    """La notice dit (« Ce qui n'est pas relevé ») : « La page ne fait appel à aucun autre site : […] ni service de
    Google ou de Cloudflare. » Or la seule mise en ligne outillée (`scripts/site-public-tunnel.sh`) et l'option A
    de docs/site-public.md font passer tout le trafic par Cloudflare : l'adresse même du site finit en
    `trycloudflare.com`, et Cloudflare voit adresse IP, pages et envois. Le navigateur ne charge rien d'un autre
    hôte (vérifié dans Chromium) : la phrase est exacte à la lettre, mais trompeuse, et la phrase « transit » ne
    nomme pas ce service. Dans le texte de consentement, c'est la première chose qu'un lecteur relèvera."""
    script = (RACINE / "scripts" / "site-public-tunnel.sh").read_text(encoding="utf-8")
    assert "cloudflared tunnel" in script  # le déploiement prévu passe par Cloudflare
    for langue in LANGUES:
        assert "Cloudflare" not in T[langue]["non_releve"], langue


def test_notice_ne_dit_pas_qu_aucun_detecteur_ne_tourne():
    """« Pourquoi » dit « pendant la visite, aucun détecteur ne tourne » (« no detector runs »), alors que la même
    notice décrit BotD, « une bibliothèque libre qui dit robot ou non », qui « tourne dans votre navigateur », et
    des contrôles « qui servent à repérer les robots ». La promesse vraie est qu'aucune décision n'est prise."""
    assert "tourne dans votre navigateur" in dict(DONNEES_RELEVEES)["botd"]
    assert "runs in your browser" in dict(DONNEES_RELEVEES_EN)["botd"]
    assert "aucun détecteur ne tourne" not in T["fr"]["pourquoi"]
    assert "no detector runs" not in T["en"]["pourquoi"]


# --- Exploitation ----------------------------------------------------------------------------------


def test_script_du_tunnel_impose_le_mode_https():
    """Le script de mise en ligne impose l'hôte, l'en-tête d'adresse et le port, mais pas SHADOWLAB_PUBLIC_HTTPS :
    une valeur `0` restée dans le shell ou dans `.env` (l'essai local de docs/site-public.md la pose) mettrait le
    site en ligne sans `Secure`, sans préfixe `__Host-` et sans HSTS."""
    script = (RACINE / "scripts" / "site-public-tunnel.sh").read_text(encoding="utf-8")
    impose = r"""^\s*(?:export\s+)?SHADOWLAB_PUBLIC_HTTPS=["']?1["']?(?:\s|$)"""
    assert re.search(impose, script, re.M), "SHADOWLAB_PUBLIC_HTTPS=1 absent"


def test_documentation_du_tunnel_rapide_dit_que_ma_session_ne_survit_pas_a_une_relance():
    """La notice promet « Ma session » (et son bouton « Supprimer ») « dans ce navigateur jusqu'à l'effacement
    automatique » (90 jours), par le cookie `slp-droits`, lié à l'hôte. Avec le tunnel rapide, l'adresse change à
    chaque relance : le cookie ne sert plus, l'ancienne adresse ne répond plus, et le formulaire de contact n'est
    plus joignable à l'adresse connue du participant. docs/site-public.md (« Limites de cette voie ») ne le dit pas :
    le propriétaire doit le savoir avant d'annoncer le lien."""
    doc = (RACINE / "docs" / "site-public.md").read_text(encoding="utf-8")
    debut = doc.index("Limites de cette voie")
    section = doc[debut : doc.index("## Réglages", debut)]
    assert "Ma session" in section or "slp-droits" in section
