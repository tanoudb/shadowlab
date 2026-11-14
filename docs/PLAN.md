# Plan NOEZIA — plan unique

Mis à jour : 11/11/2026 (soir). **Seul plan de travail du projet.** Objectif validé par Ethan (D-54).
Il remplace, comme feuille de route, `notes/ia/brainstorm-synthese-2026.md` et
`docs/superpowers/specs/2026-11-10-synthese-brainstorming.md` (gardés comme réservoir d'idées).
Détail des constats, avec fichiers et lignes : `notes/ia/analyse-paliers-2026-11-11.md`.
Il se met à jour en fin de chaque session (§ 8).

## 1. Objectif (validé le 11/11/2026, D-54)

Le produit est le **moteur de scraping NOEZIA**. ShadowLab est le laboratoire qui le mesure.

> NOEZIA v1 : un moteur de récolte généraliste qui, lancé depuis un serveur Linux, mène un long travail
> sur un site protégé sans se faire bannir, et rapporte des données complètes et exactes.

Le moteur n'est pas fait pour un site précis. Il se prouve par des mesures, sur des cibles **à nous**
(site vitrine factice, tor-i).

| Qualité | Preuve | Seuil |
|---------|--------|-------|
| Récolte | Sur le site vitrine, dont on connaît le contenu exact | ≥ 99 % des pages récupérées, ≥ 99 % des champs exacts |
| Discrétion | Contre l'Arena calibrée sur des humains (niveaux 01 à 06), puis depuis un serveur Linux contre Cloudflare sur un domaine à nous | ≥ 90 % de passages réussis |
| Endurance — une identité | Un seul compte connecté (cas d'un service payant ou d'un compte personnel) et suivi régulier d'un site, contre une Arena qui bannit | Zéro bannissement sur 7 jours ; le moteur s'arrête seul au premier signe d'alerte |
| Endurance — plusieurs identités | Volume : 10 000 pages en 3 jours, réparties sur des identités impossibles à relier | Le travail va au bout, moins de 10 % des identités perdues |
| Livrable | Sur `master`, documenté | Un clone neuf, `uv sync`, une commande → une récolte |

Les seuils sont des **choix de Claude** (Ethan n'avait pas de chiffre en tête) : ils se recalent après les
premières mesures, et tout recalage est noté ici.

Comment on compte (choix de Claude, à vérifier par Ethan) :
- Un passage est **réussi** s'il rapporte les données attendues sans être bloqué ni classé « automatisé »
  par l'Arena calibrée.
- Discrétion : ≥ 90 % **à chaque niveau** de 01 à 06, pas en moyenne ; au moins 30 passages par niveau ;
  intervalle de Wilson affiché.
- Aux niveaux 05 et 06, des CAPTCHA en clés de test sont servis à tout le monde : le passage est étiqueté
  `captcha_test`, compté dans une colonne à part, et ne vaut jamais comme résultat contre un vrai CAPTCHA.
- Récolte : mesurée au niveau 01. Elle dit si le moteur sait tout parcourir et tout lire. Sous protection,
  c'est l'endurance qui dit si le travail va au bout.
- « Le travail va au bout » : ≥ 99 % des pages récupérées à la fin, reprises comprises.
- Contre Cloudflare : aucun défi → réussi ; un défi sans action, qui se valide seul → réussi, compté à
  part ; un défi avec action (case à cocher, puzzle) → **échec**, le moteur ne clique pas (règle « aucun
  solveur de CAPTCHA réel »). La mesure ne vaut que si le témoin playwright est arrêté dans la majorité de
  ses passages ; sinon on durcit le réglage de Cloudflare (mode anti-bot, règle de défi sur la vitrine).

Ce que les mots d'Ethan veulent dire :
- **Indétectable** ne se prouve pas : on mesure un taux de passage contre des protections nommées.
- **Sur un serveur** : Linux sans écran ni carte graphique. L'adresse IP compte autant que le moteur (les
  protections notent la réputation de l'IP) : il faudra un proxy résidentiel, coût à part du moteur.
- **Durable** : un site qui détecte un bot le bannit, et un bannissement tue un travail long. Durable =
  mener un long travail sans se faire bannir.

Ce qui serait un échec même si « ça marche » :
- un moteur qui passe notre Arena mais qu'une vraie protection arrête ;
- des détecteurs qui attrapent tout le monde, humains compris ;
- un chiffre annoncé sans campagne derrière.

Hors v1 : voir § 6. Règles inchangées : périmètre D-30 (cibles à nous ou autorisées), aucun solveur de
CAPTCHA réel, aucun résultat inventé.

## 2. État mesuré au 11/11/2026

Vérifié dans le code, git ou la base (`outputs/shadowlab.sqlite3`), pas repris du journal.

| Sujet | Où on en est | Preuve |
|-------|--------------|--------|
| Socle du labo | 15 moteurs, campagnes matricielles, interface `/labo`, 405 tests rapides verts, lint propre | `pytest -m "not integration"`, `ruff` |
| Moteur contre les 39 détecteurs d'origine | Passe tout : 72/72 extractions, niveaux 01 à 06 | campagne 82 |
| Arena durcie (10/11) | NOEZIA est **classé** automatisé (23/24) mais **jamais bloqué** : la décision de bloquer se prend avant que l'empreinte arrive, et les scénarios n'ouvrent qu'une page | campagnes 84 et 85 |
| Campagne 86 (« 100 % ») | Docker est tombé pendant la campagne : 19 pannes sur 24 passages. Chiffre réel : 5 passages valides, 4 classés automatisés, 0 bloqué | base ; campagne 87 créée à 22h57 avec 0 passage |
| Calcul du taux de détection | Faux quand il y a des pannes : elles comptent au numérateur, pas au dénominateur (22 détectés / 5 évaluables pour la campagne 86) | `analytics.py:452-474` |
| Travail du 11/11 (D-47 à D-53) | Tests unitaires seulement, aucune campagne. La base réelle est encore au schéma 7 : la corrélation entre sessions n'a jamais tourné | `PRAGMA user_version` = 7 |
| Corrélation entre sessions | Le calcul d'empreinte lit une clé `proprietes` que le navigateur n'envoie pas | `correlation.py:19-39`, `observateur.js` |
| Sessions humaines | 0 sur 25 623 passages. L'outil de mesure des faux positifs existe déjà (`shadowlab manuel`) | colonne `truth` ; `analytics.py`, `cli.py` |
| Site de test | Trop petit pour mesurer une récolte : 10 références, 50 articles réduits à un identifiant, aucune page de détail | `site/pages.py` |
| Bannissement | Inexistant. Tout l'état d'un visiteur tient à un jeton neuf à chaque passage | `passages.py`, `site/gardien.py` |
| Identité du moteur | Rien n'est conservé entre deux lancements (ni cookies, ni dossier de profil). Aucune notion d'alerte, aucun budget par identité | `engines/noezia/moteur.py` |
| Serveur Linux | Jamais exécuté (D-50, D-51 sans test ni campagne) | — |
| Protection commerciale réelle | Jamais testée | — |
| Git | Branche `niveau-authentifie-perimetre` : 33 commits non poussés, 86 d'avance sur `master`, pas de PR | `git status -sb` |

### Campagne de référence n° 90 (11/11, 315 passages, 0 panne)

Passages réussis sur 15 par case (intervalle de Wilson : 15/15 → 80 à 100 % ; 0/15 → 0 à 20 %).

| Moteur | 01 | 02 | 03 | 04 | 05 | 06 | 07 |
|--------|----|----|----|----|----|----|----|
| noezia | 15 | 15 | 15 | 0 | 0 | 0 | 0 |
| patchright | 15 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright | 15 | 0 | 0 | 0 | 0 | 0 | 0 |

Ce que la base dit :
- **Niveaux 02 et 03** : l'Arena bloque les deux témoins (15/15, cause « fingerprinting ») et laisse passer
  NOEZIA. Les détecteurs d'origine font leur travail : `regles-http`, `botd`, `chrome-apis`,
  `coherence-profonde`, `regles-js` et `headless` classent patchright et playwright, **jamais NOEZIA**.
- **Niveaux 04 à 07** : les trois moteurs échouent de la même façon (180 passages sur 180). Le défi
  JavaScript est émis, l'empreinte est relevée sur la page du défi, le détecteur `cdp` la classe
  « automatisé », et la vérification du défi est refusée (« empreinte suspecte »).
- **Pour NOEZIA, `cdp` est le seul détecteur qui le classe** (101 passages sur 105), toujours avec les deux
  mêmes signaux : `debugger_instant` et `no_first_input`. La durée mesurée de l'instruction `debugger` est
  0 ms dans 298 relevés sur 315.
- Conséquence : tant qu'on ne sait pas si `cdp` classe aussi les humains, les niveaux 04 à 07 ne mesurent
  rien d'utile. S'il les classe (très probable à la lecture du code), ces niveaux sont fermés à tout le
  monde ; s'il est retiré, l'Arena n'a plus aucun signal valide contre NOEZIA. Dans les deux cas, la vérité
  viendra des sessions humaines (1.7) et de Cloudflare (1.8).
- Essai du 12/11, **non concluant** : un Chromium ordinaire, sans automatisation, a chargé la page deux
  fois mais n'a jamais envoyé son empreinte en 40 secondes. Cause non établie (piste : écran en veille ou
  fenêtre masquée, la sonde attend une animation). À surveiller pendant les sessions humaines : une page
  ouverte en arrière-plan pourrait ne rien envoyer.

### Campagne de récolte n° 92 (12/11, 105 passages, 0 panne)

Site vitrine réglé sur 40 annonces (42 pages par passage). Par case : 5 passages, complétude puis exactitude
moyennes.

| Moteur | 01 | 02 | 03 | 04 à 07 |
|--------|----|----|----|---------|
| noezia | 100 % / 100 % | 100 % / 100 % | 100 % / 100 % | 0 % (défi refusé) |
| patchright | 100 % / 100 % | 0 % (bloqué) | 0 % (bloqué) | 0 % (défi refusé) |
| playwright | 100 % / 100 % | 0 % (bloqué) | 0 % (bloqué) | 0 % (défi refusé) |

Ce que la base dit :
- **Récolte** : au niveau 01, chaque moteur retrouve les 200 annonces et les 2 800 champs de ses 5 passages.
  Le seuil « Récolte » du § 1 est atteint sur cet échantillon ; à confirmer sur le site à 500 annonces.
- **NOEZIA garde 100 % et 100 % aux niveaux 02 et 03**, où les deux témoins sont bloqués dès la première page.
- **Vitesse** : un passage de 42 pages prend 2 secondes aux témoins et 295 secondes à NOEZIA, soit 7 secondes
  par page (rythme humain). C'est le prix de la discrétion ; le débit entre dans l'endurance du palier 4.
- **Niveaux 04 à 07** : même refus que dans la campagne 90 (détecteur `cdp`), aucune fiche ouverte.

### Campagne de récolte n° 95 (12/11, site vitrine à 500 annonces, 9 passages, 0 panne, 3 h 08)

Niveau 01, scénario `recolte_vitrine` : la liste paginée puis les 500 fiches, 14 champs par annonce.

| Moteur | Passages réussis | Annonces retrouvées | Champs exacts | Durée d'un passage | dont chargement des pages | Temps processeur |
|--------|------------------|---------------------|---------------|--------------------|---------------------------|------------------|
| noezia | 3/3 | 500/500 | 7 000/7 000 | 58 à 65 min | 25 à 30 s | 12 à 14 min |
| patchright | 3/3 | 500/500 | 7 000/7 000 | 42 à 47 s | 26 à 29 s | 1 min 20 à 1 min 30 |
| playwright | 3/3 | 500/500 | 7 000/7 000 | 36 à 45 s | 21 à 28 s | 1 min 10 à 1 min 30 |

Ce que la base dit :
- **Le seuil « Récolte » du § 1 est atteint à la taille visée** : complétude 100 % et exactitude 100 % sur
  les 9 passages (seuil : 99 % et 99 %).
- **La lenteur de NOEZIA est entièrement voulue** : charger les quelque 525 pages lui prend 25 à 30 secondes,
  comme aux témoins. Le reste de l'heure (7 secondes par page) est du comportement simulé et des pauses.
  Ce rythme n'a jamais été comparé à un rythme plus rapide : c'est l'objet de
  `configs/experiments/recolte-rythme.yaml`.
- Mémoire : pic de 0,9 à 1,1 Go pour NOEZIA, 2,5 à 2,7 Go pour les témoins (le navigateur et ses processus).
- Limite : niveau 01 seulement, sans protection. Sous protection, c'est l'endurance qui dira si un long
  travail va au bout (palier 2).

### Ablations n° 93 et 94 (12/11, niveaux 04 à 07 sans `cdp`, 180 passages chacune, 0 panne)

Profils `04scdp` à `07scdp` (`configs/arena/profils-sans-cdp.yaml`) : les niveaux 04 à 07 tels quels, détecteur
`cdp` retiré. Entre les deux campagnes, deux défauts de l'Arena ont été corrigés (`c2fbdfc`, `f713b39`).
Passages réussis sur 15 (Wilson : 12/15 → 55 à 93 % ; 2/15 → 4 à 38 %).

| Moteur | 04 sans cdp | 05 sans cdp | 06 sans cdp | 07 sans cdp |
|--------|-------------|-------------|-------------|-------------|
| noezia, campagne 93 (Arena avec défauts) | 0 | 0 | 0 | 0 |
| noezia, campagne 94 (défauts corrigés) | 15 | 12 | 2 | 0 |
| patchright, campagnes 93 et 94 | 0 | 0 | 0 | 0 |
| playwright, campagnes 93 et 94 | 0 | 0 | 0 | 0 |

Ce que la base dit (campagne 94) :
- **Les témoins restent arrêtés sans `cdp`** (60/60 chacun), dès la page du défi, par les détecteurs
  d'origine : `regles-http`, `botd`, `chrome-apis`, `coherence-profonde`, `regles-js`, plus `headless` pour
  playwright (et `correlation-session` aux niveaux 06 et 07). L'Arena garde donc des signaux valides
  contre eux.
- **Niveau 04** : NOEZIA passe 15/15.
- **Niveau 05** : 12/15. Les 3 arrêts sont sur `pagination` : score composite 0,85 (seuil 0,6) =
  `pas_de_scroll` + `pas_de_pause` (délai maximal entre deux mouvements de souris : 58 à 60 ms). Turnstile
  et reCAPTCHA sont franchis **en clés de test** (`captcha_test`) : cela ne prouve rien contre un vrai CAPTCHA.
- **Niveau 06** : 2/15. 11 arrêts par `correlation-session` (la même empreinte revue 5 fois ou plus, ou plus
  de 30 sessions par heure), 2 par le composite 0,85 sur `pagination`. Les 2 réussites sont des premiers
  passages, avant que l'empreinte ait été vue 5 fois.
- **Niveau 07** : 0/15. 13 arrêts par `correlation-session`, 2 par le WAF sur `/lab/turnstile/verifier`.
- **Défaut de l'Arena au niveau 07** (reproduit le 12/11 par 6 requêtes directes au WAF) : en paranoïa 4,
  le nom même du champ `cf-turnstile-response` (deux tirets) déclenche la règle CRS 942432, et
  `g-recaptcha-response` aussi. Personne ne peut valider Turnstile ni reCAPTCHA au niveau 07, humain
  compris. Jamais vu avant : `cdp` arrêtait tout le monde plus tôt (la règle n'apparaît que 2 fois dans
  tout le journal du WAF, dans la campagne 94). Correctif à faire hors campagne (exclusion dans
  `docker/arena/coraza/main.go`, image à reconstruire).

Campagne 93, gardée pour mémoire, chiffres faussés par les deux défauts : au 04, le CAPTCHA démo était émis
sur un motif `cdp` pourtant exclu (15/15) ; au 05, composite 0,65 = `chrome_sans_alps` (faux positif sur
tout Chrome récent) + `pas_de_scroll` (15/15).

Lecture, une fois `cdp` retiré : ce qui arrête NOEZIA est (1) son comportement sur plusieurs pages, ni
défilement ni pause, à corriger en 1.9 si le rejeu confirme que les humains n'ont pas ce profil ; (2) la
corrélation entre sessions, qui tient autant à la forme de la campagne (la même empreinte à chaque passage)
qu'au moteur, voir le point connu du § 4 ; (3) le défaut du WAF au niveau 07.
**Non vérifié** : si `cdp`, `correlation-session` et le composite arrêtent aussi des humains (sessions
humaines, 1.7).

Incohérence confirmée le 11/11 (journal de la campagne 90) : le moteur annonce Chrome 129 à 132 alors que
le navigateur embarqué est Chromium 156.0.8078.4. À corriger en 1.9.

En-têtes envoyés par NOEZIA, comptés le 12/11 sur les 1 160 requêtes de ses 60 passages de la campagne 94
(`observations_http`), et comparés au même Chromium piloté sans réglage par les témoins :
- **« HeadlessChrome » fuit sur 182 requêtes (16 %).** 144 des 311 envois `POST /lab/collecte` partent avec
  le `User-Agent` d'origine du navigateur (`HeadlessChrome/156.0.8078.4`), sans aucun réglage du moteur ;
  38 navigations vers une page qui a elle-même pour référent (sans doute le retour après un défi) gardent
  le `User-Agent` réglé (`Chrome/129`) mais retrouvent le `sec-ch-ua` d'origine (« HeadlessChrome » v156).
  Le réglage du moteur ne couvre donc pas toutes les requêtes. Mécanisme lu dans le code : le moteur
  remplace « HeadlessChrome » dans les en-têtes au passage de son filtre réseau (`moteur.py`, `_filtrer`) ;
  ce filtre ne voit pas les redirections (piège connu, D-07) ni, sans doute, les envois faits au moment où
  la page se ferme. L'Arena ne le voit pas (`regles-http` ne classe jamais NOEZIA) : c'est un manque de l'Arena
  autant qu'un défaut du moteur. **C'est l'écart le plus grave trouvé à ce jour.**
- **Le moteur se contredit sur sa version, sans référence extérieure** : `User-Agent` et `sec-ch-ua` réglés
  annoncent Chrome 129 ou 130 (version tirée au sort dans le profil), `navigator.userAgentData` et les
  requêtes non réglées disent 156, la version réelle.
- `User-Agent` réglé avec la vraie version de macOS (`Mac OS X 15_1`) ; les témoins envoient la version
  figée `Mac OS X 10_15_7`. La version complète dans le `User-Agent` est aussi à vérifier sur le Chrome
  d'Ethan (un Chrome grand public la réduit à `Chrome/129.0.0.0` ; le Chromium d'essai la garde).
