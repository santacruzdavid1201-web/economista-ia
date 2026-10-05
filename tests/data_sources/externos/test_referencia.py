from pathlib import Path

import pandas as pd
import pytest

from data_sources.externos.referencia import (
    SUPUESTO_HOMOLOGACION,
    construir_referencia,
    homologar_empresa,
    indicadores_par,
)
from data_sources.externos.supersociedades import construir_historiales
from modules.balance.benchmark import DIRECCION, comparar
from modules.balance.razones import actividad, liquidez
from tests.conftest import hacer_historial

DATOS = Path(__file__).parent / "datos"


@pytest.fixture(scope="module")
def pares():
    leer = lambda n: pd.read_csv(DATOS / f"{n}.csv", dtype=str)  # noqa: E731
    historiales, exclusiones = construir_historiales(
        leer("caratula"), leer("esf"), leer("eri"), leer("efe"))
    return historiales, exclusiones


def test_indicadores_par_usa_las_claves_del_benchmark(pares):
    h = next(h for h in pares[0] if h.empresa.empresa_id == "800046878")
    ind = indicadores_par(h, 2024)
    assert set(ind) <= set(DIRECCION)
    assert ind["razon_corriente"] == pytest.approx(1_200_623 / 711_025)
    assert ind["margen_bruto"] is not None
    assert indicadores_par(h, 2019) is None


def test_par_sin_costo_de_ventas_no_entra_a_margen_bruto(pares):
    h = next(h for h in pares[0] if h.empresa.empresa_id == "800230527")
    ind = indicadores_par(h, 2024)
    assert ind["margen_bruto"] is None
    assert ind["dias_inventario"] is None
    assert ind["margen_operacional"] is not None


def test_referencia_cuenta_y_documenta(pares):
    historiales, exclusiones = pares
    ref = construir_referencia(historiales, 2024, "Hoteles (prueba)", ["5511"], exclusiones)
    n = len(historiales)
    assert all(len(v) == n for v in ref.valores.values())
    assert any(f"{n} empresas" in f and "1 excluidas" in f for f in ref.filtros)
    assert any("sin costo de ventas" in f for f in ref.filtros)
    assert any("taxonomía NIIF" in f for f in ref.filtros)


def test_la_empresa_no_es_su_propio_par(pares):
    historiales, _ = pares
    ref = construir_referencia(historiales, 2024, "Hoteles (prueba)", ["5511"],
                               excluir_nit="800046878")
    assert all(len(v) == len(historiales) - 1 for v in ref.valores.values())
    assert any("propios pares" in f for f in ref.filtros)


def test_homologar_agrega_cartera_y_proveedores():
    h = hacer_historial(balance={"otros_deudores_cp": 100, "otras_cuentas_por_pagar_cp": 30,
                                 "capital": 1_070})
    hh = homologar_empresa(h)
    b, original = hh.ultimo.balance, h.ultimo.balance
    assert b.deudores_comerciales == 300 and b.otros_deudores_cp == 0
    assert b.proveedores == 150 and b.otras_cuentas_por_pagar_cp == 0
    assert b.activo_corriente == original.activo_corriente   # solo reclasifica
    assert SUPUESTO_HOMOLOGACION in hh.ultimo.supuestos_carga
    assert original.deudores_comerciales == 200              # no muta el original
    assert actividad(hh).valor("dias_cartera") > actividad(h).valor("dias_cartera")


def test_comparar_empresa_contra_pares_reales(pares):
    historiales, exclusiones = pares
    ref = construir_referencia(historiales, 2024, "Hoteles (prueba)", ["5511"], exclusiones)
    res = comparar([liquidez(homologar_empresa(hacer_historial()))], ref)
    # Con 5 pares no hay muestra mínima: el benchmark lo dice en vez de inventar
    assert any("no se calcula percentil" in a for a in res.advertencias)


def test_no_comparables_no_llevan_valores(pares):
    historiales, _ = pares
    ref = construir_referencia(historiales, 2024, "Hoteles (prueba)", ["5511"],
                               no_comparables={"dias_proveedores": "servicios"})
    assert "dias_proveedores" not in ref.valores
    assert ref.no_comparables == {"dias_proveedores": "servicios"}
