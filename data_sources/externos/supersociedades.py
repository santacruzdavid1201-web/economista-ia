"""
Cargador de estados financieros NIIF de Supersociedades (datos.gov.co).

Traduce los reportes de las empresas pares al esquema canónico para que sus
indicadores se calculen con las MISMAS funciones que los de la empresa
analizada. Decisiones y evidencia: exploracion/hallazgos_supersociedades.md.

Dos capas:
- Descarga (`consultar`, `descargar_*`): consultas SoQL filtradas por NIT y
  fecha. Nunca se descargan los datasets completos (millones de filas).
- Transformación (`filtrar_reportes`, `a_estado_financiero`,
  `construir_historiales`): pura, sin red. Una empresa cuyos datos no se pueden
  traducir con confianza se excluye con su motivo; nunca se rellena.

Montos en miles de pesos, tal como los publica la fuente (Empresa.unidad = 1_000).
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import requests
import yaml
from pydantic import BaseModel, ValidationError

from modules.esquema_financiero import (
    BalanceGeneral,
    Empresa,
    EstadoFinanciero,
    EstadoResultados,
    FlujoEfectivo,
    HistorialFinanciero,
)

DOMINIO = "www.datos.gov.co"
DATASETS = {
    "caratula": "6hqw-m3dm",
    "esf": "pfdp-zks5",   # estado de situación financiera
    "eri": "prwj-nzxa",   # estado de resultado integral
    "efe": "ctcp-462n",   # estado de flujo de efectivo
}
MAPEO = Path(__file__).resolve().parents[2] / "config" / "mapeo_niif.yaml"

# 10/40 individual, 20/50 separado. Se descartan 30/60 consolidado y 35/65
# combinado: mezclan varias empresas y no son comparables con una pyme.
PUNTOS_ENTRADA = {"10", "20", "40", "50"}
PERIODOS = {"Periodo Actual", "Periodo Anterior"}
TOLERANCIA = 0.001      # 0,1 % del total: por debajo, el residuo es redondeo
TIMEOUT = 180

# Supuestos comunes a todas las empresas: van a ReferenciaSectorial.filtros.
SUPUESTOS_MAPEO = [
    "Cartera de los pares = cuentas comerciales y otras cuentas por cobrar "
    "corrientes (la taxonomía NIIF no las separa).",
    "Proveedores de los pares = cuentas comerciales y otras cuentas por pagar "
    "corrientes (la taxonomía NIIF no las separa).",
    "Deuda financiera de los pares = total de otros pasivos financieros (incluye "
    "préstamos y arrendamientos financieros).",
    "Solo estados individuales o separados con corte a 31 de diciembre.",
]

# Grupos del balance: total reportado, campos que lo componen y destino del residuo.
GRUPOS_BALANCE = {
    "activo corriente": ("activo_corriente",
                         ["efectivo", "inversiones_cp", "deudores_comerciales",
                          "otros_deudores_cp", "inventarios", "otros_activos_cp"],
                         "otros_activos_cp"),
    "activo no corriente": ("activo_no_corriente",
                            ["ppe", "intangibles", "inversiones_lp", "deudores_lp",
                             "otros_activos_lp"],
                            "otros_activos_lp"),
    "pasivo corriente": ("pasivo_corriente",
                         ["obligaciones_financieras_cp", "proveedores",
                          "otras_cuentas_por_pagar_cp", "impuestos_por_pagar",
                          "obligaciones_laborales", "otros_pasivos_cp"],
                         "otros_pasivos_cp"),
    "pasivo no corriente": ("pasivo_no_corriente",
                            ["obligaciones_financieras_lp", "otros_pasivos_lp"],
                            "otros_pasivos_lp"),
}
PATRIMONIO = ["capital", "reservas", "resultados_acumulados", "resultado_ejercicio",
              "otro_patrimonio"]


class ErrorCarga(ValueError):
    """Los datos de un reporte no se pueden traducir al esquema con confianza."""


class Exclusion(BaseModel):
    nit: str
    fecha_corte: date | None = None
    motivo: str


# --------------------------------------------------------------------------- #
# Normalización y mapeo
# --------------------------------------------------------------------------- #
def normalizar(texto: str) -> str:
    """
    Minúsculas, sin caracteres no ASCII y con espacios simples.

    La fuente reemplaza las tildes por U+FFFD ("administraci�n"); quitando todo
    lo no ASCII en ambos lados, "administración" y "administraci�n" coinciden.
    """
    ascii_ = "".join(c for c in str(texto).lower() if ord(c) < 128)
    return " ".join(ascii_.split())


def cargar_mapeo(ruta: Path = MAPEO) -> dict:
    """Lee el mapeo y normaliza todos los nombres de conceptos."""
    crudo = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    lista = lambda conceptos: [normalizar(c) for c in conceptos]  # noqa: E731
    return {
        "balance": {campo: lista(cs) for campo, cs in crudo["balance"].items()},
        "balance_alternativas": {campo: [lista(alt) for alt in alternativas]
                                 for campo, alternativas in crudo["balance_alternativas"].items()},
        "patrimonio_resta": lista(crudo["patrimonio_resta"]),
        "totales_balance": {k: normalizar(v) for k, v in crudo["totales_balance"].items()},
        "resultados": {campo: lista(cs) for campo, cs in crudo["resultados"].items()},
        "impuesto_renta": lista(crudo["impuesto_renta"]),
        "totales_resultados": {k: normalizar(v) for k, v in crudo["totales_resultados"].items()},
        "flujo": {k: normalizar(v) for k, v in crudo["flujo"].items()},
    }


def _sumar(valores: dict[str, float], conceptos: list[str]) -> float | None:
    """Suma los conceptos presentes; None si no hay ninguno."""
    presentes = [valores[c] for c in conceptos if c in valores]
    return sum(presentes) if presentes else None


def _tolerancia(total: float) -> float:
    return max(1.0, TOLERANCIA * abs(total))


# --------------------------------------------------------------------------- #
# Transformación
# --------------------------------------------------------------------------- #
def filtrar_reportes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Deja una fila por (nit, fecha, concepto) de reportes comparables.

    - Solo puntos de entrada individuales o separados y cortes a 31-dic.
    - `fecha` es la fecha a la que corresponde el dato: el `Periodo Anterior`
      de un reporte es el cierre del año previo.
    - Si una empresa retransmitió, gana el radicado más reciente.
    - Si un mismo año viene como `Periodo Actual` de su propio reporte y como
      `Periodo Anterior` del reporte siguiente, gana el primero.
    """
    d = df[df["punto_entrada"].astype(str).str[:2].isin(PUNTOS_ENTRADA)
           & df["periodo"].isin(PERIODOS)
           & df["fecha_corte"].astype(str).str[5:10].eq("12-31")].copy()
    corte = pd.to_datetime(d["fecha_corte"].astype(str).str[:10])
    anterior = d["periodo"].eq("Periodo Anterior")
    d["fecha"] = corte.where(~anterior, corte - pd.DateOffset(years=1)).dt.date
    d["es_anterior"] = anterior
    d["nit"] = d["nit"].astype(str)
    d["clave"] = d["concepto"].map(normalizar)
    d["valor"] = pd.to_numeric(d["valor"], errors="coerce")
    d = d.dropna(subset=["valor"])
    d = d.sort_values(["es_anterior", "numero_radicado"], ascending=[True, False])
    return d.drop_duplicates(subset=["nit", "fecha", "clave"], keep="first")


