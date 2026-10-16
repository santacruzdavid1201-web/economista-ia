"""
Lectura del proyecto que escribe el usuario en la pestaña "Su proyecto": montos
con palabras, porcentajes, años, la inflación (vacía: senda del BanRep) y la
tasa de oportunidad. También arma el costo de capital con los datos del día.
Los usan el tablero y la herramienta del chat, así que los dos leen igual y el
orquestador no depende de la interfaz.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
from typing import NamedTuple

import yaml

from app.orchestrator.lectura import montos
from data_sources.externos import pronostico_banrep
from data_sources.externos.series import catalogo
from modules.proyectos.evaluacion import TASAS
from modules.base import ResultadoModulo
from modules.esquema_financiero import HistorialFinanciero
from modules.proyectos.flujo import ErrorProyecto, Proyecto, Senda, crear_proyecto, senda_inflacion
from modules.proyectos.wacc import Parametros, costo_capital

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
COSTO_CAPITAL = catalogo.RAIZ / "config" / "costo_capital.yaml"


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
    senda, fuentes, avisos = senda_banrep(hoy, proyecto.horizonte, serie, pronostico)
    return ProyectoLeido(proyecto, senda, tasa, False, fuentes, avisos, tipo)


def senda_banrep(hoy: date, horizonte: int, serie: Callable = catalogo.serie,
                 pronostico: Callable = pronostico_banrep.pronostico
                 ) -> tuple[Senda, list[str], list[str]]:
    """La inflación esperada de cada año (pronóstico del BanRep y meta después), con sus
    fuentes y avisos; ErrorProyecto si no hay meta de inflación."""
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
    return senda_inflacion(hoy, horizonte, inflacion, vigente / 100), fuentes, avisos


def tarifa_de(valores: Mapping[str, object]) -> float:
    """La tarifa de renta del formulario del proyecto (fracción); 35 % si no hay o no es válida."""
    tarifa = numero(str(valores.get("tarifa_renta", "")))
    return tarifa / 100 if tarifa is not None and 0 <= tarifa <= 100 else 0.35


def parametros_costo_capital() -> Parametros:
    """Spread, prima y beta de Damodaran, escritos a mano en config/costo_capital.yaml."""
    c = yaml.safe_load(COSTO_CAPITAL.read_text(encoding="utf-8"))
    return Parametros(c["beta_sin_deuda"], c["spread_incumplimiento"], c["prima_total"],
                      c["fuente"], c["sector"])


def costo_capital_de(historial: HistorialFinanciero | None, hoy: date, tarifa: float,
                     serie: Callable = catalogo.serie,
                     pronostico: Callable = pronostico_banrep.pronostico,
                     parametros: Parametros | None = None) -> ResultadoModulo:
    """
    El costo de capital con los datos del día: TES UVR, IPC, Damodaran y la inflación
    esperada del primer año (la misma senda del flujo). Sin empresa, el costo de los
    activos. ErrorSerie o ErrorProyecto si falta una serie y no hay copia guardada.
    """
    senda, fuentes, avisos = senda_banrep(hoy, 1, serie, pronostico)
    tes = serie("tes_uvr_10", hoy=hoy)
    ipc = serie("ipc", hoy=hoy) if historial is not None else None
    r = costo_capital(tes, parametros or parametros_costo_capital(), tarifa, senda.tasas[0],
                      historial, -1, ipc)
    r.fuentes += fuentes
    r.advertencias += avisos + tes.advertencias + (ipc.advertencias if ipc else [])
    return r
