---
permalink: noezia-shadowlab/analyse-paliers-2026-11-11
title: analyse-paliers-2026-11-11
type: note
---

# Analyse du 11/11/2026 — ce qui existe et ce qui manque, par partie

Source du plan `docs/PLAN.md`. Quatre sous-agents ont lu le code en lecture seule (rien exécuté). Les points
marqués **[vérifié]** ont été recoupés par Claude dans le code ou la base ; les autres sont des lectures de
code à confirmer au moment de s'en servir. Chemins relatifs à `src/shadowlab/` sauf mention.

## 1. Mesure (campagnes, scénarios, sessions humaines)

Ce qui existe
- Un scénario rend un booléen, par égalité stricte avec les constantes de `site/pages.py:10-21`
  (`scenarios.py:101-124`, `269-290`). Seuls des compteurs sont gardés (`campaigns.py:641-642`).
- `/manuel/commencer` exige le consentement et crée un passage `truth='humain'` avec `consent_at`, dans
  l'expérience `sessions-manuelles` (`site/app.py:631-639`).
- Le taux de faux positifs par détecteur existe déjà : `analytics.py:127-159` et `200-304`, commande
  `shadowlab manuel` (`cli.py:297-319`), API `statistiques` (`api.py:135`), rapport HTML
  (`reports.py:126-133`). Rien dans l'interface React.
- Campagne 86 : la cause « arena : chaîne de protection injoignable » sort de `issues.py:88-89` dès qu'une
  décision de couche `arena` existe ; seule source : `arena/frontal.py:255-259`, quand le frontal ne joint
  plus Nginx. Docker est tombé vers 22h57 UTC. **[vérifié]** 19 pannes, 5 passages valides, 0 bloqué ;
  campagne 87 créée à 22:57:17 avec 0 passage.
- Blocage et classement : `issues.py:86-87` rend `extraction_reussie` dès que le scénario réussit ; le
  classement n'est qu'un drapeau. Le blocage se décide en direct à chaque page (`site/gardien.py:201-281`)
  avec les observations déjà reçues ; le classement se fait après la session (`passages.py:72-91`).
  Campagnes 84 et 85 : `bloque=0` sur 36 passages, parce que l'empreinte arrive après que la page est
  servie et que ces scénarios n'ouvrent qu'une page. Au niveau 03, `cdp` ne serait pas consulté
  (`configs/arena/profils.yaml:44-67`, non vérifié).
- Configuration la plus proche d'une référence : `configs/experiments/v4-comparative.yaml` (5 moteurs,
  niveaux 01 à 06, 6 scénarios, 2 répétitions). **[vérifié]**

Ce qui manque
- Récolte : un contenu de référence à plusieurs champs avec pages de détail, un scénario qui rend des
  enregistrements, une notation (pages récupérées / existantes, champs exacts / attendus) et son agrégation.
- Humains : le taux d'humains **bloqués** par niveau (`site/app.py:655` force le succès) ; la clôture
  automatique (une session non terminée est ignorée, `analytics.py:138`) ; le niveau 07 dans le formulaire
  (`site/pages.py:297-302`).
- **[vérifié]** `taux_detection` : les passages en panne comptent au numérateur (`detectes`, calculé sur
  toutes les lignes) mais pas au dénominateur (`evaluables`), `analytics.py:452-474`. Campagne 86 :
  22 / 5. Le « 23/23 » du journal contient des verdicts « sans JavaScript » dus à la panne.
- L'Arena n'est contrôlée qu'au lancement (`campaigns.py:342-344`) ; un site déjà lancé est réutilisé avec
  son ancien code (`campaigns.py:253-257`).
- Jamais mesurés : le niveau 07, la synchronisation défi/collecte du 11/11 (`site/static/defi.js:30-37`),
  un scénario à plusieurs pages depuis la campagne 76.
- **[vérifié]** La base réelle n'a jamais été ouverte avec le code du 11/11 : `PRAGMA user_version` = 7,
  pas de table `empreintes_vues`. La prochaine commande `shadowlab` appliquera la migration 8.

## 2. Arena (site vitrine, bannissement)

Ce qui existe
- `/lab/` sert `statique` (10 références), `dynamique` (une chaîne injectée en JavaScript), `catalogue`
  (5 pages, 50 `ART-nnn`, identifiant seul), `adaptatif` (4 annonces), une API JSON qu'aucune page ne lit
  (`site/pages.py:10-19`, `site/app.py:359`). Contenu en dur ou par formule, sans graine.
- État par visiteur : uniquement le jeton `sl`, neuf à chaque passage (`passages.py:33`) et fourni par le
  visiteur ; cookies signés d'une heure (`arena/defis.py:24`). L'IP est transmise par le frontal
  (`arena/frontal.py:236`), jamais stockée ni lue.
