# Tareas: almacen-datos

Plan: [plan.md](plan.md). Verificación común: `python -m pytest -v` antes del commit,
con y sin `TEST_DATABASE_URL`.

- [x] **0. Requisito previo (usuario)**: usuario `economista`, bases `economista_ia` y
  `economista_ia_test`, y las dos variables en `.env` (SQL en el plan).
- [x] **1. Esquema y conexión**: `db/init.sql` con las tres tablas y sus
  restricciones; `conectar`, `crear_esquema` (idempotente) y `guardar_empresa`;
  `python -m data_sources.almacen`; `DATABASE_URL` en la configuración; fixture de
  la base de prueba que se salta sin la variable y se niega con una base que no
  termine en `_test` (criterio 1).
  Archivos: `db/init.sql`, `data_sources/almacen.py`, `app/config.py`, `.env.example`,
  `requirements.txt`, `tests/data_sources/test_almacen.py`.
- [x] **2. Carga incremental**: `cargar_pms` con upsert por tabla temporal, conteo de
  nuevas, actualizadas e iguales, registro en `carga`, atomicidad con el error en
  español (fecha y regla) y huecos (criterios 2 a 4).
  Archivos: `data_sources/almacen.py`, `tests/data_sources/test_almacen.py`.
- [ ] **3. Lectura**: `leer_pms` con índice de fechas, rango opcional y tipos
  convertidos (criterio 5).
  Archivos: `data_sources/almacen.py`, `tests/data_sources/test_almacen.py`.

### Punto de control: completo
- [ ] El usuario ve las tablas y una carga de prueba en pgAdmin; suite en verde con y
  sin `TEST_DATABASE_URL` (criterio 6); documentación de cierre.
