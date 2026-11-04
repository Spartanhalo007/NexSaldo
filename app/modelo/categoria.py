"""Modelo de dominio para categorías personalizadas y predeterminadas de gastos/ingresos."""

from dataclasses import dataclass, replace
from typing import Optional


@dataclass(frozen=True)
class Categoria:
    id: Optional[int]
    nombre: str
    tipo: str = "GASTO"
    simbolo: str = "mercado"
    color: str = "#FBB718"
    es_predeterminada: bool = False
    gasto_programado: bool = False
    frecuencia: Optional[str] = None

    def con_id(self, nuevo_id: int) -> "Categoria":
        return replace(self, id=nuevo_id)
