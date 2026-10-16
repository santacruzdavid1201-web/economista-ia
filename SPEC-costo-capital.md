# Spec: costo-capital

Módulo del [mapa de proyectos](SPEC-mapa-proyectos.md). Estado: propuesta del
15/10/2026, aprobada por el usuario el 16/10/2026 (riesgo país con el método
de Damodaran). Beta leída por el usuario: 0,58.

## Objetivo

Responder **¿con qué tasa descuento mi proyecto?** con el costo de capital
promedio ponderado (WACC) de la empresa, para que la tasa de oportunidad no
se escriba "a ojo". Es la tasa mínima que el proyecto debe rendir para pagarles
a los bancos y a los dueños lo que exigen por el riesgo que corren.

Usuario: el gerente con estados financieros cargados, en la pestaña "Su
proyecto" (como tasa recomendada) y en el chat ("¿cuál es el costo de capital
de mi empresa?").

## Fuentes (verificadas el 15/10/2026)

| Dato | Fuente | Último valor |
|---|---|---|
| Tasa libre de riesgo real | TES cero cupón **UVR** 10 años, SUAMECA 15277 (diaria) | 6,74 % (9/10/2026) |
| Inflación esperada por el mercado (solo como contraste) | TES pesos 10 años (15274, 13,05 %) frente a UVR: 1,1305 / 1,0674 − 1 | 5,9 % |
| Prima de riesgo de un mercado maduro | Damodaran, `ctryprem.xlsx` o `ctryprem.html` (anual, enero) | 4,23 % (enero de 2026) |
| Spread de incumplimiento de Colombia (Baa3) | Damodaran, `ctryprem` ("Adj. Default Spread") | 1,87 % (enero de 2026) |
| Prima total de Colombia (madura + riesgo país 2,85 %) | Damodaran, `ctryprem` ("Total Equity Risk Premium") | 7,08 % (enero de 2026) |
| Beta del sector hotelero en mercados emergentes | Damodaran, `betaemerg.xls` ("Hotel/Gaming", "Unlevered beta corrected for cash"); la leyó el usuario | 0,58 (5 de enero de 2026) |
| Costo de la deuda | Balance de la empresa: tasa implícita (gastos financieros / deuda financiera promedio), ya calculada en `sensibilidad-tasas` | Según la empresa |
| Pesos de deuda y patrimonio | Balance: deuda financiera y patrimonio, en libros | Según la empresa |

## Decisiones económicas (para aprobar)

1. **Todo en términos reales, con el TES en UVR.** El TES en UVR paga sobre un
   valor que sigue al IPC, así que su tasa ya es real (6,74 %). Si el WACC se
   armara con el TES en pesos (13,05 %), traería la inflación que espera el
   mercado, 5,9 %, y los flujos del proyecto se arman con la senda del BanRep
   (4,3 % y luego 3 %): se descontaría con una inflación distinta de la de
   los flujos y el proyecto saldría castigado. En real no hay mezcla: los
   flujos en pesos de hoy se descuentan con el WACC real.
2. **Costo del patrimonio por CAPM en pesos con el método de Damodaran**
   (decisión 3 del mapa; aprobado el 16/10/2026):
   Ke real = (TES UVR − spread de incumplimiento) + β apalancada × prima total.
   El TES no está libre de riesgo: paga el spread de incumplimiento de Colombia
   (1,87 %). Se le resta para tener una tasa sin riesgo, y el riesgo país entra
   en la prima total (7,08 %), multiplicado por la beta. Sumar la prima total
   al TES completo contaría el riesgo país dos veces; usar solo la prima madura
   (la versión anterior de esta especificación) lo dejaría como el spread de un
   bono, sin beta y sin la mayor volatilidad de las acciones (2,85 / 1,87 ≈
   1,5). Mezclar la tasa real del TES con primas medidas en dólares es una
   aproximación, declarada como supuesto.
3. **Beta del sector, ajustada a la deuda de la empresa** (Hamada):
   β apalancada = β sin deuda × (1 + (1 − t) × D/P). Una pyme no cotiza en
   bolsa y no tiene beta propia; se toma la del sector hotelero de mercados
   emergentes y se le suma el riesgo de su propio endeudamiento.
4. **Costo de la deuda desde el balance, después de impuestos y en real:**
   Kd real = (1 + Kd × (1 − t)) / (1 + inflación del año del balance) − 1.
   El ahorro de impuestos se calcula sobre el interés nominal, que es el que
   se deduce; la inflación es la observada (IPC) del año del balance.
5. **Pesos en valores en libros** (deuda financiera y patrimonio del último
   balance), declarado como supuesto: una pyme no tiene valor de mercado.
