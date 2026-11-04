# ShadowLab v0.6 — Release Notes

Date : 2026-11-04
Base : v0.5 (`5f9f351`) → v0.6 (`d030d57`)
Branche : `master`, 6 commits atomiques

---

## 1. Résumé

ShadowLab v0.6 transforme le laboratoire en plateforme de mesure scientifiquement fiable :
rigueur statistique, reproductibilité expérimentale, références humaines avec consentement,
analytique multidimensionnelle et qualification par golden datasets.

## 2. Périmètre préservé

- Destinations locales ou explicitement autorisées seulement, rejet par défaut.
- Aucun solveur de CAPTCHA (une personne seule valide un CAPTCHA).
- Aucun contournement écrit sur mesure contre un détecteur commercial ou un service tiers.
- Aucun résultat de mesure inventé.
- CAPTCHA providers en mode test (test keys) ≠ victoire contre un vrai CAPTCHA.

## 3. Passes et commits

| Passe | Commit | Description |
|-------|--------|-------------|
| 1 | `649d8b3` | **Correction de 3 bugs critiques** — A2a: `burst_crawl` distingue 429/403/5xx ; A2b: `fingerprint_observation`/`detection_page` vérifient le contenu ; A5: `bloc()` calcule sur `issue` au lieu de `status` |
| 2 | `4ee4955` | **Tests de validation statistique** — E2+E3: réconciliation Σ issues == total ; E4: validité Wilson CI ; E7: stabilité des rapports ; A4: effectifs exacts dans `comparer()` |
| 3 | `c62911e` | **Références humaines** — B1+B2: consentement explicite, profils de référence ; B4: matrices de confusion 2×2 complètes (VP/FN/FP/VN, rappel, spécificité, précision, F1) |
| 4 | `f5832f4` | **Reproductibilité expérimentale** — C2: warm-up configurable, exclusion des statistiques ; C4: autocorrélation lag-1 des répétitions ; C5: versions Arena Docker enregistrées ; isolation Selenium améliorée |
| 5 | `b9a8287` | **Analytique avancée** — D1: matrice croisée moteur × protection × scénario ; D2: taux conditionnel réussite\|non-bloqué ; D6: qualité des métriques (observé/estimé/limité) |
| 6 | `d030d57` | **Golden datasets et qualification** — E1: jeu de référence à résultats connus ; E6: reproductibilité bout-en-bout par seed |

## 4. Couverture de l'audit v0.6

| Phase | Avant (v0.5) | Après (v0.6) |
|-------|-------------|-------------|
| A — Audit et corrections | 2 OK, 3 DEF, 2 PART, 1 MANQ | 5 OK, 0 DEF, 2 PART, 1 MANQ |
| B — Références humaines | 1 OK, 0 DEF, 1 PART, 2 MANQ | 3 OK, 0 DEF, 1 PART, 0 MANQ |
| C — Reproductibilité | 1 OK, 0 DEF, 3 PART, 1 MANQ | 4 OK, 0 DEF, 1 PART, 0 MANQ |
| D — Analyse et visualisation | 1 OK, 0 DEF, 4 PART, 0 MANQ | 4 OK, 0 DEF, 2 PART, 0 MANQ |
| E — Validation automatique | 0 OK, 0 DEF, 2 PART, 5 MANQ | 5 OK, 0 DEF, 2 PART, 0 MANQ |
| **Total** | **5 OK, 3 DEF, 12 PART, 9 MANQ** | **21 OK, 0 DEF, 8 PART, 0 MANQ** |

**Progression** : 0 DEF (était 3), 0 MANQ (était 9), +16 exigences OK.

## 5. Tests

- **v0.5** : 58 tests
- **v0.6** : 166 tests (+108)
- Lint (`ruff check + format`) : propre
- Temps d'exécution : ~12 s

## 6. Fichiers modifiés

14 fichiers modifiés, +1 157 / -64 lignes.

Principaux :
- `analytics.py` : +268 lignes — matrice de confusion, dépendance répétitions, matrice croisée 3D, taux conditionnels, qualité des métriques
- `test_validation.py` : +779 lignes — 55 tests de validation (réconciliation, Wilson, golden dataset, reproductibilité, analytique)
- `scenarios.py` : corrections A2a/A2b
- `database.py` : migrations 5 (consent_at) et 6 (is_warmup)
- `campaigns.py` : warm-up, versions Arena
- `passages.py` : consentement, warm-up

## 7. Nouvelles fonctionnalités analytiques

- **`matrice_confusion()`** — VP/FN/FP/VN, rappel, spécificité, précision, F1 avec Wilson CI
- **`dependance_repetitions()`** — autocorrélation lag-1 par (moteur, protection, scénario)
- **`qualite_metriques()`** — tag observé/estimé/limité par métrique
- **`matrice_croisee`** — produit complet moteur × protection × scénario dans `statistiques()`
- **`reussite_si_non_bloque`** — taux conditionnel (Wilson CI)
- **`profils_humains()`** — profils de référence des sessions humaines
- **Warm-up** — premières N répétitions exclues des statistiques

## 8. Commandes CLI ajoutées

- `shadowlab manuel` — liste les sessions humaines de référence et leurs profils

## 9. Ce qui reste (PART dans l'audit)

- **A3** : nettoyage de l'état navigateur entre répétitions (Playwright OK, Selenium amélioré mais pas complet pour tous les moteurs)
- **A4** : IC sur précision/rappel/F1 (Wilson sur rappel et précision OK, IC combiné F1 non implémenté)
- **B4** : la précision mélange VP d'expérience et FP de sessions manuelles (design délibéré, documenté)
- **C3** : pas de mécanisme automatique pour relancer et comparer 2 campagnes identiques
- **D3** : overlap entre détecteurs (complémentarité quantifiée manquante)
- **D4** : pas d'histogramme de latence (résumés p95/p99 OK)
- **E5** : comptage systématique des valeurs manquantes (qualité tags couvrent le cas principal)
- **E6** : test bout-en-bout avec campagne réelle (tests unitaires couvrent le pipeline)

## 10. Prérequis inchangés

- Python 3.12, `uv`, Google Chrome, Playwright Chromium, OrbStack/Docker (Arena)
- `uv sync && uv run pytest` pour vérifier
