# Plan: matematica-financiera

Especificación: [SPEC-matematica-financiera.md](../SPEC-matematica-financiera.md)
(aprobada el 15/10/2026). Tareas en [todo.md](todo.md).

## Resumen

Funciones puras de matemática financiera (tasas, indicadores, amortización) y
dos análisis para el gerente, el simulador de crédito y el conversor de tasas,
en el chat y en el tablero de Proyectos, que se activa con esta pieza.

## Decisiones de arquitectura

- Un solo archivo de cálculo, `modules/proyectos/matematica_financiera.py`:
  funciones puras y los dos análisis que devuelven `ResultadoModulo`. Las
  piezas siguientes del módulo importan de aquí.
- La lectura de la pregunta (tipo de tasa y montos con palabras) va en
  `app/orchestrator/lectura.py`. Es texto del usuario, no cálculo, y la usan
  el orquestador (validación de argumentos) y las herramientas.
- El modelo solo da números que están en la pregunta (`monto`, `tasa`,
  `plazo`) y elige opciones cerradas (`unidad_plazo`, `sistema`, `hacia`). El
  tipo de la tasa lo lee Python.
- La TIR se calcula con la biblioteca estándar (malla y bisección). No se
  agregan dependencias.

## Grafo de dependencias

```
tasas equivalentes ──┬── indicadores (VPN, TIR...) ── [flujo/evaluación, piezas siguientes]
                     └── amortización ──┐
lectura de la pregunta ─────────────────┼── herramienta simular_credito ── bloque L ── tablero: simulador
                                        └── herramienta convertir_tasa ─┘             tablero: conversor
```

## Fases

1. **Cimientos (tareas 1-3):** funciones puras con los casos a mano de la
   especificación. Sin interfaz.
2. **Chat (tareas 4-7):** lectura de la pregunta, las dos herramientas de punta
   a punta, la nota de conocimiento y el bloque L con el modelo real.
3. **Tablero (tareas 8-9):** página de Proyectos activa con el simulador y el
   conversor.

Cada tarea: tests primero (verlos fallar), implementación, suite completa en
verde, revisión del diff, commit y push.

## Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| El 7B extrae mal el monto o el plazo ("5 años" → 60) | Alto | Plazo con su unidad; Python lee los montos con palabras; el orquestador descarta lo que no está en la pregunta; casos en el bloque L. |
| El 7B confunde nominal con efectiva al redactar | Alto | El hallazgo nombra el tipo de cada tasa ("18,00 % efectiva anual (1,39 % mensual)"); DATOS solo con las cifras que responden; si aparece un error de sentido, se convierte en hallazgo o regla del YAML. |
| El enrutador manda el crédito a `analizar_sensibilidad_tasas` o a `fuera_de_alcance` | Medio | Descripciones en lenguaje de gerente, reglas del enrutador y casos de enrutamiento en el bloque L. |
| La respuesta dice "200 millones" y el set de evaluación no lo encuentra en el desplegable ($ 200.000.000) | Medio | Ver en la primera corrida; si pasa, el hallazgo da el monto como lo escribió el usuario o la regla del set acepta la forma con palabras. |
| LM Studio caído durante el bloque L | Bajo | Correr el bloque cuando esté arriba; las tareas 8-9 no dependen de él. |

## Preguntas abiertas

Ninguna.
