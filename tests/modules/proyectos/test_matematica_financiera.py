"""Matemática financiera: casos calculados a mano (SPEC-matematica-financiera.md)."""
import pytest

from modules.proyectos.matematica_financiera import (
    TIPOS,
    ErrorTasa,
    a_periodica,
    convertir,
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
