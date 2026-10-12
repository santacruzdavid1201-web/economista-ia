# Spec: crecimiento-real

Módulo del [mapa macro](SPEC-mapa-macro.md). Depende de
[series-externas](SPEC-series-externas.md) y del módulo 1. Estado: aprobado
y construido el 11/10/2026. Criterio 1 cumplido el 11/10/2026: el cálculo a
mano del economista coincidió con el módulo (diferencias de 10⁻¹¹ por
redondeo). Criterio 2: la primera corrida del bloque H pasó las reglas
automáticas, pero con dos errores de sentido: "volumen de ventas" en las de
cálculo (lo decía el propio hallazgo de Python) y fórmula por resta en la
conceptual (la nota no la traía). Corregidos el 12/10/2026 con un hallazgo
sobre el límite del IPC general y la nota `conocimiento/crecimiento-real.md`
(pendiente de revisión del economista); el bloque H pasó 4 de 4 con las
reglas nuevas y la conceptual dio la fórmula correcta 6 de 6 veces.

## Objetivo

Responder "¿crecí en términos reales?" y sus variantes ("¿mis ventas le
ganaron a la inflación?"): separar cuánto del crecimiento de los ingresos es
más actividad y cuánto es solo precios más altos.

Usuario: el gerente, a través del orquestador.

## Decisiones económicas

- **Deflactor: IPC promedio del periodo, no el de diciembre.** Los ingresos son
  un flujo acumulado durante el año; se comparan con el nivel de precios
  promedio de ese año. El IPC de diciembre sirve para saldos (balance), no
  para flujos. Con periodos de menos de 12 meses, se promedian los meses que
  cubre el estado.
- **Fórmula exacta, no aproximada:** crecimiento real =
  (1 + crecimiento nominal) / (1 + inflación promedio) − 1. La resta
  "nominal − inflación" se aleja con inflaciones altas (2022-2023).
- **IPC de la ciudad de la empresa** si existe (Pasto para el hotel demo);
  si no, el nacional, y se registra como supuesto.
- **El IPC general como deflactor** es un supuesto que se declara: los
  precios propios de la empresa (tarifas) pueden subir distinto. Por eso un
  crecimiento real positivo significa que los ingresos subieron más que los
  precios al consumidor (más poder de compra), no que se vendió más
  cantidad; un hallazgo lo dice siempre. Cuando exista la MMH
  (`sector-hotelero`) se podrá contrastar.
- Es un dato observado del pasado, sin juicio de "bueno/malo": el hallazgo
  dice si los ingresos subieron o cayeron en términos reales, nada más.

## Resultado

`crecimiento_real(historial, i, ipc: Serie) -> ResultadoModulo`
(`modules/macro/crecimiento_real.py`), análisis `crecimiento_real`:

| Indicador | Unidad | Fórmula |
|---|---|---|
| `crecimiento_nominal_ingresos` | proporción | Ingresos t / Ingresos t−1 − 1 (anualizados si < 12 meses) |
| `inflacion_promedio` | proporción | IPC promedio periodo t / IPC promedio periodo t−1 − 1 |
| `crecimiento_real_ingresos` | proporción | (1 + nominal) / (1 + inflación) − 1 |
| `ingresos_anteriores_a_precios_actuales` | pesos | Ingresos t−1 × IPC prom. t / IPC prom. t−1 |

Hallazgos de ejemplo (redactados en Python): "Entre 2023 y 2024 los ingresos
operacionales crecieron 15,6 % en pesos corrientes y 9,3 % en términos reales,
es decir, descontada la inflación promedio de Pasto (5,8 %)." (nominal y real
en paralelo: si el hallazgo compara con la inflación, el 7B pega la
comparación al real) y "Este crecimiento real descuenta la inflación
general (IPC), no las tarifas propias de la empresa: no permite saber si
cambió la cantidad vendida o si sus precios subieron más o menos que la
inflación."

Sin periodo anterior, o si el IPC no cubre los meses de algún periodo:
indicadores `None` con advertencia, nunca un número engañoso.

## Integración

- Herramienta `analizar_crecimiento_real` en `app/orchestrator/tools_registry.py`
  (descripción en lenguaje de gerente). `ContextoEmpresa` gana acceso a las
  series (sin romper los usos actuales).
- Entradas nuevas en `config/glosario.yaml` (crecimiento real, deflactar).
- Bloque H "Entorno macro" en `tests/eval/preguntas.yaml`, por ejemplo:
  "¿Crecí en términos reales?", "¿Mis ventas le ganaron a la inflación?",
  "¿Cuánto crecí en 2024 descontando la inflación?" (todas
  `analizar_crecimiento_real`, `cifra_de: [crecimiento_real_ingresos]`), y
  "¿Qué es el crecimiento real?" (conceptual, nota de crecimiento real).

## Comandos

```
python -m pytest -v
python -m app.demo "¿Crecí en términos reales?"
python -m app.eval --bloques H
```

## Tests (primero el test, después la función)

- Caso a mano: ingresos 1.000 → 1.100 con IPC promedio 100 → 105 da
  nominal 10 %, inflación 5 %, real 4,76 % (y no 5 %).
- Periodo de 6 meses: promedia solo esos meses y anualiza ingresos.
- Ciudad sin IPC, o con IPC que no cubre las fechas (antes de 2017) →
  nacional + supuesto; sin periodo anterior → `None` + advertencia; ni el
  IPC nacional cubre las fechas (mes aún no publicado) → `None` + advertencia.
- Hallazgo dice "cayeron" cuando el real es negativo aunque el nominal suba.
- Orquestador con LLM falso: enruta y redacta con las cifras del resultado.

## Límites

- Siempre: deflactar flujos con promedio del periodo; declarar la serie y la
  geografía usadas en `fuentes` y `supuestos`.
- Preguntar antes: usar otro deflactor (IPC de servicios, de hoteles).
- Nunca: proyectar la inflación ni el crecimiento; calificar el resultado
  sin referencia sectorial.

## Criterios de éxito

1. Para el hotel demo (2023 → 2024, Pasto) las cifras coinciden con un
   cálculo a mano en una hoja de cálculo con el IPC descargado.
2. El bloque H del set de evaluación pasa con el modelo real y el sentido de
   las respuestas es correcto en la revisión.
3. Suite completa en verde.

## Preguntas abiertas

Ninguna. El IPC de Pasto existe en SUAMECA (id 15026, desde 2017).

Con los datos reales, las dos decisiones económicas pesan: en 2024 la
inflación nacional promedio fue 6,61 % y la de diciembre a diciembre 5,20 %
(deflactar con la de diciembre sobrestimaría el crecimiento real en 1,4
puntos); la de Pasto promedio fue 5,83 %, 0,8 puntos por debajo de la nacional.
