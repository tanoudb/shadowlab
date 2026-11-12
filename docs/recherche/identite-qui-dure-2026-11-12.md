# Une identité qui dure : conception du palier 2

- **Date** : 12/11/2026, soir. **Statut** : document de conception, à valider par Ethan. Aucun code écrit.
- **Lu** : `AGENTS.md`, `docs/PLAN.md`, `docs/DECISIONS.md` (D-45, D-47, D-48, D-59 à D-69), les recherches du
  12/11, le code cité, la branche `recolte-integration` (non fusionnée). Base lue en lecture seule (annexe, Q1
  à Q5). Aucun test, serveur ni navigateur lancé.
- **Légende** : **établi** = vu dans le code, la base ou un document du dépôt (source citée) ; **hypothèse** =
  à mesurer ; **choix** = valeur de départ décidée par Claude ; **estimation** = calcul sans mesure.
- Aucune session humaine en base (Q1) : ce qui est dit des humains vient du code, ou c'est une hypothèse.

## 1. Le problème en cinq lignes

1. En identité native, le moteur passe les niveaux 01 à 06 sans corrélation : 179 passages sur 180
   (campagne 100). Au niveau 06 complet : 0 sur 15 (campagne 101), sur le seul signal `recycling_canvas`.
2. Le détecteur compte les sessions qui ont eu la même empreinte, sur toute la base et depuis toujours. Il
   punit la stabilité : un humain qui revient avec son navigateur serait pris aussi. Défaut de l'Arena.
3. Nos campagnes ont la forme exacte d'un robot : une session neuve et sans cookie à chaque passage, la même
   empreinte, 181 sessions dans l'heure avant la campagne 101 (Q4). Aucun site ne voit cela d'un humain.
4. Une fois l'Arena corrigée, le moteur resterait pris, et à juste titre : il ne garde rien d'un lancement à
   l'autre. La commande de récolte en mode navigateur non plus.
5. L'endurance « une identité » (zéro bannissement sur 7 jours, arrêt seul au premier signe d'alerte) demande
   donc une Arena qui reconnaît un visiteur qui revient, un moteur qui garde son identité, et une mesure qui a
   la forme d'un vrai suivi.

## 2. Humain qui revient, robot qui recycle : ce qui les sépare

Aucun document du dépôt ne décrit la règle d'un vrai fournisseur. La recherche du 12/11 dit seulement qu'ils
croisent plusieurs signaux sans publier leur poids (`chrome-interface-serveur-linux-2026-11-12.md` § 4).

**L'empreinte du navigateur : la même dans les deux cas.**
- Établi : un vrai Chrome qui repasse sans rien réécrire garde son empreinte. `noezia-natif` : 347 sessions,
  un seul profil `a1d51b6565478efc` (Q3). FingerprintJS, chargé par l'Arena, fait justement de l'empreinte un
  identifiant de visiteur, le même en navigation privée (`catalogue.yaml:789-810`) : la stabilité est normale.
- Établi : le canvas dit « ce Chrome sur ce Mac », pas « cette personne ». Le canvas `69eb15db3ac90f9c` est
  partagé par deux configurations distinctes du même Google Chrome 156 (499 sessions, Q3).
- Hypothèse forte, à vérifier sur la première session d'Ethan : son Chrome, sur ce Mac, a ce même canvas.
- L'empreinte seule ne sépare donc rien.

**Un cookie de visiteur durable : le meilleur séparateur.**
- Humain : le site le retrouve à chaque retour, sauf navigation privée ou cookies effacés (fréquence
  inconnue).
- Robot de nos campagnes : jamais. Chaque passage ouvre un contexte neuf (`moteur.py:257`) et le ferme
  (`:339`) : cookies jetés, empreinte gardée (`correlation-entre-sessions-2026-11-12.md` § 3.3).
- Même empreinte + même cookie = un visiteur qui revient. Même empreinte + aucun cookie à chaque fois =
  beaucoup de « nouveaux » visiteurs identiques. Établi comme raisonnement (même document, § 4.1) ; qu'un vrai
  site fasse ce lien : hypothèse (pratique courante, non sourcée dans le dépôt).

**Un historique cohérent : cache, stockage, connexion.**
- Humain : scripts en cache, il ne les redemande pas (plan § 4, point connu pour 1.7) ; une connexion qui
  dure.
- Robot de nos campagnes : cache froid à chaque passage. En identité native, le filtre réseau `route` coupe
  même le cache du navigateur (D-59).
- Ce qu'un vrai site en fait : hypothèse.

**Le rythme des visites.**
- Robot de nos campagnes : 181 sessions natives dans l'heure qui précède la campagne 101, au plus 187 sur 60
  minutes glissantes, 22,5 s d'écart médian entre deux débuts de session (Q4).
- Humain : quelques visites par jour, à intervalles irréguliers (hypothèse).
- Un débit élevé sépare sans doute possible ; un robot lent ne se distingue plus par le débit seul.

**Le volume par visite et par jour.**
- Robot : une passe de récolte lit environ 525 pages en une heure (campagne 95) ; un passage de campagne dure
  7,6 à 15,6 s en médiane (campagne 100).
- Humain : quelques pages à quelques dizaines par visite (hypothèse).

**Les heures.** Humain : heures de veille, fuseau local. Robot planifié : à toute heure, souvent à intervalle
fixe. Deux hypothèses ; signal faible, qui ne s'établit qu'en plusieurs jours.

**Le réseau.** Humain chez lui et robot sur le poste : même adresse dans les deux cas. En local, rien à
séparer : l'Arena ne relève pas l'adresse et tout vient de 127.0.0.1 (`correlation-entre-sessions` § 2.2).
Sur un vrai site, la réputation de l'adresse compte (plan § 1 ; `chrome-interface-serveur-linux` § 3) :
paliers 3 et 4.

