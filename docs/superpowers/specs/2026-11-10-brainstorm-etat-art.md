# État de l'art anti-détection et systèmes anti-bot — 2024-2026

*Recherche du 10 novembre 2026 pour le brainstorming NOEZIA v5.*
*Sources : blogs spécialisés, publications académiques (arXiv), documentation vendeurs, benchmarks communautaires.*
*Les chiffres exacts des vendeurs sont des affirmations marketing non vérifiées sauf mention contraire.*

---

## Table des matières

1. [Systèmes anti-bot commerciaux](#1-systèmes-anti-bot-commerciaux-état-2025-2026)
2. [Techniques de fingerprinting avancées](#2-techniques-de-fingerprinting-avancées)
3. [Outils anti-détection open source (top 10)](#3-outils-anti-détection-open-source-top-10)
4. [Techniques émergentes](#4-techniques-émergentes)
5. [Gaps du moteur NOEZIA](#5-gaps-du-moteur-noezia)

---

## 1. Systèmes anti-bot commerciaux (état 2025-2026)

### 1.1 Cloudflare Bot Management

**Architecture 2026 :** trois moteurs complémentaires.

**Turnstile** (GA depuis 2022, omniprésent en 2026) :
- Challenge invisible ou interactif, intégré par les éditeurs de sites.
- Collecte des signaux client-side (événements souris, scroll, frappe) + PoW léger.
- Produit un token côté client validé côté serveur.

**Precursor** (GA juillet 2026) :
- Moteur de validation comportementale *continue*, pas un one-shot au chargement.
- Monitore la session entière : mouvements souris, rythme de scroll, cadence de frappe, activité presse-papiers, durée de visibilité de la page.
- Les signaux sont évalués comme patterns agrégés, pas comme actions individuelles.
- Complément optionnel de Turnstile dans l'offre Enterprise Bot Management.
- Les scores comportementaux ne sont pas exposés dans les dashboards client.

**Adaptive Intelligence** (annoncé 31 août 2026) :
- Combine signaux réseau (JA4, structure des requêtes, réputation IP/ASN) + télémétrie client-side (Turnstile + Precursor).
- Se met à jour dynamiquement quand de nouveaux outils de contournement apparaissent, sans attendre un release de modèle.
- Les clients Enterprise obtiennent un bot score 1-99 et des detection IDs montrant quel moteur/heuristique a déclenché.

**Signaux réseau confirmés :** JA3/JA4 TLS fingerprints, ASN, réputation IP, structure des requêtes HTTP. Le HTTP/2 fingerprinting est intégré en interne mais non exposé aux Workers.

**Alertes :** déclenchées quand le Z-score dépasse 3.5 *et* que les requêtes bot dépassent 200/5 min avec un bot score < 30.

**Ce qui compte contre Cloudflare :** un benchmark indépendant 2026 (7 outils, 31 cibles Cloudflare, 651 verdicts) montre que *nodriver* est le seul outil avec 0 blocage (28 OK, 3 gatés). Patchright et Camoufox obtiennent 25 OK, 3 gatés, 3 bloqués chacun. Cela indique que Cloudflare détecte principalement via l'empreinte du protocole d'automatisation (CDP/WebDriver), pas via le fingerprinting JS classique.

Sources :
- [Cloudflare — Introducing Precursor](https://blog.cloudflare.com/introducing-precursor/)
- [Cloudflare — Adaptive Intelligence](https://blog.cloudflare.com/introducing-adaptive-intelligence/)
- [Benchmark anti-detect 2026 — Ian L. Paterson](https://dev.to/ianlpaterson/anti-detect-browser-benchmark-2026-7-stealth-tools-31-cloudflare-targets-651-verdicts-4361)

### 1.2 DataDome

**Approche :** ML-first, multi-couches, pas de décision binaire.

**Couche serveur :**
- TLS fingerprinting (JA3/JA4) confirmé dans la documentation de l'API Protection.
- TCP/IP OS fingerprinting (p0f, Zardaxt en production — source unique, à confirmer).
- IP reputation, ASN, géolocalisation, taux de requêtes.
- Selon certaines sources, le scoring côté serveur pèse plus que le fingerprinting JS dans la décision.

**Couche client (Device Check) :**
- Tag JS qui collecte « des centaines de signaux » (affirmation vendeur).
- Checks d'intégrité de l'environnement : détection de frameworks d'automatisation, environnements spoofés, accès programmatique.
- Canvas et WebGL (affirmation tierce, non confirmée par DataDome).

**Couche ML et comportement :**
- 85 000+ modèles client-spécifiques (chiffre de source secondaire, non vérifié).
- Patterns comportementaux, anomalies temporelles, trafic agrégé.
- Depuis 2025 : détection d'intention (comparaison du flux de navigation avec les patterns humains connus).
- 5+ trillions de signaux traités par jour (affirmation vendeur).

**Escalade progressive :** requêtes suspectes → Device Check → CAPTCHA si insuffisant. Pas de blocage immédiat sur signaux faibles.

**Spécificité :** DataDome corrèle beaucoup de signaux faibles plutôt que de s'appuyer sur un fingerprint unique. Un bot qui passe *presque* partout mais qui a une incohérence mineure sera quand même attrapé par accumulation.

Sources :
- [DataDome — Anti-bot solution](https://datadome.co/guides/bot-protection/anti-bot-solution/)
- [DataDome — Multi-layered ML](https://datadome.co/bot-management-protection/multi-layered-machine-learning-a-new-requirement-for-sophisticated-bot-protection/)

### 1.3 HUMAN (ex-PerimeterX)

**Identification :** cookies `_px3`, `_pxvid`, `_pxhd`.

**Approche :**
- Score de confiance *par session* qui évolue au fil de la visite.
- Recherche publiée sur la distinction mouvements souris humains vs courbes de Bézier.
- Signaux : trajectoire souris, vélocité de scroll, intervalles entre clics, patterns de frappe.
- 2026 : ajout du **cross-site behavioral fingerprinting** — corrélation des patterns entre différents sites protégés par HUMAN.
- Fusion avec PerimeterX complétée en 2022 ; le produit couvre bot defense + fraude + abus de comptes.

**Spécificité par rapport à DataDome :** HUMAN insiste davantage sur le comportemental cross-site et la détection de fraude que sur le fingerprinting pur.

### 1.4 Akamai Bot Manager

**Identification :** cookies `_abck`, `bm_sz`.

**Approche :**
- TLS + HTTP/2 fingerprinting historique (recherche Black Hat EU 2017 sur 10M+ connexions).
- 2026 : **continuous authentication** — réévaluation du comportement tout au long de la session.
- Challenges moins fréquents que Cloudflare/DataDome par défaut, mais très efficaces quand configuré de manière agressive.
- Requiert une couche TLS correcte pour passer ; un JA4 incohérent est rédhibitoire.
- Fortement intégré à la CDN Akamai : les clients existants bénéficient de la télémétrie réseau.

**Spécificité :** pionnier de l'HTTP/2 fingerprinting. L'empreinte Akamai combine SETTINGS, WINDOW_UPDATE, priorités et pseudo-header order en une chaîne unique.

### 1.5 Kasada

**Identification :** headers `x-kpsdk-*`.

**Approche :**
- Centré sur l'**interrogation active de l'environnement** navigateur.
- Proof-of-work côté client : impose un coût computationnel réel au scraping à grande échelle.
- Poids plus important sur la preuve client-side que sur la réputation IP.
- Code JS obfusqué avec VM (code de vérification lui-même protégé).
- Le coût économique du PoW est le principal moyen de dissuasion : même si le bot passe, il coûte cher à opérer.

**Spécificité :** Kasada est le plus difficile à contourner par automatisation car son challenge exige un *vrai* environnement d'exécution JS performant. Un client HTTP pur ne passera jamais.

### 1.6 Signaux les plus discriminants en production (synthèse)

| Rang | Signal | Pourquoi |
|------|--------|----------|
| 1 | **Cohérence inter-couches** | Une contradiction TLS↔HTTP/2↔UA↔Navigator↔Canvas est rédhibitoire. C'est le premier test. |
| 2 | **TLS fingerprint (JA4)** | Identifie la stack réseau. Un client non-navigateur est immédiatement visible. |
| 3 | **HTTP/2 fingerprint** | SETTINGS + pseudo-header order. Le signal le plus difficile à spoofer avec un outil non-navigateur. Stable (Chrome 120-142 identique). |
| 4 | **Détection d'automatisation CDP/WebDriver** | `Runtime.enable`, `navigator.webdriver`, stack traces, globales CDP. Attrape les outils non patchés. |
| 5 | **Intégrité des APIs JS** | `Function.prototype.toString()`, `Object.getOwnPropertyDescriptor()`, double exécution canvas. Attrape les patches JS. |
| 6 | **Comportement agrégé** | Entropie des mouvements, loi de Fitts, flux de navigation, temps de lecture. Le plus difficile à falsifier correctement. |
| 7 | **IP reputation / ASN** | Datacenter vs résidentiel. Aucune technique ne peut compenser une IP datacenter sur certains vendeurs. |
| 8 | **Canvas/WebGL uniqueness** | Cross-session : même hash = réseau de bots. Incohérence avec le GPU annoncé = spoofing. |

---

## 2. Techniques de fingerprinting avancées

### 2.1 HTTP/2 Fingerprinting (JA4H, SETTINGS, priorités)

**État de l'art 2026 :**

L'HTTP/2 fingerprinting est devenu le deuxième signal le plus important après le TLS, et dans certains cas le premier.

**Composants de l'empreinte :**
- **SETTINGS frame** : valeurs *et ordre* des paramètres. Chrome envoie `HEADER_TABLE_SIZE=65536, MAX_CONCURRENT_STREAMS=1000, INITIAL_WINDOW_SIZE=6291456, MAX_HEADER_LIST_SIZE=262144`. Firefox a des valeurs différentes.
- **WINDOW_UPDATE** initial : la valeur et le timing.
- **Ordre des pseudo-headers** : Chrome envoie `:method, :authority, :scheme, :path` ; Firefox envoie `:method, :path, :authority, :scheme`. Ce seul signal distingue Chromium de Firefox.
- **PRIORITY / PRIORITY_UPDATE** : Chrome les utilise, curl ne les envoie pas.
- **Frames PING et GOAWAY** : timing et présence.

**Stabilité :** tous les Chrome de la version 120 à 142 produisent les mêmes SETTINGS et pseudo-header order. L'HTTP/2 change beaucoup moins souvent que les paramètres TLS.

**JA4H :** couvre la couche HTTP au-dessus de TLS. Inclut l'ordre des headers, la présence de cookies, le format d'Accept-Language, la présence de Referer. Un spoof TLS parfait échoue si le JA4H ne correspond pas.

**Détection cross-layer :** les vendeurs vérifient la cohérence TLS↔HTTP/2↔headers. Un TLS parfait avec des SETTINGS HTTP/2 incorrects est *plus* suspect qu'avoir les deux légèrement faux.

**Implication pour les bots :** un client HTTP (requests, httpx, aiohttp) n'envoie pas de SETTINGS HTTP/2 de navigateur et est immédiatement identifiable. curl_cffi est le seul outil HTTP pur qui spoofe correctement cette couche.

### 2.2 TLS Fingerprinting (JA3/JA4)

**JA3 est obsolète.** Déprécié officiellement en mai 2025 en faveur de JA4. La randomisation de l'ordre des extensions TLS par Chrome (depuis Chrome 110, janvier 2023) a cassé JA3 comme identifiant de navigateur. JA3 reste utile pour détecter les clients non-navigateur qui ne randomisent pas (Python requests, curl brut).

**JA4 — le standard 2025-2026 :**
- Trie les cipher suites et extensions avant hachage → résistant à la randomisation.
- Format lisible par l'humain (type_protocole_version_extensions_ciphers).
- Couvre TLS 1.2 et 1.3, et potentiellement HTTP/3/QUIC.
- Adopté par Cloudflare, Akamai, AWS CloudFront (support natif annoncé), DataDome.
- 15 millions de JA4 fingerprints uniques chez Cloudflare (chiffre non vérifié).

**Signaux émergents dans TLS :**
- **ECH (Encrypted Client Hello)** : masque le SNI. Supporté par curl-impersonate v2.3+.
- **Post-quantum** : Chrome expérimente ML-DSA et X25519Kyber768. Ces extensions modifient le ClientHello.
- **Trust Anchors (Chrome 155+)** : extension TLS qui envoie les ancres de confiance. Les profils curl_cffi/impit qui n'incluent pas cette extension sont distinguables des vrais Chrome récents.

**Détection :** le JA4 seul n'est pas un identifiant (tous les Chrome sur le même OS partagent un JA4). C'est un signal corroborant. La puissance vient du croisement avec HTTP/2 et les headers.

### 2.3 Canvas/WebGL Fingerprinting

**Canvas 2D :**
- Le hash du rendu (texte + gradient + formes) est déterministe pour un couple {GPU, driver, navigateur, OS}. C'est le fingerprint le plus établi.
- **Détection de bruit artificiel** : double appel `toDataURL()` dans la même session. Si les résultats diffèrent → injection de bruit détectée. Si identiques mais le hash ne correspond à aucune machine connue → suspicion.
- **Cross-session uniqueness** : le même hash canvas vu sur N sessions avec des IPs différentes = réseau de bots.
- **Cohérence GPU** : le hash doit être plausible pour le GPU annoncé via `WEBGL_debug_renderer_info`. SwiftShader, Mesa, LLVMpipe = headless.
- **Dégradation :** les navigateurs anti-fingerprinting (Brave, Firefox résistFP) ajoutent du bruit. Mais ça reste utilisable car le bruit *du navigateur* est différent du bruit *d'injection JS*.

**WebGL :**
- FingerprintJS vérifie 17+ paramètres WebGL : vendor, renderer, MAX_TEXTURE_SIZE, MAX_VIEWPORT_DIMS, ALIASED_LINE_WIDTH_RANGE, extensions supportées, shader precision formats.
- Le renderer `ANGLE (Google, Vulkan...)` vs `ANGLE (NVIDIA, ...)` révèle le GPU réel.
- Les outils anti-détection spoofe typiquement 2-3 paramètres (vendor, renderer, unmasked) mais oublient les extensions, le shader precision, et les limites numériques → incohérence détectable.

**État 2026 :** canvas reste utilisable malgré la dégradation. L'analyse de cohérence (hash ↔ GPU ↔ OS ↔ browser version) est plus puissante que le hash seul.

### 2.4 Audio Fingerprinting

**Principe :** un `OscillatorNode` + `DynamicsCompressor` + `AnalyserNode` produit un signal audio dont le hash dépend de la stack audio du device (hardware + drivers + navigateur).

**Techniques 2025-2026 :**
- Exécution de multiples tests courts avec des paramètres variés et comparaison des distributions de sortie.
- AudioContext latency, sampleRate, base latency comme signaux complémentaires.
- `getChannelData()` vs `getFloatFrequencyData()` : les deux doivent être cohérents.

**Détection de spoofing :** ajouter du bruit gaussien sur `getFloatFrequencyData` (ce que fait NOEZIA) est insuffisant si :
- Le bruit n'est pas ajouté sur `getChannelData` aussi.
- L'`AnalyserNode` output est incohérent avec l'`OscillatorNode` output direct.
- Le hash audio ne correspond à aucune configuration hardware connue.

**État 2026 :** audio reste un signal actif. La standardisation des APIs audio dans les navigateurs maintient sa pertinence.

### 2.5 Font Fingerprinting

**Principe :** mesurer les dimensions de rendu de texte avec un jeu de polices. Les polices *disponibles* dépendent de l'OS, de la version, et des logiciels installés.

**Techniques :**
- Rendu côté canvas et mesure des dimensions pixel (ne nécessite pas d'API d'énumération explicite).
- Même quand `canvas.toDataURL` est brouillé, les *dimensions de texte* restent accessibles via `measureText()`.
- Référentiels de fonts par {OS, version} : un profil annonçant macOS avec des fonts Windows-only est trivial à détecter.

**État 2026 :** en légère déclin car les OS standardisent leurs sets de fonts. Mais reste un signal de cohérence important (fonts ↔ OS annoncé).

### 2.6 Worker Consistency Checks

**Principe :** comparer les valeurs de `navigator.hardwareConcurrency`, `navigator.platform`, `navigator.userAgent`, `deviceMemory` entre le main thread et un Web Worker (ou Service Worker).

**Pourquoi c'est efficace :** la plupart des outils anti-détection injectent leurs patches *uniquement* dans le main thread. Le Worker exécute un contexte séparé où les patches ne s'appliquent pas.

**Signaux vérifiés :**
- `hardwareConcurrency` : main vs worker.
- `navigator.platform` : main vs worker.
- WebGL renderer : main vs worker (OffscreenCanvas).
- `navigator.webdriver` : main vs worker.

**Recherche académique (FP-Inconsistent, arXiv 2406.07647, 2024-2025) :** les chercheurs montrent que les bots évasifs créent des combinaisons d'attributs que les vrais appareils ne produisent jamais. Leurs règles basées sur les incohérences réduisent de 44-48% le trafic bot évasif qui échappe à DataDome et BotD.

**Recherche Castle.io (2025) :** Open Bullet 2 spoofait WebGL uniquement sur le main thread ; le Worker rapportait un renderer différent. Ce mismatch est un signal fort de tampering.

**Ce que NOEZIA fait :** les patches sont propagés aux Workers via injection dans le constructeur. C'est rare et c'est un point fort. Mais la propagation doit être *complète* (WebGL, audio, canvas — pas seulement navigator).

### 2.7 Timing-Based Detection (rAF, performance.now)

**requestAnimationFrame (rAF) :**
- Un vrai navigateur avec un écran physique produit des callbacks rAF à ~16.67ms (60Hz) ou ~8.33ms (120Hz), avec une variance naturelle liée au vsync.
- En headless ou en environnement automatisé : les deltas sont soit à 0, soit parfaitement identiques, soit absents.
- rAF a une résolution de ~0.1ms (Firefox) vs ~1ms pour `performance.now()`.

**performance.now() :**
- Résolution volontairement réduite (protection Spectre) : 5μs dans Chrome, 1ms dans Firefox en contexte cross-origin.
- Un `performance.now()` surchargé qui retourne des valeurs trop précises ou trop uniformes = signal de tampering.
- Le coût relatif des opérations reflète le CPU/mémoire réels, même avec la résolution réduite.

**Paint timing :**
- `PerformanceObserver` pour `first-paint` et `first-contentful-paint`.
- En headless : `first-paint` à 0 ou absent. En vrai navigateur : valeur positive corrélée à la complexité de la page.

**État 2026 :** les preuves académiques sont minces. Les blogs vendeurs affirment que c'est un signal important. L'implémentation dans l'Arena (détecteur `raf-timing`) est pertinente mais non branchée au gardien.

---

## 3. Outils anti-détection open source (top 10)

### 3.1 Camoufox (Firefox custom)

**Quoi :** navigateur Firefox modifié (patches C++) piloté via Playwright. 100+ modifications au niveau du moteur.

**Forces :**
- Fingerprinting invisible au JS : les modifications sont dans le moteur, pas dans des scripts injectés.
- `Function.prototype.toString()` retourne `[native code]` car les patches sont natifs.
- TLS natif Firefox (pas de spoofing nécessaire).
- Spoofing de : navigator, screen, WebGL, AudioContext, polices, timezone, géolocalisation.
- Suppression des telemetries Mozilla, patches LibreWolf et Ghostery intégrés.
- Mouvement souris naturel intégré.
- **Meilleur taux** dans les benchmarks fingerprinting (100% dans un benchmark lab 2026).

**Faiblesses :**
- Licence MPL-2.0 (permissive mais avec obligations de disclosure des patches).
- TLS *Firefox* : certains CDN traitent le JA4 Firefox différemment de Chrome (suspicion car Firefox = 3% du trafic web).
- Dépendance à playwright<1.63 (conflit avec les versions récentes).
- Plantages macOS arm64 signalés (issues #915, #957).
- Mémoire croissante sur les tâches longues (#245).
- Le mainteneur principal s'est retiré.
- Live-site : 25 OK / 31 sur le benchmark Cloudflare (pas le meilleur en pratique).

**Dernière activité :** v158.0.1-beta.41 (29 octobre 2026). PyPI : 0.5.9.

### 3.2 BrowserForge (profils réalistes)

**Quoi :** générateur Python de headers et fingerprints de navigateur. Réimplémentation de fingerprint-suite (Apify).

**Forces :**
- Profils statistiquement réalistes basés sur des données du monde réel (réseau bayésien).
- Contraintes : browser, OS, device, locale, version HTTP — tout cohérent.
- Intégré à Camoufox et Crawlee.

**Faiblesses :**
- L'injection de fingerprint est **dépréciée** — BrowserForge recommande d'utiliser Camoufox pour l'injection.
- Ne gère que la *génération*, pas l'application des profils.
- Écriture de données impossible sur les systèmes en lecture seule (AWS Lambda).
- Pas de persistance d'empreinte entre sessions sans code custom.

**Dernière activité :** v1.2.4 (3 février 2026). Même auteur que Camoufox.

### 3.3 rebrowser-patches

**Quoi :** patches pour Puppeteer et Playwright ciblant les vecteurs de détection d'automatisation, principalement le leak `Runtime.enable` de CDP.

**Forces :**
- Cible le signal le plus discriminant : `Runtime.enable` qui est la signature CDP que les anti-bots détectent.
- Drop-in : paquets prêts à l'emploi (`rebrowser-puppeteer-core`, `rebrowser-playwright-core`).
- MIT, pas de contrainte de licence.

**Faiblesses :**
- Ne couvre *que* les fuites de protocole. Aucun spoofing de fingerprint.
- Évalué comme « adapté aux cibles mid-tier » dans un benchmark indépendant.
- Versions des paquets wrappeurs potentiellement en retard.

**Dernière activité :** v1.1.3 (2 novembre 2026).

### 3.4 puppeteer-extra-stealth

**Quoi :** plugins JS sur Puppeteer qui patchent les signaux de détection classiques (webdriver, Chrome.runtime, etc.).

**Forces :**
- Écosystème riche de plugins (stealth, recaptcha, adblocker).
- Historiquement le plus connu, beaucoup de documentation.

**Faiblesses :**
- **Effectivement abandonné.** Dernière version npm 2.11.2, datant de mars 2023. Aucun release depuis.
- Formellement déprécié en février 2026 selon certaines sources (non confirmé officiellement).
- Les patches JS sont visibles via `Function.prototype.toString()` — la détection a évolué depuis.
- Ne couvre que les propriétés JS in-page. Aucune action sur CDP, TLS, HTTP/2.
- **Alternatives recommandées :** rebrowser-puppeteer-core (migration la plus simple), Patchright, Camoufox.

**Dernière activité :** mars 2023 (npm).

### 3.5 Patchright

**Quoi :** fork de Playwright avec patches anti-détection au niveau du build Chromium. Drop-in replacement.

**Forces :**
- TLS Chromium natif (même JA4 que Chrome).
- API Playwright complète, migration triviale.
- Patches au niveau du protocole, pas des scripts JS.
- Exécution JS via `Page.createIsolatedWorld` au lieu de `Runtime.enable`.
- Très activement maintenu (5065 étoiles).

**Faiblesses :**
- **Chromium uniquement** — Firefox et WebKit non supportés.
- **Aucun spoofing de fingerprint** — laisse l'empreinte réelle du navigateur.
- Ne passe pas les challenges JS avancés (Kasada, DataDome Device Check) selon les tests indépendants.
- Google Chrome sur arm64 non supporté (issue #211).
- La version Chromium embarquée accuse parfois un retard de plusieurs versions.
- **25 OK / 31 sur le benchmark Cloudflare** — milieu du classement.

**Dernière activité :** v1.64.1 (15 octobre 2026).

### 3.6 nodriver / zendriver

**nodriver :**
- Bibliothèque Python asynchrone pilotant Chromium directement par CDP, sans WebDriver.
- **Meilleur score sur le benchmark Cloudflare 2026** : 28 OK, 3 gatés, 0 bloqué.
- Successeur de undetected-chromedriver.
- AGPL-3.0 (problématique pour un produit fermé).
- Aucune couche anti-fingerprinting.
- CDP détectable via `Error.stack`.
- Bugs signalés : `isTrusted: false` sur les clics, coordonnées à 0,0, pas d'événements pointer.
- Dernière activité : v0.50.99 (26 octobre 2026).

**zendriver :**
- Fork communautaire de nodriver avec correctifs et améliorations.
- Même AGPL-3.0.
- DataDome détecte zendriver (issue #20).
- Processus Chrome orphelins signalés.
- Dernière activité : v0.17.1 (2 octobre 2026).

### 3.7 undetected-chromedriver

**Quoi :** patch automatique du chromedriver Selenium pour éviter la détection.

**Forces :**
- Simple d'utilisation (import drop-in).
- Historiquement efficace contre les anti-bots de base.

**Faiblesses :**
- **Effectivement abandonné** : dernière activité juillet 2025, aucune release GitHub.
- Issues GitHub désactivées.
- Pré-Chrome 122, en retard de 20+ versions.
- L'auteur redirige vers nodriver.
- GPL-3.0 (copyleft fort, incompatible avec un produit fermé).

**Dernière activité :** 5 juillet 2025.

### 3.8 Scrapling

**Quoi :** framework Python tout-en-un : fetchers HTTP furtifs, navigateurs stealth, parsing, crawl concurrent, extraction adaptative.

**Forces :**
- BSD-3-Clause (licence permissive).
- 94 542 étoiles (énorme communauté).
- Multiple fetchers : HTTP stealth, navigateur furtif, client Cloudflare.
- Extraction adaptative avec `similaires()` (auto-match de listes) et `extraire_adaptatif()` (relocalisation par signature).
- Proxy rotation intégrée, AI integration.
- MCP Server pour agents IA.

**Faiblesses :**
- Stealth « limité » selon les reviewers indépendants — cible les détections basiques.
- Import forcé de patchright même pour le client HTTP (`extra scrapling[fetchers]` obligatoire).
- Pas de benchmark indépendant du taux de bypass.
- Moins robuste que Scrapy pour les systèmes de crawl à grande échelle.

**Dernière activité :** v0.5 (17 octobre 2026).

### 3.9 curl_cffi / curl-impersonate

**Quoi :** binding Python de curl-impersonate. Client HTTP qui reproduit les empreintes TLS/JA3 et HTTP/2 de vrais navigateurs.

**Forces :**
- **TLS + HTTP/2 spoofing parfait** : le seul outil HTTP qui passe la couche transport.
- Très rapide (pas de navigateur).
- Profils nommés pour Chrome, Firefox, Safari (multiples versions).
- v0.15+ : HTTP/3 et QUIC, WebSockets.
- API proche de requests.
- MIT licence.

**Faiblesses :**
- **Pas de JS** — ne peut pas exécuter de challenges navigateur.
- Profils à maintenir à jour (un Chrome 120 fingerprint en 2026 est suspect).
- Réponses tronquées occasionnellement (#597).
- Trust Anchors (Chrome 155+) non supportés dans les profils existants (#363).
- TCP/IP fingerprint non contrôlé.

**Dernière activité :** v0.17.0 (26 octobre 2026) pour curl_cffi, v2.3.2 (30 octobre 2026) pour curl-impersonate.

### 3.10 Autres projets significatifs

**Pydoll** (MIT, 7133 étoiles) :
- Automatisation Chromium par CDP brut, sans WebDriver.
- Couche compatible Playwright.
- Pas de couche anti-fingerprinting.
- Dernière activité : v3.0.0 (29 septembre 2026).

**impit** (Apache-2.0, 630 étoiles) :
- Bibliothèque Rust d'imitation navigateur avec bindings Python et Node.
- HTTP/1.1, HTTP/2, HTTP/3.
- Alternative moderne à curl_cffi.
- Dernière activité : js-0.14.8 (29 octobre 2026).

**Lightpanda** (AGPL-3.0, 41 132 étoiles) :
- Navigateur headless en Zig, sans Chromium.
- 16x plus léger, 9x plus rapide (chiffres vendeur).
- Piloté par CDP depuis Puppeteer/Playwright.
- Aucune couche anti-détection — intéressant pour la performance mais pas pour la furtivité.

**fingerprint-suite (Apify)** (Apache-2.0, 2650 étoiles) :
- header-generator, fingerprint-generator, fingerprint-injector.
- Réseau bayésien généré à partir de données réelles.
- Intégré à Crawlee.
- Canvas et WebGL non couverts (#36).

---

## 4. Techniques émergentes

### 4.1 IA dans la détection de bots

**ML comportemental (tendance dominante 2025-2026) :**
- Les vendeurs convergent vers des modèles ML par client plutôt que des règles statiques.
- DataDome : 85 000+ modèles spécifiques, entraînés sur le trafic de chaque client.
- Les modèles détectent des patterns statistiques même dans des mouvements souris randomisés et des délais aléatoires.
- Techniques : supervised learning sur des labels bot/humain, anomaly detection sur les séries temporelles, clustering de sessions similaires.

**Détection des agents IA (nouveau front 2026) :**
- FingerprintJS lance AI Assistant Detection (juin 2026) pour identifier le trafic ChatGPT, Gemini, Claude.
- Fonctionne au niveau HTTP, pas au niveau navigateur.
- Détection spécifique de Grok Bot, Muse (Meta), Instinct (Spear Street).
- Recherche académique émergente :
  - **FP-Agent** (arXiv 2605.01247, 2025) : fingerprinting des agents IA qui naviguent le web.
  - **"On the Internet Nobody Knows You're an LLM Bot"** (arXiv 2606.30119, 2026) : fingerprinting multi-couches des agents LLM, montrant qu'ils ont des patterns de navigation, de timing et d'erreur distincts des humains.

**Implications pour NOEZIA :** si une couche IA est ajoutée au moteur, les patterns de décision de l'IA seront eux-mêmes un signal de détection. Il faudra que l'IA imite les *patterns de décision* humains, pas seulement les mouvements physiques.

### 4.2 Proof-of-Work côté client

**Trois approches en production/open-source :**

| Projet | Algorithme | Particularité |
|--------|-----------|---------------|
| **Cloudflare Turnstile** | PoW invisible + signaux comportementaux | Intégré à l'écosystème Cloudflare, gratuit |
| **Kasada** | PoW + interrogation environnement | JS obfusqué, coût économique pour les bots |
| **Anubis** (MIT, 23 923 étoiles) | SHA-256, Argon2id, HashX (v1.28.0) | Proxy-level, populaire pour bloquer les crawlers IA |
| **ALTCHA** (MIT, 2875 étoiles) | Argon2id, Scrypt | Memory-hard, résistant GPU/ASIC |
| **Cap** (Apache-2.0, 8246 étoiles) | PoW + instrumentation | Auto-hébergé, PoW résistant GPU + checks comportementaux |

**Limites du PoW pur :**
- Anubis contourné par un outil CLI publié en juillet 2025.
- Le PoW n'arrête que les scrapers à faible effort ; un bot avec un vrai navigateur le résout normalement.
- Coût énergétique critiqué (LWN a refusé de déployer Anubis pour cette raison).
- Cap combinant PoW + instrumentation est plus résistant qu'Anubis (PoW seul).

**Tendance :** le PoW invisible (Turnstile, Kasada) est plus efficace que le PoW visible car il impose un coût sans friction pour l'humain. La combinaison PoW + instrumentation + comportemental est la direction prise par les vendeurs commerciaux.

### 4.3 Attestation matérielle (Device Integrity)

**Web Environment Integrity (WEI) — mort-né :**
- Proposition Google de 2023 pour l'attestation matérielle dans le navigateur.
- Backlash immédiat de la communauté web.
- Retiré avant implémentation.

**Play Integrity API sur desktop (rumeur 2026) :**
- Une source (unique, non corroborée) affirme que Google prévoit de rendre les résultats Play Integrity API disponibles via reCAPTCHA sur navigateur desktop.
- Si confirmé, ce serait un changement majeur : le serveur pourrait vérifier que le navigateur tourne sur un appareil réel avec un OS non modifié.
- Actuellement non vérifié — à surveiller.

**Privacy Sandbox — abandonné :**
- Google a retiré la majorité des technologies Privacy Sandbox en octobre 2025.
- Les third-party cookies persistent dans Chrome.
- Chrome n'offre presque aucune protection anti-fingerprinting native (contrairement à Firefox resistFingerprinting et Brave).

**État 2026 :** l'attestation matérielle reste un concept, pas une réalité déployée sur le web. Le WEI est mort, la Play Integrity desktop est une rumeur. En l'absence d'attestation, le fingerprinting logiciel reste le standard.

### 4.4 Privacy Sandbox et son impact sur le fingerprinting

**Contexte :** Privacy Sandbox devait réduire le fingerprinting en supprimant les third-party cookies et en standardisant certaines APIs. Son abandon signifie :

1. **Les third-party cookies restent** — les techniques de tracking classiques persistent.
2. **Aucune standardisation des APIs de fingerprinting** — `navigator.hardwareConcurrency`, `deviceMemory`, canvas, WebGL restent accessibles.
3. **Chrome n'ajoute pas de protections anti-fingerprinting** — contrairement à Firefox (résistFingerprinting) et Brave (randomisation canvas/WebGL).
4. **Google autorise le fingerprinting digital** — en février 2025, Google aurait donné le feu vert à ses annonceurs pour utiliser le fingerprinting.

**Impact pour le scraping :** paradoxalement, l'abandon du Privacy Sandbox est *favorable* aux scrapers. Les APIs de fingerprinting restent accessibles, ce qui signifie que les profils complets restent nécessaires, mais aussi que les outils anti-détection ont des cibles stables à spoofer. Si Chrome avait standardisé/réduit ces APIs, les détecteurs se seraient rabattus sur des signaux plus difficiles (timing, comportement, attestation).

### 4.5 Web Bot Auth (Cloudflare)

**Proposition 2026 :** vérification cryptographique de l'identité des bots légitimes. Au lieu de se fier à l'IP ou au User-Agent pour identifier Googlebot, les bots signent leurs requêtes.

**Implication :** sépare le problème en deux — les bots légitimes s'identifient, les bots malveillants ne le font pas. Ne change pas la détection des bots évasifs, mais réduit les faux positifs sur les crawlers légitimes.

FingerprintJS a noté que Grok Bot a cessé de signer ses requêtes avec Web Bot Auth vers le 9 octobre 2026 — signe que l'adoption n'est pas universelle.

### 4.6 Détection d'incohérences (FP-Inconsistent)

**Recherche académique (UC Davis, arXiv 2406.07647, 2024-2025) :**
- Les bots évasifs qui modifient leurs fingerprints créent des combinaisons d'attributs que les vrais appareils ne produisent *jamais*.
- Les vrais appareils ont un nombre limité de configurations hardware/software valides.
- Approche : construire des règles data-driven basées sur les paires d'attributs invalides.
- Résultats : 44-48% de réduction du trafic bot évasif qui échappe à DataDome et BotD.
- Pas de faux positifs avec les outils de protection de la vie privée (Brave, Firefox, VPN).

**Implication pour l'Arena :** cette approche est *exactement* ce que devrait faire le détecteur `coherence-profonde` (actuellement non branché). La recherche fournit une méthodologie validée pour la détection par incohérence.

---

## 5. Gaps du moteur NOEZIA

En croisant l'état de l'art avec l'audit moteur (3/10) et l'audit Arena, voici les 10 gaps les plus critiques par ordre de priorité.

### Gap 1 — Pas de contrôle HTTP/2 fingerprint (CRITIQUE)

**Constat :** NOEZIA ne touche pas au SETTINGS frame, pseudo-header order, WINDOW_UPDATE, ni aux priorités HTTP/2. Il hérite passivement de Patchright/Chromium.

**Pourquoi c'est critique :** c'est le 3e signal le plus discriminant en production. Cloudflare, Akamai, DataDome l'utilisent. Un client HTTP avec des SETTINGS incorrects est immédiatement identifiable.

**Ce qui manque :**
- Mesure de l'empreinte HTTP/2 actuelle du moteur.
- Capacité à spécifier les SETTINGS, pseudo-header order, WINDOW_UPDATE.
- Validation que l'empreinte HTTP/2 correspond au profil annoncé.

**Impact si résolu :** passage de 3/10 à 5/10 sur les cibles qui vérifient HTTP/2.

### Gap 2 — Arena trop faible (détecteurs débranchés)

**Constat :** 32 détecteurs existent mais seuls 6 sont consultés par le gardien. Le moteur passe l'Arena sans effort, ce qui empêche d'identifier ses faiblesses.

**Pourquoi c'est critique :** on ne sait pas si le moteur est bon parce qu'on ne l'a jamais testé contre un adversaire crédible. C'est le problème n°1 selon l'audit.

**Ce qui manque :**
- Activation progressive des détecteurs par niveau (proposal de l'audit Arena : niveaux 03-07 révisés).
- Score composite (somme pondérée) au lieu de la logique binaire actuelle.
- Corrélation multi-signaux.

**Impact si résolu :** le moteur échouera probablement à partir du niveau 04 révisé, ce qui donnera une feuille de route précise d'amélioration.

### Gap 3 — Cohérence inter-couches non vérifiée ni garantie

**Constat :** aucun mécanisme ne vérifie que l'ensemble {TLS JA4, HTTP/2, User-Agent, navigator, canvas, WebGL, fonts, timezone, locale} est mutuellement cohérent.

**Pourquoi c'est critique :** c'est le signal n°1 en production. Une seule contradiction = bot détecté. Les profils NOEZIA sont construits à la main et validés par des heuristiques, mais pas par un modèle de cohérence formel.

**Ce qui manque :**
- Modèle de cohérence complet : {JA4 ↔ HTTP/2 ↔ UA ↔ navigator ↔ canvas hash ↔ WebGL params ↔ fonts ↔ timezone ↔ locale ↔ screen}.
- Validation automatique avant chaque session.
- Base de données de vrais profils (pas 18 profils à la main — des centaines, extraits de données réelles).

### Gap 4 — Canvas/WebGL fingerprint insuffisant

**Constat :** le canvas a un seed par profil (v4) avec bruit déterministe pixel-par-pixel. Le WebGL spoofe 3 paramètres sur 17+.

**Problèmes spécifiques :**
- Double `toDataURL()` donne des résultats différents → injection détectable.
- Pas de corrélation cross-session (même hash = bot).
- Bruit prévisible (formule déterministe).
- WebGL : extensions, shader precision, limites numériques non spoofées.
- Pas de cohérence hash↔GPU annoncé.

**Ce qui manque :**
- Canvas déterministe intra-session (même résultat sur N appels).
- Corrélation cross-session côté Arena.
- WebGL complet : 17+ paramètres cohérents avec le GPU du profil.

### Gap 5 — Audio fingerprint minimal

**Constat :** 46 lignes de code. Bruit gaussien sur `getFloatFrequencyData` uniquement.

**Ce qui manque :**
- Patch de `getChannelData` aussi.
- Cohérence `AnalyserNode` ↔ `OscillatorNode`.
- Hash audio unique par profil (comme le canvas seed).
- AudioContext latency et sampleRate cohérents avec le profil.

### Gap 6 — Pas de modèle de session (flux de navigation)

**Constat :** le moteur fait ses actions mécaniquement. Pas de simulation d'un utilisateur qui explore, lit, hésite, revient en arrière.

**Pourquoi c'est critique :** les vendeurs 2025-2026 (DataDome, HUMAN) analysent le *flux* de navigation, pas seulement les mouvements individuels. Un bot qui va droit au but sans exploration est un signal fort.

**Ce qui manque :**
- Modèle de session : patterns de browsing humain (loi de Zipf, retours, exploration).
- Temps de lecture proportionnel au contenu visible.
- Pages « non pertinentes » visitées pour simuler une navigation naturelle.
- Patterns d'hésitation et de retour arrière.

### Gap 7 — Pas de base de données de vrais profils

**Constat :** 18 profils construits à la main (8 macOS, 6 Windows, 3 Linux, 1 Chromebook). Les fonts sont des listes codées en dur.

**Pourquoi c'est problématique :**
- 18 profils ≠ diversité réelle. FingerprintJS voit des millions de profils uniques.
- Les combinaisons {GPU, résolution, fonts, extensions} sont plausibles mais pas statistiquement représentatives.
- Un détecteur qui connaît la distribution réelle des fonts par OS/version les repérerait.

**Ce qui manque :**
- Collecte automatisée de vrais profils (headless sur de vraies machines + BrowserStack/Sauce Labs).
- BrowserForge integration (réseau bayésien) pour la génération de profils.
- Centaines de profils, pas 18.

### Gap 8 — Dépendance totale à Patchright pour TLS

**Constat :** si Patchright change de comportement, si le JA4 de Chromium headless devient un signal, ou si Patchright prend du retard sur Chrome, le moteur est exposé.

**Pourquoi c'est risqué :**
- Patchright est un projet tiers avec ses propres priorités.
- La version Chromium embarquée peut être en retard de plusieurs versions.
- Aucun contrôle sur le ClientHello TLS ni les extensions.

**Options :**
- Dual-engine : Patchright (Chromium) + Camoufox (Firefox) sélectionnable par profil.
- Monitoring du JA4 réel du moteur vs le JA4 attendu.
- Abstraction du driver pour changer de backend sans réécrire les scénarios.

### Gap 9 — Jamais testé contre un vrai WAF commercial

**Constat :** toutes les évaluations sont contre l'Arena (notre propre terrain, avec des détecteurs débranchés).

**Ce qui manque :**
- Tests reproductibles contre Cloudflare Free/Pro (sites publics protégés).
- Tests contre DataDome (sites de référence connus).
- Tests contre Akamai (sites e-commerce protégés).
- Métrique : taux de passage par vendeur, reproductibilité sur N sessions.

**Priorité :** après le durcissement de l'Arena (gap 2), tester contre des cibles réelles. Le benchmark Paterson 2026 fournit une méthodologie (31 cibles Cloudflare).

### Gap 10 — Scoring continu absent

**Constat :** chaque détection est binaire (passe/ne passe pas). Pas de score composite, pas de réévaluation au fil de la session.

**Pourquoi c'est critique :** les vendeurs utilisent un scoring continu (Cloudflare bot score 1-99, DataDome score de risque). Le score évolue à chaque requête. L'Arena doit reproduire ce comportement pour être un adversaire réaliste.

**Ce qui manque côté Arena :**
- Score composite (somme pondérée de tous les détecteurs actifs).
- Réévaluation à chaque requête, pas seulement au premier contact.
- Seuils configurables par niveau.

**Ce qui manque côté moteur :**
- Conscience de son propre score (feedback loop).
- Capacité à adapter son comportement si le score monte.

---

## Annexe A — Tableau comparatif des outils anti-détection

| Outil | TLS | HTTP/2 | Fingerprint JS | Comportement | Profils | Challenges | Licence | Score Cloudflare* |
|-------|-----|--------|----------------|-------------|---------|------------|---------|-------------------|
| **NOEZIA v4** | Patchright (correct) | Non contrôlé | 12 scripts (bon) | Minimum-jerk (bon) | 18 profils | PoW + Turnstile test | Propriétaire | Non testé |
| **Camoufox** | Firefox natif | Firefox natif | Natif (invisible) | Mouvement naturel | BrowserForge | Rien | MPL-2.0 | 25/31 |
| **Patchright** | Chromium natif | Chromium natif | Rien | Rien | Rien | Rien | Apache-2.0 | 25/31 |
| **nodriver** | Chromium natif | Chromium natif | Rien | Rien | Rien | Rien | AGPL-3.0 | 28/31 |
| **curl_cffi** | Spoofé (parfait) | Spoofé (parfait) | N/A (pas de JS) | N/A | Header spoofing | Impossible | MIT | N/A |
| **Scrapling** | Via Patchright | Non contrôlé | Via Patchright | Rien | Rien | Cloudflare intégré | BSD-3 | Non testé |
| **puppeteer-stealth** | Chromium | Non contrôlé | 11 plugins (faible) | Rien | Rien | Rien | MIT | Obsolète |

*Score Cloudflare = OK / total sur le benchmark Paterson 2026 (31 cibles Cloudflare, résultat OK = page chargée sans blocage).*

## Annexe B — Signaux de détection par couche

```
Couche 1 — Réseau/Transport
├── IP reputation (datacenter vs résidentiel, ASN)
├── TLS fingerprint (JA4)
├── HTTP/2 fingerprint (SETTINGS, pseudo-headers, priorities)
├── HTTP/3 fingerprint (QUIC)
├── TCP/IP OS fingerprint (p0f, TTL, window size)
└── Rate patterns (fréquence, régularité, distribution)

Couche 2 — Protocole HTTP
├── Headers order (JA4H)
├── Accept-Language format
├── Sec-Fetch-* headers
├── Cookie presence/format
├── Referer presence
└── Critical-CH response handling

Couche 3 — Navigateur (passif)
├── navigator.webdriver
├── navigator.plugins / mimeTypes
├── navigator.languages
├── navigator.hardwareConcurrency / deviceMemory
├── screen.width/height / window.outerWidth/outerHeight
├── chrome.app / chrome.runtime / chrome.loadTimes
├── permissions.query() (all granted = suspect)
└── NetworkInformation API (rtt, downlink)

Couche 4 — Fingerprinting actif
├── Canvas 2D hash
├── WebGL vendor/renderer + 17 paramètres
├── AudioContext hash
├── Font enumeration (measureText)
├── Client Hints (Sec-CH-UA-*)
└── Cross-session correlation (même hash = bot)

Couche 5 — Intégrité
├── Function.prototype.toString() sur APIs patchées
├── Object.getOwnPropertyDescriptor() sur getters injectés
├── Double exécution canvas (non-déterminisme = injection)
├── Error.stack analysis (frames CDP/Playwright)
├── Prototype chain integrity (own properties sur navigator/screen)
├── Enumerable flags (patches oublient souvent {enumerable: false})
├── toString/instanceof sur NavigatorUAData (Proxy détecté)
└── Worker consistency (main vs worker values)

Couche 6 — Comportement
├── Mouse movement entropy (CV des délais)
├── Mouse trajectory analysis (Bézier détectable)
├── Fitts' law compliance (temps vs distance vs taille)
├── Scroll patterns (inertie, micro-corrections)
├── Keyboard typing rhythm (digraphs, n-grams)
├── Reading time proportional to content
├── Navigation flow (exploration vs direct)
└── Session-level behavioral scoring (ML)

Couche 7 — Timing
├── requestAnimationFrame deltas (vsync = ~16.67ms)
├── performance.now() precision
├── Paint timing (first-paint, first-contentful-paint)
├── PoW resolution time vs hardwareConcurrency
└── SharedArrayBuffer timing
```

## Annexe C — Publications académiques pertinentes

| Référence | Année | Contribution |
|-----------|-------|-------------|
| **FP-Inconsistent** (arXiv 2406.07647) | 2024-2025 | Détection de bots évasifs par incohérences de fingerprint. 44-48% de réduction du trafic évasif vs DataDome/BotD. |
| **FP-Agent** (arXiv 2605.01247) | 2025 | Fingerprinting des agents IA navigateurs. |
| **"On the Internet Nobody Knows You're an LLM Bot"** (arXiv 2606.30119) | 2026 | Fingerprinting multi-couches des agents LLM. |
| **FP-Radar** (arXiv 2112.01662) | 2021 | Mesure longitudinale et détection précoce du fingerprinting navigateur. |
| Akamai HTTP/2 fingerprinting (Black Hat EU) | 2017 | Recherche fondatrice sur 10M+ connexions HTTP/2. |

## Annexe D — Feuille de route suggérée (par impact)

| Priorité | Action | Impact estimé | Effort |
|----------|--------|--------------|--------|
| **P0** | Brancher les détecteurs existants au gardien (Arena) | Le moteur échoue → on sait quoi corriger | ~50 lignes |
| **P0** | Score composite dans le gardien | Arena réaliste | ~150 lignes |
| **P1** | Détecteur HTTP/2 (Arena) | Signal le plus différenciant | ~300 lignes |
| **P1** | Canvas déterministe intra-session (moteur) | Passe le double-appel toDataURL | ~100 lignes |
| **P1** | WebGL complet : 17+ paramètres (moteur) | Passe les checks FingerprintJS | ~200 lignes |
| **P2** | Corrélation canvas cross-session (Arena) | Détecte les réseaux de bots | ~100 lignes |
| **P2** | Audio fingerprint complet (moteur) | getChannelData + cohérence | ~150 lignes |
| **P2** | Modèle de session / flux de navigation (moteur) | Passe l'analyse DataDome/HUMAN | ~500 lignes |
| **P3** | Base de données de vrais profils | Diversité réaliste | ~300 lignes + collecte |
| **P3** | Dual-engine Patchright + Camoufox | Résilience + Firefox TLS | ~400 lignes |
| **P3** | Tests contre vrais WAF (Cloudflare, DataDome) | Validation externe | Config + analyse |
| **P4** | Font fingerprint avec référentiel par OS | Cohérence fonts ↔ OS | ~200 lignes |
| **P4** | Scoring continu + feedback loop (moteur) | Adaptation en temps réel | ~300 lignes |

---

*Document généré le 10/11/2026 pour le brainstorming NOEZIA v5.*
*Prochaine mise à jour recommandée : après durcissement Arena et premiers tests contre vrais WAF.*
