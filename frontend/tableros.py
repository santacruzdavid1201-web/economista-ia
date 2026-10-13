"""
Tableros de los módulos: todo se calcula con Python, sin el modelo, así que cargan al
instante y no pueden mostrar cifras inventadas. Las gráficas son HTML y CSS: aquí se
calculan las posiciones en porcentaje y la plantilla solo las dibuja.
"""
from __future__ import annotations

from datetime import date

from app.orchestrator.tools_registry import (
    PANORAMA,
    POR_NOMBRE,
    ContextoEmpresa,
    ErrorHerramienta,
)
from data_sources.externos.referencia import homologar_empresa
from data_sources.externos.series import catalogo
from data_sources.externos.series.modelo import Serie
from modules.balance.altman import ZONA_RIESGO, ZONA_SEGURA, altman, calificacion_equivalente, zona
from modules.balance.benchmark import DIRECCION, comparar
from modules.balance.dupont import variacion
from modules.balance.razones import actividad, endeudamiento, liquidez, rentabilidad
from modules.base import ResultadoModulo, formatear
from modules.macro.panorama import inflacion_anual, panorama_macro

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


# --------------------------------------------------------------------------- #
# Tablero macro
# --------------------------------------------------------------------------- #
MESES_LINEA = 36            # meses de historia en las líneas de tendencia
ESCENARIOS = (("menos_3", "3 puntos menos"), ("menos_1", "1 punto menos"), ("", "Sin cambio de tasa"),
              ("mas_1", "1 punto más"), ("mas_3", "3 puntos más"), ("historico", "Alza de 2022"))


def _linea(puntos: list[tuple[date, float]], ancho: int = 200, alto: int = 44) -> dict | None:
    """Puntos de una línea SVG (y crece hacia abajo en SVG: se invierte)."""
    if len(puntos) < 2:
        return None
    valores = [v for _, v in puntos]
    bajo, alto_v = min(valores), max(valores)
    rango = (alto_v - bajo) or 1
    xy = [(round(k / (len(valores) - 1) * ancho, 1), round(alto - 4 - (v - bajo) / rango * (alto - 8), 1))
          for k, v in enumerate(valores)]
    return {"puntos": " ".join(f"{x},{y}" for x, y in xy), "ultimo": xy[-1], "ancho": ancho,
            "alto": alto, "desde": puntos[0][0], "hasta": puntos[-1][0]}


def _mensual_reciente(serie: Serie, meses: int = MESES_LINEA) -> list[tuple[date, float]]:
    return serie.fin_de_mes()[-meses:]


def _economia(ctx: ContextoEmpresa | None) -> dict:
    obtener = ctx.serie if ctx else catalogo.serie
    s = {v: obtener(v, "nacional", None) for v in PANORAMA}
    r = panorama_macro(*s.values())
    v = _valores([r])

    def tarjeta(clave, titulo, unidad, comparacion, linea):
        ind = v[clave]
        return {"titulo": titulo, "nombre": ind.nombre, "formula": ind.formula,
                "valor": formatear(ind.valor, unidad) if ind.valor is not None else "—",
                "comparacion": comparacion, "linea": linea}

    def previo(clave, texto):
        return f"{texto}: {formatear(v[clave].valor, v[clave].unidad)}" if clave in v and \
            v[clave].valor is not None else None

    ipc = s["ipc"].observaciones
    inflacion = [(f, x) for f, _ in ipc[-MESES_LINEA:] if (x := inflacion_anual(s["ipc"], f)) is not None]
    return {
        "tarjetas": [
            tarjeta("inflacion_anual", "Inflación anual", "tasa",
                    previo("inflacion_anual_previa", "Un año antes"), _linea(inflacion)),
            tarjeta("tasa_politica", "Tasa del Banco de la República", "tasa",
                    previo("tasa_politica_previa", "Un año antes") + " · IBR a 3 meses: "
                    + formatear(v["ibr_3m"].valor, "tasa") if "tasa_politica_previa" in v else None,
                    _linea(_mensual_reciente(s["tasa_politica"]))),
            tarjeta("trm", "Dólar (TRM)", "pesos",
                    previo("variacion_anual_trm", "Variación en un año"),
                    _linea(_mensual_reciente(s["trm"]))),
            tarjeta("crecimiento_pib", "Crecimiento del PIB", "tasa",
                    f"Trimestre anterior: {formatear(s['pib'].observaciones[-2][1] / 100, 'tasa')}",
                    _linea(s["pib"].observaciones[-12:])),
            tarjeta("desempleo", "Desempleo", "tasa",
                    previo("desempleo_previo", "Mismo mes del año anterior"),
                    _linea(_mensual_reciente(s["desempleo"]))),
        ],
        "hallazgos": r.hallazgos, "fuentes": r.fuentes, "advertencias": r.advertencias,
    }


def _empresa_macro(ctx: ContextoEmpresa) -> dict:
    """Crecimiento real y sensibilidad a tasas de la empresa, con las mismas herramientas del chat."""
    i = len(ctx.historial.periodos) - 1
    salida: dict = {}
    try:
        cr = POR_NOMBRE["analizar_crecimiento_real"].ejecutar(ctx, i, {})[0]
        v = _valores([cr])
        salida["crecimiento"] = {
            "cifras": [(v[c].nombre, formatear(v[c].valor, v[c].unidad)) for c in
                       ("crecimiento_nominal_ingresos", "inflacion_promedio", "crecimiento_real_ingresos")
                       if c in v and v[c].valor is not None],
            # Sin los supuestos de la carga del balance (deudores, reclasificaciones): no son de aquí
            "hallazgos": cr.hallazgos,
            "avisos": [a for a in cr.advertencias + cr.supuestos
                       if a not in {x for p in ctx.historial.periodos for x in p.supuestos_carga}]}
    except ErrorHerramienta as e:
        salida["crecimiento"] = {"cifras": [], "hallazgos": [], "avisos": [str(e)]}
    try:
        st = POR_NOMBRE["analizar_sensibilidad_tasas"].ejecutar(ctx, i, {})[0]
        v = _valores([st])

        def fila(sufijo, etiqueta):
            g = v.get(f"gastos_financieros_{sufijo}" if sufijo else "gastos_financieros_anuales")
            c = v.get(f"cobertura_{sufijo}" if sufijo else "cobertura_intereses")
            if g is None or g.valor is None:
                return None
            return {"escenario": etiqueta, "hoy": not sufijo, "gastos": formatear(g.valor, "pesos"),
                    "cobertura": formatear(c.valor, "veces") if c and c.valor is not None else "—"}

        salida["tasas"] = {"filas": [f for s, e in ESCENARIOS if (f := fila(s, e))],
                           "hallazgos": st.hallazgos[:1], "avisos": st.supuestos}
    except ErrorHerramienta as e:
        salida["tasas"] = {"filas": [], "hallazgos": [], "avisos": [str(e)]}
    return salida


def macro(ctx: ContextoEmpresa | None) -> dict:
    """Tablero del entorno macro: la economía siempre; la empresa, si está cargada."""
    try:
        economia = _economia(ctx)
    except catalogo.ErrorSerie as e:
        economia = {"error": str(e)}
    return {"economia": economia, "empresa": _empresa_macro(ctx) if ctx else None}
