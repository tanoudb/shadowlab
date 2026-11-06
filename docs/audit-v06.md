# Audit ShadowLab v0.6 — Matrice implémenté / défectueux / manquant

Date : 2026-11-04
Base : code sur `master` au commit `5f9f351` (ShadowLab v0.5)

Légende :
- **OK** — implémenté et correct
- **DEF** — implémenté mais défectueux (bug ou écart avec la spec)
- **PART** — partiellement implémenté (l'infrastructure existe, il manque des morceaux)
- **MANQ** — manquant (rien dans le code)

---

## Phase A — Audit et corrections

| # | Exigence | État | Fichier(s) | Détail |
|---|----------|------|------------|--------|
| A1 | Critères de réussite explicites par scénario | OK | `scenarios.py` | 10 scénarios, chacun avec son `executer` et sa vérification. Critères clairs : comparaison textuelle, présence d'éléments, comptages. |
| A2a | `burst_crawl` : définition de « refus » | DEF | `scenarios.py:L~170` | Compte les non-200 comme refus, mais un 429 (rate limit) et un 403 (WAF) ont des significations différentes. Pas de distinction. |
| A2b | `fingerprint_observation` / `detection_page` : vérification superficielle | DEF | `scenarios.py` | Vérifie seulement que l'élément HTML existe, pas son contenu. Un élément vide serait compté comme succès. |
| A3 | Indépendance des répétitions | PART | `campaigns.py` | Randomisation par seed OK. Mais aucun nettoyage explicite de l'état navigateur entre répétitions (cache, cookies, sessions). Pas de mesure de corrélation inter-répétitions. |
| A4 | Définitions détection / rappel / IC | PART | `analytics.py` | Wilson CI OK, VP/FN corrects. Mais : (1) `comparer()` reconstruit les effectifs exacts par `round(taux * n)` → erreur d'arrondi possible ; (2) pas d'IC sur précision/rappel/F1, seulement sur taux de détection et FP. |
| A5 | Séparation erreurs techniques / échecs fonctionnels | DEF | `analytics.py`, `issues.py` | 6 issues bien définis dans `issues.py`. Mais `analytics.bloc()` calcule `taux_erreur` sur `status == "erreur"` au lieu de `issue == "erreur_technique"` → mismatch possible. Le taux de réussite inclut les erreurs techniques au dénominateur (devrait les exclure pour un taux fonctionnel). `diagnostic.par_protection()` fait juste et exclut les erreurs techniques. |
| A6 | Cohérence observation / verdict | OK | `passages.py`, `issues.py` | Le pipeline `finaliser()` est cohérent : observations → détection → issue. Un passage réussi peut être détecté (correct : le moteur a extrait mais est repéré). Les `drapeaux` sont indépendants de l'issue. |
| A7 | Tests de réconciliation | MANQ | `tests/` | Aucun test vérifiant : (1) somme des issues == total passages ; (2) validité des IC Wilson (bas ≤ taux ≤ haut, 0 ≤ all ≤ 1) ; (3) cohérence CSV/JSON/stats ; (4) stabilité des rapports (même données → même sortie). |

---

## Phase B — Références humaines

| # | Exigence | État | Fichier(s) | Détail |
|---|----------|------|------------|--------|
| B1 | Collecteur de sessions humaines | MANQ | `passages.py` | `experience_manuelle()` crée l'entrée expérience, `EXPERIENCE_MANUELLE` est défini. Mais **aucun collecteur** : pas de moyen d'enregistrer une session de navigation manuelle. Piste concrète : monter un site vitrine Arena accessible publiquement (faux site type portfolio), demander à la communauté de le parcourir, enregistrer les sessions comme `truth: "humain"`. |
| B2 | Profils de référence humains | MANQ | — | Aucun profil de référence défini. Pas de caractérisation de ce qu'est une session « normale ». |
| B3 | Distinction humain / automatisé / indéterminé | OK | `detection.py`, `database.py` | Colonne `truth` dans `runs` (`automatise` / `humain`). Chaque détecteur renvoie `classification` ∈ {automatise, humain, indetermine}. `_comptes()` gère les trois. |
| B4 | Matrices de confusion complètes | PART | `analytics.py` | Rappel, précision, F1 calculés dans `qualite`. FP mesurés sur sessions manuelles. Mais : (1) pas de matrice de confusion au sens propre (tableau 2×2) ; (2) spécificité non calculée ; (3) pas d'IC sur précision/rappel/F1 ; (4) la précision mélange VP de l'expérience et FP des sessions manuelles → définition discutable ; (5) sans données manuelles, tout est « n.m. ». |

---

## Phase C — Reproductibilité

| # | Exigence | État | Fichier(s) | Détail |
|---|----------|------|------------|--------|
| C1 | Config effective enregistrée par passage | OK | `passages.py`, `database.py` | `protection_config` (JSON complet) + `config_hash` (SHA-256 16 hex) enregistrés par run. Migration 4. Vérification dans `diagnostic.verifier_profils()`. |
| C2 | Variabilité contrôlée | PART | `campaigns.py` | Seed pour l'ordre des unités et des scénarios. Mais : (1) pas de mesure de variance inter-répétitions ; (2) pas de contrôle du warm-up navigateur (1er run ≠ suivants) ; (3) l'ordre des niveaux de protection dans une unité n'est pas randomisé. |
| C3 | Répéter entre campagnes indépendantes | PART | `analytics.py` | `comparer()` existe pour 2 expériences (Fisher + Holm-Bonferroni). Mais pas de mécanisme automatique pour lancer la même expérience 2 fois et évaluer la reproductibilité. |
| C4 | Identifier les dépendances d'observation | MANQ | — | Aucune analyse de dépendance : pas de test de corrélation entre répétitions consécutives, pas de vérification que l'ordre n'affecte pas les résultats. |
| C5 | Enregistrer toutes les versions | PART | `database.py`, `campaigns.py` | Versions moteur dans `engines`. Python + système dans `experiments.environment`. Versions des détecteurs dans `detections`. Mais : versions Arena/WAF/Coraza non enregistrées ; versions des dépendances (Playwright, Selenium, navigateur) pas explicites (partiellement dans `configuration`). |

---

## Phase D — Analyse et visualisation

| # | Exigence | État | Fichier(s) | Détail |
|---|----------|------|------------|--------|
| D1 | Matrice moteur × scénario × protection | PART | `analytics.py` | Groupements séparés : `moteurs`, `scenarios` (label×scenario), `par_protection`. Mais **pas de produit croisé** moteur × scénario × protection. Le dashboard ne montre pas cette vue 3D. |
| D2 | Taux conditionnels et globaux | PART | `analytics.py` | `bloc()` calcule réussite, erreur, blocage. Mais : pas de taux conditionnel (ex : réussite sachant non-bloqué) ; le taux global ne soustrait pas les erreurs techniques du dénominateur. |
| D3 | Couverture des détecteurs | PART | `diagnostic.py`, `analytics.py` | Taux de détection par détecteur par moteur. Ablation (quel détecteur est indispensable). Mais : pas d'analyse d'overlap (quel détecteur attrape ce qu'aucun autre n'attrape), pas de complémentarité quantifiée. |
| D4 | Distributions de latence | PART | `analytics.py` | `_resume()` : n, moyenne, médiane, p95, p99, max. Suffisant en stats. Mais : pas d'histogramme, pas de visualisation de la distribution (seulement des résumés chiffrés). |
| D5 | Mesure ressources / débit | OK | `campaigns.py`, `database.py` | `metrics` : cpu_usage, cpu_time_ms, memory_usage, memory_mean, navigation_time, request_count, error_count. Métriques collectées par `_passage()`. Limitation documentée (navigateur partagé). |
| D6 | Distinguer observé / estimé / limité | PART | `analytics.py` | `LIMITES` : 6 limitations textuelles. Mais : pas de tag par métrique (observé vs estimé), pas de flag « petit échantillon » sur les intervalles, pas de distinction systématique. |

---

## Phase E — Validation automatique

| # | Exigence | État | Fichier(s) | Détail |
|---|----------|------|------------|--------|
| E1 | Jeux de référence à résultats connus | MANQ | — | Aucun golden dataset avec résultats attendus connus. Les tests unitaires utilisent des données synthétiques mais sans vérifier des résultats de référence bout en bout. |
| E2 | Vérification automatique des dénominateurs | MANQ | — | Aucun test que total == Σ(par_issue). Aucun test que le dénominateur des taux est correct. |
| E3 | Sommes de catégories | MANQ | — | Pas de test d'additivité : la somme des issues par catégorie n'est pas vérifiée contre le total. |
| E4 | Validité des intervalles | MANQ | — | Aucun test que les IC Wilson satisfont : `0 ≤ bas ≤ taux ≤ haut ≤ 1`. Le calcul semble correct (clamp dans `wilson()`) mais non testé formellement. |
| E5 | Valeurs manquantes | PART | `analytics.py` | `wilson()` renvoie `None` si total == 0. `_resume()` filtre les `None`. Mais : pas de comptage systématique des valeurs manquantes, pas de flag « données insuffisantes ». |
| E6 | Reproductibilité par seed | PART | `tests/test_campagnes.py` | `test_meme_graine_meme_ordre` et `test_unites_seed_different_ordre_different` : l'ordre des unités est déterministe. Mais : l'ordre des scénarios par unité pas testé, pas de test bout-en-bout (même seed → mêmes résultats complets). |
| E7 | Stabilité des rapports | MANQ | — | Aucun test que les mêmes données produisent des rapports identiques à chaque exécution. |

---

## Résumé

| Phase | OK | DEF | PART | MANQ | Total |
|-------|----|----|------|------|-------|
| A — Audit et corrections | 2 | 3 | 2 | 1 | 8 |
| B — Références humaines | 1 | 0 | 1 | 2 | 4 |
| C — Reproductibilité | 1 | 0 | 3 | 1 | 5 |
| D — Analyse et visualisation | 1 | 0 | 4 | 0 | 5 |
| E — Validation automatique | 0 | 0 | 2 | 5 | 7 |
| **Total** | **5** | **3** | **12** | **9** | **29** |

## Priorités de correction

### Passe 1 — Bugs (DEF) → commit distinct
1. **A2a** `burst_crawl` : distinguer 429/403/5xx dans le comptage
2. **A2b** `fingerprint_observation` / `detection_page` : vérifier le contenu, pas seulement la présence
3. **A5** `analytics.bloc()` : taux de réussite et d'erreur basés sur `issue` au lieu de `status`

### Passe 2 — Validation (MANQ Phase E) → commit distinct
4. **E2+E3** Tests de réconciliation : Σ issues == total, dénominateurs corrects
5. **E4** Test de validité des IC Wilson
6. **E7** Test de stabilité des rapports
7. **A4** Corriger `comparer()` : conserver les effectifs exacts au lieu de recalculer par arrondi

### Passe 3 — Références humaines (Phase B) → commit distinct
8. **B1** Collecteur de sessions humaines (endpoint + middleware + CLI)
9. **B2** Profils de référence (caractérisation navigateur/OS/résolution)
10. **B4** Matrice de confusion propre avec IC sur toutes les métriques

### Passe 4 — Reproductibilité (Phase C) → commit distinct
11. **C2** Contrôle du warm-up, randomisation des niveaux
12. **C4** Analyse de dépendance inter-répétitions
13. **C5** Enregistrement complet des versions (Arena, WAF, navigateur)

### Passe 5 — Analyse (Phase D) → commit distinct
14. **D1** Matrice croisée moteur × scénario × protection
15. **D2** Taux conditionnels (réussite | non-bloqué)
16. **D6** Tags par métrique (observé/estimé/limité)

### Passe 6 — Jeux de référence (E1) → commit distinct
17. **E1** Golden dataset avec résultats attendus
18. **E6** Test de reproductibilité bout-en-bout par seed
