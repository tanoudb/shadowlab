"""État de la course de 7 jours d'un coup d'oeil (étape I9) : `shadowlab course etat [<n°>]`.

Fait pour le contrôle d'une fois par jour : « la course tourne-t-elle, a-t-elle fini, est-elle arrêtée ou bloquée ? ».
Lu dans la base (SQLite ouverte en lecture seule), dans `cadence.jsonl` et dans l'état noté des identités
(`engines/noezia/identite.lire_etat`). Aucune requête vers l'Arena, rien n'est écrit : la commande peut tourner pendant
une mesure.

**État** de la course (celui du sujet, le bras qui porte l'échéance : espacement `ordonnanceur` et `jours`) :
- `finie` : échéance atteinte (note `echeance` du sujet, ou échéance passée et campagne terminée) ;
- `arrêtée` : avant l'échéance, le sujet est banni (note `bannie` ou identité `banni`), ou la campagne est finie, ou le
  processus n'est plus là (`session` absente : `scripts/course.sh` sait si la session tmux existe ; la campagne ne
  laisse ni verrou ni pid) ;
- `en cours` sinon.

**Code de sortie** : 0 en cours sans anomalie ou finie ; 1 arrêtée ; 2 en cours avec un retard anormal ou un blocage ;
3 course ou campagne introuvable.

**Prochaine visite** : la note `prevue` de la cadence (`cadence.jsonl`, écrite quand elle choisit le créneau, avant
l'attente). Elle ne vaut que tant qu'elle est la dernière note du bras et qu'aucun passage du bras n'a commencé depuis
son écriture. Hors de la plage horaire, la cadence a déjà choisi le lendemain matin : l'heure prévue est dans le futur,
ce n'est pas un retard. Une course lancée avant cette note n'en a pas : la prochaine visite est alors « inconnue » et
aucun retard n'est jugé.
"""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from . import campaigns, course, espacement
from .engines.noezia import identite as module_identite

# Une visite manquée est notée par la cadence au-delà de 10 min de retard (`espacement.RETARD_MAX_MIN`) et
# l'infrastructure est revérifiée toutes les 5 min : 30 min de retard sur l'heure prévue, sans passage en cours ni note
# plus récente, ne s'explique plus par une attente normale (3 vérifications d'infrastructure ratées de suite, ou un
# processus figé).
RETARD_ANORMAL_MIN = 30.0
# Une visite lit au plus 40 pages et celles de la soirée 131 duraient 122 s en moyenne : un passage `en_cours` depuis
# plus d'une heure n'est plus une visite longue, c'est un blocage (navigateur ou défi figé).
BLOCAGE_MIN = 60.0
# Un créneau manqué est un accident (Mac en veille, panne brève) ; le suivant manqué aussi, sans aucune visite faite
# entre les deux, ce n'est plus un accident : une panne prolongée (OrbStack tombé la nuit, site injoignable) ou un
# processus qui rate ses créneaux, et la course se perd. Un créneau réessayé après une panne compte pour un seul.
MANQUEES_DE_SUITE_MAX = 2

EN_COURS, ARRETEE, FINIE = "en cours", "arrêtée", "finie"
CODE_OK, CODE_ARRETEE, CODE_ANOMALIE, CODE_INTROUVABLE = 0, 1, 2, 3
STATUTS_FINIS = ("termine", "termine_incomplet", "interrompu")  # `experiments.status` d'une campagne qui ne tourne plus


def ouvrir_en_lecture(chemin: Path) -> sqlite3.Connection:
    """La base, en lecture seule (`mode=ro`) : ni migration, ni création du fichier. Lève `sqlite3.OperationalError`
    si elle n'existe pas."""
    cx = sqlite3.connect(f"{Path(chemin).resolve().as_uri()}?mode=ro", uri=True, timeout=5)
    cx.row_factory = sqlite3.Row
    return cx


def _instant(texte: object) -> datetime | None:
    try:
        return course._instant(str(texte)) if texte else None
    except ValueError:
        return None


def _minutes(a: datetime, b: datetime) -> float:
    return round((a - b).total_seconds() / 60, 1)


