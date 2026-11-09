# NOEZIA v4 — Moteur anti-détection modulaire + Arena durcie

## Intention

Le moteur NOEZIA v3 est un wrapper de 464 lignes autour de Patchright avec un blob JS
inline. Il passe l'Arena parce que l'Arena est faible — pas parce qu'il est bon.

L'objectif : un moteur modulaire dont chaque couche est une contribution technique réelle,
et une Arena dont les niveaux supérieurs reflètent l'état de l'art des protections anti-bot
en production (Cloudflare, Akamai, DataDome, PerimeterX).

## Objectifs

- Moteur modulaire ≥ 3 000 lignes de code substantif (pas de padding)
- Architecture en plugins enfichables
- Profils navigateur persistants et cohérents
- Comportement humain basé sur des modèles de contrôle moteur (pas random.uniform)
- Scripts stealth séparés, paramétrables par profil
- Arena avec ≥ 10 détecteurs dont : HTTP/2 fingerprint, canvas uniqueness,
  timing entropy, navigator deep consistency, automation artifacts

## Non-objectifs

- Pas de proxy réel ni réseau sortant (périmètre local seulement)
- Pas de solveur CAPTCHA (D-16)
- Pas de contournement ciblant un service commercial spécifique

## Anti-objectifs (ce qui serait un échec même si ça "marche")

- Un moteur qui passe l'Arena mais qu'un vrai Cloudflare écraserait
- Du code qui gonfle les lignes sans substance technique
- Des détecteurs Arena qu'on construit pour que notre moteur les passe

## Problèmes du v3

1. **Bruit canvas déterministe** : SEED fixe → chaque session a le même hash canvas.
   Un détecteur qui voit le même hash 10 fois sait que c'est un bot.
2. **Bezier trop lisse** : courbe quadratique avec bruit gaussien ε=0.5px.
   Le vrai mouvement humain a des submovements, de l'overshoot, une décélération
   non-linéaire. Un détecteur d'entropie des intervalles le repère.
3. **Timing uniforme** : `random.uniform(0.004, 0.014)` entre chaque point souris.
   Les humains ont des phases d'accélération/décélération corrélées à la distance.
4. **Monolithique** : 1 fichier, 1 gros script JS, aucune séparation des concerns.
5. **Profil unique** : toujours le même UA, le même GPU (M5 Pro), la même locale.
   Un vrai outil a des profils variés et cohérents.
6. **Pas de HTTP/2 fingerprint** : le ClientHello TLS est celui de Chromium
   (correct), mais rien ne gère les settings HTTP/2 ni l'ordre HPACK.

## Architecture moteur

```
src/shadowlab/engines/noezia/
├── __init__.py              # Export DriverNoezia
├── moteur.py                # Orchestrateur (hérite de Driver)
├── config.py                # Configuration typée du moteur
│
├── profils/
│   ├── __init__.py
│   ├── generateur.py        # Génération de profils réalistes
│   ├── coherence.py         # Validation de cohérence inter-propriétés
│   └── stockage.py          # Persistance JSON des profils
│
├── comportement/
│   ├── __init__.py
│   ├── souris.py            # Modèle minimum-jerk + Fitts' law
│   ├── clavier.py           # Frappe gaussienne avec fatigue et erreurs
│   ├── defilement.py        # Scroll inertiel avec phases
│   └── tempo.py             # Rythme humain (lecture, réflexion, action)
│
├── furtivite/
│   ├── __init__.py
│   ├── patches.py           # Coordination des scripts JS
│   ├── navigateur.js        # Navigator, plugins, permissions
│   ├── canvas.js            # Canvas noise par profil (seed variable)
│   ├── webgl.js             # WebGL vendor/renderer par profil
│   ├── audio.js             # AudioContext noise
│   └── divers.js            # window.chrome, toString, userAgentData
│
├── defis/
│   ├── __init__.py
│   ├── pow.py               # Proof-of-work solver
│   ├── turnstile.py         # Turnstile handler
│   └── recaptcha.py         # reCAPTCHA handler (test keys)
│
└── plugins/
    ├── __init__.py
    ├── base.py              # Interface Plugin
    └── registre.py          # Découverte et chargement
```

## Architecture Arena durcie

