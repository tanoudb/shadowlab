# WebGL sous Linux sans carte graphique : mesures, choix, remesure (17/11/2026)

Première incohérence de l'essai de fumée Linux (`docs/recherche/fumee-linux-2026-11-17.md` § 6.1) : en identité native avec interface, sur un Linux sans carte graphique, WebGL est **absent**. Cette note mesure les réglages candidats, dit lequel est choisi et pourquoi, et remesure.
**Tous les numéros de campagne sont ceux de la base du dossier `fumee-linux`** (campagnes 1 à 11 ; copie : `outputs/fumee-linux-webgl-2026-11-18.sqlite3` du dossier principal), sans rapport avec la numérotation de `outputs/shadowlab.sqlite3`.
Conditions : conteneur amd64 émulé (Rosetta) sur le Mac, Ubuntu 24.04, **Google Chrome 158.0.8127.36 lancé par Patchright** (avec les arguments par défaut de Playwright ; la sonde et le moteur passent tous deux par là) (l'essai du 17/11 avait 157.0.8103.78 : l'image reconstruite a téléchargé la version du jour), Xvfb 1920×1080, Mesa 25.2.8 (llvmpipe, LLVM 20.1.2), aucune carte graphique. L'Arena n'est pas modifiée.

## Résumé

1. **Un Chrome lancé par Patchright n'a pas de WebGL sur cette machine** : sans argument, comme avec `--disable-gpu`, `getContext('webgl')` rend `null`. Le repli sur SwiftShader que D-50 supposait n'a pas lieu avec une interface (Chromium 156, puis Chrome 157 et 158, tous lancés par Patchright). **Un Chrome lancé à la main n'a pas été essayé.**
2. **Deux réglages donnent un WebGL** : `--enable-unsafe-swiftshader` (SwiftShader) et `--ignore-gpu-blocklist` (Mesa llvmpipe).
3. **`--ignore-gpu-blocklist` seul est un piège** : il active le canvas 2D accéléré, dont la lecture devient instable (`getImageData` non déterministe, 10 essais sur 10). L'Arena le relève (`getImageData_instable`) et bloque les niveaux 05 et 06 (campagne 9 : 0 passage sur 6 à chacun).
4. **Choix : `--ignore-gpu-blocklist --disable-accelerated-2d-canvas`**, seulement sur Linux sans carte graphique, en identité native avec interface (D-102). WebGL présent (`ANGLE (Mesa, llvmpipe (LLVM 20.1.2 128 bits), OpenGL 4.5)`), canvas stable, aucun signal de plus à l'Arena.
5. **La sonde ne peut pas montrer le correctif** : elle lance Chrome par Patchright sans passer par le moteur, donc sans `FUMEE_CHROME_ARGS` elle rend toujours WebGL absent. **La preuve est dans la base** (§ 6, requête donnée). **Remesure** (campagne 11, 90 passages, mêmes cellules que la campagne 6 du 17/11) : 15 sur 15 aux six niveaux (la campagne 6 : 15, 15, 15, 15, 15, 12), WebGL présent et canvas stable sur 90 empreintes sur 90. **Ce n'est pas la preuve que le réglage améliore les taux** : voir § 6.

## 1. Ce que la sonde affiche, réglage par réglage

Sonde `scripts/fumee-linux.sh sonde amd64 ecran chrome` avec `FUMEE_CHROME_ARGS` (arguments ajoutés à Chrome par un lanceur posé à la place du binaire, `docker/linux/entrypoint.sh` ; mesure seulement). JSON : `webgl-linux-sans-gpu-2026-11-17-donnees/sondes/`.

