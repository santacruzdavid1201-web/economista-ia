"""
Pronóstico de inflación del Banco de la República: el Excel de "principales
variables del pronóstico macroeconómico" que acompaña cada Informe de Política
Monetaria (enero, abril, julio y octubre). Es la proyección oficial de quien
fija la tasa, no un pronóstico propio; el flujo de proyectos la empalma con la
meta de 3 % después de su horizonte (SPEC-flujo-proyecto.md).

Se carga a mano cada trimestre: el repositorio del BanRep tiene un sistema
anti-bots que bloquea las descargas automáticas (15/10/2026), y no se le da la
vuelta. Se descarga el Excel en el navegador desde la página del informe y:

    python -m data_sources.externos.pronostico_banrep IPM-octubre-2026-var-pron-macro.xlsx

La copia queda versionada en `data/series/pronostico_inflacion.json`.
"""
from __future__ import annotations

import argparse
import io
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import openpyxl
from pydantic import BaseModel, Field

from data_sources.externos.series import catalogo
from data_sources.externos.series.catalogo import sin_tildes

ARCHIVO = "pronostico_inflacion.json"
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
# El informe sale cada 3 meses y se publica unas semanas después de su mes
VIGENCIA = timedelta(days=120)
PAGINA = "https://www.banrep.gov.co/es/informe-de-politica-monetaria"


class ErrorPronostico(ValueError):
    """El pronóstico no se pudo leer o no está cargado; el mensaje dice qué hacer."""


class Pronostico(BaseModel):
    informe: str                       # "Informe de Política Monetaria de julio de 2026"
    fecha_informe: date                # primer día del mes del informe
    fuente: str
    consultada: date                   # día en que se cargó el Excel
    inflacion: dict[int, float]        # año → inflación a fin de año (fracción); historia y pronóstico
    advertencias: list[str] = Field(default_factory=list, exclude=True)


def desde_excel(contenido: bytes, mes: int, anio: int, consultada: date) -> Pronostico:
    """Hoja anual → fila de años y fila "IPC total". Por etiquetas, no por posición."""
    libro = openpyxl.load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    hoja = next((h for h in libro.worksheets if "anual" in sin_tildes(h.title)), None)
    filas = list(hoja.iter_rows(values_only=True)) if hoja else []
    anios = next((f for f in filas
                  if sum(isinstance(c, int) and 1990 < c < 2100 for c in f) >= 5), None)
    ipc = next((f for f in filas
                if any(isinstance(c, str) and sin_tildes(c).startswith("ipc total") for c in f)), None)
    if anios is None or ipc is None:
        raise ErrorPronostico("El formato del Excel de pronósticos del BanRep cambió: no se "
                              "encontró la fila de años o la del IPC total en la hoja anual.")
    informe = f"Informe de Política Monetaria de {MESES[mes - 1]} de {anio}"
    return Pronostico(
        informe=informe, fecha_informe=date(anio, mes, 1), consultada=consultada,
        fuente=(f"Banco de la República, {informe}: principales variables del pronóstico "
                "macroeconómico (IPC total, variación anual a fin de año)"),
        inflacion={a: v / 100 for a, v in zip(anios, ipc)
                   if isinstance(a, int) and isinstance(v, (int, float))})


def informe_del_nombre(nombre: str) -> tuple[int, int] | None:
    """(mes, año) del nombre con que el BanRep publica el archivo: IPM-julio-2026-…"""
    m = re.search(rf"({'|'.join(MESES)})-(\d{{4}})", sin_tildes(nombre))
    return (MESES.index(m.group(1)) + 1, int(m.group(2))) if m else None


def cargar(ruta: Path, mes: int, anio: int, hoy: date | None = None) -> Pronostico:
    """Lee el Excel descargado y guarda la copia versionada."""
    p = desde_excel(Path(ruta).read_bytes(), mes, anio, hoy or date.today())
    catalogo.guardar(catalogo.RESPALDO / ARCHIVO, p.model_dump_json(indent=1))
    return p


def pronostico(hoy: date | None = None) -> Pronostico:
    """La copia cargada; con aviso si el informe tiene más de 4 meses."""
    archivo = catalogo.RESPALDO / ARCHIVO
    if not archivo.exists():
        raise ErrorPronostico(
            "No hay pronóstico de inflación del BanRep cargado. Descargue el Excel de "
            f"principales variables del pronóstico en {PAGINA} y cárguelo con: python -m "
            "data_sources.externos.pronostico_banrep <archivo.xlsx>")
    p = Pronostico.model_validate_json(archivo.read_text(encoding="utf-8"))
    if (hoy or date.today()) - p.fecha_informe > VIGENCIA:
        p.advertencias.append(f"El pronóstico de inflación es del {p.informe}; puede haber uno "
                              "más reciente del Banco de la República.")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Carga el Excel de variables del pronóstico "
                                                 "del Informe de Política Monetaria.")
    parser.add_argument("archivo", help="p. ej. IPM-octubre-2026-var-pron-macro.xlsx")
    parser.add_argument("--mes", type=int, help="mes del informe, si el nombre no lo dice")
    parser.add_argument("--anio", type=int, help="año del informe, si el nombre no lo dice")
    args = parser.parse_args(argv)
    mes, anio = (args.mes, args.anio) if args.mes and args.anio else \
        informe_del_nombre(Path(args.archivo).name) or (None, None)
    if mes is None:
        print("No se reconoce el informe en el nombre del archivo: use --mes y --anio.")
        return 1
    try:
        p = cargar(Path(args.archivo), mes, anio)
    except (OSError, ErrorPronostico) as e:
        print(f"No se pudo cargar: {e}")
        return 1
    futuros = {a: f"{v * 100:.1f} %".replace(".", ",") for a, v in p.inflacion.items()
               if a >= p.fecha_informe.year}
    print(f"{p.informe}: {futuros}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
