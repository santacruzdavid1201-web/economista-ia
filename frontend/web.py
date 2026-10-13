"""
Rutas HTML de la interfaz (FastAPI + Jinja + HTMX).

Las páginas se devuelven completas; los enlaces piden a HTMX que tome solo
#pagina y la reemplace con una transición (sin el parpadeo de recargar todo).
El chat es uno solo para toda la interfaz y vive fuera de #pagina, así que sigue
abierto al navegar. La pregunta se responde en dos pasos: POST devuelve la
pregunta y un marcador que pide GET /respuesta/{id}, porque el modelo local
puede tardar un minuto.

Sesiones en memoria (MVP de un solo proceso): una cookie con un token aleatorio
apunta a la empresa cargada y a la conversación.
"""
from __future__ import annotations

import io
import json
import re
import secrets
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.datastructures import UploadFile   # el formulario entrega esta, no la de FastAPI

from app.demo import contexto_demo
from app.llm.client import ClienteLLM
from app.orchestrator.orquestador import Respuesta, responder
from app.orchestrator.tools_registry import ContextoEmpresa
from data_sources.empresa.puc import (
    RECLASIFICACIONES,
    ErrorCarga,
    cargar_historial,
    leer_balance_prueba,
)
from data_sources.externos.referencia import cargar_referencia
from frontend.cifras import libro, respuesta_html
from frontend.modulos import MODULOS, POR_CLAVE
from modules.base import formatear
from modules.esquema_financiero import Empresa, HistorialFinanciero

PLANTILLAS = Jinja2Templates(directory=Path(__file__).with_name("templates"))
COOKIE = "sesion"
MAX_SESIONES = 200
MAX_MB = 5
EXTENSIONES = (".csv", ".xlsx", ".xls")
UNIDADES = {"pesos": ("Pesos", 1), "miles": ("Miles de pesos", 1_000)}
DEUDA_LP = ("obligaciones_financieras_cp", "obligaciones_financieras_lp")
# Reclasificaciones con un nombre de campo estable para el formulario
RECLASIF = [(f"r{j}", par, etiqueta) for j, (par, etiqueta) in enumerate(RECLASIFICACIONES.items())]
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
SIN_REFERENCIA = ("No hay referencia sectorial para ese CIIU y año: la comparación con el "
                  "sector no estará disponible.")

router = APIRouter()


# --------------------------------------------------------------------------- #
# Sesiones
# --------------------------------------------------------------------------- #
@dataclass
class Turno:
    pregunta: str
    respuesta: Respuesta | None = None


@dataclass
class Sesion:
    ctx: ContextoEmpresa
    demo: bool = True
    chat: list[Turno] = field(default_factory=list)
    pendientes: dict[str, Turno] = field(default_factory=dict)
    archivos: list[tuple[str, bytes]] = field(default_factory=list)   # paso 1 de la carga
    borrador: dict = field(default_factory=dict)
    aviso: str | None = None                                          # se muestra una vez


_SESIONES: OrderedDict[str, Sesion] = OrderedDict()
_CANDADO = threading.Lock()


@lru_cache(maxsize=1)
def _demo() -> ContextoEmpresa:
    return contexto_demo()


def instalar(app: FastAPI) -> None:
    """Rutas y cookie de sesión. Un token desconocido (p. ej. tras reiniciar) se renueva."""
    app.include_router(router)

    @app.middleware("http")
    async def cookie_de_sesion(request: Request, call_next):
        sid = request.cookies.get(COOKIE)
        nueva = sid not in _SESIONES
        if nueva:
            sid = secrets.token_urlsafe(32)
        request.state.sid = sid
        respuesta = await call_next(request)
        if nueva:
            respuesta.set_cookie(COOKIE, sid, httponly=True, samesite="lax")
        return respuesta


def sesion(request: Request) -> Sesion:
    sid = request.state.sid
    with _CANDADO:
        s = _SESIONES.get(sid)
        if s is None:
            s = _SESIONES[sid] = Sesion(ctx=_demo())
            while len(_SESIONES) > MAX_SESIONES:
                _SESIONES.popitem(last=False)
        else:
            _SESIONES.move_to_end(sid)
    return s