**Ce qui sépare vraiment, du plus fort au plus faible** (hypothèse de travail) :
1. une même empreinte portée par beaucoup de visiteurs neufs en peu de temps ;
2. un débit de visites ou de pages qu'aucune personne ne tient ;
3. une empreinte qui change sous un même cookie ;
4. le volume par visite et par jour ;
5. les heures.

L'Arena locale peut juger 1, 2 et 4 dès qu'elle reconnaît un visiteur. Le 3 relève du palier 4. Le 5 demande
des jours.

## 3. Ce que fait l'Arena aujourd'hui

### 3.1 Ce qui est compté

- Deux empreintes par session (`correlation.py:20-51`) : `profil_complet` (agent, plateforme, taille d'écran,
  nombre de cœurs, densité de pixels, langues) et `canvas` (un seul petit dessin fixe).
- Remplies à chaque empreinte reçue, à tous les niveaux de 01 à 07, avant le jugement : `/lab/collecte`
  appelle `enregistrer_hash` (`app.py:435-436`). La session compte dans son propre total.
- `enregistrer_hash` (`correlation.py:54-77`) ajoute 1 par jeton neuf et ne garde que les 10 derniers (`:66`).
- Une « session » est un jeton : paramètre `sl`, sinon cookie `sl_session` (`app.py:64-70`), posé sans durée
  (`app.py:144`). Chaque passage en reçoit un neuf (`passages.py:17-18`). Il n'existe aucun cookie de
  visiteur.
- Durée : aucune. Le compte court depuis la création de la ligne ; ni monde, ni expiration, ni lien vers une
  campagne (`correlation-entre-sessions` § 1.5).
- Débit : sessions commencées dans les 60 dernières minutes (`correlation.py:106-134`), calculé sur les 10
  jetons gardés. Pour une empreinte née plus d'une heure avant, il ne dépasse jamais 10.

### 3.2 Seuils et effet

- `correlation-session` 1.1 (`detection.py:2467-2515`) : ≥ 5 sessions → 0,7 ; ≥ 10 → 1,0 (`:2483-2484`) ;
  ≥ 30 sessions en 60 minutes → 0,8 (`:2485`). « Automatisé » à 1,0 (`detection.py:18`).
- Consulté aux niveaux 06 et 07 seulement (`profils.yaml:219`, `:277`). Seuils composites 0,5 et 0,3
  (`:220`, `:278`) ; famille corrélation multipliée par 1,5 (`scoring.py:63`) : 0,7 × 1,5 = 1,05. Au 06 et au
  07, le moindre signal de comptage bloque.
- Décision à la collecte (`fingerprinting-differe`), puis vérification du défi refusée, `rejete-empreinte`
  (`app.py:489-498`).
- Le rejeu des sessions humaines l'écarte toujours (`rejeu.py:33`, `:140-142`).

### 3.3 Pourquoi elle confond les deux cas

Elle compte des jetons, pas des visiteurs. Un humain qui revient 5 fois avec son navigateur fait 5 jetons :
0,7, donc bloqué au 06 à sa 5ᵉ visite. Une identité qui revient toutes les heures aussi. À l'inverse, une
empreinte qui change passe toujours : une empreinte neuve a le compte 1. La règle punit la stabilité et laisse
passer le changement, l'inverse de ce qu'elle veut attraper.

### 3.4 Ce que dit la base (12/11, après la campagne 101)

- Schéma 9 ; 27 272 passages, 0 humain (Q1).
- `empreintes_vues` : 27 profils, 33 canvas, 1 509 sessions, du 11/11 21 h 25 au 12/11 17 h 05 UTC (Q2).
- Témoins (playwright et patchright, même Chromium) : profil `c93c6fbb57295058` et canvas `2320ef8741fc4143`,
  641 sessions chacun (Q2).
- `noezia-natif` : profil `a1d51b6565478efc`, 347 sessions en 4 h 33 (campagne 96 : 2 ; 97 : 105 ; 98 : 45 ;
  100 : 180 ; 101 : 15). Canvas `69eb15db3ac90f9c` : 499 sessions, soit ces 347 plus 152 de
  `patchright-chrome-interface`, autre configuration du même Chrome (profil `9e0211a64a099746`, écran émulé
  1280 × 720 contre 1680 × 1050) (Q3).
- Campagne 101 : 15 passages `challenge_non_valide`, 16 décisions `fingerprinting-differe`, toutes sur
  `recycling_canvas`, aucune sur le débit (Q5), alors que 181 sessions natives avaient commencé dans l'heure
  (Q4). Le signal de débit est aveugle au-delà de 10 sessions, comme le notait D-64.
- Correction de la recherche du matin (§ 6, supposition) : le canvas de Google Chrome n'est pas celui des
  témoins. Le risque demeure sous une autre forme : un humain avec ce Chrome sur ce Mac aurait probablement le
  canvas `69eb…`, déjà vu 499 fois, et serait bloqué au 06 dès sa première session (hypothèse).

### 3.5 Trois défauts voisins, de la même famille

- `sans_ressources` (détecteur `comportement`, `detection.py:605-606`, poids 0,5) : un visiteur qui revient
  avec les scripts en cache ne les redemande pas (plan § 4). Au 06, 0,5 × 1,0 (`scoring.py:62`) atteint seul
  le seuil 0,5 : bloqué. Lu dans le code, non mesuré dans un vrai navigateur.
- Les cookies d'accès (défi, Turnstile, reCAPTCHA, connexion) sont liés au jeton, valables 1 h, et posés sans
  durée (`defis.py:23-24`, `:61-75` ; `gardien.py:243`). Un visiteur qui revient refait tout à chaque visite,
  connexion comprise. Ce n'est pas un bannissement, mais une Arena d'endurance sans « porte d'entrée » par
  visiteur ne ressemble pas à un site réel.
