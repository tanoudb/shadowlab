---
permalink: noezia-shadowlab/journal
title: journal
type: note
---

# Journal inter-IA — noezia-shadowlab

## 2026-11-03 — Claude (Opus 5.5) — Audit, MVP complet et campagne de référence

**Fait**
- Projet créé (`nouveau-projet noezia-shadowlab`), Python 3.12 + `uv`. MVP du cahier des charges « NOEZIA
  ShadowLab » : site de test local (8 pages à résultat connu), serveur de détection (en-têtes dans l'ordre reçu,
  observateur JS, BotD 2.0.0 servi en local), 4 détecteurs (`botd`, `regles-http` v2, `regles-js`, `coherence`),
  4 moteurs (`playwright`, `selenium`, `scrapling` client HTTP, `httpx` témoin), campagnes YAML (graine, reprise,
  arrêt d'urgence, plafond mémoire), SQLite + migrations, statistiques (Wilson, p50/p95/p99), API `/api`, tableau
  de bord `/tableau` (sombre/clair), rapports JSON/CSV/HTML, sessions humaines `/manuel`, CLI `shadowlab`.
- Périmètre : liste blanche, rejet par défaut, redirections contrôlées. **Fuite trouvée par un test** : le filtre
  `route` de Playwright laissait suivre une redirection vers `example.com` → verrou réseau ajouté aux deux
  navigateurs (D-07).
- Mesure CPU corrigée : le site tourne dans un processus à part et hors échantillonnage (D-03) ; temps CPU en ms
  ajouté (migration 2, D-11).
- Campagne de référence `browser_baseline` (expérience n° 1, graine 20261103) : 4 moteurs × 8 scénarios × 100 =
  **3 200 passages, terminée**. Rapports dans `outputs/rapports/1/`.

**Résultats réels (Mac mini M5 Pro, navigateurs sans tête)**
| Moteur | Réussite [IC 95 %] | Médiane / p95 / p99 (ms) | CPU / passage | Mémoire moy. / max |
|---|---|---|---|---|
| playwright | 100 % [99,5–100] | 163 / 880 / 902 | 227 ms | 621 / 778 Mo |
| selenium | 99,9 % [99,3–100] (1 erreur, formulaire) | 134 / 637 / 652 | 311 ms | 1 368 / 1 519 Mo |
| scrapling | 62,5 % (pas de JS : 3 scénarios sur 8 impossibles) | 2 / 6 / 8 | 18 ms | 104 Mo |
| httpx | 62,5 % (idem) | 5 / 9 / 11 | 21 ms | 115 Mo |

- Détection : `botd` et `regles-js` repèrent 100 % des passages tranchés des deux navigateurs ; `regles-http` 100 %
  des 4 moteurs ; `coherence` 0 % (navigateurs standard cohérents entre HTTP et JS) ; clients HTTP : `botd` et
  `coherence` s'abstiennent (pas de JS).
- Faux positifs, précision, F1 : **non mesurables** (aucune session humaine).
- Essai préalable : le client HTTP de Scrapling envoie `Upgrade: h2c`, `Host` en dernier et
  `Referer: google.com` avec `Sec-Fetch-Site: none` → règles HTTP v2 (D-12).

**Fichiers** : tout le dépôt (rien n'est commité). Doc : `README.md`, `docs/architecture.md`, `docs/DECISIONS.md`
(D-01 à D-13), `AGENTS.md`, `notes/ia/contexte.md`, `notes/ia/questions-ouvertes.md`.

**Vérifié** : 46 tests verts (dont 5 réels avec navigateurs), `ruff check` et `ruff format --check` propres,
tableau de bord et rapport HTML relus sur l'expérience n° 1.

**Reste**
- Ethan : faire 20 à 30 sessions humaines sur `http://127.0.0.1:8770/manuel` (sinon pas de faux positifs).
- Décider des moteurs de la phase 6 (Crawlee, SeleniumBase ; Camoufox / undetected-chromedriver déconseillés :
  modification d'empreinte, hors cahier des charges).
- Docker Compose (D-13), observation TLS, exécution concurrente, module d'analyse IA : non faits.
- Premier commit à faire quand Ethan le demande.


## 2026-11-03 — Claude (Opus 5.5) — Revue de sécurité du premier commit

**Fait** (premier commit `abec698`, corrections non commitées)
- Une revue automatique a relevé 5 points ; 4 corrigés, 1 documenté (D-14) :
  - options de moteur sur liste blanche typée (`Driver.options_permises`) ; Scrapling passait toutes les options
    à `FetcherSession` (mandataire, rotation, redirections possibles) ; réglages imposés appliqués en dernier ;
  - en écoute locale, `Host` limité aux noms locaux et hôtes autorisés (DNS rebinding), erreur 400 sinon ;
  - alias YAML refusés (`campaigns.charger_yaml`, CLI et API) ;
  - verrou de campagne de l'API libéré si la création échoue ;
  - documenté seulement : DNS non épinglé entre contrôle et connexion (`docs/architecture.md`, Limites).
- 8 tests ajoutés, vérifiés en échec sans les corrections. 54 tests verts, lint propre.

**Fichiers** : `engines/base.py` et les 4 pilotes, `campaigns.py`, `api.py`, `site/app.py`, `tests/test_campagnes.py`,
`tests/test_site.py`, `README.md`, `AGENTS.md`, `docs/architecture.md`, `docs/DECISIONS.md`.

**Reste** : commit de ces corrections (à la demande d'Ethan) ; épinglage DNS si un nom non local est un jour autorisé.


## 2026-11-03 — Claude (Opus 4.6) — Anti-Bot Arena et périmètre R&D

**Fait**
- **Arena complète** : frontal TLS (JA3/JA4 via MSG_PEEK, `arena/tls.py`), profils de protection YAML
  (`configs/arena/profils.yaml`), secret HMAC (`arena/secret.py`), proxy inverse h11 (`arena/frontal.py`),
  pile Docker Compose Coraza WAF + Nginx (`arena/pile.py`, `docker/`), défis JS proof-of-work + demo CAPTCHA
  (`arena/defis.py`), gardien applicatif (`site/gardien.py`).
- **7 nouveaux moteurs** : curl-cffi (impersonation TLS), patchright (Playwright anti-détection), scrapling-furtif
  (StealthySession), + 4 isolés via pont JSON-over-stdio (`engines/pont.py`, `pont_serveur.py`) : camoufox,
  seleniumbase, seleniumbase-uc, undetected-chromedriver. Environnements dans `moteurs_isoles/`.
- **2 nouveaux détecteurs** : `tls` (GREASE, h2, empreinte non navigateur) et `comportement` (rate, interactions,
  ressources statiques, vitesse de visite).
- **Classification issues** : 6 catégories (extraction réussie, bloqué, challenge non validé, erreur technique,
  échec fonctionnel, indéterminé) dans `issues.py`.
- **Campagnes matricielles** : dimension `protection` ajoutée, exécution parallèle `multiprocessing.spawn`,
  superviseur à limites CPU/mémoire. 2 nouveaux scénarios : `burst_crawl`, `synthetic_browse`.
- **FingerprintJS 5.3.0** (MIT) intégré, chargé paresseusement sur les pages empreinte/détection.
- **Catalogue recherche** : 52 projets open source analysés (`docs/recherche/catalogue.yaml`).
- **Campagne de test Arena** (essai-arena) : 2 moteurs × 4 protections × 5 scénarios = 40 passages, tous
  terminés. TLS fingerprinting vérifié, rate limiting bloque burst_crawl, JS challenges bloquent httpx,
  CAPTCHA bloque Playwright au niveau élevé.
- Décisions D-15 (anti-détection autorisée), D-16 (plateforme R&D), D-17 (environnements isolés),
  D-18 (6 niveaux progressifs). AGENTS.md réécrit pour la vision R&D.

**Fichiers modifiés** : tout `src/shadowlab/` (arena/, engines/, site/, campaigns.py, scenarios.py,
detection.py, issues.py, passages.py, config.py, database.py, cli.py, api.py), `configs/arena/`,
`docker/`, `moteurs_isoles/`, `docs/`, `tests/`, `AGENTS.md`, `pyproject.toml`.

**Vérifié** : 49 tests verts (5 intégration désactivés par marqueur), lint propre.

**Reste**
- Commiter le travail Arena (rien commité depuis `abec698`).
- Implémenter les 6 niveaux progressifs (remplacer faible/moyen/élevé).
- Installer les environnements isolés (camoufox, seleniumbase, uc, crawlee).
- Intégrer Turnstile / reCAPTCHA en test keys.
- Dashboard avancé (challenges, combinaisons, faiblesses).
- Moteur expérimental propre (à concevoir).
- Couche IA (à concevoir).

## 2026-11-03 — session Opus 4.6 (suite) — 6 niveaux, sécurité, honeypots

### Fait
- **6 niveaux progressifs (D-18)** : profils.yaml réécrit (01-06), profils.py refactoré
  (classe Profils dynamique, normaliser(), compat arrière faible→02/moyen→04/élevé→05),
  campaigns.py/app.py/pages.py mis à jour (BASELINE remplace AUCUNE, dropdown 6 niveaux).
- **Sécurité paramètre `sl`** : rejet des doublons dans frontal.py et app.py (différentiel
  parse_qs vs Starlette QueryParams corrigé).
- **Honeypots** : lien piège invisible (`/lab/piege`), champ piège `sl_telephone` dans le
  formulaire, décisions enregistrées en base, intégrés dans le calcul de suspicion du gardien.
- **Fingerprinting actif** : le gardien enregistre les motifs de suspicion quand le profil
  l'active (niveaux 03+).
- Test d'intégration corrigé (nombre de détecteurs dynamique : 6, pas 4).
- 3 tests honeypots ajoutés. 57 tests verts, lint propre.

### Fichiers
- `configs/arena/profils.yaml`, `src/shadowlab/arena/profils.py`, `src/shadowlab/campaigns.py`
- `src/shadowlab/site/app.py`, `src/shadowlab/site/pages.py`, `src/shadowlab/site/gardien.py`
- `src/shadowlab/site/static/lab.css`, `src/shadowlab/arena/frontal.py`
- `tests/test_campagnes.py`, `tests/test_integration.py`, `tests/test_site.py`

### Décisions
- D-18 implémentée (6 niveaux progressifs).
- Finding sécurité noté : quand un sceau existe, utiliser `sceau.session` au lieu de re-parser
  `sl` (refactoring futur, touche la signature).

### Reste
- Turnstile avec clés de test (niveaux 05-06).
- Dashboard avancé (challenges déclenchés/résolus, résultats par combinaison).
- Environnements isolés (camoufox, seleniumbase, crawlee).
- Moteur expérimental et couche IA.

## 2026-11-03 — session Opus 4.6 (suite 2) — Turnstile

### Fait
- **Turnstile (Cloudflare test keys)** intégré pour les niveaux 05-06 :
  - Clés publiques always-pass/always-block dans `defis.py`
  - Vérification serveur via API `siteverify`
  - Page widget Turnstile (`pages.page_turnstile`)
  - Route `/lab/turnstile/verifier` avec cookie de réussite signé
  - CSP dédiée pour `challenges.cloudflare.com`
  - Résultats étiquetés `captcha_test` (D-16)
- AGENTS.md mis à jour (état courant).
- 57 tests verts.

### Fichiers
- `src/shadowlab/arena/defis.py`, `src/shadowlab/site/gardien.py`
- `src/shadowlab/site/app.py`, `src/shadowlab/site/pages.py`
- `AGENTS.md`

### Reste
- Dashboard avancé (challenges déclenchés/résolus, résultats par combinaison).
- Environnements isolés (camoufox, seleniumbase, crawlee).
- Moteur expérimental et couche IA.

## 2026-11-03 — session Opus 4.6 (suite 3) — Consolidation

### Fait
- AGENTS.md mis à jour : Turnstile retiré de « Pas encore », ajouté dans l'état courant.
- 57 tests verts, lint propre.

### État des axes
- **Arena** : 6 niveaux opérationnels, honeypots, fingerprinting actif, Turnstile (test keys).
- **Moteurs** : 7 intégrés, 4 isolés à installer.
- **Mesure** : campagnes matricielles, Wilson, CPU/mémoire.

### Prochaines pistes (au choix)
1. **Dashboard avancé** — challenges déclenchés/résolus, résultats par combinaison moteur×protection.
2. **Environnements isolés** — rendre camoufox, seleniumbase, seleniumbase-uc opérationnels.
3. **reCAPTCHA test keys** — second CAPTCHA provider après Turnstile.

## 2026-11-03 — session Opus 4.6 (suite 4) — Dashboard avancé, reCAPTCHA, moteurs isolés

### Fait
- **Dashboard avancé (Arena)** : nouvelle vue avec compteurs de décisions par couche,
  matrice moteur × protection (barres colorées), graphique durées. Deux endpoints API
  ajoutés (`/api/experiences/{id}/decisions`, `/api/experiences/{id}/protections`).
  Palette étendue à 11 séries (tous les moteurs).
- **reCAPTCHA v2 (Google test keys)** intégré pour les niveaux 05-06 :
  - Clés publiques test dans `defis.py` (always-pass)
  - Vérification serveur via API `siteverify`
  - Page widget reCAPTCHA (`pages.page_recaptcha`)
  - Route `/lab/recaptcha/verifier` avec cookie de réussite signé
  - CSP dédiée pour `www.google.com/recaptcha` et `www.gstatic.com`
  - Résultats étiquetés `captcha_test` (D-16)
  - Modèle `Recaptcha` dans `profils.py`, profils 05-06 activés
- **Moteurs isolés** : infrastructure déjà complète (pont, pont_serveur, 4 drivers).
  crawlee et zendriver ont des pyproject.toml mais pas de driver (API async → futur).
- 58 tests verts, lint propre.
- AGENTS.md mis à jour.

### Fichiers modifiés
- `src/shadowlab/arena/defis.py`, `src/shadowlab/arena/profils.py`
- `src/shadowlab/site/app.py`, `src/shadowlab/site/gardien.py`, `src/shadowlab/site/pages.py`
- `src/shadowlab/api.py` (endpoints Arena)
- `src/shadowlab/tableau_static/app.js`, `app.css`, `index.html`
- `configs/arena/profils.yaml`
- `tests/test_site.py`

### Décisions
- crawlee et zendriver restent sans driver : leur API async ne mappe pas sur `Driver` sync.
- reCAPTCHA placé après Turnstile dans la chaîne du gardien (deux challenges externes successifs en 05-06).

### Reste
- Cloudflare sur domaine test, moteur expérimental propre, couche IA.
