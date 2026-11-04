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
    SIMBOLOS_VALIDOS,
    totales_cuentas_por_moneda,
    totales_por_moneda,
)
from app.modelo.cuenta import Cuenta
from app.modelo.movimiento_financiero import MovimientoFinanciero
from app.modelo.transferencia import Transferencia


class RepositorioDeMemoria:
    """Repositorio ficticio para pruebas: guarda movimientos en una lista."""

    def __init__(self, categorias):
        self._categorias = categorias
        self._movimientos = []
        self._cuentas = {}
        self._transferencias = []
        self._colores_recientes = {}
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

    # --- Cuentas y transferencias (módulo Cuentas) ---

    def insertar_cuenta(self, cuenta):
        guardada = cuenta.con_id(self._siguiente_id)
        self._siguiente_id += 1
        self._cuentas[guardada.id] = guardada
        return guardada

    def obtener_cuentas(self):
        resultado = []
        for cuenta in self._cuentas.values():
            saldo = self._saldo_de(cuenta)
            resultado.append((cuenta, saldo))
        return resultado

    def obtener_cuenta(self, id_cuenta):
        return self._cuentas.get(id_cuenta)

    def _saldo_de(self, cuenta):
        saldo = cuenta.saldo_inicial
        for t in self._transferencias:
            if t.cuenta_destino_id == cuenta.id:
                saldo += t.valor
            if t.cuenta_origen_id == cuenta.id:
                saldo -= t.valor
        return saldo

    def saldos_de_cuentas(self):
        return {c.id: self._saldo_de(c) for c in self._cuentas.values()}

    def insertar_transferencia(self, transferencia):
        guardada = transferencia.con_id(self._siguiente_id)
        self._siguiente_id += 1
        self._transferencias.append(guardada)
        return guardada

    def obtener_transferencias(self, fecha_inicio=None, fecha_fin=None):
        filas = []
        for t in self._transferencias:
            if fecha_inicio is not None and t.fecha < fecha_inicio:
                continue
            if fecha_fin is not None and t.fecha > fecha_fin:
                continue
            origen = self._cuentas[t.cuenta_origen_id].nombre
            destino = self._cuentas[t.cuenta_destino_id].nombre
            filas.append((t.id, t.fecha, origen, destino, t.valor, t.moneda,
                          t.comentarios, t.imagen))
        return filas

    def registrar_color_reciente(self, color):
        self._colores_recientes[color] = date.today()

    def obtener_colores_recientes(self, maximo=8):
        ordenados = sorted(self._colores_recientes.items(),
                           key=lambda par: par[1], reverse=True)
        return [color for color, _fecha in ordenados[:maximo]]


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


# ----------------------------------------------------------------------
# Cuentas (módulo Cuentas)
# ----------------------------------------------------------------------

def _cuenta_de_prueba(gestor, **extras):
    """Crea una cuenta ficticia con valores válidos."""
    datos = dict(
        nombre="Cuenta de prueba",
        moneda="COP",
        saldo_inicial_texto="1000",
        simbolo="banco",
        color="#FBB718",
        incluye_en_total=True,
        nota="cuenta ficticia de prueba automatizada",
    )
    datos.update(extras)
    return gestor.crear_cuenta(**datos)


def test_crear_cuenta_valida(gestor):
    cuenta = _cuenta_de_prueba(gestor)
    assert cuenta.id is not None
    assert cuenta.nombre == "Cuenta de prueba"
    assert cuenta.moneda == "COP"
    assert cuenta.saldo_inicial == Decimal("1000")
    assert cuenta.simbolo == "banco"
    assert cuenta.color == "#FBB718"
    assert cuenta.incluye_en_total is True


def test_crear_cuenta_rechaza_nombre_vacio(gestor):
    with pytest.raises(ErrorValidacion):
        _cuenta_de_prueba(gestor, nombre="   ")


def test_crear_cuenta_rechaza_falta_de_simbolo(gestor):
    with pytest.raises(ErrorValidacion):
        _cuenta_de_prueba(gestor, simbolo="simbolo_que_no_existe")


def test_crear_cuenta_rechaza_falta_de_color(gestor):
    with pytest.raises(ErrorValidacion):
        _cuenta_de_prueba(gestor, color="azul")


def test_crear_cuenta_rechaza_saldo_negativo(gestor):
    with pytest.raises(ErrorValidacion):
        _cuenta_de_prueba(gestor, saldo_inicial_texto="-100")


def test_crear_cuenta_saldo_vacio_es_cero(gestor):
    cuenta = _cuenta_de_prueba(gestor, saldo_inicial_texto="")
    assert cuenta.saldo_inicial == Decimal("0")


