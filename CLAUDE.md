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
  no compare números), supuestos, fuentes y advertencias.
- `modules/esquema_financiero.py`: esquema canónico de estados financieros
  (presentación NIIF corriente / no corriente). Toda fuente (PUC, Excel,
  Supersociedades) se traduce a este esquema; las fórmulas solo lo conocen.
- `config/`: mapeos y configuración (PUC → esquema, grupos CIIU, prompts).
- `data_sources/`: cargadores de datos de empresa (`empresa/puc.py`) y fuentes
  externas (`externos/supersociedades.py`, `externos/referencia.py`).
- `exploracion/`: scripts exploratorios, no forman parte del sistema.
- Futuro: `app/` (FastAPI + orquestador LangGraph o enrutador propio),
  `frontend/` (Streamlit), PostgreSQL + pgvector, Docker.

## Módulos del MVP

1. Balance financiero empresarial ← en construcción
2. Econometría aplicada (pronóstico, demanda/precios, evaluación de impacto
   con Double ML / Causal Forest)
3. Evaluación de proyectos (VPN, TIR, WACC, sensibilidad, Monte Carlo)
4. Entorno macro y sectorial
5. Después: carteras de inversión (Black-Litterman)

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
- Robustez por fases (definido por el usuario el 5/10/2026). En el MVP:
  variables de entorno para claves y configuración (nunca en el código),
  validación básica de toda entrada del usuario, separación de roles
  system/user en los prompts (la pregunta del usuario nunca va en el system)
  y manejo de errores con try/except y mensajes útiles. Rate limiting fino y
  monitoreo con dashboard se agregan cuando el producto tenga uso real.

## Estado actual

Hecho y probado (178 tests): esquema canónico, mapeo PUC, razones de liquidez,
endeudamiento, rentabilidad y actividad, ciclo de conversión de efectivo,
DuPont (con descomposición logarítmica de la variación del ROE), Z'' de
Altman para mercados emergentes (zonas 4,35 / 5,85 y equivalencia de
calificación de Altman y Hotchkiss 2005) y motor de benchmark
(`modules/balance/benchmark.py`: percentil de rango medio, dirección por
indicador, muestra mínima 10 / adecuada 30). El EBITDA es `None` si no se
reportó la depreciación; el impuesto admite negativos (beneficio). Con deuda
financiera y sin gastos financieros identificados, la carga financiera y la
cobertura son `None` (los intereses quedaron en otra cuenta).

## Siguiente paso: datos de Supersociedades para el benchmark

Datasets en datos.gov.co (formato largo: nit, concepto, valor, periodo,
fecha_corte, punto_entrada, taxonomia):
- `6hqw-m3dm` Carátula (verificar si el CIIU viene como concepto)
- `pfdp-zks5` Estado de Situación Financiera
- `prwj-nzxa` Estado de Resultado Integral
- `ctcp-462n` Flujo de Efectivo (más adelante)

Pasos 1-3 resueltos (detalle en `exploracion/hallazgos_supersociedades.md`):
CIIU como concepto de la carátula (`I5511 - ...`), cruce por NIT + fecha;
punto_entrada 10/20/40/50, solo cortes 31-dic, `Periodo Actual`; valores en
miles de pesos; ~300 hoteles por año a nivel nacional.

Paso 4 resuelto: `config/mapeo_niif.yaml` + cargador
`data_sources/externos/supersociedades.py` (descarga SoQL + transformación
pura con exclusiones motivadas). Carga 303 de 305 hoteles 2024. Ver sección 6
de los hallazgos. Todos los conceptos de un año salen de un solo reporte (el
propio antes que el comparativo; la retransmisión más reciente antes que la
original): mezclarlos duplicaba partidas. Acepta los reportes antiguos (hasta
2017), cuyo periodo viene como fecha ("2016-dic-31") o como año.

Paso 5 resuelto: `data_sources/externos/referencia.py`
(`referencia_supersociedades("hoteles", 2024)`): 303 hoteles, 19 indicadores
comparables, caché en `data/raw/supersociedades/` y referencia versionada en
`data/referencias/hoteles_2024.json`. La empresa se compara con
`homologar_empresa` (cartera y proveedores agregados como la taxonomía) y nunca
es su propio par. Días de proveedores y ciclo de conversión no se comparan en
servicios (`no_comparables` en `ciiu_sectores.yaml`). Los hallazgos formatean
valores por unidad ("2,4 %", "53 días") para que el 8B no los malinterprete.

