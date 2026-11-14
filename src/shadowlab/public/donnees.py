"""Base de l'application publique : sessions humaines consenties, observations, suppression et purge, fréquentation.

Même schéma que le laboratoire (`database.MIGRATIONS`), dans un autre fichier, plus une seule table à elle,
`frequentation` (trois nombres par jour, D-75), créée ici et non par une migration du labo. Une base qui contient
une autre expérience que les sessions publiques est refusée : une purge ne doit jamais toucher une campagne.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from .. import database as db

EXPERIENCE = "sessions-publiques"
MOTEUR = ("navigateur-public", "n/a", "humain")
SCENARIO = ("navigation_publique", "Navigation libre sur le site vitrine public, après consentement")
JETON = re.compile(r"[0-9a-f]{32}")

# Liste blanche des en-têtes gardés : ceux que lisent les détecteurs, rien d'autre. Ni adresse IP
# (X-Forwarded-For, CF-Connecting-IP, X-Real-IP, Forwarded, True-Client-IP…), ni cookie, ni pays.
ENTETES_GARDES = (
    "host",
    "user-agent",
    "accept",
    "accept-language",
    "accept-encoding",
    "referer",
    "upgrade-insecure-requests",
    "upgrade",
    "dnt",
    "sec-gpc",
    "priority",
    "cache-control",
    "pragma",
    "connection",
    "te",
    "origin",
    "content-type",
    "content-length",
)
PREFIXES_GARDES = ("sec-ch-", "sec-fetch-")
# Bornes d'une requête notée : au pire ~2,4 Ko par ligne, quels que soient les en-têtes envoyés.
TAILLE_MAX_NOM = 64
TAILLE_MAX_VALEUR = 512
ENTETES_MAX = 40
TAILLE_MAX_ENTETES = 2048  # octets du JSON des en-têtes gardés
TAILLE_MAX_METHODE = 16
TAILLE_MAX_CHEMIN = 200
# Adresse interne d'une extension de navigateur (traces d'erreur) : son identifiant peut désigner une personne.
EXTENSION = re.compile(r"\b([a-z][a-z0-9+.-]*-extension)://[^/\s\"'\\)]+", re.I)
# Fréquentation (D-75) : le jour et trois nombres, rien d'autre. Ni adresse, ni identifiant, ni navigateur, ni heure.
# Hors des sessions : ni la suppression d'une session ni la purge n'y touchent.
SCHEMA_FREQUENTATION = """CREATE TABLE IF NOT EXISTS frequentation (
    jour TEXT PRIMARY KEY,  -- jour UTC, AAAA-MM-JJ
    accueil INTEGER NOT NULL DEFAULT 0,  -- chargements de la page d'accueil (GET)
    commencees INTEGER NOT NULL DEFAULT 0,  -- sessions commencées
    terminees INTEGER NOT NULL DEFAULT 0  -- sessions terminées par « Terminer ma session »
)"""
COMPTES = ("accueil", "commencees", "terminees")


def _resserrer(chemin: Path, mode: int) -> None:
    """Droits `mode` sur un chemin à nous ; un chemin d'un autre propriétaire n'est pas touché."""
    if chemin.stat().st_uid == os.getuid():
        chemin.chmod(mode)


def creer_prive(chemin: Path) -> None:
    """Prépare un fichier de base : son dossier en 700, le fichier en 600, avant que SQLite ne l'ouvre.

    Le fichier vide est créé avec le bon mode (`O_EXCL`, mode 600), puis seulement ouvert par SQLite : il n'existe
    jamais avec des droits plus larges. Le journal et les fichiers `-wal` et `-shm` prennent les droits de la base ;
    ceux d'un lancement plus ancien sont resserrés aussi. Un dossier ou un fichier qui existe déjà est resserré.
    """
    dossier = chemin.parent
    dossier.mkdir(parents=True, exist_ok=True, mode=0o700)
    _resserrer(dossier, 0o700)
    try:
        os.close(os.open(chemin, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    except FileExistsError:
        pass
    for fichier in (chemin, chemin.with_name(chemin.name + "-wal"), chemin.with_name(chemin.name + "-shm")):
        if fichier.exists():
            _resserrer(fichier, 0o600)


def connexion(chemin: Path) -> sqlite3.Connection:
    """Connexion à la base publique (créée au besoin en 600, dans un dossier en 700). `secure_delete` vide les pages
    d'une ligne effacée dans la base ; il ne garantit pas l'écrasement physique (voir docs/site-public.md)."""
    creer_prive(chemin)
    cx = db.ouvrir(chemin)
    cx.execute("PRAGMA secure_delete=ON")
    cx.execute(SCHEMA_FREQUENTATION)
    return cx


def verifier_base(cx: sqlite3.Connection, chemin: Path) -> None:
    autre = cx.execute("SELECT name FROM experiments WHERE name != ? LIMIT 1", (EXPERIENCE,)).fetchone()
    if autre:
        raise ValueError(
            f"{chemin} n'est pas une base publique : elle contient l'expérience « {autre['name']} ». "
            "Donner à SHADOWLAB_PUBLIC_BASE un fichier à part, jamais la base du laboratoire."
        )


def ouvrir(chemin: Path) -> sqlite3.Connection:
    """Connexion vérifiée : refuse la base du laboratoire."""
    cx = connexion(chemin)
    try:
        verifier_base(cx, chemin)
    except ValueError:
        cx.close()
        raise
    return cx


def taille(chemin: Path) -> int:
    """Taille sur le disque de la base et de son journal WAL. Elle ne baisse jamais : SQLite garde dans le fichier
    les pages libérées par une suppression (ni VACUUM, ni auto_vacuum) et les réutilise."""
    return sum(p.stat().st_size for p in (chemin, chemin.with_name(chemin.name + "-wal")) if p.exists())


def occupation(chemin: Path) -> int:
    """Octets réellement occupés : pages utilisées de la base, `(page_count - freelist_count) × page_size`, plus la
    taille du journal WAL. Les pages libérées par une suppression ou la purge n'y comptent plus."""
    journal = chemin.with_name(chemin.name + "-wal")
    octets_journal = journal.stat().st_size if journal.exists() else 0
    cx = sqlite3.connect(chemin, timeout=30)  # connexion nue : trois lectures d'en-tête, sans migration
    try:
        pages, libres, taille_page = (cx.execute(f"PRAGMA {p}").fetchone()[0] for p in PRAGMAS_OCCUPATION)
    finally:
        cx.close()
    return (pages - libres) * taille_page + octets_journal


