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
interface, identité réécrite), et ce sont ses réécritures qui fuient. Mesure prévue le 12/11 après la
référence : `configs/experiments/ablation-interface.yaml` (patchright avec un vrai Chrome et son interface,
rien d'imposé ; noezia en « identité native », option préparée sur la branche `moteur-identite-native`,
D-59, sans effet par défaut).

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

Aucun détecteur de l'Arena ne relève ces écarts aujourd'hui : leur effet se mesurera contre Cloudflare (1.8).
Deux règles les mesureraient dans l'Arena : « HeadlessChrome » dans un en-tête de n'importe quelle requête
d'une session (pas seulement la première), et une version du `User-Agent` différente de celle de
`userAgentData`. À décider avec Ethan (règle 4 du § 8 : on n'ajoute à l'Arena que ce qu'un palier exige).
Chiffres de ce paragraphe et des deux précédents recomptés le 12/11 par une vérification indépendante.

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
| Accord pour supprimer `pool.py` | 2.5 |
| Un serveur Linux x86_64 avec Docker, et un proxy résidentiel | 3.2, 3.3, 3.4 |
| Une clé reCAPTCHA v3 ; un environnement de tor-i qu'on a le droit de viser (facultatif) | 3.4 |
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
| 1.5 Scénario de récolte et notation | **fait** | 12/11 | commit `34fb564`, 456 tests rapides verts ; test d'intégration : playwright au niveau 01 obtient 1 et 1 ; campagne 91 (essai de durée) ; campagne 92 : tableau moteur × niveau des deux notes au § 2 |
| 1.6 Application publique réduite | **code fait, mise en ligne à faire par Ethan** | 12/11 | `src/shadowlab/public/` (D-55), 570 tests rapides verts dont 114 pour l'application publique ; 12 failles volontaires détectées ; audit indépendant : rien de bloquant, tous les points corrigés ; parcours complet rejoué dans un navigateur (accord, collecte, « Ma session », fin, suppression). Reste : hébergement, domaine, contact (`docs/site-public.md`). 12/11 : voie courte par tunnel Cloudflare, `scripts/site-public-tunnel.sh` (`ccf24c9`), jamais lancé avec un vrai tunnel ; le lancement revient à Ethan |
| 1.7 Sessions humaines et calibrage | **outil prêt, attend les sessions** | 12/11 | `shadowlab rejeu` (D-56, `1f2e3b4`) ; aucune session humaine en base. Préparé sans humains : ablations 93 et 94 (§ 2), trois défauts de l'Arena corrigés (`1f2e3b4`, `c2fbdfc`, `f713b39`), un quatrième trouvé au niveau 07 (WAF, § 2). Attend 5 sessions locales d'Ethan, puis ≥ 10 sessions publiques |
| 1.8 Mesure témoin Cloudflare | à faire (attend le domaine) | | |
| 1.9 Corriger le moteur | à faire | | |
| Palier 2 — Une identité qui dure | à faire | | |
| Palier 3 — Serveur et Cloudflare réel | à faire | | |
| Palier 4 — Plusieurs identités | à faire | | |
