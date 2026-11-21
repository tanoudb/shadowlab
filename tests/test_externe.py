"""Collecte externe : paquet sans marque, contrat de données, pont d'analyse (`docs/collecte-externe.md`).

Aucun navigateur : le script de relevé est joué sous Node (comme `test_public_releve.py`), l'analyse lit un fichier.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from test_public_releve import BANC, TOUS_LES_GESTES, avec_node

from shadowlab.cli import main
from shadowlab.externe import analyse, paquet
from shadowlab.public import script_public, trace

EXEMPLE = Path(__file__).parent / "donnees" / "sessions-externes-exemple.jsonl"
JETON = "a" * 32


# ---------- paquet sans marque ----------


def test_paquet_ecrit_deux_scripts_sans_aucun_nom_interdit(tmp_path):
    empreintes = paquet.fabriquer(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["manifeste.json", "observateur.js", "releve.js", "vendor"]
    assert set(empreintes) == {"observateur.js", "releve.js", *paquet.VENDOR}
    for nom in empreintes:
        assert script_public.noms_trouves((tmp_path / nom).read_bytes()) == []
    manifeste = json.loads((tmp_path / "manifeste.json").read_text())
    assert manifeste["fichiers"] == empreintes and manifeste["point_d_envoi"] == "meta[name=sl-collecte]"


def test_paquet_ne_contient_aucune_adresse_d_un_site_reel(tmp_path):
    paquet.fabriquer(tmp_path)
    for nom in ("observateur.js", "releve.js", "manifeste.json"):
        texte = (tmp_path / nom).read_text()
        assert "omni" not in texte.lower() and "supabase" not in texte.lower()


def test_observateur_externe_poste_vers_la_balise_et_replie_sur_le_point_d_entree_du_labo(tmp_path):
    paquet.fabriquer(tmp_path)
    code = (tmp_path / "observateur.js").read_text()
    assert "sl-collecte" in code and "/lab/collecte" in code  # repli
    assert "`/lab/collecte?sl=" not in code  # plus d'adresse en dur dans l'envoi
    assert "ShadowLab" not in code and "__shadowlab" not in code


def test_paquet_refuse_un_nom_interdit_qui_reste(tmp_path, monkeypatch):
    monkeypatch.setattr(paquet, "REMPLACEMENTS_OBSERVATEUR", [])  # plus de remplacement : le nom reste
    with pytest.raises(script_public.ScriptPublicInvalide):
        paquet.fabriquer(tmp_path)


def _banc(script: Path, options: dict) -> dict:
    sortie = subprocess.run(
        ["node", str(BANC), str(script), "pas", json.dumps({"options": options, "pas": TOUS_LES_GESTES})],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    ).stdout
    return json.loads(sortie)


@avec_node
@pytest.mark.parametrize(
    ("collecte", "attendu"),
    [
        (None, f"/lab/collecte?sl={JETON}"),  # aucune balise : le site public ne change pas
        ("/api/ext/collecte", f"/api/ext/collecte?sl={JETON}"),
        ("/api/ext/collecte?v=1", f"/api/ext/collecte?v=1&sl={JETON}"),
        ("https://autre.example/x", f"/lab/collecte?sl={JETON}"),  # jamais un autre hôte
        ("//autre.example/x", f"/lab/collecte?sl={JETON}"),
        ("/\\autre.example", f"/lab/collecte?sl={JETON}"),
        ("", f"/lab/collecte?sl={JETON}"),
    ],
)
def test_releve_poste_vers_la_balise_de_la_page(tmp_path, collecte, attendu):
    paquet.fabriquer(tmp_path)
    options = {"chemin": "/lab/social/p/abc"} | ({} if collecte is None else {"collecte": collecte})
    resultat = _banc(tmp_path / "releve.js", options)
    assert resultat["lues"] == [] and resultat["erreurs"] == []
    (page,) = resultat["pages"]
    assert page["envois"] and {e["url"] for e in page["envois"]} == {attendu}


# ---------- contrat et analyse ----------


def _lignes() -> list[dict]:
    return [json.loads(ligne) for ligne in EXEMPLE.read_text().splitlines() if ligne.strip()]


def _sessions() -> list:
    return [analyse.lire_session(brut)[0] for brut in _lignes()]


def test_l_exemple_est_au_format_du_contrat_et_ses_traces_sont_valides():
    sessions = _lignes()
    assert len(sessions) == 3
    for brut in sessions:
        session, refus = analyse.lire_session(brut)
        assert refus is None, refus
        for envoi in brut["traces"]:
            assert trace.valider(envoi["payload"]) is not None


def test_l_exemple_n_a_ni_ip_ni_courriel_ni_texte_libre():
    texte = EXEMPLE.read_text()
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", texte)
    sans_versions = re.sub(r"\d+\.0\.0\.0", "", texte)
    assert not re.search(r"(?<![\d.])\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?![\d.])", sans_versions)


@pytest.mark.parametrize(
    ("modif", "mot"),
    [
        (lambda s: s.update(ip="203.0.113.7"), "clé inconnue"),
        (lambda s: s["contexte"].update(compte="jean@exemple.fr"), "compte"),
        (lambda s: s["contexte"].update(compte="u_" + "g" * 12), "compte"),
        (lambda s: s["contexte"].update(email="x@y.fr"), "clé inconnue"),
        (lambda s: s["entetes"].update(cookie="a=b"), "clé inconnue"),
        (lambda s: s["entetes"].update(**{"x-forwarded-for": "1.2.3.4"}), "clé inconnue"),
        (lambda s: s["pages"].append({"instant": s["debut"], "chemin": "/lire?token=abc"}), "chemin"),
        (lambda s: s["traces"][0]["payload"].update(souris=[1.5]), "trace"),
        (lambda s: s["traces"][0]["payload"].update(texte="abc"), "trace"),
        (lambda s: s.update(debut="2026-11-20 18:00:00"), "début"),
        (lambda s: s.update(format=2), "format"),
        (lambda s: s.pop("empreintes"), "empreinte"),
    ],
)
def test_une_session_hors_contrat_est_refusee_avec_sa_raison(modif, mot):
    brut = _lignes()[0]
    modif(brut)
    session, refus = analyse.lire_session(brut)
    assert session is None and refus and mot in refus, refus


def test_les_identifiants_d_extension_sont_masques_a_la_lecture():
    brut = _lignes()[0]
    brut["empreintes"][0]["payload"]["stack_trace_test"] = {"stack": "at chrome-extension://abcdefghijklmnop/x.js:1"}
    session, refus = analyse.lire_session(brut)
    assert refus is None
    assert "abcdefghijklmnop" not in json.dumps(session.js)


def test_analyse_de_l_exemple_dit_ce_qui_n_est_pas_evalue_et_ne_devine_rien():
    resultat = analyse.analyser(_sessions(), refusees=[])
    assert resultat["sessions"] == {"total": 3, "rejouees": 3, "refusees": 0}
    niveaux = {n["niveau"]: n for n in resultat["niveaux"]}
    assert "04" in niveaux and "07" in niveaux
    assert {d["detecteur"] for d in niveaux["06"]["non_evalues"]} >= {"correlation-session", "honeypot"}
    non = {d["detecteur"]: d for d in niveaux["04"]["non_evalues"]}
    assert non["regles-http"]["sessions"] == 3
    assert non["comportement"]["sessions"] == 1  # la session sans relevé de comportement : dite, pas devinée
    detail = {s["jeton"]: s for s in resultat["detail"]}
    assert detail["ext-b-sans-comportement"]["non_evalues"]["comportement"]
    assert "comportement" not in detail["ext-b-sans-comportement"]["niveaux"]["04"]["classes"]
    ecartee = niveaux["04"]["regles_ecartees"]
    assert [(r["detecteur"], r["regle"], r["sessions"]) for r in ecartee] == [("comportement", "sans_ressources", 3)]
    assert detail["ext-c-webdriver"]["niveaux"]["04"]["arretee"] is True
    assert detail["ext-a-humain"]["niveaux"]["04"]["arretee"] is False


def test_les_traces_sont_comptees_mais_pas_jugees():
    resultat = analyse.analyser(_sessions(), refusees=[])
    assert resultat["traces"]["recues"] >= 1
    assert "aucun détecteur" in resultat["traces"]["note"]


def test_choix_des_niveaux():
    resultat = analyse.analyser(_sessions(), refusees=[], codes=["05", "06"])
    assert [n["niveau"] for n in resultat["niveaux"]] == ["05", "06"]
    with pytest.raises(ValueError, match="niveau"):
        analyse.analyser(_sessions(), refusees=[], codes=["99"])


def test_commande_externe_analyser_sur_l_exemple(capsys):
    code = main(["externe", "analyser", str(EXEMPLE), "--niveaux", "04,06"])
    sortie = capsys.readouterr().out
    assert code == 0
    assert "Niveau 04" in sortie and "Niveau 06" in sortie and "Niveau 05" not in sortie
    assert "non évalu" in sortie.lower()
    assert "3 session(s)" in sortie


def test_commande_externe_analyser_json(capsys):
    assert main(["externe", "analyser", str(EXEMPLE), "--json"]) == 0
    resultat = json.loads(capsys.readouterr().out)
    assert resultat["sessions"]["total"] == 3 and resultat["niveaux"]


def test_commande_externe_analyser_fichier_absent_ou_session_refusee(tmp_path, capsys):
    assert main(["externe", "analyser", str(tmp_path / "absent.jsonl")]) == 2
    mauvais = tmp_path / "x.jsonl"
    mauvais.write_text('{"format": 1, "ip": "1.2.3.4"}\nce n\'est pas du json\n')
    assert main(["externe", "analyser", str(mauvais)]) == 0
    sortie = capsys.readouterr().out
    assert "refusée" in sortie and "ligne 1" in sortie and "ligne 2" in sortie


def test_commande_externe_paquet(tmp_path):
    cible = tmp_path / "paquet"
    assert main(["externe", "paquet", str(cible)]) == 0
    assert (cible / "releve.js").is_file() and (cible / "observateur.js").is_file()
    if shutil.which("node"):
        assert subprocess.run(["node", "--check", str(cible / "observateur.js")], capture_output=True).returncode == 0


# ---------- le document dit la même chose que le code ----------

DOC = Path(__file__).parents[1] / "docs" / "collecte-externe.md"
OBSERVATEUR = Path(__file__).parents[1] / "src" / "shadowlab" / "site" / "static" / "observateur.js"


def test_le_contrat_liste_les_cles_de_l_empreinte_dans_l_ordre_du_script():
    source = OBSERVATEUR.read_text("utf-8")
    bloc = source[source.index("async function collecter()") : source.index("async function demarrer")]
    cles = re.findall(r"^    (\w+):", bloc, re.M)
    texte = DOC.read_text("utf-8")
    liste = re.search(r"`navigateur`.*?`duree_collecte_ms`", texte, re.S).group(0)
    assert re.findall(r"`(\w+)`", liste) == cles


def test_le_contrat_decrit_chaque_cle_de_la_trace():
    texte = DOC.read_text("utf-8")
    tableau = texte[texte.index("| Clé | Forme | Bornes |") : texte.index("Une liste est une liste")]
    decrites = set(re.findall(r"^\| `(\w+)` \|", tableau, re.M))
    assert decrites == set(trace.SCHEMA)


# ---------- cas relevés à la relecture ----------


def test_le_paquet_porte_ce_que_observateur_importe(tmp_path):
    paquet.fabriquer(tmp_path)
    code = (tmp_path / "observateur.js").read_text("utf-8")
    imports = re.findall(r"from '(\./[^']+)'", code)
    assert imports == ["./vendor/botd-2.0.0.esm.js"]
    for chemin in imports:
        assert (tmp_path / chemin).is_file()
    # FingerprintJS n'est chargé que sur deux pages du labo : aucune de ces pages n'existe sur un site externe
    assert "'/lab/empreinte', '/lab/detection'" in code
    assert not (tmp_path / "vendor" / "fingerprintjs-5.3.0.esm.js").exists()
    assert script_public.noms_trouves((tmp_path / "vendor" / "botd-2.0.0.esm.js").read_bytes()) == []


def test_sans_entetes_le_verdict_ne_change_pas():
    """Un en-tête absent de l'export n'est jamais lu comme « le navigateur ne l'a pas envoyé »."""
    avec = _lignes()[0]
    sans = _lignes()[0]
    del sans["entetes"]
    verdicts = []
    for brut in (avec, sans):
        session, refus = analyse.lire_session(brut)
        assert refus is None
        detail = analyse.analyser([session], refusees=[])["detail"][0]
        verdicts.append({code: (v["arretee"], v["classes"]) for code, v in detail["niveaux"].items()})
    assert verdicts[0] == verdicts[1]


def test_plusieurs_empreintes_sont_acceptees_et_la_premiere_fait_foi():
    brut = _lignes()[0]
    deuxieme = json.loads(json.dumps(brut["empreintes"][0]))
    deuxieme["instant"] = "2026-11-20T18:09:00.000+00:00"
    deuxieme["payload"]["navigateur"]["webdriver"] = True  # un rechargement plus tard : ne doit pas juger la session
    brut["empreintes"].append(deuxieme)
    session, refus = analyse.lire_session(brut)
    assert refus is None
    assert [o["kind"] for o in session.js].count("empreinte") == 2
    detail = analyse.analyser([session], refusees=[])["detail"][0]
    assert detail["niveaux"]["04"]["arretee"] is False  # comme `rejeu` : la première empreinte est celle des détecteurs
    brut["empreintes"] = []
    assert analyse.lire_session(brut)[0] is None
