"""
Cargador de la empresa a partir de un balance de prueba en PUC (Decreto 2650).

Entrada típica: el balance de prueba que exporta el software contable (Siigo,
World Office, Alegra, Helisa) en Excel o CSV, con código de cuenta y saldo
final. Debe ser ANTES del cierre: después del cierre las clases 4, 5 y 6
quedan en cero y no hay estado de resultados.

Reglas (detalle en config/mapeo_puc.yaml):
- Solo se suman las cuentas hoja; las filas padre ya contienen a sus hijas.
- Saldos con signo, débito positivo. Se acepta una columna de saldo con signo
  o dos columnas (saldo débito / saldo crédito).
- Un balance de prueba cuadra por construcción (débitos = créditos). Si las
  clases 1 a 7 no suman cero, los signos o las filas están mal y se rechaza.
- Los cortes intermedios se toman como acumulados desde enero: meses = mes
  del corte, y los módulos anualizan.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import IO

import pandas as pd
import yaml
from pydantic import ValidationError

from modules.base import formatear
from modules.esquema_financiero import (
    BalanceGeneral,
    Empresa,
    EstadoFinanciero,
    EstadoResultados,
    HistorialFinanciero,
)

MAPEO = Path(__file__).resolve().parents[2] / "config" / "mapeo_puc.yaml"
TOLERANCIA = 0.001          # 0,1 % de la suma de saldos absolutos
CLASES_CREDITO = {"2", "3", "4"}
CLASES_LEIDAS = set("1234567")

# Nombres de columna que usan los programas contables (en minúsculas, sin tildes)
COLUMNAS_CUENTA = ("cuenta", "codigo", "codigo cuenta", "cod cuenta", "codigo contable")
COLUMNAS_SALDO = ("saldo final", "saldo", "nuevo saldo", "saldo actual")
COLUMNAS_DEBITO = ("saldo debito", "saldo final debito")
COLUMNAS_CREDITO = ("saldo credito", "saldo final credito")


class ErrorCarga(ValueError):
    """El balance de prueba no se puede traducir al esquema con confianza."""


def cargar_mapeo(ruta: Path = MAPEO) -> dict:
    return yaml.safe_load(ruta.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Lectura
# --------------------------------------------------------------------------- #
def _simplificar(nombre: str) -> str:
    tabla = str.maketrans("áéíóúñ", "aeioun")
    return " ".join(re.sub(r"[^a-z ]", " ", str(nombre).lower().translate(tabla)).split())


def _buscar(columnas: dict[str, str], opciones: tuple[str, ...]) -> str | None:
    return next((columnas[o] for o in opciones if o in columnas), None)


def leer_balance_prueba(archivo: Path | str | IO[bytes], nombre: str | None = None) -> pd.DataFrame:
    """
    Lee un balance de prueba (.xlsx, .xls o .csv) y devuelve `cuenta` (texto,
    solo dígitos) y `saldo` (con signo, débito positivo).

    `archivo` puede ser una ruta o un archivo abierto (p. ej. subido desde la
    interfaz); en ese caso `nombre` indica la extensión.
    """
    extension = Path(nombre or str(getattr(archivo, "name", archivo))).suffix.lower()
    if extension not in (".csv", ".xlsx", ".xls"):
        raise ErrorCarga(f"Formato no soportado ({extension or 'sin extensión'}): use .xlsx, .xls o .csv.")
    try:
        crudo = (pd.read_csv(archivo, dtype=str) if extension == ".csv"
                 else pd.read_excel(archivo, dtype=str))
    except Exception as e:  # archivo dañado, protegido o con otra codificación
        raise ErrorCarga(f"No se pudo leer el archivo: {e}") from e
    columnas = {_simplificar(c): c for c in crudo.columns}
    cuenta = _buscar(columnas, COLUMNAS_CUENTA)
    if cuenta is None:
        raise ErrorCarga(f"No se encontró la columna de código de cuenta. Columnas: {list(crudo.columns)}.")

    numero = lambda s: pd.to_numeric(  # noqa: E731
        s.astype(str).str.replace(r"[$\s]", "", regex=True), errors="coerce").fillna(0)
    debito, credito = _buscar(columnas, COLUMNAS_DEBITO), _buscar(columnas, COLUMNAS_CREDITO)
    if debito and credito:
        saldo = numero(crudo[debito]) - numero(crudo[credito])
    else:
        col = _buscar(columnas, COLUMNAS_SALDO)
        if col is None:
            raise ErrorCarga("No se encontró la columna de saldo final (o saldo débito y crédito).")
        saldo = numero(crudo[col])
    return normalizar_balance(pd.DataFrame({"cuenta": crudo[cuenta], "saldo": saldo}))


def normalizar_balance(df: pd.DataFrame) -> pd.DataFrame:
    """Códigos solo con dígitos, filas sin código descartadas, una fila por cuenta."""
    d = df.copy()
    d["cuenta"] = d["cuenta"].astype(str).str.replace(r"\D", "", regex=True)
    d = d[d["cuenta"].str.len() > 0]
    return d.groupby("cuenta", as_index=False)["saldo"].sum()


def hojas(df: pd.DataFrame) -> pd.DataFrame:
    """Cuentas sin subcuentas en el archivo (las demás son totales de sus hijas)."""
    codigos = sorted(df["cuenta"])
    es_padre = {a for a, b in zip(codigos, codigos[1:]) if b.startswith(a)}
    return df[~df["cuenta"].isin(es_padre)]


# --------------------------------------------------------------------------- #
# Traducción al esquema
# --------------------------------------------------------------------------- #
def _legible(campo: str) -> str:
    """'obligaciones_financieras_cp' → 'obligaciones financieras de corto plazo'."""
    return (campo.replace("_cp", " de corto plazo").replace("_lp", " de largo plazo")
            .replace("_", " "))


def _prefijo(cuenta: str, tabla: dict) -> str | None:
    """Prefijo más largo de la tabla que coincide con la cuenta."""
    candidatos = [p for p in tabla if cuenta.startswith(p)]
    return max(candidatos, key=len) if candidatos else None


def a_estado_financiero(df: pd.DataFrame, fecha: date, mapeo: dict | None = None,
                        reclasificaciones: list[tuple[str, str, float]] | None = None
                        ) -> EstadoFinanciero:
    """
    Traduce un balance de prueba (cuenta, saldo con signo) al esquema canónico.

    `reclasificaciones`: (campo_origen, campo_destino, monto) que la empresa
    informa por fuera del PUC, p. ej. ("obligaciones_financieras_cp",
    "obligaciones_financieras_lp", 120_000_000) para la porción de largo plazo.
    """
    m = mapeo or cargar_mapeo()
    d = hojas(normalizar_balance(df))
    d = d[d["cuenta"].str[0].isin(CLASES_LEIDAS)]
    if d.empty:
        raise ErrorCarga("El archivo no trae cuentas de las clases 1 a 7.")

    # Débitos = créditos: si no, los signos o las filas están mal
    descuadre = d["saldo"].sum()
    if abs(descuadre) > max(1.0, TOLERANCIA * d["saldo"].abs().sum()):
        raise ErrorCarga(
            f"Las cuentas de las clases 1 a 7 no suman cero (diferencia {descuadre:,.0f}). "
            "Revise que el saldo tenga signo (débito positivo, crédito negativo) o use "
            "las columnas de saldo débito y saldo crédito."
        )

    tabla = {**m["balance"], **m["resultados"]}
    b: dict[str, float] = {}
    r: dict[str, float] = {}
    sin_mapeo: list[str] = []
    usados: set[str] = set()
    for cuenta, saldo in zip(d["cuenta"], d["saldo"]):
        p = _prefijo(cuenta, tabla)
        if p is None:
            sin_mapeo.append(cuenta)
            continue
        campo = tabla[p]
        if campo is None:
            continue
        valor = -saldo if cuenta[0] in CLASES_CREDITO else saldo
        destino = b if p in m["balance"] else r
        destino[campo] = destino.get(campo, 0) + valor
        if saldo:
            usados.add(cuenta)
    if sin_mapeo:
        raise ErrorCarga(f"Cuentas sin mapeo en config/mapeo_puc.yaml: {', '.join(sin_mapeo[:10])}.")
    if not any(c[0] == "4" for c in usados):
        raise ErrorCarga("No hay saldos en la clase 4 (ingresos): use el balance de prueba "
                         "ANTES del cierre del ejercicio.")

    # El supuesto de plazo sobra si la empresa reclasificó ese mismo campo
    reclasificados = {origen for origen, _, _ in reclasificaciones or []}
    supuestos = [texto for prefijo, texto in m["supuestos"].items()
                 if any(c.startswith(prefijo) for c in usados)
                 and tabla.get(_prefijo(prefijo, tabla)) not in reclasificados]

    # Depreciación: informativa, ya está dentro de los gastos
    dep = d[d["cuenta"].map(lambda c: _prefijo(c, m["informativo"]) is not None)]["saldo"].sum()
    if dep > 0:
        r["depreciacion_amortizacion"] = dep
    elif b.get("ppe", 0) + b.get("intangibles", 0) <= 0:
        r["depreciacion_amortizacion"] = 0
    # Si hay activos fijos y no aparecen las cuentas 5160/5165/5260/5265, la
    # depreciación pudo registrarse en costos (clase 6 o 7): queda como no
    # reportada (EBITDA = None), nunca como cero.

    for origen, destino, monto in reclasificaciones or []:
        if monto < 0 or monto > b.get(origen, 0) + 1e-6:
            raise ErrorCarga(f"Reclasificación inválida: {monto:,.0f} de {origen} (saldo "
                             f"{b.get(origen, 0):,.0f}).")
        b[origen] -= monto
        b[destino] = b.get(destino, 0) + monto
        supuestos.append(f"Se reclasificaron {formatear(monto, 'pesos')} de {_legible(origen)} "
                         f"a {_legible(destino)} según información de la empresa.")

    try:
        # Un balance de prueba es completo: la cuenta ausente vale cero (no es
        # "no reportada"). La depreciación es la excepción, ver arriba.
        r = {c: 0 for c in EstadoResultados.model_fields if c != "depreciacion_amortizacion"} | r
        resultados = EstadoResultados(**r)
        # Antes del cierre la utilidad vive en las clases 4 a 7, no en la 36
        b["resultado_ejercicio"] = b.get("resultado_ejercicio", 0) + resultados.utilidad_neta
        b = {c: 0 for c in BalanceGeneral.model_fields} | b
        return EstadoFinanciero(fecha_corte=fecha, meses=fecha.month, balance=BalanceGeneral(**b),
                                resultados=resultados, supuestos_carga=supuestos)
    except ValidationError as e:
        primero = e.errors()[0]
        campo = ".".join(str(x) for x in primero["loc"])
        raise ErrorCarga(f"No cumple el esquema ({campo}: {primero['msg']}).") from e


def cargar_historial(empresa: Empresa, balances: dict[date, pd.DataFrame | Path | str],
                     reclasificaciones: dict[date, list[tuple[str, str, float]]] | None = None
                     ) -> HistorialFinanciero:
    """Historial a partir de uno o más balances de prueba (DataFrame o ruta a archivo)."""
    m = cargar_mapeo()
    periodos = []
    for fecha, fuente in balances.items():
        df = fuente if isinstance(fuente, pd.DataFrame) else leer_balance_prueba(fuente)
        periodos.append(a_estado_financiero(df, fecha, m, (reclasificaciones or {}).get(fecha)))
    return HistorialFinanciero(empresa=empresa, periodos=periodos)
