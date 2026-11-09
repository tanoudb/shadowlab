# Sécurité à finaliser (durcissement différé)

> **Statut : phase interne / expérimentale.** On construit le moteur à pleine puissance.
> Les garde-fous de périmètre sont **débrayés par défaut** pour ne pas freiner l'expérimentation.
> Ce fichier liste ce qui est relâché et **ce qu'il faut rebasculer avant que le projet sorte de
> l'usage interne** (livraison, vente, test sur une cible externe). Décision : D-30 (voir `docs/DECISIONS.md`).

## Principe

Le mécanisme de sécurité n'est **pas supprimé**, il est **débrayé**. Re-durcir = rebasculer un
interrupteur, pas réécrire. C'est voulu : « on sécurise à la fin » doit rester une ligne, pas un chantier.

## Ce qui est relâché aujourd'hui

| Garde-fou | État phase interne | Re-durcissement final |
|---|---|---|
| Périmètre réseau (destinations joignables) | **Illimité** : `SHADOWLAB_HOTES_AUTORISES=*` (défaut). `verifier_url` et le verrou réseau laissent tout passer. | Fixer `SHADOWLAB_HOTES_AUTORISES` à une **liste explicite** d'hôtes autorisés. Le mode strict (rejet par défaut, contrôle anti-SSRF des noms qui résolvent vers un réseau interne) revient automatiquement. |
| Contournement de détecteur commercial | Autorisé sur **cibles autorisées + divulgation coordonnée**. | Politique d'engagement écrite (scope, autorisation, canal de disclosure) avant toute cible externe. |

## Ce qui reste armé en permanence (ne pas débrayer)

- **Pas de solveur de CAPTCHA réel** (reCAPTCHA / hCaptcha / Turnstile prod). Un solveur ne corrige
  aucune faille : il rend la vérification humaine inutile pour tous, et viole les ToS des fournisseurs
  (mine légale pour un produit vendable). Le CAPTCHA démo de l'Arena et les test keys restent permis.
- **Aucune mesure inventée** ; les résultats en test keys sont étiquetés comme tels. Intégrité
  scientifique : ça ne bride pas le moteur, ça garantit que les chiffres sont vrais.
- **Garde anti-DNS-rebinding du serveur de test** (`controler_hote`) : reste strict, indépendant du
  périmètre moteur. Le `*` ne s'y applique pas.

## Check-list avant sortie de l'interne

- [ ] `SHADOWLAB_HOTES_AUTORISES` = liste explicite (retirer `*`).
- [ ] Vérifier que `uv run pytest -m integration` repasse au vert en mode strict
      (`test_moteur_refuse_une_redirection_hors_perimetre`).
- [ ] Politique d'engagement + canal de divulgation documentés pour toute cible externe.
- [ ] Revue : aucune mesure non étiquetée, aucun solveur de CAPTCHA réel introduit.
- [ ] Barrer D-30 dans `docs/DECISIONS.md` et pointer la décision de re-durcissement.

## Où c'est dans le code

- `src/shadowlab/perimetre.py` — `ILLIMITE = "*"`, court-circuit dans `verifier_url`.
- `src/shadowlab/engines/base.py` — `liste_directe` renvoie `["*"]` (verrou réseau levé) en illimité.
- `src/shadowlab/config.py` — défaut `SHADOWLAB_HOTES_AUTORISES=*`.
- `src/shadowlab/site/app.py` — `hotes_servis` filtre le `*` (le serveur de test reste strict).
