# Nos moteurs devant trois pages publiques de test de détecteurs — 17/11/2026

Demande d'Ethan (17/11) : voir « leur niveau et le nôtre » sans toucher à un site qui n'est pas à nous. Ces trois pages sont faites pour tester des outils d'automatisation :
**Sannysoft** (https://bot.sannysoft.com/), **CreepJS** (https://abrahamjuliot.github.io/creepjs/), **rebrowser-bot-detector** (https://bot-detector.rebrowser.net/).
BrowserScan n'a pas été passé : ses conditions d'utilisation n'ont pas été lues.

**Conditions** : une visite par page et par moteur, une à la fois, 8 s de pause, depuis ce Mac (Chrome 156.0.8078.80 réel), aucun défi résolu (`resoudre_defis: false`), aucun CAPTCHA, aucun compte ; le cadre principal ne peut aller que sur l'hôte demandé.
Script : `scripts/detecteurs-publics.py` (`uv run python scripts/detecteurs-publics.py`). Bruts : `outputs/detecteurs-publics/2026-11-17-complet/` (captures PNG et texte, non versionnés) ; textes de Sannysoft et de rebrowser et `resultats.json` :
`detecteurs-publics-2026-11-17-donnees/`. Les quatre moteurs : `noezia-natif` (vrai Chrome avec fenêtre, identité d'origine), `noezia-reecrit` (identité réécrite, avec fenêtre), `patchright` et `playwright` (témoins sans réglage, sans fenêtre).

## Résumé

1. **`noezia` en identité native passe les trois pages presque sans tache** : Sannysoft 0 échec ; rebrowser tout vert sauf `storagePartitioning` ; CreepJS 0 % headless, 0 % stealth, mais 31 % « like headless ».
2. **L'identité réécrite se voit** : rebrowser relève quatre défauts (navigator.webdriver supprimé, User-Agent annoncé Chrome 130 contre Chromium 156 dans `userAgentData`, fonctions natives enveloppées, User-Agent) et CreepJS donne **60 % stealth**. Même leçon que la campagne 97 : truquer fait fuir ; être un vrai Chrome cohérent passe.
3. **Les deux témoins sont arrêtés partout** : `patchright` (88 % like headless et 33 % headless à CreepJS ; `HeadlessChrome` et `window.chrome` absent à rebrowser et à Sannysoft) ; `playwright` pire (67 % headless, `navigator.webdriver` vrai, fuite `Runtime.enable`).
4. **Un défaut réel du moteur** : `storagePartitioning` rouge en identité native (le partitionnement du stockage tiers est coupé par les arguments par défaut de Playwright et Patchright ; un site peut le voir). À étudier, tests d'abord.
5. **Limite** : ce sont des pages de test statiques, pas un fournisseur anti-bot du commerce : elles ne mesurent ni la réputation de l'adresse, ni le comportement dans la durée. Passer Sannysoft ne dit rien sur DataDome ou Cloudflare.

## Sannysoft (tests d'Intoli + scanner d'empreinte)

| Test | noezia natif | noezia réécrit | patchright | playwright |
|---|---|---|---|---|
| WebDriver (New) | missing (passed) | missing (passed) | missing (passed) | **present (failed)** |
| Chrome (New) | present (passed) | present (passed) | **missing (failed)** | **missing (failed)** |
| Plugins is of type PluginArray | passed | passed | **failed** | **failed** |
| Plugins Length | 5 | 4 | 0 | 0 |
| Languages | fr-FR,fr,en-US,en | **de-DE,de** | en-US | en-US |
| User agent | Chrome/156 | Chrome (macOS 15_1) | **HeadlessChrome** | **HeadlessChrome** |
| Scanner (tests en échec) | aucun | aucun | HEADCHR_UA, HEADCHR_CHROME_OBJ, HEADCHR_PERMISSIONS, HEADCHR_IFRAME, CHR_MEMORY | les mêmes cinq |

Note : l'identité réécrite annonce de l'allemand (`de-DE`) à une machine en français : le profil tire sa langue au hasard (voir aussi CreepJS, fuseau Berlin).

## rebrowser-bot-detector

🟢 réussi, 🟡 attention, 🔴 détecté, ⚪ non déclenché (la page demande du code côté script pour ces tests).

| Test | noezia natif | noezia réécrit | patchright | playwright |
|---|---|---|---|---|
| runtimeEnableLeak (CDP) | 🟢 | 🟢 | 🟢 | 🔴 |
| navigatorWebdriver | 🟢 | 🔴 | 🟢 | 🔴 |
| viewport | 🟢 | 🟢 | 🟡 | 🟡 |
| platformMismatch | 🟢 | 🔴 | 🟢 | 🟢 |
| popupBlocking | 🟢 | 🟢 | 🟡 | 🟡 |
| ipcFloodingProtection | 🟢 | 🟢 | 🟢 | 🔴 |
| headless | 🟢 | 🟢 | 🔴 | 🔴 |
| workerConsistency | 🟢 | 🟡 | 🟢 | 🟢 |
| nativeTampering | 🟢 | 🔴 | 🟢 | 🟢 |
| useragent | 🟢 | 🔴 | 🔴 | 🔴 |
| storagePartitioning | **🔴** | 🔴 | ⚪ (pas de réponse en 10 s) | ⚪ |

Les autres lignes (`pwInitScripts`, `mobileEmulation`, `documentInterception`, `cdpBindingGlobals`, `bypassCsp`) sont vertes ou non déclenchées pour les quatre.
Notes de la page pour l'identité réécrite : « User agent says Chrome 130, but navigator.userAgentData says Chromium 156 » ; « Native functions were replaced or wrapped in a Proxy: Navigator.platform, Navigator.languages, Navigator.plugins, Navigator.hardwareConcurrency… ».
Note pour `noezia natif` : « third-party storage partitioning is turned off. Playwright turns it off by default (--disable-…) » ; la page conseille ses propres correctifs (`rebrowser-patches`).

## CreepJS

| Moteur | like headless | headless | stealth |
|---|---|---|---|
| noezia natif | 31 % | 0 % | 0 % |
| noezia réécrit | 31 % | 33 % | **60 %** |
| patchright | **88 %** | 33 % | 0 % |
| playwright | **88 %** | **67 %** | 0 % |

À la capture : l'identité réécrite annonce le fuseau Europe/Berlin et la langue allemande, ce que CreepJS marque en rouge ; en identité native, la ligne WebRTC montre une connexion STUN qui expose l'adresse publique de la machine (non recopiée ici) : c'est le cas
que l'argument WebRTC des identités à proxy ferme (étape 3.2). Les chiffres sont ceux de la page ; le détail des « mensonges » n'a pas été lu ligne à ligne.

## Ce que ça veut dire, et ce que ça ne veut pas dire

- **Confirmé de nouveau** : le moteur au meilleur réglage (vrai Chrome, identité native) est le seul des quatre qui ne se voit pas ; l'identité réécrite est la plus visible des deux moteurs `noezia` pour des détecteurs spécialisés, comme pour l'Arena (campagnes 97 et 98).
- **« 31 % like headless » pour un vrai Chrome avec fenêtre** : on ne sait pas si c'est normal. Comparaison manquante : la même page ouverte à la main dans un Chrome d'humain (à demander à Ethan : un clic, une capture). Non vérifié.
- **`storagePartitioning`** : seule tache réelle du moteur au meilleur réglage. Une piste à vérifier (tests d'abord, sur Chrome 156) : retirer le drapeau qui coupe le partitionnement parmi les arguments par défaut de Patchright pour l'identité native. Non essayé : un changement d'argument de lancement touche aussi l'Arena et demande une campagne (§ 8, règle 2).
- **Pas de mesure d'adresse ni de comportement** : une protection du commerce regarde l'IP, la durée et le comportement ; ces pages non. Elles bornent le bas du niveau, elles ne prouvent rien du haut.
- **Une visite par cas** : les chiffres de CreepJS peuvent bouger d'une visite à l'autre ; non répété. Le script a eu un défaut de comptabilité (chemin relatif) : les fichiers de capture et de texte étaient bons, les métadonnées de `resultats.json` ont été réparées à la main (aucune valeur mesurée touchée) et le script corrigé.
- **Hors périmètre de cet essai** : BrowserScan, Linux (tout est sur macOS), un humain de référence.

## Mise à jour du 17/11 : `storagePartitioning` corrigé en identité native (D-101)

Cause : l'argument par défaut `--disable-features=…` de Playwright et de Patchright liste `ThirdPartyStoragePartitioning`. Correctif : en identité native seulement, le moteur repasse `--disable-features=` avec la liste de Playwright moins cette fonction (un second `--disable-features` remplace le premier ; un `--enable-features` n'y change rien).
Contrôle avec un vrai Chrome sur deux sites locaux (`tests/test_stockage_tiers_partitionne.py`) : avant `lu=valeur-premiere-partie`, après `lu=null`. **Une seule visite de contrôle** de la page rebrowser (`outputs/detecteurs-publics/2026-11-17-controle-storage/`) : `storagePartitioning` vert, 16 tests verts, 4 non déclenchés, aucun rouge ni jaune.
Le même défaut existe dans l'identité réécrite et chez les témoins (réglage par défaut de Patchright) ; non changé. Effet sur l'Arena non mesuré : campagne de contrôle à lancer depuis le dossier principal.
