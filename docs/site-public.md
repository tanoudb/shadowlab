# Site public — application réduite (étape 1.6)

Mis à jour : 14/11/2026 (version « étude », D-75). Code : `src/shadowlab/public/`. Tests : `tests/test_public.py`,
`tests/test_public_social.py`, `tests/test_public_etude.py`.

## Ce que c'est

Une petite application Python, **à part du laboratoire**, faite pour être mise en ligne. Elle sert :

- l'accueil de l'étude « Humain ou robot ? » et l'accord (`/`, `/fr`, `/en`) ; la notice complète, sans formulaire
  (`/fr/information`, `/en/information`, et `/information` dans la langue de la session ou du navigateur) ;
- le site vitrine (`/lab/vitrine…`, mêmes chemins et même code que dans le labo : `site/vitrine.py`) ;
- les sessions humaines de référence (`POST /session/commencer`, qui mène au fil du réseau social,
  `POST /session/terminer`, `POST /session/supprimer`, tous protégés contre le CSRF) et la page « Ma session »
  (`GET /session`) ;
- la collecte de l'observateur (`POST /lab/collecte`), seulement pendant une session consentie ;
- le formulaire de contact (`GET /contact`, `POST /contact`, `GET /contact/envoye`, D-57) : écrire au
  responsable sans qu'une adresse soit affichée ; sa feuille de style est servie sous `/contact/style.css` ;
- quatre fichiers statiques, en liste fermée : `observateur.js`, `vendor/botd-2.0.0.esm.js`, `vitrine.css`, `vitrine.js` ;
- le réseau social fictif « Mosaïk Démo » (squelette du 13/11, `public/social.py`, cadrage
  `docs/recherche/site-public-communaute-2026-11-13.md`) : `/lab/social` (redirige vers le fil), `/lab/social/fil`,
  `/lab/social/explorer` (paramètre `page`), `/lab/social/p/{identifiant}`, `/lab/social/u/{pseudonyme}`,
  `/lab/social/t/{etiquette}`, et les photos `/lab/social/photos/{fichier}` (seulement les fichiers du manifeste
  `public/static/social/photos/manifeste.json`). Même traitement que la vitrine : observateur et requêtes notées
  pendant une session seulement. Sa feuille et son script, `social.css` et `social.js`, sont servis sous
  `/public/static/` (liste fermée) ; le script ne fait aucune requête et n'écrit rien dans le navigateur ;
- la feuille des pages de l'étude, `public.css`, sous `/public/static/` (même liste fermée) et sous
  `/contact/style.css` pour les pages de contact.

**Deux langues** (D-75), français et anglais, sans cookie de plus : la langue d'une page est celle du préfixe de
l'adresse (`/fr`, `/en`), sinon celle notée avec l'accord de la session en cours, sinon celle préférée par le
navigateur (`Accept-Language`), sinon le français. Le formulaire de l'accueil porte sa langue dans un champ caché :
elle est notée dans `protection_config` avec la version du texte accepté. Seuls l'accueil et la notice ont une
adresse par langue ; « Ma session », le contact, les erreurs et le bandeau des deux sites suivent la session, puis
le navigateur. Les textes sont dans `public/textes.py` (un dictionnaire par langue, mêmes clés), la structure HTML
une seule fois dans `public/pages.py`. Le résumé de ce qui est relevé, sur l'accueil, est à un seul endroit
(`textes.RESUME_RELEVE`).

Tout le reste répond 404 : l'API, `/labo`, `/tableau`, la documentation OpenAPI, `/manuel`, la connexion de
test, la démo reCAPTCHA, `/lab/verdict` et les autres pages du labo. Ces modules ne sont même pas importés
(ni l'API, ni le gardien, ni le frontal, ni les détecteurs, ni les moteurs).

L'application du laboratoire (`shadowlab site`) ne se met **jamais** en ligne : son API lance des
navigateurs vers n'importe quelle adresse.

## Lancer

### Essai local (sans HTTPS)

```bash
SHADOWLAB_PUBLIC_CONTACT="Prénom Nom" \
SHADOWLAB_PUBLIC_HTTPS=0 \
uv run shadowlab public servir
# → http://127.0.0.1:8771/  (hôtes acceptés par défaut : localhost et 127.0.0.1)
```

### En ligne, derrière un mandataire HTTPS

L'application écoute **toujours** sur `127.0.0.1` ; seul le mandataire est exposé. Exemple de
configuration (`.env` sur le serveur, jamais versionné) :

```bash
SHADOWLAB_PUBLIC_HOTES=vitrine.example.org
SHADOWLAB_PUBLIC_CONTACT="Prénom Nom"
SHADOWLAB_PUBLIC_CONSERVATION_JOURS=90
SHADOWLAB_PUBLIC_BASE=/srv/shadowlab-public/public.sqlite3
SHADOWLAB_PUBLIC_ENTETE_IP=X-Forwarded-For     # voir « Adresse du visiteur » ci-dessous
```

Puis `uv run shadowlab public servir` (sous un utilisateur sans privilège, relancé par systemd ou équivalent).

**Option A — Cloudflare Tunnel (le plus simple, aucun port ouvert).** `cloudflared` relaie
`https://vitrine.example.org` vers `http://127.0.0.1:8771`. Cloudflare termine le HTTPS et pose
`CF-Connecting-IP` : régler `SHADOWLAB_PUBLIC_ENTETE_IP=CF-Connecting-IP`. Personne ne peut joindre
l'application sans passer par Cloudflare, donc cet en-tête ne peut pas être forgé.

**Option B — Caddy.** Caddy obtient le certificat, transmet `Host` tel quel et **remplace**
`X-Forwarded-For` par l'adresse du client (défaut `SHADOWLAB_PUBLIC_ENTETE_IP=X-Forwarded-For` qui convient).
Sans directive `log`, Caddy ne journalise pas les accès : n'en ajoutez pas.

```caddyfile
vitrine.example.org {
    reverse_proxy 127.0.0.1:8771
}
```

Avec Caddy **et** Cloudflare en proxy (nuage orange), l'adresse vue par Caddy est celle de Cloudflare :
passer `SHADOWLAB_PUBLIC_ENTETE_IP=CF-Connecting-IP` et n'accepter sur le port 443 que les plages
d'adresses de Cloudflare (pare-feu), sinon l'en-tête peut être forgé.

**Option C — nginx.** Il faut transmettre `Host`, remplacer (et non compléter) l'adresse, et couper le
journal d'accès (il contiendrait l'adresse du visiteur et la chaîne de requête, où passe le jeton) :

