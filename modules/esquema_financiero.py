"""
Esquema canónico de estados financieros.

Todas las funciones de cálculo del sistema trabajan sobre este esquema y nunca
sobre los datos crudos de la empresa. Los cargadores (data_sources/empresa/)
traducen cada fuente (PUC, Excel propio, taxonomía NIIF de Supersociedades)
a estas clases.

Convenciones:
- Montos en la moneda y unidad indicadas en `Empresa` (por defecto COP, pesos).
- Activos, pasivos, ingresos, costos y gastos se registran en POSITIVO;
  el signo lo pone la fórmula. Solo el patrimonio admite valores negativos.
- Balance = saldos a la fecha de corte (stocks).
- Resultados = acumulado del periodo (flujos).
- Los totales se CALCULAN a partir de las cuentas; nunca se cargan.
- La presentación sigue la NIIF (corriente / no corriente), igual que los
  reportes de Supersociedades, para que el benchmark sectorial sea comparable.
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import (
    BaseModel,
    Field,
    NonNegativeFloat,
    computed_field,
    model_validator,
)

TOLERANCIA_CUADRE = 0.001       # 0,1 % del activo total (redondeos)
TOLERANCIA_UTILIDAD = 0.01      # 1 % para conciliar utilidad del ER vs patrimonio


# --------------------------------------------------------------------------- #
# Metadatos de la empresa
# --------------------------------------------------------------------------- #
class Empresa(BaseModel):
    """Identificación. CIIU y ubicación permiten el benchmark sectorial."""

    empresa_id: str
    razon_social: str
    ciiu: str = Field(pattern=r"^\d{4}$", description="CIIU Rev. 4 A.C., 4 dígitos")
    departamento: str | None = None
    municipio: str | None = None
    grupo_niif: Literal[1, 2, 3] | None = None
    moneda: str = "COP"
    unidad: Literal[1, 1_000, 1_000_000] = 1  # pesos, miles o millones


# --------------------------------------------------------------------------- #
# Estado de situación financiera
# --------------------------------------------------------------------------- #
class BalanceGeneral(BaseModel):
    """Saldos a la fecha de corte."""

    # Activo corriente
    efectivo: NonNegativeFloat = 0
    inversiones_cp: NonNegativeFloat = 0
    deudores_comerciales: NonNegativeFloat = 0
    otros_deudores_cp: NonNegativeFloat = 0
    inventarios: NonNegativeFloat = 0
    otros_activos_cp: NonNegativeFloat = 0
    # Activo no corriente
    ppe: NonNegativeFloat = 0                      # propiedad, planta y equipo (neto)
    intangibles: NonNegativeFloat = 0
    inversiones_lp: NonNegativeFloat = 0
    deudores_lp: NonNegativeFloat = 0
    otros_activos_lp: NonNegativeFloat = 0
    # Pasivo corriente
    obligaciones_financieras_cp: NonNegativeFloat = 0
    proveedores: NonNegativeFloat = 0
    otras_cuentas_por_pagar_cp: NonNegativeFloat = 0
    impuestos_por_pagar: NonNegativeFloat = 0
    obligaciones_laborales: NonNegativeFloat = 0
    otros_pasivos_cp: NonNegativeFloat = 0
    # Pasivo no corriente
    obligaciones_financieras_lp: NonNegativeFloat = 0
    otros_pasivos_lp: NonNegativeFloat = 0
    # Patrimonio (puede ser negativo)
    capital: float = 0
    reservas: float = 0
    resultados_acumulados: float = 0               # ejercicios anteriores
    resultado_ejercicio: float = 0
    otro_patrimonio: float = 0                     # superávit, ORI, revaluaciones

    @computed_field
    @property
    def activo_corriente(self) -> float:
        return (self.efectivo + self.inversiones_cp + self.deudores_comerciales
                + self.otros_deudores_cp + self.inventarios + self.otros_activos_cp)

    @computed_field
    @property
    def activo_no_corriente(self) -> float:
        return (self.ppe + self.intangibles + self.inversiones_lp
                + self.deudores_lp + self.otros_activos_lp)

    @computed_field
    @property
    def activo_total(self) -> float:
        return self.activo_corriente + self.activo_no_corriente

    @computed_field
    @property
    def pasivo_corriente(self) -> float:
        return (self.obligaciones_financieras_cp + self.proveedores
                + self.otras_cuentas_por_pagar_cp + self.impuestos_por_pagar
                + self.obligaciones_laborales + self.otros_pasivos_cp)

    @computed_field
    @property
    def pasivo_no_corriente(self) -> float:
        return self.obligaciones_financieras_lp + self.otros_pasivos_lp

    @computed_field
    @property
    def pasivo_total(self) -> float:
        return self.pasivo_corriente + self.pasivo_no_corriente

    @computed_field
    @property
    def deuda_financiera(self) -> float:
        return self.obligaciones_financieras_cp + self.obligaciones_financieras_lp

    @computed_field
    @property
    def patrimonio_total(self) -> float:
        return (self.capital + self.reservas + self.resultados_acumulados
                + self.resultado_ejercicio + self.otro_patrimonio)


# --------------------------------------------------------------------------- #
# Estado de resultados
# --------------------------------------------------------------------------- #
class EstadoResultados(BaseModel):
    """Acumulado del periodo."""

    ingresos_operacionales: NonNegativeFloat
    costo_ventas: NonNegativeFloat = 0
    gastos_administracion: NonNegativeFloat = 0
    gastos_ventas: NonNegativeFloat = 0
    otros_ingresos: NonNegativeFloat = 0
    otros_gastos: NonNegativeFloat = 0
    ingresos_financieros: NonNegativeFloat = 0
    gastos_financieros: NonNegativeFloat = 0
    impuesto_renta: NonNegativeFloat = 0
    # Informativo: ya está incluido en costos y gastos, NO se resta otra vez.
    depreciacion_amortizacion: NonNegativeFloat = 0

    @computed_field
    @property
    def utilidad_bruta(self) -> float:
        return self.ingresos_operacionales - self.costo_ventas

    @computed_field
    @property
    def utilidad_operacional(self) -> float:
        return self.utilidad_bruta - self.gastos_administracion - self.gastos_ventas

    @computed_field
    @property
    def ebitda(self) -> float:
        return self.utilidad_operacional + self.depreciacion_amortizacion

    @computed_field
    @property
    def utilidad_antes_impuestos(self) -> float:
        return (self.utilidad_operacional + self.otros_ingresos - self.otros_gastos
                + self.ingresos_financieros - self.gastos_financieros)

    @computed_field
    @property
    def utilidad_neta(self) -> float:
        return self.utilidad_antes_impuestos - self.impuesto_renta


# --------------------------------------------------------------------------- #
# Flujo de efectivo (opcional en el MVP)
# --------------------------------------------------------------------------- #
class FlujoEfectivo(BaseModel):
    """Totales por actividad; admiten signo."""

    operacion: float
    inversion: float
    financiacion: float

    @computed_field
    @property
    def variacion_efectivo(self) -> float:
        return self.operacion + self.inversion + self.financiacion


# --------------------------------------------------------------------------- #
# Un periodo completo
# --------------------------------------------------------------------------- #
class EstadoFinanciero(BaseModel):
    fecha_corte: date
    meses: int = Field(12, ge=1, le=12)
    balance: BalanceGeneral
    resultados: EstadoResultados
    flujo: FlujoEfectivo | None = None

    @model_validator(mode="after")
    def _verificar_cuadre(self) -> "EstadoFinanciero":
        """Identidad contable: si no cuadra, los datos no sirven y se rechazan."""
        b = self.balance
        diferencia = b.activo_total - (b.pasivo_total + b.patrimonio_total)
        if abs(diferencia) > TOLERANCIA_CUADRE * max(b.activo_total, 1):
            raise ValueError(
                f"El balance al {self.fecha_corte} no cuadra: "
                f"activo − (pasivo + patrimonio) = {diferencia:,.0f}"
            )
        return self

    def advertencias(self) -> list[str]:
        """Problemas que no invalidan los datos pero deben informarse."""
        avisos: list[str] = []
        b, r = self.balance, self.resultados

        # 1. Utilidad del estado de resultados vs la registrada en el patrimonio
        un, re = r.utilidad_neta, b.resultado_ejercicio
        if abs(un - re) > TOLERANCIA_UTILIDAD * max(abs(un), abs(re), 1):
            avisos.append(
                f"La utilidad neta calculada ({un:,.0f}) no coincide con el "
                f"resultado del ejercicio en el patrimonio ({re:,.0f})."
            )

        # 2. Patrimonio negativo
        if b.patrimonio_total < 0:
            avisos.append("El patrimonio es negativo: la empresa debe más de lo que tiene.")

        # 3. Periodo incompleto
        if self.meses < 12:
            avisos.append(
                f"Periodo de {self.meses} meses: las rotaciones y rentabilidades "
                "se anualizan y pueden tener estacionalidad."
            )

        # 4. Cuentas no reportadas (quedaron en 0 por defecto, no por dato)
        faltantes = [
            c for c in BalanceGeneral.model_fields if c not in b.model_fields_set
        ] + [
            c for c in EstadoResultados.model_fields if c not in r.model_fields_set
        ]
        if faltantes:
            avisos.append(
                "Cuentas no reportadas, asumidas en cero: " + ", ".join(faltantes) + "."
            )
        return avisos


# --------------------------------------------------------------------------- #
# Serie histórica de una empresa
# --------------------------------------------------------------------------- #
class HistorialFinanciero(BaseModel):
    empresa: Empresa
    periodos: list[EstadoFinanciero] = Field(min_length=1)

    @model_validator(mode="after")
    def _ordenar(self) -> "HistorialFinanciero":
        self.periodos.sort(key=lambda p: p.fecha_corte)
        fechas = [p.fecha_corte for p in self.periodos]
        if len(fechas) != len(set(fechas)):
            raise ValueError("Hay periodos repetidos con la misma fecha de corte.")
        return self

    @property
    def ultimo(self) -> EstadoFinanciero:
        return self.periodos[-1]

    def saldo_promedio(self, cuenta: str, i: int = -1) -> tuple[float, bool]:
        """
        Promedio del saldo de una cuenta de balance entre el periodo i y el anterior.

        Las razones que mezclan un flujo (ventas, utilidad) con un saldo (activos,
        inventarios) deben usar el saldo promedio del periodo. Si no hay periodo
        anterior se usa el saldo final y el segundo valor devuelto es False, para
        que el módulo lo registre como supuesto.
        """
        i = i % len(self.periodos)
        actual = getattr(self.periodos[i].balance, cuenta)
        if i == 0:
            return actual, False
        anterior = getattr(self.periodos[i - 1].balance, cuenta)
        return (actual + anterior) / 2, True
