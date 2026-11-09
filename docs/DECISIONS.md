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
- **D-15 — 03/11/2026 — Outils anti-détection et modification d'empreinte autorisés contre nos propres protections**
  (décision d'Ethan, remplace D-05). Sans adversaire réel, un taux de détection de 100 % ne prouve rien : il ne
  mesure que des outils naïfs. Restent exclus : toute destination non autorisée, tout solveur de CAPTCHA, tout
  contournement écrit sur mesure contre un détecteur commercial ou un service tiers.
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
