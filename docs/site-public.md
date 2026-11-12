# Site public — application réduite (étape 1.6)

Mis à jour : 12/11/2026. Code : `src/shadowlab/public/`. Tests : `tests/test_public.py`.

## Ce que c'est

Une petite application Python, **à part du laboratoire**, faite pour être mise en ligne. Elle sert :

- la page d'information et de consentement (`/`) ;
- le site vitrine (`/lab/vitrine…`, mêmes chemins et même code que dans le labo : `site/vitrine.py`) ;
- les sessions humaines de référence (`POST /session/commencer`, `POST /session/terminer`,
  `POST /session/supprimer`, tous protégés contre le CSRF) et la page « Ma session » (`GET /session`) ;
- la collecte de l'observateur (`POST /lab/collecte`), seulement pendant une session consentie ;
- le formulaire de contact (`GET /contact`, `POST /contact`, `GET /contact/envoye`, D-57) : écrire au
  responsable sans qu'une adresse soit affichée ;
- quatre fichiers statiques, en liste fermée : `observateur.js`, `vendor/botd-2.0.0.esm.js`, `vitrine.css`, `vitrine.js`.

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
- Le journal du tunnel (`outputs/public/tunnel.log`, niveau `info`) ne contient aucune requête.

Pour un lien stable : un domaine chez Cloudflare (option A) ou une petite machine à part (options B et C).
Vercel et Netlify ne conviennent pas : pas de processus continu ni de disque durable pour la base SQLite.
Non vérifié au 12/11 : le script n'a jamais tourné avec un vrai tunnel (syntaxe, refus sans contact et
lecture de l'adresse vérifiés à vide).

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

### Adresse du visiteur

Elle ne sert qu'aux deux limites par adresse (ouverture de sessions, messages de contact), **en mémoire**,
sous forme d'empreinte salée, jamais écrite. Si l'en-tête est mal réglé, tous les visiteurs partagent la
même adresse (celle du mandataire ou de Cloudflare) et ces limites deviennent globales : 6 sessions et
3 messages par heure pour tout le monde.

### Limites (constantes, `public/app.py`, classe `Limites`)

| Limite | Valeur | Pourquoi |
|--------|--------|----------|
| Sessions ouvertes par adresse | 6 par heure glissante | Disque, en mémoire seulement |
| Sessions ouvertes par jour | 40, toutes adresses | Disque ; compté en base, survit au redémarrage |
| Taille de la base (+ WAL) | 2 Gio ; au-delà, plus aucune session ne s'ouvre et **plus rien ne s'écrit** (requêtes servies sans être notées, collecte en 503) | Disque |
| Envois de l'observateur par session | 300 (deux par page) | Disque |
| Volume des envois par session | 4 Mio (~10 Ko par empreinte) | Disque |
| Imbrication d'un envoi | 32 niveaux (l'observateur en a 5 au plus) ; au-delà, 400 | Mémoire, pile |
| Requêtes HTTP notées par session | 3 000 (~17 par page) ; au-delà, servies mais plus notées | Disque |
| Une requête notée | en-têtes : 40 au plus, nom ≤ 64 car., valeur ≤ 512 car., JSON ≤ 2 048 octets ; méthode ≤ 16, chemin ≤ 200 | Disque |
| Corps d'un envoi | 64 Kio, annoncé ou réel | Mémoire, disque |
| Durée d'une session | 2 heures (cookie et contrôle serveur) | Un cookie volé ne sert pas longtemps |
| Messages de contact | 2 000 caractères ; 3 par heure glissante et par adresse (en mémoire), 30 par jour, 500 gardés (au-delà, 503 jusqu'à la purge ou un effacement à la main) ; formulaire borné à 12 octets par caractère permis, plus 1 Kio | Disque : quelques Mo au pire (500 messages de 8 Ko, non mesuré) |

**Pire cas, mesuré** (12/11/2026, base temporaire, ces bornes atteintes) : une session occupe 16,9 Mo —
12,6 Mo pour 3 000 requêtes aux en-têtes de 2 Ko (une ligne de ~2,3 Ko prend une page SQLite de 4 Kio) et
4,3 Mo d'envois. À 40 sessions par jour : **environ 680 Mo par jour**. Le plafond de 2 Gio est contrôlé à
chaque écriture ; il ne peut être dépassé que des lignes déjà en cours d'écriture (une par requête
simultanée, 64 Kio au plus chacune). Sous abus soutenu, il est donc atteint en 3 jours environ : le site
reste visitable mais n'ouvre plus de session jusqu'à la purge ou une suppression à la main (voir
« Limites connues »). Une purge ne réduit pas le fichier, mais ses pages libérées sont réutilisées.

## Purge et suppression

