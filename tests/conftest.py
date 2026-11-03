from __future__ import annotations

import socket

import pytest

from shadowlab.config import charger


def port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def reglages(tmp_path, monkeypatch):
    """Réglages isolés : base et sorties temporaires, port libre (transmis au site lancé à part)."""
    monkeypatch.setenv("SHADOWLAB_SORTIES", str(tmp_path / "sorties"))
    monkeypatch.setenv("SHADOWLAB_BASE", str(tmp_path / "sorties" / "test.sqlite3"))
    monkeypatch.setenv("SHADOWLAB_PORT", str(port_libre()))
    monkeypatch.setenv("SHADOWLAB_PORT_ARENA", str(port_libre()))
    monkeypatch.delenv("SHADOWLAB_HOTE", raising=False)
    monkeypatch.delenv("SHADOWLAB_JETON", raising=False)
    return charger()


@pytest.fixture
def client(reglages):
    from fastapi.testclient import TestClient

    from shadowlab.site.app import creer_app

    with TestClient(creer_app(reglages), base_url="http://127.0.0.1") as c:
        yield c
