"""Diálogo modal desacoplado para vender/cerrar una posición de inversión y acreditar fondos en una cuenta,
más extensiones de `DialogoAsignarInversion` (selección de cuenta origen al comprar) y `VistaInversiones`
(garantía de botón '💰 Vender' en cada fila de operación abierta).
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from tkinter import messagebox
from typing import Callable, Dict, List, Optional, Tuple
import customtkinter as ctk

from app.gui.estilos import COLORES, FUENTE
from app.gui.formato import formatear_valor
from app.modelo.inversion import ValoracionInversion

DOS_DECIMALES = Decimal("0.01")

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


def _dec_seguro(valor: object) -> Optional[Decimal]:
    """Convierte un valor a Decimal si es numérico y válido; devuelve None en caso contrario."""
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return Decimal(str(valor))
    except Exception:
        return None


def extraer_unidades_efectivas(inv, *valoraciones) -> Decimal:
    """Obtiene la cantidad efectiva de títulos/unidades de la posición desde la inversión o su valoración."""
    for fuente in (inv, *valoraciones):
        if fuente is None:
            continue
        for attr in ("cantidad_titulos", "unidades", "titulos", "cantidad"):
            d = _dec_seguro(getattr(fuente, attr, None))
            if d is not None and d > Decimal("0"):
                return d
    for fuente in (inv, *valoraciones):
        if fuente is None:
            continue
        for attr_p in ("precio_compra", "precio_compra_unitario", "precio_historico", "precio_entrada"):
            p_c = _dec_seguro(getattr(fuente, attr_p, None))
            if p_c is not None and p_c > Decimal("0") and inv.monto_invertido > Decimal("0"):
                return inv.monto_invertido / p_c
    return Decimal("0")


def extraer_valor_actual_de_valoracion(
    val_obj: object,
    inv,
    moneda_valoracion: Optional[str] = None,
) -> Optional[Decimal]:
    """Extrae el valor actual de mercado en la moneda nativa de la inversión a partir de un `ValoracionInversion`."""
    if val_obj is None:
        return None

    monto_inv = inv.monto_invertido.quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)
    mon_val = str(
        moneda_valoracion
        or getattr(val_obj, "moneda_valoracion", None)
        or getattr(val_obj, "moneda_objetivo", None)
        or inv.moneda
    ).upper()
    misma_moneda = mon_val == str(inv.moneda).upper()

    # 1. Atributos explícitos en moneda nativa de origen
    for attr_orig in ("valor_actual_origen", "valor_mercado_origen", "monto_actual_origen"):
        v_or = _dec_seguro(getattr(val_obj, attr_orig, None))
        if v_or is not None and v_or > Decimal("0"):
            v_q = v_or.quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)
            if v_q != monto_inv:
                return v_q

    # 2. Si la valoración fue calculada en la misma moneda de la inversión, usar valor_actual o ganancia
    if misma_moneda:
        for attr_val in (
            "valor_actual",
            "valor_mercado",
            "valor_actual_moneda_objetivo",
            "valor_actual_convertido",
            "valor_convertido",
            "monto_actual",
        ):
            v_act = _dec_seguro(getattr(val_obj, attr_val, None))
            if v_act is not None and v_act > Decimal("0"):
                v_q = v_act.quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)
                if v_q != monto_inv:
                    return v_q

        for attr_pnl in (
            "ganancia_perdida_origen",
            "ganancia_perdida",
            "rendimiento_monetario",
            "ganancia_neta",
            "ganancia",
            "pnl",
        ):
            g_val = _dec_seguro(getattr(val_obj, attr_pnl, None))
            if g_val is not None and g_val != Decimal("0"):
                cand = (inv.monto_invertido + g_val).quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)
                if cand > Decimal("0"):
                    return cand

    # 3. Precio unitario de mercado × unidades efectivas
    unidades = extraer_unidades_efectivas(inv, val_obj)
    if unidades > Decimal("0"):
        for attr_precio in (
            "precio_mercado_actual",
            "precio_actual",
            "precio_actual_mercado",
            "precio_mercado",
            "precio_unitario_actual",
            "precio_unitario",
            "precio_unitario_usd",
        ):
            p_val = _dec_seguro(getattr(val_obj, attr_precio, None))
            if p_val is not None and p_val > Decimal("0"):
                cand = (unidades * p_val).quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)
                if cand > Decimal("0") and cand != monto_inv:
                    return cand

    # 4. Porcentaje de retorno (independiente de la divisa de visualización)
    for attr_pct in (
        "porcentaje_retorno",
        "rendimiento_porcentual",
        "variacion_porcentual",
        "rentabilidad_pct",
        "porcentaje_ganancia",
    ):
        pct = _dec_seguro(getattr(val_obj, attr_pct, None))
        if pct is not None and pct != Decimal("0") and inv.monto_invertido > Decimal("0"):
            cand = (inv.monto_invertido * (Decimal("1") + (pct / Decimal("100")))).quantize(
                DOS_DECIMALES, rounding=ROUND_HALF_UP
            )
            if cand > Decimal("0") and cand != monto_inv:
                return cand

    # 5. Inspección dinámica de atributos de ValoracionInversion cuando está en la misma moneda
    if misma_moneda:
        for nom_attr in dir(val_obj):
            if nom_attr.startswith("_") or nom_attr == "inversion":
                continue
            low = nom_attr.lower()
            if any(p in low for p in ("pct", "porcentaje", "tasa", "compra", "invertido", "inicial", "id", "fecha")):
                continue
            try:
                val_cand = _dec_seguro(getattr(val_obj, nom_attr, None))
            except Exception:
                val_cand = None
            if val_cand is None:
                continue
            if any(k in low for k in ("valor", "mercado", "actual", "total", "posicion")) and "precio" not in low:
                if val_cand > Decimal("0"):
                    vq = val_cand.quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)
                    if vq != monto_inv:
                        return vq
            if any(k in low for k in ("ganancia", "rendimiento", "pnl", "utilidad")) and val_cand != Decimal("0"):
                cand_g = (inv.monto_invertido + val_cand).quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)
                if cand_g > Decimal("0") and cand_g != monto_inv:
                    return cand_g

    return None


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
        self.geometry("480x450")
        self.resizable(False, False)
        self.configure(fg_color=COLORES["fondo_lateral"])
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

        self._valor_mercado_nativo, self._titulos_efectivos = self._resolver_valor_mercado_y_titulos()

        self._construir_widgets(opciones_menu, opcion_predeterminada)
        self._actualizar_preview_conversion()

    def _resolver_valor_mercado_y_titulos(self) -> Tuple[Decimal, Decimal]:
        """Obtiene el valor actual de mercado en la moneda nativa de la inversión usando la valoración
        fresca del portafolio y la cotización actual del activo (nunca se queda con el precio de compra
        si existe cotización en caché o en red)."""
        val_fresca = None
        if hasattr(self._gestor, "valorar_portafolio"):
            for permitir_red in (False, True):
                try:
                    resumen = self._gestor.valorar_portafolio(
                        moneda_objetivo=self._inv.moneda,
                        incluir_todas_convertidas=True,
                        forzar_actualizacion=False,
                        permitir_red=permitir_red,
                    )
                    posiciones = resumen.get("posiciones", []) if isinstance(resumen, dict) else []
                    val_fresca = next(
                        (v for v in posiciones if getattr(v.inversion, "id", None) == self._inv.id),
                        None,
                    )
                except TypeError:
                    try:
                        resumen = self._gestor.valorar_portafolio(
                            moneda_objetivo=self._inv.moneda,
                            incluir_todas_convertidas=True,
                            forzar_actualizacion=False,
                        )
                        posiciones = resumen.get("posiciones", []) if isinstance(resumen, dict) else []
                        val_fresca = next(
                            (v for v in posiciones if getattr(v.inversion, "id", None) == self._inv.id),
                            None,
                        )
                    except Exception:
                        pass
                except Exception:
                    pass

                if val_fresca is not None:
                    val_calc = extraer_valor_actual_de_valoracion(
                        val_fresca, self._inv, moneda_valoracion=self._inv.moneda
                    )
                    if val_calc is not None:
                        titulos = extraer_unidades_efectivas(self._inv, val_fresca, self._val)
                        if titulos <= Decimal("0") and hasattr(self._gestor, "_obtener_precio_unitario_seguro"):
                            p_u = self._gestor._obtener_precio_unitario_seguro(self._inv.simbolo, self._inv.moneda, permitir_red=False)
                            if p_u is not None and p_u > Decimal("0"):
                                titulos = val_calc / p_u
                        return val_calc, titulos

        # Intentar extraer desde la valoración recibida de VistaInversiones
        val_desde_vista = extraer_valor_actual_de_valoracion(
            self._val, self._inv, moneda_valoracion=self._moneda_vista
        )
        titulos = extraer_unidades_efectivas(self._inv, val_fresca, self._val)
        if val_desde_vista is not None:
            return val_desde_vista, titulos

        # Consultar directamente el precio unitario actual del activo en el gestor
        if hasattr(self._gestor, "_obtener_precio_unitario_seguro"):
            for permitir_red in (False, True):
                try:
                    precio_unit = self._gestor._obtener_precio_unitario_seguro(
                        self._inv.simbolo, self._inv.moneda, permitir_red=permitir_red
                    )
                    if precio_unit is not None and precio_unit > Decimal("0") and titulos > Decimal("0"):
                        val_unit = (titulos * precio_unit).quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)
                        if val_unit > Decimal("0"):
                            return val_unit, titulos
                except Exception:
                    pass

        return self._inv.monto_invertido.quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP), titulos

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
        pct_pnl = (
            (pnl_nativo / self._inv.monto_invertido * Decimal("100")).quantize(Decimal("0.01"))
            if self._inv.monto_invertido > Decimal("0")
            else Decimal("0.00")
        )

        marco = ctk.CTkFrame(self, fg_color=COLORES["fondo_tarjeta"], corner_radius=12)
        marco.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            marco,
            text=f"💰 Vender posición: {self._inv.simbolo}",
            font=(FUENTE, 16, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w", padx=16, pady=(14, 4))

        titulos_mostrar = self._titulos_efectivos.quantize(Decimal("0.0001"))
        ctk.CTkLabel(
            marco,
            text=(
                f"{self._inv.nombre}  •  {titulos_mostrar} títulos\n"
                f"Invertido originalmente: {formatear_valor(self._inv.monto_invertido, self._inv.moneda)}"
            ),
            font=(FUENTE, 12),
            text_color=COLORES["texto_secundario"],
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 8))

        self._lbl_valor_mercado = ctk.CTkLabel(
            marco,
            text=(
                f"Valor actual de mercado: {formatear_valor(self._valor_mercado_nativo, self._inv.moneda)} "
                f"({signo_pnl}{formatear_valor(abs(pnl_nativo), self._inv.moneda)} · {signo_pnl}{abs(pct_pnl):.2f}%)"
            ),
            font=(FUENTE, 13, "bold"),
            text_color=color_pnl,
        )
        self._lbl_valor_mercado.pack(anchor="w", padx=16, pady=(0, 12))

        ctk.CTkLabel(
            marco,
            text=f"Valor total de venta ({self._inv.moneda}):",
            font=(FUENTE, 12, "bold"),
            text_color=COLORES["texto"],
        ).pack(anchor="w", padx=16, pady=(4, 2))

        self._campo_valor_venta = ctk.CTkEntry(
            marco,
            height=36,
            fg_color=COLORES["boton_lateral"],
            border_width=1,
            border_color=COLORES["acento"],
            text_color="#FFFFFF",
            font=(FUENTE, 13, "bold"),
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
            justify="left",
            wraplength=430,
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
                return val.quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)
        except Exception:
            pass
        return self._valor_mercado_nativo

    def _actualizar_preview_conversion(self) -> None:
        monto_origen = self._obtener_monto_ingresado()
        pnl_actual = (monto_origen - self._inv.monto_invertido).quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)
        signo_pnl = "+" if pnl_actual >= Decimal("0") else "-"
        color_pnl = COLORES["exito"] if pnl_actual >= Decimal("0") else COLORES["error"]
        pct_pnl = (
            (pnl_actual / self._inv.monto_invertido * Decimal("100")).quantize(Decimal("0.01"))
            if self._inv.monto_invertido > Decimal("0")
            else Decimal("0.00")
        )
        if hasattr(self, "_lbl_valor_mercado"):
            self._lbl_valor_mercado.configure(
                text=(
                    f"Valor de venta seleccionado: {formatear_valor(monto_origen, self._inv.moneda)} "
                    f"({signo_pnl}{formatear_valor(abs(pnl_actual), self._inv.moneda)} · {signo_pnl}{abs(pct_pnl):.2f}%)"
                ),
                text_color=color_pnl,
            )

        id_cuenta = self._mapa_opciones_cuenta.get(self._selector_cuenta.get())
        if id_cuenta is None:
            self._lbl_preview.configure(
                text=(
                    f"La posición se cerrará con resultado {signo_pnl}{formatear_valor(abs(pnl_actual), self._inv.moneda)} "
                    f"sin acreditar fondos en ninguna cuenta."
                )
            )
            return

        cuenta_dest = next((c for c, _s in self._cuentas_disponibles if c.id == id_cuenta), None)
        if cuenta_dest is None:
            return

        monto_mostrar = monto_origen
        if cuenta_dest.moneda != self._inv.moneda:
            try:
                if hasattr(self._gestor, "_convertir_monto_seguro"):
                    monto_mostrar = self._gestor._convertir_monto_seguro(
                        monto_origen, self._inv.moneda, cuenta_dest.moneda, permitir_red=False
                    )
                else:
                    monto_mostrar = self._gestor.convertir_entre_monedas(
                        monto_origen, self._inv.moneda, cuenta_dest.moneda
                    )
            except Exception:
                monto_mostrar = monto_origen

        self._lbl_preview.configure(
            text=(
                f"Se acreditarán: {formatear_valor(monto_mostrar, cuenta_dest.moneda)} en '{cuenta_dest.nombre}' "
                f"(Ganancia neta: {signo_pnl}{formatear_valor(abs(pnl_actual), self._inv.moneda)})"
            )
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


def activar_selector_cuenta_en_dialogo_compra(cls_dialogo_asignar) -> None:
    """Inyecta en `DialogoAsignarInversion` el desplegable para elegir de qué cuenta se descuenta
    el dinero al comprar un activo en Inversiones."""
    if getattr(cls_dialogo_asignar, "_parche_cuenta_origen_aplicado", False):
        return
    cls_dialogo_asignar._parche_cuenta_origen_aplicado = True

    init_orig = cls_dialogo_asignar.__init__

    def _init_con_cuenta(self, master, gestor, *args, **kwargs):
        self._mapa_cuentas_origen: Dict[str, Optional[int]] = {}
        self._selector_cuenta_origen: Optional[ctk.CTkOptionMenu] = None
        init_orig(self, master, gestor, *args, **kwargs)
        try:
            self.geometry("540x695")
            marco_destino = (
                self._campo_notas.master
                if hasattr(self, "_campo_notas")
                else self
            )
            cuentas = list(getattr(self._gestor, "obtener_cuentas", lambda: [])())
            opciones: List[str] = []
            predeterminada: Optional[str] = None
            for c_obj, s_act in cuentas:
                etiq = f"{c_obj.nombre} ({c_obj.moneda}) — Disponible: {formatear_valor(s_act, c_obj.moneda)}"
                self._mapa_cuentas_origen[etiq] = c_obj.id
                opciones.append(etiq)
                if predeterminada is None and s_act > Decimal("0"):
                    predeterminada = etiq

            etiq_ninguna = "No descontar de ninguna cuenta (registro manual)"
            self._mapa_cuentas_origen[etiq_ninguna] = None
            opciones.append(etiq_ninguna)
            if predeterminada is None:
                predeterminada = opciones[0]

            lbl_c = ctk.CTkLabel(
                marco_destino,
                text="¿De qué cuenta deseas descontar este dinero?",
                font=(FUENTE, 12, "bold"),
                text_color=COLORES["texto"],
            )
            self._selector_cuenta_origen = ctk.CTkOptionMenu(
                marco_destino,
                values=opciones,
                height=32,
                fg_color=COLORES["boton_lateral"],
                button_color=COLORES["acento"],
                button_hover_color=COLORES["acento_hover"],
                text_color=COLORES["texto"],
                font=(FUENTE, 11),
            )
            self._selector_cuenta_origen.set(predeterminada)

            if hasattr(self, "_campo_notas"):
                lbl_c.pack(anchor="w", padx=16, pady=(6, 2), before=self._campo_notas)
                self._selector_cuenta_origen.pack(
                    fill="x", padx=16, pady=(0, 8), before=self._campo_notas
                )
            else:
                lbl_c.pack(anchor="w", padx=16, pady=(6, 2))
                self._selector_cuenta_origen.pack(fill="x", padx=16, pady=(0, 8))
        except Exception:
            pass

    def _guardar_con_cuenta(self):
        monto_limpio = self._campo_monto.obtener_valor().strip()
        precio_txt = self._campo_precio_compra.get().strip() or None
        notas = self._campo_notas.get().strip() or None
        id_cuenta_origen = None
        if getattr(self, "_selector_cuenta_origen", None) is not None:
            id_cuenta_origen = self._mapa_cuentas_origen.get(
                self._selector_cuenta_origen.get()
            )
        try:
            inv = self._gestor.registrar_inversion(
                simbolo=self._simbolo,
                nombre=self._nombre,
                monto_texto=monto_limpio,
                moneda=self._moneda_elegida,
                precio_compra_texto=precio_txt,
                fecha_texto=self._fecha_compra.isoformat(),
                notas=notas,
                cuenta_origen_id=id_cuenta_origen,
            )
        except Exception as error:
            messagebox.showwarning("No se pudo registrar la inversión", str(error), parent=self)
            return

        cb = self._al_guardar
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
        if cb is not None:
            cb(inv)

    cls_dialogo_asignar.__init__ = _init_con_cuenta
    cls_dialogo_asignar._guardar_inversion = _guardar_con_cuenta


def activar_boton_vender_en_vista_inversiones(cls_vista_inversiones) -> None:
    """Garantiza en tiempo de ejecución que cada fila de operación abierta en `VistaInversiones`
    tenga el botón '💰 Vender' y que al abrir el diálogo siempre use la valoración en vivo más reciente."""
    if getattr(cls_vista_inversiones, "_parche_boton_vender_aplicado", False):
        return
    cls_vista_inversiones._parche_boton_vender_aplicado = True

    render_orig = cls_vista_inversiones._renderizar_lista_posiciones
    actualizar_in_place_orig = getattr(cls_vista_inversiones, "_actualizar_textos_posiciones_in_place", None)
    abrir_orig = getattr(cls_vista_inversiones, "_abrir_dialogo_cerrar_inversion", None)

    def _guardar_valoraciones_vivas(self, lista_posiciones: List[ValoracionInversion]) -> None:
        mapa = getattr(self, "_ultimas_valoraciones_por_id", None)
        if mapa is None:
            mapa = {}
            self._ultimas_valoraciones_por_id = mapa
        for v in lista_posiciones:
            if getattr(v, "inversion", None) is not None and v.inversion.id is not None:
                mapa[v.inversion.id] = v

    def _renderizar_con_boton_vender(self, posiciones: List[ValoracionInversion], moneda_vista: str):
        _guardar_valoraciones_vivas(self, posiciones)
        res = render_orig(self, posiciones, moneda_vista)
        try:
            filas_dict = getattr(self, "_widgets_filas_operacion", {})
            for val in posiciones:
                inv = val.inversion
                if inv.id is None or inv.id not in filas_dict:
                    continue
                info_fila = filas_dict[inv.id]
                fila_op = info_fila.get("fila_op")
                if fila_op is None or not fila_op.winfo_exists():
                    continue
                ya_tiene_vender = any(
                    isinstance(h, ctk.CTkButton) and "Vender" in str(h.cget("text"))
                    for h in fila_op.winfo_children()
                )
                if not ya_tiene_vender:
                    sim_grupo = str(info_fila.get("simbolo") or inv.simbolo)
                    ctk.CTkButton(
                        fila_op,
                        text="💰 Vender",
                        width=76,
                        height=24,
                        corner_radius=6,
                        fg_color=COLORES["acento"],
                        hover_color=COLORES["acento_hover"],
                        text_color="#10241C",
                        font=(FUENTE, 11, "bold"),
                        command=lambda v_op=val, sim_k=sim_grupo: self._abrir_dialogo_cerrar_inversion(v_op, sim_k),
                    ).pack(side="right", padx=(4, 4), pady=4)
        except Exception:
            pass
        return res

    if callable(actualizar_in_place_orig):
        def _actualizar_in_place_con_cache(self, grupos_por_simbolo, moneda):
            try:
                for vals in (grupos_por_simbolo or {}).values():
                    _guardar_valoraciones_vivas(self, list(vals))
            except Exception:
                pass
            return actualizar_in_place_orig(self, grupos_por_simbolo, moneda)

        cls_vista_inversiones._actualizar_textos_posiciones_in_place = _actualizar_in_place_con_cache

    if callable(abrir_orig):
        def _abrir_con_valoracion_fresca(self, val_op: ValoracionInversion, simbolo_grupo: Optional[str] = None):
            try:
                mapa = getattr(self, "_ultimas_valoraciones_por_id", {}) or {}
                inv_id = getattr(getattr(val_op, "inversion", None), "id", None)
                if inv_id is not None and inv_id in mapa:
                    val_op = mapa[inv_id]
            except Exception:
                pass
            return abrir_orig(self, val_op, simbolo_grupo)

        cls_vista_inversiones._abrir_dialogo_cerrar_inversion = _abrir_con_valoracion_fresca

    cls_vista_inversiones._renderizar_lista_posiciones = _renderizar_con_boton_vender
