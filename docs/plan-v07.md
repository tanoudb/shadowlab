# Plan technique — ShadowLab v0.7

Fiabilité scientifique et laboratoire adversarial.
Base : audit de la campagne #17 (`docs/audit-campagne-17.md`).

**Contexte** : ShadowLab est le laboratoire scientifique qui servira à développer le moteur
NOEZIA Scraping Engine (Core, Browser Engine, Extraction Engine, Intelligence, Observatory).
La v0.7 prépare cette architecture future en rendant le laboratoire fiable : chaque mesure
reproductible, chaque résultat correctement classifié, chaque conclusion statistiquement fondée.
On ne construit rien de nouveau tant que la base existante ment.

Principe directeur : **rigueur d'abord**. Pas de résultats artificiellement impressionnants.
Performance démontrée objectivement, avec des limites explicites. Chaque capacité nouvelle
produit un gain mesurable et reproductible.

---

## Cadre méthodologique (transverse à toutes les phases)

### Dimensionnement statistique

**Taille d'échantillon justifiée.** La largeur d'un intervalle de Wilson à 95 % pour une
proportion p avec n observations est environ `2 × 1.96 × √(p(1−p)/n)`. Objectifs :

| Précision souhaitée (demi-largeur IC) | n minimum (cas p = 0.5) | Cas actuel (n = 10) |
|----------------------------------------|-------------------------|---------------------|
| ±5 pp | 385 | IC ≈ ±31 pp |
| ±10 pp | 96 | — |
| ±15 pp | 43 | — |

**Règle** : minimum **30 répétitions** par cellule (moteur × niveau × scénario) pour les
campagnes de référence (IC ≤ ±18 pp au pire). Campagnes exploratoires : 10 reps acceptables
si étiquetées « exploratoire, IC large ».

**Critère d'arrêt** : une campagne peut s'arrêter tôt si pour chaque cellule l'IC à 95 %
est inférieur à un seuil configuré (par défaut ±10 pp) — ou si le nombre maximal de
répétitions est atteint.

### Correction des comparaisons multiples

Comparer 2 campagnes sur k cellules → k tests simultanés.
- **Holm-Bonferroni** (séquentiel, plus puissant que Bonferroni) : trier les p-values, rejeter
  tant que p_i < α / (k − i + 1). Implémenté dans `analytics.py`.
- Rapporter systématiquement les p-values brutes ET corrigées.
- Avec 42 cellules (7 moteurs × 6 niveaux) et α = 0.05, le seuil le plus strict est
  0.05/42 ≈ 0.0012.

### Intervalles de confiance systématiques

Toute proportion rapportée (taux de succès, détection, blocage, faux positif) est accompagnée
de son IC Wilson à 95 %. L'API, les rapports et le dashboard affichent les bornes.
Un résultat dont l'IC chevauche zéro ou un est signalé comme « non conclusif ».

### Faux positifs — protocole multi-sessions

Pas une seule session manuelle. Protocole :

1. **Minimum 5 sessions humaines indépendantes** par niveau, avec des profils variés :
   - Navigation lente (lecture, pauses de 5-10 s)
   - Navigation rapide (clic-clic, < 1 s entre pages)
   - Navigation ciblée (formulaire, puis sortie)
   - Exploration libre (aller-retour, retour arrière)
   - Session longue (30+ pages sur 10 min)
2. Chaque session enregistre les mêmes métriques qu'un passage automatisé.
3. Taux de faux positifs = passages humains classés `automatise` ou bloqués, avec IC Wilson.
4. Si le FP dépasse 5 % sur un niveau → le détecteur a un problème, documenter et corriger
   avant de continuer.

### Ablation — individuelle ET interactions

Deux modes distincts :

1. **Ablation individuelle** : chaque protection activée seule (6 expériences). Mesure l'effet
   propre de chaque couche, sans masquage par la chaîne séquentielle.
2. **Ablation par paires** : combinaisons de 2 protections (C(6,2) = 15 expériences). Mesure
   les interactions : si détection(A+B) > détection(A) + détection(B), il y a synergie.
   Design factoriel complet sur les paires les plus prometteuses (identifiées par l'ablation
   individuelle).

