"""Sentinelle complète (étape 4) : pages de défi, porte d'entrée, arrêt sans nouvelle requête, reprise.

Pilote factice qui se comporte comme un navigateur (JavaScript, page relue sans nouvelle requête) : ni réseau ni
navigateur. Les pages de défi sont écrites à la main ici ; aucune n'est la copie d'un site réel.
"""

from __future__ import annotations

import pytest
from outils_recolte import RECETTE_VITRINE, PiloteFactice, creer_client, fabriquer, lu

from shadowlab.engines.noezia.etat import Etat
from shadowlab.engines.noezia.sentinelle import Alerte, detecter_defi

PAGE_ARENA = (
    '<!doctype html><html><head><title>Vérification — ShadowLab</title></head>'
    '<body data-arena="defi"><main class="arena"><h1>Vérification</h1><div id="defi" hidden></div></main></body></html>'
)
# Page de défi d'un fournisseur, écrite à la main : formulaire de défi, cadre d'un service de vérification.
PAGE_FOURNISSEUR = (
    "<!doctype html><html><head><title>Vérification de sécurité</title></head><body>"
    '<form id="challenge-form" action="/verifier" method="post">'
    '<iframe src="https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/b/turnstile/if/ov2/av0/rcv/x"'
    ' title="Widget"></iframe></form></body></html>'
)
PAGE_VIDE = "<html><body><p>page vide</p></body></html>"
PORTE = "\nporte_entree:\n  attendre_s: 15\n"


class PiloteNavigateur(PiloteFactice):
    """Se comporte comme `DriverNoezia` : exécute du JavaScript, et la page peut changer sans nouvelle requête."""

    runtime = "navigateur"
    executes_javascript = True

    def __init__(self, client, hotes=("*",)):
        super().__init__(client, hotes)
        self.dom_apres_attente: list[str] = []  # contenu de la page à chaque relecture (le défi se valide seul)
        self.relectures = 0

    def etat_page(self):
        self.relectures += 1
        if self.dom_apres_attente:
            self._texte = self.dom_apres_attente.pop(0)
        return 200, self.urls[-1], {}


@pytest.fixture
def site(reglages, monkeypatch):
    with creer_client(monkeypatch) as client:
        yield client


@pytest.fixture
def pilote(site):
    return PiloteNavigateur(site)


@pytest.fixture
def dossier(tmp_path):
    return tmp_path / "recoltes" / "vitrine-annonces"


def avec_porte():
    return RECETTE_VITRINE.read_text(encoding="utf-8") + PORTE


# --- Reconnaître une page de défi ---------------------------------------------------------------


def test_reconnait_le_defi_de_l_arena():
    assert detecter_defi(PAGE_ARENA, {}) == "arena"


def test_reconnait_le_defi_d_un_fournisseur():
    assert detecter_defi(PAGE_FOURNISSEUR, {}) == "cloudflare"
    assert detecter_defi("<html><body></body></html>", {"cf-mitigated": "challenge"}) == "cloudflare"


@pytest.mark.parametrize(
    ("html", "attendu"),
    [
        ('<div class="g-recaptcha" data-sitekey="x"></div>', "recaptcha"),
        ('<iframe src="https://www.google.com/recaptcha/api2/anchor?k=x"></iframe>', "recaptcha"),
        ('<div class="h-captcha" data-sitekey="x"></div>', "hcaptcha"),
        ('<iframe src="https://newassets.hcaptcha.com/captcha/v1/x"></iframe>', "hcaptcha"),
        ('<div class="cf-turnstile" data-sitekey="x"></div>', "turnstile"),
    ],
)
def test_reconnait_les_cadres_de_captcha(html, attendu):
    assert detecter_defi(f"<html><body>{html}</body></html>", {}) == attendu


def test_une_page_ordinaire_n_est_pas_un_defi():
    assert detecter_defi('<html><body data-champ="x"><h1>Annonce</h1></body></html>', {}) is None
    # La balise de mesure que Cloudflare ajoute aux pages ordinaires n'est pas un défi.
    balise = '<script src="/cdn-cgi/challenge-platform/scripts/jsd/main.js"></script>'
    assert detecter_defi(f"<html><body><p>texte</p>{balise}</body></html>", {}) is None
    # Un texte qui parle de reCAPTCHA n'est pas un cadre de CAPTCHA.
    assert detecter_defi("<html><body><p>Nous utilisons reCAPTCHA et hCaptcha.</p></body></html>", {}) is None
    assert detecter_defi("<html><body></body></html>", {"cf-mitigated": "autre"}) is None


