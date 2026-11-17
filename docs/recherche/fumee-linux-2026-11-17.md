# Essai de fumée Linux (étape 3.1) — 17/11/2026

Le moteur `noezia` a tourné pour la première fois sous Linux, dans un conteneur sans carte graphique, contre l'Arena.
**Toutes les campagnes de ce document sont dans la base du dossier de travail `fumee-linux`** (`outputs/shadowlab.sqlite3`
de ce dossier, numérotation propre : « campagne n° x » veut dire « campagne x de cette base », sans rapport avec les
numéros de la base du dossier principal). Les références du poste sont lues, en lecture seule, dans la base du dossier
principal : campagnes **97**, **100** et **132**.

Cette étape ne corrige pas le moteur : elle liste. Aucun fichier du moteur ni de l'Arena n'a été modifié.

## 1. Résultat en dix lignes

1. **Tout démarre** : 540 passages, 6 campagnes, 0 panne. Le moteur, le site, le frontal TLS, la pile Nginx + Coraza et un
   Chrome ou un Chromium tournent sous Linux, en arm64 natif comme en amd64 émulé (Rosetta).
2. Un **vrai Chrome n'existe pas pour Linux arm64** (`patchright install chrome` : « not supported on Linux Arm64 ») : l'identité
   native avec Chrome n'est possible qu'en amd64. Elle marche en amd64 émulé (Chrome 157.0.8103.78).
3. Le réglage par défaut (identité réécrite, sans écran) donne **les mêmes chiffres que sur le poste** : 15, 10, 10, 10, 0, 0 sur 15
   (campagnes 1 et 4 ; poste : campagne 97), avec la même cause. Rien de propre à Linux.
4. Avec un écran virtuel, le réglage par défaut passe **15 sur 15 aux six niveaux** (campagnes 2 et 5). Pas de référence du poste
   pour ce réglage : on ne peut pas dire si c'est identique.
5. En identité native, **le Chrome de Linux est moins bien passé que celui du poste** : 87 sur 90 en amd64 (campagne 6, trois blocages
   au niveau 06), 89 sur 90 en arm64 avec Chromium (campagne 3, un blocage au niveau 05) ; poste : 15 sur 15 à chaque niveau (campagne 132).
6. Cause des quatre blocages : le score composite, tiré par des signaux que le poste ne déclenche pas (`devices_vide`, `voices_vide`) plus
   des durées de page trop régulières (`duree_pages_reguliere`, jamais vu au poste dans la campagne 132).
7. **Pire incohérence : WebGL n'existe pas** dans un navigateur avec interface sur Linux sans carte graphique (0 passage sur 90 avec WebGL
   dans les quatre campagnes avec interface). Le masquage SwiftShader (D-50) suppose un repli qui n'a plus lieu avec Chrome 156 et 157.
   Aucun détecteur de l'Arena ne le relève.
8. L'image d'un serveur sans réglage donne aussi : fuseau UTC, langue en-US, 5 polices (15 au poste), aucun périphérique audio ou vidéo,
   fenêtre de 945 px sans gestionnaire de fenêtres. Ces écarts viennent de l'image autant que de Linux.
9. L'essai a **coûté 13 Go de disque** (8,2 Go de cache de construction + 4,6 Go d'image amd64, après effacement de l'image arm64), pas
   les 2 Go annoncés. Tout est rendu : images et cache sont revenus à leur niveau d'avant.
10. Une machine Linux d'OrbStack pourrait tenir lieu de serveur pour la 3.3, avec des limites (§ 8). **Non faite** : la consigne est arrivée pendant que le disque était sous le seuil,
    puis la coordination a interdit toute nouvelle construction ; je ne l'ai pas reprise ensuite (disque à 23 Gio en fin d'essai). À décider : la faire maintenant, ou non.

## 2. Ce qui a été monté, et pourquoi

