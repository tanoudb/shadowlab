# Brainstorming — Refonte du moteur NOEZIA vers un moteur de référence mondiale

*10 novembre 2026. Document de réflexion. Pas encore un plan d'exécution — c'est le
matériau brut pour en construire un.*

---

## Situation actuelle

**4 915 lignes** (3 200 Python + 1 715 JS), réparties en 6 packages : profils (464 lignes),
comportement (souris/clavier/scroll/tempo/humain, ~750 lignes), furtivité (12 scripts JS,
1 715 lignes), défis (PoW/Turnstile/reCAPTCHA, ~200 lignes), extraction (analyseur/signatures),
pool (non-commencé). Évaluation honnête : **3/10**.

Le moteur passe les 6 niveaux de l'Arena, mais l'Arena n'utilise que 6 de ses 32 détecteurs,
et ces 6 sont triviaux pour tout Chromium patché. Contre un vrai Cloudflare Bot Management
ou DataDome, le moteur serait probablement détecté en 2-3 requêtes.

**Forces actuelles** : modèle comportemental solide (minimum-jerk, Fitts, digraphes clavier),
profils cohérents (18 machines, GPU↔OS↔fonts validés), 12 scripts JS de furtivité avec
`natif()` pour masquer les overrides, propagation aux Workers.

**Faiblesses critiques** (par ordre de gravité) :
1. Aucun contrôle de l'empreinte TLS/HTTP2 (délégué à Patchright)
2. Canvas/WebGL/Audio : bruit simple, pas de cohérence avec le GPU réel
3. 18 profils ≠ diversité réelle (il en faut des centaines)
4. Pas de modèle de session (le moteur fait des actions, pas un parcours)
5. Jamais testé contre un adversaire réel

---

## 1. Architecture cible

### 1.1 Le choix du navigateur : rester sur Patchright ou migrer ?

**Options évaluées :**

| Option | Avantages | Inconvénients |
|--------|-----------|---------------|
| **Patchright (actuel)** | API Playwright complète, TLS Chrome natif, bonne base | Aucun contrôle HTTP/2, patches limités au runtime JS |
| **Camoufox (fork Firefox)** | Stealth compilé dans le navigateur, invisible au JS, fingerprint natif | API limitée (playwright<1.63), TLS Firefox détectable par certains CDN, AGPL-3.0 |
| **Navigateur custom (Chromium compilé)** | Contrôle total : TLS, HTTP/2, fingerprint natif, CDP nettoyé | Monstrueux à maintenir (suivre les releases Chromium), 6-12 mois de travail initial |
| **Multi-backend** | Chromium (Patchright) pour le web mainstream, curl-cffi pour le HTTP pur, Camoufox en fallback Firefox | Complexité d'orchestration, profils à maintenir par backend |

**Recommandation : Patchright en pilier principal + curl-cffi en couche HTTP/2.**

Justification :
- Un navigateur custom est irréaliste pour un développeur solo/petite équipe. Chromium sort une
  release toutes les 4 semaines — le travail de suivi dévorerait tout le reste.
- Camoufox est tentant mais l'empreinte TLS Firefox est un signal en soi sur les sites qui
  s'attendent à du Chrome (parts de marché : Chrome 65%, Firefox 3%). Et l'AGPL-3.0 pose un
  problème si le moteur devient un produit commercial.
- curl-cffi peut spoofer parfaitement le JA4 et les SETTINGS HTTP/2 de n'importe quel navigateur
  pour les requêtes purement HTTP. En l'utilisant comme couche transport pour les pré-vérifications
  et les requêtes API, on résout le problème HTTP/2 sans toucher au navigateur.

**Architecture proposée :**

```
DriverNoezia
├── TransportHTTP (curl-cffi ou httpx)
│   ├── Empreinte TLS (JA4 Chrome)
│   ├── Empreinte HTTP/2 (SETTINGS/pseudo-headers Chrome)
│   └── Headers cohérents avec le profil
├── NavigateurFurtif (Patchright)
│   ├── Contexte avec profil injecté
│   ├── Scripts de furtivité (avant tout JS)
│   └── Comportement humain (souris/clavier/scroll)
├── ProfilNavigateur
│   ├── Générateur (machines réelles, statistiquement représentatif)
│   ├── Cohérence (GPU↔OS↔fonts↔locale↔TLS↔HTTP2)
│   └── Stockage persistant
├── SessionManager
│   ├── Modèle de parcours (pas juste des actions)
│   ├── Gestion cookies/état
│   └── Rotation de profils
└── PluginRegistry
    ├── Plugin par WAF/détecteur (Cloudflare, DataDome, Akamai)
    └── Pipeline de résolution de défis
```

### 1.2 Comment gérer l'empreinte TLS/HTTP2

C'est le problème n°1. Trois approches possibles :

**A. curl-cffi pour le HTTP/2 pré-navigateur** (recommandé pour la phase 1)

