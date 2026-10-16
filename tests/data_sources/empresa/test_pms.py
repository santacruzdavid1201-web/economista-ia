"""Cargador del PMS (SPEC-series-empresa.md): formatos reales de exportación."""
import io
from datetime import date

import pandas as pd
import pytest

from data_sources.empresa.pms import ErrorPMS, leer_archivo_pms
from data_sources.empresa.pms_simulado import parametros, simular_pms


def como_csv(df: pd.DataFrame, **opciones) -> io.BytesIO:
    return io.BytesIO(df.to_csv(index=False, **opciones).encode(opciones.pop("encoding", "utf-8")))


def test_ida_y_vuelta_con_el_simulado():
    simulado = simular_pms(parametros(), semilla=1).head(60)
    leido = leer_archivo_pms(como_csv(simulado), "pms.csv")
    pd.testing.assert_frame_equal(leido, simulado, check_dtype=False)


def test_exportacion_en_ingles_con_punto_y_coma_y_numeros_colombianos():
    texto = ("Hotel Demo Andino;;;;;\n"
             "Reporte diario de ocupación;;;;;\n"
             "Date;Rooms Available;Rooms Sold;Room Revenue;Rate;Promo\n"
             "05/01/2026;45;45;\"10.125.000,00\";\"240.000,00\";No\n"
             "06/01/2026;44;43;\"9.546.000,00\";\"235.000,00\";Sí\n")
    df = leer_archivo_pms(io.BytesIO(texto.encode("cp1252")), "export.csv")
    assert list(df["fecha"]) == [date(2026, 1, 5), date(2026, 1, 6)]
    assert list(df["habitaciones_vendidas"]) == [45, 43]
    assert list(df["ingresos_habitaciones"]) == [10_125_000.0, 9_546_000.0]
    assert list(df["tarifa_publicada"]) == [240_000.0, 235_000.0]
    assert list(df["promocion"]) == [False, True]
    assert df["huespedes"].isna().all() and df["tarifa_competencia"].isna().all()


def test_excel():
    simulado = simular_pms(parametros(), semilla=1).head(10)
    archivo = io.BytesIO()
    simulado.rename(columns={"habitaciones_vendidas": "Habitaciones ocupadas",
                             "ingresos_habitaciones": "Ingresos alojamiento"}).to_excel(
        archivo, index=False)
    archivo.seek(0)
    leido = leer_archivo_pms(archivo, "pms.xlsx")
    assert list(leido["habitaciones_vendidas"]) == list(simulado["habitaciones_vendidas"])
    assert list(leido["fecha"]) == list(simulado["fecha"])


def test_falta_una_columna_obligatoria():
    sin_ingresos = simular_pms(parametros(), semilla=1).head(5).drop(columns="ingresos_habitaciones")
    with pytest.raises(ErrorPMS, match="ingresos de habitaciones"):
        leer_archivo_pms(como_csv(sin_ingresos), "pms.csv")


def test_mas_vendidas_que_disponibles_dice_la_fila_y_la_fecha():
    malo = simular_pms(parametros(), semilla=1).head(5)
    malo.loc[2, "habitaciones_vendidas"] = 50
    with pytest.raises(ErrorPMS, match=r"fila 4 \(03/01/2023\)") as e:
        leer_archivo_pms(como_csv(malo), "pms.csv")
    assert "más habitaciones" in str(e.value)


@pytest.mark.parametrize("cambio, mensaje", [
    ({"fecha": "32/01/2023"}, r"Fila 2: la fecha «32/01/2023» no es válida"),
    ({"habitaciones_vendidas": "muchas"}, r"Fila 2: «muchas» no es un número"),
])
def test_valores_que_no_sirven(cambio, mensaje):
    malo = simular_pms(parametros(), semilla=1).head(3).astype(object)
    for columna, valor in cambio.items():
        malo.loc[0, columna] = valor
    with pytest.raises(ErrorPMS, match=mensaje):
        leer_archivo_pms(como_csv(malo), "pms.csv")


def test_fecha_repetida():
    repetido = pd.concat([simular_pms(parametros(), semilla=1).head(2)] * 2)
    with pytest.raises(ErrorPMS, match="aparece más de una vez"):
        leer_archivo_pms(como_csv(repetido), "pms.csv")


def test_archivo_sin_encabezado_reconocible():
    with pytest.raises(ErrorPMS, match="No se encontró el encabezado"):
        leer_archivo_pms(io.BytesIO(b"a,b,c\n1,2,3\n"), "otro.csv")


@pytest.mark.parametrize("fechas, esperadas", [
    (["2023-01-02", "2023-01-13"], [date(2023, 1, 2), date(2023, 1, 13)]),     # ISO: sin dudas
    (["02/01/2023", "13/01/2023"], [date(2023, 1, 2), date(2023, 1, 13)]),     # día primero
    (["01/02/2023", "01/13/2023"], [date(2023, 1, 2), date(2023, 1, 13)]),     # PMS en inglés
    (["05/01/2026", "06/01/2026"], [date(2026, 1, 5), date(2026, 1, 6)]),      # ambiguo: Colombia
])
def test_el_orden_de_las_fechas_se_decide_con_toda_la_columna(fechas, esperadas):
    encabezado = "fecha,habitaciones disponibles,habitaciones vendidas,ingresos habitaciones\n"
    texto = encabezado + "".join(f"{f},45,10,1500000\n" for f in fechas)
    assert list(leer_archivo_pms(io.BytesIO(texto.encode()), "pms.csv")["fecha"]) == esperadas
