"""
Configuración desde variables de entorno.

Las claves y direcciones nunca van en el código. Para desarrollo local se puede
crear un archivo `.env` en la raíz (no se versiona; ver `.env.example`); las
variables ya definidas en el sistema tienen prioridad sobre el archivo.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def cargar_env(ruta: Path = RAIZ / ".env") -> None:
    """Lee líneas CLAVE=valor del .env sin sobrescribir variables existentes."""
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Config:
    llm_url: str
    llm_modelo: str
    llm_api_key: str | None
    llm_timeout: float
    max_caracteres_pregunta: int


def config() -> Config:
    cargar_env()
    return Config(
        # LM Studio por defecto; Ollama usa http://localhost:11434/v1
        llm_url=os.environ.get("LLM_URL", "http://localhost:1234/v1").rstrip("/"),
        llm_modelo=os.environ.get("LLM_MODELO", "qwen2.5-7b-instruct"),
        # Solo para proveedores con API (demo pública); el modelo local no la usa
        llm_api_key=os.environ.get("LLM_API_KEY") or None,
        llm_timeout=float(os.environ.get("LLM_TIMEOUT", "300")),
        max_caracteres_pregunta=int(os.environ.get("MAX_CARACTERES_PREGUNTA", "1000")),
    )
