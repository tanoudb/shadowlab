---
permalink: noezia-shadowlab/journal
title: journal
type: note
---

# Journal inter-IA — noezia-shadowlab

## 2026-11-04 — Claude (Opus 4.8) — ShadowLab v0.7 : audit adversarial et corrections

**Fait** : audit adversarial des 7 défauts v0.6 + Phase 2/3. 15 commits atomiques
(`dcb0e9f`..`89697f0`), reproduction (test rouge, chemin réel) puis correction pour chacun.

**Défauts** : #4 statut/mémoire (CORRIGÉ), #3 identité serveur via `/lab/sante` (CORRIGÉ),
#6 campagne `termine_incomplet` si moteur absent (CORRIGÉ), #1 matrice confusion gating
protection+version+prévalence (PARTIEL), #5 comparer() équivalence des designs (PARTIEL —
pas de comparaison par cellule), #7 runs test + fin de la surinterprétation lag-1
(NON DÉMONTRÉE — indépendance non prouvée), #2 confidence documentée non calibrée (labelling).

**Tests** : 187 unitaires + 6 intégration (vrais navigateurs, reproductibilité bout-en-bout). Lint propre.

**Non fait / non testé** : calibration confidence, comparaison par cellule (Simpson),
intégration Arena automatisée (NON TESTÉ, risque ports/état), isolation Selenium, traçage
de la complétude des observations.

**Fichier** : `SHADOWLAB_V07_AUDIT.md` (rapport complet, risques classés, priorités).

---

## 2026-11-04 — Claude (Opus 4.6) — ShadowLab v0.6 : implémentation complète (6 passes)

**Fait** : 6 passes d'implémentation v0.6 avec commits atomiques (649d8b3..d030d57).

**Passes** :
1. `649d8b3` — Correction de 3 bugs (burst_crawl, vérifications contenu, taux sur issue)
2. `4ee4955` — Tests de validation statistique (réconciliation, Wilson, stabilité)
3. `c62911e` — Références humaines (consentement, profils, matrices de confusion 2×2)
4. `f5832f4` — Reproductibilité (warm-up, autocorrélation lag-1, versions Arena, isolation Selenium)
5. `b9a8287` — Analytique avancée (matrice 3D, taux conditionnels, qualité métriques)
6. `d030d57` — Golden datasets et qualification (jeu de référence, reproductibilité par seed)

**Résultat** : 166 tests verts (était 58), lint propre. 14 fichiers, +1157/-64 lignes.

**Couverture audit** : 21 OK / 8 PART / 0 DEF / 0 MANQ (était 5/12/3/9).

**Fichier** : `SHADOWLAB_V06_RELEASE.md`

**Reste** : 8 exigences PART (IC combiné F1, overlap détecteurs, histogrammes latence, test campagne réelle). Rien de bloquant.

---

## 2026-11-04 — Claude (Opus 4.6) — Audit v0.6 : matrice implémenté / défectueux / manquant

**Fait** : audit complet du code v0.5 contre la spec v0.6 (5 phases, 29 exigences).

**Fichier** : `docs/audit-v06.md`

