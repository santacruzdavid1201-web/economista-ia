# Plan: almacen-datos

Especificación: [SPEC-almacen-datos.md](../SPEC-almacen-datos.md)
(aprobada el 16/10/2026). Tareas en [todo.md](todo.md).

## Requisito previo (usuario, una vez)

En pgAdmin, conectado como `postgres`, Query Tool: correr **cada línea por
separado** (seleccionarla y F5). `CREATE DATABASE` no puede ir junto a otras
órdenes en un mismo envío, porque no corre dentro de una transacción.

```sql
CREATE ROLE economista LOGIN PASSWORD 'una-clave-propia';
CREATE DATABASE economista_ia OWNER economista;
CREATE DATABASE economista_ia_test OWNER economista;
```

Y en `.env` (no se versiona):

```
DATABASE_URL=postgresql://economista:una-clave-propia@localhost:5432/economista_ia
TEST_DATABASE_URL=postgresql://economista:una-clave-propia@localhost:5432/economista_ia_test
```

## Decisiones de arquitectura

- Un solo archivo, `data_sources/almacen.py`: conexión, esquema, empresa, carga y
  lectura. Los módulos de cálculo reciben `DataFrame`, nunca una conexión.
- El upsert pasa por una tabla temporal: las filas se copian a ella y un solo
  `INSERT … SELECT … ON CONFLICT DO UPDATE … WHERE (algo cambió)` las escribe.
  `RETURNING (xmax = 0)` dice si cada fila fue nueva o actualizada; las iguales
  son el resto. Todo en una transacción.
- Las restricciones de la base son la última línea de defensa; el error de
  PostgreSQL se traduce a español con la fecha y la regla que falló.
- Los tests de la base usan `TEST_DATABASE_URL`: un fixture de sesión crea el
  esquema y lo borra al final; otro vacía las tablas antes de cada test. Sin la
  variable, se saltan.
- `app/config.py` gana `db_url` (opcional); sin ella nada cambia.

## Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Los tests borran datos reales | Alto | Solo se conectan a `TEST_DATABASE_URL` y se niegan si su nombre de base no termina en `_test`. |
| Contar mal nuevas y actualizadas | Medio | Criterio 2 de la especificación como test con los tres casos. |
| `NUMERIC` vuelve como `Decimal` y los modelos esperan `float` | Medio | `leer_pms` convierte los tipos; test de tipos (criterio 5). |
| La clave termina en el código o en git | Alto | Solo en `.env`, que git ignora; `.env.example` con un marcador. |
