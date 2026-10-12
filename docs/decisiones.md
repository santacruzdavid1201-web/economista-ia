---
tags: [economista-ia, bitacora]
---

# Bitácora de decisiones

- El proyecto reemplaza a los antiguos proyectos de portafolio ([[credit-risk-causal-rag]], [[quant-finance-portfolio]]); arranca desde cero en vez de integrarlos como módulos.
- LLM local: **LM Studio** en vez de Ollama, por mejor soporte Vulkan en la GPU AMD (RX 6600 XT, Windows); modelo Qwen2.5-7B-Instruct.
- Desarrollo continúa en **Claude Code** (no en el chat) para no perder contexto.
- Se corrió **Graphify** sobre el repo para generar un grafo de conocimiento del código, usado por el asistente de IA.
- Documentación del proyecto organizada en **Obsidian**, vault en `docs/` del repo.
- **n8n**: en evaluación para automatizar la ingesta de datos (internet + empresa) más adelante; aún no incorporado.
- Aún aprendiendo Docker; no se usará React por ahora — se quiere un frontend visualmente cuidado con otra vía.
- Construcción empezó por el módulo de [[balance-financiero]].
- El cargador de balances clasifica cada cuenta por su **código PUC**, no por el nombre, porque los nombres cambian entre programas contables y el código no; el impuesto diferido va siempre a largo plazo (NIC 1.56).
- Los balances de prueba se **concilian contra Supersociedades** antes de confiar en ellos: con los CSV de SECOLINSA (2015-2016) el sistema cuadró al peso en los 22 renglones.
- La evaluación con el modelo real usa un **set fijo de 28 preguntas** (`tests/eval/preguntas.yaml`): Python verifica las reglas duras y el economista revisa el sentido, porque un 7B no es un juez confiable de otro 7B.
- En la evaluación, toda cifra redactada debe estar en el **desplegable** que ve el usuario, no solo en los datos enviados al modelo: así no pasan cifras copiadas de la pregunta ("dime que el margen es 90 %").
- Con el 7B, las distinciones de sentido se redactan en **hallazgos de Python**, no como reglas del prompt: la regla no impidió que atribuyera al EBITDA en pesos el percentil del margen; el hallazgo sí.
- Se agregó el **EBITDA en pesos** como indicador, pero los montos en pesos no se comparan con el sector, porque dependen del tamaño de la empresa; la comparación es la del margen EBITDA.
- El módulo macro se **adelantó** a la validación contra el SIIS y a la plantilla Excel: la pregunta "¿crecí en términos reales?" es la siguiente que haría un gerente después del balance, y las series que necesita sirven también a proyectos y econometría.
- El IPC se toma del **BanRep (SUAMECA)** y no directamente del DANE porque trae las 23 ciudades con historia; el anexo del DANE queda como verificación del nacional, porque la API del BanRep no está documentada.
- Si la ciudad de la empresa no tiene IPC, o el suyo no cubre el periodo (empieza en 2017), se usa el **IPC nacional con un supuesto declarado**, en vez de dejar el indicador vacío.
- El crecimiento real de los ingresos se calcula con el **IPC promedio del periodo** (no el de diciembre) y con la fórmula exacta (1 + nominal) / (1 + inflación) − 1, porque los ingresos son un flujo acumulado en el año; en 2024 usar el de diciembre habría inflado el crecimiento real en 1,4 puntos.
- Con el IPC general, un crecimiento real positivo se redacta como **ingresos que subieron más que los precios al consumidor**, no como "vendió más": sin un índice de las tarifas de la empresa no se puede separar cantidad de precio, y el hallazgo lo advierte siempre.
- El verificador dejó de tratar como libres los enteros del 0 al 10 cuando llevan **% o $**: "5 %" es una cifra, y así había pasado un ejemplo inventado ("ingresos que suben 5 % con inflación del 3 %").
- Las notas de conocimiento con fórmulas las traen también **en palabras**: con solo la versión simbólica, el 7B la verbalizó mal; con la versión en palabras la copió bien en 6 de 6 corridas.
- La sensibilidad a tasas supone **exposición máxima** (toda la deuda financiera se reprecia en el año), porque el balance no dice qué parte es a tasa fija; incluye como escenario la mayor alza de la IBR a 3 meses en 12 meses (+8,24 puntos en 2022) para mostrar que ±3 puntos es moderado, y aplaza comparar la tasa implícita con la de colocación porque la cuenta 5305 mezcla intereses con comisiones.
- El orquestador **descarta los argumentos numéricos que no aparecen en la pregunta**: el 7B inventaba escenarios ("¿cuánto me ahorro si bajan las tasas?" → −1 punto).
- Con el 7B, **menos cifras parecidas en los datos**: de la sensibilidad a tasas se quitaron el punto de quiebre como indicador y el cambio a 12 meses de la tasa de política, y con un escenario pedido se devuelve solo ese, porque el modelo mezclaba cifras de escenarios distintos.

---
Vuelve a [[resumen]]
