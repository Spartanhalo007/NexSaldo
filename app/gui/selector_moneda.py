"""Componente reutilizable de barra de moneda mundial (COP + 4 últimas usadas + lista A-Z)
y selector de modo ('Solo esta moneda' vs 'Todo convertido a esta moneda')."""

from typing import Callable, Optional
import customtkinter as ctk

from app.gestor.gestor_financiero import GestorFinanciero
from app.gui.estilos import COLORES, FUENTE
from app.modelo.divisas import (
    DIVISAS_MUNDIALES,
    etiqueta_divisa,
    extraer_codigo_divisa,
)

MODO_SOLO_DIVISA = "Solo esta moneda"
MODO_TODO_CONVERTIDO = "Todo convertido"


class DialogoSelectorDivisa(ctk.CTkToplevel):
    """Pop-up con buscador en vivo, las 5 últimas divisas usadas (empezando por COP)
    y la lista desplazable (scrollable) en orden alfabético de todas las divisas del mundo."""

    def __init__(
        self,
        master,
        gestor: GestorFinanciero,
        moneda_actual: str,
        al_seleccionar: Callable[[str], None],
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self._gestor = gestor
        self._moneda_actual = moneda_actual.strip().upper()
        self._al_seleccionar = al_seleccionar

        self.title("Seleccionar moneda")
        self.geometry("460x560")
        self.resizable(False, False)
        self.configure(fg_color=COLORES["fondo_lateral"])
        self.transient(master)
        self.grab_set()

        self._construir_interfaz()

    def _construir_interfaz(self):
        cuerpo = ctk.CTkFrame(self, fg_color="transparent")
        cuerpo.pack(fill="both", expand=True, padx=18, pady=16)

        ctk.CTkLabel(
            cuerpo,
            text="Seleccionar divisa",
            font=(FUENTE, 18, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w")

        ctk.CTkLabel(
            cuerpo,
            text="COP siempre primero + tus últimas 4 divisas usadas, y todas las divisas del mundo (A-Z):",
            font=(FUENTE, 11),
            text_color=COLORES["texto_secundario"],
            wraplength=420,
            justify="left",
        ).pack(anchor="w", pady=(2, 10))

        self._campo_filtro = ctk.CTkEntry(
            cuerpo,
            placeholder_text="Buscar por código o país (ej: USD, EUR, Peso, Yen, Libra...)",
            fg_color=COLORES["campo_fondo"],
            text_color=COLORES["campo_texto"],
            font=(FUENTE, 13),
            height=36,
            corner_radius=8,
        )
        self._campo_filtro.pack(fill="x", pady=(0, 10))
        self._campo_filtro.bind("<KeyRelease>", lambda _e: self._renderizar_lista())

        self._lista_scroll = ctk.CTkScrollableFrame(
            cuerpo,
            fg_color=COLORES["fondo_tarjeta"],
            corner_radius=10,
            height=390,
        )
        self._lista_scroll.pack(fill="both", expand=True, pady=(0, 10))

        self._renderizar_lista()

    def _renderizar_lista(self):
        for hijo in self._lista_scroll.winfo_children():
            hijo.destroy()

        filtro = self._campo_filtro.get().strip().lower()
        ultimas_5 = self._gestor.obtener_ultimas_5_monedas()

        # 1. Sección superior: Últimas 5 divisas usadas (COP siempre de primera)
        recientes_filtradas = [
            cod for cod in ultimas_5
            if not filtro or filtro in etiqueta_divisa(cod).lower()
        ]
        if recientes_filtradas:
            ctk.CTkLabel(
                self._lista_scroll,
                text="Últimas 5 divisas usadas (COP predeterminada)",
                font=(FUENTE, 11, "bold"),
                text_color=COLORES["acento"],
            ).pack(anchor="w", padx=10, pady=(6, 4))

            for cod in recientes_filtradas:
                self._crear_boton_divisa(cod)

        # 2. Sección inferior: Todas las divisas del mundo en orden alfabético
        codigos_alfabeticos = sorted(DIVISAS_MUNDIALES.keys())
        alfabeticas_filtradas = [
            cod for cod in codigos_alfabeticos
            if not filtro or filtro in etiqueta_divisa(cod).lower()
        ]

        ctk.CTkLabel(
            self._lista_scroll,
            text="Todas las divisas del mundo (Orden alfabético A–Z)",
            font=(FUENTE, 11, "bold"),
            text_color=COLORES["texto_secundario"],
        ).pack(anchor="w", padx=10, pady=(10, 4))

        for cod in alfabeticas_filtradas:
            self._crear_boton_divisa(cod)

    def _crear_boton_divisa(self, codigo: str):
        activa = codigo == self._moneda_actual
        texto = etiqueta_divisa(codigo)
        btn = ctk.CTkButton(
            self._lista_scroll,
            text=texto,
            anchor="w",
            height=34,
            corner_radius=8,
            fg_color=COLORES["acento"] if activa else COLORES["boton_lateral"],
            hover_color=COLORES["acento_hover"] if activa else COLORES["hover_lateral"],
            text_color=COLORES["campo_texto"] if activa else COLORES["texto"],
            font=(FUENTE, 12, "bold" if activa else "normal"),
            command=lambda c=codigo: self._elegir(c),
        )
        btn.pack(fill="x", padx=6, pady=2)

    def _elegir(self, codigo: str):
        self._gestor.registrar_moneda_usada(codigo)
        self._al_seleccionar(codigo)
        self.destroy()


class BarraFiltroMoneda(ctk.CTkFrame):
    """Barra reutilizable para elegir:
    1) Divisa (muestra desplegable con las 5 últimas usadas empezando por COP + botón de lista mundial A-Z).
    2) Modo de filtro: 'Solo esta moneda' vs 'Todo convertido' (convierte todo a la moneda elegida)."""

    def __init__(
        self,
        master,
        gestor: GestorFinanciero,
        al_cambiar: Callable[[str, bool], None],
        moneda_inicial: str = "COP",
        mostrar_modo: bool = True,
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._gestor = gestor
        self._al_cambiar = al_cambiar
        self._moneda_actual = (moneda_inicial or "COP").strip().upper()
        self._mostrar_modo = mostrar_modo

        self._construir()

    def _construir(self):
        ctk.CTkLabel(
            self,
            text="Moneda:",
            font=(FUENTE, 13, "bold"),
            text_color=COLORES["texto"],
        ).pack(side="left", padx=(0, 6))

        opciones_combo = self._gestor.obtener_opciones_selector_divisas()
        self._combo_moneda = ctk.CTkComboBox(
            self,
            values=opciones_combo,
            width=215,
            height=34,
            corner_radius=8,
            fg_color=COLORES["campo_fondo"],
            text_color=COLORES["campo_texto"],
            button_color=COLORES["acento"],
            button_hover_color=COLORES["acento_hover"],
            dropdown_fg_color=COLORES["fondo_lateral"],
            dropdown_text_color=COLORES["texto"],
            dropdown_hover_color=COLORES["fondo_tarjeta"],
            font=(FUENTE, 12, "bold"),
            dropdown_font=(FUENTE, 12),
            command=self._al_seleccionar_combo,
        )
        self._combo_moneda.set(etiqueta_divisa(self._moneda_actual))
        self._combo_moneda.pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            self,
            text="🌍 Todas (A-Z)",
            width=105,
            height=34,
            corner_radius=8,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 12, "bold"),
            command=self._abrir_popup_todas,
        ).pack(side="left", padx=(0, 10))

        self._var_modo = ctk.StringVar(value=MODO_SOLO_DIVISA)
        if self._mostrar_modo:
            self._selector_modo = ctk.CTkSegmentedButton(
                self,
                values=[MODO_SOLO_DIVISA, MODO_TODO_CONVERTIDO],
                variable=self._var_modo,
                selected_color=COLORES["acento"],
                selected_hover_color=COLORES["acento_hover"],
                unselected_color=COLORES["boton_lateral"],
                unselected_hover_color=COLORES["hover_lateral"],
                text_color=COLORES["texto"],
                font=(FUENTE, 12, "bold"),
                height=34,
                command=lambda _v: self._notificar_cambio(),
            )
            self._selector_modo.pack(side="left")

    def _refrescar_opciones_combo(self):
        opciones = self._gestor.obtener_opciones_selector_divisas()
        self._combo_moneda.configure(values=opciones)
        self._combo_moneda.set(etiqueta_divisa(self._moneda_actual))

    def _al_seleccionar_combo(self, opcion_texto: str):
        codigo = extraer_codigo_divisa(opcion_texto)
        self._moneda_actual = codigo
        self._gestor.registrar_moneda_usada(codigo)
        self._refrescar_opciones_combo()
        self._notificar_cambio()

    def _abrir_popup_todas(self):
        DialogoSelectorDivisa(
            self,
            gestor=self._gestor,
            moneda_actual=self._moneda_actual,
            al_seleccionar=self._al_elegir_desde_popup,
        )

    def _al_elegir_desde_popup(self, codigo: str):
        self._moneda_actual = codigo
        self._refrescar_opciones_combo()
        self._notificar_cambio()

    def _notificar_cambio(self):
        self._al_cambiar(self.moneda_seleccionada(), self.es_todo_convertido())

    def moneda_seleccionada(self) -> str:
        return self._moneda_actual

    def establecer_moneda(self, codigo: str):
        limpio = codigo.strip().upper()
        if limpio in DIVISAS_MUNDIALES:
            self._moneda_actual = limpio
            self._gestor.registrar_moneda_usada(limpio)
            self._refrescar_opciones_combo()

    def es_todo_convertido(self) -> bool:
        return self._var_modo.get() == MODO_TODO_CONVERTIDO
