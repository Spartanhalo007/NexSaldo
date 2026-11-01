"""Modelo de datos de la tesis: MovimientoFinanciero.

Representa un ingreso o un gasto registrado manualmente por el usuario.
Los importes se manejan con Decimal (nunca float) y la fecha con date.
"""

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class MovimientoFinanciero:
    """Un movimiento de ingreso o gasto personal.

    Atributos:
        tipo_movimiento: 'INGRESO' o 'GASTO'.
        fecha: día del movimiento (sin hora).
        valor: importe del movimiento, siempre mayor que cero.
        moneda: 'COP' o 'USD'.
        categoria: nombre de la categoría del catálogo.
        descripcion: texto opcional, vacío se guarda como None.
        id: identificador asignado por la base de datos (None si no está guardado).
    """

    id: Optional[int]
    tipo_movimiento: str
    fecha: date
    valor: Decimal
    moneda: str
    categoria: str
    descripcion: Optional[str] = None

    def con_id(self, nuevo_id: int) -> "MovimientoFinanciero":
        """Devuelve una copia del movimiento con el id asignado por la base de datos."""
        return replace(self, id=nuevo_id)
