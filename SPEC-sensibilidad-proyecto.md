# Spec: sensibilidad-proyecto

Módulo del [mapa de proyectos](SPEC-mapa-proyectos.md). Estado: propuesta del
15/10/2026, aprobada por el usuario el mismo día. Orden acordado: sensibilidad →
costo de capital; el Monte Carlo queda para después del módulo 2.

## Objetivo

Responder **¿qué tan frágil es el proyecto?**: cuánto se mueve el VPN si cada
variable sale distinta de lo previsto, y hasta dónde puede moverse antes de
que el proyecto deje de crear valor (o, si hoy no lo crea, cuánto tendría que
mejorar). Es la pregunta que hace todo gerente: "¿y si vendo menos?".

Usuario: el gerente, en una pestaña nueva del tablero de Proyectos y en el
chat ("¿y si vendo 10 % menos?", "¿hasta cuánto pueden caer las ventas?",
"¿qué variable pesa más en mi proyecto?").

## Decisiones (para aprobar)

1. **Una variable a la vez, lo demás igual** (ceteris paribus). Es la
   sensibilidad clásica y se lee fácil; que varias cosas salgan mal juntas lo
   mide el Monte Carlo (pieza posterior). Se declara como supuesto.
2. **Cinco variables, en cambios relativos de ±10 % y ±20 %:**
   - ingresos del primer año (todos los años se mueven en la misma
     proporción);
   - costos variables (el porcentaje: 30 % → 33 % es +10 %);
   - costos fijos;
   - inversión (mueve también la depreciación);
   - tasa de oportunidad.
   Quedan fuera el crecimiento real (en el ejemplo es 0 y un cambio relativo
   no aplica), la tarifa de renta y la inflación (el gerente no las controla
   y pesan menos). Precio y cantidad no se separan: el formulario pide los
   ingresos totales.
3. **Valor crítico de cada variable:** el cambio que deja el VPN en cero,
   buscado por bisección entre −99 % y +200 %. Se dice en porcentaje y en el
   valor de la variable: "los ingresos del primer año pueden caer hasta
   3,07 % ($ 58.158.000) antes de que el proyecto deje de crear valor". Con un
   VPN negativo, dice cuánto tendría que mejorar. Si no cruza cero en el
   rango, lo dice. **Chequeo:** la tasa crítica es la TIR.
4. **Tornado:** las cinco variables ordenadas de la que más mueve el VPN a la
   que menos, con barras horizontales desde el VPN base (HTML y CSS, como los
   otros tableros).
5. **Pestaña nueva "Sensibilidad"**, la tercera, sobre el proyecto de la
   sesión, o el de ejemplo, marcado como tal. No tiene formulario propio:
   para cambiar datos remite a "Su proyecto". Así la página no se alarga
   (pedido del usuario).
6. **Hallazgos en Python, con pocas cifras** (lección del 7B):
   - la variable que más mueve el VPN y su rango con ±10 %;
   - los valores críticos de las dos variables con menos margen ("basta que
     los ingresos caigan 3,1 % para que el proyecto deje de crear valor");
   - en el chat, el escenario pedido: "si los ingresos caen 10 %, el VPN pasa
     de $ 3.109.400 a −$ 7.012.001: el proyecto deja de crear valor".
7. **En el chat**, herramienta `analizar_sensibilidad_proyecto` con un
   parámetro opcional `cambio` (el porcentaje de la pregunta, validado por el
   orquestador). La variable ("ventas", "ingresos", "costos fijos",
   "inversión", "tasa"...) y la dirección ("caen", "bajan", "suben",
   "aumentan"...) las lee Python. "Costos" sin más se lee como costos
   variables, con supuesto. Sin cifra, responde el resumen: la variable que
   más pesa y los valores críticos.

## Diseño

- `modules/proyectos/sensibilidad.py`: `sensibilidad(proyecto, senda, tasa)
  -> ResultadoModulo` (tornado y valores críticos) y `escenario(proyecto,
  senda, tasa, variable, cambio) -> ResultadoModulo`. Usan `flujo_caja`,
  `vpn` y la bisección de `matematica_financiera` (se vuelve pública).
- `app/orchestrator/lectura.py`: `variable_del_proyecto(pregunta)` y
  `direccion(pregunta)`.
- `app/orchestrator/tools_registry.py`: `analizar_sensibilidad_proyecto`,
  con el proyecto de la sesión (como `evaluar_proyecto`).
- Tablero: pestaña "Sensibilidad" (`?pestana=sensibilidad`) con el tornado,
  la tabla de VPN por cambio y los valores críticos.
- Glosario (sensibilidad, valor crítico) y una sección nueva en
  `conocimiento/evaluacion-de-proyectos.md`.

## Tests

Caso a mano (para conciliar): el ejemplo sin inflación al 10 % (VPN base
$ 3.109.400).

| Variable | −20 % | −10 % | +10 % | +20 % | Valor crítico |
|---|---|---|---|---|---|
| Ingresos | −17.133.401 | −7.012.001 | 13.230.801 | 23.352.201 | −3,07 % |
| Inversión | 17.802.299 | 10.455.849 | −4.237.049 | −11.583.498 | +4,23 % |
| Costos variables | 11.979.841 | 7.544.621 | −1.325.820 | −5.761.041 | +7,01 % (30 % → 32,1 %) |
| Tasa de oportunidad | 9.080.838 | 6.031.893 | 306.645 | −2.382.660 | +11,12 % (10 % → 11,11 % = TIR) |
| Costos fijos | 8.037.423 | 5.573.412 | 645.389 | −1.818.623 | +12,62 % |

El orden de la tabla es el del tornado, de la variable que más mueve el VPN a
la que menos.

Además:

- La tasa crítica coincide con la TIR.
- Con un VPN base negativo, los valores críticos dicen cuánto mejorar.
- Variable sin cruce en el rango → hallazgo "no cambia de signo".
- Lectura: "¿y si vendo 10 % menos?" → ingresos, −10; "¿y si los costos
  fijos suben 20 %?" → costos fijos, +20; "costos" sin más → costos
  variables con supuesto.
- Chat con el modelo falso: escenario pedido, resumen sin cifra, sin
  proyecto → el mensaje de la pestaña.
- Tablero: pestaña con el tornado ordenado y los valores críticos.
- Bloque N del set con el modelo real.

## Límites

- Siempre: una variable a la vez, dicho como supuesto; el VPN base y la
  tasa usada a la vista.
- Nunca: llamar "riesgoso" o "seguro" al proyecto. Se dicen los márgenes; el
  juicio es del gerente.

## Criterios de éxito

1. El caso a mano da esas cifras y el usuario lo concilia.
2. La pestaña "Sensibilidad" muestra el tornado y los valores críticos del
   proyecto de la sesión.
3. El chat responde las tres preguntas del objetivo con la herramienta
   correcta; bloque N al 100 % con el modelo real.
4. Suite completa en verde.

## Preguntas abiertas

Ninguna. El usuario aprobó las cinco variables y la tercera pestaña (15/10/2026).
