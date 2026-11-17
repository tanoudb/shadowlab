"""Résultat de fin de session du site public : côté labo (`shadowlab.resultat_public`, contrat partie A).

Aucune donnée d'un vrai visiteur : chaque test fabrique ses sessions dans une base publique temporaire.
Le module ne recopie aucune règle : son verdict doit être celui de `rejeu._rejouer_session(..., publique=True)`.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from test_rejeu import (
    CDP_SUSPECT,
    COMPORTEMENT_ROBOT,
    HOTE,
    base_publique,
    contenu,
    empreinte,
    entetes,
    message,
    requete,
    t,
)

from shadowlab import rejeu, resultat_public
from shadowlab.arena import profils
from shadowlab.detection import DETECTEURS
from shadowlab.public import donnees

DUREES_MS = [12000, 9000, 15000, 7000, 11000, 13500, 8000, 10000]  # durées de page dispersées : un humain


# --- Fabrication --------------------------------------------------------------------------------


def fabriquer(
    tmp_path: Path,
    pages: int = 5,
    *,
    modifs: dict | None = None,
    comportement: dict | None = None,
    pieges: int = 0,
) -> tuple[Path, str]:
    """Base publique avec une session consentie de `pages` pages, chacune avec son empreinte et son relevé.

    `modifs` change l'empreinte, `comportement` remplace le relevé de chaque page, `pieges` ajoute des pièges
    déclenchés avant la première empreinte. Sans rien de tout cela : un humain sous Chrome, aucun niveau ne l'arrête.
    """
    chemin = tmp_path / "public" / "public.sqlite3"
    cx = donnees.ouvrir(chemin)
    jeton = donnees.creer_session(cx, {"texte_information": "essai", "conservation_jours": 90})
    debut, precedente = 0.0, ""
    for i in range(pages):
        page = "/lab/vitrine" if i == 0 else f"/lab/vitrine/annonces/{i}"
        bruts = entetes(f"https://{HOTE}{precedente}" if precedente else None)
        gardes = donnees.entetes_gardes([(n, v.replace("127.0.0.1:8770", HOTE)) for n, v in bruts], HOTE)
        duree = DUREES_MS[i % len(DUREES_MS)]
        requete(cx, jeton, t(debut), page, cookies=(), en_tetes=gardes)
        requete(cx, jeton, t(debut + 0.2), "/lab/static/observateur.js", cookies=(), en_tetes=gardes)
        message(cx, jeton, t(debut + 1), empreinte(webrtc_test={"saute": "sans-tiers"}, **(modifs or {})), page=page)
        releve = comportement or {
            "evenements": {"mousemove": 120 + 17 * i, "click": 1 + i % 3, "scroll": 4 + i, "keydown": 0},
            "duree_page_ms": duree,
        }
        message(cx, jeton, t(debut + 1 + duree / 1000), releve, kind="comportement", page=page)
        debut += 1 + duree / 1000 + 1.3 * i + 0.7
        precedente = page
    for _ in range(pieges):
        cx.execute(
            "INSERT INTO decisions (session_token, created_at, couche, decision, chemin, motifs)"
            " VALUES (?, ?, 'honeypot', 'declenche', '/lab/piege', '[]')",
            (jeton, t(0.5)),
        )
    cx.close()
    return chemin, jeton


def niveaux_du_resultat() -> profils.Profils:
    return profils.Profils({code: p for code, p in profils.charger() if code in resultat_public.NIVEAUX})


def reference(chemin: Path, jeton: str) -> dict:
    """Ce que dit le rejeu pour cette session, lu comme `rejeu.rejouer` lit ses lignes."""
    cx = rejeu.ouvrir_publique(chemin)
    try:
        ligne = cx.execute(
            "SELECT r.session_token, r.status, r.protection FROM runs r JOIN experiments e ON e.id = r.experiment_id"
            " WHERE e.name = ? AND r.truth = 'humain' AND r.consent_at IS NOT NULL AND r.session_token = ?",
            (donnees.EXPERIENCE, jeton),
        ).fetchone()
        return rejeu._rejouer_session(cx, ligne, niveaux_du_resultat(), publique=True)
    finally:
        cx.close()


def familles_attendues(motifs: list[dict]) -> list[str]:
    presentes = {resultat_public.FAMILLE_DE[m["detecteur"]] for m in motifs}
    return [f for f in resultat_public.FAMILLES if f in presentes]


def textes(valeur) -> set[str]:
    """Toutes les clés et chaînes d'un JSON."""
    if isinstance(valeur, dict):
        return {str(k) for k in valeur} | set().union(*(textes(v) for v in valeur.values()), set())
    if isinstance(valeur, list):
        return set().union(*(textes(v) for v in valeur), set())
    return {valeur} if isinstance(valeur, str) else set()


