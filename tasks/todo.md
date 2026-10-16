# Tareas: calendario

Plan: [plan.md](plan.md). Verificación común: `python -m pytest -v` antes del commit.

- [ ] **1. Festivos**: `config/calendario.yaml` con las reglas y su vigencia (Ley 2578
  desde 2026) y `festivos(anio)`: los 19 de 2026 conciliados; 2025 con 18 festivos en
  17 días (30/6 con los dos nombres) y Reyes que ya cae en lunes; error fuera de
  1984-2100.
  Archivos: `config/calendario.yaml`, `modules/econometria/calendario.py`,
  `tests/modules/econometria/test_calendario.py`.
- [ ] **2. Calendario diario**: `calendario(desde, hasta, ciudad)` con día de la
  semana, festivo, víspera, puente, Semana Santa y eventos de la ciudad (Carnaval en
  Pasto, sin tildes ni mayúsculas); rango invertido con error claro; bordes del rango.
  Archivos: `config/calendario.yaml`, `modules/econometria/calendario.py`,
  `tests/modules/econometria/test_calendario.py`.

### Punto de control: completo
- [ ] Criterios de éxito de la especificación; suite en verde; documentación de cierre.
