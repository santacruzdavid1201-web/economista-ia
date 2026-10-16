# economista-ia

Sistema de IA que ofrece a empresas (pymes) los servicios de un economista.
Combina tres fuentes: datos de la empresa, datos externos (DANE, BanRep,
Supersociedades) y un metaprompt con el rol y las reglas del economista.

## Principio central

El LLM NO calcula. Interpreta la pregunta, elige el módulo, extrae parámetros
y redacta el resultado. Todo número sale de funciones de Python probadas.

## Arquitectura

- `modules/`: cálculos puros, sin LLM. Cada análisis devuelve un
  `ResultadoModulo` (`modules/base.py`) con: indicadores (valor, unidad,
  fórmula), hallazgos (conclusiones ya redactadas por Python para que el LLM
  no compare números), supuestos, fuentes y advertencias. Subcarpetas
  `balance/`, `macro/` y `proyectos/`.
- `modules/esquema_financiero.py`: esquema canónico de estados financieros
  (presentación NIIF corriente / no corriente). Toda fuente (PUC, Excel,
  Supersociedades) se traduce a este esquema; las fórmulas solo lo conocen.
- `data_sources/`: cargadores de datos de empresa (`empresa/puc.py`), el
  almacén en PostgreSQL (`almacen.py`: series diarias del PMS por NIT, carga
  incremental idempotente, lectura como `DataFrame`) y fuentes externas (`externos/`: Supersociedades, referencia sectorial, `series/` del
  BanRep y el DANE, pronóstico del BanRep).
- `config/`: mapeos (PUC y NIIF → esquema), grupos CIIU, catálogo de series,
  glosario y prompts (`config/prompts/`).
- `conocimiento/*.md`: notas revisadas por el usuario para el RAG (`app/rag/`).
- `app/`: `config.py` (variables de entorno), `llm/client.py` (API compatible
  con OpenAI), `orchestrator/` (enrutador, registro de herramientas, lectura
  de la pregunta, verificador de cifras), `eval/` (set de evaluación) y
  `main.py` (FastAPI; actualiza las series al arrancar y cada 6 horas).
- `frontend/`: interfaz Jinja + HTMX (`SPEC-interfaz.md`); `tableros.py` arma
  un tablero por módulo calculado solo con Python.
- `SPEC-*.md`: especificación de cada pieza; `tasks/`: plan de la pieza en curso.
- `exploracion/`: scripts exploratorios, no forman parte del sistema.
- Los archivos vacíos (`docker-compose.yml`, `db/`, `modules/econometria/`,
  `proyectos/wacc.py`...) son la arquitectura planeada: se llenan o se borran
  cuando llegue su pieza (decisión del usuario).
- PostgreSQL (desde el módulo 2, servidor local del usuario) para las series
  del PMS y el panel sectorial, confinado a `data_sources/`. Futuro: Docker
  para empaquetar la app y la base; pgvector si la base de conocimiento crece.

## Cómo responde el chat

Chat global, una conversación por sesión con memoria de 3 turnos. Cuatro tipos
de pregunta:

1. **Cálculo**: el enrutador elige una herramienta, Python calcula, el LLM
   redacta y el verificador revisa las cifras (un reintento; si falla, sale una
   respuesta de respaldo armada en Python). Supuestos y advertencias los agrega
   Python al final.
2. **Criterio o teoría**: RAG híbrido sobre `conocimiento/` (embeddings +
   palabras clave); sin nota pertinente responde en general con el aviso
   "Respuesta general". El rol (`config/prompts/rol.md`) es común a 1 y 2.
3. **Conversar**: saludos, comentarios sobre la respuesta anterior y temas
   ajenos (una o dos frases y reconduce).
4. **Fuera de alcance** (legal, tributario, en qué invertir, pronósticos):
   remite al profesional.

Sin empresa cargada (se sube en la portada) el chat no calcula sobre la
empresa; el panorama macro, el crédito, las tasas y el proyecto no la
necesitan (sin ella, el costo de capital es el de los activos).

## Módulos del MVP

Orden de construcción: 1 → 4 → 3 → 2.

1. Balance financiero: funcionando, probado con datos reales.
2. Econometría aplicada (pronóstico, demanda/precios, impacto con Double ML /
   Causal Forest): sin iniciar. Primero la capa de datos: los estados anuales
   dan 2 a 5 puntos; hacen falta series propias de mayor frecuencia (ventas,
   precios, ocupación) y externas. Incluye `sector-hotelero`.
3. Evaluación de proyectos: en construcción (`SPEC-mapa-proyectos.md`).
4. Entorno macro: funcionando (`SPEC-mapa-macro.md`).
5. Después: carteras de inversión (Black-Litterman).

## Convenciones

- Código, nombres y textos en español.
- Montos en positivo; el signo lo pone la fórmula (salvo patrimonio).
- Razones flujo/saldo usan saldo promedio (`HistorialFinanciero.saldo_promedio`)
  y anualizan flujos si el periodo < 12 meses. Si falta un dato, se usa el
  cierre y se registra como supuesto.
