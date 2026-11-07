"""Modelo de dominio para Inversiones Bursátiles (Acciones, ETFs y Fondos) en NexSaldo."""

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Tuple


# Catálogo curado de ETFs e instrumentos bursátiles populares en Yahoo Finance
# (el buscador también permite consultar cualquier otro ticker de Yahoo Finance en vivo)
CATALOGO_ACTIVOS_BURSATILES: List[Dict[str, str]] = [
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
        "simbolo": "AAPL",
        "nombre": "Apple Inc.",
        "tipo": "Acción · Tecnología",
        "moneda": "USD",
        "bolsa": "NASDAQ",
    },
    {
        "simbolo": "MSFT",
        "nombre": "Microsoft Corporation",
        "tipo": "Acción · Tecnología",
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
        "simbolo": "BRK-B",
        "nombre": "Berkshire Hathaway Inc. (Clase B)",
        "tipo": "Acción · Holding Financiero",
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
    """Representa una posición de inversión bursátil del usuario."""

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