```nginx
server {
    listen 443 ssl http2;
    server_name vitrine.example.org;
    access_log off;
    location / {
        proxy_pass http://127.0.0.1:8771;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
```

Dans tous les cas : rediriger le HTTP vers le HTTPS au niveau du mandataire.

### Mise en ligne rapide depuis ce poste (tunnel sans compte ni domaine)

```bash
SHADOWLAB_PUBLIC_CONTACT="Nom ou pseudonyme" scripts/site-public-tunnel.sh
```

Le script ouvre un tunnel Cloudflare « rapide » (`cloudflared`, installé par Homebrew), affiche l'adresse
publique tirée au hasard (`https://…trycloudflare.com`, aussi écrite dans `outputs/public/adresse-publique.txt`),
puis lance l'application pour cette adresse seulement, avec `CF-Connecting-IP` et le Mac tenu éveillé
(`caffeinate`). Ctrl+C arrête l'application et le tunnel. Il se lance **par Ethan** : l'ouverture d'un tunnel
est refusée à l'assistant par le garde-fou de l'application, et la mise en ligne reste à lui.

Limites de cette voie, à connaître avant de partager le lien :

- **L'adresse change à chaque lancement** : un lien déjà partagé meurt si le script, le Mac ou la connexion
  s'arrête. Cloudflare donne ces tunnels sans garantie de disponibilité.
- **Aucune limitation de débit** devant l'application (pas de règles Cloudflare sans domaine) : le plafond
  de 40 sessions par jour peut être vidé par un script (voir « Limites connues »).
- **Le site tourne sur le poste de travail**, qui porte d'autres projets. L'application n'écoute que sur
  `127.0.0.1` et le tunnel ne relaie que son port.
- Le journal du tunnel (`outputs/public/tunnel.log`, niveau `info`) est **filtré avant d'être écrit** : toute
  adresse y est réduite à `schéma://hôte` (plus de chemin ni de chaîne de requête), tout chemin suivi d'une
  chaîne de requête, toute chaîne de requête restante et tout `sl=…` sont masqués (expression `sed`
  `FILTRE_JOURNAL` du script, essayée par `test_journal_du_tunnel_filtre_chemins_requetes_et_jetons`). **Jamais
  vérifié avec un vrai tunnel** : les lignes d'erreur de `cloudflared` sont supposées, pas observées ; un chemin
  sans chaîne de requête, hors adresse complète, n'est pas masqué. Relire `tunnel.log` après le premier
  lancement, et le supprimer avec la fin de la mise en ligne.

Pour un lien stable : un domaine chez Cloudflare (option A) ou une petite machine à part (options B et C).
Vercel et Netlify ne conviennent pas : pas de processus continu ni de disque durable pour la base SQLite.
Non vérifié au 12/11 : le script n'a jamais tourné avec un vrai tunnel (syntaxe, refus sans contact, lecture de
l'adresse et filtre `sed` vérifiés à vide).

## Réglages

| Variable | Défaut | Rôle |
|----------|--------|------|
| `SHADOWLAB_PUBLIC_HOTES` | `localhost,127.0.0.1` | Noms acceptés dans `Host` (liste exacte, `*` refusé). **Indépendant** de `SHADOWLAB_HOTES_AUTORISES`, le périmètre des moteurs |
| `SHADOWLAB_PUBLIC_CONTACT` | *(aucun)* | Responsable (nom ou pseudonyme), affiché sur la page d'information. Une adresse y est facultative : les visiteurs écrivent par le formulaire de contact. **Vide = refus de démarrer** |
| `SHADOWLAB_PUBLIC_CONSERVATION_JOURS` | `90` | Durée de conservation d'une session et d'un message de contact (≥ 1) |
| `SHADOWLAB_PUBLIC_HTTPS` | `1` | Cookies `Secure` et préfixe `__Host-`, en-tête HSTS. `0` seulement pour l'essai local |
| `SHADOWLAB_PUBLIC_PORT` | `8771` | Port d'écoute sur `127.0.0.1` |
| `SHADOWLAB_PUBLIC_BASE` | `outputs/public/public.sqlite3` | Base publique. Une base qui contient une expérience du labo est refusée |
| `SHADOWLAB_PUBLIC_ENTETE_IP` | `X-Forwarded-For` | En-tête où le mandataire met l'adresse du visiteur (dernière valeur lue). Vide = adresse de la connexion |
| `SHADOWLAB_VITRINE_GRAINE`, `SHADOWLAB_VITRINE_TAILLE` | `20261111`, `500` | Contenu du site vitrine, comme dans le labo |
| `SHADOWLAB_PUBLIC_SOCIAL_GRAINE`, `SHADOWLAB_PUBLIC_SOCIAL_TAILLE` | `20261113`, `120` | Contenu du réseau social fictif : graine et nombre de publications (au moins 1) |

