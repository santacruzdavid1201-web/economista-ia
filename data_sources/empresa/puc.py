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

import csv
import io
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
# En orden de preferencia: "Cuenta" a veces es el nombre y no el código
COLUMNAS_CUENTA = ("codigo", "codigo cuenta", "cod cuenta", "codigo contable", "cuenta",
                   "cuenta contable")
COLUMNAS_SALDO = ("saldo final", "saldo", "nuevo saldo", "saldo actual")
COLUMNAS_DEBITO = ("saldo debito", "saldo final debito")
COLUMNAS_CREDITO = ("saldo credito", "saldo final credito")

# Reclasificaciones que la empresa puede informar por fuera del PUC, que no
# separa el plazo. Solo mueven saldos dentro del mismo lado del balance.
RECLASIFICACIONES = {
    ("obligaciones_financieras_cp", "obligaciones_financieras_lp"):
        "Obligaciones financieras de largo plazo (cuenta 21)",
    ("inversiones_cp", "inversiones_lp"): "Inversiones de largo plazo (cuenta 12)",
    ("deudores_comerciales", "deudores_lp"): "Clientes que pagan a más de un año (cuenta 1305)",
    ("otros_deudores_cp", "deudores_lp"): "Otros deudores de largo plazo (cuenta 13)",
    ("otros_pasivos_cp", "otros_pasivos_lp"): "Otros pasivos de largo plazo (cuentas 26 a 28)",
    ("otros_activos_lp", "otros_activos_cp"):
        "Diferidos que se consumen en menos de un año (cuentas 17 y 18)",
    ("ppe", "inversiones_lp"):
        "Propiedades de inversión: inmuebles para arrendar o valorizar (cuenta 15)",
}


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


def _buscar(columnas: dict[str, int], opciones: tuple[str, ...]) -> int | None:
    return next((columnas[o] for o in opciones if o in columnas), None)


# --------------------------------------------------------------------------- #
# Números en formato colombiano o inglés
# --------------------------------------------------------------------------- #
def _limpiar_numero(texto: str) -> tuple[str, bool]:
    """Quita símbolos y detecta el signo: '-', '(...)' o un '-' al final."""
    t = re.sub(r"[\s\u00a0$]|COP", "", str(texto))
    negativo = t.startswith("-") or t.endswith("-") or (t.startswith("(") and t.endswith(")"))
    return t.strip("-()"), negativo


def separador_decimal(textos: list[str]) -> str | None:
    """
    Separador decimal de una columna, decidido con todos sus valores:
    - con punto y coma a la vez, el último es el decimal ("1.234,56");
    - un separador repetido es de miles ("2.400.000");
    - uno solo seguido de 1, 2 o más de 3 dígitos es decimal ("85,5").
    Si solo hay casos ambiguos ("1.500"), son miles: en un balance en pesos
    un decimal de exactamente tres cifras es muy improbable. Devuelve None
    cuando no hay decimales.
    """
    votos = {".": 0, ",": 0}
    for texto in textos:
        t, _ = _limpiar_numero(texto)
        puntos, comas = t.count("."), t.count(",")
        if puntos and comas:
            votos["," if t.rfind(",") > t.rfind(".") else "."] += 1
        elif puntos > 1:
            votos[","] += 1
        elif comas > 1:
            votos["."] += 1
        elif puntos == 1 or comas == 1:
            sep = "." if puntos else ","
            if len(t) - t.rfind(sep) - 1 != 3:
                votos[sep] += 1
    if not any(votos.values()):
        return None
    return max(votos, key=votos.get)


def a_numero(valor: object, decimal: str | None) -> float:
    """Convierte una celda a número; las vacías valen cero."""
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return 0.0 if pd.isna(valor) else float(valor)   # celda numérica de Excel
    t, negativo = _limpiar_numero(valor if valor is not None else "")
    if not t:
        return 0.0
    if decimal is None:
        t = t.replace(".", "").replace(",", "")
    else:
        miles = "," if decimal == "." else "."
        t = t.replace(miles, "").replace(decimal, ".")
    try:
        numero = float(t)
    except ValueError:
        raise ErrorCarga(f"Valor no numérico en la columna de saldos: '{valor}'.") from None
    return -numero if negativo else numero


def _codigo(valor: object) -> str:
    """Código de cuenta como texto; en Excel puede venir como 1105.0."""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return "" if valor is None or (isinstance(valor, float) and pd.isna(valor)) else str(valor)


# --------------------------------------------------------------------------- #
# Lectura del archivo
# --------------------------------------------------------------------------- #
def _decodificar(datos: bytes) -> str:
    # Excel en español guarda los CSV en Windows-1252; los demás, en UTF-8
    for codificacion in ("utf-8-sig", "cp1252"):
        try:
            return datos.decode(codificacion)
        except UnicodeDecodeError:
            continue
    raise ErrorCarga("No se reconoce la codificación del archivo (use UTF-8 o Windows-1252).")


