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


def test_variacion_participaciones_suman_cien(historial_dos_periodos):
    v = variacion(historial_dos_periodos)
    claves = ("margen_neto", "rotacion_activos", "multiplicador_capital")
    assert sum(v.valor(f"participacion_{k}") for k in claves) == pytest.approx(1)
    # Cada participación es su diferencia logarítmica sobre la del ROE
    d0, d1 = dupont(historial_dos_periodos, 0), dupont(historial_dos_periodos, 1)
    esperado = (math.log(d1.valor("margen_neto") / d0.valor("margen_neto"))
                / math.log(d1.valor("roe") / d0.valor("roe")))
    assert v.valor("participacion_margen_neto") == pytest.approx(esperado)
    assert v.hallazgos and "subió" in v.hallazgos[0] and "Participación en el cambio" in v.hallazgos[0]


def test_variacion_con_un_solo_periodo(historial):
    v = variacion(historial)
    assert v.indicadores == []
    assert any("al menos dos periodos" in a for a in v.advertencias)
