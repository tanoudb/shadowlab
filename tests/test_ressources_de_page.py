"""Une photo ou un appel de données qu'une page charge n'est pas une page (D-78).

Cas mesuré : campagne 109, passage 34409, niveau 04. Le défi d'entrée se résout en quelques millisecondes, la
liste et ses 18 photos arrivent dans la même seconde : le détecteur de comportement lisait « 5,3 pages par
seconde » à la deuxième photo et bloquait un vrai Chrome. Les instants ci-dessous sont ceux du passage.
"""

from __future__ import annotations

import pytest
from test_detection import UA_CHROME, empreinte, entetes_navigateur

from shadowlab import detection
from shadowlab.arena import profils
from shadowlab.detection import Observations, classer, proprietes
from shadowlab.site import gardien

ENTETES = entetes_navigateur(UA_CHROME)


def h(minute_ms: str, chemin: str, methode: str = "GET", cookies=("sl_session",)) -> dict:
    return {
        "received_at": f"2026-11-14T03:25:{minute_ms}+00:00",
        "method": methode,
        "path": chemin,
        "http_version": "2",
        "headers": ENTETES,
        "cookies": list(cookies),
    }


def releve(instant: str, duree_ms: int, **kw) -> dict:
    payload = {
        "evenements": {"click": 0, "keydown": 0, "mousemove": 5, "scroll": 0, "touchstart": 0},
        "duree_page_ms": duree_ms,
        "page_defilable": False,
        "premiere_interaction_ms": 275,
        "delais_souris_ms": [23.7, 23.8, 50, 27.9],
        "angles_segments": [0.468],
    }
    payload.update(kw)
    return {
        "kind": "comportement",
        "page": "/lab/vitrine/annonces",
        "received_at": f"2026-11-14T03:25:{instant}+00:00",
        "payload": payload,
    }


def passage_34409(jusqu_a_la_photo: int | None = None) -> Observations:
    """Les requêtes et le relevé du passage 34409 (niveau 04), aux instants réels."""
    photos = [h(f"49.{502 + 19 * i}", f"/lab/vitrine/photos/AN-{i + 1:06d}/1.svg") for i in range(18)]
    if jusqu_a_la_photo is not None:
        photos = photos[:jusqu_a_la_photo]
    http = [
        h("48.957", "/lab/vitrine/annonces"),
        h("49.003", "/lab/static/lab.css"),
        h("49.014", "/lab/static/observateur.js"),
        h("49.024", "/lab/static/defi.js"),
        h("49.035", "/lab/static/vendor/botd-2.0.0.esm.js"),
        h("49.322", "/lab/collecte", "POST"),
        h("49.368", "/lab/defi/verifier", "POST"),
        h("49.419", "/lab/vitrine/annonces"),
        h("49.451", "/lab/collecte", "POST"),
        h("49.474", "/lab/static/vitrine.css"),
        h("49.485", "/lab/static/observateur.js"),
        *photos,
    ]
    # le relevé de la page de défi (404 ms de vie) arrive à 49,461 s, avant les photos
    return Observations(http=http, js=[releve("49.461", 404)])


def signaux_comportement(obs: Observations) -> set[str]:
    c = next(c for c in classer(obs) if c.detector_name == "comportement")
    return {s.code for s in c.signals}


def test_cas_mesure_liste_et_photos_dans_la_meme_seconde_apres_un_defi_de_6_ms():
    """Au moment du premier blocage réel (deuxième photo) comme à la fin du passage."""
    for photos in (2, 18):
        signaux = signaux_comportement(passage_34409(photos))
        assert "rythme_soutenu" not in signaux, f"{photos} photos"
        assert "pages_eclair" not in signaux, f"{photos} photos : la page de défi n'est pas une page lue"


def test_la_page_de_defi_ne_masque_pas_une_vraie_page_eclair():
    """Une page de contenu qui ne dure que 100 ms reste signalée, avec ou sans défi avant elle."""
    obs = passage_34409(18)
    obs.js.append(releve("49.900", 100))
    assert "pages_eclair" in signaux_comportement(obs)


def test_une_page_defi_se_reconnait_a_la_verification_pendant_sa_vie():
    """Le relevé d'une page restée 8 s, qui n'a pas posté de vérification de défi, compte comme une page."""
    obs = passage_34409(18)
    obs.js.append(releve("58.415", 100, page_defilable=True))  # vécu de 58,315 à 58,415 : aucune vérification
    assert "pages_eclair" in signaux_comportement(obs)


# --- Le témoin reste attrapé (ces tests passent avant et après la correction) --------------------------------


def temoin_http(photos: int = 0):
    """Client HTTP sans navigateur : six pages à toute vitesse, ni CSS ni JavaScript, sans cookie."""
    http = [h(f"10.{100 + 40 * i}", f"/lab/vitrine/annonces/AN-{i + 1:06d}", cookies=()) for i in range(6)]
    http += [h(f"10.{400 + 5 * i}", f"/lab/vitrine/photos/AN-{i + 1:06d}/1.svg", cookies=()) for i in range(photos)]
    http.sort(key=lambda o: o["received_at"])
    return http


# Sans aucun message JavaScript (ni empreinte ni relevé), le détecteur de comportement ne conclut pas : le témoin
# est vu avec une empreinte reçue, comme dans le gardien (`/lab/collecte`).
def test_temoin_http_declenche_rythme_et_sans_ressources():
    signaux = signaux_comportement(Observations(http=temoin_http(), js=[empreinte()]))
    assert {"rythme_soutenu", "sans_ressources"} <= signaux