def entree(chemin: Path, jeton: str) -> str:
    return json.dumps({"base": str(chemin), "jeton": jeton})


def lancer(stdin: str, env_plus: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """`python -m shadowlab.resultat_public` comme le site le lance : l'entrée par stdin, aucun argument."""
    env = {**os.environ, **(env_plus or {})}
    return subprocess.run(
        [sys.executable, "-m", "shadowlab.resultat_public"],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )


def appeler_main(monkeypatch, stdin: str) -> int:
    """`main()` dans ce processus : entrée remplacée, `os.nice` neutralisé (il est permanent pour le processus)."""
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(stdin.encode())))
    monkeypatch.setattr(sys, "argv", ["resultat_public"])
    monkeypatch.setattr(os, "nice", lambda n: 0)
    return resultat_public.main()


# --- Constantes et familles -----------------------------------------------------------------------


def test_constantes_du_contrat():
    assert resultat_public.PAGES_MIN == 4
    assert resultat_public.EMPREINTES_MAX == 80
    assert resultat_public.NIVEAUX == ("01", "02", "03", "04", "05", "06", "07")
    assert len(resultat_public.FAMILLES) == 6
    assert set(resultat_public.FAMILLES) == {
        "automatisation",
        "comportement",
        "incoherence",
        "retouche",
        "cumul",
        "piege",
    }


def test_chaque_detecteur_a_une_famille_connue():
    attendus = set(DETECTEURS) | {"composite", "honeypot"}
    assert attendus <= set(resultat_public.FAMILLE_DE), sorted(attendus - set(resultat_public.FAMILLE_DE))
    assert set(resultat_public.FAMILLE_DE) <= attendus, sorted(set(resultat_public.FAMILLE_DE) - attendus)
    assert set(resultat_public.FAMILLE_DE.values()) <= set(resultat_public.FAMILLES)
    assert resultat_public.FAMILLE_DE["cdp"] == "automatisation"
    assert resultat_public.FAMILLE_DE["composite"] == "cumul"
    assert resultat_public.FAMILLE_DE["honeypot"] == "piege"


# --- Verdict ----------------------------------------------------------------------------------------


def test_session_propre_jugeable_aucun_niveau_arrete(tmp_path):
    chemin, jeton = fabriquer(tmp_path, pages=5)
    res = resultat_public.calculer(chemin, jeton)
    assert res["jugeable"] is True
    assert res["pages"] == 5 and res["pages_min"] == resultat_public.PAGES_MIN
    assert [n["code"] for n in res["niveaux"]] == list(resultat_public.NIVEAUX)
    assert all(n == {"code": n["code"], "arrete": False, "familles": []} for n in res["niveaux"])
    assert set(res) == {"jugeable", "pages", "pages_min", "niveaux"}


SCENARIOS = {
    "automatisation": dict(modifs={"cdp_detection": CDP_SUSPECT}),
    "comportement": dict(comportement=COMPORTEMENT_ROBOT),
    "piege": dict(pieges=1),
    "automatisation_et_piege": dict(modifs={"cdp_detection": CDP_SUSPECT}, pieges=2),
}


