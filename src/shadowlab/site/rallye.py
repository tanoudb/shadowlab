"""Second site à contenu connu : résultats de rallye fictifs (arbre de pages et tableaux).

Pendant de `vitrine.py` : tout le contenu est déterministe (même graine et même taille = mêmes données),
et `verite()` exporte ce qu'une récolte complète doit retrouver, collection par collection, avec la liste
des pages attendues. Le HTML est celui d'un site ordinaire : aucun attribut `data-champ`, des tableaux
dont les colonnes se lisent par leur en-tête, des liens à suivre pour descendre l'arbre.

    saisons → calendrier d'une saison (paginé) → rallye → spéciales (temps), classement, engagés
                                                                  → châssis (historique), pilotes

Tout est inventé : rallyes, lieux, spéciales, pilotes et copilotes (noms fabriqués, jamais une personne
réelle), marques et modèles de voiture génériques (« démo »), numéros de châssis en `DEMO-XXX-0000`.
Aucune marque de site de résultats.

Pièges voulus (ceux d'un vrai site de résultats), listés dans `PIEGES`. Un test vérifie que chacun est
présent, dès que le site compte deux saisons (9 rallyes) :
temps à minutes et à heures, abandons sans temps, ex aequo, spéciale annulée sans tableau, colonnes dans
un autre ordre, pilote et copilote dans une même cellule, châssis qui passe de pilote en pilote et de
saison en saison, noms à accents et à apostrophes.
"""

# ruff: noqa: E501  (gabarits HTML : lignes longues voulues, un balisage par ligne)
from __future__ import annotations

import random
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from html import escape

from .pages import HONEYPOT_LIEN

MARQUE = "Chrono Démo"  # nom manifestement fictif
ARIANE = "Fil d'Ariane"
ANNEE_DEPART = 2023  # première saison
RALLYES_PAR_SAISON = 8
PAR_PAGE = 6  # rallyes par page du calendrier : la pagination sert
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre"]
MOIS += ["novembre", "décembre"]

# --- Données de base (toutes inventées) --------------------------------------------------------

# (nom du championnat, surfaces possibles des rallyes qui en font partie)
CHAMPIONNATS = [
    ("Coupe Démo Asphalte", ("Asphalte",)),
    ("Trophée Fictif Terre et Neige", ("Terre", "Neige")),
    ("Challenge Imaginaire Mixte", ("Mixte", "Terre")),
]
# minutes par kilomètre chronométré selon la surface (≈ 97, 83, 70 et 88 km/h)
ALLURE = {"Asphalte": 0.62, "Terre": 0.72, "Neige": 0.85, "Mixte": 0.68}
SURFACES_CSS = {"Asphalte": "asphalte", "Terre": "terre", "Neige": "neige", "Mixte": "mixte"}
# (formule du nom du rallye, commune, région)
LIEUX = [
    ("du Val-d'Ombre", "Val-d'Ombre", "Haute-Brume"),
    ("de l'Écureuil Fictif", "L'Écureuil-sur-Faux", "Pays d'Ardoise"),
    ("des Mille Girofles", "Girofle-les-Mirages", "Bas-Mirage"),
    ("du Cormoran Imaginaire", "Port-Cormoran", "Val-Fictif"),
    ("de la Lanterne Démo", "Saint-Lanternat", "Haute-Brume"),
    ("d'Aubépine-Factice", "Aubépine-Factice", "Pays d'Ardoise"),
    ("des Hérons d'Ardoise", "Héron-le-Vieux", "Bas-Mirage"),
    ("du Crépuscule", "Crépuscule-des-Fables", "Val-Fictif"),
    ("de l'Étang Inventé", "Étang-Inventé", "Haute-Brume"),
    ("du Mont-Quartz Démo", "Mont-Quartz", "Pays d'Ardoise"),
    ("des Brumes d'Orfeuil", "Orfeuil-en-Brume", "Bas-Mirage"),
    ("de l'Oubli", "Oubli-sur-Écho", "Val-Fictif"),
]
SPECIALES_NOMS = [
    "Col de la Brume",
    "Gorges du Faux-Pas",
    "Bois de l'Ours Fictif",
    "Plateau des Mirages",
    "Descente d'Orfeuil",
    "Vallon Imaginaire",
    "Les Lacets d'Ardoise",
    "Crête du Cormoran",
    "Pont de l'Écho",
    "Forêt des Girofles",
    "Moulin d'Ombre",
    "Route de l'Aubépine",
    "Bosquet du Crépuscule",
    "Cirque de la Lanterne",
    "Sentier des Hérons Démo",
    "Côte de l'Oubli",
]
GROUPES = ["Élite", "Challenger", "Découverte"]
POIDS_GROUPES = [2, 4, 5]
PAYS = ["France", "Belgique", "Finlande", "Estonie", "Italie", "Espagne", "Suisse", "Norvège", "Portugal"]
PRENOMS = [
    "Aurélien", "Léa", "Mathis", "Inès", "Noël", "Élodie", "Lucas", "Zoé", "Gaëtan", "Océane",
    "Théo", "Maëlle", "Hugo", "Chloé", "Loïc", "Rémi", "Anaïs", "Jérémie", "Soline", "Ewen",
    "Margaux", "Timéo", "Camille", "Yann", "Ilona", "Baptiste", "Éloïse", "Axel", "Nolwenn", "Dorian",
]  # fmt: skip
NOMS = [
    "Vaudrelle", "d'Estrelle", "Montbrisé", "Tarnoval", "Cassevigne", "L'Hostal-Fictif", "Rochebrune-Démo",
    "Aubrac-Factice", "O'Marnie", "Quenelvaux", "Dufaux-Imaginaire", "Bellerive-Démo", "Saint-Orme-Fictif",
    "d'Ardoisier", "Mirevaux", "Lanternois", "Poivrelle", "Grésilly", "Fontevrelle", "N'Dorval-Démo",
    "Brumaillet", "Escarbille", "d'Orfeuillet", "Valcrépin", "Hérondelle", "Girofleur-Factice", "Ombrevie",
    "Cormorand", "Pierrefaux", "L'Étournel",
]  # fmt: skip
# (marque, sigle du code de châssis) et modèles génériques
MARQUES = [
    ("Arvane", "ARV"), ("Kestrel", "KES"), ("Marmotte", "MAR"), ("Vélocia", "VEL"),
    ("Orage", "ORA"), ("Girofle", "GIR"), ("Cormoran", "COR"), ("Balise", "BAL"),
]  # fmt: skip
MODELES = [
    "Berline R5 démo",
    "Compacte T3 démo",
    "Coupé GT démo",
    "Break X7 démo",
    "Citadine C2 démo",
    "Tourisme S4 démo",
]

