"""Tests pour analytics.comparer(), Fisher exact et Holm-Bonferroni."""

from __future__ import annotations

import pytest

from shadowlab import database as db
from shadowlab.analytics import _fisher_exact_p, _holm_bonferroni, comparer


@pytest.fixture
def cx(tmp_path):
    """Base avec deux expériences à comparer."""
    base = tmp_path / "test.sqlite3"
    cx = db.ouvrir(base)
    cx.execute(
        "INSERT INTO experiments (id, name, description, created_at, configuration, status, seed)"
        " VALUES (1, 'ref', 'reference', '2026-01-01T00:00:00', '{}', 'termine', 1)"
    )
    cx.execute(
        "INSERT INTO experiments (id, name, description, created_at, configuration, status, seed)"
        " VALUES (2, 'nouveau', 'nouveau', '2026-01-01T00:00:00', '{}', 'termine', 2)"
    )
    cx.execute(
        "INSERT INTO engines (id, name, version, runtime, configuration) VALUES (1, 'httpx', '{}', 'python', '{}')"
    )
    cx.execute(
        "INSERT INTO engines (id, name, version, runtime, configuration)"
        " VALUES (2, 'playwright', '{}', 'chromium', '{}')"
    )
    cx.execute("INSERT INTO scenarios (id, name) VALUES (1, 'static_html')")

    # httpx : 5/10 dans ref, 8/10 dans nouveau (amélioration)
    for i in range(1, 11):
        success = 1 if i <= 5 else 0
        _run(cx, i, exp=1, eng=1, success=success)
    for i in range(11, 21):
        success = 1 if i <= 18 else 0
        _run(cx, i, exp=2, eng=1, success=success)

    # playwright : 9/10 dans ref, 2/10 dans nouveau (régression)
    for i in range(21, 31):
        success = 1 if i <= 29 else 0
        _run(cx, i, exp=1, eng=2, success=success)
    for i in range(31, 41):
        success = 1 if i <= 32 else 0
        _run(cx, i, exp=2, eng=2, success=success)

    return cx


def _run(cx, run_id, *, exp, eng, success):
    status = "reussi" if success else "erreur"
    issue = "extraction_reussie" if success else "bloque"
    cx.execute(
        "INSERT INTO runs (id, experiment_id, engine_id, scenario_id, repetition,"
        " session_token, truth, started_at, status, success, duration_ms, issue)"
        " VALUES (?, ?, ?, 1, 1, ?, 'automatise', '2026-01-01T00:00:00', ?, ?, ?, ?)",
        (run_id, exp, eng, f"tok-{run_id}", status, success, run_id * 10.0, issue),
    )


class TestFisherExact:
    def test_table_identique(self):
        p = _fisher_exact_p(5, 5, 5, 5)
        assert p == pytest.approx(1.0, abs=0.01)

    def test_table_extreme(self):
        p = _fisher_exact_p(10, 0, 0, 10)
        assert p < 0.001

    def test_symetrie(self):
        p1 = _fisher_exact_p(3, 7, 8, 2)
        p2 = _fisher_exact_p(8, 2, 3, 7)
        assert p1 == pytest.approx(p2, abs=1e-10)


class TestHolmBonferroni:
    def test_liste_vide(self):
        assert _holm_bonferroni([]) == []

    def test_un_seul(self):
        assert _holm_bonferroni([0.03]) == [0.03]

    def test_correction_croissante(self):
        brutes = [0.01, 0.04, 0.03]
        corrigees = _holm_bonferroni(brutes)
        assert all(c >= b for c, b in zip(corrigees, brutes, strict=True))
        assert all(c <= 1.0 for c in corrigees)

    def test_plus_petit_multiplie_par_m(self):
        brutes = [0.01, 0.04, 0.03]
        corrigees = _holm_bonferroni(brutes)
        assert corrigees[0] == pytest.approx(0.03, abs=1e-10)


class TestComparer:
    def test_structure(self, cx):
        result = comparer(cx, 1, 2)
        assert "reference" in result
        assert "nouveau" in result
        assert "moteurs" in result
        assert result["reference"]["id"] == 1
        assert result["nouveau"]["id"] == 2

    def test_moteurs_communs(self, cx):
        result = comparer(cx, 1, 2)
        labels = {m["label"] for m in result["moteurs"] if not m.get("only_in")}
        assert "httpx" in labels
        assert "playwright" in labels

    def test_deltas_reussite(self, cx):
        result = comparer(cx, 1, 2)
        httpx = next(m for m in result["moteurs"] if m["label"] == "httpx")
        d = httpx["deltas"]["reussite"]
        assert d["delta"] > 0  # amélioration

    def test_p_value_corrigee(self, cx):
        result = comparer(cx, 1, 2)
        for m in result["moteurs"]:
            if m.get("only_in"):
                continue
            d = m["deltas"]["reussite"]
            assert "p_value" in d
            assert "p_value_corrigee" in d
            assert "significatif" in d

    def test_experience_introuvable(self, cx):
        with pytest.raises(LookupError):
            comparer(cx, 1, 999)


class TestComparerDisjoint:
    """Moteur présent dans une seule expérience."""

    def test_only_in(self, tmp_path):
        base = tmp_path / "test2.sqlite3"
        cx = db.ouvrir(base)
        cx.execute(
            "INSERT INTO experiments (id, name, description, created_at, configuration, status, seed)"
            " VALUES (1, 'a', '', '2026-01-01', '{}', 'termine', 1)"
        )
        cx.execute(
            "INSERT INTO experiments (id, name, description, created_at, configuration, status, seed)"
            " VALUES (2, 'b', '', '2026-01-01', '{}', 'termine', 2)"
        )
        cx.execute(
            "INSERT INTO engines (id, name, version, runtime, configuration) VALUES (1, 'httpx', '{}', 'python', '{}')"
        )
        cx.execute(
            "INSERT INTO engines (id, name, version, runtime, configuration) VALUES (2, 'curl', '{}', 'python', '{}')"
        )
        cx.execute("INSERT INTO scenarios (id, name) VALUES (1, 'static_html')")
        _run(cx, 1, exp=1, eng=1, success=1)
        _run(cx, 2, exp=2, eng=2, success=1)
        result = comparer(cx, 1, 2)
        only = [m for m in result["moteurs"] if m.get("only_in")]
        assert len(only) == 2
