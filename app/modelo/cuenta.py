"""Modelo de cuenta personal (módulo Cuentas).

Representa una cuenta del usuario (efectivo, banco, tarjeta...) con su
moneda, su símbolo distintivo, su color y su saldo. El saldo actual no se
almacena: se calcula como saldo inicial + transferencias recibidas -
transferencias enviadas.
"""

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Cuenta:
    """Una cuenta personal y su estado.

    saldo_inicial es la plata con la que arranca la cuenta; el saldo
    actual se calcula aparte (RepositorioLocal.saldo_de_cuentas).
    """

    id: int | None
    nombre: str
    moneda: str                    # COP o USD (regla de la tesis).
    saldo_inicial: object          # Decimal; nunca float.
    simbolo: str                   # clave del catálogo de íconos.
    color: str                     # color elegido, formato #RRGGBB.
    incluye_en_total: bool = True
    nota: str | None = None

    def con_id(self, id_nuevo: int) -> "Cuenta":
        """Devuelve una copia con el id asignado por la base de datos."""
        return replace(self, id=id_nuevo)
