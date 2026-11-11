---
permalink: noezia-shadowlab/audit-arena-2026-1
title: audit-arena-2026
type: note
---

# Audit Arena ShadowLab — 10 novembre 2026

## Constat principal

L'Arena a **32 détecteurs** mais seulement **6 sont consultés pour bloquer** (`gardien.py:REGLES_REQUETE` + `REGLES_JAVASCRIPT`). Les 26 autres collectent des signaux mais **ne servent à rien dans la décision de blocage**. Un moteur qui passe les 6 détecteurs actifs traverse tous les niveaux, quels que soient les résultats des 26 autres.

## Détecteurs actifs dans le gardien (ceux qui bloquent réellement)

| Détecteur | Ce qu'il vérifie | Faiblesse |
|---|---|---|
| `regles-http` | UA outil, HeadlessChrome, Accept-Language, Sec-Fetch-*, cookies | Un Chromium patché (Patchright, Playwright) passe tout ça nativement |
| `tls` | GREASE, ALPN h2, cohérence navigateur/TLS | Tout navigateur Chromium réel a le bon ClientHello. Ne compare pas aux empreintes JA3/JA4 connues |
| `botd` | Verdict BotD 2.0 (FingerprintJS) | BotD détecte webdriver, HeadlessChrome, etc. Patchright les masque déjà |
| `regles-js` | webdriver, HeadlessChrome UA, globales automation (cdc, playwright, selenium) | Les moteurs anti-détection (Patchright, Camoufox, UC) patchent tout ça |
| `coherence` | UA HTTP vs JS, langue HTTP vs JS, platform HTTP vs JS | Important mais facile : suffit de ne pas mentir ou de mentir partout |
| `comportement` | Ressources CSS/JS chargées, rythme, interactions souris/clics | Vérifie qu'il y a des événements souris — pas leur qualité |

**Bilan : ces 6 détecteurs attrapent les outils naïfs** (requests, httpx, Selenium brut). Tout moteur qui utilise un Chromium patché avec des scripts d'injection basiques les passe.

## Détecteurs présents mais NON utilisés pour bloquer

Tous les suivants sont collectés et affichés dans le dashboard mais **ignorés par le gardien** :

- `prototypes` — détecte les patches toString, canvas, webgl, plugins
- `coherence-profonde` — avail vs screen, outer vs inner, hwc puissance de 2, deviceMemory
- `entropie-interaction` — CV des délais souris, trajectoires linéaires, frappe régulière
- `scroll` — deltas uniformes, timing régulier
- `canvas-empreinte` — hash headless connu, canvas+webgl patchés ensemble
- `integrite-proprietes` — .length/.name des fonctions, stack traces, own keys navigator
- `coherence-environnement` — timezone vs locale, screen vs viewport, offset TLS
- `chrome-apis` — chrome.app, chrome.loadTimes, chrome.csi, runtime
- `media-codecs` — canPlayType H.264/AAC, patch détecté
- `langues` — language dans languages, languages gelé, getter natif
- `headless` — hasFocus, visibilityState, webdriver, voices, devices
- `permissions-etendu` — toutes granted ou toutes denied
- `webrtc` — RTCPeerConnection patché, fuites IP
- `stack-trace` — marqueurs patchright/playwright/puppeteer dans les stacks
- `position-fenetre` — screenX/Y à 0, performance.memory patché
- `automation-globals` — globales automation, clés CDC, marqueurs NOEZIA
- `css-media` — hover:none, pointer:none, display-mode
- `prototype-chain` — propriétés propres sur navigator/screen sans prototype
- `timing-precision` — performance.now() surchargé, précision anormale
- `paint-timing` — entrées paint manquantes, first-paint à 0
- `canvas-consistency` — toDataURL vs getImageData déterminisme
- `stack-getter` — Error.prototype.stack getter patché
- `raf-timing` — rAF deltas à 0 ou identiques (pas de vsync)
- `worker-consistency` — hwc/deviceMemory/platform main vs worker
- `connection-dynamic` — NetworkInformation (rtt, downlink)
- `proxy-uadata` — Proxy sur NavigatorUAData (toString, instanceof)
- `enumerable-props` — flags enumerable manquants sur les patches

**Plusieurs de ces détecteurs sont puissants** — `worker-consistency`, `canvas-consistency`, `raf-timing`, `entropie-interaction` attrapent des choses que `regles-js` ne voit pas. Ils sont juste… débranchés.

## Signaux absents (pas de détecteur du tout)

1. **Fingerprint HTTP/2 (SETTINGS, pseudo-header order, WINDOW_UPDATE, priorités)** — prévu dans le design doc, non implémenté. Le frontal TLS relève le JA4 mais pas les settings HTTP/2. Cloudflare et Akamai s'en servent en production.

2. **Canvas uniqueness cross-session** — `canvas-empreinte` compare à des hash connus mais **ne corrèle pas entre sessions**. 10 sessions avec le même hash canvas = bot évident. Besoin d'une table de hash vus.