- Le niveau vient du jeton du passage (`frontal.py:444-457`). Sans jeton connu : profil « faible »
  (`frontal.py:41`) et aucun contrôle (`app.py:115-117`). La commande de récolte, qui n'a pas de passage,
  traverse donc l'Arena sans protection.

## 4. Ce que l'Arena devrait faire

### 4.1 Le principe

Une empreinte stable n'est pas suspecte. Sont suspects : la même empreinte sous beaucoup de visiteurs neufs,
et un débit qu'aucune personne ne tient. Il faut deux choses absentes aujourd'hui : reconnaître un visiteur
qui revient, et borner l'historique (un « monde »). Cette section reprend la proposition de
`correlation-entre-sessions-2026-11-12.md` § 4.2, réduite à ce que le palier 2 exige (règle 4 du plan).

### 4.2 Définitions

- **Monde** : un nom ; tous les comptes s'y font ; remise à zéro = monde neuf. Chaque campagne le déclare :
  `monde: passage` (un par passage), `serie` (un par moteur × niveau) ou `campagne`. Les sessions humaines ont
  leur monde à elles, jamais partagé avec une campagne.
- **Visiteur** : cookie `sl_visiteur`, valeur aléatoire signée avec le secret de l'Arena, nom du monde inclus,
  400 jours (la durée maximale de Chrome, `correlation-entre-sessions` § 4.2). Posé à la première réponse s'il
  manque ou ne vaut rien. Le visiteur d'une session est celui de sa première requête.
- **Session neuve** : sa première requête n'apportait pas de visiteur valable dans ce monde.
- **Empreinte E** : un seul hachage de `profil_complet` et `canvas` ensemble (un fait, un signal).

### 4.3 La règle : `correlation-session` 2.0

| Signal | Ce qui est compté, dans le monde | Seuil de départ | Poids |
|---|---|---|---|
| `empreinte_sans_memoire` | sessions neuves portant E dans les 24 dernières heures | ≥ 5 ; ≥ 10 | 0,7 ; 1,0 |
| `debit_empreinte` | sessions portant E commencées dans les 60 dernières minutes | ≥ 30 | 0,8 |

- `empreinte_sans_memoire` ne juge qu'une session neuve. Les retours d'un visiteur connu ne sont jamais
  comptés contre lui : il est jugé sur son débit et son volume.
- `debit_empreinte` juge toute session, sur un compte exact (une ligne par visite, plus de borne à 10).
- Seuils et poids : ceux d'aujourd'hui (D-48), pour ne pas toucher au composite ; à recaler sur les humains.
- Écartée de ce palier : `rotation_empreinte` (un même visiteur, 3 empreintes en 24 h). Notre moteur ne change
  pas d'empreinte, et personne ne la juge aujourd'hui non plus : c'est une capacité neuve, utile au palier 4.
  Écrite, pas construite.

### 4.4 Effet attendu

| Cas | Aujourd'hui, au 06 | Règle 2.0 |
|---|---|---|
| Humain qui revient, même navigateur | bloqué à la 5ᵉ session | jamais pris |
| Identité persistante, une visite par heure | bloquée à la 5ᵉ visite | jamais prise |
| Même empreinte, cookies jetés (nos campagnes) | bloqué (347 vues) | pris à la 5ᵉ session neuve en 24 h |
| Identité qui visite 30 fois en une heure | bloquée à la 5ᵉ | prise par le débit |
| Humain en navigation privée, 5 fenêtres en un jour | bloqué à la 5ᵉ | pris (limite, à mesurer) |
| Deux humains, même modèle de Mac, même Chrome | additionnés | additionnés à leur 1ʳᵉ visite |
| Robot qui change d'empreinte et jette ses cookies | jamais pris | jamais pris (palier 4, adresse) |

### 4.5 Ce qui va avec la règle, et rien de plus

- **Le monde dans chaque campagne.** Discrétion : `monde: passage` ; chaque passage est une première visite et
  les passages redeviennent indépendants, ce que suppose l'intervalle de Wilson (`correlation-entre-sessions`
  § 3.4). La corrélation entre sessions se mesure dans les campagnes d'endurance. Cela change la façon de
  compter le niveau 06 de l'objectif : question 1.
- **`sans_ressources` ne juge qu'une session neuve.** Un visiteur connu a le droit d'avoir les scripts en
  cache.
- **Bannissement (étape 2.2 du plan, précisée)** : par visiteur ; par empreinte **pour les seules sessions
  neuves**. Bannir une empreinte pour tout le monde bannirait tous les humains du même modèle de machine.
- **Profil « endurance » (étape 2.4)** : une seule porte d'entrée (défi JavaScript) par visiteur, cookie lié
  au visiteur et non au jeton, valable 24 h et gardé par le navigateur (posé avec une durée) ; aucun CAPTCHA
  en clés de test ; compteurs de pages par visiteur.
- Les niveaux 01 à 07 gardent leurs cookies d'accès liés au jeton : un humain qui revient y refait le défi
  sans être puni.
- **Mesurer la commande de récolte sans passage** (requête sans jeton protégée) : reporté. La mesure passe par
  des passages de campagne : la première page porte `?sl=<jeton>`, puis le cookie `sl_session` porte le jeton
  (`app.py:142-144`).

### 4.6 Seuils de départ et ce qui les calibrera

Écrits et datés dans `docs/DECISIONS.md` **avant** la première visite du moteur. Aucun ne vient d'une mesure
du moteur.

