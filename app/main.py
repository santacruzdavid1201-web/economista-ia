"""
Aplicación web del economista IA.

    python -m uvicorn app.main:app --port 8000      # http://localhost:8000
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from frontend import web

app = FastAPI(title="Economista IA", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=Path(web.__file__).with_name("static")), name="static")
web.instalar(app)
