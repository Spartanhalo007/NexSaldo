"""Diálogo para crear una nueva cuenta (módulo Cuentas).

Campos acordados: nombre (obligatorio), saldo inicial (puede ser 0),
divisa (COP preseleccionada), símbolo del catálogo (obligatorio), color
(obligatorio, con recientes y selector propio), opción de no incluir
en el balance total y nota opcional. El botón de añadir es amarillo.

El contenido tiene scroll: en pantallas pequeñas todos los campos
siguen siendo alcanzables.
"""

import customtkinter as ctk

from app.gestor.gestor_financiero import (
    ErrorValidacion,
    SIMBOLOS_VALIDOS,
)
from app.gui.campo_moneda import CampoMoneda
from app.gui.dialogo_color import DialogoColor
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

# Verde de selección del símbolo (el botón se vuelve verde y el ícono
# se muestra en blanco o en el color elegido).
VERDE_SELECCION = COLORES["fondo_contenido"]


class DialogoCuenta(ctk.CTkToplevel):
    """Ventana para diligenciar y guardar una cuenta nueva."""

    def __init__(self, master, gestor, al_crear, **kwargs):
        super().__init__(master, **kwargs)
        self._gestor = gestor
        self._al_crear = al_crear

        self.title("Crear nueva cuenta")
        self.geometry("660x640")
        self.minsize(560, 500)
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
        # El cuerpo es desplazable: todos los campos quedan alcanzables
        # incluso en pantallas pequeñas.
        cuerpo = ctk.CTkScrollableFrame(self, fg_color="transparent")
        cuerpo.pack(fill="both", expand=True, padx=14, pady=(8, 0))

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
        ctk.CTkLabel(columna_saldo,
                     text="Plata que tiene la cuenta (ej.: 1'000.000)",
                     font=(FUENTE, 11),
                     text_color=COLORES["texto_secundario"]).pack(
            anchor="w", pady=(0, 2))
        # Los miles se separan solos mientras se escribe (estilo colombiano).
        self._campo_saldo = CampoMoneda(columna_saldo, width=170,
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
        # queda con botón verde e ícono blanco (o del color elegido).
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
            self._botones_simbolo[clave] = boton

        # Leyenda de nombres de símbolos (dos filas).
        leyenda = ctk.CTkFrame(cuerpo, fg_color="transparent")
        leyenda.pack(fill="x")
        for indice, clave in enumerate(SIMBOLOS_VALIDOS):
            fila_leyenda, columna_leyenda = divmod(indice, 6)
            ctk.CTkLabel(leyenda, text=NOMBRES_SIMBOLOS.get(clave, clave),
                         font=(FUENTE, 9),
                         text_color=COLORES["texto_secundario"]).grid(
                row=fila_leyenda, column=columna_leyenda, padx=3)

        # Color (obligatorio): predeterminados + recientes + selector propio.
        ctk.CTkLabel(cuerpo, text="Color *",
                     font=(FUENTE, 11),
                     text_color=COLORES["texto_secundario"]).pack(
            anchor="w", pady=(12, 2))
        self._marco_colores = ctk.CTkFrame(cuerpo, fg_color="transparent")
        self._marco_colores.pack(fill="x")

        # Selector propio de color (cuadro + barra de tono).
        ctk.CTkButton(
            self._marco_colores, text="Más colores…", width=110, height=30,
            corner_radius=15, fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"], font=(FUENTE, 11),
            command=self._abrir_selector_color,
        ).grid(row=0, column=0, padx=3)

        for indice, color in enumerate(COLORES_PREDETERMINADOS, start=1):
            ctk.CTkButton(
                self._marco_colores, width=34, height=30, corner_radius=6,
                fg_color=color, hover_color=color, text="",
                command=lambda c=color: self._elegir_color(c),
            ).grid(row=0, column=indice, padx=3)

        # Espacio para los colores recientes (se llenan al abrir).
        self._marco_recientes = ctk.CTkFrame(cuerpo, fg_color="transparent")
        self._marco_recientes.pack(fill="x")
        ctk.CTkLabel(self._marco_recientes, text="Últimos usados:",
                     font=(FUENTE, 10),
                     text_color=COLORES["texto_secundario"]).pack(anchor="w")

        # Opción de no incluir en el balance total.
        self._variable_total = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            cuerpo, text="Incluir en el balance total",
            variable=self._variable_total, corner_radius=6,
            fg_color=COLORES["acento"], hover_color=COLORES["acento_hover"],
            text_color=COLORES["texto"], font=(FUENTE, 11)).pack(
            anchor="w", pady=(10, 0))

        # Nota opcional.
        ctk.CTkLabel(cuerpo, text="Nota (descripción de la cuenta, opcional)",
                     font=(FUENTE, 11),
                     text_color=COLORES["texto_secundario"]).pack(
            anchor="w", pady=(8, 2))
        self._campo_nota = ctk.CTkEntry(cuerpo, width=380, corner_radius=8)
        self._campo_nota.pack(anchor="w")

        # Mensaje de estado (éxito o error), siempre visible.
        self._etiqueta_estado = ctk.CTkLabel(self, text="",
                                             font=(FUENTE, 11),
                                             text_color=COLORES["error"])
        self._etiqueta_estado.pack(anchor="w", padx=16, pady=(6, 0))

        # Botón de añadir: amarillo (acento), como se acordó.
        ctk.CTkButton(self, text="Añadir", width=160, height=38,
                      corner_radius=18, font=(FUENTE, 13, "bold"),
                      fg_color=COLORES["acento"],
                      hover_color=COLORES["acento_hover"],
                      text_color="#10241C",
                      command=self._al_aniadir).pack(pady=(8, 12))

    def _cargar_colores_recientes(self):
        """Muestra los últimos colores usados (guardados en la base)."""
        try:
            recientes = self._gestor.obtener_colores_recientes()
        except Exception:
            recientes = []
        for hijo in self._marco_recientes.winfo_children()[1:]:
            hijo.destroy()
        for color in recientes:
            ctk.CTkButton(
                self._marco_recientes, width=34, height=30, corner_radius=6,
                fg_color=color, hover_color=color, text="",
                command=lambda c=color: self._elegir_color(c)).pack(
                side="left", padx=3)

    def _abrir_selector_color(self):
        """Abre el selector de color propio (cuadro + barra de tono)."""
        inicial = self._color_elegido or "#FBB718"
        DialogoColor(self, self._elegir_color, color_inicial=inicial)

    # ------------------------------------------------------------------
    # Selección de símbolo y color
    # ------------------------------------------------------------------

    def _elegir_simbolo(self, clave):
        """Selecciona un símbolo: botón verde, ícono blanco o del color."""
        self._simbolo_elegido = clave
        for otra_clave, boton in self._botones_simbolo.items():
            if otra_clave == clave:
                color_icono = self._color_elegido or "#FFFFFF"
                boton.configure(fg_color=VERDE_SELECCION,
                                image=icono_tk(clave, color_icono, 26))
            else:
                boton.configure(fg_color=COLORES["boton_lateral"],
                                image=icono_tk(otra_clave, GRIS, 26))

    def _elegir_color(self, color):
        """Aplica el color elegido al símbolo seleccionado (botón verde)."""
        self._color_elegido = str(color).upper()
        if self._simbolo_elegido:
            self._botones_simbolo[self._simbolo_elegido].configure(
                fg_color=VERDE_SELECCION,
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
                # El campo envía el valor sin separadores de miles.
                saldo_inicial_texto=self._campo_saldo.obtener_valor(),
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