- `sec-ch-ua-arch`, `-bitness`, `-full-version-list` et `-model` sur 1 016 requêtes (toutes sauf les 144
  non réglées) ; les témoins n'envoient que `sec-ch-ua`, `-mobile` et `-platform`.
- `Accept-Language` change d'une requête à l'autre dans une même session : valeur complète du profil sur
  804 requêtes (fichiers et envois), langue seule (`de-DE`, `fr-FR`, `en-US`) sur 212 (les pages), absent
  sur les 144 non réglées.

Piste pour 1.9, à trancher par une mesure : la documentation de Patchright (la base du moteur) recommande
un vrai Chrome avec interface, sans `User-Agent` ni en-têtes imposés. Le moteur fait l'inverse (sans
interface, identité réécrite), et ce sont ses réécritures qui fuient. Mesure faite le 12/11 (campagne 97,
voir plus bas) : `configs/experiments/ablation-interface.yaml` (patchright avec un vrai Chrome et son
interface, rien d'imposé ; noezia en « identité native », option préparée sur la branche
`moteur-identite-native`, D-59, sans effet par défaut).

Empreinte JavaScript : NOEZIA comparé champ par champ au même Chromium piloté sans réglage (patchright,
campagne 94, niveau 04 sans `cdp` ; 84 champs différents sur 315 comparés). La différence est mesurée ; ce que fait
un vrai Chrome reste **à lire dans les sessions humaines**, qui trancheront champ par champ. Candidats
pour 1.9, du plus net au moins net :
- `navigator.webdriver` **absent** chez NOEZIA (ni valeur, ni propriété sur le prototype) ; le témoin a
  `false`, propriété native sur le prototype ;
- `plugins` = 4 et `mimeTypes` = 4 (témoin sans interface : 0 et 0) ;
- `performance.memory` posée comme propriété propre, et `devicePixelRatio`, `outerWidth`, `outerHeight`
  devenues énumérables sur `window` : traces de redéfinition ;
- fenêtre plus haute que la zone utile de l'écran (`outerHeight` 1108 pour `availHeight` 1092), et 28 px
  seulement entre la fenêtre et la page ;
- `deviceMemory` = 8 annoncé avec une puce M5 Pro (le Chromium réel donne 32 sur ce poste) ;
- WebRTC : aucun candidat (le témoin en donne 4) ; 4 voix de synthèse ; une ligne de pile en plus dans une
  erreur (fonction enveloppée) ; `chrome.runtime` présent.

Origine de chaque écart dans le code du moteur : `docs/recherche/empreinte-noezia-2026-11-12.md` (analyse du
12/11, quelques renvois contrôlés). Sur les 84 champs : 31 ne servent qu'à masquer le mode sans interface,
25 sont des traces laissées par la réécriture elle-même, 18 viennent du profil généré, 10 sont de l'aléa.
Avec un vrai Chrome, son interface et aucune réécriture, les 74 premiers n'ont plus de raison d'être.

**Comparaison avec un vrai Chrome** (essai n° 96 du 12/11 : Google Chrome 156 avec interface, rien de réécrit ;
un seul Chrome, sur ce poste, piloté par Patchright : pas encore une session humaine ; détail au § 4 du même
document). Sur les 84 champs où NOEZIA diffère du témoin :
- **17 où NOEZIA a raison** (il imite bien le vrai Chrome : `window.chrome`, `chrome.app`, `csi`, `loadTimes`,
  marques annoncées, carte graphique, autorisation des notifications) ;
