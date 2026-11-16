"""Palier 2, I7 : espacement des visites d'un bras, un monde par bras, `bannir_avant_visite`, visites par entrée.

Horloge et sommeil injectables : aucune attente réelle. La campagne tourne ici avec un pilote factice (aucun navigateur,
aucune Arena) ; le passage est remplacé par une fonction qui note ce qu'il reçoit.
"""

# ruff: noqa: E501  (requêtes SQL et configurations YAML en ligne)
from __future__ import annotations

import json
import random
import threading
import time
from datetime import datetime, timedelta

import pytest
from test_campagnes import ecrire

from shadowlab import campaigns, espacement
from shadowlab import database as db
from shadowlab.arena import bannissements
from shadowlab.campaigns import lire
from shadowlab.engines.noezia import visites
from shadowlab.scenarios import SCENARIOS

DEPART = datetime(2026, 11, 16, 20, 0, 0)


@pytest.fixture(autouse=True)
def infrastructure_saine(monkeypatch):
    """Ni Arena ni site dans ces tests : la sonde d'avant visite (I9) les dit joignables."""
    monkeypatch.setattr(campaigns, "_panne_infrastructure", lambda reglages, protection: None, raising=False)


class Horloge:
    """Horloge factice : `dormir` fait avancer le temps sans attendre."""

    def __init__(self, depart: datetime = DEPART):
        self.t = depart
        self.pauses: list[float] = []

    def now(self) -> datetime:
        return self.t

    def dormir(self, secondes: float) -> None:
        self.pauses.append(secondes)
        self.t += timedelta(seconds=secondes)

    def avancer(self, secondes: float) -> None:
        self.t += timedelta(seconds=secondes)


# ── La cadence ─────────────────────────────────────────────────────────────────────────────────


def cadence(horloge, mode="fixe", **champs):
    reglage = espacement.Espacement(mode=mode, **champs)
    return espacement.Cadence(reglage, horloge=horloge.now, dormir=horloge.dormir, graine=3)


def test_fixe_la_premiere_visite_part_tout_de_suite():
    horloge = Horloge()
    creneau = cadence(horloge, minutes=10).attendre()
    assert creneau is not None and horloge.pauses == [] and creneau.pages is None


def test_fixe_compte_l_ecart_de_la_fin_d_une_visite_au_debut_de_la_suivante():
    horloge = Horloge()
    c = cadence(horloge, minutes=10)
    premier = c.attendre()
    horloge.avancer(120)  # la visite dure 2 minutes
    c.terminer(premier, 15)
    fin = horloge.now()
    c.attendre()
    assert horloge.now() == fin + timedelta(minutes=10)
    assert sum(horloge.pauses) == pytest.approx(600)


def test_fixe_dort_par_tranches_pour_que_l_arret_reste_ecoute():
    horloge = Horloge()
    c = cadence(horloge, minutes=10)
    c.terminer(c.attendre(), 3)
    c.attendre()
    assert len(horloge.pauses) > 100 and max(horloge.pauses) <= espacement.PAS_S  # jamais plus de quelques secondes


def test_l_arret_interrompt_l_attente():
    horloge = Horloge()
    c = cadence(horloge, minutes=10)
    c.terminer(c.attendre(), 3)
    appels = []
    resultat = c.attendre(interrompre=lambda: appels.append(1) or len(appels) > 3)
    assert resultat is None and sum(horloge.pauses) < 60


