# Site public pour la communauté — cadrage (13/11/2026, version 2)

Version 2, après le retour d'Ethan à 23 h 40. La version 1 prévoyait deux sites de démonstration (annonces
immobilières, rallye) : abandonnée.

## Les demandes d'Ethan (ses mots)
- 23 h 30 : « deux faux beaux sites pour que je puisse mettre sur le Cloudflare », pour « demander à des gens
  de le tester », en leur disant que « c'est pour une analyse sur comment les humains utilisent un navigateur
  et comment différencier un humain d'une IA » ; « voir le nombre de gens qui visitent » ; « anglais ou
  français, on met les deux » ; « un beau truc, que ça leur donne envie de se balader dessus » ; « un truc
  qui analyse tout et que les gens sont au courant ».
- 23 h 40 : « d'agence immobilière ou de rallye, c'est pas ouf […] les gens, ils vont pas se balader » ;
  « une sorte de faux réseau social. Tu mets des photos open source, tu vas faire un truc qui soit beau » ;
  « des sites de démo, compteur de visite, session commencée, session terminée par jour. Pour moi, ouais.
  Une page d'accueil humain-robot » ; « il faut qu'on prenne un maximum d'infos sur comment ça fonctionne
  pour faire le meilleur détecteur ».

## But
Récolter des sessions humaines (étape 1.7 du plan) auprès d'une communauté (Reddit, amis), pour mesurer et
améliorer les détecteurs : savoir lesquels prennent de vraies personnes pour des robots, et ce qui distingue
vraiment une personne d'un automate. Le site doit donner envie de se promener 5 à 10 minutes, et dire
clairement tout ce qui est relevé.