# --- En-têtes des tableaux (fixés ici : le HTML et les tests lisent la même liste) --------------

COLONNES_CALENDRIER = ["Date", "Rallye", "Championnat", "Surface", "Lieu"]
COLONNES_SPECIALES = ["ES", "Spéciale", "Longueur", "Départ", "Statut"]
COLONNES_TEMPS = ["Pos.", "N°", "Équipage", "Voiture", "Temps", "Écart"]
COLONNES_CLASSEMENT = ["Pos.", "N°", "Équipage", "Groupe", "Voiture", "Temps total", "Écart"]
COLONNES_ENGAGES = ["N°", "Pilote", "Copilote", "Voiture", "Châssis", "Groupe"]
COLONNES_HISTORIQUE = ["Date", "Rallye", "Pilote", "Résultat"]
COLONNES_ENGAGEMENTS = ["Date", "Rallye", "N°", "Châssis", "Résultat"]

PIEGES = {
    "temps_a_minutes": "temps de spéciale à minutes (« 9:58.7 »)",
    "temps_a_heures": "temps total à heures (« 1:02:03.4 ») à côté de totaux à minutes",
    "abandon_sans_temps": "abandons sans temps : « Abandon » et rang « - » dans la spéciale, « Ab. » et « - » au classement",
    "ex_aequo": "ex aequo : même temps et même rang (le rang suivant saute)",
    "speciale_annulee_sans_tableau": "spéciale annulée : un titre et un avis, aucun tableau",
    "colonnes_dans_un_autre_ordre": "mêmes colonnes dans un autre ordre entre le tableau des temps et le classement",
    "equipage_dans_une_cellule": "pilote et copilote dans une même cellule de tableau",
    "chassis_de_pilote_en_pilote_et_de_saison_en_saison": "un châssis passe de pilote en pilote et de saison en saison",
    "noms_a_apostrophes": "noms de rallyes, de spéciales et de pilotes à apostrophes",
    "noms_accentues": "noms à accents (é, è, ô, ï, ç…)",
}


# --- Modèle ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Pilote:
    id: int
    nom: str
    nationalite: str


@dataclass(frozen=True)
class Chassis:
    code: str
    marque: str
    modele: str
    annee: int

    @property
    def voiture(self) -> str:
        return f"{self.marque} {self.modele}"


@dataclass(frozen=True)
class Rallye:
    id: int
    nom: str
    saison: int
    date_debut: str
    date_fin: str
    championnat: str
    surface: str
    lieu: str
    km_chrono: float


@dataclass(frozen=True)
class Speciale:
    id: int
    rallye: int
    numero: int
    nom: str
    km: float
    depart: str  # AAAA-MM-JJThh:mm
    annulee: bool


@dataclass(frozen=True)
class Engage:
    rallye: int
    numero: int
    pilote_id: int
    copilote: str
    chassis: str  # code du châssis
    groupe: str


@dataclass(frozen=True)
class Temps:
    speciale: int
    numero: int
    rang: int | None  # None : abandon
    temps_ms: int | None


@dataclass(frozen=True)
class Classement:
    rallye: int
    numero: int
    rang: int | None  # None : abandon
    temps_total_ms: int | None


@dataclass(frozen=True)
class Passage:
    """Un passage d'un châssis dans un rallye (une ligne de son historique)."""

    chassis: str
    rallye: int
    date: str
    pilote_id: int
    resultat: str


