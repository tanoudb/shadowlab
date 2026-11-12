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

## État au 2026-11-12 (18 h 15)
- **Plan de travail unique : `docs/PLAN.md`** (objectif, état mesuré, quatre paliers, règles, suivi au § 8).
  Le lire d'abord. Constats détaillés du 11/11 : `notes/ia/analyse-paliers-2026-11-11.md`.
- Palier 1 : étapes 1.1 à 1.5 faites, 1.6 codée (application publique ; mise en ligne par Ethan, script
  `scripts/site-public-tunnel.sh`), 1.7 outillée (`uv run shadowlab rejeu`, D-56) mais sans session humaine.
- Tests au 12/11 à 18 h 11, sans campagne : **769 verts** (`uv run pytest` : 731 rapides et 38 d'intégration
  avec de vrais navigateurs et la pile Docker), 11 tests de l'interface (vitest, 16 h 16), lint propre. Branche
  `niveau-authentifie-perimetre` poussée (fusions `759ca18`, assemblage `integration-12-11-b`, et `59674d0`,
  passages orphelins), rien sur `master`.
- Mesuré, campagne 97 (525 passages, 0 panne, `docs/PLAN.md` § 2) : le moteur `noezia` tel qu'il est fait
  15, 10, 10, 10, 0, 0, 0 sur 15 aux niveaux 01 à 07 (06 et 07 sans corrélation), une seule cause d'échec :
  `headless_dans_une_requete`. `noezia` en identité native et un vrai Chrome seul : 15 sur 15 aux niveaux 01 à
  03, puis 0 sur 15 du 04 au 07, à cause de quatre règles de l'Arena, corrigées depuis par D-66. Les deux
  témoins sont arrêtés dès le niveau 02.
- **Campagne 98** (contrôle de D-66, 135 passages, 0 panne, 16 h 19 à 16 h 52, `docs/PLAN.md` § 2) : `noezia` en
  identité native fait 15 sur 15 aux niveaux 04, 05 et 06 sans corrélation, donc 15 sur 15 aux six niveaux de
  l'objectif avec la campagne 97 ; le même Chrome sans le comportement de noezia fait 10, 5 et 0 (arrêté pour
  `aucune_interaction`) ; le témoin 0 sur 45. Réserves : 15 passages par niveau (30 exigés), CAPTCHA en clés de
  test aux niveaux 05 et 06, 06 sans corrélation, aucun humain en base, un seul Chrome sur macOS.
- **Campagnes 100 et 101** (12/11, `docs/PLAN.md` § 2) : `noezia` en identité native, 30 passages
  par niveau de 01 à 06 sans corrélation, 179 sur 180 (06 : 29 sur 30 ; le seul échec est un blocage du WAF,
  corrigé par D-69). Taux observé ≥ 90 % à chaque niveau, borne basse de Wilson sous 90 % (88,6 % à 30/30).
  Niveau 06 complet (avec corrélation) : 0 sur 15, signal `recycling_canvas`. Réserves : CAPTCHA en clés de
  test aux niveaux 05 et 06, aucun humain en base, une machine, un Chrome sur macOS, pas de témoin, rien contre
  une protection réelle ; l'identité native n'est pas le réglage par défaut. Le produit n'est pas atteint.
- Décisions du jour : D-64 (corrélation entre sessions, détecteur en 1.1), D-65 et D-67 (site public, deuxième
  et troisième relectures), D-66 (quatre règles de l'Arena qui classaient tout vrai Chrome), D-68 (numéro
  d'expérience jamais réutilisé, passages orphelins adoptés par la migration 9), D-69 (le WAF n'inspecte plus
  les jetons de CAPTCHA tiers avec les règles d'injection SQL).
- Site public : parcours vérifié à l'écran à 16 h 17, feu vert à la mise en ligne, réserve : le script de tunnel
  n'a jamais tourné avec un vrai tunnel (le filtre du journal de `cloudflared` n'a jamais vu une vraie ligne).