curl-cffi impersonne parfaitement le ClientHello TLS et les SETTINGS HTTP/2 de Chrome/Firefox/Safari.
L'idée : utiliser curl-cffi pour les requêtes qui n'ont pas besoin de JS (API, HEAD, pré-vol CORS,
healthchecks) et Patchright pour les pages avec rendu JS. Cela résout 60-70% du problème HTTP/2
sans modifier le navigateur.

```python
class TransportHTTP:
    """Transport HTTP furtif basé sur curl-cffi."""
    def __init__(self, profil: ProfilNavigateur):
        # Impersonation Chrome/Firefox selon le profil
        self._session = curl_cffi.requests.Session(
            impersonate=f"chrome{profil.chrome_major}",
        )
        # Headers cohérents avec le profil
        self._session.headers.update({
            "user-agent": profil.user_agent,
            "sec-ch-ua": profil.sec_ch_ua,
            "accept-language": profil.accept_language,
        })
```

Limitation : pour les pages nécessitant du JS, on revient à Patchright dont on ne contrôle pas le
HTTP/2. Mais Patchright utilise le Chromium réel → son HTTP/2 est celui de Chrome. Le problème
n'apparaît que si un WAF corrèle le JA4 + HTTP/2 + UA et détecte une incohérence entre les requêtes
curl-cffi et les requêtes navigateur. Solution : utiliser curl-cffi **uniquement** en pre-flight,
jamais en navigation concurrente avec le navigateur.

**B. Proxy man-in-the-middle avec contrôle TLS** (phase 2, avancé)

Un proxy local (mitmproxy, custom Go) qui intercepte les connexions du navigateur et réécrit les
SETTINGS HTTP/2 et l'ordre des pseudo-headers avant de les envoyer au serveur. Le ClientHello TLS
du navigateur est conservé (il est déjà correct), mais les frames HTTP/2 sont normalisées.

Complexité : élevée (gestion TLS double, latence ajoutée, certificats). Mais c'est ce que font les
services commerciaux (Bright Data, Oxylabs) en interne.

**C. CDP pour forcer les SETTINGS** (exploratoire)

Chrome expose `Network.enable` et certains paramètres via CDP. Explorer si on peut modifier les
SETTINGS HTTP/2 via le protocole DevTools. Patchright pourrait être étendu pour ça. Probabilité
de succès : faible (les SETTINGS sont gérés au niveau nghttp2 dans Chromium, pas au niveau CDP).

### 1.3 Architecture modulaire détaillée

**Principe : chaque composant est testable et remplaçable indépendamment.**

```
src/shadowlab/engines/noezia/
├── __init__.py
├── moteur.py                # Orchestrateur (800 lignes max)
├── config.py                # Dataclasses de config typées
│
├── transport/               # NOUVEAU — couche HTTP furtive
│   ├── __init__.py
│   ├── impersonation.py     # curl-cffi, profils TLS/HTTP2
│   ├── cookies.py           # Jar partagé navigateur ↔ HTTP
│   └── headers.py           # Cohérence headers × profil
│
├── profils/
│   ├── __init__.py
│   ├── generateur.py        # Génération statistique
│   ├── coherence.py         # Validation inter-signaux
│   ├── stockage.py          # JSON persistant
│   ├── base_reelle.py       # NOUVEAU — BDD de vrais profils collectés
│   └── enrichissement.py    # NOUVEAU — complétion d'un profil partiel
│
├── comportement/
│   ├── __init__.py
│   ├── humain.py            # Distributions calibrées (existant)
│   ├── souris.py            # Minimum-jerk + Fitts (existant)
│   ├── clavier.py           # Digraphes + fatigue (existant)
│   ├── defilement.py        # Trackpad/molette (existant)
│   ├── tempo.py             # Pauses calibrées (existant)
│   ├── session.py           # NOUVEAU — modèle de parcours
│   └── formulaires.py       # NOUVEAU — remplissage réaliste
│
├── furtivite/
│   ├── __init__.py
│   ├── patches.py           # Orchestration (existant)
│   ├── navigateur.js        # (existant, à enrichir)
│   ├── canvas.js            # (existant, à réécrire)
│   ├── webgl.js             # (existant, à enrichir)
│   ├── audio.js             # (existant, à réécrire)
│   ├── fonts.js             # (existant polices.js, à renommer)
│   ├── workers.js           # (existant)
│   ├── timing.js            # NOUVEAU — rAF/setTimeout naturalisation
│   ├── webrtc.js            # NOUVEAU — fingerprint WebRTC contrôlé
│   └── ...                  # (autres existants)
│
├── defis/                   # (existant)
│
├── plugins/                 # NOUVEAU — extensibilité par WAF
│   ├── __init__.py
│   ├── base.py              # Interface Plugin
│   ├── registre.py          # Découverte et chargement
│   ├── cloudflare.py        # Spécialisations Cloudflare
│   └── datadome.py          # Spécialisations DataDome
│
└── pool/                    # NOUVEAU — gestion multi-sessions
    ├── __init__.py
    ├── pool.py              # Pool de navigateurs
    ├── rotation.py          # Rotation de profils
    └── limites.py           # Rate limiting intelligent
```

