# Spec: sensibilidad-tasas

Módulo del [mapa macro](SPEC-mapa-macro.md). Depende de
[series-externas](SPEC-series-externas.md) (segundo tramo: tasas) y del
módulo 1. Estado: aprobado y construido el 12/10/2026. Criterio 3: el bloque I
pasa 7 de 7 y el set completo, todos los bloques (12/10/2026). Los calificativos
que el 7B agregaba ("incremento significativo") los atrapa el verificador con un
reintento, por decisión del economista. Ver "Cambios al construir".

## Objetivo

Responder "¿cómo me afectan las tasas de interés?" y sus variantes ("¿qué
pasa si suben 2 puntos?", "¿cuánto me cuesta cada punto?", "si el Banco de la
República baja las tasas, ¿cuánto me ahorro?"): cuánto cambiarían los gastos
financieros y la cobertura de intereses si la tasa de la deuda sube o baja,
con la deuda que la empresa tiene hoy.

Usuario: el gerente, a través del orquestador.

## Decisiones económicas

- **Aritmética de sensibilidad, no pronóstico.** Se calcula qué pasaría si la
  tasa cambiara, sin decir si va a cambiar. Todo lo demás queda igual
  (*ceteris paribus*): misma deuda, misma utilidad operacional.
- **Un punto de tasa cuesta 1 % de la deuda financiera al corte.** Cambio en
  los gastos financieros anuales = deuda financiera al corte × cambio en la
  tasa. Se usa el saldo al corte, no el promedio, porque es la deuda que se
  va a repreciar de aquí en adelante.
- **Exposición máxima: toda la deuda financiera se reprecia.** El balance no
  dice qué parte es a tasa fija. Se supone que toda es variable (atada a la
  IBR o a la DTF) o que se renueva en el año, y se declara como supuesto: con
  deuda a tasa fija el efecto es menor y llega solo al renovar.
- **Traslado completo.** Un punto más en la tasa de referencia es un punto más
  en la tasa de la deuda (el margen del banco sobre la IBR no cambia).
- **Escenarios: ±1, ±2 y ±3 puntos** (aprobados en el mapa), más el que pida
  el gerente si da una cifra ("¿y si sube 5 puntos?"), más un **escenario
  histórico**: la mayor alza de la IBR a 3 meses en 12 meses desde 2012
  (8,2 puntos, a diciembre de 2022). Sirve para mostrar que ±3 es moderado
  frente a lo ya observado; es un dato del pasado, no una predicción.
- **Tasa implícita de la deuda** = gastos financieros anuales / deuda
  financiera promedio (convención flujo/saldo del proyecto). Es una
  aproximación: en el PUC la cuenta 5305 incluye comisiones, gastos bancarios
  y diferencia en cambio, no solo intereses; se declara como supuesto.
- **Hasta dónde aguanta:** el alza que haría que la utilidad operacional
  apenas cubra los gastos financieros (cobertura = 1) =
  (utilidad operacional − gastos financieros) / deuda financiera al corte.
  Cobertura = 1 no es un umbral de "bueno/malo": es la igualdad aritmética
  entre lo que deja la operación y lo que cuestan los intereses.
- **Antes de impuestos.** El efecto sobre la utilidad neta depende de la
  tarifa efectiva y de los límites a la deducción de intereses; no se estima.
- **Solo el canal de los intereses.** Las tasas también afectan la demanda
  (crédito de los clientes, consumo, turismo); eso no se mide aquí y se dice.
- **Contexto de mercado a la fecha de consulta**, no a la del balance: tasa
  de política monetaria y su cambio en 12 meses, e IBR a 3 meses. Cada serie
  se informa en su unidad oficial (la de política es efectiva anual; la IBR,
  nominal); los escenarios suman puntos a la tasa de la empresa, no a estas.

## Datos: series-externas, segundo tramo (tasas)

Ids de SUAMECA, averiguados el 12/10/2026 en el catálogo del portal
(`consultaMenuXopcion?opcion=CATALOGO_DATOS`, rama "Tasas de interés y sector
financiero"), todos nacionales y diarios:

| Clave | Id | Serie | Unidad | Desde |
|---|---|---|---|---|
| `tasa_politica` | 59 | Tasa de política monetaria | efectiva anual, base 365 | 1998 |
| `ibr_3m` | 243 | IBR a 3 meses, nominal | nominal, base 360 | 2012 |

Probados y descartados por ahora: IBR overnight (241) y a 1 mes (242), DTF a
90 días (65, semanal) y tasas de colocación (15109-15115, semanales; la del
crédito comercial ordinario es la 15113). Los ids 16560 y 16562 de la rama
IBR dan error 500.

Al 12/10/2026: tasa de política 12,25 % (9,25 % un año antes); IBR a 3 meses
11,70 % (8,85 % un año antes). Mayor alza en 12 meses desde 2012 (fin de
mes): IBR a 3 meses +8,24 puntos (dic/2022); tasa de política +9,0 (mar/2023).

Cambios en `series-externas`: dos entradas en `config/series.yaml` (solo
geografía `nacional`), dos copias versionadas en `data/series/` y en `Serie`
dos métodos puros: `valor_al(fecha)` (último dato en o antes de la fecha) y
`fin_de_mes()` (último dato de cada mes, para cambios a 12 meses). El formato
de `Serie` no cambia. Al construirlo, los ids pasan a `SPEC-series-externas.md`.

## Resultado

`sensibilidad_tasas(historial, i, tasa_politica: Serie, ibr: Serie,
puntos: float | None = None) -> ResultadoModulo`
(`modules/macro/sensibilidad_tasas.py`), análisis `sensibilidad_tasas`:

| Indicador | Unidad | Fórmula |
|---|---|---|
| `deuda_financiera` | pesos | Obligaciones financieras CP + LP al corte |
| `tasa_implicita_deuda` | tasa | Gastos financieros anuales / Deuda financiera promedio |
| `intereses_por_punto` | pesos | Deuda financiera al corte × 1 punto |
| `gastos_financieros_anuales`, `cobertura_intereses` | pesos, veces | Situación actual (anualizada) |
| `gastos_financieros_mas_N`, `gastos_financieros_menos_N` (N = 1, 2, 3) | pesos | Gastos financieros anuales ± deuda al corte × N puntos |
| `cobertura_mas_N`, `cobertura_menos_N` | veces | Utilidad operacional anual / gastos financieros del escenario |
| `gastos_financieros_historico`, `cobertura_historico` | pesos, veces | Escenario con la mayor alza de la IBR en 12 meses |
| `gastos_financieros_pedido`, `cobertura_pedido` | pesos, veces | Solo si el gerente dio una cifra |
| `tasa_politica`, `ibr_3m` | tasa | Último dato publicado |
| `mayor_alza_ibr_12m` | puntos | Máximo cambio a 12 meses de la IBR, fin de mes, desde 2012 |

Unidades nuevas en `formatear`: `tasa` ("12,25 %", dos decimales porque la
tasa de política se mueve de a 0,25) y `puntos` ("3,00 puntos"); ambas se
guardan como proporción.

Para el hotel demo (2024): deuda $680 millones (promedio $720 millones),
gastos financieros $95 millones, utilidad operacional $455 millones. Tasa
implícita 13,19 %; cada punto, $6,8 millones al año; con +3 puntos, gastos de
$115,4 millones y cobertura de 3,94 veces (hoy 4,79); con −3, $74,6 millones
y 6,10 veces; con el alza histórica (+8,24), $151,0 millones y 3,01 veces; la
cobertura llegaría a 1 con un alza de 52,94 puntos.

Hallazgos (redactados en Python, sin comparar cifras entre sí en el texto del
modelo):
- "Cada punto que suba la tasa de la deuda le suma $ 6.800.000 al año en gastos
  financieros (1 % de la deuda financiera de $ 680.000.000)."
- "Con 3 puntos más, los gastos financieros pasarían de $ 95.000.000 a
  $ 115.400.000 al año y la cobertura de intereses de 4,79 veces a 3,94 veces;
  con 3 puntos menos, a $ 74.600.000 y 6,10 veces."
- "La mayor alza de la IBR a 3 meses en un año fue de 8,24 puntos, en 2022 (de
  diciembre de 2021 a diciembre de 2022): si la tasa de la deuda subiera eso,
  los gastos financieros aumentarían $ 56.045.600 al año, hasta
  $ 151.045.600, y la cobertura bajaría a 3,01 veces."
- "Aun con un alza como la de 2022, la utilidad operacional seguiría
  alcanzando para pagar los gastos financieros." (el punto de quiebre, 52,94
  puntos, solo se cita si es menor que el alza histórica)
