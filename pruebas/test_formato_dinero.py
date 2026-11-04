"""Pruebas del formato de dinero con separadores colombianos."""

from app.gui.campo_moneda import (
    formatear_dinero,
    limpiar_dinero,
)
from app.gui.dialogo_color import hex_a_hsv, hsv_a_hex


# ----------------------------------------------------------------------
# Separadores de miles (punto) y millones (comilla arriba)
# ----------------------------------------------------------------------

def test_miles_se_separan_con_punto():
    assert formatear_dinero("1000") == "1.000"
    assert formatear_dinero("10000") == "10.000"
    assert formatear_dinero("100000") == "100.000"
    assert formatear_dinero("999") == "999"


def test_millones_se_separan_con_comilla_arriba():
    assert formatear_dinero("1000000") == "1'000.000"
    assert formatear_dinero("1500000") == "1'500.000"
    assert formatear_dinero("12345678") == "12'345.678"


def test_decimales_se_conservan_con_coma():
    assert formatear_dinero("1500000,5") == "1'500.000,5"
    assert formatear_dinero("1500000,50") == "1'500.000,50"


def test_limpiar_dinero_quita_separadores():
    assert limpiar_dinero("1'500.000,50") == "1500000,50"
    assert limpiar_dinero("1.000") == "1000"


def test_limpiar_y_formatear_son_inversos():
    for crudo in ("1000", "1500000", "1500000,50", "12345678"):
        assert limpiar_dinero(formatear_dinero(crudo)) == crudo


# ----------------------------------------------------------------------
# Conversión de color (selector propio)
# ----------------------------------------------------------------------

def test_hsv_a_hex_y_vuelta_atras():
    # Dorado del tema: #FBB718.
    tono, saturacion, brillo = hex_a_hsv("#FBB718")
    assert hsv_a_hex(tono, saturacion, brillo) == "#FBB718"


def test_hsv_a_hex_blanco_y_negro():
    assert hsv_a_hex(0.0, 0.0, 1.0) == "#FFFFFF"
    assert hsv_a_hex(0.0, 0.0, 0.0) == "#000000"