@pytest.mark.parametrize("nom", SCENARIOS)
def test_niveaux_arretes_et_familles_viennent_du_rejeu(tmp_path, nom):
    chemin, jeton = fabriquer(tmp_path, pages=6, **SCENARIOS[nom])
    ref = reference(chemin, jeton)
    res = resultat_public.calculer(chemin, jeton)
    assert res["jugeable"] is True
    assert [n["code"] for n in res["niveaux"]] == list(resultat_public.NIVEAUX)
    for n in res["niveaux"]:
        verdict = ref["niveaux"][n["code"]]
        assert n["arrete"] is verdict["arretee"], n["code"]
        assert n["familles"] == (familles_attendues(verdict["motifs"]) if verdict["arretee"] else []), n["code"]
        assert len(set(n["familles"])) == len(n["familles"])
    # La session est bien arrêtée quelque part, et pas partout : le test ne passe pas à vide.
    arretes = [n["code"] for n in res["niveaux"] if n["arrete"]]
    assert arretes and len(arretes) < len(res["niveaux"])
    assert not res["niveaux"][0]["arrete"]  # le niveau 01 n'a aucune protection


def test_familles_nommees_pour_les_cas_connus(tmp_path):
    """Garde-fou contre un test circulaire : les familles attendues, écrites en dur pour trois cas."""

    def familles(**kw):
        chemin, jeton = fabriquer(tmp_path / str(sorted(kw)), pages=5, **kw)
        return {n["code"]: n["familles"] for n in resultat_public.calculer(chemin, jeton)["niveaux"]}

    cdp = familles(modifs={"cdp_detection": CDP_SUSPECT})
    assert {c: f for c, f in cdp.items() if f} == {c: ["automatisation"] for c in ("04", "05", "06", "07")}
    robot = familles(comportement=COMPORTEMENT_ROBOT)
    assert robot["03"] == ["comportement"] and robot["02"] == [] and robot["01"] == []
    piege = familles(pieges=1)
    assert {c: f for c, f in piege.items() if f} == {"06": ["piege"], "07": ["piege"]}
    # Deux familles dans un même niveau : sans doublon, dans l'ordre de FAMILLES (le piège après l'automatisation).
    mixte = familles(modifs={"cdp_detection": CDP_SUSPECT}, pieges=2)
    assert mixte["06"] == mixte["07"] == ["automatisation", "piege"]


# --- Pas de verdict ---------------------------------------------------------------------------------


def test_une_seule_empreinte_trop_courte(tmp_path):
    chemin, jeton = base_publique(tmp_path)
    res = resultat_public.calculer(chemin, jeton)
    assert res == {"jugeable": False, "raison": "courte", "pages": 1, "pages_min": resultat_public.PAGES_MIN}
    assert "niveaux" not in res


@pytest.mark.parametrize("ecart,jugeable", [(-1, False), (0, True)])
def test_seuil_exact_de_pages(tmp_path, ecart, jugeable):
    n = resultat_public.PAGES_MIN + ecart
    chemin, jeton = fabriquer(tmp_path, pages=n)
    res = resultat_public.calculer(chemin, jeton)
    assert res["jugeable"] is jugeable and res["pages"] == n
    assert ("niveaux" in res) is jugeable
    if not jugeable:
        assert res["raison"] == "courte"


def test_trop_d_empreintes_sans_lancer_le_rejeu(tmp_path, monkeypatch):
    n = resultat_public.EMPREINTES_MAX + 1
    chemin, jeton = fabriquer(tmp_path, pages=n)

    def interdit(*args, **kwargs):
        raise AssertionError("le rejeu ne doit pas être lancé au-delà de EMPREINTES_MAX")

    monkeypatch.setattr(rejeu, "_rejouer_session", interdit)
    res = resultat_public.calculer(chemin, jeton)
    assert res == {"jugeable": False, "raison": "longue", "pages": n, "pages_min": resultat_public.PAGES_MIN}


