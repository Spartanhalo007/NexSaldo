"""Temas visuales de NexSaldo, tipografía y estilos de tablas."""

import sys
from pathlib import Path

from platformdirs import user_config_path

# Paleta de colores (muestreada del mockup de la pantalla inicial).
_CLASICO = {
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

# Las superficies neutras dominan; el acento queda reservado para acciones y datos clave.
# Los estados financieros conservan sus significados y las entradas siguen siendo claras.
def _paleta(lateral, fondo, tarjeta, control, hover, acento, acento_hover,
            texto, secundario, campo, borde, acento_intenso, intenso_hover):
    return dict(
        fondo_lateral=lateral, fondo_contenido=fondo, fondo_tarjeta=tarjeta,
        boton_lateral=control, hover_lateral=hover, acento=acento,
        acento_hover=acento_hover, texto=texto, texto_secundario=secundario,
        exito="#91D6A2", error="#FFA6A6", campo_fondo=campo,
        campo_texto=_CLASICO["campo_texto"], borde_tabla=borde,
        acento_intenso=acento_intenso, intenso_hover=intenso_hover,
    )


TEMA_PREDETERMINADO = "carbon"
TEMAS = {
    "carbon": ("Carbón", "Negro, grafito y amarillo", _paleta(
        "#0D0D0E", "#161617", "#222224", "#2C2C2F", "#38383C",
        "#FFDA48", "#E8C437", "#F8F8F9", "#C1C1C7", "#F5F5F3", "#45454B",
        "#6B5300", "#785E00",
    )),
    "clasico": ("Clásico", "Verde esmeralda y dorado", _CLASICO),
    "fiordo": ("Fiordo", "Azul profundo y turquesa", _paleta(
        "#0A1924", "#102633", "#173443", "#1E4051", "#285064",
        "#75E4E0", "#58CCC9", "#F0FAFC", "#B8D5DC", "#EFF8FA", "#396478",
        "#225861", "#2C616B",
    )),
    "mora": ("Mora", "Ciruela y lavanda", _paleta(
        "#190F24", "#241832", "#302143", "#3E2D52", "#4C3864",
        "#D9B5FF", "#C9A0F2", "#FAF4FF", "#D5C5E3", "#F8F2FC", "#5F4978",
        "#583B77", "#634586",
    )),
    "duna": ("Duna", "Arcilla oscura y cobre", _paleta(
        "#211712", "#2B1F19", "#392921", "#48352A", "#594233",
        "#FFB487", "#F2A374", "#FFF5EE", "#E1C7B7", "#FFF4EB", "#705340",
        "#744229", "#834B2D",
    )),
}

# Los consumidores importan estas referencias: se actualizan sin reasignarlas.
COLORES = TEMAS[TEMA_PREDETERMINADO][2].copy()
_GRAFICA_CLASICA = [
    "#FBB718", "#408FD1", "#89BF50",
    "#F28C8C", "#BFD8CC", "#7DC98F",
]
COLORES_GRAFICA = [COLORES["acento"], *_GRAFICA_CLASICA[1:]]

# Colores predeterminados ofrecidos al crear una cuenta (del mockup:
# dorado, azul, verde; el resto del propio tema).
COLORES_PREDETERMINADOS = [
    "#FBB718", "#408FD1", "#89BF50",
    "#F28C8C", "#BFD8CC", "#7DC98F",
    "#FFFFFF", "#8A8F98",
]


def _ruta_tema():
    return user_config_path("NexSaldo", appauthor=False) / "tema.txt"


def cargar_tema():
    """Usa Carbón si no hay preferencia válida en el perfil del usuario."""
    try:
        tema = _ruta_tema().read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return TEMA_PREDETERMINADO
    return tema if tema in TEMAS else TEMA_PREDETERMINADO


def guardar_tema(tema):
    if tema not in TEMAS:
        return False
    try:
        ruta = _ruta_tema()
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(f"{tema}\n", encoding="utf-8")
    except OSError:
        return False
    return True


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


def configurar_tema(tema):
    """Actualiza los tokens que usan CustomTkinter, ttk y las gráficas."""
    import customtkinter as ctk

    ctk.set_appearance_mode("dark")
    COLORES.clear()
    COLORES.update(TEMAS[tema][2])
    COLORES_GRAFICA[:] = [COLORES["acento"], *_GRAFICA_CLASICA[1:]]


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
