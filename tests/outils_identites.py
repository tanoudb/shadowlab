"""Outils des tests du gestionnaire d'identités (étape 4.2) : travailleurs lancés dans des processus neufs (`spawn`),
qui se partagent la file d'un même `etat.sqlite3`.

Un travailleur tient le verrou de travail de son identité (`gestionnaire.verrou_travailleur`) toute sa vie, prend des
pages avec son nom, les note faites, et écrit dans son propre fichier chaque page prise (le test vérifie qu'aucune
adresse n'a été prise par deux identités, sauf celle d'un travailleur tué, rendue puis reprise). Aucun navigateur, aucun
réseau.
"""

from __future__ import annotations

import random
import time
from pathlib import Path
from urllib.parse import urlsplit

from outils_recolte import RECETTE_VITRINE, Horloge, PiloteFactice

from shadowlab.engines.noezia import identite as ident
from shadowlab.engines.noezia.parcours import MoteurDriver, Options, Parcours
from shadowlab.engines.noezia.recettes import lire_texte

QUAND = "2026-11-19T10:00:00+00:00"
REFUS_BANNI = '<html><body data-arena="blocage"><p>accès refusé</p></body></html>'


class PiloteIdentite(PiloteFactice):
    """Comme `DriverNoezia` en mode identité, sans navigateur : il ouvre vraiment l'identité (verrou, refus d'une
    identité bannie ou en alerte), journalise la visite, et rend l'en-tête d'une page refusée (`X-Arena-Refus`).
    `bannir_a` : à la n-ième page demandée, l'Arena répond 403 avec l'en-tête `bannissement` à cette page et à toutes
    les suivantes (le visiteur est banni)."""

    name = "noezia"
    runtime = "navigateur"

    def __init__(self, client, nom: str, bannir_a: int | None = None):
        super().__init__(client)
        self.nom = nom
        self.bannir_a = bannir_a
        self._identite = None
        self._entetes: dict[str, str] = {}

    @property
    def identite_courante(self):
        return self._identite

    def configuration(self):
        return {"identite": self.nom, "identite_native": True}

    def open(self):
        self._identite = ident.ouvrir(self.nom)
        self.ouvert = True

    def start_session(self):
        self.sessions += 1
        self._identite.verifier_etat()
        self._identite.debut_visite()

    def close_session(self):
        self._identite.fin_visite(pages=len(self.pages_lues()))

    def close(self):
        if self._identite is not None:
            self._identite.liberer()
            self._identite = None
        self.ouvert = False

    def navigate(self, url):
        chemin = urlsplit(url).path
        banni = (
            self.bannir_a is not None
            and not chemin.startswith("/robots.txt")
            and (self.requetes_pages + 1 >= self.bannir_a)
        )
        if banni:
            self.verifier(url)
            self.urls.append(url)
            self.requetes_pages += 1
            self.demandes.append(chemin)
            self.statuts.append(403)
            self._texte = REFUS_BANNI
            self._entetes = {"x-arena-refus": "bannissement"}
            from shadowlab.engines.base import ResultatNavigation

            return ResultatNavigation(403, url, 1.0)
        self._entetes = {}
        return super().navigate(url)

    def etat_page(self):
        return (self.statuts[-1] if self.statuts else None), (self.urls[-1] if self.urls else ""), dict(self._entetes)


def parcours_partage(dossier, pilote, *, options=None, horloge=None, alea=None, texte=None):
    """Un `Parcours` de la recette vitrine sur le pilote d'une identité (moteur « navigateur »), horloge factice."""
    horloge = horloge or Horloge()
    texte = texte if texte is not None else RECETTE_VITRINE.read_text(encoding="utf-8")
    ecran: list[str] = []
    p = Parcours(
        lire_texte(texte),
        texte,
        str(RECETTE_VITRINE),
        MoteurDriver(pilote, "navigateur"),
        dossier,
        options or Options(),
        ecran=ecran.append,
        horloge=horloge,
        dormir=horloge.dormir,
        alea=alea or random.Random(7),
        horodatage=lambda: QUAND,
    )
    p.sortie_ecran = ecran
    return p


def travailleur(chemin_etat: str, passe: int, nom: str, journal: str, pause_s: float, bloquer_apres: int) -> None:
    """Prend des pages jusqu'à épuisement de la file. `bloquer_apres` > 0 : après autant de pages faites, prend une page
    de plus et s'endort sans fin en la tenant (le test le tue alors d'un SIGKILL, comme une coupure franche)."""
    from shadowlab.engines.noezia.etat import Etat
    from shadowlab.engines.noezia.gestionnaire import travailleur_vivant, verrou_travailleur

    dossier = Path(chemin_etat).parent
    verrou = verrou_travailleur(dossier, nom)  # gardé jusqu'à la mort du processus
    etat = Etat(Path(chemin_etat))
    faites = 0
    with open(journal, "a", encoding="utf-8") as flux:
        while True:
            etat.liberer_orphelines(passe, lambda autre: autre == nom or travailleur_vivant(dossier, autre))
            page = etat.prochaine(passe, identite=nom)
            if page is None:
                a_faire, en_cours = etat.pages_restantes(passe)
                if a_faire == 0 and en_cours == 0:
                    break
                time.sleep(0.05)  # d'autres tiennent encore des pages : elles peuvent revenir
                continue
            flux.write(f"{page.id}\n")
            flux.flush()
            if bloquer_apres and faites >= bloquer_apres:
                while True:  # tient la page, jusqu'au SIGKILL
                    time.sleep(1)
            time.sleep(pause_s)
            etat.terminer_page(page, etat="faite", decision="ok", quand="2026-11-19T10:00:00+00:00", statut=200)
            faites += 1
    etat.fermer()
    verrou.close()


def fin_fixe(fin: str) -> str:
    """Tâche d'une identité pour `gestionnaire.superviser` dans des processus neufs : rend la fin donnée."""
    return fin
