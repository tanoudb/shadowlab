#!/usr/bin/env bash
# Course de 7 jours (étape I9) dans un dossier isolé : une copie figée du code à une étiquette git, sous
# .courses/i9/, avec son propre site, sa base, ses sorties, ses identités et sa propre pile Docker de l'Arena.
#
# Usage (depuis le dépôt principal) :
#   scripts/course.sh preparer <étiquette>      copie figée du code (git worktree détaché) + uv sync
#   scripts/course.sh demarrer <configuration>  lance la campagne dans la session tmux course-i9
#   scripts/course.sh reprendre <n°>            reprend une campagne interrompue
#   scripts/course.sh etat                      session, conteneurs, santé de la chaîne, journal
#   scripts/course.sh bilan <n°>                bilan de la soirée
#   scripts/course.sh arreter                   arrêt d'urgence (crée <sorties>/ARRET)
#   scripts/course.sh empreinte                 preuve d'isolation (à comparer avant/après avec diff)
#
# L'environnement vient de configs/courses/i9.env DE CE DOSSIER (celui d'où le script est lancé), jamais du
# dossier de la course. Aucun secret, aucun fichier .env, aucune suppression récursive, aucun droit administrateur.
set -euo pipefail

DEPOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COURSE="$DEPOT/.courses/i9"
FICHIER_ENV="$DEPOT/configs/courses/i9.env"
SESSION="course-i9"
PROJET="shadowlab-course-i9"

erreur() { echo "course.sh : $*" >&2; exit 1; }

# Lit le fichier d'environnement : une ligne CLE=valeur par entrée, commentaires et lignes vides ignorés.
# Les chemins relatifs (SORTIES, IDENTITES) sont rendus absolus à partir du dossier de la course.
# Remplit le tableau VARIABLES (CLE=valeur), utilisable avec `env`.
charger_env() {
  [ -f "$FICHIER_ENV" ] || erreur "fichier d'environnement absent : $FICHIER_ENV"
  VARIABLES=()
  local ligne cle valeur
  while IFS= read -r ligne || [ -n "$ligne" ]; do
    case "$ligne" in ''|'#'*) continue ;; esac
    cle="${ligne%%=*}"
    valeur="${ligne#*=}"
    case "$cle" in
      SHADOWLAB_SORTIES|SHADOWLAB_IDENTITES)
        case "$valeur" in /*) ;; *) valeur="$COURSE/$valeur" ;; esac ;;
    esac
    VARIABLES+=("$cle=$valeur")
  done < "$FICHIER_ENV"
}

# Valeur d'une variable lue dans VARIABLES.
valeur_de() {
  local v
  for v in "${VARIABLES[@]}"; do
    case "$v" in "$1="*) echo "${v#*=}"; return ;; esac
  done
}

exiger_course() { [ -d "$COURSE" ] || erreur "dossier de la course absent : $COURSE (lancer d'abord « preparer »)"; }

# Exécute une commande dans le dossier de la course avec l'environnement de la course.
dans_course() {
  charger_env
  (cd "$COURSE" && env "${VARIABLES[@]}" "$@")
}

session_vivante() { tmux has-session -t "$SESSION" 2>/dev/null; }

# Lance dans tmux : pile Arena, puis la commande donnée. La sortie va dans outputs/course.log.
lancer_tmux() {
  exiger_course
  session_vivante && erreur "la session tmux $SESSION existe déjà"
  charger_env
  mkdir -p "$COURSE/outputs"
  local journal="$COURSE/outputs/course.log" commande
  # Les valeurs sont citées par printf %q : aucun caractère ne casse la ligne de commande.
  commande="cd $(printf %q "$COURSE") && env"
  local v
  for v in "${VARIABLES[@]}"; do commande+=" $(printf %q "$v")"; done
  commande+=" bash -c $(printf %q "caffeinate -i nice -n 10 uv run shadowlab arena demarrer && $1") >> $(printf %q "$journal") 2>&1"
  tmux new-session -d -s "$SESSION" -c "$COURSE" "$commande"
  echo "Session $SESSION lancée ; journal : $journal"
}

commande="${1:-}"
[ $# -gt 0 ] && shift
case "$commande" in
  preparer)
    [ $# -eq 1 ] || erreur "usage : preparer <étiquette>"
    [ -e "$COURSE" ] && erreur "le dossier $COURSE existe déjà"
    git -C "$DEPOT" worktree add --detach "$COURSE" "$1"
    (cd "$COURSE" && uv sync)
    git -C "$COURSE" describe --tags
    df -h /
    ;;
  demarrer)
    [ $# -eq 1 ] || erreur "usage : demarrer <configuration>"
    lancer_tmux "caffeinate -i nice -n 10 uv run shadowlab campagne $(printf %q "$1")"
    ;;
  reprendre)
    [ $# -eq 1 ] || erreur "usage : reprendre <n°>"
    case "$1" in ''|*[!0-9]*) erreur "le numéro de campagne doit être un entier" ;; esac
    lancer_tmux "caffeinate -i nice -n 10 uv run shadowlab reprendre $1"
    ;;
  etat)
    exiger_course
    charger_env
    if session_vivante; then echo "tmux $SESSION : vivante"; else echo "tmux $SESSION : absente"; fi
    echo "--- conteneurs ($PROJET)"
    docker ps -a --filter "label=com.docker.compose.project=$PROJET" \
      --format '{{.ID}}  créé {{.CreatedAt}}  {{.Names}}  {{.Status}}'
    echo "--- chaîne"
    dans_course uv run shadowlab arena etat || true
    echo "--- journal (20 dernières lignes)"
    tail -n 20 "$(valeur_de SHADOWLAB_SORTIES)/logs/shadowlab.jsonl" 2>/dev/null || echo "(aucun journal)"
    ;;
  bilan)
    [ $# -eq 1 ] || erreur "usage : bilan <n°>"
    exiger_course
    dans_course uv run shadowlab soiree bilan "$1"
    ;;
  arreter)
    exiger_course
    dans_course uv run shadowlab arreter
    ;;
  empreinte)
    exiger_course
    charger_env
    echo "--- conteneurs ($PROJET)"
    docker ps -a --filter "label=com.docker.compose.project=$PROJET" \
      --format '{{.Names}}  {{.ID}}  {{.CreatedAt}}' | sort
    echo "--- fichiers générés"
    generes="$(valeur_de SHADOWLAB_SORTIES)/arena/generes"
    if [ -d "$generes" ]; then
      (cd "$generes" && for f in *; do [ -f "$f" ] && shasum "$f"; done)
    else
      echo "(aucun)"
    fi
    ;;
  *)
    erreur "sous-commande inconnue « $commande » (preparer, demarrer, reprendre, etat, bilan, arreter, empreinte)"
    ;;
esac
