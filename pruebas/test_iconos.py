"""Pruebas del pintado de íconos de cuentas (Pillow, sin ventana tkinter)."""

from app.gui.iconos import GRIS, icono_pil


def test_icono_se_pinta_del_color_elegido():
    imagen = icono_pil("banco", "#FBB718", 32)
    assert imagen.size == (32, 32)
    # El píxel central es opaco (está dentro del dibujo del banco).
    rojo, verde, azul, alfa = imagen.getpixel((16, 16))
    assert alfa > 0
    # El color es el elegido, no el gris por defecto.
    assert (rojo, verde, azul) == (0xFB, 0xB7, 0x18)


def test_icono_gris_por_defecto():
    imagen = icono_pil("puerquito", GRIS, 48)
    assert imagen.size == (48, 48)


def test_icono_inexistente_usa_respaldado():
    """Un símbolo desconocido no rompe: usa el ícono de moneda."""
    imagen = icono_pil("clave_que_no_existe", "#FFFFFF", 32)
    assert imagen.size == (32, 32)