- **35 où NOEZIA se trahit**, dont 28 où le témoin sans réglage donnait la bonne valeur : la réécriture a
  cassé ce qui était juste. Les plus nets : `navigator.webdriver` supprimé (le vrai Chrome l'a, à `false`) ;
  `chrome.runtime` présent (absent du vrai Chrome sur cette page) ; aucun candidat WebRTC (4 chez le vrai
  Chrome) ; 4 plugins et 4 types MIME (5 et 2) ; `Chrome/129.0.6668.100` et `Mac OS X 15_1` dans le User-Agent
  (`Chrome/156.0.0.0` et `10_15_7`) ; 28 px entre la fenêtre et la page (87) ; canvas, audio et tailles de
  texte bruités ;
- 22 qui dépendent de la machine ou du profil (écran, fenêtre, langue, fuseau, mémoire), 10 d'aléa.
Sept champs de plus diffèrent du vrai Chrome chez NOEZIA comme chez le témoin (`pdfViewerEnabled`, partage,
polices, taille de la mémoire JavaScript arrondie). En-têtes : le vrai Chrome envoie `Chrome/156.0.0.0`,
trois indices de marque seulement, `Accept-Language: fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7`, et un ordre
d'en-têtes qu'aucune requête de NOEZIA ne reproduit. Au niveau de l'empreinte, NOEZIA en identité native
donne les mêmes valeurs que Patchright avec interface, sauf la taille de fenêtre (vraie contre émulée).

Aucun détecteur de l'Arena ne relève ces écarts aujourd'hui : leur effet se mesurera contre Cloudflare (1.8).
Deux règles les mesureraient dans l'Arena : « HeadlessChrome » dans un en-tête de n'importe quelle requête
d'une session (pas seulement la première), et une version du `User-Agent` différente de celle de
`userAgentData`. À décider avec Ethan (règle 4 du § 8 : on n'ajoute à l'Arena que ce qu'un palier exige).
Chiffres de ce paragraphe et des deux précédents recomptés le 12/11 par une vérification indépendante.

### Campagne 97 : identité réécrite ou identité native (12/11, 525 passages, 0 panne, 2 h 33)

Elle mesure, niveau par niveau, ce que change l'interface et l'identité d'origine : noezia tel qu'il est,
noezia en identité native, un vrai Chrome sans rien de noezia, et les deux témoins (13 h 35 à 16 h 08,
heure locale).
Arena du matin du 12/11 ; niveaux 06 et 07 sans `correlation-session` (profils `06scorr` et `07scorr`).
Passages réussis sur 15 par case (3 scénarios × 5 répétitions).

| Configuration | 01 | 02 | 03 | 04 | 05 | 06 sans corr. | 07 sans corr. |
|---------------|----|----|----|----|----|---------------|---------------|
| noezia (identité réécrite, sans interface) | 15 | 10 | 10 | 10 | 0 | 0 | 0 |
| noezia-natif (vrai Chrome, interface, identité d'origine) | 15 | 15 | 15 | 0 | 0 | 0 | 0 |
| patchright-chrome-interface (vrai Chrome, rien de noezia) | 15 | 15 | 15 | 0 | 0 | 0 | 0 |
| patchright (témoin) | 15 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright (témoin) | 15 | 0 | 0 | 0 | 0 | 0 | 0 |

Issues : 165 `extraction_reussie`, 240 `challenge_non_valide`, 120 `bloque`. Aucun passage sans issue, aucune
panne. Durée médiane de noezia-natif : 8,0 s pour un passage réussi, 57,4 s pour un passage refusé.

Ce que la base dit :
- **Le moteur tel qu'il est tient le seuil de discrétion (≥ 90 %) au seul niveau 01.** Une seule cause
  d'échec, dans les 60 passages refusés : le signal `headless_dans_une_requete` de `regles-http` (une requête
  sur 11 à 13 porte « HeadlessChrome »), vu par l'Arena depuis D-60. Aux niveaux 02 à 04, seul `pagination`
  échoue (0 sur 5) ; `static_html` et `javascript_content` passent (5 sur 5). Aux niveaux 05, 06 et 07, les
  trois scénarios échouent (15 sur 15), après un défi JavaScript validé et, au 05 et au-delà, un Turnstile
  en clés de test (`captcha_test`). Les trois niveaux 05 à 07 donnent la même séquence de décisions.
- **L'identité native tient les niveaux 01 à 03 (15 sur 15)**, avec ou sans le reste de noezia
  (comportement humain, défis) : noezia-natif et patchright-chrome-interface donnent les mêmes chiffres.
- **Du niveau 04 au 07, un vrai Chrome est arrêté à chaque passage (120 sur 120)** : défi JavaScript émis,
  puis refusé (`rejete-empreinte`, motif `empreinte_suspecte`) à cause du score composite : 1,03 aux niveaux
  04 et 05 (`voices_vide`, `runtime_incomplet`, `polices_os_manquantes`), 1,31 aux niveaux 06 et 07 sans
  corrélation (les trois mêmes plus `rtt_zero`). Aucun autre motif. Un humain avec le même Chrome
  déclencherait ces quatre signaux : ce sont des défauts de l'Arena, corrigés par D-66. Le chiffre réel
  de ces niveaux a été mesuré ensuite par la campagne 98 (bloc suivant).
- **Les deux témoins sont arrêtés à tous les niveaux à partir du 02** (0 sur 15, 180 passages sur 180).
  Aux niveaux 02 et 03, par `regles-http` (`ua_headless`, `langue_absente`). Du 04 au 07, le défi est refusé
  sur l'empreinte relevée par `regles-http`, `botd`, `regles-js` et `chrome-apis` (plus `headless` pour
  playwright).
- **Réserves** : 15 passages par case, alors que l'objectif en demande 30. Intervalle de Wilson à 95 % :
  15 sur 15 → 80 à 100 %, 10 sur 15 → 42 à 85 %, 0 sur 15 → 0 à 20 %. Niveaux 06 et 07 mesurés sans
  corrélation. Un seul Chrome, piloté, sur ce poste ; l'Arena n'est pas encore calibrée sur des humains (1.7).

### Campagne 98 : contrôle de D-66, un vrai Chrome passe-t-il les niveaux 04 à 06 ? (12/11, 135 passages, 0 panne, 33 min)

Elle refait la mesure de la campagne 97 sur les niveaux 04, 05 et 06 sans corrélation (profil `06scorr`),
après la correction de quatre règles de l'Arena (D-66). 16 h 19 à 16 h 52, heure locale ; mêmes cases, 15
passages chacune (3 scénarios × 5 répétitions). Configuration :
`configs/experiments/controle-vrai-chrome.yaml`. Passages réussis sur 15, avec le rappel de la campagne 97
(même Arena avant D-66).

| Configuration | 04 (97 → 98) | 05 (97 → 98) | 06 sans corr. (97 → 98) |
|---------------|--------------|--------------|-------------------------|
| noezia-natif (vrai Chrome, interface, identité d'origine, comportement et défis de noezia) | 0 → 15 | 0 → 15 | 0 → 15 |
| patchright-chrome-interface (vrai Chrome, rien de noezia) | 0 → 10 | 0 → 5 | 0 → 0 |
| patchright (témoin) | 0 → 0 | 0 → 0 | 0 → 0 |

Issues : 60 `extraction_reussie`, 45 `challenge_non_valide`, 30 `bloque`. Aucun passage sans issue. Colonne à
part (règle du § 1) : 60 passages portent une décision `captcha_test` (Turnstile en clés de test, aux niveaux
05 et 06 ; reCAPTCHA en clés de test aussi pour 35 d'entre eux). Parmi eux, 35 sont réussis (noezia-natif 30,
patchright-chrome-interface 5) ; les 25 autres réussites sont au niveau 04, sans CAPTCHA en clés de test.

Ce que la base dit :
- **L'identité native tient les niveaux 04, 05 et 06 sans corrélation : 15 sur 15 à chacun** (45 sur 45, les
  trois scénarios à 5 sur 5 par niveau). Avec la campagne 97 (niveaux 01 à 03, 15 sur 15), cela fait **les six
  niveaux de l'objectif à 15 sur 15 pour `noezia` en identité native**. Durée médiane d'un passage réussi :
  7,7 s au niveau 04, 16,7 s au niveau 05 et 16,5 s au niveau 06.
- **Le même Chrome sans le comportement de noezia est arrêté pour absence d'interaction.** Le défi JavaScript
  est maintenant validé aux trois niveaux : les quatre signaux de D-66 ne sortent plus (0 occurrence). Ce qui
  l'arrête est `aucune_interaction` (aucun mouvement, clic, touche ni défilement), avec `pages_eclair` (moins
  de 500 ms par page) au détecteur `comportement` : niveau 04, `pagination` 0 sur 5 (les deux autres scénarios
  5 sur 5) ; niveau 05, 10 arrêts sur 15 ; niveau 06, composite 0,5 sur `aucune_interaction` (12 passages) ou
  le même détecteur `comportement` (3 passages). Aucun signal d'empreinte. C'est le comportement humain du
  moteur qui fait la différence, et c'est une détection juste, pas un défaut de l'Arena.
- **Le témoin reste arrêté à chaque passage (45 sur 45)** : défi refusé pour empreinte suspecte (`regles-http`,
  signaux `ua_headless` et `langue_absente` ; `botd` ; `regles-js` ; `chrome-apis`). La correction D-66 n'a
  pas ouvert l'Arena.
- **D-66 est confirmée par la mesure** : du 04 au 06, le vrai Chrome n'est plus arrêté par les quatre signaux
  d'empreinte, et le témoin l'est toujours.
- **Réserves** :
  - 15 passages par niveau, alors que l'objectif en demande 30. Intervalle de Wilson à 95 % de 15 sur 15 : 80
    à 100 %.
  - Niveaux 05 et 06 passés avec des CAPTCHA en clés de test (`captcha_test`) : cela ne vaut rien contre un
    vrai CAPTCHA.
  - Niveau 06 mesuré sans `correlation-session` : avec elle, le moteur faisait 2 sur 15 dans la campagne 94,
    en identité réécrite. Le chiffre du 06 complet n'est pas connu pour l'identité native.
  - L'Arena n'est pas calibrée sur des humains (aucune session humaine en base) : on ne sait pas si elle
    laisse passer des humains à ces niveaux.
  - Une seule machine, un seul Chrome, avec interface, sur macOS. Rien n'a été mesuré contre une protection
    réelle.

### Campagne 100 : discrétion de l'identité native, 30 passages par niveau (12/11, 180 passages, 0 panne, 54 min)

Elle refait la mesure d'un seul tenant, au nombre de passages que demande l'objectif (§ 1). Moteur `noezia` seul,
en identité native (libellé `noezia-natif` : `headless: false`, `channel: chrome`, `identite_native: true`).
16 h 58 à 17 h 52, heure locale. Niveaux 01 à 06, niveau 06 sans corrélation (profil `06scorr`), sur l'Arena
corrigée du jour (D-60 à D-66). 3 scénarios × 10 répétitions = 30 passages par niveau. Configuration :
`configs/experiments/discretion-native-30.yaml`. Pas de témoin dans cette campagne : il est arrêté à chaque
passage des niveaux 02 à 06 dans les campagnes 97 et 98 du même jour.

| Niveau | Réussis sur 30 | Taux | Wilson à 95 % | dont `captcha_test` (réussis / passages) | Durée médiane d'un passage réussi |
|--------|----------------|------|---------------|------------------------------------------|-----------------------------------|
| 01 | 30 | 100 % | 88,6 à 100 % | 0 / 0 | 7,6 s |
| 02 | 30 | 100 % | 88,6 à 100 % | 0 / 0 | 7,8 s |
| 03 | 30 | 100 % | 88,6 à 100 % | 0 / 0 | 8,8 s |
| 04 | 30 | 100 % | 88,6 à 100 % | 0 / 0 | 8,9 s |
| 05 | 30 | 100 % | 88,6 à 100 % | 30 / 30 | 15,5 s |
| 06 sans corrélation | 29 | 96,7 % | 83,3 à 99,4 % | 29 / 30 | 15,6 s |

Total : 179 passages réussis sur 180, 0 panne. Issues : 179 `extraction_reussie`, 1 `bloque`.
Colonne à part (règle du § 1) : 60 passages portent une décision `captcha_test` (Turnstile et reCAPTCHA en clés
de test, niveaux 05 et 06), dont 59 réussis. Les 120 autres passages (niveaux 01 à 04) n'en ont aucune.

