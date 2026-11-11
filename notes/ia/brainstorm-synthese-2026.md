---
permalink: noezia-shadowlab/brainstorm-synthese-2026
title: brainstorm-synthese-2026
type: note
---

# Synthèse stratégique NOEZIA — 10 novembre 2026

*Plan d'action pour un fondateur pressé.*

---

## 1. Diagnostic

**Le moteur est à 3/10 et l'Arena fait semblant.** En une semaine (D-22 à D-29), on a itéré 8 versions du moteur (v4→v9) avec 24 détecteurs Arena — mais les détecteurs ne bloquent rien. Le gardien ne consulte que 6 des 32 détecteurs existants. Le moteur passe tout parce que l'adversaire est à genoux, pas parce qu'il est bon. On n'a aucune mesure fiable de ce qui marche et de ce qui casse.

## 2. L'erreur à ne pas faire

**Ne pas continuer à améliorer le moteur sans adversaire crédible.** Les versions v4→v9 ont amélioré des choses réelles (minimum-jerk, digraphs, patches JS), mais sans validation contre un adversaire fort, on ne sait pas si ces améliorations comptent en conditions réelles. On risque de passer 3 semaines à peaufiner du canvas noise alors que le vrai trou est dans le HTTP/2.

Autre erreur : viser un score arbitraire ("je veux 7/10") avant d'avoir défini ce que chaque point signifie. Le scoring doit être lié à des capacités vérifiables.

## 3. Les 5 actions par ordre de priorité

### Action 1 — Brancher les 26 détecteurs au gardien (2 jours)

**Quoi :** Modifier `gardien.py` pour que `suspicion()` lise la liste de détecteurs depuis le profil Arena au lieu des 6 hardcodés. Chaque niveau active progressivement plus de détecteurs.

**Impact :** Le moteur NOEZIA va probablement échouer à partir du niveau 03-04 révisé. C'est la mesure qu'on cherche — on saura EXACTEMENT quels signaux il rate.

**Risque :** Faux positifs si les seuils sont mal calibrés. Mitigation : campagne de calibration avec un vrai navigateur Chrome (session `/manuel`).

### Action 2 — Corriger ce que l'Arena durcie révèle (1-2 semaines)

**Quoi :** Une fois l'Arena branchée, lancer une campagne complète et corriger les détections dans l'ordre d'impact :
1. Canvas déterministe (double appel = même résultat) — 3 jours
2. Intégrité des patches JS (getOwnPropertyDescriptor, enumerable, prototype chain) — 4 jours  
3. Workers cohérents (main = worker sur toutes les propriétés) — 1 jour
4. Comportement de session (temps de lecture, scroll+pause, flux de navigation) — 4 jours

**Impact :** De ~3/10 à ~5/10. Le moteur passe les 6 niveaux Arena avec les détecteurs branchés.

### Action 3 — Score composite et corrélation cross-session (3 jours)

**Quoi :** Remplacer la logique binaire ("1 détecteur dit bot → bloqué") par un score pondéré. Ajouter la corrélation cross-session (même fingerprint vu N fois = bot).

**Impact :** Force le moteur à avoir des profils RÉELLEMENT divers. Avec 18 profils hardcodés, la corrélation les attrape en quelques sessions. Pousse vers un générateur procédural de profils.

### Action 4 — Diversité des profils (3 jours)

**Quoi :** Remplacer les 18 profils codés à la main par un générateur procédural basé sur des distributions réelles (StatCounter, WebGL Report, ChromeStatus). Base de fonts par OS collectée depuis des VMs.

**Impact :** De ~5/10 à ~6/10. Résiste à la corrélation cross-session.

### Action 5 — HTTP/2 fingerprint (5 jours)

**Quoi :** Capturer les SETTINGS HTTP/2 dans le frontal TLS. Nouveau détecteur côté Arena. Côté moteur : contrôler les settings HTTP/2 via Patchright ou un proxy.

**Impact :** C'est le signal le plus difficile à contourner — celui qui rapproche l'Arena des WAF commerciaux. Le 6/10 solide.

## 4. Jalons mesurables

### Jalon A — Arena crédible (fin action 1)
**Critère :** Le moteur NOEZIA échoue sur au moins 3 niveaux Arena avec les détecteurs branchés. Si il passe tout, c'est que les détecteurs existants ne sont pas assez forts → reprioriser.
**Délai :** 2 jours.

### Jalon B — Moteur robuste (fin actions 2-4)
**Critère :** Le moteur NOEZIA passe les 6 niveaux Arena durcie (32 détecteurs actifs + corrélation cross-session) avec un score composite sous le seuil.
**Délai :** 3 semaines après jalon A.

### Jalon C — Empreinte réseau (fin action 5)
**Critère :** Le nouveau détecteur HTTP/2 distingue correctement Chrome, Firefox, curl, Go et Python. Le moteur NOEZIA a des settings HTTP/2 cohérents avec son UA.
**Délai :** 1 semaine après jalon B.

## 5. Risques

1. **Le frontal TLS ne peut pas capturer HTTP/2 SETTINGS** — si la pile Docker (Nginx/Coraza) ne transmet pas les frames HTTP/2 au backend, il faut un composant dédié (mitmproxy, go-proxy). Effort ×2.

2. **Patchright change** — si Patchright modifie sa mécanique de lancement Chromium, tous nos patches JS peuvent casser. Mitigation : épingler la version, surveiller les releases.

3. **L'Arena n'est pas Cloudflare** — même avec 32 détecteurs + HTTP/2, l'Arena reste un lab local. Le vrai test est contre un WAF commercial. On peut approcher du 6/10 sans jamais avoir confirmé contre Cloudflare. Mitigation : jalon D (futur) = test ponctuel contre Cloudflare Free sur un domaine de test qu'on possède.

4. **Perfectionnisme** — avec 32 détecteurs et un scoring composite, on peut passer des mois à optimiser chaque signal. Le bon compromis : passer les 6 niveaux avec 0 détection `automatise`, pas chercher un score parfait.

---

## Budget total estimé

| Phase | Effort | Résultat |
|-------|--------|----------|
| Arena crédible | 2 jours | On sait ce qui casse |
| Corrections moteur | 12 jours | Le moteur tient l'Arena |
| Score + corrélation | 3 jours | Signaux faibles additionnés |
| Profils diversifiés | 3 jours | Résiste à la corrélation |
| HTTP/2 | 5 jours | Signal réseau crédible |
| **Total** | **~25 jours** | **De 3/10 à 6/10** |

Pour le 7/10 (passer Cloudflare Free de manière reproductible), il faut un test réel — compter 1 semaine supplémentaire de calibration.

---

*Synthèse rédigée le 10/11/2026 à partir de : audit-arena-2026.md, audit-moteur-2026.md, recherche-antibot-2026.md, 2026-11-08-noezia-v4-design.md, DECISIONS.md (D-01 à D-32).*