"""Íconos de cuentas: PNG re-colorables con Pillow.

Los íconos vienen de Bootstrap Icons y Material Design Icons (licencias
MIT, ver app/gui/recursos/iconos/LICENSE-*.txt) y se almacenan como
máscaras en blanco sobre fondo transparente. Esta función les da el color
que el usuario elija (gris por defecto) y devuelve una imagen lista para
mostrar en tkinter (ImageTk.PhotoImage).
"""

from pathlib import Path

from PIL import Image, ImageTk

RUTA_ICONOS = Path(__file__).resolve().parent / "recursos" / "iconos"

# Color gris por defecto de los íconos (según lo acordado).
GRIS = "#8A8F98"

# Caché de imágenes ya generadas: evita reprocesar el mismo ícono/color.
_cache = {}


def icono_pil(clave, color=GRIS, tamano=32):
    """Devuelve la imagen Pillow del ícono `clave` pintado en `color`.

    `clave` es una de las del catálogo (ver app/gui/recursos/iconos).
    """
    archivo = RUTA_ICONOS / f"{clave}.png"
    if not archivo.exists():
        archivo = RUTA_ICONOS / "moneda.png"

    # Carga la máscara y la escala al tamaño pedido.
    mascara = Image.open(archivo).convert("RGBA").resize(
        (tamano, tamano), Image.LANCZOS)

    # Pinta un rectángulo del color elegido y usa el alfa del ícono como
    # molde: el resultado es el ícono con ese color exacto.
    capa_color = Image.new("RGBA", mascara.size, _hexa_rgba(color))
    pintado = capa_color.copy()
    pintado.putalpha(mascara.getchannel("A"))
    return pintado


def icono_ctk(clave, color=GRIS, tamano=32):
    """Devuelve una CTkImage del ícono `clave` pintado en `color`.

    Es la versión para widgets de customtkinter (CTkLabel, CTkButton):
    con PhotoImage esos widgets muestran una advertencia de que la
    imagen no se escala bien en pantallas HiDPI.
    """
    import customtkinter as ctk

    cache_clave = ("ctk", clave, str(color).upper(), tamano)
    if cache_clave in _cache:
        return _cache[cache_clave]

    imagen = ctk.CTkImage(
        light_image=icono_pil(clave, color, tamano),
        dark_image=icono_pil(clave, color, tamano),
        size=(tamano, tamano),
    )
    _cache[cache_clave] = imagen
    return imagen


def icono_tk(clave, color=GRIS, tamano=32):
    """Devuelve una PhotoImage del ícono `clave` pintado en `color`.

    Requiere que ya exista una ventana tkinter (la crea la aplicación).
    Mantiene una referencia interna para que tkinter no la recolecte.
    Se usa donde tkinter espera PhotoImage (p. ej. el Treeview).
    """
    cache_clave = (clave, str(color).upper(), tamano)
    if cache_clave in _cache:
        return _cache[cache_clave]

    foto = ImageTk.PhotoImage(icono_pil(clave, color, tamano))
    _cache[cache_clave] = foto
    return foto


def _hexa_rgba(color):
    """Convierte '#RRGGBB' a una tupla (R, G, B, 255) para Pillow."""
    texto = str(color).lstrip("#")
    return (int(texto[0:2], 16), int(texto[2:4], 16),
            int(texto[4:6], 16), 255)