def test_jeton_inconnu(tmp_path):
    chemin, _ = fabriquer(tmp_path, pages=5)
    res = resultat_public.calculer(chemin, "0" * 32)
    assert res == {"jugeable": False, "raison": "inconnue", "pages": 0, "pages_min": resultat_public.PAGES_MIN}


def test_session_non_consentie_inconnue(tmp_path):
    chemin, jeton = fabriquer(tmp_path, pages=5)
    cx = donnees.ouvrir(chemin)
    cx.execute("UPDATE runs SET consent_at = NULL WHERE session_token = ?", (jeton,))
    cx.close()
    assert resultat_public.calculer(chemin, jeton)["raison"] == "inconnue"


# --- Rien de secret dans la sortie ------------------------------------------------------------------


@pytest.mark.parametrize("scenario", [{}, SCENARIOS["automatisation_et_piege"], SCENARIOS["comportement"]])
def test_la_sortie_ne_contient_ni_jeton_ni_detecteur_ni_chemin(tmp_path, scenario):
    chemin, jeton = fabriquer(tmp_path, pages=5, **scenario)
    ref = reference(chemin, jeton)
    res = resultat_public.calculer(chemin, jeton)
    sortie = json.dumps(res)
    assert jeton not in sortie
    assert str(chemin) not in sortie and chemin.name not in sortie and str(tmp_path) not in sortie
    # « comportement » est aussi un nom de famille : il est permis comme famille, jamais comme détecteur.
    interdits = (set(DETECTEURS) | {"composite", "honeypot", "meta-composite"}) - set(resultat_public.FAMILLES)
    assert not interdits & textes(res)
    codes_signaux = {s["code"] for v in ref["niveaux"].values() for m in v["motifs"] for s in m["signaux"]}
    assert not any(code in sortie for code in codes_signaux)


def test_jeton_inconnu_n_est_pas_renvoye(tmp_path):
    chemin, _ = fabriquer(tmp_path, pages=5)
    jeton = "ab" * 16
    assert jeton not in json.dumps(resultat_public.calculer(chemin, jeton))


# --- Lecture seule ------------------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", [{}, SCENARIOS["automatisation_et_piege"]])
def test_le_calcul_n_ecrit_rien(tmp_path, scenario):
    chemin, jeton = fabriquer(tmp_path, pages=5, **scenario)

    def lire() -> dict:
        cx = donnees.ouvrir(chemin)
        try:
            return contenu(cx)
        finally:
            cx.close()

    avant = lire()
    assert avant["observations_js"] and avant["runs"]
    resultat_public.calculer(chemin, jeton)
    assert lire() == avant


# --- Ligne de commande ----------------------------------------------------------------------------------


def test_cli_meme_sortie_que_calculer(tmp_path):
    chemin, jeton = fabriquer(tmp_path, pages=5, modifs={"cdp_detection": CDP_SUSPECT})
    attendu = resultat_public.calculer(chemin, jeton)
    assert any(n["arrete"] for n in attendu["niveaux"])
    p = lancer(entree(chemin, jeton))
    assert p.returncode == 0
    assert json.loads(p.stdout) == attendu
    assert jeton not in p.stdout and str(chemin) not in p.stdout


def test_cli_session_inconnue_reste_un_succes(tmp_path):
    chemin, _ = fabriquer(tmp_path, pages=5)
    p = lancer(entree(chemin, "0" * 32))
    assert p.returncode == 0
    assert json.loads(p.stdout)["raison"] == "inconnue"


@pytest.mark.parametrize("brut", ["", "pas du json", "[1, 2]", '{"base": "x"}', '{"jeton": "x"}'])
def test_cli_entree_illisible_code_2_et_stdout_vide(brut):
    p = lancer(brut)
    assert p.returncode == 2
    assert p.stdout == ""