**But annoncé aux visiteurs (lu dans la réponse d'Ethan : « pour faire le meilleur détecteur »)** : mesurer
et améliorer nos détecteurs de robots. Les sessions du public ne servent à rien d'autre : en particulier,
elles ne servent pas à régler le moteur d'automatisation (pas même à juger le tremblement de D-74).

## Ce qu'on construit (tout dans l'application publique, `src/shadowlab/public/`)
1. **Une page d'accueil de l'étude**, « Humain ou robot ? », belle, en français et en anglais : ce qu'est
   l'étude, ce qu'on fait, ce qui est relevé et ce qui ne l'est pas (résumé honnête), le compteur de
   sessions, la case d'accord et le bouton pour commencer. La notice complète reste à un clic, dans les deux
   langues, avant d'accepter.
2. **Le site vedette : un faux réseau social de photos**, nom de travail « Mosaïk Démo », entièrement
   fictif : fil de publications, page d'une publication avec ses commentaires, profils, étiquettes, page
   « explorer ». De vraies photos sous licence libre, hébergées sur place. Dessin et nom originaux : pas une
   copie d'un réseau existant.
3. **Habitat Démo** (les annonces, déjà dans l'application publique et déjà relu) reste accessible comme
   second site, en lien discret. Le rallye n'est pas mis en ligne.
4. **La fréquentation, pour Ethan** : un compte par jour (chargements de l'accueil, sessions commencées,
   sessions terminées), sans rien sur les personnes ; une commande `shadowlab public frequentation` ; le
   nombre de sessions affiché sur l'accueil.
5. **Un relevé plus riche** (« un maximum d'infos »), par un second script propre au site public, en plus de
   l'observateur du labo qui ne change pas : voir « Relevé enrichi ».

## Le faux réseau social : forme imposée par la mesure
- **Beaucoup de pages courtes, de vraies pages** (pas un fil infini sur une seule page) : l'observateur
  envoie un relevé de comportement par page, à la sortie, limité à 40 angles et 50 délais. Donc fil paginé
  (bouton « Voir plus » = page suivante), page par publication, par profil, par étiquette, explorer paginé.
- **Sous `/lab/social/…`**, comme la vitrine sous `/lab/vitrine/…` : les requêtes sont notées pendant une
  session et `shadowlab rejeu --base` peut rejouer les sessions. Les photos aussi (`/lab/social/photos/…`).
- **Aucune écriture venant du visiteur.** Un « j'aime » ne change que l'affichage. Un commentaire tapé
  s'affiche sur place et n'est jamais envoyé. La recherche filtre dans la page : pas de formulaire qui met
  le texte tapé dans l'adresse. Le texte tapé ne quitte jamais le navigateur.
- **Personnes fictives, visages dessinés.** Aucune photo de personne reconnaissable ; les auteurs fictifs ont
  un avatar dessiné (initiales, formes), pas un vrai visage.
- Contenu généré à partir d'une graine (comme la vitrine), en français et en anglais selon la langue.
- **Squelette d'abord** : trois types de page, une douzaine de photos, une vraie session, puis
  `shadowlab rejeu --base`. Si un détecteur se déclenche à cause de la forme du site (nombre de requêtes par
  page, rythme des pages), il faut le savoir avant de dessiner.

## Photos
- Source dont les métadonnées donnent la licence fichier par fichier ; seulement domaine public ou CC0.
- Un manifeste (adresse d'origine, auteur, licence) versionné, et une page de crédits sur le site.
- Chaque fichier est réencodé (métadonnées EXIF retirées, taille bornée) et hébergé sur place : la politique
  de sécurité interdit toute image venue d'ailleurs.
- Sujets sans personne reconnaissable : paysages, mer, montagne, ville, architecture, animaux, plantes,
  cuisine, objets.

## Relevé enrichi (second script, site public seulement)
- `site/static/observateur.js` ne change pas (il est celui du labo et des mesures du moteur).
- Un second script, servi par l'application publique seulement, envoie une nouvelle nature d'envoi
  (`trace`) : trajectoire de la souris (positions et instants, échantillonnés et plafonnés), défilement,
  clics (position, cible : type d'élément seulement), rythme du clavier (instants d'appui et de relâche,
  jamais la touche ni le caractère), gestes tactiles, passages au premier plan et à l'arrière-plan,
  redimensionnements.
- **Limites dures** : jamais un caractère tapé ni l'identité d'une touche ; rien qui demande une
  autorisation (caméra, micro, capteurs, position) ; pas d'adresse IP ; aucun tiers.
- Cela revient sur une promesse écrite (« ni la position de la souris ») : dans le même commit, la notice est
  réécrite dans les deux langues, le but est élargi à « mesurer et améliorer nos détecteurs »,
  `VERSION_INFORMATION` change, une décision est ajoutée, et le nouveau script passe sous le même test clé
  par clé que l'observateur.
- Les plafonds par session (`envois_par_session`, `volume_par_session`, `taille_corps`) sont recalculés, et
  le produit sessions × octets vérifié contre le plafond de la base (2 Gio).
- `rejeu` ignore la nature `trace` (à vérifier par un test).

## Règles (non négociables)
- **Les pages du labo ne changent pas d'un octet** (recettes, vérité, et la campagne de contrôle de D-74 se
  compare à la 108). Tout crochet dans `site/vitrine.py` est additif, page d'aujourd'hui par défaut,
  verrouillé par un test écrit avant la modification. L'application du labo (`site/app.py`) ne change pas.
- **Politique de sécurité inchangée** (`default-src 'self'; script-src 'self'; style-src 'self'; img-src
  'self' data:`) : aucune ressource extérieure, aucun script ni style dans la page, aucun attribut `style=`.
- **Trois cookies, pas un de plus.** La langue passe par l'adresse (`/fr/…`, `/en/…`) et, pendant une
  session, par la langue notée avec l'accord ; sans session, par la langue du navigateur.
- **Aucune route du labo** : le test qui le garantit couvre aussi toutes les pages du réseau social.
- **La notice dit vrai, dans les deux langues**, clé par clé (observateur et second script).
- **Le plafond de 40 sessions par jour devient un réglage** : un message sur Reddit le dépasse en une heure.
- Pas de page « votre résultat » (verdict des détecteurs montré au visiteur) dans cette version : c'est une
  décision d'Ethan, à lui proposer ensuite.

## Langue
Ordre : préfixe de l'adresse (`/fr`, `/en`) ; sinon langue de la session ; sinon `Accept-Language` ; sinon
français. `/` rend l'accueil dans la langue du navigateur, avec un lien visible vers l'autre langue. La langue
choisie est notée dans l'accord de la session (et listée dans la notice).

## Textes de l'accueil (sens à garder)
- Titre : « Humain ou robot ? » / “Human or bot?”
- Sous-titre : « Une étude ouverte sur la façon dont de vraies personnes naviguent sur le Web. » /
  “An open study of how real people browse the web.”
- Accroche : « Les sites se protègent des robots avec des détecteurs. Ces détecteurs se trompent parfois et
  prennent de vraies personnes pour des robots. Aidez-nous à les améliorer : promenez-vous 5 à 10 minutes
  sur un faux réseau social de photos, comme vous le feriez sur un vrai. » /
  “Websites use detectors to keep bots out. Those detectors sometimes get it wrong and flag real people.
  Help us make them better: spend 5 to 10 minutes browsing a fake photo-sharing network, the way you would
  browse a real one.”
- Franchise (à ajuster au relevé enrichi quand il existe) : « Pendant la session, nous relevons les
  caractéristiques de votre navigateur et votre façon de naviguer : mouvements de la souris, défilement,
  rythme des clics et des touches. Jamais ce que vous tapez, ni votre adresse IP. Vous pouvez tout supprimer
  d'un clic. » / “During the session we record your browser's characteristics and how you browse: mouse
  movements, scrolling, the rhythm of your clicks and keystrokes. Never what you type, never your IP
  address. You can delete everything with one click.”
- Compteur : « N sessions enregistrées à ce jour » / “N sessions recorded so far”.

## Ordre de fabrication
1. **Photos** : une première série, manifeste, planches de contrôle (un agent ; contrôle visuel par la
   coordination).
2. **Squelette du réseau social** dans l'application publique (un agent), puis une vraie session et
   `rejeu --base` (coordination), puis une capture à Ethan.
3. **Fond** : langues, accueil, notice, fréquentation, plafond de sessions réglable.
4. **Relevé enrichi** : second script, notice, plafonds, décision.
5. **Forme** : dessin de l'accueil et du réseau social, ordinateur et téléphone.
6. **Contrôles** : chaque type de page à l'écran, console sans erreur de politique de sécurité ; session
   complète puis rejeu ; quatrième relecture indépendante (vie privée, sécurité, licences des photos).
7. **Ethan** : regarde, lance le tunnel lui-même.

Bloque le feu vert à la mise en ligne (pas la fabrication) : la réécriture de la notice (point 4) et la
quatrième relecture.
