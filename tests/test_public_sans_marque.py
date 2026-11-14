"""Le site public ne cite jamais le nom du projet ni celui du laboratoire (demande d'Ethan, 14/11/2026 :
« tu mentionnes noezia, faut pas du tout »). Ce fichier couvre les textes des deux langues et les feuilles de style
et scripts propres au site public."""

import re
from collections import deque
from pathlib import Path

import pytest
import test_public
from fastapi.testclient import TestClient
from parsel import Selector
from test_public import commencer, fabriquer

from shadowlab.public import app as application
from shadowlab.public import textes

reglages_publics = test_public.reglages_publics  # mêmes réglages et même application que les autres tests publics
client = test_public.client
NOMS_INTERDITS = ("noezia", "shadowlab", "shadow lab")
STATIQUES = Path(textes.__file__).parent / "static"


def _noms_trouves(texte: str) -> list[str]:
    bas = texte.lower()
    return [nom for nom in NOMS_INTERDITS if nom in bas]


@pytest.mark.parametrize("langue", sorted(textes.T))
def test_aucun_texte_ne_cite_le_projet(langue: str) -> None:
    fautifs = {cle: _noms_trouves(valeur) for cle, valeur in textes.T[langue].items() if _noms_trouves(valeur)}
    assert not fautifs, f"textes « {langue} » qui citent le projet : {fautifs}"


@pytest.mark.parametrize("fichier", sorted(p.name for p in STATIQUES.glob("*.*") if p.suffix in {".css", ".js"}))
def test_aucun_fichier_statique_du_site_public_ne_cite_le_projet(fichier: str) -> None:
    contenu = (STATIQUES / fichier).read_text(encoding="utf-8")
    assert not _noms_trouves(contenu), f"{fichier} cite le projet : {_noms_trouves(contenu)}"


# === Garde globale : tout ce que le site public sert, hors session et pendant une session ================

LABO = Path(textes.__file__).parents[1] / "site" / "static" / "observateur.js"
ACCEPT = {"fr": "fr-FR,fr;q=0.9", "en": "en-US,en;q=0.9"}
PAGES_FIXES = [
    "/", "/fr", "/en", "/fr/information", "/en/information", "/information", "/session", "/contact",
    "/contact/envoye", "/contact/style.css", "/robots.txt", "/favicon.ico", "/lab/vitrine", "/lab/vitrine/annonces",
    "/lab/social/fil", "/lab/social/explorer", "/lab/social/credits", "/lab/inexistante",
]  # fmt: skip


def _fichiers_statiques() -> list[str]:
    return [f"/lab/static/{n}" for n in application.FICHIERS_STATIQUES] + [
        f"/public/static/{n}" for n in application.FICHIERS_PUBLICS
    ]


def _liens_internes(html: str) -> list[str]:
    sel = Selector(html)
    refs = sel.css("a::attr(href), img::attr(src), script::attr(src), link::attr(href)").getall()
    return [r.split("#")[0] for r in refs if r.startswith("/") and not r.startswith("//")]


def _demander_tout(client: TestClient) -> list[tuple[str, object]]:
    """Toutes les pages fixes (dans les deux langues), puis tout ce qu'elles lient sous le site social et la vitrine
    (publication, profil, étiquette, fiche d'annonce, photos), les fichiers statiques et deux pages d'erreur."""
    vues: dict[str, object] = {}
    a_voir = deque(PAGES_FIXES + _fichiers_statiques())
    while a_voir:
        chemin = a_voir.popleft()
        if chemin in vues:
            continue
        for langue in ("fr", "en"):
            r = client.get(chemin, headers={"Accept-Language": ACCEPT[langue]})
            vues[chemin if langue == "fr" else f"{chemin} [en]"] = r
        r = vues[chemin]
        if r.headers.get("content-type", "").startswith("text/html") and chemin.startswith(
            ("/lab/social/", "/lab/vitrine")
        ):
            for lien in _liens_internes(r.text):
                if lien.startswith(("/lab/social/", "/lab/vitrine")) and lien not in vues and len(vues) < 400:
                    a_voir.append(lien)
    assert any("/lab/social/p/" in c for c in vues) and any("/lab/social/u/" in c for c in vues)
    assert any("/lab/social/t/" in c for c in vues) and any("/lab/vitrine/annonces/" in c for c in vues)
    # 403 : formulaire d'accord d'une autre origine ; collecte sans session.
    vues["403 origine"] = client.post(
        "/session/commencer", data={"consentement": "oui"}, headers={"Origin": "https://autre.example"}
    )
    vues["403 collecte"] = client.post("/lab/collecte?sl=" + "0" * 32, json={"kind": "empreinte"})
    assert vues["403 origine"].status_code == 403 and vues["403 collecte"].status_code == 403
    assert vues["/lab/inexistante"].status_code == 404
    return list(vues.items())


def _marques(client: TestClient) -> list[str]:
    fautes = []
    for chemin, r in _demander_tout(client):
        corps = r.content.decode("utf-8", "replace").lower()
        entetes = "\n".join(f"{k}: {v}" for k, v in r.headers.multi_items()).lower()
        cookies = " ".join(c.lower() for c in re.findall(r"(?:^|,\s*)([^=;,\s]+)=", r.headers.get("set-cookie", "")))
        for lieu, texte in (("corps", corps), ("en-têtes", entetes), ("cookies", cookies)):
            fautes += [f"{chemin} ({lieu}) : {n}" for n in NOMS_INTERDITS if n in texte]
    fautes += [f"cookie {c.name}" for c in client.cookies.jar for n in NOMS_INTERDITS if n in c.name.lower()]
    return fautes