| Seuil | Départ | Source | Calibré par |
|---|---|---|---|
| sessions neuves par empreinte en 24 h | 5 ; 10 | D-48 | retours humains, fenêtres privées |
| sessions par empreinte en 60 min | 30 | D-48 | plus grand débit humain observé × 3 |
| pages par visiteur en 1 h (bannit) | 240 | choix | plus grand débit humain observé × 2 |
| pages par visiteur en 24 h (bannit) | 2 000 | plan, 2.4 | idem |

- Acceptation : le rejeu des visites humaines (étape I8) ne prend aucun retour d'un humain, et au plus un
  visiteur humain sur 10 en tout (règle de 1.7). Sinon le seuil monte, par une nouvelle décision.
- Limite : avec quelques humains, `empreinte_sans_memoire` ne se calibre pas vraiment (il faudrait beaucoup
  d'humains de même empreinte). On vérifie seulement qu'il se tait sur leurs retours.

## 5. Ce que le moteur doit faire

### 5.1 Garder une identité

- Ce que recommande Patchright, la base du moteur : `launch_persistent_context(user_data_dir=…,
  channel="chrome", headless=False, no_viewport=True)`, sans agent ni en-tête imposés
  (`chrome-interface-serveur-linux-2026-11-12.md:26`). D-59 le note : « Non couvert : le profil persistant ».
  Des outils du catalogue gardent leurs sessions de même : dossier de profil (`catalogue.yaml:467`), pool de
  sessions et de cookies (`:63`).
- Option `identite: <nom>` du moteur, déclarée dans `options_permises`, acceptée seulement avec
  `identite_native: true` et `headless: false`. Avec l'identité réécrite, le profil tiré à chaque `open()`
  (`moteur.py:184-189`) changerait l'empreinte sous le même cookie : le motif de rotation.
- Cycle de vie en mode identité : `start_session()` lance Chrome sur le dossier de profil, avec le verrou
  réseau du périmètre comme aujourd'hui (`moteur.py:200-223`), et ouvre un onglet ; `close_session()` ferme
  Chrome proprement. Le profil est écrit sur le disque ; les cookies sans durée disparaissent, comme chez un
  humain qui ferme son navigateur. Une visite = un lancement de Chrome. `campaigns.py` ne change pas
  (`open()` une fois par unité, `campaigns.py:503`).
- Aucune nouvelle tentative en mode identité : `nb_essais` forcé à 1, et 429 jamais réessayé (il est
  aujourd'hui dans `STATUTS_TRANSITOIRES`, `moteur.py:91`, `:409-428`).
- Le filtre réseau `route` reste : il coupe le cache (D-59). Voir risque 3.

### 5.2 Où vit le profil, son nom, sa sauvegarde

```
outputs/identites/<nom>/   (outputs/ est ignoré par git ; dossier en 700)
├── identite.json   nom, créée le, hôtes visés, machine, état (ok, alerte, banni) et depuis quand
├── chrome/         dossier de profil de Chrome : cookies, stockage, cache, historique
├── visites.jsonl   une ligne par visite : début, fin, pages, version de Chrome, statut, alerte
├── verrou          un seul processus à la fois sur une identité
└── sauvegardes/    copies de chrome/, faites Chrome fermé, une par jour au plus, 3 gardées
```

- Nom : minuscules, chiffres et tirets, 40 caractères au plus (`vitrine-suivi`). Une identité = une cible :
  ses hôtes sont dans `identite.json`, et le moteur refuse de s'en servir ailleurs.
- Une identité vit sur une machine : son empreinte en dépend. Sur le serveur du palier 3, ce sera une autre.
- Sauvegarde : seulement contre la panne (profil abîmé). Restaurer une copie d'avant un bannissement est
  interdit : ce serait tricher sur la mesure, et inutile (même empreinte, même cookie, connus du site).
- Disque presque plein sur ce poste : vérifier la place (`df -h /`) avant la course de 7 jours.

### 5.3 Ce qu'on n'y met jamais

- Le profil Chrome personnel d'Ethan, ses cookies, ses mots de passe. Aucun compte Google connecté, aucune
  synchronisation : elle enverrait cookies et historique hors du poste et relierait l'identité à une personne.
- Un mot de passe en clair : les comptes de test de l'Arena viennent de `site/comptes.py`, un vrai identifiant
  viendrait de `.env`, jamais de `identite.json`. Le moteur refuse l'enregistrement que Chrome propose.
- Une extension ; les données d'un autre projet (cloisonnement) ; le dossier d'une autre identité. Copier un
  profil pour faire une seconde identité leur donnerait le même cookie, ce que le palier 4 interdit.

### 5.4 Le rythme d'un visiteur régulier (étape 2.7)

Un seul ordonnanceur, côté moteur, que suivent la campagne et la commande de récolte. Horloge injectable.

| Réglage | Départ (choix) |
|---|---|
| plage horaire | 8 h à 23 h, heure du poste |
| écart entre deux visites | 45 à 180 min, tirage log-normal, médiane 90 min, jamais à heure fixe |
| pages par visite | 5 à 40, médiane 15 |
| plafonds | 120 pages par heure, 200 par jour |
| dans une visite | rythme `prudent` existant (`rythme.py:29`, branche de récolte), comportement humain |

- Ces valeurs décrivent ce qu'un humain fait (estimation), pas ce que l'Arena laisse passer. Elles sont fixées
  sans regarder les seuils du § 4.6. Une mesure ne les change que si elle montre un comportement non humain,
  jamais pour passer juste sous un seuil.
- Volume (estimation) : environ 10 visites et 150 pages par jour. Un suivi incrémental (étape 7 de la récolte)
  tient dans ce budget ; une première récolte des 500 annonces prendrait environ 3 jours. Plus vite, c'est
  plusieurs identités : palier 4.

### 5.5 S'arrêter seul au premier signe d'alerte (étape 2.6)

La sentinelle existe sur `recolte-integration` (`engines/noezia/sentinelle.py`) : statuts 401, 403, 407, 429,
503 (`:25`) ; page de défi de l'Arena ou d'un fournisseur (`:54`) ; adresse finale hors du site ou hors du
motif attendu (par exemple un retour à la connexion) ; sélecteur requis absent sur 3 pages ; plus de 5 échecs
sur 20 pages. Réaction : plus aucune requête, état écrit, reprise conseillée après 1 h (`parcours.py:41`).

À ajouter pour une identité :
- **L'état de l'identité**, pas seulement celui de la passe. Après une alerte : `alerte`, aucune visite avant
  la fin de l'attente (sauf `--maintenant`). Après un refus franc dès la première page (403) : `banni`,
  l'identité ne sert plus jamais et passe aux archives.
- **La porte d'entrée déclarée avec sa durée.** Un défi servi à tout visiteur une fois par 24 h est attendu ;
  le même défi revenu avant la fin de sa durée est une alerte : le site ne reconnaît plus le visiteur.
- **Une session perdue** (renvoyé à la connexion alors qu'on l'était) : déjà couverte par « hors du motif ».
- **Aucune résolution de défi hors de nos sites** : déjà le cas (`navigateur.py:53`, branche de récolte).

### 5.6 Ce qui change pour la commande de récolte en mode navigateur

- Aujourd'hui, une passe ouvre un contexte neuf et le garde jusqu'à la fin (`parcours.py:149-152`, branche de
  récolte). Les cookies passent d'une page à l'autre, pas d'une passe à l'autre : chaque `lancer` ou
  `reprendre` est un visiteur neuf avec la même empreinte. Avec la règle 2.0, la 5ᵉ passe en 24 h serait
  prise, à juste titre.
- Demain, le mode navigateur prend une identité par défaut, au nom de la recette (`--identite <nom>` pour en
  choisir une autre). Il refuse de démarrer si l'identité est en alerte, bannie, ou prise par un autre
  processus.
- Une passe devient une suite de visites : Chrome s'ouvre, lit au plus `pages_par_visite`, se ferme ; la
  commande attend la visite suivante dans la plage horaire (`caffeinate` tient déjà le Mac éveillé). `etat`
  affiche l'heure de la prochaine visite. La reprise après coupure existe déjà (`etat.sqlite3`).
- Une alerte de la sentinelle change aussi l'état de l'identité.
- Le mode `http` n'est pas concerné par ce palier.

## 6. Comment on le mesure

### 6.1 Les bras d'une campagne « une identité qui revient »

Profil `endurance` de l'Arena (§ 4.5). Chaque bras a son propre monde : le sujet et le témoin négatif ont la
même empreinte (même Chrome, même Mac), un monde commun les mélangerait.

| Bras | Ce qu'il fait | Doit |
|---|---|---|
| sujet | `noezia` natif, une identité, rythme du § 5.4 | passer à chaque visite |
| témoin négatif | même Chrome, même empreinte, cookies jetés | être pris dès sa 5ᵉ visite |
| témoin classique | `playwright` | rester arrêté (empreinte) |
| témoin de sentinelle | une identité qu'on bannit exprès | 0 requête après le refus |
| humains | visites qui reviennent, rejouées dans leur monde | aucun retour pris |

### 6.2 Une soirée : la répétition

- 24 visites du sujet espacées de 10 minutes (environ 4 h 30 à 5 h, estimation), 15 pages de la vitrine par
  visite. Le témoin négatif en parallèle, au même rythme. Le témoin de sentinelle sur 6 visites, banni à la 3ᵉ
  par une commande de l'Arena.
- Critère :
  - sujet : 24 visites réussies sur 24, le même visiteur et la même empreinte côté Arena à chaque visite
    (base), défi JavaScript vu à la première visite seulement, aucune alerte ;
  - témoin négatif : bloqué à partir de sa 5ᵉ visite, puis banni ;
  - témoin de sentinelle : aucune requête après le premier 403, identité notée `banni`.
- Débits de la soirée : 6 visites et 90 pages par heure, sous les seuils du § 4.6. On teste la mécanique, pas
  l'allure humaine du rythme.

### 6.3 Sept jours : l'objectif

- Copie figée du code (étiquette git), dossier et port à part, sans mesure de processeur ni de durée (plan
  § 4). État en base : une panne de Docker ou une mise en veille ne l'annule pas.
- Sujet au rythme du § 5.4 : environ 70 visites en 7 jours (estimation), récolte incrémentale de la vitrine.
  La taille de la vitrine peut monter chaque jour pour faire des annonces nouvelles (choix, facultatif).
- Critère : **aucun bannissement et aucune alerte sur 7 jours** ; toutes les visites faites aboutissent ; à la
  fin, au moins 99 % des annonces et des champs exacts (seuil « Récolte »). Une visite manquée parce que le
  Mac dormait est comptée à part, pas comme un échec. Le témoin négatif et le témoin de sentinelle tournent le
  premier jour.
- C'est la ligne « Endurance, une identité » du plan (§ 1), contre notre Arena seulement, et sans compte
  connecté si la réponse à la question 2 est oui.

### 6.4 Ce qu'on peut accélérer, ce qu'on ne peut pas

- On peut : vérifier les règles de l'Arena sur 7 jours simulés (horloge injectable, tests) ; rapprocher les
  visites pendant une répétition, tant que tous les débits restent sous les seuils humains.
- On ne peut pas : avancer l'horloge de l'Arena pendant que Chrome vit à l'heure réelle (Chrome compte
  lui-même la durée des cookies : tout serait faussé). Ni simuler l'âge des cookies, la porte d'entrée de
  24 h, les compteurs d'un jour sur l'autre, une mise à jour de Chrome, une veille ou un redémarrage du Mac,
  le rythme jour et nuit. Tout cela demande les 7 jours réels.

### 6.5 Ce qu'une soirée prouve, ce qui demande des jours

- Une soirée peut **réfuter** : si le sujet est pris en 24 retours, ou si le témoin négatif passe, la
  conception est fausse. Elle montre que l'identité survit à 24 relances et que la sentinelle coupe net.
- Elle ne prouve pas l'endurance : 24 visites en 5 heures ne sont pas 70 visites en 7 jours.
- Les 7 jours prouvent l'objectif **contre notre Arena**, pour **une** identité : « c'est possible », pas
  « dans x % des cas ». Les visites d'une identité se suivent et ne sont pas indépendantes : pas d'intervalle
  de Wilson sur elles. Rien ne dit ce que ferait une vraie protection sur 7 jours.

## 7. Les étapes de réalisation

Numérotées I1 à I10. Chacune commence par son test, vu en échec. Tout changement de détection est suivi d'une
campagne (règle 2 du plan).

**I1. Arena : visiteurs et mondes** (précise 2.1). Taille moyenne.
- Livre : migration **10** (la 9 est prise par D-68 : `PRAGMA user_version` vaut 9, Q1) avec les tables
  `mondes`, `visites`, `bannissements` ; cookie `sl_visiteur` signé, posé sur toute réponse `/lab` (pas dans
  l'application publique : il faudrait l'annoncer et le faire accepter) ; champ `monde` des campagnes,
  enregistré avec la configuration ; un monde à part pour `/manuel`.
- Fichiers : `database.py`, `site/app.py`, `arena/visiteurs.py` (neuf), `campaigns.py`, `passages.py`,
  `tests/test_visiteurs.py`.
- Test d'abord : deux jetons du même client → un seul visiteur, 2ᵉ visite non neuve ; cookie falsifié ou d'un
  autre monde → visiteur neuf ; durée de 400 jours ; cookie posé même sans jeton.
- Fin : `user_version` = 10 ; tests et suite rapide verts.
- Parallèle : avec I4, I5, I6.

**I2. Arena : `correlation-session` 2.0** (nouvelle : la règle n'était qu'un « point connu » au § 4 du plan).
Taille moyenne.
- Livre : la règle du § 4.3, en fonction pure (visites du monde, session, heure) ; `sans_ressources` pour les
  seules sessions neuves ; rejeu qui ne voit que les sessions humaines antérieures de leur monde (aujourd'hui
  il lit la table telle quelle, `rejeu.py:150-154`) ; `monde: passage` dans les campagnes de discrétion.
- Fichiers : `correlation.py`, `detection.py`, `site/gardien.py`, `rejeu.py`,
  `configs/experiments/discretion-*.yaml`, `tests/test_correlation_v2.py`.
- Test d'abord : humain qui revient 10 fois (une par jour, puis 5 dans une soirée) → jamais pris (pris à la
  5ᵉ aujourd'hui) ; 5 sessions neuves de même empreinte en 1 h → 0,7, 10 → 1,0 ; 30 sessions en 59 min →
  débit ; 10 sessions en 50 s comptées ; 443 sessions il y a deux jours puis 1 → aucun débit ; même jeton, 20
  empreintes envoyées → compté une fois ; visiteur connu sans ressources → aucun signal.
- Fin : tests verts ; courte campagne au 06 complet : `noezia-natif` en `monde: passage`, 30 passages (le
  chiffre de discrétion du 06 avec corrélation) ; même configuration en `monde: serie`, cookies jetés → prise
  dès le 5ᵉ passage.
- Dépend de I1.

**I3. Arena : bannissement et profil « endurance »** (fusionne et précise 2.2 et 2.4). Grande taille.
- Livre : bannissement par visiteur, et par empreinte pour les sessions neuves, lu en tête du gardien ;
  compteurs de pages par visiteur (heure, jour), horloge injectable ; profil `endurance` (détecteurs du 06,
  règle 2.0, porte d'entrée par visiteur valable 24 h, aucun CAPTCHA en clés de test) ; commande
  `shadowlab arena bannir --visiteur` pour le témoin de sentinelle.
- Fichiers : `configs/arena/profils.yaml`, `arena/profils.py`, `arena/defis.py`, `site/gardien.py`,
  `site/app.py`, `cli.py`, tests.
- Test d'abord (ceux du plan) : un visiteur détecté qui revient avec un nouveau jeton reçoit 403 ; 2 000 pages
  en 24 h → banni ; 40 pages par jour pendant 7 jours → non ; 2ᵉ session du même visiteur dans les 24 h → pas
  de défi.
- Fin : tests verts ; campagne courte : playwright banni au 2ᵉ passage (plan 2.2). Le « 0 humain banni sur
  10 » du plan passe à I8.
- Dépend de I1 et I2.

**I4. Moteur : identité persistante** (précise 2.5). Taille moyenne.
- Livre : option `identite` (§ 5.1 et 5.2) : dossier, verrou, état, refus hors identité native ou sans
  interface, `nb_essais` forcé à 1 ; `configuration()` enregistre le nom et l'âge de l'identité.
- Fichiers : `engines/noezia/moteur.py`, `engines/noezia/config.py`, `engines/noezia/identite.py` (neuf),
  `tests/test_identite.py`, `tests/test_integration.py`.
- Test d'abord : sans navigateur, nom invalide refusé, verrou pris refusé, identité `banni` refusée, option
  refusée avec `identite_native: false`. Avec navigateur (`-m integration`) : deux lancements sur la même
  identité → le site voit le même `sl_visiteur` et la même valeur de `localStorage` ; deux identités → deux
  visiteurs ; le test de redirection hors périmètre couvre aussi le lancement persistant (règle du projet).
- Fin : tests verts. L'intégration a besoin du cookie de I1, ou d'une page de test qui pose un cookie durable.
- Parallèle : avec I1 à I3.

**I5. Moteur : ordonnanceur des visites** (précise 2.7). Petite taille.
- Livre : le § 5.4, une seule source pour la campagne et la récolte.
- Fichiers : `engines/noezia/visites.py` (neuf), réutilise `rythme.py` de la branche de récolte, tests.
- Test d'abord (plan 2.7) : 7 jours en temps simulé → aucune visite hors plage, aucun écart sous 45 min, au
  plus 200 pages par jour et 120 par heure.
- Dépend de la fusion de `recolte-integration` (accord d'Ethan attendu). Parallèle avec la chaîne Arena.

**I6. Moteur : sentinelle d'identité** (précise 2.6). Petite taille.
- Livre : le § 5.5, sur la sentinelle existante.
- Fichiers : `engines/noezia/sentinelle.py`, `engines/noezia/identite.py`, `engines/noezia/parcours.py`,
  `tests/test_sentinelle.py`.
- Test d'abord : 403, 429, défi en cours de visite, retour à la connexion → aucune requête après le signe
  (tests existants, étendus au mode identité) ; identité en alerte → refus avant 1 h ; bannie → refus
  toujours ; porte d'entrée revenue avant 24 h → alerte.
- Dépend de I4 et de la fusion de la récolte.

**I7. Scénario « visite », campagne « une identité qui revient », récolte avec identité** (précise la
première moitié de 2.8). Taille moyenne.
- Livre : scénario `visite` (entre par `?sl=`, lit au plus N pages de la vitrine, note le visiteur vu) ; champ
  `espacement` des campagnes, piloté par I5 ; `configs/experiments/identite-soiree.yaml` (§ 6.2) ; option
  `--identite` de la commande de récolte (§ 5.6).
- Fichiers : `scenarios.py`, `campaigns.py`, `commande_recolte.py`, `engines/noezia/navigateur.py`,
  configurations, tests.
- Test d'abord : scénario avec un pilote factice ; planification des passages avec horloge injectable,
  espacement respecté ; deux `lancer` sur la même recette → même identité.
- Fin : la soirée du § 6.2 tenue, critère chiffré compris.
- Dépend de I2 à I6.

**I8. Humains qui reviennent** (prolonge 1.7). Petite taille côté code ; attend Ethan.
- Livre : protocole court (question 3) ; rejeu de la règle 2.0 et des compteurs sur ces visites.
- Test d'abord : celui du rejeu, écrit en I2.
- Fin : au moins 3 visiteurs humains, 4 retours chacun, sur au moins 2 jours ; aucun retour pris. Sinon les
  seuils montent (nouvelle décision) avant I9.
- Peut commencer dès I1 (le cookie est noté) ; rejeu après I2.

**I9. Course de 7 jours** (seconde moitié de 2.8). Petite taille en code ; 7 jours d'horloge.
- Livre : `configs/experiments/identite-7-jours.yaml`, étiquette git, lancement dans un dossier à part.
- Fin : critère du § 6.3, noté au plan.
- Dépend de I3, I6, I7, I8.

**I10. Comptes** (2.3, gardée). Taille moyenne.
- Livre et test : ceux du plan (un compte banni est refusé depuis un autre navigateur) ; migration 11.
- Après I9, ou avant si la réponse à la question 2 est non.

**Accord avec les étapes 2.x du plan**

| Plan | Ici | Pourquoi |
|---|---|---|
| 2.1 | I1, précisée | migration 10 (la 9 est prise, D-68) ; protection sans jeton reportée ; comptes en I10 |
| aucune | I2, ajoutée | la règle de corrélation n'était qu'un point connu, pas une étape |
| 2.2 et 2.4 | I3, fusionnées | mêmes fichiers ; une empreinte n'est bannie que pour les sessions neuves |
| 2.3 | I10, gardée | après la preuve sans compte (question 2) |
| 2.5 | I4, précisée | contexte persistant, identité native seule, dossier, aucune nouvelle tentative |
| 2.6 | I6, précisée | la sentinelle existe ; on ajoute l'état de l'identité et la durée de la porte |
| 2.7 | I5, précisée | un seul ordonnanceur pour la campagne et la récolte |
| 2.8 | I7 puis I9 | une répétition d'une soirée avant les 7 jours |
| 1.7 | I8, prolongée | des humains qui reviennent, pas seulement des premières visites |

Parallèle : I1, puis I2, puis I3 côté Arena ; I4, puis I5 et I6 (après la fusion de la récolte) côté moteur ;
I8 dès I1 ; I7 réunit les deux ; I9 en dernier. Pendant I9, le palier 3 peut avancer (plan § 4).

## 8. Hors périmètre

- Plusieurs identités, proxys, adresses IP simulées, rotation d'empreinte sous un même cookie : palier 4.
- Serveur Linux et écran virtuel : palier 3. Une identité du Mac ne part pas sur le serveur.
- Compte connecté : au palier 2 dans le plan (2.3) ; ici en dernière étape (I10), selon la question 2.
- Mesurer la commande de récolte sans passage (requête sans jeton protégée) : reporté.
- Mode `http` de la récolte : il ne garde aucun cookie d'une passe à l'autre ; pas traité ici.
- Viser un site tiers : hors du périmètre tant qu'Ethan n'a pas tranché la question ouverte du 11/11 (sites
  tiers, D-30). Ce palier se prouve sur nos cibles. Aucun solveur de CAPTCHA réel, en aucun cas.
- Niveau 07 : gelé (plan § 6).

## 9. Risques et points faibles

1. **Régler l'Arena pour que notre moteur passe.** Nous écrivons le cookie de visiteur de l'Arena et le moteur
   qui le garde : le cercle est réel. Ce qui l'empêche :
   - règles et seuils écrits et datés dans `DECISIONS.md` avant la première visite du sujet ; ensuite, un
     seuil ne bouge que sur des données humaines ou pour un défaut qui touche les humains, suivi d'une
     campagne ;
   - aucune valeur de l'Arena ne vient du moteur, et le rythme du moteur ne vient pas des seuils de l'Arena ;
   - un témoin négatif dans chaque campagne d'endurance, qui ne diffère du sujet que par ses cookies jetés :
     s'il passe, la campagne ne vaut rien ;
   - les humains qui reviennent (I8) valident la règle ; le moteur ne la valide jamais ;
   - une relecture des changements de l'Arena par un agent qui ne voit pas les chiffres du moteur, avec deux
     questions : un humain la déclencherait-il ? le témoin y échapperait-il ?
   - le résultat s'écrit « contre notre Arena ». La vérité extérieure viendra de Cloudflare (1.8 et 3.4), qui
     ne mesurera pas un bannissement sur 7 jours de la même façon (hypothèse).
2. **Ce palier prouve surtout la mécanique** (persistance, rythme, arrêt), pas la discrétion face au modèle de
   long terme d'un vrai fournisseur, qui peut relier les visites par l'adresse, le TLS ou l'historique.
3. **Le cache coupé.** Avec le filtre `route`, l'identité redemande tout à chaque visite, ce qu'un humain qui
   revient ne fait pas. L'Arena ne le juge pas et ne doit pas l'inventer maintenant (règle 4). Retirer le
   filtre touche au périmètre : une mesure avant et après, seulement avec l'accord d'Ethan.
4. **Navigation privée** : un humain qui ouvre 5 fenêtres privées en un jour sur le même Mac serait pris.
   Fréquence inconnue.
5. **Une seule identité, une machine, un Chrome.** Un succès dit « possible », pas plus.
6. **Sept jours sur un Mac utilisé** : veille, redémarrage, mise à jour de macOS ou de Chrome (l'agent change
   sous le même cookie : à noter dans le journal de l'identité), OrbStack arrêté, disque presque plein,
   journaux du WAF qui grossissent.
7. **Porte d'entrée liée au TLS** : au 06, le cookie du défi est lié au JA4 (`profils.yaml:173`). Si le JA4 de
   Chrome changeait d'un lancement à l'autre, la porte reviendrait à chaque visite et la sentinelle
   arrêterait tout. À lire pendant la soirée (défi vu une seule fois).
8. **Détecteurs du 06 pas encore calibrés sur des humains** (1.7 en attente) : le profil `endurance` hérite de
   cette faiblesse.
9. **Dépendance** : I5, I6 et I7 attendent la fusion de `recolte-integration`.
10. **Comparabilité** : les chiffres du 06 des campagnes 94 à 101 dépendent de l'historique global de la
    base ; après I2, ils ne se comparent plus tels quels.

## 10. Questions pour Ethan

1. **Le niveau 06 de l'objectif : le mesurer comme une première visite ?** Chaque passage dans son propre
   « monde » : la corrélation entre visites sort de la discrétion et se mesure dans l'endurance, où elle a un
   sens. *Recommandation : oui.* Sinon le 06 mesure la répétition de nos campagnes, pas le moteur.
2. **Prouver d'abord une identité sans compte ?** Tes besoins (annonces, rallye) sont des pages publiques ; le
   plan parle d'« un compte connecté ». *Recommandation : oui, sans compte pour les 7 jours ; le compte en
   dernière étape.*
3. **Des visites humaines qui reviennent : toi d'abord, sur ce Mac ?** 3 jours, 2 visites de 2 minutes par
   jour, avec Chrome et avec Safari, plus une fenêtre privée un des jours. *Recommandation : oui ; le site
   public plus tard (il faudrait un cookie de visiteur à faire accepter).*
4. **Une course de 7 jours sur le Mac mini, en fond ?** Une visite toutes les 1 à 3 h, de 8 h à 23 h, Chrome
   visible 2 minutes, Docker allumé, Mac tenu éveillé. *Recommandation : oui, après une soirée réussie ;
   sinon, attendre le serveur du palier 3.*

## Annexe : requêtes (lecture seule)

`sqlite3.connect("file:…/outputs/shadowlab.sqlite3?mode=ro", uri=True)` depuis `python3 -I`, le 12/11 au soir.
Les empreintes sont recalculées avec le code de `hash_session` recopié tel quel (`correlation.py:20-51`).

- **Q1** : `PRAGMA user_version` (9) ; `SELECT COUNT(*) FROM runs WHERE truth = 'humain'` (0) ;
  `SELECT COUNT(*) FROM runs` (27 272).
- **Q2** : `SELECT type, COUNT(*), SUM(nb_sessions), MIN(premiere_vue), MAX(derniere_vue) FROM
  empreintes_vues GROUP BY type` ; les 8 lignes au plus grand `nb_sessions`.
- **Q3** : pour chaque passage des campagnes 96 à 101, sa première empreinte (`observations_js`,
  `kind = 'empreinte'`) et le libellé du moteur (`json_extract(engines.configuration, '$.label')`) ; hachages
  profil et canvas, regroupés par campagne et libellé ; langues, écran et agent par profil.
- **Q4** : débuts des passages `noezia-natif` des campagnes 96 à 101 (347) : plus grand nombre sur 60 minutes
  glissantes (187) ; nombre dans l'heure avant le premier passage de la campagne 101 (181) ; écart médian
  entre deux débuts (22,5 s).
- **Q5** : décisions des passages de la campagne 101, par couche et par signal ; `issue` des passages (15
  `challenge_non_valide`) ; décisions citant `velocity_` ou `recycling_` depuis la campagne 96 (101 : 0 et
  16).
