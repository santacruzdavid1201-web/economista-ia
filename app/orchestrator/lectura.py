"""
Lectura de la pregunta: lo que el 7B confunde lo lee Python.

El modelo solo da los números que están en la pregunta (monto, tasa, plazo).
El tipo de la tasa, la unidad del plazo, la periodicidad de las cuotas y el
sistema de amortización salen del texto: con el 7B, las distinciones de sentido
van en Python (24 % NMV es 26,82 % EA, no 24 %).
"""
from __future__ import annotations

import re

from data_sources.externos.series.catalogo import sin_tildes

# Del más específico al más general; texto sin tildes y en minúsculas
TIPOS = [
    ("NMV", r"n\.?\s?m\.?\s?v\b|nominal (?:mes|mensual) vencid[oa]"),
    ("NTV", r"n\.?\s?t\.?\s?v\b|nominal trimestr(?:e|al) vencid[oa]"),
    ("NSV", r"n\.?\s?s\.?\s?v\b|nominal semestr(?:e|al) vencid[oa]"),
    ("NMA", r"n\.?\s?m\.?\s?a\b|nominal (?:mes|mensual) anticipad[oa]"),
    ("NTA", r"n\.?\s?t\.?\s?a\b|nominal trimestr(?:e|al) anticipad[oa]"),
    ("EA", r"e\.?\s?a\b|efectiv[oa] anual|anual efectiv[oa]"),
    ("MA", r"m\.?\s?a\b|(?:mes|mensual) anticipad[oa]"),
    ("TA", r"t\.?\s?a\b|trimestr(?:e|al) anticipad[oa]"),
    ("MV", r"m\.?\s?v\b|mes vencido|(?:efectiv[oa] )?mensual"),
    ("TV", r"t\.?\s?v\b|trimestre vencido|(?:efectiv[oa] )?trimestral"),
    ("SV", r"s\.?\s?v\b|semestre vencido|(?:efectiv[oa] )?semestral"),
]
ANUAL = r"anual|al ano|por ano"
# "18 % de interés EA" / "una tasa mensual del 2 %"
ANTES_DEL_TIPO = r"^\s*(?:de interes\s+|de\s+)?"
DESPUES_DEL_TIPO = r"\s+(?:es\s+)?(?:del?\s+)?$"
NUMERO = r"\d+(?:[.,]\d+)*"
MULTIPLICADORES = {"mil millones": 1e9, "millones": 1e6, "millon": 1e6, "mm": 1e6, "mil": 1e3}


def _numero(texto: str) -> float:
    """Número colombiano: punto de miles y coma decimal ("1.500,5"; "2,5"; "2.5" es 2,5)."""
    if "," in texto:
        return float(texto.replace(".", "").replace(",", "."))
    grupos = texto.split(".")
    if len(grupos) > 1 and all(len(g) == 3 for g in grupos[1:]):
        return float("".join(grupos))
    return float(texto)


def _pegado(patron: str, antes: str, despues: str) -> bool:
    """El patrón va justo después del número o justo antes ("tasa mensual del 2 %")."""
    return bool(re.match(ANTES_DEL_TIPO + f"(?:{patron})", despues)
                or re.search(f"(?:{patron})" + DESPUES_DEL_TIPO, antes))


def tipo_de_tasa(pregunta: str, tasa: float) -> tuple[str | None, bool]:
    """
    (tipo, asumido) de la tasa que vale `tasa` % en la pregunta. "Anual" sin más
    es efectiva anual, como deben informarla los bancos en Colombia: asumido.
    Sin tipo reconocible, (None, False): no se adivina.
    """
    texto = sin_tildes(pregunta)
    for m in re.finditer(rf"({NUMERO})\s*%", texto):
        if _numero(m.group(1)) != tasa:
            continue
        antes, despues = texto[:m.start()], texto[m.end():]
        for tipo, patron in TIPOS:
            if _pegado(patron, antes, despues):
                return tipo, False
        return ("EA", True) if _pegado(ANUAL, antes, despues) else (None, False)
    return None, False


def _montos(pregunta: str) -> list[tuple[float, float]]:
    """(número como está escrito, pesos) de cada monto; las tasas y los plazos no cuentan."""
    texto = sin_tildes(pregunta)
    palabras = "|".join(MULTIPLICADORES)
    pares = []
    for m in re.finditer(rf"({NUMERO})(?:\s*({palabras})\b)?", texto):
        if re.match(r"\s*(?:%|anos?\b|mes(?:es)?\b|cuotas?\b)", texto[m.end():]):
            continue
        escrito = _numero(m.group(1))
        pares.append((escrito, escrito * MULTIPLICADORES.get(m.group(2) or "", 1)))
    if re.search(r"(?<!\d )\bmil millones\b", texto):
        pares.append((1e9, 1e9))
    return pares


def montos(pregunta: str) -> list[float]:
    """Montos de la pregunta en pesos, con sus palabras ("200 millones", "$200.000.000")."""
    return [pesos for _, pesos in _montos(pregunta)]


def monto_en_pesos(pregunta: str, valor: object) -> float | None:
    """
    El monto en pesos que el modelo quiso decir: por "200 millones" da 200 o
    200000000, según el día. None si no es un monto de la pregunta (inventado).
    """
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None
    return next((pesos for escrito, pesos in _montos(pregunta)
                 if abs(v - pesos) < 0.5 or v == escrito), None)


def unidad_plazo(pregunta: str, plazo: float) -> str | None:
    """'años', 'meses' o 'cuotas' según lo que sigue al número del plazo."""
    for n, unidad in re.findall(rf"({NUMERO})\s*(anos?|mes(?:es)?|cuotas?)\b", sin_tildes(pregunta)):
        if _numero(n) == plazo:
            return "años" if unidad.startswith("ano") else "meses" if unidad.startswith("mes") \
                else "cuotas"
    return None


def periodicidad(pregunta: str) -> str:
    """Cada cuánto se paga: mensual salvo que la pregunta diga otra cosa de las cuotas."""
    texto = sin_tildes(pregunta)
    for clave, cada in (("trimestral", "trimestre"), ("semestral", "semestre"), ("anual", "ano")):
        if re.search(rf"(?:cuotas?|pagos?|abonos?)\s+{clave}(?:es)?\b|cada {cada}\b", texto):
            return clave
    return "mensual"


def sistema(pregunta: str) -> str:
    """Abono constante a capital si la pregunta lo dice; si no, cuota fija."""
    texto = sin_tildes(pregunta)
    constante = r"abono (?:constante|fijo|igual)|capital (?:constante|fijo)|cuotas? decrecientes?"
    return "abono_constante" if re.search(constante, texto) else "cuota_fija"
