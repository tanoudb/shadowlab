"""Rejeu des sessions humaines contre les niveaux de l'Arena et clôture automatique (étape 1.7).

Aucune vraie session humaine n'existe encore : chaque test fabrique les siennes dans une base temporaire.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta

import pytest
import yaml

from shadowlab import analytics, correlation, passages, rejeu
from shadowlab import database as db
from shadowlab.arena import defis, profils
from shadowlab.arena import secret as secrets_arena
from shadowlab.arena.profils import Profil, Profils
from shadowlab.cli import main
from shadowlab.detection import DetecteurChromeApis, Observations, Signal, _verdict, registre
from shadowlab.public import donnees
from shadowlab.site import gardien

T0 = datetime(2026, 11, 1, 18, 0, tzinfo=UTC)  # passé : ces sessions sont inactives pour la clôture
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)"
    " Chrome/142.0.0.0 Safari/537.36"
)
HOTE = "vitrine.test"


def t(secondes: float) -> str:
    return (T0 + timedelta(seconds=secondes)).isoformat(timespec="milliseconds")


def il_y_a(minutes: float) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat(timespec="milliseconds")


def entetes(referent: str | None = None) -> list[list[str]]:
    """En-têtes d'une navigation de Chrome 142 sur macOS, dans l'ordre où il les envoie."""
    paires = [
        ["host", "127.0.0.1:8770"],
        ["connection", "keep-alive"],
        ["sec-ch-ua", '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"'],
        ["sec-ch-ua-mobile", "?0"],
        ["sec-ch-ua-platform", '"macOS"'],
        ["upgrade-insecure-requests", "1"],
        ["user-agent", UA],
        ["accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"],
        ["sec-fetch-site", "same-origin" if referent else "none"],
        ["sec-fetch-mode", "navigate"],
        ["sec-fetch-user", "?1"],
        ["sec-fetch-dest", "document"],
        ["accept-encoding", "gzip, deflate, br, zstd"],
        ["accept-language", "fr-FR,fr;q=0.9,en;q=0.8"],
    ]
    if referent:
        paires.insert(-2, ["referer", referent])
    return paires


def empreinte(n: int = 0, **modifs) -> dict:
    """Empreinte d'un humain sous Chrome : aucun détecteur des niveaux n'y trouve de signal.

    `n` change l'écran et le canvas, pour que deux sessions n'aient pas la même empreinte (corrélation).
    """
    p = {
        "navigateur": {
            "userAgent": UA,
            "webdriver": False,
            "language": "fr-FR",
            "languages": ["fr-FR", "fr"],
            "plugins": 5,
            "platform": "MacIntel",
            "hardwareConcurrency": 8,
            "deviceMemory": 8,
            "maxTouchPoints": 0,
            "userAgentData": {"platform": "macOS", "brands": [{"brand": "Google Chrome", "version": "142"}]},
        },
        "ecran": {
            "width": 1512 + n,
            "height": 982,
            "availWidth": 1512 + n,
            "availHeight": 944,
            "colorDepth": 30,
            "devicePixelRatio": 2,
        },
        "fenetre": {"outerWidth": 1512 + n, "outerHeight": 944, "innerWidth": 1512 + n, "innerHeight": 830},
        "botd": {"bot": False},
        "canvas": f"data:image/png;base64,iVBORw0KGgo{n:04d}",
        "webgl": {"renderer": "ANGLE (Apple, ANGLE Metal Renderer: Apple M5 Pro, Unspecified Version)"},
        "permissions": {"notification": "default", "query": "prompt"},
        "automation": {},
        "fuseau": {"zone": "Europe/Paris", "decalage": -60},
        "chrome_apis": {
            "chrome_app": True,
            "chrome_loadTimes": True,
            "loadTimes_keys": DetecteurChromeApis.LOADTIMES_CLES_ATTENDUES,
            "chrome_csi": True,
            "runtime_PlatformOs": True,
        },
        "languages_test": {
            "language": "fr-FR",
            "languages": ["fr-FR", "fr"],
            "language_dans_languages": True,
            "languages_gelees": True,
            "vendor": "Google Inc.",
        },
        "paint_timing": {"count": 2, "has_first_paint": True, "has_first_contentful_paint": True},
        "webrtc_test": {"disponible": True, "rtc_natif": True, "candidats_host": 0},
        "cdp_detection": dict(CDP_HUMAIN),
    }
    p.update(modifs)
    return p


# Ce qu'envoie un vrai Chrome, outils de développement fermés : `debugger` ne coûte rien (0 ms) et aucun clic n'a
# encore eu lieu quand l'empreinte part, 0,2 s après le chargement.
CDP_HUMAIN = {"debugger_delta_ms": 0, "has_first_input": False, "console_log_natif": True}
CDP_SUSPECT = {**CDP_HUMAIN, "stack_has_evaluate": True}  # code injecté par Runtime.evaluate dans la pile
COMPORTEMENT_HUMAIN = {"evenements": {"mousemove": 150, "click": 2, "scroll": 6, "keydown": 0}, "duree_page_ms": 12000}
COMPORTEMENT_ROBOT = {"evenements": {}, "duree_page_ms": 100}  # aucune interaction, page éclair : 0,5 + 0,5


# --- Fabrication des sessions -------------------------------------------------------------------


@pytest.fixture
def cx(tmp_path):
    connexion = db.ouvrir(tmp_path / "labo.sqlite3")
    yield connexion
    connexion.close()


def session_labo(cx, protection: str = "01", consentie: bool = True) -> str:
    """Session manuelle créée comme le fait /manuel/commencer."""
    experience = passages.experience_manuelle(cx)
    moteur = db.engine_id(cx, "navigateur-manuel", "n/a", "humain", {})
    scenario = db.scenario_id(cx, "navigation_manuelle", "Navigation libre par une personne")
    _, jeton = passages.demarrer(cx, experience, moteur, scenario, 1, "humain", protection=protection)
    if consentie:
        cx.execute("UPDATE runs SET consent_at = ? WHERE session_token = ?", (db.maintenant(), jeton))
    return jeton


def requete(
    cx, jeton, instant: str, chemin: str, *, cookies=("sl_session",), en_tetes=None, methode="GET", tls_id=None
):
    cx.execute(
        "INSERT INTO observations_http (session_token, received_at, method, path, http_version, headers, cookies,"
        " tls_id) VALUES (?, ?, ?, ?, '1.1', ?, ?, ?)",
        (jeton, instant, methode, chemin, db.j(en_tetes or entetes()), db.j(list(cookies)), tls_id),
    )


def message(cx, jeton, instant: str, payload: dict, kind: str = "empreinte", page: str = "/lab/vitrine"):
    cx.execute(
        "INSERT INTO observations_js (session_token, received_at, kind, page, payload) VALUES (?, ?, ?, ?, ?)",
        (jeton, instant, kind, page, db.j(payload)),
    )


def visite(cx, jeton, premiere=None, *, comportement=COMPORTEMENT_HUMAIN, seconde=None, tls_id=None):
    """Deux pages vues par un humain : page, script, empreinte, relevé de comportement, page suivante."""
    requete(cx, jeton, t(0), "/lab/vitrine", cookies=(), tls_id=tls_id)
    requete(cx, jeton, t(0.2), "/lab/static/observateur.js", tls_id=tls_id)
    message(cx, jeton, t(1), premiere or empreinte())
    if comportement:
        message(cx, jeton, t(10), comportement, kind="comportement")
    requete(cx, jeton, t(11), "/lab/vitrine/annonces", en_tetes=entetes("http://127.0.0.1:8770/lab/vitrine"))
    if seconde:
        message(cx, jeton, t(12), seconde, page="/lab/vitrine/annonces")


def profils_test(**fingerprinting) -> Profils:
    """Niveaux fabriqués pour un test : `code=dict de fingerprinting`."""
    base = {
        "limitation": {"debit": 10, "rafale": 10},
        "waf": {"mode": "detection", "paranoia": 1, "seuil": 5},
        "defi_js": {"actif": False},
        "captcha": {"actif": False},
    }
    return Profils({code: Profil.model_validate({**base, "fingerprinting": f}) for code, f in fingerprinting.items()})


def niveau(resultat: dict, code: str) -> dict:
    return next(n for n in resultat["niveaux"] if n["niveau"] == code)


def verdict(resultat: dict, jeton: str, code: str) -> dict:
    return next(s for s in resultat["detail"] if s["jeton"] == jeton)["niveaux"][code]


def contenu(cx) -> dict[str, list[tuple]]:
    tables = [r[0] for r in cx.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
    return {table: [tuple(ligne) for ligne in cx.execute(f"SELECT * FROM {table} ORDER BY rowid")] for table in tables}


# --- Verdict par niveau -------------------------------------------------------------------------


def test_session_humaine_propre_passe_tous_les_niveaux(cx):
    jeton = session_labo(cx)
    visite(cx, jeton, seconde=empreinte())
    resultat = rejeu.rejouer(cx)
    for code in profils.charger().codes:
        assert verdict(resultat, jeton, code) == {"arretee": False, "moment": None, "motifs": [], "classes": {}}
        assert niveau(resultat, code)["arretees"] == 0


def test_cdp_arrete_aux_seuls_niveaux_qui_le_listent(cx):
    jeton = session_labo(cx)
    visite(cx, jeton, empreinte(cdp_detection=CDP_SUSPECT))
    resultat = rejeu.rejouer(cx)
    for code, profil in profils.charger().items():
        v = verdict(resultat, jeton, code)
        if "cdp" in profil.fingerprinting.detecteurs:
            assert v["arretee"], code
            assert v["motifs"] == [
                {
                    "detecteur": "cdp",
                    "signaux": [{"code": "cdp_evaluate", "description": "Runtime.evaluate dans la stack trace"}],
                }
            ]
        else:
            assert not v["arretee"], code
    assert {code for code, _ in profils.charger().items() if verdict(resultat, jeton, code)["arretee"]} == {
        "04",
        "05",
        "06",
        "07",
    }


# --- Fidélité dans le temps ---------------------------------------------------------------------


def test_premiere_empreinte_suspecte_arretee_meme_si_la_suite_est_propre(cx):
    jeton = session_labo(cx)
    visite(cx, jeton, empreinte(cdp_detection=CDP_SUSPECT), seconde=empreinte())
    v = verdict(rejeu.rejouer(cx), jeton, "04")
    assert v["arretee"]
    assert v["moment"] == {"type": "empreinte", "chemin": "/lab/vitrine", "instant": t(1)}  # pas la page d'avant
    assert [m["detecteur"] for m in v["motifs"]] == ["cdp"]


def test_signal_apparu_apres_la_derniere_page_n_arrete_qu_en_fin(cx):
    jeton = session_labo(cx)
    visite(cx, jeton, comportement=None)
    message(cx, jeton, t(20), COMPORTEMENT_ROBOT, kind="comportement")  # après la dernière page (t=11)
    v = verdict(rejeu.rejouer(cx), jeton, "03")
    assert v["arretee"]
    assert v["moment"] == {"type": "fin", "chemin": "", "instant": None}
    assert [m["detecteur"] for m in v["motifs"]] == ["comportement"]


# --- Règles du profil : bloquer, exclure ----------------------------------------------------------


def session_comportement_robot_entre_deux_pages(cx) -> str:
    """Empreinte propre, puis un relevé de robot, puis une page : seul un contrôle de page peut le voir."""
    jeton = session_labo(cx)
    visite(cx, jeton, comportement=COMPORTEMENT_ROBOT)
    return jeton


def test_bloquer_tout_arrete_a_la_page_qui_suit_le_releve(cx):
    jeton = session_comportement_robot_entre_deux_pages(cx)
    niveaux = profils_test(T={"actif": True, "bloquer": "tout", "detecteurs": ["regles-http", "comportement"]})
    v = verdict(rejeu.rejouer(cx, niveaux=niveaux), jeton, "T")
    assert v["arretee"]
    assert v["moment"] == {"type": "page", "chemin": "/lab/vitrine/annonces", "instant": t(11)}


def test_bloquer_http_ignore_le_javascript_aux_pages(cx):
    jeton = session_comportement_robot_entre_deux_pages(cx)
    niveaux = profils_test(H={"actif": True, "bloquer": "http", "detecteurs": ["regles-http", "comportement"]})
    resultat = rejeu.rejouer(cx, niveaux=niveaux)
    assert not verdict(resultat, jeton, "H")["arretee"]
    assert niveau(resultat, "H")["classes"] == []


def test_exclure_est_respecte_aux_pages(cx):
    jeton = session_comportement_robot_entre_deux_pages(cx)
    niveaux = profils_test(
        X={"actif": True, "bloquer": "tout", "detecteurs": ["regles-http", "comportement"], "exclure": ["comportement"]}
    )
    assert not verdict(rejeu.rejouer(cx, niveaux=niveaux), jeton, "X")["arretee"]


def test_bloquer_non_n_arrete_personne_mais_compte_le_detecteur(cx):
    jeton = session_labo(cx)
    visite(cx, jeton, empreinte(cdp_detection=CDP_SUSPECT))
    niveaux = profils_test(N={"actif": True, "bloquer": "non", "detecteurs": ["regles-http", "cdp"]})
    resultat = rejeu.rejouer(cx, niveaux=niveaux)
    assert not verdict(resultat, jeton, "N")["arretee"]
    n = niveau(resultat, "N")
    assert n["arretees"] == 0
    assert n["classes"][0]["detecteur"] == "cdp" and n["classes"][0]["sessions"] == 1


def test_fingerprinting_inactif_rien_n_est_consulte(cx):
    jeton = session_labo(cx)
    visite(cx, jeton, empreinte(cdp_detection=CDP_SUSPECT))
    resultat = rejeu.rejouer(cx)
    assert not verdict(resultat, jeton, "01")["arretee"]
    assert niveau(resultat, "01")["consulte"] is False
    assert niveau(resultat, "01")["non_evalues"] == []


# --- Détecteurs sans données ----------------------------------------------------------------------


def test_tls_absent_non_evalue_et_sans_effet(cx):
    jeton = session_labo(cx)
    visite(cx, jeton)
    resultat = rejeu.rejouer(cx)
    assert not verdict(resultat, jeton, "02")["arretee"]
    non_evalues = {d["detecteur"]: d for d in niveau(resultat, "02")["non_evalues"]}
    assert set(non_evalues) == {"tls"}
    assert non_evalues["tls"]["sessions"] == 1 and "frontal" in non_evalues["tls"]["raison"]
    # Les pièges ne sont servis qu'aux niveaux 06 et 07 : une session faite au niveau 01 ne dit rien d'eux.
    assert "honeypot" in {d["detecteur"] for d in niveau(resultat, "06")["non_evalues"]}
    assert "honeypot" not in {d["detecteur"] for d in niveau(resultat, "05")["non_evalues"]}


def test_detecteur_sans_donnees_ecarte_meme_s_il_classerait(cx, monkeypatch):
    """Le contrat ne dépend pas de la bonne volonté du détecteur : même s'il sanctionnait l'absence de sa
    donnée, il serait écarté du rejeu et signalé, jamais compté contre l'humain."""

    class TlsSevere:
        name, version = "tls", "test"

        def classer(self, obs):
            signaux = [] if obs.tls else [Signal("tls_absent", "aucune empreinte TLS", 1.0)]
            return _verdict(self.name, self.version, signaux)

    vrai = registre()
    monkeypatch.setattr(rejeu, "registre", lambda: {**vrai, "tls": TlsSevere()})
    jeton = session_labo(cx)
    visite(cx, jeton)
    resultat = rejeu.rejouer(cx)
    assert not verdict(resultat, jeton, "02")["arretee"]
    assert niveau(resultat, "02")["classes"] == []
    assert "tls" in {d["detecteur"] for d in niveau(resultat, "02")["non_evalues"]}


