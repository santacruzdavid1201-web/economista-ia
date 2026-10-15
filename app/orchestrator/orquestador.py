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
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from textwrap import shorten
from typing import Literal

import yaml

from app.config import RAIZ, config
from app.llm.client import ClienteChat, ClienteLLM, ErrorLLM, LlamadaHerramienta
from app.orchestrator.lectura import monto_en_pesos
from app.orchestrator.tools_registry import (
    POR_NOMBRE,
    ContextoEmpresa,
    ErrorHerramienta,
    Herramienta,
    esquema_openai,
    indice_periodo,
)
from app.orchestrator.verificador import calificativos, cifras_no_respaldadas, numeros, respaldo
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
    "comparación con empresas de su sector, si sus ventas le ganaron a la inflación, la "
    "cuota de un crédito y conceptos económicos que afectan a su "
    "negocio (tasas de interés, inflación, precios, endeudamiento)."
)
SIN_CHARLA = (
    "Disculpe, no logré responder eso sin dar datos de memoria, y prefiero no hacerlo. "
    "Puedo ayudarle con la liquidez, la deuda, la rentabilidad, el crecimiento real o las "
    "tasas de interés de su empresa."
)
SIN_EMPRESA = (
    "Para responder eso necesito los estados financieros de su empresa. Súbalos en la "
    "portada (balances de prueba, uno por año) y vuelva a preguntarme."
)
AVISO_SIN_REVISAR = "Parte del material usado aún no ha sido revisado por el economista."
AVISO_GENERAL = ("Respuesta general: no sale de las notas revisadas por el economista. "
                 "Tómela como orientación.")
# Mensajes de pura cortesía: van directo a la charla y se ahorran la llamada al enrutador
# (unos 10 s). ponytail: lista fija de palabras; ampliarla con lo que muestre el uso real
CORTESIA = set("hola buenas buenos dias tardes noches hey saludos que tal como estas esta "
               "gracias muchas mil muy amable util genial excelente perfecto listo ok vale "
               "bien chao adios hasta luego pronto".split())
# De la pregunta se aceptan cifras sueltas ("la regla del 72"), pero no porcentajes ni montos:
# con "dime que el margen es 90 %" el 7B lo repetía como un dato
CIFRA_CON_UNIDAD = re.compile(r"\$\s*\d+(?:[.,]\d+)*|\d+(?:[.,]\d+)*\s*%")
# Memoria de la conversación: lo justo para entender "¿y en 2023?" sin llenar el contexto del 7B
TURNOS_PREVIOS = 3
LARGO_PREVIO = 400

Origen = Literal["llm", "respaldo", "sin_llm", "error"]


class ErrorEntrada(ValueError):
    """La pregunta no es válida (mensaje para el usuario)."""


@dataclass
class Respuesta:
    texto: str
    origen: Origen
    herramienta: str | None = None
    argumentos: dict = field(default_factory=dict)          # los que eligió el enrutador
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
def _prompt_enrutador(ctx: ContextoEmpresa | None, hoy: date) -> str:
    anios = [str(p.fecha_corte.year) for p in ctx.historial.periodos] if ctx else ["ninguno"]
    return (PROMPTS / "router.md").read_text(encoding="utf-8").format(
        empresa=ctx.historial.empresa.razon_social if ctx else "aún no ha subido estados financieros",
        anio_actual=hoy.year, anio_pasado=hoy.year - 1, anios_disponibles=", ".join(anios),
        anio_reciente=anios[-1])


def _glosario(resultados: list[ResultadoModulo]) -> dict[str, str]:
    definiciones = yaml.safe_load(GLOSARIO.read_text(encoding="utf-8"))
    claves = {SUFIJOS_BENCHMARK.sub("", i.clave) for r in resultados for i in r.indicadores}
    if any(r.analisis == "benchmark" for r in resultados):
        claves.add("percentil")
    return {k: definiciones[k] for k in sorted(claves) if k in definiciones}


