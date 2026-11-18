# Course I9 : pourquoi le sujet est tombé à sa 6ᵉ visite — 18/11/2026

La course de 7 jours (I9, D-96) a échoué le 17/11 à 20 h 43 UTC, à la 6ᵉ visite du sujet. Deux défauts du moteur, A et
B ; l'Arena n'y est pour rien et n'a pas changé. Décision : D-103. Branche `worktree-agent-ac4f38c973462d3ea`.

Sources : la base de la course (`.courses/i9/outputs/shadowlab.sqlite3`, ouverte en lecture seule), la base de la
répétition 3 (`.courses/repetition-3-2026-11-17/shadowlab.sqlite3`, lecture seule), la campagne 131 (soirée) dans la base
du dossier principal, un banc sans navigateur et un vrai Chrome devant le site du labo (tests cités plus bas). Aucune
campagne, aucun `arena appliquer`, rien touché de la course.

## 1. Les faits

**Visite 6 du sujet** (passage 19, monde 2) : fiche `AN-000068` (4,2 s, 21 mouvements de souris, 0 défilement, page
défilable), liste (2,8 s, 31 mouvements, 0 défilement, défilable), fiche `AN-000069`. Une photo de cette fiche est
bloquée sur le score composite 0,6 (seuil 0,5 du profil `endurance`) : `pas_de_scroll` (0,35) et
`navigation_lineaire` (0,25). Le visiteur est banni (D-92).

**Après le bannissement** : le document de la fiche était déjà servi (200) ; ses photos et son appel de données
`/lab/vitrine/api/annonces/AN-000069/similaires` reçoivent 403. Puis plus rien : aucune requête, aucune ligne de
journal ; le passage reste `en_cours` plus de 3 heures, l'identité reste `ok`.

## 2. Défaut A : deux pages défilables de suite sans défilement

### Les règles (detection.py, inchangé)

- `pas_de_scroll` (0,35) : au moins deux relevés de pages défilables, plus de 20 mouvements de souris en tout, et aucun
  `scroll` sur toutes ces pages.
- `navigation_lineaire` (0,25) : au moins 4 pages (documents et appels de données, photos exclues depuis D-78), toutes
  distinctes. Le chemin est lu sans la requête (`?page=`, `?sl=` ne comptent pas).
- Score : somme des poids × coefficient de famille (comportement : 1,0). 0,35 + 0,25 = 0,6 > 0,5.

### Les causes (dans le moteur)

1. **Une visite qui reprend la passe commence sur une fiche** (`parcours.py:683` avant correction : `page =
   etat.prochaine(passe)`). La course reprend la passe d'une visite à l'autre (D-96, règle 7). Le retour obligatoire à la
   liste après la première fiche (D-94, `lecture.py:88`) va alors à une liste que cette session n'a jamais vue : fiche,
   appel de données, liste, fiche = 4 chemins distincts, `navigation_lineaire` dès la 2ᵉ fiche. La propriété de D-94
   (« un chemin répété dès la quatrième requête ») ne tient que si la visite commence sur la liste.
2. **Une page sous 5 s est parcourue vite** (`lecture.py`, D-94). Avec les durées tirées par blocs de trois, les deux
   premières pages d'une visite sont toutes deux légères dans 31 % des visites qui reprennent la passe (banc, code
   d'avant : 28 sur 91). Une première estimation à la main donnait 21 % ; le banc la dément.
3. **L'interaction légère ne défile qu'avec une probabilité de 0,4** (`moteur.py:751` avant correction, dans
   `_interaction_post_clic_navigation`). Deux pages légères de suite sans défilement : 0,6 × 0,6 = 0,36.
4. **Trouvé par le banc** : dans une passe incrémentale, chaque fiche déjà lue, évitée sans requête, prenait quand même
   une durée au plan de lecture (`parcours.py:688` avant correction : `self._regler_lecture()` avant `_traiter`). Les blocs
   de trois ne valaient plus pour les pages vraiment lues.

### L'estimation

- **Banc sans navigateur** (`tests/test_lecture_defilement.py`) : le vrai parcours, la vraie lecture, la vraie souris et
  le vrai défilement sur une page factice, le vrai détecteur `comportement` relu à chaque page et relevé. Code d'avant
  (`54bbb7c`, relancé le 18/11 sur une copie du code de ce commit) : sur 100 visites qui reprennent la 1ʳᵉ passe (vitrine
  de 2 000 annonces, graine 20261117), 91 commencent sur une fiche ; parmi elles, 85 voient `navigation_lineaire` et
  **11 sont bloquées (12 %)**, toutes sur `pas_de_scroll` + `navigation_lineaire` ; aucune des 9 qui commencent sur la
  liste ne l'est.
- **Calcul qui le recoupe** : deux premières pages légères (31 %) × aucun défilement sur les deux (0,6 × 0,6 = 0,36) =
  11 %. La course commence ses visites sur une fiche tant que la 1ʳᵉ passe n'est pas finie (300 annonces, environ 15 pages
  par visite : une vingtaine de visites). Risque d'au moins un échec en 5 visites reprises : 1 − 0,88⁵ = 47 % ; en 20 :
  92 %.
