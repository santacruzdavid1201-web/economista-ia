"""
IPC nacional desde el anexo de índices del DANE, el productor original.

Solo sirve para verificar la serie del BanRep: si dejan de coincidir, algo
cambió en la API de SUAMECA.
"""
from __future__ import annotations

import io
from calendar import monthrange
from datetime import date

import openpyxl
import requests

from data_sources.externos.series.modelo import Serie

URL = ("https://www.dane.gov.co/files/operaciones/IPC/{mes}{anio}/"
       "anex-IPC-Indices-{mes}{anio}.xlsx")
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
NOMBRES_MES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
               "septiembre", "octubre", "noviembre", "diciembre"]
TIMEOUT = 60


def descargar_anexo(hoy: date) -> bytes:
    """Anexo más reciente: el DANE publica cada mes el del mes anterior."""
    anio, mes = hoy.year, hoy.month
    for _ in range(3):
        anio, mes = (anio, mes - 1) if mes > 1 else (anio - 1, 12)
        r = requests.get(URL.format(mes=MESES[mes - 1], anio=anio), timeout=TIMEOUT)
        if r.ok:
            return r.content
    raise ValueError("No se encontró el anexo de índices del IPC en los últimos tres meses.")


def desde_anexo(contenido: bytes, consultada: date) -> Serie:
    """Hoja de índices (años en columnas, meses en filas) → Serie mensual."""
    hoja = openpyxl.load_workbook(io.BytesIO(contenido), read_only=True, data_only=True).active
    anios: list = []
    observaciones = []
    for fila in hoja.iter_rows(values_only=True):
        etiqueta = str(fila[0] or "").strip().lower()
        if etiqueta == "mes":
            anios = list(fila[1:])
        elif anios and etiqueta in NOMBRES_MES:
            mes = NOMBRES_MES.index(etiqueta) + 1
            for anio, valor in zip(anios, fila[1:]):
                if isinstance(anio, int) and isinstance(valor, (int, float)):
                    fin = date(anio, mes, monthrange(anio, mes)[1])
                    observaciones.append((fin, float(valor)))
    if not observaciones:
        raise ValueError("El anexo del DANE no tiene la tabla de índices esperada.")
    return Serie(clave="ipc_nacional_dane", nombre="Índice de Precios al Consumidor (IPC)",
                 fuente="DANE, anexo de índices del IPC",
                 unidad="Indice, base dic/2018=100", frecuencia="mensual",
                 geografia="nacional", consultada=consultada, observaciones=observaciones)
