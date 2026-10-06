"""
Balance de prueba sintético que replica la empresa de referencia de
tests/conftest.py: activo 2.050, pasivo 870, patrimonio 1.180, ingresos 1.000,
utilidad neta 140. Saldos con signo, débito positivo.
"""
from datetime import date

import pandas as pd
import pytest

from data_sources.empresa.puc import (
    ErrorCarga,
    a_estado_financiero,
    cargar_historial,
    hojas,
    leer_balance_prueba,
)
from modules.balance.razones import endeudamiento, liquidez
from tests.conftest import hacer_historial

CORTE = date(2024, 12, 31)
LARGO_PLAZO = [("obligaciones_financieras_cp", "obligaciones_financieras_lp", 600)]

# Hojas del balance de prueba
HOJAS = {
    "1105": 100, "1110": 200,            # efectivo 300
    "1305": 200,                         # clientes
    "1435": 50,                          # inventario
    "1516": 1_800, "1592": -300,         # construcciones menos depreciación acumulada
    "2105": -750,                        # obligaciones financieras (600 son de largo plazo)
    "2205": -120,                        # proveedores
    "3105": -1_000, "3705": -40,         # capital y utilidades acumuladas
    "4155": -1_000,                      # ingresos: hoteles y restaurantes
    "6155": 400,                         # costo de ventas
    "5105": 170, "5160": 80,             # gastos de administración (incluye depreciación)
    "5205": 100,                         # gastos de ventas
    "5305": 50,                          # gastos financieros
    "5405": 60,                          # impuesto de renta
}
# Filas padre como las exporta el software contable: no deben sumarse otra vez
PADRES = {"1": 2_050, "11": 300, "15": 1_500, "2": -870, "4": -1_000, "41": -1_000,
          "51": 250, "5": 460}


def balance_prueba(cambios: dict | None = None, padres: bool = True) -> pd.DataFrame:
    filas = {**HOJAS, **(PADRES if padres else {}), **(cambios or {})}
    return pd.DataFrame({"cuenta": list(filas), "saldo": list(filas.values())})


def test_hojas_descarta_filas_padre():
    h = hojas(balance_prueba())
    assert set(h["cuenta"]) == set(HOJAS)


def test_replica_la_empresa_de_referencia():
    ef = a_estado_financiero(balance_prueba(), CORTE, reclasificaciones=LARGO_PLAZO)
    b, r = ef.balance, ef.resultados
    assert b.efectivo == 300
    assert b.ppe == 1_500                    # la 1592 resta, no suma
    assert b.activo_total == 2_050
    assert b.pasivo_corriente == 270
    assert b.patrimonio_total == 1_180
    assert b.resultado_ejercicio == 140      # antes del cierre sale de las clases 4 a 6
    assert r.gastos_administracion == 250
    assert r.depreciacion_amortizacion == 80
    assert r.utilidad_neta == 140


def test_indicadores_iguales_a_los_de_la_referencia():
    referencia = hacer_historial()
    h = cargar_historial(referencia.empresa, {CORTE: balance_prueba()}, {CORTE: LARGO_PLAZO})
    for analisis in (liquidez, endeudamiento):
        esperado, obtenido = analisis(referencia), analisis(h)
        for ind in esperado.indicadores:
            assert obtenido.valor(ind.clave) == pytest.approx(ind.valor), ind.clave


def test_sin_reclasificar_la_deuda_queda_de_corto_plazo():
    ef = a_estado_financiero(balance_prueba(), CORTE)
    assert ef.balance.pasivo_corriente == 870
    assert any("porción de largo plazo" in s for s in ef.supuestos_carga)


def test_reclasificacion_queda_registrada():
    ef = a_estado_financiero(balance_prueba(), CORTE, reclasificaciones=LARGO_PLAZO)
    assert ef.balance.obligaciones_financieras_lp == 600
    assert ("Se reclasificaron $ 600 de obligaciones financieras de corto plazo a "
            "obligaciones financieras de largo plazo según información de la empresa."
            in ef.supuestos_carga)
    with pytest.raises(ErrorCarga, match="Reclasificación inválida"):
        a_estado_financiero(balance_prueba(), CORTE,
                            reclasificaciones=[("obligaciones_financieras_cp",
                                                "obligaciones_financieras_lp", 9_999)])


def test_saldos_sin_signo_se_rechazan():
    sin_signo = balance_prueba(padres=False)
    sin_signo["saldo"] = sin_signo["saldo"].abs()
    with pytest.raises(ErrorCarga, match="no suman cero"):
        a_estado_financiero(sin_signo, CORTE)


