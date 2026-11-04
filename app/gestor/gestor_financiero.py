"""Lógica de negocio y validaciones (GestorFinanciero del modelo de la tesis).

Coordina el registro, la consulta y la eliminación de movimientos.
No conoce tkinter ni PostgreSQL: depende de un repositorio inyectado,
lo que permite probar las validaciones con un repositorio de memoria.
"""

from datetime import datetime
from decimal import Decimal
import re

from app.modelo.cuenta import Cuenta
from app.modelo.movimiento_financiero import MovimientoFinanciero
from app.modelo.transferencia import Transferencia

# Decisiones registradas con el autor: monedas COP/USD y tipos INGRESO/GASTO.
TIPOS_VALIDOS = ("INGRESO", "GASTO")
MONEDAS_VALIDAS = ("COP", "USD")

# Formato de valor aceptado: dígitos con parte decimal opcional (punto o coma).
# No se aceptan separadores de miles para evitar ambigüedades (1.500 → ¿mil quinientos o uno y medio?).
PATRON_VALOR = re.compile(r"^\d+([.,]\d{1,2})?$")

# Catálogo de símbolos de cuenta (los íconos de app/gui/recursos/iconos).
SIMBOLOS_VALIDOS = (
    "cash", "banco", "criptomonedas", "tarjeta_credito", "tarjeta_debito",
    "bolsa", "moneda", "euro", "tap_and_pay", "paypal", "boveda", "puerquito",
)

# Color en formato #RRGGBB.
PATRON_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


class ErrorValidacion(Exception):
    """Se lanza cuando los datos de un movimiento no cumplen las reglas."""