def test_cli_le_jeton_ne_passe_pas_par_la_ligne_de_commande(tmp_path, monkeypatch):
    """Le jeton vient de stdin ; `main()` n'a besoin d'aucun argument."""
    chemin, jeton = fabriquer(tmp_path, pages=5)
    code = appeler_main(monkeypatch, entree(chemin, jeton))
    assert code == 0
    assert sys.argv == ["resultat_public"] and jeton not in " ".join(sys.argv)


def test_main_baisse_la_priorite_de_10(tmp_path, monkeypatch, capsys):
    chemin, jeton = fabriquer(tmp_path, pages=5)
    appels: list[int] = []
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(entree(chemin, jeton).encode())))
    monkeypatch.setattr(os, "nice", lambda n: appels.append(n) or 0)
    assert resultat_public.main() == 0
    assert appels == [10]
    assert json.loads(capsys.readouterr().out)["jugeable"] is True


def profil_qui_arrete_la_session_propre(tmp_path: Path) -> Path:
    """Fichier de profils supplémentaires : le niveau 03 y arrête dès le premier signal faible de comportement."""
    niveau3 = profils.charger().de("03").model_dump(mode="json")
    niveau3["fingerprinting"] |= {
        "actif": True,
        "bloquer": "tout",
        "detecteurs": ["comportement"],
        "exclure": [],
        "seuil_composite": 0.1,
    }
    fichier = tmp_path / "profils-extra.yaml"
    fichier.write_text(yaml.safe_dump({"03": niveau3}), encoding="utf-8")
    return fichier


def test_cli_ignore_les_profils_supplementaires(tmp_path, monkeypatch):
    chemin, jeton = fabriquer(tmp_path / "base", pages=5)
    extra = profil_qui_arrete_la_session_propre(tmp_path)
    sans = resultat_public.calculer(chemin, jeton)
    assert not any(n["arrete"] for n in sans["niveaux"])
    # Preuve que l'essai est valable : avec la variable, le rejeu arrête bien la session au niveau 03.
    monkeypatch.setenv("SHADOWLAB_PROFILS_EXTRA", str(extra))
    assert resultat_public.calculer(chemin, jeton)["niveaux"][2]["arrete"] is True
    monkeypatch.delenv("SHADOWLAB_PROFILS_EXTRA")
    # Le sous-processus, lui, retire la variable : sa sortie est celle des niveaux officiels.
    p = lancer(entree(chemin, jeton), {"SHADOWLAB_PROFILS_EXTRA": str(extra)})
    assert p.returncode == 0
    assert json.loads(p.stdout) == sans


def test_main_retire_la_variable_des_profils_supplementaires(tmp_path, monkeypatch, capsys):
    chemin, jeton = fabriquer(tmp_path / "base", pages=5)
    monkeypatch.setenv("SHADOWLAB_PROFILS_EXTRA", str(profil_qui_arrete_la_session_propre(tmp_path)))
    assert appeler_main(monkeypatch, entree(chemin, jeton)) == 0
    res = json.loads(capsys.readouterr().out)
    assert not any(n["arrete"] for n in res["niveaux"])
    assert "SHADOWLAB_PROFILS_EXTRA" not in os.environ


def test_cli_base_introuvable_code_1_et_silence(tmp_path):
    p = lancer(entree(tmp_path / "absente.sqlite3", "0" * 32))
    assert p.returncode == 1
    assert p.stdout == "" and p.stderr == ""


# --- Erreur interne ---------------------------------------------------------------------------------------


def test_erreur_interne_code_1_sans_rien_ecrire(tmp_path, monkeypatch, capsys):
    chemin, jeton = fabriquer(tmp_path, pages=5)

    def casse(*args, **kwargs):
        raise RuntimeError(f"échec pour la session {jeton} dans {chemin}")

    monkeypatch.setattr(resultat_public, "calculer", casse)
    assert appeler_main(monkeypatch, entree(chemin, jeton)) == 1
    sortie = capsys.readouterr()
    assert sortie.out == "" and sortie.err == ""
