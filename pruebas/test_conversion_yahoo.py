"""Pruebas unitarias para el catálogo mundial de divisas, últimas 5 divisas usadas y modo
'Solo esta moneda' vs 'Todo convertido' en tiempo real con Yahoo Finance."""

from datetime import date
from decimal import Decimal

from app.gestor.gestor_financiero import ErrorValidacion, GestorFinanciero
from app.modelo.cotizacion import Cotizacion
from app.modelo.divisas import (
    CODIGOS_DIVISAS_ORDENADOS,
    DIVISAS_MUNDIALES,
    construir_lista_selector_divisas,
    extraer_codigo_divisa,
)
from app.servicio.servicio_bursatil import SIMBOLO_USD_COP, ServicioBursatil
from pruebas.test_modulo_gastos import RepositorioFalsoGastos


class TickerTiempoRealMultidivisa:
    def __init__(self, simbolo: str):
        self.simbolo = simbolo
        tasas = {
            "USDCOP=X": 3321.00,
            "EURCOP=X": 3600.00,
            "COPUSD=X": 1.0 / 3321.00,
        }
        self.fast_info = {"last_price": tasas.get(simbolo, 3321.00)}


class ModuloYFinanceMultidivisa:
    def Ticker(self, simbolo: str):
        return TickerTiempoRealMultidivisa(simbolo)


def test_catalogo_divisas_mundiales_sin_criptomonedas_y_top_5():
    # Solo divisas fiduciarias ISO 4217, sin criptomonedas
    for cripto in ("BTC", "ETH", "USDT", "SOL", "BNB", "XRP"):
        assert cripto not in DIVISAS_MUNDIALES

    # La moneda inválida "EUR" de la prueba original era inválida antes, pero "INVALIDA" debe fallar
    assert "COP" in DIVISAS_MUNDIALES
    assert "USD" in DIVISAS_MUNDIALES
    assert "EUR" in DIVISAS_MUNDIALES
    assert "JPY" in DIVISAS_MUNDIALES

    # Lista selector: COP siempre primero + 4 recientes + resto en orden alfabético
    opciones = construir_lista_selector_divisas(["JPY", "EUR", "USD", "GBP", "MXN"])
    codigos_top_5 = [extraer_codigo_divisa(op) for op in opciones[:5]]
    assert codigos_top_5 == ["COP", "JPY", "EUR", "USD", "GBP"]

    # El resto después de los 5 primeros está en estricto orden alfabético
    resto = [extraer_codigo_divisa(op) for op in opciones[5:]]
    assert resto == sorted(resto)
    assert len(opciones) == len(CODIGOS_DIVISAS_ORDENADOS)


def test_modo_solo_divisa_vs_todo_convertido():
    servicio = ServicioBursatil(proveedor_yf=ModuloYFinanceMultidivisa())
    repo = RepositorioFalsoGastos()
    # Asegurar que el repo falso devuelva resumen mensual de sus movimientos
    def _resumen_mensual(anno, mes):
        acum = {}
        for m in repo._movimientos:
            if m.fecha.year == anno and m.fecha.month == mes:
                clave = (m.tipo_movimiento, m.moneda, m.categoria)
                acum[clave] = acum.get(clave, Decimal("0")) + m.valor
        return [(k[0], k[1], k[2], v) for k, v in acum.items()]

    repo.resumen_mensual = _resumen_mensual
    gestor = GestorFinanciero(repo, servicio_bursatil=servicio)

    # Registrar un gasto de 10.000 COP y otro de 1 USD (a tasa 3.321 COP)
    gestor.registrar_gasto(
        valor_texto="10000",
        moneda="COP",
        categoria="Alimentación",
        fecha_texto="2026-11-05",
    )
    gestor.registrar_gasto(
        valor_texto="1",
        moneda="USD",
        categoria="Ocio",
        fecha_texto="2026-11-05",
    )

    # 1. Modo "Solo esta moneda" en COP -> muestra únicamente 10.000 COP
    solo_cop = gestor.resumen_del_mes_en_moneda(
        2026, 11, moneda_objetivo="COP", incluir_todas_convertidas=False
    )
    assert solo_cop["gastos"] == Decimal("10000")

    # 2. Modo "Solo esta moneda" en USD -> muestra únicamente 1 USD
    solo_usd = gestor.resumen_del_mes_en_moneda(
        2026, 11, moneda_objetivo="USD", incluir_todas_convertidas=False
    )
    assert solo_usd["gastos"] == Decimal("1")

    # 3. Modo "Todo convertido" en COP -> 10.000 COP + (1 USD * 3.321) = 13.321,00 COP
    todo_en_cop = gestor.resumen_del_mes_en_moneda(
        2026, 11, moneda_objetivo="COP", incluir_todas_convertidas=True
    )
    assert todo_en_cop["gastos"] == Decimal("13321.00")
    assert todo_en_cop["gastos_por_categoria"]["Alimentación"] == Decimal("10000.00")
    assert todo_en_cop["gastos_por_categoria"]["Ocio"] == Decimal("3321.00")
