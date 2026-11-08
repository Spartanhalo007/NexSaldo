"""Modelo de dominio para Inversiones Bursátiles y Criptomonedas (Acciones, ETFs, Cripto y Fondos) en NexSaldo."""

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Tuple


# Mapa de códigos de criptomonedas en eToro / buscador -> Ticker oficial en Yahoo Finance (`{CODIGO}-USD`)
# Importante: En Yahoo Finance, 'BTC' sin '-USD' es el ETF Grayscale (~$40, lo que causaba un falso -99%)
# y 'SOL' sin '-USD' es Emeren Group (~$2). Usar 'BTC-USD', 'SOL-USD', 'ETH-USD', etc. obtiene el precio real.
MAPA_CRIPTO_A_YAHOO: Dict[str, Tuple[str, str]] = {
    "BTC": ("BTC-USD", "Bitcoin (BTC)"),
    "BITCOIN": ("BTC-USD", "Bitcoin (BTC)"),
    "XBT": ("BTC-USD", "Bitcoin (BTC)"),
    "ETH": ("ETH-USD", "Ethereum (ETH)"),
    "ETHEREUM": ("ETH-USD", "Ethereum (ETH)"),
    "SOL": ("SOL-USD", "Solana (SOL)"),
    "SOLANA": ("SOL-USD", "Solana (SOL)"),
    "XRP": ("XRP-USD", "XRP / Ripple (XRP)"),
    "RIPPLE": ("XRP-USD", "XRP / Ripple (XRP)"),
    "BNB": ("BNB-USD", "BNB / Binance Coin (BNB)"),
    "BINANCE": ("BNB-USD", "BNB / Binance Coin (BNB)"),
    "ADA": ("ADA-USD", "Cardano (ADA)"),
    "CARDANO": ("ADA-USD", "Cardano (ADA)"),
    "DOGE": ("DOGE-USD", "Dogecoin (DOGE)"),
    "DOGECOIN": ("DOGE-USD", "Dogecoin (DOGE)"),
    "AVAX": ("AVAX-USD", "Avalanche (AVAX)"),
    "AVALANCHE": ("AVAX-USD", "Avalanche (AVAX)"),
    "DOT": ("DOT-USD", "Polkadot (DOT)"),
    "POLKADOT": ("DOT-USD", "Polkadot (DOT)"),
    "LINK": ("LINK-USD", "Chainlink (LINK)"),
    "CHAINLINK": ("LINK-USD", "Chainlink (LINK)"),
    "LTC": ("LTC-USD", "Litecoin (LTC)"),
    "LITECOIN": ("LTC-USD", "Litecoin (LTC)"),
    "BCH": ("BCH-USD", "Bitcoin Cash (BCH)"),
    "SHIB": ("SHIB-USD", "Shiba Inu (SHIB)"),
    "UNI": ("UNI-USD", "Uniswap (UNI)"),
    "UNISWAP": ("UNI-USD", "Uniswap (UNI)"),
    "ATOM": ("ATOM-USD", "Cosmos (ATOM)"),
    "COSMOS": ("ATOM-USD", "Cosmos (ATOM)"),
    "XLM": ("XLM-USD", "Stellar (XLM)"),
    "STELLAR": ("XLM-USD", "Stellar (XLM)"),
    "NEAR": ("NEAR-USD", "NEAR Protocol (NEAR)"),
    "APT": ("APT-USD", "Aptos (APT)"),
    "APTOS": ("APT-USD", "Aptos (APT)"),
    "ARB": ("ARB-USD", "Arbitrum (ARB)"),
    "ARBITRUM": ("ARB-USD", "Arbitrum (ARB)"),
    "OP": ("OP-USD", "Optimism (OP)"),
    "OPTIMISM": ("OP-USD", "Optimism (OP)"),
    "SUI": ("SUI-USD", "Sui (SUI)"),
    "FIL": ("FIL-USD", "Filecoin (FIL)"),
    "FILECOIN": ("FIL-USD", "Filecoin (FIL)"),
    "ICP": ("ICP-USD", "Internet Computer (ICP)"),
    "POL": ("POL-USD", "Polygon (POL / MATIC)"),
    "MATIC": ("POL-USD", "Polygon (POL / MATIC)"),
    "POLYGON": ("POL-USD", "Polygon (POL / MATIC)"),
    "AAVE": ("AAVE-USD", "Aave (AAVE)"),
    "INJ": ("INJ-USD", "Injective (INJ)"),
    "RNDR": ("RNDR-USD", "Render (RNDR)"),
    "RENDER": ("RNDR-USD", "Render (RNDR)"),
    "FET": ("FET-USD", "Artificial Superintelligence (FET)"),
    "PEPE": ("PEPE-USD", "Pepe (PEPE)"),
    "TRX": ("TRX-USD", "TRON (TRX)"),
    "TRON": ("TRX-USD", "TRON (TRX)"),
    "ETC": ("ETC-USD", "Ethereum Classic (ETC)"),
    "HBAR": ("HBAR-USD", "Hedera (HBAR)"),
    "HEDERA": ("HBAR-USD", "Hedera (HBAR)"),
    "TON": ("TON11419-USD", "Toncoin (TON)"),
    "TONCOIN": ("TON11419-USD", "Toncoin (TON)"),
    "ALGO": ("ALGO-USD", "Algorand (ALGO)"),
    "ALGORAND": ("ALGO-USD", "Algorand (ALGO)"),
    "MANA": ("MANA-USD", "Decentraland (MANA)"),
    "SAND": ("SAND-USD", "The Sandbox (SAND)"),
    "AXS": ("AXS-USD", "Axie Infinity (AXS)"),
    "EOS": ("EOS-USD", "EOS (EOS)"),
    "XTZ": ("XTZ-USD", "Tezos (XTZ)"),
    "NEO": ("NEO-USD", "NEO (NEO)"),
    "GALA": ("GALA-USD", "Gala (GALA)"),
    "APE": ("APE-USD", "ApeCoin (APE)"),
    "LDO": ("LDO-USD", "Lido DAO (LDO)"),
    "QNT": ("QNT-USD", "Quant (QNT)"),
    "GRT": ("GRT-USD", "The Graph (GRT)"),
    "FLR": ("FLR-USD", "Flare (FLR)"),
    "IMX": ("IMX-USD", "Immutable (IMX)"),
    "CRO": ("CRO-USD", "Cronos (CRO)"),
    "VET": ("VET-USD", "VeChain (VET)"),
    "MKR": ("MKR-USD", "Maker (MKR)"),
    "RUNE": ("RUNE-USD", "THORChain (RUNE)"),
    "KAS": ("KAS-USD", "Kaspa (KAS)"),
    "BONK": ("BONK-USD", "Bonk (BONK)"),
    "WIF": ("WIF-USD", "dogwifhat (WIF)"),
    "JASMY": ("JASMY-USD", "JasmyCoin (JASMY)"),
    "PENDLE": ("PENDLE-USD", "Pendle (PENDLE)"),
}


