"""Vista de movimientos financieros (ingresos y gastos) — CU-01.

Presenta el formulario de registro, la tabla con los movimientos
guardados y la eliminación con confirmación. Basada en el mockup de la
tesis (tarjetas verdes oscuras, botones redondeados y acentos dorados).

Reglas de la tesis aplicadas aquí:
- Si una validación falla, se informa el error y se conservan los datos
  diligenciados (no se limpia el formulario).
- La eliminación pide confirmación antes de ejecutarse.
- Un fallo de base de datos se informa sin presentar la operación como
  exitosa.
"""

from datetime import date
from tkinter import ttk, messagebox

import customtkinter as ctk

from app.gestor.gestor_financiero import ErrorValidacion, totales_por_moneda
from app.gui.estilos import COLORES, FUENTE
from app.gui.formato import formatear_valor

ETIQUETAS_TIPO = {"INGRESO": "Ingreso", "GASTO": "Gasto"}


class VistaMovimientos(ctk.CTkFrame):
    """Panel de registro, consulta y eliminación de movimientos."""

    def __init__(self, master, gestor, filtro_tipo=None, titulo="Movimientos", **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._gestor = gestor
        self._filtro_tipo = filtro_tipo
        self._ids_tabla = {}

        self._construir_encabezado()

        # Cuerpo: formulario a la izquierda, tabla a la derecha.
        cuerpo = ctk.CTkFrame(self, fg_color="transparent")
        cuerpo.pack(fill="both", expand=True, pady=(12, 0))
        cuerpo.columnconfigure(1, weight=1)
        cuerpo.rowconfigure(0, weight=1)

        self._construir_formulario(cuerpo)
        self._construir_tabla(cuerpo)
        self._cargar_categorias()
        self.refrescar()

    # ------------------------------------------------------------------
    # Encabezado del módulo
    # ------------------------------------------------------------------

    def _construir_encabezado(self):
        encabezado = ctk.CTkFrame(self, fg_color="transparent")
        encabezado.pack(fill="x")
        ctk.CTkLabel(encabezado, text=titulo, font=(FUENTE, 22, "bold"),
                     text_color=COLORES["texto"], anchor="w").pack(fill="x")
        ctk.CTkLabel(
            encabezado, text="Registro manual de ingresos y gastos",
            font=(FUENTE, 12),
            text_color=COLORES["texto_secundario"], anchor="w").pack(fill="x")

    # ------------------------------------------------------------------
    # Formulario de registro
    # ------------------------------------------------------------------

    def _construir_formulario(self, cuerpo):
        tarjeta = ctk.CTkFrame(cuerpo, fg_color=COLORES["fondo_tarjeta"],
                               corner_radius=14, width=320)
        tarjeta.grid(row=0, column=0, sticky="nsw", padx=(0, 12))

        ctk.CTkLabel(tarjeta, text="Registrar movimiento",
                     font=(FUENTE, 14, "bold"),
                     text_color=COLORES["texto"]).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(14, 10))

        def etiqueta(texto, fila):
            ctk.CTkLabel(tarjeta, text=texto, font=(FUENTE, 11),
                         text_color=COLORES["texto_secundario"]).grid(
                row=fila, column=0, sticky="w", pady=5)

        # Tipo de movimiento.
        etiqueta("Tipo", 1)
        self._campo_tipo = ctk.CTkComboBox(tarjeta, values=["Ingreso", "Gasto"],
                                           state="readonly", width=180,
                                           corner_radius=8)
        self._campo_tipo.set("Gasto" if self._filtro_tipo != "INGRESO" else "Ingreso")
        self._campo_tipo.grid(row=1, column=1, sticky="we", pady=5)

        # Fecha (formato AAAA-MM-DD; valor inicial: día actual).
        etiqueta("Fecha (AAAA-MM-DD)", 2)
        self._campo_fecha = ctk.CTkEntry(tarjeta, width=180, corner_radius=8)
        self._campo_fecha.insert(0, date.today().isoformat())
        self._campo_fecha.grid(row=2, column=1, sticky="we", pady=5)

        # Valor: número mayor que cero, sin separadores de miles.
        etiqueta("Valor (ej.: 15000 o 15000.50)", 3)
        self._campo_valor = ctk.CTkEntry(tarjeta, width=180, corner_radius=8)
        self._campo_valor.grid(row=3, column=1, sticky="we", pady=5)

        # Moneda.
        etiqueta("Moneda", 4)
        self._campo_moneda = ctk.CTkComboBox(tarjeta, values=["COP", "USD"],
                                             state="readonly", width=180,
                                             corner_radius=8)
        self._campo_moneda.set("COP")
        self._campo_moneda.grid(row=4, column=1, sticky="we", pady=5)

        # Categoría (catálogo guardado en la base de datos).
        etiqueta("Categoría", 5)
        self._campo_categoria = ctk.CTkComboBox(tarjeta, state="readonly",
                                                 width=180, corner_radius=8)
        self._campo_categoria.grid(row=5, column=1, sticky="we", pady=5)

        # Descripción opcional.
        etiqueta("Descripción (opcional)", 6)
        self._campo_descripcion = ctk.CTkEntry(tarjeta, width=180, corner_radius=8)
        self._campo_descripcion.grid(row=6, column=1, sticky="we", pady=5)

        # Acciones del formulario (botones redondeados como en el mockup).
        botones = ctk.CTkFrame(tarjeta, fg_color="transparent")
        botones.grid(row=7, column=0, columnspan=2, sticky="we", pady=(12, 0))
        ctk.CTkButton(botones, text="Guardar movimiento",
                      corner_radius=16, height=34,
                      fg_color=COLORES["acento"], hover_color=COLORES["acento_hover"],
                      text_color="#10241C", font=(FUENTE, 11, "bold"),
                      command=self._al_guardar).pack(side="left")
        ctk.CTkButton(botones, text="Limpiar campos",
                      corner_radius=16, height=34,
                      fg_color=COLORES["boton_lateral"],
                      hover_color=COLORES["hover_lateral"],
                      font=(FUENTE, 11),
                      command=lambda: self._limpiar_formulario()).pack(
            side="left", padx=8)

        # Mensaje de estado (éxito o error) bajo los botones.
        self._etiqueta_estado = ctk.CTkLabel(tarjeta, text="", wraplength=260,
                                             justify="left", font=(FUENTE, 11),
                                             text_color=COLORES["texto"])
        self._etiqueta_estado.grid(row=8, column=0, columnspan=2,
                                   sticky="we", pady=(8, 12))

    def _cargar_categorias(self):
        """Carga el catálogo de categorías desde la base de datos."""
        try:
            categorias = self._gestor.obtener_categorias()
            self._campo_categoria.configure(values=categorias)
            if categorias:
                self._campo_categoria.set(categorias[0])
        except Exception as error:
            messagebox.showerror(
                "Error de base de datos",
                f"No se pudieron cargar las categorías: {error}",
            )

    # ------------------------------------------------------------------
    # Tabla de movimientos
    # ------------------------------------------------------------------

    def _construir_tabla(self, cuerpo):
        contenedor = ctk.CTkFrame(cuerpo, fg_color=COLORES["fondo_tarjeta"],
                                  corner_radius=14)
        contenedor.grid(row=0, column=1, sticky="nsew")

        ctk.CTkLabel(contenedor, text="Movimientos guardados",
                     font=(FUENTE, 14, "bold"),
                     text_color=COLORES["texto"]).pack(anchor="w", padx=14,
                                                        pady=(12, 4))

        columnas = ("fecha", "tipo", "categoria", "valor", "moneda", "descripcion")
        # Tabla: customtkinter no incluye una; se usa el Treeview de ttk
        # con los colores del tema.
        self._tabla = ttk.Treeview(contenedor, columns=columnas,
                                    show="headings", selectmode="browse",
                                    style="Tablita.Treeview")
        encabezados = {
            "fecha": ("Fecha", 90, "w"),
            "tipo": ("Tipo", 70, "w"),
            "categoria": ("Categoría", 130, "w"),
            "valor": ("Valor", 120, "e"),
            "moneda": ("Moneda", 60, "w"),
            "descripcion": ("Descripción", 170, "w"),
        }
        for columna in columnas:
            texto, ancho, alineacion = encabezados[columna]
            self._tabla.heading(columna, text=texto)
            self._tabla.column(columna, width=ancho, anchor=alineacion)

        barra = ttk.Scrollbar(contenedor, orient="vertical",
                              command=self._tabla.yview)
        self._tabla.configure(yscrollcommand=barra.set)
        self._tabla.pack(side="left", fill="both", expand=True, pady=(6, 0),
                         padx=(10, 0))
        barra.pack(side="right", fill="y", pady=(6, 0), padx=(0, 6))

        # Fila de acciones y totales bajo la tabla.
        pie = ctk.CTkFrame(contenedor, fg_color="transparent")
        pie.pack(fill="x", pady=(8, 12), padx=14)
        ctk.CTkButton(pie, text="Actualizar lista",
                      corner_radius=14, height=30,
                      fg_color=COLORES["boton_lateral"],
                      hover_color=COLORES["hover_lateral"],
                      font=(FUENTE, 11),
                      command=self.refrescar).pack(side="left")
        ctk.CTkButton(pie, text="Eliminar seleccionado",
                      corner_radius=14, height=30,
                      fg_color=COLORES["boton_lateral"],
                      hover_color=COLORES["hover_lateral"],
                      font=(FUENTE, 11),
                      command=self._al_eliminar).pack(side="left", padx=8)
        self._etiqueta_totales = ctk.CTkLabel(pie, text="",
                                              font=(FUENTE, 11),
                                              text_color=COLORES["texto"])
        self._etiqueta_totales.pack(side="right")

    def refrescar(self):
        """Vuelve a consultar los movimientos y actualiza la tabla.

        Un fallo de consulta se informa y se conservan los datos previos
        de la tabla; no se presenta como actualización exitosa.
        """
        try:
            movimientos = self._gestor.obtener_movimientos(self._filtro_tipo)
        except Exception as error:
            messagebox.showerror(
                "Error de base de datos",
                f"No se pudieron consultar los movimientos: {error}",
            )
            return

        for elemento in self._tabla.get_children():
            self._tabla.delete(elemento)
        self._ids_tabla.clear()

        for movimiento in movimientos:
            elemento = self._tabla.insert("", "end", values=(
                movimiento.fecha.isoformat(),
                ETIQUETAS_TIPO.get(movimiento.tipo_movimiento, movimiento.tipo_movimiento),
                movimiento.categoria,
                formatear_valor(movimiento.valor, movimiento.moneda),
                movimiento.moneda,
                movimiento.descripcion or "",
            ))
            self._ids_tabla[elemento] = movimiento.id

        self._actualizar_totales(movimientos)

    def _actualizar_totales(self, movimientos):
        """Muestra la suma de los movimientos listados, separada por moneda.

        No se suman importes de monedas distintas: cada moneda muestra su
        propio total hasta que se apruebe una regla de conversión.
        """
        totales = totales_por_moneda(movimientos)
        if not totales:
            self._etiqueta_totales.configure(text="Sin movimientos guardados.")
        else:
            partes = [f"{moneda}: {formatear_valor(total, moneda)}"
                      for moneda, total in totales.items()]
            self._etiqueta_totales.configure(text="Suma · " + " · ".join(partes))

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------

    def _al_guardar(self):
        """Valida y guarda el movimiento; conserva los datos si hay error."""
        try:
            self._gestor.registrar_movimiento(
                tipo=self._campo_tipo.get(),
                fecha_texto=self._campo_fecha.get(),
                valor_texto=self._campo_valor.get(),
                moneda=self._campo_moneda.get(),
                categoria=self._campo_categoria.get(),
                descripcion=self._campo_descripcion.get(),
            )
        except ErrorValidacion as error:
            # Regla de la tesis: informar el error y conservar lo diligenciado.
            self._etiqueta_estado.configure(
                text=f"No se guardó: {error}", text_color=COLORES["error"])
            messagebox.showerror("Datos incompletos o inválidos", str(error))
            return
        except Exception as error:
            # Error de almacenamiento: se informa, sin presentar éxito.
            self._etiqueta_estado.configure(
                text="No se pudo guardar el movimiento.",
                text_color=COLORES["error"])
            messagebox.showerror(
                "Error de almacenamiento",
                "El movimiento no pudo guardarse. Verifique que PostgreSQL esté "
                f"en ejecución.\n\nDetalle: {error}",
            )
            return

        self._etiqueta_estado.configure(
            text="Movimiento guardado correctamente.",
            text_color=COLORES["exito"])
        self._limpiar_formulario(limpiar_estado=False)
        self.refrescar()

    def _al_eliminar(self):
        """Elimina el movimiento seleccionado, con confirmación previa."""
        seleccion = self._tabla.selection()
        if not seleccion:
            messagebox.showwarning(
                "Ningún movimiento seleccionado",
                "Seleccione un movimiento de la lista para eliminarlo.",
            )
            return

        id_movimiento = self._ids_tabla[seleccion[0]]
        confirmado = messagebox.askyesno(
            "Confirmar eliminación",
            "¿Desea eliminar el movimiento seleccionado?\n"
            "Esta acción no se puede deshacer.",
        )
        if not confirmado:
            return

        try:
            eliminado = self._gestor.eliminar_movimiento(id_movimiento)
        except Exception as error:
            messagebox.showerror(
                "Error de almacenamiento",
                f"El movimiento no pudo eliminarse.\n\nDetalle: {error}",
            )
            return

        if not eliminado:
            messagebox.showwarning(
                "Movimiento no encontrado",
                "El movimiento ya no existe. Se actualizará la lista.",
            )
        self.refrescar()

    def _limpiar_formulario(self, limpiar_estado=True):
        """Restablece el formulario a sus valores iniciales."""
        self._campo_fecha.delete(0, "end")
        self._campo_fecha.insert(0, date.today().isoformat())
        self._campo_valor.delete(0, "end")
        self._campo_descripcion.delete(0, "end")
        if limpiar_estado:
            self._etiqueta_estado.configure(text="")
