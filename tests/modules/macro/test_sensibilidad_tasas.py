"""Sensibilidad a tasas de interés: casos calculados a mano."""
import json
from datetime import date
from pathlib import Path

import pytest

from data_sources.externos.series import banrep
from data_sources.externos.series.modelo import Serie
from modules.esquema_financiero import HistorialFinanciero
from modules.macro.sensibilidad_tasas import (
    NO_ES_PRONOSTICO,
    ErrorPuntos,
    mayor_alza_12m,
    sensibilidad_tasas,
)
from tests.conftest import hacer_historial, periodo_2023

DATOS = Path(__file__).parents[2] / "data_sources" / "externos" / "datos"


def tasa(obs: list[tuple[date, float]], clave="x") -> Serie:
    return Serie(clave=clave, nombre=clave, fuente=f"BanRep (prueba {clave})",
                 unidad="Tasa (prueba)", frecuencia="diaria", geografia="nacional",
                 consultada=date(2026, 10, 12), observaciones=obs)


TPM = tasa([(date(2025, 10, 12), 9.25), (date(2026, 10, 12), 12.25)], "tasa_politica")
# Mayor alza a 12 meses: diciembre de 2022, 11,66 − 3,418 = 8,242 puntos
IBR = tasa([(date(2021, 12, 31), 3.418), (date(2022, 12, 30), 11.66),
            (date(2026, 10, 9), 11.698)], "ibr_3m")


def historial(deuda=1_000, deuda_ant=900, gastos_financieros=95, utilidad_operacional=300,
              meses=12) -> HistorialFinanciero:
    """
    Ingresos 1.000, costo 400, ventas 100: los gastos de administración ajustan la UO.
    El capital compensa el cambio de deuda para que el balance cuadre (deuda de la
    empresa de referencia: 750 en 2024 y 780 en 2023).
    """
    h = hacer_historial(
        balance={"obligaciones_financieras_cp": deuda * 0.2,
                 "obligaciones_financieras_lp": deuda * 0.8,
                 "capital": 1_000 - (deuda - 750)},
        resultados={"gastos_financieros": gastos_financieros,
                    "gastos_administracion": 500 - utilidad_operacional},
        meses=meses)
    ant = periodo_2023()
    ant = ant.model_copy(update={"balance": ant.balance.model_copy(update={
        "obligaciones_financieras_cp": deuda_ant * 0.2,
        "obligaciones_financieras_lp": deuda_ant * 0.8,
        "capital": 1_000 - (deuda_ant - 780)})})
    return HistorialFinanciero(empresa=h.empresa, periodos=[ant, h.ultimo])


def calcular(h=None, puntos=None):
    return sensibilidad_tasas(h or historial(), 1, TPM, IBR, puntos)


def test_caso_a_mano():
    r = calcular()
    assert r.valor("deuda_financiera") == pytest.approx(1_000)
    assert r.valor("tasa_implicita_deuda") == pytest.approx(0.10)      # 95 / 950
    assert r.valor("intereses_por_punto") == pytest.approx(10)
    assert r.valor("gastos_financieros_anuales") == pytest.approx(95)
    assert r.valor("cobertura_intereses") == pytest.approx(300 / 95)
    for n, gastos in [(1, 105), (2, 115), (3, 125)]:
        assert r.valor(f"gastos_financieros_mas_{n}") == pytest.approx(gastos)
        assert r.valor(f"cobertura_mas_{n}") == pytest.approx(300 / gastos)
    for n, gastos in [(1, 85), (2, 75), (3, 65)]:
        assert r.valor(f"gastos_financieros_menos_{n}") == pytest.approx(gastos)
        assert r.valor(f"cobertura_menos_{n}") == pytest.approx(300 / gastos)
    assert r.valor("cobertura_mas_3") == pytest.approx(2.40)
    assert r.modulo == "macro" and r.analisis == "sensibilidad_tasas"


def test_escenario_historico():
    r = calcular()
    assert r.valor("mayor_alza_ibr_12m") == pytest.approx(0.08242)
    assert r.valor("gastos_financieros_historico") == pytest.approx(95 + 82.42)
    assert r.valor("cobertura_historico") == pytest.approx(300 / 177.42)


