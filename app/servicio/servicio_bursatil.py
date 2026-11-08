"""Servicio de integración en tiempo real con Yahoo Finance mediante la librería yfinance.

Incluye:
- Detección rápida de conexión a internet por puerto HTTPS 443 (`hay_conexion_internet`) para no fallar
  en redes donde el puerto TCP 53 está bloqueado.
- Búsqueda híbrida de acciones, ETFs y Criptomonedas (Bitcoin `BTC-USD`, Solana `SOL-USD`, Ethereum `ETH-USD`, etc.):
  combina respuesta instantánea local con búsqueda en vivo en Yahoo Finance (`yf.Search`).
- Consulta de precios históricos ajustados por splits en una fecha específica (`consultar_precio_historico_en_fecha`)
  para garantizar que las posiciones importadas de eToro o registradas en fechas pasadas usen el precio real de apertura.
- Soporte para el formato oficial de divisas en Yahoo Finance (`{CODIGO}=X` / `USD{CODIGO}=X`).
"""

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import logging
import socket
import time
from typing import Dict, List, Optional, Set, Tuple

from app.modelo.cotizacion import Cotizacion
from app.modelo.inversion import (
    CATALOGO_ACTIVOS_BURSATILES,
    MAPA_CRIPTO_A_YAHOO,
    normalizar_simbolo_yahoo,
)

SIMBOLO_USD_COP = "USDCOP=X"

# Silenciar avisos HTTP 404 / Crumb / DNS internos de yfinance en la terminal
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)

PARAMETROS_MARCO_TIEMPO: Dict[str, Tuple[str, str]] = {
    "1D": ("5d", "15m"),
    "1W": ("5d", "1h"),
    "1M": ("1mo", "1d"),
    "1Y": ("1y", "1wk"),
}


