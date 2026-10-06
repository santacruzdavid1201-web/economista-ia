import os

import pytest
import requests

from app.config import Config, cargar_env, config
from app.llm.client import ClienteLLM, ErrorLLM

CFG = Config(llm_url="http://servidor/v1", llm_modelo="modelo", llm_api_key=None,
             llm_timeout=5, max_caracteres_pregunta=100)


class Respuesta:
    def __init__(self, codigo=200, cuerpo=None):
        self.status_code, self._cuerpo, self.text = codigo, cuerpo, str(cuerpo)

    def json(self):
        if self._cuerpo is None:
            raise ValueError("no es JSON")
        return self._cuerpo


def simular(monkeypatch, resultado):
    enviado = {}

    def post(url, json, headers, timeout):
        enviado.update(url=url, json=json, headers=headers)
        if isinstance(resultado, Exception):
            raise resultado
        return resultado
    monkeypatch.setattr(requests, "post", post)
    return enviado


def test_texto_y_roles(monkeypatch):
    enviado = simular(monkeypatch, Respuesta(cuerpo={"choices": [{"message": {"content": "Hola"}}]}))
    r = ClienteLLM(CFG).chat("instrucciones", "pregunta")
    assert r.texto == "Hola" and r.herramientas == []
    assert enviado["json"]["messages"] == [{"role": "system", "content": "instrucciones"},
                                           {"role": "user", "content": "pregunta"}]
    assert "Authorization" not in enviado["headers"]


def test_llamada_a_herramienta(monkeypatch):
    cuerpo = {"choices": [{"message": {"content": None, "tool_calls": [
        {"function": {"name": "analizar_liquidez", "arguments": '{"periodo": 2024}'}}]}}]}
    enviado = simular(monkeypatch, Respuesta(cuerpo=cuerpo))
    r = ClienteLLM(CFG).chat("s", "u", herramientas=[{"x": 1}], forzar_herramienta=True)
    assert r.herramientas[0].nombre == "analizar_liquidez"
    assert r.herramientas[0].argumentos == {"periodo": 2024}
    assert enviado["json"]["tool_choice"] == "required"


def test_api_key_va_en_cabecera(monkeypatch):
    enviado = simular(monkeypatch, Respuesta(cuerpo={"choices": [{"message": {"content": "x"}}]}))
    cfg = Config(**{**CFG.__dict__, "llm_api_key": "secreta"})
    ClienteLLM(cfg).chat("s", "u")
    assert enviado["headers"]["Authorization"] == "Bearer secreta"


@pytest.mark.parametrize("resultado, mensaje", [
    (requests.ConnectionError(), "lms server start"),
    (requests.Timeout(), "no respondió en 5 s"),
    (Respuesta(codigo=500, cuerpo={"error": "x"}), "respondió 500"),
    (Respuesta(cuerpo=None), "formato inesperado"),
    (Respuesta(cuerpo={"choices": []}), "formato inesperado"),
])
def test_errores_con_mensaje_util(monkeypatch, resultado, mensaje):
    simular(monkeypatch, resultado)
    with pytest.raises(ErrorLLM, match=mensaje):
        ClienteLLM(CFG).chat("s", "u")


def test_env_no_sobrescribe_variables_del_sistema(tmp_path, monkeypatch):
    archivo = tmp_path / ".env"
    archivo.write_text("# comentario\nLLM_MODELO='desde-archivo'\nLLM_URL=http://x/v1\n",
                       encoding="utf-8")
    monkeypatch.setenv("LLM_URL", "http://sistema/v1")
    # setenv + delenv: monkeypatch restaura el estado original al terminar el test
    monkeypatch.setenv("LLM_MODELO", "temporal")
    monkeypatch.delenv("LLM_MODELO")
    cargar_env(archivo)
    assert os.environ["LLM_MODELO"] == "desde-archivo"
    assert os.environ["LLM_URL"] == "http://sistema/v1"


def test_config_por_defecto(monkeypatch):
    for v in ("LLM_URL", "LLM_MODELO", "LLM_API_KEY", "LLM_TIMEOUT"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr("app.config.cargar_env", lambda *a, **k: None)
    c = config()
    assert c.llm_url == "http://localhost:1234/v1" and c.llm_api_key is None
