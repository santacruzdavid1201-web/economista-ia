"""
Cliente para servidores compatibles con la API de OpenAI (LM Studio, Ollama o
un proveedor externo para la demo pública). Sin dependencias más allá de
`requests`.

Los errores de red y de formato se convierten en `ErrorLLM` con un mensaje
que dice qué revisar; el orquestador decide cómo responder al usuario.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

import requests

from app.config import Config, config


class ErrorLLM(RuntimeError):
    """El modelo no respondió o respondió algo inutilizable."""


@dataclass
class LlamadaHerramienta:
    nombre: str
    argumentos: dict


@dataclass
class RespuestaLLM:
    texto: str | None = None
    herramientas: list[LlamadaHerramienta] = field(default_factory=list)


class ClienteChat(Protocol):
    """Lo que el orquestador necesita de un LLM (permite usar uno falso en tests)."""

    def chat(self, sistema: str, usuario: str, herramientas: list[dict] | None = None,
             forzar_herramienta: bool = False, temperatura: float = 0.2) -> RespuestaLLM: ...


class ClienteLLM:
    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or config()

    def disponible(self) -> tuple[bool, str]:
        """Verificación rápida del servidor y del modelo configurado."""
        try:
            r = requests.get(f"{self.cfg.llm_url}/models", timeout=3, headers=(
                {"Authorization": f"Bearer {self.cfg.llm_api_key}"} if self.cfg.llm_api_key else {}))
            modelos = [m.get("id") for m in r.json().get("data", [])]
        except (requests.RequestException, ValueError, AttributeError):
            return False, f"Sin conexión con el modelo en {self.cfg.llm_url}."
        if self.cfg.llm_modelo not in modelos:
            return False, f"El servidor responde, pero no tiene cargado '{self.cfg.llm_modelo}'."
        return True, f"Modelo {self.cfg.llm_modelo} disponible."

    def embeddings(self, textos: list[str]) -> list[list[float]]:
        """Vectores del modelo de embeddings configurado (búsqueda por significado)."""
        try:
            r = requests.post(f"{self.cfg.llm_url}/embeddings", timeout=self.cfg.llm_timeout,
                              json={"model": self.cfg.embeddings_modelo, "input": textos},
                              headers=({"Authorization": f"Bearer {self.cfg.llm_api_key}"}
                                       if self.cfg.llm_api_key else {}))
        except requests.RequestException as e:
            raise ErrorLLM(f"No hay conexión con el modelo de embeddings: {e}") from e
        if r.status_code != 200:
            raise ErrorLLM(f"El servidor de embeddings respondió {r.status_code}: {r.text[:200]}")
        try:
            datos = sorted(r.json()["data"], key=lambda d: d.get("index", 0))
            return [d["embedding"] for d in datos]
        except (ValueError, KeyError, TypeError) as e:
            raise ErrorLLM(f"Respuesta de embeddings con formato inesperado: {e}") from e

    def chat(self, sistema: str, usuario: str, herramientas: list[dict] | None = None,
             forzar_herramienta: bool = False, temperatura: float = 0.2) -> RespuestaLLM:
        # Roles separados: las instrucciones van en system; la pregunta y los
        # datos, en user. Nunca se mezclan.
        cuerpo: dict = {
            "model": self.cfg.llm_modelo,
            "temperature": temperatura,
            "messages": [{"role": "system", "content": sistema},
                         {"role": "user", "content": usuario}],
        }
        if herramientas:
            cuerpo["tools"] = herramientas
            cuerpo["tool_choice"] = "required" if forzar_herramienta else "auto"
        cabeceras = {"Content-Type": "application/json"}
        if self.cfg.llm_api_key:
            cabeceras["Authorization"] = f"Bearer {self.cfg.llm_api_key}"

        try:
            r = requests.post(f"{self.cfg.llm_url}/chat/completions", json=cuerpo,
                              headers=cabeceras, timeout=self.cfg.llm_timeout)
        except requests.ConnectionError as e:
            raise ErrorLLM(
                f"No hay conexión con el modelo en {self.cfg.llm_url}. ¿Está encendido el "
                "servidor? En LM Studio: pestaña Developer o `lms server start`."
            ) from e
        except requests.Timeout as e:
            raise ErrorLLM(f"El modelo no respondió en {self.cfg.llm_timeout:.0f} s.") from e
        except requests.RequestException as e:
            raise ErrorLLM(f"Error de red con el modelo: {e}") from e

        if r.status_code != 200:
            raise ErrorLLM(f"El servidor del modelo respondió {r.status_code}: {r.text[:200]}")
        try:
            mensaje = r.json()["choices"][0]["message"]
            llamadas = [
                LlamadaHerramienta(c["function"]["name"],
                                   json.loads(c["function"].get("arguments") or "{}"))
                for c in mensaje.get("tool_calls") or []
            ]
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise ErrorLLM(f"Respuesta del modelo con formato inesperado: {e}") from e
        return RespuestaLLM(texto=mensaje.get("content"), herramientas=llamadas)
