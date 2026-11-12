# Corrélation entre sessions : ce que fait le détecteur, ce qu'il confond, ce qu'il faudrait

- **Date** : 12/11/2026
- **Sujet** : le détecteur `correlation-session` de l'Arena.
- **Base** : `outputs/shadowlab.sqlite3`, lue en lecture seule (`mode=ro`) pendant la campagne 95. Schéma 8.
- **Lecture seule** : aucun test, serveur ni navigateur lancé ; aucun fichier existant modifié. Les requêtes
  sont en annexe (R1 à R9). Chaque chiffre renvoie à l'une d'elles.
- **Limite importante** : aucune session humaine en base (R3). Ce qui est dit des humains vient du code,
  pas d'une mesure. Les suppositions sont marquées **(supposition)**.

Abréviations : `correlation.py`, `detection.py`, `scoring.py`, `database.py`, `campaigns.py`, `passages.py`,
`reports.py`, `rejeu.py` sont dans `src/shadowlab/` ; `app.py` et `gardien.py` dans `src/shadowlab/site/` ;
`observateur.js` dans `src/shadowlab/site/static/` ; `frontal.py` dans `src/shadowlab/arena/` ;
`moteur.py` dans `src/shadowlab/engines/noezia/`.

## En bref

- La règle compte **combien de sessions ont eu la même empreinte**, depuis toujours, sur toute la base. Elle
  ne sait pas si c'est le même visiteur qui revient ou cinq visiteurs neufs. L'Arena n'a d'ailleurs aucun
  cookie de visiteur durable.
- Elle punit donc la **stabilité** (humain qui revient, identité du palier 2, campagne de 15 passages) et
  laisse passer la **rotation** (une empreinte neuve a toujours le compte 1). Le libellé « rotation de
  fingerprint massive » dit l'inverse de ce qu'elle mesure.
- Données : aux niveaux 06 et 07 des campagnes 93 et 94, NOEZIA est classé **à partir du 5ᵉ passage** de
  chaque série (06), et dès le **3ᵉ** au 07 par un calcul de vitesse faux. Les deux témoins partagent **une
  seule empreinte**, vue 443 fois.
- Recommandation : compter les **sessions neuves (sans cookie de visiteur valable)** qui partagent une
  empreinte, la **rotation** d'empreinte pour un même visiteur, et un **débit** sur une vraie fenêtre ; le
  tout **dans un monde** remis à zéro. Une campagne de discrétion met **un monde par passage**.

## 1. Ce que fait le détecteur aujourd'hui

### 1.1 Les deux empreintes calculées

`hash_session` (`correlation.py:18-49`) calcule deux empreintes à partir de l'empreinte JavaScript :

| Empreinte | Champs | Code |
|---|---|---|
| `profil_complet` | `userAgent`, plateforme (`userAgentData.platform`, sinon `navigator.platform`), largeur et hauteur d'écran, `hardwareConcurrency`, `devicePixelRatio`, `languages` | `correlation.py:27-40`, tronquée à 16 caractères hexadécimaux `:45` |
| `canvas` | le texte `canvas` envoyé par la page, s'il n'est pas une erreur | `correlation.py:42`, `:47-48` |

Le `canvas` est un seul dessin fixe de 220 × 40 pixels (un rectangle et le texte « ShadowLab ✓ 2026 » en
Arial), dont la page garde 8 octets du SHA-256 (`observateur.js:83-97`). Les champs viennent de
`collecter()` (`observateur.js:1150-1173`, `:1184`).

Ces deux empreintes ont peu d'entropie. `profil_complet` n'a que six champs. Le `canvas` donne le même
résultat pour le Chromium 156 des témoins (sans interface, WebGL SwiftShader) et pour un Chromium 156 qui
se déclare sans « Headless » et dont le WebGL passe par le GPU Metal, sur ce Mac (R8). Il dit plutôt
« Chromium 156 sur ce Mac » que « cet appareil ».

### 1.2 Qui remplit la table, et quand

- La page envoie son empreinte **à chaque chargement de page** (`observateur.js:1221-1225`).
- `/lab/collecte` l'enregistre, puis appelle `enregistrer_hash` **avant** de calculer la suspicion
  (`app.py:435-441`). La session courante est donc toujours comptée dans son propre total.
- Cela se fait **à tous les niveaux**, de 01 à 07, et même hors de l'Arena : l'appel ne dépend ni du
  profil ni du sceau (`app.py:436`). Seule la décision dépend du niveau.