PRAGMAS_OCCUPATION = ("page_count", "freelist_count", "page_size")


def au_plafond(chemin: Path, plafond: int) -> bool:
    """Base pleine : le fichier et son journal atteignent `plafond` ET les pages réellement occupées aussi
    (`occupation`). Appelée à chaque requête : tant que les fichiers tiennent sous le plafond, aucune connexion n'est
    ouverte. Au-dessus, une suppression ou la purge rouvre le service dès que les pages libérées le permettent."""
    if not chemin.exists() or taille(chemin) < plafond:
        return False
    return occupation(chemin) >= plafond


# --- Sessions ----------------------------------------------------------------------------------


def _experience(cx: sqlite3.Connection) -> int:
    ligne = cx.execute("SELECT id FROM experiments WHERE name = ?", (EXPERIENCE,)).fetchone()
    if ligne:
        return int(ligne["id"])
    configuration = db.j({"environment": "public", "truth": "humain"})
    return int(
        cx.execute(
            "INSERT INTO experiments (id, name, description, created_at, configuration, status)"
            f" VALUES ({db.PROCHAIN_ID_EXPERIENCE}, ?, ?, ?, ?, ?)",
            (
                EXPERIENCE,
                "Sessions humaines consenties sur le site public",
                db.maintenant(),
                configuration,
                "permanente",
            ),
        ).lastrowid
    )


