# Chrome avec interface sur un serveur Linux sans écran

Recherche documentaire du 12/11/2026. Web uniquement : rien n'a été installé ni testé.
Légende : **[doc]** = documentation officielle de l'éditeur de l'outil ; **[vendeur]** = article d'un éditeur anti-bot ;
**[blog]** = blog ou site tiers (avis, pas un fait établi) ; **non confirmé** = aucune source trouvée.

## Résumé (10 lignes)
1. Faisable : un Chrome avec interface tourne sur un serveur sans écran grâce à un écran virtuel (Xvfb, `xvfb-run`). C'est ce que dit la doc Playwright. [doc]
2. Patchright recommande `channel="chrome"`, `headless=False`, `no_viewport=True`, sans User-Agent ni en-têtes imposés. Sa doc ne parle pas de Xvfb. [doc]
3. Le Chrome « headless » moderne et le Chrome avec interface partagent le même code depuis Chrome 112. L'ancien mode n'existe plus que dans `chrome-headless-shell` (depuis Chrome 132). [doc]
4. Reste visible : la carte graphique logicielle (SwiftShader/llvmpipe), l'écran par défaut de Xvfb (1280x1024), des polices rares, aucune voix de synthèse, un fuseau et une langue de serveur, l'IP de datacenter. [doc + vendeur + blog]
5. Évitable en grande partie : écran à la taille d'un vrai poste, polices du système visé, `TZ`/`LANG` cohérents, GPU réel (NVIDIA + pilotes) ou au moins llvmpipe plutôt que SwiftShader. Le GPU réel dans un conteneur est le point le moins documenté.
6. Les éditeurs disent croiser plusieurs signaux (cohérence, protocole CDP, comportement) ; aucun ne dit qu'un écran virtuel suffit seul à bloquer. Voir point 4.
7. Limites : `/dev/shm` (Docker) et bac à sable, RAM par navigateur, aucune mesure sérieuse de densité trouvée. Chiffres de blogs : 150 à 300 Mo par instance, non vérifiés.
8. Le User-Agent du mode « new headless » (présence de `HeadlessChrome` ou non) : **non confirmé** par une source officielle. Les sources se contredisent.
9. À mesurer soi-même : User-Agent et `sec-ch-ua` réels du Chrome installé, `WEBGL_debug_renderer_info`, `screen.*`, polices, `speechSynthesis.getVoices()`, `Intl`, mémoire par navigateur.
10. Aucune source ne chiffre la part de chaque signal dans une décision anti-bot ; ce sont des listes d'indices.

## 1. Donner un écran à Chrome sur un serveur sans écran

### Ce que disent Playwright et Patchright
- Playwright, page CI : l'exécution avec interface sur Linux « requiert Xvfb » ; on préfixe la commande par `xvfb-run` (exemple `xvfb-run npx playwright test`). L'image Docker officielle et l'action GitHub contiennent déjà Xvfb. [doc] https://playwright.dev/docs/ci
- Playwright, page Docker : `--init` (évite les processus zombies, PID 1) et `--ipc=host` (« sans lui, Chromium peut manquer de mémoire et planter »). `--cap-add=SYS_ADMIN` seulement en développement local. L'image tourne en root, ce qui désactive le bac à sable Chromium ; pour des sites non fiables (scraping), la doc recommande `--user pwuser` et un profil seccomp fourni. [doc] https://playwright.dev/docs/docker
- La même page parle d'un visualiseur noVNC (fonction `desktop-lite` d'un devcontainer, port 6080) pour voir le navigateur. Xvfb n'y est pas cité. [doc] https://playwright.dev/docs/docker
- Playwright, page navigateurs : `playwright install --with-deps` installe le navigateur et ses dépendances système. Le canal `chrome` ne s'installe pas par défaut. La page ne dit rien des architectures Linux prises en charge. [doc] https://playwright.dev/docs/browsers
- Patchright (Python), README : section « Best Practice - use Chrome without Fingerprint Injection » : `launch_persistent_context(user_data_dir=..., channel="chrome", headless=False, no_viewport=True)` et « do NOT add custom browser headers or user_agent ». Installation : `patchright install chrome`. Le README ne mentionne ni Linux ni Xvfb. [doc] https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python
- Message d'erreur Playwright sans serveur X : « Looks like you launched a headed browser without having a XServer running. Set either 'headless: true' or use 'xvfb-run <your-playwright-app>' ». Cité par un blog secondaire, **non vérifié à la source**. [blog] https://oddbird.net/2022/11/30/headed-playwright-in-docker

