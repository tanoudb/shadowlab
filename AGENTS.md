# Consignes du projet — NOEZIA ShadowLab

**Source de vérité du projet.** `CLAUDE.md` et `GEMINI.md` ne contiennent que `@AGENTS.md`.

## Ce que c'est
Plateforme de **recherche et développement** sur le scraping, l'automatisation web, le fingerprinting et les
systèmes anti-bot. Conçue pour évoluer sur plusieurs années.

Trois axes :
1. **Arena** — reproduire les mécanismes de protection du Web (WAF, fingerprinting, CAPTCHA, détection
   comportementale, corrélation multicouche) dans un environnement local contrôlé, à difficulté progressive.
2. **Catalogue et moteurs** — étudier l'écosystème open source, intégrer les moteurs existants, puis construire
   progressivement un **moteur expérimental propre**, modulaire, qui combine les meilleures techniques.
3. **Mesure scientifique** — campagnes reproductibles, intervalles de confiance, tests d'ablation, historique,
   dashboard complet.

À terme : couche IA pour planifier les campagnes, analyser les résultats, proposer des hypothèses et
recommander des optimisations.

## Périmètre (révisé D-30, phase interne — révise D-15)
- **Permis** : outils anti-détection, modification d'empreinte, combinaisons de techniques — moteur
  universel, capable de franchir n'importe quel détecteur et n'importe quel login.
