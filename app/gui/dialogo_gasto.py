"""Diálogo/Formulario completo para Añadir Gasto en NexSaldo con consulta de tasa en hilo de fondo
(no bloquea la interfaz), soporte de todas las divisas del mundo, aviso claro de modo sin internet
(con o sin datos en caché) y reconexión automática."""

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import os
from pathlib import Path
import shutil
import threading
from tkinter import filedialog, messagebox
from typing import Callable, Dict, List, Optional
import customtkinter as ctk
from PIL import Image

from app.gestor.gestor_financiero import ErrorValidacion, GestorFinanciero
from app.gui.calculadora import Calculadora
from app.gui.calendario import SelectorCalendario
from app.gui.campo_moneda import CampoMoneda, formatear_dinero
from app.gui.dialogo_categoria import DialogoCategoria
from app.gui.dialogo_etiqueta import DialogoEtiquetas
from app.gui.estilos import COLORES, FUENTE
from app.gui.formato import formatear_valor
from app.gui.iconos import GRIS, icono_ctk
from app.gui.selector_moneda import DialogoSelectorDivisa
from app.modelo.categoria import Categoria
from app.modelo.cotizacion import Cotizacion
from app.modelo.cuenta import Cuenta
from app.modelo.divisas import (
    etiqueta_divisa,
    extraer_codigo_divisa,
    obtener_prefijo_divisa,
)
from app.modelo.movimiento_financiero import MovimientoFinanciero

RUTA_ADJUNTOS = Path(__file__).resolve().parents[2] / "adjuntos"
MAXIMO_ADJUNTO_BYTES = 2 * 1024 * 1024


def _decimal_a_texto_moneda(valor: Decimal) -> str:
    cadena = f"{valor:.2f}"
    entero, decimal = cadena.split(".")
    if decimal == "00":
        return formatear_dinero(entero)
    return formatear_dinero(f"{entero},{decimal}")