def test_tls_present_evalue(cx):
    jeton = session_labo(cx, protection="02")
    details = {"grease": False, "alpn": [], "chiffrements": ["1302"], "extensions": ["0000"], "versions": [771]}
    tls_id = cx.execute(
        "INSERT INTO observations_tls (received_at, ja3, ja3_hash, ja4, details) VALUES (?, 'ja3', 'h', 'ja4', ?)",
        (t(0), db.j(details)),
    ).lastrowid
    visite(cx, jeton, tls_id=tls_id)
    resultat = rejeu.rejouer(cx)
    v = verdict(resultat, jeton, "02")
    assert v["arretee"] and v["moment"]["type"] == "page" and v["moment"]["instant"] == t(0)
    assert [m["detecteur"] for m in v["motifs"]] == ["tls"]
    assert "tls" not in {d["detecteur"] for d in niveau(resultat, "02")["non_evalues"]}


def base_publique(tmp_path, *, debut: str | None = None):
    """Base du site public avec une session consentie, notée comme le fait `public/donnees.py`."""
    chemin = tmp_path / "public" / "public.sqlite3"
    cx = donnees.ouvrir(chemin)
    jeton = donnees.creer_session(cx, {"texte_information": "essai", "conservation_jours": 90})
    if debut:
        cx.execute("UPDATE runs SET started_at = ? WHERE session_token = ?", (debut, jeton))
    vitrine = [(n, v.replace("127.0.0.1:8770", HOTE)) for n, v in entetes()]
    suivante = [(n, v.replace("127.0.0.1:8770", HOTE)) for n, v in entetes(f"https://{HOTE}/lab/vitrine")]
    # Comme `noter_requete` : liste blanche d'en-têtes, Referer réduit, aucun cookie.
    requete(cx, jeton, t(0), "/lab/vitrine", cookies=(), en_tetes=donnees.entetes_gardes(vitrine, HOTE))
    requete(cx, jeton, t(0.2), "/lab/static/observateur.js", cookies=(), en_tetes=donnees.entetes_gardes(vitrine, HOTE))
    message(cx, jeton, t(1), empreinte(webrtc_test={"saute": "sans-tiers"}))
    message(cx, jeton, t(10), COMPORTEMENT_HUMAIN, kind="comportement")
    requete(cx, jeton, t(11), "/lab/vitrine/annonces", cookies=(), en_tetes=donnees.entetes_gardes(suivante, HOTE))
    cx.close()
    return chemin, jeton


