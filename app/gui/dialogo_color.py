"""Selector de color propio (reemplaza el diálogo antiguo del sistema).

Cuadro de saturación/brillo arrastrable + barra de tono, con vista
previa y botón de elegir. Devuelve el color elegido como #RRGGBB
mediante un callback; si se cierra sin elegir, no llama al callback.
"""

import colorsys
import tkinter as tk

import customtkinter as ctk

from app.gui.estilos import COLORES, FUENTE

TAMANO_CELDA = 4  # px por celda del cuadro de saturación/brillo.


def hsv_a_hex(tono, saturacion, brillo):
    """Convierte HSV (0-1 cada uno) a '#RRGGBB'."""
    rojo, verde, azul = colorsys.hsv_to_rgb(tono, saturacion, brillo)
    return "#{:02X}{:02X}{:02X}".format(
        round(rojo * 255), round(verde * 255), round(azul * 255))


def hex_a_hsv(hexadecimal):
    """Convierte '#RRGGBB' a HSV (0-1 cada uno)."""
    texto = str(hexadecimal).lstrip("#")
    rojo = int(texto[0:2], 16) / 255
    verde = int(texto[2:4], 16) / 255
    azul = int(texto[4:6], 16) / 255
    return colorsys.rgb_to_hsv(rojo, verde, azul)


