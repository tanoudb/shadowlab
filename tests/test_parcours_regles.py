"""Règles du parcours sans réseau : rythme (cadence des requêtes) et sentinelle (signes d'alerte simples en HTTP)."""

import random

import pytest

from shadowlab.engines.noezia.recettes import RecetteInvalide, lire_texte
from shadowlab.engines.noezia.rythme import PRUDENT, Cadence, Rythme, rythme_de
from shadowlab.engines.noezia.sentinelle import Sentinelle

# --- Rythme ------------------------------------------------------------------------------------

BASE = """
recette: 1
nom: essai
autorisation: accord écrit de Exemple SA le 01/01/2026
hotes: [{hote}]
depart: [{{url: 'http://{hote}/a', type: p}}]
{rythme}
pages: {{p: {{url: '^/a$'}}}}
"""


def recette(hote="127.0.0.1", rythme=""):
    return lire_texte(BASE.format(hote=hote, rythme=rythme))


def test_rythme_par_defaut_libre_en_local_prudent_ailleurs():
    assert rythme_de(recette()) == Rythme()
    assert rythme_de(recette(hote="exemple.test")) == Rythme()  # .test est local
    assert rythme_de(recette(hote="exemple.fr")) == PRUDENT


def test_rythme_nomme_et_detaille():
    assert rythme_de(recette(rythme="rythme: prudent")) == PRUDENT
    assert rythme_de(recette(hote="exemple.fr", rythme="rythme: libre")) == Rythme()
    detail = rythme_de(
        recette(
            rythme="rythme: {delai_s: [1, 2, 5], pages_par_heure_max: 100,"
            " pause_longue: {minutes: [1, 2], toutes_les: [10, 20]}}"
        )
    )
    assert detail.delai_s == (1, 2, 5) and detail.pages_par_heure_max == 100
    assert detail.pause_minutes == (1, 2) and detail.pause_toutes_les == (10, 20)


def test_prudent_a_les_valeurs_du_document():
    assert PRUDENT.delai_s == (3, 8, 30)
    assert PRUDENT.pages_par_heure_max == 300
    assert PRUDENT.pause_minutes == (2, 5) and PRUDENT.pause_toutes_les == (40, 80)


@pytest.mark.parametrize(
    "rythme",
    [
        "rythme: {delai_s: [1, 2]}",
        "rythme: {delai_s: [5, 2, 1]}",
        "rythme: {delai_s: [0, -1, 2]}",
        "rythme: {pages_par_heure_max: 0}",
        "rythme: {pause_longue: {minutes: [3, 1], toutes_les: [10, 20]}}",
        "rythme: {pause_longue: {minutes: [1, 2]}}",
        "rythme: {vitesse: 3}",
    ],
)
def test_rythme_detaille_fautif_refuse(rythme):
    with pytest.raises(RecetteInvalide, match="rythme"):
        rythme_de(recette(rythme=rythme))


class Horloge:
    """Horloge factice : `dormir` fait avancer le temps."""

    def __init__(self):
        self.t = 1000.0
        self.pauses: list[float] = []

    def __call__(self):
        return self.t

    def dormir(self, secondes):
        self.pauses.append(secondes)
        self.t += secondes


def cadence(rythme, horloge, graine=1):
    return Cadence(rythme, random.Random(graine), horloge, horloge.dormir)


def test_libre_n_attend_jamais():
    h = Horloge()
    c = cadence(Rythme(), h)
    for _ in range(50):
        c.attendre()
    assert h.pauses == []


def test_la_premiere_page_part_tout_de_suite():
    h = Horloge()
    cadence(PRUDENT, h).attendre()
    assert h.pauses == []


def test_le_delai_compte_depuis_le_debut_de_la_page_precedente():
    h = Horloge()
    c = cadence(Rythme(delai_s=(8, 8, 8)), h)
    c.attendre()
    h.t += 3  # la page précédente a pris 3 s (chargement, gestes) : on n'attend que le reste
    c.attendre()
    assert h.pauses == [pytest.approx(5)]
    h.t += 20  # page plus longue que le délai : aucune attente en plus
    c.attendre()
    assert h.pauses == [pytest.approx(5)]


