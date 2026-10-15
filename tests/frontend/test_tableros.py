"""Tablero del balance: cifras calculadas con Python a partir del hotel de demostración."""
from datetime import date

import pytest

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
    assert t["economia"]["consultada"] == date(2026, 10, 11)      # la serie más vieja del respaldo
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

def test_simulador_de_credito_con_el_ejemplo():
    c = tableros.credito()
    assert c["errores"] == [] and c["v"]["monto"] == "200 millones"
    tarjetas = {t["titulo"]: t["valor"] for t in c["tarjetas"]}
    assert tarjetas["Cuota mensual"] == "$\u00a04.934.680"
    assert tarjetas["Intereses del crédito"] == "$\u00a096.080.819"
    assert [a["anio"] for a in c["anual"]] == [1, 2, 3, 4, 5] and c["anual"][-1]["saldo"] == "$ 0"
    assert c["anual"][0]["pct_interes"] > c["anual"][-1]["pct_interes"]   # el interés pesa menos al final
    assert len(c["cuotas"]) == 60


def test_simulador_de_credito_abono_constante_y_trimestral():
    c = tableros.credito({"monto": "100.000.000", "tasa": "18", "tipo": "EA", "plazo": "2",
                          "unidad": "años", "periodicidad": "trimestral", "sistema": "abono_constante"})
    titulos = [t["titulo"] for t in c["tarjetas"]]
    assert titulos[:2] == ["Primera cuota", "Última cuota"] and len(c["cuotas"]) == 8


@pytest.mark.parametrize("campos, mensaje", [
    ({"monto": ""}, "Escriba el monto"),
    ({"tasa": "abc"}, "La tasa debe ser un número"),
    ({"plazo": "5", "unidad": "meses", "periodicidad": "trimestral"}, "número entero"),
    ({"tipo": "XYZ"}, "Tipo de tasa desconocido"),
])
def test_simulador_de_credito_con_errores(campos, mensaje):
    c = tableros.credito(campos)
    assert any(mensaje in e for e in c["errores"]) and "tarjetas" not in c


def test_conversor_de_tasas_con_el_ejemplo():
    c = tableros.conversor()
    assert c["errores"] == [] and c["v"] == {"tasa": "2", "tipo": "MV"}
    filas = {f["tipo"]: f for f in c["filas"]}
    assert len(filas) == 11 and filas["EA"]["valor"] == "26,82 %"
    assert filas["MV"]["origen"] and not filas["EA"]["origen"]
    assert filas["NMV"]["valor"] == "24,00 %" and "nominal = periódica × 12" in filas["NMV"]["formula"]
    assert c["hallazgos"][0] == "Una tasa de 2 % mensual equivale a 26,82 % efectiva anual."


@pytest.mark.parametrize("campos, mensaje", [
    ({"tasa": "abc"}, "La tasa debe ser un número"), ({"tipo": "XYZ"}, "Tipo de tasa desconocido")])
def test_conversor_de_tasas_con_errores(campos, mensaje):
    c = tableros.conversor(campos)
    assert any(mensaje in e for e in c["errores"]) and "filas" not in c


# --------------------------------------------------------------------------- #
# Proyectos: pestaña "Su proyecto" (flujo de caja libre)
# --------------------------------------------------------------------------- #
def test_flujo_con_el_ejemplo_y_la_senda_del_banrep():
    c = tableros.flujo()
    assert c["errores"] == [] and c["v"]["inversion"] == "100 millones"
    assert "Informe de Política Monetaria" in " ".join(c["fuentes"])
    assert c["inflacion"].startswith(str(date.today().year + 1))


def test_flujo_con_inflacion_fija_da_el_caso_a_mano():
    c = tableros.flujo({**tableros.PROYECTO_EJEMPLO, "inflacion": "3"})
    assert c["anios"] == [0, 1, 2, 3, 4, 5]
    libre = next(f for f in c["filas"] if f["clave"] == "flujo_libre")
    assert libre["valores"][:2] == ["$ -106.180.000", "$ 27.416.117"]
    ingresos = next(f for f in c["filas"] if f["clave"] == "ingresos")
    assert ingresos["valores"][0] == "—"                    # el año 0 no tiene ingresos
    assert c["inflacion"] == "3,0 % fija todos los años"


