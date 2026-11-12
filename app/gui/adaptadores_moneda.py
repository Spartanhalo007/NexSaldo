"""Envuelve VistaCuentas, VistaMovimientos y DialogoCuenta para inyectar:
1) El filtro mundial de divisas (COP + 4 últimas usadas + lista A-Z) y el modo
   'Solo esta moneda' vs 'Todo convertido'.
2) El selector de periodo estilo píldora de fechas (`◄ [ 📅 Noviembre de 2026 ▾ ] ►`) exactamente
   dentro de la tarjeta 'Historial de transferencias' en Cuentas (donde estaban los radio
   buttons 'Mostrar: Día, Semana, Mes, Año, Período') y en Ingresos."""

from datetime import date
from decimal import Decimal
import importlib
import sys
from typing import Callable, Optional
import customtkinter as ctk

try:
    import aplicar_cambios_nexsaldo

    aplicar_cambios_nexsaldo.aplicar_todos_los_parches(silencioso=True)
    for _mod_name in ("app.gestor.gestor_financiero", "app.gui.vista_inversiones"):
        if _mod_name in sys.modules:
            importlib.reload(sys.modules[_mod_name])
except Exception:
    pass

from app.gui.dialogo_cuenta import DialogoCuenta
from app.gui.dialogo_periodo import (
    DialogoPeriodo,
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


def _construir_controles_pildora_periodo(
    contenedor,
    texto_periodo: str,
    al_desplazar: Callable[[int], None],
    al_abrir: Callable[[], None],
    alto: int = 30,
    con_etiqueta: bool = False,
) -> ctk.CTkButton:
    """Construye los controles reutilizables de navegación de periodo (`◄ [ 📅 Periodo ▾ ] ►`)."""
    if con_etiqueta:
        ctk.CTkLabel(
            contenedor,
            text="Periodo:",
            font=(FUENTE, 12, "bold"),
            text_color=COLORES["texto_secundario"],
        ).pack(side="left", padx=(0, 8), pady=4)

    for simbolo, dir_paso in (("◄", -1), ("►", 1)):
        if dir_paso == 1:
            boton_central = ctk.CTkButton(
                contenedor,
                text=f"📅 {texto_periodo} ▾",
                height=alto,
                corner_radius=8,
                fg_color=COLORES["boton_lateral"],
                hover_color=COLORES["hover_lateral"],
                border_width=1,
                border_color=COLORES["acento"],
                text_color=COLORES["texto"],
                font=(FUENTE, 12, "bold"),
                command=al_abrir,
            )
            boton_central.pack(side="left", padx=4, pady=4 if con_etiqueta else 0)

        ctk.CTkButton(
            contenedor,
            text=simbolo,
            width=alto,
            height=alto,
            corner_radius=8,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 12, "bold"),
            command=lambda d=dir_paso: al_desplazar(d),
        ).pack(side="left", padx=3, pady=4 if con_etiqueta else 0)

    return boton_central


def activar_selector_mundial_en_dialogo_cuenta() -> None:
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
            self._campo_moneda.set(extraer_codigo_divisa(self._campo_moneda.get()))
        except Exception:
            pass
        try:
            if hasattr(self, "_campo_saldo") and not (self._campo_saldo.get() or "").strip():
                self._campo_saldo.insert(0, "0")
        except Exception:
            pass
        return al_aniadir_original(self)

    DialogoCuenta.__init__ = _nuevo_init
    DialogoCuenta._al_aniadir = _nuevo_al_aniadir


