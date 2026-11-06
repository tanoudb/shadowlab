# Audit campagne #17 — résultats et défauts structurels

Date : 2026-11-05
Campagne : #17 (4 200 passages, seed 20261105, concurrency 1)
Moteurs : camoufox, scrapling-furtif, patchright, playwright, selenium, httpx, curl-cffi
Niveaux : 01–06, corrections F1 + F2 + F8 appliquées

## 1. Vérification structurelle ✓

- 42 cellules (7 moteurs × 6 niveaux), chacune avec exactement 100 passages (10 scénarios × 10 répétitions).
- Aucun passage manquant, aucune répétition dupliquée.
- Toutes les cellules complètes (`status = termine`).

## 2. Résultats bruts

```
                 Niv 01   Niv 02   Niv 03   Niv 04   Niv 05   Niv 06
camoufox          100%     100%      80%      80%       0%       0%
scrapling-furtif  100%     100%      80%      80%       0%       0%
patchright        100%       0%       0%       0%       0%       0%
playwright        100%       0%       0%       0%       0%       0%
selenium           90%       0%       0%       0%       0%       0%
httpx              60%       0%       0%       0%       0%       0%
curl-cffi          60%       0%       0%       0%       0%       0%
```

## 3. Défauts trouvés

### D1 — Bug de classification des challenges (code, sévère)

`issues.py:21` : `COUCHES_CHALLENGE = ("captcha", "defi-js")` — **Turnstile et reCAPTCHA sont absents**.

Conséquence : 180/200 passages de camoufox et scrapling-furtif sur niveaux 05-06 sont classés
`echec_fonctionnel` au lieu de `challenge_non_valide`. Le moteur reçoit la page de challenge
Turnstile (HTTP 200) mais ne peut pas interagir avec le widget. L'issue devrait être
`challenge_non_valide`, pas `echec_fonctionnel`.

Les 20 restants sont `bloque` (rate limit 429 sur `burst_crawl`).

### D2 — Chaîne de blocage séquentielle occulte les détecteurs JS (structurel, sévère)

5 moteurs sur 7 (patchright, playwright, selenium, httpx, curl-cffi) sont bloqués par
`regles-http` dès le niveau 02. Les détecteurs JS (botd, regles-js, coherence, comportement)
apparaissent en `abstentions` — ils ne sont **jamais exécutés** pour ces moteurs.

Impact :
- F1 (comportement) n'est testée que contre 2/7 moteurs
- F2 (canvas_erreur) ne se déclenche jamais (0 occurrences sur 4 200 passages)
- F8 (CDP globals) attrape selenium (`cdc_*`, 90 détections) mais sans impact additionnel
  (selenium est déjà bloqué par regles-http)

### D3 — Biais de conception des scénarios (méthodologique, modéré)

8 scénarios sur 10 sont mono-page. Le détecteur comportemental (F1) ne se déclenche que sur
les patterns multi-requêtes. Résultat : le « 80 % » de camoufox/scrapling-furtif signifie
« 8 scénarios sur 10 sont invisibles au seul détecteur qui fonctionne ».

Scénarios multi-pages : `burst_crawl` (30 requêtes), `pagination` (5 pages).
Tous les autres : 1 seule requête → aucun pattern comportemental détectable.

### D4 — Identité camoufox = scrapling-furtif (méthodologique)

Les deux moteurs ont des résultats **strictement identiques** scénario par scénario :
- burst_crawl : 0/10 pour les deux (niveaux 03-04)
- pagination : 0/10 pour les deux
- 8 autres scénarios : 10/10 pour les deux

Ceci alors qu'ils diffèrent profondément :
- Navigateur : Firefox (camoufox) vs Chrome (scrapling-furtif)
- Canvas : randomisé par session (camoufox) vs fixe `cda43037` (scrapling-furtif)
- Signaux comportement : 25 `automatise` (camoufox) vs 50 (scrapling-furtif) sur niveau 03

L'identité de résultats n'indique pas des moteurs équivalents — elle indique que le banc
de mesure ne discrimine pas. La détection comportementale produit un résultat binaire
(multi-page → bloqué, mono-page → invisible) indépendant du moteur.

### D5 — F2 (canvas_erreur) est du code mort en pratique

Aucun déclenchement sur 4 200 passages. Les moteurs avec navigateur rendent un canvas valide.
Les clients HTTP (httpx, curl-cffi) n'exécutent pas JavaScript, donc aucune observation JS
collectée → le signal ne peut pas se déclencher.

### D6 — F8 (CDP globals) sans valeur incrémentale

Attrape uniquement selenium (globals `cdc_*`), déjà bloqué par regles-http. Les moteurs
anti-détection (camoufox, scrapling-furtif, patchright) cachent tous les globals CDP.
Sur les moteurs anti-détection, `automation` rapporte tout à `false`.

### D7 — Absence de mesure de faux positifs

`analytics.py` prévoit des sessions manuelles (constante `EXPERIENCE_MANUELLE`) mais
aucune n'existe. Le taux de faux positifs est **non mesuré** : on ne sait pas si le
détecteur comportemental bloquerait un humain qui parcourt rapidement le catalogue.

### D8 — Limites d'environnement

- IP unique (localhost) : la réputation IP est sans objet.
- Concurrency 1 : pas de pression concurrente, le rate limiter ne voit qu'un flux.
- Test keys CAPTCHA : le « passage » de Turnstile/reCAPTCHA n'est pas un contournement réel
  (déjà documenté dans AGENTS.md, respecté dans les rapports).
- Pas de versionnement moteur : impossible de tracer un résultat à une version précise.

## 4. Bilan de l'impact des corrections F1/F2/F8

| Correction | Détecte | Bloque | Impact mesurable |
|------------|---------|--------|------------------|
| **F1 (comportement dans REGLES_JAVASCRIPT)** | burst_crawl + pagination sur camoufox/scrapling-furtif | Oui (−20 pp sur niveaux 03-04) | **Seul impact réel** |
| F2 (canvas_erreur) | Rien | Non | Zéro (tous les canvas sont valides) |
| F8 (CDP globals) | selenium (cdc_*) | Non additionnel | selenium déjà bloqué avant |

## 5. Composants réutilisables pour v0.7

| Composant | Lignes | Verdict | Notes |
|-----------|--------|---------|-------|
| `campaigns.py` | 642 | **Garder, étendre** | Matrice, spawn, graine, reprise : solide |
| `analytics.py` | 701 | **Garder, étendre** | Wilson, quantiles : solide. Ajouter ablation, comparaison |
| `database.py` | 285 | **Garder, étendre** | Migrations : solide. Étendre le schéma |
| `detection.py` | 373 | **Garder, étendre** | 6 détecteurs, modèle Signal : bon. Ajouter versionnement |
| `issues.py` | 87 | **Corriger** | Bug COUCHES_CHALLENGE, raffiner classification |
| `scenarios.py` | 249 | **Étendre** | Ajouter des scénarios multi-pages |
| `gardien.py` | 174 | **Garder** | Chaîne séquentielle correcte par design |
| `api.py` | 670 | **Garder, étendre** | Ajouter endpoints comparaison/ablation |
| `reports.py` | 324 | **Garder, étendre** | Ajouter rapports comparatifs |
| `frontend/` | — | **Garder, étendre** | Dashboard solide, ajouter vues comparatives |
| `observateur.js` | 187 | **Garder** | Collecte JS correcte |
| Tests | 193 | **Étendre** | Bonne couverture, suivre les ajouts |
