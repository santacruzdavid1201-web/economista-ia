"""Orquestador con un LLM falso: cada rama del pipeline sin depender del servidor."""
from datetime import date

import pytest

from app.llm.client import ErrorLLM, LlamadaHerramienta, RespuestaLLM
from app.orchestrator.orquestador import (
    FUERA_DE_ALCANCE,
    ErrorEntrada,
    datos_para_redactar,
    responder,
    validar_pregunta,
)
from app.orchestrator.tools_registry import ContextoEmpresa, esquema_openai
from app.orchestrator.verificador import cifras_no_respaldadas
from modules.balance.razones import liquidez
from tests.conftest import hacer_historial

HOY = date(2025, 10, 5)


class LLMFalso:
    """Devuelve respuestas guionadas en orden y guarda lo que recibió."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.llamadas: list[dict] = []

    def chat(self, sistema, usuario, herramientas=None, forzar_herramienta=False, temperatura=0.2):
        self.llamadas.append({"sistema": sistema, "usuario": usuario,
                              "herramientas": herramientas, "forzar": forzar_herramienta})
        r = self.respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def herramienta(nombre, **args):
    return RespuestaLLM(herramientas=[LlamadaHerramienta(nombre, args)])


def texto(t):
    return RespuestaLLM(texto=t)


@pytest.fixture
def ctx():
    return ContextoEmpresa(historial=hacer_historial())


# --------------------------------------------------------------------------- #
def test_flujo_completo(ctx):
    llm = LLMFalso(herramienta("analizar_liquidez", periodo=2024),
                   texto("Su razón corriente es 2,04 veces: cubre sus deudas de corto plazo."))
    r = responder("¿Puedo pagar mis deudas?", ctx, llm, HOY)
    assert r.origen == "llm"
    assert r.herramienta == "analizar_liquidez" and r.periodo == 2024
    assert r.texto.startswith("Su razón corriente es 2,04")
    # El enrutador fuerza herramienta; la redacción no recibe herramientas
    assert llm.llamadas[0]["forzar"] and llm.llamadas[0]["herramientas"]
    assert llm.llamadas[1]["herramientas"] is None
    # Supuestos agregados por Python, no por el LLM
    assert "Para tener en cuenta:" in r.texto_completo
    assert any("Saldos al cierre" in n for n in r.notas)


def test_roles_separados(ctx):
    pregunta = "¿Puedo pagar mis deudas?"
    llm = LLMFalso(herramienta("analizar_liquidez"), texto("Sí."))
    responder(pregunta, ctx, llm, HOY)
    for llamada in llm.llamadas:
        assert pregunta not in llamada["sistema"]
        assert pregunta in llamada["usuario"]


def test_enrutador_conoce_anios(ctx):
    llm = LLMFalso(herramienta("analizar_liquidez"), texto("Sí."))
    responder("¿Cómo vamos?", ctx, llm, HOY)
    sistema = llm.llamadas[0]["sistema"]
    assert "el año pasado\" es 2024" in sistema and "disponibles: 2024" in sistema


def test_cifra_inventada_se_reintenta(ctx):
    llm = LLMFalso(herramienta("analizar_liquidez"),
                   texto("Su razón corriente es 2,5 veces."),         # 2,5 no está en los datos
                   texto("Su razón corriente es 2,04 veces."))
    r = responder("¿Liquidez?", ctx, llm, HOY)
    assert r.origen == "llm" and "2,04" in r.texto
    assert "2,5" in llm.llamadas[2]["usuario"]                       # se le dijo qué corregir
    assert any("sin respaldo ['2,5']" in e for e in r.eventos)


def test_dos_veces_inventada_usa_respaldo(ctx):
    llm = LLMFalso(herramienta("analizar_liquidez"), texto("Es 2,5."), texto("Es 3,7."))
    r = responder("¿Liquidez?", ctx, llm, HOY)
    assert r.origen == "respaldo"
    assert "Razón corriente: 2,04 veces" in r.texto


def test_servidor_caido_en_enrutamiento(ctx):
    r = responder("¿Liquidez?", ctx, LLMFalso(ErrorLLM("No hay conexión con el modelo")), HOY)
    assert r.origen == "error" and "No hay conexión" in r.texto


def test_servidor_caido_en_redaccion_usa_respaldo(ctx):
    r = responder("¿Liquidez?", ctx, LLMFalso(herramienta("analizar_liquidez"),
                                               ErrorLLM("timeout")), HOY)
    assert r.origen == "respaldo" and "Razón corriente" in r.texto
    assert r.notas                                                    # las notas se conservan


def test_herramienta_inexistente(ctx):
    r = responder("¿Liquidez?", ctx, LLMFalso(herramienta("borrar_base_de_datos")), HOY)
    assert r.origen == "error" and "otra manera" in r.texto


def test_fuera_de_alcance_no_llama_redaccion(ctx):
    llm = LLMFalso(herramienta("fuera_de_alcance"))
    r = responder("¿Cómo registro una marca?", ctx, llm, HOY)
    assert r.texto == FUERA_DE_ALCANCE and len(llm.llamadas) == 1


def test_anio_sin_datos(ctx):
    r = responder("¿Liquidez en 2019?", ctx, LLMFalso(herramienta("analizar_liquidez",
                                                                   periodo=2019)), HOY)
    assert r.origen == "sin_llm" and "Años disponibles: 2024" in r.texto


def test_comparar_sin_referencia(ctx):
    r = responder("¿Y frente al sector?", ctx, LLMFalso(herramienta("comparar_con_sector")), HOY)
    assert "No hay una referencia sectorial" in r.texto


# --------------------------------------------------------------------------- #
def test_validar_pregunta():
    assert validar_pregunta("  ¿Liquidez?\x00\x07  ") == "¿Liquidez?"
    with pytest.raises(ErrorEntrada, match="Escriba"):
        validar_pregunta("   ")
    with pytest.raises(ErrorEntrada, match="muy larga"):
        validar_pregunta("a" * 50, max_caracteres=10)
    with pytest.raises(ErrorEntrada, match="texto"):
        validar_pregunta(None)


def test_pregunta_invalida_no_llama_al_llm(ctx):
    llm = LLMFalso()
    r = responder("", ctx, llm, HOY)
    assert r.origen == "error" and not llm.llamadas


def test_verificador():
    datos = "Razón corriente: 2,04 veces; capital: $ 280; percentil 19"
    assert cifras_no_respaldadas("Es 2,04 y percentil 19, en 3 años", datos) == []
    assert cifras_no_respaldadas("Es 2,1 y mejor que el 81 %", datos) == ["2,1", "81"]


def test_datos_incluyen_glosario_solo_de_lo_usado(ctx):
    d = datos_para_redactar(ctx, [liquidez(ctx.historial)])
    assert set(d["glosario"]) == {"razon_corriente", "prueba_acida", "razon_efectivo",
                                  "capital_trabajo"}
    assert "Razón corriente: 2,04 veces" in d["indicadores"]


def test_esquema_de_herramientas():
    nombres = [h["function"]["name"] for h in esquema_openai()]
    assert "fuera_de_alcance" in nombres and len(nombres) == len(set(nombres))
    fuera = next(h for h in esquema_openai() if h["function"]["name"] == "fuera_de_alcance")
    assert fuera["function"]["parameters"]["properties"] == {}


def test_comparar_por_tema_solo_trae_ese_tema():
    from app.demo import contexto_demo
    ctx = contexto_demo()
    llm = LLMFalso(herramienta("comparar_con_sector", tema="rentabilidad"), texto("Bien."))
    r = responder("¿Rentabilidad frente al sector?", ctx, llm, HOY)
    hallazgos = r.resultados[0].hallazgos
    assert hallazgos and all(not h.startswith(("Razón corriente", "Días")) for h in hallazgos)
    assert any(h.startswith("Rentabilidad del activo (ROA)") for h in hallazgos)


def test_tema_desconocido_compara_todo():
    from app.demo import contexto_demo
    llm = LLMFalso(herramienta("comparar_con_sector", tema="marketing"), texto("Bien."))
    r = responder("¿Frente al sector?", contexto_demo(), llm, HOY)
    assert any(h.startswith("Razón corriente") for h in r.resultados[0].hallazgos)


def test_analisis_tematico_incluye_sector_si_hay_referencia():
    from app.demo import contexto_demo
    r = responder("¿Rentabilidad?", contexto_demo(),
                  LLMFalso(herramienta("analizar_rentabilidad"), texto("Bien.")), HOY)
    assert [x.analisis for x in r.resultados] == ["rentabilidad", "benchmark"]


def test_analisis_tematico_sin_referencia_no_falla(ctx):
    r = responder("¿Rentabilidad?", ctx, LLMFalso(herramienta("analizar_rentabilidad"),
                                                  texto("Bien.")), HOY)
    assert [x.analisis for x in r.resultados] == ["rentabilidad"]


# --------------------------------------------------------------------------- #
# Crecimiento real (series externas inyectadas: sin red)
# --------------------------------------------------------------------------- #
def ctx_con_ipc(serie):
    from modules.esquema_financiero import HistorialFinanciero
    from tests.conftest import periodo_2023
    h = hacer_historial()
    return ContextoEmpresa(historial=HistorialFinanciero(empresa=h.empresa,
                                                         periodos=[periodo_2023(), h.ultimo]),
                           serie=serie)


def test_crecimiento_real_enruta_calcula_y_redacta():
    from data_sources.externos.series.modelo import Serie
    pedidas = []

    def serie(variable, geografia, desde):
        pedidas.append((variable, geografia, desde))
        obs = [(date(a, m, 28), 100 if a == 2023 else 105) for a in (2023, 2024)
               for m in range(1, 13)]
        return Serie(clave="ipc_nacional", nombre="IPC", fuente="BanRep", unidad="índice",
                     frecuencia="mensual", geografia="nacional", consultada=HOY,
                     observaciones=obs)

    # Ingresos 800 → 1.000 (25 %) con IPC 100 → 105: real 1,25 / 1,05 − 1 = 19,0 %
    llm = LLMFalso(herramienta("analizar_crecimiento_real"),
                   texto("Descontando la inflación, sus ingresos crecieron 19,0 %."))
    r = responder("¿Crecí en términos reales?", ctx_con_ipc(serie), llm, HOY)
    assert r.origen == "llm" and r.herramienta == "analizar_crecimiento_real"
    assert pedidas == [("ipc", None, date(2023, 1, 1))]     # desde el periodo anterior
    assert r.resultados[0].valor("crecimiento_real_ingresos") == pytest.approx(0.190476, abs=1e-6)
    assert "crecimiento_real_ingresos" in llm.llamadas[1]["usuario"]   # glosario
    assert any("IPC general" in n for n in r.notas)


def test_crecimiento_real_sin_ipc_disponible():
    from data_sources.externos.series.catalogo import ErrorSerie

    def sin_red(*args):
        raise ErrorSerie("No se pudo descargar la serie ipc_pasto. Revise la conexión.")

    r = responder("¿Crecí?", ctx_con_ipc(sin_red),
                  LLMFalso(herramienta("analizar_crecimiento_real")), HOY)
    assert r.origen == "sin_llm" and "Revise la conexión" in r.texto