- **Cause 4** (banc de 250 visites, vitrine de 300 annonces, graine 1, code d'avant relancé le 18/11) : parmi les 231
  visites qui commencent sur une liste, deux premières pages légères dans 31 %, `duree_pages_reguliere` dans 7 %, et
  **2 bloquées** sur `pas_de_scroll` avec `duree_pages_reguliere` (0,75), environ 1 sur 115. Même banc après correction :
  0 bloquée sur 250, `duree_pages_reguliere` 1 fois (0,4 %), deux premières pages légères dans 16 %.
- **Cohérence avec ce qui a tenu** : soirée 131, 24 visites qui commencent toutes sur la liste (aucune exposée aux causes
  1 à 3), 24 sur 24 ; répétition 3, 30 visites du sujet dont **une seule** commence sur une fiche (la 2ᵉ ; d'après les
  pages de départ, la 1ʳᵉ passe de la vitrine de 30 annonces finit à cette visite), 30 sur 30 — chance de passer : 88 % pour cette visite, environ 78 % pour les 28
  visites incrémentales (cause 4, 1 sur 115). Course I9 : visites 2 à 6 commencent sur une fiche (`AN-000009`, `23`, `45`, `54`, `68`),
  échec à la 5ᵉ d'entre elles. Les trois résultats sont compatibles avec l'estimation ; aucun ne la prouve à lui seul.

### La correction (moteur seulement)

- `moteur.py` : la **première page défilable de chaque visite est toujours défilée**, même parcourue vite
  (`_premiere_page_defilable`, `_defile_dans_la_visite`, remis à zéro par `start_session`). Les pages suivantes gardent le
  tirage à 0,4. Pas de nouvelle constante qui rende le rythme régulier : le défilement reste celui du simulateur, à
  l'heure que donne la page.
- `parcours.py` : une visite qui **reprend la passe entre par la dernière liste lue** (relue comme les retours de D-94,
  prise sur le budget de pages), sauf s'il reste moins de 2 pages ou, en passe incrémentale, si la page n'est pas à revoir.
- `parcours.py` : la durée de lecture n'est tirée **que pour une page demandée**.
- La liste d'entrée devient la première page de la passe reprise : elle passe par la porte d'entrée et par la règle de
  la première page. Vérifié sur pilote factice (tests de `test_course_visite.py`) : porte de 24 h expirée entre deux
  visites, le défi tombe sur la liste d'entrée et il est passé, la visite reprend sa file ; visiteur banni entre deux
  visites, le refus tombe sur la liste d'entrée, identité `banni`, rien de plus demandé, la fiche suivante reste en file.
- Banc après correction (mêmes graines) : 0 visite bloquée sur 100 visites reprises et 60 visites incrémentales ;
  `pas_de_scroll`, `navigation_lineaire` et `duree_pages_reguliere` vus 0 fois ; toutes commencent sur la liste ; les tests
  de D-94 restent verts.
- Dans un vrai Chrome (visite 1 du test de bout en bout : deux pages courtes, donc parcourues vite) : les relevés de
  l'observateur montrent un défilement sur les pages défilables. Un seul cas : ce n'est pas une mesure de taux.

## 3. Défaut B : la visite qui ne finit pas

### La cause

Pour juger un refus, le moteur lit le corps de chaque 403 d'une ressource (`moteur.py:628` avant correction :
`reponse.text()` dans `_defi_de_ressource`, appelé par `refus_ressources`). Playwright ne rend le corps qu'une fois la
requête finie, **et attend sans limite**. Or :

- le refus de l'Arena porte `Cache-Control: no-store` (`gardien.py:108`) ;
- `vitrine.js:37` ne lit pas le corps d'une réponse en échec (`r.ok ? r.json() : Promise.reject(…)`).

Mesuré dans un vrai Chromium (petit serveur local, 5 variantes : HTTP/1.0 ou 1.1, avec ou sans `no-store`, page qui lit
le corps ou non) : un 403 servi à un `fetch` dont la page ne lit pas le
corps ne finit jamais **seulement avec `no-store`** (aucun événement `requestfinished`), et `text()` ne revient pas ;
sans `no-store`, ou si la page lit le corps, tout finit. Les photos finissent toujours : leur corps se lit. Rejoué de bout
en bout dans un vrai Chrome au réglage de la course, devant le site du labo au profil `endurance`, bannissement écrit
pendant la fiche : les 6 photos sont lues, puis la lecture du corps de l'appel de données ne revient pas (pile du
greenlet : `_boucle` → `_controler_ressources` → `refus_ressources` → `_defi_de_ressource` → `Response.text`). Les
tests écrits avant la correction (`b4b31ff`) l'ont montré cinq fois sur cinq : les quatre cas du petit serveur (Chromium et
Chrome de la course, défi et bannissement) et la visite de bout en bout, tous arrêtés par le garde-fou (60 s, 150 s) avec
la même pile.

