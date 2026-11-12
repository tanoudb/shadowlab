"""Option `verifier_tls` du pilote curl-cffi : fausse par défaut (Arena locale), vraie hors du labo."""

import pytest

from shadowlab.engines.curl_cffi_engine import DriverCurlCffi


def test_par_defaut_le_certificat_n_est_pas_verifie_comme_avant():
    pilote = DriverCurlCffi(("*",))
    assert pilote.configuration()["tls_non_verifie"] is True


def test_verifier_tls_est_une_option_permise_et_se_voit_dans_la_configuration():
    pilote = DriverCurlCffi(("*",), {"verifier_tls": True, "impersonate": "chrome"})
    assert pilote.configuration()["tls_non_verifie"] is False
    assert pilote.configuration()["impersonate"] == "chrome"


def test_verifier_tls_demande_un_booleen():
    with pytest.raises(ValueError, match="verifier_tls"):
        DriverCurlCffi(("*",), {"verifier_tls": "oui"})


@pytest.mark.parametrize(
    ("options", "verify"), [({}, False), ({"verifier_tls": True}, True), ({"verifier_tls": False}, False)]
)
def test_le_client_recoit_verify(monkeypatch, options, verify):
    from curl_cffi import requests

    recu = {}

    class SessionFactice:
        def __init__(self, **kwargs):
            recu.update(kwargs)

    monkeypatch.setattr(requests, "Session", SessionFactice)
    pilote = DriverCurlCffi(("*",), options)
    pilote._ouvrir_client()
    assert recu["verify"] is verify
