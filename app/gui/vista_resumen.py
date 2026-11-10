"""Vista de Resumen Financiero con gráfica combinada de Ingresos (+), Gastos (-) y Balance Neto
con eje positivo/negativo (representación invertida bajo cero cuando los gastos superan a los ingresos),
respetando los colores establecidos de cada categoría, selector de periodo estilo píldora de fechas y filtro mundial de divisas."""

from datetime import date
import threading
from decimal import Decimal
import tkinter as tk
from typing import Dict, Optional, Tuple
import customtkinter as ctk

from app.gui.dialogo_periodo import (
    DialogoPeriodo,
    calcular_rango_preset,
    desplazar_rango,
)
from app.gui.estilos import COLORES, FUENTE
from app.gui.formato import formatear_valor
from app.gui.selector_moneda import BarraFiltroMoneda

ANCHO_LIENZO_BALANCE = 460
ALTO_LIENZO_BALANCE = 250


def _formatear_con_signo(monto: Decimal, moneda: str) -> str:
    """Formatea un monto agregando explícitamente '+' para valores positivos y '-' para negativos."""
    if monto > Decimal("0"):
        return f"+ {formatear_valor(monto, moneda)}"
    if monto < Decimal("0"):
        return f"- {formatear_valor(abs(monto), moneda)}"
    return formatear_valor(Decimal("0"), moneda)