def test_ordonnanceur_est_celui_de_visites_py():
    """`mode: ordonnanceur` appelle l'ordonnanceur de l'étape I5 : mêmes visites, avec la même graine."""
    horloge = Horloge()
    c = cadence(horloge, mode="ordonnanceur")
    # une graine par visite : la graine du bras, puis le nombre de visites faites et de notes (créneau recalculable)
    ordonnanceur = visites.Ordonnanceur(alea=random.Random("3:0:0"), horloge=horloge.now, dormir=horloge.dormir)
    attendu = ordonnanceur.prochaine()
    creneau = c.attendre()
    assert (creneau.debut, creneau.pages) == (attendu.debut, attendu.pages)
    assert 5 <= creneau.pages <= 40 and horloge.now() >= attendu.debut
    # la fin de visite est transmise : le prochain écart se compte depuis elle (45 min au moins)
    horloge.avancer(300)
    c.terminer(creneau, creneau.pages)
    suivant = c.attendre()
    assert suivant.debut - horloge.now() <= timedelta(0) and suivant.debut >= creneau.debut + timedelta(minutes=50)


def test_ordonnanceur_accepte_des_reglages_de_visites_py():
    horloge = Horloge()
    c = cadence(horloge, mode="ordonnanceur", reglages={"pages_min": 5, "pages_med": 6, "pages_max": 7})
    assert 5 <= c.attendre().pages <= 7


@pytest.mark.parametrize(
    "champs",
    [
        {"mode": "fixe"},  # il manque les minutes
        {"mode": "fixe", "minutes": 0},
        {"mode": "ordonnanceur", "minutes": 10},  # les minutes sont celles de `fixe`
        {"mode": "ordonnanceur", "reglages": {"inconnu": 1}},
        {"mode": "ordonnanceur", "reglages": {"plage": [23, 8]}},
        {"mode": "autre", "minutes": 1},
    ],
)
def test_espacement_invalide_refuse(champs):
    with pytest.raises(ValueError):
        espacement.Espacement(**champs)


# ── Validation de la campagne ──────────────────────────────────────────────────────────────────

BRAS = """
    - name: noezia
      label: sujet
      options: {headless: false, channel: chrome, identite_native: true, identite: soiree-sujet}
    - name: noezia
      label: temoin-negatif
      options: {headless: false, channel: chrome, identite_native: true}
    - name: noezia
      label: temoin-sentinelle
      visites: 6
      bannir_avant_visite: 3
      options: {headless: false, channel: chrome, identite_native: true, identite: soiree-sentinelle}
    - name: playwright
      label: temoin-classique
      visites: 4
"""


def campagne(tmp_path, reglages, *, engines=BRAS, extra="  espacement: {mode: fixe, minutes: 10}\n  concurrency: 4\n"):
    return lire(
        ecrire(
            tmp_path,
            f"""
experiment:
  name: soiree
  engines:{engines}
  protections: [endurance]
  scenarios: [visite]
  repetitions: 24
  seed: 1
  monde: serie
{extra}""",
        ),
        reglages,
    )


def test_campagne_de_la_soiree_valide(tmp_path, reglages):
    e = campagne(tmp_path, reglages)
    assert e.espacement.mode == "fixe" and e.pages_par_visite == 15
    assert [m.visites for m in e.engines] == [None, None, 6, 4]
    assert e.total_passages() == 24 + 24 + 6 + 4


def test_n_pages_par_visite_se_regle(tmp_path, reglages):
    e = campagne(
        tmp_path, reglages, extra="  pages_par_visite: 3\n  espacement: {mode: fixe, minutes: 1}\n  concurrency: 4\n"
    )
    assert e.pages_par_visite == 3


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ("  espacement: {mode: fixe, minutes: 10}\n  concurrency: 2\n", "concurrency"),  # les bras seraient en série
        ("  espacement: {mode: fixe, minutes: 10}\n", "concurrency"),
        ("  pages_par_visite: 0\n", "pages_par_visite"),
    ],
)
def test_espacement_exige_tous_les_bras_en_parallele(tmp_path, reglages, extra, message):
    with pytest.raises(ValueError, match=message):
        campagne(tmp_path, reglages, extra=extra)


def test_espacement_exige_le_scenario_visite(tmp_path, reglages):
    texte = ecrire(
        tmp_path,
        """
experiment:
  name: soiree
  engines: [playwright]
  scenarios: [static_html]
  repetitions: 2
  espacement: {mode: fixe, minutes: 1}
""",
    )
    with pytest.raises(ValueError, match="visite"):
        lire(texte, reglages)


