# Spec: matematica-financiera

Módulo del [mapa de proyectos](SPEC-mapa-proyectos.md). Estado: aprobado,
construido y conciliado a mano por el usuario el 15/10/2026.

## Objetivo

Dar al módulo 3 la aritmética financiera probada sobre la que se construyen
el flujo, la evaluación, la sensibilidad y el Monte Carlo, y responder desde
ya dos preguntas frecuentes de una pyme:

- "¿Cuánto pago por un crédito de 200 millones al 18 % EA a 5 años?"
- "¿2 % mensual cuánto es en efectivo anual?"

Usuarios: el gerente (chat y tablero de Proyectos) y las piezas siguientes del
módulo (funciones puras). La empresa no es necesaria: el simulador y el
conversor funcionan sin balance cargado.

Por qué en Python y no en el modelo: el 7B confunde tasa nominal con efectiva
y mensual con anual, y la diferencia no es menor (24 % NMV es 26,82 % EA).

## Alcance

**Tasas equivalentes.** Todas las tasas viajan en decimales (0,18) y con su
tipo. Tipos: efectiva anual (EA); periódica vencida (mensual, trimestral,
semestral); nominal vencida (NMV, NTV, NSV); periódica y nominal anticipada
(MA, NMA, TA, NTA). Fórmulas:

- EA → periódica con m periodos al año: i = (1 + EA)^(1/m) − 1
- nominal vencida N con m capitalizaciones → periódica: i = N / m
- anticipada → vencida en el mismo periodo: i_v = i_a / (1 − i_a)
- la conversión pasa siempre por la periódica vencida equivalente, así toda
  combinación sale con dos funciones

**Indicadores** (los usará `evaluacion-proyecto`; aquí solo las funciones y
sus tests). Flujos por periodo, el 0 es hoy, con la tasa del mismo periodo:

