"""Servicio de integración en tiempo real con Yahoo Finance mediante la librería yfinance.

Incluye:
- Detección rápida de conexión a internet (`hay_conexion_internet`) para no bloquear la interfaz
  ni contaminar el caché negativo de símbolos cuando el equipo está sin red (offline).
- Soporte para el formato oficial de divisas en Yahoo Finance: pares con USD usan el ticker corto
  '{CODIGO}=X' (ej. 'BGN=X', 'COP=X', 'EUR=X') además de 'USDCOP=X'.
- Excepción específica `ErrorSinConexionInternet` para distinguir fallos por falta de internet
  de símbolos inexistentes.
"""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import logging
import socket
import time
from typing import List, Optional, Set, Tuple

from app.modelo.cotizacion import Cotizacion

SIMBOLO_USD_COP = "USDCOP=X"

# Silenciar avisos HTTP 404 / Crumb / DNS internos de yfinance en la terminal
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)


class ErrorConsultaBursatil(Exception):
    """Se lanza cuando la consulta a Yahoo Finance falla o no devuelve datos válidos."""


class ErrorSinConexionInternet(ErrorConsultaBursatil):
    """Se lanza específicamente cuando no hay conexión a internet para consultar Yahoo Finance."""


def _es_error_de_red(error: Exception) -> bool:
    """Detecta si una excepción proviene de falta de conexión a internet o fallo DNS."""
    texto = str(error).lower()
    patrones_red = (
        "dns",
        "connection",
        "network",
        "resolve",
        "crumb",
        "timed out",
        "timeout",
        "unreachable",
        "offline",
        "name or service not known",
        "getaddrinfo failed",
        "nodename nor servname",
        "max retries exceeded",
        "newconnectionerror",
        "failed to establish a new connection",
    )
    return any(p in texto for p in patrones_red)


