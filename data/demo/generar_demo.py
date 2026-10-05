"""
Genera los balances de prueba en PUC del Hotel Demo Andino S.A.S., empresa
FICTICIA para demostraciones. Historia: rentable (margen operacional ~25 %)
pero ilíquida (razón corriente 0,67) por deuda bancaria de corto plazo; pagó
240 millones de dividendos en 2024. De la cuenta 2105, 600 millones (2023) y
520 millones (2024) son de largo plazo: pasarlos como reclasificaciones.

Uso: python data/demo/generar_demo.py
"""
import pandas as pd
NOMBRES = {
    "1105": "Caja", "1110": "Bancos", "1305": "Clientes", "1330": "Anticipos y avances",
    "1355": "Anticipo de impuestos y contribuciones", "1435": "Mercancías no fabricadas por la empresa",
    "1504": "Terrenos", "1516": "Construcciones y edificaciones", "1524": "Equipo de oficina",
    "1528": "Equipo de computación y comunicación", "1592": "Depreciación acumulada",
    "1705": "Gastos pagados por anticipado", "2105": "Bancos nacionales",
    "2205": "Proveedores nacionales", "2335": "Costos y gastos por pagar",
    "2404": "Impuesto de renta y complementarios", "2408": "Impuesto sobre las ventas por pagar",
    "2510": "Cesantías consolidadas", "2525": "Vacaciones consolidadas",
    "2805": "Anticipos y avances recibidos", "3105": "Capital suscrito y pagado",
    "3305": "Reservas obligatorias", "3705": "Utilidades acumuladas",
    "4155": "Hoteles y restaurantes", "4210": "Financieros", "4250": "Recuperaciones",
    "5105": "Gastos de personal", "5135": "Servicios", "5145": "Mantenimiento y reparaciones",
    "5160": "Depreciaciones", "5195": "Diversos", "5205": "Gastos de personal (ventas)",
    "5235": "Servicios (comisiones de agencias)", "5305": "Financieros",
    "5315": "Gastos extraordinarios", "5405": "Impuesto de renta y complementarios",
    "6155": "Hoteles y restaurantes (costo de alimentos y bebidas)",
}
# Millones de pesos; débito positivo. 3705 se calcula para que cuadre.
ANIOS = {
    2023: {"1105": 12, "1110": 50, "1305": 95, "1330": 8, "1355": 20, "1435": 25, "1504": 600,
           "1516": 2400, "1524": 320, "1528": 50, "1592": -680, "1705": 10,
           "2105": -760, "2205": -80, "2335": -35, "2404": -30, "2408": -18, "2510": -32,
           "2525": -10, "2805": -20, "3105": -1200, "3305": -46,
           "4155": -1600, "4210": -4, "4250": -2, "6155": 240, "5105": 390, "5135": 190,
           "5145": 85, "5160": 135, "5195": 55, "5205": 80, "5235": 105, "5305": 110,
           "5315": 6, "5405": 70},
    2024: {"1105": 15, "1110": 85, "1305": 120, "1330": 10, "1355": 25, "1435": 30, "1504": 600,
           "1516": 2400, "1524": 350, "1528": 60, "1592": -820, "1705": 12,
           "2105": -680, "2205": -95, "2335": -40, "2404": -48, "2408": -22, "2510": -38,
           "2525": -12, "2805": -30, "3105": -1200, "3305": -60,
           "4155": -1850, "4210": -6, "4250": -4, "6155": 260, "5105": 420, "5135": 210,
           "5145": 95, "5160": 140, "5195": 60, "5205": 90, "5235": 120, "5305": 95,
           "5315": 8, "5405": 125},
}
for anio, saldos in ANIOS.items():
    saldos["3705"] = -sum(saldos.values())          # utilidades acumuladas que cuadran
    filas = sorted(saldos.items())
    # Filas padre por clase y grupo, como las exporta el software contable
    padres = {}
    for c, v in filas:
        for nivel in (c[:1], c[:2]):
            padres[nivel] = padres.get(nivel, 0) + v
    todas = sorted({**padres, **dict(filas)}.items())
    pd.DataFrame({
        "Código": [c for c, _ in todas],
        "Nombre de la cuenta": [NOMBRES.get(c, "") for c, _ in todas],
        "Saldo final": [v * 1_000_000 for _, v in todas],
    }).to_csv(f"data/demo/hotel_demo_andino_{anio}.csv", index=False, encoding="utf-8")
    print(anio, "utilidades acumuladas (millones):", -saldos["3705"])
