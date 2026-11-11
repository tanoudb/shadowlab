---
permalink: noezia-shadowlab/questions-ouvertes
title: questions-ouvertes
type: note
---

# Questions ouvertes

Ce qui attend Ethan.
## Ouvertes
- **2026-11-11 — Commit et push** : accord pour committer les fichiers non suivis utiles et pousser la
  branche `niveau-authentifie-perimetre` (33 commits ne sont que sur ce poste). Étape 1.1 du plan.
  Recommandation : oui, tout de suite.
- **2026-11-11 — Mise en ligne du site vitrine** : où l'héberger, sur quel domaine à toi, derrière
  Cloudflare gratuit (étapes 1.6 et 1.8). Recommandation : un sous-domaine dédié, sur une petite machine
  séparée du labo. La mise en ligne reste à toi ; les conditions sont dans `docs/PLAN.md` § 5.
- **2026-11-11 — Code mort `engines/noezia/pool.py`** : il appelle une classe et deux méthodes qui
  n'existent pas, rien ne l'importe. Recommandation : le supprimer (le palier 4 le remplace).
- **2026-11-11 — Pour le palier 3** : un serveur Linux, un proxy résidentiel, et l'environnement de tor-i
  qu'on a le droit de viser. Rien d'urgent avant la fin du palier 2.
- **2026-11-11 — Périmètre : sites tiers** : les usages cités (scans de manhwa, site de résultats de rallye)
  visent des sites tiers, hors du périmètre actuel (D-30 : cibles à nous ou autorisées). Même point pour
  un service payant ou un réseau social : l'automatisation y est en général interdite par les conditions
  d'utilisation (le risque est le compte), et un réseau social contient les données personnelles d'autres
  gens (RGPD). Ne bloque pas la v1, qui se prouve sur nos cibles. Recommandation : garder le périmètre actuel pour le projet ; tor-i,
  qui nous appartient, sert de cible réelle.
- **2026-11-03, devenue bloquante le 11/11 — Sessions humaines de référence** : faire 10 sessions sur
  http://127.0.0.1:8770/manuel (navigateur habituel, une minute chacune, puis « Terminer »), dont 2 sous
  Safari. C'est l'étape 2 du plan : sans elles, on ne sait pas si l'Arena durcie attrape les bots ou tout
  le monde (le détecteur `cdp` est suspect, voir `docs/PLAN.md` § 3).
- **2026-11-11 — Domaine de test Cloudflare** : fournir un domaine ou sous-domaine à toi (pas un domaine
  client) placé derrière Cloudflare gratuit, pour l'étape 3. Recommandation : un sous-domaine dédié.
- **2026-11-09 — Clé reCAPTCHA v3** : enregistrer une clé v3 (localhost autorisé) et la mettre dans `.env`.

## Tranchées
- **2026-11-11 — Objectif de la v1** : validé par Ethan (D-54). Voir `docs/PLAN.md` § 1.
- **2026-11-03 — Moteurs anti-détection** : Ethan autorise leur intégration contre nos propres protections (D-15).
- **2026-11-03 — Docker Compose** : devenu nécessaire pour l'Arena (Coraza, Nginx) ; OrbStack est disponible.
