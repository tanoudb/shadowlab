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

## État au 2026-11-12
- **Plan de travail unique : `docs/PLAN.md`** (objectif, état mesuré, quatre paliers, règles, suivi au § 8).
  Le lire d'abord. Constats détaillés du 11/11 : `notes/ia/analyse-paliers-2026-11-11.md`.
- Palier 1 : étapes 1.1 à 1.5 faites, 1.6 codée (application publique, mise en ligne à faire par Ethan).
  602 tests rapides verts, lint propre, branche `niveau-authentifie-perimetre` poussée, rien sur `master`.
- Mesuré (campagnes 90 et 92) : NOEZIA passe et récolte 100 % aux niveaux 01 à 03 ; aux niveaux 04 à 07
  le seul détecteur `cdp` refuse tous les moteurs de la même façon. Il est soupçonné d'arrêter aussi les
  humains : aucune session humaine en base pour le dire.
- Outil prêt pour le dire : `uv run shadowlab rejeu` (D-56) rejoue les sessions humaines contre chaque
  niveau et donne les humains arrêtés et le détecteur responsable.
- Manquent pour l'objectif : les sessions humaines et le calibrage de l'Arena, le bannissement dans
  l'Arena, une identité persistante puis plusieurs identités dans le moteur, l'exécution sur un serveur
  Linux, un test contre Cloudflare.

## Prochaine action
- Étape 1.7 : sessions humaines (5 en local par Ethan, puis au moins 10 sur le site public), rejeu,
  calibrage des détecteurs (`cdp` en premier), jalon A. Puis 1.8 (Cloudflare) et 1.9 (corriger le moteur).
  Ce qu'on attend d'Ethan : `docs/PLAN.md` § 7 et `notes/ia/questions-ouvertes.md`.
