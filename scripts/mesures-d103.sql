-- Verdict des mesures de D-103 (docs/recherche/course-i9-visite-6-2026-11-18.md, § 5), lu dans la base du labo.
-- Lecture seule. Le numéro de campagne est le paramètre @n :
--   sqlite3 -readonly -header -column -cmd ".parameter set @n <n°>" outputs/shadowlab.sqlite3 < scripts/mesures-d103.sql
-- Signaux : ceux du détecteur `comportement` relus sur toute la session à la fin du passage (table `detections`) ;
-- blocages : les décisions `bloque` ou `detecte` du gardien pendant la visite (table `decisions`), défis non compris.

.print '== 1. Chaque visite'
SELECT r.repetition AS visite,
       substr(m.nom, instr(m.nom, ':') + 1) AS bras,
       r.status AS statut,
       r.success AS reussie,
       json_extract(r.drapeaux, '$.details_scenario.passe') AS passe,
       json_extract(r.drapeaux, '$.details_scenario.incrementale') AS incr,
       json_extract(r.drapeaux, '$.details_scenario.pages_visite') AS pages,
       json_extract(r.drapeaux, '$.details_scenario.recolte.annonces_retrouvees') AS annonces,
       json_extract(r.drapeaux, '$.details_scenario.identite.etat') AS identite,
       (SELECT count(*) FROM decisions d
         WHERE d.session_token = r.session_token AND d.decision IN ('bloque', 'detecte')) AS blocages,
       (SELECT count(*) FROM detections d, json_each(d.signals) s
         WHERE d.run_id = r.id AND d.detector_name = 'comportement'
           AND json_extract(s.value, '$.code') = 'pas_de_scroll') AS pas_de_scroll,
       (SELECT count(*) FROM detections d, json_each(d.signals) s
         WHERE d.run_id = r.id AND d.detector_name = 'comportement'
           AND json_extract(s.value, '$.code') = 'navigation_lineaire') AS nav_lineaire,
       (SELECT count(*) FROM detections d, json_each(d.signals) s
         WHERE d.run_id = r.id AND d.detector_name = 'comportement'
           AND json_extract(s.value, '$.code') = 'duree_pages_reguliere') AS duree_reguliere,
       json_extract(r.drapeaux, '$.details_scenario.arret.detail') AS arret
  FROM runs r JOIN mondes m ON m.id = r.monde_id
 WHERE r.experiment_id = @n
 ORDER BY bras, r.repetition;

.print ''
.print '== 2. Début de chaque visite (pages de la vitrine, dans l''ordre ; une visite reprise : la liste, puis une fiche neuve)'
SELECT r.repetition AS visite,
       substr(m.nom, instr(m.nom, ':') + 1) AS bras,
       (SELECT group_concat(replace(chemin, '/lab/vitrine/annonces', 'L'), ' > ')
          FROM (SELECT o.path AS chemin FROM observations_http o
                 WHERE o.session_token = r.session_token AND o.path LIKE '/lab/vitrine/annonces%'
                 ORDER BY o.id LIMIT 4)) AS debut,
       (SELECT count(*) FROM observations_http o
         WHERE o.session_token = r.session_token AND o.path LIKE '/lab/vitrine/annonces%') AS documents
  FROM runs r JOIN mondes m ON m.id = r.monde_id
 WHERE r.experiment_id = @n
 ORDER BY bras, r.repetition;

.print ''
.print '== 3. Défis de la porte (defi-js) : émis sur quelle page, et validés'
SELECT r.repetition AS visite,
       substr(m.nom, instr(m.nom, ':') + 1) AS bras,
       d.decision,
       d.chemin,
       d.created_at AS quand
  FROM decisions d
  JOIN runs r ON r.session_token = d.session_token
  JOIN mondes m ON m.id = r.monde_id
 WHERE r.experiment_id = @n AND d.couche = 'defi-js'
 ORDER BY d.id;

.print ''
.print '== 4. Bannissements dans les mondes de la campagne'
SELECT m.nom AS monde, b.visiteur, b.empreinte, b.motif, b.cree_le
  FROM bannissements b JOIN mondes m ON m.id = b.monde_id
 WHERE m.nom LIKE 'c' || @n || ':%'
 ORDER BY b.id;

.print ''
.print '== 5. Bilan par bras'
SELECT substr(m.nom, instr(m.nom, ':') + 1) AS bras,
       count(*) AS visites,
       sum(r.success = 1) AS reussies,
       sum((SELECT count(*) FROM decisions d
             WHERE d.session_token = r.session_token AND d.decision IN ('bloque', 'detecte')) > 0) AS bloquees,
       sum((SELECT count(*) FROM detections d, json_each(d.signals) s
             WHERE d.run_id = r.id AND d.detector_name = 'comportement'
               AND json_extract(s.value, '$.code') = 'pas_de_scroll')) AS pas_de_scroll,
       sum((SELECT count(*) FROM detections d, json_each(d.signals) s
             WHERE d.run_id = r.id AND d.detector_name = 'comportement'
               AND json_extract(s.value, '$.code') = 'navigation_lineaire')) AS nav_lineaire,
       sum((SELECT count(*) FROM detections d, json_each(d.signals) s
             WHERE d.run_id = r.id AND d.detector_name = 'comportement'
               AND json_extract(s.value, '$.code') = 'duree_pages_reguliere')) AS duree_reguliere
  FROM runs r JOIN mondes m ON m.id = r.monde_id
 WHERE r.experiment_id = @n
 GROUP BY bras;

.print ''
.print '== 6. Après le premier refus « bannissement » d''une visite : tout ce qui a encore été demandé (rien d''autre que la page refusée et ses ressources)'
SELECT r.repetition AS visite,
       substr(m.nom, instr(m.nom, ':') + 1) AS bras,
       d.couche,
       d.decision,
       d.chemin,
       d.created_at AS quand
  FROM runs r
  JOIN mondes m ON m.id = r.monde_id
  JOIN decisions d ON d.session_token = r.session_token
 WHERE r.experiment_id = @n
   AND d.id >= (SELECT min(d2.id) FROM decisions d2
                 WHERE d2.session_token = r.session_token AND d2.couche = 'bannissement')
 ORDER BY d.id;
