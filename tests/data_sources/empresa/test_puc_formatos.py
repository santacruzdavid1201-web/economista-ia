"""Formatos reales de exportación de balances de prueba."""
import io

import pandas as pd
import pytest

from data_sources.empresa.puc import (
    ErrorCarga,
    a_estado_financiero,
    a_numero,
    leer_balance_prueba,
    separador_decimal,
)
from tests.data_sources.empresa.test_puc import CORTE, balance_prueba

TITULOS = [["HOTEL DEMO S.A.S."], ["NIT 900.123.456-7"],
           ["Balance de prueba de enero 1 a diciembre 31 de 2024"], []]


def colombiano(valor: float) -> str:
    """1234567.5 → '1.234.567,50'; negativos entre paréntesis."""
    texto = f"{abs(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"({texto})" if valor < 0 else texto


# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("textos, esperado", [
    (["1.234.567,89", "500"], ","),
    (["1,234,567.89"], "."),
    (["2.400.000.000", "1.500"], ","),        # punto repetido: es de miles
    (["85,5", "12,25"], ","),
    (["1.500", "2.300"], None),               # ambiguo: miles, sin decimales
    (["1500", "-300"], None),
])
def test_separador_decimal(textos, esperado):
    assert separador_decimal(textos) == esperado


@pytest.mark.parametrize("valor, decimal, esperado", [
    ("1.234.567,89", ",", 1_234_567.89),
    ("1,234,567.89", ".", 1_234_567.89),
    ("(500.000)", None, -500_000),
    ("$ -148.000.000", None, -148_000_000),
    ("1.500-", None, -1_500),
    ("", ",", 0),
    (None, ",", 0),
    (2_400_000_000.0, None, 2_400_000_000),   # celda numérica de Excel
])
def test_a_numero(valor, decimal, esperado):
    assert a_numero(valor, decimal) == pytest.approx(esperado)


def test_valor_no_numerico():
    with pytest.raises(ErrorCarga, match="no numérico"):
        a_numero("N/A", ",")


# --------------------------------------------------------------------------- #
def test_csv_estilo_software_contable_colombiano():
    """Títulos arriba, ';', números colombianos, paréntesis y Windows-1252."""
    df = balance_prueba()
    lineas = [";".join(f) for f in TITULOS]
    lineas.append("Código;Nombre de la cuenta;Saldo anterior;Débitos;Créditos;Saldo final")
    lineas += [f"{c};Cuenta {c};0,00;0,00;0,00;{colombiano(s * 1_000)}"
               for c, s in zip(df["cuenta"], df["saldo"])]
    archivo = io.BytesIO("\r\n".join(lineas).encode("cp1252"))
    ef = a_estado_financiero(leer_balance_prueba(archivo, "balance.csv"), CORTE)
    assert ef.balance.activo_total == 2_050_000
    assert ef.resultados.utilidad_neta == 140_000


def test_excel_con_titulos_y_codigos_numericos(tmp_path):
    df = balance_prueba()
    ruta = tmp_path / "balance.xlsx"
    with pd.ExcelWriter(ruta) as w:
        pd.DataFrame(TITULOS[:3]).to_excel(w, index=False, header=False)
        pd.DataFrame({"Cuenta": df["cuenta"].astype(int),        # códigos como número
                      "Descripción": "x",
                      "Saldo Débito": df["saldo"].clip(lower=0).astype(float),
                      "Saldo Crédito": (-df["saldo"]).clip(lower=0).astype(float)}
                     ).to_excel(w, index=False, startrow=5)
    ef = a_estado_financiero(leer_balance_prueba(ruta), CORTE)
    assert ef.balance.activo_total == 2_050


def test_csv_en_formato_ingles_y_columna_cuenta_con_nombres():
    # "Cuenta" trae el nombre de la cuenta; el código está en "Código"
    df = balance_prueba()
    lineas = ['"Cuenta","Código","Saldo final"']
    lineas += [f'"Cuenta {c}","{c}","{s * 1_000:,.2f}"' for c, s in zip(df["cuenta"], df["saldo"])]
    archivo = io.BytesIO("\n".join(lineas).encode("utf-8"))
    ef = a_estado_financiero(leer_balance_prueba(archivo, "balance.csv"), CORTE)
    assert ef.balance.activo_total == 2_050_000


def test_sin_encabezado_reconocible_muestra_la_primera_fila():
    archivo = io.BytesIO("Empresa X\nDescripción;Valor\nCaja;100".encode("utf-8"))
    with pytest.raises(ErrorCarga, match=r"Primera fila con datos: \['Empresa X'\]"):
        leer_balance_prueba(archivo, "balance.csv")


def test_elige_la_columna_que_tiene_codigos():
    # "Cuenta" (preferida por nombre) trae nombres; los códigos están en "Cuenta contable"
    df = balance_prueba()
    lineas = ["Cuenta;Cuenta contable;Saldo"]
    lineas += [f"Nombre {c};{c};{s}" for c, s in zip(df["cuenta"], df["saldo"])]
    archivo = io.BytesIO("\n".join(lineas).encode("utf-8"))
    ef = a_estado_financiero(leer_balance_prueba(archivo, "balance.csv"), CORTE)
    assert ef.balance.activo_total == 2_050