---

## 2. Techniques manquantes (par priorité)

### 2.1 Canvas fingerprint — cohérent, pas juste bruité (PRIORITÉ 1)

**Problème actuel :** Le canvas.js ajoute du bruit xorshift sur 30% des pixels (±1-2 sur un canal).
C'est mieux qu'un seed fixe, mais :
- Un double-appel `toDataURL` dans la même session avec le **même contenu** canvas donne le même
  résultat (bien), mais un détecteur qui dessine deux scènes différentes puis compare la corrélation
  du bruit entre les deux verra un pattern déterministe → détectable.
- Le bruit n'est pas cohérent avec le GPU annoncé. Un vrai GPU Apple Metal produit un rendu
  légèrement différent d'un NVIDIA D3D11 à cause des différences de pipeline (arrondi flottant,
  gamma, anti-aliasing). Notre bruit est uniforme quel que soit le GPU du profil.

**Solution :**
1. **Bruit GPU-corrélé** : différentes stratégies de bruit selon le GPU annoncé. Apple Metal a
   un arrondi half-float dans le fragment shader → les pixels à basse luminosité sont affectés
   différemment. D3D11 a un dithering spécifique. Le bruit doit mimer ces patterns.
2. **Hash stable intra-session** : le hash doit être identique pour la même scène canvas dessinée
   deux fois. Actuellement c'est le cas (xorshift avec seed fixe), mais il faut aussi que le
   bruit varie si la scène change → le seed doit dépendre du contenu.
3. **Collecte de vrais hash** : construire une base de vrais hash canvas par GPU/OS/Chrome version.
   Au lieu d'ajouter du bruit, on pourrait **remplacer** le hash par un vrai hash de la base,
   correspondant au profil. C'est ce que fait BrowserForge.

**Estimation : ~400 lignes** (réécriture canvas.js + base de hash + tests).

### 2.2 HTTP/2 fingerprint (PRIORITÉ 1)

**Problème actuel :** Aucun contrôle. L'empreinte HTTP/2 est celle de Patchright/Chromium par
défaut. Les SETTINGS, l'ordre des pseudo-headers, le WINDOW_UPDATE initial ne sont ni mesurés ni
configurables.

**Solution :**
1. **Phase 1** : curl-cffi comme transport HTTP alternatif (voir section 1.2A). ~300 lignes Python.
2. **Phase 2** : proxy local qui normalise les frames HTTP/2 du navigateur. ~800 lignes.
3. **Arena** : détecteur HTTP/2 côté serveur (capturer les frames avec un middleware Python ou un
   frontal Go). ~300 lignes.

**Estimation transport : ~300 lignes.** Détecteur Arena : ~300 lignes supplémentaires.

### 2.3 WebGL fingerprint profond (PRIORITÉ 2)

**Problème actuel :** Le webgl.js spoofe vendor/renderer et ~15 paramètres `getParameter`, plus
`getShaderPrecisionFormat` et `readPixels`. C'est bien, mais :
- Les paramètres WebGL2 sont partiellement couverts
- `getUniformLocation` / `getAttribLocation` côté shader ne sont pas spoofés
- Le hash de rendu WebGL (dessiner une scène + readPixels) n'est pas cohérent avec le GPU
- Les WebGL extensions ne varient pas par profil (toujours la même liste de 28)

**Solution :**
1. **Extensions par GPU** : chaque famille GPU a un sous-ensemble d'extensions. Apple Metal
   supporte des extensions différentes de D3D11. La liste doit varier par profil.
2. **Paramètres WebGL2 complets** : `MAX_TEXTURE_LOD_BIAS`, `MAX_DRAW_BUFFERS_WEBGL`,
   `MAX_COLOR_ATTACHMENTS_WEBGL`, etc. ~30 paramètres supplémentaires.
3. **readPixels cohérent GPU** : le bruit sur readPixels doit mimer les artefacts du GPU annoncé
   (differences de rasterisation, dithering GPU-spécifique).

**Estimation : ~250 lignes** (enrichissement webgl.js + données par GPU).

### 2.4 Audio fingerprint (PRIORITÉ 2)

**Problème actuel :** Le audio.js (46 lignes) ajoute un bruit ~1e-7 sur `startRendering` et
un micro-décalage sur `getOutputTimestamp`. C'est le minimum. Un vrai fingerprint audio fait :
- `OscillatorNode` → `DynamicsCompressorNode` → `AnalyserNode` → hash des fréquences
- Chaque GPU/sound card produit un hash légèrement différent
- Notre bruit est uniforme → détectable si le détecteur connaît les patterns de bruit par GPU

