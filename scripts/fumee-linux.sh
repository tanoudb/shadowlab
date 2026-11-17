#!/usr/bin/env bash
# Essai de fumée Linux (étape 3.1) : le moteur noezia dans un conteneur Linux sans carte graphique, contre l'Arena.
#
# Montage : le site, le frontal TLS, la campagne, la base et le moteur tournent DANS le conteneur ; seule la pile
# Nginx + Coraza reste sur OrbStack (projet Docker et ports à part, ceux du dossier principal et de la course
# restent intacts). Détail et raisons : docs/recherche/fumee-linux-2026-11-17.md.
#
# Usage (depuis la racine du dépôt) :
#   scripts/fumee-linux.sh disque                                        espace libre (arrêt sous 20 Gio)
#   scripts/fumee-linux.sh construire <arm64|amd64>                      image shadowlab-linux:<arch>
#   scripts/fumee-linux.sh pile                                          génère les configurations, lance la pile
#   scripts/fumee-linux.sh lancer <arm64|amd64> <ecran|sans-ecran> <campagne.yaml>   un conteneur, en arrière-plan
#   scripts/fumee-linux.sh suivre <arm64|amd64> <ecran|sans-ecran>       journal du conteneur
#   scripts/fumee-linux.sh sonde <arm64|amd64> <ecran|sans-ecran> <chrome|chromium>   ce que le navigateur réel montre
#   scripts/fumee-linux.sh sauvegarder                                   copie la base vers outputs/shadowlab.sqlite3
#   scripts/fumee-linux.sh arreter                                       arrête la pile (jamais Docker ni OrbStack)
#   scripts/fumee-linux.sh retirer <arm64|amd64>                         supprime l'image et les conteneurs de cette archi
#
# La base vit dans le volume Docker `fumee-linux-data` (SQLite en mode WAL : jamais sur un dossier partagé avec le
# Mac) ; `sauvegarder` en fait une copie cohérente. Ne supprimer ni le volume ni cette copie.
# Aucun secret, aucun .env lu, aucune suppression récursive, aucun droit administrateur.
set -euo pipefail

DEPOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJET="fumee-linux"
PORT_ARENA=8744   # frontal TLS (dans le conteneur)
PORT_SITE=8745    # site (dans le conteneur, publié sur 127.0.0.1 pour que Coraza le joigne)
PORT_AVAL=8746    # Nginx de la pile (publié sur 127.0.0.1)
VOLUME="fumee-linux-data"
SORTIES="$DEPOT/outputs/fumee-linux"
PROFILS_EXTRA="configs/arena/profils-sans-correlation.yaml"
SEUIL_GIO=20
CPUS="${FUMEE_CPUS:-6}"
MEMOIRE="${FUMEE_MEMOIRE:-5g}"

erreur() { echo "fumee-linux.sh : $*" >&2; exit 1; }

arch_valide() { case "$1" in arm64|amd64) ;; *) erreur "architecture : arm64 ou amd64" ;; esac; }
ecran_valide() { case "$1" in ecran|sans-ecran) ;; *) erreur "mode : ecran ou sans-ecran" ;; esac; }

libre_gio() { df -g / | awk 'NR==2 {print $4}'; }

exiger_disque() {
  local libre; libre="$(libre_gio)"
  [ "$libre" -ge "$SEUIL_GIO" ] || erreur "disque : ${libre} Gio libres, seuil ${SEUIL_GIO} Gio : arrêt (voir « disque »)"
}

# Variables communes du conteneur (ports, périmètre fermé au bouclage, sorties, base dans le volume).
env_conteneur() {
  printf '%s\n' \
    -e "SHADOWLAB_PORT=$PORT_SITE" -e "SHADOWLAB_PORT_ARENA=$PORT_ARENA" -e "SHADOWLAB_PORT_AVAL=$PORT_AVAL" \
    -e "SHADOWLAB_ARENA_PROJET=$PROJET" -e "SHADOWLAB_HOTES_AUTORISES=localhost,127.0.0.1" \
    -e "SHADOWLAB_SORTIES=/srv/outputs" -e "SHADOWLAB_BASE=/data/shadowlab.sqlite3" \
    -e "SHADOWLAB_PROFILS_EXTRA=$PROFILS_EXTRA"
}

