---
permalink: noezia-shadowlab/contexte
title: contexte
type: note
---

# Contexte de noezia-shadowlab, en une lecture

## Ce que c'est
- Laboratoire local de R&D NOEZIA : compare Playwright, Selenium, Scrapling (client HTTP) et httpx face à
  des détecteurs anti-bot (BotD + règles HTTP, JS, cohérence) sur un site de test servi par la même machine.
- Demandé par Ethan le 03/11/2026 (cahier des charges « NOEZIA ShadowLab ») ; périmètre local strict, sans
  contournement de CAPTCHA ni modification d'empreinte.

## État au 2026-11-03
- MVP complet et testé (46 tests) : voir `AGENTS.md` § État et `notes/ia/journal.md`.
- À faire par Ethan : quelques sessions humaines sur http://127.0.0.1:8770/manuel (faux positifs).
- Phases restantes : Docker Compose, TLS (mitmproxy), concurrence, moteurs de la phase 6.