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

## État au 2026-11-12 (21 h 50)
- **Plan de travail unique : `docs/PLAN.md`** (objectif, état mesuré, quatre paliers, règles, suivi au § 8).
  Le lire d'abord. Constats détaillés du 11/11 : `notes/ia/analyse-paliers-2026-11-11.md`.
- Palier 1 : étapes 1.1 à 1.5 faites, 1.6 codée (application publique ; mise en ligne par Ethan, script
  `scripts/site-public-tunnel.sh`), 1.7 outillée (`uv run shadowlab rejeu`, D-56) mais sans session humaine.
- **14/11, D-78 et D-79, campagnes 110 et 111** : une photo n'est plus comptée comme une page par l'Arena (D-78) ;
  dans le moteur, la page obtenue après un défi reçoit l'interaction humaine (D-79 : la première vraie page
  durait 54 à 71 ms sans un geste, elle dure 6,2 à 10,5 s avec souris et défilement). Les deux campagnes :
  navigateur 15 sur 15 du niveau 02 au niveau 06 sans corrélation, témoin `http` 0 sur 15. Détail : `docs/PLAN.md` § 2.
- **14/11, D-80 à D-83** : site public en ligne par tunnel rapide, accueil court, plus aucun nom du projet servi
  (D-80, D-81) ; durée du cookie de l'Arena réglable par profil (D-82) ; la récolte peut repasser la porte en cours
  de passe (D-83). Campagne 112 (cookie de 600 s) : 3 passages sur 3 aux niveaux 04, 05 et 06 sans corrélation,
  158 pages et 2 100 champs sur 2 100, le défi revenu 1, 2 et 2 fois et repassé sans arrêt. Détail : `docs/PLAN.md` § 2.
- Tests au 14/11 à 11 h 49, après D-83, sans campagne : **1 714 verts** (`uv run pytest` : 1 670 rapides et 44
  d'intégration
  avec de vrais navigateurs et la pile Docker), 11 tests de l'interface (vitest, 12/11 à 16 h 16), lint propre. Branche
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
  immobilières, site de rallye avec suivi des châssis). La commande de récolte générale (liste puis fiches,
  tableaux, arbre) est faite et fusionnée (D-70) ; elle passe avant les calibrages restants du labo. La règle
  D-30 (pas de site tiers protégé sans autorisation) reste en vigueur ; la lever est une décision d'Ethan.
- Défauts de l'Arena soupçonnés d'arrêter aussi les humains : `pas_de_scroll`, `pas_de_pause`, `meta-composite`
  (se déclenche chez tout le monde, ne pèse dans aucune décision), WAF du niveau 07 sur Turnstile. Les
  sessions humaines trancheront.