**Solution :**
1. **Pipeline audio complet** : intercepter `createOscillator`, `createDynamicsCompressor`,
   `createAnalyser`, `getFloatFrequencyData`, `getByteFrequencyData`.
2. **Hash audio par profil** : comme pour le canvas, maintenir une base de vrais hash audio
   par GPU/OS et produire un résultat cohérent.
3. **AnalyserNode** : intercepter `getFloatFrequencyData` / `getByteFrequencyData` et ajouter
   un bruit GPU-corrélé.

**Estimation : ~200 lignes** (réécriture audio.js).

### 2.5 Worker consistency renforcée (PRIORITÉ 2)

**Problème actuel :** Le workers.js propage `hardwareConcurrency`, `deviceMemory`, `platform` et
`userAgentData` dans les Workers. C'est bien, mais :
- Les Workers ont leur propre `performance.now()` — si la précision diffère du main thread, c'est
  un signal.
- `navigator.languages` dans un Worker peut différer.
- Un `SharedWorker` partagé entre deux contextes doit avoir les mêmes valeurs.
- Le canvas/WebGL dans un `OffscreenCanvas` (disponible dans les Workers) n'est pas patché.

**Solution :**
1. Propager `performance.now()` normalisé dans le prologue Worker.
2. Propager `navigator.languages` / `navigator.language`.
3. Intercepter `OffscreenCanvas` dans les Workers pour appliquer le même bruit canvas.

**Estimation : ~150 lignes** (enrichissement workers.js).

### 2.6 Timing / rAF naturalisation (PRIORITÉ 3)

**Problème actuel :** Pas de script dédié. Le détecteur `raf-timing` de l'Arena vérifie que les
deltas `requestAnimationFrame` correspondent au vsync (~16.67ms à 60Hz). En headless, rAF peut
être appelé à 0ms d'intervalle ou avec des deltas identiques.

**Solution :**
1. **Nouveau script timing.js** : intercepter `requestAnimationFrame` pour normaliser les deltas.
   En headless, forcer un espacement minimum de ~16ms entre les callbacks.
2. **setTimeout/setInterval** : normaliser la précision (Chrome arrondit à 1ms, certains headless
   ont une précision plus fine).
3. **`performance.now()` est déjà normalisé** dans automation.js (arrondi à 100µs). Vérifier que
   c'est cohérent avec le détecteur.

**Estimation : ~120 lignes** (nouveau timing.js).

### 2.7 Fonts réalistes et vérifiables (PRIORITÉ 3)

**Problème actuel :** Le polices.js brouille les mesures (`measureText`, `getBoundingClientRect`)
et filtre `document.fonts.check()` par OS. C'est défensif (empêche la détection), mais pas offensif
(ne simule pas les bonnes polices).

Le générateur de profils a des listes de fonts par OS (20 par OS), mais :
- Les listes sont codées en dur, pas extraites de vrais systèmes
- Pas de variation par version d'OS (macOS 15 a des fonts que macOS 14 n'a pas)
- Les mesures brouillées ne correspondent pas aux vraies mesures de ces fonts

**Solution :**
1. **Base de vrais ensembles de fonts** : collecter les fonts installées sur de vraies machines
   (macOS 14, 15, Windows 10, 11, Ubuntu 22, 24). Stocker les métriques (largeur de "mmmmm" en
   Arial 16px) pour chaque combinaison.
2. **Fonts par version d'OS** dans le profil, pas juste par OS.
3. **Métriques simulées** : au lieu de brouiller, retourner les vraies métriques correspondant
   aux fonts du profil. Plus dur à détecter car les valeurs sont *correctes*, pas brouillées.

**Estimation : ~300 lignes** (collecte + enrichissement polices.js + données).

### 2.8 WebRTC fingerprint contrôlé (PRIORITÉ 3)

**Problème actuel :** environnement.js bloque les candidats ICE `host` (protection IP) et vide
les iceServers. Mais :
- Le blocage lui-même est un signal (un vrai navigateur a des candidats host)
- `RTCPeerConnection.generateCertificate()` produit un certificat unique — si identique entre
  sessions, c'est un signal
- Le comportement STUN (timeout, réponses) est différent quand iceServers est vide

**Solution :**
1. **Candidats ICE simulés** : au lieu de bloquer, produire de faux candidats host avec une IP
   locale crédible (192.168.x.y aléatoire mais stable par profil).
2. **Certificat par profil** : le hash du certificat DTLS doit varier par profil.
3. **SDP réaliste** : le SDP local doit contenir les mêmes sections qu'un vrai Chrome.

**Estimation : ~200 lignes** (réécriture de la partie WebRTC dans environnement.js).

---

## 3. Comportement humain avancé

### 3.1 Modèle de session (le manque principal)

