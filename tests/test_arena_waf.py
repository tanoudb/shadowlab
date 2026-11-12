"""Tests réels du WAF de l'Arena. Exigent la pile Docker (``uv run shadowlab arena demarrer``).

Les requêtes vont droit à Nginx avec un amont injoignable : le WAF décide, rien n'atteint le site de test.
"""

import base64
import http.client
import json
import os
import random
import string
import uuid

import pytest

from shadowlab.site import gardien

pytestmark = pytest.mark.integration
PORT_AVAL = int(os.environ.get("SHADOWLAB_PORT_AVAL", "8781"))
AMONT_INJOIGNABLE = "1999"
REGLE_CARACTERES_SPECIAUX = 942432  # CRS, paranoïa 4 : deux caractères spéciaux dans un nom ou une valeur


def decision_du_waf(profil: str, chemin: str, corps: str) -> dict:
    """Décision du WAF pour un formulaire envoyé au niveau donné (une session neuve par requête)."""
    entetes = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 (test WAF)",  # sans lui : règle 920320
        "Accept": "text/html,application/xhtml+xml",  # sans lui : règle 920300
        "X-ShadowLab-Profil": profil,
        "X-ShadowLab-Session": f"test-waf-{uuid.uuid4().hex}",
        "X-ShadowLab-Amont": AMONT_INJOIGNABLE,
    }
    connexion = http.client.HTTPConnection("localhost", PORT_AVAL, timeout=10)
    try:
        connexion.request("POST", chemin, body=corps, headers=entetes)
        reponse = connexion.getresponse()
        reponse.read()
    except OSError:
        pytest.skip("pile Docker de l'Arena arrêtée (uv run shadowlab arena demarrer)")
    finally:
        connexion.close()
    entete = reponse.getheader("X-ShadowLab-WAF")
    assert entete, f"pas de décision du WAF (statut {reponse.status})"
    return json.loads(base64.b64decode(entete))


@pytest.mark.parametrize(
    ("chemin", "champ"),
    [
        ("/lab/turnstile/verifier", "cf-turnstile-response"),
        ("/lab/recaptcha/verifier", "g-recaptcha-response"),
    ],
)
def test_niveau_07_laisse_valider_un_captcha_tiers(chemin, champ):
    # Le nom du champ est imposé par le fournisseur. Ses deux tirets suffisaient à déclencher la règle
    # 942432 en paranoïa 4 : personne ne pouvait valider Turnstile ni reCAPTCHA au niveau 07 (campagne 94).
    retour = gardien.encoder_retour("/lab/vitrine/annonces?page=2")
    decision = decision_du_waf("07", chemin, f"{champ}=XXXX.DUMMY.TOKEN.XXXX&retour={retour}")
    assert decision["decision"] != "bloque", decision
    assert REGLE_CARACTERES_SPECIAUX not in [regle["id"] for regle in decision["regles"]]


def _jeton_de_forme_recaptcha() -> str:
    """Fabriqué, jamais valide : environ 1 800 caractères (lettres, chiffres, « - » et « _ »), préfixe « 03A »."""
    alphabet = string.ascii_letters + string.digits + "-_"
    hasard = random.Random(20261112)
    return "03A" + "".join(hasard.choice(alphabet) for _ in range(1800))


def _jeton_de_forme_turnstile() -> str:
    """Fabriqué, jamais valide : segments séparés par des points, avec des tirets, environ 900 caractères."""
    alphabet = string.ascii_letters + string.digits + "-_"
    hasard = random.Random(20261113)

    def segment(longueur: int) -> str:
        return "".join(hasard.choice(alphabet) for _ in range(longueur))

    return f"0.{segment(40)}-{segment(300)}.{segment(40)}-{segment(300)}.{segment(120)}-{segment(60)}"


@pytest.mark.parametrize(
    ("chemin", "champ", "fabriquer"),
    [
        ("/lab/recaptcha/verifier", "g-recaptcha-response", _jeton_de_forme_recaptcha),
        ("/lab/turnstile/verifier", "cf-turnstile-response", _jeton_de_forme_turnstile),
    ],
)
def test_niveau_07_laisse_passer_un_jeton_de_la_forme_d_un_vrai_jeton(chemin, champ, fabriquer):
    # Le jeton factice du test ci-dessus est court. Un vrai jeton fait des centaines de caractères, avec des
    # « - », « _ » et (Turnstile) des points : une autre règle de paranoïa 4 (longueur, caractères spéciaux,
    # injection SQL ou XSS sur des suites aléatoires) pourrait le bloquer. Jeton fabriqué, pas un vrai.
    jeton = fabriquer()
    assert len(jeton) > 500
    retour = gardien.encoder_retour("/lab/vitrine/annonces?page=2")
    decision = decision_du_waf("07", chemin, f"{champ}={jeton}&retour={retour}")
    assert decision["decision"] != "bloque", decision


