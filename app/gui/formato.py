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


NOMBRES_DIAS = [
    "lunes", "martes", "miércoles", "jueves",
    "viernes", "sábado", "domingo",
]


def fecha_legible(fecha, hoy=None):
    """Formatea una fecha para el usuario.

    Ejemplos: 'hoy, 3 de noviembre de 2026 (martes)' o
    '3 de noviembre de 2026 (domingo)'. El día de la semana entre paréntesis.
    """
    from datetime import date as _date

    if hoy is None:
        hoy = _date.today()
    dia_semana = NOMBRES_DIAS[fecha.weekday()]
    texto = f"{fecha.day} de {nombre_mes(fecha.year, fecha.month)}"
    prefijo = "hoy, " if fecha == hoy else ""
    return f"{prefijo}{texto} ({dia_semana})"