def _columna_de_codigos(muestra: list[list], columnas: dict[str, int]) -> int | None:
    """
    Columna del código de cuenta. Algunos programas llaman "Cuenta" al código y
    otros al nombre de la cuenta: entre las candidatas gana la primera (en el
    orden de COLUMNAS_CUENTA) cuyos valores son mayoritariamente códigos.
    """
    for nombre in COLUMNAS_CUENTA:
        j = columnas.get(nombre)
        if j is None:
            continue
        valores = [_codigo(f[j]) for f in muestra if j < len(f) and f[j] not in (None, "")]
        if valores and sum(bool(re.fullmatch(r"[\d\s.\-]+", v)) for v in valores) > len(valores) / 2:
            return j
    return None


def _encabezado(filas: list[list]) -> tuple[int, int, int | None, int | None, int | None] | None:
    """
    Fila de encabezados y columnas (cuenta, saldo, débito, crédito). Los programas
    contables suelen poner antes el nombre de la empresa, el NIT y las fechas.
    Con saldo débito y crédito se usan esas dos; si no, la de saldo con signo.
    """
    for i, fila in enumerate(filas[:30]):
        columnas: dict[str, int] = {}
        for j, celda in enumerate(fila):
            if celda not in (None, ""):
                columnas.setdefault(_simplificar(celda), j)
        cuenta = _columna_de_codigos(filas[i + 1:i + 31], columnas)
        debito, credito = _buscar(columnas, COLUMNAS_DEBITO), _buscar(columnas, COLUMNAS_CREDITO)
        saldo = _buscar(columnas, COLUMNAS_SALDO)
        if cuenta is None:
            continue
        if debito is not None and credito is not None:
            return i, cuenta, None, debito, credito
        if saldo is not None:
            return i, cuenta, saldo, None, None
    return None


def _filas(archivo: Path | str | IO[bytes], extension: str) -> list[list[list]]:
    """Filas crudas del archivo; para CSV, una lectura por cada separador posible."""
    if extension != ".csv":
        df = pd.read_excel(archivo, header=None, dtype=object)
        return [df.astype(object).where(df.notna(), None).values.tolist()]
    datos = archivo.read() if hasattr(archivo, "read") else Path(archivo).read_bytes()
    texto = _decodificar(datos)
    return [list(csv.reader(io.StringIO(texto), delimiter=d)) for d in (";", ",", "\t", "|")]


def leer_balance_prueba(archivo: Path | str | IO[bytes], nombre: str | None = None) -> pd.DataFrame:
    """
    Lee un balance de prueba (.xlsx, .xls o .csv) y devuelve `cuenta` (texto,
    solo dígitos) y `saldo` (con signo, débito positivo).

    Acepta filas de título antes del encabezado, CSV separados por ";" o ",",
    archivos en UTF-8 o Windows-1252 y números en formato colombiano
    ("1.234.567,89") o inglés ("1,234,567.89"), con negativos "-" o "(...)".
    `archivo` puede ser una ruta o un archivo abierto (p. ej. subido desde la
    interfaz); en ese caso `nombre` indica la extensión.
    """
    extension = Path(nombre or str(getattr(archivo, "name", archivo))).suffix.lower()
    if extension not in (".csv", ".xlsx", ".xls"):
        raise ErrorCarga(f"Formato no soportado ({extension or 'sin extensión'}): use .xlsx, .xls o .csv.")
    try:
        lecturas = _filas(archivo, extension)
    except ErrorCarga:
        raise
    except Exception as e:  # archivo dañado o protegido
        raise ErrorCarga(f"No se pudo leer el archivo: {e}") from e

    for filas in lecturas:
        encontrado = _encabezado(filas)
        if encontrado:
            break
    else:
        primera = next((f for f in lecturas[0] if any(c not in (None, "") for c in f)), [])
        raise ErrorCarga(
            "No se encontró la fila de encabezados con la columna de código de cuenta y la "
            "de saldo final (o saldo débito y crédito) en las primeras 30 filas. Primera "
            f"fila con datos: {[c for c in primera if c not in (None, '')]}.")

    i, col_cuenta, col_saldo, col_debito, col_credito = encontrado
    datos = [f for f in filas[i + 1:] if len(f) > col_cuenta]
    celda = lambda f, j: f[j] if j is not None and j < len(f) else None  # noqa: E731

    def columna(j: int) -> list[float]:
        valores = [celda(f, j) for f in datos]
        decimal = separador_decimal([v for v in valores if isinstance(v, str)])
        return [a_numero(v, decimal) for v in valores]

    if col_saldo is None:
        saldos = [d - c for d, c in zip(columna(col_debito), columna(col_credito))]
    else:
        saldos = columna(col_saldo)
    cuentas = [_codigo(celda(f, col_cuenta)) for f in datos]
    return normalizar_balance(pd.DataFrame({"cuenta": cuentas, "saldo": saldos}))


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
    Solo se aceptan los pares de `RECLASIFICACIONES`.
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
        if (origen, destino) not in RECLASIFICACIONES:
            raise ErrorCarga(f"Reclasificación no permitida: de {_legible(origen)} a "
                             f"{_legible(destino)}.")
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
