"""Envuelve VistaCuentas, VistaMovimientos y DialogoCuenta para inyectar:
1) El filtro mundial de divisas (COP + 4 últimas usadas + lista A-Z) y el modo
   'Solo esta moneda' vs 'Todo convertido' (activo por defecto en Mis cuentas para
   mostrar cuentas en USD como eToro junto con cuentas en COP).
2) El selector de periodo estilo píldora de fechas (`◄ [ 📅 Noviembre de 2026 ▾ ] ►`)
   dentro de 'Historial de transferencias' en Cuentas y en Ingresos.
3) Lista consolidada de 'Mis cuentas' y 'Historial de transferencias' optimizada para
   carga instantánea (sin doble refresco en __init__, con caché de íconos PIL,
   diferenciación de firmas de renderizado, widgets planos sin contenedores anidados
   innecesarios y conversión de divisas en memoria sin bloqueos de red)."""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import importlib
import io
from pathlib import Path
import sys
import threading
from tkinter import messagebox, ttk
from typing import Callable, Dict, List, Optional, Tuple
import customtkinter as ctk
from PIL import Image

if not hasattr(messagebox, "showinformation"):
    messagebox.showinformation = messagebox.showinfo  # type: ignore[attr-defined]

from app.gui.dialogo_cuenta import DialogoCuenta
from app.gui.dialogo_periodo import (
    DialogoPeriodo,
    calcular_rango_preset,
    desplazar_rango,
)
from app.gui.estilos import COLORES, FUENTE
from app.gui.formato import formatear_valor
from app.gui.iconos import icono_ctk
from app.gui.selector_moneda import BarraFiltroMoneda, DialogoSelectorDivisa
from app.gui.vista_cuentas import VistaCuentas
from app.gui.vista_movimientos import ETIQUETAS_TIPO, VistaMovimientos
from app.modelo.cuenta import Cuenta
from app.modelo.divisas import etiqueta_divisa, extraer_codigo_divisa

_parche_dialogos_aplicado = False
_CACHE_ICONOS: Dict[Tuple[str, str, int], object] = {}

# Definición de columnas con ancho fijo idéntico entre cabecera y filas para alineación perfecta
COLUMNAS_MIS_CUENTAS = (
    # (col_idx, titulo, ancho_fijo, peso_grid, ancla, padx)
    (0, "Cuenta", 175, 2, "w", (12, 6)),
    (1, "Saldo actual", 150, 2, "w", (6, 6)),
    (2, "Divisa", 70, 1, "center", (6, 6)),
    (3, "En balance total", 115, 1, "center", (6, 6)),
    (4, "Nota", 220, 3, "w", (6, 6)),
    (5, "Acción", 92, 1, "e", (6, 12)),
)

COLUMNAS_TRANSFERENCIAS = (
    # (col_idx, titulo, ancho_fijo, peso_grid, ancla, padx)
    (0, "Fecha", 105, 1, "w", (12, 6)),
    (1, "Cuenta origen", 145, 2, "w", (6, 6)),
    (2, "Cuenta destino", 145, 2, "w", (6, 6)),
    (3, "Valor", 155, 2, "w", (6, 6)),
    (4, "Divisa", 70, 1, "center", (6, 6)),
    (5, "Comentarios", 210, 3, "w", (6, 12)),
)


def _obtener_icono_seguro(simbolo: Optional[str], color: Optional[str], tamano: int = 22):
    """Obtiene y memoriza en caché el CTkImage del ícono de la cuenta con fallback seguro a 'banco'."""
    color_usar = color or "#2ECC71"
    clave = (str(simbolo or "banco"), color_usar, tamano)
    if clave in _CACHE_ICONOS:
        return _CACHE_ICONOS[clave]

    for cand in (simbolo, "banco", "billetera", "efectivo"):
        if not cand:
            continue
        try:
            img = icono_ctk(cand, color_usar, tamano)
            if img is not None:
                _CACHE_ICONOS[clave] = img
                return img
        except Exception:
            pass
    return None


def _configurar_columnas_grid(contenedor, definicion_columnas: tuple) -> None:
    """Aplica exactamente los mismos pesos y minsize de columna en cabeceras y filas."""
    for col_idx, _titulo, ancho_fijo, peso_grid, _ancla, _padx in definicion_columnas:
        contenedor.grid_columnconfigure(col_idx, weight=peso_grid, minsize=ancho_fijo)


def _construir_cabecera_columnas(tarjeta_padre, definicion_columnas: tuple) -> ctk.CTkFrame:
    """Crea la barra de encabezados de columna estilizada con anchos idénticos a las filas."""
    cabecera = ctk.CTkFrame(
        tarjeta_padre,
        fg_color=COLORES["fondo_lateral"],
        corner_radius=8,
        height=32,
    )
    cabecera.pack(fill="x", padx=12, pady=(4, 2))
    _configurar_columnas_grid(cabecera, definicion_columnas)

    for col_idx, titulo, ancho_fijo, _peso, ancla, pad_x in definicion_columnas:
        ctk.CTkLabel(
            cabecera,
            text=titulo,
            width=ancho_fijo,
            font=(FUENTE, 11, "bold"),
            text_color=COLORES["texto_secundario"],
            anchor=ancla,
        ).grid(row=0, column=col_idx, sticky="ew", padx=pad_x, pady=6)

    return cabecera


