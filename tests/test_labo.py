"""Service de l'interface du laboratoire sous /labo (ignoré si le front n'est pas construit)."""

from __future__ import annotations

import pytest

from shadowlab.labo import DIST

pytestmark = pytest.mark.skipif(
    not (DIST / "index.html").is_file(),
    reason="front non construit : `npm --prefix frontend run build`",
)


def test_labo_sert_l_interface(client):
    r = client.get("/labo")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert '<div id="root">' in r.text


def test_labo_repli_spa_sur_chemin_inconnu(client):
    # React Router gère le routage côté client : tout chemin inconnu renvoie l'index.
    r = client.get("/labo/experiences/42")
    assert r.status_code == 200
    assert '<div id="root">' in r.text
