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

## État (11/11/2026)
- **Arena opérationnelle** : frontal TLS (JA3/JA4) → Nginx (rate limit) → Coraza WAF + OWASP CRS → site
  FastAPI. **7 niveaux progressifs** (01 baseline → 07 état de l'art, D-49). JS proof-of-work, demo CAPTCHA,
  FingerprintJS 5.3.0, BotD 2.0, 42 détecteurs (dont AudioContext, polices, Math, DOMRect, iframe
  cross-contexte, deep Proxy, corrélation cross-session — D-48, **TLS v2 : 17 règles d'analyse
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
- **Application publique réduite** (`src/shadowlab/public/`, D-55) : la seule partie faite pour être mise en
  ligne. Site vitrine, consentement, collecte fermée, suppression de sa session ; aucune route du labo.
  Lancement et conditions : `docs/site-public.md`. Le labo lui-même ne se met jamais en ligne.
- **Rejeu des sessions humaines** (D-56) : `shadowlab rejeu` refait la décision de chaque niveau sur les
  sessions humaines enregistrées (même code que l'Arena, `gardien.motifs_suspicion`) et donne, par niveau,
  les humains arrêtés et le détecteur responsable. Aucune session humaine en base au 12/11.
- **605 tests rapides verts** (hors intégration), lint propre.
- **Pas encore** : score v3 réel (attend une clé), Turnstile réel sur domaine test + fiabilité de son
  auto-résolution (test keys flaky), moteur expérimental propre, couche IA, test sur serveur Linux réel.

## Niveaux de difficulté Arena
| Niveau | Nom | Protections |
|--------|-----|------------|
| 01 | Baseline | Site nu, aucune protection |
| 02 | Détection simple | User-Agent, cookies, rate limit léger |
| 03 | Fingerprinting | FingerprintJS, BotD, détecteur comportemental, signaux JS |
| 04 | Challenges | JS proof-of-work, CAPTCHA demo, WAF en mode blocage |
| 05 | Protection avancée | Turnstile + reCAPTCHA (test keys), WAF paranoia élevée, TLS binding, login anti-bot |
| 06 | Défense multicouche | Tout combiné, honeypots, corrélation de signaux, adaptation, login anti-bot |

## Commandes vérifiées
```bash
uv sync                                                    # installer le backend
npm --prefix frontend install                              # installer l'interface (une fois)
npm --prefix frontend run build                            # construire l'interface → frontend/dist
uv run shadowlab site                                      # http://127.0.0.1:8770/labo (interface) + /lab/ (site de test)
uv run shadowlab arena demarrer                            # docker compose (Coraza + Nginx)
uv run shadowlab campagne configs/experiments/essai.yaml   # campagne courte
uv run shadowlab campagne configs/experiments/baseline.yaml  # campagne de référence
uv run shadowlab campagne configs/experiments/recaptcha-v3.yaml  # démo reCAPTCHA v3 réel (clés v3 dans .env)
uv run shadowlab campagne configs/experiments/connexion-arena.yaml  # le moteur franchit le login (01/05/06)
uv run shadowlab campagne configs/experiments/extraction-adaptative.yaml  # relocalisation malgré mutation CSS
uv run shadowlab recolter <url> [selecteur] [--similaires] [--json]  # récolte HTTP furtive
uv run shadowlab arreter | reprendre <n°> | rapport <n°> | liste | supprimer <n°>
uv run shadowlab public servir | purger | supprimer <id>  # application publique (docs/site-public.md) ; servir exige SHADOWLAB_PUBLIC_CONTACT
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
│   └── isoles/      # Moteurs en environnement isolé (camoufox, seleniumbase, uc)
├── site/            # Site de test FastAPI (app, pages, vitrine, gardien, static/)
├── campaigns.py     # Exécution matricielle des campagnes
├── scenarios.py     # 15 scénarios de test
├── detection.py     # 39 détecteurs
├── issues.py        # Classification en 6 issues
├── passages.py      # Cycle de vie d'un passage
├── database.py      # SQLite + migrations
├── analytics.py     # Statistiques (Wilson, p95/p99)
├── config.py        # Configuration centrale
├── api.py           # API REST (parcours : /protections, /experiences/.../progression|flux|matrice, /artefacts)
├── cli.py           # Interface ligne de commande
├── reports.py       # Rapports HTML/CSV/JSON
├── rejeu.py         # Rejeu des sessions humaines contre chaque niveau (jalon A)
├── labo.py          # Sert l'interface construite (frontend/dist) sous /labo
├── public/          # Application publique réduite (vitrine + sessions humaines), seule à se mettre en ligne
└── tableau.py       # Ancien tableau de bord (déprécié, remplacé par /labo)
frontend/            # Interface React + TypeScript (Vite), consomme /api
│   ├── src/screens/ # Configurer, Experiences, Suivi, Passage, Comparer, Moteurs, Protections
│   └── src/         # api.ts, stats.ts (Wilson), hooks.ts (SSE), ui.tsx, types.ts
configs/             # Profils Arena + campagnes YAML
docker/              # Coraza WAF + Nginx (Docker Compose)
docs/                # Architecture, décisions, recherche
moteurs_isoles/      # pyproject.toml par environnement isolé
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
- Le navigateur garde les scripts de `/lab/static` en cache une heure : après une modification, vérifier avec
  une adresse neuve (`?v=2`). La racine `/` redirige vers l'ancien tableau de bord `/tableau`.

## Mémoire vivante — à tenir à jour (obligatoire)
Toute IA qui travaille ici met la mémoire à jour au fil de l'eau :
- **En fin de tâche**, une entrée datée dans `notes/ia/journal.md` (ce qui a été fait, fichiers, décisions, reste).
- Questions pour Ethan → `notes/ia/questions-ouvertes.md`.
- `notes/ia/ETAT.md` est **généré** chaque soir — ne pas l'éditer. L'état à la main = `notes/ia/contexte.md`.

Outils (partagés, `~/atelier/cerveau/`) : `cerveau` (graphe 3D + spécialiste RAG), consolidation du soir automatique.
