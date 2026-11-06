"""Selector de periodo tipo Shopify para NexSaldo.

Al hacer clic en la etiqueta de fecha de Resumen Financiero (ej. 'Noviembre de 2026'),
se abre esta ventana con:
- Columna izquierda: Presets rápidos (Hoy / Día, Ayer, Esta semana, Últimos 7 días,
  Este mes, Mes pasado, Últimos 30 días, Este trimestre (Quarter), Trimestre pasado,
  Este año, Año hasta la fecha (Year to date), Rango personalizado).
- Columna derecha: Calendario interactivo de selección de rango (inicio y fin) o fecha única,
  más navegación rápida de mes/año y botones 'Cancelar' / 'Aplicar'.
"""

import calendar
from datetime import date, timedelta
from typing import Callable, Dict, Optional, Tuple
import customtkinter as ctk

from app.gui.estilos import COLORES, FUENTE
from app.gui.formato import NOMBRES_DIAS, NOMBRES_MESES, nombre_mes

PRESETS_SHOPIFY = [
    ("HOY", "Hoy (Día)"),
    ("AYER", "Ayer"),
    ("ESTA_SEMANA", "Esta semana"),
    ("ULTIMOS_7", "Últimos 7 días"),
    ("ESTE_MES", "Este mes"),
    ("MES_PASADO", "Mes pasado"),
    ("ULTIMOS_30", "Últimos 30 días"),
    ("ESTE_TRIMESTRE", "Este trimestre (Quarter)"),
    ("TRIMESTRE_PASADO", "Trimestre pasado"),
    ("ESTE_ANNO", "Este año"),
    ("YTD", "Año hasta la fecha (YTD)"),
    ("PERSONALIZADO", "Periodo personalizado"),
]


def calcular_rango_preset(clave_preset: str, referencia: Optional[date] = None) -> Tuple[date, date, str]:
    """Devuelve (fecha_inicio, fecha_fin, etiqueta_legible) para cada preset tipo Shopify."""
    hoy = referencia or date.today()

    if clave_preset == "HOY":
        return hoy, hoy, f"Hoy ({hoy.strftime('%d/%m/%Y')})"

    if clave_preset == "AYER":
        ayer = hoy - timedelta(days=1)
        return ayer, ayer, f"Ayer ({ayer.strftime('%d/%m/%Y')})"

    if clave_preset == "ESTA_SEMANA":
        inicio = hoy - timedelta(days=hoy.weekday())
        fin = inicio + timedelta(days=6)
        return inicio, fin, f"Esta semana ({inicio.strftime('%d/%m')} – {fin.strftime('%d/%m/%Y')})"

    if clave_preset == "ULTIMOS_7":
        inicio = hoy - timedelta(days=6)
        return inicio, hoy, f"Últimos 7 días ({inicio.strftime('%d/%m')} – {hoy.strftime('%d/%m/%Y')})"

    if clave_preset == "ESTE_MES":
        inicio = date(hoy.year, hoy.month, 1)
        ultimo_dia = calendar.monthrange(hoy.year, hoy.month)[1]
        fin = date(hoy.year, hoy.month, ultimo_dia)
        return inicio, fin, nombre_mes(hoy.year, hoy.month).capitalize()

    if clave_preset == "MES_PASADO":
        if hoy.month == 1:
            anno_ant, mes_ant = hoy.year - 1, 12
        else:
            anno_ant, mes_ant = hoy.year, hoy.month - 1
        inicio = date(anno_ant, mes_ant, 1)
        ultimo_dia = calendar.monthrange(anno_ant, mes_ant)[1]
        fin = date(anno_ant, mes_ant, ultimo_dia)
        return inicio, fin, nombre_mes(anno_ant, mes_ant).capitalize()

    if clave_preset == "ULTIMOS_30":
        inicio = hoy - timedelta(days=29)
        return inicio, hoy, f"Últimos 30 días ({inicio.strftime('%d/%m')} – {hoy.strftime('%d/%m/%Y')})"

    if clave_preset == "ESTE_TRIMESTRE":
        trimestre = (hoy.month - 1) // 3 + 1
        mes_ini = (trimestre - 1) * 3 + 1
        mes_fin = mes_ini + 2
        inicio = date(hoy.year, mes_ini, 1)
        ultimo_dia = calendar.monthrange(hoy.year, mes_fin)[1]
        fin = date(hoy.year, mes_fin, ultimo_dia)
        return inicio, fin, f"T{trimestre} {hoy.year} ({NOMBRES_MESES[mes_ini-1][:3].capitalize()} – {NOMBRES_MESES[mes_fin-1][:3].capitalize()})"

    if clave_preset == "TRIMESTRE_PASADO":
        trimestre_actual = (hoy.month - 1) // 3 + 1
        if trimestre_actual == 1:
            trimestre_ant = 4
            anno_t = hoy.year - 1
        else:
            trimestre_ant = trimestre_actual - 1
            anno_t = hoy.year
        mes_ini = (trimestre_ant - 1) * 3 + 1
        mes_fin = mes_ini + 2
        inicio = date(anno_t, mes_ini, 1)
        ultimo_dia = calendar.monthrange(anno_t, mes_fin)[1]
        fin = date(anno_t, mes_fin, ultimo_dia)
        return inicio, fin, f"T{trimestre_ant} {anno_t} ({NOMBRES_MESES[mes_ini-1][:3].capitalize()} – {NOMBRES_MESES[mes_fin-1][:3].capitalize()})"

    if clave_preset == "ESTE_ANNO":
        inicio = date(hoy.year, 1, 1)
        fin = date(hoy.year, 12, 31)
        return inicio, fin, f"Año {hoy.year}"

    if clave_preset == "YTD":
        inicio = date(hoy.year, 1, 1)
        return inicio, hoy, f"YTD {hoy.year} (01/01 – {hoy.strftime('%d/%m/%Y')})"

    # Por defecto: Este mes
    inicio = date(hoy.year, hoy.month, 1)
    ultimo_dia = calendar.monthrange(hoy.year, hoy.month)[1]
    fin = date(hoy.year, hoy.month, ultimo_dia)
    return inicio, fin, nombre_mes(hoy.year, hoy.month).capitalize()


