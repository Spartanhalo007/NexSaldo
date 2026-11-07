"""Modelo de dominio para un movimiento financiero (ingreso o gasto)."""

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Optional, Tuple


@dataclass(frozen=True)
class MovimientoFinanciero:
    id: Optional[int]
    tipo_movimiento: str
    fecha: date
    valor: Decimal
    moneda: str
    categoria: str
    descripcion: Optional[str] = None
    cuenta_id: Optional[int] = None
    etiquetas: Tuple[str, ...] = ()
    imagen: Optional[str] = None
    es_programado: bool = False
    frecuencia: Optional[str] = None

    def con_id(self, nuevo_id: int) -> "MovimientoFinanciero":
        return replace(self, id=nuevo_id)
