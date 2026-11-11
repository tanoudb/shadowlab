---
permalink: noezia-shadowlab/recherche-antibot-2026
title: recherche-antibot-2026
type: note
---

# État de l'art anti-bot 2025-2026 — Référence pour brainstorming NOEZIA

*Recherche du 10/11/2026. Sources : blogs spécialisés, reverse-engineering communautaire, docs vendeurs. Les chiffres exacts sont à vérifier contre les docs officielles.*

---

## 1. Signaux utilisés par les détecteurs commerciaux

### 1.1 Couche transport — TLS et HTTP/2

**JA4 (successeur de JA3)** est le standard 2025-2026. Contrairement à JA3, les cipher suites et extensions sont triées avant hachage → la randomisation TLS de Chrome ne casse plus l'empreinte. Adopté par Cloudflare (Bot Management Enterprise), Akamai, AWS WAF.

**HTTP/2 fingerprinting** — signaux :
- **SETTINGS frame** : valeurs et **ordre** des paramètres (HEADER_TABLE_SIZE, MAX_CONCURRENT_STREAMS, INITIAL_WINDOW_SIZE, MAX_HEADER_LIST_SIZE)
- **WINDOW_UPDATE** initial
- **Ordre des pseudo-headers** : Chrome envoie `:method, :authority, :scheme, :path` ; Firefox envoie `:method, :path, :authority, :scheme`
- **PRIORITY / PRIORITY_UPDATE** : Chrome les utilise, curl ne les envoie pas
- Désactiver HTTP/2 est lui-même un signal (anomalie)

Akamai a publié en 2017 une recherche sur 10M+ connexions HTTP/2 avec empreintes pour 40 000+ user-agents. Les vendeurs croisent JA4 + HTTP/2 + User-Agent pour détecter les incohérences.

