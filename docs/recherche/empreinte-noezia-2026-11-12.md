# Origine des différences d'empreinte NOEZIA / témoin Patchright

- **Date** : 12/11/2026
- **Base** : `outputs/shadowlab.sqlite3`, campagne 94, niveau `04scdp`, première empreinte (`observations_js`, `kind = 'empreinte'`).
- **Observations utilisées** : `65292` (noezia) et `65392` (patchright, le témoin).
- **Lecture seule** : aucun test ni navigateur lancé, aucun fichier existant modifié.
- **Limite importante** : les sections 1 à 3 disent d'où vient chaque écart avec le témoin, pas ce qu'un vrai
  Chrome aurait donné. Une première référence « vrai Chrome » existe depuis le 12/11 (campagne 96) : voir la
  section 4, « Comparaison avec un vrai Chrome ». Elle vient d'un seul Chrome, sur une seule machine, piloté
  par Patchright ; ce n'est pas encore une session humaine (`shadowlab rejeu`, aucune session humaine en base).

Chiffres : 315 champs aplatis (clés pointées, une liste = une valeur), **84 diffèrent**.
Le témoin est le même Chromium lancé sans interface et sans aucun réglage
(`playwright_engine.py:25-27` pour le lancement, `:41` pour le contexte, sans option). NOEZIA le lance avec
`moteur.py:194-208` et un contexte réglé par le profil (`moteur.py:229-249`) plus les scripts injectés
(`moteur.py:252`, assemblés par `furtivite/patches.py:45-103`).

Abréviations : `moteur.py` = `src/shadowlab/engines/noezia/moteur.py` ; `generateur.py` = `profils/generateur.py` ;
les `.js` sont dans `furtivite/`. Les scripts JS sont tous dans une seule injection : ordre `patches.py:65-101`.

## 1. Tableau des différences, regroupées par cause

Les valeurs « NOEZIA » viennent de l'observation 65292, les valeurs « témoin » de la 65392. `abs.` = champ absent.

### 1.A Nature : masque le mode sans interface (31 champs)

