"""Vista de resumen financiero del mes — preparación de RF-05.

Muestra, como en el mockup: una dona con los gastos por categoría del mes,
los totales del mes por moneda y el desglose por categoría. La columna de
inversiones del mockup se informa como pendiente (CU-03/CU-04), sin
presentar datos inexistentes.

Reglas de la tesis aplicadas aquí:
- No se suman importes de monedas distintas: la dona y los totales se
  muestran para la moneda seleccionada (COP o USD).
- No se calcula saldo ni patrimonio neto: esa fórmula está pendiente de
  aprobación.
- Un fallo de base de datos se informa sin presentar datos parciales.
"""

import tkinter as tk
from datetime import date
from decimal import Decimal
from tkinter import messagebox

import customtkinter as ctk

from app.gui.estilos import COLORES, COLORES_GRAFICA, FUENTE
from app.gui.formato import formatear_valor, nombre_mes

TAMANO_DONA = 220
GROSOR_DONA = 46


class VistaResumen(ctk.CTkFrame):
    """Panel de resumen del mes: dona de gastos, totales y desglose."""

    def __init__(self, master, gestor, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._gestor = gestor

        hoy = date.today()
        self._anno = hoy.year
        self._mes = hoy.month

        self._construir_encabezado()
        self._construir_columnas()

        self.refrescar()

    # ------------------------------------------------------------------
    # Encabezado y columnas
    # ------------------------------------------------------------------

    def _construir_encabezado(self):
        ctk.CTkLabel(self, text="Resumen Financiero",
                     font=(FUENTE, 24, "bold"),
                     text_color=COLORES["texto"]).pack()
        ctk.CTkLabel(self, text=nombre_mes(self._anno, self._mes).capitalize(),
                     font=(FUENTE, 13),
                     text_color=COLORES["texto_secundario"]).pack(pady=(0, 4))

        # Selector de moneda: los totales nunca mezclan monedas.
        fila_moneda = ctk.CTkFrame(self, fg_color="transparent")
        fila_moneda.pack(pady=(2, 6))
        ctk.CTkLabel(fila_moneda, text="Moneda:", font=(FUENTE, 12),
                     text_color=COLORES["texto_secundario"]).pack(
            side="left", padx=(0, 6))
        self._campo_moneda = ctk.CTkComboBox(
            fila_moneda, values=["COP", "USD"], width=80,
            corner_radius=8, command=lambda _valor: self.refrescar(),
        )
        self._campo_moneda.set("COP")
        self._campo_moneda.pack(side="left")

    def _construir_columnas(self):
        columnas = ctk.CTkFrame(self, fg_color="transparent")
        columnas.pack(fill="both", expand=True)
        columnas.columnconfigure(0, weight=1, uniform="resumen")
        columnas.columnconfigure(1, weight=1, uniform="resumen")
        columnas.rowconfigure(0, weight=1)

        self._construir_columna_gastos(columnas)
        self._construir_columna_inversiones(columnas)

    # ------------------------------------------------------------------
    # Columna izquierda: dona de gastos y desglose
    # ------------------------------------------------------------------

    def _construir_columna_gastos(self, columnas):
        panel = ctk.CTkFrame(columnas, fg_color="transparent")
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        ctk.CTkLabel(panel, text="Gastos por categoría este mes",
                     font=(FUENTE, 13, "bold"),
                     text_color=COLORES["texto"]).pack(anchor="w")

        # Dona dibujada sobre un Canvas (sin librerías externas).
        self._lienzo = tk.Canvas(panel, width=TAMANO_DONA, height=TAMANO_DONA,
                                 bg=COLORES["fondo_contenido"],
                                 highlightthickness=0)
        self._lienzo.pack(pady=12)

        self._etiqueta_total_gastos = ctk.CTkLabel(
            panel, text="Gastos del mes: —", font=(FUENTE, 14, "bold"),
            text_color=COLORES["texto"])
        self._etiqueta_total_gastos.pack(pady=(0, 4))

        # Tarjeta de desglose por categoría (como en el mockup).
        tarjeta = ctk.CTkFrame(panel, fg_color=COLORES["fondo_tarjeta"],
                               corner_radius=14)
        tarjeta.pack(fill="both", expand=True, pady=(6, 0))
        ctk.CTkLabel(tarjeta, text="Gastos por categoría · Este mes",
                     font=(FUENTE, 12, "bold"),
                     text_color=COLORES["texto"]).pack(anchor="w", padx=14,
                                                       pady=(10, 4))
        self._marco_desglose = ctk.CTkFrame(tarjeta, fg_color="transparent")
        self._marco_desglose.pack(fill="both", expand=True, padx=14,
                                  pady=(0, 10))

    # ------------------------------------------------------------------
    # Columna derecha: totales e inversiones
    # ------------------------------------------------------------------

    def _construir_columna_inversiones(self, columnas):
        panel = ctk.CTkFrame(columnas, fg_color="transparent")
        panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        # Totales del mes para la moneda seleccionada.
        tarjeta_totales = ctk.CTkFrame(panel, fg_color=COLORES["fondo_tarjeta"],
                                       corner_radius=14)
        tarjeta_totales.pack(fill="x")
        ctk.CTkLabel(tarjeta_totales, text="Totales del mes",
                     font=(FUENTE, 12, "bold"),
                     text_color=COLORES["texto"]).pack(anchor="w", padx=14,
                                                        pady=(10, 2))
        self._etiqueta_ingresos = ctk.CTkLabel(tarjeta_totales,
                                               text="Ingresos: —",
                                               font=(FUENTE, 13),
                                               text_color=COLORES["exito"])
        self._etiqueta_ingresos.pack(anchor="w", padx=14, pady=2)
        self._etiqueta_gastos = ctk.CTkLabel(tarjeta_totales,
                                             text="Gastos: —",
                                             font=(FUENTE, 13),
                                             text_color=COLORES["error"])
        self._etiqueta_gastos.pack(anchor="w", padx=14, pady=2)
        ctk.CTkLabel(tarjeta_totales,
                     text="Sin sumar monedas distintas ni calcular saldo.",
                     font=(FUENTE, 10, "italic"),
                     text_color=COLORES["texto_secundario"]).pack(
            anchor="w", padx=14, pady=(2, 10))

        # Columna de inversiones del mockup: módulo pendiente, sin datos
        # inventados.
        tarjeta = ctk.CTkFrame(panel, fg_color=COLORES["fondo_tarjeta"],
                               corner_radius=14)
        tarjeta.pack(fill="both", expand=True, pady=(12, 0))
        ctk.CTkLabel(tarjeta, text="Inversiones",
                     font=(FUENTE, 13, "bold"),
                     text_color=COLORES["texto"]).pack(anchor="w", padx=14,
                                                       pady=(12, 2))
        ctk.CTkLabel(tarjeta, text="Inversiones actuales: —",
                     font=(FUENTE, 14, "bold"),
                     text_color=COLORES["texto_secundario"]).pack(
            anchor="w", padx=14, pady=4)
        ctk.CTkLabel(
            tarjeta,
            text="El módulo de inversiones bursátiles (ETFs y acciones con "
                 "datos de cierre de Yahoo Finance) se implementará en una "
                 "etapa posterior (CU-03, CU-04).",
            wraplength=300, justify="left", font=(FUENTE, 11),
            text_color=COLORES["texto_secundario"],
        ).pack(anchor="w", padx=14, pady=(2, 12))

    # ------------------------------------------------------------------
    # Actualización de datos
    # ------------------------------------------------------------------

    def refrescar(self):
        """Consulta el resumen del mes y redibuja la dona y las tarjetas."""
        try:
            resumen = self._gestor.resumen_del_mes(self._anno, self._mes)
        except Exception as error:
            messagebox.showerror(
                "Error de base de datos",
                f"No se pudo consultar el resumen del mes: {error}",
            )
            return

        moneda = self._campo_moneda.get()
        datos = resumen.get(
            moneda,
            {"ingresos": Decimal("0"), "gastos": Decimal("0"),
             "gastos_por_categoria": {}},
        )
        self._dibujar_dona(datos["gastos_por_categoria"], moneda)
        self._actualizar_desglose(datos["gastos_por_categoria"],
                                 datos["gastos"], moneda)
        self._etiqueta_total_gastos.configure(
            text=f"Gastos del mes: {formatear_valor(datos['gastos'], moneda)}")
        self._etiqueta_ingresos.configure(
            text=f"Ingresos: {formatear_valor(datos['ingresos'], moneda)}")
        self._etiqueta_gastos.configure(
            text=f"Gastos: {formatear_valor(datos['gastos'], moneda)}")

    def _dibujar_dona(self, gastos_por_categoria, moneda):
        """Dibuja la dona de gastos por categoría sobre el Canvas."""
        self._lienzo.delete("all")
        centro = TAMANO_DONA / 2
        radio = centro - 4
        total = sum(gastos_por_categoria.values(), Decimal("0"))

        if total <= 0:
            # Sin datos: aro neutro y aviso en el centro.
            self._lienzo.create_oval(
                4, 4, TAMANO_DONA - 4, TAMANO_DONA - 4,
                outline=COLORES["fondo_tarjeta"], width=GROSOR_DONA)
            self._lienzo.create_text(
                centro, centro, text="Sin gastos\neste mes",
                fill=COLORES["texto_secundario"],
                font=(FUENTE, 11), justify="center")
            return

        # Cada categoría ocupa un aro proporcional a su valor.
        inicio = 90
        for indice, (categoria, valor) in enumerate(
                sorted(gastos_por_categoria.items(), key=lambda par: -par[1])):
            extension = float(valor / total) * 360.0
            color = COLORES_GRAFICA[indice % len(COLORES_GRAFICA)]
            self._lienzo.create_arc(
                4, 4, TAMANO_DONA - 4, TAMANO_DONA - 4,
                start=inicio, extent=extension, style="arc",
                outline=color, width=GROSOR_DONA)
            inicio -= extension

        # Hueco central con el total.
        self._lienzo.create_oval(
            centro - (radio - GROSOR_DONA / 2 - 2),
            centro - (radio - GROSOR_DONA / 2 - 2),
            centro + (radio - GROSOR_DONA / 2 - 2),
            centro + (radio - GROSOR_DONA / 2 - 2),
            fill=COLORES["fondo_contenido"], outline="")
        self._lienzo.create_text(
            centro, centro, text="Total\n" + formatear_valor(total, moneda),
            fill=COLORES["texto"], font=(FUENTE, 11, "bold"), justify="center")

    def _actualizar_desglose(self, gastos_por_categoria, total, moneda):
        """Llena la tarjeta de desglose: color, categoría, % y valor."""
        for hijo in self._marco_desglose.winfo_children():
            hijo.destroy()

        if total <= 0:
            ctk.CTkLabel(self._marco_desglose,
                         text="Aún no hay gastos registrados este mes.",
                         font=(FUENTE, 11),
                         text_color=COLORES["texto_secundario"]).pack(
                anchor="w", pady=6)
            return

        categorias = sorted(gastos_por_categoria.items(),
                            key=lambda par: -par[1])
        for indice, (categoria, valor) in enumerate(categorias):
            fila = ctk.CTkFrame(self._marco_desglose, fg_color="transparent")
            fila.pack(fill="x", pady=2)
            color = COLORES_GRAFICA[indice % len(COLORES_GRAFICA)]
            punto = tk.Canvas(fila, width=14, height=14,
                              bg=COLORES["fondo_tarjeta"],
                              highlightthickness=0)
            punto.create_oval(2, 2, 12, 12, fill=color, outline="")
            punto.pack(side="left", padx=(0, 8))
            porcentaje = int(round(float(valor / total) * 100))
            ctk.CTkLabel(fila, text=categoria, font=(FUENTE, 11),
                         text_color=COLORES["texto"]).pack(side="left")
            ctk.CTkLabel(fila, text=f"{porcentaje}%", font=(FUENTE, 11),
                         text_color=COLORES["texto_secundario"]).pack(
                side="left", padx=8)
            ctk.CTkLabel(
                fila, text=formatear_valor(valor, moneda), font=(FUENTE, 11),
                text_color=COLORES["texto"]).pack(side="right")

        # Fila de total (como en el mockup).
        fila_total = ctk.CTkFrame(self._marco_desglose, fg_color="transparent")
        fila_total.pack(fill="x", pady=(8, 0))
        ctk.CTkLabel(fila_total, text="Total", font=(FUENTE, 11, "bold"),
                     text_color=COLORES["texto"]).pack(side="left")
        ctk.CTkLabel(fila_total, text=formatear_valor(total, moneda),
                     font=(FUENTE, 11, "bold"),
                     text_color=COLORES["texto"]).pack(side="right")