- **Automatique** : au démarrage, puis au plus une fois par 24 h à la première requête reçue. Une session
  est effacée de toutes les tables `SHADOWLAB_PUBLIC_CONSERVATION_JOURS` jours après son début.
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
  `uv run shadowlab public effacer-message <n°>` en efface un. Ils suivent la même purge que les sessions
  (démarrage, une fois par 24 h, commande `purger`). `servir` annonce leur nombre au démarrage et écrit
  « message de contact reçu » à l'écran à chaque arrivée ; rien n'est envoyé ailleurs : il faut regarder
  l'écran ou lancer la commande de temps en temps (une demande d'effacement se traite sous un mois).
- La base est ouverte avec `PRAGMA secure_delete=ON` : ce qui est effacé est écrasé, pas seulement délié.

## Journaux

L'application écrit une ligne par requête (`méthode chemin statut`, niveau DEBUG) dans
`<dossier de la base>/logs/shadowlab.jsonl` (à l'écran seulement avec `--verbeux`) : ni adresse, ni chaîne
de requête, ni en-tête, ni jeton. Le journal d'accès d'uvicorn est coupé (`access_log=False`) et l'en-tête
`Server` aussi. **Rotation** (`public.ROTATION_JOURNAL`) : 5 Mio par fichier, le courant et 3 anciens,
donc 20 Mio au plus (`test_journal_tourne_avec_taille_et_nombre_bornes`). Le journal du labo, lui, ne
tourne pas (inchangé).

## Cookies

Tous `HttpOnly`, `SameSite=Lax`, `Path=/`, et en HTTPS `Secure` avec le préfixe `__Host-`. Signés (HMAC,
clé `secret`) sauf `slp-csrf`, qui n'est qu'une valeur au hasard.

| Cookie | Posé | Durée | Rôle |
|--------|------|-------|------|
| `slp-csrf` | dès la première page à formulaire, **avant tout accord** | fermeture du navigateur | Anti-CSRF (double soumission) ; jamais enregistré en base |
| `slp-session` | à « Commencer » | 2 h, effacé à « Terminer » | Relie les pages à la session en cours |
| `slp-droits` | à « Commencer » | durée de conservation (90 j), effacé à la suppression | Retrouver et supprimer sa session depuis « Ma session » |

La page d'information les décrit tous les trois (`test_page_d_information_decrit_cookies_et_transit`).

## Ce qui est stocké

Base publique, tables du schéma du labo (aucune migration ajoutée) :

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
- Aucune autre table n'est écrite : ni `empreintes_vues` (pas de hash de corrélation entre visites), ni
  `decisions`, `detections`, `fingerprints` (aucun détecteur ne tourne). La suppression les couvre quand même.
- `<dossier de la base>/messages.sqlite3` (droits 600, `secure_delete`) : les messages du formulaire de
  contact, **dans un fichier à part** : le texte (caractères de contrôle retirés, espaces insécables changées
  en espaces) et le **jour** de réception, rien d'autre. Ni adresse IP, ni session, ni navigateur, ni heure.
  La base des sessions peut ainsi être copiée pour le rejeu sans emporter des messages où un visiteur a
  écrit comment le joindre. Les pages de contact répondent avec `Referrer-Policy: no-referrer` : la page
  ouverte ensuite ne dit pas qu'on en vient. Reste une trace indirecte : pendant une session en cours, la
  feuille de style que ces pages chargent (`/lab/static/vitrine.css`) est notée comme toute requête
  `/lab/…`, sans référent ; avec le seul jour du message, elle ne suffit pas à désigner son auteur dès que
  plusieurs sessions ont lieu ce jour-là. Une base nommée `messages.sqlite3` est refusée au démarrage.
- `<dossier de la base>/secret` (droits 600) : clé de signature des cookies. Le dossier `outputs/` est
  ignoré par git. Un fichier `secret` vide est refusé (erreur claire au démarrage, labo compris) : sinon
  n'importe qui pourrait forger les cookies signés. Le supprimer pour qu'il soit recréé.

La liste lisible des données, sur la page d'information, est tirée de `observateur.js` clé par clé ; un test
échoue si le script envoie un champ qu'elle ne décrit pas.

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
| E. Formulaire de contact (D-57) | `test_contact_remplace_l_adresse_dans_les_pages`, `test_contact_textes_exacts`, `test_contact_enregistre_le_message_a_part_sans_adresse` (jour seul, pas de référent), `test_contact_protege` (origine, CSRF, texte rendu), `test_contact_message_vide_ou_trop_long`, `test_contact_retire_les_caracteres_de_controle`, `test_contact_limite_par_adresse`, `test_contact_plafond_par_jour_et_boite_pleine`, `test_purge_des_messages`, `test_commandes_messages`, `test_base_nommee_comme_la_boite_refusee` |

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
- Utilisateur sans privilège ; dossier de la base en `700` (la base est créée avec les droits par défaut).
- Surveillance du disque (le journal de l'application tourne seul, 20 Mio au plus).

## Limites connues de l'application

- **Quotas non atomiques.** Le quota d'une session (envois, volume, requêtes notées), le plafond quotidien et
  le plafond de taille sont lus puis écrits sans verrou : des envois parallèles peuvent les dépasser de
  quelques unités (une par requête simultanée). Sans conséquence sur le disque à cette échelle.
- **Plafond quotidien épuisable.** 40 sessions par jour pour tout le monde : un script qui change d'adresse
  peut les consommer et priver les vrais participants de la journée (et remplir la base en 3 jours environ,
  voir « Limites »). Parade : limitation de débit au mandataire (ci-dessus), surveillance, suppression à la
  main des sessions abusives (`shadowlab public supprimer`).
- **Formulaire de contact blocable.** Un script qui change d'adresse épuise les 30 messages du jour en
  quelques minutes, et remplit la boîte (500 messages) en 17 jours : le formulaire refuse alors tout (503)
  jusqu'à la purge ou jusqu'à `shadowlab public effacer-message`. Parade : limitation de débit au mandataire,
  et lire la boîte de temps en temps. Sans cookie (navigateur réglé pour tous les bloquer), le formulaire ne
  peut pas être envoyé : le jeton anti-CSRF en dépend, comme pour les autres formulaires ; le texte tapé est
  rendu à chaque refus.
- **SQLite bloque la boucle asynchrone.** Chaque accès à la base se fait dans la boucle d'uvicorn, sans
  fil séparé : acceptable pour une dizaine de participants simultanés, pas pour du trafic réel.
- **Onglet en arrière-plan.** La sonde d'empreinte attend `requestAnimationFrame`, sans délai maximal :
  dans un onglet caché, l'empreinte ne part qu'au retour de l'onglet au premier plan (et jamais si l'onglet
  est fermé avant). La sonde n'est pas modifiée ; la page d'information et le bandeau demandent de garder
  l'onglet visible.

## Limites connues, pour le rejeu de l'étape 1.7

- Colonne `cookies` vide : la règle `cookies_ignores` du détecteur `regles-http` doit être neutralisée au
  rejeu. Par construction, toute observation publique a été reçue avec le cookie de session.
- Derrière un mandataire, l'ordre et la liste des en-têtes changent, et la liste blanche en retire : les
  règles d'ordre (`host_tardif`) ne valent rien sur ces données. Pas de TLS observé (pas de frontal).
- Sonde WebRTC sautée : le détecteur `webrtc` n'a rien à lire.
- Le dernier envoi « comportement » (au départ de la dernière page) peut arriver après « terminer » et être
  refusé.

## Message à envoyer avec le lien

Prêt à copier. Les sessions utiles sont celles faites **sur ordinateur** (le plan en demande au moins 10) ;
le lien d'un tunnel rapide change à chaque relance, donc l'envoyer juste après le lancement.

Version courte :

> Tu peux me rendre un service de 5 minutes ? Depuis un ordinateur (pas le téléphone), ouvre ce lien :
> LIEN
> C'est un faux site d'annonces immobilières. Tu cliques sur « Commencer la session », tu te balades comme
> sur un vrai site (quelques annonces, quelques pages), puis « Terminer ma session » en haut. Ça m'aide à
> vérifier qu'un détecteur de robots ne prend pas les vraies personnes pour des robots. Rien de personnel
> n'est relevé (ni nom, ni e-mail, ni adresse IP), et tu peux tout effacer d'un clic.

Version détaillée, pour quelqu'un qui veut savoir avant de cliquer :

> Je travaille sur un projet de recherche autour de la détection des robots sur le Web. Pour le calibrer,
> j'ai besoin de quelques visites de vraies personnes sur un faux site d'annonces immobilières.
> - Depuis un ordinateur, ouvre LIEN et lis la page d'accueil : elle dit exactement ce qui est relevé.
> - Coche la case, clique sur « Commencer la session », puis navigue 5 à 10 minutes comme tu le ferais
>   vraiment : ouvre des annonces, fais défiler, change de page. Garde l'onglet au premier plan.
> - Clique sur « Terminer ma session » dans le bandeau du haut.
> Ce qui est relevé : les caractéristiques techniques de ton navigateur et ta façon de naviguer, en
> chiffres (nombre de clics, délais entre deux gestes). Jamais ce que tu tapes, ni ton nom, ni ton e-mail,
> ni ton adresse IP. Tout est effacé au bout de 90 jours, et la page « Ma session » permet de tout
> supprimer tout de suite.