# --- Arrêt sans nouvelle requête, état gardé, reprise -------------------------------------------


def test_un_429_a_la_page_10_zero_requete_ensuite_puis_reprise(dossier, pilote):
    pilote.reponses["AN-000010"] = (429, "<html><body>trop de requêtes</body></html>")
    bilan = fabriquer(dossier, pilote).lancer()
    assert bilan.code == 3 and bilan.statut == "arretee" and bilan.arret["signe"] == "statut"
    assert pilote.demandes[-1].endswith("AN-000010") and pilote.statuts[-1] == 429  # dernière requête : le 429
    demandees = len(pilote.demandes)
    etat = Etat(dossier / "etat.sqlite3")
    assert etat.passe(1)["statut"] == "arretee" and etat.pages(1, "en_cours") == 0
    assert etat.pages(1, "a_faire") > 0
    etat.fermer()
    assert len(pilote.demandes) == demandees  # rien n'est parti après l'alerte, ni à la fermeture
    pilote.reponses.clear()
    reprise = fabriquer(dossier, pilote).reprendre(maintenant=True)
    assert reprise.code == 0 and reprise.statut == "terminee" and reprise.resume["pages"]["faites"] == 48
    assert sum(d.endswith("AN-000009") for d in pilote.demandes) == 1  # aucune page lue deux fois


def test_page_de_defi_de_l_arena_en_cours_de_passe_alerte(dossier, pilote):
    pilote.reponses["AN-000010"] = (200, PAGE_ARENA)
    p = fabriquer(dossier, pilote)
    bilan = p.lancer()
    assert bilan.code == 3 and bilan.arret["signe"] == "defi" and "arena" in bilan.arret["detail"]
    assert not any("AN-000011" in d for d in pilote.pages_lues())  # zéro requête ensuite
    assert pilote.relectures == 0 and p.horloge_factice.pauses == []  # aucun défi plus tard : pas d'attente
    texte = "\n".join(p.sortie_ecran)
    assert "ARRÊT" in texte and "défi" in texte
    etat = Etat(dossier / "etat.sqlite3")
    assert etat.pages(1, "a_faire") > 0 and etat.pages(1, "en_cours") == 0
    etat.fermer()
    assert lu(dossier)["statut"] == "arretee"


def test_page_de_defi_de_l_arena_vue_par_le_moteur_http(dossier, site):
    http = PiloteFactice(site)  # sans JavaScript
    http.reponses["AN-000010"] = (200, PAGE_ARENA)
    bilan = fabriquer(dossier, http).lancer()
    assert bilan.code == 3 and bilan.arret["signe"] == "defi"


def test_page_de_defi_d_un_fournisseur_en_cours_de_passe_alerte_sans_attente(dossier, pilote):
    pilote.reponses["AN-000010"] = (200, PAGE_FOURNISSEUR)
    p = fabriquer(dossier, pilote, texte=avec_porte())
    bilan = p.lancer()
    assert bilan.code == 3 and bilan.arret["signe"] == "defi"
    assert pilote.relectures == 0 and p.horloge_factice.pauses == []  # la porte d'entrée n'est que pour la 1re page


def test_un_cadre_de_captcha_sur_une_page_de_contenu_alerte(dossier, pilote):
    pilote.reponses["AN-000010"] = (200, '<html><body><div class="g-recaptcha" data-sitekey="x"></div></body></html>')
    bilan = fabriquer(dossier, pilote).lancer()
    assert bilan.code == 3 and bilan.arret["signe"] == "defi" and "recaptcha" in bilan.arret["detail"]


def test_un_defi_avec_statut_403_est_une_alerte_de_statut(dossier, pilote):
    pilote.reponses["AN-000010"] = (403, PAGE_FOURNISSEUR)
    bilan = fabriquer(dossier, pilote).lancer()
    assert bilan.code == 3 and bilan.arret["signe"] == "statut"


# --- Porte d'entrée : attente sans action, bornée --------------------------------------------


