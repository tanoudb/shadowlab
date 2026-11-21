# Collecte externe : le contrat de données

Un site à nous (cas visé : un site d'Ethan avec de vraies sessions humaines) charge nos deux scripts d'observation,
range ce qu'ils envoient dans sa propre base, puis nous remet un **export** que `shadowlab externe analyser` fait
juger par les détecteurs de l'Arena. Ce document est le contrat entre les deux : **la forme exacte d'une session**.
Le site suit ce document ; le code qui le vérifie est `src/shadowlab/externe/analyse.py` (`lire_session`).

Ce document ne parle que de la partie ShadowLab. Il ne dit rien du site lui-même (autre dépôt).

## Règle d'or

**Jamais** dans une session, ni dans l'export, ni dans la base du site :

- ce que la personne **tape** (une touche, un texte, un champ, le presse-papiers, une sélection) ;
- son **adresse IP** en clair (ni `X-Forwarded-For`, ni `CF-Connecting-IP`, ni un condensat simple de l'adresse) ;
- un **identifiant de personne** lisible : courriel, nom, identifiant de compte du site. Seul un identifiant **masqué**
  est permis (voir « Le compte »).

Le pont refuse toute ligne qui sort de ce cadre : clé inconnue, courriel ou adresse IP dans le contexte ou un chemin,
chemin avec `?` ou `#`, compte non masqué, trace invalide. Une ligne refusée est comptée et dite, jamais corrigée.

La collecte se fait **sur consentement explicite** (case à cocher, refusée par défaut) et la personne peut demander la
suppression de sa session. Le site range ce consentement (version du texte, date) à part ; il ne fait pas partie de
l'export.

## Mettre les scripts sur le site

`uv run shadowlab externe paquet <dossier>` écrit ces fichiers, sans la marque du projet (règle D-81, vérifiée par
`script_public.noms_trouves` : aucun de `noezia`, `shadowlab`, `shadow lab`) :

| Fichier | Rôle |
|---|---|
| `observateur.js` | empreinte du navigateur (un envoi `empreinte` au chargement, un envoi `comportement` à la sortie de la page) |
| `vendor/botd-2.0.0.esm.js` (+ `botd-LICENSE.txt`) | bibliothèque importée par `observateur.js` (`./vendor/…`) : à servir **à côté** de lui |
| `releve.js` | relevé des gestes en nombres entiers (envois `trace`) |
| `manifeste.json` | empreinte SHA-256 de chaque script, noms des balises lues |

Le site les sert depuis son propre domaine et, **pendant une session consentie seulement**, met dans la page :

```html
<meta name="sl-session" content="JETON">            <!-- jeton opaque de la session, voir plus bas -->
<meta name="sl-collecte" content="/api/chemin-de-la-route">   <!-- sa propre route ; chemin de la même origine -->
<meta name="sl-sans-tiers" content="1">             <!-- pas de sonde WebRTC vers un serveur extérieur -->
<script type="module" src="/…/observateur.js"></script>   <!-- module : il importe ./vendor/botd-… -->
<script src="/…/releve.js" defer></script>
```

La politique de sécurité du site (CSP) doit laisser passer : `script-src` pour ces fichiers (même origine), **`worker-src blob:`** (une sonde d'`observateur.js` crée un petit worker à partir d'un blob ; refusée, la sonde `worker_consistency` signale une erreur au lieu d'une valeur) et `connect-src` vers la route de collecte. FingerprintJS n'est **pas** dans le paquet : le script ne le charge que sur deux pages du labo, et la clé `fpjs` de l'empreinte vaut `null` sur un site externe.

- Sans `sl-session`, les deux scripts ne font rien (aucun écouteur, aucun envoi).
- Sans `sl-collecte`, ou si sa valeur n'est pas un chemin de la même origine (`https://…`, `//…`, `/\…` sont refusés),
  l'envoi retombe sur `/lab/collecte`, comme avant : le site public actuel ne change pas d'un octet de comportement.
- `sl-sans-tiers` = `1` est **demandé** : sans lui, `observateur.js` ouvre une connexion WebRTC vers un serveur STUN de
  Google, qui verrait l'adresse IP de la personne. Avec lui, la sonde est sautée et le détecteur `webrtc` est noté
  « non évalué ».

## Ce que la route du site reçoit

Un `POST <sl-collecte>?sl=<jeton>` (ou `&sl=` si la route a déjà une requête), corps JSON, `Content-Type:
application/json` (envoyé par `fetch`, ou par `sendBeacon` à la sortie de la page) :

```json
{ "kind": "empreinte" | "comportement" | "trace", "page": "/chemin/de/la/page", "payload": { … } }
```

- `page` est `location.pathname` : un chemin, jamais l'adresse complète.
- Réponse attendue : `204`. Les scripts ignorent la réponse ; un échec ne gêne jamais la page.
- La route **doit** : refuser un `kind` inconnu ; refuser une `trace` que `public/trace.py` n'accepte pas (voir plus bas ;
  la liste exacte des clés et des bornes y est la seule source) ; refuser un jeton inconnu ou une session terminée ;
  limiter le nombre et le volume des envois par session (le site public prend 1 000 envois de trace et 4 Mio de trace
  par session, `public/app.py`) ; **masquer** les identifiants d'extension de navigateur
  (`chrome-extension://abc…` devient `chrome-extension://masque`, voir `public/donnees.py`, `masquer_extensions`) avant
  d'écrire. Le pont les masque aussi à la lecture.
- La route **ne range jamais** : l'adresse IP, `Cookie`, `Authorization`, `Referer`, ni aucun en-tête de la requête
  d'envoi, hors ce qui est listé dans « Une session ».

### L'envoi `empreinte` (`observateur.js`)

Un par chargement de page complet (une session peut en avoir plusieurs : rechargement, navigation complète). `payload` : un objet dont les clés de premier niveau sont exactement celles-ci
(41 clés ; `fpjs` vaut `null` hors du labo ; `duree_collecte_ms` est un entier, le reste des objets) :

`navigateur`, `ecran`, `fenetre`, `fuseau`, `apis`, `permissions`, `webgl`, `canvas`, `prototypes`, `integrite`,
`timing`, `chrome_apis`, `media_codecs`, `iframe_test`, `languages_test`, `webrtc_test`, `headless_signals`,
`stack_trace_test`, `performance_memory`, `paint_timing`, `automation_globals`, `css_media`, `prototype_chain`,
`timing_precision`, `canvas_consistency`, `stack_getter`, `raf_timing`, `domrect_fingerprint`, `audio_context`,
`font_fingerprint`, `math_constants`, `deep_proxy`, `cdp_detection`, `worker_consistency`, `connection_dynamic`,
`uadata_integrity`, `enumerable_props`, `automation`, `botd`, `fpjs`, `duree_collecte_ms`.

Le site range ce `payload` **tel quel** (jsonb), sans le trier ni le réécrire : les détecteurs lisent des sous-clés
précises, et une clé retirée change un verdict. Le site public (`public/pages.py`, liste des données de la notice)
décrit ce que chacune contient ; ce contenu est une **empreinte d'appareil** : le texte de consentement doit le dire.
Il ne contient ni adresse IP (la sonde WebRTC ne garde que des compteurs), ni texte tapé.

### L'envoi `comportement` (`observateur.js`)

Un par chargement de page complet, envoyé à la sortie de la page (`pagehide`, par `sendBeacon`). `payload` : exactement
`evenements` (compteurs par type d'événement), `premiere_interaction_ms`, `duree_page_ms`, `delais_souris_ms`,
`delai_souris_max_ms`, `angles_segments`, `delais_clavier_ms` (**délais entre frappes seulement**, jamais la touche),
`delais_scroll_ms`, `wheel_deltas`, `page_defilable`. Le site range le `payload` tel quel.

### L'envoi `trace` (`releve.js`)

Format de `src/shadowlab/public/trace.py` (`SCHEMA`, version 1). **Le site applique ce validateur avant d'écrire** (en
Python : `shadowlab.public.trace.valider`; en TypeScript : refaire les mêmes règles ; le pont en revalide chaque
trace et refuse la session sinon). Une trace n'est faite que de **nombres entiers** : jamais un booléen, un nombre à
virgule, `NaN`, l'infini, ni du texte. Exactement ces clés, ni plus ni moins :

| Clé | Forme | Bornes |
|---|---|---|
| `version` | entier | 1 |
| `morceau` | entier | 0 à 59 (numéro de l'envoi pour cette page) |
| `raison` | entier | 0 tampon plein, 1 arrière-plan, 2 sortie de la page |
| `instant_ms` | entier | 0 à 10 800 000 (ms depuis l'ouverture de la page) |
| `cadre` | 7 entiers | largeur et hauteur de la fenêtre (0 à 100 000), de la page (0 à 1 000 000), défilement vertical (± 1 000 000), rapport de pixels × 100 (1 à 10 000), pointeur (0 inconnu, 1 précis, 2 grossier) |
| `ecartes` | entier | 0 à 100 000 000 (relevés non gardés, plafond atteint) |
| `souris` | liste plate, 3 par ligne, 600 lignes au plus | instant ; x, y (± 100 000) — dès la 2ᵉ ligne : différences avec la précédente |
| `clics` | 6 par ligne, 100 lignes | instant ; x, y ; bouton (−1 à 15) ; sorte d'élément (0 autre, 1 lien, 2 bouton, 3 image, 4 zone de texte) ; pointeur (0 à 3) |
| `defilement` | 2 par ligne, 300 | instant ; position verticale (± 1 000 000) |
| `molette` | 4 par ligne, 300 | instant ; pas x, y (± 100 000) ; unité (0 pixel, 1 ligne, 2 page) |
| `clavier_appuis` | 2 par ligne, 200 | instant ; dans une zone de texte (0 ou 1). **Jamais la touche.** |
| `clavier_relaches` | 1 par ligne, 200 | instant |
| `tactile` | 7 par ligne, 300 | instant ; x, y ; doigts (0 à 20) ; rayon (−1 absent à 10 000) ; pression × 100 (−1 à 100) ; phase (0 début, 1 mouvement, 2 fin, 3 annulé) |
| `premier_plan` | 2 par ligne, 50 | instant ; visible (0 ou 1) |
| `focus` | 2 par ligne, 50 | instant ; fenêtre active (0 ou 1) |
| `redimensionnements` | 3 par ligne, 50 | instant ; largeur, hauteur (0 à 100 000) |

Une liste est une liste **plate** d'entiers (longueur multiple de la largeur d'une ligne, au plus « lignes × largeur »).
La trace est rangée **compacte**, reconstruite à partir des seules clés du schéma (jamais le corps reçu tel quel).

**Les traces ne sont jugées par aucun détecteur pour l'instant.** Le pont les vérifie et les compte ; elles servent à
préparer une étude du comportement (souris, défilement, toucher) quand il y aura assez d'humains connus.

## Une session (le format de l'export)

L'export est un fichier **JSONL** : une session par ligne, en UTF-8. Le site le produit depuis sa base (jointure de la
session, de ses envois et de son contexte) ; ShadowLab ne lit jamais la base du site (aucun secret, aucun réseau).

```json
{
  "format": 1,
  "jeton": "x7Kp2…",
  "debut": "2026-11-20T18:02:11.000+00:00",
  "user_agent": "Mozilla/5.0 (…) Chrome/142.0.0.0 Safari/537.36",
  "entetes": { "accept-language": "fr-FR,fr;q=0.9", "sec-ch-ua": "…", "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": "\"macOS\"" },
  "pages": [ { "instant": "2026-11-20T18:02:12.000+00:00", "chemin": "/manhwa/serie/chapitre-1" } ],
  "empreintes": [ { "page": "/manhwa/serie", "instant": "2026-11-20T18:02:15.000+00:00", "payload": { … } } ],
  "comportements": [ { "page": "…", "instant": "…", "payload": { … } } ],
  "traces": [ { "page": "…", "instant": "…", "payload": { … } } ],
  "contexte": { "compte": "u_3f9a…", "chapitres": [ { "serie": "serie", "chapitre": 1, "instant": "…" } ] }
}
```

| Champ | Obligatoire | Règle |
|---|---|---|
| `format` | oui | l'entier `1` |
| `jeton` | oui | **opaque** : 8 à 64 caractères parmi lettres, chiffres, `_`, `-`. Tiré au hasard par le site au début de la session ; ne dérive ni d'un compte, ni d'une IP, ni d'un cookie existant. Unique dans l'export. |
| `debut` | oui | instant ISO 8601 **avec fuseau** (le pont le ramène en UTC) |
| `user_agent` | oui | l'en-tête `User-Agent` de la première page de la session (texte imprimable, 512 caractères au plus) |
| `entetes` | non | uniquement `accept-language`, `sec-ch-ua`, `sec-ch-ua-mobile`, `sec-ch-ua-platform` (texte imprimable, 512 au plus). Toute autre clé : session refusée. **Jamais** `cookie`, `x-forwarded-for`, `cf-connecting-ip`, `referer`. |
| `pages` | oui | au moins une : `{ instant, chemin }`, une par page consultée, dans l'ordre. `chemin` = chemin seul (`/…`, 200 caractères au plus, caractères `A-Za-z0-9._~%/@,+-`, **ni `?` ni `#`**). Au plus 5 000. |
| `empreintes` | oui | les envois `empreinte`, au moins un : `{ page, instant, payload }`. Comme `shadowlab rejeu`, **la première** (la plus ancienne) est celle que lisent les détecteurs. Sans elle, la session ne peut pas être jugée. |
| `comportements` | non | les envois `comportement` : `{ page, instant, payload }`. Sans eux, le détecteur `comportement` est « non évalué ». |
| `traces` | non | les envois `trace`, validés (voir plus haut). |
| `contexte` | non | ce que le site ajoute (voir « Le contexte ») |

Les instants de `pages`, `empreintes`, `comportements` et `traces` sont ceux de la **réception par le site**
(horloge du serveur, UTC). Ils fixent l'ordre des événements, que les détecteurs utilisent (rythme, durée des pages).

### Le contexte (côté serveur)

```json
"contexte": {
  "compte": "u_3f9a1c0be4d27a56" ,
  "chapitres": [ { "serie": "slug-de-la-serie", "chapitre": 12, "instant": "2026-11-20T18:05:40.000+00:00" } ]
}
```

- `compte` : `null` (visiteur sans compte) ou **identifiant masqué** : `u_` suivi de 12 à 64 chiffres hexadécimaux. Le
  site le calcule en HMAC-SHA256 de l'identifiant interne avec un **secret gardé sur le site, jamais exporté**, tronqué.
  Même compte, même valeur (on peut compter les sessions d'une même personne, pas la retrouver). Ni courriel, ni nom,
  ni identifiant du site tel quel.
- `chapitres` : les séries et chapitres lus pendant la session. `serie` et `chapitre` : identifiants courts (lettres,
  chiffres, `.`, `_`, `-`, 60 au plus), pas de titre libre. `instant` facultatif.
- Aucune autre clé. Ni IP, ni pays, ni ville, ni appareil nommé.

## Ce que `shadowlab externe analyser` fait (et ne fait pas)

`uv run shadowlab externe analyser <export.jsonl> [--niveaux 04,05,06] [--json]` lit l'export, contrôle chaque ligne,
puis fait passer chaque session dans les détecteurs de chaque niveau, avec **le même code que `shadowlab rejeu`**
(`rejeu.juger`, `gardien.motifs_suspicion`, mêmes moments de décision, mêmes taux avec intervalle de Wilson). Sortie, par
niveau : sessions jugées, arrêtées, passées, détecteur responsable et signaux.

Ce qui n'est **pas évalué** est dit, jamais deviné :

| Écarté | Pourquoi |
|---|---|
| `tls`, `h2` | le site externe n'est pas derrière notre frontal TLS |
| `regles-http` | seuls le User-Agent et quelques en-têtes sont transmis : on ne juge pas l'ordre des en-têtes ni les cookies |
| `correlation-session` | pas d'historique de mondes ni de visites |
| `honeypot` | aucun piège servi |
| `webrtc` | sonde sautée (`sl-sans-tiers`) |
| `comportement` (par session) | aucun envoi `comportement` reçu |
| règle `sans_ressources` | le site ne relève pas les fichiers que ses pages chargent |

Les chemins des pages sont rangés en mémoire sous `/lab/externe` pour que le code de l'Arena les traite comme des pages
de son site ; ce préfixe ne sort pas du pont. Le fichier `tests/donnees/sessions-externes-exemple.jsonl` montre trois
sessions **fictives** au bon format : `uv run shadowlab externe analyser tests/donnees/sessions-externes-exemple.jsonl`.

## Pièges connus (à lire avant d'interpréter un chiffre)

- **Site à navigation sans rechargement** (Next.js) : `observateur.js` ne s'exécute qu'à un chargement complet. Il envoie
  alors **un** `empreinte` au début et **un** `comportement` à la sortie, qui résume toute la visite d'un coup
  (`duree_page_ms` très longue, délais de souris plafonnés à 50, de clavier à 40). Les détecteurs ont été réglés sur des pages courtes : le biais
  est **inconnu**. Les `pages` de la session (changements de route notés par le site) permettent au moins de compter les
  pages, mais elles ne remplacent pas un relevé par page. À mesurer avant de se fier à `comportement`.
- Un `comportement` n'arrive que si `sendBeacon` part (onglet fermé par un plantage ou un mobile en arrière-plan :
  perdu). Une session sans lui n'est pas jugée sur ce détecteur, ce qui flatte le taux de passage.
- Le consentement choisit les lecteurs : un échantillon de volontaires n'est pas le trafic. Le trafic derrière
  Cloudflare est d'ailleurs déjà filtré par ses défis : les robots les plus faciles n'arrivent pas.
- Aucune session n'est une « vérité humaine » prouvée : un lecteur consentant peut être un robot (comme pour les
  sessions du site public). Le pont dit « arrêtée par tel détecteur », pas « robot ».

## Ce que le site doit encore faire (hors ShadowLab)

À faire par la session qui travaille sur le site, d'après ce contrat :

1. Table de sessions (jeton opaque, début, user-agent, en-têtes permis, compte masqué, version et date du consentement,
   statut, date de suppression) et table de messages (jeton, `kind`, page, instant de réception, `payload` jsonb), plus
   les pages et chapitres lus. Aucune colonne d'IP.
2. Route d'écriture à `sl-collecte` : valide le jeton, le `kind`, la trace (mêmes règles que `trace.py`), les plafonds,
   masque les extensions, ne range rien d'autre ; `204`.
3. Consentement explicite (refusé par défaut), texte qui nomme l'empreinte d'appareil et les gestes (nombres seulement),
   bouton pour supprimer sa session ; le script n'est chargé qu'après le oui.
4. HMAC du compte avec un secret serveur ; jeton tiré au hasard.
5. Un export JSONL au format ci-dessus (vue ou script côté site), sans secret ; puis `shadowlab externe analyser`.
6. Limitation de débit chez le site (sans ranger l'IP) pour qu'on ne remplisse pas la base.

## Taille, quotas et rétention

Pour qu'une petite base ne sature pas. **L'objectif n'est pas le volume** : quelques centaines à quelques milliers de
bonnes sessions suffisent à calibrer les détecteurs. Mieux vaut peu de sessions complètes que beaucoup de sessions
gardées pour rien.

### Ordre de grandeur d'une session

Plafond de la trace **par page** (table `CLES` de `releve.js`, « lignes par page » × largeur de ligne) :

| Liste | Lignes par page | Largeur | Entiers |
|---|---|---|---|
| `souris` | 9 000 | 3 | 27 000 |
| `tactile` | 4 500 | 7 | 31 500 |
| `molette` | 4 500 | 4 | 18 000 |
| `defilement` | 4 500 | 2 | 9 000 |
| `clavier_appuis` | 3 000 | 2 | 6 000 |
| `clavier_relaches` | 3 000 | 1 | 3 000 |
| `clics` | 600 | 6 | 3 600 |
| `redimensionnements` | 200 | 3 | 600 |
| `premier_plan`, `focus` | 200 chacune | 2 | 800 |
| **Total** | | | **environ 99 500 entiers** |

- **Pire cas d'une page** : environ 100 000 entiers, soit **environ 450 Ko** de JSON brut (4 à 5 octets par entier,
  virgule comprise). Ce plafond n'est jamais atteint en lecture normale : il borne un client truqué.
- **Plafond par envoi** : 60 envois par page, et le site public refuse au-delà de 1 000 envois ou 4 Mio de trace par
  session (`public/app.py`). C'est le maximum d'une session, pas sa taille normale.
- **Page lue normalement** (estimation, **non mesurée**) : quelques centaines à 2 000 entiers, soit **1 à 10 Ko** brut.
  Une session de 30 pages : **environ 30 à 300 Ko** de trace brute.
- **Après compression** (gzip ou zstd ; les entiers sont déjà écrits en différences avec la ligne précédente, donc petits
  et répétitifs) : facteur attendu **5 à 10**, soit **environ 5 à 50 Ko** par session de 30 pages.
- **Empreinte** : un objet de quelques dizaines de Ko par chargement complet de page (estimation, **non mesurée** sur un
  vrai navigateur ; la liste des polices et les en-têtes de fonctions en sont le gros). Elle se compresse bien aussi
  (4 à 8 fois).
- **Donc** : compter **environ 20 à 100 Ko compressés par session**, et 1 000 sessions représentent donc de l'ordre de
  **20 à 100 Mo**. C'est un ordre de grandeur à vérifier sur les premières vraies sessions, avant de dimensionner.

### Recommandations pour la base du site

1. **Stocker la trace compressée en un seul blob** par envoi ou par session (colonne `bytea`, ou fichier d'un stockage
   objet), **pas en grosses lignes ni en grosses colonnes jsonb** : un jsonb de 100 Ko par envoi se lit et se compte mal,
   et l'index le grossit. La route valide la trace (`trace.valider`) **avant** de la compresser ; l'export décompresse.
   `payload` des envois `empreinte` et `comportement` : jsonb ou blob compressé, au choix, mais jamais réindexé.
2. **Plafond de sessions gardées** : par exemple 2 000 sessions consenties au total, puis la route répond « complet »
   (comme `plein()` du site public) au lieu de continuer à écrire. Plafond aussi **par jour** (le site public a un
   plafond de sessions par jour) et **par session** (envois et octets).
3. **Rétention** : supprimer **automatiquement le brut** (traces et empreintes) après X jours (30 par exemple), en
   gardant seulement ce qui est dérivé : le verdict de `shadowlab externe analyser` par niveau, les signaux nommés, le
   nombre de pages, la date, le compte masqué. Une tâche planifiée du site fait cette purge ; elle s'ajoute à la
   suppression à la demande de la personne.
4. **Analyser régulièrement** (hebdomadaire par exemple) et ne garder le brut que des sessions utiles : arrêtées à tort
   (humain connu arrêté par un détecteur), ou qui servent de référence. Les sessions banales passées sans signal n'ont
   pas besoin d'être gardées longtemps.
5. **Ne rien ranger de plus** pour « au cas où » : ni en-têtes de la requête d'envoi, ni IP, ni journaux détaillés.

## Ce qui n'est pas vérifié

- Le paquet n'a **jamais tourné dans un vrai navigateur** : seul `releve.js` est joué (sous Node, navigateur factice) ;
  `observateur.js` externe est vérifié par lecture du code, `node --check` et l'absence de nom interdit, pas en situation.
- Le comportement du site cible : sa politique de sécurité, Cloudflare (réécriture de scripts, Rocket Loader qui
  casserait un `type="module"`), Next.js (une seule exécution par chargement complet).
- Les détecteurs sur de **vraies** sessions d'un site de lecture : leurs seuils viennent de nos sites de démonstration.
- L'absence d'`entetes` ne change aucun verdict (vérifié par un test sur l'exemple) ; ce qui change en revanche, c'est
  que `regles-http` n'est jamais jugé.
