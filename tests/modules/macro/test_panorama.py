"""Panorama macro con series inventadas: cálculo a mano y hallazgos sin juicios."""
from datetime import date

from pytest import approx

from data_sources.externos.series.modelo import Serie
from modules.macro.panorama import inflacion_anual, panorama_macro


def serie(obs, clave="x") -> Serie:
    return Serie(clave=clave, nombre=clave, fuente=f"BanRep (prueba {clave})", unidad="",
                 frecuencia="", geografia="nacional", consultada=date(2026, 10, 13),
                 observaciones=obs)


def mensual(desde_anio: int, valores: list[float]) -> list[tuple[date, float]]:
    return [(date(desde_anio + k // 12, k % 12 + 1, 1), v) for k, v in enumerate(valores)]


# IPC: 100 todo 2024, 105 todo 2025, 110,25 en 2026 hasta septiembre (5 % anual cada año)
IPC = serie(mensual(2024, [100] * 12 + [105] * 12 + [110.25] * 9), "ipc")
TASA = serie([(date(2025, 10, 10), 9.25), (date(2026, 10, 12), 12.25)], "tasa")
IBR = serie([(date(2026, 10, 9), 11.7)], "ibr")
TRM = serie([(date(2025, 10, 14), 4000.0), (date(2026, 10, 14), 3200.0)], "trm")
PIB = serie([(date(2026, 3, 31), 2.19), (date(2026, 6, 30), 3.52)], "pib")
DESEMPLEO = serie([(date(2025, 8, 31), 8.6), (date(2026, 7, 31), 8.1), (date(2026, 8, 31), 9.36)], "des")


def test_inflacion_anual_del_indice():
    assert abs(inflacion_anual(IPC, date(2026, 9, 1)) - 0.05) < 1e-12
    assert inflacion_anual(IPC, date(2024, 5, 1)) is None          # no hay año anterior


def test_panorama_a_mano():
    r = panorama_macro(IPC, TASA, IBR, TRM, PIB, DESEMPLEO)
    assert abs(r.valor("inflacion_anual") - 0.05) < 1e-12
    assert r.valor("tasa_politica") == approx(0.1225) and r.valor("tasa_politica_previa") == approx(0.0925)
    assert r.valor("trm") == 3200 and abs(r.valor("variacion_anual_trm") + 0.2) < 1e-12
    assert r.valor("crecimiento_pib") == approx(0.0352)
    # Desempleo: contra el mismo mes del año anterior, no contra el mes previo
    assert r.valor("desempleo") == approx(0.0936) and r.valor("desempleo_previo") == approx(0.086)
    assert len(r.fuentes) == 6


def test_hallazgos_describen_sin_calificar():
    texto = " ".join(panorama_macro(IPC, TASA, IBR, TRM, PIB, DESEMPLEO).hallazgos)
    assert "un dólar cuesta 20,0 % menos que un año antes" in texto
    # TRM a la baja: el peso se revaluó (el 7B había escrito "depreciación")
    assert "el peso se revaluó (ganó valor) frente al dólar" in texto
    assert "frente a 8,60 % en agosto de 2025" in texto
    assert "segundo trimestre de 2026" in texto and "no son un pronóstico" in texto
    for palabra in ("bueno", "malo", "preocupante", "favorable"):
        assert palabra not in texto