- "Al 12/10/2026 la tasa de política monetaria del Banco de la República es
  12,25 %; la IBR a 3 meses, referencia de muchos créditos a tasa variable,
  estaba en 11,70 % al 09/10/2026."
- "Son escenarios hipotéticos sobre la tasa de la deuda, no un pronóstico de
  las tasas, y no hay referencia del sector para calificar si el efecto es
  alto o bajo."
- Con un escenario pedido (p. ej. 5 puntos), solo ese: "Con 5 puntos más, los
  gastos financieros serían $ 129.000.000 al año y la cobertura de intereses
  3,53 veces."

Casos sin cálculo, nunca con un número engañoso:
- Sin deuda financiera: hallazgo "La empresa no tiene deuda financiera al
  corte: un cambio en las tasas no le cambia los intereses"; escenarios `None`.
- Deuda sin gastos financieros identificados (los intereses quedaron en otra
  cuenta): `intereses_por_punto` sí se calcula; tasa implícita y coberturas
  `None` con la advertencia del módulo 1.
- Utilidad operacional nula o negativa, o cobertura actual < 1: coberturas y
  `alza_cobertura_uno` `None`, con advertencia (la operación ya no cubre los
  intereses).
- Baja mayor que la tasa implícita (tasa negativa): ese escenario `None`.
- Periodo de menos de 12 meses: gastos financieros y utilidad operacional
  anualizados, con supuesto.

