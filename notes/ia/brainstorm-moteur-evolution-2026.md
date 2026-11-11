---
permalink: noezia-shadowlab/brainstorm-moteur-evolution-2026
title: brainstorm-moteur-evolution-2026
type: note
---

# Feuille de route moteur NOEZIA — de 3/10 à 6/10

*10 novembre 2026. Améliorations classées par impact réel, pas par facilité.*

---

## Principe directeur

**Durcir l'Arena d'abord, améliorer le moteur ensuite.** Chaque amélioration du moteur doit être mesurée par : "quel détecteur Arena (durcie) passe maintenant ?" Si on ne peut pas répondre, l'amélioration est cosmétique.

---

## Amélioration 1 — Canvas déterministe et cohérent (Taille : M)

### Problème
Le canvas est bruité par seed, mais :
- Deux appels `toDataURL` dans la même session donnent des résultats différents (le bruit est ajouté à chaque appel) → `canvas-consistency` le détecte
- Le hash n'est pas vérifié contre le GPU annoncé → `canvas-empreinte` pourrait le détecter avec une table de référence
- WebGL a le même problème (bruit sans cohérence GPU)

### Solution
1. **Canvas** : calculer le bruit UNE FOIS au chargement (seed + profil), l'appliquer de manière déterministe sur chaque pixel. Deux appels dans la même session = même résultat. Sessions différentes = résultats différents (seed différent).
2. **WebGL** : mapper les extensions et shader precisions au GPU annoncé. Actuellement on spoofe vendor/renderer mais pas les 14 autres paramètres que FingerprintJS vérifie.

### Fichiers
- `src/shadowlab/engines/noezia/furtivite/canvas.js` — Refonte du mécanisme de bruit
- `src/shadowlab/engines/noezia/furtivite/webgl.js` — Ajouter extensions, shader, unmasked params
- `src/shadowlab/engines/noezia/profils/generateur.py` — Table GPU → paramètres WebGL attendus

### Mesure
- `canvas-consistency` : le double appel donne le même résultat ✓
- `canvas-empreinte` : hash unique par profil, plausible pour le GPU ✓

### Effort : ~3 jours
### Dépendances : Arena itération 1 (activer les détecteurs) pour pouvoir mesurer

---

## Amélioration 2 — Intégrité des patches JS (Taille : M)

### Problème
Les 12 scripts de furtivité utilisent `natif()` pour masquer `toString()`, mais :
- `Object.getOwnPropertyDescriptor()` sur les propriétés patchées révèle des getters JS au lieu de getters C++ natifs
- La longueur, le nom, et le prototype des fonctions patchées ne correspondent pas toujours à l'original
- Les propriétés `enumerable` sont parfois incorrectes après patch

### Solution
1. **Vérification systématique** : pour chaque propriété patchée, vérifier que `getOwnPropertyDescriptor` retourne la même chose que l'original (configurable, enumerable, writable)
2. **Suppression des prototypes** : les getters natifs n'ont pas de `.prototype`. Le `natif()` actuel fait `delete fn.prototype` — vérifier que c'est fait partout.
3. **Proxy-based patching** : pour les objets complexes (NavigatorUAData), utiliser des Proxy ES6 au lieu de `defineProperty`. Plus invisible, mais plus complexe.

### Fichiers
- `src/shadowlab/engines/noezia/furtivite/navigateur.js` — Audit et correction de chaque patch
- `src/shadowlab/engines/noezia/furtivite/environnement.js` — Idem
- `src/shadowlab/engines/noezia/furtivite/headless.js` — Idem
- Potentiellement tous les 12 scripts

### Mesure
- `integrite-proprietes` : 0 signal ✓
- `enumerable-props` : 0 signal ✓
- `prototype-chain` : 0 signal ✓
- `proxy-uadata` : 0 signal ✓

### Effort : ~4 jours (audit minutieux de chaque patch)
### Dépendances : Arena itération 1

---

## Amélioration 3 — Workers et iframes cohérents (Taille : S)

