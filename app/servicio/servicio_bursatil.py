"""Servicio de integración en tiempo real con Yahoo Finance mediante la librería yfinance."""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Tuple

from app.modelo.cotizacion import Cotizacion

SIMBOLO_USD_COP = "USDCOP=X"


class ErrorConsultaBursatil(Exception):
    """Se lanza cuando la consulta a Yahoo Finance falla o no devuelve datos válidos."""


class ServicioBursatil:
    """Consulta el precio en tiempo real (o el más reciente del mercado) en Yahoo Finance."""

    def __init__(self, proveedor_yf=None):
        self._yf = proveedor_yf

    def _obtener_modulo_yf(self):
        if self._yf is not None:
            return self._yf
        try:
            import yfinance as yf  # type: ignore
            return yf
        except ImportError as error:
            raise ErrorConsultaBursatil(
                "La librería 'yfinance' no está instalada. Ejecuta: .venv\\Scripts\\pip install yfinance"
            ) from error

    def _extraer_precio_tiempo_real(self, ticker, simbolo_limpio: str) -> Tuple[float, date]:
        """Obtiene el precio en tiempo real en este orden:
        1) fast_info['last_price'] (cotización en vivo directa del ticker)
        2) serie intradía de 1 minuto (period='1d', interval='1m')
        3) serie reciente de respaldo (period='5d') cuando el mercado no tiene sesión activa
        """
        # 1. Cotización directa en tiempo real via fast_info
        try:
            fast_info = getattr(ticker, "fast_info", None)
            if fast_info is not None:
                precio_vivo = None
                if hasattr(fast_info, "get"):
                    precio_vivo = fast_info.get("last_price")
                if precio_vivo is None and hasattr(fast_info, "last_price"):
                    precio_vivo = getattr(fast_info, "last_price")
                if precio_vivo is None:
                    try:
                        precio_vivo = fast_info["last_price"]
                    except Exception:
                        precio_vivo = None
                if precio_vivo is not None and float(precio_vivo) > 0:
                    return float(precio_vivo), date.today()
        except Exception:
            pass

        # 2. Serie intradía de 1 minuto (sesión en vivo)
        try:
            intradia = ticker.history(period="1d", interval="1m")
            if intradia is not None and not intradia.empty and "Close" in intradia:
                precios_min = intradia["Close"].dropna()
                if not precios_min.empty:
                    valor_min = float(precios_min.iloc[-1])
                    if valor_min > 0:
                        idx_min = precios_min.index[-1]
                        fecha_min = idx_min.date() if hasattr(idx_min, "date") else date.today()
                        return valor_min, fecha_min
        except Exception:
            pass

        # 3. Respaldo cuando la bolsa está fuera de horario
        try:
            historial = ticker.history(period="5d")
        except Exception as error:
            raise ErrorConsultaBursatil(
                f"No fue posible conectar con Yahoo Finance para '{simbolo_limpio}': {error}"
            ) from error

        if historial is None or historial.empty or "Close" not in historial:
            raise ErrorConsultaBursatil(
                f"Yahoo Finance no devolvió datos para '{simbolo_limpio}'."
            )

        precios = historial["Close"].dropna()
        if precios.empty:
            raise ErrorConsultaBursatil(
                f"No hay precios válidos disponibles para '{simbolo_limpio}'."
            )

        ultimo_valor = float(precios.iloc[-1])
        if ultimo_valor <= 0:
            raise ErrorConsultaBursatil(
                f"El precio recibido para '{simbolo_limpio}' no es válido."
            )

        ultimo_indice = precios.index[-1]
        fecha_cot = ultimo_indice.date() if hasattr(ultimo_indice, "date") else date.today()
        return ultimo_valor, fecha_cot

    def consultar_precio_actual(
        self, simbolo: str, moneda_esperada: str = "USD"
    ) -> Cotizacion:
        """Obtiene el precio en tiempo real para un símbolo (ej. 'USDCOP=X', 'VOO', 'AAPL')."""
        if not isinstance(simbolo, str) or not simbolo.strip():
            raise ErrorConsultaBursatil("El símbolo bursátil es obligatorio.")
        simbolo_limpio = simbolo.strip().upper()
        yf = self._obtener_modulo_yf()

        try:
            ticker = yf.Ticker(simbolo_limpio)
        except Exception as error:
            raise ErrorConsultaBursatil(
                f"No fue posible inicializar el símbolo '{simbolo_limpio}': {error}"
            ) from error

        valor_actual, fecha_cotizacion = self._extraer_precio_tiempo_real(
            ticker, simbolo_limpio
        )

        precio_decimal = Decimal(str(valor_actual)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        return Cotizacion(
            id=None,
            simbolo=simbolo_limpio,
            fecha=fecha_cotizacion,
            precio=precio_decimal,
            moneda=moneda_esperada.strip().upper(),
            fuente="Yahoo Finance (Tiempo real)",
        )

    def consultar_historial(
        self,
        simbolo: str,
        desde: Optional[date] = None,
        hasta: Optional[date] = None,
        moneda_esperada: str = "USD",
    ) -> List[Cotizacion]:
        """Consulta la serie histórica de precios entre dos fechas para gráficas de evolución."""
        if not isinstance(simbolo, str) or not simbolo.strip():
            raise ErrorConsultaBursatil("El símbolo bursátil es obligatorio.")
        simbolo_limpio = simbolo.strip().upper()
        yf = self._obtener_modulo_yf()

        try:
            ticker = yf.Ticker(simbolo_limpio)
            if desde and hasta:
                historial = ticker.history(
                    start=desde.isoformat(), end=hasta.isoformat()
                )
            else:
                historial = ticker.history(period="1mo")
        except Exception as error:
            raise ErrorConsultaBursatil(
                f"Error al consultar el historial de '{simbolo_limpio}': {error}"
            ) from error

        if historial is None or historial.empty or "Close" not in historial:
            raise ErrorConsultaBursatil(
                f"Sin datos para '{simbolo_limpio}' en el rango solicitado."
            )

        resultado: List[Cotizacion] = []
        for idx, fila in historial.iterrows():
            valor_item = fila.get("Close")
            if valor_item is None or valor_item != valor_item:
                continue
            precio = Decimal(str(float(valor_item))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if precio <= Decimal("0"):
                continue
            fecha_item = idx.date() if hasattr(idx, "date") else date.today()
            resultado.append(
                Cotizacion(
                    id=None,
                    simbolo=simbolo_limpio,
                    fecha=fecha_item,
                    precio=precio,
                    moneda=moneda_esperada.strip().upper(),
                    fuente="Yahoo Finance",
                )
            )
        if not resultado:
            raise ErrorConsultaBursatil(
                f"No se encontraron cotizaciones válidas para '{simbolo_limpio}'."
            )
        return resultado

    def consultar_tasa_usd_cop(self) -> Cotizacion:
        """Obtiene la tasa en tiempo real USD -> COP ('USDCOP=X' en Yahoo Finance)."""
        return self.consultar_precio_actual(SIMBOLO_USD_COP, moneda_esperada="COP")