@pytest.mark.parametrize("campos, mensaje", [
    ({"inversion": "mucho"}, "Escriba la inversión en pesos"),
    ({"horizonte": "0"}, "El horizonte debe estar entre 1 y 30 años."),
    ({"costos_variables": "abc"}, "Costos variables: escriba un porcentaje"),
])
def test_flujo_con_errores(campos, mensaje):
    c = tableros.flujo({**tableros.PROYECTO_EJEMPLO, **campos})
    assert any(mensaje in e for e in c["errores"]) and "filas" not in c


def test_evaluacion_en_la_pestana_con_el_caso_a_mano():
    c = tableros.flujo({**tableros.PROYECTO_EJEMPLO, "inflacion": "0", "tasa_oportunidad": "10"})
    tarjetas = {t["titulo"]: t for t in c["evaluacion"]["tarjetas"]}
    assert list(tarjetas) == ["VPN", "TIR", "TIRM", "Recuperación", "Índice de rentabilidad"]
    assert tarjetas["VPN"]["valor"] == "$ 3.109.400" and tarjetas["VPN"]["detalle"] == "Crea valor"
    assert tarjetas["TIR"]["valor"] == "11,11 %" and tarjetas["Recuperación"]["valor"] == "4,9 años"
    assert c["evaluacion"]["hallazgos"][0].startswith("Con una tasa de oportunidad de 10 %")


def test_evaluacion_que_no_crea_valor_lo_dice_en_palabras():
    c = tableros.flujo({**tableros.PROYECTO_EJEMPLO, "inflacion": "3", "tasa_oportunidad": "15"})
    vpn = c["evaluacion"]["tarjetas"][0]
    assert vpn["detalle"] == "No crea valor" and vpn["valor"].startswith("$ -")
    recuperacion = c["evaluacion"]["tarjetas"][3]
    assert recuperacion["valor"] == "—" and recuperacion["detalle"] == "No se recupera en 5 años"


def test_sin_tasa_de_oportunidad_hay_flujo_pero_no_evaluacion():
    c = tableros.flujo({**tableros.PROYECTO_EJEMPLO, "tasa_oportunidad": ""})
    assert c["errores"] == [] and c["evaluacion"] is None and c["filas"]


# --------------------------------------------------------------------------- #
# Proyectos: pestaña "Sensibilidad"
# --------------------------------------------------------------------------- #
CASO_A_MANO = {**tableros.PROYECTO_EJEMPLO, "inflacion": "0", "tasa_oportunidad": "10"}


def test_sensibilidad_del_caso_a_mano():
    c = tableros.sensibilidad_tab(CASO_A_MANO)
    assert c["errores"] == [] and not c["es_ejemplo"]
    assert [f["nombre"] for f in c["filas"]] == ["Ingresos", "Inversión", "Costos variables",
                                                 "Tasa de oportunidad", "Costos fijos"]
    ingresos = c["filas"][0]
    assert ingresos["vpn"] == ["$ -17.133.401", "$ -7.012.001", "$ 13.230.801", "$ 23.352.201"]
    assert ingresos["critico"].startswith("los ingresos caen 3,1 % (a $ 58.1")
    tasa = c["filas"][3]
    assert tasa["actual"] == "10,00 %" and tasa["critico"] == "la tasa de oportunidad sube a 11,11 %"
    # Barras: la de ingresos es la más larga; la línea de VPN = 0 cae dentro del gráfico
    assert ingresos["barra"]["izquierda"] == 0 and ingresos["barra"]["derecha"] == 100
    assert 0 < c["cero"] < 50


def test_sensibilidad_con_el_ejemplo_lo_dice():
    assert tableros.sensibilidad_tab()["es_ejemplo"]


def test_sensibilidad_sin_tasa_remite_a_su_proyecto():
    c = tableros.sensibilidad_tab({**CASO_A_MANO, "tasa_oportunidad": ""})
    assert any("tasa de oportunidad" in e for e in c["errores"]) and "filas" not in c
