"""Lectura del proyecto que escribe el usuario: la usan el tablero y el chat. Sin red."""
from datetime import date

import pytest

from app.orchestrator.proyecto import (
    PROYECTO_EJEMPLO,
    costo_capital_de,
    leer_proyecto,
    parametros_costo_capital,
)
from data_sources.externos.pronostico_banrep import ErrorPronostico, Pronostico
from data_sources.externos.series.modelo import Serie
from data_sources.externos.series.catalogo import ErrorSerie
from modules.proyectos.flujo import ErrorProyecto
from modules.proyectos.wacc import Parametros, costo_capital
from tests.conftest import hacer_historial

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


# --------------------------------------------------------------------------- #
# Costo de capital con los datos del día (tablero y chat)
# --------------------------------------------------------------------------- #
TES = Serie(clave="tes_uvr_10_nacional", nombre="TES UVR", fuente="BanRep 15277", unidad="%",
            frecuencia="diaria", geografia="nacional", consultada=HOY,
            observaciones=[(date(2026, 10, 9), 6.74)])
IPC = Serie(clave="ipc_nacional", nombre="IPC", fuente="BanRep 15000", unidad="Indice",
            frecuencia="mensual", geografia="nacional", consultada=HOY,
            observaciones=[(date(2023, 12, 31), 100.0), (date(2024, 12, 31), 105.1)])
PARAMETROS = Parametros(1.0, 0.0187, 0.0708, "Damodaran (prueba)", "Hotel/Gaming")


def series(variable, geografia="nacional", desde=None, hoy=None):
    return {"meta_inflacion": meta(variable), "tes_uvr_10": TES, "ipc": IPC}[variable]


def test_costo_capital_con_la_empresa_usa_la_senda_del_banrep():
    h = hacer_historial()
    r = costo_capital_de(h, HOY, 0.35, serie=series, pronostico=pronostico, parametros=PARAMETROS)
    esperado = costo_capital(TES, PARAMETROS, 0.35, 0.043, h, ipc=IPC)     # π₁ = 2027: 4,3 %
    assert r.valor("wacc") == pytest.approx(esperado.valor("wacc"))
    assert r.valor("wacc_nominal") == pytest.approx(esperado.valor("wacc_nominal"))
    assert "IPM julio" in r.fuentes and any("BanRep 15277" in f for f in r.fuentes)


def test_costo_capital_sin_empresa_con_los_parametros_del_anio():
    r = costo_capital_de(None, HOY, 0.35, serie=series, pronostico=pronostico)
    assert r.valor("costo_activos") == pytest.approx(0.0674 - 0.0187 + 0.58 * 0.0708)


def test_parametros_de_damodaran_escritos_a_mano():
    p = parametros_costo_capital()
    assert (p.beta_sin_deuda, p.spread, p.prima_total) == (0.58, 0.0187, 0.0708)
    assert "Damodaran" in p.fuente and "2026" in p.fuente and p.sector == "Hotel/Gaming"


def test_costo_capital_sin_tes_lo_dice():
    def sin_tes(variable, geografia="nacional", desde=None, hoy=None):
        if variable == "tes_uvr_10":
            raise ErrorSerie("No se pudo descargar la serie tes_uvr_10_nacional.")
        return series(variable)
    with pytest.raises(ErrorSerie, match="tes_uvr_10"):
        costo_capital_de(None, HOY, 0.35, serie=sin_tes, pronostico=pronostico)