def _encontrar_fila_radios_historial(vista_cuentas: VistaCuentas):
    """Encuentra el CTkFrame (`fila_filtros`) dentro de la tarjeta 'Historial de transferencias'
    que contiene los CTkRadioButton ('Día', 'Semana', 'Mes', 'Año', 'Periodo')."""
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
    de radio buttons ('Mostrar: Día, Semana, Mes, Año, Período') dentro de la tarjeta
    'Historial de transferencias' por el selector clicable estilo píldora de fechas."""

    def __init__(self, master, gestor, **kwargs):
        activar_selector_mundial_en_dialogo_cuenta()
        hoy = date.today()
        self._preset_periodo = "ESTE_MES"
        self._ini_periodo, self._fin_periodo, self._texto_periodo = calcular_rango_preset(
            "ESTE_MES", referencia=hoy
        )
        self._moneda_filtro = "COP"
        self._incluir_todas_convertidas = False
        self._barra_moneda = None
        self._boton_periodo: Optional[ctk.CTkButton] = None
        self._etiqueta_total_convertido = None
        super().__init__(master, gestor, **kwargs)
        self._fecha_desde = self._ini_periodo
        self._fecha_hasta = self._fin_periodo
        self._inyectar_barra_moneda_y_periodo()
        self.refrescar()

    def _rango_del_filtro(self):
        """Devuelve siempre el rango activo seleccionado en el control estilo píldora de fechas."""
        return self._ini_periodo, self._fin_periodo

    def _inyectar_barra_moneda_y_periodo(self):
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

            self._boton_periodo = _construir_controles_pildora_periodo(
                fila_filtros_historial,
                texto_periodo=self._texto_periodo,
                al_desplazar=self._desplazar_periodo,
                al_abrir=self._abrir_selector_periodo,
                alto=30,
                con_etiqueta=True,
            )

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

    def _abrir_selector_periodo(self):
        DialogoPeriodo(
            self,
            fecha_inicio=self._ini_periodo,
            fecha_fin=self._fin_periodo,
            preset_inicial=self._preset_periodo,
            al_aplicar=self._al_aplicar_periodo,
        )

    def _al_aplicar_periodo(
        self, fecha_ini: date, fecha_fin: date, preset: str, etiqueta: str
    ):
        self._ini_periodo, self._fin_periodo = fecha_ini, fecha_fin
        self._preset_periodo, self._texto_periodo = preset, etiqueta
        self._fecha_desde, self._fecha_hasta = fecha_ini, fecha_fin
        if self._boton_periodo is not None:
            self._boton_periodo.configure(text=f"📅 {self._texto_periodo} ▾")
        self._refrescar_historial()

    def _desplazar_periodo(self, direccion: int):
        ini, fin, etiqueta = desplazar_rango(
            self._preset_periodo, self._ini_periodo, self._fin_periodo, direccion
        )
        self._ini_periodo, self._fin_periodo, self._texto_periodo = ini, fin, etiqueta
        self._fecha_desde, self._fecha_hasta = ini, fin
        if self._boton_periodo is not None:
            self._boton_periodo.configure(text=f"📅 {self._texto_periodo} ▾")
        self._refrescar_historial()

    def _al_cambiar_moneda_vista(self, nueva_moneda: str, incluir_todas: bool):
        self._moneda_filtro = nueva_moneda
        self._incluir_todas_convertidas = incluir_todas
        self.refrescar()

    def _refrescar_historial(self):
        """Consulta las transferencias en el rango de período activo y aplica el filtro/conversión de moneda."""
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
            _, fecha, origen, destino, valor, moneda, comentarios, imagen = fila
            if not self._incluir_todas_convertidas and moneda != self._moneda_filtro:
                continue

            valor_texto = formatear_valor(valor, moneda)
            if self._incluir_todas_convertidas and moneda != self._moneda_filtro:
                try:
                    val_conv = self._gestor.convertir_entre_monedas(
                        valor, moneda, self._moneda_filtro
                    )
                    valor_texto = f"{formatear_valor(val_conv, self._moneda_filtro)} ({valor_texto})"
                except Exception:
                    pass

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

        cuentas_filtradas = (
            todas_cuentas
            if self._incluir_todas_convertidas
            else [(c, s) for c, s in todas_cuentas if c.moneda == self._moneda_filtro]
        )
        total = self._gestor.calcular_total_cuentas_en_moneda(
            cuentas_filtradas,
            moneda_objetivo=self._moneda_filtro,
            incluir_todas_convertidas=self._incluir_todas_convertidas,
        )
        if self._etiqueta_total_convertido is not None:
            prefijo = f"Total unificado ({self._moneda_filtro})" if self._incluir_todas_convertidas else f"Total solo {self._moneda_filtro}"
            self._etiqueta_total_convertido.configure(
                text=f"{prefijo}: {formatear_valor(total, self._moneda_filtro)}"
            )

        self._refrescar_totales(cuentas_filtradas)
        self._refrescar_cuentas(cuentas_filtradas)
        self._refrescar_historial()


class VistaMovimientosConDivisa(VistaMovimientos):
    """Subclase de VistaMovimientos (Ingresos) que añade el selector mundial de divisas y el
    selector de periodo estilo píldora de fechas (`◄ [ 📅 Noviembre de 2026 ▾ ] ►`)."""

    def __init__(self, master, gestor, filtro_tipo=None, titulo="Movimientos", **kwargs):
        hoy = date.today()
        self._preset_periodo = "ESTE_MES"
        self._ini_periodo, self._fin_periodo, self._texto_periodo = calcular_rango_preset(
            "ESTE_MES", referencia=hoy
        )
        self._moneda_filtro = "COP"
        self._incluir_todas_convertidas = False
        self._barra_moneda = None
        self._boton_periodo: Optional[ctk.CTkButton] = None
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

        marco_periodo = ctk.CTkFrame(fila, fg_color="transparent")
        marco_periodo.pack(side="right")
        self._boton_periodo = _construir_controles_pildora_periodo(
            marco_periodo,
            texto_periodo=self._texto_periodo,
            al_desplazar=self._desplazar_periodo,
            al_abrir=self._abrir_selector_periodo,
            alto=32,
            con_etiqueta=False,
        )

    def _abrir_selector_periodo(self):
        DialogoPeriodo(
            self,
            fecha_inicio=self._ini_periodo,
            fecha_fin=self._fin_periodo,
            preset_inicial=self._preset_periodo,
            al_aplicar=self._al_aplicar_periodo,
        )

    def _al_aplicar_periodo(
        self, fecha_ini: date, fecha_fin: date, preset: str, etiqueta: str
    ):
        self._ini_periodo, self._fin_periodo = fecha_ini, fecha_fin
        self._preset_periodo, self._texto_periodo = preset, etiqueta
        if self._boton_periodo is not None:
            self._boton_periodo.configure(text=f"📅 {self._texto_periodo} ▾")
        self.refrescar()

    def _desplazar_periodo(self, direccion: int):
        self._ini_periodo, self._fin_periodo, self._texto_periodo = desplazar_rango(
            self._preset_periodo, self._ini_periodo, self._fin_periodo, direccion
        )
        if self._boton_periodo is not None:
            self._boton_periodo.configure(text=f"📅 {self._texto_periodo} ▾")
        self.refrescar()

    def _al_cambiar_moneda_vista(self, nueva_moneda: str, incluir_todas: bool):
        self._moneda_filtro = nueva_moneda
        self._incluir_todas_convertidas = incluir_todas
        self.refrescar()

    def _al_guardar(self):
        try:
            self._campo_moneda.set(extraer_codigo_divisa(self._campo_moneda.get()))
        except Exception:
            pass
        resultado = super()._al_guardar()
        try:
            self._campo_moneda.configure(values=self._gestor.obtener_opciones_selector_divisas())
            self._campo_moneda.set(etiqueta_divisa(self._moneda_filtro))
        except Exception:
            pass
        return resultado

    def refrescar(self):
        try:
            todos = self._gestor.obtener_movimientos(
                self._filtro_tipo,
                fecha_inicio=self._ini_periodo,
                fecha_fin=self._fin_periodo,
            )
        except Exception:
            return super().refrescar()

        movimientos = (
            todos
            if self._incluir_todas_convertidas
            else [m for m in todos if m.moneda == self._moneda_filtro]
        )

        for elemento in self._tabla.get_children():
            self._tabla.delete(elemento)
        self._ids_tabla.clear()

        total_convertido = Decimal("0")
        for mov in movimientos:
            valor_mostrar = formatear_valor(mov.valor, mov.moneda)
            monto_sumar = mov.valor
            if self._incluir_todas_convertidas and mov.moneda != self._moneda_filtro:
                try:
                    monto_sumar = self._gestor.convertir_entre_monedas(
                        mov.valor, mov.moneda, self._moneda_filtro
                    )
                    valor_mostrar = f"{formatear_valor(monto_sumar, self._moneda_filtro)} ({valor_mostrar})"
                except Exception:
                    monto_sumar = mov.valor
            total_convertido += monto_sumar

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
            texto_tot = f"Sin movimientos en {self._moneda_filtro} ({self._texto_periodo})."
        elif self._incluir_todas_convertidas:
            texto_tot = f"Total unificado ({self._moneda_filtro} · {self._texto_periodo}): {formatear_valor(total_convertido, self._moneda_filtro)}"
        else:
            texto_tot = f"Total solo {self._moneda_filtro} ({self._texto_periodo}): {formatear_valor(total_convertido, self._moneda_filtro)}"
        self._etiqueta_totales.configure(text=texto_tot)