- `enregistrer_hash` (`correlation.py:52-75`) ajoute 1 à `nb_sessions` si le jeton n'est pas dans la liste
  `sessions`. Cette liste ne garde que **les 10 derniers jetons** (`correlation.py:63-64`). Une même session
  pourrait donc être recomptée si plus de 10 autres sessions de même empreinte s'intercalent entre deux de
  ses pages. Cela ne s'est pas produit à ce jour : le compte de la table égale exactement le nombre de
  sessions distinctes (R3).
- Une « session » est un **jeton** : le paramètre `sl` de l'adresse, sinon le cookie `sl_session`
  (`app.py:64-70`). Chaque passage de campagne et chaque session manuelle reçoit un jeton neuf
  (`passages.py:18`, `:21` ; `app.py:665-684`).
- Le site public ne remplit pas la table : seul `app.py:436` appelle `enregistrer_hash`.

### 1.3 Ce qu'il compte

`correlation_session` (`correlation.py:78-97`) renvoie, pour chaque empreinte :

- `nb_sessions` : nombre de jetons distincts vus avec cette empreinte **depuis la création de la ligne**.
  Aucune fenêtre de temps.
- `sessions_par_heure` : `nb_sessions / (dernière vue − première vue)`, en heures (`correlation.py:88-95`).
  C'est une **moyenne sur toute la vie** de l'empreinte, pas un débit récent. Et elle vaut 0 si l'écart est
  d'une minute ou moins (`:95`). Conséquences :
  - 10 sessions en 50 secondes : 0 par heure (angle mort) ;
  - 2 sessions à 3 minutes d'écart : 40 par heure, au-dessus du seuil ;
  - une vieille empreinte très vue garde un débit élevé longtemps, puis le perd lentement ; une rafale sur
    une empreinte ancienne passe inaperçue.
  - `derniere_vue` ne bouge qu'à l'arrivée d'un jeton neuf (`correlation.py:63-68`).

La donnée lue est la **première** empreinte de la session (`detection.py:60-65`). Le gardien l'appelle à
chaque page contrôlée (`gardien.py:108-125`, appel `:119-120` ; `controler` `:268`) et à chaque collecte
(`app.py:441`).

### 1.4 Seuils, poids, effet aux niveaux 06 et 07

`DetecteurCorrelationSession` (`detection.py:2393-2431`) :

| Condition, pour chaque empreinte | Signal | Poids | Code |
|---|---|---|---|
| `nb_sessions` ≥ 5 (`SEUIL_SESSIONS`, `:2397`) | `recycling_<type>`, « fingerprint recyclé » | 0,7 | `:2414-2421` |
| `nb_sessions` ≥ 10 (`SEUIL_RAPIDE`, `:2398`) | `recycling_<type>`, « rotation de fingerprint massive » | 1,0 | `:2406-2413` |
| `sessions_par_heure` ≥ 30 | `velocity_<type>` | 0,8 | `:2422-2430` |

- Les signaux s'additionnent. Le détecteur dit « automatisé » à partir de 1,0 (`detection.py:18`, `:89-97`).
- Les deux empreintes donnent chacune leur signal : la même observation compte deux fois. Dès 5 sessions
  avec le même profil **et** le même canvas : 0,7 + 0,7 = 1,4, donc « automatisé ».
- Une seule empreinte à 5 (0,7) donne « indéterminé ». Mais le score composite multiplie la famille
  corrélation par 1,5 (`scoring.py:54`, `:63`, `:81-90`) : 1,05. Les seuils composites sont 0,5 au 06 et
  0,3 au 07 (`configs/arena/profils.yaml:220`, `:278` ; `profils-sans-cdp.yaml:192`, `:265`). **Au 06 et au
  07, n'importe quel signal de corrélation suffit donc à bloquer.**
- Le détecteur n'est consulté qu'aux niveaux 06 et 07 (`profils.yaml:219`, `:277` ;
  `profils-sans-cdp.yaml:191`, `:264`).

### 1.5 Ce que la table garde d'une campagne à l'autre

Tout. La table `empreintes_vues` (migration 8, `database.py:168-182`) n'a ni monde, ni lien vers une
campagne, ni date d'expiration. Supprimer une campagne (`reports.py:325-345`) efface ses observations mais
**pas** ses lignes dans `empreintes_vues`. La seule suppression est celle d'une session du site public
(`public/donnees.py:255`), qui efface la ligne entière d'une empreinte dès que le jeton figure parmi ses
10 derniers.

### 1.6 Où le détecteur agit

- Seulement dans le gardien, en direct (table `decisions`). Dans la table `detections` des passages, il est
  toujours « indéterminé, données cross-session absentes » : 360 sur 360 dans les campagnes 93 et 94 (R7).
  Les rapports par détecteur ne le montrent donc jamais.
