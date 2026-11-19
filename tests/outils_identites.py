"""Outils des tests du gestionnaire d'identités (étape 4.2) : travailleurs lancés dans des processus neufs (`spawn`),
qui se partagent la file d'un même `etat.sqlite3`.

Un travailleur tient le verrou de travail de son identité (`gestionnaire.verrou_travailleur`) toute sa vie, prend des
pages avec son nom, les note faites, et écrit dans son propre fichier chaque page prise (le test vérifie qu'aucune
adresse n'a été prise par deux identités, sauf celle d'un travailleur tué, rendue puis reprise). Aucun navigateur, aucun
réseau.
"""

from __future__ import annotations

import time
from pathlib import Path


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
