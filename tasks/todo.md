# Tareas: sensibilidad-proyecto

Plan: [plan.md](plan.md). Verificación común: `python -m pytest -v` antes del commit.

- [x] **1. Tornado y valores críticos (puro)**: caso a mano de la especificación;
  la tasa crítica es la TIR; VPN base negativo → cuánto mejorar; sin cruce → None.
  Archivos: `modules/proyectos/sensibilidad.py`, `modules/proyectos/matematica_financiera.py`,
  `tests/modules/proyectos/test_sensibilidad.py`.
- [x] **2. Escenario puntual y lectura de la pregunta**: "si los ingresos caen
  10 %…" en palabras; `variable_del_proyecto` y `direccion`.
  Archivos: `modules/proyectos/sensibilidad.py`, `app/orchestrator/lectura.py`, tests.
- [ ] **3. Pestaña "Sensibilidad"**: tornado ordenado, tabla y valores críticos del
  proyecto de la sesión; sin tasa → mensaje.
  Archivos: `frontend/tableros.py`, `frontend/templates/_pestana_sensibilidad.html`,
  `frontend/static/estilo.css`, tests del frontend.
- [ ] **4. Chat, glosario, nota y bloque N** (después del set completo).
  Archivos: `app/orchestrator/tools_registry.py`, `config/prompts/router.md`,
  `config/glosario.yaml`, `conocimiento/evaluacion-de-proyectos.md`,
  `tests/eval/preguntas.yaml`, tests.

### Punto de control: completo
- [ ] Criterios de éxito de la especificación; documentación de cierre.
