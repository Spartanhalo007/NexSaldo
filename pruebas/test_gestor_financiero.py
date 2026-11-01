"""Pruebas del GestorFinanciero: validaciones de registro (CU-01 / RF-01).

Usan un repositorio de memoria, así que verifican las reglas de negocio
sin depender de PostgreSQL.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.gestor.gestor_financiero import (
    ErrorValidacion,
    GestorFinanciero,
    totales_por_moneda,
)
from app.modelo.movimiento_financiero import MovimientoFinanciero


class RepositorioDeMemoria:
    """Repositorio ficticio para pruebas: guarda movimientos en una lista."""

    def __init__(self, categorias):
        self._categorias = categorias
        self._movimientos = []
        self._siguiente_id = 1

    def obtener_categorias(self):
        return list(self._categorias)

    def insertar_movimiento(self, movimiento):
        guardado = movimiento.con_id(self._siguiente_id)
        self._siguiente_id += 1
        self._movimientos.append(guardado)
        return guardado

    def obtener_movimientos(self, tipo=None):
        if tipo is None:
            return list(self._movimientos)
        return [m for m in self._movimientos if m.tipo_movimiento == tipo]

    def eliminar_movimiento(self, id_movimiento):
        for movimiento in self._movimientos:
            if movimiento.id == id_movimiento:
                self._movimientos.remove(movimiento)
                return True
        return False

    def resumen_mensual(self, anno, mes):
        """Calcula el resumen en memoria, igual que el repositorio real."""
        acumulado = {}
        for m in self._movimientos:
            if m.fecha.year == anno and m.fecha.month == mes:
                clave = (m.tipo_movimiento, m.moneda, m.categoria)
                acumulado[clave] = acumulado.get(clave, Decimal("0")) + m.valor
        return [(tipo, moneda, categoria, total)
                for (tipo, moneda, categoria), total in acumulado.items()]


@pytest.fixture
def gestor():
    repositorio = RepositorioDeMemoria(
        ["Alimentación", "Salario", "Transporte"]
    )
    return GestorFinanciero(repositorio)


# ----------------------------------------------------------------------
# Registro válido
# ----------------------------------------------------------------------

def test_registro_valido_devuelve_movimiento_con_id(gestor):
    movimiento = gestor.registrar_movimiento(
        tipo="Gasto",
        fecha_texto="2026-11-01",
        valor_texto="15000",
        moneda="COP",
        categoria="Transporte",
        descripcion="dato ficticio de prueba",
    )
    assert movimiento.id == 1
    assert movimiento.tipo_movimiento == "GASTO"
    assert movimiento.fecha == date(2026, 11, 1)
    assert movimiento.valor == Decimal("15000")
    assert movimiento.moneda == "COP"
    assert movimiento.categoria == "Transporte"


def test_valor_con_coma_decimal_se_acepta(gestor):
    movimiento = gestor.registrar_movimiento(
        tipo="Ingreso",
        fecha_texto="2026-11-01",
        valor_texto="1500,50",
        moneda="COP",
        categoria="Salario",
    )
    assert movimiento.valor == Decimal("1500.50")


def test_descripcion_vacia_se_guarda_como_none(gestor):
    movimiento = gestor.registrar_movimiento(
        tipo="Ingreso",
        fecha_texto="2026-11-01",
        valor_texto="1000",
        moneda="USD",
        categoria="Salario",
        descripcion="   ",
    )
    assert movimiento.descripcion is None


def test_eliminacion_devuelve_verdadero_solo_si_existia(gestor):
    movimiento = gestor.registrar_movimiento(
        tipo="Gasto",
        fecha_texto="2026-11-01",
        valor_texto="100",
        moneda="COP",
        categoria="Transporte",
    )
    assert gestor.eliminar_movimiento(movimiento.id) is True
    assert gestor.eliminar_movimiento(movimiento.id) is False


# ----------------------------------------------------------------------
# Validaciones rechazadas
# ----------------------------------------------------------------------

@pytest.mark.parametrize("valor_invalido", ["0", "-5", "abc", "", "1.500", "15 000", "12,345"])
def test_valor_invalido_se_rechaza(gestor, valor_invalido):
    with pytest.raises(ErrorValidacion):
        gestor.registrar_movimiento(
            tipo="Gasto",
            fecha_texto="2026-11-01",
            valor_texto=valor_invalido,
            moneda="COP",
            categoria="Transporte",
        )


@pytest.mark.parametrize("fecha_invalida", ["31/12/2026", "2026-13-01", "texto", "", "2026-02-30"])
def test_fecha_invalida_se_rechaza(gestor, fecha_invalida):
    with pytest.raises(ErrorValidacion):
        gestor.registrar_movimiento(
            tipo="Gasto",
            fecha_texto=fecha_invalida,
            valor_texto="100",
            moneda="COP",
            categoria="Transporte",
        )


def test_tipo_invalido_se_rechaza(gestor):
    with pytest.raises(ErrorValidacion):
        gestor.registrar_movimiento(
            tipo="Préstamo",
            fecha_texto="2026-11-01",
            valor_texto="100",
            moneda="COP",
            categoria="Transporte",
        )


def test_moneda_invalida_se_rechaza(gestor):
    with pytest.raises(ErrorValidacion):
        gestor.registrar_movimiento(
            tipo="Gasto",
            fecha_texto="2026-11-01",
            valor_texto="100",
            moneda="EUR",
            categoria="Transporte",
        )


def test_categoria_vacia_se_rechaza(gestor):
    with pytest.raises(ErrorValidacion):
        gestor.registrar_movimiento(
            tipo="Gasto",
            fecha_texto="2026-11-01",
            valor_texto="100",
            moneda="COP",
            categoria="",
        )


def test_categoria_fuera_de_catalogo_se_rechaza(gestor):
    with pytest.raises(ErrorValidacion):
        gestor.registrar_movimiento(
            tipo="Gasto",
            fecha_texto="2026-11-01",
            valor_texto="100",
            moneda="COP",
            categoria="Mascotas",
        )


def test_descripcion_muy_larga_se_rechaza(gestor):
    with pytest.raises(ErrorValidacion):
        gestor.registrar_movimiento(
            tipo="Gasto",
            fecha_texto="2026-11-01",
            valor_texto="100",
            moneda="COP",
            categoria="Transporte",
            descripcion="x" * 201,
        )


# ----------------------------------------------------------------------
# Totales por moneda
# ----------------------------------------------------------------------

def test_totales_separan_monedas_sin_sumarlas():
    movimientos = [
        MovimientoFinanciero(1, "GASTO", date(2026, 11, 1), Decimal("100"), "COP", "Transporte"),
        MovimientoFinanciero(2, "GASTO", date(2026, 11, 1), Decimal("50"), "COP", "Salud"),
        MovimientoFinanciero(3, "GASTO", date(2026, 11, 1), Decimal("10"), "USD", "Salud"),
    ]
    totales = totales_por_moneda(movimientos)
    assert totales == {"COP": Decimal("150"), "USD": Decimal("10")}


def test_totales_con_lista_vacia():
    assert totales_por_moneda([]) == {}


# ----------------------------------------------------------------------
# Resumen del mes (preparación de RF-05)
# ----------------------------------------------------------------------

def test_resumen_del_mes_separa_monedas_y_categorias(gestor):
    gestor.registrar_movimiento("Ingreso", "2026-11-01", "1000000", "COP", "Salario")
    gestor.registrar_movimiento("Gasto", "2026-11-02", "30000", "COP", "Alimentación")
    gestor.registrar_movimiento("Gasto", "2026-11-03", "20000", "COP", "Alimentación")
    gestor.registrar_movimiento("Gasto", "2026-11-04", "500", "USD", "Alimentación")
    # De otro mes: no debe contar.
    gestor.registrar_movimiento("Gasto", "2026-10-31", "999", "COP", "Transporte")

    resumen = gestor.resumen_del_mes(2026, 11)

    assert resumen["COP"]["ingresos"] == Decimal("1000000")
    assert resumen["COP"]["gastos"] == Decimal("50000")
    assert resumen["COP"]["gastos_por_categoria"]["Alimentación"] == Decimal("50000")
    assert resumen["USD"]["gastos"] == Decimal("500")
    assert "Transporte" not in resumen["COP"]["gastos_por_categoria"]


def test_resumen_del_mes_sin_datos_devuelve_vacio(gestor):
    assert gestor.resumen_del_mes(2030, 1) == {}


def test_resumen_del_mes_rechaza_parametros_invalidos(gestor):
    with pytest.raises(ValueError):
        gestor.resumen_del_mes(2026, 13)
    with pytest.raises(ValueError):
        gestor.resumen_del_mes("2026", 11)