def cliente_llm() -> ClienteLLM:
    """Dependencia: los tests la reemplazan por un modelo falso."""
    return ClienteLLM()


# --------------------------------------------------------------------------- #
# Utilidades de presentación
# --------------------------------------------------------------------------- #
def corte_sugerido(nombre: str) -> date:
    """Fecha de corte a partir del nombre del archivo ("balance_2015-12-31.csv", "2016.xlsx")."""
    if m := re.search(r"(20\d{2})-(\d{2})-(\d{2})", nombre):
        try:
            return date(*map(int, m.groups()))
        except ValueError:
            pass
    if m := re.search(r"(20\d{2})", nombre):
        return date(int(m.group(1)), 12, 31)
    return date(date.today().year - 1, 12, 31)


def _anios(h: HistorialFinanciero) -> str:
    anios = [str(p.fecha_corte.year) for p in h.periodos]
    return anios[0] if len(anios) == 1 else f"{', '.join(anios[:-1])} y {anios[-1]}"


def _vista(r: Respuesta) -> dict:
    """Lo que la plantilla necesita de una respuesta, ya escapado o marcado."""
    del_calculo = {s for res in r.resultados for s in res.supuestos}
    return {
        "memo": respuesta_html(r.texto, r.resultados),
        "avisos": [x for x in r.notas if x not in del_calculo],
        "supuestos": [x for x in r.notas if x in del_calculo],
        "fuentes": r.fuentes,
        "analisis": ANALISIS.get(r.herramienta or "", r.herramienta),
        "periodo": r.periodo,
        "origen": r.origen,
        "detalle": [{"hallazgos": res.hallazgos,
                     "tabla": None if res.analisis == "benchmark" else libro(
                         [(i.nombre, formatear(i.valor, i.unidad) if i.valor is not None
                           else "no calculable", i.formula) for i in res.indicadores],
                         encabezado=("Indicador", "Valor", "Fórmula"))}
                    for res in r.resultados],
    }


def _turnos(s: Sesion) -> list[dict]:
    return [{"pregunta": t.pregunta, "r": _vista(t.respuesta)} for t in s.chat if t.respuesta]


def _contexto(request: Request, s: Sesion, **extra) -> dict:
    h = s.ctx.historial
    return {"empresa": h.empresa.razon_social, "anios": _anios(h), "ciiu": h.empresa.ciiu,
            "demo": s.demo, "modulos": MODULOS, "turnos": _turnos(s), **extra}


def _pagina(request: Request, plantilla: str, contexto: dict, status: int = 200):
    return PLANTILLAS.TemplateResponse(request, plantilla, contexto, status_code=status)


def _a_portada() -> Response:
    """
    Tras cambiar de empresa, HTMX trae la portada sin recargar todo; el chat, que está
    fuera de #pagina, se vacía con el evento empresa-cambiada.
    """
    destino = {"path": "/", "target": "#pagina", "select": "#pagina",
               "swap": "outerHTML transition:true"}
    return Response(status_code=204, headers={"HX-Location": json.dumps(destino),
                                              "HX-Trigger": "empresa-cambiada"})


# --------------------------------------------------------------------------- #
# Páginas
# --------------------------------------------------------------------------- #
@router.get("/", response_class=HTMLResponse)
def portada(request: Request, s: Sesion = Depends(sesion)):
    b = s.ctx.historial.ultimo.balance
    renglones = libro([("Activo total", formatear(b.activo_total, "pesos"), None),
                       ("Pasivo total", formatear(b.pasivo_total, "pesos"), None),
                       ("Patrimonio", formatear(b.patrimonio_total, "pesos"), None)])
    aviso, s.aviso = s.aviso, None
    return _pagina(request, "portada.html",
                   _contexto(request, s, renglones=renglones, aviso=aviso))