Ce que la base dit :
- **Le taux observé est au moins 90 % à chacun des six niveaux, avec 30 passages par niveau.** Les deux
  premières conditions de l'objectif (taux ≥ 90 % à chaque niveau, au moins 30 passages) sont remplies par
  `noezia` en identité native, sur l'Arena, niveau 06 sans corrélation.
- **Ce que dit l'intervalle de Wilson** (la troisième condition : l'afficher) : la borne basse est sous 90 % à
  chaque niveau, même à 30 sur 30 (88,6 %). Avec 30 passages, on ne peut donc pas exclure un taux réel un peu
  inférieur à 90 %. Pour que la borne basse atteigne 90 % avec 100 % observé, il faut au moins 35 passages
  par niveau (calcul seul, pas une mesure).
- **Le seul échec n'est pas imputable au moteur** : passage 34119, niveau 06 sans corrélation, scénario
  `static_html`. Le défi JavaScript et le Turnstile en clés de test sont validés, puis `POST /lab/recaptcha/verifier`
  est bloqué par le WAF, règle CRS 942210 (« Detects chained SQL injection attempts 1/2 »), sur le jeton du
  reCAPTCHA en clés de test. Un humain aurait été bloqué de la même façon : c'est un défaut de l'Arena, corrigé
  par D-69. Il reste compté comme échec dans le tableau : on ne retire aucun passage après coup.
- **Aucun des 180 passages n'a été classé « automatisé »** (`classe_automatise` faux partout).

Réserves :
- Niveaux 05 et 06 passés avec des CAPTCHA en clés de test (`captcha_test`) : cela ne vaut rien contre un vrai
  CAPTCHA.
- Niveau 06 complet, avec `correlation-session` : 0 sur 15 (campagne 101, bloc suivant).
- L'Arena n'est pas calibrée sur des humains : aucune session humaine en base, 5 sessions prévues le soir même
  (1.7). On ne sait pas si elle laisse passer des humains à ces niveaux.
- Une seule machine, un seul Chrome avec interface, sur macOS.
- Pas de témoin dans cette campagne ; il est arrêté à chaque passage dans les campagnes 97 et 98 du même jour.
- Rien n'a été mesuré contre une protection réelle, ni depuis un serveur.
- L'identité native n'est pas encore le réglage par défaut du moteur (option `identite_native`, D-59).
- Seule la qualité « Discrétion » est concernée, et seulement sur l'Arena. Le produit n'est pas atteint (§ 1).

### Campagne 101 : le niveau 06 complet, avec la corrélation entre sessions (12/11, 15 passages, 0 panne, 14 min)

Même moteur et même réglage que la campagne 100, niveau 06 avec `correlation-session` (profil d'origine), 3
scénarios × 5 répétitions. 17 h 52 à 18 h 06, heure locale. Configuration :
`configs/experiments/discretion-native-correlation.yaml`.

- **0 sur 15** (Wilson : 0 à 20,4 %). Les 15 passages sont `challenge_non_valide` : défi JavaScript émis, puis
  refusé pour empreinte suspecte (`rejete-empreinte`), sur le seul signal `recycling_canvas` du détecteur
  `correlation-session`. Libellé du premier passage : « profil vu dans 333 sessions et canvas vu dans 485
  sessions de la base, celle-ci comprise (seuil 10) ». Les compteurs montent d'un par passage, jusqu'à
  « profil vu dans 347 sessions et canvas vu dans 499 sessions » au quinzième (bornes : 333 à 347 et 485 à 499).
- **Lecture** : un vrai Chrome qui repasse sans rien réécrire a la même empreinte à chaque passage, et la base en
  avait gardé des centaines depuis le matin (campagnes 96 à 100). Ce n'est donc pas mesuré comme le ferait un
  site réel, qui ne voit pas des centaines de visites du même navigateur en quelques heures. Mais cela montre ce qui
  attend une longue récolte : c'est l'objet du palier 2 (une identité qui dure) et du palier 4 (plusieurs
  identités). Analyse : `docs/recherche/correlation-entre-sessions-2026-11-12.md`.
- **Conséquence pour l'objectif** : le niveau 06 de l'objectif n'est pas tenu avec la corrélation. Le seuil de
  discrétion n'est atteint que niveau 06 sans corrélation (campagne 100).

### Récolte générale (12/11, D-70)

La commande `shadowlab recolte` (recettes YAML, parcours, reprise, notation, deux moteurs) est fusionnée dans la
branche de travail (commit `b1a40ed`). Guide : `docs/recolte.md`.

- **Mesuré** (commande réelle, site du labo sur un port à part, niveau 01) : moteur `http`, vitrine à 500
  annonces : 525 pages, 500 annonces, 7 000 champs sur 7 000, 0,8 s ; site de rallye factice : 427 pages, 4 569
  enregistrements, 34 410 champs sur 34 410. Récolte incrémentale (vitrine à 45 puis 50 annonces) : 8 pages
  lues, 45 évitées, 5 nouveautés, 53 pages sur 53. Moteur `navigateur` (vrai Chrome, identité native) : vitrine
  à 45 annonces, 48 pages sur 48 en 5 min 50 s. Essai de campagne (`recolte-generale-essai.yaml`, base à part) :
  4 passages sur 4 à 100 %, dont le rallye à 3 rallyes par le navigateur (85 pages en 612 s).
- **Pas mesuré** : aucun vrai site, aucune vraie protection ; la commande elle-même vise le site en direct
  (niveau 01), les niveaux protégés de l'Arena ne sont mesurés que par les scénarios de campagne (campagne 105,
  plus bas) ; la coupure d'une redirection vers un autre hôte n'est pas vérifiée dans un vrai Chrome ; le
  rythme « prudent » n'a jamais tourné en temps réel ; le CSV n'a pas été ouvert dans Excel.
- **Campagne de preuve, n° 102** (`recolte-generale.yaml`, base du labo, le 12/11 de 21 h 54 à 1 h 18, 0 panne) :
  `noezia` en identité native (moteur `navigateur`) et `curl-cffi` (moteur `http`), niveau 01, vitrine à 150
  annonces (158 pages) et site de rallye à 24 rallyes (427 pages), 3 répétitions. **12 passages sur 12 réussis ;
  pages, enregistrements et champs à 100 % à chaque passage, aucune page en échec.** Durées en navigateur :
  vitrine 1 053, 1 038 et 1 147 s (6,6 à 7,3 s par page) ; rallye 2 868, 3 031 et 3 076 s (6,7 à 7,2 s par
  page). En HTTP : 0,3 à 0,4 s et 1,0 s. C'est le critère de l'étape 6 de la conception : la même commande sur
  les deux sites, avec les deux moteurs. Réserves : niveau 01 seulement (site en direct, aucune protection) ;
  3 répétitions ; sites à nous, en local. Une première campagne, lancée à 21 h 08 dans une base à part, avait
  été arrêtée à 21 h 43 pour la fusion (un passage fini, réussi).
- Suite complète après la fusion : 1 247 tests verts (journal du 12/11, 21 h 55).
- **Campagne 103 : la récolte jugée par l'Arena** (`recolte-arena.yaml`, 13/11 de 1 h 20 à 1 h 39, 30 passages,
  0 panne, vitrine à 20 annonces, entrée par l'Arena avec le jeton du passage). Passages réussis sur 3 :

  | Moteur de la récolte | 02 | 03 | 04 | 05 | 06 sans corr. |
  |----------------------|----|----|----|----|---------------|
  | `navigateur` (noezia en identité native) | 3 | 3 | 0 | 0 | 0 |
  | `http` (curl-cffi, témoin) | 0 | 0 | 0 | 0 | 0 |

  Le moteur navigateur récolte tout aux niveaux 02 et 03 (138 à 178 s pour 21 pages). Aux niveaux 04 à 06, il
  valide le défi JavaScript et les CAPTCHA en clés de test, puis reçoit un 429 sur une photo de la page de
  liste (photo 18 au niveau 04, 9 au 05, 4 au 06) et la sentinelle arrête la récolte, comme prévu, au premier
  refus. Ce n'est pas le moteur : la limite de débit de l'Arena comptait les photos qu'une page charge
  (défaut corrigé par D-71). Le témoin `http` est arrêté partout : empreinte aux niveaux 02 et 03, défi
  JavaScript jamais validé du 04 au 06. Campagne à refaire après D-71.
- **Campagne 104 : la même, après D-71** (13/11 de 1 h 49 à 2 h 07, 30 passages, 0 panne). Passages réussis
  sur 3 :

  | Moteur de la récolte | 02 | 03 | 04 | 05 | 06 sans corr. |
  |----------------------|----|----|----|----|---------------|
  | `navigateur` (noezia en identité native) | 3 | 3 | 0 | 0 | 0 |
  | `http` (curl-cffi, témoin) | 0 | 0 | 0 | 0 | 0 |

  D-71 a fait son effet : plus aucun 429, les 18 photos de la liste sont servies. Mais la récolte s'arrête
  quand même à la première page aux niveaux 04 à 06 (0 page lue, arrêt en 11 à 24 s), sur le signe
  « statut 403 ». Le navigateur a pourtant franchi l'entrée : défi JavaScript validé, CAPTCHA en clés de
  test passés aux niveaux 05 et 06, vraie page reçue en 200. **Cette fois le défaut est dans la commande de
  récolte** : après un défi d'entrée, le moteur rend encore le statut de la page de défi (403) avec le
  contenu de la vraie page ; la porte d'entrée de la sentinelle ne reconnaît qu'un défi encore affiché, et
  la recette du passage n'en déclarait pas. La récolte n'a donc toujours pas été jugée par les détecteurs
  des niveaux 04 à 06 : elle n'y a lu aucune page. Niveaux 02 et 03 : 150 à 166 s pour 21 pages, comme à
  la 103.
- **Campagne 105 : la même, après D-72** (13/11 de 2 h 24 à 3 h 04, 30 passages, 0 panne, vitrine à 20
  annonces, 21 pages par passage). Passages réussis sur 3 :

  | Moteur de la récolte | 02 | 03 | 04 | 05 | 06 sans corr. |
  |----------------------|----|----|----|----|---------------|
  | `navigateur` (noezia en identité native) | 3 | 3 | 3 | 3 | 3 |
  | `http` (curl-cffi, témoin) | 0 | 0 | 0 | 0 | 0 |

  **Le moteur navigateur récolte tout, à chaque niveau : 15 passages sur 15, et à chacun 21 pages sur 21,
  20 annonces sur 20, 280 champs exacts sur 280.** Aucun blocage, aucun détecteur ne le signale
  (`detecte_par` vide), aucun refus en cours de passe. Durées : 136 à 195 s pour 21 pages (6,5 à 9,3 s par
  page), sans écart net entre les niveaux. À l'entrée : défi JavaScript validé au niveau 04 ; défi
  JavaScript, Turnstile et reCAPTCHA en clés de test (`captcha_test`) aux niveaux 05 et 06. Le témoin
  `http` est arrêté partout (empreinte aux niveaux 02 et 03, défi JavaScript jamais validé ensuite).
  C'est la première fois que la récolte complète est jugée par les détecteurs des niveaux 04 à 06.
  **Réserves** : 3 passages par niveau (borne basse de Wilson : 44 % par niveau, 80 % sur les 15) ; 21 pages
  par passage, donc rien sur l'endurance ; CAPTCHA en clés de test aux niveaux 05 et 06 ; niveau 06 sans
  la corrélation entre sessions (avec elle, 0 sur 15 à la campagne 101) ; niveau 07 non mesuré ; Arena non
  calibrée sur des humains ; une machine, un Chrome sur macOS ; les défis d'entrée sont ceux du labo, que
  le moteur ne passe que sur le labo ; le témoin `http` de la campagne n'imite pas un navigateur, il est
  plus faible que le moteur `http` de la commande.
