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

## État au 2026-11-11
- **Plan de travail unique : `docs/PLAN.md`** (objectif, état mesuré, quatre paliers, règles). Le lire d'abord.
  Constats détaillés avec fichiers et lignes : `notes/ia/analyse-paliers-2026-11-11.md`.
- Le socle est sain : 405 tests rapides verts, lint propre.
- Les chiffres de l'Arena durcie ne sont pas fiables : aucune session humaine (0 sur 25 623 passages), le
  moteur est classé « automatisé » sans jamais être bloqué, le taux de détection est mal calculé quand il
  y a des pannes, et le travail du 11/11 (D-47 à D-53) n'a été mesuré par aucune campagne.
- Manquent pour l'objectif : un site vitrine à contenu connu, le bannissement dans l'Arena, une identité
  persistante puis plusieurs identités dans le moteur, l'exécution sur un serveur Linux, un test contre
  Cloudflare.
- Branche `niveau-authentifie-perimetre` : 33 commits non poussés, pas de PR, rien sur `master`.

## Prochaine action
- Palier 1, étape 1.1 (commit et push, sur accord d'Ethan), puis 1.2 (mesure fiable) et 1.3 (campagne de
  référence). Ce qu'on attend d'Ethan : `docs/PLAN.md` § 7.
