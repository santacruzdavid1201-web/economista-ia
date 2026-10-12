"""
¿Crecí en términos reales? Separa cuánto del crecimiento de los ingresos es
más actividad y cuánto es solo precios más altos.

Decisiones (SPEC-crecimiento-real.md):
- Los ingresos son un flujo acumulado durante el periodo: se deflactan con el
  IPC PROMEDIO de los meses que cubre cada estado, no con el de diciembre
  (en 2024 el promedio nacional fue 6,61 % y el de diciembre 5,20 %).
- Fórmula exacta: (1 + nominal) / (1 + inflación) − 1. La resta "nominal −
  inflación" se aleja del valor correcto cuando la inflación es alta.
- Solo describe el pasado: dice si los ingresos subieron o cayeron en términos
  reales, sin calificar el resultado.
- Con el IPC general, crecer en términos reales significa que los ingresos
  subieron más que los precios al consumidor, no que se vendió más cantidad:
  las tarifas de la empresa pueden haber subido más o menos que el IPC. La
  distinción va en un hallazgo porque el 7B la ignoró cuando solo estaba en
  los supuestos.
"""
from __future__ import annotations

from datetime import date

from data_sources.externos.series.modelo import Serie
from modules.balance.comun import contexto_base, factor_anual
from modules.base import Indicador, ResultadoModulo, division_segura, formatear
from modules.esquema_financiero import EstadoFinanciero, HistorialFinanciero

SUPUESTO_DEFLACTOR = (
    "Se descontó la inflación con el IPC general: los precios propios de la empresa "
    "(sus tarifas) pueden haber subido más o menos que el promedio de la economía."
)
LIMITE_IPC = (
    "Este crecimiento real descuenta la inflación general (IPC), no las tarifas propias "
    "de la empresa: no permite saber si cambió la cantidad vendida o si sus precios "
    "subieron más o menos que la inflación."
)


def meses_del_periodo(ef: EstadoFinanciero) -> tuple[date, date]:
    """Primer día del primer mes y fecha de corte del estado."""
    inicio = ef.fecha_corte.year * 12 + ef.fecha_corte.month - ef.meses
    return date(inicio // 12, inicio % 12 + 1, 1), ef.fecha_corte


def _pct(valor: float) -> str:
    return formatear(valor, "proporcion")


def _hallazgo(anio_ant: int, anio: int, nominal: float, inflacion: float, real: float,
              geografia: str) -> str:
    de = "nacional" if geografia == "nacional" else f"de {geografia}"
    entre = f"Entre {anio_ant} y {anio} los ingresos operacionales"
    if nominal < 0:
        return (f"{entre} cayeron {_pct(-nominal)} en pesos corrientes; con la inflación "
                f"promedio {de} ({_pct(inflacion)}), la caída real fue {_pct(-real)}.")
    if real < 0:
        return (f"{entre} subieron {_pct(nominal)} en pesos corrientes, menos que la "
                f"inflación promedio {de} ({_pct(inflacion)}): en términos reales cayeron "
                f"{_pct(-real)}.")
    # Nominal y real en paralelo: si el hallazgo compara con la inflación, el 7B pega la
    # comparación al real ("el crecimiento real de 9,3 % superó la inflación de 5,8 %")
    return (f"{entre} crecieron {_pct(nominal)} en pesos corrientes y {_pct(real)} en "
            f"términos reales, es decir, descontada la inflación promedio {de} "
            f"({_pct(inflacion)}).")


def crecimiento_real(historial: HistorialFinanciero, i: int, ipc: Serie) -> ResultadoModulo:
    i = i % len(historial.periodos)
    ef = historial.periodos[i]
    fuentes, supuestos, advertencias = contexto_base(historial, ef)
    fuentes.append(f"IPC {'nacional' if ipc.geografia == 'nacional' else 'de ' + ipc.geografia}: "
                   f"{ipc.fuente}; consultado el {ipc.consultada:%d/%m/%Y}")
    supuestos += [*ipc.supuestos, SUPUESTO_DEFLACTOR]
    advertencias += ipc.advertencias
    nominal = inflacion = real = a_precios_actuales = None
    hallazgos: list[str] = []

    if i == 0:
        advertencias.append("No hay periodo anterior: no se puede calcular el crecimiento "
                            "de los ingresos.")
    else:
        ant = historial.periodos[i - 1]
        ingresos = ef.resultados.ingresos_operacionales * factor_anual(ef)
        ingresos_ant = ant.resultados.ingresos_operacionales * factor_anual(ant)
        cociente = division_segura(ingresos, ingresos_ant)
        nominal = None if cociente is None else cociente - 1
        if cociente is None:
            advertencias.append(f"La empresa no tuvo ingresos operacionales en "
                                f"{ant.fecha_corte.year}: el crecimiento no se puede calcular.")
        if ef.meses < 12 or ant.meses < 12:
            supuestos.append(
                f"Ingresos anualizados a partir de {min(ef.meses, ant.meses)} meses; si el "
                "negocio es estacional, la comparación puede distorsionarse.")

        ipc_actual = ipc.promedio_mensual(*meses_del_periodo(ef))
        ipc_ant = ipc.promedio_mensual(*meses_del_periodo(ant))
        if ipc_actual is None or ipc_ant is None:
            advertencias.append(
                f"La serie del IPC no cubre todos los meses de {ant.fecha_corte.year} y "
                f"{ef.fecha_corte.year} (último dato: {ipc.observaciones[-1][0]:%m/%Y}): la "
                "inflación y el crecimiento real no se pueden calcular.")
        else:
            inflacion = ipc_actual / ipc_ant - 1
            a_precios_actuales = ingresos_ant * ipc_actual / ipc_ant
            if nominal is not None:
                real = (1 + nominal) / (1 + inflacion) - 1
                hallazgos += [_hallazgo(ant.fecha_corte.year, ef.fecha_corte.year, nominal,
                                        inflacion, real, ipc.geografia), LIMITE_IPC]

    indicadores = [
        Indicador(clave="crecimiento_nominal_ingresos",
                  nombre="Crecimiento de los ingresos en pesos corrientes (nominal)",
                  valor=nominal, unidad="proporcion",
                  formula="Ingresos operacionales / Ingresos operacionales del periodo "
                          "anterior − 1 (anualizados si < 12 meses)"),
        Indicador(clave="inflacion_promedio", nombre="Inflación promedio del periodo",
                  valor=inflacion, unidad="proporcion",
                  formula="IPC promedio del periodo / IPC promedio del periodo anterior − 1"),
        Indicador(clave="crecimiento_real_ingresos",
                  nombre="Crecimiento real de los ingresos (descontada la inflación)",
                  valor=real, unidad="proporcion",
                  formula="(1 + crecimiento nominal) / (1 + inflación promedio) − 1"),
        Indicador(clave="ingresos_anteriores_a_precios_actuales",
                  nombre="Ingresos del periodo anterior a precios del actual",
                  valor=a_precios_actuales, unidad="pesos",
                  formula="Ingresos del periodo anterior × IPC promedio del periodo / "
                          "IPC promedio del periodo anterior"),
    ]
    return ResultadoModulo(modulo="macro", analisis="crecimiento_real",
                           fecha_corte=ef.fecha_corte, indicadores=indicadores,
                           hallazgos=hallazgos, supuestos=supuestos, fuentes=fuentes,
                           advertencias=advertencias)
