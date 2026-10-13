"""
Módulos que ve el gerente en la portada: nombre, color, ilustración y preguntas
de ejemplo. El enrutador responde cualquier pregunta en cualquier módulo; el
módulo solo organiza la conversación y sugiere preguntas de su tema.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Modulo:
    clave: str
    nombre: str
    resumen: str
    color: str                      # token de estilo.css: menta, coral, salmon, petroleo
    ejemplos: tuple[str, ...] = ()
    activo: bool = True

    @property
    def ilustracion(self) -> str:
        return f"/static/ilustraciones/{self.clave}.svg"


MODULOS = (
    Modulo("balance", "Balance financiero",
           "Liquidez, deuda, rentabilidad y riesgo de la empresa, frente a empresas de su "
           "sector que reportan a Supersociedades.",
           "menta",
           ("¿Cómo está mi empresa?",
            "¿Tengo con qué pagar mis deudas de corto plazo?",
            "¿Cómo estamos frente a otros hoteles en rentabilidad?",
            "¿Por qué cambió la rentabilidad del patrimonio?",
            "¿Me conviene subir las tarifas de las habitaciones?")),
    Modulo("macro", "Entorno macro",
           "Inflación y tasas de interés: cuánto creció la empresa descontando el alza de "
           "precios y cómo le afectan las tasas.",
           "coral",
           ("¿Crecí en términos reales?",
            "¿Mis ventas le ganaron a la inflación?",
            "¿Cómo me afectan las tasas de interés?",
            "¿Qué pasa si las tasas suben 2 puntos?",
            "¿Por qué me afecta que el Banco de la República suba las tasas?")),
    Modulo("proyectos", "Evaluación de proyectos",
           "Valor presente, tasa interna de retorno y sensibilidad de una inversión, como "
           "una remodelación o una ampliación.",
           "salmon", activo=False),
    Modulo("econometria", "Econometría aplicada",
           "Pronósticos de demanda y efecto de precios y promociones con los datos de la "
           "empresa.",
           "petroleo", activo=False),
)
POR_CLAVE = {m.clave: m for m in MODULOS}
