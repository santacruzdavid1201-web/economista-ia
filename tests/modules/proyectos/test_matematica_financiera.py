"""Matemática financiera: casos calculados a mano (SPEC-matematica-financiera.md)."""
import pytest

from modules.proyectos.matematica_financiera import (
    TIPOS,
    ErrorCredito,
    ErrorTasa,
    a_periodica,
    amortizacion,
    convertir_tasa,
    convertir,
    indice_rentabilidad,
    recuperacion_descontada,
    simular_credito,
    tir,
    tirm,
    valor_anual_equivalente,
    vpn,
)


# --------------------------------------------------------------------------- #
# Tasas equivalentes
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tasa, desde, hacia, esperado", [
    (0.02, "MV", "EA", 0.2682417945625455),          # 2 % mensual
    (0.24, "NMV", "EA", 0.2682417945625455),         # 24 % NMV = 2 % mensual
    (0.18, "EA", "MV", 0.01388843034840992),         # 18 % EA → 1,3888 % mensual
    (0.18, "EA", "NMV", 0.16666116418091903),        # … = 16,67 % NMV
    (0.02, "MA", "MV", 0.02 / 0.98),                 # 2 % mes anticipado → 2,0408 % vencido
    (0.24, "NMA", "EA", 0.27434521242337717),        # 24 % NMA
    (0.12, "NTV", "TV", 0.03),
    (0.03, "TA", "TV", 0.03 / 0.97),
])
def test_casos_a_mano(tasa, desde, hacia, esperado):
    assert convertir(tasa, desde, hacia) == pytest.approx(esperado, abs=1e-12)


@pytest.mark.parametrize("desde", list(TIPOS))
@pytest.mark.parametrize("hacia", list(TIPOS))
def test_ida_y_vuelta(desde, hacia):
    assert convertir(convertir(0.15, desde, hacia), hacia, desde) == pytest.approx(0.15, abs=1e-12)


def test_a_periodica_da_tasa_y_periodos():
    assert a_periodica(0.24, "NMV") == pytest.approx((0.02, 12))
    assert a_periodica(0.18, "EA") == (0.18, 1)


def test_tipo_desconocido_dice_cuales_hay():
    with pytest.raises(ErrorTasa, match="NMV"):
        convertir(0.1, "XYZ", "EA")


@pytest.mark.parametrize("tasa, tipo", [(1.0, "MA"), (12.0, "NMA")])
def test_anticipada_de_100_por_ciento_en_el_periodo_no_tiene_equivalente(tasa, tipo):
    with pytest.raises(ErrorTasa, match="anticipada"):
        a_periodica(tasa, tipo)


def test_tasa_de_menos_100_por_ciento_no_es_valida():
    with pytest.raises(ErrorTasa, match="mayor que -100"):
        a_periodica(-1.0, "EA")


# --------------------------------------------------------------------------- #
# Indicadores de proyectos
# --------------------------------------------------------------------------- #
FLUJOS = [-1000, 300, 400, 500, 200]


def test_vpn():
    assert vpn(0.10, FLUJOS) == pytest.approx(115.56587664776976, abs=1e-9)


def test_tir_unica():
    valor, avisos = tir(FLUJOS)
    assert valor == pytest.approx(0.15322137877181538, abs=1e-9)
    assert avisos == [] and vpn(valor, FLUJOS) == pytest.approx(0, abs=1e-6)


def test_dos_tir_no_dan_un_numero_y_las_nombra():
    valor, avisos = tir([-100, 230, -132])          # VPN = 0 al 10 % y al 20 %
    assert valor is None
    assert "10,00 %" in avisos[0] and "20,00 %" in avisos[0] and "TIRM" in avisos[0]


def test_sin_cambio_de_signo_no_hay_tir():
    valor, avisos = tir([100, 50, 20])
    assert valor is None and "no hay TIR" in avisos[0]


