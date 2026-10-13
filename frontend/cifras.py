"""
Presentación de las respuestas en HTML.

- Cifras rastreables: cada número de la respuesta que salió de un cálculo se
  marca con su origen (el indicador y su fórmula, o el hallazgo que lo
  contiene), para que el gerente vea de dónde sale al pasar el cursor o al
  enfocarlo con el teclado.
- Renglones de libro: tablas de concepto, cifra y fórmula.
- Markdown mínimo: párrafos, listas y negritas, lo único que usa el modelo.

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
VINETA = re.compile(r"^\s*[-*•]\s+(.*)$")
NUMERADA = re.compile(r"^\s*\d+[.)]\s+(.*)$")
TITULO = re.compile(r"^\s*#{1,6}\s+(.*)$")
NEGRITA = re.compile(r"\*\*(.+?)\*\*")


# --------------------------------------------------------------------------- #
# Cifras rastreables
# --------------------------------------------------------------------------- #
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
    """Texto escapado con cada cifra calculada envuelta en un <span> con su origen."""
    mapa = origenes(resultados)

    def sustituir(m: re.Match) -> str:
        if m["num"] not in mapa or not _es_cifra(m):
            return m.group(0)
        origen, negativo = mapa[m["num"]]
        clase = "cifra negativa" if negativo or m["signo"] else "cifra"
        atributo = html.escape(origen, quote=True)
        return f'<span class="{clase}" tabindex="0" data-origen="{atributo}">{m.group(0)}</span>'

    return CIFRA.sub(sustituir, html.escape(texto, quote=False))


# --------------------------------------------------------------------------- #
# Markdown mínimo
# --------------------------------------------------------------------------- #
def a_html(texto: str) -> str:
    """
    Párrafos, listas (con viñeta o numeradas), negritas y títulos (como párrafo en
    negrita). Recibe texto YA escapado: solo agrega estas etiquetas.
    """
    partes: list[str] = []
    parrafo: list[str] = []
    lista: tuple[str, list[str]] | None = None

    def cerrar() -> None:
        nonlocal lista
        if parrafo:
            partes.append(f"<p>{'<br>'.join(parrafo)}</p>")
            parrafo.clear()
        if lista:
            etiqueta, items = lista
            partes.append(f"<{etiqueta}>{''.join(f'<li>{i}</li>' for i in items)}</{etiqueta}>")
            lista = None

    for linea in texto.splitlines():
        linea = NEGRITA.sub(r"<strong>\1</strong>", linea.rstrip())
        if not linea.strip():
            cerrar()
        elif m := TITULO.match(linea):
            cerrar()
            partes.append(f"<p><strong>{m[1]}</strong></p>")
        elif (m := VINETA.match(linea)) or (m := NUMERADA.match(linea)):
            etiqueta = "ul" if VINETA.match(linea) else "ol"
            if parrafo or (lista and lista[0] != etiqueta):
                cerrar()
            lista = lista or (etiqueta, [])
            lista[1].append(m[1])
        else:
            if lista:
                cerrar()
            parrafo.append(linea.strip())
    cerrar()
    return "".join(partes)


def respuesta_html(texto: str, resultados: list[ResultadoModulo]) -> str:
    """Respuesta del modelo lista para insertar: escapada, con cifras marcadas y formato."""
    return a_html(marcar(texto, resultados))


# --------------------------------------------------------------------------- #
# Renglones de libro
# --------------------------------------------------------------------------- #
def libro(filas: list[tuple[str, str, str | None]],
          encabezado: tuple[str, ...] | None = None) -> str:
    """
    Tabla en renglones: concepto a la izquierda, cifra a la derecha (en coral si es
    negativa) y, si la hay, la fórmula. Todo se escapa.
    """
    def e(t: str) -> str:
        return html.escape(t, quote=True)

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
