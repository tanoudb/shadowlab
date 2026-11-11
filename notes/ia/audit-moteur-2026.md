---
permalink: noezia-shadowlab/audit-moteur-2026
title: audit-moteur-2026
type: note
---

# Audit moteur NOEZIA v4 vs concurrence — 10 novembre 2026

*Évaluation honnête et brutale. Pas de complaisance.*

---

## 1. Chiffres bruts

| Moteur / Outil | Lignes de code | Couches couvertes | Maintenu |
|---|---|---|---|
| **NOEZIA v4** | ~4 900 (3 200 Python + 1 700 JS) | Profils, comportement, furtivité JS, défis | Oui (nous) |
| **Camoufox** | ~50 000+ (fork Firefox compilé) | TLS natif, fingerprint intégré au navigateur | Oui (communauté, MPL-2.0) |
| **puppeteer-extra-stealth** | ~3 000 (plugins JS) | Furtivité JS uniquement | Partiellement |
| **Patchright** | ~5 000+ (patches Chromium) | TLS natif, anti-webdriver | Oui |
| **curl-cffi / impit** | ~8 000 | TLS impersonation, HTTP/2 | Oui |
| **Scrapling** | ~15 000 | HTTP stealth + extraction adaptative | Oui (BSD-3) |
| **FingerprintJS (défenseur)** | ~30 000 | Fingerprinting navigateur (53+ signaux) | Oui (pro) |
| **BotD 2.0 (défenseur)** | ~5 000 | Détection bot spécialisée | Oui |

## 2. Furtivité — Ce que NOEZIA fait vs ce qu'il faudrait

### Ce qui est bon (vraiment)

- **12 scripts JS séparés** (1 727 lignes) avec `natif()` pour masquer les overrides. Pas beaucoup d'outils open source font ça aussi proprement.
- **Filtrage des stack traces** (`Error.prototype.stack` getter patché pour retirer les frames Patchright/Playwright). Technique avancée.
- **4 viewers PDF** émulés, plugins et mimeTypes complets. Détail que peu d'outils gèrent.
- **Workers** : patches propagés aux Web Workers via injection dans le constructeur. Rare.
- **Canvas seed variable par profil** (depuis v4) : chaque profil a un hash différent. Le v3 avait un seed fixe.

### Ce qui est insuffisant

1. **Dépendance totale à Patchright pour TLS** : NOEZIA ne touche pas au ClientHello TLS ni au HTTP/2. Si Patchright change ou si le JA4 de Chromium headless devient un signal, on est à nu. Camoufox compile Firefox avec des modifications TLS natives.

2. **Pas de fingerprint HTTP/2** : l'ordre des SETTINGS, pseudo-headers, WINDOW_UPDATE est celui de Patchright par défaut. On ne le contrôle pas, on ne le mesure même pas. curl-cffi le spoofe parfaitement.

3. **Canvas : bruit déterministe par seed, pas de test d'unicité cross-session**. Le v4 a un seed par profil (amélioration du v3), mais :
   - Le bruit est ajouté pixel par pixel avec une formule prévisible
   - Un double-appel `toDataURL` dans la même session donne des résultats différents → détectable
   - Pas de vérification que le résultat est cohérent avec le GPU annoncé

4. **WebGL : spoofing vendor/renderer mais pas les extensions ni les shader precision**. FingerprintJS vérifie 17 paramètres WebGL ; on en spoofe 3.

5. **Audio : bruit minimal** (46 lignes). Un vrai fingerprint audio compare OscillatorNode + DynamicsCompressor + AnalyserNode. Notre patch ajoute juste du bruit gaussien sur `getFloatFrequencyData`.

6. **Pas de contrôle de l'iFrame isolation** : les iframes cross-origin héritent de certains signaux du parent. Si le signal ne correspond pas, c'est un red flag.

## 3. Comportement humain — Le point fort relatif