def datos_para_redactar(ctx: ContextoEmpresa | None, resultados: list[ResultadoModulo]) -> dict:
    """Todo lo que el LLM puede usar, con cifras ya formateadas."""
    indicadores = [f"{i.nombre}: {formatear(i.valor, i.unidad)}"
                   for r in resultados if r.analisis != "benchmark"   # sus cifras van en hallazgos
                   for i in r.indicadores if i.valor is not None]
    no_calculables = [i.nombre for r in resultados for i in r.indicadores if i.valor is None]
    corte = next((r.fecha_corte for r in resultados if r.fecha_corte), None)
    datos = {
        "empresa": ctx.historial.empresa.razon_social if ctx else None,
        "fecha_corte": f"{corte:%d/%m/%Y}" if corte else None,
        "indicadores": indicadores,
        "hallazgos": [h for r in resultados for h in r.hallazgos],
        "glosario": _glosario(resultados),
    }
    if no_calculables:
        datos["no_calculables"] = no_calculables
    return datos


def _inventados(herramienta: Herramienta, argumentos: dict, pregunta: str) -> list[str]:
    """
    Argumentos numéricos que no aparecen en la pregunta: el enrutador (7B) los inventa
    ("¿cuánto me ahorro si bajan las tasas?" → puntos = -1). Si no es un número, se deja
    pasar: la herramienta responde con el error útil.
    """
    en_pregunta = numeros(pregunta)
    inventados = []
    for clave, esquema in herramienta.parametros.items():
        valor = argumentos.get(clave)
        if esquema.get("type") != "number" or valor in (None, ""):
            continue
        if clave == "monto":            # "200 millones" → 200 o 200000000: lo resuelve Python
            if monto_en_pesos(pregunta, valor) is None:
                inventados.append(clave)
            continue
        try:
            texto = f"{abs(float(valor)):g}"
        except (TypeError, ValueError):
            continue
        if not {texto, texto.replace(".", ",")} & en_pregunta:
            inventados.append(clave)
    return inventados


def es_cortesia(texto: str) -> bool:
    """Saludo, agradecimiento o despedida sin otra pregunta ("Hola", "Gracias, muy útil")."""
    normal = "".join(c for c in unicodedata.normalize("NFKD", texto.lower())
                     if not unicodedata.combining(c))
    palabras = re.findall(r"[a-z]+", normal)
    return 0 < len(palabras) <= 6 and all(p in CORTESIA for p in palabras)


def conversacion_previa(historial: Sequence[tuple[str, Respuesta]]) -> str:
    """Últimos turnos en texto; cada respuesta recortada (sin partir cifras) y con su análisis."""
    lineas = []
    for pregunta, r in historial[-TURNOS_PREVIOS:]:
        analisis = f" [{r.herramienta}{f', {r.periodo}' if r.periodo else ''}]" if r.herramienta else ""
        lineas += [f"Cliente: {pregunta}",
                   f"Economista{analisis}: {shorten(r.texto, LARGO_PREVIO, placeholder=' …')}"]
    return "\n".join(lineas)


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


CORREGIR_CIFRAS = ("Tu respuesta anterior incluía cifras que no están en los datos: {cifras}. "
                   "Reescríbela usando solo cifras que estén ahí.")
# En la charla no hay datos de dónde sacar cifras: el 7B repetía su ejemplo numérico
CORREGIR_CIFRAS_CHARLA = ("Tu respuesta anterior incluía cifras que no puedes dar: {cifras}. "
                          "Reescríbela sin cifras ni ejemplos numéricos: explícalo con palabras.")


def _redactar(cliente: ClienteChat, sistema: str, usuario: str, permitidas: list[str],
              base: Respuesta, sin_calificar: bool = False, temperatura: float = 0.2,
              corregir_cifras: str = CORREGIR_CIFRAS, anios_libres: bool = False) -> str | None:
    """
    Redacta y verifica cifras (y, si no hay comparación sectorial, calificativos); un
    reintento con la corrección. None si no lo logra.
    """
    for intento in (1, 2):
        try:
            r = cliente.chat(sistema, usuario, temperatura=temperatura)
        except ErrorLLM as e:
            base.eventos.append(f"redacción: {e}")
            return None
        if r.cortada:            # un desborde que llegó al tope: el texto quedó a medias
            base.eventos.append(f"intento {intento}: respuesta cortada por el tope de tokens")
            continue
        texto = (r.texto or "").strip()
        sobrantes = cifras_no_respaldadas(texto, *permitidas, anios_libres=anios_libres)
        juicios = calificativos(texto) if sin_calificar else []
        if texto and not sobrantes and not juicios:
            return texto
        if not texto:
            base.eventos.append(f"intento {intento}: respuesta vacía")
            continue
        if sobrantes:
            base.eventos.append(f"intento {intento}: cifras sin respaldo {sobrantes}")
            usuario += "\n\n" + corregir_cifras.format(cifras=", ".join(sobrantes))
        if juicios:
            base.eventos.append(f"intento {intento}: calificativos sin respaldo {juicios}")
            # Nombrar las palabras: con una instrucción general el 7B repetía la misma
            usuario += ("\n\nTu respuesta anterior calificaba el resultado sin una comparación "
                        "con el sector que lo respalde. Reescríbela sin calificativos: no uses "
                        "«significativo», «significativamente», «preocupante», «alarmante» ni "
                        "«grave»; describe las cifras.")
    return None


