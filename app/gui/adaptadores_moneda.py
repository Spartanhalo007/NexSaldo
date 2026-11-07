"""Envuelve VistaCuentas, VistaMovimientos y DialogoCuenta para inyectar:
1) El filtro mundial de divisas (COP + 4 últimas usadas + lista A-Z) y el modo
   'Solo esta moneda' vs 'Todo convertido'.
2) El selector de periodo estilo Shopify (`◀ [ 📅 Noviembre de 2026 ▾ ] ▶`) exactamente
   dentro de la tarjeta 'Historial de transferencias' en Cuentas (donde estaban los radio
   buttons 'Mostrar: Día, Semana, Mes, Año, Período') y en Ingresos."""

from datetime import date
from decimal import Decimal
import customtkinter as ctk

from app.gui.dialogo_cuenta import DialogoCuenta
from app.gui.dialogo_periodo_shopify import (
    DialogoPeriodoShopify,
    calcular_rango_preset,
    desplazar_rango,
)
from app.gui.estilos import COLORES, FUENTE
from app.gui.formato import formatear_valor
from app.gui.selector_moneda import BarraFiltroMoneda, DialogoSelectorDivisa
from app.gui.vista_cuentas import VistaCuentas
from app.gui.vista_movimientos import ETIQUETAS_TIPO, VistaMovimientos
from app.modelo.divisas import etiqueta_divisa, extraer_codigo_divisa

_parche_dialogos_aplicado = False


def activar_selector_mundial_en_dialogo_cuenta():
    """Extiende DialogoCuenta para que su desplegable de moneda tenga las últimas 5 divisas
    (empezando por COP), todas las divisas del mundo en orden alfabético y un botón 🌍."""
    global _parche_dialogos_aplicado
    if _parche_dialogos_aplicado:
        return
    _parche_dialogos_aplicado = True

    init_original = DialogoCuenta.__init__
    al_aniadir_original = DialogoCuenta._al_aniadir

    def _nuevo_init(self, master, gestor, al_crear, **kwargs):
        init_original(self, master, gestor, al_crear, **kwargs)
        try:
            opciones = gestor.obtener_opciones_selector_divisas()
            self._campo_moneda.configure(values=opciones, width=185)
            self._campo_moneda.set(etiqueta_divisa("COP"))

            contenedor_moneda = self._campo_moneda.master
            self._campo_moneda.pack_configure(side="left", padx=(0, 6))
            ctk.CTkButton(
                contenedor_moneda,
                text="🌍 Todas (A-Z)",
                width=95,
                height=28,
                corner_radius=8,
                fg_color=COLORES["boton_lateral"],
                hover_color=COLORES["hover_lateral"],
                text_color=COLORES["texto"],
                font=(FUENTE, 11, "bold"),
                command=lambda: DialogoSelectorDivisa(
                    self,
                    gestor=gestor,
                    moneda_actual=extraer_codigo_divisa(self._campo_moneda.get()),
                    al_seleccionar=lambda cod: self._campo_moneda.set(etiqueta_divisa(cod)),
                ),
            ).pack(side="left")
        except Exception:
            pass

    def _nuevo_al_aniadir(self):
        try:
            codigo = extraer_codigo_divisa(self._campo_moneda.get())
            self._campo_moneda.set(codigo)
        except Exception:
            pass
        return al_aniadir_original(self)

    DialogoCuenta.__init__ = _nuevo_init
    DialogoCuenta._al_aniadir = _nuevo_al_aniadir


def _encontrar_fila_radios_historial(vista_cuentas: VistaCuentas):
    """Encuentra el CTkFrame (`fila_filtros`) dentro de la tarjeta 'Historial de transferencias'
    que contiene los CTkRadioButton ('Dia', 'Semana', 'Mes', 'Año', 'Periodo')."""
    resultado = []

    def _buscar(widget):
        try:
            hijos = widget.winfo_children()
        except Exception:
            return
        if any(isinstance(h, ctk.CTkRadioButton) for h in hijos):
            resultado.append(widget)
            return
        for h in hijos:
            _buscar(h)

    _buscar(vista_cuentas)
    return resultado[0] if resultado else None


