# Spec: flujo-proyecto

Módulo del [mapa de proyectos](SPEC-mapa-proyectos.md). Estado: aprobada y
construida el 15/10/2026 (falta la conciliación a mano del usuario).

## Objetivo

Convertir lo que el gerente sabe de su proyecto (cuánto invierte, cuánto
vende y gasta de más, cuántos años) en el flujo de caja libre año por año,
que es lo que evalúa la pieza siguiente (`evaluacion-proyecto`: VPN, TIR).

Usuario: el gerente, en el tablero de Proyectos. Un gerente de pyme sabe
cuánto le costará la remodelación y cuánto espera vender, pero no cómo
entran los impuestos, la depreciación o el capital de trabajo en el flujo;
eso lo pone Python.

## Entradas (formulario del tablero)

| Campo | Ejemplo | Nota para el usuario |
|---|---|---|
| Nombre del proyecto | Remodelación de 10 habitaciones | |
| Inversión inicial | 100 millones | Lo que se paga hoy en activos (obra, equipos) |
| Vida útil para depreciar | 5 años | Orientación fiscal: construcciones 45, maquinaria y muebles 10, cómputo 5; la define su contador |
| Horizonte de evaluación | 5 años | Máximo 30 |
| Ingresos adicionales del primer año | 60 millones | A precios de hoy; solo lo que el proyecto agrega |
| Crecimiento real de los ingresos | 0 % al año | Por encima de la inflación (más clientes o tarifas que suben más que los precios) |
| Costos variables | 30 % de los ingresos | |
| Costos fijos adicionales | 10 millones al año | A precios de hoy |
| Capital de trabajo | 10 % de los ingresos | Plata que queda en cartera e inventarios |
| Tarifa de impuesto de renta | 35 % | General (Ley 2277 de 2022); si el proyecto tiene una especial, la de su contador |
| Inflación esperada | Senda del BanRep | Por defecto, el pronóstico del último Informe de Política Monetaria y la meta de 3 % después; se puede reemplazar por una tasa fija |
| Valor de salvamento | (vacío) | Vacío: el valor en libros al final |

## Decisiones económicas (para aprobar)

1. **Flujo de caja libre, sin la financiación.** No se restan intereses ni
   cuotas del crédito: la financiación entra en la tasa de descuento (WACC,
   pieza `costo-capital`). Si se restaran aquí y además se descontara con el
   WACC, el costo de la deuda se contaría dos veces. Así se separan las dos
   preguntas: ¿el proyecto crea valor? y ¿cómo lo financio?
2. **Incremental.** Solo lo que cambia por el proyecto: ingresos y costos
   adicionales frente a no hacerlo. Lo ya gastado (estudios, diseños pagados)
   no entra: es costo hundido. Lo dice la ayuda del formulario.
3. **Precios de hoy por fuera, inflación por dentro.** El usuario escribe
   todo a precios de hoy y un crecimiento real. Python arma el flujo en pesos
   corrientes, porque así se pagan los impuestos, y lo devuelve en pesos de
   hoy, dividiendo por (1 + π)^t. Importa por dos efectos que el flujo real
   ingenuo ignora:
   - la depreciación es una deducción fija en pesos corrientes, así que la
     inflación le quita valor real al ahorro de impuestos que produce;
   - el capital de trabajo crece con la inflación aunque las ventas reales
     no crezcan, y esa plata adicional queda inmovilizada cada año.

   En el ejemplo, con 3 % de inflación el flujo del primer año baja de
   $ 27.800.000 a $ 27.416.117 en pesos de hoy. Ignorar estos efectos
   sobrevalora el proyecto, más cuanto más larga la vida útil.
4. **π = senda de inflación del BanRep, editable** (cambia la decisión 2 del
   mapa, que decía "expectativa de la encuesta"; pedido del usuario el
   15/10/2026). Para los años que cubre, el pronóstico del IPC total (fin de
   periodo) del último
   Informe de Política Monetaria; después, la meta de 3 % (SUAMECA 853). En el
   informe de julio de 2026: 6,9 % para 2026 y 4,3 % para 2027. Es la
   proyección oficial de quien fija la tasa, empalmada con su ancla de largo
   plazo, y no un pronóstico propio. El año t del proyecto se asocia al año
   calendario actual + t (supuesto declarado): hoy, el año 1 usa 4,3 % y los
   siguientes 3 %. El usuario puede escribir una tasa fija en su lugar.
   Aquí π solo afecta efectos de segundo orden (depreciación y capital de
   trabajo); en `costo-capital` pesa más, al pasar la tasa nominal a real, y
   ahí se revisa su coherencia con el TES.
