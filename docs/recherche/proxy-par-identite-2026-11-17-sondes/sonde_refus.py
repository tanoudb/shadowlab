"""Sonde jetable (hors dépôt) : ce que Chrome montre quand le relais refuse, et réutilisation de connexion."""
import os, sys, tempfile, time
sys.path.insert(0, "tests"); sys.path.insert(0, "src")
os.environ["SHADOWLAB_IDENTITES"] = tempfile.mkdtemp()
from outils_proxy import CibleDeTest, ProxyHttpDeTest, ProxySocks5DeTest
from shadowlab.engines import registre
from shadowlab.engines.noezia.identite import declarer_proxy

def pilote(hotes, nom):
    return registre()["noezia"](hotes, {"identite": nom, "identite_native": True, "headless": False, "channel": "chrome", "interaction_post_page": False})

def aller(p, url):
    try:
        r = p.navigate(url)
        return ("statut", r.status, (p.dom() or "")[:120].replace("\n", " "))
    except Exception as e:
        return ("exception", type(e).__name__, str(e).splitlines()[0][:160])

with CibleDeTest() as cible2, CibleDeTest(delai_xhr_s=0.3, cible2=cible2) as cible, ProxyHttpDeTest("u", "bon", nom="H") as ph, ProxySocks5DeTest("u", "bon", nom="S") as ps:
    for schema, px in (("http", ph), ("socks5", ps)):
        # 1. mauvais mot de passe
        # 2. périmètre strict
        declarer_proxy(f"strict-{schema}", px.adresse, "u", "bon")
        p = pilote(("127.0.0.1",), f"strict-{schema}"); p.open(); p.start_session()
        print(f"[{schema}] strict, redirection hors périmètre :", aller(p, cible.url("/redirige-dehors")))
        print(f"[{schema}] strict, GET direct localhost (Playwright route) :", aller(p, f"http://localhost:{cible2.port}/"))
        print(f"[{schema}] demandes localhost/127 :", [tuple(d) for d in p._relais.demandes if d[1] in ('localhost','127.0.0.1')])
        p.close_session(); p.close()
        # 3. réutilisation de connexion : requêtes reçues par la cible, ports sources, demandes transmises
        declarer_proxy(f"ok-{schema}", px.adresse, "u", "bon")
        avant = len(cible.requetes)
        p = pilote(("*",), f"ok-{schema}"); p.open(); p.start_session()
        for i in range(3):
            aller(p, cible.url(f"/page?id=R{i}")); p.wait_for_element("#fini", 10000)
        time.sleep(0.5)
        demandes = [tuple(d) for d in p._relais.demandes]
        reqs = cible.requetes[avant:]
        gets = [d for d in demandes if d[0] != "CONNECT" and d[3] == "transmise" and d[1] == "127.0.0.1" and d[2] == cible.port]
        print(f"[{schema}] requêtes reçues par la cible : {len(reqs)} ; demandes transmises (hors CONNECT) : {len(gets)} ; toutes décisions : {sorted({d[3] for d in demandes})}")
        print(f"[{schema}] ports sources distincts vus par la cible : {len({r['port_source'] for r in reqs})}")
        p.close_session(); p.close()