def a_estado_financiero(esf: dict[str, float], eri: dict[str, float],
                        efe: dict[str, float] | None, fecha: date,
                        mapeo: dict | None = None) -> EstadoFinanciero:
    """
    Traduce un reporte (conceptos normalizados → valor) al esquema canónico.

    Lanza ErrorCarga si falta un total indispensable, si hay doble conteo o si
    el resultado no cumple las validaciones del esquema.
    """
    m = mapeo or cargar_mapeo()
    supuestos: list[str] = []

    # --- Totales reportados (indispensables) ---
    tot = {k: esf.get(c) for k, c in m["totales_balance"].items()}
    faltan = [k for k, v in tot.items() if v is None]
    if faltan:
        raise ErrorCarga(f"Faltan totales del balance: {', '.join(faltan)}.")
    tot["activo_no_corriente"] = tot["activo_total"] - tot["activo_corriente"]
    tot["pasivo_no_corriente"] = tot["pasivo_total"] - tot["pasivo_corriente"]

    tr = {k: eri.get(c) for k, c in m["totales_resultados"].items()}
    ingresos = _sumar(eri, m["resultados"]["ingresos_operacionales"])
    if ingresos is None or tr["utilidad_neta"] is None or tr["utilidad_antes_impuestos"] is None:
        raise ErrorCarga("Faltan ingresos, utilidad antes de impuestos o utilidad neta.")

    # --- Balance: cuentas mapeadas ---
    b: dict[str, float] = {}
    for campo, conceptos in m["balance"].items():
        valor = _sumar(esf, conceptos)
        if valor is not None:
            b[campo] = valor
    for campo, alternativas in m["balance_alternativas"].items():
        valor = next((v for alt in alternativas if (v := _sumar(esf, alt)) is not None), None)
        if valor is not None:
            b[campo] = valor
    resta = _sumar(esf, m["patrimonio_resta"])
    if resta:
        b["otro_patrimonio"] = b.get("otro_patrimonio", 0) - resta
    # "Ganancias acumuladas" incluye la utilidad del año: se separa.
    b["resultado_ejercicio"] = tr["utilidad_neta"]
    b["resultados_acumulados"] = b.get("resultados_acumulados", 0) - tr["utilidad_neta"]

    # --- Residuos contra los totales reportados ---
    for nombre, (clave_total, campos, destino) in GRUPOS_BALANCE.items():
        total = tot[clave_total]
        residuo = total - sum(b.get(c, 0) for c in campos)
        if residuo < -_tolerancia(total):
            raise ErrorCarga(
                f"Las cuentas del {nombre} suman más que su total reportado "
                f"({-residuo:,.0f} de diferencia): posible doble conteo."
            )
        if residuo > _tolerancia(total):
            b[destino] = b.get(destino, 0) + residuo
            supuestos.append(
                f"{residuo / total:.1%} del {nombre} no corresponde a cuentas "
                f"identificadas y se registró en {destino}."
            )
    residuo_pat = tot["patrimonio_total"] - sum(b.get(c, 0) for c in PATRIMONIO)
    if abs(residuo_pat) > _tolerancia(tot["patrimonio_total"]):
        b["otro_patrimonio"] = b.get("otro_patrimonio", 0) + residuo_pat
        supuestos.append(
            f"Partidas del patrimonio no identificadas por {residuo_pat:,.0f} "
            "(miles de pesos) se registraron en otro_patrimonio."
        )

    # --- Estado de resultados ---
    r: dict[str, float] = {"ingresos_operacionales": ingresos}
    for campo, conceptos in m["resultados"].items():
        valor = _sumar(eri, conceptos)
        if valor is not None:
            r[campo] = valor
    impuesto = next((eri[c] for c in m["impuesto_renta"] if c in eri), None)
    if impuesto is not None:
        r["impuesto_renta"] = impuesto

    # Partidas no mapeadas (coberturas, deterioro NIIF 9, método de participación,
    # "otras ganancias"): residuo contra la utilidad antes de impuestos.
    uai = (ingresos - r.get("costo_ventas", 0) - r.get("gastos_administracion", 0)
           - r.get("gastos_ventas", 0) + r.get("otros_ingresos", 0)
           - r.get("otros_gastos", 0) + r.get("ingresos_financieros", 0)
           - r.get("gastos_financieros", 0))
    ajustes = [(tr["utilidad_antes_impuestos"] - uai,
                "Partidas no operacionales sin cuenta propia")]
    discontinuadas = tr.get("operaciones_discontinuadas") or 0
    if discontinuadas:
        ajustes.append((discontinuadas, "El resultado de operaciones discontinuadas (neto "
                                        "de impuestos)"))
    for monto, descripcion in ajustes:
        if abs(monto) <= _tolerancia(ingresos):
            continue
        campo = "otros_ingresos" if monto > 0 else "otros_gastos"
        r[campo] = r.get(campo, 0) + abs(monto)
        supuestos.append(f"{descripcion} ({monto:,.0f} miles de pesos) se registró en {campo}.")

    # --- Flujo de efectivo: depreciación y totales ---
    flujo = None
    efe = efe or {}
    f = {k: efe.get(c) for k, c in m["flujo"].items()}
    if f["depreciacion_amortizacion"] is not None:
        if f["depreciacion_amortizacion"] < 0:
            supuestos.append("La depreciación venía con signo negativo; se tomó su valor absoluto.")
        r["depreciacion_amortizacion"] = abs(f["depreciacion_amortizacion"])
    if f["operacion"] is not None:
        inversion, financiacion = f["inversion"] or 0, f["financiacion"] or 0
        cuadra = (f["variacion_efectivo"] is None
                  or abs(f["operacion"] + inversion + financiacion - f["variacion_efectivo"])
                  <= _tolerancia(f["variacion_efectivo"]))
        if cuadra:
            flujo = FlujoEfectivo(operacion=f["operacion"], inversion=inversion,
                                  financiacion=financiacion)
        else:
            supuestos.append("El flujo de efectivo no cuadra con la variación del efectivo: se omitió.")

    try:
        return EstadoFinanciero(
            fecha_corte=fecha, meses=12, balance=BalanceGeneral(**b),
            resultados=EstadoResultados(**r), flujo=flujo, supuestos_carga=supuestos,
        )
    except ValidationError as e:
        primero = e.errors()[0]
        campo = ".".join(str(x) for x in primero["loc"])
        raise ErrorCarga(f"No cumple el esquema ({campo}: {primero['msg']}).") from e


