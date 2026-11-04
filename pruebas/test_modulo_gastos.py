"""Pruebas unitarias para el Módulo de Gastos, categorías personalizadas, gastos programados y etiquetas."""

from datetime import date, timedelta
from decimal import Decimal
import pytest

from app.gestor.gestor_financiero import (
    CATALOGO_SIMBOLOS_CATEGORIAS,
    CATEGORIAS_GASTO_PREDETERMINADAS,
    ErrorValidacion,
    GestorFinanciero,
)
from app.modelo.cuenta import Cuenta
from app.modelo.movimiento_financiero import MovimientoFinanciero


class RepositorioFalsoGastos:
    """Doble de prueba en memoria compatible con RepositorioDeMemoria."""

    def __init__(self):
        self._categorias = [
            "Salud",
            "Ocio",
            "Casa",
            "Café",
            "Educación",
            "Regalos",
            "Alimentación",
            "Transporte",
        ]
        self._movimientos = []
        self._cuentas = {}
        self._colores_recientes = []
        self._siguiente_id = 1

    def obtener_categorias(self):
        return list(self._categorias)

    def insertar_movimiento(self, movimiento: MovimientoFinanciero) -> MovimientoFinanciero:
        asignado = movimiento.con_id(self._siguiente_id)
        self._siguiente_id += 1
        self._movimientos.append(asignado)
        return asignado

    def obtener_movimientos(self, tipo=None):
        if tipo is None:
            return list(self._movimientos)
        return [m for m in self._movimientos if m.tipo_movimiento == tipo]

    def eliminar_movimiento(self, id_movimiento: int) -> bool:
        for idx, m in enumerate(self._movimientos):
            if m.id == id_movimiento:
                del self._movimientos[idx]
                return True
        return False

    def insertar_cuenta(self, cuenta: Cuenta) -> Cuenta:
        asignada = cuenta.con_id(self._siguiente_id)
        self._siguiente_id += 1
        self._cuentas[asignada.id] = asignada
        return asignada

    def obtener_cuentas(self):
        resultado = []
        for cid, c in self._cuentas.items():
            gastos = sum(
                (m.valor for m in self._movimientos if m.cuenta_id == cid and m.tipo_movimiento == "GASTO"),
                Decimal("0"),
            )
            resultado.append((c, c.saldo_inicial - gastos))
        return resultado

    def obtener_cuenta(self, id_cuenta: int):
        return self._cuentas.get(id_cuenta)

    def registrar_color_reciente(self, color: str):
        color = color.upper()
        if color in self._colores_recientes:
            self._colores_recientes.remove(color)
        self._colores_recientes.insert(0, color)

    def obtener_colores_recientes(self, maximo=8):
        return self._colores_recientes[:maximo]


@pytest.fixture
def gestor_gastos():
    return GestorFinanciero(RepositorioFalsoGastos())


def test_siete_categorias_predeterminadas_con_iconos_requeridos(gestor_gastos):
    categorias = gestor_gastos.obtener_categorias_detalladas("GASTO")
    mapa = {c.nombre: c.simbolo for c in categorias}
    assert mapa["Salud"] == "corazon_pulso"
    assert mapa["Ocio"] == "billetera"
    assert mapa["Casa"] == "casa"
    assert mapa["Café"] == "cubiertos"
    assert mapa["Educación"] == "graduacion"
    assert mapa["Regalos"] == "regalo"
    assert mapa["Alimentación"] == "mercado"


def test_catalogo_simbolos_incluye_especificos_y_grupos():
    assert "Finanzas" in CATALOGO_SIMBOLOS_CATEGORIAS
    assert "Transporte" in CATALOGO_SIMBOLOS_CATEGORIAS
    assert "Vacaciones y Viajes" in CATALOGO_SIMBOLOS_CATEGORIAS
    assert "Compras" in CATALOGO_SIMBOLOS_CATEGORIAS
    assert "Comida y Bebida" in CATALOGO_SIMBOLOS_CATEGORIAS
    assert "Casa y Hogar" in CATALOGO_SIMBOLOS_CATEGORIAS
    assert "Salud y Belleza" in CATALOGO_SIMBOLOS_CATEGORIAS

    claves_viajes = dict(CATALOGO_SIMBOLOS_CATEGORIAS["Vacaciones y Viajes"])
    assert "tickets" in claves_viajes
    assert "bikini" in claves_viajes

    claves_casa = dict(CATALOGO_SIMBOLOS_CATEGORIAS["Casa y Hogar"])
    assert "olla" in claves_casa
    assert "pintura" in claves_casa
    assert "lavadora" in claves_casa


