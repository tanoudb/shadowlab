# Guide de la commande de récolte

`uv run shadowlab recolte …` : récolter un site entier à partir d'une **recette** (un fichier YAML).
Ce guide dit comment écrire la recette d'un site et lancer une récolte, sans lire le code.
Conception et raisons des choix : `docs/recherche/recolte-generale-2026-11-12.md` (le code fait foi quand il
diffère ; les écarts connus sont dans la section 10).

Les commandes et les sorties de ce guide ont été exécutées le 12/11/2026, moteur `http`, sur notre site du
labo
lancé sur un port de test (8789). Les sorties sont recopiées avec le port normal du labo (8770) et des chemins
raccourcis par `…`. Ce qui n'a pas pu être rejoué (moteur `navigateur`, site tiers) est marqué « non rejoué
ici ».

## 1. En trois lignes

- La commande parcourt un site page par page (liste, fiches, tableaux…), lit les champs que la recette
  décrit et
  écrit les données en JSON Lines et en CSV, avec un état qui permet de reprendre après un arrêt.
- Elle sert pour les sites que l'on décrit par des sélecteurs CSS : nos deux sites factices du labo (annonces,
  rallye), et un autre site seulement avec une ligne `autorisation` dans la recette (section 8).
- Elle ne résout aucun CAPTCHA, ne clique jamais sur un défi d'un site tiers, ne laisse jamais une redirection
  vers un autre site se poursuivre (section 8), et ne sait pas lire ce que le HTML ne contient pas (API
  internes, défilement infini, section 10).

## 2. Démarrage rapide : récolter les annonces factices

La recette `configs/recettes/vitrine.yaml` décrit notre site d'annonces. La commande démarre le site du labo
si
besoin.

```bash
uv run shadowlab recolte lancer configs/recettes/vitrine.yaml
```

Sortie (raccourcie, une ligne de progression sur 21 gardée) :

```text
Site du labo démarré (il ne tournait pas).
Recette vitrine-annonces · moteur http · autorisation : site à nous (labo local)
robots.txt : http://127.0.0.1:8770/robots.txt → 404, aucune règle (tout est permis)
Passe 1 · état : …/outputs/recoltes/vitrine-annonces/etat.sqlite3
  pages lues 25 · 23 annonces · échecs 0 · à faire 18 · alertes de lecture 0
  …
  pages lues 525 · 500 annonces · échecs 0 · à faire 0 · alertes de lecture 0
Terminée : 525 pages (500 fiche, 25 liste), 500 annonces, 0 échec(s), 0 relocalisation(s), 0 interdite(s) par
robots.txt, durée 0.7 s
Alertes de lecture : aucune.
Données : …/outputs/recoltes/vitrine-annonces/passe-001
```

Code de sortie 0. Les données sont dans `outputs/recoltes/vitrine-annonces/passe-001/` : `annonces.jsonl`,
`annonces.csv`, `resume.json`. Première ligne du JSON Lines (raccourcie) :

```json
{"reference": "AN-000001", "titre": "Studio de 20 m² à Grenoble", "surface": 20, "pieces": 1, "prix": 57500,
 "dpe": "C", "date_publication": "2026-09-18", "nb_photos": 6, "photos": ["http://127.0.0.1:8770/…/1.svg", …],
 "_page": "http://127.0.0.1:8770/lab/vitrine/annonces/AN-000001", "_vu_le": "2026-11-12T19:15:25+01:00", "_passe": 1}
```

Voir où en est la récolte :

```bash
uv run shadowlab recolte etat vitrine-annonces
```

```text
Récolte vitrine-annonces · dossier …/outputs/recoltes/vitrine-annonces
passe 1 · terminee · début 2026-11-12T19:15:25+01:00 · fin 2026-11-12T19:15:26+01:00
  525 pages faites (500 fiche, 25 liste), 0 à faire, 0 échec(s), 0 interdite(s) par robots.txt, 0 anormale(s), …
  enregistrements : 500 annonces
  Alertes de lecture : aucune.
```

Noter la récolte contre ce que le site contient vraiment (seulement pour nos sites factices) :

```bash
uv run shadowlab recolte noter vitrine-annonces --verite vitrine
```

```text
Notation de vitrine-annonces (passe 1) contre la vérité vitrine : graine 20261111, taille 500
  pages 525/525 (100,0 %)
  enregistrements 500/500 (100,0 %)
    annonces 500/500 · champs 7000/7000
  champs 7000/7000 (100,0 %)
  annonces : champs produits mais absents de la vérité (non notés) : photos
Seuil de 99 % atteint sur les pages, les enregistrements et les champs.
```

Code de sortie 0 si les pages, les enregistrements et les champs sont tous à 99 % ou plus, 1 sinon.

## 3. Écrire la recette d'un site, pas à pas

Fil rouge : le site de rallye factice « Chrono Démo » (`/lab/rallye/…`). Chemin des pages :
saisons, calendrier d'une saison, **rallye**, **spéciales** (avec leur **tableau des temps**), puis engagés et
**châssis**. La recette complète est `configs/recettes/rallye-demo.yaml` ; on construit ici la première
moitié.

### Étape 1. Regarder les pages

Ouvrir les pages dans un navigateur et noter, pour chaque type de page : son adresse, ce qui y est toujours,
les
liens à suivre, les valeurs à lire. En ligne de commande :

```bash
curl -s http://127.0.0.1:8770/lab/rallye/rallyes/17
```

Extrait utile (raccourci) :

```html
<h1 class="titre">Rallye d'Aubépine-Factice 2025</h1>
<dl class="fiche">
  <div class="ligne"><dt>Saison</dt><dd class="saison"><a href="/lab/rallye/saisons/2025">2025</a></dd></div>
  <div class="ligne"><dt>Distance chronométrée</dt><dd class="km">19,1 km</dd></div>
</dl>
<table class="speciales"> … <td class="nom"><a href="/lab/rallye/speciales/105">Crête du Cormoran</a></td> …
```

Règle de travail : s'appuyer sur ce qui est dans le HTML tel que le serveur l'envoie (moteur `http`). Écrire
`table.temps tr` et non `table.temps tbody tr` : un navigateur ajoute `tbody`, le HTML brut n'en a pas
toujours.

### Étape 2. L'en-tête et les types de pages

Un **type de page** = une sorte de page du site. Chacun a un motif d'adresse (`url`), un sélecteur qui prouve
que c'est la bonne page (`requis`), ce qu'on y lit (`enregistrements`) et les liens à suivre (`suivre`).

```yaml
recette: 1
nom: rallye-tuto
autorisation: site à nous (labo local)
hotes: [127.0.0.1]
depart:
  - url: http://127.0.0.1:8770/lab/rallye/saisons
    type: saisons
parametres_ignores: [sl]     # jeton de session du labo, sans effet sur le contenu
rythme: libre
variables:
  saison: '*'                # --tranche saison=2025 : une seule saison
```

### Étape 3. Suivre les liens

Chaque règle `suivre` dit : quels liens (`liens`, sélecteur des balises `<a>`) et de quel type est la page
visée
(`vers`). Les règles se visitent dans l'ordre écrit, les liens dans l'ordre de la page, **en profondeur
d'abord** :
une page, puis tout ce qui en descend, avant la page suivante de la liste.

```yaml
pages:
  saisons:
    url: '^/lab/rallye/saisons$'
    requis: 'ul.saisons'
    suivre:
      - liens: 'ul.saisons a'
        vers: calendrier
        garder_si: {contient: '{saison}'}   # le texte du lien est « Saison 2025 »
  calendrier:
    url: '^/lab/rallye/saisons/\d{4}(\?page=\d+)?$'
    requis: 'table.calendrier'
    suivre:
      - liens: 'table.calendrier td.rallye a'
        vers: rallye
      - liens: 'a[rel="next"]'              # la page suivante du calendrier
        vers: calendrier
```

