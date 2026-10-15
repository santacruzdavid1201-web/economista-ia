"""Pronóstico de inflación del Informe de Política Monetaria: se carga a mano cada trimestre."""
import io
from datetime import date
from pathlib import Path

import openpyxl
import pytest

from data_sources.externos import pronostico_banrep as pb
from data_sources.externos.series import catalogo

# Recorte del Excel real de julio de 2026: hoja anual con la fila de años y la del IPC total
RUTA = Path(__file__).parent / "datos" / "ipm_julio_2026.xlsx"
EXCEL = RUTA.read_bytes()
HOY = date(2026, 10, 15)
JULIO = "Informe de Política Monetaria de julio de 2026"


@pytest.fixture(autouse=True)
def respaldo(monkeypatch, tmp_path):
    """Ningún test lee ni escribe las copias versionadas de data/series/."""
    monkeypatch.setattr(catalogo, "RESPALDO", tmp_path)
    return tmp_path


def test_lee_el_ipc_total_de_la_hoja_anual():
    p = pb.desde_excel(EXCEL, 7, 2026, HOY)
    assert p.inflacion[2026] == pytest.approx(0.069) and p.inflacion[2027] == pytest.approx(0.043)
    assert p.inflacion[2010] == pytest.approx(0.032)
    assert p.informe == JULIO and p.fecha_informe == date(2026, 7, 1)
    assert "Banco de la República" in p.fuente and JULIO in p.fuente


def test_formato_desconocido_es_error_util():
    vacio = io.BytesIO()
    openpyxl.Workbook().save(vacio)
    with pytest.raises(pb.ErrorPronostico, match="formato"):
        pb.desde_excel(vacio.getvalue(), 7, 2026, HOY)


@pytest.mark.parametrize("nombre, esperado", [
    ("IPM-julio-2026-var-pron-macro.xlsx", (7, 2026)),
    ("IPM-octubre-2026-var-pron-macro.xlsx", (10, 2026)),
    ("variables.xlsx", None),
])
def test_mes_y_anio_del_nombre_del_archivo(nombre, esperado):
    assert pb.informe_del_nombre(nombre) == esperado


def test_cargar_guarda_la_copia_y_pronostico_la_lee(respaldo):
    pb.cargar(RUTA, 7, 2026, HOY)
    assert (respaldo / "pronostico_inflacion.json").exists()
    p = pb.pronostico(HOY)
    assert p.informe == JULIO and p.inflacion[2027] == pytest.approx(0.043) and p.advertencias == []


def test_informe_de_mas_de_cuatro_meses_avisa(respaldo):
    pb.cargar(RUTA, 7, 2026, HOY)
    p = pb.pronostico(date(2026, 11, 5))
    assert p.advertencias == [f"El pronóstico de inflación es del {JULIO}; puede haber uno más "
                              "reciente del Banco de la República."]


def test_sin_copia_es_error_util():
    with pytest.raises(pb.ErrorPronostico, match="python -m data_sources.externos.pronostico_banrep"):
        pb.pronostico(HOY)
