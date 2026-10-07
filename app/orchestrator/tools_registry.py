"""
Registro de herramientas: lo único que el LLM puede "hacer" es elegir una de
estas y dar sus parámetros. Cada herramienta llama funciones de Python
probadas y devuelve `ResultadoModulo`; el LLM nunca calcula.

Las descripciones las lee el modelo para elegir: deben decir en lenguaje de
gerente qué pregunta responde cada una, no solo qué indicadores calcula.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from data_sources.externos.referencia import homologar_empresa
from modules.balance.altman import altman
from modules.balance.benchmark import ReferenciaSectorial, comparar
from modules.balance.dupont import dupont, variacion
from modules.balance.razones import actividad, endeudamiento, liquidez, rentabilidad
from modules.base import ResultadoModulo
from modules.esquema_financiero import HistorialFinanciero


class ErrorHerramienta(ValueError):
    """Los parámetros no sirven para los datos disponibles (mensaje para el usuario)."""


@dataclass
class ContextoEmpresa:
    historial: HistorialFinanciero
    referencia: ReferenciaSectorial | None = None


@dataclass(frozen=True)
class Herramienta:
    nombre: str
    descripcion: str
    # (contexto, índice del periodo, argumentos extra del LLM ya validados)
    ejecutar: Callable[[ContextoEmpresa, int, dict], list[ResultadoModulo]]
    usa_periodo: bool = True
    parametros: dict = field(default_factory=dict)       # esquema JSON de argumentos extra


def indice_periodo(historial: HistorialFinanciero, anio: object) -> int:
    """Índice del periodo cuyo corte cae en `anio`; el último si no se indicó."""
    if anio in (None, ""):
        return len(historial.periodos) - 1
    try:
        anio = int(anio)
    except (TypeError, ValueError):
        raise ErrorHerramienta(f"El periodo '{anio}' no es un año válido.") from None
    for i, p in enumerate(historial.periodos):
        if p.fecha_corte.year == anio:
            return i
    disponibles = ", ".join(str(p.fecha_corte.year) for p in historial.periodos)
    raise ErrorHerramienta(f"No hay estados financieros de {anio}. Años disponibles: {disponibles}.")


# Temas de la comparación sectorial: con los 19 indicadores a la vez el modelo
# se confundió; se le pasan solo los del tema preguntado.
TEMAS = {
    "liquidez": (liquidez,),
    "endeudamiento": (endeudamiento,),
    "rentabilidad": (rentabilidad,),
    "actividad": (actividad,),
    "riesgo": (altman,),
}


def _analisis_del_tema(tema: object) -> tuple:
    return TEMAS.get(str(tema), (liquidez, endeudamiento, rentabilidad, actividad, altman))


def _sector(ctx: ContextoEmpresa, i: int, analisis) -> list[ResultadoModulo]:
    if ctx.referencia is None:
        raise ErrorHerramienta("No hay una referencia sectorial para el CIIU de la empresa.")
    comparable = homologar_empresa(ctx.historial)
    return [comparar([f(comparable, i) for f in analisis], ctx.referencia)]


def _con_sector(ctx: ContextoEmpresa, i: int, analisis) -> list[ResultadoModulo]:
    """
    Un análisis temático más su comparación sectorial, si hay referencia. Sin
    ella el modelo calificaba indicadores de "buenos" sin ningún respaldo.
    """
    propio = [analisis(ctx.historial, i)]
    return propio + (_sector(ctx, i, (analisis,)) if ctx.referencia else [])


HERRAMIENTAS: list[Herramienta] = [
    Herramienta(
        "analizar_liquidez",
        "¿Puede la empresa pagar sus deudas de corto plazo? ¿Le alcanza la caja? Razón "
        "corriente, prueba ácida, razón de efectivo y capital de trabajo.",
        lambda c, i, a: _con_sector(c, i, liquidez)),
    Herramienta(
        "analizar_endeudamiento",
        "¿Qué tan endeudada está la empresa? ¿Puede pagar los intereses? Nivel de deuda, "
        "apalancamiento, deuda/EBITDA, cobertura de intereses y carga financiera.",
        lambda c, i, a: _con_sector(c, i, endeudamiento)),
    Herramienta(
        "analizar_rentabilidad",
        "¿Qué tan rentable es el negocio? ¿Cuánto gana por cada peso vendido o invertido? "
        "Márgenes bruto, operacional, EBITDA y neto, ROA y ROE.",
        lambda c, i, a: _con_sector(c, i, rentabilidad)),
    Herramienta(
        "analizar_actividad",
        "¿Cuánto se demoran los clientes en pagar? ¿Cuánto dura el inventario? ¿Qué tan "
        "bien se usan los activos? Rotación, días de cartera, inventario y proveedores.",
        lambda c, i, a: _con_sector(c, i, actividad)),
    Herramienta(
        "analizar_dupont",
        "¿Por qué la rentabilidad del patrimonio (ROE) es la que es, o por qué subió o "
        "bajó? La descompone en margen, rotación de activos y apalancamiento.",
        lambda c, i, a: [dupont(c.historial, i), variacion(c.historial, i)]),
    Herramienta(
        "analizar_riesgo_quiebra",
        "¿Corre la empresa riesgo de quiebra o de dificultades financieras serias? "
        "Z'' de Altman para mercados emergentes.",
        lambda c, i, a: _con_sector(c, i, altman)),
    Herramienta(
        "comparar_con_sector",
        "¿Cómo está la empresa frente a empresas similares de su sector? Ubica cada "
        "indicador en la distribución de los pares.",
        lambda c, i, a: _sector(c, i, _analisis_del_tema(a.get("tema"))),
        parametros={"tema": {
            "type": "string", "enum": [*TEMAS, "todos"],
            "description": "Tema de la comparación; 'todos' si la pregunta es general."}}),
    Herramienta(
        "diagnostico_general",
        "Preguntas amplias: ¿cómo está mi empresa?, ¿cuál es su situación financiera?, "
        "fortalezas y debilidades. Resume liquidez, deuda, rentabilidad y riesgo.",
        lambda c, i, a: [*[f(c.historial, i) for f in (liquidez, endeudamiento, rentabilidad,
                                                    altman)],
                      *(_sector(c, i, _analisis_del_tema("todos")) if c.referencia else [])]),
    Herramienta(
        "consulta_conceptual",
        "Preguntas de criterio económico o teoría que no piden calcular indicadores de la "
        "empresa: qué es un concepto (EBITDA, capital de trabajo, RevPAR), cómo afectan "
        "las tasas de interés o la inflación, si conviene subir precios o endeudarse, "
        "punto de equilibrio.",
        lambda c, i, a: [], usa_periodo=False),
    Herramienta(
        "fuera_de_alcance",
        "La pregunta no es de análisis financiero ni de criterio económico (p. ej. temas "
        "legales o tributarios específicos, trámites, mercadeo, saludos, temas personales).",
        lambda c, i, a: [], usa_periodo=False),
]
POR_NOMBRE = {h.nombre: h for h in HERRAMIENTAS}


def esquema_openai() -> list[dict]:
    """Definición de herramientas en el formato de la API de OpenAI."""
    esquemas = []
    for h in HERRAMIENTAS:
        parametros: dict = {"type": "object", "properties": {}}
        if h.usa_periodo:
            parametros["properties"]["periodo"] = {
                "type": "integer", "description": "Año del corte de los estados financieros"}
        parametros["properties"].update(h.parametros)
        esquemas.append({"type": "function", "function": {
            "name": h.nombre, "description": h.descripcion, "parameters": parametros}})
    return esquemas