- Quasi-bannissements, indexés sur le jeton donc sans effet au passage suivant : débit Nginx par session,
  à la seconde, en mémoire (`arena/profils.py:181`) ; 5 tentatives de login (`site/app.py:257`) ; blocage
  différé (`site/gardien.py:217`) ; honeypot.
- Seul état entre passages et entre campagnes : `empreintes_vues` et `correlation-session`, niveaux 06-07
  (`correlation.py:48`, `detection.py:2390`) ; global, jamais purgé.
- Login : 2 comptes en dur (`site/comptes.py:13`) ; champ piège, tentatives, `suspicion()`, mot de passe,
  puis cookie `sl_connexion` lié au jeton et au JA4 (`site/app.py:232-297`). Ni table de comptes ni session
  serveur ; `/lab/espace` ne contient aucune donnée.
- `api`, `labo`, `tableau` sont des routeurs gardés par `autoriser` (`api.py:66`), inclus en fin de
  fabrique (`site/app.py:661`).

Ce qui manque
- **[vérifié pour la clé `proprietes`]** `hash_session` lit `proprietes.ecran` et `proprietes.canvas`
  (`correlation.py:19-39`), mais `site/static/observateur.js:1147-1181` envoie tout à plat : aucun hash
  canvas, écran vide. Le test repose sur une forme fictive (`tests/test_correlation.py:10`).
- Bannissement : (a) table de comptes avec état banni ; (b) IP stockée et signée ; (c) empreinte fiable
  (`visitorId` collecté, inutilisé) ; (d) cookie visiteur durable émis par le serveur ; (e) compteurs par
  heure et par jour ; (f) appareils connus par compte. Plus une table de bannissements lue en tête de
  `gardien.controler`.
- Pièges : sans jeton, aucune protection (`site/app.py:115`) ; tout vient de 127.0.0.1
  (`arena/frontal.py:461`) ; `empreintes_vues` est global, donc une campagne influence la suivante, et la
  5ᵉ session d'un même navigateur serait bloquée au niveau 06 (lu, non mesuré) ; contexte navigateur neuf à
  chaque passage (`campaigns.py:591`).
- Vitrine inutilisable telle quelle : manquent volume, fiches à plusieurs champs, pages de détail, images,
  liste chargée en JavaScript, contenu privé, fichier de vérité, habillage (l'en-tête affiche « site de test »).
- Mode public : aucun réglage ; `/lab` et `/manuel` sont des fermetures dans `creer_app` ; `/api/docs`
  échappe à `autoriser` (`site/app.py:75`) ; frontal lié à 127.0.0.1, certificat `localhost` ; `/manuel`
  renvoie vers `https://localhost` (`site/app.py:643`). Derrière Cloudflare, le frontal ne voit plus le TLS
  du visiteur.

## 3. Moteur (identité, endurance), `N/` = `engines/noezia/`

Ce qui existe
- Profil rejouable en théorie : l'option `profil` relit un JSON complet (graines canvas et audio, GPU,
  polices, écran, user-agent), `N/moteur.py:162-163`, `N/profils/stockage.py:35-42`,
  `N/profils/generateur.py:436-466`. Sans elle, le profil est tiré au hasard à chaque `open()`
  (`N/moteur.py:167`). Elle n'a jamais servi : `configs/profils/` n'existe pas, aucun YAML ne la passe.
- Stockage du navigateur : tout repart de zéro. `launch()` puis `new_context()` neuf à chaque session, sans
  `storage_state` ni dossier de profil (`N/moteur.py:194`, `:229`). C'est le contrat de `engines/base.py:3-4`.
- Rythme : seulement dans la page (`N/comportement/tempo.py:15-44`, `N/comportement/humain.py:182-222`).
  `pause_entre_pages` n'est appelée nulle part. Aucun budget par identité.
- Alerte : aucune notion. Réessai sur 429/5xx si `nb_essais` > 1, défaut 1 (`N/moteur.py:87`, `:366-389`).
  Un 403 incrémente un compteur (`:400-401`). Les défis sont résolus par défaut (`:408-409`, `:459-512`),
  reconnus par des URL et `data-arena` propres à l'Arena. `RefusProtection` vient des scénarios
  (`scenarios.py:87-98`).
- `recolte.py` : pool de processus, un moteur et un profil aléatoire par lot, session neuve par URL ; ni
  délai, ni état, ni reprise (`N/recolte.py:25-71`). Aucun appelant : la CLI `recolter` passe par
  `rapide.py`, sans navigateur (`cli.py:142`).
- Proxy unique : `SHADOWLAB_PROXY`, au lancement, sans identifiants, seulement en périmètre illimité
  (`N/moteur.py:351-363`).
- Linux : `--disable-dev-shm-usage` (`N/moteur.py:187-189`), masquage SwiftShader
  (`N/furtivite/webgl.js:24-36`, `:95-103`), 8 machines Linux (`N/profils/generateur.py:173-242`). Sans
  écran par défaut (`N/config.py:46`). Ni écran virtuel ni Dockerfile.

