# Hallazgos: datos de Supersociedades para el benchmark

Exploración del 4/10/2026 sobre los datasets NIIF de datos.gov.co. Las cifras
de disponibilidad son de hoteles (CIIU 5511-5512), corte 2024, 306 empresas.
Datos de soporte en `exploracion/salidas/` (no versionados, se regeneran).

## Tamaño

| Dataset | Id | Filas |
|---|---|---|
| Carátula | `6hqw-m3dm` | 9,6 M |
| Estado de Situación Financiera | `pfdp-zks5` | 19,6 M |
| Estado de Resultado Integral | `prwj-nzxa` | 8,1 M |

Nunca descargar completos: filtrar por NIT y `fecha_corte` en la consulta SoQL.

## 1. CIIU: viene en la carátula como concepto

- Concepto `Clasificación Industrial Internacional Uniforme Versión 4 A.C (CIIU)`
  (existe una variante sin "(CIIU)"; buscar por prefijo `Clasificaci`).
- Valor con formato `I5511 - Alojamiento en hoteles`: letra de sección +
  4 dígitos + descripción. El código son los caracteres 1 a 4.
- Se cruza con los estados por `nit` + `fecha_corte`.

Empresas únicas (individual o separado) por año:

| Año | Hoteles 5511-5512 | División 55 |
|---|---|---|
| 2015 | 30 | 30 |
| 2016 | 248 | 263 |
| 2017-2018 | ~195 | ~205 |
| 2019 | 261 | 278 |
| 2020-2021 | ~295 | ~323 |
| 2022 | 308 | 349 |
| 2023 | 322 | 354 |
| 2024 | 305 | 337 |
| 2025 | 365 | 395 |

La muestra nacional es amplia (muy por encima de 30). 2015 es el primer año
NIIF y casi vacío: no usarlo.

## 2. Qué reportes usar

- `punto_entrada`: quedarse con los códigos **10 y 40 (individual)** y
  **20 y 50 (separado)**; descartar 30/60 (consolidado) y 35/65 (combinado).
  Filtrar por los dos primeros caracteres: el texto cambió con los años
  ("Individuales" → "Individual Grupo 2").
- Con ese filtro ninguna empresa tiene individual y separado a la vez.
- `fecha_corte`: solo 31 de diciembre. Hay cortes intermedios (liquidaciones,
  p. ej. 2024-06-30).
- Retransmisiones: 1 de 306 empresas tiene dos radicados el mismo año; quedarse
  con el `numero_radicado` más reciente.
- `periodo`: cada reporte trae `Periodo Actual` y `Periodo Anterior`
  (comparativo). Usar `Periodo Actual`; el anterior sirve de respaldo para el
  saldo inicial si falta el reporte del año previo. Los años 2015-2017 usan
  etiquetas de año ("2016", "2016-S1") en lugar de esas dos.

## 3. Formato de los valores

- `valor` es texto: convertir a número.
- Unidad: **miles de pesos** (la carátula lo declara; la mediana de ingresos
  de los hoteles es 6,1 millones → $6.100 millones). Las razones no cambian;
  solo importa para montos (`Empresa.unidad = 1_000`).
- Los acentos vienen dañados desde la fuente (carácter U+FFFD, `Gastos de
  administraci�n`). El mapeo debe comparar nombres normalizados.
- Signos: costos y gastos en positivo; las utilidades, `Ganancias acumuladas`
  y el patrimonio pueden ser negativos (12 de 306 hoteles con patrimonio
  negativo).
- `Ingreso (gasto) por impuestos`: positivo = gasto (Ganancia = antes de
  impuestos − impuesto se cumple en el 99 %). Puede ser negativo (beneficio
  por impuesto diferido) y `EstadoResultados.impuesto_renta` hoy no admite
  negativos.
- El balance cuadra en el 100 % de los casos (activos = pasivos + patrimonio).

## 4. Diferencias con el esquema canónico (decisiones pendientes)