**Problème :** Le moteur exécute des actions (navigate, click, fill) sans modèle de *pourquoi* un
humain ferait ça. Un humain sur un site de commerce :
1. Arrive sur la page d'accueil, scanne le header, scroll un peu
2. Clique sur une catégorie, scanne les produits
3. Revient en arrière (40% du temps), essaie une autre catégorie
4. Clique sur un produit, lit la description (proportionnel à la longueur)
5. Parfois abandonne sans acheter (80% des sessions)

Le moteur actuel fait : `navigate → scroll → click → navigate → ...` sans variation, sans retour
en arrière, sans abandon. C'est le pattern d'un bot.

**Solution :**
```python
class SessionHumaine:
    """Modèle de session qui décide quoi faire et quand."""

    def __init__(self, objectif: str, profil_comportemental: ProfilSession):
        self._objectif = objectif
        self._profil = profil_comportemental
        self._pages_visitees: list[str] = []
        self._temps_debut = time.monotonic()

    def prochaine_action(self, page_courante: PageAnalysee) -> Action:
        """Décide de la prochaine action selon le contexte."""
        # Probabilité de retour en arrière (augmente avec le nombre de pages)
        if len(self._pages_visitees) > 2 and random.random() < 0.15:
            return ActionRetour()

        # Probabilité d'exploration tangente (cliquer un lien non-cible)
        if random.random() < 0.08:
            return ActionExploration(page_courante.liens_secondaires)

        # Probabilité de pause longue (distraction, autre onglet)
        if random.random() < 0.05:
            return ActionPauseLongue(duree=log_normale(5000, 0.8))

        # Sinon : avancer vers l'objectif
        return ActionProgression(self._objectif, page_courante)
```

**Estimation : ~400 lignes** (session.py + intégration dans moteur.py).

### 3.2 Micro-hésitations et patterns de lecture

**Actuellement :** Le `mouvement_aleatoire()` déplace la souris aléatoirement. Les pauses sont
calibrées (log-normal, ex-gaussian) mais ne dépendent pas du contenu de la page.

**Améliorations :**
1. **Lecture guidée par le contenu** : la souris suit approximativement le texte lu. Un lecteur
   humain déplace sa souris vers les titres, les images, les CTA — pas au hasard.
2. **Micro-hésitations** : avant de cliquer sur un bouton, 15% de probabilité de déplacer la
   souris vers le bouton puis de repartir, avant de revenir cliquer (hésitation cognitive).
3. **Patterns de scan** : F-pattern (titres puis début de lignes) pour les pages de contenu,
   Z-pattern pour les pages d'accueil. Le scroll suit le pattern de scan.

**Estimation : ~300 lignes** (enrichissement souris.py + nouveau module patterns.py).

### 3.3 Formulaires réalistes

**Actuellement :** `fill()` déplace la souris vers le champ, clique, tape avec le clavier simulé.
C'est correct mais mécanique : un humain tab entre les champs, corrige des erreurs, copie-colle
parfois, hésite sur les menus déroulants.

**Améliorations :**
1. **Navigation inter-champs** : Tab (70%), clic (25%), Shift+Tab pour revenir (5%)
2. **Timing inter-champs** : pause plus longue avant le premier champ (lire le formulaire),
   pauses courtes entre les champs familiers (nom, email), longues sur les champs inconnus
3. **Corrections** : 8% de probabilité de remplir un champ, passer au suivant, puis revenir
   corriger le précédent
4. **Menus déroulants** : ouvrir, pause de lecture des options (log-normale), sélectionner.
   Parfois ouvrir, fermer, rouvrir (hésitation).

**Estimation : ~250 lignes** (nouveau formulaires.py).

### 3.4 Scroll naturel avancé

**Actuellement :** Le `defilement.py` a deux modes (trackpad/molette) avec inertie et phases.
C'est bon, mais :
- Le scroll ne dépend pas du contenu (même profil pour une page longue et une page courte)
- Pas de scroll "rage" (scroll rapide pour chercher quelque chose)
- Pas de scroll+lecture (alterner scroll court et pause de lecture)
- Le scroll s'arrête toujours proprement (un humain s'arrête parfois en plein milieu d'un
  paragraphe, ajuste de 20px, puis lit)

**Améliorations :**
1. **Scroll adaptatif** : la distance dépend de la densité du contenu visible
2. **Lecture_page() amélioré** : alterner scroll court (2-3 lignes) pour la lecture attentive
   et scroll long (demi-page) pour le scan rapide
3. **Micro-corrections** : 20% de probabilité d'ajuster le scroll de ±15-40px après l'arrêt

**Estimation : ~150 lignes** (enrichissement defilement.py).

---

## 4. Ce que font les meilleurs

### 4.1 Ce que Camoufox fait que NOEZIA ne fait pas

