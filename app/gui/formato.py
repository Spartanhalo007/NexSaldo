"""Utilidades de formato para importes monetarios y fechas en NexSaldo."""

from datetime import date, timedelta
from decimal import Decimal

from app.modelo.divisas import obtener_prefijo_divisa

NOMBRES_MESES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]

NOMBRES_DIAS = [
    "lun.",
    "mar.",
    "mié.",
    "jue.",
    "vie.",
    "sáb.",
    "dom.",
]


def formatear_valor(valor, moneda: str = "COP") -> str:
    """Da formato colombiano a un importe en cualquier divisa del mundo: $ 15.000,00, US$ 1.234,50, € 50,00."""
    numero = Decimal(str(valor)) if not isinstance(valor, Decimal) else valor
    texto = (
        f"{numero:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )
    prefijo = obtener_prefijo_divisa(moneda)
    return f"{prefijo} {texto}"


def nombre_mes(anno: int, mes: int) -> str:
    if 1 <= mes <= 12:
        return f"{NOMBRES_MESES[mes - 1]} de {anno}"
    return f"{mes}/{anno}"


def fecha_legible(fecha: date, hoy: date | None = None) -> str:
    referencia = hoy or date.today()
    if fecha == referencia:
        return "Hoy"
    if fecha == referencia - timedelta(days=1):
        return "Ayer"
    dia_sem = NOMBRES_DIAS[fecha.weekday()]
    mes_abrev = NOMBRES_MESES[fecha.month - 1][:3]
    return f"{dia_sem}, {fecha.day} {mes_abrev}."
