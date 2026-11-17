"""Identité persistante du moteur : un dossier par visiteur (profil Chrome, état, journal des visites, verrou).

Disposition (I4, `docs/recherche/identite-qui-dure-2026-11-12.md` § 5.2) :

    <racine>/<nom>/identite.json   nom, date de création, état (ok, alerte, banni), `alerte_le` / `banni_le` et
                                   `raison` après un signe de la sentinelle, `porte_franchie_le` (§ 5.5)
                   chrome/         dossier de profil de Chrome (cookies, stockage, cache)
                   visites.jsonl   une ligne par visite
                   verrou          un seul processus à la fois sur une identité
                   proxy.json      facultatif : le proxy de l'identité, avec ses identifiants (0600, jamais lisible par
                                   un autre ; `docs/recherche/proxy-par-identite-2026-11-17.md`)

La racine est `outputs/identites` (ignoré par git), ou `SHADOWLAB_IDENTITES` (tests). Ce n'est jamais une
option de campagne : une option ne doit pas pouvoir pointer vers le profil d'une personne.

Après un signe d'alerte (I6, § 5.5) : `alerte` refuse l'identité pendant `ATTENTE_ALERTE_S` (1 h) sauf `maintenant` ;
`banni` la refuse pour toujours et rien ne l'efface. La sentinelle ne fait que s'arrêter : ici, on ne fait que noter.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import stat
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ...config import RACINE
from .proxy_identite import ProxyIdentite, ProxyInvalide, analyser

NOM_VALIDE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
ETATS = ("ok", "alerte", "banni")
VERDICTS = ("alerte", "banni")
ATTENTE_ALERTE_S = 3600  # une identité en alerte ne sert pas avant 1 h (comme `parcours.ATTENTE_APRES_ALERTE_S`)
FICHIER_PROXY = "proxy.json"


class IdentiteRefusee(RuntimeError):
    """L'identité ne peut pas servir maintenant (bannie, ou déjà prise par un autre lancement)."""


def verifier_nom(nom: str) -> str:
    if not isinstance(nom, str) or not NOM_VALIDE.fullmatch(nom):
        raise ValueError(
            f"nom d'identité invalide : {nom!r} (minuscules, chiffres et tirets, 40 caractères au plus, "
            "commence par une lettre ou un chiffre)"
        )
    return nom


def racine_identites() -> Path:
    valeur = os.environ.get("SHADOWLAB_IDENTITES")
    return Path(valeur) if valeur else RACINE / "outputs" / "identites"


def _maintenant() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _aware(quand: datetime) -> datetime:
    return quand if quand.tzinfo is not None else quand.replace(tzinfo=UTC)


def _date(texte: object) -> datetime | None:
    try:
        return _aware(datetime.fromisoformat(str(texte)))
    except ValueError:
        return None


def age_jours(nom: str) -> int:
    """Âge en jours de l'identité ; 0 si elle n'existe pas encore."""
    fichier = racine_identites() / verifier_nom(nom) / "identite.json"
    try:
        creee = datetime.fromisoformat(json.loads(fichier.read_text(encoding="utf-8"))["creee_le"])
    except (OSError, ValueError, KeyError):
        return 0
    return max(0, (datetime.now(UTC) - creee).days)