- Le rejeu des sessions humaines l'écarte toujours du verdict (`rejeu.py:33-34`, `:142`, `:184`). Il donne
  à part un « historique » lu avec l'état **actuel** de la table (`rejeu.py:150-154`, `:202`) : une session
  y voit aussi les sessions venues après elle. Sur cinq sessions d'un même navigateur, la première y
  paraîtrait « vue 5 fois ».

## 2. Ce qu'il confond

### 2.1 Visiteurs légitimes classés

| Cas | Ce que voit la règle | Classé aujourd'hui (06 et 07) | Distingué ? |
|---|---|---|---|
| Humain qui revient avec son navigateur | même profil, même canvas | oui à la 5ᵉ session ; aussi à la 2ᵉ, 3ᵉ ou 4ᵉ si elle commence entre 1 et 2 × n minutes après la 1ʳᵉ (n = rang ; défaut de vitesse, § 1.3) | non : aucun cookie de visiteur durable, tous les cookies de l'Arena sont des cookies de session (`app.py:144`) |
| Identité qui dure (palier 2 : même empreinte, cookies gardés, une visite par heure) | `nb_sessions` +1 par visite | oui à la 5ᵉ visite, « rotation massive » à la 10ᵉ | non |
| Plusieurs personnes sur la même machine | même empreinte | oui à la 5ᵉ session cumulée | non |
| Modèle très répandu (même Chrome, même Mac) | canvas commun à tout Chromium 156 de ce Mac (R8) ; profil à six champs | oui ; le canvas seul (0,7 × 1,5) suffit au composite | non |
| Campagne de mesure (15 passages d'un même moteur) | même empreinte par construction (§ 3.3) | oui dès le 5ᵉ passage (06), dès le 3ᵉ (07) (R6) | non |
| Humain qui arrive après les campagnes | table globale : son canvas peut avoir déjà été vu des centaines de fois | possible **dès la 1ʳᵉ visite** **(supposition, à vérifier : § 6)** | non |

### 2.2 Comportements d'automatisation qu'elle voudrait attraper

| Comportement | La règle actuelle l'attrape ? | Le distingue d'un humain ? |
|---|---|---|
| Beaucoup de sessions **neuves, sans cookie**, avec la même empreinte | oui, à 5 | **non** : elle compte de la même façon les retours d'un visiteur connu |
| Une empreinte qui **change** à chaque session alors que le cookie ou l'adresse reste | **non** : une empreinte neuve a le compte 1. Rien ne relie deux sessions hors de l'empreinte. L'adresse IP n'est pas enregistrée (`frontal.py:193-223`), et en local toutes les sessions viennent de la même machine. **La rotation fait passer.** | non |
| Un **débit** de sessions impossible pour une personne | à moitié : moyenne sur toute la vie, aveugle sous une minute, garde la mémoire des vieilles campagnes, se déclenche sur 2 à 4 sessions rapprochées (§ 1.3) | non |

Rotation à l'intérieur d'une session : aucune des 706 sessions enregistrées n'a changé d'empreinte d'une
page à l'autre (R3). Aucun moteur ne le fait aujourd'hui.

## 3. Ce que disent les données

### 3.1 La table

- 46 lignes : 21 empreintes `profil_complet`, 25 `canvas`. 706 sessions, du 11/11 21:25:30 au 12/11
  10:13:15 (UTC) (R1). La table date de la campagne 90.
- Les 706 sessions sont toutes des passages de campagne (90 à 95). **Aucune session humaine, aucune
  session hors campagne** (R3).
- Le compte de la table égale le nombre de sessions distinctes recalculé à partir des observations, empreinte
  par empreinte : aucun écart (R3).

### 3.2 Les témoins : deux moteurs, une seule empreinte

`playwright` et `patchright` (le même Chromium, sans réglage) ont **le même** `profil_complet`
(`c93c6fbb57295058`) et **le même** `canvas` (`2320ef8741fc4143`) : 443 sessions, sur les campagnes 90
(75 + 75), 92 (25 + 25), 93 (60 + 60), 94 (60 + 60) et 95 (3) (R2, R3). Pour l'Arena, ce sont deux
« visiteurs » indiscernables. Dans les campagnes 93 et 94, leurs passages des niveaux 06 et 07 sont classés
avec « vu 201 à 440 fois » (R9). Ils sont aussi arrêtés par d'autres détecteurs (`docs/PLAN.md`, § 2).

### 3.3 NOEZIA : une empreinte par série de 15 passages

Mécanisme lu dans le code : la campagne ouvre le moteur **une fois par couple moteur × niveau**
(`campaigns.py:501-503`), puis enchaîne les 15 passages (`:514-522`). NOEZIA tire son profil dans `open()`
(`moteur.py:158-167`), donc une fois pour les 15. Chaque passage ouvre un contexte de navigateur neuf
(`moteur.py:229`, fermé `:303`) : **cookies jetés, empreinte gardée**. C'est exactement le motif « sessions
neuves, même empreinte » que la règle veut attraper. La campagne le produit par accident.

Ce que montre la base (R4) :

| Campagne | Moteur | `profil_complet` distincts (sessions chacun) | `canvas` distincts (sessions chacun) |
|---|---|---|---|
| 93 | noezia | 4 (15, 15, 15, 15) | 4 (15 chacun) |
| 93 | playwright + patchright | 1 (120 dans la campagne) | 1 (120) |
| 94 | noezia | 3 (30, 15, 15) | 4 (15 chacun) |
| 94 | playwright + patchright | 1 (120) | 1 (120) |

Collisions de `profil_complet` entre profils NOEZIA tirés indépendamment (R2, R3, R4) :
- `f6b4e00873032ec8` : séries 06scdp et 04scdp de la campagne 94. La série 04scdp, passée après, a eu les
  rangs 16 à 30 (R6). Elle était au niveau 04, où la corrélation n'est pas consultée. Si l'ordre avait été
  inverse, la série 06scdp aurait démarré au rang 16 : 0 passage sur 15 au lieu de 2 (calcul sur la règle).
- `7c81241d49e0c472` : deux séries de la campagne 90 (30 sessions).
- `7121ab0c43b9349e` et `665d2f342af9e663` : 15 sessions dans la campagne 90, puis 5 dans la 92.
  **Une campagne en influence une autre.**
- Le `canvas` de NOEZIA, bruité selon le profil, ne collisionne jamais (25 valeurs, R2).

### 3.4 À partir de quel passage la règle se déclenche

Séries NOEZIA, passages dans l'ordre de départ (R5, R6) :

| Campagne, niveau | Passages non classés par la corrélation | Classés par le compte (`vu N fois`) | Classés par la vitesse seule |
|---|---|---|---|
| 93, 06scdp | 1 à 4 | 5 à 15 (N = 5 à 15) | aucun |
| 94, 06scdp | 1 à 4 | 5 à 15 (N = 5 à 15) | aucun |
| 93, 07scdp | 1 et 2 | 5 à 15 | 3 et 4 (92,7 et 81,3 sessions par heure) |
| 94, 07scdp | 1 et 2 | 5 à 15 | 3 et 4 (132,6 et 105,0 sessions par heure) |

- Soit 11 passages sur 15 au 06 et 13 sur 15 au 07, dans chacune des deux campagnes. C'est ce que dit
  `docs/PLAN.md` (§ 2, « Ablations n° 93 et 94 »).
- Les « débits » relevés vont de 65,7 à 220,9 sessions par heure (R6). Une série NOEZIA des niveaux 06 et 07
  dure 10 à 14 minutes (R4).
- 168 décisions des campagnes 93 et 94 citent un signal de corrélation : noezia 11 + 13 + 11 + 13, témoins
  120. Toutes viennent du détecteur seul (« automatisé »), jamais du composite, car profil et canvas
  franchissent le seuil ensemble (R5).
- **Le résultat d'un passage dépend de son rang dans la série** : les passages 1 à 4 ne peuvent pas être
  classés, les passages 5 à 15 le sont toujours. Les 15 passages ne sont donc pas des tirages indépendants.
  Or l'intervalle de Wilson (`analytics.py:26`) suppose des tirages indépendants. Le « 2/15, de 4 à 38 % »
  du niveau 06 mesure la forme de la campagne autant que le moteur.

## 4. Proposition

### 4.1 Le principe

Une empreinte stable n'est pas suspecte. Ce qui est suspect, c'est :
1. une même empreinte portée par **beaucoup de visiteurs neufs** (sans mémoire), en peu de temps ;
2. un **même visiteur** qui change d'empreinte ;
3. un **débit** qu'aucune personne ne tient.

Pour cela, il faut deux choses qui n'existent pas : savoir qu'un visiteur **revient** (un cookie de visiteur
durable), et un **monde** qui borne l'historique (sinon une campagne pèse sur la suivante, § 3.3).

### 4.2 La règle proposée (version 2 du détecteur)

Définitions :
- **Empreinte E** : un seul hachage de `profil_complet` **et** `canvas` ensemble. Un fait, un signal. Une
  collision sur un seul des deux (deux profils NOEZIA ; deux Chromium 156 de ce Mac) ne suffit plus.
- **Visiteur V** : un cookie `sl_visiteur` durable (400 jours, la durée maximale qu'accepte Chrome), valeur
  aléatoire **signée** avec le secret de l'Arena, comme les cookies de défi (`arena/defis.py:3`). Il contient
  le nom du monde. Posé à la première réponse s'il manque ou s'il est invalide, même sans jeton (2.1 :
  « une requête sans jeton est protégée aussi »).
- **Session neuve** : session dont la première requête n'apportait pas de `sl_visiteur` valable dans ce
  monde.
- **Monde M** : un nom. Tous les comptes se font dans un monde. Remettre à zéro = ouvrir un monde neuf.
  Les anciens mondes restent en base pour l'histoire. Un cookie d'un autre monde vaut « visiteur neuf ».

Signaux (seuils et poids : **choix de Claude**, à recaler sur les sessions humaines ; les poids reprennent
ceux d'aujourd'hui pour ne pas toucher au composite) :

| Signal | Ce qu'il compte | Seuil | Poids |
|---|---|---|---|
| `empreinte_sans_memoire` | sessions **neuves** de M portant E dans les 24 dernières heures | ≥ 5 ; ≥ 10 | 0,7 ; 1,0 |
| `rotation_empreinte` | empreintes E distinctes pour un **même V** dans les 24 dernières heures, ou pour un même jeton | ≥ 3 | 1,0 |
| `debit_empreinte` | sessions de M portant E dans les **60 dernières minutes** (vraie fenêtre, pas de moyenne, pas d'angle mort) | ≥ 30 | 0,8 |

Ce que la règle ne compte **jamais** : les retours d'un visiteur connu avec la même empreinte.

Effet attendu sur chaque cas du § 2 :

| Cas | Version 2 |
|---|---|
| Humain qui revient (même navigateur) | une seule session neuve, la première : jamais classé |
| Identité qui dure (palier 2, une visite par heure, cookies gardés) | jamais classée ; classée si elle dépasse 30 visites par heure (normal : c'est un robot) |
| Mise à jour du navigateur, fenêtre passée sur un autre écran | 2 empreintes pour un même V : sous le seuil de 3 |
| Plusieurs personnes, même navigateur | un seul V : vu comme un visiteur qui revient |
| Plusieurs personnes, même modèle, navigateurs distincts | classé à partir de 5 nouveaux venus en 24 h : faux positif possible **à grande échelle** (voir limites) |
| Robot qui jette ses cookies à chaque session, même empreinte | classé à la 5ᵉ session neuve en 24 h (comme aujourd'hui) |
| Robot qui change d'empreinte en gardant son cookie | classé à la 3ᵉ empreinte (aujourd'hui : jamais) |
| Robot qui change d'empreinte **et** jette ses cookies | non classé : rien ne relie ses sessions en local. C'est la question du palier 4 (identités impossibles à relier) ; en ligne, l'adresse IP la tranchera (palier 3). |

Limites :
- À grande échelle, une empreinte à faible entropie est partagée par beaucoup de vrais visiteurs. Il
  faudrait alors pondérer par la fréquence normale de l'empreinte, ou l'enrichir (polices, audio, WebGL…),
  au prix de plus de changements pour un même visiteur. Hors sujet pour l'Arena locale, où les humains sont
  peu nombreux.
- Un humain en navigation privée est « neuf » à chaque fenêtre : cinq fenêtres privées en un jour avec la
  même empreinte seraient classées. À mesurer.
- La règle reste muette sur l'adresse IP : toutes les sessions locales viennent de la même machine.

### 4.3 Données nécessaires : ce qui dépend de la migration 9 et ce qui peut s'en passer

| Besoin | Sans migration ? | Avec la migration 9 (palier 2.1) |
|---|---|---|
| Cookie `sl_visiteur` signé | **oui** : du code dans le middleware (`app.py:89-145`). Sa valeur est déjà enregistrée dans l'en-tête `Cookie`, gardé en entier par le frontal (`frontal.py:218`) et par le middleware (`app.py:99`, `:110`) | idem |
| Empreinte combinée E | **oui** : un nouveau `type` (texte libre) dans `empreintes_vues` ; la table repart de zéro pour ce type | une colonne de la nouvelle table |
| Débit sur une vraie fenêtre | **en partie** : à partir des 10 derniers jetons gardés (`correlation.py:64`) et de l'heure de leur première empreinte (`observations_js`, indexée par jeton). « Les 10 dernières sessions de E tiennent en 20 minutes » ≈ 30 par heure | exact, sur n'importe quelle fenêtre |
| Sessions neuves par empreinte | **en partie** : pour les 10 derniers jetons, lire `sl_visiteur` dans l'en-tête `Cookie` de leur première requête | exact, une colonne `nouveau` |
| Rotation pour un même visiteur | **non** (il faudrait parcourir toutes les observations) ; la rotation à l'intérieur d'une session, oui (les empreintes de la session suffisent) | oui |
| Monde remis à zéro | **approché** : monde = campagne (jeton → `runs.experiment_id`), et toutes les sessions manuelles dans l'expérience permanente `sessions-manuelles` (`passages.py:14`, `:151-166`) | oui, nom de monde explicite et commande de remise à zéro |
| Rejeu de la corrélation sur les humains | **oui** : peu de sessions, l'historique se recalcule depuis les observations (empreintes, en-têtes `Cookie`), dans l'ordre du temps, sans voir les sessions suivantes | plus simple |
| Bannir par cookie et par empreinte (2.2), comptes (2.3) | non | **mêmes données** que la règle |

Contenu proposé pour la partie « visiteurs » de la migration 9 (à ajouter à la fin de `database.MIGRATIONS`,
sans toucher à la migration 8) : une table des visites, une ligne par session, avec le monde, le jeton
(unique), le visiteur, `nouveau` (0 ou 1), l'empreinte combinée et l'heure de début ; un index sur
(monde, empreinte, heure) et un sur (monde, visiteur, heure). `empreintes_vues` reste en base mais n'est
plus lue. La règle devient une fonction pure (la liste des visites du monde, la session courante, l'heure),
facile à tester sans base.

### 4.4 Ce que doit faire une campagne de mesure

Oui, un monde remis à zéro, comme le prévoit 2.1. Mais son étendue dépend de ce qu'on mesure :

| Type de campagne | Monde | Identité du moteur | Ce que la corrélation mesure |
|---|---|---|---|
| Discrétion (palier 1, niveaux 01 à 07) | **un par passage** | peu importe | rien entre sessions : chaque passage est une première visite. Les passages redeviennent indépendants (Wilson valable). La rotation à l'intérieur d'une session reste contrôlée. |
| Identité qui dure (palier 2, scénario « suivi ») | un par série (moteur × niveau) ou par longue exécution | même profil **et** cookies gardés (2.5) | qu'un visiteur qui revient n'est pas classé ; débit (2.7 : budget) ; rotation |
| Plusieurs identités (palier 4) | un par exécution | un profil et un dossier par identité | si l'Arena relie les identités |
| Témoin négatif de la règle | un par série | même profil, cookies jetés (la forme **actuelle** des campagnes) | que la règle attrape encore le « flood » : classé à la 5ᵉ session neuve |

Raison : la corrélation entre sessions mesure l'**endurance**, pas la discrétion d'une visite. La mettre dans
les campagnes de discrétion, c'est mesurer la répétition de la campagne et casser l'indépendance des
passages (§ 3.4).

Le réglage se déclare dans le fichier de campagne (par exemple `monde: passage | serie | campagne`), il est
enregistré avec la configuration de l'expérience, et le gardien le lit à partir du jeton. Les sessions
humaines vont dans un monde à elles, ouvert avant une série de sessions, jamais partagé avec une campagne.

### 4.5 Option minimale, faisable tout de suite, sans migration

Dans l'ordre :
1. **Libellés** : « empreinte revue N fois » ; « rotation » réservé au vrai signal de rotation.
2. **Un seul signal par fait** : empreinte combinée profil + canvas (nouveau `type` dans `empreintes_vues`).
   Effet de bord utile : ce type repart de zéro, l'historique global ne pèse plus.
3. **Débit sur une vraie fenêtre** à partir des 10 derniers jetons (§ 4.3). Fin de l'angle mort de la
   première minute et des faux débits sur 2 à 4 sessions.
4. **Monde approché** : réglage `monde` dans le fichier de campagne, sans changement de schéma.
   `passage` (défaut des campagnes de discrétion) : seuls les signaux internes à la session s'appliquent.
   `campagne` : ne compter que les jetons de la même expérience. Sessions manuelles : l'expérience
   `sessions-manuelles`.
5. **(Facultatif) cookie `sl_visiteur`** lu dans les en-têtes enregistrés, pour compter les sessions neuves
   parmi les 10 derniers jetons. **Sans ce point, un humain qui revient cinq fois dans le même monde reste
   classé à la 5ᵉ.** Les points 1 à 4 règlent le cas des campagnes et les défauts de calcul ; seul le point 5
   règle le cas de l'humain.

Limites de cette option :
- La fenêtre se limite aux 10 dernières sessions de chaque empreinte (`correlation.py:64`). Des jetons d'un
  autre monde peuvent occuper ces 10 places et cacher ceux du monde courant.
- Pas de rotation entre sessions pour un même visiteur.
- Pas de remise à zéro explicite pour les humains ; toutes les sessions manuelles partagent un monde.
- Le point 5 lit des en-têtes : code provisoire, remplacé par une colonne en 2.1.

Recommandation : faire **1 à 4 maintenant** (petits, testables, ils rendent les niveaux 06 et 07 mesurables
pour le palier 1). Faire la règle complète **en 2.1** avec la migration 9, parce que 2.2 (bannir par cookie
et par empreinte) a besoin exactement des mêmes données. Faire le point 5 seulement si Ethan veut évaluer la
corrélation sur des humains avant le palier 2. En attendant, le rejeu continue de la marquer « non évaluée »
pour les humains, et le jalon A au niveau 06 se lit sans elle : à écrire tel quel dans le plan.

### 4.6 Pour les sessions humaines de ce soir

- À travers l'Arena locale, aux niveaux 06 ou 07 : la 5ᵉ session d'un même navigateur sera classée (si son
  empreinte ne change pas) ; la 2ᵉ, la 3ᵉ ou la 4ᵉ aussi si elle commence plus d'une minute et moins de 4, 6
  ou 8 minutes après la 1ʳᵉ (défaut de vitesse). Et la 1ʳᵉ elle-même si le canvas du navigateur égale celui
  des témoins (§ 6).
- Aux niveaux 01 à 05, ou sur le site public : la corrélation ne décide pas en direct. Le rejeu l'écarte du
  verdict ; son « historique » lit la table actuelle, il ne faut pas en tirer de conclusion.
- Toutes les sessions faites dans le laboratoire, à n'importe quel niveau, s'ajoutent à la table (§ 1.2).

## 5. Tests à écrire d'abord

Règle (fonction pure : visites du monde, session courante, heure) :
1. Humain qui revient : 10 sessions, même visiteur, même empreinte, une par jour ; puis 5 dans une soirée à
   20 minutes d'écart → jamais classé.
2. Identité qui dure : 168 sessions (7 jours, une par heure), même visiteur, même empreinte → jamais classée.
3. Sessions neuves : 4 sessions neuves, même empreinte, en une heure → rien ; la 5ᵉ → `empreinte_sans_memoire`
   (0,7) ; la 10ᵉ → 1,0.
4. Fenêtre : 5 sessions neuves, même empreinte, étalées sur 30 jours → rien.
5. Rotation : même visiteur, 2 empreintes en 24 h (mise à jour) → rien ; 3 → `rotation_empreinte`.
6. Rotation dans une session : même jeton, 2 empreintes (changement d'écran) → rien ; 3 → signal.
7. Débit : 29 sessions en 59 minutes → rien ; 30 → `debit_empreinte` ; 10 sessions en 50 secondes ne sont pas
   ignorées (régression de `correlation.py:95`).
8. Débit ancien : 443 sessions il y a deux jours, puis 1 maintenant → pas de signal de débit (régression de
   la moyenne sur toute la vie).
9. Deux sessions à 3 minutes d'écart → aucun signal (régression : 40 par heure aujourd'hui).
10. Un fait, un signal : profil et canvas identiques → un seul signal, pas deux.
11. Collisions partielles : même profil, canvas différent (cas `f6b4e00873032ec8`) → empreintes différentes ;
    même canvas, profil différent (cas `2320ef8741fc4143`) → empreintes différentes.
12. Libellés : aucun texte « rotation » hors du signal de rotation.

Monde et visiteur :
13. 10 sessions dans le monde A, 1 dans le monde B, même empreinte → la session de B sans signal.
14. Monde neuf → compteurs à zéro ; cookie d'un ancien monde → visiteur neuf.
15. Cookie `sl_visiteur` : signé ; falsifié → visiteur neuf ; durée de 400 jours au plus ; posé à la première
    réponse, même sans jeton ; un client sans cookies est neuf à chaque session.
16. Campagne en `monde: passage` : 15 passages d'un même moteur, même profil → aucun signal entre sessions
    (régression des niveaux 06 et 07 des campagnes 93 et 94).
17. Idempotence : une session envoie 20 empreintes, avec plus de 10 autres sessions intercalées → comptée une
    fois (régression de `correlation.py:63-64`).

Gardien et rejeu :
18. Première session d'un monde neuf → le détecteur ne classe pas.
19. Rejeu : une session humaine ne voit que les sessions humaines **antérieures** de son monde (aujourd'hui
    `rejeu.py:150-154` voit tout l'état actuel).
20. Intégration, après 2.1 : témoin négatif (playwright, même profil, contextes neufs, un monde par série)
    classé au 5ᵉ passage ; NOEZIA en identité qui dure, 10 visites espacées → 0 classé.

## 6. Ce qui reste incertain

- **Canvas d'un vrai Chrome sur ce Mac (supposition, à vérifier)** : un Chromium 156 sans « Headless »,
  WebGL sur GPU Metal, a donné le même canvas que les témoins sans interface (R8). Si le Chrome d'Ethan rend ce petit dessin
  de la même façon, sa première session au 06 ou au 07 serait classée (canvas déjà vu 443 fois). À vérifier
  sur la première session de ce soir, en comparant son hachage canvas à `2320ef8741fc4143`. Explication
  probable, non vérifiée : Chrome dessine en logiciel les canvas de petite taille, quel que soit le GPU.
- **Seuils** (5 et 10 sessions neuves en 24 h, 3 empreintes, 30 par heure) : choix de Claude, sans
  référence humaine. À recaler par le rejeu une fois le cookie de visiteur en place.
- **Navigation privée, cookies effacés** : fréquence chez les participants inconnue.
- **Rotation entre sessions** : sans la migration 9, aucune mesure possible.
- L'option minimale ne voit que les 10 dernières sessions d'une empreinte : suffisant pour des seuils sous
  10, insuffisant au-delà.

## Annexe — requêtes (lecture seule)

Toutes lancées par `uv run python` avec `sqlite3.connect("file:outputs/shadowlab.sqlite3?mode=ro", uri=True)`.
Les empreintes sont recalculées avec `shadowlab.correlation.hash_session`, la fonction même de l'Arena.

- **R1** — `PRAGMA user_version` (8) ; `SELECT type, COUNT(*), SUM(nb_sessions), MIN(premiere_vue),
  MAX(derniere_vue), MAX(nb_sessions) FROM empreintes_vues GROUP BY type`.
- **R2** — `SELECT type, hash, nb_sessions, premiere_vue, derniere_vue FROM empreintes_vues ORDER BY
  nb_sessions DESC` (46 lignes).
- **R3** — `SELECT session_token, received_at, payload FROM observations_js WHERE kind = 'empreinte' AND
  received_at >= '2026-11-11T21:25' ORDER BY id` ; chaque empreinte passée à `hash_session`, regroupée par
  jeton ; jointure `runs` / `engines` sur `session_token`. Résultats : 706 sessions, 0 hors campagne, 0 session
  dont l'empreinte change d'une page à l'autre, 0 écart avec `nb_sessions`, porteurs de chaque empreinte.
  `SELECT COUNT(*) FROM runs WHERE truth = 'humain'` : 0.
- **R4** — `SELECT r.experiment_id, g.name, r.protection, r.started_at, (SELECT payload FROM observations_js o
  WHERE o.session_token = r.session_token AND o.kind = 'empreinte' ORDER BY o.id LIMIT 1) FROM runs r JOIN
  engines g ON g.id = r.engine_id WHERE r.experiment_id IN (93, 94)` ; empreintes par série et heures de début
  et de fin de chaque série.
- **R5** — `SELECT r.experiment_id, g.name, r.protection, d.couche, d.decision, d.motifs FROM runs r JOIN
  engines g ON g.id = r.engine_id JOIN decisions d ON d.session_token = r.session_token WHERE r.experiment_id
  IN (93, 94) AND (d.motifs LIKE '%recycling_%' OR d.motifs LIKE '%velocity_%')` : 168 décisions, toutes
  `fingerprinting-differe` / `detecte`, détecteur `correlation-session` ; codes : `recycling_profil_complet` 164,
  `recycling_canvas` 164, `velocity_profil_complet` 121, `velocity_canvas` 121.
- **R6** — pour chaque passage noezia des campagnes 93 et 94, dans l'ordre de `started_at` : rang de la
  session dans l'historique de son empreinte (ordre de R3), décisions de la session (`SELECT couche, decision,
  motifs FROM decisions WHERE session_token = ?`), « vu N fois » et sessions par heure lus dans les motifs,
  `runs.issue`.
- **R7** — `SELECT d.classification, COUNT(*) FROM detections d JOIN runs r ON r.id = d.run_id WHERE
  r.experiment_id IN (93, 94) AND d.detector_name = 'correlation-session' GROUP BY 1` : `indetermine` 360.
- **R8** — `SELECT o.session_token, MIN(o.received_at), o.payload FROM observations_js o LEFT JOIN runs r ON
  r.session_token = o.session_token WHERE o.kind = 'empreinte' AND r.id IS NULL GROUP BY o.session_token` :
  12 sessions des 8 et 9/11 (avant la table). Quatre d'entre elles, `Chrome/156.0.8078.4` sans « Headless »,
  rendu WebGL « ANGLE Metal Renderer: Apple M5 Pro » (trois avec 5 plugins, une avec 4), ont le canvas
  `2320ef8741fc4143`, comme les témoins, dont le rendu WebGL est SwiftShader. Ces sessions sont des essais
  pilotés, pas des humains **(supposition, d'après l'absence de passage)**.
- **R9** — motifs `recycling_profil_complet` des témoins aux niveaux 06scdp et 07scdp (campagnes 93, 94) :
  « vu N fois » de 201 à 440.