def creer_session(cx: sqlite3.Connection, accord: dict) -> str:
    """Passage humain en cours, consentement daté. `accord` garde la version du texte accepté."""
    jeton = secrets.token_hex(16)
    with db.transaction(cx):
        experience = _experience(cx)
        moteur = db.engine_id(cx, *MOTEUR, {})
        scenario = db.scenario_id(cx, *SCENARIO)
        maintenant = db.maintenant()
        cx.execute(
            "INSERT INTO runs (experiment_id, engine_id, scenario_id, repetition, session_token, truth, started_at,"
            " status, consent_at, protection_config) VALUES (?, ?, ?, 1, ?, 'humain', ?, 'en_cours', ?, ?)",
            (experience, moteur, scenario, jeton, maintenant, maintenant, db.j(accord)),
        )
    return jeton


# Une session en cours : publique, humaine, consentie, ni terminée ni plus vieille que la durée maximale. Paramètres :
# jeton, nom de l'expérience, début au plus tôt.
SESSION_EN_COURS = (
    "SELECT 1 FROM runs r JOIN experiments e ON e.id = r.experiment_id WHERE r.session_token = ? AND e.name = ?"
    " AND r.truth = 'humain' AND r.status = 'en_cours' AND r.consent_at IS NOT NULL AND r.started_at >= ?"
)


def _debut_au_plus_tot(duree_max_s: int) -> str:
    return (datetime.now(UTC) - timedelta(seconds=duree_max_s)).isoformat(timespec="milliseconds")


def session_en_cours(cx: sqlite3.Connection, jeton: str, duree_max_s: int) -> bool:
    """Vrai pour une session publique, humaine, consentie, ni terminée ni plus vieille que `duree_max_s`."""
    return cx.execute(SESSION_EN_COURS, (jeton, EXPERIENCE, _debut_au_plus_tot(duree_max_s))).fetchone() is not None


def session_existe(cx: sqlite3.Connection, jeton: str) -> bool:
    """Vrai tant que la session publique est en base (ni supprimée, ni purgée), terminée ou non."""
    ligne = cx.execute(
        "SELECT 1 FROM runs r JOIN experiments e ON e.id = r.experiment_id WHERE r.session_token = ? AND e.name = ?",
        (jeton, EXPERIENCE),
    ).fetchone()
    return ligne is not None


def langue_de_session(cx: sqlite3.Connection, jeton: str) -> str | None:
    """Langue notée avec l'accord de la session (`protection_config`), ou None (session absente, accord plus ancien
    que les deux langues, valeur illisible). L'appelant la vérifie contre les langues servies."""
    ligne = cx.execute("SELECT protection_config FROM runs WHERE session_token = ?", (jeton,)).fetchone()
    try:
        accord = json.loads(ligne[0]) if ligne and ligne[0] else None
    except ValueError:
        return None
    langue = accord.get("langue") if isinstance(accord, dict) else None
    return langue if isinstance(langue, str) else None


def clore_session(cx: sqlite3.Connection, jeton: str) -> bool:
    """Passe la session de « en cours » à « terminée ». Vrai seulement pour la requête qui l'a fait : la condition
    est dans la mise à jour elle-même, donc une session n'est close (et comptée) qu'une fois, même si plusieurs
    « Terminer » arrivent ensemble."""
    ligne = cx.execute(
        "SELECT id, started_at FROM runs WHERE session_token = ? AND status = 'en_cours'", (jeton,)
    ).fetchone()
    if ligne is None:
        return False
    fin = datetime.now(UTC)
    duree = (fin - datetime.fromisoformat(ligne["started_at"])).total_seconds() * 1000
    curseur = cx.execute(
        "UPDATE runs SET status = 'reussi', success = 1, completed_at = ?, duration_ms = ?"
        " WHERE id = ? AND status = 'en_cours'",
        (fin.isoformat(timespec="milliseconds"), round(duree), ligne["id"]),
    )
    return curseur.rowcount == 1


