# Audit des protections Arena — niveaux 01 à 06

**Date** : 2026-11-05
**Campagnes** : #15 (niveaux 01-03, 5 moteurs × 4 scénarios × 30 reps = 1800 passages)
et #16 (niveaux 04-06, 3 moteurs × 4 scénarios × 30 reps = 1080 passages)
**Résultats bruts** : `outputs/shadowlab.sqlite3`, tables `runs`, `decisions`, `detections`

---

## 1. Inventaire des détecteurs

L'Arena dispose de 6 détecteurs. Chacun classe une session en `automatise`, `humain` ou
`indetermine`. Seuls 5 d'entre eux alimentent les décisions de blocage.

### 1.1 regles-http (v2) — En-têtes HTTP

**Signaux testés** (10) :
- `ua_absent` — User-Agent absent
- `ua_outil` — User-Agent contient python/curl/httpx/requests/aiohttp/wget…
- `ua_headless` — User-Agent contient HeadlessChrome
- `headless_dans_une_requete` (v2.1, 12/11/2026) — « HeadlessChrome » dans le User-Agent ou dans `sec-ch-ua`
  d'une requête quelconque de la session (fichiers, envois, redirections), pas seulement de la première page
- `langue_absente` — Accept-Language absent
- `sec_fetch_absent` — Navigateur annoncé sans Sec-Fetch-*
- `accept_generique` — Navigation avec Accept: */*
- `client_hints_absents` — Chrome annoncé sans Sec-CH-UA
- `h2c` — Passage HTTP/2 en clair demandé
- `host_tardif` — En HTTP/1.1, Host n'est pas le premier en-tête
- `referent_incoherent` — Sec-Fetch-Site « none » avec un Referer
- `cookies_ignores` — Cookies de session jamais renvoyés

**Ce qu'il ne teste pas** :
- Ordre complet des en-têtes (fingerprint d'ordre)
- Format exact de l'en-tête Accept pour Chrome vs Firefox
- Valeurs de Accept-Encoding (navigateurs envoient gzip, deflate, br, zstd)
- Sec-CH-UA-Full-Version-List et autres Client Hints
- Majuscules/minuscules des noms d'en-têtes
- En-tête Connection (keep-alive vs absent en HTTP/2)

### 1.2 tls (v1) — Structure du ClientHello TLS

**Signaux testés** (4) :
- `chrome_sans_grease` — Chrome annoncé sans GREASE
- `firefox_avec_grease` — Firefox annoncé avec GREASE
- `navigateur_sans_h2` — Navigateur annoncé sans HTTP/2 dans l'ALPN
- `pile_non_navigateur` — Ni GREASE ni HTTP/2 : pile TLS de bibliothèque

**Ce qu'il ne teste pas** :
- Comparaison JA3/JA4 avec des valeurs connues de navigateurs réels
- Ordre et contenu des cipher suites
- Extensions TLS (supported_groups, signature_algorithms, key_share)
- Analyse de la taille et structure du ClientHello
- Correspondance empreinte TLS ↔ User-Agent ↔ version navigateur

### 1.3 botd (v2.0.0) — BotD de FingerprintJS

**Signaux testés** : Délégué entièrement à la bibliothèque BotD.
**Limitation** : Nécessite l'exécution de JavaScript. Camoufox patche suffisamment de
propriétés pour que BotD le classe « humain ».

### 1.4 regles-js (v1) — Propriétés JavaScript

**Signaux testés** (8) :
- `webdriver` — navigator.webdriver = true
- `ua_headless` — HeadlessChrome dans navigator.userAgent
- `marque_headless` — HeadlessChrome dans userAgentData.brands
- `langues_vides` — navigator.languages vide
- `fenetre_nulle` — outerWidth ou outerHeight = 0
- `plugins_vides` — Chrome sans aucun plugin
- `permissions_incoherentes` — Notification denied + query prompt
- `webgl_logiciel` — SwiftShader dans le renderer WebGL

**Ce qu'il ne teste pas** :
- navigator.webdriver après patch (Patchright le masque à false)
- Vérification Function.toString() sur des fonctions natives patchées
- Détection de Chrome DevTools Protocol (CDP)
- Globales d'automatisation (window.cdc_*, __playwright, __selenium, etc.)
- Stack trace analysis (les frames Playwright/Puppeteer)
- Object.getOwnPropertyDescriptor sur navigator.webdriver
- Analyse du prototype chain des objets natifs
- Détection d'iframes de contrôle

### 1.5 coherence (v1) — Cohérence HTTP ↔ JavaScript

**Signaux testés** (3) :
- `ua_divergent` — User-Agent HTTP ≠ navigator.userAgent
- `langue_divergente` — Langue HTTP ≠ navigator.language
- `plateforme_divergente` — Sec-CH-UA-Platform ≠ userAgentData.platform

**Ce qu'il ne teste pas** :
- Résolution écran vs viewport vs taille fenêtre
- Fuseau horaire vs langue déclarée
- Nombre de polices vs système d'exploitation déclaré
- Canvas/WebGL fingerprint vs GPU/renderer déclaré

### 1.6 comportement (v1) — Analyse comportementale

**Signaux testés** (5) :
- `sans_ressources` — Aucun CSS/JS chargé
- `rythme_soutenu` — Plus de 4 pages/seconde
- `aucune_interaction` — Aucun mouvement, clic, touche ni défilement
- `clic_sans_souris` — Clics sans mouvement de souris
- `pages_eclair` — Moins de 500 ms par page en moyenne

**⚠ PROBLÈME CRITIQUE : Ce détecteur n'est PAS dans la chaîne de blocage.**

Le gardien consulte `REGLES_REQUETE = ("regles-http", "tls")` et
`REGLES_JAVASCRIPT = ("botd", "regles-js", "coherence")`. Le détecteur `comportement`
n'apparaît dans aucune de ces listes. Il est exécuté pour l'affichage (page /lab/detection)
et enregistré dans la table `detections`, mais n'a **aucun effet sur les décisions de blocage**.

**Ce qu'il ne teste pas** (même s'il était connecté) :
- Naturalité des trajectoires de souris (courbes de Bézier vs lignes droites)
- Cadence de frappe (timing inter-touches)
- Patterns de défilement (scroll discret vs scroll fluide)
- Distribution spatiale des clics
- Pause avant interaction (temps de lecture)

---

## 2. Chaîne de décision du gardien (par niveau)

Le gardien (`gardien.py:controler()`) applique les protections **dans l'ordre** :
1. `defi_js` → preuve de travail SHA-256
2. `fingerprinting` → blocage si `suspicion()` retourne des motifs
3. `turnstile` → challenge Cloudflare (test keys)
4. `recaptcha` → challenge Google (test keys)
5. `captcha` → demo CAPTCHA (seulement si `suspicion()` retourne des motifs)

**Conséquence** : un moteur bloqué par une couche n'atteint jamais les suivantes. Un moteur
qui passe le fingerprinting sans motifs ne reçoit jamais le demo CAPTCHA (étape 5).

### Niveau 01 — Baseline

| Protection | Active | Signaux | Décision |
|---|---|---|---|
| Toutes | Non | Aucun | Aucune |

**Résultat** : tous les moteurs à 100%. C'est la référence fonctionnelle.

### Niveau 02 — Détection simple

| Protection | Active | Signaux consultés |
|---|---|---|
| Fingerprinting | Oui, `bloquer: http` | regles-http + tls uniquement |
| Limitation | 20 req/s, rafale 40 | Compteur Nginx |
| WAF | Détection seule | Coraza, paranoia 1 |

**Ce qui bloque** :
- httpx → `ua_outil` (python-httpx/0.28.1) + `pile_non_navigateur`
- patchright → `ua_headless` (HeadlessChrome) + `langue_absente`
- playwright → `ua_headless` (HeadlessChrome) + `langue_absente`

**Ce qui passe** :
- camoufox → UA = `Mozilla/5.0 … Firefox/158.0`, Accept-Language = `en-US,en;q=0.9`, TLS Firefox légitime
- scrapling-furtif → UA = `Mozilla/5.0 … Chrome/156.0`, Accept-Language = `fr-FR,fr;q=0.9`, TLS Chrome légitime

**Ce que le niveau ne sait pas détecter** :
- Tout moteur avec un UA normal et un Accept-Language présent
- Aucune analyse JavaScript (explicitement désactivée par `bloquer: http`)
- Aucune analyse comportementale

### Niveau 03 — Fingerprinting

| Protection | Active | Signaux consultés |
|---|---|---|
| Fingerprinting | Oui, `bloquer: tout` | regles-http + tls + botd + regles-js + coherence |
| Limitation | 10 req/s, rafale 25 | Compteur Nginx |

**Signaux JavaScript ajoutés** : webdriver, HeadlessChrome (JS), brands, languages, fenêtre,
plugins, permissions, WebGL, BotD, cohérence UA/langue/plateforme.

**Ce qui bloque** : Identique au niveau 02. httpx/patchright/playwright sont bloqués sur les
signaux HTTP avant que le JavaScript ne soit collecté (la page de blocage est servie au lieu
du contenu, donc l'observateur JS ne s'exécute jamais).

**Ce qui passe et pourquoi** :
- camoufox : BotD → humain, regles-js → humain (webdriver=false, UA correct, plugins
  présents, fenêtre non nulle), coherence → humain (UA/langue cohérents)
- scrapling-furtif : idem

**Ce que le niveau ne sait pas détecter** :
- Le détecteur `comportement` **classerait** ces moteurs comme automatisés (rythme 5-12 p/s,
  aucune interaction, pages < 500 ms) mais il n'est pas consulté.
- Canvas fingerprint : collecté par l'observateur JS mais jamais vérifié par un détecteur.
- FingerprintJS complet : collecté (visitorId, confidence, ~30 composants) sur /lab/empreinte
  mais jamais utilisé pour les décisions.
- Aucune détection CDP/DevTools, aucune vérification de globales d'automatisation.

### Niveau 04 — Challenges

| Protection | Active | Signaux / mécanisme |
|---|---|---|
| Defi JS | Oui, difficulté 12 | SHA-256 proof-of-work |
| Fingerprinting | `bloquer: tout` | Comme niveau 03 |
| Captcha | Oui | Demo CAPTCHA, seulement si suspicion() > 0 |
| WAF | Blocage, paranoia 1 | Coraza CRS |

**Résultats observés** :
- defi-js : **1074 émis, 1074 validés** — les 3 moteurs le résolvent à 100%. C'est trivial
  pour tout moteur qui exécute du JavaScript (calcul SHA-256 dans le navigateur).
- Playwright : bloqué par fingerprinting (comme niveaux 02-03), n'atteint jamais le CAPTCHA.
- Camoufox/scrapling-furtif : passent fingerprinting + defi-js → 100% de réussite.
- Demo CAPTCHA : **jamais servi** à camoufox/scrapling-furtif car `suspicion()` ne retourne
  aucun motif pour eux (les 5 détecteurs les classent humain/indéterminé).

### Niveau 05 — Protection avancée

| Protection | Active | Mécanisme |
|---|---|---|
| Defi JS | Oui, difficulté 15, lié TLS | SHA-256 + cookie lié au JA4 (sans `pre_shared_key` depuis D-73) |
| Fingerprinting | `bloquer: tout` | Comme niveaux 03-04 |
| Turnstile | Oui, test keys | Cloudflare Turnstile (mode test) |
| reCAPTCHA | Oui, test keys | Google reCAPTCHA v2 (mode test) |
| Captcha | Oui | Demo CAPTCHA |
| WAF | Blocage, paranoia 2 | Coraza CRS |

**Résultats observés** :
- Playwright : bloqué par fingerprinting.
- Camoufox/scrapling-furtif : passent fingerprinting + defi-js, puis reçoivent la page
  Turnstile (turnstile `emis` : 480 fois). **Turnstile n'est jamais validé** (0 décisions
  `valide`). Issue = `echec_fonctionnel` (la page de contenu n'est pas atteinte).
- reCAPTCHA : **jamais atteint** — Turnstile le précède dans la chaîne.
- Demo CAPTCHA : **jamais atteint** non plus.

**Pourquoi Turnstile bloque** : le moteur reçoit un 403 avec la page Turnstile. Il faudrait
que le moteur rende la page, attende que le widget Turnstile auto-valide (test keys), soumette
le token au serveur, reçoive le cookie, puis relance la requête originale. Aucun des 3
moteurs testés n'implémente ce flux.

**Ce que cela mesure réellement** : la capacité d'un moteur à résoudre un flux challenge
multi-étapes, pas la résistance au vrai Turnstile de Cloudflare (test keys ≠ production).

### Niveau 06 — Défense multicouche

| Protection | Active | Mécanisme |
|---|---|---|
| Tout le niveau 05 | Oui | Idem |
| Honeypots | Oui | Lien piège + champ piège |
| WAF | Blocage, paranoia 3 | Coraza CRS max |
| Limitation | 2 req/s, rafale 4 | Très restrictif |

**Résultats observés** : Identiques au niveau 05. Honeypots jamais déclenchés (les scénarios
ne cliquent pas sur les liens piège et ne remplissent pas les champs cachés).

---

## 3. Résultats par scénario

**Constat** : les 4 scénarios testés (static_html, pagination, session_cookies, api_json)
produisent des résultats **strictement identiques** pour chaque cellule moteur × protection.
30/30 ou 0/30, sans aucune variance.

Cela confirme que le blocage est déterminé par les signaux de session (en-têtes HTTP, TLS),
pas par le comportement spécifique du scénario. Un moteur bloqué le sera quel que soit le
scénario ; un moteur qui passe le fingerprinting réussira tous les scénarios.

Les scénarios `burst_crawl` et `synthetic_browse` n'étaient pas dans ces campagnes.

---

## 4. Faiblesses structurelles identifiées

### F1. Détecteur comportemental déconnecté (critique)

Le détecteur `comportement` classe régulièrement camoufox et scrapling-furtif comme
`automatise` :
- **scrapling-furtif** : 90× `aucune_interaction` + `pages_eclair`, plus ~70× `rythme_soutenu`
  (5-12 pages/seconde)
- **camoufox** : ~80× `rythme_soutenu` (5-10 pages/seconde) + `pages_eclair`

Mais `gardien.py` ne consulte que `REGLES_REQUETE` et `REGLES_JAVASCRIPT`, qui n'incluent
pas `comportement`. **Ces signaux sont enregistrés mais n'ont aucun effet.**

**Correction** : ajouter `"comportement"` à `REGLES_JAVASCRIPT` dans gardien.py.

### F2. Données collectées mais jamais exploitées

L'observateur JavaScript collecte des données riches qui ne servent à aucun détecteur :
- **Canvas fingerprint** (SHA-256 du rendu canvas) — collecté, jamais vérifié
- **FingerprintJS complet** (visitorId, confidence, ~30 composants) — collecté sur
  /lab/empreinte, jamais utilisé pour les décisions
- **APIs exposées** (bluetooth, USB, serial, HID, share, credentials, mediaDevices,
  speechSynthesis, serviceWorker) — collectées, jamais vérifiées
- **Informations écran** (résolution, colorDepth, devicePixelRatio) — collectées,
  jamais croisées avec d'autres signaux
- **Fuseau horaire** — collecté, jamais croisé avec la langue

### F3. Détection JavaScript inaccessible pour les moteurs bloqués en HTTP

Les moteurs bloqués au niveau 02 (httpx, patchright, playwright) reçoivent la page de
blocage (403) **au lieu du contenu**. L'observateur JavaScript ne s'exécute jamais pour eux.
On ne sait donc pas ce que les détecteurs JavaScript auraient trouvé.

**Conséquence** : on ne peut pas évaluer la qualité de l'empreinte JavaScript de patchright
(qui est censé masquer `navigator.webdriver`).

### F4. Chaîne séquentielle : protections masquées

L'ordre fixe (defi_js → fingerprinting → turnstile → recaptcha → captcha) fait que :
- reCAPTCHA n'est jamais atteint si Turnstile bloque (niveaux 05-06)
- Le demo CAPTCHA n'est jamais servi aux moteurs qui passent le fingerprinting
- On ne sait pas si un moteur résoudrait reCAPTCHA ou le demo CAPTCHA

### F5. Déterminisme total : pas de mesure probabiliste

2 880 passages (campagnes #15 + #16) sont tous à 30/30 ou 0/30. Les intervalles de Wilson
sont soit [88.6-100.0%] soit [0.0-11.4%]. Aucune cellule n'a de variance.

Cela signifie que les protections fonctionnent comme des **règles binaires** (signature
présente → blocage, absente → passage), pas comme des heuristiques probabilistes. Ce n'est
pas représentatif des systèmes anti-bot réels qui utilisent des scores de risque graduels.

### F6. Test keys Turnstile/reCAPTCHA ≠ production

Les test keys de Cloudflare (`1x00000000000000000000AA`) et de Google font que le widget
s'auto-valide. Un moteur capable de rendre la page et de soumettre le token passerait
automatiquement. Cela ne prouverait rien contre les vrais CAPTCHA en production.

**Ce qui est mesuré** : la capacité du moteur à gérer un flux challenge (recevoir 403 →
rendre la page → soumettre → reprendre). C'est utile mais doit être clairement étiqueté.

### F7. Honeypots inefficaces contre les scénarios scriptés

Les honeypots (lien piège `<a class="sl-hp">` et champ piège) ne sont déclenchés que par
des crawlers qui suivent tous les liens ou remplissent tous les champs. Les scénarios
de l'Arena sont ciblés : ils naviguent vers des pages précises par URL ou par sélecteur
CSS spécifique. Les honeypots sont donc structurellement inopérants contre eux.

### F8. Pas de détection CDP/DevTools

Aucun détecteur ne vérifie :
- La présence de Chrome DevTools Protocol (CDP)
- Les globales ajoutées par les outils (`window.cdc_*`, `__playwright`, `__selenium`)
- Les modifications du prototype chain des objets natifs
- Les stack traces contenant des frames d'automatisation

---

## 5. Résumé par moteur

### httpx
- **Bloqué à partir du niveau 02** par `regles-http` (ua_outil) + `tls` (pile_non_navigateur)
- Raison : User-Agent `python-httpx/0.28.1`, pile TLS de bibliothèque sans GREASE ni HTTP/2
- **Démontré** : le blocage est justifié et reproductible

### patchright
- **Bloqué à partir du niveau 02** par `regles-http` (ua_headless + langue_absente)
- Raison : lance Chrome en mode HeadlessChrome sans Accept-Language
- **Non démontré** : ce que les détecteurs JS trouveraient (patchright masque webdriver)
- L'Arena ne teste pas les signaux que patchright prétend masquer

### playwright
- **Bloqué à partir du niveau 02** par `regles-http` (ua_headless + langue_absente)
- Identique à patchright pour les signaux HTTP
- **Non démontré** : différence réelle patchright vs playwright au-delà de l'UA

### camoufox
- **Passe les niveaux 01-04 à 100%**
- **Bloqué au niveau 05** par Turnstile (ne gère pas le flux challenge)
- Le détecteur `comportement` le classerait comme automatisé (rythme 5-10 p/s, pages < 500 ms)
  mais ce détecteur n'est pas connecté aux décisions
- BotD le classe « humain »
- **Démontré** : passe les vérifications HTTP, TLS, JS et BotD
- **Non démontré** : résistance à une analyse comportementale ou à un fingerprint canvas/WebGL

### scrapling-furtif
- **Passe les niveaux 01-04 à 100%**
- **Bloqué au niveau 05** par Turnstile
- Le détecteur `comportement` le classerait comme automatisé (aucune interaction + rythme
  5-12 p/s) mais n'est pas connecté
- **Démontré** : passe les vérifications HTTP, TLS, JS et BotD
- **Non démontré** : résistance à toute analyse au-delà des signaux actuels

---

## 6. Ce qui est démontré, probable et non testé

### Démontré (reproductible, n=30, déterministe)
- httpx, patchright, playwright sont détectables par 2-3 signaux HTTP triviaux
- camoufox et scrapling-furtif passent les 10 signaux HTTP et les 8 signaux JS de l'Arena
- BotD ne détecte ni camoufox ni scrapling-furtif
- Le defi-js (SHA-256 PoW) est trivial pour tout moteur qui exécute du JavaScript
- Turnstile (test keys) bloque les moteurs qui ne gèrent pas le flux challenge multi-étapes
- Les scénarios ne produisent aucune variance : le blocage est purement basé sur la session

### Probable (signaux enregistrés, pas de blocage)
- Le détecteur comportemental **pourrait** bloquer camoufox et scrapling-furtif s'il était
  connecté à la chaîne de décision (signaux `rythme_soutenu`, `aucune_interaction`,
  `pages_eclair` relevés avec une fréquence significative)
- Les données canvas, FingerprintJS et écran **pourraient** différencier ces moteurs d'un
  humain si des détecteurs les exploitaient

### Non testé
- Résistance de patchright à la détection JavaScript (bloqué avant l'exécution JS)
- Différence réelle entre patchright et playwright au-delà du User-Agent
- Résistance de camoufox/scrapling à : détection CDP, analyse de prototype, stack traces,
  canvas/WebGL fingerprinting, timing analysis, header order fingerprinting
- reCAPTCHA (jamais atteint dans la chaîne)
- Demo CAPTCHA contre moteurs non suspectés
- Honeypots contre un crawler aveugle
- Turnstile/reCAPTCHA en production (hors périmètre D-15)
- Comportement sous limitation de débit stricte (scénario burst_crawl non inclus)

---

## 7. Corrections recommandées (par priorité)

1. **Connecter le détecteur `comportement`** à la chaîne de blocage (ajouter à
   `REGLES_JAVASCRIPT`). C'est le seul changement qui rendrait les résultats non
   déterministes pour camoufox/scrapling.

2. **Exploiter les données collectées** : créer un détecteur pour le canvas fingerprint
   et les APIs exposées (au minimum : canvas hash stable entre sessions → empreinte
   réelle vs headless).

3. **Ajouter la détection CDP/DevTools** : vérifier `window.cdc_*`, `__playwright`,
   modification de `Object.getOwnPropertyDescriptor(navigator, 'webdriver')`.

4. **Permettre le test parallèle des challenges** : option pour tester chaque challenge
   indépendamment au lieu de la chaîne séquentielle.

5. **Inclure les scénarios `burst_crawl` et `synthetic_browse`** dans les campagnes de
   référence — ce sont les seuls qui produiraient des signaux comportementaux différenciés.

6. **Ajouter un mode « observation seule »** au fingerprinting (détection sans blocage)
   pour collecter les signaux JS de patchright/playwright.

7. **Ajouter un mode « fingerprinting détaillé »** au niveau 03 : exploiter FingerprintJS
   pour comparer les visitorId entre sessions du même moteur.

---

## 8. Résultats post-corrections (campagne #17)

**Date** : 2026-11-05
**Campagne** : #17 `post_corrections_v1` — 7 moteurs × 6 niveaux × 10 scénarios × 10 reps = 4 200 passages
**Corrections appliquées** :
- F1 : `comportement` connecté à `REGLES_JAVASCRIPT` dans `gardien.py`
- F2 : `canvas_erreur` ajouté à `regles-js` v2 dans `detection.py`
- F8 : détection CDP/automation (`cdc_*`, `__playwright`, `__selenium`, `webdriver_patched`) dans `observateur.js` + `detection.py`

### 8.1 Impact mesuré

| Moteur | Niveau | Avant (rép.) | Après (rép.) | Delta | Cause |
|--------|--------|-------------|-------------|-------|-------|
| camoufox | 03 | 120/120 (100%) | 80/100 (80%) | **-20pp** | F1 : comportement |
| camoufox | 04 | 120/120 (100%) | 80/100 (80%) | **-20pp** | F1 : comportement |
| scrapling-furtif | 03 | 120/120 (100%) | 80/100 (80%) | **-20pp** | F1 : comportement |
| scrapling-furtif | 04 | 120/120 (100%) | 80/100 (80%) | **-20pp** | F1 : comportement |
| Tous les autres | * | inchangé | inchangé | 0 | — |

### 8.2 Scénarios bloqués vs passants (camoufox et scrapling-furtif, niveaux 03-04)

| Scénario | Résultat | Raison |
|----------|----------|--------|
| `burst_crawl` | **0/10 (bloqué)** | 30 requêtes rapides → `rythme_soutenu` + `pages_eclair` |
| `pagination` | **0/10 (bloqué)** | pages séquentielles rapides → `aucune_interaction` + `pages_eclair` |
| 8 autres scénarios | **10/10 (passe)** | une seule page → pas assez de signaux comportementaux |

### 8.3 Efficacité par correction

**F1 (comportement connecté)** — **seule correction à impact mesurable**.
Le détecteur comportemental détecte l'automatisation sur les scénarios multi-requêtes :
- Signaux déclencheurs : `rythme_soutenu` (6-21 p/s), `aucune_interaction`, `pages_eclair` (<500ms/page)
- Efficace uniquement quand le moteur fait ≥2 requêtes dans la même session
- Ne bloque pas les scénarios à page unique (8 sur 10)

**F2 (canvas_erreur)** — **aucun impact**.
Aucun moteur ne produit d'erreur canvas : tous pilotent un vrai navigateur avec moteur de rendu fonctionnel.
Empreintes canvas observées : `72b7dff0` (camoufox/Firefox), `123bb3f2` (Chromium/patchright/playwright), `cda43037` (Chrome/scrapling/selenium).

**F8 (CDP/automation)** — **fonctionne mais sans impact additionnel sur les anti-détection**.
- Selenium : 7 globals `cdc_*` détectées → bloqué (mais déjà bloqué par `regles-http`/`navigator.webdriver`)
- Camoufox, scrapling-furtif, patchright : **aucun global exposé** → `automation.cdc/playwright/selenium = false`
- Les moteurs anti-détection cachent efficacement leurs globals CDP

### 8.4 Limites structurelles restantes

1. **80% des scénarios passent** pour les moteurs anti-détection sur les niveaux 03-04 :
   les scénarios à page unique ne génèrent pas de signaux comportementaux exploitables.
2. **Le détecteur comportemental est réactif, pas préventif** : il faut accumuler des données
   de navigation pour détecter un pattern automatisé (minimum 2 pages rapides).
3. **Les moteurs anti-détection cachent tous les signaux JavaScript** que F8 cherche :
   aucune des 6 vérifications CDP (cdc, playwright, selenium, webdriver_patched, callPhantom, canvas)
   ne produit un signal positif sur camoufox ou scrapling-furtif.
4. **Les niveaux 05-06 restent un mur Turnstile** : aucun moteur ne résout le challenge
   (attendu avec test keys toujours valides).

### 8.5 Prochaines pistes

- Détection par **corrélation temporelle intra-session** : même sans interaction, un timing
  régulier entre requêtes (écart-type faible) est un marqueur d'automation.
- **Fingerprinting passif renforcé** : exploiter les différences de hash canvas/WebGL entre sessions
  (un moteur qui produit toujours le même visitorId FingerprintJS est suspect).
- **Détection proactive dès la première page** : honeypot plus agressif, éléments invisibles
  chargés dynamiquement, mesure de jitter réseau.
- **Mode observation sur les niveaux 02-03** : laisser passer mais enregistrer tous les signaux
  de patchright/playwright pour enrichir les heuristiques.