### Les options
| Option | Ce que disent les sources | Statut |
|---|---|---|
| **Xvfb / `xvfb-run`** | Voie recommandée par Playwright. Écran par défaut de `xvfb-run` : `-screen 0 1280x1024x24`. On le change avec `-s "-screen 0 1920x1080x24"` ; `-a` choisit un numéro libre. [doc Debian] https://manpages.debian.org/trixie/xvfb/xvfb-run.1.en.html | confirmé |
| `xvfb-run` en PID 1 | Il se bloque (il ne reçoit jamais le signal de disponibilité du serveur X). Contournement : `--init` ou un `sh -c`. [doc Docker Hardened Images, via un site tiers] https://hub.docker.com/hardened-images/catalog/dhi/playwright/guides | confirmé par un relais, source directe non lue |
| **Wayland sans écran** | Le harnais de test de Chromium utilise Weston avec Ozone/Wayland, Xvfb désactivé, pour tourner en environnement purement headless. Weston a un backend « headless ». [source Chromium] https://chromium.googlesource.com/chromium/src/+/HEAD/testing/xvfb.py ; un projet communautaire ajoute `--ozone-platform=wayland` à Chrome. [blog] https://awesome.ecosyste.ms/projects/github.com%2Fsocrateslee%2Fxvfb-chrome | Aucune recette Playwright/Patchright trouvée. Fonctionnement de Chrome avec interface sur Weston headless pour du scraping : **non confirmé** |
| **VNC / noVNC** | Sert à regarder le navigateur, pas à lui fournir un écran ; il faut déjà un serveur X (le devcontainer Playwright en lance un via `desktop-lite`). [doc] https://playwright.dev/docs/docker | confirmé pour l'usage « visualiser » |

### Paquets et réglages
- **Mémoire partagée.** Docker donne 64 Mo à `/dev/shm` par défaut (chiffre cité par des blogs ; la doc Playwright ne cite pas `/dev/shm`, elle recommande `--ipc=host`). Autres remèdes cités : `--shm-size=2g`, ou `--disable-dev-shm-usage` qui écrit dans `/tmp` (plus lent, selon un blog). [blog] https://www.browserless.io/blog/run-puppeteer-in-docker ; https://github.com/puppeteer/puppeteer/blob/v1.12.1/docs/troubleshooting.md
- **Bac à sable.** Playwright : root = pas de bac à sable ; mieux vaut un utilisateur normal + profil seccomp. `--no-sandbox` est la solution de contournement courante en Docker mais réduit l'isolement. [doc] https://playwright.dev/docs/docker ; [blog] Puppeteer troubleshooting ci-dessus.
- **Polices.** La doc Playwright (CI et Docker) n'en parle pas. Voir point 3.
- **D-Bus.** Aucune source trouvée dans cette recherche (ni recommandation, ni erreur type) : **non confirmé**.
- **Dépendances système.** `npx playwright install --with-deps` ou `install-deps`. [doc] https://playwright.dev/docs/browsers
- Pour exécuter un Chrome Google (`channel="chrome"`), il faut installer ce paquet (`patchright install chrome`). Prise en charge Linux x86_64 du canal `chrome` : la doc consultée ne la détaille pas ; **non confirmé** par source directe.

## 2. `--headless=new`, headless shell, Chrome avec interface sur écran virtuel

