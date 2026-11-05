"""Pruebas unitarias para ServicioBursatil en tiempo real (Yahoo Finance) y conversión USD <-> COP."""

from datetime import date
from decimal import Decimal

from app.gestor.gestor_financiero import GestorFinanciero
from app.modelo.cotizacion import Cotizacion
from app.servicio.servicio_bursatil import (
    SIMBOLO_USD_COP,
    ServicioBursatil,
)
from pruebas.test_modulo_gastos import RepositorioFalsoGastos


class TickerTiempoRealFalso:
    def __init__(self, simbolo: str, precio_actual: float = 3220.19):
        self.simbolo = simbolo
        self.fast_info = {"last_price": precio_actual}


class ModuloYFinanceFalso:
    def __init__(self, precio: float = 3220.19):
        self._precio = precio

    def Ticker(self, simbolo: str):
        return TickerTiempoRealFalso(simbolo, self._precio)


def test_servicio_bursatil_consulta_tasa_usd_cop_tiempo_real():
    servicio = ServicioBursatil(proveedor_yf=ModuloYFinanceFalso(3220.19))
    cotizacion = servicio.consultar_tasa_usd_cop()
    assert isinstance(cotizacion, Cotizacion)
    assert cotizacion.simbolo == SIMBOLO_USD_COP
    assert cotizacion.precio == Decimal("3220.19")
    assert cotizacion.moneda == "COP"
    assert cotizacion.fecha == date.today()


def test_conversion_bidireccional_exacta_usd_y_cop():
    servicio = ServicioBursatil(proveedor_yf=ModuloYFinanceFalso(3220.19))
    gestor = GestorFinanciero(RepositorioFalsoGastos(), servicio_bursatil=servicio)

    assert gestor.convertir_usd_a_cop(Decimal("1")) == Decimal("3220.19")
    assert gestor.convertir_usd_a_cop(Decimal("300")) == Decimal("966057.00")

    assert gestor.convertir_cop_a_usd(Decimal("966057.00")) == Decimal("300.00")
    assert gestor.convertir_cop_a_usd(Decimal("3220.19")) == Decimal("1.00")
