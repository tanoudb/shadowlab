# NOEZIA ShadowLab

Plateforme de **recherche et développement** sur le scraping, l'automatisation web, le fingerprinting et les
systèmes anti-bot. Le produit visé est le moteur de récolte NOEZIA ; ShadowLab est le laboratoire qui le mesure.

- **Arena** : une reproduction locale des protections du Web (frontal TLS, Nginx, WAF Coraza, détecteurs,
  CAPTCHA), en 7 niveaux de difficulté.
- **Moteurs** : 15 moteurs de navigation et de collecte (9 intégrés, 6 isolés), dont le moteur NOEZIA.
- **Mesure** : des campagnes reproductibles (moteur × protection × scénario × répétitions), avec intervalles de
  confiance, rapports et interface `/labo`.

**Périmètre (phase interne, décision D-30).** Les outils anti-détection sont permis. Par défaut le périmètre est
illimité (`SHADOWLAB_HOTES_AUTORISES=*`) : en interne, on ne pointe que nos propres cibles. Il peut être
restreint à une liste d'hôtes ; le durcissement final est décrit dans
[`docs/securite-a-finaliser.md`](docs/securite-a-finaliser.md). Contourner un détecteur commercial n'est
autorisé que sur une cible autorisée, avec divulgation coordonnée. Aucun solveur de CAPTCHA réel n'est
intégré. Un score obtenu sur l'Arena ne prédit pas le comportement d'un service externe.

## Prérequis

- Python 3.12 et [uv](https://docs.astral.sh/uv/)
- Node 22 (via `mise`) pour l'interface
- Google Chrome (Selenium) et le Chromium de Playwright
- OrbStack ou Docker, seulement pour l'Arena

## Installer

```bash
uv sync                                   # backend (versions figées dans uv.lock)
uv run playwright install chromium        # navigateur de Playwright
npm --prefix frontend install             # interface (une fois)
npm --prefix frontend run build           # construit frontend/dist
uv run shadowlab moteurs etat             # moteurs disponibles ; `moteurs installer` prépare les isolés
```

## Lancer

```bash
uv run shadowlab site                     # laboratoire : interface, API et site de test
uv run shadowlab arena demarrer           # Arena (Docker Compose : Coraza + Nginx)
uv run shadowlab campagne configs/experiments/essai.yaml   # campagne courte
```

- Interface du laboratoire : <http://127.0.0.1:8770/labo> (sans `npm run build`, mode développement :
  `npm --prefix frontend run dev`, <http://localhost:5173/labo>).
- Site de test : <http://127.0.0.1:8770/lab/>
- Session humaine de référence : <http://127.0.0.1:8770/manuel>
- Documentation de l'API : <http://127.0.0.1:8770/api/docs>
- `/tableau` est l'ancien tableau de bord, déprécié.

Une campagne démarre elle-même le site s'il ne tourne pas. Les rapports (HTML, CSV, JSON) sont écrits dans
`outputs/rapports/<n°>/`. Autres commandes : `shadowlab valider <fichier.yaml>`, `arreter`, `reprendre <n°>`,
`rapport <n°>`, `liste`, `supprimer <n°>`, `arena appliquer|arreter|etat`, `recolter <url>`, `recolte`, `rejeu`. La liste
complète et les commandes de campagnes de référence sont dans la section « Commandes vérifiées » d'`AGENTS.md`.

## Récolter un site

La commande `shadowlab recolte` récolte un site entier à partir d'une **recette** (un fichier YAML par site, dans
`configs/recettes/`). Deux sites factices du labo ont leur recette : des annonces immobilières et des résultats
de rallye.

```bash
uv run shadowlab recolte lancer configs/recettes/vitrine.yaml       # récolte les annonces factices
uv run shadowlab recolte noter vitrine-annonces --verite vitrine    # compare à ce que le site contient vraiment
uv run shadowlab recolte etat vitrine-annonces                      # où en est la récolte
```

Les données sont écrites dans `outputs/recoltes/<nom>/passe-001/` (JSON Lines et CSV pour Excel). La commande
respecte `robots.txt`, ne suit aucune redirection vers un autre site et n'a aucun solveur de CAPTCHA. Un site
qui n'est pas à nous exige une ligne `autorisation` dans la recette. Elle n'a été éprouvée que sur nos deux
sites factices. Guide complet : [`docs/recolte.md`](docs/recolte.md).

## Écrire une campagne

Une campagne est un fichier YAML de `configs/experiments/` : moteurs × niveaux de l'Arena × scénarios ×
répétitions, exécutés un passage à la fois et notés dans la base.

```yaml
experiment:
  name: mon_essai                   # minuscules, chiffres, - et _
  description: Ce que la campagne mesure
  environment: local                # seule valeur acceptée
  engines:
    - noezia                        # un moteur dans sa configuration par défaut
    - name: patchright              # le même moteur avec des options : un libellé distinct est exigé
      label: patchright-chrome-interface
      options: {headless: false, channel: chrome}
  protections: ["01", "03"]         # niveaux de l'Arena (configs/arena/profils.yaml) ; "01" par défaut
  scenarios: [static_html, pagination]
  repetitions: 5
  seed: 20261112                    # facultatif : tirée au hasard et enregistrée sinon
  output: [json, html]
```