Nouveaux détecteurs (ajoutés à detection.py ou en modules séparés) :

### 1. DetecteurEmpreinteCanvas (nouveau)
- Calcule le hash canvas côté serveur à partir de la collecte JS
- Vérifie l'unicité : un hash vu plus de N fois sur des sessions différentes → bot
- Vérifie la cohérence : le hash doit être plausible pour le GPU annoncé
- Détecte le bruit trop régulier (entropie des différences pixel-à-pixel)

### 2. DetecteurEntropieTiming (nouveau)
- Analyse les intervalles entre événements souris (collectés par l'observateur)
- Calcule l'entropie de Shannon des deltas
- Détecte les courbes de Bezier (autocorrélation des vitesses)
- Vérifie la loi de Fitts (temps vs distance vs taille cible)

### 3. DetecteurConsistanceProfonde (nouveau, renforce coherence)
- screen.width/height vs viewport vs CSS media queries
- devicePixelRatio cohérent avec l'appareil annoncé
- hardwareConcurrency vs performance.now() résolution
- Timezone vs locale vs Accept-Language vs navigator.language
- Fonts disponibles vs OS annoncé

### 4. DetecteurArtefactsAutomation (nouveau, renforce regles-js)
- Analyse Error.stack pour des frames CDP ou Playwright
- Vérifie l'intégrité de la chaîne de prototypes (Object.getOwnPropertyDescriptor)
- Détecte les getters installés par des scripts d'injection
- Vérifie que les méthodes natives n'ont pas été wrappées

### 5. DetecteurHttp2 (nouveau)
- Analyse les SETTINGS HTTP/2 (HEADER_TABLE_SIZE, MAX_CONCURRENT_STREAMS, etc.)
- Ordre des pseudo-headers (:method, :authority, :scheme, :path)
- WINDOW_UPDATE et priorités
- Comparaison avec les profils connus (Chrome, Firefox, Safari, curl, Go)

## Modèle de mouvement souris

Remplace la Bezier quadratique par un modèle à minimum-jerk :

```
x(t) = x0 + (xf - x0) * (10t³ - 15t⁴ + 6t⁵)
```

Avec :
- Temps de mouvement selon Fitts : MT = a + b * log₂(D/W + 1)
- Sous-mouvements correctifs (2-3 ajustements fins à l'approche)
- Overshoot occasionnel (8-15% des mouvements longs)
- Bruit corrélé à la vitesse (plus de bruit à haute vitesse)
- Pauses de décision entre les mouvements (50-300ms, distribution log-normale)

## Profils navigateur

Chaque profil est un ensemble cohérent :
- OS + version (macOS 14.x, Windows 11, Ubuntu 24.04)
- Navigateur + version (Chrome 131, Firefox 133)
- GPU (vendor + renderer cohérents avec l'OS)
- Résolution d'écran (parmi les courantes pour cet OS)
- Locale + timezone (cohérents)
- Fonts (ensemble réaliste pour cet OS)
- Canvas seed (unique par profil, persistant)
- User-Agent (construit à partir des composants ci-dessus)

Base de données : `configs/profils/` avec des templates par OS/navigateur.

## Plan d'exécution

### Phase 1 : Structure + profils (~800 lignes)
- Créer le package noezia/ avec tous les modules
- Système de profils avec générateur et validation de cohérence
- Migration depuis le v3 (même interface Driver)

### Phase 2 : Comportement humain (~600 lignes)
- Modèle minimum-jerk pour la souris
- Frappe avec fatigue et micro-erreurs
- Scroll inertiel
- Tempo adaptatif (lecture de la page)

### Phase 3 : Furtivité (~800 lignes)
- Scripts JS séparés et paramétrables
- Canvas noise par profil (seed variable)
- WebGL par profil
- Détection et évitement des honeypots amélioré

### Phase 4 : Arena durcie (~600 lignes)
- 4-5 nouveaux détecteurs
- Collecte enrichie côté client (timing events, canvas hash)
- Niveaux 05-06 renforcés, niveau 07 optionnel

### Phase 5 : Validation
- Tests unitaires pour chaque module
- Campagne complète : le v4 vs l'Arena durcie
- Résultats honnêtes (le moteur ne DOIT PAS passer tous les niveaux au début)