def desplazar_rango(
    clave_preset: str, fecha_inicio: date, fecha_fin: date, direccion: int
) -> Tuple[date, date, str]:
    """Desplaza el periodo hacia atrás (-1) o adelante (+1) con las flechas ◀ / ▶."""
    paso = -1 if direccion < 0 else 1

    if clave_preset == "ESTE_MES" or (
        fecha_inicio.day == 1
        and fecha_inicio.year == fecha_fin.year
        and fecha_inicio.month == fecha_fin.month
        and fecha_fin.day == calendar.monthrange(fecha_fin.year, fecha_fin.month)[1]
    ):
        nuevo_mes = fecha_inicio.month + paso
        nuevo_anno = fecha_inicio.year
        if nuevo_mes < 1:
            nuevo_mes = 12
            nuevo_anno -= 1
        elif nuevo_mes > 12:
            nuevo_mes = 1
            nuevo_anno += 1
        ini = date(nuevo_anno, nuevo_mes, 1)
        fin = date(nuevo_anno, nuevo_mes, calendar.monthrange(nuevo_anno, nuevo_mes)[1])
        return ini, fin, nombre_mes(nuevo_anno, nuevo_mes).capitalize()

    if clave_preset == "ESTE_ANNO" or (
        fecha_inicio == date(fecha_inicio.year, 1, 1)
        and fecha_fin == date(fecha_inicio.year, 12, 31)
    ):
        nuevo_anno = fecha_inicio.year + paso
        return date(nuevo_anno, 1, 1), date(nuevo_anno, 12, 31), f"Año {nuevo_anno}"

    if clave_preset in ("ESTE_TRIMESTRE", "TRIMESTRE_PASADO"):
        mes_central = fecha_inicio.month + (paso * 3)
        anno_t = fecha_inicio.year
        while mes_central < 1:
            mes_central += 12
            anno_t -= 1
        while mes_central > 12:
            mes_central -= 12
            anno_t += 1
        trimestre = (mes_central - 1) // 3 + 1
        mes_ini = (trimestre - 1) * 3 + 1
        mes_fin = mes_ini + 2
        ini = date(anno_t, mes_ini, 1)
        fin = date(anno_t, mes_fin, calendar.monthrange(anno_t, mes_fin)[1])
        etiqueta = f"T{trimestre} {anno_t} ({NOMBRES_MESES[mes_ini-1][:3].capitalize()} – {NOMBRES_MESES[mes_fin-1][:3].capitalize()})"
        return ini, fin, etiqueta

    dias = (fecha_fin - fecha_inicio).days + 1
    delta = timedelta(days=dias * paso)
    nuevo_ini = fecha_inicio + delta
    nuevo_fin = fecha_fin + delta
    if nuevo_ini == nuevo_fin:
        return nuevo_ini, nuevo_fin, f"Día {nuevo_ini.isoformat()}"
    return (
        nuevo_ini,
        nuevo_fin,
        f"{nuevo_ini.strftime('%d/%m/%Y')} – {nuevo_fin.strftime('%d/%m/%Y')}",
    )


