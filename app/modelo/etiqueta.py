"""Modelo de dominio para etiquetas personalizables de movimientos y gastos."""

from dataclasses import dataclass, replace
from typing import Optional


@dataclass(frozen=True)
class Etiqueta:
    id: Optional[int]
    nombre: str
    color: str = "#408FD1"

    def con_id(self, nuevo_id: int) -> "Etiqueta":
        return replace(self, id=nuevo_id)