| Réglage (arguments ajoutés) | WebGL | Fournisseur | Moteur de rendu | WebGL2 |
|---|---|---|---|---|
| aucun (état d'avant) | **absent** | – | – | absent |
| `--disable-gpu` | **absent** | – | – | absent |
| `--use-gl=angle --use-angle=gl` | **absent** | – | – | absent |
| `--enable-unsafe-swiftshader` | présent | `Google Inc. (Google)` | `ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)` | présent |
| `--use-angle=swiftshader --enable-unsafe-swiftshader` | présent | `Google Inc. (Google)` | idem | présent |
| **`--ignore-gpu-blocklist`** (seul) | présent | `Google Inc. (Mesa)` | `ANGLE (Mesa, llvmpipe (LLVM 20.1.2 128 bits), OpenGL 4.5)` | présent |
| `--use-angle=gl --ignore-gpu-blocklist` | présent | `Google Inc. (Mesa)` | idem (`OpenGL 4.5`) | présent |
| `--use-gl=angle --use-angle=gl-egl --ignore-gpu-blocklist` | présent | `Google Inc. (Mesa)` | `ANGLE (Mesa, llvmpipe (LLVM 20.1.2 128 bits), OpenGL ES 3.2)` | présent |
| `--use-angle=vulkan --enable-features=Vulkan --ignore-gpu-blocklist` (lavapipe) | présent | `Google Inc. (Mesa)` | `ANGLE (Mesa, Vulkan 1.4.318 (llvmpipe (LLVM 20.1.2 128 bits) (0x00000000)), llvmpipe)` | présent |

WebGPU : présent mais **sans adaptateur** dans tous les cas (inchangé).

## 2. La lecture du canvas 2D (sonde, 10 essais par réglage)

La sonde refait le contrôle de l'Arena (`canvasConsistencyTest` de `observateur.js` : deux lectures de suite d'un même canvas 2D doivent donner les mêmes octets), 10 fois.

| Réglage | WebGL | Essais instables |
|---|---|---|
| aucun | absent | 0 sur 10 |
| `--enable-unsafe-swiftshader` | SwiftShader | 0 sur 10 |
| `--ignore-gpu-blocklist` | llvmpipe | **10 sur 10** |
| `--ignore-gpu-blocklist --disable-gpu-rasterization` | llvmpipe | **10 sur 10** |
| `--use-angle=vulkan --ignore-gpu-blocklist` | lavapipe | **10 sur 10** |
| `--ignore-gpu-blocklist --disable-accelerated-2d-canvas` | llvmpipe | **0 sur 10** |
| `--ignore-gpu-blocklist --disable-accelerated-2d-canvas --disable-gpu-rasterization` | llvmpipe | 0 sur 10 |

Cause : `--ignore-gpu-blocklist` lève aussi le refus de l'accélération du canvas 2D par llvmpipe, dont la relecture n'est pas déterministe. `--disable-accelerated-2d-canvas` suffit à l'écarter (la désactivation de la rastérisation GPU n'y change rien).

## 3. Ce qu'en disent les détecteurs de l'Arena, tels qu'ils sont

Règles de l'Arena qui regardent WebGL (`detection.py`) : `webgl_logiciel` (détecteur `regles-js`, poids 0,25) si le moteur de rendu contient « swiftshader » ; `webgl_patche` et `canvas_webgl_patches` (0,75) si `getParameter` est enveloppé. **Aucune règle ne juge l'absence de WebGL, aucune ne vise llvmpipe.**
Campagnes courtes (`webgl-linux-essai.yaml` : identité native, Chrome 158, niveaux 03 à 06 sans corrélation, 3 scénarios × 2 répétitions = **6 passages par niveau**, le réglage vient de `FUMEE_CHROME_ARGS`) : mesure de signaux, **pas des taux**.

| Campagne | Réglage | 03 | 04 | 05 | 06 sans corr. | Signaux (hors corrélation) |
|---|---|---|---|---|---|---|
| 7 | aucun | 6 | 6 | 6 | 6 | `devices_vide` (24 passages sur 24) |
| 8 | `--enable-unsafe-swiftshader` | 6 | 6 | 6 | 5 | `devices_vide`, **`webgl_logiciel` (24 sur 24)** ; un blocage au 06 : composite 0,785 = `webgl_logiciel` + `duree_pages_reguliere` + `devices_vide` |
| 9 | `--ignore-gpu-blocklist` | 6 | 6 | **0** | **0** | `devices_vide`, **`getImageData_instable` (24 sur 24)** ; composite 0,85 aux niveaux 05 et 06 |
| 10 | `--ignore-gpu-blocklist --disable-accelerated-2d-canvas` | 6 | 6 | 6 | 6 | `devices_vide` seulement |

Seuils composites : 04 = 0,8 ; 05 = 0,6 ; 06 = 0,5 (`configs/arena/profils.yaml`).

## 4. Lequel ressemble le plus à un vrai poste Linux sans carte graphique