- **Phase interne / expérimentale (actuelle)** :
  - **Périmètre illimité par défaut** : `SHADOWLAB_HOTES_AUTORISES=*` (défaut). Le rejet-par-défaut
    reste **débrayable** (liste explicite d'hôtes) — le durcissement final est différé, voir
    [`docs/securite-a-finaliser.md`](docs/securite-a-finaliser.md). **Non responsable de l'usage ;
    en interne on ne pointe que nos propres cibles.**
  - Contournement d'un détecteur commercial : **autorisé sur cibles autorisées** (notre Arena, un
    périmètre de bug bounty, un système qu'on possède) **+ divulgation coordonnée** au fournisseur.
    Pas d'exploit sur la prod d'un tiers sans autorisation.
- **Maintenu, non négociable** :
  - **Aucun solveur de CAPTCHA réel** (reCAPTCHA / hCaptcha / Turnstile de production). Le CAPTCHA
    démo de l'Arena (fixture maison) et les flux en test keys restent permis ; le but du moteur est
    de **ne pas déclencher** le CAPTCHA, pas de le résoudre à la place d'un humain.
  - Aucun résultat de mesure inventé.
  - CAPTCHA providers en mode test (test keys) ≠ victoire contre un vrai CAPTCHA : le distinguer dans les résultats.

## État (14/11/2026)
- **Arena opérationnelle** : frontal TLS (JA3/JA4) → Nginx (rate limit) → Coraza WAF + OWASP CRS → site
  FastAPI. **7 niveaux progressifs** (01 baseline → 07 état de l'art, D-49). JS proof-of-work, demo CAPTCHA,
  FingerprintJS 5.3.0, BotD 2.0, 42 détecteurs (dont AudioContext, polices, Math, DOMRect, iframe
  cross-contexte, deep Proxy, corrélation cross-session — D-48 puis D-64, en 1.1 ; `headless`, `chrome-apis`,
  `polices` et `connection-dynamic` en 1.1 — D-66, **TLS v2 : 17 règles d'analyse
  ClientHello** — D-52, **HTTP/2 fingerprinting : 11 règles SETTINGS/WU** — D-53), honeypots (lien piège + champ piège),
  fingerprinting actif, Turnstile Cloudflare (test keys, niveaux 05-07), reCAPTCHA v2 Google (test keys,
  niveaux 05-07). Score composite pondéré par famille (D-47).
- **Niveau authentifié** (05-07) : login `/lab/connexion` gardé par une porte comportementale
  (empreinte + comportement + honeypot + limite de tentatives), espace privé `/lab/espace`, comptes de
  test locaux. Scénario `connexion` (le moteur franchit le login).
- **Démo reCAPTCHA v3 RÉEL** : `/lab/recaptcha-v3` charge le vrai v3 et relève le score attribué au
  moteur (clés dans `.env`, secret jamais exposé). Passer = être perçu comme humain (v3 ne fait que noter).
- **Moteur NOEZIA** : GPU Metal réel sur macOS, masquage SwiftShader sur Linux sans GPU (D-50),
  8 profils GPU Linux (Intel/NVIDIA/AMD — D-51), profils cohérents avec l'OS hôte.
- **Dashboard avancé** : vue Arena (décisions par couche, matrice moteur × protection, durées).
- **15 moteurs** : 9 intégrés (playwright, selenium, scrapling, httpx, curl-cffi, patchright, scrapling-furtif,
  noezia, noezia-experimental), 6 isolés opérationnels (camoufox, seleniumbase, seleniumbase-uc,
  undetected-chromedriver, crawlee, zendriver).
- **Campagnes matricielles** : moteur × protection × scénario × répétitions, exécution parallèle (spawn),
  classification en 6 issues, intervalles de Wilson, mesures CPU/mémoire.
- **Chiffres de détection** : voir `docs/PLAN.md` § 2 ; ils ne sont pas validés sur des humains (aucune session humaine en base au 12/11).
- **Catalogue recherche** : 52 projets open source analysés (`docs/recherche/catalogue.yaml`).
- **Périmètre** : illimité par défaut en phase interne (D-30, débrayable — `docs/securite-a-finaliser.md`).
- **Extraction adaptative** : `Analyseur` fetcher-agnostique avec `Element` (navigation DOM complète),
  `similaires()` (auto-match de liste façon Scrapling), `extraire_adaptatif()` (relocalisation par
  signature si le sélecteur casse). Page `/lab/adaptatif` (classes CSS mutées). CLI `shadowlab recolter`.
- **Site vitrine à contenu connu** : `/lab/vitrine` (annonces immobilières fictives générées à partir
  d'une graine, liste paginée, fiches, photos SVG, bloc chargé en JavaScript). `vitrine.verite()` donne
  le contenu exact attendu d'une récolte. Réglages `SHADOWLAB_VITRINE_GRAINE` et `SHADOWLAB_VITRINE_TAILLE`.
- **Récolte notée** : scénario `recolte_vitrine` (toute la liste puis chaque fiche) et `notation.noter_recolte`
  (complétude, exactitude). Campagne : `SHADOWLAB_VITRINE_TAILLE=40 uv run shadowlab campagne
  configs/experiments/recolte-palier1.yaml` (environ 2 h).
- **Application publique** (`src/shadowlab/public/`, D-55 ; refaite le 14/11, D-75 à D-77) : la seule partie faite
  pour être mise en ligne ; aucune route du labo. C'est le site d'étude « Humain ou robot ? », en français et en
  anglais (langue par l'adresse `/fr`, `/en`, puis la session, puis le navigateur ; trois cookies, pas un de plus) :
  accueil avec l'accord, notice complète (`/fr|en/information`), « Ma session », suppression, contact (D-57).
  Site de démonstration vedette : **Mosaïk Démo**, un faux réseau social de photos sous `/lab/social/…`
  (`public/social.py` : fil paginé, publication, profil, étiquette, explorer, crédits ; de vraies pages courtes ;
  aucune écriture venant du visiteur, le texte tapé ne quitte jamais la page). 93 photos de Wikimedia Commons
  sous licence libre ou dans le domaine public (`public/static/social/photos/manifeste.json`), créditées sous
  chaque publication, sur l'accueil et sur la page de crédits. Second site, discret : les annonces
  (`/lab/vitrine/…`). **Relevé** pendant une session seulement : l'observateur du labo (inchangé) et un second
  script propre au site public, `public/static/releve.js` (envoi `trace`, validé par `public/trace.py` :
  trajectoire de la souris, clics, défilement, rythme du clavier, tactile ; jamais une touche ni un texte).
  **Fréquentation** : un compte par jour (accueil, sessions commencées, terminées), `shadowlab public
  frequentation` ; `shadowlab public sessions` liste les sessions par taille. Plafond réglable
  `SHADOWLAB_PUBLIC_SESSIONS_PAR_JOUR` (40 par défaut). Quatre relectures indépendantes (D-65, D-67, D-77) ; la
  quatrième a trouvé 15 défauts, tous corrigés. **En ligne depuis le 14/11 à 11 h 06 par le tunnel rapide**, lancé par l'assistant à la demande d'Ethan : adresse
  temporaire dans `outputs/public/adresse-publique.txt`, plafond réglé à 150 sessions par jour ; le site s'arrête
  avec le tunnel, la session qui l'a lancé ou le Mac. **Accueil court** (D-80, 14/11) : une phrase, un seul bouton
  « J'accepte et je commence » (plus de case à cocher), « 2 minutes », détail replié, menu du haut réduit à la marque
  et à la langue. **Le site ne cite jamais le projet ni le laboratoire** (D-81), script d'observation compris :
  copie dérivée par `public/script_public.py`, garde `tests/test_public_sans_marque.py`. Avant une annonce publique, à la charge
  d'Ethan : un nom d'hôte stable (tunnel nommé sur un domaine, pas le tunnel rapide), une règle de limitation de
  débit chez Cloudflare, le plafond de sessions réglé ; liste dans `docs/site-public.md` (« Avant d'annoncer le
  site publiquement »). Non essayé : Safari, iPhone, Firefox. Vrai tunnel
  vérifié le 14/11 (pages identiques à la version locale, photos non gardées en cache par Cloudflare, aucune
  adresse IP ni en-tête de Cloudflare en base, session d'essai commencée puis supprimée). Les pages du labo n'ont pas changé
  d'un octet (`tests/test_labo_inchange.py`). Cadrage : `docs/recherche/site-public-communaute-2026-11-13.md`.
  Le labo lui-même ne se met jamais en ligne.
- **Arena, D-78 (14/11)** : une photo chargée par une page n'est plus comptée comme une page par les détecteurs
  (`detection.RESSOURCES_DE_PAGE`, `Observations.documents`) ; les photos restent contrôlées par le gardien, les
  appels de données restent des pages. Avant : 1 passage sur 35 bloqué à tort au niveau 04 (campagne 109), et un
  humain arrêté aux niveaux 06 et 07 sur le site public. Campagne 110 (non-régression) : navigateur 15 sur 15,
  témoin `http` 0 sur 15.
- **Moteur, première page après un défi** (D-79, 14/11) : la page obtenue après un défi reçoit l'interaction
  humaine (`moteur.py`, `navigate` et `click`). Avant, la récolte quittait la première vraie page en 54 à 71 ms
  sans un geste (campagne 110, niveaux 05 et 06 sans corrélation). Campagne 111 (même fichier) : 6,2 à 10,5 s
  avec souris et défilement, navigateur 15 sur 15, témoin `http` 0 sur 15. Aucun détecteur de l'Arena ne voyait
  ce défaut : aucun taux ne change. `pages_eclair` fait toujours la moyenne avec les pages de défi.
- **Arena, D-82 (14/11)** : la durée des cookies de réussite d'un défi est un réglage du profil (`duree_cookie_s`,
  3 600 s par défaut). Profils de mesure à 600 s : `04court`, `05court`, `06scorrcourt`
  (`configs/arena/profils-cookie-court.yaml`, à passer par `SHADOWLAB_PROFILS_EXTRA`). Aucune campagne encore.
- **Rejeu des sessions humaines** (D-56) : `shadowlab rejeu` refait la décision de chaque niveau sur les
  sessions humaines enregistrées (même code que l'Arena, `gardien.motifs_suspicion`) et donne, par niveau,
  les humains arrêtés et le détecteur responsable. Aucune session humaine en base au 12/11.
- **1 640 tests verts** (`uv run pytest`, 14/11 à 10 h 12, après D-79, hors campagne : 1 596 rapides et 44
  d'intégration avec de vrais navigateurs et la pile Docker), 11 tests de
  l'interface (vitest), lint propre. Depuis, suite rapide seule : 1 650 verts le 14/11 à 11 h 30 (après D-80 à D-82) ;
  les 44 tests d'intégration ne sont pas relancés. Branche `niveau-authentifie-perimetre` (dernière fusion `f374e4e`), rien sur
  `master`. Base au schéma 9 (D-68).
- **Moteur, souris** (D-74, 13/11) : la trajectoire garde un tremblement visible au pixel, après deux blocages au
  niveau 05 sur le signal `trajectoire_lineaire` (campagne 108). Banc de mesure sans navigateur :
  `tests/test_souris_trajectoire.py`. Vérifié dans un vrai Chrome par la campagne 109 (14/11, même fichier que
  la 108) : 0 page sur 2 015 sous la marge de 0,15 rad (30 sur 1 997 avant), niveau 05 à 35 sur 35 (32 avant),
  niveaux 04 et 06 sans corrélation à 34 et 35 sur 35 ; le seul échec est le défaut de l'Arena ci-dessous.
- **Campagne 97** (identité réécrite ou native, 525 passages, 0 panne, `docs/PLAN.md` § 2) : `noezia` tel
  qu'il est fait 15, 10, 10, 10, 0, 0, 0 sur 15 aux niveaux 01 à 07 (06 et 07 sans corrélation), avec une seule
  cause d'échec, le signal `headless_dans_une_requete`. `noezia` en identité native (`headless: false`,
  `channel: chrome`, `identite_native: true`) et un vrai Chrome seul font 15 sur 15 aux niveaux 01 à 03, puis
  0 sur 15 du 04 au 07, à cause de quatre règles corrigées depuis (D-66). Les deux témoins sont arrêtés dès
  le niveau 02.
- **Campagne 98** (contrôle de D-66, 135 passages, 0 panne, `docs/PLAN.md` § 2) : `noezia` en identité native fait
  15 sur 15 aux niveaux 04, 05 et 06 sans corrélation, donc aux six niveaux de l'objectif avec la 97 ; le même Chrome
  sans le comportement de noezia fait 10, 5 et 0 (`aucune_interaction`), le témoin 0 sur 45.
  Réserves : 15 passages par niveau (30 exigés), CAPTCHA en clés de test aux niveaux 05 et 06, niveau 06 sans corrélation,
  aucun humain en base, un seul Chrome sur macOS.
- **Campagnes 100 et 101** (12/11, `docs/PLAN.md` § 2) : `noezia` en identité native, 30 passages par niveau
  de 01 à 06 sans corrélation, 179 sur 180 (06 : 29 sur 30, le seul échec est un blocage du WAF corrigé par D-69).
  Taux observé ≥ 90 % à chaque niveau, mais borne basse de Wilson sous 90 % (88,6 % à 30 sur 30). Réserves :
  CAPTCHA en clés de test aux niveaux 05 et 06, niveau 06 complet à 0 sur 15 (corrélation entre sessions,
  campagne 101), aucun humain en base, une machine, un Chrome sur macOS, pas de témoin, rien contre une
  protection réelle ; l'identité native n'est pas le réglage par défaut. Le produit n'est pas atteint.
- **Récolte générale** (D-70, fusionnée le 12/11 dans cette branche, commit `b1a40ed`, rien sur `master`) :
  `shadowlab recolte lancer | reprendre | etat | essayer | noter`. Une **recette** YAML par site
  (`configs/recettes/`), un parcours avec état SQLite et reprise, `robots.txt` respecté, rythme, sentinelle
  (arrêt au premier signe d'alerte), deux moteurs (`http`, `navigateur` = vrai Chrome en identité native),
  export JSON Lines et CSV pour Excel France, notation (pages, enregistrements, champs), récolte incrémentale.
  Second site factice à contenu connu : `/lab/rallye`. Guide : `docs/recolte.md`.
  Mesuré (moteur `http`, site du labo) : vitrine à 500 annonces, 525 pages, 7 000 champs sur 7 000, 0,8 s ;
  rallye, 427 pages, 34 410 champs sur 34 410. Moteur `navigateur`, niveau 01 : vitrine à 45 annonces, 48
  pages sur 48 en 5 min 50 s. Campagne 102 (`recolte-generale.yaml`, les deux moteurs, les deux sites factices,
  niveau 01, 3 répétitions) : 12 passages sur 12, pages, enregistrements et champs à 100 % ; en navigateur,
  environ 7 s par page (427 pages de rallye en 48 à 51 minutes). 1 247 tests verts après la fusion.
  **Par l'Arena** (scénario `recolte_recette_vitrine`, `configs/experiments/recolte-arena.yaml`, vitrine à 20
  annonces) : campagnes 103 et 104, 0 sur 3 aux niveaux 04 à 06, deux défauts corrigés (D-71 : la limite de
  débit comptait les photos d'une page ; D-72 : la porte d'entrée ne voyait pas un défi déjà franchi pendant
  la lecture) ; campagne 105 (13/11) : le moteur navigateur fait 15 passages sur 15 du niveau 02 au niveau 06
  sans corrélation, 21 pages et 280 champs sur 280 à chacun, aucun blocage ; le témoin `http` 0 sur 15.
  Réserves : 3 passages par niveau, 21 pages par passage, CAPTCHA en clés de test aux niveaux 05 et 06, niveau
  06 sans corrélation, niveau 07 non mesuré, aucun humain en base.
  **Parcours long par l'Arena** (scénario `recolte_recette_rallye`, `recolte-arena-rallye.yaml`, 427 pages dans
  une seule session, environ 50 minutes) : campagne 106, réussi aux niveaux 04 et 05, arrêté à la 10ᵉ page au
  niveau 06 sans corrélation (l'Arena redemandait le défi quand Chrome reprenait sa session TLS : D-73) ;
  campagne 107 (13/11) : 427 pages et 34 410 champs sur 34 410 aux niveaux 04, 05 et 06 sans corrélation, un
  passage par niveau. Le cookie de défi de l'Arena vit une heure : une passe plus longue sera redéfiée et
  arrêtée par la sentinelle (arrêt puis `reprendre`, jamais mesuré).
  **Non prouvé** : aucun vrai site ni vraie protection ; la commande elle-même vise le site en direct (niveau
  01), les niveaux protégés ne sont mesurés que par campagne ; une passe de plus d'une heure sous
  protection ; coupure d'une redirection vers un autre hôte non vérifiée dans un vrai Chrome ; `attendre` non
  branché ; champ adaptatif sans signature mémorisée muet ; rythme « prudent » jamais tourné en temps réel ;
  CSV jamais ouvert dans Excel.
- **Pas encore** : score v3 réel (attend une clé), Turnstile réel sur domaine test + fiabilité de son
  auto-résolution (test keys flaky), produit NOEZIA v1 visé (`docs/PLAN.md` § 1 ; le paquet `engines/noezia/` existe mais le produit n'est pas atteint), couche IA, test sur serveur Linux réel, récolte d'un vrai site (aucune
  n'a été faite), récolte par l'Arena à 30 passages par niveau (3 à la campagne 105, 1 par niveau pour les
  427 pages de la campagne 107), identité qui dure (palier 2, conception
  `docs/recherche/identite-qui-dure-2026-11-12.md` à valider par Ethan).

## Niveaux de difficulté Arena
| Niveau | Nom | Protections |
|--------|-----|------------|
| 01 | Baseline | Site nu, aucune protection |
| 02 | Détection simple | Blocage sur signaux HTTP (détecteurs `regles-http`, `tls`), limite de fréquence (20 requêtes/s) |
| 03 | Fingerprinting | 12 détecteurs (BotD, signaux JS, comportement, prototypes, headless, APIs Chrome…), seuil composite 1,5, WAF en détection |
| 04 | Challenges | 26 détecteurs, JS proof-of-work (difficulté 12), CAPTCHA démo, WAF en blocage |
| 05 | Protection avancée | 35 détecteurs, PoW lié au TLS (difficulté 15), Turnstile + reCAPTCHA v2 (test keys), WAF paranoia 2, login anti-bot |
| 06 | Défense multicouche | 41 détecteurs dont corrélation cross-session, honeypots, WAF paranoia 3, PoW difficulté 18, login anti-bot |
| 07 | État de l'art | Mêmes détecteurs que 06, seuil composite minimal (0,3), WAF paranoia 4, PoW difficulté 20, limite 1 requête/s, login limité à 2 tentatives |

Source exacte : `configs/arena/profils.yaml` (`shadowlab arena appliquer` régénère Nginx et Coraza à partir de lui).

## Commandes vérifiées
```bash
uv sync                                                    # installer le backend
npm --prefix frontend install                              # installer l'interface (une fois)
npm --prefix frontend run build                            # construire l'interface → frontend/dist
uv run shadowlab site                                      # http://127.0.0.1:8770/labo (interface) + /lab/ (site de test)
uv run shadowlab arena demarrer                            # docker compose (Coraza + Nginx)
SHADOWLAB_PROFILS_EXTRA=configs/arena/profils-sans-correlation.yaml uv run shadowlab arena appliquer   # avant une campagne sans corrélation (niveaux 06 et 07) ; relancer ensuite sans la variable
SHADOWLAB_PROFILS_EXTRA=configs/arena/profils-sans-correlation.yaml uv run shadowlab campagne configs/experiments/ablation-interface.yaml  # identité réécrite ou native (campagne 97, 525 passages)
SHADOWLAB_PROFILS_EXTRA=configs/arena/profils-sans-correlation.yaml uv run shadowlab campagne configs/experiments/controle-vrai-chrome.yaml  # contrôle de D-66, niveaux 04 à 06 (135 passages)
uv run shadowlab campagne configs/experiments/essai.yaml   # campagne courte
uv run shadowlab campagne configs/experiments/baseline.yaml  # campagne de référence
uv run shadowlab campagne configs/experiments/recaptcha-v3.yaml  # démo reCAPTCHA v3 réel (clés v3 dans .env)
uv run shadowlab campagne configs/experiments/connexion-arena.yaml  # le moteur franchit le login (01/05/06)
uv run shadowlab campagne configs/experiments/extraction-adaptative.yaml  # relocalisation malgré mutation CSS
uv run shadowlab recolter <url> [selecteur] [--similaires] [--json]  # récolte HTTP furtive
uv run shadowlab recolte lancer configs/recettes/vitrine.yaml   # récolte générale d'un site (recette) ; `--moteur navigateur` pour Chrome
uv run shadowlab recolte noter vitrine-annonces --verite vitrine   # note contre la vérité du site factice (`rallye` pour l'autre)
uv run shadowlab recolte etat <nom> | reprendre <nom> | essayer <recette> <adresse>   # voir, reprendre, tester une recette sur une page
SHADOWLAB_VITRINE_TAILLE=150 SHADOWLAB_RALLYE_TAILLE=24 uv run shadowlab campagne configs/experiments/recolte-generale.yaml  # preuve (~3 h 30) ; recolte-generale-essai.yaml d'abord
SHADOWLAB_PROFILS_EXTRA=configs/arena/profils-sans-correlation.yaml SHADOWLAB_VITRINE_TAILLE=20 uv run shadowlab campagne configs/experiments/recolte-arena.yaml  # la récolte jugée par les niveaux 02 à 06 sans corrélation (campagne 105, 40 min) ; `arena appliquer` avec la variable avant, sans elle après
SHADOWLAB_PROFILS_EXTRA=configs/arena/profils-sans-correlation.yaml SHADOWLAB_RALLYE_TAILLE=24 uv run shadowlab campagne configs/experiments/recolte-arena-rallye.yaml  # 427 pages d'une seule session aux niveaux 04 à 06 sans corrélation (campagne 107, 2 h 35) ; même encadrement par `arena appliquer`
uv run shadowlab arreter | reprendre <n°> | rapport <n°> | liste | supprimer <n°>
uv run shadowlab public servir | purger | supprimer <id> | messages | effacer-message <n°>  # application publique (docs/site-public.md) ; servir exige SHADOWLAB_PUBLIC_CONTACT
uv run shadowlab public frequentation | sessions            # visites et sessions par jour ; sessions par taille (repérer un abus)
scripts/site-public-tunnel.sh                              # site public en ligne par tunnel Cloudflare (lancé par Ethan, exige SHADOWLAB_PUBLIC_CONTACT ; docs/site-public.md)
uv run shadowlab rejeu [--base <base publique>] [--json]   # humains arrêtés par niveau (sessions de /manuel, ou du site public avec --base)
uv run shadowlab moteurs etat                              # disponibilité des moteurs
uv run pytest                                              # tests Python (navigateurs réels + e2e UI)
uv run pytest -m "not integration"                         # < 3 s, sans navigateur
uv run ruff check src tests && uv run ruff format --check src tests
npm --prefix frontend test                                 # tests front (vitest)
npm --prefix frontend run dev                              # dev UI : http://localhost:5173/labo (proxy /api → 8770)
```
Prérequis : Python 3.12, `uv`, Node 22 (`mise`), Google Chrome (Selenium), Chromium de Playwright
(`uv run playwright install chromium`), OrbStack/Docker (Arena). L'interface doit être construite
(`npm --prefix frontend run build`) pour que `shadowlab site` la serve sous `/labo` ; sinon, mode dev.

## Carte du code
```
src/shadowlab/
├── arena/           # Anti-Bot Arena (frontal TLS, profils, défis, CAPTCHA, pile Docker)
├── engines/         # Moteurs (base.Driver, intégrés, pont pour isolés)
│   ├── isoles/      # Moteurs en environnement isolé (camoufox, seleniumbase, uc, crawlee, zendriver)
│   └── noezia/      # Le moteur étudié : moteur, profils, furtivité, comportement, défis, récolte ; récolte générale :
│                    #   recettes, parcours, etat, robots, rythme, sentinelle, navigateur, export
├── site/            # Site de test FastAPI (app, pages, vitrine, rallye, gardien, static/)
├── campaigns.py     # Exécution matricielle des campagnes
├── scenarios.py     # 19 scénarios de test (dont recolte_recette_vitrine et recolte_recette_rallye)
├── commande_recolte.py  # `shadowlab recolte` : lancer, reprendre, etat, essayer, noter (D-70)
├── detection.py     # 42 détecteurs
├── issues.py        # Classification en 6 issues
├── correlation.py   # Corrélation cross-session : recyclage d'empreintes entre sessions
├── scoring.py       # Score composite pondéré par famille de détecteur
├── notation.py      # Notation d'une récolte (complétude, exactitude) contre la vérité de la vitrine
├── diagnostic.py    # Diagnostic par signal, ablation, comparaison des configurations moteurs
├── perimetre.py     # Destinations joignables par les moteurs (mode strict ou illimité)
├── mesures.py       # CPU et mémoire de l'arbre de processus du lanceur
├── journal.py       # Journaux JSON (outputs/logs/shadowlab.jsonl)
├── passages.py      # Cycle de vie d'un passage
├── database.py      # SQLite + migrations
├── analytics.py     # Statistiques (Wilson, p95/p99)
├── config.py        # Configuration centrale
├── api.py           # API REST (parcours : /protections, /experiences/.../progression|flux|matrice, /artefacts)
├── cli.py           # Interface ligne de commande
├── reports.py       # Rapports HTML/CSV/JSON
├── rejeu.py         # Rejeu des sessions humaines contre chaque niveau (jalon A)
├── labo.py          # Sert l'interface construite (frontend/dist) sous /labo
├── public/          # Application publique : étude « Humain ou robot ? », réseau social fictif (social.py), relevé (trace.py,
│                    #   static/releve.js), textes des deux langues (textes.py) ; seule à se mettre en ligne
└── tableau.py       # Ancien tableau de bord (déprécié, remplacé par /labo)
frontend/            # Interface React + TypeScript (Vite), consomme /api
│   ├── src/screens/ # Configurer, Experiences, Suivi, Passage, Comparer, Moteurs, Protections
│   └── src/         # api.ts, stats.ts (Wilson), hooks.ts (SSE), ui.tsx, types.ts
configs/             # Profils Arena + campagnes YAML ; recettes/ = une recette de récolte par site (vitrine, rallye-demo)
docker/              # Coraza WAF + Nginx (Docker Compose)
docs/                # Architecture, décisions, recherche ; recolte.md = guide de la commande de récolte
moteurs_isoles/      # pyproject.toml par environnement isolé
scripts/             # site-public-tunnel.sh (site public en ligne par tunnel Cloudflare)
tests/               # tests Python (pytest)
```
**Plan de travail unique : `docs/PLAN.md`** (objectif, état mesuré, étapes, règles) — à lire avant de coder.
Décisions : `docs/DECISIONS.md`. Architecture : `docs/architecture.md`.
Interface : front séparé dans `frontend/` (parcours Configurer → Lancer → Suivre → Comprendre → Comparer),
servi par `labo.py` sous `/labo` ; le backend reste la seule source de vérité via `/api`.

## Règles
- Tout nouveau moteur passe par `engines/base.Driver` et respecte le périmètre (`self.verifier(url)` avant
  chaque requête ; verrou réseau pour un navigateur). Un test de redirection hors périmètre est obligatoire
  (`tests/test_integration.py`).
- Chaque moteur est testé d'abord dans sa configuration par défaut. Une option d'empreinte n'existe que si
  l'outil la documente, et elle est déclarée dans `options_permises`. Tout réglage imposé est déclaré dans
  `configuration()` et enregistré avec les résultats.
- Options de moteur : seulement celles déclarées dans `options_permises` (liste blanche typée) ; les réglages
  imposés par le périmètre s'appliquent **après** les options, pour qu'aucune ne puisse les écraser.
- Schéma : ajouter une migration à la fin de `database.MIGRATIONS`, ne jamais modifier une migration passée.
- Données de détection affichées par `textContent` dans le tableau de bord (jamais `innerHTML`).
- Ne pas lancer de tests ni de travaux lourds pendant une campagne de mesure : ils faussent CPU et durées.
- Récolte générale (D-70) : une recette qui vise un site qui n'est pas à nous porte une ligne `autorisation`
  (D-30) ; `robots.txt` est respecté par défaut ; aucune redirection vers un autre hôte n'est suivie ; la
  commande ne clique jamais sur un défi d'un site tiers et n'a aucun solveur de CAPTCHA. Une valeur douteuse
  donne une valeur vide et une alerte, jamais une valeur fausse en silence.
- CAPTCHA provider en test keys → résultat étiqueté `captcha_test`, jamais confondu avec un vrai contournement.

## Pièges
- Le filtre `route` de Playwright **n'intercepte pas les redirections** : d'où le verrou réseau (D-07).
- Chrome : `--proxy-bypass-list` avec `<-loopback>` envoie aussi le local au mandataire (Selenium échouait).
- Scrapling 0.5 importe `patchright` même pour son client HTTP : extra `scrapling[fetchers]` obligatoire.
- Le site lancé par une campagne garde le code chargé au démarrage : relancer la campagne (ou le site) après
  une modification de l'API.
- Camoufox exige playwright<1.63, SeleniumBase épingle pytest==9.1.1 : d'où les environnements isolés (D-17).
- Une ablation passe par des profils supplémentaires (`SHADOWLAB_PROFILS_EXTRA`, exemple
  `configs/experiments/ablation-cdp.yaml`) : `shadowlab arena appliquer` avec la variable avant la campagne,
  puis `shadowlab arena appliquer` sans elle après, sinon Nginx garde les profils supplémentaires.
- Un vrai Chrome n'a pas un JA4 unique : quand il reprend sa session TLS, son ClientHello porte l'extension
  `pre_shared_key` en plus (`t13d1517h2_…` devient `t13d1518h2_…`). Tout ce qui lie quelque chose au TLS doit
  passer par l'empreinte de liaison (`tls.ja4_liaison`, D-73), pas par le JA4 exact.
- Le navigateur garde les scripts de `/lab/static` en cache une heure : après une modification, vérifier avec
  une adresse neuve (`?v=2`). La racine `/` redirige vers l'ancien tableau de bord `/tableau`.

## Mémoire vivante — à tenir à jour (obligatoire)
Toute IA qui travaille ici met la mémoire à jour au fil de l'eau :
- **En fin de tâche**, une entrée datée dans `notes/ia/journal.md` (ce qui a été fait, fichiers, décisions, reste).
- Questions pour Ethan → `notes/ia/questions-ouvertes.md`.
- `notes/ia/ETAT.md` est **généré** chaque soir — ne pas l'éditer. L'état à la main = `notes/ia/contexte.md`.

Outils (partagés, `~/atelier/cerveau/`) : `cerveau` (graphe 3D + spécialiste RAG), consolidation du soir automatique.
