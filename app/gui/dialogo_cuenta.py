"""Diálogo para crear una nueva cuenta (módulo Cuentas).

Campos acordados: nombre (obligatorio), saldo inicial (puede ser 0),
divisa (COP preseleccionada), símbolo del catálogo (obligatorio), color
(obligatorio, con recientes y rueda de selección), opción de no incluir
en el balance total y nota opcional. El botón de añadir es amarillo.
"""

import customtkinter as ctk
from tkinter import colorchooser

from app.gestor.gestor_financiero import (
    ErrorValidacion,
    SIMBOLOS_VALIDOS,
)
from app.gui.estilos import COLORES, COLORES_PREDETERMINADOS, FUENTE
from app.gui.iconos import GRIS, icono_tk

NOMBRES_SIMBOLOS = {
    "cash": "Efectivo",
    "banco": "Banco",
    "criptomonedas": "Criptomonedas",
    "tarjeta_credito": "Tarjeta de crédito",
    "tarjeta_debito": "Tarjeta de débito",
    "bolsa": "Bolsa (%)",
    "moneda": "Moneda",
    "euro": "Euro",
    "tap_and_pay": "Tap and pay",
    "paypal": "PayPal",
    "boveda": "Bóveda",
    "puerquito": "Puerquito",
}


class DialogoCuenta(ctk.CTkToplevel):
    """Ventana para diligenciar y guardar una cuenta nueva."""

    def __init__(self, master, gestor, al_crear, **kwargs):
        super().__init__(master, **kwargs)
        self._gestor = gestor
        self._al_crear = al_crear

        self.title("Crear nueva cuenta")
        self.geometry("640x560")
        self.resizable(False, False)
        self.configure(fg_color=COLORES["fondo_tarjeta"])
        self.transient(master)
        self.grab_set()

        # Estado del formulario.
        self._simbolo_elegido = None
        self._color_elegido = None

        self._construir_formulario()
        self._cargar_colores_recientes()

        self.protocol("WM_DELETE_WINDOW", self.destroy)

    # ------------------------------------------------------------------
    # Formulario
    # ------------------------------------------------------------------

    def _construir_formulario(self):
        cuerpo = ctk.CTkFrame(self, fg_color="transparent")
        cuerpo.pack(fill="both", expand=True, padx=18, pady=12)

        ctk.CTkLabel(cuerpo, text="Crear nueva cuenta",
                     font=(FUENTE, 18, "bold"),
                     text_color=COLORES["texto"]).pack(anchor="w")

        # Nombre (obligatorio).
        ctk.CTkLabel(cuerpo, text="Nombre de la cuenta *",
                     font=(FUENTE, 11),
                     text_color=COLORES["texto_secundario"]).pack(
            anchor="w", pady=(10, 2))
        self._campo_nombre = ctk.CTkEntry(cuerpo, width=380, corner_radius=8)
        self._campo_nombre.pack(anchor="w")

        # Saldo inicial y divisa en la misma fila.
        fila = ctk.CTkFrame(cuerpo, fg_color="transparent")
        fila.pack(fill="x", pady=(10, 0))
        columna_saldo = ctk.CTkFrame(fila, fg_color="transparent")
        columna_saldo.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(columna_saldo, text="Plata que tiene la cuenta",
                     font=(FUENTE, 11),
                     text_color=COLORES["texto_secundario"]).pack(
            anchor="w", pady=(0, 2))
        self._campo_saldo = ctk.CTkEntry(columna_saldo, width=170,
                                         corner_radius=8)
        self._campo_saldo.insert(0, "0")
        self._campo_saldo.pack(anchor="w")

        columna_moneda = ctk.CTkFrame(fila, fg_color="transparent")
        columna_moneda.pack(side="left", padx=(18, 0))
        ctk.CTkLabel(columna_moneda, text="Divisa",
                     font=(FUENTE, 11),
                     text_color=COLORES["texto_secundario"]).pack(
            anchor="w", pady=(0, 2))
        self._campo_moneda = ctk.CTkComboBox(
            columna_moneda, values=["COP", "USD"], width=90,
            state="readonly", corner_radius=8)
        self._campo_moneda.set("COP")   # COP preseleccionado (acordado).
        self._campo_moneda.pack(anchor="w")

        # Símbolo (obligatorio): cuadrícula de íconos en gris; el elegido
        # se muestra con el color seleccionado.
        ctk.CTkLabel(cuerpo, text="Símbolo *",
                     font=(FUENTE, 11),
                     text_color=COLORES["texto_secundario"]).pack(
            anchor="w", pady=(12, 2))
        self._marco_simbolos = ctk.CTkFrame(cuerpo, fg_color="transparent")
        self._marco_simbolos.pack(fill="x")
        self._botones_simbolo = {}
        for indice, clave in enumerate(SIMBOLOS_VALIDOS):
            fila_simbolo, columna_simbolo = divmod(indice, 6)
            boton = ctk.CTkButton(
                self._marco_simbolos, width=52, height=44, corner_radius=10,
                fg_color=COLORES["boton_lateral"],
                hover_color=COLORES["hover_lateral"],
                text="",
                image=icono_tk(clave, GRIS, 26),
                command=lambda c=clave: self._elegir_simbolo(c),
            )
            boton.grid(row=fila_simbolo, column=columna_simbolo,
                       padx=3, pady=3)
            boton_tooltip = NOMBRES_SIMBOLOS.get(clave, clave)
            # El nombre del símbolo se muestra debajo del ícono.
            self._botones_simbolo[clave] = (boton, boton_tooltip)

        # Leyenda de nombres de símbolos (dos filas).
        leyenda = ctk.CTkFrame(cuerpo, fg_color="transparent")
        leyenda.pack(fill="x")
        for indice, clave in enumerate(SIMBOLOS_VALIDOS):
            fila_leyenda, columna_leyenda = divmod(indice, 6)
            ctk.CTkLabel(leyenda, text=NOMBRES_SIMBOLOS.get(clave, clave),
                         font=(FUENTE, 9),
                         text_color=COLORES["texto_secundario"]).grid(
                row=fila_leyenda, column=columna_leyenda, padx=3)

        # Color (obligatorio): recientes + predeterminados + rueda.
        ctk.CTkLabel(cuerpo, text="Color *",
                     font=(FUENTE, 11),
                     text_color=COLORES["texto_secundario"]).pack(
            anchor="w", pady=(10, 2))
        self._marco_colores = ctk.CTkFrame(cuerpo, fg_color="transparent")
        self._marco_colores.pack(fill="x")
        self._botones_color = {}

        # Rueda de selección de color (selector del sistema).
        ctk.CTkButton(
            self._marco_colores, text="Más colores…", width=110, height=30,
            corner_radius=15, fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"], font=(FUENTE, 11),
            command=self._abrir_rueda_de_color,
        ).grid(row=0, column=0, padx=3)

        for indice, color in enumerate(COLORES_PREDETERMINADOS, start=1):
            self._agregar_boton_color(color, 0, indice)

        # Espacio para los colores recientes (se llenan al abrir).
        self._marco_recientes = ctk.CTkFrame(cuerpo, fg_color="transparent")
        self._marco_recientes.pack(fill="x")
        self._etiqueta_recientes = ctk.CTkLabel(
            self._marco_recientes, text="Últimos usados:",
            font=(FUENTE, 10), text_color=COLORES["texto_secundario"])
        self._etiqueta_recientes.pack(anchor="w")

        # Opción de no incluir en el balance total.
        self._variable_total = ctk.BooleanVar(value=True)
        self._casilla_total = ctk.CTkCheckBox(
            cuerpo, text="Incluir en el balance total",
            variable=self._variable_total, corner_radius=6,
            fg_color=COLORES["acento"], hover_color=COLORES["acento_hover"],
            text_color=COLORES["texto"], font=(FUENTE, 11))
        self._casilla_total.pack(anchor="w", pady=(10, 0))

        # Nota opcional.
        ctk.CTkLabel(cuerpo, text="Nota (descripción de la cuenta, opcional)",
                     font=(FUENTE, 11),
                     text_color=COLORES["texto_secundario"]).pack(
            anchor="w", pady=(8, 2))
        self._campo_nota = ctk.CTkEntry(cuerpo, width=380, corner_radius=8)
        self._campo_nota.pack(anchor="w")

        # Mensaje de estado (éxito o error).
        self._etiqueta_estado = ctk.CTkLabel(cuerpo, text="",
                                             font=(FUENTE, 11),
                                             text_color=COLORES["error"])
        self._etiqueta_estado.pack(anchor="w", pady=(6, 0))

        # Botón de añadir: amarillo (acento), como se acordó.
        ctk.CTkButton(cuerpo, text="Añadir", width=160, height=38,
                      corner_radius=18, font=(FUENTE, 13, "bold"),
                      fg_color=COLORES["acento"],
                      hover_color=COLORES["acento_hover"],
                      text_color="#10241C",
                      command=self._al_aniadir).pack(pady=(10, 0))

    def _agregar_boton_color(self, color, fila, columna):
        """Crea el botón cuadradito de un color de la paleta."""
        boton = ctk.CTkButton(
            self._marco_colores, width=34, height=30, corner_radius=6,
            fg_color=color, hover_color=color,
            text="", command=lambda c=color: self._elegir_color(c))
        boton.grid(row=fila, column=columna, padx=3)
        self._botones_color[color.upper()] = boton

    def _cargar_colores_recientes(self):
        """Muestra los últimos colores usados (guardados en la base)."""
        try:
            recientes = self._gestor.obtener_colores_recientes()
        except Exception:
            recientes = []
        for hijo in self._marco_recientes.winfo_children()[1:]:
            hijo.destroy()
        for indice, color in enumerate(recientes):
            boton = ctk.CTkButton(
                self._marco_recientes, width=34, height=30, corner_radius=6,
                fg_color=color, hover_color=color, text="",
                command=lambda c=color: self._elegir_color(c))
            boton.pack(side="left", padx=3)

    def _abrir_rueda_de_color(self):
        """Abre el selector de color del sistema (rueda/paleta)."""
        resultado = colorchooser.askcolor(parent=self)
        if resultado and resultado[1]:
            self._elegir_color(resultado[1])

    # ------------------------------------------------------------------
    # Selección de símbolo y color
    # ------------------------------------------------------------------

    def _elegir_simbolo(self, clave):
        self._simbolo_elegido = clave
        color = self._color_elegido or GRIS
        for otra_clave, (boton, _) in self._botones_simbolo.items():
            if otra_clave == clave:
                boton.configure(fg_color=COLORES["acento"],
                                image=icono_tk(clave, "#10241C", 26))
            else:
                boton.configure(fg_color=COLORES["boton_lateral"],
                                image=icono_tk(otra_clave, GRIS, 26))

    def _elegir_color(self, color):
        self._color_elegido = color.upper()
        # El símbolo elegido se muestra con el color seleccionado.
        if self._simbolo_elegido:
            for otra_clave, (boton, _) in self._botones_simbolo.items():
                if otra_clave == self._simbolo_elegido:
                    boton.configure(
                        fg_color=COLORES["acento"],
                        image=icono_tk(self._simbolo_elegido,
                                       self._color_elegido, 26))

    # ------------------------------------------------------------------
    # Guardar
    # ------------------------------------------------------------------

    def _al_aniadir(self):
        """Valida y guarda la cuenta; conserva los datos si hay error."""
        try:
            cuenta = self._gestor.crear_cuenta(
                nombre=self._campo_nombre.get(),
                moneda=self._campo_moneda.get(),
                saldo_inicial_texto=self._campo_saldo.get(),
                simbolo=self._simbolo_elegido,
                color=self._color_elegido,
                incluye_en_total=self._variable_total.get(),
                nota=self._campo_nota.get(),
            )
        except ErrorValidacion as error:
            # Regla de la tesis: informar el error y conservar lo diligenciado.
            self._etiqueta_estado.configure(text=str(error),
                                           text_color=COLORES["error"])
            return
        except Exception as error:
            self._etiqueta_estado.configure(
                text=f"No se pudo guardar la cuenta: {error}",
                text_color=COLORES["error"])
            return

        self._al_crear(cuenta)
        self.destroy()