- **Campagne 106 : un parcours long par l'Arena** (`recolte-arena-rallye.yaml`, 13/11 de 3 h 07 à 4 h 50,
  3 passages, 0 panne) : le site de rallye, 427 pages lues par une seule session, moteur navigateur.

  | Niveau | Pages lues | Champs exacts | Durée | Issue |
  |--------|-----------|---------------|-------|-------|
  | 04 | 427 sur 427 | 34 410 sur 34 410 | 2 940 s (6,9 s par page) | réussi |
  | 05 | 427 sur 427 | 34 410 sur 34 410 | 3 155 s (7,4 s par page) | réussi (`captcha_test`) |
  | 06 sans corr. | 9 sur 427 | 1 176 sur 1 176 lus | 86 s | **arrêté** : défi redemandé à la 10ᵉ page |

  Aux niveaux 04 et 05, une session lit 427 pages de suite pendant 49 et 53 minutes sans blocage, sans
  détecteur qui la signale, sans une seule page en échec. Au niveau 06, l'Arena a redemandé le défi
  JavaScript et les deux CAPTCHA à la 10ᵉ page, et la sentinelle a arrêté la passe (un 403 en cours de
  passe arrête toujours, c'est voulu). **Cause, lue dans la base : ce n'est pas le moteur.** Aux niveaux 05 à
  07, l'Arena lie le cookie du défi au JA4 exact (`lier_tls`). Or le vrai Chrome a rouvert une connexion en
  reprenant sa session TLS : son ClientHello porte alors l'extension `pre_shared_key` (0029) en plus, et
  son JA4 passe de `t13d1517h2_…` à `t13d1518h2_…`. Les trois passages ont eu cette connexion (environ
  50 s après le début) ; aux niveaux 04 (pas de liaison) et 05 (la connexion reprise n'a porté qu'un envoi
  de mesures, pas une page), cela n'a rien déclenché. Un humain avec un vrai Chrome aurait reçu le défi une
  seconde fois de la même façon : défaut de l'Arena, corrigé par D-73. En base : 135 connexions de ce
  Chrome avec reprise, 2 908 sans.
  **Constat pour l'endurance** : le cookie de défi de l'Arena vit 3 600 s. Une passe de plus d'une heure
  sera donc redéfiée en cours de route à partir du niveau 04, et la sentinelle l'arrêtera. Les 427 pages
  (53 minutes au plus) sont passées juste dessous. Un long travail demande une réponse à ce cas (attendre
  un défi qui se valide seul en cours de passe, ou arrêter puis reprendre) : à concevoir avant l'endurance.
  Réserves : un seul passage par niveau ; CAPTCHA en clés de test ; niveau 06 sans corrélation ; site à
  nous, en local ; une machine.
- **Campagne 107 : le même parcours long, après D-73** (13/11 de 5 h 07 à 7 h 40, 3 passages, 0 panne) :

  | Niveau | Pages lues | Champs exacts | Durée | Issue |
  |--------|-----------|---------------|-------|-------|
  | 04 | 427 sur 427 | 34 410 sur 34 410 | 3 143 s (7,4 s par page) | réussi |
  | 05 | 427 sur 427 | 34 410 sur 34 410 | 2 935 s (6,9 s par page) | réussi (`captcha_test`) |
  | 06 sans corr. | 427 sur 427 | 34 410 sur 34 410 | 3 133 s (7,3 s par page) | réussi (`captcha_test`) |

  **Une session lit 427 pages de suite à chacun des trois niveaux, sans blocage, sans détecteur qui la
  signale, sans page en échec, et le défi d'entrée n'est demandé qu'une fois.** Au niveau 06, une page a été
  demandée sur une connexion reprise par Chrome (JA4 `t13d1518h2_…`, 6 requêtes dont 1 page) : c'est le
  cas exact qui arrêtait la campagne 106, et l'Arena n'a pas redemandé le défi. D-73 est donc vérifiée
  dans un vrai Chrome, par l'Arena. Avec la 106 : 5 passages de 427 pages réussis sur 5 aux niveaux 04 et 05
  (2 et 2) et 06 sans corrélation (1), le sixième arrêté par le défaut corrigé.
  Réserves : un passage par niveau et par campagne ; CAPTCHA en clés de test aux niveaux 05 et 06 ; niveau 06
  sans corrélation ; niveau 07 non mesuré ; 53 minutes au plus par passe, sous la durée de vie du cookie de
  défi (une heure) ; aucun humain en base ; site à nous, en local ; une machine, un Chrome sur macOS.
- **Campagne 108 : la récolte par l'Arena, 35 passages par niveau** (`recolte-arena-35.yaml`, 13/11 de 7 h 55
  à 12 h 47, arrêtée de 9 h 36 à 10 h 02 à la demande d'Ethan puis reprise ; 105 passages, 0 panne ; vitrine
  à 20 annonces, 21 pages par passage, moteur navigateur).

  | Niveau | Réussis | Wilson à 95 % | Durée médiane | Échecs |
  |--------|---------|---------------|---------------|--------|
  | 04 | 35 sur 35 | 90,1 à 100 % | 155 s | aucun |
  | 05 | 32 sur 35 | 77,6 à 97,0 % | 162 s | 2 blocages du moteur, 1 erreur réseau du CAPTCHA de test |
  | 06 sans corr. | 35 sur 35 | 90,1 à 100 % | 163 s | aucun |

  102 passages sur 105 ; chaque passage réussi lit 21 pages sur 21 et 280 champs sur 280. Aux niveaux 04 et
  06 sans corrélation, la borne basse passe 90 %. **Au niveau 05, le moteur a été bloqué deux fois** (passages
  34342 à la 8ᵉ page, 34366 à la 13ᵉ) par le détecteur de comportement, signal `trajectoire_lineaire` : angle
  moyen entre les segments de la souris à 0,073 et 0,065 rad, pour un seuil à 0,08. Le troisième échec
  (34335) n'est pas le moteur : le site n'a pas pu joindre Google pour vérifier le reCAPTCHA en clé de test.
  **Mesure du défaut, sur toutes les pages jugées des campagnes 105 à 108 (environ 4 400)** : la valeur
  médiane du moteur est 0,72 rad, loin du seuil, mais 4 pages sont passées dessous (0,050, 0,060, 0,065,
  0,073), toujours avec 10 à 15 angles seulement, donc un mouvement court. Soit environ une page sur 1 000.
  Deux étaient au niveau 04, où ce signal ne bloque pas ; les deux du niveau 05 ont bloqué. À ce rythme, un
  travail de 10 000 pages serait bloqué une dizaine de fois : c'est un défaut du moteur, à corriger (étape
  1.9), et pas un réglage de l'Arena à adoucir. Réserves : CAPTCHA en clés de test aux niveaux 05 et 06 ;
  niveau 06 sans corrélation ; le seuil du détecteur n'est pas calibré sur des humains ; site à nous, une
  machine, un Chrome sur macOS.
- **Campagne 109 : la même, après D-74 (contrôle de la souris)** (14/11 de 4 h 15 à 8 h 54, 105 passages,
  0 panne, même fichier `recolte-arena-35.yaml`, pages du labo inchangées).

  | Niveau | Campagne 108 (avant) | Campagne 109 (après) | Wilson à 95 % (109) | Échecs de la 109 |
  |--------|----------------------|----------------------|---------------------|------------------|
  | 04 | 35 sur 35 | 34 sur 35 | 85,5 à 99,5 % | 1 : `rythme_soutenu` et `pages_eclair` (défaut de l'Arena) |
  | 05 | 32 sur 35 | **35 sur 35** | 90,1 à 100 % | aucun |
  | 06 sans corr. | 35 sur 35 | 35 sur 35 | 90,1 à 100 % | aucun |

  **La souris, objet du contrôle** : moyenne des angles entre segments, par page jugée (au moins 10 angles).

  | | Pages jugées | Minimum | 1 % | Médiane | Sous 0,08 (seuil) | Sous 0,15 (marge) |
  |---|---|---|---|---|---|---|
  | Campagne 108 | 1 997 | 0,050 | 0,121 | 0,720 | 3 | 30 |
  | Campagne 109 | 2 015 | 0,261 | 0,441 | 0,943 | **0** | **0** |

  D-74 est vérifiée dans un vrai Chrome : plus aucune page ne s'approche du seuil, le niveau 05 passe de 32 à
  35 sur 35, les durées ne changent pas (médianes 156, 167 et 162 s contre 155, 162 et 163 s), et chaque
  passage réussi lit toujours 21 pages et 280 champs sur 280. Le banc de mesure sans navigateur avait prédit
  ces valeurs (minimum 0,196, 1 % à 0,43, médiane 0,94).
  **Le seul échec (passage 34409, niveau 04) n'est pas le moteur** : le défi d'entrée s'est résolu en 6 ms, les
  18 photos de la liste sont arrivées dans la foulée, et le détecteur de comportement, qui compte les photos
  comme des pages, a vu 5,3 « pages » par seconde dès la deuxième photo (`rythme_soutenu`, `pages_eclair`). Un
  humain sur une machine rapide serait bloqué de la même façon. C'est le défaut repéré le 14/11 par le rejeu
  du site public ; il tient au hasard de la durée du défi, d'où 0 cas sur 35 à la 108 et 1 sur 35 ici. À
  corriger dans l'Arena. Réserves : inchangées (CAPTCHA en clés de test aux niveaux 05 et 06, niveau 06 sans
  corrélation, aucun humain en base, une machine, un Chrome sur macOS) ; la souris bouge plus qu'avant
  partout (médiane 0,94 au lieu de 0,72), et sans session humaine on ne sait pas si c'est plus proche d'une
  vraie main.
- **D-78 et campagne 110 (14/11) : une photo n'est plus comptée comme une page.** Le détecteur de comportement
  comptait les photos d'une page comme des pages (`rythme_soutenu`, navigation). Corrigé dans l'Arena, test vu
  en échec avant ; les photos restent contrôlées par le gardien, les appels de données restent des pages.
  Rejoué hors ligne : le faux signal apparaissait dans 37 passages de la campagne 108 et 35 de la 109, plus
  aucun après. **Campagne 110** (`recolte-arena.yaml`, 9 h 17 à 9 h 56, 30 passages, 0 panne), non-régression
  dans la vraie Arena : moteur navigateur 15 sur 15 du niveau 02 au niveau 06 sans corrélation (280 champs sur
  280 à chacun), témoin `http` 0 sur 15 (empreinte aux niveaux 02 et 03, défi JavaScript ensuite), aucune
  décision ne cite plus `rythme_soutenu` ni `pages_eclair`. 1 624 tests verts.
  **Faiblesse du moteur trouvée au passage, non corrigée** : après le défi d'entrée, la récolte quitte la
  première vraie page au bout de 55 ms environ (l'interaction humaine a eu lieu sur la page de défi, pas sur
  la page lue). La règle `pages_eclair` ne le voit pas, parce qu'elle fait la moyenne avec la page de défi ;
  une protection plus fine le verrait. À corriger dans le moteur (étape 1.9). Corrigée le jour même : D-79 et
  campagne 111, ci-dessous.
