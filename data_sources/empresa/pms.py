"""
Cargador de la exportación diaria del PMS (software hotelero) al esquema canónico
que guarda el almacén (SPEC-series-empresa.md).

Reutiliza el lector del cargador del PUC: CSV o Excel, filas de título antes del
encabezado, ";" o ",", UTF-8 o Windows-1252, números colombianos o ingleses (el
formato se decide con toda la columna). Acepta los nombres habituales de las
exportaciones en español e inglés. Los errores dicen la fila del archivo.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import IO

import pandas as pd

from data_sources.empresa.puc import ErrorCarga, _filas, _simplificar, a_numero, separador_decimal

# Columna canónica → nombres que la reconocen (ya simplificados: minúsculas, sin tildes)
ALIAS = {
    "fecha": ("fecha", "date", "dia", "business date", "fecha de estadia"),
    "habitaciones_disponibles": ("habitaciones disponibles", "disponibles", "rooms available",
                                 "available rooms", "inventario"),
    "habitaciones_vendidas": ("habitaciones vendidas", "habitaciones ocupadas", "ocupadas",
                              "vendidas", "rooms sold", "rooms occupied", "occupied rooms",
                              "room nights"),
    "ingresos_habitaciones": ("ingresos habitaciones", "ingresos de habitaciones",
                              "ingresos alojamiento", "ingresos de alojamiento", "room revenue",
                              "rooms revenue"),
    "tarifa_publicada": ("tarifa publicada", "tarifa", "tarifa rack", "rack rate", "rate",
                         "best available rate", "bar", "published rate"),
    "tarifa_competencia": ("tarifa competencia", "tarifa de la competencia", "competitor rate",
                           "comp rate"),
    "promocion": ("promocion", "promo", "promotion"),
    "huespedes": ("huespedes", "guests", "pax"),
}
OBLIGATORIAS = ("fecha", "habitaciones_disponibles", "habitaciones_vendidas",
                "ingresos_habitaciones")
ENTEROS = ("habitaciones_disponibles", "habitaciones_vendidas", "huespedes")
MONTOS = ("ingresos_habitaciones", "tarifa_publicada", "tarifa_competencia")
ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})")              # 2026-01-31 (con hora o sin ella)
NUMERICA = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})$")  # 31/01/2026 u 01/31/2026
SI = {"si", "s", "yes", "y", "true", "verdadero", "x"}
NO = {"no", "n", "false", "falso"}
ETIQUETA = {"fecha": "la fecha", "habitaciones_disponibles": "habitaciones disponibles",
            "habitaciones_vendidas": "habitaciones vendidas",
            "ingresos_habitaciones": "ingresos de habitaciones",
            "tarifa_publicada": "tarifa publicada", "tarifa_competencia": "tarifa de la competencia",
            "promocion": "promoción", "huespedes": "huéspedes"}


class ErrorPMS(ValueError):
    """El archivo del PMS no sirve; el mensaje dice la fila y qué arreglar."""


def _encabezado(filas: list[list]) -> tuple[int, dict[str, int]] | None:
    """Fila de encabezados (entre las primeras 30) y columna de cada campo reconocido."""
    for i, fila in enumerate(filas[:30]):
        nombres = {_simplificar(c): j for j, c in enumerate(fila) if c not in (None, "")}
        columnas = {campo: next((nombres[a] for a in alias if a in nombres), None)
                    for campo, alias in ALIAS.items()}
        if all(columnas[c] is not None for c in OBLIGATORIAS):
            return i, {c: j for c, j in columnas.items() if j is not None}
    return None


def dia_primero(textos: list[str]) -> bool:
    """
    Orden de las fechas numéricas de una columna, decidido con todos sus valores: un
    primer número mayor que 12 solo puede ser el día; un segundo número mayor que 12,
    también (y entonces el mes va primero, como en los PMS en inglés). Sin evidencia,
    el día primero, como se escribe en Colombia.
    """
    dia = mes = 0
    for texto in textos:
        m = NUMERICA.match(texto.strip())
        if m and int(m[1]) > 12:
            dia += 1
        elif m and int(m[2]) > 12:
            mes += 1
    return dia >= mes


def _fecha(valor: object, fila: int, dia_va_primero: bool) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    try:
        if m := ISO.match(texto):                  # año-mes-día, sin ambigüedad
            return date(int(m[1]), int(m[2]), int(m[3]))
        if m := NUMERICA.match(texto):
            dia, mes = (m[1], m[2]) if dia_va_primero else (m[2], m[1])
            anio = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
            return date(anio, int(mes), int(dia))
    except ValueError:
        pass
    raise ErrorPMS(f"Fila {fila}: la fecha «{valor}» no es válida (use 31/01/2026 o "
                   "2026-01-31).")


def _vacio(valor: object) -> bool:
    return valor is None or (isinstance(valor, float) and pd.isna(valor)) or str(valor).strip() == ""


def _promocion(valor: object, fila: int) -> bool | None:
    if _vacio(valor):
        return None
    if isinstance(valor, bool):
        return valor
    texto = _simplificar(str(valor)) or str(valor).strip()
    if texto in SI or texto == "1":
        return True
    if texto in NO or texto == "0":
        return False
    raise ErrorPMS(f"Fila {fila}: «{valor}» no dice si hubo promoción (use sí o no).")


def leer_archivo_pms(archivo: Path | str | IO[bytes], nombre: str | None = None) -> pd.DataFrame:
    """El archivo del PMS → DataFrame canónico (una fila por día), validado."""
    extension = Path(nombre or str(archivo)).suffix.lower()
    for filas in _filas(archivo, extension):
        encontrado = _encabezado(filas)
        if encontrado:
            break
    else:
        raise ErrorPMS("No se encontró el encabezado del PMS: el archivo debe tener columnas de "
                       "fecha, habitaciones disponibles, habitaciones vendidas e ingresos de "
                       "habitaciones.")
    i, columnas = encontrado
    datos = [(i + 2 + k, f) for k, f in enumerate(filas[i + 1:])
             if any(not _vacio(c) for c in f)]                        # (fila del archivo, celdas)

    def celda(f: list, campo: str) -> object:
        j = columnas.get(campo)
        return f[j] if j is not None and j < len(f) else None

    textos = [str(celda(f, "fecha")) for _, f in datos]
    orden = dia_primero(textos)
    salida: dict[str, list] = {"fecha": [_fecha(celda(f, "fecha"), n, orden) for n, f in datos]}
    for campo in (*ENTEROS, *MONTOS):
        valores = [celda(f, campo) for _, f in datos]
        decimal = separador_decimal([str(v) for v in valores if isinstance(v, str)])
        numeros = []
        for (n, _), v in zip(datos, valores):
            if _vacio(v):
                if campo in OBLIGATORIAS:
                    raise ErrorPMS(f"Fila {n}: falta el dato de {ETIQUETA[campo]}.")
                numeros.append(None)
                continue
            try:
                numero = a_numero(v, decimal)
            except ErrorCarga:
                raise ErrorPMS(f"Fila {n}: «{v}» no es un número ({ETIQUETA[campo]}).") from None
            if campo in ENTEROS and not float(numero).is_integer():
                raise ErrorPMS(f"Fila {n}: {ETIQUETA[campo]} debe ser un número entero ({v}).")
            numeros.append(int(numero) if campo in ENTEROS else numero)
        salida[campo] = numeros
    salida["promocion"] = [_promocion(celda(f, "promocion"), n) for n, f in datos]

    df = pd.DataFrame(salida)[list(ALIAS)]
    for (n, _), (_, r) in zip(datos, df.iterrows()):
        cuando = f"fila {n} ({r['fecha']:%d/%m/%Y})"
        if r["habitaciones_disponibles"] <= 0:
            raise ErrorPMS(f"En la {cuando}, las habitaciones disponibles deben ser más de cero.")
        if r["habitaciones_vendidas"] > r["habitaciones_disponibles"]:
            raise ErrorPMS(f"En la {cuando}, se vendieron más habitaciones de las disponibles "
                           f"({r['habitaciones_vendidas']} de {r['habitaciones_disponibles']}).")
        negativos = [ETIQUETA[c] for c in (*ENTEROS, *MONTOS)
                     if r[c] is not None and not pd.isna(r[c]) and r[c] < 0]
        if negativos:
            raise ErrorPMS(f"En la {cuando}, {', '.join(negativos)} no puede ser negativo.")
    repetidas = df["fecha"][df["fecha"].duplicated()]
    if not repetidas.empty:
        raise ErrorPMS(f"La fecha {repetidas.iloc[0]:%d/%m/%Y} aparece más de una vez en el "
                       "archivo.")
    return df