def test_crear_categoria_customizada_con_gasto_programado_y_color_reciente(gestor_gastos):
    nueva = gestor_gastos.crear_categoria(
        nombre="Vacaciones Playa",
        tipo="GASTO",
        simbolo="bikini",
        color="#408FD1",
        gasto_programado=True,
        frecuencia="ANUAL",
    )
    assert nueva.nombre == "Vacaciones Playa"
    assert nueva.simbolo == "bikini"
    assert nueva.color == "#408FD1"
    assert nueva.gasto_programado is True
    assert nueva.frecuencia == "ANUAL"
    assert "#408FD1" in gestor_gastos.obtener_colores_recientes()


def test_registrar_gasto_por_defecto_cop_con_cuenta_etiquetas_comentario_y_foto(gestor_gastos):
    cuenta = gestor_gastos.crear_cuenta(
        nombre="Billetera Principal",
        moneda="COP",
        saldo_inicial_texto="500000",
        simbolo="cash",
        color="#166246",
    )
    et1 = gestor_gastos.crear_etiqueta("Mercado mensual", "#7DC98F")
    mov = gestor_gastos.registrar_gasto(
        valor_texto="125000,50",
        cuenta_id=cuenta.id,
        categoria="Alimentación",
        fecha_texto="2026-11-04",
        etiquetas=[et1.nombre, "Hogar"],
        comentario="Compra quincenal supermercado",
        imagen="adjuntos/recibo_prueba.png",
    )
    assert mov.id is not None
    assert mov.moneda == "COP"
    assert mov.valor == Decimal("125000.50")
    assert mov.cuenta_id == cuenta.id
    assert mov.etiquetas == ("Mercado mensual", "Hogar")
    assert mov.descripcion == "Compra quincenal supermercado"
    assert mov.imagen == "adjuntos/recibo_prueba.png"

    # El saldo de la cuenta disminuye con el gasto
    cuentas_actualizadas = dict(
        (c.id, saldo) for c, saldo in gestor_gastos.obtener_cuentas()
    )
    assert cuentas_actualizadas[cuenta.id] == Decimal("374999.50")


def test_resumen_gastos_por_periodo_personalizado(gestor_gastos):
    hoy = date.today()
    hace_3_dias = hoy - timedelta(days=3)
    hace_20_dias = hoy - timedelta(days=20)

    gestor_gastos.registrar_gasto(
        valor_texto="40000",
        moneda="COP",
        categoria="Salud",
        fecha_texto=hoy.isoformat(),
    )
    gestor_gastos.registrar_gasto(
        valor_texto="60000",
        moneda="COP",
        categoria="Café",
        fecha_texto=hace_3_dias.isoformat(),
    )
    gestor_gastos.registrar_gasto(
        valor_texto="200000",
        moneda="COP",
        categoria="Casa",
        fecha_texto=hace_20_dias.isoformat(),
    )

    resumen = gestor_gastos.resumen_gastos_periodo(
        fecha_inicio=hace_3_dias, fecha_fin=hoy
    )
    assert "COP" in resumen
    assert resumen["COP"]["total"] == Decimal("100000")
    assert resumen["COP"]["por_categoria"]["Salud"] == Decimal("40000")
    assert resumen["COP"]["por_categoria"]["Café"] == Decimal("60000")
    assert "Casa" not in resumen["COP"]["por_categoria"]


def test_periodo_sin_gastos_devuelve_diccionario_vacio(gestor_gastos):
    futuro_ini = date(2035, 1, 1)
    futuro_fin = date(2035, 1, 31)
    resumen = gestor_gastos.resumen_gastos_periodo(
        fecha_inicio=futuro_ini, fecha_fin=futuro_fin
    )
    assert resumen == {}
