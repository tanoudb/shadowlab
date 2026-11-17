#!/bin/sh
# Entrée du conteneur « shadowlab-linux » (étape 3.1). Dans le conteneur tournent le site, le frontal TLS, la
# campagne et le moteur ; seule la pile Nginx + Coraza reste sur le poste (projet Docker à part, ports à part).
# Le code de l'Arena vise des adresses en dur (frontal -> 127.0.0.1:<aval>, Coraza -> host.docker.internal:<site>) :
# deux relais socat les satisfont sans toucher à l'Arena.
#   relais A : 127.0.0.1:<aval> du conteneur -> la pile du poste (host.docker.internal:<aval>)
#   relais B : <adresse du conteneur>:<site> -> 127.0.0.1:<site> (le site n'écoute que le bouclage ; Coraza le
#              joint par le poste, port publié par `docker run -p 127.0.0.1:<site>:<site>`)
# Le moteur, lui, ne voit que https://localhost:<frontal> : le périmètre (bouclage seul) n'est pas élargi.
set -eu

: "${SHADOWLAB_PORT:?SHADOWLAB_PORT (port du site) est exigé}"
: "${SHADOWLAB_PORT_AVAL:?SHADOWLAB_PORT_AVAL (Nginx de la pile) est exigé}"

socat "TCP-LISTEN:${SHADOWLAB_PORT_AVAL},bind=127.0.0.1,reuseaddr,fork" "TCP:host.docker.internal:${SHADOWLAB_PORT_AVAL}" &
ADRESSE="$(hostname -i | awk '{print $1}')"
socat "TCP-LISTEN:${SHADOWLAB_PORT},bind=${ADRESSE},reuseaddr,fork" "TCP:127.0.0.1:${SHADOWLAB_PORT}" &

# Écran virtuel : seulement quand on le demande (un passage « sans écran » n'a pas de serveur X du tout).
if [ "${FUMEE_ECRAN:-0}" = "1" ]; then
  Xvfb :99 -screen 0 "${FUMEE_ECRAN_TAILLE:-1920x1080x24}" -nolisten tcp &
  for _ in $(seq 1 50); do [ -e /tmp/.X11-unix/X99 ] && break; sleep 0.1; done
  [ -e /tmp/.X11-unix/X99 ] || { echo "Xvfb n'a pas démarré" >&2; exit 1; }
  export DISPLAY=:99
fi

# MESURE SEULEMENT : `FUMEE_CHROME_ARGS` ajoute des arguments de lancement à Google Chrome, par un lanceur posé à la place
# du binaire (Playwright lance `/opt/google/chrome/chrome` ; ses enfants relancent le vrai binaire, qui garde ses
# ressources à côté). Sert à comparer des réglages WebGL (docs/recherche/webgl-linux-sans-gpu-2026-11-17.md) avec la sonde et
# les campagnes, sans toucher au moteur. Sans la variable : rien n'est modifié.
if [ -n "${FUMEE_CHROME_ARGS:-}" ] && [ -x /opt/google/chrome/chrome ] && [ ! -e /opt/google/chrome/chrome.reel ]; then
  mv /opt/google/chrome/chrome /opt/google/chrome/chrome.reel
  printf '#!/bin/sh\nexec /opt/google/chrome/chrome.reel %s "$@"\n' "$FUMEE_CHROME_ARGS" > /opt/google/chrome/chrome
  chmod +x /opt/google/chrome/chrome
fi

exec "$@"