```
conteneur « shadowlab-linux » (Ubuntu 24.04, arm64 ou amd64)       OrbStack, projet Docker « fumee-linux »
  campagne → moteur noezia → Chrome ou Chromium                      ┌──────────────────────────────┐
        │ https://localhost:8744                                      │ Nginx (127.0.0.1:8746 du poste) │
  frontal TLS (JA3/JA4) ── relais socat A ──────────────────────────▶│        ↓                       │
  site FastAPI (127.0.0.1:8745) ◀── relais socat B ◀─────────────────│ Coraza + OWASP CRS             │
  base SQLite (volume Docker)                                         └──────────────────────────────┘
```

- **Où tourne l'Arena** : le site, le frontal TLS, la campagne, la base et le moteur sont **dans le conteneur** ; seule la pile
  Nginx + Coraza reste sur OrbStack, sous un nom de projet et des ports à nous (8744 frontal, 8745 site, 8746 Nginx : libres, vérifiés
  contre `lsof` et `docker ps`). Raisons : la campagne crée le moteur dans son propre processus, donc elle doit tourner sous Linux ;
  la base SQLite est en mode WAL, donc elle ne se partage pas entre le Mac et Linux ; c'est la disposition de l'étape 3.3
  (l'Arena sur le même serveur que le moteur).
- **Le code de l'Arena n'a pas changé.** Il vise des adresses en dur (frontal → `127.0.0.1:<aval>`, Coraza → `host.docker.internal:<site>`) ;
  deux relais `socat` les satisfont (test préalable : `host.docker.internal` joint bien un port publié par un autre conteneur).
- **Périmètre respecté** : `SHADOWLAB_HOTES_AUTORISES=localhost,127.0.0.1` (mode strict). Le moteur ne voit que
  `https://localhost:8744` ; le relais est de l'infrastructure, pas une destination du moteur.
- **Niveau 06** : même convention que les campagnes de contrôle du poste (115, 132) : **sans corrélation** (`06scorr`,
  `configs/arena/profils-sans-correlation.yaml`, passé à la pile et au conteneur).
- Même plan que la 132 : 3 scénarios (`static_html`, `javascript_content`, `pagination`) × 5 répétitions = 15 passages par niveau,
  un à la fois ; niveaux 01 à 06 (la 132 n'a que 04 à 06).
- Image : `docker/linux/Dockerfile` (Ubuntu 24.04, `uv`, Python 3.12, Patchright 1.64.4, Chromium de Patchright 156.0.8078.4,
  Chrome 157.0.8103.78 en amd64, Xvfb à la demande). Pilotage : `scripts/fumee-linux.sh`.

## 3. Ce qui démarre et ce qui ne démarre pas

| Configuration | Démarre ? | Preuve |
|---|---|---|
| arm64, Chromium de Patchright, sans écran (`headless: true`) | oui | campagne 1 |
| arm64, Chromium avec interface sur Xvfb (`headless: false`) | oui | campagne 2 |
| arm64, identité native avec Chromium (pas de Chrome) | oui | campagne 3 |
| **arm64, `channel: chrome` (vrai Chrome)** | **non** | construction : « ERROR: not supported on Linux Arm64 » (Playwright) |
| amd64 émulé, Chromium, sans écran | oui | campagne 4 |
| amd64 émulé, Chromium avec interface sur Xvfb | oui | campagne 5 |
| amd64 émulé, identité native avec le vrai Chrome 157 | oui | campagne 6 |

L'émulation n'a fait échouer aucun passage : durées plus longues de 8 à 22 % qu'en arm64 sur les mêmes scénarios (campagnes 1 contre 4 et
2 contre 5, durée moyenne par scénario), aucun échec par délai (tous les échecs sont des décisions de détecteurs, lues dans `decisions`).
Le conteneur amd64 voit un processeur « VirtualApple @ 2.50GHz » dans `/proc/cpuinfo` (invisible pour une page).

## 4. Les campagnes (base du dossier `fumee-linux`, 15 passages par niveau)

**Où vivent les campagnes 1 à 6** : dans le dossier principal, `outputs/fumee-linux-2026-11-17.sqlite3` (copie de la base du dossier `fumee-linux`, faite par la session de coordination ; 48 Mo,
non versionnée). Les autres exemplaires : `outputs/shadowlab.sqlite3` du dossier `fumee-linux`, le volume Docker `fumee-linux-data` et le dossier de notes partagé. Les numéros « campagne 1 à 6 » de ce document sont ceux de cette base,
sans rapport avec la numérotation de `outputs/shadowlab.sqlite3` du dossier principal (où la campagne 132 est la référence du poste).

Les chiffres sont des passages réussis sur 15 (champ `success` de la base). Aux niveaux 05 et 06, des CAPTCHA en clés de test sont servis à
tout le monde : les passages sont étiquetés `captcha_test` (décisions `turnstile` et `recaptcha`, 15 passages par niveau et par fournisseur
atteint) et ne valent **jamais** comme résultat contre un vrai CAPTCHA.

| Campagne | Mode | 01 | 02 | 03 | 04 | 05 | 06 sans corr. | Durée |
|---|---|---|---|---|---|---|---|---|
| 1 | arm64, sans écran, réglage par défaut | 15 | 10 | 10 | 10 | 0 | 0 | 19 min |
| 2 | arm64, écran virtuel, réglage par défaut | 15 | 15 | 15 | 15 | 15 | 15 | 28 min |
| 3 | arm64, natif avec Chromium (pas de Chrome), écran virtuel | 15 | 15 | 15 | 15 | 14 | 15 | 27 min |
| 4 | amd64 émulé, sans écran, réglage par défaut | 15 | 10 | 10 | 10 | 0 | 0 | 21 min |
| 5 | amd64 émulé, écran virtuel, réglage par défaut | 15 | 15 | 15 | 15 | 15 | 15 | 33 min |
| 6 | amd64 émulé, natif avec Chrome 157, écran virtuel | 15 | 15 | 15 | 15 | 15 | 12 | 30 min |

Références du poste (base du dossier principal, lecture seule) :

| Référence du poste | Réglage | 01 | 02 | 03 | 04 | 05 | 06 sans corr. |
|---|---|---|---|---|---|---|---|
| campagne 97 (12/11, `noezia`) | défaut, sans écran, Chromium | 15 | 10 | 10 | 10 | 0 | 0 |
| campagne 100 (12/11, 30 passages par niveau) | natif, Chrome, écran | 30/30 | 30/30 | 30/30 | – | – | – |
| campagne 132 (16/11) | natif, Chrome 156, écran | – | – | – | 15 | 15 | 15 |

(La campagne 100 donne 30 sur 30 aux niveaux 01 à 03 ; la 97 s'arrête au 07, non repris ici.)

**Les trois blocages de la campagne 6 et celui de la 3.**
- Campagne 6, niveau 06 sans corrélation, scénario `pagination`, répétitions 1, 4 et 5 : décision `composite-differe`, score composite 0,61 pour un
  seuil de 0,5 ; signaux `duree_pages_reguliere` (CV des durées de page 0,12, 0,18 et 0,08, pour un seuil de 0,2) et `devices_vide`.
- Campagne 3, niveau 05, `pagination`, répétition 1 : score 0,89 pour un seuil de 0,6 ; signaux `duree_pages_reguliere` (CV 0,18), `voices_vide`
  et `devices_vide`. Un autre passage du même niveau a reçu la même détection différée (0,89) mais avait déjà fini : il compte réussi.
- Seuils composites : 03 = 1,5 ; 04 = 0,8 ; 05 = 0,6 ; 06 = 0,5 ; 07 = 0,3 (`configs/arena/profils.yaml`). **Le niveau 07 n'a pas été mesuré** (hors
  objectif) : avec un seuil de 0,3, ces signaux de Linux pèseraient plus.

## 5. Comparaison avec le poste, détecteur par détecteur

Outil : `scripts/fumee-linux-comparer.py` (signaux vus d'un côté seulement, écart d'au moins 20 points de proportion ; propriétés brutes de
l'empreinte). **Un signal dont le détecteur n'a pas la même version des deux côtés n'est pas imputable à Linux** : le script le dit.

### 5.1 Identité réécrite, sans écran (campagnes 1 et 4 contre la 97)

Identique, niveau par niveau : mêmes issues, même cause (`headless_dans_une_requete` : « HeadlessChrome » dans les en-têtes d'une requête sur 11 ou 13), mêmes
nombres (5 blocages sur 15 aux niveaux 02 à 04, 15 sur 15 aux niveaux 05 et 06). Seul signal différent : `correlation-session` (2.1 ici,
1 dans la 97) : version différente, donc **rien d'imputable à Linux**. Ce réglage échoue de la même façon sur Mac et sur Linux : ce n'est pas un défaut de Linux.

### 5.2 Identité native (campagnes 3 et 6 contre la 132 pour 04 à 06, la 100 pour 01 à 03)

Signaux d'un seul côté, **même version de détecteur** (donc imputables à Linux ou à l'image) :

| Signal | Campagne 3 (arm64, Chromium) | Campagne 6 (amd64, Chrome 157) | Poste (132 et 100) |
|---|---|---|---|
| `headless` / `devices_vide` | 15/15 à chaque niveau | 15/15 à chaque niveau | 0 |
| `headless` / `voices_vide` | 15/15 à chaque niveau | 0 (19 voix) | 0 (1 passage sur 30 à la 100, niveau 01) |
| `duree_pages_reguliere` (cité par la détection `composite-differe`) | 2 passages (1 bloqué, 1 réussi) | 3 passages (3 bloqués) | 0 (campagne 132) |

Autres écarts, **version de détecteur différente** (non imputables) : `correlation-session` (`empreinte_sans_memoire`, `debit_empreinte` : conséquence
de l'historique de ma base, où 540 passages de quelques empreintes se succèdent ; `debit_empreinte` au niveau 06 : 15/15 contre 1/15 à la 132,
alors que la version est la même, 2.1 — la règle est écartée au profil `06scorr`) ; `scroll` / `entropie-interaction` `sans_releve` (versions 1.1 et 1.2 contre 1 et 1.1).

### 5.3 Identité réécrite, avec écran virtuel (campagnes 2 et 5)

**Pas de référence du poste** pour ce réglage (aucune campagne du poste avec `headless: false` et profil réécrit) : 15 sur 15 aux six niveaux, rien de plus à
affirmer. Pas de campagne du poste lancée pour l'occasion : elle aurait ouvert des fenêtres de Chrome sur l'écran d'Ethan pendant 30 minutes.

### 5.4 arm64 contre amd64, même Chromium (campagnes 2 et 5, niveau 04)

Les dix constantes mathématiques (`math_constants.*`) et les codecs sont **identiques** entre arm64 et amd64 (V8 les calcule lui-même) : ils ne distinguent pas l'architecture. L'**AudioContext**, lui, la
distingue : somme 124,043475 sur arm64, 124,043476 sur amd64 sous Rosetta, hachages différents. En identité native (sans bruit du moteur), la valeur est (124,043475 ; hachage 2136325374) sur les quatre séries arm64 — Chrome du Mac
(campagnes 132, 100 et 97 du poste) et Chromium arm64 du conteneur (campagne 3) — et (124,043476 ; 538831359) pour le Chrome 157 amd64 de la campagne 6. L'écart suit donc l'architecture, **mêlée à la version**
(Chromium 156 contre Chrome 157) : les deux ne sont pas séparées ici. En identité réécrite, le bruit audio du moteur change le dernier chiffre d'un profil à l'autre (campagnes 1, 2, 4, 5) et masque cet écart. Aucun détecteur de l'Arena
ne compare ces valeurs. Données : `fumee-linux-2026-11-17-donnees/comparaisons/cmp-2-vs-5-arm64-amd64.md`.

## 6. Les incohérences, de la plus grave à la moins grave

« Grave » veut dire : ce qu'une vraie protection verrait, et ce qui a déjà coûté un passage. Preuve : numéro de campagne de la base `fumee-linux`.

1. **WebGL absent dans tout navigateur avec interface** (campagnes 2, 3, 5, 6 : `webgl.disponible` faux sur 90 empreintes sur 90 dans chacune ;
   sonde : `getContext('webgl')` et `'webgl2'` rendent `null`, WebGPU sans adaptateur, Chrome 157 comme Chromium 156). Sans interface (headless shell, campagnes
   1 et 4) WebGL existe, avec SwiftShader (sonde : « ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero)…) », 35 extensions, texture max 8192,
   SUBPIXEL_BITS 4), et c'est ce que D-50 masque (90 empreintes sur 90 des campagnes 1 et 4 annoncent la carte d'un profil — Mesa AMD ou Intel, ANGLE NVIDIA — aucune ne montre SwiftShader). **D-50 suppose un repli sur SwiftShader qui n'a pas lieu
   avec une interface** : un profil qui annonce une carte NVIDIA, AMD ou Intel (D-51) sans WebGL est contradictoire. Aucun détecteur de l'Arena ne le relève
   (aucun blocage ne s'y rattache). Un navigateur de bureau sans WebGL est une rareté. Constat mesuré avec les drapeaux par défaut du moteur et de Patchright ; le drapeau `--enable-unsafe-swiftshader` n'a **pas été essayé**.
2. **`devices_vide` : aucun périphérique audio ou vidéo** (identité native, campagnes 3 et 6 : 15/15 à chaque niveau, 0 au poste, même version 1.1).
   C'est ce signal qui a fait basculer **trois blocages sur quatre** (§ 4) : à lui seul il ne bloque pas, mais il laisse moins de marge au composite.
   Le profil réécrit l'invente (`audioinput`, `audiooutput`, `videoinput`) : il ne se déclenche pas en identité réécrite.
3. **`voices_vide` : aucune voix de synthèse avec le Chromium de Patchright** (campagne 3 : 0 voix, 15/15 à chaque niveau ; sonde Chromium : 0 voix) alors
   que **Chrome 157 en a 19** (campagne 6, sonde). La différence vient du navigateur, pas de Linux. Il faut un vrai Chrome pour avoir des voix.
4. **Durées de page trop régulières dans `pagination`** (`duree_pages_reguliere`, CV de 0,08 à 0,18 pour un seuil de 0,2) : 5 passages touchés dont 4 bloqués
   (campagnes 3 et 6), jamais vu à la campagne 132 du poste. Sur les passages réussis, la durée de `pagination` est la même qu'au poste aux niveaux 04 et 05 (30,8 s contre 31,6 s ; 44,3 s contre 44,4 s) : le rythme moyen n'explique donc rien. **Cause non établie** : ce n'est pas l'émulation (le signal apparaît aussi en arm64 natif, campagne 3) ; à chercher dans l'interaction
   (fenêtre sans gestionnaire de fenêtres, écran virtuel) ou dans les durées de chargement.
5. **Fuseau UTC et langue en-US en identité native** (campagnes 3 et 6 ; sonde) contre Europe/Paris et fr-FR au poste. Écart de l'image (`TZ` et `LANG` non
   réglés), pas de Linux. Les profils réécrits imposent leur fuseau et leur langue (campagne 2 : `America/Chicago` avec `fr-FR`, une paire contradictoire
   propre au générateur de profils, pas à Linux).