def _empresa(nit: str, caratula: pd.DataFrame, grupo: str | None) -> Empresa:
    """Datos de identificación a partir de la carátula más reciente de la empresa."""
    # De la carátula más reciente a la más antigua: gana el último valor reportado
    c = caratula[caratula["nit"].astype(str) == nit].sort_values("fecha_corte", ascending=False)

    def valor(prefijo: str) -> str | None:
        return next((v for k, v in zip(c["clave"], c["valor"]) if k.startswith(prefijo)), None)

    ciiu = valor(normalizar("Clasificación Industrial"))
    if not ciiu or not str(ciiu)[1:5].isdigit():
        raise ErrorCarga("La carátula no trae un CIIU válido.")
    return Empresa(
        empresa_id=nit,
        razon_social=valor(normalizar("Razón social de la sociedad")) or f"NIT {nit}",
        ciiu=str(ciiu)[1:5],
        departamento=valor(normalizar("Departamento de la dirección del domicilio")),
        municipio=valor(normalizar("Ciudad de la dirección del domicilio")),
        grupo_niif=1 if grupo in ("10", "20") else 2 if grupo in ("40", "50") else None,
        unidad=1_000,
    )


def construir_historiales(caratula: pd.DataFrame, esf: pd.DataFrame, eri: pd.DataFrame,
                          efe: pd.DataFrame | None = None, mapeo: dict | None = None
                          ) -> tuple[list[HistorialFinanciero], list[Exclusion]]:
    """
    Convierte las descargas crudas en un HistorialFinanciero por empresa.

    Cada periodo que no se puede traducir queda en la lista de exclusiones con
    su motivo; la empresa se conserva si le queda al menos un periodo.
    """
    m = mapeo or cargar_mapeo()
    car = caratula[caratula["periodo"].eq("Periodo Actual")].copy()
    car["clave"] = car["concepto"].map(normalizar)
    esf_f, eri_f = filtrar_reportes(esf), filtrar_reportes(eri)
    efe_f = filtrar_reportes(efe) if efe is not None else None

    def por_fecha(d: pd.DataFrame | None) -> dict[tuple[str, date], dict[str, float]]:
        if d is None:
            return {}
        return {k: dict(zip(g["clave"], g["valor"])) for k, g in d.groupby(["nit", "fecha"])}

    esf_g, eri_g, efe_g = por_fecha(esf_f), por_fecha(eri_f), por_fecha(efe_f)
    anteriores = set(zip(esf_f.loc[esf_f["es_anterior"], "nit"],
                         esf_f.loc[esf_f["es_anterior"], "fecha"]))
    grupos = dict(zip(esf_f["nit"], esf_f["punto_entrada"].astype(str).str[:2]))

    periodos: dict[str, list[EstadoFinanciero]] = {}
    exclusiones: list[Exclusion] = []
    for (nit, fecha), valores_esf in sorted(esf_g.items()):
        try:
            if (nit, fecha) not in eri_g:
                raise ErrorCarga("No hay estado de resultados para la misma fecha.")
            ef = a_estado_financiero(valores_esf, eri_g[(nit, fecha)],
                                     efe_g.get((nit, fecha)), fecha, m)
        except ErrorCarga as e:
            exclusiones.append(Exclusion(nit=nit, fecha_corte=fecha, motivo=str(e)))
            continue
        if (nit, fecha) in anteriores:
            ef.supuestos_carga.append(
                "Cifras tomadas del comparativo (periodo anterior) del reporte del año siguiente.")
        periodos.setdefault(nit, []).append(ef)

    historiales: list[HistorialFinanciero] = []
    for nit, efs in periodos.items():
        try:
            empresa = _empresa(nit, car, grupos.get(nit))
        except ErrorCarga as e:
            exclusiones.append(Exclusion(nit=nit, motivo=str(e)))
            continue
        historiales.append(HistorialFinanciero(empresa=empresa, periodos=efs))
    return historiales, exclusiones


