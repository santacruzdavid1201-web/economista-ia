# Spec: series-empresa

Módulo del [mapa de econometría](SPEC-mapa-econometria.md). Estado: aprobada por
el usuario el 16/10/2026, con los parámetros revisados.

## Objetivo

Que el gerente cargue la serie diaria de su hotel (exportación del PMS) y la vea
evolucionar, y que el sistema tenga un **hotel simulado con proceso generador
conocido** para validar cada estimador del módulo. Es la entrada de datos de
`pronostico-demanda`, `elasticidad-precio` y la evaluación de impacto.

Usuario: el gerente (carga y gráfica) y el código de los modelos (serie y
simulador).

## 1. Hotel simulado (`data_sources/empresa/pms_simulado.py`)

Es el mismo Hotel Demo Andino S.A.S. de los balances (Pasto, CIIU 5511, NIT
ficticio 900111222), para que el PMS y el estado de resultados cuenten la misma
historia. Demanda latente diaria, en logaritmos:

ln D_t = α + Fourier anual (K = 2) + día de la semana + calendario_t
         + ε · ln(P_t / IPC_t) + γ · ln(Pc_t / IPC_t) + tendencia · t + u_t,
u_t = ρ · u_{t−1} + e_t

Vendidas_t = min(disponibles_t, Poisson(D_t)): con el hotel lleno la demanda
queda **censurada**, como en la realidad. Los parámetros verdaderos quedan en
`config/pms_simulado.yaml`, para que los tests de cada estimador sepan qué deben
recuperar.

| Parámetro | Valor propuesto | Por qué |
|---|---|---|
| Habitaciones | 45 (1 o 2 en mantenimiento algunos días) | Ingresos de habitaciones ≈ 70 % de los ingresos del balance de demostración ($1.600 millones en 2023, $1.850 en 2024) |
| Historia | 1/1/2023 a 30/9/2026 (≈ 1.370 días, 4 Carnavales) | Cubre los años de los balances |
| Ocupación media | ≈ 40 % | EMA del DANE, región Pacífico: 42,5 % en agosto de 2025 y 37,0 % en agosto de 2026 |
| Tarifa base | $ 170.000 en 2023, indexada al IPC nacional real (copia de `data/series/`) | Hotel urbano de 3 o 4 estrellas en Pasto (supuesto) |
| Elasticidad propia ε | −1,2 | Demanda elástica: el hotel compite con otros hoteles y con apartamentos turísticos, sustitutos cercanos |
| Elasticidad cruzada γ | +0,4 | Si la competencia sube, se vende más |
| Día de la semana | domingo −25 %, lunes −5 %, martes a jueves +10 %, viernes +5 %, sábado 0 | Hotel urbano: negocios entre semana |
| Puente / víspera de festivo / Semana Santa | +25 % / +15 % / +30 % | |
| Carnaval | × 3,0 del 2 al 7 de enero y +35 % adicional el 5 y el 6 | Pasto se llena varios días seguidos (revisión del usuario: × 2,5 se quedaba corto); ahí se ve la censura |
| Tendencia real | +3 % al año | |
| Ruido | AR(1) con ρ = 0,5 y σ = 0,12 | Días buenos y malos seguidos |
| Tarifa según la demanda (revenue management) | +40 % en Carnaval, +15 % en puentes y Semana Santa, +10 % en diciembre, más un ruido de 3 % | El hotel sube precios cuando espera demanda: con lo observable es identificable con controles |
| Tarifa según lo no observable | 0 | La elasticidad lo activa en su escenario de falla |
| Promociones | 8 % de los días (más entre semana en temporada baja), 15 % de descuento, y un efecto de visibilidad de +10 % entre semana y 0 % el fin de semana | Para `impacto-recurrente`: efecto heterogéneo |
| Remodelación | desde el 1/7/2025, +8 % de demanda | Para `impacto-evento` |
| Tarifa de la competencia | Sigue la temporada, con un ruido propio de 5 % | Variación para la elasticidad cruzada |
| ADR realizado | Tarifa publicada menos un descuento corporativo de 0 % a 8 % | El ADR no es el precio: por eso la elasticidad usa la tarifa |