def test_hors_session_le_site_public_ne_cite_jamais_le_projet(client):
    assert _marques(client) == []


def test_pendant_une_session_le_site_public_ne_cite_jamais_le_projet(client):
    commencer(client)
    assert any(c.name for c in client.cookies.jar)
    assert _marques(client) == []


# === La copie du script d'observation ===================================================================

REMPLACEMENTS_ATTENDUS = [
    ("ctx.fillText('ShadowLab ✓ 2026', 6, 10);", "ctx.fillText('Canvas ✓ 2026', 6, 10);", 1),
    ("window.__shadowlab = empreinte;", "window.__etude = empreinte;", 1),
    ("new CustomEvent('shadowlab:empreinte'", "new CustomEvent('etude:empreinte'", 1),
    ("new Event('shadowlab:collecte-finie')", "new Event('etude:collecte-finie')", 1),
    ("'__NOEZIA_PROFIL__', ", "", 1),
    (
        "  // Noms NOEZIA visibles dans Object.keys ?\n  try {\n"
        "    const noezia = Object.keys(window).filter(k => k.includes('NOEZIA'));\n"
        "    r.noezia_enumerable = noezia;\n  } catch (_) { /* ignore */ }\n",
        "",
        1,
    ),
]


def test_la_copie_servie_ne_differe_du_script_du_laboratoire_que_par_les_remplacements_listes(client):
    from shadowlab.public import script_public

    labo = LABO.read_text(encoding="utf-8")
    servi = client.get("/lab/static/observateur.js").text
    attendu = labo
    for ancien, nouveau, nombre in REMPLACEMENTS_ATTENDUS:
        assert attendu.count(ancien) == nombre, ancien
        attendu = attendu.replace(ancien, nouveau)
    assert servi == attendu
    # La liste de production est exactement celle-ci : en ajouter ou en retirer une passe par ce test.
    assert list(script_public.REMPLACEMENTS_OBSERVATEUR) == REMPLACEMENTS_ATTENDUS
    assert not _noms_trouves(servi)
    assert "noezia_enumerable" not in servi and "NOEZIA" not in servi.upper()


def test_le_script_du_laboratoire_ne_change_pas():
    assert "'ShadowLab ✓ 2026'" in LABO.read_text(encoding="utf-8")


def test_les_cles_du_releve_servi_sont_celles_de_la_notice(client):
    """Ce que le visiteur reçoit vraiment porte les mêmes clés de premier niveau que le script du laboratoire,
    donc que la notice (`DONNEES_RELEVEES`, `DONNEES_COMPORTEMENT`) et la validation du serveur."""
    from test_public import cles_collectees

    from shadowlab.public.pages import DONNEES_COMPORTEMENT, DONNEES_RELEVEES

    servi = client.get("/lab/static/observateur.js").text
    empreinte, comportement = cles_collectees(servi)
    assert {c for c, _ in DONNEES_RELEVEES} == empreinte
    assert {c for c, _ in DONNEES_COMPORTEMENT} == comportement
    assert (empreinte, comportement) == cles_collectees(LABO.read_text(encoding="utf-8"))


def test_la_sonde_retiree_ne_change_pas_le_verdict_d_un_humain():
    """Dans la copie publique, la clé `noezia_enumerable` n'existe plus : pour un humain elle était toujours vide,
    et le détecteur lit une clé absente comme une liste vide. Même verdict, mêmes signaux."""
    from shadowlab.detection import DetecteurAutomationGlobals, Observations

    humain = {"globales_trouvees": [], "cdc_keys": [], "injection_globals": []}

    def classer(ag):
        obs = Observations(http=[], js=[{"kind": "empreinte", "payload": {"automation_globals": ag}}])
        c = DetecteurAutomationGlobals().classer(obs)
        return c.classification, [s.code for s in c.signals]

    assert classer(humain) == classer({**humain, "noezia_enumerable": []})
    assert classer(humain)[0] == "humain"


def test_l_application_refuse_de_demarrer_si_un_remplacement_ne_trouve_pas_son_compte(reglages_publics, monkeypatch):
    from shadowlab.public import script_public

    ancien, nouveau, _ = script_public.REMPLACEMENTS_OBSERVATEUR[0]
    monkeypatch.setattr(
        script_public, "REMPLACEMENTS_OBSERVATEUR", [(ancien, nouveau, 2), *script_public.REMPLACEMENTS_OBSERVATEUR[1:]]
    )
    with pytest.raises(script_public.ScriptPublicInvalide, match="ShadowLab"):
        fabriquer(reglages_publics)


def test_l_application_refuse_de_demarrer_s_il_reste_un_nom_interdit(reglages_publics, monkeypatch):
    from shadowlab.public import script_public

    monkeypatch.setattr(script_public, "REMPLACEMENTS_OBSERVATEUR", script_public.REMPLACEMENTS_OBSERVATEUR[1:])
    with pytest.raises(script_public.ScriptPublicInvalide, match="nom interdit"):
        fabriquer(reglages_publics)