Sources : [Scrapfly — JA3/JA4 Guide](https://scrapfly.io/blog/posts/ja3-ja4-tls-fingerprinting-guide-to-detection-and-evasion), [Scrapfly — HTTP/2 Guide](https://scrapfly.io/blog/posts/http2-http3-fingerprinting-guide), [krowdev — Bot Detection 2026](https://krowdev.com/article/bot-detection-2026/), [send.win — HTTP/2 Fingerprinting](https://blog.send.win/http2-fingerprinting-browser-detection/)

### 1.2 Couche navigateur — Fingerprinting actif

| Signal | Ce qu'il mesure | Détection bot |
|--------|----------------|---------------|
| **Canvas** | Hash du rendu 2D (texte + gradient) | Hash identique entre sessions = bot ; bruit trop régulier = injection ; incohérence avec GPU annoncé |
| **WebGL** | Vendor + Renderer + extensions | Doit être cohérent avec l'OS et le GPU réel ; "SwiftShader" ou "Google Inc." en headless = signal fort |
| **AudioContext** | Hash de l'oscillateur | Même logique que canvas — bruit artificiel détectable |
| **Fonts** | Ensemble de polices disponibles | Doit correspondre à l'OS annoncé |
| **Navigator deep** | `navigator.webdriver`, plugins, languages, platform, hardwareConcurrency, deviceMemory | Incohérences croisées (ex: `platform: "Win32"` + fonts macOS) |

**Vérification d'intégrité** (critique 2025-2026) :
- `Function.prototype.toString()` sur les APIs patchées → révèle si `toDataURL`, `getParameter`, etc. ont été modifiées (le code source patché remplace `[native code]`)
- `Object.getOwnPropertyDescriptor()` pour détecter les getters installés par injection
- Exécution du canvas **deux fois** et comparaison : un bruit non-déterministe entre les deux = injection
- Analyse de `Error.stack` pour des frames CDP ou Playwright

Sources : [Scrapfly — How Cloudflare Detects Bots](https://scrapfly.io/blog/posts/how-cloudflare-detects-bots), [Edioff/akamai-analysis (GitHub)](https://github.com/Edioff/akamai-analysis), [send.win — Akamai Detection Guide](https://blog.send.win/how-akamai-bot-manager-detects-browsers-browser-isolation-guide-2026/)

### 1.3 Couche comportementale — ML et biométrie

**DataDome** : ML-first, 85 000+ modèles client-spécifiques, 35-300+ signaux par session (chiffres contradictoires selon les sources). Depuis 2025 : détection d'intention (comparaison du flux de navigation avec les patterns humains connus).

**HUMAN (ex-PerimeterX)** : score de confiance par session qui évolue au fil de la visite. Recherche publiée sur la distinction mouvements souris humains vs courbes de Bézier. Signaux : trajectoire souris, vélocité de scroll, intervalles entre clics, patterns de frappe.

**Kasada** : centré sur l'interrogation de l'environnement navigateur + proof-of-work. Impose un coût computationnel réel au scraping à grande échelle.

**Signaux comportementaux communs (tous vendeurs)** :
- Séquences de coordonnées souris + accélération
- Patterns de scroll (inertie, phases)
- Timing entre les clics
- Rythme de frappe clavier
- Temps de lecture proportionnel au contenu
- Flux de navigation (pages visitées, ordre, durée)

Sources : [justbrowser — Anti-Bot 2026 Comparison](https://justbrowser.app/blog/anti-bot-detection-vendors-2026-landscape), [rcaptcha — Bot Mitigation Comparison 2025](https://blog.rcaptcha.app/articles/bot-mitigation-tools-comparison-2025)

### 1.4 Couche réseau et scoring

- **IP reputation** : datacenter vs résidentiel, ASN, géolocalisation vs timezone annoncée
- **Rate patterns** : fréquence, régularité, distribution des requêtes
- **Score continu** (pas binaire) : réévalué à chaque requête, pas juste au premier contact
- **Corrélation multicouche** : une contradiction entre deux couches quelconques suffit (ex: JA4 Chrome + HTTP/2 Firefox = bot)

---

## 2. Techniques d'évasion — État de l'art open source

| Outil | Approche | Forces | Faiblesses |
|-------|----------|--------|------------|
| **Camoufox** | Fork Firefox compilé avec stealth intégré | Meilleur taux contre fingerprinting (100% dans un benchmark 2026) ; modifications invisibles au JS | TLS Firefox détectable par certains CDN ; dépendances playwright<1.63 ; AGPL |
| **Patchright** | Fork Playwright avec patches Chromium au build | TLS Chrome natif ; API Playwright complète | Aucun spoofing de fingerprint — laisse l'empreinte réelle |
| **nodriver/zendriver** | CDP direct sans WebDriver | Pas de flag `navigator.webdriver` | Aucune couche anti-fingerprinting ; CDP detectable via `Error.stack` |
| **undetected-chromedriver** | Patches runtime Chrome | Simple à utiliser | Stale (dernière release fév. 2024, pré-Chrome 122) ; auteur redirige vers nodriver |
| **puppeteer-extra-stealth** | Plugins JS sur Puppeteer | Écosystème riche | Patches JS visibles via `toString()` ; couverture limitée |
| **curl-cffi / impit** | Impersonation TLS au niveau HTTP | JA3/JA4 parfaits ; très rapide | Pas de JS → ne passe pas les challenges navigateur |

**Points faibles communs** : aucun outil open source ne gère correctement l'ensemble {TLS + HTTP/2 + fingerprint navigateur + comportement + cohérence inter-couches}. Chaque outil est fort sur 1-2 couches et faible sur les autres.

Sources : [dev.to — Anti-detect Benchmark 2026](https://dev.to/ianlpaterson/anti-detect-browser-benchmark-2026-7-stealth-tools-31-cloudflare-targets-651-verdicts-4361), [ScrapingBee — UC Guide 2026](https://www.scrapingbee.com/blog/undetected-chromedriver-python-tutorial-avoiding-bot-detection/), [Scrapfly — Best Stealth Browsers](https://scrapfly.io/blog/posts/best-stealth-browsers)

---

## 3. Détecteurs implémentables dans notre Arena

Basé sur les signaux réels des vendeurs, voici ce qu'on peut reproduire localement :

### Priorité haute (signaux les plus discriminants)

1. **DetecteurEmpreinteHTTP2** — Capturer le SETTINGS frame, WINDOW_UPDATE, ordre des pseudo-headers. Comparer avec les profils connus (Chrome, Firefox, Safari, curl). C'est le signal le plus difficile à spoofer.

2. **DetecteurCoherenceCroisee** — Le cœur de la détection moderne. Vérifier la cohérence entre : JA4 ↔ User-Agent ↔ HTTP/2 ↔ navigator ↔ canvas ↔ WebGL ↔ fonts ↔ timezone ↔ locale. Une seule contradiction = bot.

3. **DetecteurIntegriteAPI** — `Function.prototype.toString()` sur les APIs sensibles (canvas, WebGL, navigator). Double exécution canvas et comparaison. `Object.getOwnPropertyDescriptor` sur les propriétés critiques. Analyse `Error.stack` pour frames CDP/Playwright.

### Priorité moyenne

4. **DetecteurCanvasUnique** — Hash canvas côté serveur. Unicité : un hash vu N+ fois sur des sessions différentes = bot. Cohérence : hash plausible pour le GPU annoncé. Entropie du bruit pixel-à-pixel (bruit trop régulier = injection).

5. **DetecteurEntropieTiming** — Entropie de Shannon des intervalles entre événements souris. Autocorrélation des vitesses (détecte les Bézier). Vérification de la loi de Fitts (temps vs distance vs taille cible). Distribution des pauses de lecture.

6. **DetecteurFluxNavigation** — Pattern d'accès aux pages (ordre, durée, pages ignorées). Un bot qui va droit au but sans explorer = signal. Temps de lecture proportionnel au contenu.

### Priorité basse (avancé)

7. **DetecteurProofOfWork** — Challenge computationnel côté client (style Kasada). Mesure le temps de résolution vs la puissance annoncée (`hardwareConcurrency`).

8. **DetecteurAttestationNavigateur** — Vérifier des signaux impossibles à simuler sans vrai navigateur : `performance.now()` résolution, `SharedArrayBuffer` timing, API spécifiques récentes.

---

## 4. Tendances 2026

1. **ML comportemental dominant** — Les vendeurs convergent vers des modèles ML par client (DataDome : 85K modèles) plutôt que des règles statiques. Le comportemental est le signal le plus difficile à falsifier.

2. **Proof-of-Work invisible** — Cloudflare Turnstile, Kasada : le challenge est transparent pour l'humain mais impose un coût au bot. Tendance à l'escalade du coût computationnel.

3. **"Proof of Browser"** — DataDome (2026) : vérification VM-obfusquée que le client est un vrai navigateur, pas un environnement émulé. Logique d'obfuscation du code de vérification lui-même.

4. **Scoring continu** — Plus de décision binaire au premier contact. Le score évolue au fil de la session, avec réévaluation à chaque requête.

5. **Détection des agents IA** — Recherche émergente (arXiv 2026 : "FP-Agent", "On the Internet Nobody Knows You're an LLM Bot") sur le fingerprinting des agents IA qui naviguent le web. Nouveau front de détection.

6. **Web Bot Auth (Cloudflare)** — Proposition de vérification cryptographique de l'identité des bots légitimes, en remplacement des méthodes basées sur l'IP.

7. **Corrélation multi-session** — Les vendeurs commencent à corréler les signaux entre sessions (même fingerprint canvas vue avec des IPs différentes = réseau de bots).

Sources : [Fingerprint.com — Bot Detection 2026](https://fingerprint.com/blog/bot-detection/), [Crawlbase — Bot Detection Engineering Guide](https://crawlbase.com/blog/bot-detection-2026-engineering-guide/), [POH Research — Bot Benchmarking 2026](https://research.poh.org/bot-benchmarking-2026/), [arXiv — FP-Agent](https://arxiv.org/pdf/2605.01247)

---

## Implications pour NOEZIA

**Pour passer de 3/10 à 6/10**, il faut :
- Reproduire la cohérence inter-couches dans l'Arena (détecteur n°2 ci-dessus)
- Que le moteur gère sa propre empreinte HTTP/2 (pas seulement TLS via Patchright)
- Un comportement humain qui passe l'analyse d'entropie et Fitts' law (pas juste des Bézier)
- Des profils navigateur qui tiennent la vérification `toString()` et la double exécution canvas

**L'Arena durcie doit être l'adversaire crédible** qui force le moteur à s'améliorer. Sans elle, on optimise dans le vide.