class VistaCuentasConDivisa(VistaCuentas):
    """Subclase de VistaCuentas que añade la BarraFiltroMoneda arriba y reemplaza la fila
    de radio buttons ('Mostrar: Dia, Semana, Mes, Año, Periodo') dentro de la tarjeta
    'Historial de transferencias' por el selector clicable estilo Shopify."""

    def __init__(self, master, gestor, **kwargs):
        activar_selector_mundial_en_dialogo_cuenta()
        hoy = date.today()
        self._preset_shopify = "ESTE_MES"
        self._ini_shopify, self._fin_shopify, self._texto_shopify = calcular_rango_preset(
            "ESTE_MES", referencia=hoy
        )
        self._moneda_filtro = "COP"
        self._incluir_todas_convertidas = False
        self._barra_moneda = None
        self._boton_periodo_shopify = None
        self._etiqueta_total_convertido = None
        super().__init__(master, gestor, **kwargs)
        self._fecha_desde = self._ini_shopify
        self._fecha_hasta = self._fin_shopify
        self._inyectar_barra_moneda_y_periodo()
        self.refrescar()

    def _rango_del_filtro(self):
        """Devuelve siempre el rango activo seleccionado en el control estilo Shopify."""
        return self._ini_shopify, self._fin_shopify

    def _inyectar_barra_moneda_y_periodo(self):
        # 1. En la tarjeta "Historial de transferencias", reemplazar los radio buttons por el selector Shopify
        if hasattr(self, "_marco_periodo") and self._marco_periodo is not None:
            try:
                self._marco_periodo.pack_forget()
            except Exception:
                pass

        fila_filtros_historial = _encontrar_fila_radios_historial(self)
        if fila_filtros_historial is not None:
            for hijo in list(fila_filtros_historial.winfo_children()):
                try:
                    hijo.pack_forget()
                except Exception:
                    pass

            ctk.CTkLabel(
                fila_filtros_historial,
                text="Periodo:",
                font=(FUENTE, 12, "bold"),
                text_color=COLORES["texto_secundario"],
            ).pack(side="left", padx=(0, 8), pady=4)

            ctk.CTkButton(
                fila_filtros_historial,
                text="◀",
                width=30,
                height=30,
                corner_radius=8,
                fg_color=COLORES["boton_lateral"],
                hover_color=COLORES["hover_lateral"],
                text_color=COLORES["texto"],
                font=(FUENTE, 12, "bold"),
                command=lambda: self._desplazar_periodo_shopify(-1),
            ).pack(side="left", padx=3, pady=4)

            self._boton_periodo_shopify = ctk.CTkButton(
                fila_filtros_historial,
                text=f"📅  {self._texto_shopify}  ▾",
                height=30,
                corner_radius=8,
                fg_color=COLORES["boton_lateral"],
                hover_color=COLORES["hover_lateral"],
                border_width=1,
                border_color=COLORES["acento"],
                text_color=COLORES["texto"],
                font=(FUENTE, 12, "bold"),
                command=self._abrir_selector_periodo_shopify,
            )
            self._boton_periodo_shopify.pack(side="left", padx=4, pady=4)

            ctk.CTkButton(
                fila_filtros_historial,
                text="▶",
                width=30,
                height=30,
                corner_radius=8,
                fg_color=COLORES["boton_lateral"],
                hover_color=COLORES["hover_lateral"],
                text_color=COLORES["texto"],
                font=(FUENTE, 12, "bold"),
                command=lambda: self._desplazar_periodo_shopify(1),
            ).pack(side="left", padx=3, pady=4)

        # 2. Barra superior de filtro de moneda (COP + 4 últimas + Todas A-Z)
        marco_filtro = ctk.CTkFrame(
            self, fg_color=COLORES["fondo_tarjeta"], corner_radius=12
        )
        hijos = self.winfo_children()
        if hijos:
            marco_filtro.pack(fill="x", pady=(0, 8), before=hijos[0])
        else:
            marco_filtro.pack(fill="x", pady=(0, 8))

        fila = ctk.CTkFrame(marco_filtro, fg_color="transparent")
        fila.pack(fill="x", padx=14, pady=8)

        self._barra_moneda = BarraFiltroMoneda(
            fila,
            gestor=self._gestor,
            al_cambiar=self._al_cambiar_moneda_vista,
            moneda_inicial="COP",
            mostrar_modo=True,
        )
        self._barra_moneda.pack(side="left")

        self._etiqueta_total_convertido = ctk.CTkLabel(
            fila,
            text="",
            font=(FUENTE, 12, "bold"),
            text_color=COLORES["acento"],
        )
        self._etiqueta_total_convertido.pack(side="right", padx=10)

    def _abrir_selector_periodo_shopify(self):
        DialogoPeriodoShopify(
            self,
            fecha_inicio=self._ini_shopify,
            fecha_fin=self._fin_shopify,
            preset_inicial=self._preset_shopify,
            al_aplicar=self._al_aplicar_periodo_shopify,
        )

    def _al_aplicar_periodo_shopify(
        self, fecha_ini: date, fecha_fin: date, preset: str, etiqueta: str
    ):
        self._ini_shopify = fecha_ini
        self._fin_shopify = fecha_fin
        self._preset_shopify = preset
        self._texto_shopify = etiqueta
        self._fecha_desde = fecha_ini
        self._fecha_hasta = fecha_fin
        if self._boton_periodo_shopify is not None:
            self._boton_periodo_shopify.configure(text=f"📅  {self._texto_shopify}  ▾")
        self._refrescar_historial()

    def _desplazar_periodo_shopify(self, direccion: int):
        ini, fin, etiqueta = desplazar_rango(
            self._preset_shopify, self._ini_shopify, self._fin_shopify, direccion
        )
        self._ini_shopify = ini
        self._fin_shopify = fin
        self._texto_shopify = etiqueta
        self._fecha_desde = ini
        self._fecha_hasta = fin
        if self._boton_periodo_shopify is not None:
            self._boton_periodo_shopify.configure(text=f"📅  {self._texto_shopify}  ▾")
        self._refrescar_historial()

    def _al_cambiar_moneda_vista(self, nueva_moneda: str, incluir_todas: bool):
        self._moneda_filtro = nueva_moneda
        self._incluir_todas_convertidas = incluir_todas
        self.refrescar()

    def _refrescar_historial(self):
        """Consulta las transferencias en el rango Shopify activo y aplica el filtro/conversión de moneda."""
        inicio, fin = self._rango_del_filtro()
        try:
            transferencias = self._gestor.obtener_transferencias(inicio, fin)
        except Exception:
            return super()._refrescar_historial()

        if not hasattr(self, "_tabla_transferencias"):
            return super()._refrescar_historial()

        for elemento in self._tabla_transferencias.get_children():
            self._tabla_transferencias.delete(elemento)
        self._ids_fila_transferencia.clear()

        for fila in transferencias:
            (
                id_transferencia,
                fecha,
                origen,
                destino,
                valor,
                moneda,
                comentarios,
                imagen,
            ) = fila

            if not self._incluir_todas_convertidas and moneda != self._moneda_filtro:
                continue

            if self._incluir_todas_convertidas and moneda != self._moneda_filtro:
                try:
                    val_conv = self._gestor.convertir_entre_monedas(
                        valor, moneda, self._moneda_filtro
                    )
                    valor_texto = f"{formatear_valor(val_conv, self._moneda_filtro)} ({formatear_valor(valor, moneda)})"
                except Exception:
                    valor_texto = formatear_valor(valor, moneda)
            else:
                valor_texto = formatear_valor(valor, moneda)

            elemento = self._tabla_transferencias.insert(
                "",
                "end",
                values=(
                    fecha.isoformat() if hasattr(fecha, "isoformat") else fecha,
                    origen,
                    destino,
                    valor_texto,
                    moneda,
                    ("📎 " if imagen else "") + (comentarios or ""),
                ),
            )
            self._ids_fila_transferencia[elemento] = fila

    def refrescar(self):
        try:
            todas_cuentas = self._gestor.obtener_cuentas()
        except Exception:
            return super().refrescar()

        if self._incluir_todas_convertidas:
            cuentas_filtradas = todas_cuentas
            total_unificado = self._gestor.calcular_total_cuentas_en_moneda(
                todas_cuentas,
                moneda_objetivo=self._moneda_filtro,
                incluir_todas_convertidas=True,
            )
            if self._etiqueta_total_convertido is not None:
                self._etiqueta_total_convertido.configure(
                    text=f"Total unificado ({self._moneda_filtro}): {formatear_valor(total_unificado, self._moneda_filtro)}"
                )
        else:
            cuentas_filtradas = [
                (c, s) for c, s in todas_cuentas if c.moneda == self._moneda_filtro
            ]
            total_moneda = self._gestor.calcular_total_cuentas_en_moneda(
                cuentas_filtradas,
                moneda_objetivo=self._moneda_filtro,
                incluir_todas_convertidas=False,
            )
            if self._etiqueta_total_convertido is not None:
                self._etiqueta_total_convertido.configure(
                    text=f"Total solo {self._moneda_filtro}: {formatear_valor(total_moneda, self._moneda_filtro)}"
                )

        self._refrescar_totales(cuentas_filtradas)
        self._refrescar_cuentas(cuentas_filtradas)
        self._refrescar_historial()


