"""Indicadores hoteleros por día, semana o mes (SPEC-series-empresa.md)."""
from datetime import date, timedelta

import pandas as pd
import pytest

from data_sources.empresa.pms_simulado import parametros, simular_pms
from modules.econometria.indicadores import agregar


def serie(desde: date, disponibles: list[int], vendidas: list[int], adr: list[float]) -> pd.DataFrame:
    """Como la devuelve el almacén: índice de fechas y las columnas del PMS."""
    fechas = pd.DatetimeIndex([desde + timedelta(days=k) for k in range(len(vendidas))],
                              name="fecha")
    return pd.DataFrame({"habitaciones_disponibles": disponibles,
                         "habitaciones_vendidas": vendidas,
                         "ingresos_habitaciones": [v * a for v, a in zip(vendidas, adr)]},
                        index=fechas)


SEMANA = serie(date(2026, 3, 2), [45, 45, 43, 45, 45, 45, 45], [18, 20, 21, 22, 25, 30, 12],
               [180_000] * 4 + [200_000] * 2 + [170_000])


def test_semana_a_mano_con_un_dia_en_mantenimiento():
    s = agregar(SEMANA, "semanal")
    assert len(s) == 1 and s.index[0] == pd.Timestamp("2026-03-02")      # empieza el lunes
    fila = s.iloc[0]
    assert (fila.habitaciones_disponibles, fila.habitaciones_vendidas) == (313, 148)
    assert fila.ingresos_habitaciones == pytest.approx(27_620_000)
    assert fila.ocupacion == pytest.approx(148 / 313)                  # 47,28 %: ponderada
    assert fila.adr == pytest.approx(27_620_000 / 148)                 # $ 186.622
    assert fila.revpar == pytest.approx(fila.ocupacion * fila.adr)     # $ 88.243
    assert fila.completo and fila.dias == 7


def test_el_mes_incompleto_queda_marcado():
    s = agregar(serie(date(2026, 3, 1), [45] * 10, [20] * 10, [180_000] * 10), "mensual")
    assert s.index[0] == pd.Timestamp("2026-03-01")
    assert not s.iloc[0].completo and s.iloc[0].dias == 10


def test_diaria_y_dia_sin_ventas_sin_dividir_por_cero():
    s = agregar(serie(date(2026, 3, 1), [45, 45], [0, 9], [0, 180_000]), "diaria")
    assert pd.isna(s.iloc[0].adr) and s.iloc[0].ocupacion == 0 and s.iloc[0].revpar == 0
    assert s.iloc[1].adr == pytest.approx(180_000) and s["completo"].all()


def test_el_simulado_por_mes_tiene_el_pico_del_carnaval_en_enero():
    sim = simular_pms(parametros(), semilla=1)
    s = agregar(sim.set_index(pd.DatetimeIndex(sim.pop("fecha"), name="fecha")), "mensual")
    assert len(s) == 45 and s["completo"].all()                       # ene-2023 a sep-2026
    por_anio = s.groupby(s.index.year)["ocupacion"].idxmax()
    assert all(m.month == 1 for m in por_anio)


def test_frecuencia_desconocida():
    with pytest.raises(ValueError, match="diaria, semanal o mensual"):
        agregar(SEMANA, "anual")