class DialogoColor(ctk.CTkToplevel):
    """Ventana para elegir un color con cuadro y barra de tono."""

    ANCHO = 300
    ALTO_CAMPO = 200
    ALTO_BARRA = 24

    def __init__(self, master, al_elegir, color_inicial="#FBB718", **kwargs):
        super().__init__(master, **kwargs)
        self._al_elegir = al_elegir
        self._tono, self._saturacion, self._brillo = hex_a_hsv(color_inicial)

        self.title("Elegir color")
        self.resizable(False, False)
        self.configure(fg_color=COLORES["fondo_tarjeta"])
        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self._construir()
        self._dibujar_campo()
        self._dibujar_barra()
        self._actualizar_marcadores()

    # ------------------------------------------------------------------
    # Construcción
    # ------------------------------------------------------------------

    def _construir(self):
        ctk.CTkLabel(self, text="Elija un color",
                     font=(FUENTE, 13, "bold"),
                     text_color=COLORES["texto"]).pack(anchor="w", padx=14,
                                                        pady=(10, 4))

        # Cuadro de saturación (horizontal) y brillo (vertical).
        self._lienzo_campo = tk.Canvas(
            self, width=self.ANCHO, height=self.ALTO_CAMPO,
            bg=COLORES["fondo_tarjeta"], highlightthickness=0)
        self._lienzo_campo.pack(padx=14)

        # Barra de tono (arcoíris horizontal).
        self._lienzo_barra = tk.Canvas(
            self, width=self.ANCHO, height=self.ALTO_BARRA,
            bg=COLORES["fondo_tarjeta"], highlightthickness=0)
        self._lienzo_barra.pack(padx=14, pady=(8, 0))

        # Vista previa + botones.
        fila = ctk.CTkFrame(self, fg_color="transparent")
        fila.pack(fill="x", padx=14, pady=(10, 12))
        self._lienzo_previa = tk.Canvas(fila, width=52, height=32,
                                        bg=COLORES["fondo_tarjeta"],
                                        highlightthickness=1,
                                        highlightbackground=COLORES["borde_tabla"])
        self._lienzo_previa.pack(side="left")
        self._etiqueta_hex = ctk.CTkLabel(fila, text="", font=(FUENTE, 12),
                                         text_color=COLORES["texto"])
        self._etiqueta_hex.pack(side="left", padx=10)
        ctk.CTkButton(fila, text="Cancelar", width=90, corner_radius=14,
                      font=(FUENTE, 11), fg_color=COLORES["boton_lateral"],
                      hover_color=COLORES["hover_lateral"],
                      command=self.destroy).pack(side="right")
        ctk.CTkButton(fila, text="Elegir", width=90, corner_radius=14,
                      font=(FUENTE, 11, "bold"), fg_color=COLORES["acento"],
                      hover_color=COLORES["acento_hover"],
                      text_color="#10241C",
                      command=self._al_elegir).pack(side="right", padx=8)

        # Arrastre con el mouse.
        for lienzo, manejador in ((self._lienzo_campo, self._al_arrastar_campo),
                                  (self._lienzo_barra, self._al_arrastar_barra)):
            lienzo.bind("<Button-1>", manejador)
            lienzo.bind("<B1-Motion>", manejador)

    # ------------------------------------------------------------------
    # Dibujo del cuadro y la barra
    # ------------------------------------------------------------------

    def _dibujar_campo(self):
        """Dibuja el cuadro saturación/brillo del tono actual."""
        self._lienzo_campo.delete("all")
        columnas = self.ANCHO // TAMANO_CELDA
        filas = self.ALTO_CAMPO // TAMANO_CELDA
        for columna in range(columnas):
            saturacion = columna / (columnas - 1)
            for fila in range(filas):
                brillo = 1 - fila / (filas - 1)
                color = hsv_a_hex(self._tono, saturacion, brillo)
                self._lienzo_campo.create_rectangle(
                    columna * TAMANO_CELDA, fila * TAMANO_CELDA,
                    (columna + 1) * TAMANO_CELDA,
                    (fila + 1) * TAMANO_CELDA,
                    fill=color, outline="")

    def _dibujar_barra(self):
        """Dibuja la barra de tonos (arcoíris)."""
        self._lienzo_barra.delete("all")
        pasos = self.ANCHO
        for x in range(pasos):
            self._lienzo_barra.create_rectangle(
                x, 0, x + 1, self.ALTO_BARRA,
                fill=hsv_a_hex(x / (pasos - 1), 1, 1), outline="")

    def _actualizar_marcadores(self):
        """Mueve el marcador del cuadro y la barra; actualiza la previa."""
        # Marcador en el cuadro (posición de saturación/brillo).
        self._lienzo_campo.delete("marcador")
        x = self._saturacion * self.ANCHO
        y = (1 - self._brillo) * self.ALTO_CAMPO
        radio = 6
        self._lienzo_campo.create_oval(
            x - radio, y - radio, x + radio, y + radio,
            outline="#FFFFFF", width=2, tags="marcador")

        # Marcador en la barra (posición del tono).
        self._lienzo_barra.delete("marcador")
        hx = self._tono * self.ANCHO
        self._lienzo_barra.create_rectangle(
            hx - 2, 0, hx + 2, self.ALTO_BARRA,
            outline="#FFFFFF", width=2, tags="marcador")

        # Vista previa.
        color = self.color_actual()
        self._lienzo_previa.delete("previa")
        self._lienzo_previa.create_rectangle(
            0, 0, 52, 32, fill=color, outline="", tags="previa")
        self._etiqueta_hex.configure(text=color)

    # ------------------------------------------------------------------
    # Interacción
    # ------------------------------------------------------------------

    def _al_arrastar_campo(self, evento):
        """Clic o arrastre sobre el cuadro: fija saturación y brillo."""
        self._saturacion = max(0, min(1, evento.x / self.ANCHO))
        self._brillo = max(0, min(1, 1 - evento.y / self.ALTO_CAMPO))
        self._actualizar_marcadores()

    def _al_arrastar_barra(self, evento):
        """Clic o arrastre sobre la barra: fija el tono y redibuja."""
        self._tono = max(0, min(1, evento.x / self.ANCHO))
        self._dibujar_campo()
        self._actualizar_marcadores()

    def color_actual(self):
        """Color elegido hasta ahora, como '#RRGGBB'."""
        return hsv_a_hex(self._tono, self._saturacion, self._brillo)

    def _al_elegir(self):
        color = self.color_actual()
        self.destroy()
        self._al_elegir(color)
