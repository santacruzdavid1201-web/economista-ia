"""Calendario de la demanda hotelera (SPEC-calendario.md): casos verificados a mano."""
from datetime import date

import pytest

from modules.econometria.calendario import ErrorCalendario, festivos


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
