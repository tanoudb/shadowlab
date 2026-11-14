"""Durée des cookies de réussite d'un défi : un réglage du profil, 3 600 s par défaut.

Pourquoi : pour mesurer une récolte plus longue que le cookie, il faut pouvoir le raccourcir sans attendre une
heure. `duree_cookie_s` vaut pour les cookies `defi`, `captcha`, `turnstile` et `recaptcha` ; le cookie `connexion`
(espace privé) garde 3 600 s. Le temps est figé sur `defis.time` : aucun `sleep`.
"""

import itertools
from types import SimpleNamespace

import pytest
import yaml
from pydantic import ValidationError

from shadowlab.arena import defis, profils
from shadowlab.arena import secret as secrets_arena
from shadowlab.site import gardien

JETON = "0123456789abcdef0123456789abcdef"
SECRET = b"secret-de-test"
FICHIER_COURT = profils.RACINE / "configs" / "arena" / "profils-cookie-court.yaml"
FICHIER_SANS_CORRELATION = profils.RACINE / "configs" / "arena" / "profils-sans-correlation.yaml"
COPIES = {"04court": "04", "05court": "05", "06scorrcourt": "06scorr"}


def _figer(monkeypatch, instant: float) -> None:
    """Fige l'horloge vue par `defis` (et par elle seule)."""
    monkeypatch.setattr(defis, "time", SimpleNamespace(time=lambda: instant))


def test_cookie_de_600_s_valide_a_599_s_refuse_a_601_s(monkeypatch):
    _figer(monkeypatch, 1_000_000)
    cookie = defis.creer_cookie(SECRET, "defi", JETON, duree_s=600)
    _figer(monkeypatch, 1_000_599)
    assert defis.cookie_valide(SECRET, "defi", cookie, JETON)
    _figer(monkeypatch, 1_000_601)
    assert not defis.cookie_valide(SECRET, "defi", cookie, JETON)


def test_sans_reglage_la_duree_reste_3600_s(monkeypatch):
    assert defis.DUREE_COOKIE_S == 3600
    _figer(monkeypatch, 1_000_000)
    cookie = defis.creer_cookie(SECRET, "defi", JETON)
    _figer(monkeypatch, 1_003_599)
    assert defis.cookie_valide(SECRET, "defi", cookie, JETON)
    _figer(monkeypatch, 1_003_601)
    assert not defis.cookie_valide(SECRET, "defi", cookie, JETON)


def test_les_profils_existants_gardent_3600_s_par_defaut():
    tous = profils.charger()
    assert all(p.duree_cookie_s == 3600 for _, p in tous)


def _entetes(reglages, profil: str) -> dict[str, str]:
    secret = secrets_arena.charger(reglages.dossier_arena)
    return {
        "x-shadowlab-sceau": secrets_arena.signer(secret, "obs", profil, JETON, "ja4-reel", ""),
        "x-shadowlab-obs": "obs",
        "x-shadowlab-profil": profil,
        "x-shadowlab-session": JETON,
        "x-shadowlab-ja4": "ja4-reel",
        "x-shadowlab-liaison": "",
    }


def _cookie_de_defi_obtenu(client, reglages, profil: str, difficulte: int) -> str:
    """Résout le défi comme le ferait un navigateur : le cookie vient de la route de l'application."""
    secret = secrets_arena.charger(reglages.dossier_arena)
    defi = defis.creer_defi(secret, JETON, difficulte)
    nonce = next(n for n in itertools.count() if defis.verifier_defi(secret, JETON, defi, n) is None)
    r = client.post(
        f"/lab/defi/verifier?sl={JETON}",
        json={"defi": defi, "nonce": nonce},
        headers=_entetes(reglages, profil),
    )
    assert r.status_code == 204, r.text
    return r.cookies[gardien.COOKIE_DEFI]


def _page_a(client, reglages, profil: str, cookie: str):
    client.cookies.clear()
    client.cookies.set(gardien.COOKIE_DEFI, cookie)
    return client.get(f"/lab/vitrine?sl={JETON}", headers=_entetes(reglages, profil))


