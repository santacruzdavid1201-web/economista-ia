"""Calendario de la demanda hotelera (SPEC-calendario.md): casos verificados a mano."""
from datetime import date

import pytest

from modules.econometria.calendario import ErrorCalendario, calendario, festivos


# --------------------------------------------------------------------------- #
# Festivos
# --------------------------------------------------------------------------- #
def test_los_19_festivos_de_2026_conciliados_por_el_usuario():
    esperados = ["01/01", "12/01", "23/03", "02/04", "03/04", "01/05", "18/05", "08/06",
                 "15/06", "29/06", "13/07", "20/07", "07/08", "17/08", "12/10", "02/11",
                 "16/11", "08/12", "25/12"]
    assert [f"{d:%d/%m}" for d in festivos(2026)] == esperados


def test_el_9_de_julio_rige_desde_2026_corrido_al_lunes():
    assert festivos(2026)[date(2026, 7, 13)] == "Virgen de Chiquinquirá"   # Ley 2578 de 2026
    assert "Virgen de Chiquinquirá" not in festivos(2025).values()


def test_2025_tiene_18_festivos_en_17_dias():
    f = festivos(2025)
    assert len(f) == 17
    assert "San Pedro y San Pablo" in f[date(2025, 6, 30)]
    assert "Sagrado Corazón" in f[date(2025, 6, 30)]
    assert f[date(2025, 4, 18)] == "Viernes Santo"                         # Pascua: 20/4
    assert f[date(2025, 1, 6)] == "Reyes Magos"                            # ya era lunes


@pytest.mark.parametrize("anio", [1983, 2101])
def test_anio_fuera_de_la_ley_emiliani(anio):
    with pytest.raises(ErrorCalendario, match="1984"):
        festivos(anio)


# --------------------------------------------------------------------------- #
# Calendario diario
# --------------------------------------------------------------------------- #
def dia(c, texto: str):
    return c.loc[texto]


def test_puente_y_vispera_de_un_lunes_festivo():
    c = calendario(date(2026, 3, 19), date(2026, 3, 24))                  # San José: lunes 23
    assert [dia(c, f"2026-03-{d}").puente for d in (20, 21, 22, 23, 24)] == [
        False, True, True, True, False]
    assert dia(c, "2026-03-22").vispera_festivo and not dia(c, "2026-03-21").vispera_festivo
    assert dia(c, "2026-03-23").festivo and dia(c, "2026-03-23").nombre_festivo == "San José"
    assert dia(c, "2026-03-23").dia_semana == 0                           # lunes


def test_puente_de_un_viernes_festivo():
    c = calendario(date(2026, 4, 29), date(2026, 5, 4))                   # 1 de mayo: viernes
    assert [bool(c.loc[f"2026-{f}"].puente) for f in ("04-30", "05-01", "05-02", "05-03",
                                                     "05-04")] == [False, True, True, True, False]
    assert dia(c, "2026-04-30").vispera_festivo


def test_semana_santa_2026():
    c = calendario(date(2026, 3, 28), date(2026, 4, 6))
    assert c["semana_santa"].tolist() == [False] + [True] * 8 + [False]   # 29/3 al 5/4


def test_carnaval_en_pasto_dos_anios():
    c = calendario(date(2025, 1, 1), date(2026, 12, 31), "Pasto")
    assert len(c) == 730
    carnaval = c.index[c["evento_carnaval"]]
    assert [f"{d:%d/%m/%Y}" for d in carnaval] == [f"{d:02d}/01/{a}" for a in (2025, 2026)
                                                   for d in range(2, 8)]
    assert list(c.index[c["evento_carnaval_central"]].day) == [5, 6, 5, 6]


@pytest.mark.parametrize("ciudad", ["pasto", "PASTO"])
def test_la_ciudad_se_busca_sin_mayusculas(ciudad):
    assert "evento_carnaval" in calendario(date(2026, 1, 1), date(2026, 1, 10), ciudad)


@pytest.mark.parametrize("ciudad", [None, "Medellín", "Ciudad Inventada"])
def test_sin_ciudad_o_sin_eventos_no_hay_columnas_de_evento(ciudad):
    c = calendario(date(2026, 1, 1), date(2026, 1, 10), ciudad)
    assert not [col for col in c.columns if col.startswith("evento_")]
    assert list(c.columns) == ["dia_semana", "festivo", "nombre_festivo", "vispera_festivo",
                               "puente", "semana_santa"]


def test_bordes_del_rango_usan_los_festivos_de_los_anios_vecinos():
    # El 31/12/2025 es víspera del 1/1/2026, aunque el rango termine ese día
    assert calendario(date(2025, 12, 31), date(2025, 12, 31))["vispera_festivo"].iloc[0]
    # El domingo 11/1/2026 es puente del lunes 12 (Reyes), aunque el rango empiece ahí
    assert calendario(date(2026, 1, 11), date(2026, 1, 11))["puente"].iloc[0]


def test_rango_invertido():
    with pytest.raises(ErrorCalendario, match="invertido"):
        calendario(date(2026, 2, 1), date(2026, 1, 1))