L'application publique ne charge du fichier `.env` que `SHADOWLAB_PUBLIC_*`, `SHADOWLAB_VITRINE_*` et
`SHADOWLAB_SORTIES` : les clés propres au labo (jeton d'API, clés reCAPTCHA…) n'entrent pas dans son processus.
Une variable déjà exportée garde la priorité (`test_charger_public_ne_charge_que_ses_variables`).

### Adresse du visiteur

Elle ne sert qu'aux limites par adresse (ouverture de sessions, messages de contact), **en mémoire**,
sous forme d'empreinte salée, jamais écrite sur le disque. Un balayage, au plus une fois par minute par limiteur, retire toute empreinte dont
la dernière action est sortie de la fenêtre (1 heure ou 24 heures) ; il a lieu à chaque appel d'un limiteur **et** à chaque
requête reçue par l'application (`test_une_requete_ordinaire_balaie_les_empreintes_expirees_de_chaque_limiteur`).
Une empreinte quitte donc la mémoire à la première requête qui suit la fin de sa fenêtre : une journée au plus
pour la plus longue, un peu plus si personne ne visite le site entre-temps ; elle disparaît aussi à l'arrêt du
processus. Elle est salée, mais un attaquant qui lirait la mémoire du processus retrouverait une adresse IPv4 par
essais : on ne la dit pas « non réversible ». Une table pleine (10 000 empreintes) d'entrées encore valides n'est
**plus vidée** : une adresse inconnue est refusée jusqu'au prochain balayage, les adresses déjà connues gardent
leur compte (`test_limiteur_table_pleine_ne_remet_aucun_compteur_a_zero`). Une adresse IPv6 y compte pour son bloc /64 : un abonné en
reçoit au moins un entier et y change d'adresse à volonté. Une adresse IPv4, même écrite en IPv6
(`::ffff:a.b.c.d`), reste elle-même ; une valeur qui n'est pas une adresse est comptée telle quelle. Si
l'en-tête est mal réglé, tous les visiteurs partagent la même adresse (celle du mandataire ou de
Cloudflare) et ces limites deviennent globales : 6 sessions et 3 messages par heure, 5 messages par jour,
pour tout le monde. Si l'en-tête configuré manque à une requête, l'application écrit **un avertissement au
journal, une seule fois par démarrage**, sans aucune adresse (`test_en_tete_d_adresse_absent_avertit_une_seule_fois_sans_adresse`).

### Limites (constantes, `public/app.py`, classe `Limites`)

| Limite | Valeur | Pourquoi |
|--------|--------|----------|
| Sessions ouvertes par adresse | 6 par heure glissante (IPv6 : par /64) | Disque, en mémoire seulement |
| Sessions ouvertes par jour | 40, toutes adresses | Disque ; compté en base, survit au redémarrage |
| Taille de la base (+ WAL) | 2 Gio ; au-delà, plus aucune session ne s'ouvre et **plus rien ne s'écrit** (requêtes servies sans être notées, collecte en 503) | Disque |
| Envois de l'observateur par session | 300 (deux par page) | Disque |
| Volume des envois par session | 4 Mio (~10 Ko par empreinte) | Disque |
| Imbrication d'un envoi | 32 niveaux (l'observateur en a 5 au plus) ; au-delà, 400 | Mémoire, pile |
| Requêtes HTTP notées par session | 3 000 (~17 par page) ; au-delà, servies mais plus notées | Disque |
| Une requête notée | en-têtes : 40 au plus, nom ≤ 64 car., valeur ≤ 512 car., JSON ≤ 2 048 octets ; méthode ≤ 16, chemin ≤ 200 | Disque |
| Corps d'un envoi | 64 Kio, annoncé ou réel | Mémoire, disque |
| Durée d'une session | 2 heures (cookie et contrôle serveur) | Un cookie volé ne sert pas longtemps |
| Messages de contact | 2 000 caractères ; par adresse (en mémoire, IPv6 par /64) : 3 par heure glissante et 5 par 24 h glissantes ; 30 par jour pour tout le monde, 500 gardés (au-delà, 503 jusqu'à la purge ou un effacement à la main) ; formulaire borné à 12 octets par caractère permis, plus 1 Kio | Disque : quelques Mo au pire (500 messages de 8 Ko, non mesuré). 5 par adresse et par jour : un visiteur écrit une ou deux fois, et une adresse seule n'épuise ni le plafond du jour (30) ni la boîte avant la purge (5 × 90 jours = 450 < 500) |

**Pire cas, mesuré** (12/11/2026, base temporaire, ces bornes atteintes) : une session occupe 16,9 Mo —
12,6 Mo pour 3 000 requêtes aux en-têtes de 2 Ko (une ligne de ~2,3 Ko prend une page SQLite de 4 Kio) et
4,3 Mo d'envois. À 40 sessions par jour : **environ 680 Mo par jour**. Le plafond de 2 Gio est contrôlé à
chaque écriture ; il ne peut être dépassé que des lignes déjà en cours d'écriture (une par requête
simultanée, 64 Kio au plus chacune). Sous abus soutenu, il est donc atteint en 3 jours environ : le site
reste visitable mais n'ouvre plus de session jusqu'à la purge ou une suppression à la main (voir
« Limites connues »). Une purge ne réduit pas le fichier, mais ses pages libérées sont réutilisées.

## Purge et suppression

