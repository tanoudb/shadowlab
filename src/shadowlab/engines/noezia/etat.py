"""État d'une récolte : une base SQLite par recette (`outputs/recoltes/<nom>/etat.sqlite3`).

C'est la vérité de la récolte : passes, file de pages, enregistrements, événements. Une page lue = une
transaction (page faite, enregistrements et liens neufs écrits ensemble, ou rien). La file est la table `pages` :
profondeur d'abord (la dernière page empilée sort la première ; les enfants d'une page sont empilés dans l'ordre
inverse pour que le premier sorte en premier). Base à part : aucune migration de la base du labo.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit

from .recettes import Enregistrement

_PORTS_PAR_DEFAUT = {"http": 80, "https": 443}


def canonique(adresse: str, ignores: Iterable[str] = ()) -> str:
    """Adresse canonique : schéma et hôte en minuscules, port par défaut et fragment retirés, paramètres
    ignorés retirés, autres paramètres triés. La casse du chemin est gardée."""
    morceaux = urlsplit(adresse.strip())
    schema = morceaux.scheme.lower()
    hote = (morceaux.hostname or "").lower()
    if ":" in hote:
        hote = f"[{hote}]"
    port = morceaux.port
    if port is not None and port != _PORTS_PAR_DEFAUT.get(schema):
        hote = f"{hote}:{port}"
    ignores = set(ignores)
    parametres = sorted((n, v) for n, v in parse_qsl(morceaux.query, keep_blank_values=True) if n not in ignores)
    requete = f"?{urlencode(parametres)}" if parametres else ""
    return f"{schema}://{hote}{morceaux.path or '/'}{requete}"


@dataclass(frozen=True)
class Page:
    id: int
    passe: int
    adresse: str  # celle qu'on demande : la première forme rencontrée
    type: str
    canon: str


@dataclass(frozen=True)
class Empilement:
    neufs: int
    deja_vus: int
    exclus: int  # refusés par un plafond de type


_SCHEMA = """
CREATE TABLE IF NOT EXISTS passes (
    numero INTEGER PRIMARY KEY,
    debut TEXT NOT NULL, fin TEXT,
    statut TEXT NOT NULL,
    recette TEXT NOT NULL, empreinte TEXT NOT NULL, texte_recette TEXT NOT NULL, chemin_recette TEXT NOT NULL,
    moteur TEXT NOT NULL, options TEXT NOT NULL, arret TEXT, robots TEXT
);
CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY,
    passe INTEGER NOT NULL REFERENCES passes(numero),
    adresse TEXT NOT NULL, canon TEXT NOT NULL, type TEXT NOT NULL,
    etat TEXT NOT NULL, seq INTEGER NOT NULL,
    statut INTEGER, decision TEXT,
    duree_chargement_ms REAL, duree_totale_ms REAL,
    lu_le TEXT, rang_lecture INTEGER,
    enregistrements INTEGER NOT NULL DEFAULT 0, liens_neufs INTEGER NOT NULL DEFAULT 0,
    liens_hors_site INTEGER NOT NULL DEFAULT 0, liens_exclus INTEGER NOT NULL DEFAULT 0,
    relocalisations INTEGER NOT NULL DEFAULT 0,
    UNIQUE (passe, canon)
);
CREATE INDEX IF NOT EXISTS pages_file ON pages (passe, etat, seq);
CREATE TABLE IF NOT EXISTS enregistrements (
    id INTEGER PRIMARY KEY,
    collection TEXT NOT NULL, cle TEXT NOT NULL,
    donnees TEXT NOT NULL, empreinte TEXT NOT NULL, page TEXT NOT NULL, relocalises TEXT NOT NULL,
    premiere_passe INTEGER NOT NULL, derniere_passe INTEGER NOT NULL, vu_le TEXT NOT NULL,
    UNIQUE (collection, cle)
);
CREATE TABLE IF NOT EXISTS evenements (
    id INTEGER PRIMARY KEY, passe INTEGER NOT NULL, quand TEXT NOT NULL, genre TEXT NOT NULL, detail TEXT NOT NULL
);
"""

_JSON = ("moteur", "options", "arret", "robots")


def _json(valeur: Any) -> str:
    return json.dumps(valeur, ensure_ascii=False)


class Etat:
    def __init__(self, chemin: Path) -> None:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        self.chemin = chemin
        self._cx = sqlite3.connect(chemin, isolation_level=None)  # transactions écrites à la main
        self._cx.row_factory = sqlite3.Row
        self._profondeur = 0
        tables = {r[0] for r in self._cx.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if tables and "passes" not in tables:
            self._cx.close()
            raise ValueError(f"{chemin} n'est pas un état de récolte (table des passes absente)")
        self._cx.execute("PRAGMA journal_mode = WAL")
        self._cx.execute("PRAGMA synchronous = NORMAL")
        self._cx.executescript(_SCHEMA)

    def fermer(self) -> None:
        self._cx.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Une transaction ; imbriquée, elle se joint à celle qui est ouverte."""
        if self._profondeur == 0:
            self._cx.execute("BEGIN IMMEDIATE")
        self._profondeur += 1
        try:
            yield
        except BaseException:
            self._profondeur -= 1
            if self._profondeur == 0:
                self._cx.execute("ROLLBACK")
            raise
        self._profondeur -= 1
        if self._profondeur == 0:
            self._cx.execute("COMMIT")

    # ── Passes ──────────────────────────────────────────────────────────
    def ouvrir_passe(
        self,
        recette: str,
        empreinte: str,
        texte_recette: str,
        chemin_recette: str,
        moteur: Mapping[str, Any],
        options: Mapping[str, Any],
        quand: str,
    ) -> int:
        with self.transaction():
            numero = self._cx.execute("SELECT COALESCE(MAX(numero), 0) + 1 FROM passes").fetchone()[0]
            self._cx.execute(
                "INSERT INTO passes (numero, debut, statut, recette, empreinte, texte_recette, chemin_recette,"
                " moteur, options) VALUES (?, ?, 'en_cours', ?, ?, ?, ?, ?, ?)",
                (numero, quand, recette, empreinte, texte_recette, chemin_recette, _json(moteur), _json(options)),
            )
        return numero

    @staticmethod
    def _passe(ligne: sqlite3.Row | None) -> dict[str, Any] | None:
        if ligne is None:
            return None
        donnees = dict(ligne)
        for cle in _JSON:
            if donnees[cle] is not None:
                donnees[cle] = json.loads(donnees[cle])
        return donnees

    def passe(self, numero: int) -> dict[str, Any]:
        ligne = self._passe(self._cx.execute("SELECT * FROM passes WHERE numero = ?", (numero,)).fetchone())
        if ligne is None:
            raise KeyError(f"passe {numero} inconnue")
        return ligne

    def derniere_passe(self) -> dict[str, Any] | None:
        return self._passe(self._cx.execute("SELECT * FROM passes ORDER BY numero DESC LIMIT 1").fetchone())

    def terminer_passe(self, numero: int, statut: str, arret: Mapping[str, Any] | None, quand: str) -> None:
        with self.transaction():
            self._cx.execute(
                "UPDATE passes SET statut = ?, arret = ?, fin = ? WHERE numero = ?",
                (statut, None if arret is None else _json(arret), quand, numero),
            )

    def reprendre_passe(self, numero: int) -> int:
        """Remet la passe « en cours » et ses pages « en cours » (coupure) à faire. Rend leur nombre."""
        with self.transaction():
            remises = self._cx.execute(
                "UPDATE pages SET etat = 'a_faire' WHERE passe = ? AND etat = 'en_cours'", (numero,)
            ).rowcount
            self._cx.execute(
                "UPDATE passes SET statut = 'en_cours', arret = NULL, fin = NULL WHERE numero = ?", (numero,)
            )
        return remises

    def enregistrer_robots(self, numero: int, robots: Mapping[str, Any]) -> None:
        with self.transaction():
            self._cx.execute("UPDATE passes SET robots = ? WHERE numero = ?", (_json(robots), numero))

    def changer_recette(self, numero: int, empreinte: str, texte_recette: str) -> None:
        with self.transaction():
            self._cx.execute(
                "UPDATE passes SET empreinte = ?, texte_recette = ? WHERE numero = ?",
                (empreinte, texte_recette, numero),
            )

    def effacer_enregistrements(self) -> None:
        with self.transaction():
            self._cx.execute("DELETE FROM enregistrements")

    # ── File ────────────────────────────────────────────────────────────
    def empiler(
        self,
        passe: int,
        liens: Sequence[tuple[str, str]],
        ignores: Iterable[str] = (),
        plafonds: Mapping[str, int] | None = None,
    ) -> Empilement:
        """Met en file les liens neufs (adresse, type), dans l'ordre : le premier sortira en premier.

        Un lien dont l'adresse canonique existe déjà dans la passe garde sa place. `plafonds` : nombre maximal
        de pages d'un type dans la passe ; au-delà, le lien est exclu.
        """
        ignores = list(ignores)
        neufs: list[tuple[str, str, str]] = []
        deja_vus = exclus = 0
        with self.transaction():
            par_type = dict(
                self._cx.execute("SELECT type, COUNT(*) FROM pages WHERE passe = ? GROUP BY type", (passe,))
            )
            vus: set[str] = set()
            for adresse, type_page in liens:
                canon = canonique(adresse, ignores)
                existe = (
                    canon in vus
                    or self._cx.execute("SELECT 1 FROM pages WHERE passe = ? AND canon = ?", (passe, canon)).fetchone()
                )
                if existe:
                    deja_vus += 1
                    continue
                if plafonds and type_page in plafonds and par_type.get(type_page, 0) >= plafonds[type_page]:
                    exclus += 1
                    continue
                vus.add(canon)
                par_type[type_page] = par_type.get(type_page, 0) + 1
                neufs.append((adresse.strip(), type_page, canon))
            seq = self._cx.execute("SELECT COALESCE(MAX(seq), 0) FROM pages WHERE passe = ?", (passe,)).fetchone()[0]
            for adresse, type_page, canon in reversed(neufs):  # le premier lien reçoit le plus grand rang
                seq += 1
                self._cx.execute(
                    "INSERT INTO pages (passe, adresse, canon, type, etat, seq) VALUES (?, ?, ?, ?, 'a_faire', ?)",
                    (passe, adresse, canon, type_page, seq),
                )
        return Empilement(len(neufs), deja_vus, exclus)

    @staticmethod
    def _page(ligne: sqlite3.Row) -> Page:
        return Page(ligne["id"], ligne["passe"], ligne["adresse"], ligne["type"], ligne["canon"])

    def prochaine(self, passe: int) -> Page | None:
        """Dépile la page suivante (profondeur d'abord) et la marque « en cours »."""
        with self.transaction():
            ligne = self._cx.execute(
                "SELECT * FROM pages WHERE passe = ? AND etat = 'a_faire' ORDER BY seq DESC LIMIT 1", (passe,)
            ).fetchone()
            if ligne is None:
                return None
            self._cx.execute("UPDATE pages SET etat = 'en_cours' WHERE id = ?", (ligne["id"],))
        return self._page(ligne)

    def rendre(self, page: Page) -> None:
        """Remet une page « en cours » en file, à sa place."""
        with self.transaction():
            self._cx.execute("UPDATE pages SET etat = 'a_faire' WHERE id = ? AND etat = 'en_cours'", (page.id,))

    def terminer_page(
        self,
        page: Page,
        *,
        etat: str,
        decision: str,
        quand: str,
        statut: int | None = None,
        duree_chargement_ms: float | None = None,
        duree_totale_ms: float | None = None,
        enregistrements: Sequence[Enregistrement] = (),
        liens: Sequence[tuple[str, str]] = (),
        ignores: Iterable[str] = (),
        plafonds: Mapping[str, int] | None = None,
        hors_site: int = 0,
        exclus: int = 0,
    ) -> Empilement:
        """Écrit en une transaction : l'état de la page, ses enregistrements et ses liens neufs."""
        with self.transaction():
            for e in enregistrements:
                self._ecrire_enregistrement(page, e, quand)
            empilement = self.empiler(page.passe, liens, ignores, plafonds)
            lue = etat in ("faite", "echec")
            rang = None
            if lue:
                rang = self._cx.execute(
                    "SELECT COALESCE(MAX(rang_lecture), 0) + 1 FROM pages WHERE passe = ?", (page.passe,)
                ).fetchone()[0]
            self._cx.execute(
                "UPDATE pages SET etat = ?, statut = ?, decision = ?, duree_chargement_ms = ?, duree_totale_ms = ?,"
                " lu_le = ?, rang_lecture = ?, enregistrements = ?, liens_neufs = ?, liens_hors_site = ?,"
                " liens_exclus = ?, relocalisations = ? WHERE id = ?",
                (
                    etat,
                    statut,
                    decision,
                    duree_chargement_ms,
                    duree_totale_ms,
                    quand if lue else None,
                    rang,
                    len(enregistrements),
                    empilement.neufs,
                    hors_site,
                    exclus + empilement.exclus,
                    sum(len(e.relocalises) for e in enregistrements),
                    page.id,
                ),
            )
        return empilement

    def _ecrire_enregistrement(self, page: Page, e: Enregistrement, quand: str) -> None:
        donnees = _json(e.donnees)
        empreinte = hashlib.sha256(json.dumps(e.donnees, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        self._cx.execute(
            "INSERT INTO enregistrements (collection, cle, donnees, empreinte, page, relocalises, premiere_passe,"
            " derniere_passe, vu_le) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (collection, cle) DO UPDATE SET donnees = excluded.donnees, empreinte = excluded.empreinte,"
            " page = excluded.page, relocalises = excluded.relocalises, derniere_passe = excluded.derniere_passe,"
            " vu_le = excluded.vu_le",
            (
                e.collection,
                _json(list(e.cle)),
                donnees,
                empreinte,
                page.adresse,
                _json(list(e.relocalises)),
                page.passe,
                page.passe,
                quand,
            ),
        )

    # ── Lecture ─────────────────────────────────────────────────────────
    def pages(self, passe: int, etat: str) -> int:
        return self._cx.execute("SELECT COUNT(*) FROM pages WHERE passe = ? AND etat = ?", (passe, etat)).fetchone()[0]

    def lignes_pages(self, passe: int) -> list[dict[str, Any]]:
        """Le journal : une ligne par page lue, dans l'ordre de lecture."""
        lignes = self._cx.execute(
            "SELECT * FROM pages WHERE passe = ? AND rang_lecture IS NOT NULL ORDER BY rang_lecture", (passe,)
        )
        return [dict(ligne) for ligne in lignes]

    def dernieres_lues(self, passe: int, n: int) -> list[dict[str, Any]]:
        lignes = self._cx.execute(
            "SELECT type, decision, statut, adresse FROM pages WHERE passe = ? AND rang_lecture IS NOT NULL"
            " ORDER BY rang_lecture DESC LIMIT ?",
            (passe, n),
        ).fetchall()
        return [dict(ligne) for ligne in reversed(lignes)]

    def compteurs(self, passe: int) -> dict[str, int]:
        par_etat = dict(self._cx.execute("SELECT etat, COUNT(*) FROM pages WHERE passe = ? GROUP BY etat", (passe,)))
        par_decision = dict(
            self._cx.execute("SELECT decision, COUNT(*) FROM pages WHERE passe = ? GROUP BY decision", (passe,))
        )
        somme = self._cx.execute(
            "SELECT COALESCE(SUM(liens_hors_site), 0), COALESCE(SUM(liens_exclus), 0),"
            " COALESCE(SUM(relocalisations), 0) FROM pages WHERE passe = ?",
            (passe,),
        ).fetchone()
        return {
            "faites": par_etat.get("faite", 0),
            "echecs": par_etat.get("echec", 0),
            "interdites_robots": par_decision.get("interdite", 0),
            "anormales": par_decision.get("anormale", 0),
            "introuvables": par_decision.get("introuvable", 0),
            "hors_site": somme[0] + par_decision.get("hors_hotes", 0),
            "liens_exclus": somme[1],
            "relocalisations": somme[2],
            "a_faire": par_etat.get("a_faire", 0),
            "en_cours": par_etat.get("en_cours", 0),
            "lues": par_etat.get("faite", 0) + par_etat.get("echec", 0),
        }

    def faites_par_type(self, passe: int) -> dict[str, int]:
        lignes = self._cx.execute(
            "SELECT type, COUNT(*) FROM pages WHERE passe = ? AND etat = 'faite' GROUP BY type ORDER BY type", (passe,)
        )
        return dict(lignes)

    def adresses_lues(self, passe: int) -> list[str]:
        """Adresses des pages faites : ce que `noter_pages` compare aux pages attendues."""
        lignes = self._cx.execute(
            "SELECT adresse FROM pages WHERE passe = ? AND etat = 'faite' AND statut = 200 ORDER BY rang_lecture",
            (passe,),
        )
        return [r[0] for r in lignes]

    def collections(self) -> list[str]:
        return [r[0] for r in self._cx.execute("SELECT DISTINCT collection FROM enregistrements ORDER BY collection")]

    def nb_enregistrements(self) -> dict[str, int]:
        lignes = self._cx.execute(
            "SELECT collection, COUNT(*) FROM enregistrements GROUP BY collection ORDER BY collection"
        )
        return dict(lignes)

    def enregistrements(self, collection: str | None = None) -> list[dict[str, Any]]:
        """Les enregistrements connus, dans l'ordre de première lecture, avec les clés `_page`, `_vu_le`, `_passe`
        (et `_relocalises` s'il y en a eu)."""
        requete = "SELECT * FROM enregistrements" + (" WHERE collection = ?" if collection else "") + " ORDER BY id"
        rendus = []
        for ligne in self._cx.execute(requete, (collection,) if collection else ()):
            donnees = json.loads(ligne["donnees"])
            donnees["_page"] = ligne["page"]
            donnees["_vu_le"] = ligne["vu_le"]
            donnees["_passe"] = ligne["derniere_passe"]
            relocalises = json.loads(ligne["relocalises"])
            if relocalises:
                donnees["_relocalises"] = relocalises
            rendus.append(donnees)
        return rendus

    # ── Événements ──────────────────────────────────────────────────────
    def evenement(self, passe: int, genre: str, detail: Mapping[str, Any], quand: str) -> None:
        with self.transaction():
            self._cx.execute(
                "INSERT INTO evenements (passe, quand, genre, detail) VALUES (?, ?, ?, ?)",
                (passe, quand, genre, _json(detail)),
            )

    def evenements(self, passe: int) -> list[dict[str, Any]]:
        lignes = self._cx.execute("SELECT * FROM evenements WHERE passe = ? ORDER BY id", (passe,))
        return [{"quand": r["quand"], "genre": r["genre"], "detail": json.loads(r["detail"])} for r in lignes]