class ErrorConsultaBursatil(Exception):
    """Se lanza cuando la consulta a Yahoo Finance falla o el ticker no existe."""


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
    """Consulta el precio, búsqueda de tickers, series históricas y tasas de cambio en Yahoo Finance."""

    def __init__(self, proveedor_yf=None):
        self._yf = proveedor_yf
        self._simbolos_no_disponibles: Set[str] = set()
        self._cache_busqueda_remota: Dict[str, List[Dict[str, str]]] = {}
        self._cache_historico_fecha: Dict[Tuple[str, str], Optional[Decimal]] = {}
        self._cache_series_temporales: Dict[Tuple[str, str], List[Tuple[str, Decimal]]] = {}
        self._ultimo_chequeo_red: float = 0.0
        self._estado_red_reciente: bool = True
        self._forzar_sin_conexion: bool = False

    def hay_conexion_internet(self, usar_cache_breve: bool = False) -> bool:
        """Verifica de forma rápida por HTTPS (puerto 443) si hay conexión a internet."""
        if self._forzar_sin_conexion:
            return False
        if self._yf is not None:
            return True

        ahora = time.monotonic()
        if usar_cache_breve and (ahora - self._ultimo_chequeo_red) < 15.0:
            return self._estado_red_reciente

        conectado = False
        # Usar puerto 443 (HTTPS) que nunca es bloqueado por routers o firewalls domésticos
        for host, puerto in (
            ("query1.finance.yahoo.com", 443),
            ("1.1.1.1", 443),
            ("8.8.8.8", 443),
        ):
            try:
                with socket.create_connection((host, puerto), timeout=1.2):
                    conectado = True
                    break
            except OSError:
                continue

        if conectado and not self._estado_red_reciente:
            self._simbolos_no_disponibles.clear()

        self._estado_red_reciente = conectado
        self._ultimo_chequeo_red = ahora
        return conectado

    def limpiar_cache_simbolos_no_disponibles(self) -> None:
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

    def buscar_activos_bursatiles(
        self, consulta: str = "", incluir_remoto: bool = False
    ) -> List[Dict[str, str]]:
        """Busca acciones, ETFs y criptomonedas (Bitcoin, Solana, Ethereum, etc.):
        1) Filtra instantáneamente en el catálogo local curado (incluye BTC-USD, SOL-USD, ETH-USD, TTWO, VOO, QQQ...).
        2) Si `incluir_remoto=True` y hay internet, consulta `yf.Search` en Yahoo Finance."""
        termino = (consulta or "").strip()
        if not termino:
            return list(CATALOGO_ACTIVOS_BURSATILES[:12])

        termino_low = termino.lower()
        termino_up = termino.upper()
        simbolo_cripto_norm = normalizar_simbolo_yahoo(termino_up)

        coincidencias: List[Dict[str, str]] = []
        simbolos_vistos: Set[str] = set()

        # 1. Si coincide exactamente con un símbolo del catálogo o con su alias cripto (ej. 'BTC' -> 'BTC-USD', 'SOL' -> 'SOL-USD')
        for item in CATALOGO_ACTIVOS_BURSATILES:
            sim_item = item["simbolo"].upper()
            if sim_item in (termino_up, simbolo_cripto_norm):
                coincidencias.append(dict(item))
                simbolos_vistos.add(sim_item)

        # 2. Si está en MAPA_CRIPTO_A_YAHOO y aún no estaba en el catálogo principal
        if termino_up in MAPA_CRIPTO_A_YAHOO:
            sim_c, nom_c = MAPA_CRIPTO_A_YAHOO[termino_up]
            if sim_c not in simbolos_vistos:
                coincidencias.append(
                    {
                        "simbolo": sim_c,
                        "nombre": nom_c,
                        "tipo": "Criptomoneda · Crypto",
                        "moneda": "USD",
                        "bolsa": "Crypto Global",
                    }
                )
                simbolos_vistos.add(sim_c)

        # 3. Coincidencias parciales por símbolo, nombre o tipo en el catálogo local
        for item in CATALOGO_ACTIVOS_BURSATILES:
            sim_item = item["simbolo"].upper()
            if sim_item in simbolos_vistos:
                continue
            if (
                termino_low in sim_item.lower()
                or termino_low in item["nombre"].lower()
                or termino_low in item["tipo"].lower()
            ):
                coincidencias.append(dict(item))
                simbolos_vistos.add(sim_item)

        # 4. Búsqueda en vivo en Yahoo Finance (`yf.Search`) cuando se solicita en hilo secundario
        if incluir_remoto and len(termino) >= 2 and self.hay_conexion_internet(usar_cache_breve=True):
            remotos = self._buscar_en_yahoo_finance_remoto(termino)
            for rem in remotos:
                sim_rem = rem["simbolo"].upper()
                if sim_rem not in simbolos_vistos:
                    coincidencias.append(rem)
                    simbolos_vistos.add(sim_rem)

        # 5. Si el usuario escribió un ticker directo que aún no está en la lista, ofrecer búsqueda directa exacta
        simbolo_directo = simbolo_cripto_norm if termino_up in MAPA_CRIPTO_A_YAHOO else termino_up
        if (
            1 <= len(simbolo_directo) <= 12
            and all(ch.isalnum() or ch in ("-", ".") for ch in simbolo_directo)
            and simbolo_directo not in simbolos_vistos
        ):
            coincidencias.insert(
                0,
                {
                    "simbolo": simbolo_directo,
                    "nombre": f"{simbolo_directo} (Consultar en Yahoo Finance)",
                    "tipo": "Acción / ETF / Cripto · Yahoo Finance",
                    "moneda": "USD",
                    "bolsa": "Mercado Global",
                },
            )
        return coincidencias[:12]

    def _buscar_en_yahoo_finance_remoto(self, consulta: str) -> List[Dict[str, str]]:
        clave = consulta.strip().upper()
        if clave in self._cache_busqueda_remota:
            return self._cache_busqueda_remota[clave]

        yf = self._obtener_modulo_yf()
        encontrados: List[Dict[str, str]] = []
        try:
            buscador_cls = getattr(yf, "Search", None)
            if buscador_cls is not None:
                busqueda = buscador_cls(consulta.strip(), max_results=8)
                cotizaciones = getattr(busqueda, "quotes", None) or []
                for q in cotizaciones:
                    if not isinstance(q, dict):
                        continue
                    tipo_q = str(q.get("quoteType", "")).upper()
                    if tipo_q and tipo_q not in (
                        "EQUITY",
                        "ETF",
                        "MUTUALFUND",
                        "INDEX",
                        "CRYPTOCURRENCY",
                    ):
                        continue
                    sim = str(q.get("symbol", "")).strip().upper()
                    if not sim or "=" in sim or "^" in sim:
                        continue
                    if tipo_q == "CRYPTOCURRENCY":
                        sim = normalizar_simbolo_yahoo(sim, es_cripto=True)
                    nombre = (
                        q.get("longname")
                        or q.get("shortname")
                        or q.get("name")
                        or sim
                    )
                    bolsa = str(q.get("exchDisp") or q.get("exchange") or "Yahoo Finance")
                    etiqueta_tipo = "Criptomoneda" if tipo_q == "CRYPTOCURRENCY" else (tipo_q or "Activo")
                    encontrados.append(
                        {
                            "simbolo": sim,
                            "nombre": str(nombre).strip(),
                            "tipo": f"{etiqueta_tipo} · {bolsa}",
                            "moneda": "USD",
                            "bolsa": bolsa,
                        }
                    )
        except Exception:
            pass

        if encontrados:
            self._cache_busqueda_remota[clave] = encontrados
        return encontrados

    def _extraer_precio_tiempo_real(self, ticker, simbolo_limpio: str) -> Tuple[float, date]:
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
                f"Yahoo Finance no devolvió datos para el símbolo '{simbolo_limpio}'."
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
        """Obtiene el precio en tiempo real para un símbolo (ej. 'USDCOP=X', 'BTC-USD', 'SOL-USD', 'VOO', 'TTWO')."""
        if not isinstance(simbolo, str) or not simbolo.strip():
            raise ErrorConsultaBursatil("El símbolo bursátil es obligatorio.")
        simbolo_bruto = simbolo.strip().upper()
        simbolo_limpio = (
            normalizar_simbolo_yahoo(simbolo_bruto)
            if "=" not in simbolo_bruto
            else simbolo_bruto
        )

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

    def consultar_precio_historico_en_fecha(
        self, simbolo: str, fecha_objetivo: date
    ) -> Optional[Decimal]:
        """Obtiene el precio de cierre ajustado por splits en o alrededor de `fecha_objetivo`
        desde Yahoo Finance. Permite corregir automáticamente tasas de apertura corruptas o pre-split."""
        if not isinstance(simbolo, str) or not simbolo.strip():
            return None
        simbolo_limpio = normalizar_simbolo_yahoo(simbolo.strip().upper())
        fecha_ref = fecha_objetivo if isinstance(fecha_objetivo, date) else date.today()
        clave_cache = (simbolo_limpio, fecha_ref.isoformat())
        if clave_cache in self._cache_historico_fecha:
            return self._cache_historico_fecha[clave_cache]

        if not self.hay_conexion_internet(usar_cache_breve=True):
            return None

        yf = self._obtener_modulo_yf()
        try:
            ticker = yf.Ticker(simbolo_limpio)
            inicio = (fecha_ref - timedelta(days=6)).isoformat()
            fin = (fecha_ref + timedelta(days=5)).isoformat()
            historial = ticker.history(start=inicio, end=fin)
        except Exception:
            return None

        if historial is None or historial.empty or "Close" not in historial:
            return None

        mejor_precio: Optional[Decimal] = None
        menor_distancia_dias: Optional[int] = None

        for idx, fila in historial.iterrows():
            val = fila.get("Close")
            if val is None or val != val:
                continue
            try:
                p_dec = Decimal(str(float(val))).quantize(
                    Decimal("0.00000001"), rounding=ROUND_HALF_UP
                )
            except Exception:
                continue
            if p_dec <= Decimal("0"):
                continue

            fecha_fila = idx.date() if hasattr(idx, "date") else fecha_ref
            dist = abs((fecha_fila - fecha_ref).days)
            # Preferir la fecha exacta o el día hábil inmediatamente anterior
            peso = dist * 2 + (1 if fecha_fila > fecha_ref else 0)
            if menor_distancia_dias is None or peso <= menor_distancia_dias:
                menor_distancia_dias = peso
                mejor_precio = p_dec

        if mejor_precio is not None:
            self._cache_historico_fecha[clave_cache] = mejor_precio
        return mejor_precio

    def consultar_serie_temporal(
        self,
        simbolo: str,
        marco_tiempo: str = "1M",
        forzar_actualizacion: bool = False,
    ) -> List[Tuple[str, Decimal]]:
        """Obtiene la serie de puntos `(etiqueta_fecha, precio)` para la gráfica estilo montaña
        en los marcos de tiempo `1D`, `1W`, `1M` o `1Y`, con caché en memoria por sesión."""
        if not isinstance(simbolo, str) or not simbolo.strip():
            raise ErrorConsultaBursatil("El símbolo bursátil es obligatorio.")
        simbolo_limpio = normalizar_simbolo_yahoo(simbolo.strip().upper())
        tf = (marco_tiempo or "1M").strip().upper()
        clave_serie = (simbolo_limpio, tf)

        if not forzar_actualizacion and clave_serie in self._cache_series_temporales:
            return list(self._cache_series_temporales[clave_serie])

        if not self.hay_conexion_internet(usar_cache_breve=True):
            raise ErrorSinConexionInternet(
                "No tienes conexión a internet para consultar la gráfica histórica."
            )
        periodo, intervalo = PARAMETROS_MARCO_TIEMPO.get(tf, ("1mo", "1d"))
        yf = self._obtener_modulo_yf()

        try:
            ticker = yf.Ticker(simbolo_limpio)
            try:
                historial = ticker.history(period=periodo, interval=intervalo)
            except TypeError:
                historial = ticker.history(period=periodo)
            if (historial is None or historial.empty) and intervalo != "1d":
                historial = ticker.history(period=periodo)
        except Exception as error:
            if _es_error_de_red(error) or not self.hay_conexion_internet(usar_cache_breve=False):
                raise ErrorSinConexionInternet(
                    "No tienes conexión a internet para consultar la gráfica histórica."
                ) from error
            raise ErrorConsultaBursatil(
                f"Error al consultar serie temporal de '{simbolo_limpio}': {error}"
            ) from error

        if historial is None or historial.empty or "Close" not in historial:
            raise ErrorConsultaBursatil(
                f"Sin datos históricos para '{simbolo_limpio}' ({tf})."
            )

        puntos: List[Tuple[str, Decimal]] = []
        for idx, fila in historial.iterrows():
            val = fila.get("Close")
            if val is None or val != val:
                continue
            precio = Decimal(str(float(val))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if precio <= Decimal("0"):
                continue
            if hasattr(idx, "strftime"):
                etiqueta = idx.strftime("%d/%m %H:%M") if tf in ("1D", "1W") else idx.strftime("%Y-%m-%d")
            else:
                etiqueta = str(idx)
            puntos.append((etiqueta, precio))

        if tf == "1D" and len(puntos) > 28:
            puntos = puntos[-28:]

        if not puntos:
            raise ErrorConsultaBursatil(
                f"No se encontraron puntos válidos para '{simbolo_limpio}'."
            )
        self._cache_series_temporales[clave_serie] = list(puntos)
        return puntos

    def _consultar_unidades_por_usd(self, codigo_moneda: str) -> Tuple[Decimal, date]:
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
        return self.consultar_precio_actual(SIMBOLO_USD_COP, moneda_esperada="COP")

    def consultar_historial(
        self,
        simbolo: str,
        desde: Optional[date] = None,
        hasta: Optional[date] = None,
        moneda_esperada: str = "USD",
    ) -> List[Cotizacion]:
        if not isinstance(simbolo, str) or not simbolo.strip():
            raise ErrorConsultaBursatil("El símbolo bursátil es obligatorio.")
        if not self.hay_conexion_internet(usar_cache_breve=False):
            raise ErrorSinConexionInternet(
                "No tienes conexión a internet para consultar el historial bursátil."
            )
        simbolo_limpio = normalizar_simbolo_yahoo(simbolo.strip().upper())
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