# --------------------------------------------------------------------------- #
# Descarga
# --------------------------------------------------------------------------- #
def consultar(dataset: str, where: str, limite: int = 50_000) -> pd.DataFrame:
    """Consulta SoQL paginada contra la API de datos.gov.co."""
    url = f"https://{DOMINIO}/resource/{DATASETS.get(dataset, dataset)}.json"
    paginas, offset = [], 0
    while True:
        r = requests.get(url, params={"$where": where, "$limit": limite, "$offset": offset,
                                      "$order": ":id"}, timeout=TIMEOUT)
        r.raise_for_status()
        filas = r.json()
        paginas.append(pd.DataFrame(filas))
        if len(filas) < limite:
            break
        offset += limite
    return pd.concat(paginas, ignore_index=True)


def _rango(anios: list[int]) -> str:
    return (f"fecha_corte between '{min(anios)}-01-01' "
            f"and '{max(anios)}-12-31T23:59:59'")


# Secciones CIIU Rev. 4 A.C. por división (dos primeros dígitos): la carátula
# escribe el código con la letra de la sección delante ("I5511 - ...").
SECCIONES_CIIU = [
    ("A", 1, 3), ("B", 5, 9), ("C", 10, 33), ("D", 35, 35), ("E", 36, 39),
    ("F", 41, 43), ("G", 45, 47), ("H", 49, 53), ("I", 55, 56), ("J", 58, 63),
    ("K", 64, 66), ("L", 68, 68), ("M", 69, 75), ("N", 77, 82), ("O", 84, 84),
    ("P", 85, 85), ("Q", 86, 88), ("R", 90, 93), ("S", 94, 96), ("T", 97, 98),
    ("U", 99, 99),
]


