"""Vista principal del Módulo de Gastos para NexSaldo con selector de periodo estilo píldora de fechas
(`◀ [ 📅 Noviembre de 2026 ▾ ] ▶`) y filtro de todas las divisas del mundo."""

from datetime import date
import threading
from decimal import Decimal
import tkinter as tk
from tkinter import messagebox
from typing import Dict, Optional
import customtkinter as ctk

from app.gestor.gestor_financiero import GestorFinanciero
from app.gui.dialogo_gasto import DialogoGasto
from app.gui.dialogo_periodo import (
    DialogoPeriodo,
    calcular_rango_preset,
    desplazar_rango,
)
from app.gui.estilos import COLORES, COLORES_GRAFICA, FUENTE
from app.gui.formato import fecha_legible, formatear_valor
from app.gui.iconos import icono_ctk
from app.gui.selector_moneda import BarraFiltroMoneda

TAMANO_DONA = 240
GROSOR_DONA = 34


class VistaGastos(ctk.CTkFrame):
    """Muestra la gráfica circular de gastos por periodo usando el selector clicable estilo píldora de fechas
    (Hoy/Día, Semana, Mes, Quarter, Año, YTD, Periodo personalizado), el filtro mundial de divisas
    ('Solo esta moneda' o 'Todo convertido'), el botón amarillo 'Añadir gasto', el desglose por
    categorías y la lista de gastos."""

    def __init__(self, master, gestor: GestorFinanciero, **kwargs):
        super().__init__(master, fg_color=COLORES["fondo_contenido"], **kwargs)
        self._gestor = gestor

        hoy = date.today()
        self._preset_periodo = "ESTE_MES"
        self._fecha_inicio, self._fecha_fin, self._texto_periodo = calcular_rango_preset(
            "ESTE_MES", referencia=hoy
        )
        self._moneda_grafica = "COP"  # COP siempre por defecto
        self._incluir_todas_convertidas = False

        self._construir_interfaz()
        self._refrescar_vista()

    def _construir_interfaz(self):
        contenedor = ctk.CTkScrollableFrame(self, fg_color="transparent")
        contenedor.pack(fill="both", expand=True, padx=24, pady=18)

        # ==================================================================
        # 1. CABECERA, SELECTOR DE PERIODO ESTILO PÍLDORA DE FECHAS Y BOTÓN AMARILLO "Añadir gasto"
        # ==================================================================
        fila_superior = ctk.CTkFrame(contenedor, fg_color="transparent")
        fila_superior.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            fila_superior,
            text="Gastos",
            font=(FUENTE, 26, "bold"),
            text_color=COLORES["texto"],
        ).pack(side="left")

        ctk.CTkButton(
            fila_superior,
            text="Añadir gasto",
            width=175,
            height=42,
            corner_radius=10,
            fg_color=COLORES["acento"],
            hover_color=COLORES["acento_hover"],
            text_color=COLORES["campo_texto"],
            font=(FUENTE, 15, "bold"),
            command=self._abrir_dialogo_anadir_gasto,
        ).pack(side="right")

        # Selector clicable estilo píldora de fechas: ◀ [ 📅 Noviembre de 2026 ▾ ] ▶
        marco_periodo = ctk.CTkFrame(fila_superior, fg_color="transparent")
        marco_periodo.pack(side="right", padx=(0, 14))

        ctk.CTkButton(
            marco_periodo,
            text="◀",
            width=34,
            height=36,
            corner_radius=8,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 12, "bold"),
            command=lambda: self._desplazar_periodo(-1),
        ).pack(side="left", padx=4)

        self._boton_periodo = ctk.CTkButton(
            marco_periodo,
            text=f"📅  {self._texto_periodo}  ▾",
            height=36,
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
            marco_periodo,
            text="▶",
            width=34,
            height=36,
            corner_radius=8,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 12, "bold"),
            command=lambda: self._desplazar_periodo(1),
        ).pack(side="left", padx=4)

        # ==================================================================
        # 2. BARRA DE MONEDA MUNDIAL (COP + 4 últimas + Todas A-Z) Y MODO
        # ==================================================================
        marco_moneda = ctk.CTkFrame(
            contenedor, fg_color=COLORES["fondo_tarjeta"], corner_radius=12
        )
        marco_moneda.pack(fill="x", pady=(0, 16))

        fila_barra_moneda = ctk.CTkFrame(marco_moneda, fg_color="transparent")
        fila_barra_moneda.pack(fill="x", padx=16, pady=10)

        self._barra_moneda = BarraFiltroMoneda(
            fila_barra_moneda,
            gestor=self._gestor,
            al_cambiar=self._al_cambiar_filtro_moneda,
            moneda_inicial="COP",
            mostrar_modo=True,
        )
        self._barra_moneda.pack(side="left")

        # ==================================================================
        # 3. PANEL CENTRAL: GRÁFICA CIRCULAR + DESGLOSE POR CATEGORÍAS
        # ==================================================================
        fila_central = ctk.CTkFrame(contenedor, fg_color="transparent")
        fila_central.pack(fill="x", pady=(0, 16))
        fila_central.grid_columnconfigure(0, weight=1)
        fila_central.grid_columnconfigure(1, weight=1)

        tarjeta_dona = ctk.CTkFrame(
            fila_central, fg_color=COLORES["fondo_tarjeta"], corner_radius=14
        )
        tarjeta_dona.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        self._titulo_rango = ctk.CTkLabel(
            tarjeta_dona,
            text=f"Gastos · {self._texto_periodo}",
            font=(FUENTE, 15, "bold"),
            text_color=COLORES["texto"],
        )
        self._titulo_rango.pack(pady=(14, 6))

        self._lienzo = tk.Canvas(
            tarjeta_dona,
            width=TAMANO_DONA,
            height=TAMANO_DONA,
            bg=COLORES["fondo_tarjeta"],
            highlightthickness=0,
        )
        self._lienzo.pack(pady=(4, 14))

        tarjeta_desglose = ctk.CTkFrame(
            fila_central, fg_color=COLORES["fondo_tarjeta"], corner_radius=14
        )
        tarjeta_desglose.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        ctk.CTkLabel(
            tarjeta_desglose,
            text="Gastos por categoría en el periodo",
            font=(FUENTE, 15, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w", padx=16, pady=(14, 8))

        self._contenedor_desglose = ctk.CTkScrollableFrame(
            tarjeta_desglose, fg_color="transparent", height=230
        )
        self._contenedor_desglose.pack(fill="both", expand=True, padx=10, pady=(0, 12))

        # ==================================================================
        # 4. HISTORIAL DETALLADO DE GASTOS DEL PERIODO
        # ==================================================================
        tarjeta_historial = ctk.CTkFrame(
            contenedor, fg_color=COLORES["fondo_tarjeta"], corner_radius=14
        )
        tarjeta_historial.pack(fill="both", expand=True)

        ctk.CTkLabel(
            tarjeta_historial,
            text="Movimientos de gastos registrados en este periodo",
            font=(FUENTE, 15, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w", padx=16, pady=(14, 8))

        self._contenedor_historial = ctk.CTkFrame(
            tarjeta_historial, fg_color="transparent"
        )
        self._contenedor_historial.pack(fill="both", expand=True, padx=16, pady=(0, 16))

    # ------------------------------------------------------------------
    # Manejo del Selector de Periodo estilo píldora de fechas y Moneda
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
        self._boton_periodo.configure(text=f"📅  {self._texto_periodo}  ▾")
        self._refrescar_vista()

    def _desplazar_periodo(self, direccion: int):
        ini, fin, etiqueta = desplazar_rango(
            self._preset_periodo, self._fecha_inicio, self._fecha_fin, direccion
        )
        self._fecha_inicio = ini
        self._fecha_fin = fin
        self._texto_periodo = etiqueta
        self._boton_periodo.configure(text=f"📅  {self._texto_periodo}  ▾")
        self._refrescar_vista()

    def _al_cambiar_filtro_moneda(self, nueva_moneda: str, incluir_todas: bool):
        self._moneda_grafica = nueva_moneda
        self._incluir_todas_convertidas = incluir_todas
        self._refrescar_vista()

    # ------------------------------------------------------------------
    # Gráfica Circular (Dona) y Actualización de Datos
    # ------------------------------------------------------------------
    def refrescar(self):
        self._refrescar_vista()

    def _refrescar_vista(self, _desde_hilo_tasas: bool = False):
        fecha_ini = self._fecha_inicio
        fecha_fin = self._fecha_fin
        sufijo_modo = (
            f"Todo convertido a {self._moneda_grafica}"
            if self._incluir_todas_convertidas
            else f"Solo {self._moneda_grafica}"
        )
        self._titulo_rango.configure(
            text=f"Gastos · {self._texto_periodo} ({sufijo_modo})"
        )

        todos_movimientos = self._gestor.obtener_movimientos(
            "GASTO", fecha_inicio=fecha_ini, fecha_fin=fecha_fin
        )
        if self._incluir_todas_convertidas and not _desde_hilo_tasas and hasattr(self._gestor, "tiene_tasa_en_sesion"):
            monedas_faltantes = {
                m.moneda
                for m in todos_movimientos
                if m.moneda != self._moneda_grafica
                and not self._gestor.tiene_tasa_en_sesion(m.moneda, self._moneda_grafica)
            }
            if monedas_faltantes:
                mon_dest_bg = self._moneda_grafica

                def _precargar_tasas():
                    for mon_orig in monedas_faltantes:
                        try:
                            self._gestor.obtener_tasa_cambio(mon_orig, mon_dest_bg, forzar_actualizacion=False)
                        except Exception:
                            pass
                    if self.winfo_exists():
                        self.after(0, lambda: self._refrescar_vista(_desde_hilo_tasas=True))

                threading.Thread(target=_precargar_tasas, daemon=True).start()
                return

        resumen_global = self._gestor.resumen_gastos_periodo(
            fecha_inicio=fecha_ini,
            fecha_fin=fecha_fin,
            moneda_objetivo=self._moneda_grafica,
            incluir_todas_convertidas=self._incluir_todas_convertidas,
        )
        datos_moneda = resumen_global.get(
            self._moneda_grafica,
            {"total": Decimal("0"), "por_categoria": {}, "colores": {}, "simbolos": {}},
        )
        total: Decimal = datos_moneda["total"]  # type: ignore[assignment]
        por_cat: Dict[str, Decimal] = datos_moneda["por_categoria"]  # type: ignore[assignment]
        colores: Dict[str, str] = datos_moneda["colores"]  # type: ignore[assignment]
        simbolos: Dict[str, str] = datos_moneda["simbolos"]  # type: ignore[assignment]

        self._dibujar_dona(total, por_cat, colores)
        self._renderizar_desglose(total, por_cat, colores, simbolos)
        self._renderizar_historial(fecha_ini, fecha_fin, movimientos_precargados=todos_movimientos)

    def _dibujar_dona(
        self,
        total: Decimal,
        por_categoria: Dict[str, Decimal],
        colores: Dict[str, str],
    ):
        self._lienzo.delete("all")
        margen = 22
        x0, y0 = margen, margen
        x1, y1 = TAMANO_DONA - margen, TAMANO_DONA - margen
        centro = TAMANO_DONA // 2

        if total <= Decimal("0") or not por_categoria:
            self._lienzo.create_oval(
                x0,
                y0,
                x1,
                y1,
                outline=COLORES["boton_lateral"],
                width=GROSOR_DONA,
            )
            self._lienzo.create_text(
                centro,
                centro,
                text="No hubo gastos\neste periodo",
                fill=COLORES["texto_secundario"],
                font=(FUENTE, 12, "bold"),
                justify="center",
            )
            return

        items_ordenados = sorted(
            por_categoria.items(), key=lambda par: par[1], reverse=True
        )
        if len(items_ordenados) == 1:
            cat_unica, _ = items_ordenados[0]
            color_unico = colores.get(cat_unica, COLORES_GRAFICA[0])
            self._lienzo.create_oval(
                x0,
                y0,
                x1,
                y1,
                outline=color_unico,
                width=GROSOR_DONA,
            )
        else:
            angulo_inicio = 90.0
            for idx, (cat, monto) in enumerate(items_ordenados):
                proporcion = float(monto / total)
                extension = -proporcion * 360.0
                color_seg = colores.get(
                    cat, COLORES_GRAFICA[idx % len(COLORES_GRAFICA)]
                )
                self._lienzo.create_arc(
                    x0,
                    y0,
                    x1,
                    y1,
                    start=angulo_inicio,
                    extent=extension,
                    style="arc",
                    outline=color_seg,
                    width=GROSOR_DONA,
                )
                angulo_inicio += extension

        monto_formateado = formatear_valor(total, self._moneda_grafica)
        self._lienzo.create_text(
            centro,
            centro - 10,
            text="Total gastado",
            fill=COLORES["texto_secundario"],
            font=(FUENTE, 11),
            justify="center",
        )
        self._lienzo.create_text(
            centro,
            centro + 12,
            text=monto_formateado,
            fill=COLORES["texto"],
            font=(FUENTE, 14, "bold"),
            justify="center",
        )

    def _renderizar_desglose(
        self,
        total: Decimal,
        por_categoria: Dict[str, Decimal],
        colores: Dict[str, str],
        simbolos: Dict[str, str],
    ):
        for hijo in self._contenedor_desglose.winfo_children():
            hijo.destroy()

        if total <= Decimal("0") or not por_categoria:
            ctk.CTkLabel(
                self._contenedor_desglose,
                text="No hubo gastos este periodo.",
                font=(FUENTE, 13),
                text_color=COLORES["texto_secundario"],
            ).pack(pady=40)
            return

        for cat, monto in sorted(
            por_categoria.items(), key=lambda par: par[1], reverse=True
        ):
            porcentaje = (monto / total) * Decimal("100")
            color_cat = colores.get(cat, COLORES["acento"])
            simbolo_cat = simbolos.get(cat, "mercado")

            fila = ctk.CTkFrame(
                self._contenedor_desglose,
                fg_color=COLORES["boton_lateral"],
                corner_radius=10,
            )
            fila.pack(fill="x", padx=4, pady=4)

            insignia = ctk.CTkButton(
                fila,
                text="",
                width=36,
                height=36,
                corner_radius=18,
                fg_color=color_cat,
                hover_color=color_cat,
                image=icono_ctk(simbolo_cat, color="#10241C", tamano=20),
                state="disabled",
            )
            insignia.pack(side="left", padx=(10, 10), pady=8)

            ctk.CTkLabel(
                fila,
                text=cat,
                font=(FUENTE, 13, "bold"),
                text_color=COLORES["texto"],
            ).pack(side="left")

            ctk.CTkLabel(
                fila,
                text=formatear_valor(monto, self._moneda_grafica),
                font=(FUENTE, 13, "bold"),
                text_color=COLORES["texto"],
            ).pack(side="right", padx=(10, 12))

            ctk.CTkLabel(
                fila,
                text=f"{porcentaje:.1f}%",
                font=(FUENTE, 12),
                text_color=COLORES["texto_secundario"],
            ).pack(side="right", padx=6)

    def _renderizar_historial(
        self,
        fecha_ini: Optional[date],
        fecha_fin: Optional[date],
        movimientos_precargados=None,
    ):
        for hijo in self._contenedor_historial.winfo_children():
            hijo.destroy()

        todos_movimientos = (
            movimientos_precargados
            if movimientos_precargados is not None
            else self._gestor.obtener_movimientos(
                "GASTO", fecha_inicio=fecha_ini, fecha_fin=fecha_fin
            )
        )
        if self._incluir_todas_convertidas:
            movimientos = todos_movimientos
        else:
            movimientos = [
                m for m in todos_movimientos if m.moneda == self._moneda_grafica
            ]

        if not movimientos:
            ctk.CTkLabel(
                self._contenedor_historial,
                text="No hubo gastos este periodo.",
                font=(FUENTE, 13),
                text_color=COLORES["texto_secundario"],
            ).pack(pady=24)
            return

        mapa_cat = {
            c.nombre: c for c in self._gestor.obtener_categorias_detalladas("GASTO")
        }
        mapa_cuentas = {c.id: c.nombre for c, _ in self._gestor.obtener_cuentas()}

        for mov in movimientos:
            cat_info = mapa_cat.get(mov.categoria)
            color_cat = cat_info.color if cat_info else COLORES["acento"]
            simbolo_cat = cat_info.simbolo if cat_info else "mercado"

            item = ctk.CTkFrame(
                self._contenedor_historial,
                fg_color=COLORES["boton_lateral"],
                corner_radius=10,
            )
            item.pack(fill="x", pady=4)

            circulo = ctk.CTkButton(
                item,
                text="",
                width=42,
                height=42,
                corner_radius=21,
                fg_color=color_cat,
                hover_color=color_cat,
                image=icono_ctk(simbolo_cat, color="#10241C", tamano=22),
                state="disabled",
            )
            circulo.pack(side="left", padx=12, pady=10)

            col_info = ctk.CTkFrame(item, fg_color="transparent")
            col_info.pack(side="left", fill="x", expand=True, pady=8)

            titulo_linea = f"{mov.categoria} [{mov.moneda}]"
            if mov.cuenta_id and mov.cuenta_id in mapa_cuentas:
                titulo_linea += f"  •  Cuenta: {mapa_cuentas[mov.cuenta_id]}"
            if mov.es_programado:
                titulo_linea += f"  •  ⏱ Programado ({mov.frecuencia or 'MENSUAL'})"

            ctk.CTkLabel(
                col_info,
                text=titulo_linea,
                font=(FUENTE, 13, "bold"),
                text_color=COLORES["texto"],
            ).pack(anchor="w")

            detalles = [fecha_legible(mov.fecha)]
            if mov.descripcion:
                detalles.append(mov.descripcion)
            if mov.etiquetas:
                detalles.append(" ".join(f"#{e}" for e in mov.etiquetas))
            if mov.imagen:
                detalles.append("📷 Foto adjunta")

            ctk.CTkLabel(
                col_info,
                text="  |  ".join(detalles),
                font=(FUENTE, 11),
                text_color=COLORES["texto_secundario"],
            ).pack(anchor="w")

            btn_eliminar = ctk.CTkButton(
                item,
                text="Eliminar",
                width=76,
                height=28,
                corner_radius=6,
                fg_color="transparent",
                hover_color=COLORES["hover_lateral"],
                text_color=COLORES["error"],
                font=(FUENTE, 11, "bold"),
                command=lambda mid=mov.id: self._confirmar_eliminar(mid),
            )
            btn_eliminar.pack(side="right", padx=(6, 12))

            if self._incluir_todas_convertidas and mov.moneda != self._moneda_grafica:
                try:
                    val_conv = self._gestor.convertir_entre_monedas(
                        mov.valor, mov.moneda, self._moneda_grafica
                    )
                    texto_monto = f"- {formatear_valor(val_conv, self._moneda_grafica)} ({formatear_valor(mov.valor, mov.moneda)})"
                except Exception:
                    texto_monto = f"- {formatear_valor(mov.valor, mov.moneda)}"
            else:
                texto_monto = f"- {formatear_valor(mov.valor, mov.moneda)}"

            ctk.CTkLabel(
                item,
                text=texto_monto,
                font=(FUENTE, 13, "bold"),
                text_color=COLORES["error"],
            ).pack(side="right", padx=8)

    def _abrir_dialogo_anadir_gasto(self):
        DialogoGasto(
            self,
            gestor=self._gestor,
            al_guardar=self._al_guardar_nuevo_gasto,
        )

    def _al_guardar_nuevo_gasto(self, movimiento):
        self._moneda_grafica = movimiento.moneda
        self._barra_moneda.establecer_moneda(movimiento.moneda)
        self._refrescar_vista()

    def _confirmar_eliminar(self, id_movimiento: Optional[int]):
        if id_movimiento is None:
            return
        confirmar = messagebox.askyesno(
            "Eliminar gasto",
            "¿Deseas eliminar este gasto de forma permanente?",
            parent=self,
        )
        if confirmar:
            self._gestor.eliminar_movimiento(id_movimiento)
            self._refrescar_vista()