class VistaResumen(ctk.CTkFrame):
    """Muestra el resumen combinado de Ingresos, Gastos y Balance Neto del periodo
    con eje bidireccional (+ / -), conservando los colores establecidos de cada categoría,
    junto con el panel de Cuentas e Inversiones."""

    def __init__(self, master, gestor, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._gestor = gestor

        hoy = date.today()
        self._anno = hoy.year
        self._mes = hoy.month
        self._preset_periodo = "ESTE_MES"
        self._fecha_inicio, self._fecha_fin, self._texto_periodo = calcular_rango_preset(
            "ESTE_MES", referencia=hoy
        )
        self._moneda_actual = "COP"
        self._incluir_todas_convertidas = False
        self._actualizando_inv_bg = False

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

        # Controles de navegación de periodo: ◀ [ 📅 Noviembre de 2026 ▾ ] ▶
        marco_mes = ctk.CTkFrame(fila_titulo, fg_color="transparent")
        marco_mes.pack(side="right")

        ctk.CTkButton(
            marco_mes,
            text="◀",
            width=34,
            height=34,
            corner_radius=8,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 12, "bold"),
            command=lambda: self._desplazar_periodo(-1),
        ).pack(side="left", padx=4)

        self._boton_periodo = ctk.CTkButton(
            marco_mes,
            text=f"📅  {self._texto_periodo}  ▾",
            height=34,
            corner_radius=8,
            fg_color=COLORES["fondo_tarjeta"],
            hover_color=COLORES["boton_lateral"],
            border_width=1,
            border_color=COLORES["acento"],
            text_color=COLORES["texto"],
            font=(FUENTE, 13, "bold"),
            command=self._abrir_selector_periodo,
        )
        self._boton_periodo.pack(side="left", padx=6)

        ctk.CTkButton(
            marco_mes,
            text="▶",
            width=34,
            height=34,
            corner_radius=8,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 12, "bold"),
            command=lambda: self._desplazar_periodo(1),
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

        self._construir_columna_balance(columnas)
        self._construir_columna_inversiones(columnas)

    def _construir_columna_balance(self, columnas):
        col_gastos = ctk.CTkFrame(
            columnas, fg_color=COLORES["fondo_tarjeta"], corner_radius=14
        )
        col_gastos.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        self._titulo_col_gastos = ctk.CTkLabel(
            col_gastos,
            text="Balance Neto: Ingresos vs. Gastos",
            font=(FUENTE, 16, "bold"),
            text_color=COLORES["texto"],
        )
        self._titulo_col_gastos.pack(pady=(12, 2))

        self._lienzo = tk.Canvas(
            col_gastos,
            width=ANCHO_LIENZO_BALANCE,
            height=ALTO_LIENZO_BALANCE,
            bg=COLORES["fondo_tarjeta"],
            highlightthickness=0,
        )
        self._lienzo.pack(padx=10, pady=2)

        self._etiqueta_total_gastos = ctk.CTkLabel(
            col_gastos,
            text="Balance neto: $ 0,00",
            font=(FUENTE, 14, "bold"),
            text_color=COLORES["texto"],
        )
        self._etiqueta_total_gastos.pack(pady=(2, 6))

        fila_ing_gas = ctk.CTkFrame(
            col_gastos, fg_color=COLORES["boton_lateral"], corner_radius=10
        )
        fila_ing_gas.pack(fill="x", padx=16, pady=(0, 8))

        self._etiqueta_ingresos = ctk.CTkLabel(
            fila_ing_gas,
            text="Ingresos: + $ 0,00",
            font=(FUENTE, 12, "bold"),
            text_color=COLORES["exito"],
        )
        self._etiqueta_ingresos.pack(side="left", padx=12, pady=7)

        self._etiqueta_gastos = ctk.CTkLabel(
            fila_ing_gas,
            text="Gastos: - $ 0,00",
            font=(FUENTE, 12, "bold"),
            text_color=COLORES["error"],
        )
        self._etiqueta_gastos.pack(side="right", padx=12, pady=7)

        self._marco_desglose = ctk.CTkScrollableFrame(
            col_gastos, fg_color=COLORES["boton_lateral"], corner_radius=10, height=140
        )
        self._marco_desglose.pack(fill="both", expand=True, padx=16, pady=(0, 12))

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

    # ------------------------------------------------------------------
    # Navegación de Periodo y Popup estilo píldora de fechas
    # ------------------------------------------------------------------
    def _abrir_selector_periodo(self):
        DialogoPeriodo(
            self,
            fecha_inicio=self._fecha_inicio,
            fecha_fin=self._fecha_fin,
            preset_inicial=self._preset_periodo,
            al_aplicar=self._al_aplicar_periodo,
        )

    def _al_aplicar_periodo(
        self, fecha_ini: date, fecha_fin: date, preset: str, etiqueta: str
    ):
        self._fecha_inicio = fecha_ini
        self._fecha_fin = fecha_fin
        self._preset_periodo = preset
        self._texto_periodo = etiqueta
        self._anno = fecha_fin.year
        self._mes = fecha_fin.month
        self._boton_periodo.configure(text=f"📅  {self._texto_periodo}  ▾")
        self.refrescar()

    def _desplazar_periodo(self, direccion: int):
        ini, fin, etiqueta = desplazar_rango(
            self._preset_periodo, self._fecha_inicio, self._fecha_fin, direccion
        )
        self._fecha_inicio = ini
        self._fecha_fin = fin
        self._texto_periodo = etiqueta
        self._anno = fin.year
        self._mes = fin.month
        self._boton_periodo.configure(text=f"📅  {self._texto_periodo}  ▾")
        self.refrescar()

    def _al_cambiar_filtro_moneda(self, moneda: str, incluir_todas: bool):
        self._moneda_actual = moneda
        self._incluir_todas_convertidas = incluir_todas
        self.refrescar()

    def _obtener_colores_establecidos(self) -> Tuple[Dict[str, str], Dict[str, str]]:
        """Obtiene los colores exactos definidos para cada categoría de INGRESO y de GASTO."""
        colores_ing: Dict[str, str] = {}
        colores_gas: Dict[str, str] = {}
        if hasattr(self._gestor, "obtener_categorias_detalladas"):
            try:
                for c in self._gestor.obtener_categorias_detalladas("INGRESO"):
                    colores_ing[c.nombre] = c.color
                for c in self._gestor.obtener_categorias_detalladas("GASTO"):
                    colores_gas[c.nombre] = c.color
            except Exception:
                pass
        return colores_ing, colores_gas

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

        self._titulo_col_gastos.configure(
            text=f"Balance Neto (Ingresos vs. Gastos) · {self._texto_periodo}"
        )

        datos_rango = self._gestor.resumen_del_rango_en_moneda(
            fecha_inicio=self._fecha_inicio,
            fecha_fin=self._fecha_fin,
            moneda_objetivo=moneda,
            incluir_todas_convertidas=incluir_todas,
        )
        ingresos: Decimal = datos_rango.get("ingresos", Decimal("0"))  # type: ignore[assignment]
        gastos: Decimal = datos_rango.get("gastos", Decimal("0"))  # type: ignore[assignment]
        gastos_por_cat: Dict[str, Decimal] = datos_rango.get("gastos_por_categoria", {})  # type: ignore[assignment]
        ingresos_por_cat: Dict[str, Decimal] = datos_rango.get("ingresos_por_categoria", {})  # type: ignore[assignment]

        # Si el gestor no devolvió ingresos_por_categoria (ej. en un mock antiguo), lo calculamos
        if not ingresos_por_cat and ingresos > Decimal("0"):
            ingresos_por_cat = {"Ingresos": ingresos}

        balance_neto = ingresos - gastos
        colores_ing, colores_gas = self._obtener_colores_establecidos()
        colores_ing.update(datos_rango.get("colores_ingresos", {}))  # type: ignore[arg-type]
        colores_gas.update(datos_rango.get("colores_gastos", {}))  # type: ignore[arg-type]

        if balance_neto > Decimal("0"):
            color_balance = COLORES["exito"]
            estado_txt = "Superávit"
        elif balance_neto < Decimal("0"):
            color_balance = COLORES["error"]
            estado_txt = "Déficit (gastas más de lo que ganas)"
        else:
            color_balance = COLORES["texto"]
            estado_txt = "Equilibrio"

        self._etiqueta_total_gastos.configure(
            text=f"Balance neto ({moneda}): {_formatear_con_signo(balance_neto, moneda)}  •  {estado_txt}",
            text_color=color_balance,
        )
        self._etiqueta_ingresos.configure(
            text=f"Ingresos: + {formatear_valor(ingresos, moneda)}"
        )
        self._etiqueta_gastos.configure(
            text=f"Gastos: - {formatear_valor(gastos, moneda)}"
        )

        self._dibujar_grafica_balance_neto(
            ingresos_por_categoria=ingresos_por_cat,
            gastos_por_categoria=gastos_por_cat,
            total_ingresos=ingresos,
            total_gastos=gastos,
            balance_neto=balance_neto,
            colores_ingresos=colores_ing,
            colores_gastos=colores_gas,
            moneda=moneda,
        )
        self._actualizar_desglose_combinado(
            ingresos_por_categoria=ingresos_por_cat,
            gastos_por_categoria=gastos_por_cat,
            total_ingresos=ingresos,
            total_gastos=gastos,
            colores_ingresos=colores_ing,
            colores_gastos=colores_gas,
            moneda=moneda,
        )
        self._actualizar_panel_cuentas(moneda, incluir_todas)

    # ------------------------------------------------------------------
    # Gráfica Divergente de Balance Neto (Eje +Y arriba / Eje -Y invertido abajo)
    # ------------------------------------------------------------------
    def _dibujar_grafica_balance_neto(
        self,
        ingresos_por_categoria: Dict[str, Decimal],
        gastos_por_categoria: Dict[str, Decimal],
        total_ingresos: Decimal,
        total_gastos: Decimal,
        balance_neto: Decimal,
        colores_ingresos: Dict[str, str],
        colores_gastos: Dict[str, str],
        moneda: str,
    ):
        """Dibuja una visualización divergente con eje cero ($0):
        - Eje positivo (+Y, hacia arriba): apila las categorías de Ingresos con sus colores establecidos.
        - Eje negativo (-Y, invertido hacia abajo): apila las categorías de Gastos con sus colores establecidos.
        - Columna de Balance Neto (`Ingresos - Gastos`): se proyecta hacia arriba (+Y) si es positivo
          o invertida hacia abajo (-Y) si es negativo (ej. $0 ingresos y $100 gastos -> -$100 hacia abajo)."""
        self._lienzo.delete("all")
        ancho = ANCHO_LIENZO_BALANCE
        alto = ALTO_LIENZO_BALANCE

        if total_ingresos <= Decimal("0") and total_gastos <= Decimal("0"):
            self._lienzo.create_line(
                50, alto // 2, ancho - 24, alto // 2,
                fill=COLORES["boton_lateral"], width=2, dash=(4, 4)
            )
            self._lienzo.create_text(
                ancho // 2,
                alto // 2,
                text="Sin ingresos ni gastos\nregistrados en este periodo",
                fill=COLORES["texto_secundario"],
                font=(FUENTE, 12, "bold"),
                justify="center",
            )
            return

        margen_izq = 86
        margen_der = 22
        margen_sup = 28
        margen_inf = 36
        alto_util = alto - margen_sup - margen_inf

        max_pos = max(total_ingresos, balance_neto if balance_neto > Decimal("0") else Decimal("0"))
        max_neg = max(total_gastos, abs(balance_neto) if balance_neto < Decimal("0") else Decimal("0"))

        # Posicionamiento adaptativo del eje 0 ($0):
        # - Si solo hay gastos (ej. $0 ingresos, $100 gastos -> balance -$100), el eje 0 se ubica arriba
        #   para que toda la gráfica se dibuje invertida hacia el eje negativo (-Y).
        # - Si solo hay ingresos, el eje 0 se ubica abajo.
        # - Si hay ambos, el eje 0 se centra proporcionalmente con un margen mínimo de 25% por lado.
        if max_pos <= Decimal("0") and max_neg > Decimal("0"):
            proporcion_pos = 0.14
        elif max_neg <= Decimal("0") and max_pos > Decimal("0"):
            proporcion_pos = 0.86
        else:
            suma_extremos = float(max_pos + max_neg)
            proporcion_pos = float(max_pos) / suma_extremos if suma_extremos > 0 else 0.5
            proporcion_pos = max(0.28, min(0.72, proporcion_pos))

        y_cero = int(margen_sup + alto_util * proporcion_pos)
        alto_pos_px = max(1, y_cero - margen_sup)
        alto_neg_px = max(1, (alto - margen_inf) - y_cero)

        escala_pos = (alto_pos_px / float(max_pos)) if max_pos > Decimal("0") else 0.0
        escala_neg = (alto_neg_px / float(max_neg)) if max_neg > Decimal("0") else 0.0

        # Guías horizontales y etiquetas del Eje Y (+Máx, 0, -Máx)
        if max_pos > Decimal("0"):
            y_top = margen_sup
            self._lienzo.create_line(
                margen_izq, y_top, ancho - margen_der, y_top,
                fill=COLORES["boton_lateral"], width=1, dash=(3, 3),
            )
            self._lienzo.create_text(
                margen_izq - 6,
                y_top,
                text=f"+{_abreviar_monto(max_pos)}",
                fill=COLORES["exito"],
                font=(FUENTE, 9, "bold"),
                anchor="e",
            )

        if max_neg > Decimal("0"):
            y_bot = alto - margen_inf
            self._lienzo.create_line(
                margen_izq, y_bot, ancho - margen_der, y_bot,
                fill=COLORES["boton_lateral"], width=1, dash=(3, 3),
            )
            self._lienzo.create_text(
                margen_izq - 6,
                y_bot,
                text=f"-{_abreviar_monto(max_neg)}",
                fill=COLORES["error"],
                font=(FUENTE, 9, "bold"),
                anchor="e",
            )

        # Coordenadas X de las 3 columnas: 1) Ingresos (+), 2) Gastos (-), 3) Balance Neto
        ancho_plot = (ancho - margen_izq - margen_der)
        ancho_barra = 66
        centros_x = [
            margen_izq + int(ancho_plot * 0.20),
            margen_izq + int(ancho_plot * 0.52),
            margen_izq + int(ancho_plot * 0.84),
        ]

        # ------------------------------------------------------------------
        # 1. BARRA APILADA DE INGRESOS (+Y, hacia arriba desde y_cero)
        # ------------------------------------------------------------------
        x_ing = centros_x[0]
        if total_ingresos > Decimal("0") and ingresos_por_categoria:
            y_cursor = float(y_cero)
            for cat, monto in sorted(
                ingresos_por_categoria.items(), key=lambda p: p[1], reverse=True
            ):
                if monto <= Decimal("0"):
                    continue
                h_seg = max(2.0, float(monto) * escala_pos)
                y_sig = max(float(margen_sup), y_cursor - h_seg)
                color_cat = colores_ingresos.get(cat, "#7DC98F")
                self._lienzo.create_rectangle(
                    x_ing - ancho_barra // 2,
                    int(y_sig),
                    x_ing + ancho_barra // 2,
                    int(y_cursor),
                    fill=color_cat,
                    outline=COLORES["fondo_tarjeta"],
                    width=1,
                )
                y_cursor = y_sig

            self._lienzo.create_text(
                x_ing,
                max(12, int(y_cursor) - 10),
                text=f"+{_abreviar_monto(total_ingresos)}",
                fill=COLORES["exito"],
                font=(FUENTE, 10, "bold"),
            )
        else:
            self._lienzo.create_text(
                x_ing,
                y_cero - 10,
                text="$ 0",
                fill=COLORES["texto_secundario"],
                font=(FUENTE, 9),
            )

        # ------------------------------------------------------------------
        # 2. BARRA APILADA DE GASTOS (-Y, invertida hacia abajo desde y_cero)
        # ------------------------------------------------------------------
        x_gas = centros_x[1]
        if total_gastos > Decimal("0") and gastos_por_categoria:
            y_cursor = float(y_cero)
            for cat, monto in sorted(
                gastos_por_categoria.items(), key=lambda p: p[1], reverse=True
            ):
                if monto <= Decimal("0"):
                    continue
                h_seg = max(2.0, float(monto) * escala_neg)
                y_sig = min(float(alto - margen_inf), y_cursor + h_seg)
                color_cat = colores_gastos.get(cat, "#FBB718")
                self._lienzo.create_rectangle(
                    x_gas - ancho_barra // 2,
                    int(y_cursor),
                    x_gas + ancho_barra // 2,
                    int(y_sig),
                    fill=color_cat,
                    outline=COLORES["fondo_tarjeta"],
                    width=1,
                )
                y_cursor = y_sig

            self._lienzo.create_text(
                x_gas,
                min(alto - 22, int(y_cursor) + 11),
                text=f"-{_abreviar_monto(total_gastos)}",
                fill=COLORES["error"],
                font=(FUENTE, 10, "bold"),
            )
        else:
            self._lienzo.create_text(
                x_gas,
                y_cero + 12,
                text="$ 0",
                fill=COLORES["texto_secundario"],
                font=(FUENTE, 9),
            )

        # ------------------------------------------------------------------
        # 3. BARRA DE BALANCE NETO (Ingresos - Gastos: +Y arriba o -Y invertida abajo)
        # ------------------------------------------------------------------
        x_net = centros_x[2]
        if balance_neto > Decimal("0"):
            h_net = max(4.0, float(balance_neto) * escala_pos)
            y_fin_net = max(float(margen_sup), float(y_cero) - h_net)
            # Segmentar con los colores de las categorías de ingreso proporcionalmente
            y_c = float(y_cero)
            for cat, monto in sorted(
                ingresos_por_categoria.items(), key=lambda p: p[1], reverse=True
            ):
                if monto <= Decimal("0") or total_ingresos <= Decimal("0"):
                    continue
                prop = float(monto / total_ingresos)
                h_seg = h_net * prop
                y_s = max(y_fin_net, y_c - h_seg)
                color_cat = colores_ingresos.get(cat, COLORES["exito"])
                self._lienzo.create_rectangle(
                    x_net - ancho_barra // 2,
                    int(y_s),
                    x_net + ancho_barra // 2,
                    int(y_c),
                    fill=color_cat,
                    outline=COLORES["exito"],
                    width=2,
                )
                y_c = y_s

            self._lienzo.create_line(
                x_ing + ancho_barra // 2,
                int(y_fin_net),
                x_net + ancho_barra // 2,
                int(y_fin_net),
                fill=COLORES["exito"],
                width=1,
                dash=(4, 3),
            )
            self._lienzo.create_text(
                x_net,
                max(12, int(y_fin_net) - 10),
                text=f"+{_abreviar_monto(balance_neto)}",
                fill=COLORES["exito"],
                font=(FUENTE, 10, "bold"),
            )
        elif balance_neto < Decimal("0"):
            # Representación invertida (upside-down) en el eje negativo
            h_net = max(4.0, float(abs(balance_neto)) * escala_neg)
            y_fin_net = min(float(alto - margen_inf), float(y_cero) + h_net)
            y_c = float(y_cero)
            for cat, monto in sorted(
                gastos_por_categoria.items(), key=lambda p: p[1], reverse=True
            ):
                if monto <= Decimal("0") or total_gastos <= Decimal("0"):
                    continue
                prop = float(monto / total_gastos)
                h_seg = h_net * prop
                y_s = min(y_fin_net, y_c + h_seg)
                color_cat = colores_gastos.get(cat, COLORES["error"])
                self._lienzo.create_rectangle(
                    x_net - ancho_barra // 2,
                    int(y_c),
                    x_net + ancho_barra // 2,
                    int(y_s),
                    fill=color_cat,
                    outline=COLORES["error"],
                    width=2,
                )
                y_c = y_s

            self._lienzo.create_line(
                x_gas - ancho_barra // 2,
                int(y_fin_net),
                x_net + ancho_barra // 2,
                int(y_fin_net),
                fill=COLORES["error"],
                width=1,
                dash=(4, 3),
            )
            self._lienzo.create_text(
                x_net,
                min(alto - 22, int(y_fin_net) + 11),
                text=f"-{_abreviar_monto(abs(balance_neto))}",
                fill=COLORES["error"],
                font=(FUENTE, 10, "bold"),
            )
        else:
            self._lienzo.create_text(
                x_net,
                y_cero - 10,
                text="$ 0",
                fill=COLORES["texto"],
                font=(FUENTE, 10, "bold"),
            )

        # Línea base del Eje Cero ($0) destacada de lado a lado
        self._lienzo.create_line(
            margen_izq - 4,
            y_cero,
            ancho - margen_der,
            y_cero,
            fill=COLORES["texto"],
            width=2,
        )
        self._lienzo.create_text(
            margen_izq - 8,
            y_cero,
            text=f"0 {moneda}",
            fill=COLORES["texto"],
            font=(FUENTE, 9, "bold"),
            anchor="e",
        )

        # Etiquetas del eje X en la base
        etiquetas_x = [
            (centros_x[0], "Ingresos (+)", COLORES["exito"]),
            (centros_x[1], "Gastos (-)", COLORES["error"]),
            (centros_x[2], "Balance Neto", COLORES["acento"]),
        ]
        for cx, texto_col, color_col in etiquetas_x:
            self._lienzo.create_text(
                cx,
                alto - 10,
                text=texto_col,
                fill=color_col,
                font=(FUENTE, 10, "bold"),
            )

    def _actualizar_desglose_combinado(
        self,
        ingresos_por_categoria: Dict[str, Decimal],
        gastos_por_categoria: Dict[str, Decimal],
        total_ingresos: Decimal,
        total_gastos: Decimal,
        colores_ingresos: Dict[str, str],
        colores_gastos: Dict[str, str],
        moneda: str,
    ):
        """Muestra la lista combinada de categorías de ingresos (+) y gastos (-)
        preservando el color configurado en cada categoría."""
        for hijo in self._marco_desglose.winfo_children():
            hijo.destroy()

        if total_ingresos <= Decimal("0") and total_gastos <= Decimal("0"):
            ctk.CTkLabel(
                self._marco_desglose,
                text="No hubo ingresos ni gastos en este periodo.",
                font=(FUENTE, 12),
                text_color=COLORES["texto_secundario"],
            ).pack(pady=24)
            return

        # 1. Categorías de Ingreso (+) con sus colores establecidos
        for cat, monto in sorted(
            ingresos_por_categoria.items(), key=lambda p: p[1], reverse=True
        ):
            if monto <= Decimal("0"):
                continue
            pct = (monto / total_ingresos) * Decimal("100") if total_ingresos > Decimal("0") else Decimal("0")
            color_cat = colores_ingresos.get(cat, "#7DC98F")
            self._crear_fila_desglose(
                nombre=f"▲ {cat} (Ingreso)",
                monto_texto=f"+ {formatear_valor(monto, moneda)}",
                porcentaje_texto=f"{pct:.1f}% ing.",
                color_punto=color_cat,
                color_monto=COLORES["exito"],
            )

        # 2. Categorías de Gasto (-) con sus colores establecidos
        for cat, monto in sorted(
            gastos_por_categoria.items(), key=lambda p: p[1], reverse=True
        ):
            if monto <= Decimal("0"):
                continue
            pct = (monto / total_gastos) * Decimal("100") if total_gastos > Decimal("0") else Decimal("0")
            color_cat = colores_gastos.get(cat, "#FBB718")
            self._crear_fila_desglose(
                nombre=f"▼ {cat} (Gasto)",
                monto_texto=f"- {formatear_valor(monto, moneda)}",
                porcentaje_texto=f"{pct:.1f}% gas.",
                color_punto=color_cat,
                color_monto=COLORES["error"],
            )

    def _crear_fila_desglose(
        self,
        nombre: str,
        monto_texto: str,
        porcentaje_texto: str,
        color_punto: str,
        color_monto: str,
    ):
        fila = ctk.CTkFrame(self._marco_desglose, fg_color="transparent")
        fila.pack(fill="x", padx=8, pady=3)

        punto = ctk.CTkFrame(
            fila, width=12, height=12, corner_radius=6, fg_color=color_punto
        )
        punto.pack(side="left", padx=(4, 8))

        ctk.CTkLabel(
            fila,
            text=nombre,
            font=(FUENTE, 12, "bold"),
            text_color=COLORES["texto"],
        ).pack(side="left")

        ctk.CTkLabel(
            fila,
            text=monto_texto,
            font=(FUENTE, 12, "bold"),
            text_color=color_monto,
        ).pack(side="right", padx=6)

        ctk.CTkLabel(
            fila,
            text=porcentaje_texto,
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

        # Valoración instantánea desde memoria/caché (0ms en hilo principal) + actualización asíncrona
        if hasattr(self._gestor, "valorar_portafolio"):
            try:
                datos_inv = self._gestor.valorar_portafolio(
                    moneda_objetivo=moneda,
                    incluir_todas_convertidas=True,
                    forzar_actualizacion=False,
                    permitir_red=False,
                )
            except TypeError:
                datos_inv = self._gestor.valorar_portafolio(
                    moneda_objetivo=moneda,
                    incluir_todas_convertidas=True,
                    forzar_actualizacion=False,
                )
        else:
            datos_inv = {
                "posiciones": [],
                "valor_actual_mercado": Decimal("0"),
                "ganancia_perdida_neta": Decimal("0"),
                "rendimiento_porcentaje": Decimal("0"),
                "en_ganancia": True,
            }

        if datos_inv.get("faltan_precios_vivos") and not self._actualizando_inv_bg:
            self._actualizando_inv_bg = True

            def _cargar_inv_vivo_bg():
                try:
                    self._gestor.valorar_portafolio(
                        moneda_objetivo=moneda,
                        incluir_todas_convertidas=True,
                        forzar_actualizacion=False,
                        permitir_red=True,
                    )
                    if self.winfo_exists():
                        self.after(
                            0,
                            lambda: self._actualizar_panel_cuentas(
                                self._moneda_actual, self._incluir_todas_convertidas
                            ),
                        )
                except Exception:
                    pass
                finally:
                    self._actualizando_inv_bg = False

            threading.Thread(target=_cargar_inv_vivo_bg, daemon=True).start()
        valor_inversiones: Decimal = datos_inv.get("valor_actual_mercado", Decimal("0"))
        ganancia_inv: Decimal = datos_inv.get("ganancia_perdida_neta", Decimal("0"))
        rend_inv_pct: Decimal = datos_inv.get("rendimiento_porcentaje", Decimal("0"))
        en_ganancia_inv: bool = bool(datos_inv.get("en_ganancia", True))
        posiciones_inv = datos_inv.get("posiciones", [])

        patrimonio_total = total_cuentas + valor_inversiones
        self._etiqueta_saldo_cuentas_resumen.configure(
            text=f"Patrimonio total ({moneda}): {formatear_valor(patrimonio_total, moneda)}"
        )
        flecha_inv = "▲" if en_ganancia_inv else "▼"
        signo_inv = "+" if en_ganancia_inv else "-"
        self._etiqueta_sub_cuentas.configure(
            text=(
                f"Cuentas: {formatear_valor(total_cuentas, moneda)}   •   "
                f"Inversiones: {formatear_valor(valor_inversiones, moneda)} "
                f"({flecha_inv} {signo_inv}{abs(rend_inv_pct):.2f}%)"
            )
        )

        cuentas_mostrar = [
            (c, s)
            for c, s in cuentas_con_saldo
            if incluir_todas or c.moneda == moneda
        ]

        # 1. Sección de Cuentas Bancarias / Efectivo
        ctk.CTkLabel(
            self._contenedor_cuentas_resumen,
            text="🏦 Cuentas líquidas",
            font=(FUENTE, 12, "bold"),
            text_color=COLORES["texto_secundario"],
        ).pack(anchor="w", padx=8, pady=(4, 2))

        if not cuentas_mostrar:
            ctk.CTkLabel(
                self._contenedor_cuentas_resumen,
                text=f"No hay cuentas registradas en {moneda}.",
                font=(FUENTE, 11),
                text_color=COLORES["texto_secundario"],
            ).pack(anchor="w", padx=12, pady=(0, 6))
        else:
            for cuenta, saldo in cuentas_mostrar:
                fila = ctk.CTkFrame(
                    self._contenedor_cuentas_resumen,
                    fg_color=COLORES["fondo_tarjeta"],
                    corner_radius=8,
                )
                fila.pack(fill="x", padx=6, pady=3)

                ctk.CTkLabel(
                    fila,
                    text=f"{cuenta.nombre} ({cuenta.moneda})",
                    font=(FUENTE, 12, "bold"),
                    text_color=COLORES["texto"],
                ).pack(side="left", padx=10, pady=7)

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
                ).pack(side="right", padx=10, pady=7)

        # 2. Sección de Portafolio de Inversiones en Tiempo Real
        ctk.CTkLabel(
            self._contenedor_cuentas_resumen,
            text="📈 Portafolio de inversiones (Yahoo Finance)",
            font=(FUENTE, 12, "bold"),
            text_color=COLORES["texto_secundario"],
        ).pack(anchor="w", padx=8, pady=(10, 2))

        if not posiciones_inv:
            ctk.CTkLabel(
                self._contenedor_cuentas_resumen,
                text="Sin inversiones activas. Añade ETFs o acciones en la pestaña Inversiones.",
                font=(FUENTE, 11),
                text_color=COLORES["texto_secundario"],
            ).pack(anchor="w", padx=12, pady=(0, 6))
        else:
            for pos in posiciones_inv:
                inv = pos.inversion
                fila_i = ctk.CTkFrame(
                    self._contenedor_cuentas_resumen,
                    fg_color=COLORES["fondo_tarjeta"],
                    corner_radius=8,
                )
                fila_i.pack(fill="x", padx=6, pady=3)

                ctk.CTkLabel(
                    fila_i,
                    text=f"{inv.simbolo} · {inv.nombre[:20]}",
                    font=(FUENTE, 12, "bold"),
                    text_color=COLORES["texto"],
                ).pack(side="left", padx=10, pady=7)

                fl = "▲" if pos.en_ganancia else "▼"
                sg = "+" if pos.en_ganancia else "-"
                col_p = COLORES["exito"] if pos.en_ganancia else COLORES["error"]
                ctk.CTkLabel(
                    fila_i,
                    text=f"{formatear_valor(pos.valor_actual_convertido, moneda)} ({fl} {sg}{abs(pos.rendimiento_porcentaje):.2f}%)",
                    font=(FUENTE, 11, "bold"),
                    text_color=col_p,
                ).pack(side="right", padx=10, pady=7)


def _abreviar_monto(valor: Decimal) -> str:
    """Formatea valores para etiquetas compactas en los ejes del gráfico."""
    v = abs(float(valor))
    if v >= 1_000_000_000:
        return f"{v / 1_000_000_000:.1f}B"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if v >= 10_000:
        return f"{v / 1_000:.1f}k"
    if v == int(v):
        return f"{int(v):,}".replace(",", ".")
    return f"{v:,.2f}"