L'ablation factorielle complète (2^6 = 64 combinaisons) n'est pas justifiée au départ.
La construire progressivement, guidée par les résultats individuels et par paires.

---

## Benchmarks NOEZIA (préparés dès v0.7)

Métriques de référence pour évaluer le futur moteur. Collectées dès maintenant sur les
moteurs existants, elles constitueront la baseline.

| Dimension | Métrique | Collecte | Source actuelle |
|-----------|----------|----------|-----------------|
| **Discrétion** | Taux de succès par niveau | Existant | `runs.success` |
| **Discrétion** | Taux de détection (sans blocage) | P0.2 | `drapeaux.detecte_par` |
| **Latence** | Durée médiane et p95 par passage | Existant | `runs.duration_ms` |
| **Débit** | Pages/seconde par moteur | À calculer | `duration_ms / nb_requetes` |
| **Mémoire** | Pic mémoire par passage (RSS) | Existant | `metrics` (Echantillonneur) |
| **CPU** | CPU-secondes par passage | Existant | `metrics` |
| **Coût** | CPU-s par extraction réussie | P0.2 | `duration_ms × cpu / succès` |
| **Qualité extraction** | Précision des données extraites vs vérité terrain | P1.3 | Scénarios avec contenu attendu |
| **Robustesse** | Taux de succès après mutation du site | P3 (futur) | Pas encore implémenté |

**Rapport benchmark** : à chaque campagne de référence, un rapport automatique classe les
moteurs sur ces dimensions. Ce rapport sera le standard de comparaison pour le moteur NOEZIA.

---

## Schéma de données versionné et contrats d'interface

### Versionement du schéma

Chaque modification du schéma de données (tables, colonnes, format JSON des drapeaux) est :
1. Numérotée (migration incrémentale dans `database.MIGRATIONS`).
2. Documentée (champ ajouté, type, valeur par défaut, raison).
3. Testée (test de validation qui vérifie la structure).

Le numéro de schéma est enregistré dans chaque expérience (`schema_version` dans `experiments`).

### Contrats d'interface testés

Trois contrats stabilisés en v0.7, chacun validé par un test :

1. **Contrat passage** : structure JSON de `drapeaux` (P2.1). Test : `test_contrat_drapeaux`
   vérifie que chaque passage produit les champs requis au bon type.
2. **Contrat configuration moteur** : structure JSON de la config sérialisée (P2.3). Test :
   `test_contrat_config_moteur` vérifie la présence de `engine_name`, `engine_version`,
   `browser_version`, `options`.
3. **Contrat comparaison** : structure de sortie de l'API `/api/comparaison` (P1.2). Test :
   `test_contrat_comparaison` vérifie les champs `cellules`, `p_values`, `corrections`.

Un contrat cassé = test rouge = la PR ne passe pas.

---

## Critères d'acceptation par phase

### P0 — Corriger ce qui fausse les résultats

| Critère | Mesure | Seuil |
|---------|--------|-------|
| Classification Turnstile correcte | Campagne de test sur niveaux 05-06 : issues `challenge_non_valide` au lieu de `echec_fonctionnel` | 100 % des passages Turnstile non validés classés correctement |
| Métriques séparées | L'API `/api/experiences/{id}/statistiques` retourne succès, détection, challenge, blocage séparément | 4 taux distincts avec IC Wilson |
| Versionnement | Chaque run a `engine_version` non vide, chaque détection a `detector_version` | 0 valeur nulle sur une campagne complète |
| Non-régression | `uv run pytest` + `npm --prefix frontend test` passent | 0 test cassé |

### P1 — Rigueur méthodologique

| Critère | Mesure | Seuil |
|---------|--------|-------|
| Ablation individuelle | 6 campagnes (une par protection), résultats comparés au baseline | Chaque protection a un profil de détection distinct et documenté |
| Comparaison automatisée | `shadowlab comparer A B` produit un rapport avec p-values corrigées | Test Fisher + Holm-Bonferroni sur toutes les cellules |
| Scénarios multi-pages | ≥ 4 nouveaux scénarios multi-pages avec profils comportementaux variés | Le détecteur comportemental est testé par ≥ 6 scénarios (2 existants + 4 nouveaux) |
| Faux positifs | ≥ 5 sessions humaines indépendantes par niveau | FPR < 5 % par niveau, avec IC Wilson |
| Non-régression | Tous les tests existants passent + tests ajoutés pour les nouvelles fonctions | 0 test cassé |

