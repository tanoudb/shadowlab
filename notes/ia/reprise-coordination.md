---
permalink: noezia-shadowlab/reprise-coordination
title: reprise-coordination
type: note
---

# Reprise de la coordination (tenue à la main, mise à jour le 17/11/2026 à 14 h)

Pour une session de coordination qui reprend sans rien avoir vu. L'état du projet est dans `AGENTS.md` et
`notes/ia/contexte.md` ; ce fichier dit seulement ce qui est en cours, qui le fait et ce qu'il faut surveiller.

## Rôle
La coordination ne code pas : elle écrit des briefs, contrôle les résultats dans les bases et les diffs, décide,
fusionne dans `niveau-authentifie-perimetre` (jamais `master`), pousse et rend compte à Ethan, court et en français.
Sous-agents et sessions : Sonnet par défaut, Opus pour une conception difficile, jamais Fable. Pas de veille à vide.

## Ce qui tourne
| Quoi | Où | État au 17/11, 14 h | À surveiller |
|---|---|---|---|
| **Course de 7 jours (I9, D-96)** | `.courses/i9`, tmux `course-i9`, pile Docker `shadowlab-course-i9`, ports 8760, 8753, 8761, code figé `course-i9` (`d5983d7`) | Départ le 17/11 à 11 h 21, fin le 24/11 à 11 h 21. Jour 1 : les trois témoins tenus ; sujet 2 visites réussies sur 2, même visiteur, identité `ok` | Une fois par jour, au premier réveil : `scripts/course.sh etat` (lire le code **sans tube** : 0 normal, 1 arrêtée, 2 retard ou blocage, 3 introuvable), la ligne de l'identité du sujet, `scripts/course.sh bilan 1` et `df -h /`. Le bilan dit « NON TENU » tant que la récolte n'a pas atteint 99 % : c'est attendu avant la fin. Ne jamais changer de commit dans `.courses/i9`, ne jamais redémarrer Docker ni OrbStack |
| **Site public** | tmux `site-public-tunnel` et `site-public-app`, port 8771 | En ligne, avec le résultat de fin de session (D-97, fusion `c4f5de8`). Adresse dans `outputs/public/adresse-publique.txt` (change si le tunnel s'arrête) | Nouvelles sessions : `SHADOWLAB_PUBLIC_CONTACT="Labo Vitrine" uv run shadowlab public sessions`, puis `uv run shadowlab rejeu --base outputs/public/public.sqlite3`. Ethan poste le lien lui-même ; il doit dire quand et où (un Reddit de revente : sessions à mettre à part) |
| **Étape 3.2, un proxy par identité** | session « Palier 3.1 : essai de fumée Linux » (`local_8d1fdd5e-f440-410b-a609-0c8cf3887bc9`), branche `claude/fumee-linux-43d3e8` | Brief envoyé le 17/11 vers 14 h | À sa note de fin : contrôler (tests rouges puis verts, diff, test avec un vrai Chrome), puis fusionner |

## Ce qui est fini et attend une action de la coordination
- **Étape 3.1 (essai du moteur sous Linux)** : faite sur `claude/fumee-linux-43d3e8`, contrôlée (six campagnes relues dans
  sa base, copiée dans `outputs/fumee-linux-2026-11-17.sqlite3`). **À fusionner** au SHA que la session donnera.
  Attention aux conflits : le journal et `docs/DECISIONS.md` se résolvent en gardant les deux côtés ; `docs/PLAN.md` et
  `AGENTS.md` se lisent bloc par bloc (sinon des lignes de tableau en double).
- Dossiers de travail de sessions finies, à retirer quand Ethan aura archivé les sessions :
  `.claude/worktrees/resultat-public-a943e4` (captures non versionnées dans `outputs/resultat-public/`) et
  `agent-a9b93470a0105ec94`.

## La suite du moteur, dans l'ordre
1. **Linux, après l'essai 3.1** (liste dans `docs/recherche/fumee-linux-2026-11-17.md` § 6). Trois travaux séparés :
   - WebGL absent avec interface sur Linux sans carte graphique : corriger le moteur (premier essai :
     `--enable-unsafe-swiftshader`, avec la sonde `scripts/fumee-linux-sonde.py`) ; critère : `webgl.disponible` vrai dans
     les empreintes.
   - Une règle de l'Arena pour l'absence de WebGL : étape à part (le plan § 6 gèle les nouveaux détecteurs ; un seul
     humain connu sur ordinateur). Elle ne bloque pas la correction du moteur ; elle bloque de déclarer la 3.3 atteinte.
   - `devices_vide` et `duree_pages_reguliere` (4 blocages en identité native) : chercher la cause avant de corriger,
     puis remesurer à 30 passages, en amd64 avec le vrai Chrome seulement.
   **Tout cela demande une image Linux : environ 13 Go au pic.** Règle : amd64 seulement, effacer son cache juste après
   la construction, et aucune construction si « libre moins pic » passe sous 20 Gio.
2. **3.3** : Ethan a dit « utlise orbsatck pour linux » : pas de serveur payant, une machine Linux x86_64 d'OrbStack
   tiendra lieu de serveur (limites dans le même document, § 8). **3.4** (vrai Cloudflare) attend un domaine et un proxy.
3. **Palier 2, reste** : I8 (humains qui reviennent, attend Ethan ; passé après I9 par D-96), bilan final d'I9 le 24/11,
   I10 (comptes).

## Disque (le point fragile du poste)
Le 17/11 le disque est tombé deux fois sous 15 Gio libres : un autre projet du poste écrit beaucoup par moments, et les
constructions Docker de l'essai Linux ont pris 13 Go. Seuil d'arrêt des sessions : 20 Gio libres. Ethan fait la place
lui-même hors de ce projet ; ne rien supprimer hors du projet sans qu'il le dise.

## En attente d'Ethan
- Quand et où il poste le lien du site ; un essai du partage sur son téléphone (Safari et iPhone jamais essayés).
- De la place sur le disque pour la suite Linux.
- I8 : il a répondu « il faut que on au vraiment des inconnu qui les test », puis « gratuit » (pas de panel payant).
- Un contrôle automatique quotidien de la course lui a été proposé deux fois, sans réponse : ne pas reposer la question ;
  faire le contrôle au premier réveil de chaque jour.