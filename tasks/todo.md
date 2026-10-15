# Tareas: flujo-proyecto

Plan: [plan.md](plan.md). Verificación común de cada tarea:
`python -m pytest -v` en verde antes del commit.

## Fase 1: datos de inflación

- [x] **1. Meta de inflación en el catálogo**
  - Aceptación: `serie("meta_inflacion")` devuelve la serie 853 de SUAMECA
    (3 %); `actualizar()` la incluye; copia de respaldo en `data/series/`.
  - Verificar: `python -m pytest tests/data_sources -v`
  - Archivos: `config/series.yaml`, `data/series/meta_inflacion_nacional.json`,
    `tests/data_sources/externos/test_series.py`
  - Tamaño: XS

- [x] **2. Pronóstico de inflación del Informe de Política Monetaria**
  - Cambio del 15/10/2026: el repositorio del BanRep bloquea las descargas
    automáticas (anti-bots), así que el Excel se carga a mano cada trimestre.
  - Aceptación: lectura del Excel por etiquetas con fixture recortado del
    real de julio de 2026 (2026: 6,9 %; 2027: 4,3 %); formato desconocido →
    error útil; `python -m data_sources.externos.pronostico_banrep
    <archivo>` guarda la copia versionada (mes y año desde el nombre del
    archivo o con `--mes`/`--anio`); aviso si el informe tiene más de 4 meses;
    sin copia → error con las instrucciones.
  - Archivos: `data_sources/externos/pronostico_banrep.py`,
    `data_sources/externos/series/catalogo.py` (escritura atómica
    compartida), `data/series/pronostico_inflacion.json`,
    `tests/data_sources/externos/test_pronostico_banrep.py`,
    `tests/data_sources/externos/datos/ipm_julio_2026.xlsx`
  - Tamaño: M

## Fase 2: cálculo

- [x] **3. Senda de inflación**
  - Aceptación: `senda_inflacion(hoy, horizonte, pronostico, meta, fija=None)`
    → (π por año, supuestos, fuentes); en octubre de 2026 con el informe de
    julio: año 1 = 4,3 %, siguientes = 3 %; con `fija` todos iguales; sin
    pronóstico, solo la meta con supuesto.
  - Verificar: `python -m pytest tests/modules/proyectos -v`
  - Archivos: `modules/proyectos/flujo.py`, `tests/modules/proyectos/test_flujo.py`
  - Tamaño: S

- [ ] **4. Proyecto y flujo de caja libre**
  - Aceptación: `Proyecto` valida rangos (horizonte 1-30, vida útil 1-50,
    porcentajes 0-100, inversión > 0) con mensajes útiles;
    `flujo_caja(proyecto, senda)` da la tabla por año en pesos de hoy y en
    corrientes; el caso a mano de la especificación (π = 0 y π = 3 % fija);
    propiedades: π > 0 baja el flujo en pesos de hoy, vida útil mayor que el
    horizonte pasa el valor en libros al salvamento, salvamento de mercado
    paga la tarifa sobre la ganancia, pérdida → impuesto negativo y supuesto.
  - Verificar: `python -m pytest tests/modules/proyectos -v`
  - Depende de: 3
  - Archivos: `modules/proyectos/flujo.py`, `tests/modules/proyectos/test_flujo.py`
  - Tamaño: M

### Punto de control: cálculo
- [ ] Suite completa en verde.
- [ ] Caso a mano listo para que el usuario lo concilie (no bloquea).

## Fase 3: tablero

- [ ] **5. Pestañas en el tablero de Proyectos**
  - Aceptación: "Su proyecto" (por defecto) y "Crédito y tasas" (simulador y
    conversor, sin cambios); `?pestana=credito` abre la segunda; valor
    desconocido → "Su proyecto"; HTMX cambia solo el contenido y empuja la
    dirección; marcado `role="tablist"` y `aria-selected`.
  - Verificar: suite (TestClient) + captura de la página
  - Archivos: `frontend/tableros.py`, `frontend/web.py`,
    `frontend/templates/_tablero_proyectos.html`,
    `frontend/static/estilo.css`, `tests/frontend/test_web.py`
  - Tamaño: S

- [ ] **6. Pestaña "Su proyecto": formulario y flujo**
  - Aceptación: formulario con el ejemplo de la especificación; la inflación
    por defecto es la senda del BanRep (se ve cuál se usó y su fuente) y se
    puede reemplazar por una fija; `POST /proyectos/flujo` recalcula solo la
    tabla en pesos de hoy (ingresos, costos, depreciación, utilidad
    operativa, impuesto, capital de trabajo, salvamento, flujo de caja
    libre); errores con mensaje útil; el proyecto válido queda en la sesión.
  - Verificar: suite + captura de la página
  - Depende de: 2, 4, 5
  - Archivos: `frontend/tableros.py`, `frontend/web.py`,
    `frontend/templates/_tablero_proyectos.html`,
    `frontend/templates/_flujo.html`, `tests/frontend/test_tableros.py`,
    `tests/frontend/test_web.py`
  - Tamaño: M

### Punto de control: completo
- [ ] Criterios de éxito 1-4 de la especificación.
- [ ] CLAUDE.md, `docs/decisiones.md` y `docs/modulos/evaluacion-proyectos.md`.