@pytest.mark.parametrize(
    "bras",
    [
        # sans identité
        "    - {name: noezia, bannir_avant_visite: 3, options: {headless: false, channel: chrome, identite_native: true}}\n",
        # visite voulue au-delà des visites prévues
        "    - {name: noezia, visites: 2, bannir_avant_visite: 3, options: {headless: false, channel: chrome, identite_native: true, identite: x}}\n",
    ],
)
def test_bannir_avant_visite_est_reserve_a_une_identite_et_a_une_visite_prevue(tmp_path, reglages, bras):
    with pytest.raises(ValueError, match="bannir_avant_visite"):
        campagne(tmp_path, reglages, engines="\n" + bras, extra="")


def test_bannir_avant_visite_exige_un_monde_par_serie(tmp_path, reglages):
    texte = ecrire(
        tmp_path,
        """
experiment:
  name: soiree
  engines:
    - {name: noezia, bannir_avant_visite: 2, options: {headless: false, channel: chrome, identite_native: true, identite: x}}
  scenarios: [visite]
  repetitions: 3
  monde: passage
""",
    )
    with pytest.raises(ValueError, match="monde"):
        lire(texte, reglages)


def test_sans_les_nouveaux_champs_une_campagne_est_inchangee(tmp_path, reglages):
    e = lire(
        ecrire(
            tmp_path,
            "experiment:\n  name: ancienne\n  engines: [playwright]\n  scenarios: [static_html]\n  repetitions: 3\n",
        ),
        reglages,
    )
    assert e.espacement is None and e.engines[0].visites is None and e.engines[0].bannir_avant_visite is None
    assert e.total_passages() == 3


# ── Exécution d'une unité : un monde par bras, espacement, bannissement ───────────────────────────


def faux_pilote():
    from shadowlab.engines import registre

    class PiloteFactice(registre()["httpx"]):
        @classmethod
        def controler_options(cls, options):  # les options de la campagne (identité…) sont celles du vrai moteur
            pass

        def __init__(self, hotes, options=None):
            super().__init__(hotes, {})

        def open(self):
            pass

        def close(self):
            pass

        def versions(self):
            return {}

    return PiloteFactice


class Passages:
    """Remplace `campaigns._passage` : note ce qu'il reçoit, quand, et ce que la base contenait à cet instant."""

    def __init__(self, reglages, horloge=None, ecrire_visite=None):
        self.reglages = reglages
        self.horloge = horloge
        self.ecrire_visite = ecrire_visite
        self.appels: list[dict] = []

    def __call__(self, cx, reglages, experience, experiment_id, pilote, engine_id, scenario, scenario_id, repetition,
                 protection, base, rng, dossier_artefacts, engine_version="", monde=None):  # fmt: skip
        ligne = cx.execute("SELECT COUNT(*) FROM bannissements").fetchone()[0]
        self.appels.append(
            {
                "repetition": repetition,
                "monde": monde,
                "scenario": scenario,
                "quand": self.horloge.now() if self.horloge else None,
                "bannissements": ligne,
            }
        )
        if self.ecrire_visite:
            self.ecrire_visite(cx, monde, repetition)
        cx.execute(
            "INSERT INTO runs (experiment_id, engine_id, scenario_id, repetition, session_token, truth, started_at,"
            " status, success, protection) VALUES (?, ?, ?, ?, ?, 'automatise', '2026-11-16', 'reussi', 1, ?)",
            (
                experiment_id,
                engine_id,
                scenario_id,
                repetition,
                f"t-{engine_id}-{scenario_id}-{repetition}",
                protection,
            ),
        )
        return {"pages_faites": 15}


def preparer(tmp_path, reglages, monkeypatch, extra, engines=BRAS):
    experience = campagne(tmp_path, reglages, engines=engines, extra=extra)
    cx = db.ouvrir(reglages.base_donnees)
    experiment_id = campaigns.creer(cx, experience, reglages)
    pilote = faux_pilote()
    monkeypatch.setattr(campaigns, "registre", lambda: {"noezia": pilote, "playwright": pilote})
    return experience, cx, experiment_id


