# Tareas: matematica-financiera

Plan: [plan.md](plan.md). Verificación común de cada tarea:
`python -m pytest -v` en verde antes del commit.

## Fase 1: cimientos

- [x] **1. Tasas equivalentes**
  - Aceptación: `a_periodica(tasa, tipo)` → (periódica vencida, periodos al
    año) y `convertir(tasa, desde, hacia)` para EA, periódicas (mensual,
    trimestral, semestral), nominales vencidas (NMV, NTV, NSV) y anticipadas
    (MA, NMA, TA, NTA); los cinco casos de tasas de la especificación;
    ida y vuelta < 1e-12; tipo desconocido → error con mensaje útil.
  - Verificar: `python -m pytest tests/modules/proyectos -v`
  - Archivos: `modules/proyectos/__init__.py`,
    `modules/proyectos/matematica_financiera.py`,
    `tests/modules/proyectos/__init__.py`,
    `tests/modules/proyectos/test_matematica_financiera.py`
  - Tamaño: S

- [x] **2. Indicadores de proyectos**
  - Aceptación: `vpn`, `tir` (única, o `None` con advertencia si no hay o hay
    varias: −100, 230, −132 nombra 10 % y 20 %), `tirm`,
    `recuperacion_descontada` (interpolada; `None` si no se recupera),
    `indice_rentabilidad` (`None` si F0 ≥ 0), `valor_anual_equivalente`;
    flujos −1.000, 300, 400, 500, 200 al 10 % → VPN 115,57 y TIR 15,32 %.
  - Verificar: `python -m pytest tests/modules/proyectos -v`
  - Depende de: 1
  - Archivos: los mismos dos de la tarea 1
  - Tamaño: S

- [x] **3. Amortización de créditos**
  - Aceptación: `amortizacion(monto, tasa_periodica, n, sistema)` con cuota
    fija y abono constante; casos de la especificación ($ 4.934.680 y
    $ 96.080.819; $ 6.111.019, $ 3.379.628 y $ 84.719.425); abonos = monto,
    saldo final 0 ± 1 peso, interés = saldo inicial × tasa.
  - Verificar: `python -m pytest tests/modules/proyectos -v`
  - Depende de: 1
  - Archivos: los mismos dos de la tarea 1
  - Tamaño: S

### Punto de control: cimientos
- [x] Suite completa en verde.
- [ ] Casos a mano listos para que el usuario los concilie (no bloquea).

## Fase 2: chat

- [x] **4. Lectura de la pregunta**
  - Aceptación: `tipo_de_tasa(pregunta)` reconoce EA, NMV, mes vencido,
    mensual, trimestral, anticipada…; "18 % anual" → EA con supuesto; sin
    tipo → `None`. `montos(pregunta)` lee "200 millones", "1.500 millones",
    "$200.000.000", "mil millones", "2,5 millones".
  - Verificar: `python -m pytest tests/app -v`
  - Archivos: `app/orchestrator/lectura.py`, `tests/app/test_lectura.py`
  - Tamaño: S

- [x] **5. Herramienta `simular_credito` de punta a punta**
  - Aceptación: análisis `simular_credito` → `ResultadoModulo` con cuota,
    intereses totales y proporción, hallazgos que nombran el tipo de tasa y el
    supuesto de seguros y comisiones; herramienta registrada sin periodo ni
    empresa; el orquestador acepta el monto de "200 millones" y descarta uno
    inventado; reglas del enrutador (crédito de la empresa ≠ fuera de
    alcance). Test con modelo falso de la pregunta del objetivo.
  - Verificar: suite + `python -m app.demo "¿Cuánto pago por un crédito de 200 millones al 18 % EA a 5 años?"`
  - Depende de: 3, 4
  - Archivos: `modules/proyectos/matematica_financiera.py`,
    `app/orchestrator/tools_registry.py`, `app/orchestrator/orquestador.py`,
    `config/prompts/router.md`, tests de orquestador
  - Tamaño: M

- [ ] **6. Herramienta `convertir_tasa` de punta a punta**
  - Aceptación: "¿2 % mensual cuánto es en efectivo anual?" → 26,82 % EA con
    hallazgo que nombra los dos tipos; `hacia` por defecto EA (o mensual si la
    tasa ya es EA); sin tipo reconocible → mensaje que pide aclararlo.
  - Verificar: suite + `python -m app.demo "¿2 % mensual cuánto es en efectivo anual?"`
  - Depende de: 1, 4
  - Archivos: `modules/proyectos/matematica_financiera.py`,
    `app/orchestrator/tools_registry.py`, `config/prompts/router.md`, tests
  - Tamaño: S

- [ ] **7. Nota de conocimiento y bloque L**
  - Aceptación: `conocimiento/tasas-equivalentes.md` (fórmulas en símbolos y
    en palabras; `revisado: false` hasta que el usuario la revise), índice RAG
    reconstruido; bloque L en `tests/eval/preguntas.yaml` (crédito EA, crédito
    "anual" ambiguo, abono constante, conversión, conceptual "¿qué es la
    EA?", invertir en acciones → fuera de alcance) y en `bloques_duros`.
  - Verificar: `python -m app.eval --bloques L` al 100 % con el modelo real
  - Depende de: 5, 6
  - Archivos: `conocimiento/tasas-equivalentes.md`, `tests/eval/preguntas.yaml`
  - Tamaño: S

### Punto de control: chat
- [ ] Las dos preguntas del objetivo se responden bien en el chat.
- [ ] Bloque L al 100 %; el resto del set sin regresiones en enrutamiento.

## Fase 3: tablero

- [ ] **8. Tablero de Proyectos con el simulador de crédito**
  - Aceptación: módulo `proyectos` activo con ejemplos de preguntas;
    formulario (monto, tasa, tipo, plazo, periodicidad, sistema) por HTMX →
    cuota, totales, tabla por año y tabla completa desplegable; errores de
    entrada con mensaje útil (monto ≤ 0, plazo fuera de rango).
  - Verificar: suite (TestClient) + revisión manual en el navegador
  - Depende de: 5
  - Archivos: `frontend/modulos.py`, `frontend/tableros.py`,
    `frontend/web.py`, `frontend/templates/_tablero_proyectos.html`,
    `tests/frontend/test_web.py`
  - Tamaño: M

- [ ] **9. Conversor de tasas en el tablero**
  - Aceptación: una tasa y su tipo → equivalentes (EA, mensual, NMV,
    trimestral, NTV, mes anticipado) con la fórmula en el título.
  - Verificar: suite + revisión manual
  - Depende de: 6, 8
  - Archivos: `frontend/tableros.py`, `frontend/web.py`,
    `frontend/templates/_tablero_proyectos.html`, `tests/frontend/test_web.py`
  - Tamaño: S

### Punto de control: completo
- [ ] Criterios de éxito 1-5 de la especificación.
- [ ] CLAUDE.md, `docs/decisiones.md` y `docs/modulos/evaluacion-proyectos.md`
      (estado: en construcción).
