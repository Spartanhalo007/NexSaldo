"""Importación de portafolios desde varios brokers (módulo Inversiones).

Cada broker tiene su propio formato de exportación. Este módulo centraliza:

1. El registro BROKERS con los datos de cada plataforma (nombre,
   instrucciones para exportar el archivo y el parser que lo lee).
2. Parsers para los formatos documentados públicamente:
   - eToro: Estado de Cuenta .xlsx o CSV (importador_etoro, sin cambios).
   - Binance: Historial de operaciones Spot en CSV.
   - Interactive Brokers: Trades Flex Query / Activity Statement en CSV.
   - Trii y Hapi: no publican un formato de exportación en CSV; se usa la
     plantilla CSV genérica de NexSaldo (mismas columnas que el CSV de
     eToro) con instrucciones para copiar el portafolio desde la app.

Todos los parsers devuelven la misma estructura que espera
GestorFinanciero.importar_inversiones_lote: una lista de diccionarios con
simbolo, nombre, monto_invertido (Decimal), moneda, precio_compra,
unidades, fecha_compra (date) y notas.

Notas de diseño (decisiones registradas):
- Los importes se manejan con Decimal, nunca float.
- De Binance solo se importan las compras (BUY) contra moneda fiduciaria
  o estable (USDT/USDC se tratan como USD, con nota en la inversión).
- De IBKR solo se importan compras de acciones/ETFs/cripto (se omiten
  opciones y futuros).
"""

import csv
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Dict, List, Optional

from app.modelo.inversion import normalizar_simbolo_yahoo
from app.servicio.importador_etoro import parsear_archivo_etoro_o_csv

# ---------------------------------------------------------------------------
# Utilidades comunes
# ---------------------------------------------------------------------------

# Establecoins que Binance usa como moneda de cotización: se registran
# como USD (1:1 aproximado, se deja nota en la inversión).
ESTABLECOINES_A_USD = {"USDT", "USDC", "FDUSD", "TUSD", "DAI"}

# Activos de cotización reconocidos en pares de Binance (el más largo
# primero para que 'ETHUSDT' no se parta como ETH + USDT... sino como
# ETH + USDT: el sufijo más largo gana).
COTIZACIONES_BINANCE = [
    "FDUSD", "USDC", "USDT", "TUSD", "DAI", "USD", "COP", "EUR", "TRY",
    "BRL", "GBP", "JPY", "AUD", "CAD", "CHF", "MXN", "ARS", "RUB",
    "BTC", "ETH", "BNB", "SOL", "XRP", "TRX", "DOT",
]


def _leer_csv_con_delimitador(ruta: Path) -> List[List[str]]:
    """Lee un CSV detectando el delimitador (coma, punto y coma o tab)."""
    contenido = ruta.read_text(encoding="utf-8-sig", errors="replace")
    muestra = contenido[:2048]
    delimitador = ";" if muestra.count(";") > muestra.count(",") else ","
    if "\t" in muestra and muestra.count("\t") > muestra.count(delimitador):
        delimitador = "\t"
    lector = csv.reader(contenido.splitlines(), delimiter=delimitador)
    return [list(fila) for fila in lector if any(c.strip() for c in fila)]


def _a_decimal(valor: object) -> Optional[Decimal]:
    """Convierte texto a Decimal; devuelve None si no se puede."""
    if valor is None:
        return None
    texto = re.sub(r"[^\d.,\-]", "", str(valor)).replace(",", ".")
    if not texto or texto in ("-", ".", "-."):
        return None
    try:
        return Decimal(texto)
    except InvalidOperation:
        return None


def _dividir_par_binance(par: str) -> Optional[tuple]:
    """Parte 'ETHUSDT' en ('ETH', 'USDT') usando los sufijos conocidos."""
    par = (par or "").strip().upper()
    if "/" in par:  # algunos exportadores usan ETH/USDT
        base, cotizacion = par.split("/", 1)
        return base.strip(), cotizacion.strip()
    for cotizacion in COTIZACIONES_BINANCE:
        if par.endswith(cotizacion) and len(par) > len(cotizacion):
            return par[: -len(cotizacion)], cotizacion
    return None