def test_tirm_reinvierte_a_la_tasa_de_descuento():
    vf = 300 * 1.1 ** 3 + 400 * 1.1 ** 2 + 500 * 1.1 + 200      # 1.633,3
    assert tirm(0.10, FLUJOS) == pytest.approx((vf / 1000) ** 0.25 - 1, abs=1e-12)
    assert tirm(0.10, [100, 50]) is None                         # sin inversión


def test_recuperacion_descontada_interpola_dentro_del_anio():
    acumulado_3 = -1000 + 300 / 1.1 + 400 / 1.1 ** 2 + 500 / 1.1 ** 3      # -21,04
    assert recuperacion_descontada(0.10, FLUJOS) == pytest.approx(
        3 + -acumulado_3 / (200 / 1.1 ** 4), abs=1e-12)                      # 3,15 años
    assert recuperacion_descontada(0.10, [-1000, 100, 100]) is None


def test_indice_de_rentabilidad():
    assert indice_rentabilidad(0.10, FLUJOS) == pytest.approx(1 + 115.56587664776976 / 1000)
    assert indice_rentabilidad(0.10, [0, 100]) is None


def test_valor_anual_equivalente():
    assert valor_anual_equivalente(0.10, FLUJOS) == pytest.approx(
        115.56587664776976 * 0.10 / (1 - 1.1 ** -4))
    assert valor_anual_equivalente(0, FLUJOS) == pytest.approx(400 / 4)


# --------------------------------------------------------------------------- #
# Amortización
# --------------------------------------------------------------------------- #
MENSUAL_18_EA = 1.18 ** (1 / 12) - 1


def _cuadra(tabla, monto, i):
    assert sum(c.abono for c in tabla) == pytest.approx(monto, abs=1)
    assert abs(tabla[-1].saldo_final) < 1
    for c in tabla:
        assert c.interes == pytest.approx(c.saldo_inicial * i)
        assert c.cuota == pytest.approx(c.interes + c.abono)


def test_cuota_fija():
    tabla = amortizacion(200_000_000, MENSUAL_18_EA, 60, "cuota_fija")
    assert len(tabla) == 60 and tabla[0].periodo == 1
    assert {round(c.cuota, 2) for c in tabla} == {4_934_680.31}
    assert sum(c.interes for c in tabla) == pytest.approx(96_080_818.85, abs=0.01)
    _cuadra(tabla, 200_000_000, MENSUAL_18_EA)


def test_abono_constante():
    tabla = amortizacion(200_000_000, MENSUAL_18_EA, 60, "abono_constante")
    assert tabla[0].cuota == pytest.approx(6_111_019.40, abs=0.01)
    assert tabla[-1].cuota == pytest.approx(3_379_628.10, abs=0.01)
    assert sum(c.interes for c in tabla) == pytest.approx(84_719_425.13, abs=0.01)
    _cuadra(tabla, 200_000_000, MENSUAL_18_EA)


def test_tasa_cero_reparte_el_monto():
    assert {c.cuota for c in amortizacion(1_200, 0, 12, "cuota_fija")} == {100}


@pytest.mark.parametrize("monto, n, sistema, mensaje", [
    (0, 12, "cuota_fija", "monto"),
    (1_000, 0, "cuota_fija", "al menos una cuota"),
    (1_000, 12, "aleman", "Sistema"),
])
def test_entradas_invalidas(monto, n, sistema, mensaje):
    with pytest.raises(ErrorCredito, match=mensaje):
        amortizacion(monto, 0.01, n, sistema)


