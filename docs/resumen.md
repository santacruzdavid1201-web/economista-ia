---
tags: [economista-ia, resumen]
---

# economista-ia — Resumen del proyecto

Agente de IA dirigido a empresas que ofrece lo que normalmente ofrece un economista: respuestas en lenguaje natural, pero fundamentadas en cálculos, modelos y teoría propia de cada área — no solo análisis de datos.

## Cómo se alimenta

- Datos de la empresa (balance, información interna)
- Datos de internet (contexto macro y sectorial)
- Un metaprompt que guía el rol y el alcance de las respuestas → ver [[metaprompt]]

## Módulos del MVP

1. [[balance-financiero]] — estado financiero de la empresa (probado con datos reales)
2. [[econometria-aplicada]] — evaluación de impacto vía Double ML / ML causal
3. [[evaluacion-proyectos]] — matemática financiera aplicada a evaluación de proyectos
4. [[entorno-macro]] — entorno macroeconómico y sectorial

Orden de construcción: 1 → 4 → 3 → 2.

Después se suma un módulo de carteras de inversión (Black-Litterman).

## Stack

Python, SQL, Power BI, R, Docker, APIs, Git. Google Cloud solo si resulta necesario y factible.

LLM local (LM Studio + Qwen, runtime Vulkan) para desarrollo; modelo por API para la demo pública.

## Estado actual

Ver [[decisiones]] para la bitácora de decisiones y avances.
