"""Series externas: transformación, operaciones y catálogo. Ningún test toca la red."""
import io
import json
from datetime import date
from pathlib import Path

import openpyxl
import pytest
import requests

from data_sources.externos.series import banrep, catalogo, dane
from data_sources.externos.series.catalogo import ErrorSerie, serie, verificar
from data_sources.externos.series.modelo import Serie

DATOS = Path(__file__).parent / "datos"
HOY = date(2026, 10, 11)


def suameca(nombre: str) -> dict:
    """Respuesta real de SUAMECA, recortada (inicio de la serie + 2023-2024)."""
    return json.loads((DATOS / f"suameca_ipc_{nombre}.json").read_text(encoding="utf-8"))[0]


def suameca_tasa(clave: str) -> dict:
    """Respuesta real de SUAMECA del 12/10/2026, recortada: último dato de cada mes y
    la historia diaria del último mes."""
    return json.loads((DATOS / f"suameca_{clave}.json").read_text(encoding="utf-8"))[0]


def hacer_serie(obs: list[tuple[date, float]], **campos) -> Serie:
    base = dict(clave="x", nombre="x", fuente="x", unidad="x", frecuencia="mensual",
                geografia="nacional", consultada=HOY)
    return Serie(**{**base, **campos}, observaciones=obs)


# --------------------------------------------------------------------------- #
# Transformación
# --------------------------------------------------------------------------- #
def test_suameca_fechas_fin_de_mes_incluso_antes_de_1970():
    s = banrep.desde_suameca(suameca("nacional"), "ipc_nacional", "nacional", HOY)
    assert s.observaciones[0] == (date(1954, 7, 31), 0.03)
    assert s.observaciones[-1] == (date(2024, 12, 31), 144.88)
    assert s.frecuencia == "mensual"
    assert "serie 15000" in s.fuente and "DANE" in s.fuente


def test_suameca_ignora_valores_vacios():
    respuesta = suameca("pasto")
    respuesta["data"].append([1735707600000, None])
    s = banrep.desde_suameca(respuesta, "ipc_pasto", "Pasto", HOY)
    assert len(s.observaciones) == 26


def test_serie_ordena_y_deja_el_ultimo_repetido():
    s = hacer_serie([(date(2024, 2, 29), 2.0), (date(2024, 1, 31), 1.0), (date(2024, 2, 29), 3.0)])
    assert s.observaciones == [(date(2024, 1, 31), 1.0), (date(2024, 2, 29), 3.0)]


def anexo_dane() -> bytes:
    """Hoja con la forma del anexo real: títulos, fila 'Mes' con años, meses en filas."""
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append(["Total, Índice de Precios al Consumidor (IPC)"])
    hoja.append([None, None, None, "Base Diciembre de 2018 = 100,00"])
    hoja.append(["Mes", 2023, 2024, 2025, None])
    hoja.append(["Enero", 128.27, 138.98, 146.24])
    hoja.append(["Febrero", 130.4, 140.49, None])   # 2025 aún no publicado
    hoja.append(["Fuente: DANE"])
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def test_anexo_dane_a_serie():
    s = dane.desde_anexo(anexo_dane(), HOY)
    assert s.observaciones == [(date(2023, 1, 31), 128.27), (date(2023, 2, 28), 130.4),
                               (date(2024, 1, 31), 138.98), (date(2024, 2, 29), 140.49),
                               (date(2025, 1, 31), 146.24)]


def test_anexo_sin_tabla_es_error():
    libro = openpyxl.Workbook()
    salida = io.BytesIO()
    libro.save(salida)
    with pytest.raises(ValueError, match="tabla de índices"):
        dane.desde_anexo(salida.getvalue(), HOY)


# --------------------------------------------------------------------------- #
# Operaciones
# --------------------------------------------------------------------------- #
def test_promedio_mensual_a_mano():
    s = hacer_serie([(date(2024, 1, 31), 100), (date(2024, 2, 29), 102), (date(2024, 3, 31), 104)])
    assert s.promedio_mensual(date(2024, 1, 1), date(2024, 3, 31)) == 102
    assert s.promedio_mensual(date(2024, 2, 1), date(2024, 3, 31)) == 103


def test_promedio_con_meses_faltantes_es_none():
    s = hacer_serie([(date(2024, 1, 31), 100), (date(2024, 3, 31), 104)])
    assert s.promedio_mensual(date(2024, 1, 1), date(2024, 3, 31)) is None