def lire_etat(nom: str) -> dict[str, Any] | None:
    """L'état noté de l'identité (`identite.json`), lu sans verrou ni création : la campagne le consulte avant chaque
    créneau d'un bras espacé (I9), y compris avant d'ouvrir le pilote. None si l'identité n'existe pas, ou illisible."""
    fichier = racine_identites() / verifier_nom(nom) / "identite.json"
    try:
        donnees = json.loads(fichier.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return donnees if isinstance(donnees, dict) else None


def fin_d_alerte(donnees: dict[str, Any], maintenant: datetime) -> datetime | None:
    """Quand une identité en alerte pourra resservir : `alerte_le` + `ATTENTE_ALERTE_S` (même règle que
    `controler_etat`). None si elle n'est pas en alerte. Date illisible : l'attente court depuis `maintenant`."""
    if donnees.get("etat") != "alerte":
        return None
    depuis = _date(donnees.get("alerte_le")) or _aware(maintenant)
    return depuis + timedelta(seconds=ATTENTE_ALERTE_S)


def controler_etat(
    nom: str, donnees: dict[str, Any], horloge: Callable[[], datetime], *, maintenant: bool = False
) -> None:
    """La règle d'admission d'une identité, à l'ouverture comme avant chaque visite : bannie, jamais ; en alerte,
    pas avant `ATTENTE_ALERTE_S` (sauf `maintenant`). Lève `IdentiteRefusee`."""
    etat = donnees.get("etat", "ok")
    if etat == "banni":
        raise IdentiteRefusee(f"identité {nom!r} bannie : elle ne sert plus jamais")
    if etat == "alerte" and not maintenant:
        depuis = _date(donnees.get("alerte_le"))
        ecoule = (horloge() - depuis).total_seconds() if depuis else 0.0
        if ecoule < ATTENTE_ALERTE_S:
            reste = int((ATTENTE_ALERTE_S - ecoule) // 60) + 1
            raise IdentiteRefusee(
                f"identité {nom!r} en alerte ({donnees.get('raison', 'raison inconnue')}) : "
                f"attendre encore {reste} min, ou `--maintenant`"
            )


class Identite:
    """Une identité ouverte : verrou pris, état vérifié. `liberer()` rend le verrou."""

    def __init__(self, nom: str, dossier: Path, verrou, horloge: Callable[[], datetime] | None = None) -> None:
        self.nom = nom
        self.dossier = dossier
        self._verrou = verrou
        self._horloge = horloge or (lambda: datetime.now(UTC))
        self._visite: dict[str, Any] | None = None
        self._verdict: str | None = None  # `alerte` ou `banni` marqué pendant la visite en cours

    @property
    def dossier_profil(self) -> Path:
        return self.dossier / "chrome"

    @property
    def fichier(self) -> Path:
        return self.dossier / "identite.json"

    def etat(self) -> dict[str, Any]:
        return json.loads(self.fichier.read_text(encoding="utf-8"))

    def verifier_etat(self) -> None:
        """Relit l'état et refuse si l'identité ne peut plus servir (bannie, alerte récente) : à appeler avant chaque
        lancement de Chrome, l'état ayant pu changer depuis `ouvrir` (une visite d'avant l'a marquée)."""
        controler_etat(self.nom, self.etat(), self._horloge)

    def debut_visite(self, details: dict[str, Any] | None = None) -> None:
        self._visite = {"debut": _maintenant(), **(details or {})}

    def _ecrire(self, donnees: dict[str, Any]) -> None:
        temporaire = self.fichier.with_suffix(".tmp")
        temporaire.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporaire, self.fichier)

    def marquer(self, verdict: str, raison: str, quand: datetime | None = None) -> None:
        """Note le verdict de la sentinelle (`alerte` ou `banni`) avec sa date et sa raison. Un bannissement ne se
        remplace jamais ; la visite en cours finira avec ce statut."""
        if verdict not in VERDICTS:
            raise ValueError(f"verdict inconnu : {verdict!r} (admis : {', '.join(VERDICTS)})")
        quand = _aware(quand or self._horloge())
        donnees = self.etat()
        if donnees.get("etat") != "banni":
            donnees.update({"etat": verdict, f"{verdict}_le": quand.isoformat(timespec="seconds"), "raison": raison})
            self._ecrire(donnees)
        self._verdict = "banni" if donnees.get("etat") == "banni" else verdict

    def noter_porte(self, quand: datetime) -> None:
        """Date du dernier passage de la porte d'entrée du site (défi franchi)."""
        donnees = self.etat()
        donnees["porte_franchie_le"] = _aware(quand).isoformat(timespec="seconds")
        self._ecrire(donnees)

    def porte_franchie_le(self) -> datetime | None:
        valeur = self.etat().get("porte_franchie_le")
        return _date(valeur) if valeur else None

    def fin_visite(self, pages: int, statut: str | None = None) -> None:
        """Journalise la visite. Sans `statut` : celui que la sentinelle a marqué, sinon `ok`. Une visite `ok` finie
        sur une identité qui sortait d'une alerte la remet à l'état `ok` : l'attente est derrière elle."""
        statut = statut or self._verdict or "ok"
        self._verdict = None
        if statut == "ok" and self.etat().get("etat") == "alerte":
            donnees = {k: v for k, v in self.etat().items() if k not in ("alerte_le", "raison")}
            self._ecrire({**donnees, "etat": "ok"})
        if self._visite is None:
            return
        ligne = {**self._visite, "fin": _maintenant(), "pages": pages, "statut": statut}
        self._visite = None
        with (self.dossier / "visites.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")

    def liberer(self) -> None:
        if self._verrou is not None:
            try:
                fcntl.flock(self._verrou, fcntl.LOCK_UN)
            finally:
                self._verrou.close()
                self._verrou = None


def ouvrir(nom: str, *, horloge: Callable[[], datetime] | None = None, maintenant: bool = False) -> Identite:
    """Ouvre (ou crée) l'identité : refuse si elle est bannie, en alerte depuis moins d'une heure (sauf `maintenant`),
    ou déjà utilisée par un autre lancement. L'horloge est injectable (tests)."""
    horloge = horloge or (lambda: datetime.now(UTC))
    verifier_nom(nom)
    dossier = racine_identites() / nom
    dossier.mkdir(parents=True, exist_ok=True, mode=0o700)
    dossier.chmod(0o700)
    verrou = (dossier / "verrou").open("a+")
    try:
        fcntl.flock(verrou, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        verrou.close()
        raise IdentiteRefusee(f"identité {nom!r} déjà utilisée par un autre lancement (verrou pris)") from None
    try:
        fichier = dossier / "identite.json"
        if fichier.exists():
            controler_etat(nom, json.loads(fichier.read_text(encoding="utf-8")), horloge, maintenant=maintenant)
        else:
            fichier.write_text(
                json.dumps({"nom": nom, "creee_le": _maintenant(), "etat": "ok"}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        (dossier / "chrome").mkdir(exist_ok=True, mode=0o700)
    except BaseException:
        fcntl.flock(verrou, fcntl.LOCK_UN)
        verrou.close()
        raise
    return Identite(nom, dossier, verrou, horloge)


def declarer_proxy(nom: str, serveur: str, utilisateur: str | None = None, mot_de_passe: str | None = None) -> Path:
    """Écrit le proxy de l'identité (`proxy.json`, droits 0600, dossier 0700) ; rien n'est écrit s'il est invalide. Le
    fichier est remplacé d'un coup : un ancien fichier plus ouvert ne laisse pas ses droits au nouveau."""
    verifier_nom(nom)
    analyser(serveur, utilisateur, mot_de_passe)
    dossier = racine_identites() / nom
    dossier.mkdir(parents=True, exist_ok=True, mode=0o700)
    dossier.chmod(0o700)
    champs = {"serveur": serveur, "utilisateur": utilisateur, "mot_de_passe": mot_de_passe}
    fichier = dossier / FICHIER_PROXY
    temporaire = fichier.with_suffix(".tmp")
    descripteur = os.open(temporaire, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descripteur, "w", encoding="utf-8") as f:
        os.fchmod(f.fileno(), 0o600)  # avant d'écrire : ni l'umask ni un `.tmp` laissé plus ouvert ne comptent
        json.dump({cle: valeur for cle, valeur in champs.items() if valeur is not None}, f)
    os.replace(temporaire, fichier)
    return fichier


def lire_proxy(nom: str) -> ProxyIdentite | None:
    """Le proxy déclaré de l'identité, ou None sans fichier (rien n'est créé). Lève `ProxyInvalide` si le fichier est
    lisible par le groupe ou les autres, d'un autre propriétaire, ou invalide : un proxy déclaré mais inutilisable ne
    doit jamais devenir un accès direct. Aucun message ne cite le contenu du fichier."""
    chemin = racine_identites() / verifier_nom(nom) / FICHIER_PROXY
    try:
        # Un seul descripteur pour contrôler les droits et lire (rien ne change entre les deux), sans lien symbolique.
        descripteur = os.open(chemin, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    except OSError:
        raise ProxyInvalide(f"proxy de l'identité {nom!r} : fichier illisible (lien symbolique ?)") from None
    with os.fdopen(descripteur, encoding="utf-8") as f:
        info = os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise ProxyInvalide(f"proxy de l'identité {nom!r} : fichier ordinaire de l'utilisateur attendu")
        if info.st_mode & 0o077:
            raise ProxyInvalide(f"proxy de l'identité {nom!r} : droits trop larges (0600 attendu)")
        try:
            donnees = json.load(f)
        except ValueError:
            raise ProxyInvalide(f"proxy de l'identité {nom!r} : JSON invalide") from None
    if not isinstance(donnees, dict):
        raise ProxyInvalide(f"proxy de l'identité {nom!r} : un objet JSON est attendu")
    try:
        return analyser(donnees.get("serveur"), donnees.get("utilisateur"), donnees.get("mot_de_passe"))
    except ProxyInvalide as erreur:
        raise ProxyInvalide(f"proxy de l'identité {nom!r} : {erreur}") from None