def sessions_du_jour(cx: sqlite3.Connection) -> int:
    minuit = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="milliseconds")
    return int(cx.execute("SELECT COUNT(*) FROM runs WHERE started_at >= ?", (minuit,)).fetchone()[0])


# --- Observations ------------------------------------------------------------------------------


def _referent(valeur: str, hote: str) -> str:
    """Un référent du site lui-même se réduit à son chemin ; un référent extérieur n'est pas gardé."""
    try:
        morceaux = urlsplit(valeur)
    except ValueError:
        return "externe"
    return (morceaux.path or "/") if morceaux.netloc.lower() == hote.lower() else "externe"


def entetes_gardes(paires: list[tuple[str, str]], hote: str) -> list[list[str]]:
    """En-têtes de la liste blanche, dans l'ordre reçu : noms, valeurs, nombre et taille totale bornés."""
    gardes: list[list[str]] = []
    taille = 2  # crochets du JSON
    for nom, valeur in paires:
        cle = nom.lower()
        if len(cle) > TAILLE_MAX_NOM or not (cle in ENTETES_GARDES or cle.startswith(PREFIXES_GARDES)):
            continue
        if cle == "referer":
            valeur = _referent(valeur, hote)
        paire = [nom, valeur[:TAILLE_MAX_VALEUR]]
        poids = len(db.j(paire).encode()) + 2  # séparateur « , » compris
        if len(gardes) >= ENTETES_MAX or taille + poids > TAILLE_MAX_ENTETES:
            break
        gardes.append(paire)
        taille += poids
    return gardes


def noter_requete(
    cx: sqlite3.Connection, jeton: str, methode: str, chemin: str, version: str | None, entetes: list, plafond: int
) -> None:
    """Une requête de la session, sans cookie ni chaîne de requête. Au-delà du plafond, plus rien n'est noté."""
    deja = cx.execute("SELECT COUNT(*) FROM observations_http WHERE session_token = ?", (jeton,)).fetchone()[0]
    if deja >= plafond:
        return
    cx.execute(
        "INSERT INTO observations_http (session_token, received_at, method, path, http_version, headers, cookies)"
        " VALUES (?, ?, ?, ?, ?, ?, '[]')",
        (
            jeton,
            db.maintenant(),
            methode[:TAILLE_MAX_METHODE],
            chemin[:TAILLE_MAX_CHEMIN],
            version[:8] if version else None,
            db.j(entetes),
        ),
    )


def masquer_extensions(texte: str) -> str:
    """`chrome-extension://<id>/…` → `chrome-extension://masque/…` (et `moz-`, `safari-web-`… de même)."""
    return EXTENSION.sub(lambda m: f"{m.group(1)}://masque", texte)


def usage(cx: sqlite3.Connection, jeton: str, trace: bool = False) -> tuple[int, int]:
    """Nombre d'envois JavaScript de la session et leur volume en octets : ceux de l'observateur (empreinte,
    comportement), ou, avec `trace`, ceux du relevé enrichi (D-76), comptés à part."""
    n, volume = cx.execute(
        "SELECT COUNT(*), COALESCE(SUM(LENGTH(CAST(payload AS BLOB))), 0) FROM observations_js"
        " WHERE session_token = ? AND (kind = 'trace') = ?",
        (jeton, trace),
    ).fetchone()
    return int(n), int(volume)


def noter_collecte(cx: sqlite3.Connection, jeton: str, kind: str, page: str, charge: str, duree_max_s: int) -> bool:
    """Écrit un envoi, seulement si la session est encore en cours : la vérification est dans l'écriture elle-même
    (`INSERT … SELECT … WHERE EXISTS`), sans attente possible entre les deux. Un envoi encore en vol pendant
    « Supprimer ma session » ou « Terminer » n'écrit donc rien (faux)."""
    curseur = cx.execute(
        "INSERT INTO observations_js (session_token, received_at, kind, page, payload) SELECT ?, ?, ?, ?, ?"
        f" WHERE EXISTS ({SESSION_EN_COURS})",
        (jeton, db.maintenant(), kind, page, charge, jeton, EXPERIENCE, _debut_au_plus_tot(duree_max_s)),
    )
    return curseur.rowcount == 1