- **D-79 et campagne 111 (14/11) : la première vraie page après un défi dure un temps humain.** Cause du défaut
  ci-dessus : le moteur faisait son interaction (souris, défilement) sur la page arrivée, puis résolvait les
  défis ; la page finale n'en recevait aucune. Corrigé dans `moteur.py` (`navigate` et `click`), 2 tests vus en
  échec avant. **Campagne 111** (`recolte-arena.yaml`, la même que la 110, 10 h 12 à 10 h 53, 30 passages,
  0 panne), avant → après sur la vraie page de liste, 3 passages par niveau :

  | Niveau | Campagne 110 : durée, mouvements de souris | Campagne 111 : durée, mouvements de souris |
  |--------|--------------------------------------------|--------------------------------------------|
  | 05 | 54 à 55 ms, 0 | 8 044 à 10 478 ms, 38 à 67 |
  | 06 sans corrélation | 55 à 71 ms, 0 | 6 242 à 6 609 ms, 47 à 52 |

  Rien n'a régressé : moteur navigateur 15 sur 15 du niveau 02 au niveau 06 sans corrélation (280 champs sur
  280 à chacun), témoin `http` 0 sur 15, aucune décision ne cite `rythme_soutenu`, `pages_eclair` ni
  `trajectoire_lineaire`. Coût : la session médiane passe de 164 à 177 s au niveau 05 et de 163 à 168 s au
  niveau 06 sans corrélation. 1 640 tests verts (10 h 12, avant la campagne). **À relire à la prochaine
  campagne** : au niveau 04, qui résout lui aussi un défi, la page de liste dure 2 026, 3 047 et 12 496 ms à
  la campagne 111, contre 4 084 à 5 610 ms à la 110 ; deux pages sont donc plus courtes qu'avant (20 et 32
  mouvements de souris, loin du seuil de 500 ms de `pages_eclair`), cause non cherchée, 3 passages seulement.
  Réserves : 3 passages par
  niveau ; le défaut n'était vu par aucun détecteur de l'Arena, donc la correction ne change aucun taux de
  passage ici, elle retire un signe qu'une protection plus fine pourrait lire ; `pages_eclair` fait toujours
  la moyenne avec les pages de défi ; aucun humain en base pour dire ce qu'est une durée « humaine ».
- **D-82, D-83 et campagne 112 (14/11) : la récolte survit à l'expiration du laissez-passer.** Jusqu'ici, un défi
  qui revenait en plein travail arrêtait la passe, et le cookie de défi de l'Arena vit une heure : aucune passe de
  plus d'une heure n'était possible. Deux changements, chacun avec ses tests vus en échec avant : la durée du cookie
  est un réglage du profil (D-82 ; profils de mesure à 600 s, `04court`, `05court`, `06scorrcourt`), et la récolte
  peut repasser la porte en cours de passe, sur option, sans aucune action, de façon bornée et tracée (D-83).
  **Campagne 112** (`recolte-arena-cookie-court-essai.yaml`, vitrine à 150 annonces, 11 h 49 à 12 h 52, 3 passages,
  0 panne, moteur navigateur en identité native) :

  | Niveau (cookie de 600 s) | Pages | Champs | Durée | Retours du défi, écart depuis le passage précédent | Défis de la même rafale |
  |--------------------------|-------|--------|-------|-----------------------------------------------------|-------------------------|
  | 04 | 158 sur 158 | 2 100 sur 2 100 | 1 194 s | 1 : 601 s | 0 |
  | 05 | 158 sur 158 | 2 100 sur 2 100 | 1 369 s | 2 : 592 s, 582 s | 2 (23 s et 36 s après) |
  | 06 sans corrélation | 158 sur 158 | 2 100 sur 2 100 | 1 248 s | 2 : 612 s, 589 s | 1 (19 s après) |

  Chaque retour tombe à l'expiration du cookie (582 à 612 s pour 600 s) : aucun n'est un soupçon de l'Arena. La
  porte est repassée sans attente (le pilote lève le défi pendant la lecture, la récolte ne fait que relire la
  page). Les rafales existent bien aux niveaux 05 et 06 (un cookie par défi) : la règle « un seul passage par
  rafale » était nécessaire. Aucune page de moins de 500 ms sur 491 relevés de comportement, aucune décision ne cite
  `rythme_soutenu`, `pages_eclair` ni `trajectoire_lineaire`. Page de liste au niveau 04 (point à relire de la
  campagne 111) : la vraie page après le défi dure 4,8 s, rien d'anormal. Suite complète avant la campagne :
  1 714 tests verts (11 h 49). Réserves : un passage par niveau ; cookie raccourci à 600 s, le cookie d'une heure
  n'est toujours pas mesuré sur une passe de plus d'une heure ; aux niveaux 05 et 06 les défis repassés sont des
  CAPTCHA en clés de test (`captcha_test`), levés par le pilote sur notre Arena : sur un site tiers, seul un défi
  qui se valide seul serait repassé ; niveau 06 sans corrélation ; aucun humain en base. Suite : le long parcours,
  `recolte-arena-cookie-court.yaml` (427 pages, quatre à cinq retours du défi par passage), lancé à 12 h 53.

## 3. Pourquoi on a perdu du temps

- Pas de définition de « fini » : la cible a changé trois fois en trois jours.
- On a empilé des détecteurs au lieu de mesurer : le 11/11, 6 commits de fonctionnalités, 0 campagne.
- Des chiffres ont été annoncés sans référence humaine, et un calcul de taux était faux.
- Deux synthèses concurrentes non versionnées, un `contexte.md` resté au 03/11.

## 4. Les quatre paliers

Chaque palier se termine par des chiffres et une PR vers `master` (fusion par Ethan). On ne commence pas
un palier avant la fin du précédent, sauf mention « en parallèle » et sauf pendant une longue exécution :

- Les longues exécutions (2.8 : 7 jours ; 4.3 : 3 jours) tournent sur une **copie figée du code**
  (étiquette git), dans un dossier à part et sur un autre port, sans mesure de CPU ni de durée.
- Leur état est en base : une panne de Docker ne les annule pas, elles reprennent où elles en étaient.
- Le développement du palier suivant continue pendant ce temps.

### Palier 1 — Récolte et discrétion sur le poste

But : on mesure juste, l'Arena est crédible, le moteur récolte tout et passe.

