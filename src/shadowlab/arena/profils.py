"""Profils de protection (faible, moyen, élevé) et génération des configurations Nginx et Coraza."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from ..config import RACINE

AUCUNE = "aucune"  # site servi en direct, sans frontal : la référence du MVP
NIVEAUX = ("faible", "moyen", "eleve")
PROTECTIONS = (AUCUNE, *NIVEAUX)
FICHIER = RACINE / "configs" / "arena" / "profils.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Limitation(_Strict):
    debit: int = Field(ge=1, le=1000)
    rafale: int = Field(ge=0, le=1000)


class Waf(_Strict):
    mode: Literal["detection", "blocage"]
    paranoia: int = Field(ge=1, le=4)
    seuil: int = Field(ge=1, le=100)


class DefiJs(_Strict):
    actif: bool
    difficulte: int = Field(default=0, ge=0, le=22)
    lier_tls: bool = False


class Captcha(_Strict):
    actif: bool


class Profil(_Strict):
    limitation: Limitation
    waf: Waf
    defi_js: DefiJs
    captcha: Captcha


class Profils(_Strict):
    faible: Profil
    moyen: Profil
    eleve: Profil

    def de(self, niveau: str) -> Profil | None:
        return getattr(self, niveau) if niveau in NIVEAUX else None


def charger(chemin: Path | None = None) -> Profils:
    with (chemin or FICHIER).open(encoding="utf-8") as f:
        return Profils.model_validate(yaml.safe_load(f))


def enregistrer(profils: Profils, chemin: Path | None = None) -> None:
    (chemin or FICHIER).write_text(yaml.safe_dump(profils.model_dump(), sort_keys=False), encoding="utf-8")


def rendre_nginx(profils: Profils) -> str:
    """Une zone de limitation par profil. La clé est vide hors de son profil : Nginx ne compte alors pas la requête."""
    cartes, zones, limites = [], [], []
    for niveau in NIVEAUX:
        p = profils.de(niveau).limitation
        cartes.append(
            f'  map $http_x_shadowlab_profil $cle_{niveau} {{ {niveau} $http_x_shadowlab_session; default ""; }}'
        )
        zones.append(f"  limit_req_zone $cle_{niveau} zone={niveau}:4m rate={p.debit}r/s;")
        limites.append(f"      limit_req zone={niveau} burst={p.rafale} nodelay;")
    return f"""# Généré par `shadowlab arena appliquer` depuis configs/arena/profils.yaml : ne pas éditer.
worker_processes 1;
error_log /var/log/arena/nginx-erreurs.log warn;
pid /tmp/nginx.pid;
events {{ worker_connections 1024; }}
http {{
  log_format arena escape=json '{{"t":"$time_iso8601","session":"$http_x_shadowlab_session",'
    '"profil":"$http_x_shadowlab_profil","methode":"$request_method","chemin":"$uri","statut":$status,'
    '"limite":"$limit_req_status","amont_s":"$upstream_response_time"}}';
  access_log /var/log/arena/nginx.jsonl arena;
{chr(10).join(cartes)}
{chr(10).join(zones)}
  limit_req_status 429;
  limit_req_log_level warn;
  client_max_body_size 1m;
  upstream waf {{ server coraza:8782; keepalive 16; }}
  server {{
    listen 8781;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $http_host;
    location = /arena-sante {{ proxy_pass http://waf/waf-sante; }}
    # Échanges techniques (fichiers, télémétrie, réponses aux défis) : une page en déclenche plusieurs, et les compter
    # bloquerait aussi une vraie personne. La limitation porte sur les pages.
    location ~ ^/lab/(static|collecte|verdict|defi|captcha)(/|$) {{ proxy_pass http://waf; }}
    location / {{
{chr(10).join(limites)}
      add_header X-ShadowLab-Limite $limit_req_status always;
      proxy_pass http://waf;
    }}
  }}
}}
"""


def rendre_coraza(profils: Profils) -> str:
    """Règles placées avant le CRS : le niveau de paranoïa et le seuil dépendent du profil de la requête."""
    lignes = ["# Généré par `shadowlab arena appliquer` depuis configs/arena/profils.yaml : ne pas éditer."]
    for rang, niveau in enumerate(NIVEAUX, start=1):
        w = profils.de(niveau).waf
        actions = [
            f"id:{1000 + rang}",
            "phase:1",
            "pass",
            "nolog",
            f"setvar:tx.blocking_paranoia_level={w.paranoia}",
            f"setvar:tx.detection_paranoia_level={w.paranoia}",
            f"setvar:tx.inbound_anomaly_score_threshold={w.seuil}",
        ]
        if w.mode == "detection":
            actions.append("ctl:ruleEngine=DetectionOnly")
        lignes.append(f'SecRule REQUEST_HEADERS:X-ShadowLab-Profil "@streq {niveau}" "{",".join(actions)}"')
    return "\n".join(lignes) + "\n"