**Résultat** :
- 5 OK, 3 défectueux, 12 partiels, 9 manquants
- Phase E (validation) la plus lacunaire : 5/7 manquants
- Phase A : 3 bugs identifiés (burst_crawl, vérifications superficielles, taux basé sur status au lieu d'issue)
- Phase B : collecteur humain manquant — piste : site vitrine Arena + communauté pour sessions réelles
- `comparer()` reconstruit les effectifs par arrondi au lieu de garder les comptes exacts

**Plan de correction** : 6 passes avec commits distincts (bugs → validation → humains → reproductibilité → analyse → jeux de référence).

**Reste** : commencer Passe 1 (corrections des 3 bugs DEF).

---

## 2026-11-04 — Claude (Opus 4.6) — Benchmark v0.5 : exécution et résultats

*(entrée précédente renommée pour clarté)*

## 2026-11-04 — Claude (Opus 4.6) — ShadowLab v0.5 : Benchmark & Experiment Engine

### Fait
- **Fiabilité** : randomisation reproductible des unités (seed), config de protection complète enregistrée par passage avec SHA-256, migration 4 (`protection_config`, `config_hash`).
- **Statistiques** : Fisher exact (pure Python, sans scipy), Holm-Bonferroni pour comparaisons multiples, `comparer()` avec deltas + p-values + significativité.
- **Exports** : CSV enrichi (protection/issue/cause), `passages.json` (export brut par passage), rapport HTML avec `(n=X)` et section par protection.
- **Diagnostic** : `regles_fingerprinting()` dynamique (remplace le tuple figé), `generer_profils_ablation()` multi-niveaux, `verifier_profils()`.
- **CLI** : `--generer-ablation 03,04` (multi-niveaux), `--verifier-profils`, sous-commande `comparer <ref> <nouveau>`.
- **API** : `/api/comparaison` enrichie avec `analytics.comparer()` quand 2 expériences.
- **Tests** : 105 passent (2 nouveaux fichiers : `test_reports.py`, `test_comparaison.py`, ajouts dans analytics/diagnostic/campagnes).
- **Config** : `benchmark-v05.yaml` (7×6×6×30 = 7 560 passages, seed 20261104).

### Fichiers modifiés
`database.py`, `passages.py`, `campaigns.py`, `analytics.py`, `reports.py`, `diagnostic.py`, `cli.py`, `api.py`, + 2 nouveaux tests + config benchmark.

### Décisions
- Fisher exact plutôt que chi² (petits effectifs attendus avec 30 reps).
- Pas de dépendance scipy : implémentation pure Python avec `math.comb`.
- `comparer()` retourne une structure imbriquée `deltas.reussite` / `deltas.duree_ms` (extensible).
- L'API `/api/comparaison` change de type de retour (`dict` avec `experiences` + `deltas` au lieu d'une `list`).

### Reste
- Préparation v0.6 (moteur expérimental NOEZIA).

## 2026-11-04 — Claude (Opus 4.6) — Benchmark v0.5 : exécution et résultats

### Fait
- Campagne de validation courte (24 passages) : tous les livrables v0.5 vérifiés.
- **Benchmark complet** : expérience #11, 7 560 passages (7 moteurs × 6 protections × 6 scénarios × 30 reps), seed 20261104.
- Rapports générés : `outputs/rapports/11/` (statistiques.json, passages.json 20 Mo, passages.csv 2 Mo, rapport.html).
- Expérience #10 (interrompue lors d'un changement de session) supprimée.
- Arena arrêtée après la campagne.
- Nettoyage disque : 24 Go libérés (uv cache 21.8 Go, Docker build cache 2 Go, npm/Homebrew).

### Résultats clés
| Moteur | Taux global | Meilleur niveau |
|--------|------------|-----------------|
| scrapling-furtif | 63.9 % | 100 % niv. 01-03, 83 % niv. 04 |
| playwright | 16.7 % | 100 % niv. 01 seulement |
| selenium | 16.7 % | 100 % niv. 01 seulement |
| patchright | 16.7 % | 100 % niv. 01 seulement |
| httpx | 11.1 % | 67 % niv. 01 seulement |
| curl-cffi | 11.1 % | 67 % niv. 01 seulement |
| scrapling | 11.1 % | 67 % niv. 01 seulement |

- **Niveaux 05-06** : 0 % pour tous — Turnstile + reCAPTCHA (test keys) bloquent tout.
- **scrapling-furtif** domine nettement : seul moteur à passer les niveaux 02-04.
- Clients HTTP (httpx, curl-cffi, scrapling) : 67 % au niveau 01 (4/6 scénarios, ceux sans JS).

### Reste
- Préparation v0.6 (moteur expérimental NOEZIA).

## 2026-11-04 — Claude (Opus 4.6) — ShadowLab v0.4 : validation scientifique

**Fait :**
- Tests de régression pour les 5 rapports CLI diagnostic (18 tests) : `test_diagnostic.py`
- Campagne d'ablation réelle dans l'Arena :
  - `profils.py` : champ `exclure` sur `Fingerprinting`, env `SHADOWLAB_PROFILS_EXTRA`
  - `gardien.py` : `suspicion()` respecte les exclusions du profil
  - `diagnostic.py` : `generer_profils_ablation()`, `ecrire_profils_ablation()`
  - `cli.py` : `--generer-ablation NIVEAU`
  - `configs/experiments/ablation-03.yaml` : 9 moteurs × 7 protections × 2 scénarios
