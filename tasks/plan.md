# Plan: calendario

Especificación: [SPEC-calendario.md](../SPEC-calendario.md)
(aprobada el 16/10/2026). Tareas en [todo.md](todo.md).

## Decisiones de arquitectura

- `modules/econometria/calendario.py`, puro (llena el directorio de la
  arquitectura planeada): `festivos(anio)` y `calendario(desde, hasta, ciudad)`.
- Las reglas de festivos (fijos, trasladables, según la Pascua) y los eventos
  locales viven en `config/calendario.yaml`, cada regla con su vigencia: una ley
  nueva es una línea, sin tocar el código.
- La Pascua sale de `dateutil.easter` (ya instalada con pandas): sin dependencias
  nuevas. Las ciudades se buscan con `sin_tildes` del catálogo de series.
- `calendario` mira también los festivos del año anterior y del siguiente, para
  que las vísperas y los puentes de los bordes del rango salgan bien.

## Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Una ley cambia los festivos y el código no se entera | Medio | Reglas en el YAML con vigencia; nota en los límites para revisar la decisión de la Corte sobre la Ley 2578 antes de 2027. |
| Dos festivos el mismo día se cuentan doble | Bajo | Un solo día con los dos nombres (caso del 30/6/2025 en los tests). |
| Víspera y puente mal en el borde del rango (31/12, 1/1) | Bajo | Se cargan los festivos de los años vecinos; test con un rango que empieza en un lunes festivo. |