def test_crear_cuenta_rechaza_moneda_invalida(gestor):
    with pytest.raises(ErrorValidacion):
        _cuenta_de_prueba(gestor, moneda="EUR")


def test_crear_cuenta_registra_color_reciente(gestor):
    _cuenta_de_prueba(gestor)
    assert "#FBB718" in gestor.obtener_colores_recientes()


def test_totales_cuentas_separan_monedas_y_respetan_exclusion(gestor):
    _cuenta_de_prueba(gestor, nombre="Principal COP",
                      saldo_inicial_texto="4000000")
    _cuenta_de_prueba(gestor, nombre="Amex COP",
                      saldo_inicial_texto="1000000")
    _cuenta_de_prueba(gestor, nombre="Ahorritos USD", moneda="USD",
                      saldo_inicial_texto="120",
                      incluye_en_total=False)

    totales = totales_cuentas_por_moneda(gestor.obtener_cuentas())

    assert totales["COP"] == Decimal("5000000")
    # La cuenta USD excluida del balance total no suma.
    assert "USD" not in totales


# ----------------------------------------------------------------------
# Transferencias entre cuentas
# ----------------------------------------------------------------------

def test_transferencia_valida_mueve_el_saldo(gestor):
    principal = _cuenta_de_prueba(gestor, nombre="Principal",
                                  saldo_inicial_texto="5000000")
    amex = _cuenta_de_prueba(gestor, nombre="Amex",
                             saldo_inicial_texto="0")

    transferencia = gestor.crear_transferencia(
        cuenta_origen_id=principal.id, cuenta_destino_id=amex.id,
        valor_texto="400000", fecha_texto="2026-11-03",
        comentarios="pago de tarjeta Amex",
    )
    assert transferencia.id is not None
    assert transferencia.valor == Decimal("400000")
    assert transferencia.moneda == "COP"

    saldos = {c.nombre: s for c, s in gestor.obtener_cuentas()}
    assert saldos["Principal"] == Decimal("4600000")
    assert saldos["Amex"] == Decimal("400000")


def test_transferencia_rechaza_saldo_insuficiente(gestor):
    origen = _cuenta_de_prueba(gestor, saldo_inicial_texto="100")
    destino = _cuenta_de_prueba(gestor, nombre="Otra")
    with pytest.raises(ErrorValidacion):
        gestor.crear_transferencia(
            cuenta_origen_id=origen.id, cuenta_destino_id=destino.id,
            valor_texto="500", fecha_texto="2026-11-03",
        )


def test_transferencia_rechaza_misma_cuenta(gestor):
    cuenta = _cuenta_de_prueba(gestor)
    with pytest.raises(ErrorValidacion):
        gestor.crear_transferencia(
            cuenta_origen_id=cuenta.id, cuenta_destino_id=cuenta.id,
            valor_texto="10", fecha_texto="2026-11-03",
        )


def test_transferencia_rechaza_monedas_distintas(gestor):
    origen = _cuenta_de_prueba(gestor, nombre="Bancolombia")
    destino = _cuenta_de_prueba(gestor, nombre="Cuenta USD", moneda="USD",
                               saldo_inicial_texto="50")
    with pytest.raises(ErrorValidacion):
        gestor.crear_transferencia(
            cuenta_origen_id=origen.id, cuenta_destino_id=destino.id,
            valor_texto="10", fecha_texto="2026-11-03",
        )


def test_transferencia_rechaza_valor_invalido(gestor):
    origen = _cuenta_de_prueba(gestor, nombre="Con plata",
                              saldo_inicial_texto="10000")
    destino = _cuenta_de_prueba(gestor, nombre="Destino")
    with pytest.raises(ErrorValidacion):
        gestor.crear_transferencia(
            cuenta_origen_id=origen.id, cuenta_destino_id=destino.id,
            valor_texto="0", fecha_texto="2026-11-03",
        )


def test_transferencias_se_filtran_por_rango_de_fechas(gestor):
    origen = _cuenta_de_prueba(gestor, nombre="Con plata",
                              saldo_inicial_texto="100000")
    destino = _cuenta_de_prueba(gestor, nombre="Destino")
    gestor.crear_transferencia(origen.id, destino.id, "1000",
                               "2026-10-31")
    gestor.crear_transferencia(origen.id, destino.id, "2000",
                               "2026-11-01")
    gestor.crear_transferencia(origen.id, destino.id, "3000",
                               "2026-11-02")

    noviembre = gestor.obtener_transferencias(
        date(2026, 11, 1), date(2026, 11, 30))
    assert len(noviembre) == 2

    solo_dos = gestor.obtener_transferencias(
        date(2026, 11, 2), date(2026, 11, 2))
    assert len(solo_dos) == 1
    assert solo_dos[0][4] == Decimal("3000")