- **Un Chrome lancé par Patchright, sur cette machine, n'a pas de WebGL.** Je ne l'ai pas mesuré lancé à la main (sans les arguments par défaut de Playwright, dont `--disable-field-trial-config` et `--disable-background-networking`) : si un Chrome ordinaire en a un, l'état d'avant serait un signal du moteur ; **non vérifié**. Un humain avec un WebGL sur une telle machine l'a obtenu par un réglage explicite, ou par un Chrome plus ancien qui se repliait sur le rendu logiciel (intuition, non vérifiée). Je ne sais pas quelle part des vrais postes Linux sans carte graphique a un WebGL, ni lequel : **non établi ici**, aucune machine réelle ni statistique n'a été regardée.
- **Parmi les réglages qui donnent un WebGL, llvmpipe par ANGLE sur OpenGL est le plus ordinaire** : la chaîne `ANGLE (Mesa, llvmpipe (LLVM …, … bits), OpenGL 4.5)` a le même format que celles des cartes Linux réelles (`ANGLE (fournisseur, moteur, OpenGL x.y)`), et c'est le chemin que Chrome prend sur Linux avec Mesa. SwiftShader (`Vulkan 1.3.0 (SwiftShader Device (Subzero)…)`) est la signature connue de Chrome sans interface dans un conteneur, et l'Arena le marque déjà ; lavapipe (Vulkan) est peu courant sur Linux de bureau ; `OpenGL ES 3.2` est celui des systèmes qui passent par EGL (Wayland, mobiles). Ceci vient de ma connaissance générale, **non vérifié** ici.
- **Le piège du canvas** (§ 2) : llvmpipe seul est reconnu par l'Arena comme instable. Une vraie machine à llvmpipe aurait-elle ce défaut ? Non établi ; ce qui est mesuré, c'est qu'un moteur qui le laisserait est arrêté.

## 5. Choix et correctif (D-102)

`--ignore-gpu-blocklist --disable-accelerated-2d-canvas` (`moteur.ARGUMENTS_WEBGL_SANS_GPU`), ajoutés seulement quand les quatre conditions tiennent : Linux (`_HOTE_OS`), aucun nœud `/dev/dri/*` ni `/dev/nvidia*` (`moteur.sans_carte_graphique()`), identité native, avec interface (`headless` faux). Sans interface, Chrome a déjà un WebGL (SwiftShader du « headless shell » : campagnes 1 et 4) : rien n'est ajouté. Sur macOS, avec une carte, ou en identité réécrite : rien ne change (tests).
Déclaré dans `configuration()` : `webgl_sans_carte_graphique_arguments`, présent seulement là où le réglage s'applique (la configuration enregistrée ne change donc pas ailleurs, macOS compris). Tests : `tests/test_webgl_sans_carte_graphique.py` (25, écrits d'abord, vus en échec).

## 6. Remesure : campagne 11 contre campagne 6

Même fichier que la campagne 6 (`fumee-linux-natif.yaml` : identité native, vrai Chrome, Xvfb, amd64 ; 15 passages par niveau, niveaux 01 à 06 sans corrélation), **sans aucun argument injecté** : c'est le moteur qui ajoute les deux arguments.

| Niveau | 01 | 02 | 03 | 04 | 05 | 06 sans corr. |
|---|---|---|---|---|---|---|
| Campagne 6 (17/11, Chrome 157, WebGL absent) | 15 | 15 | 15 | 15 | 15 | 12 |
| **Campagne 11** (Chrome 158, WebGL llvmpipe) | 15 | 15 | 15 | 15 | 15 | 15 |

WebGL présent et `getImageData` stable sur 90 empreintes sur 90 (campagne 6 : WebGL absent sur 90 sur 90) ; la configuration enregistrée porte `webgl_sans_carte_graphique_arguments`. `devices_vide` reste sur 90 passages sur 90 (inchangé : autre incohérence de la note du 17/11).

**Où lire la preuve** (la base copiée `outputs/fumee-linux-webgl-2026-11-18.sqlite3`) : `SELECT json_extract(f.browser_properties,'$.webgl.disponible'), json_extract(f.browser_properties,'$.canvas_consistency.getImageData_stable'), count(*) FROM fingerprints f JOIN runs r ON r.id=f.run_id WHERE r.experiment_id=11 GROUP BY 1,2` (90 lignes : WebGL présent, canvas stable) ; la configuration enregistrée : `SELECT g.configuration FROM runs r JOIN engines g ON g.id=r.engine_id WHERE r.experiment_id=11 LIMIT 1` (clé `webgl_sans_carte_graphique_arguments`).

