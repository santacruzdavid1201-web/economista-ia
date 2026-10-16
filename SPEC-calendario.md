# Spec: calendario

Módulo del [mapa de econometría](SPEC-mapa-econometria.md). Estado: aprobada por
el usuario el 16/10/2026.

## Objetivo

Dar, para cada día de un rango y una ciudad, los hechos del calendario que mueven
la demanda hotelera: festivos de Colombia, puentes, la noche antes de un festivo,
Semana Santa y eventos locales como el Carnaval de Negros y Blancos. Las
vacaciones no entran: son bloques de semanas que el ciclo anual del pronóstico
(Fourier) aproxima bien, y un rango aproximado le atribuiría un efecto a fechas
que no son exactas (decisión del usuario).
Son las variables explicativas determinísticas del pronóstico y de la
elasticidad, y las fechas que el hotel simulado usa para sus picos.

Usuario directo: el código (`series-empresa`, `pronostico-demanda`,
`elasticidad-precio`). No es una herramienta del chat.

## Reglas de Colombia (Ley 51 de 1983, "Ley Emiliani", y las que la modifican)

Las reglas van en `config/calendario.yaml`, cada una con el año desde el que
rige (y hasta cuál, si una ley o la Corte la cambia): una ley nueva es una línea
nueva, sin tocar el código.

- **Fijos:** 1 de enero, 1 de mayo, 20 de julio, 7 de agosto, 8 y 25 de diciembre.
- **Se corren al lunes siguiente** (si no caen en lunes): 6 de enero (Reyes), 19 de
  marzo (San José), 29 de junio (San Pedro y San Pablo), 15 de agosto (Asunción),
  12 de octubre (Día de la Raza), 1 de noviembre (Todos los Santos) y 11 de
  noviembre (Independencia de Cartagena). Desde 2026, también el 9 de julio
  (Virgen de Chiquinquirá, Ley 2578 de 2026; hay una demanda en la Corte
  Constitucional que, si prospera, regiría desde 2027).
- **Según la Pascua:** Jueves y Viernes Santo (Pascua − 3 y − 2 días); Ascensión
  (Pascua + 39), Corpus Christi (Pascua + 60) y Sagrado Corazón (Pascua + 68),
  corridos al lunes siguiente. La fecha de la Pascua sale de
  `dateutil.easter`, que ya viene con pandas.

## Variables por día

| Columna | Qué es |
|---|---|
| `dia_semana` | 0 lunes … 6 domingo |
| `festivo` | el día es festivo; `nombre_festivo` dice cuál |
| `vispera_festivo` | el día siguiente es festivo |
| `puente` | sábado, domingo o lunes de un fin de semana con lunes festivo, o viernes, sábado o domingo con viernes festivo |
| `semana_santa` | del Domingo de Ramos al Domingo de Resurrección |
| `evento_<clave>` | un evento local de la ciudad, de `config/calendario.yaml` |

**La noche es la del día.** El PMS cuenta cada noche vendida en la fecha en que
empieza. Por eso importa `vispera_festivo`: en un hotel vacacional, el domingo
antes de un lunes festivo se llena como un sábado. Sin esa variable, el modelo
confundiría ese domingo con uno normal.

## Configuración (`config/calendario.yaml`)

```yaml
festivos:
  fijos:                          # mes-día
    - {fecha: 01-01, nombre: Año Nuevo}
    # …
  trasladables:                   # se corren al lunes siguiente
    - {fecha: 01-06, nombre: Reyes Magos}
    # …
    - {fecha: 07-09, nombre: Virgen de Chiquinquirá, desde: 2026}   # Ley 2578 de 2026
  pascua:                         # días desde el Domingo de Pascua
    - {dias: -3, nombre: Jueves Santo}
    - {dias: 39, nombre: Ascensión del Señor, trasladable: true}
    # …
eventos:
  Pasto:
    - {clave: carnaval, nombre: Carnaval de Negros y Blancos, desde: 01-02, hasta: 01-07}
    - {clave: carnaval_central, nombre: Días de Negros y de Blancos, desde: 01-05, hasta: 01-06}
```

Si dos festivos caen el mismo día (el 30 de junio de 2025, San Pedro y San
Pablo y el Sagrado Corazón), es un solo día festivo con los dos nombres. Las
ciudades se buscan sin tildes ni mayúsculas, como en las series del IPC.
Agregar una ciudad o un evento es agregar líneas al YAML, sin tocar el código.

## Interfaz (`modules/econometria/calendario.py`, puro)

```python
def festivos(anio: int) -> dict[date, str]: ...       # fecha → nombre
def calendario(desde: date, hasta: date, ciudad: str | None = None) -> pd.DataFrame: ...
```

`calendario` devuelve un `DataFrame` con índice diario de fechas y las columnas
de arriba, en booleanos salvo `dia_semana` y `nombre_festivo`. Sin ciudad, o con
una ciudad sin eventos, no hay columnas `evento_*`.

## Comandos

```
python -m pytest tests/modules/econometria/test_calendario.py -v
```

## Estrategia de pruebas

- **Caso a mano, conciliado por el usuario el 16/10/2026:** los 19 festivos de
  2026, con Pascua el 5 de abril: 1/1, 12/1, 23/3, 2/4, 3/4, 1/5, 18/5, 8/6,
  15/6, 29/6, 13/7, 20/7, 7/8, 17/8, 12/10, 2/11, 16/11, 8/12 y 25/12. El 13/7
  es el 9 de julio de la Ley 2578 corrido al lunes; el usuario lo detectó al
  conciliar.
- 2025 tiene 18 festivos en 17 días (todavía sin el 9 de julio; San Pedro y
  San Pablo y el Sagrado Corazón coinciden el 30 de junio), otra Pascua (20 de
  abril) y un festivo que ya cae en lunes no se corre (Reyes, 6 de enero).
- Puentes y vísperas de un fin de semana con lunes festivo; Semana Santa de 2026
  (29/3 al 5/4).
- Pasto tiene `evento_carnaval` del 2 al 7 de enero de cada año y
  `evento_carnaval_central` el 5 y el 6; otra ciudad, ninguno.
- Error claro para un rango invertido o un año fuera de 1984-2100 (la Ley
  Emiliani rige desde 1984).

## Límites

- Siempre: las fechas de leyes y eventos salen de reglas del YAML con su
  vigencia, nunca escritas a mano en el código por año. Revisar la decisión de
  la Corte sobre la Ley 2578 antes de 2027.
- Preguntar antes: agregar fechas que cambian cada año sin una regla (p. ej. un
  festival con fecha variable).
- Nunca: inventar eventos de una ciudad; si no está en el YAML, no existe.

## Criterios de éxito

1. `festivos(2026)` da los 19 de la lista (conciliados) y `festivos(2025)`, 17
   días con los dos nombres el 30 de junio.
2. `calendario(1/1/2025, 31/12/2026, "Pasto")` da 730 días con todas las
   columnas, y el Carnaval cae del 2 al 7 de enero de los dos años.
3. Suite completa en verde.

## Decisiones del usuario (16/10/2026)

1. Carnaval del 2 al 7 de enero, con el 5 y el 6 (Negros y Blancos) como días
   centrales; otros días (Inocentes, Años Viejos) se agregan al YAML si hace
   falta.
2. Sin vacaciones: las capta el ciclo anual del pronóstico.
