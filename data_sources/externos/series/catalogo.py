"""
Catálogo de series externas: `serie("ipc", "Pasto")` y nada más.

El análisis pide variable y geografía; el catálogo resuelve el id
(`config/series.yaml`), usa la copia guardada si tiene menos de 7 días,
descarga si no, y cae a la serie nacional con un supuesto cuando la ciudad no
tiene serie o la suya no cubre las fechas pedidas.

Las copias se guardan en `data/series/` y se versionan: la demo y los tests
de punta a punta no dependen de la red.

    python -m data_sources.externos.series.catalogo Pasto   # refresca y verifica
"""
from __future__ import annotations

import argparse
import sys
import unicodedata
from datetime import date, timedelta
from pathlib import Path

import requests
import yaml

from data_sources.externos.series import banrep, dane
from data_sources.externos.series.modelo import Serie

RAIZ = Path(__file__).resolve().parents[3]
CATALOGO = RAIZ / "config" / "series.yaml"
DIRECTORIO = RAIZ / "data" / "series"
VIGENCIA = timedelta(days=7)
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
    """Copia guardada si está vigente; si no, descarga. Sin red, la copia vieja con advertencia."""
    nombre, id_serie = _buscar(variable, geografia)
    clave = f"{variable}_{sin_tildes(nombre).replace(' ', '_')}"
    archivo = directorio / f"{clave}.json"
    guardada = Serie.model_validate_json(archivo.read_text(encoding="utf-8")) \
        if archivo.exists() else None
    if guardada and not forzar and hoy - guardada.consultada < VIGENCIA:
        return guardada
    try:
        serie = banrep.desde_suameca(banrep.descargar(id_serie), clave, nombre, hoy)
    except (requests.RequestException, ValueError, KeyError) as e:
        if guardada is None:
            raise ErrorSerie(
                f"No se pudo descargar la serie {clave} del Banco de la República ({e}) y no "
                "hay copia guardada. Revise la conexión a internet y vuelva a intentar.") from e
        return guardada.model_copy(update={"advertencias": [
            f"No se pudo actualizar la serie {clave}; se usaron los datos consultados el "
            f"{guardada.consultada:%d/%m/%Y}."]})
    directorio.mkdir(parents=True, exist_ok=True)
    archivo.write_text(serie.model_dump_json(indent=1), encoding="utf-8")
    return serie


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
    args = parser.parse_args(argv)
    hoy = date.today()
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
