"""Base de conocimiento (tipo 2): índice, búsqueda híbrida y respuesta conceptual."""
from datetime import date
from types import SimpleNamespace

import pytest

from app.config import _prefijo
from app.llm.client import ErrorLLM
from app.orchestrator.orquestador import AVISO_SIN_REVISAR, SIN_FUENTE, responder
from app.orchestrator.tools_registry import ContextoEmpresa
from app.rag.ingest import ErrorNota, construir_indice, leer_nota, leer_notas
from app.rag.retriever import Buscador, raices
from tests.app.test_orquestador import LLMFalso, herramienta, texto
from tests.conftest import hacer_historial

NOTA = """---
titulo: {titulo}
temas: [{temas}]
fuente: Prueba
revisado: {revisado}
---
{cuerpo}
"""


def escribir(carpeta, nombre, titulo, temas, cuerpo, revisado="false"):
    (carpeta / nombre).write_text(NOTA.format(titulo=titulo, temas=temas, cuerpo=cuerpo,
                                              revisado=revisado), encoding="utf-8")


class EmbeddingsFalsos:
    """Vector = conteo de palabras clave; suficiente para probar la búsqueda."""
    EJES = ("ebitda", "tasa", "precio", "deuda")
    cfg = SimpleNamespace(embeddings_modelo="falso", embeddings_prefijo_documento="doc: ",
                          embeddings_prefijo_consulta="q: ")

    def __init__(self, falla=False):
        self.llamadas, self.falla = [], falla

    def embeddings(self, textos):
        if self.falla:
            raise ErrorLLM("sin servidor")
        self.llamadas.append(textos)
        return [[t.lower().count(e) + 0.01 for e in self.EJES] for t in textos]


@pytest.fixture
def base(tmp_path):
    carpeta = tmp_path / "conocimiento"
    carpeta.mkdir()
    escribir(carpeta, "ebitda.md", "EBITDA", "ebitda, caja", "El ebitda aproxima la caja.",
             revisado="true")
    escribir(carpeta, "tasas.md", "Tasas de interés", "tasa, deuda", "Si sube la tasa, la deuda cuesta más.")
    (carpeta / "README.md").write_text("no es una nota", encoding="utf-8")
    return carpeta


# --------------------------------------------------------------------------- #
def test_leer_notas_ignora_readme_y_valida_encabezado(base, tmp_path):
    notas = leer_notas(base)
    assert [n.titulo for n in notas] == ["EBITDA", "Tasas de interés"]
    assert notas[0].revisado and not notas[1].revisado
    mala = tmp_path / "mala.md"
    mala.write_text("---\ntitulo: X\n---\ntexto", encoding="utf-8")
    with pytest.raises(ErrorNota, match="faltan campos"):
        leer_nota(mala)


def test_indice_solo_recalcula_lo_que_cambio(base, tmp_path):
    destino = tmp_path / "indice.json"
    emb = EmbeddingsFalsos()
    assert construir_indice(emb, base, destino)["recalculadas"] == 2
    assert all(t.startswith("doc: ") for t in emb.llamadas[0])   # prefijo de documento
    assert construir_indice(emb, base, destino)["recalculadas"] == 0
    escribir(base, "tasas.md", "Tasas de interés", "tasa", "Texto nuevo sobre la tasa.")
    assert construir_indice(emb, base, destino)["recalculadas"] == 1


def test_busqueda_hibrida_y_umbral(base, tmp_path):
    destino = tmp_path / "indice.json"
    emb = EmbeddingsFalsos()
    construir_indice(emb, base, destino)
    b = Buscador.desde_archivo(emb, destino)
    assert b.buscar("¿Qué es el EBITDA?")[0].titulo == "EBITDA"
    assert b.buscar("¿Cómo me afecta la tasa de interés de mi deuda?")[0].titulo == "Tasas de interés"
    assert b.buscar("¿Cómo registro una marca?") == []
    assert emb.llamadas[-1][0].startswith("q: ")                   # prefijo de consulta


def test_sin_servidor_busca_solo_por_palabras(base, tmp_path):
    destino = tmp_path / "indice.json"
    construir_indice(EmbeddingsFalsos(), base, destino)
    b = Buscador.desde_archivo(EmbeddingsFalsos(falla=True), destino)
    assert b.buscar("¿Qué es el ebitda y la caja?")[0].titulo == "EBITDA"
    assert any("solo por palabras" in e for e in b.eventos)


def test_raices_iguala_singular_y_plural():
    assert raices("¿Tengo con qué pagar mis deudas?") & raices("la deuda de corto plazo")
    assert "tengo" not in "".join(raices("tengo"))                 # palabra vacía


def test_prefijo_recupera_el_espacio():
    assert _prefijo("search_query:") == "search_query: "
    assert _prefijo("  ") == ""


# --------------------------------------------------------------------------- #
@pytest.fixture
def buscador(base, tmp_path):
    destino = tmp_path / "indice.json"
    emb = EmbeddingsFalsos()
    construir_indice(emb, base, destino)
    return Buscador.desde_archivo(emb, destino)


CTX = ContextoEmpresa(historial=hacer_historial())
HOY = date(2025, 10, 5)


def test_respuesta_conceptual_con_fuentes(buscador):
    llm = LLMFalso(herramienta("consulta_conceptual"),
                   texto("Si sube la tasa, su deuda cuesta más."))
    r = responder("¿Cómo me afecta la tasa de interés de mi deuda?", CTX, llm, HOY, buscador)
    assert r.origen == "llm" and r.herramienta == "consulta_conceptual"
    assert r.fuentes == ["Tasas de interés (Prueba)"]
    assert AVISO_SIN_REVISAR in r.notas                            # la nota no está revisada
    assert "Fuentes:" in r.texto_completo
    redaccion = llm.llamadas[1]
    assert "FUENTES:" in redaccion["usuario"] and "economista de cabecera" in redaccion["sistema"]


def test_nota_revisada_no_lleva_aviso(buscador):
    llm = LLMFalso(herramienta("consulta_conceptual"), texto("El EBITDA aproxima la caja."))
    r = responder("¿Qué es el EBITDA?", CTX, llm, HOY, buscador)
    assert r.fuentes == ["EBITDA (Prueba)"] and not r.notas


def test_sin_fuente_no_responde_de_memoria(buscador):
    llm = LLMFalso(herramienta("consulta_conceptual"))
    r = responder("¿Qué opina del dólar?", CTX, llm, HOY, buscador)
    assert r.texto == SIN_FUENTE and r.origen == "sin_llm" and len(llm.llamadas) == 1


def test_cifra_inventada_en_conceptual_usa_el_texto_de_la_nota(buscador):
    llm = LLMFalso(herramienta("consulta_conceptual"),
                   texto("La tasa subió 3 puntos en 2023."), texto("Subió 12,5 %."))
    r = responder("¿Cómo me afecta la tasa de interés de mi deuda?", CTX, llm, HOY, buscador)
    assert r.origen == "respaldo"
    assert "Si sube la tasa, la deuda cuesta más." in r.texto
