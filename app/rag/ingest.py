"""
Construye el índice de la base de conocimiento (conocimiento/*.md).

Cada nota se convierte en un vector con el modelo de embeddings y se guarda en
data/conocimiento/indice.json. Solo se recalculan las notas que cambiaron.

Uso (con el servidor de LM Studio encendido):
    python -m app.rag.ingest
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

from app.config import RAIZ, config
from app.llm.client import ClienteLLM

CONOCIMIENTO = RAIZ / "conocimiento"
INDICE = RAIZ / "data" / "conocimiento" / "indice.json"


class ErrorNota(ValueError):
    """Una nota no tiene el encabezado requerido."""


@dataclass
class Nota:
    archivo: str
    titulo: str
    temas: list[str]
    fuente: str
    revisado: bool
    texto: str

    @property
    def para_indice(self) -> str:
        """Lo que se convierte en vector: título y temas ayudan a la búsqueda."""
        return f"{self.titulo}. Temas: {', '.join(self.temas)}.\n{self.texto}"


def leer_nota(ruta: Path) -> Nota:
    contenido = ruta.read_text(encoding="utf-8")
    partes = contenido.split("---", 2)
    if not contenido.startswith("---") or len(partes) < 3:
        raise ErrorNota(f"{ruta.name}: falta el encabezado entre líneas '---'.")
    try:
        meta = yaml.safe_load(partes[1]) or {}
    except yaml.YAMLError as e:
        raise ErrorNota(f"{ruta.name}: encabezado mal formado ({e}).") from e
    faltan = [c for c in ("titulo", "temas", "fuente", "revisado") if c not in meta]
    if faltan:
        raise ErrorNota(f"{ruta.name}: faltan campos en el encabezado: {', '.join(faltan)}.")
    return Nota(archivo=ruta.name, titulo=str(meta["titulo"]),
                temas=[str(t) for t in meta["temas"]], fuente=str(meta["fuente"]),
                revisado=bool(meta["revisado"]), texto=partes[2].strip())


def leer_notas(carpeta: Path = CONOCIMIENTO) -> list[Nota]:
    return [leer_nota(r) for r in sorted(carpeta.glob("*.md")) if r.name.lower() != "readme.md"]


def huella(texto: str, modelo: str, prefijo: str) -> str:
    return hashlib.sha256(f"{modelo}|{prefijo}|{texto}".encode("utf-8")).hexdigest()


def construir_indice(cliente: ClienteLLM | None = None, carpeta: Path = CONOCIMIENTO,
                     destino: Path = INDICE) -> dict:
    cliente = cliente or ClienteLLM()
    cfg = cliente.cfg if hasattr(cliente, "cfg") else config()
    modelo, prefijo = cfg.embeddings_modelo, cfg.embeddings_prefijo_documento
    anterior = {}
    if destino.exists():
        anterior = {n["huella"]: n["vector"]
                    for n in json.loads(destino.read_text(encoding="utf-8"))["notas"]}

    notas = leer_notas(carpeta)
    huellas = [huella(n.para_indice, modelo, prefijo) for n in notas]
    pendientes = [i for i, h in enumerate(huellas) if h not in anterior]
    nuevos = cliente.embeddings([prefijo + notas[i].para_indice for i in pendientes]) if pendientes else []
    vectores = dict(zip(pendientes, nuevos))

    indice = {
        "modelo": modelo,
        "prefijo_documento": prefijo,
        "notas": [{**asdict(n), "huella": h, "vector": vectores.get(i) or anterior[h]}
                  for i, (n, h) in enumerate(zip(notas, huellas))],
    }
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(indice, ensure_ascii=False), encoding="utf-8")
    indice["recalculadas"] = len(pendientes)
    return indice


if __name__ == "__main__":
    indice = construir_indice()
    sin_revisar = [n["titulo"] for n in indice["notas"] if not n["revisado"]]
    print(f"Índice con {len(indice['notas'])} notas ({indice['recalculadas']} recalculadas) "
          f"en {INDICE.relative_to(RAIZ)}.")
    if sin_revisar:
        print(f"Sin revisar ({len(sin_revisar)}): " + "; ".join(sin_revisar))