def test_piege_declenche_ne_compte_qu_aux_niveaux_qui_servent_des_pieges(cx):
    jeton = session_labo(cx, protection="06")  # niveau qui sert des pièges
    visite(cx, jeton)
    cx.execute(
        "INSERT INTO decisions (session_token, created_at, couche, decision, chemin, motifs)"
        " VALUES (?, ?, 'honeypot', 'declenche', '/lab/piege', '[]')",
        (jeton, t(5)),
    )
    resultat = rejeu.rejouer(cx)
    for code, profil in profils.charger().items():
        v = verdict(resultat, jeton, code)
        if profil.honeypots.actif:
            assert v["arretee"] and [m["detecteur"] for m in v["motifs"]] == ["honeypot"], code
            assert v["moment"]["instant"] == t(11)  # la première page demandée après le piège
        else:
            assert not v["arretee"], code  # ce niveau ne sert aucun piège : rien à déclencher
            assert "honeypot" not in v["classes"], code


def test_session_publique_sans_cookies_pas_de_faux_positif(tmp_path):
    chemin, jeton = base_publique(tmp_path)
    cx = rejeu.ouvrir_publique(chemin)
    try:
        resultat = rejeu.rejouer(cx, publique=True)
        http, js = db.observations(cx, jeton)
    finally:
        cx.close()
    # Sans écarter la règle, l'absence de cookie stocké suffirait à arrêter l'humain au niveau 07.
    sept = profils.charger().de("07")
    brut = gardien.motifs_suspicion(Observations(http=http, js=js), **gardien.parametres(sept))
    assert any(s["code"] == "cookies_ignores" for m in brut for s in m["signaux"])
    for code in profils.charger().codes:
        assert not verdict(resultat, jeton, code)["arretee"], code
    ecartees = {(r["detecteur"], r["regle"]) for r in niveau(resultat, "07")["regles_ecartees"]}
    assert ecartees == {("regles-http", "cookies_ignores"), ("regles-http", "host_tardif")}
    assert "webrtc" in {d["detecteur"] for d in niveau(resultat, "07")["non_evalues"]}  # sonde sautée


