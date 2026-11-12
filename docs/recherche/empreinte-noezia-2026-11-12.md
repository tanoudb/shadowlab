# Origine des différences d'empreinte NOEZIA / témoin Patchright

- **Date** : 12/11/2026
- **Base** : `outputs/shadowlab.sqlite3`, campagne 94, niveau `04scdp`, première empreinte (`observations_js`, `kind = 'empreinte'`).
- **Observations utilisées** : `65292` (noezia) et `65392` (patchright, le témoin).
- **Lecture seule** : aucun test ni navigateur lancé, aucun fichier existant modifié.
- **Limite importante** : la référence « vrai Chrome » manque encore. Elle viendra des sessions humaines
  (`shadowlab rejeu`, aucune session humaine en base au 12/11). Ce document dit d'où vient chaque écart
  avec le témoin, pas ce qu'un vrai Chrome aurait donné.

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
