# Récolte générale : une commande, une recette par site

Conception du 12/11/2026, **à valider par Ethan avant toute réalisation**. Aucun code écrit, rien exécuté
(une campagne de mesure tournait). Les chiffres viennent des campagnes 92, 95 et 97 (`docs/PLAN.md` § 2) ou
du code ; les autres sont marqués « estimation » ou « choix ».

## 1. But et critère de réussite

- **But** : tenir la ligne « Livrable » du § 1 du plan : un clone neuf, `uv sync`, **une commande → une
  récolte**, sur tout site décrit par un fichier lisible (la recette), plus seulement sur notre vitrine.
- **Critère** : la même commande rapporte **≥ 99 % des pages et ≥ 99 % des champs exacts** (seuils
  « Récolte » du § 1) sur le site vitrine (liste puis fiches) et sur un site factice de résultats de rallye
  (arbre et tableaux), au niveau 01, reprise après coupure comprise.
- **Pas dans le critère** : la discrétion (étape 1.9) et l'endurance (paliers 2 et 4). La commande s'arrête au
  premier signe d'alerte ; elle ne promet pas de passer une protection.

## 2. Ce qui existe et se réutilise

| Besoin | Existant | Usage |
|--------|----------|-------|
| HTTP, TLS de Chrome, cookies | `engines/curl_cffi_engine.py`, `DriverCurlCffi` | tel quel, + 1 option |
| Redirections contrôlées une à une | `engines/http_base.py`, `DriverHttp._demander` | tel quel |
| Vrai Chrome, identité native (D-59) | `engines/noezia/moteur.py`, `DriverNoezia` | tel quel, + 1 option |
| Périmètre | `perimetre.verifier_url`, `Driver.verifier` | tel quel |
| Sélecteurs, DOM | `engines/noezia/analyseur.py`, `Analyseur.elements`, `Element` | tel quel |
| Listes sans classe commune | `Analyseur.similaires` | tel quel |
| Sélecteur qui casse | `Analyseur.extraire_adaptatif`, `extraction.Signatures` | après 2 corrections |
| Liste puis fiches | `scenarios.recolte_vitrine`, `_lire_fiche`, `aller` | logique généralisée |
| Notation | `notation.noter_recolte` | généralisée |
| Vérité exacte | `site/vitrine.verite()` | modèle du 2e site |
| YAML sûr, validation | `campaigns.charger_yaml`, modèles pydantic de `campaigns.py` | même façon de faire |
| Lancer le site du labo | `campaigns.serveur_local` | tel quel |
| Attente croissante | `DriverNoezia._backoff` | tel quel |
| robots.txt | Protego 0.7.0, déjà dans `uv.lock` (tiré par `scrapling[fetchers]`) | à déclarer |

Pourquoi Protego et pas le module standard : `urllib.robotparser` compare par préfixe seulement, il ne
comprend pas les jokers `*` et `$` courants dans les robots.txt. Protego est déjà installé ; on le déclare
dans `pyproject.toml` puisqu'on l'appelle directement. Aucun paquet nouveau à télécharger.

Ne sert pas : `engines/noezia/recolte.py` (lots d'adresses en parallèle, sans liens ni état : le parallélisme,
c'est le palier 4) ; `engines/noezia/pool.py` (code mort déjà signalé) ; `noezia` en identité réécrite (fuit
« HeadlessChrome », campagne 97).

Pourquoi pas Scrapy, Crawlee ou les « spiders » de Scrapling (file persistante et reprise annoncées dans
`docs/recherche/catalogue.yaml`) : aucun ne passe par `engines/base.Driver` ni par `verifier(url)` à chaque
saut (règle du projet, piège D-07), donc aucun ne pilote NOEZIA en identité native. Scrapy et Crawlee seraient
des dépendances nouvelles. Les spiders de Scrapling 0.5 (installé) sont asynchrones et gardent leur état dans
un fichier `pickle` écrit par défaut toutes les 300 s (`scrapling/spiders/checkpoint.py`) : illisible, et une
coupure perd jusqu'à 5 minutes. Une file SQLite à une transaction par page coûte moins cher que les adapter.

**Ce qui manque**
1. La recette : format, lecture, contrôle ; l'extraction par règles (champs, lignes de tableau lues par nom de
   colonne, liens à suivre).
2. Le parcours d'un site : file, ordre, dédoublonnage, bornes, état sur disque, reprise.
3. robots.txt, rythme par site, arrêt au signe d'alerte (aujourd'hui seulement `RefusProtection`, propre à
   l'Arena, dans `scenarios.aller`).
4. L'export des données.
5. La notation d'un arbre : plusieurs collections, clés composées, valeur attendue vide.
6. Le second site factice.

**Défauts trouvés en lisant le code**, à corriger avant usage :
- `Analyseur.extraire_adaptatif` rend le texte de la signature, **tronqué à 200 caractères** (`_features`,
  `texte[:200]`, `analyseur.py` ligne 28) : une description longue serait fausse.
- Deux règles de texte dans le même fichier : `Element.texte` nettoie chaque morceau puis les joint par une
  espace ; `_features` joint les morceaux bruts (`itertext`), d'où deux espaces dans
  `Réf. <span>AN-1</span>`. Un champ peut changer selon le chemin pris (sélecteur trouvé ou relocalisé).
- `Analyseur.css_un` rend le **premier nœud de texte**, pas le texte de l'élément : sur
  `<p><span>X</span><br>Tél. <span>Y</span></p>` il rend « X ». La commande lira `elements(sel)[0].texte`.
- `notation._egal` compte faux une valeur attendue vide (`None`) même quand rien n'est lu (`obtenu is None`
  rend faux) : à corriger pour les abandons sans temps.
