"""Vista principal del Módulo de Inversiones Bursátiles para NexSaldo.

Incluye:
1. Buscador de acciones y ETFs en tiempo real (ej. QQQ, VOO, SPY, AAPL, NVDA o cualquier ticker de Yahoo Finance).
2. Modal de asignación de portafolio (`DialogoAsignarInversion`) al hacer clic en un resultado de búsqueda,
   calculando automáticamente los títulos fraccionarios y convirtiendo divisas en segundo plano.
3. Valoración dinámica en tiempo real con indicadores de ganancia (▲ verde) o pérdida (▼ rojo) y soporte offline con caché.
4. Gráfica de rendimiento estilo montaña (formato eToro / Robinhood) con selectores de temporalidad
   (`1D`, `1W`, `1M`, `1Y`), degradado bajo la curva adaptable a tendencia positiva/negativa y crosshair interactivo.
"""

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Callable, Dict, List, Optional, Tuple
import customtkinter as ctk

from app.gestor.gestor_financiero import ErrorValidacion, GestorFinanciero
from app.gui.calendario import SelectorCalendario
from app.gui.campo_moneda import CampoMoneda
from app.gui.estilos import COLORES, FUENTE
from app.gui.formato import formatear_valor
from app.gui.selector_moneda import BarraFiltroMoneda, DialogoSelectorDivisa
from app.modelo.cotizacion import Cotizacion
from app.modelo.divisas import (
    etiqueta_divisa,
    extraer_codigo_divisa,
    obtener_prefijo_divisa,
)
from app.modelo.inversion import Inversion, ValoracionInversion

ANCHO_MONTANA = 620
ALTO_MONTANA = 235
MARCOS_TIEMPO = ("1D", "1W", "1M", "1Y")