# --- Lecture seule, sessions inutilisables, corrélation -------------------------------------------


def test_rejeu_n_ecrit_rien(cx):
    propre, suspecte = session_labo(cx), session_labo(cx, protection="06")
    visite(cx, propre)
    visite(cx, suspecte, empreinte(1, cdp_detection=CDP_SUSPECT))
    correlation.enregistrer_hash(cx, propre, empreinte())
    db.enregistrer_decision(cx, suspecte, "honeypot", "declenche", "/lab/piege", [{"type": "lien"}])
    avant, changements = contenu(cx), cx.total_changes
    rejeu.rejouer(cx)
    assert contenu(cx) == avant
    assert cx.total_changes == changements
    assert avant["empreintes_vues"] and avant["decisions"]


def test_session_sans_empreinte_inutilisable_hors_taux(cx):
    avec, sans = session_labo(cx), session_labo(cx)
    visite(cx, avec)
    requete(cx, sans, t(0), "/lab/vitrine", cookies=())
    resultat = rejeu.rejouer(cx)
    assert resultat["sessions"] == {"total": 2, "rejouees": 1, "inutilisables": 1}
    assert resultat["inutilisables"] == [sans]
    assert all(n["rejouees"] == 1 for n in resultat["niveaux"])
    assert [s["jeton"] for s in resultat["detail"]] == [avec]


