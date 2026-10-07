"""
Interfaz mínima del economista IA (Streamlit).

Desde la raíz del proyecto, con el servidor del modelo encendido:
    streamlit run frontend/app.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # importar app/, modules/, ...

from app.demo import contexto_demo  # noqa: E402
from app.llm.client import ClienteLLM  # noqa: E402
from app.orchestrator.orquestador import responder  # noqa: E402
from app.orchestrator.tools_registry import ContextoEmpresa  # noqa: E402
from data_sources.empresa.puc import ErrorCarga, cargar_historial, leer_balance_prueba  # noqa: E402
from data_sources.externos.referencia import cargar_referencia  # noqa: E402
from modules.base import formatear  # noqa: E402
from modules.esquema_financiero import Empresa  # noqa: E402

MAX_MB = 5
EJEMPLOS = [
    "¿Cómo está mi empresa?",
    "¿Tengo con qué pagar mis deudas de corto plazo?",
    "¿Cómo estamos frente a otros hoteles en rentabilidad?",
    "¿Por qué cambió la rentabilidad del patrimonio?",
    "¿Cómo me afecta que el Banco de la República suba las tasas?",
    "¿Me conviene subir las tarifas de las habitaciones?",
]

st.set_page_config(page_title="Economista IA", page_icon="📊", layout="centered")
st.title("Economista IA")
st.caption("Análisis financiero para pymes. Las cifras las calcula Python; "
           "el modelo de lenguaje solo elige el análisis y redacta.")


# --------------------------------------------------------------------------- #
# Barra lateral: estado del modelo y datos de la empresa
# --------------------------------------------------------------------------- #
with st.sidebar:
    ok, mensaje = ClienteLLM().disponible()
    (st.success if ok else st.error)(mensaje)
    if not ok:
        st.caption("En LM Studio: pestaña Developer → Start Server, o `lms server start`.")

    st.header("Empresa")
    fuente = st.radio("Datos", ["Hotel de demostración (ficticio)", "Subir balance de prueba"])

    if fuente.startswith("Hotel"):
        if st.session_state.get("fuente") != "demo":
            st.session_state.update(ctx=contexto_demo(), fuente="demo", chat=[])
        st.caption("Hotel Demo Andino S.A.S.: empresa ficticia con balances de prueba en "
                   "PUC de 2023 y 2024 (data/demo/).")
    else:
        if st.session_state.get("fuente") == "demo":
            st.session_state.update(ctx=None, fuente=None, chat=[])
        with st.form("carga"):
            razon_social = st.text_input("Razón social", max_chars=120)
            ciiu = st.text_input("CIIU (4 dígitos)", value="5511", max_chars=4)
            archivos = st.file_uploader("Balances de prueba antes del cierre (.xlsx o .csv), "
                                        "uno por año", type=["xlsx", "xls", "csv"],
                                        accept_multiple_files=True)
            cortes, largo_plazo = {}, {}
            for a in archivos or []:
                st.markdown(f"**{a.name}**")
                cortes[a.name] = st.date_input("Fecha de corte", value=date(2024, 12, 31),
                                               key=f"f_{a.name}")
                largo_plazo[a.name] = st.number_input(
                    "Obligaciones financieras de largo plazo (pesos)", min_value=0.0,
                    step=1_000_000.0, key=f"lp_{a.name}",
                    help="El PUC no separa la porción de largo plazo de la cuenta 21.")
            cargar = st.form_submit_button("Cargar")

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
                    balances = {cortes[a.name]: leer_balance_prueba(a, a.name) for a in archivos}
                    reclasif = {cortes[a.name]: [("obligaciones_financieras_cp",
                                                  "obligaciones_financieras_lp", lp)]
                                for a in archivos if (lp := largo_plazo[a.name]) > 0}
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
    st.info("Cargue los balances de prueba de la empresa en la barra lateral.")
    st.stop()

h = ctx.historial
b = h.ultimo.balance
st.subheader(h.empresa.razon_social)
anios = ", ".join(str(p.fecha_corte.year) for p in h.periodos)
c1, c2, c3 = st.columns(3)
c1.metric("Activo total", formatear(b.activo_total, "pesos"))
c2.metric("Patrimonio", formatear(b.patrimonio_total, "pesos"))
c3.metric("Años cargados", anios)


# --------------------------------------------------------------------------- #
# Conversación
# --------------------------------------------------------------------------- #
def mostrar(respuesta) -> None:
    st.markdown(respuesta.texto_completo.replace("$", "\\$"))
    if respuesta.resultados:
        with st.expander("Datos que sustentan la respuesta"):
            st.caption(f"Análisis: {respuesta.herramienta} · año {respuesta.periodo} · "
                       f"origen del texto: {respuesta.origen}")
            for res in respuesta.resultados:
                for hz in res.hallazgos:
                    st.markdown(f"- {hz}".replace("$", "\\$"))
                if res.analisis != "benchmark":
                    st.table({"Indicador": [i.nombre for i in res.indicadores],
                              "Valor": [formatear(i.valor, i.unidad) if i.valor is not None
                                        else "no calculable" for i in res.indicadores],
                              "Fórmula": [i.formula for i in res.indicadores]})
    if respuesta.origen == "respaldo":
        st.caption("El modelo no produjo una redacción verificable; se muestran los "
                   "resultados calculados directamente.")


st.session_state.setdefault("chat", [])
for turno in st.session_state.chat:
    with st.chat_message("user"):
        st.markdown(turno["pregunta"])
    with st.chat_message("assistant"):
        mostrar(turno["respuesta"])

if not st.session_state.chat:
    st.caption("Ejemplos: " + " · ".join(EJEMPLOS))

if pregunta := st.chat_input("Escriba su pregunta"):
    with st.chat_message("user"):
        st.markdown(pregunta)
    with st.chat_message("assistant"):
        with st.spinner("Analizando… (el modelo local puede tardar hasta un minuto)"):
            try:
                respuesta = responder(pregunta, ctx)
            except Exception as e:  # última red: la interfaz nunca se cae
                st.error(f"Ocurrió un error inesperado: {e}")
                st.stop()
        mostrar(respuesta)
    st.session_state.chat.append({"pregunta": pregunta, "respuesta": respuesta})
