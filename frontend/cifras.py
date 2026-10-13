"""
Cifras rastreables: cada número de la respuesta que salió de un cálculo se marca
con su origen (el indicador y su fórmula, o el hallazgo que lo contiene), para que
el gerente vea de dónde sale al pasar el cursor o al enfocarlo con el teclado.

El texto del modelo se escapa antes de marcarlo: nunca se inserta HTML suyo.
"""
from __future__ import annotations

import html
import re

from app.orchestrator.verificador import LIBRES, NUMERO
from modules.base import ResultadoModulo, formatear

# Cifra con su signo, el símbolo de pesos y la unidad, si los tiene
CIFRA = re.compile(r"(?P<signo>[-−])?(?P<peso>\$\s?)?(?P<num>\d+(?:[.,]\d+)*)"
                   r"(?P<unidad>\s?(?:%|veces|puntos|días))?")
ANIO = re.compile(r"(19|20)\d{2}")


def origenes(resultados: list[ResultadoModulo]) -> dict[str, tuple[str, bool]]:
    """Número tal como se escribe ("6.800.000", "2,04") → (origen, es negativo)."""
    mapa: dict[str, tuple[str, bool]] = {}
    for r in resultados:
        for h in r.hallazgos:
            for n in NUMERO.findall(h):
                mapa.setdefault(n, (f"Del análisis: {h}", False))
    # El indicador es más preciso que la frase: reemplaza al hallazgo
    for r in resultados:
        for i in r.indicadores:
            if i.valor is not None:
                for n in NUMERO.findall(formatear(i.valor, i.unidad)):
                    mapa[n] = (f"{i.nombre}. Fórmula: {i.formula}", i.valor < 0)
    return mapa


def _es_cifra(m: re.Match) -> bool:
    """Los años y los enteros pequeños sin % ni $ son redacción, no cifras calculadas."""
    n, con_simbolo = m["num"], m["peso"] or (m["unidad"] or "").strip() == "%"
    return con_simbolo or not (n in LIBRES or ANIO.fullmatch(n))


def marcar(texto: str, resultados: list[ResultadoModulo]) -> str:
    """Markdown con cada cifra calculada envuelta en un <span> con su origen."""
    mapa = origenes(resultados)

    def sustituir(m: re.Match) -> str:
        if m["num"] not in mapa or not _es_cifra(m):
            return m.group(0)
        origen, negativo = mapa[m["num"]]
        clase = "cifra negativa" if negativo or m["signo"] else "cifra"
        atributo = html.escape(origen, quote=True).replace("$", "&#36;")
        return f'<span class="{clase}" tabindex="0" data-origen="{atributo}">{m.group(0)}</span>'

    marcado = CIFRA.sub(sustituir, html.escape(texto, quote=False))
    # Streamlit lee "$...$" como LaTeX: el $ visible se escapa (el del atributo ya es entidad)
    return marcado.replace("$", "\\$")


def libro(filas: list[tuple[str, str, str | None]],
          encabezado: tuple[str, ...] | None = None) -> str:
    """
    Tabla en renglones de libro: concepto a la izquierda, cifra a la derecha en tinta
    azul (roja si es negativa) y, si la hay, la fórmula. Todo se escapa.
    """
    def e(t: str) -> str:
        return html.escape(t, quote=True).replace("$", "&#36;")

    con_formula = any(f is not None for _, _, f in filas)
    renglones = []
    if encabezado:
        renglones.append("<tr>" + "".join(f"<th>{e(c)}</th>" for c in encabezado) + "</tr>")
    for concepto, valor, formula in filas:
        clase = "valor negativa" if valor.startswith(("-", "−")) else "valor"
        celdas = f'<td>{e(concepto)}</td><td class="{clase}">{e(valor)}</td>'
        if con_formula:
            celdas += f'<td class="formula">{e(formula or "")}</td>'
        renglones.append(f"<tr>{celdas}</tr>")
    return f'<table class="libro">{"".join(renglones)}</table>'
