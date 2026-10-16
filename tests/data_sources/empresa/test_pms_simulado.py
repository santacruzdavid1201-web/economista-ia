"""
Hotel simulado con proceso generador conocido (SPEC-series-empresa.md): los rangos
que debe cumplir para servir de demostración y de verdad para los estimadores.
"""
from datetime import date

import pandas as pd
import pytest

from app.demo import contexto_demo
from data_sources.empresa.pms_simulado import CSV_DEMO, parametros, simular_pms


@pytest.fixture(scope="module")
def serie() -> pd.DataFrame:
    return simular_pms(parametros(), semilla=1)


def ocupacion(df: pd.DataFrame) -> float:
    return df["habitaciones_vendidas"].sum() / df["habitaciones_disponibles"].sum()


def test_misma_semilla_misma_serie(serie):
    pd.testing.assert_frame_equal(serie, simular_pms(parametros(), semilla=1))
    assert not serie.equals(simular_pms(parametros(), semilla=2))


def test_columnas_canonicas_y_dias_seguidos(serie):
    assert list(serie.columns) == ["fecha", "habitaciones_disponibles", "habitaciones_vendidas",
                                   "ingresos_habitaciones", "tarifa_publicada",
                                   "tarifa_competencia", "promocion", "huespedes"]
    assert serie["fecha"].iloc[0] == date(2023, 1, 1) and serie["fecha"].iloc[-1] == date(2026, 9, 30)
    assert len(serie) == 1369 and serie["fecha"].is_unique


def test_ocupacion_media_como_la_region_pacifico(serie):
    assert ocupacion(serie) == pytest.approx(0.40, abs=0.03)


def test_el_carnaval_llena_el_hotel(serie):
    for anio in (2023, 2024, 2025, 2026):
        carnaval = serie[serie["fecha"].between(date(anio, 1, 2), date(anio, 1, 7))]
        central = carnaval[carnaval["fecha"].isin([date(anio, 1, 5), date(anio, 1, 6)])]
        assert ocupacion(central) > 0.9
        llenos = (carnaval["habitaciones_vendidas"] == carnaval["habitaciones_disponibles"]).sum()
        assert llenos >= 3, f"Carnaval de {anio}: solo {llenos} días llenos"


def test_nunca_vende_mas_de_lo_que_tiene(serie):
    assert (serie["habitaciones_vendidas"] <= serie["habitaciones_disponibles"]).all()
    assert set(serie["habitaciones_disponibles"]) <= {43, 44, 45}


def test_los_ingresos_cuadran_con_los_balances_de_demostracion(serie):
    anual = serie.groupby(pd.to_datetime(serie["fecha"]).dt.year)["ingresos_habitaciones"].sum()
    for periodo in contexto_demo().historial.periodos:
        ingresos = periodo.resultados.ingresos_operacionales
        assert 0.60 <= anual[periodo.fecha_corte.year] / ingresos <= 0.80


def test_promociones_en_8_por_ciento_de_los_dias(serie):
    assert serie["promocion"].mean() == pytest.approx(0.08, abs=0.02)


def test_la_tarifa_publicada_sube_en_carnaval(serie):
    enero = serie[pd.to_datetime(serie["fecha"]).dt.month == 1]
    carnaval = enero["fecha"].map(lambda d: 2 <= d.day <= 7)
    assert enero[carnaval]["tarifa_publicada"].mean() > 1.3 * enero[~carnaval]["tarifa_publicada"].mean()


def test_el_csv_de_la_demostracion_es_el_de_los_parametros(serie):
    demo = pd.read_csv(CSV_DEMO, parse_dates=["fecha"])
    demo["fecha"] = demo["fecha"].dt.date
    pd.testing.assert_frame_equal(demo, serie, check_dtype=False)
