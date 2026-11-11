---
permalink: noezia-shadowlab/brainstorm-arena-durcie-2026
title: brainstorm-arena-durcie-2026
type: note
---

# Plan de durcissement Arena — 10 novembre 2026

*Plan en 3 itérations pour faire de l'Arena un adversaire crédible.*

---

## Le problème en une phrase

`gardien.py` hardcode 6 détecteurs dans `REGLES_REQUETE` + `REGLES_JAVASCRIPT`. Les 26 autres collectent des signaux mais ne déclenchent jamais de blocage. Le moteur NOEZIA (et tous les moteurs anti-détection) passent les 6 niveaux parce que l'adversaire est trop faible.

## Mécanisme technique actuel

```python
# gardien.py, lignes 40-41
REGLES_REQUETE = ("regles-http", "tls")
REGLES_JAVASCRIPT = ("botd", "regles-js", "coherence", "comportement")
```

La fonction `suspicion()` (ligne 105) itère uniquement sur ces 6 noms. Le profil Arena (`profils.yaml`) a un champ `fingerprinting.exclure` qui peut en retirer, mais AUCUN mécanisme n'en ajoute.

## Itération 1 — Activer les détecteurs existants par niveau (~2 jours)

### Changement principal

Remplacer les constantes hardcodées par une **liste par niveau**, définie dans `profils.yaml`.

**`profils.yaml`** — Ajouter un champ `detecteurs_actifs` par niveau :

