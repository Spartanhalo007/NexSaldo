"""Modelo de transferencia entre cuentas.

Representa la plata que se mueve de una cuenta a otra (por ejemplo, pagar
la tarjeta Amex desde la cuenta principal). No es un ingreso ni un gasto:
solo cambia de ubicación el dinero.
"""

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Transferencia:
    """Una transferencia entre dos cuentas de la misma moneda."""

    id: int | None
    cuenta_origen_id: int          # cuenta de la que sale la plata.
    cuenta_destino_id: int         # cuenta a la que llega la plata.
    valor: object                  # Decimal; nunca float.
    moneda: str                    # COP o USD, igual a las dos cuentas.
    fecha: object                  # datetime.date.
    comentarios: str | None = None
    imagen: str | None = None      # ruta del adjunto opcional.

    def con_id(self, id_nuevo: int) -> "Transferencia":
        """Devuelve una copia con el id asignado por la base de datos."""
        return replace(self, id=id_nuevo)