Ce qui manque
- **[vérifié]** `pool.py` est mort : il importe `MoteurNoezia` et appelle `aller()` et `contenu()`, qui
  n'existent pas (`N/pool.py:24`, `:96-97`) ; rien ne l'importe.
- Défauts d'identité : (a) un profil nommé est créé avec un système au hasard, pas celui de la machine
  (`stockage.py:40`) ; (b) son dossier est relatif au répertoire courant (`stockage.py:15`) ;
  (c) **[vérifié pour l'annonce]** l'user-agent annonce Chrome 129 à 132 (`generateur.py:245-250`) ; le
  Chromium embarqué serait plus récent (version non vérifiée) ; (d) langue et fuseau tirés au hasard, sans
  lien avec l'IP (`generateur.py:514`).
- Pas d'objet « identité » (profil, stockage, proxy, compteurs, état), ni budget, ni registre d'adresses,
  ni reprise. Pas d'arrêt au premier signe, ni de classement des signes (403, 429, défi, retour au login).
  Pas de proxy par identité avec identifiants.
- Jamais exécuté sur Linux : aucun test pour D-50 et D-51, aucune campagne.
- `plugins/` vide : pas un manque pour l'objectif.
- Non vérifié : le binaire lancé sans écran, la version exposée par `userAgentData`, l'effet réel du
  masquage SwiftShader, les polices d'un serveur.

## 4. Sécurité d'une mise en ligne publique

Bloquant
- L'authentification dépend de l'adresse d'écoute, pas de la requête (`api.py:49-52`, même garde pour
  `/labo` et `/tableau`). En 127.0.0.1 tout est ouvert ; derrière un mandataire ou un tunnel local, l'API
  devient publique sans jeton dès que l'en-tête Host vaut localhost (`site/app.py:154-164`). Ajouter le
  domaine public à `SHADOWLAB_HOTES_AUTORISES` change aussi le périmètre du moteur (même variable).
- API joignable + périmètre `*` (`config.py:68`) : `POST /api/experiences` (`api.py:291`) lance des
  navigateurs furtifs vers n'importe quelle URL, réseau interne compris (`scenarios.py:35`). Captures
  relisibles (`api.py:608`), jusqu'à 10 000 répétitions (`campaigns.py:93`), empreintes humaines et
  rapports lisibles (`api.py:180,249`).
- Pas d'application réduite : `creer_app` monte toujours l'API, `/labo` et `/tableau`
  (`site/app.py:661-667`). Swagger échappe à `autoriser` (`site/app.py:75`). La commande `site` démarre
  aussi le frontal (`cli.py:99`).
- Google contacté avant le consentement : le test WebRTC appelle `stun.l.google.com`
  (`observateur.js:399`), même sans jeton (`:1218`), y compris sur `/manuel` (`site/pages.py:63,309`). Cela
  contredit le texte de consentement (`site/pages.py:306-307`).
- Disque saturable anonymement : `/lab/collecte` accepte tout jeton au bon format, sans vérifier le passage
  ni le consentement (`site/app.py:371-374`), 64 Ko par requête, sans limite de débit. En-têtes stockés
  pour toute requête `/lab?sl=` (`site/app.py:98-113`). Chaque POST `/manuel/commencer` crée un passage.

Important
- Consentement : la case, le contrôle serveur et `consent_at` existent (`site/app.py:631-639`). Manquent la
  liste complète des données, la durée, le responsable, les droits. La mention « serveur local » devient
  fausse. CSRF possible sur `/manuel/commencer`. La collecte continue après `terminer`.
- Collecté (`observateur.js:1150-1238`) : user-agent, écran, fuseau, langues, GPU, canvas, polices, audio,
  périphériques, permissions ; délais souris et clavier (pas les touches), angles, défilement. Côté
  serveur : tous les en-têtes dont X-Forwarded-For (`arena/frontal.py:236`). Stockage dans
  `outputs/shadowlab.sqlite3`, plus un hash persistant qui relie les visites (`correlation.py:48-71`).
- Ni purge ni suppression par personne. `reports.supprimer` oublie `decisions`, `empreintes_vues` et
  `observations_tls` (`reports.py:308-330`).
- Tiers : Turnstile et reCAPTCHA chargés depuis Cloudflare et Google (`site/pages.py:230,384,408`).
  FingerprintJS et BotD sont auto-hébergés, télémétrie coupée.
- HTTP seul, cookies sans `Secure` (`site/app.py:144,291`), jeton dans l'URL donc dans les journaux.

Mineur
- Charge non-objet : erreur 500 après insertion (`correlation.py:20`) ; message SQLite renvoyé au client
  (`site/app.py:671`). `*.db-wal` et `*.db-shm` non ignorés par git. Page de connexion de test exposée.
  Aucun `innerHTML` trouvé, rapports échappés.

Non vérifié : `.env`, historique git, configuration du futur mandataire, exploitation réelle.
