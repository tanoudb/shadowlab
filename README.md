# NOEZIA ShadowLab

Laboratoire **local** qui compare des moteurs de navigation automatisée et de collecte (Playwright, Selenium,
Scrapling, httpx) face à des détecteurs anti-bot, sur un site de test qui tourne sur la même machine.

Il répond à des questions mesurées : que voit un site quand un navigateur le visite, en quoi un navigateur
piloté diffère d'un navigateur manuel, quels signaux trahissent l'automatisation, comment plusieurs détecteurs
classent les mêmes sessions, et ce que coûte chaque moteur en temps, CPU et mémoire.

**Périmètre.** Tout se passe en local : les destinations externes sont refusées par défaut, redirections
comprises. Le laboratoire n'intègre ni résolution de CAPTCHA, ni rotation d'identité, ni modification
d'empreinte. Un score obtenu ici ne prédit pas le comportement d'un service de détection externe.

## Installer

Prérequis : macOS ou Linux, Python 3.12, [uv](https://docs.astral.sh/uv/), Google Chrome (pour Selenium).

```bash
uv sync                              # dépendances (versions figées dans uv.lock)
uv run playwright install chromium   # navigateur de Playwright (déjà présent sur le Mac d'Ethan)
```

Selenium Manager télécharge tout seul le `chromedriver` qui correspond au Chrome installé.

## Lancer

```bash
uv run shadowlab site                                   # site de test, API et tableau de bord
uv run shadowlab campagne configs/experiments/essai.yaml   # campagne courte (48 passages, ~30 s)
uv run shadowlab campagne configs/experiments/baseline.yaml  # référence : 3 200 passages
```

- Tableau de bord : <http://127.0.0.1:8770/tableau>
- Site de test : <http://127.0.0.1:8770/lab/>
- Session humaine de référence (pour mesurer les faux positifs) : <http://127.0.0.1:8770/manuel>
- Documentation de l'API : <http://127.0.0.1:8770/api/docs>

Une campagne démarre elle-même le site dans un processus à part s'il ne tourne pas déjà. Les rapports
(HTML, CSV, JSON) sont écrits dans `outputs/rapports/<n°>/`.

### Autres commandes

| Commande | Effet |
|---|---|
| `uv run shadowlab valider <fichier.yaml>` | Vérifie une campagne sans la lancer |
| `uv run shadowlab arreter` | Arrêt d'urgence : la campagne s'arrête après le passage en cours |
| `uv run shadowlab reprendre <n°>` | Reprend une campagne interrompue (les passages faits sont gardés) |
| `uv run shadowlab rapport <n°>` | Régénère les exports d'une expérience |
| `uv run shadowlab liste` | Liste les expériences |
| `uv run shadowlab supprimer <n°>` | Supprime une expérience, ses observations et ses captures |
| `uv run pytest` | Tous les tests (54, dont 5 réels avec navigateurs, ~15 s) |
| `uv run pytest -m "not integration"` | Tests rapides seulement (< 1 s) |
| `uv run ruff check src tests` | Lint |

## Écrire une campagne

```yaml
experiment:
  name: browser_baseline            # minuscules, chiffres, - et _
  description: Référence
  environment: local                # seule valeur acceptée
  engines:
    - playwright
    - {name: playwright, label: playwright-visible, options: {headless: false}}
    - scrapling
  scenarios: [static_html, javascript_content, pagination, form_interaction,
              session_cookies, fingerprint_observation, detection_page, api_json]
  repetitions: 100
  seed: 20261103                    # facultatif : tirée au hasard et enregistrée sinon
  detectors: [botd, regles-http]    # facultatif : tous par défaut
  output: [json, csv, html]
```

Le fichier est validé strictement : moteur, scénario, détecteur ou métrique inconnus, champ en trop, URL hors
périmètre, option de moteur non prévue et alias YAML (`*nom`) sont refusés avant tout lancement.

| Moteur | Options permises |
|---|---|
| `playwright` | `headless`, `trace` (booléens), `channel` (texte) |
| `selenium` | `headless` |
| `scrapling`, `httpx` | `timeout` (secondes) |

## Ce qui est mesuré

| Élément | Contenu |
|---|---|
| **Moteurs** | `playwright` (Chromium sans tête), `selenium` (Chrome installé, sans tête), `scrapling` (client HTTP `FetcherSession`, curl_cffi), `httpx` (client HTTP brut, témoin) |
| **Scénarios** | HTML statique, contenu JavaScript, pagination sur 5 pages, formulaire, cookie de session, relevé d'empreinte, page de verdict, API JSON — chacun avec un résultat attendu vérifié |
| **Détecteurs** | `botd` (BotD 2.0.0 de FingerprintJS, MIT), `regles-http` (en-têtes), `regles-js` (propriétés du navigateur), `coherence` (HTTP contre JavaScript). Chaque verdict garde ses raisons. |
| **Observations** | En-têtes HTTP dans l'ordre reçu, version HTTP, cookies renvoyés, propriétés JavaScript (navigateur, écran, fuseau, WebGL, canvas, permissions, API), comportement (évènements, temps sur la page). TLS : `not_collected` (site servi en HTTP). |
| **Statistiques** | Taux de réussite, de détection, de faux négatifs et d'abstention avec intervalles de confiance de Wilson à 95 % ; faux positifs, précision, rappel et F1 dès qu'il existe des sessions humaines ; médiane, p95, p99 des durées ; temps CPU, mémoire, requêtes |

## Architecture

```
src/shadowlab/
├── cli.py            ligne de commande
├── config.py         réglages (variables SHADOWLAB_*)
├── perimetre.py      liste des destinations autorisées, rejet par défaut
├── database.py       SQLite, schéma versionné et migrations
├── engines/          pilotes : interface commune (base.py), un fichier par moteur, registre extensible
├── scenarios.py      scénarios et résultats attendus
├── site/             site de test, serveur de détection, sessions manuelles (FastAPI)
├── detection.py      détecteurs et empreinte normalisée
├── passages.py       cycle de vie d'un passage (session d'un moteur sur un scénario)
├── campaigns.py      campagnes YAML : validation, exécution, reprise, arrêt d'urgence
├── mesures.py        CPU et mémoire de l'arbre de processus du lanceur
├── analytics.py      statistiques
├── reports.py        exports JSON, CSV, rapport HTML ; suppression
├── api.py            API de consultation et de lancement (/api)
├── tableau.py        tableau de bord (/tableau, fichiers dans tableau_static/)
└── journal.py        journaux JSON (outputs/logs/shadowlab.jsonl)
```

Détail des choix : [`docs/architecture.md`](docs/architecture.md) et [`docs/DECISIONS.md`](docs/DECISIONS.md).

**Ajouter un moteur ou un détecteur** sans toucher au cœur : un paquet qui déclare le point d'entrée
`shadowlab.engines` (une classe héritant de `engines.base.Driver`, options déclarées dans `options_permises`) ou `shadowlab.detectors` (une classe avec
`name`, `version` et `classer(observations)`).

## Sécurité

- Écoute sur `127.0.0.1` par défaut. Sur une autre adresse, le démarrage est refusé sans `SHADOWLAB_JETON`,
  et chaque appel exige `Authorization: Bearer <jeton>`.
- Les appels qui écrivent exigent l'en-tête `X-ShadowLab: 1` (protection contre une page tierce).
- En écoute locale, l'en-tête `Host` doit être un nom local ou un hôte autorisé : une page tierce dont le nom
  pointerait vers `127.0.0.1` (« DNS rebinding ») reçoit une erreur 400.
- Périmètre : `SHADOWLAB_HOTES_AUTORISES` (défaut `127.0.0.1,localhost`). Un nom d'hôte autorisé qui résout
  vers un réseau interne non déclaré est refusé. Navigateurs : verrou réseau (tout le reste part vers une
  adresse locale fermée) ; clients HTTP : chaque redirection est contrôlée.
- Le site de test envoie une politique de sécurité de contenu stricte (`connect-src 'self'`) : rien n'en sort.

## Réglages

| Variable | Défaut | Rôle |
|---|---|---|
| `SHADOWLAB_HOTE` | `127.0.0.1` | Adresse d'écoute |
| `SHADOWLAB_PORT` | `8770` | Port |
| `SHADOWLAB_HOTES_AUTORISES` | `127.0.0.1,localhost` | Destinations autorisées |
| `SHADOWLAB_JETON` | — | Jeton exigé hors écoute locale |
| `SHADOWLAB_SORTIES` | `outputs/` | Base, rapports, captures, journaux |
| `SHADOWLAB_BASE` | `outputs/shadowlab.sqlite3` | Fichier SQLite |
| `SHADOWLAB_MEMOIRE_MAX_MO` | `4096` | Plafond mémoire : au-delà, la campagne s'arrête |
| `SHADOWLAB_CONCURRENCE_MAX` | `1` | Plafond de concurrence (seule la valeur 1 est disponible) |

## Limites connues

Voir [`docs/architecture.md`](docs/architecture.md#limites). En bref : pas de TLS observé, pas d'exécution
concurrente, pas encore de Docker Compose, CPU et mémoire mesurés sur l'arbre de processus du lanceur, et
faux positifs non mesurables tant qu'aucune session humaine n'a été faite.
