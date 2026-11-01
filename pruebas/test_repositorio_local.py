"""Pruebas de integración de RepositorioLocal contra PostgreSQL local.

Usan la configuración real del proyecto (archivo .env), por lo que
requieren PostgreSQL en ejecución y la base de datos `nexsaldo` ya
preparada. Todos los datos insertados son ficticios y se eliminan al
final de cada prueba.

Si no existe el archivo .env, estas pruebas se omiten (no fallan).
"""

from datetime import date
from decimal import Decimal

import pytest

from app.configuracion import cargar_configuracion_bd
from app.gestor.gestor_financiero import GestorFinanciero
from app.modelo.movimiento_financiero import MovimientoFinanciero
from app.repositorio.repositorio_local import RepositorioLocal

# Repositorio y gestor compartidos por las pruebas de este módulo.
repositorio = None
gestor = None


def _configurar():
    """Crea el repositorio si hay configuración disponible; si no, omite pruebas."""
    global repositorio, gestor
    if repositorio is None:
        try:
            repositorio = RepositorioLocal(cargar_configuracion_bd())
            repositorio.conectar()
        except Exception:
            pytest.skip(
                "No se pudo conectar a PostgreSQL con la configuración de .env; "
                "pruebas de integración omitidas."
            )
        gestor = GestorFinanciero(repositorio)
    return gestor


def _movimiento_ficticio(**extras):
    """Crea un movimiento claramente ficticio para las pruebas."""
    datos = dict(
        id=None,
        tipo_movimiento="GASTO",
        fecha=date(2026, 11, 1),
        valor=Decimal("12345.67"),
        moneda="COP",
        categoria="Otros gastos",
        descripcion="dato ficticio de prueba automatizada",
    )
    datos.update(extras)
    return MovimientoFinanciero(**datos)


def _limpiar_movimientos_ficticios(repositorio):
    """Elimina todos los movimientos ficticios creados por las pruebas."""
    for movimiento in repositorio.obtener_movimientos():
        if movimiento.descripcion == "dato ficticio de prueba automatizada":
            repositorio.eliminar_movimiento(movimiento.id)


def test_insertar_y_consultar_movimiento():
    gestor = _configurar()
    repositorio = gestor._repositorio
    _limpiar_movimientos_ficticios(repositorio)

    guardado = repositorio.insertar_movimiento(_movimiento_ficticio())
    assert guardado.id is not None

    consultados = repositorio.obtener_movimientos()
    propio = [m for m in consultados if m.id == guardado.id]
    assert len(propio) == 1
    assert propio[0].valor == Decimal("12345.67")
    assert propio[0].categoria == "Otros gastos"

    repositorio.eliminar_movimiento(guardado.id)


def test_filtro_por_tipo():
    gestor = _configurar()
    repositorio = gestor._repositorio
    _limpiar_movimientos_ficticios(repositorio)

    gasto = repositorio.insertar_movimiento(_movimiento_ficticio())
    ingreso = repositorio.insertar_movimiento(_movimiento_ficticio(
        tipo_movimiento="INGRESO", categoria="Otros ingresos",
        descripcion="dato ficticio de prueba automatizada",
    ))

    gastos = repositorio.obtener_movimientos("GASTO")
    assert all(m.tipo_movimiento == "GASTO" for m in gastos)
    assert gasto.id in [m.id for m in gastos]
    assert ingreso.id not in [m.id for m in gastos]

    repositorio.eliminar_movimiento(gasto.id)
    repositorio.eliminar_movimiento(ingreso.id)


def test_eliminar_movimiento_inexistente_devuelve_falso():
    gestor = _configurar()
    repositorio = gestor._repositorio
    assert repositorio.eliminar_movimiento(-1) is False


def test_categoria_inexistente_no_se_guarda():
    gestor = _configurar()
    repositorio = gestor._repositorio
    movimiento = _movimiento_ficticio(categoria="Categoría que no existe")
    with pytest.raises(LookupError):
        repositorio.insertar_movimiento(movimiento)


def test_flujo_completo_por_el_gestor():
    """Registro válido vía GestorFinanciero y eliminación posterior."""
    gestor = _configurar()
    repositorio = gestor._repositorio
    _limpiar_movimientos_ficticios(repositorio)

    movimiento = gestor.registrar_movimiento(
        tipo="Gasto",
        fecha_texto="2026-11-01",
        valor_texto="99999.99",
        moneda="COP",
        categoria="Otros gastos",
        descripcion="dato ficticio de prueba automatizada",
    )
    assert movimiento.id is not None
    assert gestor.eliminar_movimiento(movimiento.id) is True


def test_resumen_mensual_agrupa_por_tipo_moneda_y_categoria():
    """Inserta gastos ficticios y verifica la agrupación del resumen."""
    gestor = _configurar()
    repositorio = gestor._repositorio
    _limpiar_movimientos_ficticios(repositorio)

    primero = repositorio.insertar_movimiento(_movimiento_ficticio(
        valor=Decimal("10000")))
    segundo = repositorio.insertar_movimiento(_movimiento_ficticio(
        valor=Decimal("5000"), categoria="Alimentación"))
    try:
        filas = repositorio.resumen_mensual(2026, 11)
        fila_gastos = [f for f in filas
                       if f[0] == "GASTO" and f[1] == "COP"
                       and f[2] == "Otros gastos"]
        assert len(fila_gastos) == 1
        assert fila_gastos[0][3] == Decimal("10000")

        fila_alimentacion = [f for f in filas
                            if f[2] == "Alimentación"]
        assert len(fila_alimentacion) == 1
        assert fila_alimentacion[0][3] == Decimal("5000")
    finally:
        repositorio.eliminar_movimiento(primero.id)
        repositorio.eliminar_movimiento(segundo.id)
