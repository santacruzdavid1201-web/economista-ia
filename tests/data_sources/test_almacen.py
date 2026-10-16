"""
Almacén en PostgreSQL (SPEC-almacen-datos.md). Corre contra la base de prueba
(TEST_DATABASE_URL); sin ella, los tests que la usan se saltan. Nunca toca una
base cuyo nombre no termine en _test.
"""
import os

import psycopg
import pytest

from app import config as configuracion
from data_sources import almacen

configuracion.cargar_env()
URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture(scope="module")
def base():
    if not URL:
        pytest.skip("sin TEST_DATABASE_URL: los tests de PostgreSQL se saltan")
    nombre = psycopg.conninfo.conninfo_to_dict(URL).get("dbname", "")
    if not nombre.endswith("_test"):
        pytest.fail(f"TEST_DATABASE_URL apunta a «{nombre}»: los tests solo usan bases *_test")
    conexion = almacen.conectar(URL)
    almacen.crear_esquema(conexion)
    yield conexion
    conexion.rollback()
    conexion.execute("DROP TABLE IF EXISTS pms_diario, carga, empresa CASCADE")
    conexion.commit()
    conexion.close()


@pytest.fixture
def db(base):
    """Cada test empieza con las tablas vacías."""
    base.rollback()
    base.execute("TRUNCATE pms_diario, carga, empresa RESTART IDENTITY CASCADE")
    base.commit()
    return base


def tablas(conexion) -> set[str]:
    filas = conexion.execute("SELECT table_name FROM information_schema.tables "
                             "WHERE table_schema = 'public'").fetchall()
    return {f[0] for f in filas}


# --------------------------------------------------------------------------- #
# Conexión
# --------------------------------------------------------------------------- #
def test_sin_url_dice_como_configurarla(monkeypatch):
    monkeypatch.setattr(configuracion, "cargar_env", lambda *a, **k: None)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(almacen.ErrorAlmacen, match="DATABASE_URL"):
        almacen.conectar()


def test_conexion_fallida_no_muestra_la_clave():
    with pytest.raises(almacen.ErrorAlmacen, match="No se pudo conectar") as e:
        almacen.conectar("postgresql://economista:clave-secreta@localhost:5432/no_existe_test")
    assert "clave-secreta" not in str(e.value)


# --------------------------------------------------------------------------- #
# Esquema y empresa
# --------------------------------------------------------------------------- #
def test_crear_esquema_es_idempotente(db):
    almacen.crear_esquema(db)
    almacen.crear_esquema(db)
    assert {"empresa", "carga", "pms_diario"} <= tablas(db)


def test_guardar_empresa_la_crea_y_la_actualiza(db):
    almacen.guardar_empresa(db, "900123456", "Hotel Demo Andino", "5511", "Pasto")
    almacen.guardar_empresa(db, "900123456", "Hotel Andino S.A.S.")
    fila = db.execute("SELECT razon_social, ciiu, municipio FROM empresa").fetchall()
    assert fila == [("Hotel Andino S.A.S.", "5511", "Pasto")]      # lo vacío no borra


def test_nit_invalido_lo_rechaza_la_base_con_un_mensaje_util(db):
    with pytest.raises(almacen.ErrorAlmacen, match="NIT"):
        almacen.guardar_empresa(db, "900.123.456-7", "Hotel")
    assert db.execute("SELECT count(*) FROM empresa").fetchone() == (0,)


def test_el_comando_crea_el_esquema(monkeypatch, capsys):
    if not URL:
        pytest.skip("sin TEST_DATABASE_URL")
    monkeypatch.setenv("DATABASE_URL", URL)
    assert almacen.main() == 0
    assert "pms_diario" in capsys.readouterr().out