def _moneda_de_cotizacion(cotizacion: str) -> Optional[str]:
    """Mapea el activo de cotización a una divisa del app.

    Las establecoins se registran como USD; el resto de criptos no se
    pueden registrar como divisa de una inversión (se omite la fila).
    """
    cotizacion = (cotizacion or "").strip().upper()
    if cotizacion in ESTABLECOINES_A_USD:
        return "USD"
    if re.fullmatch(r"[A-Z]{3}", cotizacion):
        return cotizacion  # divisa fiduciaria (USD, COP, EUR, TRY...).
    return None


def _parsear_fecha_flexible(texto: object) -> Optional[date]:
    """Acepta los formatos de fecha más comunes en exportaciones."""
    if texto is None:
        return None
    texto = str(texto).strip().strip('"')
    if not texto:
        return None
    formatos = (
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d, %H:%M:%S", "%Y-%m-%d %H:%M",
        "%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%d/%m/%Y", "%m/%d/%Y",
    )
    for formato in formatos:
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    # Formato compacto de IBKR: '20260701;143000'.
    if ";" in texto:
        try:
            return datetime.strptime(texto.split(";", 1)[0], "%Y%m%d").date()
        except ValueError:
            return None
    return None


def _consolidar_por_ticker(posiciones: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """Agrupa las compras por ticker en una sola posición.

    Suma los montos y las unidades, y calcula el precio promedio
    ponderado. La fecha de compra del grupo es la de la compra más
    antigua (cuando se empezó a acumular la posición).
    """
    grupos: Dict[str, List[Dict[str, object]]] = {}
    for posicion in posiciones:
        grupos.setdefault(str(posicion["simbolo"]), []).append(posicion)

    consolidadas: List[Dict[str, object]] = []
    for simbolo, grupo in grupos.items():
        monto_total = sum((p["monto_invertido"] for p in grupo), Decimal("0"))
        unidades_total = sum(
            (p.get("unidades") or Decimal("0") for p in grupo), Decimal("0"))
        precio: Optional[Decimal] = None
        if unidades_total > 0:
            precio = (monto_total / unidades_total)
        fechas = [p["fecha_compra"] for p in grupo if p.get("fecha_compra")]
        consolidadas.append({
            "simbolo": simbolo,
            "nombre": grupo[0].get("nombre", simbolo),
            "monto_invertido": monto_total,
            "moneda": grupo[0].get("moneda", "USD"),
            "precio_compra": precio,
            "unidades": unidades_total if unidades_total > 0 else None,
            "fecha_compra": min(fechas) if fechas else None,
            "notas": grupo[0].get("notas"),
        })
    return consolidadas


# ---------------------------------------------------------------------------
# Parser de Binance: Historial de operaciones Spot (Trade History)
# ---------------------------------------------------------------------------

def _extraer_cantidad_y_moneda(celda: str) -> Optional[tuple]:
    """'240.00000000USDT' -> (Decimal('240.00000000'), 'USDT')."""
    celda = str(celda or "").strip()
    # La moneda admite dígitos (1INCH, TST1); un número solo no cuenta
    # como moneda.
    coincidencia = re.match(r"^([\d.,]+)\s*([A-Z0-9]{2,10})$", celda)
    if not coincidencia or coincidencia.group(2).isdigit():
        return None
    numero = _a_decimal(coincidencia.group(1))
    if numero is None:
        return None
    return numero, coincidencia.group(2).upper()


def parsear_binance_csv(ruta_archivo: str, agrupar_por_ticker: bool = False) -> List[Dict[str, object]]:
    """Lee el Historial de operaciones Spot de Binance en CSV.

    Solo importa las compras (BUY/BUYER). Formatos aceptados (columnas):

    - Actual:   Date(UTC), Pair, Side, Price, Executed, Amount, Fee
    - Antiguo:  Date(UTC), Market, Type, Price, Amount, Total, Fee [, Fee Coin]

    En el formato actual, `Executed` y `Amount` traen la cantidad y el
    activo en la misma celda (ej. '0.10000000ETH'). En el antiguo,
    `Amount` es la cantidad del activo base y `Total` el valor en la
    moneda de cotización.
    """
    ruta = Path(ruta_archivo)
    if not ruta.exists():
        raise ValueError("El archivo seleccionado no existe.")

    filas = _leer_csv_con_delimitador(ruta)
    if not filas:
        raise ValueError("El archivo está vacío.")

    encabezados = [c.strip().lower() for c in filas[0]]
    registros = [dict(zip(encabezados, fila)) for fila in filas[1:]]

    def campo(registro: Dict[str, str], *nombres: str) -> str:
        for nombre in nombres:
            for clave in registro:
                if clave == nombre or clave.startswith(nombre):
                    return str(registro[clave] or "").strip()
        return ""

    posiciones: List[Dict[str, object]] = []
    for registro in registros:
        lado = campo(registro, "side", "type").upper()
        if lado not in ("BUY", "BUYER", "COMPRA"):
            continue  # solo compras: las ventas no crean posiciones nuevas.

        par = campo(registro, "pair", "market", "symbol")
        division = _dividir_par_binance(par)
        if division is None:
            continue
        base, cotizacion = division

        fecha = _parsear_fecha_flexible(campo(registro, "date(utc)", "date"))
        precio = _a_decimal(campo(registro, "price"))

        # Cantidad ejecutada del activo base y total en la cotización.
        ejecutado = _extraer_cantidad_y_moneda(campo(registro, "executed"))
        total_celda = _extraer_cantidad_y_moneda(campo(registro, "amount"))
        if ejecutado and total_celda:
            unidades, moneda_base = ejecutado
            monto, moneda_total = total_celda
            if moneda_base != base or moneda_total != cotizacion:
                continue
        else:
            # Formato antiguo: Amount = cantidad base, Total = valor total.
            unidades = _a_decimal(campo(registro, "amount"))
            total = _extraer_cantidad_y_moneda(campo(registro, "total"))
            if unidades is None or total is None:
                continue
            monto, moneda_total = total
            if moneda_total != cotizacion:
                continue

        moneda = _moneda_de_cotizacion(cotizacion)
        if moneda is None:
            continue  # cotización en cripto (ej. ETH/BTC): no se registra.

        if not unidades or unidades <= 0 or not monto or monto <= 0:
            continue
        if fecha is None or precio is None or precio <= 0:
            continue

        es_estable = cotizacion in ESTABLECOINES_A_USD
        posiciones.append({
            "simbolo": normalizar_simbolo_yahoo(base, es_cripto=True),
            "nombre": base,
            "monto_invertido": monto,
            "moneda": moneda,
            "precio_compra": precio,
            "unidades": unidades,
            "fecha_compra": fecha,
            "notas": (
                f"Importado de Binance (compra {base}/{cotizacion}"
                + (f", {cotizacion} tratado como USD" if es_estable else "")
                + ")"
            ),
        })

    if agrupar_por_ticker:
        posiciones = _consolidar_por_ticker(posiciones)
    return posiciones


# ---------------------------------------------------------------------------
# Parser de Interactive Brokers: Trades (Flex Query / Activity Statement)
# ---------------------------------------------------------------------------

def parsear_ibkr_csv(ruta_archivo: str, agrupar_por_ticker: bool = False) -> List[Dict[str, object]]:
    """Lee la sección Trades de un Flex Query o Activity Statement de IBKR.

    Columnas reconocidas (por nombre, sin importar mayúsculas): Symbol,
    Date/Time (o TradeDate/DateTime), Buy/Sell, Quantity, TradePrice
    (o T. Price/Price), CurrencyPrimary (o Currency) y opcionalmente
    AssetClass / Asset Category.

    Solo se importan compras (BOT/BUY) de acciones, ETFs y cripto; las
    opciones y futuros se omiten.
    """
    ruta = Path(ruta_archivo)
    if not ruta.exists():
        raise ValueError("El archivo seleccionado no existe.")

    filas = _leer_csv_con_delimitador(ruta)
    if not filas:
        raise ValueError("El archivo está vacío.")

    encabezados = [c.strip().lower() for c in filas[0]]
    registros = [dict(zip(encabezados, fila)) for fila in filas[1:]]

    def campo(registro: Dict[str, str], *nombres: str) -> str:
        for nombre in nombres:
            for clave in registro:
                if clave == nombre:
                    return str(registro[clave] or "").strip()
        return ""

    # Nombres exactos primero; luego cualquier columna que empiece igual
    # (p. ej. 'trade price' vs 'price').
    def campo_flexible(registro: Dict[str, str], *nombres: str) -> str:
        valor = campo(registro, *nombres)
        if valor:
            return valor
        for nombre in nombres:
            for clave in registro:
                if clave.startswith(nombre):
                    return str(registro[clave] or "").strip()
        return ""

    posiciones: List[Dict[str, object]] = []
    for registro in registros:
        # Encabezados de sección de los Activity Statements: se omiten.
        simbolo = campo_flexible(registro, "symbol")
        if not simbolo or simbolo.lower() in ("symbol", "total", "total value"):
            continue

        clase = campo_flexible(registro, "assetclass", "asset category",
                               "assetcategory").upper()
        if clase in ("OPT", "FOP", "FUT", "WAR", "IOPT", "CFD", "BAG"):
            continue  # opciones, futuros y warrants: fuera de alcance.

        lado = campo_flexible(registro, "buy/sell", "buysell").upper()
        cantidad = _a_decimal(campo_flexible(registro, "quantity", "qty"))
        es_compra = lado in ("BOT", "BUY", "B", "COMPRA") or (
            lado == "" and cantidad is not None and cantidad > 0
        )
        if not es_compra:
            continue
        if cantidad is None or cantidad <= 0:
            continue

        precio = _a_decimal(campo_flexible(
            registro, "tradeprice", "t. price", "price"))
        if precio is None or precio <= 0:
            continue

        fecha = _parsear_fecha_flexible(campo_flexible(
            registro, "datetime", "date/time", "tradedate"))
        if fecha is None:
            continue

        moneda = campo_flexible(registro, "currencyprimary", "currency").upper()
        if not moneda:
            moneda = "USD"

        monto = (cantidad * precio).quantize(Decimal("0.01"))
        posiciones.append({
            "simbolo": normalizar_simbolo_yahoo(simbolo),
            "nombre": simbolo,
            "monto_invertido": monto,
            "moneda": moneda,
            "precio_compra": precio,
            "unidades": cantidad,
            "fecha_compra": fecha,
            "notas": "Importado de Interactive Brokers",
        })

    if agrupar_por_ticker:
        posiciones = _consolidar_por_ticker(posiciones)
    return posiciones


# ---------------------------------------------------------------------------
# Registro de brokers soportados
# ---------------------------------------------------------------------------

INSTRUCCIONES_ETORO = (
    "¿Cómo exportar tus inversiones desde eToro en 30 segundos?\n"
    "1. Entra a eToro (Web o App) → ve a 'Portafolio' (Portfolio) → haz clic en 'Historial' (History).\n"
    "2. Arriba a la derecha, abre el menú (⚙️) y elige 'Estado de cuenta' (Account Statement).\n"
    "3. Elige la fecha de inicio desde que empezaste a invertir hasta hoy, pulsa 'Crear' y haz clic en el icono de Excel (.xlsx).\n"
    "4. Súbelo aquí: NexSaldo filtra automáticamente tus posiciones abiertas actuales y consolida tus compras por ticker."
)

INSTRUCCIONES_BINANCE = (
    "¿Cómo exportar tus operaciones desde Binance en 30 segundos?\n"
    "1. Entra a Binance (Web) → menú 'Órdenes' → 'Órdenes Spot' → pestaña 'Historial de operaciones'.\n"
    "2. Pulsa el icono de exportación (descarga) y elige 'Historial de operaciones Spot'.\n"
    "3. En el Centro de descargas, elige el rango de fechas (idealmente 'Todo el historial'), formato CSV y pulsa 'Generar'.\n"
    "4. Descarga el archivo y súbelo aquí: NexSaldo importa solo tus COMPRAS spot (las ventas y los retiros se ignoran)."
)

INSTRUCCIONES_IBKR = (
    "¿Cómo exportar tus operaciones desde Interactive Brokers?\n"
    "1. Entra al Client Portal de IBKR → 'Performance & Reports' → 'Flex Queries'.\n"
    "2. Crea (o ejecuta) una 'Activity Flex Query' con la sección 'Trades' (Level of Detail: Execution).\n"
    "3. Asegúrate de incluir: Symbol, Date/Time, Buy/Sell, Quantity, Trade Price, Currency Primary.\n"
    "4. Ejecútala para todo tu historial en formato CSV, descárgala y súbela aquí: NexSaldo importa solo las compras de acciones, ETFs y cripto (omitiendo opciones y futuros)."
)

INSTRUCCIONES_TRII = (
    "Cómo traer tu portafolio de Trii:\n"
    "1. Trii no tiene una exportación pública en CSV: abre la app → sección 'Portafolio'.\n"
    "2. Descarga aquí abajo la plantilla CSV de NexSaldo y ábrela en Excel o Google Sheets.\n"
    "3. Copia tus posiciones una por una: ticker (ej. EC, BANCOL, VOO), nombre, plata invertida, divisa (COP o USD), precio de compra, unidades y fecha de compra.\n"
    "4. Guarda la plantilla como CSV y súbela aquí."
)

INSTRUCCIONES_HAPI = (
    "Cómo traer tu portafolio de Hapi:\n"
    "1. Hapi no tiene una exportación pública en CSV: abre la app → 'Banking' → 'Reportes' para ver tus estados de cuenta y confirmaciones.\n"
    "2. Descarga aquí abajo la plantilla CSV de NexSaldo y ábrela en Excel o Google Sheets.\n"
    "3. Copia tus posiciones una por una: ticker (ej. AAPL, VOO), nombre, plata invertida, divisa (USD), precio de compra, unidades y fecha de compra.\n"
    "4. Guarda la plantilla como CSV y súbela aquí."
)

BROKERS: Dict[str, Dict[str, object]] = {
    "etoro": {
        "nombre": "eToro",
        "instrucciones": INSTRUCCIONES_ETORO,
        "extensiones": ("*.xlsx", "*.csv", "*.tsv", "*.txt"),
        "parsear": parsear_archivo_etoro_o_csv,
    },
    "binance": {
        "nombre": "Binance",
        "instrucciones": INSTRUCCIONES_BINANCE,
        "extensiones": ("*.csv", "*.tsv", "*.txt"),
        "parsear": parsear_binance_csv,
    },
    "ibkr": {
        "nombre": "Interactive Brokers",
        "instrucciones": INSTRUCCIONES_IBKR,
        "extensiones": ("*.csv", "*.tsv", "*.txt"),
        "parsear": parsear_ibkr_csv,
    },
    # Trii y Hapi no publican un formato de exportación: se usa la
    # plantilla CSV genérica (mismas columnas que el CSV de eToro).
    "trii": {
        "nombre": "Trii",
        "instrucciones": INSTRUCCIONES_TRII,
        "extensiones": ("*.csv", "*.tsv", "*.txt"),
        "parsear": parsear_archivo_etoro_o_csv,
    },
    "hapi": {
        "nombre": "Hapi",
        "instrucciones": INSTRUCCIONES_HAPI,
        "extensiones": ("*.csv", "*.tsv", "*.txt"),
        "parsear": parsear_archivo_etoro_o_csv,
    },
}


def parsear_archivo_broker(
    ruta_archivo: str, broker: str, agrupar_por_ticker: bool = False
) -> List[Dict[str, object]]:
    """Analiza un archivo de exportación del broker indicado.

    Devuelve la lista de posiciones para importar (misma estructura que
    el importador de eToro). Lanza ValueError si el broker no existe.
    """
    config = BROKERS.get(broker)
    if config is None:
        raise ValueError(f"Broker no soportado: {broker}")
    parsear: Callable = config["parsear"]  # type: ignore[assignment]
    return parsear(ruta_archivo, agrupar_por_ticker=agrupar_por_ticker)