- **Automatique** : au démarrage, puis au plus une fois par 24 h à la première requête reçue. Une session
  est effacée de toutes les tables `SHADOWLAB_PUBLIC_CONSERVATION_JOURS` jours après son début (à la vérification
  qui suit : un jour de plus au plus, davantage si l'application est arrêtée). Un message, daté du seul jour,
  part quand ce jour a `SHADOWLAB_PUBLIC_CONSERVATION_JOURS` jours révolus, jour limite compris
  (`test_purge_des_messages_au_jour_limite` : avant, il restait un jour de trop).
- **Commande** : `uv run shadowlab public purger` (même règle). Une tâche planifiée quotidienne reste
  conseillée si l'application peut rester sans trafic ni redémarrage.
- **Par le visiteur, dès le début** : la page « Ma session » (`/session`, liée depuis le bandeau de chaque
  page pendant la session, et depuis la navigation) affiche l'identifiant, l'état et le bouton « Supprimer ma
  session » (formulaire signé, protégé contre le CSRF) ; effet immédiat, dans toutes les tables. Elle marche
  aussi après « Terminer », après l'expiration des 2 heures ou un redémarrage du navigateur, grâce au cookie
  `slp-droits` (voir « Cookies ») ; la page de fin y renvoie.
- **Sur demande écrite** (autre appareil, cookies effacés) : le visiteur écrit par le formulaire de contact
  en donnant l'identifiant de sa session (affiché sur « Ma session ») ; puis
  `uv run shadowlab public supprimer <identifiant>`.
- **Messages de contact** : `uv run shadowlab public messages` les affiche (numéro, jour, texte) ;
  `uv run shadowlab public effacer-message <n°>` en efface un, `effacer-message tous` les efface tous et
  dit combien (les numéros suivants ne reprennent pas à 1). Ils suivent la même purge que les sessions
  (démarrage, une fois par 24 h, commande `purger`). `servir` annonce leur nombre au démarrage et écrit
  « message de contact reçu » à chaque arrivée, sur la sortie standard **et seulement si c'est un
  terminal** : jamais dans le journal, ni dans journald sous systemd, où la ligne horodatée daterait le
  message. Rien n'est envoyé ailleurs : il faut regarder l'écran ou lancer la commande de temps en temps
  (une demande d'effacement se traite sous un mois) ; sous systemd, seule la commande les montre.
- La base et la boîte de messages sont ouvertes avec `PRAGMA secure_delete=ON` : SQLite vide les pages d'une
  ligne effacée, au lieu de les laisser lisibles dans le fichier. Cela **ne garantit pas l'écrasement physique** :
  le journal de transaction de SQLite (`-wal`), un disque SSD, un système de fichiers en copie sur écriture
  (APFS) et les sauvegardes peuvent garder des copies. Ce que la page d'information promet (« efface aussitôt
  toutes les données qui la concernent ») vaut pour la base, pas pour ces copies : voir « Ce qui reste à la
  charge de l'hébergement » (FileVault, sauvegardes).

## Journaux

L'application n'écrit une ligne que pour une **réponse d'erreur** (statut 400 ou plus : `méthode chemin statut`,
niveau DEBUG) dans `<dossier de la base>/logs/shadowlab.jsonl` (à l'écran seulement avec `--verbeux`) : ni
adresse, ni chaîne de requête, ni en-tête, ni jeton, ni identifiant de session. Une requête réussie ou redirigée
n'écrit **rien** (`test_journal_ne_garde_que_les_erreurs`) : ce journal est horodaté à la milliseconde et ne suit
pas la purge à 90 jours (il tourne par taille), il ne doit pas dater chaque visite, ce qui contredirait « rien
n'est enregistré » pour qui visite sans participer (hormis le compte du jour, voir « Fréquentation »). La notice
le dit (« Un journal technique ne garde que les erreurs… »).

**Aucune ligne**, même en erreur, pour les pages de contact (`/contact…`, feuille de style `/contact/style.css`
comprise) ni pour ce qu'un navigateur charge avec chaque page (fichiers `/lab/static/…` et `/public/static/…`,
`/favicon.ico`) :
rapprochée des requêtes notées d'une session à la même milliseconde, une ligne `POST /contact` daterait un
message, que D-57 ne garde qu'au jour (`test_contact_absent_du_fichier_de_journal`). L'avis « message de contact
reçu » ne passe pas par ce journal (voir « Purge et suppression »). L'application écrit aussi un avertissement,
une fois par démarrage, si l'en-tête d'adresse configuré manque (voir « Adresse du visiteur »).

Le journal d'accès d'uvicorn est coupé (`access_log=False`) et l'en-tête `Server` aussi. **Rotation**
(`public.ROTATION_JOURNAL`) : 5 Mio par fichier, le courant et 3 anciens, donc 20 Mio au plus
(`test_journal_tourne_avec_taille_et_nombre_bornes`). Le journal du labo, lui, ne tourne pas (inchangé).

## Cookies

Tous `HttpOnly`, `SameSite=Lax`, `Path=/`, et en HTTPS `Secure` avec le préfixe `__Host-`. Signés (HMAC,
clé `secret`) sauf `slp-csrf`, qui n'est qu'une valeur au hasard.

| Cookie | Posé | Durée | Rôle |
|--------|------|-------|------|
| `slp-csrf` | dès la première page à formulaire, **avant tout accord** | fermeture du navigateur | Anti-CSRF (double soumission) ; jamais enregistré en base |
| `slp-session` | à « Commencer » | 2 h, effacé à « Terminer » | Relie les pages à la session en cours |
| `slp-droits` | à « Commencer » | durée de conservation (90 j), effacé à la suppression | Retrouver et supprimer sa session depuis « Ma session » |

La notice les décrit tous les trois (`test_page_d_information_decrit_cookies_et_transit`). Il n'y en a jamais
d'autre, dans aucune langue (`test_toujours_exactement_trois_cookies`).

## Ce qui est stocké

Base publique, tables du schéma du labo (aucune migration ajoutée), plus une table à elle, `frequentation` :