1. **Utilidad operacional.** El total NIIF `Ganancia (pérdida) por actividades
   de operación` INCLUYE otros ingresos y otros gastos (cuadra en el 100 %).
   Nuestro `utilidad_operacional` los excluye. No mapear ese total: reconstruir
   desde los componentes.
2. **Sin depreciación en el ERI.** El EBITDA (margen EBITDA, deuda/EBITDA) no
   sale de este dataset. Probar con el flujo de efectivo `ctcp-462n`
   (ajuste por depreciación y amortización del método indirecto).
3. **Cartera y proveedores agregados.** Solo existe `Cuentas comerciales por
   cobrar y otras cuentas por cobrar corrientes` y su equivalente por pagar.
   Para comparar igual con igual, el benchmark debe calcular los días de
   cartera y de proveedores de la empresa con la misma agregación.
4. **Costo de ventas ausente en el 9 %** (28 hoteles lo llevan todo a gastos
   de administración): margen bruto de 100 % y días de inventario no
   calculables. En hoteles, el margen operacional es más comparable.
5. **Deuda financiera:** en esta taxonomía `Otros pasivos financieros` es el
   TOTAL de pasivos financieros y `Préstamos corrientes` / `Parte corriente de
   préstamos no corrientes` son su desglose (el exceso coincidió con ese
   concepto en 225 de 225 casos). Se usa el total y, si no viene, el desglose.
6. **Utilidades retenidas:** `Ganancias acumuladas` incluye la utilidad del año
   (el patrimonio cuadra así en el 100 % de los hoteles 2024). Las acciones
   propias en cartera vienen en positivo y restan.
7. `Costos de distribución` (8 %) es sinónimo de gastos de ventas: sumarlos.

## 5. Disponibilidad (hoteles 2024)

Estado de resultados: ingresos, ganancia bruta, operativa, antes de impuestos
y neta 100 %; gastos de administración 96 %; costo de ventas 91 %; otros
ingresos 84 %; impuestos 81 %; otros gastos 80 %; costos financieros 75 %;
gastos de ventas 69 %; ingresos financieros 59 %.

Balance: totales de activo, pasivo, patrimonio, efectivo, activo corriente,
capital emitido y ganancias acumuladas 100 %; pasivo corriente 99 %; deudores
98 %; cuentas por pagar 97 %; PPE 94 %; inventarios 76 %; préstamos corrientes
39 %; préstamos no corrientes 36 %.

Que un concepto falte suele significar cero (la empresa no tiene esa cuenta),
no dato faltante. **Excepción: la depreciación.** Falta en el flujo de efectivo
del 22 % de los hoteles, y 55 de esos 67 tienen PPE (mediana $6.300 millones):
no la reportaron. Se trata como desconocida y esos hoteles no entran en el
benchmark de EBITDA. Los totales reportados permiten verificarlo: mapear las
cuentas, sumar y comparar contra `Total de activos` / `Total pasivos`; la
diferencia va a `otros_*` y se registra como medida de calidad.

## 6. Resultado del cargador (5/10/2026)

`data_sources/externos/supersociedades.py` con `config/mapeo_niif.yaml`,
sobre los hoteles 2024:

- 303 de 306 empresas cargadas, 605 periodos (2023 sale del comparativo del
  reporte 2024); 302 con dos periodos para saldo promedio.
- 7 periodos excluidos: 5 sin total de activo o pasivo corriente y 2 de una
  empresa que reporta la misma cifra como intangibles y como plusvalía.
- Balance: ninguna empresa queda con residuo sin clasificar después de mapear
  los activos pignorados como garantía.
- Resultados: 22 empresas con partidas no operacionales sin cuenta propia
  (van a otros ingresos o gastos, con supuesto).
- Depreciación en 238 empresas (79 %); 5 venían con signo negativo.
- Anomalía para el paso 5: hay hoteles con depreciación mayor que sus
  ingresos (p. ej. NIT 800108852). Los percentiles del benchmark resisten
  estos extremos, pero conviene revisarlos.
