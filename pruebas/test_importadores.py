"""Pruebas de la importación multi-broker (módulo Inversiones).

Cobertura:
- Parser de Binance (Historial de operaciones Spot, dos variantes de
  columnas) con datos ficticios.
- Parser de Interactive Brokers (sección Trades de Flex Query).
- Despacho por broker y errores esperables.
- Llaves de detección de duplicados (símbolo + fecha + monto).
- Integración contra PostgreSQL del flujo completo de importación con
  omisión de duplicados (requiere .env; si no hay conexión se omite).

Datos 100% ficticios, marcados con símbolos TEST para no confundirlos
con datos reales.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.gestor.gestor_financiero import (
    GestorFinanciero,
    clave_duplicado_inversion,
    clave_duplicado_posicion,
)
from app.modelo.inversion import Inversion
from app.servicio.importadores import (
    BROKERS,
    _consolidar_por_ticker,
    parsear_archivo_broker,
    parsear_binance_csv,
    parsear_ibkr_csv,
)

BINANCE_V2 = """Date(UTC),Pair,Side,Price,Executed,Amount,Fee
2026-03-15 00:03:12,ETHUSDT,BUY,2400.00,0.10000000ETH,240.00000000USDT,0.00010000ETH
2026-03-16 00:03:12,ETHUSDT,SELL,2500.00,0.10000000ETH,250.00000000USDT,0.00010000ETH
2026-04-20 10:00:00,BTCUSDT,BUY,88000.00,0.00100000BTC,88.00000000USDT,0.00000100BTC
2026-05-01 09:30:00,TST1USD,BUY,190.00,1.00000000TST1,190.00000000USD,0.10000000TST1
"""

BINANCE_V1 = """Date(UTC),Market,Type,Price,Amount,Total,Fee,Fee Coin
2026-03-15 00:03:12,ETHUSDT,BUY,2400.00,0.10000000,240.00000000USDT,0.00010000,ETH
2026-03-16 00:03:12,ETHUSDT,SELL,2500.00,0.10000000,250.00000000USDT,0.00010000,ETH
"""

IBKR = """Symbol,Date/Time,Buy/Sell,Quantity,TradePrice,CurrencyPrimary,AssetClass
TST2,"2026-07-01, 09:35:00",BOT,20,120.50,USD,STK
TST2,"2026-07-02, 14:05:00",SLD,-20,131.00,USD,STK
TST3,20260701;143000,BOT,10,190.00,USD,STK
TST4,2026-07-01,BOT,5,500.00,USD,STK
TST5,2026-07-01,BOT,1,2.50,USD,OPT
"""


def _crear_csv(tmp_path, nombre, contenido):
    ruta = tmp_path / nombre
    ruta.write_text(contenido, encoding="utf-8")
    return str(ruta)


# ---------------------------------------------------------------------------
# Binance
# ---------------------------------------------------------------------------

def test_binance_formato_actual_importa_solo_compras(tmp_path):
    """El Historial de operaciones Spot (columnas actuales) importa solo BUY."""
    posiciones = parsear_binance_csv(_crear_csv(tmp_path, "binance.csv", BINANCE_V2))

    assert len(posiciones) == 3  # la venta (SELL) queda excluida.

    eth = next(p for p in posiciones if p["simbolo"] == "ETH-USD")
    assert eth["monto_invertido"] == Decimal("240.00")
    assert eth["unidades"] == Decimal("0.10000000")
    assert eth["precio_compra"] == Decimal("2400.00")
    assert eth["moneda"] == "USD"  # USDT se registra como USD.
    assert eth["fecha_compra"] == date(2026, 3, 15)

    btc = next(p for p in posiciones if p["simbolo"] == "BTC-USD")
    assert btc["monto_invertido"] == Decimal("88.00")

    # Compra cotizada directamente en USD (sin establecoin).
    tstd = next(p for p in posiciones if p["simbolo"] == "TST1-USD")
    assert tstd["moneda"] == "USD"
    assert tstd["nombre"] == "TST1"


def test_binance_formato_antiguo(tmp_path):
    """La variante con Market/Type/Amount/Total también se lee."""
    posiciones = parsear_binance_csv(_crear_csv(tmp_path, "binance_v1.csv", BINANCE_V1))

    assert len(posiciones) == 1  # solo la compra.
    eth = posiciones[0]
    assert eth["simbolo"] == "ETH-USD"
    assert eth["monto_invertido"] == Decimal("240.00")
    assert eth["unidades"] == Decimal("0.10000000")


def test_binance_consolidacion_por_ticker(tmp_path):
    """Con agrupar_por_ticker, dos compras del mismo activo quedan en una."""
    contenido = (
        "Date(UTC),Pair,Side,Price,Executed,Amount,Fee\n"
        "2026-01-10 00:00:00,ETHUSDT,BUY,2000.00,0.10000000ETH,200.00000000USDT,0\n"
        "2026-02-10 00:00:00,ETHUSDT,BUY,2500.00,0.10000000ETH,250.00000000USDT,0\n"
    )
    posiciones = parsear_binance_csv(
        _crear_csv(tmp_path, "binance_dca.csv", contenido),
        agrupar_por_ticker=True,
    )

    assert len(posiciones) == 1
    grupo = posiciones[0]
    assert grupo["simbolo"] == "ETH-USD"
    assert grupo["monto_invertido"] == Decimal("450.00")
    assert grupo["unidades"] == Decimal("0.20000000")
    # Precio promedio ponderado: 450 / 0.2 = 2250.
    assert grupo["precio_compra"] == Decimal("2250")
    # La fecha del grupo es la compra más antigua.
    assert grupo["fecha_compra"] == date(2026, 1, 10)


# ---------------------------------------------------------------------------
# Interactive Brokers
# ---------------------------------------------------------------------------

def test_ibkr_importa_solo_compras_de_acciones(tmp_path):
    posiciones = parsear_ibkr_csv(_crear_csv(tmp_path, "ibkr.csv", IBKR))

    # Se importan TST2 (BOT), TST3 y TST4. Quedan fuera la venta (SLD)
    # y la opción (AssetClass OPT).
    assert len(posiciones) == 3
    assert {p["simbolo"] for p in posiciones} == {"TST2", "TST3", "TST4"}

    tst2 = next(p for p in posiciones if p["simbolo"] == "TST2")
    assert tst2["monto_invertido"] == Decimal("2410.00")  # 20 * 120.50
    assert tst2["unidades"] == Decimal("20")
    assert tst2["moneda"] == "USD"
    assert tst2["fecha_compra"] == date(2026, 7, 1)

    # Fecha compacta de IBKR (20260701;143000).
    tst3 = next(p for p in posiciones if p["simbolo"] == "TST3")
    assert tst3["fecha_compra"] == date(2026, 7, 1)


def test_ibkr_consolidacion_por_ticker(tmp_path):
    contenido = (
        "Symbol,Date/Time,Buy/Sell,Quantity,TradePrice,CurrencyPrimary\n"
        "TST6,2026-01-10,BOT,10,100.00,USD\n"
        "TST6,2026-02-10,BOT,10,200.00,USD\n"
    )
    posiciones = parsear_ibkr_csv(
        _crear_csv(tmp_path, "ibkr_dca.csv", contenido),
        agrupar_por_ticker=True,
    )

    assert len(posiciones) == 1
    assert posiciones[0]["monto_invertido"] == Decimal("3000.00")
    assert posiciones[0]["unidades"] == Decimal("20")
    assert posiciones[0]["fecha_compra"] == date(2026, 1, 10)


# ---------------------------------------------------------------------------
# Registro de brokers y despacho
# ---------------------------------------------------------------------------

def test_registro_de_brokers_tiene_las_cinco_plataformas():
    assert set(BROKERS) == {"etoro", "binance", "ibkr", "trii", "hapi"}


def test_despacho_por_broker_y_error_si_no_existe(tmp_path):
    ruta = _crear_csv(tmp_path, "binance.csv", BINANCE_V2)
    posiciones = parsear_archivo_broker(ruta, "binance")
    assert len(posiciones) == 3

    with pytest.raises(ValueError):
        parsear_archivo_broker(ruta, "broker_inexistente")


# ---------------------------------------------------------------------------
# Detección de duplicados
# ---------------------------------------------------------------------------

def _posicion(simbolo, fecha, monto):
    return {
        "simbolo": simbolo,
        "nombre": simbolo,
        "monto_invertido": Decimal(monto),
        "moneda": "USD",
        "precio_compra": Decimal("100"),
        "unidades": Decimal("1"),
        "fecha_compra": fecha,
        "notas": None,
    }


def test_clave_duplicado_ignora_diferencias_de_redondeo():
    """El monto se compara en centavos: 200.001 y 200.00 son iguales."""
    a = clave_duplicado_posicion(_posicion("VOO", date(2026, 1, 10), "200.001"))
    b = clave_duplicado_posicion(_posicion("VOO", date(2026, 1, 10), "200.00"))
    assert a == b


def test_clave_duplicado_distingue_fecha_y_monto():
    base = _posicion("VOO", date(2026, 1, 10), "200.00")

    otra_fecha = clave_duplicado_posicion(_posicion("VOO", date(2026, 2, 10), "200.00"))
    otro_monto = clave_duplicado_posicion(_posicion("VOO", date(2026, 1, 10), "500.00"))
    otra_posicion = clave_duplicado_posicion(_posicion("VOO", date(2026, 1, 10), "200.00"))

    assert otra_posicion == clave_duplicado_posicion(base)
    assert otra_fecha != clave_duplicado_posicion(base)
    assert otro_monto != clave_duplicado_posicion(base)


def test_clave_duplicado_inversion_coincide_con_posicion():
    """Lo que guardó la base y lo que trae el archivo deben comparar igual."""
    inversion = Inversion(
        id=1,
        simbolo="VOO",
        nombre="Vanguard S&P 500",
        monto_invertido=Decimal("200.00"),
        moneda="USD",
        precio_compra=Decimal("100"),
        cantidad_titulos=Decimal("2"),
        fecha_compra=date(2026, 1, 10),
    )
    posicion = _posicion("VOO", date(2026, 1, 10), "200.00")

    assert clave_duplicado_inversion(inversion) == clave_duplicado_posicion(posicion)


def test_consolidar_por_ticker_sume_correctamente():
    posiciones = [
        _posicion("VOO", date(2026, 1, 10), "250.00"),
        _posicion("VOO", date(2026, 3, 10), "250.00"),
        _posicion("AAPL", date(2026, 2, 10), "100.00"),
    ]
    consolidadas = _consolidar_por_ticker(posiciones)

    assert len(consolidadas) == 2
    voo = next(p for p in consolidadas if p["simbolo"] == "VOO")
    assert voo["monto_invertido"] == Decimal("500.00")
    assert voo["fecha_compra"] == date(2026, 1, 10)


# ---------------------------------------------------------------------------
# Integración con PostgreSQL: importación con omisión de duplicados
# ---------------------------------------------------------------------------

def _gestor_con_bd():
    """Crea el gestor con la base real si hay .env; si no, omite la prueba."""
    try:
        from app.configuracion import cargar_configuracion_bd
        from app.repositorio.repositorio_local import RepositorioLocal

        repositorio = RepositorioLocal(cargar_configuracion_bd())
        repositorio.conectar()
        repositorio.aplicar_esquema()
    except Exception:
        pytest.skip(
            "No se pudo conectar a PostgreSQL con la configuración de .env; "
            "prueba de integración omitida."
        )
    gestor = GestorFinanciero(repositorio)
    # Sin red en las pruebas: los precios vienen del propio archivo.
    gestor.consultar_precio_historico_inversion = lambda *a, **k: None  # type: ignore[method-assign]
    gestor.consultar_precio_inversion = lambda *a, **k: None  # type: ignore[method-assign]
    return gestor, repositorio


def _limpiar_inversiones_prueba(repositorio):
    repositorio.ejecutar_consulta(
        "DELETE FROM inversion WHERE simbolo LIKE %s", ("TST%",))
    repositorio.conectar().commit()


def test_importar_lote_con_omision_de_duplicados(tmp_path):
    """Importar dos veces el mismo archivo sin reemplazar no duplica posiciones."""
    gestor, repositorio = _gestor_con_bd()
    _limpiar_inversiones_prueba(repositorio)
    try:
        lote = [
            _posicion("TSTDUP", date(2026, 1, 10), "200.00"),
            _posicion("TSTNUEVA", date(2026, 1, 10), "100.00"),
        ]

        # Primera importación: reemplaza (base vacía).
        importadas, omitidas = gestor.importar_inversiones_lote(
            lote, limpiar_antes=True)
        assert len(importadas) == 2
        assert omitidas == 0

        # Segunda importación del MISMO lote sin reemplazar: todo duplicado.
        importadas, omitidas = gestor.importar_inversiones_lote(
            lote, limpiar_antes=False, omitir_duplicados=True)
        assert len(importadas) == 0
        assert omitidas == 2

        # Lote con una nueva y una repetida: importa solo la nueva.
        lote_mixto = lote + [_posicion("TSTOTRA", date(2026, 2, 10), "50.00")]
        importadas, omitidas = gestor.importar_inversiones_lote(
            lote_mixto, limpiar_antes=False, omitir_duplicados=True)
        assert len(importadas) == 1
        assert omitidas == 2
        assert importadas[0].simbolo == "TSTOTRA"

        # Sin omitir duplicados ni reemplazar, sí quedan repetidas
        # (comportamiento anterior sin cambios).
        importadas, omitidas = gestor.importar_inversiones_lote(
            lote, limpiar_antes=False, omitir_duplicados=False)
        assert len(importadas) == 2
        assert omitidas == 0
    finally:
        _limpiar_inversiones_prueba(repositorio)