**Versions (confirmées) [doc Chrome]**
- Chrome 112 (début 2023) : nouveau mode `--headless=new`, qui partage le code de Chrome. « Headless crée des fenêtres de plateforme mais ne les affiche pas ; toutes les autres fonctions sont disponibles sans limites ». https://developer.chrome.com/docs/chromium/new-headless
- L'ancien mode est publié à part sous le nom `chrome-headless-shell` (2023).
- Chrome 132 (132.0.6793.0) : l'ancien mode est retiré du binaire Chrome ; `--headless=old` affiche une erreur. Annonce du 23/10/2024. https://developer.chrome.com/blog/removing-headless-old-from-chrome
- Puppeteer : `headless: true` = nouveau mode, `'shell'` = ancien, `false` = avec interface. [doc] page new-headless ci-dessus.
- Playwright : par défaut, les exécutions headless utilisent un `chromium-headless-shell` distinct ; `channel: 'chromium'` ou les canaux Chrome/Edge utilisent le nouveau mode, « plus proche du mode avec interface ». [doc] https://playwright.dev/docs/browsers

**Ce que chacun annonce**
| Mode | User-Agent | `sec-ch-ua` | Statut |
|---|---|---|---|
| Ancien headless shell | Contient `HeadlessChrome` (jeton connu des détecteurs). [blog Castle, 13/03/2025] https://blog.castle.io/how-to-detect-headless-chrome-bots-instrumented-with-puppeteer-2/ | Marque `HeadlessChrome` signalée avec un paquet Chromium sans interface (forum Apify, environ 2024). [blog] https://discord.apify.com/m/1296473256156467301 | confirmé par blogs, pas par doc Chrome |
| `--headless=new` | **Non confirmé.** La doc Chrome ne parle pas du User-Agent. Un mainteneur SeleniumBase écrit (24/09/2024) que le nouveau mode met « headless » dans le User-Agent, et l'a corrigé dans sa version 4.31.1. [blog/issue] https://github.com/seleniumbase/SeleniumBase/issues/3162 Un autre site dit « UA Chrome normal sauf réduction ou surcharge ». Les sources se contredisent ; dépend de la version et du lanceur. | **Non confirmé.** Chromium contient un test avec la marque `HeadlessChrome` dans `userAgentData.brands`, donc ce chemin existe encore dans le code. [source Chromium] https://chromium.googlesource.com/chromium/src/+/901b499ceed663f237665ce1fdf0f84f99816d6f/headless/test/headless_browser_user_agent_metadata_browsertest.cc | à mesurer |
| Chrome avec interface sur Xvfb | Pas de jeton `HeadlessChrome` : c'est le mode normal. Aucune source officielle ne le dit en toutes lettres ; c'est la conséquence du fait qu'il n'est pas « headless ». | idem | déduction, à mesurer |

