# Architecture de ShadowLab

## Vue d'ensemble

```
             fichier YAML ──► campaigns.lire()  (validation stricte + périmètre)
                                   │
                                   ▼
 ┌──────────────── lanceur (processus principal) ────────────────┐      ┌──── site (processus à part) ────┐
 │ campaigns.executer()                                          │      │ FastAPI                          │
 │   pour chaque moteur : Driver.open()                          │ HTTP │  /lab/*      pages de test       │
 │     pour chaque répétition, scénarios dans un ordre tiré      │─────►│  middleware  en-têtes reçus      │
 │       Driver.start_session() → scénario → close_session()     │      │  /lab/collecte  relevés JS       │
 │       Echantillonneur : CPU, mémoire (hors site)              │      │  /manuel     sessions humaines   │
 │       passages.finaliser() : détecteurs → base                │      │  /api, /tableau                  │
 └──────────────────────────────┬────────────────────────────────┘      └───────────────┬──────────────────┘
                                │            SQLite (WAL, même fichier)                 │
                                └──────────────────────► outputs/shadowlab.sqlite3 ◄────┘
```

Un **passage** est une session d'un moteur sur un scénario. Chaque passage reçoit un jeton aléatoire, transmis
au site par le paramètre `sl` puis par un cookie : c'est lui qui relie ce que le moteur a fait à ce que le site
a observé.

## Flux d'un passage

1. `passages.demarrer()` crée la ligne `runs` (état `en_cours`) et le jeton.
2. `Driver.start_session()` ouvre une session neuve : contexte Playwright, cookies et cache vidés pour Selenium,
   client neuf pour les clients HTTP.
3. Le scénario agit par l'interface commune (`navigate`, `click`, `fill`, `select`, `wait_for_element`,
   `texts`, `content`) et vérifie son résultat attendu.
4. Côté site, chaque requête `/lab` est enregistrée (`observations_http`, en-têtes dans l'ordre reçu) ;
   l'observateur JavaScript envoie l'empreinte et le verdict BotD (`observations_js`), puis un relevé de
   comportement à la sortie de la page.
5. `close_session()` quitte la page (ce qui déclenche l'envoi du relevé de comportement).
6. `passages.finaliser()` relit les observations, fait classer la session par chaque détecteur, puis écrit
   empreinte, verdicts, mesures et fin du passage, en une transaction.

## Base de données

Tables du cahier des charges (`experiments`, `engines`, `runs`, `fingerprints`, `detections`, `metrics`,
`artifacts`), plus `scenarios` et les observations brutes (`observations_http`, `observations_js`).
Migrations : liste ordonnée dans `database.MIGRATIONS`, numéro atteint dans `PRAGMA user_version`. Pour
modifier le schéma, **ajouter** une migration à la fin, ne jamais modifier une migration existante.

Une configuration de moteur est identifiée par son nom, ses versions exactes (bibliothèque, navigateur, pilote)
et sa configuration effective : un changement de version crée une nouvelle ligne `engines`, ce qui permet de
comparer deux versions.

## Reproductibilité

- La graine de la campagne fixe l'ordre des scénarios et les valeurs saisies dans les formulaires ; elle est
  enregistrée même quand elle est tirée au hasard.
- Versions enregistrées : ShadowLab, Python, système, puce, chaque bibliothèque et chaque navigateur.
- La reprise rejoue seulement les couples (moteur, scénario, répétition) absents ou restés « en cours ».

## Mesures

- **Durée** : du début de la session à la fin du scénario, en ms (horloge monotone).
- **CPU** : temps CPU consommé par le lanceur et tous ses descendants (pilote, navigateur, moteurs de rendu),
  hors site de test, relevé toutes les 100 ms par `psutil`. Stocké en ms et en % moyen d'un cœur.
- **Mémoire** : somme des mémoires résidentes du même arbre ; maximum et moyenne par passage.
- **Requêtes et erreurs** : comptées par le pilote (événements Playwright, entrées `performance` pour Selenium,
  appels pour les clients HTTP).

## Périmètre

| Moteur | Comment le périmètre est tenu |
|---|---|
| Clients HTTP | URL contrôlée avant chaque requête ; redirections suivies à la main, chacune contrôlée |
| Playwright | URL contrôlée avant `navigate` ; filtre `route` (requêtes directes) ; **verrou réseau** du navigateur |
| Selenium | URL contrôlée avant `navigate` ; **verrou réseau** du navigateur |

Le verrou réseau : le navigateur reçoit un mandataire inexistant (`127.0.0.1:9`, port fermé) et une liste
d'exceptions égale aux hôtes autorisés. Tout ce qui sort de la liste échoue (`ERR_PROXY_CONNECTION_FAILED`).
Il a été ajouté après qu'un test a montré que le filtre `route` de Playwright n'intercepte pas les redirections
(`tests/test_integration.py::test_moteur_refuse_une_redirection_hors_perimetre`).

## Limites

- **TLS non observé** : le site est servi en HTTP local et uvicorn n'expose pas le ClientHello. Pour l'étudier,
  il faudrait terminer TLS dans un composant qui le lit (mitmproxy, ou un petit serveur dédié).
- **Pas d'exécution concurrente** : `concurrency` doit valoir 1. La structure (un pilote par moteur, passages
  indépendants) le permet ; la mesure CPU par passage deviendrait alors approximative.
- **Mesure des ressources** : un navigateur partagé entre passages compte dans chacun ; un processus né et mort
  entre deux relevés (100 ms) échappe à la mesure.
- **Faux positifs** : mesurables seulement avec des sessions humaines (`/manuel`). Sans elles, précision et F1
  sont « non mesurables ».
- **Détecteurs locaux** : BotD et des règles simples. Un service externe observe bien plus (réputation des
  adresses, TLS, historique, comportement sur la durée) ; une absence de détection ici ne prouve rien ailleurs.
- **Selenium** : pas de contexte isolé dans WebDriver (cookies et cache vidés entre passages) ; pas de corps
  brut de réponse (texte affiché pour un JSON).
- **Scrapling 0.5** : seul le client HTTP est intégré. `StealthyFetcher` (navigateur modifié pour échapper aux
  détecteurs) est hors périmètre ; Scrapling 0.5 n'expose plus de navigateur « dynamique » standard.
- **Contrôle DNS avant la requête, pas à la connexion** : le périmètre résout le nom puis la bibliothèque le
  résout à nouveau. Un nom autorisé dont le DNS changerait entre les deux (« DNS rebinding ») passerait. La liste
  par défaut (`127.0.0.1`, `localhost`) n'est pas concernée ; n'ajouter que des noms dont on maîtrise le DNS.
- **Pas encore de Docker Compose** ni d'image : le projet tourne avec `uv` (voir `docs/DECISIONS.md`).
