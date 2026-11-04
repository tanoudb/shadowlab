# ShadowLab v0.7 — Rapport d'audit adversarial

Date : 2026-11-04
Base : v0.6 (`ee52b8f`) → HEAD (`89697f0`), 15 commits atomiques.
Posture : auditeur technique adversarial. Aucune affirmation de validité non prouvée.

Convention de criticité : **CRITIQUE** (fausse une mesure / une conclusion), **MOYEN** (dégrade
la fiabilité), **FAIBLE** (hygiène). Labels : **CORRIGÉ**, **PARTIEL**, **INCOMPLÈTE**,
**NON DÉMONTRÉE**, **NON TESTÉ**.

---

## 1. Avertissement sur la portée

Les tests qui passent **ne prouvent pas** la validité scientifique. Ils prouvent que le code
fait ce que le test vérifie. Ce rapport distingue : (a) ce qui est corrigé et testé sur le
**vrai chemin d'exécution**, (b) ce qui reste une **hypothèse non démontrée**, (c) ce qui n'a
**pas été exécuté**.

---

## 2. Défauts confirmés et corrigés

### #4 — Statut du passage calculé avant le dépassement mémoire — CRITIQUE — CORRIGÉ
- **Cause** : [campaigns.py](src/shadowlab/campaigns.py), `_passage` — `statut` était calculé
  avant que `echantillon.depassement` ne soit intégré à `erreur`. Un passage `succes=True`
  dépassant le plafond était enregistré `status='reussi'` avec `success=0` et une erreur mémoire.
- **Reproduction** : `tests/test_audit_v07.py::TestStatutDepassementMemoire`. Test chemin-réel
  `test_chemin_reel_passage_depassement` : exécute le vrai `_passage()` avec plafond 1 Mo.
  **Vérifié rouge sur le code pré-correction** (`status='reussi'`), vert après.
- **Correction** : `_resultat_passage()` intègre le dépassement **avant** le calcul du statut ;
  un dépassement mémoire est une erreur technique (`status='erreur'`, `success=0`). Commits
  `dcb0e9f` (repro), `78d1b54` (fix), `7a5e975` (test chemin-réel).

### #3 — Vérification du serveur par connexion TCP sans identité — CRITIQUE — CORRIGÉ
- **Cause** : [campaigns.py](src/shadowlab/campaigns.py) `_repond()` ne faisait qu'un
  `socket.create_connection`. N'importe quel service sur le port était pris pour le site.
- **Reproduction** : `TestIdentiteServeur` — serveur HTTP étranger réel sur le port.
  Démontré : l'ancien critère `_repond` renvoie `True` pour l'étranger, le nouveau
  `_identite_site` renvoie `False` ; `serveur_local` lève désormais une erreur.
- **Correction** : endpoint signé `GET /lab/sante → {"service":"shadowlab-site"}`
  ([site/app.py](src/shadowlab/site/app.py)) ; `serveur_local` ne réutilise un serveur que si
  la signature correspond, et attend cette signature au démarrage. Commit `495c6a9`.
- **Limite** : la signature distingue le site ShadowLab d'un service tiers. Elle **ne protège
  pas** contre un serveur malveillant qui imiterait volontairement la signature (ce n'est pas un
  secret). Suffisant pour l'usage local prévu, pas un contrôle d'authenticité.

### #6 — Campagne « termine » malgré un moteur non démarré — MOYEN — CORRIGÉ
- **Cause** : un moteur dont `open()` échoue fait enregistrer tous ses passages en erreur
  « démarrage impossible » et `executer_unite` renvoie `termine` ; la campagne finissait `termine`.
- **Reproduction** : `TestCampagneMoteurAbsent` — vrai `executer()` avec un moteur dont `open()`
  lève. Rouge (`termine`) avant, vert (`termine_incomplet`) après. Commits `9b7288f`, `7769ceb`.
- **Correction** : `_degrader_si_moteur_absent()` rétrograde `termine → termine_incomplet` si un
  passage porte une erreur « démarrage impossible ». Le CLI renvoie alors un code de sortie ≠ 0.

