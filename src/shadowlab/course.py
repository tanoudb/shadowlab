"""Bilan de la course de 7 jours, « une identité qui dure » (étape I9, § 6.3 de
`docs/recherche/identite-qui-dure-2026-11-12.md`).

Lu dans la base de la campagne (`configs/experiments/identite-7-jours.yaml`, ou sa répétition courte) et dans le relevé
de la cadence (`<sorties>/campagnes/<n°>/cadence.jsonl`), sans rien écrire. Chaque critère vaut `tenu`, `non tenu` ou
`non mesuré` ; sans donnée, jamais `tenu` (même règle que la soirée, `soiree.py`).

**Sujet** :
- aucun bannissement dans son monde ; aucune alerte (identité notée `alerte` ou `banni`, visite arrêtée par la
  sentinelle) ;
- toutes les visites faites ont abouti (une visite interrompue par une coupure, une visite manquée et une visite non
  faite après l'échéance ne sont pas des visites faites : elles sont comptées à part) ;
- le même visiteur et la même empreinte E côté Arena à chaque visite (critères de la soirée) ;
- la porte d'entrée revenue seulement après sa durée : un retour de la porte, ce sont tous les défis émis
  par l'Arena (`decisions`, couche `defi-js`, décision `emis`) entre deux validations (`defi-js`, `valide`) ; son âge
  va de la dernière validation à la première émission du retour (la première porte n'a pas d'âge). Il doit valoir au
  moins la durée du cookie du profil gardé avec le passage (`runs.protection_config`, `profil.duree_cookie_s`), moins
  `TOLERANCE_PORTE_S` (60 s, la tolérance de la récolte : l'heure notée suit de quelques secondes la pose du cookie).
  Sans validation du tout : non mesuré. La porte revient donc au plus une fois par période ;
- au moins 99 % des annonces et 99 % des champs exacts à la fin : la note de la récolte cumulée (`recolte`, contre
  `vitrine.verite()`) de la dernière visite qui en porte une ;
- les visites manquées comptées à part : nombre de créneaux manqués (un créneau réessayé après une panne
  d'infrastructure compte une fois, avec son motif d'origine), motifs, essais notés. Ce critère est un relevé : il est
  tenu dès que le relevé existe, il ne juge pas le nombre (une visite manquée n'est pas un échec du moteur).
  Aussi à part : les créneaux non lancés parce que l'identité était en alerte (`attente_alerte`, une par alerte) ou
  bannie (`bannie`, répétitions restantes). Une attente d'alerte rend `aucune_alerte` non tenu.

**Témoins** (négatif, sentinelle, classique) : les critères de la soirée, et toutes leurs visites commencées dans les
24 premières heures de la course (`pendant_le_premier_jour`, départ = création de la campagne).
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from . import soiree
from .campaigns import FICHIER_CADENCE
from .engines.noezia.parcours import TOLERANCE_PORTE_S
from .soiree import NON_MESURE, NON_TENU, TENU, Bras

SEUIL_RECOLTE = 0.99
PREMIER_JOUR = timedelta(days=1)
TEMOINS = ("temoin-negatif", "temoin-sentinelle", "temoin-classique")


def _critere(statut: str, detail: str) -> dict[str, str]:
    return {"statut": statut, "detail": detail}


def _instant(texte: str | None) -> datetime | None:
    if not texte:
        return None
    t = datetime.fromisoformat(texte)
    return t if t.tzinfo else t.astimezone()


def _pct(x: float) -> str:
    return f"{100 * x:.1f} %"


# ═══ Lecture ═════════════════════════════════════════════════════════════════════════════════════


def lire_releve(dossier: Path | None) -> list[dict[str, Any]] | None:
    """Les lignes de `cadence.jsonl` (None si le relevé n'existe pas ; une ligne illisible est ignorée)."""
    fichier = Path(dossier) / FICHIER_CADENCE if dossier is not None else None
    if fichier is None or not fichier.exists():
        return None
    lignes = []
    for ligne in fichier.read_text(encoding="utf-8").splitlines():
        try:
            lignes.append(json.loads(ligne))
        except ValueError:
            continue
    return lignes


def _passages(cx: sqlite3.Connection, bras: Bras) -> dict[str, sqlite3.Row]:
    """Heure de début, profil et détails de chaque visite du bras, par jeton."""
    jetons = [v.session for v in bras.visites]
    if not jetons:
        return {}
    return {
        r["session_token"]: r
        for r in cx.execute(
            "SELECT session_token, started_at, protection_config, drapeaux FROM runs"
            f" WHERE session_token IN ({','.join('?' * len(jetons))})",
            jetons,
        )
    }


def _duree_porte(ligne: sqlite3.Row) -> float | None:
    try:
        return json.loads(ligne["protection_config"] or "{}").get("profil", {}).get("duree_cookie_s")
    except (ValueError, AttributeError):
        return None


def _details(ligne: sqlite3.Row) -> dict[str, Any]:
    details = json.loads(ligne["drapeaux"] or "{}").get("details_scenario") or {}
    return details if isinstance(details, dict) else {}


# ═══ Critères du sujet ════════════════════════════════════════════════════════════════════════════


def juger_porte(
    emissions: list[tuple[datetime, float | None]], validations: list[datetime]
) -> tuple[dict[str, str], dict[str, Any]]:
    """`emissions` : (heure, durée du cookie du profil du passage) de chaque défi émis au sujet ; `validations` :
    l'heure de chaque défi validé (`defi-js` / `valide`). Un retour de la porte va de la première émission suivant une
    validation à la validation qui le clôt (toutes les émissions entre les deux en font partie : photo, puis page). Son
    âge est le temps écoulé depuis la dernière validation avant lui ; la première porte n'en a pas."""
    evenements = sorted([(q, 0, d) for q, d in emissions] + [(q, 1, None) for q in validations], key=lambda e: e[:2])
    retours: list[tuple[datetime, float | None, datetime | None]] = []  # (1re émission, durée, dernière validation)
    derniere: datetime | None = None
    ouvert = False
    for quand, genre, duree in evenements:
        if genre == 1:
            derniere, ouvert = quand, False
        elif not ouvert:
            retours.append((quand, duree, derniere))
            ouvert = True
    faits = {"passages": len(retours), "duree_s": None, "ecart_min_s": None, "trop_tot": []}
    if not retours:
        return _critere(NON_MESURE, "aucun défi émis par l'Arena : la porte n'a jamais été vue"), faits
    if not validations:
        return _critere(NON_MESURE, "aucune validation du défi : l'âge du laissez-passer au retour est inconnu"), faits
    durees = {d for _, d, _ in retours}
    if None in durees:
        return _critere(NON_MESURE, "durée de la porte inconnue (profil non gardé avec un passage)"), faits
    ages = [((e - v).total_seconds(), d) for e, d, v in retours if v is not None]
    trop_tot = [round(a) for a, d in ages if a < d - TOLERANCE_PORTE_S]
    faits.update(
        duree_s=max(durees) if len(durees) == 1 else sorted(durees),
        ecart_min_s=round(min(a for a, _ in ages)) if ages else None,
        trop_tot=trop_tot,
    )
    duree = " ou ".join(f"{d:g}" for d in sorted(durees))
    detail = f"{len(retours)} passage(s) de la porte ; durée {duree} s, tolérance {TOLERANCE_PORTE_S} s"
    if ages:
        detail += f" ; âge le plus court au retour (dernière validation à première émission) {faits['ecart_min_s']} s"
    if trop_tot:
        detail += f" ; revenue trop tôt après {trop_tot} s"
    return _critere(NON_TENU if trop_tot else TENU, detail), faits


def juger_recolte(note: dict[str, Any] | None, rang: int | None) -> dict[str, str]:
    if not note or not note.get("annonces_attendues") or not note.get("champs_attendus"):
        return _critere(NON_MESURE, "aucune récolte notée contre la vérité de la vitrine")
    annonces = note["annonces_retrouvees"] / note["annonces_attendues"]
    champs = note["champs_exacts"] / note["champs_attendus"]
    tenu = annonces >= SEUIL_RECOLTE and champs >= SEUIL_RECOLTE
    return _critere(
        TENU if tenu else NON_TENU,
        f"annonces {note['annonces_retrouvees']}/{note['annonces_attendues']} ({_pct(annonces)}), champs exacts "
        f"{note['champs_exacts']}/{note['champs_attendus']} ({_pct(champs)}), seuil {_pct(SEUIL_RECOLTE)} ; "
        f"notée à la visite {rang}" + (f", {note['passes']} passe(s)" if note.get("passes") else ""),
    )


def compter_manquees(notes: list[dict[str, Any]]) -> dict[str, Any]:
    """Un créneau manqué compte une fois (son motif d'origine), quel que soit le nombre d'essais notés."""
    manquees = [n for n in notes if n.get("genre") == "manquee"]
    motifs: dict[str, str] = {}
    for n in manquees:
        motifs.setdefault(n.get("creneau") or n.get("prevue") or "", n.get("motif") or "inconnu")
    return {"nombre": len(motifs), "par_motif": dict(Counter(motifs.values())), "essais": len(manquees)}


def compter_identite(notes: list[dict[str, Any]]) -> dict[str, int]:
    """Les créneaux non lancés à cause de l'identité du bras : attentes d'alerte (une par alerte, `alerte_le` : une
    reprise pendant l'attente ne compte pas deux fois) et visites non faites après un bannissement (la dernière note
    fait foi, comme pour l'échéance). Ce ne sont pas des visites faites."""
    attentes = {n.get("alerte_le") or n.get("constatee") for n in notes if n.get("genre") == "attente_alerte"}
    bannie = next((n.get("restantes") or 0 for n in reversed(notes) if n.get("genre") == "bannie"), 0)
    return {"attentes_alerte": len(attentes), "visites_non_faites_bannie": bannie}


def juger_sujet(
    bras: Bras, emissions: list[tuple[datetime, float | None]], validations: list[datetime],
    recolte: tuple[dict | None, int | None], notes: list[dict[str, Any]] | None,
) -> tuple[dict[str, dict[str, str]], dict[str, Any]]:  # fmt: skip
    vide = soiree._vide(bras)
    criteres: dict[str, dict[str, str]] = {}
    criteres["aucun_bannissement"] = vide or _critere(
        NON_TENU if bras.bannissements else TENU, f"{len(bras.bannissements)} bannissement(s) dans le monde du bras"
    )
    alertes = [v.rang for v in bras.visites if v.identite_etat in ("alerte", "banni") or v.arret]
    identite = compter_identite(notes or [])
    criteres["aucune_alerte"] = vide or _critere(
        NON_TENU if alertes or identite["attentes_alerte"] else TENU,
        f"visites en alerte ou arrêtées : {alertes or 'aucune'} ; "
        f"attentes d'alerte (visites non lancées) : {identite['attentes_alerte']}",
    )
    interrompues = sum(1 for n in notes or [] if n.get("genre") == "interrompue")
    criteres["visites_faites_abouties"] = vide or _critere(
        TENU if bras.reussies == bras.faites else NON_TENU,
        f"{bras.reussies} abouties sur {bras.faites} faites ; interrompues par une coupure (à part) : {interrompues}",
    )
    de_la_soiree = soiree.juger_sujet(bras)
    criteres["meme_visiteur"] = de_la_soiree["meme_visiteur"]
    criteres["meme_empreinte"] = de_la_soiree["meme_empreinte"]
    porte, faits_porte = juger_porte(emissions, validations)
    criteres["porte_apres_sa_duree"] = vide or porte
    criteres["recolte_99"] = vide or juger_recolte(*recolte)
    manquees = compter_manquees(notes or [])
    # `reprendre` après l'échéance réécrit la même note (mêmes répétitions restantes) : la dernière fait foi
    non_faites = next((n.get("restantes") or 0 for n in reversed(notes or []) if n.get("genre") == "echeance"), 0)
    if notes is None:
        criteres["visites_manquees_a_part"] = _critere(NON_MESURE, f"aucun relevé de la cadence ({FICHIER_CADENCE})")
    else:
        motifs = ", ".join(f"{m} {k}" for m, k in sorted(manquees["par_motif"].items())) or "aucun motif"
        criteres["visites_manquees_a_part"] = _critere(
            TENU,
            f"{manquees['nombre']} visite(s) manquée(s) ({motifs} ; {manquees['essais']} essai(s) noté(s)) ; "
            f"{interrompues} interrompue(s) ; {non_faites} non faite(s) (échéance) ; "
            f"{identite['attentes_alerte']} attente(s) d'alerte ; "
            f"{identite['visites_non_faites_bannie']} non faite(s) (identité bannie)",
        )
    faits = {
        "visites_manquees": manquees,
        "visites_interrompues": interrompues,
        "visites_non_faites_echeance": non_faites,
        **identite,
        "porte": faits_porte,
        "recolte": recolte[0],
    }
    return criteres, faits


def juger_premier_jour(bras: Bras, debuts: list[datetime | None], depart: datetime | None) -> dict[str, str]:
    if not bras.visites:
        return _critere(NON_MESURE, "aucune visite faite")
    if depart is None or None in debuts:
        return _critere(NON_MESURE, "heure de départ ou de visite inconnue")
    tard = [v.rang for v, d in zip(bras.visites, debuts, strict=True) if d - depart >= PREMIER_JOUR]
    derniere = max(d for d in debuts if d is not None) - depart
    return _critere(
        NON_TENU if tard else TENU,
        f"dernière visite commencée {derniere.total_seconds() / 3600:.1f} h après le départ ; "
        f"après 24 h : {tard or 'aucune'}",
    )


# ═══ Bilan ═══════════════════════════════════════════════════════════════════════════════════════


def bilan(
    cx: sqlite3.Connection, experiment_id: int, dossier: Path | None, roles: dict[str, str] | None = None
) -> dict[str, Any]:
    """Le bilan de la course `experiment_id` ; `dossier` : ses sorties durables (`campaigns.dossier_campagne`), où vit
    `cadence.jsonl`. Lève `LookupError` si la campagne n'existe pas."""
    ligne = cx.execute("SELECT configuration, created_at FROM experiments WHERE id = ?", (experiment_id,)).fetchone()
    if ligne is None:
        raise LookupError(f"expérience {experiment_id} introuvable")
    config = json.loads(ligne["configuration"])
    depart = _instant(ligne["created_at"])
    releve = lire_releve(dossier)
    roles = roles or soiree.ROLES
    rapport: dict[str, Any] = {
        "campagne": experiment_id,
        "depart": depart.isoformat() if depart else None,
        "releve": releve is not None,
        "bras": {},
    }
    statuts: list[str] = []
    for role, juge in soiree.JUGES.items():
        label = roles.get(role, soiree.ROLES[role])
        bras = soiree._lire_bras(cx, experiment_id, config, label)
        passages = _passages(cx, bras)
        notes = None if releve is None else [n for n in releve if n.get("bras") == label]
        faits: dict[str, Any] = {}
        if role == "sujet":
            emissions = _emissions(cx, passages)
            validations = _validations(cx, passages)
            recolte: tuple[dict | None, int | None] = (None, None)
            for v in bras.visites:
                note = _details(passages[v.session]).get("recolte")
                if isinstance(note, dict) and "champs_attendus" in note:
                    recolte = (note, v.rang)
            criteres, faits = juger_sujet(bras, emissions, validations, recolte, notes)
        else:
            criteres = juge(bras)
            debuts = [_instant(passages[v.session]["started_at"]) for v in bras.visites]
            criteres["pendant_le_premier_jour"] = juger_premier_jour(bras, debuts, depart)
            faits = compter_identite(notes or [])  # la sentinelle bannie : ses visites 4 à 6, non faites
        statuts += [c["statut"] for c in criteres.values()]
        rapport["bras"][role] = {
            "label": bras.label,
            "monde": bras.monde,
            "visites_prevues": bras.prevues,
            "visites_faites": bras.faites,
            "visites_reussies": bras.reussies,
            "bannissements": len(bras.bannissements),
            **faits,
            "criteres": criteres,
        }
    rapport["verdict"] = soiree.verdict(statuts)
    return rapport


def _emissions(cx: sqlite3.Connection, passages: dict[str, sqlite3.Row]) -> list[tuple[datetime, float | None]]:
    if not passages:
        return []
    jetons = list(passages)
    lignes = cx.execute(
        "SELECT session_token, created_at FROM decisions WHERE decision = 'emis'"
        f" AND session_token IN ({','.join('?' * len(jetons))}) ORDER BY created_at, id",
        jetons,
    ).fetchall()
    emissions = []
    for d in lignes:
        quand = _instant(d["created_at"])
        if quand is not None:
            emissions.append((quand, _duree_porte(passages[d["session_token"]])))
    return sorted(emissions, key=lambda e: e[0])


def _validations(cx: sqlite3.Connection, passages: dict[str, sqlite3.Row]) -> list[datetime]:
    if not passages:
        return []
    jetons = list(passages)
    lignes = cx.execute(
        "SELECT created_at FROM decisions WHERE couche = 'defi-js' AND decision = 'valide'"
        f" AND session_token IN ({','.join('?' * len(jetons))}) ORDER BY created_at, id",
        jetons,
    ).fetchall()
    return sorted(q for q in (_instant(d["created_at"]) for d in lignes) if q is not None)


def texte(rapport: dict[str, Any]) -> str:
    """Le bilan pour le terminal."""
    lignes = [f"Course, campagne {rapport['campagne']} : {rapport['verdict'].upper()}", f"Départ : {rapport['depart']}"]
    for role, bras in rapport["bras"].items():
        lignes.append(
            f"\n{role} ({bras['label']}) : {bras['visites_faites']} visite(s) faite(s), "
            f"{bras['visites_reussies']} réussie(s), plafond {bras['visites_prevues']}"
        )
        for nom, critere in bras["criteres"].items():
            lignes.append(f"  {critere['statut']:<10} {nom} : {critere['detail']}")
    return "\n".join(lignes)
