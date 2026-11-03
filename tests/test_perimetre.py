import socket

import pytest

from shadowlab.perimetre import DestinationRefusee, est_autorisee, verifier_url

AUTORISES = ("127.0.0.1", "localhost", "::1")


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:8770/lab/", "http://localhost/x", "https://127.0.0.1/", "http://[::1]:8770/"],
)
def test_destinations_locales_acceptees(url):
    assert verifier_url(url, AUTORISES) == url


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "file:///etc/passwd",
        "ftp://127.0.0.1/",
        "http://user:mdp@127.0.0.1/",
        "http://127.0.0.1.example.com/",
        "javascript:alert(1)",
        "",
    ],
)
def test_destinations_refusees_par_defaut(url):
    with pytest.raises(DestinationRefusee):
        verifier_url(url, AUTORISES)


def test_nom_autorise_qui_resout_vers_un_reseau_interne_est_refuse(monkeypatch):
    def faux_getaddrinfo(hote, port, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.0.12", port))]

    monkeypatch.setattr(socket, "getaddrinfo", faux_getaddrinfo)
    with pytest.raises(DestinationRefusee, match="réseau interne"):
        verifier_url("http://lab.test/", ("lab.test",))


def test_nom_autorise_qui_resout_en_local_est_accepte(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda hote, port, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))],
    )
    assert est_autorisee("http://lab.test/", ("lab.test",))