| Technique Camoufox | NOEZIA | Difficulté à reproduire |
|---------------------|--------|------------------------|
| **Fingerprint compilé dans Firefox** — les valeurs canvas/WebGL sont natives, pas injectées par JS. Invisible à toString/getOwnPropertyDescriptor. | Injection JS avec `natif()` pour masquer les overrides. Résiste aux tests toString mais pas à une analyse statique du code V8. | Très difficile sans compiler un navigateur. |
| **Empreinte TLS Firefox native** — pas de patch, c'est le vrai TLS de Firefox. | Patchright = TLS Chrome réel. Pas de problème TLS, mais pas de choix non plus. | N/A — on est OK côté TLS grâce à Patchright. |
| **Rotation de viewport** — peut changer la taille de fenêtre entre les sessions sans incohérence. | Viewport fixe par profil. | Facile (~30 lignes). |
| **Fonts natives** — les fonts disponibles sont celles du système, pas une simulation. | `document.fonts.check()` filtré par OS. Les mesures sont brouillées, pas simulées. | Moyen (~200 lignes). |
| **Aucun marqueur d'automation** — pas de `__playwright`, pas de CDP visible. | Nettoyage des globales et stack traces, mais CDP est techniquement présent (Patchright l'utilise). | Difficile — CDP est inhérent à Patchright/Playwright. |