- `experiments` : une seule ligne, `sessions-publiques` ; `engines`, `scenarios` : une ligne chacune.
- `runs` : une ligne par session (`truth='humain'`, `consent_at`, `protection_config` garde la version du
  texte d'information et la durée de conservation acceptées). Passe à `reussi` à « terminer ».
- `observations_http` : pour chaque requête `/lab/…` d'une session en cours, méthode, chemin sans
  paramètres, version HTTP et les seuls en-têtes de la liste blanche `donnees.ENTETES_GARDES`
  (+ `sec-ch-*`, `sec-fetch-*`). Colonne `cookies` toujours `[]`. Référent extérieur → `externe`.
- `observations_js` : les envois de l'observateur (empreinte et comportement), tels quels, sauf les
  identifiants d'extension de navigateur (`chrome-extension://<id>`, `moz-extension://`,
  `safari-web-extension://`… dans les traces d'erreur), remplacés par `masque` avant le calcul du volume et
  l'écriture : un identifiant d'extension peu répandue peut désigner une personne.
- `frequentation` (D-75), créée par l'application (`donnees.SCHEMA_FREQUENTATION`, pas une migration du labo) :
  une ligne par jour UTC, `jour` (AAAA-MM-JJ) et trois nombres, `accueil` (chargements de la page d'accueil, en
  GET), `commencees`, `terminees` (« Terminer ma session »). Ni adresse, ni identifiant, ni navigateur, ni heure.
  Une visite hors session n'écrit rien d'autre que ce compte. Ni la suppression d'une session ni la purge n'y
  touchent : les comptes sont gardés sans limite de durée, et la notice le dit. Base pleine, rien ne s'y écrit ;
  base en panne, l'accueil reste servi, sans compteur (le compte est perdu).
- Aucune autre table n'est écrite : ni `empreintes_vues` (pas de hash de corrélation entre visites), ni
  `decisions`, `detections`, `fingerprints` (aucun détecteur ne tourne). La suppression les couvre quand même.
- `<dossier de la base>/messages.sqlite3` (droits 600 dès la création, `secure_delete`) : les messages du formulaire de
  contact, **dans un fichier à part** : le texte et le **jour** de réception, rien d'autre. Ni adresse IP, ni
  session, ni navigateur, ni heure. Le texte est nettoyé par **liste blanche**, pour s'afficher sans risque
  dans un terminal : on garde saut de ligne, tabulation, caractères affichables (`str.isprintable()`) et les
  deux liants des emoji composés (U+200C, U+200D) ; les espaces particulières (insécables…) deviennent des
  espaces ; tout le reste est retiré (contrôle dont ESC, mise en forme invisible, sens d'écriture forcé,
  balises, usage privé, caractères non attribués). **Limite acceptée** : un emoji plus récent que la table
  Unicode de Python disparaît, et un drapeau à balises (Angleterre, Écosse…) perd ses balises. Une liste
  noire, essayée le 12/11, laissait passer d'autres invisibles (U+200B, U+200E, U+FEFF, balises…).
  La base des sessions peut ainsi être copiée pour le rejeu sans emporter des messages où un visiteur a
  écrit comment le joindre.
  **Les pages de contact ne laissent aucune trace dans une session en cours** : la base ne note que les
  requêtes `/lab/…`, et ces pages (formulaire, confirmation, page d'erreur du formulaire) ne chargent plus rien
  sous `/lab/` (leur feuille de style est servie sous `/contact/style.css`, même contenu et mêmes en-têtes que
  `/lab/static/vitrine.css`), ne chargent aucun script (donc aucun envoi à `/lab/collecte`, observateur
  absent) et ne mènent qu'à `/` ou `/contact…`, jamais à une page `/lab/…` : la navigation suivante n'est pas
  notée avec un référent réduit à l'origine. Elles répondent avec `Referrer-Policy: origin` (jamais
  `no-referrer` : le navigateur enverrait `Origin: null` au POST du formulaire, refusé en 403, et l'envoi serait
  cassé). Preuve : `test_pages_de_contact_sans_trace_dans_la_session`. Une base nommée `messages.sqlite3` est
  refusée au démarrage.
- `<dossier de la base>/secret` (droits 600) : clé de signature des cookies. Le dossier `outputs/` est
  ignoré par git. Un fichier `secret` vide est refusé (erreur claire au démarrage, labo compris) : sinon
  n'importe qui pourrait forger les cookies signés. Le supprimer pour qu'il soit recréé.

La liste lisible des données, dans la notice, est tirée de `observateur.js` clé par clé, dans chaque langue ; un
test échoue si le script envoie un champ qu'elle ne décrit pas.

## Fréquentation

`uv run shadowlab public frequentation` affiche, jour par jour (UTC), les chargements de l'accueil, les sessions
commencées et les sessions terminées, puis les totaux. L'accueil affiche le total des sessions terminées
(« N sessions enregistrées à ce jour »). Limites : tout chargement de l'accueil compte (rechargements, robots,
aperçus de lien) ; une session terminée puis supprimée reste comptée ; une session abandonnée sans « Terminer »
compte comme commencée seulement.

## Les dix règles de l'étape 1.6 et leurs preuves