def test_contexto_de_mercado():
    r = calcular()
    assert r.valor("tasa_politica") == pytest.approx(0.1225)
    assert r.valor("ibr_3m") == pytest.approx(0.11698)
    assert any("prueba tasa_politica" in f for f in r.fuentes)
    assert any("prueba ibr_3m" in f for f in r.fuentes)


def test_hallazgos():
    assert calcular().hallazgos == [
        "Cada punto que suba la tasa de la deuda le suma $ 10 al año en gastos financieros "
        "(1 % de la deuda financiera de $ 1.000).",
        "En 2024 los gastos financieros fueron $ 95 y la cobertura de intereses 3,16 veces.",
        "Con 3 puntos más, los gastos financieros aumentarían $ 30 al año, hasta $ 125, y la "
        "cobertura de intereses bajaría a 2,40 veces.",
        "Con 3 puntos menos, los gastos financieros disminuirían $ 30 al año, hasta $ 65, y la "
        "cobertura de intereses subiría a 4,62 veces.",
        "La mayor alza de la IBR a 3 meses en un año fue de 8,24 puntos, en 2022 (de diciembre "
        "de 2021 a diciembre de 2022): si la tasa de la deuda subiera eso, los gastos "
        "financieros aumentarían $ 82 al año, hasta $ 177, y la cobertura bajaría a 1,69 "
        "veces.",
        "Aun con un alza como la de 2022, la utilidad operacional seguiría alcanzando para "
        "pagar los gastos financieros.",
        "Al 12/10/2026 la tasa de política monetaria del Banco de la República es 12,25 %; "
        "la IBR a 3 meses, referencia de muchos créditos a tasa variable, estaba en 11,70 % "
        "al 09/10/2026.",
        NO_ES_PRONOSTICO]


def test_alza_que_agota_la_cobertura_menor_que_la_historica():
    # (120 − 95) / 1.000 = 2,5 puntos, menos que los 8,24 de 2022
    r = calcular(historial(utilidad_operacional=120))
    assert ("Con un alza de 2,50 puntos, menor que la de 2022 (8,24 puntos), la utilidad "
            "operacional apenas alcanzaría para pagar los gastos financieros.") in r.hallazgos


def test_escenario_pedido_va_solo():
    # Con todos los escenarios a la vez, el 7B los comparaba por su cuenta
    r = calcular(puntos=5)
    assert r.valor("gastos_financieros_pedido") == pytest.approx(145)
    assert r.valor("cobertura_pedido") == pytest.approx(300 / 145)
    claves = {i.clave for i in r.indicadores}
    assert "gastos_financieros_mas_3" not in claves and "mayor_alza_ibr_12m" not in claves
    assert r.hallazgos == [
        "Cada punto que suba la tasa de la deuda le suma $ 10 al año en gastos financieros "
        "(1 % de la deuda financiera de $ 1.000).",
        "En 2024 los gastos financieros fueron $ 95 y la cobertura de intereses 3,16 veces.",
        "Con 5 puntos más, los gastos financieros aumentarían $ 50 al año, hasta $ 145, y la "
        "cobertura de intereses bajaría a 2,07 veces.",
        "Al 12/10/2026 la tasa de política monetaria del Banco de la República es 12,25 %; "
        "la IBR a 3 meses, referencia de muchos créditos a tasa variable, estaba en 11,70 % "
        "al 09/10/2026.",
        NO_ES_PRONOSTICO]


def test_escenario_pedido_de_los_fijos_usa_su_clave():
    r = calcular(puntos=-2)
    assert r.valor("gastos_financieros_menos_2") == pytest.approx(75)
    assert r.valor("cobertura_menos_2") == pytest.approx(4.0)
    assert all(i.clave != "gastos_financieros_pedido" for i in r.indicadores)
    assert ("Con 2 puntos menos, los gastos financieros disminuirían $ 20 al año, hasta "
            "$ 75, y la cobertura de intereses subiría a 4,00 veces.") in r.hallazgos
    r = calcular(puntos=1)
    assert ("Con 1 punto más, los gastos financieros aumentarían $ 10 al año, hasta $ 105, "
            "y la cobertura de intereses bajaría a 2,86 veces.") in r.hallazgos