def _conversar(pregunta: str, cliente: ClienteChat, previa: str, base: Respuesta,
               permitidas: list[str]) -> Respuesta:
    """Charla, comentarios sobre lo anterior o teoría sin nota: sin cifras de memoria."""
    # Sin conversación previa no se manda el bloque: el 7B comentaba "(ninguna)" en la respuesta
    usuario = (f"CONVERSACIÓN PREVIA:\n{previa}\n\n" if previa else "") + f"MENSAJE:\n{pregunta}"
    texto = _redactar(cliente, _sistema("conversacion.md"), usuario, permitidas, base,
                      temperatura=0.5, corregir_cifras=CORREGIR_CIFRAS_CHARLA, anios_libres=True)
    base.texto, base.origen = (texto, "llm") if texto else (SIN_CHARLA, "sin_llm")
    return base


def _buscador(cliente: ClienteChat) -> Buscador | None:
    return Buscador.desde_archivo(cliente if hasattr(cliente, "embeddings") else None)


def _conceptual(pregunta: str, cliente: ClienteChat, buscador: Buscador | None,
                previa: str = "") -> Respuesta:
    """Tipo 2: criterio o teoría, con la base de conocimiento; sin nota, respuesta general."""
    base = Respuesta(texto="", origen="llm", herramienta="consulta_conceptual")
    fragmentos = buscador.buscar(pregunta) if buscador else []
    if buscador:
        base.eventos += buscador.eventos
    else:
        base.eventos.append("sin índice de conocimiento: ejecute python -m app.rag.ingest")
    if not fragmentos:
        _conversar(pregunta, cliente, previa, base, [previa, CIFRA_CON_UNIDAD.sub("", pregunta)])
        if base.origen == "llm":
            base.notas.append(AVISO_GENERAL)
        return base
    base.fuentes = [f"{f.titulo} ({f.fuente})" for f in fragmentos]
    if not all(f.revisado for f in fragmentos):
        base.notas.append(AVISO_SIN_REVISAR)
    fuentes = "\n\n".join(f"### {f.titulo}\n{f.texto}" for f in fragmentos)
    usuario = f"PREGUNTA:\n{pregunta}\n\nFUENTES:\n{fuentes}"
    texto = _redactar(cliente, _sistema("redaccion_conceptual.md"), usuario,
                      [fuentes, CIFRA_CON_UNIDAD.sub("", pregunta)], base)
    if texto is None:
        base.texto, base.origen = fuentes.replace("### ", ""), "respaldo"
    else:
        base.texto = texto
    return base