- Consigne d'Ethan du 12/11 : il aura besoin du scraper pour de vrais sites (premiers visés : annonces
  immobilières, site de rallye avec suivi des châssis). Après la mesure des niveaux 04 à 06, la commande de
  récolte générale (liste puis fiches, tableaux, arbre) passe avant les calibrages restants du labo. La règle
  D-30 (pas de site tiers protégé sans autorisation) reste en vigueur ; la lever est une décision d'Ethan.
- Défauts de l'Arena soupçonnés d'arrêter aussi les humains : `pas_de_scroll`, `pas_de_pause`, `meta-composite`
  (se déclenche chez tout le monde, ne pèse dans aucune décision), WAF du niveau 07 sur Turnstile. Les
  sessions humaines trancheront.
- Manquent pour l'objectif : les sessions humaines et le calibrage de l'Arena, le bannissement dans
  l'Arena, une identité persistante puis plusieurs identités dans le moteur, l'exécution sur un serveur
  Linux, un test contre Cloudflare, la commande de récolte générale.

## Chantiers (12/11, 16 h 25)
Fusionnés dans `niveau-authentifie-perimetre` et poussés : `formulaire-contact` (D-57), identité native
(D-59), `arena-headless-partout` (D-60), D-61, D-62, D-63, WAF du niveau 07, puis les branches du jour
ci-dessous. Dossiers de travail retirés pour les premiers ; vérifier ceux des branches du tableau
(`git worktree list` ne montre plus que le dossier principal à 16 h 25).

| Branche | Contenu | État |
|---------|---------|------|
| `public-relecture` | site public, relectures (D-65, D-67) | fusionnée (`integration-12-11-b`) |
| `tests-relecture` | tests de l'identité native, du périmètre, de `page_defilable`, des jetons au WAF | fusionnée |
| `arena-correlation-calcul` | corrélation : libellés, un signal par fait, débit sur 60 min (D-64) | fusionnée |
| `arena-vrai-chrome` | quatre règles qui classaient un vrai Chrome (D-66) | fusionnée |
| `integration-12-11-b` | assemblage des quatre ci-dessus, commit `759ca18` | fusionnée, poussée |
| `moteur-version-reelle` | version réelle annoncée (D-58) | de côté ; sans objet si l'identité native l'emporte |

## Prochaine action (12/11)
1. **Site libre à 20 h** : aucune campagne ni `shadowlab site` en cours. Ethan fait 5 sessions humaines
   locales (`uv run shadowlab site`, puis `http://127.0.0.1:8770/manuel`), puis `uv run shadowlab rejeu`
   (jalon A sur l'Arena corrigée) ; comparer ses en-têtes et son empreinte à NOEZIA.
2. **Récolte générale** : conception `docs/recherche/recolte-generale-2026-11-12.md`, soumise à Ethan à
   16 h 43, réponse attendue. Étapes 1, 2, 3, 5 et la recette du rallye (étape 6) faites, relues et assemblées
   dans `recolte-integration` (poussée, dossier `../noezia-shadowlab-recolte`) : 1 106 tests rapides verts ;
   commande réelle à 100 % sur la vitrine (500 annonces, 0,8 s) et sur le site de rallye factice (427 pages).
   Rien n'est fusionné dans la branche de travail sans son accord. Suite : étape 4 (moteur navigateur),
   campagne de preuve, étapes 7 et 8 (journal du 12/11, 19 h).
3. **Tunnel du site public** : à lancer par Ethan, à son Mac (`SHADOWLAB_PUBLIC_CONTACT="Labo Vitrine"
   scripts/site-public-tunnel.sh`) ; relire `outputs/public/tunnel.log` après le premier lancement.
4. Reporté au 13/11 : `configs/experiments/recolte-rythme.yaml` (mesure du rythme de récolte).
5. Plan (§ 2, § 8), `AGENTS.md` (État), journal, pousser.

Ce qu'on attend d'Ethan : `docs/PLAN.md` § 7 et `notes/ia/questions-ouvertes.md`.
