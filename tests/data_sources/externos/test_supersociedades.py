"""
Cargador de Supersociedades con datos reales (hoteles CIIU 5511, corte 2024)
guardados en tests/data_sources/externos/datos/. Cifras en miles de pesos.
"""
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from data_sources.externos.supersociedades import (
    ErrorCarga,
    a_estado_financiero,
    cargar_mapeo,
    construir_historiales,
    filtrar_reportes,
    normalizar,
    normalizar_periodo,
)
from modules.balance.razones import endeudamiento, rentabilidad

DATOS = Path(__file__).parent / "datos"
MAPEO = cargar_mapeo()
CORTE = date(2024, 12, 31)


def leer(nombre: str) -> pd.DataFrame:
    return pd.read_csv(DATOS / f"{nombre}.csv", dtype=str)


@pytest.fixture(scope="module")
def carga():
    historiales, exclusiones = construir_historiales(
        leer("caratula"), leer("esf"), leer("eri"), leer("efe"))
    return {h.empresa.empresa_id: h for h in historiales}, exclusiones


# --------------------------------------------------------------------------- #
# Normalización y filtro
# --------------------------------------------------------------------------- #
def test_normalizar_iguala_tildes_danadas():
    assert normalizar("Gastos de administraci�n") == normalizar("Gastos de administración")
    assert normalizar("  Costo   de VENTAS ") == "costo de ventas"


def test_periodos_de_reportes_antiguos():
    # Hasta 2017 el periodo viene como fecha (balance) o como año (resultados)
    periodo = pd.Series(["2016-dic-31", "2015-dic-31", "2015-ene-01", "2016", "2015",
                         "Periodo Actual", "830010665"])
    corte = pd.Series(["2016-12-31T00:00:00.000"] * 7)
    assert normalizar_periodo(periodo, corte).fillna("").tolist() == [
        "Periodo Actual", "Periodo Anterior", "", "Periodo Actual", "Periodo Anterior",
        "Periodo Actual", ""]


def test_un_anio_sale_de_un_solo_reporte():
    # El comparativo del reporte siguiente no completa conceptos del reporte propio
    base = {"nit": "1", "punto_entrada": "40 NIIF Pymes", "valor": "10"}
    filas = [
        {**base, "numero_radicado": "A", "fecha_corte": "2016-12-31", "periodo": "Periodo Actual",
         "concepto": "Otros gastos"},
        {**base, "numero_radicado": "B", "fecha_corte": "2017-12-31", "periodo": "Periodo Anterior",
         "concepto": "Otros gastos, por función"},
    ]
    f = filtrar_reportes(pd.DataFrame(filas))
    assert f["numero_radicado"].tolist() == ["A"]


def test_filtro_descarta_consolidados_y_fecha_el_comparativo():
    esf = leer("esf")
    assert esf["punto_entrada"].str.startswith("30").any()  # el dato crudo sí los trae
    f = filtrar_reportes(esf)
    assert not f["punto_entrada"].str.startswith("30").any()
    assert set(f["fecha"]) == {date(2023, 12, 31), CORTE}
    assert not f.duplicated(["nit", "fecha", "clave"]).any()


# --------------------------------------------------------------------------- #
# Empresas reales
# --------------------------------------------------------------------------- #
def test_hotel_tipico_reproduce_los_totales_reportados(carga):
    h = carga[0]["800046878"]
    assert h.empresa.ciiu == "5511"
    assert h.empresa.unidad == 1_000
    assert [p.fecha_corte.year for p in h.periodos] == [2023, 2024]
    b, r = h.ultimo.balance, h.ultimo.resultados
    assert b.activo_total == 14_023_008
    assert b.activo_corriente == 1_200_623
    assert b.pasivo_corriente == 711_025
    assert b.patrimonio_total == 12_886_257
    # Ganancias acumuladas (2.496.323) incluye la utilidad del año (248.727)
    assert b.resultado_ejercicio == 248_727
    assert b.resultados_acumulados == 2_496_323 - 248_727
    assert r.utilidad_neta == pytest.approx(248_727)
    assert r.depreciacion_amortizacion == 260_604
    assert h.ultimo.supuestos_carga == []


def test_deuda_financiera_no_se_duplica(carga):
    # Reporta "Otros pasivos financieros no corrientes" y su desglose
    # "Parte no corriente de préstamos" por el mismo valor: cuenta una sola vez.
    b = carga[0]["800046878"].ultimo.balance
    assert b.deuda_financiera == 50_966
    b = carga[0]["800156664"].ultimo.balance
    assert b.obligaciones_financieras_cp == 1_341_827
    assert b.obligaciones_financieras_lp == 488_805


def test_comparativo_da_el_periodo_anterior(carga):
    h = carga[0]["800046878"]
    anterior = h.periodos[0]
    assert anterior.balance.activo_total == 13_751_185
    assert anterior.resultados.ingresos_operacionales == 3_254_227
    assert any("comparativo" in s for s in anterior.supuestos_carga)
    # Con dos periodos, las razones flujo/saldo usan saldo promedio
    assert h.saldo_promedio("activo_total") == ((14_023_008 + 13_751_185) / 2, True)


def test_impuesto_negativo_es_beneficio(carga):
    r = carga[0]["800156664"].ultimo.resultados
    assert r.impuesto_renta == -3_289_251
    assert r.utilidad_neta == pytest.approx(-7_150_730)


