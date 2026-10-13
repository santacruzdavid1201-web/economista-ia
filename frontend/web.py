"""
Rutas HTML de la interfaz (FastAPI + Jinja + HTMX).

Las páginas se devuelven completas; los enlaces piden a HTMX que tome solo
#pagina y la reemplace con una transición (sin el parpadeo de recargar todo).
El chat es uno solo para toda la interfaz y vive fuera de #pagina, así que sigue
abierto al navegar. La pregunta se responde en dos pasos: POST devuelve la
pregunta y un marcador que pide GET /respuesta/{id}, porque el modelo local
puede tardar un minuto.

Sesiones en memoria (MVP de un solo proceso): una cookie con un token aleatorio
apunta a la empresa cargada y a la conversación. La sesión empieza sin empresa:
el usuario sube sus balances de prueba en la portada y cada archivo se lee al
momento (activo, pasivo y patrimonio, o el error de ese archivo).
"""
from __future__ import annotations

import io
import re
import secrets
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.datastructures import UploadFile   # el formulario entrega esta, no la de FastAPI

from app.llm.client import ClienteLLM
from app.orchestrator.orquestador import Respuesta, responder
from app.orchestrator.tools_registry import ContextoEmpresa
from data_sources.empresa.puc import (
    RECLASIFICACIONES,
    ErrorCarga,
    a_estado_financiero,
    cargar_mapeo,
    leer_balance_prueba,
)
from data_sources.externos.referencia import REFERENCIAS, cargar_referencia
from frontend.cifras import libro, respuesta_html
from frontend.modulos import MODULOS, POR_CLAVE
from modules.base import formatear
from modules.esquema_financiero import Empresa, EstadoFinanciero, HistorialFinanciero

PLANTILLAS = Jinja2Templates(directory=Path(__file__).with_name("templates"))
ESTATICOS = Path(__file__).with_name("static")


def estatico(nombre: str) -> str:
    """URL con la fecha del archivo: el navegador no reutiliza una hoja de estilos vieja."""
    return f"/static/{nombre}?v={int((ESTATICOS / nombre).stat().st_mtime)}"


PLANTILLAS.env.globals["estatico"] = estatico
COOKIE = "sesion"
MAX_SESIONES = 200
MAX_MB = 5
MAX_ARCHIVOS = 10
EXTENSIONES = (".csv", ".xlsx", ".xls")
UNIDADES = {"pesos": ("Pesos", 1), "miles": ("Miles de pesos", 1_000)}
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

router = APIRouter()


# --------------------------------------------------------------------------- #
# Sesiones
# --------------------------------------------------------------------------- #
@dataclass
class Turno:
    pregunta: str
    respuesta: Respuesta | None = None


@dataclass
class Archivo:
    """Un balance de prueba subido; se relee cuando cambian la unidad, la fecha o un ajuste."""
    nombre: str
    datos: bytes
    fecha: date
    reclasif: dict[str, float] = field(default_factory=dict)    # campo de RECLASIF → monto
    estado: EstadoFinanciero | None = None
    error: str | None = None


@dataclass
class Sesion:
    ctx: ContextoEmpresa | None = None       # None hasta tener razón social, CIIU y un balance
    razon_social: str = ""
    ciiu: str = ""
    unidad: str = "pesos"
    # ponytail: archivos en memoria (hasta MAX_ARCHIVOS × MAX_MB por sesión); pasarlos a disco
    # o a la base cuando haya varios usuarios
    archivos: list[Archivo] = field(default_factory=list)
    chat: list[Turno] = field(default_factory=list)
    pendientes: dict[str, Turno] = field(default_factory=dict)


_SESIONES: OrderedDict[str, Sesion] = OrderedDict()
_CANDADO = threading.Lock()


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
            s = _SESIONES[sid] = Sesion()
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


