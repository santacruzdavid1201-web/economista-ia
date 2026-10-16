# Tareas: series-empresa

Plan: [plan.md](plan.md). Verificación común: `python -m pytest -v` antes del commit.

- [x] **1. Hotel simulado**: `config/pms_simulado.yaml` con los parámetros verdaderos y
  `simular_pms(parametros, semilla)`: misma semilla, misma serie; ocupación media
  40 % ± 3; Carnaval central > 90 % y al menos tres días llenos por Carnaval; nunca
  más vendidas que disponibles; ingresos 2023 y 2024 entre 60 % y 80 % del balance;
  promociones 8 % ± 2; CSV de la demostración con su comando.
  Archivos: `config/pms_simulado.yaml`, `data_sources/empresa/pms_simulado.py`,
  `data/demo/pms_hotel_demo_andino.csv`, `tests/data_sources/empresa/test_pms_simulado.py`.
- [x] **2. Cargador del PMS**: CSV y Excel con el lector del PUC, alias en español e
  inglés, números de los dos formatos, errores con la fila; ida y vuelta con el
  simulado.
  Archivos: `data_sources/empresa/pms.py`, `tests/data_sources/empresa/test_pms.py`.
- [x] **3. Indicadores**: agregación diaria, semanal y mensual con ocupación ponderada,
  ADR y RevPAR; periodos incompletos marcados; caso a mano de una semana.
  Archivos: `modules/econometria/indicadores.py`, `tests/modules/econometria/test_indicadores.py`.

### Punto de control: datos
- [ ] El usuario concilia la semana a mano y revisa el comportamiento del simulado.

- [ ] **4. NIT en "Su empresa"**: campo nuevo, limpieza (puntos, dígito de
  verificación) y validación; se guarda en el almacén al cargar series.
  Archivos: `frontend/web.py`, `frontend/templates/_carga.html`, tests del frontend.
- [ ] **5. Pestaña "Sus datos"**: módulo de Econometría activo; subir el archivo o usar
  la demostración; resultado de la carga; gráfica con selector de frecuencia e
  indicador; mensaje sin base.
  Archivos: `frontend/modulos.py`, `frontend/tableros.py`, `frontend/web.py`,
  `frontend/templates/_tablero_econometria.html`, `frontend/static/estilo.css`, tests.

### Punto de control: completo
- [ ] El usuario ve en el tablero la evolución mensual con el pico del Carnaval;
  suite en verde; documentación de cierre.
