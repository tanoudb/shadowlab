"""Ordonnanceur des visites (I5, étape 2.7, § 5.4 de la conception) : temps simulé, aucune attente réelle."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from statistics import median

import pytest

from shadowlab.engines.noezia import rythme
from shadowlab.engines.noezia.visites import Ordonnanceur, Reglages

LUNDI_7H = datetime(2026, 11, 16, 7, 0, 0)  # heure du poste, sans fuseau : l'ordonnanceur lit l'heure telle quelle


class Horloge:
    """Temps simulé : `dormir` avance l'horloge, rien n'attend pour de vrai."""

    def __init__(self, depart: datetime = LUNDI_7H) -> None:
        self.t = depart
        self.sommeils: list[float] = []

    def maintenant(self) -> datetime:
        return self.t

    def dormir(self, secondes: float) -> None:
        self.sommeils.append(secondes)
        self.t += timedelta(seconds=secondes)

    def avancer(self, secondes: float) -> None:
        self.t += timedelta(seconds=secondes)


def simuler(jours: int = 7, graine: int = 0, depart: datetime = LUNDI_7H, reglages: Reglages | None = None):
    """Rend les visites faites : (debut, fin, pages). Une page dure 5 à 20 s (`prudent` : 8 s en médiane)."""
    h = Horloge(depart)
    o = Ordonnanceur(reglages or Reglages(), random.Random(graine), h.maintenant, h.dormir)
    duree = random.Random(graine + 1000)
    faites = []
    limite = depart + timedelta(days=jours)
    while True:
        v = o.attendre_prochaine()
        if h.t >= limite:
            break
        assert h.t == v.debut  # l'ordonnanceur a dormi jusqu'à l'heure annoncée
        lues = v.pages
        h.avancer(sum(duree.uniform(5, 20) for _ in range(lues)))
        o.terminer(v, lues)
        faites.append((v.debut, h.t, lues))
    return faites


GRAINES = range(6)


@pytest.mark.parametrize("graine", GRAINES)
def test_sept_jours_aucune_visite_hors_plage(graine):
    faites = simuler(graine=graine)
    assert len(faites) > 30
    for debut, fin, _ in faites:
        assert debut.date() == fin.date()
        assert debut.time() >= datetime(2026, 1, 1, 8).time(), debut
        assert fin.time() <= datetime(2026, 1, 1, 23).time(), fin


@pytest.mark.parametrize("graine", GRAINES)
def test_sept_jours_aucun_ecart_sous_45_minutes(graine):
    faites = simuler(graine=graine)
    for (_, fin, _), (debut, _, _) in zip(faites, faites[1:], strict=False):
        assert debut - fin >= timedelta(minutes=45), (fin, debut)


@pytest.mark.parametrize("graine", GRAINES)
def test_sept_jours_au_plus_200_pages_par_jour_et_120_par_heure(graine):
    faites = simuler(graine=graine)
    par_jour: dict = {}
    pages_vues: list[datetime] = []
    for debut, fin, pages in faites:
        par_jour[debut.date()] = par_jour.get(debut.date(), 0) + pages
        pas = (fin - debut) / max(pages, 1)
        pages_vues += [debut + pas * i for i in range(pages)]  # les pages réparties sur la durée de la visite
    assert max(par_jour.values()) <= 200
    for i, t in enumerate(pages_vues):
        assert sum(1 for u in pages_vues[i:] if u - t < timedelta(hours=1)) <= 120


@pytest.mark.parametrize("graine", GRAINES)
def test_pages_par_visite_de_5_a_40(graine):
    pages = [p for _, _, p in simuler(graine=graine)]
    assert min(pages) >= 5 and max(pages) <= 40


def test_ordre_de_grandeur_dix_visites_par_jour_ecart_median_90_minutes():
    faites = simuler(jours=30, graine=3)
    jours = {d.date() for d, _, _ in faites}
    moyenne = len(faites) / len(jours)
    assert 5 <= moyenne <= 14, moyenne
    ecarts = [
        (d - f).total_seconds() / 60
        for (_, f, _), (d, _, _) in zip(faites, faites[1:], strict=False)
        if d.date() == f.date()
    ]
    assert 60 <= median(ecarts) <= 125, median(ecarts)
    assert max(ecarts) <= 180 + 1


def test_jamais_a_heure_fixe():
    faites = simuler(jours=14, graine=4)
    minutes = {d.hour * 60 + d.minute for d, _, _ in faites}
    assert len(minutes) >= 60
    premieres = {d.hour * 60 + d.minute for d, _, _ in faites if d.hour < 11}
    assert len(premieres) >= 8  # la première visite du matin non plus


def test_meme_graine_meme_planning_graines_differentes_plannings_differents():
    assert simuler(graine=1) == simuler(graine=1)
    assert simuler(graine=1) != simuler(graine=2)


def test_depart_la_nuit_premiere_visite_apres_8_heures():
    h = Horloge(datetime(2026, 11, 16, 3, 0))
    o = Ordonnanceur(Reglages(), random.Random(0), h.maintenant, h.dormir)
    v = o.attendre_prochaine()
    assert v.debut.date() == datetime(2026, 11, 16).date() and v.debut.hour >= 8
    assert sum(h.sommeils) >= 5 * 3600


@pytest.mark.parametrize("heure", [(22, 50), (23, 30)])
def test_depart_trop_tard_la_visite_est_le_lendemain(heure):
    h = Horloge(datetime(2026, 11, 16, *heure))  # une visite lancée à 22 h 50 finirait après 23 h
    o = Ordonnanceur(Reglages(), random.Random(0), h.maintenant, h.dormir)
    v = o.attendre_prochaine()
    assert v.debut.date() == datetime(2026, 11, 17).date() and v.debut.hour >= 8


def test_la_visite_prend_la_fin_reelle_pour_l_ecart():
    h = Horloge(datetime(2026, 11, 16, 9, 0))
    o = Ordonnanceur(Reglages(), random.Random(0), h.maintenant, h.dormir)
    v = o.attendre_prochaine()
    h.avancer(25 * 60)  # une visite longue
    o.terminer(v, v.pages)
    suivante = o.prochaine()
    assert suivante.debut - h.t >= timedelta(minutes=45)


def test_plafond_par_jour_borne_les_pages_puis_remet_au_lendemain():
    reglages = Reglages(pages_par_jour=30, ecart_min_min=1, ecart_med_min=2, ecart_max_min=5)
    faites = simuler(jours=3, graine=0, reglages=reglages)
    par_jour: dict = {}
    for debut, _, pages in faites:
        par_jour[debut.date()] = par_jour.get(debut.date(), 0) + pages
    assert len(par_jour) == 3 and max(par_jour.values()) <= 30
    assert min(par_jour.values()) >= 25  # le budget est bien consommé avant de s'arrêter


def test_plafond_par_heure_borne_les_pages_ou_repousse_la_visite():
    reglages = Reglages(pages_par_heure=20, pages_par_jour=1000, ecart_min_min=1, ecart_med_min=2, ecart_max_min=5)
    faites = simuler(jours=2, graine=1, reglages=reglages)
    pages_vues = []
    for debut, fin, pages in faites:
        pas = (fin - debut) / max(pages, 1)
        pages_vues += [debut + pas * i for i in range(pages)]
    assert len(faites) > 10
    for i, t in enumerate(pages_vues):
        assert sum(1 for u in pages_vues[i:] if u - t < timedelta(hours=1)) <= 20


def test_reprise_apres_coupure_l_historique_compte():
    h = Horloge(datetime(2026, 11, 16, 15, 0))
    o = Ordonnanceur(Reglages(), random.Random(0), h.maintenant, h.dormir)
    o.rejouer(
        [(datetime(2026, 11, 16, 12, 0), datetime(2026, 11, 16, 12, 10), 195), (datetime(2026, 11, 16, 14, 40), h.t, 0)]
    )
    v = o.prochaine()
    assert v.debut - h.t >= timedelta(minutes=45)  # l'écart compte depuis la fin de la dernière visite rejouée
    if v.debut.date() == h.t.date():
        assert v.pages <= 5  # il ne reste que 5 pages au budget du jour
    else:
        assert v.debut.hour >= 8


def test_le_rythme_dans_une_visite_est_le_rythme_prudent_existant():
    assert Reglages().rythme_visite is rythme.PRUDENT


@pytest.mark.parametrize(
    "reglage",
    [
        {"plage": (23, 8)},
        {"ecart_min_min": 100, "ecart_med_min": 90},
        {"pages_min": 50},
        {"pages_par_heure": 0},
    ],
)
def test_reglages_incoherents_refuses(reglage):
    with pytest.raises(ValueError):
        Reglages(**reglage)
