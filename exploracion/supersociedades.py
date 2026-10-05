"""
Exploración de los datos de Supersociedades en Datos Abiertos Colombia.

No es parte del sistema: es la fase previa para decidir CÓMO construir el
benchmark. Produce archivos en exploracion/salidas/ que luego revisamos juntos.

Uso (desde la raíz del proyecto, con el entorno activado):

    python exploracion/supersociedades.py buscar
    python exploracion/supersociedades.py inspeccionar <id_dataset>

`buscar` consulta el catálogo de datos.gov.co y lista los datasets candidatos
con su identificador (formato xxxx-xxxx). `inspeccionar` describe uno de ellos:
columnas, número de filas, muestra, valores de PUNTO_ENTRADA y TAXONOMIA,
rango de fechas, catálogo de conceptos contables y si trae CIIU.

Requiere: pip install requests pandas
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import requests

DOMINIO = "www.datos.gov.co"
CATALOGO = "https://api.us.socrata.com/api/catalog/v1"
SALIDAS = Path(__file__).parent / "salidas"
TIMEOUT = 180  # segundos; las agregaciones sobre millones de filas tardan

BUSQUEDAS = [
    "supersociedades estado de situación financiera",
    "supersociedades estado de resultado integral",
    "supersociedades flujo de efectivo",
    "supersociedades carátula",
    "supersociedades estados financieros NIIF",
]

# Columnas que interesan, buscadas por coincidencia parcial del nombre técnico
COLUMNAS_CLAVE = ["punto_entrada", "taxonomia", "periodo", "fecha_corte", "ciiu",
                  "departamento", "ciudad", "macrosector"]


def _get(url: str, params: dict | None = None) -> list | dict:
    r = requests.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def _soql(id_dataset: str, **params) -> pd.DataFrame:
    """Consulta SoQL contra la API de recursos de Socrata."""
    url = f"https://{DOMINIO}/resource/{id_dataset}.json"
    return pd.DataFrame(_get(url, {f"${k}": v for k, v in params.items()}))


# --------------------------------------------------------------------------- #
def buscar() -> None:
    filas = []
    for q in BUSQUEDAS:
        datos = _get(CATALOGO, {"domains": DOMINIO, "search_context": DOMINIO,
                                "q": q, "limit": 20})
        for item in datos.get("results", []):
            res = item.get("resource", {})
            filas.append({
                "id": res.get("id"),
                "nombre": res.get("name"),
                "entidad": item.get("classification", {}).get("domain_metadata", [{}])[0].get("value")
                if item.get("classification", {}).get("domain_metadata") else None,
                "actualizado": res.get("data_updated_at") or res.get("updatedAt"),
                "columnas": ", ".join(res.get("columns_field_name", [])),
                "busqueda": q,
            })
    if not filas:
        print("El catálogo no devolvió resultados. Revisa tu conexión o prueba en el navegador:")
        print(f"  https://{DOMINIO}/browse?q=supersociedades")
        return

    df = pd.DataFrame(filas).drop_duplicates(subset="id")
    df = df[df["nombre"].str.contains("financ|resultado|carátula|caratula|flujo|situaci",
                                      case=False, na=False)]
    SALIDAS.mkdir(parents=True, exist_ok=True)
    df.to_csv(SALIDAS / "catalogo_datasets.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.max_colwidth", 70)
    print(df[["id", "nombre", "actualizado"]].to_string(index=False))
    print(f"\n{len(df)} datasets candidatos guardados en {SALIDAS / 'catalogo_datasets.csv'}")


# --------------------------------------------------------------------------- #
def inspeccionar(id_dataset: str) -> None:
    destino = SALIDAS / id_dataset
    destino.mkdir(parents=True, exist_ok=True)
    resumen: list[str] = []

    def anotar(texto: str = "") -> None:
        print(texto)
        resumen.append(texto)

    # 1. Metadatos y columnas
    meta = _get(f"https://{DOMINIO}/api/views/{id_dataset}.json")
    columnas = pd.DataFrame([
        {"campo": c.get("fieldName"), "nombre": c.get("name"), "tipo": c.get("dataTypeName")}
        for c in meta.get("columns", [])
    ])
    columnas.to_csv(destino / "columnas.csv", index=False, encoding="utf-8-sig")
    anotar(f"# {meta.get('name')} ({id_dataset})")
    anotar(f"Entidad: {meta.get('attribution')} | Actualizado: {meta.get('rowsUpdatedAt')}")
    anotar("\n## Columnas")
    anotar(columnas.to_string(index=False))

    campos = columnas["campo"].tolist()
    def encontrar(parte: str) -> str | None:
        # Primero el nombre exacto: si no, "punto_entrada" encontraría "id_punto_entrada"
        if parte in campos:
            return parte
        return next((c for c in campos if parte in c.lower()), None)

    # 2. Número de filas
    total = _soql(id_dataset, select="count(*) AS n")
    anotar(f"\n## Filas: {int(total.iloc[0, 0]):,}".replace(",", "."))

    # 3. Muestra
    muestra = _soql(id_dataset, limit=50)
    muestra.to_csv(destino / "muestra.csv", index=False, encoding="utf-8-sig")
    anotar("\n## Muestra (primeras 5 filas)")
    anotar(muestra.head().to_string(index=False))

    # 4. Valores de las columnas clave
    for parte in COLUMNAS_CLAVE:
        campo = encontrar(parte)
        if campo is None:
            anotar(f"\n## {parte}: no existe en este dataset")
            continue
        try:
            conteo = _soql(id_dataset, select=f"{campo}, count(*) AS n",
                           group=campo, order="n DESC", limit=200)
            conteo.to_csv(destino / f"valores_{parte}.csv", index=False, encoding="utf-8-sig")
            anotar(f"\n## {parte} ({campo}): {len(conteo)} valores distintos")
            anotar(conteo.head(15).to_string(index=False))
        except requests.HTTPError as e:
            anotar(f"\n## {parte}: error al agrupar ({e})")

    # 5. Catálogo de conceptos contables (el insumo del mapeo al esquema canónico)
    concepto = encontrar("concepto")
    conceptos = None
    if concepto:
        try:
            conceptos = _soql(id_dataset, select=f"{concepto}, count(*) AS n",
                              group=concepto, order="n DESC", limit=10000)
            conceptos.to_csv(destino / "conceptos.csv", index=False, encoding="utf-8-sig")
            anotar(f"\n## Conceptos contables: {len(conceptos)} distintos "
                   f"(lista completa en conceptos.csv)")
            anotar(conceptos.head(40).to_string(index=False))
        except requests.HTTPError as e:
            anotar(f"\n## Conceptos: error al agrupar ({e})")

    # 6. ¿Trae CIIU? Puede venir como columna o como concepto (caso de la carátula)
    anotar("\n## CIIU")
    ciiu_concepto = conceptos is not None and conceptos[concepto].str.contains("CIIU", na=False).any()
    if encontrar("ciiu"):
        anotar("Sí trae CIIU como columna.")
    elif ciiu_concepto:
        anotar("Trae CIIU como concepto (formato 'I5511 - Descripción').")
    else:
        anotar("NO trae CIIU: habrá que cruzarlo por NIT con otro dataset (p. ej. la carátula).")

    (destino / "resumen.md").write_text("\n".join(resumen), encoding="utf-8")
    print(f"\nArchivos guardados en {destino}")


# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("buscar", help="Lista datasets candidatos de Supersociedades")
    p = sub.add_parser("inspeccionar", help="Describe un dataset por su id")
    p.add_argument("id_dataset", help="Identificador tipo xxxx-xxxx")
    args = parser.parse_args()

    try:
        if args.comando == "buscar":
            buscar()
        else:
            inspeccionar(args.id_dataset)
    except requests.RequestException as e:
        sys.exit(f"Error de conexión con datos.gov.co: {e}")


if __name__ == "__main__":
    main()