- VPN = Σ F_t / (1 + i)^t
- TIR: la tasa con VPN = 0. Se buscan cambios de signo del VPN en una malla de
  −99 % a 1.000 % y se refina cada uno por bisección (sin scipy). Una raíz →
  la TIR. Ninguna → `None` con advertencia ("el VPN no cambia de signo: no hay
  TIR"). Dos o más → `None` con advertencia que las nombra y remite al VPN y la
  TIRM: un número único sería engañoso. Es el caso de un hotel con una
  remodelación grande a mitad de la vida del proyecto.
- TIRM: flujos positivos capitalizados a la tasa de descuento hasta el final,
  negativos descontados a hoy con la misma tasa; (VF / VP)^(1/n) − 1. Una sola
  tasa para reinversión y financiación, declarado como supuesto.
- Recuperación descontada: primer periodo en que el flujo descontado
  acumulado llega a cero, interpolando dentro del periodo (supone el flujo
  repartido de forma pareja; supuesto). `None` con advertencia si no se
  recupera dentro de la vida del proyecto.
- Índice de rentabilidad: VP de los flujos desde t = 1 / −F_0 (pesos de valor
  presente por cada peso invertido). `None` si F_0 no es negativo.
- Valor anual equivalente: VPN × i / (1 − (1 + i)^−n), para comparar
  proyectos de vida distinta.

**Crédito.** Monto, tasa (con su tipo), plazo y periodicidad de las cuotas
(mensual por defecto; trimestral, semestral o anual). Dos sistemas:

- Cuota fija (francés): cuota = P · i / (1 − (1 + i)^−n)
- Abono constante a capital: abono = P / n; interés sobre el saldo; cuotas
  decrecientes

Tabla por periodo (saldo inicial, interés, abono, cuota, saldo final) y
totales (intereses pagados y su proporción sobre el monto). Supuesto fijo: la
cuota no incluye seguros, comisiones ni GMF, así que el costo real del crédito
puede ser mayor.

## Diseño

- `modules/proyectos/matematica_financiera.py`: funciones puras (tasas,
  indicadores, amortización) y dos análisis que devuelven `ResultadoModulo`:
  `simular_credito(...)` y `convertir_tasa(...)`, con hallazgos redactados en
  Python. Ejemplo: "Con 18,00 % efectiva anual (1,39 % mensual), un crédito de
  $ 200.000.000 a 60 meses tiene una cuota fija de $ 4.934.680. En total paga
  $ 96.080.819 de intereses, el 48,0 % del monto."
- **Tipo de tasa leído por Python en la pregunta**, no por el modelo: "EA",
  "efectiva anual", "NMV", "mes vencido", "mensual", "anticipad"... junto al
  número. Si solo dice "anual", se asume efectiva anual con el supuesto "Se
  asumió que la tasa es efectiva anual, como deben informarla los bancos en
  Colombia". Lección del 7B: las distinciones de sentido van en Python.
- **Montos y plazos que el orquestador no descarte.** Hoy descarta todo
  número que no esté escrito en la pregunta, así que 200000000 (de "200
  millones") se perdería. Python lee los montos con sus palabras ("200
  millones", "1.500 millones", "$200.000.000", "mil millones") y el
  orquestador acepta el monto si coincide con uno de ellos. El plazo se pide
  con su unidad (`plazo` + `unidad_plazo`: meses o años) para que el número sea
  el de la pregunta.
- Herramientas nuevas en `app/orchestrator/tools_registry.py`, sin periodo ni
  empresa: `simular_credito(monto, tasa, plazo, unidad_plazo, sistema)` y
  `convertir_tasa(tasa, hacia)`. Reglas del enrutador para elegirlas, y para
  que un crédito de la empresa no caiga en `fuera_de_alcance`.
- Tablero de Proyectos activo desde esta pieza (sale de "próximamente"):
  simulador de crédito (formulario: monto, tasa, tipo de tasa, plazo,
  periodicidad, sistema → cuota, totales, tabla resumida por año y la tabla
  completa desplegable) y conversor de tasas (una tasa y su tipo → sus
  equivalentes). En el formulario el tipo se elige de una lista: no hay
  ambigüedad que suponer. Mismo patrón de los otros tableros
  (`frontend/tableros.py` + `_tablero_proyectos.html`, HTMX, sin JavaScript
  propio).
- Nota de conocimiento `conocimiento/tasas-equivalentes.md` (EA, nominal,
  periódica, anticipada; cuota fija y abono constante; fórmulas en símbolos y
  en palabras), para revisión del usuario.

## Comandos

```
python -m pytest -v                                   # suite completa, sin red
python -m pytest tests/modules/proyectos -v           # solo esta pieza
python -m app.eval --bloques L                        # bloque nuevo del set de evaluación
python -m app.demo "¿Cuánto pago por un crédito de 200 millones al 18 % EA a 5 años?"
python -m uvicorn app.main:app --port 8000            # tablero en /modulo/proyectos
```

## Estructura

```
modules/proyectos/__init__.py
modules/proyectos/matematica_financiera.py     funciones puras + simular_credito, convertir_tasa
app/orchestrator/tools_registry.py             dos herramientas nuevas
app/orchestrator/orquestador.py                montos con palabras en la validación
config/prompts/router.md                       reglas para crédito, tasas y proyectos propios
frontend/tableros.py, frontend/web.py          tablero y formularios de Proyectos
frontend/templates/_tablero_proyectos.html
conocimiento/tasas-equivalentes.md
tests/modules/proyectos/test_matematica_financiera.py
tests/eval/preguntas.yaml                      bloque L
```

## Estilo

Como el resto del proyecto: español, funciones puras, tasas en decimales,
montos en positivo, `None` con advertencia cuando no hay un número honesto.

```python
def a_periodica(tasa: float, tipo: str) -> tuple[float, int]:
    """Tasa de cualquier tipo → (tasa periódica vencida, periodos por año)."""

def tir(flujos: list[float]) -> tuple[float | None, list[str]]:
    """TIR única, o None con la advertencia que explica por qué no hay una."""
```

## Tests

Casos calculados a mano (para conciliar con el usuario):

| Caso | Resultado |
|---|---|
| 2 % mensual → EA | 26,82 % |
| 24 % NMV → EA | 26,82 % |
| 18 % EA → mensual | 1,3888 % (16,67 % NMV) |
| 2 % mes anticipado → mes vencido | 2,0408 % |
| 24 % NMA → EA | 27,43 % |
| Crédito $ 200.000.000, 18 % EA, 60 meses, cuota fija | cuota $ 4.934.680; intereses $ 96.080.819 (48,0 %) |
| El mismo, abono constante | primera cuota $ 6.111.019; última $ 3.379.628; intereses $ 84.719.425 |
| Flujos −1.000, 300, 400, 500, 200 al 10 % | VPN 115,57; TIR 15,32 % |

Además:

- Ida y vuelta entre todos los tipos de tasa (error < 1e-12).
- Amortización: abonos suman el monto, saldo final 0 (± 1 peso), interés de
  cada periodo = saldo inicial × tasa.
- TIR: sin cambio de signo → `None`; dos raíces (−100, 230, −132 tiene TIR
  10 % y 20 %) → `None` y la advertencia nombra ambas; VPN(TIR) = 0.
- Lectura de la pregunta: tipo de tasa ("18 % EA", "24 % NMV", "2 %
  mensual", "18 % anual" → EA con supuesto) y montos ("200 millones", "1.500
  millones", "$200.000.000").
- Orquestador: acepta el monto de "200 millones" y descarta uno inventado.
- Tablero: formularios y resultados con TestClient.

## Límites

- Siempre: todo número sale de Python; el tipo de tasa y los supuestos se
  dicen en la respuesta; tests sin red.
- Preguntar antes: agregar dependencias (no hacen falta: numpy ya está para el
  Monte Carlo y la TIR va con la biblioteca estándar); comparar la tasa con la
  de usura (habría que confirmar la fuente).
- Nunca: recomendar un banco, un crédito o un sistema de amortización;
  calificar una tasa de "cara" o "barata" sin referencia.

## Criterios de éxito

1. Los casos de la tabla de tests dan esos valores y el usuario los concilia
   con su cálculo a mano.
2. Las dos preguntas del objetivo se responden en el chat con la herramienta
   correcta, el tipo de tasa dicho y ninguna cifra fuera del desplegable.
3. "18 % anual" se trata como EA y lo dice como supuesto.
4. El tablero de Proyectos está activo con el simulador y el conversor.
5. Bloque L del set de evaluación al 100 % con el modelo real; suite completa
   en verde.

## Preguntas abiertas

Ninguna. Resueltas el 15/10/2026:

1. Solo flujos a precios de hoy con tasa real (no hay opción de pesos
   corrientes); el usuario confirmó también el CAPM en pesos del mapa.
2. La comparación con la tasa de usura vigente se agrega después, en una pieza
   aparte, si se confirma una fuente automática (Superfinanciera o BanRep).
