"""
Aplicación web del economista IA.

    python -m uvicorn app.main:app --port 8000      # http://localhost:8000

Al arrancar y cada 6 horas descarga de nuevo las series macro nacionales en
segundo plano: el tablero y el chat leen esas copias y quedan al día solos.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from data_sources.externos.series import catalogo
from frontend import web

CADA = 6 * 60 * 60          # segundos entre actualizaciones de las series macro
registro = logging.getLogger(__name__)


async def _actualizar_series() -> None:
    while True:
        try:
            # En un hilo: las descargas tardan y no deben bloquear la interfaz
            for problema in await asyncio.to_thread(catalogo.actualizar):
                registro.warning(problema)
        except Exception:
            # Un fallo inesperado no detiene las actualizaciones siguientes
            registro.exception("Falló la actualización de las series macro.")
        await asyncio.sleep(CADA)


@asynccontextmanager
async def ciclo(_app: FastAPI):
    tarea = asyncio.create_task(_actualizar_series())
    yield
    tarea.cancel()


app = FastAPI(title="Economista IA", docs_url=None, redoc_url=None, lifespan=ciclo)
app.mount("/static", StaticFiles(directory=Path(web.__file__).with_name("static")), name="static")
web.instalar(app)