| Niveau | Détecteurs ajoutés (en plus des 6 de base) |
|--------|---------------------------------------------|
| 01 | Aucun (baseline) |
| 02 | `regles-http`, `tls` (HTTP seul, comme aujourd'hui) |
| 03 | + `prototypes`, `coherence-profonde`, `headless`, `chrome-apis`, `langues`, `media-codecs` |
| 04 | + `integrite-proprietes`, `stack-trace`, `stack-getter`, `automation-globals`, `css-media`, `prototype-chain`, `enumerable-props`, `proxy-uadata` |
| 05 | + `entropie-interaction`, `scroll`, `canvas-empreinte`, `canvas-consistency`, `raf-timing`, `worker-consistency`, `paint-timing`, `timing-precision` |
| 06 | + `connection-dynamic`, `permissions-etendu`, `position-fenetre`, `webrtc`, `coherence-environnement` |

### Fichiers à modifier

1. **`src/shadowlab/arena/profils.py`** — Ajouter `detecteurs_actifs: list[str]` au modèle `Fingerprinting` (ou nouveau champ `Profil`). Valeur par défaut = les 6 actuels.

2. **`src/shadowlab/site/gardien.py`** — Modifier `suspicion()` :
   - Lire la liste de détecteurs depuis le profil Arena du sceau
   - Remplacer `REGLES_REQUETE` + `REGLES_JAVASCRIPT` par cette liste
   - Garder la logique d'exclusion existante (`exclure`)

3. **`configs/arena/profils.yaml`** — Ajouter les listes pour chaque niveau.

### Impact attendu

- **Niveau 03 révisé** : Playwright brut et Selenium brut vont échouer (détection `prototypes`, `headless`)
- **Niveau 04 révisé** : puppeteer-extra-stealth va échouer (`integrite-proprietes`, `stack-trace`)
- **Niveau 05 révisé** : **NOEZIA va probablement échouer** (`entropie-interaction` analyse la qualité des mouvements, `canvas-consistency` détecte le bruit non-déterministe, `worker-consistency` vérifie les patches dans les workers)
- **Niveau 06 révisé** : Même Camoufox pourrait avoir des difficultés (`position-fenetre`, `webrtc`)

### Effort : ~16h

- Modèle Pydantic : 2h
- Modification gardien.py : 4h (avec tests)
- Mise à jour profils.yaml : 2h
- Calibration (ajuster les seuils pour que le niveau 01-02 reste passable) : 4h
- Tests + campagne de validation : 4h

---

## Itération 2 — Score composite et corrélation cross-session (~3 jours)

### Changement principal

Remplacer la logique binaire (`automatise` → bloqué, sinon → passe) par un **score composite pondéré** et une **corrélation cross-session**.

### Score composite

Au lieu de : "si UN détecteur dit `automatise`, bloquer", faire : "additionner les poids de tous les signaux de tous les détecteurs actifs, bloquer si le score dépasse un seuil."

Ça permet :
- Un signal faible isolé ne bloque pas, mais 5 signaux faibles ensemble si
- Chaque niveau a son propre seuil (03 : libéral, 06 : strict)
- Les détecteurs gardent leur logique interne mais c'est le **gardien** qui décide

### Corrélation cross-session

Nouveau détecteur `DetecteurCorrelation` :
- Table SQLite : `fingerprints_vus(hash_canvas TEXT, hash_webgl TEXT, ua TEXT, session_count INT, last_seen TIMESTAMP)`
- Si un fingerprint (combiné canvas+webgl+UA) est vu > N fois sur des sessions différentes → signal fort
- Seuil configurable par niveau (N=100 pour niveau 03, N=5 pour niveau 06)

### Fichiers à créer/modifier

1. **`src/shadowlab/site/gardien.py`** — Nouvelle logique de score dans `suspicion()` : appeler TOUS les détecteurs du niveau, sommer les poids, comparer au seuil du profil
2. **`src/shadowlab/detection.py`** — Nouveau `DetecteurCorrelation` (~150 lignes)
3. **`src/shadowlab/database.py`** — Nouvelle table + migration pour les fingerprints vus
4. **`configs/arena/profils.yaml`** — Ajouter `seuil_composite` par niveau

### Impact attendu

- Les moteurs qui passent chaque détecteur de justesse vont se faire attraper par l'accumulation
- Les moteurs qui réutilisent le même profil vont se faire attraper par la corrélation
- NOEZIA avec ses 18 profils va tenir un moment, mais pas indéfiniment

### Effort : ~24h

---

## Itération 3 — Détecteur HTTP/2 + niveau 07 (~5 jours)

### Changement principal

Nouveau détecteur `DetecteurHTTP2` qui analyse l'empreinte HTTP/2 du client. C'est le signal le plus difficile à spoofer (seul curl-cffi le fait correctement).

### Signaux HTTP/2 à capturer

1. **SETTINGS frame** : ordre et valeurs des paramètres
2. **WINDOW_UPDATE** initial
3. **Pseudo-headers** : ordre (`:method, :authority, :scheme, :path` = Chrome)
4. **PRIORITY frames** : Chrome les envoie, curl pas

### Architecture

Le frontal TLS (`arena/tls.py`) relève déjà le JA4. Il faut ajouter :
- Capture du SETTINGS frame à la connexion HTTP/2 (dans le handshake)
- Nouveau header interne `X-ShadowLab-H2` vers le backend
- Détecteur Python qui compare aux profils connus (Chrome, Firefox, Safari, curl, Go, Python)

### Niveau 07 (nouveau)

Tout le niveau 06 + HTTP/2 + `DetecteurCorrelation` strict (N=3) + WAF paranoia 4 seuil 2.

Pour passer le niveau 07, un moteur doit :
- Avoir un ClientHello TLS cohérent avec son UA
- Avoir des SETTINGS HTTP/2 cohérents avec le navigateur annoncé
- Avoir un fingerprint navigateur unique et cohérent
- Avoir un comportement qui passe l'analyse d'entropie
- Ne pas réutiliser un fingerprint vu trop souvent

### Fichiers

1. **`src/shadowlab/arena/tls.py`** — Capture HTTP/2 SETTINGS (~100 lignes)
2. **`src/shadowlab/arena/frontal.py`** — Nouveau header interne
3. **`src/shadowlab/detection.py`** — `DetecteurHTTP2` (~200 lignes)
4. **`configs/arena/profils.yaml`** — Niveau 07
5. **`docker/`** — Mise à jour de la pile pour supporter la capture HTTP/2

### Impact attendu

- Seul curl-cffi (et les outils qui impersonatent le HTTP/2) passeront la couche HTTP/2
- NOEZIA devra contrôler ses settings HTTP/2 via Patchright ou un proxy
- C'est le signal qui rapproche le plus l'Arena des WAF commerciaux

### Effort : ~40h (partie frontal TLS = le plus complexe)

---

## Résumé des priorités

| # | Action | Effort | Impact | Prérequis |
|---|--------|--------|--------|-----------|
| 1 | Activer détecteurs par niveau | 2j | Le moteur échoue dès niveau 03-04 | Rien |
| 2 | Score composite + corrélation | 3j | Accumulation de signaux faibles | #1 |
| 3 | HTTP/2 fingerprint + niveau 07 | 5j | Signal impossible à contourner sans effort | #1, #2 |

**Total : ~10 jours de travail pour une Arena crédible.**