def lister_sessions(cx: sqlite3.Connection, duree_max_s: int) -> list[dict]:
    """Chaque session, la plus grosse d'abord, pour repérer une session abusive (`shadowlab public sessions`) :
    identifiant, début, état (ouverte, expirée, terminée), requêtes notées, nombre et volume des envois (octets),
    et `total`, volume des envois plus celui des requêtes notées (en-têtes et chemin), qui donne l'ordre."""
    debut_min = _debut_au_plus_tot(duree_max_s)
    lignes = cx.execute(
        "SELECT r.session_token AS jeton, r.started_at AS debut, r.status AS statut,"
        " (SELECT COUNT(*) FROM observations_http h WHERE h.session_token = r.session_token) AS requetes,"
        " (SELECT COALESCE(SUM(LENGTH(CAST(h.headers AS BLOB)) + LENGTH(CAST(h.path AS BLOB))), 0)"
        "  FROM observations_http h WHERE h.session_token = r.session_token) AS volume_requetes,"
        " (SELECT COUNT(*) FROM observations_js j WHERE j.session_token = r.session_token) AS envois,"
        " (SELECT COALESCE(SUM(LENGTH(CAST(j.payload AS BLOB))), 0)"
        "  FROM observations_js j WHERE j.session_token = r.session_token) AS volume"
        " FROM runs r JOIN experiments e ON e.id = r.experiment_id WHERE e.name = ?",
        (EXPERIENCE,),
    ).fetchall()
    resultat = []
    for ligne in lignes:
        if ligne["statut"] != "en_cours":
            etat = "terminée"
        else:
            etat = "ouverte" if ligne["debut"] >= debut_min else "expirée"
        resultat.append(
            {
                "jeton": ligne["jeton"],
                "debut": ligne["debut"],
                "etat": etat,
                "requetes": ligne["requetes"],
                "envois": ligne["envois"],
                "volume": ligne["volume"],
                "total": ligne["volume"] + ligne["volume_requetes"],
            }
        )
    return sorted(resultat, key=lambda s: (-s["total"], -s["requetes"], s["debut"]))


# --- Suppression et purge ----------------------------------------------------------------------


def effacer_session(cx: sqlite3.Connection, jeton: str) -> bool:
    """Efface la session dans toutes les tables du schéma, avec toute ligne orpheline, puis vide le journal WAL.
    Faux si elle n'existait pas."""
    if not JETON.fullmatch(jeton):
        return False
    existait = _effacer(cx, jeton)
    retirer_orphelines(cx)
    vider_journal(cx)
    return existait


# Tables où une ligne porte le jeton d'une session (`session_token`), sans clé étrangère vers `runs`.
TABLES_PAR_JETON = ("observations_http", "observations_js", "decisions")


def retirer_orphelines(cx: sqlite3.Connection) -> int:
    """Retire toute ligne d'observation dont la session n'existe plus (envoi arrivé après une suppression, base
    écrite par une version plus ancienne) : la purge part des sessions et ne la retrouverait jamais. Renvoie le
    nombre de lignes retirées."""
    sans_session = "NOT EXISTS (SELECT 1 FROM runs r WHERE r.session_token = {t}.session_token)"
    retirees = 0
    with db.transaction(cx):
        cx.execute(
            "DELETE FROM observations_tls WHERE id IN (SELECT h.tls_id FROM observations_http h WHERE h.tls_id IS NOT"
            f" NULL AND {sans_session.format(t='h')})"
        )
        for table in TABLES_PAR_JETON:
            retirees += cx.execute(f"DELETE FROM {table} WHERE {sans_session.format(t=table)}").rowcount
    return retirees


