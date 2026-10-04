"""
Empresa de referencia: Activo 2.050 | Capital de trabajo 280 | Utilidades retenidas 180
EBIT 250 | Patrimonio 1.180 | Pasivo 870
EM = 3,25 + 6,56·0,13659 + 3,26·0,08780 + 6,72·0,12195 + 1,05·1,35632 ≈ 6,676
"""
import pytest

from modules.balance.altman import altman, calificacion_equivalente, zona
from tests.conftest import hacer_historial


def test_em_score_empresa_de_referencia(historial):
    res = altman(historial)
    assert res.valor("x1") == pytest.approx(280 / 2_050)
    assert res.valor("x2") == pytest.approx(180 / 2_050)
    assert res.valor("x3") == pytest.approx(250 / 2_050)
    assert res.valor("x4") == pytest.approx(1_180 / 870)
    assert res.valor("em_score") == pytest.approx(6.676, abs=1e-3)
    assert "zona segura" in res.hallazgos[0] and "calificación A " in res.hallazgos[0]


def test_patrimonio_negativo_cae_en_zona_de_riesgo():
    h = hacer_historial(balance={"obligaciones_financieras_lp": 2_000,
                                 "resultados_acumulados": -1_360})
    res = altman(h)
    assert res.valor("em_score") == pytest.approx(2.924, abs=1e-3)
    assert "zona riesgo" in res.hallazgos[0] and "CCC" in res.hallazgos[0]


def test_advierte_sector_financiero(historial):
    historial.empresa = historial.empresa.model_copy(update={"ciiu": "6419"})
    res = altman(historial)
    assert any("sector financiero" in a for a in res.advertencias)


@pytest.mark.parametrize("em, esperado", [
    (8.5, "AAA"), (6.676, "A"), (5.85, "BBB"), (5.84, "BBB-"),
    (4.40, "B"), (1.80, "CCC-"), (1.0, "D"),
])
def test_tabla_de_calificaciones(em, esperado):
    assert calificacion_equivalente(em) == esperado


@pytest.mark.parametrize("em, esperado", [
    (6.0, "segura"), (5.85, "gris"), (4.35, "gris"), (4.34, "riesgo"),
])
def test_zonas(em, esperado):
    assert zona(em) == esperado