### #1 — Matrice de confusion : populations non comparables — CRITIQUE — PARTIEL
- **Cause** : `matrice_confusion` combinait VP/FN (automatisés) et FP/VN tirés de **toutes** les
  sessions humaines, toutes protections et versions confondues. Sans session humaine appariée,
  `precision = VP/(VP+0) = 1.0` — score parfait artificiel.
- **Reproduction** : `TestMatriceConfusionComparabilite` (protections 06 vs 01 ; versions
  2.0.0 vs 1.0.0). Rouge avant (precision non nulle / clé absente), vert après. Commits
  `7bc932b`, `c3ae2e4`.
- **Correction** : FP/VN restreints aux protections de l'expérience ; exigence de **version de
  détecteur identique** entre populations ; `precision`/`f1` calculés **uniquement** si
  comparables, sinon `None` avec motif. `rappel` (TPR) et `taux_faux_positifs` (FPR) restent, car
  chacun est mesuré dans **une seule** population (indépendants de la prévalence).
- **PARTIEL / NON DÉMONTRÉE** : même appariés sur protection+version, precision/F1 **dépendent de
  la prévalence assemblée** (rapport n_auto/n_humain, choisi arbitrairement). Ils sont désormais
  étiquetés `prevalence_dependante: True` et **ne sont pas généralisables**. Restent **non
  contrôlés** : scénario, navigateur, moment de collecte. La comparabilité réelle des deux
  populations n'est donc **pas démontrée** ; precision/F1 ne doivent pas être lus comme une
  performance de détection généralisable.

### #5 — comparer() sans contrôle d'équivalence des designs — CRITIQUE — PARTIEL
- **Cause** : `comparer()` appliquait Fisher + Holm-Bonferroni sans vérifier que les deux
  expériences partageaient scénarios, protections et configurations de moteurs.
- **Reproduction** : `TestComparerDesignEquivalence` (protections 01 vs 06). Rouge avant
  (verdict `significatif` émis), vert après. Commits `399b86e`, `56f781b`.
- **Correction** : extraction du design depuis la configuration stockée ; refus par défaut si les
  designs diffèrent (`comparable: False` + `differences`, aucun verdict) ; `forcer=True` avec
  avertissement. CLI : refus explicite, code de sortie 2.
- **PARTIEL** : même à designs équivalents, le test **agrège un moteur sur toutes protections et
  scénarios** (risque de paradoxe de Simpson). La comparaison par cellule (moteur × protection ×
  scénario) **n'est pas faite** — documentée dans la docstring et ci-dessous.

### #7 — Autocorrélation lag-1 présentée comme preuve d'indépendance — MOYEN — PARTIEL
- **Cause** : docstring de `dependance_repetitions` affirmait qu'un lag-1 proche de 0 « indique
  l'indépendance ». Faux : compatible avec une dépendance d'ordre supérieur.
- **Reproduction** : `TestDependanceRepetitions` — exige un diagnostic complémentaire et une mise
  en garde ; cas périodique `(0,0,1,1)…` à lag-1 ≈ 0 non indépendant. Commits `223a7ab`, `63bf468`.
- **Correction** : reformulation (les diagnostics **révèlent** une dépendance, ne prouvent jamais
  l'indépendance) ; ajout du test des runs de Wald–Wolfowitz ; avertissement explicite dans le
  résumé ; entrée dédiée dans `LIMITES`.
- **NON DÉMONTRÉE** : l'indépendance effective des répétitions **n'est pas prouvée** et ne peut pas
  l'être par ces diagnostics. L'**isolation de session** a été vérifiée seulement en partie (voir
  §4) : httpx prouvé (client neuf par session), Playwright par conception (contexte neuf, non
  prouvé par test), Selenium **isolation la plus faible** (process partagé, nettoyage CDP des
  cookies/cache/stockage seulement).

### #2 — Scores de confiance fixes/heuristiques non calibrés — MOYEN — CORRIGÉ (labelling)
- **Cause** : `_verdict()` et `DetecteurBotD` attribuent une `confidence` = somme de poids
  plafonnée, ou constante (0.6 humain / 0.9 bot). Ce n'est pas une probabilité calibrée.
- **Vérification** : `confidence` n'alimente **aucun** calcul statistique (analytics n'utilise que
  `classification`). Garde comportemental `TestConfidenceNonCalibree` : deux expériences
  différant seulement par la `confidence` produisent des statistiques **identiques**. Commit `684ff49`.