def _faltantes(s: Sesion) -> list[str]:
    faltan = [] if s.razon_social else ["la razón social"]
    if not (s.ciiu.isdigit() and len(s.ciiu) == 4):
        faltan.append("el código CIIU de 4 dígitos")
    return faltan


def _actualizar(s: Sesion) -> None:
    """Relee cada archivo y arma el historial con los que se leyeron bien."""
    factor = UNIDADES[s.unidad][1]
    mapeo = cargar_mapeo()
    s.archivos.sort(key=lambda a: a.fecha)
    fechas: set[date] = set()
    for a in s.archivos:
        a.estado, a.error = None, None
        if a.fecha in fechas:
            a.error = "Otro archivo tiene la misma fecha de corte: corrija una de las dos."
            continue
        ajustes = [(*par, a.reclasif[campo] * factor) for campo, par, _ in RECLASIF
                   if a.reclasif.get(campo, 0) > 0]
        try:
            df = leer_balance_prueba(io.BytesIO(a.datos), a.nombre)
            a.estado = a_estado_financiero(df.assign(saldo=df["saldo"] * factor), a.fecha,
                                           mapeo, ajustes)
            fechas.add(a.fecha)
        except ErrorCarga as e:
            a.error = str(e)
    periodos = [a.estado for a in s.archivos if a.estado]
    s.ctx = None
    if periodos and not _faltantes(s):
        historial = HistorialFinanciero(
            empresa=Empresa(empresa_id="usuario", razon_social=s.razon_social, ciiu=s.ciiu),
            periodos=periodos)
        s.ctx = ContextoEmpresa(historial=historial, referencia=cargar_referencia(
            s.ciiu, historial.ultimo.fecha_corte.year))


def _sin_referencia(h: HistorialFinanciero) -> str:
    """Aviso concreto: qué CIIU y año faltan y qué referencias sí hay."""
    hay = ", ".join(sorted(r.stem.replace("_", " ") for r in REFERENCIAS.glob("*.json")))
    return (f"No hay referencia sectorial para el CIIU {h.empresa.ciiu} en "
            f"{h.ultimo.fecha_corte.year} (por ahora hay: {hay or 'ninguna'}). El resto del "
            "análisis funciona; solo la comparación con el sector no estará disponible.")


def _carga(s: Sesion, errores: list[str] | None = None) -> dict:
    """Lo que muestra la tarjeta de la empresa: datos, archivos leídos y qué falta."""
    if s.ctx:
        estado = (f"Listo: estados financieros de {_anios(s.ctx.historial)}. Ya puede "
                  "preguntarle al economista.")
    elif not s.archivos:
        estado = "Suba al menos un balance de prueba."
    elif not any(a.estado for a in s.archivos):
        estado = "Ningún archivo se pudo leer: revise los errores."
    else:
        estado = f"Para analizar la empresa falta {' y '.join(_faltantes(s))}."
    return {
        "razon_social": s.razon_social, "ciiu": s.ciiu, "unidad": s.unidad, "unidades": UNIDADES,
        "max_mb": MAX_MB, "errores": errores or [], "estado": estado, "listo": s.ctx is not None,
        "sin_referencia": (_sin_referencia(s.ctx.historial)
                           if s.ctx and s.ctx.referencia is None else None),
        "reclasif": RECLASIF,
        "archivos": [{"i": i, "nombre": a.nombre, "fecha": a.fecha.isoformat(), "error": a.error,
                      "reclasif": a.reclasif, "renglones": libro([
                          ("Activo total", formatear(a.estado.balance.activo_total, "pesos"), None),
                          ("Pasivo total", formatear(a.estado.balance.pasivo_total, "pesos"), None),
                          ("Patrimonio", formatear(a.estado.balance.patrimonio_total, "pesos"), None),
                      ]) if a.estado else None}
                     for i, a in enumerate(s.archivos)],
    }