def test_inflacion_promedio_2024_con_datos_reales():
    """6,61 % nacional: el cálculo hecho al averiguar los ids (11/10/2026)."""
    s = banrep.desde_suameca(suameca("nacional"), "ipc_nacional", "nacional", HOY)
    inflacion = (s.promedio_mensual(date(2024, 1, 1), date(2024, 12, 31))
                 / s.promedio_mensual(date(2023, 1, 1), date(2023, 12, 31)) - 1)
    assert round(inflacion * 100, 2) == 6.61


def test_valor_al_es_el_ultimo_dato_en_o_antes_de_la_fecha():
    s = hacer_serie([(date(2024, 1, 2), 10.0), (date(2024, 1, 5), 10.5), (date(2024, 2, 1), 11.0)],
                    frecuencia="diaria")
    assert s.valor_al(date(2024, 1, 5)) == 10.5
    assert s.valor_al(date(2024, 1, 31)) == 10.5      # sin dato ese día: el anterior
    assert s.valor_al(date(2030, 1, 1)) == 11.0
    assert s.valor_al(date(2024, 1, 1)) is None       # antes de que empiece la serie


def test_fin_de_mes_deja_el_ultimo_dato_de_cada_mes():
    s = hacer_serie([(date(2024, 1, 2), 10.0), (date(2024, 1, 30), 10.5), (date(2024, 2, 1), 11.0),
                     (date(2024, 2, 28), 11.5)], frecuencia="diaria")
    assert s.fin_de_mes() == [(date(2024, 1, 30), 10.5), (date(2024, 2, 28), 11.5)]


def test_tasa_de_politica_real():
    """12,25 % al 12/10/2026 y 9,25 % un año antes (consultado al averiguar los ids)."""
    s = banrep.desde_suameca(suameca_tasa("tasa_politica"), "tasa_politica_nacional",
                             "nacional", HOY)
    assert s.unidad == "Tasa efectiva anual base 365."
    assert s.observaciones[-1] == (date(2026, 10, 12), 12.25)
    assert s.valor_al(date(2025, 10, 12)) == 9.25


def test_verificar():
    a = hacer_serie([(date(2024, 1, 31), 138.98), (date(2024, 2, 29), 140.49)])
    b = hacer_serie([(date(2024, 1, 31), 138.98), (date(2024, 2, 29), 140.5)])
    assert verificar(a, a) == []
    assert verificar(a, b) == ["2024-02: BanRep 140.49, DANE 140.5"]


# --------------------------------------------------------------------------- #
# Catálogo
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def respaldo_vacio(monkeypatch, tmp_path):
    """Ningún test lee las copias versionadas de data/series/."""
    monkeypatch.setattr(catalogo, "RESPALDO", tmp_path / "respaldo")


@pytest.fixture
def descargas(monkeypatch):
    """SUAMECA falso: responde con los fixtures y anota cada id pedido."""
    pedidas = []
    respuestas = {15000: "nacional", 15026: "pasto"}
    tasas = {59: "tasa_politica", 243: "ibr_3m"}

    def descargar(id_serie):
        pedidas.append(id_serie)
        if id_serie in tasas:
            return suameca_tasa(tasas[id_serie])
        if id_serie in respuestas:
            return suameca(respuestas[id_serie])
        return {**suameca_tasa("ibr_3m"), "id": id_serie}   # TRM, PIB, desempleo: basta la forma

    monkeypatch.setattr(banrep, "descargar", descargar)
    return pedidas


def sin_red(monkeypatch):
    def falla(id_serie):
        raise requests.ConnectionError("sin conexión")
    monkeypatch.setattr(banrep, "descargar", falla)


def test_ciudad_disponible(tmp_path, descargas):
    s = serie("ipc", "pasto", desde=date(2023, 1, 1), hoy=HOY, directorio=tmp_path)
    assert s.geografia == "Pasto" and s.clave == "ipc_pasto"
    assert s.supuestos == []
    assert descargas == [15026]


def test_ciudad_sin_serie_usa_nacional_con_supuesto(tmp_path, descargas):
    s = serie("ipc", "Ipiales", hoy=HOY, directorio=tmp_path)
    assert s.geografia == "nacional"
    assert s.supuestos == ["Se usó el IPC nacional porque no hay IPC de Ipiales."]


def test_ciudad_que_no_cubre_las_fechas_usa_nacional(tmp_path, descargas):
    s = serie("ipc", "Pasto", desde=date(2016, 1, 1), hoy=HOY, directorio=tmp_path)
    assert s.geografia == "nacional"
    assert s.supuestos == ["Se usó el IPC nacional porque el IPC de Pasto empieza en "
                           "enero de 2017."]


