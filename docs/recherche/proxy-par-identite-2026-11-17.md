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
   périmètre (hôtes des défis compris) avant de contacter le proxy. **Choix à valider par la coordination : pour ces identités, le relais REMPLACE le mandataire bloquant de D-07 (le verrou « liste directe + mandataire mort ») au lieu de s'y enchaîner** ; la propriété demandée tient (rien hors périmètre ne sort, l'enchaînement avec un proxy est testé, scénario d), mais le mécanisme change : voir les raisons ci-dessous. **Le contrôle du relais se fait par nom, sans résolution locale** : l'hôte demandé doit être dans la liste (mêmes règles de comparaison que `perimetre.verifier_url`, `*` compris, mais sans son `getaddrinfo`). Pourquoi : cette résolution protège contre un nom qui mènerait à NOTRE réseau privé ; le relais ne joint jamais rien en direct (le proxy résout et sort), donc elle ne protège de rien ici, elle fuirait le nom hors proxy et refuserait à tort un nom que seul le proxy connaît. Le contrôle de périmètre est donc le même et plus strict
   (rien n'est joint en direct) ; il ne dépend plus de la liste `bypass` de Chrome. En mode illimité (`*`, défaut de la phase interne, D-30) le relais laisse tout passer
   (http et https seulement), mais tout passe encore par le proxy. Le filtre `route` de Playwright (`_filtrer`) reste inchangé.
4. **Sans proxy déclaré : aucun changement** (ni relais, ni argument de lancement). `SHADOWLAB_PROXY` (proxy unique du processus, mode illimité, sans identité) reste tel quel ;
   une identité qui déclare un proxy ne retombe **jamais** dessus ni sur un accès direct : si le relais ou le fichier est invalide, le lancement est refusé.
5. **Fuite WebRTC** : l'UDP de WebRTC ignore le proxy. Pour une identité qui a un proxy, Chrome est lancé avec `--webrtc-ip-handling-policy=disable_non_proxied_udp`
   (aucune autre option de lancement ; l'identité native reste native pour tout le reste). **Mesuré sur Chrome 156 (macOS)** avec un STUN local : sans l'argument 4 paquets UDP sortent, avec lui 0 ;
   le nom `--force-webrtc-ip-handling-policy`, souvent cité, n'a aucun effet (4 paquets) : la première version de cette conception le nommait, le test l'a montré. Effet sur les détecteurs de l'Arena non mesuré :
   cet argument n'existe que pour les identités qui ont un proxy, il n'y en a aucune dans les campagnes à ce jour. **Lecture du code** (`DetecteurWebRTC`, `detection.py`) : les seules règles sont `rtc_patche` (0,4, `RTCPeerConnection.toString()`
   non natif : un argument de lancement n'y change rien) et `rtc_host_leak` (poids 0,0, informatif) ; `disponible: false` ne donne aucun signal. Zéro candidat « host » ne déclencherait donc rien ; non confirmé par une campagne.
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
                  + args=["--webrtc-ip-handling-policy=disable_non_proxied_udp"] ; sans relais -> exactement comme avant.
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

Sur ce poste, il n'y a qu'une adresse réseau utile (`127.0.0.1`) : macOS n'en offre pas d'autres sur `lo0` sans réglage administrateur (Linux offrirait `127.0.0.2`, `127.0.0.3` ; non utilisé). « Deux adresses » veut donc
dire ici **deux points de sortie distincts**, que la cible distingue par le **port source** de chaque connexion : chaque faux proxy note le port local de ses connexions sortantes, la cible note le port source de chaque connexion
reçue ; les deux jeux de ports sont disjoints, et chaque port vu par la cible est celui d'un proxy (donc aucune connexion directe de Chrome).

- **Prouvé par les tests** : le routage (A par le proxy A seulement, B par le proxy B seulement, ressources de la page comprises) ; l'absence de connexion directe ; le refus d'un mauvais mot de passe sans repli direct ;
  le nom d'hôte résolu par le proxy et non en local ; le verrou de périmètre qui tient avec un proxy (refus de `localhost` hors liste, de `example.com`) ; l'absence d'identifiants dans `configuration()`, `versions()`, les journaux,
  `demandes` et les fichiers de l'identité autres que `proxy.json` ; l'absence de paquet UDP vers un STUN local avec proxy.
- **Ne sera prouvé qu'avec de vrais proxys** : que deux vrais proxys donnent deux **adresses IP publiques** différentes (il faudra un service qui renvoie l'adresse vue, à nous, comme la vitrine de l'étape 3.4) ;
  la réputation de ces adresses ; ce qu'un fournisseur réel accepte (beaucoup limitent `CONNECT` aux ports 80 et 443, ou exigent un nom d'utilisateur qui porte la session ou le pays) ; les en-têtes qu'un proxy réel ajoute
  (`Via`, `X-Forwarded-For`) ; la durée de vie d'une adresse (rotation) ; la latence ; un proxy HTTPS (`https://`, non géré) ; Linux (tout a tourné sur macOS).

## 6. Fuites hors proxy

Légende : **test** = couvert par un test du dépôt, rejouable ; **sonde** = observé une fois par une sonde jetable de l'agent qui a écrit le code (hors dépôt, non rejouable) ; **lecture** = déduit du code ; **non vérifié**.

**Ce qui passe par le proxy de l'identité**
- Page, image, script, appel de données (XHR) d'une page en `http://` : **test** (`test_proxy_identite_chrome.py`, scénario a, proxy HTTP pour A et SOCKS5 pour B ; cible : aucune connexion directe).
- Le nom des hôtes de la page : **test** (scénario e) : un nom que seul le proxy connaît se charge, Chrome n'a rien résolu en local ; avec SOCKS5, le nom part tel quel (type « domaine », RFC 1928) : **test** (relais).
- `https://` par `CONNECT`, tunnel intact (le ClientHello de Chrome ne change pas) : **test** au niveau du relais (octets bruts, `tests/test_proxy_identite.py`) et **test avec un vrai Chrome** (`test_h_*` : cible TLS locale, certificat jetable de l'Arena, deux pages chargées par un proxy HTTP puis par un proxy SOCKS5, chaque port source vu par la cible est celui d'une sortie du proxy ; en mode strict, `https://localhost` hors liste échoue par `ERR_TUNNEL_CONNECTION_FAILED` sans connexion de l'amont).
- Le trafic de fond de Chrome (Google, gstatic, googleapis, `update.googleapis.com`) : **sonde** : il passe par le relais, donc par le proxy ; en mode strict, `www.google.com` et `www.gstatic.com` passent (ils sont dans `HOTES_CHALLENGES`),
  `accounts.google.com` et `update.googleapis.com` sont refusés par le périmètre.
- Les sockets de l'arbre de processus de Chrome : **test** (scénario g, échantillon `psutil` toutes les 0,2 s) : aucune connexion TCP vers autre chose que le relais.
- Un refus du relais : en `http://` une page d'erreur 403 (hors périmètre) ou 502 (le proxy refuse), jamais une demande d'identifiants (**sonde**, et les tests b et d jugent sur le réseau) ; en `https://` une erreur `net::ERR_TUNNEL_CONNECTION_FAILED` (**test**) ; le fait qu'aucune connexion directe ne suive : **test**.

**Ce qui ne passe pas par le proxy, ou y passe mal**
1. **WebRTC (UDP)** : l'UDP ignore le proxy. Sans correction 4 paquets arrivent directement à un STUN local (**sonde**, avec proxy mais sans l'argument). **Corrigé** par `--webrtc-ip-handling-policy=disable_non_proxied_udp` (0 paquet : **test**, scénario f).
   Le nom `--force-webrtc-ip-handling-policy` n'a aucun effet sur Chrome 156 (première version de la conception, corrigée). Reste : la correction est mesurée sur Chrome 156 macOS seulement ; son effet sur les détecteurs de l'Arena (`webrtc_test`) n'est pas mesuré ;
   un Chrome qui renommerait encore l'argument ferait échouer le test f, pas la production.
2. **DNS local du mode strict** : `Driver.verifier()` et le filtre `route` (`_filtrer`) appellent `perimetre.verifier_url`, qui résout en local (`getaddrinfo`) le nom des hôtes de la liste. Le relais, lui, ne résout rien (**test**). Pas de fuite en mode illimité
   (le défaut de la phase interne). **Lecture.** Non corrigé : changer `perimetre.py` touche tous les moteurs.
3. **Le relais n'a pas d'authentification** : tout processus du poste qui trouve le port sur `127.0.0.1` sort par le proxy de l'identité. **Lecture.** Correction possible (un jeton aléatoire par lancement donné à Chrome comme identifiant du proxy local), non faite : elle remet les identifiants de Chrome
   dans le circuit de Playwright, et le seul danger est un autre processus de la même machine.
4. **Les identifiants circulent en clair jusqu'au proxy** (Basic pour un proxy HTTP, utilisateur/mot de passe pour SOCKS5) : inhérent à ces deux protocoles ; un proxy `https://` n'est pas géré (refusé à l'analyse).
5. **Le local passe aussi par le proxy** : Playwright ajoute `<-loopback>`, le trafic vers `127.0.0.1` part donc vers le proxy, qui ne peut pas joindre le poste d'un vrai fournisseur. Une identité avec proxy ne sert donc pas contre l'Arena locale.
   `PLAYWRIGHT_DISABLE_FORCED_CHROMIUM_PROXIED_LOOPBACK` retirerait cet ajout et enverrait le local en direct. **Lecture.**
6. **Requêtes `http://` : une connexion par requête, imposée par le relais** : il ne transmet que l'en-tête et exactement `Content-Length` octets de corps, jette le reste (une seconde requête collée à la première ou envoyée après n'atteint jamais le proxy : **test**, 12 cas, amont HTTP et SOCKS5), et ajoute `Connection: close` dans les deux sens. Un corps découpé (`Transfer-Encoding`) est refusé en 501 (un envoi `http://` en flux ne passe pas), un `Content-Length` invalide ou multiple en 400. Un site en clair voit une connexion par requête ; le trafic `https://` (le cas réel) n'est pas touché. Cette borne vient d'une revue de sécurité automatique (la première version recopiait tout ce que le client envoyait encore). **Sonde** (12 requêtes reçues par la cible pour 12 demandes transmises, 12 ports sources distincts, en HTTP et en SOCKS5) et **lecture**.
7. **Bornes du relais** : `demandes` grossit sans borne (une ligne par demande) ; un tunnel à demi fermé garde son fil jusqu'à `arreter()` ; une requête simple dont l'origine tarde plus de 15 s (`delai_s`) avant son premier octet donne 502.

**Non vérifié**
- QUIC / HTTP/3 : on attend que Chrome ne l'utilise pas à travers un proxy HTTP ou SOCKS5 ; non mesuré.
- Les processus voisins de Chrome qui ont leur propre pile réseau (mise à jour de Google Chrome, envoi des rapports de plantage) : non observés ; ils ne reçoivent pas le proxy de Chrome.
- Mises à jour de composants, Safe Browsing, DNS sécurisé (DoH) au démarrage d'un profil neuf : seuls les passages par le relais ont été vus (sonde) ; une résolution du navigateur hors proxy ne se voit pas avec `psutil`.
- UDP autre que WebRTC (mDNS, découverte du réseau local) : aucun socket UDP vu par l'échantillonnage, mais il ne voit pas les paquets.
- Un vrai fournisseur (HTTP ou SOCKS5), Linux, un Chrome autre que 156.

## 7. Résultat (17/11)

- Code : `src/shadowlab/engines/noezia/proxy_identite.py` (nouveau, ~580 lignes, bibliothèque standard), `identite.py` (+54 : `declarer_proxy`, `lire_proxy`), `moteur.py` (+~30 : relais à `open()`, arrêt à `close()`, lancement, masque dans `configuration()`).
  Aucune option dans `options_permises`.
- Tests : 162 rapides (`tests/test_proxy_identite.py`) + 40 d'aides (`tests/test_outils_proxy.py`) + 23 avec un vrai Chrome 156 (`tests/test_proxy_identite_chrome.py`, 31 s) ; les trois tests d'identité d'avant (`test_integration.py -k identite`) passent encore ; suite rapide :
  2 492 réussis, 2 sautés ; suite complète non lancée. Les tests ont été écrits et committés avant le code (commit `ee72107`, en échec par `ModuleNotFoundError`) ; les compléments (arguments de lancement dans `configuration()`, requête simple bornée) l'ont été de même, vus en échec (34 des 40 tests de bornage).
  Un test d'avant a été mis à jour à la main : `test_configuration_sans_proxy_pas_de_cle_et_le_reste_ne_change_pas` exclut maintenant les deux clés que le proxy ajoute (`identite_proxy` et `identite_proxy_arguments`).
- Sondes jetables des agents (le cas des requêtes simples, `open()` qui échoue, refus du relais, WebRTC) : `docs/recherche/proxy-par-identite-2026-11-17-sondes/` (rejouables depuis la racine du dépôt ; la sonde HTTPS est devenue un test).
- Écarts décidés pendant le code : un refus (`403`) d'une **requête simple** est la réponse de l'origine et passe tel quel (l'Arena en sert, la sentinelle en a besoin), seul un `407` du proxy devient `502` ; `open()` qui échoue appelle `close()` (le verrou de l'identité est rendu :
  avant, il restait pris) ; `analyser` refuse aussi un port absent, un chemin ou une requête dans l'adresse, des identifiants SOCKS5 de plus de 255 octets ; `lire_proxy` refuse un lien symbolique et tout fichier non ordinaire.