- **Correction** : documentation au niveau du code et de `LIMITES`.
- **INCOMPLÈTE** : aucune **calibration empirique** n'a été faite (il n'existe pas de jeu étiqueté
  suffisant). La `confidence` reste un score heuristique d'affichage. **Calibration = NON FAITE.**

---

## 3. Phase 2 — Audit des autres modules

| Point | Verdict | Détail |
|---|---|---|
| Exception masquée dans `reports.passages_json` | **CORRIGÉ (FAIBLE)** | `except Exception: pass` resserré en `except sqlite3.OperationalError` (les colonnes existent après migration). Commit `076e12a`. |
| Concurrence SQLite | **NON-DÉFAUT** (suspicion infirmée) | WAL, `busy_timeout=30000`, `BEGIN IMMEDIATE`, une connexion par processus (`spawn`). Robuste par inspection. **NON stress-testé** sous forte contention. |
| Interruption / reprise | **PLAUSIBLE, NON TESTÉ exhaustivement** | `executer()` supprime les runs `en_cours` et `_deja_faits()` évite les doublons à la reprise. Logique cohérente par lecture ; pas de test de coupure réelle en milieu de campagne. |
| Résultat manquant compté comme réussite | **IDENTIFIÉ, NON CORRIGÉ** | Dans `_passage`, si la balise d'observation n'arrive pas (`wait_for_element("#observation-envoyee")` expire), le passage garde son `succes` : l'extraction peut être réussie alors que la **détection** s'appuie sur des observations incomplètes. La réussite d'extraction est légitime, mais la complétude de l'observation **n'est pas tracée**. À traiter (drapeau « observation incomplète »). |
| Fuites d'état entre répétitions | **PARTIEL** | httpx : prouvé isolé. Playwright : contexte neuf par session (par conception). Selenium : process partagé, isolation la plus faible. Voir §4. |
| Confinement de l'Arena / périmètre | **NON RÉ-AUDITÉ en profondeur** | Test de redirection hors périmètre existant (`test_integration`) passe pour les 4 moteurs. Audit dédié du périmètre non refait dans cette passe. |

---

## 4. Phase 3 — Validation d'intégration (chemins réels)

- **Suite unitaire** : `uv run pytest` → **187 passés**, lint `ruff` propre.
- **Suite d'intégration réelle** (`-m integration`, vrais navigateurs + site local) : **6 passés**
  en ~12 s. Inclut :
  - `test_campagne_complete_tous_moteurs` : campagne réelle de 16 passages (playwright, selenium,
    scrapling, httpx) sur le site réel — valide #3 (identité/`serveur_local`), #4 et #6 sur le vrai chemin.
  - `test_reproductibilite_bout_en_bout` (**ajouté**) : deux campagnes httpx identiques (même seed)
    produisent un plan **et** des résultats identiques bout en bout.
- **Arena (Coraza + Nginx) en campagne automatisée** : **NON TESTÉ**. Décision délibérée : démarrer
  la pile Docker dans la suite toucherait aux ports et à l'état partagé de la machine (cf. consignes
  machine). À exécuter manuellement : `uv run shadowlab arena demarrer` puis une campagne niveaux 02–06.
