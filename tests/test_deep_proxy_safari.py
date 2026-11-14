"""Détecteur `deep-proxy` et sa sonde : un humain sous Safari ou Firefox ne doit pas être classé « automatisé ».

Constat (14/11, deux sessions réelles : Safari 26 et 27 sur iPhone) : la sonde 1 (`testDetectionProfonde`) ne
reconnaissait que les formes de Chrome (`function get userAgent() { [native code] }`, message « Illegal invocation »).
La sonde 2 mesure la même chose sur les trois moteurs ; le détecteur ne croit un relevé de la sonde 1 que pour un
navigateur de la famille Chromium.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from test_detection import empreinte as empreinte_chrome
from test_detection import entetes_navigateur, requete
from test_rejeu import (
    COMPORTEMENT_HUMAIN,
    entetes,
    message,
    niveau,
    session_labo,
    t,
    verdict,
)
from test_rejeu import requete as requete_rejeu

from shadowlab import database as db
from shadowlab import rejeu
from shadowlab.detection import Observations, classer

OBSERVATEUR = Path(__file__).parents[1] / "src" / "shadowlab" / "site" / "static" / "observateur.js"
avec_node = pytest.mark.skipif(shutil.which("node") is None, reason="node absent")

UA_SAFARI_IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/26.0 Mobile/15E148 Safari/604.1"
)

# Relevé réel des deux sessions Safari (sonde 1, identique pour les deux).
RELEVE_SAFARI_SONDE_1 = {
    "error_has_proxy": False,
    "error_stack_lines": 3,
    "hwc_desc_match": True,
    "hwc_illegal_invoc": False,
    "hwc_natif": False,
    "navigator_constructor": True,
    "navigator_proto": True,
    "platform_desc_match": True,
    "platform_illegal_invoc": False,
    "platform_natif": False,
    "screen_w_desc_match": True,
    "screen_w_illegal_invoc": False,
    "screen_w_natif": False,
    "toString_length": 0,
    "toString_natif": True,
    "ua_desc_match": True,
    "ua_illegal_invoc": False,
    "ua_natif": False,
    "wd_desc_match": True,
    "wd_illegal_invoc": False,
    "wd_natif": False,
}
SIGNAUX_SONDE = {"getter_non_natif", "illegal_invoc_absent"}


def releve_propre(**surcharges):
    base = {
        f"{g}_{k}": True
        for g in ("hwc", "ua", "wd", "platform", "screen_w")
        for k in ("natif", "illegal_invoc", "desc_match")
    }
    base.update(navigator_proto=True, navigator_constructor=True, toString_natif=True, toString_length=0)
    base.update(error_stack_lines=3, error_has_proxy=False)
    base.update(surcharges)
    return base


def observation(releve, navigateur="chrome"):
    if navigateur == "chrome":
        e = empreinte_chrome()
        entetes_http = entetes_navigateur()
    else:  # Safari sur iPhone : ni Client Hints, ni `userAgentData`
        e = empreinte_chrome(userAgent=UA_SAFARI_IPHONE, userAgentData=None, platform="iPhone")
        entetes_http = [h for h in entetes_navigateur(UA_SAFARI_IPHONE) if not h[0].startswith("sec-ch-ua")]
    e["payload"]["deep_proxy"] = releve
    return Observations(http=[requete(entetes_http)], js=[e])


def signaux_deep_proxy(obs):
    (c,) = [c for c in classer(obs) if c.detector_name == "deep-proxy"]
    return {s.code for s in c.signals}, c


def test_version_du_detecteur():
    _, c = signaux_deep_proxy(observation(releve_propre()))
    assert c.detector_version == "1.1"


# --- Le détecteur ---------------------------------------------------------------------------------


def test_releve_safari_sonde_1_ne_donne_plus_les_deux_signaux():
    codes, c = signaux_deep_proxy(observation(RELEVE_SAFARI_SONDE_1, "safari"))
    assert not codes & SIGNAUX_SONDE
    assert c.classification == "humain"


def test_releve_safari_sonde_1_garde_les_autres_signaux():
    codes, _ = signaux_deep_proxy(observation({**RELEVE_SAFARI_SONDE_1, "toString_natif": False}, "safari"))
    assert codes == {"toString_patche"}


def test_releve_chrome_sonde_1_garde_les_deux_signaux():
    codes, c = signaux_deep_proxy(observation(RELEVE_SAFARI_SONDE_1, "chrome"))
    assert SIGNAUX_SONDE <= codes
    assert c.classification == "automatise"


def test_releve_sonde_2_non_natif_vaut_pour_tous_les_navigateurs():
    for navigateur in ("chrome", "safari"):
        releve = releve_propre(sonde=2, ua_natif=False)
        codes, _ = signaux_deep_proxy(observation(releve, navigateur))
        assert "getter_non_natif" in codes, navigateur


def test_releve_sonde_2_sans_illegal_invocation_vaut_pour_tous_les_navigateurs():
    for navigateur in ("chrome", "safari"):
        codes, _ = signaux_deep_proxy(observation(releve_propre(sonde=2, ua_illegal_invoc=False), navigateur))
        assert "illegal_invoc_absent" in codes, navigateur


def test_releve_sonde_2_propre_ne_donne_rien():
    for navigateur in ("chrome", "safari"):
        codes, c = signaux_deep_proxy(observation(releve_propre(sonde=2), navigateur))
        assert codes == set(), navigateur
        assert c.classification == "humain"


# --- La sonde, exécutée sous Node ------------------------------------------------------------------

BANC_SONDE = r"""
const fs = require('fs');
const vm = require('vm');
const P = JSON.parse(process.argv[1]);
const source = fs.readFileSync(P.fichier, 'utf8');
const corps = source.match(/function testDetectionProfonde\(\) \{[\s\S]*?\n\}\n/)[0];
const ctx = vm.createContext({});
vm.runInContext(`
  const textes = new Map();
  const vrai = Function.prototype.toString;
  Function.prototype.toString = function () { return textes.has(this) ? textes.get(this) : vrai.call(this); };
  textes.set(Function.prototype.toString, 'function toString() { [native code] }');
  function Navigator() {}
  function Screen() {}
  const navigator = new Navigator();
  function getter(texte, typeErreur, msg) {
    const g = function () {
      if (this !== navigator) {
        if (typeErreur === 'aucune') return 1;
        throw new (typeErreur === 'Error' ? Error : TypeError)(msg);
      }
      return 1;
    };
    if (texte !== null) textes.set(g, texte);
    return g;
  }
`, ctx);
ctx.P = P;
const r = vm.runInContext(`
  Object.defineProperty(Navigator.prototype, 'userAgent', {
    get: getter(P.texte, P.erreur, P.message), configurable: true,
  });
  ${corps}
  testDetectionProfonde();
`, ctx);
process.stdout.write(JSON.stringify(r));
"""


def sonde(texte, erreur="TypeError", message_erreur="x"):
    sortie = subprocess.run(
        [
            "node",
            "-e",
            BANC_SONDE,
            json.dumps({"fichier": str(OBSERVATEUR), "texte": texte, "erreur": erreur, "message": message_erreur}),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout
    return json.loads(sortie)


TEXTES_NATIFS = {
    "chrome": "function get userAgent() { [native code] }",
    "webkit_gecko": "function userAgent() {\n    [native code]\n}",
}


@avec_node
@pytest.mark.parametrize("texte", TEXTES_NATIFS.values(), ids=TEXTES_NATIFS.keys())
def test_sonde_reconnait_un_getter_natif_sur_les_trois_moteurs(texte):
    assert sonde(texte)["ua_natif"] is True


@avec_node
@pytest.mark.parametrize(
    "texte",
    [
        None,
        "function userAgent() { return 'x'; }",
        "function userAgent() {\n [native code]\n return 1;\n}",
        "function () { [native code] }",
    ],
    ids=["fonction_ordinaire", "corps_js", "native_plus_code", "sans_nom"],
)
def test_sonde_refuse_un_getter_qui_n_est_pas_natif(texte):
    assert sonde(texte)["ua_natif"] is False


@avec_node
@pytest.mark.parametrize(
    "message_erreur",
    [
        "Illegal invocation",
        "The Navigator.userAgent getter can only be used on instances of Navigator",
        "'get userAgent' called on an object that does not implement interface Navigator.",
    ],
    ids=["chrome", "webkit", "gecko"],
)
def test_sonde_reconnait_l_erreur_du_getter_quel_que_soit_le_message(message_erreur):
    assert sonde(TEXTES_NATIFS["chrome"], message_erreur=message_erreur)["ua_illegal_invoc"] is True


@avec_node
def test_sonde_refuse_un_getter_qui_ne_leve_rien_ou_pas_une_typeerror():
    assert sonde(TEXTES_NATIFS["chrome"], erreur="aucune")["ua_illegal_invoc"] is False
    assert (
        sonde(TEXTES_NATIFS["chrome"], erreur="Error", message_erreur="Illegal invocation")["ua_illegal_invoc"] is False
    )


@avec_node
def test_sonde_porte_son_numero_de_version():
    assert sonde(TEXTES_NATIFS["chrome"])["sonde"] == 2


# --- Le rejeu -------------------------------------------------------------------------------------


def test_rejeu_session_humaine_safari_n_est_plus_arretee_par_deep_proxy(tmp_path):
    cx = db.ouvrir(tmp_path / "labo.sqlite3")
    jeton = session_labo(cx)
    e = empreinte_chrome()["payload"]
    e["navigateur"] = {
        **e["navigateur"],
        "userAgent": UA_SAFARI_IPHONE,
        "userAgentData": None,
        "platform": "iPhone",
    }
    e["deep_proxy"] = RELEVE_SAFARI_SONDE_1
    sans_hints = [h for h in entetes() if not h[0].startswith("sec-ch-ua")]
    sans_hints = [["user-agent", UA_SAFARI_IPHONE] if h[0] == "user-agent" else h for h in sans_hints]
    requete_rejeu(cx, jeton, t(0), "/lab/vitrine", cookies=(), en_tetes=sans_hints)
    requete_rejeu(cx, jeton, t(0.2), "/lab/static/observateur.js", en_tetes=sans_hints)
    message(cx, jeton, t(1), e)
    message(cx, jeton, t(10), COMPORTEMENT_HUMAIN, kind="comportement")
    requete_rejeu(cx, jeton, t(11), "/lab/vitrine/annonces", en_tetes=sans_hints)
    resultat = rejeu.rejouer(cx)
    for code in ("04", "05", "06", "07"):
        detecteurs = {m["detecteur"] for m in verdict(resultat, jeton, code)["motifs"]}
        assert "deep-proxy" not in detecteurs, code
    assert niveau(resultat, "04")["arretees"] == 0
