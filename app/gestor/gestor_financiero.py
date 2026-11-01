"""Lógica de negocio y validaciones (GestorFinanciero del modelo de la tesis).

Coordina el registro, la consulta y la eliminación de movimientos.
No conoce tkinter ni PostgreSQL: depende de un repositorio inyectado,
lo que permite probar las validaciones con un repositorio de memoria.
"""

from datetime import datetime
from decimal import Decimal
import re

from app.modelo.movimiento_financiero import MovimientoFinanciero

# Decisiones registradas con el autor: monedas COP/USD y tipos INGRESO/GASTO.
TIPOS_VALIDOS = ("INGRESO", "GASTO")
MONEDAS_VALIDAS = ("COP", "USD")

# Formato de valor aceptado: dígitos con parte decimal opcional (punto o coma).
# No se aceptan separadores de miles para evitar ambigüedades (1.500 → ¿mil quinientos o uno y medio?).
PATRON_VALOR = re.compile(r"^\d+([.,]\d{1,2})?$")


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
