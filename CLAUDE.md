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
- `data_sources/`: cargadores de datos de empresa y fuentes externas.
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

## Estado actual

Hecho y probado (67 tests): esquema canónico, mapeo PUC, razones de liquidez,
endeudamiento, rentabilidad y actividad, ciclo de conversión de efectivo,
DuPont (con descomposición logarítmica de la variación del ROE), Z'' de
Altman para mercados emergentes (zonas 4,35 / 5,85 y equivalencia de
calificación de Altman y Hotchkiss 2005) y motor de benchmark
(`modules/balance/benchmark.py`: percentil de rango medio, dirección por
indicador, muestra mínima 10 / adecuada 30). El EBITDA es `None` si no se
reportó la depreciación; el impuesto admite negativos (beneficio).

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
pura con exclusiones motivadas). Carga 303 de 306 hoteles 2024. Ver sección 6
de los hallazgos.

Pendiente, en orden:
5. Construir `ReferenciaSectorial` calculando los indicadores de los pares
   con las mismas funciones de `modules/balance/`. Decisiones acordadas:
   pares sin `costo_ventas` en `model_fields_set` no entran a margen bruto ni
   días de inventario; los días de cartera y proveedores de la empresa se
   comparan con la misma agregación que los pares (cuentas comerciales + otras);
   `SUPUESTOS_MAPEO` va a `ReferenciaSectorial.filtros`.
6. Validar contra los indicadores que publica el SIIS.

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
