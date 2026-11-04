"""Selector de fechas tipo calendario (ventana emergente).

Tkinter no trae un calendario; este es un calendario propio y mínimo:
navegación por mes/año y una cuadrícula de días. Al elegir un día llama
al callback con un datetime.date.
"""

import calendar
from datetime import date

import customtkinter as ctk

from app.gui.estilos import COLORES, FUENTE
from app.gui.formato import NOMBRES_MESES

DIAS_CABECERA = ("Lu", "Ma", "Mi", "Ju", "Vi", "Sa", "Do")


class SelectorCalendario(ctk.CTkToplevel):
    """Ventana pequeña con un mes navegable para escoger una fecha."""

    def __init__(self, master, al_elegir, fecha_inicial=None, **kwargs):
        super().__init__(master, **kwargs)
        self._al_elegir = al_elegir
        self._elegida = fecha_inicial or date.today()

        self.title("Seleccionar fecha")
        self.resizable(False, False)
        self.configure(fg_color=COLORES["fondo_tarjeta"])
        # Modal: mientras está abierta, solo esta ventana recibe eventos.
        self.transient(master)
        self.grab_set()

        self._anno = self._elegida.year
        self._mes = self._elegida.month

        self._construir_controles()
        self._dibujar_mes()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _construir_controles(self):
        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.pack(fill="x", padx=10, pady=(10, 4))
        ctk.CTkButton(barra, text="<", width=34, corner_radius=8,
                      fg_color=COLORES["boton_lateral"],
                      hover_color=COLORES["hover_lateral"],
                      command=self._mes_anterior).pack(side="left")
        self._etiqueta_mes = ctk.CTkLabel(
            barra, text="", font=(FUENTE, 13, "bold"), text_color=COLORES["texto"])
        self._etiqueta_mes.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(barra, text=">", width=34, corner_radius=8,
                      fg_color=COLORES["boton_lateral"],
                      hover_color=COLORES["hover_lateral"],
                      command=self._mes_siguiente).pack(side="right")

        # Encabezado de días de la semana (lunes a domingo).
        fila_dias = ctk.CTkFrame(self, fg_color="transparent")
        fila_dias.pack(fill="x", padx=10)
        for indice, dia in enumerate(DIAS_CABECERA):
            ctk.CTkLabel(fila_dias, text=dia, width=36,
                         font=(FUENTE, 11, "bold"),
                         text_color=COLORES["texto_secundario"]).grid(
                row=0, column=indice)

        self._cuadricula = ctk.CTkFrame(self, fg_color="transparent")
        self._cuadricula.pack(padx=10, pady=(2, 10))

    def _dibujar_mes(self):
        self._etiqueta_mes.configure(
            text=f"{NOMBRES_MESES[self._mes - 1].capitalize()} de {self._anno}")

        for boton in self._cuadricula.winfo_children():
            boton.destroy()

        # calendar.monthcalendar: semanas con None donde no hay día.
        for fila, semana in enumerate(
                calendar.monthcalendar(self._anno, self._mes)):
            for columna, dia in enumerate(semana):
                if dia == 0:
                    continue
                es_elegida = (dia == self._elegida.day
                              and self._anno == self._elegida.year
                              and self._mes == self._elegida.month)
                ctk.CTkButton(
                    self._cuadricula, text=str(dia), width=36, height=30,
                    corner_radius=8,
                    fg_color=COLORES["acento"] if es_elegida
                    else COLORES["boton_lateral"],
                    hover_color=COLORES["hover_lateral"],
                    text_color="#10241C" if es_elegida else COLORES["texto"],
                    font=(FUENTE, 11),
                    command=lambda d=dia: self._elegir(dia),
                ).grid(row=fila, column=columna, padx=1, pady=1)

    def _mes_anterior(self):
        self._mes -= 1
        if self._mes == 0:
            self._mes = 12
            self._anno -= 1
        self._dibujar_mes()

    def _mes_siguiente(self):
        self._mes += 1
        if self._mes == 13:
            self._mes = 1
            self._anno += 1
        self._dibujar_mes()

    def _elegir(self, dia):
        self._elegida = date(self._anno, self._mes, dia)
        self.destroy()
        self._al_elegir(self._elegida)