def test_sin_ciudad_usa_nacional(tmp_path, descargas):
    s = serie("ipc", None, hoy=HOY, directorio=tmp_path)
    assert s.supuestos == ["Se usó el IPC nacional porque no se conoce la ciudad de la empresa."]


def test_nacional_pedido_no_lleva_supuesto(tmp_path, descargas):
    assert serie("ipc", "Nacional", hoy=HOY, directorio=tmp_path).supuestos == []


def test_copia_del_dia_no_descarga(tmp_path, descargas):
    serie("ipc", "Pasto", hoy=HOY, directorio=tmp_path)
    serie("ipc", "Pasto", hoy=HOY, directorio=tmp_path)
    assert descargas == [15026]
    serie("ipc", "Pasto", hoy=date(2026, 10, 12), directorio=tmp_path)
    assert descargas == [15026, 15026]


def test_la_descarga_va_a_la_copia_del_dia_y_no_al_respaldo(tmp_path, descargas):
    serie("ipc", "Pasto", hoy=HOY, directorio=catalogo.RESPALDO)
    serie("ipc", "Pasto", hoy=date(2026, 10, 15), directorio=tmp_path)
    assert descargas == [15026, 15026]
    assert Serie.model_validate_json((tmp_path / "ipc_pasto.json").read_text(
        encoding="utf-8")).consultada == date(2026, 10, 15)
    assert Serie.model_validate_json((catalogo.RESPALDO / "ipc_pasto.json").read_text(
        encoding="utf-8")).consultada == HOY


def test_sin_copia_del_dia_y_sin_red_usa_el_respaldo(tmp_path, descargas, monkeypatch):
    serie("ipc", "Pasto", hoy=HOY, directorio=catalogo.RESPALDO)
    sin_red(monkeypatch)
    s = serie("ipc", "Pasto", hoy=date(2026, 10, 15), directorio=tmp_path)
    assert len(s.observaciones) == 26
    assert s.advertencias == ["No se pudo actualizar la serie ipc_pasto; se usaron los datos "
                              "consultados el 11/10/2026."]


def test_actualizar_descarga_todas_las_nacionales_aunque_esten_vigentes(tmp_path, descargas):
    serie("tasa_politica", hoy=HOY, directorio=tmp_path)
    assert catalogo.actualizar(hoy=HOY, directorio=tmp_path) == []
    assert descargas == [59, 15000, 59, 243, 1, 15271, 15312, 853, 15277]


def test_actualizar_sin_red_dice_que_no_pudo(tmp_path, descargas, monkeypatch):
    serie("tasa_politica", hoy=HOY, directorio=tmp_path)
    sin_red(monkeypatch)
    problemas = catalogo.actualizar(hoy=HOY, directorio=tmp_path)
    assert len(problemas) == 8 and all(p.startswith("No se pudo") for p in problemas)


def test_la_copia_no_guarda_supuestos(tmp_path, descargas):
    serie("ipc", "Ipiales", hoy=HOY, directorio=tmp_path)
    assert "supuestos" not in (tmp_path / "ipc_nacional.json").read_text(encoding="utf-8")


def test_sin_red_usa_copia_vieja_con_advertencia(tmp_path, descargas, monkeypatch):
    serie("ipc", "Pasto", hoy=HOY, directorio=tmp_path)
    sin_red(monkeypatch)
    s = serie("ipc", "Pasto", hoy=date(2026, 12, 1), directorio=tmp_path)
    assert len(s.observaciones) == 26
    assert s.advertencias == ["No se pudo actualizar la serie ipc_pasto; se usaron los datos "
                              "consultados el 11/10/2026."]


def test_sin_red_y_sin_copia_es_error_util(tmp_path, monkeypatch):
    sin_red(monkeypatch)
    with pytest.raises(ErrorSerie, match="Revise la conexión"):
        serie("ipc", "Pasto", hoy=HOY, directorio=tmp_path)


def test_tildes_y_mayusculas_no_importan():
    assert catalogo._buscar("ipc", "BOGOTA") == ("Bogotá", 15013)
    assert catalogo._buscar("ipc", " cúcuta ") == ("Cúcuta", 15020)


@pytest.mark.parametrize("variable, id_serie", [("tasa_politica", 59), ("ibr_3m", 243),
                                               ("meta_inflacion", 853)])
def test_tasas_son_nacionales_sin_supuesto(tmp_path, descargas, variable, id_serie):
    s = serie(variable, hoy=HOY, directorio=tmp_path)
    assert descargas == [id_serie]
    assert s.clave == f"{variable}_nacional" and s.supuestos == []
    assert (tmp_path / f"{variable}_nacional.json").exists()
