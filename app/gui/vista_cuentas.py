"""Vista de cuentas y transferencias (módulo Cuentas).

Como en el mockup: total del balance por moneda (con opción de copiar),
lista de cuentas como píldoras del color de los botones, botón amarillo
de crear nueva cuenta, historial de transferencias con filtros de día,
semana, mes, año y período, y nueva transferencia entre cuentas.

Reglas de la tesis aplicadas aquí:
- No se suman monedas distintas: el total se muestra por moneda.
- Las cuentas marcadas como "no incluir en el balance total" no suman.
- Un fallo de base de datos se informa sin presentar datos parciales.
"""

import os
from datetime import date, timedelta
from tkinter import ttk, messagebox

import customtkinter as ctk

from app.gestor.gestor_financiero import totales_cuentas_por_moneda
from app.gui.calendario import SelectorCalendario
from app.gui.dialogo_cuenta import DialogoCuenta
from app.gui.dialogo_transferencia import DialogoTransferencia
from app.gui.estilos import COLORES, FUENTE, configurar_tabla
from app.gui.formato import formatear_valor
from app.gui.iconos import icono_tk


class VistaCuentas(ctk.CTkFrame):
    """Panel de cuentas: totales, lista de cuentas y transferencias."""

    def __init__(self, master, gestor, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._gestor = gestor
        self._cuentas = []
        self._ids_fila_cuenta = {}
        self._fecha_desde = None   # fecha de inicio del período elegido
        self._fecha_hasta = None   # fecha final del período elegido

        self._construir_encabezado()
        self._construir_lista_cuentas()
        self._construir_historial()

        self.refrescar()

    # ------------------------------------------------------------------
    # Encabezado: título, totales por moneda y botones
    # ------------------------------------------------------------------

    def _construir_encabezado(self):
        ctk.CTkLabel(self, text="Cuentas", font=(FUENTE, 22, "bold"),
                     text_color=COLORES["texto"]).pack(anchor="w")

        # Tarjeta del total: una línea por moneda, cada una con copiar.
        tarjeta_total = ctk.CTkFrame(self, fg_color=COLORES["fondo_tarjeta"],
                                    corner_radius=14)
        tarjeta_total.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(tarjeta_total, text="Balance total",
                     font=(FUENTE, 12, "bold"),
                     text_color=COLORES["texto"]).pack(
            anchor="w", padx=14, pady=(10, 2))
        self._marco_totales = ctk.CTkFrame(tarjeta_total,
                                            fg_color="transparent")
        self._marco_totales.pack(anchor="w", padx=14, pady=(0, 10))

        # Botones: crear cuenta (amarillo) y nueva transferencia.
        fila_botones = ctk.CTkFrame(self, fg_color="transparent")
        fila_botones.pack(fill="x", pady=(10, 0))
        ctk.CTkButton(fila_botones, text="Crear nueva cuenta", width=180,
                      height=36, corner_radius=18, font=(FUENTE, 12, "bold"),
                      fg_color=COLORES["acento"],
                      hover_color=COLORES["acento_hover"],
                      text_color="#10241C",
                      command=self._abrir_dialogo_cuenta).pack(side="left")
        ctk.CTkButton(fila_botones, text="Nueva transferencia", width=180,
                      height=36, corner_radius=18, font=(FUENTE, 12),
                      fg_color=COLORES["boton_lateral"],
                      hover_color=COLORES["hover_lateral"],
                      command=self._abrir_dialogo_transferencia).pack(
            side="left", padx=8)

    def _refrescar_totales(self, cuentas_con_saldo):
        """Muestra una línea de total por moneda, con botón de copiar.

        Nunca suma monedas distintas (regla de la tesis).
        """
        for hijo in self._marco_totales.winfo_children():
            hijo.destroy()

        totales = totales_cuentas_por_moneda(cuentas_con_saldo)
        if not totales:
            ctk.CTkLabel(self._marco_totales,
                         text="Sin cuentas todavía: cree la primera.",
                         font=(FUENTE, 12),
                         text_color=COLORES["texto_secundario"]).pack(
                anchor="w")
            return

        for moneda, total in totales.items():
            fila = ctk.CTkFrame(self._marco_totales, fg_color="transparent")
            fila.pack(anchor="w", pady=2)
            ctk.CTkLabel(fila, font=(FUENTE, 15, "bold"),
                         text_color=COLORES["texto"],
                         text=f"Total {moneda}: "
                              f"{formatear_valor(total, moneda)}").pack(
                side="left")
            ctk.CTkButton(
                fila, text="Copiar", width=80, height=26, corner_radius=13,
                font=(FUENTE, 10),
                fg_color=COLORES["boton_lateral"],
                hover_color=COLORES["hover_lateral"],
                command=lambda t=f"Total {moneda}: "
                                 f"{formatear_valor(total, moneda)}":
                        self._copiar_al_portapapeles(t),
            ).pack(side="left", padx=10)

    def _copiar_al_portapapeles(self, texto):
        """Copia el total al portapapeles de Windows."""
        self.clipboard_clear()
        self.clipboard_append(texto)
        self.update_idletasks()  # asegura que el portapapeles reciba el texto.

    # ------------------------------------------------------------------
    # Lista de cuentas (píldoras del color de los botones)
    # ------------------------------------------------------------------

    def _construir_lista_cuentas(self):
        tarjeta = ctk.CTkFrame(self, fg_color=COLORES["fondo_tarjeta"],
                               corner_radius=14)
        tarjeta.pack(fill="both", expand=True, pady=(10, 0))
        ctk.CTkLabel(tarjeta, text="Mis cuentas",
                     font=(FUENTE, 12, "bold"),
                     text_color=COLORES["texto"]).pack(
            anchor="w", padx=14, pady=(10, 4))

        # Tabla de cuentas: ícono en la columna árbol, nombre, saldo, moneda,
        # inclusión y nota.
        self._tabla_cuentas = ttk.Treeview(
            tarjeta, columns=("nombre", "saldo", "moneda", "total", "nota"),
            show="tree headings", selectmode="browse", height=5,
            style="Tablita.Treeview")
        # Columna #0 (árbol): ahí se muestra el ícono de cada cuenta,
        # a la izquierda del nombre.
        self._tabla_cuentas.heading("#0", text="", anchor="w")
        self._tabla_cuentas.column("#0", width=50, minwidth=50,
                                  stretch=False, anchor="w")
        encabezados = {
            "nombre": ("Cuenta", 200, "w"),
            "saldo": ("Saldo actual", 140, "e"),
            "moneda": ("Divisa", 70, "w"),
            "total": ("En balance total", 120, "w"),
            "nota":  ("Nota", 200, "w"),
        }
        for columna in ("nombre", "saldo", "moneda", "total", "nota"):
            texto, ancho, alineacion = encabezados[columna]
            # El título se alinea igual que los datos de su columna: así el
            # encabezado no queda centrado mientras los valores van a la
            # izquierda o derecha (causa del desfase reportado).
            self._tabla_cuentas.heading(columna, text=texto,
                                        anchor=alineacion)
            self._tabla_cuentas.column(columna, width=ancho,
                                        anchor=alineacion)
        self._tabla_cuentas.pack(fill="both", expand=True, padx=12,
                                 pady=(2, 6))

        # Detalle de la cuenta seleccionada: ícono grande a la izquierda,
        # nombre, saldo, inclusión en el balance total y nota.
        marco_detalle = ctk.CTkFrame(tarjeta, fg_color="transparent")
        marco_detalle.pack(fill="x", padx=14, pady=(2, 10))
        self._detalle_icono = ctk.CTkLabel(marco_detalle, text="", image=None)
        self._detalle_icono.pack(side="left", padx=(0, 12))
        marco_textos = ctk.CTkFrame(marco_detalle, fg_color="transparent")
        marco_textos.pack(side="left", fill="x", expand=True)
        self._detalle_titulo = ctk.CTkLabel(
            marco_textos,
            text="Seleccione una cuenta de la lista para ver su detalle.",
            font=(FUENTE, 15, "bold"), text_color=COLORES["texto"],
            anchor="w", justify="left")
        self._detalle_titulo.pack(anchor="w")
        self._detalle_saldo = ctk.CTkLabel(
            marco_textos, text="", font=(FUENTE, 13),
            text_color=COLORES["texto_secundario"], anchor="w",
            justify="left")
        self._detalle_saldo.pack(anchor="w")
        self._detalle_extra = ctk.CTkLabel(
            marco_textos, text="", font=(FUENTE, 11),
            text_color=COLORES["texto_secundario"], anchor="w",
            justify="left", wraplength=560)
        self._detalle_extra.pack(anchor="w")
        self._tabla_cuentas.bind("<<TreeviewSelect>>",
                                self._al_seleccionar_cuenta)
        self._ids_fila_cuenta = {}

    def _refrescar_cuentas(self, cuentas_con_saldo):
        """Llena la tabla de cuentas con nombre y saldo."""
        for elemento in self._tabla_cuentas.get_children():
            self._tabla_cuentas.delete(elemento)
        self._ids_fila_cuenta.clear()
        self._cuentas = cuentas_con_saldo

        for cuenta, saldo in cuentas_con_saldo:
            # El ícono de la cuenta (con su color) va en la columna árbol,
            # a la izquierda del nombre.
            elemento = self._tabla_cuentas.insert(
                "", "end", image=icono_tk(cuenta.simbolo, cuenta.color, 20),
                values=(
                    cuenta.nombre,
                    formatear_valor(saldo, cuenta.moneda),
                    cuenta.moneda,
                    "Sí" if cuenta.incluye_en_total else "No",
                    cuenta.nota or "",
                ))
            self._ids_fila_cuenta[elemento] = cuenta

    def _al_seleccionar_cuenta(self, evento=None):
        """Muestra el detalle de la cuenta seleccionada (con su ícono)."""
        seleccion = self._tabla_cuentas.selection()
        if not seleccion:
            return
        cuenta = self._ids_fila_cuenta.get(seleccion[0])
        if cuenta is None:
            return
        try:
            saldo = next(s for c, s in self._cuentas if c.id == cuenta.id)
        except StopIteration:
            saldo = cuenta.saldo_inicial

        self._detalle_icono.configure(
            image=icono_tk(cuenta.simbolo, cuenta.color, 48))
        self._detalle_titulo.configure(text=cuenta.nombre)
        self._detalle_saldo.configure(
            text=f"{formatear_valor(saldo, cuenta.moneda)} ({cuenta.moneda})")
        inclusion = ("Incluida en el balance total"
                     if cuenta.incluye_en_total
                     else "NO incluida en el balance total")
        nota = f" · Nota: {cuenta.nota}" if cuenta.nota else ""
        self._detalle_extra.configure(text=inclusion + nota)

    # ------------------------------------------------------------------
    # Historial de transferencias
    # ------------------------------------------------------------------

    def _construir_historial(self):
        tarjeta = ctk.CTkFrame(self, fg_color=COLORES["fondo_tarjeta"],
                               corner_radius=14)
        tarjeta.pack(fill="both", expand=True, pady=(10, 0))
        ctk.CTkLabel(tarjeta, text="Historial de transferencias",
                     font=(FUENTE, 12, "bold"),
                     text_color=COLORES["texto"]).pack(
            anchor="w", padx=14, pady=(10, 4))

        # Filtros: día, semana, mes, año y período.
        fila_filtros = ctk.CTkFrame(tarjeta, fg_color="transparent")
        fila_filtros.pack(fill="x", padx=14)
        ctk.CTkLabel(fila_filtros, text="Mostrar:", font=(FUENTE, 11),
                     text_color=COLORES["texto_secundario"]).pack(
            side="left", padx=(0, 6))
        self._filtro_actual = ctk.StringVar(value="Mes")
        for texto in ("Día", "Semana", "Mes", "Año", "Período"):
            ctk.CTkRadioButton(
                fila_filtros, text=texto, variable=self._filtro_actual,
                value=texto, corner_radius=6,
                fg_color=COLORES["acento"], hover_color=COLORES["acento_hover"],
                text_color=COLORES["texto"], font=(FUENTE, 11),
                command=self._al_cambiar_filtro,
            ).pack(side="left", padx=(0, 10))

        # Período personalizado: se eligen las dos fechas en un calendario.
        self._marco_periodo = ctk.CTkFrame(tarjeta, fg_color="transparent")
        ctk.CTkLabel(self._marco_periodo, text="Fecha de inicio:",
                     font=(FUENTE, 10),
                     text_color=COLORES["texto_secundario"]).pack(
            side="left", padx=(0, 4))
        self._boton_desde = ctk.CTkButton(
            self._marco_periodo, text="Elegir fecha", width=110, height=26,
            corner_radius=13, font=(FUENTE, 10),
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            command=self._elegir_fecha_inicio)
        self._boton_desde.pack(side="left", padx=(0, 12))
        ctk.CTkLabel(self._marco_periodo, text="Fecha final:",
                     font=(FUENTE, 10),
                     text_color=COLORES["texto_secundario"]).pack(
            side="left", padx=(0, 4))
        self._boton_hasta = ctk.CTkButton(
            self._marco_periodo, text="Elegir fecha", width=110, height=26,
            corner_radius=13, font=(FUENTE, 10),
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            command=self._elegir_fecha_final)
        self._boton_hasta.pack(side="left")

        # Tabla de transferencias.
        columnas = ("fecha", "origen", "destino", "valor", "moneda",
                    "comentarios")
        self._tabla_transferencias = ttk.Treeview(
            tarjeta, columns=columnas, show="headings", selectmode="browse",
            height=6, style="Tablita.Treeview")
        encabezados = {
            "fecha": ("Fecha", 110, "w"),
            "origen": ("Desde", 130, "w"),
            "destino": ("Hacia", 130, "w"),
            "valor": ("Valor", 120, "e"),
            "moneda": ("Divisa", 60, "w"),
            "comentarios": ("Comentarios", 200, "w"),
        }
        for columna in columnas:
            texto, ancho, alineacion = encabezados[columna]
            # Mismo anclaje para título y datos: evita el desfase.
            self._tabla_transferencias.heading(columna, text=texto,
                                              anchor=alineacion)
            self._tabla_transferencias.column(columna, width=ancho,
                                              anchor=alineacion)
        self._tabla_transferencias.pack(fill="both", expand=True, padx=12,
                                        pady=(6, 4))
        self._ids_fila_transferencia = {}

        # Botón para ver la imagen adjunta de la transferencia seleccionada.
        fila_ver = ctk.CTkFrame(tarjeta, fg_color="transparent")
        fila_ver.pack(fill="x", padx=14, pady=(0, 8))
        ctk.CTkButton(fila_ver, text="Ver imagen adjunta", width=170,
                      height=28, corner_radius=14, font=(FUENTE, 10),
                      fg_color=COLORES["boton_lateral"],
                      hover_color=COLORES["hover_lateral"],
                      command=self._ver_imagen).pack(side="left")

    # ------------------------------------------------------------------
    # Filtros del historial
    # ------------------------------------------------------------------

    def _al_cambiar_filtro(self):
        """Muestra (u oculta) las fechas del período personalizado."""
        if self._filtro_actual.get() == "Período":
            self._marco_periodo.pack(fill="x", padx=14, pady=(4, 0))
            # Al entrar al período se abren los dos calendarios seguidos:
            # primero la fecha de inicio y luego la fecha final.
            if self._fecha_desde is None:
                self._elegir_fecha_inicio()
        else:
            self._marco_periodo.pack_forget()
        self._refrescar_historial()

    def _elegir_fecha_inicio(self):
        """Abre el calendario para escoger la fecha de inicio."""
        SelectorCalendario(self, self._al_elegir_inicio,
                           fecha_inicial=self._fecha_desde)

    def _al_elegir_inicio(self, fecha):
        self._fecha_desde = fecha
        self._boton_desde.configure(text=fecha.isoformat())
        SelectorCalendario(self, self._al_elegir_final, fecha_inicial=fecha)

    def _elegir_fecha_final(self):
        """Abre el calendario para escoger (o cambiar) la fecha final."""
        SelectorCalendario(self, self._al_elegir_final,
                           fecha_inicial=self._fecha_hasta
                           or self._fecha_desde)

    def _al_elegir_final(self, fecha):
        if self._fecha_desde is not None and fecha < self._fecha_desde:
            messagebox.showwarning(
                "Fechas incoherentes",
                "La fecha final no puede ser anterior a la fecha de inicio.",
            )
            return
        self._fecha_hasta = fecha
        self._boton_hasta.configure(text=fecha.isoformat())
        self._refrescar_historial()

    def _rango_del_filtro(self):
        """Traduce el filtro activo a (fecha_inicio, fecha_fin)."""
        hoy = date.today()
        filtro = self._filtro_actual.get()
        if filtro == "Día":
            return hoy, hoy
        if filtro == "Semana":
            # Semana en curso: del lunes al domingo.
            lunes = hoy - timedelta(days=hoy.weekday())
            return lunes, lunes + timedelta(days=6)
        if filtro == "Mes":
            fin = (hoy.replace(month=hoy.month % 12 + 1, day=1)
                   if hoy.month != 12 else hoy.replace(year=hoy.year + 1,
                                                        month=1, day=1))
            return hoy.replace(day=1), fin - timedelta(days=1)
        if filtro == "Año":
            return (hoy.replace(month=1, day=1),
                    hoy.replace(month=12, day=31))
        # Período personalizado: fechas elegidas en el calendario.
        return self._fecha_desde, self._fecha_hasta

    # ------------------------------------------------------------------
    # Actualización de datos
    # ------------------------------------------------------------------

    def refrescar(self):
        """Consulta cuentas y transferencias; un fallo se informa aparte."""
        try:
            cuentas_con_saldo = self._gestor.obtener_cuentas()
        except Exception as error:
            messagebox.showerror(
                "Error de base de datos",
                f"No se pudieron consultar las cuentas: {error}",
            )
            return

        self._refrescar_totales(cuentas_con_saldo)
        self._refrescar_cuentas(cuentas_con_saldo)
        self._refrescar_historial()

    def _refrescar_historial(self):
        """Consulta las transferencias del filtro activo y llena la tabla."""
        inicio, fin = self._rango_del_filtro()
        if self._filtro_actual.get() == "Período":
            # Sin las dos fechas no hay nada que consultar todavía (el
            # calendario se abre justo al elegir el período).
            if inicio is None or fin is None:
                return

        try:
            transferencias = self._gestor.obtener_transferencias(
                inicio or None, fin or None)
        except Exception as error:
            messagebox.showerror(
                "Error de base de datos",
                f"No se pudieron consultar las transferencias: {error}",
            )
            return

        for elemento in self._tabla_transferencias.get_children():
            self._tabla_transferencias.delete(elemento)
        self._ids_fila_transferencia.clear()

        for fila in transferencias:
            (id_transferencia, fecha, origen, destino, valor, moneda,
             comentarios, imagen) = fila
            elemento = self._tabla_transferencias.insert("", "end", values=(
                fecha.isoformat() if hasattr(fecha, "isoformat") else fecha,
                origen, destino, formatear_valor(valor, moneda), moneda,
                ("📎 " if imagen else "") + (comentarios or ""),
            ))
            self._ids_fila_transferencia[elemento] = fila

    def _ver_imagen(self):
        """Abre la imagen adjunta de la transferencia seleccionada."""
        seleccion = self._tabla_transferencias.selection()
        if not seleccion:
            messagebox.showwarning(
                "Ninguna transferencia seleccionada",
                "Seleccione una transferencia para ver su imagen.",
            )
            return
        fila = self._ids_fila_transferencia.get(seleccion[0])
        if fila is None or not fila[7]:
            messagebox.showinformation(
                "Sin imagen",
                "La transferencia seleccionada no tiene imagen adjunta.",
            )
            return
        ruta = fila[7]
        if not os.path.exists(ruta):
            messagebox.showerror(
                "Imagen no encontrada",
                f"El archivo ya no existe: {ruta}",
            )
            return
        os.startfile(ruta)  # la abre el visor de imágenes de Windows.

    # ------------------------------------------------------------------
    # Diálogos
    # ------------------------------------------------------------------

    def _abrir_dialogo_cuenta(self):
        DialogoCuenta(self, self._gestor, self._al_crear_cuenta)

    def _al_crear_cuenta(self, cuenta):
        self.refrescar()

    def _abrir_dialogo_transferencia(self):
        DialogoTransferencia(self, self._gestor, self._al_crear_transferencia)

    def _al_crear_transferencia(self, transferencia):
        self.refrescar()