3. **Audio fingerprint uniqueness** — même problème que canvas. AudioContext.createOscillator + analyser produit un fingerprint ; s'il est identique entre sessions ou incohérent avec le GPU, c'est suspect.

4. **Font enumeration** — le détecteur `coherence-environnement` vérifie timezone/locale mais pas les fonts. Un profil qui annonce macOS avec des fonts Windows est trivial à détecter. Besoin de : lister les fonts disponibles côté JS, comparer avec un référentiel par OS.

5. **Corrélation multi-signaux** — aucun détecteur ne combine les signaux des autres. En production, Cloudflare/DataDome donnent un score composite. Ici, chaque détecteur est indépendant et le gardien ne consulte que 6.

6. **Rate limiting intelligent** — le rate limit actuel est un compteur Nginx par session. Pas de détection de patterns (même pages dans le même ordre, pas de temps de lecture, pas de 404).

## Évaluation du design doc (5 détecteurs prévus)

| Détecteur prévu | Statut | Verdict |
|---|---|---|
| DetecteurEmpreinteCanvas | **Implémenté** (`canvas-empreinte`) mais pas de corrélation cross-session, et **non branché au gardien** | Bon concept, doit être activé + enrichi |
| DetecteurEntropieTiming | **Implémenté** (`entropie-interaction`) — CV des délais, trajectoires, frappe | Bon, mais **non branché au gardien** |
| DetecteurConsistanceProfonde | **Implémenté** (`coherence-profonde`) — screen, DPR, hwc, deviceMemory | Bon, **non branché** |
| DetecteurArtefactsAutomation | **Implémenté** réparti sur `prototypes`, `integrite-proprietes`, `stack-trace`, `stack-getter`, `automation-globals` | Couvert, **non branché** |
| DetecteurHttp2 | **Non implémenté** | Manque réel — le plus différenciant vs vrais WAF |

**Verdict : 4 des 5 sont codés mais non activés. Le 5e (HTTP/2) est le seul vrai manque.**

## Proposition de niveaux Arena révisés

Le problème n'est pas le nombre de détecteurs — c'est que le gardien n'en consulte que 6. La correction prioritaire est d'**activer progressivement les détecteurs existants par niveau**.

### Niveau 01-02 (inchangé)
Baseline + détection HTTP simple. Attrape requests/httpx/curl.

### Niveau 03 — Fingerprinting étendu
Activer dans le gardien : `prototypes`, `coherence-profonde`, `headless`, `chrome-apis`, `langues`, `media-codecs`
→ Attrape Playwright/Selenium bruts (sans stealth).

### Niveau 04 — Intégrité + challenges
Ajouter : `integrite-proprietes`, `stack-trace`, `stack-getter`, `automation-globals`, `css-media`, `prototype-chain`, `enumerable-props`, `proxy-uadata`
→ Détecte les patches mal faits (puppeteer-extra-stealth, Patchright avec scripts naïfs).

### Niveau 05 — Comportement + canvas
Ajouter : `entropie-interaction`, `scroll`, `canvas-empreinte` (avec corrélation cross-session), `canvas-consistency`, `raf-timing`, `worker-consistency`, `paint-timing`, `timing-precision`
→ Détecte les bots avec patches parfaits mais comportement machine.

### Niveau 06 — Corrélation
Ajouter : `connection-dynamic`, `permissions-etendu`, `position-fenetre`, `webrtc`
+ **Score composite** (somme pondérée de tous les détecteurs, seuil configurable)
+ **Corrélation cross-session** (canvas hash, UA, profil identiques)
+ Honeypots + CAPTCHA + rate limit serré

### Niveau 07 (nouveau) — État de l'art
Tout le niveau 06 + **détecteur HTTP/2** + **fonts** + **audio fingerprint**
+ WAF paranoia 4, seuil 2
→ Le moteur doit avoir une empreinte TLS/HTTP2 cohérente, des fonts réalistes, un audio fingerprint unique, un comportement humain crédible et ne déclencher aucun signal d'intégrité.

## Actions prioritaires (par impact)

1. **Brancher les détecteurs existants au gardien** — ~50 lignes à modifier dans `gardien.py` + `profils.yaml`. Impact immédiat : le moteur NOEZIA va probablement échouer à partir du niveau 03-04 révisé.
2. **Corrélation canvas cross-session** — table de hash, compteur. ~100 lignes.
3. **Score composite** — somme pondérée de tous les détecteurs actifs au lieu de la logique binaire actuelle. ~150 lignes.
4. **Détecteur HTTP/2** — nécessite que le frontal TLS relève les SETTINGS HTTP/2 (modifications dans `arena/tls.py` + `arena/frontal.py`). ~300 lignes.
5. **Collecte fonts côté JS** — nouveau script dans l'observateur. ~100 lignes JS + détecteur Python.