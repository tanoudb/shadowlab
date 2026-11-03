"""Anti-Bot Arena : protections locales en couches, chacune enregistre ses décisions et leurs motifs.

Chaîne d'une requête : frontal TLS (observation) → Nginx (limitation de débit) → Coraza + OWASP CRS (WAF)
→ site de test (défi JavaScript, CAPTCHA de démonstration). Détail : `docs/arena.md`.
"""
