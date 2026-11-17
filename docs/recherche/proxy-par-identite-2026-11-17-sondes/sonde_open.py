import os, sys, tempfile, threading
sys.path.insert(0, "tests"); sys.path.insert(0, "src")
os.environ["SHADOWLAB_IDENTITES"] = tempfile.mkdtemp()
from unittest import mock
from outils_proxy import ProxyHttpDeTest
from shadowlab.engines import registre
from shadowlab.engines.noezia import identite
with ProxyHttpDeTest("u", "p") as px:
    identite.declarer_proxy("x", px.adresse, "u", "p")
    avant = set(threading.enumerate())
    p = registre()["noezia"](("*",), {"identite": "x", "identite_native": True, "headless": False, "channel": "chrome"})
    import patchright.sync_api as api
    with mock.patch.object(api, "sync_playwright", side_effect=RuntimeError("pw indisponible")):
        try: p.open()
        except RuntimeError as e: print("open a levé :", e)
    import time; time.sleep(0.5)
    print("relais :", p._relais, "| verrou repris possible :", identite.ouvrir("x").liberer() is None, "| fils en trop :", [t.name for t in set(threading.enumerate()) - avant if t.is_alive()])