def rang_de(experience, label):
    return [m.nom_affiche for m, _ in campaigns.unites(experience)].index(label)


def test_chaque_bras_a_son_monde_meme_deux_entrees_noezia(tmp_path, reglages, monkeypatch):
    """`monde: serie` nomme le monde par LIBELLÉ du bras, pas par nom de moteur : deux `noezia` ont deux mondes."""
    experience, cx, experiment_id = preparer(tmp_path, reglages, monkeypatch, extra="")
    mondes = {}
    for label in ("sujet", "temoin-negatif", "temoin-sentinelle", "temoin-classique"):
        passages = Passages(reglages, ecrire_visite=visite_du_visiteur)
        monkeypatch.setattr(campaigns, "_passage", passages)
        assert campaigns.executer_unite(reglages, experiment_id, rang_de(experience, label)) == "termine"
        assert len({a["monde"] for a in passages.appels}) == 1  # un seul monde pour toutes les visites du bras
        mondes[label] = passages.appels[0]["monde"]
    assert mondes["sujet"] == f"c{experiment_id}:sujet:endurance"
    assert mondes["temoin-negatif"] == f"c{experiment_id}:temoin-negatif:endurance"
    assert len(set(mondes.values())) == 4


def test_les_visites_par_entree_remplacent_les_repetitions(tmp_path, reglages, monkeypatch):
    experience, cx, experiment_id = preparer(tmp_path, reglages, monkeypatch, extra="")
    experience = experience.model_copy(update={"repetitions": 5})
    plan = {m.nom_affiche: len(list(campaigns._plan(experience, m, "endurance"))) for m in experience.engines}
    assert plan == {"sujet": 5, "temoin-negatif": 5, "temoin-sentinelle": 6, "temoin-classique": 4}


def test_sans_espacement_la_campagne_tourne_comme_avant(tmp_path, reglages, monkeypatch):
    """Sans le champ : aucune cadence construite, aucun sommeil, le scénario est celui du registre, pas de bannissement."""
    experience = lire(
        ecrire(
            tmp_path,
            "experiment:\n  name: ancienne\n  engines: [playwright]\n  scenarios: [static_html, api_json]\n"
            "  repetitions: 3\n  seed: 1\n",
        ),
        reglages,
    )
    cx = db.ouvrir(reglages.base_donnees)
    experiment_id = campaigns.creer(cx, experience, reglages)
    monkeypatch.setattr(campaigns, "registre", lambda: {"playwright": faux_pilote()})

    def interdit(*_, **__):
        raise AssertionError("aucune cadence sans le champ `espacement`")

    monkeypatch.setattr(espacement, "Cadence", interdit)
    monkeypatch.setattr(time, "sleep", interdit)
    monkeypatch.setattr(bannissements, "bannir_visiteur_connu", interdit)
    passages = Passages(reglages)
    monkeypatch.setattr(campaigns, "_passage", passages)
    assert campaigns.executer_unite(reglages, experiment_id, 0) == "termine"
    assert sorted(a["repetition"] for a in passages.appels) == [1, 1, 2, 2, 3, 3]
    assert all(a["scenario"] is SCENARIOS[a["scenario"].name] for a in passages.appels)  # pas de scénario refait


def test_l_espacement_fixe_est_applique_entre_deux_visites_d_un_bras(tmp_path, reglages, monkeypatch):
    experience, cx, experiment_id = preparer(
        tmp_path, reglages, monkeypatch, extra="  espacement: {mode: fixe, minutes: 10}\n  concurrency: 4\n"
    )
    horloge = Horloge()
    passages = Passages(reglages, horloge)
    monkeypatch.setattr(campaigns, "_passage", passages)
    rang = rang_de(experience, "temoin-classique")
    assert (
        campaigns.executer_unite(reglages, experiment_id, rang, horloge=horloge.now, dormir=horloge.dormir) == "termine"
    )
    debuts = [a["quand"] for a in passages.appels]
    assert len(debuts) == 4
    assert [(b - a).total_seconds() for a, b in zip(debuts, debuts[1:], strict=False)] == [600, 600, 600]


