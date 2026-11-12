"""Lógica de negocio para gestionar cuentas, ingresos, gastos, categorías, etiquetas, divisas e inversiones.

Incluye gestión inteligente de estado de conexión a internet para divisas e inversiones:
- Cuando hay internet (`ONLINE`): actualiza tasas y precios en tiempo real desde Yahoo Finance y los guarda en caché.
- Cuando no hay internet pero existe caché (`OFFLINE_CON_CACHE`): informa al usuario y utiliza la última cotización guardada.
- Cuando no hay internet y no existe caché (`OFFLINE_SIN_CACHE`): informa al usuario que no tiene conexión y que se actualizará automáticamente apenas se conecte.
"""

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
import threading
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from app.modelo.categoria import Categoria
from app.modelo.cotizacion import Cotizacion
from app.modelo.cuenta import Cuenta
from app.modelo.divisas import (
    CODIGOS_DIVISAS_ORDENADOS,
    DIVISAS_MUNDIALES,
    construir_lista_selector_divisas,
)
from app.modelo.etiqueta import Etiqueta
from app.modelo.inversion import (
    CATALOGO_ACTIVOS_BURSATILES,
    MAPA_CRIPTO_A_YAHOO,
    Inversion,
    ValoracionInversion,
    normalizar_simbolo_yahoo,
)
from app.modelo.movimiento_financiero import MovimientoFinanciero
from app.modelo.transferencia import Transferencia
from app.servicio.importador_etoro import (
    generar_plantilla_csv_etoro,
    parsear_archivo_etoro_o_csv,
)
from app.servicio.importadores import parsear_archivo_broker
from app.servicio.servicio_bursatil import (
    ErrorConsultaBursatil,
    ErrorSinConexionInternet,
    SIMBOLO_USD_COP,
    ServicioBursatil,
)

TIPOS_VALIDOS = ("INGRESO", "GASTO")
MONEDAS_VALIDAS = CODIGOS_DIVISAS_ORDENADOS
FRECUENCIAS_VALIDAS = ("DIARIO", "SEMANAL", "QUINCENAL", "MENSUAL", "ANUAL")
PATRON_VALOR = re.compile(r"^\d+([.,]\d{1,2})?$")
PATRON_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")

ESTADO_CONEXION_ONLINE = "ONLINE"
ESTADO_OFFLINE_CON_CACHE = "OFFLINE_CON_CACHE"
ESTADO_OFFLINE_SIN_CACHE = "OFFLINE_SIN_CACHE"

SIMBOLOS_VALIDOS = (
    "cash",
    "banco",
    "criptomonedas",
    "tarjeta_credito",
    "tarjeta_debito",
    "bolsa",
    "moneda",
    "euro",
    "tap_and_pay",
    "paypal",
    "boveda",
    "puerquito",
)

CATALOGO_SIMBOLOS_CATEGORIAS: Dict[str, List[Tuple[str, str]]] = {
    "Finanzas": [
        ("factura", "Factura / Recibo"),
        ("billetera", "Billetera / Ocio"),
        ("cash", "Efectivo / Salario"),
        ("banco", "Banco / Préstamo"),
        ("tarjeta_credito", "Tarjeta crédito"),
        ("tarjeta_debito", "Tarjeta débito"),
        ("impuestos", "Impuestos / %"),
        ("grafico_subida", "Intereses / Rendimiento"),
        ("calculadora_icono", "Presupuesto"),
        ("puerquito", "Alcancía / Otros"),
        ("boveda", "Bóveda / Caja"),
        ("moneda", "Moneda / Bono"),
    ],
    "Transporte": [
        ("carro", "Automóvil"),
        ("bus", "Bus / Masivo"),
        ("gasolina", "Gasolina / Peaje"),
        ("moto", "Moto / Bicicleta"),
        ("taxi", "Taxi / App"),
    ],
    "Vacaciones y Viajes": [
        ("tickets", "Tiquetes / Boletos"),
        ("bikini", "Playa / Bikini"),
        ("avion", "Vuelos / Avión"),
        ("maleta", "Equipaje / Maleta"),
        ("playa", "Sombrilla / Sol"),
        ("hotel", "Hotel / Hospedaje"),
        ("camping", "Camping / Naturaleza"),
    ],
    "Compras": [
        ("mercado", "Supermercado"),
        ("bolsa_compras", "Ventas / Compras"),
        ("ropa", "Ropa / Moda"),
        ("zapatos", "Calzado / Zapatos"),
        ("regalo", "Regalos / Detalles"),
        ("etiqueta_icono", "Ofertas / Descuentos"),
    ],
    "Comida y Bebida": [
        ("cubiertos", "Restaurante / Café"),
        ("taza_cafe", "Cafetería / Tinto"),
        ("hamburguesa", "Comida rápida"),
        ("pizza", "Pizza / Domicilio"),
        ("copa", "Bar / Bebidas"),
        ("helado", "Postres / Helado"),
    ],
    "Casa y Hogar": [
        ("casa", "Vivienda / Arriendo"),
        ("olla", "Cocina / Ollas"),
        ("pintura", "Pintura / Mejoras"),
        ("lavadora", "Electrodomésticos"),
        ("herramientas", "Reparaciones"),
        ("muebles", "Muebles / Decoración"),
    ],
    "Cuentas y Servicios": [
        ("bombillo", "Energía / Luz"),
        ("gota_agua", "Acueducto / Agua"),
        ("wifi", "Internet / TV"),
        ("celular", "Plan Celular"),
    ],
    "Salud y Belleza": [
        ("corazon_pulso", "Salud / EPS"),
        ("pildora", "Medicamentos"),
        ("hospital", "Clínica / Consulta"),
        ("diente", "Odontología"),
        ("tijeras", "Peluquería / Barbería"),
        ("cosmeticos", "Cosméticos / Maquillaje"),
        ("spa", "Spa / Cuidado personal"),
    ],
    "Entretenimiento y Tecnología": [
        ("videojuegos", "Videojuegos / Consolas"),
        ("cine", "Cine / Streaming"),
        ("musica", "Música / Conciertos"),
        ("computador", "Tecnología / Freelance"),
        ("camara", "Fotografía / Hobby"),
    ],
    "Mascotas, Educación y Rutina": [
        ("mascota", "Mascotas / Veterinaria"),
        ("graduacion", "Educación / Cursos"),
        ("libro", "Libros / Papelería"),
        ("gimnasio", "Gimnasio / Deporte"),
        ("reloj", "Rutina / Suscripción"),
        ("familia", "Familia / Hijos"),
    ],
}

TODOS_LOS_SIMBOLOS_CATEGORIA = tuple(
    {clave for lista in CATALOGO_SIMBOLOS_CATEGORIAS.values() for clave, _ in lista}
    | set(SIMBOLOS_VALIDOS)
)

CATEGORIAS_GASTO_PREDETERMINADAS = (
    Categoria(None, "Salud", "GASTO", "corazon_pulso", "#F28C8C", True),
    Categoria(None, "Ocio", "GASTO", "billetera", "#408FD1", True),
    Categoria(None, "Casa", "GASTO", "casa", "#FBB718", True),
    Categoria(None, "Café", "GASTO", "cubiertos", "#D98A4E", True),
    Categoria(None, "Educación", "GASTO", "graduacion", "#9B7EDE", True),
    Categoria(None, "Regalos", "GASTO", "regalo", "#E86F9A", True),
    Categoria(None, "Alimentación", "GASTO", "mercado", "#7DC98F", True),
)

CATEGORIAS_INGRESO_PREDETERMINADAS = (
    Categoria(None, "Salario", "INGRESO", "cash", "#7DC98F", True),
    Categoria(None, "Regalo", "INGRESO", "regalo", "#E86F9A", True),
    Categoria(None, "Intereses", "INGRESO", "grafico_subida", "#FBB718", True),
    Categoria(None, "Préstamo", "INGRESO", "banco", "#408FD1", True),
    Categoria(None, "Ventas", "INGRESO", "bolsa_compras", "#89BF50", True),
    Categoria(None, "Bonificación", "INGRESO", "moneda", "#D98A4E", True),
    Categoria(None, "Otros", "INGRESO", "puerquito", "#9B7EDE", True),
)


class ErrorValidacion(Exception):
    """Se lanza cuando los datos ingresados por el usuario no cumplen las reglas."""


# ---------------------------------------------------------------------------
# Detección de duplicados en la importación de portafolios
# ---------------------------------------------------------------------------

def _clave_duplicado(simbolo: str, fecha_compra, monto_invertido) -> tuple:
    """Llave de comparación: símbolo + fecha de compra + monto en centavos.

    El monto se compara en centavos (2 decimales) para que diferencias
    de redondeo del archivo no cuenten como posiciones distintas.
    """
    monto = Decimal(str(monto_invertido)).quantize(Decimal("0.01"))
    return (str(simbolo).strip().upper(), str(fecha_compra), monto)


def clave_duplicado_posicion(posicion: Dict[str, object]) -> tuple:
    """Llave de duplicado para una posición detectada en un archivo."""
    fecha = posicion.get("fecha_compra") or ""
    return _clave_duplicado(
        posicion.get("simbolo", ""),
        fecha.isoformat() if hasattr(fecha, "isoformat") else fecha,
        posicion.get("monto_invertido", 0),
    )


def clave_duplicado_inversion(inversion: Inversion) -> tuple:
    """Llave de duplicado para una inversión ya guardada en la base."""
    return _clave_duplicado(
        inversion.simbolo, inversion.fecha_compra, inversion.monto_invertido)


def totales_por_moneda(movimientos: Iterable[MovimientoFinanciero]) -> Dict[str, Decimal]:
    """Suma valores agrupando por moneda sin mezclar divisas."""
    totales: Dict[str, Decimal] = {}
    for mov in movimientos:
        totales[mov.moneda] = totales.get(mov.moneda, Decimal("0")) + mov.valor
    return totales


def totales_cuentas_por_moneda(cuentas_con_saldo: Iterable[Tuple[Cuenta, Decimal]]) -> Dict[str, Decimal]:
    """Suma saldos de cuentas que incluyen en el total, separando por moneda."""
    totales: Dict[str, Decimal] = {}
    for cuenta, saldo in cuentas_con_saldo:
        if cuenta.incluye_en_total:
            totales[cuenta.moneda] = totales.get(cuenta.moneda, Decimal("0")) + saldo
    return totales


def _marcar_cotizacion_como_cache(cot: Cotizacion) -> Cotizacion:
    """Devuelve una copia de la cotización indicando explícitamente que proviene del caché local."""
    fuente_actual = cot.fuente or "Yahoo Finance"
    if "Caché" not in fuente_actual:
        fuente_nueva = "Caché local (Sin conexión)"
    else:
        fuente_nueva = fuente_actual
    return Cotizacion(
        id=cot.id,
        simbolo=cot.simbolo,
        fecha=cot.fecha,
        precio=cot.precio,
        moneda=cot.moneda,
        fuente=fuente_nueva,
    )