def test_session_non_consentie_ignoree(cx):
    visite(cx, session_labo(cx, consentie=False))
    assert rejeu.rejouer(cx)["sessions"]["total"] == 0


def test_correlation_non_evaluee_et_historique_signale(cx):
    jeton = session_labo(cx)
    visite(cx, jeton)
    # Même empreinte, 10 sessions : un seul signal de comptage (le plus grand des deux comptes), de poids 1 dès 10.
    # À 6, il pèse 0,7 : le détecteur seul ne classe plus (avant, profil et canvas en donnaient chacun un).
    for autre in [jeton, *(passages.nouveau_jeton() for _ in range(9))]:
        correlation.enregistrer_hash(cx, autre, empreinte())
    premier = rejeu.rejouer(cx)
    assert not verdict(premier, jeton, "06")["arretee"]
    six = niveau(premier, "06")
    raison = next(d["raison"] for d in six["non_evalues"] if d["detecteur"] == "correlation-session")
    assert "historique" in raison
    assert six["correlation_historique"] == {"sessions": 1, "sur": 1}
    assert niveau(premier, "05")["correlation_historique"] is None  # non consulté au niveau 05
    assert rejeu.rejouer(cx) == premier  # rien d'écrit : l'ordre et le nombre de rejeux ne changent rien


