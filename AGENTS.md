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

## Périmètre (D-15, D-16)
- **Permis** : outils anti-détection, modification d'empreinte, combinaisons de techniques — **contre nos
  propres protections** et sur nos domaines de test autorisés.
- **Maintenu, non négociable** :
  - Destinations locales ou explicitement autorisées seulement, rejet par défaut.
  - Aucun solveur de CAPTCHA (une personne seule valide un CAPTCHA).
  - Aucun contournement écrit sur mesure contre un détecteur commercial ou un service tiers.
  - Aucun résultat de mesure inventé.
  - CAPTCHA providers en mode test (test keys) ≠ victoire contre un vrai CAPTCHA : le distinguer dans les résultats.

## État (03/11/2026)
- **Arena opérationnelle** : frontal TLS (JA3/JA4) → Nginx (rate limit) → Coraza WAF + OWASP CRS → site
  FastAPI. **6 niveaux progressifs** (01 baseline → 06 multicouche, D-18). JS proof-of-work, demo CAPTCHA,
  FingerprintJS 5.3.0, BotD 2.0, 6 détecteurs, honeypots (lien piège + champ piège), fingerprinting actif,
  Turnstile Cloudflare (test keys, niveaux 05-06).
- **11 moteurs** : 7 intégrés (playwright, selenium, scrapling, httpx, curl-cffi, patchright, scrapling-furtif),
  4 isolés à installer (camoufox, seleniumbase, seleniumbase-uc, undetected-chromedriver).
- **Campagnes matricielles** : moteur × protection × scénario × répétitions, exécution parallèle (spawn),
  classification en 6 issues, intervalles de Wilson, mesures CPU/mémoire.
- **Catalogue recherche** : 52 projets open source analysés (`docs/recherche/catalogue.yaml`).
- **57 tests verts**, lint propre.
- **Pas encore** : reCAPTCHA (test keys), Cloudflare sur domaine test, moteur expérimental propre,
  dashboard avancé, environnements isolés opérationnels, couche IA.

## Niveaux de difficulté Arena
| Niveau | Nom | Protections |
|--------|-----|------------|
| 01 | Baseline | Site nu, aucune protection |
| 02 | Détection simple | User-Agent, cookies, rate limit léger |
| 03 | Fingerprinting | FingerprintJS, BotD, détecteur comportemental, signaux JS |
| 04 | Challenges | JS proof-of-work, CAPTCHA demo, WAF en mode blocage |
| 05 | Protection avancée | Turnstile (test keys), WAF paranoia élevée, TLS binding |
| 06 | Défense multicouche | Tout combiné, honeypots, corrélation de signaux, adaptation |

## Commandes vérifiées
```bash
uv sync                                                    # installer
uv run shadowlab site                                      # http://127.0.0.1:8770/tableau
uv run shadowlab arena demarrer                            # docker compose (Coraza + Nginx)
uv run shadowlab campagne configs/experiments/essai.yaml   # campagne courte
uv run shadowlab campagne configs/experiments/baseline.yaml  # campagne de référence
uv run shadowlab arreter | reprendre <n°> | rapport <n°> | liste | supprimer <n°>
uv run shadowlab moteurs etat                              # disponibilité des moteurs
uv run pytest                                              # ~54 tests, ~15 s (navigateurs réels)
uv run pytest -m "not integration"                         # < 1 s
uv run ruff check src tests && uv run ruff format --check src tests
```
Prérequis : Python 3.12, `uv`, Google Chrome (Selenium), Chromium de Playwright (`uv run playwright install chromium`),
OrbStack/Docker (Arena).

## Carte du code
```
src/shadowlab/
├── arena/           # Anti-Bot Arena (frontal TLS, profils, défis, CAPTCHA, pile Docker)
├── engines/         # Moteurs (base.Driver, intégrés, pont pour isolés)
│   └── isoles/      # Moteurs en environnement isolé (camoufox, seleniumbase, uc)
├── site/            # Site de test FastAPI (app, pages, gardien, static/)
├── campaigns.py     # Exécution matricielle des campagnes
├── scenarios.py     # 10 scénarios de test
├── detection.py     # 6 détecteurs
├── issues.py        # Classification en 6 issues
├── passages.py      # Cycle de vie d'un passage
├── database.py      # SQLite + migrations
├── analytics.py     # Statistiques (Wilson, p95/p99)
├── config.py        # Configuration centrale
├── api.py           # API REST
├── cli.py           # Interface ligne de commande
├── reports.py       # Rapports HTML/CSV/JSON
└── tableau.py       # Tableau de bord
configs/             # Profils Arena + campagnes YAML
docker/              # Coraza WAF + Nginx (Docker Compose)
docs/                # Architecture, décisions, recherche
moteurs_isoles/      # pyproject.toml par environnement isolé
```
Décisions : `docs/DECISIONS.md`. Architecture : `docs/architecture.md`.

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

## Mémoire vivante — à tenir à jour (obligatoire)
Toute IA qui travaille ici met la mémoire à jour au fil de l'eau :
- **En fin de tâche**, une entrée datée dans `notes/ia/journal.md` (ce qui a été fait, fichiers, décisions, reste).
- Questions pour Ethan → `notes/ia/questions-ouvertes.md`.
- `notes/ia/ETAT.md` est **généré** chaque soir — ne pas l'éditer. L'état à la main = `notes/ia/contexte.md`.

Outils (partagés, `~/atelier/cerveau/`) : `cerveau` (graphe 3D + spécialiste RAG), consolidation du soir automatique.