- Tests Turnstile/reCAPTCHA : assertions que les clés sont les officielles de développement
- Diagnostic `par_protection` : taux indépendant par couche, erreurs techniques exclues du dénominateur
  - Répond à « Ce moteur a été classé automatisé par telle règle, avec telle observation »
  - CLI : `--rapport par_protection`

**Commits :** `fb278a2`, `68b0402`, `d79f068`, `d553ac7`
**Fichiers :** `diagnostic.py`, `cli.py`, `profils.py`, `gardien.py`, `test_diagnostic.py`, `test_site.py`,
`configs/experiments/ablation-03.yaml`, `configs/arena/profils-ablation-03.yaml`
**Reste :** lancer la campagne d'ablation réelle, enrichir le rapport HTML avec le diagnostic par protection.

---

## 2026-11-04 — Claude (Opus 4.6) — Diagnostic par signal (D-20)

**Fait :**
- Module `src/shadowlab/diagnostic.py` avec 4 rapports post-campagne :
  - `signaux` : détecteur, signal déclencheur et description, par moteur détecté
  - `chaine` : premier motif de blocage par moteur et par niveau de protection (répond à la demande sur les niveaux 05-06)
  - `configurations` : UA, Accept-Language, Sec-Fetch, Sec-CH-UA, version HTTP, JA4, ordre des en-têtes, comparés côte à côte
  - `ablation` : recalcul des verdicts de détection en désactivant chaque règle une par une
- Commande CLI `shadowlab diagnostic <id> [--rapport signaux|chaine|configurations|ablation|tous]`
- D-20 ajoutée : patchright reste en configuration standard comme référence

**Résultats clés de l'ablation (expérience 7, 264 passages) :**
- `regles-js` est la règle la plus critique : sans elle, 31% échappent (undetected-chromedriver passe aussi)
- `comportement` a un impact modéré (14% vs 8% de passages échappés)
- Les 3 anti-détection (camoufox, scrapling-furtif, seleniumbase-uc) échappent toujours, peu importe la règle retirée

**Fichiers :** `src/shadowlab/diagnostic.py` (nouveau), `src/shadowlab/cli.py`, `docs/DECISIONS.md`
**Commit :** `fa4f569`
**Reste :** enrichir le rapport HTML avec les diagnostics, ajouter des tests unitaires pour le module diagnostic.

---

## 2026-11-04 — Claude (Opus 4.6) — Blocage fingerprinting niveaux 02-03

**Fait**
- Ajout du mode de blocage fingerprinting à trois valeurs (`non`, `http`, `tout`) dans `profils.py` et
  `profils.yaml` (D-19). Niveau 02 bloque sur signaux HTTP/TLS, niveau 03 sur tous les signaux y compris JS.
- `gardien.py:controler()` bloque désormais quand `bloquer != "non"` au lieu de simplement loguer.
- `suspicion()` accepte `inclure_js` pour que le mode `http` ne consulte que les règles HTTP/TLS.
- Page `page_blocage()` ajoutée dans `pages.py` pour le refus fingerprinting.
- Campagne `arena-essai` (3 moteurs × 6 niveaux) : niveau 01 = 100 % réussite, niveaux 02-06 = 0 % (blocage
  fingerprinting confirmé). 53 tests verts, lint propre.

**Fichiers modifiés** : `src/shadowlab/arena/profils.py`, `configs/arena/profils.yaml`,
`src/shadowlab/site/gardien.py`, `src/shadowlab/site/pages.py`, `docs/DECISIONS.md`.

**Décisions** : D-19 (trois modes de blocage fingerprinting).

**Campagne de validation (11 moteurs × 6 niveaux, 264 passages)**
- Trois groupes : 7 moteurs bloqués dès le 02 (dont patchright, surprenant), 3 anti-détection (camoufox,
  scrapling-furtif, seleniumbase-uc) passent jusqu'au 04 et bloqués au 05 par Turnstile/reCAPTCHA,
  undetected-chromedriver échoue partout (bug moteur).
