"""Interfaz web con TestClient y un modelo falso: páginas, chat global y carga de balances."""
import re
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.demo import contexto_demo
from app.llm.client import LlamadaHerramienta, RespuestaLLM
from app.main import app
from frontend import web
from modules.base import formatear

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


def csv_demo(anio: int) -> tuple[str, bytes, str]:
    nombre = f"hotel_demo_andino_{anio}.csv"
    return nombre, (DEMO / nombre).read_bytes(), "text/csv"


def subir(cliente, archivos, **campos):
    datos = {"razon_social": "Hotel Mío S.A.S.", "ciiu": "5511", "unidad": "pesos", **campos}
    return cliente.post("/empresa", data=datos, files=[("archivos", a) for a in archivos])


def sesion_unica() -> web.Sesion:
    (s,) = web._SESIONES.values()
    return s


@pytest.fixture
def empresa(cliente):
    subir(cliente, [csv_demo(2023), csv_demo(2024)])


# --------------------------------------------------------------------------- #
# Páginas
# --------------------------------------------------------------------------- #
def test_portada_sin_empresa_y_con_los_modulos(cliente):
    r = cliente.get("/")
    assert r.status_code == 200 and web.COOKIE in r.cookies
    assert "Sin empresa" in r.text and "Hotel Demo Andino" not in r.text
    assert 'id="empresa"' in r.text and "Suba al menos un balance de prueba." in r.text
    assert 'href="/modulo/balance"' in r.text and 'href="/modulo/macro"' in r.text
    assert r.text.count("Próximamente") == 1


def test_modulo_activo_tiene_ejemplos_que_van_al_chat(cliente):
    r = cliente.get("/modulo/balance")
    assert r.status_code == 200
    assert "¿Cómo está mi empresa?" in r.text and 'hx-post="/preguntar"' in r.text


def test_el_chat_esta_en_todas_las_paginas(cliente):
    for url in ("/", "/modulo/balance", "/modulo/macro", "/modulo/proyectos"):
        assert 'id="chat"' in cliente.get(url).text


def test_la_hoja_de_estilos_lleva_su_version(cliente):
    # Sin versión el navegador reutilizaba una hoja de estilos vieja (el chat salió sin estilos)
    html = cliente.get("/").text
    assert re.search(r'href="/static/estilo\.css\?v=\d+"', html)
    assert cliente.get(re.search(r'href="(/static/estilo\.css\?v=\d+)"', html)[1]).status_code == 200


def test_tablero_de_balance(cliente):
    assert "Aún no hay estados financieros" in cliente.get("/modulo/balance").text
    subir(cliente, [csv_demo(2023), csv_demo(2024)])
    r = cliente.get("/modulo/balance").text
    for parte in ("Frente al sector", "Por qué cambió la rentabilidad del patrimonio",
                  "Indicadores por año", 'class="pista-punto"', "frente a 2023"):
        assert parte in r, parte
    macro = cliente.get("/modulo/macro").text
    assert "La economía colombiana" in macro and "¿Cómo le afectan las tasas de interés?" in macro


def test_tablero_macro_sin_empresa(cliente):
    r = cliente.get("/modulo/macro").text
    assert "Inflación anual" in r and "Dólar (TRM)" in r and "<polyline" in r
    assert "Subir estados financieros" in r
    assert "Datos consultados el 11/10/2026" in r


def test_modulo_inactivo_en_construccion(cliente):
    r = cliente.get("/modulo/econometria")
    assert r.status_code == 200 and "en construcción" in r.text


def test_modulo_desconocido(cliente):
    assert cliente.get("/modulo/astrologia").status_code == 404


def test_estado_del_modelo(cliente):
    assert "Modelo listo" in cliente.get("/estado-modelo").text


# --------------------------------------------------------------------------- #
# Conversación
# --------------------------------------------------------------------------- #
def test_preguntar_y_recibir_la_respuesta(cliente, llm, empresa):
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


def test_la_conversacion_previa_llega_al_modelo(cliente, llm, empresa):
    llm.respuestas += [herramienta("analizar_liquidez"), RespuestaLLM(texto="Puede pagar."),
                       herramienta("conversar"), RespuestaLLM(texto="Con gusto.")]
    for pregunta in ("¿Puedo pagar mis deudas?", "Gracias"):
        r = cliente.post("/preguntar", data={"pregunta": pregunta})
        cliente.get(f"/respuesta/{pid_de(r.text)}")
    assert llm.usuarios[0] == "¿Puedo pagar mis deudas?"
    assert "Cliente: ¿Puedo pagar mis deudas?" in llm.usuarios[2]