| # | Étape | Fin vérifiable |
|---|-------|----------------|
| 1.1 | **Sol propre.** Committer les fichiers non suivis utiles, ignorer `.DS_Store`, `*.db-wal`, `*.db-shm`, pousser la branche (sur accord d'Ethan) | `git status` propre, branche poussée |
| 1.2 | **Mesure fiable.** Les pannes sortent du taux de détection ; une campagne s'arrête après 3 pannes d'Arena de suite ; le calcul d'empreinte lit la vraie forme des données | Tests unitaires ; le rapport de la campagne 86 affiche un taux ≤ 100 % ; un hash canvas présent sur des données réelles |
| 1.3 | **Campagne de référence.** `configs/experiments/reference-palier1.yaml` : noezia, patchright, playwright × niveaux 01 à 07 × 3 scénarios (dont `pagination`, plusieurs pages) × 5 répétitions = 315 passages, site et Arena relancés avec le code courant | Tableau moteur × niveau en base, < 5 % de pannes. Première mesure de D-47 à D-53 |
| 1.4 | **Site vitrine à contenu connu.** Contenu généré à partir d'une graine, taille réglable, fiches à plusieurs champs, pages de détail, images, liste chargée en JavaScript, espace privé, export de la vérité, apparence crédible. Thème : annonces immobilières fictives (choix de Claude) | Un parcours complet par un moteur témoin au niveau 01 égale la vérité à 100 % |
| 1.5 | **Scénario de récolte et notation.** Complétude et exactitude, sans migration (compteurs dans `details`), visibles dans les rapports | Tests ; playwright au niveau 01 obtient 100 % et 100 % ; tableau moteur × niveau avec les deux notes |
| 1.6 | **Application publique réduite.** La vitrine sans espace privé ni connexion, les sessions humaines et la collecte, rien d'autre (§ 5). Pas de Nginx, pas de Coraza, pas de niveaux : une simple application Python | Tests : `/api`, `/labo`, `/tableau`, `/api/docs` répondent 404 ; liste du § 5 cochée ; mise en ligne par Ethan |
| 1.7 | **Sessions humaines et calibrage.** Au moins 10 sessions sur ordinateur en tout (Ethan et amis, navigateurs variés). Les sessions enregistrées sont **rejouées** contre les détecteurs de chaque niveau : on obtient le taux d'humains classés automatisés par niveau sans faire passer les humains par l'Arena. Ajouter ce rejeu et la clôture automatique des sessions. Un détecteur gardé classe au plus 1 humain sur 10 en automatisé ; sinon il est recalibré ou retiré (`cdp` en premier). L'Arena doit bloquer, pas seulement classer | **Jalon A** : l'Arena bloque les moteurs témoins (playwright, selenium) et, par rejeu, laisse passer ≥ 9 humains sur 10 à chaque niveau |
| 1.8 | **Mesure témoin contre Cloudflare.** Dès que le site public est derrière Cloudflare gratuit : 30 passages noezia + playwright depuis le poste. Une mesure, pas un critère | Un taux chiffré, noté ici |
| 1.9 | **Corriger le moteur**, dans l'ordre des signaux mesurés en 1.3, 1.7 et 1.8. Une correction = une campagne avant/après | Seuils « Récolte » et « Discrétion » atteints depuis le poste |

Limite du calibrage public : le site public n'a ni le frontal TLS ni la chaîne Nginx et Coraza. Les
détecteurs TLS et HTTP/2 se calibrent en local, avec les navigateurs d'Ethan à travers l'Arena.

Point connu pour 1.7 (mesuré le 12/11 dans un navigateur) : la sonde d'empreinte attend des images
d'animation sans délai maximum. Fenêtre visible : l'empreinte part en 0,2 seconde. Onglet en arrière-plan
ou fenêtre masquée : elle ne part qu'au retour au premier plan. Les participants doivent garder l'onglet
visible ; un délai maximum sur cette sonde est à envisager, suivi d'une campagne.

Point connu pour 1.7 et 2.1 : le détecteur de corrélation, réparé en 1.2, classe « recyclée » toute
empreinte vue 5 fois. Un humain qui revient, ou une identité persistante (palier 2), a par nature la même
empreinte : il faudra compter la même empreinte sur des cookies, comptes ou adresses différents, pas ses
simples retours. La table est globale : les résultats des niveaux 06 et 07 dépendent de l'historique.

Outil prêt pour 1.7 (12/11, D-56) : `uv run shadowlab rejeu` (base du labo) ou
`uv run shadowlab rejeu --base <fichier>` (base du site public, lue sans écrire) donne par niveau les
humains arrêtés, avec le détecteur et les signaux responsables. Il clôt d'abord les sessions manuelles
restées ouvertes sans activité depuis 10 minutes. Il ne dit rien du TLS et du HTTP/2 pour une session faite
hors du frontal, ni de la corrélation, ni des pièges : la sortie les liste comme « non évalués ».

Points connus pour 1.7, relevés le 12/11 dans la configuration et sur une session d'essai faite dans un
navigateur piloté par outil (ce n'est pas une session humaine) :
- Les photos de la vitrine et l'appel « similaires » comptent comme des pages pour les détecteurs
  (`Observations.documents`) : 26 des 31 « pages » de la session d'essai étaient des photos. L'effet sur
  `comportement` et sur le score composite se lira dans le rejeu des vraies sessions.
- Un visiteur qui revient a les scripts en cache et ne les redemande pas : le signal `sans_ressources`
  se déclenche. À lire dans le rejeu dès la 2ᵉ session d'un même navigateur.
- Les photos passent par la limite de débit de Nginx (seuls `/lab/static`, `/lab/collecte`, `/lab/verdict`,
  `/lab/defi` et `/lab/captcha` y échappent). Une page de liste demande 20 photos d'un coup ; la rafale
  permise est de 15 au niveau 04, 8 au 05, 4 au 06 et 2 au 07. À ces niveaux, une partie des photos reçoit
  donc un 429, pour un humain comme pour un moteur. Effet sur le verdict d'un passage : non mesuré.

Points connus pour 1.7 et 1.9, lus le 12/11 dans les relevés de comportement de la campagne 94 (passages
`pagination` de NOEZIA au niveau 05 sans `cdp`) — hypothèses à confirmer par le rejeu des sessions humaines :
- **`pas_de_scroll` se déclenche sur une page qui ne peut pas défiler.** `/lab/catalogue` tient en 10 lignes,
  bien moins haut que la fenêtre. Le moteur tourne la molette sur 7 des 31 pages relevées (12 à 48 crans)
  mais le navigateur n'émet aucun événement de défilement : 0 sur les 31 pages. La règle compte les
  défilements sans savoir si la page est plus haute que la fenêtre. Un humain y serait classé de même.
- **`pas_de_pause` ne lit que les 50 premiers délais de souris d'une page** (borne de l'observateur). Un seul
  geste continu de 50 événements, soit environ 1,5 seconde, suffit : c'est le cas d'une page par passage
  arrêté (délai maximal 58 à 60 ms sur 50 délais, alors que la page dure 2,7 à 3,4 s). Très probable aussi
  chez un humain qui balaie l'écran en arrivant.
- **`device_memory_invalide` (détecteur `coherence-profonde`) n'admet que 8 Go au plus.** Le Chromium 156
  des témoins annonce 32 sur ce poste, et Chrome a relevé ses paliers en 2026 (2, 4, 8, 16, 32 hors
  Android, [annonce Blink](https://groups.google.com/a/chromium.org/g/blink-dev/c/vXtAmrVZeDk)). Tout
  humain sur une machine de 16 Go ou plus serait classé : 0,5 point, presque le seuil du niveau 05 à lui seul.
- **`Accept-Language`** : Chrome prévoit de réduire l'en-tête à la première langue et sa langue de base
  (`fr-FR,fr;q=0.9`, [annonce Blink](https://groups.google.com/a/chromium.org/g/blink-dev/c/NBEBB81RjaI)),
  ni la liste complète ni la langue seule que NOEZIA envoie selon la requête. À lire sur le Chrome d'Ethan.
- **Relevés par la relecture du code du 12/11, à lire dans le rejeu avant de corriger :**
  `pas_de_scroll` (D-61) se fie à ce que dit la page : une fenêtre plus haute que toutes les pages la fait
  taire, et rien ne compare la hauteur de la fenêtre à celle de l'écran (une telle règle classerait peut-être
  un humain qui dézoome : à mesurer d'abord). Un seul signal faible suffit aux niveaux 06 et 07 (seuils
  composites 0,5 et 0,3) : un humain qui lit le haut de deux longues pages sans défiler y serait arrêté.
  Le détecteur `scroll` classe sans doute une molette de souris sous Windows (crans tous égaux à 100) : onze
  crans donnent `deltas_uniformes` et `scroll_regulier`, soit 1,3. Aucune session Windows n'existe encore.
- Conséquence : `pas_de_scroll` et `pas_de_pause` font le score composite 0,85 qui arrête NOEZIA au niveau 05. Ne pas
  « corriger le moteur » sur eux avant d'avoir le taux humain ; si les humains les déclenchent, c'est le
  détecteur qu'on corrige (hauteur de page dans le relevé, pauses cherchées sur toute la page).

En parallèle possible : 1.2 et 1.4 (fichiers distincts). 1.9 est la seule étape dont la taille est
inconnue : elle sera chiffrée après 1.3, 1.7 et 1.8, pas avant.

### Palier 2 — Une identité qui dure

But : un seul compte connecté travaille 7 jours sans être banni.

| # | Étape | Fin vérifiable |
|---|-------|----------------|
| 2.1 | **Arena : mémoire des visiteurs.** Migration 9 : visiteurs, bannissements, comptes. L'état est rattaché à un « monde » remis à zéro explicitement (sinon une campagne influence la suivante). Une requête sans jeton est protégée aussi | `PRAGMA user_version` = 9 ; test |
| 2.2 | **Arena : bannir par cookie durable et par empreinte**, lu en tête du gardien | Test : un visiteur détecté qui revient avec un nouveau jeton reçoit 403. Campagne : playwright banni au 2ᵉ passage, 0 humain banni sur 10 |
| 2.3 | **Arena : comptes.** Table de comptes, bannissement du compte, « nouvel appareil » | Test : un compte banni est refusé depuis un autre navigateur |
| 2.4 | **Arena : compteurs par heure et par jour**, horloge injectable. Plus un **profil « endurance »** pour les longues exécutions : détecteurs calibrés du niveau 06, connexion, bannissement, compteurs ; une seule porte d'entrée (défi JavaScript) par cookie valable 24 h ; aucun CAPTCHA en clés de test | Test : 2 000 pages en 24 h → bannissement ; 40 pages par jour pendant 7 jours → aucun |
| 2.5 | **Moteur : identité persistante.** Un dossier par identité (profil, stockage du navigateur, journal), même empreinte à chaque visite, système du profil = système de la machine | Test : connexion, fermeture, relance, espace privé atteint sans se reconnecter ; empreinte identique côté site |
| 2.6 | **Moteur : sentinelle.** Chaque navigation rend « ok », « alerte » ou « banni » ; un mode arrête tout au premier signe, sans réessai ni résolution de défi. La sentinelle distingue la **porte d'entrée attendue** (un défi servi à tout visiteur, déclaré pour la cible) du **signe d'alerte** (403, 429, défi en cours de session, retour à la connexion, compte suspendu) | Tests 403, 429, défi en cours de session, retour à la connexion : zéro requête après le signe ; la porte d'entrée ne déclenche pas l'arrêt |
| 2.7 | **Moteur : budget par identité.** Pages par heure, plages horaires, pauses longues, horloge injectable | Test en temps simulé sur 7 jours : plafonds respectés |
| 2.8 | **Scénario « suivi »** : la même identité connectée revient toutes les heures | Une exécution réelle de 7 jours : zéro bannissement |

En parallèle possible : 2.1 à 2.4 (Arena) et 2.5 à 2.7 (moteur).

### Palier 3 — Serveur et Cloudflare réel

But : les mêmes chiffres depuis un serveur Linux, contre une vraie protection.

| # | Étape | Fin vérifiable |
|---|-------|----------------|
| 3.1 | **Essai de fumée Linux.** Conteneur sans carte graphique sur le poste : noezia × niveaux 01 à 06 × 5, sans écran puis avec écran virtuel. Simple vérification que tout démarre : le conteneur du poste est en ARM alors que le moteur annonce x86 sous Linux | Les passages s'exécutent ; les incohérences vues sont listées |
| 3.2 | **Proxy par identité**, avec identifiants (jamais dans le code) | Test : deux identités sortent par deux adresses |
| 3.3 | **Vrai serveur** (x86_64, Docker). L'Arena tourne **sur le serveur lui-même** et la campagne de référence s'y lance sans proxy : on mesure l'effet de Linux sans carte graphique | Écart ≤ 5 points avec le poste, niveau par niveau |
| 3.4 | **Cloudflare réel**, depuis le serveur et à travers le proxy résidentiel : site vitrine public derrière Cloudflare, 30 passages noezia + playwright en témoin, comptés selon le § 1. Score reCAPTCHA v3 relevé. tor-i est une seconde cible si Ethan fournit un environnement ; le palier se clôt sur la vitrine seule | ≥ 90 % de passages réussis, témoin arrêté ; rapport |

### Palier 4 — Plusieurs identités

But : 10 000 pages en 3 jours sans que le travail s'arrête.

| # | Étape | Fin vérifiable |
|---|-------|----------------|
| 4.1 | **Arena : adresses IP simulées** (protocole PROXY accepté depuis la machine locale) et bannissement par IP | Test : deux adresses distinctes en base, adresse forgée ignorée |
| 4.2 | **Moteur : gestionnaire d'identités.** File d'adresses à récolter en SQLite, un proxy par identité, réaffectation quand une identité tombe | 1 000 pages avec une identité bannie exprès : 100 % récupérées, aucune graine, aucun proxy ni cookie partagé |
| 4.3 | **Endurance en volume** sur le site vitrine porté à plus de 10 000 pages | 10 000 pages en 3 jours, moins de 10 % des identités perdues |
| 4.4 | **Livrable final** : README, commande de récolte documentée | Un clone neuf, `uv sync`, une commande → une récolte |

## 5. Avant la mise en ligne du site vitrine (étape 1.6)

Le labo ne se met jamais en ligne tel quel : son API lance des navigateurs vers n'importe quelle adresse.

1. Une application publique distincte : vitrine, sessions humaines, collecte. `/api`, `/labo`, `/tableau`,
   `/api/docs`, la page de connexion de test et la démo reCAPTCHA v3 sont absents, pas seulement protégés.
2. Une base séparée, sans frontal ni moteurs.
3. La liste des hôtes servis est séparée du périmètre du moteur (aujourd'hui c'est la même variable).
4. La collecte est refusée hors d'une session consentie en cours ; quotas par session, débit par adresse.
5. Aucune requête vers un tiers avant ou après le consentement : retirer l'appel WebRTC vers un serveur de
   Google, ne charger ni Turnstile ni reCAPTCHA.
6. Page d'information complète (données collectées, durée, responsable, droits), consentement avant toute
   collecte, bouton « supprimer ma session » qui couvre toutes les tables, purge après une durée fixée.
7. HTTPS, cookies sécurisés, journaux sans adresse complète ni jeton.
8. Aucun secret dans le dépôt (contrôle de l'historique avant publication).

Point 8 contrôlé le 12/11 sur les 161 commits de toutes les branches (recherche par motifs dans les lignes
ajoutées, fichiers sensibles ajoutés un jour) : aucun secret, seulement des clés de test publiques de Google
et de Cloudflare et des adresses d'exemple. À refaire juste avant de publier le dépôt.

## 6. Gelé (rien de tout cela avant la fin du palier 4)

Niveau 07 comme cible (il est mesuré, pas visé), couche IA, plugins (`plugins/` est vide : à laisser),
nouveaux moteurs, nouveaux détecteurs d'empreinte, tableau de bord, ergonomie du parseur « façon Scrapling ».
Une idée hors plan s'ajoute ici, pas dans le code.

Code mort signalé, non supprimé : `engines/noezia/pool.py` (appelle une classe et deux méthodes qui
n'existent pas ; rien ne l'importe). À supprimer avec l'accord d'Ethan ; le palier 4 le remplace.

## 7. Ce qu'on attend d'Ethan

| Quoi | Pour |
|------|------|
| Accord pour committer et pousser la branche | 1.1 |
| Mise en ligne de l'application publique (`docs/site-public.md`) : une machine qui fait tourner une application Python derrière un mandataire HTTPS, un domaine à lui derrière Cloudflare gratuit, et son contact à afficher sur la page d'information (`SHADOWLAB_PUBLIC_CONTACT`). Voie courte demandée le 12/11 : tunnel depuis le poste, `scripts/site-public-tunnel.sh`, à lancer par lui (lien temporaire, ne couvre pas 1.8) | 1.6, 1.8 |
| **Dès maintenant** : 5 sessions humaines en local (10 minutes), fenêtre visible, sur `http://127.0.0.1:8770/manuel` après `uv run shadowlab site`, en visitant aussi `/lab/vitrine` (la liste, une fiche). Arrêter le site, puis `uv run shadowlab rejeu` : il dit, niveau par niveau, si `cdp` et les autres détecteurs arrêtent les humains, donc si les niveaux 04 à 07 valent quelque chose | 1.7, 1.9 |
| Au moins 10 sessions humaines (lui et des amis) sur le site public | 1.7 |
| **Avant d'annoncer le site public (Reddit, amis)** : un nom d'hôte stable (tunnel nommé sur un domaine à lui, pas le tunnel rapide dont l'adresse change à chaque lancement) ; une règle de limitation de débit chez Cloudflare devant le site ; régler `SHADOWLAB_PUBLIC_SESSIONS_PAR_JOUR` ; regarder le site lui-même sur son téléphone (Safari et iPhone jamais essayés) ; dire s'il garde le nom « Mosaïk Démo » | 1.6, 1.7 |
| Accord pour supprimer `pool.py` | 2.5 |
| Un serveur Linux x86_64 avec Docker, et un proxy résidentiel | 3.2, 3.3, 3.4 |
| Une clé reCAPTCHA v3 ; un environnement de tor-i qu'on a le droit de viser (facultatif) | 3.4 |
| Les données de rallye : usage personnel ou produit ? | récolte générale (D-70) |
| L'accord du site de rallye réel avant d'y pointer le moteur (D-30 : sans autorisation, la recette est refusée) | récolte générale (D-70) |
| Les quatre questions de la conception du palier 2 (`docs/recherche/identite-qui-dure-2026-11-12.md` § 10) : mesurer le niveau 06 comme une première visite ; prouver d'abord une identité sans compte ; faire lui-même des visites qui reviennent pendant 3 jours ; faire tourner une course de 7 jours en fond sur le Mac mini | palier 2 |
| Sa décision sur les sites tiers (hors périmètre aujourd'hui) | ne bloque pas la v1 |

Détail et recommandations : `notes/ia/questions-ouvertes.md`.

## 8. Règles de pilotage et suivi

1. Une session = une étape, un critère. On ne passe pas à la suivante sans le chiffre.
2. Tout changement de détection ou de furtivité est suivi d'une campagne. Le journal cite le numéro de
   campagne, et le chiffre écrit est celui de la base.
3. Un détecteur n'est valide que s'il laisse passer les humains.
4. On n'ajoute à l'Arena que ce qu'un palier exige.
5. Ce tableau est mis à jour en fin de session.

| Étape | État | Date | Preuve (n° de campagne, commit) |
|-------|------|------|---------------------------------|
| 1.1 Sol propre | **fait** | 11/11 | commits `9a2f0f1`, `f0c2f5e`, branche poussée, `git status` propre |
| 1.2 Mesure fiable | **fait** | 11/11 | commit `74c301a` ; 416 tests rapides verts ; campagne 86 recalculée : 80 % (4/5) au lieu de 440 % ; hash canvas présent sur des données réelles de la base |
| 1.3 Campagne de référence | **fait** | 11/11 | campagne 90 : 315 passages, 0 panne (critère < 5 %), 1 h 52. Tableau et lecture au § 2. Base au schéma 8, sauvegarde `outputs/shadowlab-avant-migration8-2026-11-11.sqlite3` |
| 1.4 Site vitrine à contenu connu | **fait** | 12/11 | `/lab/vitrine`, 440 tests rapides verts. Un parcours HTTP complet (toutes les pages, toutes les fiches) reconstruit la vérité à 100 % (`tests/test_vitrine.py`). Le parcours par un vrai moteur est le critère de 1.5. Rendu vérifié à l'écran, ordinateur et téléphone |
| 1.5 Scénario de récolte et notation | **fait** | 12/11 | commit `34fb564`, 456 tests rapides verts ; test d'intégration : playwright au niveau 01 obtient 1 et 1 ; campagne 91 (essai de durée) ; campagne 92 : tableau moteur × niveau des deux notes au § 2 ; campagne 95 (12/11) : seuil « Récolte » confirmé sur le site à 500 annonces, 9 passages sur 9 sans faute |
| 1.6 Application publique réduite | **en ligne par tunnel rapide depuis le 14/11 (adresse temporaire) ; nom d'hôte stable à faire par Ethan** | 12/11 | `src/shadowlab/public/` (D-55), 570 tests rapides verts dont 114 pour l'application publique ; 12 failles volontaires détectées ; audit indépendant : rien de bloquant, tous les points corrigés ; parcours complet rejoué dans un navigateur (accord, collecte, « Ma session », fin, suppression). Reste : hébergement, domaine, contact (`docs/site-public.md`). 12/11 : voie courte par tunnel Cloudflare, `scripts/site-public-tunnel.sh` (`ccf24c9`), jamais lancé avec un vrai tunnel ; le lancement revient à Ethan **Refaite le 14/11 pour une étude ouverte à une communauté** (demande d'Ethan le 13/11 au soir, cadrage `docs/recherche/site-public-communaute-2026-11-13.md`) : accueil « Humain ou robot ? » en deux langues, faux réseau social de photos « Mosaïk Démo » (93 photos libres créditées), relevé enrichi des gestes (`releve.js`, D-76), fréquentation par jour (D-75), quatrième relecture indépendante : 15 défauts prouvés par des tests, tous corrigés (D-77). 1 552 tests rapides verts dans la branche du site, fusion `346f4b6`. Parcours complet vu à l'écran (téléphone et ordinateur) et rejoué par `shadowlab rejeu --base`. Avant une annonce publique, à la charge d'Ethan : nom d'hôte stable, limitation de débit chez Cloudflare, plafond de sessions (`docs/site-public.md`, « Avant d'annoncer le site publiquement »). Non essayé : Safari, iPhone, Firefox. **Mis en ligne le 14/11 à 11 h 06** par le tunnel rapide, lancé par l'assistant à la demande d'Ethan (« publie le vite stp »), plafond à 150 sessions par jour. Vérifié par l'adresse publique : pages servies, routes du labo en 404, pages identiques à la version locale, photos non gardées en cache par Cloudflare, session d'essai (accord, promenade, relevé reçu en 204, « Ma session », suppression), aucune adresse IP ni en-tête de Cloudflare en base ; session d'essai effacée. L'adresse change à chaque lancement. Le même jour, sur le retour d'Ethan (« trop long », « tu mention noezia faut pas du tout ») : accueil en une phrase et un bouton (D-80), plus aucun nom du projet dans ce que le site sert, script compris (D-81) ; 1 650 tests rapides verts, session d'essai par l'adresse publique |
| 1.7 Sessions humaines et calibrage | **outil prêt, attend les sessions** | 12/11 | `shadowlab rejeu` (D-56, `1f2e3b4`) ; aucune session humaine en base. Préparé sans humains : ablations 93 et 94 (§ 2), trois défauts de l'Arena corrigés (`1f2e3b4`, `c2fbdfc`, `f713b39`), un quatrième trouvé au niveau 07 (WAF, § 2). Attend 5 sessions locales d'Ethan, puis ≥ 10 sessions publiques. Campagne 97 (12/11, § 2) : un vrai Chrome est arrêté aux niveaux 04 à 07 par quatre signaux, corrigés par D-66 ; campagne 98 (12/11, § 2) : contrôle fait, `noezia` en identité native passe les niveaux 04 à 06 sans corrélation (15 sur 15 chacun), le même Chrome sans le comportement de noezia est arrêté pour absence d'interaction, le témoin reste arrêté ; campagne 100 (12/11, § 2) : `noezia` en identité native, 30 passages par niveau, 179 sur 180 (01 à 05 : 30 sur 30 ; 06 sans corrélation : 29 sur 30, un blocage du WAF corrigé par D-69) ; campagne 101 (12/11, § 2) : niveau 06 complet, 0 sur 15 (corrélation) |
| 1.8 Mesure témoin Cloudflare | à faire (attend le domaine) | | |
| 1.9 Corriger le moteur | **direction mesurée** | 12/11 | Campagnes 97 et 98 (§ 2) : identité native, 15 sur 15 aux niveaux 01 à 06 sans corrélation ; l'identité réécrite fuit. Campagne 100 (12/11, § 2) : 30 passages par niveau, 179 sur 180, taux observé ≥ 90 % à chaque niveau (06 sans corrélation : 29 sur 30, le seul échec est un défaut du WAF, D-69), borne basse de Wilson sous 90 % partout, `captcha_test` aux niveaux 05 et 06. Campagne 101 (§ 2) : niveau 06 complet, 0 sur 15 (`recycling_canvas`). Reste : en faire le réglage de référence du moteur, corrélation, humains Campagne 108 (13/11) : premier blocage du moteur en identité native sur une récolte, au niveau 05, signal `trajectoire_lineaire` (2 passages sur 35 ; environ une page sur 1 000 sous le seuil sur 4 400 pages) : corrigé par D-74 (tremblement visible au pixel) et vérifié par la campagne 109 (14/11) : 0 page sur 2 015 sous la marge (30 sur 1 997 avant), niveau 05 à 35 sur 35. D-79 (14/11, fusion `8983345`) : après un défi, la première vraie page était quittée en 54 à 71 ms sans un geste (campagne 110) ; elle dure 6,2 à 10,5 s avec souris et défilement à la campagne 111, 15 sur 15 inchangé, témoin 0 sur 15 |
| Récolte générale (commande `shadowlab recolte`, D-70) | **commande fusionnée, prouvée au niveau 01 et, en navigateur, par l'Arena jusqu'au niveau 06 sans corrélation (3 passages de 21 pages par niveau ; 427 pages d'une seule session aux niveaux 04, 05 et 06 sans corrélation)** | 13/11 | Commit de fusion `b1a40ed` (accord d'Ethan à 21 h 40) ; campagne 102 : 12 passages sur 12 au niveau 01, pages, enregistrements et champs à 100 % avec les deux moteurs sur les deux sites factices. Par l'Arena : campagnes 103 et 104 (0 sur 3 aux niveaux 04 à 06 ; D-71 dans l'Arena, D-72 dans la commande), campagne 105 : 15 passages sur 15 du niveau 02 au niveau 06 sans corrélation, 280 champs sur 280 à chacun. Parcours long : campagne 106 (427 pages aux niveaux 04 et 05, arrêt au niveau 06 : D-73 dans l'Arena), campagne 107 : 427 pages et 34 410 champs sur 34 410 aux trois niveaux ; 1 285 tests verts (fusion `d4e6d4e`). Campagne 108, 35 passages par niveau : 35 sur 35 au niveau 04, 32 sur 35 au niveau 05 (2 blocages du moteur sur `trajectoire_lineaire`, 1 erreur réseau du CAPTCHA de test), 35 sur 35 au niveau 06 sans corrélation. Campagne 109 (14/11, souris corrigée par D-74) : 34, 35 et 35 sur 35, le seul échec est un défaut de l'Arena (D-78, corrigé). Campagnes 110 et 111 (14/11, après D-78 puis D-79) : 15 sur 15 du niveau 02 au niveau 06 sans corrélation, témoin 0 sur 15. 14/11 : la récolte peut repasser la porte en cours de passe (D-83) et le cookie de l'Arena est réglable par profil (D-82) ; campagne 112 (cookie de 600 s, vitrine à 150 annonces) : 3 passages sur 3 aux niveaux 04, 05 et 06 sans corrélation, 158 pages et 2 100 champs sur 2 100 à chacun, le défi revenu 1, 2 et 2 fois et repassé sans arrêt. Reste : une passe de plus d'une heure (le cookie de défi expire : arrêt puis reprise, jamais mesuré) ; aucun vrai site (§ 2). 1.9 et les paliers 2 à 4 restent au plan |
| Palier 2 — Une identité qui dure | à faire | | |
| Palier 3 — Serveur et Cloudflare réel | à faire | | |
| Palier 4 — Plusieurs identités | à faire | | |