def test_dans_l_application_le_cookie_du_profil_court_expire_et_celui_du_profil_par_defaut_non(
    client, reglages, monkeypatch
):
    monkeypatch.setenv("SHADOWLAB_PROFILS_EXTRA", str(FICHIER_COURT))
    cookie_court = _cookie_de_defi_obtenu(client, reglages, "04court", 12)
    cookie_normal = _cookie_de_defi_obtenu(client, reglages, "04", 12)
    maintenant = defis.time.time()
    # Même instant (maintenant + 601 s) pour les deux : seul le réglage du profil change.
    _figer(monkeypatch, maintenant + 601)
    refus = _page_a(client, reglages, "04court", cookie_court)
    assert refus.status_code == 403 and refus.json()["bloque_par"] == "defi-js"
    assert _page_a(client, reglages, "04", cookie_normal).status_code == 200
    # À 599 s, le cookie court passe encore.
    _figer(monkeypatch, maintenant + 599)
    assert _page_a(client, reglages, "04court", cookie_court).status_code == 200


def test_le_cookie_de_connexion_garde_3600_s(client, reglages, monkeypatch):
    monkeypatch.setenv("SHADOWLAB_PROFILS_EXTRA", str(FICHIER_COURT))
    _figer(monkeypatch, 1_000_000)
    cookie = defis.creer_cookie(SECRET, "connexion", JETON)
    _figer(monkeypatch, 1_003_599)
    assert defis.cookie_valide(SECRET, "connexion", cookie, JETON)


def _profil_d_origine(code: str) -> profils.Profil:
    if code == "06scorr":
        brut = yaml.safe_load(FICHIER_SANS_CORRELATION.read_text(encoding="utf-8"))
        return profils.Profil.model_validate(brut["06scorr"])
    brut = yaml.safe_load(profils.FICHIER.read_text(encoding="utf-8"))
    return profils.Profil.model_validate(brut[code])


def _sans(profil: profils.Profil) -> dict:
    return profil.model_dump(exclude={"duree_cookie_s", "description"})


@pytest.mark.parametrize(("court", "origine"), COPIES.items())
def test_les_profils_cookie_court_sont_des_copies_a_la_duree_pres(court, origine, monkeypatch):
    monkeypatch.setenv("SHADOWLAB_PROFILS_EXTRA", str(FICHIER_COURT))
    copie = profils.charger().de(court)
    assert copie is not None
    assert copie.duree_cookie_s == 600
    assert _profil_d_origine(origine).duree_cookie_s == 3600
    assert _sans(copie) == _sans(_profil_d_origine(origine))
    assert copie.description != _profil_d_origine(origine).description


def test_le_fichier_cookie_court_se_suffit_et_ne_contient_que_ses_trois_profils(monkeypatch):
    brut = yaml.safe_load(FICHIER_COURT.read_text(encoding="utf-8"))
    assert set(brut) == set(COPIES)
    monkeypatch.setenv("SHADOWLAB_PROFILS_EXTRA", str(FICHIER_COURT))
    assert set(COPIES) <= set(profils.charger().codes_arena)


def test_la_generation_nginx_et_coraza_accepte_les_profils_cookie_court(monkeypatch):
    monkeypatch.setenv("SHADOWLAB_PROFILS_EXTRA", str(FICHIER_COURT))
    tous = profils.charger()
    nginx, coraza = profils.rendre_nginx(tous), profils.rendre_coraza(tous)
    for code in COPIES:
        assert f"zone={code}:" in nginx and f"limit_req zone={code} " in nginx
        assert f'"@streq {code}"' in coraza


@pytest.mark.parametrize("valeur", [0, 29, 86_401, -1])
def test_une_duree_hors_bornes_est_refusee(valeur):
    brut = yaml.safe_load(profils.FICHIER.read_text(encoding="utf-8"))["04"]
    with pytest.raises(ValidationError):
        profils.Profil.model_validate({**brut, "duree_cookie_s": valeur})


@pytest.mark.parametrize("valeur", [30, 86_400])
def test_les_bornes_elles_memes_sont_acceptees(valeur):
    brut = yaml.safe_load(profils.FICHIER.read_text(encoding="utf-8"))["04"]
    assert profils.Profil.model_validate({**brut, "duree_cookie_s": valeur}).duree_cookie_s == valeur


def test_une_duree_hors_bornes_est_refusee_au_chargement(tmp_path, monkeypatch):
    brut = yaml.safe_load(FICHIER_COURT.read_text(encoding="utf-8")) if FICHIER_COURT.exists() else {}
    brut["04court"] = {**yaml.safe_load(profils.FICHIER.read_text(encoding="utf-8"))["04"], "duree_cookie_s": 5}
    extra = tmp_path / "extra.yaml"
    extra.write_text(yaml.safe_dump(brut), encoding="utf-8")
    monkeypatch.setenv("SHADOWLAB_PROFILS_EXTRA", str(extra))
    with pytest.raises(ValidationError):
        profils.charger()
