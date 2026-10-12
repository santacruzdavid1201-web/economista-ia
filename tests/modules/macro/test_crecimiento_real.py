"""Crecimiento real de los ingresos: casos calculados a mano."""
from datetime import date

import pytest

from data_sources.externos.series.modelo import Serie
from modules.esquema_financiero import HistorialFinanciero
from modules.macro.crecimiento_real import LIMITE_IPC, crecimiento_real
from tests.conftest import hacer_historial, periodo_2023


def ipc(meses: dict[tuple[int, int], float], geografia="Pasto", supuestos=()) -> Serie:
    obs = [(date(a, m, 28), v) for (a, m), v in meses.items()]
    return Serie(clave="ipc_x", nombre="IPC", fuente="BanRep (prueba)", unidad="índice",
                 frecuencia="mensual", geografia=geografia, consultada=date(2026, 10, 11),
                 observaciones=obs, supuestos=list(supuestos))


def anio(a: int, valor: float, desde=1, hasta=12) -> dict:
    return {(a, m): valor for m in range(desde, hasta + 1)}


IPC_5 = ipc({**anio(2023, 100), **anio(2024, 105)})


def historial(ingresos_2023: float, ingresos_2024: float, meses=12) -> HistorialFinanciero:
    h = hacer_historial(resultados={"ingresos_operacionales": ingresos_2024}, meses=meses)
    ant = periodo_2023()
    ant = ant.model_copy(update={"resultados": ant.resultados.model_copy(
        update={"ingresos_operacionales": ingresos_2023})})
    return HistorialFinanciero(empresa=h.empresa, periodos=[ant, h.ultimo])


def test_caso_a_mano_formula_exacta():
    r = crecimiento_real(historial(1_000, 1_100), 1, IPC_5)
    assert r.valor("crecimiento_nominal_ingresos") == pytest.approx(0.10)
    assert r.valor("inflacion_promedio") == pytest.approx(0.05)
    # 1,10 / 1,05 − 1 = 4,76 %, no la resta aproximada 10 % − 5 % = 5 %
    assert r.valor("crecimiento_real_ingresos") == pytest.approx(0.047619, abs=1e-6)
    assert r.valor("ingresos_anteriores_a_precios_actuales") == pytest.approx(1_050)
    assert r.modulo == "macro" and r.analisis == "crecimiento_real"


def test_hallazgo_crecimiento_real_positivo():
    r = crecimiento_real(historial(1_000, 1_100), 1, IPC_5)
    assert r.hallazgos == [
        "Entre 2023 y 2024 los ingresos operacionales crecieron 10,0 % en pesos corrientes "
        "y 4,8 % en términos reales, es decir, descontada la inflación promedio de Pasto "
        "(5,0 %).",
        LIMITE_IPC]


@pytest.mark.parametrize("ingresos_2024", [1_100, 1_030, 900])
def test_advierte_que_no_mide_cantidad_vendida(ingresos_2024):
    # El IPC general no son las tarifas de la empresa: el modelo afirmó "vendiste más
    # servicios" y "volumen de ventas" cuando el hallazgo no lo permitía (11/10/2026)
    r = crecimiento_real(historial(1_000, ingresos_2024), 1, IPC_5)
    assert r.hallazgos[-1] == LIMITE_IPC
    assert not any("vendió más" in h for h in r.hallazgos)


def test_hallazgo_cayeron_aunque_el_nominal_suba():
    r = crecimiento_real(historial(1_000, 1_030), 1, IPC_5)
    assert r.valor("crecimiento_real_ingresos") < 0
    assert r.hallazgos == [
        "Entre 2023 y 2024 los ingresos operacionales subieron 3,0 % en pesos corrientes, "
        "menos que la inflación promedio de Pasto (5,0 %): en términos reales cayeron 1,9 %.",
        LIMITE_IPC]


def test_hallazgo_caida_nominal():
    r = crecimiento_real(historial(1_000, 900), 1, IPC_5)
    assert r.hallazgos == [
        "Entre 2023 y 2024 los ingresos operacionales cayeron 10,0 % en pesos corrientes; "
        "con la inflación promedio de Pasto (5,0 %), la caída real fue 14,3 %.",
        LIMITE_IPC]


def test_ipc_nacional_se_nombra_asi():
    r = crecimiento_real(historial(1_000, 1_100), 1,
                         ipc({**anio(2023, 100), **anio(2024, 105)}, geografia="nacional"))
    assert "la inflación promedio nacional (5,0 %)" in r.hallazgos[0]


def test_periodo_de_seis_meses_promedia_solo_esos_meses_y_anualiza():
    # Corte 31/12/2024 con 6 meses: julio a diciembre. Los meses de enero a junio
    # (IPC 200) no deben entrar al promedio.
    serie = ipc({**anio(2023, 100), **anio(2024, 200, 1, 6), **anio(2024, 105, 7, 12)})
    r = crecimiento_real(historial(1_000, 550, meses=6), 1, serie)
    assert r.valor("crecimiento_nominal_ingresos") == pytest.approx(0.10)
    assert r.valor("inflacion_promedio") == pytest.approx(0.05)
    assert any("anualizados a partir de 6 meses" in s for s in r.supuestos)


def test_sin_periodo_anterior():
    r = crecimiento_real(hacer_historial(), 0, IPC_5)
    assert all(i.valor is None for i in r.indicadores)
    assert any("No hay periodo anterior" in a for a in r.advertencias)
    assert r.hallazgos == []


def test_ipc_sin_todos_los_meses():
    serie = ipc({**anio(2023, 100), **anio(2024, 105, 1, 11)})   # falta diciembre de 2024
    r = crecimiento_real(historial(1_000, 1_100), 1, serie)
    assert r.valor("crecimiento_nominal_ingresos") == pytest.approx(0.10)
    assert r.valor("inflacion_promedio") is None
    assert r.valor("crecimiento_real_ingresos") is None
    assert r.valor("ingresos_anteriores_a_precios_actuales") is None
    assert any("no cubre todos los meses" in a for a in r.advertencias)


def test_sin_ingresos_anteriores():
    r = crecimiento_real(historial(0, 1_100), 1, IPC_5)
    assert r.valor("crecimiento_nominal_ingresos") is None
    assert r.valor("crecimiento_real_ingresos") is None
    assert any("no tuvo ingresos operacionales en 2023" in a for a in r.advertencias)


def test_declara_serie_supuestos_del_catalogo_y_deflactor():
    serie = ipc({**anio(2023, 100), **anio(2024, 105)}, geografia="nacional",
                supuestos=["Se usó el IPC nacional porque no hay IPC de Ipiales."])
    r = crecimiento_real(historial(1_000, 1_100), 1, serie)
    assert "Se usó el IPC nacional porque no hay IPC de Ipiales." in r.supuestos
    assert any("IPC general" in s for s in r.supuestos)
    assert any("BanRep (prueba)" in f and "nacional" in f for f in r.fuentes)