class ServicioBursatil:
    """Consulta el precio y tasas de cambio en tiempo real en Yahoo Finance con alta precisión."""

    def __init__(self, proveedor_yf=None):
        self._yf = proveedor_yf
        self._simbolos_no_disponibles: Set[str] = set()
        self._ultimo_chequeo_red: float = 0.0
        self._estado_red_reciente: bool = True
        self._forzar_sin_conexion: bool = False

    def hay_conexion_internet(self, usar_cache_breve: bool = False) -> bool:
        """Verifica de forma rápida (máx. 1.2s) si hay conexión a internet hacia Yahoo Finance.
        Si se inyectó un proveedor mock (`self._yf is not None`), devuelve True salvo que se
        fuerce modo offline en pruebas."""
        if self._forzar_sin_conexion:
            return False
        if self._yf is not None:
            return True

        ahora = time.monotonic()
        if usar_cache_breve and (ahora - self._ultimo_chequeo_red) < 2.5:
            return self._estado_red_reciente

        conectado = False
        # 1) Intento de conexión TCP rápida a DNS públicos (Cloudflare / Google) sin coste DNS
        for host, puerto in (("1.1.1.1", 53), ("8.8.8.8", 53)):
            try:
                with socket.create_connection((host, puerto), timeout=1.0):
                    conectado = True
                    break
            except OSError:
                continue

        # 2) Respaldo: resolución y conexión directa a query1.finance.yahoo.com
        if not conectado:
            try:
                with socket.create_connection(("query1.finance.yahoo.com", 443), timeout=1.2):
                    conectado = True
            except OSError:
                conectado = False

        if conectado and not self._estado_red_reciente:
            # Al recuperar internet, limpiamos cualquier símbolo bloqueado temporalmente
            self._simbolos_no_disponibles.clear()

        self._estado_red_reciente = conectado
        self._ultimo_chequeo_red = ahora
        return conectado

    def limpiar_cache_simbolos_no_disponibles(self) -> None:
        """Limpia la lista de símbolos marcados como no disponibles tras reconectar internet."""
        self._simbolos_no_disponibles.clear()

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
        """Obtiene el precio en tiempo real de forma rápida:
        1) fast_info['last_price']
        2) history(period='5d') que incluye el precio en vivo de la sesión actual como última fila.
        """
        if not self.hay_conexion_internet(usar_cache_breve=True):
            raise ErrorSinConexionInternet(
                "No tienes conexión a internet para actualizar precios desde Yahoo Finance."
            )

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
                    self._estado_red_reciente = True
                    return float(precio_vivo), date.today()
        except Exception as error:
            if _es_error_de_red(error) or not self.hay_conexion_internet(usar_cache_breve=False):
                raise ErrorSinConexionInternet(
                    "No tienes conexión a internet para actualizar precios desde Yahoo Finance."
                ) from error

        try:
            historial = ticker.history(period="5d")
        except Exception as error:
            if _es_error_de_red(error) or not self.hay_conexion_internet(usar_cache_breve=False):
                raise ErrorSinConexionInternet(
                    "No tienes conexión a internet para actualizar precios desde Yahoo Finance."
                ) from error
            self._simbolos_no_disponibles.add(simbolo_limpio)
            raise ErrorConsultaBursatil(
                f"No fue posible conectar con Yahoo Finance para '{simbolo_limpio}': {error}"
            ) from error

        if historial is None or historial.empty or "Close" not in historial:
            if not self.hay_conexion_internet(usar_cache_breve=False):
                raise ErrorSinConexionInternet(
                    "No tienes conexión a internet para actualizar precios desde Yahoo Finance."
                )
            self._simbolos_no_disponibles.add(simbolo_limpio)
            raise ErrorConsultaBursatil(
                f"Yahoo Finance no devolvió datos para '{simbolo_limpio}'."
            )

        precios = historial["Close"].dropna()
        if precios.empty:
            if not self.hay_conexion_internet(usar_cache_breve=False):
                raise ErrorSinConexionInternet(
                    "No tienes conexión a internet para actualizar precios desde Yahoo Finance."
                )
            self._simbolos_no_disponibles.add(simbolo_limpio)
            raise ErrorConsultaBursatil(
                f"No hay precios válidos disponibles para '{simbolo_limpio}'."
            )

        ultimo_valor = float(precios.iloc[-1])
        if ultimo_valor <= 0:
            self._simbolos_no_disponibles.add(simbolo_limpio)
            raise ErrorConsultaBursatil(
                f"El precio recibido para '{simbolo_limpio}' no es válido."
            )

        self._estado_red_reciente = True
        ultimo_indice = precios.index[-1]
        fecha_cot = ultimo_indice.date() if hasattr(ultimo_indice, "date") else date.today()
        return ultimo_valor, fecha_cot

    def consultar_precio_actual(
        self, simbolo: str, moneda_esperada: str = "USD", decimales: str = "0.01"
    ) -> Cotizacion:
        """Obtiene el precio en tiempo real para un símbolo (ej. 'USDCOP=X', 'BGN=X', 'VOO')."""
        if not isinstance(simbolo, str) or not simbolo.strip():
            raise ErrorConsultaBursatil("El símbolo bursátil es obligatorio.")
        simbolo_limpio = simbolo.strip().upper()

        if not self.hay_conexion_internet(usar_cache_breve=True):
            raise ErrorSinConexionInternet(
                "No tienes conexión a internet para actualizar precios desde Yahoo Finance."
            )

        if simbolo_limpio in self._simbolos_no_disponibles:
            raise ErrorConsultaBursatil(f"Símbolo '{simbolo_limpio}' no disponible en Yahoo Finance.")

        yf = self._obtener_modulo_yf()
        try:
            ticker = yf.Ticker(simbolo_limpio)
        except Exception as error:
            if _es_error_de_red(error) or not self.hay_conexion_internet(usar_cache_breve=False):
                raise ErrorSinConexionInternet(
                    "No tienes conexión a internet para actualizar precios desde Yahoo Finance."
                ) from error
            raise ErrorConsultaBursatil(
                f"No fue posible inicializar el símbolo '{simbolo_limpio}': {error}"
            ) from error

        valor_actual, fecha_cotizacion = self._extraer_precio_tiempo_real(
            ticker, simbolo_limpio
        )

        precio_decimal = Decimal(str(valor_actual)).quantize(
            Decimal(decimales), rounding=ROUND_HALF_UP
        )

        return Cotizacion(
            id=None,
            simbolo=simbolo_limpio,
            fecha=fecha_cotizacion,
            precio=precio_decimal,
            moneda=moneda_esperada.strip().upper(),
            fuente="Yahoo Finance (Tiempo real)",
        )

    def _consultar_unidades_por_usd(self, codigo_moneda: str) -> Tuple[Decimal, date]:
        """Devuelve cuántas unidades de `codigo_moneda` equivalen a 1 USD.
        En Yahoo Finance la convención estándar es `{CODIGO}=X` (ej. `BGN=X`, `COP=X`, `EUR=X`)
        o `USD{CODIGO}=X` (ej. `USDCOP=X`)."""
        cod = codigo_moneda.strip().upper()
        if cod == "USD":
            return Decimal("1.00000000"), date.today()

        if not self.hay_conexion_internet(usar_cache_breve=True):
            raise ErrorSinConexionInternet(
                "No tienes conexión a internet para actualizar tasas de cambio."
            )

        candidatos = [f"{cod}=X", f"USD{cod}=X"] if cod != "COP" else [f"USD{cod}=X", f"{cod}=X"]
        for ticker_sym in candidatos:
            try:
                cot = self.consultar_precio_actual(
                    ticker_sym, moneda_esperada=cod, decimales="0.00000001"
                )
                if cot.precio > Decimal("0"):
                    return cot.precio, cot.fecha
            except ErrorSinConexionInternet:
                raise
            except ErrorConsultaBursatil:
                continue

        # Último recurso: par inverso '{CODIGO}USD=X'
        try:
            cot_inv = self.consultar_precio_actual(
                f"{cod}USD=X", moneda_esperada="USD", decimales="0.00000001"
            )
            if cot_inv.precio > Decimal("0"):
                return (Decimal("1") / cot_inv.precio).quantize(
                    Decimal("0.00000001"), rounding=ROUND_HALF_UP
                ), cot_inv.fecha
        except ErrorSinConexionInternet:
            raise
        except ErrorConsultaBursatil:
            pass

        raise ErrorConsultaBursatil(
            f"Yahoo Finance no dispone de cotización para la divisa '{cod}'."
        )

    def consultar_tasa_cambio(self, moneda_origen: str, moneda_destino: str) -> Cotizacion:
        """Calcula la tasa en tiempo real entre cualquier par de divisas del mundo con 8 decimales.
        Usa la relación oficial con USD (`{MONEDA}=X` / `USD{MONEDA}=X`) para evitar consultar
        combinaciones cruzadas inexistentes como `BGNCOP=X`."""
        origen = moneda_origen.strip().upper()
        destino = moneda_destino.strip().upper()
        simbolo_canonico = f"{origen}{destino}=X"

        if origen == destino:
            return Cotizacion(
                id=None,
                simbolo=simbolo_canonico,
                fecha=date.today(),
                precio=Decimal("1.00000000"),
                moneda=destino,
                fuente="Paridad 1:1",
            )

        if not self.hay_conexion_internet(usar_cache_breve=False):
            raise ErrorSinConexionInternet(
                "No tienes conexión a internet para actualizar las tasas de cambio."
            )

        unidades_origen_por_usd, fecha_orig = self._consultar_unidades_por_usd(origen)
        unidades_destino_por_usd, fecha_dest = self._consultar_unidades_por_usd(destino)

        tasa = (unidades_destino_por_usd / unidades_origen_por_usd).quantize(
            Decimal("0.00000001"), rounding=ROUND_HALF_UP
        )
        fecha_ref = fecha_dest if destino != "USD" else fecha_orig

        return Cotizacion(
            id=None,
            simbolo=simbolo_canonico,
            fecha=fecha_ref,
            precio=tasa,
            moneda=destino,
            fuente="Yahoo Finance (Tiempo real)",
        )

    def consultar_tasa_usd_cop(self) -> Cotizacion:
        """Obtiene la tasa en tiempo real USD -> COP ('USDCOP=X' en Yahoo Finance)."""
        return self.consultar_precio_actual(SIMBOLO_USD_COP, moneda_esperada="COP")

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
        if not self.hay_conexion_internet(usar_cache_breve=False):
            raise ErrorSinConexionInternet(
                "No tienes conexión a internet para consultar el historial bursátil."
            )
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
            if _es_error_de_red(error) or not self.hay_conexion_internet(usar_cache_breve=False):
                raise ErrorSinConexionInternet(
                    "No tienes conexión a internet para consultar el historial bursátil."
                ) from error
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
