# Extraction adaptative

Extraire des données structurées d'une page web même quand les sélecteurs CSS cassent
(classes renommées, obfuscation, refonte partielle).

## Principe

1. **Premier passage** — le sélecteur CSS fonctionne. L'extracteur mémorise une *signature*
   de chaque élément trouvé (balise, classes, id, texte, profondeur dans le DOM).
2. **Passages suivants** — si le sélecteur ne trouve plus rien (les classes ont changé),
   l'extracteur parcourt tous les éléments du même tag et les compare à la signature par
   un score de ressemblance pondéré. Le meilleur candidat au-dessus du seuil est retenu.

## Score de ressemblance

| Critère         | Poids | Mesure                                    |
|-----------------|-------|-------------------------------------------|
| Classes CSS     | 0.35  | Jaccard (intersection / union)            |
| Identifiant     | 0.25  | Égalité exacte (bonus partiel si absents) |
| Texte           | 0.25  | SequenceMatcher ratio                     |
| Profondeur DOM  | 0.15  | 1 − (écart / 5), plancher à 0            |

La balise doit coïncider (sinon score = 0). Seuil par défaut : **0.55**.

## Usage en Python

```python
from shadowlab.engines.noezia.analyseur import Analyseur
from shadowlab.engines.noezia.extraction import Signatures

# Signatures en mémoire (pas de fichier)
sigs = Signatures()

# Premier passage : apprend
a1 = Analyseur(html_page_1, url="https://exemple.fr/annonces", signatures=sigs)
titre = a1.extraire_adaptatif("h3.titre-annonce", "titre")

# Deuxième passage : les classes ont changé, mais relocalise
a2 = Analyseur(html_page_2, url="https://exemple.fr/annonces", signatures=sigs)
titre = a2.extraire_adaptatif("h3.titre-annonce", "titre")  # retrouvé par ressemblance
```

Pour persister les signatures entre exécutions :

```python
from pathlib import Path
sigs = Signatures(Path("signatures.json"))
```

## Avec les moteurs HTTP

Tous les moteurs HTTP (httpx, curl-cffi, scrapling) exposent `.analyseur()` :

```python
pilote = DriverHttpx(hotes_autorises)
pilote.start_session()
pilote.navigate("https://exemple.fr/annonces")
a = pilote.analyseur()
titres = a.css("h3.titre-annonce")
```

## Auto-match de liste (`similaires`)

Pour récupérer tous les éléments semblables à un exemple (comme Scrapling) :

```python
a = Analyseur(html)
cartes = a.similaires("article.carte")  # pointe UNE carte, récupère les trois
for c in cartes:
    print(c.css_un("h3"), c.css_un("span.prix"))
```

## Navigation DOM (`Element`)

Les éléments retournés par `elements()` et `similaires()` sont des `Element` navigables :

```python
els = a.elements("article.carte")
for el in els:
    el.tag           # "article"
    el.attributs     # {"class": "carte", "data-id": "42"}
    el.texte         # texte complet
    el.parent        # Element parent
    el.enfants       # enfants directs
    el.freres        # frères (même parent, sans soi-même)
    el.elements("span.prix")  # sous-sélection CSS
```

## Scénario Arena

La page `/lab/adaptatif` mute les classes CSS à chaque requête. Le scénario
`extraction_adaptative` teste que l'extracteur retrouve les données malgré la mutation.

```bash
uv run shadowlab campagne configs/experiments/extraction-adaptative.yaml
```

## Fichiers

| Fichier | Rôle |
|---------|------|
| `engines/noezia/extraction.py` | Score, Signatures, relocalisation |
| `engines/noezia/analyseur.py` | Analyseur, Element, similaires() |
| `engines/http_base.py` | `.analyseur()` pour tous les moteurs HTTP |
| `site/pages.py` | Page `/lab/adaptatif` (mutation CSS) |
| `scenarios.py` | Scénario `extraction_adaptative` |