def test_la_respuesta_marca_las_cifras_calculadas(cliente, llm, empresa):
    from modules.balance.razones import liquidez
    rc = liquidez(sesion_unica().ctx.historial).valor("razon_corriente")
    llm.respuestas += [herramienta("analizar_liquidez", periodo=2024),
                       RespuestaLLM(texto=f"Su razón corriente es {formatear(rc, 'veces')}.")]
    r = cliente.post("/preguntar", data={"pregunta": "¿Liquidez?"})
    r = cliente.get(f"/respuesta/{pid_de(r.text)}")
    assert 'class="cifra" tabindex="0" data-origen="Razón corriente.' in r.text


def test_la_pregunta_y_la_respuesta_se_escapan(cliente, llm, empresa):
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
    subir(a, [csv_demo(2024)])
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
def test_al_subir_un_archivo_muestra_activo_pasivo_y_patrimonio(cliente):
    r = subir(cliente, [csv_demo(2024)])
    b = contexto_demo().historial.ultimo.balance       # mismo archivo: mismos totales
    for valor in (b.activo_total, b.pasivo_total, b.patrimonio_total):
        assert formatear(valor, "pesos") in r.text
    assert 'name="fecha_0" value="2024-12-31"' in r.text
    assert "Listo: estados financieros de 2024" in r.text
    # El nombre de la barra superior se actualiza fuera de banda
    assert 'id="chip-empresa"' in r.text and 'hx-swap-oob="true"' in r.text
    assert "Hotel Mío S.A.S." in cliente.get("/modulo/balance").text


def test_los_archivos_se_suman_de_a_uno_y_en_orden(cliente):
    subir(cliente, [csv_demo(2024)])
    r = subir(cliente, [csv_demo(2023)], fecha_0="2024-12-31")
    assert r.text.index("hotel_demo_andino_2023.csv") < r.text.index("hotel_demo_andino_2024.csv")
    assert "Listo: estados financieros de 2023 y 2024" in r.text
    assert [p.fecha_corte.year for p in sesion_unica().ctx.historial.periodos] == [2023, 2024]


def test_un_archivo_con_error_no_impide_los_demas(cliente):
    roto = ("roto_2023.csv", "cuenta;saldo\n1105;100\n4135;-40\n".encode(), "text/csv")
    r = subir(cliente, [csv_demo(2024), roto])
    assert 'class="archivo-error"' in r.text and "no suman cero" in r.text
    assert "Listo: estados financieros de 2024" in r.text


def test_sin_razon_social_ni_ciiu_igual_lee_los_archivos(cliente):
    r = subir(cliente, [csv_demo(2024)], razon_social=" ", ciiu="55")
    assert "falta la razón social y el código CIIU de 4 dígitos" in r.text
    assert formatear(contexto_demo().historial.ultimo.balance.activo_total, "pesos") in r.text
    assert sesion_unica().ctx is None


def test_aviso_sin_referencia_dice_que_falta_y_que_hay(cliente):
    r = subir(cliente, [csv_demo(2023)], ciiu="6810")
    assert "No hay referencia sectorial para el CIIU 6810 cerca de 2023" in r.text
    assert "hoteles 2024" in r.text
    # Hotel de 2023: usa la referencia de 2024 y lo dice
    r = subir(cliente, [], ciiu="5511")
    assert "la comparación con el sector usa la de 2024" in r.text
    assert sesion_unica().ctx.referencia.anio == 2024
    assert 'class="aviso"' not in subir(cliente, [], ciiu="5511", fecha_0="2024-12-31").text


def test_cifras_en_miles_de_pesos(cliente):
    subir(cliente, [csv_demo(2024)], unidad="miles")
    activo = contexto_demo().historial.ultimo.balance.activo_total
    assert sesion_unica().ctx.historial.ultimo.balance.activo_total == pytest.approx(1000 * activo)


