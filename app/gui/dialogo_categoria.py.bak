"""Diálogo modal para crear una categoría personalizada de Gastos en NexSaldo."""

from tkinter import messagebox
from typing import Callable, Dict, Optional
import customtkinter as ctk

from app.gestor.gestor_financiero import (
    CATALOGO_SIMBOLOS_CATEGORIAS,
    ErrorValidacion,
    FRECUENCIAS_VALIDAS,
    GestorFinanciero,
)
from app.gui.dialogo_color import DialogoColor
from app.gui.estilos import COLORES, COLORES_PREDETERMINADOS, FUENTE
from app.gui.iconos import icono_ctk
from app.modelo.categoria import Categoria

ETIQUETAS_FRECUENCIA = {
    "DIARIO": "Diario",
    "SEMANAL": "Semanal",
    "QUINCENAL": "Quincenal",
    "MENSUAL": "Mensual",
    "ANUAL": "Anual",
}


class DialogoCategoria(ctk.CTkToplevel):
    """Permite crear una categoría personalizada con ícono categorizado, gasto programado y color."""

    def __init__(
        self,
        master,
        gestor: GestorFinanciero,
        al_crear: Callable[[Categoria], None],
        tipo_inicial: str = "GASTO",
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self._gestor = gestor
        self._al_crear = al_crear
        self._tipo = tipo_inicial.upper() if tipo_inicial else "GASTO"
        self._simbolo_elegido = "factura"
        self._color_elegido = COLORES_PREDETERMINADOS[0]
        self._botones_simbolos: Dict[str, ctk.CTkButton] = {}
        self._grupo_actual = list(CATALOGO_SIMBOLOS_CATEGORIAS.keys())[0]

        self.title("Crear categoría")
        self.geometry("620x740")
        self.resizable(False, False)
        self.configure(fg_color=COLORES["fondo_lateral"])
        self.transient(master)
        self.grab_set()

        self._construir_interfaz()

    def _construir_interfaz(self):
        contenedor = ctk.CTkScrollableFrame(
            self, fg_color="transparent", width=580, height=690
        )
        contenedor.pack(fill="both", expand=True, padx=16, pady=14)

        # --- Cabecera y vista previa circular ---
        fila_cabecera = ctk.CTkFrame(contenedor, fg_color="transparent")
        fila_cabecera.pack(fill="x", pady=(0, 12))

        self._preview_circulo = ctk.CTkButton(
            fila_cabecera,
            text="",
            width=64,
            height=64,
            corner_radius=32,
            fg_color=self._color_elegido,
            hover_color=self._color_elegido,
            image=icono_ctk(self._simbolo_elegido, color="#10241C", tamano=32),
            state="disabled",
        )
        self._preview_circulo.pack(side="left", padx=(0, 14))

        col_titulo = ctk.CTkFrame(fila_cabecera, fg_color="transparent")
        col_titulo.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            col_titulo,
            text="Nueva categoría personalizada",
            font=(FUENTE, 18, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w")

        ctk.CTkLabel(
            col_titulo,
            text="Elige nombre, tipo, gasto programado, símbolo categorizado y color.",
            font=(FUENTE, 12),
            text_color=COLORES["texto_secundario"],
        ).pack(anchor="w")

        # --- 1. Nombre de la categoría y Tipo (preseleccionado Gastos) ---
        marco_datos = ctk.CTkFrame(
            contenedor, fg_color=COLORES["fondo_tarjeta"], corner_radius=10
        )
        marco_datos.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            marco_datos,
            text="Nombre de la categoría",
            font=(FUENTE, 13, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w", padx=14, pady=(10, 4))

        self._campo_nombre = ctk.CTkEntry(
            marco_datos,
            placeholder_text="Ej: Vacaciones de playa, Mascotas, Streaming...",
            fg_color=COLORES["campo_fondo"],
            text_color=COLORES["campo_texto"],
            font=(FUENTE, 13),
            height=36,
            corner_radius=8,
        )
        self._campo_nombre.pack(fill="x", padx=14, pady=(0, 10))

        fila_tipo = ctk.CTkFrame(marco_datos, fg_color="transparent")
        fila_tipo.pack(fill="x", padx=14, pady=(0, 12))

        ctk.CTkLabel(
            fila_tipo,
            text="Tipo de categoría:",
            font=(FUENTE, 13, "bold"),
            text_color=COLORES["texto"],
        ).pack(side="left", padx=(0, 14))

        self._var_tipo = ctk.StringVar(value=self._tipo)
        ctk.CTkRadioButton(
            fila_tipo,
            text="Gastos",
            variable=self._var_tipo,
            value="GASTO",
            font=(FUENTE, 13, "bold"),
            text_color=COLORES["texto"],
            fg_color=COLORES["acento"],
            hover_color=COLORES["acento_hover"],
        ).pack(side="left", padx=(0, 18))

        ctk.CTkRadioButton(
            fila_tipo,
            text="Ingresos",
            variable=self._var_tipo,
            value="INGRESO",
            font=(FUENTE, 13),
            text_color=COLORES["texto_secundario"],
            fg_color=COLORES["acento"],
            hover_color=COLORES["acento_hover"],
        ).pack(side="left")

        # --- 2. Gasto programado (recurrente automático) ---
        marco_prog = ctk.CTkFrame(
            contenedor, fg_color=COLORES["fondo_tarjeta"], corner_radius=10
        )
        marco_prog.pack(fill="x", pady=(0, 12))

        fila_switch = ctk.CTkFrame(marco_prog, fg_color="transparent")
        fila_switch.pack(fill="x", padx=14, pady=(10, 8))

        self._var_programado = ctk.BooleanVar(value=False)
        self._switch_programado = ctk.CTkSwitch(
            fila_switch,
            text="Gasto programado (ocurre automáticamente cada cierto tiempo)",
            variable=self._var_programado,
            font=(FUENTE, 13, "bold"),
            text_color=COLORES["texto"],
            progress_color=COLORES["acento"],
            button_color=COLORES["texto"],
            command=self._al_cambiar_programado,
        )
        self._switch_programado.pack(side="left")

        self._fila_frecuencia = ctk.CTkFrame(marco_prog, fg_color="transparent")
        ctk.CTkLabel(
            self._fila_frecuencia,
            text="Frecuencia automática:",
            font=(FUENTE, 12),
            text_color=COLORES["texto_secundario"],
        ).pack(side="left", padx=(0, 10))

        self._var_frecuencia = ctk.StringVar(value="Mensual")
        self._combo_frecuencia = ctk.CTkOptionMenu(
            self._fila_frecuencia,
            values=[ETIQUETAS_FRECUENCIA[f] for f in FRECUENCIAS_VALIDAS],
            variable=self._var_frecuencia,
            fg_color=COLORES["boton_lateral"],
            button_color=COLORES["acento"],
            button_hover_color=COLORES["acento_hover"],
            text_color=COLORES["texto"],
            font=(FUENTE, 12, "bold"),
            width=160,
        )
        self._combo_frecuencia.pack(side="left")

        # --- 3. Selección de símbolos categorizados ---
        marco_simbolos = ctk.CTkFrame(
            contenedor, fg_color=COLORES["fondo_tarjeta"], corner_radius=10
        )
        marco_simbolos.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            marco_simbolos,
            text="Seleccionar símbolo por categoría",
            font=(FUENTE, 13, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w", padx=14, pady=(10, 6))

        # Pestañas/botones de grupos de íconos
        marco_grupos = ctk.CTkFrame(marco_simbolos, fg_color="transparent")
        marco_grupos.pack(fill="x", padx=10, pady=(0, 8))

        self._botones_grupos: Dict[str, ctk.CTkButton] = {}
        grupos = list(CATALOGO_SIMBOLOS_CATEGORIAS.keys())
        for idx, nombre_grupo in enumerate(grupos):
            fila_g = idx // 3
            col_g = idx % 3
            marco_grupos.grid_columnconfigure(col_g, weight=1)
            activo = nombre_grupo == self._grupo_actual
            btn_g = ctk.CTkButton(
                marco_grupos,
                text=nombre_grupo,
                height=28,
                corner_radius=6,
                fg_color=COLORES["acento"] if activo else COLORES["boton_lateral"],
                hover_color=COLORES["acento_hover"] if activo else COLORES["hover_lateral"],
                text_color=COLORES["campo_texto"] if activo else COLORES["texto"],
                font=(FUENTE, 11, "bold" if activo else "normal"),
                command=lambda g=nombre_grupo: self._cambiar_grupo_simbolos(g),
            )
            btn_g.grid(row=fila_g, column=col_g, padx=4, pady=3, sticky="ew")
            self._botones_grupos[nombre_grupo] = btn_g

        self._rejilla_simbolos = ctk.CTkFrame(
            marco_simbolos, fg_color=COLORES["fondo_lateral"], corner_radius=8
        )
        self._rejilla_simbolos.pack(fill="x", padx=14, pady=(4, 12))

        self._renderizar_simbolos_grupo(self._grupo_actual)

        # --- 4. Selección de Color (Predeterminados + Últimos usados + botón '+') ---
        marco_colores = ctk.CTkFrame(
            contenedor, fg_color=COLORES["fondo_tarjeta"], corner_radius=10
        )
        marco_colores.pack(fill="x", pady=(0, 14))

        ctk.CTkLabel(
            marco_colores,
            text="Colores predeterminados",
            font=(FUENTE, 13, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w", padx=14, pady=(10, 6))

        self._fila_predeterminados = ctk.CTkFrame(marco_colores, fg_color="transparent")
        self._fila_predeterminados.pack(fill="x", padx=14, pady=(0, 8))

        ctk.CTkLabel(
            marco_colores,
            text="Últimos colores usados",
            font=(FUENTE, 12, "bold"),
            text_color=COLORES["texto_secundario"],
        ).pack(anchor="w", padx=14, pady=(2, 4))

        self._fila_recientes = ctk.CTkFrame(marco_colores, fg_color="transparent")
        self._fila_recientes.pack(fill="x", padx=14, pady=(0, 12))

        self._renderizar_filas_colores()

        # --- 5. Botón Amarillo "Añadir categoría" ---
        fila_acciones = ctk.CTkFrame(contenedor, fg_color="transparent")
        fila_acciones.pack(fill="x", pady=(4, 6))

        ctk.CTkButton(
            fila_acciones,
            text="Cancelar",
            width=120,
            height=40,
            corner_radius=8,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 13),
            command=self.destroy,
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            fila_acciones,
            text="Añadir categoría",
            width=190,
            height=40,
            corner_radius=8,
            fg_color=COLORES["acento"],
            hover_color=COLORES["acento_hover"],
            text_color=COLORES["campo_texto"],
            font=(FUENTE, 14, "bold"),
            command=self._guardar_categoria,
        ).pack(side="right")

    def _al_cambiar_programado(self):
        if self._var_programado.get():
            self._fila_frecuencia.pack(fill="x", padx=14, pady=(0, 10))
        else:
            self._fila_frecuencia.pack_forget()

    def _cambiar_grupo_simbolos(self, nuevo_grupo: str):
        self._grupo_actual = nuevo_grupo
        for nombre_g, btn in self._botones_grupos.items():
            activo = nombre_g == nuevo_grupo
            btn.configure(
                fg_color=COLORES["acento"] if activo else COLORES["boton_lateral"],
                hover_color=COLORES["acento_hover"] if activo else COLORES["hover_lateral"],
                text_color=COLORES["campo_texto"] if activo else COLORES["texto"],
                font=(FUENTE, 11, "bold" if activo else "normal"),
            )
        self._renderizar_simbolos_grupo(nuevo_grupo)

    def _renderizar_simbolos_grupo(self, nombre_grupo: str):
        for hijo in self._rejilla_simbolos.winfo_children():
            hijo.destroy()
        self._botones_simbolos.clear()

        items = CATALOGO_SIMBOLOS_CATEGORIAS.get(nombre_grupo, [])
        columnas = 4
        for c in range(columnas):
            self._rejilla_simbolos.grid_columnconfigure(c, weight=1)

        for idx, (clave, etiqueta) in enumerate(items):
            fila = idx // columnas
            col = idx % columnas
            seleccionado = clave == self._simbolo_elegido
            color_fondo = self._color_elegido if seleccionado else COLORES["boton_lateral"]
            color_icono = "#10241C" if seleccionado else "#FFFFFF"

            celda = ctk.CTkFrame(self._rejilla_simbolos, fg_color="transparent")
            celda.grid(row=fila, column=col, padx=6, pady=6)

            btn = ctk.CTkButton(
                celda,
                text="",
                width=46,
                height=46,
                corner_radius=23,
                fg_color=color_fondo,
                hover_color=self._color_elegido,
                border_width=2 if seleccionado else 0,
                border_color="#FFFFFF",
                image=icono_ctk(clave, color=color_icono, tamano=24),
                command=lambda k=clave: self._seleccionar_simbolo(k),
            )
            btn.pack()

            ctk.CTkLabel(
                celda,
                text=etiqueta,
                font=(FUENTE, 10),
                text_color=COLORES["texto"] if seleccionado else COLORES["texto_secundario"],
            ).pack(pady=(2, 0))
            self._botones_simbolos[clave] = btn

    def _seleccionar_simbolo(self, clave: str):
        self._simbolo_elegido = clave
        self._actualizar_preview()
        self._renderizar_simbolos_grupo(self._grupo_actual)

    def _renderizar_filas_colores(self):
        for hijo in self._fila_predeterminados.winfo_children():
            hijo.destroy()
        for hijo in self._fila_recientes.winfo_children():
            hijo.destroy()

        # Línea superior: Colores predeterminados + botón '+' para abrir la ruedita DialogoColor
        for color_hex in COLORES_PREDETERMINADOS:
            es_actual = color_hex.upper() == self._color_elegido.upper()
            btn = ctk.CTkButton(
                self._fila_predeterminados,
                text="",
                width=32,
                height=32,
                corner_radius=16,
                fg_color=color_hex,
                hover_color=color_hex,
                border_width=3 if es_actual else 1,
                border_color="#FFFFFF" if es_actual else COLORES["fondo_lateral"],
                command=lambda c=color_hex: self._seleccionar_color(c),
            )
            btn.pack(side="left", padx=4)

        btn_mas_color = ctk.CTkButton(
            self._fila_predeterminados,
            text="+",
            width=32,
            height=32,
            corner_radius=16,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 16, "bold"),
            command=self._abrir_ruedita_color,
        )
        btn_mas_color.pack(side="left", padx=(8, 0))

        # Línea inferior: Últimos colores usados
        recientes = self._gestor.obtener_colores_recientes()
        if not recientes:
            ctk.CTkLabel(
                self._fila_recientes,
                text="Aún no hay colores recientes guardados.",
                font=(FUENTE, 11),
                text_color=COLORES["texto_secundario"],
            ).pack(side="left")
        else:
            for color_rec in recientes:
                es_actual = color_rec.upper() == self._color_elegido.upper()
                btn_r = ctk.CTkButton(
                    self._fila_recientes,
                    text="",
                    width=28,
                    height=28,
                    corner_radius=14,
                    fg_color=color_rec,
                    hover_color=color_rec,
                    border_width=3 if es_actual else 1,
                    border_color="#FFFFFF" if es_actual else COLORES["fondo_lateral"],
                    command=lambda c=color_rec: self._seleccionar_color(c),
                )
                btn_r.pack(side="left", padx=4)

    def _seleccionar_color(self, color_hex: str):
        self._color_elegido = color_hex.upper()
        self._gestor.registrar_color_reciente(self._color_elegido)
        self._actualizar_preview()
        self._renderizar_filas_colores()
        self._renderizar_simbolos_grupo(self._grupo_actual)

    def _abrir_ruedita_color(self):
        DialogoColor(
            self,
            al_elegir=self._seleccionar_color,
            color_inicial=self._color_elegido,
        )

    def _actualizar_preview(self):
        self._preview_circulo.configure(
            fg_color=self._color_elegido,
            hover_color=self._color_elegido,
            image=icono_ctk(self._simbolo_elegido, color="#10241C", tamano=32),
        )

    def _guardar_categoria(self):
        nombre = self._campo_nombre.get().strip()
        tipo = self._var_tipo.get()
        programado = self._var_programado.get()
        frecuencia_clave: Optional[str] = None
        if programado:
            inverso = {v: k for k, v in ETIQUETAS_FRECUENCIA.items()}
            frecuencia_clave = inverso.get(self._var_frecuencia.get(), "MENSUAL")

        try:
            nueva = self._gestor.crear_categoria(
                nombre=nombre,
                tipo=tipo,
                simbolo=self._simbolo_elegido,
                color=self._color_elegido,
                gasto_programado=programado,
                frecuencia=frecuencia_clave,
            )
        except ErrorValidacion as error:
            messagebox.showwarning("Datos incompletos", str(error), parent=self)
            return

        self._al_crear(nueva)
        self.destroy()