Conséquence pratique : le plus sûr est de **relever soi-même** `navigator.userAgent`, `navigator.userAgentData` et les en-têtes `sec-ch-ua*` du Chrome installé, dans chaque mode. Une surcharge du User-Agent par ligne de commande peut ne pas créer les Client Hints correspondants (avis d'un blog, https://www.itechguides.com/?p=873981). C'est la raison pour laquelle Patchright dit de ne rien imposer. [doc Patchright]

Sur la proximité : DataDome écrit (13/06/2024, mis à jour 14/04/2026) que le nouveau Headless Chrome et Chrome « ont presque exactement la même empreinte de navigateur » ; la détection se déplace vers le protocole CDP. [vendeur] https://securityboulevard.com/2024/06/how-new-headless-chrome-the-cdp-signal-are-impacting-bot-detection

## 3. Traces d'un écran virtuel dans l'empreinte

| Trace | Ce que disent les sources | Évitable ? |
|---|---|---|
| **WebGL (SwiftShader / llvmpipe)** | Le rendu logiciel « Google SwiftShader » est cité comme indice d'automatisation ou de datacenter ; la valeur vient du pilote, donc difficile à imiter par JavaScript, et ne changer que la chaîne crée des contradictions avec les autres paramètres WebGL (Scrappey, 15/06/2026). [blog] https://scrappey.com/qa/anti-bot/what-is-the-swiftshader-renderer-tell Un serveur sous Xvfb avec Mesa llvmpipe peut être un montage légitime : llvmpipe seul est un indice plus faible (Microlink). [blog] https://microlink.io/blog/webgl-without-a-gpu | Oui, en partie. (a) Chrome a annoncé retirer le repli automatique vers SwiftShader : intention du 13/02/2025, cible Chrome 137, avertissement depuis Chrome 130 ; réactivable avec `--enable-unsafe-swiftshader`. Statut final et version réelle : **non confirmés**. [source Chromium] https://groups.google.com/a/chromium.org/g/blink-dev/c/yhFguWS_3pM (b) Mesa llvmpipe via `--use-angle=gl` (sans `--disable-gpu`) donne un rendu CPU 2 à 4 fois plus rapide que SwiftShader, mais reste « software ». [blog Microlink] (c) GPU réel : serveur avec NVIDIA, pilotes compatibles, `--use-angle=vulkan` ou `--use-gl=egl` signalés comme fonctionnels ; un utilisateur Docker a quand même obtenu SwiftShader malgré une carte NVIDIA. [doc/forum] https://chromium.googlesource.com/chromium/src.git/+/lkgr/docs/gpu/using-gpu-hardware-in-headless-chrome.md ; https://forums.docker.com/t/hardware-acceleration-for-headless-chrome-with-nvidia-gpu/132557 La chaîne obtenue serait celle d'une carte de serveur (par exemple « NVIDIA … »), pas d'une carte grand public : cohérence avec le profil visé **non confirmée** |
| **Taille et profondeur d'écran** | Défaut Xvfb : 1280x1024x24. [doc Debian] Une liste publique de tests de détection cite `devicePixelRatio` et les dimensions de fenêtre. [blog] https://www.github.com/azerpas/detect-headless Castle/cside : l'écran et la fenêtre doivent être cohérents avec la classe d'appareil annoncée (cside, juillet 2026). [vendeur] https://cside.com/blog/detect-ai-agents-stealth-browsers | Oui : `-s "-screen 0 WxHx24"` avec une taille courante de poste ; `no_viewport=True` (Patchright) laisse la fenêtre suivre l'écran. Quelle taille est « courante » : **non confirmé** par source |
| **Polices installées** | « Un serveur avec peu de polices se remarque tout de suite » (databay, blog). https://databay.com/blog/how-sites-detect-headless-browsers Les polices doivent correspondre à l'OS annoncé (cside). Un test pydoll : un profil Windows sur Mac est bloqué même avec interface, l'OS fuit par les polices. [blog] https://pydoll.tech/docs/deep-dive/fingerprinting/browser-fingerprinting/ | Oui sur Linux : installer un jeu de polices courant (liste précise : **non confirmée** par source ; ni Playwright ni Patchright n'en parlent). Se faire passer pour Windows/macOS depuis Linux : reste visible |
| **Audio / vidéo (`mediaDevices`)** | Une bibliothèque liste WebRTC/MediaDevices comme contrôle de présence. [blog] https://www.github.com/azerpas/detect-headless Aucune source sur « liste vide » comme indice : **non confirmé** | À mesurer ; périphériques virtuels (loopback) : aucune source trouvée |
| **Voix de synthèse** | `getVoices()` vide ou jamais rempli, « courant sur Linux sans moteur vocal », est l'indice ; les voix révèlent l'OS (Scrappey, 31/05/2026). [blog] https://scrappey.com/qa/anti-bot/what-is-speech-synthesis-fingerprinting La page ne cite pas de paquet (speech-dispatcher, espeak) pour y remédier. | Sur Linux : probablement installer un moteur vocal, mais **non confirmé** par source ; mêmes limites qu'au point « polices » (voix du faux OS impossibles) |
| **Fuseau horaire et langue** | `Intl.DateTimeFormat().resolvedOptions().timeZone` est lu ; une langue `en-US` avec un fuseau `Asia/Tokyo` est suspecte ; fuseau, langue et mode d'affichage à fixer ensemble. [blog] https://pydoll.tech/docs/deep-dive/fingerprinting/browser-fingerprinting/ ; https://dev.to/vhub_systems_ed5641f65d59/how-sites-detect-headless-browsers-and-how-to-evade-each-signal-2026-guide-2jj0 | Oui : régler `TZ`, `LANG` et la locale du contexte pour qu'ils collent à l'IP de sortie. Réglage Chrome exact : voir doc Playwright (non consultée ici) |
| **IP de datacenter** | Une IP de mauvaise réputation est challengée avec ou sans interface (blog pydoll ci-dessus). | Hors sujet du poste, mais annule les autres efforts |

## 4. Ce que disent les éditeurs et auteurs d'outils

- **DataDome** (juin 2024, màj avril 2026) : fingerprints du nouveau headless et de Chrome presque identiques, donc passage à la détection CDP, qui marche aussi en mode avec interface. Plus tard : `navigator.webdriver` et CDP font partie du jeu de signaux mais « n'ont jamais été la vérité de terrain » (date non précisée). [vendeur] https://securityboulevard.com/2024/06/how-new-headless-chrome-the-cdp-signal-are-impacting-bot-detection ; https://datadome.co/threat-research/how-browser-vendors-are-quietly-making-automation-harder-to-detect/ (lien vu en résultat, page non lue)
- **DataDome, décembre 2025** (d'après un extrait de recherche, page non lisible : erreur 403) : les empreintes tirées du matériel (audio, vidéo, etc.) perdent de l'utilité à cause des protections de vie privée ; ne pas dépendre d'une seule catégorie de signaux. [vendeur] https://datadome.co/threat-research/end-of-fingerprinting-how-browser-privacy-reshaping-bot-detection/
- **Castle** (13/03/2025) : trois signaux pour Puppeteer : `HeadlessChrome` dans le User-Agent, `navigator.webdriver`, effet de bord CDP (surcharge du getter `stack` d'une Error). [vendeur] https://blog.castle.io/how-to-detect-headless-chrome-bots-instrumented-with-puppeteer-2/
- **cside** (15/07/2026, màj 20/07/2026) : un Chrome avec interface sur écran virtuel « supprime tous les indices propres au headless en gardant l'automatisation dessous ». Couches restantes : liaison CDP (« l'indice plus difficile »), cohérence du rendu GPU, écran/fenêtre, polices, canvas/AudioContext trop uniformes, `hardwareConcurrency`/mémoire, comportement. La page ne dit pas si un GPU réel sur écran virtuel est signalé en soi ; ses contrôles visent les profils falsifiés incohérents. [vendeur] https://cside.com/blog/detect-ai-agents-stealth-browsers
- **Autres listes publiques** (indices : plugins vides, nombre de langues, `speechSynthesis`, `devicePixelRatio`, rendu logiciel) : blogs sans méthode vérifiable. https://blog.send.win/headless-browser-detection-methods/ ; https://www.github.com/azerpas/detect-headless
- Consensus : aucun signal seul n'est fiable ; ce qui compte est la **cohérence** entre couches. Quelle part chaque signal pèse dans la décision d'un fournisseur : **non confirmé** (non publié).

## 5. Limites connues

- **Stabilité.** Plantages de mémoire partagée en Docker (voir point 1). Xvfb en PID 1 qui se bloque. Firefox en délai d'attente sous `xvfb-run` dans Docker, Chrome et WebKit corrects (un seul témoignage). [blog] https://community.latenode.com/t/docker-playwright-ui-mode-xserver-issue-need-solution/26469
- **Rendu logiciel.** Il tourne sur le processeur (llvmpipe répartit sur tous les cœurs ; scènes lourdes 6 à 14 s). [blog Microlink] Risque d'écrans noirs sur certaines pages lourdes.
- **Mémoire.** Aucune mesure fiable trouvée. Estimations de blogs : 100 à 300 Mo de base + 50 à 150 Mo par page ; Xvfb ajoute des processus (Browserless). Une thèse citée par un blog donne une mémoire médiane de 6,1 % (headless), 13 % (Chrome normal), 6,7 % (Chrome sous Xvfb), pourcentages sans étiquette, à prendre avec prudence. [blog] https://webscraping.ai/faq/headless-chromium/what-are-the-resource-requirements-for-running-headless-chromium-at-scale ; https://www.browserless.io/blog/headless-browser-practices
- **Nombre de navigateurs par machine.** Aucune source ne donne de densité vérifiée. Conseil des blogs : limiter la concurrence par la RAM, pas par les cœurs, et mesurer soi-même le RSS de tous les processus (navigateur, rendu, Xvfb) à plusieurs niveaux de concurrence.
- **GPU réel dans un conteneur.** Peu documenté ; échecs signalés (repli sur SwiftShader malgré une carte NVIDIA). Le seul guide officiel Chromium couvre les instances NVIDIA et renvoie vers des dépôts tiers. [doc] https://chromium.googlesource.com/chromium/src/+/main/docs/gpu/server-side-headless-linux-chrome-with-gpus.md

## Ce qu'il faudrait mesurer soi-même
1. User-Agent, `navigator.userAgentData.brands` et en-têtes `sec-ch-ua*` : Chrome avec interface sur Xvfb, `--headless=new`, headless shell.
2. `WEBGL_debug_renderer_info` (vendeur et renderer) dans chaque configuration : SwiftShader, llvmpipe, GPU réel.
3. `screen.width/height/colorDepth`, `devicePixelRatio`, `outerWidth/innerWidth` avec une taille Xvfb choisie.
4. Liste des polices détectables et `speechSynthesis.getVoices()` avant et après installation de polices et d'un moteur vocal.
5. `Intl` (fuseau, langue) face à l'IP de sortie.
6. Mémoire et processeur réels par navigateur et nombre maximal avant dégradation.
7. Si Chrome 137 et plus plante ou perd WebGL sans `--enable-unsafe-swiftshader` sur la machine cible.

## Non confirmé (récapitulatif)
- User-Agent et `sec-ch-ua` exacts de `--headless=new` selon la version.
- Chrome avec interface sur Weston headless (Wayland) pour ce cas d'usage.
- Rôle de D-Bus ; liste précise de polices et paquet de voix de synthèse.
- Statut final du retrait de SwiftShader (Chrome 137 visé, intention du 13/02/2025).
- Prise en charge x86_64 du canal `chrome` par Playwright/Patchright (non précisée dans la doc lue).
- Cohérence de la chaîne GPU d'une carte de serveur avec un profil de poste.
- Densité de navigateurs par machine ; part de chaque signal chez les éditeurs.
- Pages DataDome 2025 et « browser vendors » : lues seulement par extrait de recherche (403).

## Sources (date quand connue)
Documentation officielle
- Playwright, CI : https://playwright.dev/docs/ci (date non indiquée)
- Playwright, Docker : https://playwright.dev/docs/docker (date non indiquée)
- Playwright, navigateurs : https://playwright.dev/docs/browsers (date non indiquée)
- Patchright Python, README : https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python (date non indiquée)
- Chrome, nouveau headless : https://developer.chrome.com/docs/chromium/new-headless (date non indiquée)
- Chrome, retrait de `--headless=old` : https://developer.chrome.com/blog/removing-headless-old-from-chrome (23/10/2024)
- Chromium, SwiftShader (intention de retrait) : https://groups.google.com/a/chromium.org/g/blink-dev/c/yhFguWS_3pM (13/02/2025)
- Chromium, GPU en headless : https://chromium.googlesource.com/chromium/src.git/+/lkgr/docs/gpu/using-gpu-hardware-in-headless-chrome.md ; https://chromium.googlesource.com/chromium/src/+/main/docs/gpu/server-side-headless-linux-chrome-with-gpus.md
- Chromium, test Wayland/Weston : https://chromium.googlesource.com/chromium/src/+/HEAD/testing/xvfb.py
- Chromium, test marque `HeadlessChrome` : https://chromium.googlesource.com/chromium/src/+/901b499ceed663f237665ce1fdf0f84f99816d6f/headless/test/headless_browser_user_agent_metadata_browsertest.cc
- Debian, `xvfb-run` : https://manpages.debian.org/trixie/xvfb/xvfb-run.1.en.html
- Puppeteer, dépannage : https://github.com/puppeteer/puppeteer/blob/v1.12.1/docs/troubleshooting.md (ancienne version)

Éditeurs anti-bot
- DataDome, nouveau headless et CDP : https://securityboulevard.com/2024/06/how-new-headless-chrome-the-cdp-signal-are-impacting-bot-detection (13/06/2024, màj 14/04/2026)
- DataDome, fin du fingerprinting : https://datadome.co/threat-research/end-of-fingerprinting-how-browser-privacy-reshaping-bot-detection/ (déc. 2025, non lu)
- DataDome, vendeurs de navigateurs : https://datadome.co/threat-research/how-browser-vendors-are-quietly-making-automation-harder-to-detect/ (non lu, date inconnue)
- Castle : https://blog.castle.io/how-to-detect-headless-chrome-bots-instrumented-with-puppeteer-2/ (13/03/2025)
- cside : https://cside.com/blog/detect-ai-agents-stealth-browsers (15/07/2026, màj 20/07/2026)

Blogs, forums, tiers (avis, non établis)
- Scrappey, SwiftShader : https://scrappey.com/qa/anti-bot/what-is-the-swiftshader-renderer-tell (15/06/2026)
- Scrappey, voix de synthèse : https://scrappey.com/qa/anti-bot/what-is-speech-synthesis-fingerprinting (31/05/2026)
- Microlink, WebGL sans GPU : https://microlink.io/blog/webgl-without-a-gpu (date inconnue ; exemple Chrome 150 / Mesa 26.1.3)
- SeleniumBase, issue 3162 : https://github.com/seleniumbase/SeleniumBase/issues/3162 (24/09/2024)
- OddBird, Playwright headed en Docker : https://oddbird.net/2022/11/30/headed-playwright-in-docker (30/11/2022)
- Docker forum, GPU NVIDIA : https://forums.docker.com/t/hardware-acceleration-for-headless-chrome-with-nvidia-gpu/132557 (date inconnue)
- Browserless : https://www.browserless.io/blog/run-puppeteer-in-docker ; https://www.browserless.io/blog/headless-browser-practices (dates inconnues)
- webscraping.ai : https://webscraping.ai/faq/headless-chromium/what-are-the-resource-requirements-for-running-headless-chromium-at-scale (date inconnue)
- Divers : https://pydoll.tech/docs/deep-dive/fingerprinting/browser-fingerprinting/ ; https://databay.com/blog/how-sites-detect-headless-browsers ; https://www.github.com/azerpas/detect-headless ; https://blog.send.win/headless-browser-detection-methods/ ; https://dev.to/vhub_systems_ed5641f65d59/how-sites-detect-headless-browsers-and-how-to-evade-each-signal-2026-guide-2jj0 ; https://www.itechguides.com/?p=873981 ; https://discord.apify.com/m/1296473256156467301 ; https://community.latenode.com/t/docker-playwright-ui-mode-xserver-issue-need-solution/26469 ; https://awesome.ecosyste.ms/projects/github.com%2Fsocrateslee%2Fxvfb-chrome ; https://hub.docker.com/hardened-images/catalog/dhi/playwright/guides (dates inconnues)