def test_porcion_de_largo_plazo(cliente):
    subir(cliente, [csv_demo(2024)])
    r = subir(cliente, [], fecha_0="2024-12-31", r0_0="520000000")
    lp = sesion_unica().ctx.historial.ultimo.balance.obligaciones_financieras_lp
    assert lp == contexto_demo().historial.ultimo.balance.obligaciones_financieras_lp
    assert '<details class="desplegable" open>' in r.text and 'value="520000000"' in r.text


def test_misma_fecha_y_ajuste_invalido(cliente):
    subir(cliente, [csv_demo(2023), csv_demo(2024)])
    r = subir(cliente, [], fecha_0="2024-12-31", fecha_1="2024-12-31", r0_0="-5")
    assert "misma fecha de corte" in r.text
    assert "debe ser un número positivo o cero" in r.text


def test_formato_no_permitido(cliente):
    r = subir(cliente, [("balance.pdf", b"%PDF", "application/pdf")])
    assert "balance.pdf: el archivo debe ser .csv, .xlsx o .xls." in r.text


def test_quitar_un_archivo(cliente):
    subir(cliente, [csv_demo(2023), csv_demo(2024)])
    r = cliente.post("/empresa/quitar/0")
    assert "hotel_demo_andino_2023.csv" not in r.text
    assert "Listo: estados financieros de 2024" in r.text


def test_empezar_de_nuevo_vacia_la_empresa_y_el_chat(cliente, llm):
    subir(cliente, [csv_demo(2024)])
    llm.respuestas += [herramienta("conversar"), RespuestaLLM(texto="Hola.")]
    r = cliente.post("/preguntar", data={"pregunta": "Hola"})
    cliente.get(f"/respuesta/{pid_de(r.text)}")
    r = cliente.post("/empresa/borrar")
    assert r.headers["HX-Trigger"] == "empresa-cambiada"
    assert "Suba al menos un balance de prueba." in r.text
    assert "¿en qué le ayudo?" in cliente.get("/chat").text
    assert "Sin empresa" in cliente.get("/").text


def test_sin_empresa_el_chat_pide_los_estados(cliente, llm):
    llm.respuestas += [herramienta("analizar_liquidez")]
    r = cliente.post("/preguntar", data={"pregunta": "¿Liquidez?"})
    assert "necesito los estados financieros" in cliente.get(f"/respuesta/{pid_de(r.text)}").text


def test_corte_sugerido():
    assert web.corte_sugerido("balance_2015-06-30.csv") == date(2015, 6, 30)
    assert web.corte_sugerido("cierre 2016.xlsx") == date(2016, 12, 31)
    assert web.corte_sugerido("balance_2015-02-30.csv") == date(2015, 12, 31)


CREDITO_NMV = {"monto": "150.000.000", "tasa": "24", "tipo": "NMV", "plazo": "36",
               "unidad": "meses", "periodicidad": "mensual", "sistema": "cuota_fija"}


def test_tablero_de_proyectos_abre_con_el_ejemplo(cliente):
    r = cliente.get("/modulo/proyectos?pestana=credito").text
    assert "Simulador de crédito" in r and 'hx-post="/proyectos/credito"' in r
    assert "$ 4.934.680" in r and "Ver las 60 cuotas" in r and "en construcción" not in r


def test_simulador_de_credito_devuelve_solo_el_resultado(cliente):
    r = cliente.post("/proyectos/credito", data=CREDITO_NMV)
    assert r.status_code == 200 and "$ 5.884.928" in r.text
    assert "26,82 % efectiva anual" in r.text
    assert "<form" not in r.text            # el formulario no se redibuja: conserva el foco


def test_simulador_de_credito_muestra_los_errores(cliente):
    r = cliente.post("/proyectos/credito", data={**CREDITO_NMV, "monto": "mucho"})
    assert r.status_code == 200 and "Escriba el monto" in r.text and "$ 5.884.928" not in r.text


def test_conversor_de_tasas_en_el_tablero(cliente):
    assert "Conversor de tasas" in cliente.get("/modulo/proyectos?pestana=credito").text
    r = cliente.post("/proyectos/tasas", data={"tasa": "24", "tipo": "NMV"})
    assert r.status_code == 200 and "26,82 %" in r.text and "<form" not in r.text