def seccion_ciiu(ciiu: str) -> str:
    division = int(ciiu[:2])
    for letra, desde, hasta in SECCIONES_CIIU:
        if desde <= division <= hasta:
            return letra
    raise ValueError(f"CIIU sin sección conocida: {ciiu}")


def descargar_nits_por_ciiu(ciius: list[str], anios: list[int]) -> list[str]:
    """NIT de las empresas cuya carátula declara alguno de los CIIU dados."""
    # starts_with en lugar de like '%...': evita recorrer los 9,6 M de filas
    ciiu = " OR ".join(f"starts_with(valor, '{seccion_ciiu(c)}{c}')" for c in ciius)
    d = consultar("caratula", f"starts_with(concepto, 'Clasificaci') AND ({ciiu}) "
                              f"AND {_rango(anios)}")
    return sorted(d["nit"].astype(str).unique()) if not d.empty else []


def descargar_estados(nits: list[str], anios: list[int], lote: int = 200
                      ) -> dict[str, pd.DataFrame]:
    """Carátula, balance, resultados y flujo de los NIT y años indicados."""
    salida: dict[str, list[pd.DataFrame]] = {k: [] for k in DATASETS}
    for i in range(0, len(nits), lote):
        lista = ",".join(nits[i:i + lote])
        for dataset in DATASETS:
            salida[dataset].append(consultar(dataset, f"nit in({lista}) AND {_rango(anios)}"))
    return {k: pd.concat(v, ignore_index=True) for k, v in salida.items()}
