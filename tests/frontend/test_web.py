"""Interfaz web con TestClient y un modelo falso: páginas, chat global y carga de balances."""
import json
import re
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.llm.client import LlamadaHerramienta, RespuestaLLM
from app.main import app
from frontend import web

DEMO = Path(__file__).parents[2] / "data" / "demo"


class LLMFalso:
    """Responde en orden lo que se le guionó; informa que está disponible."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.usuarios: list[str] = []

    def chat(self, sistema, usuario, herramientas=None, forzar_herramienta=False, temperatura=0.2):
        self.usuarios.append(usuario)
        return self.respuestas.pop(0)

    def disponible(self):
        return True, "Modelo de prueba disponible."


def herramienta(nombre, **args):
    return RespuestaLLM(herramientas=[LlamadaHerramienta(nombre, args)])


@pytest.fixture
def llm():
    falso = LLMFalso()
    app.dependency_overrides[web.cliente_llm] = lambda: falso
    yield falso
    app.dependency_overrides.clear()


@pytest.fixture
def cliente(llm):
    web._SESIONES.clear()
    return TestClient(app)


def pid_de(html: str) -> str:
    return re.search(r'hx-get="/respuesta/([^"]+)"', html)[1]


# --------------------------------------------------------------------------- #
# Páginas
# --------------------------------------------------------------------------- #
def test_portada_con_la_empresa_y_los_modulos(cliente):
    r = cliente.get("/")
    assert r.status_code == 200 and web.COOKIE in r.cookies
    assert "Hotel Demo Andino S.A.S." in r.text and "Empresa ficticia de demostración" in r.text
    assert 'href="/modulo/balance"' in r.text and 'href="/modulo/macro"' in r.text
    assert r.text.count("Próximamente") == 2
    assert '<table class="libro">' in r.text


def test_modulo_activo_tiene_ejemplos_que_van_al_chat(cliente):
    r = cliente.get("/modulo/balance")
    assert r.status_code == 200
    assert "¿Cómo está mi empresa?" in r.text and 'hx-post="/preguntar"' in r.text


def test_el_chat_esta_en_todas_las_paginas(cliente):
    for url in ("/", "/modulo/balance", "/modulo/macro", "/modulo/proyectos"):
        assert 'id="chat"' in cliente.get(url).text


def test_modulo_inactivo_en_construccion(cliente):
    r = cliente.get("/modulo/proyectos")
    assert r.status_code == 200 and "en construcción" in r.text


def test_modulo_desconocido(cliente):
    assert cliente.get("/modulo/astrologia").status_code == 404


def test_estado_del_modelo(cliente):
    assert "Modelo listo" in cliente.get("/estado-modelo").text


# --------------------------------------------------------------------------- #
# Conversación
# --------------------------------------------------------------------------- #
def test_preguntar_y_recibir_la_respuesta(cliente, llm):
    llm.respuestas += [herramienta("analizar_liquidez", periodo=2024),
                       RespuestaLLM(texto="Puede pagar sus deudas de corto plazo.")]
    r = cliente.post("/preguntar", data={"pregunta": "¿Puedo pagar mis deudas?"})
    assert "¿Puedo pagar mis deudas?" in r.text and "Analizando" in r.text
    r = cliente.get(f"/respuesta/{pid_de(r.text)}")
    assert '<article class="respuesta">' in r.text
    assert "<p>Puede pagar sus deudas de corto plazo.</p>" in r.text
    assert "De dónde salen las cifras" in r.text and "Razón corriente" in r.text
    # Una sola conversación: se ve desde cualquier página y en el fragmento del chat
    assert "¿Puedo pagar mis deudas?" in cliente.get("/modulo/macro").text
    assert "Puede pagar sus deudas" in cliente.get("/chat").text


def test_la_conversacion_previa_llega_al_modelo(cliente, llm):
    llm.respuestas += [herramienta("analizar_liquidez"), RespuestaLLM(texto="Puede pagar."),
                       herramienta("conversar"), RespuestaLLM(texto="Con gusto.")]
    for pregunta in ("¿Puedo pagar mis deudas?", "Gracias"):
        r = cliente.post("/preguntar", data={"pregunta": pregunta})
        cliente.get(f"/respuesta/{pid_de(r.text)}")
    assert llm.usuarios[0] == "¿Puedo pagar mis deudas?"
    assert "Cliente: ¿Puedo pagar mis deudas?" in llm.usuarios[2]


def test_la_respuesta_marca_las_cifras_calculadas(cliente, llm):
    from modules.balance.razones import liquidez
    from modules.base import formatear
    ctx = web._demo()
    rc = liquidez(ctx.historial).valor("razon_corriente")
    llm.respuestas += [herramienta("analizar_liquidez", periodo=2024),
                       RespuestaLLM(texto=f"Su razón corriente es {formatear(rc, 'veces')}.")]
    r = cliente.post("/preguntar", data={"pregunta": "¿Liquidez?"})
    r = cliente.get(f"/respuesta/{pid_de(r.text)}")
    assert 'class="cifra" tabindex="0" data-origen="Razón corriente.' in r.text


def test_la_pregunta_y_la_respuesta_se_escapan(cliente, llm):
    llm.respuestas += [herramienta("analizar_liquidez"),
                       RespuestaLLM(texto='<img src=x onerror="alert(1)">Todo bien.')]
    r = cliente.post("/preguntar", data={"pregunta": "<script>alert(1)</script>"})
    assert "<script>alert(1)</script>" not in r.text and "&lt;script&gt;" in r.text
    r = cliente.get(f"/respuesta/{pid_de(r.text)}")
    assert "<img" not in r.text and "&lt;img" in r.text


def test_respuesta_que_ya_no_existe(cliente):
    r = cliente.get("/respuesta/inventada")
    assert r.status_code == 200 and "ya no está disponible" in r.text


def test_cada_sesion_tiene_su_conversacion(llm):
    web._SESIONES.clear()
    a, b = TestClient(app), TestClient(app)
    llm.respuestas += [herramienta("analizar_liquidez"), RespuestaLLM(texto="Bien.")]
    r = a.post("/preguntar", data={"pregunta": "Pregunta de A"})
    a.get(f"/respuesta/{pid_de(r.text)}")
    assert "Pregunta de A" not in b.get("/chat").text
    # Otra sesión no puede pedir respuestas ajenas
    r = a.post("/preguntar", data={"pregunta": "Otra de A"})
    assert "ya no está disponible" in b.get(f"/respuesta/{pid_de(r.text)}").text


# --------------------------------------------------------------------------- #
# Empresa
# --------------------------------------------------------------------------- #
def csv_demo(anio: int) -> tuple[str, bytes, str]:
    nombre = f"hotel_demo_andino_{anio}.csv"
    return nombre, (DEMO / nombre).read_bytes(), "text/csv"


def subir(cliente, archivos, **campos):
    datos = {"razon_social": "Hotel Mío S.A.S.", "ciiu": "5511", "unidad": "pesos", **campos}
    return cliente.post("/empresa/archivos", data=datos,
                        files=[("archivos", a) for a in archivos])


def test_carga_en_dos_pasos(cliente):
    r = subir(cliente, [csv_demo(2023), csv_demo(2024)])
    assert 'name="fecha_0" value="2023-12-31"' in r.text
    assert 'name="fecha_1" value="2024-12-31"' in r.text
    r = cliente.post("/empresa/cargar", data={"fecha_0": "2023-12-31", "fecha_1": "2024-12-31",
                                              "r0_0": "0", "r0_1": "520000000"})
    assert r.status_code == 204
    assert json.loads(r.headers["HX-Location"])["path"] == "/"
    portada = cliente.get("/").text
    assert "Hotel Mío S.A.S." in portada and "Empresa ficticia" not in portada


def test_errores_del_paso_1(cliente):
    r = cliente.post("/empresa/archivos", data={"razon_social": " ", "ciiu": "55"})
    for error in ("Escriba la razón social.", "El CIIU debe tener 4 dígitos.",
                  "Suba al menos un balance de prueba."):
        assert error in r.text
    r = subir(cliente, [("balance.pdf", b"%PDF", "application/pdf")])
    assert "balance.pdf: el archivo debe ser .csv, .xlsx o .xls." in r.text


def test_errores_del_paso_2(cliente):
    subir(cliente, [csv_demo(2023), csv_demo(2024)])
    r = cliente.post("/empresa/cargar", data={"fecha_0": "2024-12-31", "fecha_1": "2024-12-31",
                                              "r0_0": "-5"})
    assert "Cada archivo debe tener una fecha de corte distinta." in r.text
    assert "debe ser un número positivo o cero" in r.text
    assert 'name="fecha_0" value="2024-12-31"' in r.text     # conserva lo escrito


def test_cargar_sin_paso_1(cliente):
    assert "Vuelva a subir los archivos" in cliente.post("/empresa/cargar", data={}).text


def test_volver_al_hotel_de_demostracion(cliente):
    subir(cliente, [csv_demo(2024)])
    cliente.post("/empresa/cargar", data={"fecha_0": "2024-12-31"})
    assert "Hotel Mío S.A.S." in cliente.get("/").text
    r = cliente.post("/empresa/demo")
    assert r.status_code == 204 and r.headers["HX-Trigger"] == "empresa-cambiada"
    assert "Hotel Demo Andino S.A.S." in cliente.get("/").text


def test_cambiar_de_empresa_vacia_el_chat(cliente, llm):
    llm.respuestas += [herramienta("conversar"), RespuestaLLM(texto="Hola.")]
    r = cliente.post("/preguntar", data={"pregunta": "Hola"})
    cliente.get(f"/respuesta/{pid_de(r.text)}")
    cliente.post("/empresa/demo")
    assert "¿en qué le ayudo?" in cliente.get("/chat").text


def test_corte_sugerido():
    assert web.corte_sugerido("balance_2015-06-30.csv") == date(2015, 6, 30)
    assert web.corte_sugerido("cierre 2016.xlsx") == date(2016, 12, 31)
    assert web.corte_sugerido("balance_2015-02-30.csv") == date(2015, 12, 31)
