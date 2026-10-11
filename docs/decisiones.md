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

---
Vuelve a [[resumen]]
