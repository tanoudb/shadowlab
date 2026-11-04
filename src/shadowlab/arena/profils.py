"""Niveaux de difficulté progressive (01-06) et génération des configurations Nginx et Coraza."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from ..config import RACINE

BASELINE = "01"
FICHIER = RACINE / "configs" / "arena" / "profils.yaml"

_COMPAT = {"faible": "02", "moyen": "04", "eleve": "05"}


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


ModeBlocage = Literal["non", "http", "tout"]


class Fingerprinting(_Strict):
    actif: bool
    bloquer: ModeBlocage = "non"
    exclure: list[str] = Field(default_factory=list)


class Honeypots(_Strict):
    actif: bool


class Turnstile(_Strict):
    actif: bool


class Recaptcha(_Strict):
    actif: bool


class Profil(_Strict):
    nom: str = ""
    description: str = ""
    limitation: Limitation
    waf: Waf
    defi_js: DefiJs
    captcha: Captcha
    fingerprinting: Fingerprinting = Fingerprinting(actif=False)
    honeypots: Honeypots = Honeypots(actif=False)
    turnstile: Turnstile = Turnstile(actif=False)
    recaptcha: Recaptcha = Recaptcha(actif=False)


class Profils:
    """Collection de niveaux chargés depuis YAML. Itérable, indexable par code de niveau."""

    def __init__(self, niveaux: dict[str, Profil]) -> None:
        self._niveaux = dict(sorted(niveaux.items()))

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(self._niveaux)

    @property
    def codes_arena(self) -> tuple[str, ...]:
        return tuple(c for c in self._niveaux if c != BASELINE)

    def de(self, niveau: str) -> Profil | None:
        niveau = _COMPAT.get(niveau, niveau)
        return self._niveaux.get(niveau)

    def __contains__(self, niveau: str) -> bool:
        return _COMPAT.get(niveau, niveau) in self._niveaux

    def __iter__(self):
        return iter(self._niveaux.items())

    def __len__(self):
        return len(self._niveaux)

    def items(self):
        return self._niveaux.items()

    def model_dump(self) -> dict:
        return {code: p.model_dump() for code, p in self._niveaux.items()}


def normaliser(niveau: str) -> str:
    return _COMPAT.get(niveau, niveau)


def charger(chemin: Path | None = None) -> Profils:
    with (chemin or FICHIER).open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    extra = os.environ.get("SHADOWLAB_PROFILS_EXTRA")
    if extra:
        with Path(extra).open(encoding="utf-8") as f:
            raw.update(yaml.safe_load(f) or {})
    niveaux = {}
    for code, data in raw.items():
        code_str = str(code)
        if code_str.isdigit():
            code_str = code_str.zfill(2)
        niveaux[code_str] = Profil.model_validate(data)
    return Profils(niveaux)


def enregistrer(profils: Profils, chemin: Path | None = None) -> None:
    (chemin or FICHIER).write_text(
        yaml.safe_dump(profils.model_dump(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


AUCUNE = BASELINE
NIVEAUX: tuple[str, ...] = ()
PROTECTIONS: tuple[str, ...] = ()


def _init_constantes() -> None:
    global NIVEAUX, PROTECTIONS  # noqa: PLW0603
    try:
        p = charger()
        NIVEAUX = p.codes_arena
        PROTECTIONS = p.codes
    except Exception:  # noqa: BLE001
        NIVEAUX = ("02", "03", "04", "05", "06")
        PROTECTIONS = (BASELINE, *NIVEAUX)


_init_constantes()


def rendre_nginx(profils: Profils) -> str:
    cartes, zones, limites = [], [], []
    for code in profils.codes_arena:
        p = profils.de(code)
        if p is None:
            continue
        lim = p.limitation
        cartes.append(f'  map $http_x_shadowlab_profil $cle_{code} {{ {code} $http_x_shadowlab_session; default ""; }}')
        zones.append(f"  limit_req_zone $cle_{code} zone={code}:4m rate={lim.debit}r/s;")
        limites.append(f"      limit_req zone={code} burst={lim.rafale} nodelay;")
    return f"""# Généré par `shadowlab arena appliquer` — ne pas éditer.
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
    lignes = [
        "# Généré par `shadowlab arena appliquer` — ne pas éditer.",
    ]
    for rang, code in enumerate(profils.codes_arena, start=1):
        p = profils.de(code)
        if p is None:
            continue
        w = p.waf
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
        lignes.append(f'SecRule REQUEST_HEADERS:X-ShadowLab-Profil "@streq {code}" "{",".join(actions)}"')
    return "\n".join(lignes) + "\n"
