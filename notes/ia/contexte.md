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

## Chantiers en parallèle (12/11, 11 h 50) — consigne d'Ethan : la session principale dirige, des sous-agents travaillent
Un dossier de travail git par chantier de code, à côté du dépôt. Rien n'y est testé tant qu'une campagne tourne.

| Chantier | Branche (dossier) | Qui | État |
|----------|-------------------|-----|------|
| Formulaire de contact (D-57) | `formulaire-contact` (`../noezia-shadowlab-formulaire`) | session principale, relu par Opus | écrit ; à tester puis fusionner (accord d'Ethan) |
| Règle « HeadlessChrome partout » (D-60) | `arena-headless-partout` (`../noezia-shadowlab-arena`) | session principale | écrit ; à tester puis fusionner avant la référence (accord d'Ethan) |
| NOEZIA en identité native (D-59) | `moteur-identite-native` (`../noezia-shadowlab-moteur`) | session principale, relu par Sonnet | écrit ; à tester puis fusionner (option sans effet par défaut) |
| Version réelle annoncée (D-58) | `moteur-version-reelle` (sans dossier) | session principale | en attente de la mesure « interface » |
| Mémoire 16 et 32 Go admise | `arena-memoire-32` (`../noezia-shadowlab-memoire`) | sous-agent Sonnet | écrit et relu ; à tester, puis fusionner avec les autres règles de l'Arena avant la référence |
| `pas_de_scroll` et `pas_de_pause` justes | `arena-comportement-pages` (`../noezia-shadowlab-comportement`) | sous-agent Opus | écrit et relu ; à tester et fusionner **avant** les sessions humaines (le relevé gagne deux champs, `page_defilable` et `delai_souris_max_ms`). Laisser de côté son commit de journal `4c402f8`. `VERSION_INFORMATION` : garder « 2026-11-12.4 » |
| Origine des 84 écarts d'empreinte | `docs/recherche/empreinte-noezia-2026-11-12.md` | sous-agent Sonnet, lecture seule | fait, contrôlé par sondage, poussé |
| Chrome avec interface sur serveur Linux | `docs/recherche/chrome-interface-serveur-linux-2026-11-12.md` | sous-agent Sonnet, recherche Web | fait, poussé (rien d'installé ni de testé) |
| Détecteur `cdp` en V2 | `arena-cdp-juste` (`../noezia-shadowlab-cdp`) | sous-agent Opus | écrit et relu : `debugger_instant` et `no_first_input` retirés (0 ms dans 803 relevés sur 835, tous moteurs ; relevé pris avant tout clic). À tester et fusionner **avant** la campagne et les sessions humaines (décidé par la coordination : faux par construction, pas besoin d'attendre). Révise D-45, point 1 |
| Mémoire affichée « 0.0 Mo » dans la fiche d'un passage | `interface-memoire-mo` (`../noezia-shadowlab-interface`) | sous-agents Sonnet (enquête puis correctif) | écrit et relu ; à tester (`npm --prefix frontend test`) puis fusionner. La mesure en base est juste, en Mo |
| Écarts entre `AGENTS.md`, `README.md` et le code | `README.md`, `AGENTS.md` | sous-agents Sonnet (audit puis réécriture) | fait, contrôlé, poussé. Reste à vérifier en lançant : nombre de tests rapides, bornes de versions des moteurs isolés |
| WAF du niveau 07 | `tests/test_arena_waf.py` (non suivi), `configs/experiments/controle-waf-07.yaml` | session principale | prêt ; image du WAF à reconstruire hors campagne |

## Prochaine action (12/11, après la récolte 95 qui finit vers 13 h 20)
Décidé par la coordination à midi : une seule campagne remplace la référence et la mesure « interface » ; le
détecteur `cdp` corrigé entre dans l'Arena avant elle, donc elle tourne sur les niveaux 01 à 07 normaux.
Dans l'ordre, sans campagne en cours pour les étapes 1 à 4 :
1. Lire la récolte 95 (complétude, exactitude, durée ; chargement des pages = 30 s sur 61 min) et l'écrire
   au § 2 du plan.
2. Tester chaque branche dans son dossier (tests vus en échec sur le commit de tests, verts sur la tête),
   puis fusionner dans `niveau-authentifie-perimetre` : `formulaire-contact`, `arena-headless-partout`,
   `arena-memoire-32`, `arena-comportement-pages`, `arena-cdp-juste`, `moteur-identite-native`, `interface-memoire-mo`
   (`npm --prefix frontend test`). `docs/DECISIONS.md` : garder toutes les entrées (D-57, D-59, D-60, et
   numéroter celles des règles de comportement et de la mémoire). Suite complète, lint, pousser, retirer
   les dossiers fusionnés. Prévenir Ethan pour le formulaire (il lance le tunnel devant le Mac).
3. WAF du niveau 07 : `uv run pytest tests/test_arena_waf.py` (échec attendu), exclusion de la règle 942432
   sur `/lab/(turnstile|recaptcha)/verifier` dans `docker/arena/coraza/main.go`, `uv run shadowlab arena
   demarrer --reconstruire`, test vert.
4. Vérifier à l'écran la page `/contact` du site public (essai local, sans tunnel).
5. Campagne unique `configs/experiments/ablation-interface.yaml` (525 passages, environ 2 h 30) : noezia,
   noezia en identité native, patchright recommandé, deux témoins ; niveaux 01 à 07 de l'Arena corrigée.
   Puis `recolte-rythme.yaml` (30 min).
6. Plan (§ 2, § 8), journal, pousser. **Site libre à 20 h** : aucune campagne ni `shadowlab site` en cours.
7. Ce soir, après les 5 sessions d'Ethan : `uv run shadowlab rejeu` (jalon A sur l'Arena corrigée),
   comparaison de ses en-têtes et de son empreinte à ceux de NOEZIA ; vérifier qu'aucune session ne porte de
   signal `cdp` et que `debugger_delta_ms` vaut 0 chez lui aussi.

Branche `moteur-version-reelle` (D-58) : gardée de côté, sans doute inutile si l'identité native l'emporte.
Ce qu'on attend d'Ethan : `docs/PLAN.md` § 7 et `notes/ia/questions-ouvertes.md`.