def test_agregat_par_niveau_avec_wilson(cx):
    suspecte = session_labo(cx)
    visite(cx, suspecte, empreinte(cdp_detection=CDP_SUSPECT))
    for n in (1, 2):
        visite(cx, session_labo(cx), empreinte(n))
    quatre = niveau(rejeu.rejouer(cx), "04")
    assert (quatre["rejouees"], quatre["arretees"], quatre["passees"]) == (3, 1, 2)
    assert quatre["taux_arret"] == analytics.wilson(1, 3)
    assert quatre["classes"] == [
        {"detecteur": "cdp", "sessions": 1, "signaux": [{"code": "cdp_evaluate", "sessions": 1}]}
    ]


# --- Clôture automatique et base publique en lecture seule ----------------------------------------


def test_cloture_des_sessions_manuelles_inactives(cx):
    inactive, active, jamais_vue = session_labo(cx), session_labo(cx), session_labo(cx)
    requete(cx, inactive, il_y_a(20), "/lab/vitrine", cookies=())
    message(cx, inactive, il_y_a(19), empreinte())
    requete(cx, active, il_y_a(30), "/lab/vitrine", cookies=())
    message(cx, active, il_y_a(1), empreinte(1))
    cx.execute("UPDATE runs SET started_at = ? WHERE session_token IN (?, ?)", (il_y_a(30), inactive, jamais_vue))
    # Un passage de campagne en cours n'est jamais touché.
    experience = cx.execute(
        "INSERT INTO experiments (name, created_at, configuration, status) VALUES ('campagne', ?, '{}', 'en_cours')",
        (db.maintenant(),),
    ).lastrowid
    moteur = db.engine_id(cx, "playwright", "1", "python", {})
    scenario = db.scenario_id(cx, "navigation", "")
    _, campagne = passages.demarrer(cx, experience, moteur, scenario, 1, "automatise")
    cx.execute("UPDATE runs SET started_at = ? WHERE session_token = ?", (il_y_a(60), campagne))

    assert rejeu.clore_inactives(cx) == 2
    statut = {r["session_token"]: r for r in cx.execute("SELECT * FROM runs")}
    for jeton in (inactive, jamais_vue):
        assert statut[jeton]["status"] == "reussi" and statut[jeton]["completed_at"]
    assert statut[active]["status"] == "en_cours" and statut[campagne]["status"] == "en_cours"
    run_inactive = statut[inactive]["id"]
    assert cx.execute("SELECT COUNT(*) FROM detections WHERE run_id = ?", (run_inactive,)).fetchone()[0] > 0
    assert rejeu.clore_inactives(cx) == 0
    # Close ou non, une session humaine avec une empreinte reste rejouée.
    assert {s["jeton"] for s in rejeu.rejouer(cx)["detail"]} == {inactive, active}


def test_base_publique_en_lecture_seule(tmp_path, cx):
    debut = il_y_a(180)  # au-delà des 2 h du site public : la session reste « en_cours » en base
    chemin, jeton = base_publique(tmp_path, debut=debut)
    lecture = rejeu.ouvrir_publique(chemin)
    try:
        assert rejeu.rejouer(lecture, publique=True)["sessions"]["rejouees"] == 1
        with pytest.raises(Exception, match="readonly"):
            lecture.execute("UPDATE runs SET status = 'reussi'")
    finally:
        lecture.close()
    verif = donnees.ouvrir(chemin)
    try:
        ligne = verif.execute("SELECT status, started_at FROM runs WHERE session_token = ?", (jeton,)).fetchone()
    finally:
        verif.close()
    assert (ligne["status"], ligne["started_at"]) == ("en_cours", debut)
    session_labo(cx)
    with pytest.raises(ValueError):
        rejeu.ouvrir_publique(tmp_path / "labo.sqlite3")  # la base du labo n'est pas une base publique


# --- Même verdict que l'Arena -----------------------------------------------------------------------


