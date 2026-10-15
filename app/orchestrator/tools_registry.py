"""
Registro de herramientas: lo único que el LLM puede "hacer" es elegir una de
estas y dar sus parámetros. Cada herramienta llama funciones de Python
probadas y devuelve `ResultadoModulo`; el LLM nunca calcula.

Las descripciones las lee el modelo para elegir: deben decir en lenguaje de
gerente qué pregunta responde cada una, no solo qué indicadores calcula.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from app.orchestrator.lectura import (
    direccion,
    monto_en_pesos,
    periodicidad,
    sistema,
    tipo_de_tasa,
    tipo_destino,
    unidad_plazo,
    variable_del_proyecto,
)
from app.orchestrator.proyecto import ProyectoLeido, leer_proyecto
from data_sources.externos.referencia import homologar_empresa
from data_sources.externos.series import catalogo
from data_sources.externos.series.modelo import Serie
from modules.balance.altman import altman
from modules.balance.benchmark import ReferenciaSectorial, comparar
from modules.balance.dupont import dupont, variacion
from modules.balance.razones import actividad, endeudamiento, liquidez, rentabilidad
from modules.base import ResultadoModulo
from modules.esquema_financiero import HistorialFinanciero
from modules.macro.crecimiento_real import crecimiento_real, meses_del_periodo
from modules.macro.panorama import panorama_macro
from modules.macro.sensibilidad_tasas import MAX_PUNTOS, ErrorPuntos, sensibilidad_tasas
from modules.proyectos.evaluacion import evaluar
from modules.proyectos.flujo import ErrorProyecto, flujo_caja
from modules.proyectos.matematica_financiera import (
    ErrorCredito,
    ErrorTasa,
    convertir_tasa,
    cuotas_del_plazo,
    simular_credito,
)
from modules.proyectos.sensibilidad import critico_de, escenario, sensibilidad


class ErrorHerramienta(ValueError):
    """Los parámetros no sirven para los datos disponibles (mensaje para el usuario)."""


@dataclass
class ContextoEmpresa:
    historial: HistorialFinanciero
    referencia: ReferenciaSectorial | None = None
    # (variable, geografía, desde) → Serie; los tests lo reemplazan para no usar la red
    serie: Callable[..., Serie] = catalogo.serie


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


def _crecimiento_real(ctx: ContextoEmpresa, i: int) -> list[ResultadoModulo]:
    """IPC de la ciudad de la empresa desde el inicio del periodo anterior."""
    desde, _ = meses_del_periodo(ctx.historial.periodos[max(i, 1) - 1])
    try:
        ipc = ctx.serie("ipc", ctx.historial.empresa.municipio, desde)
    except catalogo.ErrorSerie as e:
        raise ErrorHerramienta(str(e)) from e
    return [crecimiento_real(ctx.historial, i, ipc)]


def _sensibilidad_tasas(ctx: ContextoEmpresa, i: int, argumentos: dict) -> list[ResultadoModulo]:
    """Tasas del día de la consulta (no del corte) y el escenario que pidió el gerente."""
    puntos = argumentos.get("puntos")
    try:
        puntos = None if puntos in (None, "") else float(puntos)
    except (TypeError, ValueError):
        raise ErrorHerramienta(f"El cambio de tasa debe ser un número de puntos entre "
                               f"−{MAX_PUNTOS} y {MAX_PUNTOS} (se recibió '{puntos}').") from None
    try:
        tasas = [ctx.serie(variable, "nacional", None) for variable in ("tasa_politica", "ibr_3m")]
        return [sensibilidad_tasas(ctx.historial, i, *tasas, puntos)]
    except (catalogo.ErrorSerie, ErrorPuntos) as e:
        raise ErrorHerramienta(str(e)) from e


def _decimal(valor: float) -> str:
    return f"{valor:g}".replace(".", ",")


def _credito(ctx: ContextoEmpresa | None, i: int | None, argumentos: dict) -> list[ResultadoModulo]:
    """
    Sin empresa. El modelo da los números de la pregunta (monto, tasa, plazo); el
    tipo de tasa, la unidad del plazo, la periodicidad y el sistema los lee Python.
    """
    pregunta = argumentos.get("pregunta", "")
    monto = monto_en_pesos(pregunta, argumentos.get("monto"))
    if monto is None or monto <= 0:
        raise ErrorHerramienta("¿De cuánto es el crédito? Escriba el monto, por ejemplo: "
                               "200 millones.")
    try:
        tasa = float(argumentos.get("tasa"))
        if tasa < 0:
            raise ValueError
    except (TypeError, ValueError):
        raise ErrorHerramienta("¿A qué tasa de interés? Escríbala con su tipo, por ejemplo: "
                               "18 % EA o 1,5 % mensual.") from None
    tipo, asumido = tipo_de_tasa(pregunta, tasa)
    supuestos = []
    if tipo is None:
        tipo = "EA"
        supuestos.append(f"La pregunta no dice el tipo de la tasa de {_decimal(tasa)} %; se "
                         "asumió efectiva anual. Si es mensual o nominal, la cuota cambia.")
    elif asumido:
        supuestos.append(f"Se asumió que la tasa de {_decimal(tasa)} % anual es efectiva anual, "
                         "como deben informarla los bancos en Colombia.")
    try:
        plazo = float(argumentos.get("plazo"))
    except (TypeError, ValueError):
        plazo = None
    unidad = unidad_plazo(pregunta, plazo) if plazo else None
    if unidad is None:
        raise ErrorHerramienta("¿A qué plazo? Escríbalo en meses o años, por ejemplo: 60 meses "
                               "o 5 años.")
    cada = periodicidad(pregunta)
    try:
        return [simular_credito(monto, tasa / 100, tipo, cuotas_del_plazo(plazo, unidad, cada),
                                cada, sistema(pregunta), supuestos)]
    except (ErrorTasa, ErrorCredito) as e:
        raise ErrorHerramienta(str(e)) from e


SIN_PROYECTO = ("Para evaluar su proyecto, primero escríbalo en la pestaña «Su proyecto» del "
                "módulo Evaluación de proyectos y pulse Calcular (también sirve con el ejemplo).")


def _proyecto_leido(argumentos: dict) -> ProyectoLeido:
    """El último proyecto válido de la sesión, con la tasa de la pregunta si la da."""
    valores = argumentos.get("proyecto")
    if not valores:
        raise ErrorHerramienta(SIN_PROYECTO)
    tasa = argumentos.get("tasa")
    if tasa not in (None, ""):
        valores = {**valores, "tasa_oportunidad": str(tasa)}
    try:
        leido = leer_proyecto(valores, date.today())
    except ErrorProyecto as e:
        raise ErrorHerramienta(" ".join(e.mensajes)) from e
    if leido.tasa is None:
        raise ErrorHerramienta("Su proyecto no tiene tasa de oportunidad. Escríbala en la pestaña "
                               "«Su proyecto» o en la pregunta, por ejemplo: ¿y si mi tasa es 18 %?")
    return leido


def _con_el_proyecto(r: ResultadoModulo, leido: ProyectoLeido, que: str) -> list[ResultadoModulo]:
    """Dice qué proyecto se usó (el nombre lo escribió el usuario: va en las notas, nunca en el
    prompt) y suma las fuentes y avisos de la inflación."""
    r.supuestos.insert(0, f"Se {que} el proyecto «{leido.proyecto.nombre}» de la pestaña Su "
                          "proyecto, con flujos a precios de hoy.")
    r.fuentes, r.advertencias = leido.fuentes, r.advertencias + leido.avisos
    return [r]


def _evaluar_proyecto(ctx: ContextoEmpresa | None, i: int | None,
                      argumentos: dict) -> list[ResultadoModulo]:
    leido = _proyecto_leido(argumentos)
    return _con_el_proyecto(evaluar(flujo_caja(leido.proyecto, leido.senda), leido.tasa), leido,
                            "evaluó")


def _sensibilidad_proyecto(ctx: ContextoEmpresa | None, i: int | None,
                           argumentos: dict) -> list[ResultadoModulo]:
    """Con cifra, el escenario pedido; sin ella, el resumen. La variable y si sube o baja las lee
    Python; el modelo solo da el porcentaje."""
    leido = _proyecto_leido(argumentos)
    pregunta = argumentos.get("pregunta", "")
    variable, asumida = variable_del_proyecto(pregunta)
    cambio = argumentos.get("cambio")
    if cambio not in (None, ""):
        try:
            magnitud = abs(float(cambio))
        except (TypeError, ValueError):
            magnitud = None
        if not magnitud or magnitud > 100:
            raise ErrorHerramienta("El cambio debe ser un porcentaje entre 1 y 100, por ejemplo: "
                                   "¿y si vendo 10 % menos?")
        if variable is None:
            raise ErrorHerramienta("¿Qué dato del proyecto cambia? Por ejemplo: ¿y si vendo 10 % "
                                   "menos? o ¿y si los costos fijos suben 20 %?")
        signo = direccion(pregunta) or (1 if float(cambio) > 0 else -1)
        r = escenario(leido.proyecto, leido.senda, leido.tasa, variable, signo * magnitud / 100)
    else:
        s = sensibilidad(leido.proyecto, leido.senda, leido.tasa)
        r = s.resultado
        # "¿Hasta cuánto pueden caer las ventas?": primero el valor crítico de ese dato
        if variable and (frase := critico_de(s, variable)):
            r.hallazgos.insert(0, frase)
    if asumida:
        r.supuestos.insert(0, "La pregunta dice «costos» sin más: se tomaron los costos variables.")
    return _con_el_proyecto(r, leido, "analizó")


def _convertir(ctx: ContextoEmpresa | None, i: int | None, argumentos: dict) -> list[ResultadoModulo]:
    """Sin empresa. El modelo da la cifra; el tipo de origen y el de destino los lee Python."""
    pregunta = argumentos.get("pregunta", "")
    try:
        tasa = float(argumentos.get("tasa"))
    except (TypeError, ValueError):
        raise ErrorHerramienta("¿Qué tasa quiere convertir? Escríbala con su tipo, por ejemplo: "
                               "2 % mensual o 24 % NMV.") from None
    desde, asumido = tipo_de_tasa(pregunta, tasa)
    if desde is None:
        raise ErrorHerramienta(f"¿Qué tipo de tasa es el {_decimal(tasa)} %? Por ejemplo: 2 % "
                               "mensual, 24 % NMV o 18 % EA. Según el tipo, la equivalencia cambia.")
    supuestos = [f"Se asumió que la tasa de {_decimal(tasa)} % anual es efectiva anual."] \
        if asumido else []
    hacia = tipo_destino(pregunta, tasa)
    if hacia in (None, desde):
        hacia = "MV" if desde == "EA" else "EA"
    try:
        return [convertir_tasa(tasa / 100, desde, hacia, supuestos)]
    except ErrorTasa as e:
        raise ErrorHerramienta(str(e)) from e


PANORAMA = ("ipc", "tasa_politica", "ibr_3m", "trm", "pib", "desempleo")


def _panorama(ctx: ContextoEmpresa | None, i: int | None, argumentos: dict) -> list[ResultadoModulo]:
    """Datos nacionales; no necesita empresa (sin ella se usa el catálogo directamente)."""
    serie = ctx.serie if ctx else catalogo.serie
    try:
        return [panorama_macro(*(serie(v, "nacional", None) for v in PANORAMA))]
    except catalogo.ErrorSerie as e:
        raise ErrorHerramienta(str(e)) from e


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
        "analizar_crecimiento_real",
        "¿Crecí en términos reales? ¿Mis ventas le ganaron a la inflación? ¿Cuánto "
        "crecieron los ingresos descontando el alza de precios? Crecimiento nominal y real "
        "de los ingresos frente al año anterior.",
        lambda c, i, a: _crecimiento_real(c, i)),
    Herramienta(
        "analizar_sensibilidad_tasas",
        "¿Cómo me afectan las tasas de interés? ¿Qué pasa con mis intereses si suben o bajan "
        "las tasas? ¿Cuánto me cuesta cada punto de tasa? Escenarios con los números de la "
        "empresa: gastos financieros y cobertura de intereses si la tasa de la deuda sube o "
        "baja.",
        _sensibilidad_tasas,
        parametros={"puntos": {
            "type": "number",
            "description": "Puntos que sube (positivo) o baja (negativo) la tasa, solo si la "
                           "pregunta da una cifra; p. ej. 5 o -2."}}),
    Herramienta(
        "consultar_panorama_macro",
        "¿Cómo está la economía colombiana? ¿Cuál es la inflación? ¿A cuánto está el dólar "
        "(TRM)? ¿En cuánto está la tasa del Banco de la República? ¿Cuánto creció el PIB? "
        "¿Cómo va el desempleo? Datos actuales de la economía, no de la empresa.",
        _panorama, usa_periodo=False),
    Herramienta(
        "simular_credito",
        "¿Cuánto pago por un crédito o préstamo? ¿De cuánto sería la cuota? ¿Cuántos intereses "
        "pagaría? Cuota fija o abono constante con el monto, la tasa y el plazo que da la "
        "pregunta. No necesita los estados financieros.",
        _credito, usa_periodo=False,
        parametros={
            "monto": {"type": "number",
                      "description": "Monto del crédito como aparece en la pregunta; p. ej. 200 "
                                     "si dice 200 millones."},
            "tasa": {"type": "number",
                     "description": "Tasa de interés en porcentaje, como aparece en la pregunta; "
                                    "p. ej. 18 si dice 18 % EA."},
            "plazo": {"type": "number",
                      "description": "Plazo como aparece en la pregunta, sin convertirlo; p. ej. "
                                     "5 si dice 5 años."}}),
    Herramienta(
        "convertir_tasa",
        "¿A cuánto equivale una tasa de interés en otro tipo? Pasa la tasa que da la pregunta "
        "de mensual a efectiva anual, de nominal (NMV, NTV) a efectiva, de anticipada a vencida, "
        "o al revés. No necesita los estados financieros.",
        _convertir, usa_periodo=False,
        parametros={"tasa": {
            "type": "number",
            "description": "Tasa en porcentaje, como aparece en la pregunta; p. ej. 2 si dice "
                           "2 % mensual."}}),
    Herramienta(
        "analizar_sensibilidad_proyecto",
        "¿Qué pasa con mi proyecto si vendo menos, si suben los costos o si la inversión sale más "
        "cara? ¿Hasta cuánto pueden caer las ventas? ¿Qué variable pesa más? Mueve un dato del "
        "proyecto de la pestaña Su proyecto y dice cómo cambia su valor. No necesita los estados "
        "financieros.",
        _sensibilidad_proyecto, usa_periodo=False,
        parametros={"cambio": {
            "type": "number",
            "description": "Porcentaje que cambia el dato, solo si la pregunta da una cifra; "
                           "p. ej. 10 si dice 10 % menos."}}),
    Herramienta(
        "evaluar_proyecto",
        "¿Me conviene mi proyecto? ¿Crea valor? ¿Cuál es su VPN o su TIR? ¿En cuánto tiempo "
        "recupero la inversión? ¿Y si mi tasa de oportunidad fuera otra? Evalúa el proyecto que el "
        "gerente escribió en la pestaña Su proyecto. No necesita los estados financieros.",
        _evaluar_proyecto, usa_periodo=False,
        parametros={"tasa": {
            "type": "number",
            "description": "Tasa de oportunidad en porcentaje, solo si la pregunta da una cifra; "
                           "p. ej. 18."}}),
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
        "empresa: qué es un concepto (EBITDA, capital de trabajo, RevPAR), por qué las "
        "tasas de interés o la inflación afectan a las empresas, si conviene subir precios "
        "o endeudarse, punto de equilibrio.",
        lambda c, i, a: [], usa_periodo=False),
    Herramienta(
        "conversar",
        "Mensajes que no piden un análisis ni un concepto: saludos, agradecimientos, charla, "
        "qué puede hacer el sistema, comentarios sobre la respuesta anterior (explícamelo más "
        "fácil, ¿por qué?) y temas ajenos a la empresa y a la economía (deportes, noticias, "
        "recetas).",
        lambda c, i, a: [], usa_periodo=False),
    Herramienta(
        "fuera_de_alcance",
        "Asesoría que exige a otro profesional o que el sistema aún no hace: temas legales o "
        "tributarios específicos (impuestos a pagar, despidos, contratos), en qué invertir, "
        "pronósticos de resultados futuros.",
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