def test_chaque_bras_a_son_rythme_et_ils_tournent_en_parallele(tmp_path, reglages, monkeypatch):
    """Deux bras en même temps (fils), chacun à son écart : les visites de l'un tombent entre celles de l'autre."""
    experience, cx, experiment_id = preparer(
        tmp_path, reglages, monkeypatch, extra="  espacement: {mode: fixe, minutes: 0.005}\n  concurrency: 4\n"
    )
    verrou = threading.Lock()
    passages = []

    def passage(cx, reglages, experience, experiment_id, pilote, engine_id, scenario, scenario_id, repetition,
                protection, base, rng, dossier_artefacts, engine_version="", monde=None):  # fmt: skip
        with verrou:
            passages.append((monde, repetition, time.monotonic()))
        return {"pages_faites": 1}

    monkeypatch.setattr(campaigns, "_passage", passage)
    fils = [
        threading.Thread(target=campaigns.executer_unite, args=(reglages, experiment_id, rang_de(experience, label)))
        for label in ("temoin-classique", "temoin-sentinelle")
    ]
    debut = time.monotonic()
    [f.start() for f in fils]
    [f.join(60) for f in fils]
    duree = time.monotonic() - debut
    par_bras = {}
    for monde, _, quand in passages:
        par_bras.setdefault(monde, []).append(quand)
    assert len(par_bras) == 2
    # chaque bras est espacé (0,3 s entre deux visites)...
    for quand in par_bras.values():
        assert all(b - a >= 0.25 for a, b in zip(sorted(quand), sorted(quand)[1:], strict=False))
    # ... et l'un ne attend pas l'autre : le plus court finit avant la fin de l'autre, les deux ont démarré ensemble
    premiers = sorted(min(q) for q in par_bras.values())
    assert premiers[1] - premiers[0] < 0.25
    assert duree < 0.3 * (4 + 6) * 0.8  # bien moins que les deux bras l'un après l'autre


def visite_du_visiteur(cx, monde, repetition):
    """Ce que fait l'Arena à une visite : une ligne `visites` (monde, visiteur) pour la session."""
    from shadowlab.arena import visiteurs

    cx.execute(
        "INSERT INTO visites (monde_id, visiteur, session_token, neuve, vue_le) VALUES (?, 'v1', ?, ?, ?)",
        (visiteurs.identifiant_monde(cx, monde), f"s-{monde}-{repetition}", int(repetition == 1), db.maintenant()),
    )


def test_bannir_avant_visite_ecrit_la_ligne_avant_la_visite_voulue_dans_le_monde_du_bras(
    tmp_path, reglages, monkeypatch
):
    experience, cx, experiment_id = preparer(
        tmp_path, reglages, monkeypatch, extra="  espacement: {mode: fixe, minutes: 1}\n  concurrency: 4\n"
    )
    horloge = Horloge()
    passages = Passages(reglages, horloge, ecrire_visite=visite_du_visiteur)
    monkeypatch.setattr(campaigns, "_passage", passages)
    rang = rang_de(experience, "temoin-sentinelle")
    assert (
        campaigns.executer_unite(reglages, experiment_id, rang, horloge=horloge.now, dormir=horloge.dormir) == "termine"
    )
    # la base contenait 0 bannissement aux visites 1 et 2, 1 à partir de la 3e
    assert [a["bannissements"] for a in passages.appels] == [0, 0, 1, 1, 1, 1]
    monde = f"c{experiment_id}:temoin-sentinelle:endurance"
    lignes = cx.execute(
        "SELECT b.visiteur, b.motif FROM bannissements b JOIN mondes m ON m.id = b.monde_id WHERE m.nom = ?", (monde,)
    ).fetchall()
    assert [(x["visiteur"], x["motif"]) for x in lignes] == [("v1", "manuel")]  # le même code que `arena bannir`
    assert cx.execute("SELECT COUNT(*) FROM bannissements").fetchone()[0] == 1  # aucun autre monde touché


