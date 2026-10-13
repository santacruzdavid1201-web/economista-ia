"""
Interfaz del economista IA (Streamlit), tema "libro contable".

Desde la raíz del proyecto, con el servidor del modelo encendido:
    streamlit run frontend/app.py

El tema (colores y fuentes) está en .streamlit/config.toml; aquí solo va el CSS
que Streamlit no cubre: las cifras rastreables y los renglones de libro.
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # importar app/, modules/, ...

from app.demo import contexto_demo  # noqa: E402
from app.llm.client import ClienteLLM  # noqa: E402
from app.orchestrator.orquestador import responder  # noqa: E402
from app.orchestrator.tools_registry import ContextoEmpresa  # noqa: E402
from data_sources.empresa.puc import (  # noqa: E402
    RECLASIFICACIONES,
    ErrorCarga,
    cargar_historial,
    leer_balance_prueba,
)
from data_sources.externos.referencia import cargar_referencia  # noqa: E402
from frontend.cifras import libro, marcar  # noqa: E402
from modules.base import formatear  # noqa: E402
from modules.esquema_financiero import Empresa  # noqa: E402

MAX_MB = 5
DEUDA_LP = ("obligaciones_financieras_cp", "obligaciones_financieras_lp")
UNIDADES = {"Pesos": 1, "Miles de pesos": 1_000}
EJEMPLOS = [
    "¿Cómo está mi empresa?",
    "¿Tengo con qué pagar mis deudas de corto plazo?",
    "¿Cómo estamos frente a otros hoteles en rentabilidad?",
    "¿Crecí en términos reales?",
    "¿Cómo me afectan las tasas de interés?",
    "¿Me conviene subir las tarifas de las habitaciones?",
]
# Nombre de cada análisis en palabras del gerente
ANALISIS = {
    "analizar_liquidez": "liquidez",
    "analizar_endeudamiento": "endeudamiento",
    "analizar_rentabilidad": "rentabilidad",
    "analizar_actividad": "actividad (cobro, inventario y pago)",
    "analizar_dupont": "rentabilidad del patrimonio (DuPont)",
    "analizar_riesgo_quiebra": "riesgo financiero (Z'' de Altman)",
    "analizar_crecimiento_real": "crecimiento real de los ingresos",
    "analizar_sensibilidad_tasas": "sensibilidad a las tasas de interés",
    "comparar_con_sector": "comparación con el sector",
    "diagnostico_general": "diagnóstico general",
}
ESTILO = """
<style>
/* Cifras calculadas: tinta azul, números tabulares y su origen al pasar el cursor */
.cifra {
  color: #1F4FA3; font-variant-numeric: tabular-nums lining-nums; white-space: nowrap;
  text-decoration: underline dotted; text-decoration-thickness: 1px;
  text-underline-offset: 0.2em; cursor: help; position: relative; border-radius: 2px;
}
.cifra.negativa { color: #A8322D; }
.cifra:focus-visible { outline: 2px solid currentColor; outline-offset: 2px; }
.cifra::after {
  content: attr(data-origen); position: absolute; left: 0; top: calc(100% + 0.4rem);
  z-index: 1000; width: max-content; max-width: min(18rem, 70vw); white-space: normal;
  padding: 0.5rem 0.7rem; border-radius: 0.25rem; background: #1E2B3A; color: #F1F4EE;
  font: 400 0.8125rem/1.45 "Archivo", sans-serif; text-align: left;
  opacity: 0; visibility: hidden; pointer-events: none; transition: opacity 120ms ease;
}
.cifra:hover::after, .cifra:focus::after { opacity: 1; visibility: visible; }
@media (prefers-reduced-motion: reduce) { .cifra::after { transition: none; } }
/* En el celular el origen aparece como franja fija sobre la caja de pregunta */
@media (max-width: 640px) {
  .cifra::after {
    position: fixed; left: 1rem; right: 1rem; top: auto; bottom: 7.5rem;
    width: auto; max-width: none;
  }
  [data-testid="stMain"] h1 { font-size: 2rem; }
}

/* La respuesta se lee como un memorando */
[class*="st-key-memo"] :is(p, li) {
  font-family: "Source Serif 4", Georgia, serif; font-size: 1.0625rem; line-height: 1.65;
  max-width: 68ch;
}
[class*="st-key-notas"] :is(p, li) { font-size: 0.875rem; color: #4A5868; max-width: 72ch; }

/* Renglones de libro */
.libro { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums lining-nums; }
.libro th {
  text-align: left; font-weight: 500; font-size: 0.8125rem; color: #4A5868;
  padding: 0.35rem 0.75rem 0.35rem 0; border-bottom: 1px solid #C9D6C3;
}
.libro td { padding: 0.45rem 0.75rem 0.45rem 0; border-bottom: 1px solid #C9D6C3; vertical-align: top; }
.libro th:nth-child(2), .libro td.valor { text-align: right; }
.libro td.valor { color: #1F4FA3; white-space: nowrap; }
.libro td.valor.negativa { color: #A8322D; }
.libro td.formula { color: #4A5868; font-size: 0.8125rem; }
</style>
"""


def corte_sugerido(nombre: str) -> date:
    """Fecha de corte a partir del nombre del archivo ("balance_2015-12-31.csv", "2016.xlsx")."""
    if m := re.search(r"(20\d{2})-(\d{2})-(\d{2})", nombre):
        try:
            return date(*map(int, m.groups()))
        except ValueError:
            pass
    if m := re.search(r"(20\d{2})", nombre):
        return date(int(m.group(1)), 12, 31)
    return date(2024, 12, 31)


def _md(texto: str) -> str:
    """Texto de Python para st.markdown: el $ no es LaTeX."""
    return texto.replace("$", "\\$")


def _anios(h) -> str:
    anios = [str(p.fecha_corte.year) for p in h.periodos]
    return anios[0] if len(anios) == 1 else f"{', '.join(anios[:-1])} y {anios[-1]}"


st.set_page_config(page_title="Economista IA", page_icon=":material/menu_book:",
                   layout="centered")
st.markdown(ESTILO, unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Barra lateral: qué es, estado del modelo y datos de la empresa
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.title("Economista IA")
    st.caption("Las cifras las calcula el sistema con los estados financieros de la empresa; "
               "el modelo de lenguaje solo elige el análisis y redacta. Pase el cursor sobre "
               "una cifra azul para ver de dónde sale.")
    ok, mensaje = ClienteLLM().disponible()
    (st.success if ok else st.error)(mensaje)
    if not ok:
        st.caption("En LM Studio: pestaña Developer, Start Server; o en la terminal, "
                   "`lms server start`.")

    st.header("Empresa")
    fuente = st.radio("Datos", ["Hotel de demostración (ficticio)", "Subir balance de prueba"],
                      label_visibility="collapsed")

    if fuente.startswith("Hotel"):
        if st.session_state.get("fuente") != "demo":
            st.session_state.update(ctx=contexto_demo(), fuente="demo", chat=[])
        st.caption("Hotel Demo Andino S.A.S.: empresa ficticia con balances de prueba en "
                   "PUC de 2023 y 2024.")
    else:
        if st.session_state.get("fuente") == "demo":
            st.session_state.update(ctx=None, fuente=None, chat=[])
        with st.form("carga"):
            razon_social = st.text_input("Razón social", max_chars=120)
            ciiu = st.text_input("CIIU (4 dígitos)", value="5511", max_chars=4)
            archivos = st.file_uploader("Balances de prueba antes del cierre (.xlsx o .csv), "
                                        "uno por año", type=["xlsx", "xls", "csv"],
                                        accept_multiple_files=True)
            unidad = st.radio("Las cifras del archivo están en", list(UNIDADES), horizontal=True,
                              help="Supersociedades y muchos estados auditados reportan en "
                                   "miles de pesos. Los montos de abajo van en la misma unidad.")
            cortes, montos = {}, {}
            for a in archivos or []:
                st.markdown(f"**{a.name}**")
                cortes[a.name] = st.date_input("Fecha de corte", value=corte_sugerido(a.name),
                                               key=f"f_{a.name}")
                # El PUC no separa el plazo: la empresa informa qué parte es de largo plazo
                montos[a.name] = {DEUDA_LP: st.number_input(
                    RECLASIFICACIONES[DEUDA_LP], min_value=0.0, step=1_000.0,
                    key=f"lp_{a.name}",
                    help="El PUC no separa la porción de largo plazo de la cuenta 21.")}
                with st.expander("Otras reclasificaciones de plazo (opcional)"):
                    for par, etiqueta in RECLASIFICACIONES.items():
                        if par != DEUDA_LP:
                            montos[a.name][par] = st.number_input(
                                etiqueta, min_value=0.0, step=1_000.0, key=f"{par}_{a.name}")
            st.caption("Columnas: código de cuenta y saldo final con signo (débito +, "
                       "crédito −), o saldo débito y saldo crédito. Se aceptan filas de "
                       "título arriba, CSV con ';' o ',' y números como 1.234.567,89.")
            cargar = st.form_submit_button("Cargar balances")

        if cargar:
            errores = []
            if not razon_social.strip():
                errores.append("Escriba la razón social.")
            if not (ciiu.isdigit() and len(ciiu) == 4):
                errores.append("El CIIU debe tener 4 dígitos.")
            if not archivos:
                errores.append("Suba al menos un balance de prueba.")
            if any(a.size > MAX_MB * 1_048_576 for a in archivos or []):
                errores.append(f"Cada archivo debe pesar menos de {MAX_MB} MB.")
            if len(set(cortes.values())) != len(cortes):
                errores.append("Cada archivo debe tener una fecha de corte distinta.")
            if errores:
                for e in errores:
                    st.error(e)
            else:
                try:
                    empresa = Empresa(empresa_id="usuario", razon_social=razon_social.strip(),
                                      ciiu=ciiu)
                    factor = UNIDADES[unidad]
                    balances = {}
                    for a in archivos:
                        df = leer_balance_prueba(a, a.name)
                        balances[cortes[a.name]] = df.assign(saldo=df["saldo"] * factor)
                    reclasif = {cortes[a.name]: [(*par, monto * factor)
                                                 for par, monto in montos[a.name].items() if monto > 0]
                                for a in archivos}
                    historial = cargar_historial(empresa, balances, reclasif)
                    referencia = cargar_referencia(ciiu, historial.ultimo.fecha_corte.year)
                    st.session_state.update(
                        ctx=ContextoEmpresa(historial=historial, referencia=referencia),
                        fuente="usuario", chat=[])
                    st.success("Balances cargados.")
                    if referencia is None:
                        st.info("No hay referencia sectorial para ese CIIU y año: la "
                                "comparación con el sector no estará disponible.")
                except ErrorCarga as e:
                    st.error(f"No se pudo cargar: {e}")

ctx: ContextoEmpresa | None = st.session_state.get("ctx")
if ctx is None:
    st.title("¿Qué quiere saber de su empresa?")
    st.markdown("Cargue los balances de prueba en la barra lateral, o elija el hotel de "
                "demostración para probar con una empresa ficticia.")
    st.stop()


# --------------------------------------------------------------------------- #
# Encabezado: la empresa en renglones de libro
# --------------------------------------------------------------------------- #
h = ctx.historial
b = h.ultimo.balance
st.title(h.empresa.razon_social)
st.caption(f"Estados financieros de {_anios(h)}. Actividad CIIU {h.empresa.ciiu}.")
st.html(libro([
    ("Activo total", formatear(b.activo_total, "pesos"), None),
    ("Pasivo total", formatear(b.pasivo_total, "pesos"), None),
    ("Patrimonio", formatear(b.patrimonio_total, "pesos"), None),
]))


# --------------------------------------------------------------------------- #
# Conversación
# --------------------------------------------------------------------------- #
def mostrar(respuesta, n: int) -> None:
    with st.container(key=f"memo_{n}"):
        st.markdown(marcar(respuesta.texto, respuesta.resultados), unsafe_allow_html=True)
    # Las advertencias se ven siempre; los supuestos del cálculo, a un clic
    del_calculo = {s for r in respuesta.resultados for s in r.supuestos}
    avisos = [x for x in respuesta.notas if x not in del_calculo]
    supuestos = [x for x in respuesta.notas if x in del_calculo]
    if avisos or respuesta.fuentes:
        with st.container(key=f"notas_{n}"):
            if avisos:
                st.markdown(_md("**Para tener en cuenta**\n\n"
                                + "\n".join(f"- {x}" for x in avisos)))
            if respuesta.fuentes:
                st.markdown(_md("**Fuentes**\n\n"
                                + "\n".join(f"- {f}" for f in respuesta.fuentes)))
    if supuestos:
        with st.expander(f"Supuestos del cálculo ({len(supuestos)})"):
            st.markdown(_md("\n".join(f"- {x}" for x in supuestos)))
    if respuesta.resultados:
        with st.expander("De dónde salen las cifras"):
            nombre = ANALISIS.get(respuesta.herramienta, respuesta.herramienta)
            st.caption(f"Análisis de {nombre}, con los estados de {respuesta.periodo}.")
            for res in respuesta.resultados:
                if res.hallazgos:
                    st.markdown(_md("\n".join(f"- {hz}" for hz in res.hallazgos)))
                if res.analisis != "benchmark":
                    st.html(libro(
                        [(i.nombre, formatear(i.valor, i.unidad) if i.valor is not None
                          else "no calculable", i.formula) for i in res.indicadores],
                        encabezado=("Indicador", "Valor", "Fórmula")))
    if respuesta.origen == "respaldo":
        st.caption("El modelo no produjo una redacción verificable: se muestran los "
                   "resultados calculados directamente.")


def guardar_ejemplo() -> None:
    """Un clic en un ejemplo lo envía como pregunta; la selección se limpia."""
    st.session_state.pendiente = st.session_state.ejemplo
    st.session_state.ejemplo = None


AVATARES = {"user": ":material/person:", "assistant": ":material/menu_book:"}
st.session_state.setdefault("chat", [])
for n, turno in enumerate(st.session_state.chat):
    with st.chat_message("user", avatar=AVATARES["user"]):
        st.markdown(_md(turno["pregunta"]))
    with st.chat_message("assistant", avatar=AVATARES["assistant"]):
        mostrar(turno["respuesta"], n)

if not st.session_state.chat:
    st.subheader("¿Qué quiere saber de su empresa?")
    st.pills("Preguntas de ejemplo", EJEMPLOS, key="ejemplo", on_change=guardar_ejemplo,
             label_visibility="collapsed")

pregunta = st.chat_input("Escriba su pregunta") or st.session_state.pop("pendiente", None)
if pregunta:
    with st.chat_message("user", avatar=AVATARES["user"]):
        st.markdown(_md(pregunta))
    with st.chat_message("assistant", avatar=AVATARES["assistant"]):
        with st.spinner("Analizando… El modelo local puede tardar hasta un minuto."):
            try:
                respuesta = responder(pregunta, ctx)
            except Exception as e:  # última red: la interfaz nunca se cae
                st.error(f"Ocurrió un error inesperado: {e}")
                st.stop()
        mostrar(respuesta, len(st.session_state.chat))
    st.session_state.chat.append({"pregunta": pregunta, "respuesta": respuesta})
    st.rerun()  # el estado vacío (ejemplos) desaparece en cuanto hay conversación