class DialogoAsignarInversion(ctk.CTkToplevel):
    """Modal que se abre al seleccionar una acción o ETF en el buscador para ingresar
    cuánto dinero tiene invertido el usuario en ese activo."""

    def __init__(
        self,
        master,
        gestor: GestorFinanciero,
        activo: Dict[str, str],
        moneda_predeterminada: str = "USD",
        al_guardar: Optional[Callable[[Inversion], None]] = None,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self._gestor = gestor
        self._activo = dict(activo)
        self._simbolo = activo.get("simbolo", "VOO").strip().upper()
        self._nombre = activo.get("nombre", self._simbolo).strip()
        self._al_guardar = al_guardar

        self._moneda_elegida = (
            moneda_predeterminada or activo.get("moneda", "USD") or "USD"
        ).strip().upper()
        self._fecha_compra = date.today()
        self._precio_mercado_usd: Optional[Decimal] = None
        self._precio_en_moneda: Optional[Decimal] = None
        self._desde_cache = False

        self.title(f"Invertir en {self._simbolo} — {self._nombre}")
        self.geometry("540x610")
        self.resizable(False, False)
        self.configure(fg_color=COLORES["fondo_lateral"])
        self.transient(master)
        self.grab_set()

        self._construir_interfaz()
        self._consultar_precio_vivo_asincrono()

    def _construir_interfaz(self):
        cuerpo = ctk.CTkFrame(self, fg_color="transparent")
        cuerpo.pack(fill="both", expand=True, padx=20, pady=16)

        # Cabecera del activo seleccionado
        tarjeta_activo = ctk.CTkFrame(
            cuerpo, fg_color=COLORES["fondo_tarjeta"], corner_radius=12
        )
        tarjeta_activo.pack(fill="x", pady=(0, 12))

        fila_cab = ctk.CTkFrame(tarjeta_activo, fg_color="transparent")
        fila_cab.pack(fill="x", padx=16, pady=12)

        insignia = ctk.CTkLabel(
            fila_cab,
            text=self._simbolo,
            font=(FUENTE, 16, "bold"),
            fg_color=COLORES["acento"],
            text_color=COLORES["campo_texto"],
            corner_radius=8,
            width=72,
            height=38,
        )
        insignia.pack(side="left", padx=(0, 12))

        col_tit = ctk.CTkFrame(fila_cab, fg_color="transparent")
        col_tit.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            col_tit,
            text=self._nombre,
            font=(FUENTE, 15, "bold"),
            text_color=COLORES["texto"],
            anchor="w",
        ).pack(anchor="w")

        self._etiqueta_precio_vivo = ctk.CTkLabel(
            col_tit,
            text="Consultando cotización actual en Yahoo Finance...",
            font=(FUENTE, 11, "bold"),
            text_color=COLORES["texto_secundario"],
            anchor="w",
        )
        self._etiqueta_precio_vivo.pack(anchor="w", pady=(2, 0))

        # Formulario de asignación de capital
        marco_form = ctk.CTkFrame(
            cuerpo, fg_color=COLORES["fondo_tarjeta"], corner_radius=12
        )
        marco_form.pack(fill="both", expand=True, pady=(0, 12))

        ctk.CTkLabel(
            marco_form,
            text="¿Cuánto dinero tienes invertido en este activo?",
            font=(FUENTE, 13, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w", padx=16, pady=(14, 6))

        fila_monto = ctk.CTkFrame(marco_form, fg_color="transparent")
        fila_monto.pack(fill="x", padx=16, pady=(0, 10))

        prefijo = obtener_prefijo_divisa(self._moneda_elegida)
        self._etiqueta_prefijo = ctk.CTkLabel(
            fila_monto,
            text=f"{self._moneda_elegida} {prefijo}",
            font=(FUENTE, 13, "bold"),
            text_color=COLORES["acento"],
            width=64,
        )
        self._etiqueta_prefijo.pack(side="left", padx=(0, 6))

        self._campo_monto = CampoMoneda(
            fila_monto, width=180, height=40, corner_radius=8
        )
        self._campo_monto.pack(side="left", padx=(0, 8))
        self._campo_monto.bind("<KeyRelease>", self._recalcular_titulos, add="+")

        opciones_div = self._gestor.obtener_opciones_selector_divisas()
        self._combo_moneda = ctk.CTkComboBox(
            fila_monto,
            values=opciones_div,
            width=155,
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
            command=self._al_cambiar_moneda_combo,
        )
        self._combo_moneda.set(etiqueta_divisa(self._moneda_elegida))
        self._combo_moneda.pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            fila_monto,
            text="🌍",
            width=38,
            height=40,
            corner_radius=8,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 14),
            command=self._abrir_selector_mundial,
        ).pack(side="left")

        # Precio de compra por unidad (auto-rellenado desde Yahoo Finance, editable para simular ganancias/pérdidas)
        ctk.CTkLabel(
            marco_form,
            text="Precio de compra por acción / título (se autocompleta con el precio actual o ingresa tu precio de entrada):",
            font=(FUENTE, 11, "bold"),
            text_color=COLORES["texto_secundario"],
            wraplength=470,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(4, 4))

        fila_precio = ctk.CTkFrame(marco_form, fg_color="transparent")
        fila_precio.pack(fill="x", padx=16, pady=(0, 8))

        self._campo_precio_compra = ctk.CTkEntry(
            fila_precio,
            placeholder_text="Precio de entrada por título...",
            fg_color=COLORES["campo_fondo"],
            text_color=COLORES["campo_texto"],
            font=(FUENTE, 13, "bold"),
            width=210,
            height=36,
            corner_radius=8,
        )
        self._campo_precio_compra.pack(side="left", padx=(0, 10))
        self._campo_precio_compra.bind("<KeyRelease>", self._recalcular_titulos, add="+")

        self._etiqueta_titulos_calculados = ctk.CTkLabel(
            fila_precio,
            text="Títulos estimados: 0.000000",
            font=(FUENTE, 12, "bold"),
            text_color=COLORES["exito"],
        )
        self._etiqueta_titulos_calculados.pack(side="left")

        # Fecha de compra y nota opcional
        fila_fecha = ctk.CTkFrame(marco_form, fg_color="transparent")
        fila_fecha.pack(fill="x", padx=16, pady=(6, 8))

        ctk.CTkLabel(
            fila_fecha,
            text="Fecha de inversión:",
            font=(FUENTE, 12, "bold"),
            text_color=COLORES["texto"],
        ).pack(side="left", padx=(0, 10))

        self._btn_fecha = ctk.CTkButton(
            fila_fecha,
            text=f"📅  {self._fecha_compra.isoformat()}",
            width=160,
            height=34,
            corner_radius=8,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 12, "bold"),
            command=self._abrir_calendario,
        )
        self._btn_fecha.pack(side="left")

        ctk.CTkLabel(
            marco_form,
            text="Nota o bróker (opcional):",
            font=(FUENTE, 12, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w", padx=16, pady=(6, 4))

        self._campo_notas = ctk.CTkEntry(
            marco_form,
            placeholder_text="Ej: Portafolio largo plazo eToro / Interactive Brokers / Trii...",
            fg_color=COLORES["campo_fondo"],
            text_color=COLORES["campo_texto"],
            font=(FUENTE, 12),
            height=36,
            corner_radius=8,
        )
        self._campo_notas.pack(fill="x", padx=16, pady=(0, 14))

        # Botones inferiores
        fila_botones = ctk.CTkFrame(cuerpo, fg_color="transparent")
        fila_botones.pack(fill="x")

        ctk.CTkButton(
            fila_botones,
            text="Cancelar",
            width=120,
            height=40,
            corner_radius=8,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 13),
            command=self.destroy,
        ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            fila_botones,
            text="Añadir al portafolio",
            width=195,
            height=40,
            corner_radius=8,
            fg_color=COLORES["acento"],
            hover_color=COLORES["acento_hover"],
            text_color=COLORES["campo_texto"],
            font=(FUENTE, 14, "bold"),
            command=self._guardar_inversion,
        ).pack(side="right")

    def _al_cambiar_moneda_combo(self, texto: str):
        self._aplicar_moneda(extraer_codigo_divisa(texto))

    def _abrir_selector_mundial(self):
        DialogoSelectorDivisa(
            self,
            gestor=self._gestor,
            moneda_actual=self._moneda_elegida,
            al_seleccionar=self._aplicar_moneda,
        )

    def _aplicar_moneda(self, codigo: str):
        self._moneda_elegida = codigo.strip().upper()
        self._gestor.registrar_moneda_usada(self._moneda_elegida)
        self._combo_moneda.configure(values=self._gestor.obtener_opciones_selector_divisas())
        self._combo_moneda.set(etiqueta_divisa(self._moneda_elegida))
        prefijo = obtener_prefijo_divisa(self._moneda_elegida)
        self._etiqueta_prefijo.configure(text=f"{self._moneda_elegida} {prefijo}")
        self._consultar_precio_vivo_asincrono()

    def _consultar_precio_vivo_asincrono(self):
        sim = self._simbolo
        mon = self._moneda_elegida
        self._etiqueta_precio_vivo.configure(
            text=f"Consultando precio actual de {sim} en Yahoo Finance...",
            text_color=COLORES["texto_secundario"],
        )

        def _tarea():
            cot = self._gestor.consultar_precio_inversion(sim, moneda_esperada="USD")
            precio_conv = None
            if cot is not None and cot.precio > Decimal("0"):
                if mon == cot.moneda:
                    precio_conv = cot.precio
                else:
                    try:
                        precio_conv = self._gestor.convertir_entre_monedas(
                            cot.precio, cot.moneda, mon
                        )
                    except Exception:
                        precio_conv = cot.precio
            if self.winfo_exists():
                self.after(0, lambda: self._al_recibir_precio_vivo(cot, precio_conv))

        threading.Thread(target=_tarea, daemon=True).start()

    def _al_recibir_precio_vivo(
        self, cot: Optional[Cotizacion], precio_conv: Optional[Decimal]
    ):
        if not self.winfo_exists():
            return
        if cot is not None and precio_conv is not None:
            self._precio_mercado_usd = cot.precio
            self._precio_en_moneda = precio_conv
            es_cache = "Caché" in (cot.fuente or "")
            etiqueta_fuente = (
                f"Caché sin conexión ({cot.fecha.isoformat()})"
                if es_cache
                else f"Yahoo Finance en vivo ({cot.fecha.isoformat()})"
            )
            self._etiqueta_precio_vivo.configure(
                text=f"Precio actual: {formatear_valor(precio_conv, self._moneda_elegida)}  •  {etiqueta_fuente}",
                text_color=COLORES["acento"] if es_cache else COLORES["exito"],
            )
            self._campo_precio_compra.delete(0, "end")
            self._campo_precio_compra.insert(0, f"{precio_conv:.2f}")
            self._recalcular_titulos()
        else:
            self._etiqueta_precio_vivo.configure(
                text="📡 Sin conexión ni caché previo para este activo; ingresa tu precio de compra manualmente.",
                text_color=COLORES["error"],
            )

    def _recalcular_titulos(self, _evento=None):
        monto_txt = self._campo_monto.obtener_valor().strip()
        precio_txt = self._campo_precio_compra.get().strip().replace(",", ".")
        try:
            monto = Decimal(monto_txt.replace(",", "."))
            precio = Decimal(precio_txt)
            if monto > Decimal("0") and precio > Decimal("0"):
                titulos = (monto / precio).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
                self._etiqueta_titulos_calculados.configure(
                    text=f"Títulos: {titulos} {self._simbolo}",
                    text_color=COLORES["exito"],
                )
                return
        except (InvalidOperation, ZeroDivisionError):
            pass
        self._etiqueta_titulos_calculados.configure(
            text="Títulos estimados: 0.000000",
            text_color=COLORES["texto_secundario"],
        )

    def _abrir_calendario(self):
        SelectorCalendario(
            self,
            al_elegir=self._al_elegir_fecha,
            fecha_inicial=self._fecha_compra,
        )

    def _al_elegir_fecha(self, nueva_fecha: date):
        self._fecha_compra = nueva_fecha
        self._btn_fecha.configure(text=f"📅  {nueva_fecha.isoformat()}")

    def _guardar_inversion(self):
        monto_limpio = self._campo_monto.obtener_valor().strip()
        precio_txt = self._campo_precio_compra.get().strip() or None
        notas = self._campo_notas.get().strip() or None
        try:
            inv = self._gestor.registrar_inversion(
                simbolo=self._simbolo,
                nombre=self._nombre,
                monto_texto=monto_limpio,
                moneda=self._moneda_elegida,
                precio_compra_texto=precio_txt,
                fecha_texto=self._fecha_compra.isoformat(),
                notas=notas,
            )
        except ErrorValidacion as error:
            messagebox.showwarning("Datos incompletos", str(error), parent=self)
            return

        if self._al_guardar is not None:
            self._al_guardar(inv)
        self.destroy()


class VistaInversiones(ctk.CTkFrame):
    """Módulo completo de Inversiones Bursátiles con buscador de tickers en vivo,
    gráfica de rendimiento estilo montaña (eToro / Robinhood) con marcos 1D, 1W, 1M, 1Y,
    y portafolio dinámico en tiempo real."""

    def __init__(self, master, gestor: GestorFinanciero, **kwargs):
        super().__init__(master, fg_color=COLORES["fondo_contenido"], **kwargs)
        self._gestor = gestor
        self._moneda_vista = "COP"
        self._incluir_todas_convertidas = True
        self._marco_tiempo = "1M"
        self._simbolo_grafica: Optional[str] = None
        self._botones_timeframe: Dict[str, ctk.CTkButton] = {}
        self._puntos_montana_actuales: List[Tuple[str, Decimal]] = []
        self._coords_montana_px: List[Tuple[float, float, str, Decimal]] = []
        self._en_ganancia_montana: bool = True

        self._construir_interfaz()
        self.refrescar()

    def _construir_interfaz(self):
        contenedor = ctk.CTkScrollableFrame(self, fg_color="transparent")
        contenedor.pack(fill="both", expand=True, padx=22, pady=16)

        # ==================================================================
        # 1. CABECERA + BOTÓN ACTUALIZAR PRECIOS EN VIVO
        # ==================================================================
        fila_sup = ctk.CTkFrame(contenedor, fg_color="transparent")
        fila_sup.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            fila_sup,
            text="Inversiones Bursátiles",
            font=(FUENTE, 26, "bold"),
            text_color=COLORES["texto"],
        ).pack(side="left")

        self._btn_refrescar_vivo = ctk.CTkButton(
            fila_sup,
            text="🔄 Actualizar precios en vivo",
            width=210,
            height=38,
            corner_radius=10,
            fg_color=COLORES["acento"],
            hover_color=COLORES["acento_hover"],
            text_color=COLORES["campo_texto"],
            font=(FUENTE, 13, "bold"),
            command=self._forzar_actualizacion_precios,
        )
        self._btn_refrescar_vivo.pack(side="right")

        # ==================================================================
        # 2. BARRA DE MONEDA MUNDIAL (COP por defecto + Todo convertido)
        # ==================================================================
        marco_moneda = ctk.CTkFrame(
            contenedor, fg_color=COLORES["fondo_tarjeta"], corner_radius=12
        )
        marco_moneda.pack(fill="x", pady=(0, 12))

        fila_barra = ctk.CTkFrame(marco_moneda, fg_color="transparent")
        fila_barra.pack(fill="x", padx=14, pady=8)

        self._barra_moneda = BarraFiltroMoneda(
            fila_barra,
            gestor=self._gestor,
            al_cambiar=self._al_cambiar_moneda,
            moneda_inicial="COP",
            mostrar_modo=True,
        )
        self._barra_moneda.pack(side="left")
        # Por defecto activar "Todo convertido" para ver activos en USD convertidos a COP
        try:
            self._barra_moneda._var_modo.set("Todo convertido")
        except Exception:
            pass

        # ==================================================================
        # 3. BUSCADOR DE ACCIONES Y ETFs (QQQ, VOO, SPY, AAPL, NVDA...)
        # ==================================================================
        tarjeta_buscador = ctk.CTkFrame(
            contenedor, fg_color=COLORES["fondo_tarjeta"], corner_radius=14
        )
        tarjeta_buscador.pack(fill="x", pady=(0, 14))

        fila_tit_busq = ctk.CTkFrame(tarjeta_buscador, fg_color="transparent")
        fila_tit_busq.pack(fill="x", padx=16, pady=(12, 4))

        ctk.CTkLabel(
            fila_tit_busq,
            text="🔎 Buscar acción o ETF en bolsa (haz clic en un resultado para añadir fondos):",
            font=(FUENTE, 13, "bold"),
            text_color=COLORES["texto"],
        ).pack(side="left")

        self._campo_busqueda = ctk.CTkEntry(
            tarjeta_buscador,
            placeholder_text="Escribe un ticker o índice (ej: QQQ para Nasdaq, VOO o SPY para S&P 500, AAPL, NVDA, MSFT...)",
            fg_color=COLORES["campo_fondo"],
            text_color=COLORES["campo_texto"],
            font=(FUENTE, 13),
            height=38,
            corner_radius=8,
        )
        self._campo_busqueda.pack(fill="x", padx=16, pady=(0, 8))
        self._campo_busqueda.bind("<KeyRelease>", lambda _e: self._renderizar_resultados_busqueda())

        self._contenedor_resultados = ctk.CTkFrame(
            tarjeta_buscador, fg_color="transparent"
        )
        self._contenedor_resultados.pack(fill="x", padx=14, pady=(0, 12))
        self._renderizar_resultados_busqueda()

        # ==================================================================
        # 4. TARJETA CENTRAL: GRÁFICA DE RENDIMIENTO ESTILO MONTAÑA (eToro / Robinhood)
        # ==================================================================
        tarjeta_montana = ctk.CTkFrame(
            contenedor, fg_color=COLORES["fondo_tarjeta"], corner_radius=14
        )
        tarjeta_montana.pack(fill="x", pady=(0, 14))

        cab_montana = ctk.CTkFrame(tarjeta_montana, fg_color="transparent")
        cab_montana.pack(fill="x", padx=18, pady=(14, 6))

        col_kpi = ctk.CTkFrame(cab_montana, fg_color="transparent")
        col_kpi.pack(side="left")

        self._etiqueta_titulo_portafolio = ctk.CTkLabel(
            col_kpi,
            text="Valor actual del portafolio",
            font=(FUENTE, 12, "bold"),
            text_color=COLORES["texto_secundario"],
        )
        self._etiqueta_titulo_portafolio.pack(anchor="w")

        self._etiqueta_valor_portafolio = ctk.CTkLabel(
            col_kpi,
            text="$ 0,00",
            font=(FUENTE, 26, "bold"),
            text_color=COLORES["texto"],
        )
        self._etiqueta_valor_portafolio.pack(anchor="w")

        self._etiqueta_rendimiento_portafolio = ctk.CTkLabel(
            col_kpi,
            text="Capital invertido: $ 0,00  •  Rendimiento: +$ 0,00 (0.00%)",
            font=(FUENTE, 12, "bold"),
            text_color=COLORES["exito"],
        )
        self._etiqueta_rendimiento_portafolio.pack(anchor="w", pady=(2, 0))

        # Controles de temporalidad (1D, 1W, 1M, 1Y) a la derecha
        col_controles_graf = ctk.CTkFrame(cab_montana, fg_color="transparent")
        col_controles_graf.pack(side="right")

        fila_tf = ctk.CTkFrame(col_controles_graf, fg_color=COLORES["boton_lateral"], corner_radius=8)
        fila_tf.pack(anchor="e", pady=(0, 6))

        for tf in MARCOS_TIEMPO:
            btn = ctk.CTkButton(
                fila_tf,
                text=tf,
                width=46,
                height=30,
                corner_radius=6,
                font=(FUENTE, 12, "bold"),
                command=lambda m=tf: self._cambiar_marco_tiempo(m),
            )
            btn.pack(side="left", padx=3, pady=3)
            self._botones_timeframe[tf] = btn

        self._actualizar_estilo_botones_timeframe()

        self._etiqueta_hover_montana = ctk.CTkLabel(
            col_controles_graf,
            text="Pasa el cursor sobre la curva para inspeccionar",
            font=(FUENTE, 11),
            text_color=COLORES["texto_secundario"],
        )
        self._etiqueta_hover_montana.pack(anchor="e")

        self._lienzo_montana = tk.Canvas(
            tarjeta_montana,
            width=ANCHO_MONTANA,
            height=ALTO_MONTANA,
            bg=COLORES["fondo_tarjeta"],
            highlightthickness=0,
        )
        self._lienzo_montana.pack(fill="x", padx=16, pady=(4, 14))
        self._lienzo_montana.bind("<Motion>", self._al_mover_cursor_montana)
        self._lienzo_montana.bind("<Leave>", lambda _e: self._limpiar_crosshair_montana())

        # ==================================================================
        # 5. LISTA DE POSICIONES ACTIVAS EN EL PORTAFOLIO
        # ==================================================================
        tarjeta_posiciones = ctk.CTkFrame(
            contenedor, fg_color=COLORES["fondo_tarjeta"], corner_radius=14
        )
        tarjeta_posiciones.pack(fill="both", expand=True)

        fila_cab_pos = ctk.CTkFrame(tarjeta_posiciones, fg_color="transparent")
        fila_cab_pos.pack(fill="x", padx=18, pady=(14, 8))

        ctk.CTkLabel(
            fila_cab_pos,
            text="Mis activos en portafolio (haz clic en un activo para filtrar la gráfica de montaña)",
            font=(FUENTE, 15, "bold"),
            text_color=COLORES["texto"],
        ).pack(side="left")

        self._btn_ver_todo_portafolio = ctk.CTkButton(
            fila_cab_pos,
            text="Ver todo el portafolio",
            width=155,
            height=28,
            corner_radius=6,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["acento"],
            font=(FUENTE, 11, "bold"),
            command=lambda: self._filtrar_grafica_por_simbolo(None),
        )
        self._btn_ver_todo_portafolio.pack(side="right")

        self._contenedor_posiciones = ctk.CTkFrame(
            tarjeta_posiciones, fg_color="transparent"
        )
        self._contenedor_posiciones.pack(fill="both", expand=True, padx=16, pady=(0, 16))

    # ------------------------------------------------------------------
    # Buscador de Acciones y ETFs
    # ------------------------------------------------------------------
    def _renderizar_resultados_busqueda(self):
        for hijo in self._contenedor_resultados.winfo_children():
            hijo.destroy()

        consulta = self._campo_busqueda.get().strip()
        resultados = self._gestor.buscar_activos_bursatiles(consulta)[:8]

        rejilla = ctk.CTkFrame(self._contenedor_resultados, fg_color="transparent")
        rejilla.pack(fill="x")
        for c in range(4):
            rejilla.grid_columnconfigure(c, weight=1)

        for idx, item in enumerate(resultados):
            fila = idx // 4
            col = idx % 4
            sim = item["simbolo"]
            nom = item["nombre"]
            nombre_corto = nom if len(nom) <= 24 else nom[:22] + "…"

            btn = ctk.CTkButton(
                rejilla,
                text=f"📈 {sim}  •  {nombre_corto}",
                anchor="w",
                height=34,
                corner_radius=8,
                fg_color=COLORES["boton_lateral"],
                hover_color=COLORES["hover_lateral"],
                border_width=1,
                border_color=COLORES["acento"] if idx < 2 and consulta else COLORES["boton_lateral"],
                text_color=COLORES["texto"],
                font=(FUENTE, 11, "bold"),
                command=lambda act=item: self._abrir_modal_asignar(act),
            )
            btn.grid(row=fila, column=col, sticky="ew", padx=4, pady=3)

    def _abrir_modal_asignar(self, activo: Dict[str, str]):
        DialogoAsignarInversion(
            self,
            gestor=self._gestor,
            activo=activo,
            moneda_predeterminada=activo.get("moneda", "USD"),
            al_guardar=lambda _inv: self.refrescar(),
        )

    # ------------------------------------------------------------------
    # Controles de Moneda, Temporalidad y Actualización Asíncrona
    # ------------------------------------------------------------------
    def _al_cambiar_moneda(self, nueva_moneda: str, incluir_todas: bool):
        self._moneda_vista = nueva_moneda
        self._incluir_todas_convertidas = incluir_todas
        self.refrescar()

    def _cambiar_marco_tiempo(self, nuevo_marco: str):
        self._marco_tiempo = nuevo_marco
        self._actualizar_estilo_botones_timeframe()
        self._cargar_curva_montana_asincrona()

    def _filtrar_grafica_por_simbolo(self, simbolo: Optional[str]):
        self._simbolo_grafica = simbolo
        self.refrescar()

    def _actualizar_estilo_botones_timeframe(self):
        for tf, boton in self._botones_timeframe.items():
            activo = tf == self._marco_tiempo
            boton.configure(
                fg_color=COLORES["acento"] if activo else "transparent",
                hover_color=COLORES["acento_hover"] if activo else COLORES["hover_lateral"],
                text_color=COLORES["campo_texto"] if activo else COLORES["texto"],
            )

    def _forzar_actualizacion_precios(self):
        self._btn_refrescar_vivo.configure(text="⏳ Actualizando...", state="disabled")

        def _tarea():
            try:
                self._gestor.valorar_portafolio(
                    moneda_objetivo=self._moneda_vista,
                    incluir_todas_convertidas=self._incluir_todas_convertidas,
                    forzar_actualizacion=True,
                )
            finally:
                if self.winfo_exists():
                    self.after(0, self._al_terminar_actualizacion_forzada)

        threading.Thread(target=_tarea, daemon=True).start()

    def _al_terminar_actualizacion_forzada(self):
        if not self.winfo_exists():
            return
        self._btn_refrescar_vivo.configure(
            text="🔄 Actualizar precios en vivo", state="normal"
        )
        self.refrescar()

    def refrescar(self):
        moneda = self._moneda_vista
        resumen = self._gestor.valorar_portafolio(
            moneda_objetivo=moneda,
            incluir_todas_convertidas=self._incluir_todas_convertidas,
            forzar_actualizacion=False,
        )
        posiciones: List[ValoracionInversion] = resumen["posiciones"]  # type: ignore[assignment]
        capital_inv: Decimal = resumen["capital_invertido"]  # type: ignore[assignment]
        valor_actual: Decimal = resumen["valor_actual_mercado"]  # type: ignore[assignment]
        ganancia_neta: Decimal = resumen["ganancia_perdida_neta"]  # type: ignore[assignment]
        rend_pct: Decimal = resumen["rendimiento_porcentaje"]  # type: ignore[assignment]
        en_ganancia: bool = bool(resumen["en_ganancia"])

        filtro_txt = (
            f" ({self._simbolo_grafica})" if self._simbolo_grafica else " (Portafolio total)"
        )
        self._etiqueta_titulo_portafolio.configure(
            text=f"Valor actual del portafolio ({moneda}){filtro_txt}"
        )
        self._etiqueta_valor_portafolio.configure(
            text=formatear_valor(valor_actual, moneda)
        )

        flecha = "▲" if en_ganancia else "▼"
        signo = "+" if en_ganancia else "-"
        color_pnl = COLORES["exito"] if en_ganancia else COLORES["error"]
        self._etiqueta_rendimiento_portafolio.configure(
            text=(
                f"Capital invertido: {formatear_valor(capital_inv, moneda)}   •   "
                f"{flecha} {signo}{formatear_valor(abs(ganancia_neta), moneda)} ({signo}{abs(rend_pct):.2f}%)"
            ),
            text_color=color_pnl,
        )

        self._renderizar_lista_posiciones(posiciones, moneda)
        self._cargar_curva_montana_asincrona()

    # ------------------------------------------------------------------
    # Gráfica Estilo Montaña (eToro / Robinhood) con Área Degradada
    # ------------------------------------------------------------------
    def _cargar_curva_montana_asincrona(self):
        tf = self._marco_tiempo
        sim = self._simbolo_grafica
        mon = self._moneda_vista
        inc = self._incluir_todas_convertidas

        def _tarea():
            datos_curva = self._gestor.obtener_serie_montana_portafolio(
                marco_tiempo=tf,
                simbolo_filtro=sim,
                moneda_objetivo=mon,
                incluir_todas_convertidas=inc,
            )
            if self.winfo_exists():
                self.after(0, lambda: self._dibujar_grafica_montana(datos_curva))

        threading.Thread(target=_tarea, daemon=True).start()

    def _dibujar_grafica_montana(self, datos_curva: Dict[str, object]):
        if not self.winfo_exists():
            return
        self._lienzo_montana.delete("all")
        self._coords_montana_px.clear()

        puntos: List[Tuple[str, Decimal]] = datos_curva.get("puntos", [])  # type: ignore[assignment]
        en_ganancia: bool = bool(datos_curva.get("en_ganancia", True))
        self._puntos_montana_actuales = puntos
        self._en_ganancia_montana = en_ganancia

        ancho = max(ANCHO_MONTANA, self._lienzo_montana.winfo_width())
        alto = ALTO_MONTANA

        if not puntos:
            self._lienzo_montana.create_text(
                ancho // 2,
                alto // 2,
                text="Aún no tienes inversiones registradas.\nBusca un activo arriba (ej. QQQ, VOO, AAPL) y haz clic para añadir fondos.",
                fill=COLORES["texto_secundario"],
                font=(FUENTE, 12, "bold"),
                justify="center",
            )
            return

        margen_izq = 68
        margen_der = 26
        margen_sup = 24
        margen_inf = 30
        ancho_util = max(10, ancho - margen_izq - margen_der)
        alto_util = max(10, alto - margen_sup - margen_inf)
        y_base = alto - margen_inf

        valores = [float(p[1]) for p in puntos]
        v_min = min(valores)
        v_max = max(valores)
        rango_v = (v_max - v_min) if v_max > v_min else max(1.0, v_max * 0.05)

        # Paleta dinámica según si el rendimiento sube (verde eToro) o baja (rojo)
        if en_ganancia:
            color_linea = "#7DC98F"
            bandas_relleno = ("#255440", "#1E4434", "#18372A")
        else:
            color_linea = "#F28C8C"
            bandas_relleno = ("#522931", "#3E2128", "#2E1B21")

        # Líneas guía horizontales
        for frac in (0.0, 0.5, 1.0):
            yg = int(margen_sup + alto_util * frac)
            val_guia = Decimal(str(v_max - rango_v * frac))
            self._lienzo_montana.create_line(
                margen_izq, yg, ancho - margen_der, yg,
                fill=COLORES["boton_lateral"], width=1, dash=(3, 3)
            )
            self._lienzo_montana.create_text(
                margen_izq - 8,
                yg,
                text=_abreviar_cifra(val_guia),
                fill=COLORES["texto_secundario"],
                font=(FUENTE, 9),
                anchor="e",
            )

        # Calcular coordenadas (x, y) de cada punto de la curva
        n = len(puntos)
        coords_curva: List[Tuple[float, float]] = []
        for idx, (etiqueta, valor_dec) in enumerate(puntos):
            x = margen_izq + (idx / max(1, n - 1)) * ancho_util
            norm = (float(valor_dec) - v_min) / rango_v
            y = (y_base - 8) - norm * (alto_util - 16)
            coords_curva.append((x, y))
            self._coords_montana_px.append((x, y, etiqueta, valor_dec))

        # Polígono de montaña en 3 bandas superpuestas para efecto degradado suave (estilo eToro)
        alturas_base = [
            (y_base, bandas_relleno[2]),
            (margen_sup + int(alto_util * 0.78), bandas_relleno[1]),
            (margen_sup + int(alto_util * 0.55), bandas_relleno[0]),
        ]
        for y_corte, color_banda in alturas_base:
            poligono_pts: List[float] = [coords_curva[0][0], float(y_base)]
            for x, y in coords_curva:
                poligono_pts.extend([x, min(float(y_corte), y)])
            poligono_pts.extend([coords_curva[-1][0], float(y_base)])
            self._lienzo_montana.create_polygon(
                *poligono_pts,
                fill=color_banda,
                outline="",
                smooth=False,
            )

        # Línea de referencia del valor inicial del periodo (punteada)
        y_inicial = coords_curva[0][1]
        self._lienzo_montana.create_line(
            margen_izq,
            int(y_inicial),
            ancho - margen_der,
            int(y_inicial),
            fill=COLORES["texto_secundario"],
            width=1,
            dash=(4, 4),
        )

        # Trazo superior brillante de la montaña
        linea_plana: List[float] = []
        for x, y in coords_curva:
            linea_plana.extend([x, y])
        if len(linea_plana) >= 4:
            self._lienzo_montana.create_line(
                *linea_plana,
                fill=color_linea,
                width=2.8,
                capstyle="round",
                joinstyle="round",
            )

        # Punto luminoso en el extremo actual (última cotización)
        x_ult, y_ult = coords_curva[-1]
        self._lienzo_montana.create_oval(
            x_ult - 6, y_ult - 6, x_ult + 6, y_ult + 6,
            fill=color_linea, outline=COLORES["fondo_tarjeta"], width=2
        )

        # Etiquetas del eje X (Inicio, Medio, Final)
        indices_x = [0, n // 2, n - 1] if n >= 3 else [0, n - 1]
        for ix in dict.fromkeys(indices_x):
            x_lbl, _, et_lbl, _ = self._coords_montana_px[ix]
            self._lienzo_montana.create_text(
                x_lbl,
                alto - 10,
                text=et_lbl,
                fill=COLORES["texto_secundario"],
                font=(FUENTE, 9, "bold"),
            )

    def _al_mover_cursor_montana(self, evento):
        if not self._coords_montana_px:
            return
        x_raton = evento.x
        mas_cercano = min(
            self._coords_montana_px, key=lambda item: abs(item[0] - x_raton)
        )
        px, py, etiqueta, valor = mas_cercano
        color_c = "#7DC98F" if self._en_ganancia_montana else "#F28C8C"

        self._lienzo_montana.delete("crosshair_hover")
        self._lienzo_montana.create_line(
            px, 20, px, ALTO_MONTANA - 28,
            fill=color_c, width=1, dash=(3, 2), tags="crosshair_hover"
        )
        self._lienzo_montana.create_oval(
            px - 5, py - 5, px + 5, py + 5,
            fill=color_c, outline="#FFFFFF", width=2, tags="crosshair_hover"
        )
        self._etiqueta_hover_montana.configure(
            text=f"📅 {etiqueta}   •   {formatear_valor(valor, self._moneda_vista)}",
            text_color=color_c,
        )

    def _limpiar_crosshair_montana(self):
        self._lienzo_montana.delete("crosshair_hover")
        self._etiqueta_hover_montana.configure(
            text="Pasa el cursor sobre la curva para inspeccionar",
            text_color=COLORES["texto_secundario"],
        )

    # ------------------------------------------------------------------
    # Lista de Posiciones del Portafolio
    # ------------------------------------------------------------------
    def _renderizar_lista_posiciones(
        self, posiciones: List[ValoracionInversion], moneda_vista: str
    ):
        for hijo in self._contenedor_posiciones.winfo_children():
            hijo.destroy()

        if not posiciones:
            ctk.CTkLabel(
                self._contenedor_posiciones,
                text="Tu portafolio está vacío. Usa el buscador superior para añadir tu primera inversión (ej. VOO o QQQ).",
                font=(FUENTE, 13),
                text_color=COLORES["texto_secundario"],
            ).pack(pady=28)
            return

        for val in posiciones:
            inv = val.inversion
            seleccionada = self._simbolo_grafica == inv.simbolo
            fila = ctk.CTkFrame(
                self._contenedor_posiciones,
                fg_color=COLORES["boton_lateral"],
                corner_radius=10,
                border_width=2 if seleccionada else 0,
                border_color=COLORES["acento"],
            )
            fila.pack(fill="x", pady=4)

            btn_ticker = ctk.CTkButton(
                fila,
                text=inv.simbolo,
                width=68,
                height=42,
                corner_radius=8,
                fg_color=COLORES["acento"] if seleccionada else COLORES["fondo_tarjeta"],
                hover_color=COLORES["acento_hover"],
                text_color=COLORES["campo_texto"] if seleccionada else COLORES["acento"],
                font=(FUENTE, 13, "bold"),
                command=lambda s=inv.simbolo: self._filtrar_grafica_por_simbolo(s),
            )
            btn_ticker.pack(side="left", padx=12, pady=10)

            col_izq = ctk.CTkFrame(fila, fg_color="transparent")
            col_izq.pack(side="left", fill="x", expand=True, pady=8)

            ctk.CTkLabel(
                col_izq,
                text=f"{inv.nombre}  •  {inv.cantidad_titulos.quantize(Decimal('0.0001'))} títulos",
                font=(FUENTE, 13, "bold"),
                text_color=COLORES["texto"],
            ).pack(anchor="w")

            sub_detalle = (
                f"Compra: {formatear_valor(inv.precio_compra, inv.moneda)}  →  "
                f"Actual: {formatear_valor(val.precio_actual, inv.moneda)}  •  "
                f"Invertido: {formatear_valor(val.monto_invertido_convertido, moneda_vista)}"
            )
            if val.desde_cache:
                sub_detalle += "  (Caché offline)"

            ctk.CTkLabel(
                col_izq,
                text=sub_detalle,
                font=(FUENTE, 11),
                text_color=COLORES["texto_secundario"],
            ).pack(anchor="w")

            ctk.CTkButton(
                fila,
                text="Eliminar",
                width=72,
                height=28,
                corner_radius=6,
                fg_color="transparent",
                hover_color=COLORES["hover_lateral"],
                text_color=COLORES["error"],
                font=(FUENTE, 11, "bold"),
                command=lambda iid=inv.id: self._confirmar_eliminar_inversion(iid),
            ).pack(side="right", padx=(6, 12))

            col_der = ctk.CTkFrame(fila, fg_color="transparent")
            col_der.pack(side="right", padx=10, pady=8)

            ctk.CTkLabel(
                col_der,
                text=formatear_valor(val.valor_actual_convertido, moneda_vista),
                font=(FUENTE, 14, "bold"),
                text_color=COLORES["texto"],
            ).pack(anchor="e")

            flecha = "▲" if val.en_ganancia else "▼"
            signo = "+" if val.en_ganancia else "-"
            color_pnl = COLORES["exito"] if val.en_ganancia else COLORES["error"]
            ctk.CTkLabel(
                col_der,
                text=(
                    f"{flecha} {signo}{formatear_valor(abs(val.ganancia_perdida_convertida), moneda_vista)} "
                    f"({signo}{abs(val.rendimiento_porcentaje):.2f}%)"
                ),
                font=(FUENTE, 11, "bold"),
                text_color=color_pnl,
            ).pack(anchor="e")

    def _confirmar_eliminar_inversion(self, id_inversion: Optional[int]):
        if id_inversion is None:
            return
        if messagebox.askyesno(
            "Eliminar inversión",
            "¿Deseas eliminar esta posición del portafolio?",
            parent=self,
        ):
            self._gestor.eliminar_inversion(id_inversion)
            self.refrescar()


def _abreviar_cifra(valor: Decimal) -> str:
    v = abs(float(valor))
    if v >= 1_000_000_000:
        return f"{v / 1_000_000_000:.1f}B"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if v >= 10_000:
        return f"{v / 1_000:.1f}k"
    return f"{v:,.0f}"
