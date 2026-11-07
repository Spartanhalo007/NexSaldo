"""Diálogo modal para crear y seleccionar etiquetas 100% customizables en NexSaldo."""

from tkinter import messagebox
from typing import Callable, List, Sequence
import customtkinter as ctk

from app.gestor.gestor_financiero import ErrorValidacion, GestorFinanciero
from app.gui.dialogo_color import DialogoColor
from app.gui.estilos import COLORES, COLORES_PREDETERMINADOS, FUENTE


class DialogoEtiquetas(ctk.CTkToplevel):
    """Permite seleccionar etiquetas existentes o crear nuevas etiquetas 100% customizables."""

    def __init__(
        self,
        master,
        gestor: GestorFinanciero,
        etiquetas_seleccionadas: Sequence[str],
        al_confirmar: Callable[[List[str]], None],
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self._gestor = gestor
        self._seleccionadas = set(etiquetas_seleccionadas or [])
        self._al_confirmar = al_confirmar
        self._color_nueva = COLORES_PREDETERMINADOS[1]

        self.title("Gestionar y añadir etiquetas")
        self.geometry("460x500")
        self.resizable(False, False)
        self.configure(fg_color=COLORES["fondo_lateral"])
        self.transient(master)
        self.grab_set()

        self._construir_interfaz()

    def _construir_interfaz(self):
        cuerpo = ctk.CTkFrame(self, fg_color="transparent")
        cuerpo.pack(fill="both", expand=True, padx=20, pady=18)

        ctk.CTkLabel(
            cuerpo,
            text="Etiquetas personalizadas",
            font=(FUENTE, 18, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w")

        ctk.CTkLabel(
            cuerpo,
            text="Selecciona las etiquetas para este gasto o crea una nueva:",
            font=(FUENTE, 12),
            text_color=COLORES["texto_secundario"],
        ).pack(anchor="w", pady=(2, 12))

        # --- Sección para crear nueva etiqueta ---
        marco_crear = ctk.CTkFrame(
            cuerpo, fg_color=COLORES["fondo_tarjeta"], corner_radius=10
        )
        marco_crear.pack(fill="x", pady=(0, 14))

        ctk.CTkLabel(
            marco_crear,
            text="Crear nueva etiqueta",
            font=(FUENTE, 13, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w", padx=14, pady=(10, 6))

        fila_input = ctk.CTkFrame(marco_crear, fg_color="transparent")
        fila_input.pack(fill="x", padx=14, pady=(0, 12))

        self._campo_nombre = ctk.CTkEntry(
            fila_input,
            placeholder_text="Ej: Vacaciones playa, Urgente, Deducible...",
            fg_color=COLORES["campo_fondo"],
            text_color=COLORES["campo_texto"],
            font=(FUENTE, 13),
            width=230,
            corner_radius=8,
        )
        self._campo_nombre.pack(side="left", padx=(0, 8))

        self._boton_color = ctk.CTkButton(
            fila_input,
            text="",
            width=34,
            height=34,
            corner_radius=17,
            fg_color=self._color_nueva,
            hover_color=self._color_nueva,
            command=self._abrir_selector_color,
        )
        self._boton_color.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            fila_input,
            text="+ Crear",
            width=90,
            height=34,
            corner_radius=8,
            fg_color=COLORES["acento"],
            hover_color=COLORES["acento_hover"],
            text_color=COLORES["campo_texto"],
            font=(FUENTE, 13, "bold"),
            command=self._crear_etiqueta,
        ).pack(side="left")

        # --- Lista de etiquetas disponibles ---
        ctk.CTkLabel(
            cuerpo,
            text="Etiquetas disponibles",
            font=(FUENTE, 13, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w", pady=(0, 6))

        self._contenedor_lista = ctk.CTkScrollableFrame(
            cuerpo,
            fg_color=COLORES["fondo_tarjeta"],
            corner_radius=10,
            height=210,
        )
        self._contenedor_lista.pack(fill="both", expand=True, pady=(0, 14))

        self._refrescar_lista_etiquetas()

        # --- Botones inferiores ---
        fila_botones = ctk.CTkFrame(cuerpo, fg_color="transparent")
        fila_botones.pack(fill="x")

        ctk.CTkButton(
            fila_botones,
            text="Cancelar",
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 13),
            corner_radius=8,
            width=120,
            command=self.destroy,
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            fila_botones,
            text="Aplicar etiquetas",
            fg_color=COLORES["acento"],
            hover_color=COLORES["acento_hover"],
            text_color=COLORES["campo_texto"],
            font=(FUENTE, 13, "bold"),
            corner_radius=8,
            width=160,
            command=self._confirmar,
        ).pack(side="right")

    def _abrir_selector_color(self):
        DialogoColor(
            self,
            al_elegir=self._al_elegir_color,
            color_inicial=self._color_nueva,
        )

    def _al_elegir_color(self, nuevo_color: str):
        self._color_nueva = nuevo_color
        self._boton_color.configure(fg_color=nuevo_color, hover_color=nuevo_color)

    def _crear_etiqueta(self):
        nombre = self._campo_nombre.get().strip()
        try:
            etiqueta = self._gestor.crear_etiqueta(nombre, self._color_nueva)
        except ErrorValidacion as error:
            messagebox.showwarning("Etiqueta inválida", str(error), parent=self)
            return

        self._seleccionadas.add(etiqueta.nombre)
        self._campo_nombre.delete(0, "end")
        self._refrescar_lista_etiquetas()

    def _refrescar_lista_etiquetas(self):
        for hijo in self._contenedor_lista.winfo_children():
            hijo.destroy()

        etiquetas = self._gestor.obtener_etiquetas()
        if not etiquetas:
            ctk.CTkLabel(
                self._contenedor_lista,
                text="Aún no hay etiquetas creadas.\nEscribe un nombre arriba y presiona '+ Crear'.",
                font=(FUENTE, 12),
                text_color=COLORES["texto_secundario"],
                justify="center",
            ).pack(pady=35)
            return

        for et in etiquetas:
            activa = et.nombre in self._seleccionadas
            fila = ctk.CTkFrame(
                self._contenedor_lista,
                fg_color=COLORES["fondo_contenido"] if activa else COLORES["boton_lateral"],
                corner_radius=8,
            )
            fila.pack(fill="x", padx=6, pady=4)

            punto = ctk.CTkFrame(
                fila, width=14, height=14, corner_radius=7, fg_color=et.color
            )
            punto.pack(side="left", padx=(10, 8), pady=10)

            var_chk = ctk.BooleanVar(value=activa)
            chk = ctk.CTkCheckBox(
                fila,
                text=et.nombre,
                variable=var_chk,
                font=(FUENTE, 13, "bold" if activa else "normal"),
                text_color=COLORES["texto"],
                fg_color=COLORES["acento"],
                hover_color=COLORES["acento_hover"],
                checkmark_color=COLORES["campo_texto"],
                command=lambda n=et.nombre, v=var_chk: self._alternar_etiqueta(n, v.get()),
            )
            chk.pack(side="left", fill="x", expand=True, pady=6)

    def _alternar_etiqueta(self, nombre: str, estado: bool):
        if estado:
            self._seleccionadas.add(nombre)
        else:
            self._seleccionadas.discard(nombre)
        self._refrescar_lista_etiquetas()

    def _confirmar(self):
        self._al_confirmar(sorted(self._seleccionadas))
        self.destroy()