# --------------------------------------------------------------------------- #
# Simulador de crédito (análisis para el chat y el tablero)
# --------------------------------------------------------------------------- #
def test_simular_credito_cuota_fija():
    r = simular_credito(200_000_000, 0.18, "EA", 60)
    assert r.modulo == "proyectos" and r.analisis == "credito"
    assert r.valor("cuota") == pytest.approx(4_934_680.31, abs=0.01)
    assert r.valor("intereses_totales") == pytest.approx(96_080_818.85, abs=0.01)
    assert r.valor("total_pagado") == pytest.approx(296_080_818.85, abs=0.01)
    assert r.valor("proporcion_intereses") == pytest.approx(0.4804, abs=1e-4)
    assert r.valor("tasa_periodica") == pytest.approx(MENSUAL_18_EA)
    assert r.hallazgos == [
        "Con una tasa de 18 % efectiva anual (1,39 % mensual), un crédito de "
        "$ 200.000.000 a 60 cuotas mensuales tiene una cuota fija de $ 4.934.680.",
        "En total pagaría $ 96.080.819 de intereses, el 48,0 % del monto prestado."]
    assert any("seguros" in s for s in r.supuestos)


def test_simular_credito_con_tasa_nominal_dice_su_equivalente_efectiva():
    r = simular_credito(200_000_000, 0.24, "NMV", 60)
    assert r.hallazgos[0] == ("La tasa de 24 % nominal mes vencido equivale a 26,82 % "
                              "efectiva anual: la nominal no cuenta el interés sobre los intereses.")
    assert r.valor("tasa_periodica") == pytest.approx(0.02)


def test_simular_credito_abono_constante():
    r = simular_credito(200_000_000, 0.18, "EA", 60, sistema="abono_constante")
    assert r.valor("primera_cuota") == pytest.approx(6_111_019.40, abs=0.01)
    assert r.valor("ultima_cuota") == pytest.approx(3_379_628.10, abs=0.01)
    assert "la primera cuota es de $ 6.111.019 y la última de $ 3.379.628" in r.hallazgos[0]
    assert "saldo cada vez menor" in r.hallazgos[0]


def test_simular_credito_trimestral():
    r = simular_credito(100_000_000, 0.18, "EA", 20, periodicidad="trimestral")
    assert r.valor("tasa_periodica") == pytest.approx(1.18 ** 0.25 - 1)
    assert "a 20 cuotas trimestrales" in r.hallazgos[0] and "trimestral)" in r.hallazgos[0]


def test_simular_credito_pasa_los_supuestos_de_la_lectura():
    r = simular_credito(1_000_000, 0.18, "EA", 12, supuestos=["Se asumió algo."])
    assert r.supuestos[0] == "Se asumió algo."


# --------------------------------------------------------------------------- #
# Conversor de tasas
# --------------------------------------------------------------------------- #
def test_convertir_tasa_mensual_a_efectiva():
    r = convertir_tasa(0.02, "MV", "EA")
    assert r.modulo == "proyectos" and r.analisis == "conversion_tasa"
    assert r.valor("tasa_convertida") == pytest.approx(0.2682417945625455)
    assert r.hallazgos == ["Una tasa de 2 % mensual equivale a 26,82 % efectiva anual."]
    assert "(1 + i)^(12/1) − 1" in r.indicadores[0].formula


def test_convertir_tasa_nominal_explica_la_diferencia():
    r = convertir_tasa(0.24, "NMV", "EA")
    assert r.hallazgos[0] == "Una tasa de 24 % nominal mes vencido equivale a 26,82 % efectiva anual."
    assert "la nominal no cuenta el interés sobre los intereses" in r.hallazgos[1]
    assert r.indicadores[0].formula.startswith("periódica = nominal / 12")


def test_convertir_tasa_anticipada_explica_la_diferencia():
    r = convertir_tasa(0.02, "MA", "MV")
    assert r.valor("tasa_convertida") == pytest.approx(0.02 / 0.98)
    assert "al inicio del periodo" in r.hallazgos[1]


def test_la_tasa_del_usuario_va_como_la_escribio():
    # El 7B la repite así ("1,5 %"); con "1,50 %" no estaría en el desplegable
    r = simular_credito(10_000_000, 0.015, "MV", 12)
    assert r.hallazgos[0].startswith("La tasa de 1,5 % mensual equivale a ")