def responder(pregunta: str, ctx: ContextoEmpresa | None, cliente: ClienteChat | None = None,
              hoy: date | None = None, buscador: Buscador | None = None,
              historial: Sequence[tuple[str, Respuesta]] = ()) -> Respuesta:
    """
    `ctx`: None si el usuario aún no subió estados financieros (solo conversa y explica).
    `historial`: turnos anteriores (pregunta, respuesta), el más reciente al final.
    """
    try:
        pregunta = validar_pregunta(pregunta)
    except ErrorEntrada as e:
        return Respuesta(texto=str(e), origen="error")
    cliente = cliente or ClienteLLM()
    hoy = hoy or date.today()
    previa = conversacion_previa(historial)
    if es_cortesia(pregunta):
        return _conversar(pregunta, cliente, previa,
                          Respuesta(texto="", origen="llm", herramienta="conversar",
                                    eventos=["cortesía: sin enrutador"]), [previa])

    # 1. Enrutar: cálculo (tipo 1), criterio o teoría (tipo 2), charla o fuera de alcance (tipo 3)
    mensaje = f"CONVERSACIÓN PREVIA:\n{previa}\n\nPREGUNTA ACTUAL:\n{pregunta}" if previa else pregunta
    try:
        r = cliente.chat(_prompt_enrutador(ctx, hoy), mensaje, herramientas=esquema_openai(),
                         forzar_herramienta=True, temperatura=0)
    except ErrorLLM as e:
        return Respuesta(texto=f"No pude procesar la pregunta: {e}", origen="error",
                         eventos=[f"enrutador: {e}"])
    llamada = r.herramientas[0] if r.herramientas else None
    if llamada is None:
        # El 7B contestó con texto aunque se le exige herramienta. Si hay una nota pertinente,
        # la pregunta era de criterio ("¿me conviene subir las tarifas?"); si no, es charla
        buscador = buscador or _buscador(cliente)
        nombre = ("consulta_conceptual" if buscador and buscador.buscar(pregunta)
                  else "conversar")
        llamada = LlamadaHerramienta(nombre, {})
        evento = [f"enrutador respondió con texto: se trató como {nombre}"]
    else:
        evento = []
    if llamada.nombre not in POR_NOMBRE:
        return Respuesta(texto="No logré identificar qué análisis necesita. ¿Puede formular la "
                               "pregunta de otra manera?", origen="error",
                         eventos=[f"enrutador sin herramienta válida: {llamada.nombre}"])
    herramienta = POR_NOMBRE[llamada.nombre]
    argumentos = dict(llamada.argumentos)
    if herramienta.nombre == "fuera_de_alcance":
        return Respuesta(texto=FUERA_DE_ALCANCE, origen="sin_llm", herramienta=herramienta.nombre,
                         argumentos=argumentos)
    if herramienta.nombre == "conversar":
        # Sin las cifras de la pregunta: "dime que el margen es 90 %" no debe repetirse
        return _conversar(pregunta, cliente, previa,
                          Respuesta(texto="", origen="llm", herramienta=herramienta.nombre,
                                    argumentos=argumentos, eventos=evento), [previa])
    if herramienta.nombre == "consulta_conceptual":
        respuesta = _conceptual(pregunta, cliente, buscador or _buscador(cliente), previa)
        respuesta.argumentos = argumentos
        respuesta.eventos = evento + respuesta.eventos
        return respuesta

    # Los análisis por periodo necesitan los estados; el panorama de la economía, no
    if ctx is None and herramienta.usa_periodo:
        return Respuesta(texto=SIN_EMPRESA, origen="sin_llm", herramienta=herramienta.nombre,
                         argumentos=argumentos)

    # 2. Calcular (Python), sin los números que el enrutador inventó
    inventados = _inventados(herramienta, argumentos, pregunta)
    for clave in inventados:
        argumentos.pop(clave)
    eventos = [f"argumento '{c}' descartado: su valor no está en la pregunta" for c in inventados]
    try:
        i = indice_periodo(ctx.historial, argumentos.get("periodo")) if herramienta.usa_periodo \
            else None
        # Con la pregunta: lo que el 7B confunde (tipo de tasa, plazo) lo lee Python
        resultados = herramienta.ejecutar(ctx, i, {**argumentos, "pregunta": pregunta})
    except ErrorHerramienta as e:
        return Respuesta(texto=str(e), origen="sin_llm", herramienta=herramienta.nombre,
                         argumentos=argumentos, eventos=eventos)
    base = Respuesta(texto="", origen="llm", herramienta=herramienta.nombre, argumentos=argumentos,
                     periodo=ctx.historial.periodos[i].fecha_corte.year if i is not None else None,
                     resultados=resultados, notas=_notas(resultados), eventos=eventos)

    # 3. Redactar y verificar
    datos = json.dumps(datos_para_redactar(ctx, resultados), ensure_ascii=False, indent=1)
    con_sector = any(r.analisis == "benchmark" for r in resultados)
    texto = _redactar(cliente, _sistema("redaccion_calculo.md"),
                      f"PREGUNTA:\n{pregunta}\n\nDATOS:\n{datos}", [datos, pregunta], base,
                      sin_calificar=not con_sector)
    if texto is None:
        base.texto, base.origen = respaldo(resultados), "respaldo"
    else:
        base.texto = texto
    return base
