# Mapa de capacidades: módulo 2, econometría aplicada

Aprobado por el usuario el 16/10/2026. Los ids son estables: las
especificaciones (`SPEC-<id>.md`) y los planes se refieren a ellos.

## Objetivo del módulo

Responder con modelos estimados sobre los datos del propio hotel las preguntas
que los estados financieros anuales no pueden contestar (dan 2 a 5 puntos):
¿cuánta demanda espero?, ¿qué pasa si subo la tarifa?, ¿funcionó la
promoción? La fuente es la exportación diaria del software hotelero (PMS), con
unas 365 observaciones al año. Usuario: el gerente de un hotel pyme.

| Id | Qué hace | Depende de |
|---|---|---|
| `almacen-datos` | PostgreSQL 18 local del usuario (base `economista_ia`, esquema en `db/init.sql`, conexión en `.env`; se inspecciona con pgAdmin) y funciones de lectura y escritura en `data_sources/`. Grano diario por empresa, con el NIT como llave; carga incremental con cualquier frecuencia (upsert idempotente por empresa y fecha, que corrige los días que el PMS revisa) y registro de cada carga (rango, filas nuevas y actualizadas, días faltantes). Guarda también el panel sectorial. | — |
| `series-empresa` | Carga la exportación diaria del PMS (CSV o Excel) al esquema canónico, la valida, la guarda por empresa y la agrega a semanas y meses (se calculan, no se guardan); ocupación, ADR y RevPAR. Hotel de demostración simulado con proceso generador conocido, calibrado con la MMH de Nariño y con el pico del Carnaval. La tarjeta "Su empresa" pide el NIT. Tablero: subir la serie y ver su evolución diaria, semanal o mensual (habitaciones vendidas, ocupación, ADR y RevPAR). | `almacen-datos`, `calendario` |
| `calendario` | Festivos de Colombia (Ley Emiliani, Semana Santa), puentes, temporadas y eventos locales por ciudad en `config/` (Pasto: Carnaval de Negros y Blancos, 2 al 7 de enero), como variables explicativas. Funciones puras. | — |
| `pronostico-demanda` | ¿Cuánta ocupación espero las próximas semanas o meses? Modelo ingenuo estacional como base y regresión armónica dinámica (Fourier anual, día de la semana, festivos y eventos como el Carnaval, con errores ARIMA); validación fuera de muestra (le gana o no al ingenuo, y se dice) e intervalos. En el chat y en el tablero (histórico, pronóstico e intervalo). | `series-empresa`, `calendario` |
| `sector-hotelero` | ¿Cómo va mi sector? Muestra Mensual de Hoteles (MMH) del DANE (anexos descargados de su página) y CITUR (MinCIT) para la región y el país, y panel multianual de Supersociedades en el almacén; la empresa frente al sector. Solo fuentes oficiales: no se raspan sitios de reservas (sus términos lo prohíben). | `almacen-datos`, `series-externas` |
| `elasticidad-precio` | ¿Si subo la tarifa 10 %, cuánto cae la ocupación y qué pasa con los ingresos? ln(vendidas) sobre ln(tarifa publicada real) con controles (calendario, Fourier, MMH regional); sin el ADR como precio (sesgo de división); sin los días llenos (demanda censurada); Double ML parcialmente lineal como robustez; por temporada si hay datos; elasticidad cruzada si viene la tarifa de la competencia. Dice el supuesto de identificación y cuándo no es creíble. | `series-empresa`, `calendario`, `sector-hotelero` |
| `impacto-evento` | ¿Funcionó una intervención única (remodelación, página web nueva)? Series de tiempo interrumpidas (el pronóstico con los datos de antes como contrafactual) y diferencias en diferencias contra la MMH regional, con revisión de tendencias previas y placebo. | `pronostico-demanda`, `sector-hotelero` |
| `impacto-recurrente` | ¿Funcionan las promociones que se repiten? Efecto promedio con Double ML y efectos heterogéneos con bosque causal (entre semana o fin de semana, temporada alta o baja), en ingresos y no solo en ventas. | `elasticidad-precio` |

## Orden de construcción

`almacen-datos` y `calendario` → `series-empresa` → `pronostico-demanda` y
`sector-hotelero` → `elasticidad-precio` → `impacto-evento` →
`impacto-recurrente`

La capa de datos va primero porque todo lo demás la lee; el calendario, porque
el hotel simulado necesita sus festivos y el Carnaval. El pronóstico va antes
que la elasticidad (decisión del usuario): es el más fácil de validar fuera de
muestra y da hecho el contrafactual de la evaluación de un evento único.
Con una sola unidad tratada y una sola fecha, el Double ML y el bosque causal no
tienen variación para estimar: sirven para las intervenciones recurrentes, que
van al final y reusan el Double ML de la elasticidad.
`sector-hotelero` no necesita datos nuevos de la empresa y llega antes de la
elasticidad para que la MMH sirva de control de demanda. Después del módulo
vuelve el Monte Carlo del módulo 3.

