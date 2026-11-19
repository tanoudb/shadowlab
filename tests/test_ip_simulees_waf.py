"""4.1 (D-105) : les deux en-têtes d'adresse du frontal ne déclenchent aucune règle du WAF, à aucun niveau.

Exige la pile Docker de l'Arena (déjà lancée ; ce test ne la démarre ni ne la change). Les requêtes vont droit à Nginx
avec un amont injoignable : le WAF décide, rien n'atteint le site de test. La décision d'une requête qui porte
`X-ShadowLab-Adresse` et son sceau doit être la même que celle de la même requête sans eux (mêmes règles, même décision),
du niveau 01 au niveau 07 (paranoïa 4) et à `endurance`. `X-Real-IP` et `Forwarded` ne sont plus transmis par le frontal.
"""

from __future__ import annotations

import base64
import http.client
import json
import os
import uuid

import pytest

pytestmark = pytest.mark.integration
PORT_AVAL = int(os.environ.get("SHADOWLAB_PORT_AVAL", "8781"))
SCEAU = "0123456789abcdef" * 4  # la forme d'un sceau (64 hexadécimaux), jamais valide


def decision_du_waf(profil: str, adresse: str | None) -> dict:
    entetes = {
        "User-Agent": "Mozilla/5.0 (test WAF)",
        "Accept": "text/html,application/xhtml+xml",
        "X-ShadowLab-Profil": profil,
        "X-ShadowLab-Session": f"test-adresse-{uuid.uuid4().hex}",
        "X-ShadowLab-Amont": "1999",
    }
    if adresse is not None:
        entetes["X-ShadowLab-Adresse"] = adresse
        entetes["X-ShadowLab-Adresse-Sceau"] = SCEAU
        entetes["X-Forwarded-For"] = adresse
    connexion = http.client.HTTPConnection("localhost", PORT_AVAL, timeout=10)
    try:
        connexion.request("GET", "/lab/vitrine/annonces?page=2", headers=entetes)
        reponse = connexion.getresponse()
        reponse.read()
    except OSError:
        pytest.skip("pile Docker de l'Arena arrêtée (uv run shadowlab arena demarrer)")
    finally:
        connexion.close()
    entete = reponse.getheader("X-ShadowLab-WAF")
    assert entete, f"pas de décision du WAF (statut {reponse.status})"
    return json.loads(base64.b64decode(entete))


@pytest.mark.parametrize("profil", ["01", "02", "03", "04", "05", "06", "07", "endurance"])
@pytest.mark.parametrize("adresse", ["198.51.100.11", "2001:db8::7"])
def test_les_en_tetes_d_adresse_ne_changent_pas_la_decision_du_waf(profil, adresse):
    sans = decision_du_waf(profil, None)
    avec = decision_du_waf(profil, adresse)
    assert avec["decision"] == sans["decision"], (avec, sans)
    assert sorted(r["id"] for r in avec["regles"]) == sorted(r["id"] for r in sans["regles"])
