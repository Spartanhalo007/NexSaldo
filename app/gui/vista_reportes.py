"""Módulo de Reportes, Salud Financiera, Radiografía Patrimonial y Centro de Exportación.

Integra las 5 capacidades analíticas exclusivas que cruzan información de Cuentas, Ingresos,
Gastos, Transferencias e Inversiones (abiertas y cerradas):
1. Centro de Exportación de Estados de Cuenta (.xlsx multi-hoja, .csv y .html imprimible/PDF).
2. Salud Financiera (Tasa de Ahorro %, Fondo de Emergencia en meses de supervivencia,
   Ritmo de Gasto Diario + Proyección, y P&L Total Abierto + Realizado con Win Rate %).
3. Radiografía de Patrimonio y Riesgo (Liquidez en Cuentas vs. Capital Invertido,
   Exposición Cambiaria por Divisa nativa y Concentración por Plataforma/Cuenta/Activo).
4. Comparativa Mes a Mes y Detección de Anomalías (variación Δ% frente al periodo anterior
   en Ingresos, Gastos y por cada Categoría).
5. Libro de Posiciones Cerradas y Ganancias Realizadas (historial de ventas ejecutadas con
   '💰 Vender' para control de rendimientos realizados e impuestos).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
import os
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Callable, Dict, List, Optional, Sequence, Tuple
import webbrowser
import customtkinter as ctk

from app.gui.dialogo_periodo import (
    DialogoPeriodo,
    calcular_rango_preset,
    desplazar_rango,
)
from app.gui.estilos import COLORES, FUENTE
from app.gui.formato import formatear_valor
from app.gui.selector_moneda import BarraFiltroMoneda

PALETA_DIVISAS = ("#FBB718", "#2ECC71", "#408FD1", "#9B7EDE", "#E86F9A")
FORMATOS_EXPORTACION: Dict[str, Tuple[str, List[Tuple[str, str]], str]] = {
    "xlsx": (".xlsx", [("Excel Workbook (.xlsx)", "*.xlsx")], "estado_cuenta_nexsaldo.xlsx"),
    "csv": (".csv", [("Archivo CSV (.csv)", "*.csv")], "estado_cuenta_nexsaldo.csv"),
    "html": (".html", [("Estado de Cuenta Imprimible (.html)", "*.html")], "estado_cuenta_nexsaldo.html"),
}


def _limpiar_hijos(contenedor) -> None:
    """Destruye todos los widgets hijos de un contenedor de forma segura."""
    for hijo in list(contenedor.winfo_children()):
        hijo.destroy()


def _color_por_umbrales(valor: Decimal, umbral_exito: str, umbral_medio: str) -> str:
    """Devuelve el color semántico (éxito, acento o error) según dos umbrales numéricos."""
    if valor >= Decimal(umbral_exito):
        return COLORES["exito"]
    return COLORES["acento"] if valor >= Decimal(umbral_medio) else COLORES["error"]


def _dibujar_barra_apilada(
    lienzo: tk.Canvas,
    x_ini: int,
    x_fin: int,
    y_top: int,
    y_bot: int,
    segmentos: Sequence[Tuple[float, str]],
) -> None:
    """Dibuja una barra horizontal segmentada proporcionalmente en un `tk.Canvas`."""
    ancho_util = max(100, x_fin - x_ini)
    activos = [(pct, col) for pct, col in segmentos if pct > 0]
    if not activos:
        lienzo.create_rectangle(x_ini, y_top, x_fin, y_bot, fill=COLORES["boton_lateral"], outline="")
        return

    cursor_x = x_ini
    for idx, (pct, color) in enumerate(activos):
        ancho_seg = (x_fin - cursor_x) if idx == len(activos) - 1 else int(ancho_util * (pct / 100.0))
        if ancho_seg > 0:
            lienzo.create_rectangle(
                cursor_x,
                y_top,
                cursor_x + ancho_seg,
                y_bot,
                fill=color,
                outline=COLORES["fondo_tarjeta"],
                width=1,
            )
            cursor_x += ancho_seg


class VistaReportes(ctk.CTkFrame):
    """Vista integral del módulo Reportes con selector de periodo, filtro mundial de divisas,
    indicadores de Salud Financiera, Radiografía de Patrimonio/Divisas, Comparativa Mes a Mes,
    Historial de Posiciones Cerradas y Centro de Exportación (.xlsx / .csv / .html)."""

    def __init__(self, master, gestor, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._gestor = gestor

        hoy = date.today()
        self._preset_periodo = "ESTE_MES"
        self._fecha_inicio, self._fecha_fin, self._texto_periodo = calcular_rango_preset(
            "ESTE_MES", referencia=hoy
        )
        self._moneda_actual = "COP"
        self._incluir_todas_convertidas = True
        self._ultimo_reporte: Dict[str, object] = {}

        self._construir_encabezado()
        self._construir_cuerpo()
        self.refrescar()

    # ------------------------------------------------------------------
    # Construcción de la Interfaz
    # ------------------------------------------------------------------
    def _construir_encabezado(self) -> None:
        cabecera = ctk.CTkFrame(self, fg_color="transparent")
        cabecera.pack(fill="x", pady=(0, 10))

        fila_sup = ctk.CTkFrame(cabecera, fg_color="transparent")
        fila_sup.pack(fill="x")

        col_tit = ctk.CTkFrame(fila_sup, fg_color="transparent")
        col_tit.pack(side="left")

        ctk.CTkLabel(
            col_tit,
            text="📊 Reportes y Salud Financiera",
            font=(FUENTE, 22, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w")

        ctk.CTkLabel(
            col_tit,
            text="Diagnóstico cruzado de liquidez, ahorro, exposición cambiaria, anomalías y estados de cuenta",
            font=(FUENTE, 11),
            text_color=COLORES["texto_secundario"],
        ).pack(anchor="w")

        # Selector de período estilo píldora: ◄ [ 📅 Noviembre de 2026 ▾ ] ►
        marco_periodo = ctk.CTkFrame(fila_sup, fg_color="transparent")
        marco_periodo.pack(side="right")

        self._crear_boton_flecha(marco_periodo, "◄", -1)
        self._boton_periodo = ctk.CTkButton(
            marco_periodo,
            text=f"📅  {self._texto_periodo}  ▾",
            height=32,
            corner_radius=8,
            fg_color=COLORES["fondo_tarjeta"],
            hover_color=COLORES["boton_lateral"],
            border_width=1,
            border_color=COLORES["acento"],
            text_color=COLORES["texto"],
            font=(FUENTE, 12, "bold"),
            command=self._abrir_selector_periodo,
        )
        self._boton_periodo.pack(side="left", padx=5)
        self._crear_boton_flecha(marco_periodo, "►", 1)

        # Barra de filtro de moneda + Botones del Centro de Exportación
        barra_herramientas = ctk.CTkFrame(
            cabecera, fg_color=COLORES["fondo_tarjeta"], corner_radius=10
        )
        barra_herramientas.pack(fill="x", pady=(8, 0))

        fila_herr = ctk.CTkFrame(barra_herramientas, fg_color="transparent")
        fila_herr.pack(fill="x", padx=12, pady=7)

        self._barra_moneda = BarraFiltroMoneda(
            fila_herr,
            gestor=self._gestor,
            al_cambiar=self._al_cambiar_filtro_moneda,
            moneda_inicial="COP",
            mostrar_modo=True,
        )
        self._barra_moneda.pack(side="left")

        marco_export = ctk.CTkFrame(fila_herr, fg_color="transparent")
        marco_export.pack(side="right")

        botones_export = (
            ("🖨️ Estado de Cuenta (HTML/PDF)", "html", False),
            ("📄 Exportar CSV", "csv", False),
            ("📥 Exportar Excel (.xlsx)", "xlsx", True),
        )
        for texto_btn, fmt_key, es_primario in botones_export:
            ctk.CTkButton(
                marco_export,
                text=texto_btn,
                height=30,
                corner_radius=8,
                fg_color=COLORES["acento"] if es_primario else COLORES["boton_lateral"],
                hover_color=COLORES["acento_hover"] if es_primario else COLORES["hover_lateral"],
                text_color=COLORES["campo_texto"] if es_primario else COLORES["texto"],
                font=(FUENTE, 11, "bold"),
                command=lambda f=fmt_key: self._exportar(f),
            ).pack(side="right", padx=3)

    def _crear_boton_flecha(self, contenedor, simbolo: str, direccion: int) -> None:
        ctk.CTkButton(
            contenedor,
            text=simbolo,
            width=32,
            height=32,
            corner_radius=8,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 12, "bold"),
            command=lambda d=direccion: self._desplazar_periodo(d),
        ).pack(side="left", padx=3)

    def _construir_cuerpo(self) -> None:
        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        self._scroll.pack(fill="both", expand=True)

        # 1. Fila de 4 tarjetas KPI de Salud Financiera
        self._marco_kpis = ctk.CTkFrame(self._scroll, fg_color="transparent")
        self._marco_kpis.pack(fill="x", pady=(0, 10))
        for col_idx in range(4):
            self._marco_kpis.grid_columnconfigure(col_idx, weight=1)

        self._kpi_ahorro = self._crear_tarjeta_kpi(
            self._marco_kpis, 0, "💰 Tasa de Ahorro", "0.0%", "Sin datos en el periodo"
        )
        self._kpi_emergencia = self._crear_tarjeta_kpi(
            self._marco_kpis, 1, "🛡️ Fondo de Emergencia", "0.0 meses", "Liquidez vs. gasto mensual"
        )
        self._kpi_ritmo = self._crear_tarjeta_kpi(
            self._marco_kpis, 2, "🔥 Ritmo de Gasto Diario", "$ 0", "Proyección mensual: $ 0"
        )
        self._kpi_pnl_total = self._crear_tarjeta_kpi(
            self._marco_kpis, 3, "📈 P&L Total Inversiones", "$ 0", "Abierto + Realizado"
        )

        # 2. Fila central de 2 columnas: Radiografía de Patrimonio/Riesgo (Izq) y Comparativa Mes a Mes (Der)
        fila_central = ctk.CTkFrame(self._scroll, fg_color="transparent")
        fila_central.pack(fill="x", pady=(0, 10))
        fila_central.grid_columnconfigure(0, weight=1)
        fila_central.grid_columnconfigure(1, weight=1)

        self._tarjeta_radiografia = ctk.CTkFrame(
            fila_central, fg_color=COLORES["fondo_tarjeta"], corner_radius=14
        )
        self._tarjeta_radiografia.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        ctk.CTkLabel(
            self._tarjeta_radiografia,
            text="🧭 Radiografía de Patrimonio y Exposición al Riesgo",
            font=(FUENTE, 15, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w", padx=16, pady=(12, 4))

        self._lbl_patrimonio_neto = ctk.CTkLabel(
            self._tarjeta_radiografia,
            text="Patrimonio Neto Total: $ 0",
            font=(FUENTE, 14, "bold"),
            text_color=COLORES["acento"],
        )
        self._lbl_patrimonio_neto.pack(anchor="w", padx=16, pady=(0, 6))

        self._lienzo_radiografia = tk.Canvas(
            self._tarjeta_radiografia,
            width=440,
            height=135,
            bg=COLORES["fondo_tarjeta"],
            highlightthickness=0,
        )
        self._lienzo_radiografia.pack(fill="x", padx=16, pady=(2, 6))

        self._contenedor_exposicion = ctk.CTkFrame(
            self._tarjeta_radiografia, fg_color=COLORES["boton_lateral"], corner_radius=10
        )
        self._contenedor_exposicion.pack(fill="both", expand=True, padx=16, pady=(4, 14))

        self._tarjeta_mom = ctk.CTkFrame(
            fila_central, fg_color=COLORES["fondo_tarjeta"], corner_radius=14
        )
        self._tarjeta_mom.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        ctk.CTkLabel(
            self._tarjeta_mom,
            text="📉 Comparativa vs. Periodo Anterior y Anomalías",
            font=(FUENTE, 15, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w", padx=16, pady=(12, 4))

        self._lbl_resumen_mom = ctk.CTkLabel(
            self._tarjeta_mom,
            text="Comparando frente al periodo inmediatamente anterior...",
            font=(FUENTE, 12, "bold"),
            text_color=COLORES["texto_secundario"],
            justify="left",
            wraplength=430,
        )
        self._lbl_resumen_mom.pack(anchor="w", padx=16, pady=(0, 8))

        self._contenedor_mom = ctk.CTkScrollableFrame(
            self._tarjeta_mom,
            fg_color=COLORES["boton_lateral"],
            corner_radius=10,
            height=220,
        )
        self._contenedor_mom.pack(fill="both", expand=True, padx=16, pady=(0, 14))

        # 3. Sección Inferior: Historial de Posiciones Cerradas (P&L Realizado / Impuestos)
        self._tarjeta_cerradas = ctk.CTkFrame(
            self._scroll, fg_color=COLORES["fondo_tarjeta"], corner_radius=14
        )
        self._tarjeta_cerradas.pack(fill="x", pady=(0, 10))

        cab_cerradas = ctk.CTkFrame(self._tarjeta_cerradas, fg_color="transparent")
        cab_cerradas.pack(fill="x", padx=16, pady=(12, 4))

        ctk.CTkLabel(
            cab_cerradas,
            text="🏛️ Historial de Posiciones Cerradas y Ganancias Realizadas (P&L Realizado)",
            font=(FUENTE, 15, "bold"),
            text_color=COLORES["texto"],
        ).pack(side="left")

        self._lbl_total_realizado = ctk.CTkLabel(
            cab_cerradas,
            text="Total realizado: $ 0",
            font=(FUENTE, 13, "bold"),
            text_color=COLORES["exito"],
        )
        self._lbl_total_realizado.pack(side="right")

        self._contenedor_cerradas = ctk.CTkFrame(
            self._tarjeta_cerradas, fg_color=COLORES["boton_lateral"], corner_radius=10
        )
        self._contenedor_cerradas.pack(fill="x", padx=16, pady=(4, 14))

    def _crear_tarjeta_kpi(
        self, contenedor, col_idx: int, titulo: str, valor_ini: str, sub_ini: str
    ) -> Dict[str, ctk.CTkLabel]:
        marco = ctk.CTkFrame(
            contenedor, fg_color=COLORES["fondo_tarjeta"], corner_radius=12
        )
        marco.grid(
            row=0,
            column=col_idx,
            sticky="nsew",
            padx=(0 if col_idx == 0 else 5, 0 if col_idx == 3 else 5),
        )

        lbl_tit = ctk.CTkLabel(
            marco,
            text=titulo,
            font=(FUENTE, 12, "bold"),
            text_color=COLORES["texto_secundario"],
        )
        lbl_tit.pack(anchor="w", padx=14, pady=(10, 2))

        lbl_val = ctk.CTkLabel(
            marco,
            text=valor_ini,
            font=(FUENTE, 18, "bold"),
            text_color=COLORES["texto"],
        )
        lbl_val.pack(anchor="w", padx=14, pady=(0, 2))

        lbl_sub = ctk.CTkLabel(
            marco,
            text=sub_ini,
            font=(FUENTE, 11),
            text_color=COLORES["texto_secundario"],
            justify="left",
            wraplength=210,
        )
        lbl_sub.pack(anchor="w", padx=14, pady=(0, 10))

        return {"titulo": lbl_tit, "valor": lbl_val, "sub": lbl_sub}

    # ------------------------------------------------------------------
    # Eventos de Período, Moneda y Exportación
    # ------------------------------------------------------------------
    def _abrir_selector_periodo(self) -> None:
        DialogoPeriodo(
            self,
            fecha_inicio=self._fecha_inicio,
            fecha_fin=self._fecha_fin,
            preset_inicial=self._preset_periodo,
            al_aplicar=self._al_aplicar_periodo,
        )

    def _al_aplicar_periodo(
        self, fecha_ini: date, fecha_fin: date, preset: str, etiqueta: str
    ) -> None:
        self._fecha_inicio, self._fecha_fin = fecha_ini, fecha_fin
        self._preset_periodo, self._texto_periodo = preset, etiqueta
        self._boton_periodo.configure(text=f"📅  {self._texto_periodo}  ▾")
        self.refrescar()

    def _desplazar_periodo(self, direccion: int) -> None:
        self._fecha_inicio, self._fecha_fin, self._texto_periodo = desplazar_rango(
            self._preset_periodo, self._fecha_inicio, self._fecha_fin, direccion
        )
        self._boton_periodo.configure(text=f"📅  {self._texto_periodo}  ▾")
        self.refrescar()

    def _al_cambiar_filtro_moneda(self, moneda: str, incluir_todas: bool) -> None:
        self._moneda_actual = moneda
        self._incluir_todas_convertidas = incluir_todas
        self.refrescar()

    def _exportar(self, formato: str) -> None:
        ext_def, tipos, nombre_sug = FORMATOS_EXPORTACION.get(
            formato, FORMATOS_EXPORTACION["xlsx"]
        )
        ruta = filedialog.asksaveasfilename(
            title=f"Exportar Estado de Cuenta ({self._texto_periodo})",
            defaultextension=ext_def,
            initialfile=nombre_sug,
            filetypes=tipos,
            parent=self,
        )
        if not ruta:
            return

        try:
            ruta_final = self._gestor.exportar_reporte_completo(
                ruta_destino=ruta,
                fecha_inicio=self._fecha_inicio,
                fecha_fin=self._fecha_fin,
                moneda_objetivo=self._moneda_actual,
                incluir_todas_convertidas=self._incluir_todas_convertidas,
                formato=formato,
            )
            if formato == "html" and os.path.exists(ruta_final):
                try:
                    webbrowser.open(f"file://{os.path.abspath(ruta_final)}")
                except Exception:
                    pass
            messagebox.showinfo(
                "Estado de Cuenta exportado",
                f"Se generó exitosamente el reporte en:\n{ruta_final}",
                parent=self,
            )
        except Exception as error:
            messagebox.showerror("Error al exportar reporte", str(error), parent=self)

    # ------------------------------------------------------------------
    # Actualización de Datos y Renderizado
    # ------------------------------------------------------------------
    def refrescar(self) -> None:
        mon = self._moneda_actual
        try:
            rep = self._gestor.generar_radiografia_y_salud_financiera(
                fecha_inicio=self._fecha_inicio,
                fecha_fin=self._fecha_fin,
                moneda_objetivo=mon,
                incluir_todas_convertidas=self._incluir_todas_convertidas,
            )
        except Exception:
            return

        self._ultimo_reporte = rep
        salud = rep["salud_financiera"]
        self._actualizar_tarjetas_kpi(salud, mon)
        self._renderizar_radiografia(rep["radiografia"], mon)
        self._renderizar_comparativa_mom(rep["comparativa_mom"], mon)
        self._renderizar_posiciones_cerradas(
            rep["posiciones_cerradas"], salud["pnl_realizado"], mon
        )

    def _actualizar_tarjetas_kpi(self, salud: Dict[str, object], mon: str) -> None:
        tasa_ahorro: Decimal = salud["tasa_ahorro_pct"]  # type: ignore[assignment]
        ahorro_neto: Decimal = salud["ahorro_neto"]  # type: ignore[assignment]
        self._kpi_ahorro["valor"].configure(
            text=f"{tasa_ahorro:+.1f}% ({formatear_valor(ahorro_neto, mon)})",
            text_color=_color_por_umbrales(tasa_ahorro, "10", "0"),
        )
        self._kpi_ahorro["sub"].configure(text=str(salud["diagnostico_ahorro"]))

        meses_em: Optional[Decimal] = salud["meses_supervivencia"]  # type: ignore[assignment]
        if meses_em is None:
            self._kpi_emergencia["valor"].configure(text="∞ meses", text_color=COLORES["exito"])
            self._kpi_emergencia["sub"].configure(text="Sin gastos en el periodo • Liquidez intacta")
        else:
            meta_txt = (
                "Óptimo (≥ 6 meses)"
                if meses_em >= Decimal("6")
                else ("Aceptable (3–6 meses)" if meses_em >= Decimal("3") else "Bajo (< 3 meses recomendados)")
            )
            self._kpi_emergencia["valor"].configure(
                text=f"{meses_em:.1f} meses",
                text_color=_color_por_umbrales(meses_em, "6", "3"),
            )
            self._kpi_emergencia["sub"].configure(text=meta_txt)

        gasto_diario: Decimal = salud["gasto_diario_promedio"]  # type: ignore[assignment]
        proyeccion_mes: Decimal = salud["proyeccion_gasto_mensual"]  # type: ignore[assignment]
        self._kpi_ritmo["valor"].configure(
            text=f"{formatear_valor(gasto_diario, mon)} / día",
            text_color=COLORES["texto"],
        )
        self._kpi_ritmo["sub"].configure(
            text=f"Proyección a 30 días: {formatear_valor(proyeccion_mes, mon)}"
        )

        pnl_combinado: Decimal = salud["pnl_total_combinado"]  # type: ignore[assignment]
        pnl_abierto: Decimal = salud["pnl_abierto"]  # type: ignore[assignment]
        pnl_realizado: Decimal = salud["pnl_realizado"]  # type: ignore[assignment]
        win_rate: Decimal = salud["win_rate_pct"]  # type: ignore[assignment]
        signo_pnl = "+" if pnl_combinado >= Decimal("0") else "-"
        self._kpi_pnl_total["valor"].configure(
            text=f"{signo_pnl}{formatear_valor(abs(pnl_combinado), mon)}",
            text_color=COLORES["exito"] if pnl_combinado >= Decimal("0") else COLORES["error"],
        )
        self._kpi_pnl_total["sub"].configure(
            text=(
                f"Abierto: {formatear_valor(pnl_abierto, mon)} · "
                f"Realizado: {formatear_valor(pnl_realizado, mon)} ({win_rate:.0f}% Win Rate)"
            )
        )

    def _renderizar_radiografia(self, radio: Dict[str, object], mon: str) -> None:
        patrimonio: Decimal = radio["patrimonio_total"]  # type: ignore[assignment]
        liquidez: Decimal = radio["liquidez_cuentas"]  # type: ignore[assignment]
        invertido: Decimal = radio["valor_inversiones"]  # type: ignore[assignment]
        pct_liq: Decimal = radio["pct_liquidez"]  # type: ignore[assignment]
        pct_inv: Decimal = radio["pct_inversiones"]  # type: ignore[assignment]
        exp_divisas: List[Dict[str, object]] = radio["exposicion_divisas"]  # type: ignore[assignment]
        alerta_riesgo = str(radio["alerta_concentracion"])

        self._lbl_patrimonio_neto.configure(
            text=(
                f"Patrimonio Neto ({mon}): {formatear_valor(patrimonio, mon)}   "
                f"•   Liquidez: {pct_liq:.1f}%  |  Inversiones: {pct_inv:.1f}%"
            )
        )

        self._lienzo_radiografia.delete("all")
        ancho = max(420, int(self._lienzo_radiografia.winfo_width() or 440))
        x_ini, x_fin = 16, ancho - 16

        # Barra 1: Liquidez vs. Inversiones
        self._lienzo_radiografia.create_text(
            x_ini,
            14,
            text=(
                f"🏦 Liquidez ({formatear_valor(liquidez, mon)} · {pct_liq:.1f}%)  vs.  "
                f"📈 Inversiones ({formatear_valor(invertido, mon)} · {pct_inv:.1f}%)"
            ),
            fill=COLORES["texto"],
            font=(FUENTE, 10, "bold"),
            anchor="w",
        )
        segmentos_liq_inv = (
            [(float(pct_liq), "#408FD1"), (float(pct_inv), "#2ECC71")]
            if patrimonio > Decimal("0")
            else []
        )
        _dibujar_barra_apilada(self._lienzo_radiografia, x_ini, x_fin, 26, 48, segmentos_liq_inv)

        # Barra 2: Exposición Cambiaria
        texto_div = "  •  ".join(
            f"{d['moneda']}: {d['porcentaje']:.1f}%" for d in exp_divisas[:4]
        ) or "Sin saldo registrado"
        self._lienzo_radiografia.create_text(
            x_ini,
            68,
            text=f"🌍 Exposición Cambiaria: {texto_div}",
            fill=COLORES["texto"],
            font=(FUENTE, 10, "bold"),
            anchor="w",
        )
        segmentos_div = (
            [
                (float(item_d["porcentaje"]), PALETA_DIVISAS[idx % len(PALETA_DIVISAS)])
                for idx, item_d in enumerate(exp_divisas)
            ]
            if patrimonio > Decimal("0")
            else []
        )
        _dibujar_barra_apilada(self._lienzo_radiografia, x_ini, x_fin, 80, 102, segmentos_div)

        self._lienzo_radiografia.create_text(
            x_ini,
            118,
            text=alerta_riesgo,
            fill=COLORES["acento"] if "⚠️" in alerta_riesgo else COLORES["exito"],
            font=(FUENTE, 10, "bold"),
            anchor="w",
        )

        _limpiar_hijos(self._contenedor_exposicion)
        dist_entidades: List[Dict[str, object]] = radio["distribucion_entidades"]  # type: ignore[assignment]
        if not dist_entidades:
            ctk.CTkLabel(
                self._contenedor_exposicion,
                text="Añade cuentas o inversiones para visualizar el desglose patrimonial.",
                font=(FUENTE, 11),
                text_color=COLORES["texto_secundario"],
            ).pack(pady=14)
            return

        for ent in dist_entidades[:6]:
            fila = ctk.CTkFrame(self._contenedor_exposicion, fg_color="transparent")
            fila.pack(fill="x", padx=10, pady=3)

            icono = "📈" if ent["tipo"] == "INVERSION" else "🏦"
            ctk.CTkLabel(
                fila,
                text=f"{icono} {ent['nombre']} ({ent['moneda_origen']})",
                font=(FUENTE, 11, "bold"),
                text_color=COLORES["texto"],
            ).pack(side="left")

            ctk.CTkLabel(
                fila,
                text=f"{formatear_valor(ent['valor_convertido'], mon)} ({ent['porcentaje']:.1f}%)",
                font=(FUENTE, 11, "bold"),
                text_color=COLORES["acento"],
            ).pack(side="right")

    def _renderizar_comparativa_mom(self, mom: Dict[str, object], mon: str) -> None:
        _limpiar_hijos(self._contenedor_mom)

        etiqueta_prev = str(mom["etiqueta_periodo_anterior"])
        var_gas_pct: Optional[Decimal] = mom["variacion_gastos_pct"]  # type: ignore[assignment]
        var_ing_pct: Optional[Decimal] = mom["variacion_ingresos_pct"]  # type: ignore[assignment]

        partes_mom = [f"Periodo previo ({etiqueta_prev}):"]
        if var_ing_pct is not None:
            partes_mom.append(f"Ingresos {var_ing_pct:+.1f}%")
        if var_gas_pct is not None:
            partes_mom.append(f"Gastos {var_gas_pct:+.1f}%")
        self._lbl_resumen_mom.configure(text="  •  ".join(partes_mom))

        cambios_cat: List[Dict[str, object]] = mom["categorias_comparadas"]  # type: ignore[assignment]
        if not cambios_cat:
            ctk.CTkLabel(
                self._contenedor_mom,
                text="Sin gastos en el periodo actual ni en el periodo anterior para comparar.",
                font=(FUENTE, 11),
                text_color=COLORES["texto_secundario"],
            ).pack(pady=24)
            return

        for item in cambios_cat:
            fila = ctk.CTkFrame(
                self._contenedor_mom, fg_color=COLORES["fondo_tarjeta"], corner_radius=8
            )
            fila.pack(fill="x", padx=6, pady=3)

            cat = str(item["categoria"])
            actual_val: Decimal = item["actual"]  # type: ignore[assignment]
            prev_val: Decimal = item["anterior"]  # type: ignore[assignment]
            delta_pct: Optional[Decimal] = item["variacion_pct"]  # type: ignore[assignment]
            prefijo = "🚨 " if item["es_anomalia"] else ""

            ctk.CTkLabel(
                fila,
                text=f"{prefijo}{cat}",
                font=(FUENTE, 12, "bold"),
                text_color=COLORES["texto"],
            ).pack(side="left", padx=10, pady=6)

            badge_txt, col_badge = self._etiqueta_y_color_variacion(delta_pct)
            ctk.CTkLabel(
                fila,
                text=f"{formatear_valor(actual_val, mon)}  (prev: {formatear_valor(prev_val, mon)})  •  {badge_txt}",
                font=(FUENTE, 11, "bold"),
                text_color=col_badge,
            ).pack(side="right", padx=10, pady=6)

    @staticmethod
    def _etiqueta_y_color_variacion(delta_pct: Optional[Decimal]) -> Tuple[str, str]:
        if delta_pct is None:
            return "🆕 Nuevo este periodo", COLORES["acento"]
        if delta_pct > Decimal("0"):
            return f"▲ +{delta_pct:.1f}% vs. prev.", COLORES["error"]
        if delta_pct < Decimal("0"):
            return f"▼ {delta_pct:.1f}% vs. prev.", COLORES["exito"]
        return "= 0.0%", COLORES["texto_secundario"]

    def _renderizar_posiciones_cerradas(
        self, cerradas: List[Dict[str, object]], pnl_realizado: Decimal, mon: str
    ) -> None:
        _limpiar_hijos(self._contenedor_cerradas)

        signo = "+" if pnl_realizado >= Decimal("0") else "-"
        col_tot = COLORES["exito"] if pnl_realizado >= Decimal("0") else COLORES["error"]
        self._lbl_total_realizado.configure(
            text=f"Ganancia/Pérdida Realizada ({mon}): {signo}{formatear_valor(abs(pnl_realizado), mon)}",
            text_color=col_tot,
        )

        if not cerradas:
            ctk.CTkLabel(
                self._contenedor_cerradas,
                text=(
                    "Aún no has cerrado/vendido posiciones con '💰 Vender'. "
                    "Cuando vendas una acción o cripto en Inversiones, su ganancia realizada aparecerá aquí."
                ),
                font=(FUENTE, 11),
                text_color=COLORES["texto_secundario"],
            ).pack(pady=16)
            return

        for op in cerradas:
            fila = ctk.CTkFrame(
                self._contenedor_cerradas, fg_color=COLORES["fondo_tarjeta"], corner_radius=8
            )
            fila.pack(fill="x", padx=8, pady=4)

            sim = str(op.get("simbolo", "ACTIVO"))
            nom = str(op.get("nombre", sim))
            fecha_cierre = str(op.get("fecha_cierre", ""))
            cuenta_dest = str(op.get("cuenta_destino", "Cuenta"))
            inv_orig: Decimal = op.get("monto_invertido", Decimal("0"))  # type: ignore[assignment]
            val_venta: Decimal = op.get("valor_venta", Decimal("0"))  # type: ignore[assignment]
            mon_op = str(op.get("moneda_origen", "USD"))
            ganancia_op: Decimal = op.get("ganancia_realizada", Decimal("0"))  # type: ignore[assignment]
            pct_op = (
                (ganancia_op / inv_orig * Decimal("100"))
                if inv_orig > Decimal("0")
                else Decimal("0")
            )

            ctk.CTkLabel(
                fila,
                text=f"📅 {fecha_cierre}  •  {sim} ({nom[:20]})  →  Acreditado en: {cuenta_dest}",
                font=(FUENTE, 12, "bold"),
                text_color=COLORES["texto"],
            ).pack(side="left", padx=10, pady=7)

            en_gan = ganancia_op >= Decimal("0")
            sg = "+" if en_gan else "-"
            fl = "▲" if en_gan else "▼"
            ctk.CTkLabel(
                fila,
                text=(
                    f"Invertido: {formatear_valor(inv_orig, mon_op)}  |  "
                    f"Venta: {formatear_valor(val_venta, mon_op)}  |  "
                    f"{fl} {sg}{formatear_valor(abs(ganancia_op), mon_op)} ({sg}{abs(pct_op):.2f}%)"
                ),
                font=(FUENTE, 11, "bold"),
                text_color=COLORES["exito"] if en_gan else COLORES["error"],
            ).pack(side="right", padx=10, pady=7)