@router.get("/modulo/{clave}", response_class=HTMLResponse)
def modulo(request: Request, clave: str, s: Sesion = Depends(sesion)):
    m = POR_CLAVE.get(clave)
    if m is None:
        raise HTTPException(404, "Ese módulo no existe.")
    return _pagina(request, "modulo.html", _contexto(request, s, m=m))


# --------------------------------------------------------------------------- #
# Conversación
# --------------------------------------------------------------------------- #
@router.get("/chat", response_class=HTMLResponse)
def chat(request: Request, s: Sesion = Depends(sesion)):
    return _pagina(request, "_conversacion.html", {"turnos": _turnos(s)})


@router.post("/preguntar", response_class=HTMLResponse)
async def preguntar(request: Request, s: Sesion = Depends(sesion)):
    pregunta = str((await request.form()).get("pregunta", ""))
    pid = secrets.token_urlsafe(8)
    s.pendientes[pid] = Turno(pregunta=pregunta)
    return _pagina(request, "_pendiente.html", {"pid": pid, "pregunta": pregunta})


@router.get("/respuesta/{pid}", response_class=HTMLResponse)
def respuesta(request: Request, pid: str, s: Sesion = Depends(sesion),
              cliente=Depends(cliente_llm)):
    """Corre el orquestador (en un hilo de FastAPI: puede tardar un minuto)."""
    turno = s.pendientes.pop(pid, None)
    if turno is None:
        return HTMLResponse('<p class="aviso-chat">Esa pregunta ya no está disponible. '
                            'Escríbala de nuevo.</p>')
    historial = [(t.pregunta, t.respuesta) for t in s.chat if t.respuesta]
    try:
        turno.respuesta = responder(turno.pregunta, s.ctx, cliente, historial=historial)
    except Exception as e:  # última red: la interfaz nunca se cae
        turno.respuesta = Respuesta(texto=f"Ocurrió un error inesperado: {e}", origen="error")
    s.chat.append(turno)
    return _pagina(request, "_respuesta.html", {"r": _vista(turno.respuesta)})


@router.get("/estado-modelo", response_class=HTMLResponse)
def estado_modelo(request: Request, cliente=Depends(cliente_llm)):
    ok, mensaje = cliente.disponible()
    return _pagina(request, "_estado.html", {"ok": ok, "mensaje": mensaje})


# --------------------------------------------------------------------------- #
# Empresa: hotel de demostración o balances propios en dos pasos
# --------------------------------------------------------------------------- #
@router.get("/empresa", response_class=HTMLResponse)
def empresa(request: Request, s: Sesion = Depends(sesion)):
    return _pagina(request, "_empresa.html", {"unidades": UNIDADES, "v": s.borrador,
                                              "errores": [], "max_mb": MAX_MB})


@router.post("/empresa/demo")
def usar_demo(s: Sesion = Depends(sesion)):
    s.ctx, s.demo, s.aviso = _demo(), True, None
    s.chat.clear()
    return _a_portada()


@router.post("/empresa/archivos", response_class=HTMLResponse)
async def subir_archivos(request: Request, s: Sesion = Depends(sesion)):
    """Paso 1: datos de la empresa y archivos. Devuelve el paso 2 o el mismo con errores."""
    form = await request.form()
    v = {"razon_social": str(form.get("razon_social", "")).strip(),
         "ciiu": str(form.get("ciiu", "")).strip(),
         "unidad": str(form.get("unidad", "pesos"))}
    archivos = [a for a in form.getlist("archivos") if isinstance(a, UploadFile) and a.filename]
    errores = []
    if not v["razon_social"]:
        errores.append("Escriba la razón social.")
    elif len(v["razon_social"]) > 120:
        errores.append("La razón social debe tener máximo 120 caracteres.")
    if not (v["ciiu"].isdigit() and len(v["ciiu"]) == 4):
        errores.append("El CIIU debe tener 4 dígitos.")
    if v["unidad"] not in UNIDADES:
        errores.append("Elija si las cifras están en pesos o en miles de pesos.")
    if not archivos:
        errores.append("Suba al menos un balance de prueba.")
    leidos = []
    for a in archivos:
        datos = await a.read(MAX_MB * 1_048_576 + 1)
        if Path(a.filename).suffix.lower() not in EXTENSIONES:
            errores.append(f"{a.filename}: el archivo debe ser .csv, .xlsx o .xls.")
        elif len(datos) > MAX_MB * 1_048_576:
            errores.append(f"{a.filename}: cada archivo debe pesar menos de {MAX_MB} MB.")
        else:
            leidos.append((Path(a.filename).name, datos))
    s.borrador = v
    if errores:
        return _pagina(request, "_empresa.html", {"unidades": UNIDADES, "v": v,
                                                  "errores": errores, "max_mb": MAX_MB})
    s.archivos = leidos
    return _paso2(request, s, [])