- La différenciation 02 vs 03 ne se manifeste pas : les vrais anti-détection passent les deux niveaux.
  Les détecteurs JS (BotD, regles-js, coherence) ne parviennent pas à distinguer camoufox/seleniumbase-uc
  d'un vrai navigateur. C'est un résultat utile : il montre que le fingerprinting passif ne suffit pas contre
  les outils modernes, et que les CAPTCHA (niveau 05+) restent la seule barrière efficace.
- patchright bloqué dès le 02 : cause identifiée — il hérite de DriverPlaywright sans changer le User-Agent
  (`HeadlessChrome`, signal `ua_headless` = 1.0) ni ajouter `Accept-Language` (signal `langue_absente` = 0.5).
  Les patchs de patchright portent uniquement sur les APIs JS (navigator.webdriver, etc.), pas sur les en-têtes
  HTTP. C'est cohérent avec D-04 (config standard). L'option `locale` de Chromium résoudrait les deux signaux
  mais ce serait un réglage ajouté.

**Reste**
- Investiguer pourquoi patchright est détecté par les règles HTTP.
- Renforcer les détecteurs JS pour distinguer les anti-détection (axe futur, non urgent).


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

## 2026-11-04 — session Opus 4.6 — Première campagne Arena complète

### Fait
- **Campagne essai** (exp. 3) : 3 moteurs × 6 protections × 4 scénarios × 1 rép = 72 passages.
  Résultat : playwright 100 % sur 01-03, httpx/curl-cffi 75 % (pas de JS), tout bloque à 04+.
- **Campagne complète** (exp. 4) : 7 moteurs × 6 protections × 10 scénarios × 5 rép = **2 100 passages**.
  Durée : ~12 minutes, concurrency 1.

### Résultats (exp. 4)
| Moteur | 01 | 02 | 03 | 04 | 05 | 06 |
|---|---|---|---|---|---|---|
| scrapling-furtif | 100 % | 100 % | 100 % | **90 %** | 0 % | 0 % |
| playwright | 100 % | 100 % | 100 % | 0 % | 0 % | 0 % |
| patchright | 100 % | 100 % | 100 % | 0 % | 0 % | 0 % |
| selenium | 90 % | 90 % | 90 % | 0 % | 0 % | 0 % |
| httpx | 60 % | 60 % | 60 % | 0 % | 0 % | 0 % |
| curl-cffi | 60 % | 60 % | 60 % | 0 % | 0 % | 0 % |
| scrapling | 60 % | 60 % | 60 % | 0 % | 0 % | 0 % |

- **scrapling-furtif** seul moteur à percer le niveau 04 (proof-of-work JS) : 45/50 = 90 %.
- Selenium à 90 % (01-03) : 5 erreurs techniques par niveau (burst_crawl timeout probable).
- Clients HTTP (httpx, curl-cffi, scrapling) à 60 % : les 4 scénarios JS échouent (pas de moteur JS).
- Niveaux 05-06 : mur total (Turnstile + reCAPTCHA, aucun solveur conforme au périmètre).
- Décisions : 21 572 WAF passes, 2 356 défis JS émis / 601 validés (26 %), 3 095 fingerprinting suspects,
  585 CAPTCHA + 1 560 Turnstile émis / 0 validés.
- Durées moyennes : httpx 42 ms, curl-cffi 44 ms, scrapling 89 ms, selenium 402 ms,
  playwright 660 ms, patchright 694 ms, scrapling-furtif 889 ms.

### Enseignements
- La rupture défensive est entre 03 (fingerprinting passif) et 04 (challenge JS actif).
- scrapling-furtif (Scrapling StealthySession) résout le proof-of-work JS contrairement à playwright/patchright standard.
- Patchright ne fait pas mieux que playwright standard sur cette Arena (pas de contremesures spécifiques ici).
- Les niveaux 05-06 nécessitent une validation CAPTCHA humaine ou un futur mécanisme de contournement de test keys.

### Fichiers
- `configs/experiments/arena-essai.yaml`, `configs/experiments/arena-complete.yaml`
- `outputs/rapports/3/`, `outputs/rapports/4/` (statistiques.json, passages.csv, rapport.html)

### Reste
- ~~Installer les environnements isolés~~ → fait (session suivante).
- Investiguer pourquoi scrapling-furtif perce 04 mais pas 05 (Turnstile bloque, pas le JS).
- Moteur expérimental propre, couche IA.