def _passages(cx: sqlite3.Connection, experiment_id: int) -> dict[tuple[str, str], list[sqlite3.Row]]:
    """Les passages de la campagne, par bras (libellé, protection)."""
    par_bras: dict[tuple[str, str], list[sqlite3.Row]] = {}
    for r in cx.execute(
        "SELECT json_extract(e.configuration, '$.label') AS label, r.protection, r.status, r.success, r.started_at,"
        " r.completed_at FROM runs r JOIN engines e ON e.id = r.engine_id WHERE r.experiment_id = ? ORDER BY r.id",
        (experiment_id,),
    ):
        par_bras.setdefault((r["label"], r["protection"]), []).append(r)
    return par_bras


def _identite(options: dict[str, Any], maintenant: datetime) -> dict[str, Any] | None:
    """L'état de l'identité persistante du bras, lu par le code de l'identité (sans verrou, sans création)."""
    nom = options.get("identite")
    if not nom:
        return None
    try:
        donnees = module_identite.lire_etat(nom)
    except ValueError:
        donnees = None
    if donnees is None:
        return {"nom": nom, "etat": "absente", "jusqu_a": None}
    fin = module_identite.fin_d_alerte(donnees, maintenant)
    return {
        "nom": nom,
        "etat": donnees.get("etat", "ok"),
        "jusqu_a": fin.astimezone(maintenant.tzinfo).isoformat(timespec="seconds") if fin else None,
    }


def _prochaine(notes: list[dict[str, Any]], passages: list[sqlite3.Row]) -> datetime | None:
    """L'heure de la dernière note `prevue` du bras, si elle est encore la dernière note et si aucun passage n'a
    commencé depuis son écriture."""
    if not notes or notes[-1].get("genre") != "prevue":
        return None
    ecrite, prevue = _instant(notes[-1].get("ecrite")), _instant(notes[-1].get("prevue"))
    if prevue is None:
        return None
    if ecrite is not None and any((d := _instant(p["started_at"])) is not None and d >= ecrite for p in passages):
        return None
    return prevue


def _manquees_de_suite(notes: list[dict[str, Any]], finis: list[sqlite3.Row]) -> list[dict[str, Any]]:
    """Les créneaux manqués depuis la dernière visite faite du bras (un créneau réessayé compte une fois, avec la note
    de son premier essai), dans l'ordre."""
    fin = max((d for p in finis if (d := _instant(p["completed_at"] or p["started_at"])) is not None), default=None)
    creneaux: dict[str, dict[str, Any]] = {}
    for n in notes:
        constatee = _instant(n.get("constatee"))
        if n.get("genre") != "manquee" or (fin is not None and constatee is not None and constatee <= fin):
            continue
        creneaux.setdefault(str(n.get("creneau") or n.get("prevue")), n)
    return list(creneaux.values())


def _bras(
    moteur: campaigns.MoteurConfig, protection: str, experience: campaigns.Experience, passages: list[sqlite3.Row],
    notes: list[dict[str, Any]], maintenant: datetime,
) -> dict[str, Any]:  # fmt: skip
    """Un bras : visites, passage en cours, prochaine visite et retard, identité."""
    finis = [p for p in passages if p["status"] in ("reussi", "echec", "erreur")]
    ouverts = [d for p in passages if p["status"] == "en_cours" and (d := _instant(p["started_at"])) is not None]
    prevues = experience.visites_de(moteur)
    de_suite = _manquees_de_suite(notes, finis)
    premiere = _instant(de_suite[0].get("prevue")) if de_suite else None
    identite = _identite(moteur.options, maintenant)
    echeance = next((n for n in reversed(notes) if n.get("genre") == "echeance"), None)
    if any(n.get("genre") == "bannie" for n in notes) or (identite and identite["etat"] == "banni"):
        fini = "banni"
    elif echeance is not None:
        fini = "échéance"
    elif len(finis) >= prevues:
        fini = "complet"
    else:
        fini = None
    prochaine = None if fini else _prochaine(notes, passages)
    retard = _minutes(maintenant, prochaine) if prochaine and prochaine < maintenant else None
    reglage = moteur.espacement or experience.espacement
    return {
        "label": moteur.nom_affiche,
        "protection": protection,
        "espacement": reglage.mode if reglage else None,
        "etat": fini or "actif",
        "prevues": prevues,
        "faites": len(finis),
        "reussies": sum(1 for p in finis if p["status"] == "reussi" and p["success"]),
        "manquees": course.compter_manquees(notes)["nombre"],
        "manquees_de_suite": len(de_suite),
        "premiere_manquee": {
            "prevue": premiere.astimezone(maintenant.tzinfo).isoformat(timespec="seconds"),
            "motif": de_suite[0].get("motif"),
        }
        if premiere
        else None,
        "en_cours": {
            "depuis": min(ouverts).astimezone(maintenant.tzinfo).isoformat(timespec="seconds"),
            "minutes": _minutes(maintenant, min(ouverts)),
        }
        if ouverts
        else None,
        "prochaine": prochaine.astimezone(maintenant.tzinfo).isoformat(timespec="seconds") if prochaine else None,
        "retard_min": retard,
        "identite": identite,
    }


