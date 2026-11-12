"""Diálogo modal desacoplado para vender/cerrar una posición de inversión y acreditar fondos en una cuenta.

Extraído de `vista_inversiones.py` para mantener cada componente de interfaz enfocado en una
única responsabilidad (SRP) y reducir el tamaño de `vista_inversiones.py`.
"""

from __future__ import annotations

from decimal import Decimal
from tkinter import messagebox
from typing import Callable, Dict, List, Optional
import customtkinter as ctk

from app.gui.estilos import COLORES, FUENTE
from app.gui.formato import formatear_valor
from app.modelo.inversion import ValoracionInversion

MAPA_BROKERS_POR_NOTA = (
    ("binance", "Binance"),
    ("interactive brokers", "Interactive Brokers"),
    ("ibkr", "Interactive Brokers"),
    ("trii", "Trii"),
    ("hapi", "Hapi"),
    ("etoro", "eToro"),
)


def detectar_broker_desde_notas(notas: Optional[str]) -> str:
    """Identifica el nombre estándar del broker a partir de las notas de la posición."""
    texto = (notas or "").lower()
    return next((nombre for clave, nombre in MAPA_BROKERS_POR_NOTA if clave in texto), "eToro")


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

        broker_sugerido = detectar_broker_desde_notas(self._inv.notas)
        try:
            self._gestor.asegurar_cuenta_broker(broker_sugerido, moneda=self._inv.moneda)
        except Exception:
            pass

        self._cuentas_disponibles = list(getattr(self._gestor, "obtener_cuentas", lambda: [])())
        self._mapa_opciones_cuenta: Dict[str, Optional[int]] = {}
        opciones_menu, opcion_predeterminada = self._construir_opciones_cuentas(broker_sugerido)

        precio_vivo = getattr(valoracion, "precio_mercado_actual", None)
        self._valor_mercado_nativo = (
            (self._inv.cantidad_titulos * precio_vivo).quantize(Decimal("0.01"))
            if (precio_vivo is not None and precio_vivo > Decimal("0") and self._inv.cantidad_titulos > Decimal("0"))
            else self._inv.monto_invertido.quantize(Decimal("0.01"))
        )

        self._construir_widgets(opciones_menu, opcion_predeterminada)
        self._actualizar_preview_conversion()

    def _construir_opciones_cuentas(self, broker_sugerido: str):
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
        return opciones_menu, (opcion_predeterminada or opciones_menu[0])

    def _construir_widgets(self, opciones_menu: List[str], opcion_predeterminada: str) -> None:
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
        id_cuenta = self._mapa_opciones_cuenta.get(self._selector_cuenta.get())
        if id_cuenta is None:
            self._lbl_preview.configure(
                text="La posición se cerrará sin acreditar fondos en ninguna cuenta."
            )
            return

        cuenta_dest = next((c for c, _s in self._cuentas_disponibles if c.id == id_cuenta), None)
        if cuenta_dest is None:
            return

        monto_mostrar = monto_origen
        if cuenta_dest.moneda != self._inv.moneda:
            try:
                monto_mostrar = self._gestor.convertir_entre_monedas(
                    monto_origen, self._inv.moneda, cuenta_dest.moneda
                )
            except Exception:
                monto_mostrar = monto_origen

        self._lbl_preview.configure(
            text=f"Se acreditarán: {formatear_valor(monto_mostrar, cuenta_dest.moneda)} en '{cuenta_dest.nombre}'"
        )

    def _confirmar(self) -> None:
        if self._inv.id is None:
            self.destroy()
            return
        monto_origen = self._obtener_monto_ingresado()
        id_cuenta = self._mapa_opciones_cuenta.get(self._selector_cuenta.get())
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
