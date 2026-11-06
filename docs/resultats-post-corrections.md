# Résultats post-corrections — campagne #17

## Corrections appliquées

| # | Faiblesse | Correction | Fichiers |
|---|-----------|-----------|----------|
| F1 | `comportement` détecte mais ne bloque pas | Ajouté à `REGLES_JAVASCRIPT` | `gardien.py:39` |
| F2 | Canvas collecté mais inexploité | Signal `canvas_erreur` dans regles-js v2 | `detection.py` |
| F8 | Globals CDP non vérifiés | Collecte automation + 6 signaux CDP | `observateur.js`, `detection.py` |

## Résultats comparatifs (avant → après)

```
                 Niveau 01   Niveau 02   Niveau 03   Niveau 04   Niveau 05   Niveau 06
                 ---------   ---------   ---------   ---------   ---------   ---------
camoufox         100→100     100→100     100→ 80 ▼   100→ 80 ▼     0→  0       0→  0
scrapling-furtif 100→100     100→100     100→ 80 ▼   100→ 80 ▼     0→  0       0→  0
patchright       100→100       0→  0       0→  0       0→  0       0→  0       0→  0
playwright       100→100       0→  0       0→  0       0→  0       0→  0       0→  0
selenium            —→ 90       —→  0       —→  0       —→  0       —→  0       —→  0
httpx            100→ 60       0→  0       0→  0       0→  0       0→  0       0→  0
curl-cffi           —→ 60       —→  0       —→  0       —→  0       —→  0       —→  0
```

▼ = correction effective (−20 points de pourcentage)

## Ce qui bloque (niveaux 03-04, anti-détection)

| Scénario | Résultat | Signaux |
|----------|:--------:|---------|
| burst_crawl | **0/10** | rythme_soutenu (6-21 p/s), pages_eclair, aucune_interaction |
| pagination | **0/10** | pages_eclair, aucune_interaction |
| static_html | 10/10 | une seule page → pas de pattern comportemental |
| javascript_content | 10/10 | idem |
| form_interaction | 10/10 | idem |
| session_cookies | 10/10 | idem |
| fingerprint_observation | 10/10 | idem |
| detection_page | 10/10 | idem |
| api_json | 10/10 | idem |
| synthetic_browse | 10/10 | idem |

## Bilan par correction

| Correction | Impact | Explication |
|------------|--------|-------------|
| **F1 (comportement)** | **−20pp sur 03-04** | Seule correction à effet mesurable. Bloque les patterns multi-requêtes rapides. |
| F2 (canvas) | Aucun | Tous les moteurs rendent un canvas valide (navigateur réel). |
| F8 (CDP) | Aucun additionnel | Détecte selenium (globals `cdc_*`), mais les anti-détection cachent déjà tout. |

## Conclusion

Les protections passent de « scores parfaits distribués gratuitement » à « 80% pour les
anti-détection sur les niveaux 03-04 ». C'est un progrès : le laboratoire mesure maintenant
une réalité (le détecteur comportemental attrape les rafales). Mais 8 scénarios sur 10
passent encore intacts — le détecteur comportemental est réactif (il faut des données
accumulées) et les moteurs anti-détection cachent tous les signaux JavaScript que F8 cherche.

**Prochaines pistes** : corrélation temporelle intra-session, fingerprinting passif renforcé
(hash canvas/WebGL entre sessions), détection proactive dès la première page.