def test_balance_despues_del_cierre_se_rechaza():
    # Al cierre las clases 4 a 6 pasan a cero y la utilidad queda en la 36
    cierre = {c: 0 for c in HOJAS if c[0] in "456"} | {"3605": -140}
    with pytest.raises(ErrorCarga, match="ANTES del cierre"):
        a_estado_financiero(balance_prueba(cierre, padres=False), CORTE)


def test_depreciacion_no_encontrada_con_activos_fijos_es_desconocida():
    # Misma empresa, pero la depreciación se registró en otra cuenta de gastos
    ef = a_estado_financiero(balance_prueba({"5160": 0, "5195": 80}, padres=False), CORTE)
    assert ef.resultados.depreciacion_amortizacion is None
    assert ef.resultados.ebitda is None


def test_valorizaciones_se_ignoran_en_ambos_lados():
    ef = a_estado_financiero(balance_prueba({"1910": 500, "3805": -500}, padres=False), CORTE)
    assert ef.balance.activo_total == 2_050
    assert ef.balance.patrimonio_total == 1_180


def test_corte_intermedio_es_acumulado_del_anio():
    ef = a_estado_financiero(balance_prueba(), date(2024, 6, 30))
    assert ef.meses == 6


def test_cuenta_sin_mapeo_se_reporta():
    with pytest.raises(ErrorCarga, match="sin mapeo.*1099"):
        a_estado_financiero(balance_prueba({"1099": 10, "1105": 90}, padres=False), CORTE)


def test_lee_excel_con_columnas_debito_y_credito(tmp_path):
    df = balance_prueba()
    archivo = pd.DataFrame({
        "Código": df["cuenta"],
        "Nombre de la cuenta": "x",
        "Saldo Débito": df["saldo"].clip(lower=0),
        "Saldo Crédito": (-df["saldo"]).clip(lower=0),
    })
    ruta = tmp_path / "balance.xlsx"
    archivo.to_excel(ruta, index=False)
    leido = leer_balance_prueba(ruta)
    ef = a_estado_financiero(leido, CORTE)
    assert ef.balance.activo_total == 2_050


def test_lee_csv_con_saldo_y_formato_de_moneda(tmp_path):
    df = balance_prueba()
    ruta = tmp_path / "balance.csv"
    pd.DataFrame({"Cuenta": df["cuenta"], "Saldo final": [f"$ {v}" for v in df["saldo"]]}
                 ).to_csv(ruta, index=False)
    assert a_estado_financiero(leer_balance_prueba(ruta), CORTE).balance.activo_total == 2_050


def test_columnas_no_reconocidas(tmp_path):
    ruta = tmp_path / "balance.csv"
    pd.DataFrame({"Descripción": ["Caja"], "Valor": [100]}).to_csv(ruta, index=False)
    with pytest.raises(ErrorCarga, match="código de cuenta"):
        leer_balance_prueba(ruta)


def test_historial_de_dos_anios():
    referencia = hacer_historial()
    # 2023: 100 menos en bancos y 100 menos de ingresos (sigue cuadrando)
    anterior = balance_prueba({"1110": 100, "4155": -900}, padres=False)
    h = cargar_historial(referencia.empresa, {CORTE: balance_prueba(),
                                             date(2023, 12, 31): anterior})
    assert [p.fecha_corte.year for p in h.periodos] == [2023, 2024]
    assert h.saldo_promedio("efectivo") == (250, True)


def test_reclasificar_anula_el_supuesto_de_plazo():
    ef = a_estado_financiero(balance_prueba(), CORTE, reclasificaciones=LARGO_PLAZO)
    assert not any("porción de largo plazo" in s for s in ef.supuestos_carga)


def test_balance_de_prueba_completo_no_advierte_cuentas_faltantes():
    ef = a_estado_financiero(balance_prueba(), CORTE, reclasificaciones=LARGO_PLAZO)
    assert not any("no reportadas" in a for a in ef.advertencias())


def test_lee_archivo_abierto_y_rechaza_formatos(tmp_path):
    import io
    df = balance_prueba()
    contenido = pd.DataFrame({"Cuenta": df["cuenta"], "Saldo": df["saldo"]}).to_csv(index=False)
    leido = leer_balance_prueba(io.BytesIO(contenido.encode("utf-8")), nombre="subido.csv")
    assert a_estado_financiero(leido, CORTE).balance.activo_total == 2_050
    with pytest.raises(ErrorCarga, match="Formato no soportado"):
        leer_balance_prueba(io.BytesIO(b"x"), nombre="balance.pdf")
    with pytest.raises(ErrorCarga, match="No se pudo leer"):
        leer_balance_prueba(io.BytesIO(b"\x00\x01basura"), nombre="balance.xlsx")
