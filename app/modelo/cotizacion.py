"""Modelo de dominio para una cotización en tiempo real obtenida mediante yfinance."""

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class Cotizacion:
    id: Optional[int]
    simbolo: str
    fecha: date
    precio: Decimal
    moneda: str
    fuente: str = "Yahoo Finance (Tiempo real)"

    def con_id(self, nuevo_id: int) -> "Cotizacion":
        return replace(self, id=nuevo_id)