---
permalink: noezia-shadowlab/questions-ouvertes
title: questions-ouvertes
type: note
---

# Questions ouvertes

Ce qui attend Ethan.
## Ouvertes
- **2026-11-12 — 5 sessions humaines locales, dès que possible (10 minutes)** : lancer
  `uv run shadowlab site`, ouvrir http://127.0.0.1:8770/manuel dans ton navigateur habituel, fenêtre
  visible, laisser « 01 — Baseline », cocher l'accord, puis naviguer une minute : quelques pages du site de
  test **et le site vitrine** (http://127.0.0.1:8770/lab/vitrine : la liste, une fiche). Finir par
  « Terminer une session manuelle » en bas de page (un oubli n'est pas grave : la session est fermée seule
  après 10 minutes). Si possible, une ou deux sessions dans un autre navigateur (Safari, Firefox).
  Arrêter le site, puis `uv run shadowlab rejeu` : il dit, niveau par niveau, combien de tes sessions
  l'Arena aurait arrêtées et quel détecteur est en cause. La campagne 90 montre que seul `cdp` arrête
  NOEZIA aux niveaux 04 à 07, et il arrête tout le monde de la même façon : ces sessions disent s'il
  arrête aussi les humains. Recommandation : les faire avant tout autre chose ; arrêter le site ensuite
  (une campagne réutiliserait un site resté ouvert avec un ancien code).
- **2026-11-12 — Mise en ligne de l'application publique (étape 1.6, bloque 1.7 et 1.8)** : le code est
  prêt (`src/shadowlab/public/`, `docs/site-public.md`). Il faut de toi : (1) une machine qui fait tourner une
  application Python derrière un mandataire HTTPS ; (2) un domaine ou sous-domaine à toi, derrière Cloudflare
  gratuit ; (3) ton nom et un moyen de te joindre, affichés sur la page d'information
  (`SHADOWLAB_PUBLIC_CONTACT`, sans lui l'application refuse de démarrer) ; (4) la durée de conservation si
  90 jours ne te conviennent pas. Recommandation : un sous-domaine dédié, sur une petite machine séparée
  du labo, 90 jours. La mise en ligne reste à toi.
  **Mise à jour du 12/11, 8 h 45 — tu m'as demandé de le mettre en ligne pour le partager.** Voie la plus
  courte, sans machine ni domaine : un tunnel Cloudflare depuis le Mac mini (`cloudflared`, lien
  `…trycloudflare.com`, aucun port ouvert, adresse de la maison cachée). Il ne me manque que **le texte du
  contact** (point 3) ; ta réponse vaut accord pour installer `cloudflared` (Homebrew, client officiel de
  Cloudflare, absent de la machine). Limites de ce lien : il change à chaque relance du tunnel, pas de
  limitation de débit, le Mac doit rester allumé et éveillé (il s'endort après 1 minute sans activité : à
  tenir éveillé avec `caffeinate` tant que le site tourne). Pour un lien stable à partager largement, il
  faut un domaine à toi chez Cloudflare (points 1 et 2).
  **9 h — tu veux un pseudonyme comme responsable.** `cloudflared` est installé et le script
  `scripts/site-public-tunnel.sh` est prêt. Deux choses restent à toi : (a) **une adresse e-mail** où
  l'on peut t'écrire (la page dit « écrivez à : … » pour faire supprimer une session ; je ne peux pas créer
  de boîte à ta place) ; recommandation : un alias dédié, pseudonyme proposé « Labo Vitrine » ; (b) **lancer
  le script toi-même** : l'ouverture du tunnel m'est refusée par le garde-fou de l'application.
  `SHADOWLAB_PUBLIC_CONTACT="Labo Vitrine — <adresse>" scripts/site-public-tunnel.sh`, puis me donner la
  main : je vérifie le parcours complet depuis l'adresse publique.
  **10 h 15 — tu as donné une adresse en conversation (volontairement pas recopiée dans le dépôt), sans
  enthousiasme pour l'afficher.** Elle contient ton pseudo habituel : le pseudonyme protège donc peu sur un
  lien très partagé. À trancher avant de partager (le lien change à chaque relance) : garder l'adresse, ou
  la remplacer par un **formulaire de contact** sur le site (aucune adresse affichée ; une à deux heures de
  travail, code et tests). Recommandation : le formulaire si le partage est large. Reste dans les deux cas
  (b) : lancer le script toi-même.
  **10 h 55 — tranché : « Oui, fusionne ».** Le formulaire (D-57, branche `formulaire-contact`) sera testé
  puis fusionné dès la fin de la récolte en cours. Il ne te restera qu'à lancer, avec le pseudonyme seul :
  `SHADOWLAB_PUBLIC_CONTACT="Labo Vitrine" scripts/site-public-tunnel.sh`.
- **2026-11-12 — CAPTCHA démo jamais servi aux niveaux 04 à 07** : une session suspecte est bloquée avant
  d'y arriver, une session propre n'est pas défiée (dernière émission à un niveau normal : campagnes 3 à 5).
  Le tableau des niveaux l'annonce pourtant au niveau 04. Recommandation : ne rien changer à l'Arena avant
  les sessions humaines ; corriger seulement la description des niveaux, et décider au palier 2 s'il faut
  une « zone grise » où il serait servi.
- **2026-11-12 — WAF du niveau 07 : Turnstile et reCAPTCHA impossibles à valider** : en paranoïa 4, le nom
  des champs `cf-turnstile-response` et `g-recaptcha-response` déclenche la règle 942432 (reproduit).
  Personne ne passe, humain compris. Pas une question : je corrige (exclusion étroite, test vu en échec
  d'abord) dès qu'aucune campagne ne tourne, puis une courte campagne de contrôle. Dis-le si tu préfères
  que je n'y touche pas.
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
- **2026-11-12 — Arena : règle « HeadlessChrome dans n'importe quelle requête d'une session »** : accord
  d'Ethan (« Oui, ajoute-la »), D-60, branche `arena-headless-partout`, à tester et fusionner après la
  récolte, avant la campagne de référence.
- **2026-11-12 — Contact du site public** : un formulaire de contact à la place d'une adresse affichée (D-57) ;
  responsable affiché sous le pseudonyme « Labo Vitrine ». Accord d'Ethan (« Oui, fusionne »).
- **2026-11-11 — Commit et push** : accord d'Ethan, branche poussée le 11/11 (étape 1.1).
- **2026-11-11 — Objectif de la v1** : validé par Ethan (D-54). Voir `docs/PLAN.md` § 1.
- **2026-11-03 — Moteurs anti-détection** : Ethan autorise leur intégration contre nos propres protections (D-15).
- **2026-11-03 — Docker Compose** : devenu nécessaire pour l'Arena (Coraza, Nginx) ; OrbStack est disponible.
