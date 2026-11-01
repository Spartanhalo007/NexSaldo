"""Formato de visualización de importes (solo pantalla, no almacenamiento)."""


def formatear_valor(valor, moneda):
    """Da formato colombiano a un importe: $ 15.000,00 o US$ 1.234,50."""
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    prefijo = "$" if moneda == "COP" else "US$"
    return f"{prefijo} {texto}"


NOMBRES_MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def nombre_mes(anno, mes):
    """Devuelve el nombre legible de un mes, ej.: 'noviembre de 2026'."""
    return f"{NOMBRES_MESES[mes - 1]} de {anno}"