class VistaMovimientosConDivisa(VistaMovimientos):
    """Subclase de VistaMovimientos (Ingresos) que añade el selector mundial de divisas y el
    selector de periodo estilo Shopify (`◀ [ 📅 Noviembre de 2026 ▾ ] ▶`)."""

    def __init__(self, master, gestor, filtro_tipo=None, titulo="Movimientos", **kwargs):
        hoy = date.today()
        self._preset_shopify = "ESTE_MES"
        self._ini_shopify, self._fin_shopify, self._texto_shopify = calcular_rango_preset(
            "ESTE_MES", referencia=hoy
        )
        self._moneda_filtro = "COP"
        self._incluir_todas_convertidas = False
        self._barra_moneda = None
        self._boton_periodo_shopify = None
        super().__init__(
            master, gestor, filtro_tipo=filtro_tipo, titulo=titulo, **kwargs
        )
        self._configurar_selector_mundial_y_periodo()
        self.refrescar()

    def _configurar_selector_mundial_y_periodo(self):
        try:
            opciones = self._gestor.obtener_opciones_selector_divisas()
            self._campo_moneda.configure(values=opciones)
            self._campo_moneda.set(etiqueta_divisa("COP"))
        except Exception:
            pass

        marco_filtro = ctk.CTkFrame(
            self, fg_color=COLORES["fondo_tarjeta"], corner_radius=12
        )
        hijos = self.winfo_children()
        if hijos:
            marco_filtro.pack(fill="x", pady=(0, 8), before=hijos[0])
        else:
            marco_filtro.pack(fill="x", pady=(0, 8))

        fila = ctk.CTkFrame(marco_filtro, fg_color="transparent")
        fila.pack(fill="x", padx=14, pady=8)

        self._barra_moneda = BarraFiltroMoneda(
            fila,
            gestor=self._gestor,
            al_cambiar=self._al_cambiar_moneda_vista,
            moneda_inicial="COP",
            mostrar_modo=True,
        )
        self._barra_moneda.pack(side="left")

        marco_shopify = ctk.CTkFrame(fila, fg_color="transparent")
        marco_shopify.pack(side="right")

        ctk.CTkButton(
            marco_shopify,
            text="◀",
            width=32,
            height=32,
            corner_radius=8,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 12, "bold"),
            command=lambda: self._desplazar_periodo_shopify(-1),
        ).pack(side="left", padx=3)

        self._boton_periodo_shopify = ctk.CTkButton(
            marco_shopify,
            text=f"📅  {self._texto_shopify}  ▾",
            height=32,
            corner_radius=8,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            border_width=1,
            border_color=COLORES["acento"],
            text_color=COLORES["texto"],
            font=(FUENTE, 12, "bold"),
            command=self._abrir_selector_periodo_shopify,
        )
        self._boton_periodo_shopify.pack(side="left", padx=4)

        ctk.CTkButton(
            marco_shopify,
            text="▶",
            width=32,
            height=32,
            corner_radius=8,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 12, "bold"),
            command=lambda: self._desplazar_periodo_shopify(1),
        ).pack(side="left", padx=3)

    def _abrir_selector_periodo_shopify(self):
        DialogoPeriodoShopify(
            self,
            fecha_inicio=self._ini_shopify,
            fecha_fin=self._fin_shopify,
            preset_inicial=self._preset_shopify,
            al_aplicar=self._al_aplicar_periodo_shopify,
        )

    def _al_aplicar_periodo_shopify(
        self, fecha_ini: date, fecha_fin: date, preset: str, etiqueta: str
    ):
        self._ini_shopify = fecha_ini
        self._fin_shopify = fecha_fin
        self._preset_shopify = preset
        self._texto_shopify = etiqueta
        if self._boton_periodo_shopify is not None:
            self._boton_periodo_shopify.configure(text=f"📅  {self._texto_shopify}  ▾")
        self.refrescar()

    def _desplazar_periodo_shopify(self, direccion: int):
        ini, fin, etiqueta = desplazar_rango(
            self._preset_shopify, self._ini_shopify, self._fin_shopify, direccion
        )
        self._ini_shopify = ini
        self._fin_shopify = fin
        self._texto_shopify = etiqueta
        if self._boton_periodo_shopify is not None:
            self._boton_periodo_shopify.configure(text=f"📅  {self._texto_shopify}  ▾")
        self.refrescar()

    def _al_cambiar_moneda_vista(self, nueva_moneda: str, incluir_todas: bool):
        self._moneda_filtro = nueva_moneda
        self._incluir_todas_convertidas = incluir_todas
        self.refrescar()

    def _al_guardar(self):
        try:
            codigo = extraer_codigo_divisa(self._campo_moneda.get())
            self._campo_moneda.set(codigo)
        except Exception:
            pass
        resultado = super()._al_guardar()
        try:
            opciones = self._gestor.obtener_opciones_selector_divisas()
            self._campo_moneda.configure(values=opciones)
            self._campo_moneda.set(etiqueta_divisa(self._moneda_filtro))
        except Exception:
            pass
        return resultado

    def refrescar(self):
        try:
            todos = self._gestor.obtener_movimientos(
                self._filtro_tipo,
                fecha_inicio=self._ini_shopify,
                fecha_fin=self._fin_shopify,
            )
        except Exception:
            return super().refrescar()

        if self._incluir_todas_convertidas:
            movimientos = todos
        else:
            movimientos = [m for m in todos if m.moneda == self._moneda_filtro]

        for elemento in self._tabla.get_children():
            self._tabla.delete(elemento)
        self._ids_tabla.clear()

        total_convertido = Decimal("0")
        for mov in movimientos:
            if self._incluir_todas_convertidas and mov.moneda != self._moneda_filtro:
                try:
                    val_conv = self._gestor.convertir_entre_monedas(
                        mov.valor, mov.moneda, self._moneda_filtro
                    )
                    total_convertido += val_conv
                    valor_mostrar = f"{formatear_valor(val_conv, self._moneda_filtro)} ({formatear_valor(mov.valor, mov.moneda)})"
                except Exception:
                    total_convertido += mov.valor
                    valor_mostrar = formatear_valor(mov.valor, mov.moneda)
            else:
                total_convertido += mov.valor
                valor_mostrar = formatear_valor(mov.valor, mov.moneda)

            elemento = self._tabla.insert(
                "",
                "end",
                values=(
                    mov.fecha.isoformat(),
                    ETIQUETAS_TIPO.get(mov.tipo_movimiento, mov.tipo_movimiento),
                    mov.categoria,
                    valor_mostrar,
                    mov.moneda,
                    mov.descripcion or "",
                ),
            )
            self._ids_tabla[elemento] = mov.id

        if not movimientos:
            self._etiqueta_totales.configure(
                text=f"Sin movimientos en {self._moneda_filtro} ({self._texto_shopify})."
            )
        elif self._incluir_todas_convertidas:
            self._etiqueta_totales.configure(
                text=f"Total unificado ({self._moneda_filtro} · {self._texto_shopify}): {formatear_valor(total_convertido, self._moneda_filtro)}"
            )
        else:
            self._etiqueta_totales.configure(
                text=f"Total solo {self._moneda_filtro} ({self._texto_shopify}): {formatear_valor(total_convertido, self._moneda_filtro)}"
            )
