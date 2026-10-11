"""
Series del Banco de la República desde SUAMECA.

La API es la que usa el portal por dentro; no está documentada como servicio
público y puede cambiar sin aviso. Por eso: consultas en serie (en paralelo
el servidor rechaza las conexiones), caché en el catálogo y verificación del
IPC nacional contra el anexo del DANE.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import requests

from data_sources.externos.series.modelo import Serie

URL = ("https://suameca.banrep.gov.co/estadisticas-economicas-back/rest/"
       "estadisticaEconomicaRestService/consultaInformacionSerie")
TIMEOUT = 60
EPOCH = date(1970, 1, 1)
# ponytail: cadena fija de DigiCert porque el servidor no envía el intermedio;
# si el BanRep cambia de certificado, actualizar el .pem (o usar truststore).
CADENA = Path(__file__).with_name("suameca_cadena.pem")


def descargar(id_serie: int) -> dict:
    """Respuesta cruda de SUAMECA para una serie (metadatos e historia)."""
    r = requests.get(URL, params={"idSerie": id_serie}, timeout=TIMEOUT, verify=CADENA)
    r.raise_for_status()
    datos = r.json()
    if not datos:
        raise ValueError(f"SUAMECA no devolvió datos para la serie {id_serie}.")
    return datos[0]


def a_fecha(epoch_ms: int) -> date:
    # datetime.fromtimestamp falla en Windows con fechas anteriores a 1970
    return EPOCH + timedelta(milliseconds=epoch_ms)


def desde_suameca(respuesta: dict, clave: str, geografia: str, consultada: date) -> Serie:
    """JSON de consultaInformacionSerie → Serie. Sin red: se prueba con fixtures."""
    return Serie(
        clave=clave,
        nombre=respuesta["nombre"],
        fuente=(f"Banco de la República, SUAMECA (serie {respuesta['id']}), "
                f"con datos de {respuesta['fuente']}"),
        unidad=respuesta["unidad"],
        frecuencia=respuesta["descripcionPeriodicidad"].lower(),
        geografia=geografia,
        consultada=consultada,
        observaciones=[(a_fecha(t), float(v)) for t, v in respuesta["data"] if v is not None],
    )
