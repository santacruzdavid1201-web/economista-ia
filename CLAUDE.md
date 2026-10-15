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
- `app/main.py` (FastAPI) sirve la interfaz web de `frontend/` (plantillas
  Jinja + HTMX, ver `SPEC-interfaz.md`).
- Futuro: PostgreSQL + pgvector, Docker.

## Módulos del MVP

1. Balance financiero empresarial (funcionando)
2. Econometría aplicada (pronóstico, demanda/precios, evaluación de impacto
   con Double ML / Causal Forest)
3. Evaluación de proyectos (VPN, TIR, WACC, sensibilidad, Monte Carlo) ← en construcción
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

Hecho y probado (179 tests): esquema canónico, mapeo PUC, razones de liquidez,
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
   con OpenAI; LM Studio con qwen2.5-7b-instruct; desde su actualización a
   1.1.8 "Bionic" del 12/10/2026 la API está en localhost:1235, fijado en
   `.env`, y el CLI `lms` ya no la enciende: la abre `iniciar.ps1`),
   `app/orchestrator/` (registro de herramientas, orquestador, verificador de
   cifras con un reintento y respuesta de respaldo armada en Python),
   `config/prompts/`, `config/glosario.yaml` y `app/demo.py`
   (`python -m app.demo "pregunta"`). Supuestos y advertencias los agrega
   Python al final; el LLM solo redacta. Lecciones con el modelo real: 8/8 en
   enrutamiento; inventó una definición sin glosario; el verificador atrapa
   cifras inventadas, pero no errores de sentido (p. ej. confundir "mejor que
   el 78 % de los pares" con un margen de 78 %). Interfaz web (12/10/2026,
   reemplazó a Streamlit por su parpadeo al recargar y sus límites de diseño):
   `python -m uvicorn app.main:app --port 8000`, o arranque completo con
   `.\iniciar.ps1`. FastAPI + Jinja + HTMX (vendorizado en
   `frontend/static/`): portada con módulos ilustrados (Balance y Entorno
   macro activos; Proyectos y Econometría "próximamente"), navegación sin
   recargar (View Transitions) y la respuesta pedida en un segundo paso
   porque el modelo tarda. Desde el 13/10/2026 el chat es global (burbuja
   flotante fuera de `#pagina`, una conversación por sesión con memoria de 3
   turnos) y cada módulo será un tablero calculado solo con Python. Paleta menta y coral
   sobre gris azulado, Outfit y Manrope, ilustraciones SVG propias en
   `frontend/static/ilustraciones/`. Cada cifra de la respuesta muestra su
   indicador y fórmula (`frontend/cifras.py`, que escapa el HTML del modelo).
   Sesiones en memoria. Desde el 13/10/2026 la sesión empieza sin empresa:
   los balances se suben en la tarjeta "Su empresa" de la portada y cada
   archivo se lee al momento (activo, pasivo y patrimonio, o su error); sin
   empresa el chat conversa pero no calcula. El hotel ficticio queda solo
   para el set de evaluación y `app/demo.py`.
   Tipos de pregunta (acordado el 6/10/2026, ampliado el 13/10/2026): (1)
   cálculo con herramientas de Python; (2) criterio o teoría con la base de
   conocimiento `conocimiento/*.md` (RAG híbrido: embeddings nomic de LM
   Studio + palabras clave; índice en `data/conocimiento/indice.json`, se
   reconstruye con `python -m app.rag.ingest`); sin nota pertinente responde
   en general con el aviso "Respuesta general"; (3) `conversar`: saludos,
   charla, comentarios sobre la respuesta anterior y temas ajenos (una o dos
   frases y reconduce), con `config/prompts/conversacion.md`; (4) fuera de
   alcance (legal, tributario, en qué invertir, pronósticos) con remisión al
   profesional. Ninguna cifra de memoria: en la charla solo valen las de la
   conversación previa, ni siquiera las de la pregunta. El rol del
   economista está en `config/prompts/rol.md`, común a la redacción de los
   tipos 1 y 2. Los análisis temáticos incluyen la comparación sectorial
   cuando hay referencia. Las 9 notas fueron revisadas por el usuario el
   7/10/2026 (`revisado: true`), con ajustes para Colombia (tarifa general de
   renta, tasa de usura, indexación al IPC y al salario mínimo, MMH del DANE).
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
3. ~~Revisar las 9 notas de conocimiento~~ hecho el 7/10/2026.
4. Validar la referencia contra los indicadores que publica el SIIS, y
   revisar valores extremos (p. ej. hoteles con depreciación > ingresos).