def vider_journal(cx: sqlite3.Connection) -> bool:
    """Point de contrôle complet et journal WAL remis à zéro (`wal_checkpoint(TRUNCATE)`) : les versions des pages
    d'avant une suppression ne restent pas lisibles dans le journal, et sa taille ne compte plus dans `occupation`.
    Sans attendre : si un lecteur d'un autre processus le bloque, le journal sera vidé au point de contrôle suivant
    (faux). Ne garantit rien pour le disque lui-même (voir docs/site-public.md, « Purge et suppression »)."""
    attente = cx.execute("PRAGMA busy_timeout").fetchone()[0]
    cx.execute("PRAGMA busy_timeout=0")
    try:
        bloque = cx.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]
    finally:
        cx.execute(f"PRAGMA busy_timeout={int(attente)}")
    return not bloque


def _effacer(cx: sqlite3.Connection, jeton: str) -> bool:
    with db.transaction(cx):
        runs = [(r["id"],) for r in cx.execute("SELECT id FROM runs WHERE session_token = ?", (jeton,))]
        cx.execute(
            "DELETE FROM observations_tls WHERE id IN"
            " (SELECT tls_id FROM observations_http WHERE session_token = ? AND tls_id IS NOT NULL)",
            (jeton,),
        )
        for table in ("observations_http", "observations_js", "decisions"):
            cx.execute(f"DELETE FROM {table} WHERE session_token = ?", (jeton,))
        cx.execute("DELETE FROM empreintes_vues WHERE sessions LIKE ?", (f'%"{jeton}"%',))  # jeton en hexadécimal
        for table in ("fingerprints", "detections", "metrics", "artifacts"):
            cx.executemany(f"DELETE FROM {table} WHERE run_id = ?", runs)
        cx.execute("DELETE FROM runs WHERE session_token = ?", (jeton,))
    return bool(runs)


def purger(cx: sqlite3.Connection, jours: int, maintenant: datetime | None = None) -> int:
    """Efface les sessions publiques commencées il y a plus de `jours` jours, puis toute ligne orpheline, et vide le
    journal WAL. Renvoie le nombre de sessions effacées."""
    limite = ((maintenant or datetime.now(UTC)) - timedelta(days=jours)).isoformat(timespec="milliseconds")
    jetons = [
        r["session_token"]
        for r in cx.execute(
            "SELECT r.session_token FROM runs r JOIN experiments e ON e.id = r.experiment_id"
            " WHERE e.name = ? AND r.started_at < ?",
            (EXPERIENCE, limite),
        )
    ]
    for jeton in jetons:
        _effacer(cx, jeton)
    retirer_orphelines(cx)
    vider_journal(cx)
    return len(jetons)


# --- Fréquentation (D-75) ------------------------------------------------------------------------


def compter(cx: sqlite3.Connection, compte: str, moment: datetime | None = None) -> None:
    """Ajoute 1 au compte `compte` du jour UTC (`accueil`, `commencees` ou `terminees`)."""
    if compte not in COMPTES:
        raise ValueError(f"compte inconnu : {compte}")
    jour = (moment or datetime.now(UTC)).date().isoformat()
    cx.execute(
        f"INSERT INTO frequentation (jour, {compte}) VALUES (?, 1)"
        f" ON CONFLICT (jour) DO UPDATE SET {compte} = {compte} + 1",
        (jour,),
    )


def frequentation(cx: sqlite3.Connection) -> list[sqlite3.Row]:
    """Les comptes, jour par jour, du plus ancien au plus récent."""
    return cx.execute("SELECT jour, accueil, commencees, terminees FROM frequentation ORDER BY jour").fetchall()


def sessions_terminees(cx: sqlite3.Connection) -> int:
    """Total des sessions terminées depuis le début, tous jours confondus (affiché sur l'accueil)."""
    return int(cx.execute("SELECT COALESCE(SUM(terminees), 0) FROM frequentation").fetchone()[0])
