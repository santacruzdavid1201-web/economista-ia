"""
Lectura del proyecto que escribe el usuario en la pestaña "Su proyecto": montos
con palabras, porcentajes, años, la inflación (vacía: senda del BanRep) y la
tasa de oportunidad. La usan el tablero y la herramienta del chat, así que los
dos leen el proyecto igual y el orquestador no depende de la interfaz.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
from typing import NamedTuple

from app.orchestrator.lectura import montos
from data_sources.externos import pronostico_banrep
from data_sources.externos.series import catalogo
from modules.proyectos.evaluacion import TASAS
from modules.proyectos.flujo import ErrorProyecto, Proyecto, Senda, crear_proyecto, senda_inflacion

# Valores con que abre el formulario; el aviso de la pestaña dice que son un ejemplo
PROYECTO_EJEMPLO = {
    "nombre": "Remodelación de 10 habitaciones", "inversion": "100 millones", "vida_util": "5",
    "horizonte": "5", "ingresos": "60 millones", "crecimiento_real": "0",
    "costos_variables": "30", "costos_fijos": "10 millones", "capital_trabajo": "10",
    "tarifa_renta": "35", "inflacion": "", "salvamento": "", "tasa_oportunidad": "15",
    "tasa_tipo": "nominal"}
# campo → etiqueta en los mensajes; los opcionales pueden ir vacíos
MONTOS = {"inversion": "la inversión", "ingresos": "los ingresos del primer año",
          "costos_fijos": "los costos fijos", "salvamento": "el valor de salvamento"}
PORCENTAJES = {"crecimiento_real": "Crecimiento real", "costos_variables": "Costos variables",
               "capital_trabajo": "Capital de trabajo", "tarifa_renta": "Tarifa de renta",
               "inflacion": "Inflación esperada", "tasa_oportunidad": "Tasa de oportunidad"}
ANIOS = {"vida_util": "Vida útil", "horizonte": "Horizonte"}
OPCIONALES = {"salvamento", "inflacion", "tasa_oportunidad"}


class ProyectoLeido(NamedTuple):
    proyecto: Proyecto
    senda: Senda
    tasa: float | None            # tasa de oportunidad (fracción); None si no la escribió
    fija: bool                    # la inflación la escribió el usuario
    fuentes: list[str]
    avisos: list[str]
    tipo: str = "nominal"         # de la tasa: "nominal", "real" o "wacc" (ver evaluacion.TASAS)

    @property
    def real(self) -> bool:
        """La tasa es real (o el WACC): descuenta los flujos en pesos de hoy."""
        return TASAS[self.tipo].real


def numero(texto: str) -> float | None:
    """'18', '1,5', '30 %' → número; None si no lo es."""
    try:
        return float(texto.replace("%", "").replace(",", ".").strip())
    except ValueError:
        return None


def leer_proyecto(valores: Mapping[str, object], hoy: date,
                  serie: Callable = catalogo.serie,
                  pronostico: Callable = pronostico_banrep.pronostico) -> ProyectoLeido:
    """
    Los valores del formulario → proyecto validado, senda de inflación y tasa,
    o ErrorProyecto con un mensaje por campo. `serie` y `pronostico`: los tests
    los reemplazan para no usar la red.
    """
    v = {k: str(valores.get(k, "")).strip() for k in PROYECTO_EJEMPLO}
    errores, datos = [], {"nombre": v["nombre"] or "Su proyecto"}
    for campo, etiqueta in MONTOS.items():
        if campo in OPCIONALES and not v[campo]:
            continue
        encontrados = montos(v[campo])
        if len(encontrados) != 1:
            errores.append(f"Escriba {etiqueta} en pesos, por ejemplo 100 millones o 100.000.000.")
        else:
            datos[campo] = encontrados[0]
    for campo, etiqueta in PORCENTAJES.items():
        if campo in OPCIONALES and not v[campo]:
            continue
        if (valor := numero(v[campo])) is None:
            errores.append(f"{etiqueta}: escriba un porcentaje, por ejemplo 30.")
        else:
            datos[campo] = valor / 100
    for campo, etiqueta in ANIOS.items():
        if (valor := numero(v[campo])) is None:
            errores.append(f"{etiqueta}: escriba un número de años, por ejemplo 5.")
        else:
            datos[campo] = valor
    tasa = datos.pop("tasa_oportunidad", None)
    if tasa is not None and not 0 <= tasa <= 1:
        errores.append("La tasa de oportunidad debe estar entre 0 % y 100 %.")
    tipo = v["tasa_tipo"] or "nominal"            # vacío: proyectos guardados antes del campo
    if tipo not in TASAS:
        errores.append("Tipo de tasa: elija nominal, real o el WACC de la empresa.")
    if errores:
        raise ErrorProyecto(errores)
    fija = datos.pop("inflacion", None)
    proyecto = crear_proyecto(**datos)

    if fija is not None:
        return ProyectoLeido(proyecto, senda_inflacion(hoy, proyecto.horizonte, None, 0, fija=fija),
                             tasa, True, [], [], tipo)
    try:
        meta = serie("meta_inflacion", hoy=hoy)
    except catalogo.ErrorSerie as e:
        raise ErrorProyecto([str(e)]) from e
    fuentes, avisos = [meta.fuente], list(meta.advertencias)
    try:
        p = pronostico(hoy)
        fuentes.insert(0, p.fuente)
        avisos += p.advertencias
        inflacion = p.inflacion
    except pronostico_banrep.ErrorPronostico:
        inflacion = None
    # La meta del año puede venir fechada al cierre (futuro): entonces, la última publicada
    vigente = meta.valor_al(hoy)
    vigente = meta.observaciones[-1][1] if vigente is None else vigente
    senda = senda_inflacion(hoy, proyecto.horizonte, inflacion, vigente / 100)
    return ProyectoLeido(proyecto, senda, tasa, False, fuentes, avisos, tipo)