def _derniere_activite(
    passages: dict[tuple[str, str], list[sqlite3.Row]], releve: list[dict[str, Any]], maintenant: datetime
) -> datetime | None:
    """La plus récente entre le dernier passage commencé ou fini en base et la dernière note de `cadence.jsonl` (heure
    d'écriture ou constatée ; jamais une heure prévue, qui est dans le futur)."""
    instants = [_instant(p[c]) for liste in passages.values() for p in liste for c in ("started_at", "completed_at")]
    for n in releve:
        instants += [_instant(n.get(c)) for c in ("constatee", "ecrite")]
        if n.get("genre") == "interrompue":
            instants.append(_instant(n.get("fin")))
    return max((t for t in instants if t is not None and t <= maintenant), default=None)


def etat(
    cx: sqlite3.Connection, experiment_id: int, dossier: Path | None, *, maintenant: datetime | None = None,
    session: str | None = None,
) -> dict[str, Any]:  # fmt: skip
    """L'état de la course `experiment_id` ; `dossier` : ses sorties durables (`campaigns.dossier_campagne`) ;
    `session` : `vivante` ou `absente` (la session tmux de la course ; None : inconnue). Lève `LookupError` si la
    campagne n'existe pas."""
    maintenant = maintenant or datetime.now()
    maintenant = maintenant.astimezone() if maintenant.tzinfo is None else maintenant  # naïve : heure locale
    ligne = cx.execute(
        "SELECT configuration, created_at, status FROM experiments WHERE id = ?", (experiment_id,)
    ).fetchone()
    if ligne is None:
        raise LookupError(f"campagne {experiment_id} introuvable")
    experience = campaigns.Experience.model_validate_json(ligne["configuration"])
    depart = _instant(ligne["created_at"])
    releve = course.lire_releve(dossier) or []
    passages = _passages(cx, experiment_id)

    liste = []
    for moteur, protection in campaigns.unites(experience):
        notes = [n for n in releve if n.get("bras") == moteur.nom_affiche and n.get("protection") == protection]
        liste.append(
            _bras(moteur, protection, experience, passages.get((moteur.nom_affiche, protection), []), notes, maintenant)
        )

    # Le sujet porte l'échéance : l'échéance est calculée par la cadence elle-même (départ + `jours`), pas recopiée.
    sujet = jours = echeance = None
    for moteur, protection in campaigns.unites(experience):
        reglage = moteur.espacement or experience.espacement
        if reglage is not None and reglage.mode == "ordonnanceur" and reglage.jours is not None and depart is not None:
            cadence = espacement.Cadence(reglage, horloge=lambda: maintenant, depart=depart)
            sujet = next(b for b in liste if (b["label"], b["protection"]) == (moteur.nom_affiche, protection))
            jours, echeance = reglage.jours, cadence.echeance
            break

    statut = ligne["status"]
    campagne_finie = statut in STATUTS_FINIS or all(b["etat"] != "actif" for b in liste)
    raisons: list[str] = []
    if sujet is not None and sujet["etat"] == "banni":
        etat_course = ARRETEE
        raisons.append(f"le sujet ({sujet['label']}) est banni avant l'échéance")
    elif sujet is not None and sujet["etat"] == "échéance":
        etat_course = FINIE
    elif echeance is not None and maintenant >= echeance and statut in ("termine", "termine_incomplet"):
        etat_course = FINIE
    elif sujet is None and campagne_finie:
        etat_course = FINIE
    elif sujet is not None and sujet["etat"] != "actif":  # `complet` : toutes ses visites écrites, avant l'échéance
        etat_course = ARRETEE
        raisons.append(f"le sujet ({sujet['label']}) n'a plus de visite à faire avant l'échéance ({sujet['etat']})")
    elif campagne_finie:
        etat_course = ARRETEE
        raisons.append(f"campagne finie avant l'échéance (état {statut})")
    elif session == "absente":
        etat_course = ARRETEE
        raisons.append("session tmux absente : le processus n'est plus là avant l'échéance")
    else:
        etat_course = EN_COURS
    if etat_course == EN_COURS:
        for b in liste:
            if b["etat"] != "actif":
                continue
            if b["retard_min"] is not None and b["retard_min"] > RETARD_ANORMAL_MIN:
                raisons.append(
                    f"retard anormal : {b['label']} devait commencer à {_heure(b['prochaine'])}, "
                    f"{b['retard_min']:g} min de retard"
                )
            if b["manquees_de_suite"] >= MANQUEES_DE_SUITE_MAX and b["premiere_manquee"]:
                premiere = b["premiere_manquee"]
                raisons.append(
                    f"visites manquées de suite : {b['label']}, {b['manquees_de_suite']} créneaux sans visite faite, "
                    f"la première prévue à {_heure(premiere['prevue'])} (motif {premiere['motif']})"
                )
            if b["en_cours"] is not None and b["en_cours"]["minutes"] > BLOCAGE_MIN:
                raisons.append(f"blocage : {b['label']} a un passage en_cours depuis {b['en_cours']['minutes']:g} min")
    code = {ARRETEE: CODE_ARRETEE, FINIE: CODE_OK}.get(etat_course, CODE_ANOMALIE if raisons else CODE_OK)

    activite = _derniere_activite(passages, releve, maintenant)
    jour = None
    if depart is not None and jours is not None:
        jour = min(int((maintenant - depart) / timedelta(days=1)) + 1, math.ceil(jours))
    return {
        "campagne": experiment_id,
        "etat": etat_course,
        "code": code,
        "raisons": raisons,
        "session": session,
        "statut_campagne": statut,
        "jour": jour,
        "jours": int(jours) if jours is not None and float(jours).is_integer() else jours,
        "echeance": echeance.astimezone(maintenant.tzinfo).isoformat(timespec="seconds") if echeance else None,
        "derniere_activite": activite.astimezone(maintenant.tzinfo).isoformat(timespec="seconds") if activite else None,
        "depuis_min": _minutes(maintenant, activite) if activite else None,
        "maintenant": maintenant.isoformat(timespec="seconds"),
        "bras": liste,
    }