- `DriverCurlCffi` n'imite aucun navigateur par défaut (`impersonate` absent) et ne vérifie jamais le
  certificat (`verify=False`, fait pour l'Arena locale). `DriverNoezia` ignore toujours les erreurs de
  certificat (`ignore_https_errors=True`, lignes 257 et 263). Sur un vrai site : option `verifier_tls`,
  déclarée dans `options_permises`, vraie hors du labo.
- `rapide.recuperer` ouvre une connexion neuve à chaque page (aucun cookie d'une page à l'autre) : la commande
  passe par `DriverCurlCffi`, qui garde sa session.

**Gel du § 6 (« ergonomie du parseur façon Scrapling »)** : la proposition n'y touche pas. Aucune méthode
nouvelle dans `Analyseur` ni `Element` ; deux corrections de défauts (troncature, règle de texte). La lecture
des colonnes par en-tête vit dans le nouveau module de recettes.

## 3. La commande

`shadowlab recolte <action>`. L'actuelle `shadowlab recolter <url> [sélecteur]` (une page) reste telle quelle.

| Action | Rôle |
|--------|------|
| `lancer <recette.yaml>` | nouvelle passe (incrémentale si une passe précédente existe) |
| `reprendre <nom>` | continue la passe coupée ou arrêtée |
| `etat <nom> [--pages]` | où en est la récolte ; `--pages` : le journal page par page |
| `essayer <recette.yaml> <adresse>` | lit une page (ou un `.html`), montre champs et liens, n'écrit rien |
| `noter <nom> --verite vitrine\|rallye` | labo seulement : complétude et exactitude contre la vérité |

Options de `lancer` :

| Option | Effet | Défaut |
|--------|-------|--------|
| `--moteur http\|navigateur` | remplace le moteur de la recette | celui de la recette |
| `--tranche nom=valeur` (répétable) | donne une valeur à une variable de la recette | `*` (tout) |
| `--pages-max N` | arrête la passe après N pages lues | aucun |
| `--sans type,type` | ne visite pas ces types de pages | aucun |
| `--tout-refaire` | ignore les passes précédentes | non |
| `--ignorer-robots` | ne lit pas robots.txt ; écrit dans `resume.json` et à l'écran | non |
| `--sortie DOSSIER` | où vont l'état et les données | `outputs/recoltes/<nom>` |

`reprendre` accepte `--maintenant` (passer outre l'attente conseillée après une alerte) et
`--recette-modifiee` (la recette a changé depuis le début de la passe).

Moteurs : `http` = `DriverCurlCffi` avec `impersonate: chrome` (rapide, sans JavaScript) ; `navigateur` =
`DriverNoezia` avec `channel: chrome`, `identite_native: true`, `headless: false` (vrai Chrome visible,
comportement humain gardé ; `resoudre_defis` seulement sur le labo local). Le moteur se construit avec le
périmètre du labo (`SHADOWLAB_HOTES_AUTORISES`) ; les `hotes` de la recette disent seulement quelles pages
visiter (bloquer les CDN du site dans le navigateur changerait la page et l'empreinte).

Exemple d'appel complet :

```bash
uv run shadowlab recolte lancer configs/recettes/rallye-demo.yaml \
  --tranche saison=2025 --tranche championnat="Coupe Démo Asphalte" --pages-max 300 --sans pilote
```

Codes de sortie : 0 terminée ; 3 arrêtée sur alerte (état gardé) ; 2 refus avant toute requête (recette
invalide, autorisation absente, robots.txt interdit le départ, verrou pris) ; 1 erreur.

Ce qu'elle écrit :

```
outputs/recoltes/vitrine-annonces/      (outputs/ est ignoré par git)
├── etat.sqlite3        la vérité de la récolte : passes, pages, enregistrements, événements
├── verrou              empêche deux passes en même temps sur la même recette
├── signatures.json     signatures de l'extraction adaptative, propres à cette recette
└── passe-001/
    ├── annonces.jsonl  une ligne JSON par enregistrement, un fichier par collection
    └── resume.json     recette, moteur, robots.txt, autorisation, tranche, compteurs, arrêt
```

Une ligne de `annonces.jsonl` (repliée ici pour la lecture ; valeurs d'illustration) :

```json
{"reference": "AN-000001", "titre": "Appartement 3 pièces à Lyon", "type_bien": "Appartement",
 "ville": "Lyon", "code_postal": "69003", "surface": 74, "pieces": 3, "prix": 401500, "dpe": "D",
 "description": "…", "date_publication": "2026-04-18", "nb_photos": 5,
 "agence": "Agence Fictive Horizon", "telephone": "01 99 00 12 34",
 "photos": ["http://127.0.0.1:8770/lab/vitrine/photos/AN-000001/1.svg", "…"],
 "_page": "http://127.0.0.1:8770/lab/vitrine/annonces/AN-000001", "_vu_le": "…", "_passe": 1}
```

Les clés en `_` sont ajoutées par la commande ; la notation ne compare que les champs de la vérité.

`resume.json` (forme ; les compteurs de la vitrine à 500 annonces se déduisent du code) :

```json
{"recette": "vitrine-annonces", "recette_empreinte": "sha256:…", "passe": 1, "statut": "terminee",
 "debut": "…", "fin": "…",
 "moteur": {"nom": "http", "pilote": "curl-cffi", "configuration": {"impersonate": "chrome",
            "verifier_tls": false}, "versions": {"curl_cffi": "0.17.0"}},
 "autorisation": "site à nous (labo local)",
 "robots": {"respecte": true, "agent": "noezia", "adresse": "http://127.0.0.1:8770/robots.txt",
            "statut": 404, "crawl_delay": null},
 "tranche": {}, "bornes": {"pages_max": null},
 "pages": {"faites": 525, "echecs": 0, "interdites_robots": 0, "hors_site": 0, "anormales": 0},
 "enregistrements": {"annonces": 500}, "relocalisations": 0, "arret": null}
```

Journal : la table `pages` de l'état garde une ligne par page (heure, statut HTTP, durée de chargement, durée
totale, enregistrements lus, liens neufs, décision de la sentinelle) ; `recolte etat --pages` l'affiche. Les
événements (début, arrêt, reprise, relocalisation) vont aussi dans le journal existant
`outputs/logs/shadowlab.jsonl` (`journal.py`). Pas de troisième fichier.

Exemple de sortie (forme ; `…` = valeur non connue d'avance) :

```
$ uv run shadowlab recolte lancer configs/recettes/vitrine.yaml
Recette vitrine-annonces · moteur http · autorisation : site à nous (labo local)
robots.txt : http://127.0.0.1:8770/robots.txt → 404, aucune règle (tout est permis)
Site du labo démarré (il ne tournait pas).
Passe 1 · état : outputs/recoltes/vitrine-annonces/etat.sqlite3
  liste 1/… · fiche 20 · annonces 20 · échecs 0
  …
Terminée : 525 pages (25 listes, 500 fiches), 500 annonces, 0 échec, 0 relocalisation, durée …
Données : outputs/recoltes/vitrine-annonces/passe-001/annonces.jsonl

$ uv run shadowlab recolte lancer configs/recettes/rallye-demo.yaml
…
ARRÊT : signe d'alerte (statut 429) sur http://127.0.0.1:8770/lab/rallye/speciales/… à …
Aucun nouvel essai. État gardé : … pages faites, … à faire.
Reprise conseillée après … : uv run shadowlab recolte reprendre rallye-demo
```

## 4. La recette d'un site

Un fichier YAML par site, dans `configs/recettes/`. Il dit où commencer, à quoi ressemblent les pages, quoi
lire, quels liens suivre, et jusqu'où aller. Aucun code. Sur un autre site de même forme, seule la partie
`pages` change (motifs d'adresse et sélecteurs).

**Clés du fichier**
- `recette` : version du format (1). `nom` : nom court, sert de dossier de sortie.
- `autorisation` : pourquoi on a le droit (« site à nous », « accord écrit de … le … »). Obligatoire dès
  qu'un hôte n'est pas local, sinon refus (D-30). Recopiée dans `resume.json`.
- `moteur` : `http` ou `navigateur`.
- `hotes` : hôtes dont on visite les pages ; un lien ailleurs est ignoré et compté.
- `depart` : adresses de départ, chacune avec son type de page.
- `variables` : valeurs par défaut des variables (`*` = tout), remplacées par `--tranche`.
- `parametres_ignores` : paramètres d'adresse sans effet sur la page (jeton, suivi), retirés avant le
  dédoublonnage.
- `rythme` : `libre`, `prudent` ou le détail (§ 5). Défaut : `libre` sur 127.0.0.1, `prudent` ailleurs.
- `robots` : `agent`, le nom présenté au robots.txt (défaut `noezia` ; la règle `*` s'applique s'il n'est
  pas cité).
- `porte_entree` : `attendre_s`, défi qui se valide seul, attendu sans action sur la première page (§ 5).
- `bornes` : `pages_max`, `par_type` (ex. `{rallye: 10}`).
- `pages` : les types de pages (ci-dessous).

L'option qui ignore robots.txt n'existe qu'en ligne de commande, jamais dans la recette : un fichier partagé
ne doit pas l'emporter sans qu'on le voie.

**Clés d'un type de page**
- `url` : expression régulière sur chemin et paramètres (après retrait des `parametres_ignores`) ; la page
  reçue doit y correspondre, sinon alerte.
- `requis` : sélecteur toujours présent sur une vraie page de ce type ; absent = page anormale.
- `attendre` : navigateur seulement, sélecteur à attendre (bloc chargé par JavaScript), 10 s au plus.
- `revisiter` : `toujours`, `jamais` ou `<n>j` (incrémental). Défaut : `toujours` si le type a des `suivre`.
- `enregistrements` : ce qu'on lit. Chacun a une `collection`, une `cle` (un champ ou une liste de champs),
  des `champs`. Pour un tableau, `lignes` (une ligne = un enregistrement) ; pour des blocs répétés sans
  classe commune, `similaires` (un exemple, `Analyseur.similaires` trouve les autres).
- `suivre` : règles de liens : `liens` (sélecteur des `<a>`), `vers` (type de la page cible), `garder_si`.

**Désigner un champ**
- `'sélecteur'` : texte de l'élément ; espaces du bord retirés, suites d'espaces réduites à une.
- `{css: …, attribut: …}` : un attribut (`datetime`, `href`, `data-valeur`, `src`).
- `{adresse: 'motif'}` : un morceau de l'adresse de la page (groupe 1 de l'expression).
- `{colonne: 'Nom'}` : dans `lignes`, la cellule sous l'en-tête « Nom » (ou un rang, 1 = première colonne) ;
  un `css` en plus cherche dans la cellule.
- `motif: '…'` : garde le groupe 1 d'une expression régulière appliquée à la valeur.
- `format` : `texte` (défaut) ; `entier` (chiffres seuls) ; `nombre` (virgule décimale admise, unités
  retirées) ; `duree_ms` (`9:58.7` → 598700, `1:02:03.4` → 3723400).
- `vide_si: [...]` : valeurs qui veulent dire « rien », rendues `null` (`Abandon`, `-`).
- `tous: true` : toutes les valeurs (liste), pas seulement la première. `lien: true` : adresse absolue.
- `present: true` : vrai si l'élément existe, faux sinon.
- `adaptatif: true` : si le sélecteur ne trouve rien, relocalisation par ressemblance
  (`extraire_adaptatif`), comptée et signalée. Jamais par défaut.

Dans un tableau, les lignes sans cellule `td` (en-têtes) sont sautées, et la ligne d'en-tête est la première
ligne à cellules `th` de la même table. Écrire `table.temps tr`, pas `table.temps tbody tr` : un navigateur
ajoute `tbody`, le HTML brut lu en HTTP ne l'a pas toujours.

**Suivre des liens.** Les règles `suivre` se visitent dans l'ordre écrit, les liens dans l'ordre de la page.
`garder_si: {contient: '{saison}'}` garde un lien dont le texte contient la valeur ; avec `contexte: 'tr'`, on
regarde la ligne de tableau qui contient le lien. `*` garde tout.

**Borner la récolte.** Une tranche, c'est une variable : `--tranche saison=2025` ne suit que la saison 2025 ;
`--tranche championnat=…` ne garde que les lignes du calendrier de ce championnat. Puis `--pages-max N`,
`bornes.par_type`, `--sans pilote`. Et surtout ce qu'on ne suit pas : la page d'un châssis renvoie vers des
rallyes d'autres saisons ; la recette ne les suit pas, sinon une tranche déborde sur tout le site.

### (a) Annonces immobilières : le site vitrine

```yaml
# configs/recettes/vitrine.yaml : liste paginée → fiches → 14 champs et les photos.
recette: 1
nom: vitrine-annonces
autorisation: site à nous (labo local)
moteur: http                 # « navigateur » pour une mesure de discrétion
hotes: [127.0.0.1]
depart:
  - url: http://127.0.0.1:8770/lab/vitrine/annonces
    type: liste
parametres_ignores: [sl]     # jeton de session du labo, sans effet sur le contenu
rythme: libre                # site à nous : aucun délai ajouté
pages:
  liste:
    url: '^/lab/vitrine/annonces(\?page=\d+)?$'
    requis: 'a.fiche'
    revisiter: toujours      # de nouvelles annonces peuvent apparaître
    suivre:                  # dans cet ordre : les fiches de la page, puis la page suivante
      - liens: 'a.fiche'
        vers: fiche
      - liens: 'a[rel="next"]'
        vers: liste
  fiche:
    url: '^/lab/vitrine/annonces/AN-\d{6}$'
    requis: '[data-champ="reference"]'
    revisiter: jamais        # « 7j » pour suivre les baisses de prix
    enregistrements:
      - collection: annonces
        cle: reference
        champs:
          reference: '[data-champ="reference"]'
          titre: '[data-champ="titre"]'
          type_bien: '[data-champ="type_bien"]'
          ville: '[data-champ="ville"]'
          code_postal: '[data-champ="code_postal"]'
          surface: {css: '[data-champ="surface"]', attribut: data-valeur, format: entier}
          pieces: {css: '[data-champ="pieces"]', attribut: data-valeur, format: entier}
          prix: {css: '[data-champ="prix"]', attribut: data-valeur, format: entier}
          # Sans attribut prévu pour les robots, le texte affiché marche aussi :
          #   prix: {css: '.bien-prix', format: entier}      « 401 500 € » → 401500
          dpe: '[data-champ="dpe"]'
          description: {css: '[data-champ="description"]', adaptatif: true}
          date_publication: {css: '[data-champ="date_publication"]', attribut: data-valeur}
          nb_photos: {css: '[data-champ="nb_photos"]', attribut: data-valeur, format: entier}
          agence: '[data-champ="agence"]'
          telephone: '[data-champ="telephone"]'
          photos: {css: '.galerie img', attribut: src, tous: true, lien: true}  # adresses, non notées
```

La vitrine porte des attributs `data-champ` qui facilitent tout. Un vrai site n'en a pas : c'est pourquoi le
site de rallye factice n'en aura aucun.

### (b) Résultats de rallye : le site factice (arbre et tableaux)

```yaml
# configs/recettes/rallye-demo.yaml : saisons → calendrier → rallye → spéciales (temps),
# classement, engagés → châssis (historique) et pilotes.
recette: 1
nom: rallye-demo
autorisation: site à nous (labo local)
moteur: http
hotes: [127.0.0.1]
variables:
  saison: '*'                # --tranche saison=2025
  championnat: '*'           # --tranche championnat="Coupe Démo Asphalte"
depart:
  - url: http://127.0.0.1:8770/lab/rallye/saisons
    type: saisons
parametres_ignores: [sl]
rythme: libre
pages:
  saisons:
    url: '^/lab/rallye/saisons$'
    requis: 'ul.saisons'
    suivre:
      - liens: 'ul.saisons a'
        vers: calendrier
        garder_si: {contient: '{saison}'}
  calendrier:                # liste des rallyes d'une saison, paginée
    url: '^/lab/rallye/saisons/\d{4}(\?page=\d+)?$'
    requis: 'table.calendrier'
    revisiter: toujours      # la saison en cours s'allonge
    suivre:
      - liens: 'table.calendrier td.rallye a'
        vers: rallye
        garder_si: {contexte: 'tr', contient: '{championnat}'}
      - liens: 'nav.pages a.suivante'
        vers: calendrier
  rallye:
    url: '^/lab/rallye/rallyes/\d+$'
    requis: 'h1.titre'
    enregistrements:
      - collection: rallyes
        cle: id
        champs:
          id: {adresse: '/rallyes/(\d+)$', format: entier}
          nom: 'h1.titre'
          date_debut: {css: 'p.infos time.debut', attribut: datetime}
          date_fin: {css: 'p.infos time.fin', attribut: datetime}
          championnat: 'dl.fiche dd.championnat'
          surface: 'dl.fiche dd.surface'
          lieu: 'dl.fiche dd.lieu'
          km_chrono: {css: 'dl.fiche dd.km', format: nombre}      # « 142,6 km » → 142.6
    suivre:                  # tout le rallye avant le suivant
      - liens: 'table.speciales td.nom a'
        vers: speciale
      - liens: 'a.classement'
        vers: classement
      - liens: 'a.engages'
        vers: engages
  speciale:
    url: '^/lab/rallye/speciales/\d+$'
    requis: 'h1.titre'       # une spéciale annulée n'a pas de tableau : le titre suffit
    enregistrements:
      - collection: speciales
        cle: id
        champs:
          id: {adresse: '/speciales/(\d+)$', format: entier}
          rallye: {css: 'nav.fil a.rallye', attribut: href, motif: '/rallyes/(\d+)', format: entier}
          numero: {css: 'h1.titre', motif: '^ES(\d+)', format: entier}      # « ES3 · Col de la Brume »
          nom: {css: 'h1.titre', motif: '^ES\d+ · (.+)$'}
          km: {css: 'p.details .km', format: nombre}
          depart: {css: 'p.details time', attribut: datetime}
          annulee: {css: 'p.annulee', present: true}
      - collection: temps
        lignes: 'table.temps tr'
        cle: [speciale, numero]
        champs:
          speciale: {adresse: '/speciales/(\d+)$', format: entier}
          numero: {colonne: 'N°', format: entier}
          rang: {colonne: 'Pos.', format: entier, vide_si: ['-']}
          pilote_id: {colonne: 'Équipage', css: 'a.pilote', attribut: href, motif: '/pilotes/(\d+)',
                      format: entier}
          pilote: {colonne: 'Équipage', css: 'a.pilote'}
          copilote: {colonne: 'Équipage', css: '.copilote'}
          voiture: {colonne: 'Voiture'}
          temps: {colonne: 'Temps'}                                  # texte affiché : « 9:58.7 »
          temps_ms: {colonne: 'Temps', format: duree_ms, vide_si: ['Abandon']}
  classement:                # colonnes dans un autre ordre que les temps : on les lit par leur nom
    url: '^/lab/rallye/rallyes/\d+/classement$'
    requis: 'table.classement'
    enregistrements:
      - collection: classements
        lignes: 'table.classement tr'
        cle: [rallye, numero]
        champs:
          rallye: {adresse: '/rallyes/(\d+)/', format: entier}
          numero: {colonne: 'N°', format: entier}
          rang: {colonne: 'Pos.', format: entier, vide_si: ['Ab.']}
          temps_total_ms: {colonne: 'Temps total', format: duree_ms, vide_si: ['-']}
  engages:
    url: '^/lab/rallye/rallyes/\d+/engages$'
    requis: 'table.engages'
    enregistrements:
      - collection: engages
        lignes: 'table.engages tr'
        cle: [rallye, numero]
        champs:
          rallye: {adresse: '/rallyes/(\d+)/', format: entier}
          numero: {colonne: 'N°', format: entier}
          pilote_id: {colonne: 'Pilote', css: 'a', attribut: href, motif: '/pilotes/(\d+)', format: entier}
          copilote: {colonne: 'Copilote'}
          voiture: {colonne: 'Voiture'}
          chassis: {colonne: 'Châssis'}
          groupe: {colonne: 'Groupe'}
    suivre:                  # un châssis ou un pilote déjà vu n'est pas relu (dédoublonnage)
      - liens: 'table.engages td a[href*="/chassis/"]'
        vers: chassis
      - liens: 'table.engages td a[href*="/pilotes/"]'
        vers: pilote
  chassis:
    url: '^/lab/rallye/chassis/[\w-]+$'
    requis: 'h1.titre'
    revisiter: 30j           # l'historique s'allonge à chaque rallye
    enregistrements:
      - collection: chassis
        cle: code
        champs:
          code: {adresse: '/chassis/([\w-]+)$'}
          marque: 'dl.fiche dd.marque'
          modele: 'dl.fiche dd.modele'
          annee: {css: 'dl.fiche dd.annee', format: entier}
      - collection: historique
        lignes: 'table.historique tr'
        cle: [chassis, rallye]
        champs:
          chassis: {adresse: '/chassis/([\w-]+)$'}
          rallye: {colonne: 'Rallye', css: 'a', attribut: href, motif: '/rallyes/(\d+)', format: entier}
          date: {colonne: 'Date', css: 'time', attribut: datetime}
          pilote_id: {colonne: 'Pilote', css: 'a', attribut: href, motif: '/pilotes/(\d+)', format: entier}
          resultat: {colonne: 'Résultat'}                            # « 3e » ou « Abandon »
    # Pas de « suivre » : l'historique pointe vers des rallyes d'autres saisons.
  pilote:
    url: '^/lab/rallye/pilotes/\d+$'
    requis: 'h1.titre'
    enregistrements:
      - collection: pilotes
        cle: id
        champs:
          id: {adresse: '/pilotes/(\d+)$', format: entier}
          nom: 'h1.titre'
          nationalite: 'dl.fiche dd.nationalite'
```

Les noms de collections et de champs sont ceux de la vérité du site factice (§ 7) : c'est le contrat.

## 5. Le déroulement

**File et ordre.** La file est la table `pages` de `etat.sqlite3`. Au départ : les adresses de `depart`. Une
page lue donne ses liens (règles `suivre`), mis en file avec le type `vers`. Ordre : **profondeur d'abord**,
règles dans l'ordre écrit, liens dans l'ordre de la page. Effet : les fiches d'une page de liste avant la page
suivante (comme `recolte_vitrine`), un rallye entier (spéciales, classement, engagés, châssis neufs) avant le
rallye suivant. Une coupure laisse des rallyes complets, pas des morceaux partout.

**Dédoublonnage.** Adresse canonique : schéma et hôte en minuscules, port par défaut et fragment `#…` retirés,
`parametres_ignores` retirés, autres paramètres triés. Une adresse canonique n'entre qu'une fois dans la file.
Un enregistrement est unique par `(collection, clé)` : relu, il est remplacé, jamais doublé. Limite : deux
adresses différentes pour la même page (`/annonces` et `/annonces?page=1`) sont lues deux fois ; la clé des
enregistrements absorbe le doublon, le coût est une page de plus.

**État et reprise.** Tout est dans `outputs/recoltes/<nom>/etat.sqlite3` (base à part : pas de migration de la
base du labo, dont le n° 9 est réservé au palier 2). Tables : `passes` ; `pages` (adresse, type, état : à
faire, en cours, faite, échec, interdite, hors tranche ; statut, durées, heure, essais) ; `enregistrements`
(collection, clé, données, empreinte, page, première et dernière passe) ; `evenements`. Une page = une
transaction : page faite et enregistrements écrits ensemble, ou rien. Après une coupure (Ctrl-C, panne, Mac
qui s'endort), `reprendre` remet les pages « en cours » à faire et continue la même passe. La recette est
comparée à son empreinte de départ : modifiée, refus sauf `--recette-modifiee`. Les `.jsonl` sont réécrits
depuis la base à la fin et à chaque arrêt : la base fait foi. La file est pensée pour l'étape 4.2 (« file
d'adresses à récolter en SQLite ») : le palier 4 y ajoutera l'identité qui prend chaque page.

**Rythme et pauses.** Le délai compte depuis le début de la page précédente ; le temps déjà passé par le
moteur (chargement, gestes humains) est déduit, pour ne pas doubler les pauses.

| Réglage | `libre` (127.0.0.1) | `prudent` (ailleurs) | Source |
|---------|---------------------|----------------------|--------|
| `comportement` (souris, défilement ; navigateur) | oui | oui | option `interaction_post_page` |
| `delai_s` [min, médiane, max], tirage log-normal | [0, 0, 0] | [3, 8, 30] | choix |
| `pages_par_heure_max` | aucun | 300 | choix |
| `pause_longue` | aucune | 2 à 5 min toutes les 40 à 80 pages | choix |
| `Crawl-delay` du robots.txt | appliqué | appliqué s'il est plus long | usage courant (hors RFC 9309) |
| Essais sur panne réseau, 500, 502, 504 | 2, attente croissante | 2 | `_backoff` du moteur |
| Délai maximal d'une page | 30 s | 30 s | `timeout` de curl-cffi |

Les valeurs « choix » sont à recaler par la mesure (`recolte-rythme.yaml`, puis Cloudflare en 1.8). Avec
`prudent`, le débit tombe vers 230 à 300 pages par heure (estimation par le calcul).

**Arrêt au premier signe d'alerte.** Première version de la sentinelle de l'étape 2.6, dans son propre module
pour que le palier 2 la complète au lieu de la refaire. Signes :
1. statut 401, 403, 407, 429 ou 503 ;
2. page de défi : `body[data-arena]` (Arena) ; en-tête `cf-mitigated: challenge` ou page de défi Cloudflare
   (formulaire de défi, cadre `challenges.cloudflare.com`) ; cadre reCAPTCHA, hCaptcha ou Turnstile sur une
   page de contenu ;
3. adresse finale hors des `hotes`, ou hors du motif `url` du type attendu (renvoi vers une connexion ou
   l'accueil) ;
4. `requis` absent sur 3 pages de suite d'un même type (page vide servie à la place du contenu, ou site
   refait) ;
5. plus de 5 échecs (réseau, 500, 502, 504) sur les 20 dernières pages.

Réaction : plus aucune requête, état écrit, message (signe, adresse, heure), code 3. Aucun nouvel essai sur
les signes 1 à 4 : réessayer aggrave. `reprendre` conseille d'attendre 1 h (choix) ; `--maintenant` passe
outre. Ne déclenchent pas l'arrêt : un 404 (page notée introuvable), une page isolée sans `requis` (notée
anormale, comptée).

**Porte d'entrée.** Avec `porte_entree: {attendre_s: 15}`, sur la première page seulement, un défi qui se
valide seul (Cloudflare sans case à cocher, calcul de l'Arena) est attendu sans aucune action, 15 s au plus.
S'il passe : on continue, compté à part dans `resume.json`. Sinon : arrêt. Un défi plus tard dans la passe est
une alerte. Aucun clic, aucune résolution : c'est la règle « aucun solveur de CAPTCHA réel » et le compte du
§ 1 (défi sans action = réussi compté à part ; défi avec action = échec).

**Récolte incrémentale.** Un second `lancer` ouvre une nouvelle passe qui s'appuie sur les précédentes : un
type `revisiter: jamais` déjà fait n'est pas relu ; `toujours` est relu ; `<n>j` est relu s'il date de plus de
n jours. Les listes relues font découvrir les nouvelles fiches, seules lues. Chaque enregistrement garde une
empreinte : `nouveautes.jsonl` liste les nouveaux et les modifiés (`_changement`), les fichiers par collection
gardent tout ce qui est connu. `--tout-refaire` ignore l'historique. Pour le rallye : une saison passée ne
change plus (`calendrier` relu seulement pour la saison en cours, via `--tranche`).

## 6. Volume et durée

Vitesses mesurées : NOEZIA ≈ 7 s par page (campagne 92 : 295 s pour 42 pages ; campagne 95 : 58 à 65 min
pour environ 525 pages, dont 25 à 30 s de chargement, le reste en gestes et pauses). Sans pause, en local,
les témoins mettent 36 à 47 s pour les mêmes pages (campagne 95), soit 0,07 à 0,09 s par page. L'identité
native n'a jamais fait de récolte complète : on lui suppose le même rythme, son comportement simulé étant le
même (estimation).

| Pages | NOEZIA, 7 s/page, sans arrêt | Prudent, ≈ 250 pages/h (estimation) | Sans pause, en local |
|-------|------------------------------|-------------------------------------|----------------------|
| 500 | ≈ 1 h (mesuré : 58 à 65 min) | ≈ 2 h | 36 à 47 s (mesuré) |
| 10 000 | ≈ 19 h 30 | ≈ 40 h | ≈ 15 min |
| 600 000 | ≈ 49 jours | ≈ 100 jours | ≈ 15 h |

Sur des journées de 8 h (estimation d'un rythme humain) : 10 000 pages = 2,5 jours à 7 s/page, 5 jours en
prudent ; 600 000 pages = 146 jours, ou 300 jours en prudent. Dernière colonne : borne basse sur notre
machine, sans réseau réel ni protection ; inatteignable sur un vrai site sans se faire repérer.

Ce que cela impose :
- **Un site entier de plusieurs centaines de milliers de pages n'est pas à la portée d'une identité.** On
  récolte par tranches : une saison, un championnat. Sur le site factice, un rallye fait environ 15 à 21
  pages (rallye, classement, engagés, 4 à 10 spéciales, et en moyenne 8 pages de châssis et de pilotes
  neufs ; estimation par la formule du § 7), donc une saison de 8 rallyes ≈ 120 à 170 pages, 15 à 20 min
  au rythme mesuré.
- **Un budget par identité et par jour.** Le test prévu en 2.4 bannit à 2 000 pages en 24 h (seuil du test
  de l'Arena, pas d'un vrai site). À ce plafond, 10 000 pages en 3 jours demandent au moins 2 identités, et
  600 000 pages en un mois environ 10 identités. C'est le palier 4 (identités impossibles à relier, un proxy
  chacune, étape 4.2) et le budget de l'étape 2.7 ; cette brique ne les conçoit pas, elle prépare la file.
- **Une longue récolte sur le Mac** : il s'endort après 1 minute sans activité (noté le 12/11 dans
  `notes/ia/questions-ouvertes.md`) ; la commande lance `caffeinate` pendant une passe en mode navigateur, ou
  le dit. Une fenêtre Chrome reste ouverte à l'écran.

## 7. Le second site factice : résultats de rallye

**Où** : `src/shadowlab/site/rallye.py` (génération, vérité, pages HTML), routes dans `site/app.py` sous
`/lab/rallye/...` (même intergiciel que le reste de `/lab`, donc les niveaux de l'Arena s'y appliquent),
style sobre dans `site/static/rallye.css`, réglages `SHADOWLAB_RALLYE_GRAINE` et `SHADOWLAB_RALLYE_TAILLE`
dans `config.py`. Labo seulement : il n'entre pas dans l'application publique.

**Pages** (aucun attribut `data-champ` : du HTML de site ordinaire)
- `/lab/rallye/saisons` : liste des saisons (`ul.saisons`).
- `/lab/rallye/saisons/<année>?page=<n>` : calendrier, `table.calendrier` (Date, Rallye, Championnat,
  Surface, Lieu), 6 rallyes par page pour que la pagination serve (`nav.pages a.suivante`).
- `/lab/rallye/rallyes/<id>` : nom, dates (`<time datetime>`), fiche (`dl.fiche`), tableau des spéciales,
  liens « Classement » et « Engagés ».
- `/lab/rallye/speciales/<id>` : fil d'Ariane vers le rallye, titre « ES3 · Col de la Brume », longueur,
  heure de départ, `table.temps` (Pos., N°, Équipage, Voiture, Temps, Écart).
- `/lab/rallye/rallyes/<id>/classement` : `table.classement` (Pos., N°, Équipage, Groupe, Voiture, Temps
  total, Écart).
- `/lab/rallye/rallyes/<id>/engages` : `table.engages` (N°, Pilote, Copilote, Voiture, Châssis, Groupe).
- `/lab/rallye/chassis/<code>` : marque, modèle, année, `table.historique` (Date, Rallye, Pilote, Résultat).
- `/lab/rallye/pilotes/<id>` : nom, nationalité.

**Pièges voulus** (ceux d'un vrai site de résultats) : temps à heures (`1:02:03.4`) et à minutes
(`9:58.7`) ; abandons sans temps ; ex aequo (même temps, même rang) ; spéciale annulée sans tableau ; colonnes
dans un autre ordre entre temps et classement ; pilote et copilote dans une même cellule ; châssis qui passe
de pilote en pilote et de saison en saison ; noms à accents et apostrophes. Tout est inventé : rallyes,
pilotes, marques et codes de châssis manifestement fictifs.

**Volume réglable** : `SHADOWLAB_RALLYE_TAILLE` = nombre de rallyes (défaut 24), 8 rallyes par saison, 4 à
10 spéciales, 12 à 30 engagés, 4 châssis et 4 pilotes par rallye en réserve partagée. Pages ≈ 1 + 2 × saisons
\+ rallyes × (3 + spéciales) + châssis + pilotes : environ 440 pages pour 24 rallyes, proche des 525 de la
vitrine (estimation par la formule, à recompter au premier test). Environ 3 500 lignes de temps (estimation).

**Vérité** : `rallye.verite(graine, taille)`, comme `vitrine.verite()` : déterministe, sérialisable en JSON,
avec `collections` (rallyes, speciales, temps, classements, engages, chassis, historique, pilotes),
`cles` (ex. `temps` : `[speciale, numero]`) et `pages` (toutes les adresses attendues).

**Noter une récolte en arbre** : `noter_recolte` reçoit deux paramètres de plus (`liste`, `cle`, clé
composée admise) et est appelé une fois par collection ; une fonction `noter_pages` compare les pages faites
aux pages attendues. Résultat : par collection, enregistrements retrouvés et champs exacts ; au total, pages,
enregistrements et champs, chacun contre le seuil de 99 %. Pour la vitrine, `vitrine.pages_attendues()`
(nouvelle, petite) donne les 25 listes et 500 fiches ; sa vérité ne change pas, et `recolte_vitrine` reste
noté comme aujourd'hui.

## 8. Étapes de réalisation

Tailles (estimation) : petite = un module court et ses tests ; moyenne = deux ou trois modules ; grande = un
sous-ensemble complet. Rien ne démarre pendant une campagne de mesure (règle du projet).

1. **Lire une recette, extraire une page** (moyenne)
   - Livre : le format, sa lecture et son contrôle ; `extraire(html, adresse, type)` qui rend
     enregistrements et liens ; `configs/recettes/vitrine.yaml` ; les deux corrections de
     `Analyseur.extraire_adaptatif`.
   - Fichiers : `engines/noezia/recettes.py` (nouveau), `engines/noezia/analyseur.py`,
     `tests/test_recettes.py`.
   - Test vu en échec d'abord : la recette appliquée aux pages de `vitrine.page_fiche` pour 45 annonces égale
     `vitrine.verite()["annonces"]` ; une description de 300 caractères relocalisée reste entière ; une
     recette fautive (clé inconnue, motif invalide, `vers` vers un type absent) est refusée avec un message
     clair.
   - Fin : tests rapides verts, `ruff` propre.

2. **Parcours HTTP, état, reprise, commande** (grande) : **Ethan a un outil utilisable ici**, sur les sites
   sans protection qu'il a le droit de viser.
   - Livre : `recolte lancer | reprendre | etat | essayer`, moteur `http`, file SQLite, ordre, dédoublonnage,
     bornes, tranches, robots.txt (Protego), rythme, export, verrou ; option `verifier_tls` de
     `DriverCurlCffi` ; démarrage du site du labo s'il ne tourne pas.
   - Fichiers : `engines/noezia/parcours.py` (nouveau), `cli.py`, `engines/curl_cffi_engine.py`,
     `pyproject.toml` (Protego), `tests/test_parcours.py`, `tests/test_cli_recolte.py`.
   - Test vu en échec d'abord (pilote factice branché sur le `TestClient` du site, ni réseau ni navigateur) :
     vitrine à 45 annonces → 45 enregistrements, 48 pages ; coupure forcée à la page 20 puis `reprendre` →
     même résultat, aucune page lue deux fois ; robots.txt qui interdit une fiche → jamais demandée, comptée ;
     `--ignorer-robots` → écrit dans `resume.json` ; redirection vers un autre hôte → alerte ; `--pages-max`.
   - Fin : tests verts ; après la campagne, `recolte lancer configs/recettes/vitrine.yaml` → 525 pages,
     500 annonces.

3. **Notation générale** (petite), en parallèle des étapes 1 et 2.
   - Livre : `noter_recolte` avec `liste` et `cle` (clé composée), valeur attendue vide, `noter_pages` ;
     `vitrine.pages_attendues()` ; `recolte noter`.
   - Fichiers : `notation.py`, `site/vitrine.py`, `tests/test_notation.py`.
   - Test vu en échec d'abord : clé composée ; `None` attendu et rien lu = exact ; les 8 tests actuels
     inchangés.
   - Fin : `recolte noter vitrine-annonces --verite vitrine` → pages 525/525, annonces 500/500,
     champs 7 000/7 000.

4. **Moteur navigateur et sentinelle** (moyenne), après l'étape 2.
   - Livre : `moteur: navigateur` (identité native) ; la sentinelle (§ 5) ; la porte d'entrée ; option
     `verifier_tls` de `DriverNoezia` ; `resoudre_defis` coupé hors du labo local.
   - Fichiers : `engines/noezia/sentinelle.py` (nouveau), `parcours.py`, `engines/noezia/moteur.py`,
     `tests/test_sentinelle.py`.
   - Test vu en échec d'abord : un 429 à la page 10 → zéro requête ensuite, passe « arrêtée », `reprendre`
     possible ; page de défi de l'Arena → alerte ; page de défi Cloudflare (fixture écrite à la main) →
     attente sans action puis arrêt ; `requis` absent 3 fois → alerte ; 404 → on continue.
   - Fin : tests verts ; après la campagne, vitrine à 500 en navigateur au niveau 01 → ≥ 99 % partout.

5. **Site factice de résultats de rallye** (grande), en parallèle des étapes 1 à 4.
   - Livre : le site du § 7, sa vérité, ses réglages, son style.
   - Fichiers : `site/rallye.py` (nouveau), `site/app.py`, `config.py`, `site/static/rallye.css`,
     `tests/test_rallye.py`.
   - Test vu en échec d'abord (calqué sur `tests/test_vitrine.py`) : même graine = mêmes données ; vérité
     sérialisable ; un parcours HTTP écrit dans le test retrouve la vérité à 100 % ; 404 sur l'inconnu ;
     échappement HTML ; chaque piège du § 7 présent au moins une fois.
   - Fin : tests verts ; rendu vérifié à l'écran.

6. **Recette du rallye et preuve sur les deux sites** (moyenne), après 3, 4 et 5.
   - Livre : `configs/recettes/rallye-demo.yaml`, écrite à partir des pages seules (§ 12) ; deux scénarios
     `recolte_recette_vitrine` et `recolte_recette_rallye` qui appellent le parcours et notent ; une campagne
     `configs/experiments/recolte-generale.yaml` (curl-cffi et noezia natif, niveau 01, 3 répétitions ;
     environ 6 h, estimation).
   - Fichiers : la recette, `scenarios.py`, la campagne, `tests/test_recolte_generale.py` (intégration).
   - Test vu en échec d'abord : la même commande sur les deux sites → pages, enregistrements et champs ≥ 99 %.
   - Fin : chiffres en base, écrits au § 2 du plan avec le n° de campagne.

7. **Récolte incrémentale** (moyenne), après l'étape 2.
   - Livre : `revisiter`, empreintes, `nouveautes.jsonl`, `--tout-refaire`.
   - Fichiers : `parcours.py`, `tests/test_parcours.py`.
   - Test vu en échec d'abord : vitrine à 45 puis à 50 annonces → la seconde passe relit les 3 listes et
     les 5 fiches neuves seulement ; `nouveautes.jsonl` en compte 5.
   - Fin : tests verts.

8. **Documentation du livrable** (petite), en dernier.
   - Livre : `docs/recolte.md` (écrire une recette, chaque clé, les pièges), README, `AGENTS.md` (commandes
     vérifiées, carte du code), décision D-xx (numéro vérifié sur toutes les branches distantes), plan § 8.
   - Fin : un clone neuf, `uv sync`, `uv run shadowlab recolte lancer configs/recettes/vitrine.yaml` → une
     récolte complète (ligne « Livrable »).

Ordre conseillé : 1 → 2 → 4, avec 3 et 5 en parallèle ; puis 6 ; 7 dès que 2 est fusionné ; 8 à la fin.

## 9. Hors périmètre de cette brique

- Plusieurs identités, proxys, répartition de la file (palier 4) ; identité persistante, compte connecté,
  connexion à un site (étapes 2.5 et 2.8) ; budget par identité et plages horaires (2.7).
- Serveur Linux sans écran (palier 3) : le mode navigateur demande un écran et Google Chrome.
- Toute résolution de CAPTCHA, tout clic sur un défi.
- Défilement infini, bouton « voir plus », formulaires de recherche, API JSON internes, plans de site
  (`sitemap.xml`).
- Téléchargement des photos (adresses seulement) ; suivi des annonces retirées.
- Plusieurs pages à la fois dans une même identité.
- Couche IA qui écrirait une recette seule (gelée, § 6 du plan).
- Viser le site de rallye réel : décision d'Ethan (D-30).

## 10. Risques et points faibles

- **« N'importe quel site » est trop dire.** Il faut une recette par site, écrite par quelqu'un. Les grands
  portails d'annonces chargent souvent leurs listes par JavaScript ou par une API interne, avec un bouton
  « voir plus » : la v1 ne sait pas cliquer pour charger la suite. Ces sites sortent du format tant qu'on ne
  l'étend pas.
- **On teste ce qu'on a construit.** Le site factice et sa recette viennent de la même main : le format peut
  coller à notre HTML et casser sur un vrai site. Parade partielle : HTML sans aide, pièges réels, recette
  écrite à partir des pages seules.
- **Vitesse.** Au rythme qui passe aujourd'hui (≈ 7 s par page), un site entier est hors de portée d'une
  identité (§ 6). La brique ne règle pas le volume ; elle le rend reprenable par tranches.
- **Cloudflare réel jamais mesuré** (étape 1.8 à faire). L'identité native tient les niveaux 01 à 03 de notre
  Arena (campagne 97), rien de plus n'est prouvé. La porte d'entrée peut ne jamais s'ouvrir pour un Chrome
  piloté.
- **Navigation par adresse directe.** Comme `recolte_vitrine` aujourd'hui, chaque page s'ouvre par son
  adresse : sans référent, et très probablement avec `Sec-Fetch-Site: none`, ce qu'un humain qui clique
  n'envoie pas. À vérifier dans `observations_http` ; si l'Arena ou Cloudflare le relève, il faudra cliquer
  et revenir en arrière, ce qui complique la file.
- **Relocalisation trompeuse.** Sur un vrai site, sans vérité, une relocalisation fausse passe inaperçue.
  D'où `adaptatif` jamais par défaut, et chaque relocalisation comptée et marquée dans l'enregistrement.
- **Tableaux complexes.** Cellules fusionnées (`rowspan`, `colspan`) ou en-têtes sur deux lignes : la lecture
  par nom de colonne se trompe. Non traité en v1.
- **Liens pièges.** Une règle `suivre` trop large (`a`) suivrait un lien piège invisible : en HTTP, la
  visibilité ne se voit pas. Les recettes doivent viser des liens précis.
- **robots.txt n'est qu'une convention.** Le site de rallye cité refuse des agents IA nommés. NOEZIA ne porte
  aucun de ces noms et tomberait sous la règle générale `*` : respecter la lettre n'est pas respecter
  l'intention. Raison de plus pour demander l'accord du site.
- **Droit.** Des pages de résultats contiennent des noms de vraies personnes (pilotes) et une annonce le nom
  et le téléphone d'un agent : données personnelles (RGPD) dès qu'on les garde et les réutilise. Extraire
  une part substantielle d'une base de données peut aussi heurter le droit du producteur de la base (UE).
  À regarder avant de livrer quoi que ce soit à un client.
- **Doublon de code temporaire** : `recolte_vitrine` et la commande font la même chose jusqu'à ce que la
  campagne de l'étape 6 montre qu'ils se valent ; alors le scénario appelle la commande.
- **Rien n'a tourné.** Toutes les durées viennent des campagnes 92 et 95 (identité réécrite) ; l'identité
  native n'a jamais fait de récolte complète.

## 11. Questions pour Ethan

1. **Le site de rallye réel : as-tu leur accord ?** Sans accord, la règle D-30 interdit d'y pointer le moteur,
   et leur robots.txt refuse les agents IA. Ma recommandation : leur demander un accès ou un export ; d'ici
   là, on prouve sur le factice. La commande demandera une ligne `autorisation` à toute recette qui vise un
   site qui n'est pas à nous.
2. **Moteur par défaut sur un site qui n'est pas à nous : navigateur (discret, lent) ou HTTP (rapide, repéré
   plus vite) ?** Recommandation : navigateur ; HTTP pour nos sites et les sites sans protection.
3. **Rythme par défaut sur un site tiers : 300 pages par heure au plus, pauses longues, environ 250 pages par
   heure en moyenne. D'accord ?** Recommandation : oui, puis recaler après `recolte-rythme.yaml` et la mesure
   Cloudflare.
4. **Format des données : JSON Lines (un fichier par collection) te suffit, ou il te faut du CSV pour tes
   clients ?** Recommandation : JSON Lines, plus un CSV par collection en fin de passe (petit ajout).
5. **Photos des annonces : les adresses seulement, ou les fichiers ?** Recommandation : les adresses ; le
   téléchargement plus tard, en option (il multiplie les requêtes : 3 à 6 photos par annonce sur la vitrine).

## 12. Désaccords avec les décisions de la coordination

1. **Critère : ajouter « ≥ 99 % des enregistrements ».** Une page peut être lue et son tableau à moitié lu ;
   l'exactitude ne compte que les enregistrements retrouvés. Pages, enregistrements et champs, chacun ≥ 99 %.
2. **Extraction adaptative : oui, mais jamais par défaut.** La décision 4 veut la réutiliser ; je la garde
   champ par champ (`adaptatif: true`), comptée et signalée, pour la raison du § 10.
3. **Qui écrit la recette du rallye.** Pour que la preuve vaille, elle est écrite à partir des pages seules,
   par un agent qui n'a pas lu `rallye.py`. C'est aussi le test de la décision 5 (un autre développeur
   reprend un site par sa recette).
4. **Le mot « recette »** veut aussi dire « tests d'acceptation » dans l'informatique française. Je le garde
   (décision prise) ; on peut lui préférer « fiche de site » si Ethan trouve l'ambiguïté gênante.
