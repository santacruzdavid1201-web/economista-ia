"""
Almacén de las series de la empresa en PostgreSQL (SPEC-almacen-datos.md).

Grano diario por empresa (NIT), carga incremental idempotente y lectura como
DataFrame: los módulos de cálculo nunca ven SQL. Toda consulta va con
parámetros (%s), nunca con el texto de una entrada pegado al SQL.

    python -m data_sources.almacen        # crea o completa el esquema
"""
from __future__ import annotations

import re
import sys
from datetime import date
from typing import NamedTuple

import pandas as pd
import psycopg

from app.config import RAIZ, config

ESQUEMA = RAIZ / "db" / "init.sql"
TABLAS = ("empresa", "carga", "pms_diario")
# Restricción de la base → qué decirle al usuario (los nombres están en db/init.sql)
RESTRICCIONES = {
    "nit_valido": "El NIT debe tener entre 6 y 10 dígitos, sin puntos ni dígito de verificación.",
    "disponibles_positivas": "Las habitaciones disponibles deben ser más de cero.",
    "vendidas_no_negativas": "Las habitaciones vendidas no pueden ser negativas.",
    "ingresos_no_negativos": "Los ingresos de habitaciones no pueden ser negativos.",
    "tarifa_positiva": "La tarifa publicada debe ser mayor que cero.",
    "tarifa_competencia_positiva": "La tarifa de la competencia debe ser mayor que cero.",
    "huespedes_no_negativos": "Los huéspedes no pueden ser negativos.",
    "vendidas_no_superan_disponibles": "Un día no puede vender más habitaciones de las que tiene "
                                       "disponibles.",
    "carga_nit_fkey": "La empresa no está registrada en la base: guarde primero su NIT y su "
                      "razón social.",
}


class ErrorAlmacen(Exception):
    """Algo falló con la base; el mensaje dice qué hacer y nunca trae la clave."""


def conectar(url: str | None = None) -> psycopg.Connection:
    """Conexión a la base de `url` o, sin ella, a la de DATABASE_URL (.env)."""
    url = url or config().db_url
    if not url:
        raise ErrorAlmacen("No hay base de datos configurada: agregue DATABASE_URL al archivo "
                           ".env (ver .env.example).")
    try:
        return psycopg.connect(url, connect_timeout=5)
    except psycopg.OperationalError as e:
        # El mensaje de libpq dice el servidor y el usuario, no la clave
        motivo = (str(e).strip().splitlines() or [""])[-1]
        raise ErrorAlmacen("No se pudo conectar a PostgreSQL. Revise que el servicio esté "
                           "encendido y que el usuario, la clave y la base de DATABASE_URL sean "
                           f"correctos ({motivo}).") from None


def traducir(e: psycopg.errors.IntegrityError) -> ErrorAlmacen:
    """El error de una restricción de la base, en español."""
    nombre = e.diag.constraint_name or ""
    return ErrorAlmacen(RESTRICCIONES.get(nombre, f"La base rechazó los datos ({nombre or e})."))


def crear_esquema(conexion: psycopg.Connection) -> None:
    """Crea lo que falte del esquema (db/init.sql); lo que existe no se toca."""
    conexion.execute(ESQUEMA.read_text(encoding="utf-8"))
    conexion.commit()


def guardar_empresa(conexion: psycopg.Connection, nit: str, razon_social: str,
                    ciiu: str | None = None, municipio: str | None = None) -> None:
    """Crea la empresa o actualiza sus datos; lo que llega vacío no borra lo guardado."""
    try:
        conexion.execute(
            """INSERT INTO empresa (nit, razon_social, ciiu, municipio) VALUES (%s, %s, %s, %s)
               ON CONFLICT (nit) DO UPDATE SET
                   razon_social = EXCLUDED.razon_social,
                   ciiu = COALESCE(EXCLUDED.ciiu, empresa.ciiu),
                   municipio = COALESCE(EXCLUDED.municipio, empresa.municipio)""",
            (nit, razon_social, ciiu, municipio))
    except psycopg.errors.IntegrityError as e:
        conexion.rollback()
        raise traducir(e) from None
    conexion.commit()


COLUMNAS = ("habitaciones_disponibles", "habitaciones_vendidas", "ingresos_habitaciones",
            "tarifa_publicada", "tarifa_competencia", "promocion", "huespedes")
OBLIGATORIAS = COLUMNAS[:3]
FECHA = re.compile(r"\d{4}-\d{2}-\d{2}")


class ResultadoCarga(NamedTuple):
    carga_id: int
    desde: date
    hasta: date
    nuevas: int
    actualizadas: int                  # días que el PMS corrigió
    iguales: int                       # días que ya estaban, sin cambios
    faltantes: list[date]              # huecos de la empresa después de la carga


def _nativo(valor: object) -> object:
    """numpy y pandas → tipos de Python, que es lo que psycopg sabe escribir; vacío → None."""
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):
        return None
    if isinstance(valor, pd.Timestamp):
        return valor.date()
    return valor.item() if hasattr(valor, "item") else valor