5. Plantilla Excel para empresas sin software contable.
   Pendiente para el módulo 2 (pedido del usuario el 13/10/2026): definir la
   capa de datos de econometría. Los estados financieros anuales dan muy
   pocas observaciones para estimar (2 a 5 puntos); los modelos necesitan
   series propias de mayor frecuencia (ventas, precios, ocupación,
   promociones; p. ej. del software del hotel) más series externas, y una
   forma de cargarlas y guardarlas (probable disparador de PostgreSQL).
6. Módulos 4 → 3 → 2 (macro, proyectos, econometría). El 4 se adelantó a los
   pasos 4 y 5 (decidido el 11/10/2026). Mapa en `SPEC-mapa-macro.md`.
   Hecho: `series-externas` con el IPC (`data_sources/externos/series/`):
   SUAMECA del BanRep (nacional 15000 desde 1954; 23 ciudades 15013-15035
   desde 2017, Pasto 15026), verificado contra el anexo del DANE, copias
   de respaldo versionadas en `data/series/` (desde el 15/10/2026 la copia del
   día va a `data/cache/series/`, vigencia 1 día; sin red usa la copia más
   reciente con advertencia). La ciudad sin serie o sin cobertura cae al nacional con
   supuesto. SUAMECA no envía el certificado intermedio: se usa la cadena de
   DigiCert en `suameca_cadena.pem`. Refrescar: `python -m
   data_sources.externos.series.catalogo Pasto`.
   Hecho `crecimiento-real` (`modules/macro/crecimiento_real.py`, herramienta
   `analizar_crecimiento_real`, IPC de `municipio` de la empresa, bloque H del
   set de evaluación, casos 29-32). Conciliado con el cálculo a mano del
   usuario (11/10/2026). Errores de sentido corregidos el 12/10/2026: el
   hallazgo de Python ya no dice "vendió más" (con el IPC general, crecer en
   términos reales es subir más que los precios al consumidor, no vender más
   cantidad) y un segundo hallazgo lo advierte. El hallazgo da nominal y real
   en paralelo, sin compararlos con la inflación: cuando lo hacía, el 7B decía
   que "el crecimiento real superó la inflación". Nota nueva
   `conocimiento/crecimiento-real.md` con la fórmula exacta en símbolos y en
   palabras (el 7B copia la versión en palabras); revisada por el usuario el
   13/10/2026, que pidió precisar que la resta solo sirve con tasas bajas y
   agregar la ecuación de Fisher. El verificador ya no deja libres los
   enteros 0-10 cuando llevan % o $ (así pasó un ejemplo inventado). Bloque
   H: 4/4 en dos corridas con reglas nuevas (sin "volumen"; nominal y real
   en 30; "1 más el crecimiento nominal" en 32).
   Hecho `sensibilidad-tasas` (12/10/2026, `modules/macro/sensibilidad_tasas.py`,
   herramienta `analizar_sensibilidad_tasas` con argumento opcional `puntos`,
   bloque I, casos 33-39): tasa de política (SUAMECA 59) e IBR a 3 meses (243)
   en series-externas; exposición máxima; escenarios ±1/±2/±3, el pedido (solo
   ese) y el histórico de la IBR (+8,24 puntos en 2022). El orquestador descarta
   argumentos numéricos que no están en la pregunta. Lección: con el 7B, menos
   cifras parecidas en DATOS (quitar las que no responden la pregunta) evita
   que las mezcle. Los calificativos sin comparación sectorial
   ("significativo", "preocupante"...) los atrapa el verificador con un
   reintento que nombra las palabras (`CALIFICATIVOS` en `verificador.py`); si
   el modelo insiste, sale el respaldo. El caso 18 ("¿cómo me afecta que el
   BanRep suba las tasas?") acepta la herramienta o la nota. Set completo (41
   casos) el 12/10/2026: todos los bloques al 100 %, respaldo 3 %. El
   13/10/2026 se agregó el bloque J (conversación, casos 40-45; `despues_de`
   da a un caso la conversación de otro) y se ajustaron los casos 20, 27, 28
   y 38. Set completo (47 casos) con el modelo real el 13/10/2026, tras la
   actualización de LM Studio: cálculo y macro al 100 %, respaldo 3 %; de 5
   fallas, 2 fueron caídas de LM Studio ("Channel Error", probable falta de
   VRAM con contexto de 32.768) y 3 se corrigieron (19, 26, 42); la corrida
   de los casos afectados pasó completa. Lecciones: LM Studio 1.1.8 no obliga
   a elegir herramienta y el 7B contesta saludos con texto y puede desbordarse
   (tope de tokens; si contesta con texto, nota pertinente → conceptual, si no
   → charla; la cortesía se salta el enrutador); en la charla los años son
   libres, pero no porcentajes ni montos de la pregunta.
   Rediseño de la interfaz antes del módulo 3 (decidido el 13/10/2026; el
   módulo 3 se corre unos días y nace con el patrón nuevo): (a) chat global
   y conversacional, hecho; (b) tablero de Balance, hecho el 13/10/2026
   (`frontend/tableros.py` + `_tablero_balance.html`: tarjetas con cambio
   anual y posición sectorial, franja p25-p75 con mediana y empresa por
   indicador, palancas DuPont y tabla por año; gráficas en HTML y CSS); (c)
   tablero Macro, hecho el 13/10/2026: `panorama-macro`
   (`modules/macro/panorama.py`, herramienta `consultar_panorama_macro`, que
   no necesita empresa; bloque K, casos 46-50) con inflación (IPC 15000), tasa
   de política (59), IBR (243), TRM (1), crecimiento del PIB (15271,
   trimestral) y desempleo (15312, mensual, sin ajuste estacional: se compara
   con el mismo mes del año anterior); tarjetas con línea de tendencia de 3
   años (SVG simple) y, con empresa, crecimiento real y escenarios de tasas.
   Error de sentido corregido con un hallazgo: con la TRM a la baja el 7B
   escribió "depreciación del peso"; ahora Python dice si el peso se revaluó
   o se devaluó. `sector-hotelero` (MMH + panel de Supersociedades + SQL)
   pasa al módulo 2, que usa la misma infraestructura.
   Actualización diaria del entorno macro (hecha el 15/10/2026, tercer tramo
   de `SPEC-series-externas.md`): `app/main.py` llama a
   `catalogo.actualizar()` al arrancar y cada 6 horas, en un hilo y una serie
   tras otra (un candado también la separa de las consultas). Copias del día
   en `data/cache/series/` (ignorada por Git, escritura atómica);
   `data/series/` queda como respaldo de tests, demo y arranque sin red;
   vigencia de 1 día como red de seguridad; el tablero dice "Datos
   consultados el …" (la serie más vieja). El chat lee las mismas copias. El
   IPC de las ciudades no entra en el actualizador: la vigencia lo renueva al
   pedirlo. Probado con la interfaz real: 6 series del 15/10/2026.
   Módulo 3 (desde el 15/10/2026), con el flujo de agent-skills (spec → plan
   en `tasks/` → tests primero → revisión del diff → commit por tarea). Mapa
   aprobado en `SPEC-mapa-proyectos.md`: matematica-financiera →
   flujo-proyecto → evaluacion-proyecto → costo-capital →
   sensibilidad-proyecto → montecarlo-proyecto. Decisiones: el proyecto entra
   por formulario del tablero; flujos a precios de hoy con tasa real (Fisher
   con la expectativa de inflación de la encuesta del BanRep); costo del
   patrimonio por CAPM en pesos (TES 10 años + beta de Damodaran) o la tasa de
   oportunidad del dueño. Hecho `matematica-financiera`
   (`modules/proyectos/matematica_financiera.py`, conciliado a mano por el
   usuario el 15/10/2026): tasas equivalentes en 11 tipos, VPN, TIR (única o
   `None` con aviso si hay varias o ninguna; malla y bisección, sin scipy),
   TIRM, recuperación descontada, índice de rentabilidad, VAE y amortización
   (cuota fija y abono constante). En el chat, `simular_credito` y
   `convertir_tasa`, sin empresa: el modelo solo da los números de la
   pregunta; el tipo de tasa (pegado al número), la unidad del plazo, la
   periodicidad, el sistema y el destino de la conversión los lee Python
   (`app/orchestrator/lectura.py`); "200 millones" vale como 200 o 200000000;
   "anual" sin más es EA con supuesto. La pregunta llega a la herramienta en
   sus argumentos. Bloque L del set (casos 51-58): 8/8 con el modelo real.
   Lecciones: la tasa del usuario va en los hallazgos como la escribió ("24 %",
   no "24,00 %"), porque el 7B la repite así; los análisis que no son de la
   empresa (crédito, tasas, panorama) se redactan sin su nombre (lo mezcló en
   una conversión). Tablero de Proyectos activo: simulador de crédito y
   conversor de tasas (HTMX que recalcula solo el resultado). Nota
   `conocimiento/tasas-equivalentes.md` revisada por el usuario.
   Hecho `flujo-proyecto` (15/10/2026, `modules/proyectos/flujo.py`): flujo
   de caja libre sin la financiación, incremental, a precios de hoy por fuera
   y en pesos corrientes por dentro (la inflación le quita valor al ahorro de
   impuestos de la depreciación y el capital de trabajo crece con los
   precios); pérdidas que ahorran impuestos (supuesto), valor en libros al
   salvamento y salvamento de mercado que tributa (aproximación). Inflación:
   senda del BanRep = pronóstico del IPC total del último Informe de Política
   Monetaria (`data_sources/externos/pronostico_banrep.py`) y meta de 3 %
   (SUAMECA 853, `meta_inflacion`) después; el año t del proyecto es el año
   calendario actual + t. El repositorio del BanRep bloquea las descargas
   automáticas (anti-bots): el Excel "principales variables del pronóstico"
   se descarga en el navegador cada trimestre y se carga con `python -m
   data_sources.externos.pronostico_banrep <archivo.xlsx>` (copia versionada
   en `data/series/pronostico_inflacion.json`; aviso a los 4 meses). Cargado
   el de julio de 2026 (6,9 % en 2026, 4,3 % en 2027); el de octubre sale a
   fin de mes. Tablero de Proyectos en pestañas (pedido del usuario): "Su
   proyecto" (formulario agrupado y tabla del flujo con la columna de
   etiquetas fija; la sesión recuerda el último proyecto válido) y "Crédito
   y tasas". Sin herramienta de chat todavía: llega con la evaluación.
   Siguiente: `evaluacion-proyecto` (VPN, TIR, TIRM, recuperación con la tasa
   de oportunidad del usuario, en la pestaña "Su proyecto" y en el chat).
   Después, la comparación con la tasa de usura si hay fuente automática.
   Pendiente menor: bajar el contexto del modelo en LM Studio a 8.192 si
   vuelve a caerse.
   Sensibilidad-tasas conciliada con el cálculo a mano del usuario (demo 2024,
   13/10/2026): tasa implícita, aumento por punto, coberturas y escenarios; el
   alza de 2022 es 8,242 puntos (se muestra 8,24). La tasa de política
   (12,25 %) y la IBR (11,70 %) las confirmó contra la última reunión del
   BanRep el 13/10/2026.

Grupos de comparación en `config/ciiu_sectores.yaml` (alojamiento / hoteles).
El benchmark se describe siempre como "empresas reportantes a
Supersociedades", nunca como el sector completo. Probablemente será nacional:
Nariño tendrá muy pocas empresas.

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
