"""Lógica de negocio para gestionar cuentas, ingresos, gastos, categorías, etiquetas, divisas e inversiones.

Incluye gestión inteligente de estado de conexión a internet para divisas e inversiones:
- Cuando hay internet (`ONLINE`): actualiza tasas y precios en tiempo real desde Yahoo Finance y los guarda en caché.
- Cuando no hay internet pero existe caché (`OFFLINE_CON_CACHE`): informa al usuario y utiliza la última cotización guardada.
- Cuando no hay internet y no existe caché (`OFFLINE_SIN_CACHE`): informa al usuario que no tiene conexión y que se actualizará automáticamente apenas se conecte.
"""

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from app.modelo.categoria import Categoria
from app.modelo.cotizacion import Cotizacion
from app.modelo.cuenta import Cuenta
from app.modelo.divisas import (
    CODIGOS_DIVISAS_ORDENADOS,
    DIVISAS_MUNDIALES,
    construir_lista_selector_divisas,
)
from app.modelo.etiqueta import Etiqueta
from app.modelo.movimiento_financiero import MovimientoFinanciero
from app.modelo.transferencia import Transferencia
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
        if limpia in self._monedas_recientes_memoria:
            self._monedas_recientes_memoria.remove(limpia)
        self._monedas_recientes_memoria.insert(0, limpia)
        self._monedas_recientes_memoria = self._monedas_recientes_memoria[:4]

        if hasattr(self._repositorio, "registrar_moneda_reciente"):
            try:
                self._repositorio.registrar_moneda_reciente(limpia)
            except Exception:
                pass

    def obtener_ultimas_5_monedas(self) -> List[str]:
        """Devuelve siempre ['COP', <hasta 4 últimas divisas usadas>]."""
        recientes_bd: List[str] = []
        if hasattr(self._repositorio, "obtener_monedas_recientes"):
            try:
                recientes_bd = self._repositorio.obtener_monedas_recientes(4)
            except Exception:
                recientes_bd = []

        combinadas: List[str] = ["COP"]
        for cod in list(recientes_bd) + list(self._monedas_recientes_memoria):
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
    def obtener_tasa_cambio(
        self,
        moneda_origen: str,
        moneda_destino: str,
        forzar_actualizacion: bool = False,
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

        # Si ya se obtuvo en vivo en esta sesión y sigue habiendo conexión, reutilizar sin latencia
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

    def consultar_precio_inversion(
        self,
        simbolo: str,
        moneda_esperada: str = "USD",
        forzar_actualizacion: bool = False,
    ) -> Optional[Cotizacion]:
        """Consulta el precio en tiempo real de un activo de inversión (ej. 'VOO', 'AAPL')
        y si no hay conexión a internet devuelve el precio guardado en caché (o None si no hay caché),
        actualizando el estado de conexión para informar al usuario."""
        simbolo_limpio = simbolo.strip().upper()
        if (
            not forzar_actualizacion
            and simbolo_limpio in self._precios_inversion_vivos_sesion
            and self.hay_conexion_internet(usar_cache_breve=True)
        ):
            cot_viva = self._precios_inversion_vivos_sesion[simbolo_limpio]
            self._estado_conexion_api = ESTADO_CONEXION_ONLINE
            self._ultima_cotizacion_usada = cot_viva
            return cot_viva

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
        except (ErrorSinConexionInternet, ErrorConsultaBursatil):
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
        gastos_por_cat: Dict[str, Decimal] = {}

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
            elif mov.tipo_movimiento == "GASTO":
                total_gastos += monto
                gastos_por_cat[mov.categoria] = (
                    gastos_por_cat.get(mov.categoria, Decimal("0")) + monto
                )

        return {
            "ingresos": total_ingresos,
            "gastos": total_gastos,
            "gastos_por_categoria": gastos_por_cat,
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
        return self._repositorio.obtener_categorias()

    def obtener_categorias_detalladas(self, tipo: Optional[str] = "GASTO") -> List[Categoria]:
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
        saldo_inicial_texto: str,
        simbolo: str,
        color: str,
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
    # Validaciones internas
    # ------------------------------------------------------------------
    def _validar_nombre_cuenta(self, nombre: str) -> str:
        if not isinstance(nombre, str) or not nombre.strip():
            raise ErrorValidacion("El nombre de la cuenta es obligatorio.")
        limpio = nombre.strip()
        if len(limpio) > 60:
            raise ErrorValidacion("El nombre de la cuenta no puede superar 60 caracteres.")
        return limpio

    def _validar_saldo_inicial(self, saldo_texto: str) -> Decimal:
        if not isinstance(saldo_texto, str) or not saldo_texto.strip():
            raise ErrorValidacion("El saldo inicial es obligatorio.")
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
