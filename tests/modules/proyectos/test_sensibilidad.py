"""Sensibilidad del proyecto: caso calculado a mano (SPEC-sensibilidad-proyecto.md)."""
import pytest

from modules.proyectos.flujo import Senda, crear_proyecto, flujo_caja
from modules.proyectos.matematica_financiera import tir
from modules.proyectos.sensibilidad import POR_CLAVE, escenario, movimiento, sensibilidad

EJEMPLO = dict(nombre="Remodelación", inversion=100_000_000, vida_util=5, horizonte=5,
               ingresos=60_000_000, crecimiento_real=0, costos_variables=0.30,
               costos_fijos=10_000_000, capital_trabajo=0.10, tarifa_renta=0.35)
SIN_INFLACION = Senda([0] * 5, [])


def tornado(tasa: float = 0.10, **cambios):
    return sensibilidad(crear_proyecto(**{**EJEMPLO, **cambios}), SIN_INFLACION, tasa)


def test_caso_a_mano_ordenado_de_mayor_a_menor_efecto():
    s = tornado()
    assert s.vpn_base == pytest.approx(3_109_400.13, abs=0.01)
    assert [f.variable for f in s.filas] == ["ingresos", "inversion", "costos_variables", "tasa",
                                             "costos_fijos"]
    assert s.filas[0].vpn == pytest.approx(
        {-0.2: -17_133_401, -0.1: -7_012_001, 0.1: 13_230_801, 0.2: 23_352_201}, abs=1)
    assert {f.variable: f.critico for f in s.filas} == pytest.approx(
        {"ingresos": -0.0307, "inversion": 0.0423, "costos_variables": 0.0701, "tasa": 0.1112,
         "costos_fijos": 0.1262}, abs=1e-4)


def test_la_tasa_critica_es_la_tir():
    proyecto = crear_proyecto(**EJEMPLO)
    la_tir, _ = tir([f.flujo_libre for f in flujo_caja(proyecto, SIN_INFLACION).corriente])
    tasa = next(f for f in tornado().filas if f.variable == "tasa")
    assert tasa.valor_critico == pytest.approx(la_tir, abs=1e-6)


def test_hallazgos_en_palabras_y_con_pocas_cifras():
    s = tornado()
    assert s.resultado.hallazgos[0] == (
        "Lo que más mueve el VPN son los ingresos: con un 10 % menos, el proyecto dejaría "
        "$ 7.012.001 menos que la alternativa; con un 10 % más, dejaría $ 13.230.801 más.")
    assert s.resultado.hallazgos[1] == (
        "El proyecto deja de crear valor si los ingresos caen 3,1 % o si la inversión sube 4,2 %, "
        "cada una por separado.")
    assert [i.clave for i in s.resultado.indicadores] == ["vpn"]          # el tornado va aparte


def test_las_tasas_se_dicen_en_nivel_y_no_en_cambio_relativo():
    assert (movimiento(POR_CLAVE["costos_variables"], 0.0701, 0.3210)
            == "los costos variables suben a 32,10 % de los ingresos")
    assert movimiento(POR_CLAVE["tasa"], 0.1112, 0.1111) == "la tasa de oportunidad sube a 11,11 %"
    assert movimiento(POR_CLAVE["ingresos"], -0.0307) == "los ingresos caen 3,1 %"


def test_con_vpn_negativo_dice_cuanto_mejorar():
    s = tornado(tasa=0.15)
    assert s.vpn_base < 0
    assert s.resultado.hallazgos[1].startswith("Para que el proyecto cree valor, los ingresos "
                                                "tendrían que subir")


def test_sin_cruce_en_el_rango_no_hay_valor_critico():
    # Con ingresos enormes, ni triplicar los costos fijos deja el VPN en cero
    fijos = next(f for f in tornado(ingresos=600_000_000).filas if f.variable == "costos_fijos")
    assert fijos.critico is None and fijos.valor_critico is None


def test_supuesto_de_una_variable_a_la_vez():
    assert any("Cada variable se mueve sola" in s for s in tornado().resultado.supuestos)


# --------------------------------------------------------------------------- #
# Escenario puntual (el chat: "¿y si vendo 10 % menos?")
# --------------------------------------------------------------------------- #
def test_escenario_que_deja_de_crear_valor():
    r = escenario(crear_proyecto(**EJEMPLO), SIN_INFLACION, 0.10, "ingresos", -0.10)
    assert r.valor("vpn") == pytest.approx(3_109_400.13, abs=0.01)
    assert r.valor("vpn_escenario") == pytest.approx(-7_012_001, abs=1)
    assert r.hallazgos[0] == ("Si los ingresos caen 10 %, el proyecto deja de crear valor: "
                              "dejaría $ 7.012.001 menos que la alternativa (con los datos "
                              "actuales, $ 3.109.400 más).")


@pytest.mark.parametrize("variable, cambio, estado", [
    ("costos_fijos", 0.10, "sigue creando valor"),
    ("ingresos", 0.10, "sigue creando valor"),
])
def test_escenario_que_sigue_creando_valor(variable, cambio, estado):
    r = escenario(crear_proyecto(**EJEMPLO), SIN_INFLACION, 0.10, variable, cambio)
    assert f"el proyecto {estado}" in r.hallazgos[0]


def test_escenario_desde_un_vpn_negativo():
    p = crear_proyecto(**EJEMPLO)
    assert "pasa a crear valor" in escenario(p, SIN_INFLACION, 0.15, "ingresos", 0.20).hallazgos[0]
    assert "sigue sin crear valor" in escenario(p, SIN_INFLACION, 0.15, "ingresos", -0.10).hallazgos[0]
