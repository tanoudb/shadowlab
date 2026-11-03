# Décisions — NOEZIA ShadowLab

Format : `D-xx — date — décision (pourquoi)`. Une décision remplacée est barrée avec un renvoi.

- **D-01 — 03/11/2026 — Python, FastAPI, SQLite, `uv`.** Un seul langage pour le lanceur, le site et l'API ;
  SQLite suffit au prototype (un fichier, mode WAL pour deux processus) ; migrations maison numérotées.
- **D-02 — 03/11/2026 — Un seul serveur FastAPI pour le site de test, la détection, l'API et le tableau de
  bord**, au lieu de quatre services. Moins de pièces pour un MVP local ; les modules restent séparés
  (`site/`, `detection.py`, `api.py`, `tableau.py`) pour être éclatés plus tard.
- **D-03 — 03/11/2026 — Le site de test tourne dans un processus à part pendant une campagne.** Dans le même
  processus, son CPU comptait dans chaque passage (≈ 98 % mesuré pour les clients HTTP sur l'essai).
- **D-04 — 03/11/2026 — Moteurs dans leur configuration standard, seuls deux réglages imposés** : pas de
  redirection suivie par la bibliothèque (le périmètre contrôle chaque étape) et une seule tentative pour
  Scrapling (les erreurs sont comptées, pas masquées).
- **D-05 — 03/11/2026 — `StealthyFetcher` de Scrapling non intégré.** C'est un navigateur modifié pour échapper
  aux détecteurs ; le cahier des charges exclut les modifications d'empreinte. Seul le client HTTP
  `FetcherSession` est intégré.
- **D-06 — 03/11/2026 — `httpx` ajouté comme témoin brut** (aucun réglage d'en-têtes) : il donne le point
  bas de comparaison pour les clients HTTP.
- **D-07 — 03/11/2026 — Verrou réseau pour les deux navigateurs** (mandataire bloquant `127.0.0.1:9`, exceptions
  = hôtes autorisés). Le filtre `route` de Playwright laissait passer les redirections : un test l'a montré
  (redirection vers `example.com` suivie). Selenium n'a pas de filtre de requêtes.
- **D-08 — 03/11/2026 — BotD servi en local, `monitoring: false`.** Pas de CDN ; la statistique d'usage que
  BotD envoie à FingerprintJS est coupée ; la politique de sécurité du site bloque toute sortie.
- **D-09 — 03/11/2026 — Classement en trois valeurs (`automatise`, `humain`, `indetermine`).** Un détecteur
  qui n'a pas de quoi trancher s'abstient ; l'abstention est rapportée à part et n'entre ni dans les vrais ni
  dans les faux. Intervalles de Wilson à 95 %.
- **D-10 — 03/11/2026 — Faux positifs mesurés uniquement sur des sessions humaines réelles** (`/manuel`). Aucune
  session « humaine » simulée par un automate : ce serait une fausse référence.
- **D-11 — 03/11/2026 — Temps CPU en ms ajouté au pourcentage** (migration 2). Sur un passage de 2 ms, le
  pourcentage d'un cœur est proche de 100 % et ne dit rien de la consommation réelle.
- **D-12 — 03/11/2026 — Règles HTTP v2** : demande `Upgrade: h2c`, `Host` hors de la première place en HTTP/1.1,
  `Referer` avec `Sec-Fetch-Site: none`. Relevées sur le client HTTP de Scrapling, que les règles v1 classaient
  « humain » ; ce sont des incohérences qu'aucun navigateur ne produit.
- **D-13 — 03/11/2026 — Docker Compose reporté.** OrbStack n'était pas lancé et rien ne l'exige pour tourner en
  local ; une image non vérifiée serait pire que pas d'image. À faire avec le déploiement sur Linux.