def _filas(nit: str, filas: pd.DataFrame, carga_id: int) -> list[tuple]:
    opcionales = {c: filas[c] if c in filas else None for c in COLUMNAS}
    return [(nit, _nativo(f), *(_nativo(opcionales[c].iloc[k]) if opcionales[c] is not None
                                else None for c in COLUMNAS), carga_id)
            for k, f in enumerate(filas["fecha"])]


def cargar_pms(conexion: psycopg.Connection, nit: str, filas: pd.DataFrame,
               archivo: str) -> ResultadoCarga:
    """
    Guarda los días del PMS de una empresa: los nuevos se agregan, los que el PMS corrigió
    se actualizan y los iguales no se tocan, así que cargar dos veces el mismo archivo no
    cambia nada. Todo o nada: si un día viola una regla, no se guarda ninguno.
    """
    if filas.empty:
        raise ErrorAlmacen("El archivo no tiene días para cargar.")
    faltan = [c for c in ("fecha", *OBLIGATORIAS) if c not in filas]
    if faltan:
        raise ErrorAlmacen(f"Faltan columnas obligatorias: {', '.join(faltan)}.")
    fechas = pd.to_datetime(filas["fecha"]).dt.date
    repetidas = sorted(set(fechas[fechas.duplicated()]))
    if repetidas:
        raise ErrorAlmacen(f"La fecha {repetidas[0]} aparece más de una vez en el archivo.")
    filas = filas.assign(fecha=fechas)
    desde, hasta = min(fechas), max(fechas)
    lista = ", ".join(COLUMNAS)
    distinto = (f"({', '.join(f'pms_diario.{c}' for c in COLUMNAS)}) IS DISTINCT FROM "
                f"({', '.join(f'EXCLUDED.{c}' for c in COLUMNAS)})")
    try:
        cur = conexion.cursor()
        carga_id = cur.execute(
            "INSERT INTO carga (nit, archivo, desde, hasta, filas_nuevas, filas_actualizadas, "
            "filas_iguales) VALUES (%s, %s, %s, %s, 0, 0, 0) RETURNING id",
            (nit, archivo, desde, hasta)).fetchone()[0]
        cur.execute("CREATE TEMP TABLE entrada (LIKE pms_diario INCLUDING DEFAULTS) ON COMMIT DROP")
        with cur.copy(f"COPY entrada (nit, fecha, {lista}, carga_id) FROM STDIN") as copia:
            for fila in _filas(nit, filas, carga_id):
                copia.write_row(fila)
        # Un solo INSERT: el día nuevo entra, el corregido se actualiza y el igual no se
        # toca (el WHERE). xmax = 0 en las filas insertadas y ≠ 0 en las actualizadas.
        escritas = cur.execute(
            f"""INSERT INTO pms_diario (nit, fecha, {lista}, carga_id)
                SELECT nit, fecha, {lista}, carga_id FROM entrada
                ON CONFLICT (nit, fecha) DO UPDATE SET
                    {', '.join(f'{c} = EXCLUDED.{c}' for c in COLUMNAS)},
                    carga_id = EXCLUDED.carga_id, actualizado_en = now()
                WHERE {distinto}
                RETURNING (xmax = 0)""").fetchall()
        nuevas = sum(1 for (insertada,) in escritas if insertada)
        actualizadas, iguales = len(escritas) - nuevas, len(filas) - len(escritas)
        cur.execute("UPDATE carga SET filas_nuevas = %s, filas_actualizadas = %s, "
                    "filas_iguales = %s WHERE id = %s", (nuevas, actualizadas, iguales, carga_id))
        faltantes = [f for (f,) in cur.execute(
            """SELECT d::date FROM generate_series(
                   (SELECT min(fecha) FROM pms_diario WHERE nit = %s),
                   (SELECT max(fecha) FROM pms_diario WHERE nit = %s), interval '1 day') AS d
               WHERE NOT EXISTS (SELECT 1 FROM pms_diario WHERE nit = %s AND fecha = d::date)
               ORDER BY d""", (nit, nit, nit)).fetchall()]
        conexion.commit()
    except psycopg.errors.IntegrityError as e:
        conexion.rollback()
        error = traducir(e)
        # La fila rechazada viene en el detalle de PostgreSQL: su fecha ubica el error
        fecha = FECHA.search(e.diag.message_detail or "")
        raise ErrorAlmacen(f"{error} Día: {fecha.group()}." if fecha else str(error)) from None
    except Exception:
        conexion.rollback()
        raise
    return ResultadoCarga(carga_id, desde, hasta, nuevas, actualizadas, iguales, faltantes)


def main() -> int:
    try:
        with conectar() as conexion:
            crear_esquema(conexion)
            base = conexion.info.dbname
    except ErrorAlmacen as e:
        print(e)
        return 1
    print(f"Esquema listo en la base {base}: {', '.join(TABLAS)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