def test_temoin_http_qui_prend_aussi_les_photos_reste_sans_ressources():
    """Une photo n'est ni du CSS ni du JavaScript : `sans_ressources` ne s'affaiblit pas."""
    signaux = signaux_comportement(Observations(http=temoin_http(photos=6), js=[empreinte()]))
    assert {"rythme_soutenu", "sans_ressources"} <= signaux


def test_temoin_qui_execute_du_javascript_trop_vite_declenche_pages_eclair():
    obs = Observations(http=temoin_http(), js=[releve(f"10.{300 + i}", 100) for i in range(3)])
    assert {"rythme_soutenu", "pages_eclair", "sans_ressources"} <= signaux_comportement(obs)


def test_une_seule_page_sans_cookie_suivie_de_photos_reste_signalee():
    """`cookies_ignores` lit toutes les requêtes de page, photos comprises : une page + photos sans cookie."""
    http = [h("10.100", "/lab/vitrine/annonces", cookies=())] + [
        h(f"10.{200 + i}", f"/lab/vitrine/photos/AN-{i + 1:06d}/1.svg", cookies=()) for i in range(3)
    ]
    c = next(c for c in classer(Observations(http=http, js=[])) if c.detector_name == "regles-http")
    assert "cookies_ignores" in {s.code for s in c.signals}


# --- Chaque usage de `documents` dont le comportement change -------------------------------------------------


def test_documents_ne_garde_que_les_pages():
    obs = passage_34409()
    assert [o["path"] for o in obs.documents] == ["/lab/vitrine/annonces", "/lab/vitrine/annonces"]
    chemins = {o["path"] for o in obs.ressources_de_page}
    assert "/lab/vitrine/photos/AN-000001/1.svg" in chemins and "/lab/static/lab.css" in chemins
    assert not {o["path"] for o in obs.documents} & chemins


def test_ressources_reste_les_fichiers_css_et_javascript():
    """`ressources` (règle `sans_ressources`) ne contient jamais une photo."""
    obs = passage_34409()
    assert obs.ressources and all(o["path"].startswith("/lab/static") for o in obs.ressources)


def test_navigation_lineaire_ne_compte_pas_les_photos():
    """Deux pages et trois photos, toutes distinctes : ce ne sont pas cinq pages sans retour en arrière."""
    http = [
        h("10.000", "/lab/vitrine/annonces"),
        h("10.100", "/lab/vitrine/photos/AN-000001/1.svg"),
        h("10.200", "/lab/vitrine/photos/AN-000002/1.svg"),
        h("10.300", "/lab/vitrine/photos/AN-000003/1.svg"),
        h("14.000", "/lab/vitrine/annonces/AN-000001"),
    ]
    js = [releve("10.050", 5000), releve("14.050", 5000), releve("15.050", 5000)]
    assert "navigation_lineaire" not in signaux_comportement(Observations(http=http, js=js))


def test_navigation_lineaire_reste_signalee_sur_quatre_vraies_pages():
    http = [h(f"1{i}.000", f"/lab/vitrine/annonces/AN-00000{i}") for i in range(4)]
    js = [releve("19.000", 5000)]
    assert "navigation_lineaire" in signaux_comportement(Observations(http=http, js=js))


def test_proprietes_de_session_liste_les_pages_et_pas_les_photos():
    obs = passage_34409()
    assert proprietes(obs)["session_properties"]["pages"] == ["/lab/vitrine/annonces", "/lab/vitrine/annonces"]


# --- Une seule définition, alignée avec la limite de débit de Nginx (D-71) ---------------------------------


def test_une_ressource_de_page_est_definie_a_un_seul_endroit():
    for chemin in (
        "/lab/static/lab.css",
        "/lab/vitrine/photos/AN-000001/1.svg",
        "/lab/social/photos/x/480.jpg",
        "/lab/vitrine/api/annonces/AN-000001/similaires",
    ):
        assert detection.est_ressource_de_page(chemin), chemin
    for chemin in ("/lab/vitrine/annonces", "/lab/vitrine/annonces/AN-000001", "/lab/social/fil", "/lab/rallye/"):
        assert not detection.est_ressource_de_page(chemin), chemin


def test_un_chemin_qui_remonte_n_est_pas_une_ressource_de_page():
    assert not detection.est_ressource_de_page("/lab/vitrine/photos/../annonces/AN-000001")
    assert not detection.est_photo("/lab/social/photos/../fil")


def test_liste_alignee_avec_la_limite_de_debit_de_nginx():
    """Tout fichier que Nginx ne compte pas (D-71) est une ressource de page ; l'API, comptée par Nginx, l'est
    aussi pour le détecteur (elle n'est pas une page) mais pas pour la limite de débit."""
    for morceau in profils.CHEMINS_STATIQUES:
        assert detection.est_ressource_de_page(f"/lab/{morceau}/exemple"), morceau
    assert not any("api" in morceau for morceau in profils.CHEMINS_STATIQUES)


# --- `gardien.protegee` -------------------------------------------------------------------------------------


def test_une_photo_n_est_pas_un_moment_de_controle_de_page():
    assert not gardien.protegee("/lab/vitrine/photos/AN-000001/1.svg", "GET")
    assert not gardien.protegee("/lab/social/photos/x/480.jpg", "GET")


@pytest.mark.parametrize(
    "chemin",
    [
        "/lab/vitrine/annonces",
        "/lab/vitrine/annonces/AN-000001",
        "/lab/vitrine/api/annonces/AN-000001/similaires",  # contenu des fiches : reste contrôlé
        "/lab/vitrine/photos/../annonces/AN-000001",  # remonter d'un dossier ne donne pas accès aux pages
        "/lab/social/photos/../fil",
        "/lab/rallye/",
    ],
)
def test_pages_et_donnees_restent_controlees(chemin):
    assert gardien.protegee(chemin, "GET")