- **Isolation Playwright/Selenium par test** : **NON TESTÉ** directement (nécessite un vrai
  navigateur et une sonde d'état inter-session). Seul httpx a un test d'isolation.

---

## 5. Limites scientifiques encore présentes

1. **Précision / F1 non généralisables** (NON DÉMONTRÉE) : dépendent de la prévalence assemblée et
   de conditions non contrôlées (scénario, navigateur, moment). Ne pas les lire comme une
   performance de détection.
2. **Indépendance des répétitions non prouvée** (NON DÉMONTRÉE) : les diagnostics révèlent une
   dépendance, jamais l'absence. L'isolation Selenium est partielle.
3. **Comparaison d'expériences agrégée** (INCOMPLÈTE) : pas de comparaison par cellule → paradoxe
   de Simpson possible même à designs équivalents.
4. **Confiance des détecteurs non calibrée** (INCOMPLÈTE) : score heuristique, pas de probabilité.
5. **Détecteurs = repères locaux** : un taux de détection ici n'est pas la probabilité d'être
   repéré par un service externe (déjà dans `LIMITES`).
6. **Complétude des observations non tracée** : une détection peut reposer sur des observations
   partielles sans que ce soit signalé.

---

## 6. Risques résiduels classés

- **CRITIQUE** : lecture de `precision`/`f1` comme métrique généralisable malgré l'étiquette
  `prevalence_dependante` — risque d'interprétation. Atténué par le gating + l'étiquetage, pas éliminé.
- **CRITIQUE** : conclusions tirées d'une comparaison agrégée (Simpson) à designs équivalents.
- **MOYEN** : interprétation d'un lag-1 ≈ 0 comme indépendance ; isolation Selenium partielle.
- **MOYEN** : passages réussis avec observations incomplètes faussant les taux de détection.
- **FAIBLE** : signature `/lab/sante` imitable (pas un secret).

---

## 7. Commits (15)

```
dcb0e9f test: reproduce defect #4         78d1b54 fix: defect #4
223a7ab test: reproduce defect #7         63bf468 fix: defect #7
7bc932b test: reproduce defect #1         c3ae2e4 fix: defect #1
7a5e975 test: defect #4 real-path         399b86e test: reproduce defect #5
56f781b fix: defect #5                    495c6a9 fix: defect #3
9b7288f test: reproduce defect #6         7769ceb fix: defect #6
684ff49 fix: defect #2                    076e12a fix: reports except + httpx isolation
89697f0 test: end-to-end reproducibility (integration)
```

---

## 8. Prochaines priorités techniques

1. **Comparaison par cellule** (moteur × protection × scénario) dans `comparer()` pour éliminer le
   risque de Simpson ; agréger par Cochran–Mantel–Haenszel plutôt qu'un Fisher global.
2. **Tracer la complétude des observations** : drapeau « observation incomplète » sur un passage
   dont la balise n'est pas arrivée ; exclure ces passages des taux de détection ou les rapporter à part.
3. **Isolation Selenium** : redémarrer le navigateur par session, ou prouver l'absence de fuite par
   un test d'état inter-session ; test d'isolation pour Playwright.
4. **Intégration Arena automatisée** mais isolée (ports dédiés, pile jetable) pour couvrir les
   niveaux 02–06 sans toucher l'état de la machine.
5. **Test de coupure/reprise réelle** en milieu de campagne (tuer le processus, relancer, vérifier
   l'absence de doublon et la complétude).
6. **Calibration** (ou retrait) des scores de confiance, à partir d'un vrai jeu étiqueté.

---

## 9. Verdict de fiabilité (sans complaisance)

Sur les 7 points visés, 3 sont pleinement corrigés et testés sur le vrai chemin (#2 labelling, #3,
#4, #6), 3 sont **partiellement** corrigés avec limites explicites (#1, #5, #7). Le laboratoire est
**plus fiable** qu'en v0.6 sur ces points précis, mais **n'est pas** un instrument de mesure
scientifiquement clos : precision/F1 ne sont pas généralisables, l'indépendance des répétitions
n'est pas démontrée, et l'intégration Arena n'est pas testée automatiquement. Les mesures de
**rappel (TPR)**, **taux de faux positifs (FPR)**, **taux de réussite/blocage** et **ressources**
sont les plus solides ; tout ce qui combine deux populations (precision/F1) ou conclut à une
équivalence/indépendance doit être lu avec les réserves ci-dessus.
