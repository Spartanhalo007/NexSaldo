"""Lógica de negocio para gestionar cuentas, ingresos, gastos, categorías, etiquetas y divisas."""

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from app.modelo.categoria import Categoria
from app.modelo.cotizacion import Cotizacion
from app.modelo.cuenta import Cuenta
from app.modelo.etiqueta import Etiqueta
from app.modelo.movimiento_financiero import MovimientoFinanciero
from app.modelo.transferencia import Transferencia
from app.servicio.servicio_bursatil import (
    ErrorConsultaBursatil,
    SIMBOLO_USD_COP,
    ServicioBursatil,
)

TIPOS_VALIDOS = ("INGRESO", "GASTO")
MONEDAS_VALIDAS = ("COP", "USD")
FRECUENCIAS_VALIDAS = ("DIARIO", "SEMANAL", "QUINCENAL", "MENSUAL", "ANUAL")
PATRON_VALOR = re.compile(r"^\d+([.,]\d{1,2})?$")
PATRON_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")

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
        ("cash", "Efectivo"),
        ("banco", "Banco"),
        ("tarjeta_credito", "Tarjeta crédito"),
        ("tarjeta_debito", "Tarjeta débito"),
        ("impuestos", "Impuestos / %"),
        ("grafico_subida", "Inversión / Ahorro"),
        ("calculadora_icono", "Presupuesto"),
        ("puerquito", "Alcancía"),
        ("boveda", "Bóveda / Caja"),
        ("moneda", "Moneda"),
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
        ("bolsa_compras", "Compras / Mall"),
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
        ("computador", "Tecnología / PC"),
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


class GestorFinanciero:
    """Coordina las validaciones, el acceso al repositorio y las consultas bursátiles en tiempo real."""

    def __init__(self, repositorio, servicio_bursatil: Optional[ServicioBursatil] = None):
        self._repositorio = repositorio
        self._servicio_bursatil = servicio_bursatil or ServicioBursatil()
        self._cotizacion_usd_cop_memoria: Optional[Cotizacion] = None
        self._categorias_memoria_extra: Dict[str, Categoria] = {
            c.nombre: c for c in CATEGORIAS_GASTO_PREDETERMINADAS
        }
        self._etiquetas_memoria_extra: Dict[str, Etiqueta] = {}

    # ------------------------------------------------------------------
    # Conversión en tiempo real USD <-> COP (Yahoo Finance / yfinance)
    # ------------------------------------------------------------------
    def obtener_tasa_usd_cop(self, forzar_actualizacion: bool = False) -> Optional[Cotizacion]:
        """Devuelve la cotización en tiempo real USD->COP o el último valor guardado localmente."""
        if not forzar_actualizacion:
            if self._cotizacion_usd_cop_memoria is not None:
                return self._cotizacion_usd_cop_memoria
            if hasattr(self._repositorio, "obtener_ultima_cotizacion"):
                guardada = self._repositorio.obtener_ultima_cotizacion(SIMBOLO_USD_COP)
                if guardada is not None:
                    self._cotizacion_usd_cop_memoria = guardada
                    return guardada

        try:
            nueva = self._servicio_bursatil.consultar_tasa_usd_cop()
            if hasattr(self._repositorio, "guardar_cotizaciones"):
                guardadas = self._repositorio.guardar_cotizaciones([nueva])
                if guardadas:
                    nueva = guardadas[0]
            self._cotizacion_usd_cop_memoria = nueva
            return nueva
        except ErrorConsultaBursatil:
            if self._cotizacion_usd_cop_memoria is not None:
                return self._cotizacion_usd_cop_memoria
            if hasattr(self._repositorio, "obtener_ultima_cotizacion"):
                return self._repositorio.obtener_ultima_cotizacion(SIMBOLO_USD_COP)
            return None

    def convertir_usd_a_cop(self, monto_usd: Decimal, tasa: Optional[Decimal] = None) -> Decimal:
        """Convierte dólares (USD) a pesos colombianos (COP) redondeando a 2 decimales."""
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
        """Convierte pesos colombianos (COP) a dólares (USD) redondeando a 2 decimales."""
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
    # Categorías (compatibilidad total + creación customizada)
    # ------------------------------------------------------------------
    def obtener_categorias(self) -> List[str]:
        return self._repositorio.obtener_categorias()

    def obtener_categorias_detalladas(self, tipo: Optional[str] = "GASTO") -> List[Categoria]:
        if hasattr(self._repositorio, "obtener_categorias_detalladas"):
            categorias = self._repositorio.obtener_categorias_detalladas(tipo=tipo)
            if categorias:
                return categorias

        nombres_repo = self._repositorio.obtener_categorias()
        resultado: List[Categoria] = []
        vistos = set()

        for cat_pred in CATEGORIAS_GASTO_PREDETERMINADAS:
            if tipo is None or cat_pred.tipo == tipo.upper():
                resultado.append(cat_pred)
                vistos.add(cat_pred.nombre)

        for nombre, cat_extra in self._categorias_memoria_extra.items():
            if nombre not in vistos and (tipo is None or cat_extra.tipo == tipo.upper()):
                resultado.append(cat_extra)
                vistos.add(nombre)

        for nombre in nombres_repo:
            if nombre not in vistos:
                resultado.append(
                    Categoria(None, nombre, tipo or "GASTO", "mercado", "#FBB718", False)
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
                raise ErrorValidacion("La frecuencia del gasto programado no es válida.")
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
    # Movimientos y Gastos
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

    def resumen_gastos_periodo(
        self,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
    ) -> Dict[str, Dict[str, object]]:
        if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
            raise ErrorValidacion("La fecha final no puede ser anterior a la fecha inicial.")

        mapa_cat = {c.nombre: c for c in self.obtener_categorias_detalladas("GASTO")}
        gastos = self.obtener_movimientos("GASTO", fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)

        resumen: Dict[str, Dict[str, object]] = {}
        for g in gastos:
            datos_moneda = resumen.setdefault(
                g.moneda,
                {"total": Decimal("0"), "por_categoria": {}, "colores": {}, "simbolos": {}},
            )
            datos_moneda["total"] = datos_moneda["total"] + g.valor
            por_cat: Dict[str, Decimal] = datos_moneda["por_categoria"]  # type: ignore[assignment]
            por_cat[g.categoria] = por_cat.get(g.categoria, Decimal("0")) + g.valor

            cat_info = mapa_cat.get(g.categoria)
            colores: Dict[str, str] = datos_moneda["colores"]  # type: ignore[assignment]
            simbolos: Dict[str, str] = datos_moneda["simbolos"]  # type: ignore[assignment]
            colores[g.categoria] = cat_info.color if cat_info else "#FBB718"
            simbolos[g.categoria] = cat_info.simbolo if cat_info else "mercado"

        return resumen

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
        if limpia not in MONEDAS_VALIDAS:
            raise ErrorValidacion(f"La moneda debe ser una de: {', '.join(MONEDAS_VALIDAS)}.")
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