def test_niveau_07_garde_la_regle_hors_des_captchas_tiers():
    decision = decision_du_waf("07", "/lab/connexion", "a-b-c=1")
    assert REGLE_CARACTERES_SPECIAUX in [regle["id"] for regle in decision["regles"]]


# --- Jetons des fournisseurs de CAPTCHA : les règles d'injection SQL ne les inspectent pas -----------------
#
# Un jeton est une longue suite aléatoire de lettres, chiffres, « - », « _ » (et « . » pour Turnstile). Sur
# 1 800 caractères, il contient par hasard « un chiffre, or, des chiffres, puis - » environ une fois sur mille
# (règle 942210, paranoïa 2), et un Turnstile (avec ses points, donc hors de l'exception « mot simple » de la
# règle 942440) contient « -- » suivi d'un autre « - » une fois sur six. Mesuré : campagne 100, passage 34119.
REGLE_SQL_ENCHAINE = 942210  # CRS, paranoïa 2 : « chained SQL injection attempts 1/2 »
REGLE_COMMENTAIRE_SQL = 942440  # CRS, paranoïa 2 : séquence de commentaire SQL (« -- »), sauf mot simple
MOTIF_942210 = "5or1-"  # un chiffre, « or », des chiffres, « - » : le motif qu'un jeton aléatoire peut contenir
JETONS_FABRIQUES = (
    ("/lab/recaptcha/verifier", "g-recaptcha-response", "recaptcha"),
    ("/lab/turnstile/verifier", "cf-turnstile-response", "turnstile"),
)


def _segment(hasard: random.Random, longueur: int) -> str:
    # Lettres et « _ » seulement : le filler ne déclenche rien, seul le motif ajouté peut le faire.
    return "".join(hasard.choice(string.ascii_letters + "_") for _ in range(longueur))


def _jeton_avec(forme: str, motif: str) -> str:
    """Jeton fabriqué (jamais valide) de la forme d'un vrai jeton, avec le motif glissé au milieu."""
    hasard = random.Random(f"{forme}-{motif}")
    if forme == "recaptcha":
        return "03A" + _segment(hasard, 900) + motif + _segment(hasard, 900)
    return (
        f"0.{_segment(hasard, 300)}-{_segment(hasard, 40)}.{_segment(hasard, 300)}{motif}{_segment(hasard, 300)}"
        f".{_segment(hasard, 120)}"
    )


def _regles_sql(decision: dict) -> list[int]:
    return [regle["id"] for regle in decision["regles"] if 942000 <= regle["id"] < 943000]


@pytest.mark.parametrize("niveau", ["06", "07"])
@pytest.mark.parametrize(("chemin", "champ", "forme"), JETONS_FABRIQUES)
@pytest.mark.parametrize(
    "motif", [MOTIF_942210, "--" + "a" * 5 + "-"], ids=["chiffre-or-chiffre-tiret", "double-tiret"]
)
def test_un_jeton_de_captcha_tiers_n_est_pas_inspecte_par_les_regles_sql(niveau, chemin, champ, forme, motif):
    # Un humain qui valide le CAPTCHA ne doit pas être bloqué parce que son jeton aléatoire ressemble, par
    # hasard, à de l'injection SQL (règles 942210, 942440…). Le nom du champ est imposé par le fournisseur.
    jeton = _jeton_avec(forme, motif)
    retour = gardien.encoder_retour("/lab/vitrine/annonces?page=2")
    decision = decision_du_waf(niveau, chemin, f"{champ}={jeton}&retour={retour}")
    assert decision["decision"] != "bloque", decision
    assert _regles_sql(decision) == [], decision


@pytest.mark.parametrize("niveau", ["06", "07"])
@pytest.mark.parametrize(("chemin", "champ", "forme"), JETONS_FABRIQUES)
def test_l_exclusion_des_jetons_ne_couvre_pas_les_autres_champs_de_la_meme_adresse(niveau, chemin, champ, forme):
    # La même chaîne dans un champ qui n'est pas le jeton du fournisseur reste inspectée.
    jeton_sain = _jeton_avec(forme, "")
    piege = _jeton_avec(forme, MOTIF_942210)
    retour = gardien.encoder_retour("/lab/vitrine/annonces?page=2")
    decision = decision_du_waf(niveau, chemin, f"{champ}={jeton_sain}&commentaire={piege}&retour={retour}")
    assert REGLE_SQL_ENCHAINE in [regle["id"] for regle in decision["regles"]], decision


@pytest.mark.parametrize("niveau", ["06", "07"])
@pytest.mark.parametrize(("_chemin", "champ", "forme"), JETONS_FABRIQUES)
def test_l_exclusion_des_jetons_ne_couvre_pas_les_autres_adresses(niveau, _chemin, champ, forme):
    # Le même nom de champ sur une autre adresse (la connexion) reste inspecté.
    piege = _jeton_avec(forme, MOTIF_942210)
    decision = decision_du_waf(niveau, "/lab/connexion", f"{champ}={piege}")
    assert REGLE_SQL_ENCHAINE in [regle["id"] for regle in decision["regles"]], decision
