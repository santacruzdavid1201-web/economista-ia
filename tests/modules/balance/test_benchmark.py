import pytest

from modules.balance.benchmark import (
    ReferenciaSectorial,
    comparar,
    cuantil,
    percentil_rango_medio,
)
from modules.balance.razones import endeudamiento, liquidez


def referencia(**valores) -> ReferenciaSectorial:
    return ReferenciaSectorial(universo="Alojamiento (prueba)", anio=2024,
                               ciius=["5511"], valores=valores)


# 40 valores: 0,1 · 0,2 · ... · 4,0
CORRIENTE = [round(0.1 * k, 1) for k in range(1, 41)]


def test_percentil_rango_medio_con_empates():
    assert percentil_rango_medio(3, [1, 2, 3, 3, 5]) == pytest.approx((2 + 1) / 5 * 100)
    assert percentil_rango_medio(0, [1, 2, 3]) == 0
    assert percentil_rango_medio(9, [1, 2, 3]) == 100


def test_cuantiles_coinciden_con_numpy():
    muestra = [7, 1, 3, 9, 5]
    assert cuantil(muestra, 0.5) == 5
    assert cuantil(muestra, 0.25) == 3
    assert cuantil([1, 2, 3, 4], 0.5) == 2.5


def test_compara_razon_corriente(historial):
    res = comparar([liquidez(historial)], referencia(razon_corriente=CORRIENTE))
    # Razón corriente 2,037: hay 20 pares por debajo (0,1 … 2,0)
    assert res.valor("razon_corriente_percentil") == pytest.approx(50)
    assert res.valor("razon_corriente_mediana") == pytest.approx(2.05)
    assert "40 empresas" in res.hallazgos[0]


def test_capital_de_trabajo_no_se_compara(historial):
    res = comparar([liquidez(historial)], referencia(capital_trabajo=CORRIENTE))
    assert res.indicadores == []


def test_direccion_menor_es_mejor(historial):
    # Endeudamiento de la empresa 0,424; pares entre 0,02 y 0,80
    pares = [0.02 * k for k in range(1, 41)]
    res = comparar([endeudamiento(historial)], referencia(nivel_endeudamiento=pares))
    pct = res.valor("nivel_endeudamiento_percentil")
    assert pct == pytest.approx(52.5)
    assert f"mejor que el {100 - pct:.0f} %" in res.hallazgos[0]


def test_muestra_pequena_y_muy_pequena(historial):
    res = comparar([liquidez(historial)],
                   referencia(razon_corriente=CORRIENTE[:15], prueba_acida=[1.0] * 5))
    assert any("Muestra pequeña" in a for a in res.advertencias)
    assert any("solo 5 empresas" in a for a in res.advertencias)
    with pytest.raises(KeyError):
        res.valor("prueba_acida_percentil")


def test_descarta_faltantes_e_infinitos(historial):
    sucios = CORRIENTE + [None, float("inf"), float("nan")]
    res = comparar([liquidez(historial)], referencia(razon_corriente=sucios))
    assert "40 empresas" in res.hallazgos[0]


def test_advierte_anios_distintos(historial):
    ref = referencia(razon_corriente=CORRIENTE).model_copy(update={"anio": 2023})
    res = comparar([liquidez(historial)], ref)
    assert any("mezcla años distintos" in a for a in res.advertencias)
    assert any("no es censal" in s for s in res.supuestos)


def test_indicador_no_comparable_se_explica(historial):
    from modules.balance.razones import actividad
    ref = referencia(dias_cartera=[float(k) for k in range(1, 41)],
                     dias_proveedores=[float(k) for k in range(1, 41)])
    ref = ref.model_copy(update={"no_comparables": {"dias_proveedores": "motivo de prueba"}})
    res = comparar([actividad(historial)], ref)
    assert "dias_cartera_percentil" in {i.clave for i in res.indicadores}
    with pytest.raises(KeyError):
        res.valor("dias_proveedores_percentil")
    assert any("no se compara con el sector (motivo de prueba)" in a for a in res.advertencias)


def test_formatear_por_unidad():
    from modules.balance.benchmark import formatear
    assert formatear(0.0241, "proporcion") == "2,4 %"
    assert formatear(53.32, "dias") == "53 días"
    assert formatear(1.514, "veces") == "1,51 veces"
    assert formatear(520_000_000, "pesos") == "$ 520.000.000"


def test_hallazgo_incluye_valor_y_mediana_legibles(historial):
    pares = [0.02 * k for k in range(1, 41)]
    res = comparar([endeudamiento(historial)], referencia(nivel_endeudamiento=pares))
    assert res.hallazgos[0].startswith(
        "Nivel de endeudamiento: 42,4 %, por encima de la mediana del sector (41,0 %); "
        "percentil 52 frente a 40 empresas")