### P2 — Instrumentation avancée

| Critère | Mesure | Seuil |
|---------|--------|-------|
| Décisions par couche | Chaque passage enregistre la décision de chaque couche traversée | Test `test_contrat_drapeaux` passe |
| First detection | `first_detection_at` renseigné pour chaque détection | 0 valeur nulle |
| Config complète | Chaque run a sa config moteur sérialisée | Test `test_contrat_config_moteur` passe |
| Benchmark automatique | Rapport benchmark produit à chaque campagne de référence | Toutes les dimensions du tableau benchmark couvertes |
| Non-régression | Aucun test existant cassé | 0 régression |

---

## P0 — Corriger ce qui fausse les résultats

Sans ces corrections, toute campagne future produit des données inexploitables.

### P0.1 — Corriger COUCHES_CHALLENGE (bug D1)

**Quoi** : ajouter `"turnstile"` et `"recaptcha"` à `COUCHES_CHALLENGE` dans `issues.py:21`.

**Pourquoi** : 90 % des échecs niveaux 05-06 sont classés `echec_fonctionnel` au lieu de
`challenge_non_valide`. Cela fausse les statistiques de blocage et masque que Turnstile
fonctionne.

**Effort** : 1 ligne + 2 tests. Migration inutile (les drapeaux sont corrects dans la base,
seule l'issue finale est fausse).

### P0.2 — Séparer les métriques succès / détection / challenge / blocage

**Quoi** : dans `analytics.py`, calculer et rapporter séparément :
- Taux de succès (extraction réussie, comme aujourd'hui)
- Taux de détection (classé `automatise` par ≥1 détecteur)
- Taux de challenge (challenge émis, qu'il soit validé ou non)
- Taux de blocage effectif (issue = `bloque`)
- Taux de challenge non validé (issue = `challenge_non_valide`)

**Pourquoi** : aujourd'hui on ne voit que succès/échec. Un moteur peut être détecté sans être
bloqué (camoufox sur 02 : `comportement` détecte 23 % mais ne bloque rien). Distinguer
absence de détection, détection sans blocage, et blocage effectif.

**Effort** : ~80 lignes dans analytics.py, API et frontend.

### P0.3 — Versionnement des détecteurs et moteurs

**Quoi** : enregistrer dans chaque détection la version du détecteur (`regles-js` a déjà "2"),
et dans chaque run la version du moteur (extraite de son package ou rapportée par `version()`).

**Pourquoi** : impossible de comparer deux campagnes si on ne sait pas quelle version du code
a produit les résultats.

**Effort** : migration DB (1 colonne `detector_version` sur `detections`, 1 `engine_version`
sur `runs`), ~30 lignes.

## P1 — Rigueur méthodologique

Prérequis : P0 terminé.

### P1.1 — Ablation automatisée (individuelle + interactions)

**Quoi** : deux modes de campagne :

```yaml
# Mode 1 : ablation individuelle (chaque protection seule)
mode: ablation
protections_isolees: [regles-http, tls, regles-js, botd, coherence, comportement]

# Mode 2 : ablation par paires (combinaisons de 2)
mode: ablation_paires
paires: [[regles-http, comportement], [regles-js, coherence], ...]
```

- **Individuelle** (6 expériences) : chaque protection activée seule. Mesure l'effet propre.
- **Par paires** (sélection guidée par les résultats individuels) : mesure les interactions.
  Si détection(A+B) > détection(A) + détection(B), il y a synergie.

**Pourquoi** : la chaîne séquentielle (D2) empêche de mesurer l'effet de chaque couche.
Les interactions entre protections sont aussi importantes que leurs effets isolés.

**Réutilisation** : `campaigns.py` gère déjà des matrices moteur × protection. Il suffit
d'ajouter un mode qui itère sur les protections individuelles/paires au lieu des niveaux.

**Effort** : ~150 lignes dans campaigns.py, adaptation de la config Arena.

### P1.2 — Comparaison avant/après automatisée

**Quoi** : endpoint API et commande CLI `shadowlab comparer <campagne_A> <campagne_B>` qui
produit :
- Différence de taux de succès par cellule avec intervalles de confiance
- Test d'hypothèse (Fisher exact ou chi²) pour chaque cellule
- Matrice de changement (amélioration / régression / stable)

**Pourquoi** : la comparaison campagne #15/16 vs #17 a été faite à la main. Chaque cycle
d'amélioration doit pouvoir se comparer automatiquement.

**Réutilisation** : `analytics.py` a déjà Wilson. Ajouter le test de Fisher et la logique
de comparaison.

**Effort** : ~120 lignes analytics, ~60 lignes API, ~40 lignes CLI.

### P1.3 — Plus de scénarios multi-pages

**Quoi** : ajouter 3–4 scénarios multi-pages pour tester le détecteur comportemental :
- `navigation_lente` : 5 pages avec délais humains (2–5 s entre chaque)
- `exploration_aleatoire` : visite aléatoire de 8 pages parmi les disponibles
- `session_profonde` : login → catalogue → détail → formulaire → confirmation (5 étapes)
- `crawl_progressif` : 10 pages avec accélération progressive (teste le seuil)

**Pourquoi** : 8/10 scénarios actuels sont mono-page (D3). Le détecteur comportemental est
le seul efficace contre les anti-détection, mais il n'est testé que par 2 scénarios
(burst_crawl et pagination), les deux étant des cas extrêmes (très rapide).

**Effort** : ~150 lignes dans scenarios.py, ajout des pages nécessaires dans site/.

### P1.4 — Mesure des faux positifs (protocole multi-sessions)

**Quoi** : commande `shadowlab session-manuelle --profil <nom>` qui enregistre une session
humaine. Protocole complet (cf. cadre méthodologique) : minimum 5 sessions indépendantes par
niveau, 5 profils de navigation :
- `lente` : lecture, pauses 5-10 s
- `rapide` : clic-clic, < 1 s entre pages
- `ciblee` : formulaire puis sortie
- `exploration` : aller-retour, retour arrière
- `longue` : 30+ pages sur 10 min

**Pourquoi** : sans baseline multi-profils, on ne sait pas si le détecteur comportemental
bloquerait un humain rapide ou un humain qui explore (D7). Un seul profil ne suffit pas.

**Seuil d'acceptation** : FPR < 5 % par niveau, avec IC Wilson. Si dépassé, corriger le
détecteur avant de continuer les mesures.

**Réutilisation** : `passages.py` et `database.py` supportent déjà les sessions manuelles.
Il manque le point d'entrée CLI et le système de profils.

**Effort** : ~100 lignes CLI + instructions pour le protocole.

## P2 — Instrumentation avancée

Prérequis : P0 + P1 terminés.

### P2.1 — Enregistrement par couche (pas seulement la décision finale)

**Quoi** : pour chaque passage, enregistrer la décision de CHAQUE couche de protection,
même si elle ne bloque pas. Aujourd'hui `drapeaux` enregistre les blocages et détections,
mais pas les « passe » intermédiaires.

Structure enrichie dans `drapeaux` :
```json
{
  "couches": [
    {"nom": "regles-http", "decision": "passe", "motifs": []},
    {"nom": "tls", "decision": "passe", "motifs": []},
    {"nom": "fingerprinting", "decision": "bloque", "motifs": ["regles-js:automatise"]}
  ]
}
```

**Pourquoi** : permet de voir quelles couches sont traversées silencieusement et lesquelles
sont proches du seuil de blocage.

**Effort** : ~80 lignes dans gardien.py + migration DB.

### P2.2 — Moment exact de première détection

**Quoi** : enregistrer le timestamp de la première détection (pas seulement le résultat final).
Permet de savoir si la détection est immédiate (1re requête) ou progressive.

**Effort** : ~40 lignes, champ `first_detection_at` dans la table detections.

### P2.3 — Enregistrement configuration moteur complète

**Quoi** : sérialiser la configuration complète du moteur (`configuration()` + `options_permises`)
dans chaque run. Inclure la version du navigateur sous-jacent.

**Pourquoi** : reproductibilité totale — savoir exactement quelle configuration a produit
chaque résultat.

**Effort** : ~30 lignes, champ JSON dans runs.

## P3 — Expérimentation adversariale

Prérequis : P0 + P1 + P2 terminés (les outils de mesure doivent être fiables avant de
tester des hypothèses adversariales).

### P3.1 — Cohérence d'empreinte

**Quoi** : campagne spécialisée qui compare l'empreinte JS (user-agent, platform, canvas,
WebGL) avec les en-têtes HTTP. Mesure du taux de cohérence par moteur.

Exemple : camoufox envoie `Firefox/158.0` en User-Agent mais rapporte `Win32` en
`navigator.platform` sur macOS — est-ce cohérent avec un Firefox Windows ?

### P3.2 — Stabilité de session

**Quoi** : campagne qui mesure si l'empreinte reste stable entre requêtes d'une même session.
Camoufox randomise le canvas par session — change-t-il entre pages ?

### P3.3 — Interaction cumulative des protections

**Quoi** : campagnes avec combinaisons progressives de protections (pas seulement les niveaux
prédéfinis). Mesurer si la combinaison A+B détecte plus que A seul + B seul.

### P3.4 — Comportement humain simulé

**Quoi** : scénarios avec délais réalistes, mouvements de souris simulés, scrolls, clics
intermédiaires. Mesurer si le détecteur comportemental est contournable par simulation.

## Séquencement

```
Semaine 1 :  P0.1 + P0.2 + P0.3          (corrections, base fiable)
Semaine 2 :  P1.1 + P1.2                  (ablation, comparaison)
Semaine 3 :  P1.3 + P1.4                  (scénarios, faux positifs)
Semaine 4 :  Campagne de validation v0.7 + ablation complète
Semaine 5 :  P2.1 + P2.2 + P2.3          (instrumentation)
Semaine 6+ : P3.x                         (adversarial, selon résultats)
```

## Ce qui NE change PAS

- Architecture Arena (frontal TLS → Nginx → Coraza → FastAPI) : solide.
- Modèle `engines/base.Driver` + périmètre + verrou réseau : solide, critique pour la sécurité.
- 6 détecteurs existants : tous fonctionnels, à étendre pas remplacer.
- Frontend React + API REST : solide, à étendre.
- Graine + reproductibilité : déjà en place, testé (3 tests dédiés).
- 193 tests existants : tous verts, à compléter.

## Préparation de l'architecture NOEZIA

La v0.7 ne construit pas encore le moteur NOEZIA, mais elle pose les fondations :

| Composant NOEZIA | Ce que v0.7 prépare |
|-------------------|---------------------|
| **Observatory** | P0.2 (métriques séparées) + P2.1 (décisions par couche) + P2.2 (timestamps) → les données que Observatory consommera |
| **Browser Engine** | P1.1 (ablation) mesure chaque technique isolément → guide les choix d'architecture du moteur navigateur |
| **Core** | P0.3 (versionnement) + P2.3 (config complète) → traçabilité de bout en bout pour l'orchestrateur |
| **Intelligence** | P3.4 (comportement simulé) → premiers benchmarks pour l'agent adaptatif |
| **Extraction Engine** | P1.3 (scénarios variés) → benchmarks représentatifs pour évaluer l'extraction |
| **ShadowLab** | Tout P0-P2 → le laboratoire fiable qui validera chaque composant du moteur |

**Interfaces à stabiliser en v0.7** (pour que les futurs composants puissent s'y brancher) :
- Format de résultat d'un passage (drapeaux enrichis P2.1) → contrat Observatory
- Format de configuration moteur sérialisée (P2.3) → contrat Core ↔ Engine
- API de comparaison entre campagnes (P1.2) → contrat benchmarks reproductibles

## Décisions techniques à prendre

1. **Schéma de la table d'ablation** : table séparée ou réutilisation de `runs` avec un champ
   `mode` ? Recommandation : champ `mode` dans `experiments` (ablation vs standard).

2. **Stockage des versions moteur** : colonne texte ou table de référence ?
   Recommandation : colonne texte dans `runs` (simple, suffisant).

3. **Scénarios multi-pages** : combien de pages minimum pour déclencher le comportemental ?
   → À mesurer par ablation (P1.1) avant de fixer les scénarios (P1.3).

4. **Format des drapeaux enrichis (P2.1)** : doit être stable, car c'est le contrat de données
   entre ShadowLab et le futur Observatory. Figer le schéma JSON dans un test de validation.
