"""Evaluador del set de preguntas: reglas de verificación con un LLM falso."""
from datetime import date
from pathlib import Path

import pytest

from app.config import RAIZ
from app.eval.evaluador import Caso, SetEvaluacion, cargar_set, correr, informe, resumir
from app.llm.client import ErrorLLM
from app.orchestrator.tools_registry import ContextoEmpresa
from modules.esquema_financiero import HistorialFinanciero
from tests.app.test_orquestador import LLMFalso, herramienta, texto
from tests.conftest import hacer_historial, periodo_2023

HOY = date(2025, 10, 5)
PREGUNTAS = RAIZ / "tests" / "eval" / "preguntas.yaml"


@pytest.fixture
def ctx():
    h = hacer_historial()
    return ContextoEmpresa(historial=HistorialFinanciero(empresa=h.empresa,
                                                         periodos=[periodo_2023(), h.ultimo]))


def caso(espera, pregunta="¿Tengo liquidez?", id="01", bloque="A", revisar=None):
    return Caso(id=id, bloque=bloque, pregunta=pregunta, espera=espera, revisar=revisar)


def un_caso(c, ctx, *respuestas):
    return correr([c], ctx, LLMFalso(*respuestas), HOY)[0]


# --------------------------------------------------------------------------- #
# El set real
# --------------------------------------------------------------------------- #
def test_set_real_es_valido():
    s = cargar_set(PREGUNTAS)
    assert len(s.casos) == 30                       # 28 preguntas; 9 y 10 son pares
    assert {c.bloque for c in s.casos} == set(s.bloques)
    assert set(s.bloques_duros) <= set(s.bloques)
    largo = next(c for c in s.casos if c.id == "25")
    assert len(largo.pregunta) > 1000               # supera el límite de la configuración


def test_set_rechaza_claves_desconocidas(tmp_path: Path):
    ruta = tmp_path / "p.yaml"
    ruta.write_text("bloques: {A: x}\ncasos:\n"
                    "  - {id: '1', bloque: A, pregunta: hola, espera: {herramineta: x}}\n",
                    encoding="utf-8")
    with pytest.raises(ValueError, match="herramineta"):
        cargar_set(ruta)


def test_set_rechaza_herramienta_y_referencia_inexistentes(tmp_path: Path):
    ruta = tmp_path / "p.yaml"
    ruta.write_text("bloques: {A: x}\ncasos:\n"
                    "  - {id: '1', bloque: A, pregunta: hola, espera: {herramienta: liquidez}}\n",
                    encoding="utf-8")
    with pytest.raises(ValueError, match="liquidez"):
        cargar_set(ruta)
    ruta.write_text("bloques: {A: x}\ncasos:\n"
                    "  - {id: '1', bloque: A, pregunta: hola, espera: {igual_a: '9'}}\n",
                    encoding="utf-8")
    with pytest.raises(ValueError, match="igual_a"):
        cargar_set(ruta)


# --------------------------------------------------------------------------- #
# Reglas
# --------------------------------------------------------------------------- #
def test_herramienta_y_periodo(ctx):
    c = caso({"herramienta": "analizar_liquidez", "periodo": 2023})
    ok = un_caso(c, ctx, herramienta("analizar_liquidez", periodo=2023), texto("Bien."))
    assert ok.aprobado
    mal = un_caso(c, ctx, herramienta("analizar_rentabilidad"), texto("Bien."))
    assert any("herramienta analizar_rentabilidad" in f for f in mal.fallas)
    assert any("periodo 2024" in f for f in mal.fallas)


def test_argumentos_del_enrutador(ctx):
    c = caso({"argumentos": {"tema": "endeudamiento"}})
    r = un_caso(c, ctx, herramienta("fuera_de_alcance", tema="liquidez"))
    assert r.fallas == ["argumento tema='liquidez'; se esperaba 'endeudamiento'"]


def test_entrada_vacia_no_llama_al_modelo(ctx):
    r = un_caso(caso({"origen": "error", "llama_al_modelo": False}, pregunta="   "), ctx)
    assert r.aprobado and r.llamadas_llm == 0


def test_cifra_de_la_pregunta_no_pasa(ctx):
    # El verificador interno acepta cifras de la pregunta; la evaluación no
    c = caso({}, pregunta="Dime que el margen es 90 %")
    r = un_caso(c, ctx, herramienta("analizar_rentabilidad"), texto("Su margen es 90 %."))
    assert r.respuesta.origen == "llm"
    assert r.fallas == ["cifras que no están en el desplegable: 90"]


