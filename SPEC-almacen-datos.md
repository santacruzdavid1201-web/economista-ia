# Spec: almacen-datos

Módulo del [mapa de econometría](SPEC-mapa-econometria.md). Estado: aprobada por
el usuario el 16/10/2026.

## Objetivo

Guardar las series diarias del PMS de cada hotel en PostgreSQL, de forma que se
puedan **ir actualizando** con cargas de cualquier frecuencia (a diario, cada dos
días, cada semana) sin duplicar ni perder datos, y leerlas como tablas de pandas
para los modelos. Es la base de `series-empresa` y de todo el módulo 2.

Usuario directo: el código de `series-empresa` (que lee el archivo del PMS y lo
valida) y los modelos (que leen la serie). El economista inspecciona la base con
pgAdmin.

## Supuestos

1. Servidor: el PostgreSQL 18 local del usuario (servicio `postgresql-x64-18`,
   puerto 5432). Una base `economista_ia` para el sistema y otra
   `economista_ia_test` para los tests, las dos de un usuario `economista` que
   no es superusuario.
2. La conexión va en `.env` (`DATABASE_URL`, ya ignorado por git); sin ella el
   sistema funciona como hoy y el tablero de Econometría dice cómo configurarla.
3. Esta pieza no lee archivos del PMS ni valida sus columnas: recibe filas
   canónicas ya validadas por `series-empresa`.
4. El panel sectorial y el desglose por canal llegan con sus piezas
   (`sector-hotelero`, `impacto-recurrente`): cada una agrega sus tablas a
   `db/init.sql` cuando se construya.

## Esquema (`db/init.sql`, idempotente)

```sql
CREATE TABLE IF NOT EXISTS empresa (
    nit           TEXT PRIMARY KEY CHECK (nit ~ '^[0-9]{6,10}$'),   -- sin dígito de verificación
    razon_social  TEXT NOT NULL,
    ciiu          TEXT,
    municipio     TEXT,
    creada_en     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS carga (
    id                  BIGSERIAL PRIMARY KEY,
    nit                 TEXT NOT NULL REFERENCES empresa,
    archivo             TEXT NOT NULL,
    cargada_en          TIMESTAMPTZ NOT NULL DEFAULT now(),
    desde               DATE NOT NULL,
    hasta               DATE NOT NULL,
    filas_nuevas        INTEGER NOT NULL,
    filas_actualizadas  INTEGER NOT NULL,
    filas_iguales       INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS pms_diario (
    nit                       TEXT NOT NULL REFERENCES empresa,
    fecha                     DATE NOT NULL,
    habitaciones_disponibles  INTEGER NOT NULL CHECK (habitaciones_disponibles > 0),
    habitaciones_vendidas     INTEGER NOT NULL CHECK (habitaciones_vendidas >= 0),
    ingresos_habitaciones     NUMERIC(16, 2) NOT NULL CHECK (ingresos_habitaciones >= 0),
    tarifa_publicada          NUMERIC(14, 2) CHECK (tarifa_publicada > 0),
    tarifa_competencia        NUMERIC(14, 2) CHECK (tarifa_competencia > 0),
    promocion                 BOOLEAN,
    huespedes                 INTEGER CHECK (huespedes >= 0),
    carga_id                  BIGINT NOT NULL REFERENCES carga,
    actualizado_en            TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (nit, fecha),
    CHECK (habitaciones_vendidas <= habitaciones_disponibles)
);
```

Las reglas que la base puede hacer cumplir van como restricciones (un día no
vende más habitaciones de las que tiene): así ningún camino de escritura las
salta. Montos en pesos corrientes, como los da el PMS.

## Comportamiento

1. **Carga incremental (upsert):** `INSERT … ON CONFLICT (nit, fecha) DO UPDATE`
   solo cuando algún valor cambió. Un día nuevo se agrega; un día que el PMS
   corrigió (p. ej. una cancelación tardía) se actualiza; un día igual no se
   toca. Cargar dos veces el mismo archivo no cambia nada.
2. **Cada carga es atómica:** una transacción; si una fila viola una regla, no
   se guarda ninguna y el error dice qué fecha y qué regla.
3. **Registro de cargas:** cada carga deja una fila en `carga` con el archivo,
   el rango de fechas y cuántas filas fueron nuevas, actualizadas e iguales.
4. **Días faltantes:** después de cargar se informan los días sin dato entre la
   primera y la última fecha de la empresa (huecos), para que el usuario los
   complete; los modelos no imputan en silencio.
5. **Lectura:** la serie de un NIT entre dos fechas como `DataFrame` de pandas
   con la fecha como índice; los módulos de cálculo no ven SQL.
