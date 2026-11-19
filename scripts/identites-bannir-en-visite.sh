#!/usr/bin/env bash
# Étape 4.2 (D-106) : bannit exprès une identité d'une récolte partagée PENDANT une de ses visites, par la commande
# prévue pour cela (`uv run shadowlab arena bannir --visiteur <id> --monde <nom>`), une seule fois.
#
#   scripts/identites-bannir-en-visite.sh <n° de campagne> <libellé du bras> <n° de visite> <secondes>
#
# Attend que le bras ait une visite, la <n° de visite>-ième ou une suivante, qui tourne depuis <secondes> (passage
# `en_cours` dans la base du labo, son visiteur vu par l'Arena), lit le visiteur et le monde de CETTE visite (jamais « le
# dernier visiteur du monde » : dans une récolte partagée, toutes les identités sont dans le même monde), puis lance
# `arena bannir`. Une visite qui finit avant le délai (la visite vide du départ, quand une autre identité a pris la page
# de départ) est passée : la suivante est guettée. Lancer depuis le dossier du code, avec les mêmes variables
# d'environnement que la campagne (SHADOWLAB_BASE…). Lecture seule de la base jusqu'au bannissement.
# Code 0 : banni ; 1 : la campagne a fini avant (rien n'est écrit) ; 2 : mauvais arguments ou campagne inconnue.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ $# -ne 4 || ! $1 =~ ^[0-9]+$ || ! $2 =~ ^[a-z0-9][a-z0-9_-]*$ || ! $3 =~ ^[0-9]+$ || ! $4 =~ ^[0-9]+$ ]]; then
  echo "usage : $0 <n° de campagne> <libellé du bras> <n° de visite> <secondes>" >&2
  exit 2
fi
campagne=$1 bras=$2 visite=$3 apres=$4
base=${SHADOWLAB_BASE:-outputs/shadowlab.sqlite3}
filtre="r.experiment_id = $campagne AND json_extract(e.configuration, '\$.label') = '$bras' AND r.repetition >= $visite"

while true; do
  statut=$(sqlite3 -readonly "$base" "SELECT status FROM experiments WHERE id = $campagne")
  if [[ -z $statut ]]; then
    echo "campagne $campagne inconnue dans $base" >&2
    exit 2
  fi
  ligne=$(sqlite3 -readonly -separator ' ' "$base" \
    "SELECT r.repetition, m.nom, v.visiteur FROM runs r JOIN engines e ON e.id = r.engine_id
       JOIN visites v ON v.session_token = r.session_token JOIN mondes m ON m.id = v.monde_id
      WHERE $filtre AND r.status = 'en_cours' AND (julianday('now') - julianday(r.started_at)) * 86400 >= $apres
      ORDER BY r.repetition LIMIT 1")
  if [[ -n $ligne ]]; then
    read -r numero monde visiteur <<<"$ligne"
    echo "$(date -u +%FT%TZ) visite $numero de $bras en cours depuis $apres s ou plus : bannissement du visiteur $visiteur dans le monde $monde"
    uv run shadowlab arena bannir --visiteur "$visiteur" --monde "$monde"
    exit 0
  fi
  if [[ $statut != creee && $statut != en_cours ]]; then
    echo "$(date -u +%FT%TZ) campagne $campagne $statut : aucune visite de $bras (à partir de la visite $visite) n'a duré $apres s ; aucun bannissement écrit" >&2
    exit 1
  fi
  sleep 5
done
