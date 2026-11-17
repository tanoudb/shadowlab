# Quel anti-bot du commerce mettre devant une cible à nous (étape 3.4) — recherche du 17/11/2026

Question d'Ethan (17/11) : pour mesurer notre niveau face à un vrai fournisseur anti-bot, quelles protections peut-on poser **sur un domaine à nous** (essai ou offre en libre-service) ?
Recherche web seulement : rien n'a été acheté, installé ni créé. **Les sources sont en majorité des comparateurs et des annuaires** ; seul ce qui vient de la documentation de Cloudflare est de première main.
Ce qui n'est pas confirmé est dit comme tel. Aucun prix n'est à tenir pour sûr avant d'avoir regardé la page du fournisseur.

## Résumé

1. **Cloudflare est la voie la plus simple et la seule dont la documentation est confirmée** : la vitrine sur un domaine à nous derrière Cloudflare, comme le plan le prévoit (§ 1, 3.4).
   - **Plan gratuit** : Bot Fight Mode. Il défie les requêtes qui ressemblent à des robots, active seul les détections JavaScript, mais **n'est pas réglable** (ni règles d'exception, ni réglage par catégorie) et ne protège que tout le domaine.
   - **Plan Pro et au-dessus** : Super Bot Fight Mode. Action choisie par catégorie (« sûrement automatisé », « probablement automatisé », robots vérifiés), protection des ressources statiques, détections JavaScript, règles d'exception, rapport des robots sur 24 heures.
   - **Bot Management (les scores)** : option de l'offre Enterprise, sur devis. C'est la seule qui donne un score de robot par requête.
2. **AWS WAF Bot Control** est la seule offre « du commerce » que j'ai trouvée en libre-service, payée à l'usage, avec un niveau « ciblé » (apprentissage, empreinte du navigateur, comportement). Elle suppose un compte AWS et la vitrine derrière CloudFront ou un équilibreur AWS.
3. **DataDome, HUMAN, Kasada, Akamai Bot Manager, Imperva** : conclusion commerciale, pas de libre-service trouvé. Pour DataDome, les sources se contredisent sur l'essai (30 jours d'après des annuaires, « sur demande » d'après d'autres) ; sa page de prix a refusé ma lecture (403).
4. **Recommandation** : 3.4 avec Cloudflare d'abord (gratuit pour un premier relevé, Pro pour pouvoir durcir le réglage), AWS WAF Bot Control ensuite si on veut un second fournisseur de nature différente, DataDome seulement si Ethan obtient un essai écrit.

## Détail par offre

