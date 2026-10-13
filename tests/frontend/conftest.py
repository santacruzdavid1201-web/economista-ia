import pytest

from data_sources.externos.series import catalogo
from data_sources.externos.series.modelo import Serie


@pytest.fixture(autouse=True)
def series_guardadas(monkeypatch):
    """El tablero macro lee las copias de data/series/ sin descargar: los tests no usan la red."""
    def local(variable, geografia, hoy, directorio=catalogo.DIRECTORIO, forzar=False):
        nombre, _ = catalogo._buscar(variable, geografia)
        archivo = directorio / f"{variable}_{catalogo.sin_tildes(nombre).replace(' ', '_')}.json"
        return Serie.model_validate_json(archivo.read_text(encoding="utf-8"))
    monkeypatch.setattr(catalogo, "obtener", local)