6. **Polices** : 5 détectées au lieu de 15 au poste (campagnes 2 à 6 : Arial, Helvetica, Times New Roman, Courier New, Liberation Mono — les alias
   métriques de Liberation ; `polices_os_manquantes` ne se déclenche pas pour un profil Linux). Écart de l'image : paquets de polices de `patchright install-deps`.
7. **Écran et fenêtre** : Xvfb 1920×1080 avec, sans gestionnaire de fenêtres, une fenêtre de 945 px de large à `screenX = screenY = 10`, largeur extérieure
   égale à la largeur intérieure (campagne 6 ; sonde). Pas de blocage constaté. (L'écran de 800×600 sans interface est le même au poste : pas imputable à Linux.)
8. **Architecture annoncée contre architecture réelle.** Les profils Linux du moteur ne déclarent que `x86_64` (`profils/generateur.py`), et l'en-tête
   `sec-ch-ua-arch` est forcé à `"x86"` pour tout profil non macOS (`moteur.py`). Sur un conteneur **arm64**, la réalité est `aarch64`. **La sonde n'a pas pu lire l'architecture sur arm64** : l'image
   arm64 a été effacée avant la sonde (disque). **Observé indirectement** : l'AudioContext donne une valeur différente sur arm64 et sur amd64 (§ 5.4), donc la machine arm64 se lit dans un calcul que le profil réécrit ne masque pas (il ne fait que le bruiter). À savoir : Chrome réduit son User-Agent, donc le User-Agent et `navigator.platform` d'un Chromium arm64 natif disent
   déjà « Linux x86_64 » (campagne 3) ; seul `userAgentData.getHighEntropyValues().architecture` donnerait « arm », et l'Arena ne le collecte pas. Sous
   Rosetta (amd64), la page voit `x86` (sonde) : pas d'écart. Sur un vrai serveur x86_64, ce point disparaît.
9. **Ressources déclarées** : `hardwareConcurrency` = 18 (les cœurs de la machine virtuelle) alors que le conteneur est limité à 6 processeurs ; `deviceMemory`
   = 16 (campagnes 3 et 6) contre 32 au poste. Pas de blocage.
10. **Divers propres à Linux, sans effet constaté** : `domrect_fingerprint.has_subpixel` faux, `apis.bluetooth` et `apis.share` faux, 2 candidats WebRTC au lieu de 4,
    échantillonnage audio 44 100 Hz au lieu de 48 000 (sonde).
11. **Hors Linux** (déjà connu, noté pour ne pas l'imputer à Linux) : le profil réécrit annonce Chrome 129 à 132 alors que le navigateur est en 156 ou 157 ; Chrome 157 (Linux) contre 156 (poste) change les marques
    de `userAgentData` (« Not-A.Brand » 99 contre « Not:A-Brand » 8).

## 7. Ce que montre la sonde du navigateur réel (sans le moteur)

`scripts/fumee-linux-sonde.py` lance Chrome ou Chromium tel quel devant une page `http://localhost` et note ce qu'une page peut lire. JSON dans
`outputs/fumee-linux/sondes/` (non versionné) : `amd64-ecran-chrome`, `amd64-sans-ecran-chrome`, `amd64-ecran-chromium`, `amd64-sans-ecran-chromium`,
`poste-ecran-chrome`, `poste-sans-ecran-chrome` (Chrome 156.0.8078.80 du poste), **versionnés** avec les comparaisons dans `fumee-linux-2026-11-17-donnees/` (sondes/, comparaisons/). Lancées le 17/11 entre les campagnes. **Aucune sonde arm64** (image effacée).

| | poste (Chrome 156, arm64) | amd64 Chrome 157 avec écran | amd64 Chromium 156 avec écran | amd64 Chrome 157 sans écran |
|---|---|---|---|---|
| WebGL | Apple M5 Pro, Metal, 39 extensions | **absent** | **absent** | SwiftShader, 35 extensions |
| WebGPU | adaptateur Apple | présent, **aucun adaptateur** | idem | idem |
| Voix de synthèse | 19 | 19 | **0** | 19 |
| Périphériques | audio entrée et sortie | **aucun** | **aucun** | **aucun** |
| Fuseau, langue | Europe/Paris, fr | **UTC, en-US** | **UTC, en-US** | **UTC, en-US** |
| Écran | 1680×1050 (800×600 sans interface) | 1920×1080 (Xvfb) | idem | 800×600 (comme le poste sans interface) |
| `userAgentData.architecture` | arm | x86 | x86 | x86 |
| User-Agent | … Chrome/156 | … Chrome/157 | … Chrome/156 | **HeadlessChrome/157** |

Les six JSON contiennent un champ `polices` vide partout (poste compris) : la mesure était fausse, elle est retirée du script ; les polices viennent de l'empreinte du moteur (`font_fingerprint`).

## 8. Ce qu'OrbStack permet sur ce poste (lu avec `orbctl`, rien créé)

- OrbStack 2.2.5 ; machine virtuelle de Docker à 18 cœurs et 16 Gio ; Rosetta activé. Aucune machine Linux n'existe (`orbctl list` vide).
- `orbctl create` : architectures **arm64 et amd64** ; Ubuntu 22.04, 24.04, 25.10, 26.04, Debian 11 à 14, Fedora, Alma, Rocky, etc. ; limites par machine
  (`--cpus`, `--memory`, `--disk`), machine isolée (`--isolated`), cloud-init (`--user-data`).
- Vérifié : un **conteneur** amd64 démarre et le moteur y tourne (campagnes 4 à 6) ; Chrome 157 s'y installe.
- **Non fait** (consigne arrivée disque sous le seuil, puis interdiction de construire, puis non reprise) : Chrome dans une machine amd64 (probable : même Rosetta), Docker dans une
  machine, et tout ce qui suit.
- **Pour la 3.3** : une machine amd64 aurait l'avantage d'être « un serveur » (systemd, apt, Docker dans la machine) et ferait disparaître mes deux relais : l'Arena et le moteur seraient
  dans la même machine, comme sur le vrai serveur. Limites probables : même noyau et même émulation que les conteneurs (donc les mêmes résultats que ci-dessus : WebGL absent, périphériques vides,
  processeur « VirtualApple »), disque pris sur le même volume du Mac, et le poste n'est pas un x86 réel : l'écart « ≤ 5 points avec le poste » de la 3.3 mesurera aussi l'émulation.

## 9. Coût disque réel (à retenir pour la suite du palier 3)

Estimé : 2 Gio au pic. **Mesuré : environ 13 Go**, et le disque du poste était déjà serré.

| Poste de dépense | Taille |
|---|---|
| image arm64 (Ubuntu 24.04, venv Python, Chromium, Xvfb) | 3,55 Go affichés par Docker |
| image amd64 (idem + Chrome 157) | 4,6 Go (images : 28,78 → 33,36 Go) |
| cache de construction (deux constructions) | 8,2 Go (2,5 → 10,5 Go), dont 5,7 récupérables |
| base et sorties de l'essai | 50 Mo (SQLite) + rapports |

Rendu en fin d'essai : image amd64 effacée, pile arrêtée, 29 enregistrements de cache effacés un par un par leur identifiant (ceux d'avant n'ont pas été touchés) ; images
28,81 Go et cache 2,63 Go, soit le niveau d'avant. Le volume Docker `fumee-linux-data` (la base vivante, 50 Mo) est gardé. **Un constat** : la mesure `df` a peu bougé juste après l'effacement du cache (19 Gio avant et après) ; cause non établie (OrbStack qui rend l'espace avec retard, ou d'autres projets qui écrivaient au même moment). Pendant l'essai le disque libre est passé de 22 à 14 Gio ; une partie venait d'autres projets du poste.

## 10. Composition de l'image : ce qui est de Linux, ce qui est de l'image

Image volontairement ordinaire (un serveur sans réglage) : Ubuntu 24.04, aucun GPU, aucun gestionnaire de fenêtres, polices de `patchright install-deps`
(`fonts-liberation`, `fonts-freefont-ttf`, `fonts-noto-color-emoji`, `fonts-ipafont-*`, `fonts-wqy-zenhei`, `fonts-tlwg-loma`, `fonts-unifont`, `xfonts-*`), fuseau UTC, langue `C.UTF-8`, Xvfb
1920×1080×24 seulement pour les passages « avec écran ». **Ce qui vient de l'image** (réglable) : fuseau, langue, polices, taille d'écran, fenêtre sans gestionnaire,
absence de périphériques simulés. **Ce qui vient de Linux sans GPU** : pas de WebGL avec interface (drapeaux par défaut), SwiftShader sans interface. **Non essayé** : `--enable-unsafe-swiftshader`, que la note `chrome-interface-serveur-linux-2026-11-12.md` donne à mesurer ; on ne sait donc pas si ce drapeau rendrait WebGL avec interface.

## 11. Non vérifié

- Aucun vrai serveur Linux x86_64 : tout est un conteneur sur Mac (arm64 natif, ou amd64 sous Rosetta). Les durées, le processeur et le comportement de la mémoire ne valent pas pour un serveur.
- L'architecture réelle `aarch64` face à l'annonce `x86_64` : lue seulement indirectement (AudioContext, § 5.4), jamais directement (image arm64 effacée avant la sonde).
- `--enable-unsafe-swiftshader` : non essayé (WebGL avec interface sans GPU reste inexpliqué).
- La base de l'essai : la copie `outputs/shadowlab.sqlite3` du dossier `fumee-linux` et le volume Docker `fumee-linux-data` ; une copie est aussi dans le dossier de notes partagé des sessions.
- Aucune référence du poste pour l'identité réécrite avec écran (campagnes 2 et 5) ni pour l'identité native avec Chromium (campagne 3, comparée à un Chrome 156).
- Chrome 157 (Linux) contre Chrome 156 (poste) : la différence de version est mêlée aux écarts.
- Niveau 07 non mesuré ; 15 passages par niveau (pas 30), un seul passage par cellule, un seul poste ; CAPTCHA en clés de test aux niveaux 05 et 06.
- Cause de la régularité des durées de page (`duree_pages_reguliere`) : non établie.
- Aucune machine Linux d'OrbStack créée ; Docker dans une machine : non essayé.
- Aucun humain : ces campagnes ne disent rien sur la façon dont un humain sur Linux serait traité (aucune session humaine sous Linux).

## 12. Refaire l'essai

```bash
scripts/fumee-linux.sh disque                          # espace libre : arrêt sous 20 Gio ; prévoir environ 13 Go
scripts/fumee-linux.sh construire arm64                # ou amd64 ; une image à la fois
scripts/fumee-linux.sh pile                            # configurations + pile Nginx/Coraza du projet fumee-linux (8746)
scripts/fumee-linux.sh lancer arm64 sans-ecran configs/experiments/fumee-linux-sans-ecran.yaml
scripts/fumee-linux.sh lancer arm64 ecran configs/experiments/fumee-linux-ecran-virtuel.yaml
scripts/fumee-linux.sh lancer amd64 ecran configs/experiments/fumee-linux-natif.yaml           # Chrome 157 : amd64 seulement
scripts/fumee-linux.sh sauvegarder                     # copie la base du volume vers outputs/shadowlab.sqlite3 (celle de l'essai du 17/11 : outputs/fumee-linux-2026-11-17.sqlite3 du dossier principal)
python3 scripts/fumee-linux-comparer.py --linux outputs/fumee-linux-2026-11-17.sqlite3 --linux-campagne 6 --linux-label noezia-natif \
  --poste ~/dev/noezia-shadowlab/outputs/shadowlab.sqlite3 --poste-campagne 132 --poste-label noezia-natif --protections 04 05 06scorr
scripts/fumee-linux.sh arreter && scripts/fumee-linux.sh retirer amd64                      # rendre la place
```

Les quatre fichiers de campagne : `configs/experiments/fumee-linux-{sans-ecran,ecran-virtuel,natif,natif-chromium}.yaml`.