commande="${1:-}"
[ $# -gt 0 ] && shift
case "$commande" in
  disque)
    df -h /
    docker system df
    ;;
  construire)
    [ $# -eq 1 ] || erreur "usage : construire <arm64|amd64>"
    arch_valide "$1"; exiger_disque
    docker build --platform "linux/$1" -f "$DEPOT/docker/linux/Dockerfile" -t "shadowlab-linux:$1" "$DEPOT"
    df -h /
    ;;
  pile)
    exiger_disque
    arch="${FUMEE_ARCH_GENERATION:-arm64}"
    mkdir -p "$SORTIES"
    # 1. Les configurations Nginx et Coraza sont générées par le code de l'Arena, dans l'image (pas de Python sur le Mac).
    # shellcheck disable=SC2046
    docker run --rm --platform "linux/$arch" --add-host host.docker.internal:host-gateway \
      $(env_conteneur) -v "$SORTIES:/srv/outputs" "shadowlab-linux:$arch" \
      python -c "from shadowlab.config import charger; from shadowlab.arena import pile; print(pile.generer(charger()))"
    # 2. La pile : l'image Coraza du dossier principal sous une étiquette à nous (aucun octet de plus).
    docker tag shadowlab-coraza:local "shadowlab-coraza:$PROJET"
    SHADOWLAB_ARENA_DIR="$SORTIES/arena" SHADOWLAB_PORT_AVAL="$PORT_AVAL" SHADOWLAB_PORT="$PORT_SITE" \
      SHADOWLAB_ARENA_PROJET="$PROJET" SHADOWLAB_ARENA_IMAGE="shadowlab-coraza:$PROJET" \
      docker compose -p "$PROJET" -f "$DEPOT/docker/arena/docker-compose.yml" up -d --wait --force-recreate
    docker ps --filter "label=com.docker.compose.project=$PROJET" --format '{{.Names}}\t{{.Ports}}'
    ;;
  lancer)
    [ $# -eq 3 ] || erreur "usage : lancer <arm64|amd64> <ecran|sans-ecran> <campagne.yaml>"
    arch_valide "$1"; ecran_valide "$2"; exiger_disque
    nom="$PROJET-$1-$2"
    docker rm "$nom" >/dev/null 2>&1 || true
    ecran=0; [ "$2" = "ecran" ] && ecran=1
    # shellcheck disable=SC2046
    docker run -d --name "$nom" --platform "linux/$1" --cpus "$CPUS" --memory "$MEMOIRE" --shm-size 1g \
      --add-host host.docker.internal:host-gateway -p "127.0.0.1:$PORT_SITE:$PORT_SITE" \
      $(env_conteneur) -e "FUMEE_ECRAN=$ecran" \
      -v "$VOLUME:/data" -v "$SORTIES:/srv/outputs" \
      "shadowlab-linux:$1" shadowlab campagne "$3"
    echo "Conteneur $nom lancé ; journal : scripts/fumee-linux.sh suivre $1 $2"
    ;;
  suivre)
    [ $# -eq 2 ] || erreur "usage : suivre <arm64|amd64> <ecran|sans-ecran>"
    docker logs -f --tail 50 "$PROJET-$1-$2"
    ;;
  sauvegarder)
    mkdir -p "$DEPOT/outputs"
    arch="${FUMEE_ARCH_GENERATION:-arm64}"  # l'entrée normale exige les ports : on la remplace pour une simple copie
    docker run --rm --platform "linux/$arch" --entrypoint python -v "$VOLUME:/data" -v "$DEPOT/outputs:/sortie" \
      "shadowlab-linux:$arch" \
      -c "import sqlite3; s = sqlite3.connect('file:/data/shadowlab.sqlite3?mode=ro', uri=True); d = sqlite3.connect('/sortie/shadowlab.sqlite3'); s.backup(d); print('copie faite')"
    ls -la "$DEPOT/outputs/shadowlab.sqlite3"
    ;;
  sonde)
    # Ce que le navigateur réel montre à une page (sans le moteur) : JSON dans outputs/fumee-linux/sondes/.
    [ $# -eq 3 ] || erreur "usage : sonde <arm64|amd64> <ecran|sans-ecran> <chrome|chromium>"
    arch_valide "$1"; ecran_valide "$2"; exiger_disque
    case "$3" in chrome|chromium) ;; *) erreur "navigateur : chrome ou chromium" ;; esac
    ecran=0; sans=(--sans-interface); [ "$2" = "ecran" ] && { ecran=1; sans=(); }
    mkdir -p "$SORTIES/sondes"
    # shellcheck disable=SC2046
    docker run --rm --platform "linux/$1" --add-host host.docker.internal:host-gateway --shm-size 1g \
      $(env_conteneur) -e "FUMEE_ECRAN=$ecran" -v "$SORTIES:/srv/outputs" \
      -v "$DEPOT/scripts/fumee-linux-sonde.py:/sonde.py:ro" "shadowlab-linux:$1" \
      python /sonde.py --canal "$3" ${sans[@]+"${sans[@]}"} --sortie "/srv/outputs/sondes/$1-$2-$3.json"
    ;;
  arreter)
    SHADOWLAB_ARENA_DIR="$SORTIES/arena" SHADOWLAB_PORT_AVAL="$PORT_AVAL" SHADOWLAB_PORT="$PORT_SITE" \
      SHADOWLAB_ARENA_PROJET="$PROJET" SHADOWLAB_ARENA_IMAGE="shadowlab-coraza:$PROJET" \
      docker compose -p "$PROJET" -f "$DEPOT/docker/arena/docker-compose.yml" down
    ;;
  retirer)
    [ $# -eq 1 ] || erreur "usage : retirer <arm64|amd64>"
    arch_valide "$1"
    for nom in "$PROJET-$1-ecran" "$PROJET-$1-sans-ecran"; do docker rm -f "$nom" >/dev/null 2>&1 || true; done
    docker rmi "shadowlab-linux:$1"
    df -h /
    ;;
  *)
    sed -n 2,20p "${BASH_SOURCE[0]}"
    exit 2
    ;;
esac
