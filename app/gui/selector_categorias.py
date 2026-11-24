"""Selector reutilizable de categorías con creación inline ('+' / 'Más') y menú contextual (clic derecho) para Editar y Eliminar."""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Dict, List, Optional, Tuple

import customtkinter as ctk

from app.gui.estilos import COLORES, FUENTE
from app.gui.iconos import icono_ctk
from app.modelo.categoria import Categoria

GRIS_BOTON_MAS = "#8A8F98"
HOVER_BOTON_MAS = "#6E737B"


def _enlazar_clic_derecho(widget, callback: Callable) -> None:
    """Enlaza el evento de clic derecho en el widget y sus hijos internos de CustomTkinter."""
    for secuencia in ("<Button-3>", "<Button-2>", "<Control-Button-1>"):
        try:
            widget.bind(secuencia, callback, add="+")
        except Exception:
            pass
    for attr in ("_canvas", "_text_label", "_image_label"):
        interno = getattr(widget, attr, None)
        if interno is not None:
            for secuencia in ("<Button-3>", "<Button-2>", "<Control-Button-1>"):
                try:
                    interno.bind(secuencia, callback, add="+")
                except Exception:
                    pass


class DialogoEliminarCategoria(ctk.CTkToplevel):
    """Modal de confirmación segura para eliminar una categoría, con reasignación si tiene movimientos."""

    def __init__(
        self,
        master,
        categoria: Categoria,
        cantidad_movimientos: int,
        alternativas: List[Categoria],
        al_confirmar: Callable[[Optional[int]], None],
    ) -> None:
        super().__init__(master)
        self._categoria = categoria
        self._cantidad = cantidad_movimientos
        self._alternativas = alternativas
        self._al_confirmar = al_confirmar
        self._mapa_nombres: Dict[str, int] = {
            c.nombre: c.id for c in alternativas if c.id is not None
        }

        self.title("Eliminar categoría")
        self.resizable(False, False)
        self.configure(fg_color=COLORES["fondo_lateral"])
        self.transient(master)
        self.grab_set()

        alto = 290 if cantidad_movimientos > 0 else 210
        self.geometry(f"440x{alto}")
        self._construir_ui()
        self._centrar_en_padre(master)

    def _centrar_en_padre(self, master) -> None:
        self.update_idletasks()
        try:
            px = master.winfo_rootx() + (master.winfo_width() // 2)
            py = master.winfo_rooty() + (master.winfo_height() // 2)
            w, h = self.winfo_width(), self.winfo_height()
            self.geometry(f"+{max(0, px - w // 2)}+{max(0, py - h // 2)}")
        except Exception:
            pass

    def _construir_ui(self) -> None:
        contenedor = ctk.CTkFrame(self, fg_color="transparent")
        contenedor.pack(fill="both", expand=True, padx=24, pady=20)

        ctk.CTkLabel(
            contenedor,
            text=f"Eliminar «{self._categoria.nombre}»",
            font=ctk.CTkFont(family=FUENTE, size=17, weight="bold"),
            text_color=COLORES["texto"],
            anchor="w",
        ).pack(fill="x", pady=(0, 8))

        if self._cantidad > 0:
            plural = "movimiento asociado" if self._cantidad == 1 else "movimientos asociados"
            aviso = (
                f"Esta categoría tiene {self._cantidad} {plural}. "
                "Selecciona a qué categoría reasignarlos antes de eliminarla:"
            )
            ctk.CTkLabel(
                contenedor,
                text=aviso,
                font=ctk.CTkFont(family=FUENTE, size=13),
                text_color=COLORES["texto_secundario"],
                wraplength=390,
                justify="left",
                anchor="w",
            ).pack(fill="x", pady=(0, 12))

            nombres_alt = list(self._mapa_nombres.keys())
            predeterminada = self._elegir_destino_por_defecto(nombres_alt)
            self._var_destino = ctk.StringVar(value=predeterminada)
            ctk.CTkOptionMenu(
                contenedor,
                variable=self._var_destino,
                values=nombres_alt,
                fg_color=COLORES["fondo_tarjeta"],
                button_color=COLORES["acento"],
                button_hover_color=COLORES["acento_hover"],
                text_color=COLORES["texto"],
                dropdown_fg_color=COLORES["fondo_lateral"],
                dropdown_hover_color=COLORES["hover_lateral"],
                dropdown_text_color=COLORES["texto"],
                font=ctk.CTkFont(family=FUENTE, size=13),
                height=36,
            ).pack(fill="x", pady=(0, 18))
        else:
            self._var_destino = None
            ctk.CTkLabel(
                contenedor,
                text="Esta categoría no tiene movimientos registrados. ¿Deseas eliminarla permanentemente?",
                font=ctk.CTkFont(family=FUENTE, size=13),
                text_color=COLORES["texto_secundario"],
                wraplength=390,
                justify="left",
                anchor="w",
            ).pack(fill="x", pady=(0, 18))

        fila_botones = ctk.CTkFrame(contenedor, fg_color="transparent")
        fila_botones.pack(fill="x", side="bottom")

        ctk.CTkButton(
            fila_botones,
            text="Cancelar",
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=ctk.CTkFont(family=FUENTE, size=13, weight="bold"),
            height=38,
            command=self.destroy,
        ).pack(side="left", expand=True, fill="x", padx=(0, 8))

        texto_accion = "Reasignar y eliminar" if self._cantidad > 0 else "Eliminar"
        ctk.CTkButton(
            fila_botones,
            text=texto_accion,
            fg_color=COLORES["error"],
            hover_color="#D97070",
            text_color="#10241C",
            font=ctk.CTkFont(family=FUENTE, size=13, weight="bold"),
            height=38,
            command=self._confirmar,
        ).pack(side="right", expand=True, fill="x", padx=(8, 0))

    @staticmethod
    def _elegir_destino_por_defecto(nombres: List[str]) -> str:
        for candidato in ("Otros gastos", "Otros ingresos", "Otros"):
            if candidato in nombres:
                return candidato
        return nombres[0] if nombres else ""

    def _confirmar(self) -> None:
        destino_id: Optional[int] = None
        if self._var_destino is not None:
            destino_id = self._mapa_nombres.get(self._var_destino.get())
        self.destroy()
        self._al_confirmar(destino_id)


class SelectorCategorias(ctk.CTkFrame):
    """Cuadrícula de chips circulares de categorías con '+' ('Más') y menú contextual clic derecho."""

    def __init__(
        self,
        master,
        gestor,
        tipo: str,
        categoria_inicial: str,
        al_seleccionar: Callable[[str], None],
        al_modificar: Optional[Callable[[], None]] = None,
        columnas: int = 5,
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._gestor = gestor
        self._tipo = tipo.upper()
        self._categoria_elegida = categoria_inicial
        self._al_seleccionar = al_seleccionar
        self._al_modificar = al_modificar
        self._columnas = columnas
        self._widgets_categorias: Dict[str, Tuple[ctk.CTkButton, ctk.CTkLabel]] = {}
        self._categorias_actuales: List[Categoria] = []
        self._menu_contextual: Optional[tk.Menu] = None
        self._lbl_error: Optional[ctk.CTkLabel] = None

        self._marco_grid = ctk.CTkFrame(self, fg_color="transparent")
        self._marco_grid.pack(fill="x", expand=True)

        self._lbl_pista = ctk.CTkLabel(
            self,
            text="Clic derecho en una categoría para editarla o eliminarla",
            font=ctk.CTkFont(family=FUENTE, size=11),
            text_color=COLORES["texto_secundario"],
            anchor="w",
        )
        self._lbl_pista.pack(fill="x", pady=(6, 0))

        self.renderizar()

    @property
    def categoria_elegida(self) -> str:
        return self._categoria_elegida

    def establecer_categoria(self, nombre: str) -> None:
        self._categoria_elegida = nombre
        self._actualizar_bordes()

    def _mostrar_aviso(self, mensaje: str) -> None:
        if self._lbl_error is None:
            self._lbl_error = ctk.CTkLabel(
                self,
                text=mensaje,
                font=ctk.CTkFont(family=FUENTE, size=12),
                text_color=COLORES["error"],
                anchor="w",
                wraplength=460,
            )
            self._lbl_error.pack(fill="x", pady=(4, 0))
        else:
            self._lbl_error.configure(text=mensaje)

    def _limpiar_aviso(self) -> None:
        if self._lbl_error is not None:
            self._lbl_error.configure(text="")

    def renderizar(self) -> None:
        for hijo in self._marco_grid.winfo_children():
            hijo.destroy()
        self._widgets_categorias.clear()

        categorias = self._gestor.obtener_categorias_detalladas(self._tipo)
        self._categorias_actuales = list(categorias)

        nombres_disponibles = [c.nombre for c in categorias]
        if nombres_disponibles and self._categoria_elegida not in nombres_disponibles:
            self._categoria_elegida = nombres_disponibles[0]
            self._al_seleccionar(self._categoria_elegida)

        for idx, cat in enumerate(categorias):
            fila = idx // self._columnas
            col = idx % self._columnas
            celda = ctk.CTkFrame(self._marco_grid, fg_color="transparent")
            celda.grid(row=fila, column=col, padx=6, pady=6, sticky="n")

            activa = cat.nombre == self._categoria_elegida
            btn = ctk.CTkButton(
                celda,
                text="",
                width=54,
                height=54,
                corner_radius=27,
                fg_color=cat.color,
                hover_color=cat.color,
                border_width=3 if activa else 0,
                border_color="#FFFFFF",
                image=icono_ctk(cat.simbolo, color="#10241C", tamano=26),
                command=lambda n=cat.nombre: self._seleccionar(n),
            )
            btn.pack()

            etiqueta = f"{cat.nombre} ⏱" if cat.gasto_programado else cat.nombre
            lbl = ctk.CTkLabel(
                celda,
                text=etiqueta,
                font=ctk.CTkFont(family=FUENTE, size=11, weight="bold" if activa else "normal"),
                text_color=COLORES["texto"],
                wraplength=76,
                justify="center",
            )
            lbl.pack(pady=(4, 0))

            # Clic derecho en botón, etiqueta o celda completa
            handler = lambda e, c=cat: self._abrir_menu_contextual(e, c)
            _enlazar_clic_derecho(celda, handler)
            _enlazar_clic_derecho(btn, handler)
            _enlazar_clic_derecho(lbl, handler)

            self._widgets_categorias[cat.nombre] = (btn, lbl)

        # Botón '+' ("Más") para crear categoría inline
        idx_mas = len(categorias)
        celda_mas = ctk.CTkFrame(self._marco_grid, fg_color="transparent")
        celda_mas.grid(
            row=idx_mas // self._columnas,
            column=idx_mas % self._columnas,
            padx=6,
            pady=6,
            sticky="n",
        )
        btn_mas = ctk.CTkButton(
            celda_mas,
            text="",
            width=54,
            height=54,
            corner_radius=27,
            fg_color=GRIS_BOTON_MAS,
            hover_color=HOVER_BOTON_MAS,
            image=icono_ctk("mas", color="#FFFFFF", tamano=26),
            command=self._abrir_crear_categoria,
        )
        btn_mas.pack()
        ctk.CTkLabel(
            celda_mas,
            text="Más",
            font=ctk.CTkFont(family=FUENTE, size=11),
            text_color=COLORES["texto_secundario"],
        ).pack(pady=(4, 0))

        for c_idx in range(self._columnas):
            self._marco_grid.grid_columnconfigure(c_idx, weight=1)

    def _seleccionar(self, nombre: str) -> None:
        self._limpiar_aviso()
        self._categoria_elegida = nombre
        self._actualizar_bordes()
        self._al_seleccionar(nombre)

    def _actualizar_bordes(self) -> None:
        for nombre, (btn, lbl) in self._widgets_categorias.items():
            activa = nombre == self._categoria_elegida
            btn.configure(border_width=3 if activa else 0)
            lbl.configure(
                font=ctk.CTkFont(family=FUENTE, size=11, weight="bold" if activa else "normal")
            )

    def _abrir_menu_contextual(self, evento, categoria: Categoria) -> None:
        self._limpiar_aviso()
        if self._menu_contextual is not None:
            try:
                self._menu_contextual.destroy()
            except Exception:
                pass

        menu = tk.Menu(
            self,
            tearoff=0,
            bg=COLORES["fondo_lateral"],
            fg=COLORES["texto"],
            activebackground=COLORES["hover_lateral"],
            activeforeground=COLORES["acento"],
            bd=1,
            relief="flat",
            font=(FUENTE, 10),
        )
        menu.add_command(
            label=f"✎  Editar «{categoria.nombre}»",
            command=lambda c=categoria: self._abrir_editar_categoria(c),
        )
        menu.add_separator()
        menu.add_command(
            label=f"✕  Eliminar «{categoria.nombre}»",
            foreground=COLORES["error"],
            activeforeground=COLORES["error"],
            command=lambda c=categoria: self._solicitar_eliminar_categoria(c),
        )
        self._menu_contextual = menu
        try:
            menu.tk_popup(evento.x_root, evento.y_root)
        finally:
            menu.grab_release()

    def _abrir_crear_categoria(self) -> None:
        from app.gui.dialogo_categoria import DialogoCategoria

        DialogoCategoria(
            self.winfo_toplevel(),
            gestor=self._gestor,
            al_crear=self._al_crear_categoria,
            tipo_inicial=self._tipo,
        )

    def _al_crear_categoria(self, nueva_cat: Categoria) -> None:
        self._categoria_elegida = nueva_cat.nombre
        self.renderizar()
        self._al_seleccionar(nueva_cat.nombre)
        if self._al_modificar:
            self._al_modificar()

    def _abrir_editar_categoria(self, categoria: Categoria) -> None:
        from app.gui.dialogo_categoria import DialogoCategoria

        nombre_anterior = categoria.nombre

        def _al_guardar_edicion(actualizada: Categoria) -> None:
            if self._categoria_elegida == nombre_anterior:
                self._categoria_elegida = actualizada.nombre
            self.renderizar()
            self._al_seleccionar(self._categoria_elegida)
            if self._al_modificar:
                self._al_modificar()

        DialogoCategoria(
            self.winfo_toplevel(),
            gestor=self._gestor,
            al_crear=_al_guardar_edicion,
            tipo_inicial=categoria.tipo,
            categoria_editar=categoria,
        )

    def _solicitar_eliminar_categoria(self, categoria: Categoria) -> None:
        if categoria.id is None:
            self._mostrar_aviso("No se puede eliminar esta categoría porque aún no tiene ID en base de datos.")
            return

        alternativas = [
            c for c in self._categorias_actuales if c.id is not None and c.id != categoria.id
        ]
        if not alternativas:
            self._mostrar_aviso(
                f"Debe existir al menos una categoría de {self._tipo.lower()}."
            )
            return

        cantidad = self._gestor.contar_movimientos_categoria(categoria.id)

        def _ejecutar_eliminacion(destino_id: Optional[int]) -> None:
            try:
                self._gestor.eliminar_categoria(
                    categoria.id,
                    categoria_destino_id=destino_id,
                )
            except Exception as exc:
                self._mostrar_aviso(str(exc))
                return

            if self._categoria_elegida == categoria.nombre:
                destino = next((c for c in alternativas if c.id == destino_id), alternativas[0])
                self._categoria_elegida = destino.nombre

            self._limpiar_aviso()
            self.renderizar()
            self._al_seleccionar(self._categoria_elegida)
            if self._al_modificar:
                self._al_modificar()

        DialogoEliminarCategoria(
            self.winfo_toplevel(),
            categoria=categoria,
            cantidad_movimientos=cantidad,
            alternativas=alternativas,
            al_confirmar=_ejecutar_eliminacion,
        )