def test_meme_verdict_que_l_arena(client, reglages, monkeypatch, tmp_path):
    """La même suite d'observations passe par le vrai chemin (frontal simulé, /lab/collecte, gardien) puis
    par le rejeu. Les niveaux 90 à 92 vérifient les réglages du profil dès la réception de l'empreinte :
    `bloquer: http` n'y consulte pas le JavaScript, `bloquer: non` n'arrête personne, `exclure` écarte le
    détecteur (sans quoi un profil d'ablation bloquerait encore sur le détecteur retiré)."""
    base = {"limitation": {"debit": 1000, "rafale": 1000}, "waf": {"mode": "detection", "paranoia": 1, "seuil": 100}}
    base |= {"defi_js": {"actif": False}, "captcha": {"actif": False}}
    extra = {
        "90": {**base, "fingerprinting": {"actif": True, "bloquer": "http", "detecteurs": ["regles-http", "cdp"]}},
        "91": {**base, "fingerprinting": {"actif": True, "bloquer": "non", "detecteurs": ["regles-http", "cdp"]}},
        "92": {
            **base,
            "fingerprinting": {
                "actif": True,
                "bloquer": "tout",
                "detecteurs": ["regles-http", "cdp"],
                "exclure": ["cdp"],
            },
        },
    }
    fichier = tmp_path / "profils-extra.yaml"
    fichier.write_text(yaml.safe_dump(extra), encoding="utf-8")
    monkeypatch.setenv("SHADOWLAB_PROFILS_EXTRA", str(fichier))
    secret = secrets_arena.charger(reglages.dossier_arena)
    cx = db.ouvrir(reglages.base_donnees)

    def frontal(jeton, chemin, cookies=("sl_session",), referent=None):
        """Ce que le frontal note avant de relayer la requête."""
        cx.execute(
            "INSERT INTO observations_http (session_token, received_at, method, path, http_version, headers,"
            " cookies, source) VALUES (?, ?, 'GET', ?, '1.1', ?, ?, 'frontal')",
            (jeton, db.maintenant(), chemin, db.j(entetes(referent)), db.j(list(cookies))),
        )

    arena: dict[str, tuple[str, bool]] = {}
    n = 0
    for code in profils.charger().codes_arena:
        for suspecte in (False, True):
            n += 1
            r = client.post("/manuel/commencer", data={"protection": code, "consentement": "oui"})
            jeton = re.search(r"sl=([0-9a-f]{32})", r.text).group(1)
            for usage, nom in (
                ("defi", gardien.COOKIE_DEFI),
                ("turnstile", gardien.COOKIE_TURNSTILE),
                ("recaptcha", gardien.COOKIE_RECAPTCHA),
                ("captcha", gardien.COOKIE_CAPTCHA),
            ):
                client.cookies.set(nom, defis.creer_cookie(secret, usage, jeton, ""))
            sceau = {
                "x-shadowlab-sceau": secrets_arena.signer(secret, "obs", code, jeton, "", ""),
                "x-shadowlab-obs": "obs",
                "x-shadowlab-profil": code,
                "x-shadowlab-session": jeton,
                "x-shadowlab-ja4": "",
            }
            frontal(jeton, "/lab/vitrine", cookies=())
            frontal(jeton, "/lab/static/observateur.js")
            assert client.get(f"/lab/vitrine?sl={jeton}", headers=sceau).status_code == 200
            payload = empreinte(n, cdp_detection=CDP_SUSPECT) if suspecte else empreinte(n)
            corps = json.dumps({"kind": "empreinte", "page": "/lab/vitrine", "payload": payload})
            assert client.post(f"/lab/collecte?sl={jeton}", content=corps, headers=sceau).status_code == 204
            frontal(jeton, "/lab/vitrine/annonces", referent="http://127.0.0.1:8770/lab/vitrine")
            r2 = client.get(f"/lab/vitrine/annonces?sl={jeton}", headers=sceau)
            assert r2.status_code in (200, 403)
            arena[jeton] = (code, r2.status_code == 403)

    resultat = rejeu.rejouer(cx)
    for jeton, (code, bloquee) in arena.items():
        v = verdict(resultat, jeton, code)
        assert v["arretee"] == bloquee, (code, jeton)
        if bloquee:
            ligne = cx.execute(
                "SELECT motifs FROM decisions WHERE session_token = ? AND couche = 'fingerprinting-differe'", (jeton,)
            ).fetchone()
            assert v["moment"]["type"] == "empreinte" and v["motifs"] == json.loads(ligne["motifs"])
    bloquees = sorted(code for code, b in arena.values() if b)
    assert bloquees == ["04", "05", "06", "07"]  # les sessions à empreinte CDP, là où `cdp` est consulté et bloque
    cx.close()


