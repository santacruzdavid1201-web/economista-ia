import math

import pytest

from modules.balance.dupont import dupont, variacion
from modules.balance.razones import rentabilidad
from tests.conftest import hacer_historial


def test_dupont_reproduce_el_roe(historial_dos_periodos):
    d = dupont(historial_dos_periodos)
    assert d.valor("margen_neto") == pytest.approx(0.14)
    assert d.valor("rotacion_activos") == pytest.approx(1_000 / 1_945)
    assert d.valor("multiplicador_capital") == pytest.approx(1_945 / 1_070)
    # La identidad DuPont debe coincidir con el ROE directo
    assert d.valor("roe") == pytest.approx(rentabilidad(historial_dos_periodos).valor("roe"))


def test_dupont_patrimonio_negativo():
    h = hacer_historial(balance={"obligaciones_financieras_lp": 2_000,
                                 "resultados_acumulados": -1_360})
    d = dupont(h)
    assert d.valor("roe") is None
    assert any("no tiene interpretación" in a for a in d.advertencias)


def test_variacion_contribuciones_suman_el_cambio(historial_dos_periodos):
    v = variacion(historial_dos_periodos)
    suma = sum(v.valor(f"contribucion_{k}")
               for k in ("margen_neto", "rotacion_activos", "multiplicador_capital"))
    assert suma == pytest.approx(v.valor("cambio_log_roe"))
    assert v.valor("cambio_log_roe") == pytest.approx(
        math.log(v.valor("roe_actual") / v.valor("roe_anterior")))
    assert v.hallazgos and "subió" in v.hallazgos[0]


def test_variacion_con_un_solo_periodo(historial):
    v = variacion(historial)
    assert v.indicadores == []
    assert any("al menos dos periodos" in a for a in v.advertencias)