class GestorFinanciero:
    """Coordina las operaciones sobre los movimientos financieros."""

    def __init__(self, repositorio):
        self._repositorio = repositorio

    # ------------------------------------------------------------------
    # Registro
    # ------------------------------------------------------------------

    def registrar_movimiento(
        self,
        tipo,
        fecha_texto,
        valor_texto,
        moneda,
        categoria,
        descripcion=None,
    ) -> MovimientoFinanciero:
        """Valida los datos y guarda el movimiento en el repositorio.

        Lanza ErrorValidacion con un mensaje comprensible si algún dato
        no cumple las reglas. Solo devuelve un movimiento si se guardó.
        """
        tipo_movimiento = self._validar_tipo(tipo)
        fecha = self._validar_fecha(fecha_texto)
        valor = self._validar_valor(valor_texto)
        moneda_valida = self._validar_moneda(moneda)
        categoria_valida = self._validar_categoria(categoria)
        descripcion_valida = self._validar_descripcion(descripcion)

        movimiento = MovimientoFinanciero(
            id=None,
            tipo_movimiento=tipo_movimiento,
            fecha=fecha,
            valor=valor,
            moneda=moneda_valida,
            categoria=categoria_valida,
            descripcion=descripcion_valida,
        )
        return self._repositorio.insertar_movimiento(movimiento)

    # ------------------------------------------------------------------
    # Consulta y eliminación
    # ------------------------------------------------------------------

    def obtener_categorias(self):
        """Devuelve los nombres de las categorías del catálogo."""
        return self._repositorio.obtener_categorias()

    def obtener_movimientos(self, tipo=None):
        """Devuelve los movimientos guardados, opcionalmente filtrados por tipo."""
        return self._repositorio.obtener_movimientos(tipo)

    def resumen_del_mes(self, anno, mes):
        """Resume los movimientos de un mes, separados por moneda.

        Devuelve {moneda: {"ingresos": Decimal, "gastos": Decimal,
        "gastos_por_categoria": {categoria: Decimal}}}. No suma importes
        de monedas distintas ni calcula saldo: esa regla está pendiente
        de aprobación.
        """
        if not isinstance(anno, int) or not isinstance(mes, int):
            raise ValueError("El año y el mes deben ser números enteros.")
        if not 1 <= mes <= 12:
            raise ValueError("El mes debe estar entre 1 y 12.")

        filas = self._repositorio.resumen_mensual(anno, mes)
        resumen = {}
        for tipo, moneda, categoria, total in filas:
            datos = resumen.setdefault(
                moneda, {"ingresos": Decimal("0"), "gastos": Decimal("0"),
                         "gastos_por_categoria": {}}
            )
            if tipo == "INGRESO":
                datos["ingresos"] += total
            else:
                datos["gastos"] += total
                datos["gastos_por_categoria"][categoria] = (
                    datos["gastos_por_categoria"].get(categoria, Decimal("0"))
                    + total
                )
        return resumen

    def eliminar_movimiento(self, id_movimiento) -> bool:
        """Elimina un movimiento por su id. Devuelve True si existía."""
        return self._repositorio.eliminar_movimiento(id_movimiento)

    # ------------------------------------------------------------------
    # Cuentas (módulo Cuentas)
    # ------------------------------------------------------------------

    def crear_cuenta(
        self,
        nombre,
        moneda,
        saldo_inicial_texto,
        simbolo,
        color,
        incluye_en_total=True,
        nota=None,
    ) -> Cuenta:
        """Valida los datos de una cuenta nueva y la guarda.

        Obligatorios según lo acordado: nombre, símbolo y color. La moneda
        preseleccionada es COP y el saldo inicial puede quedar en 0.
        Lanza ErrorValidacion con un mensaje comprensible si algo falla.
        """
        nombre_valido = self._validar_nombre_cuenta(nombre)
        moneda_valida = self._validar_moneda(moneda)
        saldo = self._validar_saldo_inicial(saldo_inicial_texto)
        simbolo_valido = self._validar_simbolo(simbolo)
        color_valido = self._validar_color(color)
        nota_valida = self._validar_descripcion(nota)

        cuenta = Cuenta(
            id=None,
            nombre=nombre_valido,
            moneda=moneda_valida,
            saldo_inicial=saldo,
            simbolo=simbolo_valido,
            color=color_valido,
            incluye_en_total=bool(incluye_en_total),
            nota=nota_valida,
        )
        cuenta_guardada = self._repositorio.insertar_cuenta(cuenta)

        # El color usado se ofrece de nuevo en las próximas cuentas.
        try:
            self._repositorio.registrar_color_reciente(color_valido)
        except Exception:
            pass  # los colores recientes son un detalle, no un bloqueo.

        return cuenta_guardada

    def obtener_cuentas(self):
        """Devuelve las cuentas con su saldo actual: [(Cuenta, saldo)]."""
        return self._repositorio.obtener_cuentas()

    def obtener_cuenta(self, id_cuenta):
        """Devuelve una cuenta por su id, o None si no existe."""
        return self._repositorio.obtener_cuenta(id_cuenta)

    def obtener_colores_recientes(self):
        """Devuelve los últimos colores usados en cuentas."""
        return self._repositorio.obtener_colores_recientes()

    # ------------------------------------------------------------------
    # Transferencias entre cuentas
    # ------------------------------------------------------------------

    def crear_transferencia(
        self,
        cuenta_origen_id,
        cuenta_destino_id,
        valor_texto,
        fecha_texto,
        comentarios=None,
        imagen=None,
    ) -> Transferencia:
        """Valida y registra una transferencia entre dos cuentas.

        Reglas acordadas:
        - Solo entre cuentas de la misma moneda (no hay conversión aprobada).
        - La cuenta de origen debe tener saldo suficiente (se exige).
        - Cuentas de origen y destino distintas.
        """
        if cuenta_origen_id == cuenta_destino_id:
            raise ErrorValidacion(
                "Las cuentas de origen y destino deben ser distintas."
            )

        origen = self._repositorio.obtener_cuenta(cuenta_origen_id)
        destino = self._repositorio.obtener_cuenta(cuenta_destino_id)
        if origen is None or destino is None:
            raise ErrorValidacion("Seleccione las cuentas de origen y destino.")

        if origen.moneda != destino.moneda:
            raise ErrorValidacion(
                "Solo se pueden transferir entre cuentas de la misma moneda "
                f"(origen: {origen.moneda}, destino: {destino.moneda})."
            )

        valor = self._validar_valor(valor_texto)
        fecha = self._validar_fecha(fecha_texto)
        comentarios_validos = self._validar_descripcion(comentarios)
        if imagen is not None and not isinstance(imagen, str):
            raise ErrorValidacion("La imagen adjunta no es válida.")
        if imagen is not None and len(imagen) > 300:
            raise ErrorValidacion("La ruta de la imagen es demasiado larga.")

        saldos = self._repositorio.saldos_de_cuentas()
        saldo_origen = saldos.get(cuenta_origen_id, Decimal("0"))
        if saldo_origen < valor:
            raise ErrorValidacion(
                f"La cuenta «{origen.nombre}» no tiene saldo suficiente: "
                f"disponible {saldo_origen}, se intenta transferir {valor}."
            )

        transferencia = Transferencia(
            id=None,
            cuenta_origen_id=cuenta_origen_id,
            cuenta_destino_id=cuenta_destino_id,
            valor=valor,
            moneda=origen.moneda,
            fecha=fecha,
            comentarios=comentarios_validos,
            imagen=imagen,
        )
        return self._repositorio.insertar_transferencia(transferencia)

    def obtener_transferencias(self, fecha_inicio=None, fecha_fin=None):
        """Devuelve transferencias, opcionalmente en un rango de fechas.

        Cada fila es (id, fecha, nombre_origen, nombre_destino, valor,
        moneda, comentarios, imagen).
        """
        return self._repositorio.obtener_transferencias(fecha_inicio, fecha_fin)

    # ------------------------------------------------------------------
    # Validaciones de cuentas (mensajes en español para el usuario)
    # ------------------------------------------------------------------

    def _validar_nombre_cuenta(self, nombre):
        if not isinstance(nombre, str) or not nombre.strip():
            raise ErrorValidacion("Escriba un nombre para la cuenta.")
        texto = nombre.strip()
        if len(texto) > 60:
            raise ErrorValidacion("El nombre de la cuenta no puede superar 60 caracteres.")
        return texto

    def _validar_saldo_inicial(self, saldo_texto):
        """El saldo inicial es obligatorio pero puede ser 0; vacío = 0."""
        if saldo_texto is None:
            return Decimal("0")
        if not isinstance(saldo_texto, str):
            raise ErrorValidacion("El saldo inicial debe ser un número.")
        texto = saldo_texto.strip()
        if not texto:
            return Decimal("0")
        if not PATRON_VALOR.match(texto):
            raise ErrorValidacion(
                "El saldo inicial debe ser un número mayor o igual a cero, "
                "sin separadores de miles (ejemplos válidos: 0, 500000, 500000.50)."
            )
        saldo = Decimal(texto.replace(",", "."))
        if saldo < 0:
            raise ErrorValidacion("El saldo inicial no puede ser negativo.")
        return saldo

    def _validar_simbolo(self, simbolo):
        if simbolo not in SIMBOLOS_VALIDOS:
            raise ErrorValidacion("Seleccione un símbolo para la cuenta.")
        return simbolo

    def _validar_color(self, color):
        if not isinstance(color, str) or not PATRON_COLOR.match(color):
            raise ErrorValidacion("Seleccione un color para la cuenta (formato #RRGGBB).")
        return color.upper()

    # ------------------------------------------------------------------
    # Validaciones (mensajes en español, pensados para mostrarse al usuario)
    # ------------------------------------------------------------------

    def _validar_tipo(self, tipo):
        if not isinstance(tipo, str) or tipo.strip().upper() not in TIPOS_VALIDOS:
            permitidos = " o ".join(TIPOS_VALIDOS)
            raise ErrorValidacion(f"El tipo de movimiento debe ser {permitidos}.")
        return tipo.strip().upper()

    def _validar_fecha(self, fecha_texto):
        if not isinstance(fecha_texto, str):
            raise ErrorValidacion("La fecha debe tener el formato AAAA-MM-DD.")
        try:
            return datetime.strptime(fecha_texto.strip(), "%Y-%m-%d").date()
        except ValueError:
            raise ErrorValidacion(
                "La fecha debe tener el formato AAAA-MM-DD y ser un día real "
                "(ejemplo: 2026-11-01)."
            ) from None

    def _validar_valor(self, valor_texto):
        if not isinstance(valor_texto, str):
            raise ErrorValidacion("El valor debe ser un número mayor que cero.")
        texto = valor_texto.strip()
        if not PATRON_VALOR.match(texto):
            raise ErrorValidacion(
                "El valor debe ser un número mayor que cero, sin separadores "
                "de miles (ejemplos válidos: 15000 o 15000.50)."
            )
        valor = Decimal(texto.replace(",", "."))
        if valor <= 0:
            raise ErrorValidacion("El valor debe ser mayor que cero.")
        return valor

    def _validar_moneda(self, moneda):
        if not isinstance(moneda, str) or moneda.strip().upper() not in MONEDAS_VALIDAS:
            permitidas = " o ".join(MONEDAS_VALIDAS)
            raise ErrorValidacion(f"La moneda debe ser {permitidas}.")
        return moneda.strip().upper()

    def _validar_categoria(self, categoria):
        if not isinstance(categoria, str) or not categoria.strip():
            raise ErrorValidacion("Seleccione una categoría de la lista.")
        nombre = categoria.strip()
        categorias = self._repositorio.obtener_categorias()
        if nombre not in categorias:
            raise ErrorValidacion(
                f"La categoría «{nombre}» no existe en el catálogo."
            )
        return nombre

    def _validar_descripcion(self, descripcion):
        """La descripción es opcional: vacía se guarda como None."""
        if descripcion is None:
            return None
        texto = descripcion.strip()
        if not texto:
            return None
        if len(texto) > 200:
            raise ErrorValidacion(
                "La descripción no puede superar 200 caracteres."
            )
        return texto


def totales_por_moneda(movimientos):
    """Suma los importes de una lista de movimientos, separados por moneda.

    Nunca suma importes de monedas distintas: devuelve un diccionario
    {moneda: Decimal} hasta que se apruebe una regla de conversión.
    """
    totales = {}
    for movimiento in movimientos:
        acumulado = totales.get(movimiento.moneda, Decimal("0"))
        totales[movimiento.moneda] = acumulado + movimiento.valor
    return totales


def totales_cuentas_por_moneda(cuentas_con_saldo):
    """Suma el saldo de las cuentas, separado por moneda.

    Solo cuentan las cuentas con incluye_en_total activado. Nunca suma
    monedas distintas: devuelve {moneda: Decimal} hasta que se apruebe una
    regla de conversión.
    """
    totales = {}
    for cuenta, saldo in cuentas_con_saldo:
        if not cuenta.incluye_en_total:
            continue
        acumulado = totales.get(cuenta.moneda, Decimal("0"))
        totales[cuenta.moneda] = acumulado + saldo
    return totales
