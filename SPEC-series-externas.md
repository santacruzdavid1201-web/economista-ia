# Spec: series-externas (primer tramo: IPC)

Módulo del [mapa macro](SPEC-mapa-macro.md). Estado: borrador para aprobación.

## Objetivo

Dar a los análisis del módulo 4 (y después a los módulos 3 y 2) series de
tiempo oficiales de Colombia en un formato único, con su fuente, unidad y
fecha de consulta, sin que ningún análisis sepa de dónde ni cómo se
descargaron. Este tramo cubre solo el IPC (nacional y por ciudad); tasas y
MMH se agregan en tramos siguientes con el mismo formato.

Usuario: los módulos de análisis (no el gerente directamente).

## Fuentes (averiguado el 7/10/2026)

| Serie | Fuente | Acceso |
|---|---|---|
| IPC nacional y por ciudad | Banco de la República, portal SUAMECA | `GET https://suameca.banrep.gov.co/estadisticas-economicas-back/rest/estadisticaEconomicaRestService/consultaInformacionSerie?idSerie=<id>` devuelve JSON con metadatos (nombre, unidad, periodicidad, fuente, notas) y la historia completa en `data: [[epoch_ms, valor], ...]`. Probado con la TRM (id 1, 12.735 datos desde 1991). |
| IPC nacional (verificación) | DANE, anexo `anex-IPC-Indices-<mes><año>.xlsx` | Índice mensual desde 2003, base diciembre 2018 = 100, una hoja con años en columnas. Es el productor original. |

**Riesgo.** La API de SUAMECA es la que usa el portal del BanRep por dentro; no
está documentada como servicio público y puede cambiar sin aviso. Se mitiga
con: caché local, copia versionada de cada serie usada, y la verificación
contra el anexo del DANE (si el IPC nacional deja de coincidir, algo cambió).
Con consultas en paralelo el servidor rechazó las conexiones: siempre en serie.

## Diseño

- `Serie` (pydantic, en `data_sources/externos/series/modelo.py`): clave,
  nombre, fuente, unidad, frecuencia (`mensual`, `diaria`...), geografía
  (`nacional` o la ciudad), base (p. ej. "dic 2018 = 100"), fecha de consulta y
  observaciones `list[tuple[date, float]]` ordenadas y sin duplicados.
  Métodos puros: `valor(fecha)`, `promedio(desde, hasta)`, `ultimo()`.
- Catálogo `config/series.yaml`: clave estable → fuente, id en la fuente,
  geografía, unidad. Ej.: `ipc_nacional`, `ipc_pasto`. Un análisis pide
  `serie("ipc", geografia="Pasto")` y recibe la de la ciudad o la nacional
  con un supuesto que lo dice.
- Cargadores: `banrep.py` (SUAMECA → `Serie`), `dane.py` (anexo IPC → `Serie`).
  Descarga separada de la transformación (como `supersociedades.py`), para
  probar la transformación sin red.
- Caché en `data/raw/series/<clave>.json`; se usa si tiene menos de 7 días.
  Si la descarga falla y hay caché vieja, se usa con una advertencia
  ("datos al <fecha>"); si no hay caché, error con mensaje útil.
- Copia versionada de las series que usa el demo en `data/series/`, para que
  los tests de punta a punta y la demo no dependan de la red.

## Comandos

```
python -m pytest -v                                   # sin red: fixtures JSON/xlsx
python -m data_sources.externos.series.actualizar     # descarga o refresca el catálogo
python -m data_sources.externos.series.actualizar --verificar   # IPC BanRep vs. DANE
```

## Estructura

```
config/series.yaml                       catálogo de series
data_sources/externos/series/
  modelo.py                              Serie y operaciones puras
  banrep.py                              cliente SUAMECA + transformación
  dane.py                                anexo IPC del DANE + transformación
  catalogo.py                            serie(clave, geografía) con caché y respaldo
  actualizar.py                          línea de comandos
tests/data_sources/externos/series/      tests con fixtures en tests/fixtures/series/
data/raw/series/                         caché (no versionada)
data/series/                             copias versionadas para demo y tests
```

## Estilo

Igual que el resto del proyecto: español, funciones puras para transformar,
descarga aislada, errores con mensajes para el usuario.

```python
def desde_suameca(respuesta: dict, clave: str, geografia: str) -> Serie:
    """JSON de consultaInformacionSerie → Serie. Sin red: se prueba con fixtures."""
```

## Tests

- Transformación SUAMECA y DANE con fixtures reales recortados (fechas epoch →
  mes, decimales, orden, duplicados).
- `Serie.promedio` y `valor` con casos calculados a mano.
- Catálogo: ciudad disponible, ciudad no disponible → nacional + supuesto,
  caché fresca, caché vieja con advertencia, sin caché y sin red → error.
- Ningún test toca la red.

## Límites

- Siempre: consultas en serie, con timeout y caché; fuente y fecha de consulta
  en cada `Serie`; tests sin red.
- Preguntar antes: agregar dependencias; cambiar el formato de `Serie` una vez
  lo usen otros módulos.
- Nunca: consultas en paralelo a las fuentes; valores de series escritos en el
  código; pronósticos.

## Criterios de éxito

1. `serie("ipc", "nacional")` y `serie("ipc", "Pasto")` devuelven el índice
   mensual con metadatos, desde la API o desde la caché.
2. El IPC nacional del BanRep coincide con el anexo del DANE (redondeado a 2
   decimales) en los últimos 24 meses (`--verificar`).
3. Sin red y con caché, todo funciona; sin red y sin caché, el error dice qué
   hacer.
4. Tests nuevos pasan y la suite completa sigue en verde.

## Preguntas abiertas

1. Ids de SUAMECA del IPC nacional y del IPC de Pasto: es la primera tarea
   (buscarlos en el catálogo del portal, a mano o con consultas en serie).
2. Si SUAMECA no publica el IPC de Pasto, la alternativa es el anexo de
   variaciones por ciudad del DANE (solo el mes publicado: habría que
   acumular la historia en la caché). Se decide al resolver la pregunta 1.
