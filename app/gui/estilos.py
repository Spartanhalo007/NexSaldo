"""Tema visual de NexSaldo (customtkinter).

Paleta tomada del mockup de la tesis (colores muestreados de la imagen
original): fondo esmeralda, barra lateral verde bosque, tarjetas verde
oscuro y acentos dorados. La prioridad es la legibilidad: los campos de
entrada usan fondo claro para que el texto digitado sea fácil de leer.
"""

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

# Tipografía del mockup sobre Windows.
FUENTE = "Segoe UI"


def configurar_tema():
    """Aplica el modo oscuro de customtkinter a toda la aplicación."""
    import customtkinter as ctk

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark")


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