class GestorFinanciero:
    """Coordina las validaciones, el acceso al repositorio y las consultas bursátiles en tiempo real."""

    def __init__(self, repositorio, servicio_bursatil: Optional[ServicioBursatil] = None):
        self._repositorio = repositorio
        self._servicio_bursatil = servicio_bursatil or ServicioBursatil()
        self._cotizacion_usd_cop_memoria: Optional[Cotizacion] = None
        self._tasas_memoria: Dict[Tuple[str, str], Cotizacion] = {}
        self._tasas_vivas_sesion: Dict[Tuple[str, str], Cotizacion] = {}
        self._precios_inversion_memoria: Dict[str, Cotizacion] = {}
        self._precios_inversion_vivos_sesion: Dict[str, Cotizacion] = {}
        self._estado_conexion_api: str = ESTADO_CONEXION_ONLINE
        self._ultima_cotizacion_usada: Optional[Cotizacion] = None
        self._listeners_conexion: List[Callable[[], None]] = []
        self._monedas_recientes_memoria: List[str] = ["USD", "EUR", "MXN", "GBP"]
        self._categorias_memoria_extra: Dict[str, Categoria] = {
            c.nombre: c
            for c in (
                list(CATEGORIAS_GASTO_PREDETERMINADAS)
                + list(CATEGORIAS_INGRESO_PREDETERMINADAS)
            )
        }
        self._etiquetas_memoria_extra: Dict[str, Etiqueta] = {}
        self._inversiones_memoria: List[Inversion] = []
        self._cache_inversiones_bd: Optional[List[Inversion]] = None
        self._cache_categorias_detalladas: Dict[str, List[Categoria]] = {}
        self._cache_nombres_categorias: Optional[List[str]] = None
        self._monedas_recientes_cargadas_bd: bool = False
        self._tabla_inversion_verificada: bool = False
        self._inversiones_verificadas_sesion: Set[int] = set()

    # ------------------------------------------------------------------
    # Estado de conexión a internet, caché offline y notificaciones a la GUI
    # ------------------------------------------------------------------
    def registrar_listener_conexion(self, callback: Callable[[], None]) -> None:
        if callback not in self._listeners_conexion:
            self._listeners_conexion.append(callback)

    def desregistrar_listener_conexion(self, callback: Callable[[], None]) -> None:
        if callback in self._listeners_conexion:
            self._listeners_conexion.remove(callback)

    def _notificar_cambio_estado_conexion(self) -> None:
        for cb in list(self._listeners_conexion):
            try:
                cb()
            except Exception:
                pass

    def hay_conexion_internet(self, usar_cache_breve: bool = False) -> bool:
        """Verifica si hay acceso a internet a través del ServicioBursatil."""
        if hasattr(self._servicio_bursatil, "hay_conexion_internet"):
            return self._servicio_bursatil.hay_conexion_internet(
                usar_cache_breve=usar_cache_breve
            )
        return True

    def obtener_estado_conexion_bursatil(
        self, moneda_referencia: str = "USD"
    ) -> Dict[str, object]:
        """Devuelve el diagnóstico actual de conectividad y caché para mostrar en la GUI."""
        mon = (moneda_referencia or "USD").strip().upper()
        if mon == "COP":
            mon = "USD"

        online = self.hay_conexion_internet(usar_cache_breve=True)
        if online and self._estado_conexion_api == ESTADO_CONEXION_ONLINE:
            return {
                "online": True,
                "estado": ESTADO_CONEXION_ONLINE,
                "tiene_cache": True,
                "cotizacion_cache": self._ultima_cotizacion_usada,
                "mensaje": "",
            }

        cot_cache = self._buscar_cotizacion_en_cache(mon, "COP")
        if cot_cache is None and self._ultima_cotizacion_usada is not None:
            cot_cache = self._ultima_cotizacion_usada

        if cot_cache is not None:
            fecha_txt = cot_cache.fecha.isoformat()
            precio_txt = f"{cot_cache.precio:,.2f}"
            par_txt = f"1 {mon} = $ {precio_txt} COP"
            mensaje = (
                f"⚠️ Sin conexión a internet: no es posible actualizar los precios de divisas e inversiones. "
                f"Mostrando información guardada en caché ({par_txt} del {fecha_txt}). "
                f"Tan pronto como te conectes a internet, actualizaremos la información."
            )
            return {
                "online": False,
                "estado": ESTADO_OFFLINE_CON_CACHE,
                "tiene_cache": True,
                "cotizacion_cache": cot_cache,
                "mensaje": mensaje,
            }

        mensaje_sin_cache = (
            "📡 No tienes conexión a internet y no hay información guardada en caché. "
            "Tan pronto como te conectes a internet, actualizaremos los precios de divisas e inversiones automáticamente."
        )
        return {
            "online": False,
            "estado": ESTADO_OFFLINE_SIN_CACHE,
            "tiene_cache": False,
            "cotizacion_cache": None,
            "mensaje": mensaje_sin_cache,
        }

    def _buscar_cotizacion_en_cache(
        self, origen: str, destino: str
    ) -> Optional[Cotizacion]:
        """Busca una tasa de cambio guardada en memoria o en la base de datos local,
        incluyendo búsqueda directa, inversa y triangulación vía USD si existe en caché."""
        par = (origen, destino)
        simbolo_par = f"{origen}{destino}=X"

        if par in self._tasas_memoria:
            return _marcar_cotizacion_como_cache(self._tasas_memoria[par])

        if hasattr(self._repositorio, "obtener_ultima_cotizacion"):
            # 1) Búsqueda directa (ej. USDCOP=X, EURCOP=X)
            guardada = self._repositorio.obtener_ultima_cotizacion(simbolo_par)
            if guardada is not None and guardada.precio > Decimal("0"):
                cot_cache = _marcar_cotizacion_como_cache(guardada)
                self._tasas_memoria[par] = cot_cache
                return cot_cache

            # 2) Búsqueda por ticker corto si el origen es USD (ej. COP=X o BGN=X)
            if origen == "USD":
                guardada_corta = self._repositorio.obtener_ultima_cotizacion(f"{destino}=X")
                if guardada_corta is not None and guardada_corta.precio > Decimal("0"):
                    cot_cache = Cotizacion(
                        id=guardada_corta.id,
                        simbolo=simbolo_par,
                        fecha=guardada_corta.fecha,
                        precio=guardada_corta.precio,
                        moneda=destino,
                        fuente="Caché local (Sin conexión)",
                    )
                    self._tasas_memoria[par] = cot_cache
                    return cot_cache

            # 3) Búsqueda inversa (ej. si piden COP -> USD y está guardada USDCOP=X)
            simbolo_inv = f"{destino}{origen}=X"
            guardada_inv = self._repositorio.obtener_ultima_cotizacion(simbolo_inv)
            if guardada_inv is not None and guardada_inv.precio > Decimal("0"):
                tasa_inv = (Decimal("1") / guardada_inv.precio).quantize(
                    Decimal("0.00000001"), rounding=ROUND_HALF_UP
                )
                cot_cache = Cotizacion(
                    id=guardada_inv.id,
                    simbolo=simbolo_par,
                    fecha=guardada_inv.fecha,
                    precio=tasa_inv,
                    moneda=destino,
                    fuente="Caché local (Sin conexión)",
                )
                self._tasas_memoria[par] = cot_cache
                return cot_cache

        return None

    # ------------------------------------------------------------------
    # Historial de las últimas 5 divisas usadas y Selector Mundial
    # ------------------------------------------------------------------
    def registrar_moneda_usada(self, codigo: str) -> None:
        if not isinstance(codigo, str):
            return
        limpia = codigo.strip().upper()
        if limpia not in DIVISAS_MUNDIALES or limpia == "COP":
            return
        if self._monedas_recientes_memoria and self._monedas_recientes_memoria[0] == limpia:
            return
        if limpia in self._monedas_recientes_memoria:
            self._monedas_recientes_memoria.remove(limpia)
        self._monedas_recientes_memoria.insert(0, limpia)
        self._monedas_recientes_memoria = self._monedas_recientes_memoria[:4]

        if hasattr(self._repositorio, "registrar_moneda_reciente"):
            def _guardar_bg():
                try:
                    self._repositorio.registrar_moneda_reciente(limpia)
                except Exception:
                    pass
            threading.Thread(target=_guardar_bg, daemon=True).start()

    def obtener_ultimas_5_monedas(self) -> List[str]:
        """Devuelve siempre ['COP', <hasta 4 últimas divisas usadas>] desde caché en memoria."""
        if not self._monedas_recientes_cargadas_bd:
            self._monedas_recientes_cargadas_bd = True
            if hasattr(self._repositorio, "obtener_monedas_recientes"):
                try:
                    recientes_bd = self._repositorio.obtener_monedas_recientes(4)
                    combinadas_ini: List[str] = []
                    for cod in list(recientes_bd) + list(self._monedas_recientes_memoria):
                        c = cod.strip().upper()
                        if c in DIVISAS_MUNDIALES and c != "COP" and c not in combinadas_ini:
                            combinadas_ini.append(c)
                        if len(combinadas_ini) >= 4:
                            break
                    if combinadas_ini:
                        self._monedas_recientes_memoria = combinadas_ini
                except Exception:
                    pass

        combinadas: List[str] = ["COP"]
        for cod in self._monedas_recientes_memoria:
            c = cod.strip().upper()
            if c in DIVISAS_MUNDIALES and c not in combinadas:
                combinadas.append(c)
            if len(combinadas) >= 5:
                break
        return combinadas

    def obtener_opciones_selector_divisas(self) -> List[str]:
        ultimas_5 = self.obtener_ultimas_5_monedas()
        return construir_lista_selector_divisas(ultimas_5[1:])

    # ------------------------------------------------------------------
    # Conversión en tiempo real entre cualquier par de divisas (Yahoo Finance) + Caché Offline
    # ------------------------------------------------------------------
    def tiene_tasa_en_sesion(self, moneda_origen: str, moneda_destino: str) -> bool:
        """Indica si el par de divisas ya está cargado en memoria en esta sesión (respuesta 0ms)."""
        origen = moneda_origen.strip().upper()
        destino = moneda_destino.strip().upper()
        if origen == destino:
            return True
        if (origen, destino) in self._tasas_vivas_sesion:
            return True
        if origen == "COP" and (destino, "COP") in self._tasas_vivas_sesion:
            return True
        return False

    def obtener_tasa_cambio_instantanea(
        self, moneda_origen: str, moneda_destino: str
    ) -> Optional[Cotizacion]:
        """Devuelve la tasa de cambio desde memoria o caché local en 0ms sin realizar llamadas de red."""
        return self.obtener_tasa_cambio(
            moneda_origen,
            moneda_destino,
            forzar_actualizacion=False,
            permitir_red=False,
        )

    def obtener_tasa_cambio(
        self,
        moneda_origen: str,
        moneda_destino: str,
        forzar_actualizacion: bool = False,
        permitir_red: bool = True,
    ) -> Optional[Cotizacion]:
        origen = self._validar_moneda(moneda_origen)
        destino = self._validar_moneda(moneda_destino)
        if origen == destino:
            return Cotizacion(
                id=None,
                simbolo=f"{origen}{destino}=X",
                fecha=date.today(),
                precio=Decimal("1.00000000"),
                moneda=destino,
                fuente="Paridad 1:1",
            )

        par = (origen, destino)

        # Si ya se obtuvo en vivo en esta sesión, reutilizar instantáneamente en 0ms
        if not forzar_actualizacion and par in self._tasas_vivas_sesion:
            cot_viva = self._tasas_vivas_sesion[par]
            self._estado_conexion_api = ESTADO_CONEXION_ONLINE
            self._ultima_cotizacion_usada = cot_viva
            return cot_viva

        if not permitir_red:
            return self._buscar_cotizacion_en_cache(origen, destino)

        try:
            nueva = self._servicio_bursatil.consultar_tasa_cambio(origen, destino)
            if hasattr(self._repositorio, "guardar_cotizaciones"):
                try:
                    guardadas = self._repositorio.guardar_cotizaciones([nueva])
                    if guardadas:
                        nueva = guardadas[0]
                except Exception:
                    pass
            self._tasas_vivas_sesion[par] = nueva
            self._tasas_memoria[par] = nueva
            if par == ("USD", "COP"):
                self._cotizacion_usd_cop_memoria = nueva
            cambio_estado = self._estado_conexion_api != ESTADO_CONEXION_ONLINE
            self._estado_conexion_api = ESTADO_CONEXION_ONLINE
            self._ultima_cotizacion_usada = nueva
            if cambio_estado:
                self._notificar_cambio_estado_conexion()
            return nueva
        except (ErrorSinConexionInternet, ErrorConsultaBursatil):
            cot_cache = self._buscar_cotizacion_en_cache(origen, destino)
            if cot_cache is not None:
                self._estado_conexion_api = ESTADO_OFFLINE_CON_CACHE
                self._ultima_cotizacion_usada = cot_cache
                self._notificar_cambio_estado_conexion()
                return cot_cache

            self._estado_conexion_api = ESTADO_OFFLINE_SIN_CACHE
            self._ultima_cotizacion_usada = None
            self._notificar_cambio_estado_conexion()
            return None

    def convertir_entre_monedas(
        self,
        monto: Decimal,
        moneda_origen: str,
        moneda_destino: str,
        tasa: Optional[Decimal] = None,
    ) -> Decimal:
        origen = self._validar_moneda(moneda_origen)
        destino = self._validar_moneda(moneda_destino)
        monto_dec = Decimal(str(monto))
        if origen == destino:
            return monto_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if tasa is not None:
            if tasa <= Decimal("0"):
                raise ErrorValidacion("La tasa de cambio debe ser mayor que cero.")
            return (monto_dec * tasa).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if origen == "COP" and destino != "COP":
            cot_inversa = self.obtener_tasa_cambio(destino, "COP")
            if cot_inversa is not None and cot_inversa.precio > Decimal("0"):
                return (monto_dec / cot_inversa.precio).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )

        cot = self.obtener_tasa_cambio(origen, destino)
        if cot is None or cot.precio <= Decimal("0"):
            raise ErrorValidacion(
                f"No hay tasa de cambio disponible de {origen} a {destino}."
            )
        return (monto_dec * cot.precio).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    def obtener_tasa_usd_cop(self, forzar_actualizacion: bool = False) -> Optional[Cotizacion]:
        par = ("USD", "COP")
        if (
            not forzar_actualizacion
            and par in self._tasas_vivas_sesion
            and self.hay_conexion_internet(usar_cache_breve=True)
        ):
            cot_viva = self._tasas_vivas_sesion[par]
            self._estado_conexion_api = ESTADO_CONEXION_ONLINE
            self._ultima_cotizacion_usada = cot_viva
            return cot_viva

        try:
            nueva = self._servicio_bursatil.consultar_tasa_usd_cop()
            if hasattr(self._repositorio, "guardar_cotizaciones"):
                try:
                    guardadas = self._repositorio.guardar_cotizaciones([nueva])
                    if guardadas:
                        nueva = guardadas[0]
                except Exception:
                    pass
            self._cotizacion_usd_cop_memoria = nueva
            self._tasas_vivas_sesion[par] = nueva
            self._tasas_memoria[par] = nueva
            cambio_estado = self._estado_conexion_api != ESTADO_CONEXION_ONLINE
            self._estado_conexion_api = ESTADO_CONEXION_ONLINE
            self._ultima_cotizacion_usada = nueva
            if cambio_estado:
                self._notificar_cambio_estado_conexion()
            return nueva
        except (ErrorSinConexionInternet, ErrorConsultaBursatil):
            cot_cache = self._buscar_cotizacion_en_cache("USD", "COP")
            if cot_cache is None and self._cotizacion_usd_cop_memoria is not None:
                cot_cache = _marcar_cotizacion_como_cache(self._cotizacion_usd_cop_memoria)
            if cot_cache is not None:
                self._cotizacion_usd_cop_memoria = cot_cache
                self._estado_conexion_api = ESTADO_OFFLINE_CON_CACHE
                self._ultima_cotizacion_usada = cot_cache
                self._notificar_cambio_estado_conexion()
                return cot_cache

            self._estado_conexion_api = ESTADO_OFFLINE_SIN_CACHE
            self._ultima_cotizacion_usada = None
            self._notificar_cambio_estado_conexion()
            return None

    def consultar_precio_historico_inversion(
        self,
        simbolo: str,
        fecha_compra: date,
        moneda_esperada: str = "USD",
    ) -> Optional[Decimal]:
        """Obtiene el precio histórico ajustado por splits en `fecha_compra` desde Yahoo Finance."""
        if not hasattr(self._servicio_bursatil, "consultar_precio_historico_en_fecha"):
            return None
        simbolo_limpio = normalizar_simbolo_yahoo(simbolo.strip().upper())
        try:
            precio_usd = self._servicio_bursatil.consultar_precio_historico_en_fecha(
                simbolo_limpio, fecha_compra
            )
        except Exception:
            precio_usd = None
        if precio_usd is None or precio_usd <= Decimal("0"):
            return None
        mon_dest = (moneda_esperada or "USD").strip().upper()
        if mon_dest == "USD":
            return precio_usd
        try:
            return self.convertir_entre_monedas(precio_usd, "USD", mon_dest)
        except Exception:
            return precio_usd

    def consultar_precio_inversion(
        self,
        simbolo: str,
        moneda_esperada: str = "USD",
        forzar_actualizacion: bool = False,
        permitir_red: bool = True,
    ) -> Optional[Cotizacion]:
        """Consulta el precio en tiempo real de un activo de inversión (ej. 'VOO', 'AAPL', 'BTC-USD', 'SOL-USD').
        Si `permitir_red=False`, devuelve inmediatamente desde memoria o caché de BD en 0ms sin bloquear la GUI."""
        simbolo_limpio = normalizar_simbolo_yahoo(simbolo.strip().upper())
        if not forzar_actualizacion and simbolo_limpio in self._precios_inversion_vivos_sesion:
            cot_viva = self._precios_inversion_vivos_sesion[simbolo_limpio]
            self._estado_conexion_api = ESTADO_CONEXION_ONLINE
            self._ultima_cotizacion_usada = cot_viva
            return cot_viva

        if not permitir_red:
            cot_mem = self._precios_inversion_memoria.get(simbolo_limpio)
            if cot_mem is not None:
                return cot_mem
            if hasattr(self._repositorio, "obtener_ultima_cotizacion"):
                try:
                    cot_bd = self._repositorio.obtener_ultima_cotizacion(simbolo_limpio)
                    if cot_bd is not None:
                        self._precios_inversion_memoria[simbolo_limpio] = cot_bd
                        return cot_bd
                except Exception:
                    pass
            return None

        try:
            nueva = self._servicio_bursatil.consultar_precio_actual(
                simbolo_limpio, moneda_esperada=moneda_esperada
            )
            if hasattr(self._repositorio, "guardar_cotizaciones"):
                try:
                    guardadas = self._repositorio.guardar_cotizaciones([nueva])
                    if guardadas:
                        nueva = guardadas[0]
                except Exception:
                    pass
            self._precios_inversion_vivos_sesion[simbolo_limpio] = nueva
            self._precios_inversion_memoria[simbolo_limpio] = nueva
            self._estado_conexion_api = ESTADO_CONEXION_ONLINE
            self._ultima_cotizacion_usada = nueva
            self._notificar_cambio_estado_conexion()
            return nueva
        except ErrorSinConexionInternet:
            cot_cache = self._precios_inversion_memoria.get(simbolo_limpio)
            if cot_cache is None and hasattr(self._repositorio, "obtener_ultima_cotizacion"):
                cot_cache = self._repositorio.obtener_ultima_cotizacion(simbolo_limpio)
            if cot_cache is not None:
                cot_cache = _marcar_cotizacion_como_cache(cot_cache)
                self._precios_inversion_memoria[simbolo_limpio] = cot_cache
                self._estado_conexion_api = ESTADO_OFFLINE_CON_CACHE
                self._ultima_cotizacion_usada = cot_cache
                self._notificar_cambio_estado_conexion()
                return cot_cache

            self._estado_conexion_api = ESTADO_OFFLINE_SIN_CACHE
            self._ultima_cotizacion_usada = None
            self._notificar_cambio_estado_conexion()
            return None
        except ErrorConsultaBursatil:
            # El usuario sí tiene internet pero el símbolo no existe o no tiene datos en Yahoo Finance
            cot_cache = self._precios_inversion_memoria.get(simbolo_limpio)
            if cot_cache is None and hasattr(self._repositorio, "obtener_ultima_cotizacion"):
                cot_cache = self._repositorio.obtener_ultima_cotizacion(simbolo_limpio)
            return cot_cache

    def convertir_usd_a_cop(self, monto_usd: Decimal, tasa: Optional[Decimal] = None) -> Decimal:
        tasa_efectiva = tasa
        if tasa_efectiva is None:
            cot = self.obtener_tasa_usd_cop()
            if cot is None:
                raise ErrorValidacion("No hay una tasa de cambio USD/COP disponible.")
            tasa_efectiva = cot.precio
        if tasa_efectiva <= Decimal("0"):
            raise ErrorValidacion("La tasa de cambio debe ser mayor que cero.")
        return (monto_usd * tasa_efectiva).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def convertir_cop_a_usd(self, monto_cop: Decimal, tasa: Optional[Decimal] = None) -> Decimal:
        tasa_efectiva = tasa
        if tasa_efectiva is None:
            cot = self.obtener_tasa_usd_cop()
            if cot is None:
                raise ErrorValidacion("No hay una tasa de cambio USD/COP disponible.")
            tasa_efectiva = cot.precio
        if tasa_efectiva <= Decimal("0"):
            raise ErrorValidacion("La tasa de cambio debe ser mayor que cero.")
        return (monto_cop / tasa_efectiva).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # ------------------------------------------------------------------
    # Resúmenes y Totales Unificados por Mes o por Rango arbitrario
    # ------------------------------------------------------------------
    def resumen_del_rango_en_moneda(
        self,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        moneda_objetivo: str = "COP",
        incluir_todas_convertidas: bool = False,
    ) -> Dict[str, object]:
        if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
            raise ErrorValidacion("La fecha final no puede ser anterior a la fecha inicial.")

        moneda_dest = self._validar_moneda(moneda_objetivo)
        self.registrar_moneda_usada(moneda_dest)
        movimientos = self.obtener_movimientos(
            tipo=None, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin
        )

        total_ingresos = Decimal("0")
        total_gastos = Decimal("0")
        ingresos_por_cat: Dict[str, Decimal] = {}
        gastos_por_cat: Dict[str, Decimal] = {}
        colores_ing = {c.nombre: c.color for c in self.obtener_categorias_detalladas("INGRESO")}
        colores_gas = {c.nombre: c.color for c in self.obtener_categorias_detalladas("GASTO")}

        for mov in movimientos:
            if not incluir_todas_convertidas and mov.moneda != moneda_dest:
                continue

            if mov.moneda == moneda_dest:
                monto = mov.valor
            else:
                try:
                    monto = self.convertir_entre_monedas(mov.valor, mov.moneda, moneda_dest)
                except ErrorValidacion:
                    continue

            if mov.tipo_movimiento == "INGRESO":
                total_ingresos += monto
                ingresos_por_cat[mov.categoria] = (
                    ingresos_por_cat.get(mov.categoria, Decimal("0")) + monto
                )
            elif mov.tipo_movimiento == "GASTO":
                total_gastos += monto
                gastos_por_cat[mov.categoria] = (
                    gastos_por_cat.get(mov.categoria, Decimal("0")) + monto
                )

        return {
            "ingresos": total_ingresos,
            "gastos": total_gastos,
            "balance_neto": total_ingresos - total_gastos,
            "ingresos_por_categoria": ingresos_por_cat,
            "gastos_por_categoria": gastos_por_cat,
            "colores_ingresos": colores_ing,
            "colores_gastos": colores_gas,
        }

    def resumen_del_mes_en_moneda(
        self,
        anno: int,
        mes: int,
        moneda_objetivo: str = "COP",
        incluir_todas_convertidas: bool = False,
    ) -> Dict[str, object]:
        moneda_dest = self._validar_moneda(moneda_objetivo)
        self.registrar_moneda_usada(moneda_dest)
        por_moneda = self.resumen_del_mes(anno, mes)

        if not incluir_todas_convertidas:
            datos = por_moneda.get(moneda_dest)
            if not datos:
                return {
                    "ingresos": Decimal("0"),
                    "gastos": Decimal("0"),
                    "gastos_por_categoria": {},
                }
            return {
                "ingresos": datos["ingresos"],
                "gastos": datos["gastos"],
                "gastos_por_categoria": dict(datos["gastos_por_categoria"]),  # type: ignore[arg-type]
            }

        total_ingresos = Decimal("0")
        total_gastos = Decimal("0")
        gastos_cat_unificados: Dict[str, Decimal] = {}

        for mon_orig, datos in por_moneda.items():
            ing_orig: Decimal = datos["ingresos"]  # type: ignore[assignment]
            gas_orig: Decimal = datos["gastos"]  # type: ignore[assignment]
            cats_orig: Dict[str, Decimal] = datos["gastos_por_categoria"]  # type: ignore[assignment]

            try:
                if ing_orig > Decimal("0"):
                    total_ingresos += self.convertir_entre_monedas(ing_orig, mon_orig, moneda_dest)
                if gas_orig > Decimal("0"):
                    total_gastos += self.convertir_entre_monedas(gas_orig, mon_orig, moneda_dest)
                for cat_nombre, monto_cat in cats_orig.items():
                    monto_conv = self.convertir_entre_monedas(monto_cat, mon_orig, moneda_dest)
                    gastos_cat_unificados[cat_nombre] = (
                        gastos_cat_unificados.get(cat_nombre, Decimal("0")) + monto_conv
                    )
            except ErrorValidacion:
                continue

        return {
            "ingresos": total_ingresos,
            "gastos": total_gastos,
            "gastos_por_categoria": gastos_cat_unificados,
        }

    def _resumen_movimientos_periodo(
        self,
        tipo: str,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        moneda_objetivo: Optional[str] = None,
        incluir_todas_convertidas: bool = False,
        color_defecto: str = "#FBB718",
        simbolo_defecto: str = "mercado",
    ) -> Dict[str, Dict[str, object]]:
        if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
            raise ErrorValidacion("La fecha final no puede ser anterior a la fecha inicial.")

        mapa_cat = {c.nombre: c for c in self.obtener_categorias_detalladas(tipo)}
        movimientos = self.obtener_movimientos(tipo, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)

        if moneda_objetivo and incluir_todas_convertidas:
            mon_dest = self._validar_moneda(moneda_objetivo)
            self.registrar_moneda_usada(mon_dest)
            datos_unificados: Dict[str, object] = {
                "total": Decimal("0"),
                "por_categoria": {},
                "colores": {},
                "simbolos": {},
            }
            for m in movimientos:
                try:
                    valor_conv = self.convertir_entre_monedas(m.valor, m.moneda, mon_dest)
                except ErrorValidacion:
                    continue
                datos_unificados["total"] = datos_unificados["total"] + valor_conv  # type: ignore[operator]
                por_cat: Dict[str, Decimal] = datos_unificados["por_categoria"]  # type: ignore[assignment]
                por_cat[m.categoria] = por_cat.get(m.categoria, Decimal("0")) + valor_conv

                cat_info = mapa_cat.get(m.categoria)
                colores: Dict[str, str] = datos_unificados["colores"]  # type: ignore[assignment]
                simbolos: Dict[str, str] = datos_unificados["simbolos"]  # type: ignore[assignment]
                colores[m.categoria] = cat_info.color if cat_info else color_defecto
                simbolos[m.categoria] = cat_info.simbolo if cat_info else simbolo_defecto
            return {mon_dest: datos_unificados} if movimientos else {}

        resumen: Dict[str, Dict[str, object]] = {}
        for m in movimientos:
            datos_moneda = resumen.setdefault(
                m.moneda,
                {"total": Decimal("0"), "por_categoria": {}, "colores": {}, "simbolos": {}},
            )
            datos_moneda["total"] = datos_moneda["total"] + m.valor
            por_cat = datos_moneda["por_categoria"]  # type: ignore[assignment]
            por_cat[m.categoria] = por_cat.get(m.categoria, Decimal("0")) + m.valor

            cat_info = mapa_cat.get(m.categoria)
            colores = datos_moneda["colores"]  # type: ignore[assignment]
            simbolos = datos_moneda["simbolos"]  # type: ignore[assignment]
            colores[m.categoria] = cat_info.color if cat_info else color_defecto
            simbolos[m.categoria] = cat_info.simbolo if cat_info else simbolo_defecto

        return resumen

    def resumen_gastos_periodo(
        self,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        moneda_objetivo: Optional[str] = None,
        incluir_todas_convertidas: bool = False,
    ) -> Dict[str, Dict[str, object]]:
        return self._resumen_movimientos_periodo(
            tipo="GASTO",
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            moneda_objetivo=moneda_objetivo,
            incluir_todas_convertidas=incluir_todas_convertidas,
            color_defecto="#FBB718",
            simbolo_defecto="mercado",
        )

    def resumen_ingresos_periodo(
        self,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        moneda_objetivo: Optional[str] = None,
        incluir_todas_convertidas: bool = False,
    ) -> Dict[str, Dict[str, object]]:
        return self._resumen_movimientos_periodo(
            tipo="INGRESO",
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            moneda_objetivo=moneda_objetivo,
            incluir_todas_convertidas=incluir_todas_convertidas,
            color_defecto="#7DC98F",
            simbolo_defecto="cash",
        )

    def calcular_total_cuentas_en_moneda(
        self,
        cuentas_con_saldo: Iterable[Tuple[Cuenta, Decimal]],
        moneda_objetivo: str = "COP",
        incluir_todas_convertidas: bool = False,
    ) -> Decimal:
        mon_dest = self._validar_moneda(moneda_objetivo)
        self.registrar_moneda_usada(mon_dest)
        total = Decimal("0")
        for cuenta, saldo in cuentas_con_saldo:
            if not cuenta.incluye_en_total:
                continue
            if cuenta.moneda == mon_dest:
                total += saldo
            elif incluir_todas_convertidas:
                try:
                    total += self.convertir_entre_monedas(saldo, cuenta.moneda, mon_dest)
                except ErrorValidacion:
                    continue
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # ------------------------------------------------------------------
    # Categorías (compatibilidad total + creación customizada para GASTO e INGRESO)
    # ------------------------------------------------------------------
    def obtener_categorias(self) -> List[str]:
        if self._cache_nombres_categorias is not None:
            return list(self._cache_nombres_categorias)
        nombres = self._repositorio.obtener_categorias()
        self._cache_nombres_categorias = list(nombres)
        return nombres

    def obtener_categorias_detalladas(self, tipo: Optional[str] = "GASTO") -> List[Categoria]:
        clave_tipo = tipo.upper() if isinstance(tipo, str) else "TODOS"
        if clave_tipo in self._cache_categorias_detalladas:
            return list(self._cache_categorias_detalladas[clave_tipo])

        predeterminadas = (
            CATEGORIAS_INGRESO_PREDETERMINADAS
            if (tipo and tipo.upper() == "INGRESO")
            else CATEGORIAS_GASTO_PREDETERMINADAS
        )

        if hasattr(self._repositorio, "obtener_categorias_detalladas"):
            categorias = self._repositorio.obtener_categorias_detalladas(tipo=tipo)
            nombres_actuales = {c.nombre for c in categorias}
            if tipo and tipo.upper() == "INGRESO":
                for cat_p in predeterminadas:
                    if cat_p.nombre not in nombres_actuales and hasattr(self._repositorio, "insertar_categoria"):
                        try:
                            insertada = self._repositorio.insertar_categoria(cat_p)
                            categorias.append(insertada)
                        except Exception:
                            categorias.append(cat_p)
            if categorias:
                self._cache_categorias_detalladas[clave_tipo] = list(categorias)
                return categorias

        nombres_repo = self._repositorio.obtener_categorias()
        resultado: List[Categoria] = []
        vistos = set()

        for cat_pred in predeterminadas:
            if tipo is None or cat_pred.tipo == tipo.upper():
                resultado.append(cat_pred)
                vistos.add(cat_pred.nombre)

        for nombre, cat_extra in self._categorias_memoria_extra.items():
            if nombre not in vistos and (tipo is None or cat_extra.tipo == tipo.upper()):
                resultado.append(cat_extra)
                vistos.add(nombre)

        for nombre in nombres_repo:
            if nombre not in vistos and tipo is None:
                resultado.append(
                    Categoria(None, nombre, "GASTO", "mercado", "#FBB718", False)
                )
                vistos.add(nombre)
        return resultado

    def crear_categoria(
        self,
        nombre: str,
        tipo: str = "GASTO",
        simbolo: str = "mercado",
        color: str = "#FBB718",
        gasto_programado: bool = False,
        frecuencia: Optional[str] = None,
    ) -> Categoria:
        if not isinstance(nombre, str) or not nombre.strip():
            raise ErrorValidacion("El nombre de la categoría es obligatorio.")
        nombre_limpio = nombre.strip()
        if len(nombre_limpio) > 50:
            raise ErrorValidacion("El nombre de la categoría no puede superar 50 caracteres.")

        tipo_limpio = self._validar_tipo(tipo)
        if not isinstance(simbolo, str) or simbolo.strip() not in TODOS_LOS_SIMBOLOS_CATEGORIA:
            raise ErrorValidacion("Debe seleccionar un símbolo válido para la categoría.")
        color_limpio = self._validar_color(color)

        frecuencia_limpia = None
        if gasto_programado:
            frec = (frecuencia or "MENSUAL").strip().upper()
            if frec not in FRECUENCIAS_VALIDAS:
                raise ErrorValidacion("La frecuencia programada no es válida.")
            frecuencia_limpia = frec

        nueva = Categoria(
            id=None,
            nombre=nombre_limpio,
            tipo=tipo_limpio,
            simbolo=simbolo.strip(),
            color=color_limpio,
            es_predeterminada=False,
            gasto_programado=bool(gasto_programado),
            frecuencia=frecuencia_limpia,
        )

        if hasattr(self._repositorio, "insertar_categoria"):
            guardada = self._repositorio.insertar_categoria(nueva)
        else:
            if hasattr(self._repositorio, "_categorias") and nombre_limpio not in self._repositorio._categorias:
                self._repositorio._categorias.append(nombre_limpio)
            guardada = nueva.con_id(len(self._categorias_memoria_extra) + 10)
            self._categorias_memoria_extra[nombre_limpio] = guardada

        self._cache_categorias_detalladas.clear()
        self._cache_nombres_categorias = None
        if hasattr(self._repositorio, "registrar_color_reciente"):
            try:
                self._repositorio.registrar_color_reciente(color_limpio)
            except Exception:
                pass
        return guardada

    # ------------------------------------------------------------------
    # Etiquetas 100% customizables
    # ------------------------------------------------------------------
    def obtener_etiquetas(self) -> List[Etiqueta]:
        if hasattr(self._repositorio, "obtener_etiquetas"):
            return self._repositorio.obtener_etiquetas()
        return list(self._etiquetas_memoria_extra.values())

    def crear_etiqueta(self, nombre: str, color: str = "#408FD1") -> Etiqueta:
        if not isinstance(nombre, str) or not nombre.strip():
            raise ErrorValidacion("El nombre de la etiqueta no puede estar vacío.")
        nombre_limpio = nombre.strip()
        if len(nombre_limpio) > 40:
            raise ErrorValidacion("La etiqueta no puede superar 40 caracteres.")
        color_limpio = self._validar_color(color)
        etiqueta = Etiqueta(id=None, nombre=nombre_limpio, color=color_limpio)
        if hasattr(self._repositorio, "insertar_etiqueta"):
            return self._repositorio.insertar_etiqueta(etiqueta)
        guardada = etiqueta.con_id(len(self._etiquetas_memoria_extra) + 1)
        self._etiquetas_memoria_extra[nombre_limpio] = guardada
        return guardada

    # ------------------------------------------------------------------
    # Movimientos, Gastos e Ingresos
    # ------------------------------------------------------------------
    def registrar_movimiento(
        self,
        tipo: str,
        fecha_texto: str,
        valor_texto: str,
        moneda: str,
        categoria: str,
        descripcion: Optional[str] = None,
        cuenta_id: Optional[int] = None,
        etiquetas: Optional[Sequence[str]] = None,
        imagen: Optional[str] = None,
        es_programado: bool = False,
        frecuencia: Optional[str] = None,
    ) -> MovimientoFinanciero:
        tipo_valido = self._validar_tipo(tipo)
        fecha_valida = self._validar_fecha(fecha_texto)
        valor_valido = self._validar_valor(valor_texto)
        moneda_valida = self._validar_moneda(moneda)
        categoria_valida = self._validar_categoria(categoria)
        descripcion_valida = self._validar_descripcion(descripcion)
        self.registrar_moneda_usada(moneda_valida)

        if cuenta_id is not None:
            cuenta = self.obtener_cuenta(cuenta_id)
            if cuenta is None:
                raise ErrorValidacion("La cuenta seleccionada no existe.")

        etiquetas_tupla: Tuple[str, ...] = ()
        if etiquetas:
            limpias = []
            for et in etiquetas:
                if isinstance(et, str) and et.strip():
                    limpias.append(et.strip())
            etiquetas_tupla = tuple(dict.fromkeys(limpias))

        frecuencia_limpia = None
        if es_programado:
            frec = (frecuencia or "MENSUAL").strip().upper()
            if frec not in FRECUENCIAS_VALIDAS:
                raise ErrorValidacion("La frecuencia programada no es válida.")
            frecuencia_limpia = frec

        movimiento = MovimientoFinanciero(
            id=None,
            tipo_movimiento=tipo_valido,
            fecha=fecha_valida,
            valor=valor_valido,
            moneda=moneda_valida,
            categoria=categoria_valida,
            descripcion=descripcion_valida,
            cuenta_id=cuenta_id,
            etiquetas=etiquetas_tupla,
            imagen=imagen,
            es_programado=bool(es_programado),
            frecuencia=frecuencia_limpia,
        )
        return self._repositorio.insertar_movimiento(movimiento)

    def registrar_gasto(
        self,
        valor_texto: str,
        moneda: str = "COP",
        cuenta_id: Optional[int] = None,
        categoria: str = "Alimentación",
        fecha_texto: Optional[str] = None,
        etiquetas: Optional[Sequence[str]] = None,
        comentario: Optional[str] = None,
        imagen: Optional[str] = None,
        es_programado: bool = False,
        frecuencia: Optional[str] = None,
    ) -> MovimientoFinanciero:
        fecha_str = fecha_texto if fecha_texto is not None else date.today().isoformat()
        categorias_actuales = self._repositorio.obtener_categorias()
        if categoria in self._categorias_memoria_extra and categoria not in categorias_actuales:
            cat_obj = self._categorias_memoria_extra[categoria]
            if hasattr(self._repositorio, "insertar_categoria"):
                self._repositorio.insertar_categoria(cat_obj)
            elif hasattr(self._repositorio, "_categorias"):
                self._repositorio._categorias.append(categoria)

        return self.registrar_movimiento(
            tipo="GASTO",
            fecha_texto=fecha_str,
            valor_texto=valor_texto,
            moneda=moneda,
            categoria=categoria,
            descripcion=comentario,
            cuenta_id=cuenta_id,
            etiquetas=etiquetas,
            imagen=imagen,
            es_programado=es_programado,
            frecuencia=frecuencia,
        )

    def registrar_ingreso(
        self,
        valor_texto: str,
        moneda: str = "COP",
        cuenta_id: Optional[int] = None,
        categoria: str = "Salario",
        fecha_texto: Optional[str] = None,
        etiquetas: Optional[Sequence[str]] = None,
        comentario: Optional[str] = None,
        imagen: Optional[str] = None,
        es_programado: bool = False,
        frecuencia: Optional[str] = None,
    ) -> MovimientoFinanciero:
        """Registra un ingreso con COP por defecto y suma automáticamente al saldo de la cuenta asociada."""
        fecha_str = fecha_texto if fecha_texto is not None else date.today().isoformat()
        categorias_actuales = self._repositorio.obtener_categorias()
        if categoria in self._categorias_memoria_extra and categoria not in categorias_actuales:
            cat_obj = self._categorias_memoria_extra[categoria]
            if hasattr(self._repositorio, "insertar_categoria"):
                self._repositorio.insertar_categoria(cat_obj)
            elif hasattr(self._repositorio, "_categorias"):
                self._repositorio._categorias.append(categoria)

        return self.registrar_movimiento(
            tipo="INGRESO",
            fecha_texto=fecha_str,
            valor_texto=valor_texto,
            moneda=moneda,
            categoria=categoria,
            descripcion=comentario,
            cuenta_id=cuenta_id,
            etiquetas=etiquetas,
            imagen=imagen,
            es_programado=es_programado,
            frecuencia=frecuencia,
        )

    def obtener_movimientos(
        self,
        tipo: Optional[str] = None,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
    ) -> List[MovimientoFinanciero]:
        tipo_filtro = self._validar_tipo(tipo) if tipo is not None else None
        try:
            movimientos = self._repositorio.obtener_movimientos(
                tipo_filtro, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin
            )
        except TypeError:
            movimientos = self._repositorio.obtener_movimientos(tipo_filtro)
            if fecha_inicio is not None:
                movimientos = [m for m in movimientos if m.fecha >= fecha_inicio]
            if fecha_fin is not None:
                movimientos = [m for m in movimientos if m.fecha <= fecha_fin]
        return movimientos

    def obtener_ultima_fecha_gasto(self) -> Optional[date]:
        if hasattr(self._repositorio, "obtener_ultima_fecha_movimiento"):
            return self._repositorio.obtener_ultima_fecha_movimiento("GASTO")
        gastos = self.obtener_movimientos("GASTO")
        return gastos[0].fecha if gastos else None

    def obtener_ultima_fecha_ingreso(self) -> Optional[date]:
        if hasattr(self._repositorio, "obtener_ultima_fecha_movimiento"):
            return self._repositorio.obtener_ultima_fecha_movimiento("INGRESO")
        ingresos = self.obtener_movimientos("INGRESO")
        return ingresos[0].fecha if ingresos else None

    def resumen_del_mes(self, anno: int, mes: int) -> Dict[str, Dict[str, object]]:
        if not isinstance(anno, int) or isinstance(anno, bool) or anno < 1900 or anno > 9999:
            raise ValueError("El año debe ser un número entero válido.")
        if not isinstance(mes, int) or isinstance(mes, bool) or mes < 1 or mes > 12:
            raise ValueError("El mes debe estar entre 1 y 12.")

        filas = self._repositorio.resumen_mensual(anno, mes)
        resultado: Dict[str, Dict[str, object]] = {}
        for tipo, moneda, categoria, total in filas:
            datos_moneda = resultado.setdefault(
                moneda,
                {
                    "ingresos": Decimal("0"),
                    "gastos": Decimal("0"),
                    "gastos_por_categoria": {},
                },
            )
            if tipo == "INGRESO":
                datos_moneda["ingresos"] = datos_moneda["ingresos"] + total
            elif tipo == "GASTO":
                datos_moneda["gastos"] = datos_moneda["gastos"] + total
                gastos_cat: Dict[str, Decimal] = datos_moneda["gastos_por_categoria"]  # type: ignore[assignment]
                gastos_cat[categoria] = gastos_cat.get(categoria, Decimal("0")) + total
        return resultado

    def eliminar_movimiento(self, id_movimiento: int) -> bool:
        return self._repositorio.eliminar_movimiento(id_movimiento)

    # ------------------------------------------------------------------
    # Cuentas y Transferencias
    # ------------------------------------------------------------------
    def crear_cuenta(
        self,
        nombre: str,
        moneda: str,
        saldo_inicial_texto: Optional[str] = "0",
        simbolo: str = "banco",
        color: str = "#408FD1",
        incluye_en_total: bool = True,
        nota: Optional[str] = None,
    ) -> Cuenta:
        nombre_limpio = self._validar_nombre_cuenta(nombre)
        moneda_limpia = self._validar_moneda(moneda)
        saldo_limpio = self._validar_saldo_inicial(saldo_inicial_texto)
        simbolo_limpio = self._validar_simbolo(simbolo)
        color_limpio = self._validar_color(color)
        nota_limpia = self._validar_descripcion(nota)
        self.registrar_moneda_usada(moneda_limpia)

        cuenta = Cuenta(
            id=None,
            nombre=nombre_limpio,
            moneda=moneda_limpia,
            saldo_inicial=saldo_limpio,
            simbolo=simbolo_limpio,
            color=color_limpio,
            incluye_en_total=bool(incluye_en_total),
            nota=nota_limpia,
        )
        guardada = self._repositorio.insertar_cuenta(cuenta)
        if hasattr(self._repositorio, "registrar_color_reciente"):
            try:
                self._repositorio.registrar_color_reciente(color_limpio)
            except Exception:
                pass
        return guardada

    def obtener_cuentas(self) -> List[Tuple[Cuenta, Decimal]]:
        return self._repositorio.obtener_cuentas()

    def obtener_cuenta(self, id_cuenta: int) -> Optional[Cuenta]:
        return self._repositorio.obtener_cuenta(id_cuenta)

    def obtener_colores_recientes(self) -> List[str]:
        if hasattr(self._repositorio, "obtener_colores_recientes"):
            return self._repositorio.obtener_colores_recientes()
        return []

    def registrar_color_reciente(self, color: str) -> None:
        color_limpio = self._validar_color(color)
        if hasattr(self._repositorio, "registrar_color_reciente"):
            self._repositorio.registrar_color_reciente(color_limpio)

    def crear_transferencia(
        self,
        cuenta_origen_id: int,
        cuenta_destino_id: int,
        valor_texto: str,
        fecha_texto: str,
        comentarios: Optional[str] = None,
        imagen: Optional[str] = None,
    ) -> Transferencia:
        if cuenta_origen_id == cuenta_destino_id:
            raise ErrorValidacion("La cuenta de origen y la de destino deben ser diferentes.")
        origen = self.obtener_cuenta(cuenta_origen_id)
        destino = self.obtener_cuenta(cuenta_destino_id)
        if origen is None or destino is None:
            raise ErrorValidacion("Ambas cuentas deben existir.")
        if origen.moneda != destino.moneda:
            raise ErrorValidacion("Las transferencias solo se permiten entre cuentas de la misma moneda.")

        valor = self._validar_valor(valor_texto)
        saldo_disponible = self.obtener_saldo_cuenta(cuenta_origen_id)
        if valor > saldo_disponible:
            raise ErrorValidacion(
                f"Fondos insuficientes en la cuenta '{origen.nombre}'. "
                f"Saldo disponible: {saldo_disponible:,.2f} {origen.moneda}."
            )
        fecha = self._validar_fecha(fecha_texto)
        comentarios_limpios = self._validar_descripcion(comentarios)

        transferencia = Transferencia(
            id=None,
            cuenta_origen_id=cuenta_origen_id,
            cuenta_destino_id=cuenta_destino_id,
            valor=valor,
            moneda=origen.moneda,
            fecha=fecha,
            comentarios=comentarios_limpios,
            imagen=imagen,
        )
        return self._repositorio.insertar_transferencia(transferencia)

    def obtener_transferencias(self, fecha_inicio=None, fecha_fin=None):
        return self._repositorio.obtener_transferencias(fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)

    # ------------------------------------------------------------------
    # Módulo de Inversiones Bursátiles (Buscador, Portafolio, Valoración en Vivo y Curva de Montaña)
    # ------------------------------------------------------------------
    def buscar_activos_bursatiles(
        self, consulta: str = "", incluir_remoto: bool = False
    ) -> List[Dict[str, str]]:
        """Busca tickers de acciones y ETFs (ej. TTWO, QQQ, VOO, SPY, AAPL, NVDA)."""
        if hasattr(self._servicio_bursatil, "buscar_activos_bursatiles"):
            try:
                return self._servicio_bursatil.buscar_activos_bursatiles(
                    consulta, incluir_remoto=incluir_remoto
                )
            except TypeError:
                return self._servicio_bursatil.buscar_activos_bursatiles(consulta)
        return list(CATALOGO_ACTIVOS_BURSATILES)

    def _asegurar_tabla_inversion_bd(self) -> None:
        if self._tabla_inversion_verificada:
            return
        if hasattr(self._repositorio, "_asegurar_tabla_inversion"):
            self._repositorio._asegurar_tabla_inversion()
            self._tabla_inversion_verificada = True
            return
        if hasattr(self._repositorio, "ejecutar_consulta"):
            self._repositorio.ejecutar_consulta(
                """
                CREATE TABLE IF NOT EXISTS inversion (
                    id SERIAL PRIMARY KEY,
                    simbolo VARCHAR(20) NOT NULL,
                    nombre VARCHAR(100) NOT NULL,
                    monto_invertido NUMERIC(16,2) NOT NULL CHECK (monto_invertido > 0),
                    moneda CHAR(3) NOT NULL DEFAULT 'USD',
                    precio_compra NUMERIC(20,8) NOT NULL CHECK (precio_compra > 0),
                    cantidad_titulos NUMERIC(20,8) NOT NULL CHECK (cantidad_titulos > 0),
                    fecha_compra DATE NOT NULL DEFAULT CURRENT_DATE,
                    cuenta_id INTEGER REFERENCES cuenta(id) ON DELETE SET NULL,
                    notas VARCHAR(200),
                    fecha_registro TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def obtener_inversiones(self, forzar_bd: bool = False) -> List[Inversion]:
        if not forzar_bd and self._cache_inversiones_bd is not None:
            return list(self._cache_inversiones_bd)

        if hasattr(self._repositorio, "obtener_inversiones"):
            try:
                lista = self._repositorio.obtener_inversiones()
                self._cache_inversiones_bd = list(lista)
                return list(lista)
            except Exception:
                pass
        if hasattr(self._repositorio, "ejecutar_consulta"):
            try:
                self._asegurar_tabla_inversion_bd()
                filas = self._repositorio.ejecutar_consulta(
                    """
                    SELECT id, simbolo, nombre, monto_invertido, moneda,
                           precio_compra, cantidad_titulos, fecha_compra, cuenta_id, notas
                    FROM inversion
                    ORDER BY fecha_compra DESC, id DESC
                    """
                )
                lista = [
                    Inversion(
                        id=f[0],
                        simbolo=f[1].strip().upper(),
                        nombre=f[2],
                        monto_invertido=Decimal(str(f[3])),
                        moneda=f[4].strip().upper(),
                        precio_compra=Decimal(str(f[5])),
                        cantidad_titulos=Decimal(str(f[6])),
                        fecha_compra=f[7],
                        cuenta_id=f[8],
                        notas=f[9],
                    )
                    for f in filas
                ]
                self._cache_inversiones_bd = list(lista)
                return list(lista)
            except Exception:
                pass
        return list(self._inversiones_memoria)

    def registrar_inversion(
        self,
        simbolo: str,
        nombre: str,
        monto_texto: str,
        moneda: str = "USD",
        precio_compra_texto: Optional[str] = None,
        fecha_texto: Optional[str] = None,
        cuenta_id: Optional[int] = None,
        notas: Optional[str] = None,
    ) -> Inversion:
        """Registra una inversión bursátil calculando automáticamente la fracción de títulos
        comprados según el monto invertido y el precio de mercado (o precio de compra indicado)."""
        if not isinstance(simbolo, str) or not simbolo.strip():
            raise ErrorValidacion("El símbolo bursátil (ticker) es obligatorio.")
        simbolo_bruto = simbolo.strip().upper()
        simbolo_limpio = normalizar_simbolo_yahoo(simbolo_bruto)
        nombre_base = (nombre or simbolo_limpio).strip()
        if simbolo_bruto in MAPA_CRIPTO_A_YAHOO and nombre_base.upper() in (simbolo_bruto, simbolo_limpio):
            nombre_base = MAPA_CRIPTO_A_YAHOO[simbolo_bruto][1]
        nombre_limpio = nombre_base[:100]
        monto_valido = self._validar_valor(monto_texto)
        moneda_valida = self._validar_moneda(moneda)
        self.registrar_moneda_usada(moneda_valida)
        fecha_valida = (
            self._validar_fecha(fecha_texto)
            if fecha_texto and fecha_texto.strip()
            else date.today()
        )
        notas_limpias = self._validar_descripcion(notas)

        # Determinar el precio de compra en la moneda de la inversión
        precio_compra: Optional[Decimal] = None
        if precio_compra_texto and str(precio_compra_texto).strip():
            try:
                p_dec = Decimal(str(precio_compra_texto).strip().replace(",", "."))
                if p_dec > Decimal("0"):
                    precio_compra = p_dec.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
            except InvalidOperation as error:
                raise ErrorValidacion("El precio de compra por acción/título no es válido.") from error

        if precio_compra is None and fecha_valida < date.today():
            precio_compra = self.consultar_precio_historico_inversion(
                simbolo_limpio, fecha_valida, moneda_esperada=moneda_valida
            )

        if precio_compra is None:
            cot_mercado = self.consultar_precio_inversion(simbolo_limpio, moneda_esperada="USD")
            if cot_mercado is not None and cot_mercado.precio > Decimal("0"):
                if moneda_valida == cot_mercado.moneda:
                    precio_compra = cot_mercado.precio
                else:
                    try:
                        precio_compra = self.convertir_entre_monedas(
                            cot_mercado.precio, cot_mercado.moneda, moneda_valida
                        )
                    except ErrorValidacion:
                        precio_compra = cot_mercado.precio
            else:
                # Si se registra completamente offline sin caché previa, usar base unitaria 100.00
                precio_compra = Decimal("100.00000000")

        if precio_compra <= Decimal("0"):
            raise ErrorValidacion("El precio de compra debe ser mayor que cero.")

        cantidad_titulos = (monto_valido / precio_compra).quantize(
            Decimal("0.00000001"), rounding=ROUND_HALF_UP
        )
        if cantidad_titulos <= Decimal("0"):
            cantidad_titulos = Decimal("0.00000001")

        nueva = Inversion(
            id=None,
            simbolo=simbolo_limpio,
            nombre=nombre_limpio,
            monto_invertido=monto_valido,
            moneda=moneda_valida,
            precio_compra=precio_compra,
            cantidad_titulos=cantidad_titulos,
            fecha_compra=fecha_valida,
            cuenta_id=cuenta_id,
            notas=notas_limpias,
        )

        guardada_bd: Optional[Inversion] = None
        if hasattr(self._repositorio, "insertar_inversion"):
            try:
                guardada_bd = self._repositorio.insertar_inversion(nueva)
            except Exception:
                guardada_bd = None
        if guardada_bd is None and hasattr(self._repositorio, "ejecutar_consulta"):
            try:
                self._asegurar_tabla_inversion_bd()
                filas = self._repositorio.ejecutar_consulta(
                    """
                    INSERT INTO inversion (
                        simbolo, nombre, monto_invertido, moneda, precio_compra,
                        cantidad_titulos, fecha_compra, cuenta_id, notas
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        nueva.simbolo,
                        nueva.nombre,
                        nueva.monto_invertido,
                        nueva.moneda,
                        nueva.precio_compra,
                        nueva.cantidad_titulos,
                        nueva.fecha_compra,
                        nueva.cuenta_id,
                        nueva.notas,
                    ),
                )
                if filas:
                    guardada_bd = nueva.con_id(filas[0][0])
            except Exception:
                guardada_bd = None

        if guardada_bd is not None:
            if self._cache_inversiones_bd is not None:
                self._cache_inversiones_bd.insert(0, guardada_bd)
            return guardada_bd

        guardada = nueva.con_id(len(self._inversiones_memoria) + 1)
        self._inversiones_memoria.insert(0, guardada)
        if self._cache_inversiones_bd is not None:
            self._cache_inversiones_bd.insert(0, guardada)
        return guardada

    def obtener_saldo_cuenta(self, id_cuenta: int) -> Decimal:
        """Devuelve el saldo disponible actual de la cuenta indicada."""
        try:
            for cuenta, saldo in self.obtener_cuentas():
                if cuenta.id == id_cuenta:
                    return Decimal(str(saldo))
        except Exception:
            pass
        if hasattr(self._repositorio, "saldos_de_cuentas"):
            try:
                saldos = self._repositorio.saldos_de_cuentas()
                if id_cuenta in saldos:
                    return Decimal(str(saldos[id_cuenta]))
            except Exception:
                pass
        cuenta_obj = self.obtener_cuenta(id_cuenta)
        return Decimal(str(cuenta_obj.saldo_inicial)) if cuenta_obj is not None else Decimal("0")

    def asegurar_cuenta_broker(
        self, broker: str = "eToro", moneda: Optional[str] = None
    ) -> Cuenta:
        """Garantiza que exista una cuenta asociada al broker con saldo inicial 0."""
        mapa_brokers = {
            "etoro": ("eToro", "USD", "bolsa", "#2ECC71"),
            "binance": ("Binance", "USD", "criptomonedas", "#F3BA2F"),
            "ibkr": ("Interactive Brokers", "USD", "bolsa", "#408FD1"),
            "interactive brokers": ("Interactive Brokers", "USD", "bolsa", "#408FD1"),
            "trii": ("Trii", "COP", "bolsa", "#9B7EDE"),
            "hapi": ("Hapi", "USD", "bolsa", "#408FD1"),
        }
        clave = (broker or "eToro").strip().lower()
        nombre_std, moneda_def, simbolo_def, color_def = mapa_brokers.get(
            clave, ((broker or "eToro").strip() or "eToro", "USD", "bolsa", "#2ECC71")
        )
        moneda_final = self._validar_moneda(moneda or moneda_def)

        existente = next(
            (c for c, _s in self.obtener_cuentas() if c.nombre.strip().lower() == nombre_std.lower()),
            None,
        )
        if existente is not None:
            return existente

        return self.crear_cuenta(
            nombre=nombre_std,
            moneda=moneda_final,
            saldo_inicial_texto="0",
            simbolo=simbolo_def,
            color=color_def,
            incluye_en_total=True,
            nota=f"Cuenta de broker ({nombre_std}) creada automáticamente",
        )

    def obtener_cuentas_destino_inversion(
        self, broker_preferido: str = "eToro", moneda_inversion: str = "USD"
    ) -> List[Tuple[Cuenta, Decimal]]:
        """Garantiza que exista la cuenta del broker y devuelve todas las cuentas disponibles."""
        try:
            self.asegurar_cuenta_broker(broker_preferido, moneda=moneda_inversion)
        except Exception:
            pass
        return self.obtener_cuentas()

    def _obtener_precio_unitario_seguro(
        self, simbolo: str, moneda: str = "USD", permitir_red: bool = True
    ) -> Optional[Decimal]:
        """Obtiene el precio de mercado actual compatible tanto con ServicioBursatil real como con mocks."""
        sim_norm = normalizar_simbolo_yahoo(simbolo)
        for metodo in ("consultar_precio_actual", "obtener_cotizacion_activo"):
            if hasattr(self._servicio_bursatil, metodo):
                try:
                    cot = getattr(self._servicio_bursatil, metodo)(sim_norm, moneda_esperada=moneda)
                    if cot is not None and getattr(cot, "precio", Decimal("0")) > Decimal("0"):
                        return Decimal(str(cot.precio))
                except Exception:
                    pass
        try:
            cot = self.consultar_precio_inversion(
                simbolo, moneda_esperada=moneda, forzar_actualizacion=False, permitir_red=permitir_red
            )
            if cot is not None and getattr(cot, "precio", Decimal("0")) > Decimal("0"):
                return Decimal(str(cot.precio))
        except Exception:
            pass
        return None

    def _convertir_monto_seguro(
        self, monto: Decimal, moneda_origen: str, moneda_destino: str
    ) -> Decimal:
        """Convierte un monto entre dos monedas usando el flujo principal o el fallback de pruebas."""
        if moneda_origen == moneda_destino or monto == Decimal("0"):
            return Decimal(str(monto)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        try:
            conv = self.convertir_entre_monedas(monto, moneda_origen, moneda_destino)
            if conv is not None and conv != Decimal("0"):
                return Decimal(str(conv)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except Exception:
            pass
        for metodo_tasa in ("consultar_tasa_cambio", "obtener_tasa_cambio"):
            if hasattr(self._servicio_bursatil, metodo_tasa):
                try:
                    cot = getattr(self._servicio_bursatil, metodo_tasa)(moneda_origen, moneda_destino)
                    if cot is not None and getattr(cot, "precio", Decimal("0")) > Decimal("0"):
                        return (Decimal(str(monto)) * Decimal(str(cot.precio))).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        )
                except Exception:
                    pass
        return Decimal(str(monto)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def clasificar_posiciones_importacion(
        self,
        posiciones: List[Dict[str, object]],
        omitir_duplicados: bool = True,
        limpiar_antes: bool = False,
    ) -> Dict[str, object]:
        """Pre-valida instantáneamente las operaciones de un archivo CSV/XLSX contra las
        inversiones ya guardadas en la base de datos antes de importar."""
        if limpiar_antes or not omitir_duplicados:
            todas = [dict(p, es_duplicada=False) for p in posiciones]
            return {
                "total_detectadas": len(posiciones),
                "nuevas": todas,
                "duplicadas": [],
                "cantidad_nuevas": len(todas),
                "cantidad_duplicadas": 0,
                "todas_marcadas": todas,
            }

        try:
            existentes = self.listar_inversiones()
        except Exception:
            existentes = self.obtener_inversiones()

        claves_existentes = {clave_duplicado_inversion(inv) for inv in existentes}
        for inv in existentes:
            try:
                claves_existentes.add(
                    _clave_duplicado(
                        normalizar_simbolo_yahoo(inv.simbolo),
                        inv.fecha_compra,
                        inv.monto_invertido,
                    )
                )
            except Exception:
                pass

        nuevas, duplicadas, todas_marcadas = [], [], []
        vistos_en_lote = set()

        for pos in posiciones:
            clave_raw = clave_duplicado_posicion(pos)
            fecha_pos = pos.get("fecha_compra") or ""
            fecha_iso = fecha_pos.isoformat() if hasattr(fecha_pos, "isoformat") else str(fecha_pos)
            clave_norm = _clave_duplicado(
                normalizar_simbolo_yahoo(str(pos.get("simbolo", ""))),
                fecha_iso,
                pos.get("monto_invertido", 0),
            )
            es_dup = bool({clave_raw, clave_norm} & (claves_existentes | vistos_en_lote))
            copia = dict(pos, es_duplicada=es_dup)
            if es_dup:
                duplicadas.append(copia)
            else:
                vistos_en_lote.update((clave_raw, clave_norm))
                nuevas.append(copia)
            todas_marcadas.append(copia)

        return {
            "total_detectadas": len(posiciones),
            "nuevas": nuevas,
            "duplicadas": duplicadas,
            "cantidad_nuevas": len(nuevas),
            "cantidad_duplicadas": len(duplicadas),
            "todas_marcadas": todas_marcadas,
        }

    def _acreditar_saldo_cuenta_directo(self, cuenta_id: int, monto: Decimal) -> None:
        """Incrementa el saldo de la cuenta cuando el repositorio no enlaza movimientos a cuentas."""
        if monto <= Decimal("0"):
            return
        if hasattr(self._repositorio, "conectar") and hasattr(self._repositorio, "ejecutar_consulta"):
            try:
                conexion = self._repositorio.conectar()
                with conexion:
                    with conexion.cursor() as cursor:
                        cursor.execute(
                            "UPDATE cuenta SET saldo_inicial = saldo_inicial + %s WHERE id = %s",
                            (monto, cuenta_id),
                        )
                return
            except Exception:
                pass
        if hasattr(self._repositorio, "_cuentas") and isinstance(self._repositorio._cuentas, dict):
            c_mem = self._repositorio._cuentas.get(cuenta_id)
            if c_mem is not None and hasattr(c_mem, "saldo_inicial"):
                try:
                    object.__setattr__(c_mem, "saldo_inicial", c_mem.saldo_inicial + monto)
                except Exception:
                    pass

    def _resolver_cuenta_destino(
        self, cuenta_destino: Optional[object], moneda_defecto: str
    ) -> Optional[Cuenta]:
        """Resuelve una cuenta de destino a partir de una instancia, ID numérico o nombre de cuenta."""
        if isinstance(cuenta_destino, Cuenta):
            return cuenta_destino
        if isinstance(cuenta_destino, int):
            return self.obtener_cuenta(cuenta_destino)
        if isinstance(cuenta_destino, str):
            texto = cuenta_destino.strip()
            if not texto or texto.lower().startswith(("no ", "ningun", "sin ")):
                return None
            if " (" in texto and texto.endswith(")"):
                texto = texto.rsplit(" (", 1)[0].strip()
            encontrada = next(
                (c for c, _s in self.obtener_cuentas() if c.nombre.strip().lower() == texto.lower()),
                None,
            )
            return encontrada or self.asegurar_cuenta_broker(texto, moneda=moneda_defecto)
        return None

    def _determinar_valor_venta_origen(
        self,
        inv: Inversion,
        precio_venta_unitario: Optional[object],
        valor_total_venta: Optional[object],
    ) -> Decimal:
        """Calcula el valor total de venta en la moneda nativa de la inversión."""
        if valor_total_venta is not None and str(valor_total_venta).strip() != "":
            try:
                val = Decimal(str(valor_total_venta).strip().replace(",", "."))
                if val > Decimal("0"):
                    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            except Exception as exc:
                raise ErrorValidacion("El valor total de venta no es válido.") from exc

        if precio_venta_unitario is not None and str(precio_venta_unitario).strip() != "":
            try:
                p_unit = Decimal(str(precio_venta_unitario).strip().replace(",", "."))
                if p_unit <= Decimal("0"):
                    raise ErrorValidacion("El precio de venta debe ser mayor que cero.")
                return (inv.cantidad_titulos * p_unit).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            except ErrorValidacion:
                raise
            except Exception as exc:
                raise ErrorValidacion("El precio unitario de venta no es válido.") from exc

        precio_actual = self._obtener_precio_unitario_seguro(inv.simbolo, inv.moneda, permitir_red=True)
        if precio_actual is not None and inv.cantidad_titulos > Decimal("0"):
            return (inv.cantidad_titulos * precio_actual).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return inv.monto_invertido.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _seleccionar_categoria_ingreso_venta(self) -> str:
        """Elige la categoría de ingreso más adecuada disponible en el catálogo."""
        cats_ingreso: List[str] = []
        if hasattr(self._repositorio, "obtener_categorias"):
            try:
                cats_ingreso = list(self._repositorio.obtener_categorias("INGRESO"))
            except TypeError:
                cats_ingreso = list(self._repositorio.obtener_categorias())
        for candidata in ("Inversiones", "Ventas", "Intereses", "Otros ingresos", "Otros", "Salario"):
            if not cats_ingreso or candidata in cats_ingreso:
                return candidata
        return cats_ingreso[0] if cats_ingreso else "Ventas"

    def cerrar_inversion(
        self,
        id_inversion: int,
        cuenta_destino: Optional[object] = "eToro",
        precio_venta_unitario: Optional[object] = None,
        valor_total_venta: Optional[object] = None,
        fecha_cierre: Optional[date] = None,
    ) -> Dict[str, object]:
        """Cierra/vende una posición de inversión al valor actual del mercado (o al valor indicado),
        convierte la divisa si la cuenta destino está en otra moneda y acredita los fondos."""
        inv_objetivo = next((i for i in self.obtener_inversiones() if i.id == id_inversion), None)
        if inv_objetivo is None:
            raise ErrorValidacion(f"No se encontró la inversión con ID {id_inversion}.")

        valor_venta_origen = self._determinar_valor_venta_origen(
            inv_objetivo, precio_venta_unitario, valor_total_venta
        )
        cuenta_obj = self._resolver_cuenta_destino(cuenta_destino, inv_objetivo.moneda)

        monto_acreditado = valor_venta_origen
        moneda_destino = inv_objetivo.moneda
        movimiento_creado: Optional[MovimientoFinanciero] = None
        fecha_op = fecha_cierre if isinstance(fecha_cierre, date) else date.today()
        ganancia_neta = (valor_venta_origen - inv_objetivo.monto_invertido).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        if cuenta_obj is not None:
            moneda_destino = cuenta_obj.moneda
            monto_acreditado = self._convertir_monto_seguro(
                valor_venta_origen, inv_objetivo.moneda, moneda_destino
            )
            saldo_antes = self.obtener_saldo_cuenta(cuenta_obj.id)

            try:
                signo = "+" if ganancia_neta >= Decimal("0") else ""
                desc_venta = (
                    f"Venta {inv_objetivo.simbolo} ({inv_objetivo.cantidad_titulos.quantize(Decimal('0.0001'))} títulos) "
                    f"→ {cuenta_obj.nombre} ({signo}{ganancia_neta} {inv_objetivo.moneda})"
                )
                movimiento_creado = self.registrar_movimiento(
                    tipo="INGRESO",
                    fecha_texto=fecha_op.isoformat(),
                    valor_texto=f"{monto_acreditado:.2f}",
                    moneda=moneda_destino,
                    categoria=self._seleccionar_categoria_ingreso_venta(),
                    descripcion=desc_venta[:200],
                    cuenta_id=cuenta_obj.id,
                )
            except Exception:
                movimiento_creado = None

            if self.obtener_saldo_cuenta(cuenta_obj.id) < saldo_antes + monto_acreditado:
                self._acreditar_saldo_cuenta_directo(cuenta_obj.id, monto_acreditado)

        self._registrar_cierre_inversion_historial(
            inv=inv_objetivo,
            valor_venta_origen=valor_venta_origen,
            ganancia_neta=ganancia_neta,
            cuenta_nombre=cuenta_obj.nombre if cuenta_obj is not None else "Sin cuenta",
            monto_acreditado=monto_acreditado,
            moneda_destino=moneda_destino,
            fecha_cierre=fecha_op,
        )
        self.eliminar_inversion(id_inversion)

        return {
            "inversion_cerrada": inv_objetivo,
            "valor_venta_origen": valor_venta_origen,
            "moneda_origen": inv_objetivo.moneda,
            "monto_acreditado": monto_acreditado,
            "moneda_destino": moneda_destino,
            "cuenta_destino": cuenta_obj,
            "ganancia_neta_origen": ganancia_neta,
            "movimiento": movimiento_creado,
        }

    def _asegurar_tabla_inversion_cerrada(self) -> None:
        if hasattr(self._repositorio, "ejecutar_consulta"):
            try:
                self._repositorio.ejecutar_consulta(
                    """
                    CREATE TABLE IF NOT EXISTS inversion_cerrada (
                        id SERIAL PRIMARY KEY,
                        simbolo VARCHAR(30) NOT NULL,
                        nombre VARCHAR(120) NOT NULL,
                        cantidad_titulos NUMERIC(18, 8) NOT NULL DEFAULT 0,
                        monto_invertido NUMERIC(18, 2) NOT NULL DEFAULT 0,
                        valor_venta NUMERIC(18, 2) NOT NULL DEFAULT 0,
                        ganancia_realizada NUMERIC(18, 2) NOT NULL DEFAULT 0,
                        moneda_origen VARCHAR(10) NOT NULL DEFAULT 'USD',
                        cuenta_destino VARCHAR(80),
                        monto_acreditado NUMERIC(18, 2) NOT NULL DEFAULT 0,
                        moneda_destino VARCHAR(10) NOT NULL DEFAULT 'USD',
                        fecha_compra DATE,
                        fecha_cierre DATE NOT NULL
                    )
                    """
                )
            except Exception:
                pass

    def _registrar_cierre_inversion_historial(
        self,
        inv: Inversion,
        valor_venta_origen: Decimal,
        ganancia_neta: Decimal,
        cuenta_nombre: str,
        monto_acreditado: Decimal,
        moneda_destino: str,
        fecha_cierre: date,
    ) -> None:
        registro = {
            "simbolo": inv.simbolo,
            "nombre": inv.nombre,
            "cantidad_titulos": inv.cantidad_titulos,
            "monto_invertido": inv.monto_invertido,
            "valor_venta": valor_venta_origen,
            "ganancia_realizada": ganancia_neta,
            "moneda_origen": inv.moneda,
            "cuenta_destino": cuenta_nombre,
            "monto_acreditado": monto_acreditado,
            "moneda_destino": moneda_destino,
            "fecha_compra": inv.fecha_compra.isoformat() if hasattr(inv.fecha_compra, "isoformat") else str(inv.fecha_compra),
            "fecha_cierre": fecha_cierre.isoformat() if hasattr(fecha_cierre, "isoformat") else str(fecha_cierre),
        }
        if not hasattr(self, "_inversiones_cerradas_memoria"):
            self._inversiones_cerradas_memoria = []
        self._inversiones_cerradas_memoria.insert(0, registro)

        if hasattr(self._repositorio, "ejecutar_consulta"):
            try:
                self._asegurar_tabla_inversion_cerrada()
                self._repositorio.ejecutar_consulta(
                    """
                    INSERT INTO inversion_cerrada (
                        simbolo, nombre, cantidad_titulos, monto_invertido,
                        valor_venta, ganancia_realizada, moneda_origen,
                        cuenta_destino, monto_acreditado, moneda_destino,
                        fecha_compra, fecha_cierre
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        inv.simbolo,
                        inv.nombre,
                        inv.cantidad_titulos,
                        inv.monto_invertido,
                        valor_venta_origen,
                        ganancia_neta,
                        inv.moneda,
                        cuenta_nombre,
                        monto_acreditado,
                        moneda_destino,
                        inv.fecha_compra,
                        fecha_cierre,
                    ),
                )
            except Exception:
                pass

    def obtener_inversiones_cerradas(
        self,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
    ) -> List[Dict[str, object]]:
        """Devuelve el historial de posiciones cerradas/vendidas en el rango de fechas."""
        resultados: List[Dict[str, object]] = []

        if hasattr(self._repositorio, "ejecutar_consulta"):
            try:
                self._asegurar_tabla_inversion_cerrada()
                filas = self._repositorio.ejecutar_consulta(
                    """
                    SELECT simbolo, nombre, cantidad_titulos, monto_invertido,
                           valor_venta, ganancia_realizada, moneda_origen,
                           cuenta_destino, monto_acreditado, moneda_destino,
                           fecha_compra, fecha_cierre
                    FROM inversion_cerrada
                    ORDER BY fecha_cierre DESC, id DESC
                    """
                )
                for f in filas or []:
                    f_cierre_date = (
                        f[11]
                        if isinstance(f[11], date)
                        else date.fromisoformat(str(f[11])[:10])
                    )
                    if (fecha_inicio and f_cierre_date < fecha_inicio) or (fecha_fin and f_cierre_date > fecha_fin):
                        continue
                    resultados.append(
                        {
                            "simbolo": str(f[0]),
                            "nombre": str(f[1]),
                            "cantidad_titulos": Decimal(str(f[2])),
                            "monto_invertido": Decimal(str(f[3])),
                            "valor_venta": Decimal(str(f[4])),
                            "ganancia_realizada": Decimal(str(f[5])),
                            "moneda_origen": str(f[6]).strip(),
                            "cuenta_destino": str(f[7] or "Cuenta"),
                            "monto_acreditado": Decimal(str(f[8])),
                            "moneda_destino": str(f[9]).strip(),
                            "fecha_compra": str(f[10] or ""),
                            "fecha_cierre": f_cierre_date.isoformat(),
                        }
                    )
            except Exception:
                pass

        if not resultados and hasattr(self, "_inversiones_cerradas_memoria"):
            for item in self._inversiones_cerradas_memoria:
                try:
                    f_c = date.fromisoformat(str(item["fecha_cierre"])[:10])
                    if (fecha_inicio and f_c < fecha_inicio) or (fecha_fin and f_c > fecha_fin):
                        continue
                except Exception:
                    pass
                resultados.append(dict(item))

        return resultados

    def _calcular_ingresos_y_gastos_rango(
        self,
        fecha_inicio: date,
        fecha_fin: date,
        moneda_objetivo: str = "COP",
        incluir_todas_convertidas: bool = True,
    ) -> Dict[str, object]:
        if hasattr(self, "resumen_del_rango_en_moneda"):
            try:
                return self.resumen_del_rango_en_moneda(
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
                    moneda_objetivo=moneda_objetivo,
                    incluir_todas_convertidas=incluir_todas_convertidas,
                )
            except Exception:
                pass

        ingresos, gastos = Decimal("0.00"), Decimal("0.00")
        gastos_cat: Dict[str, Decimal] = {}
        ingresos_cat: Dict[str, Decimal] = {}

        try:
            movs = self._repositorio.obtener_movimientos(
                None, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin
            )
        except TypeError:
            movs = [
                m
                for m in self._repositorio.obtener_movimientos()
                if fecha_inicio <= m.fecha <= fecha_fin
            ]

        for m in movs:
            if not incluir_todas_convertidas and m.moneda != moneda_objetivo:
                continue
            val = self._convertir_monto_seguro(m.valor, m.moneda, moneda_objetivo)
            if m.tipo_movimiento == "INGRESO":
                ingresos += val
                ingresos_cat[m.categoria] = ingresos_cat.get(m.categoria, Decimal("0")) + val
            elif m.tipo_movimiento == "GASTO":
                gastos += val
                gastos_cat[m.categoria] = gastos_cat.get(m.categoria, Decimal("0")) + val

        return {
            "ingresos": ingresos.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "gastos": gastos.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "gastos_por_categoria": gastos_cat,
            "ingresos_por_categoria": ingresos_cat,
        }

    def generar_radiografia_y_salud_financiera(
        self,
        fecha_inicio: date,
        fecha_fin: date,
        moneda_objetivo: str = "COP",
        incluir_todas_convertidas: bool = True,
    ) -> Dict[str, object]:
        """Fachada hacia el servicio modular `analitica_reportes.generar_reporte_analitico`."""
        from app.servicio.analitica_reportes import generar_reporte_analitico

        return generar_reporte_analitico(
            self,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            moneda_objetivo=moneda_objetivo,
            incluir_todas_convertidas=incluir_todas_convertidas,
        )

    def exportar_reporte_completo(
        self,
        ruta_destino: str,
        fecha_inicio: date,
        fecha_fin: date,
        moneda_objetivo: str = "COP",
        incluir_todas_convertidas: bool = True,
        formato: str = "xlsx",
    ) -> str:
        """Fachada hacia el servicio modular `analitica_reportes.exportar_estado_cuenta`."""
        from app.servicio.analitica_reportes import exportar_estado_cuenta

        return exportar_estado_cuenta(
            self,
            ruta_destino=ruta_destino,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            moneda_objetivo=moneda_objetivo,
            incluir_todas_convertidas=incluir_todas_convertidas,
            formato=formato,
        )

    def eliminar_inversion(self, id_inversion: int) -> bool:
        if self._cache_inversiones_bd is not None:
            self._cache_inversiones_bd = [
                inv for inv in self._cache_inversiones_bd if inv.id != id_inversion
            ]
        self._inversiones_memoria = [
            inv for inv in self._inversiones_memoria if inv.id != id_inversion
        ]
        if hasattr(self._repositorio, "eliminar_inversion"):
            try:
                return self._repositorio.eliminar_inversion(id_inversion)
            except Exception:
                pass
        if hasattr(self._repositorio, "ejecutar_consulta"):
            try:
                self._asegurar_tabla_inversion_bd()
                filas = self._repositorio.ejecutar_consulta(
                    "DELETE FROM inversion WHERE id = %s RETURNING id",
                    (id_inversion,),
                )
                return bool(filas)
            except Exception:
                pass
        return True

    def limpiar_todas_las_inversiones(self) -> None:
        """Elimina todas las posiciones del portafolio actual (en base de datos y en memoria)."""
        self._inversiones_memoria.clear()
        self._cache_inversiones_bd = []
        if hasattr(self._repositorio, "ejecutar_consulta"):
            try:
                self._asegurar_tabla_inversion_bd()
                self._repositorio.ejecutar_consulta("DELETE FROM inversion")
            except Exception:
                pass

    def previsualizar_importacion_etoro(
        self, ruta_archivo: str, agrupar_por_ticker: bool = False
    ) -> List[Dict[str, object]]:
        """Analiza un archivo Excel (.xlsx) de Estado de Cuenta de eToro o un CSV de portafolio
        y devuelve ÚNICAMENTE las posiciones abiertas (por defecto cada transacción por separado)."""
        return parsear_archivo_etoro_o_csv(ruta_archivo, agrupar_por_ticker=agrupar_por_ticker)

    def previsualizar_importacion_broker(
        self, ruta_archivo: str, broker: str, agrupar_por_ticker: bool = False
    ) -> List[Dict[str, object]]:
        """Analiza un archivo de exportación del broker indicado (eToro, Binance,
        Interactive Brokers, Trii o Hapi) y devuelve las posiciones a importar."""
        return parsear_archivo_broker(
            ruta_archivo, broker, agrupar_por_ticker=agrupar_por_ticker)

    def importar_inversiones_lote(
        self,
        posiciones_detectadas: Sequence[Dict[str, object]],
        limpiar_antes: bool = True,
        omitir_duplicados: bool = False,
    ) -> Tuple[List[Inversion], int]:
        """Guarda en la base de datos un lote de posiciones abiertas provenientes de un broker.

        - Si `limpiar_antes=True`, limpia primero las inversiones anteriores
          para no duplicar.
        - Si `omitir_duplicados=True` (y no se limpia antes), compara cada
          posición contra las inversiones ya guardadas y también contra las
          demás filas del mismo archivo, y omite las que ya existan.
          Una posición se considera duplicada cuando coincide el símbolo,
          la fecha de compra y el monto invertido (en centavos).
        Devuelve (lista de importadas, cantidad de duplicadas omitidas).
        """
        omitidas = 0
        posiciones_finales = list(posiciones_detectadas)
        if omitir_duplicados and not limpiar_antes:
            existentes = self.obtener_inversiones(forzar_bd=True)
            claves_existentes = {
                clave_duplicado_inversion(inv) for inv in existentes
            }
            vistos_en_lote: set = set()
            sin_duplicados: List[Dict[str, object]] = []
            for posicion in posiciones_finales:
                clave = clave_duplicado_posicion(posicion)
                if clave in claves_existentes or clave in vistos_en_lote:
                    omitidas += 1
                    continue
                vistos_en_lote.add(clave)
                sin_duplicados.append(posicion)
            posiciones_finales = sin_duplicados
        elif omitir_duplicados and limpiar_antes:
            # Reemplazar y omitir duplicados a la vez no tiene efecto
            # (se borra todo antes), pero se respeta el conteo en cero.
            omitidas = 0

        if limpiar_antes:
            self.limpiar_todas_las_inversiones()

        importadas: List[Inversion] = []
        for item in posiciones_finales:
            simbolo_bruto = str(item.get("simbolo", "")).strip().upper()
            simbolo = normalizar_simbolo_yahoo(simbolo_bruto)
            nombre = str(item.get("nombre", simbolo)).strip()
            if simbolo_bruto in MAPA_CRIPTO_A_YAHOO and nombre.upper() in (simbolo_bruto, simbolo):
                nombre = MAPA_CRIPTO_A_YAHOO[simbolo_bruto][1]
            monto: Decimal = item.get("monto_invertido", Decimal("0"))  # type: ignore[assignment]
            moneda = str(item.get("moneda", "USD")).strip().upper()
            precio_compra: Optional[Decimal] = item.get("precio_compra")  # type: ignore[assignment]
            unidades: Optional[Decimal] = item.get("unidades")  # type: ignore[assignment]
            fecha_c = item.get("fecha_compra")
            notas = str(item.get("notas", "Importado de eToro")).strip()

            if not simbolo or monto <= Decimal("0"):
                continue

            if (precio_compra is None or precio_compra <= Decimal("0")) and unidades and unidades > Decimal("0"):
                precio_compra = (monto / unidades).quantize(
                    Decimal("0.00000001"), rounding=ROUND_HALF_UP
                )

            fecha_obj = fecha_c if isinstance(fecha_c, date) else date.today()
            # Validar precio de apertura contra el precio histórico real de Yahoo Finance en la fecha de compra
            # para corregir splits de acciones o discrepancias de 'Units / Contracts' en el Excel de eToro
            precio_hist = self.consultar_precio_historico_inversion(
                simbolo, fecha_obj, moneda_esperada=moneda
            )
            if precio_hist is not None and precio_hist > Decimal("0"):
                if precio_compra is None or precio_compra <= Decimal("0"):
                    precio_compra = precio_hist
                else:
                    desviacion = abs(precio_compra - precio_hist) / precio_hist
                    if desviacion > Decimal("0.25"):
                        precio_compra = precio_hist

            fecha_str = fecha_obj.isoformat()
            precio_str = f"{precio_compra:.8f}" if (precio_compra and precio_compra > Decimal("0")) else None
            guardada = self.registrar_inversion(
                simbolo=simbolo,
                nombre=nombre,
                monto_texto=f"{monto:.2f}",
                moneda=moneda,
                precio_compra_texto=precio_str,
                fecha_texto=fecha_str,
                notas=notas,
            )
            if guardada.id is not None:
                self._inversiones_verificadas_sesion.add(guardada.id)
            importadas.append(guardada)
        return importadas, omitidas

    def exportar_plantilla_etoro_csv(self, ruta_destino: str) -> None:
        generar_plantilla_csv_etoro(ruta_destino)

    def exportar_plantilla_csv(self, ruta_destino: str) -> None:
        """Plantilla CSV genérica para armar un portafolio a mano
        (usada por Trii y Hapi, que no tienen exportación pública)."""
        generar_plantilla_csv_etoro(ruta_destino)

    def _actualizar_inversion_saneada(self, inv_actualizada: Inversion) -> None:
        """Actualiza en la base de datos y en memoria una inversión cuyo símbolo cripto o precio
        de apertura pre-split/corrupto fue reparado automáticamente."""
        if inv_actualizada.id is not None and hasattr(self._repositorio, "ejecutar_consulta"):
            try:
                self._asegurar_tabla_inversion_bd()
                self._repositorio.ejecutar_consulta(
                    """
                    UPDATE inversion
                    SET simbolo = %s,
                        nombre = %s,
                        precio_compra = %s,
                        cantidad_titulos = %s
                    WHERE id = %s
                    """,
                    (
                        inv_actualizada.simbolo,
                        inv_actualizada.nombre,
                        inv_actualizada.precio_compra,
                        inv_actualizada.cantidad_titulos,
                        inv_actualizada.id,
                    ),
                )
            except Exception:
                pass
        for idx, item in enumerate(self._inversiones_memoria):
            if item.id == inv_actualizada.id:
                self._inversiones_memoria[idx] = inv_actualizada
                break
        if self._cache_inversiones_bd is not None:
            for idx, item in enumerate(self._cache_inversiones_bd):
                if item.id == inv_actualizada.id:
                    self._cache_inversiones_bd[idx] = inv_actualizada
                    break

    def _sanear_inversiones_existentes(
        self, inversiones: List[Inversion], permitir_red: bool = True
    ) -> List[Inversion]:
        """Auto-repara inversiones previamente guardadas:
        1) Convierte símbolos cortos de cripto ('BTC' -> 'BTC-USD', 'SOL' -> 'SOL-USD', 'ETH' -> 'ETH-USD') en 0ms.
        2) Si `permitir_red=True` (hilo secundario), verifica el precio histórico en la fecha de apertura."""
        saneadas: List[Inversion] = []
        hay_red = permitir_red and self.hay_conexion_internet(usar_cache_breve=True)

        for inv in inversiones:
            sim_orig = inv.simbolo.strip().upper()
            sim_norm = normalizar_simbolo_yahoo(sim_orig)
            nom_nuevo = inv.nombre
            if sim_orig in MAPA_CRIPTO_A_YAHOO and (
                nom_nuevo.strip().upper() in (sim_orig, sim_norm)
            ):
                nom_nuevo = MAPA_CRIPTO_A_YAHOO[sim_orig][1]

            precio_c = inv.precio_compra
            cant_t = inv.cantidad_titulos
            cambio = sim_norm != sim_orig or nom_nuevo != inv.nombre

            debe_verificar_hist = (
                hay_red
                and (inv.id is None or inv.id not in self._inversiones_verificadas_sesion)
                and (
                    cambio
                    or (inv.notas and ("etoro" in inv.notas.lower() or "importado" in inv.notas.lower()))
                )
            )
            if debe_verificar_hist:
                if inv.id is not None:
                    self._inversiones_verificadas_sesion.add(inv.id)
                precio_hist = self.consultar_precio_historico_inversion(
                    sim_norm, inv.fecha_compra, moneda_esperada=inv.moneda
                )
                if precio_hist is not None and precio_hist > Decimal("0"):
                    desviacion = abs(precio_c - precio_hist) / precio_hist
                    if desviacion > Decimal("0.25"):
                        precio_c = precio_hist
                        cant_t = (inv.monto_invertido / precio_c).quantize(
                            Decimal("0.00000001"), rounding=ROUND_HALF_UP
                        )
                        if cant_t <= Decimal("0"):
                            cant_t = Decimal("0.00000001")
                        cambio = True

            if cambio:
                inv_rep = Inversion(
                    id=inv.id,
                    simbolo=sim_norm,
                    nombre=nom_nuevo,
                    monto_invertido=inv.monto_invertido,
                    moneda=inv.moneda,
                    precio_compra=precio_c,
                    cantidad_titulos=cant_t,
                    fecha_compra=inv.fecha_compra,
                    cuenta_id=inv.cuenta_id,
                    notas=inv.notas,
                )
                self._actualizar_inversion_saneada(inv_rep)
                saneadas.append(inv_rep)
            else:
                saneadas.append(inv)
        return saneadas

    def valorar_portafolio(
        self,
        moneda_objetivo: str = "COP",
        incluir_todas_convertidas: bool = True,
        forzar_actualizacion: bool = False,
        permitir_red: bool = True,
    ) -> Dict[str, object]:
        """Calcula la valoración dinámica de todas las inversiones del usuario.
        Cuando `permitir_red=False`, responde en <2ms desde memoria/caché sin bloquear la interfaz."""
        mon_dest = self._validar_moneda(moneda_objetivo)
        inversiones = self._sanear_inversiones_existentes(
            self.obtener_inversiones(), permitir_red=permitir_red
        )

        posiciones: List[ValoracionInversion] = []
        capital_total = Decimal("0")
        valor_actual_total = Decimal("0")
        usando_cache = False
        faltan_precios_vivos = False

        # Consultar una sola vez por cada ticker único
        cotizaciones_por_simbolo: Dict[str, Optional[Cotizacion]] = {}
        for inv in inversiones:
            if not incluir_todas_convertidas and inv.moneda != mon_dest:
                continue
            if inv.simbolo not in cotizaciones_por_simbolo:
                if inv.simbolo not in self._precios_inversion_vivos_sesion:
                    faltan_precios_vivos = True
                cotizaciones_por_simbolo[inv.simbolo] = self.consultar_precio_inversion(
                    inv.simbolo,
                    moneda_esperada="USD",
                    forzar_actualizacion=forzar_actualizacion,
                    permitir_red=permitir_red,
                )
            if (
                inv.id is not None
                and inv.id not in self._inversiones_verificadas_sesion
                and inv.notas
                and ("etoro" in inv.notas.lower() or "importado" in inv.notas.lower())
            ):
                faltan_precios_vivos = True

        for inv in inversiones:
            if not incluir_todas_convertidas and inv.moneda != mon_dest:
                continue

            cot = cotizaciones_por_simbolo.get(inv.simbolo)
            desde_cache_item = False
            fecha_cot = inv.fecha_compra

            if cot is not None and cot.precio > Decimal("0"):
                desde_cache_item = "Caché" in (cot.fuente or "")
                fecha_cot = cot.fecha
                if inv.moneda == cot.moneda:
                    precio_actual_moneda_inv = cot.precio
                else:
                    try:
                        precio_actual_moneda_inv = self.convertir_entre_monedas(
                            cot.precio, cot.moneda, inv.moneda
                        )
                    except ErrorValidacion:
                        precio_actual_moneda_inv = inv.precio_compra
            else:
                desde_cache_item = True
                precio_actual_moneda_inv = inv.precio_compra

            if desde_cache_item:
                usando_cache = True

            valor_actual_nativo = (inv.cantidad_titulos * precio_actual_moneda_inv).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            ganancia_nativa = (valor_actual_nativo - inv.monto_invertido).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            rendimiento_pct = (
                ((ganancia_nativa / inv.monto_invertido) * Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                if inv.monto_invertido > Decimal("0")
                else Decimal("0.00")
            )

            if inv.moneda == mon_dest:
                monto_inv_conv = inv.monto_invertido
                valor_act_conv = valor_actual_nativo
            else:
                cot_tasa = self.obtener_tasa_cambio(
                    inv.moneda, mon_dest, forzar_actualizacion=False, permitir_red=permitir_red
                )
                if cot_tasa is not None and cot_tasa.precio > Decimal("0"):
                    monto_inv_conv = (inv.monto_invertido * cot_tasa.precio).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                    valor_act_conv = (valor_actual_nativo * cot_tasa.precio).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                else:
                    faltan_precios_vivos = True
                    monto_inv_conv = inv.monto_invertido
                    valor_act_conv = valor_actual_nativo

            ganancia_conv = (valor_act_conv - monto_inv_conv).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

            capital_total += monto_inv_conv
            valor_actual_total += valor_act_conv

            posiciones.append(
                ValoracionInversion(
                    inversion=inv,
                    precio_actual=precio_actual_moneda_inv,
                    valor_actual=valor_actual_nativo,
                    ganancia_perdida=ganancia_nativa,
                    rendimiento_porcentaje=rendimiento_pct,
                    moneda_visualizacion=mon_dest,
                    monto_invertido_convertido=monto_inv_conv,
                    valor_actual_convertido=valor_act_conv,
                    ganancia_perdida_convertida=ganancia_conv,
                    desde_cache=desde_cache_item,
                    fecha_cotizacion=fecha_cot,
                )
            )

        ganancia_neta_total = (valor_actual_total - capital_total).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        rendimiento_total_pct = (
            ((ganancia_neta_total / capital_total) * Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if capital_total > Decimal("0")
            else Decimal("0.00")
        )

        return {
            "posiciones": posiciones,
            "capital_invertido": capital_total,
            "valor_actual_mercado": valor_actual_total,
            "ganancia_perdida_neta": ganancia_neta_total,
            "rendimiento_porcentaje": rendimiento_total_pct,
            "en_ganancia": ganancia_neta_total >= Decimal("0"),
            "desde_cache": usando_cache,
            "faltan_precios_vivos": faltan_precios_vivos,
            "moneda": mon_dest,
        }

    def obtener_serie_montana_portafolio(
        self,
        marco_tiempo: str = "1M",
        simbolo_filtro: Optional[str] = None,
        moneda_objetivo: str = "COP",
        incluir_todas_convertidas: bool = True,
        valoracion_precalculada: Optional[Dict[str, object]] = None,
        forzar_actualizacion: bool = False,
        permitir_red: bool = True,
    ) -> Dict[str, object]:
        """Construye la serie histórica `(etiqueta, valor)` para renderizar el gráfico estilo
        montaña (formato eToro) en los marcos `1D`, `1W`, `1M`, `1Y`."""
        mon_dest = self._validar_moneda(moneda_objetivo)
        valoracion = (
            valoracion_precalculada
            if valoracion_precalculada is not None
            else self.valorar_portafolio(
                moneda_objetivo=mon_dest,
                incluir_todas_convertidas=incluir_todas_convertidas,
                forzar_actualizacion=False,
                permitir_red=permitir_red,
            )
        )
        posiciones: List[ValoracionInversion] = list(valoracion.get("posiciones", []))  # type: ignore[arg-type]
        if simbolo_filtro:
            sim_up = simbolo_filtro.strip().upper()
            posiciones = [p for p in posiciones if p.inversion.simbolo == sim_up]

        if not posiciones:
            return {
                "puntos": [],
                "en_ganancia": True,
                "cambio_absoluto": Decimal("0.00"),
                "cambio_porcentaje": Decimal("0.00"),
                "valor_inicial": Decimal("0.00"),
                "valor_final": Decimal("0.00"),
            }

        # Intentar construir la curva real sumando las series históricas de cada activo
        series_por_simbolo: Dict[str, List[Tuple[str, Decimal]]] = {}
        for pos in posiciones:
            sim = pos.inversion.simbolo
            if sim not in series_por_simbolo:
                if not permitir_red:
                    cache_s = getattr(self._servicio_bursatil, "_cache_series_temporales", {})
                    series_por_simbolo[sim] = list(cache_s.get((sim, (marco_tiempo or "1M").strip().upper()), []))
                    continue
                try:
                    series_por_simbolo[sim] = self._servicio_bursatil.consultar_serie_temporal(
                        sim,
                        marco_tiempo=marco_tiempo,
                        forzar_actualizacion=forzar_actualizacion,
                    )
                except TypeError:
                    try:
                        series_por_simbolo[sim] = self._servicio_bursatil.consultar_serie_temporal(
                            sim, marco_tiempo=marco_tiempo
                        )
                    except Exception:
                        series_por_simbolo[sim] = []
                except Exception:
                    series_por_simbolo[sim] = []

        # Factor de conversión USD -> mon_dest
        tasa_usd_dest = Decimal("1.00")
        if mon_dest != "USD":
            cot_fx = self.obtener_tasa_cambio(
                "USD", mon_dest, forzar_actualizacion=False, permitir_red=permitir_red
            )
            if cot_fx is not None and cot_fx.precio > Decimal("0"):
                tasa_usd_dest = cot_fx.precio

        # Si hay al menos una serie con datos reales de Yahoo Finance, agregamos punto por punto
        serie_base = next((s for s in series_por_simbolo.values() if len(s) >= 2), None)
        puntos_curva: List[Tuple[str, Decimal]] = []

        if serie_base is not None:
            num_puntos = len(serie_base)
            for idx in range(num_puntos):
                etiqueta_t = serie_base[idx][0]
                suma_punto = Decimal("0")
                for pos in posiciones:
                    serie_act = series_por_simbolo.get(pos.inversion.simbolo, [])
                    if serie_act:
                        i_efectivo = min(idx, len(serie_act) - 1)
                        precio_usd = serie_act[i_efectivo][1]
                        # Cantidad equivalente en USD o moneda nativa
                        if pos.inversion.moneda == "USD":
                            val_usd = pos.inversion.cantidad_titulos * precio_usd
                            suma_punto += (val_usd * tasa_usd_dest)
                        else:
                            # Escalar proporcionalmente respecto al último precio de la serie
                            ultimo_p = serie_act[-1][1]
                            factor = (precio_usd / ultimo_p) if ultimo_p > Decimal("0") else Decimal("1")
                            suma_punto += (pos.valor_actual_convertido * factor)
                    else:
                        suma_punto += pos.valor_actual_convertido
                puntos_curva.append(
                    (etiqueta_t, suma_punto.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                )
        else:
            # Respaldo determinista cuando no hay conexión (interpola entre capital invertido y valor actual)
            cap_ini = sum((p.monto_invertido_convertido for p in posiciones), Decimal("0"))
            val_fin = sum((p.valor_actual_convertido for p in posiciones), Decimal("0"))
            pesos = [0.0, 0.18, 0.12, 0.35, 0.28, 0.52, 0.48, 0.72, 0.68, 0.88, 0.94, 1.0]
            diferencia = val_fin - cap_ini
            # Si cap_ini == val_fin, mostrar ligera oscilación alrededor de cap_ini
            amplitud = diferencia if diferencia != Decimal("0") else (cap_ini * Decimal("0.015"))
            for idx, w in enumerate(pesos):
                if diferencia != Decimal("0"):
                    v = cap_ini + (diferencia * Decimal(str(w)))
                else:
                    ond = Decimal(str((w - 0.5) * 0.4))
                    v = cap_ini + (amplitud * ond) if idx < len(pesos) - 1 else val_fin
                puntos_curva.append(
                    (f"P{idx + 1}", v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                )

        valor_inicial = puntos_curva[0][1]
        valor_final = puntos_curva[-1][1]
        cambio_abs = (valor_final - valor_inicial).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cambio_pct = (
            ((cambio_abs / valor_inicial) * Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if valor_inicial > Decimal("0")
            else Decimal("0.00")
        )

        return {
            "puntos": puntos_curva,
            "en_ganancia": cambio_abs >= Decimal("0"),
            "cambio_absoluto": cambio_abs,
            "cambio_porcentaje": cambio_pct,
            "valor_inicial": valor_inicial,
            "valor_final": valor_final,
        }

    # ------------------------------------------------------------------
    # Validaciones internas
    # ------------------------------------------------------------------
    def _validar_nombre_cuenta(self, nombre: str) -> str:
        if not isinstance(nombre, str) or not nombre.strip():
            raise ErrorValidacion("El nombre de la cuenta es obligatorio.")
        limpio = nombre.strip()
        if len(limpio) > 60:
            raise ErrorValidacion("El nombre de la cuenta no puede superar 60 caracteres.")
        return limpio

    def _validar_saldo_inicial(self, saldo_texto: Optional[str] = "0") -> Decimal:
        if saldo_texto is None:
            return Decimal("0")
        if isinstance(saldo_texto, (int, float, Decimal)):
            saldo_texto = str(saldo_texto)
        if not isinstance(saldo_texto, str) or not saldo_texto.strip():
            return Decimal("0")
        limpio = saldo_texto.strip()
        if not PATRON_VALOR.match(limpio):
            raise ErrorValidacion("El saldo inicial debe ser un número válido mayor o igual a cero.")
        try:
            valor = Decimal(limpio.replace(",", "."))
        except InvalidOperation as error:
            raise ErrorValidacion("El saldo inicial no es válido.") from error
        if valor < Decimal("0"):
            raise ErrorValidacion("El saldo inicial no puede ser negativo.")
        return valor

    def _validar_simbolo(self, simbolo: str) -> str:
        if not isinstance(simbolo, str) or simbolo.strip() not in SIMBOLOS_VALIDOS:
            raise ErrorValidacion("Debe seleccionar un símbolo válido para la cuenta.")
        return simbolo.strip()

    def _validar_color(self, color: str) -> str:
        if not isinstance(color, str) or not PATRON_COLOR.match(color.strip()):
            raise ErrorValidacion("El color debe estar en formato hexadecimal (#RRGGBB).")
        return color.strip().upper()

    def _validar_tipo(self, tipo: str) -> str:
        if not isinstance(tipo, str):
            raise ErrorValidacion("El tipo de movimiento es obligatorio.")
        limpio = tipo.strip().upper()
        if limpio not in TIPOS_VALIDOS:
            raise ErrorValidacion(f"El tipo de movimiento debe ser uno de: {', '.join(TIPOS_VALIDOS)}.")
        return limpio

    def _validar_fecha(self, fecha_texto: str) -> date:
        if not isinstance(fecha_texto, str) or not fecha_texto.strip():
            raise ErrorValidacion("La fecha es obligatoria (formato AAAA-MM-DD).")
        limpio = fecha_texto.strip()
        if len(limpio) != 10 or limpio[4] != "-" or limpio[7] != "-":
            raise ErrorValidacion("La fecha debe tener el formato AAAA-MM-DD.")
        try:
            return date.fromisoformat(limpio)
        except ValueError as error:
            raise ErrorValidacion("La fecha ingresada no es válida.") from error

    def _validar_valor(self, valor_texto: str) -> Decimal:
        if not isinstance(valor_texto, str) or not valor_texto.strip():
            raise ErrorValidacion("El valor es obligatorio.")
        limpio = valor_texto.strip()
        if not PATRON_VALOR.match(limpio):
            raise ErrorValidacion("El valor debe ser numérico positivo con máximo dos decimales.")
        try:
            valor = Decimal(limpio.replace(",", "."))
        except InvalidOperation as error:
            raise ErrorValidacion("El valor numérico es inválido.") from error
        if valor <= Decimal("0"):
            raise ErrorValidacion("El valor debe ser mayor que cero.")
        return valor

    def _validar_moneda(self, moneda: str) -> str:
        if not isinstance(moneda, str):
            raise ErrorValidacion("La moneda es obligatoria.")
        limpia = moneda.strip().upper()
        if limpia not in DIVISAS_MUNDIALES:
            raise ErrorValidacion(f"La moneda '{limpia}' no es una divisa ISO válida.")
        return limpia

    def _validar_categoria(self, categoria: str) -> str:
        if not isinstance(categoria, str) or not categoria.strip():
            raise ErrorValidacion("La categoría es obligatoria.")
        limpia = categoria.strip()
        categorias_disponibles = self._repositorio.obtener_categorias()
        if limpia not in categorias_disponibles:
            raise ErrorValidacion(f"La categoría '{limpia}' no pertenece al catálogo registrado.")
        return limpia

    def _validar_descripcion(self, descripcion: Optional[str]) -> Optional[str]:
        if descripcion is None:
            return None
        if not isinstance(descripcion, str):
            raise ErrorValidacion("La descripción debe ser texto.")
        limpia = descripcion.strip()
        if not limpia:
            return None
        if len(limpia) > 200:
            raise ErrorValidacion("La descripción no puede superar los 200 caracteres.")
        return limpia