El simulador es una función pura con semilla fija, `simular_pms(parametros,
semilla)` → `DataFrame` canónico. La demostración la guarda en
`data/demo/pms_hotel_demo_andino.csv`, que queda versionado.

## 2. Cargador del PMS (`data_sources/empresa/pms.py`)

Lee CSV o Excel con el lector del cargador del PUC (filas de título antes del
encabezado, `;` o `,`, UTF-8 o Windows-1252, números colombianos o ingleses).
Columnas canónicas: `fecha`, `habitaciones_disponibles`, `habitaciones_vendidas`,
`ingresos_habitaciones` y las opcionales `tarifa_publicada`,
`tarifa_competencia`, `promocion` y `huespedes`. Acepta los nombres habituales de
las exportaciones en español e inglés ("Rooms Sold", "Habitaciones ocupadas",
"Room Revenue", …). Los errores dicen la fila y qué arreglar; las reglas que
también impone la base (vendidas ≤ disponibles) se revisan antes, con un mensaje
más claro.

## 3. Agregación e indicadores (`modules/econometria/indicadores.py`, puro)

Diaria, semanal o mensual, a partir de la serie del almacén:

- Ocupación = Σ vendidas / Σ disponibles (ponderada, no el promedio de los
  porcentajes diarios)
- ADR = Σ ingresos / Σ vendidas
- RevPAR = Σ ingresos / Σ disponibles = ocupación × ADR

Los periodos incompletos (el mes en curso, una semana con huecos) se marcan
como tales.

## 4. Interfaz

- La tarjeta "Su empresa" pide el **NIT** (sin puntos ni dígito de verificación;
  se limpian si vienen). Es opcional para los balances y obligatorio para las
  series.
- El tablero de **Econometría** pasa a activo, con la pestaña "Sus datos":
  - subir el archivo del PMS, o el botón **"Usar el hotel de demostración"**;
  - el resultado de la carga: días nuevos, corregidos, iguales y faltantes;
  - la gráfica de la evolución con selector de frecuencia (diaria, semanal,
    mensual) e indicador (habitaciones vendidas, ocupación, ADR, RevPAR), en SVG
    como las del tablero macro;
  - sin `DATABASE_URL`, un mensaje que dice cómo configurarla.
- Sin herramienta de chat todavía: llega con el pronóstico.

## Comandos

```
python -m data_sources.empresa.pms_simulado     # regenera el CSV de la demostración
python -m pytest -v
```

## Estrategia de pruebas

- **Simulador:** misma semilla, misma serie; ocupación media de 40 % ± 3 puntos;
  los días centrales del Carnaval por encima de 90 % y al menos tres días llenos
  en cada Carnaval; nunca más vendidas que
  disponibles; ingresos de habitaciones de 2023 y 2024 entre 60 % y 80 % de los
  ingresos del balance de demostración; 8 % ± 2 de días con promoción.
- **Cargador:** ida y vuelta (simulado → CSV → cargador = lo mismo), alias de
  columnas, formatos de números y errores con la fila.
- **Indicadores:** caso a mano de una semana para conciliar (ocupación ponderada
  con un día de habitaciones en mantenimiento).
- **Interfaz:** cargar la demostración dos veces da días iguales la segunda;
  la gráfica responde al selector; sin base, el mensaje.

## Límites

- Siempre: el simulador es de demostración y lo dice ("Hotel Demo Andino,
  datos simulados") en el tablero.
- Nunca: mezclar en una misma empresa datos simulados y reales.

## Criterios de éxito

1. El simulador reproduce los rangos de la estrategia de pruebas, y el usuario
   aprueba los parámetros verdaderos.
2. Con el botón de demostración, el tablero muestra la evolución mensual de las
   habitaciones vendidas, con el pico del Carnaval cada enero.
3. Un CSV con otro formato (nombres en inglés, separador `;`) carga igual.
4. Suite completa en verde.

## Decisiones del usuario (16/10/2026)

1. Parámetros revisados: razonables para un hotel urbano de Pasto; el Carnaval
   sube a × 3,0 y la elasticidad de −1,2 se justifica por los sustitutos.
2. El "Hotel de prueba (borrar)" de `almacen-datos` se borró.