def _ocultar_treeview_y_scrollbars(contenedor) -> None:
    """Oculta cualquier ttk.Treeview y sus barras de desplazamiento asociadas dentro de un contenedor."""
    for hijo in list(contenedor.winfo_children()):
        if isinstance(hijo, (ttk.Treeview, ttk.Scrollbar, ctk.CTkScrollbar)):
            try:
                hijo.pack_forget()
            except Exception:
                pass
            try:
                hijo.grid_forget()
            except Exception:
                pass


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
    """Extiende DialogoCuenta con:
    1) Selector mundial de divisas (COP + últimas usadas + botón 🌍 Todas A-Z).
    2) Saldo inicial vacío por defecto en '0'.
    3) Soporte de edición (`cuenta_editar` y `saldo_actual`) conservando exactamente la misma
       interfaz de 'Crear nueva cuenta' pero precargada con los datos actuales de la cuenta."""
    global _parche_dialogos_aplicado
    if _parche_dialogos_aplicado:
        return
    _parche_dialogos_aplicado = True

    init_original = DialogoCuenta.__init__
    al_aniadir_original = DialogoCuenta._al_aniadir

    def _nuevo_init(
        self,
        master,
        gestor,
        al_crear,
        cuenta_editar=None,
        saldo_actual: Optional[Decimal] = None,
        **kwargs,
    ):
        self._cuenta_editar = cuenta_editar
        self._saldo_actual_editar = saldo_actual
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

        if cuenta_editar is not None:
            self._precargar_datos_edicion(cuenta_editar, saldo_actual)

    def _precargar_datos_edicion(self, cuenta, saldo_actual: Optional[Decimal] = None) -> None:
        """Rellena todos los controles de DialogoCuenta con los valores actuales de la cuenta a editar."""
        self.title(f"Editar cuenta — {cuenta.nombre}")

        def _actualizar_etiquetas_recursivo(widget):
            for hijo in widget.winfo_children():
                if isinstance(hijo, ctk.CTkLabel):
                    try:
                        if hijo.cget("text") in ("Crear nueva cuenta", "Nueva Cuenta"):
                            hijo.configure(text=f"Editar cuenta: {cuenta.nombre}")
                    except Exception:
                        pass
                elif isinstance(hijo, ctk.CTkButton):
                    try:
                        if hijo.cget("text") in ("Añadir", "Crear", "Guardar"):
                            hijo.configure(text="Guardar cambios")
                    except Exception:
                        pass
                _actualizar_etiquetas_recursivo(hijo)

        _actualizar_etiquetas_recursivo(self)

        try:
            self._campo_nombre.delete(0, "end")
            self._campo_nombre.insert(0, cuenta.nombre)
        except Exception:
            pass

        try:
            monto_mostrar = saldo_actual if saldo_actual is not None else cuenta.saldo_inicial
            monto_dec = Decimal(str(monto_mostrar))
            texto_monto = (
                str(int(monto_dec))
                if monto_dec == int(monto_dec)
                else f"{monto_dec:.2f}"
            )
            self._campo_saldo.delete(0, "end")
            self._campo_saldo.insert(0, texto_monto)
        except Exception:
            pass

        try:
            self._campo_moneda.set(etiqueta_divisa(cuenta.moneda))
        except Exception:
            pass

        try:
            if hasattr(self, "_elegir_simbolo") and cuenta.simbolo:
                self._elegir_simbolo(cuenta.simbolo)
        except Exception:
            pass

        try:
            if hasattr(self, "_elegir_color") and cuenta.color:
                self._elegir_color(cuenta.color)
        except Exception:
            pass

        try:
            if hasattr(self, "_variable_total"):
                self._variable_total.set(bool(cuenta.incluye_en_total))
        except Exception:
            pass

        try:
            if hasattr(self, "_campo_nota"):
                self._campo_nota.delete(0, "end")
                if cuenta.nota:
                    self._campo_nota.insert(0, cuenta.nota)
        except Exception:
            pass

    def _nuevo_al_aniadir(self):
        try:
            self._campo_moneda.set(extraer_codigo_divisa(self._campo_moneda.get()))
        except Exception:
            pass
        try:
            val_actual = (
                self._campo_saldo.obtener_valor()
                if hasattr(self._campo_saldo, "obtener_valor")
                else self._campo_saldo.get()
            )
            if not (val_actual or "").strip():
                self._campo_saldo.delete(0, "end")
                self._campo_saldo.insert(0, "0")
        except Exception:
            pass

        cuenta_ed = getattr(self, "_cuenta_editar", None)
        if cuenta_ed is not None and cuenta_ed.id is not None:
            try:
                saldo_txt = (
                    self._campo_saldo.obtener_valor()
                    if hasattr(self._campo_saldo, "obtener_valor")
                    else self._campo_saldo.get()
                )
                actualizada = self._gestor.actualizar_cuenta(
                    id_cuenta=cuenta_ed.id,
                    nombre=self._campo_nombre.get(),
                    moneda=extraer_codigo_divisa(self._campo_moneda.get()),
                    saldo_inicial_texto=saldo_txt or "0",
                    simbolo=self._simbolo_elegido or cuenta_ed.simbolo,
                    color=self._color_elegido or cuenta_ed.color,
                    incluye_en_total=bool(self._variable_total.get()),
                    nota=self._campo_nota.get(),
                )
            except Exception as error:
                if hasattr(self, "_etiqueta_estado"):
                    self._etiqueta_estado.configure(
                        text=str(error), text_color=COLORES["error"]
                    )
                return

            cb = getattr(self, "_al_crear", None) or getattr(self, "al_crear", None)
            if cb is not None:
                cb(actualizada)
            self.destroy()
            return

        return al_aniadir_original(self)

    DialogoCuenta.__init__ = _nuevo_init
    DialogoCuenta._precargar_datos_edicion = _precargar_datos_edicion
    DialogoCuenta._al_aniadir = _nuevo_al_aniadir