def test_partidas_no_mapeadas_van_a_otros_con_supuesto(carga):
    ef = carga[0]["800065539"].ultimo
    assert ef.resultados.utilidad_antes_impuestos == pytest.approx(8_845_398)
    assert any("no operacionales" in s for s in ef.supuestos_carga)


def test_sin_depreciacion_reportada_no_hay_ebitda(carga):
    h = carga[0]["800072974"]
    assert h.ultimo.resultados.depreciacion_amortizacion is None
    assert endeudamiento(h).valor("deuda_ebitda") is None
    assert rentabilidad(h).valor("margen_ebitda") is None


def test_sin_costo_de_ventas_queda_marcado(carga):
    r = carga[0]["800230527"].ultimo.resultados
    assert "costo_ventas" not in r.model_fields_set
    assert r.utilidad_bruta == r.ingresos_operacionales


def test_retransmision_reemplaza_el_reporte_completo(carga):
    historiales, exclusiones = carga
    # El radicado original reporta intangibles y plusvalía; la retransmisión
    # corrigió y reporta solo intangibles. Mezclar conceptos de los dos
    # reportes contaba dos veces la misma cifra.
    h = historiales["806000591"]
    assert h.ultimo.balance.intangibles == 8_952_762
    assert not [e for e in exclusiones if e.nit == "806000591"]


def test_las_funciones_del_modulo_corren_sobre_los_pares(carga):
    for h in carga[0].values():
        res = rentabilidad(h)
        assert res.valor("margen_operacional") is not None


# --------------------------------------------------------------------------- #
# Reglas puntuales (datos sintéticos)
# --------------------------------------------------------------------------- #
def reporte(**cambios) -> tuple[dict, dict]:
    """Balance y resultados mínimos que cuadran: activo 100 = pasivo 40 + patrimonio 60."""
    esf = {
        "Total de activos": 100, "Activos corrientes totales": 30,
        "Total pasivos": 40, "Pasivos corrientes totales": 25, "Patrimonio total": 60,
        "Efectivo y equivalentes al efectivo": 30, "Propiedades, planta y equipo": 70,
        "Cuentas por pagar comerciales y otras cuentas por pagar corrientes": 25,
        "Otros pasivos financieros no corrientes": 15,
        "Capital emitido": 50, "Ganancias acumuladas": 10,
    }
    eri = {"Ingresos de actividades ordinarias": 80, "Gastos de administración": 70,
           "Ganancia (pérdida), antes de impuestos": 10, "Ganancia (pérdida)": 10}
    for k, v in cambios.items():
        destino = esf if k in esf or k.startswith(("Total", "Activo", "Otro", "Acciones")) else eri
        destino[k] = v
    return ({normalizar(k): v for k, v in esf.items() if v is not None},
            {normalizar(k): v for k, v in eri.items() if v is not None})


def test_reporte_minimo_cuadra():
    ef = a_estado_financiero(*reporte(), None, CORTE, MAPEO)
    assert ef.balance.activo_total == 100
    assert ef.balance.resultados_acumulados == 0
    assert ef.supuestos_carga == []


def test_residuo_positivo_va_a_otros_con_supuesto():
    # El activo corriente reporta 40 pero las cuentas identificadas suman 30
    esf, eri = reporte(**{"Total de activos": 110, "Activos corrientes totales": 40,
                          "Patrimonio total": 70, "Capital emitido": 60})
    ef = a_estado_financiero(esf, eri, None, CORTE, MAPEO)
    assert ef.balance.otros_activos_cp == 10
    assert any("25.0% del activo corriente" in s for s in ef.supuestos_carga)


def test_acciones_propias_restan_del_patrimonio():
    esf, eri = reporte(**{"Acciones propias en cartera": 5, "Patrimonio total": 55,
                          "Total pasivos": 45, "Pasivos corrientes totales": 30,
                          "Otros pasivos financieros corrientes": 5})
    ef = a_estado_financiero(esf, eri, None, CORTE, MAPEO)
    assert ef.balance.otro_patrimonio == -5
    assert ef.balance.patrimonio_total == 55


def test_doble_conteo_se_rechaza():
    # Intangibles reportados además de la PPE que ya completa el no corriente
    esf, eri = reporte(**{"Activos intangibles distintos de la plusvalía": 70})
    with pytest.raises(ErrorCarga, match="doble conteo"):
        a_estado_financiero(esf, eri, None, CORTE, MAPEO)


def test_falta_un_total_se_rechaza():
    esf, eri = reporte(**{"Pasivos corrientes totales": None})
    with pytest.raises(ErrorCarga, match="pasivo_corriente"):
        a_estado_financiero(esf, eri, None, CORTE, MAPEO)


def test_flujo_que_no_cuadra_se_omite():
    efe = {normalizar(MAPEO["flujo"]["operacion"]): 10,
           normalizar(MAPEO["flujo"]["inversion"]): -4,
           normalizar(MAPEO["flujo"]["variacion_efectivo"]): 99}
    ef = a_estado_financiero(*reporte(), efe, CORTE, MAPEO)
    assert ef.flujo is None
    assert any("no cuadra" in s for s in ef.supuestos_carga)