### Étape 4. Lire les champs d'une page

Une page de rallye donne un enregistrement dans la collection `rallyes`. `cle` dit quel champ identifie
l'enregistrement : deux enregistrements de même clé n'en font qu'un (le dernier lu remplace l'autre).

```yaml
  rallye:
    url: '^/lab/rallye/rallyes/\d+$'
    requis: 'dl.fiche'
    enregistrements:
      - collection: rallyes
        cle: id
        champs:
          id: {adresse: '/rallyes/(\d+)$'}                # un morceau de l'adresse de la page
          nom: 'h1.titre'                                 # un sélecteur seul : le texte
          date_debut: {css: 'time.debut', attribut: datetime}
          saison: {css: 'dd.saison', format: entier}
          km_chrono: {css: 'dd.km', format: nombre}       # « 19,1 km » → 19.1
    suivre:
      - liens: 'table.speciales td.nom a'
        vers: speciale
```

### Étape 5. Un tableau : les temps d'une spéciale

`lignes` dit « une ligne du tableau = un enregistrement ». Chaque champ se lit par le **nom de sa colonne**
(l'en-tête `th`), pas par sa position. Un `css` en plus cherche dans la cellule.

```yaml
  speciale:
    url: '^/lab/rallye/speciales/\d+$'
    requis: 'h1.titre'
    enregistrements:
      - collection: temps
        cle: [speciale, numero]                           # une clé peut avoir plusieurs champs
        lignes: 'table.temps tr'
        champs:
          speciale: {adresse: '/speciales/(\d+)$'}
          numero: {colonne: 'N°', format: entier}
          rang: {colonne: 'Pos.', vide_si: ['-'], format: entier}
          pilote: {colonne: Équipage, css: 'a.pilote'}
          temps: {colonne: Temps}                         # texte affiché : « 3:59.9 », « Abandon »
          temps_ms: {colonne: Temps, vide_si: [Abandon], format: duree_ms}
```

Ces cinq blocs, mis bout à bout dans l'ordre (en-tête, `pages:`, saisons, calendrier, rallye, spéciale),
forment
la recette de l'essai. Enregistrer sous `configs/recettes/rallye-tuto.yaml`. Le fichier de l'essai a passé les
commandes ci-dessous.

### Étape 6. Essayer page par page avant de lancer

`recolte essayer` lit **une** page, montre ce que la recette y trouve et n'écrit rien. Le type de page est
trouvé par le premier motif `url` qui correspond (ou imposé par `--type`).

```bash
uv run shadowlab recolte essayer configs/recettes/rallye-tuto.yaml http://127.0.0.1:8770/lab/rallye/rallyes/17
```

```text
Page http://127.0.0.1:8770/lab/rallye/rallyes/17 · statut 200 · type rallye
Enregistrements (1) :
  rallyes ['17']
    id: '17'
    nom: "Rallye d'Aubépine-Factice 2025"
    date_debut: '2025-02-16'
    saison: 2025
    km_chrono: 19.1
Liens à suivre (4) :
  speciale   http://127.0.0.1:8770/lab/rallye/speciales/105
  speciale   http://127.0.0.1:8770/lab/rallye/speciales/106
  speciale   http://127.0.0.1:8770/lab/rallye/speciales/107
  speciale   http://127.0.0.1:8770/lab/rallye/speciales/108
```

Un tableau (`…/speciales/105`, 30 lignes, début raccourci) :

```text
Enregistrements (30) :
  temps ['105', 75]
    speciale: '105'
    numero: 75
    rang: 1
    pilote: 'Mathis Quenelvaux'
    temps: '3:59.9'
    temps_ms: 239900
  …
Liens à suivre (0) :
```

Essayer aussi une page de calendrier paginée : `essayer … "…/saisons/2025?page=2"` (guillemets : le `?` est un
joker du terminal). Une spéciale annulée (`…/speciales/106`) n'a pas de tableau : elle donne 0 enregistrement
`temps`, sans alerte (c'est voulu, voir `rallye-demo.yaml`). Pour essayer un fichier HTML enregistré :
`essayer recette.yaml page.html --type fiche --base http://…/la-page`.

### Étape 7. Borner, puis lancer

```bash
uv run shadowlab recolte lancer configs/recettes/rallye-tuto.yaml --tranche saison=2025
```

```text
Passe 1 · état : …/outputs/recoltes/rallye-tuto/etat.sqlite3
  pages lues 25 · 4 rallyes, 391 temps · échecs 0 · à faire 11 · alertes de lecture 0
  pages lues 50 · 7 rallyes, 737 temps · échecs 0 · à faire 5 · alertes de lecture 0
Terminée : 65 pages (2 calendrier, 8 rallye, 1 saisons, 54 speciale), 8 rallyes, 899 temps, 0 échec(s),
0 relocalisation(s), 0 interdite(s) par robots.txt, durée 0.1 s
```

`noter` dit ce qui manque encore. La recette de l'essai ne lit ni les engagés ni les châssis, et la tranche ne
prend qu'une saison : la note est basse, c'est attendu.

```bash
uv run shadowlab recolte noter rallye-tuto --verite rallye
```

```text
Notation de rallye-tuto (passe 1) contre la vérité rallye : graine 20261112, taille 24
  pages 65/427 (15,2 %)
  enregistrements 907/4569 (19,9 %)
    rallyes 8/24 · champs 32/64 · erreurs {'championnat': 8, 'date_fin': 8, 'lieu': 8, 'surface': 8}
    speciales 0/158 · champs 0/0 (rien à comparer)
    temps 899/2745 · champs 5394/8091 · erreurs {'copilote': 899, 'pilote_id': 899, 'voiture': 899}
    …
  ATTENTION speciales : aucun enregistrement « speciales » récolté ; collections récoltées : rallyes, temps.
  …
Sous le seuil de 99 % : pages, enregistrements, champs.
```

Code de sortie 1. Les `erreurs {…}` listent les champs que la vérité attend et que la recette ne lit pas. Pour
finir, ajouter ce qui manque (collections `speciales`, `classements`, `engages`, `pilotes`, `chassis`,
`historique`) en recopiant les blocs de `rallye-demo.yaml`. La récolte complète, sans tranche :

```bash
uv run shadowlab recolte lancer configs/recettes/rallye-demo.yaml
uv run shadowlab recolte noter rallye-demo --verite rallye
```

```text
Terminée : 427 pages (6 calendrier, 93 chassis, 24 classement, 24 engages, 97 pilote, 24 rallye, 1 saisons,
158 speciale), 93 chassis, 484 classements, 484 engages, 484 historique, 97 pilotes, 24 rallyes, 158 speciales,
2745 temps, 0 échec(s), 0 relocalisation(s), 0 interdite(s) par robots.txt, durée 0.8 s
…
  pages 427/427 (100,0 %)
  enregistrements 4569/4569 (100,0 %)
  champs 34410/34410 (100,0 %)
Seuil de 99 % atteint sur les pages, les enregistrements et les champs.
```

Borner par la recette plutôt que par la ligne de commande : voir `bornes` (section 4). Ne pas suivre un lien
qui
mène à tout le site : la recette `rallye-demo.yaml` ne suit pas les pages liées depuis un pilote ou un châssis
(leurs historiques renvoient vers toutes les saisons, une tranche déborderait).

## 4. Référence des clés d'une recette

Une clé inconnue ou une valeur invalide refuse la recette avant toute requête (section 9).
« Obligatoire » : sans elle, refus. Les noms (collection, champ, type de page) : minuscules, chiffres et `_`,
commençant par une lettre.

### 4.1 En-tête (racine du fichier)

| Clé | Rôle | Valeurs possibles | Défaut |
|---|---|---|---|
| `recette` | version du format | `1` | obligatoire |
| `nom` | nom court, donne le dossier de sortie | minuscules, chiffres, `-`, `_` | obligatoire |
| `autorisation` | pourquoi on a le droit de viser ce site ; recopiée dans `resume.json` | un texte | aucune ; obligatoire si un hôte n'est pas local (D-30) |
| `moteur` | comment lire les pages | `http`, `navigateur` | `http` |
| `hotes` | hôtes dont on visite les pages ; un lien ailleurs est ignoré et compté | liste de noms d'hôtes | obligatoire |
| `depart` | adresses de départ | liste de `{url, type}` ; l'hôte doit être dans `hotes` | obligatoire |
| `variables` | variables de tranche et leur valeur par défaut | `nom: valeur`, `*` = tout | aucune |
| `parametres_ignores` | paramètres d'adresse sans effet (jeton, suivi), retirés avant le dédoublonnage et avant le test du motif `url` | liste de noms | aucun |
| `rythme` | pause entre deux pages | `libre`, `prudent` ou le détail (4.2) | `libre` si tous les hôtes sont locaux, sinon `prudent` |
| `robots` | `agent` : nom présenté au `robots.txt` | `{agent: nom}` | `noezia` (la règle `*` s'applique si le nom n'est pas cité) |
| `porte_entree` | `attendre_s` : attente d'un défi qui se valide seul, première page seulement (section 8) | `{attendre_s: nombre > 0}` | aucune |
| `bornes` | limites de la passe | `pages_max` (entier ≥ 1) ; `par_type` (`{type: n}`) | aucune |
| `pages` | les types de pages (4.3) | tableau `type: {…}` | obligatoire |

Hôtes locaux (aucune autorisation demandée) : `127.0.0.1`, `localhost`, `::1`, `*.localhost`, `*.test`.

Il n'y a pas de clé de recette pour ignorer `robots.txt` : c'est `--ignorer-robots` en ligne de commande,
jamais dans
un fichier qui se partage.

### 4.2 Le détail du rythme

| Clé de `rythme` | Rôle | Format |
|---|---|---|
| `delai_s` | délai entre le début d'une page et le début de la suivante, tiré au hasard (loi log-normale) | `[minimum, médiane, maximum]`, croissants |
| `pages_par_heure_max` | plafond horaire | entier ≥ 1 |
| `pause_longue` | pause longue de temps en temps | `{minutes: [a, b], toutes_les: [n, m]}`, les deux obligatoires |

`prudent` = délai `[3, 8, 30]` s, 300 pages par heure au plus, une pause de 2 à 5 min toutes les 40 à 80
pages.
Le temps déjà passé par le moteur est déduit du délai. Le `Crawl-delay` du `robots.txt` s'applique s'il est
plus
long. `libre` = aucun délai. La clé `comportement` est acceptée dans le détail mais n'a aucun effet.
Exemple lancé : `rythme: {delai_s: [0.2, 0.5, 1], pages_par_heure_max: 5000, pause_longue: {minutes: [0.01,
0.02],
toutes_les: [5, 8]}}` a lu 12 pages en 7 s.

### 4.3 Un type de page (`pages.<nom>`)

| Clé | Rôle | Valeurs | Défaut |
|---|---|---|---|
| `url` | expression régulière sur chemin et paramètres (sans les `parametres_ignores`) ; la page reçue doit y correspondre | regex | obligatoire |
| `requis` | sélecteur CSS toujours présent sur une vraie page de ce type ; absent = page anormale | sélecteur | aucun |
| `enregistrements` | ce qu'on lit (4.4) | liste | aucun |
| `suivre` | les liens à suivre (4.6) | liste | aucun |
| `attendre` | prévu pour le moteur `navigateur` (sélecteur à attendre) | sélecteur | accepté, **sans effet** pour l'instant |
| `revisiter` | quand une page déjà lue est relue dans une passe suivante (section « Récolter seulement le neuf ») | `toujours`, `jamais`, `<n>j` (`7j`) | `toujours` si le type a des `suivre`, sinon `jamais` |

### 4.4 Un enregistrement (`pages.<nom>.enregistrements[]`)

| Clé | Rôle | Valeurs | Défaut |
|---|---|---|---|
| `collection` | nom de la collection (un fichier par collection) | identifiant | obligatoire |
| `cle` | champ, ou liste de champs, qui identifie l'enregistrement | noms de `champs`, sans doublon, pas de champ `tous` | obligatoire |
| `champs` | les champs (4.5), au moins un | tableau `nom: champ` | obligatoire |
| `lignes` | une ligne de tableau = un enregistrement | sélecteur (`table.x tr`) | un enregistrement par page |
| `similaires` | un enregistrement par bloc répété (un exemple suffit, les blocs semblables sont trouvés) | sélecteur | un enregistrement par page |

`lignes` et `similaires` s'excluent. Un enregistrement dont un champ de la clé est vide est **ignoré**, avec
une
alerte de lecture.

### 4.5 Un champ (`champs.<nom>`)

Forme courte : `nom: 'sélecteur'` = le texte du premier élément trouvé. Forme longue : un tableau avec les
clés
suivantes. Il faut au moins `css`, `adresse` ou `colonne`.

| Clé | Rôle | Valeurs | Défaut |
|---|---|---|---|
| `css` | sélecteur de l'élément (dans la cellule si `colonne` est donnée) | sélecteur | aucun |
| `attribut` | lire un attribut au lieu du texte (`href`, `datetime`, `data-valeur`, `src`) | nom d'attribut | le texte |
| `adresse` | un morceau de l'adresse de la page (chemin et paramètres), groupe 1 de l'expression | regex avec un groupe | aucun |
| `colonne` | dans `lignes` : la cellule sous cet en-tête, ou de ce rang | nom d'en-tête, ou entier à partir de 1 | aucun |
| `motif` | garde le groupe 1 d'une expression appliquée à la valeur | regex avec un groupe | aucun |
| `format` | convertit la valeur (section 5) | `texte`, `entier`, `nombre`, `duree_ms` | `texte` |
| `vide_si` | valeurs qui veulent dire « rien » (donnent une valeur vide) | liste de textes | aucune |
| `tous` | toutes les valeurs, en liste, pas seulement la première | `true` | `false` |
| `lien` | rend l'adresse absolue ; demande `attribut` | `true` | `false` |
| `present` | vrai si l'élément existe, faux sinon | `true` | `false` |
| `adaptatif` | relocalise l'élément par ressemblance si le sélecteur ne trouve plus rien (section 5) | `true` | `false` |

Combinaisons refusées : `adresse` avec `css`, `colonne`, `attribut`, `tous`, `present`, `adaptatif` ou
`lien` ;
`present` avec `attribut`, `motif`, `tous`, `adaptatif`, `lien`, `vide_si` ou un `format` autre que `texte` ;
`adaptatif` sans `css`, ou avec `colonne`, `attribut` ou `tous` ; `colonne` hors d'un enregistrement à
`lignes` ;
`adaptatif` dans `lignes` ou `similaires`.

Un champ ne peut pas s'appeler comme un champ ajouté par la commande : `_page`, `_vu_le`, `_passe`,
`_relocalises` (le nom doit commencer par une lettre, donc ils sont de toute façon refusés).

### 4.6 Un lien à suivre (`pages.<nom>.suivre[]`)

| Clé | Rôle | Valeurs | Défaut |
|---|---|---|---|
| `liens` | sélecteur des balises `<a>` | sélecteur | obligatoire |
| `vers` | type de la page visée | un type de `pages` | obligatoire |
| `garder_si` | ne garder que certains liens | `{contient: texte, contexte: sélecteur}` ou `'*'` | tout garder |

`garder_si.contient` : le texte du lien (ou, avec `contexte`, celui de l'élément englobant le plus proche, par
exemple `tr` pour la ligne d'un tableau) doit **contenir** ce texte. `{saison}` y est remplacé par la valeur
de la
variable ; si la variable vaut `*`, tout est gardé. Une variable utilisée et non déclarée refuse la recette.

Le lien est rendu absolu et sans fragment (`#…`). Sont écartés : les liens vides ou `#…` seuls, ceux dont le
schéma n'est pas `http(s)`, et ceux dont l'hôte n'est pas dans `hotes` (comptés comme « lien(s) hors site »).

## 5. Lire une valeur

Ordre des opérations sur chaque valeur : espaces nettoyés (suites d'espaces réduites à une, bords retirés) ;
valeur vide ou égale à un `vide_si` : valeur absente ; `lien` ; `motif` ; `format`. Le texte d'un champ est
celui
de l'élément entier, enfants compris. Une valeur absente s'écrit `null` en JSON et cellule vide en CSV.

### Les formats

| Format | Accepté | Donne une valeur vide **et une alerte** |
|---|---|---|
| `texte` | tout | |
| `entier` | chiffres, signe `+` ou `-`, milliers par espace (`401 500`), une unité ou un symbole après le nombre : `401 500 €` donne `401500`, `7 pièces` donne `7` | `12,5 km`, `2,0` (décimale), `3-4`, `1e3`, `1 2` |
| `nombre` | virgule décimale : `142,6 m²` donne `142.6`, `12,5 km` donne `12.5`, `1 234,5` et `1.234,5` donnent `1234.5` | `10.5` (point décimal), `1,234.5` (mélange), `1e3` |
| `duree_ms` | `3:59.9` donne `239900`, `1:49:48.6` donne `6588600`, `0:02.2` donne `2200` ; virgule ou point avant les fractions de seconde | `59.9` (pas de minutes), `+0:02.2` (signe), `1:75.0` (secondes ≥ 60), `1:75:00` (minutes ≥ 60 avec heures) |

Relevé avec `essayer` sur un fichier HTML (extraits) :

```text
    prix_entier: 401500        ← « 401 500 € », format entier
    dist_entier: None          ← « 12,5 km », format entier
    dist_nombre: 12.5          ← « 12,5 km », format nombre
    decimale_point: None       ← « 10.5 », format nombre
    point_milliers: 1234.0     ← « 1.234 », format nombre : lu comme 1234, pas comme 1,234
    duree: 6588600             ← « 1:49:48.6 », format duree_ms
    duree_mauvaise: None       ← « 1:75.0 », format duree_ms
    ecart_signe: None          ← « +0:02.2 », format duree_ms
Alerte : champ « dist_entier » : « 12,5 km » n'est pas lisible en entier
Alerte : champ « decimale_point » : « 10.5 » n'est pas lisible en nombre
Alerte : champ « duree_mauvaise » : « 1:75.0 » n'est pas lisible en duree_ms
Alerte : champ « ecart_signe » : « +0:02.2 » n'est pas lisible en duree_ms
```

Deux pièges : le format `nombre` suit la convention française. `1.234` s'y lit comme mille deux cent
trente-quatre,
et un point décimal (`10.5`) est refusé plutôt que deviné. Pour un site qui écrit à l'anglaise, laisser le
format
`texte` et convertir après la récolte.

Pour enlever un signe ou un préfixe avant la conversion, utiliser `motif` :
`ecart_ms: {colonne: Écart, vide_si: ['—'], motif: '\+(.+)$', format: duree_ms}` lit `+0:02.2` comme `2200` et
`—` (écart du premier) comme vide.

### Les tableaux lus par le nom de leurs colonnes

Dans un enregistrement à `lignes`, `colonne: Nom` désigne la cellule sous l'en-tête « Nom » (comparaison après
nettoyage des espaces). La ligne d'en-tête est la première ligne de la table qui contient des cellules `th`.
Les lignes sans cellule `td` sont sautées. `colonne: 3` désigne la 3e cellule. Un `css` en plus cherche dans
la
cellule : `colonne: Équipage, css: 'a.pilote'`. Alertes de lecture possibles (relevées sur un tableau
d'essai) :

```text
Alerte : ligne ignorée : 3 cellules pour 4 en-têtes (colspan, cellule th en tête de ligne ?) : les colonnes se décaleraient
Alerte : colonne « Position » absente de l'en-tête (Pos., N°, Équipage, Temps)
```

Une ligne dont le nombre de cellules diffère du nombre d'en-têtes est **sautée** (cellules fusionnées). Un nom
de colonne qui apparaît deux fois est refusé comme ambigu (alerte) : utiliser le rang.

### `motif`, `vide_si`, `present`

- `motif: '^ES(\d+) '` garde le groupe 1. Le motif doit avoir un groupe, sinon la recette est refusée.
  **Si le motif ne correspond pas, la valeur est vide, sans alerte** : à vérifier avec `essayer`.
  Exemple lu : `numero: {css: 'h1.titre', motif: '^ES(\d+) ', format: entier}` lit « ES3 · Pont de l'Écho »
  comme `3`,
  et `nom: {css: 'h1.titre', motif: '· (.+)$'}` lit `Pont de l'Écho`.
- `vide_si: [Abandon]` : si la cellule vaut exactement « Abandon », la valeur est vide (et le format n'est pas
  essayé, donc pas d'alerte). C'est ainsi que le temps d'un abandon donne `temps_ms: null`.
- `present: true` : `annulee: {css: 'p.annulee', present: true}` donne `True` ou `False`. Sur la spéciale
  106 :
  `annulee: True`.
- Les motifs à quantificateurs imbriqués (`(a+)+`) sont refusés ; un texte de plus de 10 000 caractères est
  coupé
  avant la recherche (alerte).

### L'extraction adaptative : jamais par défaut

`adaptatif: true` dit : « si ce sélecteur ne trouve plus rien, cherche un élément qui ressemble à celui
d'avant ».
La commande mémorise, à chaque lecture réussie, une signature de l'élément (balise, classes, id, texte,
profondeur)
dans `outputs/recoltes/<nom>/signatures.json`. Quand le sélecteur casse, elle prend l'élément de même balise
le plus
ressemblant, à condition d'atteindre un score de 0,5. La valeur relocalisée est marquée : `_relocalises` dans
l'enregistrement et « relocalisation(s) » dans le bilan.

Pourquoi pas par défaut : un site qui change vraiment (le champ n'existe plus) donnerait une valeur fausse
mais
plausible, prise sur un autre élément. Le champ vide d'un site refait est une information ; une valeur
devinée la
cache. À réserver aux champs de texte libre dont la classe change souvent (comme `description` dans
`vitrine.yaml`).

Essai sur une page dont la classe change (`h1.titre` devient `h1.x-4b2`, avec une classe commune `grand`) :

```text
Terminée : 4 pages (1 liste, 3 page), 3 pages, 0 échec(s), 2 relocalisation(s), 0 interdite(s) par robots.txt, …
{"numero": "2", "titre": "Titre de la page 2", "chapeau": "Intro", …, "_relocalises": ["titre"]}
```

Limites : `essayer` ne relocalise jamais (il n'a pas de mémoire). Si la classe change **entièrement** et que
l'élément
n'a ni id ni autre classe commune, le score n'atteint pas 0,5 : sur un premier essai (classe `titre` devenue
`x-4b2`,
sans classe commune) la valeur est restée vide, sans alerte ni relocalisation.

## 6. Lancer, suivre, reprendre

```text
uv run shadowlab recolte lancer    <recette.yaml>  [options]
uv run shadowlab recolte reprendre <nom>           [options]
uv run shadowlab recolte etat      <nom>           [--pages]
uv run shadowlab recolte essayer   <recette.yaml>  <adresse | fichier.html>  [--type T --base URL]
uv run shadowlab recolte noter     <nom>           --verite vitrine|rallye  [--attendu]
```

`<nom>` est le `nom` de la recette (le dossier `outputs/recoltes/<nom>`).

### Les actions

- **`lancer`** : nouvelle passe. Refus si la dernière passe n'est pas finie (voir `reprendre`), sauf avec
  `--tout-refaire`. Une passe terminée n'empêche pas d'en lancer une autre : elle est **incrémentale** (elle ne relit
  que ce que `revisiter` demande, plus les pages jamais lues ; voir « Récolter seulement le neuf »).
- **`reprendre`** : continue la dernière passe coupée (arrêt sur alerte, limite, Ctrl-C, coupure) avec ses
  options d'origine. Les pages qui étaient en cours sont remises en file. Si la recette a changé depuis le
  début :
  refus, sauf `--recette-modifiee`. Si la passe s'est arrêtée sur alerte il y a moins d'une heure : refus,
  sauf
  `--maintenant`. Si le fichier de recette a disparu, la copie gardée au début de la passe sert.
- **`etat`** : où en est la dernière passe : pages faites par type, à faire, échecs, pages interdites par
  `robots.txt`, anormales, introuvables, liens hors site, enregistrements, alertes de lecture, arrêt
  éventuel, et
  « une passe tourne en ce moment » si le verrou est pris, et, pour une passe incrémentale, une ligne « incrémentale ». `--pages` ajoute le journal page par page.
- **`essayer`** : une page, rien d'écrit (section 3, étape 6). Il lit `robots.txt` comme le ferait une
  passe, sauf
  avec `--ignorer-robots`.
- **`noter`** : compare à la vérité des sites factices (section 2). `--attendu` montre, sans noter, la clé
  et les
  champs que la vérité attend.

### Les options

| Option | Actions | Effet |
|---|---|---|
| `--moteur http\|navigateur` | lancer, essayer | remplace le moteur de la recette |
| `--tranche nom=valeur` | lancer, essayer | valeur d'une variable de la recette ; plusieurs fois possible ; guillemets si espaces : `--tranche "championnat=Coupe Démo Asphalte"` |
| `--pages-max N` | lancer, reprendre | arrête la passe après N pages lues (échecs compris) |
| `--sans a,b` | lancer | ne visite pas ces types de pages (leurs liens ne sont pas mis en file) |
| `--tout-refaire` | lancer | abandonne la passe non finie et **efface les enregistrements gardés dans l'état** ; les dossiers `passe-NNN` déjà écrits restent |
| `--ignorer-robots` | lancer, essayer | ne lit pas `robots.txt` ; écrit « IGNORÉ » à l'écran et dans `resume.json` |
| `--sortie dossier` | toutes | dossier de l'état et des données (défaut `outputs/recoltes/<nom>`) ; à redonner à `reprendre`, `etat` et `noter` |
| `--maintenant` | reprendre | passe outre l'attente d'une heure après une alerte |
| `--recette-modifiee` | reprendre | continue avec la recette modifiée |
| `--pages` | etat | journal page par page |
| `--verite`, `--attendu` | noter | voir plus haut |
| `--type`, `--base` | essayer | type de page imposé ; adresse d'origine d'un fichier HTML (obligatoires avec un fichier) |

Exemples lancés : `--tranche saison=2025 --tranche "championnat=Coupe Démo Asphalte" --sans pilote,chassis`
sur
le rallye donne 24 pages, 39 classements, 2 rallyes, 211 temps. Une variable inconnue est refusée :

```text
Refus : variable inconnue : « annee » (déclarées : saison, championnat)
```

`--pages-max` à la reprise : voir la section 9 (la limite d'origine est gardée).

### Codes de sortie

| Code | Sens |
|---|---|
| 0 | terminée, ou limite `--pages-max` atteinte (état gardé) ; pour `noter` : seuil de 99 % atteint |
| 1 | erreur, passe interrompue (Ctrl-C) ; pour `noter` : sous le seuil |
| 2 | refus avant toute requête : recette fautive, autorisation absente, `robots.txt`, verrou pris, passe non finie… |
| 3 | arrêtée sur un signe d'alerte (état gardé, section 8) |

### Ce que la commande écrit, et où

Dossier `outputs/recoltes/<nom>/` :

| Fichier | Contenu |
|---|---|
| `etat.sqlite3` | l'état : passes, file de pages, enregistrements, événements, alertes de lecture. **C'est la vérité**, les autres fichiers en viennent |
| `verrou` | une seule passe à la fois par recette (`verrou pris : une passe tourne déjà…`) |
| `signatures.json` | mémoire de l'extraction adaptative |
| `passe-NNN/<collection>.jsonl` | une collection, un enregistrement par ligne, valeurs exactes |
| `passe-NNN/nouveautes.jsonl` et `.csv` | seulement ce que cette passe a fait apparaître ou changer (vides s'il n'y a rien) |
| `passe-NNN/<collection>.csv` | la même, pour Excel en France : UTF-8 avec BOM, séparateur `;`, virgule décimale |
| `passe-NNN/resume.json` | le bilan de la passe |

Les fichiers de collection contiennent **tout ce qui est connu** (toutes les passes) et sont réécrits en
entier à
chaque arrêt (fin, alerte, limite, Ctrl-C), par un fichier temporaire puis un renommage : une coupure ne
laisse
pas de fichier à moitié écrit. Colonnes ajoutées : `_page` (adresse de la page lue), `_vu_le`, `_passe`, et
`_relocalises` si un champ adaptatif a été retrouvé par ressemblance. Dans le CSV, une liste est écrite en
JSON, un
booléen en `true`/`false`, et un texte qui commence par `=`, `@`, `+` ou `-` (sauf un nombre ou un
téléphone) reçoit
une apostrophe devant, pour qu'un tableur ne l'exécute pas comme une formule. Le JSON Lines garde la valeur
exacte.

`resume.json` contient : recette et son empreinte, passe, statut, moteur et sa configuration, autorisation,
état
de `robots.txt` (`respecte`, groupe lu, `Crawl-delay`, ou `ignore_par`), tranche, bornes, `sans`, compteurs de
pages (faites, échecs, interdites, hors site, anormales, introuvables, évitées, à faire, par type), nombre
d'enregistrements
par collection, relocalisations, porte d'entrée, alertes de lecture, arrêt, liste des fichiers et format du
CSV.

Une passe interrompue ou arrêtée écrit quand même ces fichiers. Exemple d'arrêt puis de reprise (site local de
test, qui répond 429 une fois) :

```text
ARRÊT : signe d'alerte (statut 429) sur http://127.0.0.1:…/fiche/6 à 2026-11-12T19:17:51+01:00.
Aucun nouvel essai. État gardé : 6 pages faites, 6 à faire.
Reprise conseillée après 1 h : uv run shadowlab recolte reprendre mini
```
```text
$ uv run shadowlab recolte reprendre mini
Refus : la passe 1 s'est arrêtée sur alerte il y a 0 min : attendre 1 h, ou `reprendre … --maintenant`
$ uv run shadowlab recolte reprendre mini --maintenant
Reprise de la passe 1 · état : …/outputs/recoltes/mini/etat.sqlite3
Terminée : 11 pages (10 fiche, 1 liste), 10 fiches, 0 échec(s), 0 relocalisation(s), 1 interdite(s) par
robots.txt, durée 0.0 s
```

### Récolter seulement le neuf

Une deuxième passe sur la même récolte (même `nom`, même dossier) ne relit pas tout : elle s'appuie sur les
précédentes. Règles (relevées dans le code) :
- une page **jamais lue avec succès** est lue ;
- une page déjà lue suit la clé `revisiter` de son type : `toujours` (relue), `jamais` (évitée), `<n>j` (relue si
  sa dernière lecture date d'au moins n jours, sinon évitée) ;
- une page évitée est notée « évitée car déjà lue » ; elle n'est pas redemandée, ses liens ne sont pas remis en
  file (ils l'ont été à la passe où elle a été lue) ;
- une page qui avait échoué, était anormale, introuvable ou interdite n'est pas « déjà lue » : elle est redemandée ;
- `--tout-refaire` relit tout et efface les enregistrements gardés ; la passe d'après repart de celle-ci.

Dans `vitrine.yaml`, les listes sont `revisiter: toujours` (de nouvelles annonces peuvent y apparaître) et les
fiches `jamais`. Exemple : le site à 45 annonces, puis à 50 (`SHADOWLAB_VITRINE_TAILLE`, à donner aussi à `noter`),
dans un dossier à part.

```bash
SHADOWLAB_VITRINE_TAILLE=45 uv run shadowlab recolte lancer configs/recettes/vitrine.yaml --sortie outputs/recoltes/neuf
SHADOWLAB_VITRINE_TAILLE=50 uv run shadowlab recolte lancer configs/recettes/vitrine.yaml --sortie outputs/recoltes/neuf
```

```text
Passe 1 · état : outputs/recoltes/neuf/etat.sqlite3
Terminée : 48 pages (45 fiche, 3 liste), 45 annonces, 0 échec(s), 0 relocalisation(s), 0 interdite(s) par robots.txt, durée 0.1 s
Alertes de lecture : aucune.
Données : outputs/recoltes/neuf/passe-001
```

```text
Passe 2 · état : outputs/recoltes/neuf/etat.sqlite3
Terminée : 8 pages (5 fiche, 3 liste), 50 annonces, 0 échec(s), 0 relocalisation(s), 0 interdite(s) par robots.txt, durée 0.0 s
Incrémental : 3 page(s) relue(s), 45 évitée(s), 5 page(s) neuve(s) · 5 nouveauté(s), 0 modifié(s)
Alertes de lecture : aucune.
Données : outputs/recoltes/neuf/passe-002
```

La passe 2 a relu les 3 listes, trouvé 5 fiches neuves, et évité les 45 déjà lues. La notation compte les pages
évitées comme lues :

```bash
SHADOWLAB_VITRINE_TAILLE=50 uv run shadowlab recolte noter vitrine-annonces --sortie outputs/recoltes/neuf --verite vitrine
```

```text
Notation de vitrine-annonces (passe 2) contre la vérité vitrine : graine 20261111, taille 50
  pages 53/53 (100,0 %)
  enregistrements 50/50 (100,0 %)
    annonces 50/50 · champs 700/700
  champs 700/700 (100,0 %)
Seuil de 99 % atteint sur les pages, les enregistrements et les champs.
```

```bash
uv run shadowlab recolte etat vitrine-annonces --sortie outputs/recoltes/neuf
```

```text
passe 2 · terminee · début … · fin …
  8 pages faites (5 fiche, 3 liste), 0 à faire, 0 échec(s), … 0 lien(s) hors site
  incrémentale : 8 lue(s) (3 relue(s), 5 neuve(s)), 45 évitée(s) car déjà lues
  enregistrements : 50 annonces
```

Ce que la passe écrit en plus, dans `passe-002/` : `nouveautes.jsonl` et `nouveautes.csv` (même format Excel),
avec les 5 annonces neuves. Chaque ligne a `_collection` et `_changement` (`nouveau` ou `modifie`) en tête ;
une ligne `modifie` a aussi `_champs_modifies` : champ et **ancienne valeur**. `resume.json` porte un bloc
`incrementale` :

```json
{"active": true, "pages_relues": 3, "pages_evitees": 45, "pages_nouvelles": 5, "nouveautes": 5, "modifies": 0}
```

Les fichiers `annonces.*` gardent tout ce qui est connu (50 annonces) ; `nouveautes.*` seulement le neuf de la passe.

**Voir un changement.** Un prix modifié n'apparaît que si la fiche est relue. Essai sur un petit site local à
moi (2 biens, prix changé entre deux passes), recette avec `fiche: revisiter: toujours` :

```text
Incrémental : 3 page(s) relue(s), 0 évitée(s), 0 page(s) neuve(s) · 0 nouveauté(s), 2 modifié(s)
```
```json
{"_collection": "biens", "_changement": "modifie", "_champs_modifies": {"prix": 201000}, "numero": "1", "titre": "Bien 1", "prix": 211000, …}
```

Avec `fiche: revisiter: jamais` (ou `7j` moins d'une semaine après), la même passe ne relit que la liste, évite les
2 fiches et ne voit **aucun** changement : `1 page(s) relue(s), 2 évitée(s), 0 nouveauté(s), 0 modifié(s)`.

Limites, sans les adoucir :
- **Un prix qui change sur une fiche déjà lue ne se voit que si la recette fait relire les fiches** (`revisiter: 7j`
  ou `toujours`), ce qui coûte **une requête par fiche** relue. Avec `jamais`, le changement est invisible ;
- **une annonce retirée du site n'est pas signalée** : elle reste dans les fichiers de collection, avec l'ancienne
  date `_vu_le` ; rien n'indique qu'elle a disparu ;
- **une recette modifiée entre deux passes ne force pas la relecture** : les pages déjà lues restent évitées avec
  l'ancienne recette. Pour appliquer la nouvelle à tout le site : `--tout-refaire` ;
- un enregistrement n'est vu « modifié » que si sa page est relue dans la passe ;
  l'état gardé juste avant ;
- seul le moteur `http` a été rejoué.

## 7. Les deux moteurs

| | `http` | `navigateur` |
|---|---|---|
| Ce que c'est | requêtes HTTP avec une empreinte TLS de Chrome (`curl-cffi`) | le vrai Google Chrome avec interface, en identité native (aucun réglage d'empreinte), avec le comportement humain de NOEZIA |
| JavaScript | non : on lit le HTML tel que le serveur l'envoie | oui : on lit la page après son exécution |
| Vitesse mesurée | 525 pages en moins d'une seconde sur notre site local (0,7 s lors de l'essai de ce guide) | environ 7 s par page ; mesuré le 12/11 : 48 pages en 5 min 50 s au niveau 01 de l'Arena |
| Rejoué pour ce guide | oui | non rejoué ici |

Choisir `http` quand les données sont dans le HTML reçu (c'est le cas des deux sites factices) : c'est
rapide, peu
coûteux, et la recette se vérifie page par page avec `essayer`. Choisir `navigateur` quand une page ne
montre ses
données qu'après exécution de JavaScript, ou quand on mesure la discrétion de l'identité face à une
protection.
Une recette écrite pour `http` se relance avec `--moteur navigateur` sans changement : les sélecteurs lisent
le
HTML final, ce qui explique aussi `table.temps tr` plutôt que `… tbody tr`.

Points propres au moteur `navigateur` (d'après le code, non rejoués ici) :
- il demande que Google Chrome soit installé (sinon refus « moteur navigateur indisponible ») ;
- il garde le Mac éveillé pendant la passe (`caffeinate`) et prévient si la commande manque ;
- les redirections sont suivies par Chrome lui-même, avec une garde sur les hôtes de la recette, et l'adresse
  d'arrivée est contrôlée ensuite ; les sous-ressources (images, scripts, polices…) sont chargées par Chrome
  sans
  être limitées aux hôtes de la recette ;
- le certificat TLS est vérifié dès qu'un hôte de la recette n'est pas local ;
- la clé `attendre` d'un type de page n'est pas encore branchée (section 4.3).

## 8. Les règles que la commande applique

- **`robots.txt` respecté par défaut.** Lu une fois par passe et par origine. Le groupe qui cite l'agent de la
  recette (`robots.agent`) s'applique, sinon le groupe `*` ; les règles `Allow`/`Disallow` suivent la RFC
  9309 ;
  le `Crawl-delay` allonge le rythme. Une page interdite est comptée (« interdite(s) par robots.txt ») et pas
  lue. Fichier absent (404) : tout est permis. Fichier inaccessible (erreur serveur, 429, pas de réponse) :
  rien
  n'est permis, la passe est refusée avant la première page. `--ignorer-robots` passe outre et s'écrit à
  l'écran et
  dans `resume.json`. Relevé sur le site de test :

  ```text
  Refus : robots.txt inaccessible (statut None) pour http://127.0.0.1:… : rien n'est permis pour cette passe
  (`--ignorer-robots` pour passer outre)
  ```

- **Un site qui n'est pas à nous exige `autorisation`** (règle D-30 du projet : pas de site tiers protégé sans
  autorisation, et divulgation coordonnée si on contourne un détecteur commercial). La recette est refusée à
  la
  lecture si un hôte n'est pas local et que la ligne manque :

  ```text
  recette fautive (…/faux1.yaml) :?  - hotes[0] (ligne 3) : autorisation obligatoire : l'hôte « www.site-tiers.example »
  n'est pas local (D-30)
  ```

  Écrire dans la ligne ce qui donne le droit (accord écrit, périmètre de bug bounty, site que l'on possède)
  ; elle
  est recopiée dans `resume.json`. Un lancement réel sur un site tiers, avec rythme prudent, n'a pas été
  rejoué ici.

- **Arrêt au premier signe d'alerte, sans nouvel essai** (réessayer aggrave). Les signes :
  1. statut 401, 403, 407, 429 ou 503 ;
  2. page de défi : page de l'Arena (`body[data-arena]`), en-tête `cf-mitigated: challenge`, formulaire ou
     cadre de
     défi Cloudflare, cadre ou widget reCAPTCHA, hCaptcha ou Turnstile ;
  3. adresse finale hors des `hotes`, ou hors du motif `url` du type attendu (renvoi vers une connexion,
     l'accueil) ;
  4. `requis` absent sur 3 pages de suite d'un même type ;
  5. plus de 5 échecs (panne réseau, 500, 502, 504) sur les 20 dernières pages.

  La commande écrit l'état, affiche le signe, l'adresse et l'heure, et sort avec le code 3. Ne déclenchent pas
  l'arrêt : un 404 ou 410 (page notée « introuvable »), une page isolée sans son `requis` (notée « anormale
  »). Les
  statuts 500, 502 et 504 et les pannes réseau sont retentés deux fois, avec une attente croissante, avant
  d'être
  comptés comme échec.

- **Jamais de clic sur un défi, aucun solveur de CAPTCHA.** La commande reconnaît un défi, ne fait que cela.
  Seule
  exception volontaire : `porte_entree: {attendre_s: N}` attend, **sans aucune action**, un défi qui se
  valide seul
  sur la première page (au plus N secondes). S'il passe, la passe continue et la porte est comptée à part dans
  `resume.json` ; sinon, arrêt. Un défi plus tard dans la passe arrête toujours. Le moteur `http` ne peut pas
  attendre (pas de JavaScript). Non rejoué ici : aucun défi de ce type sur nos sites de test locaux.
  Nuance du code : avec le moteur `navigateur` et uniquement des hôtes locaux (le labo), l'option
  `resoudre_defis` du navigateur est active pour passer les défis maison de l'Arena ; sur un site tiers elle
  est
  coupée.

- **Les redirections vers un autre site ne sont jamais suivies en `http`.** Chaque redirection est contrôlée
  avant
  d'être demandée (5 sauts au plus) : hôte hors recette = arrêt sur alerte, `robots.txt` interdit = page notée
  interdite. Avec `navigateur`, Chrome suit lui-même les redirections : une garde limite le cadre principal
  aux
  hôtes de la recette et l'adresse d'arrivée arrête la passe si elle sort (non rejoué ici). Relevé en `http` :

  ```text
  ARRÊT : signe d'alerte (redirection vers un autre hôte : autre-site.example) sur http://127.0.0.1:…/fiche/9 à …
  ```

- **Une passe à la fois par recette** (verrou), et le périmètre du labo (`SHADOWLAB_HOTES_AUTORISES`)
  s'applique
  avant chaque requête.

## 9. Quand ça ne marche pas

Les messages ci-dessous sont recopiés de vraies exécutions.

**Recette refusée (code 2).** Le message nomme le chemin de la clé fautive et sa ligne. Le `?` entre deux
fautes remplace un retour à la ligne (voir section 10).

```text
recette fautive (…/faux1.yaml) :?  - pages.fiche.enregistrements[0].champs.prix.format (ligne 20) : valeur admise : 'texte', 'entier', 'nombre' or 'duree_ms'?  - pages.fiche.enregistrements[0].champs.ville.couleur (ligne 21) : clé inconnue
recette fautive (…/faux2.yaml) :?  - pages.liste.enregistrements[0].champs.numero (ligne 14) : adaptatif ne lit que le texte d'un élément : pas attribut
recette fautive (…/faux2.yaml) :?  - pages.liste.enregistrements[0].champs.sans_groupe.motif (ligne 21) : motif de valeur sans groupe « \d+ » : le groupe 1 donne la valeur gardée
recette illisible (…/faux3.yaml) : YAML invalide (ligne 3) : expected ',' or ']', but got '<stream end>'
recette introuvable ou illisible : …/nexiste.yaml ([Errno 2] No such file or directory: '…/nexiste.yaml')
```

Corriger la ligne indiquée et relancer. Les contrôles se font en deux temps : d'abord clé par clé (clé
inconnue,
format, sélecteur invalide, motif sans groupe), puis les renvois d'un type à l'autre (`vers: fichee` absent de
`pages`, hôte absent de `hotes`, autorisation manquante, variable non déclarée). Une deuxième série de
fautes peut
donc apparaître une fois la première corrigée.

**Alertes de lecture** (l'écran de fin et `etat`). Elles sont regroupées par sorte avec un exemple :

```text
Alertes de lecture : 10 au total, 1 sorte(s) parmi les plus fréquentes :
  10 × fiche · champ « distance » : « 1,5 km » n'est pas lisible en entier (ex. http://127.0.0.1:…/fiche/1)
```

Ici le champ est en `format: entier` et le site écrit des décimales : passer à `nombre`. Autres alertes :
`colonne « X » absente de l'en-tête (…)` (nom de colonne faux : recopier celui de la liste entre parenthèses),
`ligne ignorée : N cellules pour M en-têtes` (cellules fusionnées, section 10), `enregistrement « X » ignoré :
clé « Y » sans valeur` (le champ de clé n'a rien lu). Pour vérifier un champ : `essayer` sur une page, ou
`etat --pages`.

**Page non conforme.** La page reçue n'a pas la forme du type attendu. Avec `essayer` :

```text
Page non conforme au type « speciale » : adresse /lab/rallye/rallyes/17 hors du motif url du type « speciale »
(^/lab/rallye/speciales/\d+$)
Page non conforme au type « rallye » : sélecteur requis absent de la page « rallye » : dl.fiche
```

Dans une passe, ces pages sont notées « anormales », rien n'y est lu, et trois de suite pour un même type
déclenchent l'arrêt (signe 4). Causes habituelles : `requis` mal choisi, motif `url` trop strict, ou site
refait.
Autre refus de `essayer` : `aucun type de page de la recette « rallye-demo » ne correspond à
/lab/rallye/pilotes/zz
(`--type` pour en imposer un)`.

**Arrêt sur alerte (code 3).** Lire le signe : un 429 ou un 403 est un refus du site ; un défi est une
protection ;
« redirection vers un autre hôte » est un renvoi vers une autre adresse. Ne pas relancer aussitôt. Attendre
une
heure, ralentir (`rythme: prudent`, ou `delai_s` plus long), puis `reprendre <nom>`. `--maintenant` passe
outre
l'attente : à n'utiliser qu'en connaissant la cause (par exemple un site de test dont on a corrigé la panne).

**Un site arrêté pendant la passe.** Les pages en échec s'accumulent ; au-delà de 5 échecs sur 20 pages, arrêt
(signe 5). Une fois le site revenu : `reprendre`. Une passe tuée net (coupure, `kill`) reste « en_cours » : un
`lancer` est refusé (`la passe 2 n'est pas finie (en_cours)`), `reprendre` marche.

**`noter` sous le seuil (code 1).** Lire les trois lignes (pages, enregistrements, champs), puis les `erreurs`
par champ et les `ATTENTION`. Cas courant : la clé de la recette n'est pas celle que la vérité attend.

```text
  enregistrements 0/500 (0,0 %)
    annonces 0/500 · champs 0/0 (rien à comparer)
  champs 0/0 : rien à comparer, ce n'est pas un succès
  ATTENTION annonces : la clé attendue est `reference` (`reference` absente des enregistrements) ; les
  enregistrements récoltés ont les champs : ref, titre, …
```

Remède : nommer le champ comme la vérité (`reference`). `uv run shadowlab recolte noter <nom> --verite vitrine
--attendu` montre, avant toute note, la clé et les champs attendus. Une note basse peut aussi venir d'une
récolte
partielle (tranche, `--pages-max`) ou de graine et taille différentes entre le site lancé et la vérité
(`SHADOWLAB_VITRINE_GRAINE`, `SHADOWLAB_VITRINE_TAILLE`, `SHADOWLAB_RALLYE_GRAINE`,
`SHADOWLAB_RALLYE_TAILLE`).
Sans `--verite` : `Refus : noter demande --verite vitrine|rallye`.

**Autres refus fréquents (code 2).**

```text
Refus : la passe 2 n'est pas finie (limitee) : `recolte reprendre vitrine-annonces`, ou `lancer … --tout-refaire` pour tout recommencer
Refus : la recette a changé depuis le début de la passe 1 : `reprendre … --recette-modifiee` pour continuer avec la nouvelle
Refus : verrou pris : une passe tourne déjà sur cette recette (processus 47984) (…/outputs/recoltes/vitrine-prudent/verrou)
Refus : --sans : type de page inconnu « fiche » (connus : saisons, calendrier, rallye, speciale, classement, …)
Refus : --tranche attend nom=valeur, reçu « saison »
Refus : aucune récolte « inconnue » dans …/outputs/recoltes/inconnue
```

**La limite `--pages-max` revient à la reprise.** Une passe lancée avec `--pages-max 3` garde cette limite :
un
`reprendre` sans option s'arrête aussitôt (« Limite atteinte (3 pages lues) »). Pour continuer, redonner une
limite plus grande que le nombre de pages déjà lues, par exemple `--pages-max 100000`. La nouvelle limite
n'est
pas gardée pour la reprise d'après.

## 10. Limites connues

Ce que le format de recette ne sait pas exprimer :
- la **classe CSS d'une ligne de tableau** (une `tr class="annulee"`) : un champ ne lit que les cellules de la
  ligne. Contournement : lire une cellule qui porte la même information, ou le texte « Annulée » dans une
  colonne ;
- un **booléen depuis un texte** (« Oui »/« Non », « Disputée »/« Annulée ») : il n'y a que `present`
  (l'élément
  existe ou non) ; sinon la valeur reste du texte à convertir après la récolte ;
- une **date écrite en toutes lettres** (« 16 février 2025 ») : aucun format `date`. Il faut un attribut
  `datetime` ou `data-valeur` dans la page, ou garder le texte ;
- les **cellules fusionnées** (`colspan`, `rowspan`) : la ligne est sautée avec une alerte, ses données ne
  sont
  pas lues ;
- le **défilement infini** et le bouton « voir plus » : le moteur `http` ne voit que le premier chargement ;
  le moteur `navigateur` ne défile ni ne clique pour charger la suite (il n'y a pas de règle pour cela) ;
- les **API internes** (données chargées par un appel JSON) : non lues ; la recette ne lit que des pages
  HTML ;
- un nombre à l'anglaise (`10.5`), une notation scientifique, un temps sans minutes : voir section 5.

Ce qui n'a pas été mesuré ni rejoué :
- **rien n'a été mesuré sur un site réel ni contre une vraie protection.** Tous les essais de ce guide, et
  tous les
  chiffres de durée et de réussite, portent sur nos deux sites factices et sur notre Arena ;
- le moteur `navigateur` n'a pas été rejoué pour ce guide ; les chiffres (7 s par page, 48 pages en 5 min 50
  s)
  viennent de mesures du 12/11 sur le niveau 01 de l'Arena ;
- le **rythme `prudent`** n'a jamais tourné en temps réel sur une récolte entière. Seul essai pour ce guide :
  2 pages en 20,5 secondes (un seul délai tiré). La pause longue et le plafond horaire n'ont tourné qu'avec
  des
  valeurs très courtes ;
- l'arrêt par **Ctrl-C** (statut « interrompue », code 1) n'a pas été rejoué ; seule une passe tuée par signal
  (`kill`) l'a été : elle reste « en_cours » et se reprend ;
- la **porte d'entrée** (`porte_entree`) et le lancement sur un **site tiers avec `autorisation`** n'ont pas
  été
  rejoués.

Ce qui n'existe pas encore :
- `attendre` (attente d'un bloc chargé par JavaScript) est accepté par la lecture de la recette mais sans
  effet ;
- la récolte incrémentale a ses propres limites, dites dans « Récolter seulement le neuf » : retrait d'une
  annonce non signalé, prix changé non vu sans relecture des fiches, recette modifiée sans relecture forcée.

Écarts entre le document de conception et le code (le code fait foi) :
- `attendre` y est décrit comme actif ; il est seulement accepté par la lecture de la recette ;
- `entier` et `nombre` y sont décrits plus simplement : le code accepte aussi les milliers par espace et une
  unité
  après le nombre (`entier`), et les milliers par point (`nombre`) ;
- `--tout-refaire` y « ignore l'historique » : il efface en plus les enregistrements gardés dans l'état.

Défauts connus de la commande (non corrigés par ce guide) :
- un message de recette refusée qui compte plusieurs fautes les écrit sur une ligne, séparées par `?` ;
- le conseil final de `lancer` (`reprendre <nom>`) ne rappelle pas `--sortie` quand elle a été utilisée : il
  faut
  la redonner à la main ;
- `reprendre` garde la limite d'origine de `--pages-max` (section 9) ;
- `essayer` sort en code 0 même quand la page est non conforme ou qu'il n'y a rien à lire ;
- une relocalisation adaptative qui échoue ne dit rien : le champ est simplement vide ;
- `lien: true` rend l'adresse absolue mais garde le fragment `#…` d'un champ, alors qu'un lien à suivre le
  perd.
