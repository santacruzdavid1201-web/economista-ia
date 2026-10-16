"""Lectura del proyecto que escribe el usuario: la usan el tablero y el chat. Sin red."""
from datetime import date

import pytest

from app.orchestrator.proyecto import PROYECTO_EJEMPLO, leer_proyecto
from data_sources.externos.pronostico_banrep import ErrorPronostico, Pronostico
from data_sources.externos.series.modelo import Serie
from modules.proyectos.flujo import ErrorProyecto

HOY = date(2026, 10, 15)


def meta(variable, geografia="nacional", desde=None, hoy=None):
    return Serie(clave="meta_inflacion_nacional", nombre="Meta de inflación", fuente="BanRep 853",
                 unidad="Porcentaje", frecuencia="anual", geografia="nacional",
                 consultada=HOY, observaciones=[(date(2026, 12, 31), 3.0)])


def pronostico(hoy=None):
    return Pronostico(informe="Informe de julio", fecha_informe=date(2026, 7, 1), fuente="IPM julio",
                      consultada=HOY, inflacion={2026: 0.069, 2027: 0.043})


def sin_pronostico(hoy=None):
    raise ErrorPronostico("no hay")


def leer(**cambios):
    return leer_proyecto({**PROYECTO_EJEMPLO, **cambios}, HOY, serie=meta, pronostico=pronostico)


def test_el_ejemplo_con_la_senda_del_banrep():
    p = leer()
    assert p.proyecto.inversion == 100_000_000 and p.proyecto.costos_variables == pytest.approx(0.30)
    assert p.senda.tasas == [0.043, 0.03, 0.03, 0.03, 0.03] and not p.fija
    assert p.tasa == pytest.approx(0.15)
    assert p.fuentes == ["IPM julio", "BanRep 853"]


def test_inflacion_fija_del_usuario():
    p = leer(inflacion="3")
    assert p.senda.tasas == [0.03] * 5 and p.fija and p.fuentes == []


def test_sin_pronostico_cargado_usa_la_meta():
    p = leer_proyecto(PROYECTO_EJEMPLO, HOY, serie=meta, pronostico=sin_pronostico)
    assert p.senda.tasas == [0.03] * 5 and p.fuentes == ["BanRep 853"]


def test_tasa_de_oportunidad_vacia_deja_el_flujo_sin_evaluar():
    assert leer(tasa_oportunidad="").tasa is None


def test_el_tipo_de_tasa_es_nominal_por_defecto_y_se_puede_elegir():
    assert leer().tipo == "nominal"
    assert leer(tasa_tipo="").tipo == "nominal"          # proyectos guardados antes del campo
    assert leer(tasa_tipo="real").tipo == "real" and leer(tasa_tipo="wacc").tipo == "wacc"


@pytest.mark.parametrize("cambio, mensaje", [
    ({"tasa_oportunidad": "abc"}, "Tasa de oportunidad: escriba un porcentaje, por ejemplo 30."),
    ({"tasa_oportunidad": "150"}, "La tasa de oportunidad debe estar entre 0 % y 100 %."),
    ({"tasa_tipo": "mensual"}, "Tipo de tasa: elija nominal, real o el WACC de la empresa."),
    ({"inversion": "mucho"}, "Escriba la inversión en pesos, por ejemplo 100 millones o 100.000.000."),
    ({"horizonte": "0"}, "El horizonte debe estar entre 1 y 30 años."),
])
def test_errores_con_mensajes_utiles(cambio, mensaje):
    with pytest.raises(ErrorProyecto) as e:
        leer(**cambio)
    assert mensaje in e.value.mensajes
