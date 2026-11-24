"""Selector de apariencia con muestras de los colores reales de cada tema."""

import tkinter as tk

import customtkinter as ctk

from app.gui.estilos import COLORES, FUENTE, TEMAS, TEMA_PREDETERMINADO


class VistaTemas(ctk.CTkFrame):
    def __init__(self, master, tema, al_elegir, guardado):
        super().__init__(master, fg_color="transparent")
        ctk.CTkLabel(self, text="Themes", font=(FUENTE, 26, "bold"),
                     text_color=COLORES["texto"]).pack(anchor="w")
        ctk.CTkLabel(self, text="Elige la apariencia de NexSaldo. El cambio es inmediato.",
                     font=(FUENTE, 13), text_color=COLORES["texto_secundario"]).pack(anchor="w")

        rejilla = ctk.CTkFrame(self, fg_color="transparent")
        rejilla.pack(fill="x", pady=(18, 8))
        rejilla.grid_columnconfigure((0, 1, 2), weight=1, uniform="temas")
        self._seleccion = tk.StringVar(master=self, value=tema)
        self._opciones = {}
        for indice, (clave, (nombre, descripcion, paleta)) in enumerate(TEMAS.items()):
            activo = clave == tema
            fondo = COLORES["fondo_tarjeta"]
            borde = COLORES["acento" if activo else "borde_tabla"]
            tarjeta = ctk.CTkFrame(rejilla, fg_color=fondo, border_color=borde,
                                   border_width=2 if activo else 1, corner_radius=12)
            tarjeta.grid(row=indice // 3, column=indice % 3, sticky="ew", padx=5, pady=5)

            # La muestra no depende del tema activo: usa la paleta que representa.
            muestra = tk.Canvas(tarjeta, bg=paleta["fondo_contenido"], width=1, height=58,
                               highlightthickness=0, cursor="hand2", takefocus=False)
            muestra.pack(fill="x", padx=12, pady=(12, 4))
            muestra.bind("<Configure>", lambda evento, p=paleta: self._dibujar_muestra(evento, p))

            etiqueta = f"{nombre} (predeterminado)" if clave == TEMA_PREDETERMINADO else nombre
            opcion = tk.Radiobutton(
                tarjeta, text=etiqueta, variable=self._seleccion, value=clave,
                command=lambda t=clave: al_elegir(t), anchor="w", cursor="hand2",
                bg=fondo, fg=COLORES["texto"], selectcolor=COLORES["fondo_lateral"],
                activebackground=fondo, activeforeground=COLORES["texto"],
                highlightbackground=fondo, highlightcolor=COLORES["acento"],
                highlightthickness=2, borderwidth=0, font=(FUENTE, 11, "bold"),
            )
            opcion.pack(fill="x", padx=9)
            opcion.bind("<Return>", lambda _evento, radio=opcion: radio.invoke())
            self._opciones[clave] = opcion
            muestra.bind("<Button-1>", lambda _evento, radio=opcion: radio.invoke())
            ctk.CTkLabel(tarjeta, text=descripcion, font=(FUENTE, 11),
                         text_color=COLORES["texto_secundario"]).pack(anchor="w", padx=14, pady=(0, 8))

        mensaje = f"Tema activo: {TEMAS[tema][0]}. La elección se guarda en este dispositivo."
        if not guardado:
            mensaje = "El tema cambió, pero no se pudo guardar la preferencia en este dispositivo."
        ctk.CTkLabel(self, text=mensaje, font=(FUENTE, 12), text_color=COLORES[
            "texto_secundario" if guardado else "error"
        ]).pack(anchor="w", padx=5)

    def enfocar_tema(self, tema):
        self._opciones[tema].focus_set()

    @staticmethod
    def _dibujar_muestra(evento, paleta):
        lienzo = evento.widget
        lienzo.delete("all")
        for coords, token in (
            ((6, 6, 30, 52), "fondo_lateral"),
            ((36, 8, evento.width - 7, 50), "fondo_tarjeta"),
            ((45, 17, 78, 24), "acento"),
            ((45, 33, 95, 36), "texto_secundario"),
        ):
            lienzo.create_rectangle(*coords, fill=paleta[token], outline="")