| Offre | Libre-service ? | Ce que la source dit | Confiance |
|---|---|---|---|
| **Cloudflare, plan gratuit : Bot Fight Mode** | oui | « Un produit simple et gratuit » ; défie les requêtes qui ressemblent à des robots ; défis qui coûtent du calcul au robot ; détections JavaScript automatiques et non désactivables ; **ne se règle pas** (aucune règle d'exception, pas de réglage par catégorie) ; journal des requêtes défiées dans « Security > Analytics > Events » ; ne tourne pas sur le moteur de règles, donc Skip/Allow des règles personnalisées sont sans effet | documentation Cloudflare |
| **Cloudflare, Pro et plus : Super Bot Fight Mode** | oui, payant | Disponible sur Pro, Business et Enterprise ; actions par groupe (sûrement automatisé, probablement automatisé, robots vérifiés) ; protection des ressources statiques ; détections JavaScript ; règles d'exception par Skip ; rapport des robots sur les 24 dernières heures ; bloquer les robots d'IA. À désactiver : Bot Fight Mode avant de passer au suivant | documentation Cloudflare. **Prix non confirmé** (un comparatif parle de 200 $ par mois pour Business : non vérifié) |
| **Cloudflare Bot Management** | non (devis) | Option de l'offre Enterprise ; seul niveau avec un score par requête | documentation Cloudflare (mention seule) ; prix : devis |
| **AWS WAF Bot Control** | oui, à l'usage | Niveau « commun » : 10 $ par liste de contrôle et par mois + 1 $ par million de requêtes (les 10 premiers millions gratuits d'après la page de prix) ; niveau « ciblé » : 10 $ par mois + 10 $ par million (le premier million gratuit) ; CAPTCHA 0,40 $ les 1 000 tentatives. Doit se poser devant CloudFront ou un équilibreur AWS | page de prix d'AWS (via moteur de recherche) ; un compte AWS et un moyen de paiement sont nécessaires |
| **DataDome** | essai à confirmer | Un annuaire parle d'un essai de 30 jours ; un autre de « sur demande » ; prix annoncés d'environ 3 830 $ par mois (Essentials) : tous ces chiffres viennent d'annuaires, la page de prix officielle n'a pas pu être lue | faible : à demander à DataDome |
| **HUMAN (ex-PerimeterX), Kasada, Akamai Bot Manager, Imperva** | non trouvé | Offres sur contrat, essai ou démonstration sur demande ; sources contradictoires pour Akamai et Imperva (Kasada : « pas d'essai ») | faible |

## Ce que chaque option permet de mesurer (et ce qu'elle ne permet pas)

- Le plan § 1 fixe la règle de comptage : aucun défi → réussi ; un défi qui se valide seul → réussi, compté à part ; un défi avec action (case à cocher, puzzle) → échec (le moteur ne clique pas) ;
  la mesure ne vaut que si le témoin `playwright` est arrêté dans la majorité de ses passages, sinon on durcit le réglage chez le fournisseur.
- **Plan gratuit de Cloudflare** : peut ne pas arrêter le témoin (réglage non modifiable). C'est le risque de « mesure qui ne vaut rien » que le plan prévoit ; les règles personnalisées du plan gratuit
  (un défi sur le chemin de la vitrine) restent à vérifier (nombre autorisé, actions disponibles) : **non confirmé**.
- **Pro** : permet de durcir (bloquer « sûrement automatisé », défier « probablement automatisé ») et de mettre des exceptions ; pas de score par requête.
- **AWS WAF Bot Control ciblé** : plus proche d'un fournisseur spécialisé (signaux de navigateur et de comportement) ; deux niveaux, donc deux mesures ; les journaux de décision sont disponibles dans AWS (à vérifier lors de la mise en place).
- **Aucune** de ces options ne dit si notre moteur « passerait Vinted » : une protection réglée par un tiers sur son site réel n'est pas la protection par défaut d'une offre. On mesure un taux de passage contre une protection **nommée et réglée par nous**.

## Règles qui restent vraies

- Cibles à nous seulement (D-30) ; aucun solveur de CAPTCHA réel ; un défi avec action est un échec ; `captcha_test` jamais confondu avec une vraie victoire.
- Un contournement trouvé contre un fournisseur : divulgation coordonnée (D-30), même si la cible est à nous.
- Créer un compte (Cloudflare, AWS), payer, acheter un domaine : **à Ethan**, jamais à l'assistant (consigne de sécurité du projet).

## Ce qu'il faut d'Ethan pour lancer la 3.4

1. Un domaine à lui pour la vitrine (déjà attendu au § 7 du plan, pour l'application publique), et son compte Cloudflare.
2. Le choix du niveau : gratuit d'abord, Pro seulement si le témoin n'est pas arrêté.
3. Facultatif : un compte AWS (second fournisseur) ; une demande d'essai à DataDome en son nom.
4. Toujours attendus : un serveur Linux x86_64 avec Docker et un proxy résidentiel (étapes 3.3 et 3.4) ; le proxy par identité existe maintenant (3.2) mais n'a jamais été essayé avec un vrai fournisseur.

## Sources

- Cloudflare, Bot Fight Mode : <https://developers.cloudflare.com/bots/get-started/bot-fight-mode/>
- Cloudflare, Super Bot Fight Mode : <https://developers.cloudflare.com/bots/get-started/super-bot-fight-mode/>
- AWS WAF, prix : <https://aws.amazon.com/waf/pricing> (lu par un moteur de recherche, pas directement) ; recoupement : <https://innfactory.de/en/cloud/aws/products/waf-captcha/>
- DataDome (annuaires, non officiel) : <https://capterra.com/p/149769/datadome-bot-mitigation> ; <https://cside.com/blog/datadome-pricing> ; page de prix officielle <https://datadome.co/pricing/> : lecture refusée (403)
- Comparatifs des autres fournisseurs : <https://www.krowdbase.com/best-bot-detection-mitigation-software-small-businesses> ; <https://www.comparitech.com/net-admin/perimeterx-review/> ; <https://comparitech.com/net-admin/akamai-bot-manager-review>