def test_proyectos_abre_en_la_pestana_de_su_proyecto(cliente):
    r = cliente.get("/modulo/proyectos").text
    assert 'role="tablist"' in r and "Simulador de crédito" not in r
    assert re.search(r'id="pestana-proyecto"[^>]*aria-selected="true"', r)
    assert re.search(r'id="pestana-credito"[^>]*aria-selected="false"', r)
    assert 'hx-get="/modulo/proyectos?pestana=credito"' in r and 'hx-push-url="true"' in r


@pytest.mark.parametrize("pestana, credito", [("credito", True), ("proyecto", False), ("xyz", False)])
def test_la_pestana_va_en_la_direccion(cliente, pestana, credito):
    r = cliente.get(f"/modulo/proyectos?pestana={pestana}").text
    assert ("Simulador de crédito" in r) is credito and ("Conversor de tasas" in r) is credito
    assert re.search(r'id="pestana-credito"[^>]*aria-selected="%s"' % str(credito).lower(), r)


PROYECTO = {"nombre": "Hotel del lago", "inversion": "100 millones", "vida_util": "5",
            "horizonte": "5", "ingresos": "60 millones", "crecimiento_real": "0",
            "costos_variables": "30", "costos_fijos": "10 millones", "capital_trabajo": "10",
            "tarifa_renta": "35", "inflacion": "3", "salvamento": ""}


def test_pestana_de_su_proyecto_con_el_flujo(cliente):
    r = cliente.get("/modulo/proyectos").text
    assert 'hx-post="/proyectos/flujo"' in r and "Flujo de caja libre" in r


def test_el_formulario_del_proyecto_recalcula_solo_la_tabla(cliente):
    r = cliente.post("/proyectos/flujo", data=PROYECTO)
    assert r.status_code == 200 and "$ 27.416.117" in r.text and "<form" not in r.text


def test_la_sesion_recuerda_el_proyecto_al_volver_a_la_pestana(cliente):
    cliente.post("/proyectos/flujo", data=PROYECTO)
    assert 'value="Hotel del lago"' in cliente.get("/modulo/proyectos").text
    cliente.post("/proyectos/flujo", data={**PROYECTO, "nombre": "Otro", "horizonte": "0"})
    assert 'value="Hotel del lago"' in cliente.get("/modulo/proyectos").text    # el inválido no


def test_las_dos_pestanas_dicen_que_los_valores_son_un_ejemplo(cliente):
    for url in ("/modulo/proyectos", "/modulo/proyectos?pestana=credito"):
        assert "Los valores iniciales son un ejemplo" in cliente.get(url).text


def test_la_pestana_de_su_proyecto_abre_evaluada(cliente):
    r = cliente.get("/modulo/proyectos").text
    assert 'name="tasa_oportunidad"' in r and "Valor presente neto (VPN)" in r


def test_sin_tasa_de_oportunidad_pide_escribirla(cliente):
    r = cliente.post("/proyectos/flujo", data={**PROYECTO, "tasa_oportunidad": ""}).text
    assert "Escriba su tasa de oportunidad" in r and "Flujo de caja libre" in r


def test_el_formulario_actualiza_tambien_la_evaluacion_de_arriba(cliente):
    r = cliente.post("/proyectos/flujo", data=PROYECTO).text
    assert 'id="evaluacion"' in r and 'hx-swap-oob="true"' in r and "Valor presente neto" in r
    r = cliente.post("/proyectos/flujo", data={**PROYECTO, "horizonte": "0"}).text
    assert "Corrija los datos del formulario" in r and "Valor presente neto" not in r


def test_la_pagina_no_repite_el_bloque_de_evaluacion(cliente):
    assert cliente.get("/modulo/proyectos").text.count('id="evaluacion"') == 1


def test_pestana_de_sensibilidad(cliente):
    r = cliente.get("/modulo/proyectos?pestana=sensibilidad").text
    assert re.search(r'id="pestana-sensibilidad"[^>]*aria-selected="true"', r)
    assert "¿Qué tan frágil es su proyecto?" in r and 'class="tornado' in r
    assert "Es el proyecto de ejemplo" in r


def test_la_sensibilidad_usa_el_proyecto_de_la_sesion(cliente):
    cliente.post("/proyectos/flujo", data=PROYECTO)
    r = cliente.get("/modulo/proyectos?pestana=sensibilidad").text
    assert "Hotel del lago" in r and "Es el proyecto de ejemplo" not in r
