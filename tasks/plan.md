# Plan: evaluacion-proyecto

Especificación: [SPEC-evaluacion-proyecto.md](../SPEC-evaluacion-proyecto.md)
(aprobada el 15/10/2026). Tareas en [todo.md](todo.md). Los planes anteriores
(`matematica-financiera`, `flujo-proyecto`, completos) quedan en Git.

## Resumen

Con el flujo de caja libre y la tasa de oportunidad del usuario: VPN (primero),
TIR nominal, TIRM, recuperación descontada e índice de rentabilidad, con
hallazgos que dicen si el proyecto crea valor. En la pestaña "Su proyecto" y en
el chat, sobre el último proyecto válido de la sesión.

## Decisiones de arquitectura

- `evaluar(flujo, tasa)` es pura y usa las funciones ya conciliadas de
  `matematica_financiera`; descuenta los flujos corrientes con la tasa nominal.
- La lectura del formulario (montos con palabras, porcentajes, senda de
  inflación) pasa de `frontend/tableros.py` a `app/orchestrator/proyecto.py`:
  el tablero y la herramienta del chat leen el proyecto de la misma forma, y
  el orquestador no depende de la interfaz.
- El proyecto llega al chat como la pregunta: `responder(..., proyecto=...)`
  lo pasa a las herramientas en sus argumentos (sin entrar en `Respuesta`).
  La web pasa el de la sesión; el set de evaluación, el de ejemplo.

## Grafo de dependencias

```
evaluar (puro) ─────────────┬── tablero: tarjetas y hallazgos ── aviso de ejemplo
lectura del proyecto ───────┤
                            └── herramienta evaluar_proyecto ── nota + bloque M
```

## Fases

1. **Cálculo (tareas 1-2):** evaluación pura con el caso a mano y la lectura
   compartida del proyecto.
2. **Tablero (tarea 3):** tasa en el formulario, tarjetas, hallazgos y aviso de
   valores de ejemplo en las dos pestañas.
3. **Chat (tareas 4-5):** herramienta, reglas del enrutador, nota de
   conocimiento y bloque M con el modelo real.

Cada tarea: tests primero (verlos fallar), implementación, suite completa,
revisión del diff, commit y push.

## Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| El 7B lee mal un VPN negativo (pierde el signo o dice que crea valor) | Alto | El hallazgo lo dice en palabras ("no crea valor: deja $ X menos que la alternativa"), con la cifra en positivo; regla del bloque M. |
| El 7B califica ("buen proyecto", "rentable", "le conviene") | Medio | Hallazgo que dice que crear valor es un criterio y no una recomendación; reglas `no_contiene` en el bloque M. |
| "¿Me conviene el proyecto?" va a la ruta conceptual (criterio) | Medio | Regla del enrutador: si habla de "mi proyecto" o "el proyecto", `evaluar_proyecto`; casos de enrutamiento en el bloque M. |
| Mover la lectura del formulario rompe el tablero del flujo | Bajo | Los tests del tablero y de la web ya cubren el flujo; se mueven sin cambiar su comportamiento. |

## Preguntas abiertas

Ninguna.