**Ce que cela ne prouve pas** : que le réglage fait passer le niveau 06. Les trois blocages de la campagne 6 venaient de `duree_pages_reguliere` + `devices_vide` ; la campagne 11 a encore `duree_pages_reguliere` sur 5 passages (niveaux 01, 03, 06 ; deux au 06, tous réussis) sans blocage. Avec 15 passages par niveau, 12 sur 15 contre 15 sur 15 peut être du hasard ; en outre Chrome a changé de version (157 vers 158). **La seule affirmation tenable** : le réglage ne dégrade rien dans ces 90 passages et donne un WebGL présent et un canvas stable. La cause de `duree_pages_reguliere` reste ouverte.

## 7. Ce que je ne sais pas, et les limites

- Si des détecteurs du commerce marquent llvmpipe, ou l'absence de WebGL ; l'Arena ne marque ni l'un ni l'autre aujourd'hui (une règle « WebGL absent » serait une étape à part).
- Sous Rosetta, llvmpipe annonce **« 128 bits »** (SSE seulement, pas d'AVX) ; sur un vrai x86_64 avec AVX2 on attend « 256 bits » : cette partie de la chaîne vient de l'émulation. Non vérifié sur un vrai serveur.
- La version de LLVM et de Mesa de l'image (LLVM 20.1.2, Mesa 25.2.8) apparaît dans la chaîne ; un vrai poste en aurait d'autres.
- Chrome 158 contre 157 ; un seul poste ; 6 passages par niveau pour les campagnes 7 à 10 ; 15 pour la 11 ; niveau 07 non mesuré.
- `sans_carte_graphique()` regarde `/dev/dri` et `/dev/nvidia*` : un serveur avec une carte mais sans ces nœuds visibles dans un conteneur serait pris pour une machine sans carte ; non essayé.
- **Chrome lancé à la main** (sans les arguments par défaut de Playwright) : non essayé, voir § 4.
- **`/dev/dri` sur un vrai serveur** : `sans_carte_graphique()` répond « une carte » dès qu'un nœud `/dev/dri/*` existe (le test fige « card0 = une carte »). Beaucoup de machines virtuelles exposent un nœud d'affichage sans rendu matériel : sur elles le correctif ne s'appliquerait pas, sans erreur. **Contrôle à faire à l'étape 3.3, sur la machine réelle** : `ls /dev/dri`, puis la présence de `webgl_sans_carte_graphique_arguments` dans la configuration enregistrée et `webgl.disponible` dans les empreintes.
- **Identité persistante sous Linux** : ce lancement n'a tourné qu'avec un faux Playwright (tests) ; la campagne 11 n'exerce que le lancement natif simple.
- **Coût du rendu llvmpipe** (bases des campagnes 6 et 11, par passage) : processeur moyen 62,3 % puis 74,3 %, temps processeur 10,7 s puis 13,3 s (environ +24 %) ; mémoire moyenne inchangée (2 314 puis 2 277, unité de la base).
- **La stabilité de l'image rendue par WebGL** (pas celle du canvas 2D) n'est pas sondée.
- Le crochet `FUMEE_CHROME_ARGS` remplace le binaire de Chrome du conteneur par un lanceur : outil de mesure, jamais utilisé par le moteur.

## 8. Coût disque

Image amd64 reconstruite (Mesa en plus) : environ 4,7 Go d'images et 4,9 Go de cache de construction, comme le 17/11 ; le disque libre est resté entre 24 et 33 Gio. Place rendue à la fin (cache de construction par identifiant, image, pile arrêtée) : voir le journal.

## 9. Refaire

```bash
scripts/fumee-linux.sh disque && scripts/fumee-linux.sh construire amd64
FUMEE_ARCH_GENERATION=amd64 scripts/fumee-linux.sh pile
FUMEE_ETIQUETTE=essai FUMEE_CHROME_ARGS="--ignore-gpu-blocklist" scripts/fumee-linux.sh sonde amd64 ecran chrome   # un réglage, à la sonde
FUMEE_CHROME_ARGS="…" scripts/fumee-linux.sh lancer amd64 ecran configs/experiments/webgl-linux-essai.yaml          # un réglage, à l'Arena (24 passages)
scripts/fumee-linux.sh lancer amd64 ecran configs/experiments/fumee-linux-natif.yaml                                # la remesure du moteur (90 passages, sans FUMEE_CHROME_ARGS)
FUMEE_ARCH_GENERATION=amd64 scripts/fumee-linux.sh sauvegarder
```
