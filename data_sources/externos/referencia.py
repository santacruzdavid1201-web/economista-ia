"""
Construcción de la referencia sectorial a partir de Supersociedades.

Calcula los indicadores de cada empresa par con las MISMAS funciones de
modules/balance/ que se usan para la empresa analizada, y los agrupa en una
`ReferenciaSectorial` que consume `modules.balance.benchmark.comparar`.

Decisiones (exploracion/hallazgos_supersociedades.md):
- Un par sin costo de ventas reportado no entra a margen bruto ni a los
  indicadores que dependen del costo (inventario, proveedores, ciclo): su
  margen bruto de 100 % es un artefacto contable, no desempeño.
- La empresa analizada se homologa (`homologar_empresa`) para que su cartera y
  sus proveedores tengan la misma agregación que la taxonomía NIIF.
- La empresa analizada nunca es su propio par.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from data_sources.externos.supersociedades import (
    SUPUESTOS_MAPEO,
    Exclusion,
    construir_historiales,
    descargar_estados,
    descargar_nits_por_ciiu,
)
from modules.balance.altman import altman
from modules.balance.benchmark import DIRECCION, ReferenciaSectorial
from modules.balance.razones import actividad, endeudamiento, liquidez, rentabilidad
from modules.esquema_financiero import HistorialFinanciero

RAIZ = Path(__file__).resolve().parents[2]
SECTORES = RAIZ / "config" / "ciiu_sectores.yaml"
CACHE = RAIZ / "data" / "raw" / "supersociedades"
REFERENCIAS = RAIZ / "data" / "referencias"

ANALISIS = (liquidez, endeudamiento, rentabilidad, actividad, altman)
DEPENDEN_DEL_COSTO = ("margen_bruto", "dias_inventario", "dias_proveedores",
                      "ciclo_conversion_efectivo")

SUPUESTO_HOMOLOGACION = (
    "Para compararla con Supersociedades, la cartera incluye otros deudores de "
    "corto plazo y los proveedores incluyen otras cuentas por pagar, como en la "
    "taxonomía NIIF."
)


def _indice(historial: HistorialFinanciero, anio: int) -> int | None:
    return next((k for k, p in enumerate(historial.periodos) if p.fecha_corte.year == anio), None)


def _sin_costo(historial: HistorialFinanciero, i: int) -> bool:
    return "costo_ventas" not in historial.periodos[i].resultados.model_fields_set


def indicadores_par(historial: HistorialFinanciero, anio: int) -> dict[str, float | None] | None:
    """Indicadores comparables de un par para el año dado; None si no reportó ese año."""
    i = _indice(historial, anio)
    if i is None:
        return None
    valores = {ind.clave: ind.valor
               for analisis in ANALISIS for ind in analisis(historial, i).indicadores
               if ind.clave in DIRECCION}
    if _sin_costo(historial, i):
        valores.update({k: None for k in DEPENDEN_DEL_COSTO})
    return valores


def construir_referencia(historiales: list[HistorialFinanciero], anio: int, universo: str,
                         ciius: list[str], exclusiones: list[Exclusion] | None = None,
                         excluir_nit: str | None = None,
                         no_comparables: dict[str, str] | None = None) -> ReferenciaSectorial:
    no_comparables = no_comparables or {}
    valores: dict[str, list[float | None]] = {clave: [] for clave in DIRECCION
                                              if clave not in no_comparables}
    n = sin_costo = 0
    for h in historiales:
        if h.empresa.empresa_id == excluir_nit:
            continue
        ind = indicadores_par(h, anio)
        if ind is None:
            continue
        n += 1
        sin_costo += _sin_costo(h, _indice(h, anio))
        for clave in valores:
            valores[clave].append(ind.get(clave))

    excluidas = len({e.nit for e in exclusiones or [] if e.fecha_corte is None
                     or e.fecha_corte.year == anio})
    filtros = [
        *SUPUESTOS_MAPEO,
        f"{n} empresas con estados de {anio}; {excluidas} excluidas por datos "
        "inconsistentes (doble conteo o totales faltantes).",
    ]
    if sin_costo:
        filtros.append(f"{sin_costo} empresas sin costo de ventas reportado no entran a margen "
                       "bruto, días de inventario, días de proveedores ni ciclo de efectivo.")
    if excluir_nit:
        filtros.append("La empresa analizada se excluyó de sus propios pares.")
    return ReferenciaSectorial(universo=universo, anio=anio, ciius=ciius,
                               filtros=filtros, valores=valores, no_comparables=no_comparables)


def homologar_empresa(historial: HistorialFinanciero) -> HistorialFinanciero:
    """
    Copia del historial con la cartera y los proveedores agregados como en la
    taxonomía NIIF de Supersociedades. Úsese solo para compararla con los pares.
    """
    periodos = []
    for p in historial.periodos:
        b = p.balance
        balance = b.model_copy(update={
            "deudores_comerciales": b.deudores_comerciales + b.otros_deudores_cp,
            "otros_deudores_cp": 0,
            "proveedores": b.proveedores + b.otras_cuentas_por_pagar_cp,
            "otras_cuentas_por_pagar_cp": 0,
        })
        periodos.append(p.model_copy(update={
            "balance": balance,
            "supuestos_carga": [*p.supuestos_carga, SUPUESTO_HOMOLOGACION],
        }))
    return historial.model_copy(update={"periodos": periodos})


# --------------------------------------------------------------------------- #
# Pipeline completo con caché
# --------------------------------------------------------------------------- #
def descargar_con_cache(grupo: str, ciius: list[str], anio: int,
                        cache: Path = CACHE) -> dict[str, pd.DataFrame]:
    """Descarga los estados del grupo y año, o los lee de la caché si ya existen."""
    archivos = {k: cache / f"{grupo}_{anio}_{k}.csv" for k in ("caratula", "esf", "eri", "efe")}
    if all(a.exists() for a in archivos.values()):
        return {k: pd.read_csv(a, dtype=str) for k, a in archivos.items()}
    nits = descargar_nits_por_ciiu(ciius, [anio])
    datos = descargar_estados(nits, [anio])
    cache.mkdir(parents=True, exist_ok=True)
    for k, a in archivos.items():
        datos[k].to_csv(a, index=False, encoding="utf-8")
    return datos


def referencia_supersociedades(grupo: str, anio: int, excluir_nit: str | None = None,
                               guardar: bool = True) -> ReferenciaSectorial:
    """Referencia de un grupo de `config/ciiu_sectores.yaml` para un año."""
    sectores = yaml.safe_load(SECTORES.read_text(encoding="utf-8"))
    definicion = sectores[grupo]
    ciius = list(definicion["ciius"])
    datos = descargar_con_cache(grupo, ciius, anio)
    historiales, exclusiones = construir_historiales(
        datos["caratula"], datos["esf"], datos["eri"], datos["efe"])
    # Solo pares cuyo CIIU (según su carátula más reciente) pertenece al grupo
    historiales = [h for h in historiales if h.empresa.ciiu in ciius]
    universo = (f"{definicion['descripcion']}: empresas reportantes a Supersociedades "
                f"(CIIU {', '.join(ciius)})")
    ref = construir_referencia(historiales, anio, universo, ciius, exclusiones, excluir_nit,
                               definicion.get("no_comparables"))
    if guardar and excluir_nit is None:
        REFERENCIAS.mkdir(parents=True, exist_ok=True)
        (REFERENCIAS / f"{grupo}_{anio}.json").write_text(
            ref.model_dump_json(indent=1), encoding="utf-8")
    return ref
