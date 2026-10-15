"""
Catálogo de series externas: `serie("ipc", "Pasto")` y nada más.

El análisis pide variable y geografía; el catálogo resuelve el id
(`config/series.yaml`), usa la copia de hoy si existe, descarga si no, y cae a
la serie nacional con un supuesto cuando la ciudad no tiene serie o la suya no
cubre las fechas pedidas.

Las descargas van a `data/cache/series/` (sin versionar); `data/series/` es el
respaldo versionado para los tests, la demo y el primer arranque sin red. La
interfaz llama a `actualizar()` al arrancar y cada 6 horas.

    python -m data_sources.externos.series.catalogo Pasto   # refresca y verifica
    python -m data_sources.externos.series.catalogo --tasas # tasa de política e IBR
"""
from __future__ import annotations

import argparse
import sys
import threading
import unicodedata
from datetime import date, timedelta
from pathlib import Path

import requests
import yaml

from data_sources.externos.series import banrep, dane
from data_sources.externos.series.modelo import Serie

RAIZ = Path(__file__).resolve().parents[3]
CATALOGO = RAIZ / "config" / "series.yaml"
DIRECTORIO = RAIZ / "data" / "cache" / "series"
RESPALDO = RAIZ / "data" / "series"
VIGENCIA = timedelta(days=1)
# Una descarga a la vez, también entre el actualizador y las consultas: en
# paralelo SUAMECA rechaza las conexiones.
_DESCARGA = threading.Lock()
TASAS = ["tasa_politica", "ibr_3m"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


class ErrorSerie(ValueError):
    """La serie no se pudo obtener; el mensaje dice qué hacer."""


def sin_tildes(texto: str) -> str:
    """'Bogotá' y 'bogota' coinciden."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c)).lower().strip()


def _catalogo() -> dict:
    return yaml.safe_load(CATALOGO.read_text(encoding="utf-8"))


def _buscar(variable: str, geografia: str) -> tuple[str, int] | None:
    """(nombre en el catálogo, id en la fuente) o None si no hay serie."""
    ids = _catalogo()[variable]["ids"]
    return next(((n, i) for n, i in ids.items() if sin_tildes(n) == sin_tildes(geografia)), None)


def obtener(variable: str, geografia: str, hoy: date, directorio: Path = DIRECTORIO,
            forzar: bool = False) -> Serie:
    """
    Copia de hoy si existe; si no, descarga. Sin red, la copia vieja (o la del
    respaldo versionado) con advertencia.
    """
    nombre, id_serie = _buscar(variable, geografia)
    clave = f"{variable}_{sin_tildes(nombre).replace(' ', '_')}"
    archivo = directorio / f"{clave}.json"
    copia = next((a for a in (archivo, RESPALDO / archivo.name) if a.exists()), None)
    guardada = Serie.model_validate_json(copia.read_text(encoding="utf-8")) if copia else None
    if guardada and not forzar and hoy - guardada.consultada < VIGENCIA:
        return guardada
    try:
        with _DESCARGA:
            serie = banrep.desde_suameca(banrep.descargar(id_serie), clave, nombre, hoy)
    except (requests.RequestException, ValueError, KeyError) as e:
        if guardada is None:
            raise ErrorSerie(
                f"No se pudo descargar la serie {clave} del Banco de la República ({e}) y no "
                "hay copia guardada. Revise la conexión a internet y vuelva a intentar.") from e
        return guardada.model_copy(update={"advertencias": [
            f"No se pudo actualizar la serie {clave}; se usaron los datos consultados el "
            f"{guardada.consultada:%d/%m/%Y}."]})
    # Atómico: quien lee mientras el actualizador escribe nunca ve un JSON a medias.
    # Un temporal por hilo; si Windows niega el reemplazo porque alguien lee la
    # copia en ese instante, se devuelve la serie igual y se guarda en la próxima.
    temporal = archivo.with_name(f"{archivo.name}.{threading.get_ident()}.tmp")
    try:
        directorio.mkdir(parents=True, exist_ok=True)
        temporal.write_text(serie.model_dump_json(indent=1), encoding="utf-8")
        temporal.replace(archivo)
    except OSError:
        temporal.unlink(missing_ok=True)
    return serie


def actualizar(hoy: date | None = None, directorio: Path = DIRECTORIO) -> list[str]:
    """
    Descarga de nuevo todas las series nacionales, una tras otra, aunque la
    copia esté vigente. Devuelve lo que no se pudo actualizar. El IPC de las
    ciudades no entra: es mensual y la vigencia de un día lo renueva al pedirlo.
    """
    problemas = []
    for variable in _catalogo():
        try:
            problemas += obtener(variable, "nacional", hoy or date.today(), directorio,
                                 forzar=True).advertencias
        except ErrorSerie as e:
            problemas.append(str(e))
    return problemas


def serie(variable: str, geografia: str | None = "nacional", desde: date | None = None,
          hoy: date | None = None, directorio: Path = DIRECTORIO) -> Serie:
    """
    Serie de la geografía pedida. Si no existe, si no se sabe la ciudad o si la
    serie de la ciudad empieza después de `desde`, la nacional con un supuesto.
    """
    hoy = hoy or date.today()
    sigla = _catalogo()[variable]["nombre"]
    if geografia is not None and sin_tildes(geografia) == "nacional":
        return obtener(variable, "nacional", hoy, directorio)

    encontrada = _buscar(variable, geografia) if geografia else None
    if geografia is None:
        motivo = "no se conoce la ciudad de la empresa"
    elif encontrada is None:
        motivo = f"no hay {sigla} de {geografia}"
    else:
        local = obtener(variable, geografia, hoy, directorio)
        inicio = local.observaciones[0][0]
        if desde is None or (inicio.year, inicio.month) <= (desde.year, desde.month):
            return local
        motivo = f"el {sigla} de {encontrada[0]} empieza en {MESES[inicio.month - 1]} de {inicio.year}"

    nacional = obtener(variable, "nacional", hoy, directorio)
    return nacional.model_copy(update={
        "supuestos": [f"Se usó el {sigla} nacional porque {motivo}."]})


def verificar(banrep_: Serie, dane_: Serie, meses: int = 24) -> list[str]:
    """Diferencias entre las dos fuentes en los últimos meses del DANE (a 2 decimales)."""
    por_mes = {(f.year, f.month): v for f, v in banrep_.observaciones}
    diferencias = []
    for f, v in dane_.observaciones[-meses:]:
        b = por_mes.get((f.year, f.month))
        if b is None or round(b, 2) != round(v, 2):
            diferencias.append(f"{f:%Y-%m}: BanRep {b}, DANE {v}")
    return diferencias


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Refresca el IPC nacional (y el de las ciudades dadas) y lo verifica "
                    "contra el anexo del DANE.")
    parser.add_argument("ciudades", nargs="*", help="p. ej. Pasto Bogotá")
    parser.add_argument("--tasas", action="store_true",
                        help="refresca solo las tasas (política monetaria e IBR)")
    args = parser.parse_args(argv)
    hoy = date.today()
    if args.tasas:
        for variable in TASAS:
            s = obtener(variable, "nacional", hoy, forzar=True)
            fecha, valor = s.observaciones[-1]
            print(f"{s.clave}: {len(s.observaciones)} datos, último {fecha:%d/%m/%Y} = {valor}")
        return 0
    for geografia in ["nacional", *args.ciudades]:
        if _buscar("ipc", geografia) is None:
            print(f"No hay IPC de {geografia} en config/series.yaml.")
            return 1
        s = obtener("ipc", geografia, hoy, forzar=True)
        fecha, valor = s.observaciones[-1]
        print(f"{s.clave}: {len(s.observaciones)} meses, último {fecha:%m/%Y} = {valor}")
    diferencias = verificar(obtener("ipc", "nacional", hoy),
                            dane.desde_anexo(dane.descargar_anexo(hoy), hoy))
    if diferencias:
        print("El IPC del BanRep NO coincide con el del DANE:", *diferencias, sep="\n  ")
        return 1
    print("IPC nacional: BanRep y DANE coinciden en los últimos 24 meses.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
