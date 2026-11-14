"""Verrou : les pages des deux sites du labo (vitrine et rallye) ne changent pas d'un octet.

Règle du cadrage du site public (`docs/recherche/site-public-communaute-2026-11-13.md`) : les recettes de récolte
et la vérité dépendent de ce HTML, et la campagne de contrôle de D-74 doit se comparer à la 108. Les crochets que
l'application publique ajoute à `site/vitrine.py` et `site/rallye.py` sont additifs : par défaut, la page
d'aujourd'hui.

Les empreintes SHA-256 ont été relevées sur le code du 13/11/2026 (commit cb1ff99), avant toute modification de
ces deux modules. Si un test échoue, une page du labo a changé : c'est un défaut à corriger, jamais une empreinte
à recalculer. (Elles dépendent aussi du générateur `random` de Python, stable d'une version à l'autre pour
`randint`, `choice`, `sample` et `uniform`.)
"""

from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

from shadowlab.config import charger
from shadowlab.site import rallye, vitrine
from shadowlab.site.app import creer_app

GRAINE_VITRINE, TAILLE_VITRINE = 20261111, 45
GRAINE_RALLYE, TAILLE_RALLYE = 20261112, 12  # deux saisons : pagination du calendrier, spéciale annulée
JETON = "0123456789abcdef0123456789abcdef"

# Échantillon : chaque type de page des deux sites.
PAGES = {
    "vitrine-accueil": "/lab/vitrine",
    "vitrine-liste": "/lab/vitrine/annonces?page=2",
    "vitrine-fiche": "/lab/vitrine/annonces/AN-000003",
    "rallye-saisons": "/lab/rallye/saisons",
    "rallye-calendrier": "/lab/rallye/saisons/2023?page=2",
    "rallye-fiche": "/lab/rallye/rallyes/2",
    "rallye-speciale": "/lab/rallye/speciales/1",
    "rallye-speciale-annulee": "/lab/rallye/speciales/6",
    "rallye-classement": "/lab/rallye/rallyes/3/classement",
    "rallye-engages": "/lab/rallye/rallyes/3/engages",
    "rallye-chassis": "/lab/rallye/chassis/DEMO-BAL-0001",
    "rallye-pilote": "/lab/rallye/pilotes/1",
}

EMPREINTES: dict[tuple[str, bool], str] = {
    ("vitrine-accueil", False): "76339873890b2403aa0d1edb38e15796dc12438cf0cfad2deecc57c9e3a1805b",
    ("vitrine-accueil", True): "6e2c55993614a7465b91701c562bf609ef41289be0acd6aa0a81822ac8d4c671",
    ("vitrine-liste", False): "a056d8dc115b57c688f2c517dd975b70e49d8c8c280e39c8ead7a861edfb3b1e",
    ("vitrine-liste", True): "54e565f4223c27bff504e6d4177886d643c5fd5f5cffb298eef2993baff35421",
    ("vitrine-fiche", False): "65b537d0fb8a624bc1f58b6e49a5344c9dc768d40469d2b82531ef6d3278f944",
    ("vitrine-fiche", True): "77138c71ae7453cb0688281dab51cec3008c9670cde778f828d43a777a902b34",
    ("rallye-saisons", False): "afa3a8df28c989e643a611d9a195bc5e0587e23f4761f483bf2a0ad459fdf90b",
    ("rallye-saisons", True): "82660faefafbc49f14c83840dfb51ee54b4eb9d2f34c17eb46848a1b8afbc432",
    ("rallye-calendrier", False): "78ef6fb8dfa15f2b474f7244dded46a18c7ed2951161b212266bc3070e05e1d4",
    ("rallye-calendrier", True): "91c800baa960bd3b86511a903b1613955713b9c9f7149f76f01b07d23f3f3ac9",
    ("rallye-fiche", False): "341b1dca8e7c270749ffe68ffe2f97adf9fa3e0e3998afafc66fc2b6a7c4eb52",
    ("rallye-fiche", True): "8da7fe2607508a4263232b06f043d41e5a3d04bfa81dfb82aa8e688bac1c4fa5",
    ("rallye-speciale", False): "17368af54da03325f830aa10bebb88cb006a7235c1fc295ec69a548128d22859",
    ("rallye-speciale", True): "29926914feb6c8b6df46b860aaf0188acad0b817e19f220066019c07c7174c66",
    ("rallye-speciale-annulee", False): "ee9ce5b90fdf8e3050ca86126d3405027e3bb5f813639013e3eff1528784d41c",
    ("rallye-speciale-annulee", True): "a1cd392a75e14729ca04931ceb4bde90c6375e7907af583851c858d43fcb14d2",
    ("rallye-classement", False): "ece809e21d82ebe42079d7f9d12ae4808fb1e250fa10acdc7115417364456213",
    ("rallye-classement", True): "e8eff80fe3c541a649a86e9050cec892ee2bd14f1ddff1c582a2326083e3efff",
    ("rallye-engages", False): "6126347fd9368dca1a025ae1ecfa494cb63aeb0f5f54e6d852f567848b7ec80d",
    ("rallye-engages", True): "a9f17503972bc625b1cd7a179b0bef53322943bb5e90d2c8051b4c5b7ef0fea2",
    ("rallye-chassis", False): "81e3b9276adec595277e82f4bf1130d5ab350f19307741a3a8be317fa4558196",
    ("rallye-chassis", True): "bff78db904f43014adfff6737f1f4b43f01b1bf67b706d6f459b18b3d1392a09",
    ("rallye-pilote", False): "fc83d73d8daa808e7d691417d02dcf07cdb4a4d1fb9f4900630d990b2e0e5e32",
    ("rallye-pilote", True): "d0cfa41965d0032b3ea7f3d40baa74761518b7e9e3023a18cfd21d6b192032f7",
}

