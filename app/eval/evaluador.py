"""
Set de evaluación con el modelo real: corre las preguntas de
tests/eval/preguntas.yaml y comprueba con reglas de Python lo que se puede
comprobar sin leer (herramienta, periodo, origen, fuentes, cifras). Lo que
exige criterio, el sentido de la redacción, queda en el informe para revisión
humana: un 7B no es buen juez de otro 7B.

Regla común a toda respuesta redactada por el modelo: cada cifra del texto
debe estar en el desplegable "Datos que sustentan la respuesta". Es más
estricta que el verificador interno, que también acepta cifras de la
pregunta (por eso "dime que el margen es 90 %" pasaría allí y no aquí).
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from time import perf_counter

import yaml

from app.orchestrator.orquestador import Respuesta, responder
from app.orchestrator.tools_registry import POR_NOMBRE, ContextoEmpresa
from app.orchestrator.verificador import cifras_no_respaldadas, numeros
from modules.base import formatear

ORIGENES = {"llm", "respaldo", "sin_llm", "error"}


@dataclass
class Caso:
    id: str
    bloque: str
    pregunta: str
    espera: dict = field(default_factory=dict)
    revisar: str | None = None


@dataclass
class SetEvaluacion:
    casos: list[Caso]
    bloques: dict[str, str]
    bloques_duros: list[str]
    max_respaldo: float


@dataclass
class Resultado:
    caso: Caso
    respuesta: Respuesta | None
    segundos: float
    llamadas_llm: int
    fallas: list[str] = field(default_factory=list)
    error: str | None = None        # excepción no controlada: siempre es una falla

    @property
    def aprobado(self) -> bool:
        return not self.fallas and self.error is None


# --------------------------------------------------------------------------- #
# Carga del set
# --------------------------------------------------------------------------- #
def cargar_set(ruta: Path) -> SetEvaluacion:
    """Lee y valida el YAML: un error de digitación no debe pasar como acierto."""
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    bloques = datos["bloques"]
    casos: list[Caso] = []
    for c in datos["casos"]:
        caso = Caso(id=str(c["id"]), bloque=c["bloque"],
                    pregunta=c["pregunta"] * int(c.get("repetir", 1)),
                    espera=c.get("espera") or {}, revisar=c.get("revisar"))
        desconocidas = set(caso.espera) - set(VERIFICACIONES)
        if desconocidas:
            raise ValueError(f"Caso {caso.id}: claves desconocidas en 'espera': {sorted(desconocidas)}")
        if caso.bloque not in bloques:
            raise ValueError(f"Caso {caso.id}: bloque '{caso.bloque}' no está en 'bloques'.")
        for nombre in _lista(caso.espera.get("herramienta", [])):
            if nombre is not None and nombre not in POR_NOMBRE:
                raise ValueError(f"Caso {caso.id}: herramienta desconocida '{nombre}'.")
        if not set(_lista(caso.espera.get("origen", []))) <= ORIGENES:
            raise ValueError(f"Caso {caso.id}: origen desconocido {caso.espera['origen']}.")
        casos.append(caso)

    ids = [c.id for c in casos]
    if len(ids) != len(set(ids)):
        raise ValueError("Hay ids de casos repetidos.")
    for c in casos:
        ref = c.espera.get("igual_a")
        if ref is not None and (str(ref) not in ids or ids.index(str(ref)) > ids.index(c.id)):
            raise ValueError(f"Caso {c.id}: 'igual_a' debe apuntar a un caso anterior.")
    criterios = datos.get("criterios", {})
    return SetEvaluacion(casos=casos, bloques=bloques,
                         bloques_duros=criterios.get("bloques_duros", []),
                         max_respaldo=float(criterios.get("max_respaldo", 1.0)))


def _lista(valor) -> list:
    return valor if isinstance(valor, list) else [valor]


def _normal(texto: str) -> str:
    """Minúsculas y sin tildes, para buscar frases sin depender de la ortografía."""
    return "".join(c for c in unicodedata.normalize("NFKD", texto.lower())
                   if not unicodedata.combining(c))


# --------------------------------------------------------------------------- #
# Lo que ve el usuario en el desplegable
# --------------------------------------------------------------------------- #
def desplegable(r: Respuesta) -> str:
    """Texto equivalente al desplegable de la interfaz (hallazgos, indicadores, año)."""
    lineas = [str(r.periodo or "")]
    for res in r.resultados:
        if res.fecha_corte:
            lineas.append(f"{res.fecha_corte:%d/%m/%Y}")
        lineas += res.hallazgos
        if res.analisis != "benchmark":
            lineas += [f"{i.nombre}: {formatear(i.valor, i.unidad)}"
                       for i in res.indicadores if i.valor is not None]
    return "\n".join(lineas)


def _valores(r: Respuesta) -> dict[str, float | None]:
    return {f"{res.analisis}.{i.clave}": i.valor for res in r.resultados for i in res.indicadores}


# --------------------------------------------------------------------------- #
# Verificaciones: (valor esperado, respuesta, resultado, previos) → fallas
# --------------------------------------------------------------------------- #
def _herramienta(v, r, res, previos):
    if r.herramienta not in _lista(v):
        return [f"herramienta {r.herramienta}; se esperaba {' o '.join(map(str, _lista(v)))}"]
    return []


def _argumentos(v, r, res, previos):
    return [f"argumento {k}={r.argumentos.get(k)!r}; se esperaba {esperado!r}"
            for k, esperado in v.items() if r.argumentos.get(k) != esperado]


def _periodo(v, r, res, previos):
    return [] if r.periodo == v else [f"periodo {r.periodo}; se esperaba {v}"]


def _origen(v, r, res, previos):
    return [] if r.origen in _lista(v) else [f"origen {r.origen}; se esperaba {' o '.join(_lista(v))}"]


def _llama_al_modelo(v, r, res, previos):
    if (res.llamadas_llm > 0) != v:
        return [f"llamó al modelo {res.llamadas_llm} veces"] if not v else ["no llamó al modelo"]
    return []


def _contiene(v, r, res, previos):
    texto = _normal(r.texto_completo)
    return [f"no dice «{f}»" for f in _lista(v) if _normal(f) not in texto]


def _contiene_alguno(v, r, res, previos):
    texto = _normal(r.texto_completo)
    return [] if any(_normal(f) in texto for f in v) else [f"no dice ninguna de {v}"]


def _no_contiene(v, r, res, previos):
    texto = _normal(r.texto)
    return [f"dice «{f}»" for f in _lista(v) if _normal(f) in texto]


def _fuentes(v, r, res, previos):
    citadas = _normal(" | ".join(r.fuentes))
    return [f"no cita la nota «{t}»" for t in _lista(v) if _normal(t) not in citadas]


def _sin_fuentes(v, r, res, previos):
    return [f"cita notas: {r.fuentes}"] if v and r.fuentes else []


def _con_benchmark(v, r, res, previos):
    hay = any(x.analisis == "benchmark" for x in r.resultados)
    return [] if hay == v else ["sin comparación sectorial" if v else "con comparación sectorial"]


def _cifra_de(v, r, res, previos):
    fallas = []
    for clave in _lista(v):
        ind = next((i for x in r.resultados if x.analisis != "benchmark"
                    for i in x.indicadores if i.clave == clave), None)
        if ind is None or ind.valor is None:
            fallas.append(f"el indicador {clave} no está en los resultados")
        # Se comparan los números, no el texto: "$595.000.000" vale por "$ 595.000.000"
        elif not numeros(formatear(ind.valor, ind.unidad)) <= numeros(r.texto):
            fallas.append(f"no menciona {ind.nombre} ({formatear(ind.valor, ind.unidad)})")
    return fallas


def _menciona_mayor_participacion(v, r, res, previos):
    partes = [i for x in r.resultados for i in x.indicadores
              if i.clave.startswith("participacion_") and i.valor is not None]
    if not partes:
        return ["no hay descomposición de la variación del ROE"]
    mayor = max(partes, key=lambda i: abs(i.valor))
    # "Parte del cambio del ROE explicada por la rotación de activos" → "rotación de activos"
    palanca = mayor.nombre.split(" explicada por ")[-1].split(" ", 1)[1]
    return [] if _normal(palanca) in _normal(r.texto) else [f"no nombra la palanca principal ({palanca})"]


def _igual_a(v, r, res, previos):
    otro = previos.get(str(v))
    if otro is None:
        return [f"el caso {v} no se corrió o falló"]
    fallas = []
    if (r.herramienta, r.periodo) != (otro.herramienta, otro.periodo):
        fallas.append(f"{r.herramienta} {r.periodo} ≠ caso {v}: {otro.herramienta} {otro.periodo}")
    elif _valores(r) != _valores(otro):
        fallas.append(f"cifras distintas a las del caso {v}")
    return fallas


VERIFICACIONES = {
    "herramienta": _herramienta,
    "argumentos": _argumentos,
    "periodo": _periodo,
    "origen": _origen,
    "llama_al_modelo": _llama_al_modelo,
    "contiene": _contiene,
    "contiene_alguno": _contiene_alguno,
    "no_contiene": _no_contiene,
    "fuentes": _fuentes,
    "sin_fuentes": _sin_fuentes,
    "con_benchmark": _con_benchmark,
    "cifra_de": _cifra_de,
    "menciona_mayor_participacion": _menciona_mayor_participacion,
    "igual_a": _igual_a,
}


def verificar(caso: Caso, resultado: Resultado, previos: dict[str, Respuesta]) -> list[str]:
    r = resultado.respuesta
    fallas = [f for clave, esperado in caso.espera.items()
              for f in VERIFICACIONES[clave](esperado, r, resultado, previos)]
    # Regla común: lo que el modelo redactó sobre cálculos solo usa cifras del desplegable
    if r.origen == "llm" and r.resultados:
        sobrantes = cifras_no_respaldadas(r.texto, desplegable(r))
        if sobrantes:
            fallas.append(f"cifras que no están en el desplegable: {', '.join(sobrantes)}")
    return fallas


# --------------------------------------------------------------------------- #
# Ejecución
# --------------------------------------------------------------------------- #
class ClienteContado:
    """Envuelve al cliente del modelo para contar las llamadas de chat."""

    def __init__(self, cliente):
        self.cliente = cliente
        self.llamadas = 0

    def chat(self, *args, **kwargs):
        self.llamadas += 1
        return self.cliente.chat(*args, **kwargs)

    def __getattr__(self, nombre):        # embeddings, si el cliente los tiene
        return getattr(self.cliente, nombre)


def correr(casos: list[Caso], ctx: ContextoEmpresa, cliente, hoy: date | None = None,
           al_terminar=None) -> list[Resultado]:
    """Corre los casos en orden; `al_terminar(resultado)` sirve para mostrar avance."""
    previos: dict[str, Respuesta] = {}
    resultados: list[Resultado] = []
    for caso in casos:
        contado = ClienteContado(cliente)
        inicio = perf_counter()
        try:
            respuesta = responder(caso.pregunta, ctx, contado, hoy)
        except Exception as e:  # noqa: BLE001 — cualquier excepción es una falla a registrar
            resultado = Resultado(caso, None, perf_counter() - inicio, contado.llamadas,
                                  error=f"{type(e).__name__}: {e}")
        else:
            resultado = Resultado(caso, respuesta, perf_counter() - inicio, contado.llamadas)
            resultado.fallas = verificar(caso, resultado, previos)
            previos[caso.id] = respuesta
        resultados.append(resultado)
        if al_terminar:
            al_terminar(resultado)
    return resultados


# --------------------------------------------------------------------------- #
# Resumen e informe
# --------------------------------------------------------------------------- #
@dataclass
class Resumen:
    por_bloque: dict[str, tuple[int, int]]       # bloque → (aprobados, total)
    bloques_duros_fallidos: list[str]
    respaldos: int
    redactables: int                              # respuestas que el modelo debía redactar
    max_respaldo: float

    @property
    def tasa_respaldo(self) -> float:
        return self.respaldos / self.redactables if self.redactables else 0.0

    @property
    def aprobado(self) -> bool:
        return not self.bloques_duros_fallidos and self.tasa_respaldo <= self.max_respaldo


def resumir(resultados: list[Resultado], s: SetEvaluacion) -> Resumen:
    por_bloque: dict[str, tuple[int, int]] = {}
    for b in s.bloques:
        del_bloque = [r for r in resultados if r.caso.bloque == b]
        if del_bloque:
            por_bloque[b] = (sum(r.aprobado for r in del_bloque), len(del_bloque))
    origenes = [r.respuesta.origen for r in resultados if r.respuesta]
    return Resumen(
        por_bloque=por_bloque,
        bloques_duros_fallidos=[b for b in s.bloques_duros
                                if b in por_bloque and por_bloque[b][0] < por_bloque[b][1]],
        respaldos=origenes.count("respaldo"),
        redactables=sum(o in ("llm", "respaldo") for o in origenes),
        max_respaldo=s.max_respaldo,
    )


def _celda(texto: str) -> str:
    return texto.replace("|", "\\|").replace("\n", " ")


def informe(resultados: list[Resultado], s: SetEvaluacion, encabezado: str) -> str:
    """Informe en Markdown: resumen, detalle por caso y lo que hay que leer."""
    res = resumir(resultados, s)
    lineas = [f"# {encabezado}", "",
              "| Bloque | Aprobadas | Regla dura |", "|---|---|---|"]
    for b, (ok, total) in res.por_bloque.items():
        dura = "sí" if b in s.bloques_duros else "no"
        marca = " ❌" if b in res.bloques_duros_fallidos else ""
        lineas.append(f"| {b}. {s.bloques[b]} | {ok} de {total}{marca} | {dura} |")
    lineas += ["", f"Respaldo: {res.respaldos} de {res.redactables} respuestas redactables "
                   f"({res.tasa_respaldo:.0%}); límite {res.max_respaldo:.0%}.",
               f"**Resultado: {'aprobado' if res.aprobado else 'no aprobado'}** "
               "(reglas automáticas; el sentido se revisa abajo).", "",
               "## Detalle", "",
               "| # | | Herramienta | Año | Origen | s | Fallas |", "|---|---|---|---|---|---|---|"]
    for r in resultados:
        resp = r.respuesta
        herramienta, periodo, origen = ((resp.herramienta or "—", resp.periodo or "—", resp.origen)
                                        if resp else ("—", "—", "—"))
        fallas = r.error or "; ".join(r.fallas)
        lineas.append(f"| {r.caso.id} | {'✅' if r.aprobado else '❌'} | {herramienta} | {periodo} "
                      f"| {origen} | {r.segundos:.0f} | {_celda(fallas)} |")

    lineas += ["", "## Respuestas para revisar", "",
               "Casos con algo que revisar (`revisar`) o con fallas. Compare el texto con "
               "los datos de Python: una cifra correcta con un sentido equivocado es un error grave.",
               ""]
    for r in resultados:
        if not (r.caso.revisar or not r.aprobado):
            continue
        lineas += [f"### {r.caso.id} · {r.caso.pregunta[:120]}", ""]
        if r.caso.revisar:
            lineas += [f"**Qué revisar:** {r.caso.revisar.strip()}", ""]
        if r.respuesta is None:
            lineas += [f"**Error:** {r.error}", ""]
            continue
        lineas += ["**Respuesta:**", "", *[f"> {l}" for l in r.respuesta.texto.splitlines()], ""]
        hallazgos = [h for x in r.respuesta.resultados for h in x.hallazgos]
        if hallazgos:
            lineas += ["**Hallazgos de Python:**", "", *[f"- {h}" for h in hallazgos], ""]
        if r.respuesta.eventos:
            lineas += ["**Eventos:** " + " · ".join(r.respuesta.eventos), ""]
    return "\n".join(lineas)