- Manquent pour l'objectif : les sessions humaines et le calibrage de l'Arena, le bannissement dans
  l'Arena, une identité persistante puis plusieurs identités dans le moteur, l'exécution sur un serveur
  Linux, un test contre Cloudflare, la preuve de la récolte générale (campagne complète, un vrai site).

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
2. **Récolte générale** : fusionnée dans `niveau-authentifie-perimetre` (commit `b1a40ed`, accord d'Ethan à
   21 h 40, D-70), rien sur `master`. Guide `docs/recolte.md`, conception
   `docs/recherche/recolte-generale-2026-11-12.md`. Mesuré avec la commande réelle : vitrine à 500 annonces,
   525 pages, 7 000 champs sur 7 000 (0,8 s) ; rallye factice, 427 pages, 34 410 champs sur 34 410 ; navigateur,
   48 pages sur 48 au niveau 01. Après la fusion : 1 247 tests verts. **Campagne de preuve n° 102** (12/11, 21 h 54
   à 1 h 18) : 12 passages sur 12, pages, enregistrements et champs à 100 % avec les deux moteurs sur les deux
   sites factices, niveau 01. **Par l'Arena (13/11)** : campagnes 103 et 104, 0 sur 3 aux niveaux 04 à 06, deux
   défauts trouvés et corrigés (D-71 : la limite de débit comptait les photos ; D-72 : la porte d'entrée ne
   voyait pas un défi déjà franchi) ; **campagne 105 : le moteur navigateur fait 15 passages sur 15 du niveau
   02 au niveau 06 sans corrélation, 21 pages et 280 champs sur 280 à chacun**, aucun blocage. Réserves : 3
   passages par niveau, 21 pages par passage, CAPTCHA en clés de test, pas de corrélation, pas de niveau 07,
   pas d'humain en base. **Parcours long (13/11)** : campagne 106, le site de rallye (427 pages, une seule
   session) passe aux niveaux 04 et 05 et s'arrête à la 10ᵉ page au niveau 06 sans corrélation, parce que
   l'Arena redemandait le défi quand Chrome reprenait sa session TLS (D-73, corrigé) ; **campagne 107 : 427
   pages et 34 410 champs sur 34 410 aux niveaux 04, 05 et 06 sans corrélation**, un passage par niveau,
   environ 50 minutes chacun. Le cookie de défi de l'Arena vit une heure : une passe plus longue sera redéfiée
   et arrêtée (arrêt puis reprise, jamais mesuré). **Campagne 108 (13/11), 35 passages par niveau** : 35 sur
   35 au niveau 04, 32 sur 35 au niveau 05, 35 sur 35 au niveau 06 sans corrélation. Au niveau 05, **deux
   blocages du moteur** par le détecteur de comportement (`trajectoire_lineaire` : souris trop droite), le
   troisième échec est une erreur réseau du CAPTCHA de test. Sur environ 4 400 pages, la souris du moteur
   passe sous le seuil environ une fois sur 1 000 (mouvement court de 10 à 15 angles) : défaut du moteur, à
   corriger avant tout long travail. Rien n'est prouvé sur un vrai site.
3. **Site public pour la communauté (14/11)** : refait à la demande d'Ethan pour une étude ouverte (Reddit, amis) :
   accueil « Humain ou robot ? » en français et en anglais, faux réseau social de photos « Mosaïk Démo » (93 photos
   libres de Wikimedia Commons, créditées), relevé enrichi des gestes (jamais une touche ni un texte), fréquentation
   par jour (`shadowlab public frequentation`, `shadowlab public sessions`), plafond de sessions réglable. Quatrième
   relecture indépendante : 15 défauts, tous corrigés (D-75 à D-77). Fusionné dans la branche de travail (`346f4b6`).
   **En ligne depuis le 14/11 à 11 h 06 par le tunnel rapide** (adresse temporaire dans
   `outputs/public/adresse-publique.txt`, lancé par l'assistant à la demande d'Ethan, plafond à 150 sessions par jour). À la charge d'Ethan avant une annonce : nom d'hôte stable (tunnel nommé sur un domaine), règle de
   limitation de débit chez Cloudflare, plafond de sessions ; liste dans `docs/site-public.md`. Lancement d'essai :
   `SHADOWLAB_PUBLIC_CONTACT="Labo Vitrine" scripts/site-public-tunnel.sh` (tunnel rapide : adresse qui change, à
   ne pas annoncer). Non essayé : Safari, iPhone, Firefox, un vrai tunnel. Défaut de l'Arena trouvé au passage :
   `rythme_soutenu` comptait les photos comme des pages (corrigé le 14/11 : D-78, campagne 110).
4. Reporté au 13/11 : `configs/experiments/recolte-rythme.yaml` (mesure du rythme de récolte).
5. **Palier 2** : conception `docs/recherche/identite-qui-dure-2026-11-12.md`, à valider par Ethan (quatre
   questions au § 10 de ce document, reprises au `docs/PLAN.md` § 7). Aucune session humaine en base à 21 h 30.
6. Plan (§ 2, § 8), `AGENTS.md` (État), journal, pousser.

Ce qu'on attend d'Ethan : `docs/PLAN.md` § 7 et `notes/ia/questions-ouvertes.md`.
