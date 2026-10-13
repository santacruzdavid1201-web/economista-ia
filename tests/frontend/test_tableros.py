"""Tablero del balance: cifras calculadas con Python a partir del hotel de demostración."""
from app.demo import contexto_demo
from app.orchestrator.tools_registry import ContextoEmpresa
from frontend import tableros


def test_tablero_balance_con_dos_anios_y_sector():
    t = tableros.balance(contexto_demo())
    tarjetas = {c["titulo"]: c for c in t["tarjetas"]}
    roe = tarjetas["Rentabilidad del patrimonio"]
    assert roe["valor"] == "12,3 %" and roe["cambio"] == "+5,0 puntos frente a 2023"
    assert roe["sector"] == "Mejor que el 74 % de los pares"
    # Sin dirección (liquidez) no se dice "mejor": solo el percentil
    assert tarjetas["Liquidez"]["sector"].startswith("Percentil ")
    assert tarjetas["Riesgo financiero"]["valor"] == "6,88"           # el Z'' es un puntaje
    assert t["altman"]["zona"] == "segura"
    palancas = [(p["nombre"], p["texto"]) for p in t["dupont"]["palancas"]]
    assert palancas[0] == ("Margen neto", "72,3 %") and len(palancas) == 3
    assert t["por_anio"]["anios"] == [2023, 2024]
    # Cada fila del sector ubica banda, mediana y empresa dentro de la barra
    filas = [f for tema in t["sector"]["temas"] for f in tema["filas"]]
    assert filas and all(0 <= f["x_empresa"] <= 100 and 0 <= f["x_mediana"] <= 100 for f in filas)
    assert any("Días de proveedores: no se compara" in a for a in t["sector"]["avisos"])


def test_tablero_con_un_anio_y_sin_referencia():
    ctx = contexto_demo()
    h = ctx.historial.model_copy(update={"periodos": ctx.historial.periodos[-1:]})
    t = tableros.balance(ContextoEmpresa(historial=h, referencia=None))
    assert t["sector"] is None and t["dupont"] is None
    assert all(c["cambio"] is None and c["sector"] is None for c in t["tarjetas"])
    assert t["por_anio"]["anios"] == [2024]


def test_tablero_macro_con_y_sin_empresa():
    t = tableros.macro(contexto_demo())
    titulos = [c["titulo"] for c in t["economia"]["tarjetas"]]
    assert titulos == ["Inflación anual", "Tasa del Banco de la República", "Dólar (TRM)",
                       "Crecimiento del PIB", "Desempleo"]
    assert all(c["linea"] for c in t["economia"]["tarjetas"])
    cifras = dict(t["empresa"]["crecimiento"]["cifras"])
    assert cifras["Crecimiento real de los ingresos (descontada la inflación)"] == "9,3 %"
    filas = {f["escenario"]: f for f in t["empresa"]["tasas"]["filas"]}
    assert filas["Sin cambio de tasa"]["gastos"] == "$ 95.000.000" and filas["Sin cambio de tasa"]["hoy"]
    assert filas["3 puntos más"]["cobertura"] == "3,94 veces"
    assert tableros.macro(None)["empresa"] is None


def test_linea_de_tendencia():
    from datetime import date
    linea = tableros._linea([(date(2026, m, 1), v) for m, v in ((1, 10), (2, 20), (3, 15))])
    assert linea["puntos"] == "0.0,40.0 100.0,4.0 200.0,22.0"     # el máximo arriba (y pequeña)
    assert tableros._linea([(date(2026, 1, 1), 5)]) is None