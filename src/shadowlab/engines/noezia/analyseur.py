"""Analyseur HTML fetcher-agnostique (façon Scrapling), avec extraction adaptative SANS navigateur.

Se tient sur `parsel` (le sélecteur de Scrapy, basé sur lxml) pour le css/xpath ergonomique, et
ajoute notre différenciateur : relocaliser un élément par ressemblance quand le sélecteur a cassé,
calculé en Python pur sur le HTML parsé — donc utilisable par n'importe quel moteur (y compris le
HTTP brut, ultra-rapide), pas seulement le navigateur.
"""

from __future__ import annotations

from typing import Any

from parsel import Selector

from . import extraction


def _features(element: Any) -> dict[str, Any]:
    """Caractéristiques d'un élément lxml, même format que la capture JS du navigateur."""
    classes = (element.get("class") or "").split()
    texte = " ".join(element.itertext()).strip()
    profondeur = sum(1 for _ in element.iterancestors())
    tag = element.tag if isinstance(element.tag, str) else ""
    return {
        "tag": tag,
        "classes": classes,
        "id": element.get("id") or "",
        "texte": texte[:200],
        "profondeur": profondeur,
    }


class Element:
    """Vue légère sur un élément : lire son texte, ses attributs, et descendre en css/xpath."""

    def __init__(self, selecteur: Selector) -> None:
        self._sel = selecteur

    @property
    def texte(self) -> str:
        return " ".join(t.strip() for t in self._sel.css("::text").getall() if t.strip())

    def attribut(self, nom: str) -> str | None:
        return self._sel.attrib.get(nom)

    def css(self, selecteur: str) -> list[str]:
        return [t.strip() for t in self._sel.css(f"{selecteur} ::text").getall() if t.strip()]

    def css_un(self, selecteur: str) -> str | None:
        valeurs = self.css(selecteur)
        return valeurs[0] if valeurs else None


class Analyseur:
    """Enveloppe un document HTML : sélection css/xpath ergonomique + extraction adaptative."""

    def __init__(self, html: str, url: str = "", signatures: extraction.Signatures | None = None) -> None:
        self._sel = Selector(text=html or "")
        self._url = url
        self._signatures = signatures

    # ── Sélection ergonomique ───────────────────────────────────────────
    def css(self, selecteur: str) -> list[str]:
        """textContent des éléments correspondant au sélecteur CSS."""
        return [t.strip() for t in self._sel.css(f"{selecteur} ::text").getall() if t.strip()]

    def css_un(self, selecteur: str) -> str | None:
        valeurs = self.css(selecteur)
        return valeurs[0] if valeurs else None

    def xpath(self, chemin: str) -> list[str]:
        return [t.strip() for t in self._sel.xpath(chemin).getall() if isinstance(t, str) and t.strip()]

    def attribut(self, selecteur: str, nom: str) -> str | None:
        el = self._sel.css(selecteur)
        return el[0].attrib.get(nom) if el else None

    def tout_le_texte(self) -> str:
        return " ".join(t.strip() for t in self._sel.css("::text").getall() if t.strip())

    # ── Auto-match de liste (façon Scrapling) ───────────────────────────
    def similaires(self, selecteur: str, seuil: float = 0.5) -> list[Element]:
        """À partir d'UN exemple, retrouve tous les éléments qui lui ressemblent.

        Utile pour les listes : on pointe une carte produit, un `<li>`, une ligne de tableau, et on
        récupère toutes les sœurs de même structure — même quand elles n'ont pas de classe commune
        exploitable par un sélecteur. Rend des `Element` dans l'ordre du document (l'exemple inclus).
        """
        exemples = self._sel.css(selecteur)
        if not exemples:
            return []
        modele = _features(exemples[0].root)
        retenus: list[Element] = []
        for cand in self._sel.css(modele["tag"]):
            if extraction.score(modele, _features(cand.root)) >= seuil:
                retenus.append(Element(cand))
        return retenus

    # ── Extraction adaptative (relocalisation sans navigateur) ───────────
    def extraire_adaptatif(self, selecteur: str, cle: str) -> str | None:
        """Texte de l'élément ciblé ; si le sélecteur a cassé, relocalise par ressemblance.

        Mémorise une signature à chaque extraction réussie (si un store est fourni), et s'en sert
        pour retrouver l'élément quand le site a changé. Fonctionne sur le HTML parsé, sans navigateur.
        """
        domaine = extraction.domaine_de(self._url)
        trouves = self._sel.css(selecteur)
        if trouves:
            feats = _features(trouves[0].root)
            if self._signatures is not None:
                self._signatures.enregistrer(domaine, cle, feats)
            return feats["texte"]
        if self._signatures is None:
            return None
        sig = self._signatures.charger(domaine, cle)
        if not sig:
            return None
        candidats = [_features(s.root) for s in self._sel.css(sig["tag"])]
        meilleur, score = extraction.meilleur_candidat(sig, candidats)
        if meilleur and score >= extraction.SEUIL_RELOCALISATION:
            return meilleur["texte"]
        return None