Dans la course, les refus de la fiche `AN-000069` (base de la course) : la 1ʳᵉ photo refusée par la détection (couche
`fingerprinting`, score 0,6), les photos 2 à 4 et l'appel de données par le bannissement.

Le test réel qui existait (`test_dans_un_vrai_navigateur_la_nature_du_defi_d_une_photo_et_d_un_appel_de_donnees`) ne
le voyait pas : son serveur ne renvoyait pas l'en-tête `Cache-Control` du gardien.

### La correction

- `moteur.py` : le moteur note la fin de la requête de chaque refus (`requestfinished`) et **n'en lit le corps que s'il est
  arrivé**, après une attente bornée (2 s au plus, par pas de 100 ms, seulement quand un corps manque). Sinon le refus est
  rendu « corps non lu » (`MOTIF_NON_LU`). Corps illisible après la fin : refus franc, comme avant.
- `sentinelle.py` : le motif JSON de l'Arena est lu dans le corps (`motif_de_refus`, `RefusRessource.motif`). Un refus au
  motif **`bannissement` bannit l'identité à toute page de la passe** (avant : seulement sur la première page, D-91 ;
  après, `alerte`). Un corps non lu ne masque pas un corps lu (ni un refus, ni le défi de la porte) ; seul, il compte comme
  un refus franc. Les autres refus après la première page restent une alerte (D-91).
- Résultat, de bout en bout (vrai Chrome, après correction) : la visite 2 finit en 25,5 s (lancement de Chrome, entrée par
  la liste, deux fiches et attente bornée comprises), notée `arretee`, cause « statut 403 sur une ressource de la page
  (motif bannissement) », identité `banni`, aucune page demandée après les refus de la fiche. Sur les refus de la visite 6
  (détection, puis bannissement, puis corps non lu), la sentinelle rend aussi `banni` (test). Si aucun corps au motif
  `bannissement` n'était lu (seulement le refus de la détection), l'identité serait en `alerte` et ne passerait à `banni`
  qu'à la première page de la visite suivante (403 en page, D-91).

## 4. Limites

- **Rien n'est mesuré devant la vraie Arena** (frontal TLS, Nginx, Coraza) après correction : aucune campagne lancée.
- Le banc ne juge que le détecteur `comportement` ; il ne reproduit ni un vrai Chrome (fusion d'événements, `scroll`
  sans molette), ni les autres détecteurs, ni la porte. Il suppose chaque page défilable (vrai dans la fenêtre de la
  course).
- La règle « première page défilable toujours défilée » est un comportement de plus, propre au moteur : un détecteur qui
  chercherait « le premier défilement arrive toujours sur la première page longue » le verrait ; aucun ne le fait dans
  l'Arena.
- L'entrée par la liste (première page de la passe reprise, porte d'entrée comprise) n'est vérifiée que sur pilote
  factice ; la répétition 1 était tombée sur une couture de ce genre (porte et relecture).
- L'entrée par la liste ajoute une page déjà lue à chaque visite reprise : une récolte un peu plus lente (une page sur 5
  à 40), jamais au-delà du budget.
- Un défi de la porte servi au seul appel de données, sans photo refusée dans la même page, n'est pas reconnu (corps non
  lu) : refus franc, donc alerte (ou bannissement sur la première page de la passe). Fenêtre étroite (la porte expire
  entre le document et son appel de données) ; jamais observé.
- Un refus **en page** au motif `bannissement` (page HTML de l'Arena) après la première page reste une alerte : la page de
  refus ne porte pas de motif lisible. Non traité ici.
- Le délai de 2 s n'est vérifié que sur le labo local ; sur un réseau lent, un corps arrivé après 2 s serait « non lu ».

## 5. Ce qu'il faut mesurer avant de relancer une course

1. Un essai de **visites qui reprennent la passe** devant la vraie Arena, profil `endurance` ou `endurancecourt`, vitrine
   de 300 annonces : au moins 20 visites du sujet (la 1ʳᵉ passe en entier), 0 blocage attendu ; relever par visite les
   signaux `pas_de_scroll`, `navigation_lineaire`, `duree_pages_reguliere`.
2. Une passe incrémentale réelle (vitrine courte, 30 annonces, comme la répétition 3) sur une trentaine de visites :
   aucune `duree_pages_reguliere` sur le sujet.
3. Une campagne de contrôle (même fichier que la 132) : mêmes taux à chaque cellule, pour s'assurer que la règle de
   défilement ne change rien ailleurs.
4. L'entrée par la liste devant la vraie Arena : une visite reprise après l'expiration de la porte (profil
   `enduranceporte150`, porte de 150 s, comme l'essai du 17/11) passe le défi sur la liste d'entrée sans alerte ; une
   visite reprise d'un visiteur banni (`shadowlab arena bannir` entre deux visites) s'arrête sur la liste d'entrée,
   identité `banni`, 0 page après.
5. Un bannissement en cours de visite devant la vraie Arena (`shadowlab arena bannir` pendant une visite, ou témoin
   sentinelle) : la visite finit, identité `banni`, 0 page après.
