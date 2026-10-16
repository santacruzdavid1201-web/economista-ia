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


# --------------------------------------------------------------------------- #
# Carga incremental (criterios 2 a 4)
# --------------------------------------------------------------------------- #
from datetime import date, timedelta  # noqa: E402

import pandas as pd  # noqa: E402

NIT = "900123456"


def dias(desde: date, n: int, vendidas: int = 10, **extra) -> pd.DataFrame:
    """n días seguidos de un hotel de 20 habitaciones, a $ 150.000 la noche."""
    fechas = [desde + timedelta(days=k) for k in range(n)]
    return pd.DataFrame({"fecha": fechas, "habitaciones_disponibles": 20,
                         "habitaciones_vendidas": vendidas,
                         "ingresos_habitaciones": vendidas * 150_000.0, **extra})


@pytest.fixture
def hotel(db):
    almacen.guardar_empresa(db, NIT, "Hotel Demo Andino", "5511", "Pasto")
    return db


def cuenta(conexion, tabla: str) -> int:
    return conexion.execute(f"SELECT count(*) FROM {tabla}").fetchone()[0]


def test_cargar_30_dias_nuevos(hotel):
    r = almacen.cargar_pms(hotel, NIT, dias(date(2025, 1, 1), 30), "enero.csv")
    assert (r.nuevas, r.actualizadas, r.iguales) == (30, 0, 0)
    assert (r.desde, r.hasta, r.faltantes) == (date(2025, 1, 1), date(2025, 1, 30), [])
    assert hotel.execute("SELECT archivo, filas_nuevas FROM carga").fetchall() == [("enero.csv", 30)]


def test_cargar_otra_vez_el_mismo_archivo_no_cambia_nada(hotel):
    almacen.cargar_pms(hotel, NIT, dias(date(2025, 1, 1), 30), "enero.csv")
    r = almacen.cargar_pms(hotel, NIT, dias(date(2025, 1, 1), 30), "enero.csv")
    assert (r.nuevas, r.actualizadas, r.iguales) == (0, 0, 30)
    assert cuenta(hotel, "pms_diario") == 30 and cuenta(hotel, "carga") == 2


def test_traslape_agrega_los_nuevos_y_corrige_los_revisados(hotel):
    almacen.cargar_pms(hotel, NIT, dias(date(2025, 1, 1), 30), "enero.csv")
    # Del 26/01 al 04/02: cinco días ya cargados (el PMS corrigió tres) y cinco nuevos
    nuevos = dias(date(2025, 1, 26), 10)
    nuevos.loc[:2, "habitaciones_vendidas"] = 9                     # 26, 27 y 28 de enero
    nuevos.loc[:2, "ingresos_habitaciones"] = 9 * 150_000.0
    r = almacen.cargar_pms(hotel, NIT, nuevos, "corte_04feb.csv")
    assert (r.nuevas, r.actualizadas, r.iguales) == (5, 3, 2)
    corregidos = hotel.execute(
        "SELECT fecha, habitaciones_vendidas, carga_id FROM pms_diario "
        "WHERE fecha BETWEEN '2025-01-26' AND '2025-01-28' ORDER BY fecha").fetchall()
    assert [(v, c) for _, v, c in corregidos] == [(9, r.carga_id)] * 3


def test_una_fila_invalida_no_deja_guardar_nada(hotel):
    malos = dias(date(2025, 1, 1), 30)
    malos.loc[13, "habitaciones_vendidas"] = 25                     # 14/01: 25 de 20
    with pytest.raises(almacen.ErrorAlmacen, match="más habitaciones") as e:
        almacen.cargar_pms(hotel, NIT, malos, "enero.csv")
    assert "2025-01-14" in str(e.value)
    assert cuenta(hotel, "pms_diario") == 0 and cuenta(hotel, "carga") == 0


def test_empresa_no_registrada(db):
    with pytest.raises(almacen.ErrorAlmacen, match="no está registrada"):
        almacen.cargar_pms(db, NIT, dias(date(2025, 1, 1), 3), "enero.csv")


def test_informa_los_dias_faltantes(hotel):
    almacen.cargar_pms(hotel, NIT, dias(date(2025, 1, 1), 10), "a.csv")
    r = almacen.cargar_pms(hotel, NIT, dias(date(2025, 1, 15), 6), "b.csv")
    assert r.faltantes == [date(2025, 1, d) for d in (11, 12, 13, 14)]


def test_los_opcionales_ausentes_quedan_vacios_y_los_presentes_se_guardan(hotel):
    almacen.cargar_pms(hotel, NIT, dias(date(2025, 1, 1), 2, tarifa_publicada=160_000.0,
                                        promocion=[True, False]), "enero.csv")
    filas = hotel.execute("SELECT tarifa_publicada, promocion, huespedes FROM pms_diario "
                          "ORDER BY fecha").fetchall()
    assert [(float(t), p, h) for t, p, h in filas] == [(160_000.0, True, None),
                                                       (160_000.0, False, None)]


@pytest.mark.parametrize("filas, mensaje", [
    (pd.DataFrame(), "no tiene días"),
    (dias(date(2025, 1, 1), 2).drop(columns="habitaciones_vendidas"), "habitaciones_vendidas"),
    (pd.concat([dias(date(2025, 1, 1), 2)] * 2), "aparece más de una vez"),
])
def test_entradas_que_no_sirven(hotel, filas, mensaje):
    with pytest.raises(almacen.ErrorAlmacen, match=mensaje):
        almacen.cargar_pms(hotel, NIT, filas, "x.csv")