Le fichier est validé avant tout lancement (`uv run shadowlab valider <fichier.yaml>`) : moteur, niveau,
scénario ou champ inconnu, et option de moteur non déclarée sont refusés. Les options permises d'un moteur
sont sa liste `options_permises` (`src/shadowlab/engines/`). Les scénarios sont ceux de `SCENARIOS` dans
`src/shadowlab/scenarios.py`. Exemples commentés : `configs/experiments/`.

## Tester

```bash
uv run pytest                                              # tout (navigateurs réels et e2e)
uv run pytest -m "not integration"                         # rapide, sans navigateur
uv run ruff check src tests && uv run ruff format --check src tests
npm --prefix frontend test                                 # interface (vitest)
```

Ne pas lancer de tests ni de travaux lourds pendant une campagne de mesure : ils faussent CPU et durées.

## Déployer

Une seule partie du dépôt se met en ligne : l'**application publique réduite** (`src/shadowlab/public/`). Elle
sert un site vitrine, un consentement et la collecte de sessions humaines ; elle n'expose aucune route du
laboratoire.

```bash
SHADOWLAB_PUBLIC_CONTACT="Nom ou pseudonyme" uv run shadowlab public servir
SHADOWLAB_PUBLIC_CONTACT="Nom ou pseudonyme" scripts/site-public-tunnel.sh   # en ligne par tunnel Cloudflare
```

`SHADOWLAB_PUBLIC_CONTACT` est obligatoire : sans lui, l'application refuse de démarrer. Les visiteurs écrivent au responsable par le formulaire de
contact du site ; aucune adresse n'a besoin d'être affichée. Conditions,
réglages et mode d'emploi : [`docs/site-public.md`](docs/site-public.md).

**Le laboratoire lui-même (`shadowlab site`) ne se met JAMAIS en ligne** : son API lance des navigateurs vers
n'importe quelle adresse. La mise en ligne de l'application publique est faite par le propriétaire du projet.

## Réglages

Variables d'environnement, lues aussi dans un fichier `.env` (ignoré par git). Source : `src/shadowlab/config.py`.

Laboratoire :

| Variable | Défaut | Rôle |
|---|---|---|
| `SHADOWLAB_HOTE` | `127.0.0.1` | Adresse d'écoute |
| `SHADOWLAB_PORT` | `8770` | Port |
| `SHADOWLAB_HOTES_AUTORISES` | `*` | Destinations autorisées (liste d'hôtes séparés par des virgules, ou `*`) |
| `SHADOWLAB_JETON` | — | Jeton exigé hors écoute locale |
| `SHADOWLAB_SORTIES` | `outputs/` | Base, rapports, captures, journaux |
| `SHADOWLAB_BASE` | `<sorties>/shadowlab.sqlite3` | Fichier SQLite |
| `SHADOWLAB_MEMOIRE_MAX_MO` | `4096` | Plafond mémoire : au-delà, la campagne s'arrête |
| `SHADOWLAB_CONCURRENCE_MAX` | `4` | Plafond de passages en parallèle |
| `SHADOWLAB_PORT_ARENA` | `8743` | Port du frontal TLS de l'Arena |
| `SHADOWLAB_PORT_AVAL` | `8781` | Port de Nginx dans la pile Docker de l'Arena |
| `SHADOWLAB_VITRINE_GRAINE` | `20261111` | Graine du site vitrine (contenu connu) |
| `SHADOWLAB_VITRINE_TAILLE` | `500` | Nombre d'annonces du site vitrine |
| `SHADOWLAB_RALLYE_GRAINE` | `20261112` | Graine du site de rallye factice (contenu connu) |
| `SHADOWLAB_RALLYE_TAILLE` | `24` | Nombre de rallyes du site de rallye factice |

Application publique (`SHADOWLAB_VITRINE_GRAINE`, `SHADOWLAB_VITRINE_TAILLE` et `SHADOWLAB_SORTIES` s'appliquent aussi) :

| Variable | Défaut | Rôle |
|---|---|---|
| `SHADOWLAB_PUBLIC_CONTACT` | — (obligatoire) | Responsable (nom ou pseudonyme), affiché sur la page d'information |
| `SHADOWLAB_PUBLIC_HOTES` | `localhost,127.0.0.1` | Noms acceptés dans l'en-tête `Host` |
| `SHADOWLAB_PUBLIC_PORT` | `8771` | Port d'écoute (sur `127.0.0.1`, derrière un mandataire HTTPS) |
| `SHADOWLAB_PUBLIC_HTTPS` | `1` | Cookies `Secure` et HSTS ; `0` pour un essai local |
| `SHADOWLAB_PUBLIC_CONSERVATION_JOURS` | `90` | Durée de conservation d'une session |
| `SHADOWLAB_PUBLIC_BASE` | `<sorties>/public/public.sqlite3` | Base de l'application publique |
| `SHADOWLAB_PUBLIC_ENTETE_IP` | `X-Forwarded-For` | En-tête où le mandataire met l'adresse du visiteur (vide : adresse de la connexion) |

## Pour la suite

- [`AGENTS.md`](AGENTS.md) : source de vérité du projet (état, commandes vérifiées, carte du code, règles, pièges)
- [`docs/PLAN.md`](docs/PLAN.md) : plan de travail unique (objectif, état mesuré, étapes)
- [`docs/recolte.md`](docs/recolte.md) : guide de la commande de récolte (écrire une recette, lancer, reprendre)
- [`docs/DECISIONS.md`](docs/DECISIONS.md) : décisions et leurs raisons
- [`docs/architecture.md`](docs/architecture.md) : architecture et limites
- [`docs/site-public.md`](docs/site-public.md) : application publique
