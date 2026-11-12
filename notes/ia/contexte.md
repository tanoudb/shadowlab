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

## Chantiers (12/11, 13 h 40) — consigne d'Ethan : la session principale dirige, des sous-agents travaillent
**Intégré dans `niveau-authentifie-perimetre` et poussé** (fusion `13ccfa3`, puis `6cf5686`, `4449757`) : formulaire
de contact (D-57), identité native de NOEZIA (D-59), règle « HeadlessChrome dans toute requête » (D-60),
`pas_de_scroll` et `pas_de_pause` (D-61), détecteur `cdp` V2 (D-62), mémoire 16 et 32 Go (D-63), mémoire
affichée en Mo, WAF du niveau 07 (`2135656`). Chaque test vu en échec sans son code ; suite complète verte
(665 tests, dont ceux avec de vrais navigateurs) ; formulaire vérifié à l'écran après correction d'un refus
dans un vrai navigateur (`Referrer-Policy: origin`, pas `no-referrer`). Dossiers de travail retirés.

| Reste ouvert | Où | État |
|--------------|----|------|
| Corrélation : libellés, un signal par fait, débit sur 60 min | `arena-correlation-calcul` (`../noezia-shadowlab-correlation`) | écrit par Opus, repris après une alerte de sécurité, rouge puis vert sur sa branche ; à fusionner hors campagne (décision à numéroter D-64) |
| Version réelle annoncée (D-58) | branche `moteur-version-reelle` | de côté ; sans objet si l'identité native l'emporte |
| NOEZIA comparé au vrai Chrome (campagne 96) | `docs/recherche/empreinte-noezia-2026-11-12.md` | sous-agent Sonnet en cours, lecture seule |

## Prochaine action (12/11)
1. **Campagne 97 en cours** depuis 13 h 35 (`ablation-interface.yaml`, 525 passages, fin vers 16 h 05, journal
   `outputs/campagne-ablation-interface.log`) : ni test ni modification de `src/` d'ici là.
2. À sa fin : `uv run shadowlab arena appliquer` (sans `SHADOWLAB_PROFILS_EXTRA`) pour retirer les profils
   `06scorr` et `07scorr` ; lire les résultats (script `lire_campagne.py` du dossier temporaire de la
   session, sinon requêtes) ; les écrire au § 2 du plan.
3. Fusionner `arena-correlation-calcul`, suite complète, pousser.
4. `SHADOWLAB_VITRINE_TAILLE=40 uv run shadowlab campagne configs/experiments/recolte-rythme.yaml` (30 min).
5. Plan (§ 2, § 8), `AGENTS.md` (État), journal, pousser. **Site libre à 20 h** : aucune campagne ni
   `shadowlab site` en cours.
6. Ce soir : Ethan lance le site public (`SHADOWLAB_PUBLIC_CONTACT="Labo Vitrine" scripts/site-public-tunnel.sh`,
   devant le Mac) ; vérifier le parcours depuis l'adresse publique. Après ses 5 sessions locales :
   `uv run shadowlab rejeu` (jalon A sur l'Arena corrigée), comparer ses en-têtes et son empreinte à NOEZIA.

Ce qu'on attend d'Ethan : `docs/PLAN.md` § 7 et `notes/ia/questions-ouvertes.md`.