5. **Impuesto con la tarifa general por defecto; las pérdidas ahorran
   impuestos.** Si un año el proyecto pierde, el impuesto sale negativo: se
   supone que la empresa tiene utilidades contra las cuales descontarlo
   (supuesto declarado). Si no las tiene, el proyecto vale menos de lo que
   muestra el flujo.
6. **Depreciación en línea recta** con la vida útil que escriba el usuario.
   Si la vida útil supera el horizonte, el valor en libros que queda pasa al
   salvamento.
7. **Capital de trabajo como % de los ingresos de cada año**, invertido al
   inicio del año y recuperado al final del horizonte.
8. **Salvamento.** Vacío: el valor en libros al final, sin impuesto. Si el
   usuario escribe un valor de mercado (a precios de hoy), la diferencia con
   el valor en libros paga la tarifa de renta. Es una aproximación declarada:
   la venta de activos puede tener otro tratamiento (ganancia ocasional), y
   eso lo define el contador.
9. **Un proyecto por sesión**, en memoria como la empresa, y sin necesidad
   de estados financieros. **Excepción a las reglas comunes del mapa:** la
   herramienta del chat llega con `evaluacion-proyecto`, porque un flujo sin
   evaluar no responde ninguna pregunta del gerente.

## Cálculo

Para t = 1…n (con g el crecimiento real y π la inflación):

- Índice de precios P_t = (1 + π₁) × … × (1 + π_t), con P_0 = 1 (π_t de la senda)
- Ingresos_t = I₁ × (1 + g)^(t−1) × P_t (pesos corrientes)
- Costos variables_t = cv × Ingresos_t; costos fijos_t = F × P_t
- Depreciación_t = inversión / vida útil, mientras t ≤ vida útil
- Utilidad operativa_t = ingresos − costos − depreciación
- Impuesto_t = tarifa × utilidad operativa_t (negativo si hay pérdida)
- Capital de trabajo_t = ct × Ingresos_t, invertido en t − 1; se recupera en n
- FCL_t = utilidad operativa − impuesto + depreciación − aumento del capital
  de trabajo (+ salvamento y recuperación del capital de trabajo en n)
- FCL_0 = −inversión − capital de trabajo del año 1
- En pesos de hoy: cada partida / P_t

## Diseño

- `modules/proyectos/flujo.py`: `Proyecto` (pydantic, valida rangos:
  horizonte 1-30, vida útil 1-50, porcentajes entre 0 y 100, montos
  positivos) y `flujo_caja(proyecto) -> ResultadoModulo` con la tabla por
  año en pesos de hoy, el total de cada partida, supuestos y fuentes (la
  meta de inflación con su fecha).
- `config/series.yaml`: `meta_inflacion` (853). El actualizador diario la
  incluye solo, como las demás series nacionales.
- `data_sources/externos/pronostico_banrep.py`: el Excel de variables del
  pronóstico del Informe de Política Monetaria, leído por etiquetas (hoja
  anual, fila "IPC total" y fila de años). **Se carga a mano cada trimestre**
  (cambio del 15/10/2026): el repositorio del BanRep tiene un sistema
  anti-bots que bloquea las descargas automáticas, y no se le da la vuelta.
  Se descarga el Excel en el navegador y `python -m
  data_sources.externos.pronostico_banrep <archivo.xlsx>` guarda la copia
  versionada en `data/series/pronostico_inflacion.json`. El tablero dice qué
  informe se usa y, pasados 4 meses desde él, avisa que puede haber uno más
  reciente. Sin copia, la meta sola con supuesto.
- **Tablero de Proyectos en pestañas** (pedido del usuario el 15/10/2026,
  para que el módulo no quede muy largo): "Su proyecto" (abre por defecto:
  formulario con el ejemplo y tabla del flujo por año; después se suman la
  evaluación, la sensibilidad y el Monte Carlo) y "Crédito y tasas" (el
  simulador y el conversor que ya existen). La pestaña va en la dirección
  (`/modulo/proyectos?pestana=credito`), así que recargar o compartir el
  enlace la conserva. HTMX cambia solo el contenido de la pestaña, sin
  JavaScript propio, y las pestañas son enlaces normales si HTMX no carga.
  Marcado accesible (`role="tablist"`, `aria-selected`). Si una pestaña
  crece demasiado con las piezas siguientes, se divide en otra.
- El formulario del proyecto sigue el patrón HTMX del simulador
  (`POST /proyectos/flujo`, recalcula solo la tabla); el proyecto válido
  queda en la sesión para la pieza siguiente.