EMPREINTES_AVEC_PIEGE: dict[str, str] = {
    "vitrine-accueil": "136a89278b06ad76d4855807a7d4b053af832424f32c0047312ddc0a86997e5d",
    "vitrine-liste": "2481aa5b3b0103d4f3199ff41baf385b8d0940a01792a5915aa16131a4fe072b",
    "vitrine-fiche": "d63c0acb2cbeb463887f5d7ac4d622a8ef116282ad3a8b5b174f9db053ae1a57",
    "rallye-saisons": "4c36f36a62da318801b2c67d82f4291650a3ed1b0a41bdd5b669fb258c1a660a",
    "rallye-calendrier": "f6f79916493cd26765af1d62c5cb3c658e20a494261a0c40236c0f9dded4b149",
    "rallye-fiche": "921a214e9aa47b5bd426df361698a0793fe2577f65c53758cc6497a4f2264642",
    "rallye-speciale": "dd993ebbd04502eea0e7c7e358425b1723ebe8a3ce5b41023c7623905452b73d",
    "rallye-classement": "0ec0e77bfa6c0b668511e4549fb8989508d7f2cd4d46fb8e2fbef586ee386ef6",
    "rallye-engages": "e798177aaa2d1aafe8ade1062c0acb96799a45428bcaeaccfbf713e274b4ea5c",
    "rallye-chassis": "0b9ecaca03c39b96c7e6aa3d7ddd46c56648c76aca7db5d745daaf34472435b5",
    "rallye-pilote": "741a992c234f4cba14266b704f6a9fdaefe36bc1e9224a5a6de3e11eb1b72702",
}


def pages_avec_piege() -> dict[str, str]:
    """Pages rendues directement par les modules, lien piège actif : une branche que le labo ne prend que derrière
    le frontal de l'Arena (sceau), donc absente des pages servies au client de test."""
    annonces = vitrine.generer(GRAINE_VITRINE, TAILLE_VITRINE)
    u = rallye.construire(GRAINE_RALLYE, TAILLE_RALLYE)
    r2 = u.trouver_rallye(2)
    return {
        "vitrine-accueil": vitrine.page_accueil(JETON, annonces, honeypot=True),
        "vitrine-liste": vitrine.page_liste(JETON, annonces, 2, honeypot=True),
        "vitrine-fiche": vitrine.page_fiche(JETON, annonces[2], honeypot=True),
        "rallye-saisons": rallye.page_saisons(JETON, u, honeypot=True),
        "rallye-calendrier": rallye.page_calendrier(JETON, u, 2023, 2, honeypot=True),
        "rallye-fiche": rallye.page_rallye(JETON, u, r2, honeypot=True),
        "rallye-speciale": rallye.page_speciale(JETON, u, u.trouver_speciale(1), honeypot=True),
        "rallye-classement": rallye.page_classement(JETON, u, u.trouver_rallye(3), honeypot=True),
        "rallye-engages": rallye.page_engages(JETON, u, u.trouver_rallye(3), honeypot=True),
        "rallye-chassis": rallye.page_chassis(JETON, u, u.trouver_chassis("DEMO-BAL-0001"), honeypot=True),
        "rallye-pilote": rallye.page_pilote(JETON, u, u.trouver_pilote(1), honeypot=True),
    }


@pytest.fixture
def client_labo(reglages, monkeypatch):
    monkeypatch.setenv("SHADOWLAB_VITRINE_GRAINE", str(GRAINE_VITRINE))
    monkeypatch.setenv("SHADOWLAB_VITRINE_TAILLE", str(TAILLE_VITRINE))
    monkeypatch.setenv("SHADOWLAB_RALLYE_GRAINE", str(GRAINE_RALLYE))
    monkeypatch.setenv("SHADOWLAB_RALLYE_TAILLE", str(TAILLE_RALLYE))
    with TestClient(creer_app(charger()), base_url="http://127.0.0.1") as c:
        yield c


def empreinte(contenu: bytes) -> str:
    return hashlib.sha256(contenu).hexdigest()


@pytest.mark.parametrize("avec_jeton", [False, True], ids=["sans-jeton", "avec-jeton"])
@pytest.mark.parametrize("nom", list(PAGES))
def test_page_servie_par_le_labo_inchangee(client_labo, nom, avec_jeton):
    adresse = PAGES[nom]
    if avec_jeton:
        adresse += ("&" if "?" in adresse else "?") + f"sl={JETON}"
    client_labo.cookies.clear()  # sans jeton : aucun cookie de session d'une requête précédente
    r = client_labo.get(adresse)
    assert r.status_code == 200, adresse
    attendu = JETON if avec_jeton else ""
    assert f'<meta name="sl-session" content="{attendu}">' in r.text, "jeton de session (ou son absence) dans la page"
    assert empreinte(r.content) == EMPREINTES[(nom, avec_jeton)], f"la page du labo {adresse} a changé"


@pytest.mark.parametrize("nom", list(EMPREINTES_AVEC_PIEGE))
def test_page_avec_lien_piege_inchangee(nom):
    pages = pages_avec_piege()
    assert set(pages) == set(EMPREINTES_AVEC_PIEGE)
    assert 'class="sl-hp"' in pages[nom], "le lien piège est bien dans la page"
    assert empreinte(pages[nom].encode()) == EMPREINTES_AVEC_PIEGE[nom], f"la page {nom} (piège actif) a changé"
