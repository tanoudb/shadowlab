# Proxy par identité (étape 3.2) — conception, 17/11/2026

Étape 3.2 du plan : « Proxy par identité, avec identifiants (jamais dans le code). Fin vérifiable : test, deux identités sortent par deux adresses. »
Ce document est d'abord la conception (écrite avant le code), puis le résultat et la liste des fuites (sections 5 et 6, remplies en fin d'étape).

## 1. Le besoin

Une identité (étape I4, D-88) est un dossier `outputs/identites/<nom>/` : un profil Chrome qui dure. Pour que deux identités ne se relient pas, il faut
qu'elles ne sortent pas par la même adresse. Chaque identité peut donc déclarer **son** proxy (HTTP ou SOCKS5, avec nom d'utilisateur et mot de passe) ;
tout le trafic de Chrome pour cette identité passe par lui, ressources de page comprises. Sans proxy déclaré : rien ne change.

## 2. Les choix

1. **Où vivent les identifiants : un fichier `proxy.json` dans le dossier de l'identité, en mode 0600** (le dossier est en 0700, sous `outputs/`, ignoré par git).
   Pourquoi : le proxy *appartient* à l'identité (deux identités, deux proxys, jamais mélangés) ; un fichier de campagne est versionné et sa configuration est
   enregistrée dans la base (`experiments.configuration`) ; une variable d'environnement est partagée par tous les lancements du processus, passe aux processus enfants
   et se voit dans `ps` et dans tmux ; une option du moteur finirait dans `configuration()` donc dans les résultats. **Aucune option de campagne ne porte le proxy** :
   l'option `identite` ne nomme que l'identité. Le fichier est refusé s'il est lisible par le groupe ou les autres. On ne lit pas `.env`.
   Format : `{"serveur": "http://hote:3128" | "socks5://hote:1080", "utilisateur": "...", "mot_de_passe": "..."}` (identifiants à part de l'adresse ; une adresse qui en contient est refusée).
2. **Un relais local qui tient les identifiants, pas Chrome.** Le moteur lance un petit relais HTTP sur `127.0.0.1:<port libre>` (dans le processus du moteur) ;
   Chrome n'a pour proxy que ce relais, sans identifiant (rien de secret dans les arguments de Chrome, ni dans la mémoire du pilote Playwright). Le relais ouvre la
   connexion vers le proxy de l'identité (HTTP `CONNECT` avec `Proxy-Authorization: Basic`, ou SOCKS5 avec mot de passe, nom de domaine transmis tel quel) et recopie les octets.
3. **Le relais est le verrou réseau de cette identité.** En mode strict, le verrou actuel (mandataire bloquant `127.0.0.1:9` + liste directe, D-07) envoie les hôtes autorisés
   *en direct* : incompatible avec un proxy d'identité. Avec un proxy d'identité, Chrome n'a **aucun chemin direct** : tout passe par le relais, qui refuse tout hôte hors
   périmètre (hôtes des défis compris) avant de contacter le proxy. **Le contrôle du relais se fait par nom, sans résolution locale** : l'hôte demandé doit être dans la liste (mêmes règles de comparaison que `perimetre.verifier_url`, `*` compris, mais sans son `getaddrinfo`). Pourquoi : cette résolution protège contre un nom qui mènerait à NOTRE réseau privé ; le relais ne joint jamais rien en direct (le proxy résout et sort), donc elle ne protège de rien ici, elle fuirait le nom hors proxy et refuserait à tort un nom que seul le proxy connaît. Le contrôle de périmètre est donc le même et plus strict
   (rien n'est joint en direct) ; il ne dépend plus de la liste `bypass` de Chrome. En mode illimité (`*`, défaut de la phase interne, D-30) le relais laisse tout passer
   (http et https seulement), mais tout passe encore par le proxy. Le filtre `route` de Playwright (`_filtrer`) reste inchangé.
4. **Sans proxy déclaré : aucun changement** (ni relais, ni argument de lancement). `SHADOWLAB_PROXY` (proxy unique du processus, mode illimité, sans identité) reste tel quel ;
   une identité qui déclare un proxy ne retombe **jamais** dessus ni sur un accès direct : si le relais ou le fichier est invalide, le lancement est refusé.
5. **Fuite WebRTC** : l'UDP de WebRTC ignore le proxy. Pour une identité qui a un proxy, Chrome est lancé avec `--force-webrtc-ip-handling-policy=disable_non_proxied_udp`
   (aucune autre option de lancement ; l'identité native reste native pour tout le reste). Effet sur les détecteurs de l'Arena non mesuré : cet argument n'existe que pour les
   identités qui ont un proxy, il n'y en a aucune dans les campagnes à ce jour.
6. **`configuration()`** enregistre `identite_proxy` = adresse sans identifiants + `***` (exemple `http://***:***@127.0.0.1:3128`). Le mot de passe n'apparaît ni dans
   `repr`, ni dans les messages d'erreur, ni dans les journaux.

## 3. Interfaces

```
src/shadowlab/engines/noezia/proxy_identite.py   (nouveau)
    class ProxyInvalide(ValueError)
    @dataclass(frozen=True) class ProxyIdentite: schema ("http"|"socks5"), hote, port, utilisateur|None, mot_de_passe|None (repr=False)
        .masque() -> "http://***:***@hote:port" (ou "http://hote:port" sans identifiants) ; __repr__ == __str__ == masque()
    def analyser(serveur: str, utilisateur=None, mot_de_passe=None) -> ProxyIdentite     # refuse : autre schéma, hôte vide, port hors 1..65535, identifiants dans l'adresse
    class Demande(NamedTuple): methode, hote, port, decision      # decision : "transmise" | "refusee_perimetre" | "refusee_amont" | "echec_amont"
    class RelaisProxy(amont: ProxyIdentite, hotes_autorises: tuple[str, ...], hotes_supplementaires: tuple[str, ...] = (), delai_s: float = 15.0)
        .demarrer() -> int (port)  .arreter()  .adresse -> "http://127.0.0.1:<port>"  .demandes -> list[Demande]  (contexte : with)
src/shadowlab/engines/noezia/identite.py   (ajouts)
    FICHIER_PROXY = "proxy.json"
    def declarer_proxy(nom, serveur, utilisateur=None, mot_de_passe=None) -> Path   # écrit proxy.json en 0600 dans le dossier (créé en 0700) ; valide avec `analyser`
    def lire_proxy(nom) -> ProxyIdentite | None   # None sans fichier ; ProxyInvalide si JSON invalide, droits > 0600 (mode & 0o077), propriétaire autre, valeurs invalides
src/shadowlab/engines/noezia/moteur.py   (changements)
    open()       : lit `identite.lire_proxy(nom)` AVANT de prendre le verrou de l'identité ; s'il y a un proxy, démarre le relais (et l'arrête dans close()).
    _lancer_identite() : avec relais -> proxy={"server": relais.adresse} (pas de bypass : Playwright ajoute <-loopback>, le local passe donc aussi par le relais)
                  + args=["--force-webrtc-ip-handling-policy=disable_non_proxied_udp"] ; sans relais -> exactement comme avant.
    configuration() : + "identite_proxy": masque, seulement s'il y a un proxy.
```

Le relais (client = Chrome) :
- `CONNECT hote:port HTTP/1.1` : décision de périmètre ; connexion au proxy de l'identité ; réponse `200 Connection Established` puis recopie dans les deux sens. Refus de périmètre : `403` ;
  échec ou refus du proxy (407, 403, mauvais mot de passe SOCKS5, connexion impossible) : `502` (jamais `407` à Chrome, qui afficherait une demande d'identifiants) ; **jamais de repli sur une connexion directe**.
- Requête `http://hote[:port]/chemin` (forme absolue) : même décision ; proxy HTTP : la requête part telle quelle avec `Proxy-Authorization` et `Connection: close` ; proxy SOCKS5 : connexion au
  nom d'hôte par SOCKS5, requête réécrite en forme d'origine avec `Connection: close`. Une connexion du client porte une seule requête.
- Aucun nom n'est résolu localement par le relais (le nom part au proxy), y compris pour juger du périmètre (§ 2.3). **Reste hors du relais** : en mode strict, `Driver.verifier()` et le filtre `route` (`_filtrer`) appellent encore `perimetre.verifier_url`, donc résolvent localement le nom des hôtes de la liste ; fuite DNS du mode strict, à lister (§ 6), pas à corriger ici. Les identifiants ne sont jamais écrits dans un message d'erreur ni dans `demandes`.

## 4. Tests (écrits avant le code, vus en échec)

Rapides, sans navigateur (`tests/test_proxy_identite.py`, aides communes `tests/outils_proxy.py`) :
analyse et masque ; `declarer_proxy` (0600, dossier 0700) et `lire_proxy` (refuse 0644, JSON invalide, schéma inconnu, identifiants dans l'adresse) ; `configuration()` d'un pilote avec identité et proxy ne
contient pas le mot de passe (et contient le masque) ; relais avec faux proxy HTTP et faux proxy SOCKS5 à authentification : identifiants corrects transmis, mauvais mot de passe -> 502 et aucune connexion
à la cible, hôte hors périmètre -> 403 et le proxy n'est pas contacté, mode illimité -> tout passe, nom d'hôte transmis tel quel (pas de résolution locale), requête HTTP simple par les deux sortes de proxy.

Avec un vrai Google Chrome en identité native (`tests/test_proxy_identite_chrome.py`, marque `integration`) : deux identités A (proxy HTTP) et B (proxy SOCKS5) à authentification, lancés par le test ;
un serveur cible local qui note, pour chaque connexion reçue, le port source ; chaque proxy note les ports sources de ses connexions vers la cible. Critères : les requêtes de A (page, image, script, XHR) ne passent
que par le proxy A, celles de B que par le proxy B ; aucune connexion directe à la cible (chaque port source vu par la cible est celui d'un proxy) ; un mauvais mot de passe : la page échoue et la cible ne reçoit rien ;
aucun identifiant dans `configuration()`, `versions()`, ni dans les fichiers de l'identité autres que `proxy.json` ; la redirection hors périmètre échoue encore avec un proxy ; un nom d'hôte que seul le proxy
sait résoudre fonctionne (pas de DNS local) ; WebRTC : avec proxy aucun paquet UDP n'atteint un STUN local, sans proxy (témoin) il en arrive ; sockets de l'arbre de processus de Chrome : aucune connexion TCP
vers autre chose que le relais.

## 5. Ce que « deux adresses » veut dire sur un seul poste

(rempli en fin d'étape)

## 6. Fuites hors proxy

(rempli en fin d'étape)
