# Décisions — NOEZIA ShadowLab

Format : `D-xx — date — décision (pourquoi)`. Une décision remplacée est barrée avec un renvoi.

- **D-01 — 03/11/2026 — Python, FastAPI, SQLite, `uv`.** Un seul langage pour le lanceur, le site et l'API ;
  SQLite suffit au prototype (un fichier, mode WAL pour deux processus) ; migrations maison numérotées.
- **D-02 — 03/11/2026 — Un seul serveur FastAPI pour le site de test, la détection, l'API et le tableau de
  bord**, au lieu de quatre services. Moins de pièces pour un MVP local ; les modules restent séparés
  (`site/`, `detection.py`, `api.py`, `tableau.py`) pour être éclatés plus tard.
- **D-03 — 03/11/2026 — Le site de test tourne dans un processus à part pendant une campagne.** Dans le même
  processus, son CPU comptait dans chaque passage (≈ 98 % mesuré pour les clients HTTP sur l'essai).
- **D-04 — 03/11/2026 — Moteurs dans leur configuration standard, seuls deux réglages imposés** : pas de
  redirection suivie par la bibliothèque (le périmètre contrôle chaque étape) et une seule tentative pour
  Scrapling (les erreurs sont comptées, pas masquées).
- ~~**D-05 — 03/11/2026 — `StealthyFetcher` de Scrapling non intégré.** C'est un navigateur modifié pour échapper
  aux détecteurs ; le cahier des charges exclut les modifications d'empreinte. Seul le client HTTP
  `FetcherSession` est intégré.~~ Remplacée par D-15.
- **D-06 — 03/11/2026 — `httpx` ajouté comme témoin brut** (aucun réglage d'en-têtes) : il donne le point
  bas de comparaison pour les clients HTTP.
- **D-07 — 03/11/2026 — Verrou réseau pour les deux navigateurs** (mandataire bloquant `127.0.0.1:9`, exceptions
  = hôtes autorisés). Le filtre `route` de Playwright laissait passer les redirections : un test l'a montré
  (redirection vers `example.com` suivie). Selenium n'a pas de filtre de requêtes.
- **D-08 — 03/11/2026 — BotD servi en local, `monitoring: false`.** Pas de CDN ; la statistique d'usage que
  BotD envoie à FingerprintJS est coupée ; la politique de sécurité du site bloque toute sortie.
- **D-09 — 03/11/2026 — Classement en trois valeurs (`automatise`, `humain`, `indetermine`).** Un détecteur
  qui n'a pas de quoi trancher s'abstient ; l'abstention est rapportée à part et n'entre ni dans les vrais ni
  dans les faux. Intervalles de Wilson à 95 %.
- **D-10 — 03/11/2026 — Faux positifs mesurés uniquement sur des sessions humaines réelles** (`/manuel`). Aucune
  session « humaine » simulée par un automate : ce serait une fausse référence.
- **D-11 — 03/11/2026 — Temps CPU en ms ajouté au pourcentage** (migration 2). Sur un passage de 2 ms, le
  pourcentage d'un cœur est proche de 100 % et ne dit rien de la consommation réelle.
- **D-12 — 03/11/2026 — Règles HTTP v2** : demande `Upgrade: h2c`, `Host` hors de la première place en HTTP/1.1,
  `Referer` avec `Sec-Fetch-Site: none`. Relevées sur le client HTTP de Scrapling, que les règles v1 classaient
  « humain » ; ce sont des incohérences qu'aucun navigateur ne produit.
- **D-13 — 03/11/2026 — Docker Compose reporté.** OrbStack n'était pas lancé et rien ne l'exige pour tourner en
  local ; une image non vérifiée serait pire que pas d'image. À faire avec le déploiement sur Linux.
- **D-14 — 03/11/2026 — Suites de la revue de sécurité du premier commit.** Options de moteur sur liste blanche
  typée (`Driver.options_permises`) : les options de Scrapling allaient telles quelles à `FetcherSession`, qui
  accepte mandataire, rotation de mandataires et redirections. En écoute locale, l'en-tête `Host` doit être un nom
  local ou autorisé (contre le « DNS rebinding »). Alias YAML refusés (expansion d'un petit fichier). Verrou de
  campagne libéré si la création échoue. Non corrigé, documenté : le DNS résolu au contrôle n'est pas épinglé
  pour la connexion (voir `docs/architecture.md`, Limites).
- ~~**D-15 — 03/11/2026 — Outils anti-détection et modification d'empreinte autorisés contre nos propres protections**
  (décision d'Ethan, remplace D-05). Sans adversaire réel, un taux de détection de 100 % ne prouve rien : il ne
  mesure que des outils naïfs. Restent exclus : toute destination non autorisée, tout solveur de CAPTCHA, tout
  contournement écrit sur mesure contre un détecteur commercial ou un service tiers.~~ **Révisée par D-30.**
- **D-16 — 03/11/2026 — Le projet est une plateforme de R&D à long terme, pas un benchmark ponctuel** (décision
  d'Ethan). Trois axes : Arena (défenses configurables à difficulté progressive), catalogue + moteur expérimental
  propre (combinaison modulaire des meilleures techniques open source), mesure scientifique. À terme, couche IA
  pour planifier les campagnes et recommander des optimisations. Les résultats de CAPTCHA providers en test keys
  sont étiquetés `captcha_test` et ne sont jamais confondus avec un vrai contournement.
- **D-17 — 03/11/2026 — Environnements isolés par pont JSON-over-stdio** pour les moteurs aux dépendances
  incompatibles (camoufox → playwright<1.63, seleniumbase → pytest==9.1.1). Chaque moteur a son `pyproject.toml`
  dans `moteurs_isoles/`, son propre venv `uv`, et communique avec le processus principal via `engines/pont.py`.
- **D-18 — 03/11/2026 — Arena à 6 niveaux de difficulté progressifs** (01 Baseline → 06 Défense multicouche).
  Remplace les 3 profils faible/moyen/élevé qui deviennent des sous-ensembles des niveaux. Chaque niveau ajoute
  des couches de protection ; un moteur qui passe le niveau N a franchi toutes les défenses des niveaux inférieurs.
- ~~**D-13 — 03/11/2026 — Docker Compose reporté.**~~ Annulée : Docker Compose opérationnel (Coraza + Nginx)
  pour l'Arena.
- **D-19 — 04/11/2026 — Fingerprinting à trois modes de blocage** (`non`, `http`, `tout`). Niveaux 02-03
  loguaient les suspicions sans jamais bloquer : tous les moteurs avaient les mêmes résultats qu'en niveau 01.
  Niveau 02 bloque sur signaux HTTP/TLS seuls (attrape les outils HTTP bruts), niveau 03 ajoute les signaux
  JavaScript (attrape l'automation navigateur standard). Niveaux 04-06 gardent `tout`.
- **D-20 — 04/11/2026 — Patchright reste en configuration standard** (décision d'Ethan). Il est bloqué dès le
  niveau 02 (HeadlessChrome dans le User-Agent, pas de Accept-Language) mais c'est une mesure de référence
  précieuse : elle montre ce que les patchs JavaScript seuls changent, sans réglage HTTP. Modifier sa config
  pour faire passer ses résultats au vert ferait perdre cette mesure.
- **D-21 — 05/11/2026 — Plan v0.7 « Fiabilité scientifique »** (`docs/plan-v07.md`). L'audit de la campagne #17
  a montré 8 défauts structurels (classification fausse, chaîne de blocage qui occulte les détecteurs JS, biais
  des scénarios mono-page, absence de faux positifs). Priorité P0 = corriger ce qui fausse les résultats avant
  d'ajouter des fonctionnalités. Plan détaillé dans `docs/plan-v07.md`.
- **D-22 — 08/11/2026 — NOEZIA v4 : architecture modulaire à la place du wrapper monolithique.** Le v3
  (`noezia_engine.py`, 464 lignes) était un wrapper Patchright avec tout dans un fichier : profil en dur
  (M5 Pro), spoofing par init script unique, comportement minimal. Le v4 (`engines/noezia/`, ~2000 lignes,
  20+ fichiers) sépare profils cohérents (générateur + validateur + stockage), comportement humain (souris
  minimum-jerk + Fitts, clavier QWERTY, défilement inertiel, tempo adaptatif), furtivité (5 scripts JS
  modulaires avec PRNG par profil), et défis (3 handlers indépendants). L'ancien moteur reste sous le nom
  `noezia-experimental` pour comparaison. Le v4 est conçu pour évoluer : chaque module est testable et
  remplaçable indépendamment, les profils sont persistants et reproductibles par graine.
- **D-23 — 09/11/2026 — Durcissement simultané Arena + moteur.** Ajouter de nouveaux détecteurs à l'Arena
  (intégrité des propriétés, cohérence d'environnement — 12 total) en même temps que les contre-mesures
  dans NOEZIA (prototype chain, environnement.js). Le moteur et l'Arena progressent en parallèle : chaque
  nouveau détecteur est une épreuve que le moteur doit passer, et chaque évasion réussie valide la qualité
  du spoofing. Les propriétés navigator passent sur `Navigator.prototype` (pas l'instance) et les dimensions
  écran sur `Screen.prototype` pour reproduire la vraie chaîne de prototype de Chrome.
- **D-24 — 09/11/2026 — NOEZIA v5 : intégration des techniques de puppeteer-extra-plugin-stealth.** Plutôt
  que de forker littéralement les projets concurrents, on prend les techniques de puppeteer-stealth (15 modules
  d'évasion étudiés) et on les réécrit pour l'architecture natif()/NOEZIA_PROFIL de NOEZIA. 3 nouveaux scripts
  (iframes.js, codecs.js, polices.js), navigateur.js enrichi (+chrome.app, +chrome.loadTimes, +chrome.runtime
  complet, +navigator.languages gelé). Args de lancement Chromium durcis (disable-blink-features, suppression
  flags d'automation). 3 nouveaux détecteurs Arena pour valider (chrome-apis, media-codecs, langues). NOEZIA
  passe de ~1 900 à 2 674 lignes, 8 scripts de furtivité au lieu de 5, 15 détecteurs Arena au lieu de 12.
- **D-25 — 09/11/2026 — NOEZIA v6 : défenses anti-headless dédiées.** Headless Chrome a des comportements
  spécifiques détectables : `document.hasFocus()` retourne false, `document.visibilityState` est 'hidden',
  `speechSynthesis.getVoices()` retourne une liste vide, `mediaDevices.enumerateDevices()` ne trouve aucun
  périphérique, les permissions API sont toutes 'denied'. Nouveau script `headless.js` qui corrige chacun de
  ces signaux. Permissions API étendu dans navigateur.js (18 permissions → 'prompt', 3 capteurs → 'granted').
  2 nouveaux détecteurs Arena (headless, permissions-etendu). Total : 10 scripts furtivité, 17 détecteurs.
- **D-26 — 09/11/2026 — NOEZIA v6+ : durcissement multi-vecteur.** Ajouts post-v6 : filtrage des stack
  traces d'erreur (Error.prepareStackTrace patché, regex contre patchright/playwright/puppeteer/cdp/devtools
  dans les noms de fichiers), `performance.memory.jsHeapSizeLimit` normalisé (4 294 705 152), `window.screenX/Y`
  avec offsets réalistes au lieu de 0,0, suppression de `navigator.scheduling` (spécifique headless),
  `PluginArray`/`MimeTypeArray` itérables (Symbol.iterator + accès par nom), cohérence Intl
  (`Intl.DateTimeFormat`/`NumberFormat` locale alignée sur `navigator.language`), `shaderPrecisionFormat`
  WebGL cohérent avec le GPU déclaré, collecteurs observateur enrichis (stack_trace_test,
  performance_memory). 4 nouveaux détecteurs Arena : stack-trace, position-fenetre, webrtc, permissions-etendu.
  Total : 10 scripts furtivité (944 lignes JS), 20 détecteurs Arena, moteur NOEZIA 2 756 lignes.
- **D-27 — 09/11/2026 — NOEZIA v7 : nettoyage automation, CSS/timing, 24 détecteurs.** Nouveau 11e script
  `automation.js` (dernier dans le pipeline) : suppression systématique des globales d'automation
  (Playwright, Selenium, ChromeDriver, Puppeteer, PhantomJS, Nightmare), nettoyage document, correction
  `matchMedia` pour hover/pointer headless (desktop = hover:hover, pointer:fine), suppression des propriétés
  propres inattendues sur `navigator` (webdriver, hardwareConcurrency etc. doivent être sur le prototype),
  normalisation `performance.now()` à 100µs (comportement standard cross-origin sans SharedArrayBuffer),
  marqueurs `__NOEZIA_PROFIL__`/`__NOEZIA_NATIF__` rendus non-énumérables. 4 nouveaux détecteurs Arena
  (automation-globals, css-media, prototype-chain, timing-precision) avec collecteurs dans observateur.js.
  Total : 11 scripts furtivité (~1 100 lignes JS), 24 détecteurs Arena, 265 tests.
- **D-28 — 09/11/2026 — NOEZIA v8 : trajectoire calée sur le frame rate.** Le nombre de points de
  trajectoire souris était calculé sur la distance (jusqu'à 120 points/mouvement), générant 250-330
  mousemove/page. L'observateur Arena garde les 50 derniers délais : les pauses entre mouvements étaient
  poussées hors fenêtre, ne laissant que des délais uniformes ~16ms → détection `entropie-interaction`
  (CV < 0.15 + max < 80ms). Fix : `n_points = max(6, min(int(duree_ms / 16), 50))` — calé sur 60 fps
  comme un vrai navigateur. Résultat : 0 détection automatise sur 109 passages × 24 détecteurs.
  Aussi : `outerWidth`/`dpr` déplacés sur `Window.prototype` (anti own-property detection),
  comportement post-navigation (`_interaction_post_clic_navigation`), pauses inter-clics améliorées.
- **D-29 — 09/11/2026 — NOEZIA v9 : modèle comportemental universel.** Les versions v4-v8 calibraient les
  délais sur les seuils de nos 24 détecteurs (CV > 0.15, max > 80ms, etc.). Une vraie défense universelle
  doit passer *n'importe quel* test statistique. Nouveau module `humain.py` : délais souris log-normaux
  (Hwang 2006, médiane 280ms σ=0.9), clavier par digraphes biomécaniques (Card/Moran/Newell 1983) avec
  distribution ex-gaussienne, profils souris (rapide/moyen/lent), micro-pauses Pareto (8%), auto-corrélation
  temporelle via marche aléatoire multiplicative (`RythmeHumain`). Les modules `souris.py`, `clavier.py`,
  `tempo.py` réécris pour déléguer à `humain.py`. Résultat campagne 37 : 108 passages × 24 détecteurs,
  0 détection automatise. Données v9 : CV=3.43 (seuil=0.15), médiane=25ms, max=6049ms, queue lourde
  typique d'un humain. Les distributions sont correctes par construction — aucun seuil à tuner.
- **D-30 — 09/11/2026 — Phase interne : périmètre illimité débrayable, et moteur universel.** (décision
  d'Ethan, révise D-15.) Objectif assumé : un moteur qui se connecte à n'importe quel site et franchit
  n'importe quel détecteur. Pour ne pas brider l'expérimentation : **périmètre illimité par défaut**
  (`SHADOWLAB_HOTES_AUTORISES=*`), mais le rejet-par-défaut reste **débrayable** (mécanisme conservé,
  pas supprimé) — le durcissement final est différé et documenté dans `docs/securite-a-finaliser.md`.
  Non responsable de l'usage ; en interne on ne pointe que nos propres cibles. Contournement d'un
  détecteur commercial : autorisé **sur cibles autorisées + divulgation coordonnée** (plus « jamais »).
  **Restent non négociables** : aucun solveur de CAPTCHA réel (reCAPTCHA/hCaptcha/Turnstile prod — le
  démo Arena et les test keys restent permis ; le but est de *ne pas déclencher* le CAPTCHA), aucune
  mesure inventée, étiquetage des résultats en test keys. Implémentation : `perimetre.ILLIMITE`,
  `base.liste_directe`, défaut `config.charger`, filtrage du `*` côté serveur de test (`site/app.py`).
- **D-31 — 10/11/2026 — Signatures mémoire seule (`chemin=None`).** Pour les scénarios en mémoire
  (campagnes, tests unitaires), `Signatures()` sans argument fonctionne en RAM sans fichier. Plus
  simple qu'un `tempfile` : pas d'effets de bord disque, pas de nettoyage. Le fichier JSON reste
  disponible pour la persistance inter-exécutions (`Signatures(Path("..."))`). Implémentation :
  `chemin: Path | None = None` dans `extraction.Signatures.__init__`, `enregistrer` saute l'écriture
  si `_chemin is None`.
- **D-32 — 10/11/2026 — Crawlee et Zendriver comme moteurs isolés.** Les deux derniers moteurs async
  Python du catalogue (crawlee-python 1.11, zendriver 0.17) sont intégrés via le pont subprocess. Crawlee
  apporte un client HTTP avec empreinte TLS/headers réaliste (impit) ; zendriver pilote Chrome par CDP sans
  WebDriver (anti-détection native, AGPL-3.0 — à surveiller avant livraison). Le pont est corrigé pour
  charger `base.py` sans déclencher `engines/__init__` (pré-enregistrement de modules fantômes), ce qui
  répare aussi les moteurs isolés existants.
- **D-33 — 10/11/2026 — Détecteurs par niveau : `fingerprinting.detecteurs` dans le profil Arena.** Les 6
  détecteurs hardcodés (`REGLES_REQUETE` + `REGLES_JAVASCRIPT`) laissaient 26 détecteurs collectés mais
  ignorés par le gardien. Le champ `detecteurs` dans la config `fingerprinting` de chaque niveau liste
  explicitement les détecteurs consultés : 0 (baseline) → 2 → 12 → 20 → 28 → 33. Si absent ou vide,
  le comportement legacy (6 détecteurs) est préservé. La campagne D-33 a montré que NOEZIA passe tous
  les niveaux : les détecteurs individuels sont trop faibles, un score composite est nécessaire.
- **D-34 — 10/11/2026 — Patch furtivité : propriété propre + prototype.** Chrome (y compris Patchright)
  place certaines propriétés (`outerWidth`, `outerHeight`, `hardwareConcurrency`, `deviceMemory`) comme
  propriétés propres sur `window`/`navigator`, pas seulement sur le prototype. Un `defineProperty` sur
  le prototype seul est masqué. Règle : tout patch de propriété navigateur doit cibler le prototype
  ET l'instance. Corrigé dans `environnement.js` et `navigateur.js`. Le détecteur `coherence-profonde`
  excluait aussi à tort les `hardwareConcurrency` Apple Silicon (10, 12, 14…) comme non-puissance-de-2.
- **D-35 — 10/11/2026 — Score composite : agrégation des signaux faibles inter-détecteurs.** Un moteur
  bien patché (type NOEZIA) échappe à chaque détecteur pris isolément — aucun n'atteint le seuil de 1.0.
  Le score composite cumule les signaux faibles (poids > 0) de tous les détecteurs « indéterminés ».
  Si la somme ≥ `seuil_composite` (dans `fingerprinting` du profil Arena), un motif synthétique
  « composite » bloque la session. Seuils progressifs : 03=1.5, 04=1.0, 05=0.7, 06=0.5. Le score
  composite ne se déclenche que quand aucun détecteur individuel n'a déjà bloqué (pas de double peine).
- **D-36 — 10/11/2026 — Composite différé : évaluation à la collecte, blocage à la 2e page.** Le gardien
  vérifie au moment de servir la page, mais l'empreinte JS n'arrive qu'après le chargement (2-3 s).
  Le composite ne peut donc pas bloquer la 1re page. Solution : `/lab/collecte` évalue le composite
  dès réception de l'empreinte et enregistre une décision `composite-differe` / `detecte`. Toute requête
  protégée ultérieure (2e page) consulte cette décision et bloque immédiatement. Comportement réaliste :
  les vrais WAF (Cloudflare, Akamai) font aussi « collecter puis vérifier ».
- **D-37 — 10/11/2026 — 6 détecteurs cross-contexte inspirés CreepJS : AudioContext, polices, Math,
  DOMRect, cohérence iframe, deep Proxy.** L'audit comparatif avec CreepJS a identifié 6 lacunes majeures
  de nos 33 détecteurs. Les 6 techniques implémentées couvrent : fingerprint audio (oscillateur offline →
  hash stable, détection headless sans carte son), empreinte des polices installées (cohérence OS),
  intégrité des fonctions Math (native vs patchée), empreinte DOMRect multi-polices (stabilité + nativeness
  de getBoundingClientRect), cohérence cross-iframe (propriétés navigator, Math, chrome, own keys entre
  thread principal et iframe srcdoc), et détection profonde de Proxy sur les getters natifs (toString,
  illegal invocation, descripteurs Object vs Reflect, chaîne prototype, stack d'erreur). Le collecteur JS
  (`observateur.js`) envoie les données ; 6 classes Python (`detection.py`) les classent. Total : 39
  détecteurs, 338 tests verts.
- **D-38 — 10/11/2026 — Illegal invocation sur getters patchés.** Les getters natifs de Chrome lancent
  `TypeError: Illegal invocation` quand appelés avec un `this` non conforme (ex: `getter.call({})`). Nos
  patches retournaient silencieusement la valeur — signature détectable par la sonde deep-proxy. Ajout d'un
  paramètre `cible` à `natif()` : quand présent, vérifie `this instanceof Constructor` avant de retourner.
  Appliqué aux 3 fichiers de furtivité (navigateur, environnement, headless). Campagne 58 confirme la
  disparition du signal `illegal_invoc_absent` sur NOEZIA.
- **D-39 — 10/11/2026 — Faux positif proxy_dans_stack : renommer la fonction de test.** La regex
  `/Proxy|proxy/` du détecteur deep-proxy matchait le nom de la fonction `deepProxyDetectionTest` dans
  les stack traces d'erreur, pas un vrai Proxy V8. Renommée en `testDetectionProfonde()`. Campagne 62
  confirme deep-proxy « humain » avec 0 signal.
- **D-40 — 10/11/2026 — DOMRect déterministe, navigator sans own props : 37/39 humain.** Trois corrections :
  (1) bruit DOMRect dérivé des valeurs du rect et du seed profil (pas du PRNG global) → stable entre deux
  appels ; (2) `hardwareConcurrency`/`deviceMemory` seulement sur `Navigator.prototype` (le vrai Chrome ne
  les met pas en propre sur l'instance) ; (3) nettoyage des own props résiduelles de Patchright. Campagne 64 :
  37 humain, 0 automatisé, 2 indéterminés structurels (tls=hors Arena, worker-consistency=timeout).
- **D-41 — 10/11/2026 — Propagation profil dans les blob workers : 38/39 humain.** Deux problèmes :
  (1) la CSP bloquait les blob workers (manquait `worker-src 'self' blob:`) ; (2) le XHR synchrone sur les
  blob URLs échouait silencieusement, le worker tournait sans patches profil. Fix : interception de
  `URL.createObjectURL` pour tracker les blobs JS, puis Blob compositing (`new Blob([prologue, origBlob])`)
  au lieu de XHR. Prologue nettoyé pour poser les propriétés sur le prototype uniquement (cohérence D-40).
  Campagne 66 : 38 humain, 0 automatisé, 1 indéterminé (tls=hors Arena, pas applicable en local).
- **D-42 — 10/11/2026 — Suppression des gardes hostname dans les 9 scripts de furtivité.** Chaque script
  vérifiait `location.hostname` et ne s'exécutait que sur localhost/.localhost/.test. Les patches de furtivité
  étaient donc **totalement désactivés sur les sites externes** — NOEZIA naviguait « nu » sur bot.incolumitas.com.
  Le périmètre Python (`self.verifier(url)` + `SHADOWLAB_HOTES_AUTORISES`) est la vraie barrière de sécurité,
  pas les gardes JS. Suppression dans : automation.js, cdp.js, codecs.js, environnement.js, headless.js,
  iframes.js, navigateur.js, polices.js, workers.js. Impact immédiat : passage de 7 FAIL à 1 FAIL sur
  bot.incolumitas.com (campagne 70).
- **D-43 — 10/11/2026 — webdriver supprimé du prototype Navigator : 0/27 FAIL sur bot.incolumitas.com.**
  fpCollect vérifie `'webdriver' in navigator` (présence, pas valeur) ; fpscanner marque FAIL si la propriété
  existe, même avec `value=false`. Le vrai Chrome a aussi `webdriver` sur `Navigator.prototype` (getter → false),
  donc le test est un faux positif chez fpscanner. Plutôt que de redéfinir le getter, suppression complète
  du prototype : `navigator.webdriver` → `undefined` (falsy, passe tous les tests intoli et fpscanner).
  Campagne 71 : NOEZIA **0 FAIL / 27 tests**, verdict **humain** sur le détecteur indépendant
  bot.incolumitas.com. Playwright vanilla : 11 FAIL / 27.
- **D-44 — 10/11/2026 — Résolveur Turnstile réécrit : détection inline + timeout 30 s.** Deux bugs :
  1) `_resoudre_defis()` ne détectait les challenges que par URL, mais le gardien sert le challenge
  *inline* (même URL, status 403, `data-arena` sur le body) — corrigé par détection `data-arena`.
  2) `resoudre()` (a) attendait l'iframe Cloudflare en partageant le timeout avec le token (20 s total),
  et (b) vérifiait la soumission par URL (`"/lab/turnstile" not in u`) ce qui passait immédiatement
  pour les challenges inline — réécrit : polling du callback Arena (`#turnstile-etat`) + hidden input
  (le plus rapide gagne), timeout 30 s, vérification par disparition de `data-arena="turnstile"`.
- **D-45 — 11/11/2026 — Trois détecteurs renforcés : CDP, comportement v2, méta-composite.** La campagne 82
  montrait 0/72 détections NOEZIA (score=0, `_verdict()` retourne "humain" par défaut). Cause racine :
  modèle à signaux négatifs uniquement — si aucun signal connu n'est trouvé, humain par défaut. Trois
  ajouts :
  ~~1) **DetecteurCDP** : exploite les artefacts Chrome DevTools Protocol (debugger timing <0.05ms,
  absence de first-input, console patchée, scripts vides injectés, ressources CDP). Score 1.0 quand
  le debugger répond instantanément.~~ Point 1 remplacé par D-62
  (deux de ses signaux se déclenchaient chez tout le monde).
  2) **DetecteurComportement v2** : signaux de naturalité — ratio mousemove/click < 8 (trajectoires
  Bézier directes), absence de scroll, durée des pages trop régulière (CV < 0.2), navigation linéaire.
  3) **DetecteurMetaComposite** : méta-analyse — session avec >80% des détecteurs à 0 signal = suspecte.
  Résultat : campagne 86, 23/23 passages valides détectés (100%).
- **D-46 — 11/11/2026 — Agrégation composite dans issues.py (seuil 0.8).** Quand aucun détecteur
  individuel ne classifie "automatise", la somme des poids positifs de tous les signaux est comparée à
  0.8. Comble le gap quand le debugger CDP est au-dessus du seuil 0.05ms : les signaux CDP (0.4) +
  comportement (0.5) + meta-composite (0.5) = 1.4 dépassent le seuil. Le seuil 0.8 est arbitraire —
  à calibrer sur des sessions humaines réelles (D-10).
- **D-47 — 11/11/2026 — Score composite pondéré par famille de détecteurs (scoring.py).** Chaque détecteur
  appartient à une famille (transport, empreinte, intégrité, cohérence, comportement, corrélation) dotée
  d'un coefficient multiplicateur. Remplace la somme naïve de poids dans gardien.py et issues.py.
  Coefficients initiaux : transport 1.0, empreinte 0.7, intégrité 1.2, cohérence 0.8, comportement 1.0,
  corrélation 1.5. À calibrer sur données réelles (D-10).
- **D-48 — 11/11/2026 — Corrélation cross-session (correlation.py, migration 8).** Hash SHA-256 tronqué
  du profil navigateur et du canvas ; ~~table empreintes_vues ; détecteur correlation-session qui signale le
  recyclage de fingerprint (≥5 sessions identiques) et la vélocité anormale (≥30 sessions/h avec le même
  hash).~~ **(Règle 1.1 remplacée par D-89 : règle 2.0, par monde ; seuils et poids repris.)** Coefficient famille corrélation : 1.5 (le signal le plus fort). 41 détecteurs au total.
- **D-49 — 11/11/2026 — Niveau 07 « État de l'art ».** Tous les 41 détecteurs, seuil composite 0.3,
  WAF paranoia 4, rate limit 1 req/s, honeypots, Turnstile + reCAPTCHA, connexion à 2 tentatives max.
  Objectif : équivalent Cloudflare Enterprise Bot Management en local.
- **D-50 — 11/11/2026 — Masquage SwiftShader pour Linux headless sans GPU.** ~~Sur un serveur Linux sans GPU, Chromium utilise Google SwiftShader (logiciel)~~ **(faux avec une interface : Chrome 156 à 158 n'a alors aucun WebGL ; ne reste vrai que sans interface, « headless shell » — voir D-102)** ; les limites WebGL de SwiftShader (SUBPIXEL_BITS=4,
  MAX_ELEMENTS_*=65536, extensions réduites) trahissent un bot. Le script webgl.js détecte le backend
  réel au démarrage, override les paramètres distinctifs, et filtre les extensions du profil contre celles
  réellement disponibles. Correction aussi de la classification NVIDIA Linux (ANGLE+OpenGL sans D3D11
  ni Mesa → isLinuxGL) qui laissait GP vide.
- **D-51 — 11/11/2026 — 8 profils GPU Linux (au lieu de 3).** Intel UHD 630/770/Xe, NVIDIA RTX 3060/4070
  + Tesla T4 (serveur cloud), AMD Radeon RX 6700 XT + Pro W6800. Couvre les configurations serveur et
  desktop les plus courantes.
- **D-52 — 11/11/2026 — Détecteur TLS v2 : 17 règles d'analyse du ClientHello.** Le v1 avait 4 règles
  structurelles (GREASE, ALPN h2). Le v2 ajoute : comptage chiffrements/extensions, suites TLS 1.3
  (présence + position en tête), extensions Chrome-spécifiques (compress_certificate, ALPS),
  extensions Firefox (record_size_limit), confusion cross-navigateur, groupes elliptiques (x25519,
  ffdhe2048, ordre), algorithmes de signature, supported_versions, version TLS max, et détection
  d'empreinte OpenSSL (AES-256-GCM en tête). 28 tests unitaires dédiés.
- **D-53 — 11/11/2026 — Support HTTP/2 dans le frontal Arena + détecteur h2.** Le frontal négocie
  maintenant h2 via ALPN (`["h2", "http/1.1"]`). La classe `_ConnexionH2` (hérite de `_Connexion`)
  capture l'empreinte HTTP/2 style Akamai (SETTINGS frame : IDs + valeurs en ordre reçu,
  WINDOW_UPDATE connexion, PRIORITY) et relaie chaque requête vers Nginx via HTTP/1.1. Le nouveau
  détecteur `DetecteurH2` (11 règles) vérifie la cohérence du profil h2 avec le navigateur annoncé :
  Chrome 5 SETTINGS + WU ~15M, Firefox 2 SETTINGS + WU ~12M, bibliothèques = profil minimal.
  Famille `transport` dans le scoring. 16 tests unitaires. 42 détecteurs au total.
- **D-54 — 11/11/2026 — Objectif de la v1 du moteur, validé par Ethan ; plan unique `docs/PLAN.md`.**
  NOEZIA v1 = un moteur de récolte généraliste qui, lancé depuis un serveur Linux, mène un long travail
  sur un site protégé sans se faire bannir, et rapporte des données complètes et exactes. Il se prouve
  par des mesures sur nos propres cibles (site vitrine factice, tor-i) : récolte, discrétion, endurance
  « une identité » (un seul compte connecté, suivi régulier), endurance « plusieurs identités » (volume),
  livrable. Quatre paliers. Pourquoi : sans définition de « fini », la cible a changé trois fois en trois
  jours et le travail du 11/11 (D-47 à D-53) n'a été mesuré par aucune campagne. Les seuils chiffrés sont
  des choix de Claude, à recaler après les premières mesures. Le périmètre (D-30) est inchangé : l'usage
  sur des sites tiers reste une question ouverte pour Ethan.
- **D-55 — 12/11/2026 — Application publique réduite, séparée du laboratoire (`src/shadowlab/public/`).**
  Pour les sessions humaines de référence, on ne met jamais le labo en ligne (son API lance des navigateurs
  vers n'importe quelle adresse) : une application à part ne sert que le site vitrine, le consentement, la
  collecte et la suppression. Choix : consentement avant toute collecte ; jeton de session dans un cookie
  signé, jamais lu dans l'URL ; liste blanche d'en-têtes (ni adresse IP ni cookie stockés) ; aucune requête
  vers un tiers (sonde WebRTC sautée par `<meta name="sl-sans-tiers">`) ; aucun détecteur en direct, les
  humains ne sont jamais bloqués ; base et liste d'hôtes distinctes de celles du labo ; contact du
  responsable obligatoire au démarrage ; suppression par le participant dès le début (page « Ma session »)
  et purge automatique. Pourquoi : audit de sécurité du 11/11 (`notes/ia/analyse-paliers-2026-11-11.md`
  § 4) et conditions du § 5 du plan. Relue, éprouvée (12 failles volontaires détectées par les tests) et
  auditée par un second sous-agent. Mise en ligne : `docs/site-public.md`, à la charge d'Ethan.
- **D-56 — 12/11/2026 — Les humains arrêtés par niveau se mesurent par rejeu, avec le code de décision de
  l'Arena (`shadowlab rejeu`).** On ne fait pas passer chaque humain par chaque niveau : on rejoue les
  observations de sa session contre les détecteurs de chaque niveau. Choix : le rejeu appelle la même
  fonction que l'Arena (`gardien.motifs_suspicion`, réglages `gardien.parametres`) et décide aux mêmes
  moments (empreinte reçue, page contrôlée, fin de session) ; un détecteur qui n'a pas ses données (TLS et
  HTTP/2 hors frontal, corrélation, sonde WebRTC sautée, pièges non servis) est écarté et signalé, jamais
  compté ; sur le site public, les règles `cookies_ignores` et `host_tardif` sont écartées (donnée non
  gardée) ; la corrélation, qui dépend de l'historique de la base, reste hors du taux ; une session sans
  empreinte est comptée à part. Au passage, correction de l'Arena : `/lab/collecte` ignorait `exclure` et
  consultait le JavaScript même en `bloquer: http` ; les réglages sont maintenant les mêmes à la collecte
  et aux pages. Aucun effet sur les niveaux 01 à 07 (mêmes listes de détecteurs avant et après) ; les
  ablations faites avant le 12/11 (campagne 8) sont fausses pour tout détecteur qui tranche à la collecte.
  Pourquoi : jalon A du plan (étape 1.7) et règle « un détecteur n'est valide que s'il laisse passer les
  humains ». Limites : le rejeu ne rejoue ni le WAF, ni la limite de débit de Nginx, ni les défis et CAPTCHA.
- **D-57 — 12/11/2026 — Site public : un formulaire de contact à la place d'une adresse affichée.** Ethan
  ne veut pas afficher son adresse e-mail sur un lien très partagé. Choix : la page d'information nomme le
  responsable (`SHADOWLAB_PUBLIC_CONTACT` ; Ethan y met un pseudonyme, c'est son choix : le RGPD demande
  l'identité du responsable, voir `notes/ia/questions-ouvertes.md`) et renvoie vers `/contact` ; un
  message n'est que son texte et le jour de sa réception (ni adresse IP, ni session, ni navigateur, ni
  heure), 2 000 caractères au plus, caractères de contrôle retirés ; il est gardé dans un fichier à part de la base des sessions
  (`messages.sqlite3`, droits 600, `secure_delete`) et purgé à la même échéance ; lecture et effacement par
  `shadowlab public messages` et `effacer-message`. Limites : 3 messages par heure et par adresse, 30 par
  jour, 500 gardés. Pourquoi un fichier à part : la base des sessions garde le schéma du labo sans migration
  (la migration 9 est réservée au palier 2) et peut être copiée pour le rejeu sans emporter des messages où
  un visiteur a écrit comment le joindre. Limite : aucun envoi au responsable ; `shadowlab public servir`
  donne le nombre de messages au démarrage et écrit une ligne à l'écran à chaque arrivée. Écarté : un envoi par e-mail (il faudrait un
  compte d'envoi et son secret sur le poste).
- **D-58 — 12/11/2026 — (réservé)** : version réelle annoncée par le moteur, branche `moteur-version-reelle`, gardée de côté en attendant la mesure de l'identité native.
- **D-59 — 12/11/2026 — NOEZIA peut tourner en « identité native » (options `channel` et `identite_native`).**
  Mesuré dans la campagne 94 : l'identité réécrite par le moteur (User-Agent, `sec-ch-ua`, scripts
  d'empreinte) ne couvre pas toutes ses requêtes : « HeadlessChrome » apparaît sur 182 requêtes sur 1 160, la
  version annoncée se contredit, et 84 champs d'empreinte sur 315 diffèrent du même navigateur sans réglage.
  La documentation de Patchright, la base du moteur, recommande l'inverse : un vrai Chrome
  (`channel="chrome"`), avec interface, `no_viewport`, sans User-Agent ni en-têtes imposés (« Best Practice -
  use Chrome without Fingerprint Injection »). Choix : deux options déclarées, sans effet par défaut.
  `channel` choisit le navigateur installé ; `identite_native` retire le profil, les réglages de lancement,
  le User-Agent, les en-têtes, la fenêtre imposée et les scripts d'empreinte, et garde le comportement
  humain, la résolution des défis de l'Arena, la récolte et le verrou de périmètre. Pourquoi une option et
  pas un remplacement : la règle du projet veut une mesure avant de trancher
  (`configs/experiments/ablation-interface.yaml`, à comparer à la référence du même jour). Non couvert : le
  profil persistant recommandé par Patchright (identité qui dure, palier 2) ; le serveur Linux sans écran
  (palier 3). Reste imposé en identité native : le filtre réseau du périmètre (`route`), qui coupe le cache
  HTTP du navigateur, et les réglages par défaut d'un contexte Playwright (langue), à lire dans la mesure.
  Les options `profil` et `locale` sont alors sans effet.
- **D-60 — 12/11/2026 — Arena : « HeadlessChrome » cherché dans toutes les requêtes d'une session.** La règle
  `ua_headless` de `regles-http` ne lisait que la première page. Mesuré dans la campagne 94 : NOEZIA réécrit
  son identité sur cette page, mais 182 de ses 1 160 requêtes (envois de fin de page, redirections) disent
  « HeadlessChrome » dans `User-Agent` ou `sec-ch-ua`, et l'Arena ne le voyait pas. Choix : nouveau signal
  `headless_dans_une_requete` (poids 1, comme `ua_headless`), détecteur `regles-http` en 2.1. Accord d'Ethan
  (« Oui, ajoute-la ») : la règle 4 du plan demande son avis pour tout ajout à l'Arena. Pourquoi : aucun
  vrai navigateur n'envoie ce mot, donc aucun humain ne peut la déclencher, et sans elle l'Arena notait
  15/15 un moteur qu'un anti-bot réel arrêterait. Effet attendu, à mesurer par la campagne de référence
  du 12/11 : NOEZIA arrêté sur les scénarios à plusieurs pages dès qu'un envoi non réécrit est arrivé.
- **D-61 — 12/11/2026 — `pas_de_scroll` et `pas_de_pause` ne jugent que ce qu'ils peuvent voir.** Le relevé
  `comportement` d'`observateur.js` porte deux champs de plus : `page_defilable` (la page dépasse sa zone
  visible, mesuré à la sortie de la page) et `delai_souris_max_ms` (le plus grand délai entre deux mouvements
  de souris sur toute la page, sans plafond). `pas_de_scroll` ne compte que les pages qui pouvaient défiler ;
  `pas_de_pause` juge la page entière. Seuils et poids inchangés : on corrige ce que la règle regarde, pas sa
  sévérité. Un ancien relevé auquel il manque l'information ne fait conclure aucune des deux règles ; sous le
  plafond de 50 délais, la liste contient toute la page et fait foi. Versions : `comportement` 2.1,
  `entropie-interaction` 1.1 ; texte d'information du site public en version 2026-11-12.4. Pourquoi :
  campagne 94. La molette tournée sur `/lab/catalogue`, plus courte que la fenêtre, ne produit aucun `scroll`
  ; un seul geste continu de 50 événements (environ 1,5 s) suffisait à `pas_de_pause`, alors que les pages
  duraient 2,7 à 3,4 s. Un humain serait classé de même (règle « un détecteur n'est valide que s'il laisse
  passer les humains »). Ces deux signaux faisaient le score composite 0,85 qui arrêtait NOEZIA au niveau 05.
  Limites : un geste unique suivi d'un clic, sans arrêt entre deux mouvements, déclenche encore
  `pas_de_pause` ; non vérifié dans un vrai navigateur. Décidé par : coordination (travail d'un sous-agent
  Opus, relu).
- **D-62 — 12/11/2026 — Détecteur `cdp` V2 : retrait de `debugger_instant` et `no_first_input` (révise D-45,
  point 1).** Les deux signaux se déclenchent chez tout le monde par construction. `debugger_instant`
  chronomètre une instruction `debugger`, sans effet quand les outils de développement sont fermés : 0 ms
  dans 803 relevés sur 835 (campagnes 90, 93, 94, les trois moteurs), les 32 autres valant un tic d'horloge ;
  seul un humain aux outils ouverts y échappe. `no_first_input` lit l'entrée first-input au moment du relevé,
  environ 0,2 s après le chargement, avant tout clic possible ; l'absence d'interaction reste jugée par
  `comportement`, sur le relevé de fin de page. Les cinq autres signaux gardent leur poids ; aucun ne s'est
  déclenché sur les trois moteurs (0 sur 835). Le relevé d'`observateur.js` est inchangé. Pourquoi : dans la
  campagne 90, `cdp` arrêtait les trois moteurs à l'identique aux niveaux 04 à 07, et aurait arrêté les
  humains de même ; étape 1.7 du plan, un détecteur gardé classe au plus 1 humain sur 10. Conséquence : au
  niveau 04, l'Arena n'a plus de signal contre NOEZIA (campagne 94 : 15/15) ; les témoins restent arrêtés par
  les détecteurs d'origine. À confirmer par le rejeu des sessions humaines : aucune ne doit porter de signal
  `cdp`. Fusionné avant ces sessions parce que le défaut tient au fonctionnement du navigateur, pas à une
  supposition. Décidé par : coordination (analyse d'un sous-agent Opus, relue).
- **D-63 — 12/11/2026 — `device_memory_invalide` admet 16 et 32 Go.** La règle de `coherence-profonde`
  n'admettait que 8 Go au plus. Chrome a relevé ses paliers en 2026 (2, 4, 8, 16, 32 hors Android) et le
  Chromium 156 piloté sans réglage annonce 32 sur ce poste (campagne 94) : tout humain sur une machine de 16
  Go ou plus était classé. Détecteur en 1.1. Décidé par : coordination.
- **D-64 — 12/11/2026 — `correlation-session` 1.1 : un seul signal par fait, des libellés justes, un débit sur
  60 minutes (révise le calcul de D-48).** ~~Le détecteur lit toujours les deux comptes de `empreintes_vues`
  (profil, canvas ; types et historique inchangés). Il n'émet plus qu'un signal de comptage, sur le plus grand
  des deux, et qu'un signal de débit. Avant, le profil et le canvas d'une même session donnaient chacun leur
  signal : 5 sessions identiques faisaient 0,7 + 0,7, « automatisé » à elles seules. Les libellés disent ce
  qui est compté (« profil vu dans N sessions de la base ») ; « rotation de fingerprint massive » désignait
  une empreinte stable. Le débit compte, pour chaque hash, les sessions commencées dans les 60 dernières
  minutes, au lieu de diviser le compte par la vie du hash (0 sous une minute, 40 par heure pour deux
  sessions à 3 minutes).~~ **(Règle 1.1 remplacée par D-89 ; l'empreinte combinée écartée ci-dessous est
  celle que D-89 retient.)** Seuils et poids inchangés. Écarté : une empreinte combinée profil + canvas, proposée
  par l'analyse puis signalée par la relecture de sécurité (un moteur qui bruite son canvas à chaque session
  n'aurait plus jamais été revu). Pourquoi : aux campagnes 93 et 94, NOEZIA était classé au niveau 07 dès le
  3ᵉ passage par un débit faux (`docs/recherche/correlation-entre-sessions-2026-11-12.md`). Effet aux niveaux
  06 et 07 : de 5 à 9 sessions, le détecteur seul dit « indéterminé » ; la session reste bloquée par le
  composite (0,7 × 1,5), sous le motif `composite` ; dès 10, rien ne change. Limites : ~~la table ne garde que
  10 jetons par hash, donc le débit ne décide plus seul~~ (table remplacée par D-89 : une ligne par visite, comptes exacts). Inchangé, et à reprendre avec la mémoire des
  visiteurs du palier 2 : un humain qui revient cinq fois reste classé ; le canvas seul, commun aux machines
  du même modèle, classe encore. Décidé par : coordination (travail d'un sous-agent Opus, repris et relu).
- **D-65 — 12/11/2026 — Site public, seconde relecture : journal, limites par adresse, `debugger`, nettoyage
  des messages (complète D-57 et D-62).** Une relecture indépendante du code fusionné le 12/11 a trouvé quatre
  défauts. (1) Le journal tournant (`logs/shadowlab.jsonl`, horodaté à la milliseconde, hors purge) écrivait
  `POST /contact 303` et « message de contact reçu » : rapprochées de `observations_http.received_at` d'une
  session en cours, ces lignes reliaient un message à sa session, contre D-57. Choix : aucune ligne pour
  `/contact…` ni pour ce que le navigateur charge avec chaque page (`/lab/static/…`, `/favicon.ico`), sans
  quoi une feuille de style sans page notée trahissait une page de contact ; l'avis au responsable passe par
  la sortie standard, seulement si c'est un terminal. (2) À 3 messages par heure, une adresse seule épuisait
  le plafond du jour en 10 heures et remplissait la boîte en 17 jours. Choix : 5 messages par adresse et par
  24 heures glissantes, en mémoire (5 < 30 ; 5 × 90 = 450 < 500) ; ~~toutes les limites par adresse comptent un
  /64 IPv6 pour une adresse~~ (remplacé par D-77 : un /56) ; commande `shadowlab public effacer-message tous`. (3) Sur une page qui porte
  `sl-sans-tiers`, `observateur.js` n'exécute plus `debugger` (elle arrêtait la page d'un visiteur aux outils
  de développement ouverts) et ne lit plus first-input : depuis D-62 aucun détecteur ne les lit ; le labo
  relève comme avant ; texte d'information en version 2026-11-12.5. (4) Nettoyage des messages : la liste
  blanche est gardée (`str.isprintable()` et deux liants) ; une liste noire essayée puis écartée par la
  relecture de sécurité laissait passer des caractères invisibles. Prix accepté : un emoji plus récent que
  la table Unicode de Python disparaît, un drapeau à balises perd ses balises. Limites : six adresses ferment
  encore le formulaire pour la journée (parade : limitation de débit au mandataire) ; sous systemd, plus
  d'avis à l'écran. Décidé par : coordination (travail d'un sous-agent Opus, relu).
- **D-66 — 12/11/2026 — Arena : quatre règles qui classaient tout vrai Chrome ne jugent plus que ce qu'elles
  peuvent voir (`headless`, `chrome-apis`, `polices`, `connection-dynamic` en 1.1).** Mesuré dans l'essai 96
  et la campagne 97 : Google Chrome 156 avec son interface, piloté sans aucune réécriture, passe les niveaux
  01 à 03 (15 sur 15) mais est arrêté à chaque passage du niveau 04 au niveau 07 (06 et 07 sans corrélation ;
  120 passages sur 120, campagne 97) par le score composite (1,03 aux niveaux 04 et 05, 1,31 aux 06 et 07).
  Les quatre signaux en cause, un humain avec le même Chrome les déclencherait :
  `voices_vide` (la liste des voix était lue avant que Chrome l'ait chargée) ; `runtime_incomplet` (l'Arena
  exigeait `chrome.runtime`, absent d'une page ordinaire) ; `polices_os_manquantes` (comparée au seul
  `monospace`, Menlo, la police à chasse fixe par défaut, paraissait absente) ; `rtt_zero` (sur l'Arena
  locale la latence estimée vaut 0 ou 50 selon les passages, et 0 chez les témoins aussi). Choix : le relevé
  appelle `getVoices()` dès le chargement, attend `voiceschanged` au plus 250 ms et envoie `voices_evenement`
  et `voices_attente_ms` ; `voices_vide` ne juge qu'une liste qui a eu le temps d'arriver ;
  `runtime_incomplet` ne juge qu'un `chrome.runtime` présent sans `PlatformOs` (imitation partielle) ; les
  polices sont comparées à trois familles génériques, et une absence n'est jugée que sur un tel relevé ;
  `rtt_zero` est retiré. Un relevé plus ancien ne fait conclure ni `voices_vide` ni `polices_os_manquantes`.
  Seuils et poids inchangés ; texte d'information du site public en version 2026-11-12.6. Pourquoi : plan
  § 1 (« des détecteurs qui attrapent tout le monde ») et étape 1.7. Aucun de ces signaux ne séparait les
  témoins du vrai Chrome ; `polices_os_manquantes` ne touchait que lui. Prévision rejouée sur les passages
  finis à 15 h (niveaux 03 à 06 ; le 07 est extrapolé), à confirmer par la campagne de contrôle
  `configs/experiments/controle-vrai-chrome.yaml` : composite du vrai Chrome à 0 ; les témoins restent classés
  par `regles-http` au niveau 02 et par 4 à 6 détecteurs seuls du 03 au 07. Limites : durée de chargement des
  voix non mesurée dans un vrai Chrome ; un Chrome sous Linux sans voix installées reste signalé ; la
  référence est un Chrome piloté, pas encore une session humaine ; `meta-composite` (« session trop
  propre », D-45) se déclenche chez tout le monde sans peser dans aucune décision : à revoir avec Ethan.
  Décidé par : coordination (travail d'un sous-agent Opus, relu).
- **D-67 — 12/11/2026 — Site public, troisième relecture : le journal ne garde que les erreurs, une page de
  contact ne laisse aucune trace dans une session (complète D-57 et D-65).** Une relecture de sécurité
  indépendante, avant la mise en ligne, a trouvé des écarts entre ce que la page d'information promet et ce que
  l'application fait. Choix : (1) le journal de l'application ne garde plus que les réponses de code 400 ou
  plus (méthode, chemin, code ; ni adresse, ni jeton, ni identifiant de session) ; une requête réussie n'écrit
  rien. Avant, chaque page vue était datée à la milliseconde dans un fichier que ni la suppression d'une
  session ni la purge ne touchaient, alors que la page dit « rien n'est enregistré ». (2) Les pages de contact
  ne chargent plus rien sous `/lab/` (feuille de style servie sous `/contact/style.css`) et ne mènent qu'à `/`
  ou `/contact…` : la base d'une session en cours ne note plus ni l'ouverture du formulaire ni l'envoi (avant,
  une feuille de style au référent réduit à « / » les datait). (3) Limites par adresse : les empreintes
  expirées sortent de la mémoire au plus une minute après la première requête qui suit leur délai ; une table
  pleine n'est plus remise à zéro (l'adresse inconnue est refusée) ; un en-tête d'adresse absent est signalé
  une fois au journal. (4) Le dossier de la base est en 700 et ses fichiers en 600 dès leur création, par
  l'application elle-même. (5) L'application publique ne charge du fichier `.env` que ses propres variables
  (`SHADOWLAB_PUBLIC_*`, `SHADOWLAB_VITRINE_*`, `SHADOWLAB_SORTIES`) : les clés du laboratoire n'entrent pas
  dans un processus exposé. (6) Le journal de `cloudflared` est filtré avant écriture (adresses réduites à
  l'hôte, chaînes de requête et jetons masqués). (7) Plus de promesse d'écrasement physique : `secure_delete`
  vide les pages dans la base, mais ni le journal de SQLite, ni le disque, ni les sauvegardes ne sont
  garantis ; chiffrement du disque et exclusion de `outputs/` des sauvegardes reviennent au responsable.
  (8) Les messages de contact sont purgés le jour limite compris (ils vivaient un jour de trop). Texte
  d'information en version 2026-11-12.7 : journal des erreurs, empreinte d'adresse en mémoire vive, délai réel
  de l'effacement automatique. Limites acceptées, écrites dans `docs/site-public.md` : le responsable présent
  devant l'écran voit l'heure d'arrivée d'un message ; quelques adresses suffisent à épuiser le plafond du jour
  du formulaire ; quiconque a le lien peut ouvrir une session par script, donc une session publique ne prouve
  pas qu'un humain était là (question ouverte pour Ethan) ; le filtre du journal de `cloudflared` n'a jamais
  été vérifié avec un vrai tunnel. Décidé par : coordination (relecture d'un sous-agent, corrections d'un
  autre, relues).
- **D-68 — 12/11/2026 — Numéro d'expérience jamais réutilisé, passages orphelins adoptés.** Constat : la base
  du labo contenait 18 passages du 08/11 rattachés à une expérience n° 99 qui n'existe pas (tous `en_cours`,
  moteur playwright, niveaux 05 et 06). `experiments.id` est un `INTEGER PRIMARY KEY` sans `AUTOINCREMENT` :
  la campagne suivante (ou les sessions humaines du soir, qui créent leur expérience `sessions-manuelles`)
  aurait pris le n° 99 et hérité de ces passages. Choix : tout `INSERT INTO experiments` prend
  `db.PROCHAIN_ID_EXPERIENCE`, au-dessus de la plus grande expérience et du plus grand `runs.experiment_id` ;
  la migration 9 crée une expérience `orpheline_<n°>` (statut `interrompu` s'il reste des passages `en_cours`,
  sinon `termine_incomplet`, date du premier passage) pour chaque numéro de passages sans expérience, sans
  rien supprimer. Pourquoi : `AUTOINCREMENT` aurait exigé de reconstruire la table ; l'adoption garde les
  données. Sauvegarde avant migration : `outputs/shadowlab-avant-migration9-2026-11-12.sqlite3.gz`. Limites :
  la cause reste une hypothèse (une connexion SQLite sans clés étrangères, hors du lanceur ; le code
  applicatif active les clés étrangères et supprime en cascade) ; `/progression`, `/matrice` et `/reprendre`
  de l'API renvoient une erreur pour une expérience dont la configuration n'est pas une campagne (déjà vrai
  pour `sessions-manuelles`) ; `reports.supprimer` laisse des lignes dans `decisions`, `observations_tls` et
  `empreintes_vues` ; rien n'empêche de supprimer une campagne en cours. Décidé par : coordination.
- **D-69 — 12/11/2026 — Le WAF de l'Arena n'applique plus ses règles d'injection SQL aux jetons de CAPTCHA
  tiers.** Constat : dans la campagne 100, le passage 34119 (niveau 06 sans corrélation, `static_html`) a été
  bloqué par le WAF sur `POST /lab/recaptcha/verifier`, règle CRS 942210 (« Detects chained SQL injection
  attempts 1/2 »), à cause de la valeur du jeton du reCAPTCHA en clés de test. Choix : la règle 1015 de
  `docker/arena/coraza/main.go` retire, sur `/lab/turnstile/verifier` et `/lab/recaptcha/verifier` seulement,
  toutes les règles de l'étiquette `attack-sqli` pour `ARGS:g-recaptcha-response` et
  `ARGS:cf-turnstile-response`. Tout autre champ de ces deux adresses, et les mêmes champs sur une autre
  adresse (`/lab/connexion`), restent inspectés. La règle 1014 (retrait de 942432, nom du champ) est gardée.
  Pourquoi : le jeton est une suite aléatoire dont le nom de champ est imposé par le fournisseur, donc un
  humain est bloqué comme un robot. La règle 942210 se déclenche sur « chiffre, or ou and, chiffres, tiret » :
  environ un jeton sur mille d'après un essai sur 5 000 jetons simulés. La règle 942440 (« -- ») bloquerait
  bien plus souvent un vrai jeton Turnstile, qui contient des points : environ 16 % des jetons simulés. Preuve
  : campagne 100, passage 34119 ; sur la branche `arena-waf-jetons`, `tests/test_arena_waf.py` avait 6 tests
  en échec contre le pare-feu en service, il en a 21 verts après reconstruction de l'image (18 h 07). Limites
  : les simulations sont des expressions régulières rejouées hors du WAF, pas le WAF lui-même ; les familles
  XSS, commandes et fichiers n'ont pas été étudiées ; la base compte 1 blocage sur 121 vérifications de
  CAPTCHA de la campagne 100 (61 reCAPTCHA, 60 Turnstile), soit plus que le calcul ne le prévoit : écart non
  expliqué. Le passage 34119 reste compté comme échec dans la campagne 100. Décidé par : coordination.
- **D-70 — 12/11/2026 — Commande de récolte générale : une recette par site, fusionnée dans la branche de
  travail.** Demande d'Ethan (12/11) : « je veux que tu me parles en concret à chaque fois avec le niveau de
  notre objectif » ; « car après le scraper j'en aurais besoin pour scraper des sites justement ». Premiers
  sites visés : « annonce immobilier et site de rallye », « avec le suivi des châssis etc., les spectacles
  [comprendre : spéciales], tout ». Accord de fusion donné à 21 h 40 : « Oui, fusionne ». Choix : une commande
  `shadowlab recolte lancer | reprendre | etat | essayer | noter` (`commande_recolte.py`) qui récolte un site
  entier à partir d'une **recette** YAML par site (`configs/recettes/`, lue par `engines/noezia/recettes.py`),
  avec un parcours, un état SQLite qui permet de reprendre, une notation générale (pages, enregistrements,
  champs), une récolte incrémentale (`revisiter`, `nouveautes.jsonl`), deux moteurs (`http`, `navigateur`) et
  un second site factice à contenu connu, des résultats de rallye (`/lab/rallye`). Branche `recolte-integration`
  fusionnée dans `niveau-authentifie-perimetre` (commit `b1a40ed`, 49 fichiers, environ 12 300 lignes
  ajoutées) ; rien sur `master`. Décisions de réalisation : (1) `robots.txt` respecté par défaut ;
  `--ignorer-robots` est explicite et écrit dans `resume.json`. (2) Lecteur de `robots.txt` maison, sans
  expression régulière (un fichier hostile ne peut pas bloquer la récolte) et sans nouvelle dépendance.
  (3) Une recette qui vise un site qui n'est pas à nous exige une ligne `autorisation` ; D-30 reste en
  vigueur. (4) Une redirection vers un autre hôte n'est jamais suivie : zéro requête vers cet hôte. (5) Arrêt
  au premier signe d'alerte ; jamais de clic sur un défi d'un site tiers ; aucun solveur de CAPTCHA. (6) CSV au
  format d'Excel en France (point-virgule, BOM, virgule décimale) ; le JSON Lines reste la donnée exacte.
  (7) Photos : les adresses seulement. (8) Extraction adaptative jamais par défaut. (9) Une valeur douteuse
  donne une valeur vide et une alerte, jamais une valeur fausse en silence. Pourquoi : le moteur doit devenir
  un outil qu'Ethan utilise sur de vrais sites (ligne « Livrable » de l'objectif, `docs/PLAN.md` § 1), et une
  commande générale par recette évite d'écrire un programme par site. Ordre de travail : la commande passe
  avant les calibrages restants du labo ; l'étape 1.9 et les paliers 2 à 4 du plan ne sont pas retirés.
  Mesures (commande réelle, site du labo sur un port à part) : moteur `http`, vitrine à 500 annonces : 525
  pages, 500 annonces, 7 000 champs sur 7 000, 0,8 s ; site de rallye : 427 pages, 4 569 enregistrements,
  34 410 champs sur 34 410. Récolte incrémentale, vitrine à 45 puis 50 annonces : 8 pages lues, 45 évitées,
  5 nouveautés, notation 53 pages sur 53. Moteur `navigateur` (vrai Chrome, identité native, niveau 01) :
  vitrine à 45 annonces, 48 pages sur 48 en 5 min 50 s. Essai de campagne (`recolte-generale-essai.yaml`,
  base à part, campagne n° 1 de cette base) : 4 passages sur 4 à 100 %, dont le site de rallye à 3 rallyes par
  le navigateur (85 pages en 612 s). Campagne de preuve complète (`recolte-generale.yaml`) lancée à 21 h 08
  dans la même base à part, arrêtée à 21 h 43 pour la fusion après un seul passage fini (vitrine à 150
  annonces par le navigateur : réussi, 1 164 s) ; à relancer dans la base du labo. Méthode : briques écrites
  dans des branches à part, chaque commit de tests vu en échec avant son code ; relecture indépendante (six
  défauts corrigés) ; relecture de sécurité automatique (lecteur de `robots.txt` réécrit) ; recette du site de
  rallye écrite par un agent qui n'avait lu ni le code du site ni l'exemple du document (première version en
  3 minutes environ, 100 % après correction des noms de champs). Avant la fusion, la branche avait 1 205 tests
  rapides verts ; suite complète relancée après la fusion, résultat au journal suivant. **Limites, non
  prouvé** : aucun vrai site, aucune vraie protection ; la commande n'a été jugée par aucun niveau protégé de
  l'Arena (elle vise le site en direct, donc le niveau 01 ; le chemin par l'Arena est écrit dans les
  scénarios de campagne, jamais lancé) ; le mode navigateur n'a tourné qu'au niveau 01 ; en mode navigateur,
  Chrome charge de lui-même les sous-ressources d'autres hôtes et la coupure d'une redirection vers un autre
  hôte n'a pas été vérifiée dans un vrai Chrome ; `attendre` (bloc chargé en JavaScript) n'est pas branché ;
  un champ adaptatif sans signature mémorisée échoue sans alerte ; le rythme « prudent » n'a jamais tourné en
  temps réel ; le CSV n'a pas été ouvert dans Excel ; la campagne de preuve complète n'a pas fini. Décidé par :
  Ethan (accord de fusion), coordination (choix de réalisation).
- **D-71 — 13/11/2026 — La limite de débit de l'Arena ne compte plus les photos qu'une page charge.** Constat :
  campagne 103 (`configs/experiments/recolte-arena.yaml`, la récolte générale jugée par l'Arena, vitrine à 20
  annonces). Le moteur en identité native passe les niveaux 02 et 03 (3 sur 3 chacun) puis est arrêté aux
  niveaux 04, 05 et 06 sans corrélation (0 sur 3 chacun), toujours pour la même raison : « débit dépassé
  (429) ». Lu requête par requête : la page de liste charge 20 photos en moins d'une seconde, et `limit_req`
  de Nginx comptait ces photos avec la rafale du niveau (15, 8, 4) ; le premier refus tombe sur la photo 18 au
  niveau 04, la photo 9 au 05, la photo 4 au 06. Le défi JavaScript et les CAPTCHA en clés de test étaient
  déjà validés. Tout navigateur charge ces images en parallèle : un humain qui ouvre cette page aurait été
  classé « bloqué » aux niveaux 04 à 07. Le défaut n'était jamais apparu parce que les scénarios habituels
  n'utilisent que des pages légères ; `/lab/static` était déjà hors limite, pas les photos. Choix :
  `/lab/vitrine/photos/` rejoint `/lab/static/` dans une `location` Nginx sans `limit_req` (liste unique
  `CHEMINS_STATIQUES`, `arena/profils.py`) ; les pages, les envois, la collecte du parcours et les
  vérifications de CAPTCHA restent comptés ; débits et rafales par niveau inchangés. Pourquoi : une limite de
  débit vise les pages et les appels, pas les fichiers qu'une page charge d'elle-même ; un détecteur n'est
  valide que s'il laisse passer les humains (plan § 8, règle 3). Preuve : 2 tests rapides et 2 tests contre le
  Nginx de la pile vus en échec avant, 46 verts après `shadowlab arena appliquer` (sans reconstruction
  d'image). Limites : un client peut télécharger les photos sans limite (le WAF les voit toujours) ; tout
  nouveau fichier chargé par une page doit être ajouté à la liste ; les appels `collecte`, `verdict`, `defi` et
  `captcha` étaient déjà hors limite avant cette décision et le restent ; aucun humain n'a encore été mesuré
  derrière la limite de débit (le rejeu des sessions humaines ne la rejoue pas) ; la campagne 103 est à
  refaire après la correction. Décidé par : coordination (travail d'un sous-agent, relu).

- **D-72 — 13/11/2026 — La porte d'entrée de la récolte reconnaît un défi déjà franchi pendant la lecture.**
  Constat (campagne 104, après D-71) : la récolte en navigateur s'arrêtait à la première page aux niveaux 04 à
  06 de l'Arena, sur « statut 403 », avec 0 page lue, alors que le navigateur avait franchi l'entrée et reçu
  la vraie page en 200. Cause : après une navigation, le moteur rend le statut de la première réponse (la
  page de défi, 403) avec l'adresse et le contenu de la page actuelle ; la porte d'entrée ne reconnaissait
  qu'un défi encore affiché ; la recette d'un passage par l'Arena n'en déclarait pas. Le même défaut aurait
  arrêté à tort une récolte sur un site tiers dont le défi se valide seul plus vite que le temps de lecture.
  Décision : à la première page d'une passe, si la recette déclare `porte_entree`, qu'aucun défi n'est dans
  la page lue et que le premier statut est un statut d'alerte, la commande regarde la page sur place (aucune
  requête, aucune attente, aucune action). Page actuelle en 2xx et sans défi : la porte est franchie, comptée
  à part dans `resume.json` (`defi: "statut 403"`, la nature du défi n'étant plus connue, `franchie: true`,
  `attente_s: 0.0`), et la passe continue. La recette d'un passage par l'Arena déclare une porte d'entrée
  (15 s) quand son fichier n'en a pas. Ce qui ne change pas : sans porte déclarée, un 403 à la première page
  arrête ; en cours de passe, un 403 arrête toujours, même si la page est devenue lisible ; la commande ne
  clique sur aucun défi d'un site tiers et ne résout rien (seul le moteur du labo passe les défis du labo).
  Preuve : test vu en échec avant (commit `82694b9`), vert après (`7af7575`, fusion `1c59d55`), 1 278 tests
  verts ; campagne 105 : 15 passages sur 15 du niveau 02 au niveau 06 sans corrélation (0 sur 3 aux niveaux
  04 à 06 à la campagne 104). Limites : le critère est l'état actuel de la page, pas la preuve qu'un défi a
  existé (une page 403 devenue lisible seule à la première visite passe aussi, uniquement si la recette a
  déclaré une porte) ; le statut rendu par le moteur reste celui de la première réponse, la porte d'entrée
  est le seul endroit qui regarde l'état actuel ; jamais essayé sur un vrai défi d'un fournisseur. Décidé
  par : coordination (travail d'un sous-agent, relu).

- **D-73 — 13/11/2026 — L'Arena lie les cookies de défi au JA4 sans `pre_shared_key`.** Constat (campagne
  106, parcours de 427 pages) : au niveau 06 sans corrélation, l'Arena a redemandé le défi JavaScript et les
  deux CAPTCHA à la 10ᵉ page d'une session qui les avait déjà passés ; la sentinelle a arrêté la récolte.
  Cause, lue dans la base : aux niveaux 05 à 07 (`lier_tls`), le cookie de réussite était lié au JA4 exact.
  Or un vrai Chrome qui reprend sa session TLS 1.3 envoie une extension de plus, `pre_shared_key` (0029) :
  son JA4 passe de `t13d1517h2_8daaf6152771_cb7bf5808d99` à `t13d1518h2_8daaf6152771_e2d80978ab2e`, rien
  d'autre ne change. Dès qu'une page part sur une connexion reprise, le cookie n'est plus reconnu. Un humain
  avec un vrai Chrome serait redéfié de la même façon : faux positif de l'Arena (règle 3 du plan).
  Décision : le frontal calcule une empreinte de liaison, le JA4 sans l'extension 41, la transmet au site
  dans l'en-tête interne `X-ShadowLab-Liaison`, couvert par le sceau ; les cookies de défi, de CAPTCHA et de
  connexion y sont liés. Le JA4 complet reste enregistré et vu par les détecteurs. Seule l'extension 41 est
  écartée : c'est la seule mesurée. Un cookie reste refusé à un client d'empreinte différente.
  Preuve : tests vus en échec avant (commit `3b96d79`), verts après (`d9bcb3d`, fusion `d4e6d4e`), 1 285
  tests verts ; sur les trois vrais ClientHello de la campagne 106, la liaison est la même ; campagne 107 :
  au niveau 06 sans corrélation, une page demandée sur une connexion reprise ne déclenche plus de défi, et
  les 427 pages sont lues (9 à la campagne 106). Un test verrouille aussi que le frontal écarte tout en-tête
  `X-ShadowLab-*` envoyé par le client (c'était déjà le cas, sans test). Limites : `early_data` (002a), que
  Chrome n'envoie pas par défaut, n'est ni mesurée ni écartée ; un seul Chrome, sur macOS ; aucun humain en
  base pour confirmer ; le niveau 05 avait le même défaut et n'était passé à la campagne 106 que parce que la
  connexion reprise n'avait porté aucune page. Décidé par : coordination (travail d'un sous-agent, relu).

- **D-74 — 13/11/2026 — Le mouvement de souris du moteur garde un tremblement visible au pixel.** Constat
  (campagne 108) : au niveau 05, deux sessions de récolte sur 35 bloquées par le détecteur de comportement,
  signal `trajectoire_lineaire` (moyenne des angles entre segments de souris sous 0,08 rad). Sur environ 4 400
  pages lues par le moteur (campagnes 105 à 108), la moyenne passe sous ce seuil environ une fois sur 1 000,
  toujours sur un mouvement court, avec beaucoup d'angles exactement nuls. Cause, établie par un banc de
  mesure sans navigateur (`tests/test_souris_trajectoire.py`) qui rejoue le code réel du moteur et le calcul
  de `observateur.js` : le bruit du mouvement (écart-type de 0,15 à 0,7 px) disparaît quand la position est
  arrondie au pixel entier, et la page reçoit une ligne lisse. Le banc retrouve la base : 0,13 % des pages
  sous 0,08 (base : 0,09 %), 1,5 % sous 0,15 (base : 1,4 %), mêmes quantiles.
  Décision : `comportement/souris.py` ajoute à la trajectoire un tremblement de la main (processus à bande
  étroite, 8 à 12 Hz, 1,5 px au repos plus une part du pas parcouru), nul au départ, la cible restant exacte.
  On corrige le moteur ; le détecteur, l'observateur et les profils de l'Arena ne changent pas.
  Preuve : test vu en échec avant (commit `88358ca` : 295 pages sur 20 869 sous 0,15, dont 27 sous 0,08), vert
  après (`34f0ae4`, fusion `5e87a54`) ; dans le banc, sur 20 900 pages : minimum 0,196 rad (0,062 avant),
  médiane 0,94 (0,72 avant), durée d'une page inchangée (5,3 s) ; aucune autre règle de souris de
  `detection.py` ne se déclenche sur 1 000 sessions simulées. Limites : pas encore mesuré dans un vrai
  Chrome (campagne de contrôle à faire) ; toute la distribution monte, la souris bouge plus qu'avant ;
  aucune session humaine pour dire si c'est plus proche d'une vraie main ; le banc ne reproduit ni la cadence
  d'images de Chrome ni les gestes vers un élément. Décidé par : coordination (travail d'un sous-agent Opus,
  coupé avant son rapport, relu et remesuré).
  **Ajout du 14/11, mesure dans un vrai Chrome (campagne 109, même fichier que la 108)** : 2 015 pages jugées,
  minimum 0,261 rad, aucune sous 0,15 (30 sur 1 997 à la campagne 108, dont 3 sous 0,08) ; niveau 05 à 35 sur 35
  (32 sur 35 avant) ; durées inchangées. La limite « pas encore mesuré dans un vrai Chrome » est levée ; les
  autres restent.

- **D-75 — 14/11/2026 — Site public, version « étude » : deux langues, accueil « Humain ou robot ? », but élargi,
  fréquentation (cadrage `docs/recherche/site-public-communaute-2026-11-13.md`, v2 ; complète D-55, D-57, D-65 et
  D-67).** Ethan veut mettre le site en ligne lui-même pour une communauté, en français et en anglais, et voir
  combien de gens viennent. Choix : (1) **Langues**, sans cookie de plus (toujours trois) : préfixe de l'adresse
  (`/fr`, `/en`), sinon langue notée avec l'accord de la session (champ caché du formulaire, gardé dans
  `protection_config` avec la version du texte), sinon `Accept-Language`, sinon français. Un dictionnaire de
  textes par langue (`public/textes.py`), la structure HTML écrite une seule fois (`public/pages.py`) : la notice
  est la même phrase pour phrase, et la liste des données reste tirée d'`observateur.js` clé par clé, dans les
  deux langues. Seuls l'accueil et la notice ont une adresse par langue ; les autres pages suivent la session,
  puis le navigateur. (2) **Accueil** sous `/`, `/fr`, `/en` (textes du cadrage, trois étapes, résumé de ce qui est
  relevé, Mosaïk Démo en grand, Habitat Démo en lien discret, case d'accord avec la notice juste à côté) ; notice
  complète sous `/fr/information`, `/en/information` et `/information`, sans formulaire ; « Commencer » mène au fil
  du réseau social. Le résumé de l'accueil est à un seul endroit (`textes.RESUME_RELEVE`) ~~et dit ce que relève
  aujourd'hui `observateur.js` (des nombres et des délais, ni la position de la souris ni ce qui est tapé) ; la
  phrase du cadrage sur les « mouvements de la souris » attend le second script de relevé.~~ Fin de phrase
  remplacée par D-76. Feuille minimale
  `public/static/public.css`, politique de sécurité inchangée. (3) **But annoncé** : mesurer et améliorer nos
  détecteurs de robots (avant : mesurer) ; les données ne servent à rien d'autre. (4) **Fréquentation** : une table
  `frequentation` dans la base publique, créée par l'application (pas une migration du labo) : le jour UTC et
  trois nombres, chargements de l'accueil (GET), sessions commencées, sessions terminées ; ni adresse, ni
  identifiant, ni navigateur, ni heure. Hors des sessions : ni la suppression ni la purge n'y touchent, gardée sans
  limite de durée. Base pleine, rien ne s'écrit ; base en panne, l'accueil reste servi sans compteur. Commande
  `shadowlab public frequentation` ; l'accueil affiche le total des sessions terminées. La notice dit ce compte
  (section « Fréquentation ») et ne dit plus « rien n'est relevé » pour une visite sans participer, ni « ni mesure
  d'audience ». Au passage, les lignes `navigateur` et `apis` de la liste des données nomment les sous-champs
  qu'elles taisaient (cookies permis, lecteur PDF, types de fichiers, mobile ou non, objet propre à Chrome,
  périphériques HID). Texte d'information en version 2026-11-14.4. Limites : le total affiché compte aussi une session
  terminée puis supprimée ; tout chargement de l'accueil compte, robots et rechargements compris ; le bandeau du
  réseau social (`social.T`, hors de ce travail) parle encore de « la page d'information ». Le plafond de sessions
  ouvertes par jour, d'abord une constante de `Limites`, est devenu le réglage `SHADOWLAB_PUBLIC_SESSIONS_PAR_JOUR`
  (40 par défaut, ramené entre 1 et 5 000) : il fixe le jour où un abus peut remplir la base, c'est le plafond de
  2 Gio qui protège le disque (`docs/site-public.md`, « Limites »). Décidé par : coordination.

- **D-76 — 14/11/2026 — Site public : relevé enrichi des gestes (`public/static/releve.js`, envoi `trace`), la
  promesse « ni la position de la souris » retirée (cadrage `docs/recherche/site-public-communaute-2026-11-13.md`,
  section « Relevé enrichi » ; complète D-75 et remplace sa phrase sur le résumé de l'accueil).** Pour faire le
  meilleur détecteur, l'étude relève désormais la façon de bouger et de taper, pas seulement des comptes et des
  délais. **Ajouté** : un second script, `releve.js`, servi par la seule application publique sous
  `/public/static/` (l'`observateur.js` du labo n'est pas modifié, son empreinte est verrouillée par un test),
  chargé seulement pendant une session, sur les pages des deux sites de démonstration (rendu du réseau social,
  bandeau de la vitrine), par une balise `<script defer>`, sans script dans la page. Il envoie à `/lab/collecte`
  (même jeton, même forme) une nature nouvelle, `trace`, faite seulement de nombres entiers (millisecondes depuis
  l'arrivée sur la page, écarts d'une ligne à la suivante) : trajectoire de la souris (30 points par seconde au
  plus, 9 000 par page), clics et appuis (position, instant, bouton, sorte d'élément dans une liste fermée : lien,
  bouton, image, zone de texte, autre ; jamais son texte, son adresse ni son identifiant ; 600 par page),
  défilement et molette (4 500 par page chacun), rythme du clavier (instant d'appui puis de relâche, dans une zone
  de texte ou non ; jamais la touche, son code ni le caractère ; 3 000 par page), gestes tactiles (position,
  instant, nombre de doigts, rayon et pression si le navigateur les donne ; 4 500 par page), passages au premier
  plan, focus de la fenêtre et redimensionnements (200 par page chacun), et le cadre (taille de la fenêtre et de
  la page, défilement, densité de pixels, sorte de pointeur). L'envoi part au départ de la page ou à son passage
  en arrière-plan (`sendBeacon`), et par morceaux quand une liste est pleine (60 envois par page au plus) ; ce qui
  dépasse un plafond est compté (`ecartes`), pas envoyé. Le serveur valide chaque trace strictement
  (`public/trace.py` : clés connues seulement, entiers bornés, listes bornées, page d'un des deux sites), la
  récrit en JSON compact et la compte à part de l'observateur (`envois_trace_par_session` = 1 000,
  `volume_trace_par_session` = 4 Mio) : elle n'use jamais les envois dont le rejeu a besoin. `requetes_par_session`
  passe de 3 000 à 4 000 (chaque morceau est une requête `/lab/collecte` notée). Une session au pire passe de
  16,9 Mo (mesuré le 12/11) à 25,2 Mo (calcul) ; la base de 2 Gio en tient 85 au lieu de 127 ; une session
  ordinaire de 10 minutes fait environ 1 Mo (estimation, aucun humain en base). **Reste exclu**, verrouillé par des
  tests qui lisent le script et par un banc sous Node qui piège ces lectures : la touche, son code et le texte
  tapé, le contenu, l'adresse ou l'identifiant d'un élément, le presse-papiers et la sélection, toute fonction qui
  demande une autorisation, tout cookie et tout stockage dans le navigateur, tout envoi ailleurs qu'à
  `/lab/collecte` du même site, tout relevé hors session. `rejeu.py` n'est pas modifié : il ignore les traces
  (test). **Notice** : elle décrit la trace clé par clé dans les deux langues (liste tirée du script, test) ;
  « jamais relevé » ne dit plus « ni la position de la souris », mais garde et renforce ni ce que vous tapez (ni le
  texte, ni les touches), ni l'adresse IP, ~~ni la localisation~~ (remplacé par D-77 : aucune géolocalisation, le
  fuseau horaire et les langues relevés), rien qui demande une autorisation ; elle dit qu'une
  façon de bouger la souris ou de taper peut aider à reconnaître une personne. Le résumé de l'accueil
  (`textes.RESUME_RELEVE`) prend le texte « Franchise » du cadrage. Le but annoncé ne change pas. Texte
  d'information en version 2026-11-14.5 ; aucune session publique n'existe encore, tout consentement se donne donc
  sous cette notice. Limites : la durée d'appui d'une touche n'est exacte que sans chevauchement de touches (deux
  listes, sans identité de touche) ; le rythme des touches peut, en théorie, renseigner sur ce qui est tapé ; la
  trace de la dernière page part au clic sur « Terminer », sans garantie d'arriver avant la fin de la session ; la
  note du réseau social sur le commentaire (« jamais envoyé ni enregistré ») reste vraie pour le texte, pas pour
  son rythme (texte non changé, hors de ce travail) ; rien n'est mesuré sur un humain. Décidé par : coordination, à
  la demande d'Ethan le 13/11 : « il faut qu'on prenne un maximum d'infos […] pour faire le meilleur détecteur ».

- **D-77 — 14/11/2026 — Site public, quatrième relecture indépendante avant l'annonce : quinze défauts prouvés par
  des essais, corrigés (complète D-65, D-67, D-75 et D-76 ; remplace le /64 de D-65 et « ni la localisation » de
  D-76).** Les quinze essais de `tests/test_public_relecture4.py`, en échec sur le code relu, passent sans avoir été
  modifiés ; les corrections au-delà sont prouvées par `tests/test_public_corrections4.py`, chaque test vu en échec
  avant. (B1) Une base pleine rouvre : le plafond mesure l'espace réellement occupé (pages utilisées plus journal
  WAL), plus la taille du fichier, que SQLite ne réduit jamais ; commande `shadowlab public sessions` (la plus
  grosse d'abord) pour repérer et supprimer une session abusive. (B2) Une session n'est comptée terminée que par la
  requête qui l'a close, une seule fois. (B3) L'accueil et le pied des pages de l'étude, sauf le contact, mènent aux
  crédits des photos ; `objets-03`, créditée au peintre d'une fresque et non au photographe, est retirée (93
  photos) ; la page de crédits dit « sous licence libre ou dans le domaine public ». (B4) Une adresse IPv6 compte
  pour son /56 (un abonné en reçoit souvent un entier). (B5) La documentation dit que le tunnel rapide perd
  « Ma session » à chaque relance. (C1) Une demi-paire UTF-16 dans un envoi donne 400, plus 500. (C2) Un envoi en
  vol n'écrit rien après une suppression (vérification dans l'écriture), et la purge et la suppression retirent
  les lignes orphelines. (C3) Un double clic sur « Commencer » n'ouvre qu'une session ; la seconde requête reçoit
  une redirection sans aucun cookie (une première version rendait les cookies de la session à qui présentait la
  même valeur anti-CSRF : fixation de session, relevée par une relecture de sécurité et reprise) ; la valeur
  anti-CSRF est renouvelée à l'ouverture. (C4) La notice ne dit plus « ni service de Cloudflare » et nomme
  Cloudflare dans le paragraphe sur le transit. (C5) Elle ne dit plus « aucun détecteur ne tourne », mais
  qu'aucune décision n'est prise pendant la visite. (C6) La limite par adresse lit la dernière ligne de l'en-tête.
  (C7) Le script du tunnel impose `SHADOWLAB_PUBLIC_HTTPS=1`. (Textes) L'accueil et la notice disent qu'aucune
  géolocalisation n'est relevée mais que le fuseau horaire et les langues le sont, et que le nombre de frappes dans
  une zone de texte en dit la longueur, la trajectoire de la souris ce sur quoi le regard s'est attardé ; texte
  d'information en version 2026-11-14.6. (Petites choses) Journal WAL remis à zéro après une suppression et une
  purge ; `HEAD` répond comme `GET`, sans corps, sans compter l'accueil ni écrire au journal. **Reste à la charge
  de l'exploitant avant une annonce** (`docs/site-public.md`, « Avant d'annoncer le site publiquement ») : un nom
  d'hôte stable (tunnel nommé sur un domaine) ; une règle de limitation de débit chez Cloudflare ; régler
  `SHADOWLAB_PUBLIC_SESSIONS_PAR_JOUR` ; surveiller `frequentation`, `sessions` et la taille de la base ; au premier
  lancement réel, comparer une fois le HTML servi par le tunnel au HTML local et vérifier que les photos arrivent à
  l'application (cache de Cloudflare). Limites : si le navigateur abandonne la première réponse d'un double clic, le
  visiteur arrive sur le fil sans session ; la notice nomme Cloudflare, donc une autre voie de mise en ligne demande
  de la changer ; rien n'a tourné avec un vrai tunnel. Décidé par : coordination, après la quatrième relecture
  indépendante.
  *Ajout du 14/11 :* un client qui coupe la connexion pendant l'envoi d'un corps (`ClientDisconnect`) ne laisse plus de
  trace d'erreur d'uvicorn : la garde arrête la requête sans réponse, sans écrire en base, sans compter ni user de
  quota, sans ligne au journal (`tests/test_public_deconnexion.py`).

- **D-78 — 14/11/2026 — Le détecteur de comportement ne compte plus les photos comme des pages.** Constat : campagne
  109, passage 34409, niveau 04 : le défi d'entrée se résout en 6 ms, la liste et ses 18 photos arrivent dans la même
  seconde, et à la deuxième photo le détecteur lit « 5,3 pages par seconde » (`rythme_soutenu`) et « moins de
  500 ms par page » (`pages_eclair`) : session bloquée, 18 refus. Un vrai Chrome sur une machine rapide serait arrêté
  pareil. Rejeu hors ligne des campagnes 108 et 109 (niveaux 04, 05, 06 sans corrélation, 35 passages chacun) :
  `rythme_soutenu` ou `pages_eclair` signalé sur 37 des 105 passages de la 108 (35 au niveau 04, 2 au 05) et sur 35
  des 105 de la 109 (tout le niveau 04) ; les 34 autres passages du 04 en 109 n'étaient pas arrêtés parce que le
  défi, plus lent, diluait le calcul : le résultat tenait au hasard. Sur le site public (sans défi d'entrée), le
  rejeu arrêtait la session sociale dès la première page aux niveaux 06 et 07. Cause : `Observations.documents`
  prenait pour une page tout chemin hors `CHEMINS_TECHNIQUES`, photos comprises ; et `pages_eclair`, qui moyenne la
  durée des relevés, lisait la durée de la page de défi (404 ms, quittée dès la vérification) comme une page lue.
  Même famille de défaut que D-71 (Nginx). Décision : (1) une seule définition, `detection.RESSOURCES_DE_PAGE`
  (fichiers statiques, `/lab/vitrine/photos/`, `/lab/social/photos/`, sans remontée `..`) ; `documents` ne garde que
  les pages, `requetes_de_page` toutes les requêtes de navigation, `ressources_de_page` ce que les pages chargent ;
  `ressources` (règle `sans_ressources`) reste les seuls fichiers statiques : une photo n'est ni du CSS ni du
  JavaScript ; un test aligne la liste sur `CHEMINS_STATIQUES` (D-71). (2) L'appel de données d'une fiche
  (`/lab/vitrine/api/`) reste une page : il rend du contenu, un client qui moissonne par là à toute vitesse doit
  rester vu. (3) `cookies_ignores` et les cookies de `proprietes` lisent toutes les requêtes de navigation (une page
  suivie de photos sans cookie reste signalée) ; `pages` de `proprietes` ne liste que les pages ; les règles qui lisent
  `documents[0]` (en-têtes de la première requête) sont inchangées. (4) `pages_eclair` ne conclut pas sur les seules
  pages de défi (relevé d'une page qui a posté `/lab/{defi,captcha,turnstile,recaptcha}/verifier` pendant sa vie) ;
  dès qu'une page lue existe, la moyenne reste faite sur tous les relevés, comme avant. (5) `gardien.protegee` est
  inchangée : une photo reste un moment de contrôle (défi, session bloquée), car une photo d'annonce porte du contenu
  (ville, titre) ; c'est le compte des pages qui est corrigé, pas la protection (essai d'abord fait, puis annulé après
  relecture). Seuils (4 pages par seconde, 500 ms), profils, moteur, `observateur.js` inchangés. Preuve : 10 tests
  vus en échec avant (cas mesuré aux instants réels du passage 34409, `documents`, `navigation_lineaire`,
  `proprietes`, définition unique, alignement D-71, les deux tests du réseau social sortis de `xfail`), témoins et
  contrôle des pages verts avant et après ; rejeu hors ligne après : 0 passage signalé sur 105 en 108, 0 sur 105 en
  109, 0 sur 30 en 105 ; les 15 passages du témoin `curl-cffi` de la 105 restent tous arrêtés par l'ensemble des
  détecteurs (15 sur 15 avant et après ; le détecteur de comportement ne les voit pas, ils n'exécutent pas de
  JavaScript). Limites : mesure hors ligne, à confirmer par campagne ; la page de défi reste dans la moyenne de
  `pages_eclair` quand une page lue existe (la retirer ferait signaler `pages_eclair` sur la première page lue, quittée
  en 55 ms par le moteur, à 34 passages sur 35 au niveau 05 et 35 sur 35 au 06 en 108 et 109, ce qui bloquerait le
  06 à seuil composite 0,5) ; cette quasi-fuite du moteur est un point faible latent, non corrigé ici ; la liste
  doit être complétée à tout nouveau fichier chargé par une page ; aucun humain mesuré. Décidé par : coordination
  (travail d'un sous-agent, relu).

  **Ajout du 15/11 (enquête sur la campagne 115)** : D-78 a aussi changé le sort du vrai Chrome sans comportement
  (`patchright-chrome-interface`) au niveau 05 : 5 sur 15 à la campagne 98, 15 sur 15 à la 115. Rejeu hors ligne des
  relevés des deux campagnes : avant D-78, 10 passages sur 15 étaient arrêtés par `comportement` (`aucune_interaction`
  + `pages_eclair`) sur le seul relevé de la page de défi (426 à 488 ms, aucun geste) ; les 5 réussis avaient un défi
  de 503 à 878 ms. Depuis D-78 la page de défi n'est plus une page lue : 0 arrêt. Ce témoin n'était donc pas arrêté
  pour son comportement. Conséquence : le niveau 05 ne sépare plus le moteur de ce témoin ; le niveau 06 le fait.
- **D-79 — 14/11/2026 — La page obtenue après un défi reçoit l'interaction humaine.** Constat (campagne 110, récolte de 21
  pages par session) : au niveau 05 (passage 34531) et au niveau 06 sans corrélation (passage 34510), la vraie page de
  liste vit 54 ms et 71 ms, sans mouvement ni défilement, alors que les pages de défi et les fiches durent 4 à 8 s ; au
  niveau 04 (passage 34528) la liste vit 5 394 ms avec 43 mouvements et 46 défilements. Cause : `DriverNoezia.navigate`
  faisait l'interaction (`_interaction_post_chargement`) sur la page arrivée, puis résolvait les défis ; l'interaction
  tombait donc sur la page de défi et la page finale, arrivée après le dernier défi, n'en recevait aucune (au niveau 04, le
  défi JavaScript recharge la page pendant l'interaction, d'où le bon résultat). `click()` avait le même défaut
  (`_interaction_post_clic_navigation` avant `_resoudre_defis`). Décision : après `_resoudre_defis`, si au moins un défi a
  été résolu pendant l'appel (`mesures.details["defis_resolus"]` a grandi), la page finale reçoit l'interaction
  (`_interaction_post_chargement` pour `navigate`, `_interaction_post_clic_navigation` pour `click`), si
  `interaction_post_page` est vrai. Sans défi : rien ne change, une seule interaction. Arena, `observateur.js`, parcours
  de récolte inchangés. Preuve : 6 tests sans navigateur (doubles qui notent l'ordre des appels), 2 vus en échec avant le
  code (navigation et clic à travers des défis), les 4 autres (sans défi, option coupée) verts avant et après ; suite
  rapide et lint verts. Limites : pas encore mesuré dans un vrai Chrome (à confirmer par campagne : durée et gestes de la
  page de liste aux niveaux 05 et 06) ; coût attendu de 5 à 8 s par session, une fois par traversée de défis, la
  première page n'étant plus quittée en quelques millisecondes ; un défi résolu sans que le compteur grandisse (échec de
  résolution) ne déclenche pas l'interaction ; `pages_eclair` n'est pas modifiée. Décidé par : coordination (travail d'un
  sous-agent, relu).
  **Ajout du 14/11, mesure dans un vrai Chrome (campagne 111, même fichier que la 110, 30 passages, 0 panne)** : la vraie
  page de liste dure 8 044 à 10 478 ms avec 38 à 67 mouvements de souris au niveau 05 (54 à 55 ms et aucun geste à la
  campagne 110) et 6 242 à 6 609 ms avec 47 à 52 mouvements au niveau 06 sans corrélation (55 à 71 ms et aucun geste), 3
  passages par niveau. Moteur navigateur 15 sur 15 du niveau 02 au niveau 06 sans corrélation, 280 champs sur 280, témoin
  `http` 0 sur 15 : rien n'a régressé. Coût mesuré : session médiane de 164 à 177 s au niveau 05, de 163 à 168 s au niveau
  06 sans corrélation. Limite : aucun détecteur de l'Arena ne voyait ce défaut, donc aucun taux de passage ne change.
- **D-80 — 14/11/2026 — Site public : accueil court, accord en un clic.** Constat : Ethan, en voyant le site en ligne
  sur son téléphone : « Trop long […] les gens font jamais le faire […] trop de truc ». L'accueil faisait cinq sections,
  demandait « 5 à 10 minutes », et le bouton de départ était tout en bas, derrière une case à cocher. Décision : un
  titre, une phrase, puis le formulaire d'accord tout de suite : la phrase de franchise (ce qui est relevé, jamais ce
  qui est tapé ni l'adresse IP, suppression en un clic), le lien vers la notice complète et un seul bouton « J'accepte
  et je commence » (`name="consentement" value="oui"` : le serveur exige toujours ce champ, rien n'y change) ; le
  consentement n'est plus une case mais ce clic. Le détail (ce qui est relevé, ce qui ne l'est jamais, à quoi ça sert)
  est replié dans un `<details>` sous le formulaire ; les sections « étapes » et « sites » sont retirées ; « 2 minutes »
  remplace « 5 à 10 minutes » partout ; le menu du haut ne garde que la marque et la langue, les liens (notice, « Ma
  session », contact, crédits) passent au pied de page de chaque page. Notice en version 2026-11-14.8. Preuve :
  `tests/test_public_accueil_court.py` (23 cas, 19 vus en échec avant le code), suite rapide verte, captures à 390 × 844
  et 1 280 × 800 en clair et en sombre (`outputs/apercu-court/`), session d'essai complète par l'adresse publique dans
  un Chromium piloté (bouton, relevé reçu en 204, suppression). Limites : code mort laissé en place (classes CSS des
  sections retirées, `pages._vignettes_vedette`) ; non essayé sur Safari, iPhone, Firefox ; aucune mesure de l'effet
  sur la participation. Décidé par : Ethan (la demande), coordination (la forme ; travail d'un sous-agent, relu).
- **D-81 — 14/11/2026 — Le site public ne cite jamais le projet ni le laboratoire.** Constat : Ethan, le même jour :
  « tu mention noezia faut pas du tout ». Le pied de page et la notice disaient « NOEZIA ShadowLab », une feuille de
  style citait un chemin du dépôt, et le script d'observation servi pendant une session portait ces noms à 8 lignes
  (texte dessiné sur le canvas, noms internes, sondes au nom du moteur). Décision : aucun de ces noms dans ce que le
  site sert (corps, en-têtes, noms de cookie). Les textes et la feuille de style sont corrigés. Le script du laboratoire
  ne change pas d'un octet : l'application publique en sert une copie dérivée, fabriquée au démarrage par six
  remplacements exacts (`public/script_public.py`) ; elle refuse de démarrer si un remplacement ne trouve pas son
  compte ou s'il reste un nom interdit dans un fichier servi sous `/lab/static/`. Les deux sondes au nom du moteur
  (`noezia_enumerable`, `__NOEZIA_PROFIL__`) sont absentes de la copie : pour un humain elles étaient toujours vides, et
  `detection.DetecteurAutomationGlobals` lit une clé absente comme une liste vide, donc `shadowlab rejeu --base` donne
  le même verdict. Preuve : `tests/test_public_sans_marque.py` (textes, fichiers statiques, parcours de toutes les
  pages hors session et pendant une session, copie du script, refus de démarrer ; vus en échec avant), `node --check`
  sur la copie, session d'essai par l'adresse publique (41 clés d'empreinte, relevé reçu en 204, aucune erreur de
  console). Conséquences acceptées : le canvas du site public porte un autre texte, donc son hachage n'est pas
  comparable à celui du laboratoire ; un moteur NOEZIA lancé contre le site public ne serait plus vu par ces deux
  sondes (ce n'est pas l'usage du site) ; les fichiers sous `/lab/static/` sont servis sans `ETag` ni `Last-Modified`.
  Décidé par : Ethan (la règle), coordination (la forme ; travail d'un sous-agent, relu).
- **D-82 — 14/11/2026 — Arena : la durée des cookies de réussite d'un défi est un réglage du profil.** Constat : le
  cookie vivait 3 600 s par une constante ; une récolte plus longue que lui n'a jamais été mesurée (la campagne 107
  dure 50 minutes par passage). Décision : `duree_cookie_s` au niveau du profil (30 à 86 400 s, 3 600 par défaut : rien
  ne change pour les profils existants), pour les cookies `defi`, `captcha`, `turnstile` et `recaptcha` ; le cookie
  `connexion` garde 3 600 s. Profils de mesure dans `configs/arena/profils-cookie-court.yaml` (`04court`, `05court`,
  `06scorrcourt`, copies de 04, 05 et 06 sans corrélation avec 600 s), un seul fichier de profils supplémentaires.
  Preuve : `tests/test_duree_cookie.py` (17 cas, 10 vus en échec avant ; à travers l'application, un cookie obtenu par
  la vraie route est refusé à 601 s sous `04court` et accepté sous `04` au même instant). Limites : génération Nginx et
  Coraza vérifiée sur le texte seulement, aucune campagne lancée, tests d'intégration pas relancés depuis. Décidé par :
  coordination (travail d'un sous-agent, relu).
- **D-83 — 14/11/2026 — La récolte peut repasser la porte en cours de passe, sur option de la recette.** Constat : le
  laissez-passer d'une protection expire (cookie de l'Arena : une heure, un cookie par défi). Une passe plus longue
  était redéfiée en plein travail puis arrêtée par la sentinelle ; jamais mesuré au-delà de 50 minutes (campagne 107).
  Décision : deux réglages de plus dans `porte_entree` : `repassages_max` (0 par défaut : rien ne change, un défi en
  cours de passe arrête) et `ecart_min_s` (300 s par défaut). Quand l'option est active, un défi qui revient est traité
  comme à l'entrée, sans aucune action de la récolte (ni clic, ni rechargement, ni résolution) : attente sur place
  pendant `attendre_s`, ou statut d'alerte périmé d'un défi levé pendant la lecture. Bornes : au plus `repassages_max`
  repassages ; un défi revenu moins de `ecart_min_s` après le passage précédent (entrée comprise) est un signe
  d'alerte et arrête, avec la même alerte qu'avant. Une rafale (défis vus moins de 120 s après un passage, 4 au plus)
  compte pour un seul passage : aux niveaux 05 à 07 de l'Arena, chaque défi a son propre cookie et ils expirent à
  quelques secondes d'écart ; 120 s et 4 viennent de la lecture du code, pas d'une mesure. Tracé : événement
  `porte_repassage` par défi vu (adresse, rang, défi, attente, écart, rafale, refus), bloc `porte_repassages` de
  `resume.json`, ligne de `shadowlab recolte etat` ; le compte se relit à la reprise. Dans les campagnes, le scénario
  active l'option (10 repassages au plus, 300 s) et rend le nombre et la liste dans les détails du passage. Règle
  maintenue : la commande ne clique jamais sur un défi d'un site tiers et n'a aucun solveur de CAPTCHA. Preuve :
  `tests/test_parcours_porte_en_cours.py` (doubles de moteur ; 16 cas vus en échec avant le code), 1 670 tests rapides
  verts après fusion. **Conséquence pour la lecture des campagnes** : un défi né d'un soupçon de l'Arena en cours de
  passe, levé par le pilote plus de 300 s après le passage précédent, ne fait plus échouer le passage ; il apparaît
  dans `porte_repassages`. Tout bilan de campagne donne donc le nombre de repassages et compare leur écart à la durée
  du cookie du niveau : un repassage bien avant l'expiration est un soupçon, pas une expiration. Limites : aucune
  mesure dans un vrai Chrome à cette date ; une page de blocage de l'Arena est attendue `attendre_s` avant l'arrêt ;
  les constantes de campagne dépendent de la durée du cookie (écart minimal au plus la moitié de cette durée).
  Décidé par : coordination (conception d'un sous-agent Opus, relue).
  **Ajout du 14/11, mesure dans un vrai Chrome (campagne 112, cookie de 600 s, vitrine à 150 annonces, 3 passages, 0
  panne)** : niveaux 04, 05 et 06 sans corrélation, 158 pages et 2 100 champs sur 2 100 à chacun. Le défi revient 1, 2
  et 2 fois, à 582 à 612 s du passage précédent (l'expiration du cookie), et la porte est repassée sans attente. Trois
  défis de rafale aux niveaux 05 et 06 (19, 23 et 36 s après un passage) : la règle de rafale était nécessaire. Limites :
  un passage par niveau ; les défis sont levés par le pilote sur notre Arena (CAPTCHA en clés de test aux niveaux 05 et
  06) ; le cookie d'une heure sur une passe de plus d'une heure reste à mesurer.
  **Ajout du 14/11, campagne 113 (cookie de 600 s, rallye, 427 pages par passage, 3 passages, 0 panne)** : 34 410 champs
  sur 34 410 aux niveaux 04, 05 et 06 sans corrélation ; le défi revient 4, 5 et 4 fois (546 à 607 s), neuf défis de
  rafale, aucun arrêt. Limite mesurée de la règle de rafale : aux niveaux 05 et 06 le délai du deuxième défi grandit de
  8 à 10 s par cycle (22 s puis 62 s au cinquième cycle du niveau 05) ; au-delà de 120 s, vers le onzième cycle, il
  serait pris pour un défi revenu trop tôt et la passe s'arrêterait. Non corrigé (trait de notre Arena, un cookie par
  défi) ; à revoir si un travail de plus d'une dizaine d'heures est visé.
  **Ajout du 14/11, campagne 114 (cookie d'origine de 3 600 s, rallye à 683 pages, 3 passages, 0 panne)** : niveaux 04,
  05 et 06 sans corrélation, 59 257 champs sur 59 257 à chacun, en 4 515, 4 867 et 4 631 s. Le défi revient une fois,
  à 3 607, 3 590 et 3 590 s, et la récolte finit le travail. Première passe de plus d'une heure sous protection.
- **D-84 — 14/11/2026 — Site public : le site d'annonces est caché par défaut, et le site tourne dans tmux.** Constat :
  Ethan, avant de partager le site sur Reddit : « Pour le site masqué l'autre site annonce on s'en fou ». Décision : le
  site d'annonces « Habitat Démo » n'apparaît plus sur le site public : ses cinq routes `/lab/vitrine/…` ne sont pas
  enregistrées (404 comme toute adresse inconnue), le bandeau du réseau social n'a plus de lien « Autre site », et les
  textes parlent d'un seul site de démonstration (notice 2026-11-14.9). Le réglage `SHADOWLAB_PUBLIC_VITRINE=1` le
  rallume, avec les textes d'avant ; le laboratoire garde son site d'annonces. Exploitation : `site-public-tunnel.sh`
  a trois modes (`tout`, `tunnel`, `app`) ; le site tourne dans deux sessions tmux (`site-public-tunnel`,
  `site-public-app`), indépendantes de toute session d'assistant, et l'application se relance sans changer l'adresse.
  Preuve : `tests/test_public_sans_annonces.py` (27 échecs et 13 erreurs avant le code), 3 tests du script vus en échec
  avant, 1 715 tests rapides verts, vérification par l'adresse publique (annonces en 404, aucune mention, session
  d'essai complète puis supprimée). Limites : `vitrine.css` et `vitrine.js` restent servis (partagés avec le réseau
  social) ; le test d'intégration du site public n'est pas relancé ; l'adresse reste celle d'un tunnel rapide (perdue
  si le Mac redémarre ou si le tunnel tombe, et avec elle « Ma session » pour les participants). Décidé par : Ethan (la
  demande), coordination (la forme ; travail d'un sous-agent, relu).
- **D-85 — 14/11/2026 — Arena : la sonde `deep-proxy` mesure aussi Safari et Firefox (sonde 2, détecteur 1.1).**
  Constat : les deux premières sessions humaines du site public (Safari 26 et 27 sur iPhone), rejouées contre les
  niveaux, passent 01 à 03 et sont arrêtées de 04 à 07 par le seul détecteur `deep-proxy` (`getter_non_natif` 0,8 et
  `illegal_invoc_absent` 0,7). Cause : la sonde de `observateur.js` (`testDetectionProfonde`) ne reconnaissait que les
  formes de Chrome (texte `function get x() { [native code] }`, message « Illegal invocation ») ; tout Safari et tout
  Firefox étaient classés automatisés. Décision : la sonde accepte le texte d'une fonction native avec ou sans `get `,
  sur une ou plusieurs lignes, compte toute `TypeError` levée par le getter appelé sur un objet étranger, et écrit
  `sonde: 2`. Le détecteur (1.1) n'applique ces deux signaux à un relevé de l'ancienne sonde (sans `sonde`) que pour
  la famille Chromium (`userAgentData`, `Sec-CH-UA`, ou `Chrome/` dans le User-Agent) ; ses autres signaux ne changent
  pas. Preuve : `tests/test_deep_proxy_safari.py` (19 tests, 9 vus en échec avant le code ; sonde exécutée sous Node
  sur les trois formes de texte et de message), 1 734 tests rapides verts ; rejeu des deux vraies sessions avec le
  code corrigé : `deep-proxy` ne les arrête plus. Limites : aucun vrai Safari ni Firefox n'a encore exécuté la sonde
  2 (on le saura à la prochaine session Safari du site public, relancé avec elle à 19 h 45) ; le repli sur le
  User-Agent est falsifiable ; **les deux sessions restent arrêtées de 04 à 07 par le score composite** (`vendor_absent`,
  `hover_none`, `ratio_move_click_faible`, `no_first_paint`, quatre règles pensées pour Chrome sur ordinateur) :
  correction suivante. Campagne de contrôle à faire après les deux corrections. Décidé par : coordination (travail
  d'un sous-agent, relu).
- **D-86 — 14/11/2026 — Arena : quatre règles ne supposent plus un Chrome sur ordinateur.** Constat : `deep-proxy`
  corrigé (D-85), les deux sessions humaines (Safari sur iPhone) restaient arrêtées de 04 à 07 par le score composite :
  `vendor_absent` (« Apple Computer, Inc. » n'est pas « Google Inc. »), `hover_none` (un téléphone n'a pas de survol),
  `ratio_move_click_faible` (un toucher donne un seul mouvement de souris par clic), `no_first_paint` (Safari ne donne
  pas cette entrée). Décision : deux aides dans `detection.py`, `famille_navigateur` (chromium, webkit, gecko ou
  inconnue : `userAgentData`, `Sec-CH-UA`, puis le User-Agent) et `appareil_tactile` (au moins deux indices parmi
  `maxTouchPoints > 0`, `css_media` sans survol ni pointeur fin, `touchstart` relevé). `vendor_absent` compare au
  vendor de la famille (`langues` 1.1) ; `hover_none` ne vaut pas sur un appareil tactile (`css-media` 1.1) ;
  `ratio_move_click_faible` ne vaut pas quand les clics viennent du toucher (`comportement` 2.2) ; `no_first_paint` ne
  vaut que pour Chromium (`paint-timing` 1.1). Aucun seuil, aucun profil, `observateur.js` inchangé. Preuve :
  `tests/test_detecteurs_hors_chrome_bureau.py` (29 tests, 20 vus en échec avant le code), suite complète à 1 807
  tests verts (14/11, 19 h 55) ; rejeu des deux sessions iPhone : 0 arrêtée sur 2 du niveau 01 au niveau 07 (2 sur 2 de
  04 à 07 avant). **Campagne de contrôle 115** (`controle-vrai-chrome.yaml`, 14/11, 19 h 55 à 20 h 32, 135 passages, 0
  panne, à comparer à la 98) : `noezia` en identité native 15 sur 15 aux niveaux 04, 05 et 06 sans corrélation
  (inchangé) ; témoin `patchright` 0 sur 45 (inchangé) ; le vrai Chrome sans comportement (`patchright-chrome-interface`)
  10 sur 15 au niveau 04 et 0 sur 15 au niveau 06 (inchangés), mais **15 sur 15 au niveau 05 au lieu de 5 sur 15** : écart
  non attribué à cette date (plusieurs changements de l'Arena séparent les deux campagnes, dont D-78) ; enquête en
  cours, à écrire en ajout ici. Limites : deux sessions humaines, un seul type d'appareil ; un robot qui émule un
  mobile de façon cohérente (points de contact, `matchMedia`, événements de toucher) profite de ces exemptions ;
  `screen_position_zero` reste à 0,28 pour ces sessions (seuil du niveau 07 : 0,3). Décidé par : coordination (travail
  d'un sous-agent, relu).
  **Ajout du 15/11, écart de la campagne 115 attribué** : le passage du vrai Chrome sans comportement de 5 à 15 sur 15
  au niveau 05 vient de D-78 (voir son ajout), pas de D-85 ni de D-86 : rejoués hors ligne, les relevés des campagnes 98
  et 115 donnent les mêmes verdicts aux niveaux 04 et 05 avant et après ces deux corrections. Réserve : la campagne 115
  ne juge que Chrome sur ordinateur ; elle ne mesure pas ce que D-86 ouvre à un robot qui se présente comme tactile ou
  WebKit. Les sessions du site public sont présumées humaines, pas des humains connus. Une troisième session (Chrome
  157 sur Windows, 15/11) est arrêtée de 05 à 07 par `trajectoire_lineaire` et `screen_position_zero` : non corrigé,
  on ne recale pas un seuil sur une session anonyme.
  **Ajout du 15/11, la réserve « un robot qui émule un mobile » mesurée (campagne 117, 120 passages, 0 panne)** : le vrai
  Chrome sans comportement piloté par patchright fait 15, 10, 15 et 0 sur 15 aux niveaux 03, 04, 05 et 06 sans
  corrélation ; le même avec le descripteur « Pixel 7 » de Playwright fait 15, 10, 0 et 0. Le déguisement ne lui fait
  rien gagner : il est arrêté par `aucune_interaction` et `outer_eq_inner`. Limite : une seule émulation, sans vrais
  touchers ; l'option `appareil` des pilotes Playwright et Patchright est documentée par Playwright et déclarée dans
  `options_permises`.

  **Ajout du 15/11, quatrième session et critère annoncé** : la quatrième session du site public (`414f351a`, 15/11 à
  18 h 06 UTC, 61 s, 12 pages) vient du navigateur intégré de l'application Claude (`Claude/5.1231.2 Chrome/156`, marques
  `Not:A-Brand` et `Chromium`, `window.chrome` sans `app`, `loadTimes` ni `csi`), pas de Google Chrome ; conduite à la
  main ou par un automate : non établi. Rejeu (code `fd57b6e`) : elle passe 01 et 02, arrêtée de 03 à 07 par
  `chrome-apis` et `comportement` ; sans ces deux détecteurs elle passe 03 et 04 et reste arrêtée de 05 à 07
  (`client_hints_absents`, `trajectoire_lineaire`, `permissions_all_denied`, `screen_position_zero`). Les trois autres
  sessions n'ont pas changé. `trajectoire_lineaire` (détecteur `entropie-interaction`, une émission par page, poids 0,6) :
  une seule page sous 0,08 rad franchit le seuil composite des niveaux 05, 06 et 07 ; 4 pages sur 9 évaluées pour
  `414f351a`, 2 sur 11 pour la session Windows, qu'elle seule arrête ; 0 déclenchement dans les 255 passages des
  campagnes 115 et 117. `screen_position_zero` : `screenX` et `screenY` à 0 dans les quatre sessions publiques ;
  déclenchée dans 105 passages sur 255 du labo, jamais pour un Chrome visible ; neutralisée, aucun verdict ne bascule
  chez les quatre sessions. Décision : aucune règle ne change, aucune nouvelle décision, pas de campagne. Critère annoncé d'avance
  pour `trajectoire_lineaire` : dès qu'un humain connu, dans un vrai Chrome, Safari ou Firefox sur ordinateur, a une
  seule page sous 0,08, la forme « une page suffit » est prouvée arrêter un humain et on la corrige (ce sera une nouvelle décision, avec
  les campagnes de contrôle `controle-vrai-chrome.yaml` et `temoin-mobile-emule.yaml` à comparer aux 115 et 117) ; la
  valeur du seuil attend le critère de 1.7 (10 sessions sur ordinateur). `screen_position_zero` reste inchangée : elle
  ne change aucun verdict aujourd'hui et coûte 0,28 de marge aux niveaux 06 et 07 ; à traiter avec le prochain
  changement de l'Arena, pas seule. Détail : `docs/recherche/calibrage-sessions-publiques-2026-11-15.md`. Décidé par :
  coordination.
- **D-87 — 15/11/2026 — Palier 2, étape I1 : l'Arena garde la mémoire des visiteurs, par « monde » (migration 10).**
  Pourquoi maintenant : le palier 1 attend Ethan (1.7 : des humains connus sur ordinateur ; 1.8 : un domaine). Le 15/11
  au soir, Ethan : « je te laisse tout continue a travailler sur d'autre chose ». La coordination ouvre donc le palier 2
  par ses deux étapes qui ne dépendent d'aucune des quatre questions de la conception
  (`docs/recherche/identite-qui-dure-2026-11-12.md` § 7 et § 10) : I1 (ici) et I4 (D-88). C'est une **exception à la
  règle du plan § 4** (« on ne commence pas un palier avant la fin du précédent »), décidée par la coordination. Les
  quatre questions restent ouvertes. Constat : l'Arena ne reconnaît pas un visiteur d'une requête à l'autre (étape 2.1
  du plan), et rien ne sépare l'état d'une campagne de celui de la suivante. Décision : migration **10** (tables
  `mondes`, `visites`, `bannissements` vide, préparée pour I3 ; colonne `runs.monde_id`). Cookie `sl_visiteur`, signé
  par le secret existant de l'Arena (`arena/secret.py`), valeur `<visiteur>.<hmac>`, nom du monde compris dans la
  signature, 400 jours, `HttpOnly`, `SameSite=Lax`, `Path=/lab` ; posé sur les réponses `/lab` du labo seulement (pas
  `/labo`, jamais par l'application publique). Champ `monde` des campagnes : `campagne` (défaut, monde `c<id>`),
  `serie` (`c<id>:<moteur>:<niveau>`), `passage` (la même chose plus `:<scénario>:<répétition>`) ; monde `manuel` pour
  `/manuel`, `hors-passage` pour une requête sans jeton. I1 ne change aucune décision de l'Arena : la corrélation reste
  celle de D-48 et D-64 jusqu'à I2. Preuve : `tests/test_visiteurs.py` (16 tests, écrits d'abord, en échec avant le code
  avec `ImportError`) ; commits `a2a4770` (tests), `7e42535` (code), `ba5ae45` (empreinte de `site/app.py` mise à jour
  dans la garde de `tests/test_public_social.py`, comme pour D-82), fusion `9ce9066` ; suite complète 1 858 verts
  (15/11, 22 h, 8 min 33 s). **Campagne de contrôle 118** (`controle-vrai-chrome.yaml`, 15/11, 22 h 04 à 22 h 43,
  135 passages, 0 panne), comparée à la 115 : taux identiques à chaque cellule (`noezia-natif` 15, 15, 15 sur 15 aux
  niveaux 04, 05 et 06 sans corrélation ; `patchright-chrome-interface` 10, 15, 0 ; témoin `patchright` 0, 0, 0) ; les
  135 passages sont dans le monde `c118`. Limites : les durées moyennes sont plus longues (`noezia-natif` 15,7 / 31,5 /
  32,8 s contre 15,1 / 30,2 / 30,1 s ; `patchright-chrome-interface` 1,6 / 6,7 / 4,8 s contre 1,4 / 5,8 / 4,1 s) ; cause
  non établie : chaque requête `/lab` fait deux écritures `INSERT OR IGNORE` (`mondes`, `visites`) dans une connexion
  SQLite neuve, et la charge de la machine a atteint 11 pendant la campagne ; à reprendre avec I2 (n'écrire qu'à la
  première requête d'une session). Un test était déjà intermittent avant I1 (`tests/test_duree_cookie.py`, voir
  `AGENTS.md`) : non corrigé. La base du site public recevra la migration 10 (tables vides) au prochain redémarrage de
  l'application publique, qui tourne encore avec l'ancien code ; sauvegardes : `outputs/shadowlab-avant-migration10-2026-11-15.sqlite3.gz`
  (115 Mo, schéma 9) et `outputs/public/public-avant-migration10-2026-11-15.sqlite3`. Décidé par : coordination.
- **D-88 — 15/11/2026 — Palier 2, étape I4 : le moteur `noezia` garde une identité persistante (option `identite`).**
  Constat : chaque lancement du moteur repart d'un Chrome vierge (étape 2.5 du plan) ; un compte connecté ne peut pas
  durer. Décision : option `identite` (chaîne, dans `options_permises`), acceptée seulement avec `identite_native: true`
  et `headless: false`. Nom : `^[a-z0-9][a-z0-9-]{0,39}$`. `nb_essais` est forcé à 1. Un dossier par identité,
  `outputs/identites/<nom>/` (droits 700) : `identite.json` (`nom`, `creee_le`, `etat`), `chrome/`, `visites.jsonl`,
  `verrou` (`flock` non bloquant : une identité ne sert qu'à un lancement à la fois). La racine ne se règle que par
  `SHADOWLAB_IDENTITES`, jamais par une option de campagne. Une identité à l'état `banni` est refusée. Chrome est lancé
  par `launch_persistent_context`, avec le verrou réseau du périmètre. `configuration()` enregistre `identite` et
  `identite_age_jours`. Preuve : tests écrits d'abord (commit `1b5907f`, en échec avant le code avec `ImportError`),
  code `ea77e14`, fusion `49d9cf7` ; dans un vrai Chrome, la même identité sur deux lancements garde le même cookie
  durable et le même `localStorage`, deux identités donnent deux visiteurs, et une redirection hors périmètre est
  refusée en mode persistant (`test_noezia_identite_refuse_une_redirection_hors_perimetre`) ; suite complète 1 858 verts.
  Limites : essayé avec le cookie d'une page locale, pas encore avec `sl_visiteur` ; pas d'état `alerte` ni de
  sentinelle d'identité (I6) ; pas de sauvegarde du profil ; `identite.json` ne porte ni « hôtes visés » ni « machine »
  (§ 5.2 de la conception) ; aucune campagne ne s'en sert encore. Décidé par : coordination.
- **D-89 — 15/11/2026 — Palier 2, étape I2 : `correlation-session` 2.0, par monde (remplace la règle 1.1 de D-48 et D-64).**
  Constat : en 1.1, la règle comptait des sessions de toute la base. Un humain qui revient 5 fois était classé comme un
  robot qui recycle son empreinte, et une campagne influençait la suivante (campagne 101 : niveau 06 complet à 0 sur 15).
  Les visiteurs et les mondes de D-87 permettent de compter des **visites dans un monde**. Décision (conception
  `docs/recherche/identite-qui-dure-2026-11-12.md` § 4.3) : l'empreinte **E** est un seul hachage de `profil_complet` et
  de `canvas` (`correlation.empreinte_e` ; un canvas en échec n'entre pas). Deux signaux. `empreinte_sans_memoire` :
  sessions **neuves** (premier passage d'un visiteur dans le monde) de même E, commencées dans les 24 dernières heures,
  dans le même monde, celle-ci comprise ; à partir de 5, poids 0,7 ; à partir de 10, poids 1,0 ; elle ne juge qu'une
  session neuve. `debit_empreinte` : au moins 30 sessions de même E commencées dans les 60 dernières minutes, dans le
  même monde, neuves ou non ; poids 0,8. Seuils et poids de D-48 inchangés, composite inchangé (version du détecteur 2.0).
  Une session sans monde n'est pas jugée : le rejeu des sessions d'avant I1 ne juge rien (`correlation_historique`
  rend `None`). Le rejeu ne voit que les visites antérieures du monde de la session ; sa ligne de `shadowlab rejeu`
  donne le nombre de sessions classées « automatisé » parmi celles qui ont un monde. **Allègement d'I1** (cause
  possible de la hausse des durées de la campagne 118, non prouvée) : `visiteurs.reconnaitre` lit d'abord et n'écrit que
  la première fois ; une session déjà connue n'écrit plus rien ; l'application tient un cache des sessions connues
  (`visiteurs.Connus`, 20 000 entrées au plus, les plus anciennes partent d'abord) qui évite même d'ouvrir une
  connexion à la base. **`comportement` 2.3**, après la relecture de sécurité du 15/11 : `sans_ressources` ne juge
  qu'une session neuve, ou un visiteur connu dont aucune session antérieure du même monde n'a chargé les ressources
  (`/lab/static`) ; sans cela un cookie de visiteur rejoué aurait dispensé un robot qui ne charge jamais les ressources
  (`correlation.visite_neuve`). **Bilan d'un passage** (16/11) : avant, `passages.finaliser` ne donnait jamais la
  corrélation au détecteur ; dans le bilan de chaque passage `correlation-session` valait « indéterminé », même quand le
  gardien avait refusé la session pour elle (les campagnes 101 et 120 ont `detecte_par` vide ; le défaut date de D-48).
  Maintenant `correlation_historique` lit les visites antérieures du monde, avec un jugement figé au début de la
  session (des passages tournent en parallèle). L'issue ne change pas (`challenge_non_valide`, la cause affichée reste
  le défi) ; seuls les drapeaux changent : `classe_automatise` vrai ; `detecte_par` = `composite` de 5 à 9 sessions
  neuves, `correlation-session` à partir de 10. Les bilans déjà en base ne sont pas recalculés. **Version 2.1 (16/11,
  `6de26a0` puis `733f25d`, fusion `46fc745`)** : sans aucun signal, le détecteur répond « indéterminé »
  (`aucune_correlation`), plus « humain ». Une absence de corrélation ne prouve rien sur l'humanité de la session.
  Pourquoi : la campagne 122 (16/11, 0 h 48 à 1 h 01, `correlation-06-mondes-serie.yaml`, en 2.0) a montré l'effet de
  bord du bilan nommé. `meta-composite` y voyait 42 détecteurs « humain » (`unanimite_humain`) et classait
  « automatisée » chacune des 4 sessions réussies. Avant, l'indétermination permanente de `correlation-session` bloquait
  cette unanimité : `meta-composite` n'apparaît dans aucun `detecte_par` de passage réussi des campagnes en base. Aucun
  effet sur la décision de l'Arena : « indéterminé » sans signal et « humain » sans signal pèsent 0, et
  `meta-composite` n'entre dans aucun profil. Contrôle, **campagne 123** (16/11, 1 h 18 à 1 h 30, même fichier, en 2.1) :
  4 sur 15, comme les 120 et 122. Les 4 réussis ont `detecte_par` vide. Du 5ᵉ au 9ᵉ passage, `detecte_par` vaut
  `composite` ; du 10ᵉ au 15ᵉ, `correlation-session`. Preuve : tests écrits
  d'abord, en échec avant le code (`tests/test_correlation_v2.py`, `5e225f1` puis `c63b10c` ;
  `tests/test_visiteurs_allegement.py`, `34776cd` puis `6515485` ; `sans_ressources`, `3d6283f` puis `b492174` ;
  `tests/test_bilan_correlation.py`, `853228b` puis `ff237ee`), fusions `4bb19b4` et `bef7017`.
  **Campagne 119** (15/11, 23 h 24 à 23 h 39, `configs/experiments/correlation-06-mondes.yaml`, `monde: passage`) :
  `noezia` en identité native, niveau 06 complet, **30 sur 30**, borne basse de Wilson 88,6 %. C'est le niveau 06 **en
  première visite** : un seul passage par monde, donc la corrélation n'a rien à comparer. Elle ne remplace pas « 06
  complet, 0 sur 15 » de la campagne 101 ; la question Q1 de la conception (mesurer le 06 comme une première visite)
  reste ouverte, à Ethan. **Campagne 120** (15/11, 23 h 39 à 23 h 52, `correlation-06-mondes-serie.yaml`, `monde:
  serie`, 15 passages dans un seul monde) : **4 sur 15**. Les 4 premiers passent ; du 5ᵉ au 15ᵉ, le gardien relève
  `empreinte_sans_memoire` (« 5 sessions neuves de même empreinte dans les 24 dernières heures ») et rejette la preuve
  de travail (`defi-js`, `rejete-empreinte`). Le monde 33 a 15 visites, toutes neuves, de 15 visiteurs : chaque passage
  est un navigateur neuf, sans mémoire. C'est le comportement voulu : un robot qui revient sans mémoire est arrêté à la
  5ᵉ session ; ce qui doit le faire passer, c'est l'identité persistante (I4, I6, puis I7). **Campagne 121** (contrôle,
  15/11 23 h 52 au 16/11 0 h 30, `controle-vrai-chrome.yaml`, sans corrélation) : mêmes taux que les campagnes 115 et 118
  à chaque cellule (durées dans `docs/PLAN.md` § 2) ; patchright et `noezia` au niveau 04 sont revenus au niveau de la
  115, `noezia` aux niveaux 05 et 06 sans corrélation non : **la cause de la hausse de la 118 n'est pas établie**.
  Limites : un cookie de visiteur rejoué donne des sessions « connues » que `empreinte_sans_memoire` ne juge pas ;
  `debit_empreinte` et les compteurs par visiteur d'I3 doivent le couvrir (conception § 4.3 ; relecture de sécurité du
  15/11). Pas de témoin aux campagnes 119 et 120. CAPTCHA en clés de test au niveau 06. Une seule machine, aucun humain
  en base. Le monde par défaut est `campagne` : une campagne au niveau 06 complet partage désormais un monde par
  campagne ; non mesuré. **Code mort signalé, non supprimé** : `correlation.enregistrer_hash` et la table
  `empreintes_vues` sont encore écrits à la collecte (`site/app.py`) mais plus lus par le détecteur (`hash_session`
  reste utile : `empreinte_e` s'en sert) ; la purge de `public/donnees.py` y touche encore. `shadowlab rejeu`
  (`cli.py`) affichait encore « correlation-session avec la table actuelle empreintes_vues », alors que le chiffre vient
  maintenant des visites antérieures du monde de chaque session : libellé corrigé le 16/11 (« visites antérieures du
  monde de chaque session »). Décidé par : coordination (Ethan a laissé la main : « je te laisse tout continue
  a travailler sur d'autre chose »).
- **D-90 — 15/11/2026 — Palier 2, étape I5 : l'ordonnanceur des visites (`engines/noezia/visites.py`).** Constat : la
  campagne « une identité qui revient » (I7) et la récolte ont besoin de dire quand commence la prochaine visite d'un
  visiteur régulier et combien de pages elle lit. Décision : une seule source pour les deux (conception § 5.4). Elle ne
  lit aucune page et ne fait aucune requête ; ce qui se passe dans la visite reste le rythme `prudent` de `rythme.py`.
  Valeurs de départ, des estimations de ce qu'un humain fait, pas des valeurs réglées sur l'Arena : visites de 8 h à 23 h
  (heure du poste) ; écart de 45 à 180 min entre deux visites, tirage log-normal de médiane 90 min, compté de la **fin**
  de la visite précédente au début de la suivante ; première visite du matin décalée de 0 à 90 min (jamais 8 h pile) ;
  5 à 40 pages par visite, médiane 15 ; au plus 120 pages sur toute heure glissante (une visite finie dans l'heure
  précédente compte en entier) et 200 par jour. Un plafond réduit les pages de la visite, ou repousse la visite (à la
  fin de l'heure, au lendemain) s'il en reste moins que le minimum. Une visite doit finir dans la plage : la dernière
  heure de début est la fin de plage moins 30 min (`duree_visite_max_min`) ; l'ordonnanceur ne coupe pas une visite qui
  déborde. Horloge et sommeil injectables ; l'état est en mémoire, `rejouer` reprend les visites déjà faites.
  `rythme.tirer_lognormal` est devenu public : une seule loi pour la cadence de la récolte et pour l'ordonnanceur.
  Preuve : `tests/test_visites.py`, écrit d'abord (`8338d6b`, en échec avant le code), code `ab4de92`, fusion `2c484bc`.
  Limites : aucune campagne ni récolte ne s'en sert encore (I7) ; valeurs non mesurées. Décidé par : coordination
  (Ethan a laissé la main : « je te laisse tout continue a travailler sur d'autre chose »).
- **D-91 — 15/11/2026 — Palier 2, étape I6 : la sentinelle d'identité.** Constat : la sentinelle de la récolte s'arrête
  au premier signe d'alerte, mais ne dit rien à l'identité persistante de D-88, qui pourrait resservir tout de suite.
  Décision (conception § 5.5) : `sentinelle.verdict_identite` classe l'alerte : `banni` pour un 403 sur la **première
  page** d'un passage (révisé par D-103 : aussi à toute page quand le corps du refus d'une ressource dit
  `bannissement` ; révisé par D-104 : aussi quand une page refusée porte `X-Arena-Refus: bannissement`), `alerte` pour tout autre signe (429 et autres statuts, défi en cours de passe, hors site, porte
  d'entrée revenue trop tôt…). Elle ne fait que classer : aucune requête, aucune action. `parcours.py` écrit le verdict
  dans l'identité (`identite.marquer`, avec `alerte_le` ou `banni_le` et la raison). États : `ok` ; `alerte` : l'identité
  est refusée pendant 1 h (`identite.ATTENTE_ALERTE_S`), sauf option `maintenant` ; `banni` : refusée toujours, et rien ne
  l'efface. Une visite `ok` finie sur une identité qui sortait d'une alerte la remet à `ok`. Nouveau signe, `porte_revenue` :
  la recette peut déclarer `porte_entree.duree_s` (facultative, `recettes.py`), le temps pendant lequel le site ne
  redemande pas le défi à un visiteur connu ; avec une identité persistante, le même défi revenu avant cette durée est
  une alerte immédiate, sans attente ni action sur le défi ; l'heure du dernier défi franchi est gardée dans l'identité
  (`porte_franchie_le`). Preuve : `tests/test_sentinelle.py` et `tests/test_identite.py`, écrits d'abord (`81f9cbc`, en
  échec avant le code), code `99897ca`, fusion `2c484bc`. Limites : aucune campagne ne s'en sert encore ; pas de sauvegarde
  du profil ; une seule identité à la fois. Décidé par : coordination (Ethan a laissé la main : « je te laisse tout
  continue a travailler sur d'autre chose »).
- **D-92 — 16/11/2026 — Palier 2, étape I3 : le bannissement de l'Arena et le profil « endurance ».** Constat : l'Arena
  ne se souvenait de personne. Un robot détecté revenait avec un nouveau jeton et repartait de zéro ; le plan 2.2 et la
  conception § 4.5 demandent qu'il soit refusé. Décision : un module `arena/bannissements.py`, lu **en tête du
  gardien**, avant tout défi. **Par visiteur**, dans son monde : un 403, même avec un nouveau jeton. **Par empreinte E**,
  dans le monde, pour les **seules sessions neuves** : un visiteur connu de même E n'est pas touché (sinon on bannirait
  tous les humains d'un même modèle de machine), ni un autre monde. Tout s'écrit dans la table `bannissements`.
  **Ce qui bannit** : une détection à la collecte de l'empreinte (visiteur et E, une seule ligne ; sans cela un scénario
  d'une seule page ne redemande jamais de page et n'est jamais banni) ; les trois branches `fingerprinting/bloque` de
  `controler` (`fingerprinting-differe`, `composite-differe`, pièges et règles) ; `defi_verifier` sur `rejete-empreinte`
  (sinon un robot détecté boucle entre le défi et le rejet) ; une session neuve dont E est bannie est refusée dès la
  collecte, et son visiteur est banni à son tour. **Ce qui ne bannit pas** : un défi émis, une preuve ratée, `suspect`
  quand le profil ne bloque pas, le 429 de Nginx, le WAF. Un banni n'obtient pas le cookie de porte. **Compteurs de pages
  par visiteur**, toutes ses sessions ensemble (une page au sens de D-78) : plus de 240 en 1 heure glissante, ou plus de
  2 000 en 24 h, et le visiteur est banni, sans E. Lecture stricte : la 241ᵉ et la 2 001ᵉ page bannissent. Ce sont les
  seuils de départ du § 4.6, pas des mesures. Un cookie de visiteur rejoué dans beaucoup de sessions en parallèle est
  compté une seule fois, en tout : cela répond à la limite de D-89 (relecture de sécurité du 15/11). Les mondes `manuel`
  et `hors-passage` ne sont jamais remis à zéro : aucun bannissement automatique n'y est écrit ; le bannissement manuel
  y fonctionne. **Le bannissement est une option de profil** (`bannissement.actif`, fausse par défaut), active dans
  `endurance` seulement : les niveaux 01 à 07 ne changent pas d'une décision. Sinon, dans un monde partagé par une
  campagne, un seul passage détecté ferait tomber tous les suivants, et les taux mesurés ne seraient plus comparables.
  Preuve : un test où toute lecture ou écriture de bannissement lèverait une erreur au profil 04, puis la campagne 125.
  **Profil `endurance`** : le niveau 06 pour un visiteur qui revient. Repris du 06 : ses détecteurs (ancre YAML
  `detecteurs_06`, donc par construction, avec `correlation-session` 2.1 par monde), le seuil composite 0,5, la
  limitation 2/4, le WAF en blocage (paranoïa 3, seuil 3), la preuve de travail de difficulté 18 liée au TLS, les pièges,
  le login anti-bot. Changé : la porte d'entrée (défi JavaScript) est liée au visiteur et non au jeton, valable 24 h,
  posée avec `max-age=86400` (`duree_cookie_s: 86400`, `defi_js.par_visiteur`). Écarté : le CAPTCHA démo, Turnstile et
  reCAPTCHA, tous éteints (le but est de ne pas déclencher un défi). `endurance` apparaît dans la liste des profils, le
  rejeu et `/api`. **Migration 11** : deux index sur `bannissements`, `(monde_id, visiteur)` et `(monde_id, empreinte)` ;
  aucune colonne ne change. **Commande** `shadowlab arena bannir --visiteur <id> --monde <nom>` : motif « manuel », pour
  le témoin de la sentinelle d'identité (D-91) ; elle refuse un monde ou un visiteur inconnu (code 2) ; aucune commande ne
  lève un bannissement. **Coût** : une session connue fait 1 lecture et 0 écriture par requête ; le bannissement et les
  compteurs tiennent dans la même requête SQL, qui lit `observations_http` jointe à `visites`.
  **Campagne 124** (`endurance-bannissement.yaml`, monde `campagne`, 3 passages par moteur, 16/11 de 2 h 06 à 2 h 08) :
  `noezia` en identité native, 3 sur 3, jamais banni (son empreinte diffère de celle du témoin : la seule E bannie du
  monde est celle de `playwright`). `playwright` (témoin) : 0 sur 3. Au 1ᵉʳ passage il est détecté (`botd`, `chrome-apis`,
  `headless`, `regles-http`, `regles-js`) puis banni, visiteur et E ; la suite du passage est refusée par le visiteur. Aux
  2ᵉ et 3ᵉ passages il est refusé par l'empreinte, puis son nouveau visiteur est banni. 3 lignes dans `bannissements`
  (monde 37) : c'est le critère du plan 2.2. **Réserve** : le témoin est aussi détecté à chaque passage par ses propres
  signaux. La campagne prouve que le bannissement est écrit et lu ; elle ne prouve pas qu'il arrête un robot qui
  passerait sans lui. Ce sera le témoin de la sentinelle (`arena bannir` avec une identité persistante, I7).
  **Campagne 125** (contrôle, `controle-vrai-chrome.yaml`, niveaux 04 à 06 sans corrélation, 135 passages, 16/11 de
  2 h 08 à 2 h 45) : mêmes taux que les campagnes 115, 118 et 121 à chaque cellule. `patchright` témoin : 0 sur 15 à 04, 05
  et 06 sans corrélation ; `patchright-chrome-interface` : 10, 15 et 0 ; `noezia` : 15, 15 et 15. Durées moyennes de
  `noezia` : 16,3 s, 28,0 s et 30,9 s ; de `patchright-chrome-interface` : 1,3 s, 5,7 s et 3,6 s. **Limites** : le
  bannissement par E ne peut pas bloquer la première page d'une session neuve (E n'existe pas encore) ; un robot qui jette
  ses cookies est un nouveau visiteur, donc ses compteurs ne s'accumulent pas : seul le bannissement par E le rattrape, et
  seulement après une détection ; une session commencée il y a plus de 24 h n'est pas comptée ; un humain détecté au profil
  `endurance` est banni (le « 0 humain banni sur 10 » du plan passe à I8) ; l'issue d'un passage banni peut rester
  `extraction_reussie` si le scénario a réussi avant l'arrivée de l'empreinte ; une requête sans jeton reste sans
  protection ; l'interface (`frontend/`) n'a pas été vérifiée pour le nouveau profil ; aucun humain en base, une seule
  machine. Preuve : `tests/test_bannissement.py`, écrit d'abord (`db87b7c`, en échec avant le code), code `2926718`,
  fusion `08635e0` ; suite complète : 2 015 tests verts (16/11, 9 min 10 s). Décidé par : coordination (Ethan a laissé la
  main : « je te laisse tout continue a travailler sur d'autre chose »).
- **D-93 — 16/11/2026 — Palier 2, étape I7 : le scénario « visite » et la campagne « une identité qui revient ».**
  Constat : I3 à I6 étaient en place, mais aucune campagne ne s'en servait. La conception (§ 6.1 et § 6.2) demande une
  soirée où une même identité revient de nombreuses fois, avec trois témoins. Décision : le **scénario `visite`** (le 20ᵉ
  scénario, `scenarios.py`). Il entre par `?sl=`, lit au plus N pages de la vitrine (15 par défaut), passe par `Parcours`,
  et sa porte d'entrée est déclarée valable 24 h. Il note le visiteur lu dans `visites` par le jeton de session (jamais le
  cookie signé), le monde, si la visite est neuve, et l'état de l'identité. **Champ `espacement` des campagnes**
  (`espacement.py`) : `fixe`, où l'écart se compte de la **fin** d'une visite au **début** de la suivante et où l'attente se
  fait par tranches de 5 s au plus, pour que `shadowlab arreter` reste écouté ; ou `ordonnanceur`, qui appelle `visites.py`
  (D-90). Les bras tournent en parallèle, chacun avec sa cadence : `concurrency` doit couvrir tous les bras. Sans le champ,
  rien ne change. Champs ajoutés : `pages_par_visite`, et, par entrée, `visites` et `bannir_avant_visite` (réservé au témoin
  de sentinelle ; il exige `identite` et `monde: serie`). **Un monde par bras** : `monde: serie` nomme le monde à partir du
  **libellé** de l'entrée (`c<n°>:<libellé>:<niveau>`) ; deux entrées `noezia` aux libellés différents ont donc deux mondes.
  **Bilan** : `shadowlab soiree bilan <n°> [--json]` (`soiree.py`) donne un verdict par critère du § 6.2 (tenu, non tenu,
  non mesuré) ; code de sortie 0 si tout est tenu, 1 sinon, 2 si la campagne est inconnue. **Récolte** :
  `recolte lancer --identite <nom>`, moteur navigateur seulement. **Deux corrections faites en route.** (1) Sentinelle :
  la page de refus de l'Arena (`data-arena="blocage"`) était prise pour un défi ; la porte attendait 15 s, puis l'identité
  passait en `alerte` au lieu de `banni`. Désormais, pour toute récolte, un refus en première page arrête tout de suite et
  l'identité devient `banni`, ce que D-91 voulait. (2) Moteur : l'état de l'identité n'était lu qu'à l'ouverture, une fois
  par unité ; il est relu avant chaque lancement de Chrome, donc une identité bannie à la visite d'avant ne revient pas.
  **Témoin classique** : le pilote `playwright` n'avait pas `etat_page`. Devant le défi JavaScript, le parcours l'abandonnait
  « après 0 s d'attente » : il était arrêté par l'outil, pas par l'Arena. Il a maintenant `etat_page`, avec le même contrat
  que `noezia` ; `patchright` en hérite. Il attend le défi comme `noezia`, puis l'Arena le juge. Aucune option d'empreinte,
  aucune requête en plus. **Essai 126** (`identite-soiree-essai.yaml`, 16/11, 3 h 38 à 3 h 46, avant le correctif du
  témoin) : non tenu sur un seul critère, celui du témoin classique (« arrêté par l'outil, aucun refus de l'Arena ») ; tous
  les autres sont tenus. **Essai 127** (même fichier, identités en `-2`, après le correctif, 3 h 54 à 4 h 03) : **tenu, à
  tous les critères**. Sujet : 3 visites sur 3, 1 visiteur, 1 empreinte E ; défi émis à la 1ʳᵉ visite seulement ; aucune
  alerte, 0 bannissement. Témoin négatif : 6 visites ; la première arrêtée est la 5ᵉ ; 2 bannissements dans son monde.
  Sentinelle : bannie (motif manuel) ; premier refus à la 3ᵉ visite ; 0 page demandée après ; identité notée `banni`.
  Témoin classique : 0 visite réussie sur 3, refus enregistré par l'Arena. **Soirée (campagne 128) : voir le dernier
  paragraphe.** Elle est configurée dans `identite-soiree.yaml` : sujet et témoin négatif à 24 visites espacées de 10
  minutes, 15 pages par visite ; sentinelle à 6 visites ; témoin classique à 4 visites. Limites : chaque visite relit les mêmes
  pages (la liste, puis les premières fiches) : le suivi est régulier, pas varié ; une campagne reprise repart sans attendre,
  car l'état de la cadence est en mémoire ; `recolte reprendre --maintenant` ne lève pas l'alerte d'une identité, bien que
  le message le conseille ; `--identite` n'est lu que par `lancer` ; la récolte en plusieurs visites avec attente (§ 5.6) et
  l'identité par défaut au nom de la recette ne sont pas faites ; « même visiteur » avec un vrai Chrome n'est vérifié que
  par les essais, à 3 visites ; les noms d'identité sont à usage unique (la sentinelle reste bannie). Preuve : tests écrits
  d'abord (`329f438`, en échec avant le code, puis `4b5fee2` pour le témoin), code `77bdc41` et `353ec91` (fusion `b224227`),
  puis `1f7c7ee` (fusion `91fa5f9`) ; suite complète : 2 097 tests verts (16/11, 8 min 31 s), puis 2 055 tests rapides verts
  après le correctif du témoin. Décidé par : coordination (Ethan a laissé la main : « je te laisse tout continue a
  travailler sur d'autre chose »).
  **Soirée, campagne 128 (16/11) : non tenue** (`shadowlab soiree bilan 128`, code 1). Profil `endurance`, 4 bras, un monde
  par bras, visites espacées de 10 minutes ; lancée à 4 h 03, finie vers 8 h 20. **Sujet** (`noezia` natif, identité
  `soiree-sujet-1`) : 24 visites faites, **3 réussies**. À la visite 4 (4 h 40), l'Arena l'arrête sur le score composite 0,65
  (seuil 0,5 de l'`endurance`), fait de deux signaux du détecteur `comportement` : `duree_pages_reguliere` (CV des durées de
  page 0,19, seuil 0,2) et `navigation_lineaire` (pages toutes distinctes, aucun retour en arrière). Dans l'`endurance`, un
  arrêt bannit le visiteur (D-92) : les photos de la fiche suivante, puis la fiche AN-000005, reçoivent un 403 ; l'identité
  passe en `alerte` (1 h). Visites 5 à 9 : l'outil refuse de lancer Chrome. Visite 10 : 403 dès la première page, identité
  `banni`. Visites 11 à 24 : refusées par l'outil. Critères : visites réussies non tenu ; même visiteur et même empreinte E non
  tenus (19 et 20 visites sans visiteur ou sans E noté, faute d'avoir été faites) ; défi seulement à la 1ʳᵉ visite tenu ;
  aucune alerte non tenu (visites 4 et 10, 1 bannissement dans le monde). **Témoin négatif** (même moteur, profil neuf à chaque
  visite) : 4 visites réussies, arrêté à la 5ᵉ comme prévu (5ᵉ session neuve de même empreinte en 24 h), puis banni (20
  bannissements dans son monde) : tenu. **Témoin de sentinelle** (identité `soiree-sentinelle-1`, bannissement manuel prévu
  avant la visite 3) : arrêté dès la visite 2 par la même règle que le sujet (score 0,65 : CV 0,20 et `navigation_lineaire`),
  avant le bannissement prévu ; identité en `alerte`, visites 3 à 6 refusées par l'outil, jamais `banni`. Le bannissement
  manuel est bien écrit. Après le refus de ses photos, le moteur a demandé encore une fiche (et l'appel de données de la fiche
  en cours) : le bilan compte 2 pages après le premier refus. Tous les critères sont non tenus, sauf « bannissement écrit ».
  **Témoin classique** (`playwright`) : 0 visite réussie sur 4, refusé par l'Arena : tenu. **Lecture** : la soirée a fait ce
  qu'elle devait. Sur une longue série, le rythme du moteur pendant une visite est trop régulier et trop linéaire.
  `navigation_lineaire` se lève à presque chaque visite (la récolte va de fiche en fiche sans revenir à la liste) ; un second
  signal faible suffit (CV des durées de page sous 0,2, environ une visite sur quatre à six) pour dépasser 0,5, et le
  bannissement est définitif. Le même signal avait déjà coûté un passage au niveau 07 (campagne 116). Les essais courts (124
  et 127, 3 visites) ne l'avaient pas montré. **Suite décidée par la coordination** : on ne touche pas à l'Arena (c'est elle
  qui juge) ; on corrige le moteur pendant une visite, avec un ordre de lecture moins linéaire (retour à la liste) et des
  durées de page plus dispersées, sans dépasser le nombre de pages qu'une visite compte aujourd'hui. Puis on relance la
  soirée avec de nouvelles identités. La décision sera écrite avec la correction.
- **D-94 — 16/11/2026 — Lecture humaine de la visite et refus d'une ressource par la sentinelle (moteur).**
  **Cause.** La soirée du 16/11 (campagne 128) n'a pas tenu : le sujet est arrêté à la 4ᵉ visite par le score 0,65
  (`duree_pages_reguliere` et `navigation_lineaire`), puis banni ; la sentinelle est arrêtée dès la 2ᵉ visite de la même
  façon. On corrige le moteur, pas l'Arena. Le réglage se fait sur les données du labo (campagne 128), jamais sur les
  sessions du site public. **Décision.** (1) Option `Options.lecture` du moteur `noezia`, éteinte par défaut, allumée par le
  scénario `visite` (`engines/noezia/lecture.py`, `parcours.py`, `moteur.py`) : durées de page log-normales (minimum 1,5 s,
  médiane 4,5 s, maximum 30 s) tirées par blocs de trois pour que chaque début de visite soit dispersé ; une page sous 5 s est
  parcourue vite (interaction légère) ; retour obligatoire à la liste après la première fiche, puis retours et fiches déjà lues
  revues au hasard, pris sur le budget de pages de la visite, jamais en plus. (2) Sentinelle (`sentinelle.py`) : un 403 sur une
  ressource ou un appel de données du même hôte arrête avant toute navigation (banni sur la première page, ~~sinon alerte~~
  ; révisé par D-103 : sinon alerte, sauf motif `bannissement` lu dans le corps du refus, qui bannit).
  (3) Une relecture respecte `robots.txt`, son `Crawl-delay` et les hôtes de la recette (D-70). Preuve : tests écrits d'abord
  (`d9549c2`, en échec avant le code), code `3145957`, test `a378418`, correctif `7827fa1`, fusion `6a751e5`.
  **Essai 129** (`configs/experiments/identite-rythme-essai.yaml`, sujet seul) : 8 visites sur 8 réussies, 1 visiteur, 1
  empreinte E, défi à la 1ʳᵉ visite seulement, aucune alerte. Le bilan dit « non mesuré » pour les témoins : normal, l'essai n'en
  a pas. **Essai 130** (`identite-soiree-essai.yaml`, 3 visites) : tenu à tous les critères. Sujet : 3 sur 3. Témoin négatif :
  arrêté à la 5ᵉ visite, 2 bannissements. Sentinelle : refus à la 3ᵉ visite comme voulu, 0 page après le refus, identité notée
  `banni`. Témoin classique : 0 sur 3, refus de l'Arena. **Soirée 131** (`identite-soiree.yaml`, 16/11, de 9 h 53 à 14 h 32) :
  **TENUE à tous les critères.** Sujet : 24 visites réussies sur 24, 1 visiteur, 1 empreinte E, défi émis à la 1ʳᵉ visite
  seulement, aucune alerte, 0 bannissement ; durée moyenne d'une visite : 122 s. Témoin négatif : arrêté à la 5ᵉ visite comme
  attendu, 20 bannissements dans son monde. Sentinelle : refus à la 3ᵉ visite comme voulu, 0 page demandée après le refus,
  identité notée `banni`. Témoin classique : 0 visite réussie sur 4, refus de l'Arena. **Réserves.** Une seule soirée, une
  machine, un Chrome sur macOS. Profil `endurance` sans CAPTCHA. Aucun humain qui revient (I8). L'Arena est la nôtre, et le
  rythme a été réglé contre ses propres détecteurs. Décidé par : coordination.
- **D-95 — 16/11/2026 — Calibrage de quatre règles sur un humain connu (Arena, détecteurs).**
  **Origine.** La coordination a demandé à Ethan : « Tu sais qui a fait ces deux sessions ? ». Il a répondu : « Oui, je les
  connais ». Les deux sont `c7c5142c` et `0b1a476b` (Edge 157 sur Windows, 16/11, 29 s, 2 pages : elle passe partout, trop
  courte pour juger). `23a7b8a2` n'en fait pas partie, elle reste non confirmée. La session `c7c5142c` du site public (16/11, Chrome 157 sur Mac, 10 pages), est donc un humain connu,
  sur ordinateur, dans un vrai Chrome. Elle était arrêtée de 05 à 07 et en `endurance` dès la 4ᵉ page par le score composite
  0,85 : `trajectoire_lineaire` (poids 0,6) plus `navigation_lineaire` (0,25). Elle était aussi signalée par `deltas_uniformes`
  et `scroll_timing_regulier`. La condition posée le 15/11 (« sera corrigée dès qu'un humain connu sur ordinateur… ») est donc
  remplie. **Méthode.** Pour chaque règle : un défaut de construction se corrige ; un seuil statistique se dit tel quel, avec
  le nombre d'humains connus. **Aucun seuil chiffré ne change.** **Les quatre règles corrigées** (défauts de construction) :
  (1) `trajectoire_lineaire` (détecteur `entropie-interaction`, 1.1 → 1.2). Défaut : une seule page sous 0,08 suffisait. Chez
  cet humain, 5 relevés de page sur 17 sont sous 0,08, mais la moyenne cumulée de la session ne descend jamais sous 0,095
  environ. La règle juge maintenant la moyenne des angles de toute la session, sur les pages d'au moins 10 angles ; il en
  faut au moins 3, et 60 angles en tout. Seuil 0,08 et poids 0,6 inchangés. Un seul signal par session. (2) `deltas_uniformes`
  (détecteur `scroll`, 1 → 1.1). Défaut : des petits deltas entiers (pavé tactile, défilement doux) ont peu de valeurs
  différentes, sans être un pas fixe. Il faut maintenant qu'au moins 90 % des deltas aient la même valeur. (3)
  `scroll_timing_regulier` (même détecteur). Défaut : Chrome envoie `scroll` une fois par image (16,7 ms) pendant un geste
  continu, donc tout humain paraît régulier. Plus aucune conclusion quand le délai médian est sous deux images (33 ms). (4)
  `screen_position_zero` (détecteur `position-fenetre`, 1 → 1.1). Défaut : une fenêtre agrandie sous Windows est à 0,0. La règle
  ne vaut plus que sans barre de navigateur (hauteur extérieure moins hauteur intérieure sous 40 px). Sans relevé de fenêtre,
  elle s'applique comme avant. **`navigation_lineaire`** : c'est un seuil, pas un défaut ; inchangé. Les 4 premières pages de
  cet humain sont vraiment distinctes, et son poids de 0,25 n'arrête personne seul. Un seul humain connu en juge (deux si Ethan
  confirme `23a7b8a2`). **Tests.** `tests/test_detecteurs_calibrage_humain.py` : 26 tests, données fabriquées, aucune donnée de
  visiteur ; 9 échouaient sur l'ancien code. `tests/test_detection.py` est ajusté : le robot à trajectoire droite fait
  maintenant 3 pages de 22 angles. **Rejeu de la base publique** (lecture seule) : `c7c5142c` passe de 01 à 07 et en
  `endurance` ; `23a7b8a2` (Chrome sur Windows, 14/11, non confirmée comme humain connu) passe maintenant aussi de 05 à 07 ;
  `414f351a` (navigateur intégré de l'application Claude) est toujours arrêtée dès 03, par `chrome-apis` et `comportement` :
  inchangé ; les autres sessions passent comme avant. **Campagne 108** (labo, lecture seule) : l'ancienne règle arrêtait 3
  passages du moteur (34332 au niveau 04, 34342 et 34366 au niveau 05) ; il y avait 3 pages sur 2 134 sous 0,08, pour des
  moyennes cumulées de 0,695, 0,780 et 0,572 ; la nouvelle règle n'en arrête aucun. **Robots toujours pris.** Dans les
  campagnes 115 et 117, `patchright` sans tête (45 passages) et `patchright-chrome-mobile` (85 passages) n'ont aucune barre de
  navigateur et sont à 0,0 : `screen_position_zero` les arrête toujours. Les vrais Chrome ont une barre d'au moins 40 px et ne
  sont pas à 0,0. **Campagne de contrôle 132** (16/11, `controle-vrai-chrome.yaml`, le fichier de la 115, niveaux 04, 05 et 06 sans corrélation, 135 passages) : mêmes taux que la 115, la 118, la 121 et la 125, dans les 9 cellules. `noezia` natif : 15, 15 et 15 sur 15. `patchright` : 0, 0 et 0 sur 15. Chrome sans comportement (`patchright-chrome-interface`) : 10, 15 et 0 sur 15. `screen_position_zero` (`position-fenetre` 1.1) se déclenche toujours sur les 45 passages de `patchright` sans tête, comme dans la 125. `trajectoire_lineaire`, `deltas_uniformes` et `scroll_timing_regulier` ne se déclenchent sur aucun des 135 passages, ni dans la 125 ni dans la 132. La campagne ne juge donc pas ces trois règles : seul le robot fabriqué des tests montre qu'elles prennent encore un robot. Les nouvelles versions des détecteurs (1.2, 1.1 et 1.1) sont enregistrées dans les passages. **Limites.** Un robot qui trace des droites
  sur une ou deux pages seulement, ou qui mélange droites et courbes, passe. Un pas de molette presque fixe (moins de 90 %
  identiques) échappe à `deltas_uniformes`. Un défilement par `requestAnimationFrame` échappe à `scroll_timing_regulier`. Une
  fausse hauteur extérieure échappe à `screen_position_zero` (`outer_eq_inner` devrait encore le prendre ; non testé). La marge
  de l'humain est mince : 0,095 contre un seuil de 0,08, avec un seul humain connu sur ordinateur. Non traité, question
  ouverte : une vraie molette à crans (deltas de ±100 tous égaux) est toujours signalée par `deltas_uniformes` et
  `scroll_regulier`. Révise, pour ces deux règles, la décision du 15/11 « aucune règle ne change ». Décidé par : coordination, à
  la demande de la session de coordination ; Ethan a laissé la main : « je te laisse tout continue a travailler sur d'autre
  chose ».
- **D-96 — 16/11/2026 — Course de 7 jours (I9) avant les humains qui reviennent (I8), et ses règles.**
  **Ce qu'a dit Ethan.** À la question « Je lance l'essai sur 7 jours (étape I9) ? Le Mac ouvrira des fenêtres Chrome par
  moments pendant toute la semaine, comme pendant la soirée. », Ethan a répondu : « Oui ». C'est aussi sa réponse à la
  question 4 de la conception (§ 10). Ce n'est pas une réponse aux questions 1 à 3. **Exception à l'ordre du § 7.** I9
  dépendait de I3, I6, I7 et I8 ; elle part avant I8. Pourquoi : la seule suite prévue de I8 est de monter les seuils
  (conception, I8 : « Sinon les seuils montent… avant I9 »). Une course réussie contre les règles d'aujourd'hui, plus
  sévères, reste donc valable. Réserves : une course ratée serait ambiguë, et les règles de retour de l'Arena ne sont pas
  validées sur des humains. Sans compte connecté (recommandation de la question 2, comme la soirée). I8 reste à faire en
  parallèle ; il attend Ethan.
  **Isolation.** La course tourne dans une copie figée du code : un git worktree détaché à une étiquette, sous
  `.courses/i9/`, à la racine du projet. Elle a ses propres ports : site 8760, frontal TLS 8753, Nginx 8761. Elle a sa
  base, ses sorties et ses identités sous `.courses/i9/outputs/`. Elle a son projet Docker `shadowlab-course-i9` et son
  image `shadowlab-coraza:shadowlab-course-i9`. La composition et `arena/pile.py` lisent `SHADOWLAB_ARENA_PROJET` ; sans
  la variable, rien ne change. **Preuve, pendant la répétition** : dans le dossier principal, `arena appliquer` avec puis
  sans `SHADOWLAB_PROFILS_EXTRA`, une campagne courte (133) et la suite complète (2 244 tests verts) n'ont rien changé aux
  conteneurs ni aux fichiers générés de la course (`scripts/course.sh empreinte`). Les conteneurs du dossier principal,
  eux, ont bien été recréés.
  **Le dossier, et pourquoi là.** Hors de `.claude/worktrees/` : l'archivage d'une session supprime ce dossier. Dans le
  projet : la règle « pas de `rm -rf` hors du projet » le couvre, et ce n'est pas un nouveau projet sous `~/dev`. Caché et
  ignoré par git (`/.courses/`). Vérifié le 16/11 : la consolidation du soir ne parcourt que les projets Basic Memory qui
  ont un `notes/ia/`, et l'index du cerveau ne lit que `notes/` et `docs/` à la racine du projet ; le dossier n'est donc
  ni consolidé ni indexé. **Exempté de la règle « retirer un worktree fusionné »** jusqu'au bilan de la course : un
  worktree détaché à une étiquette passe toujours `merge-base --is-ancestor`.
  **Règles de la course** (`course.py`, `espacement.py`). (1) Visite manquée : créneau pris plus de 10 min en retard
  (`RETARD_MAX_MIN`), ou réveil hors plage ; elle n'est pas jouée, elle est notée `retard`, puis on replanifie. (2) Panne
  de l'Arena ou du site avant une visite : notée `infrastructure`, réessayée 5 min plus tard
  (`REESSAI_INFRASTRUCTURE_MIN`), identité intacte, le créneau compté une fois. (3) Les notes vont dans
  `<sorties>/campagnes/<n°>/cadence.jsonl`. (4) La cadence reprend les visites faites (base, plus les visites coupées
  notées `interrompue`) par `Ordonnanceur.rejouer`, sans modifier l'ordonnanceur. (5) Échéance `jours: 7`, comptée de la
  création de l'expérience. (6) La porte n'est jugée trop tôt que sous la durée du profil moins 60 s
  (`TOLERANCE_PORTE_S`). L'âge de la porte au retour se compte depuis sa dernière validation (`defi-js` / `valide`) jusqu'à la
  première émission du retour : une photo puis la page suivante ne font qu'un seul retour (`fa88df6`). (7) Récolte incrémentale portée par le scénario `visite`, avec un dossier durable par bras
  (`campagnes/<n°>/recolte/<libellé>-<protection>/`), pas par `recolte lancer`, qui vise le site sans jeton, donc sans
  profil de l'Arena. (8) Vitrine de 300 annonces. (9) Témoins négatif, de sentinelle et classique à 10 min d'intervalle le
  premier jour. (10) Bilan : `shadowlab course bilan <n°>` (`scripts/course.sh bilan <n°>`), un verdict par critère du
  § 6.3. (11) Contrôle : `shadowlab course etat [<n°>] [--session vivante|absente] [--json]`, appelé par `scripts/course.sh etat [<n°>]`
  (`d2932bc`). Il montre : en cours, arrêtée ou finie ; le jour et l'échéance ; la dernière activité ; par bras, les visites, les
  manquées, la prochaine visite et le retard, l'identité. Codes de sortie : 0 en cours ou finie ; 1 arrêtée ; 2 retard de plus de
  30 min, ou visite en cours depuis plus de 60 min, ou 2 visites prévues manquées de suite ; 3 introuvable ou erreur d'usage. La
  cadence écrit une note `prevue` dans `cadence.jsonl`.
  **Disque.** Ce qu'a écrit la soirée 131 : environ 18 Mo en base, 4 Mo de journaux de l'Arena et 100 Mo par profil
  d'identité. La répétition 2 a écrit 106 Mo. Estimation pour la course : environ 1 Go, second `.venv` compris (533 Mo).
  Mesures : 12 Gio libres le 16/11 à 15 h 43, 9,8 Gio après la préparation du dossier, 30 Gio le 17/11 à 8 h 41, 29 Gio à 11 h 02 (de la place a été libérée hors du projet ; règle de la coordination : pas de départ sous 20 Gio libres). Aucune place à
  faire. Dans le projet, ce qui pèse n'est pas un cache : des sauvegardes de la base (603, 129 et 80 Mo) et des identités archivées
  (565 Mo) ; c'est à Ethan de décider.
  **Répétitions.** (1) **16/11, 17 h 11 : non tenue.** Prouvé : l'isolation ; l'arrêt brutal puis la reprise (même visiteur
  `73855330`, visite coupée notée `interrompue`) ; la panne de Docker (2 visites notées `manquee/infrastructure`, aucune alerte) ;
  la récolte (30 annonces sur 30, 420 champs sur 420). Cause, à la visite 11 : la porte revenait pendant une relecture de la lecture
  humaine ; le défi de l'Arena est servi en 403 et la relecture le prenait pour une alerte. Corrigé : fusion `bb14c58` (`_relire`
  passe par `_porte_en_cours` ; aucune visite pendant une alerte de l'identité). (2) **16/11, 19 h 23 : non tenue**, arrêtée seule à
  19 h 33, personne ne l'a vu pendant 13 heures. La porte de 600 s a expiré pendant la visite 3 du sujet ; l'Arena a servi à deux
  photos chargées au défilement son motif JSON `{"bloque_par":"defi-js"}` en 403 ; le moteur l'a pris pour un bannissement :
  identité `banni`, 197 visites non faites. L'Arena n'a rien banni (aucune ligne dans `bannissements`). Témoins tous tenus ; sujet
  2 visites réussies sur 3 ; récolte 30 sur 30 et 420 sur 420 ; 2 passages de la porte, écart le plus court 602 s. Corrigé : `a3d56e4`
  (un défi sur une ressource n'est plus un bannissement ; la page ou le JSON `bannissement` en restent un, sur une page comme sur
  une photo ; le moteur ne recharge rien, la page suivante repasse la porte), `d2932bc` (`course etat`, règle 11), `fa88df6`
  (règle 6). (3) **17/11, de 9 h 15 à 10 h 41, tenue**, étiquette `course-i9-repetition-3` = `a3d56e4`, bilan fait avec le code de
  `fa88df6` (qui ne change que le bilan). Déjà prouvé : l'isolation refaite (conteneurs principaux recréés à 9 h 15 min 46 s,
  empreinte de la course inchangée) ; arrêt brutal à 9 h 29 min 00 s (`kill -9` du groupe de processus pendant la visite 5 du sujet,
  aucun survivant, `course.sh etat` répond « arrêtée », code 1) ; reprise à 9 h 29 min 18 s (même visiteur `9d0650de`, visite 5
  notée `interrompue` avec 2 pages, visite suivante réussie à 9 h 32 min 47 s, la sentinelle bannie n'a relancé aucune visite) ;
  Docker arrêté à 9 h 35 min 41 s (note `manquee/infrastructure` à 9 h 37 min 41 s, Docker relancé à 9 h 37 min 42 s, aucune
  alerte) ; témoins : négatif arrêté à la 5ᵉ visite, sentinelle refusée à la 3ᵉ (identité `banni`), classique 0 visite réussie sur 3.
  Un défi sur une photo ne s'est pas présenté en vrai : la porte a expiré 1 s après la fin de la visite 3, puis a été repassée en page
  à la visite 4. Bilan : **TENUE à tous les critères**. Code 0 de `course bilan 1`, avec le code de `a3d56e4` comme avec celui de `fa88df6`. Finie seule à l'échéance à 10 h 41 ; `course etat` répond « finie ». Sujet : 30 visites réussies sur 30 ; 1 visiteur et 1 empreinte E ; aucune alerte, 0 bannissement ; 8 passages de la porte (600 s) : 7 au début d'une visite, 1 au milieu de la visite 11, sur un retour à la page de liste (`porte_repassages` = 1) ; âge le plus court au retour 603 s ; récolte : 30 annonces sur 30 et 420 champs exacts sur 420, en 29 passes ; 1 visite manquée (infrastructure) et 1 visite interrompue, notées à part ; 170 visites non faites à l'échéance. Témoins tenus : le négatif est arrêté à la 5ᵉ visite (2 bannissements) ; la sentinelle est refusée à la 3ᵉ visite, ne demande aucune page après le refus, identité `banni` ; le classique fait 0 visite réussie sur 3, refusé par l'Arena. Pendant la répétition, la suite complète a tourné dans le dossier principal : 2 345 tests verts en 9 min 11 s. Sorties gardées dans `.courses/repetition-3-2026-11-17` (125 Mo).
  **Essai ciblé de la porte** (17/11, 10 h 48 à 11 h 01, demandé par la coordination avant le départ). But : revoir dans un vrai Chrome, devant la vraie Arena, le cas qui a fait tomber la répétition 2 (la porte expire en pleine visite). Code figé : étiquette `course-i9-essai-porte` = `da41a39`, dans le dossier de la course. Réglage : profil `enduranceporte150`, porte de 150 s (`configs/arena/profils-endurance-essai-porte.yaml`) ; pas 60 à 120 s, parce qu'un défi revenu moins de 120 s après le précédent passe par la branche « rafale » du moteur, qui n'est pas celle de la vraie course. Vitrine de 60 annonces ; 3 visites du sujet en espacement fixe d'1 min, 40 pages au plus (`configs/experiments/essai-porte-en-visite.yaml`, `configs/courses/i9-essai-porte.env`). Visite 1 : porte validée à 10 h 48 min 47,8 s ; à 10 h 51 min 19,9 s, 152 s plus tard, les photos `AN-000019` et `AN-000020` reçoivent le défi (403), même cas et mêmes photos que la répétition 2 ; le moteur le note `porte_ressource` (`defi: arena`, écart 146 s, hors rafale), sans alerte ; la page suivante (`AN-000018`) reçoit le défi 0,9 s après et la porte est repassée à 10 h 51 min 22,6 s (`porte_repassage`, rang 19) ; visite réussie, 34 pages, 1 repassage. Visite 2 : porte repassée au milieu de la visite, sur une page (`AN-000043`, rang 46, écart 157 s) ; réussie, 29 pages, 2 passages. Visite 3 : réussie. Fin : identité `ok`, 0 ligne dans `bannissements`, 1 visiteur et 1 empreinte E. Bilan, bloc du sujet : tous les critères tenus ; 5 passages de la porte ; âge le plus court au retour 152 s (durée 150 s, tolérance 60 s) ; récolte 60 sur 60 et 840 champs exacts sur 840 ; verdict global « non mesuré », faute de témoin. Sorties gardées dans `.courses/essai-porte-2026-11-17` (108 Mo). Ce point est donc vérifié, une fois.
  **Rythme et surveillance.** Rythme gardé : 45 à 180 min (D-90), sans changement, tranché par la coordination. Ethan a dit « Oui » à
  « par moments », pas à « une visite toutes les 1 à 3 h » (formulation de la question 4). Un contrôle après les témoins du premier
  jour, puis un au plus par jour, avec `scripts/course.sh etat` ; un code différent de 0 veut dire qu'il faut regarder. Pour la
  répétition seulement, toutes les commandes `course.sh` (`etat`, `bilan`, `reprendre`) exigent
  `COURSE_ENV=configs/courses/i9-repetition.env`, sinon le profil `endurancecourt` est inconnu et elles sortent en 3 ; la vraie course
  ne passe pas de `COURSE_ENV`.
  **Lancement prévu** (rien d'exécuté) : (1) `git tag -a course-i9 -m "Course I9 (7 jours)"` sur le commit qui porte cette version de D-96 ;
  (2) vérifier que `.courses/i9/outputs` est absent (les sorties de l'essai ciblé sont déjà rangées dans `.courses/essai-porte-2026-11-17`) ; (3) `git -C .courses/i9 checkout --detach course-i9 && (cd .courses/i9
  && uv sync)` ; (4) `scripts/course.sh demarrer configs/experiments/identite-7-jours.yaml`, sans `COURSE_ENV` ; (5) ensuite
  `scripts/course.sh etat | reprendre <n°> | bilan <n°>`. Étiquette `course-i9` sur le commit qui porte cette version de D-96 ; depuis `da41a39`, il n'ajoute que des documents. Pendant la course, ne jamais changer de commit dans `.courses/i9` : un outil plus récent, en lecture seule, se lance depuis le dossier principal. **Code répété et code étiqueté** : la répétition 3 a tourné sur `a3d56e4`. Entre `a3d56e4` et `da41a39`, le code n'a changé que dans `src/shadowlab/course.py`, le calcul du bilan (`fa88df6`) ; le reste, ce sont des tests et trois fichiers de configuration de l'essai (`configs/arena/profils-endurance-essai-porte.yaml`, `configs/courses/i9-essai-porte.env`, `configs/experiments/essai-porte-en-visite.yaml`), qu'aucune lecture de la vraie course ne charge. Lancée
  seulement quand la coordination le dit.
  **Lancée** le 17/11 à 11 h 21 min 14 s, départ accordé par la coordination : campagne 1 de la base de la course, graine 20261117,
  échéance le 24/11 vers 11 h 21 (`course etat`). Étiquette `course-i9` posée sur `d5983d7` et poussée. Avant le départ : les deux
  conteneurs de l'essai (porte de 150 s) retirés, puis recréés neufs à 11 h 21 min 13 s ; configuration générée sans autre profil
  qu'`endurance` ; un dossier de sorties vide créé à 11 h 19 par une commande de contrôle, retiré. Premières visites (11 h 21 à
  11 h 23) : sujet réussi (9 pages, identité `ok`, visiteur `0405c585`), témoin sentinelle réussi (11 pages), témoin négatif réussi
  (12 pages), témoin classique arrêté (0 page, comme voulu). Porte du sujet : défi émis à 11 h 21 min 25,6 s, validé à 11 h 21 min
  27,2 s ; cookie `sl_defi` de 86 400 s dans son Chrome (jusqu'au 18/11, 11 h 21 min 27 s) ; `duree_porte_s` = 86 400 au passage.
  `scripts/course.sh etat`, lu sans tube : code 0, prochaine visite du sujet à 12 h 58.
  **Non vérifié** : les nuits et le passage d'une journée à l'autre ; la vraie porte de 24 h ; une vraie mise en veille du Mac ; le
  plafond de 200 pages par jour ; un profil Chrome qui tient 7 jours ; `course etat` : une seule visite prévue manquée la nuit
  donne encore 0, et un blocage hors attente et hors visite ne se voit qu'à « dernière activité » ; le code 0 ne veut pas dire
  « critères tenus » (une identité en alerte le laisse à 0) : lire aussi la ligne de l'identité, et `df -h /`, que `course etat`
  ne suit pas ; la vraie configuration (`identite-7-jours.yaml` : profil `endurance`, porte de 24 h, vitrine de 300, plage 8 h à
  23 h) n'a jamais démarré : le lancement est son premier départ ; un 403 de ressource dès la première page dont le corps n'est
  pas un défi reconnu (page du WAF ou de Nginx, motif inconnu, corps illisible) vaut toujours `banni`, sans retour ; une mise à
  jour de Chrome pendant la semaine.
  Décidé par : coordination, sur le « Oui » d'Ethan.
  **Résultat (constat du 18/11 à 0 h 31) : course NON TENUE.** Le sujet est banni à sa 6ᵉ visite (17/11, 21 h 43, passage 19 de la base de la course) : `composite` 0,6 (seuil 0,5), signaux `pas_de_scroll` et `navigation_lineaire`, après une fiche et la liste quittées en 4,4 s et 3,4 s sans défilement ; même fenêtre qu'à la visite 5. Puis la visite ne se termine pas (plus de 3 heures `en_cours`, identité encore notée `ok`). Avant : 5 visites réussies, 1 visiteur, 1 empreinte E, 67 annonces sur 300 ; les trois témoins tiennent tous leurs critères. Deux défauts du moteur (rythme de lecture, visite sans fin), à corriger tests d'abord avant toute nouvelle course ; l'Arena ne change pas.

- **D-97 — 17/11/2026 — Site public : le visiteur voit son résultat à la fin de la session, niveau par niveau, et peut le partager.**
  **Ce qu'a dit Ethan.** Le 17/11, à la proposition de montrer au visiteur, à la fin, si nos détecteurs l'ont pris pour un
  humain ou un robot : « oui bonne idee ». Les choix ci-dessous sont ceux de la session chargée du travail, transmis à la
  coordination. **Le calcul.** Quand la session est terminée, le site lance un sous-processus du laboratoire
  (`python -m shadowlab.resultat_public`, jeton sur l'entrée standard, jamais dans les arguments). Il ouvre la base publique
  en lecture seule et refait la décision des niveaux 01 à 07 avec `rejeu._rejouer_session(..., publique=True)` : aucune
  règle recopiée, aucun niveau ajouté (`SHADOWLAB_PROFILS_EXTRA` est retirée). Le site public n'importe toujours aucun
  module du laboratoire. Coût mesuré : de 0 à 0,5 s par session réelle (base publique en lecture seule, 7 sessions,
  jusqu'à 18 pages), 0,43 s pour 8 pages fabriquées ; il croît à peu près comme le carré du nombre de pages. Garde-fous :
  priorité basse (`nice` 10), un calcul à la fois pour tout le site, 30 s au plus puis le sous-processus est tué, aucun
  calcul au-delà de 80 pages. Le site attend 4 s ; au-delà, une page « calcul en cours » se recharge seule vers « Ma
  session » (sans script). **Rien de plus stocké.** Le résultat reste 15 minutes en mémoire, un échec 2 minutes (sinon chaque
  rechargement relancerait un calcul) ; il est recalculé si le visiteur rouvre « Ma session » plus tard, et oublié quand
  il supprime sa session. **Ce qu'on montre.** Le verdict de chaque niveau (« Humain » ou « Robot ») ; une phrase de tête
  sur les niveaux 02 à 07, car le 01 n'a aucune protection ; les raisons en six familles de mots simples (traces
  d'automatisation, gestes, navigateur incohérent, fonctions modifiées, petits indices additionnés, lien ou champ piège),
  jamais un nom de détecteur ni de signal ; celles du moment où un niveau aurait arrêté la session. Un message honnête :
  un humain pris pour un robot est une erreur de nos détecteurs, ce que l'étude cherche. **Pas d'oracle en cours de
  route.** Aucun résultat tant que la base dit la session en cours, même si le visiteur retire le cookie de session.
  **Seuil : 4 pages avec empreinte.** Plusieurs règles ne jugent qu'à partir de 3 ou 4 pages (trajectoire de la souris,
  régularité des durées, navigation linéaire) ; en dessous, « Humain » voudrait seulement dire « pas encore jugé ». Sous
  le seuil, « Terminer » ne clôt pas la session : la page « Encore un peu » propose de continuer, ou de terminer quand
  même, sans verdict. **Notice.** Version `2026-11-17.1`, puis `2026-11-17.2` (elle annonce aussi la page « Encore un peu », qui dit que la
  session reste ouverte) : nouvelle section « Votre résultat », « plus tard et hors ligne »
  devient « plus tard ». Une session acceptée sous une notice plus ancienne n'a pas de résultat (elle n'avait pas été
  annoncée). **Partage.** Le bouton (`partage.js`, fichier statique en liste fermée) ouvre le partage du téléphone, sinon
  copie la phrase du score et l'adresse nue du site (`location.origin` + « / ») : rien de la session. Le bouton de fin
  devient « Terminer et voir mon résultat », et l'accroche de l'accueil promet le résultat. **Limites.** Le résultat ne
  juge que l'empreinte et le comportement : ni TLS, ni HTTP/2, ni corrélation entre sessions, ni défis, ni CAPTCHA, ni
  WAF. Un auteur de robots peut s'en servir comme banc d'essai : familles seulement, à la fin seulement, plafond de
  sessions par jour inchangé. Les partages faits pendant le tunnel rapide mourront avec son adresse : un nom d'hôte
  stable reste à la charge d'Ethan. Non essayé : Safari, iPhone, Firefox, et le partage natif sur un vrai téléphone. La
  finalité ne change pas : mesurer et améliorer nos détecteurs ; les sessions publiques ne règlent jamais le moteur.
  **Relecture indépendante** (un agent qui n'a rien écrit) : aucun défaut bloquant. Corrigé : les lectures de la base de
  « Ma session » et de « Terminer » passent par le pool de fils (elles bloquaient la boucle) ; un échec n'est plus gardé
  15 minutes mais 2 ; le seuil de la notice suit `PAGES_MIN`.

- **D-98 — 17/11/2026 — Étape 3.1, essai de fumée Linux : montage et règle « on liste, on ne corrige pas ».** L'Arena d'un essai Linux se monte ainsi : le site, le frontal TLS,
  la campagne, la base et le moteur dans le conteneur Linux ; seule la pile Nginx + Coraza reste sur OrbStack, sous un projet Docker et des ports à part (`fumee-linux`, 8744 à 8746), reliée par deux relais `socat`
  (le code de l'Arena vise des adresses en dur, il ne change pas). Pourquoi : la campagne crée le moteur dans son processus, donc elle doit tourner sous Linux ; la base SQLite est en mode WAL et ne se partage pas ;
  c'est la disposition de l'étape 3.3. Le périmètre reste en mode strict (`localhost,127.0.0.1`). Niveau 06 sans corrélation, comme les campagnes 115 et 132. L'étape ne corrige rien : elle liste (aucun fichier du moteur
  ni de l'Arena modifié). Résultats et incohérences : `docs/recherche/fumee-linux-2026-11-17.md`. Le numéro D-98 est le premier libre au 17/11 sur toutes les branches (D-97 pris par la branche du site public) ; la coordination
  le renumérote à la fusion si une autre branche l'a pris. Décidé par : la session qui a fait l'étape 3.1, montage approuvé par la session de coordination (17/11) ; Ethan avait demandé de continuer le moteur « en attendant » la course.
- **D-99 — 17/11/2026 — Étape 3.2 : un proxy par identité (`proxy.json`) et un relais local qui est le verrou réseau de l'identité.** Constat : pour que deux identités ne se relient pas, elles ne doivent pas sortir par la même
  adresse ; le verrou de D-07 envoie les hôtes autorisés EN DIRECT (liste `bypass`), incompatible avec un proxy. Décision : (1) une identité déclare son proxy (HTTP ou SOCKS5, utilisateur et mot de passe) dans un fichier `proxy.json`
  de son dossier, droits 0600 imposés à la lecture (jamais lisible par un autre) ; **aucune option de campagne ne porte le proxy** (un fichier de campagne est versionné et sa configuration est enregistrée dans la base ; une variable
  d'environnement est partagée par tout le processus) ; l'option `identite` ne nomme que l'identité ; (2) le moteur lance un relais local (`proxy_identite.RelaisProxy`, 127.0.0.1, port libre) qui tient les identifiants ; Chrome n'a pour proxy que
  ce relais, sans identifiant ; le relais joint le proxy de l'identité (`CONNECT` + Basic, ou SOCKS5 avec mot de passe, nom d'hôte transmis tel quel) ; (3) le relais est le verrou réseau de cette identité : Chrome n'a aucun chemin direct, tout hôte
  hors périmètre (hôtes des défis compris) est refusé par nom avant que le proxy soit contacté, **sans résolution locale** (le proxy résout et sort) ; jamais de repli sur une connexion directe ni sur `SHADOWLAB_PROXY` ;
  (4) pour une identité qui a un proxy, Chrome reçoit `--webrtc-ip-handling-policy=disable_non_proxied_udp` (0 paquet UDP direct vers un STUN local ; sans lui 4 ; le nom `--force-…` n'a aucun effet sur Chrome 156) ; (5) `configuration()` enregistre
  `identite_proxy` sous forme masquée (`http://***:***@hote:port`). Sans proxy déclaré : rien ne change. Preuve : tests écrits d'abord (commit `ee72107`, en échec par `ModuleNotFoundError`), code `fa40f7f` ; 162 tests rapides, 40 d'aides, 23 avec un vrai
  Chrome 156 (deux identités, HTTP et SOCKS5, `http://` et `https://`, aucune connexion directe, mauvais mot de passe refusé, périmètre tenu, aucun identifiant dans ce que le moteur enregistre) ; suite rapide 2 492 réussis, suite complète non lancée. Une requête `http://` par connexion est imposée par le relais (corps borné à `Content-Length`, `Transfer-Encoding` refusé : revue de sécurité) ; l'argument WebRTC est déclaré dans `configuration()` (`identite_proxy_arguments`). Limites et fuites : `docs/recherche/proxy-par-identite-2026-11-17.md`
  (§ 5 : ce qu'« deux adresses » veut dire sur un poste ; § 6 : DNS local du mode strict, relais sans authentification, identifiants en clair jusqu'au proxy, effet de l'argument WebRTC sur les détecteurs non mesuré). Aucun vrai proxy essayé.
  **Durcissements après relecture indépendante (17/11, sans nouveau numéro)** : `configuration()` ne lève jamais à cause du proxy (un `proxy.json` inutilisable donne `identite_proxy: "invalide"`, sans rien citer du fichier ; `open()` refuse toujours de démarrer) ; `declarer_proxy` ne suit jamais un lien symbolique (`proxy.tmp` retiré avant l'écriture, puis création `O_EXCL | O_NOFOLLOW`) ; le relais réécrit l'en-tête `Host` d'une requête `http://` sur la cible jugée (RFC 7230 § 5.4) ; 218 tests rapides + 41 d'aides + 23 avec un vrai Chrome, suite rapide 2 549. Décidé par : la session qui a fait l'étape 3.2, à la demande de la session de coordination.
- **D-100 — 17/11/2026 — Exception bornée à D-30 : nos moteurs devant trois pages publiques de test de détecteurs.** Constat : Ethan a demandé s'il fallait tester sur Vinted (« T'en pense quoi de tester sur Vinted ? Je sait qu'il sont très actif contre les bots ça nous permettrai de voir leurs niveau et le notre »). Un site du commerce n'est pas à nous : D-30 n'autorise le contournement
  d'un détecteur que sur cible autorisée (la nôtre, un bug bounty, un système qu'on possède) ; l'assistant a déconseillé et refusé de pointer le moteur dessus sans accord de leur part, et proposé les pages publiques faites pour tester des outils d'automatisation. Ethan a répondu « Oui » à la question
  « Je les prépare : oui ou non ? » (après un message de frappe, « Jien », éclairci par « Je voulais dire hein »). **Décision** : une exception **bornée** à D-30, réservée aux pages conçues pour tester des outils d'automatisation : **Sannysoft** (`bot.sannysoft.com`), **CreepJS** (`abrahamjuliot.github.io/creepjs`, page du projet libre) et
  **rebrowser-bot-detector** (`bot-detector.rebrowser.net`). **BrowserScan est écartée** : c'est un service commercial dont les conditions d'utilisation n'ont pas été lues. Cadre tenu par `scripts/detecteurs-publics.py` : une visite par page et par moteur (quatre moteurs, trois pages, douze visites), une à la fois, 8 s de pause ; aucun défi résolu (`resoudre_defis: false`), aucun CAPTCHA, aucun compte ;
  le cadre principal ne peut aller que sur l'hôte de la page demandée (`hotes_navigation`) et l'adresse d'arrivée est contrôlée ; depuis l'adresse du poste. **Les résultats sont rangés à part des taux de l'Arena** (`docs/recherche/detecteurs-publics-2026-11-17.md`) : ils ne remplacent aucun taux de passage et n'entrent pas dans les tableaux de `docs/PLAN.md` § 2. Cette décision n'autorise ni une autre page, ni un autre site, ni des visites répétées en
  nombre. **Ce qu'on sait de l'accord d'Ethan** : son « Oui » portait sur la *préparation* des pages ; la passe a été lancée une fois par l'assistant dans la foulée, sans question séparée sur le lancement. Décidé par : la session qui a fait la passe ; contrôlée par la coordination (fusion `23781cd`).
- **D-101 — 17/11/2026 — Identité native : le partitionnement du stockage tiers est rétabli (un argument de lancement change).** Constat : `rebrowser-bot-detector` (D-100) marque en rouge `storagePartitioning` pour `noezia` en identité native : une iframe du site B placée dans une page du site A lit le
  `localStorage` de B, ce qu'un vrai Chrome ne permet pas. **Cause** : Playwright, donc Patchright, lance Chrome avec `--disable-features=…` et sa liste contient `ThirdPartyStoragePartitioning` (`chromiumSwitches.ts`, « playwright/issues/32230 ») ; `ignore_default_args` ne filtre que des arguments entiers et exacts, donc on ne peut pas en retirer
  une seule fonction. **Mesures** (vrai Chrome 156, deux sites locaux `localhost` et `127.0.0.1`, sans la page rebrowser) : sans changement `lu=valeur-premiere-partie` (non partitionné) ; avec `--enable-features=ThirdPartyStoragePartitioning` toujours non partitionné (le `--disable-features` l'emporte) ; avec un second
  `--disable-features=…` sans cette fonction : `lu=null` (partitionné) : le dernier remplace le premier. **Décision** : en identité native seulement (lancement `launch` avec `identite_native` et lancement persistant d'une identité), le moteur passe `--disable-features=` + la liste de Playwright MOINS `ThirdPartyStoragePartitioning`
  (`moteur.ARGUMENT_STOCKAGE_TIERS_PARTITIONNE`) ; les autres contournements de Playwright restent coupés (par exemple `BlockOriginHeaderModificationOnRedirect`, dont l'interception des requêtes du moteur dépend). Réglage déclaré dans `configuration()` (`stockage_tiers_partitionne`, vrai en identité native, faux sinon). **La liste est copiée de
  Patchright 1.64.4** : un test (`test_la_liste_copiee_est_celle_de_patchright_moins_le_partitionnement`) la compare à l'installée, une mise à jour qui la change échoue là. **Inchangé** : l'identité réécrite (réglage par défaut) garde le partitionnement coupé, et le même défaut s'y trouve (un test de garde le dit, sans dire que c'est un bien) ; les moteurs `patchright` et
  `playwright` non plus. **Preuve** : tests écrits d'abord et vus en échec (commits `d669e89` et `b7927be` : 5 rouges sur 6, puis l'`ImportError` de la garde), correctif ensuite ; 7 tests (3 rapides sur la configuration, 2 avec un vrai Chrome, 1 de garde du réglage par défaut, 1 de la liste copiée) ; tests du proxy, de l'identité et suite rapide verts (2 553) ;
  **une seule visite de contrôle** de la page rebrowser (D-100) : `storagePartitioning` vert (« Third-party storage is partitioned, as in a normal Chrome »), 16 tests verts, 4 non déclenchés, aucun rouge ni jaune. **Non vérifié** : l'effet sur l'Arena. Le changement d'un argument de lancement impose une campagne de contrôle (`docs/PLAN.md` § 8, règle 2), à lancer par la coordination
  depuis le dossier principal (`controle-vrai-chrome.yaml`) ; point à regarder : les iframes Turnstile et reCAPTCHA (clés de test) des niveaux 05 et 06 voient maintenant un stockage partitionné, comme dans un vrai Chrome ; la raison pour laquelle Playwright coupe cette fonction n'a pas été lue en détail. Décidé par : la session qui a fait l'étape, à la demande de la coordination.
  **Contrôle fait par la coordination (17/11)** : suite complète 2 762 tests verts sur `06319e3` ; campagne 134 (`controle-vrai-chrome.yaml`, 135 passages, pendant la course I9) : mêmes taux que la 132 dans les 9 cellules (`noezia` natif 15 sur 15 aux niveaux 04, 05 et 06 sans corrélation, Chrome sans comportement 10, 15 et 0, `patchright` 0 sur 45). Reste non mesuré : le lancement avec identité persistante, les niveaux 06 et 07 complets.
- **D-102 — 17/11/2026 — Identité native avec interface sur Linux sans carte graphique : un WebGL présent (deux arguments de lancement), et ce que D-50 supposait à tort.** **Ce que D-50 (11/11) supposait** : que sur un serveur Linux sans GPU Chromium se replie sur SwiftShader, dont le script `webgl.js` masquerait les paramètres distinctifs. **Mesuré le 17/11** (conteneur amd64, Xvfb ; Chromium 156, Chrome 157 et 158, tous lancés par Patchright avec ses arguments par défaut) : avec une interface il n'y a pas de repli ; WebGL est **absent**
  (`getContext('webgl')` rend `null` : 90 empreintes sur 90 dans chacune des campagnes 2, 3, 5 et 6 de la base `fumee-linux`, et dans la campagne 7 sans réglage) ; SwiftShader n'existe que sans interface (le « headless shell », campagnes 1 et 4). Le masquage de D-50 n'avait donc rien à masquer pour l'identité native avec interface, (un Chrome lancé à la main n'a pas été essayé : non vérifié).
  **Mesures** (sonde et campagnes courtes 7 à 10, `docs/recherche/webgl-linux-sans-gpu-2026-11-17.md`) : `--enable-unsafe-swiftshader` donne un WebGL SwiftShader que l'Arena marque (`webgl_logiciel`, 24 passages sur 24, un blocage sur 6 au niveau 06) ; `--ignore-gpu-blocklist` donne un WebGL `ANGLE (Mesa, llvmpipe (LLVM 20.1.2 128 bits), OpenGL 4.5)` mais active le canvas 2D accéléré, dont la lecture devient
  instable (10 essais sur 10) : l'Arena relève `getImageData_instable` (24 passages sur 24) et bloque les niveaux 05 et 06 (0 sur 6 à chacun) ; ajouter `--disable-accelerated-2d-canvas` rend le canvas stable (0 sur 10) et laisse WebGL. **Décision** : en identité native, avec interface, sur Linux sans carte graphique (aucun `/dev/dri/*` ni `/dev/nvidia*`),
  le moteur ajoute `--ignore-gpu-blocklist --disable-accelerated-2d-canvas` (`moteur.ARGUMENTS_WEBGL_SANS_GPU`, `arguments_natifs`, `sans_carte_graphique`), pour les deux lancements (natif et identité persistante) ; déclaré dans `configuration()` (`webgl_sans_carte_graphique_arguments`, clé présente seulement là où le réglage s'applique). **Rien ne change** sur macOS, avec une carte graphique, sans interface ni en identité réécrite (tests).
  Choisi parce que, parmi les réglages qui donnent un WebGL, il a la chaîne de moteur de rendu au format des cartes Linux réelles, qu'aucune règle de l'Arena ne marque, et qu'il ne coûte aucun signal de plus (campagne 10 : 24 sur 24, `devices_vide` seul). **Non établi** : quelle part des vrais postes Linux sans carte a un WebGL ; si un Chrome lancé à la main en a un ; `/dev/dri` sur une machine virtuelle réelle (le correctif ne s'y appliquerait pas si un nœud d'affichage existe sans rendu matériel : à contrôler à l'étape 3.3) ; si des détecteurs du commerce marquent llvmpipe ou l'absence de WebGL ; sous Rosetta llvmpipe annonce « 128 bits » (sur un vrai x86_64 on attend « 256 bits »).
  **Remesure** : campagne 11 (identité native, Chrome 158, 90 passages, sans argument injecté) : 15 sur 15 aux six niveaux (campagne 6 : 15, 15, 15, 15, 15, 12), WebGL présent et canvas stable sur 90 empreintes sur 90 ; **pas la preuve que le réglage améliore les taux** (15 passages par niveau, `duree_pages_reguliere` encore sur 5 passages, Chrome 157 vers 158). L'Arena n'est pas modifiée ; une règle « WebGL absent » serait une étape à part. **Preuve** : tests écrits d'abord, vus en échec (commit `78fe124`, 25 rouges, `AttributeError`),
  code ensuite ; suite rapide 2 578 verts, tests du proxy et du stockage tiers avec un vrai Chrome verts. **Tenu en garde** : le crochet `FUMEE_CHROME_ARGS` (le conteneur remplace le binaire de Chrome par un lanceur) est un outil de mesure, jamais utilisé par le moteur. Décidé par : la session qui a fait l'étape, à la demande de la coordination.
- **D-103 — 18/11/2026 — Course I9 tombée à la 6ᵉ visite du sujet : défilement en début de visite et entrée par la liste (défaut A), corps d'un refus attendu un temps borné et motif `bannissement` lu (défaut B) ; moteur seulement.**
  **Constat** (base de la course, lecture seule ; 17/11, 20 h 43 UTC, passage 19) : à la 6ᵉ visite, l'Arena bloque une photo de la 3ᵉ page sur le score
  0,6 (seuil 0,5 d'`endurance`) : `pas_de_scroll` (deux pages défilables de suite, fiche puis liste, 52 mouvements de souris, 0 défilement) et
  `navigation_lineaire` (4 chemins distincts) ; le visiteur est banni (D-92). Puis la visite ne finit jamais : passage `en_cours` plus de 3 heures,
  identité `ok`, aucune requête. **Causes A** (moteur) : (1) une visite qui reprend la passe commence sur la fiche suivante de la file
  (`parcours.py:683` avant correction), donc le retour obligatoire à la liste de D-94 va à une liste jamais vue de la session ; (2) une page sous
  5 s est parcourue vite (D-94) ; (3) l'interaction légère ne défile qu'à 40 % (`moteur.py:751` avant correction) ; (4) trouvé par le banc : en
  passe incrémentale, une fiche évitée sans requête prenait une durée au plan de lecture (`parcours.py:688`), ce qui cassait les blocs de trois.
  **Estimation** (banc sans navigateur, `tests/test_lecture_defilement.py`, code d'avant) : 11 visites bloquées sur les 91 qui reprennent la
  1ʳᵉ passe en commençant sur une fiche (12 %), recoupé par le calcul 0,31 (deux premières pages parcourues vite, mesuré) × 0,36 (aucun défilement
  sur les deux) = 11 % ; risque d'au moins un échec en 5 visites reprises : 47 %. Cause 4 : 2 visites incrémentales bloquées sur 231 (environ 1
  sur 115 ; après correction 0 sur 250). Compatible avec la soirée 131 (24 visites, toutes commencées sur la liste), la répétition 3 (30 visites, une seule commencée sur une
  fiche) et la course (visites 2 à 6 commencées sur une fiche, échec à la 5ᵉ) ; aucun ne le prouve à lui seul.
  **Cause B** : le moteur lit le corps de chaque 403 d'une ressource (`moteur.py:628` avant correction, `reponse.text()`) ; Playwright attend sans
  limite le corps d'une requête qui ne finit pas ; le refus de l'Arena est `no-store` (`gardien.py:108`) et `vitrine.js:37` ne lit pas le corps
  d'une réponse en échec : la requête de l'appel de données ne finit jamais (mesuré dans un vrai Chromium : seulement avec `no-store`).
  **Décision** (l'Arena ne change pas : `detection.py`, `scoring.py`, profils intacts) : (A1) `moteur.py` : la première page défilable de chaque
  visite est toujours défilée, même parcourue vite ; les suivantes gardent le tirage à 0,4. (A2) `parcours.py` : une visite qui reprend la passe
  (lecture humaine allumée) entre par la dernière liste lue, relue et prise sur le budget, sauf s'il reste moins de 2 pages ou si, en passe
  incrémentale, la page n'est pas à revoir. (A3) la durée de lecture n'est tirée que pour une page demandée. (B1) `moteur.py` : le corps d'un
  refus n'est lu qu'une fois sa requête finie (`requestfinished`), attendu au plus 2 s (`ATTENTE_CORPS_MS`), sinon le refus est rendu
  `corps-non-lu`. (B2) `sentinelle.py` : le motif JSON de l'Arena est lu dans le corps (`motif_de_refus`, `RefusRessource.motif`) ; le motif
  `bannissement` bannit l'identité à toute page de la passe (D-91 reste vrai pour les autres refus : `banni` sur la première page, `alerte`
  après) ; un corps non lu ne masque pas un corps lu ; seul, il compte comme un refus franc.
  **Preuve** : tests écrits d'abord et vus en échec (A : `54bbb7c` ; B : `b4b31ff`), code ensuite (A : `80b8ac5` ; B : `55baf97`).
  Suite rapide (`-m "not integration"`) : 2 732 verts, 2 ignorés ; avec un vrai navigateur : les 4 cas du petit serveur et la visite de bout en bout verts (avant correction : 5 sur 5 bloqués, arrêtés par le garde-fou dans `Response.text`), 13 tests voisins verts (identité, récolte par le navigateur, périmètre, témoin) ; lint propre. **Non vérifié** : rien devant la vraie Arena après correction (aucune campagne) ; l'entrée par la liste (porte expirée,
  visiteur banni) n'est vérifiée que sur pilote factice ; le banc ne juge que `comportement` ; un
  défi de la porte servi au seul appel de données n'est pas reconnu (corps non lu : refus franc) ; un refus en page au motif `bannissement` après
  la première page reste une alerte (révisé par D-104 : l'en-tête `X-Arena-Refus` le dit, c'est un bannissement) ; l'attente de 2 s n'est vérifiée qu'en local. **À mesurer avant de relancer une course** : note
  `docs/recherche/course-i9-visite-6-2026-11-18.md` § 5. Décidé par : la session chargée du défaut, à la demande de la coordination.
  **Mesures faites par la coordination sur l'Arena (18/11, profil `endurance`, verdict par `scripts/mesures-d103.sql`)** : campagne 135 (21 visites de 15 pages espacées d'1 min) : 9 visites réussies, 8 reprises entrées par la liste, aucun signal de comportement, puis arrêt à la 10ᵉ par `debit:pages_par_heure` (241 pages comptées en 27 min : rythme de l'essai, pas du moteur) ; la visite 10 finit en 44 s (`alerte`), la 11 est refusée sur sa liste d'entrée (`banni`). Campagne 137 (24 visites de 8 pages espacées de 3 min) : 24 sur 24, 23 reprises entrées par la liste, 0 `pas_de_scroll`, 0 `navigation_lineaire`, 0 `duree_pages_reguliere`, aucun bannissement ; soit 31 visites reprises sans signal avec la 135 (environ 2 % de chances avec le défaut d'avant, à 12 % par visite). Campagne 138 (porte de 150 s) : sujet 5 sur 5, défi repassé sur la liste d'entrée aux visites 2 à 5 ; visiteur banni entre deux visites arrêté sur sa liste d'entrée, identité `banni`, 1 document. Campagne 139 (contrôle) : mêmes taux que la 132 et la 134 dans les 9 cellules. Campagne 140 (vitrine de 30 annonces, 30 visites) : 30 sur 30, 24 passes incrémentales, aucun signal. Campagne 141 (bannissement écrit 60 s après le début de la visite 2) : la page suivante est refusée, la visite finit 3 s plus tard (échec, « statut 403 », identité `alerte`), rien n'est demandé après la page refusée et ses ressources ; campagne arrêtée ensuite. **Non mesuré sur l'Arena** : le cas exact de la course (document servi, puis ses photos et son appel de données refusés), couvert seulement par le test de bout en bout de la suite ; des visites de plus de 15 pages reprises ; l'ordonnanceur ; une nuit ; la porte de 24 h. Une répétition de la course reste à faire avant toute nouvelle course.
  **Répétition 4 et deuxième course (18/11)** : répétition (`course-i9-repetition-4` = `7143d24`, 8 h 34 à 10 h 00) tenue à tous les critères : sujet 32 visites réussies sur 32, aucun bannissement, aucune alerte, 1 visiteur, 1 empreinte E, porte de 600 s repassée 8 fois (âge le plus court au retour 608 s), récolte 30 annonces sur 30 et 420 champs sur 420 en 31 passes ; témoin négatif arrêté à la visite 5, sentinelle refusée à la visite 3 sans page demandée après, témoin classique 0 sur 3. Deuxième course de 7 jours lancée à 10 h 03 sur le mot d'Ethan (« Oui »), étiquette `course-i9-2` = `7143d24`, échéance le 25/11 vers 10 h 03. Non vérifié, comme à la première : les nuits, la porte de 24 h, une veille du Mac, le plafond de 200 pages par jour.
- **D-104 — 19/11/2026 — I10 (comptes) : l'Arena se souvient des comptes au seul profil `endurance` (connexion gardée 30 jours, bannissement du compte, règle « nouvel appareil » à 4 appareils en 24 h), le refus dit son motif dans un en-tête, et le moteur reste connecté d'un lancement à l'autre.**
  **Contexte** : étape 2.3 du plan (I10), confiée par la coordination. Critère du plan : un compte banni est refusé depuis un autre navigateur. Les comptes restent les fixtures locales de `site/comptes.py` (`demo`, `analyste`).
  **Décision, Arena** (seulement là où `bannissement.actif` est vrai, donc `endurance` ; aux niveaux 01 à 07 rien de ce qui suit n'est lu ni écrit, la connexion reste liée au jeton, sans durée) :
  (1) migration 12 : tables `comptes` (un compte par monde) et `appareils` (un visiteur qui s'est connecté au compte : première et dernière connexion, `nouvel_appareil`, `connecte_jusqu_au`), colonne `bannissements.compte` et trois index ; les migrations 1 à 11 ne changent pas.
  (2) connexion durable : le cookie `sl_connexion` est signé pour le monde, le visiteur et le compte (et l'empreinte TLS de liaison si le niveau en a une), posé pour 30 jours (`bannissement.duree_connexion_s`) : il survit à la fermeture du navigateur ; volé par un autre visiteur, il ne vaut rien. La déconnexion clôt la connexion de cet appareil.
  (3) bannissement d'un compte : à la main (`shadowlab arena bannir --compte <id> --monde <nom>`, pour un compte déjà connecté dans ce monde, sinon code 2) ; automatique quand un visiteur est banni alors qu'il est connecté au compte (connexion ni expirée ni close ; motif `visiteur_banni:<motif du visiteur>`) ; par la règle (4). Un compte banni est refusé à la connexion (même avec le bon mot de passe ; un mauvais mot de passe reste un 401) et sur l'espace privé d'une session déjà ouverte, depuis tout visiteur, toute empreinte, tout jeton. Le refus est celui de D-92 : même page de blocage (octet pour octet), même JSON `{"bloque_par":"bannissement"}`, décision `bannissement`/`bloque` avec `par: compte` et `compte`. Il ne bannit ni le visiteur ni l'empreinte. Aucun bannissement automatique dans les mondes partagés `manuel` et `hors-passage`.
  (4) règle « nouvel appareil » : toute connexion d'un visiteur jamais vu sur le compte est enregistrée (`nouvel_appareil = 1` si le compte avait déjà un appareil, 0 pour le tout premier). Au plus **4 appareils distincts connectés au compte en 24 h** (`bannissement.appareils_par_jour`) ; la connexion du 5ᵉ est refusée et le compte banni (motif `appareils_par_jour`). Pourquoi 4 : un humain se connecte depuis son ordinateur, son téléphone, parfois une tablette ou le poste du travail, soit 2 ou 3 appareils, jamais pris ; 5 visiteurs distincts en 24 h sur un même compte est le même ordre de grandeur que `empreinte_sans_memoire` (5 sessions neuves de même empreinte en 24 h, D-48 et D-89). **Ce n'est pas une mesure** : aucun humain connu sur deux appareils en base. La même identité du moteur garde son visiteur (son profil Chrome) : elle n'est un appareil qu'une fois, et jamais « nouvelle » après sa première connexion. Limite connue : un humain qui se connecte chaque jour depuis une fenêtre privée compte un appareil à chaque fois (risque 4 de la conception) ; 5 en 24 h le ferait bannir.
  (5) le motif d'une page refusée : `gardien.refus_banni` pose l'en-tête `X-Arena-Refus: bannissement` (visiteur, empreinte ou compte). Pas de préfixe `X-ShadowLab-` : le frontal retire ces en-têtes internes. Un refus de niveau (détecteurs, porte) n'a pas l'en-tête.
  **Décision, moteur** :
  (6) sentinelle : un 403 de page qui porte cet en-tête est un bannissement de l'identité à toute page de la passe. **Révise D-91 et D-103** : jusqu'ici un refus de page après la première page restait une alerte (campagne 141), et seul le motif lu dans le corps du refus d'une ressource bannissait. Sans l'en-tête, rien ne change (`banni` sur la première page, `alerte` après).
  (7) identité : `identite.json` retient `connexions` (compte → date), jamais un mot de passe.
  (8) scénario `visite(compte=…)` : après une lecture réussie de la vitrine, l'étape du compte : si l'identité n'est pas connectée à ce compte, la page de connexion, le formulaire, puis l'espace où il mène ; sinon l'espace seul. Chaque page passe par la sentinelle : renvoyé vers la connexion alors qu'on était connecté = alerte (`hors_motif`), aucune reconnexion ; compte banni = identité `banni` ; dans les deux cas rien n'est demandé après, aucun réessai. Une lecture arrêtée ne tente pas la connexion. La visite ne réussit que si les deux étapes réussissent. Les détails du passage ne portent que l'identifiant du compte.
  (9) campagne : champ `compte` (une fixture ; scénario `visite` seul) ; avec `bannir_avant_visite`, c'est le compte du bras qui est banni (le code de `arena bannir --compte`), pas son visiteur ; champ `identite_apres_bannissement` (exige `compte` et `bannir_avant_visite`) : à partir de cette visite, le pilote est rouvert sur une autre identité (autre profil Chrome, donc autre visiteur), aussi à la reprise (avec ou sans `espacement`) ; c'est une nouvelle ligne `engines` sous le même libellé. Essai : `configs/experiments/comptes-essai.yaml`.
  **Écarté** (brief de la coordination) : adresses IP et bannissement par IP ; la corrélation (D-89), les seuils des détecteurs, les profils 01 à 07 ; tout CAPTCHA ; une course de 7 jours avec compte.
  **Preuve** : tests écrits d'abord et vus en échec (Arena : `8611415`, `ImportError` de `shadowlab.arena.comptes` ; moteur : `ee08ad5`, 18 sur 28 en échec, les 10 autres gardent le comportement d'avant ou sont refusés par `extra="forbid"` avant le code ; Chrome : `visite()` sans `compte`), code ensuite (`8f8b556`, `e09e8eb`) : `tests/test_comptes.py` (Arena, 49), `tests/test_comptes_moteur.py` (moteur et campagne, 29, dont la reprise sans espacement ajoutée après l'essai : `05cf867` en échec, `4c5a08a` code), `tests/test_comptes_chrome.py` (vrai Chrome au réglage de la course, 96 s : connexion, Chrome relancé, espace atteint sans se reconnecter, même visiteur et même E côté site, compte banni puis refusé à une autre identité, rien après, identité bannie refusée avant Chrome). `tests/test_labo_inchange.py` vert sans changement ; l'empreinte d'`app.py` de `tests/test_public_social.py` est mise à jour avec un commentaire daté.
  **Essai** (`configs/experiments/comptes-essai.yaml`, campagne 1 de la base du dossier de travail d'I10, 19/11 de 7 h 42 à 7 h 52, devant la vraie Arena : frontal du dossier sur 8748, site sur 8774, pile Docker partagée `shadowlab-arena` sur 8781 choisie par `X-ShadowLab-Amont`, configurations Nginx et Coraza identiques à celles du dossier principal ; aucune commande qui modifie Docker, la pile n'a pas été recréée) : **sujet** (`demo`) 4 visites réussies sur 4, connexion à la 1ʳᵉ seulement (une décision `connexion`/`valide`), espace lu sans se reconnecter aux visites 2 à 4, 1 visiteur, 1 empreinte E, 1 appareil (`nouvel_appareil` 0), défi émis à la 1ʳᵉ visite seulement, aucun signal de détecteur, aucun bannissement, identité `ok`. **Témoin** (`analyste`) : visites 1 et 2 par l'identité A réussies (connexion, puis espace) ; avant la 3ᵉ, une ligne `bannissements` (compte `analyste`, ni visiteur ni empreinte, motif `manuel`) ; visite 3 par l'identité B (autre visiteur ; même E, même machine) : porte franchie, 4 pages de la vitrine lues, puis connexion refusée (403, décision `bannissement` avec `par: compte`), B notée `banni` (« statut 403 (motif bannissement) ») ; après le refus, rien que les couches du frontal pour la même requête, la balise de fin de la page de connexion et la feuille de style de la page de refus : aucune page demandée ; visite 4 non lancée (note `bannie`, aucune ligne `runs`). L'en-tête traverse donc Coraza, Nginx et le frontal. **Non vérifié** : la règle « nouvel appareil » devant la vraie Arena (tests seulement) ; un visiteur banni qui fait bannir son compte, l'espace refusé à une identité déjà connectée et le renvoi vers la connexion, vus seulement sur `TestClient` et navigateur factice ; une autre empreinte E dans un vrai navigateur (même machine) ; le test dans un vrai Chrome tourne détecteurs coupés ; un seul essai, 4 visites ; un compte sur plusieurs jours ; un humain sur deux appareils. **Limite connue** : la connexion notée dans l'identité n'a ni durée ni monde ; après 30 jours, ou dans le monde d'une autre campagne (cookie signé pour un autre monde), l'identité est renvoyée vers la connexion à chaque visite : une alerte à chaque fois, jamais de reconnexion (d'où des identités neuves à chaque essai). Décidé par : la session chargée d'I10, à la demande de la coordination.
