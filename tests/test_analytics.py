import pytest

from shadowlab.analytics import quantile, wilson


def test_wilson_valeurs_connues():
    assert wilson(0, 0) is None
    ic = wilson(5, 10)
    assert ic["taux"] == 0.5
    assert ic["bas"] == pytest.approx(0.2366, abs=1e-4)
    assert ic["haut"] == pytest.approx(0.7634, abs=1e-4)
    tout = wilson(20, 20)
    assert tout["haut"] == 1.0 and tout["bas"] == pytest.approx(0.8389, abs=1e-4)


def test_quantile_interpolation_lineaire():
    valeurs = [1.0, 2.0, 3.0, 4.0, 100.0]
    assert quantile(valeurs, 0.5) == 3.0
    assert quantile(valeurs, 0.95) == pytest.approx(80.8, abs=0.1)
    assert quantile([], 0.5) is None


def test_statistiques_par_protection(tmp_path):
    from shadowlab import database as db
    from shadowlab.analytics import statistiques

    base = tmp_path / "test.sqlite3"
    cx = db.ouvrir(base)
    cx.execute(
        "INSERT INTO experiments (id, name, description, created_at, configuration, status, seed)"
        " VALUES (1, 't', '', '2026-01-01', '{}', 'termine', 1)"
    )
    cx.execute(
        "INSERT INTO engines (id, name, version, runtime, configuration) VALUES (1, 'httpx', '{}', 'python', '{}')"
    )
    cx.execute("INSERT INTO scenarios (id, name) VALUES (1, 'static_html')")
    for i in range(1, 4):
        cx.execute(
            "INSERT INTO runs (id, experiment_id, engine_id, scenario_id, repetition,"
            " session_token, truth, started_at, status, success, duration_ms, protection, issue)"
            " VALUES (?, 1, 1, 1, 1, ?, 'automatise', '2026-01-01', 'reussi', 1, 100, ?, 'extraction_reussie')",
            (i, f"t-{i}", f"0{i}"),
        )
    stats = statistiques(cx, 1)
    assert "par_protection" in stats
    prots = {p["protection"] for p in stats["par_protection"]}
    assert prots == {"01", "02", "03"}


def test_statistiques_par_issue(tmp_path):
    from shadowlab import database as db
    from shadowlab.analytics import statistiques

    base = tmp_path / "test.sqlite3"
    cx = db.ouvrir(base)
    cx.execute(
        "INSERT INTO experiments (id, name, description, created_at, configuration, status, seed)"
        " VALUES (1, 't', '', '2026-01-01', '{}', 'termine', 1)"
    )
    cx.execute(
        "INSERT INTO engines (id, name, version, runtime, configuration) VALUES (1, 'httpx', '{}', 'python', '{}')"
    )
    cx.execute("INSERT INTO scenarios (id, name) VALUES (1, 'static_html')")
    cx.execute(
        "INSERT INTO runs (id, experiment_id, engine_id, scenario_id, repetition,"
        " session_token, truth, started_at, status, success, duration_ms, issue)"
        " VALUES (1, 1, 1, 1, 1, 'a', 'automatise', '2026-01-01', 'reussi', 1, 100, 'extraction_reussie')"
    )
    cx.execute(
        "INSERT INTO runs (id, experiment_id, engine_id, scenario_id, repetition,"
        " session_token, truth, started_at, status, success, duration_ms, issue)"
        " VALUES (2, 1, 1, 1, 2, 'b', 'automatise', '2026-01-01', 'erreur', 0, 50, 'bloque')"
    )
    stats = statistiques(cx, 1)
    moteur = stats["moteurs"][0]
    assert "par_issue" in moteur
    assert moteur["par_issue"]["extraction_reussie"] == 1
    assert moteur["par_issue"]["bloque"] == 1