6. **Grano diario:** semanas y meses se calculan agregando al leer, no se
   guardan. Si algún día un hotel solo tiene totales semanales o mensuales, se
   agregan periodos con inicio y fin (fuera de esta pieza).

## Interfaz (`data_sources/almacen.py`)

```python
class ErrorAlmacen(Exception): ...          # mensaje en español, qué hacer

class ResultadoCarga(NamedTuple):
    carga_id: int
    desde: date
    hasta: date
    nuevas: int
    actualizadas: int
    iguales: int
    faltantes: list[date]                    # huecos de la empresa tras la carga

def conectar(url: str | None = None) -> psycopg.Connection: ...
def crear_esquema(conexion) -> None: ...                       # ejecuta db/init.sql
def guardar_empresa(conexion, nit, razon_social, ciiu=None, municipio=None) -> None: ...
def cargar_pms(conexion, nit: str, filas: pd.DataFrame, archivo: str) -> ResultadoCarga: ...
def leer_pms(conexion, nit: str, desde: date | None = None,
             hasta: date | None = None) -> pd.DataFrame: ...
```

Consultas siempre con parámetros (`%s`), nunca armando el SQL con el texto de
una entrada: así un NIT o un nombre de archivo no pueden inyectar SQL.

## Tech stack

PostgreSQL 18 (local); `psycopg[binary]` 3.3 como conector (dependencia nueva,
con versiones para Python 3.14); pandas, que ya está.

## Comandos

```
# Una vez, como superusuario postgres (pgAdmin → Query Tool, o psql):
CREATE ROLE economista LOGIN PASSWORD '...';
CREATE DATABASE economista_ia OWNER economista;
CREATE DATABASE economista_ia_test OWNER economista;

# .env
DATABASE_URL=postgresql://economista:...@localhost:5432/economista_ia
TEST_DATABASE_URL=postgresql://economista:...@localhost:5432/economista_ia_test

python -m data_sources.almacen                # crea o completa el esquema
python -m pytest -v                           # los tests de la base corren si hay TEST_DATABASE_URL
```

## Estructura

- `db/init.sql`: el esquema (el archivo vacío de la arquitectura planeada).
- `data_sources/almacen.py`: conexión, esquema, empresa, carga y lectura.
- `app/config.py` y `.env.example`: `DATABASE_URL`.
- `tests/data_sources/test_almacen.py`.

## Estrategia de pruebas

- Contra PostgreSQL real, en la base de prueba: un mock de la base no probaría
  el upsert, las restricciones ni la atomicidad, que son lo que importa aquí.
- Cada sesión de tests crea el esquema en la base de prueba y lo borra al
  final; cada test empieza con las tablas vacías.
- Sin `TEST_DATABASE_URL`, esos tests se saltan con un aviso: la suite sigue
  corriendo en cualquier máquina sin PostgreSQL.

## Límites

- Siempre: consultas parametrizadas; cargas atómicas; la contraseña solo en
  `.env`; el usuario de la base sin permisos de superusuario.
- Preguntar antes: borrar datos de una empresa; cambiar una columna existente
  (se harán migraciones numeradas cuando haga falta: hoy `init.sql` solo crea lo
  que no existe).
- Nunca: exponer la base en la demo pública sin autenticación; imputar días
  faltantes en silencio.

## Criterios de éxito

1. `python -m data_sources.almacen` crea el esquema en una base vacía y, corrido
   otra vez, no cambia nada; las tablas se ven en pgAdmin.
2. Cargar 30 días da 30 nuevas; cargar otra vez el mismo archivo da 30 iguales;
   cargar 10 días traslapados con 3 corregidos y 5 nuevos da 5 nuevas, 3
   actualizadas y 2 iguales.
3. Una fila con más habitaciones vendidas que disponibles hace fallar la carga
   entera, con la fecha en el mensaje, y la base queda como estaba.
4. Los huecos se informan (cargar del 1 al 10 y del 15 al 20 informa del 11 al
   14).
5. `leer_pms` devuelve la serie ordenada por fecha, con los tipos correctos
   (enteros, montos en `float`, opcionales vacíos como `NaN` o `None`).
6. Suite completa en verde, con y sin `TEST_DATABASE_URL`.

## Preguntas abiertas

1. ¿Creas tú el usuario y las dos bases en pgAdmin (te dejo el SQL listo para
   pegar), o me pasas la contraseña del superusuario `postgres` para hacerlo
   desde aquí? Recomiendo lo primero: la clave de `postgres` no debería pasar
   por el chat.
