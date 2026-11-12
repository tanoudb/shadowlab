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
