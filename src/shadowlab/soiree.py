"""Bilan de la soirée « une identité qui revient » (§ 6.2 de `docs/recherche/identite-qui-dure-2026-11-12.md`).

Lu dans la base d'une campagne (`configs/experiments/identite-soiree.yaml`), bras par bras, sans requête à la main :

- **sujet** : visites réussies sur visites prévues ; le même visiteur et la même empreinte E côté Arena à chaque
  visite ;
  le défi JavaScript vu à la première visite seulement ; aucune alerte, aucun bannissement ;
- **témoin négatif** : arrêté à partir de sa 5ᵉ visite, puis banni ;
- **témoin de sentinelle** : la ligne de bannissement écrite, un refus vu à la visite voulue, aucune page demandée après
  ce premier refus, identité notée `banni` ;
- **témoin classique** : arrêté à chaque visite, et par l'Arena (pas par l'outil).

Chaque critère vaut `tenu`, `non tenu` ou `non mesuré`. Un bras qui n'a rien fait ou dont on ne sait rien (identité déjà
bannie : « démarrage impossible » partout, donc zéro requête ; Arena absente) n'est JAMAIS « tenu » : sans donnée, c'est
`non mesuré`. Les bras sont retrouvés par leur libellé (`ROLES`) ; les visites prévues et la visite où bannir viennent
de la configuration de la campagne enregistrée avec elle.

Ce que les critères lisent : `runs` (statut, drapeaux : défis émis, détails du scénario `visite` : visiteur, état de
l'identité), `visites` (visiteur par session), `observations_js` (empreinte E de la session), `decisions` (refus de
l'Arena), `observations_http` (pages demandées après le premier refus, au sens de D-78), `bannissements`.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from . import correlation
from .arena import bannissements

TENU, NON_TENU, NON_MESURE = "tenu", "non tenu", "non mesuré"
ROLES = {
    "sujet": "sujet",
    "temoin-negatif": "temoin-negatif",
    "temoin-sentinelle": "temoin-sentinelle",
    "temoin-classique": "temoin-classique",
}
VISITE_ARRETEE_ATTENDUE = 5  # § 6.2 : le témoin négatif est pris à sa 5ᵉ visite (règle `correlation-session` 2.x)
MOTIF_MANUEL = bannissements.MOTIF_MANUEL


@dataclass
class VisiteLue:
    rang: int
    session: str
    reussie: bool
    visiteur: str | None = None
    empreinte: str | None = None
    defis: int | None = None  # défis émis par l'Arena pendant la visite (drapeaux)
    identite_etat: str | None = None  # état de l'identité noté par le scénario après la visite
    arret: bool = False  # la sentinelle de la récolte a arrêté la visite
    refusee_par_arena: bool = False  # une décision `bloque` est enregistrée pour cette session


@dataclass
class Bras:
    label: str
    prevues: int | None
    bannir_avant: int | None
    visites: list[VisiteLue] = field(default_factory=list)
    bannissements: list[dict[str, Any]] = field(default_factory=list)
    monde: str | None = None
    premier_refus: str | None = None  # horodatage de la première décision `bloque` du bras
    requetes_apres_refus: int | None = None  # pages demandées après ce premier refus (D-78), toutes sessions du bras
    requetes_apres_refus_total: int | None = None  # toutes requêtes, ressources comprises

    @property
    def faites(self) -> int:
        return len(self.visites)

    @property
    def reussies(self) -> int:
        return sum(1 for v in self.visites if v.reussie)


def _critere(statut: str, detail: str) -> dict[str, str]:
    return {"statut": statut, "detail": detail}


def _vide(bras: Bras) -> dict[str, str] | None:
    return _critere(NON_MESURE, "aucune visite faite") if bras.faites == 0 else None


# ═══ Critères, bras par bras (fonctions pures sur des faits déjà lus) ═════════════════════════════


def juger_sujet(bras: Bras) -> dict[str, dict[str, str]]:
    vide = _vide(bras)
    visites = bras.visites
    criteres: dict[str, dict[str, str]] = {}
    criteres["visites_reussies"] = vide or _critere(
        TENU if bras.reussies == bras.prevues == bras.faites else NON_TENU,
        f"{bras.reussies} réussies sur {bras.faites} faites, {bras.prevues} prévues",
    )
    for nom, attribut, libelle in (
        ("meme_visiteur", "visiteur", "visiteur"),
        ("meme_empreinte", "empreinte", "empreinte E"),
    ):
        valeurs = [getattr(v, attribut) for v in visites]
        connues = {x for x in valeurs if x is not None}
        if vide:
            criteres[nom] = vide
        elif not connues:
            criteres[nom] = _critere(NON_MESURE, f"l'Arena n'a noté aucun {libelle}")
        elif None in valeurs:
            criteres[nom] = _critere(NON_TENU, f"{valeurs.count(None)} visite(s) sans {libelle} noté")
        else:
            criteres[nom] = _critere(
                TENU if len(connues) == 1 else NON_TENU,
                f"{len(connues)} {libelle} distinct(s) sur {len(valeurs)} visites",
            )
    defis = [v.defis for v in visites]
    if vide:
        criteres["defi_premiere_visite_seulement"] = vide
    elif None in defis:
        criteres["defi_premiere_visite_seulement"] = _critere(NON_MESURE, "défis émis non enregistrés")
    else:
        tard = [v.rang for v in visites[1:] if v.defis]
        criteres["defi_premiere_visite_seulement"] = _critere(
            TENU if defis[0] and not tard else NON_TENU,
            f"défis émis à la 1re visite : {defis[0]} ; revenus aux visites : {tard or 'aucune'}",
        )
    alertes = [v.rang for v in visites if v.identite_etat in ("alerte", "banni") or v.arret]
    criteres["aucune_alerte"] = vide or _critere(
        TENU if not alertes and not bras.bannissements else NON_TENU,
        f"visites en alerte ou arrêtées : {alertes or 'aucune'} ; "
        f"bannissements dans le monde : {len(bras.bannissements)}",
    )
    return criteres


def juger_temoin_negatif(bras: Bras, seuil: int = VISITE_ARRETEE_ATTENDUE) -> dict[str, dict[str, str]]:
    vide = _vide(bras)
    arretees = [v.rang for v in bras.visites if not v.reussie]
    premiere = arretees[0] if arretees else None
    if vide:
        arret = vide
    elif premiere is None:
        arret = _critere(NON_MESURE if bras.faites < seuil else NON_TENU, f"aucune visite arrêtée sur {bras.faites}")
    else:
        apres = [v.rang for v in bras.visites if v.rang >= seuil]
        tenu = premiere == seuil and all(r in arretees for r in apres)
        arret = _critere(TENU if tenu else NON_TENU, f"première visite arrêtée : {premiere} (attendue : {seuil})")
    if vide:
        banni = vide
    elif bras.bannissements:
        banni = _critere(TENU, f"{len(bras.bannissements)} bannissement(s) dans le monde du bras")
    else:
        banni = _critere(NON_MESURE if bras.faites < seuil else NON_TENU, "aucun bannissement dans le monde du bras")
    return {f"arrete_a_la_visite_{seuil}": arret, "banni": banni}


def juger_temoin_sentinelle(bras: Bras) -> dict[str, dict[str, str]]:
    manuels = [b for b in bras.bannissements if b["motif"] == MOTIF_MANUEL and b["visiteur"]]
    refusees = [v.rang for v in bras.visites if v.refusee_par_arena]
    premier = min(refusees) if refusees else None
    criteres: dict[str, dict[str, str]] = {}
    criteres["bannissement_ecrit"] = (
        _critere(TENU, f"visiteur {manuels[0]['visiteur']} banni (motif manuel)")
        if manuels
        else _vide(bras) or _critere(NON_TENU, "aucune ligne `bannissements` de motif manuel dans le monde du bras")
    )
    if bras.bannir_avant is None:
        criteres["refus_a_la_visite_voulue"] = _critere(NON_MESURE, "la campagne ne dit pas où bannir")
    elif premier is None:
        criteres["refus_a_la_visite_voulue"] = _critere(
            NON_TENU if manuels else NON_MESURE,
            "bannissement écrit mais aucun refus vu" if manuels else "aucun refus de l'Arena vu",
        )
    else:
        criteres["refus_a_la_visite_voulue"] = _critere(
            TENU if premier == bras.bannir_avant else NON_TENU,
            f"premier refus à la visite {premier} (voulue : {bras.bannir_avant})",
        )
    if premier is None or bras.requetes_apres_refus is None:
        criteres["aucune_requete_apres_403"] = _critere(NON_MESURE, "aucun premier refus à partir duquel compter")
    else:
        criteres["aucune_requete_apres_403"] = _critere(
            TENU if bras.requetes_apres_refus == 0 else NON_TENU,
            f"{bras.requetes_apres_refus} page(s) demandée(s) après le premier refus "
            f"({bras.requetes_apres_refus_total} requête(s) toutes ressources comprises)",
        )
    etats = [v.identite_etat for v in bras.visites if v.identite_etat is not None]
    if "banni" in etats:
        criteres["identite_bannie"] = _critere(TENU, "identité notée `banni`")
    elif etats:
        criteres["identite_bannie"] = _critere(NON_TENU, f"états notés : {sorted(set(etats))}, jamais `banni`")
    else:
        criteres["identite_bannie"] = _critere(NON_MESURE, "aucun état d'identité noté")
    return criteres


def juger_temoin_classique(bras: Bras) -> dict[str, dict[str, str]]:
    vide = _vide(bras)
    passees = [v.rang for v in bras.visites if v.reussie]
    arena = any(v.refusee_par_arena for v in bras.visites) or bool(bras.bannissements)
    return {
        "toujours_arrete": vide
        or _critere(TENU if not passees else NON_TENU, f"visites réussies : {passees or 'aucune'} sur {bras.faites}"),
        "refus_par_l_arena": vide
        or _critere(
            TENU if arena else NON_TENU,
            "refus ou bannissement enregistré par l'Arena" if arena else "arrêté par l'outil, aucun refus de l'Arena",
        ),
    }


JUGES = {
    "sujet": juger_sujet,
    "temoin-negatif": juger_temoin_negatif,
    "temoin-sentinelle": juger_temoin_sentinelle,
    "temoin-classique": juger_temoin_classique,
}


def verdict(statuts: list[str]) -> str:
    """Un seul `non tenu` rend le tout non tenu ; sinon un seul `non mesuré` le rend non mesuré."""
    if NON_TENU in statuts:
        return NON_TENU
    return NON_MESURE if NON_MESURE in statuts or not statuts else TENU


# ═══ Lecture dans la base ═════════════════════════════════════════════════════════════════════════


def _entree_config(config: dict[str, Any], label: str) -> dict[str, Any]:
    for moteur in config.get("engines", []):
        if (moteur.get("label") or moteur.get("name")) == label:
            return moteur
    return {}


def _lire_bras(cx: sqlite3.Connection, experiment_id: int, config: dict[str, Any], label: str) -> Bras:
    entree = _entree_config(config, label)
    bras = Bras(
        label,
        (entree.get("visites") or config.get("repetitions")) if entree else None,
        entree.get("bannir_avant_visite"),
    )
    runs = cx.execute(
        "SELECT r.repetition, r.session_token, r.status, r.success, r.drapeaux, r.monde_id, m.nom AS monde"
        " FROM runs r JOIN engines e ON e.id = r.engine_id LEFT JOIN mondes m ON m.id = r.monde_id"
        " WHERE r.experiment_id = ? AND json_extract(e.configuration, '$.label') = ?"
        " AND r.status IN ('reussi', 'echec', 'erreur') ORDER BY r.repetition, r.id",
        (experiment_id, label),
    ).fetchall()
    jetons = [r["session_token"] for r in runs]
    refus = (
        {
            ligne["session_token"]: ligne["premier"]
            for ligne in cx.execute(
                "SELECT session_token, MIN(created_at) AS premier FROM decisions WHERE decision = 'bloque'"
                f" AND session_token IN ({','.join('?' * len(jetons))}) GROUP BY session_token",
                jetons,
            )
        }
        if jetons
        else {}
    )
    for r in runs:
        drapeaux = json.loads(r["drapeaux"] or "{}")
        details = drapeaux.get("details_scenario") or {}
        details = details if isinstance(details, dict) else {}
        visite = cx.execute("SELECT visiteur FROM visites WHERE session_token = ?", (r["session_token"],)).fetchone()
        identite = details.get("identite") or {}
        bras.visites.append(
            VisiteLue(
                rang=r["repetition"],
                session=r["session_token"],
                reussie=bool(r["success"]) and r["status"] == "reussi",
                visiteur=visite["visiteur"] if visite else None,
                empreinte=correlation.empreinte_de_session(cx, r["session_token"]),
                defis=drapeaux.get("challenges_emis"),
                identite_etat=identite.get("etat") if isinstance(identite, dict) else None,
                arret=bool(details.get("arret")),
                refusee_par_arena=r["session_token"] in refus,
            )
        )
    bras.monde = next((r["monde"] for r in runs if r["monde"]), None)
    mondes = sorted({r["monde_id"] for r in runs if r["monde_id"] is not None})
    if mondes:
        marques = ",".join("?" * len(mondes))
        bras.bannissements = [
            dict(b)
            for b in cx.execute(
                f"SELECT visiteur, empreinte, motif FROM bannissements WHERE monde_id IN ({marques}) ORDER BY id",
                mondes,
            )
        ]
    if refus:
        bras.premier_refus = min(refus.values())
        marques = ",".join("?" * len(jetons))
        base = f"FROM observations_http h WHERE h.session_token IN ({marques}) AND h.received_at > ?"
        parametres = [*jetons, bras.premier_refus]
        bras.requetes_apres_refus = cx.execute(
            f"SELECT COUNT(*) {base} AND {bannissements.clause_pages()}", parametres
        ).fetchone()[0]
        bras.requetes_apres_refus_total = cx.execute(f"SELECT COUNT(*) {base}", parametres).fetchone()[0]
    return bras


def bilan(cx: sqlite3.Connection, experiment_id: int, roles: dict[str, str] | None = None) -> dict[str, Any]:
    """Le bilan de la campagne `experiment_id` : un bloc par bras (faits, critères) et un verdict d'ensemble.

    `roles` : libellé de chaque bras, par rôle (défaut `ROLES`). Lève `LookupError` si la campagne n'existe pas."""
    ligne = cx.execute("SELECT configuration FROM experiments WHERE id = ?", (experiment_id,)).fetchone()
    if ligne is None:
        raise LookupError(f"expérience {experiment_id} introuvable")
    config = json.loads(ligne["configuration"])
    rapport: dict[str, Any] = {"campagne": experiment_id, "bras": {}}
    statuts: list[str] = []
    for role, juge in JUGES.items():
        bras = _lire_bras(cx, experiment_id, config, (roles or ROLES).get(role, ROLES[role]))
        criteres = juge(bras)
        statuts += [c["statut"] for c in criteres.values()]
        rapport["bras"][role] = {
            "label": bras.label,
            "monde": bras.monde,
            "visites_prevues": bras.prevues,
            "visites_faites": bras.faites,
            "visites_reussies": bras.reussies,
            "bannissements": len(bras.bannissements),
            "criteres": criteres,
            **(
                {"premiere_visite_arretee": next((v.rang for v in bras.visites if not v.reussie), None)}
                if role == "temoin-negatif"
                else {}
            ),
            **(
                {
                    "premiere_visite_refusee": min((v.rang for v in bras.visites if v.refusee_par_arena), default=None),
                    "requetes_apres_403": bras.requetes_apres_refus,
                }
                if role == "temoin-sentinelle"
                else {}
            ),
        }
    rapport["verdict"] = verdict(statuts)
    return rapport


def texte(rapport: dict[str, Any]) -> str:
    """Le bilan pour le terminal."""
    lignes = [f"Soirée, campagne {rapport['campagne']} : {rapport['verdict'].upper()}"]
    for role, bras in rapport["bras"].items():
        lignes.append(
            f"\n{role} ({bras['label']}) : {bras['visites_faites']} visite(s) faite(s) sur "
            f"{bras['visites_prevues']} prévue(s), {bras['visites_reussies']} réussie(s)"
        )
        for nom, critere in bras["criteres"].items():
            lignes.append(f"  {critere['statut']:<10} {nom} : {critere['detail']}")
    return "\n".join(lignes)