**Conclusion Camoufox :** Le principal avantage est la furtivité *native* (pas d'injection JS). Pour
reproduire ça sans compiler un navigateur, il faudrait que nos injections soient parfaitement
indétectables — ce qui est une course sans fin. L'approche pragmatique : investir dans les tests
de détectabilité de nos patches, pas dans la perfection des patches eux-mêmes.

### 4.2 Ce que BrowserForge fait que NOEZIA ne fait pas

BrowserForge est un générateur de fingerprints réalistes (pas un moteur, un outil complémentaire).

| Technique BrowserForge | NOEZIA | Impact |
|-------------------------|--------|--------|
| **Base de données de vrais fingerprints** collectés depuis des navigateurs réels. Chaque fingerprint est un ensemble complet {canvas hash, audio hash, WebGL params, fonts, screen, ...}. | Profils construits manuellement (18 machines). Les hash canvas/audio sont générés par bruit, pas extraits de données réelles. | Énorme — la cohérence inter-signaux est garantie par construction (c'est un vrai fingerprint). |
| **Distribution statistique** des fingerprints pondérée par les parts de marché réelles. Un fingerprint Chrome 131 / Windows 11 / RTX 3060 a la bonne fréquence d'apparition. | Profils équiprobables (random.choice). Un Mac M5 Pro est aussi probable qu'un Intel Iris Xe — pas réaliste. | Important — un fingerprint rare est un signal. |
| **Variation entre sessions** : chaque session tire un nouveau fingerprint de la base, avec les bonnes corrélations. | Profil fixe par nom ou aléatoire. Pas de rotation intelligente. | Moyen. |

**Conclusion BrowserForge :** L'investissement principal est la **collecte de vrais fingerprints**.
On pourrait utiliser BrowserForge comme source de profils (MIT), ou construire notre propre base.

### 4.3 Ce que font les services commerciaux

**Bright Data (anciennement Luminati) :**
- Réseau de proxies résidentiels (72M+ IPs). Impossible à reproduire.
- Navigateur avec fingerprint pré-configuré + proxy résidentiel = passe presque tout.
- L'approche : résoudre le problème côté réseau plutôt que côté fingerprint.
- **Ce qu'on peut reproduire** : la qualité des profils navigateur et la rotation. Pas le réseau.

**Oxylabs :**
- Web Unblocker : API qui gère automatiquement les proxies, headers, cookies, fingerprints.
- ML pour choisir le bon proxy + fingerprint par cible.
- **Ce qu'on peut reproduire** : le choix intelligent du profil par cible (un site financier attend
  des profils desktop haute résolution, pas un mobile).

**Multilogin / GoLogin / AdsPower (anti-detect browsers) :**
- Navigateurs multi-profils avec fingerprints isolés par profil.
- Chaque profil a son propre canvas hash, audio hash, WebGL, fonts, etc.
- Stockage de l'état navigateur (cookies, localStorage) par profil.
- **C'est exactement ce qu'on construit**, mais ils ont 5-10 ans d'avance sur la collecte de données.

**SmartProxy / Scrapfly / ZenRows (scraping APIs) :**
- Rotation automatique navigateur + proxy + fingerprint.
- Retry intelligent avec changement de stratégie (si Cloudflare bloque, essayer avec un profil
  Firefox + proxy résidentiel).
- **Ce qu'on peut reproduire** : la logique de retry et d'adaptation.

### 4.4 Technique que personne n'a encore (notre opportunité)

**Comportement humain calibré sur la recherche en neurosciences motrices.** Les services commerciaux
résolvent le problème par la force brute (millions d'IPs, vrais navigateurs). Les outils open source
ne font aucun comportement. NOEZIA est le seul à utiliser minimum-jerk, Fitts' law, digraphes
biomécaniques, distributions ex-gaussiennes auto-corrélées.

Si on pousse ce comportement jusqu'au bout (modèle de session, patterns de lecture, formulaires
réalistes), on aura un avantage que ni les services commerciaux (qui ne s'en soucient pas car ils
ont les IPs) ni les outils open source (qui n'ont pas l'expertise) ne reproduiront facilement.

**C'est notre niche et notre moat.**

---

## 5. Feuille de route concrète

### Étape 1 — Arena durcie (impact: critique, difficulté: faible)

**Quoi :** Activer les 26 détecteurs existants mais non branchés dans le gardien. Distribuer
progressivement par niveau (voir l'audit Arena). Implémenter le détecteur HTTP/2 et le score
composite.

**Pourquoi en premier :** On ne peut pas améliorer le moteur sans savoir ce qui le casse. L'Arena
durcie est l'adversaire qui force l'amélioration.

**Estimation :** ~400 lignes (gardien.py + profils.yaml + détecteur HTTP/2 + score composite).

**Critère de validation :** Le moteur NOEZIA **échoue** à partir du niveau 03-04 révisé. C'est un
succès de l'Arena, pas un échec du moteur.

### Étape 2 — Profils statistiquement réalistes (impact: élevé, difficulté: moyenne)

**Quoi :**
- Collecter de vrais fingerprints depuis des navigateurs réels (ou utiliser BrowserForge comme
  source). Au minimum : 200 profils validés avec canvas hash, audio hash, WebGL params, fonts.
- Pondérer les profils par parts de marché réelles (Chrome 131 + Windows 11 = fréquent,
  Chrome 129 + Linux = rare).
- Enrichir le générateur pour tirer des profils de la base plutôt que de les construire.

**Estimation :** ~500 lignes (base_reelle.py + enrichissement.py + collecte).

**Critère de validation :** Un détecteur qui connaît la distribution des fingerprints ne peut pas
distinguer nos profils de vrais navigateurs (test KS sur les distributions de canvas hash,
WebGL params, etc.).

### Étape 3 — Transport HTTP/2 furtif (impact: élevé, difficulté: moyenne)

**Quoi :**
- Intégrer curl-cffi comme transport HTTP alternatif pour les requêtes sans JS.
- Impersonation du ClientHello TLS et des SETTINGS HTTP/2 de Chrome, cohérents avec le profil.
- Cookie jar partagé entre le transport HTTP et le navigateur.

**Estimation :** ~400 lignes (transport/ package + intégration dans moteur.py).

**Critère de validation :** Le détecteur HTTP/2 de l'Arena (étape 1) ne voit aucune incohérence
entre l'empreinte HTTP/2 des requêtes curl-cffi et l'UA annoncé.

### Étape 4 — Canvas/WebGL/Audio cohérents (impact: élevé, difficulté: élevée)

**Quoi :**
- Réécrire canvas.js avec bruit GPU-corrélé et stabilité double-appel garantie.
- Enrichir webgl.js : extensions par GPU, paramètres WebGL2, readPixels GPU-corrélé.
- Réécrire audio.js : pipeline complet (Oscillator→Compressor→Analyser), hash par profil.
- Construire ou intégrer une base de vrais hash {canvas, audio, WebGL} par GPU/OS.

**Estimation :** ~850 lignes (canvas 400 + WebGL 250 + audio 200).

**Critère de validation :**
- Le détecteur `canvas-consistency` (double-appel) ne détecte pas d'injection.
- Le détecteur `canvas-empreinte` avec corrélation cross-session voit des hash uniques par profil.
- Les hash sont plausibles pour le GPU annoncé (vérification de cohérence).

### Étape 5 — Modèle de session et comportement avancé (impact: élevé, difficulté: moyenne)

**Quoi :**
- Modèle de session humaine (session.py) : objectif, exploration, retours, abandondon.
- Formulaires réalistes (formulaires.py) : Tab, corrections, hésitations.
- Patterns de lecture et micro-hésitations (enrichissement souris.py).
- Scroll adaptatif au contenu.

**Estimation :** ~1 100 lignes (session 400 + formulaires 250 + patterns 300 + scroll 150).

**Critère de validation :**
- Le détecteur `entropie-interaction` ne distingue pas le moteur d'un humain sur une session
  de 20+ actions.
- Le détecteur `flux-navigation` (nouveau, à créer dans l'Arena) ne repère pas de pattern bot.

### Étape 6 — Worker/timing/WebRTC (impact: moyen, difficulté: moyenne)

**Quoi :**
- Enrichir workers.js : OffscreenCanvas, performance.now normalisé, languages.
- Nouveau timing.js : rAF naturalisation, setTimeout précision.
- WebRTC : candidats ICE simulés, certificat par profil, SDP réaliste.

**Estimation :** ~470 lignes (workers 150 + timing 120 + WebRTC 200).

**Critère de validation :**
- `worker-consistency` : aucune différence main thread vs Worker.
- `raf-timing` : deltas rAF à ~16.67ms ± bruit vsync naturel.
- `webrtc` : pas de blocage détecté, SDP réaliste.

### Étape 7 — Plugins par WAF et validation externe (impact: décisif, difficulté: élevée)

**Quoi :**
- Architecture de plugins extensible : un plugin par WAF/détecteur commercial.
- Plugin Cloudflare Free : passer la vérification JS sans déclencher Turnstile.
- Tests reproductibles contre un vrai Cloudflare Free (site de test autorisé).
- Résultats honnêtes publiés.

**Estimation :** ~600 lignes (base plugin 200 + Cloudflare 400).

**Critère de validation :** Le moteur passe un site protégé par Cloudflare Free de manière
reproductible (≥ 80% de succès sur 50 passages). C'est le passage de 3/10 à 7/10.

### Étape 8 — Pool et scaling (impact: moyen, difficulté: moyenne)

**Quoi :**
- Pool de navigateurs : N sessions en parallèle avec des profils différents.
- Rotation intelligente : changer de profil si une session est bloquée.
- Rate limiting par profil : respecter les limites implicites du site cible.
- Gestion mémoire : recycler les contextes après N pages.

**Estimation :** ~500 lignes (pool.py + rotation.py + limites.py).

**Critère de validation :** 10 sessions parallèles avec 10 profils différents, chacune passant
le niveau 06 de l'Arena durcie, sans que la corrélation cross-session ne les relie.

---

## Récapitulatif

| Étape | Quoi | Lignes estimées | Impact | Critère de succès |
|-------|------|-----------------|--------|-------------------|
| 1 | Arena durcie | ~400 | Critique | NOEZIA échoue au niveau 03-04 |
| 2 | Profils réalistes | ~500 | Élevé | Distribution indistinguable de vrais navigateurs |
| 3 | Transport HTTP/2 | ~400 | Élevé | Détecteur HTTP/2 Arena passé |
| 4 | Canvas/WebGL/Audio | ~850 | Élevé | Cohérence GPU, unicité cross-session, double-appel |
| 5 | Session + comportement | ~1 100 | Élevé | Entropie et flux navigation indétectables |
| 6 | Worker/timing/WebRTC | ~470 | Moyen | Cohérence inter-contextes |
| 7 | Plugins WAF + tests | ~600 | Décisif | Cloudflare Free ≥ 80% |
| 8 | Pool et scaling | ~500 | Moyen | 10 sessions parallèles sans corrélation |
| **Total** | | **~4 820** | | **De 3/10 à 7/10** |

Le total (~4 820 lignes) doublerait à peu près le code du moteur (actuellement ~4 900 lignes).
C'est réaliste pour un moteur de ~10 000 lignes — ni trop peu (pas un wrapper), ni trop
(pas de code mort).

L'ordre est important : l'étape 1 (Arena durcie) doit venir en premier car sans adversaire
crédible, toutes les autres étapes sont de l'optimisation dans le vide. L'étape 7 (validation
externe) est le test de vérité — c'est là qu'on passe de « ça marche sur notre terrain » à
« ça marche dans le monde réel ».

---

## Questions ouvertes

1. **Licence de BrowserForge** (MIT) : peut-on l'utiliser comme source de profils pour un produit
   commercial, ou faut-il construire notre propre base de collecte ?

2. **Proxy man-in-the-middle pour HTTP/2** (étape 3 phase 2) : est-ce que la latence ajoutée
   est acceptable ? Un proxy local ajoute ~1-5ms, mais un WAF qui mesure les timings de
   connexion pourrait le détecter.

3. **Test contre Cloudflare** (étape 7) : quel site de test utiliser ? Options :
   - Notre propre domaine derrière Cloudflare Free (le plus propre)
   - Un site tiers avec autorisation (programme bug bounty ?)
   - nowsecure.nl / bot.sannysoft.com (détecteurs publics, pas des WAF)

4. **Camoufox en backup** : maintenir un DriverCamoufox en parallèle de DriverNoezia pour les
   cas où l'empreinte Firefox est un avantage ? Le moteur isolé existe déjà, c'est juste une
   question de stratégie multi-moteur.

5. **Collecte de vrais fingerprints** : comment collecter légalement et éthiquement les hash
   canvas/audio/WebGL de vrais navigateurs ? Options :
   - Lancer nos propres navigateurs sur différentes machines et collecter les empreintes
   - Utiliser des données publiées (FingerprintJS a publié des statistiques)
   - Crowdsourcing volontaire (site web qui affiche le fingerprint du visiteur)

6. **IA pour la planification de session** (long terme) : un LLM qui regarde le HTML de la page
   et décide de la prochaine action ? C'est dans la vision du projet mais c'est un chantier
   entier (RAG sur les patterns de navigation, fine-tuning sur des sessions humaines réelles).
   À quand dans la roadmap ?

---

*Ce document est un brainstorming, pas un engagement. Les estimations en lignes de code sont des
ordres de grandeur. La feuille de route sera affinée après l'étape 1 (Arena durcie) quand on saura
exactement ce qui casse.*