class DialogoPeriodoShopify(ctk.CTkToplevel):
    """Pop-up estilo Shopify: barra lateral izquierda con rangos rápidos (Día, Semana,
    Mes, Trimestre/Quarter, Año, YTD, Personalizado) y calendario interactivo a la derecha."""

    def __init__(
        self,
        master,
        fecha_inicio: date,
        fecha_fin: date,
        preset_inicial: str,
        al_aplicar: Callable[[date, date, str, str], None],
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self._fecha_inicio = fecha_inicio
        self._fecha_fin = fecha_fin
        self._preset_actual = preset_inicial or "ESTE_MES"
        self._al_aplicar = al_aplicar

        # Control del mes que se visualiza actualmente en el calendario derecho
        self._anno_cal = fecha_fin.year
        self._mes_cal = fecha_fin.month
        # Cuando el usuario hace clic en el calendario: primer clic = inicio, segundo clic = fin
        self._esperando_segundo_clic = False
        self._botones_presets: Dict[str, ctk.CTkButton] = {}

        self.title("Seleccionar periodo")
        self.geometry("670x490")
        self.resizable(False, False)
        self.configure(fg_color=COLORES["fondo_lateral"])
        self.transient(master)
        self.grab_set()

        self._construir_interfaz()
        self._actualizar_estado_visual()

    def _construir_interfaz(self):
        contenedor = ctk.CTkFrame(self, fg_color="transparent")
        contenedor.pack(fill="both", expand=True, padx=16, pady=14)
        contenedor.grid_columnconfigure(0, weight=0)
        contenedor.grid_columnconfigure(1, weight=1)
        contenedor.grid_rowconfigure(0, weight=1)

        # ==================================================================
        # COLUMNA IZQUIERDA: Presets estilo Shopify
        # ==================================================================
        panel_presets = ctk.CTkScrollableFrame(
            contenedor,
            width=215,
            fg_color=COLORES["fondo_tarjeta"],
            corner_radius=12,
        )
        panel_presets.grid(row=0, column=0, sticky="ns", padx=(0, 12))

        ctk.CTkLabel(
            panel_presets,
            text="Rangos rápidos",
            font=(FUENTE, 13, "bold"),
            text_color=COLORES["acento"],
        ).pack(anchor="w", padx=10, pady=(6, 6))

        for clave, texto in PRESETS_SHOPIFY:
            btn = ctk.CTkButton(
                panel_presets,
                text=texto,
                anchor="w",
                height=30,
                corner_radius=8,
                fg_color=COLORES["boton_lateral"],
                hover_color=COLORES["hover_lateral"],
                text_color=COLORES["texto"],
                font=(FUENTE, 12),
                command=lambda k=clave: self._seleccionar_preset(k),
            )
            btn.pack(fill="x", padx=6, pady=2)
            self._botones_presets[clave] = btn

        # ==================================================================
        # COLUMNA DERECHA: Rango desde/hasta + Calendario interactivo
        # ==================================================================
        panel_derecho = ctk.CTkFrame(
            contenedor, fg_color=COLORES["fondo_tarjeta"], corner_radius=12
        )
        panel_derecho.grid(row=0, column=1, sticky="nsew")

        # Franja superior con los cuadros de Fecha Inicial y Fecha Final
        fila_rango = ctk.CTkFrame(panel_derecho, fg_color="transparent")
        fila_rango.pack(fill="x", padx=16, pady=(14, 8))

        col_desde = ctk.CTkFrame(fila_rango, fg_color="transparent")
        col_desde.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkLabel(
            col_desde,
            text="Desde (Inicio)",
            font=(FUENTE, 11, "bold"),
            text_color=COLORES["texto_secundario"],
        ).pack(anchor="w")
        self._lbl_desde = ctk.CTkLabel(
            col_desde,
            text="",
            height=32,
            corner_radius=8,
            fg_color=COLORES["boton_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 13, "bold"),
        )
        self._lbl_desde.pack(fill="x", pady=(2, 0))

        col_hasta = ctk.CTkFrame(fila_rango, fg_color="transparent")
        col_hasta.pack(side="left", fill="x", expand=True, padx=(6, 0))
        ctk.CTkLabel(
            col_hasta,
            text="Hasta (Fin)",
            font=(FUENTE, 11, "bold"),
            text_color=COLORES["texto_secundario"],
        ).pack(anchor="w")
        self._lbl_hasta = ctk.CTkLabel(
            col_hasta,
            text="",
            height=32,
            corner_radius=8,
            fg_color=COLORES["boton_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 13, "bold"),
        )
        self._lbl_hasta.pack(fill="x", pady=(2, 0))

        # Navegación del mes del calendario (◀ Mes Año ▶)
        fila_nav_cal = ctk.CTkFrame(panel_derecho, fg_color="transparent")
        fila_nav_cal.pack(fill="x", padx=16, pady=(6, 6))

        ctk.CTkButton(
            fila_nav_cal,
            text="◀",
            width=34,
            height=28,
            corner_radius=8,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 12, "bold"),
            command=lambda: self._cambiar_mes_calendario(-1),
        ).pack(side="left")

        self._lbl_titulo_cal = ctk.CTkLabel(
            fila_nav_cal,
            text="",
            font=(FUENTE, 14, "bold"),
            text_color=COLORES["texto"],
        )
        self._lbl_titulo_cal.pack(side="left", expand=True)

        ctk.CTkButton(
            fila_nav_cal,
            text="▶",
            width=34,
            height=28,
            corner_radius=8,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 12, "bold"),
            command=lambda: self._cambiar_mes_calendario(1),
        ).pack(side="right")

        # Cuadrícula de días del calendario
        self._rejilla_dias = ctk.CTkFrame(
            panel_derecho, fg_color=COLORES["fondo_lateral"], corner_radius=10
        )
        self._rejilla_dias.pack(fill="both", expand=True, padx=16, pady=(2, 8))

        self._lbl_ayuda = ctk.CTkLabel(
            panel_derecho,
            text="Haz clic en un día para elegir inicio y en otro día para elegir fin.",
            font=(FUENTE, 11),
            text_color=COLORES["texto_secundario"],
        )
        self._lbl_ayuda.pack(pady=(0, 6))

        # Botones inferiores Cancelar / Aplicar
        fila_acciones = ctk.CTkFrame(self, fg_color="transparent")
        fila_acciones.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkButton(
            fila_acciones,
            text="Cancelar",
            width=110,
            height=36,
            corner_radius=8,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 13),
            command=self.destroy,
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            fila_acciones,
            text="Aplicar periodo",
            width=155,
            height=36,
            corner_radius=8,
            fg_color=COLORES["acento"],
            hover_color=COLORES["acento_hover"],
            text_color=COLORES["campo_texto"],
            font=(FUENTE, 13, "bold"),
            command=self._confirmar,
        ).pack(side="right")

    def _seleccionar_preset(self, clave: str):
        self._preset_actual = clave
        self._esperando_segundo_clic = False
        if clave != "PERSONALIZADO":
            ini, fin, _ = calcular_rango_preset(clave)
            self._fecha_inicio = ini
            self._fecha_fin = fin
            self._anno_cal = fin.year
            self._mes_cal = fin.month
        self._actualizar_estado_visual()

    def _cambiar_mes_calendario(self, delta: int):
        nuevo_mes = self._mes_cal + delta
        nuevo_anno = self._anno_cal
        if nuevo_mes < 1:
            nuevo_mes = 12
            nuevo_anno -= 1
        elif nuevo_mes > 12:
            nuevo_mes = 1
            nuevo_anno += 1
        self._mes_cal = nuevo_mes
        self._anno_cal = nuevo_anno
        self._renderizar_calendario()

    def _al_clic_dia(self, dia_elegido: date):
        self._preset_actual = "PERSONALIZADO"
        if not self._esperando_segundo_clic:
            self._fecha_inicio = dia_elegido
            self._fecha_fin = dia_elegido
            self._esperando_segundo_clic = True
            self._lbl_ayuda.configure(
                text=f"Inicio: {dia_elegido.isoformat()} — Ahora selecciona la fecha final (o aplica para un solo día).",
                text_color=COLORES["acento"],
            )
        else:
            if dia_elegido < self._fecha_inicio:
                self._fecha_fin = self._fecha_inicio
                self._fecha_inicio = dia_elegido
            else:
                self._fecha_fin = dia_elegido
            self._esperando_segundo_clic = False
            self._lbl_ayuda.configure(
                text=f"Rango seleccionado: {self._fecha_inicio.isoformat()} a {self._fecha_fin.isoformat()}",
                text_color=COLORES["exito"],
            )
        self._actualizar_estado_visual()

    def _actualizar_estado_visual(self):
        for clave, btn in self._botones_presets.items():
            activo = clave == self._preset_actual
            btn.configure(
                fg_color=COLORES["acento"] if activo else COLORES["boton_lateral"],
                hover_color=COLORES["acento_hover"] if activo else COLORES["hover_lateral"],
                text_color=COLORES["campo_texto"] if activo else COLORES["texto"],
                font=(FUENTE, 12, "bold" if activo else "normal"),
            )

        self._lbl_desde.configure(text=self._fecha_inicio.isoformat())
        self._lbl_hasta.configure(text=self._fecha_fin.isoformat())
        self._renderizar_calendario()

    def _renderizar_calendario(self):
        for hijo in self._rejilla_dias.winfo_children():
            hijo.destroy()

        self._lbl_titulo_cal.configure(
            text=nombre_mes(self._anno_cal, self._mes_cal).capitalize()
        )

        encabezados = ("Lu", "Ma", "Mi", "Ju", "Vi", "Sá", "Do")
        for col, nombre_dia in enumerate(encabezados):
            self._rejilla_dias.grid_columnconfigure(col, weight=1)
            ctk.CTkLabel(
                self._rejilla_dias,
                text=nombre_dia,
                font=(FUENTE, 11, "bold"),
                text_color=COLORES["texto_secundario"],
            ).grid(row=0, column=col, pady=(6, 4))

        semanas = calendar.monthcalendar(self._anno_cal, self._mes_cal)
        for idx_sem, semana in enumerate(semanas, start=1):
            for col, num_dia in enumerate(semana):
                if num_dia == 0:
                    ctk.CTkLabel(self._rejilla_dias, text="").grid(
                        row=idx_sem, column=col, padx=2, pady=2
                    )
                    continue

                fecha_celda = date(self._anno_cal, self._mes_cal, num_dia)
                es_extremo = fecha_celda in (self._fecha_inicio, self._fecha_fin)
                en_rango = self._fecha_inicio < fecha_celda < self._fecha_fin

                if es_extremo:
                    color_fg = COLORES["acento"]
                    color_txt = COLORES["campo_texto"]
                    peso = "bold"
                elif en_rango:
                    color_fg = COLORES["fondo_contenido"]
                    color_txt = COLORES["texto"]
                    peso = "bold"
                else:
                    color_fg = COLORES["boton_lateral"]
                    color_txt = COLORES["texto"]
                    peso = "normal"

                btn_dia = ctk.CTkButton(
                    self._rejilla_dias,
                    text=str(num_dia),
                    width=38,
                    height=30,
                    corner_radius=6,
                    fg_color=color_fg,
                    hover_color=COLORES["acento_hover"],
                    text_color=color_txt,
                    font=(FUENTE, 12, peso),
                    command=lambda f=fecha_celda: self._al_clic_dia(f),
                )
                btn_dia.grid(row=idx_sem, column=col, padx=3, pady=3)

    def _etiqueta_para_seleccion(self) -> str:
        if self._preset_actual != "PERSONALIZADO":
            _, _, et = calcular_rango_preset(self._preset_actual)
            return et
        if self._fecha_inicio == self._fecha_fin:
            return f"Día {self._fecha_inicio.isoformat()}"
        return f"{self._fecha_inicio.strftime('%d/%m/%Y')} – {self._fecha_fin.strftime('%d/%m/%Y')}"

    def _confirmar(self):
        etiqueta = self._etiqueta_para_seleccion()
        self._al_aplicar(
            self._fecha_inicio, self._fecha_fin, self._preset_actual, etiqueta
        )
        self.destroy()
