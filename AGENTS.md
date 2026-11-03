# Consignes du projet — NOEZIA ShadowLab

**Source de vérité du projet.** `CLAUDE.md` et `GEMINI.md` ne contiennent que `@AGENTS.md`.

## Ce que c'est
Laboratoire **local** de R&D NOEZIA : compare des moteurs de navigation automatisée (Playwright, Selenium,
Scrapling, httpx) face à des détecteurs anti-bot, sur un site de test servi par la même machine. Mesure
réussite, détection (avec raisons), faux positifs (sessions humaines), durée, CPU, mémoire.

**Périmètre non négociable** (cahier des charges du 03/11/2026) : destinations locales ou explicitement
autorisées seulement, rejet par défaut ; ni résolution de CAPTCHA, ni rotation d'identité, ni modification
d'empreinte pour échapper à un détecteur ; aucun résultat de mesure inventé.

## État (03/11/2026)
- MVP complet : site de test (8 pages), 4 détecteurs, 4 moteurs, campagnes YAML (graine, reprise, arrêt
  d'urgence, plafond mémoire), SQLite avec migrations, statistiques (Wilson, p95/p99), API, tableau de bord,
  rapports HTML/CSV/JSON. 46 tests verts.
- Campagne de référence `browser_baseline` : 4 moteurs × 8 scénarios × 100 répétitions (voir journal).
- Pas encore : Docker Compose, TLS, concurrence, Crawlee / SeleniumBase / Camoufox (phase 6), sessions
  humaines de référence (à faire par Ethan sur `/manuel`).

## Commandes vérifiées
```bash
uv sync                                                    # installer
uv run shadowlab site                                      # http://127.0.0.1:8770/tableau
uv run shadowlab campagne configs/experiments/essai.yaml   # 48 passages, ~30 s
uv run shadowlab campagne configs/experiments/baseline.yaml  # 3 200 passages
uv run shadowlab arreter | reprendre <n°> | rapport <n°> | liste | supprimer <n°>
uv run pytest                                              # 46 tests, ~15 s (navigateurs réels)
uv run pytest -m "not integration"                         # < 1 s
uv run ruff check src tests && uv run ruff format --check src tests
```
Prérequis : Python 3.12, `uv`, Google Chrome (Selenium), Chromium de Playwright (`uv run playwright install chromium`).

## Carte du code
Voir le tableau d'architecture du `README.md` et `docs/architecture.md` (flux d'un passage, périmètre,
mesures, limites). Décisions : `docs/DECISIONS.md`.

## Règles
- Tout nouveau moteur passe par `engines/base.Driver` et respecte le périmètre (`self.verifier(url)` avant
  chaque requête ; verrou réseau pour un navigateur). Un test de redirection hors périmètre est obligatoire
  (`tests/test_integration.py`).
- Configuration standard des moteurs : aucun réglage d'empreinte ou de comportement visant à passer un
  détecteur. Tout réglage imposé est déclaré dans `configuration()` et enregistré avec les résultats.
- Schéma : ajouter une migration à la fin de `database.MIGRATIONS`, ne jamais modifier une migration passée.
- Données de détection affichées par `textContent` dans le tableau de bord (jamais `innerHTML`).
- Ne pas lancer de tests ni de travaux lourds pendant une campagne de mesure : ils faussent CPU et durées.

## Pièges
- Le filtre `route` de Playwright **n'intercepte pas les redirections** : d'où le verrou réseau (D-07).
- Chrome : `--proxy-bypass-list` avec `<-loopback>` envoie aussi le local au mandataire (Selenium échouait).
- Scrapling 0.5 importe `patchright` même pour son client HTTP : extra `scrapling[fetchers]` obligatoire.
- Le site lancé par une campagne garde le code chargé au démarrage : relancer la campagne (ou le site) après
  une modification de l'API.

## Mémoire vivante — à tenir à jour (obligatoire)
Toute IA qui travaille ici met la mémoire à jour au fil de l'eau :
- **En fin de tâche**, une entrée datée dans `notes/ia/journal.md` (ce qui a été fait, fichiers, décisions, reste).
- Questions pour Ethan → `notes/ia/questions-ouvertes.md`.
- `notes/ia/ETAT.md` est **généré** chaque soir — ne pas l'éditer. L'état à la main = `notes/ia/contexte.md`.
- **Basic Memory** (MCP `basic-memory`) = lecture/écriture de cette mémoire : relis le contexte avant de commencer.

Outils (partagés, `~/atelier/cerveau/`) : `cerveau` (graphe 3D + spécialiste RAG), consolidation du soir automatique.
