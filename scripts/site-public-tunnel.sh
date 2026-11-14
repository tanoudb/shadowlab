#!/bin/bash
# Met le site public en ligne depuis ce poste, par un tunnel Cloudflare « rapide » (sans compte ni domaine).
#
#   SHADOWLAB_PUBLIC_CONTACT="Nom ou pseudonyme" scripts/site-public-tunnel.sh [tout|tunnel|app]
#
# Trois modes :
#   tout    (défaut) le tunnel puis l'application, dans le même terminal ; Ctrl+C arrête les deux.
#   tunnel  le tunnel seul : il lit l'adresse publique tirée au hasard, la note, et reste ouvert.
#   app     l'application seule, pour l'adresse du tunnel déjà ouvert (notée par le mode `tunnel`).
# Avec `tunnel` et `app` lancés à part (deux sessions tmux, par exemple), on peut relancer l'application après
# une mise à jour sans changer l'adresse publique : seul l'arrêt du tunnel la change.
#
# Ce que fait le script (mode `tout`) :
#   1. ouvre un tunnel cloudflared vers http://127.0.0.1:<port> (aucun port ouvert sur la box) ;
#   2. lit l'adresse publique tirée au hasard (https://…trycloudflare.com) et l'affiche ;
#   3. lance l'application publique pour cette adresse seulement, en tenant le Mac éveillé.
# L'adresse change à chaque ouverture du tunnel.
# Seule l'application publique est exposée ; le labo (shadowlab site) ne passe jamais par ce tunnel.
# Limites et conditions : docs/site-public.md, « Mise en ligne rapide depuis ce poste ».
set -euo pipefail

cd "$(dirname "$0")/.."

mode="${1:-tout}"
case "$mode" in
    tout | tunnel | app) ;;
    *)
        echo "Usage : $0 [tout|tunnel|app]" >&2
        exit 2
        ;;
esac

if [ "$mode" != "tunnel" ] && [ -z "${SHADOWLAB_PUBLIC_CONTACT:-}" ]; then
    echo "SHADOWLAB_PUBLIC_CONTACT est vide : donner le nom ou le pseudonyme du responsable." >&2
    exit 2
fi
for outil in cloudflared uv caffeinate; do
    command -v "$outil" >/dev/null || { echo "Outil absent : $outil" >&2; exit 2; }
done

port="${SHADOWLAB_PUBLIC_PORT:-8771}"
dossier="${SHADOWLAB_PUBLIC_DOSSIER:-outputs/public}"
journal="$dossier/tunnel.log"
adresse="$dossier/adresse-publique.txt"

# Filtre appliqué à chaque ligne de cloudflared AVANT son écriture dans le journal (`sed` de macOS : -E pour les
# expressions étendues, -l pour une sortie ligne à ligne). En cas d'erreur, cloudflared peut écrire l'adresse
# complète demandée (chemin et chaîne de requête, où passe le jeton `sl=`), avec l'heure. Le filtre :
#   1. réduit toute adresse `schéma://hôte/…` à `schéma://hôte` (l'hôte du tunnel reste lisible : le script le lit) ;
#   2. remplace un chemin suivi d'une chaîne de requête par `/[masque]` ;
#   3. masque toute chaîne de requête restante, puis tout `sl=…`.
# Il est lu par tests/test_public.py. Vérifié avec un vrai tunnel le 14/11/2026 pour les lignes de démarrage (aucun
# `sl=`) ; jamais vérifié sur une vraie ligne d'erreur de cloudflared (supposées, pas observées) ; un chemin sans chaîne de requête,
# hors adresse complète, n'est pas masqué. Le journal contient l'adresse du poste sur le réseau local : hors de git.
FILTRE_JOURNAL='s~([a-z][a-z0-9+.-]*)://([^/ ?",;<>|]+)[^ ",;<>|]*~\1://\2~g; s~/[^ ",;<>|?]*\?[^ ",;<>|]+~/[masque]~g; s~\?[^ ",;<>|]+~?[masque]~g; s~sl=[^& ",;<>|]*~sl=[masque]~g'

hote=""
tunnel=""

ouvrir_tunnel() {
    mkdir -p "$dossier"
    chmod 700 "$dossier"
    : > "$journal"
    # Niveau « info ». `$tunnel` reste le PID de cloudflared (substitution de processus, pas de tube) : le `trap` le
    # tue, et `sed` s'arrête de lui-même quand cloudflared ferme sa sortie.
    cloudflared tunnel --no-autoupdate --loglevel info --url "http://127.0.0.1:$port" > >(sed -l -E "$FILTRE_JOURNAL" >> "$journal") 2>&1 &
    tunnel=$!
    trap 'kill "$tunnel" 2>/dev/null || true' EXIT

    for _ in $(seq 1 60); do
        hote="$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' "$journal" | grep -v '^https://api\.' | head -1 | sed 's#^https://##' || true)"
        [ -n "$hote" ] && break
        kill -0 "$tunnel" 2>/dev/null || { echo "cloudflared s'est arrêté (voir $journal)." >&2; exit 1; }
        sleep 1
    done
    if [ -z "$hote" ]; then
        echo "Le tunnel n'a pas donné d'adresse en 60 secondes (voir $journal)." >&2
        exit 1
    fi

    echo "https://$hote" > "$adresse"
    echo
    echo "  Site public : https://$hote"
    echo "  (adresse aussi écrite dans $adresse ; Ctrl+C pour tout arrêter)"
    echo
}

servir() {
    # Cloudflare pose CF-Connecting-IP ; personne ne joint l'application sans passer par le tunnel. Le mode HTTPS est
    # imposé (cookies `Secure` et `__Host-`, HSTS) : une valeur `0` restée dans le shell ou dans `.env` après un essai
    # local ne doit jamais mettre le site en ligne sans eux.
    SHADOWLAB_PUBLIC_HOTES="$hote" \
    SHADOWLAB_PUBLIC_HTTPS=1 \
    SHADOWLAB_PUBLIC_ENTETE_IP="CF-Connecting-IP" \
    SHADOWLAB_PUBLIC_PORT="$port" \
        caffeinate -is uv run shadowlab public servir
}

case "$mode" in
    tout)
        ouvrir_tunnel
        servir
        ;;
    tunnel)
        ouvrir_tunnel
        echo "  Tunnel seul : lancer l'application à part avec « $0 app »."
        wait "$tunnel"
        ;;
    app)
        if [ ! -s "$adresse" ]; then
            echo "Aucune adresse notée dans $adresse : ouvrir d'abord le tunnel (« $0 tunnel »)." >&2
            exit 2
        fi
        hote="$(head -1 "$adresse" | sed 's#^https://##')"
        echo "  Application seule, pour le tunnel déjà ouvert : https://$hote"
        servir
        ;;
esac