def _heure(iso: str | None) -> str:
    return datetime.fromisoformat(iso).strftime("%d/%m %H:%M") if iso else "-"


def _duree(minutes: float) -> str:
    return f"{minutes:g} min" if minutes < 120 else f"{minutes / 60:.1f} h"


def texte(rapport: dict[str, Any]) -> str:
    """Le résumé : l'état en tête, puis une ligne par bras."""
    tete = f"{rapport['etat']} — campagne {rapport['campagne']}"
    if rapport["jour"] is not None:
        tete += f", jour {rapport['jour']} sur {rapport['jours']:g}, échéance {_heure(rapport['echeance'])}"
    lignes = [tete]
    if rapport["derniere_activite"]:
        lignes.append(
            f"dernière activité : il y a {_duree(rapport['depuis_min'])} ({_heure(rapport['derniere_activite'])})"
        )
    else:
        lignes.append("dernière activité : aucune")
    lignes += [f"! {r}" for r in rapport["raisons"]]
    for b in rapport["bras"]:
        pieces = [f"{b['faites']}/{b['prevues']} faites, {b['reussies']} réussies, {b['manquees']} manquée(s)"]
        if b["etat"] != "actif":
            pieces.append(f"fini ({b['etat']})")
        elif b["en_cours"]:
            pieces.append(f"passage en cours depuis {_duree(b['en_cours']['minutes'])}")
        elif b["prochaine"]:
            retard = f", retard {_duree(b['retard_min'])}" if b["retard_min"] is not None else ""
            pieces.append(f"prochaine {_heure(b['prochaine'])}{retard}")
        else:
            pieces.append("prochaine : inconnue (aucune note `prevue`)")
        i = b["identite"]
        if i:
            pieces.append(
                f"identité {i['etat']}" + (f" jusqu'à {_heure(i['jusqu_a'])}" if i["etat"] == "alerte" else "")
            )
        lignes.append(f"  {b['label']} ({b['protection']}) : " + " ; ".join(pieces))
    return "\n".join(lignes)