### Problème
- `worker-consistency` vérifie que `hardwareConcurrency`, `deviceMemory`, `platform` sont identiques entre le main thread et les Web Workers
- Nos patches sont propagés aux Workers (`workers.js`), mais la propagation doit être vérifiée
- Les iframes cross-origin ne sont PAS patchées (correct pour les widgets CAPTCHA, mais l'Arena pourrait tester avec ses propres iframes)

### Solution
1. Vérifier que TOUTES les propriétés patchées dans le main thread sont identiques dans les Workers
2. Ajouter un test spécifique : créer un Worker, lui faire lire navigator.*, comparer avec le main

### Fichiers
- `src/shadowlab/engines/noezia/furtivite/workers.js` — Audit + compléter si manquant
- Nouveau test unitaire : spawn worker, vérifier cohérence

### Mesure : `worker-consistency` : 0 signal ✓
### Effort : ~1 jour
### Dépendances : Aucune

---

## Amélioration 4 — Comportement de session (Taille : L)

### Problème
Le moteur simule bien les gestes individuels (souris minimum-jerk, clavier digraph), mais il n'y a PAS de modèle de session. Un vrai humain :
- Arrive, lit le contenu, scroll, clique des liens
- Passe du temps proportionnel à la quantité de texte
- N'accède pas à 20 pages en 10 secondes
- Revient parfois en arrière, hésite, fait des erreurs de navigation

Le détecteur `scroll` vérifie les deltas et le timing. Le détecteur `entropie-interaction` vérifie le CV des délais et l'autocorrélation. Un moteur qui fait page1→page2→page3→page4 avec des pauses fixes est trivial à détecter.

### Solution
1. **Modèle de session** : nouveau module `comportement/session.py` qui planifie un flux de navigation réaliste
   - Temps de lecture proportionnel au contenu (compter les mots, appliquer ~250 WPM humain)
   - Scroll progressif avec pauses aux sections
   - Probabilité de retour arrière (~10%)
   - Variabilité inter-session (pas toujours le même chemin)

2. **Améliorer scroll** : le scroll actuel est bon (trackpad bell-curve + roue ticks) mais ne simule pas un humain qui lit : scroll → pause → scroll → pause.

### Fichiers
- `src/shadowlab/engines/noezia/comportement/session.py` — Nouveau (~200 lignes)
- `src/shadowlab/engines/noezia/moteur.py` — Intégrer le modèle de session dans `naviguer()`

### Mesure
- `entropie-interaction` : entropie des intervalles dans la plage humaine ✓
- `scroll` : pattern de scroll réaliste ✓
- `comportement` : ressources chargées, rythme crédible ✓

### Effort : ~4 jours
### Dépendances : Arena itération 1

---

## Amélioration 5 — Diversité des profils (Taille : M)

### Problème
18 profils codés à la main. En production, FingerprintJS voit des millions de profils uniques. Avec la corrélation cross-session (Arena itération 2), 18 profils sont détectables rapidement.

### Solution
1. **Générateur procédural** : au lieu de 18 machines hardcodées, définir des *distributions* :
   - Distribution des résolutions par OS (données publiques de StatCounter)
   - Distribution des GPU par OS (données WebGL Report)
   - Distribution des versions Chrome (données ChromeStatus)
   - Générer un profil cohérent en tirant dans ces distributions

2. **Base de fonts par OS/version** : collecter les fonts réelles d'une VM macOS, Windows, Linux. Stocker dans `configs/profils/fonts/`.

### Fichiers
- `src/shadowlab/engines/noezia/profils/generateur.py` — Refonte vers génération procédurale
- `configs/profils/distributions/` — Données de distribution (JSON)
- `configs/profils/fonts/` — Listes de fonts par OS/version

### Mesure : `DetecteurCorrelation` ne détecte plus de profils répétés ✓
### Effort : ~3 jours
### Dépendances : Arena itération 2 (corrélation cross-session)

---

## Résumé priorisé

| # | Amélioration | Effort | De → À | Condition de succès |
|---|---|---|---|---|
| 1 | Canvas déterministe + WebGL complet | 3j | Passer `canvas-consistency`, `canvas-empreinte` | Double appel identique + hash plausible GPU |
| 2 | Intégrité des patches JS | 4j | Passer `integrite-proprietes`, `prototype-chain`, `enumerable-props` | 0 signal sur les 4 détecteurs d'intégrité |
| 3 | Workers cohérents | 1j | Passer `worker-consistency` | Main = Worker sur toutes les propriétés |
| 4 | Comportement de session | 4j | Passer `entropie-interaction`, `scroll` | Entropie des intervalles dans plage humaine |
| 5 | Diversité des profils | 3j | Résister à la corrélation cross-session | 100 profils uniques, distribution réaliste |

**Total moteur : ~15 jours. Avec l'Arena : ~25 jours au total pour passer de 3/10 à ~5-6/10.**

Le 7/10 (passer Cloudflare Free de manière reproductible) demande en plus le contrôle HTTP/2 — ce qui est un projet en soi, dépendant de Patchright ou d'un proxy TLS.