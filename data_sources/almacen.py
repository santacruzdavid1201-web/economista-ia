"""
Almacén de las series de la empresa en PostgreSQL (SPEC-almacen-datos.md).

Grano diario por empresa (NIT), carga incremental idempotente y lectura como
DataFrame: los módulos de cálculo nunca ven SQL. Toda consulta va con
parámetros (%s), nunca con el texto de una entrada pegado al SQL.

    python -m data_sources.almacen        # crea o completa el esquema
"""
from __future__ import annotations

import sys

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