6. **WACC real** = P/(D+P) × Ke + D/(D+P) × Kd real. Se muestra también su
   equivalente nominal del primer año, (1 + WACC) × (1 + π₁) − 1, para
   compararlo con tasas que el gerente conoce.
7. **La evaluación con el WACC descuenta los flujos en pesos de hoy con la
   tasa real.** El formulario tiene un tipo de tasa: nominal (efectiva anual,
   la de siempre), real o WACC de la empresa. Con real o WACC, flujos en pesos
   de hoy y TIR real (flujos y tasa en la misma moneda). Con el WACC, el
   proyecto se compara con lo que cuesta su capital ("deja $ X más de lo que
   exigen los dueños y los bancos"), con el supuesto de que tiene el riesgo y
   la financiación de siempre. La tasa escrita en una pregunta del chat es
   nominal. La sensibilidad sigue diciendo "tasa de oportunidad" (el WACC es
   el costo de oportunidad del capital), con "real" cuando lo es (decidido el
   16/10/2026).
8. **Sin estados financieros no hay WACC** (faltan la deuda, su costo y el
   patrimonio): se muestra el costo de capital de los activos, Ku = (TES UVR −
   spread) + β sin deuda × prima total, que es lo que el mercado le exigiría a
   un hotel sin deuda (el WACC antes del ahorro de impuestos de la deuda, según
   Modigliani-Miller). Se dice así, como referencia, no como el WACC de la
   empresa.
9. **El WACC es una referencia, no una regla:** el gerente puede exigirle más
   a un proyecto más riesgoso que el negocio de siempre. Se dice en un
   hallazgo.

## Ejemplo (conciliado a mano por el usuario el 16/10/2026; la beta es hipotética)

β sin deuda 1,00; D/P = 0,5; t = 35 %; Kd = 14 % nominal; inflación del año
del balance 5,1 %; TES UVR 6,74 %; spread de incumplimiento 1,87 %; prima
total 7,08 %; π₁ = 4,3 %.

- β apalancada = 1,00 × (1 + 0,65 × 0,5) = 1,325
- Ke real = (6,74 % − 1,87 %) + 1,325 × 7,08 % = 14,25 %
- Kd real después de impuestos = (1 + 0,14 × 0,65) / 1,051 − 1 = 3,81 %
- WACC real = 2/3 × 14,25 % + 1/3 × 3,81 % = 10,77 %
- Equivalente nominal del primer año = 1,1077 × 1,043 − 1 = 15,53 %
- Sin estados financieros: Ku = 4,87 % + 1,00 × 7,08 % = 11,95 %

## Diseño

- `config/series.yaml`: `tes_uvr_10` (15277). El actualizador diario la
  incluye. El TES en pesos (15274) no entra: ninguna fórmula lo usa.
- `config/costo_capital.yaml`: spread de incumplimiento, prima total y beta
  sin deuda del sector, escritos a mano con fuente y fecha (se actualizan en
  enero, cuando Damodaran publica; sin dependencia para leer `.xls`).
- `modules/proyectos/wacc.py`: costo de capital puro -> `ResultadoModulo` con
  Ke, Kd, pesos y WACC (real y su equivalente nominal), o Ku sin estados
  financieros, con hallazgos y supuestos.
- `modules/proyectos/evaluacion.py`: `evaluar(flujo, tasa, tipo)` con tipo
  "nominal", "real" o "wacc"; con los dos últimos descuenta los flujos en
  pesos de hoy.
- Pestaña "Su proyecto": con empresa cargada, un bloque "Tasa recomendada:
  WACC de su empresa" con el desglose y la opción de evaluar con ella.
- Chat: herramienta `calcular_costo_capital` (necesita la empresa) y bloque O
  del set.

## Límites

- Siempre: las fuentes con su fecha; los supuestos (valores en libros, beta
  del sector, inflación del año) dichos.
- Nunca: presentar el WACC como "la" tasa correcta del proyecto.

## Criterios de éxito

1. El ejemplo da esas cifras y el usuario lo concilia.
2. Con el hotel de demostración, la pestaña muestra el WACC con su desglose y
   permite evaluar el proyecto con él.
3. El chat responde "¿cuál es el costo de capital de mi empresa?"; bloque O al
   100 % con el modelo real.
4. Suite completa en verde.

## Decisiones del usuario (16/10/2026)

1. Riesgo país con el método de Damodaran (spread restado del TES, prima
   total por beta), en vez de la prima madura sola.
2. La beta se escribe a mano en `config/costo_capital.yaml`; el usuario la lee
   del Excel de Damodaran.
3. Sin estados financieros se muestra el costo de capital de los activos (Ku).
