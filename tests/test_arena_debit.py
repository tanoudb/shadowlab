"""Limite de débit de l'Arena : elle vise les pages et les appels, pas les fichiers qu'une page charge d'elle-même.

Défaut mesuré le 13/11/2026 (campagne 103) : la liste de la vitrine charge 20 photos en moins d'une seconde ;
au niveau 06 un vrai Chrome recevait 429 dès la quatrième, et passait pour bloqué.

Les tests rapides lisent la configuration Nginx générée. Les tests d'intégration exigent la pile Docker
(``uv run shadowlab arena demarrer``) : requêtes droit à Nginx avec un amont injoignable, le statut et l'en-tête
``X-ShadowLab-Limite`` disent si la limite a joué.
"""

import http.client
import os
import re
import uuid

import pytest

from shadowlab.arena import profils

PORT_AVAL = int(os.environ.get("SHADOWLAB_PORT_AVAL", "8781"))
AMONT_INJOIGNABLE = "1999"

FICHIERS_D_UNE_PAGE = [
    "/lab/static/lab.css",
    "/lab/static/observateur.js",
    "/lab/static/vendor/botd-2.0.0.esm.js",
    "/lab/vitrine/photos/AN-0001/1.svg",
    "/lab/vitrine/photos/AN-0020/3.svg",
]
PAGES_ET_APPELS = [
    "/lab/vitrine/annonces",
    "/lab/vitrine/annonces/AN-0001",
    "/lab/vitrine/api/annonces/AN-0001/similaires",
    "/lab/dynamique",
    "/lab/connexion",
    "/lab/espace",
    "/lab/rallye/saisons",
    "/lab/turnstile/verifier",
    "/lab/recaptcha/verifier",
    "/lab/vitrine/photos",  # le dossier lui-même n'est pas un fichier
    "/lab/vitrine/photos-autre/1.svg",
    "/lab/staticx/lab.css",
    "/lab/vitrine/annonces?x=/lab/static/lab.css",  # $uri exclut la chaîne de requête : testé sur le chemin seul
    "/",
]


def _locations(conf: str) -> list[tuple[str, str, str]]:
    """(modificateur, motif, corps) de chaque `location` du serveur, dans l'ordre du fichier."""
    return re.findall(r"location\s+(=|~)?\s*(\S+)\s*\{(.*?)\}", conf, flags=re.DOTALL)


def _bloc_de(conf: str, chemin: str) -> str:
    """Corps de la `location` que Nginx retient pour ce chemin (exacte, puis expressions dans l'ordre, puis `/`)."""
    chemin = chemin.split("?")[0]
    locations = _locations(conf)
    for modificateur, motif, corps in locations:
        if modificateur == "=" and chemin == motif:
            return corps
    for modificateur, motif, corps in locations:
        if modificateur == "~" and re.search(motif, chemin):
            return corps
    return next(corps for modificateur, motif, corps in locations if modificateur == "" and motif == "/")


@pytest.fixture(scope="module")
def conf() -> str:
    return profils.rendre_nginx(profils.charger())


def test_une_limite_par_niveau_sur_la_location_generale(conf):
    niveaux = profils.charger().codes_arena
    corps = _bloc_de(conf, "/lab/vitrine/annonces")
    for code in niveaux:
        assert f"limit_req zone={code} " in corps, code


@pytest.mark.parametrize("chemin", FICHIERS_D_UNE_PAGE)
def test_les_fichiers_d_une_page_ne_sont_pas_limites(conf, chemin):
    assert "limit_req" not in _bloc_de(conf, chemin), chemin


@pytest.mark.parametrize("chemin", PAGES_ET_APPELS)
def test_les_pages_et_les_appels_restent_limites_a_chaque_niveau(conf, chemin):
    corps = _bloc_de(conf, chemin)
    for code in profils.charger().codes_arena:
        assert f"limit_req zone={code} " in corps, (code, chemin)


def test_les_fichiers_exemptes_passent_toujours_par_le_waf(conf):
    for chemin in FICHIERS_D_UNE_PAGE:
        assert "proxy_pass http://waf;" in _bloc_de(conf, chemin), chemin


def _rafale(profil: str, chemin: str, nombre: int, methode: str = "GET") -> list[http.client.HTTPResponse]:
    """`nombre` requêtes d'une même session, l'une après l'autre sans pause."""
    entetes = {
        "User-Agent": "Mozilla/5.0 (test débit)",
        "Accept": "text/html,application/xhtml+xml",
        "X-ShadowLab-Profil": profil,
        "X-ShadowLab-Session": f"test-debit-{uuid.uuid4().hex}",
        "X-ShadowLab-Amont": AMONT_INJOIGNABLE,
    }
    reponses = []
    connexion = http.client.HTTPConnection("localhost", PORT_AVAL, timeout=10)
    try:
        for _ in range(nombre):
            connexion.request(methode, chemin, headers=entetes)
            r = connexion.getresponse()
            r.read()
            reponses.append(r)
    except OSError:
        pytest.skip("pile Docker de l'Arena arrêtée (uv run shadowlab arena demarrer)")
    finally:
        connexion.close()
    return reponses


@pytest.mark.integration
@pytest.mark.parametrize("profil", ["06", "07"])
def test_vingt_photos_en_rafale_ne_sont_jamais_limitees(profil):
    reponses = _rafale(profil, "/lab/vitrine/photos/AN-0001/1.svg", 20)
    assert [r.status for r in reponses if r.status == 429] == []
    assert [r.getheader("X-ShadowLab-Limite") for r in reponses if r.getheader("X-ShadowLab-Limite")] == []


@pytest.mark.integration
@pytest.mark.parametrize("profil", ["06", "07"])
def test_vingt_pages_en_rafale_sont_limitees(profil):
    reponses = _rafale(profil, "/lab/vitrine/annonces", 20)
    assert sum(r.status == 429 for r in reponses) >= 10  # rafale de 4 (06) ou 2 (07), débit 2 ou 1 par seconde
    assert {r.getheader("X-ShadowLab-Limite") for r in reponses if r.status == 429} == {"REJECTED"}