## 2026-11-04 — session Opus 4.6 — Moteurs isolés et campagne 11 moteurs

### Fait
- **Environnements isolés installés** : camoufox (+ Firefox modifié 158.0.1-beta.41, 1.3 Go),
  seleniumbase, undetected-chromedriver. 11/11 moteurs prêts (`shadowlab moteurs etat`).
- **Campagne élargie** (exp. 5) : 11 moteurs × 6 protections × 10 scénarios × 3 rép = **1 980 passages**.

### Résultats (exp. 5)
| Moteur | Type | 01 | 02 | 03 | 04 | 05 | 06 |
|---|---|---|---|---|---|---|---|
| camoufox | iso, anti-det | 100 % | 100 % | 100 % | **90 %** | 0 % | 0 % |
| scrapling-furtif | intégré, anti-det | 100 % | 100 % | 100 % | **90 %** | 0 % | 0 % |
| seleniumbase-uc | iso, anti-det | 90 % | 90 % | 90 % | **80 %** | 0 % | 0 % |
| patchright | intégré, anti-det | 100 % | 100 % | 100 % | 0 % | 0 % | 0 % |
| playwright | intégré, standard | 100 % | 100 % | 100 % | 0 % | 0 % | 0 % |
| selenium | intégré, standard | 90 % | 90 % | 90 % | 0 % | 0 % | 0 % |
| seleniumbase | iso, standard | 90 % | 90 % | 90 % | 0 % | 0 % | 0 % |
| curl-cffi | intégré, anti-det | 60 % | 60 % | 60 % | 0 % | 0 % | 0 % |
| httpx | intégré, standard | 60 % | 60 % | 60 % | 0 % | 0 % | 0 % |
| scrapling | intégré, anti-det | 60 % | 60 % | 60 % | 0 % | 0 % | 0 % |
| undetected-chromedriver | iso, anti-det | 0 % | 0 % | 0 % | 0 % | 0 % | 0 % |

- **3 moteurs percent le niveau 04** (proof-of-work JS) : camoufox (90 %), scrapling-furtif (90 %),
  seleniumbase-uc (80 %). Ce sont les 3 outils avec contournement actif de détection JS.
- **undetected-chromedriver** : erreur technique 100 % — incompatibilité Chrome 156 probable, à investiguer.
- **seleniumbase (standard)** : 90 % comme selenium, sans gain anti-détection (mode UC désactivé).
- Durées moyennes : httpx 61 ms, curl-cffi 67 ms, scrapling 73 ms, selenium 360 ms,
  seleniumbase 436 ms, patchright 679 ms, playwright 680 ms, scrapling-furtif 976 ms,
  seleniumbase-uc 1 616 ms, camoufox 2 730 ms.
- Niveaux 05-06 : mur total (Turnstile + reCAPTCHA, aucun solveur).

### Enseignements
- Les moteurs anti-détection actifs (camoufox, scrapling-furtif, seleniumbase-uc) résistent au
  proof-of-work JS grâce à leur camouflage d'empreinte navigateur.
- Patchright et playwright standard ne percent pas le 04 : ils se contentent de masquer
  `navigator.webdriver` mais l'empreinte complète est détectée.
- Compromis vitesse/furtivité : camoufox est 45× plus lent que httpx mais le seul à combiner
  Firefox modifié + empreinte custom.
- undetected-chromedriver est cassé avec Chrome 156 (le projet semble mal maintenu).

### Fichiers
- `moteurs_isoles/camoufox/.venv/`, `moteurs_isoles/seleniumbase/.venv/`,
  `moteurs_isoles/undetected-chromedriver/.venv/` (créés, non versionnés)
- `configs/experiments/arena-tous-moteurs.yaml` (nouveau)
- `outputs/rapports/5/` (statistiques.json, passages.csv, rapport.html)

### Reste
- Investiguer l'erreur undetected-chromedriver (version Chrome ? API dépréciée ?).
- Moteur expérimental propre (combiner les techniques de camoufox + scrapling-furtif).
- Couche IA pour analyse automatique des résultats.
- Cloudflare sur domaine test (pour tester hors test keys).

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
