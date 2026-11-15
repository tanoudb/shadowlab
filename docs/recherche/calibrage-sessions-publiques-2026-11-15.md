# Calibrage : session 414f351a, trajectoire_lineaire, screen_position_zero (15/11/2026)

- Ce document garde l'enquête sur la quatrième session du site public (`414f351a`, navigateur intégré de l'application Claude) et sur deux règles de l'Arena, `trajectoire_lineaire` et `screen_position_zero`.
- Décision du 15/11 (coordination) : aucune règle ne change, aucune nouvelle décision, pas de campagne ; critère annoncé d'avance dans `docs/DECISIONS.md` (ajout à D-86).
- Ces sessions servent à juger les détecteurs, jamais à régler le moteur.

Enquête en lecture seule : scripts d'enquête non versionnés (dossier de brouillon de la session du 15/11). Aucun fichier du dépôt modifié ; bases ouvertes en `mode=ro`.
Ces sessions servent à juger les détecteurs, pas à régler le moteur. « Présumées humaines » : rien ne prouve qui tient le navigateur.

## A. Faits bruts (première empreinte de chaque session, celle que lisent les détecteurs : `Observations.empreinte_js`)

| | 906fff2e | 52773a43 | 23a7b8a2 | 414f351a |
|---|---|---|---|---|
| Début (UTC) | 14/11 17:21:40 | 14/11 17:40:48 | 15/11 04:35:20 | 15/11 18:06:24 |
| Requêtes HTTP / empreintes | 26 / 3 | 82 / 7 | 127 / 12 | 128 / 11 |
| User-Agent | iPhone, iOS 18_7, Version/26.5.2 Safari | iPhone, iOS 18_7, Version/27.2 Safari | Windows NT 10.0, Chrome/157.0.0.0 | Macintosh 10_15_7, **Claude/5.1231.2** Chrome/156.0.8078.75 |
| `sec-ch-ua` | absent | absent | `"Not-A.Brand";v="99", "Google Chrome";v="157", "Chromium";v="157"` | `"Not:A-Brand";v="8", "Chromium";v="156"` (absent sur une partie des requêtes ; ni « Google Chrome » ni « Claude » dans les marques) |
| `sec-ch-ua-mobile` / platform | absents | absents | ?0 / "Windows" | ?0 / "macOS" |
| `userAgentData` | absent | absent | Not-A.Brand 99, Google Chrome 157, Chromium 157 ; mobile false ; Windows | Not:A-Brand 8, Chromium 156 ; mobile false ; macOS |
| `navigator.platform` / `maxTouchPoints` | iPhone / 5 | iPhone / 5 | Win32 / 0 | MacIntel / 0 |
| `screenX`, `screenY` (lus dans `performance_memory`) | 0, 0 | 0, 0 | 0, 0 | 0, 0 |
| outer (L x H) | 393 x 852 | 402 x 874 | 1440 x 762 | 1680 x 1050 |
| inner (L x H) | 393 x 695 | 402 x 682 (787 sur 2 empreintes) | 1440 x 675 | 1457 x 884 |
| screen (L x H) | 393 x 852 | 402 x 874 | 1440 x 810 | 1680 x 1050 |
| avail (L x H) | 393 x 852 | 402 x 874 | 1440 x 762 | 1680 x 1020 |
| devicePixelRatio | 3 | 3 | 2 | 1 |
| `window.chrome` : app / loadTimes / csi / runtime | faux x4 (`apis.chrome` faux) | faux x4 | **vrai x4** (+ `loadTimes_keys` complètes, `runtime_PlatformOs`) | **faux x4** (mais `apis.chrome` vrai : l'objet existe, sans ces membres) |

Faits : `screenX = screenY = 0` dans les quatre sessions, y compris les deux iPhone. Chaque session garde les mêmes valeurs `screenX/Y` et `fenetre` sur toutes ses empreintes
(sauf `innerHeight` de 52773a43). 23a7b8a2 et 414f351a : `outerWidth` = `screen.width` (fenêtre pleine largeur). `outer_eq_inner` ne se déclenche pour aucune des quatre (hauteurs différentes).

## B. Par page (414f351a et 23a7b8a2)

Sources : `observations_js` `comportement` (observateur du labo : événements `mousemove`, angles plafonnés à 40 par le script `observateur.js:58`) et `trace` (`releve.js` : souris
échantillonnée à 30 Hz au plus, positions horodatées, décodées par somme cumulée par morceau). `début` = arrivée du relevé moins `duree_page_ms`, depuis la 1re requête.
Écarts obs = `delais_souris_ms` (50 premiers écarts d'événements `mousemove`) ; « ident » = effectif du mode (arrondi 0,1 ms) sur le total. Angles trace 30 Hz : même formule que l'observateur
(segments > 3 px) sur la trace sous-échantillonnée, donné à titre indicatif seulement (autre échantillonnage que la règle).
`angles_segments` est déjà plafonné à 40 par le script : la moyenne « des 40 premiers » et « sur tous » du relevé sont donc la même valeur.

**414f351a** (12 relevés, 0 toucher, 0 touche)

| n | chemin | début | durée ms | mousemove | souris trace | clics | scroll | angles | moy. angles | angles trace 30 Hz (nb) | écarts souris (ms) : méd / min / ident | écarts trace méd / min | < 0,08 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | /lab/social/fil | +0,4 s | 329 | 0 | 0 | 1 | 0 | 0 | - | - | - | - | non (0 angle) |
| 2 | /lab/social/p/s5k7pat | +0,8 | 3242 | 71 | 38 | 2 | 34 | 28 | 0,063 | 0,095 (20) | 16,7 / 12,0 / 12 sur 50 | 32 / 8 | **oui** |
| 3 | /lab/social/p/cwccmzp | +4,3 | 4198 | 58 | 29 | 1 | 20 | 27 | 0,056 | 0,086 (13) | 16,7 / 15,8 / 18 sur 50 | 37 / 14 | **oui** |
| 4 | /lab/social/t/calme | +8,6 | 12147 | 216 | 116 | 3 | 119 | 40 | 0,097 | 0,164 (82) | 16,7 / 10,5 / 14 sur 50 | 33 / 7 | non |
| 5 | /lab/social/fil | +20,9 | 2865 | 41 | 20 | 1 | 24 | 19 | 0,149 | 0,130 (9) | 16,7 / 15,6 / 7 sur 40 | 36 / 15 | non |
| 6 | /lab/social/fil | +23,9 | 3286 | 118 | 62 | 1 | 0 | 40 | 0,071 | 0,102 (35) | 16,7 / 15,7 / 21 sur 50 | 34 / 18 | **oui** |
| 7 | /lab/social/u/grain.de.sable | +27,4 | 3606 | 29 | 14 | 1 | 49 | 24 | 0,185 | 0,329 (11) | 16,7 / 10,5 / 7 sur 28 | 31 / 19 | non |
| 8 | /lab/social/p/gmersge | +31,2 | 16983 | 312 | 164 | 5 | 39 | 40 | 0,157 | 0,170 (92) | 16,7 / 15,6 / 10 sur 50 | 35 / 8 | non |
| 9 | /lab/social/fil | +48,3 | 714 | 9 | 4 | 1 | 0 | 2 | 0,122 | 0,158 (1) | 16,7 / 15,0 / 2 sur 8 | 35 / 30 | non (< 10) |
| 10 | /lab/social/explorer | +49,2 | 1628 | 35 | 18 | 1 | 0 | 24 | 0,055 | 0,094 (12) | 16,7 / 15,8 / 9 sur 34 | 31 / 7 | **oui** |
| 11 | /lab/social/p/nhqedm7 | +51,0 | 4149 | 83 | 43 | 4 | 13 | 39 | 0,168 | 0,316 (22) | 16,7 / 15,8 / 18 sur 50 | 37 / 5 | non |
| 12 | /lab/social/t/ville | +55,3 | 4847 | 23 | 13 | 1 | 90 | 9 | 0,079 | 0,062 (5) | 16,7 / 15,9 / 10 sur 22 | 30 / 8 | non (< 10) |

Pages avec >= 10 angles : 9 ; sous 0,08 : 4 (0,063 ; 0,056 ; 0,071 ; 0,055). Écarts `mousemove` : médiane 16,7 ms sur les 11 pages avec souris (cadence 60 Hz).
**Clics sans mouvement de souris précédent sur la même page : 5 sur 22** (page 1 : le seul clic, à 500 ms ; page 8 : clics à 1394 et 1529 ms ; page 11 : clics à 701 et 865 ms, pointeur « souris », éléments « image »).
Les 17 autres clics suivent un échantillon de souris, le dernier de 0 à 766 ms avant le clic. Page 1 : instant du clic en base trace (500 ms) > durée observateur (329 ms) : horloges d'origine différente, non élucidé.

**23a7b8a2** (11 relevés + 1 trace finale sans relevé `comportement` à 04:37:12 : 37 points de souris, 1 clic ; 0 toucher, 0 touche)

| n | chemin | début | durée ms | mousemove | souris trace | clics | scroll | angles | moy. angles | angles trace 30 Hz (nb) | écarts souris (ms) : méd / min / ident | écarts trace méd / min | < 0,08 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | /lab/social/fil | +0,5 s | 31766 | 195 | 60 | 2 | 925 | 40 | 0,096 | 0,336 (45) | 8,4 / 7,8 / 12 sur 50 | 35 / 7 | non |
| 2 | /lab/social/t/lumiere | +32,7 | 4835 | 57 | 23 | 1 | 140 | 18 | 0,114 | 0,135 (13) | 8,4 / 3,4 / 14 sur 50 | 35 / 13 | non |
| 3 | /lab/social/credits | +37,9 | 3603 | 80 | 29 | 1 | 93 | 40 | 0,264 | 0,257 (15) | 8,4 / 0,6 / 12 sur 50 | 35 / 13 | non |
| 4 | /lab/social/credits | +41,9 | 1698 | 43 | 18 | 1 | 0 | 30 | 0,182 | 0,403 (13) | 8,4 / 3,7 / 9 sur 42 | 28 / 14 | non |
| 5 | /lab/social/fil | +44,0 | 5135 | 118 | 43 | 1 | 104 | 40 | 0,102 | 0,140 (29) | 8,5 / 7,2 / 8 sur 50 | 35 / 7 | non |
| 6 | /lab/social/p/s5k7pat | +49,5 | 9763 | 241 | 82 | 1 | 316 | 40 | 0,066 | 0,238 (52) | 8,4 / 2,7 / 9 sur 50 | 35 / 6 | **oui** |
| 7 | /lab/social/fil | +64,0 | 5814 | 266 | 85 | 2 | 70 | 40 | 0,073 | 0,166 (49) | 8,4 / 4,2 / 10 sur 50 | 35 / 6 | **oui** |
| 8 | /lab/social/explorer | +70,2 | 5254 | 123 | 45 | 1 | 134 | 40 | 0,085 | 0,122 (29) | 8,4 / 3,1 / 11 sur 50 | 35 / 7 | non |
| 9 | /lab/social/u/tasse.de.the | +75,8 | 4846 | 93 | 32 | 1 | 51 | 20 | 0,179 | 0,298 (17) | 8,4 / 2,7 / 11 sur 50 | 42 / 7 | non |
| 10 | /lab/social/p/phkyvvq | +81,0 | 8130 | 210 | 77 | 2 | 171 | 40 | 0,198 | 0,192 (44) | 8,4 / 5,0 / 8 sur 50 | 35 / 13 | non |
| 11 | /lab/social/credits | +89,7 | 2958 | 101 | 37 | 1 | 18 | 27 | 0,167 | 0,190 (17) | 8,3 / 2,5 / 16 sur 50 | 35 / 7 | non |

Pages avec >= 10 angles : 11 ; sous 0,08 : 2 (0,066 ; 0,073). Cadence `mousemove` 120 Hz (médiane 8,4 ms). **Clics sans souris précédente : 0 sur 14** (le clic de la trace finale sans relevé n'est pas évalué) (le plus ancien échantillon précédent : 2459 ms avant, page 1).
La règle n'est pas franchie sur les pages 1 à 5 : à 04:36:23.560 (requête de page après le relevé n°6 reçu à 04:36:19.4), un seul signal (0,6) suffit au composite des niveaux 05 à 07.
Observation : l'angle moyen de la trace à 30 Hz est plus grand que celui de l'observateur sur la plupart des pages (échantillonnage différent) ; il ne remplace pas le calcul de la règle.

## C. Lecture du code (`src/shadowlab/detection.py`, sauf mention)

| Signal | Détecteur | Condition exacte | Poids | Famille (coef.) | Niveaux actifs |
|---|---|---|---|---|---|
| `trajectoire_lineaire` | `entropie-interaction` v1.1 (l. 948, signal l. 1015) | pour **chaque** relevé `comportement` : `angles_segments` (l. 1005) de >= 10 valeurs (l. 1006) et moyenne < 0,08 rad (l. 1012) | 0,6 | comportement (1,0) | 05, 06, 07 seulement |
| `screen_position_zero` | `position-fenetre` v1 (l. 1689, signal l. 1704-1710) | `performance_memory.screenX == 0 and screenY == 0` sur la **première** empreinte | 0,4 | empreinte (0,7) soit 0,28 | 06, 07 seulement |
| `outer_eq_inner` | `coherence-profonde` v1.1 (l. 842, signal l. 887-893) | outerWidth = innerWidth ET outerHeight = innerHeight (toutes quatre non nulles) | 0,5 | cohérence (0,8) | 03 à 07 |
| `clic_sans_souris` | `comportement` v2.2 (l. 672, signal l. 721-722) | somme des `mousemove` de tous les relevés = 0 et somme des `click` > 0 | 0,5 | comportement (1,0) | 03 à 07 |
| `pages_eclair` | `comportement` (l. 724-725) | somme des `duree_page_ms` < 500 x nombre de relevés, avec au moins une page « lue » (hors page de défi, l. 716) ; `SEUIL_DUREE_PAGE_MS = 500` (l. 20) | 0,5 | comportement (1,0) | 03 à 07 |
| `chrome_app_absent` | `chrome-apis` v1.1 (l. 1313, signal l. 1355-1356) | « Chrome/ » dans le UA et `chrome_app` faux | 0,5 | empreinte (0,7) | 03 à 07 |
| `loadTimes_absent` | idem (l. 1357-1358) | « Chrome/ » dans le UA et `chrome_loadTimes` faux | 0,5 | empreinte (0,7) | 03 à 07 |
| `csi_absent` | idem (l. 1367-1368) | « Chrome/ » dans le UA et `chrome_csi` faux | 0,25 | empreinte (0,7) | 03 à 07 |

- **Même calcul ?** Il n'existe qu'un seul calcul : `trajectoire_lineaire` n'apparaît dans `detection.py` qu'à la l. 1015 (détecteur `entropie-interaction`). `comportement` n'a pas ce signal. Sous « composite »
  (`site/gardien.py:173-183`), le motif synthétique ne fait que lister les signaux positifs de tous les détecteurs « indéterminés » ; le même signal s'y retrouve donc.
- Le signal est émis **une fois par page** (boucle `for r in releves`, l. 970) : deux pages sous 0,08 donnent 1,2 >= `SEUIL_AUTOMATISE` (1,0, l. 18) : `entropie-interaction` devient alors « automatisé » à lui seul (indépendamment du composite). Cas de 23a7b8a2 en fin de session.
- Un détecteur est « automatisé » si la somme de ses poids >= 1,0 (`_verdict`, l. 184-192). Sinon ses signaux positifs vont au composite : `scoring.score_signaux` (`scoring.py:81-90`) somme poids x coefficient de famille (`scoring.py:12-64`).
- Seuil composite par niveau (`configs/arena/profils.yaml`, l. 54, 110, 162, 220, 278) : 01 aucun (inactif) ; 02 aucun (HTTP/TLS seuls) ; **03 : 1,5 ; 04 : 0,8 ; 05 : 0,6 ; 06 : 0,5 ; 07 : 0,3**.
- `screen_position_zero` pèse 0,28 au composite : sous le seuil du niveau 07 (0,3) à lui seul, mais il suffit d'un autre signal faible pour le franchir. Il ne compte pas aux niveaux 03 à 05.
- La lecture de `screenX/Y` se fait dans `performance_memory` (`site/static/observateur.js:721-722`), pas dans `fenetre`.

## D. Rejeu hors ligne (`d_rejeu.py` : `rejeu.ouvrir_publique` + `rejeu.rejouer(publique=True)` ; neutralisation = `rejeu.registre` remplacé, signaux retirés par `rejeu._SansRegles`)

Contrôle du cas 1 : verdicts identiques à ceux établis (906fff2e et 52773a43 passent 01-07 ; 23a7b8a2 arrêtée 05-07 à 04:36:23.560, composite 0,6 puis 0,88 ; 414f351a arrêtée 03-07 à 18:06:25.368 par `comportement`).

| Cas | 906fff2e, 52773a43 | 23a7b8a2 | 414f351a |
|---|---|---|---|
| 1. courant | 01-07 passent | 05 arrêtée (composite 0,6, trajectoire) ; 06 et 07 (0,88, trajectoire + screen) | 03-07 arrêtée à 18:06:25.368 (empreinte), `comportement` : clic_sans_souris + pages_eclair |
| 2. sans `screen_position_zero` | inchangé | **aucun basculement** : 05 0,6 ; 06 et 07 restent arrêtées (composite 0,6 >= 0,5 et 0,3), même instant | inchangé |
| 3. sans `trajectoire_lineaire` | inchangé | **01-07 passent** (bascule : 05, 06, 07 deviennent « passe ») ; reste à la fin : screen_position_zero seul = 0,28 < 0,5 et < 0,3 | inchangé (arrêtée 03-07 par `comportement`) |
| 4. sans les deux | inchangé | 01-07 passent (même résultat que 3) | inchangé |
| 5. 414f seule, sans `chrome-apis`, `clic_sans_souris`, `pages_eclair` | - | - | **03 et 04 passent** ; **05 arrêtée** à 18:06:28.445 (page) par composite 0,85 = client_hints_absents 0,25 + trajectoire_lineaire 0,6 ; **06 et 07 arrêtées** à 18:06:25.368 (empreinte) par composite 0,88 = client_hints_absents 0,25 + permissions_all_denied 0,35 (0,5 x 0,7) + screen_position_zero 0,28 |
| 5b. 414f : 5 + sans les deux règles | - | - | 03 et 04 passent ; **05 arrêtée** à 18:06:32.936 (page) composite 1,0 (client_hints_absents, navigation_lineaire, timing_quantifie) ; **06 et 07 arrêtées** à 18:06:25.368 composite 0,6 (client_hints_absents + permissions_all_denied) |

Détail du reste de 414f351a en fin de session (signaux positifs, hors `chrome-apis`, `clic_sans_souris`, `pages_eclair`) : `client_hints_absents` 0,25 (regles-http) ; `entropie-interaction` : `timing_quantifie` 0,5 (x3 pages), `timing_trop_regulier` 0,75, `pas_de_pause` 0,5 (à 05-07), `trajectoire_lineaire` 0,6 x4 ; `permissions_all_denied` 0,5 x 0,7 (06-07) ; `screen_position_zero` 0,28 (06-07).
Totaux de fin : 05 : 5,4 (3,0 sans trajectoire) ; 06 : 6,03 (3,35 sans screen et trajectoire).
Bascules : sur 414f351a, retirer les règles `chrome-apis`/`clic_sans_souris`/`pages_eclair` fait passer 03 et 04 ; 05 à 07 restent arrêtés par d'autres signaux, même sans `screen_position_zero` ni `trajectoire_lineaire` (5b). Aucune bascule sur les iPhone (ils passent déjà ; au niveau 07, `screen_position_zero` y vaut 0,28 contre un seuil de 0,3).

## E. Témoins du labo (`outputs/shadowlab.sqlite3`, `mode=ro` ; campagnes 115 `controle_vrai_chrome` et 117 `temoin_mobile_emule` : numéros confirmés dans `experiments`, 135 + 120 = 255 passages)

Moteurs : `patchright` (headless, témoin), `patchright-chrome-interface` (Chrome avec fenêtre), `noezia-natif`, `patchright-chrome-mobile` (Pixel 7). Niveaux : 03, 04, 05, 06scorr.

**Valeurs relevées** (identiques pour tous les passages d'un moteur) :

| Moteur | screenX/Y | outer | inner | screen | avail | DPR | touch |
|---|---|---|---|---|---|---|---|
| patchright headless (45) | 0 / 0 | 1280 x 720 | 1280 x 720 | 1280 x 720 | 1280 x 720 | 1 | 0 |
| patchright-chrome-interface (105) | 22 / 52 | 1282 x 800 | 1280 x 720 | 1280 x 720 | 1280 x 720 | 1 | 0 |
| noezia-natif (45) | 22 / 52 | 1200 x 913 | 1200 x 826 | 1680 x 1050 | 1680 x 957 | 1 | 0 |
| patchright-chrome-mobile (60) | **0 / 0** | 412 x 839 | 412 x 839 | 412 x 839 | 412 x 839 | 2,625 | 1 |

**`screen_position_zero`, par moteur et niveau** (enregistrement `detections` du passage, c.-à-d. relevé après coup ; `screenX/Y = 0` dans l'empreinte donne les mêmes comptes ; dernière colonne : présent dans les motifs d'une décision de l'Arena) :

| Campagne | Moteur | Niveau | Passages | déclenché (detections) | dans une décision de l'Arena | Issue réelle |
|---|---|---|---|---|---|---|
| 115 | headless | 04 / 05 / 06scorr | 15 / 15 / 15 | 15 / 15 / 15 | 0 / 0 / 0 (arrêtés par `ua_headless`, BotD, etc.) | `challenge_non_valide` x45 |
| 117 | chrome-mobile | 03 | 15 | 15 | 0 (détecteur absent du niveau) | 15 réussis |
| 117 | chrome-mobile | 04 | 15 | 15 | 0 | 10 réussis, 5 bloqués |
| 117 | chrome-mobile | 05 | 15 | 15 | 0 | 15 bloqués (composite 0,9 = `aucune_interaction` + `outer_eq_inner`) |
| 117 | chrome-mobile | 06scorr | 15 | 15 | **15** (composite 0,68 = `outer_eq_inner` 0,4 + `screen_position_zero` 0,28) | 15 `challenge_non_valide` (défi-js refusé après la décision du composite) |
| 115 et 117 | interface (105), noezia-natif (45) | tous | - | **0** | 0 | - |

`screen_position_zero` est donc déclenché dans 105 passages sur 255 (45 headless + 60 mobile) ; il pèse dans une décision de l'Arena pour 15 passages seulement (chrome-mobile, 117, niveau 06scorr), les autres étant hors du niveau 06 ou déjà arrêtés pour autre chose.

**Passages dont le verdict basculerait en « passe » si `screen_position_zero` était neutralisé** (rejeu du code courant sur les observations du labo, profil du niveau du passage, `e_labo.py`, `e_detail.py`) :
- `patchright-chrome-interface` niveau 06scorr (117 et 115 : 30 passages bloqués) : **0**. Le signal ne s'y déclenche jamais (screenX/Y = 22/52) ; le blocage vient de `aucune_interaction` seul : composite 0,5 >= 0,5, vérifié sur les 30 passages.
- `patchright-chrome-mobile` niveau 06scorr (117, 15 passages) : **1 sur 15 en rejeu formel, 0 en réalité**. Sans le signal, 14 passages restent arrêtés (à la fin de session, composite 0,9 = `aucune_interaction` 0,5 + `outer_eq_inner` 0,4 ; ce passage de relevé `comportement` existe pour 14 sur 15). Le 15e n'a aucun relevé `comportement` en base (observations coupées par le refus du défi) : il « passe » faute de données, composite 0,4 < 0,5. Aux niveaux 04 et 05 le même moteur est déjà bloqué à 0,9 avec les mêmes deux signaux (15 sur 15 au 05), sans `screen_position_zero`.
- Autres moteurs et niveaux : 0 basculement (headless arrêté par d'autres règles ; noezia-natif jamais arrêté).

**`trajectoire_lineaire`** : **0 passage sur 255** (ni dans `detections`, ni dans les motifs de décision, ni recalculé sur les relevés `comportement` : 0 page sous 0,08). Seul noezia-natif produit des angles (126 pages sur 172 avec >= 10 angles ; moyenne minimale 0,467). Les trois autres moteurs n'émettent aucun mouvement de souris (0 page avec >= 10 angles).

## Non établi / réserves
- Ce que conduisait 414f351a (main ou automate) : non établi, comme demandé. Faits : navigateur intégré d'une application (UA « Claude/… »), pas Google Chrome ; `window.chrome` sans `app`, `loadTimes`, `csi`.
- `screenX/Y = 0` : valeur identique chez quatre sessions de natures différentes (dont deux Safari iPhone). Cause du zéro (navigateur, plateforme ou page) : non établie.
- Instant du clic de la page 1 de 414f351a (500 ms) > durée observateur (329 ms) : l'écart d'horloges n'est pas élucidé.
- Les angles de la trace (30 Hz) ne sont pas ceux de la règle : le relevé `angles_segments` est plafonné à 40 par page.
- Rejeu du labo : aux niveaux 03 et 04, le rejeu arrête des passages réussis dans la campagne (décisions « différées » : la détection est enregistrée mais la page déjà servie) ; ces écarts ne concernent pas `screen_position_zero` (détecteur absent de 03-05).
- Une seule session présumée humaine par profil (Chrome Windows, Claude intégré macOS, deux iPhone) : aucun taux calculable.
