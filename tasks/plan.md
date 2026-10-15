# Plan: sensibilidad-proyecto

Especificación: [SPEC-sensibilidad-proyecto.md](../SPEC-sensibilidad-proyecto.md)
(aprobada el 15/10/2026). Tareas en [todo.md](todo.md).

## Decisiones de arquitectura

- `modules/proyectos/sensibilidad.py`, puro: tornado, valores críticos y escenario
  puntual sobre `flujo_caja` y `vpn`; la bisección de `matematica_financiera` se
  vuelve pública. El resultado trae pocas cifras para el chat (VPN base y valores
  críticos) y la tabla completa aparte para el tablero.
- La variable y la dirección de la pregunta las lee Python (`lectura.py`).
- La pestaña "Sensibilidad" y la herramienta usan el proyecto de la sesión con la
  lectura compartida (`app/orchestrator/proyecto.py`).
- El enrutador, el glosario y la nota se tocan al final: el set completo que corre
  en segundo plano los lee en cada pregunta.

## Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| El 7B lee mal un VPN que pasa a negativo | Alto | El escenario se dice en palabras ("deja de crear valor: deja $ X menos que la alternativa"). |
| Demasiadas cifras parecidas en DATOS (20 VPN del tornado) | Alto | El chat recibe solo el VPN base, los valores críticos y los hallazgos; la tabla va al tablero. |
| "Costos" ambiguo en la pregunta | Medio | Costos variables por defecto, dicho como supuesto. |
| La herramienta nueva atrae preguntas de otras (como pasó con el crédito) | Medio | Reglas del enrutador y casos de enrutamiento en el bloque N. |
