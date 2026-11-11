# Synthèse du brainstorming — 10 novembre 2026

**Refonte complète du moteur NOEZIA et durcissement de l'Arena ShadowLab**

4 documents produits par 3 agents en parallèle + 1 audit préalable :
- `notes/ia/audit-arena-2026.md` — Audit des 32 détecteurs et du gardien
- `2026-11-10-brainstorm-moteur.md` — Refonte du moteur (architecture, techniques, feuille de route)
- `2026-11-10-brainstorm-arena.md` — Durcissement de l'Arena (détecteurs, score composite, niveaux)
- `2026-11-10-brainstorm-etat-art.md` — État de l'art anti-bot 2024-2026

---

## Diagnostic unanime

Les 3 agents convergent sur le même diagnostic :

1. **Le moteur est un wrapper** — Patchright fait le gros du travail, NOEZIA orchestre. La valeur ajoutée propre (comportement humain minimum-jerk, profils OS-cohérents) est réelle mais insuffisante.

2. **L'Arena est un adversaire fantoche** — 26 détecteurs sur 32 ne bloquent pas. Le moteur passe tous les niveaux mais ce n'est pas un accomplissement.

3. **Le problème n°1 est l'empreinte TLS/HTTP2** — C'est le signal le plus discriminant en production (Cloudflare, Akamai, DataDome l'utilisent). NOEZIA n'a aucun contrôle dessus.

4. **Jamais testé contre la réalité** — Aucune campagne contre Cloudflare Free, DataDome, ou PerimeterX. Sans confrontation réelle, impossible de savoir où on en est.

## Convergence sur la stratégie

### Étape 0 : Durcir l'Arena (prérequis absolu)
- Brancher les 26 détecteurs débranchés au gardien
- Logique score composite (somme pondérée) au lieu de binaire
- 7 niveaux au lieu de 6 (niveau 07 = état de l'art)
- **Critère** : le moteur NOEZIA actuel échoue aux niveaux 04+
- **Estimation** : ~400-600 lignes

### Étape 1 : Profils réalistes (base de données statistique)
- Passer de 18 profils codés à main à des centaines issus de vraies distributions
- Intégrer ou reproduire BrowserForge (base de fingerprints réels)
- **Estimation** : ~500 lignes

### Étape 2 : Transport HTTP/2 furtif
- Utiliser curl-cffi pour les requêtes HTTP (empreinte TLS/HTTP2 cohérente)
- Double couche : navigateur (Patchright) + HTTP pur (curl-cffi) selon le besoin
- **Estimation** : ~400 lignes

### Étape 3 : Fingerprint canvas/WebGL/audio cohérents
- Canvas corrélé au GPU réel (pas du bruit aléatoire)
- WebGL profond (37+ paramètres cohérents)
- Audio fingerprint complet
- **Estimation** : ~850 lignes

### Étape 4 : Modèle de session et comportement avancé
- Parcours de navigation réalistes (pas toujours les mêmes pages)
- Micro-hésitations, scroll avec inertie, patterns de lecture
- Interaction formulaires naturelle
- **Estimation** : ~1100 lignes

### Étape 5 : Worker/timing/WebRTC
- Cohérence main thread ↔ worker (hwConcurrency, deviceMemory, platform)
- Naturalisation des timings rAF (vsync réaliste)
- Contrôle WebRTC (pas de fuite IP)
- **Estimation** : ~470 lignes

### Étape 6 : Validation contre protections réelles
- Cloudflare Free (premier test de vérité)
- DataDome (si possible en bug bounty ou test autorisé)
- Campagnes reproductibles avec intervalles de confiance
- **Estimation** : ~600 lignes (plugins WAF + harness)

### Étape 7 : Pool et scaling
- Multi-sessions avec rotation de profils
- Gestion de la pression (adapter le rythme selon les signaux)
- **Estimation** : ~500 lignes

**Total estimé : ~4 800 lignes** (doublerait le code actuel)

## Avantage compétitif identifié

Le brainstorming moteur identifie un créneau que personne n'occupe : **le comportement humain calibré sur les neurosciences motrices**. Les outils existants font du bruit aléatoire ou du minimum-jerk basique. Un modèle de mouvement humain réaliste (loi de Fitts, micro-corrections, fatigue, hésitation) serait un vrai différenciateur.

## Questions ouvertes pour Ethan

1. **BrowserForge** : utiliser sa base de fingerprints (licence MIT) ou reconstruire la nôtre ?
2. **Site de test Cloudflare** : quel site pour la première campagne réelle ?
3. **Couche IA** : quand ? (le brainstorming dit "après l'étape 6, pas avant")
4. **Priorité moteur vs Arena** : l'Arena d'abord (consensuel entre les 3 agents) ou en parallèle ?
5. **Contribution open source** : publier le moteur à terme ou le garder propriétaire ?

## Signaux d'alerte de l'état de l'art

- **JA3 est mort** (déprécié mai 2025) — JA4 est le standard, Cloudflare l'utilise
- **puppeteer-extra-stealth est abandonné** — ne plus s'en inspirer
- **nodriver score le mieux sur Cloudflare** (28/31 benchmarks) — à étudier
- **L'IA détecte les bots** — FingerprintJS a lancé un détecteur d'agents IA (juin 2026)
- **Privacy Sandbox abandonné** — favorable au scraping (le fingerprinting reste possible)
- **Attestation matérielle** — risque à moyen terme (Play Integrity Desktop rumeuré)
