# Mapa de capacidades: módulo 3, evaluación de proyectos

Aprobado por el usuario el 15/10/2026. Los ids son estables: las
especificaciones (`SPEC-<id>.md`) y los planes se refieren a ellos.

| Id | Qué hace | Depende de |
|---|---|---|
| `matematica-financiera` | Funciones puras: tasas equivalentes, VPN, TIR (única o ninguna, con aviso), TIRM, recuperación descontada, valor anual equivalente, índice de rentabilidad y tabla de amortización de un crédito. En el chat y en el tablero: simulador de crédito y conversor de tasas. | — |
| `flujo-proyecto` | El proyecto (inversión, vida útil, ingresos y costos adicionales, capital de trabajo, salvamento) → flujo de caja libre por año, con impuesto de renta y depreciación. Entra por un formulario del tablero. | `matematica-financiera` |
| `evaluacion-proyecto` | ¿Me conviene? VPN, TIR, TIRM, índice de rentabilidad y recuperación con una tasa de descuento; hallazgos en Python; tablero completo. | `flujo-proyecto` |
| `costo-capital` | WACC de la empresa: costo de la deuda implícito del balance después de impuestos y costo del patrimonio por CAPM en pesos (TES 10 años + beta sectorial de Damodaran reapalancada × prima de mercado), o la tasa de oportunidad del dueño. | módulo 1, `series-externas` |
| `sensibilidad-proyecto` | ¿Qué tan frágil es? VPN ante ±10 % y ±20 % en cada variable (tornado) y valor crítico de cada una (VPN = 0). | `evaluacion-proyecto` |
| `montecarlo-proyecto` | ¿Qué probabilidad hay de perder? Rangos mínimo / más probable / máximo por variable, 10.000 simulaciones con semilla fija, probabilidad de VPN negativo y percentiles. | `sensibilidad-proyecto` |

## Orden de construcción

`matematica-financiera` → `flujo-proyecto` → `evaluacion-proyecto` (con la
tasa de oportunidad del usuario) → `costo-capital` → `sensibilidad-proyecto` →
`montecarlo-proyecto`

La matemática financiera va primero: es aritmética pura, fácil de conciliar a
mano, y sirve sola (las pymes preguntan mucho por créditos y el 7B se equivoca
al convertir tasas). El WACC va después de la evaluación para tener pronto un
tablero completo; llega como la tasa recomendada.

## Decisiones aprobadas (15/10/2026)

1. **El proyecto entra por un formulario del tablero**; el chat trabaja sobre
   el proyecto cargado ("¿y si los costos suben 10 %?"). Lo que tiene pocos
   parámetros (monto, tasa, plazo) sí sale de la pregunta.
2. **Flujos a precios de hoy y tasa de descuento real**: (1 + nominal) /
   (1 + π) − 1, con π la expectativa de inflación de la encuesta del BanRep
   (dato observado, no un pronóstico propio). El error que se evita: flujos a
   precios de hoy descontados con una tasa nominal subvaloran el proyecto.
3. **Costo del patrimonio por CAPM en pesos** (el TES ya incluye el riesgo
   país), reemplazable por la tasa de oportunidad del dueño. Pesos de deuda y
   patrimonio en valores en libros, declarado como supuesto.

## Reglas comunes

- Cada pieza devuelve un `ResultadoModulo` con hallazgos redactados en Python,
  entra como herramienta del orquestador y trae su bloque en el set de
  evaluación (`tests/eval/preguntas.yaml`).
- El sistema no proyecta: los flujos son supuestos del usuario y se muestran
  como tales. Los datos de la empresa (deuda, intereses, impuesto) salen del
  módulo 1.
- Evaluar un proyecto de la propia empresa entra; recomendar inversiones
  financieras (acciones, CDT, fondos) sigue en `fuera_de_alcance`. El
  enrutador debe distinguirlo.
- Sin calificativos sin referencia: "crea valor" (VPN > 0) es un criterio de
  decisión, no una opinión; "buen proyecto" o "tasa cara" no se dicen.