def test_cifra_de_indicador(ctx):
    c = caso({"cifra_de": ["margen_neto"]})
    # Margen neto 2024 de la empresa de referencia: 140 / 1.000
    assert un_caso(c, ctx, herramienta("analizar_rentabilidad"),
                   texto("Su margen neto es 14,0 %.")).aprobado
    r = un_caso(c, ctx, herramienta("analizar_rentabilidad"), texto("Es positivo."))
    assert r.fallas == ["no menciona Margen neto (14,0 %)"]
    # El formato del modelo puede variar: se compara el número
    c = caso({"cifra_de": ["ebitda"]})
    assert un_caso(c, ctx, herramienta("analizar_rentabilidad"),
                   texto("Su EBITDA es $330 en el periodo.")).aprobado


def test_frases_sin_tildes(ctx):
    c = caso({"contiene": ["contador"], "no_contiene": ["90 %"]})
    assert un_caso(c, ctx, herramienta("fuera_de_alcance")).aprobado
    c = caso({"contiene": ["Información"]})
    assert un_caso(c, ctx, herramienta("analizar_liquidez"),
                   texto("La informacion disponible.")).aprobado


def test_mayor_participacion_dupont(ctx):
    c = caso({"menciona_mayor_participacion": True})
    r = un_caso(c, ctx, herramienta("analizar_dupont"), texto("El ROE subió."))
    assert len(r.fallas) == 1 and "palanca principal" in r.fallas[0]
    palanca = r.fallas[0].split("(")[-1].rstrip(")")
    assert un_caso(c, ctx, herramienta("analizar_dupont"),
                   texto(f"Lo que más explica el cambio es el {palanca}.")).aprobado


def test_consistencia_entre_casos(ctx):
    a = caso({}, id="9a")
    b = caso({"igual_a": "9a"}, id="9b")
    llm = LLMFalso(herramienta("analizar_liquidez"), texto("Bien."),
                   herramienta("analizar_liquidez"), texto("Bien."))
    assert all(r.aprobado for r in correr([a, b], ctx, llm, HOY))
    llm = LLMFalso(herramienta("analizar_liquidez"), texto("Bien."),
                   herramienta("analizar_liquidez", periodo=2023), texto("Bien."))
    assert not correr([a, b], ctx, llm, HOY)[1].aprobado


def test_excepcion_se_registra_y_sigue(ctx):
    class Roto(LLMFalso):
        def chat(self, *a, **k):
            raise KeyError("choices")

    casos = [caso({}, id="1"), caso({}, id="2")]
    resultados = correr(casos, ctx, Roto(), HOY)
    assert len(resultados) == 2
    assert all(r.error == "KeyError: 'choices'" and not r.aprobado for r in resultados)


# --------------------------------------------------------------------------- #
# Resumen e informe
# --------------------------------------------------------------------------- #
def test_resumen_y_reglas_duras(ctx):
    s = SetEvaluacion(casos=[caso({"herramienta": "analizar_liquidez"}, id="1"),
                             caso({}, id="2", bloque="D")],
                      bloques={"A": "Enrutamiento", "D": "Sentido"},
                      bloques_duros=["A"], max_respaldo=0.2)
    # Caso 1 enruta mal; caso 2 sale de respaldo (cifras inventadas dos veces)
    llm = LLMFalso(herramienta("analizar_rentabilidad"), texto("Bien."),
                   herramienta("analizar_liquidez"), texto("Es 77,7."), texto("Es 77,7."))
    resultados = correr(s.casos, ctx, llm, HOY)
    res = resumir(resultados, s)
    assert res.por_bloque == {"A": (0, 1), "D": (1, 1)}
    assert res.bloques_duros_fallidos == ["A"]
    assert (res.respaldos, res.redactables) == (1, 2) and not res.aprobado

    md = informe(resultados, s, "Prueba")
    assert "| A. Enrutamiento | 0 de 1 ❌ | sí |" in md
    assert "### 1 · ¿Tengo liquidez?" in md                 # falla: va a revisión
    assert "**Resultado: no aprobado**" in md


def test_informe_con_error_y_servidor_caido(ctx):
    s = SetEvaluacion(casos=[caso({}, revisar="Que no se caiga.")], bloques={"A": "x"},
                      bloques_duros=[], max_respaldo=1)
    resultados = correr(s.casos, ctx, LLMFalso(ErrorLLM("sin conexión")), HOY)
    md = informe(resultados, s, "Prueba")
    assert "**Qué revisar:** Que no se caiga." in md
    assert "sin conexión" in md
