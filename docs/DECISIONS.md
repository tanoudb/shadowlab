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
  du profil navigateur et du canvas ; table empreintes_vues ; détecteur correlation-session qui signale le
  recyclage de fingerprint (≥5 sessions identiques) et la vélocité anormale (≥30 sessions/h avec le même
  hash). Coefficient famille corrélation : 1.5 (le signal le plus fort). 41 détecteurs au total.
- **D-49 — 11/11/2026 — Niveau 07 « État de l'art ».** Tous les 41 détecteurs, seuil composite 0.3,
  WAF paranoia 4, rate limit 1 req/s, honeypots, Turnstile + reCAPTCHA, connexion à 2 tentatives max.
  Objectif : équivalent Cloudflare Enterprise Bot Management en local.
- **D-50 — 11/11/2026 — Masquage SwiftShader pour Linux headless sans GPU.** Sur un serveur Linux sans GPU,
  Chromium utilise Google SwiftShader (logiciel) dont les limites WebGL (SUBPIXEL_BITS=4,
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
  60 minutes (révise le calcul de D-48).** Le détecteur lit toujours les deux comptes de `empreintes_vues`
  (profil, canvas ; types et historique inchangés). Il n'émet plus qu'un signal de comptage, sur le plus grand
  des deux, et qu'un signal de débit. Avant, le profil et le canvas d'une même session donnaient chacun leur
  signal : 5 sessions identiques faisaient 0,7 + 0,7, « automatisé » à elles seules. Les libellés disent ce
  qui est compté (« profil vu dans N sessions de la base ») ; « rotation de fingerprint massive » désignait
  une empreinte stable. Le débit compte, pour chaque hash, les sessions commencées dans les 60 dernières
  minutes, au lieu de diviser le compte par la vie du hash (0 sous une minute, 40 par heure pour deux
  sessions à 3 minutes). Seuils et poids inchangés. Écarté : une empreinte combinée profil + canvas, proposée
  par l'analyse puis signalée par la relecture de sécurité (un moteur qui bruite son canvas à chaque session
  n'aurait plus jamais été revu). Pourquoi : aux campagnes 93 et 94, NOEZIA était classé au niveau 07 dès le
  3ᵉ passage par un débit faux (`docs/recherche/correlation-entre-sessions-2026-11-12.md`). Effet aux niveaux
  06 et 07 : de 5 à 9 sessions, le détecteur seul dit « indéterminé » ; la session reste bloquée par le
  composite (0,7 × 1,5), sous le motif `composite` ; dès 10, rien ne change. Limites : la table ne garde que
  10 jetons par hash, donc le débit ne décide plus seul. Inchangé, et à reprendre avec la mémoire des
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
  24 heures glissantes, en mémoire (5 < 30 ; 5 × 90 = 450 < 500) ; toutes les limites par adresse comptent un
  /64 IPv6 pour une adresse ; commande `shadowlab public effacer-message tous`. (3) Sur une page qui porte
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
  du réseau social. Le résumé de l'accueil est à un seul endroit (`textes.RESUME_RELEVE`) et dit ce que relève
  aujourd'hui `observateur.js` (des nombres et des délais, ni la position de la souris ni ce qui est tapé) ; la
  phrase du cadrage sur les « mouvements de la souris » attend le second script de relevé. Feuille minimale
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
  texte, ni les touches), ni l'adresse IP, ni la localisation, rien qui demande une autorisation ; elle dit qu'une
  façon de bouger la souris ou de taper peut aider à reconnaître une personne. Le résumé de l'accueil
  (`textes.RESUME_RELEVE`) prend le texte « Franchise » du cadrage. Le but annoncé ne change pas. Texte
  d'information en version 2026-11-14.5 ; aucune session publique n'existe encore, tout consentement se donne donc
  sous cette notice. Limites : la durée d'appui d'une touche n'est exacte que sans chevauchement de touches (deux
  listes, sans identité de touche) ; le rythme des touches peut, en théorie, renseigner sur ce qui est tapé ; la
  trace de la dernière page part au clic sur « Terminer », sans garantie d'arriver avant la fin de la session ; la
  note du réseau social sur le commentaire (« jamais envoyé ni enregistré ») reste vraie pour le texte, pas pour
  son rythme (texte non changé, hors de ce travail) ; rien n'est mesuré sur un humain. Décidé par : coordination, à
  la demande d'Ethan le 13/11 : « il faut qu'on prenne un maximum d'infos […] pour faire le meilleur détecteur ».
