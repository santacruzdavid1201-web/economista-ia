"""Lectura de la pregunta: lo que el 7B confunde (tipo de tasa, montos, plazo) lo lee Python."""
import pytest

from app.orchestrator.lectura import (
    pide_wacc,
    direccion,
    monto_en_pesos,
    montos,
    periodicidad,
    sistema,
    tipo_de_tasa,
    tipo_destino,
    unidad_plazo,
    variable_del_proyecto,
)


@pytest.mark.parametrize("pregunta, tasa, esperado", [
    ("¿Cuánto pago por un crédito de 200 millones al 18 % EA a 5 años?", 18, ("EA", False)),
    ("crédito al 18% E.A.", 18, ("EA", False)),
    ("al 18 % efectivo anual", 18, ("EA", False)),
    ("al 18 % de interés efectivo anual", 18, ("EA", False)),
    ("una tasa efectiva anual del 18 %", 18, ("EA", False)),
    ("al 24 % NMV", 24, ("NMV", False)),
    ("al 24 % nominal mes vencido", 24, ("NMV", False)),
    ("¿2 % mensual cuánto es en efectivo anual?", 2, ("MV", False)),
    ("al 1,5 % mes vencido", 1.5, ("MV", False)),
    ("al 2 % mes anticipado", 2, ("MA", False)),
    ("al 24 % NMA", 24, ("NMA", False)),
    ("al 12 % NTV", 12, ("NTV", False)),
    ("al 3 % trimestral", 3, ("TV", False)),
    ("una tasa mensual del 2 %", 2, ("MV", False)),
    # "anual" sin más: efectiva anual, como deben informarla los bancos (supuesto)
    ("al 18 % anual con cuotas mensuales", 18, ("EA", True)),
    # Sin tipo: no se adivina
    ("un crédito al 18 % a 5 años", 18, (None, False)),
    # La tasa pedida es la que se lee, no otra del texto
    ("si la cuota sube 5 % y la tasa es 18 % EA", 18, ("EA", False)),
])
def test_tipo_de_tasa(pregunta, tasa, esperado):
    assert tipo_de_tasa(pregunta, tasa) == esperado


@pytest.mark.parametrize("pregunta, monto", [
    ("un crédito de 200 millones", 200_000_000),
    ("un crédito de 1.500 millones", 1_500_000_000),
    ("un crédito de $200.000.000", 200_000_000),
    ("un crédito de $ 80.000.000 de pesos", 80_000_000),
    ("un crédito de mil millones", 1_000_000_000),
    ("un crédito de 2 mil millones", 2_000_000_000),
    ("un crédito de 2,5 millones", 2_500_000),
    ("un préstamo de 500 mil pesos", 500_000),
    ("un crédito de 200 millón", 200_000_000),
])
def test_montos(pregunta, monto):
    assert monto in montos(pregunta)


@pytest.mark.parametrize("pregunta, plazo, esperado", [
    ("a 5 años", 5, "años"),
    ("a 1 año", 1, "años"),
    ("a 60 meses", 60, "meses"),
    ("en 24 cuotas", 24, "cuotas"),
    ("a 5 años", 60, None),
])
def test_unidad_plazo(pregunta, plazo, esperado):
    assert unidad_plazo(pregunta, plazo) == esperado


@pytest.mark.parametrize("pregunta, esperado", [
    ("con cuotas trimestrales", "trimestral"),
    ("pagando cada semestre", "semestral"),
    ("con cuotas anuales", "anual"),
    ("al 18 % anual a 5 años", "mensual"),        # "anual" de la tasa no es la cuota
    ("con pagos anticipados", "mensual"),
    ("pagando cada año", "anual"),
])
def test_periodicidad(pregunta, esperado):
    assert periodicidad(pregunta) == esperado


@pytest.mark.parametrize("pregunta, esperado", [
    ("con abono constante a capital", "abono_constante"),
    ("con cuotas decrecientes", "abono_constante"),
    ("con cuota fija", "cuota_fija"),
    ("un crédito de 200 millones", "cuota_fija"),
])
def test_sistema(pregunta, esperado):
    assert sistema(pregunta) == esperado


@pytest.mark.parametrize("valor, esperado", [
    (200_000_000, 200_000_000),     # el modelo lo pasó a pesos
    (200, 200_000_000),             # el modelo lo dejó como está escrito
    (300, None),                    # inventado
    (18, None),                     # es la tasa
    (5, None),                      # es el plazo
])
def test_monto_en_pesos(valor, esperado):
    pregunta = "¿Cuánto pago por un crédito de 200 millones al 18 % EA a 5 años?"
    assert monto_en_pesos(pregunta, valor) == esperado


@pytest.mark.parametrize("pregunta, tasa, esperado", [
    ("¿2 % mensual cuánto es en efectivo anual?", 2, "EA"),
    ("¿A cuánto equivale una tasa del 24 % NMV en efectiva anual?", 24, "EA"),
    ("¿Cuánto es 18 % EA mensual?", 18, "MV"),
    ("Una tasa efectiva anual del 18 %, ¿cuánto es mensual?", 18, "MV"),
    ("¿Cuánto es 18 % EA en nominal mes vencido?", 18, "NMV"),
    ("¿A cuánto equivale el 2 % mes anticipado?", 2, None),        # sin destino
    ("¿2 % mensual cuánta plata es al año?", 2, "EA"),
    ("¿Con 2 % mensual cuánta plata pago?", 2, None),               # "cuanta" no es TA
])
def test_tipo_destino(pregunta, tasa, esperado):
    assert tipo_destino(pregunta, tasa) == esperado


@pytest.mark.parametrize("pregunta, esperado", [
    ("¿Y si vendo 10 % menos?", ("ingresos", False)),
    ("¿Y si las ventas caen 20 %?", ("ingresos", False)),
    ("¿Y si los costos fijos suben 20 %?", ("costos_fijos", False)),
    ("¿Y si los costos variables suben 10 %?", ("costos_variables", False)),
    ("¿Y si los costos suben 10 %?", ("costos_variables", True)),     # "costos" sin más: supuesto
    ("¿Y si la inversión sale 15 % más cara?", ("inversion", False)),
    ("¿Y si mi tasa de oportunidad sube 20 %?", ("tasa", False)),
    ("¿Qué variable pesa más en mi proyecto?", (None, False)),
])
def test_variable_del_proyecto(pregunta, esperado):
    assert variable_del_proyecto(pregunta) == esperado


@pytest.mark.parametrize("pregunta, esperado", [
    ("¿Y si vendo 10 % menos?", -1),
    ("¿Y si las ventas caen 20 %?", -1),
    ("¿Y si bajan los ingresos un 5 %?", -1),
    ("¿Y si los costos fijos suben 20 %?", 1),
    ("¿Y si la inversión sale 15 % más cara?", 1),
    ("¿Y si los ingresos cambian 10 %?", None),
])
def test_direccion(pregunta, esperado):
    assert direccion(pregunta) == esperado


@pytest.mark.parametrize("pregunta, esperado", [
    ("¿Mi proyecto crea valor con el WACC?", True),
    ("¿Y con el costo de capital de la empresa?", True),
    ("Evalúalo con el costo del capital", True),
    ("¿Me conviene el proyecto?", False),
    ("¿Y si mi tasa de oportunidad es 12 %?", False),
])
def test_pide_evaluar_con_el_wacc(pregunta, esperado):
    assert pide_wacc(pregunta) is esperado