def _recorrer_estructura_inicial(vista_cuentas: VistaCuentas):
    """En una sola pasada sobre el árbol de widgets:
    1) Localiza la fila de radios del historial (`Día`, `Semana`, `Mes`, `Año`, `Periodo`).
    2) Oculta el botón redundante 'Ver imagen adjunta'."""
    fila_radios = None

    def _visitar(widget):
        nonlocal fila_radios
        try:
            hijos = list(widget.winfo_children())
        except Exception:
            return
        if fila_radios is None and any(isinstance(h, ctk.CTkRadioButton) for h in hijos):
            fila_radios = widget
        for h in hijos:
            if isinstance(h, ctk.CTkButton):
                try:
                    txt = str(h.cget("text") or "").lower()
                    if "imagen" in txt or "comprobante" in txt or "adjunt" in txt:
                        h.pack_forget()
                        h.grid_forget()
                        continue
                except Exception:
                    pass
            _visitar(h)

    _visitar(vista_cuentas)
    return fila_radios


class VistaCuentasConDivisa(VistaCuentas):
    """Subclase optimizada de VistaCuentas que:
    1) Evita el doble/triple `refrescar()` durante `__init__` y suprime el llenado de los
       `ttk.Treeview` ocultos en cada refresco.
    2) Calcula los totales y conversiones en O(1) sin bloquear el hilo de interfaz con
       peticiones HTTP a Yahoo Finance (`permitir_red=False` + precarga en hilo de fondo).
    3) Usa widgets planos (1 `CTkFrame` por fila en lugar de 5 contenedores anidados) y
       caché de firmas de datos para que abrir y cambiar a la pestaña Cuentas tome < 15 ms."""

    def __init__(self, master, gestor, **kwargs):
        activar_selector_mundial_en_dialogo_cuenta()
        hoy = date.today()
        self._preset_periodo = "ESTE_MES"
        self._ini_periodo, self._fin_periodo, self._texto_periodo = calcular_rango_preset(
            "ESTE_MES", referencia=hoy
        )
        self._moneda_filtro = "COP"
        self._incluir_todas_convertidas = True
        self._barra_moneda = None
        self._boton_periodo: Optional[ctk.CTkButton] = None
        self._etiqueta_total_convertido = None
        self._contenedor_filas_edicion: Optional[ctk.CTkScrollableFrame] = None
        self._contenedor_filas_transferencias: Optional[ctk.CTkScrollableFrame] = None
        self._id_cuenta_seleccionada: Optional[int] = None
        self._id_transferencia_seleccionada: Optional[int] = None
        self._marcos_fila_por_id: dict = {}
        self._marcos_transferencia_por_id: dict = {}
        self._firma_cuentas_render: Optional[tuple] = None
        self._firma_transferencias_render: Optional[tuple] = None
        self._cargando_tasas_bg = False

        # Suprimir el refrescar() prematuro que ejecuta super().__init__() antes de construir las listas nuevas
        self._inicializando_vista = True
        super().__init__(master, gestor, **kwargs)
        self._fecha_desde = self._ini_periodo
        self._fecha_hasta = self._fin_periodo
        self._inyectar_barra_moneda_y_periodo()
        self._reemplazar_tabla_por_lista_consolidada()
        self._reemplazar_tabla_transferencias_por_lista_consolidada()
        self._inicializando_vista = False
        self.refrescar()

    def _rango_del_filtro(self):
        """Devuelve siempre el rango activo seleccionado en el control estilo píldora de fechas."""
        return self._ini_periodo, self._fin_periodo

    def _convertir_rapido_sin_red(
        self, monto: Decimal, moneda_origen: str, moneda_destino: str
    ) -> Decimal:
        """Convierte en memoria (0 ms) sin realizar llamadas HTTP en el hilo de UI."""
        if moneda_origen == moneda_destino or monto == Decimal("0"):
            return Decimal(str(monto)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if hasattr(self._gestor, "_convertir_monto_seguro"):
            try:
                return self._gestor._convertir_monto_seguro(
                    monto, moneda_origen, moneda_destino, permitir_red=False
                )
            except Exception:
                pass
        return Decimal(str(monto)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _precalentar_tasas_faltantes_fondo(self, divisas_origen: set) -> None:
        """Si alguna cuenta o transferencia está en una divisa cuya tasa aún no está en caché,
        la consulta en un hilo secundario y actualiza los textos al terminar sin congelar la UI."""
        if self._cargando_tasas_bg:
            return
        mon_dest = self._moneda_filtro.strip().upper()
        cache_tasas = getattr(self._gestor, "_cache_tasas_rapido", {}) or {}
        faltantes = {
            d.strip().upper()
            for d in divisas_origen
            if d and d.strip().upper() != mon_dest and (d.strip().upper(), mon_dest) not in cache_tasas
        }
        if not faltantes:
            return

        self._cargando_tasas_bg = True

        def _tarea():
            actualizado = False
            try:
                for div_o in faltantes:
                    if hasattr(self._gestor, "_obtener_tasa_cambio_segura"):
                        t = self._gestor._obtener_tasa_cambio_segura(div_o, mon_dest, permitir_red=True)
                        if t > Decimal("0") and t != Decimal("1"):
                            actualizado = True
                    elif hasattr(self._gestor, "obtener_tasa_cambio"):
                        self._gestor.obtener_tasa_cambio(div_o, mon_dest, forzar_actualizacion=False)
                        actualizado = True
            except Exception:
                pass
            finally:
                self._cargando_tasas_bg = False

            if actualizado:
                try:
                    self.after(0, self._forzar_recalculo_visual)
                except Exception:
                    pass

        threading.Thread(target=_tarea, daemon=True).start()

    def _forzar_recalculo_visual(self) -> None:
        self._firma_cuentas_render = None
        self._firma_transferencias_render = None
        self.refrescar()

    def _encontrar_tarjeta_seccion(self, widget_interno) -> ctk.CTkFrame:
        """Sube desde un widget interno (ej. `_tabla_transferencias`) hasta la tarjeta CTkFrame
        principal de esa sección dentro de VistaCuentas."""
        actual = widget_interno.master
        ultimo_ctk = actual if isinstance(actual, ctk.CTkFrame) else self
        while actual is not None and actual is not self:
            if isinstance(actual, ctk.CTkFrame):
                ultimo_ctk = actual
            if getattr(actual, "master", None) is self:
                break
            actual = getattr(actual, "master", None)
        return ultimo_ctk

    @staticmethod
    def _contiene_widget_objetivo(raiz, objetivo) -> bool:
        if objetivo is None:
            return False
        if raiz is objetivo:
            return True
        try:
            for h in raiz.winfo_children():
                if VistaCuentasConDivisa._contiene_widget_objetivo(h, objetivo):
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def _limpiar_marcos_vacios_o_antiguos(tarjeta, conservar_widgets: tuple) -> None:
        """Oculta cualquier sub-marco antiguo (como el contenedor de Treeview, `_marco_periodo`
        o la barra del botón eliminado) que de otro modo dejaría un hueco vacío en CustomTkinter."""
        for hijo in list(tarjeta.winfo_children()):
            if isinstance(hijo, ctk.CTkLabel):
                continue
            if any(VistaCuentasConDivisa._contiene_widget_objetivo(hijo, w) for w in conservar_widgets if w is not None):
                continue
            # Si es un contenedor que solo tenía la tabla antigua, el selector de fechas viejo o botones ocultos, desempacarlo
            tiene_boton_visible = False
            try:
                for sub in hijo.winfo_children():
                    if isinstance(sub, (ctk.CTkButton, ctk.CTkLabel)) and sub.winfo_manager():
                        tiene_boton_visible = True
                        break
            except Exception:
                pass
            if not tiene_boton_visible:
                try:
                    hijo.pack_forget()
                except Exception:
                    pass
                try:
                    hijo.grid_forget()
                except Exception:
                    pass

    def _reemplazar_tabla_por_lista_consolidada(self) -> None:
        """Oculta `_tabla_cuentas` y su contenedor antiguo sin dejar espacios en blanco."""
        if not hasattr(self, "_tabla_cuentas"):
            return
        try:
            contenedor_tabla = self._tabla_cuentas.master
            tarjeta_cuentas = self._encontrar_tarjeta_seccion(self._tabla_cuentas)
            _ocultar_treeview_y_scrollbars(contenedor_tabla)
            if contenedor_tabla is not tarjeta_cuentas:
                try:
                    contenedor_tabla.pack_forget()
                    contenedor_tabla.grid_forget()
                except Exception:
                    pass

            _construir_cabecera_columnas(tarjeta_cuentas, COLUMNAS_MIS_CUENTAS)

            self._contenedor_filas_edicion = ctk.CTkScrollableFrame(
                tarjeta_cuentas,
                fg_color=COLORES["boton_lateral"],
                corner_radius=10,
                height=195,
            )
            self._contenedor_filas_edicion.pack(
                fill="both", expand=True, padx=12, pady=(2, 10)
            )
        except Exception:
            pass

    def _reemplazar_tabla_transferencias_por_lista_consolidada(self) -> None:
        """Oculta `_tabla_transferencias` y cualquier marco intermedio vacío para que la lista de
        transferencias quede inmediatamente debajo del título y selector de período."""
        if not hasattr(self, "_tabla_transferencias"):
            return
        try:
            contenedor_tr = self._tabla_transferencias.master
            tarjeta_tr = self._encontrar_tarjeta_seccion(self._tabla_transferencias)
            _ocultar_treeview_y_scrollbars(contenedor_tr)
            if contenedor_tr is not tarjeta_tr:
                try:
                    contenedor_tr.pack_forget()
                    contenedor_tr.grid_forget()
                except Exception:
                    pass

            self._limpiar_marcos_vacios_o_antiguos(tarjeta_tr, (self._boton_periodo,))

            # Si el marco que contiene el botón de período tiene padding inferior excesivo, ajustarlo
            if self._boton_periodo is not None:
                marco_per = self._boton_periodo.master
                try:
                    marco_per.pack_configure(pady=(2, 2))
                except Exception:
                    pass

            _construir_cabecera_columnas(tarjeta_tr, COLUMNAS_TRANSFERENCIAS)

            self._contenedor_filas_transferencias = ctk.CTkScrollableFrame(
                tarjeta_tr,
                fg_color=COLORES["boton_lateral"],
                corner_radius=10,
                height=195,
            )
            self._contenedor_filas_transferencias.pack(
                fill="both", expand=True, padx=12, pady=(2, 10)
            )
        except Exception:
            pass

    def _seleccionar_cuenta_en_lista(self, cuenta: Cuenta) -> None:
        """Sincroniza perezosamente la cuenta seleccionada con `_tabla_cuentas` solo al hacer clic."""
        self._id_cuenta_seleccionada = cuenta.id
        for cid, marco_f in self._marcos_fila_por_id.items():
            if not marco_f.winfo_exists():
                continue
            marco_f.configure(
                border_width=1 if cid == cuenta.id else 0,
                border_color=COLORES["acento"],
            )

        if hasattr(self, "_tabla_cuentas") and hasattr(self, "_ids_fila_cuenta"):
            try:
                for elem in self._tabla_cuentas.get_children():
                    self._tabla_cuentas.delete(elem)
                self._ids_fila_cuenta.clear()
                item_id = self._tabla_cuentas.insert("", "end", values=(cuenta.nombre,))
                self._ids_fila_cuenta[item_id] = cuenta
                self._tabla_cuentas.selection_set(item_id)
                self._tabla_cuentas.focus(item_id)
            except Exception:
                pass

    def _seleccionar_transferencia_en_lista(
        self, id_tr: object, fila_datos: tuple, abrir_imagen: bool = True
    ) -> None:
        """Selecciona la transferencia y, si tiene una imagen subida, la muestra automáticamente."""
        self._id_transferencia_seleccionada = id_tr  # type: ignore[assignment]
        for tid, marco_tr in self._marcos_transferencia_por_id.items():
            if not marco_tr.winfo_exists():
                continue
            marco_tr.configure(
                border_width=1 if tid == id_tr else 0,
                border_color=COLORES["acento"],
            )

        if hasattr(self, "_tabla_transferencias") and hasattr(self, "_ids_fila_transferencia"):
            try:
                for elem in self._tabla_transferencias.get_children():
                    self._tabla_transferencias.delete(elem)
                self._ids_fila_transferencia.clear()
                item_id = self._tabla_transferencias.insert("", "end", values=(id_tr,))
                self._ids_fila_transferencia[item_id] = fila_datos
                self._tabla_transferencias.selection_set(item_id)
                self._tabla_transferencias.focus(item_id)
            except Exception:
                pass

        if abrir_imagen and len(fila_datos) >= 8 and fila_datos[7]:
            self._mostrar_imagen_de_transferencia(fila_datos)

    def _mostrar_imagen_de_transferencia(self, fila_datos: tuple) -> None:
        """Abre el comprobante/imagen asociado a la transferencia seleccionada."""
        id_tr, fecha, origen, destino, valor, moneda, comentarios, dato_imagen = fila_datos
        if not dato_imagen:
            return

        img_pil = None
        try:
            if isinstance(dato_imagen, (bytes, bytearray, memoryview)):
                img_pil = Image.open(io.BytesIO(bytes(dato_imagen)))
            elif isinstance(dato_imagen, (str, Path)):
                ruta_p = Path(str(dato_imagen))
                if ruta_p.exists():
                    img_pil = Image.open(ruta_p)
        except Exception:
            img_pil = None

        if img_pil is not None:
            try:
                visor = ctk.CTkToplevel(self)
                fecha_txt = fecha.isoformat() if hasattr(fecha, "isoformat") else str(fecha)
                visor.title(f"Comprobante de transferencia — {origen} → {destino} ({fecha_txt})")
                visor.geometry("620x580")
                visor.configure(fg_color=COLORES["fondo_lateral"])
                visor.transient(self.winfo_toplevel())
                visor.grab_set()

                marco = ctk.CTkFrame(visor, fg_color=COLORES["fondo_tarjeta"], corner_radius=12)
                marco.pack(fill="both", expand=True, padx=16, pady=16)

                ctk.CTkLabel(
                    marco,
                    text=f"📎 {origen}  →  {destino}  •  {formatear_valor(valor, moneda)}",
                    font=(FUENTE, 15, "bold"),
                    text_color=COLORES["texto"],
                ).pack(anchor="w", padx=16, pady=(14, 4))

                if comentarios:
                    ctk.CTkLabel(
                        marco,
                        text=str(comentarios),
                        font=(FUENTE, 11),
                        text_color=COLORES["texto_secundario"],
                    ).pack(anchor="w", padx=16, pady=(0, 8))

                copia_img = img_pil.copy()
                copia_img.thumbnail((560, 420))
                ctk_img = ctk.CTkImage(
                    light_image=copia_img,
                    dark_image=copia_img,
                    size=copia_img.size,
                )
                lbl_img = ctk.CTkLabel(marco, text="", image=ctk_img)
                lbl_img._img_ref = ctk_img  # type: ignore[attr-defined]
                lbl_img.pack(expand=True, padx=16, pady=8)

                ctk.CTkButton(
                    marco,
                    text="Cerrar",
                    width=110,
                    height=32,
                    corner_radius=8,
                    fg_color=COLORES["acento"],
                    hover_color=COLORES["acento_hover"],
                    text_color="#10241C",
                    font=(FUENTE, 12, "bold"),
                    command=visor.destroy,
                ).pack(pady=(4, 14))
                return
            except Exception:
                pass

        if hasattr(super(), "_ver_imagen"):
            try:
                super()._ver_imagen()  # type: ignore[misc]
            except Exception:
                pass

    def _abrir_dialogo_editar_cuenta(self, cuenta, saldo: Decimal) -> None:
        DialogoCuenta(
            self,
            self._gestor,
            self._al_crear_cuenta,
            cuenta_editar=cuenta,
            saldo_actual=saldo,
        )

    def _renderizar_filas_cuentas_con_editar(
        self, cuentas_con_saldo: List[Tuple[Cuenta, Decimal]]
    ) -> None:
        """Renderiza las tarjetas de 'Mis cuentas' usando solo 1 CTkFrame por fila y omitiendo
        la reconstrucción si los datos no cambiaron."""
        if self._contenedor_filas_edicion is None:
            return

        firma_actual = (
            self._moneda_filtro,
            self._incluir_todas_convertidas,
            tuple(
                (
                    c.id,
                    c.nombre,
                    c.moneda,
                    str(s),
                    c.simbolo,
                    c.color,
                    bool(c.incluye_en_total),
                    c.nota or "",
                )
                for c, s in cuentas_con_saldo
            ),
        )
        if self._firma_cuentas_render == firma_actual:
            return
        self._firma_cuentas_render = firma_actual

        for hijo in list(self._contenedor_filas_edicion.winfo_children()):
            hijo.destroy()
        self._marcos_fila_por_id.clear()

        if not cuentas_con_saldo:
            ctk.CTkLabel(
                self._contenedor_filas_edicion,
                text="No hay cuentas registradas para mostrar.",
                font=(FUENTE, 12),
                text_color=COLORES["texto_secundario"],
            ).pack(pady=20)
            return

        for cuenta, saldo in cuentas_con_saldo:
            es_seleccionada = (
                self._id_cuenta_seleccionada is not None
                and cuenta.id == self._id_cuenta_seleccionada
            )
            fila = ctk.CTkFrame(
                self._contenedor_filas_edicion,
                fg_color=COLORES["fondo_tarjeta"],
                corner_radius=8,
                border_width=1 if es_seleccionada else 0,
                border_color=COLORES["acento"],
            )
            fila.pack(fill="x", padx=4, pady=3)
            _configurar_columnas_grid(fila, COLUMNAS_MIS_CUENTAS)

            if cuenta.id is not None:
                self._marcos_fila_por_id[cuenta.id] = fila

            # 1. Columna: Cuenta (1 solo CTkLabel con compound='left' e ícono en caché, ancho fijo 175px)
            img_ic = _obtener_icono_seguro(cuenta.simbolo, cuenta.color, 20)
            lbl_nombre = ctk.CTkLabel(
                fila,
                text=f"  {cuenta.nombre}" if img_ic is not None else f"🏦  {cuenta.nombre}",
                image=img_ic,
                compound="left",
                width=175,
                font=(FUENTE, 12, "bold"),
                text_color=COLORES["texto"],
                anchor="w",
            )
            lbl_nombre.grid(row=0, column=0, sticky="ew", padx=(12, 6), pady=6)

            # 2. Columna: Saldo actual (conversión O(1) en memoria sin red, ancho fijo 150px)
            texto_saldo = formatear_valor(saldo, cuenta.moneda)
            if self._incluir_todas_convertidas and cuenta.moneda != self._moneda_filtro:
                saldo_conv = self._convertir_rapido_sin_red(
                    saldo, cuenta.moneda, self._moneda_filtro
                )
                texto_saldo = f"{texto_saldo}\n≈ {formatear_valor(saldo_conv, self._moneda_filtro)}"

            lbl_saldo = ctk.CTkLabel(
                fila,
                text=texto_saldo,
                width=150,
                font=(FUENTE, 12, "bold"),
                text_color=COLORES["acento"],
                anchor="w",
                justify="left",
            )
            lbl_saldo.grid(row=0, column=1, sticky="ew", padx=6, pady=6)

            # 3. Columna: Divisa (Badge directo sin CTkFrame intermedio, ancho fijo 70px)
            insignia_divisa = ctk.CTkLabel(
                fila,
                text=cuenta.moneda,
                width=70,
                height=24,
                corner_radius=6,
                fg_color=COLORES["boton_lateral"],
                text_color=COLORES["texto"],
                font=(FUENTE, 11, "bold"),
            )
            insignia_divisa.grid(row=0, column=2, padx=6, pady=6)

            # 4. Columna: En balance total (Badge directo sin CTkFrame intermedio, ancho fijo 115px)
            en_total = bool(cuenta.incluye_en_total)
            insignia_total = ctk.CTkLabel(
                fila,
                text="✔ Sí" if en_total else "✖ No",
                width=115,
                height=24,
                corner_radius=6,
                fg_color=COLORES["boton_lateral"],
                text_color=COLORES["exito"] if en_total else COLORES["texto_secundario"],
                font=(FUENTE, 11, "bold"),
            )
            insignia_total.grid(row=0, column=3, padx=6, pady=6)

            # 5. Columna: Nota (ancho fijo 220px)
            texto_nota = (cuenta.nota or "").strip() or "—"
            lbl_nota = ctk.CTkLabel(
                fila,
                text=texto_nota,
                width=220,
                font=(FUENTE, 11),
                text_color=COLORES["texto"] if cuenta.nota else COLORES["texto_secundario"],
                anchor="w",
                justify="left",
                wraplength=210,
            )
            lbl_nota.grid(row=0, column=4, sticky="ew", padx=6, pady=6)

            # 6. Columna: Acción (Botón directo sin CTkFrame intermedio, ancho 88px)
            btn_editar = ctk.CTkButton(
                fila,
                text="✏️ Editar",
                width=88,
                height=26,
                corner_radius=8,
                fg_color=COLORES["acento"],
                hover_color=COLORES["acento_hover"],
                text_color="#10241C",
                font=(FUENTE, 11, "bold"),
                command=lambda c_obj=cuenta, s_val=saldo: self._abrir_dialogo_editar_cuenta(c_obj, s_val),
            )
            btn_editar.grid(row=0, column=5, sticky="e", padx=(6, 12), pady=6)

            for w_bind in (fila, lbl_nombre, lbl_saldo, insignia_divisa, insignia_total, lbl_nota):
                w_bind.bind("<Button-1>", lambda _e, c=cuenta: self._seleccionar_cuenta_en_lista(c))
                w_bind.bind(
                    "<Double-1>",
                    lambda _e, c=cuenta, s=saldo: self._abrir_dialogo_editar_cuenta(c, s),
                )

    def _renderizar_filas_transferencias(self, filas_transferencias: list) -> None:
        """Renderiza las tarjetas de 'Historial de transferencias' usando solo 1 CTkFrame por fila
        y omitiendo la reconstrucción si no hubo cambios."""
        if self._contenedor_filas_transferencias is None:
            return

        firma_tr = (
            self._moneda_filtro,
            self._incluir_todas_convertidas,
            self._texto_periodo,
            tuple(
                (f[0], str(f[1]), f[2], f[3], str(f[4]), f[5], f[6] or "", bool(f[7]), v_txt)
                for f, v_txt in filas_transferencias
            ),
        )
        if self._firma_transferencias_render == firma_tr:
            return
        self._firma_transferencias_render = firma_tr

        for hijo in list(self._contenedor_filas_transferencias.winfo_children()):
            hijo.destroy()
        self._marcos_transferencia_por_id.clear()

        if not filas_transferencias:
            ctk.CTkLabel(
                self._contenedor_filas_transferencias,
                text=f"No hay transferencias registradas en {self._texto_periodo}.",
                font=(FUENTE, 12),
                text_color=COLORES["texto_secundario"],
            ).pack(pady=20)
            return

        for fila_datos, valor_texto in filas_transferencias:
            id_tr, fecha, origen, destino, _valor, moneda, comentarios, imagen = fila_datos
            fecha_txt = fecha.isoformat() if hasattr(fecha, "isoformat") else str(fecha)
            es_sel = (
                self._id_transferencia_seleccionada is not None
                and id_tr == self._id_transferencia_seleccionada
            )

            fila = ctk.CTkFrame(
                self._contenedor_filas_transferencias,
                fg_color=COLORES["fondo_tarjeta"],
                corner_radius=8,
                border_width=1 if es_sel else 0,
                border_color=COLORES["acento"],
            )
            fila.pack(fill="x", padx=4, pady=3)
            _configurar_columnas_grid(fila, COLUMNAS_TRANSFERENCIAS)

            if id_tr is not None:
                self._marcos_transferencia_por_id[id_tr] = fila

            lbl_fecha = ctk.CTkLabel(
                fila,
                text=f"📅 {fecha_txt}",
                width=105,
                font=(FUENTE, 11, "bold"),
                text_color=COLORES["texto_secundario"],
                anchor="w",
            )
            lbl_fecha.grid(row=0, column=0, sticky="ew", padx=(12, 6), pady=7)

            lbl_origen = ctk.CTkLabel(
                fila,
                text=f"↗ {origen}",
                width=145,
                font=(FUENTE, 12, "bold"),
                text_color=COLORES["texto"],
                anchor="w",
            )
            lbl_origen.grid(row=0, column=1, sticky="ew", padx=6, pady=7)

            lbl_destino = ctk.CTkLabel(
                fila,
                text=f"↘ {destino}",
                width=145,
                font=(FUENTE, 12, "bold"),
                text_color=COLORES["exito"],
                anchor="w",
            )
            lbl_destino.grid(row=0, column=2, sticky="ew", padx=6, pady=7)

            lbl_valor = ctk.CTkLabel(
                fila,
                text=valor_texto,
                width=155,
                font=(FUENTE, 12, "bold"),
                text_color=COLORES["acento"],
                anchor="w",
                justify="left",
            )
            lbl_valor.grid(row=0, column=3, sticky="ew", padx=6, pady=7)

            insignia_div = ctk.CTkLabel(
                fila,
                text=str(moneda),
                width=70,
                height=24,
                corner_radius=6,
                fg_color=COLORES["boton_lateral"],
                text_color=COLORES["texto"],
                font=(FUENTE, 11, "bold"),
            )
            insignia_div.grid(row=0, column=4, padx=6, pady=7)

            texto_com = (("📎 " if imagen else "") + (comentarios or "")).strip() or "—"
            lbl_com = ctk.CTkLabel(
                fila,
                text=texto_com,
                width=210,
                font=(FUENTE, 11),
                text_color=COLORES["texto"] if (comentarios or imagen) else COLORES["texto_secundario"],
                anchor="w",
                justify="left",
                wraplength=200,
            )
            lbl_com.grid(row=0, column=5, sticky="ew", padx=(6, 12), pady=7)

            for w_tr in (fila, lbl_fecha, lbl_origen, lbl_destino, lbl_valor, insignia_div, lbl_com):
                w_tr.bind(
                    "<Button-1>",
                    lambda _e, tid=id_tr, fd=fila_datos: self._seleccionar_transferencia_en_lista(tid, fd),
                )

    def _inyectar_barra_moneda_y_periodo(self):
        if hasattr(self, "_marco_periodo") and self._marco_periodo is not None:
            try:
                self._marco_periodo.pack_forget()
            except Exception:
                pass

        fila_filtros_historial = _recorrer_estructura_inicial(self)
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

        for attr_var in ("_var_todas", "_var_incluir_todas", "_var_modo", "var_modo"):
            var_obj = getattr(self._barra_moneda, attr_var, None)
            if var_obj is not None and hasattr(var_obj, "set"):
                try:
                    var_obj.set(True)
                except Exception:
                    pass

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
        if getattr(self, "_inicializando_vista", False):
            self._moneda_filtro = nueva_moneda
            self._incluir_todas_convertidas = incluir_todas
            return
        self._moneda_filtro = nueva_moneda
        self._incluir_todas_convertidas = incluir_todas
        self.refrescar()

    def _refrescar_historial(self):
        """Consulta las transferencias en el rango de período activo y renderiza las tarjetas en O(1)."""
        if getattr(self, "_inicializando_vista", False):
            return
        inicio, fin = self._rango_del_filtro()
        try:
            transferencias = self._gestor.obtener_transferencias(inicio, fin)
        except Exception:
            return

        divisas_vistas = set()
        filas_para_tarjetas = []
        for fila in transferencias:
            _, _fecha, _origen, _destino, valor, moneda, _comentarios, _imagen = fila
            if not self._incluir_todas_convertidas and moneda != self._moneda_filtro:
                continue

            divisas_vistas.add(moneda)
            valor_texto = formatear_valor(valor, moneda)
            if self._incluir_todas_convertidas and moneda != self._moneda_filtro:
                val_conv = self._convertir_rapido_sin_red(valor, moneda, self._moneda_filtro)
                valor_texto = f"{formatear_valor(val_conv, self._moneda_filtro)} ({valor_texto})"

            filas_para_tarjetas.append((fila, valor_texto))

        self._renderizar_filas_transferencias(filas_para_tarjetas)
        if divisas_vistas:
            self._precalentar_tasas_faltantes_fondo(divisas_vistas)

    def refrescar(self):
        if getattr(self, "_inicializando_vista", False):
            return
        try:
            todas_cuentas = list(self._gestor.obtener_cuentas())
        except Exception:
            return

        nombres_brokers = {"etoro", "binance", "interactive brokers", "ibkr", "trii", "hapi"}
        cuentas_mostrar = (
            todas_cuentas
            if self._incluir_todas_convertidas
            else [
                (c, s)
                for c, s in todas_cuentas
                if c.moneda == self._moneda_filtro
                or c.nombre.strip().lower() in nombres_brokers
                or "broker" in (c.nota or "").lower()
            ]
        )

        # Cálculo instantáneo en memoria sin llamar a calcular_total_cuentas_en_moneda (evita bloqueo HTTP)
        total = Decimal("0.00")
        divisas_presentes = set()
        for c_obj, s_val in cuentas_mostrar:
            divisas_presentes.add(c_obj.moneda)
            if not c_obj.incluye_en_total:
                continue
            if c_obj.moneda == self._moneda_filtro:
                total += Decimal(str(s_val))
            else:
                total += self._convertir_rapido_sin_red(s_val, c_obj.moneda, self._moneda_filtro)

        if self._etiqueta_total_convertido is not None:
            prefijo = (
                f"Total unificado ({self._moneda_filtro})"
                if self._incluir_todas_convertidas
                else f"Total ({self._moneda_filtro})"
            )
            self._etiqueta_total_convertido.configure(
                text=f"{prefijo}: {formatear_valor(total, self._moneda_filtro)}"
            )

        self._refrescar_totales(cuentas_mostrar)
        self._renderizar_filas_cuentas_con_editar(cuentas_mostrar)
        self._refrescar_historial()
        if divisas_presentes:
            self._precalentar_tasas_faltantes_fondo(divisas_presentes)


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
                    if hasattr(self._gestor, "_convertir_monto_seguro"):
                        monto_sumar = self._gestor._convertir_monto_seguro(
                            mov.valor, mov.moneda, self._moneda_filtro, permitir_red=False
                        )
                    else:
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