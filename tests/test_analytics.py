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
