"""Componente reutilizable de barra de moneda mundial (COP + 4 últimas usadas + lista A-Z),
selector de modo ('Solo esta moneda' vs 'Todo convertido') y banner inteligente de estado de
conexión a internet (muestra datos en caché cuando no hay red o avisa que actualizará
automáticamente apenas se restablezca la conexión)."""

import threading
from typing import Callable, Optional
import customtkinter as ctk

from app.gestor.gestor_financiero import (
    ESTADO_CONEXION_ONLINE,
    ESTADO_OFFLINE_CON_CACHE,
    ESTADO_OFFLINE_SIN_CACHE,
    GestorFinanciero,
)
from app.gui.estilos import COLORES, FUENTE
from app.gui.formato import formatear_valor
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
    2) Modo de filtro: 'Solo esta moneda' vs 'Todo convertido' (convierte todo a la moneda elegida).
    3) Aviso automático de estado de internet: informa si está usando datos en caché por falta de
       conexión o si no hay caché y actualizará automáticamente apenas vuelva el internet."""

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
        self._estaba_sin_conexion = False
        self._verificando_red = False
        self._id_timer_reconexion: Optional[str] = None

        self._construir()
        self._construir_banner_conexion()

        if hasattr(self._gestor, "registrar_listener_conexion"):
            self._gestor.registrar_listener_conexion(self._al_cambiar_estado_conexion_gestor)
        self.bind("<Destroy>", self._al_destruir, add="+")

        # Chequeo inicial asíncrono para informar al usuario si abre la app sin internet
        self.after(150, lambda: self._verificar_conexion_asincrona(notificar_si_reconecta=False))

    def _construir(self):
        fila_controles = ctk.CTkFrame(self, fg_color="transparent")
        fila_controles.pack(fill="x")

        ctk.CTkLabel(
            fila_controles,
            text="Moneda:",
            font=(FUENTE, 13, "bold"),
            text_color=COLORES["texto"],
        ).pack(side="left", padx=(0, 6))

        opciones_combo = self._gestor.obtener_opciones_selector_divisas()
        self._combo_moneda = ctk.CTkComboBox(
            fila_controles,
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
            fila_controles,
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
                fila_controles,
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

    def _construir_banner_conexion(self):
        """Crea el banner de estado de conexión dentro de la tarjeta contenedora para que ocupe
        todo el ancho debajo de la fila del selector de moneda."""
        contenedor_tarjeta = (
            self.master.master
            if (self.master is not None and isinstance(getattr(self.master, "master", None), ctk.CTkFrame))
            else self
        )
        self._marco_aviso_conexion = ctk.CTkFrame(
            contenedor_tarjeta,
            fg_color=COLORES["boton_lateral"],
            corner_radius=8,
            border_width=1,
            border_color=COLORES["acento"],
        )

        fila_aviso = ctk.CTkFrame(self._marco_aviso_conexion, fg_color="transparent")
        fila_aviso.pack(fill="x", padx=12, pady=6)

        self._etiqueta_aviso_conexion = ctk.CTkLabel(
            fila_aviso,
            text="",
            font=(FUENTE, 11, "bold"),
            text_color=COLORES["acento"],
            justify="left",
            anchor="w",
            wraplength=760,
        )
        self._etiqueta_aviso_conexion.pack(side="left", fill="x", expand=True)

        self._boton_reintentar_red = ctk.CTkButton(
            fila_aviso,
            text="🔄 Reintentar",
            width=96,
            height=26,
            corner_radius=6,
            fg_color=COLORES["fondo_tarjeta"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 11, "bold"),
            command=lambda: self._verificar_conexion_asincrona(notificar_si_reconecta=True, forzar_red=True),
        )
        self._boton_reintentar_red.pack(side="right", padx=(8, 0))

    def _al_destruir(self, _evento=None):
        if self._id_timer_reconexion is not None:
            try:
                self.after_cancel(self._id_timer_reconexion)
            except Exception:
                pass
            self._id_timer_reconexion = None
        if hasattr(self._gestor, "desregistrar_listener_conexion"):
            self._gestor.desregistrar_listener_conexion(self._al_cambiar_estado_conexion_gestor)

    def _al_cambiar_estado_conexion_gestor(self):
        try:
            if self.winfo_exists():
                self.after(0, self._actualizar_banner_desde_gestor)
        except Exception:
            pass

    def _verificar_conexion_asincrona(
        self, notificar_si_reconecta: bool = True, forzar_red: bool = False
    ):
        """Consulta en segundo plano si hay internet y reutiliza la caché de sesión sin bloquear."""
        if self._verificando_red or not self.winfo_exists():
            return
        moneda_ref = self._moneda_actual if self._moneda_actual != "COP" else "USD"
        # Si ya estamos online y la tasa ya está en sesión, no lanzar hilos redundantes
        if (
            not forzar_red
            and not self._estaba_sin_conexion
            and hasattr(self._gestor, "tiene_tasa_en_sesion")
            and self._gestor.tiene_tasa_en_sesion(moneda_ref, "COP")
        ):
            self._ocultar_banner_conexion()
            return

        self._verificando_red = True

        def _tarea():
            try:
                hay_red = (
                    self._gestor.hay_conexion_internet(usar_cache_breve=not forzar_red)
                    if hasattr(self._gestor, "hay_conexion_internet")
                    else True
                )
                cot = self._gestor.obtener_tasa_cambio(
                    moneda_ref,
                    "COP",
                    forzar_actualizacion=(forzar_red or self._estaba_sin_conexion),
                )
                if self.winfo_exists():
                    self.after(
                        0,
                        lambda: self._procesar_resultado_conexion(
                            hay_red, moneda_ref, cot, notificar_si_reconecta
                        ),
                    )
            except Exception:
                if self.winfo_exists():
                    self.after(0, self._actualizar_banner_desde_gestor)
            finally:
                self._verificando_red = False

        threading.Thread(target=_tarea, daemon=True).start()

    def _procesar_resultado_conexion(
        self,
        hay_red: bool,
        moneda_ref: str,
        cot,
        notificar_si_reconecta: bool,
    ):
        if not self.winfo_exists():
            return

        if hay_red and cot is not None and "Caché" not in (cot.fuente or ""):
            reconectado_ahora = self._estaba_sin_conexion
            self._estaba_sin_conexion = False
            self._ocultar_banner_conexion()
            if reconectado_ahora and notificar_si_reconecta:
                self._al_cambiar(self.moneda_seleccionada(), self.es_todo_convertido())
            return

        # Modo sin conexión (Offline)
        self._estaba_sin_conexion = True
        if cot is not None:
            tasa_fmt = formatear_valor(cot.precio, "COP")
            texto = (
                f"⚠️ Sin conexión a internet: no es posible actualizar los precios de divisas ni inversiones en tiempo real. "
                f"Mostrando información guardada en caché (1 {moneda_ref} = {tasa_fmt} del {cot.fecha.isoformat()}). "
                f"Tan pronto como te conectes a internet, actualizaremos la información."
            )
            self._mostrar_banner_conexion(texto, con_cache=True)
        else:
            texto = (
                f"📡 No tienes conexión a internet y no hay información en caché para {moneda_ref}. "
                f"Tan pronto como te conectes a internet, actualizaremos la información automáticamente."
            )
            self._mostrar_banner_conexion(texto, con_cache=False)

        self._programar_reintento_automatico()

    def _actualizar_banner_desde_gestor(self):
        if not self.winfo_exists() or not hasattr(self._gestor, "obtener_estado_conexion_bursatil"):
            return
        moneda_ref = self._moneda_actual if self._moneda_actual != "COP" else "USD"
        info = self._gestor.obtener_estado_conexion_bursatil(moneda_ref)
        if info.get("online"):
            reconectado = self._estaba_sin_conexion
            self._estaba_sin_conexion = False
            self._ocultar_banner_conexion()
            if reconectado:
                self._al_cambiar(self.moneda_seleccionada(), self.es_todo_convertido())
            return

        self._estaba_sin_conexion = True
        tiene_cache = bool(info.get("tiene_cache"))
        cot = info.get("cotizacion_cache")
        if tiene_cache and cot is not None:
            tasa_fmt = formatear_valor(cot.precio, "COP")
            texto = (
                f"⚠️ Sin conexión a internet: no es posible actualizar los precios de divisas ni inversiones en tiempo real. "
                f"Mostrando información guardada en caché (1 {moneda_ref} = {tasa_fmt} del {cot.fecha.isoformat()}). "
                f"Tan pronto como te conectes a internet, actualizaremos la información."
            )
            self._mostrar_banner_conexion(texto, con_cache=True)
        else:
            texto = (
                f"📡 No tienes conexión a internet y no hay información en caché disponible. "
                f"Tan pronto como te conectes a internet, actualizaremos la información automáticamente."
            )
            self._mostrar_banner_conexion(texto, con_cache=False)

        self._programar_reintento_automatico()

    def _mostrar_banner_conexion(self, mensaje: str, con_cache: bool):
        color_borde = COLORES["acento"] if con_cache else COLORES["error"]
        self._marco_aviso_conexion.configure(border_color=color_borde)
        self._etiqueta_aviso_conexion.configure(text=mensaje, text_color=color_borde)
        if not self._marco_aviso_conexion.winfo_ismapped():
            self._marco_aviso_conexion.pack(fill="x", padx=14, pady=(0, 8))

    def _ocultar_banner_conexion(self):
        if self._id_timer_reconexion is not None:
            try:
                self.after_cancel(self._id_timer_reconexion)
            except Exception:
                pass
            self._id_timer_reconexion = None
        if self._marco_aviso_conexion.winfo_ismapped():
            self._marco_aviso_conexion.pack_forget()

    def _programar_reintento_automatico(self):
        if self._id_timer_reconexion is not None:
            try:
                self.after_cancel(self._id_timer_reconexion)
            except Exception:
                pass
        if self.winfo_exists():
            self._id_timer_reconexion = self.after(
                4000, lambda: self._verificar_conexion_asincrona(notificar_si_reconecta=True)
            )

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
        self._verificar_conexion_asincrona(notificar_si_reconecta=True)

    def moneda_seleccionada(self) -> str:
        return self._moneda_actual

    def establecer_moneda(self, codigo: str):
        limpio = codigo.strip().upper()
        if limpio in DIVISAS_MUNDIALES:
            self._moneda_actual = limpio
            self._gestor.registrar_moneda_usada(limpio)
            self._refrescar_opciones_combo()
            self._verificar_conexion_asincrona(notificar_si_reconecta=False)

    def es_todo_convertido(self) -> bool:
        return self._var_modo.get() == MODO_TODO_CONVERTIDO