Supuestos fijos: exposición máxima (toda la deuda se reprecia), traslado
completo, deuda y utilidad operacional constantes, deuda del corte del
balance (si cambió desde entonces, el efecto cambia en proporción), 5305
incluye más que intereses, solo el canal de intereses, antes de impuestos.

## Cambios al construir (12/10/2026)

Con el modelo real aparecieron errores de sentido que se corrigieron en Python,
no en el prompt:

- El punto de quiebre (`alza_cobertura_uno`) dejó de ser indicador: el 7B lo
  mezcló con la cobertura de otro escenario y, por su nombre ("apenas cubre"),
  dijo que +5 puntos "apenas cubriría" los intereses. Ahora es un hallazgo que
  lo compara con el alza histórica: con cifra si es menor ("con un alza de 2,50
  puntos, menor que la de 2022…"); si no, "aun con un alza como la de 2022, la
  utilidad operacional seguiría alcanzando".
- Se quitó el cambio a 12 meses de la tasa de política: el 7B le atribuyó el
  escenario de 2022. El contexto queda en niveles.
- El hallazgo histórico da el año primero y separa aumento y nivel ("aumentarían
  $ 56.045.600 al año, hasta $ 151.045.600"): el 7B lo ubicó "en el último año"
  y llamó "aumento" al nivel.
- Con un escenario pedido se devuelve solo ese (con la clave fija si es ±1, ±2
  o ±3): con todos a la vez el 7B los comparaba por su cuenta.
- El orquestador descarta un argumento numérico que no esté en la pregunta: el
  enrutador pasaba `puntos = -1` a "¿cuánto me ahorro?".
- `NO_ES_PRONOSTICO` dice además que no hay referencia del sector para calificar
  el efecto; aun así el 7B escribe "significativo".

## Integración

- Herramienta `analizar_sensibilidad_tasas` en `tools_registry.py`, con
  descripción que la separe de `analizar_endeudamiento` (esa describe la
  deuda de hoy; esta, qué pasa si cambian las tasas). Argumento opcional
  `puntos` (número entre −10 y 10, distinto de 0; fuera de rango, error con
  mensaje útil).
- `ContextoEmpresa.serie` ya existe: se piden `tasa_politica` e `ibr_3m`.
- Glosario: `tasa_implicita_deuda`, `intereses_por_punto`, `alza_cobertura_uno`,
  `tasa_politica`, `ibr_3m` (sin cifras en las definiciones).
- Bloque I "Tasas de interés" en `tests/eval/preguntas.yaml`:
  - "¿Cómo me afectan las tasas de interés?" y "¿Cuánto me cuesta cada punto
    de tasa?" (par de consistencia; `cifra_de: [intereses_por_punto]`).
  - "¿Qué pasa si las tasas suben 2 puntos?" (`cifra_de:
    [gastos_financieros_mas_2, cobertura_mas_2]`).
  - "¿Y si suben 5 puntos?" (`argumentos: {puntos: 5}`,
    `cifra_de: [gastos_financieros_pedido]`).
  - "Si el Banco de la República baja las tasas, ¿cuánto me ahorro?"
    (revisar: no promete que vayan a bajar).
  - "¿Va a subir la tasa del Banco de la República?" (`fuera_de_alcance`: es
    un pronóstico).
  - "¿Por qué me afecta que el Banco de la República suba las tasas?"
    (conceptual, nota "Tasas de interés del Banco de la República y deuda de
    la empresa").

## Comandos

```
python -m pytest -v
python -m data_sources.externos.series.catalogo --tasas   # refresca tasa de política e IBR
python -m app.demo "¿Cómo me afectan las tasas de interés?"
python -m app.eval --bloques I
```

## Tests (primero el test, después la función)

- Caso a mano: deuda 1.000 al corte (900 al inicio), gastos financieros 95,
  utilidad operacional 300 → tasa implícita 10 %, cada punto 10, con +3
  gastos 125 y cobertura 2,40, alza a cobertura 1 de 20,5 puntos.
- Escenario pedido (5 puntos) y fuera de rango (15 → error).
- Sin deuda; deuda sin gastos financieros; utilidad operacional negativa;
  cobertura actual < 1; baja mayor que la tasa implícita; periodo de 6 meses.
- `Serie.valor_al` y `fin_de_mes` con fixtures; mayor alza a 12 meses con una
  serie corta calculada a mano.
- Orquestador con LLM falso: enruta a la herramienta y pasa `puntos`.
- Ningún test toca la red.

## Límites

- Siempre: declarar exposición máxima, traslado completo y ceteris paribus;
  fecha y unidad oficial de cada tasa en `fuentes`.
- Preguntar antes: separar deuda fija y variable (exige un dato que el balance
  no trae); comparar la tasa implícita con la de colocación del mercado;
  estimar el efecto después de impuestos.
- Nunca: pronosticar tasas ni decir si van a subir o bajar; calificar la
  sensibilidad como alta o baja sin referencia sectorial.

## Criterios de éxito

1. Para el hotel demo (2024) las cifras coinciden con un cálculo a mano en una
   hoja de cálculo.
2. La tasa de política y la IBR del sistema coinciden con las que publica el
   BanRep en su página.
3. El bloque I pasa con el modelo real y el sentido es correcto en la revisión
   (en especial: no presenta un escenario como pronóstico).
4. Suite completa en verde.

## Preguntas abiertas

Ninguna. Resueltas por el economista el 12/10/2026: exposición máxima (toda la
deuda se reprecia), escenario histórico incluido y comparación con la tasa de
colocación aplazada hasta poder aislar los intereses de la cuenta 5305.
