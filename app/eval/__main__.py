"""
Corre el set de evaluación con el modelo real sobre el hotel de demostración.

Uso, con el servidor del modelo encendido:
    python -m app.eval                  # todas las preguntas
    python -m app.eval --casos 13,14    # algunas (se agregan las de referencia de igual_a)
    python -m app.eval --bloques D,E

Escribe el informe en data/eval/AAAA-MM-DD_HHMM.md. Sale con código 1 si falla
una regla dura o el respaldo supera el límite.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime

from app.config import RAIZ, config
from app.demo import contexto_demo
from app.eval.evaluador import cargar_set, correr, informe, resumir
from app.llm.client import ClienteLLM

PREGUNTAS = RAIZ / "tests" / "eval" / "preguntas.yaml"
SALIDA = RAIZ / "data" / "eval"


def _lista(texto: str | None) -> set[str]:
    return {x.strip() for x in texto.split(",") if x.strip()} if texto else set()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Set de evaluación con el modelo real.")
    parser.add_argument("--casos", help="ids separados por coma, p. ej. 13,14")
    parser.add_argument("--bloques", help="bloques separados por coma, p. ej. D,E")
    args = parser.parse_args()

    s = cargar_set(PREGUNTAS)
    casos, bloques = _lista(args.casos), _lista(args.bloques)
    if casos or bloques:
        elegidos = {c.id for c in s.casos if c.id in casos or c.bloque in bloques}
        elegidos |= {str(c.espera["igual_a"]) for c in s.casos
                     if c.id in elegidos and "igual_a" in c.espera}
        s.casos = [c for c in s.casos if c.id in elegidos]
        if not s.casos:
            print("Ningún caso coincide con el filtro.")
            return 1

    modelo = config().llm_modelo
    print(f"Evaluando {len(s.casos)} casos con {modelo}…\n")

    def avance(r):
        estado = "✅" if r.aprobado else "❌"
        origen = r.respuesta.origen if r.respuesta else "excepción"
        print(f"  {r.caso.id:>4} {estado} {r.segundos:5.1f} s  {origen:<9} {r.caso.pregunta[:60]}")

    resultados = correr(s.casos, contexto_demo(), ClienteLLM(), al_terminar=avance)
    ahora = datetime.now()
    texto = informe(resultados, s, f"Evaluación · {ahora:%Y-%m-%d %H:%M} · {modelo}")
    SALIDA.mkdir(parents=True, exist_ok=True)
    ruta = SALIDA / f"{ahora:%Y-%m-%d_%H%M}.md"
    ruta.write_text(texto, encoding="utf-8")

    res = resumir(resultados, s)
    print()
    for b, (ok, total) in res.por_bloque.items():
        print(f"  {b}. {s.bloques[b]:<36} {ok} de {total}")
    print(f"  Respaldo: {res.respaldos} de {res.redactables} ({res.tasa_respaldo:.0%})")
    print(f"\n{'Aprobado' if res.aprobado else 'No aprobado'}. Informe: {ruta.relative_to(RAIZ)}")
    return 0 if res.aprobado else 1


if __name__ == "__main__":
    sys.exit(main())