Pendiente, en orden (acordado el 5/10/2026, ajustado el 7/10/2026):
1. ~~Cargador PUC~~ hecho: `data_sources/empresa/puc.py` lee el balance de
   prueba (Excel/CSV, saldo con signo o débito/crédito), suma solo cuentas
   hoja, exige que las clases 1-7 sumen cero, rechaza balances posteriores al
   cierre y acepta reclasificaciones de corto a largo plazo. Lee formatos
   reales de exportación: filas de título antes del encabezado, CSV con ";"
   o ",", UTF-8 o Windows-1252, números colombianos o ingleses (el formato se
   decide con toda la columna) y negativos con "-" o paréntesis; si "Cuenta"
   trae nombres, elige la columna que contiene códigos. El impuesto diferido
   (2725) es no corriente (NIC 1.56). Reclasificaciones permitidas en
   `RECLASIFICACIONES` (deuda, inversiones, deudores y otros pasivos a largo
   plazo; diferidos a corto plazo; PPE a propiedades de inversión). La
   interfaz pide la unidad del archivo (pesos o miles) y propone la fecha de
   corte a partir del nombre. Conciliado al peso contra Supersociedades con
   los CSV de prueba del usuario (SECOLINSA, NIT 830010665, 2015-2016; copia
   local en `data/raw/prueba/`, no versionada). Falta: plantilla
   Excel propia para empresas sin software contable.
   Caso de demostración: `data/demo/hotel_demo_andino_{2023,2024}.csv`
   (empresa ficticia, generada con `data/demo/generar_demo.py`).
2. Versión delgada de punta a punta (en curso). Hecho: `app/config.py`
   (variables de entorno, `.env.example`), `app/llm/client.py` (API compatible
   con OpenAI; LM Studio con qwen2.5-7b-instruct en localhost:1234),
   `app/orchestrator/` (registro de herramientas, orquestador, verificador de
   cifras con un reintento y respuesta de respaldo armada en Python),
   `config/prompts/`, `config/glosario.yaml` y `app/demo.py`
   (`python -m app.demo "pregunta"`). Supuestos y advertencias los agrega
   Python al final; el LLM solo redacta. Lecciones con el modelo real: 8/8 en
   enrutamiento; inventó una definición sin glosario; el verificador atrapa
   cifras inventadas, pero no errores de sentido (p. ej. confundir "mejor que
   el 78 % de los pares" con un margen de 78 %). Interfaz: `streamlit run
   frontend/app.py` (hotel de demostración o balances subidos, con validación
   de archivos); arranque completo con `.\iniciar.ps1`.
   Tres tipos de pregunta (acordado el 6/10/2026): (1) cálculo con
   herramientas de Python; (2) criterio o teoría respondido SOLO con la base
   de conocimiento `conocimiento/*.md` (RAG híbrido: embeddings nomic de LM
   Studio + palabras clave; índice en `data/conocimiento/indice.json`, se
   reconstruye con `python -m app.rag.ingest`; sin nota pertinente no
   responde); (3) fuera de alcance con remisión al profesional. El rol del
   economista está en `config/prompts/rol.md`, común a la redacción de los
   tipos 1 y 2. Los análisis temáticos incluyen la comparación sectorial
   cuando hay referencia. Las 9 notas iniciales son borradores con
   `revisado: false`: el usuario debe revisarlas.
   Set de evaluación (hecho el 7/10/2026): `tests/eval/preguntas.yaml` (las 28
   preguntas del guion de prueba en 7 bloques A-G; 9 y 10 son pares de
   consistencia) y `app/eval/` (`python -m app.eval`, con `--casos` o
   `--bloques`; informe en `data/eval/`, no versionado). Python comprueba
   herramienta, periodo, origen, fuentes, frases y que toda cifra redactada
   esté en el desplegable (más estricto que el verificador, que acepta cifras
   de la pregunta). El sentido lo revisa el usuario en la sección "Respuestas
   para revisar" del informe. Criterios: bloques A, B, C, F y G al 100 %;
   respaldo ≤ 20 %. Primera corrida con qwen 7B: 30/30 en reglas automáticas,
   0 % respaldo, pero un error de sentido (presentó el margen EBITDA como "el
   EBITDA"); se agregó el EBITDA en pesos como indicador. Después le pegó al
   monto el percentil del margen: la regla en el prompt no bastó, sí un
   hallazgo redactado en Python ("no se compara con el sector"). Lección:
   con el 7B, las distinciones de sentido van en hallazgos, no en el prompt.
   Cuando se encuentre un error de sentido nuevo, convertirlo en regla del YAML.
3. Revisar las 9 notas de conocimiento (`revisado: true`).
4. Validar la referencia contra los indicadores que publica el SIIS, y
   revisar valores extremos (p. ej. hoteles con depreciación > ingresos).
5. Plantilla Excel para empresas sin software contable.
6. Módulos 4 → 3 → 2 (macro, proyectos, econometría).

Grupos de comparación en `config/ciiu_sectores.yaml` (alojamiento / hoteles).
El benchmark se describe siempre como "empresas reportantes a
Supersociedades", nunca como el sector completo. Probablemente será nacional:
Nariño tendrá muy pocas empresas.

## Entorno

Windows, proyecto en `D:\economista-ia`, entorno virtual `.venv` con
Python 3.14 (si alguna librería no instala, usar 3.12). GPU AMD RX 6600 XT
(8 GB VRAM): el LLM local será un modelo 7-8B (Qwen) vía Ollama con Vulkan o
LM Studio, corriendo fuera de Docker. Demo pública futura en Hugging Face
Spaces con LLM por API.

## Cómo trabajar conmigo

Soy economista (econometría, Python, SQL, Power BI). Explica el razonamiento
económico detrás de cada decisión, y ve paso a paso con herramientas que estoy
retomando (Docker, Git, terminal).
