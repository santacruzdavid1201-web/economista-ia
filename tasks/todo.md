# Tareas: costo-capital

Plan: [plan.md](plan.md). Verificación común: `python -m pytest -v` antes del commit.

- [x] **1. Costo de capital (puro)**: el caso a mano de la especificación (β apalancada
  1,325; Ke 14,25 %; Kd real 3,81 %; WACC real 10,77 %; equivalente nominal 15,53 %;
  Ku 11,95 %); sin deuda, WACC = Ke = Ku; deuda sin gastos financieros → Kd y WACC
  `None` con advertencia; patrimonio ≤ 0 → WACC `None`. La tasa implícita queda en
  una función compartida y los tests de sensibilidad-tasas siguen en verde.
  Archivos: `modules/proyectos/wacc.py`, `modules/balance/comun.py`,
  `modules/macro/sensibilidad_tasas.py`, `tests/modules/proyectos/test_wacc.py`.
- [ ] **2. Evaluación y sensibilidad con tasa real**: `tasa_tipo` en el formulario y
  en `ProyectoLeido`; con tasa real r, el VPN de los flujos en pesos de hoy es igual
  al de los flujos corrientes descontados con (1 + r)(1 + π_t) − 1 de cada año
  (test de consistencia); TIR real; los hallazgos dicen "real"; una tasa escrita en
  la pregunta vuelve a nominal.
  Archivos: `app/orchestrator/proyecto.py`, `modules/proyectos/evaluacion.py`,
  `modules/proyectos/sensibilidad.py`, `app/orchestrator/tools_registry.py`, tests.

### Punto de control: cálculos
- [ ] El usuario concilia el ejemplo a mano (criterio de éxito 1).

- [ ] **3. Datos del costo de capital** (necesita la beta): `tes_uvr_10` en el catálogo
  con su copia de respaldo; `config/costo_capital.yaml` con fuente y fecha; la senda
  del BanRep extraída de `leer_proyecto`; una función arma el costo de capital para
  el tablero y el chat (sin red en los tests).
  Archivos: `config/series.yaml`, `data/series/tes_uvr_10_nacional.json`,
  `config/costo_capital.yaml`, `app/orchestrator/proyecto.py`, `tests/app/test_proyecto.py`.
- [ ] **4. Bloque "Tasa de referencia" en Su proyecto**: con el hotel de demostración,
  el WACC con su desglose; sin empresa, Ku dicho como referencia; un botón pone la
  tasa real en el formulario y evalúa con ella.
  Archivos: `frontend/tableros.py`, `frontend/web.py`,
  `frontend/templates/_pestana_proyecto.html`, `frontend/static/estilo.css`,
  `tests/frontend/test_tableros.py`.

### Punto de control: tablero
- [ ] Criterio de éxito 2 con la interfaz real.

- [ ] **5. Chat, glosario, nota y bloque O**: herramienta `calcular_costo_capital`,
  reglas del enrutador, glosario (WACC, costo del patrimonio, costo de la deuda,
  beta, costo de los activos, prima de riesgo país), nota
  `conocimiento/costo-de-capital.md` para revisión del usuario, índice RAG, casos 70
  en adelante.
  Archivos: `app/orchestrator/tools_registry.py`, `config/prompts/router.md`,
  `config/glosario.yaml`, `conocimiento/costo-de-capital.md`,
  `tests/eval/preguntas.yaml`, tests.

### Punto de control: completo
- [ ] Bloque O al 100 % con el modelo real; set completo; suite en verde;
  documentación de cierre (criterios 3 y 4).