| Champ(s) | NOEZIA | Témoin | Origine dans le code | Remarque |
|---|---|---|---|---|
| `permissions.notification` | `default` | `denied` | `navigateur.js:125-130` (getter `Notification.permission` forcé à `default`) | Le Chromium sans interface répond `denied`. |
| `navigateur.plugins`, `navigateur.mimeTypes` | 4 et 4 | 0 et 0 | `navigateur.js:71-123` (faux plugins PDF, faux types MIME) | Les nombres 4 et 4 sont un choix du moteur ; pas de référence humaine. |
| `apis.chrome` | `true` | `false` | `navigateur.js:265` (`window.chrome = {}` créé s'il manque) | Le témoin n'a pas d'objet `window.chrome`. |
| `chrome_apis.chrome_app`, `chrome_app_getDetails`, `chrome_app_isInstalled`, `chrome_app_runningState` | `true`, `true`, `false`, `true` | `false`, abs., abs., abs. | `navigateur.js:268-279` (`chrome.app` fabriqué) | |
| `chrome_apis.chrome_csi`, `csi_keys`, `csi_pageT_positif` | `true`, `["onloadT","pageT","startE","tran"]`, `true` | `false`, abs., abs. | `navigateur.js:319-330` (`chrome.csi`) | |
| `chrome_apis.chrome_loadTimes`, `loadTimes_keys`, `loadTimes_requestTime_positif`, `loadTimes_connectionInfo` | `true`, 13 clés (`commitLoadTime` … `wasNpnNegotiated`), `true`, `http/1.1` | `false`, abs., abs., abs. | `navigateur.js:333-360` (`chrome.loadTimes`) | `connectionInfo` = `http/1.1` (`:346`) alors que `npnNegotiatedProtocol` = `h2` (`:352`) : deux champs du même faux objet se contredisent. |
| `chrome_apis.chrome_runtime`, `runtime_connect`, `runtime_sendMessage`, `runtime_PlatformOs` | `true` ×4 | `false`, abs. ×3 | `navigateur.js:282-316` (`chrome.runtime` fabriqué) | |
| `navigateur.userAgentData.brands` | `Not:A-Brand 8`, `Chromium 156`, `Google Chrome 156` | `Not:A-Brand 8`, `Chromium 156`, `HeadlessChrome 156` | `navigateur.js:172-192` (`nettoyer` remplace `HeadlessChrome` par `Google Chrome`) | La version 156 est celle du vrai binaire. |
| `botd.bot`, `botd.botKind` | `false`, abs. | `true`, `headless_chrome` | Conséquence du User-Agent sans `Headless` (`moteur.py:233`, voir 1.C `navigateur.userAgent`) et de `navigateur.js` | BotD lit le jeton `HeadlessChrome` ; sa sortie n'est pas un champ réécrit en soi. |
| `headless_signals.voices_count` | 4 | 0 | `headless.js:42-74` (`speechSynthesis.getVoices` remplacé par 4 voix macOS : Samantha, Alex, Thomas, Daniel) | |
| `performance_memory.jsHeapSizeLimit` | 4294705152 | 3760000000 | `headless.js:101-115`, valeur écrite en dur à `:106` | |
| `performance_memory.screenX`, `screenY` | 106, 91 | 0, 0 | `headless.js:124-149` ; valeurs tirées de `canvas_seed` (`headless.js:127-130`, seed `generateur.py:517`) | Le commentaire du code dit « headless : souvent 0,0 ». |
| `fenetre.outerHeight` | 1108 | 720 | `environnement.js:36-37` (`gapH` macOS = 28) et `:42-44` (`outerHeight = innerHeight + gapH`) | 1108 = 1080 + 28. Le témoin a `outer = inner`. L'écart de 28 px est une valeur inventée. |
| `ecran.availHeight` | 1092 | 720 | `environnement.js:14-15` (`barreH` macOS = 25, `availHeight = height - 25`) et `:17-21` | 1092 = 1117 - 25. Le témoin a `availHeight = height`. |
| `connection_dynamic.rtt_1` | 50 | 0 | `environnement.js:154-200` (`rtt` tiré dans `[50,50,50,100,100,150]` via `canvas_seed`, `:160-163`) | Le témoin répond `rtt = 0`. Le tirage dépend du seed ; seule la nature « 0 côté témoin » relève du mode sans interface (hésitation : peut aussi se lire comme choix du profil). |
| `webgl.renderer`, `webgl.vendor` | `ANGLE (Apple, ANGLE Metal Renderer: Apple M5 Pro, Unspecified Version)`, `Google Inc. (Apple)` | `ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (LLVM 10.0.0) (0x0000C0DE)), SwiftShader driver)`, `Google Inc. (Google)` | **Deux origines, les deux** : (1) options de lancement `moteur.py:184-186` (`--use-gl=angle --use-angle=metal --ignore-gpu-blocklist`) qui sortent le Chromium du rendu logiciel SwiftShader ; (2) `webgl.js:155-157` renvoie `profil.gpu_renderer` / `gpu_vendor`. | Le profil est choisi pour correspondre au GPU de la machine (`generateur.py:98-106`, filtre `:502-507`). Sans les options de lancement, le moteur serait en SwiftShader comme le témoin. |

### 1.B Nature : trace de réécriture (25 champs)

| Champ(s) | NOEZIA | Témoin | Origine dans le code | Remarque |
|---|---|---|---|---|
| `navigateur.webdriver` | abs. | `false` | `headless.js:15` (`delete Navigator.prototype.webdriver`) ; option `--disable-blink-features=AutomationControlled` en renfort possible (`moteur.py:180`) | La propriété n'existe plus du tout. Le témoin garde la propriété, à `false`. |
| `headless_signals.webdriver`, `headless_signals.webdriver_getter_natif`, `headless_signals.webdriver_sur_prototype` | abs., abs., `false` | `false`, `true`, `true` | `headless.js:14-23` | Même cause : plus de descripteur sur le prototype. |
| `iframe_test.webdriver_getter_match` | abs. | `true` | `headless.js:14-23` | Le test ne peut pas comparer deux getters qui n'existent plus. |
| `prototype_chain.navigator_own.webdriver.prototype` | `false` | `true` | `headless.js:14-23` | |
| `enumerable_props.nav_webdriver` | abs. | `true` | `headless.js:14-23` | |
| `deep_proxy.wd_desc_match`, `wd_illegal_invoc`, `wd_natif` | abs. ×3 | `true` ×3 | `headless.js:14-23` | Le test « profondeur » saute le champ quand le descripteur manque. |
| `enumerable_props.win_devicePixelRatio` | `true` | abs. | `environnement.js:28-30` (getter créé sur `Window.prototype`) puis `cdp.js:80-101` (le rend énumérable) | Le Chrome du témoin n'a rien sur `Window.prototype` (la propriété est sur l'instance) ; le script en crée une, énumérable. |
| `enumerable_props.win_outerWidth`, `win_outerHeight` | `true` ×2 | abs. ×2 | `environnement.js:46-53` (défini sur `Window.prototype` et sur `window`, `enumerable: true`) | Même cause. |
| `deep_proxy.error_stack_lines` | 5 | 4 | `navigateur.js:16-21` (le getter de `hardwareConcurrency`, `:225-228`, est une fonction JS enveloppée qui lève `TypeError('Illegal invocation')` à la main) | Une ligne de pile en plus. Origine très probable ; non vérifiée en exécutant la page. |
| `performance_memory.memory_propre` | `true` | `false` | `headless.js:111-113` (`Object.defineProperty(performance, 'memory', …)` : propriété propre à l'objet) | Dans le témoin, `memory` vient du prototype. |
| `performance_memory.memory_getter_natif` | `true` | abs. | `headless.js:111-113` | Le témoin n'a pas de getter propre, donc pas de test. |
| `canvas` | `7ab2f1c3e74e2cf4` | `123bb3f2caaeb527` | `canvas.js:62-67` (bruit sur `toDataURL`), seed `canvas_seed` tirée au hasard par profil (`generateur.py:517`) | Hésitation : le GPU change aussi (Metal contre SwiftShader), donc une part de l'écart pourrait exister sans bruit. Non séparé. |
| `audio_context.hash` | 1542660092 | 2136325374 | `audio.js:16-31` (bruit de l'ordre de 1e-7 sur `startRendering`), seed `audio_seed` (`generateur.py:518`) | La somme (`audio_context.sum` = 124.043475) est identique : seul le hash change, c'est donc le bruit. |
| `timing_precision.min_delta`, `precision_samples` | `0.0999999999999659`, `[0.0999999999999659]` | abs., `[]` | `automation.js:128-134` (`performance.now` remplacé et arrondi à 0,1 ms) | Hésitation : le témoin ne voit aucun changement en 20 lectures, NOEZIA en voit un. Le surcoût d'appel du wrapper et l'arrondi expliquent probablement l'écart ; dépend aussi de la vitesse de la boucle. |
| `domrect_fingerprint.rects` | hauteurs et largeurs à virgule (ex. 18.054665859271694 × 134.43133554837772) | entiers ou quasi (18 × 134.421875) | `polices.js:49-81` (`_noiseRect` : bruit déterministe de ±0,075 px sur `getBoundingClientRect`, seed `canvas_seed`, `:60-61`), appelé par le test via `observateur.js:762` | Les écarts mesurés (0,05 px en hauteur, 0,01 px en largeur) sont dans cette plage. Le DPR 2 (`moteur.py:234`) peut y ajouter une part ; non séparé. |
| `webrtc_test.candidats_count`, `candidats_host`, `candidats_avec_ip`, `sdp_host_lines` | 0, 0, 0, 0 | 4, 2, 1, 2 | `environnement.js:56-109` : `iceServers: []` forcé (`:64`), candidats `host` filtrés (`:59-62`, `:76-84`), lignes `host` retirées du SDP (`:87-101`) | Choix de protection (pas de fuite d'IP) mais le résultat, zéro candidat, est une marque. |

### 1.C Nature : choix du profil (18 champs)

| Champ(s) | NOEZIA | Témoin | Origine dans le code | Remarque |
|---|---|---|---|---|
| `ecran.width`, `ecran.height` | 1728, 1117 | 1280, 720 | Tirage `generateur.py:513` dans la liste de la machine (`:105`), écrit par `environnement.js:10-21` | Le témoin prend la taille de fenêtre par défaut de Playwright (1280x720). |
| `ecran.availWidth` | 1728 | 1280 | Idem (`environnement.js:15`, `aw = sw`) | |
| `ecran.devicePixelRatio` | 2 | 1 | `generateur.py:513` ; `moteur.py:234` (`device_scale_factor`) ; `environnement.js:28-30` | |
| `fenetre.innerWidth`, `fenetre.innerHeight` | 1728, 1080 | 1280, 720 | `generateur.py:427-430` (`viewport()` = min(écran, 1920x1080)) ; `moteur.py:226` et `:232` | |
| `fenetre.outerWidth` | 1728 | 1280 | Suit `innerWidth` : `environnement.js:36` (`gapW` macOS = 0) et `:39-41` | Pas d'écart propre au correctif sur macOS ; l'écart vient du viewport. |
| `fuseau.zone`, `languages_test.intl_timezone` | `Europe/Berlin` | `Europe/Paris` | `generateur.py:258` (ligne `de-DE`), tirage `:514` ; `moteur.py:235` (`timezone_id`) | Le témoin garde le fuseau de la machine. |
| `navigateur.language`, `languages_test.language`, `languages_test.intl_locale` | `de-DE` | `en-US` | `generateur.py:258`, `:514` ; `moteur.py:231` (`locale`) ; `navigateur.js:237-250` (réécrit aussi `language`) | |
| `navigateur.languages`, `languages_test.languages` | `["de-DE","de"]` | `["en-US"]` | Idem ; liste construite à `navigateur.js:239-245` | |
| `navigateur.deviceMemory`, `worker_consistency.main_deviceMemory`, `worker_consistency.worker_deviceMemory` | 8 | 32 | `generateur.py:104` (machine M5 Pro : 8), `:540` ; `navigateur.js:230-235` (page) ; `workers.js:27-32` (Worker) | La valeur 8 est écrite dans la table de machines, pas lue sur l'ordinateur. Le témoin donne 32 (valeur de la base). |
| `navigateur.userAgent` | `Mozilla/5.0 (Macintosh; Intel Mac OS X 15_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.6668.100 Safari/537.36` | `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/156.0.8078.4 Safari/537.36` | `generateur.py:398-404` (construction) ; version tirée `:512` (`CHROME_VERSIONS`, `:245-250`) ; OS `:100` et `:511` ; appliqué par `moteur.py:233` | Deux parts : la version 129 et `15_1` sont des choix du profil ; la disparition de `Headless` relève du masque (voir `botd.*`). **Incohérence interne** : le User-Agent annonce Chrome 129 alors que `userAgentData.brands` annonce 156 (vraie version). |

### 1.D Nature : aléa ou horloge (10 champs, à écarter)

| Champ(s) | NOEZIA | Témoin | Origine | Remarque |
|---|---|---|---|---|
| `duree_collecte_ms` | 485 | 437 | Durée de la collecte | |
| `paint_timing.entries`, `first_paint_time`, `first_contentful_paint_time` | 96 | 68 | Chrome mesure lui-même ; `headless.js:151-199` ne fabrique des entrées que si elles manquent, ce qui n'est pas le cas ici (les deux ont FP et FCP) | |
| `raf_timing.deltas` | `[16.7, 16.6, 16.7, 16.7, 16.6]` | `[16.6, 16.6, 16.7, 16.7, 16.7]` | Cadence d'affichage | |
| `timing.date_now`, `timing.perf_timeOrigin` | 1794472029992, 1794472029865.9 | 1794472255101, 1794472254975 | Horloge (passages à 225 s d'écart) | |
| `timing.perf_now` | 126.6 | 126.20000004768372 | Horloge ; l'arrondi à 0,1 de NOEZIA (`automation.js:130-133`) retire la queue de décimales, mais la valeur varie de toute façon | |
| `cdp_detection.heap_ratio` | 0.002 | 0.003 | Rapport `usedJSHeapSize / jsHeapSizeLimit` (`observateur.js:952`) ; la limite forcée à `headless.js:106` y contribue un peu | Valeur de l'ordre du millième : bruit. |
| `connection_dynamic.downlink_1` | 8.65 | 9.5 | `environnement.js:154-200` (tirage par seed puis gigue selon `Date.now()`, `:168-183`) | Change d'une lecture à l'autre. |

## 2. Différences dont l'origine n'est pas établie

Aucun écart n'est resté sans origine probable, mais quatre champs n'ont pas d'origine prouvée à 100 % :

1. **`domrect_fingerprint.rects`** : l'origine principale est établie (`polices.js:49-81`), mais la part due au DPR 2 (`moteur.py:234`) n'est pas séparée du bruit sans mesure du témoin à DPR 2.
2. **`canvas`** : le bruit (`canvas.js`) suffit à expliquer l'écart, mais le passage de SwiftShader à Metal (options `moteur.py:186`) peut aussi changer le rendu. Les deux ne sont pas séparés sans mesure.
3. **`deep_proxy.error_stack_lines`** (5 contre 4) : l'explication par le getter enveloppé (`navigateur.js:16-21`) est la seule trouvée ; pas vérifiée dans le navigateur.
4. **`timing_precision.*`** : le wrapper `performance.now` (`automation.js:128-134`) explique que NOEZIA voie un pas de 0,1 ms et pas le témoin, mais le résultat dépend aussi de la vitesse de la boucle de mesure.

Cherché sans rien trouver de plus : `webgl.js` pour une autre cause de `webgl.vendor`/`renderer` (aucune, mais deux origines cumulées), `iframes.js` et `codecs.js` (aucun champ de la liste ne les concerne), `workers.js` (n'explique que `worker_consistency.*`, déjà couvert par le profil).

## 3. Ce qui disparaîtrait sans aucune réécriture

Si NOEZIA ne réécrivait rien (aucun script, aucun profil), il serait le témoin : les 84 écarts disparaîtraient. Mais le témoin n'est pas un vrai Chrome.

| Nature | Champs | Disparaît sans réécriture | Resterait différent d'un vrai Chrome sans réécriture |
|---|---|---|---|
| masque le mode sans interface | **31** | oui | **oui** : ce sont des champs où le témoin sans interface montre sa différence (plugins 0, pas de `window.chrome`, `Notification` à `denied`, `screenX` 0, voix 0, `rtt` 0, SwiftShader, `HeadlessChrome` dans UA/brands/BotD, `outer = inner`, `availHeight = height`, `jsHeapSizeLimit` 3,76 Go). Avec un Chrome avec interface, ces correctifs deviendraient inutiles. |
| trace de réécriture | **25** | oui | non : ce sont des marques créées par les correctifs eux-mêmes (`webdriver` supprimé, `Window.prototype` enrichi, getters JS, bruit canvas/audio, WebRTC vide). Le témoin n'en a pas ; un vrai Chrome non plus (à confirmer par les sessions humaines). |
| choix du profil | **18** | oui | non en soi, mais ils divergent d'un vrai Chrome tant que le profil ne reprend pas les valeurs réelles de la machine (écran 1728x1117, `deviceMemory` 8 écrit en dur, User-Agent Chrome 129 contre un binaire 156, `de-DE`/`Europe/Berlin` choisis au hasard). |
| aléa ou horloge | **10** | oui | écartés |

Lecture : sur 84 champs, **31** viennent uniquement du fait que le Chromium est sans interface (réponse « résolue » par un vrai Chrome avec interface), **25** sont des marques laissées par la façon de réécrire (le vrai risque de détection propre au moteur), **18** sont des valeurs du profil, **10** sont du bruit. Les 25 traces sont la partie à comparer en priorité avec les sessions humaines quand elles existeront.

Observations hors tableau, à garder en tête : (a) User-Agent Chrome 129 contre `userAgentData` 156 ; (b) `loadTimes.connectionInfo` = `http/1.1` contre `npnNegotiatedProtocol` = `h2`.

---

## 4. Comparaison avec un vrai Chrome (campagne 96, 12/11)

Lecture seule : requêtes SQLite uniquement, aucun navigateur lancé.

### 4.1 Les trois empreintes

| Lettre | Quoi | Source dans la base |
|---|---|---|
| **A** | NOEZIA réécrit | campagne 94, niveau `04scdp`, observation `65292` (session `d4327507…`) |
| **B** | Témoin sans interface | campagne 94, niveau `04scdp`, observation `65392` (session `937f0c9d…`) |
| **C** | Vrai Google Chrome 156 avec interface, rien de réécrit | campagne 96, run 33335 (`noezia`, `identite_native: true`, `channel: "chrome"`, label `noezia-natif`), niveau `01`, observation `71920` |
| C2 | Même Chrome, autre passage | campagne 96, run 33336, niveau `03` (via le frontal TLS), observation `71929` |
| P1, P2 | `patchright` avec interface (label `patchright-chrome-interface`) | runs 33333 (niveau `01`, obs. `71912`) et 33334 (niveau `03`, obs. `71918`) |

Même aplatissement que plus haut : 315 champs, **84 diffèrent entre A et B** (on retrouve bien le même nombre).

**Limites à garder en tête.**
- C vient d'**un seul Chrome, sur une seule machine, piloté par Patchright**. Ce n'est pas encore une session humaine.
- Les niveaux ne sont pas les mêmes : A et B sont au niveau `04scdp`, C au niveau `01` (site servi direct en HTTP/1.1 sur `127.0.0.1:8770`, sans frontal), C2 au niveau `03` (frontal TLS, h2). Les champs de C et C2 sont identiques sauf `loadTimes_connectionInfo`, les durées et les horloges.
- Le fichier `observateur.js` a bougé de 5 lignes entre les deux campagnes (ligne 252 contre 257 pour la même instruction) : les champs de piles d'appel (`integrite.toDataURL_error_stack`, `stack_trace_test.*`) ne se comparent pas et sont exclus.
- C est une fenêtre réelle (`viewport` nul) : écran 1680x1050, fenêtre 1200x825. P1 et P2 ont l'écran émulé 1280x720 de Playwright. Sur tous les autres champs stables, C = C2 = P1 = P2 (voir 4.5).

### 4.2 Résultat sur les 84 champs

| Case | Champs |
|---|---|
| 1. NOEZIA a raison (A = C) | **17** |
| 2. NOEZIA se trahit (A ≠ C) | **35** (dont 28 où le témoin B = C : la réécriture a cassé ce que le témoin avait juste ; 7 où B ≠ C aussi) |
| 3. Dépend de la machine ou du profil | **22** |
| 4. Aléa ou horloge | **10** |
| Total | **84** |

Méthode : les cases 4 et 3 sont des listes fermées, choisies à la main ; ensuite A = C donne la case 1 et le reste la case 2. Trois champs sont en case 2 sans que la règle brute le dise (`loadTimes_connectionInfo` : A = C par coïncidence de niveau ; `fenetre.outerHeight` : l'écart `outer - inner` est faux ; `voices_count`) : voir leurs remarques.

### 4.3 Ce que ni NOEZIA ni le témoin ne reproduisent du vrai Chrome (A = B, C diffère) : 7 champs

Ces écarts n'étaient pas visibles avec le premier document (A et B sont égaux, donc absents des 84).

| Champ | A = B | C (C2 identique) | Remarque |
|---|---|---|---|
| `apis.share` | `false` | `true` | `navigator.share` existe dans le Chrome avec interface sur macOS. |
| `navigateur.pdfViewerEnabled` | `false` | `true` | A annonce 4 plugins PDF mais `pdfViewerEnabled` reste faux : incohérence interne. |
| `font_fingerprint.presentes` | contient `Menlo`, pas `Courier New` | contient `Courier New`, pas `Menlo` | Le test de polices tombe autrement dans le Chrome avec interface. |
| `font_fingerprint.absentes` | contient `Courier New`, pas `Menlo` | contient `Menlo`, pas `Courier New` | Même cause. |
| `font_fingerprint.os_manquantes` | `[]` | `["Menlo"]` | Même cause. À lire avec prudence : une seule machine. |
| `performance_memory.totalJSHeapSize` | `10000000` | `3498829` (C), `4016022` (C2) | Valeur ronde dans A et B ; P1 donne `16630204`, donc la valeur varie beaucoup d'un passage à l'autre. |
| `performance_memory.usedJSHeapSize` | `10000000` | `2468225` (C), `1281430` (C2) | Idem. |

Écartés : `raf_timing.mean_delta` (horloge) et les trois champs de piles (voir limites).

### 4.4 Les 84 champs, un par un

Les valeurs longues sont coupées. Identifiants : A 65292, B 65392, C 71920 (C2 71929 pour les champs qui varient selon le niveau).

#### Case 1. NOEZIA a raison (A = C) : 17 champs

| Champ | A (NOEZIA) | B (témoin) | C (vrai Chrome) | Remarque |
|---|---|---|---|---|
| `apis.chrome` | `true` | `false` | `true` |  |
| `botd.bot` | `false` | `true` | `false` |  |
| `botd.botKind` | abs. | `headless_chrome` | abs. |  |
| `chrome_apis.chrome_app` | `true` | `false` | `true` |  |
| `chrome_apis.chrome_app_getDetails` | `true` | abs. | `true` |  |
| `chrome_apis.chrome_app_isInstalled` | `false` | abs. | `false` |  |
| `chrome_apis.chrome_app_runningState` | `true` | abs. | `true` |  |
| `chrome_apis.chrome_csi` | `true` | `false` | `true` |  |
| `chrome_apis.chrome_loadTimes` | `true` | `false` | `true` |  |
| `chrome_apis.csi_keys` | `["onloadT", "pageT", "startE", "tran"]` | abs. | `["onloadT", "pageT", "startE", "tran"]` |  |
| `chrome_apis.csi_pageT_positif` | `true` | abs. | `true` |  |
| `chrome_apis.loadTimes_keys` | `["commitLoadTime", "connectionInfo", "finishDocumentLoadTime…` | abs. | `["commitLoadTime", "connectionInfo", "finishDocumentLoadTime…` |  |
| `chrome_apis.loadTimes_requestTime_positif` | `true` | abs. | `true` |  |
| `navigateur.userAgentData.brands` | `[{"brand": "Not:A-Brand", "version": "8"}, {"brand": "Chromi…` | `[{"brand": "Not:A-Brand", "version": "8"}, {"brand": "Chromi…` | `[{"brand": "Not:A-Brand", "version": "8"}, {"brand": "Chromi…` |  |
| `permissions.notification` | `default` | `denied` | `default` |  |
| `webgl.renderer` | `ANGLE (Apple, ANGLE Metal Renderer: Apple M5 Pro, Unspecifie…` | `ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (LLVM 10.0.0…` | `ANGLE (Apple, ANGLE Metal Renderer: Apple M5 Pro, Unspecifie…` |  |
| `webgl.vendor` | `Google Inc. (Apple)` | `Google Inc. (Google)` | `Google Inc. (Apple)` |  |

#### Case 2. NOEZIA se trahit (A ≠ C) : 35 champs

| Champ | A (NOEZIA) | B (témoin) | C (vrai Chrome) | Remarque |
|---|---|---|---|---|
| `audio_context.hash` | `1542660092` | `2136325374` | `2136325374` | B = C : le vrai Chrome donne la valeur sans bruit. Le bruit d'A est une trace. |
| `canvas` | `7ab2f1c3e74e2cf4` | `123bb3f2caaeb527` | `cda43037e1ecda0f` | A et C annoncent le même GPU (Apple M5 Pro, Metal) : sans bruit, A aurait donné la valeur de C. Le bruit change donc le hachage. |
| `chrome_apis.chrome_runtime` | `true` | `false` | `false` |  |
| `chrome_apis.loadTimes_connectionInfo` | `http/1.1` | abs. | `http/1.1` | A dit `http/1.1` alors que sa page est servie en h2 par le frontal (observations_http 375559, `http_version` 2). Le vrai Chrome passé par le même frontal (C2, niveau 03) dit `h2`. Le `http/1.1` de C vient du niveau 01, servi direct en HTTP/1.1 : A = C par coïncidence. |
| `chrome_apis.runtime_PlatformOs` | `true` | abs. | abs. |  |
| `chrome_apis.runtime_connect` | `true` | abs. | abs. |  |
| `chrome_apis.runtime_sendMessage` | `true` | abs. | abs. |  |
| `deep_proxy.error_stack_lines` | `5` | `4` | `4` | 4 lignes dans le vrai Chrome comme dans le témoin ; A en a 5. |
| `deep_proxy.wd_desc_match` | abs. | `true` | `true` |  |
| `deep_proxy.wd_illegal_invoc` | abs. | `true` | `true` |  |
| `deep_proxy.wd_natif` | abs. | `true` | `true` |  |
| `domrect_fingerprint.rects` | `[{"font": "16px monospace", "height": 18.054665859271694, "w…` | `[{"font": "16px monospace", "height": 18, "width": 134.42187…` | `[{"font": "16px monospace", "height": 19, "width": 134.85937…` | A : décimales longues (ex. 18.0546…). C et le témoin : entiers ou fractions binaires (19, 134.859375). Le bruit d'A n'existe dans aucun Chrome observé. |
| `enumerable_props.nav_webdriver` | abs. | `true` | `true` |  |
| `enumerable_props.win_devicePixelRatio` | `true` | abs. | abs. |  |
| `enumerable_props.win_outerHeight` | `true` | abs. | abs. |  |
| `enumerable_props.win_outerWidth` | `true` | abs. | abs. |  |
| `fenetre.outerHeight` | `1108` | `720` | `912` | Le champ dépend de l'écran, mais l'écart `outer - inner` est la barre du navigateur : A 28 px (inventé), C 87 px (912-825), Patchright avec interface 80 px (800-720). 28 n'est pas une valeur d'un Chrome avec interface. |
| `headless_signals.voices_count` | `4` | `0` | `0` | A fabrique 4 voix ; le vrai Chrome en rend 0 à ce moment de la collecte. Sans doute lecture synchrone avant le chargement des voix, non vérifié. |
| `headless_signals.webdriver` | abs. | `false` | `false` |  |
| `headless_signals.webdriver_getter_natif` | abs. | `true` | `true` |  |
| `headless_signals.webdriver_sur_prototype` | `false` | `true` | `true` |  |
| `iframe_test.webdriver_getter_match` | abs. | `true` | `true` |  |
| `navigateur.mimeTypes` | `4` | `0` | `2` | Voir `navigateur.plugins`. |
| `navigateur.plugins` | `4` | `0` | `5` | Vrai Chrome : 5 plugins, 2 types MIME, `pdfViewerEnabled` vrai. A : 4 et 4, et `pdfViewerEnabled` faux (voir section 4). |
| `navigateur.userAgent` | `Mozilla/5.0 (Macintosh; Intel Mac OS X 15_1) AppleWebKit/537…` | `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/…` | `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/…` | C : Chrome/156.0.0.0 (version réduite du vrai Chrome), `10_15_7`. A : Chrome/129.0.6668.100, `15_1`. Les en-têtes d'A annoncent aussi 129 (HTTP) alors que `userAgentData.brands` annonce 156 (JS). |
| `navigateur.webdriver` | abs. | `false` | `false` |  |
| `performance_memory.memory_getter_natif` | `true` | abs. | abs. |  |
| `performance_memory.memory_propre` | `true` | `false` | `false` |  |
| `prototype_chain.navigator_own.webdriver.prototype` | `false` | `true` | `true` |  |
| `timing_precision.min_delta` | `0.0999999999999659` | abs. | abs. | Le vrai Chrome ne montre aucun pas mesurable (abs.), comme le témoin. A en montre un de 0,1 ms. |
| `timing_precision.precision_samples` | `[0.0999999999999659]` | `[]` | `[]` | Voir `min_delta`. |
| `webrtc_test.candidats_avec_ip` | `0` | `1` | `1` |  |
| `webrtc_test.candidats_count` | `0` | `4` | `4` | Le vrai Chrome (comme le témoin) montre des candidats `host` ; A n'en montre aucun. |
| `webrtc_test.candidats_host` | `0` | `2` | `2` |  |
| `webrtc_test.sdp_host_lines` | `0` | `2` | `2` |  |

#### Case 3. Dépend de la machine ou du profil : 22 champs

| Champ | A (NOEZIA) | B (témoin) | C (vrai Chrome) | Remarque |
|---|---|---|---|---|
| `connection_dynamic.rtt_1` | `50` | `0` | `0` | C et le témoin donnent 0 sur ce site local. A donne 50, tiré au hasard. Un vrai Chrome sur un vrai réseau donne en général une valeur non nulle, non mesuré ici. |
| `ecran.availHeight` | `1092` | `720` | `956` | A : hauteur - 25. C : 1050 - 956 = 94 (barre de menus plus Dock). L'écart dépend du Dock de l'utilisateur. |
| `ecran.availWidth` | `1728` | `1280` | `1680` |  |
| `ecran.devicePixelRatio` | `2` | `1` | `1` | C = 1 (écran externe 1680x1050). A = 2 (type portable Retina) : plausible. |
| `ecran.height` | `1117` | `720` | `1050` |  |
| `ecran.width` | `1728` | `1280` | `1680` |  |
| `fenetre.innerHeight` | `1080` | `720` | `825` |  |
| `fenetre.innerWidth` | `1728` | `1280` | `1200` |  |
| `fenetre.outerWidth` | `1728` | `1280` | `1200` |  |
| `fuseau.zone` | `Europe/Berlin` | `Europe/Paris` | `Europe/Paris` |  |
| `languages_test.intl_locale` | `de-DE` | `en-US` | `fr` | C : `intl_locale` = `fr` alors que `language` = `fr-FR`. A : `de-DE` des deux côtés. Un vrai Chrome en `de-DE` donnerait peut-être `de` : non vérifié. |
| `languages_test.intl_timezone` | `Europe/Berlin` | `Europe/Paris` | `Europe/Paris` |  |
| `languages_test.language` | `de-DE` | `en-US` | `fr-FR` |  |
| `languages_test.languages` | `["de-DE", "de"]` | `["en-US"]` | `["fr-FR", "fr", "en-US", "en"]` |  |
| `navigateur.deviceMemory` | `8` | `32` | `32` | C = 32 (la vraie machine, 64 Go). A = 8, écrit dans la table de machines : plausible pour une autre machine. |
| `navigateur.language` | `de-DE` | `en-US` | `fr-FR` |  |
| `navigateur.languages` | `["de-DE", "de"]` | `["en-US"]` | `["fr-FR", "fr", "en-US", "en"]` |  |
| `performance_memory.jsHeapSizeLimit` | `4294705152` | `3760000000` | `4395630592` | A : valeur écrite en dur. C = Patchright avec interface = 4395630592 sur cette machine. La limite dépend de la mémoire ; valeur d'A non vérifiable ailleurs. |
| `performance_memory.screenX` | `106` | `0` | `22` | Position de la fenêtre : dépend de l'utilisateur. A (106, 91) et C (22, 52) sont deux positions plausibles ; seul le témoin (0, 0) est suspect. |
| `performance_memory.screenY` | `91` | `0` | `52` | Voir `screenX`. |
| `worker_consistency.main_deviceMemory` | `8` | `32` | `32` |  |
| `worker_consistency.worker_deviceMemory` | `8` | `32` | `32` |  |

#### Case 4. Aléa ou horloge (écartés) : 10 champs

| Champ | A (NOEZIA) | B (témoin) | C (vrai Chrome) | Remarque |
|---|---|---|---|---|
| `cdp_detection.heap_ratio` | `0.002` | `0.003` | `0` |  |
| `connection_dynamic.downlink_1` | `8.65` | `9.5` | `1.45` |  |
| `duree_collecte_ms` | `485` | `437` | `707` |  |
| `paint_timing.entries` | `[{"name": "first-paint", "startTime": 96}, {"name": "first-c…` | `[{"name": "first-paint", "startTime": 68}, {"name": "first-c…` | `[{"name": "first-paint", "startTime": 64}, {"name": "first-c…` |  |
| `paint_timing.first_contentful_paint_time` | `96` | `68` | `64` |  |
| `paint_timing.first_paint_time` | `96` | `68` | `64` |  |
| `raf_timing.deltas` | `[16.7, 16.6, 16.7, 16.7, 16.6]` | `[16.6, 16.6, 16.7, 16.7, 16.7]` | `[16.7, 16.7, 16.7, 16.7, 16]` |  |
| `timing.date_now` | `1794472029992` | `1794472255101` | `1794486785644` |  |
| `timing.perf_now` | `126.6` | `126.20000004768372` | `55` |  |
| `timing.perf_timeOrigin` | `1794472029865.9` | `1794472254975` | `1794486785589.7` |  |

### 4.5 C contre Patchright avec interface (P1, P2)

Les deux donnent les mêmes valeurs sur tous les champs qui ne dépendent pas du hasard, sauf ceux liés à la taille de la fenêtre et de l'écran :
- `ecran.width/height/availWidth/availHeight` : C 1680, 1050, 1680, 956 ; P 1280, 720, 1280, 720 (écran émulé par Playwright).
- `fenetre.innerWidth/innerHeight/outerWidth/outerHeight` : C 1200, 825, 1200, 912 ; P 1280, 720, 1282, 800.
- `performance_memory.totalJSHeapSize/usedJSHeapSize` : valeurs différentes (mesures de mémoire, aléatoires).
- Horloges, `raf_timing`, `paint_timing`, `cdp_detection.heap_ratio` (C : 0, P : 0,003), `connection_dynamic.downlink_1`, `duree_collecte_ms`.

Tout le reste est identique : agent utilisateur `Chrome/156.0.0.0`, marques `Google Chrome 156`, `plugins` 5, `mimeTypes` 2, `webdriver` faux, `chrome.runtime` absent, WebGL Apple M5 Pro Metal, canvas `cda43037e1ecda0f`, hachage audio `2136325374`, langues `fr-FR`, fuseau `Europe/Paris`, `deviceMemory` 32, WebRTC 4 candidats.
Conséquence : le mode « identité native » de NOEZIA ne rajoute rien que Patchright n'ait pas ; C est bien « Chrome tel qu'il est ».

### 4.6 En-têtes HTTP d'une requête de page

Sources (`observations_http`, requête de page, `GET`) : A 375559 (`/lab/dynamique`, h2 via frontal), B 375894 (idem), C 453808 (`/lab/catalogue`, HTTP/1.1 direct), C2 453837 (`/lab/catalogue`, h2 via frontal, comparable à A et B), P1 453756, P2 453782. Les pages ne sont pas les mêmes (`dynamique` pour A et B, `catalogue` pour C), ce qui ne change pas les en-têtes de navigation.

| En-tête | A (NOEZIA) | B (témoin) | C2 (vrai Chrome, h2) | C (vrai Chrome, HTTP/1.1) |
|---|---|---|---|---|
| `user-agent` | `Chrome/129.0.6668.100`, `Mac OS X 15_1` | `HeadlessChrome/156.0.8078.4`, `10_15_7` | `Chrome/156.0.0.0`, `10_15_7` | idem C2 |
| `sec-ch-ua` | `"Not:A-Brand";v="8", "Chromium";v="129", "Google Chrome";v="129"` | `…"Chromium";v="156", "HeadlessChrome";v="156"` | `…"Chromium";v="156", "Google Chrome";v="156"` | idem C2 |
| `sec-ch-ua-mobile`, `-platform` | `?0`, `"macOS"` | `?0`, `"macOS"` | `?0`, `"macOS"` | idem |
| autres `sec-ch-ua-*` | **présents** : `-arch` `"arm"`, `-bitness` `"64"`, `-full-version-list` (129.0.6668.100), `-model` `""` | absents | absents | absents |
| `accept-language` | `de-DE` (sans `q`, sans `de`) | **absent** | `fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7` | idem C2 |
| `accept` | `text/html,application/xhtml+xml,application/xml;q=0.9,image/jxl,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7` | idem | idem | idem |
| `accept-encoding` | `gzip, deflate, br, zstd` | idem | idem | idem |
| `sec-fetch-site/mode/user/dest` | `none`, `navigate`, `?1`, `document` | idem | idem | idem |
| `upgrade-insecure-requests` | `1` | `1` | `1` | `1` |
| `priority` | `u=0, i` | `u=0, i` | `u=0, i` | absent (HTTP/1.1) |
| `connection` | absent (h2) | absent | absent | `keep-alive` |

**Ordre des en-têtes** (noms, tels que stockés) :
- **A** : `host, pragma, cache-control, accept, upgrade-insecure-requests, user-agent, accept-language, sec-ch-ua, sec-ch-ua-arch, sec-ch-ua-bitness, sec-ch-ua-full-version-list, sec-ch-ua-mobile, sec-ch-ua-model, sec-ch-ua-platform, sec-fetch-site, sec-fetch-mode, sec-fetch-user, sec-fetch-dest, accept-encoding, priority`
- **B** : `host, pragma, cache-control, sec-ch-ua, sec-ch-ua-mobile, sec-ch-ua-platform, upgrade-insecure-requests, user-agent, accept, sec-fetch-site, sec-fetch-mode, sec-fetch-user, sec-fetch-dest, accept-encoding, priority`
- **C2** : `host, pragma, cache-control, sec-ch-ua, sec-ch-ua-mobile, sec-ch-ua-platform, upgrade-insecure-requests, user-agent, accept, sec-fetch-site, sec-fetch-mode, sec-fetch-user, sec-fetch-dest, accept-encoding, accept-language, priority`
- **C** : comme C2, avec `connection` en 2e position et sans `priority`. P1 et P2 donnent exactement les mêmes listes que C et C2.

Constat :
1. **L'ordre d'A n'est celui d'aucun Chrome observé.** B, C, C2 : `sec-ch-ua*` avant `upgrade-insecure-requests`, `accept` après `user-agent`, `accept-language` entre `accept-encoding` et `priority`. A : `accept` avant `upgrade-insecure-requests`, `accept-language` juste après `user-agent`, `sec-ch-ua*` après. Les en-têtes d'A semblent réécrits en bloc (hypothèse, le code n'a pas été relu pour cette section).
2. **`sec-ch-ua` annonce 129 en HTTP et 156 en JavaScript** (`userAgentData.brands`, case 1) : deux versions pour le même navigateur.
3. **Quatre en-têtes `sec-ch-ua-*` à haute entropie envoyés sans qu'on les demande** (`arch`, `bitness`, `full-version-list`, `model`). Le vrai Chrome (C, C2, P1, P2) n'envoie que `sec-ch-ua`, `-mobile`, `-platform` sur une première navigation. Je n'ai pas vérifié si le site demandait ces en-têtes (`Accept-CH`) : non vérifié.
4. **`accept-language: de-DE` seul** alors que `navigator.languages` = `["de-DE","de"]`. Le vrai Chrome envoie la liste avec poids (`fr-FR,fr;q=0.9,…`) : on attendrait `de-DE,de;q=0.9`.
5. Le témoin B n'envoie **aucun `accept-language`** et annonce `HeadlessChrome` : A corrige ce second point, mais mal pour le premier.
6. `accept`, `accept-encoding`, `sec-fetch-*`, `upgrade-insecure-requests` et `priority` sont identiques partout : aucun écart.

### 4.7 Ce qui reste incertain

- **Une machine, un Chrome, un pilote** : C est un Chrome 156 sur un Mac mini, écran externe 1680x1050, langue `fr-FR`, piloté par Patchright. Les 22 champs de la case 3 ne sont jugés que par plausibilité, pas par une mesure sur d'autres machines.
- **Niveaux différents** : A/B au niveau `04scdp`, C/C2 aux niveaux `01`/`03`. Rien dans les 84 champs ne semble dépendre du niveau, sauf `loadTimes_connectionInfo` (protocole), mais je n'ai pas de Chrome au niveau `04scdp`.
- **`voices_count`** (0 dans C) : peut être un artefact de la lecture synchrone ; à confirmer sur une session humaine.
- **`intl_locale`** : voir la remarque du tableau ; la valeur qu'aurait un vrai Chrome en `de-DE` n'est pas mesurée.
- **`rtt_1` et `jsHeapSizeLimit`** : valeurs de C obtenues sur un site local ; elles pourraient différer sur un vrai réseau et avec une autre mémoire.
- **Polices** : le test donne `Menlo` absent et `Courier New` présent dans le Chrome avec interface ; cause (police `monospace` par défaut) non vérifiée.
- **Heap JS** : les valeurs varient beaucoup entre C, C2, P1, P2 ; seule la valeur ronde `10000000` d'A et B est notable.
- **Pas une session humaine** : les champs de comportement (souris, frappe), le TLS réel et les en-têtes sur plusieurs pages n'ont pas été comparés ici.
