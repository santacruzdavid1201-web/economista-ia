# Mapa de capacidades: módulo 4, entorno macro y sectorial

Aprobado por el usuario el 7/10/2026. Los ids son estables: las
especificaciones (`SPEC-<id>.md`) y los planes se refieren a ellos.

| Id | Qué hace | Depende de |
|---|---|---|
| `series-externas` | Descarga, caché y formato común de series de tiempo (BanRep: tasa de política, IBR, TRM; DANE: IPC nacional y por ciudad, PIB, desempleo, Muestra Mensual de Hoteles). Solo trae datos: no analiza. | — |
| `crecimiento-real` | ¿Crecí en términos reales? Deflacta los ingresos de la empresa con el IPC de su ciudad (o el nacional). | `series-externas` (IPC), módulo 1 |
| `sensibilidad-tasas` | ¿Cómo me afectan las tasas? Cambio en gastos financieros y cobertura de intereses si la tasa sube o baja 1, 2 o 3 puntos. Aritmética sobre datos actuales, no pronóstico. | `series-externas` (IBR, tasa BanRep), módulo 1 |
| `panorama-macro` | Contexto: nivel y tendencia de inflación, tasa, TRM, PIB y desempleo, con hallazgos redactados en Python. | `series-externas` |
| `sector-hotelero` | ¿Cómo va mi sector? MMH de la región frente al país, y crecimiento real de la empresa frente al del sector. | `series-externas` (MMH, IPC), `crecimiento-real` |

## Orden de construcción

`series-externas` (IPC) → `crecimiento-real` → `series-externas` (+ tasas) →
`sensibilidad-tasas` → `panorama-macro` → `series-externas` (+ MMH) →
`sector-hotelero`

`series-externas` crece fuente por fuente, junto con el análisis que la usa:
cada paso es un tramo completo que se puede probar en la interfaz.

## Reglas comunes

- Cada análisis devuelve un `ResultadoModulo` con hallazgos redactados en
  Python, entra como herramienta del orquestador y trae sus preguntas en un
  bloque nuevo del set de evaluación (`tests/eval/preguntas.yaml`).
- Los datos de la empresa (ingresos, deuda, intereses) se toman del módulo 1;
  este módulo no los recalcula.
- Solo datos observados. Proyectar es del módulo 2 (econometría).