| Règle | Tests (`tests/test_public.py`) |
|-------|-------------------------------|
| Surface réduite | `test_routes_du_labo_absentes` (40 routes), `test_routes_du_labo_absentes_en_post`, `test_aucun_module_du_labo_n_est_charge` |
| 1. Consentement avant collecte | `test_sans_consentement_ni_observateur_ni_jeton`, `test_visite_sans_participer_ne_laisse_aucune_trace`, `test_consentement_exige`, `test_parcours_complet`, `test_double_clic_ne_cree_pas_deux_sessions` |
| 2. Collecte fermée | `test_collecte_refusee_sans_session`, `…_jeton_inconnu_ou_cookie_forge`, `…_apres_terminer_meme_avec_l_ancien_cookie`, `…_apres_la_duree_maximale`, `test_quota_d_envois_par_session`, `test_quota_de_volume_par_session`, `test_corps_trop_gros`, `test_messages_invalides` |
| 3. Aucune requête vers un tiers | `test_aucune_adresse_externe_dans_les_pages`, `test_sonde_webrtc_sautee_quand_la_page_le_demande` (avec et sans la balise, exécuté par Node) |
| 4. Moins de données personnelles | `test_entetes_porteurs_d_ip_et_cookies_non_stockes`, `test_pas_de_hash_de_correlation`, `test_journaux_sans_jeton_ni_requete_ni_adresse`, `test_commandes_public` (uvicorn sans journal d'accès) |
| 5. Humains jamais bloqués | `test_aucun_defi_ni_detection_en_direct`, `test_aucun_module_du_labo_n_est_charge` (détecteurs non importés) |
| 6. Base et hôtes séparés | `test_hote_etranger_refuse`, `test_hotes_et_base_independants_du_labo`, `test_base_du_labo_refusee`, `test_hotes_invalides_refuses` |
| 7. Cookies et en-têtes | `test_parcours_complet` (cookie), `test_entetes_de_securite`, `test_mode_http_sans_secure_ni_hsts`, `test_commencer_depuis_une_autre_origine_refuse`, `test_commencer_sans_jeton_csrf_refuse`, `test_supprimer_protege` |
| 8. Page d'information, contact obligatoire | `test_page_d_information_complete`, `test_liste_des_donnees_tiree_de_l_observateur`, `test_demarrage_refuse_sans_contact`, `test_conservation_invalide_refusee`, `test_commandes_public` |
| 9. Purge | `test_purge_efface_les_vieilles_sessions_et_garde_les_recentes`, `test_purge_au_demarrage`, `test_commandes_public` ; suppression : `test_supprimer_efface_la_session_dans_toutes_les_tables` |
| 10. Limite d'ouverture | `test_limite_par_adresse`, `test_plafond_global_par_jour`, `test_plafond_de_taille_de_la_base` |

Corrections après relecture et audit (12/11/2026) :

| Point | Tests |
|-------|-------|
| A. Remplissage du disque | `test_requetes_notees_bornees`, `test_plafond_de_taille_respecte_a_l_ecriture` |
| B. Rotation du journal | `test_journal_tourne_avec_taille_et_nombre_bornes` |
| C. Effacement hors « Terminer » | `test_ma_session_accessible_des_le_debut`, `test_effacement_possible_apres_la_session` (terminée ; expirée, navigateur relancé) |
| D. « Terminer » en POST + CSRF | `test_terminer_exige_post_et_csrf` |
| D. Cookies et transit sur la page d'information | `test_page_d_information_decrit_cookies_et_transit` |
| D. Identifiants d'extension | `test_identifiants_d_extension_masques` |
| D. Pas de redirection `http://` sur barre finale | `test_pas_de_redirection_sur_barre_finale` |
| D. JSON trop imbriqué | `test_json_trop_imbrique_refuse` |
| D. Panne de base → 503 avec les en-têtes | `test_erreur_de_base_donne_503_avec_les_entetes` |
| D. Secret vide | `test_secret_vide_refuse`, `test_secret_valide_inchange_et_cree_s_il_manque` |
| E. Formulaire de contact (D-57) | `test_contact_remplace_l_adresse_dans_les_pages`, `test_contact_textes_exacts`, `test_contact_enregistre_le_message_a_part_sans_adresse` (jour seul, pas de référent), `test_contact_protege` (origine, CSRF, texte rendu), `test_contact_message_vide_ou_trop_long`, `test_contact_retire_les_caracteres_de_controle`, `test_contact_limite_par_adresse`, `test_contact_plafond_par_jour_et_boite_pleine`, `test_purge_des_messages`, `test_commandes_messages`, `test_base_nommee_comme_la_boite_refusee`, `test_contact_origine_null_refusee`, `test_contact_referent_reduit_a_l_origine`, `test_contact_s_envoie_depuis_un_vrai_navigateur` (intégration, Chromium réel) |

Seconde relecture indépendante (12/11/2026) :

| Point | Tests |
|-------|-------|
| F. Le journal ne date plus un message de contact | `test_contact_absent_du_fichier_de_journal` (envoi complet pendant une session : aucune ligne, pas même la feuille de style ou l'icône), `test_contact_avis_a_l_ecran_seulement_sur_un_terminal` |
| G. Une adresse seule ne ferme plus le formulaire | `test_limiteur_sur_une_journee_glissante`, `test_contact_limite_par_adresse_et_par_jour`, `test_bloc_d_adresse`, `test_limites_par_adresse_comptent_un_bloc_ipv6` (sessions et messages), `test_effacer_tous_les_messages` |
| H. Ni `debugger` ni first-input sur le site public | `test_debugger_et_first_input_sautes_quand_la_page_le_demande` (avec et sans la balise, exécuté par Node), `test_description_de_cdp_detection_suit_le_releve_public` |
| I. Nettoyage des messages : liste blanche gardée, limite sur les emoji récents acceptée | `test_nettoyer_ne_garde_que_ce_qui_s_affiche` (invisibles retirés, emoji courants et composés gardés, drapeau à balises réduit), `test_contact_garde_les_emoji_courants`, `test_contact_retire_les_caracteres_de_controle` |

Troisième relecture indépendante (12/11/2026) :

| Point | Tests |
|-------|-------|
| J. Le journal ne garde que les erreurs ; textes de la page d'information (journal, empreinte d'adresse, purge) | `test_journal_ne_garde_que_les_erreurs`, `test_page_d_information_dit_la_verite_sur_le_journal_et_l_adresse` |
| K. Pages de contact sans trace dans une session en cours | `test_pages_de_contact_sans_trace_dans_la_session` |
| L. Limiteur : balayage, table pleine, en-tête absent | `test_limiteur_balaie_les_adresses_expirees_une_fois_par_minute_au_plus`, `test_limiteur_table_pleine_ne_remet_aucun_compteur_a_zero`, `test_en_tete_d_adresse_absent_avertit_une_seule_fois_sans_adresse` |
| M. Droits 700/600 dès la création ; pas de promesse d'écrasement | `test_droits_des_fichiers_des_leur_creation`, `test_droits_resserres_sur_un_dossier_et_des_fichiers_existants`, `test_documentation_sans_promesse_d_ecrasement_physique` |
| N. `.env` réduit aux variables du site public | `test_charger_public_ne_charge_que_ses_variables`, `test_le_labo_charge_toujours_tout_le_fichier_env` |
| O. Journal de cloudflared filtré | `test_journal_du_tunnel_filtre_chemins_requetes_et_jetons`, `test_script_du_tunnel_garde_le_pid_de_cloudflared_et_filtre_sa_sortie` |
| P. Purge des messages au jour limite | `test_purge_des_messages_au_jour_limite` |

Version « étude » (14/11/2026, D-75, `tests/test_public_etude.py`) :

| Point | Tests |
|-------|-------|
| Deux langues, ordre du cadrage | `test_langue_par_le_prefixe_puis_le_navigateur`, `test_langue_de_suit_l_ordre_du_cadrage`, `test_langue_notee_avec_l_accord`, `test_langue_de_l_accord_sans_champ_valide`, `test_langue_de_la_session_avant_celle_du_navigateur`, `test_pages_publiques_dans_les_deux_langues`, `test_bandeau_de_la_vitrine_dans_les_deux_langues` |
| Notice phrase pour phrase, clé par clé | `test_liste_des_donnees_dans_les_deux_langues_tiree_de_l_observateur`, `test_notice_complete_dans_chaque_langue`, `test_notices_de_meme_structure` |
| Trois cookies, jamais plus | `test_toujours_exactement_trois_cookies` |
| Accueil et notice | `test_accueil_de_l_etude`, `test_accueil_resume_du_releve_exact_et_a_un_seul_endroit`, `test_accueil_presente_mosaik_en_grand_et_habitat_en_lien_discret`, `test_accueil_accord_notice_a_cote_et_visite_sans_participer`, `test_accueil_et_notice_disent_le_but`, `test_commencer_mene_au_reseau_social`, `test_notice_a_son_adresse`, `test_ancien_chemin_de_la_notice`, `test_feuille_de_style_de_l_etude`, `test_pages_de_l_etude_sans_style_ni_script_dans_la_page` |
| Fréquentation | `test_table_de_frequentation_trois_nombres_par_jour`, `test_comptes_du_jour`, `test_visite_hors_session_n_ecrit_que_le_compte_du_jour`, `test_comptes_survivent_a_la_purge_et_a_la_suppression`, `test_base_pleine_ne_compte_plus`, `test_compte_perdu_si_la_base_tombe_mais_accueil_servi`, `test_accueil_affiche_le_total_des_sessions_terminees`, `test_notice_dit_exactement_le_compte_par_jour`, `test_commande_frequentation` |

## Les huit conditions du § 5 du plan

| Condition | Couverture |
|-----------|-----------|
| 1. Application distincte ; `/api`, `/labo`, `/tableau`, `/api/docs`, connexion de test, démo reCAPTCHA v3 absents | **Code.** `test_routes_du_labo_absentes`, `test_aucun_module_du_labo_n_est_charge` |
| 2. Base séparée, sans frontal ni moteurs | **Code.** `test_hotes_et_base_independants_du_labo`, `test_base_du_labo_refusee`, `test_aucun_module_du_labo_n_est_charge` |
| 3. Hôtes servis séparés du périmètre du moteur | **Code.** `test_hotes_et_base_independants_du_labo`, `test_hote_etranger_refuse` |
| 4. Collecte refusée hors session consentie ; quotas par session ; débit par adresse | **Code** pour la collecte, les quotas et l'ouverture de sessions par adresse (règles 2 et 10). **Hébergement** pour le débit des requêtes ordinaires (pages, images) par adresse : règle de limitation Cloudflare ou du mandataire |
| 5. Aucune requête vers un tiers ; ni Turnstile ni reCAPTCHA | **Code.** `test_aucune_adresse_externe_dans_les_pages`, `test_sonde_webrtc_sautee_quand_la_page_le_demande`. L'observateur du labo garde sa sonde STUN (balise absente) |
| 6. Information complète, consentement avant collecte, suppression dans toutes les tables, purge | **Code.** Règles 1, 8, 9 ; `test_supprimer_efface_la_session_dans_toutes_les_tables` |
| 7. HTTPS, cookies sécurisés, journaux sans adresse ni jeton | **Partagé.** Code : cookies `Secure`/`HttpOnly`/`SameSite=Lax`/`__Host-`, HSTS, journaux de l'application (`test_entetes_de_securite`, `test_journaux_sans_jeton_ni_requete_ni_adresse`). **Hébergement** : certificat, redirection HTTP → HTTPS, journaux du mandataire et de Cloudflare |
| 8. Aucun secret dans le dépôt (contrôle de l'historique) | **Mise en ligne.** Non vérifié ici. L'application n'ajoute aucun secret au dépôt : sa clé de signature est créée dans le dossier de la base, sous `outputs/`, ignoré par git |

## Ce qui reste à la charge de l'hébergement

- Certificat TLS, redirection HTTP → HTTPS, mandataire qui transmet `Host` sans le changer.
- Journaux du mandataire : coupés, ou sans adresse ni chaîne de requête (le jeton de session passe dans
  `?sl=` des envois de l'observateur). L'hébergeur et le service placé devant (Cloudflare…) voient passer
  toutes les données en transit, adresse comprise : la page d'information le dit ; la nommer si on la précise.
- En-tête d'adresse non forgeable (tunnel, ou pare-feu limité aux plages de Cloudflare).
- Limitation de débit par adresse au mandataire ou chez Cloudflare : pages et images, **et
  `POST /session/commencer` et `POST /contact`** (quelques requêtes par minute), pour que les plafonds
  quotidiens ne soient pas épuisés par un script (voir ci-dessous).
- Sauvegardes : une sauvegarde de la base ou de `messages.sqlite3` garde des sessions et des messages
  supprimés ou purgés. Pas de sauvegarde, ou
  une rétention inférieure à la durée de conservation.
- Utilisateur sans privilège. Le dossier de la base est mis en `700` et `public.sqlite3`, `messages.sqlite3`
  (et leurs fichiers `-wal` et `-shm`) en `600` **par l'application elle-même**, dès la création, avec ou sans le
  script de tunnel : le fichier vide est créé avec ses droits avant d'être ouvert par SQLite. Un dossier ou un
  fichier d'un autre propriétaire n'est pas touché : si `SHADOWLAB_PUBLIC_BASE` pointe dans un dossier partagé,
  donner à la base son propre dossier.
- **À faire par le responsable (pas par le code)** : activer **FileVault** (le disque chiffré protège la base et
  les copies que `secure_delete` ne peut pas effacer si le Mac est perdu ou volé), et **exclure `outputs/` des
  sauvegardes** (Time Machine, copie vers un nuage) : une sauvegarde garde les sessions et les messages supprimés
  ou purgés.
- Surveillance du disque (le journal de l'application tourne seul, 20 Mio au plus).

## Limites connues de l'application

- **Quotas non atomiques.** Le quota d'une session (envois, volume, requêtes notées), le plafond quotidien et
  le plafond de taille sont lus puis écrits sans verrou : des envois parallèles peuvent les dépasser de
  quelques unités (une par requête simultanée). Sans conséquence sur le disque à cette échelle.
- **Plafond quotidien épuisable.** 40 sessions par jour pour tout le monde : un script qui change d'adresse
  peut les consommer et priver les vrais participants de la journée (et remplir la base en 3 jours environ,
  voir « Limites »). Parade : limitation de débit au mandataire (ci-dessus), surveillance, suppression à la
  main des sessions abusives (`shadowlab public supprimer`).
- **Formulaire de contact blocable.** Une adresse seule ne le peut plus (5 messages par jour ; un /64 IPv6
  compte pour une adresse). Mais six adresses IPv4, ou six /64, épuisent les 30 messages du jour en deux
  heures (dix en quelques minutes), chaque jour, et remplissent la boîte (500 messages) en 17 jours : le
  formulaire refuse alors tout (503) jusqu'à la purge ou jusqu'à `shadowlab public effacer-message` (`tous`
  vide la boîte d'un coup). Parade : limitation de débit au mandataire, et lire la boîte de temps en temps.
  Sans cookie (navigateur réglé pour tous les bloquer), le formulaire ne peut pas être envoyé : le jeton
  anti-CSRF en dépend, comme pour les autres formulaires ; le texte tapé est rendu à chaque refus.
- **SQLite bloque la boucle asynchrone.** Chaque accès à la base se fait dans la boucle d'uvicorn, sans
  fil séparé : acceptable pour une dizaine de participants simultanés, pas pour du trafic réel.
- **Onglet en arrière-plan.** La sonde d'empreinte attend `requestAnimationFrame`, sans délai maximal :
  dans un onglet caché, l'empreinte ne part qu'au retour de l'onglet au premier plan (et jamais si l'onglet
  est fermé avant). La sonde n'est pas modifiée ; la page d'information et le bandeau demandent de garder
  l'onglet visible.

## Limites acceptées

- Le responsable présent devant l'écran voit l'heure d'arrivée d'un message (l'avis « message de contact reçu »).
- Le regroupement IPv6 par /64 se contourne avec un préfixe plus large, et quelques adresses suffisent à épuiser
  le plafond du jour du formulaire (la suppression de sa session, elle, ne passe pas par le formulaire).
- N'importe qui peut ouvrir une session par script : les sessions du site public ne prouvent pas qu'un humain
  était là.
- Les caractères invisibles ou empilés gardés dans un message (liants, accents multiples) donnent un affichage
  laid, sans effet sur le terminal.
- La purge ne tourne que si l'application tourne ou si `shadowlab public purger` est lancé.

## Limites connues, pour le rejeu de l'étape 1.7

- Colonne `cookies` vide : la règle `cookies_ignores` du détecteur `regles-http` doit être neutralisée au
  rejeu. Par construction, toute observation publique a été reçue avec le cookie de session.
- Derrière un mandataire, l'ordre et la liste des en-têtes changent, et la liste blanche en retire : les
  règles d'ordre (`host_tardif`) ne valent rien sur ces données. Pas de TLS observé (pas de frontal).
- Sonde WebRTC sautée : le détecteur `webrtc` n'a rien à lire.
- `cdp_detection` sans `debugger_delta_ms`, `debugger_suspect` ni `has_first_input` (mesures sautées,
  `saute: "sans-tiers"`) : aucun détecteur ne les lit depuis D-62. Les sessions publiques ne peuvent donc pas
  servir à revalider ces deux mesures ; il faudrait des sessions `/manuel` du labo.
- Le dernier envoi « comportement » (au départ de la dernière page) peut arriver après « terminer » et être
  refusé.

## Message à envoyer avec le lien

Prêt à copier. Les sessions utiles sont celles faites **sur ordinateur** (le plan en demande au moins 10) ;
le lien d'un tunnel rapide change à chaque relance, donc l'envoyer juste après le lancement.

Version courte :

> Tu peux me rendre un service de 5 minutes ? Depuis un ordinateur (pas le téléphone), ouvre ce lien :
> LIEN
> C'est un faux réseau social de photos. Tu coches la case, « Commencer la session », tu te balades comme sur
> un vrai (quelques publications, quelques profils), puis « Terminer ma session » en haut. Ça m'aide à vérifier
> qu'un détecteur de robots ne prend pas les vraies personnes pour des robots. Rien de personnel n'est relevé
> (ni nom, ni e-mail, ni adresse IP), et tu peux tout effacer d'un clic.

Version détaillée, pour quelqu'un qui veut savoir avant de cliquer :

> Je travaille sur un projet de recherche autour de la détection des robots sur le Web. Pour le calibrer,
> j'ai besoin de quelques visites de vraies personnes sur un faux réseau social de photos.
> - Depuis un ordinateur, ouvre LIEN et lis la page d'accueil (et la notice complète, à un clic) : elles disent
>   exactement ce qui est relevé.
> - Coche la case, clique sur « Commencer la session », puis navigue 5 à 10 minutes comme tu le ferais
>   vraiment : ouvre des publications, des profils, fais défiler, change de page. Garde l'onglet au premier plan.
> - Clique sur « Terminer ma session » dans le bandeau du haut.
> Ce qui est relevé : les caractéristiques techniques de ton navigateur et ta façon de naviguer, en
> chiffres (nombre de clics, délais entre deux gestes). Jamais ce que tu tapes, ni ton nom, ni ton e-mail,
> ni ton adresse IP. Tout est effacé au bout de 90 jours, et la page « Ma session » permet de tout
> supprimer tout de suite.