def _contexto(request: Request, s: Sesion, **extra) -> dict:
    return {"empresa": s.razon_social, "modulos": MODULOS, "turnos": _turnos(s), **extra}


def _pagina(request: Request, plantilla: str, contexto: dict, status: int = 200):
    return PLANTILLAS.TemplateResponse(request, plantilla, contexto, status_code=status)


# --------------------------------------------------------------------------- #
# Páginas
# --------------------------------------------------------------------------- #
@router.get("/", response_class=HTMLResponse)
def portada(request: Request, s: Sesion = Depends(sesion)):
    return _pagina(request, "portada.html", _contexto(request, s, c=_carga(s)))


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
# Empresa: balances de prueba que se leen al subirlos
# --------------------------------------------------------------------------- #
def _tarjeta(request: Request, s: Sesion, errores: list[str] | None = None):
    """La tarjeta de la empresa y, fuera de banda, el nombre en la barra superior."""
    return _pagina(request, "_carga.html", {"c": _carga(s, errores), "empresa": s.razon_social,
                                            "oob": True})


@router.post("/empresa", response_class=HTMLResponse)
async def empresa(request: Request, s: Sesion = Depends(sesion)):
    """Cualquier cambio de la tarjeta: datos de la empresa, fechas, ajustes o archivos nuevos."""
    form = await request.form()
    s.razon_social = str(form.get("razon_social", "")).strip()[:120]
    s.ciiu = str(form.get("ciiu", "")).strip()
    if (unidad := str(form.get("unidad", ""))) in UNIDADES:
        s.unidad = unidad
    errores = []
    for i, a in enumerate(s.archivos):
        try:
            a.fecha = date.fromisoformat(str(form.get(f"fecha_{i}", "")))
        except ValueError:
            pass        # fecha vacía o a medio escribir: se conserva la anterior
        for campo, _, etiqueta in RECLASIF:
            texto = str(form.get(f"{campo}_{i}", "")).strip() or "0"
            try:
                monto = float(texto)
                if not monto >= 0:          # también descarta NaN
                    raise ValueError
                a.reclasif[campo] = monto
            except ValueError:
                errores.append(f"{a.nombre}: «{etiqueta}» debe ser un número positivo o cero.")
    for archivo in form.getlist("archivos"):
        if not (isinstance(archivo, UploadFile) and archivo.filename):
            continue
        nombre = Path(archivo.filename).name
        datos = await archivo.read(MAX_MB * 1_048_576 + 1)
        if len(s.archivos) >= MAX_ARCHIVOS:
            errores.append(f"Se pueden subir máximo {MAX_ARCHIVOS} archivos.")
            break
        if Path(nombre).suffix.lower() not in EXTENSIONES:
            errores.append(f"{nombre}: el archivo debe ser .csv, .xlsx o .xls.")
        elif len(datos) > MAX_MB * 1_048_576:
            errores.append(f"{nombre}: cada archivo debe pesar menos de {MAX_MB} MB.")
        else:
            s.archivos.append(Archivo(nombre=nombre, datos=datos, fecha=corte_sugerido(nombre)))
    _actualizar(s)
    return _tarjeta(request, s, errores)


@router.post("/empresa/quitar/{i}", response_class=HTMLResponse)
def quitar(request: Request, i: int, s: Sesion = Depends(sesion)):
    if 0 <= i < len(s.archivos):
        del s.archivos[i]
    _actualizar(s)
    return _tarjeta(request, s)


@router.post("/empresa/borrar", response_class=HTMLResponse)
def borrar(request: Request, s: Sesion = Depends(sesion)):
    """Empezar de nuevo: otra empresa, así que el chat (fuera de #pagina) también se vacía."""
    s.ctx, s.razon_social, s.ciiu, s.unidad, s.archivos = None, "", "", "pesos", []
    s.chat.clear()
    respuesta = _tarjeta(request, s)
    respuesta.headers["HX-Trigger"] = "empresa-cambiada"
    return respuesta