def _paso2(request: Request, s: Sesion, errores: list[str], valores: dict | None = None):
    archivos = [{"i": i, "nombre": nombre,
                 "fecha": (valores or {}).get(f"fecha_{i}") or corte_sugerido(nombre).isoformat()}
                for i, (nombre, _) in enumerate(s.archivos)]
    return _pagina(request, "_empresa_paso2.html", {
        "archivos": archivos, "reclasif": RECLASIF, "deuda_lp": RECLASIF[0][0],
        "unidad": UNIDADES[s.borrador.get("unidad", "pesos")][0], "errores": errores,
        "valores": valores or {}})


@router.post("/empresa/cargar")
async def cargar(request: Request, s: Sesion = Depends(sesion)):
    """Paso 2: fecha de corte y reclasificaciones por archivo; arma el historial."""
    if not s.archivos:
        return _pagina(request, "_empresa.html", {
            "unidades": UNIDADES, "v": s.borrador, "max_mb": MAX_MB,
            "errores": ["Vuelva a subir los archivos: la carga anterior expiró."]})
    form = {k: str(v) for k, v in (await request.form()).items()}
    errores, cortes, montos = [], {}, {}
    for i, (nombre, _) in enumerate(s.archivos):
        try:
            cortes[i] = date.fromisoformat(form.get(f"fecha_{i}", ""))
        except ValueError:
            errores.append(f"{nombre}: escriba una fecha de corte válida.")
        for campo, par, etiqueta in RECLASIF:
            texto = form.get(f"{campo}_{i}", "").strip() or "0"
            try:
                monto = float(texto)
                if monto < 0:
                    raise ValueError
                montos[(i, par)] = monto
            except ValueError:
                errores.append(f"{nombre}: «{etiqueta}» debe ser un número positivo o cero.")
    if len(set(cortes.values())) != len(cortes):
        errores.append("Cada archivo debe tener una fecha de corte distinta.")
    if errores:
        return _paso2(request, s, errores, form)
    try:
        factor = UNIDADES[s.borrador["unidad"]][1]
        empresa_ = Empresa(empresa_id="usuario", razon_social=s.borrador["razon_social"],
                           ciiu=s.borrador["ciiu"])
        balances, reclasif = {}, {}
        for i, (nombre, datos) in enumerate(s.archivos):
            df = leer_balance_prueba(io.BytesIO(datos), nombre)
            balances[cortes[i]] = df.assign(saldo=df["saldo"] * factor)
            reclasif[cortes[i]] = [(*par, montos[(i, par)] * factor)
                                   for _, par, _ in RECLASIF if montos[(i, par)] > 0]
        historial = cargar_historial(empresa_, balances, reclasif)
    except ErrorCarga as e:
        return _paso2(request, s, [f"No se pudo cargar: {e}"], form)
    referencia = cargar_referencia(empresa_.ciiu, historial.ultimo.fecha_corte.year)
    s.ctx = ContextoEmpresa(historial=historial, referencia=referencia)
    s.demo, s.aviso, s.archivos = False, (SIN_REFERENCIA if referencia is None else None), []
    s.chat.clear()
    return _a_portada()