def test_bannir_sans_visiteur_connu_arrete_le_bras_sans_le_cacher(tmp_path, reglages, monkeypatch):
    experience, cx, experiment_id = preparer(
        tmp_path, reglages, monkeypatch, extra="  espacement: {mode: fixe, minutes: 1}\n  concurrency: 4\n"
    )
    horloge = Horloge()
    passages = Passages(reglages, horloge)  # aucune ligne `visites` écrite : l'Arena n'a vu personne
    monkeypatch.setattr(campaigns, "_passage", passages)
    rang = rang_de(experience, "temoin-sentinelle")
    assert (
        campaigns.executer_unite(reglages, experiment_id, rang, horloge=horloge.now, dormir=horloge.dormir)
        == "interrompu"
    )
    assert [a["repetition"] for a in passages.appels] == [1, 2]  # la 3e visite n'a pas eu lieu
    assert cx.execute("SELECT COUNT(*) FROM bannissements").fetchone()[0] == 0


# ── Le code commun de `arena bannir` ───────────────────────────────────────────────────────────


def test_bannir_visiteur_connu_refuse_un_monde_ou_un_visiteur_inconnu(reglages):
    cx = db.ouvrir(reglages.base_donnees)
    with pytest.raises(bannissements.BannissementRefuse, match="monde inconnu"):
        bannissements.bannir_visiteur_connu(cx, "nulle-part", "v1")
    visite_du_visiteur(cx, "m", 1)
    with pytest.raises(bannissements.BannissementRefuse, match="visiteur inconnu"):
        bannissements.bannir_visiteur_connu(cx, "m", "v2")
    assert bannissements.bannir_visiteur_connu(cx, "m", "v1") is True
    assert bannissements.bannir_visiteur_connu(cx, "m", "v1") is False  # déjà banni
    assert bannissements.dernier_visiteur(cx, "m") == "v1" and bannissements.dernier_visiteur(cx, "autre") is None


# ── Une identité refusée avant la visite est un résultat, pas une panne ───────────────────────


def test_une_identite_refusee_est_un_resultat_du_passage_et_non_une_panne(tmp_path, reglages, monkeypatch):
    from shadowlab.engines.noezia.identite import IdentiteRefusee

    experience, cx, experiment_id = preparer(tmp_path, reglages, monkeypatch, extra="")
    base = faux_pilote()

    class IdentiteBannie(base):
        def start_session(self):
            raise IdentiteRefusee("identité 'x' bannie : elle ne sert plus jamais")

    pilote = IdentiteBannie(reglages.hotes_autorises, {})
    moteur = db.engine_id(cx, "noezia", "{}", "navigateur", {"label": "temoin-sentinelle"})
    scenario = db.scenario_id(cx, "visite", "visite")
    details = campaigns._passage(
        cx, reglages, experience, experiment_id, pilote, moteur, SCENARIOS["visite"], scenario, 4, "endurance",
        reglages.url_arena, random.Random(1), tmp_path / "artefacts", monde="m",
    )  # fmt: skip
    assert details["pages_faites"] == 0 and "bannie" in details["identite_refusee"]
    run = cx.execute("SELECT status, success, issue FROM runs WHERE experiment_id = ?", (experiment_id,)).fetchone()
    assert (run["status"], run["success"]) == ("echec", 0)  # pas `erreur` : ce n'est pas une panne du moteur
    assert run["issue"] != "erreur_technique"
    drapeaux = json.loads(cx.execute("SELECT drapeaux FROM runs").fetchone()[0])
    assert "identite_refusee" in drapeaux["details_scenario"] and drapeaux["erreur_technique"] is False