## Comandos

```
python -m pytest tests/modules/proyectos -v
python -m pytest -v
python -m uvicorn app.main:app --port 8000      # /modulo/proyectos
```

## Estructura

```
modules/proyectos/flujo.py                     Proyecto, senda de inflación y flujo_caja
config/series.yaml                             meta_inflacion (853)
data_sources/externos/pronostico_banrep.py     pronóstico de inflación del Informe de Política Monetaria
data/series/pronostico_inflacion.json          copia versionada del pronóstico
tests/data_sources/externos/datos/ipm_*.xlsx   fixture recortado del Excel real
frontend/tableros.py, frontend/web.py          formulario, pestañas, ruta y proyecto en la sesión
frontend/templates/_tablero_proyectos.html     pestañas "Su proyecto" y "Crédito y tasas"
frontend/templates/_flujo.html                 tabla del flujo (respuesta del formulario)
tests/modules/proyectos/test_flujo.py
```

## Tests

Caso a mano (el ejemplo de la tabla de entradas, con la inflación fija que
escribe el usuario para que la cuenta sea sencilla): inversión 100 millones,
vida útil y horizonte 5 años, ingresos 60 millones, sin crecimiento real,
costos variables 30 %, costos fijos 10 millones, capital de trabajo 10 %,
tarifa 35 %, salvamento vacío.

| Año | FCL sin inflación | FCL con π = 3 % (pesos de hoy) |
|---|---|---|
| 0 | −106.000.000 | −106.180.000 |
| 1 | 27.800.000 | 27.416.117 |
| 2 | 27.800.000 | 27.218.171 |
| 3 | 27.800.000 | 27.025.992 |
| 4 | 27.800.000 | 26.839.409 |
| 5 | 33.800.000 | 32.838.261 |

Sin inflación, cada año: utilidad operativa 60 − 18 − 10 − 20 = 12 millones;
impuesto 4,2; flujo 12 − 4,2 + 20 = 27,8. En el año 5 se recuperan los 6
millones del capital de trabajo.

Además:

- Con π = 0, pesos corrientes y pesos de hoy coinciden.
- Senda: con el pronóstico de 2026 y 2027 y la meta de 3 %, en octubre de 2026
  el año 1 usa 4,3 % y los siguientes 3 %; el índice P_t encadena la senda.
- Lectura del Excel del informe con un fixture recortado del real: la fila
  del IPC total y sus años; un formato desconocido da un error útil y se cae
  a la copia guardada o a la meta.
- Con π > 0, el flujo en pesos de hoy es menor que sin inflación (depreciación
  y capital de trabajo), con todo lo demás igual.
- Vida útil mayor que el horizonte: el valor en libros restante entra como
  salvamento.
- Salvamento de mercado por encima del valor en libros: paga la tarifa sobre
  la diferencia.
- Año con pérdida: impuesto negativo y el supuesto en la lista.
- Validación: horizonte 0 o 31, porcentajes fuera de 0-100, inversión ≤ 0 →
  mensaje útil.
- Tablero: el formulario recalcula solo la tabla; un error muestra el mensaje.
- Pestañas: sin parámetro abre "Su proyecto"; `?pestana=credito` abre el
  simulador y el conversor; un valor desconocido cae en "Su proyecto".

## Límites

- Siempre: todo a precios de hoy en la pantalla; los supuestos (inflación,
  tarifa, pérdidas, salvamento) dichos en la tabla.
- Preguntar antes: financiación dentro del flujo.
- Fuera por ahora (15/10/2026): terrenos (no se deprecian y su valor sigue la
  inflación) y varias inversiones en años distintos.
- Nunca: proyectar ventas o precios por el usuario; decir si el proyecto
  "conviene" (eso es VPN, pieza siguiente).

## Criterios de éxito

1. El caso de la tabla da esos flujos y el usuario lo concilia a mano.
2. El tablero abre en la pestaña "Su proyecto" con el formulario del
   ejemplo y la tabla del flujo en pesos de hoy; cada cambio recalcula. El
   simulador y el conversor quedan en la pestaña "Crédito y tasas".
3. La inflación sale de la senda del BanRep (pronóstico del último informe y
   meta después), con su fuente y fecha, y se puede reemplazar por una fija.
4. Suite completa en verde.

## Preguntas abiertas

Ninguna. Resueltas el 15/10/2026:

1. Inflación esperada: el pronóstico del Informe de Política Monetaria (pedido
   del usuario), empalmado con la meta de 3 % después de su horizonte.
2. Terrenos y varias inversiones en años distintos quedan por fuera por ahora.
