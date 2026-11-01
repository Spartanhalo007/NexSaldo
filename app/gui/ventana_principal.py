"""Ventana principal de NexSaldo (customtkinter).

Reproduce la estructura del mockup: barra lateral izquierda con la
navegación (Resumen, Cuentas, Gastos, Ingresos, Inversiones, Reportes,
Categorías, Configuración y Modo Oscuro), logo de la aplicación y un área
de contenido a la derecha. Están implementados Resumen (vista de gastos
por categoría del mes) y Gastos/Ingresos (movimientos); el resto muestra
un aviso claro de que están pendientes, sin presentarlos como disponibles.
"""

import tkinter as tk
from pathlib import Path

import customtkinter as ctk

from app.gui.estilos import COLORES, FUENTE, configurar_tabla, configurar_tema
from app.gui.vista_movimientos import VistaMovimientos
from app.gui.vista_resumen import VistaResumen

# Logo de la aplicación (versión sin fondo, 64x64).
RUTA_LOGO = Path(__file__).resolve().parent / "recursos" / "logo_64.png"

# Botones de la barra lateral, en el orden del mockup.
# (texto visible, módulo asociado)
NAVEGACION = [
    ("Resumen", "resumen"),
    ("Cuentas", "pendiente"),
    ("Gastos", "movimientos"),
    ("Ingresos", "movimientos"),
    ("Inversiones", "pendiente"),
    ("Reportes", "pendiente"),
    ("Categorías", "pendiente"),
    ("Configuración", "pendiente"),
    ("Modo Oscuro", "tema"),
]

MODULOS_PENDIENTES = {
    "Cuentas": "El módulo de cuentas está pendiente de definición (saldos iniciales, tratamiento de monedas).",
    "Inversiones": "El registro de inversiones bursátiles se implementará en una etapa posterior (CU-03, CU-04).",
    "Reportes": "Los reportes y gráficos se definirán a partir de los requerimientos (RF-06).",
    "Categorías": "La edición de categorías desde la aplicación está pendiente para un incremento posterior.",
    "Configuración": "La pantalla de configuración está pendiente de definición.",
}

ANCHO_BARRA = 200


class VentanaPrincipal(ctk.CTk):
    """Ventana raíz: barra lateral de navegación + área de contenido."""

    def __init__(self, gestor):
        super().__init__()
        configurar_tema()
        configurar_tabla(self)
        self.title("NexSaldo - Finanzas personales e inversiones")
        self.geometry("1150x660")
        self.minsize(960, 580)
        self.configure(fg_color=COLORES["fondo_contenido"])

        self._gestor = gestor
        self._botones = {}
        self._vista_actual = None

        self._construir_barra_lateral()
        self._construir_area_contenido()

        # Vista inicial: resumen financiero del mes.
        self._mostrar_resumen()
        self._resaltar_boton("Resumen")

    # ------------------------------------------------------------------
    # Barra lateral
    # ------------------------------------------------------------------

    def _construir_barra_lateral(self):
        barra = ctk.CTkFrame(self, fg_color=COLORES["fondo_lateral"],
                             corner_radius=0, width=ANCHO_BARRA)
        barra.pack(side="left", fill="y")
        barra.pack_propagate(False)

        # Logo de la aplicación + nombre.
        logo = tk.Frame(barra, bg=COLORES["fondo_lateral"], height=64)
        logo.pack(pady=(22, 2))
        # La imagen debe existir durante toda la vida de la ventana.
        self._imagen_logo = tk.PhotoImage(file=str(RUTA_LOGO))
        tk.Label(logo, image=self._imagen_logo, bg=COLORES["fondo_lateral"],
                 highlightthickness=0).pack()
        ctk.CTkLabel(barra, text="NexSaldo", font=(FUENTE, 18, "bold"),
                     text_color=COLORES["texto"]).pack(pady=(2, 20))

        for texto, modulo in NAVEGACION:
            boton = ctk.CTkButton(
                barra,
                text=texto,
                anchor="w",
                height=38,
                corner_radius=19,           # píldora como en el mockup
                font=(FUENTE, 12),
                fg_color="transparent",
                hover_color=COLORES["hover_lateral"],
                command=lambda m=modulo, t=texto: self._al_navegar(m, t),
            )
            boton.pack(fill="x", padx=12, pady=3)
            self._botones[texto] = boton

    def _resaltar_boton(self, texto_activo):
        """Marca el botón activo con el color dorado del mockup."""
        for texto, boton in self._botones.items():
            if texto == texto_activo:
                boton.configure(fg_color=COLORES["acento"],
                                text_color="#10241C")
            else:
                boton.configure(fg_color="transparent",
                                text_color=COLORES["texto"])

    # ------------------------------------------------------------------
    # Área de contenido
    # ------------------------------------------------------------------

    def _construir_area_contenido(self):
        self._area = ctk.CTkFrame(self, fg_color="transparent")
        self._area.pack(side="left", fill="both", expand=True,
                        padx=18, pady=16)

    def _limpiar_area(self):
        if self._vista_actual is not None:
            self._vista_actual.destroy()
            self._vista_actual = None

    def _al_navegar(self, modulo, texto):
        if modulo == "resumen":
            self._mostrar_resumen()
        elif modulo == "movimientos":
            filtro = "GASTO" if texto == "Gastos" else "INGRESO"
            self._mostrar_movimientos(filtro_tipo=filtro, titulo=texto)
        elif modulo == "tema":
            self._mostrar_pendiente(
                "Modo Oscuro",
                "La interfaz ya usa el tema oscuro del mockup; el cambio entre "
                "temas está pendiente de implementación.",
            )
        else:
            self._mostrar_pendiente(texto, MODULOS_PENDIENTES[texto])
        self._resaltar_boton(texto)

    def _mostrar_resumen(self):
        self._limpiar_area()
        self._vista_actual = VistaResumen(self._area, self._gestor)
        self._vista_actual.pack(fill="both", expand=True)

    def _mostrar_movimientos(self, filtro_tipo, titulo):
        self._limpiar_area()
        self._vista_actual = VistaMovimientos(
            self._area, self._gestor, filtro_tipo=filtro_tipo, titulo=titulo
        )
        self._vista_actual.pack(fill="both", expand=True)

    def _mostrar_pendiente(self, titulo, mensaje):
        self._limpiar_area()
        panel = ctk.CTkFrame(self._area, fg_color="transparent")
        panel.pack(fill="both", expand=True)
        ctk.CTkLabel(panel, text=titulo, font=(FUENTE, 22, "bold"),
                     text_color=COLORES["texto"]).pack(pady=(8, 6))
        ctk.CTkLabel(panel, text="Módulo pendiente de implementación",
                     font=(FUENTE, 13, "italic"),
                     text_color=COLORES["acento"]).pack()
        ctk.CTkLabel(panel, text=mensaje, wraplength=430, justify="center",
                     font=(FUENTE, 12),
                     text_color=COLORES["texto_secundario"]).pack(pady=14)
