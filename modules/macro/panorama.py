"""
Panorama macro: nivel y tendencia de la inflación, las tasas, la TRM, el PIB y el
desempleo, con hallazgos redactados en Python (SPEC-mapa-macro.md).

Cada variable se compara con la misma fecha de un año antes: el desempleo no
viene ajustado por estacionalidad, así que compararlo con el mes anterior
confundiría la temporada con la tendencia. No califica ni pronostica: describe.
"""
from __future__ import annotations

from datetime import date

from data_sources.externos.series.modelo import Serie
from modules.base import Indicador, ResultadoModulo, formatear

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
TRIMESTRES = {3: "primer", 6: "segundo", 9: "tercer", 12: "cuarto"}


def _hace_un_anio(f: date) -> date:
    return f.replace(year=f.year - 1, day=min(f.day, 28))


def _mes(f: date) -> str:
    return f"{MESES[f.month - 1]} de {f.year}"


def _anterior(serie: Serie, f: date) -> float | None:
    """Dato del mismo mes un año antes (series mensuales o trimestrales)."""
    return next((v for g, v in serie.observaciones if (g.year, g.month) == (f.year - 1, f.month)),
                None)


def inflacion_anual(ipc: Serie, f: date) -> float | None:
    """IPC del mes frente al del mismo mes del año anterior."""
    actual = next((v for g, v in ipc.observaciones if (g.year, g.month) == (f.year, f.month)), None)
    previo = _anterior(ipc, f)
    return actual / previo - 1 if actual and previo else None


def panorama_macro(ipc: Serie, tasa_politica: Serie, ibr: Serie, trm: Serie, pib: Serie,
                   desempleo: Serie) -> ResultadoModulo:
    indicadores: list[Indicador] = []
    hallazgos: list[str] = []
    advertencias = [a for s in (ipc, tasa_politica, ibr, trm, pib, desempleo) for a in s.advertencias]

    def agregar(clave, nombre, valor, unidad, formula):
        indicadores.append(Indicador(clave=clave, nombre=nombre, valor=valor, unidad=unidad,
                                     formula=formula))

    # Inflación anual: del índice (IPC), último mes y el mismo mes un año antes
    f_ipc = ipc.observaciones[-1][0]
    infl, infl_previa = inflacion_anual(ipc, f_ipc), inflacion_anual(ipc, _hace_un_anio(f_ipc))
    agregar("inflacion_anual", f"Inflación anual a {_mes(f_ipc)}", infl, "tasa",
            "IPC del mes / IPC del mismo mes del año anterior − 1")
    agregar("inflacion_anual_previa", f"Inflación anual a {_mes(_hace_un_anio(f_ipc))}",
            infl_previa, "tasa", "La misma fórmula, un año antes")
    if infl is not None and infl_previa is not None:
        hallazgos.append(f"La inflación anual a {_mes(f_ipc)} fue {formatear(infl, 'tasa')}; "
                         f"un año antes era {formatear(infl_previa, 'tasa')}.")

    # Tasas: último dato y el de un año antes
    f_tp, tp = tasa_politica.observaciones[-1]
    tp_previa = tasa_politica.valor_al(_hace_un_anio(f_tp))
    f_ibr, v_ibr = ibr.observaciones[-1]
    agregar("tasa_politica", "Tasa de política monetaria", tp / 100, "tasa",
            f"Último dato publicado ({f_tp:%d/%m/%Y})")
    agregar("ibr_3m", "IBR a 3 meses", v_ibr / 100, "tasa", f"Último dato publicado ({f_ibr:%d/%m/%Y})")
    if tp_previa is not None:
        agregar("tasa_politica_previa", "Tasa de política monetaria un año antes", tp_previa / 100,
                "tasa", f"Dato al {_hace_un_anio(f_tp):%d/%m/%Y}")
        hallazgos.append(
            f"La tasa de política monetaria del Banco de la República está en "
            f"{formatear(tp / 100, 'tasa')} (al {f_tp:%d/%m/%Y}); un año antes estaba en "
            f"{formatear(tp_previa / 100, 'tasa')}. La IBR a 3 meses está en "
            f"{formatear(v_ibr / 100, 'tasa')}.")

    # TRM: último dato y su variación frente al mismo día de un año antes
    f_trm, v_trm = trm.observaciones[-1]
    trm_previa = trm.valor_al(_hace_un_anio(f_trm))
    agregar("trm", f"TRM al {f_trm:%d/%m/%Y}", v_trm, "pesos", "Pesos por dólar (Superfinanciera)")
    if trm_previa:
        variacion = v_trm / trm_previa - 1
        agregar("variacion_anual_trm", "Variación anual de la TRM", variacion, "proporcion",
                "TRM / TRM del mismo día un año antes − 1")
        hallazgos.append(
            f"La TRM está en {formatear(v_trm, 'pesos')} por dólar (al {f_trm:%d/%m/%Y}): un "
            f"dólar cuesta {formatear(abs(variacion), 'proporcion')} "
            f"{'más' if variacion > 0 else 'menos'} que un año antes, cuando estaba en "
            f"{formatear(trm_previa, 'pesos')}; es decir, el peso "
            # Explícito: con la TRM a la baja el 7B escribió "depreciación del peso"
            f"{'se devaluó (perdió valor)' if variacion > 0 else 'se revaluó (ganó valor)'} "
            "frente al dólar.")

    # PIB: la serie ya es variación anual; el trimestre anterior da la tendencia reciente
    (f_pib, v_pib), (f_pib_ant, v_pib_ant) = pib.observaciones[-1], pib.observaciones[-2]
    agregar("crecimiento_pib", f"Crecimiento anual del PIB, {TRIMESTRES.get(f_pib.month, '')} "
            f"trimestre de {f_pib.year}", v_pib / 100, "tasa",
            "PIB real del trimestre / mismo trimestre del año anterior − 1 (DANE)")
    hallazgos.append(
        f"El PIB creció {formatear(v_pib / 100, 'tasa')} anual en el "
        f"{TRIMESTRES.get(f_pib.month, '')} trimestre de {f_pib.year}; en el trimestre anterior "
        f"había crecido {formatear(v_pib_ant / 100, 'tasa')}.")

    # Desempleo: mismo mes del año anterior (la serie no corrige la estacionalidad)
    f_des, v_des = desempleo.observaciones[-1]
    des_previo = _anterior(desempleo, f_des)
    agregar("desempleo", f"Tasa de desempleo, {_mes(f_des)}", v_des / 100, "tasa",
            "Desocupados / fuerza de trabajo (DANE, total nacional)")
    if des_previo is not None:
        agregar("desempleo_previo", f"Tasa de desempleo, {_mes(_hace_un_anio(f_des))}",
                des_previo / 100, "tasa", "El mismo mes del año anterior")
        hallazgos.append(
            f"La tasa de desempleo nacional fue {formatear(v_des / 100, 'tasa')} en {_mes(f_des)}, "
            f"frente a {formatear(des_previo / 100, 'tasa')} en {_mes(_hace_un_anio(f_des))}; se "
            "compara con el mismo mes porque la serie no corrige la estacionalidad.")

    hallazgos.append("Son datos de la economía colombiana, no de la empresa, y describen lo "
                     "que ya pasó: no son un pronóstico.")
    return ResultadoModulo(
        modulo="macro", analisis="panorama_macro", indicadores=indicadores, hallazgos=hallazgos,
        supuestos=[], advertencias=advertencias,
        fuentes=[s.fuente for s in (ipc, tasa_politica, ibr, trm, pib, desempleo)])
