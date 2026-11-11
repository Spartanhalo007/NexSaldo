"""Vista principal del Módulo de Inversiones Bursátiles para NexSaldo.

Incluye:
1. Buscador de acciones y ETFs ultra-fluido (sin recrear widgets en cada tecla, evitando pérdida
   de caracteres al escribir rápido ej. 'TTWO') + búsqueda en vivo en Yahoo Finance (`yf.Search`).
2. Modal de asignación de portafolio (`DialogoAsignarInversion`) que distingue entre un ticker
   inexistente/incompleto cuando hay internet vs. falta real de conexión a internet.
3. Valoración dinámica en tiempo real con indicadores de ganancia (▲ verde) o pérdida (▼ rojo).
4. Gráfica de rendimiento estilo montaña (formato eToro) con selectores de temporalidad
   (`1D`, `1W`, `1M`, `1Y`), degradado bajo la curva adaptable a tendencia positiva/negativa y crosshair interactivo.
"""

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Callable, Dict, List, Optional, Tuple
import customtkinter as ctk

from app.gestor.gestor_financiero import ErrorValidacion, GestorFinanciero
from app.servicio.importadores import BROKERS
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
TOTAL_BOTONES_SUGERENCIA = 8


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
            text=f"Consultando cotización actual de {self._simbolo} en Yahoo Finance...",
            font=(FUENTE, 11, "bold"),
            text_color=COLORES["texto_secundario"],
            anchor="w",
            wraplength=390,
            justify="left",
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

        # Precio de compra por unidad
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
            hay_red = (
                self._gestor.hay_conexion_internet(usar_cache_breve=False)
                if hasattr(self._gestor, "hay_conexion_internet")
                else True
            )
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
                self.after(
                    0, lambda: self._al_recibir_precio_vivo(cot, precio_conv, hay_red)
                )

        threading.Thread(target=_tarea, daemon=True).start()

    def _al_recibir_precio_vivo(
        self,
        cot: Optional[Cotizacion],
        precio_conv: Optional[Decimal],
        hay_red: bool = True,
    ):
        if not self.winfo_exists():
            return
        if cot is not None and precio_conv is not None:
            self._precio_mercado_usd = cot.precio
            self._precio_en_moneda = precio_conv
            es_cache = "Caché" in (cot.fuente or "") or not hay_red
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
        elif hay_red:
            self._etiqueta_precio_vivo.configure(
                text=(
                    f"⚠️ El símbolo '{self._simbolo}' no existe en Yahoo Finance. "
                    f"Verifica que el ticker esté completo (ej. TTWO, VOO, QQQ) o ingresa el precio manualmente."
                ),
                text_color=COLORES["error"],
            )
        else:
            self._etiqueta_precio_vivo.configure(
                text=(
                    f"📡 No tienes conexión a internet y no hay caché previo para {self._simbolo}. "
                    f"Tan pronto te conectes se actualizará, o ingresa tu precio de compra manualmente."
                ),
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
        if nueva_fecha < date.today() and hasattr(
            self._gestor, "consultar_precio_historico_inversion"
        ):
            sim = self._simbolo
            mon = self._moneda_elegida

            def _tarea_hist():
                p_hist = self._gestor.consultar_precio_historico_inversion(
                    sim, nueva_fecha, moneda_esperada=mon
                )
                if p_hist is not None and p_hist > Decimal("0") and self.winfo_exists():
                    def _aplicar_p():
                        if not self.winfo_exists():
                            return
                        self._campo_precio_compra.delete(0, "end")
                        self._campo_precio_compra.insert(0, f"{p_hist:.2f}")
                        self._recalcular_titulos()
                    self.after(0, _aplicar_p)

            threading.Thread(target=_tarea_hist, daemon=True).start()

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

        cb = self._al_guardar
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
        if cb is not None:
            cb(inv)




class DialogoElegirBroker(ctk.CTkToplevel):
    """Menú para elegir desde qué plataforma se importa el portafolio.

    Muestra las 5 plataformas más usadas en Colombia. Al elegir una, abre
    el diálogo de importación con las instrucciones propias de esa
    plataforma.
    """

    # Orden acordado: las más usadas en Colombia primero.
    CLAVES_BROKERS = ("etoro", "binance", "trii", "hapi", "ibkr")

    def __init__(self, master, gestor, al_importar, **kwargs):
        super().__init__(master, **kwargs)
        self._gestor = gestor
        self._al_importar = al_importar

        self.title("Importar portafolio")
        self.geometry("460x430")
        self.resizable(False, False)
        self.configure(fg_color=COLORES["fondo_lateral"])
        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        ctk.CTkLabel(
            self,
            text="📥 ¿Desde qué plataforma quieres importar?",
            font=(FUENTE, 17, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w", padx=20, pady=(18, 10))

        for clave in self.CLAVES_BROKERS:
            config = BROKERS[clave]
            ctk.CTkButton(
                self,
                text=str(config["nombre"]),
                width=400,
                height=52,
                corner_radius=10,
                anchor="w",
                fg_color=COLORES["boton_lateral"],
                hover_color=COLORES["hover_lateral"],
                border_width=1,
                border_color=COLORES["acento"],
                text_color=COLORES["texto"],
                font=(FUENTE, 14, "bold"),
                command=lambda c=clave: self._elegir(c),
            ).pack(padx=20, pady=5)

    def _elegir(self, broker: str):
        self.destroy()
        DialogoImportarBroker(
            self.master,
            gestor=self._gestor,
            al_importar=self._al_importar,
            broker=broker,
        )


class DialogoImportarBroker(ctk.CTkToplevel):
    """Modal interactivo para importar posiciones abiertas desde el broker
    elegido (eToro .xlsx/.csv, Binance, Interactive Brokers o la plantilla
    CSV genérica de Trii/Hapi)."""

    def __init__(
        self,
        master,
        gestor: GestorFinanciero,
        al_importar: Callable[[], None],
        broker: str = "etoro",
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self._gestor = gestor
        self._al_importar = al_importar
        self._broker = broker if broker in BROKERS else "etoro"
        self._config = BROKERS[self._broker]
        self._ruta_seleccionada: Optional[str] = None
        self._posiciones_detectadas: List[Dict[str, object]] = []

        self.title(
            f"Importar portafolio desde {self._config['nombre']} (.xlsx / .csv)")
        self.geometry("680x680")
        self.resizable(False, True)
        self.configure(fg_color=COLORES["fondo_lateral"])
        self.transient(master)
        self.grab_set()

        self._construir_interfaz()

    def _construir_interfaz(self):
        cuerpo = ctk.CTkFrame(self, fg_color="transparent")
        cuerpo.pack(fill="both", expand=True, padx=20, pady=16)

        ctk.CTkLabel(
            cuerpo,
            text=f"📥 Importar portafolio desde {self._config['nombre']}",
            font=(FUENTE, 20, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w")

        # Tarjeta de instrucciones paso a paso para exportar desde el broker
        marco_guia = ctk.CTkFrame(
            cuerpo, fg_color=COLORES["fondo_tarjeta"], corner_radius=12
        )
        marco_guia.pack(fill="x", pady=(8, 12))

        ctk.CTkLabel(
            marco_guia,
            text=str(self._config["instrucciones"]),
            font=(FUENTE, 11),
            text_color=COLORES["texto_secundario"],
            justify="left",
            wraplength=610,
        ).pack(anchor="w", padx=14, pady=10)

        # Controles de selección de archivo y agrupación
        fila_arch = ctk.CTkFrame(cuerpo, fg_color="transparent")
        fila_arch.pack(fill="x", pady=(0, 8))

        extensiones = self._config["extensiones"]
        tipos_archivo = [
            (f"Archivos de {self._config['nombre']} / CSV", " ".join(extensiones)),
            ("Todos los archivos", "*.*"),
        ]

        ctk.CTkButton(
            fila_arch,
            text=f"📂 Seleccionar archivo de {self._config['nombre']}",
            width=285,
            height=38,
            corner_radius=8,
            fg_color=COLORES["acento"],
            hover_color=COLORES["acento_hover"],
            text_color=COLORES["campo_texto"],
            font=(FUENTE, 13, "bold"),
            command=self._seleccionar_archivo,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            fila_arch,
            text="📄 Descargar plantilla CSV",
            width=185,
            height=38,
            corner_radius=8,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 12, "bold"),
            command=self._descargar_plantilla,
        ).pack(side="left")

        # Opción 1: reemplazar todo el portafolio con el archivo nuevo.
        self._var_reemplazar = ctk.BooleanVar(value=True)
        self._chk_reemplazar = ctk.CTkCheckBox(
            cuerpo,
            text="Reemplazar portafolio actual (borra importaciones previas antes de cargar solo las abiertas)",
            variable=self._var_reemplazar,
            font=(FUENTE, 12, "bold"),
            text_color=COLORES["acento"],
            fg_color=COLORES["acento"],
            hover_color=COLORES["acento_hover"],
            command=self._al_cambiar_reemplazo,
        )
        self._chk_reemplazar.pack(anchor="w", pady=(2, 4))

        # Opción 2 (nueva): importar solo las posiciones que no existan aún.
        self._var_sin_duplicados = ctk.BooleanVar(value=False)
        self._chk_sin_duplicados = ctk.CTkCheckBox(
            cuerpo,
            text="Importar solo nuevas (omitir duplicados: compara símbolo, fecha y monto contra lo ya guardado)",
            variable=self._var_sin_duplicados,
            font=(FUENTE, 12, "bold"),
            text_color=COLORES["acento"],
            fg_color=COLORES["acento"],
            hover_color=COLORES["acento_hover"],
            command=self._al_cambiar_sin_duplicados,
        )
        self._chk_sin_duplicados.pack(anchor="w", pady=(2, 4))

        # Opción 3: consolidar compras del mismo ticker en una sola posición.
        self._var_agrupar = ctk.BooleanVar(value=False)
        chk = ctk.CTkCheckBox(
            cuerpo,
            text="Consolidar compras por ticker (déjalo desmarcado para importar cada compra de ej. $200, $50, $500 por separado)",
            variable=self._var_agrupar,
            font=(FUENTE, 11),
            text_color=COLORES["texto_secundario"],
            fg_color=COLORES["acento"],
            hover_color=COLORES["acento_hover"],
            command=self._recargar_previsualizacion,
        )
        chk.pack(anchor="w", pady=(0, 8))

        self._etiqueta_estado = ctk.CTkLabel(
            cuerpo,
            text="Ningún archivo seleccionado todavía.",
            font=(FUENTE, 12, "bold"),
            text_color=COLORES["texto_secundario"],
        )
        self._etiqueta_estado.pack(anchor="w", pady=(0, 6))

        # Tabla de previsualización
        self._lista_preview = ctk.CTkScrollableFrame(
            cuerpo, fg_color=COLORES["fondo_tarjeta"], corner_radius=12, height=230
        )
        self._lista_preview.pack(fill="both", expand=True, pady=(0, 12))

        fila_inf = ctk.CTkFrame(cuerpo, fg_color="transparent")
        fila_inf.pack(fill="x")

        ctk.CTkButton(
            fila_inf,
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

        self._btn_confirmar = ctk.CTkButton(
            fila_inf,
            text="✅ Importar al portafolio",
            width=220,
            height=40,
            corner_radius=8,
            fg_color=COLORES["exito"],
            hover_color=COLORES["acento_hover"],
            text_color=COLORES["campo_texto"],
            font=(FUENTE, 14, "bold"),
            state="disabled",
            command=self._ejecutar_importacion,
        )
        self._btn_confirmar.pack(side="right")

    def _al_cambiar_reemplazo(self):
        """Reemplazar e 'importar solo nuevas' son excluyentes."""
        if self._var_reemplazar.get():
            self._var_sin_duplicados.set(False)

    def _al_cambiar_sin_duplicados(self):
        if self._var_sin_duplicados.get():
            self._var_reemplazar.set(False)

    def _seleccionar_archivo(self):
        ruta = filedialog.askopenfilename(
            title=f"Seleccionar archivo de {self._config['nombre']}",
            filetypes=[
                (f"Archivos de {self._config['nombre']} / CSV",
                 " ".join(self._config["extensiones"])),
                ("Excel (.xlsx)", "*.xlsx"),
                ("CSV (.csv)", "*.csv"),
                ("Todos los archivos", "*.*"),
            ],
            parent=self,
        )
        if not ruta:
            return
        self._ruta_seleccionada = ruta
        self._recargar_previsualizacion()

    def _recargar_previsualizacion(self):
        if not self._ruta_seleccionada:
            return
        for hijo in self._lista_preview.winfo_children():
            hijo.destroy()

        try:
            posiciones = self._gestor.previsualizar_importacion_broker(
                self._ruta_seleccionada,
                broker=self._broker,
                agrupar_por_ticker=bool(self._var_agrupar.get()),
            )
        except Exception as error:
            self._posiciones_detectadas = []
            self._etiqueta_estado.configure(
                text=f"⚠️ Error al leer el archivo: {error}",
                text_color=COLORES["error"],
            )
            self._btn_confirmar.configure(state="disabled", text="✅ Importar al portafolio")
            return

        self._posiciones_detectadas = posiciones
        if not posiciones:
            self._etiqueta_estado.configure(
                text="⚠️ No se encontraron posiciones abiertas en este archivo. Verifica que sea una exportación "
                     f"de {self._config['nombre']} con las columnas esperadas (o usa la plantilla CSV).",
                text_color=COLORES["error"],
            )
            self._btn_confirmar.configure(state="disabled", text="✅ Importar al portafolio")
            return

        total_usd = sum((p["monto_invertido"] for p in posiciones), Decimal("0"))
        tickers_unicos = len({str(p["simbolo"]) for p in posiciones})
        self._etiqueta_estado.configure(
            text=(
                f"✅ {len(posiciones)} operaciones ABIERTAS detectadas en {tickers_unicos} activos "
                f"(cerradas excluidas)  •  Total invertido: {formatear_valor(total_usd, 'USD')}"
            ),
            text_color=COLORES["exito"],
        )
        self._btn_confirmar.configure(
            state="normal",
            text=f"✅ Importar {len(posiciones)} operaciones abiertas",
        )

        for pos in posiciones:
            fila = ctk.CTkFrame(
                self._lista_preview, fg_color=COLORES["boton_lateral"], corner_radius=8
            )
            fila.pack(fill="x", padx=6, pady=3)

            sim = str(pos["simbolo"])
            nom = str(pos["nombre"])
            monto: Decimal = pos["monto_invertido"]  # type: ignore[assignment]
            mon = str(pos["moneda"])
            precio_c = pos.get("precio_compra")
            unidades = pos.get("unidades")
            fecha_c = pos.get("fecha_compra")
            fecha_txt = fecha_c.isoformat() if hasattr(fecha_c, "isoformat") else str(fecha_c or "")

            ctk.CTkLabel(
                fila,
                text=f"{sim}  •  {nom[:22]}  ({fecha_txt})",
                font=(FUENTE, 12, "bold"),
                text_color=COLORES["acento"],
            ).pack(side="left", padx=10, pady=6)

            det_txt = f"Invertido: {formatear_valor(monto, mon)}"
            if unidades is not None:
                det_txt += f"  |  {Decimal(str(unidades)).quantize(Decimal('0.0001'))} títulos"
            if precio_c is not None:
                det_txt += f" @ {formatear_valor(Decimal(str(precio_c)), mon)}"

            ctk.CTkLabel(
                fila,
                text=det_txt,
                font=(FUENTE, 11, "bold"),
                text_color=COLORES["texto"],
            ).pack(side="right", padx=10, pady=6)

    def _descargar_plantilla(self):
        ruta = filedialog.asksaveasfilename(
            title="Guardar plantilla CSV para inversiones",
            defaultextension=".csv",
            initialfile="plantilla_inversiones.csv",
            filetypes=[("Archivo CSV", "*.csv")],
            parent=self,
        )
        if not ruta:
            return
        try:
            self._gestor.exportar_plantilla_csv(ruta)
            messagebox.showinfo(
                "Plantilla guardada",
                f"Se guardó la plantilla de ejemplo en:\n{ruta}",
                parent=self,
            )
        except Exception as error:
            messagebox.showerror("Error", str(error), parent=self)

    def _ejecutar_importacion(self):
        if not self._posiciones_detectadas:
            return
        self._btn_confirmar.configure(text="⏳ Importando...", state="disabled")

        limpiar_prev = bool(self._var_reemplazar.get())
        omitir_dup = bool(self._var_sin_duplicados.get())

        def _tarea():
            try:
                importadas, omitidas = self._gestor.importar_inversiones_lote(
                    self._posiciones_detectadas,
                    limpiar_antes=limpiar_prev,
                    omitir_duplicados=omitir_dup,
                )
                if self.winfo_exists():
                    self.after(
                        0,
                        lambda: self._finalizar_exito(len(importadas), omitidas),
                    )
            except Exception as error:
                if self.winfo_exists():
                    self.after(
                        0,
                        lambda e=error: self._finalizar_error(e),
                    )

        threading.Thread(target=_tarea, daemon=True).start()

    def _finalizar_exito(self, cantidad: int, omitidas: int):
        if not self.winfo_exists():
            return
        cb = self._al_importar
        try:
            self.grab_release()
        except Exception:
            pass
        resumen = f"Se importaron {cantidad} posiciones al portafolio."
        if omitidas:
            resumen += f"\nSe omitieron {omitidas} duplicados (ya existían)."
        self.destroy()
        cb()
        if omitidas:
            messagebox.showinfo("Importación terminada", resumen)

    def _finalizar_error(self, error: Exception):
        """Restaura el botón y muestra el error sin cerrar el diálogo."""
        if not self.winfo_exists():
            return
        self._btn_confirmar.configure(
            state="normal", text="✅ Importar al portafolio")
        messagebox.showerror("Error al importar", str(error), parent=self)


class VistaInversiones(ctk.CTkFrame):
    """Módulo completo de Inversiones Bursátiles con buscador de tickers en vivo (sin lag de teclado),
    gráfica de rendimiento estilo montaña (formato eToro) con marcos 1D, 1W, 1M, 1Y,
    y portafolio dinámico en tiempo real."""

    def __init__(self, master, gestor: GestorFinanciero, **kwargs):
        super().__init__(master, fg_color=COLORES["fondo_contenido"], **kwargs)
        self._gestor = gestor
        self._moneda_vista = "COP"
        self._incluir_todas_convertidas = True
        self._marco_tiempo = "1M"
        self._simbolo_grafica: Optional[str] = None
        self._botones_timeframe: Dict[str, ctk.CTkButton] = {}
        self._botones_sugerencia: List[ctk.CTkButton] = []
        self._activos_sugeridos: List[Dict[str, str]] = []
        self._id_debounce_busqueda: Optional[str] = None
        self._secuencia_busqueda: int = 0
        self._puntos_montana_actuales: List[Tuple[str, Decimal]] = []
        self._coords_montana_px: List[Tuple[float, float, str, Decimal]] = []
        self._en_ganancia_montana: bool = True
        self._actualizando_en_segundo_plano: bool = False
        self._firma_estructura_posiciones = None
        self._widgets_grupos_simbolo: Dict[str, Dict[str, object]] = {}
        self._widgets_filas_operacion: Dict[int, Dict[str, object]] = {}

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
            width=205,
            height=38,
            corner_radius=10,
            fg_color=COLORES["acento"],
            hover_color=COLORES["acento_hover"],
            text_color=COLORES["campo_texto"],
            font=(FUENTE, 13, "bold"),
            command=self._forzar_actualizacion_precios,
        )
        self._btn_refrescar_vivo.pack(side="right")

        ctk.CTkButton(
            fila_sup,
            text="📥 Importar",
            width=245,
            height=38,
            corner_radius=10,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            border_width=1,
            border_color=COLORES["acento"],
            text_color=COLORES["texto"],
            font=(FUENTE, 13, "bold"),
            command=self._abrir_dialogo_importar,
        ).pack(side="right", padx=(0, 10))

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
        try:
            self._barra_moneda._var_modo.set("Todo convertido")
        except Exception:
            pass

        # ==================================================================
        # 3. BUSCADOR DE ACCIONES Y ETFs (QQQ, VOO, TTWO, AAPL, NVDA...)
        # ==================================================================
        tarjeta_buscador = ctk.CTkFrame(
            contenedor, fg_color=COLORES["fondo_tarjeta"], corner_radius=14
        )
        tarjeta_buscador.pack(fill="x", pady=(0, 14))

        fila_tit_busq = ctk.CTkFrame(tarjeta_buscador, fg_color="transparent")
        fila_tit_busq.pack(fill="x", padx=16, pady=(12, 4))

        ctk.CTkLabel(
            fila_tit_busq,
            text="🔎 Buscar acción, ETF o criptomoneda (escribe ej. Bitcoin, BTC, Solana, SOL, TTWO, QQQ, VOO y haz clic o Enter):",
            font=(FUENTE, 13, "bold"),
            text_color=COLORES["texto"],
        ).pack(side="left")

        fila_entrada_busq = ctk.CTkFrame(tarjeta_buscador, fg_color="transparent")
        fila_entrada_busq.pack(fill="x", padx=16, pady=(0, 8))

        self._campo_busqueda = ctk.CTkEntry(
            fila_entrada_busq,
            placeholder_text="Escribe acción, ETF o cripto (ej: Bitcoin / BTC, Solana / SOL, Ethereum / ETH, TTWO, QQQ, VOO, NVDA...)",
            fg_color=COLORES["campo_fondo"],
            text_color=COLORES["campo_texto"],
            font=(FUENTE, 13),
            height=38,
            corner_radius=8,
        )
        self._campo_busqueda.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._campo_busqueda.bind("<KeyRelease>", self._al_escribir_busqueda)
        self._campo_busqueda.bind("<Return>", lambda _e: self._abrir_primer_resultado_o_ticker_exacto())

        ctk.CTkButton(
            fila_entrada_busq,
            text="Invertir en ticker ↵",
            width=155,
            height=38,
            corner_radius=8,
            fg_color=COLORES["acento"],
            hover_color=COLORES["acento_hover"],
            text_color=COLORES["campo_texto"],
            font=(FUENTE, 12, "bold"),
            command=self._abrir_primer_resultado_o_ticker_exacto,
        ).pack(side="right")

        # Rejilla pre-construida de 8 botones (se reutilizan sin destruirlos para cero lag al escribir)
        self._rejilla_resultados = ctk.CTkFrame(
            tarjeta_buscador, fg_color="transparent"
        )
        self._rejilla_resultados.pack(fill="x", padx=14, pady=(0, 12))
        for c in range(4):
            self._rejilla_resultados.grid_columnconfigure(c, weight=1)

        for idx in range(TOTAL_BOTONES_SUGERENCIA):
            fila = idx // 4
            col = idx % 4
            btn = ctk.CTkButton(
                self._rejilla_resultados,
                text="",
                anchor="w",
                height=34,
                corner_radius=8,
                fg_color=COLORES["boton_lateral"],
                hover_color=COLORES["hover_lateral"],
                border_width=1,
                border_color=COLORES["boton_lateral"],
                text_color=COLORES["texto"],
                font=(FUENTE, 11, "bold"),
                command=lambda i=idx: self._al_clic_boton_sugerencia(i),
            )
            btn.grid(row=fila, column=col, sticky="ew", padx=4, pady=3)
            self._botones_sugerencia.append(btn)

        self._actualizar_botones_sugerencia(self._gestor.buscar_activos_bursatiles(""))

        # ==================================================================
        # 4. TARJETA CENTRAL: GRÁFICA DE RENDIMIENTO ESTILO MONTAÑA (formato eToro)
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
    # Buscador de Acciones y ETFs (Sin lag de teclado + búsqueda remota en Yahoo Finance)
    # ------------------------------------------------------------------
    def _al_escribir_busqueda(self, _evento=None):
        consulta = self._campo_busqueda.get().strip()
        # 1. Actualización local instantánea (< 1 ms, reutilizando botones existentes)
        resultados_locales = self._gestor.buscar_activos_bursatiles(consulta)
        self._actualizar_botones_sugerencia(resultados_locales, consulta)

        # 2. Debounce para búsqueda remota en Yahoo Finance (yf.Search) sin bloquear el teclado
        if self._id_debounce_busqueda is not None:
            try:
                self.after_cancel(self._id_debounce_busqueda)
            except Exception:
                pass
        if len(consulta) >= 2:
            self._id_debounce_busqueda = self.after(
                240, lambda q=consulta: self._buscar_remoto_yahoo_asincrono(q)
            )

    def _buscar_remoto_yahoo_asincrono(self, consulta: str):
        if not self.winfo_exists():
            return
        self._secuencia_busqueda += 1
        seq = self._secuencia_busqueda

        def _tarea():
            try:
                resultados = self._gestor.buscar_activos_bursatiles(
                    consulta, incluir_remoto=True
                )
            except TypeError:
                resultados = self._gestor.buscar_activos_bursatiles(consulta)
            if self.winfo_exists() and seq == self._secuencia_busqueda:
                texto_actual = self._campo_busqueda.get().strip()
                if texto_actual.upper() == consulta.upper():
                    self.after(
                        0, lambda: self._actualizar_botones_sugerencia(resultados, texto_actual)
                    )

        threading.Thread(target=_tarea, daemon=True).start()

    def _actualizar_botones_sugerencia(
        self, resultados: List[Dict[str, str]], consulta: str = ""
    ):
        self._activos_sugeridos = list(resultados[:TOTAL_BOTONES_SUGERENCIA])
        tiene_consulta = bool(consulta.strip())

        for idx, btn in enumerate(self._botones_sugerencia):
            if idx < len(self._activos_sugeridos):
                item = self._activos_sugeridos[idx]
                sim = item["simbolo"]
                nom = item["nombre"]
                nombre_corto = nom if len(nom) <= 24 else nom[:22] + "…"
                btn.configure(
                    text=f"📈 {sim}  •  {nombre_corto}",
                    border_color=COLORES["acento"] if (idx == 0 and tiene_consulta) else COLORES["boton_lateral"],
                )
                btn.grid()
            else:
                btn.grid_remove()

    def _al_clic_boton_sugerencia(self, indice: int):
        # Si el usuario escribió un ticker completo en la caja (ej. 'TTWO') y presionó el botón
        # de consulta directa que tenía un prefijo parcial, usar siempre el texto completo actual
        if indice >= len(self._activos_sugeridos):
            return
        elegido = dict(self._activos_sugeridos[indice])
        texto_caja = self._campo_busqueda.get().strip().upper()
        if (
            "Consultar en Yahoo Finance" in elegido.get("nombre", "")
            and texto_caja
            and all(ch.isalnum() or ch in ("-", ".") for ch in texto_caja)
        ):
            coincidencias_actuales = self._gestor.buscar_activos_bursatiles(texto_caja)
            if coincidencias_actuales:
                elegido = dict(coincidencias_actuales[0])
        self._abrir_modal_asignar(elegido)

    def _abrir_primer_resultado_o_ticker_exacto(self):
        texto = self._campo_busqueda.get().strip()
        if not texto:
            if self._activos_sugeridos:
                self._abrir_modal_asignar(self._activos_sugeridos[0])
            return
        resultados = self._gestor.buscar_activos_bursatiles(texto)
        if resultados:
            self._abrir_modal_asignar(resultados[0])

    def _abrir_dialogo_importar(self):
        """Abre el menú para elegir la plataforma de importación."""
        DialogoElegirBroker(
            self,
            gestor=self._gestor,
            al_importar=self.refrescar,
        )

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
        if self._actualizando_en_segundo_plano:
            return
        self._actualizando_en_segundo_plano = True
        self._btn_refrescar_vivo.configure(text="⏳ Actualizando...", state="disabled")
        mon = self._moneda_vista
        inc = self._incluir_todas_convertidas
        tf = self._marco_tiempo
        sim = self._simbolo_grafica

        def _tarea():
            resumen_vivo = None
            curva_viva = None
            try:
                try:
                    resumen_vivo = self._gestor.valorar_portafolio(
                        moneda_objetivo=mon,
                        incluir_todas_convertidas=inc,
                        forzar_actualizacion=True,
                        permitir_red=True,
                    )
                except TypeError:
                    resumen_vivo = self._gestor.valorar_portafolio(
                        moneda_objetivo=mon,
                        incluir_todas_convertidas=inc,
                        forzar_actualizacion=True,
                    )
                try:
                    curva_viva = self._gestor.obtener_serie_montana_portafolio(
                        marco_tiempo=tf,
                        simbolo_filtro=sim,
                        moneda_objetivo=mon,
                        incluir_todas_convertidas=inc,
                        valoracion_precalculada=resumen_vivo,
                        forzar_actualizacion=True,
                        permitir_red=True,
                    )
                except TypeError:
                    curva_viva = self._gestor.obtener_serie_montana_portafolio(
                        marco_tiempo=tf,
                        simbolo_filtro=sim,
                        moneda_objetivo=mon,
                        incluir_todas_convertidas=inc,
                    )
            finally:
                self._actualizando_en_segundo_plano = False
                if self.winfo_exists():
                    self.after(
                        0,
                        lambda: self._al_terminar_actualizacion_forzada(
                            resumen_vivo, curva_viva, mon
                        ),
                    )

        threading.Thread(target=_tarea, daemon=True).start()

    def _al_terminar_actualizacion_forzada(
        self,
        resumen_vivo: Optional[Dict[str, object]],
        curva_viva: Optional[Dict[str, object]],
        moneda: str,
    ):
        if not self.winfo_exists():
            return
        self._btn_refrescar_vivo.configure(
            text="🔄 Actualizar precios en vivo", state="normal"
        )
        if resumen_vivo is not None:
            self._aplicar_resumen_en_ui(resumen_vivo, moneda)
        if curva_viva is not None:
            self._dibujar_grafica_montana(curva_viva)

    def _actualizar_encabezado_kpi(self, resumen: Dict[str, object], moneda: str):
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

    def _aplicar_resumen_en_ui(self, resumen: Dict[str, object], moneda: str):
        posiciones: List[ValoracionInversion] = resumen["posiciones"]  # type: ignore[assignment]
        self._actualizar_encabezado_kpi(resumen, moneda)
        self._renderizar_lista_posiciones(posiciones, moneda)

    def refrescar(self):
        """Renderiza instantáneamente en 0ms usando precios en memoria/caché sin bloquear el hilo principal,
        y si algún activo aún no tiene cotización viva en sesión, la descarga en segundo plano."""
        moneda = self._moneda_vista
        try:
            resumen_rapido = self._gestor.valorar_portafolio(
                moneda_objetivo=moneda,
                incluir_todas_convertidas=self._incluir_todas_convertidas,
                forzar_actualizacion=False,
                permitir_red=False,
            )
        except TypeError:
            resumen_rapido = self._gestor.valorar_portafolio(
                moneda_objetivo=moneda,
                incluir_todas_convertidas=self._incluir_todas_convertidas,
                forzar_actualizacion=False,
            )

        self._aplicar_resumen_en_ui(resumen_rapido, moneda)

        # Dibujar gráfica inmediata con caché disponible (0ms)
        try:
            curva_rapida = self._gestor.obtener_serie_montana_portafolio(
                marco_tiempo=self._marco_tiempo,
                simbolo_filtro=self._simbolo_grafica,
                moneda_objetivo=moneda,
                incluir_todas_convertidas=self._incluir_todas_convertidas,
                valoracion_precalculada=resumen_rapido,
                forzar_actualizacion=False,
                permitir_red=False,
            )
            self._dibujar_grafica_montana(curva_rapida)
        except TypeError:
            pass

        # Si faltan precios vivos o series históricas en sesión, actualizarlos en segundo plano sin congelar la UI
        if resumen_rapido.get("faltan_precios_vivos"):
            self._forzar_actualizacion_en_fondo_suave()
        else:
            self._cargar_curva_montana_asincrona(resumen_precalculado=resumen_rapido)

    def _forzar_actualizacion_en_fondo_suave(self):
        if self._actualizando_en_segundo_plano:
            return
        self._actualizando_en_segundo_plano = True
        self._btn_refrescar_vivo.configure(text="⏳ Sincronizando...", state="disabled")
        mon = self._moneda_vista
        inc = self._incluir_todas_convertidas
        tf = self._marco_tiempo
        sim = self._simbolo_grafica

        def _tarea():
            resumen_vivo = None
            curva_viva = None
            try:
                try:
                    resumen_vivo = self._gestor.valorar_portafolio(
                        moneda_objetivo=mon,
                        incluir_todas_convertidas=inc,
                        forzar_actualizacion=False,
                        permitir_red=True,
                    )
                    curva_viva = self._gestor.obtener_serie_montana_portafolio(
                        marco_tiempo=tf,
                        simbolo_filtro=sim,
                        moneda_objetivo=mon,
                        incluir_todas_convertidas=inc,
                        valoracion_precalculada=resumen_vivo,
                        forzar_actualizacion=False,
                        permitir_red=True,
                    )
                except TypeError:
                    resumen_vivo = self._gestor.valorar_portafolio(
                        moneda_objetivo=mon,
                        incluir_todas_convertidas=inc,
                        forzar_actualizacion=False,
                    )
            finally:
                self._actualizando_en_segundo_plano = False
                if self.winfo_exists():
                    self.after(
                        0,
                        lambda: self._al_terminar_actualizacion_forzada(
                            resumen_vivo, curva_viva, mon
                        ),
                    )

        threading.Thread(target=_tarea, daemon=True).start()

    # ------------------------------------------------------------------
    # Gráfica Estilo Montaña (formato eToro) con Área Degradada
    # ------------------------------------------------------------------
    def _cargar_curva_montana_asincrona(
        self, resumen_precalculado: Optional[Dict[str, object]] = None
    ):
        tf = self._marco_tiempo
        sim = self._simbolo_grafica
        mon = self._moneda_vista
        inc = self._incluir_todas_convertidas

        def _tarea():
            try:
                datos_curva = self._gestor.obtener_serie_montana_portafolio(
                    marco_tiempo=tf,
                    simbolo_filtro=sim,
                    moneda_objetivo=mon,
                    incluir_todas_convertidas=inc,
                    valoracion_precalculada=resumen_precalculado,
                    forzar_actualizacion=False,
                    permitir_red=True,
                )
            except TypeError:
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
                text="Aún no tienes inversiones registradas.\nBusca un activo arriba (ej. TTWO, QQQ, VOO, AAPL) y haz clic para añadir fondos.",
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

        if en_ganancia:
            color_linea = "#7DC98F"
            bandas_relleno = ("#255440", "#1E4434", "#18372A")
        else:
            color_linea = "#F28C8C"
            bandas_relleno = ("#522931", "#3E2128", "#2E1B21")

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

        n = len(puntos)
        coords_curva: List[Tuple[float, float]] = []
        for idx, (etiqueta, valor_dec) in enumerate(puntos):
            x = margen_izq + (idx / max(1, n - 1)) * ancho_util
            norm = (float(valor_dec) - v_min) / rango_v
            y = (y_base - 8) - norm * (alto_util - 16)
            coords_curva.append((x, y))
            self._coords_montana_px.append((x, y, etiqueta, valor_dec))

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

        x_ult, y_ult = coords_curva[-1]
        self._lienzo_montana.create_oval(
            x_ult - 6, y_ult - 6, x_ult + 6, y_ult + 6,
            fill=color_linea, outline=COLORES["fondo_tarjeta"], width=2
        )

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
        grupos_por_simbolo: Dict[str, List[ValoracionInversion]] = {}
        for val in posiciones:
            grupos_por_simbolo.setdefault(val.inversion.simbolo, []).append(val)

        firma_nueva = (
            moneda_vista,
            self._simbolo_grafica,
            tuple(
                (sim, tuple(v.inversion.id for v in vals))
                for sim, vals in grupos_por_simbolo.items()
            ),
        )

        # Si la estructura de posiciones es idéntica (ej. al actualizar precios en vivo),
        # actualizar únicamente los textos de las etiquetas existentes en <2ms sin destruir widgets
        if (
            self._firma_estructura_posiciones == firma_nueva
            and posiciones
            and self._widgets_grupos_simbolo
        ):
            self._actualizar_textos_posiciones_in_place(grupos_por_simbolo, moneda_vista)
            return

        self._firma_estructura_posiciones = firma_nueva
        self._widgets_grupos_simbolo.clear()
        self._widgets_filas_operacion.clear()
        for hijo in self._contenedor_posiciones.winfo_children():
            hijo.destroy()

        if not posiciones:
            ctk.CTkLabel(
                self._contenedor_posiciones,
                text="Tu portafolio está vacío. Usa el buscador superior o importa tu Estado de Cuenta de eToro (.xlsx).",
                font=(FUENTE, 13),
                text_color=COLORES["texto_secundario"],
            ).pack(pady=28)
            return

        for simbolo, lista_vals in grupos_por_simbolo.items():
            seleccionada = self._simbolo_grafica == simbolo
            inv_ref = lista_vals[0].inversion
            total_inv_grupo = sum((v.monto_invertido_convertido for v in lista_vals), Decimal("0"))
            total_act_grupo = sum((v.valor_actual_convertido for v in lista_vals), Decimal("0"))
            total_pnl_grupo = total_act_grupo - total_inv_grupo
            total_titulos = sum((v.inversion.cantidad_titulos for v in lista_vals), Decimal("0"))
            pct_grupo = (
                ((total_pnl_grupo / total_inv_grupo) * Decimal("100")).quantize(Decimal("0.01"))
                if total_inv_grupo > Decimal("0")
                else Decimal("0.00")
            )
            en_gan_grupo = total_pnl_grupo >= Decimal("0")

            marco_grupo = ctk.CTkFrame(
                self._contenedor_posiciones,
                fg_color=COLORES["boton_lateral"],
                corner_radius=10,
                border_width=2 if seleccionada else 0,
                border_color=COLORES["acento"],
            )
            marco_grupo.pack(fill="x", pady=5)

            cab_grupo = ctk.CTkFrame(marco_grupo, fg_color="transparent")
            cab_grupo.pack(fill="x", padx=12, pady=(8, 4))

            btn_ticker = ctk.CTkButton(
                cab_grupo,
                text=simbolo,
                width=70,
                height=38,
                corner_radius=8,
                fg_color=COLORES["acento"] if seleccionada else COLORES["fondo_tarjeta"],
                hover_color=COLORES["acento_hover"],
                text_color=COLORES["campo_texto"] if seleccionada else COLORES["acento"],
                font=(FUENTE, 13, "bold"),
                command=lambda s=simbolo: self._filtrar_grafica_por_simbolo(s),
            )
            btn_ticker.pack(side="left", padx=(0, 10))

            col_tit = ctk.CTkFrame(cab_grupo, fg_color="transparent")
            col_tit.pack(side="left", fill="x", expand=True)

            etiqueta_ops = (
                f"{len(lista_vals)} operaciones abiertas"
                if len(lista_vals) > 1
                else "1 operación abierta"
            )
            lbl_subtitulo = ctk.CTkLabel(
                col_tit,
                text=f"{inv_ref.nombre}  •  {etiqueta_ops} ({total_titulos.quantize(Decimal('0.0001'))} títulos totales)",
                font=(FUENTE, 13, "bold"),
                text_color=COLORES["texto"],
            )
            lbl_subtitulo.pack(anchor="w")

            lbl_precio_inv = ctk.CTkLabel(
                col_tit,
                text=(
                    f"Precio mercado actual: {formatear_valor(lista_vals[0].precio_actual, inv_ref.moneda)}   •   "
                    f"Total invertido en {simbolo}: {formatear_valor(total_inv_grupo, moneda_vista)}"
                ),
                font=(FUENTE, 11),
                text_color=COLORES["texto_secundario"],
            )
            lbl_precio_inv.pack(anchor="w")

            col_tot_der = ctk.CTkFrame(cab_grupo, fg_color="transparent")
            col_tot_der.pack(side="right", padx=6)

            lbl_total_act = ctk.CTkLabel(
                col_tot_der,
                text=formatear_valor(total_act_grupo, moneda_vista),
                font=(FUENTE, 14, "bold"),
                text_color=COLORES["texto"],
            )
            lbl_total_act.pack(anchor="e")

            fl_g = "▲" if en_gan_grupo else "▼"
            sg_g = "+" if en_gan_grupo else "-"
            col_pnl_g = COLORES["exito"] if en_gan_grupo else COLORES["error"]
            lbl_total_pnl = ctk.CTkLabel(
                col_tot_der,
                text=(
                    f"{fl_g} {sg_g}{formatear_valor(abs(total_pnl_grupo), moneda_vista)} "
                    f"({sg_g}{abs(pct_grupo):.2f}%)"
                ),
                font=(FUENTE, 11, "bold"),
                text_color=col_pnl_g,
            )
            lbl_total_pnl.pack(anchor="e")

            self._widgets_grupos_simbolo[simbolo] = {
                "marco_grupo": marco_grupo,
                "lbl_subtitulo": lbl_subtitulo,
                "lbl_precio_inv": lbl_precio_inv,
                "lbl_total_act": lbl_total_act,
                "lbl_total_pnl": lbl_total_pnl,
            }

            for idx_op, val in enumerate(lista_vals, start=1):
                inv = val.inversion
                fila_op = ctk.CTkFrame(
                    marco_grupo,
                    fg_color=COLORES["fondo_tarjeta"],
                    corner_radius=8,
                )
                fila_op.pack(fill="x", padx=12, pady=(2, 5))

                nota_id = f"  •  {inv.notas}" if inv.notas else ""
                texto_izq_op = (
                    f"#{idx_op}  📅 {inv.fecha_compra.isoformat()}   •   "
                    f"Invertido: {formatear_valor(inv.monto_invertido, inv.moneda)}"
                )
                if inv.moneda != moneda_vista:
                    texto_izq_op += f" ({formatear_valor(val.monto_invertido_convertido, moneda_vista)})"
                texto_izq_op += (
                    f"   •   {inv.cantidad_titulos.quantize(Decimal('0.0001'))} títulos "
                    f"@ {formatear_valor(inv.precio_compra, inv.moneda)}{nota_id}"
                )

                lbl_izq_op = ctk.CTkLabel(
                    fila_op,
                    text=texto_izq_op,
                    font=(FUENTE, 11),
                    text_color=COLORES["texto"],
                )
                lbl_izq_op.pack(side="left", padx=10, pady=5)

                ctk.CTkButton(
                    fila_op,
                    text="✕",
                    width=28,
                    height=24,
                    corner_radius=6,
                    fg_color="transparent",
                    hover_color=COLORES["hover_lateral"],
                    text_color=COLORES["error"],
                    font=(FUENTE, 11, "bold"),
                    command=lambda iid=inv.id, sim_k=simbolo: self._confirmar_eliminar_inversion(iid, sim_k),
                ).pack(side="right", padx=(4, 8), pady=4)

                fl = "▲" if val.en_ganancia else "▼"
                sg = "+" if val.en_ganancia else "-"
                col_p = COLORES["exito"] if val.en_ganancia else COLORES["error"]
                lbl_der_op = ctk.CTkLabel(
                    fila_op,
                    text=(
                        f"Actual: {formatear_valor(val.valor_actual_convertido, moneda_vista)}  "
                        f"({fl} {sg}{formatear_valor(abs(val.ganancia_perdida_convertida), moneda_vista)} | "
                        f"{sg}{abs(val.rendimiento_porcentaje):.2f}%)"
                    ),
                    font=(FUENTE, 11, "bold"),
                    text_color=col_p,
                )
                lbl_der_op.pack(side="right", padx=8, pady=5)

                if inv.id is not None:
                    self._widgets_filas_operacion[inv.id] = {
                        "fila_op": fila_op,
                        "lbl_izq_op": lbl_izq_op,
                        "lbl_der_op": lbl_der_op,
                        "simbolo": simbolo,
                    }

    def _actualizar_textos_posiciones_in_place(
        self,
        grupos_por_simbolo: Dict[str, List[ValoracionInversion]],
        moneda_vista: str,
    ):
        """Actualiza los textos y colores de cada grupo y fila de operación sin destruir ningún widget."""
        for simbolo, lista_vals in grupos_por_simbolo.items():
            w_grupo = self._widgets_grupos_simbolo.get(simbolo)
            if not w_grupo:
                continue
            inv_ref = lista_vals[0].inversion
            total_inv_grupo = sum((v.monto_invertido_convertido for v in lista_vals), Decimal("0"))
            total_act_grupo = sum((v.valor_actual_convertido for v in lista_vals), Decimal("0"))
            total_pnl_grupo = total_act_grupo - total_inv_grupo
            total_titulos = sum((v.inversion.cantidad_titulos for v in lista_vals), Decimal("0"))
            pct_grupo = (
                ((total_pnl_grupo / total_inv_grupo) * Decimal("100")).quantize(Decimal("0.01"))
                if total_inv_grupo > Decimal("0")
                else Decimal("0.00")
            )
            en_gan_grupo = total_pnl_grupo >= Decimal("0")
            etiqueta_ops = (
                f"{len(lista_vals)} operaciones abiertas"
                if len(lista_vals) > 1
                else "1 operación abierta"
            )
            w_grupo["lbl_subtitulo"].configure(  # type: ignore[union-attr]
                text=f"{inv_ref.nombre}  •  {etiqueta_ops} ({total_titulos.quantize(Decimal('0.0001'))} títulos totales)"
            )
            w_grupo["lbl_precio_inv"].configure(  # type: ignore[union-attr]
                text=(
                    f"Precio mercado actual: {formatear_valor(lista_vals[0].precio_actual, inv_ref.moneda)}   •   "
                    f"Total invertido en {simbolo}: {formatear_valor(total_inv_grupo, moneda_vista)}"
                )
            )
            w_grupo["lbl_total_act"].configure(  # type: ignore[union-attr]
                text=formatear_valor(total_act_grupo, moneda_vista)
            )
            fl_g = "▲" if en_gan_grupo else "▼"
            sg_g = "+" if en_gan_grupo else "-"
            col_pnl_g = COLORES["exito"] if en_gan_grupo else COLORES["error"]
            w_grupo["lbl_total_pnl"].configure(  # type: ignore[union-attr]
                text=(
                    f"{fl_g} {sg_g}{formatear_valor(abs(total_pnl_grupo), moneda_vista)} "
                    f"({sg_g}{abs(pct_grupo):.2f}%)"
                ),
                text_color=col_pnl_g,
            )

            for idx_op, val in enumerate(lista_vals, start=1):
                inv = val.inversion
                if inv.id is None or inv.id not in self._widgets_filas_operacion:
                    continue
                w_fila = self._widgets_filas_operacion[inv.id]
                nota_id = f"  •  {inv.notas}" if inv.notas else ""
                texto_izq_op = (
                    f"#{idx_op}  📅 {inv.fecha_compra.isoformat()}   •   "
                    f"Invertido: {formatear_valor(inv.monto_invertido, inv.moneda)}"
                )
                if inv.moneda != moneda_vista:
                    texto_izq_op += f" ({formatear_valor(val.monto_invertido_convertido, moneda_vista)})"
                texto_izq_op += (
                    f"   •   {inv.cantidad_titulos.quantize(Decimal('0.0001'))} títulos "
                    f"@ {formatear_valor(inv.precio_compra, inv.moneda)}{nota_id}"
                )
                w_fila["lbl_izq_op"].configure(text=texto_izq_op)  # type: ignore[union-attr]

                fl = "▲" if val.en_ganancia else "▼"
                sg = "+" if val.en_ganancia else "-"
                col_p = COLORES["exito"] if val.en_ganancia else COLORES["error"]
                w_fila["lbl_der_op"].configure(  # type: ignore[union-attr]
                    text=(
                        f"Actual: {formatear_valor(val.valor_actual_convertido, moneda_vista)}  "
                        f"({fl} {sg}{formatear_valor(abs(val.ganancia_perdida_convertida), moneda_vista)} | "
                        f"{sg}{abs(val.rendimiento_porcentaje):.2f}%)"
                    ),
                    text_color=col_p,
                )

    def _abrir_dialogo_cerrar_inversion(
        self, val_op: ValoracionInversion, simbolo_grupo: Optional[str] = None
    ):
        inv = val_op.inversion
        if inv.id is None:
            return

        def _al_vender(resultado: Dict[str, object]) -> None:
            id_inv = inv.id
            info_fila = self._widgets_filas_operacion.pop(id_inv, None) if id_inv is not None else None
            if info_fila is not None:
                try:
                    info_fila["fila_op"].destroy()  # type: ignore[union-attr]
                except Exception:
                    pass

            moneda = self._moneda_vista
            try:
                resumen = self._gestor.valorar_portafolio(
                    moneda_objetivo=moneda,
                    incluir_todas_convertidas=self._incluir_todas_convertidas,
                    forzar_actualizacion=False,
                    permitir_red=False,
                )
            except TypeError:
                resumen = self._gestor.valorar_portafolio(
                    moneda_objetivo=moneda,
                    incluir_todas_convertidas=self._incluir_todas_convertidas,
                    forzar_actualizacion=False,
                )

            posiciones: List[ValoracionInversion] = resumen["posiciones"]  # type: ignore[assignment]
            grupos_por_simbolo: Dict[str, List[ValoracionInversion]] = {}
            for val in posiciones:
                grupos_por_simbolo.setdefault(val.inversion.simbolo, []).append(val)

            sim_verificar = simbolo_grupo or (str(info_fila["simbolo"]) if info_fila else "")
            if sim_verificar and sim_verificar not in grupos_por_simbolo:
                w_grp = self._widgets_grupos_simbolo.pop(sim_verificar, None)
                if w_grp is not None:
                    try:
                        w_grp["marco_grupo"].destroy()  # type: ignore[union-attr]
                    except Exception:
                        pass
                if self._simbolo_grafica == sim_verificar:
                    self._simbolo_grafica = None

            self._firma_estructura_posiciones = (
                moneda,
                self._simbolo_grafica,
                tuple(
                    (sim, tuple(v.inversion.id for v in vals))
                    for sim, vals in grupos_por_simbolo.items()
                ),
            )
            self._actualizar_encabezado_kpi(resumen, moneda)
            if not posiciones:
                self._renderizar_lista_posiciones([], moneda)
            else:
                self._actualizar_textos_posiciones_in_place(grupos_por_simbolo, moneda)

            try:
                curva = self._gestor.obtener_serie_montana_portafolio(
                    marco_tiempo=self._marco_tiempo,
                    simbolo_filtro=self._simbolo_grafica,
                    moneda_objetivo=moneda,
                    incluir_todas_convertidas=self._incluir_todas_convertidas,
                    valoracion_precalculada=resumen,
                    forzar_actualizacion=False,
                    permitir_red=False,
                )
                self._dibujar_grafica_montana(curva)
            except TypeError:
                self._cargar_curva_montana_asincrona(resumen_precalculado=resumen)

        DialogoCerrarInversion(
            self,
            gestor=self._gestor,
            valoracion=val_op,
            moneda_vista=self._moneda_vista,
            al_confirmar=_al_vender,
        )

    def _confirmar_eliminar_inversion(
        self, id_inversion: Optional[int], simbolo_grupo: Optional[str] = None
    ):
        if id_inversion is None:
            return
        if not messagebox.askyesno(
            "Eliminar inversión",
            "¿Deseas eliminar esta posición del portafolio?",
            parent=self,
        ):
            return

        # 1. Eliminar en memoria inmediatamente y destruir ÚNICAMENTE la fila eliminada (0ms, sin parpadeo)
        info_fila = self._widgets_filas_operacion.pop(id_inversion, None)
        if info_fila is not None:
            try:
                info_fila["fila_op"].destroy()  # type: ignore[union-attr]
            except Exception:
                pass

        self._gestor.eliminar_inversion(id_inversion)

        # 2. Recalcular totales en memoria (<1ms, sin llamadas de red) y actualizar cabeceras in-place
        moneda = self._moneda_vista
        try:
            resumen = self._gestor.valorar_portafolio(
                moneda_objetivo=moneda,
                incluir_todas_convertidas=self._incluir_todas_convertidas,
                forzar_actualizacion=False,
                permitir_red=False,
            )
        except TypeError:
            resumen = self._gestor.valorar_portafolio(
                moneda_objetivo=moneda,
                incluir_todas_convertidas=self._incluir_todas_convertidas,
                forzar_actualizacion=False,
            )

        posiciones: List[ValoracionInversion] = resumen["posiciones"]  # type: ignore[assignment]
        grupos_por_simbolo: Dict[str, List[ValoracionInversion]] = {}
        for val in posiciones:
            grupos_por_simbolo.setdefault(val.inversion.simbolo, []).append(val)

        # Si el símbolo ya no tiene más operaciones abiertas, remover su tarjeta de grupo
        sim_verificar = simbolo_grupo or (str(info_fila["simbolo"]) if info_fila else "")
        if sim_verificar and sim_verificar not in grupos_por_simbolo:
            w_grp = self._widgets_grupos_simbolo.pop(sim_verificar, None)
            if w_grp is not None:
                try:
                    w_grp["marco_grupo"].destroy()  # type: ignore[union-attr]
                except Exception:
                    pass
            if self._simbolo_grafica == sim_verificar:
                self._simbolo_grafica = None

        self._firma_estructura_posiciones = (
            moneda,
            self._simbolo_grafica,
            tuple(
                (sim, tuple(v.inversion.id for v in vals))
                for sim, vals in grupos_por_simbolo.items()
            ),
        )

        self._actualizar_encabezado_kpi(resumen, moneda)
        if not posiciones:
            self._renderizar_lista_posiciones([], moneda)
        else:
            self._actualizar_textos_posiciones_in_place(grupos_por_simbolo, moneda)

        # Actualizar curva montaña instantáneamente desde las series ya en caché
        try:
            curva = self._gestor.obtener_serie_montana_portafolio(
                marco_tiempo=self._marco_tiempo,
                simbolo_filtro=self._simbolo_grafica,
                moneda_objetivo=moneda,
                incluir_todas_convertidas=self._incluir_todas_convertidas,
                valoracion_precalculada=resumen,
                forzar_actualizacion=False,
                permitir_red=False,
            )
            self._dibujar_grafica_montana(curva)
        except TypeError:
            self._cargar_curva_montana_asincrona(resumen_precalculado=resumen)


def _abreviar_cifra(valor: Decimal) -> str:
    v = abs(float(valor))
    if v >= 1_000_000_000:
        return f"{v / 1_000_000_000:.1f}B"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if v >= 10_000:
        return f"{v / 1_000:.1f}k"
    return f"{v:,.0f}"


class DialogoCerrarInversion(ctk.CTkToplevel):
    """Modal para vender/cerrar una posición de inversión y acreditar los fondos en una cuenta."""

    def __init__(
        self,
        master,
        gestor,
        valoracion: ValoracionInversion,
        moneda_vista: str = "COP",
        al_confirmar: Optional[Callable[[Dict[str, object]], None]] = None,
    ):
        super().__init__(master)
        self._gestor = gestor
        self._val = valoracion
        self._inv = valoracion.inversion
        self._moneda_vista = moneda_vista
        self._al_confirmar = al_confirmar

        self.title(f"Vender / Cerrar posición — {self._inv.simbolo}")
        self.geometry("480x440")
        self.resizable(False, False)
        self.configure(fg_color=COLORES["fondo_principal"])
        self.transient(master)
        self.grab_set()

        # Detectar broker sugerido desde las notas de la inversión (por defecto eToro)
        broker_sugerido = "eToro"
        notas_low = (self._inv.notas or "").lower()
        for cand_key, cand_nom in (
            ("binance", "Binance"),
            ("interactive brokers", "Interactive Brokers"),
            ("ibkr", "Interactive Brokers"),
            ("trii", "Trii"),
            ("hapi", "Hapi"),
            ("etoro", "eToro"),
        ):
            if cand_key in notas_low:
                broker_sugerido = cand_nom
                break

        try:
            self._gestor.asegurar_cuenta_broker(broker_sugerido, moneda=self._inv.moneda)
        except Exception:
            pass

        self._cuentas_disponibles = []
        try:
            self._cuentas_disponibles = list(self._gestor.obtener_cuentas())
        except Exception:
            self._cuentas_disponibles = []

        self._mapa_opciones_cuenta: Dict[str, Optional[int]] = {}
        opciones_menu: List[str] = []
        opcion_predeterminada: Optional[str] = None

        for cuenta_obj, saldo_actual in self._cuentas_disponibles:
            etiqueta = f"{cuenta_obj.nombre} ({cuenta_obj.moneda}) — Saldo: {formatear_valor(saldo_actual, cuenta_obj.moneda)}"
            self._mapa_opciones_cuenta[etiqueta] = cuenta_obj.id
            opciones_menu.append(etiqueta)
            if cuenta_obj.nombre.strip().lower() == broker_sugerido.lower():
                opcion_predeterminada = etiqueta

        etiqueta_ninguna = "No enviar a ninguna cuenta (solo cerrar posición)"
        self._mapa_opciones_cuenta[etiqueta_ninguna] = None
        opciones_menu.append(etiqueta_ninguna)
        if opcion_predeterminada is None and opciones_menu:
            opcion_predeterminada = opciones_menu[0]

        # Valor de venta actual en la moneda nativa de la inversión
        if (
            getattr(valoracion, "precio_mercado_actual", None) is not None
            and valoracion.precio_mercado_actual > Decimal("0")
            and self._inv.cantidad_titulos > Decimal("0")
        ):
            self._valor_mercado_nativo = (
                self._inv.cantidad_titulos * valoracion.precio_mercado_actual
            ).quantize(Decimal("0.01"))
        else:
            self._valor_mercado_nativo = self._inv.monto_invertido.quantize(Decimal("0.01"))

        pnl_nativo = self._valor_mercado_nativo - self._inv.monto_invertido
        signo_pnl = "+" if pnl_nativo >= Decimal("0") else "-"
        color_pnl = COLORES["exito"] if pnl_nativo >= Decimal("0") else COLORES["error"]

        marco = ctk.CTkFrame(self, fg_color=COLORES["fondo_tarjeta"], corner_radius=12)
        marco.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            marco,
            text=f"💰 Vender posición: {self._inv.simbolo}",
            font=(FUENTE, 16, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w", padx=16, pady=(14, 4))

        ctk.CTkLabel(
            marco,
            text=(
                f"{self._inv.nombre}  •  {self._inv.cantidad_titulos.quantize(Decimal('0.0001'))} títulos\n"
                f"Invertido originalmente: {formatear_valor(self._inv.monto_invertido, self._inv.moneda)}"
            ),
            font=(FUENTE, 12),
            text_color=COLORES["texto_secundario"],
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 8))

        ctk.CTkLabel(
            marco,
            text=(
                f"Valor actual de mercado: {formatear_valor(self._valor_mercado_nativo, self._inv.moneda)} "
                f"({signo_pnl}{formatear_valor(abs(pnl_nativo), self._inv.moneda)})"
            ),
            font=(FUENTE, 13, "bold"),
            text_color=color_pnl,
        ).pack(anchor="w", padx=16, pady=(0, 12))

        ctk.CTkLabel(
            marco,
            text=f"Valor total de venta ({self._inv.moneda}):",
            font=(FUENTE, 12, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w", padx=16, pady=(4, 2))

        self._campo_valor_venta = ctk.CTkEntry(
            marco,
            height=34,
            fg_color=COLORES["campo_fondo"],
            text_color=COLORES["campo_texto"],
            font=(FUENTE, 12),
        )
        self._campo_valor_venta.pack(fill="x", padx=16, pady=(0, 10))
        self._campo_valor_venta.insert(0, f"{self._valor_mercado_nativo:.2f}")
        self._campo_valor_venta.bind("<KeyRelease>", lambda _e: self._actualizar_preview_conversion())

        ctk.CTkLabel(
            marco,
            text="Enviar fondos de la venta a la cuenta:",
            font=(FUENTE, 12, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w", padx=16, pady=(4, 2))

        self._selector_cuenta = ctk.CTkOptionMenu(
            marco,
            values=opciones_menu,
            height=34,
            fg_color=COLORES["boton_lateral"],
            button_color=COLORES["acento"],
            button_hover_color=COLORES["acento_hover"],
            text_color=COLORES["texto"],
            font=(FUENTE, 12),
            command=lambda _val: self._actualizar_preview_conversion(),
        )
        self._selector_cuenta.pack(fill="x", padx=16, pady=(0, 8))
        if opcion_predeterminada:
            self._selector_cuenta.set(opcion_predeterminada)

        self._lbl_preview = ctk.CTkLabel(
            marco,
            text="",
            font=(FUENTE, 12, "bold"),
            text_color=COLORES["acento"],
        )
        self._lbl_preview.pack(anchor="w", padx=16, pady=(2, 12))

        fila_botones = ctk.CTkFrame(marco, fg_color="transparent")
        fila_botones.pack(fill="x", padx=16, pady=(8, 14))

        ctk.CTkButton(
            fila_botones,
            text="Cancelar",
            width=120,
            height=34,
            corner_radius=8,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 12, "bold"),
            command=self.destroy,
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            fila_botones,
            text="Confirmar venta",
            width=150,
            height=34,
            corner_radius=8,
            fg_color=COLORES["exito"],
            hover_color=COLORES["acento_hover"],
            text_color="#FFFFFF",
            font=(FUENTE, 12, "bold"),
            command=self._confirmar,
        ).pack(side="right")

        self._actualizar_preview_conversion()

    def _obtener_monto_ingresado(self) -> Decimal:
        texto = (self._campo_valor_venta.get() or "").strip().replace(",", ".")
        try:
            val = Decimal(texto)
            if val > Decimal("0"):
                return val.quantize(Decimal("0.01"))
        except Exception:
            pass
        return self._valor_mercado_nativo

    def _actualizar_preview_conversion(self) -> None:
        monto_origen = self._obtener_monto_ingresado()
        seleccion = self._selector_cuenta.get()
        id_cuenta = self._mapa_opciones_cuenta.get(seleccion)
        if id_cuenta is None:
            self._lbl_preview.configure(
                text="La posición se cerrará sin acreditar fondos en ninguna cuenta."
            )
            return

        cuenta_dest = None
        for c_obj, _s in self._cuentas_disponibles:
            if c_obj.id == id_cuenta:
                cuenta_dest = c_obj
                break
        if cuenta_dest is None:
            return

        if cuenta_dest.moneda != self._inv.moneda:
            try:
                convertido = self._gestor.convertir_entre_monedas(
                    monto_origen, self._inv.moneda, cuenta_dest.moneda
                )
                self._lbl_preview.configure(
                    text=f"Se acreditarán: {formatear_valor(convertido, cuenta_dest.moneda)} en '{cuenta_dest.nombre}'"
                )
                return
            except Exception:
                pass

        self._lbl_preview.configure(
            text=f"Se acreditarán: {formatear_valor(monto_origen, cuenta_dest.moneda)} en '{cuenta_dest.nombre}'"
        )

    def _confirmar(self) -> None:
        if self._inv.id is None:
            self.destroy()
            return
        monto_origen = self._obtener_monto_ingresado()
        seleccion = self._selector_cuenta.get()
        id_cuenta = self._mapa_opciones_cuenta.get(seleccion)
        destino_param = id_cuenta if id_cuenta is not None else "No enviar a ninguna cuenta"

        try:
            resultado = self._gestor.cerrar_inversion(
                id_inversion=self._inv.id,
                cuenta_destino=destino_param,
                valor_total_venta=f"{monto_origen:.2f}",
            )
        except Exception as error:
            messagebox.showerror("Error al cerrar posición", str(error), parent=self)
            return

        self.destroy()
        if self._al_confirmar is not None:
            self._al_confirmar(resultado)

