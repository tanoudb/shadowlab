# Brainstorm : Durcissement de l'Arena ShadowLab

**Date** : 10 novembre 2026
**Objectif** : Transformer l'Arena d'un filtre basique en un adversaire crédible, comparable aux protections commerciales (Cloudflare Bot Management, DataDome, PerimeterX/HUMAN).

---

## Table des matières

1. [Brancher les 26 detectors existants](#1-brancher-les-26-détecteurs-existants)
2. [Score composite](#2-score-composite)
3. [Corrélation cross-session](#3-corrélation-cross-session)
4. [Détecteur HTTP/2](#4-détecteur-http2)
5. [Niveaux révisés (7 niveaux)](#5-niveaux-révisés--7-niveaux)
6. [Plan d'implémentation](#6-plan-dimplémentation)

---

## 1. Brancher les 26 détecteurs existants

### Diagnostic

Le gardien (`gardien.py`) ne consulte que 6 détecteurs, câblés en dur dans deux tuples :

```python
REGLES_REQUETE = ("regles-http", "tls")
REGLES_JAVASCRIPT = ("botd", "regles-js", "coherence", "comportement")
```

La fonction `suspicion()` itère sur ces noms, appelle `detecteur.classer(observations)`, et
collecte les motifs quand le verdict est `automatise`. C'est une logique binaire : un seul
détecteur qui dit `automatise` suffit à bloquer. Les 26 autres ne sont jamais consultés pour
la décision.

### Modification proposée de `gardien.py`

**Principe** : rendre la liste des détecteurs consultés configurable par niveau, via le profil Arena.

#### a) Ajouter un champ `detecteurs` au profil Fingerprinting

Dans `profils.py`, le modèle `Fingerprinting` reçoit un nouveau champ :

```python
class Fingerprinting(_Strict):
    actif: bool
    bloquer: ModeBlocage = "non"
    exclure: list[str] = Field(default_factory=list)
    detecteurs: list[str] = Field(default_factory=list)  # NOUVEAU : liste explicite
    seuil_score: float = Field(default=1.0, ge=0.0, le=10.0)  # NOUVEAU : score composite
```

Si `detecteurs` est vide, le comportement actuel est conservé (les 6 de base). Sinon, seuls
les détecteurs listés sont consultés. Le `exclure` existant continue de fonctionner (soustraction).

#### b) Modifier `suspicion()` dans `gardien.py`

La fonction actuelle :

```python
def suspicion(cx, jeton, inclure_js=True, exclure=None):
    http, js = db.observations(cx, jeton)
    observations = Observations(http=http, js=js, tls=db.tls_session(cx, jeton))
    noms = list(REGLES_REQUETE)
    if inclure_js and observations.empreinte_js is not None:
        noms += REGLES_JAVASCRIPT
    if exclure:
        noms = [n for n in noms if n not in exclure]
    detecteurs = registre()
    motifs = []
    for nom in noms:
        classement = detecteurs[nom].classer(observations)
        if classement.classification == "automatise":
            motifs.append(...)
    return motifs
```

Devient (schéma conceptuel) :

```python
def suspicion(cx, jeton, inclure_js=True, exclure=None, detecteurs_actifs=None, seuil=None):
    http, js = db.observations(cx, jeton)
    observations = Observations(http=http, js=js, tls=db.tls_session(cx, jeton))

    if detecteurs_actifs:
        # Mode étendu : liste explicite du profil
        noms_http = [n for n in detecteurs_actifs if n in DETECTEURS_HTTP]
        noms_js = [n for n in detecteurs_actifs if n in DETECTEURS_JS]
        noms = noms_http
        if inclure_js and observations.empreinte_js is not None:
            noms += noms_js
    else:
        # Mode legacy (niveaux 01-02)
        noms = list(REGLES_REQUETE)
        if inclure_js and observations.empreinte_js is not None:
            noms += REGLES_JAVASCRIPT

    if exclure:
        noms = [n for n in noms if n not in exclure]

    tous = registre()
    classements = [(nom, tous[nom].classer(observations)) for nom in noms if nom in tous]

    if seuil is not None:
        # Mode score composite
        return _evaluer_score(classements, seuil)
    else:
        # Mode binaire (actuel)
        return _evaluer_binaire(classements)
```

#### c) Groupement logique des détecteurs

Les 32 détecteurs se répartissent en 5 familles, qui correspondent à des couches de détection
différentes :

| Famille | Détecteurs | Ce qu'ils attrapent |
|---------|-----------|-------------------|
| **Transport** | `regles-http`, `tls` | Clients HTTP bruts, piles TLS de bibliothèque |
| **Empreinte navigateur** | `botd`, `regles-js`, `headless`, `chrome-apis`, `media-codecs`, `langues`, `css-media`, `permissions-etendu`, `connection-dynamic`, `position-fenetre` | Navigateurs headless, absences de fonctionnalités |
| **Intégrité des patches** | `prototypes`, `integrite-proprietes`, `stack-trace`, `stack-getter`, `automation-globals`, `prototype-chain`, `enumerable-props`, `proxy-uadata`, `timing-precision`, `paint-timing` | Patches JS mal faits, injections d'automation |
| **Cohérence** | `coherence`, `coherence-profonde`, `coherence-environnement`, `canvas-empreinte`, `canvas-consistency`, `worker-consistency`, `raf-timing` | Incohérences entre ce que le navigateur dit être et ce qu'il est |
| **Comportement** | `comportement`, `entropie-interaction`, `scroll`, `webrtc` | Comportement non humain, fuites réseau |

---

## 2. Score composite

### Problème de la logique binaire actuelle

La logique actuelle est `OR` : un seul détecteur qui dit `automatise` bloque. C'est :
- **Trop strict** pour les détecteurs faibles (un faux positif bloque tout)
- **Trop laxiste** pour les signaux combinés (10 détecteurs `indetermine` ne font rien)

Les protections commerciales (Cloudflare, DataDome) utilisent un **score composite** : chaque
signal ajoute un poids, et le total est comparé à un seuil. Cela permet :
- De capturer les bots qui sont "juste assez bons" sur chaque détecteur
- De tolérer un signal isolé sans bloquer un humain sur un navigateur exotique

### Architecture du score

```
Score_session = Somme( poids_signal * coefficient_detecteur )

Si Score_session >= seuil_niveau → bloqué
Si Score_session >= seuil_captcha → CAPTCHA
Si Score_session < seuil_passant → passé
Sinon → indéterminé (journalisé, pas bloqué)
```

#### Coefficients par famille de détecteur

| Famille | Coefficient | Justification |
|---------|------------|---------------|
| Transport | 1.0 | Signal fort, peu de faux positifs |
| Intégrité | 1.2 | Un patch mal fait est quasi-certain = bot |
| Cohérence | 0.8 | Peut être un navigateur exotique ou ancien |
| Empreinte navigateur | 0.7 | Varie selon les versions, DPR/locale sont culturels |
| Comportement | 1.0 | Bon signal mais dépend de la durée de la session |

Les poids de chaque `Signal` dans `detection.py` existent déjà (le champ `poids: float`).
Le score composite les utilise directement :

```python
def score_composite(classements: list[tuple[str, Classement]], coefficients: dict[str, float]) -> float:
    score = 0.0
    for nom, classement in classements:
        coeff = coefficients.get(famille_de(nom), 1.0)
        for signal in classement.signals:
            score += signal.poids * coeff
    return score
```

#### Seuils par niveau

| Niveau | Seuil blocage | Seuil CAPTCHA | Seuil passant | Philosophie |
|--------|--------------|---------------|--------------|-------------|
| 01 | -- | -- | -- | Aucune protection |
| 02 | 2.0 | -- | 0.0 | Bloque les outils évidents |
| 03 | 1.5 | -- | 0.0 | Bloque Playwright/Selenium bruts |
| 04 | 1.2 | 0.8 | 0.0 | Patches naïfs échouent, CAPTCHA sur suspicion |
| 05 | 1.0 | 0.6 | 0.0 | Combinaison de signaux faibles bloque |
| 06 | 0.7 | 0.4 | 0.0 | Seuil très bas, tout signal compte |
| 07 | 0.5 | 0.3 | 0.0 | Etat de l'art : même un signal isolé suffit |

**Le seuil qui baisse** est l'équivalent du "threat score" de Cloudflare : plus on monte en
sécurité, moins on tolère de signaux.

### Gestion des faux positifs

Le score composite réduit les faux positifs (un signal isolé faible ne bloque plus seul), mais
il faut aussi :

1. **Listes blanches** : un navigateur avec un user-agent connu et un JA4 cohérent peut avoir
   un bonus négatif (-0.3). Implémentable via un détecteur `confiance-navigateur` qui retourne
   des signaux négatifs.

2. **Calibration empirique** : lancer des campagnes avec un vrai Chrome piloté manuellement
   (session humaine de référence, `consent_at` non nul), mesurer le score, et ajuster les
   seuils pour que le score humain soit toujours < seuil_captcha.

3. **Décroissance temporelle** : un signal vieux de 5 minutes vaut moins qu'un signal frais.
   Un bot rapide accumule les signaux en quelques secondes ; un humain lent en accumule peu.

4. **Soft-block** : au lieu de bloquer net, servir un CAPTCHA interstitiel (comme Cloudflare).
   Le score composite alimente les 3 zones : passé / CAPTCHA / bloqué.

### Signal vs bruit : classement des détecteurs

**Signal fort (vrais positifs, peu de bruit)** :
- `worker-consistency` : quasiment sans faux positif (le main thread et le Worker lisent le même matériel)
- `stack-trace` / `stack-getter` : un nom de framework dans la stack = certitude
- `automation-globals` : les globales CDC/playwright sont des marqueurs directs
- `prototypes` : toString patché est un marqueur direct
- `entropie-interaction` : un CV de délais < 0.05 est machine à coup sûr
- `raf-timing` : deltas rAF à 0 = headless sans vsync

**Signal moyen (bons positifs, quelques faux)** :
- `coherence-profonde` : availWidth > width est impossible, mais outer == inner arrive sur
  certains gestionnaires de fenêtres Linux tiling
- `canvas-consistency` : toDataURL instable est presque toujours un patch, mais peut arriver
  avec certains GPU bugués
- `integrite-proprietes` : .length/.name incorrects attrapent les patches naïfs
- `headless` : hasFocus false arrive sur des onglets en arrière-plan

**Signal faible (bruit possible)** :
- `coherence-environnement` : timezone vs locale a beaucoup de vrais cas humains
  (expat, multilingue, VPN)
- `timing-precision` : varie selon les navigateurs et les politiques de sécurité
- `permissions-etendu` : all denied est le défaut de Chrome sur localhost
- `position-fenetre` : screenX/Y à 0 arrive sur un écran principal

Le score composite pondère naturellement : les détecteurs à signal fort ont des signaux à
`poids: 1.0`, ceux à signal faible ont des poids `0.25-0.5`.

---

## 3. Corrélation cross-session

### Problème

L'Arena traite chaque session indépendamment. Un bot qui renouvelle sa session 100 fois avec
le même fingerprint passe 100 fois les mêmes détecteurs. Les WAF commerciaux corrèlent les
sessions par fingerprint pour détecter :
- **Fingerprints identiques** entre sessions (même canvas hash, même JA4, même profil)
- **Rotation de fingerprints trop rapide** (changement à chaque session = outil de rotation)
- **Volume par fingerprint** (un fingerprint qui fait 1000 sessions en 1h est un bot)

### Architecture

#### a) Table de hash

Nouvelle table SQLite :

```sql
CREATE TABLE empreintes_vues (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL,           -- 'canvas', 'audio', 'ja4', 'profil_complet'
    hash TEXT NOT NULL,
    premiere_vue TEXT NOT NULL,   -- datetime
    derniere_vue TEXT NOT NULL,
    nb_sessions INTEGER NOT NULL DEFAULT 1,
    sessions TEXT NOT NULL DEFAULT '[]',  -- JSON : 10 derniers tokens
    UNIQUE (type, hash)
);
CREATE INDEX empreintes_vues_hash ON empreintes_vues(type, hash);
CREATE INDEX empreintes_vues_nb ON empreintes_vues(nb_sessions DESC);
```

#### b) Collecte des hash

A la fin de chaque session (dans `passages.py` ou un hook), calculer :

```python
import hashlib, json

def hash_session(fingerprint: dict) -> dict[str, str]:
    """Calcule les hash de corrélation d'une session."""
    canvas = fingerprint.get("browser_properties", {}).get("canvas", "")
    ja4 = fingerprint.get("tls_properties", {}).get("ja4", "")
    nav = fingerprint.get("browser_properties", {}).get("navigateur", {})

    # Hash de profil complet : UA + platform + screen + hwc + dpr + langues
    profil = json.dumps({
        "ua": nav.get("userAgent", ""),
        "platform": (nav.get("userAgentData") or {}).get("platform", ""),
        "screen": fingerprint.get("browser_properties", {}).get("ecran", {}),
        "hwc": nav.get("hardwareConcurrency"),
        "dpr": fingerprint.get("browser_properties", {}).get("ecran", {}).get("devicePixelRatio"),
        "languages": nav.get("languages", []),
    }, sort_keys=True)

    return {
        "canvas": hashlib.sha256(str(canvas).encode()).hexdigest()[:16],
        "ja4": ja4,  # déjà un hash
        "profil_complet": hashlib.sha256(profil.encode()).hexdigest()[:16],
    }
```

#### c) Détecteur cross-session

Nouveau détecteur `correlation-session` :

```python
class DetecteurCorrelationSession:
    name = "correlation-session"
    version = "1"

    SEUIL_SESSIONS = 5   # suspicion à partir de 5 sessions avec le même hash
    SEUIL_RAPIDE = 10    # suspicion si 10 sessions en 1h

    def classer(self, obs, cx, jeton):
        # Lookup dans empreintes_vues
        for type_hash, valeur in hash_session(proprietes(obs)).items():
            row = cx.execute(
                "SELECT nb_sessions, premiere_vue FROM empreintes_vues WHERE type = ? AND hash = ?",
                (type_hash, valeur)
            ).fetchone()
            if row and row["nb_sessions"] >= self.SEUIL_SESSIONS:
                ...  # signal
```

**Note** : ce détecteur a besoin d'un accès à la base (via `cx`), ce qui casse l'interface
actuelle `Detecteur.classer(obs) -> Classement`. Deux options :
1. Enrichir `Observations` avec les données cross-session avant l'appel
2. Passer `cx` en paramètre optionnel (breaking mais simple)

**Recommandation** : option 1, en ajoutant un champ `correlation: dict` à `Observations`,
rempli par `suspicion()` avant d'appeler les détecteurs.

#### d) Rate limiting par fingerprint

En complément du rate limit Nginx par session (`$http_x_shadowlab_session`), ajouter un
rate limit par hash de profil. Implémentable soit :
- Côté Python (dans `gardien.py`), en comptant les requêtes par hash dans la table
- Côté Nginx, en utilisant `$http_x_shadowlab_fingerprint` comme variable (le frontal
  calcule le hash et le passe en en-tête interne)

La seconde option est plus performante (Nginx fait du rate limiting natif), mais nécessite
que le frontal connaisse le hash avant la première requête, ce qui n'est pas le cas (le hash
canvas arrive après le JavaScript). Le rate limit par fingerprint côté Python est donc la voie
réaliste pour la première itération.

---

## 4. Détecteur HTTP/2

### Pourquoi c'est critique

L'empreinte HTTP/2 est **le signal le plus différenciant** entre un vrai navigateur et un outil.
Cloudflare, Akamai et Fastly l'utilisent en production. Le fingerprint TLS (JA3/JA4) est déjà
contournable (les bibliothèques comme `curl-cffi`, `tls-client` reproduisent le ClientHello de
Chrome). Mais le fingerprint HTTP/2 est beaucoup plus dur à reproduire :

- **SETTINGS frame** : chaque navigateur envoie des valeurs différentes pour
  HEADER_TABLE_SIZE, MAX_CONCURRENT_STREAMS, INITIAL_WINDOW_SIZE, MAX_FRAME_SIZE,
  MAX_HEADER_LIST_SIZE
- **Pseudo-header order** : `:method`, `:authority`, `:scheme`, `:path` — Chrome envoie
  dans un ordre, Firefox dans un autre, curl dans un troisième
- **WINDOW_UPDATE** : la taille initiale de fenêtre varie
- **PRIORITY / PRIORITY_UPDATE** : Chrome les envoie, curl non
- **HPACK** : la stratégie de compression des en-têtes varie (Huffman, table statique vs
  dynamique)

### Signaux à capturer

| Signal | Valeur Chrome | Valeur curl | Détectabilité |
|--------|--------------|-------------|---------------|
| SETTINGS order | `[1,2,4,6]` (HEADER_TABLE_SIZE, ENABLE_PUSH, INITIAL_WINDOW_SIZE, MAX_HEADER_LIST_SIZE) | `[1,3,4]` | Facile |
| INITIAL_WINDOW_SIZE | 6291456 (Chrome 120+) | 65535 (défaut RFC) | Facile |
| MAX_CONCURRENT_STREAMS | absent (Chrome ne l'envoie pas en client) | 100 | Facile |
| MAX_HEADER_LIST_SIZE | 262144 | absent | Facile |
| Pseudo-header order | `:method :authority :scheme :path` | `:method :path :scheme :authority` | Facile |
| WINDOW_UPDATE (conn) | 15663105 | absent | Moyen |
| PRIORITY frames | oui (Chrome) / non (Chrome 131+, PRIORITY_UPDATE) | non | Moyen |
| HPACK Huffman | oui | oui (mais stratégie différente) | Difficile |

### Implémentation

#### a) Limitation actuelle du frontal

Le frontal (`frontal.py`) utilise `h11` (HTTP/1.1 seulement) et annonce `set_alpn_protocols(["http/1.1"])`.
Il ne peut pas parler HTTP/2 aux clients. C'est la limitation la plus bloquante.

Ligne 316 de `frontal.py` :
```python
self.contexte.set_alpn_protocols(["http/1.1"])  # h11 ne parle que HTTP/1.1
```

#### b) Option 1 : Remplacer h11 par un serveur HTTP/2

Utiliser `h2` (la bibliothèque Python HTTP/2, `pip install h2`) pour parser le SETTINGS frame
et les pseudo-headers. Le frontal accepte HTTP/2 du client, extrait les signaux, puis relaie
en HTTP/1.1 vers Nginx (qui ne change pas).

**Modifications** :
- `frontal.py` : remplacer `h11.Connection` par `h2.connection.H2Connection` pour la
  connexion client. Le relais vers Nginx reste en HTTP/1.1 via `http.client`.
- `tls.py` : ajouter une fonction `h2_empreinte(connection)` qui extrait les SETTINGS,
  l'ordre des pseudo-headers, et le WINDOW_UPDATE.
- Nouveau champ dans `observations_tls` : `h2_fingerprint TEXT`.

**Complexité** : h2 est une state machine bas niveau. Il faut gérer les frames manuellement,
ce qui est plus complexe que h11 mais faisable (h2 est bien documentée et maintenue).

#### c) Option 2 : Module Nginx (plus performant mais plus complexe)

Utiliser un module Nginx qui expose les SETTINGS HTTP/2 en en-têtes internes. Le module
`ngx_http_v2_fingerprint` (https://github.com/AliasIO/ngx_http_v2_fingerprint) fait
exactement ça. Mais il faut compiler un Nginx custom, ce qui complique le Docker.

**Recommandation** : Option 1 (h2 dans le frontal Python). Le frontal fait déjà le TLS
termination et l'observation — ajouter HTTP/2 dans le même processus est cohérent avec
l'architecture. Le frontal ne gère pas de charge (c'est un labo local), donc la performance
Python est suffisante.

#### d) Référentiel de fingerprints HTTP/2

Akarmai h2fingerprint research + https://tls.peet.ws/api/all :

| Navigateur | SETTINGS | WINDOW_UPDATE | Pseudo-order | Identifiant |
|-----------|----------|---------------|-------------|-------------|
| Chrome 120+ | `1:65536;2:0;4:6291456;6:262144` | 15663105 | `m,a,s,p` | `chrome_120` |
| Firefox 120+ | `1:65536;4:131072;5:16384` | 12517377 | `m,p,a,s` | `firefox_120` |
| Safari 17+ | `4:4194304;3:100` | 10485760 | `m,s,p,a` | `safari_17` |
| curl (default) | `1:65536;3:100;4:65535` | absent | `m,p,s,a` | `curl_default` |
| curl-cffi (Chrome) | Copie Chrome | Copie Chrome | `m,a,s,p` | `impersonate_chrome` |
| httpx | pas de HTTP/2 | -- | -- | `http11_only` |
| requests | pas de HTTP/2 | -- | -- | `http11_only` |
| Playwright (Chrome) | = Chrome natif | = Chrome natif | `m,a,s,p` | `chrome_120` |

**curl-cffi avec impersonate passe ce test.** C'est attendu : il reproduit fidèlement les
settings Chrome. Le détecteur HTTP/2 est surtout utile contre les outils qui ne reproduisent
pas ces settings (httpx, requests, Scrapling HTTP, curl brut, Go net/http).

#### e) Nouveau détecteur `http2`

```python
class DetecteurHttp2:
    name = "http2"
    version = "1"

    CHROME_SETTINGS = {"1": 65536, "2": 0, "4": 6291456, "6": 262144}
    FIREFOX_SETTINGS = {"1": 65536, "4": 131072, "5": 16384}
    SAFARI_SETTINGS = {"4": 4194304, "3": 100}

    def classer(self, obs):
        h2 = (obs.tls or {}).get("h2_fingerprint")
        if h2 is None:
            return _indetermine(...)

        signaux = []
        settings = h2.get("settings", {})
        ua = ...  # extraire le navigateur déclaré

        # SETTINGS incohérents avec le navigateur annoncé
        if "chrome" in ua and settings != self.CHROME_SETTINGS:
            signaux.append(Signal("h2_settings_mismatch", "...", 0.9))

        # Pseudo-header order anormal
        order = h2.get("pseudo_order", [])
        if "chrome" in ua and order != ["m", "a", "s", "p"]:
            signaux.append(Signal("h2_pseudo_order", "...", 0.8))

        # WINDOW_UPDATE absent pour Chrome
        if "chrome" in ua and not h2.get("window_update_conn"):
            signaux.append(Signal("h2_window_update_absent", "...", 0.7))

        # Pas de HTTP/2 du tout alors que le navigateur le supporte
        if h2.get("protocol") == "http/1.1" and ("chrome" in ua or "firefox" in ua):
            signaux.append(Signal("h2_absent", "...", 0.6))

        return _verdict(self.name, self.version, signaux)
```

---

## 5. Niveaux révisés : 7 niveaux

### Vue d'ensemble

| Niveau | Nom | Equivalent commercial | Détecteurs actifs | Seuil score |
|--------|-----|----------------------|------------------|-------------|
| 01 | Baseline | Aucune protection | aucun | -- |
| 02 | Détection HTTP | CDN basique (IP rate limit) | 2 détecteurs | 2.0 (binaire) |
| 03 | Fingerprinting étendu | Cloudflare Free | 12 détecteurs | 1.5 |
| 04 | Intégrité + challenges | Cloudflare Pro / DataDome passif | 22 détecteurs | 1.2 |
| 05 | Comportement + canvas | Cloudflare Business | 28 détecteurs | 1.0 |
| 06 | Corrélation | DataDome / PerimeterX | 30+ détecteurs | 0.7 |
| 07 | État de l'art | Cloudflare Enterprise Bot Management | tout + HTTP/2 + corrélation | 0.5 |

### Détail par niveau

#### Niveau 01 — Baseline

Inchangé. Site nu. Tout passe.

```yaml
fingerprinting: {actif: false}
```

#### Niveau 02 — Détection HTTP

Inchangé dans son principe. Bloque sur les signaux HTTP et TLS bruts.

```yaml
fingerprinting:
  actif: true
  bloquer: http
  detecteurs: ["regles-http", "tls"]
  seuil_score: 2.0
```

**Attrape** : requests, httpx, curl, wget, Go net/http, aiohttp.
**Passe** : tout navigateur réel ou Chromium piloté.

#### Niveau 03 — Fingerprinting étendu

Premier niveau avec JavaScript. Active les détecteurs de base qui vérifient les propriétés du
navigateur.

```yaml
fingerprinting:
  actif: true
  bloquer: tout
  detecteurs:
    - regles-http
    - tls
    - botd
    - regles-js
    - coherence
    - comportement
    - headless
    - chrome-apis
    - media-codecs
    - langues
    - css-media
    - permissions-etendu
  seuil_score: 1.5
```

**Attrape** : Playwright brut, Selenium brut, Puppeteer sans stealth.
**Passe** : Patchright, Camoufox, puppeteer-extra-stealth, UC.
**Equivalent** : Cloudflare Free (bot score basique).

#### Niveau 04 — Intégrité + challenges

Ajoute la vérification de l'intégrité des patches JavaScript. Les moteurs avec des patches
naïfs (toString mal fait, globales oubliées, stacks non filtrées) échouent.

```yaml
fingerprinting:
  actif: true
  bloquer: tout
  detecteurs:
    # Niveau 03 complet +
    - prototypes
    - integrite-proprietes
    - stack-trace
    - stack-getter
    - automation-globals
    - prototype-chain
    - enumerable-props
    - proxy-uadata
    - timing-precision
    - paint-timing
  seuil_score: 1.2
defi_js: {actif: true, difficulte: 14, lier_tls: false}
captcha: {actif: true}
waf: {mode: blocage, paranoia: 2, seuil: 5}
```

**Attrape** : puppeteer-extra-stealth (toString détecté), Patchright avec scripts d'injection
maladroits, SeleniumBase avec mauvaise configuration.
**Passe** : Patchright (patches propres), Camoufox (fork Firefox complet), moteur NOEZIA actuel.
**Equivalent** : Cloudflare Pro, DataDome en mode passif.

#### Niveau 05 — Comportement + canvas

Ajoute l'analyse comportementale fine et la vérification de cohérence approfondie. Un bot avec
des patches parfaits mais un comportement mécanique est détecté.

```yaml
fingerprinting:
  actif: true
  bloquer: tout
  detecteurs:
    # Niveau 04 complet +
    - coherence-profonde
    - coherence-environnement
    - entropie-interaction
    - scroll
    - canvas-empreinte
    - canvas-consistency
    - raf-timing
    - worker-consistency
  seuil_score: 1.0
defi_js: {actif: true, difficulte: 16, lier_tls: true}
captcha: {actif: true}
turnstile: {actif: true}
recaptcha: {actif: true}
waf: {mode: blocage, paranoia: 2, seuil: 4}
honeypots: {actif: false}
connexion: {actif: true, tentatives_max: 5}
```

**Attrape** : tout moteur sans simulation comportementale humaine réaliste. Même avec des
patches parfaits, un CV de délais souris < 0.15 est signalé. Les deltas rAF à 0 en headless
(sans `--use-gl=angle`) sont détectés. Les divergences main thread vs Worker sont fatales.
**Passe** : Camoufox (headed, avec interaction humaine simulée de bonne qualité), moteur
NOEZIA avec simulation comportementale calibrée.
**Equivalent** : Cloudflare Business, DataDome actif.

#### Niveau 06 — Corrélation

Ajoute la corrélation cross-session, le rate limiting par fingerprint, et les signaux réseau.

```yaml
fingerprinting:
  actif: true
  bloquer: tout
  detecteurs:
    # Niveau 05 complet +
    - connection-dynamic
    - webrtc
    - position-fenetre
    - correlation-session     # NOUVEAU
  seuil_score: 0.7
defi_js: {actif: true, difficulte: 18, lier_tls: true}
captcha: {actif: true}
turnstile: {actif: true}
recaptcha: {actif: true}
waf: {mode: blocage, paranoia: 3, seuil: 3}
honeypots: {actif: true}
connexion: {actif: true, tentatives_max: 3}
correlation:                 # NOUVEAU
  actif: true
  seuil_sessions: 5
  fenetre_minutes: 60
```

**Attrape** : bots qui recyclent le même fingerprint, rotation de fingerprints trop rapide,
volumes anormaux par fingerprint.
**Passe** : uniquement un moteur avec fingerprints uniques et réalistes par session, simulation
comportementale calibrée, et volume raisonnable.
**Equivalent** : DataDome, PerimeterX/HUMAN.

#### Niveau 07 — État de l'art (NOUVEAU)

Tout le niveau 06, plus HTTP/2 fingerprinting, enumeration de fonts, audio fingerprint, et
seuil le plus bas.

```yaml
fingerprinting:
  actif: true
  bloquer: tout
  detecteurs:
    # Niveau 06 complet +
    - http2                   # NOUVEAU
    - fonts                   # NOUVEAU
    - audio-fingerprint       # NOUVEAU
  seuil_score: 0.5
limitation: {debit: 1, rafale: 2}
defi_js: {actif: true, difficulte: 20, lier_tls: true}
captcha: {actif: true}
turnstile: {actif: true}
recaptcha: {actif: true}
waf: {mode: blocage, paranoia: 4, seuil: 2}
honeypots: {actif: true}
connexion: {actif: true, tentatives_max: 2}
correlation:
  actif: true
  seuil_sessions: 3
  fenetre_minutes: 30
```

**Exigences pour passer** :
- Empreinte TLS/HTTP2 cohérente avec le navigateur annoncé
- Fonts réalistes pour l'OS déclaré
- Audio fingerprint unique et cohérent avec le GPU/driver
- Comportement humain crédible (entropie, pauses, trajectoires)
- Aucun signal d'intégrité (patches invisibles)
- Aucune corrélation cross-session
- Volume < 1 req/s soutenu

**Equivalent** : Cloudflare Enterprise Bot Management avec Bot Fight Mode.

### Mapping vers les protections commerciales

| Protection commerciale | Niveau Arena le plus proche | Notes |
|----------------------|---------------------------|-------|
| Aucune (hébergement standard) | 01 | |
| CDN avec rate limit (AWS CloudFront) | 02 | Pas de détection JS |
| Cloudflare Free (bot score) | 03 | Challenge JS basique, BotD |
| Cloudflare Pro (WAF + JS challenge) | 04 | OWASP CRS, challenge JS, détection d'intégrité |
| Cloudflare Business (advanced bot) | 05 | Analyse comportementale, canvas |
| DataDome / PerimeterX | 06 | Corrélation multi-session, scoring |
| Cloudflare Enterprise Bot Management | 07 | HTTP/2, ML, corrélation complète |
| Akamai Bot Manager Premier | 07+ | Au-delà de ce qu'on peut reproduire localement |

---

## 6. Plan d'implémentation

### Etape 1 : Rendre les détecteurs configurables par niveau (~80 lignes)

**Fichiers** : `profils.py`, `gardien.py`, `profils.yaml`
**Impact** : fondation pour tout le reste

- Ajouter `detecteurs: list[str]` à `Fingerprinting` dans `profils.py`
- Modifier `suspicion()` dans `gardien.py` pour lire cette liste
- Mettre à jour `profils.yaml` avec les listes de détecteurs par niveau (niveaux 01-06)
- Tests : vérifier que le niveau 03 révisé consulte les 12 détecteurs

**Validation** : campagne `essai.yaml` — le moteur NOEZIA doit échouer au niveau 03 ou 04
révisé (il passe actuellement tous les niveaux).

**Estimation** : ~80 lignes Python + ~60 lignes YAML + ~30 lignes tests = **~170 lignes**

---

### Etape 2 : Score composite (~150 lignes)

**Fichiers** : `gardien.py` (nouvelle fonction), `profils.py` (nouveau champ), `profils.yaml`
**Impact** : remplace la logique binaire, réduit les faux positifs

- Ajouter `seuil_score: float` à `Fingerprinting`
- Implémenter `score_composite()` dans `gardien.py` ou un nouveau `scoring.py`
- Modifier `suspicion()` pour retourner le score en plus des motifs
- Modifier `controler()` pour comparer au seuil et décider blocage / CAPTCHA / passé
- Enregistrer le score dans `decisions` (nouveau champ ou dans les motifs JSON)

**Validation** : campagne avec Chrome humain de référence — le score doit rester sous le seuil.
Campagne avec Playwright brut — le score doit dépasser le seuil.

**Estimation** : ~150 lignes Python + ~20 lignes YAML + ~50 lignes tests = **~220 lignes**

---

### Etape 3 : Corrélation cross-session (~200 lignes)

**Fichiers** : `database.py` (migration), nouveau `correlation.py`, `gardien.py`, `profils.py`
**Impact** : détecte les bots à fingerprint constant

- Migration : table `empreintes_vues`
- Fonction `enregistrer_hash()` appelée en fin de passage
- Fonction `correlation_session()` qui retourne les données cross-session
- Enrichir `Observations` avec un champ `correlation`
- Nouveau détecteur `DetecteurCorrelationSession`
- Ajouter `correlation` au profil YAML (niveaux 06-07)

**Validation** : lancer 10 passages avec le même moteur/profil — à partir du 5e, le détecteur
doit signaler.

**Estimation** : ~200 lignes Python + ~30 lignes YAML + ~40 lignes tests = **~270 lignes**

---

### Etape 4 : Niveau 07 + profils YAML révisés (~40 lignes)

**Fichiers** : `profils.yaml`, documentation
**Impact** : les niveaux reflètent la progression réelle

- Écrire le profil complet du niveau 07
- Réviser les niveaux 03 à 06 avec les listes de détecteurs
- Mettre à jour la documentation (AGENTS.md, architecture.md)
- Ajuster les campagnes existantes

**Validation** : `uv run pytest -m "not integration"` passe ; `shadowlab moteurs etat` inchangé.

**Estimation** : ~40 lignes YAML + ~30 lignes doc = **~70 lignes**

---

### Etape 5 : Frontal HTTP/2 (~400 lignes)

**Fichiers** : `frontal.py` (refactoring majeur), `tls.py`, `database.py` (migration)
**Dépendance** : `pip install h2` (bibliothèque HTTP/2 frame-level)
**Impact** : le signal le plus différenciant, celui qui manque vs les WAF commerciaux

- Remplacer `set_alpn_protocols(["http/1.1"])` par `["h2", "http/1.1"]`
- Ajouter un parseur HTTP/2 dans le frontal (h2 state machine côté serveur)
- Extraire SETTINGS, pseudo-header order, WINDOW_UPDATE
- Stocker dans `observations_tls` (nouveau champ `h2_fingerprint`)
- Le relais vers Nginx reste en HTTP/1.1 (traduction h2 → h1)

**Validation** : Chrome via le frontal — le SETTINGS frame est capturé et correspond au
référentiel Chrome. curl brut — les SETTINGS diffèrent.

**Estimation** : ~400 lignes Python + ~30 lignes migration + ~60 lignes tests = **~490 lignes**

---

### Etape 6 : Détecteur HTTP/2 (~120 lignes)

**Fichiers** : `detection.py`, tests
**Dépendance** : étape 5

- Implémenter `DetecteurHttp2` avec le référentiel par navigateur
- Comparer SETTINGS + pseudo-order + WINDOW_UPDATE vs navigateur annoncé
- L'ajouter au registre et au niveau 07

**Validation** : campagne au niveau 07 — curl brut est détecté, Chrome natif passe.

**Estimation** : ~120 lignes Python + ~40 lignes tests = **~160 lignes**

---

### Etape 7 : Détecteur de fonts (~100 lignes JS + ~80 lignes Python)

**Fichiers** : `site/static/observateur.js`, `detection.py`
**Impact** : détecte les profils avec un OS déclaré et des fonts incompatibles

- Côté JS : énumérer les fonts disponibles (technique : mesurer le rendu de texte dans un
  canvas avec une liste de fonts connues, comparer au rendu de la police par défaut)
- Envoyer la liste de fonts détectées dans l'empreinte JS
- Côté Python : nouveau détecteur `DetecteurFonts` avec un référentiel par OS :
  - macOS : San Francisco, Helvetica Neue, Apple Color Emoji
  - Windows : Segoe UI, Calibri, Consolas
  - Linux : Liberation Sans, DejaVu Sans, Noto Sans

**Validation** : Chrome macOS passe (fonts macOS détectées). Un profil qui annonce macOS mais
n'a que les fonts Linux échoue.

**Estimation** : ~100 lignes JS + ~80 lignes Python + ~30 lignes tests = **~210 lignes**

---

### Etape 8 : Audio fingerprint + corrélation (~100 lignes JS + ~80 lignes Python)

**Fichiers** : `site/static/observateur.js`, `detection.py`, `correlation.py`
**Impact** : un fingerprint de plus pour la corrélation

- Côté JS : AudioContext → createOscillator → analyser → getFloatFrequencyData → hash
- Envoyer le hash dans l'empreinte JS
- Côté Python : stocker dans `empreintes_vues` (type = 'audio')
- Détecteur : vérifier cohérence avec le WebGL renderer (même GPU devrait donner le même
  audio fingerprint)

**Validation** : même test que la corrélation canvas, appliqué à l'audio.

**Estimation** : ~100 lignes JS + ~80 lignes Python + ~20 lignes tests = **~200 lignes**

---

### Etape 9 : Calibration et campagne de référence (~50 lignes)

**Fichiers** : nouvelle campagne YAML, documentation
**Impact** : validation empirique de tout le durcissement

- Campagne "matrice complète" : tous les moteurs × tous les niveaux révisés (01-07)
- Session humaine de référence (Chrome piloté manuellement) pour calibrer les seuils
- Ajuster les seuils de score si nécessaire
- Documenter les résultats dans `docs/resultats/`

**Validation** : le moteur NOEZIA échoue au niveau qu'on vise (05 ou 06). Chrome humain passe
tous les niveaux.

**Estimation** : ~50 lignes YAML + temps de campagne

---

### Etape 10 : Dashboard enrichi (~200 lignes)

**Fichiers** : `api.py`, `frontend/`
**Impact** : visualiser le score composite, les corrélations, les décisions par couche

- API : exposer le score composite dans `/api/experiences/.../progression`
- API : endpoint corrélation (`/api/correlation`)
- Frontend : afficher le score par détecteur dans la vue Passage
- Frontend : visualisation de la matrice niveaux × moteurs avec le score au lieu du binaire

**Estimation** : ~100 lignes Python (API) + ~100 lignes TypeScript (UI) = **~200 lignes**

---

### Récapitulatif

| # | Étape | Impact | Lignes estimées | Critère de validation |
|---|-------|--------|----------------|----------------------|
| 1 | Détecteurs configurables | Fondation | ~170 | NOEZIA échoue au niveau 03-04 |
| 2 | Score composite | Précision | ~220 | Chrome humain < seuil, Playwright > seuil |
| 3 | Corrélation cross-session | Anti-recycling | ~270 | 5e session identique signalée |
| 4 | Niveau 07 + profils révisés | Structure | ~70 | Tests passent |
| 5 | Frontal HTTP/2 | Signal fort | ~490 | SETTINGS Chrome capturés |
| 6 | Détecteur HTTP/2 | Différenciation | ~160 | curl détecté, Chrome passe |
| 7 | Fonts | Cohérence OS | ~210 | macOS → fonts macOS |
| 8 | Audio fingerprint | Corrélation | ~200 | Hash audio dans empreintes_vues |
| 9 | Calibration | Validation | ~50 | Matrice complète validée |
| 10 | Dashboard enrichi | Visibilité | ~200 | Score visible dans l'UI |
| **Total** | | | **~2010** | |

### Ordre d'exécution recommandé

```
Étape 1 (fondation) → Étape 2 (score) → Étape 4 (niveaux)
     ↓                       ↓
Étape 3 (corrélation)  Étape 5 (HTTP/2) → Étape 6 (détecteur)
     ↓                       ↓
Étape 7 (fonts)        Étape 8 (audio)
     ↓
Étape 9 (calibration) → Étape 10 (dashboard)
```

Les étapes 1-2-4 forment le socle minimal (le moteur NOEZIA doit échouer quelque part). Les
étapes 3-5-6 sont le coeur du durcissement. Les étapes 7-8-9-10 sont du polish.

---

## Annexe A : Référentiel rapide des 32+ détecteurs

| # | Nom | Famille | Signal | Actif gardien | Recommandé à partir de |
|---|-----|---------|--------|--------------|----------------------|
| 1 | `regles-http` | Transport | Fort | Oui | 02 |
| 2 | `tls` | Transport | Fort | Oui | 02 |
| 3 | `botd` | Empreinte | Moyen | Oui | 03 |
| 4 | `regles-js` | Empreinte | Fort | Oui | 03 |
| 5 | `coherence` | Cohérence | Fort | Oui | 03 |
| 6 | `comportement` | Comportement | Moyen | Oui | 03 |
| 7 | `headless` | Empreinte | Moyen | Non | 03 |
| 8 | `chrome-apis` | Empreinte | Moyen | Non | 03 |
| 9 | `media-codecs` | Empreinte | Moyen | Non | 03 |
| 10 | `langues` | Empreinte | Moyen | Non | 03 |
| 11 | `css-media` | Empreinte | Moyen | Non | 03 |
| 12 | `permissions-etendu` | Empreinte | Faible | Non | 03 |
| 13 | `prototypes` | Intégrité | Fort | Non | 04 |
| 14 | `integrite-proprietes` | Intégrité | Fort | Non | 04 |
| 15 | `stack-trace` | Intégrité | Fort | Non | 04 |
| 16 | `stack-getter` | Intégrité | Fort | Non | 04 |
| 17 | `automation-globals` | Intégrité | Fort | Non | 04 |
| 18 | `prototype-chain` | Intégrité | Moyen | Non | 04 |
| 19 | `enumerable-props` | Intégrité | Moyen | Non | 04 |
| 20 | `proxy-uadata` | Intégrité | Fort | Non | 04 |
| 21 | `timing-precision` | Intégrité | Faible | Non | 04 |
| 22 | `paint-timing` | Intégrité | Moyen | Non | 04 |
| 23 | `coherence-profonde` | Cohérence | Moyen | Non | 05 |
| 24 | `coherence-environnement` | Cohérence | Faible | Non | 05 |
| 25 | `entropie-interaction` | Comportement | Fort | Non | 05 |
| 26 | `scroll` | Comportement | Moyen | Non | 05 |
| 27 | `canvas-empreinte` | Cohérence | Moyen | Non | 05 |
| 28 | `canvas-consistency` | Cohérence | Fort | Non | 05 |
| 29 | `raf-timing` | Cohérence | Fort | Non | 05 |
| 30 | `worker-consistency` | Cohérence | Fort | Non | 05 |
| 31 | `connection-dynamic` | Empreinte | Faible | Non | 06 |
| 32 | `webrtc` | Comportement | Faible | Non | 06 |
| 33 | `position-fenetre` | Empreinte | Faible | Non | 06 |
| -- | `correlation-session` | Corrélation | Fort | Non | 06 (nouveau) |
| -- | `http2` | Transport | Fort | Non | 07 (nouveau) |
| -- | `fonts` | Cohérence | Moyen | Non | 07 (nouveau) |
| -- | `audio-fingerprint` | Cohérence | Moyen | Non | 07 (nouveau) |

## Annexe B : Formule du score composite (pseudo-code)

```python
COEFFICIENTS_FAMILLE = {
    "transport": 1.0,
    "empreinte": 0.7,
    "integrite": 1.2,
    "coherence": 0.8,
    "comportement": 1.0,
    "correlation": 1.5,
}

FAMILLE = {
    "regles-http": "transport",
    "tls": "transport",
    "http2": "transport",
    "botd": "empreinte",
    "regles-js": "empreinte",
    "headless": "empreinte",
    "chrome-apis": "empreinte",
    "media-codecs": "empreinte",
    "langues": "empreinte",
    "css-media": "empreinte",
    "permissions-etendu": "empreinte",
    "connection-dynamic": "empreinte",
    "position-fenetre": "empreinte",
    "prototypes": "integrite",
    "integrite-proprietes": "integrite",
    "stack-trace": "integrite",
    "stack-getter": "integrite",
    "automation-globals": "integrite",
    "prototype-chain": "integrite",
    "enumerable-props": "integrite",
    "proxy-uadata": "integrite",
    "timing-precision": "integrite",
    "paint-timing": "integrite",
    "coherence": "coherence",
    "coherence-profonde": "coherence",
    "coherence-environnement": "coherence",
    "canvas-empreinte": "coherence",
    "canvas-consistency": "coherence",
    "raf-timing": "coherence",
    "worker-consistency": "coherence",
    "fonts": "coherence",
    "audio-fingerprint": "coherence",
    "comportement": "comportement",
    "entropie-interaction": "comportement",
    "scroll": "comportement",
    "webrtc": "comportement",
    "correlation-session": "correlation",
}

def score_composite(classements: list[tuple[str, Classement]]) -> float:
    score = 0.0
    for nom, classement in classements:
        famille = FAMILLE.get(nom, "empreinte")
        coeff = COEFFICIENTS_FAMILLE.get(famille, 1.0)
        for signal in classement.signals:
            if signal.poids > 0:
                score += signal.poids * coeff
    return round(score, 3)

def decision(score: float, seuil_blocage: float, seuil_captcha: float | None) -> str:
    if score >= seuil_blocage:
        return "bloque"
    if seuil_captcha is not None and score >= seuil_captcha:
        return "captcha"
    return "passe"
```

## Annexe C : Ce que chaque moteur NOEZIA devra faire pour passer le niveau 07

1. **TLS** : ClientHello identique à Chrome (déjà le cas via Chromium réel)
2. **HTTP/2** : SETTINGS, pseudo-headers, WINDOW_UPDATE identiques à Chrome (nécessite que
   le frontal accepte h2 et que Chromium envoie ses settings natifs — c'est le cas par défaut)
3. **Patches JS invisibles** : aucun signal d'intégrité (toString natif, pas de globales,
   stacks propres). Le moteur NOEZIA utilise Playwright/Patchright : vérifier que les patches
   sont indétectables par les 10 détecteurs d'intégrité.
4. **Cohérence profonde** : écran, DPR, hwc, deviceMemory cohérents avec l'OS et le matériel
   annoncés. Le profil GPU Metal réel aide (pas de SwiftShader).
5. **Comportement humain** : simulation de mouvements souris avec entropie réaliste (CV > 0.15),
   pauses, trajectoires non linéaires, frappe clavier variée. Le moteur doit intégrer un
   générateur de comportement calibré sur des sessions humaines.
6. **Canvas/audio unique** : ne pas utiliser de bruit aléatoire (détectable par instabilité).
   Utiliser le rendu natif du GPU (si le profil est cohérent, le canvas est unique et stable).
7. **Fonts** : le profil doit avoir les fonts de l'OS déclaré. Sur macOS, Chromium a
   naturellement les fonts macOS.
8. **Pas de corrélation** : chaque session doit avoir un fingerprint distinct (IP, canvas,
   audio, profil). Si le même profil navigateur est utilisé, les hash vont se répéter.
   Solution : rotation de profils réalistes.
9. **Volume** : < 1 req/s soutenu, avec des pauses réalistes entre les pages.
10. **rAF** : deltas réalistes (16.67ms ± bruit). Nécessite `--use-gl=angle` ou GPU réel
    (le moteur NOEZIA utilise déjà GPU Metal).
