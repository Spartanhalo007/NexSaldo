"""Estilos visuales de NexSaldo.

Paleta tomada del mockup de la tesis (verde bosque oscuro, verde esmeralda
y acentos dorados, con texto blanco). La prioridad es la legibilidad: los
campos de entrada usan fondo claro para que el texto digitado sea fácil de
leer, aunque el resto de la ventana mantenga el tema oscuro del mockup.
"""

# Paleta de colores (basada en el mockup de la pantalla inicial).
COLORES = {
    "fondo_lateral": "#14342B",     # barra lateral: verde bosque oscuro
    "fondo_lateral_hover": "#1E4A3A",
    "boton_lateral": "#1E4A3A",      # botones de navegación en píldora
    "fondo_contenido": "#1F5B45",    # área principal: verde esmeralda
    "fondo_tarjeta": "#0F291F",     # formularios y tablas: verde muy oscuro
    "borde_tarjeta": "#2E6B54",
    "acento": "#E9C46A",            # dorado: botones principales y encabezados
    "texto": "#FFFFFF",
    "texto_secundario": "#BFD8CC",
    "exito": "#7DC98F",
    "error": "#F28C8C",
    "campo_fondo": "#F4F7F5",       # entradas de texto: fondo claro (legibilidad)
    "campo_texto": "#10241C",
}


def configurar_estilos(raiz):
    """Configura los estilos ttk sobre la ventana principal dada."""
    import tkinter as tk
    from tkinter import ttk

    estilo = ttk.Style(raiz)
    estilo.theme_use("clam")

    colores = COLORES

    estilo.configure("TFrame", background=colores["fondo_contenido"])
    estilo.configure("Tarjeta.TFrame", background=colores["fondo_tarjeta"])
    estilo.configure("TLabel", background=colores["fondo_contenido"],
                     foreground=colores["texto"], font=("Segoe UI", 10))
    estilo.configure("EtiquetaFormulario.TLabel",
                     background=colores["fondo_tarjeta"],
                     foreground=colores["texto_secundario"], font=("Segoe UI", 10))
    estilo.configure("Titulo.TLabel", font=("Segoe UI", 18, "bold"),
                     foreground=colores["texto"])
    estilo.configure("Subtitulo.TLabel", foreground=colores["texto_secundario"])

    # Botón principal: dorado con texto oscuro (contraste alto).
    estilo.configure("Primario.TButton", background=colores["acento"],
                     foreground="#10241C", font=("Segoe UI", 10, "bold"),
                     padding=(12, 6))
    estilo.map("Primario.TButton",
               background=[("active", "#F5D98D"), ("disabled", "#8A7A55")],
               foreground=[("disabled", "#4A4436")])

    # Botón secundario: píldora verde dentro de las tarjetas.
    estilo.configure("Secundario.TButton", background=colores["boton_lateral"],
                     foreground=colores["texto"], padding=(10, 4))
    estilo.map("Secundario.TButton",
               background=[("active", colores["fondo_lateral_hover"])])

    # Campos de entrada: fondo claro para legibilidad del texto digitado.
    estilo.configure("TEntry", fieldbackground=colores["campo_fondo"],
                     foreground=colores["campo_texto"], padding=4)
    estilo.configure("TCombobox", fieldbackground=colores["campo_fondo"],
                     foreground=colores["campo_texto"], padding=4)
    raiz.option_add("*TCombobox*Listbox*Background", colores["campo_fondo"])
    raiz.option_add("*TCombobox*Listbox*Foreground", colores["campo_texto"])

    # Tabla de movimientos.
    estilo.configure("Treeview", background=colores["fondo_tarjeta"],
                     foreground=colores["texto"], fieldbackground=colores["fondo_tarjeta"],
                     rowheight=26, font=("Segoe UI", 10))
    estilo.configure("Treeview.Heading", background=colores["boton_lateral"],
                     foreground=colores["acento"], font=("Segoe UI", 10, "bold"))
    estilo.map("Treeview", background=[("selected", colores["acento"])],
              foreground=[("selected", "#10241C")])
    estilo.map("Treeview.Heading", background=[("active", colores["fondo_lateral_hover"])])
