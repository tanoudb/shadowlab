"""Déclare les quatre identités de l'essai des adresses simulées (4.1, D-105).

    uv run python scripts/ip-simulees-declarer.py <port de l'Arena>

Chaque identité reçoit un `proxy.json` (droits 0600) : l'amont `arena://127.0.0.1:<port>` et son adresse simulée, prise
dans les plages de documentation (RFC 5737). Aucun proxy réel, aucun identifiant. Le port doit être celui du frontal de
ce dossier de travail (`SHADOWLAB_PORT_ARENA`) : le relais de l'identité refuse tout autre hôte et tout autre port.
"""

from __future__ import annotations

import sys

from shadowlab.engines.noezia import identite

IDENTITES = {
    "ip-a-1": "198.51.100.11",
    "ip-b-1": "198.51.100.22",
    "ip-c-1": "203.0.113.33",
    "ip-c-2": "203.0.113.33",  # la même adresse que c-1 : un autre navigateur derrière la même adresse
}


def main(argv: list[str]) -> int:
    if len(argv) != 1 or not argv[0].isdigit():
        print(__doc__, file=sys.stderr)
        return 2
    port = int(argv[0])
    for nom, adresse in IDENTITES.items():
        chemin = identite.declarer_proxy(nom, f"arena://127.0.0.1:{port}", adresse_simulee=adresse)
        print(f"{nom} : {adresse} -> arena://127.0.0.1:{port} ({chemin})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
