# Plan: series-empresa

Especificación: [SPEC-series-empresa.md](../SPEC-series-empresa.md)
(aprobada el 16/10/2026). Tareas en [todo.md](todo.md).

## Decisiones de arquitectura

- `data_sources/empresa/pms_simulado.py`: `simular_pms(parametros, semilla)` puro,
  con los parámetros verdaderos en `config/pms_simulado.yaml`. Usa el `calendario`
  y el IPC nacional de la copia versionada (`data/series/ipc_nacional.json`), sin
  red: la misma semilla da la misma serie en cualquier máquina. Las variables de
  calendario y los choques se arman en arreglos de numpy (≈ 1.370 días: un bucle
  solo para el AR(1)).
- `data_sources/empresa/pms.py`: cargador que reutiliza el lector del PUC
  (`_filas`, `_decodificar`, `separador_decimal`, `a_numero`, `_simplificar`) y
  devuelve el `DataFrame` canónico que espera `almacen.cargar_pms`.
- `modules/econometria/indicadores.py`: agregación pura sobre el `DataFrame` de
  `leer_pms`; la ocupación, el ADR y el RevPAR se calculan de las sumas.
- Interfaz: el NIT entra por la tarjeta "Su empresa" (sesión) y se guarda en el
  almacén al cargar series; la pestaña "Sus datos" del tablero de Econometría lee
  del almacén. Las gráficas en SVG simple, como las del tablero macro (con la
  skill de visualización).

## Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| La calibración no da 40 % ni los ingresos del balance | Medio | `α` se fija en el YAML y los tests de rango (ocupación, ingresos 60 % a 80 % del balance) avisan si se sale. |
| El simulador cambia y los tests de los estimadores pierden la verdad | Alto | Parámetros verdaderos en un solo YAML; el CSV de la demostración se regenera con un comando y queda versionado. |
| Datos simulados confundidos con reales | Medio | El tablero dice "datos simulados"; NIT ficticio propio. |
| La gráfica diaria de 1.370 puntos pesa | Bajo | La polilínea SVG lleva pocos atributos; la vista por defecto es mensual. |