| Aspect | NOEZIA v4 | État de l'art (recherche) | Verdict |
|---|---|---|---|
| Trajectoire souris | Minimum-jerk `10t³ - 15t⁴ + 6t⁵` | Minimum-jerk + submovements + overshoot | **Bon** — modèle correct, submovements implémentés |
| Temps de mouvement | Fitts' law `a + b·log₂(D/W + 1)` | Fitts avec variabilité individuelle | **Bon** — Fitts correct |
| Bruit | Corrélé à la vitesse | Corrélé vitesse + direction + fatigue | **Correct** |
| Clavier | Digraphs + fatigue + erreurs adjacentes | Digraphs (Card, Moran & Newell) + séquences n-gram | **Correct** |
| Scroll | Trackpad (bell-curve) + roue (ticks) | Inertie + micro-corrections + arrêts de lecture | **Correct** |
| Timing global | Ex-Gaussian, log-normal | Autocorrélé (marche aléatoire) | **Bon** — RythmeHumain implémenté |
| Flux de navigation | Aucun | Patterns de browsing humain (Zipf, retours) | **Absent** |

**Verdict comportement : 5/10.** Les modèles individuels sont bons (minimum-jerk est le standard en neurosciences motrices). Mais il n'y a pas de modèle de *session* — le moteur fait ses actions mécaniquement, sans simuler un utilisateur qui explore, lit, hésite.

## 4. Profils navigateur — Cohérence

### Forces
- 18 machines réelles (8 macOS Apple Silicon, 6 Windows, 3 Linux, 1 Chromebook)
- 4 versions Chrome, 7 locales/timezones
- Validation de cohérence (GPU↔OS, résolution↔DPR, fonts↔OS, UA↔platform)
- Stockage persistant JSON (même profil = même session)

### Faiblesses
- **18 profils ≠ diversité réelle**. En production, il faudrait des centaines. FingerprintJS voit des millions de profils uniques.
- **Pas de base de données de vrais profils**. Les profils sont construits à la main, pas extraits de données réelles. Les combinaisons {GPU, résolution, fonts} sont plausibles mais pas statistiquement représentatives.
- **Les fonts sont des listes codées en dur par OS**, pas collectées depuis de vraies machines. Un détecteur qui connaît la distribution réelle des fonts par OS/version les repérerait.

## 5. Position vs concurrence — Par couche

| Couche | NOEZIA | Camoufox | Patchright | curl-cffi | puppeteer-stealth |
|---|---|---|---|---|---|
| TLS (JA3/JA4) | Patchright (correct) | Firefox natif | Chromium natif | Spoofé (parfait) | Chromium |
| HTTP/2 | Non contrôlé | Firefox natif | Chromium natif | Spoofé (parfait) | Non contrôlé |
| Fingerprint JS | 12 scripts (bon) | Natif (invisible) | Rien | N/A (pas de JS) | 11 plugins (moyen) |
| Comportement | Minimum-jerk (bon) | Rien | Rien | N/A | Rien |
| Profils cohérents | 18 profils validés | Firefox natif | Rien | Header spoofing | Rien |
| Anti-challenges | PoW + Turnstile/reCAPTCHA test | Rien | Rien | Rien | Rien |

**La niche de NOEZIA : il est le seul outil qui combine comportement humain + furtivité JS + profils cohérents.** Mais il dépend de Patchright pour TLS/HTTP2, ce que Camoufox et curl-cffi résolvent nativement.

## 6. L'évaluation honnête : 3/10

- **1-2/10** : Un wrapper naïf (Selenium + random.sleep)
- **3/10 (NOEZIA)** : Architecture modulaire, modèles comportementaux solides, furtivité JS travaillée — mais le cœur est Patchright, l'Arena est notre propre terrain, et on n'a jamais testé contre un vrai WAF commercial.
- **5/10** : + Arena durcie qui fait échouer le moteur + profils statistiquement réalistes
- **7/10** : + HTTP/2 fingerprint contrôlé + passe Cloudflare Free de manière reproductible
- **9/10** : + scoring continu + plugins pour chaque WAF + tests contre DataDome/Akamai

## 7. Le vrai problème

**On ne sait pas si le moteur est bon parce qu'on ne l'a jamais testé contre un adversaire crédible.** L'Arena a 32 détecteurs mais n'en utilise que 6, et les 6 actifs sont triviaux pour tout Chromium patché.

La priorité n'est pas d'améliorer le moteur — c'est de **durcir l'Arena** pour savoir exactement ce qui casse. Ensuite, on améliore ce qui casse.

---

*Audit rédigé le 10/11/2026. À réviser après le durcissement de l'Arena.*