def normalizar_simbolo_yahoo(simbolo: str, es_cripto: bool = False) -> str:
    """Convierte códigos cortos de criptomonedas (ej. 'BTC', 'SOL', 'ETH') a su ticker oficial
    en Yahoo Finance ('BTC-USD', 'SOL-USD', 'ETH-USD')."""
    limpio = (simbolo or "").strip().upper()
    if not limpio:
        return ""
    if "/" in limpio:
        partes = limpio.split("/", 1)
        base = partes[0].strip()
        cot = partes[1].strip() or "USD"
        if base in MAPA_CRIPTO_A_YAHOO:
            return MAPA_CRIPTO_A_YAHOO[base][0]
        if es_cripto:
            return f"{base}-{cot}"
        limpio = base
    if limpio in MAPA_CRIPTO_A_YAHOO:
        return MAPA_CRIPTO_A_YAHOO[limpio][0]
    if es_cripto and not limpio.endswith("-USD") and "=" not in limpio and "-" not in limpio:
        return f"{limpio}-USD"
    return limpio


# Catálogo curado de Criptomonedas, Acciones y ETFs populares en Yahoo Finance.
# Los primeros 8 activos aparecen como botones de acceso rápido bajo la barra de búsqueda.
CATALOGO_ACTIVOS_BURSATILES: List[Dict[str, str]] = [
    # --- Acceso rápido inicial (Top 8: Cripto + ETFs + Acciones clave) ---
    {
        "simbolo": "BTC-USD",
        "nombre": "Bitcoin (BTC)",
        "tipo": "Criptomoneda · Crypto",
        "moneda": "USD",
        "bolsa": "Crypto Global",
    },
    {
        "simbolo": "SOL-USD",
        "nombre": "Solana (SOL)",
        "tipo": "Criptomoneda · Crypto",
        "moneda": "USD",
        "bolsa": "Crypto Global",
    },
    {
        "simbolo": "ETH-USD",
        "nombre": "Ethereum (ETH)",
        "tipo": "Criptomoneda · Crypto",
        "moneda": "USD",
        "bolsa": "Crypto Global",
    },
    {
        "simbolo": "TTWO",
        "nombre": "Take-Two Interactive Software, Inc.",
        "tipo": "Acción · Videojuegos",
        "moneda": "USD",
        "bolsa": "NASDAQ",
    },
    {
        "simbolo": "VOO",
        "nombre": "Vanguard S&P 500 ETF",
        "tipo": "ETF · S&P 500",
        "moneda": "USD",
        "bolsa": "NYSE Arca",
    },
    {
        "simbolo": "QQQ",
        "nombre": "Invesco QQQ Trust (Nasdaq-100)",
        "tipo": "ETF · Nasdaq 100",
        "moneda": "USD",
        "bolsa": "NASDAQ",
    },
    {
        "simbolo": "NVDA",
        "nombre": "NVIDIA Corporation",
        "tipo": "Acción · Semiconductores",
        "moneda": "USD",
        "bolsa": "NASDAQ",
    },
    {
        "simbolo": "AAPL",
        "nombre": "Apple Inc.",
        "tipo": "Acción · Tecnología",
        "moneda": "USD",
        "bolsa": "NASDAQ",
    },
    # --- Otras Criptomonedas Populares ---
    {
        "simbolo": "XRP-USD",
        "nombre": "XRP / Ripple (XRP)",
        "tipo": "Criptomoneda · Crypto",
        "moneda": "USD",
        "bolsa": "Crypto Global",
    },
    {
        "simbolo": "BNB-USD",
        "nombre": "BNB / Binance Coin (BNB)",
        "tipo": "Criptomoneda · Crypto",
        "moneda": "USD",
        "bolsa": "Crypto Global",
    },
    {
        "simbolo": "ADA-USD",
        "nombre": "Cardano (ADA)",
        "tipo": "Criptomoneda · Crypto",
        "moneda": "USD",
        "bolsa": "Crypto Global",
    },
    {
        "simbolo": "DOGE-USD",
        "nombre": "Dogecoin (DOGE)",
        "tipo": "Criptomoneda · Crypto",
        "moneda": "USD",
        "bolsa": "Crypto Global",
    },
    {
        "simbolo": "AVAX-USD",
        "nombre": "Avalanche (AVAX)",
        "tipo": "Criptomoneda · Crypto",
        "moneda": "USD",
        "bolsa": "Crypto Global",
    },
    {
        "simbolo": "DOT-USD",
        "nombre": "Polkadot (DOT)",
        "tipo": "Criptomoneda · Crypto",
        "moneda": "USD",
        "bolsa": "Crypto Global",
    },
    {
        "simbolo": "LINK-USD",
        "nombre": "Chainlink (LINK)",
        "tipo": "Criptomoneda · Crypto",
        "moneda": "USD",
        "bolsa": "Crypto Global",
    },
    {
        "simbolo": "LTC-USD",
        "nombre": "Litecoin (LTC)",
        "tipo": "Criptomoneda · Crypto",
        "moneda": "USD",
        "bolsa": "Crypto Global",
    },
    {
        "simbolo": "SUI-USD",
        "nombre": "Sui (SUI)",
        "tipo": "Criptomoneda · Crypto",
        "moneda": "USD",
        "bolsa": "Crypto Global",
    },
    {
        "simbolo": "SHIB-USD",
        "nombre": "Shiba Inu (SHIB)",
        "tipo": "Criptomoneda · Crypto",
        "moneda": "USD",
        "bolsa": "Crypto Global",
    },
    {
        "simbolo": "PEPE-USD",
        "nombre": "Pepe (PEPE)",
        "tipo": "Criptomoneda · Crypto",
        "moneda": "USD",
        "bolsa": "Crypto Global",
    },
    {
        "simbolo": "UNI-USD",
        "nombre": "Uniswap (UNI)",
        "tipo": "Criptomoneda · Crypto",
        "moneda": "USD",
        "bolsa": "Crypto Global",
    },
    {
        "simbolo": "NEAR-USD",
        "nombre": "NEAR Protocol (NEAR)",
        "tipo": "Criptomoneda · Crypto",
        "moneda": "USD",
        "bolsa": "Crypto Global",
    },
    {
        "simbolo": "APT-USD",
        "nombre": "Aptos (APT)",
        "tipo": "Criptomoneda · Crypto",
        "moneda": "USD",
        "bolsa": "Crypto Global",
    },
    {
        "simbolo": "POL-USD",
        "nombre": "Polygon (POL / MATIC)",
        "tipo": "Criptomoneda · Crypto",
        "moneda": "USD",
        "bolsa": "Crypto Global",
    },
    # --- Otros ETFs Principales ---
    {
        "simbolo": "SPY",
        "nombre": "SPDR S&P 500 ETF Trust",
        "tipo": "ETF · S&P 500",
        "moneda": "USD",
        "bolsa": "NYSE Arca",
    },
    {
        "simbolo": "VTI",
        "nombre": "Vanguard Total Stock Market ETF",
        "tipo": "ETF · EE. UU. Total",
        "moneda": "USD",
        "bolsa": "NYSE Arca",
    },
    {
        "simbolo": "SCHD",
        "nombre": "Schwab U.S. Dividend Equity ETF",
        "tipo": "ETF · Dividendos",
        "moneda": "USD",
        "bolsa": "NYSE Arca",
    },
    {
        "simbolo": "VXUS",
        "nombre": "Vanguard Total International Stock ETF",
        "tipo": "ETF · Internacional",
        "moneda": "USD",
        "bolsa": "NASDAQ",
    },
    {
        "simbolo": "GLD",
        "nombre": "SPDR Gold Shares (Oro)",
        "tipo": "ETF · Materias Primas",
        "moneda": "USD",
        "bolsa": "NYSE Arca",
    },
    {
        "simbolo": "DIA",
        "nombre": "SPDR Dow Jones Industrial Average ETF",
        "tipo": "ETF · Dow Jones",
        "moneda": "USD",
        "bolsa": "NYSE Arca",
    },
    {
        "simbolo": "IWM",
        "nombre": "iShares Russell 2000 ETF",
        "tipo": "ETF · Small Caps",
        "moneda": "USD",
        "bolsa": "NYSE Arca",
    },
    # --- Otras Acciones Principales ---
    {
        "simbolo": "MSFT",
        "nombre": "Microsoft Corporation",
        "tipo": "Acción · Tecnología",
        "moneda": "USD",
        "bolsa": "NASDAQ",
    },
    {
        "simbolo": "GOOGL",
        "nombre": "Alphabet Inc. (Google)",
        "tipo": "Acción · Tecnología",
        "moneda": "USD",
        "bolsa": "NASDAQ",
    },
    {
        "simbolo": "AMZN",
        "nombre": "Amazon.com, Inc.",
        "tipo": "Acción · Comercio y Nube",
        "moneda": "USD",
        "bolsa": "NASDAQ",
    },
    {
        "simbolo": "META",
        "nombre": "Meta Platforms, Inc.",
        "tipo": "Acción · Tecnología",
        "moneda": "USD",
        "bolsa": "NASDAQ",
    },
    {
        "simbolo": "TSLA",
        "nombre": "Tesla, Inc.",
        "tipo": "Acción · Automotriz / Energía",
        "moneda": "USD",
        "bolsa": "NASDAQ",
    },
    {
        "simbolo": "EA",
        "nombre": "Electronic Arts Inc.",
        "tipo": "Acción · Videojuegos",
        "moneda": "USD",
        "bolsa": "NASDAQ",
    },
    {
        "simbolo": "SONY",
        "nombre": "Sony Group Corporation",
        "tipo": "Acción · Entretenimiento y Gaming",
        "moneda": "USD",
        "bolsa": "NYSE",
    },
    {
        "simbolo": "NTDOY",
        "nombre": "Nintendo Co., Ltd. (ADR)",
        "tipo": "ADR · Videojuegos",
        "moneda": "USD",
        "bolsa": "OTC",
    },
    {
        "simbolo": "AMD",
        "nombre": "Advanced Micro Devices, Inc.",
        "tipo": "Acción · Semiconductores",
        "moneda": "USD",
        "bolsa": "NASDAQ",
    },
    {
        "simbolo": "NFLX",
        "nombre": "Netflix, Inc.",
        "tipo": "Acción · Streaming",
        "moneda": "USD",
        "bolsa": "NASDAQ",
    },
    {
        "simbolo": "SPOT",
        "nombre": "Spotify Technology S.A.",
        "tipo": "Acción · Audio y Streaming",
        "moneda": "USD",
        "bolsa": "NYSE",
    },
    {
        "simbolo": "DIS",
        "nombre": "The Walt Disney Company",
        "tipo": "Acción · Entretenimiento",
        "moneda": "USD",
        "bolsa": "NYSE",
    },
    {
        "simbolo": "PLTR",
        "nombre": "Palantir Technologies Inc.",
        "tipo": "Acción · Inteligencia Artificial",
        "moneda": "USD",
        "bolsa": "NASDAQ",
    },
    {
        "simbolo": "UBER",
        "nombre": "Uber Technologies, Inc.",
        "tipo": "Acción · Movilidad",
        "moneda": "USD",
        "bolsa": "NYSE",
    },
    {
        "simbolo": "BRK-B",
        "nombre": "Berkshire Hathaway Inc. (Clase B)",
        "tipo": "Acción · Holding Financiero",
        "moneda": "USD",
        "bolsa": "NYSE",
    },
    {
        "simbolo": "JPM",
        "nombre": "JPMorgan Chase & Co.",
        "tipo": "Acción · Banca Global",
        "moneda": "USD",
        "bolsa": "NYSE",
    },
    {
        "simbolo": "V",
        "nombre": "Visa Inc.",
        "tipo": "Acción · Pagos Globales",
        "moneda": "USD",
        "bolsa": "NYSE",
    },
    {
        "simbolo": "NU",
        "nombre": "Nu Holdings Ltd. (Nubank)",
        "tipo": "Acción · Fintech LatAm",
        "moneda": "USD",
        "bolsa": "NYSE",
    },
    {
        "simbolo": "MELI",
        "nombre": "MercadoLibre, Inc.",
        "tipo": "Acción · E-Commerce LatAm",
        "moneda": "USD",
        "bolsa": "NASDAQ",
    },
    {
        "simbolo": "CIB",
        "nombre": "Bancolombia S.A. (ADR)",
        "tipo": "ADR · Banca Colombia",
        "moneda": "USD",
        "bolsa": "NYSE",
    },
    {
        "simbolo": "EC",
        "nombre": "Ecopetrol S.A. (ADR)",
        "tipo": "ADR · Energía Colombia",
        "moneda": "USD",
        "bolsa": "NYSE",
    },
    {
        "simbolo": "KO",
        "nombre": "The Coca-Cola Company",
        "tipo": "Acción · Consumo Masivo",
        "moneda": "USD",
        "bolsa": "NYSE",
    },
]


@dataclass(frozen=True)
class Inversion:
    """Representa una posición de inversión bursátil o de criptomoneda del usuario."""

    id: Optional[int]
    simbolo: str
    nombre: str
    monto_invertido: Decimal
    moneda: str
    precio_compra: Decimal
    cantidad_titulos: Decimal
    fecha_compra: date
    cuenta_id: Optional[int] = None
    notas: Optional[str] = None

    def con_id(self, nuevo_id: int) -> "Inversion":
        return replace(self, id=nuevo_id)


@dataclass(frozen=True)
class ValoracionInversion:
    """Resultado dinámico en tiempo real de una posición de inversión."""

    inversion: Inversion
    precio_actual: Decimal
    valor_actual: Decimal
    ganancia_perdida: Decimal
    rendimiento_porcentaje: Decimal
    moneda_visualizacion: str
    monto_invertido_convertido: Decimal
    valor_actual_convertido: Decimal
    ganancia_perdida_convertida: Decimal
    desde_cache: bool = False
    fecha_cotizacion: Optional[date] = None

    @property
    def en_ganancia(self) -> bool:
        return self.ganancia_perdida >= Decimal("0")
