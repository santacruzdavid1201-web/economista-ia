"""
Orquestador de una pregunta: validar → enrutar (LLM) → calcular (Python) →
redactar (LLM) → verificar cifras (Python) → agregar notas (Python).

Principio central: el LLM elige y redacta; Python calcula y verifica. Si el LLM
falla o inventa cifras dos veces, la respuesta se arma solo con Python.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

import yaml

from app.config import RAIZ, config
from app.llm.client import ClienteChat, ClienteLLM, ErrorLLM
from app.orchestrator.tools_registry import (
    POR_NOMBRE,
    ContextoEmpresa,
    ErrorHerramienta,
    esquema_openai,
    indice_periodo,
)
from app.orchestrator.verificador import cifras_no_respaldadas, respaldo
from app.rag.retriever import Buscador
from modules.base import ResultadoModulo, formatear

PROMPTS = RAIZ / "config" / "prompts"
GLOSARIO = RAIZ / "config" / "glosario.yaml"
SUFIJOS_BENCHMARK = re.compile(r"_(percentil|p25|p75|mediana)$")

FUERA_DE_ALCANCE = (
    "Esa pregunta está fuera de lo que puedo responder con rigor. Para temas legales "
    "o tributarios específicos, lo indicado es consultar a un abogado o a un contador. "
    "Puedo ayudarle con la liquidez, el endeudamiento, la rentabilidad, la rotación de "
    "cartera e inventarios, el riesgo financiero (Z'' de Altman), el análisis DuPont, la "
    "comparación con empresas de su sector y conceptos económicos que afectan a su "
    "negocio (tasas de interés, inflación, precios, endeudamiento)."
)
SIN_FUENTE = (
    "No tengo una fuente revisada para responder eso con rigor, y prefiero no "
    "responder de memoria. Puedo ayudarle con el análisis de los estados financieros "
    "de su empresa o con los conceptos de la base de conocimiento del sistema."
)
AVISO_SIN_REVISAR = "Parte del material usado aún no ha sido revisado por el economista."

Origen = Literal["llm", "respaldo", "sin_llm", "error"]


class ErrorEntrada(ValueError):
    """La pregunta no es válida (mensaje para el usuario)."""


@dataclass
class Respuesta:
    texto: str
    origen: Origen
    herramienta: str | None = None
    periodo: int | None = None
    resultados: list[ResultadoModulo] = field(default_factory=list)
    notas: list[str] = field(default_factory=list)          # supuestos y advertencias
    fuentes: list[str] = field(default_factory=list)        # notas de la base de conocimiento
    eventos: list[str] = field(default_factory=list)        # trazas internas (no se muestran)

    @property
    def texto_completo(self) -> str:
        partes = [self.texto]
        if self.fuentes:
            partes.append("Fuentes:\n" + "\n".join(f"- {f}" for f in self.fuentes))
        if self.notas:
            partes.append("Para tener en cuenta:\n" + "\n".join(f"- {n}" for n in self.notas))
        return "\n\n".join(partes)


# --------------------------------------------------------------------------- #
# Validación de entrada
# --------------------------------------------------------------------------- #
def validar_pregunta(pregunta: object, max_caracteres: int | None = None) -> str:
    if not isinstance(pregunta, str):
        raise ErrorEntrada("La pregunta debe ser texto.")
    # Sin caracteres de control (salvo saltos de línea) ni espacios de sobra
    limpia = "".join(c for c in pregunta
                     if c == "\n" or unicodedata.category(c)[0] != "C").strip()
    limite = max_caracteres or config().max_caracteres_pregunta
    if not limpia:
        raise ErrorEntrada("Escriba una pregunta.")
    if len(limpia) > limite:
        raise ErrorEntrada(f"La pregunta es muy larga ({len(limpia)} caracteres; máximo {limite}).")
    return limpia


# --------------------------------------------------------------------------- #
# Piezas del pipeline
# --------------------------------------------------------------------------- #
def _prompt_enrutador(ctx: ContextoEmpresa, hoy: date) -> str:
    anios = [p.fecha_corte.year for p in ctx.historial.periodos]
    return (PROMPTS / "router.md").read_text(encoding="utf-8").format(
        empresa=ctx.historial.empresa.razon_social, anio_actual=hoy.year,
        anio_pasado=hoy.year - 1, anios_disponibles=", ".join(map(str, anios)),
        anio_reciente=anios[-1])


def _glosario(resultados: list[ResultadoModulo]) -> dict[str, str]:
    definiciones = yaml.safe_load(GLOSARIO.read_text(encoding="utf-8"))
    claves = {SUFIJOS_BENCHMARK.sub("", i.clave) for r in resultados for i in r.indicadores}
    if any(r.analisis == "benchmark" for r in resultados):
        claves.add("percentil")
    return {k: definiciones[k] for k in sorted(claves) if k in definiciones}


def datos_para_redactar(ctx: ContextoEmpresa, resultados: list[ResultadoModulo]) -> dict:
    """Todo lo que el LLM puede usar, con cifras ya formateadas."""
    indicadores = [f"{i.nombre}: {formatear(i.valor, i.unidad)}"
                   for r in resultados if r.analisis != "benchmark"   # sus cifras van en hallazgos
                   for i in r.indicadores if i.valor is not None]
    no_calculables = [i.nombre for r in resultados for i in r.indicadores if i.valor is None]
    corte = next((r.fecha_corte for r in resultados if r.fecha_corte), None)
    datos = {
        "empresa": ctx.historial.empresa.razon_social,
        "fecha_corte": f"{corte:%d/%m/%Y}" if corte else None,
        "indicadores": indicadores,
        "hallazgos": [h for r in resultados for h in r.hallazgos],
        "glosario": _glosario(resultados),
    }
    if no_calculables:
        datos["no_calculables"] = no_calculables
    return datos


def _notas(resultados: list[ResultadoModulo]) -> list[str]:
    vistas: list[str] = []
    for r in resultados:
        for n in [*r.advertencias, *r.supuestos]:
            if n not in vistas:
                vistas.append(n)
    return vistas


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
def _sistema(reglas: str) -> str:
    """Rol del economista (común) + reglas de redacción del tipo de pregunta."""
    return "\n\n".join((PROMPTS / f).read_text(encoding="utf-8") for f in ("rol.md", reglas))


def _redactar(cliente: ClienteChat, sistema: str, usuario: str, permitidas: list[str],
              base: Respuesta) -> str | None:
    """Redacta y verifica cifras; un reintento con la corrección. None si no lo logra."""
    for intento in (1, 2):
        try:
            texto = (cliente.chat(sistema, usuario, temperatura=0.2).texto or "").strip()
        except ErrorLLM as e:
            base.eventos.append(f"redacción: {e}")
            return None
        sobrantes = cifras_no_respaldadas(texto, *permitidas)
        if texto and not sobrantes:
            return texto
        if not texto:
            base.eventos.append(f"intento {intento}: respuesta vacía")
            continue
        base.eventos.append(f"intento {intento}: cifras sin respaldo {sobrantes}")
        usuario += ("\n\nTu respuesta anterior incluía cifras que no están en los datos: "
                    f"{', '.join(sobrantes)}. Reescríbela usando solo cifras que estén ahí.")
    return None


def _conceptual(pregunta: str, cliente: ClienteChat, buscador: Buscador | None) -> Respuesta:
    """Tipo 2: criterio o teoría, respondido solo con la base de conocimiento."""
    base = Respuesta(texto="", origen="llm", herramienta="consulta_conceptual")
    fragmentos = buscador.buscar(pregunta) if buscador else []
    if buscador:
        base.eventos += buscador.eventos
    else:
        base.eventos.append("sin índice de conocimiento: ejecute python -m app.rag.ingest")
    if not fragmentos:
        base.texto, base.origen = SIN_FUENTE, "sin_llm"
        return base
    base.fuentes = [f"{f.titulo} ({f.fuente})" for f in fragmentos]
    if not all(f.revisado for f in fragmentos):
        base.notas.append(AVISO_SIN_REVISAR)
    fuentes = "\n\n".join(f"### {f.titulo}\n{f.texto}" for f in fragmentos)
    usuario = f"PREGUNTA:\n{pregunta}\n\nFUENTES:\n{fuentes}"
    texto = _redactar(cliente, _sistema("redaccion_conceptual.md"), usuario,
                      [fuentes, pregunta], base)
    if texto is None:
        base.texto, base.origen = fuentes.replace("### ", ""), "respaldo"
    else:
        base.texto = texto
    return base


def responder(pregunta: str, ctx: ContextoEmpresa, cliente: ClienteChat | None = None,
              hoy: date | None = None, buscador: Buscador | None = None) -> Respuesta:
    try:
        pregunta = validar_pregunta(pregunta)
    except ErrorEntrada as e:
        return Respuesta(texto=str(e), origen="error")
    cliente = cliente or ClienteLLM()
    hoy = hoy or date.today()

    # 1. Enrutar: cálculo (tipo 1), criterio o teoría (tipo 2) o fuera de alcance (tipo 3)
    try:
        r = cliente.chat(_prompt_enrutador(ctx, hoy), pregunta, herramientas=esquema_openai(),
                         forzar_herramienta=True, temperatura=0)
    except ErrorLLM as e:
        return Respuesta(texto=f"No pude procesar la pregunta: {e}", origen="error",
                         eventos=[f"enrutador: {e}"])
    llamada = r.herramientas[0] if r.herramientas else None
    if llamada is None or llamada.nombre not in POR_NOMBRE:
        nombre = llamada.nombre if llamada else None
        return Respuesta(texto="No logré identificar qué análisis necesita. ¿Puede formular la "
                               "pregunta de otra manera?", origen="error",
                         eventos=[f"enrutador sin herramienta válida: {nombre}"])
    herramienta = POR_NOMBRE[llamada.nombre]
    if herramienta.nombre == "fuera_de_alcance":
        return Respuesta(texto=FUERA_DE_ALCANCE, origen="sin_llm", herramienta=herramienta.nombre)
    if herramienta.nombre == "consulta_conceptual":
        if buscador is None:
            buscador = Buscador.desde_archivo(cliente if hasattr(cliente, "embeddings") else None)
        return _conceptual(pregunta, cliente, buscador)

    # 2. Calcular (Python)
    try:
        i = indice_periodo(ctx.historial, llamada.argumentos.get("periodo"))
        resultados = herramienta.ejecutar(ctx, i, llamada.argumentos)
    except ErrorHerramienta as e:
        return Respuesta(texto=str(e), origen="sin_llm", herramienta=herramienta.nombre)
    base = Respuesta(texto="", origen="llm", herramienta=herramienta.nombre,
                     periodo=ctx.historial.periodos[i].fecha_corte.year,
                     resultados=resultados, notas=_notas(resultados))

    # 3. Redactar y verificar
    datos = json.dumps(datos_para_redactar(ctx, resultados), ensure_ascii=False, indent=1)
    texto = _redactar(cliente, _sistema("redaccion_calculo.md"),
                      f"PREGUNTA:\n{pregunta}\n\nDATOS:\n{datos}", [datos, pregunta], base)
    if texto is None:
        base.texto, base.origen = respaldo(resultados), "respaldo"
    else:
        base.texto = texto
    return base
