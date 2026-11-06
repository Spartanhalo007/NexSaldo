"""Vista de Resumen Financiero con soporte de todas las divisas del mundo
(COP + 4 últimas usadas + orden alfabético A-Z) y modo 'Solo esta moneda' vs 'Todo convertido'."""

from datetime import date
from decimal import Decimal
import tkinter as tk
import customtkinter as ctk

from app.gui.estilos import COLORES, COLORES_GRAFICA, FUENTE
from app.gui.formato import formatear_valor, nombre_mes
from app.gui.selector_moneda import BarraFiltroMoneda

TAMANO_DONA = 220
GROSOR_DONA = 32


class VistaResumen(ctk.CTkFrame):
    """Muestra el resumen mensual de gastos por categoría, ingresos e inversiones,
    filtrando solo por la divisa seleccionada o convirtiendo todo a la divisa elegida."""

    def __init__(self, master, gestor, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._gestor = gestor

        hoy = date.today()
        self._anno = hoy.year
        self._mes = hoy.month
        self._moneda_actual = "COP"
        self._incluir_todas_convertidas = False

        self._construir_encabezado()
        self._construir_columnas()
        self.refrescar()

    def _construir_encabezado(self):
        cabecera = ctk.CTkFrame(self, fg_color="transparent")
        cabecera.pack(fill="x", pady=(0, 12))

        fila_titulo = ctk.CTkFrame(cabecera, fg_color="transparent")
        fila_titulo.pack(fill="x")

        ctk.CTkLabel(
            fila_titulo,
            text="Resumen Financiero",
            font=(FUENTE, 24, "bold"),
            text_color=COLORES["texto"],
        ).pack(side="left")

        # Controles de navegación de mes
        marco_mes = ctk.CTkFrame(fila_titulo, fg_color="transparent")
        marco_mes.pack(side="right")

        ctk.CTkButton(
            marco_mes,
            text="◀",
            width=32,
            height=30,
            corner_radius=8,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 12, "bold"),
            command=lambda: self._cambiar_mes(-1),
        ).pack(side="left", padx=4)

        self._etiqueta_mes = ctk.CTkLabel(
            marco_mes,
            text=nombre_mes(self._anno, self._mes).capitalize(),
            font=(FUENTE, 14, "bold"),
            text_color=COLORES["texto_secundario"],
            width=155,
        )
        self._etiqueta_mes.pack(side="left", padx=6)

        ctk.CTkButton(
            marco_mes,
            text="▶",
            width=32,
            height=30,
            corner_radius=8,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 12, "bold"),
            command=lambda: self._cambiar_mes(1),
        ).pack(side="left", padx=4)

        # Barra de filtro de moneda (COP + 4 últimas + Todas A-Z) y modo (Solo esta moneda vs Todo convertido)
        fila_moneda = ctk.CTkFrame(
            cabecera, fg_color=COLORES["fondo_tarjeta"], corner_radius=10
        )
        fila_moneda.pack(fill="x", pady=(10, 0))

        contenedor_barra = ctk.CTkFrame(fila_moneda, fg_color="transparent")
        contenedor_barra.pack(fill="x", padx=14, pady=8)

        self._barra_moneda = BarraFiltroMoneda(
            contenedor_barra,
            gestor=self._gestor,
            al_cambiar=self._al_cambiar_filtro_moneda,
            moneda_inicial="COP",
            mostrar_modo=True,
        )
        self._barra_moneda.pack(side="left")

        self._etiqueta_modo_activo = ctk.CTkLabel(
            contenedor_barra,
            text="Mostrando solo movimientos en COP",
            font=(FUENTE, 11),
            text_color=COLORES["texto_secundario"],
        )
        self._etiqueta_modo_activo.pack(side="right")

    def _construir_columnas(self):
        columnas = ctk.CTkFrame(self, fg_color="transparent")
        columnas.pack(fill="both", expand=True)
        columnas.grid_columnconfigure(0, weight=1)
        columnas.grid_columnconfigure(1, weight=1)
        columnas.grid_rowconfigure(0, weight=1)

        self._construir_columna_gastos(columnas)
        self._construir_columna_inversiones(columnas)

    def _construir_columna_gastos(self, columnas):
        col_gastos = ctk.CTkFrame(
            columnas, fg_color=COLORES["fondo_tarjeta"], corner_radius=14
        )
        col_gastos.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        self._titulo_col_gastos = ctk.CTkLabel(
            col_gastos,
            text="Gastos por categoría este mes",
            font=(FUENTE, 16, "bold"),
            text_color=COLORES["texto"],
        )
        self._titulo_col_gastos.pack(pady=(14, 4))

        self._lienzo = tk.Canvas(
            col_gastos,
            width=TAMANO_DONA,
            height=TAMANO_DONA,
            bg=COLORES["fondo_tarjeta"],
            highlightthickness=0,
        )
        self._lienzo.pack(pady=4)

        self._etiqueta_total_gastos = ctk.CTkLabel(
            col_gastos,
            text="Total gastos: $ 0,00",
            font=(FUENTE, 14, "bold"),
            text_color=COLORES["texto"],
        )
        self._etiqueta_total_gastos.pack(pady=(2, 8))

        fila_ing_gas = ctk.CTkFrame(
            col_gastos, fg_color=COLORES["boton_lateral"], corner_radius=10
        )
        fila_ing_gas.pack(fill="x", padx=16, pady=(0, 10))

        self._etiqueta_ingresos = ctk.CTkLabel(
            fila_ing_gas,
            text="Ingresos: $ 0,00",
            font=(FUENTE, 12, "bold"),
            text_color=COLORES["exito"],
        )
        self._etiqueta_ingresos.pack(side="left", padx=12, pady=8)

        self._etiqueta_gastos = ctk.CTkLabel(
            fila_ing_gas,
            text="Gastos: $ 0,00",
            font=(FUENTE, 12, "bold"),
            text_color=COLORES["error"],
        )
        self._etiqueta_gastos.pack(side="right", padx=12, pady=8)

        self._marco_desglose = ctk.CTkScrollableFrame(
            col_gastos, fg_color=COLORES["boton_lateral"], corner_radius=10, height=150
        )
        self._marco_desglose.pack(fill="both", expand=True, padx=16, pady=(0, 14))

    def _construir_columna_inversiones(self, columnas):
        col_inv = ctk.CTkFrame(
            columnas, fg_color=COLORES["fondo_tarjeta"], corner_radius=14
        )
        col_inv.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        ctk.CTkLabel(
            col_inv,
            text="Cuentas e Inversiones",
            font=(FUENTE, 16, "bold"),
            text_color=COLORES["texto"],
        ).pack(pady=(14, 6))

        self._etiqueta_saldo_cuentas_resumen = ctk.CTkLabel(
            col_inv,
            text="Saldo en cuentas: $ 0,00",
            font=(FUENTE, 16, "bold"),
            text_color=COLORES["acento"],
        )
        self._etiqueta_saldo_cuentas_resumen.pack(pady=(8, 4))

        self._etiqueta_sub_cuentas = ctk.CTkLabel(
            col_inv,
            text="",
            font=(FUENTE, 12),
            text_color=COLORES["texto_secundario"],
        )
        self._etiqueta_sub_cuentas.pack(pady=(0, 12))

        self._contenedor_cuentas_resumen = ctk.CTkScrollableFrame(
            col_inv, fg_color=COLORES["boton_lateral"], corner_radius=10, height=220
        )
        self._contenedor_cuentas_resumen.pack(
            fill="both", expand=True, padx=16, pady=(0, 14)
        )

    def _cambiar_mes(self, delta: int):
        nuevo_mes = self._mes + delta
        nuevo_anno = self._anno
        if nuevo_mes < 1:
            nuevo_mes = 12
            nuevo_anno -= 1
        elif nuevo_mes > 12:
            nuevo_mes = 1
            nuevo_anno += 1
        self._mes = nuevo_mes
        self._anno = nuevo_anno
        self._etiqueta_mes.configure(
            text=nombre_mes(self._anno, self._mes).capitalize()
        )
        self.refrescar()

    def _al_cambiar_filtro_moneda(self, moneda: str, incluir_todas: bool):
        self._moneda_actual = moneda
        self._incluir_todas_convertidas = incluir_todas
        self.refrescar()

    def refrescar(self):
        moneda = self._moneda_actual
        incluir_todas = self._incluir_todas_convertidas

        if incluir_todas:
            self._etiqueta_modo_activo.configure(
                text=f"Total unificado (todas las divisas convertidas a {moneda} con Yahoo Finance)",
                text_color=COLORES["acento"],
            )
        else:
            self._etiqueta_modo_activo.configure(
                text=f"Mostrando únicamente registros en {moneda}",
                text_color=COLORES["texto_secundario"],
            )

        datos_mes = self._gestor.resumen_del_mes_en_moneda(
            self._anno,
            self._mes,
            moneda_objetivo=moneda,
            incluir_todas_convertidas=incluir_todas,
        )
        ingresos: Decimal = datos_mes["ingresos"]  # type: ignore[assignment]
        gastos: Decimal = datos_mes["gastos"]  # type: ignore[assignment]
        gastos_por_cat: dict = datos_mes["gastos_por_categoria"]  # type: ignore[assignment]

        self._etiqueta_total_gastos.configure(
            text=f"Total gastos ({moneda}): {formatear_valor(gastos, moneda)}"
        )
        self._etiqueta_ingresos.configure(
            text=f"Ingresos: {formatear_valor(ingresos, moneda)}"
        )
        self._etiqueta_gastos.configure(
            text=f"Gastos: {formatear_valor(gastos, moneda)}"
        )

        self._dibujar_dona(gastos_por_cat, moneda)
        self._actualizar_desglose(gastos_por_cat, gastos, moneda)
        self._actualizar_panel_cuentas(moneda, incluir_todas)

    def _dibujar_dona(self, gastos_por_categoria: dict, moneda: str):
        self._lienzo.delete("all")
        margen = 18
        x0, y0 = margen, margen
        x1, y1 = TAMANO_DONA - margen, TAMANO_DONA - margen
        centro = TAMANO_DONA // 2

        total = sum(gastos_por_categoria.values(), Decimal("0"))
        if total <= Decimal("0") or not gastos_por_categoria:
            self._lienzo.create_oval(
                x0, y0, x1, y1, outline=COLORES["boton_lateral"], width=GROSOR_DONA
            )
            self._lienzo.create_text(
                centro,
                centro,
                text="Sin gastos\neste mes",
                fill=COLORES["texto_secundario"],
                font=(FUENTE, 12, "bold"),
                justify="center",
            )
            return

        items = sorted(
            gastos_por_categoria.items(), key=lambda par: par[1], reverse=True
        )
        if len(items) == 1:
            self._lienzo.create_oval(
                x0, y0, x1, y1, outline=COLORES_GRAFICA[0], width=GROSOR_DONA
            )
        else:
            inicio = 90.0
            for idx, (_, valor) in enumerate(items):
                ext = -float(valor / total) * 360.0
                color = COLORES_GRAFICA[idx % len(COLORES_GRAFICA)]
                self._lienzo.create_arc(
                    x0,
                    y0,
                    x1,
                    y1,
                    start=inicio,
                    extent=ext,
                    style="arc",
                    outline=color,
                    width=GROSOR_DONA,
                )
                inicio += ext

        self._lienzo.create_text(
            centro,
            centro,
            text=formatear_valor(total, moneda),
            fill=COLORES["texto"],
            font=(FUENTE, 12, "bold"),
            justify="center",
        )

    def _actualizar_desglose(
        self, gastos_por_categoria: dict, total_gastos: Decimal, moneda: str
    ):
        for hijo in self._marco_desglose.winfo_children():
            hijo.destroy()

        if total_gastos <= Decimal("0") or not gastos_por_categoria:
            ctk.CTkLabel(
                self._marco_desglose,
                text="No hay gastos registrados en este filtro.",
                font=(FUENTE, 12),
                text_color=COLORES["texto_secundario"],
            ).pack(pady=24)
            return

        for idx, (cat, monto) in enumerate(
            sorted(gastos_por_categoria.items(), key=lambda p: p[1], reverse=True)
        ):
            pct = (monto / total_gastos) * Decimal("100")
            fila = ctk.CTkFrame(self._marco_desglose, fg_color="transparent")
            fila.pack(fill="x", padx=8, pady=3)

            color = COLORES_GRAFICA[idx % len(COLORES_GRAFICA)]
            punto = ctk.CTkFrame(
                fila, width=12, height=12, corner_radius=6, fg_color=color
            )
            punto.pack(side="left", padx=(4, 8))

            ctk.CTkLabel(
                fila,
                text=cat,
                font=(FUENTE, 12, "bold"),
                text_color=COLORES["texto"],
            ).pack(side="left")

            ctk.CTkLabel(
                fila,
                text=formatear_valor(monto, moneda),
                font=(FUENTE, 12, "bold"),
                text_color=COLORES["texto"],
            ).pack(side="right", padx=6)

            ctk.CTkLabel(
                fila,
                text=f"{pct:.1f}%",
                font=(FUENTE, 11),
                text_color=COLORES["texto_secundario"],
            ).pack(side="right", padx=6)

    def _actualizar_panel_cuentas(self, moneda: str, incluir_todas: bool):
        for hijo in self._contenedor_cuentas_resumen.winfo_children():
            hijo.destroy()

        cuentas_con_saldo = self._gestor.obtener_cuentas()
        total_cuentas = self._gestor.calcular_total_cuentas_en_moneda(
            cuentas_con_saldo,
            moneda_objetivo=moneda,
            incluir_todas_convertidas=incluir_todas,
        )
        self._etiqueta_saldo_cuentas_resumen.configure(
            text=f"Saldo disponible ({moneda}): {formatear_valor(total_cuentas, moneda)}"
        )
        self._etiqueta_sub_cuentas.configure(
            text="Incluyendo todas las cuentas convertidas"
            if incluir_todas
            else f"Mostrando solo cuentas en {moneda}"
        )

        cuentas_mostrar = [
            (c, s)
            for c, s in cuentas_con_saldo
            if incluir_todas or c.moneda == moneda
        ]
        if not cuentas_mostrar:
            ctk.CTkLabel(
                self._contenedor_cuentas_resumen,
                text=f"No hay cuentas en {moneda}.",
                font=(FUENTE, 12),
                text_color=COLORES["texto_secundario"],
            ).pack(pady=30)
            return

        for cuenta, saldo in cuentas_mostrar:
            fila = ctk.CTkFrame(
                self._contenedor_cuentas_resumen,
                fg_color=COLORES["fondo_tarjeta"],
                corner_radius=8,
            )
            fila.pack(fill="x", padx=6, pady=4)

            ctk.CTkLabel(
                fila,
                text=f"{cuenta.nombre} ({cuenta.moneda})",
                font=(FUENTE, 12, "bold"),
                text_color=COLORES["texto"],
            ).pack(side="left", padx=10, pady=8)

            if incluir_todas and cuenta.moneda != moneda:
                try:
                    conv = self._gestor.convertir_entre_monedas(
                        saldo, cuenta.moneda, moneda
                    )
                    texto_saldo = f"{formatear_valor(conv, moneda)} ({formatear_valor(saldo, cuenta.moneda)})"
                except Exception:
                    texto_saldo = formatear_valor(saldo, cuenta.moneda)
            else:
                texto_saldo = formatear_valor(saldo, cuenta.moneda)

            ctk.CTkLabel(
                fila,
                text=texto_saldo,
                font=(FUENTE, 12, "bold"),
                text_color=COLORES["acento"],
            ).pack(side="right", padx=10, pady=8)