- Indicadores no calculables devuelven `None` con una advertencia; nunca un
  número engañoso.
- Sin umbrales genéricos de "bueno/malo": eso lo da el benchmark sectorial.
- Cada función nueva lleva tests en `tests/` con la misma estructura de
  carpetas. Correr `python -m pytest -v` antes de cada commit.
- Cada pieza nueva sigue el flujo de agent-skills: spec → plan en `tasks/` →
  tests primero → revisión del diff → commit por tarea. Los cálculos nuevos
  traen un caso a mano que el usuario concilia.
- Robustez por fases (definido por el usuario el 5/10/2026). En el MVP:
  variables de entorno para claves y configuración (nunca en el código),
  validación básica de toda entrada del usuario, separación de roles
  system/user en los prompts (la pregunta del usuario nunca va en el system)
  y manejo de errores con try/except y mensajes útiles. Rate limiting fino y
  monitoreo con dashboard se agregan cuando el producto tenga uso real.

## Reglas de redacción con el 7B

Lecciones de las corridas del set de evaluación (`tests/eval/preguntas.yaml`).

- Las distinciones de sentido van en hallazgos redactados por Python, no en el
  prompt: con el 7B la regla del prompt no basta. Ejemplos: el EBITDA en pesos
  "no se compara con el sector"; con la TRM, Python dice si el peso se revaluó
  o se devaluó; un escenario dice primero el estado actual ("sigue sin crear
  valor").
- Cada error de sentido nuevo se vuelve una regla del YAML del set.
- Menos cifras parecidas en los datos: se quitan las que no responden la
  pregunta, porque el 7B las mezcla.
- Valores formateados por unidad ("2,4 %", "53 días"); la tasa del usuario
  como la escribió ("24 %", no "24,00 %"); montos también con palabras
  ("$ 150.000.000 (150 millones)").
- Nominal y real en paralelo, sin compararlos con la inflación.
- Los análisis que no son de la empresa (crédito, tasas, panorama) se redactan
  sin su nombre.
- El benchmark es "empresas reportantes a Supersociedades", nunca el sector
  completo.
- Nunca recomendar. "Conviene", "rentable", las recetas ("debes usar") y los
  calificativos sin comparación sectorial están en `CALIFICATIVOS`
  (`verificador.py`): se pide reescribir y, si insiste, sale el respaldo. En el
  reintento el 7B cambia la palabra por un sinónimo ("usar" → "utilizar"): la
  lista lleva los dos.
- Una cifra con "$" y "%" a la vez ("$ 8,17 %") se rechaza y se nombra tal cual
  en el reintento.
- Ninguna cifra de memoria. El verificador acepta cifras de la pregunta, salvo
  en la charla, donde solo valen las de la conversación previa (los años son
  libres). Los enteros 0-10 con % o $ no quedan libres.
- El modelo solo da los números de la pregunta; su sentido (tipo de tasa,
  plazo, periodicidad, sistema, variable, dirección) lo lee Python
  (`app/orchestrator/lectura.py`). Se descartan argumentos numéricos que no
  están en la pregunta.
- Sin glosario el 7B inventa definiciones: todo indicador nuevo va en
  `config/glosario.yaml`. Las notas dan las fórmulas en símbolos y en palabras
  (el 7B copia la versión en palabras).
- LM Studio 1.1.8 no obliga a elegir herramienta: si el 7B contesta con texto,
  nota pertinente → conceptual, si no → charla. La cortesía se salta el
  enrutador. Hay tope de tokens.

## Comandos

- `.\iniciar.ps1`: arranque completo (abre la API de LM Studio y la interfaz).
  Solo la interfaz: `python -m uvicorn app.main:app --port 8000`.
- `python -m pytest -v`: tests.
- `python -m app.eval [--casos 13,14] [--bloques D,E]`: set de evaluación con
  el modelo real; informe en `data/eval/` (no versionado). Criterios: bloques
  A, B, C, F y G al 100 %; respaldo ≤ 20 %.
- `python -m app.demo "pregunta"`: una pregunta con el hotel ficticio
  (`data/demo/`, generado con `data/demo/generar_demo.py`).
- `python -m app.rag.ingest`: reconstruye el índice tras editar `conocimiento/`.
- `python -m data_sources.almacen`: crea o completa el esquema de PostgreSQL
  (`db/init.sql`). Conexión en `.env` (`DATABASE_URL`); los tests de la base usan
  `TEST_DATABASE_URL` (una base `*_test`) y se saltan sin ella.
- `python -m data_sources.externos.series.catalogo Pasto`: refresca las series.
- `python -m data_sources.externos.pronostico_banrep <archivo.xlsx>`: carga el
  pronóstico del Informe de Política Monetaria.

## Fuentes externas

| Dato | Fuente | Actualización |
|---|---|---|
| IPC nacional y 23 ciudades | SUAMECA 15000; 15013-15035 (Pasto 15026) | Nacional cada 6 h; ciudades al pedirlas |
| Tasa de política, IBR 3 meses, TRM | SUAMECA 59, 243, 1 | Cada 6 h |
| PIB (trimestral), desempleo (mensual, sin ajuste estacional) | SUAMECA 15271, 15312 | Cada 6 h |
| Meta de inflación | SUAMECA 853 | Cada 6 h |
| TES cero cupón UVR 10 años (tasa sin riesgo real del WACC) | SUAMECA 15277 | Cada 6 h |
| Spread de incumplimiento, prima total de Colombia y beta sin deuda del sector | Damodaran (`ctryprem`, `betaemerg.xls`), a mano en `config/costo_capital.yaml` | Cada enero |
| Pronóstico de inflación | Excel del Informe de Política Monetaria | A mano cada trimestre (el BanRep bloquea descargas automáticas); aviso a los 4 meses |
| Estados financieros de pares | datos.gov.co: carátula `6hqw-m3dm`, situación financiera `pfdp-zks5`, resultados `prwj-nzxa`, flujo `ctcp-462n` | Por año |

- Series: copias del día en `data/cache/series/` (no versionada, vigencia 1
  día); `data/series/` es el respaldo versionado para tests, demo y arranque
  sin red. SUAMECA no envía el certificado intermedio: `suameca_cadena.pem`.
- Supersociedades: valores en miles de pesos, solo cortes 31-dic; caché en
  `data/raw/supersociedades/`, referencia en `data/referencias/`; grupos en
  `config/ciiu_sectores.yaml`. Detalle en `exploracion/hallazgos_supersociedades.md`.

## Estado y siguiente paso

Se reemplaza al cerrar cada pieza; no se acumula (la historia va en
`docs/decisiones.md` y en git; la anterior al 16/10/2026, en `docs/bitacora.md`).

- Módulo 3 hecho: matemática financiera, flujo, evaluación, sensibilidad y
  costo de capital (WACC, 16/10/2026), conciliados a mano por el usuario.
  Monte Carlo después del módulo 2. Opción abierta: beta total (Damodaran)
  para el dueño de pyme no diversificado. Set completo (77 casos, bloques
  A-O) el 16/10/2026: todos al 100 %, respaldo 1 %.
- En curso: módulo 2 (econometría), mapa aprobado el 16/10/2026 en
  `SPEC-mapa-econometria.md`. Hecho `almacen-datos` (16/10/2026, revisado por
  el usuario en pgAdmin) y `calendario` (16/10/2026; festivos con reglas
  y vigencia en `config/calendario.yaml`, Ley 2578 de 2026 incluida y conciliada
  por el usuario; Carnaval de Pasto; revisar la decisión de la Corte sobre la
  Ley 2578 antes de 2027). En curso `series-empresa` (especificación aprobada).
- Pendientes: cargar el Informe de Política Monetaria de octubre (sale a fin
  de mes); bajar el contexto de LM Studio a 8.192 si vuelve a caerse; validar
  la referencia contra el SIIS y revisar valores extremos; plantilla Excel
  para empresas sin software contable.

## Documentación del proyecto (Obsidian)

Vault en `docs/`. Se actualiza solo en estos momentos, no en cada cambio menor:

1. Decisión de diseño o arquitectura (herramienta, enfoque, esquema de datos):
   una viñeta nueva en `docs/decisiones.md`, en el estilo de las existentes
   (breve, en pasado, con el qué y el porqué en una frase).
2. Un módulo cambia de estado (sin iniciar → en construcción → funcionando /
   probado con datos reales): actualizar **Estado** y agregar una nota breve
   en `docs/modulos/<módulo>.md` (econometria-aplicada, evaluacion-proyectos,
   entorno-macro, balance-financiero).
3. Al final de una sesión larga o con varios cambios importantes, si no se
   hizo en el momento, resumir en `decisiones.md` lo decidido.

No se documentan fixes menores, cambios de redacción, ajustes de formato ni
iteraciones de prueba y error que no cambiaron una decisión final. Si se
actualizó la documentación, decirlo en una línea al final de la respuesta.

Este archivo solo lleva instrucciones y el mapa del proyecto: lo que pasó va
en `docs/`, no aquí.

## Entorno

Windows, proyecto en `D:\economista-ia`, entorno virtual `.venv` con
Python 3.14 (si alguna librería no instala, usar 3.12). GPU AMD RX 6600 XT
(8 GB VRAM): LLM local qwen2.5-7b-instruct en LM Studio 1.1.8, fuera de
Docker; su API está en localhost:1235 (fijada en `.env`) y la abre
`iniciar.ps1`, no el CLI `lms`. Demo pública futura en Hugging Face Spaces
con LLM por API.

## Cómo trabajar conmigo

Soy economista (econometría, Python, SQL, Power BI). Explica el razonamiento
económico detrás de cada decisión, y ve paso a paso con herramientas que estoy
retomando (Docker, Git, terminal).
