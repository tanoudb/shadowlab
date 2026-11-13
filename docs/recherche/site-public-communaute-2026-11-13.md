# Site public pour la communauté — cadrage (13/11/2026)

Demande d'Ethan (13/11, 23 h 30), ses mots : « deux faux beaux sites pour que je puisse mettre sur le
Cloudflare », pour « demander à des gens de le tester », en leur disant que « c'est pour une analyse sur
comment les humains utilisent un navigateur et comment différencier un humain d'une IA » ; « voir le nombre de
gens qui visitent » ; « anglais ou français, on met les deux » ; « un beau truc, que ça leur donne envie de se
balader dessus » ; « un truc qui analyse tout et que les gens sont au courant ».

## But
Récolter des sessions humaines (étape 1.7 du plan) auprès d'une communauté (Reddit, amis), pour calibrer
l'Arena : savoir quels détecteurs prennent de vraies personnes pour des robots. Le site doit donner envie de
se promener 5 à 10 minutes, et dire clairement ce qui est relevé.

## Ce qu'on construit (tout dans l'application publique, `src/shadowlab/public/`)
1. **Une page d'accueil de l'étude**, belle, en français et en anglais : ce qu'est l'étude, ce qu'on fait
   (se promener sur deux sites de démonstration), ce qui est relevé et ce qui ne l'est pas (résumé), le
   compteur de sessions, les deux sites en vignettes, la case d'accord et le bouton pour commencer. La notice
   complète (celle d'aujourd'hui) reste accessible en un clic, dans les deux langues, avant d'accepter.
2. **Deux sites de démonstration** : Habitat Démo (annonces immobilières, déjà dans l'application publique)
   et Chrono Démo (résultats de rallye, aujourd'hui seulement dans le labo). Mêmes chemins que dans le labo
   (`/lab/vitrine/…`, `/lab/rallye/…`), pour que `shadowlab rejeu --base` rejoue les sessions telles quelles.
3. **Un habillage public** : une feuille de style en plus, servie seulement par l'application publique, qui
   rend les deux sites beaux sans changer leur HTML.
4. **La fréquentation** : un compte par jour (chargements de l'accueil, sessions commencées, sessions
   terminées), sans rien sur les personnes ; une commande `shadowlab public frequentation` ; le nombre de
   sessions affiché sur l'accueil.

## Règles (non négociables)
- **Les pages du labo ne changent pas d'un octet.** Les recettes de récolte et la vérité dépendent de leur
  HTML, et la campagne de contrôle de D-74 doit se comparer à la 108. Tout crochet ajouté dans
  `site/vitrine.py` ou `site/rallye.py` est additif, avec la page d'aujourd'hui par défaut, verrouillé par un
  test écrit avant la modification.
- **Politique de sécurité inchangée** (`default-src 'self'; script-src 'self'; style-src 'self'; img-src
  'self' data:`) : aucune ressource extérieure, aucun script ni style dans la page, aucun attribut `style=`,
  aucune police téléchargée ailleurs. Donc un dessin original, pas un modèle pris sur Internet.
- **Trois cookies, pas un de plus.** La langue passe par l'adresse (`/fr/…`, `/en/…`) et, pendant une
  session, par la langue notée avec l'accord ; sans session, par la langue du navigateur. Pas de cookie de
  langue.
- **Aucune route du labo**, comme aujourd'hui : le test qui le garantit couvre aussi toutes les pages du
  rallye.
- **La notice dit vrai, dans les deux langues.** Le test qui compare la liste des données à
  `observateur.js`, clé par clé, couvre les deux langues. `VERSION_INFORMATION` change. Les phrases « rien
  n'est enregistré » (visite sans participer) et « aucune mesure d'audience » sont réécrites pour dire le
  compte par jour.
- **Le but annoncé ne change pas** : mesurer combien de vraies personnes nos détecteurs classent à tort comme
  des robots. Les sessions publiques ne servent à rien d'autre (pas à régler le moteur), tant qu'Ethan n'a
  pas décidé d'annoncer un second but.
- Pas de page « votre résultat » (verdict des détecteurs montré au visiteur) dans cette version : mettre les
  verdicts en ligne est une décision d'Ethan.
- Le contenu généré des deux sites (annonces, rallyes) reste en français : c'est la vérité des récoltes.
  L'accueil le dit en une phrase aux visiteurs anglophones.

## Langue
Ordre : préfixe de l'adresse (`/fr`, `/en`) ; sinon langue de la session ; sinon `Accept-Language` ; sinon
français. `/` rend l'accueil dans la langue du navigateur, avec un lien visible vers l'autre langue. La langue
choisie est notée dans l'accord de la session (et listée dans la notice).

## Textes de l'accueil (à garder tels quels, sens compris)
- Titre : « Humain ou robot ? » / “Human or bot?”
- Sous-titre : « Une étude ouverte sur la façon dont de vraies personnes naviguent sur le Web. » /
  “An open study of how real people browse the web.”
- Accroche : « Les sites se protègent des robots avec des détecteurs. Ces détecteurs se trompent parfois et
  prennent de vraies personnes pour des robots. Aidez-nous à mesurer ces erreurs : promenez-vous 5 à 10
  minutes sur deux sites de démonstration, comme vous le feriez sur de vrais sites. » /
  “Websites use detectors to keep bots out. Those detectors sometimes get it wrong and flag real people.
  Help us measure how often: spend 5 to 10 minutes browsing two demo sites, the way you would browse real
  ones.”
- Franchise : « Pendant la session, nous relevons les caractéristiques de votre navigateur et votre façon
  de naviguer, en chiffres. Ni votre adresse IP, ni ce que vous tapez, ni la position de votre souris. Vous
  pouvez tout supprimer d'un clic. » / “During the session we record your browser's characteristics and how
  you browse, as numbers. Not your IP address, not what you type, not where your mouse is. You can delete
  everything with one click.”
- Compteur : « N sessions enregistrées à ce jour » / “N sessions recorded so far”.

## Ordre de fabrication
1. Fond (un agent) : crochets additifs et tests de non-changement du labo ; rallye dans l'application
   publique ; langues ; accueil et notice ; fréquentation et commande ; décision et notice dans le même commit.
2. Forme (un agent) : dessin de l'accueil et habillage des deux sites, ordinateur et téléphone.
3. Contrôles (coordination) : chaque type de page à l'écran, console sans erreur de politique de sécurité ;
   une session complète (deux sites, deux langues) puis `shadowlab rejeu --base` : aucun signal dû à
   l'habillage ; quatrième relecture indépendante vie privée et sécurité ; plafonds de stockage.
4. Ethan : regarde, décide du but annoncé, lance le tunnel lui-même.

## Question ouverte pour Ethan
Les sessions publiques servent-elles seulement à mesurer les erreurs des détecteurs (recommandé, c'est ce
que dit la notice et son message), ou aussi à comparer les humains à notre moteur d'automatisation ? Dans le
second cas, la notice et son message sur Reddit doivent le dire en toutes lettres.
