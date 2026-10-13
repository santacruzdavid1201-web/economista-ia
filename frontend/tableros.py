"""
Tableros de los módulos: todo se calcula con Python, sin el modelo, así que cargan al
instante y no pueden mostrar cifras inventadas. Las gráficas son HTML y CSS: aquí se
calculan las posiciones en porcentaje y la plantilla solo las dibuja.
"""
from __future__ import annotations

from app.orchestrator.tools_registry import ContextoEmpresa
from data_sources.externos.referencia import homologar_empresa
from modules.balance.altman import ZONA_RIESGO, ZONA_SEGURA, altman, calificacion_equivalente, zona
from modules.balance.benchmark import DIRECCION, comparar
from modules.balance.dupont import variacion
from modules.balance.razones import actividad, endeudamiento, liquidez, rentabilidad
from modules.base import ResultadoModulo, formatear

TEMAS = (("Liquidez", liquidez), ("Endeudamiento", endeudamiento),
         ("Rentabilidad", rentabilidad), ("Actividad", actividad), ("Riesgo financiero", altman))
TARJETAS = (("razon_corriente", "Liquidez"), ("nivel_endeudamiento", "Endeudamiento"),
            ("roe", "Rentabilidad del patrimonio"), ("em_score", "Riesgo financiero"))
PALANCAS = (("participacion_margen_neto", "Margen neto"),
            ("participacion_rotacion_activos", "Rotación de activos"),
            ("participacion_multiplicador_capital", "Apalancamiento"))


def _unidad(clave: str, unidad: str) -> str:
    """El Z'' es un puntaje: se muestra sin unidad ("6,88", no "6,88 veces")."""
    return "otro" if clave == "em_score" else unidad


def _valores(resultados: list[ResultadoModulo]) -> dict:
    return {i.clave: i for r in resultados for i in r.indicadores}


def _cambio(actual: float, anterior: float, unidad: str) -> str:
    """Diferencia en la unidad del indicador: puntos porcentuales para las proporciones."""
    d = actual - anterior
    texto = (f"{d * 100:+.1f} puntos" if unidad == "proporcion" else
             f"{d:+.0f} días" if unidad == "dias" else f"{d:+.2f}")
    return texto.replace(".", ",").replace("-", "−")


def _posicion(pct: float, direccion: str) -> str:
    if direccion == "mayor":
        return f"Mejor que el {pct:.0f} % de los pares"
    if direccion == "menor":
        return f"Mejor que el {100 - pct:.0f} % de los pares"
    return f"Percentil {pct:.0f} del sector"


def _escala(*valores: float):
    """Función que lleva un valor a un porcentaje de la barra, con margen a los lados."""
    bajo, alto = min(valores), max(valores)
    margen = (alto - bajo) * 0.15 or abs(alto) * 0.1 or 1
    bajo, alto = bajo - margen, alto + margen
    return lambda v: round((v - bajo) / (alto - bajo) * 100, 1)


def _sector(ctx: ContextoEmpresa, i: int) -> dict | None:
    if ctx.referencia is None:
        return None
    propios = [f(homologar_empresa(ctx.historial), i) for _, f in TEMAS]
    comparacion = comparar(propios, ctx.referencia)
    sector = _valores([comparacion])
    temas = []
    for (tema, _), res in zip(TEMAS, propios):
        filas = []
        for ind in res.indicadores:
            if f"{ind.clave}_percentil" not in sector:
                continue
            p25, med, p75 = (sector[f"{ind.clave}_{q}"].valor for q in ("p25", "mediana", "p75"))
            x = _escala(p25, p75, ind.valor)
            pct = sector[f"{ind.clave}_percentil"].valor
            u = _unidad(ind.clave, ind.unidad)
            filas.append({
                "nombre": ind.nombre, "valor": formatear(ind.valor, u),
                "posicion": _posicion(pct, DIRECCION.get(ind.clave, "neutral")),
                "rango": f"{formatear(p25, u)} a {formatear(p75, u)}",
                "mediana": formatear(med, u),
                "banda": (x(p25), x(p75) - x(p25)), "x_mediana": x(med), "x_empresa": x(ind.valor),
            })
        if filas:
            temas.append({"tema": tema, "filas": filas})
    return {"universo": ctx.referencia.universo, "anio": ctx.referencia.anio, "temas": temas,
            "avisos": comparacion.advertencias,
            "percentiles": {c[: -len("_percentil")]: s.valor for c, s in sector.items()
                            if c.endswith("_percentil")}}