## Decisiones del usuario (16/10/2026)

1. **La fuente es la exportación diaria del PMS, con datos simulados** (no hay
   una exportación real). Esquema mínimo por día:
   habitaciones disponibles, habitaciones vendidas e ingresos de habitaciones
   (de ahí salen ocupación, ADR y RevPAR). Opcionales: tarifa publicada
   (la necesita la elasticidad), tarifa de la competencia (elasticidad
   cruzada), si hubo promoción, canal y huéspedes. El hotel simulado las trae
   todas. Las ventas mensuales de la
   contabilidad quedan fuera por ahora: 12 puntos al año no alcanzan.
2. **Pronóstico primero**, luego elasticidad e impacto.
3. **PostgreSQL desde ya, en el servidor 18 que el usuario ya tiene** (lo ve
   en pgAdmin); Docker entra cuando se empaquete la aplicación completa (app y
   base) para desplegarla: pasar a un contenedor es cambiar la conexión del
   `.env`. El NIT es la llave de la empresa. Es **actualizable**: la
   frecuencia de carga es libre (a diario, cada dos días, cada semana) y el
   grano es diario. Si algún hotel solo tuviera totales semanales o mensuales,
   se guardarían como periodos con inicio y fin (se agrega cuando aparezca el
   caso). El cambio queda en `data_sources/`: los módulos de cálculo reciben
   objetos de Python, nunca SQL. Las series externas y los balances del
   módulo 1 siguen como están.
4. **El Carnaval de Negros y Blancos es estacionalidad determinística**: se
   modela con variables de evento del calendario, no con diferencias
   estacionales (diferenciar a 365 días se come un año de datos y trata como
   estocástico algo conocido de antemano). El hotel simulado lo trae, y un
   test exige que el pronóstico con el evento le gane fuera de muestra al que
   no lo tiene.
5. **La evaluación de impacto son dos piezas:** intervenciones únicas primero
   (series interrumpidas y diferencias en diferencias), recurrentes después
   (Double ML y bosque causal). La tarifa de la competencia es una columna
   opcional: no hay fuente legal para rasparla.
6. **Datos del sector solo de fuentes oficiales** (DANE, CITUR,
   Supersociedades), descargados de sus páginas como ya se hace con el anexo
   del IPC; sirven también para calibrar el hotel simulado.

## Decisiones propuestas (para aprobar)

7. **Cada estimador se valida con datos simulados de proceso generador
   conocido** (semilla fija): el test comprueba que recupera la elasticidad o
   el efecto verdaderos dentro de su error; en la elasticidad, además, un
   mundo donde el hotel fija precios con información que no se observa, y el
   sistema debe advertirlo; en impacto, un placebo que dé cero. Además, un caso pequeño a mano que
   el usuario concilia, como en los módulos anteriores.
8. **El pronóstico de la propia empresa entra en el alcance**; los de la
   economía (dólar, inflación, tasas) siguen en `fuera_de_alcance`. Todo
   pronóstico va con intervalo y con su comparación contra el modelo ingenuo.
9. **Sin identificación no hay causalidad.** Cada estimación dice su supuesto
   (p. ej. "el precio no responde a choques de demanda que los controles no
   recogen") y devuelve `None` con advertencia cuando no es creíble (poca
   variación de precio, muestra corta).
10. **Librerías:** statsmodels y scikit-learn (con versiones para Python 3.14);
   psycopg 3 para PostgreSQL. El Double ML parcialmente lineal se escribe con
   validación cruzada sobre scikit-learn, sin DoubleML. El bosque causal
   (EconML o grf en R) se decide en la especificación de `impacto-recurrente`.

## Reglas comunes

- Cada pieza devuelve un `ResultadoModulo`, entra como herramienta del
  orquestador y trae su bloque en el set de evaluación.
- Los coeficientes se dicen en palabras en los hallazgos de Python ("si la
  tarifa sube 10 %, la ocupación cae cerca de 13 %"); al 7B no le llegan
  coeficientes crudos, errores estándar ni R².
- Precios y ADR en pesos reales (IPC) para estimar; en pesos corrientes para
  mostrar, dicho.
- El tablero de Econometría pasa de "próximamente" a activo con
  `series-empresa`.
- Sin autenticación, la base no se expone en la demo pública.

## Preguntas abiertas

Ninguna: el NIT como llave y el servidor local se decidieron el 16/10/2026.
