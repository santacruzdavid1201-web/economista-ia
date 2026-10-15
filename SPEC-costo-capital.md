# Spec: costo-capital

Módulo del [mapa de proyectos](SPEC-mapa-proyectos.md). Estado: propuesta del
15/10/2026, pendiente de aprobación.

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
| Prima de riesgo de un mercado maduro | Damodaran, `ctryprem.xlsx` (anual, enero) | 4,23 % |
| Beta del sector hotelero en mercados emergentes | Damodaran, `betaemerg.xls` ("Hotel/Gaming", beta sin deuda) | Ver pregunta abierta 1 |
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
2. **Costo del patrimonio por CAPM en pesos** (decisión 3 del mapa):
   Ke real = TES UVR + β apalancada × prima de mercado madura. Se usa la prima
   madura (4,23 %) y no la total de Colombia (7,08 %), porque el TES ya trae el
   riesgo país; sumar las dos lo contaría dos veces.
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
   tasa real** (la evaluación pasa a admitir tasa real; la TIR se muestra
   real en ese caso). La tasa que escribe el usuario sigue siendo nominal.
8. **Sin estados financieros no hay WACC** (faltan la deuda, su costo y el
   patrimonio): se muestra solo el costo del patrimonio sin deuda como
   referencia, dicho así.
9. **El WACC es una referencia, no una regla:** el gerente puede exigirle más
   a un proyecto más riesgoso que el negocio de siempre. Se dice en un
   hallazgo.

## Ejemplo (para conciliar; la beta es hipotética hasta resolver la pregunta 1)

β sin deuda 1,00; D/P = 0,5; t = 35 %; Kd = 14 % nominal; inflación del año
del balance 5,1 %; TES UVR 6,74 %; prima madura 4,23 %; π₁ = 4,3 %.

- β apalancada = 1,00 × (1 + 0,65 × 0,5) = 1,325
- Ke real = 6,74 % + 1,325 × 4,23 % = 12,35 %
- Kd real después de impuestos = (1 + 0,14 × 0,65) / 1,051 − 1 = 3,81 %
- WACC real = 2/3 × 12,35 % + 1/3 × 3,81 % = 9,50 %
- Equivalente nominal del primer año = 1,0950 × 1,043 − 1 = 14,21 %

## Diseño

- `config/series.yaml`: `tes_uvr_10` (15277) y `tes_pesos_10` (15274). El
  actualizador diario las incluye.
- `config/costo_capital.yaml`: prima de mercado madura y beta sin deuda del
  sector, con fuente y fecha (se actualizan en enero, cuando Damodaran
  publica).
- `modules/proyectos/costo_capital.py`: `costo_capital(historial, tasas,
  parametros) -> ResultadoModulo` con Ke, Kd, pesos y WACC (real y su
  equivalente nominal), hallazgos y supuestos.
- `modules/proyectos/evaluacion.py`: `evaluar(..., real=True)` descuenta los
  flujos en pesos de hoy.
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

## Preguntas abiertas

1. **La beta del sector.** Damodaran la publica solo en `.xls` (formato viejo),
   que el proyecto no lee hoy. Opciones:
   - (a) agregar `xlrd`, una librería pequeña y conocida que lee `.xls`, y
     cargar el archivo una vez al año con un comando, como el informe del
     BanRep;
   - (b) escribir a mano en `config/costo_capital.yaml` el número del año
     (una cifra en enero), con su fuente.

   Recomiendo (b): es un número al año y no justifica una dependencia. Para
   el valor de hoy, ¿lo lees tú en el Excel ("Hotel/Gaming", columna
   "Unlevered beta corrected for cash") o me autorizas a instalar `xlrd`
   solo para leerlo esta vez, sin agregarlo al proyecto?
2. ¿Te parece bien que, sin estados financieros, se muestre solo el costo
   del patrimonio sin deuda como referencia?
