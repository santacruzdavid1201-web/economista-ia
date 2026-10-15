# Tareas: evaluacion-proyecto

Plan: [plan.md](plan.md). Verificación común de cada tarea:
`python -m pytest -v` en verde antes del commit.

## Fase 1: cálculo

- [x] **1. Evaluación pura**
  - Aceptación: `evaluar(flujo, tasa) -> ResultadoModulo` con VPN (pesos de
    hoy), TIR nominal, TIRM, recuperación descontada e índice de
    rentabilidad, cada uno con su fórmula; caso a mano (π = 0, 10 %): VPN
    $ 3.109.400, TIR 11,11 %, TIRM 10,64 %, recuperación 4,85 años, índice
    1,03; hallazgos: crea valor / no crea valor (cifra en positivo y en
    palabras), TIR frente a la tasa solo con TIR única, recuperación dentro o
    fuera del horizonte; coherencia nominal-real; supuesto de la TIRM.
  - Verificar: `python -m pytest tests/modules/proyectos -v`
  - Archivos: `modules/proyectos/evaluacion.py`,
    `tests/modules/proyectos/test_evaluacion.py`
  - Tamaño: S

- [x] **2. Lectura compartida del proyecto**
  - Aceptación: `app/orchestrator/proyecto.py` convierte los valores del
    formulario (montos con palabras, porcentajes, años, inflación vacía o
    fija, tasa de oportunidad) en proyecto, senda, tasa, fuentes y avisos, o
    en mensajes de error; `tableros.flujo` la usa sin cambiar su
    comportamiento; tasa de oportunidad vacía, inválida o fuera de 0-100 % →
    mensaje útil.
  - Verificar: `python -m pytest tests/app tests/frontend -v`
  - Archivos: `app/orchestrator/proyecto.py`, `frontend/tableros.py`,
    `tests/app/test_proyecto.py`, `tests/frontend/test_tableros.py`
  - Tamaño: M

## Fase 2: tablero

- [x] **3. Evaluación en la pestaña "Su proyecto"**
  - Aceptación: campo "Tasa de oportunidad (% efectiva anual)" en Supuestos
    (ejemplo 15); arriba de la tabla del flujo, tarjetas con VPN, TIR, TIRM,
    recuperación e índice y los hallazgos; el aviso "Los valores iniciales
    son un ejemplo: reemplácelos por los de su proyecto" en las dos pestañas.
  - Verificar: suite (TestClient) + captura de la página
  - Depende de: 1, 2
  - Archivos: `frontend/tableros.py`, `frontend/templates/_pestana_proyecto.html`,
    `frontend/templates/_flujo.html`, `frontend/templates/_pestana_credito.html`,
    `tests/frontend/test_tableros.py`, `tests/frontend/test_web.py`
  - Tamaño: M

### Punto de control: tablero
- [x] Suite completa en verde y captura revisada.
- [x] Caso a mano listo para que el usuario lo concilie (no bloquea).

## Fase 3: chat

- [ ] **4. Herramienta `evaluar_proyecto`**
  - Aceptación: `responder(..., proyecto=...)` pasa el proyecto a las
    herramientas; `evaluar_proyecto` lo evalúa (tasa de la pregunta si la da,
    descartada si no está en ella); sin proyecto → mensaje que remite a la
    pestaña; la web pasa el de la sesión y el set de evaluación el de
    ejemplo; reglas del enrutador y glosario (VPN, TIR, TIRM, recuperación,
    índice).
  - Verificar: `python -m pytest tests/app -v` + `python -m app.demo`
  - Depende de: 1, 2
  - Archivos: `app/orchestrator/tools_registry.py`,
    `app/orchestrator/orquestador.py`, `frontend/web.py`,
    `app/eval/evaluador.py`, `config/prompts/router.md`,
    `config/glosario.yaml`, `tests/app/test_orquestador.py`
  - Tamaño: M

- [ ] **5. Nota de conocimiento y bloque M**
  - Aceptación: `conocimiento/evaluacion-de-proyectos.md` (`revisado:
    false`), índice reconstruido; bloque M en `tests/eval/preguntas.yaml`
    (¿me conviene?, ¿cuál es la TIR?, ¿en cuánto recupero?, ¿y si mi tasa es
    20 %?, ¿qué es la TIR?, ¿qué es mejor, VPN o TIR?) y en `bloques_duros`.
  - Verificar: `python -m app.eval --bloques M` al 100 % con el modelo real
  - Depende de: 4
  - Archivos: `conocimiento/evaluacion-de-proyectos.md`, `tests/eval/preguntas.yaml`,
    `tests/app/test_evaluador.py`
  - Tamaño: S

### Punto de control: completo
- [ ] Criterios de éxito de la especificación (el 1 espera la conciliación).
- [ ] CLAUDE.md, `docs/decisiones.md` y `docs/modulos/evaluacion-proyectos.md`.
