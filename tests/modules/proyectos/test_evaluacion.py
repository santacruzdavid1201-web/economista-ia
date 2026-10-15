"""Evaluación del proyecto: caso calculado a mano (SPEC-evaluacion-proyecto.md)."""
import pytest

from modules.proyectos.evaluacion import evaluar
from modules.proyectos.flujo import Senda, crear_proyecto, flujo_caja
from modules.proyectos.matematica_financiera import vpn

EJEMPLO = dict(nombre="Remodelación", inversion=100_000_000, vida_util=5, horizonte=5,
               ingresos=60_000_000, crecimiento_real=0, costos_variables=0.30,
               costos_fijos=10_000_000, capital_trabajo=0.10, tarifa_renta=0.35)


def evaluacion(tasa: float, tasas_inflacion: list[float] | None = None, **cambios):
    p = crear_proyecto(**{**EJEMPLO, **cambios})
    return evaluar(flujo_caja(p, Senda(tasas_inflacion or [0] * p.horizonte, [])), tasa)


def test_caso_a_mano_sin_inflacion_al_10_por_ciento():
    r = evaluacion(0.10)
    assert r.modulo == "proyectos" and r.analisis == "evaluacion"
    assert r.valor("vpn") == pytest.approx(3_109_400.13, abs=0.01)
    assert r.valor("tir") == pytest.approx(0.1111196823, abs=1e-9)
    assert r.valor("tirm") == pytest.approx(0.1063790556, abs=1e-9)
    assert r.valor("recuperacion") == pytest.approx(4.8518426036, abs=1e-9)
    assert r.valor("indice_rentabilidad") == pytest.approx(1.0293339635, abs=1e-9)
    assert r.hallazgos[0] == ("Con una tasa de oportunidad de 10 % efectiva anual, el proyecto "
                              "crea valor: deja $ 3.109.400 más, en pesos de hoy, que invertir esa "
                              "plata en la alternativa.")
    assert "La TIR es 11,11 %, mayor que la tasa de oportunidad de 10 %." in r.hallazgos
    assert "Recupera la inversión, con su costo de oportunidad, en 4,9 años de 5." in r.hallazgos


def test_no_crea_valor_lo_dice_en_palabras_con_la_cifra_en_positivo():
    r = evaluacion(0.15, [0.03] * 5)
    assert r.valor("vpn") == pytest.approx(-4_174_372, abs=1)
    assert r.hallazgos[0].startswith("Con una tasa de oportunidad de 15 % efectiva anual, el "
                                     "proyecto no crea valor: deja $ 4.174.372 menos")
    assert "La TIR es 13,40 %, menor que la tasa de oportunidad de 15 %." in r.hallazgos
    assert ("No recupera la inversión, con su costo de oportunidad, dentro de los 5 años del "
            "horizonte.") in r.hallazgos


def test_crear_valor_es_criterio_y_no_recomendacion():
    assert any("no una recomendación" in h for h in evaluacion(0.10).hallazgos)


def test_vpn_nominal_igual_a_vpn_real_con_la_tasa_real_de_cada_anio():
    senda = [0.043, 0.03, 0.03, 0.03, 0.03]
    p = crear_proyecto(**EJEMPLO)
    f = flujo_caja(p, Senda(senda, []))
    factor, real = 1.0, 0.0
    for t, fila in enumerate(f.real):
        if t:
            factor *= 1.15 / (1 + senda[t - 1])          # 1 + tasa real del año t
        real += fila.flujo_libre / factor
    assert evaluar(f, 0.15).valor("vpn") == pytest.approx(real)
    assert evaluar(f, 0.15).valor("vpn") == pytest.approx(
        vpn(0.15, [fila.flujo_libre for fila in f.corriente]))


def test_sin_tir_unica_no_hay_hallazgo_de_tir_pero_si_advertencia():
    r = evaluacion(0.10, ingresos=0, costos_fijos=50_000_000)      # todos los flujos negativos
    assert r.valor("tir") is None and r.advertencias
    assert not any(h.startswith("La TIR") for h in r.hallazgos)


def test_supuestos_de_la_tirm_y_del_flujo():
    r = evaluacion(0.10)
    assert any("TIRM" in s and "tasa de oportunidad" in s for s in r.supuestos)
    assert any("sin la financiación" in s for s in r.supuestos)
