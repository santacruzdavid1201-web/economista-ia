"""Costo de capital: el caso a mano de SPEC-costo-capital.md y los casos borde."""
from datetime import date

import pytest

from data_sources.externos.series.modelo import Serie
from modules.proyectos.wacc import Parametros, costo_capital
from tests.conftest import hacer_historial

TES_UVR = Serie(clave="tes_uvr_10", nombre="TES UVR 10 años", fuente="BanRep (prueba TES)",
                unidad="Tasa", frecuencia="diaria", geografia="nacional",
                consultada=date(2026, 10, 9), observaciones=[(date(2026, 10, 9), 6.74)])
# Inflación de 2024 (12 meses al corte del balance): 5,1 %
IPC = Serie(clave="ipc_nacional", nombre="IPC", fuente="BanRep (prueba IPC)", unidad="Indice",
            frecuencia="mensual", geografia="nacional", consultada=date(2026, 10, 9),
            observaciones=[(date(2023, 12, 31), 100.0), (date(2024, 12, 31), 105.1)])
# β sin deuda hipotética de 1,00, como en el ejemplo de la especificación
PARAMETROS = Parametros(beta_sin_deuda=1.0, spread=0.0187, prima_total=0.0708,
                        fuente="Damodaran (prueba)", sector="Hotel/Gaming")


def historial(deuda=500, gastos_financieros=70, patrimonio=1_000, gastos_administracion=230):
    """
    Deuda 500 y patrimonio 1.000 (D/P = 0,5); gastos financieros 70 sobre la deuda
    de cierre (no hay periodo anterior): Kd = 14 %. Los activos cuadran el balance.
    """
    proveedores = 120
    return hacer_historial(
        balance={"obligaciones_financieras_cp": deuda * 0.2,
                 "obligaciones_financieras_lp": deuda * 0.8,
                 "capital": patrimonio - 180, "resultados_acumulados": 40,
                 "resultado_ejercicio": 140, "efectivo": 0,
                 "ppe": deuda + proveedores + patrimonio - 250},
        resultados={"gastos_financieros": gastos_financieros,
                    "gastos_administracion": gastos_administracion})


def calcular(h=None, ipc=IPC):
    return costo_capital(TES_UVR, PARAMETROS, tarifa=0.35, inflacion_1=0.043,
                         historial=h or historial(), ipc=ipc)


def test_caso_a_mano():
    r = calcular()
    assert r.valor("beta_apalancada") == pytest.approx(1.325)
    assert r.valor("costo_patrimonio") == pytest.approx(0.1425, abs=5e-5)
    assert r.valor("costo_deuda_nominal") == pytest.approx(0.14)
    assert r.valor("costo_deuda_real") == pytest.approx(0.0381, abs=5e-5)
    assert r.valor("peso_deuda") == pytest.approx(1 / 3)
    assert r.valor("wacc") == pytest.approx(0.1077, abs=5e-5)
    assert r.valor("wacc_nominal") == pytest.approx(0.1553, abs=5e-5)
    assert r.modulo == "proyectos" and r.analisis == "costo_capital"
    assert r.fecha_corte == date(2024, 12, 31)


def test_la_tasa_sin_riesgo_resta_el_spread_del_tes():
    assert calcular().valor("tasa_sin_riesgo") == pytest.approx(0.0487)


def test_sin_estados_financieros_da_el_costo_de_los_activos():
    r = costo_capital(TES_UVR, PARAMETROS, tarifa=0.35, inflacion_1=0.043)
    assert r.valor("costo_activos") == pytest.approx(0.1195)
    assert r.valor("costo_activos_nominal") == pytest.approx(1.1195 * 1.043 - 1)
    assert "wacc" not in {i.clave for i in r.indicadores}
    assert any("referencia" in h for h in r.hallazgos)


def test_sin_deuda_el_wacc_es_el_costo_del_patrimonio():
    r = calcular(historial(deuda=0, gastos_financieros=0, gastos_administracion=300))
    assert r.valor("beta_apalancada") == pytest.approx(1.0)
    assert r.valor("wacc") == pytest.approx(r.valor("costo_patrimonio"))
    assert r.valor("wacc") == pytest.approx(0.1195)
    assert "costo_deuda_real" not in {i.clave for i in r.indicadores}
    assert any("no tiene deuda financiera" in h for h in r.hallazgos)


def test_deuda_sin_gastos_financieros_no_tiene_wacc():
    r = calcular(historial(gastos_financieros=0, gastos_administracion=300))
    assert r.valor("costo_deuda_real") is None
    assert r.valor("wacc") is None and r.valor("wacc_nominal") is None
    assert r.valor("costo_patrimonio") == pytest.approx(0.1425, abs=5e-5)
    assert any("gastos financieros" in a for a in r.advertencias)


def test_patrimonio_negativo_no_tiene_wacc_y_da_el_costo_de_los_activos():
    r = calcular(historial(patrimonio=-100))
    assert r.valor("wacc") is None
    assert r.valor("costo_activos") == pytest.approx(0.1195)
    assert any("patrimonio" in a for a in r.advertencias)


def test_sin_ipc_del_mes_del_corte_no_hay_costo_real_de_la_deuda():
    ipc = IPC.model_copy(update={"observaciones": IPC.observaciones[:1]})
    r = calcular(ipc=ipc)
    assert r.valor("costo_deuda_real") is None and r.valor("wacc") is None
    assert any("IPC" in a for a in r.advertencias)


def test_con_perdida_advierte_que_no_aprovecha_el_ahorro_de_impuestos():
    r = calcular(historial(gastos_administracion=900))
    assert r.valor("wacc") is not None
    assert any("ahorro de impuestos" in a for a in r.advertencias)


def test_hallazgos_dicen_real_y_nominal_y_que_es_una_referencia():
    texto = " ".join(calcular().hallazgos)
    assert "10,77 %" in texto and "15,53 %" in texto
    assert "real" in texto and "referencia, no una regla" in texto
    assert "conviene" not in texto


def test_supuestos_y_fuentes_nombran_damodaran_el_tes_y_los_valores_en_libros():
    r = calcular()
    assert any("Hamada" in s for s in r.supuestos)
    assert any("en libros" in s for s in r.supuestos)
    assert any("Damodaran" in f for f in r.fuentes)
    assert any("prueba TES" in f for f in r.fuentes)