class Univers:
    """Tout le contenu du site, avec les index utiles aux pages. Construit par `construire()`."""

    def __init__(self, rallyes, speciales, engages, temps, classements, chassis, pilotes, historique):
        self.rallyes: tuple[Rallye, ...] = tuple(rallyes)
        self.speciales: tuple[Speciale, ...] = tuple(speciales)
        self.engages: tuple[Engage, ...] = tuple(engages)
        self.temps: tuple[Temps, ...] = tuple(temps)
        self.classements: tuple[Classement, ...] = tuple(classements)
        self.chassis: tuple[Chassis, ...] = tuple(chassis)
        self.pilotes: tuple[Pilote, ...] = tuple(pilotes)
        self.historique: tuple[Passage, ...] = tuple(historique)
        self.saisons: tuple[int, ...] = tuple(sorted({r.saison for r in self.rallyes}))
        self._rallye = {r.id: r for r in self.rallyes}
        self._speciale = {s.id: s for s in self.speciales}
        self._chassis = {c.code: c for c in self.chassis}
        self._pilote = {p.id: p for p in self.pilotes}
        self._engage = {(e.rallye, e.numero): e for e in self.engages}
        self._classement = {(c.rallye, c.numero): c for c in self.classements}
        self._de_la_saison: dict[int, list[Rallye]] = defaultdict(list)
        for r in self.rallyes:
            self._de_la_saison[r.saison].append(r)
        self._speciales_de: dict[int, list[Speciale]] = defaultdict(list)
        for s in self.speciales:
            self._speciales_de[s.rallye].append(s)
        self._engages_de: dict[int, list[Engage]] = defaultdict(list)
        for e in self.engages:
            self._engages_de[e.rallye].append(e)
        self._temps_de: dict[int, list[Temps]] = defaultdict(list)
        for t in self.temps:
            self._temps_de[t.speciale].append(t)
        self._classement_de: dict[int, list[Classement]] = defaultdict(list)
        for c in self.classements:
            self._classement_de[c.rallye].append(c)
        self._historique_de: dict[str, list[Passage]] = defaultdict(list)
        for h in self.historique:
            self._historique_de[h.chassis].append(h)
        self._engagements_de: dict[int, list[Engage]] = defaultdict(list)
        for e in self.engages:
            self._engagements_de[e.pilote_id].append(e)

    def trouver_rallye(self, id_rallye: int) -> Rallye | None:
        return self._rallye.get(id_rallye)

    def trouver_speciale(self, id_speciale: int) -> Speciale | None:
        return self._speciale.get(id_speciale)

    def trouver_chassis(self, code: str) -> Chassis | None:
        return self._chassis.get(code)

    def trouver_pilote(self, id_pilote: int) -> Pilote | None:
        return self._pilote.get(id_pilote)

    def engage(self, id_rallye: int, numero: int) -> Engage:
        return self._engage[(id_rallye, numero)]

    def resultat(self, id_rallye: int, numero: int) -> Classement:
        return self._classement[(id_rallye, numero)]

    def rallyes_de(self, saison: int) -> list[Rallye]:
        return list(self._de_la_saison.get(saison, ()))

    def speciales_de(self, id_rallye: int) -> list[Speciale]:
        return list(self._speciales_de.get(id_rallye, ()))

    def engages_de(self, id_rallye: int) -> list[Engage]:
        return list(self._engages_de.get(id_rallye, ()))

    def temps_de(self, id_speciale: int) -> list[Temps]:
        return list(self._temps_de.get(id_speciale, ()))

    def classement_de(self, id_rallye: int) -> list[Classement]:
        return list(self._classement_de.get(id_rallye, ()))

    def historique_de(self, code: str) -> list[Passage]:
        return list(self._historique_de.get(code, ()))

    def engagements_de(self, id_pilote: int) -> list[Engage]:
        return list(self._engagements_de.get(id_pilote, ()))

    def nb_pages_calendrier(self, saison: int) -> int:
        return max(1, -(-len(self._de_la_saison.get(saison, ())) // PAR_PAGE))

    def voiture(self, e: Engage) -> str:
        return self._chassis[e.chassis].voiture


# --- Génération --------------------------------------------------------------------------------


def _nom_personne(alea: random.Random) -> str:
    return f"{alea.choice(PRENOMS)} {alea.choice(NOMS)}"


def _pilote(graine: int, j: int) -> Pilote:
    """Pilote n° `j` : sa propre graine. Le n° 1 est fixé (accent et apostrophe garantis)."""
    if j == 1:
        return Pilote(1, "Aurélien d'Estrelle", "France")
    alea = random.Random(graine * 999_983 + j)
    return Pilote(j, _nom_personne(alea), alea.choice(PAYS))


def _chassis(graine: int, j: int) -> Chassis:
    """Châssis n° `j` de la réserve commune, à code manifestement fictif."""
    alea = random.Random(graine * 104_729 + j)
    marque, sigle = alea.choice(MARQUES)
    return Chassis(f"DEMO-{sigle}-{j:04d}", marque, alea.choice(MODELES), alea.randint(2012, 2022))


def _rangs(valeurs: list[int | None]) -> list[int | None]:
    """Rang « à la compétition » (1, 2, 2, 4) ; une valeur absente n'a pas de rang."""
    return [None if v is None else 1 + sum(1 for w in valeurs if w is not None and w < v) for v in valeurs]


def _en_tete(liste: list[int], valeur: int) -> None:
    """Met `valeur` en première place sans doublon ni changement de longueur."""
    if valeur in liste:
        k = liste.index(valeur)
        liste[0], liste[k] = liste[k], liste[0]
    else:
        liste[0] = valeur


def _plan_speciales(alea: random.Random, i: int) -> tuple[list[str], list[float], set[int]]:
    """Noms, longueurs et spéciales annulées du rallye n° `i`.

    Un rallye sur quatre est court (4 spéciales de 4 à 9 km : total sous l'heure), un autre long (8 à 10
    spéciales de 14 à 28 km : total au-delà de l'heure) ; un sur cinq voit sa spéciale 2 annulée.
    """
    if i % 4 == 1:
        n, bornes = 4, (4.0, 9.0)
    elif i % 4 == 3:
        n, bornes = alea.randint(8, 10), (14.0, 28.0)
    else:
        n, bornes = alea.randint(4, 10), (5.0, 26.0)
    noms = alea.sample(SPECIALES_NOMS, n)
    kms = [round(alea.uniform(*bornes), 1) for _ in range(n)]
    annulees = {s for s in range(2, n + 1) if alea.random() < 0.04}  # la première spéciale n'est jamais annulée
    if i % 5 == 2:
        annulees.add(2)
    while len(annulees) > n - 2:  # au moins deux spéciales disputées
        annulees.discard(max(annulees))
    return noms, kms, annulees


def _departs(debut: date, nb_jours: int, n: int) -> list[str]:
    """Heures de départ : les spéciales réparties sur les jours du rallye, la première à 8 h 30."""
    jours = [(s - 1) * nb_jours // n for s in range(1, n + 1)]
    departs = []
    for s in range(n):
        jour = debut + timedelta(days=jours[s])
        heure = datetime(jour.year, jour.month, jour.day, 8, 30) + timedelta(minutes=55 * jours[:s].count(jours[s]))
        departs.append(heure.strftime("%Y-%m-%dT%H:%M"))
    return departs


def ordinal(rang: int) -> str:
    return "1er" if rang == 1 else f"{rang}e"


@lru_cache(maxsize=8)
def construire(graine: int, taille: int) -> Univers:
    """Les `taille` rallyes de la graine (8 par saison), toujours identiques pour les mêmes arguments.

    Chaque rallye a sa propre graine ; les engagés se tirent dans une réserve de pilotes et de châssis
    qui s'agrandit de 4 à chaque rallye (14 + 4 × n° du rallye) : un châssis revient de rallye en rallye,
    avec un autre pilote. Seuls les pilotes et les châssis réellement engagés ont une page.
    """
    rallyes, speciales, engages, temps, classements, historique = [], [], [], [], [], []
    pilotes_vus: dict[int, Pilote] = {}
    chassis_vus: dict[int, Chassis] = {}
    id_speciale = 0

    for i in range(1, taille + 1):
        alea = random.Random(graine * 1_000_003 + i)
        saison = ANNEE_DEPART + (i - 1) // RALLYES_PAR_SAISON
        rang_saison = (i - 1) % RALLYES_PAR_SAISON
        ordre_lieux = random.Random(graine * 7_919 + saison).sample(range(len(LIEUX)), RALLYES_PAR_SAISON)
        formule, commune, region = LIEUX[ordre_lieux[rang_saison]]
        championnat, surfaces = alea.choice(CHAMPIONNATS)
        surface = alea.choice(surfaces)
        debut = date(saison, 2, 15) + timedelta(days=rang_saison * 36 + alea.randint(0, 12))
        nb_jours = alea.choice((2, 3))
        fin = debut + timedelta(days=nb_jours - 1)

        # Spéciales.
        noms, kms, annulees = _plan_speciales(alea, i)
        n_spe = len(noms)
        departs = _departs(debut, nb_jours, n_spe)
        ids_speciales = [id_speciale + s for s in range(1, n_spe + 1)]
        id_speciale += n_spe
        for s in range(1, n_spe + 1):
            speciales.append(
                Speciale(ids_speciales[s - 1], i, s, noms[s - 1], kms[s - 1], departs[s - 1], s in annulees)
            )
        km_chrono = round(sum(round(kms[s - 1] * 10) for s in range(1, n_spe + 1) if s not in annulees) / 10, 1)
        rallyes.append(
            Rallye(
                i,
                f"Rallye {formule} {saison}",
                saison,
                debut.isoformat(),
                fin.isoformat(),
                championnat,
                surface,
                f"{commune} ({region})",
                km_chrono,
            )
        )

        # Engagés : le châssis n° 1 est toujours engagé (en tête de liste) avec un pilote qui change.
        disponibles = 14 + 4 * i
        n_eng = min(alea.randint(12, 30), disponibles)
        ids_pilotes = alea.sample(range(1, disponibles + 1), n_eng)
        ids_chassis = alea.sample(range(1, disponibles + 1), n_eng)
        _en_tete(ids_pilotes, (i - 1) % 5 + 1)
        _en_tete(ids_chassis, 1)
        numeros = sorted(alea.sample(range(1, 100), n_eng))
        facteurs = [alea.uniform(1.0, 1.10) for _ in range(n_eng)]
        for e in range(n_eng):
            pilotes_vus.setdefault(ids_pilotes[e], _pilote(graine, ids_pilotes[e]))
            chassis_vus.setdefault(ids_chassis[e], _chassis(graine, ids_chassis[e]))
            engages.append(
                Engage(
                    i,
                    numeros[e],
                    ids_pilotes[e],
                    _nom_personne(alea),
                    chassis_vus[ids_chassis[e]].code,
                    alea.choices(GROUPES, weights=POIDS_GROUPES)[0],
                )
            )

        # Abandons : à partir de la spéciale 2, jamais sur une spéciale annulée.
        possibles = [s for s in range(2, n_spe + 1) if s not in annulees]
        abandon: list[int | None] = [alea.choice(possibles) if alea.random() < 0.10 else None for _ in range(n_eng)]
        if i % 2 == 1 and all(a is None for a in abandon):
            abandon[1] = possibles[0]

        # Temps de spéciale. Un équipage figure dans le tableau jusqu'à sa spéciale d'abandon incluse.
        pas = ALLURE[surface] * 60_000
        par_speciale: dict[int, dict[int, int | None]] = {}
        for s in range(1, n_spe + 1):
            if s in annulees:
                continue
            en_course = [e for e in range(n_eng) if abandon[e] is None or s <= abandon[e]]
            ms: dict[int, int | None] = {}
            for e in en_course:
                if abandon[e] == s:
                    ms[e] = None
                else:
                    ms[e] = round(kms[s - 1] * pas * facteurs[e] * alea.uniform(0.97, 1.03) / 100) * 100
            if s == 1:
                ms[4] = ms[3]  # ex aequo : les 4e et 5e engagés font le même temps sur la première spéciale
            par_speciale[s] = ms
            ordre = sorted(en_course, key=lambda e, ms=ms: (ms[e] is None, ms[e] or 0, numeros[e]))
            for e, rang in zip(ordre, _rangs([ms[e] for e in ordre]), strict=True):
                temps.append(Temps(ids_speciales[s - 1], numeros[e], rang, ms[e]))

        # Classement final : les équipages qui ont tout couru, puis les abandons dans l'ordre des numéros.
        totaux = {e: sum(par_speciale[s][e] for s in par_speciale) for e in range(n_eng) if abandon[e] is None}
        classes = sorted(totaux, key=lambda e, t=totaux: (t[e], numeros[e]))
        rang_de = dict(zip(classes, _rangs([totaux[e] for e in classes]), strict=True))
        for e in classes:
            classements.append(Classement(i, numeros[e], rang_de[e], totaux[e]))
        for e in range(n_eng):
            if abandon[e] is not None:
                classements.append(Classement(i, numeros[e], None, None))
            code = chassis_vus[ids_chassis[e]].code
            resultat = "Abandon" if abandon[e] is not None else ordinal(rang_de[e])
            historique.append(Passage(code, i, debut.isoformat(), ids_pilotes[e], resultat))

    historique.sort(key=lambda h: (h.chassis, h.date, h.rallye))
    return Univers(
        rallyes,
        speciales,
        engages,
        temps,
        classements,
        sorted(chassis_vus.values(), key=lambda c: c.code),
        sorted(pilotes_vus.values(), key=lambda p: p.id),
        historique,
    )


# --- Adresses ----------------------------------------------------------------------------------


def adresse_saisons() -> str:
    return "/lab/rallye/saisons"


def adresse_saison(saison: int, page: int = 1) -> str:
    return f"/lab/rallye/saisons/{saison}" + (f"?page={page}" if page > 1 else "")


def adresse_rallye(id_rallye: int) -> str:
    return f"/lab/rallye/rallyes/{id_rallye}"


def adresse_classement(id_rallye: int) -> str:
    return f"/lab/rallye/rallyes/{id_rallye}/classement"


def adresse_engages(id_rallye: int) -> str:
    return f"/lab/rallye/rallyes/{id_rallye}/engages"


def adresse_speciale(id_speciale: int) -> str:
    return f"/lab/rallye/speciales/{id_speciale}"


def adresse_chassis(code: str) -> str:
    return f"/lab/rallye/chassis/{code}"


def adresse_pilote(id_pilote: int) -> str:
    return f"/lab/rallye/pilotes/{id_pilote}"


RE_IDENTIFIANT = re.compile(r"^[1-9]\d{0,8}$")
RE_SAISON = re.compile(r"^\d{4}$")
RE_CODE_CHASSIS = re.compile(r"^DEMO-[A-Z]{3}-\d{4}$")


def lire_identifiant(texte: str) -> int | None:
    """Identifiant numérique d'une adresse, ou None si ce n'en est pas un (la route répond alors 404)."""
    return int(texte) if RE_IDENTIFIANT.match(texte) else None


def lire_saison(texte: str) -> int | None:
    return int(texte) if RE_SAISON.match(texte) else None


# --- Vérité ------------------------------------------------------------------------------------


def duree(ms: int) -> str:
    """Temps affiché : « 9:58.7 » sous l'heure, « 1:02:03.4 » au-delà (au dixième de seconde)."""
    dixiemes = round(ms / 100)
    heures, dixiemes = divmod(dixiemes, 36_000)
    minutes, dixiemes = divmod(dixiemes, 600)
    secondes, dixieme = divmod(dixiemes, 10)
    if heures:
        return f"{heures}:{minutes:02d}:{secondes:02d}.{dixieme}"
    return f"{minutes}:{secondes:02d}.{dixieme}"


def ecart(ms: int) -> str:
    return f"+{duree(ms)}"


def pages_attendues(graine: int, taille: int) -> list[dict]:
    """Les pages d'une récolte complète, depuis la page des saisons : `{type, adresse}` (chemin et paramètres)."""
    u = construire(graine, taille)
    pages = [{"type": "saisons", "adresse": adresse_saisons()}]
    for saison in u.saisons:
        for page in range(1, u.nb_pages_calendrier(saison) + 1):
            pages.append({"type": "calendrier", "adresse": adresse_saison(saison, page)})
    for r in u.rallyes:
        pages.append({"type": "rallye", "adresse": adresse_rallye(r.id)})
        pages += [{"type": "speciale", "adresse": adresse_speciale(s.id)} for s in u.speciales_de(r.id)]
        pages.append({"type": "classement", "adresse": adresse_classement(r.id)})
        pages.append({"type": "engages", "adresse": adresse_engages(r.id)})
    pages += [{"type": "chassis", "adresse": adresse_chassis(c.code)} for c in u.chassis]
    pages += [{"type": "pilote", "adresse": adresse_pilote(p.id)} for p in u.pilotes]
    return pages


def _collections(u: Univers) -> dict[str, list[dict]]:
    """Les enregistrements qu'une récolte doit retrouver ; les noms de champs sont le contrat avec la recette."""
    rallyes = [
        {k: v for k, v in asdict(r).items() if k != "saison"}  # la saison n'est pas un champ de la page rallye
        for r in u.rallyes
    ]
    temps = []
    for t in u.temps:
        s = u._speciale[t.speciale]
        e = u.engage(s.rallye, t.numero)
        temps.append(
            {
                "speciale": t.speciale,
                "numero": t.numero,
                "rang": t.rang,
                "pilote_id": e.pilote_id,
                "pilote": u._pilote[e.pilote_id].nom,
                "copilote": e.copilote,
                "voiture": u.voiture(e),
                "temps": "Abandon" if t.temps_ms is None else duree(t.temps_ms),
                "temps_ms": t.temps_ms,
            }
        )
    engages = [
        {
            "rallye": e.rallye,
            "numero": e.numero,
            "pilote_id": e.pilote_id,
            "copilote": e.copilote,
            "voiture": u.voiture(e),
            "chassis": e.chassis,
            "groupe": e.groupe,
        }
        for e in u.engages
    ]
    return {
        "rallyes": rallyes,
        "speciales": [asdict(s) for s in u.speciales],
        "temps": temps,
        "classements": [asdict(c) for c in u.classements],
        "engages": engages,
        "chassis": [asdict(c) for c in u.chassis],
        "historique": [asdict(h) for h in u.historique],
        "pilotes": [asdict(p) for p in u.pilotes],
    }


CLES = {
    "rallyes": ["id"],
    "speciales": ["id"],
    "temps": ["speciale", "numero"],
    "classements": ["rallye", "numero"],
    "engages": ["rallye", "numero"],
    "chassis": ["code"],
    "historique": ["chassis", "rallye"],
    "pilotes": ["id"],
}


def pieges_presents(v: dict) -> dict[str, int]:
    """Combien de fois chaque piège de `PIEGES` apparaît dans la vérité `v` (0 = absent : le site est défaillant)."""
    c = v["collections"]
    sans_rang = [k for k in c["classements"] if k["rang"] is not None]
    ex_aequo: dict[tuple, list] = defaultdict(list)
    for t in c["temps"]:
        if t["rang"] is not None:
            ex_aequo[(t["speciale"], t["rang"])].append(t["temps_ms"])
    saison = {r["id"]: r["date_debut"][:4] for r in c["rallyes"]}
    par_chassis: dict[str, list[tuple]] = defaultdict(list)
    for h in c["historique"]:
        par_chassis[h["chassis"]].append((saison[h["rallye"]], h["pilote_id"]))
    noms = (
        [r["nom"] for r in c["rallyes"]]
        + [s["nom"] for s in c["speciales"]]
        + [p["nom"] for p in c["pilotes"]]
        + [e["copilote"] for e in c["engages"]]
    )
    communes = [x for x in COLONNES_TEMPS if x in COLONNES_CLASSEMENT]
    return {
        "temps_a_minutes": sum(1 for t in c["temps"] if t["temps_ms"] is not None and t["temps_ms"] < 3_600_000),
        "temps_a_heures": sum(1 for k in sans_rang if k["temps_total_ms"] >= 3_600_000),
        "abandon_sans_temps": sum(1 for t in c["temps"] if t["temps_ms"] is None and t["temps"] == "Abandon")
        + sum(1 for k in c["classements"] if k["rang"] is None and k["temps_total_ms"] is None),
        "ex_aequo": sum(1 for lot in ex_aequo.values() if len(lot) > 1 and len(set(lot)) == 1),
        "speciale_annulee_sans_tableau": sum(1 for s in c["speciales"] if s["annulee"]),
        "colonnes_dans_un_autre_ordre": int(
            [COLONNES_TEMPS.index(x) for x in communes] != [COLONNES_CLASSEMENT.index(x) for x in communes]
        ),
        "equipage_dans_une_cellule": len(c["temps"]),
        "chassis_de_pilote_en_pilote_et_de_saison_en_saison": sum(
            1 for lot in par_chassis.values() if len({s for s, _ in lot}) >= 2 and len({p for _, p in lot}) >= 2
        ),
        "noms_a_apostrophes": sum(1 for n in noms if "'" in n),
        "noms_accentues": sum(1 for n in noms if re.search(r"[àâçéèêëîïôûùü]", n, re.IGNORECASE)),
    }


def verite(graine: int, taille: int) -> dict:
    """Export complet de ce que le site publie, sérialisable en JSON : collections, clés et pages attendues."""
    u = construire(graine, taille)
    pages = pages_attendues(graine, taille)
    par_type: dict[str, int] = defaultdict(int)
    for p in pages:
        par_type[p["type"]] += 1
    v = {
        "graine": graine,
        "taille": taille,
        "par_page": PAR_PAGE,
        "rallyes_par_saison": RALLYES_PAR_SAISON,
        "nb_saisons": len(u.saisons),
        "saisons": list(u.saisons),
        "nb_pages": len(pages),
        "pages_par_type": dict(par_type),
        "cles": {nom: list(cle) for nom, cle in CLES.items()},
        "collections": _collections(u),
        "pages": pages,
    }
    v["pieges"] = pieges_presents(v)
    return v


# --- Pages HTML --------------------------------------------------------------------------------


def _date_fr(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"{d.day} {MOIS[d.month - 1]} {d.year}"


def _heure_fr(iso: str) -> str:
    return f"{iso[11:13]}h{iso[14:16]}"


def _km(valeur: float) -> str:
    return f"{valeur:.1f}".replace(".", ",") + " km"


def _pluriel(n: int, mot: str) -> str:
    return f"{n} {mot}{'s' if n > 1 else ''}"


def _gabarit(titre: str, corps: str, jeton: str, fil: str = "", honeypot: bool = False) -> str:
    piege = HONEYPOT_LIEN if honeypot else ""
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="sl-session" content="{escape(jeton)}">
<title>{escape(titre)} — {MARQUE}</title>
<link rel="stylesheet" href="/lab/static/rallye.css">
</head>
<body class="rallye">
<header class="entete"><div class="conteneur">
<a class="marque" href="{adresse_saisons()}"><span class="fanion" aria-hidden="true"></span>{MARQUE}</a>
<nav aria-label="Navigation principale"><a href="{adresse_saisons()}">Saisons</a></nav>
</div></header>
<main class="conteneur">
{fil}
{corps}
{piege}
</main>
<footer class="pied"><div class="conteneur">Site de démonstration — rallyes, pilotes et châssis fictifs</div></footer>
<script type="module" src="/lab/static/observateur.js"></script>
</body>
</html>"""


def _fil(*elements: tuple[str, str | None, str]) -> str:
    """Fil d'Ariane : (texte, adresse ou None pour la page courante, classe du lien)."""
    morceaux = []
    for texte, adresse, classe in elements:
        if adresse is None:
            morceaux.append(f'<span aria-current="page">{escape(texte)}</span>')
        else:
            attribut = f' class="{classe}"' if classe else ""
            morceaux.append(f'<a{attribut} href="{adresse}">{escape(texte)}</a>')
    return f'<nav class="fil" aria-label="{ARIANE}">{" › ".join(morceaux)}</nav>'


def _fil_rallye(r: Rallye, *suite: tuple[str, str | None, str]) -> str:
    return _fil(
        ("Saisons", adresse_saisons(), ""),
        (str(r.saison), adresse_saison(r.saison), ""),
        (r.nom, adresse_rallye(r.id) if suite else None, "rallye"),
        *suite,
    )


def _entete(colonne: str, a_droite: bool) -> str:
    classe = ' class="droite"' if a_droite else ""
    return f'<th scope="col"{classe}>{escape(colonne)}</th>'


def _tableau(classe: str, colonnes: list[str], lignes: list[str], droite: tuple[str, ...] = ()) -> str:
    """Tableau avec en-tête, dans un conteneur qui défile en largeur sur petit écran."""
    entetes = "".join(_entete(c, c in droite) for c in colonnes)
    return (
        f'<div class="tableau"><table class="{classe}"><thead><tr>{entetes}</tr></thead>'
        f"<tbody>\n{chr(10).join(lignes)}\n</tbody></table></div>"
    )


def _surface(nom: str) -> str:
    return f'<span class="surface surface-{SURFACES_CSS.get(nom, "mixte")}">{escape(nom)}</span>'


def _lien_pilote(u: Univers, id_pilote: int, classe: str = "") -> str:
    p = u.trouver_pilote(id_pilote)
    attribut = f' class="{classe}"' if classe else ""
    return f'<a{attribut} href="{adresse_pilote(id_pilote)}">{escape(p.nom if p else str(id_pilote))}</a>'


def _equipage(u: Univers, e: Engage) -> str:
    """Pilote et copilote dans une même cellule : le pilote en lien, le copilote en dessous."""
    return f'{_lien_pilote(u, e.pilote_id, "pilote")}<br><span class="copilote">{escape(e.copilote)}</span>'


def _pagination(saison: int, page: int, total: int) -> str:
    precedent = (
        f'<a class="precedente" rel="prev" href="{adresse_saison(saison, page - 1)}">← Page précédente</a>'
        if page > 1
        else '<span class="vide"></span>'
    )
    suivant = (
        f'<a class="suivante" rel="next" href="{adresse_saison(saison, page + 1)}">Page suivante →</a>'
        if page < total
        else '<span class="vide"></span>'
    )
    return f'<nav class="pages" aria-label="Pagination">{precedent}<span class="etat">Page {page} sur {total}</span>{suivant}</nav>'


def page_saisons(jeton: str, u: Univers, honeypot: bool = False) -> str:
    elements = ""
    for saison in reversed(u.saisons):
        rallyes = u.rallyes_de(saison)
        elements += (
            f'<li><a href="{adresse_saison(saison)}">Saison {saison}</a>'
            f'<span class="detail">{_pluriel(len(rallyes), "rallye")} · du {_date_fr(rallyes[0].date_debut)}'
            f" au {_date_fr(rallyes[-1].date_fin)}</span></li>\n"
        )
    corps = f"""<h1 class="titre">Saisons</h1>
<p class="chapeau">Choisissez une saison pour parcourir son calendrier, puis les résultats de chaque rallye.</p>
<ul class="saisons">
{elements}</ul>"""
    return _gabarit("Saisons", corps, jeton, _fil(("Saisons", None, "")), honeypot)


def page_calendrier(jeton: str, u: Univers, saison: int, page: int = 1, honeypot: bool = False) -> str:
    total = u.nb_pages_calendrier(saison)
    lignes = []
    for r in u.rallyes_de(saison)[(page - 1) * PAR_PAGE : page * PAR_PAGE]:
        lignes.append(
            f'<tr><td class="date"><time datetime="{escape(r.date_debut)}">{_date_fr(r.date_debut)}</time></td>'
            f'<td class="rallye"><a href="{adresse_rallye(r.id)}">{escape(r.nom)}</a></td>'
            f"<td>{escape(r.championnat)}</td><td>{_surface(r.surface)}</td><td>{escape(r.lieu)}</td></tr>"
        )
    nb = len(u.rallyes_de(saison))
    corps = f"""<h1 class="titre">Saison {saison}</h1>
<p class="chapeau">{_pluriel(nb, "rallye")} au calendrier.</p>
{_tableau("calendrier", COLONNES_CALENDRIER, lignes)}
{_pagination(saison, page, total)}"""
    fil = _fil(("Saisons", adresse_saisons(), ""), (str(saison), None, ""))
    return _gabarit(f"Saison {saison} — page {page}", corps, jeton, fil, honeypot)


def page_rallye(jeton: str, u: Univers, r: Rallye, honeypot: bool = False) -> str:
    speciales = u.speciales_de(r.id)
    lignes = []
    for s in speciales:
        statut = '<span class="etiquette etiquette-annulee">Annulée</span>' if s.annulee else "Disputée"
        classe = ' class="annulee"' if s.annulee else ""
        lignes.append(
            f'<tr{classe}><td class="es">ES{s.numero}</td>'
            f'<td class="nom"><a href="{adresse_speciale(s.id)}">{escape(s.nom)}</a></td>'
            f'<td class="droite">{_km(s.km)}</td><td>{_date_fr(s.depart)} · {_heure_fr(s.depart)}</td><td>{statut}</td></tr>'
        )
    n_eng = len(u.engages_de(r.id))
    corps = f"""<h1 class="titre">{escape(r.nom)}</h1>
<p class="infos">Du <time class="debut" datetime="{escape(r.date_debut)}">{_date_fr(r.date_debut)}</time> au <time class="fin" datetime="{escape(r.date_fin)}">{_date_fr(r.date_fin)}</time></p>
<dl class="fiche">
<div class="ligne"><dt>Saison</dt><dd class="saison"><a href="{adresse_saison(r.saison)}">{r.saison}</a></dd></div>
<div class="ligne"><dt>Championnat</dt><dd class="championnat">{escape(r.championnat)}</dd></div>
<div class="ligne"><dt>Surface</dt><dd class="surface">{_surface(r.surface)}</dd></div>
<div class="ligne"><dt>Lieu</dt><dd class="lieu">{escape(r.lieu)}</dd></div>
<div class="ligne"><dt>Distance chronométrée</dt><dd class="km">{_km(r.km_chrono)}</dd></div>
<div class="ligne"><dt>Engagés</dt><dd class="nb-engages">{n_eng}</dd></div>
</dl>
<p class="actions"><a class="bouton classement" href="{adresse_classement(r.id)}">Classement final</a><a class="bouton engages" href="{adresse_engages(r.id)}">Liste des engagés</a></p>
<h2>Spéciales</h2>
{_tableau("speciales", COLONNES_SPECIALES, lignes, droite=("Longueur",))}"""
    return _gabarit(r.nom, corps, jeton, _fil_rallye(r), honeypot)


def _ligne_temps(u: Univers, r: Rallye, t: Temps, premier: int | None) -> str:
    e = u.engage(r.id, t.numero)
    if t.temps_ms is None:
        pos, chrono, gap, classe = "-", "Abandon", "—", "abandon"
    else:
        pos, chrono = str(t.rang), duree(t.temps_ms)
        gap = "—" if t.temps_ms == premier else ecart(t.temps_ms - premier)
        classe = "podium" if t.rang is not None and t.rang <= 3 else ""
    attribut = f' class="{classe}"' if classe else ""
    return (
        f'<tr{attribut}><td class="pos">{pos}</td><td class="num">{t.numero}</td><td class="equipage">{_equipage(u, e)}</td>'
        f'<td>{escape(u.voiture(e))}</td><td class="chrono">{chrono}</td><td class="ecart">{gap}</td></tr>'
    )


def page_speciale(jeton: str, u: Univers, s: Speciale, honeypot: bool = False) -> str:
    r = u.trouver_rallye(s.rallye)
    titre = f"ES{s.numero} · {s.nom}"
    if s.annulee:
        suite = '<p class="annulee">Cette spéciale a été annulée : aucun temps n\'a été relevé.</p>'
    else:
        lignes_brutes = u.temps_de(s.id)
        premier = min((t.temps_ms for t in lignes_brutes if t.temps_ms is not None), default=0)
        lignes = [_ligne_temps(u, r, t, premier) for t in lignes_brutes]
        suite = (
            _tableau("temps", COLONNES_TEMPS, lignes, droite=("Temps", "Écart"))
            + '\n<p class="legende">Pos. : rang sur la spéciale ; deux équipages au même temps partagent le même rang.</p>'
        )
    corps = f"""<h1 class="titre">{escape(titre)}</h1>
<p class="details"><span class="km">{_km(s.km)}</span> · départ le <time datetime="{escape(s.depart)}">{_date_fr(s.depart)} à {_heure_fr(s.depart)}</time></p>
{suite}"""
    return _gabarit(titre, corps, jeton, _fil_rallye(r, (f"ES{s.numero}", None, "")), honeypot)


def page_classement(jeton: str, u: Univers, r: Rallye, honeypot: bool = False) -> str:
    lignes = []
    resultats = u.classement_de(r.id)
    premier = next((k.temps_total_ms for k in resultats if k.rang == 1), 0)
    for k in resultats:
        e = u.engage(r.id, k.numero)
        if k.rang is None:
            pos, total, gap, classe = "Ab.", "-", "—", ' class="abandon"'
        else:
            pos, total = str(k.rang), duree(k.temps_total_ms)
            gap = "—" if k.temps_total_ms == premier else ecart(k.temps_total_ms - premier)
            classe = ' class="podium"' if k.rang <= 3 else ""
        lignes.append(
            f'<tr{classe}><td class="pos">{pos}</td><td class="num">{k.numero}</td><td class="equipage">{_equipage(u, e)}</td>'
            f'<td>{escape(e.groupe)}</td><td>{escape(u.voiture(e))}</td><td class="chrono">{total}</td><td class="ecart">{gap}</td></tr>'
        )
    classes = sum(1 for k in resultats if k.rang is not None)
    nb_speciales = sum(1 for s in u.speciales_de(r.id) if not s.annulee)
    corps = f"""<h1 class="titre">Classement final</h1>
<p class="chapeau">{escape(r.nom)} — {_pluriel(nb_speciales, "spéciale")} disputée{"s" if nb_speciales > 1 else ""}, {_pluriel(classes, "équipage")} classé{"s" if classes > 1 else ""}, {_pluriel(len(resultats) - classes, "abandon")}.</p>
{_tableau("classement", COLONNES_CLASSEMENT, lignes, droite=("Temps total", "Écart"))}
<p class="legende">Ab. : abandon, sans temps total. Deux équipages au même temps partagent le même rang.</p>"""
    return _gabarit(f"Classement — {r.nom}", corps, jeton, _fil_rallye(r, ("Classement", None, "")), honeypot)


def page_engages(jeton: str, u: Univers, r: Rallye, honeypot: bool = False) -> str:
    lignes = []
    for e in u.engages_de(r.id):
        lignes.append(
            f'<tr><td class="num">{e.numero}</td><td>{_lien_pilote(u, e.pilote_id)}</td><td>{escape(e.copilote)}</td>'
            f'<td>{escape(u.voiture(e))}</td><td><a href="{adresse_chassis(e.chassis)}">{escape(e.chassis)}</a></td>'
            f"<td>{escape(e.groupe)}</td></tr>"
        )
    corps = f"""<h1 class="titre">Liste des engagés</h1>
<p class="chapeau">{escape(r.nom)} — {_pluriel(len(lignes), "équipage")} au départ.</p>
{_tableau("engages", COLONNES_ENGAGES, lignes)}"""
    return _gabarit(f"Engagés — {r.nom}", corps, jeton, _fil_rallye(r, ("Engagés", None, "")), honeypot)


def page_chassis(jeton: str, u: Univers, c: Chassis, honeypot: bool = False) -> str:
    lignes = []
    for h in u.historique_de(c.code):
        r = u.trouver_rallye(h.rallye)
        classe = ' class="abandon"' if h.resultat == "Abandon" else ""
        lignes.append(
            f'<tr{classe}><td class="date"><time datetime="{escape(h.date)}">{_date_fr(h.date)}</time></td>'
            f'<td><a href="{adresse_rallye(h.rallye)}">{escape(r.nom)}</a></td><td>{_lien_pilote(u, h.pilote_id)}</td>'
            f'<td class="resultat">{escape(h.resultat)}</td></tr>'
        )
    corps = f"""<h1 class="titre">Châssis {escape(c.code)}</h1>
<dl class="fiche">
<div class="ligne"><dt>Marque</dt><dd class="marque">{escape(c.marque)}</dd></div>
<div class="ligne"><dt>Modèle</dt><dd class="modele">{escape(c.modele)}</dd></div>
<div class="ligne"><dt>Année</dt><dd class="annee">{c.annee}</dd></div>
<div class="ligne"><dt>Rallyes disputés</dt><dd class="nb-rallyes">{len(lignes)}</dd></div>
</dl>
<h2>Historique</h2>
{_tableau("historique", COLONNES_HISTORIQUE, lignes)}"""
    fil = _fil(("Saisons", adresse_saisons(), ""), (f"Châssis {c.code}", None, ""))
    return _gabarit(f"Châssis {c.code}", corps, jeton, fil, honeypot)


def page_pilote(jeton: str, u: Univers, p: Pilote, honeypot: bool = False) -> str:
    lignes = []
    for e in u.engagements_de(p.id):
        r = u.trouver_rallye(e.rallye)
        resultat = u.resultat(e.rallye, e.numero)
        texte = "Abandon" if resultat.rang is None else ordinal(resultat.rang)
        classe = ' class="abandon"' if resultat.rang is None else ""
        lignes.append(
            f'<tr{classe}><td class="date"><time datetime="{escape(r.date_debut)}">{_date_fr(r.date_debut)}</time></td>'
            f'<td><a href="{adresse_rallye(r.id)}">{escape(r.nom)}</a></td><td class="num">{e.numero}</td>'
            f'<td><a href="{adresse_chassis(e.chassis)}">{escape(e.chassis)}</a></td><td class="resultat">{texte}</td></tr>'
        )
    corps = f"""<h1 class="titre">{escape(p.nom)}</h1>
<dl class="fiche">
<div class="ligne"><dt>Nationalité</dt><dd class="nationalite">{escape(p.nationalite)}</dd></div>
<div class="ligne"><dt>Rallyes disputés</dt><dd class="nb-rallyes">{len(lignes)}</dd></div>
</dl>
<h2>Engagements</h2>
{_tableau("engagements", COLONNES_ENGAGEMENTS, lignes)}"""
    fil = _fil(("Saisons", adresse_saisons(), ""), (p.nom, None, ""))
    return _gabarit(p.nom, corps, jeton, fil, honeypot)