@pytest.mark.parametrize("puntos", [0, 15, -10.5])
def test_puntos_fuera_de_rango(puntos):
    with pytest.raises(ErrorPuntos, match="entre −10 y 10"):
        calcular(puntos=puntos)


def test_supuestos_declarados():
    r = calcular()
    assert any("toda la deuda financiera" in s for s in r.supuestos)
    assert any("antes de impuestos" in s for s in r.supuestos)
    assert any("comisiones" in s for s in r.supuestos)
    assert any("demanda" in s for s in r.supuestos)


def test_sin_deuda_financiera():
    r = calcular(historial(deuda=0, deuda_ant=0, gastos_financieros=0))
    assert r.valor("deuda_financiera") == 0
    assert r.valor("intereses_por_punto") is None
    assert r.valor("gastos_financieros_mas_3") is None
    assert r.hallazgos[0] == ("La empresa no tiene deuda financiera al corte: un cambio en "
                              "las tasas no le cambia los gastos financieros.")
    assert not any("toda la deuda financiera" in s for s in r.supuestos)


def test_deuda_sin_gastos_financieros_identificados():
    r = calcular(historial(gastos_financieros=0))
    assert r.valor("intereses_por_punto") == pytest.approx(10)
    assert r.valor("tasa_implicita_deuda") is None
    assert r.valor("gastos_financieros_mas_3") is None
    assert r.valor("cobertura_mas_3") is None
    assert not any("apenas alcanzaría" in h or "seguiría alcanzando" in h for h in r.hallazgos)
    assert any("otra cuenta" in a for a in r.advertencias)


def test_utilidad_operacional_negativa():
    r = calcular(historial(utilidad_operacional=-50))
    assert r.valor("gastos_financieros_mas_3") == pytest.approx(125)
    assert r.valor("cobertura_mas_3") is None
    assert not any("apenas alcanzaría" in h or "seguiría alcanzando" in h for h in r.hallazgos)
    assert any("nula o negativa" in a for a in r.advertencias)


def test_cobertura_actual_menor_que_uno():
    r = calcular(historial(utilidad_operacional=80))
    assert r.valor("cobertura_mas_1") == pytest.approx(80 / 105)
    assert not any("apenas alcanzaría" in h or "seguiría alcanzando" in h for h in r.hallazgos)
    assert any("ya no alcanza" in a for a in r.advertencias)


def test_baja_que_dejaria_gastos_negativos():
    r = calcular(historial(gastos_financieros=15))       # 15 − 1.000 × 2 % < 0
    assert r.valor("gastos_financieros_menos_1") == pytest.approx(5)
    assert r.valor("gastos_financieros_menos_2") is None
    assert r.valor("cobertura_menos_2") is None


def test_periodo_de_seis_meses_anualiza_flujos():
    r = calcular(historial(gastos_financieros=47.5, utilidad_operacional=150, meses=6))
    assert r.valor("gastos_financieros_anuales") == pytest.approx(95)
    assert r.valor("tasa_implicita_deuda") == pytest.approx(0.10)
    assert r.valor("cobertura_mas_3") == pytest.approx(2.40)
    assert any("anualizados a partir de 6 meses" in s for s in r.supuestos)


def test_sin_periodo_anterior_usa_deuda_al_cierre():
    h = historial()
    r = sensibilidad_tasas(HistorialFinanciero(empresa=h.empresa, periodos=[h.ultimo]), 0,
                           TPM, IBR)
    assert r.valor("tasa_implicita_deuda") == pytest.approx(0.095)    # 95 / 1.000
    assert any("saldos de cierre" in s for s in r.supuestos)


def test_mayor_alza_con_la_ibr_real():
    """+8,242 puntos a diciembre de 2022 (consultado al averiguar los ids, 12/10/2026)."""
    respuesta = json.loads((DATOS / "suameca_ibr_3m.json").read_text(encoding="utf-8"))[0]
    ibr = banrep.desde_suameca(respuesta, "ibr_3m_nacional", "nacional", date(2026, 10, 12))
    fecha, alza = mayor_alza_12m(ibr)
    assert (fecha.year, fecha.month) == (2022, 12)
    assert alza == pytest.approx(8.242)
