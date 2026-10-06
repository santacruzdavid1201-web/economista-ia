"""
Contexto del Hotel Demo Andino S.A.S. (empresa FICTICIA, ver data/demo/).

Uso desde la terminal, con el servidor del modelo encendido:
    python -m app.demo "¿Mi hotel tiene con qué pagar sus deudas de corto plazo?"
"""
from __future__ import annotations

import sys
from datetime import date

from app.config import RAIZ
from app.orchestrator.tools_registry import ContextoEmpresa
from data_sources.empresa.puc import cargar_historial
from data_sources.externos.referencia import cargar_referencia
from modules.esquema_financiero import Empresa

DEMO = RAIZ / "data" / "demo"
EMPRESA = Empresa(empresa_id="demo-andino", razon_social="Hotel Demo Andino S.A.S.",
                  ciiu="5511", departamento="Nariño", municipio="Pasto")
# Porción de largo plazo de la cuenta 2105 (créditos de remodelación)
LARGO_PLAZO = {date(2023, 12, 31): 600_000_000, date(2024, 12, 31): 520_000_000}


def contexto_demo() -> ContextoEmpresa:
    historial = cargar_historial(
        EMPRESA,
        {fecha: DEMO / f"hotel_demo_andino_{fecha.year}.csv" for fecha in LARGO_PLAZO},
        {fecha: [("obligaciones_financieras_cp", "obligaciones_financieras_lp", monto)]
         for fecha, monto in LARGO_PLAZO.items()},
    )
    referencia = cargar_referencia(EMPRESA.ciiu, historial.ultimo.fecha_corte.year)
    return ContextoEmpresa(historial=historial, referencia=referencia)


if __name__ == "__main__":
    from app.orchestrator.orquestador import responder

    pregunta = " ".join(sys.argv[1:]) or "¿Cómo está mi empresa?"
    r = responder(pregunta, contexto_demo())
    print(f"[{r.origen} · {r.herramienta} · {r.periodo}]\n")
    print(r.texto_completo)
    if r.eventos:
        print("\nEventos:", *r.eventos, sep="\n  ")
