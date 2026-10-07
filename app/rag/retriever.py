"""
Búsqueda en la base de conocimiento: híbrida, por significado y por palabras.

El modelo de embeddings local (nomic) está entrenado sobre todo en inglés: en
pruebas, "¿Tengo con qué pagar mis deudas?" quedó más cerca de la nota del
EBITDA que de la de liquidez. La coincidencia de palabras en español corrige
esos casos; el significado cubre las preguntas con otras palabras.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from app.llm.client import ErrorLLM
from app.rag.ingest import INDICE

PESO_SIGNIFICADO, PESO_PALABRAS = 0.7, 0.3
UMBRAL = 0.55           # por debajo, la nota no es pertinente (calibrado con el set de prueba)
UMBRAL_SOLO_PALABRAS = 0.5
STOPWORDS = set("""a al algo como con cual cuales cuando de del el ella ellos en entre es esa
ese eso esta este esto estos fue ha hay la las le les lo los me mi mis muy no nos o para pero
por que qué quien se sea ser si sin sobre su sus te tengo tiene tu tus un una uno y ya yo
cómo cuál cuándo dónde por qué mí también usted ustedes nuestro nuestra mucho poco""".split())


@dataclass
class Fragmento:
    titulo: str
    fuente: str
    revisado: bool
    texto: str
    puntaje: float


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto.lower())
                   if not unicodedata.combining(c))


def raices(texto: str) -> set[str]:
    """Palabras de contenido truncadas a 5 letras: 'deudas' y 'deuda' coinciden."""
    palabras = re.findall(r"[a-zñ]+", _sin_tildes(texto))
    return {p[:5] for p in palabras if p not in STOPWORDS and len(p) > 2}


def coseno(a: list[float], b: list[float]) -> float:
    norma = math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b)) / norma if norma else 0.0


class Buscador:
    def __init__(self, indice: dict, cliente=None):
        self.notas = indice["notas"]
        self.cliente = cliente
        self.prefijo = (cliente.cfg.embeddings_prefijo_consulta
                        if cliente is not None and hasattr(cliente, "cfg") else "search_query: ")
        self.eventos: list[str] = []
        self._raices = [raices(f"{n['titulo']} {' '.join(n['temas'])} {n['texto']}")
                        for n in self.notas]

    @classmethod
    def desde_archivo(cls, cliente=None, ruta: Path = INDICE) -> "Buscador | None":
        if not ruta.exists():
            return None
        return cls(json.loads(ruta.read_text(encoding="utf-8")), cliente)

    def buscar(self, pregunta: str, k: int = 2) -> list[Fragmento]:
        q = raices(pregunta)
        palabras = [len(q & r) / len(q) if q else 0.0 for r in self._raices]

        significado = None
        if self.cliente is not None:
            try:
                vector = self.cliente.embeddings([self.prefijo + pregunta])[0]
                significado = [coseno(vector, n["vector"]) for n in self.notas]
            except ErrorLLM as e:
                self.eventos.append(f"búsqueda solo por palabras: {e}")

        if significado is None:
            puntajes, umbral = palabras, UMBRAL_SOLO_PALABRAS
        else:
            puntajes = [PESO_SIGNIFICADO * s + PESO_PALABRAS * p
                        for s, p in zip(significado, palabras)]
            umbral = UMBRAL
        orden = sorted(range(len(self.notas)), key=lambda i: puntajes[i], reverse=True)
        return [Fragmento(titulo=self.notas[i]["titulo"], fuente=self.notas[i]["fuente"],
                          revisado=self.notas[i]["revisado"], texto=self.notas[i]["texto"],
                          puntaje=puntajes[i])
                for i in orden[:k] if puntajes[i] >= umbral]
