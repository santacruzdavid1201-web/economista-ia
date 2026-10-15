# Spec: evaluacion-proyecto

Módulo del [mapa de proyectos](SPEC-mapa-proyectos.md). Estado: propuesta del
15/10/2026, aprobada por el usuario el mismo día.

## Objetivo

Responder la pregunta del gerente: **¿me conviene el proyecto?**, con el flujo
de caja libre de `flujo-proyecto` y una tasa de oportunidad. Primero con la
tasa que escribe el usuario; cuando exista `costo-capital`, con el WACC de la
empresa como tasa recomendada.

Usuario: el gerente, en la pestaña "Su proyecto" del tablero y en el chat
("¿me conviene el proyecto?", "¿cuál es la TIR?", "¿y si mi tasa de
oportunidad es 18 %?").

## Decisiones económicas (para aprobar)

1. **La tasa de oportunidad la escribe el usuario, efectiva anual
   nominal**, que es como se cotizan todas las tasas en Colombia: la
   rentabilidad que exigiría a otra inversión de riesgo parecido. El
   formulario abre con el proyecto de ejemplo y una tasa de ejemplo de
   15 %, con el aviso visible "Los valores iniciales son un ejemplo:
   reemplácelos por los de su proyecto", para que nadie crea que la tasa
   sale de una fuente. El mismo aviso va en la pestaña "Crédito y tasas"
   (decidido el 15/10/2026: un ejemplo calculado enseña cómo se llena el
   formulario; lo que confundía era que no dijera que es un ejemplo).
2. **Cálculo coherente con la inflación.** El VPN descuenta los flujos en
   pesos corrientes con la tasa nominal. Es la misma cifra que descontar los
   flujos en pesos de hoy con la tasa real de cada año, (1 + i) / (1 + π_t) − 1,
   y no exige elegir una sola inflación. El VPN se muestra en pesos de hoy
   (está en el año 0).
3. **La TIR se muestra nominal**, para compararla directamente con la tasa
   que escribió el usuario: "TIR de 13,40 % frente a su tasa de 15 %". Una
   TIR real habría que compararla con una tasa real que cambia año por año
   con la senda de inflación, y eso confunde. Si hay varias TIR o ninguna,
   `None` con el aviso de `matematica-financiera`.
4. **Manda el VPN.** Es el criterio que nunca falla: la TIR puede no existir,
   ser varias o engañar al comparar proyectos de distinto tamaño. Los
   hallazgos lo dicen en ese orden:
   - VPN > 0: "Con una tasa de oportunidad de 15 %, el proyecto crea valor:
     deja $ X más, en pesos de hoy, que invertir esa plata en la alternativa."
   - VPN < 0: "…no crea valor: deja $ X menos que la alternativa."
   - TIR frente a la tasa, solo si hay una sola TIR.
   - Recuperación descontada: "recupera la inversión, con su costo de
     oportunidad, en 4,9 años de 5", o "no la recupera dentro del horizonte".
   - "Crear valor" es un criterio de decisión, no una opinión. No se dice
     "buen proyecto", "rentable" ni "le conviene": eso depende también del
     riesgo y de la caja de la empresa, que miran las piezas siguientes.
5. **Indicadores:** VPN, TIR, TIRM (reinversión a la tasa de oportunidad,
   supuesto declarado), recuperación descontada e índice de rentabilidad. El
   valor anual equivalente queda fuera: sirve para comparar proyectos de
   distinta vida, y todavía no se comparan proyectos.
6. **En el chat**, herramienta `evaluar_proyecto` sobre el último proyecto
   válido de la sesión, sin necesidad de estados financieros. Parámetro
   opcional `tasa` si la pregunta da otra ("¿y si mi tasa es 18 %?"); el
   orquestador descarta la tasa si no está en la pregunta. Sin proyecto en la
   sesión: "Primero escriba su proyecto en la pestaña Su proyecto del módulo
   Evaluación de proyectos".

## Diseño

- `modules/proyectos/evaluacion.py`: `evaluar(flujo, tasa) -> ResultadoModulo`
  con los indicadores (valor, unidad, fórmula) y los hallazgos de la
  decisión 4. Usa las funciones de `matematica_financiera` (ya conciliadas).
- `frontend/tableros.py`: `flujo()` lee también la tasa de oportunidad y
  devuelve la evaluación. En la pestaña "Su proyecto": la tasa entra en el
  grupo Supuestos del formulario; arriba de la tabla del flujo, tarjetas con
  el VPN, la TIR, la TIRM, la recuperación y el índice, y los hallazgos.
- La sesión guarda el proyecto con su tasa (ya guarda lo que se escribió).
- Chat: `responder(..., proyecto=…)` recibe el proyecto de la sesión y lo
  pasa a las herramientas con sus argumentos, como la pregunta. Reglas del
  enrutador: preguntas sobre "mi proyecto" → `evaluar_proyecto`; "¿qué es la
  TIR?" → conceptual. El set de evaluación corre con el proyecto de ejemplo.
- Nota de conocimiento `conocimiento/evaluacion-de-proyectos.md`: VPN, TIR,
  TIRM, recuperación, índice, tasa de oportunidad, por qué manda el VPN y por
  qué la inflación entra en la tasa y en el flujo (la explicación del
  15/10/2026). Para revisión del usuario.

## Comandos

```
python -m pytest tests/modules/proyectos -v
python -m pytest -v
python -m app.eval --bloques M
python -m uvicorn app.main:app --port 8000      # /modulo/proyectos
```

## Estructura

```
modules/proyectos/evaluacion.py                 evaluar(flujo, tasa)
frontend/tableros.py, frontend/web.py           tasa en el formulario, tarjetas, proyecto al chat
frontend/templates/_pestana_proyecto.html       campo de la tasa y línea de "valores de ejemplo"
frontend/templates/_flujo.html                  tarjetas y hallazgos de la evaluación
app/orchestrator/tools_registry.py              evaluar_proyecto
app/orchestrator/orquestador.py                 el proyecto de la sesión a las herramientas
config/prompts/router.md, config/glosario.yaml  reglas y definiciones (VPN, TIR...)
conocimiento/evaluacion-de-proyectos.md
tests/modules/proyectos/test_evaluacion.py
tests/eval/preguntas.yaml                       bloque M
```

## Tests

Caso a mano (para conciliar): el proyecto de ejemplo **sin inflación** (π = 0
fija) y tasa de oportunidad de 10 %. Flujos: −106.000.000; 27.800.000 cuatro
años; 33.800.000 el quinto.

| Año | Flujo descontado al 10 % | Acumulado |
|---|---|---|
| 0 | −106.000.000 | −106.000.000 |
| 1 | 25.272.727 | −80.727.273 |
| 2 | 22.975.207 | −57.752.066 |
| 3 | 20.886.551 | −36.865.515 |
| 4 | 18.987.774 | −17.877.741 |
| 5 | 20.987.141 | 3.109.400 |

- VPN = $ 3.109.400 (crea valor)
- TIR = 11,11 % (mayor que 10 %)
- TIRM = 10,64 %
- Recuperación descontada = 4 + 17.877.741 / 20.987.141 = 4,85 años
- Índice de rentabilidad = 109.109.400 / 106.000.000 = 1,03

Además:

- Con la senda del BanRep y 15 %: VPN negativo → el hallazgo dice "no crea
  valor"; la TIR (13,40 % con π = 3 % fija) es menor que la tasa.
- Coherencia: VPN de los flujos corrientes a la tasa nominal = VPN de los
  flujos en pesos de hoy a la tasa real de cada año.
- Sin TIR única: el hallazgo de la TIR no aparece y la advertencia sí.
- Sin recuperación dentro del horizonte: "no la recupera".
- Chat con el modelo falso: con proyecto en la sesión, la herramienta lo
  evalúa; con "¿y si mi tasa es 18 %?", usa 18 %; sin proyecto, el mensaje
  que remite a la pestaña.
- Tablero: tarjetas y hallazgos con el ejemplo; tasa vacía o inválida →
  mensaje útil.

## Límites

- Siempre: el VPN primero; la tasa usada y su naturaleza (nominal, efectiva
  anual, la del usuario) dichas en la respuesta.
- Preguntar antes: comparar varios proyectos; pedir la tasa en otros tipos
  (para eso está el conversor de la otra pestaña).
- Nunca: recomendar hacer o no el proyecto; calificar la TIR de "buena".

## Criterios de éxito

1. El caso a mano da esas cifras y el usuario lo concilia.
2. La pestaña "Su proyecto" muestra las tarjetas de la evaluación arriba de
   la tabla, con la línea de valores de ejemplo.
3. El chat responde "¿me conviene el proyecto?" con el VPN primero y la
   tasa usada; bloque M del set al 100 % con el modelo real.
4. Suite completa en verde.

## Preguntas abiertas

Ninguna. Resueltas el 15/10/2026: tasa de ejemplo de 15 % dentro de un
ejemplo marcado como tal, y el mismo aviso en el simulador de crédito.
