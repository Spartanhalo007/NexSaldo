"""Diálogo/Formulario completo para Añadir Gasto en NexSaldo."""

from datetime import date, datetime, timedelta
import os
from pathlib import Path
import shutil
from tkinter import filedialog, messagebox
from typing import Callable, Dict, List, Optional
import customtkinter as ctk
from PIL import Image

from app.gestor.gestor_financiero import ErrorValidacion, GestorFinanciero
from app.gui.calculadora import Calculadora
from app.gui.calendario import SelectorCalendario
from app.gui.campo_moneda import CampoMoneda
from app.gui.dialogo_categoria import DialogoCategoria
from app.gui.dialogo_etiqueta import DialogoEtiquetas
from app.gui.estilos import COLORES, FUENTE
from app.gui.formato import formatear_valor
from app.gui.iconos import GRIS, icono_ctk
from app.modelo.categoria import Categoria
from app.modelo.cuenta import Cuenta
from app.modelo.movimiento_financiero import MovimientoFinanciero

RUTA_ADJUNTOS = Path(__file__).resolve().parents[2] / "adjuntos"
MAXIMO_ADJUNTO_BYTES = 2 * 1024 * 1024


class DialogoGasto(ctk.CTkToplevel):
    """Formulario para añadir un gasto con monto, divisa (COP por defecto), calculadora,
    cuenta, categorías circulares (+ botón Más gris), fechas rápidas (Hoy/Ayer/Último/Calendario),
    etiquetas 100% customizables, comentario y foto."""

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

        self._moneda_elegida = "COP"  # Default siempre Peso Colombiano
        self._cuenta_elegida_id: Optional[int] = None
        self._mapa_cuentas: Dict[str, Cuenta] = {}
        self._categoria_elegida: str = "Alimentación"
        self._fecha_elegida: date = date.today()
        self._modo_fecha: str = "HOY"
        self._etiquetas_elegidas: List[str] = []
        self._ruta_imagen: Optional[str] = None

        self.title("Añadir gasto")
        self.geometry("680x820")
        self.resizable(False, True)
        self.configure(fg_color=COLORES["fondo_lateral"])
        self.transient(master)
        self.grab_set()

        self._construir_interfaz()

    def _construir_interfaz(self):
        cuerpo = ctk.CTkScrollableFrame(
            self, fg_color="transparent", width=640, height=770
        )
        cuerpo.pack(fill="both", expand=True, padx=16, pady=14)

        ctk.CTkLabel(
            cuerpo,
            text="Añadir gasto",
            font=(FUENTE, 22, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w", pady=(0, 10))

        # ==================================================================
        # 1. CANTIDAD GASTADA + DIVISA (COP default / USD) + CALCULADORA
        # ==================================================================
        marco_monto = ctk.CTkFrame(
            cuerpo, fg_color=COLORES["fondo_tarjeta"], corner_radius=12
        )
        marco_monto.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            marco_monto,
            text="Cantidad gastada y divisa",
            font=(FUENTE, 13, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w", padx=16, pady=(12, 6))

        fila_monto_calc = ctk.CTkFrame(marco_monto, fg_color="transparent")
        fila_monto_calc.pack(fill="x", padx=16, pady=(0, 14))

        # Columna izquierda: CampoMoneda + selector de divisa al lado + selector de cuenta abajo
        col_izquierda = ctk.CTkFrame(fila_monto_calc, fg_color="transparent")
        col_izquierda.pack(side="left", fill="both", expand=True, padx=(0, 12))

        fila_input_divisa = ctk.CTkFrame(col_izquierda, fg_color="transparent")
        fila_input_divisa.pack(fill="x", pady=(0, 12))

        self._campo_valor = CampoMoneda(
            fila_input_divisa, width=210, height=40, corner_radius=8
        )
        self._campo_valor.pack(side="left", padx=(0, 10))

        # Selector de divisa al lado (COP siempre por defecto)
        self._var_moneda = ctk.StringVar(value="COP")
        self._selector_divisa = ctk.CTkSegmentedButton(
            fila_input_divisa,
            values=["COP", "USD"],
            variable=self._var_moneda,
            selected_color=COLORES["acento"],
            selected_hover_color=COLORES["acento_hover"],
            unselected_color=COLORES["boton_lateral"],
            unselected_hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 13, "bold"),
            height=40,
            command=self._al_cambiar_divisa,
        )
        self._selector_divisa.pack(side="left")

        # Debajo de cantidad y divisa: Seleccionar la cuenta en la que se añadirá el gasto
        ctk.CTkLabel(
            col_izquierda,
            text="Cuenta de origen del gasto:",
            font=(FUENTE, 13, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w", pady=(4, 4))

        self._var_cuenta = ctk.StringVar(value="Sin cuenta asociada")
        self._combo_cuenta = ctk.CTkOptionMenu(
            col_izquierda,
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
            col_izquierda,
            text="Moneda por defecto: Peso colombiano (COP)",
            font=(FUENTE, 11),
            text_color=COLORES["texto_secundario"],
        )
        self._etiqueta_info_cuenta.pack(anchor="w", pady=(4, 0))

        # Al lado derecho: Calculadora tal como aparece en el módulo de cuentas
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
    # Lógica de Divisa y Cuentas
    # ------------------------------------------------------------------
    def _cargar_cuentas_disponibles(self):
        cuentas_con_saldo = self._gestor.obtener_cuentas()
        self._mapa_cuentas.clear()
        opciones = ["Sin cuenta asociada"]

        for cuenta, saldo in cuentas_con_saldo:
            if cuenta.moneda == self._moneda_elegida:
                etiqueta = f"{cuenta.nombre} ({formatear_valor(saldo, cuenta.moneda)})"
                self._mapa_cuentas[etiqueta] = cuenta
                opciones.append(etiqueta)

        self._combo_cuenta.configure(values=opciones)
        if len(opciones) > 1:
            primera = opciones[1]
            self._var_cuenta.set(primera)
            self._cuenta_elegida_id = self._mapa_cuentas[primera].id
        else:
            self._var_cuenta.set("Sin cuenta asociada")
            self._cuenta_elegida_id = None

    def _al_cambiar_divisa(self, nueva_moneda: str):
        self._moneda_elegida = nueva_moneda
        self._etiqueta_info_cuenta.configure(
            text=f"Mostrando cuentas en {nueva_moneda}"
        )
        self._cargar_cuentas_disponibles()

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

        # Al lado de las categorías: Símbolo gris de sumar llamado "Más"
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
        comentario = self._campo_comentario.get().strip() or None

        # Verificar si la categoría seleccionada tiene gasto programado activo
        mapa_cats = {c.nombre: c for c in self._gestor.obtener_categorias_detalladas("GASTO")}
        cat_obj = mapa_cats.get(self._categoria_elegida)
        es_prog = bool(cat_obj.gasto_programado) if cat_obj else False
        frec_prog = cat_obj.frecuencia if cat_obj else None

        try:
            movimiento = self._gestor.registrar_gasto(
                valor_texto=valor_limpio,
                moneda=self._moneda_elegida,
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
