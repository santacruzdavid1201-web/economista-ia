# Plan: costo-capital

Especificación: [SPEC-costo-capital.md](../SPEC-costo-capital.md)
(aprobada el 16/10/2026). Tareas en [todo.md](todo.md).

## Decisiones de arquitectura

- `modules/proyectos/wacc.py` (el archivo vacío de la arquitectura planeada),
  puro: recibe el historial, el TES UVR y el IPC como `Serie`, los parámetros de
  Damodaran, la tarifa de renta y π₁; devuelve un `ResultadoModulo` con el WACC
  real, su equivalente nominal del primer año, Ke, Kd real y el peso de la
  deuda. Sin estados financieros, el costo de los activos (Ku).
- La tasa implícita de la deuda sale de una sola función, compartida con
  `sensibilidad-tasas` (hoy vive dentro de ella): el mismo número en los dos
  tableros.
- Inflación del año del balance: variación de 12 meses del IPC nacional al
  corte. Es Fisher ex post: la tasa de ese año entre la inflación de ese año.
- Tarifa de renta: la del proyecto (35 % por defecto), porque hay hoteles con
  tarifa especial; dicha como supuesto.
- Parámetros de Damodaran escritos a mano en `config/costo_capital.yaml`
  (spread, prima total, beta sin deuda, con fuente y fecha). Los lee la capa
  `app/`; el módulo los recibe.
- TES UVR 10 años como serie nueva del catálogo (`tes_uvr_10`, SUAMECA 15277):
  el actualizador la incluye solo. El TES en pesos (15274) queda fuera: ninguna
  fórmula lo usa y sería otra cifra parecida para el 7B. Se agrega si se quiere
  mostrar la inflación que espera el mercado.
- La evaluación admite tasa real: un campo `tasa_tipo` (nominal / real) en el
  formulario viaja con el proyecto de la sesión al tablero, a la sensibilidad y
  al chat. Con tasa real se descuentan los flujos en pesos de hoy y la TIR sale
  real. Una tasa en la pregunta ("¿y si mi tasa es 18 %?") vuelve a nominal.
- La senda del BanRep se extrae de `leer_proyecto` para que el costo de capital
  use el mismo π₁ que el flujo.
- Una función de `app/orchestrator/proyecto.py` arma el costo de capital
  (series, parámetros, π₁) para el tablero y el chat, como `leer_proyecto`.
- Chat: `calcular_costo_capital`; con empresa da el WACC, sin ella el costo de
  los activos.
- El enrutador, el glosario y la nota se tocan al final, como en la pieza
  anterior.

## Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| El 7B mezcla el WACC real con su equivalente nominal o con Ke (varias tasas parecidas) | Alto | Hallazgos en palabras ("10,77 % por encima de la inflación; unos 15,53 % en pesos corrientes el primer año"). El chat recibe solo el WACC, su equivalente, Ke, Kd y el peso de la deuda; primas, spread y beta van en fórmulas y supuestos. |
| El 7B presenta el WACC como "la" tasa correcta o recomienda | Alto | Hallazgo "es una referencia, no una regla"; regla en el bloque O. |
| Patrimonio en libros ≤ 0: D/P y beta sin sentido | Medio | WACC `None` con advertencia; se muestra Ku. |
| Deuda sin gastos financieros identificados | Medio | Kd y WACC `None` con advertencia (criterio del módulo 1); se muestra Ke. |
| Tasa real y nominal confundidas en el formulario | Medio | El tipo es un campo visible y cada tarjeta de la evaluación dice "real". |
| Empresa con pérdida: no aprovecha el ahorro de impuestos de la deuda | Bajo | Advertencia; el cálculo sigue con la tarifa. |
| La beta "Hotel/Gaming" incluye casinos | Bajo | Supuesto dicho. |

## Pregunta abierta

- El valor de la beta sin deuda (el usuario lo lee del Excel de Damodaran).
  Bloquea solo la tarea 3; las tareas 1 y 2 avanzan con el ejemplo.