def test_defi_d_un_fournisseur_a_la_premiere_page_attente_sans_action_puis_arret(dossier, pilote):
    pilote.reponses["=/lab/vitrine/annonces"] = (200, PAGE_FOURNISSEUR)
    p = fabriquer(dossier, pilote, texte=avec_porte())
    bilan = p.lancer()
    assert bilan.code == 3 and bilan.statut == "arretee" and bilan.arret["signe"] == "defi"
    assert sum(p.horloge_factice.pauses) == pytest.approx(15)  # attendu 15 s, pas une de plus
    assert pilote.relectures == 15  # la page est relue sur place
    assert pilote.requetes_pages == 1  # aucune nouvelle requête, aucun rechargement, aucun clic
    assert "15" in bilan.arret["detail"]
    assert lu(dossier)["porte_entree"] == {"defi": "cloudflare", "franchie": False, "attente_s": 15.0}


def test_defi_qui_se_valide_seul_la_passe_continue_et_c_est_compte_a_part(dossier, pilote):
    pilote.reponses["=/lab/vitrine/annonces"] = (200, PAGE_FOURNISSEUR)
    vraie_liste = pilote.client.get("/lab/vitrine/annonces").text
    pilote.dom_apres_attente = [PAGE_FOURNISSEUR, PAGE_FOURNISSEUR, vraie_liste]
    p = fabriquer(dossier, pilote, texte=avec_porte())
    bilan = p.lancer()
    assert bilan.code == 0 and bilan.resume["pages"]["faites"] == 48
    assert pilote.relectures == 3 and sum(p.horloge_factice.pauses) == pytest.approx(3)
    assert bilan.resume["porte_entree"] == {"defi": "cloudflare", "franchie": True, "attente_s": 3.0}
    assert lu(dossier)["porte_entree"]["franchie"] is True


def test_sans_porte_entree_un_defi_a_la_premiere_page_est_une_alerte_immediate(dossier, pilote):
    pilote.reponses["=/lab/vitrine/annonces"] = (200, PAGE_FOURNISSEUR)
    p = fabriquer(dossier, pilote)
    bilan = p.lancer()
    assert bilan.code == 3 and bilan.arret["signe"] == "defi"
    assert pilote.relectures == 0 and p.horloge_factice.pauses == []
    assert lu(dossier)["porte_entree"] is None


def test_la_porte_d_entree_n_attend_pas_avec_un_moteur_sans_javascript(dossier, site):
    http = PiloteFactice(site)
    http.reponses["=/lab/vitrine/annonces"] = (200, PAGE_FOURNISSEUR)
    p = fabriquer(dossier, http, texte=avec_porte())
    bilan = p.lancer()
    assert bilan.code == 3 and bilan.arret["signe"] == "defi" and p.horloge_factice.pauses == []


def test_la_porte_d_entree_n_est_que_pour_la_premiere_page_de_la_passe(dossier, pilote):
    p = fabriquer(dossier, pilote, texte=avec_porte())
    p.options.pages_max = 2
    assert p.lancer().statut == "limitee"
    pilote.reponses["AN-000003"] = (200, PAGE_FOURNISSEUR)
    suite = fabriquer(dossier, pilote, texte=avec_porte())
    bilan = suite.reprendre(pages_max=10)
    assert bilan.code == 3 and bilan.arret["signe"] == "defi" and pilote.relectures == 0


# --- Les autres signes, avec un moteur de type navigateur ---------------------------------------


def test_requis_absent_trois_fois_de_suite_alerte(dossier, pilote):
    for n in (5, 6, 7):
        pilote.reponses[f"AN-00000{n}"] = (200, PAGE_VIDE)
    bilan = fabriquer(dossier, pilote).lancer()
    assert bilan.code == 3 and bilan.arret["signe"] == "page_non_conforme"
    assert not any("AN-000008" in d for d in pilote.pages_lues())


def test_un_404_la_passe_continue(dossier, pilote):
    pilote.reponses["AN-000005"] = (404, "<html><body>introuvable</body></html>")
    bilan = fabriquer(dossier, pilote).lancer()
    assert bilan.code == 0 and bilan.resume["pages"]["introuvables"] == 1 and bilan.resume["pages"]["faites"] == 48


def test_une_page_de_defi_ne_compte_pas_comme_page_lue(dossier, pilote):
    pilote.reponses["AN-000010"] = (200, PAGE_ARENA)
    bilan = fabriquer(dossier, pilote).lancer()
    assert bilan.resume["enregistrements"] == {"annonces": 9}  # les 9 fiches avant le défi, pas celle du défi


def test_message_d_alerte():
    assert "défi" in Alerte("defi", "page de défi (arena)", "http://127.0.0.1/a").message()
