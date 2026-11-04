"""Tema visual de NexSaldo (customtkinter).

Paleta tomada del mockup de la tesis (colores muestreados de la imagen
original): fondo esmeralda, barra lateral verde bosque, tarjetas verde
oscuro y acentos dorados. La prioridad es la legibilidad: los campos de
entrada usan fondo claro para que el texto digitado sea fácil de leer.
"""

import sys
from pathlib import Path

# Paleta de colores (muestreada del mockup de la pantalla inicial).
COLORES = {
    "fondo_lateral": "#0B3623",     # barra lateral: verde bosque oscuro
    "fondo_contenido": "#278960",   # área principal: verde esmeralda
    "fondo_tarjeta": "#166246",     # tarjetas: verde oscuro
    "boton_lateral": "#103725",     # botones de navegación en píldora
    "hover_lateral": "#0E2B1C",     # resaltado al pasar el mouse
    "acento": "#FBB718",            # dorado: botones principales y dona
    "acento_hover": "#E5A512",
    "texto": "#FFFFFF",
    "texto_secundario": "#CFE8DA",
    "exito": "#7DC98F",
    "error": "#F28C8C",
    "campo_fondo": "#F4F7F5",       # entradas de texto: fondo claro (legibilidad)
    "campo_texto": "#10241C",
    "borde_tabla": "#2E6B54",
}

# Colores de los segmentos de la dona (dorado, azul, verde del mockup).
COLORES_GRAFICA = [
    "#FBB718", "#408FD1", "#89BF50",
    "#F28C8C", "#BFD8CC", "#7DC98F",
]

# Colores predeterminados ofrecidos al crear una cuenta (del mockup:
# dorado, azul, verde; el resto del propio tema).
COLORES_PREDETERMINADOS = [
    "#FBB718", "#408FD1", "#89BF50",
    "#F28C8C", "#BFD8CC", "#7DC98F",
    "#FFFFFF", "#8A8F98",
]

def _cargar_instrument_sans():
    """Carga los TTF de Instrument Sans en Windows (solo este proceso).

    Los archivos vienen incluidos en app/gui/recursos/fuentes (licencia
    OFL, ver OFL.txt en esa carpeta). Devuelve el nombre de la familia si
    se cargó, o None si no (en ese caso se usa Segoe UI de respaldo).
    """
    carpeta = Path(__file__).resolve().parent / "recursos" / "fuentes"
    if sys.platform != "win32" or not carpeta.is_dir():
        return None
    try:
        import ctypes

        FR_PRIVATE = 0x10  # disponible solo para este proceso
        cargados = False
        for ttf in carpeta.glob("*.ttf"):
            if ctypes.windll.gdi32.AddFontResourceExW(str(ttf), FR_PRIVATE, 0):
                cargados = True
        return "Instrument Sans" if cargados else None
    except Exception:
        # Ante cualquier fallo, la interfaz usa Segoe UI sin detenerse.
        return None


# Tipografía del mockup (Instrument Sans) con respaldo en Segoe UI.
FUENTE = _cargar_instrument_sans() or "Segoe UI"


def configurar_tema():
    """Aplica el modo oscuro de customtkinter a toda la aplicación.

    Los colores de los widgets se fijan explícitamente con la paleta del
    mockup, así que no se carga un tema de color adicional.
    """
    import customtkinter as ctk

    ctk.set_appearance_mode("dark")


def configurar_tabla(raiz):
    """Configura los estilos ttk de la tabla de movimientos (Treeview).

    customtkinter no incluye tabla; se conserva el Treeview de ttk
    con colores del tema para que no destaque sobre el resto.
    """
    from tkinter import ttk

    estilo = ttk.Style(raiz)
    estilo.theme_use("clam")
    colores = COLORES

    estilo.configure("Tablita.Treeview", background=colores["fondo_tarjeta"],
                     foreground=colores["texto"],
                     fieldbackground=colores["fondo_tarjeta"],
                     rowheight=28, font=(FUENTE, 10), borderwidth=0)
    estilo.configure("Tablita.Treeview.Heading",
                     background=colores["boton_lateral"],
                     foreground=colores["acento"], font=(FUENTE, 10, "bold"),
                     relief="flat", borderwidth=0)
    estilo.map("Tablita.Treeview",
               background=[("selected", colores["acento"])],
               foreground=[("selected", "#10241C")])
    estilo.map("Tablita.Treeview.Heading",
               background=[("active", colores["fondo_tarjeta"])])
    raiz.option_add("*TCombobox*Listbox*Background", colores["campo_fondo"])
    raiz.option_add("*TCombobox*Listbox*Foreground", colores["campo_texto"])
