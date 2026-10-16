"""
PMS diario simulado del Hotel Demo Andino S.A.S. (FICTICIO), con proceso generador
conocido (SPEC-series-empresa.md). Sirve de demostración y de verdad para validar los
estimadores del módulo 2: cada test sabe qué elasticidad o qué efecto debe recuperar.
Los parámetros verdaderos están en config/pms_simulado.yaml; sin red (el IPC sale de la
copia versionada), así que la misma semilla da la misma serie en cualquier máquina.

    python -m data_sources.empresa.pms_simulado     # regenera el CSV de la demostración
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from data_sources.externos.series.modelo import Serie
from modules.econometria.calendario import calendario

RAIZ = Path(__file__).resolve().parents[2]
CONFIG = RAIZ / "config" / "pms_simulado.yaml"
IPC = RAIZ / "data" / "series" / "ipc_nacional.json"
CSV_DEMO = RAIZ / "data" / "demo" / "pms_hotel_demo_andino.csv"


def parametros() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def _ipc_diario(fechas: pd.DatetimeIndex) -> np.ndarray:
    """IPC nacional del mes de cada día, relativo al del primer mes (el último publicado
    se repite si la serie no llega hasta el final)."""
    ipc = Serie.model_validate_json(IPC.read_text(encoding="utf-8"))
    mensual = pd.Series({pd.Period(f, "M"): v for f, v in ipc.observaciones})
    valores = mensual.reindex(fechas.to_period("M")).ffill().to_numpy()
    return valores / valores[0]


def simular_pms(p: dict, semilla: int | None = None) -> pd.DataFrame:
    """La serie diaria canónica del PMS (las columnas que espera el almacén)."""
    rng = np.random.default_rng(p["semilla"] if semilla is None else semilla)
    d, t = p["demanda"], p["tarifa"]
    cal = calendario(p["desde"], p["hasta"], p["empresa"]["municipio"])
    fechas, n = cal.index, len(cal)
    efecto = lambda x: np.log1p(x)              # noqa: E731 — +25 % entra como ln(1,25)

    # Tarifa publicada (nominal): base indexada al IPC, revenue management según lo que el
    # hotel espera (calendario), ruido propio, la respuesta a lo no observable y promociones
    rho, sigma = d["ar1"]["rho"], d["ar1"]["sigma"]
    e = rng.normal(0, sigma, n)
    u = np.empty(n)
    u[0] = e[0] / np.sqrt(1 - rho ** 2)          # arranca en la distribución estacionaria
    for k in range(1, n):
        u[k] = rho * u[k - 1] + e[k]
    alta = fechas.month.isin([12, 1, 6, 7])
    baja = (cal["dia_semana"] <= 3).to_numpy() & ~alta & ~cal["festivo"].to_numpy()
    prob = np.where(baja, t["promocion"]["prob_baja"], t["promocion"]["prob_resto"])
    promocion = rng.random(n) < prob
    ln_real = (efecto(t["carnaval"]) * cal["evento_carnaval"]
               + efecto(t["puente"]) * (cal["puente"] | cal["semana_santa"])
               + efecto(t["diciembre"]) * (fechas.month == 12)
               + rng.normal(0, t["ruido"], n)
               + t["respuesta_no_observable"] * u
               + np.log1p(-t["promocion"]["descuento"]) * promocion).to_numpy()
    ipc = _ipc_diario(fechas)
    tarifa = np.round(t["base"] * ipc * np.exp(ln_real), -2)
    c = p["competencia"]
    ln_comp = (0.8 * (ln_real - t["respuesta_no_observable"] * u
                      - np.log1p(-t["promocion"]["descuento"]) * promocion)
               + rng.normal(0, c["ruido"], n))
    competencia = np.round(c["base"] * ipc * np.exp(ln_comp), -2)

    # Demanda latente
    anio = 2 * np.pi * (fechas.dayofyear.to_numpy() - 1) / 365.25
    f = d["fourier"]
    fin_de_semana = (cal["dia_semana"] >= 4).to_numpy()
    ln_d = (d["alfa"]
            + f["cos1"] * np.cos(anio) + f["sen1"] * np.sin(anio)
            + f["cos2"] * np.cos(2 * anio) + f["sen2"] * np.sin(2 * anio)
            + efecto(np.array(d["dia_semana"]))[cal["dia_semana"].to_numpy()]
            + efecto(d["puente"]) * cal["puente"].to_numpy()
            + efecto(d["vispera_festivo"]) * cal["vispera_festivo"].to_numpy()
            + efecto(d["semana_santa"]) * cal["semana_santa"].to_numpy()
            + efecto(d["carnaval"]) * cal["evento_carnaval"].to_numpy()
            + efecto(d["carnaval_central"]) * cal["evento_carnaval_central"].to_numpy()
            + d["elasticidad"] * np.log(tarifa / ipc / t["base"])
            + d["elasticidad_cruzada"] * np.log(competencia / ipc / c["base"])
            + d["tendencia_anual"] * np.arange(n) / 365.25
            + promocion * np.where(fin_de_semana, efecto(d["promocion"]["fin_de_semana"]),
                                   efecto(d["promocion"]["entre_semana"]))
            + efecto(d["remodelacion"]["efecto"]) * (fechas >= pd.Timestamp(d["remodelacion"]["desde"]))
            + u)

    m = p["mantenimiento"]
    fuera = np.where(rng.random(n) < m["probabilidad"], rng.integers(1, m["maximo"] + 1, n), 0)
    disponibles = p["habitaciones"] - fuera
    vendidas = np.minimum(disponibles, rng.poisson(np.exp(ln_d)))
    adr = tarifa * (1 - rng.uniform(0, t["descuento_corporativo_maximo"], n))
    huespedes = vendidas + rng.binomial(vendidas, p["huespedes_por_habitacion"] - 1)
    return pd.DataFrame({
        "fecha": [x.date() for x in fechas],
        "habitaciones_disponibles": disponibles.astype("int64"),
        "habitaciones_vendidas": vendidas.astype("int64"),
        "ingresos_habitaciones": np.round(vendidas * adr),
        "tarifa_publicada": tarifa,
        "tarifa_competencia": competencia,
        "promocion": promocion,
        "huespedes": huespedes.astype("int64"),
    })


def main() -> int:
    serie = simular_pms(parametros())
    serie.to_csv(CSV_DEMO, index=False)
    ocupacion = serie["habitaciones_vendidas"].sum() / serie["habitaciones_disponibles"].sum()
    print(f"{CSV_DEMO.name}: {len(serie)} días del {serie['fecha'].iloc[0]} al "
          f"{serie['fecha'].iloc[-1]}, ocupación media {ocupacion:.1%}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