def test_delai_tire_entre_min_et_max_autour_de_la_mediane():
    h = Horloge()
    c = cadence(Rythme(delai_s=(3, 8, 30)), h)
    c.attendre()
    for _ in range(300):
        c.attendre()
    attentes = h.pauses
    assert all(3 - 1e-9 <= a <= 30 + 1e-9 for a in attentes)
    attentes.sort()
    assert 5 < attentes[len(attentes) // 2] < 12  # médiane proche de 8
    assert attentes[0] < 5 and attentes[-1] > 15  # la dispersion existe


def test_le_crawl_delay_s_applique_s_il_est_plus_long():
    h = Horloge()
    c = cadence(Rythme(), h)  # libre : le Crawl-delay est quand même appliqué
    c.attendre(crawl_delay=2)
    c.attendre(crawl_delay=2)
    assert h.pauses == [pytest.approx(2)]
    h = Horloge()
    c = cadence(Rythme(delai_s=(10, 10, 10)), h)
    c.attendre(crawl_delay=2)
    c.attendre(crawl_delay=2)
    assert h.pauses == [pytest.approx(10)]  # le délai du rythme est plus long


def test_pages_par_heure_max_fenetre_glissante():
    h = Horloge()
    c = cadence(Rythme(pages_par_heure_max=3), h)
    for _ in range(3):
        c.attendre()
        h.t += 1
    assert h.pauses == []  # 3 pages en 3 s : la fenêtre est pleine
    c.attendre()  # la 4e doit attendre que la 1re ait une heure
    assert h.pauses == [pytest.approx(3600 - 3)]


def test_pause_longue_apres_40_a_80_pages():
    h = Horloge()
    c = cadence(Rythme(pause_minutes=(2, 5), pause_toutes_les=(40, 80)), h)
    for _ in range(81):
        c.attendre()
    assert len(h.pauses) == 1  # une seule pause dans les 80 premières pages
    assert 120 <= h.pauses[0] <= 300
    for _ in range(80):
        c.attendre()
    assert len(h.pauses) == 2


# --- Sentinelle --------------------------------------------------------------------------------


def sentinelle():
    return Sentinelle(hotes=["127.0.0.1"])


def examiner(s, statut=200, adresse_finale="http://127.0.0.1/a", motif=True, type_page="fiche"):
    return s.examiner(
        type_page=type_page,
        adresse="http://127.0.0.1/a",
        statut=statut,
        adresse_finale=adresse_finale,
        dans_le_motif=motif,
    )


@pytest.mark.parametrize("statut", [401, 403, 407, 429, 503])
def test_statuts_d_alerte(statut):
    alerte = examiner(sentinelle(), statut=statut)
    assert alerte is not None and alerte.signe == "statut" and alerte.statut == statut
    assert str(statut) in alerte.message() and "http://127.0.0.1/a" in alerte.message()


@pytest.mark.parametrize("statut", [200, 404, 410, 500, 502, 504])
def test_autres_statuts_ne_declenchent_pas(statut):
    assert examiner(sentinelle(), statut=statut) is None


def test_redirection_vers_un_autre_hote():
    alerte = examiner(sentinelle(), adresse_finale="http://autre.example/connexion")
    assert alerte.signe == "hors_site" and "autre.example" in alerte.message()


def test_l_hote_compare_sans_casse_ni_port():
    assert examiner(sentinelle(), adresse_finale="http://127.0.0.1:8770/a") is None
    assert examiner(Sentinelle(hotes=["exemple.fr"]), adresse_finale="https://EXEMPLE.fr/a") is None


def test_adresse_finale_hors_du_motif_du_type():
    alerte = examiner(sentinelle(), motif=False, adresse_finale="http://127.0.0.1/connexion")
    assert alerte.signe == "hors_motif"


def test_trois_pages_de_suite_sans_requis_meme_type():
    s = sentinelle()
    assert s.noter("fiche", "anormale") is None
    assert s.noter("fiche", "anormale") is None
    alerte = s.noter("fiche", "anormale")
    assert alerte is not None and alerte.signe == "page_non_conforme" and "fiche" in alerte.message()


def test_une_page_conforme_remet_le_compte_a_zero_pour_son_type():
    s = sentinelle()
    s.noter("fiche", "anormale")
    s.noter("fiche", "anormale")
    s.noter("liste", "anormale")  # un autre type compte à part
    assert s.noter("fiche", "ok") is None
    assert s.noter("fiche", "anormale") is None
    assert s.noter("fiche", "anormale") is None


def test_une_page_isolee_et_un_404_ne_declenchent_pas():
    s = sentinelle()
    assert s.noter("fiche", "anormale") is None
    assert s.noter("fiche", "introuvable") is None
    assert s.noter("fiche", "ok") is None


def test_plus_de_5_echecs_sur_les_20_dernieres_pages():
    s = sentinelle()
    for _ in range(5):
        assert s.noter("fiche", "echec") is None
    alerte = s.noter("fiche", "echec")
    assert alerte.signe == "echecs"


def test_les_echecs_sortent_de_la_fenetre_de_20():
    s = sentinelle()
    for _ in range(5):
        s.noter("fiche", "echec")
    for _ in range(20):
        assert s.noter("fiche", "ok") is None
    for _ in range(5):
        assert s.noter("fiche", "echec") is None  # les 5 premiers sont sortis de la fenêtre


def test_rejouer_l_historique_a_la_reprise():
    historique = [
        {"type": "fiche", "decision": "anormale"},
        {"type": "fiche", "decision": "anormale"},
    ]
    s = sentinelle()
    s.rejouer(historique)
    assert s.noter("fiche", "anormale").signe == "page_non_conforme"
