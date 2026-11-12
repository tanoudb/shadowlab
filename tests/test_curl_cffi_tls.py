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


def _pilote_a_redirections(options):
    from shadowlab.engines.http_base import ReponseBrute

    pilote = DriverCurlCffi(("*",), options)
    demandees = []

    def envoyer(methode, url, donnees):
        demandees.append(url)
        if url.endswith("/a"):
            return ReponseBrute(302, {"location": "http://autre.example/b", "content-type": "text/html"}, "")
        return ReponseBrute(200, {"content-type": "text/html"}, "<html>ok</html>")

    pilote._envoyer = envoyer
    pilote._url, pilote._texte, pilote._document, pilote._valeurs = "", "", None, {}
    return pilote, demandees


def test_par_defaut_les_redirections_sont_suivies_comme_avant():
    pilote, demandees = _pilote_a_redirections({})
    resultat = pilote.navigate("http://h.test/a")
    assert demandees == ["http://h.test/a", "http://autre.example/b"] and resultat.status == 200


def test_suivre_redirections_faux_rend_la_3xx_et_sa_destination_sans_la_demander():
    pilote, demandees = _pilote_a_redirections({"suivre_redirections": False})
    resultat = pilote.navigate("http://h.test/a")
    assert demandees == ["http://h.test/a"]  # l'hôte étranger n'est jamais interrogé
    assert resultat.status == 302 and pilote.location == "http://autre.example/b"
    pilote.navigate("http://h.test/c")
    assert pilote.location is None  # la destination ne traîne pas d'une page à l'autre


def test_suivre_redirections_demande_un_booleen():
    with pytest.raises(ValueError, match="suivre_redirections"):
        DriverCurlCffi(("*",), {"suivre_redirections": 0})
