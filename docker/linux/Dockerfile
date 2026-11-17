# Image « serveur Linux sans carte graphique » du moteur noezia (étape 3.1, essai de fumée).
# Une image par architecture : arm64 (celle du poste) ou amd64 (celle du vrai serveur, émulée sur le poste).
#   docker build --platform linux/arm64 -f docker/linux/Dockerfile -t shadowlab-linux:arm64 .
#   docker build --platform linux/amd64 -f docker/linux/Dockerfile -t shadowlab-linux:amd64 .
# Pilotée par `scripts/fumee-linux.sh` (voir docs/recherche/fumee-linux-2026-11-17.md).
#
# Contenu volontairement ordinaire, comme un serveur sans réglage : aucun GPU, aucun gestionnaire de fenêtres,
# polices = celles que `patchright install-deps` apporte, fuseau UTC, langue C.UTF-8. Seul écart : Xvfb, que
# l'entrée ne lance que pour les passages « avec écran virtuel » (FUMEE_ECRAN=1).
FROM ubuntu:24.04

ARG TARGETARCH
ARG UV_VERSION=0.13.1
ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_LINK_MODE=copy \
    UV_NO_SYNC=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/browsers \
    PATH=/opt/venv/bin:/usr/local/bin:/usr/bin:/bin

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl socat xvfb tini hostname \
 && rm -rf /var/lib/apt/lists/* \
 && curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" | env UV_UNMANAGED_INSTALL=/usr/local/bin sh

WORKDIR /app

# 1. Dépendances (couche mise en cache tant que pyproject.toml et uv.lock ne changent pas).
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

# 2. Navigateurs de Patchright (celui du moteur noezia) et leurs bibliothèques système.
RUN patchright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*

# 3. Google Chrome (« identité native »). Google ne publie pas Chrome pour Linux arm64 : l'essai est enregistré
#    pour les deux architectures, et ne fait pas échouer la construction.
RUN (patchright install chrome > /opt/chrome-installation.txt 2>&1 && echo "chrome: installé" >> /opt/chrome-installation.txt) \
    || echo "chrome: NON installé pour ${TARGETARCH}" >> /opt/chrome-installation.txt; \
    rm -rf /var/lib/apt/lists/*; cat /opt/chrome-installation.txt

# 4. Le code. Le dépôt n'est pas monté : l'image est l'état exact d'un commit.
COPY README.md ./
COPY src ./src
COPY configs ./configs
RUN uv sync --frozen --no-dev
COPY docker/linux/entrypoint.sh /usr/local/bin/entree-fumee
RUN chmod +x /usr/local/bin/entree-fumee

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entree-fumee"]
CMD ["shadowlab", "moteurs", "etat"]
