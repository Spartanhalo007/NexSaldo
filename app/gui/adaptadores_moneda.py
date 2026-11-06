"""Envuelve VistaCuentas, VistaMovimientos y DialogoCuenta para inyectar el filtro mundial
de divisas (COP + 4 últimas usadas + lista A-Z) y el modo 'Solo esta moneda' vs 'Todo convertido'
sin reescribir ni reemplazar el código original de esos módulos."""

from decimal import Decimal
import customtkinter as ctk

from app.gui.dialogo_cuenta import DialogoCuenta
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


class VistaCuentasConDivisa(VistaCuentas):
    """Subclase ligera de VistaCuentas que añade la BarraFiltroMoneda (COP + 4 últimas + A-Z)
    y permite ver solo las cuentas/transferencias de una moneda o todo convertido en tiempo real."""

    def __init__(self, master, gestor, **kwargs):
        activar_selector_mundial_en_dialogo_cuenta()
        self._moneda_filtro = "COP"
        self._incluir_todas_convertidas = False
        self._barra_moneda = None
        self._etiqueta_total_convertido = None
        super().__init__(master, gestor, **kwargs)
        self._inyectar_barra_moneda()
        self.refrescar()

    def _inyectar_barra_moneda(self):
        marco_filtro = ctk.CTkFrame(
            self, fg_color=COLORES["fondo_tarjeta"], corner_radius=12
        )
        # Empaquetar arriba de las tarjetas existentes
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
            font=(FUENTE, 13, "bold"),
            text_color=COLORES["acento"],
        )
        self._etiqueta_total_convertido.pack(side="right", padx=6)

    def _al_cambiar_moneda_vista(self, nueva_moneda: str, incluir_todas: bool):
        self._moneda_filtro = nueva_moneda
        self._incluir_todas_convertidas = incluir_todas
        self.refrescar()

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
    """Subclase ligera de VistaMovimientos (Ingresos) que añade el selector mundial de divisas
    tanto al formulario como a la barra superior ('Solo esta moneda' vs 'Todo convertido')."""

    def __init__(self, master, gestor, filtro_tipo=None, titulo="Movimientos", **kwargs):
        self._moneda_filtro = "COP"
        self._incluir_todas_convertidas = False
        self._barra_moneda = None
        super().__init__(
            master, gestor, filtro_tipo=filtro_tipo, titulo=titulo, **kwargs
        )
        self._configurar_selector_mundial()
        self.refrescar()

    def _configurar_selector_mundial(self):
        # 1. Actualizar el combo de moneda del formulario para incluir todas las divisas del mundo
        try:
            opciones = self._gestor.obtener_opciones_selector_divisas()
            self._campo_moneda.configure(values=opciones)
            self._campo_moneda.set(etiqueta_divisa("COP"))
        except Exception:
            pass

        # 2. Añadir BarraFiltroMoneda en la parte superior de la vista
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
            todos = self._gestor.obtener_movimientos(self._filtro_tipo)
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
                text=f"Sin movimientos en {self._moneda_filtro}."
            )
        elif self._incluir_todas_convertidas:
            self._etiqueta_totales.configure(
                text=f"Total unificado ({self._moneda_filtro}): {formatear_valor(total_convertido, self._moneda_filtro)}"
            )
        else:
            self._etiqueta_totales.configure(
                text=f"Total solo {self._moneda_filtro}: {formatear_valor(total_convertido, self._moneda_filtro)}"
            )