class DialogoGasto(ctk.CTkToplevel):
    """Formulario para añadir un gasto con monto, selector mundial de divisa (COP por defecto),
    conversión bidireccional automática Divisa <-> COP en segundo plano y detección de modo offline."""

    def __init__(
        self,
        master,
        gestor: GestorFinanciero,
        al_guardar: Callable[[MovimientoFinanciero], None],
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self._gestor = gestor
        self._al_guardar = al_guardar

        self._moneda_elegida = "COP"
        self._cotizacion_trm: Optional[Cotizacion] = None
        self._sincronizando_conversion = False
        self._id_consulta_tasa = 0
        self._id_timer_reconexion: Optional[str] = None
        self._cuenta_elegida_id: Optional[int] = None
        self._mapa_cuentas: Dict[str, Cuenta] = {}
        self._categoria_elegida: str = "Alimentación"
        self._fecha_elegida: date = date.today()
        self._modo_fecha: str = "HOY"
        self._etiquetas_elegidas: List[str] = []
        self._ruta_imagen: Optional[str] = None

        self.title("Añadir gasto")
        self.geometry("690x840")
        self.resizable(False, True)
        self.configure(fg_color=COLORES["fondo_lateral"])
        self.transient(master)
        self.grab_set()
        self.bind("<Destroy>", self._al_destruir_dialogo, add="+")

        self._construir_interfaz()

    def _al_destruir_dialogo(self, _evento=None):
        if self._id_timer_reconexion is not None:
            try:
                self.after_cancel(self._id_timer_reconexion)
            except Exception:
                pass
            self._id_timer_reconexion = None

    def _construir_interfaz(self):
        cuerpo = ctk.CTkScrollableFrame(
            self, fg_color="transparent", width=650, height=790
        )
        cuerpo.pack(fill="both", expand=True, padx=16, pady=14)

        ctk.CTkLabel(
            cuerpo,
            text="Añadir gasto",
            font=(FUENTE, 22, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w", pady=(0, 10))

        # ==================================================================
        # 1. CANTIDAD GASTADA + DIVISA MUNDIAL (COP default) + CALCULADORA
        # ==================================================================
        marco_monto = ctk.CTkFrame(
            cuerpo, fg_color=COLORES["fondo_tarjeta"], corner_radius=12
        )
        marco_monto.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            marco_monto,
            text="Cantidad gastada y divisa (COP + 4 últimas usadas o cualquier divisa del mundo)",
            font=(FUENTE, 13, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w", padx=16, pady=(12, 6))

        fila_monto_calc = ctk.CTkFrame(marco_monto, fg_color="transparent")
        fila_monto_calc.pack(fill="x", padx=16, pady=(0, 14))

        col_izquierda = ctk.CTkFrame(fila_monto_calc, fg_color="transparent")
        col_izquierda.pack(side="left", fill="both", expand=True, padx=(0, 12))

        fila_input_divisa = ctk.CTkFrame(col_izquierda, fg_color="transparent")
        fila_input_divisa.pack(fill="x", pady=(0, 8))

        self._etiqueta_campo_principal = ctk.CTkLabel(
            fila_input_divisa,
            text="COP $",
            font=(FUENTE, 13, "bold"),
            text_color=COLORES["acento"],
            width=58,
        )
        self._etiqueta_campo_principal.pack(side="left", padx=(0, 4))

        self._campo_valor = CampoMoneda(
            fila_input_divisa, width=145, height=40, corner_radius=8
        )
        self._campo_valor.pack(side="left", padx=(0, 6))
        self._campo_valor.bind("<KeyRelease>", self._al_escribir_campo_principal, add="+")
        self._campo_valor.bind("<FocusIn>", lambda _e: self._apuntar_calculadora(self._campo_valor), add="+")

        opciones_divisa = self._gestor.obtener_opciones_selector_divisas()
        self._combo_divisa = ctk.CTkComboBox(
            fila_input_divisa,
            values=opciones_divisa,
            width=145,
            height=40,
            corner_radius=8,
            state="readonly",
            fg_color=COLORES["campo_fondo"],
            text_color=COLORES["campo_texto"],
            button_color=COLORES["acento"],
            button_hover_color=COLORES["acento_hover"],
            dropdown_fg_color=COLORES["fondo_lateral"],
            dropdown_text_color=COLORES["texto"],
            dropdown_hover_color=COLORES["fondo_tarjeta"],
            font=(FUENTE, 12, "bold"),
            command=self._al_cambiar_combo_divisa,
        )
        self._combo_divisa.set(etiqueta_divisa("COP"))
        self._combo_divisa.pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            fila_input_divisa,
            text="🌍",
            width=38,
            height=40,
            corner_radius=8,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 14),
            command=self._abrir_selector_todas_divisas,
        ).pack(side="left")

        # --- Panel de conversión bidireccional en tiempo real ---
        self._marco_conversion_extranjera = ctk.CTkFrame(
            col_izquierda, fg_color=COLORES["boton_lateral"], corner_radius=10
        )

        self._etiqueta_instruccion_conv = ctk.CTkLabel(
            self._marco_conversion_extranjera,
            text="Equivalente en Pesos Colombianos (escribe en USD o en COP):",
            font=(FUENTE, 11, "bold"),
            text_color=COLORES["texto"],
        )
        self._etiqueta_instruccion_conv.pack(anchor="w", padx=10, pady=(8, 4))

        fila_equiv_cop = ctk.CTkFrame(self._marco_conversion_extranjera, fg_color="transparent")
        fila_equiv_cop.pack(fill="x", padx=10, pady=(0, 6))

        ctk.CTkLabel(
            fila_equiv_cop,
            text="COP $",
            font=(FUENTE, 13, "bold"),
            text_color=COLORES["acento"],
            width=58,
        ).pack(side="left", padx=(0, 4))

        self._campo_valor_cop_equiv = CampoMoneda(
            fila_equiv_cop, width=180, height=36, corner_radius=8
        )
        self._campo_valor_cop_equiv.pack(side="left", padx=(0, 8))
        self._campo_valor_cop_equiv.bind(
            "<KeyRelease>", self._al_escribir_campo_cop_equivalente, add="+"
        )
        self._campo_valor_cop_equiv.bind(
            "<FocusIn>",
            lambda _e: self._apuntar_calculadora(self._campo_valor_cop_equiv),
            add="+",
        )

        ctk.CTkButton(
            fila_equiv_cop,
            text="↻ Tasa",
            width=72,
            height=32,
            corner_radius=8,
            fg_color=COLORES["fondo_tarjeta"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 11, "bold"),
            command=lambda: self._cargar_tasa_yahoo(forzar=True),
        ).pack(side="left")

        self._etiqueta_tasa_yahoo = ctk.CTkLabel(
            self._marco_conversion_extranjera,
            text="Consultando cotización en tiempo real en Yahoo Finance...",
            font=(FUENTE, 11),
            text_color=COLORES["texto_secundario"],
            wraplength=330,
            justify="left",
        )
        self._etiqueta_tasa_yahoo.pack(anchor="w", padx=10, pady=(0, 8))

        # --- Selección de Cuenta ---
        self._contenedor_selector_cuenta = ctk.CTkFrame(col_izquierda, fg_color="transparent")
        self._contenedor_selector_cuenta.pack(fill="x")

        ctk.CTkLabel(
            self._contenedor_selector_cuenta,
            text="Cuenta de origen del gasto:",
            font=(FUENTE, 13, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w", pady=(4, 4))

        self._var_cuenta = ctk.StringVar(value="Sin cuenta asociada")
        self._combo_cuenta = ctk.CTkOptionMenu(
            self._contenedor_selector_cuenta,
            values=["Sin cuenta asociada"],
            variable=self._var_cuenta,
            fg_color=COLORES["boton_lateral"],
            button_color=COLORES["acento"],
            button_hover_color=COLORES["acento_hover"],
            text_color=COLORES["texto"],
            font=(FUENTE, 12, "bold"),
            width=310,
            height=36,
            command=self._al_seleccionar_cuenta,
        )
        self._combo_cuenta.pack(anchor="w")

        self._etiqueta_info_cuenta = ctk.CTkLabel(
            self._contenedor_selector_cuenta,
            text="Moneda por defecto: Peso colombiano (COP)",
            font=(FUENTE, 11),
            text_color=COLORES["texto_secundario"],
        )
        self._etiqueta_info_cuenta.pack(anchor="w", pady=(4, 0))

        # Al lado derecho: Calculadora
        col_calculadora = ctk.CTkFrame(fila_monto_calc, fg_color="transparent")
        col_calculadora.pack(side="right")

        self._calculadora = Calculadora(col_calculadora, self._campo_valor)
        self._calculadora.pack()

        self._cargar_cuentas_disponibles()

        # ==================================================================
        # 2. CATEGORÍAS CIRCULARES + BOTÓN GRIS "+" ("Más") PARA CREAR
        # ==================================================================
        marco_categorias = ctk.CTkFrame(
            cuerpo, fg_color=COLORES["fondo_tarjeta"], corner_radius=12
        )
        marco_categorias.pack(fill="x", pady=(0, 12))

        fila_titulo_cat = ctk.CTkFrame(marco_categorias, fg_color="transparent")
        fila_titulo_cat.pack(fill="x", padx=16, pady=(12, 6))

        ctk.CTkLabel(
            fila_titulo_cat,
            text="Categorías",
            font=(FUENTE, 14, "bold"),
            text_color=COLORES["texto"],
        ).pack(side="left")

        self._etiqueta_cat_seleccionada = ctk.CTkLabel(
            fila_titulo_cat,
            text=f"Seleccionada: {self._categoria_elegida}",
            font=(FUENTE, 12, "bold"),
            text_color=COLORES["acento"],
        )
        self._etiqueta_cat_seleccionada.pack(side="right")

        self._rejilla_categorias = ctk.CTkFrame(
            marco_categorias, fg_color="transparent"
        )
        self._rejilla_categorias.pack(fill="x", padx=12, pady=(2, 14))

        self._renderizar_categorias()

        # ==================================================================
        # 3. FECHA: HOY, AYER, ÚLTIMO Y BOTÓN DE CALENDARIO
        # ==================================================================
        marco_fecha = ctk.CTkFrame(
            cuerpo, fg_color=COLORES["fondo_tarjeta"], corner_radius=12
        )
        marco_fecha.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            marco_fecha,
            text="Fecha del gasto",
            font=(FUENTE, 13, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w", padx=16, pady=(12, 6))

        fila_botones_fecha = ctk.CTkFrame(marco_fecha, fg_color="transparent")
        fila_botones_fecha.pack(fill="x", padx=16, pady=(0, 12))

        self._btn_hoy = ctk.CTkButton(
            fila_botones_fecha,
            text=f"Hoy\n({date.today().strftime('%d/%m')})",
            width=120,
            height=44,
            corner_radius=8,
            font=(FUENTE, 12, "bold"),
            command=self._seleccionar_fecha_hoy,
        )
        self._btn_hoy.pack(side="left", padx=(0, 8))

        ayer = date.today() - timedelta(days=1)
        self._btn_ayer = ctk.CTkButton(
            fila_botones_fecha,
            text=f"Ayer\n({ayer.strftime('%d/%m')})",
            width=120,
            height=44,
            corner_radius=8,
            font=(FUENTE, 12, "bold"),
            command=self._seleccionar_fecha_ayer,
        )
        self._btn_ayer.pack(side="left", padx=(0, 8))

        ultima_fecha = self._gestor.obtener_ultima_fecha_gasto()
        texto_ultimo = (
            f"Último\n({ultima_fecha.strftime('%d/%m/%Y')})"
            if ultima_fecha
            else "Último\n(Sin previos)"
        )
        self._btn_ultimo = ctk.CTkButton(
            fila_botones_fecha,
            text=texto_ultimo,
            width=145,
            height=44,
            corner_radius=8,
            font=(FUENTE, 12, "bold"),
            command=self._seleccionar_fecha_ultimo,
        )
        self._btn_ultimo.pack(side="left", padx=(0, 8))

        self._btn_calendario = ctk.CTkButton(
            fila_botones_fecha,
            text="Calendario...",
            width=165,
            height=44,
            corner_radius=8,
            font=(FUENTE, 12, "bold"),
            command=self._abrir_calendario_fecha,
        )
        self._btn_calendario.pack(side="left")

        self._actualizar_botones_fecha()

        # ==================================================================
        # 4. ETIQUETAS 100% CUSTOMIZABLES ("Añadir etiquetas")
        # ==================================================================
        marco_etiquetas = ctk.CTkFrame(
            cuerpo, fg_color=COLORES["fondo_tarjeta"], corner_radius=12
        )
        marco_etiquetas.pack(fill="x", pady=(0, 12))

        fila_cab_etiquetas = ctk.CTkFrame(marco_etiquetas, fg_color="transparent")
        fila_cab_etiquetas.pack(fill="x", padx=16, pady=(10, 6))

        ctk.CTkLabel(
            fila_cab_etiquetas,
            text="Etiquetas",
            font=(FUENTE, 13, "bold"),
            text_color=COLORES["texto"],
        ).pack(side="left")

        ctk.CTkButton(
            fila_cab_etiquetas,
            text="Añadir etiquetas",
            width=145,
            height=32,
            corner_radius=8,
            fg_color=COLORES["acento"],
            hover_color=COLORES["acento_hover"],
            text_color=COLORES["campo_texto"],
            font=(FUENTE, 12, "bold"),
            command=self._abrir_dialogo_etiquetas,
        ).pack(side="right")

        self._contenedor_chips_etiquetas = ctk.CTkFrame(
            marco_etiquetas, fg_color="transparent"
        )
        self._contenedor_chips_etiquetas.pack(fill="x", padx=16, pady=(0, 12))
        self._renderizar_chips_etiquetas()

        # ==================================================================
        # 5. COMENTARIO (DESCRIPCIÓN) Y SUBIR FOTO
        # ==================================================================
        marco_detalles = ctk.CTkFrame(
            cuerpo, fg_color=COLORES["fondo_tarjeta"], corner_radius=12
        )
        marco_detalles.pack(fill="x", pady=(0, 16))

        ctk.CTkLabel(
            marco_detalles,
            text="Comentario / Descripción",
            font=(FUENTE, 13, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w", padx=16, pady=(12, 4))

        self._campo_comentario = ctk.CTkEntry(
            marco_detalles,
            placeholder_text="Añade una nota o descripción del gasto (opcional, máx. 200 caracteres)...",
            fg_color=COLORES["campo_fondo"],
            text_color=COLORES["campo_texto"],
            font=(FUENTE, 13),
            height=38,
            corner_radius=8,
        )
        self._campo_comentario.pack(fill="x", padx=16, pady=(0, 12))

        fila_foto = ctk.CTkFrame(marco_detalles, fg_color="transparent")
        fila_foto.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkButton(
            fila_foto,
            text="Subir foto / comprobante",
            image=icono_ctk("camara", color="#FFFFFF", tamano=20),
            compound="left",
            width=210,
            height=36,
            corner_radius=8,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 12, "bold"),
            command=self._subir_imagen,
        ).pack(side="left", padx=(0, 12))

        self._etiqueta_imagen = ctk.CTkLabel(
            fila_foto,
            text="Ninguna foto seleccionada",
            font=(FUENTE, 12),
            text_color=COLORES["texto_secundario"],
        )
        self._etiqueta_imagen.pack(side="left")

        # ==================================================================
        # 6. BOTÓN AMARILLO PARA GUARDAR EL GASTO
        # ==================================================================
        fila_guardar = ctk.CTkFrame(cuerpo, fg_color="transparent")
        fila_guardar.pack(fill="x", pady=(0, 8))

        ctk.CTkButton(
            fila_guardar,
            text="Cancelar",
            width=130,
            height=42,
            corner_radius=8,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 13),
            command=self.destroy,
        ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            fila_guardar,
            text="Añadir gasto",
            width=200,
            height=42,
            corner_radius=8,
            fg_color=COLORES["acento"],
            hover_color=COLORES["acento_hover"],
            text_color=COLORES["campo_texto"],
            font=(FUENTE, 15, "bold"),
            command=self._guardar_gasto,
        ).pack(side="right")

    # ------------------------------------------------------------------
    # Lógica de Divisa Mundial, Conversión Bidireccional Asíncrona <-> COP y Cuentas
    # ------------------------------------------------------------------
    def _apuntar_calculadora(self, campo_objetivo: CampoMoneda):
        if hasattr(self, "_calculadora") and hasattr(self._calculadora, "_campo_destino"):
            self._calculadora._campo_destino = campo_objetivo

    def _abrir_selector_todas_divisas(self):
        DialogoSelectorDivisa(
            self,
            gestor=self._gestor,
            moneda_actual=self._moneda_elegida,
            al_seleccionar=self._aplicar_cambio_divisa,
        )

    def _al_cambiar_combo_divisa(self, opcion_texto: str):
        codigo = extraer_codigo_divisa(opcion_texto)
        self._aplicar_cambio_divisa(codigo)

    def _aplicar_cambio_divisa(self, nueva_moneda: str):
        self._moneda_elegida = nueva_moneda.strip().upper()
        self._gestor.registrar_moneda_usada(self._moneda_elegida)
        opciones = self._gestor.obtener_opciones_selector_divisas()
        self._combo_divisa.configure(values=opciones)
        self._combo_divisa.set(etiqueta_divisa(self._moneda_elegida))

        prefijo = obtener_prefijo_divisa(self._moneda_elegida)
        self._etiqueta_campo_principal.configure(text=f"{self._moneda_elegida} {prefijo}")

        if self._moneda_elegida != "COP":
            self._etiqueta_instruccion_conv.configure(
                text=f"Equivalente en Pesos Colombianos (escribe en {self._moneda_elegida} o en COP):"
            )
            self._marco_conversion_extranjera.pack(
                fill="x", pady=(0, 8), before=self._contenedor_selector_cuenta
            )
            self._cargar_tasa_yahoo(forzar=False)
            self._etiqueta_info_cuenta.configure(
                text=f"Puedes digitar en {self._moneda_elegida} o en COP; el otro campo se convierte automáticamente."
            )
        else:
            if self._id_timer_reconexion is not None:
                try:
                    self.after_cancel(self._id_timer_reconexion)
                except Exception:
                    pass
                self._id_timer_reconexion = None
            self._marco_conversion_extranjera.pack_forget()
            self._apuntar_calculadora(self._campo_valor)
            self._etiqueta_info_cuenta.configure(
                text="Moneda por defecto: Peso colombiano (COP)"
            )
        self._cargar_cuentas_disponibles()

    def _cargar_tasa_yahoo(self, forzar: bool = False):
        """Consulta la tasa en un hilo secundario para que la ventana jamás deje de responder."""
        if self._moneda_elegida == "COP":
            return
        if self._id_timer_reconexion is not None:
            try:
                self.after_cancel(self._id_timer_reconexion)
            except Exception:
                pass
            self._id_timer_reconexion = None

        self._id_consulta_tasa += 1
        id_actual = self._id_consulta_tasa
        moneda_consulta = self._moneda_elegida
        self._cotizacion_trm = None
        self._etiqueta_tasa_yahoo.configure(
            text=f"Consultando tasa {moneda_consulta} -> COP en Yahoo Finance...",
            text_color=COLORES["texto_secundario"],
        )

        def _tarea_fondo():
            hay_red = (
                self._gestor.hay_conexion_internet(usar_cache_breve=False)
                if hasattr(self._gestor, "hay_conexion_internet")
                else True
            )
            cot = self._gestor.obtener_tasa_cambio(
                moneda_consulta, "COP", forzar_actualizacion=(forzar or hay_red)
            )
            try:
                if self.winfo_exists():
                    self.after(
                        0,
                        lambda: self._al_recibir_tasa_yahoo(
                            id_actual, moneda_consulta, cot, hay_red
                        ),
                    )
            except Exception:
                pass

        threading.Thread(target=_tarea_fondo, daemon=True).start()

    def _al_recibir_tasa_yahoo(
        self,
        id_consulta: int,
        moneda: str,
        cot: Optional[Cotizacion],
        hay_red: bool = True,
    ):
        if id_consulta != self._id_consulta_tasa or not self.winfo_exists():
            return
        self._cotizacion_trm = cot
        es_cache = cot is not None and ("Caché" in (cot.fuente or "") or not hay_red)

        if cot is not None and not es_cache:
            tasa_fmt = formatear_valor(cot.precio, "COP")
            self._etiqueta_tasa_yahoo.configure(
                text=f"1 {moneda} = {tasa_fmt}  •  Yahoo Finance en tiempo real ({cot.fecha.isoformat()})",
                text_color=COLORES["exito"],
            )
            self._al_escribir_campo_principal()
        elif cot is not None and es_cache:
            tasa_fmt = formatear_valor(cot.precio, "COP")
            self._etiqueta_tasa_yahoo.configure(
                text=(
                    f"⚠️ Sin conexión a internet: no es posible actualizar el precio en vivo. "
                    f"Mostrando tasa en caché: 1 {moneda} = {tasa_fmt} ({cot.fecha.isoformat()}). "
                    f"Tan pronto te conectes, actualizaremos la información."
                ),
                text_color=COLORES["acento"],
            )
            self._al_escribir_campo_principal()
            self._programar_reintento_reconexion()
        elif not hay_red:
            self._etiqueta_tasa_yahoo.configure(
                text=(
                    f"📡 No tienes conexión a internet y no hay tasa en caché para {moneda}. "
                    f"Tan pronto como te conectes a internet, actualizaremos la información automáticamente."
                ),
                text_color=COLORES["error"],
            )
            self._programar_reintento_reconexion()
        else:
            self._etiqueta_tasa_yahoo.configure(
                text=f"Sin cotización disponible para {moneda} en Yahoo Finance.",
                text_color=COLORES["error"],
            )

    def _programar_reintento_reconexion(self):
        if self._id_timer_reconexion is not None:
            try:
                self.after_cancel(self._id_timer_reconexion)
            except Exception:
                pass
        if self.winfo_exists() and self._moneda_elegida != "COP":
            self._id_timer_reconexion = self.after(
                4000, self._chequear_reconexion_fondo
            )

    def _chequear_reconexion_fondo(self):
        if not self.winfo_exists() or self._moneda_elegida == "COP":
            return

        def _probar():
            conectado = (
                self._gestor.hay_conexion_internet(usar_cache_breve=False)
                if hasattr(self._gestor, "hay_conexion_internet")
                else False
            )
            if self.winfo_exists():
                if conectado:
                    self.after(0, lambda: self._cargar_tasa_yahoo(forzar=True))
                else:
                    self.after(0, self._programar_reintento_reconexion)

        threading.Thread(target=_probar, daemon=True).start()

    def _al_escribir_campo_principal(self, _evento=None):
        if self._moneda_elegida == "COP" or self._sincronizando_conversion:
            return
        if self._cotizacion_trm is None:
            return

        texto_ext = self._campo_valor.obtener_valor().strip()
        self._sincronizando_conversion = True
        try:
            if not texto_ext:
                self._campo_valor_cop_equiv.delete(0, "end")
                return
            monto_ext = Decimal(texto_ext.replace(",", "."))
            if monto_ext <= Decimal("0"):
                self._campo_valor_cop_equiv.delete(0, "end")
                return
            monto_cop = self._gestor.convertir_entre_monedas(
                monto_ext,
                self._moneda_elegida,
                "COP",
                tasa=self._cotizacion_trm.precio,
            )
            self._campo_valor_cop_equiv.delete(0, "end")
            self._campo_valor_cop_equiv.insert(0, _decimal_a_texto_moneda(monto_cop))
        except (InvalidOperation, ErrorValidacion):
            pass
        finally:
            self._sincronizando_conversion = False

    def _al_escribir_campo_cop_equivalente(self, _evento=None):
        if self._moneda_elegida == "COP" or self._sincronizando_conversion:
            return
        if self._cotizacion_trm is None or self._cotizacion_trm.precio <= Decimal("0"):
            return

        texto_cop = self._campo_valor_cop_equiv.obtener_valor().strip()
        self._sincronizando_conversion = True
        try:
            if not texto_cop:
                self._campo_valor.delete(0, "end")
                return
            monto_cop = Decimal(texto_cop.replace(",", "."))
            if monto_cop <= Decimal("0"):
                self._campo_valor.delete(0, "end")
                return
            tasa_inversa = Decimal("1") / self._cotizacion_trm.precio
            monto_ext = self._gestor.convertir_entre_monedas(
                monto_cop, "COP", self._moneda_elegida, tasa=tasa_inversa
            )
            self._campo_valor.delete(0, "end")
            self._campo_valor.insert(0, _decimal_a_texto_moneda(monto_ext))
        except (InvalidOperation, ErrorValidacion):
            pass
        finally:
            self._sincronizando_conversion = False

    def _cargar_cuentas_disponibles(self):
        cuentas_con_saldo = self._gestor.obtener_cuentas()
        self._mapa_cuentas.clear()
        opciones = ["Sin cuenta asociada"]

        for cuenta, saldo in cuentas_con_saldo:
            etiqueta = f"{cuenta.nombre} [{cuenta.moneda}] ({formatear_valor(saldo, cuenta.moneda)})"
            self._mapa_cuentas[etiqueta] = cuenta
            if cuenta.moneda == self._moneda_elegida:
                opciones.insert(1, etiqueta)
            else:
                opciones.append(etiqueta)

        self._combo_cuenta.configure(values=opciones)
        if len(opciones) > 1:
            primera = opciones[1]
            self._var_cuenta.set(primera)
            self._cuenta_elegida_id = self._mapa_cuentas[primera].id
        else:
            self._var_cuenta.set("Sin cuenta asociada")
            self._cuenta_elegida_id = None

    def _al_seleccionar_cuenta(self, seleccion: str):
        cuenta = self._mapa_cuentas.get(seleccion)
        self._cuenta_elegida_id = cuenta.id if cuenta else None

    # ------------------------------------------------------------------
    # Lógica de Categorías Circulares + Botón Gris "Más"
    # ------------------------------------------------------------------
    def _renderizar_categorias(self):
        for hijo in self._rejilla_categorias.winfo_children():
            hijo.destroy()

        categorias = self._gestor.obtener_categorias_detalladas("GASTO")
        nombres_disponibles = [c.nombre for c in categorias]
        if self._categoria_elegida not in nombres_disponibles and nombres_disponibles:
            self._categoria_elegida = nombres_disponibles[0]

        columnas = 5
        for c in range(columnas):
            self._rejilla_categorias.grid_columnconfigure(c, weight=1)

        for idx, cat in enumerate(categorias):
            fila = idx // columnas
            col = idx % columnas
            activa = cat.nombre == self._categoria_elegido_actual()

            celda = ctk.CTkFrame(self._rejilla_categorias, fg_color="transparent")
            celda.grid(row=fila, column=col, padx=6, pady=8)

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
                command=lambda nombre_c=cat.nombre: self._seleccionar_categoria(nombre_c),
            )
            btn.pack()

            subtexto = cat.nombre
            if cat.gasto_programado:
                subtexto = f"{cat.nombre} ⏱"

            ctk.CTkLabel(
                celda,
                text=subtexto,
                font=(FUENTE, 11, "bold" if activa else "normal"),
                text_color=COLORES["acento"] if activa else COLORES["texto"],
            ).pack(pady=(3, 0))

        idx_mas = len(categorias)
        fila_mas = idx_mas // columnas
        col_mas = idx_mas % columnas

        celda_mas = ctk.CTkFrame(self._rejilla_categorias, fg_color="transparent")
        celda_mas.grid(row=fila_mas, column=col_mas, padx=6, pady=8)

        btn_mas = ctk.CTkButton(
            celda_mas,
            text="",
            width=54,
            height=54,
            corner_radius=27,
            fg_color=GRIS,
            hover_color="#6E737B",
            image=icono_ctk("mas", color="#FFFFFF", tamano=26),
            command=self._abrir_crear_categoria,
        )
        btn_mas.pack()

        ctk.CTkLabel(
            celda_mas,
            text="Más",
            font=(FUENTE, 11, "bold"),
            text_color=COLORES["texto_secundario"],
        ).pack(pady=(3, 0))

        self._etiqueta_cat_seleccionada.configure(
            text=f"Seleccionada: {self._categoria_elegida}"
        )

    def _categoria_elegido_actual(self) -> str:
        return self._categoria_elegida

    def _seleccionar_categoria(self, nombre_categoria: str):
        self._categoria_elegida = nombre_categoria
        self._renderizar_categorias()

    def _abrir_crear_categoria(self):
        DialogoCategoria(
            self,
            gestor=self._gestor,
            al_crear=self._al_crear_nueva_categoria,
            tipo_inicial="GASTO",
        )

    def _al_crear_nueva_categoria(self, nueva_cat: Categoria):
        self._categoria_elegida = nueva_cat.nombre
        self._renderizar_categorias()

    # ------------------------------------------------------------------
    # Lógica de Fecha (Hoy, Ayer, Último, Calendario)
    # ------------------------------------------------------------------
    def _seleccionar_fecha_hoy(self):
        self._fecha_elegida = date.today()
        self._modo_fecha = "HOY"
        self._actualizar_botones_fecha()

    def _seleccionar_fecha_ayer(self):
        self._fecha_elegida = date.today() - timedelta(days=1)
        self._modo_fecha = "AYER"
        self._actualizar_botones_fecha()

    def _seleccionar_fecha_ultimo(self):
        ultima = self._gestor.obtener_ultima_fecha_gasto()
        if ultima is None:
            messagebox.showinfo(
                "Sin registros previos",
                "Aún no hay una fecha de último gasto guardada; se usará la fecha de hoy.",
                parent=self,
            )
            self._seleccionar_fecha_hoy()
            return
        self._fecha_elegida = ultima
        self._modo_fecha = "ULTIMO"
        self._actualizar_botones_fecha()

    def _abrir_calendario_fecha(self):
        SelectorCalendario(
            self,
            al_elegir=self._al_elegir_fecha_calendario,
            fecha_inicial=self._fecha_elegida,
        )

    def _al_elegir_fecha_calendario(self, fecha_seleccionada: date):
        self._fecha_elegida = fecha_seleccionada
        self._modo_fecha = "CALENDARIO"
        self._actualizar_botones_fecha()

    def _actualizar_botones_fecha(self):
        pares = [
            ("HOY", self._btn_hoy),
            ("AYER", self._btn_ayer),
            ("ULTIMO", self._btn_ultimo),
            ("CALENDARIO", self._btn_calendario),
        ]
        for modo, boton in pares:
            activo = self._modo_fecha == modo
            boton.configure(
                fg_color=COLORES["acento"] if activo else COLORES["boton_lateral"],
                hover_color=COLORES["acento_hover"] if activo else COLORES["hover_lateral"],
                text_color=COLORES["campo_texto"] if activo else COLORES["texto"],
            )
        if self._modo_fecha == "CALENDARIO":
            self._btn_calendario.configure(
                text=f"Calendario\n({self._fecha_elegida.isoformat()})"
            )
        else:
            self._btn_calendario.configure(text="Calendario...")

    # ------------------------------------------------------------------
    # Lógica de Etiquetas y Foto
    # ------------------------------------------------------------------
    def _abrir_dialogo_etiquetas(self):
        DialogoEtiquetas(
            self,
            gestor=self._gestor,
            etiquetas_seleccionadas=self._etiquetas_elegidas,
            al_confirmar=self._al_confirmar_etiquetas,
        )

    def _al_confirmar_etiquetas(self, nuevas_etiquetas: List[str]):
        self._etiquetas_elegidas = nuevas_etiquetas
        self._renderizar_chips_etiquetas()

    def _renderizar_chips_etiquetas(self):
        for hijo in self._contenedor_chips_etiquetas.winfo_children():
            hijo.destroy()

        if not self._etiquetas_elegidas:
            ctk.CTkLabel(
                self._contenedor_chips_etiquetas,
                text="Sin etiquetas seleccionadas (haz clic en 'Añadir etiquetas' para crear o elegir).",
                font=(FUENTE, 11),
                text_color=COLORES["texto_secundario"],
            ).pack(anchor="w")
            return

        mapa_colores = {e.nombre: e.color for e in self._gestor.obtener_etiquetas()}
        for nombre_et in self._etiquetas_elegidas:
            color_chip = mapa_colores.get(nombre_et, "#408FD1")
            chip = ctk.CTkButton(
                self._contenedor_chips_etiquetas,
                text=f"#{nombre_et} ✕",
                height=26,
                corner_radius=13,
                fg_color=color_chip,
                hover_color=color_chip,
                text_color="#FFFFFF",
                font=(FUENTE, 11, "bold"),
                command=lambda n=nombre_et: self._quitar_etiqueta(n),
            )
            chip.pack(side="left", padx=(0, 6), pady=2)

    def _quitar_etiqueta(self, nombre_etiqueta: str):
        if nombre_etiqueta in self._etiquetas_elegidas:
            self._etiquetas_elegidas.remove(nombre_etiqueta)
            self._renderizar_chips_etiquetas()

    def _subir_imagen(self):
        ruta = filedialog.askopenfilename(
            title="Seleccionar foto del gasto",
            filetypes=[("Imágenes", "*.png *.jpg *.jpeg"), ("Todos", "*.*")],
            parent=self,
        )
        if not ruta:
            return
        try:
            with Image.open(ruta) as img:
                img.verify()
        except Exception:
            messagebox.showerror(
                "Archivo inválido",
                "El archivo escogido no es una imagen válida.",
                parent=self,
            )
            return

        if os.path.getsize(ruta) > MAXIMO_ADJUNTO_BYTES:
            messagebox.showerror(
                "Imagen muy grande",
                "La imagen supera el límite de 2 MB.",
                parent=self,
            )
            return

        RUTA_ADJUNTOS.mkdir(parents=True, exist_ok=True)
        extension = Path(ruta).suffix.lower() or ".png"
        marca = datetime.now().strftime("%Y%m%d%H%M%S")
        destino = RUTA_ADJUNTOS / f"gasto_{marca}_{os.getpid()}{extension}"
        shutil.copy2(ruta, destino)
        self._ruta_imagen = str(destino)
        self._etiqueta_imagen.configure(
            text=f"Foto adjunta: {Path(ruta).name}",
            text_color=COLORES["exito"],
        )

    # ------------------------------------------------------------------
    # Guardado del Gasto
    # ------------------------------------------------------------------
    def _guardar_gasto(self):
        valor_limpio = self._campo_valor.obtener_valor()
        moneda_guardar = self._moneda_elegida
        comentario = self._campo_comentario.get().strip() or None

        cuenta_obj = None
        if self._cuenta_elegida_id is not None:
            cuenta_obj = self._gestor.obtener_cuenta(self._cuenta_elegida_id)

        if self._moneda_elegida != "COP" and self._cotizacion_trm is not None:
            valor_cop_equiv = self._campo_valor_cop_equiv.obtener_valor().strip()
            if cuenta_obj is not None and cuenta_obj.moneda == "COP" and valor_cop_equiv:
                nota_conv = f"({self._moneda_elegida} {valor_limpio} a tasa {self._cotizacion_trm.precio})"
                comentario = f"{comentario} {nota_conv}".strip() if comentario else nota_conv
                valor_limpio = valor_cop_equiv
                moneda_guardar = "COP"

        mapa_cats = {c.nombre: c for c in self._gestor.obtener_categorias_detalladas("GASTO")}
        cat_obj = mapa_cats.get(self._categoria_elegida)
        es_prog = bool(cat_obj.gasto_programado) if cat_obj else False
        frec_prog = cat_obj.frecuencia if cat_obj else None

        try:
            movimiento = self._gestor.registrar_gasto(
                valor_texto=valor_limpio,
                moneda=moneda_guardar,
                cuenta_id=self._cuenta_elegida_id,
                categoria=self._categoria_elegida,
                fecha_texto=self._fecha_elegida.isoformat(),
                etiquetas=self._etiquetas_elegidas,
                comentario=comentario,
                imagen=self._ruta_imagen,
                es_programado=es_prog,
                frecuencia=frec_prog,
            )
        except (ErrorValidacion, LookupError) as error:
            messagebox.showwarning("No se pudo guardar el gasto", str(error), parent=self)
            return

        self._al_guardar(movimiento)
        self.destroy()
