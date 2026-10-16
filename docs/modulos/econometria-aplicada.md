---
tags: [economista-ia, modulo]
---

# Módulo 2 — Econometría aplicada

**Objetivo:** evaluación de impacto usando Double ML / ML causal, basada en teoría propia del área (el ML se usa solo donde es pertinente, no como caja negra).

**Estado:** en construcción (mapa de ocho piezas aprobado; listos `almacen-datos` y `calendario`, sigue `series-empresa`).

## Notas

- 16/10/2026: mapa aprobado en `SPEC-mapa-econometria.md`: almacén en PostgreSQL, calendario con el Carnaval de Negros y Blancos, series diarias del PMS (simuladas), pronóstico, sector hotelero, elasticidad precio e impacto (eventos únicos y promociones recurrentes). Sigue `almacen-datos`.
- 16/10/2026: listo `almacen-datos`: PostgreSQL local con las series diarias del PMS por NIT, carga incremental idempotente (nuevas, corregidas e iguales), registro de cargas y días faltantes; revisado por el economista en pgAdmin. Sigue `calendario`.
- 16/10/2026: listo `calendario`: festivos de Colombia con reglas y vigencia en el YAML (incluido el 9 de julio de la Ley 2578 de 2026, que detectó el economista al conciliar), vísperas, puentes, Semana Santa y el Carnaval de Negros y Blancos. Sigue `series-empresa`.

---
Vuelve a [[resumen]]