def _tarjetas(actual: dict, anterior: dict | None, anio_anterior: int | None,
              sector: dict | None) -> list[dict]:
    tarjetas = []
    for clave, titulo in TARJETAS:
        ind = actual.get(clave)
        if ind is None or ind.valor is None:
            continue
        previo = anterior.get(clave) if anterior else None
        pct = sector["percentiles"].get(clave) if sector else None
        tarjetas.append({
            "titulo": titulo, "nombre": ind.nombre,
            "valor": formatear(ind.valor, _unidad(clave, ind.unidad)),
            "formula": ind.formula,
            "cambio": (f"{_cambio(ind.valor, previo.valor, ind.unidad)} frente a {anio_anterior}"
                       if previo is not None and previo.valor is not None else None),
            "sube": previo is not None and previo.valor is not None and ind.valor > previo.valor,
            "sector": _posicion(pct, DIRECCION.get(clave, "neutral")) if pct is not None else None,
            "zona": f"Zona {zona(ind.valor)} · equivale a {calificacion_equivalente(ind.valor)}"
                    if clave == "em_score" else None,
        })
    return tarjetas


def _altman(z: float) -> dict:
    x = _escala(min(z, 2.0), max(z, 8.5))
    return {"valor": formatear(z, "otro"), "zona": zona(z), "x": x(z),
            "riesgo": x(ZONA_RIESGO), "gris": x(ZONA_SEGURA) - x(ZONA_RIESGO),
            "limites": (formatear(ZONA_RIESGO, "otro"), formatear(ZONA_SEGURA, "otro"))}


def _dupont(ctx: ContextoEmpresa, i: int) -> dict | None:
    if i < 1:
        return None
    res = variacion(ctx.historial, i)
    v = _valores([res])
    partes = [(nombre, v[c].valor) for c, nombre in PALANCAS if c in v]
    if not partes or any(p is None for _, p in partes):
        return {"hallazgos": res.hallazgos, "advertencias": res.advertencias, "palancas": []}
    mayor = max(abs(p) for _, p in partes) or 1
    return {
        "desde": formatear(v["roe_anterior"].valor, "proporcion"),
        "hasta": formatear(v["roe_actual"].valor, "proporcion"),
        "hallazgos": res.hallazgos[:1], "advertencias": res.advertencias,
        "palancas": [{"nombre": n, "texto": formatear(p, "proporcion"), "negativa": p < 0,
                      "ancho": round(abs(p) / mayor * 50, 1)} for n, p in partes],
    }


def _por_anio(ctx: ContextoEmpresa) -> dict:
    h = ctx.historial
    periodos = range(len(h.periodos))
    temas = []
    for tema, f in TEMAS:
        resultados = [f(h, j) for j in periodos]
        por_periodo = [_valores([r]) for r in resultados]
        filas = [{"nombre": ind.nombre, "formula": ind.formula,
                  "valores": [formatear(p[ind.clave].valor, ind.unidad)
                              if ind.clave in p and p[ind.clave].valor is not None else "—"
                              for p in por_periodo]}
                 for ind in resultados[-1].indicadores]
        temas.append({"tema": tema, "filas": filas})
    return {"anios": [p.fecha_corte.year for p in h.periodos], "temas": temas}


def balance(ctx: ContextoEmpresa) -> dict:
    """Tablero del balance financiero con el último periodo de la empresa."""
    h = ctx.historial
    i = len(h.periodos) - 1
    actual = _valores([f(h, i) for _, f in TEMAS])
    anterior = _valores([f(h, i - 1) for _, f in TEMAS]) if i else None
    sector = _sector(ctx, i)
    z = actual.get("em_score")
    return {
        "corte": h.ultimo.fecha_corte,
        "tarjetas": _tarjetas(actual, anterior, h.periodos[i - 1].fecha_corte.year if i else None,
                              sector),
        "sector": sector,
        "altman": _altman(z.valor) if z is not None and z.valor is not None else None,
        "dupont": _dupont(ctx, i),
        "por_anio": _por_anio(ctx),
    }
