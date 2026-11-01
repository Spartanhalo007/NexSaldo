"""Ventana principal de NexSaldo.

Reproduce la estructura del mockup: barra lateral izquierda con la
navegación (Resumen, Cuentas, Gastos, Ingresos, Inversiones, Reportes,
Categorías, Configuración y Modo Oscuro) y un área de contenido a la
derecha. En este incremento solo los módulos de Gastos e Ingresos
(movimientos) están implementados; el resto muestra un aviso claro de
que están pendientes, sin presentarlos como disponibles.
"""

import tkinter as tk
from tkinter import ttk

from app.gui.estilos import COLORES, configurar_estilos
from app.gui.vista_movimientos import VistaMovimientos

# Botones de la barra lateral, en el orden del mockup.
# (texto visible, módulo asociado)
NAVEGACION = [
    ("Resumen", "pendiente"),
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
    "Resumen": "El resumen financiero consolidado se implementará cuando existan las funciones de consulta conjunta (RF-05).",
    "Cuentas": "El módulo de cuentas está pendiente de definición (saldos iniciales, tratamiento de monedas).",
    "Inversiones": "El registro de inversiones bursátiles se implementará en una etapa posterior (CU-03, CU-04).",
    "Reportes": "Los reportes y gráficos se definirán a partir de los requerimientos (RF-06).",
    "Categorías": "La edición de categorías desde la aplicación está pendiente para un incremento posterior.",
    "Configuración": "La pantalla de configuración está pendiente de definición.",
}

ANCHO_BARRA = 190


class VentanaPrincipal(tk.Tk):
    """Ventana raíz: barra lateral de navegación + área de contenido."""

    def __init__(self, gestor):
        super().__init__()
        self.title("NexSaldo - Finanzas personales e inversiones")
        self.geometry("1100x650")
        self.minsize(900, 560)
        self.configure(bg=COLORES["fondo_contenido"])

        configurar_estilos(self)

        self._gestor = gestor
        self._botones = {}
        self._vista_actual = None

        self._construir_barra_lateral()
        self._construir_area_contenido()

        # Vista inicial: gestión de movimientos (único módulo implementado).
        self._mostrar_movimientos(filtro_tipo=None, titulo="Movimientos")

    # ------------------------------------------------------------------
    # Barra lateral
    # ------------------------------------------------------------------

    def _construir_barra_lateral(self):
        barra = tk.Frame(self, bg=COLORES["fondo_lateral"], width=ANCHO_BARRA)
        barra.pack(side="left", fill="y")
        barra.pack_propagate(False)

        # Marca del mockup: barra de barras doradas + nombre.
        logo = tk.Frame(barra, bg=COLORES["fondo_lateral"])
        logo.pack(pady=(18, 4))
        tk.Frame(logo, bg=COLORES["acento"], width=10, height=26).pack(side="left", padx=2)
        tk.Frame(logo, bg=COLORES["texto_secundario"], width=10, height=18).pack(side="left", padx=2)
        tk.Frame(logo, bg=COLORES["exito"], width=10, height=12).pack(side="left", padx=2)
        tk.Label(barra, text="NexSaldo", font=("Segoe UI", 16, "bold"),
                 bg=COLORES["fondo_lateral"], fg=COLORES["texto"]).pack(pady=(0, 18))

        for texto, modulo in NAVEGACION:
            boton = tk.Button(
                barra,
                text=texto,
                anchor="w",
                font=("Segoe UI", 10),
                bg=COLORES["boton_lateral"],
                fg=COLORES["texto"],
                activebackground=COLORES["fondo_lateral_hover"],
                activeforeground=COLORES["texto"],
                relief="flat",
                padx=14,
                pady=6,
                cursor="hand2",
                command=lambda m=modulo, t=texto: self._al_navegar(m, t),
            )
            boton.pack(fill="x", padx=10, pady=3)
            self._botones[texto] = boton

    def _resaltar_boton(self, texto_activo):
        """Marca el botón activo con el color dorado del mockup."""
        for texto, boton in self._botones.items():
            if texto == texto_activo:
                boton.configure(bg=COLORES["acento"], fg="#10241C")
            else:
                boton.configure(bg=COLORES["boton_lateral"], fg=COLORES["texto"])

    # ------------------------------------------------------------------
    # Área de contenido
    # ------------------------------------------------------------------

    def _construir_area_contenido(self):
        self._area = tk.Frame(self, bg=COLORES["fondo_contenido"])
        self._area.pack(side="left", fill="both", expand=True, padx=16, pady=14)

    def _limpiar_area(self):
        if self._vista_actual is not None:
            self._vista_actual.destroy()
            self._vista_actual = None

    def _al_navegar(self, modulo, texto):
        if modulo == "movimientos":
            filtro = "GASTO" if texto == "Gastos" else "INGRESO"
            self._mostrar_movimientos(filtro_tipo=filtro, titulo=texto)
            self._resaltar_boton(texto)
        elif modulo == "tema":
            self._mostrar_pendiente(
                "Modo Oscuro",
                "La interfaz ya usa el tema oscuro del mockup; el cambio entre "
                "temas está pendiente de implementación.",
            )
            self._resaltar_boton(texto)
        else:
            self._mostrar_pendiente(texto, MODULOS_PENDIENTES[texto])
            self._resaltar_boton(texto)

    def _mostrar_movimientos(self, filtro_tipo, titulo):
        self._limpiar_area()
        self._vista_actual = VistaMovimientos(
            self._area, self._gestor, filtro_tipo=filtro_tipo, titulo=titulo
        )
        self._vista_actual.pack(fill="both", expand=True)

    def _mostrar_pendiente(self, titulo, mensaje):
        self._limpiar_area()
        panel = tk.Frame(self._area, bg=COLORES["fondo_contenido"])
        panel.pack(fill="both", expand=True)
        tk.Label(panel, text=titulo, font=("Segoe UI", 18, "bold"),
                 bg=COLORES["fondo_contenido"], fg=COLORES["texto"]).pack(pady=(10, 6))
        tk.Label(panel, text="Módulo pendiente de implementación",
                 font=("Segoe UI", 11, "italic"),
                 bg=COLORES["fondo_contenido"], fg=COLORES["acento"]).pack()
        tk.Label(panel, text=mensaje, wraplength=420, justify="center",
                 font=("Segoe UI", 10),
                 bg=COLORES["fondo_contenido"], fg=COLORES["texto_secundario"]).pack(pady=12)
