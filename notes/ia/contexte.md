---
permalink: noezia-shadowlab/contexte
title: contexte
type: note
---

# Contexte de noezia-shadowlab, en une lecture

## Ce que c'est
- Le produit visé est le **moteur de scraping NOEZIA**. ShadowLab est le laboratoire qui le mesure :
  15 moteurs comparés face à une Arena anti-bot locale (7 niveaux, 42 détecteurs), campagnes reproductibles.
- Périmètre : voir `AGENTS.md` § Périmètre (D-30). Aucun solveur de CAPTCHA réel, aucun résultat inventé.

## Objectif (validé par Ethan le 2026-11-11, D-54)
Un moteur de récolte généraliste qui, lancé depuis un serveur Linux, mène un long travail sur un site
protégé sans se faire bannir, et rapporte des données complètes et exactes. Il se prouve par des mesures
sur nos propres cibles (site vitrine factice, tor-i).

## État au 2026-11-12 (11 h)
- **Plan de travail unique : `docs/PLAN.md`** (objectif, état mesuré, quatre paliers, règles, suivi au § 8).
  Le lire d'abord. Constats détaillés du 11/11 : `notes/ia/analyse-paliers-2026-11-11.md`.
- Palier 1 : étapes 1.1 à 1.5 faites, 1.6 codée (application publique ; mise en ligne par Ethan, script
  `scripts/site-public-tunnel.sh`), 1.7 outillée (`uv run shadowlab rejeu`, D-56) mais sans session humaine.
  605 tests rapides verts, branche `niveau-authentifie-perimetre` poussée, rien sur `master`.
- Mesuré (campagnes 90, 92, 94) : NOEZIA passe et récolte 100 % aux niveaux 01 à 03. Aux niveaux 04 à 07 le
  détecteur `cdp` refuse tous les moteurs ; sans lui, NOEZIA passe 15/15 au 04, 12/15 au 05, 2/15 au 06 et
  0/15 au 07, les témoins 0 partout.
- **Défaut du moteur le plus grave connu** : « HeadlessChrome » visible sur 16 % de ses requêtes, version
  annoncée contradictoire, une dizaine d'écarts d'empreinte. La base du moteur (Patchright) recommande un
  vrai Chrome avec interface sans identité réécrite : à mesurer (`configs/experiments/ablation-interface.yaml`).
- Défauts de l'Arena soupçonnés d'arrêter aussi les humains : `cdp`, `pas_de_scroll`, `pas_de_pause`,
  corrélation entre sessions, WAF du niveau 07 sur Turnstile. Les sessions humaines trancheront.
- Branches locales préparées, non fusionnées : `formulaire-contact` (D-57, accord d'Ethan pour fusionner
  après tests) et `moteur-version-reelle` (D-58, en attente). Dossiers `../noezia-shadowlab-formulaire` et
  `../noezia-shadowlab-moteur` : à retirer dès que leur branche est fusionnée ou abandonnée.
- Manquent pour l'objectif : les sessions humaines et le calibrage de l'Arena, le bannissement dans
  l'Arena, une identité persistante puis plusieurs identités dans le moteur, l'exécution sur un serveur
  Linux, un test contre Cloudflare.

## Prochaine action (12/11, après la récolte 95 qui finit vers 13 h 10)
Dans l'ordre, sans campagne en cours pour les étapes 1 à 5 :
1. Lire la récolte 95 (complétude, exactitude, durée) et l'écrire au § 2 du plan.
2. Formulaire de contact : dans `../noezia-shadowlab-formulaire`, voir les tests échouer sur `5a915a1`, passer
   sur la tête de `formulaire-contact` ; suite rapide et lint ; regarder `/contact` à l'écran ; fusionner dans
   `niveau-authentifie-perimetre`, pousser, retirer le dossier. Prévenir Ethan (il lance le tunnel).
3. WAF du niveau 07 : `uv run pytest tests/test_arena_waf.py` (échec attendu), exclusion de la règle 942432
   sur `/lab/(turnstile|recaptcha)/verifier` dans `docker/arena/coraza/main.go`, `uv run shadowlab arena
   demarrer --reconstruire`, test vert, puis `configs/experiments/controle-waf-07.yaml` (profils
   supplémentaires à appliquer avant, à retirer après).
4. Identité native (`../noezia-shadowlab-moteur`, branche `moteur-identite-native`, D-59) : tests rouges sur
   `d052c92`, verts sur la tête ; fusionner (option sans effet par défaut).
5. Suite complète (`uv run pytest`), lint.
6. Campagne de référence (`reference-palier1.yaml`, 1 h 50), puis `ablation-interface.yaml` (210 passages,
   fenêtres à l'écran). Lecture : script `lire_campagne.py` du dossier temporaire de la session, sinon requêtes.
7. Plan (§ 2, § 8), journal, pousser. **Site libre à 20 h** : aucune campagne ni `shadowlab site` en cours.
8. Ce soir, après les 5 sessions d'Ethan : `uv run shadowlab rejeu`, puis comparer ses en-têtes et son
   empreinte à ceux de NOEZIA (candidats listés au § 2 du plan).

Branche `moteur-version-reelle` (D-58) : gardée de côté, à trancher après la campagne « interface ».
Ce qu'on attend d'Ethan : `docs/PLAN.md` § 7 et `notes/ia/questions-ouvertes.md`.
