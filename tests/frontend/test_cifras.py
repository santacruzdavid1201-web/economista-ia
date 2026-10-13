"""Cifras rastreables en la respuesta: cada número calculado lleva su origen."""
from modules.base import Indicador, ResultadoModulo
from frontend.cifras import marcar


def resultado(*indicadores: Indicador, hallazgos: list[str] | None = None) -> ResultadoModulo:
    return ResultadoModulo(modulo="balance", analisis="x", indicadores=list(indicadores),
                           hallazgos=hallazgos or [])


RAZON = Indicador(clave="razon_corriente", nombre="Razón corriente", valor=2.04, unidad="veces",
                  formula="Activo corriente / Pasivo corriente")


def test_marca_la_cifra_de_un_indicador_con_su_formula():
    html = marcar("Su razón corriente es 2,04 veces.", [resultado(RAZON)])
    assert html == ('Su razón corriente es <span class="cifra" tabindex="0" data-origen="'
                    'Razón corriente. Fórmula: Activo corriente / Pasivo corriente">'
                    '2,04 veces</span>.')


def test_cifra_que_solo_esta_en_un_hallazgo():
    h = "Cada punto le suma $ 6.800.000 al año."
    html = marcar("Cada punto cuesta $6.800.000.", [resultado(hallazgos=[h])])
    # El $ visible se escapa para Streamlit (no es LaTeX); en el atributo va como entidad
    assert ('<span class="cifra" tabindex="0" data-origen="Del análisis: Cada punto le suma '
            '&#36; 6.800.000 al año.">\\$6.800.000</span>') in html


def test_no_marca_anios_enteros_pequenos_ni_cifras_ajenas():
    r = resultado(RAZON, hallazgos=["En 2024, con 3 puntos más, la razón fue 2,04 veces."])
    html = marcar("En 2024, con 3 puntos más y 7,5 de otra cosa.", [r])
    assert "<span" not in html


def test_negativos_en_rojo_contable():
    caida = Indicador(clave="crecimiento", nombre="Crecimiento real", valor=-0.019,
                      unidad="proporcion", formula="(1 + nominal) / (1 + inflación) − 1")
    html = marcar("Cayeron -1,9 % en términos reales.", [resultado(caida)])
    assert 'class="cifra negativa"' in html


def test_el_html_del_modelo_nunca_se_inserta():
    html = marcar('<img src=x onerror="alert(1)"> Es 2,04 veces.', [resultado(RAZON)])
    assert "<img" not in html and "&lt;img" in html
    assert 'data-origen="Razón corriente.' in html


def test_el_origen_se_escapa_en_el_atributo():
    raro = Indicador(clave="x", nombre='Margen "neto" <prueba>', valor=0.25,
                     unidad="proporcion", formula="a / b")
    html = marcar("Es 25,0 %.", [resultado(raro)])
    assert 'data-origen="Margen &quot;neto&quot; &lt;prueba&gt;. Fórmula: a / b"' in html


def test_libro_alinea_cifras_y_escapa():
    from frontend.cifras import libro
    html = libro([("Activo total", "$ 1.000", None),
                  ("Crecimiento <real>", "-1,9 %", "a / b − 1")],
                 encabezado=("Indicador", "Valor", "Fórmula"))
    assert html.startswith('<table class="libro">')
    assert "<th>Indicador</th>" in html
    assert '<td class="valor">&#36; 1.000</td>' in html
    assert '<td class="valor negativa">-1,9 %</td>' in html
    assert "<td>Crecimiento &lt;real&gt;</td>" in html
    assert '<td class="formula">a / b − 1</td>' in html
    assert html.count("<tr>") == 3


def test_libro_sin_formulas_tiene_dos_columnas():
    from frontend.cifras import libro
    html = libro([("Patrimonio", "$ 5", None)])
    assert "formula" not in html and "<th>" not in html