def test_detecteur_exclu_ne_fait_pas_servir_le_captcha(client, reglages, monkeypatch, tmp_path):
    """Un détecteur retiré par `exclure` ne décide nulle part, pas même de servir le CAPTCHA démo. Sans quoi une
    ablation mesure encore le détecteur retiré : campagne 93, niveau 04 sans `cdp`, CAPTCHA servi 15 fois sur 15
    pour un motif `cdp`."""
    sans_cdp = {"actif": True, "bloquer": "tout", "detecteurs": ["regles-http", "cdp"], "exclure": ["cdp"]}
    extra = {
        "93": {
            "limitation": {"debit": 1000, "rafale": 1000},
            "waf": {"mode": "detection", "paranoia": 1, "seuil": 100},
            "defi_js": {"actif": False},
            "captcha": {"actif": True},
            "fingerprinting": sans_cdp,
        }
    }
    fichier = tmp_path / "profils-extra.yaml"
    fichier.write_text(yaml.safe_dump(extra), encoding="utf-8")
    monkeypatch.setenv("SHADOWLAB_PROFILS_EXTRA", str(fichier))
    secret = secrets_arena.charger(reglages.dossier_arena)
    cx = db.ouvrir(reglages.base_donnees)
    r = client.post("/manuel/commencer", data={"protection": "93", "consentement": "oui"})
    jeton = re.search(r"sl=([0-9a-f]{32})", r.text).group(1)
    sceau = {
        "x-shadowlab-sceau": secrets_arena.signer(secret, "obs", "93", jeton, "", ""),
        "x-shadowlab-obs": "obs",
        "x-shadowlab-profil": "93",
        "x-shadowlab-session": jeton,
        "x-shadowlab-ja4": "",
    }
    for chemin, cookies, referent in (
        ("/lab/vitrine", [], None),
        ("/lab/static/observateur.js", ["sl_session"], None),
        ("/lab/vitrine/annonces", ["sl_session"], "http://127.0.0.1:8770/lab/vitrine"),
    ):
        cx.execute(
            "INSERT INTO observations_http (session_token, received_at, method, path, http_version, headers,"
            " cookies, source) VALUES (?, ?, 'GET', ?, '1.1', ?, ?, 'frontal')",
            (jeton, db.maintenant(), chemin, db.j(entetes(referent)), db.j(cookies)),
        )
    payload = empreinte(1, cdp_detection=CDP_SUSPECT)
    corps = json.dumps({"kind": "empreinte", "page": "/lab/vitrine", "payload": payload})
    assert client.post(f"/lab/collecte?sl={jeton}", content=corps, headers=sceau).status_code == 204

    assert client.get(f"/lab/vitrine/annonces?sl={jeton}", headers=sceau).status_code == 200
    couches = [d["couche"] for d in db.decisions_session(cx, jeton)]
    assert "captcha" not in couches
    cx.close()


# --- Commande -------------------------------------------------------------------------------------


def test_commande_rejeu_base_vide(reglages, capsys):
    assert main(["rejeu"]) == 0
    assert "Aucune session humaine" in capsys.readouterr().out


def test_commande_rejeu_labo(reglages, capsys):
    cx = db.ouvrir(reglages.base_donnees)
    suspecte, propre, oubliee = session_labo(cx), session_labo(cx), session_labo(cx)
    visite(cx, suspecte, empreinte(cdp_detection=CDP_SUSPECT))
    visite(cx, propre, empreinte(1))
    requete(cx, oubliee, il_y_a(30), "/lab/vitrine", cookies=())
    cx.execute("UPDATE runs SET started_at = ? WHERE session_token = ?", (il_y_a(30), oubliee))
    cx.execute("UPDATE runs SET started_at = ? WHERE session_token IN (?, ?)", (t(-1), suspecte, propre))
    cx.close()
    assert main(["rejeu"]) == 0
    sortie = capsys.readouterr().out
    assert "3 session(s) en cours clôturée(s)" in sortie
    assert "inutilisable" in sortie
    assert re.search(r"^04\s.*\s2\s+1\s+1\s", sortie, re.M)  # niveau 04 : 2 rejouées, 1 arrêtée, 1 passée
    assert "cdp" in sortie and "tls" in sortie
    assert main(["rejeu", "--json"]) == 0
    donnees_json = json.loads(capsys.readouterr().out)
    assert donnees_json["sessions"] == {"total": 3, "rejouees": 2, "inutilisables": 1}


def test_commande_rejeu_base_publique(reglages, tmp_path, capsys):
    chemin, _ = base_publique(tmp_path)
    assert main(["rejeu", "--base", str(chemin), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["base"] == "publique"
    cx = db.ouvrir(reglages.base_donnees)
    session_labo(cx)
    cx.close()
    assert main(["rejeu", "--base", str(reglages.base_donnees)]) == 2
    assert "Refus" in capsys.readouterr().err
