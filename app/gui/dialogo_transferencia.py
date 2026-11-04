"""Diálogo para crear una nueva transferencia entre cuentas.

Campos acordados: cuenta actual (origen), cuenta objetivo (destino),
cantidad (con calculadora incorporada), divisa (la de las cuentas: solo
se permiten cuentas de la misma moneda), fecha con selector de calendario
y formato legible, comentarios opcionales e imagen adjunta opcional.
"""

import os
import shutil
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from app.gestor.gestor_financiero import ErrorValidacion
from app.gui.calculadora import Calculadora
from app.gui.calendario import SelectorCalendario
from app.gui.campo_moneda import CampoMoneda
from app.gui.estilos import COLORES, FUENTE
from app.gui.formato import fecha_legible, formatear_valor

# Carpeta local para los adjuntos (no se versiona: ver .gitignore).
RUTA_ADJUNTOS = Path(__file__).resolve().parents[2] / "adjuntos"

# Límite del adjunto: 2 MB (acordado como tamaño máximo razonable).
MAXIMO_ADJUNTO_BYTES = 2 * 1024 * 1024


class DialogoTransferencia(ctk.CTkToplevel):
    """Ventana para registrar una transferencia entre dos cuentas."""

    def __init__(self, master, gestor, al_crear, **kwargs):
        super().__init__(master, **kwargs)
        self._gestor = gestor
        self._al_crear = al_crear

        self.title("Nueva transferencia")
        self.geometry("720x560")
        self.resizable(False, False)
        self.configure(fg_color=COLORES["fondo_tarjeta"])
        self.transient(master)
        self.grab_set()

        self._fecha_elegida = date.today()
        self._ruta_imagen = None

        self._construir_formulario()
        self._cargar_cuentas()

        self.protocol("WM_DELETE_WINDOW", self.destroy)

    # ------------------------------------------------------------------
    # Formulario
    # ------------------------------------------------------------------

    def _construir_formulario(self):
        # El cuerpo es desplazable: todos los campos quedan alcanzables
        # incluso en pantallas pequeñas.
        cuerpo = ctk.CTkScrollableFrame(self, fg_color="transparent")
        cuerpo.pack(fill="both", expand=True, padx=14, pady=(8, 0))

        ctk.CTkLabel(cuerpo, text="Nueva transferencia",
                     font=(FUENTE, 18, "bold"),
                     text_color=COLORES["texto"]).pack(anchor="w")

        # Cuenta actual (origen) y cuenta objetivo (destino).
        fila_cuentas = ctk.CTkFrame(cuerpo, fg_color="transparent")
        fila_cuentas.pack(fill="x", pady=(10, 0))
        columna_origen = ctk.CTkFrame(fila_cuentas, fg_color="transparent")
        columna_origen.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(columna_origen, text="Cuenta actual (sale la plata) *",
                     font=(FUENTE, 11),
                     text_color=COLORES["texto_secundario"]).pack(
            anchor="w", pady=(0, 2))
        self._campo_origen = ctk.CTkComboBox(
            columna_origen, state="readonly", corner_radius=8,
            command=lambda _v: self._al_cambiar_origen())
        self._campo_origen.pack(fill="x")

        columna_destino = ctk.CTkFrame(fila_cuentas, fg_color="transparent")
        columna_destino.pack(side="left", padx=(18, 0), fill="x", expand=True)
        ctk.CTkLabel(columna_destino, text="Cuenta objetivo (llega la plata) *",
                     font=(FUENTE, 11),
                     text_color=COLORES["texto_secundario"]).pack(
            anchor="w", pady=(0, 2))
        self._campo_destino = ctk.CTkComboBox(
            columna_destino, state="readonly", corner_radius=8)
        self._campo_destino.pack(fill="x")

        # Cantidad + divisa + calculadora al lado.
        fila_valor = ctk.CTkFrame(cuerpo, fg_color="transparent")
        fila_valor.pack(fill="x", pady=(12, 0))
        columna_valor = ctk.CTkFrame(fila_valor, fg_color="transparent")
        columna_valor.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(columna_valor, text="Cantidad (ej.: 15.000 o 15.000,50)",
                     font=(FUENTE, 11),
                     text_color=COLORES["texto_secundario"]).pack(
            anchor="w", pady=(0, 2))
        # Los miles se separan solos mientras se escribe (estilo colombiano).
        self._campo_valor = CampoMoneda(columna_valor, width=200,
                                        corner_radius=8)
        self._campo_valor.pack(anchor="w")

        columna_moneda = ctk.CTkFrame(fila_valor, fg_color="transparent")
        columna_moneda.pack(side="left", padx=(18, 0))
        ctk.CTkLabel(columna_moneda, text="Divisa",
                     font=(FUENTE, 11),
                     text_color=COLORES["texto_secundario"]).pack(
            anchor="w", pady=(0, 2))
        self._etiqueta_moneda = ctk.CTkLabel(
            columna_moneda, text="—", font=(FUENTE, 12, "bold"),
            text_color=COLORES["texto"])
        self._etiqueta_moneda.pack(anchor="w", pady=(4, 0))

        # Calculadora: el resultado se escribe en el campo de cantidad.
        self._calculadora = Calculadora(cuerpo, self._campo_valor)
        self._calculadora.pack(anchor="w", pady=(10, 0))

        # Fecha: texto legible + botón de calendario emergente.
        ctk.CTkLabel(cuerpo, text="Fecha *",
                     font=(FUENTE, 11),
                     text_color=COLORES["texto_secundario"]).pack(
            anchor="w", pady=(12, 2))
        fila_fecha = ctk.CTkFrame(cuerpo, fg_color="transparent")
        fila_fecha.pack(anchor="w")
        self._etiqueta_fecha = ctk.CTkLabel(
            fila_fecha, text=fecha_legible(self._fecha_elegida),
            font=(FUENTE, 12), text_color=COLORES["texto"])
        self._etiqueta_fecha.pack(side="left")
        ctk.CTkButton(fila_fecha, text="Cambiar fecha", width=130, height=30,
                      corner_radius=14, font=(FUENTE, 11),
                      fg_color=COLORES["boton_lateral"],
                      hover_color=COLORES["hover_lateral"],
                      command=self._abrir_calendario).pack(
            side="left", padx=10)

        # Comentarios e imagen adjunta.
        ctk.CTkLabel(cuerpo, text="Comentarios (opcional)",
                     font=(FUENTE, 11),
                     text_color=COLORES["texto_secundario"]).pack(
            anchor="w", pady=(10, 2))
        self._campo_comentarios = ctk.CTkEntry(cuerpo, width=380,
                                               corner_radius=8)
        self._campo_comentarios.pack(anchor="w")

        fila_imagen = ctk.CTkFrame(cuerpo, fg_color="transparent")
        fila_imagen.pack(anchor="w", pady=(8, 0))
        ctk.CTkButton(fila_imagen, text="Subir imagen (opcional, máx. 2 MB)",
                      width=240, height=30, corner_radius=14,
                      font=(FUENTE, 11),
                      fg_color=COLORES["boton_lateral"],
                      hover_color=COLORES["hover_lateral"],
                      command=self._subir_imagen).pack(side="left")
        self._etiqueta_imagen = ctk.CTkLabel(
            fila_imagen, text="Ninguna", font=(FUENTE, 10),
            text_color=COLORES["texto_secundario"])
        self._etiqueta_imagen.pack(side="left", padx=10)

        # Mensaje de estado (éxito o error).
        self._etiqueta_estado = ctk.CTkLabel(cuerpo, text="",
                                             font=(FUENTE, 11),
                                             text_color=COLORES["error"])
        self._etiqueta_estado.pack(anchor="w", pady=(6, 0))

        # Botón de añadir: amarillo (acento), como se acordó.
        ctk.CTkButton(cuerpo, text="Añadir", width=160, height=38,
                      corner_radius=18, font=(FUENTE, 13, "bold"),
                      fg_color=COLORES["acento"],
                      hover_color=COLORES["acento_hover"],
                      text_color="#10241C",
                      command=self._al_aniadir).pack(pady=(10, 0))

    # ------------------------------------------------------------------
    # Cuentas, divisa y fecha
    # ------------------------------------------------------------------

    def _cargar_cuentas(self):
        """Llena los combos con las cuentas y preselecciona la primera."""
        try:
            self._cuentas = self._gestor.obtener_cuentas()
        except Exception as error:
            messagebox.showerror("Error de base de datos",
                                f"No se pudieron cargar las cuentas: {error}")
            self._cuentas = []
            return

        nombres = [cuenta.nombre for cuenta, _saldo in self._cuentas]
        self._campo_origen.configure(values=nombres)
        self._campo_destino.configure(values=nombres)
        if nombres:
            self._campo_origen.set(nombres[0])
            self._al_cambiar_origen()

    def _cuenta_por_nombre(self, nombre):
        for cuenta, _saldo in self._cuentas:
            if cuenta.nombre == nombre:
                return cuenta
        return None

    def _al_cambiar_origen(self):
        """Al elegir la cuenta origen, se muestra su divisa y el destino
        solo ofrece cuentas de esa misma moneda."""
        origen = self._cuenta_por_nombre(self._campo_origen.get())
        if origen is None:
            return
        self._etiqueta_moneda.configure(text=origen.moneda)
        compatibles = [cuenta.nombre for cuenta, _saldo in self._cuentas
                       if cuenta.moneda == origen.moneda
                       and cuenta.id != origen.id]
        self._campo_destino.configure(values=compatibles)
        if compatibles:
            self._campo_destino.set(compatibles[0])

    def _abrir_calendario(self):
        SelectorCalendario(self, self._al_elegir_fecha,
                           fecha_inicial=self._fecha_elegida)

    def _al_elegir_fecha(self, fecha):
        self._fecha_elegida = fecha
        self._etiqueta_fecha.configure(text=fecha_legible(fecha))

    # ------------------------------------------------------------------
    # Imagen adjunta
    # ------------------------------------------------------------------

    def _subir_imagen(self):
        """Escoge una imagen (PNG/JPG, máx. 2 MB) y la copia a adjuntos/."""
        ruta = filedialog.askopenfilename(
            parent=self,
            title="Seleccionar imagen",
            filetypes=[("Imágenes", "*.png *.jpg *.jpeg"), ("Todos", "*.*")],
        )
        if not ruta:
            return
        try:
            from PIL import Image  # validación de que es una imagen real.

            with Image.open(ruta) as imagen:
                imagen.verify()
        except Exception:
            self._etiqueta_estado.configure(
                text="El archivo escogido no es una imagen válida.",
                text_color=COLORES["error"])
            return
        if os.path.getsize(ruta) > MAXIMO_ADJUNTO_BYTES:
            self._etiqueta_estado.configure(
                text="La imagen supera el límite de 2 MB.",
                text_color=COLORES["error"])
            return

        RUTA_ADJUNTOS.mkdir(exist_ok=True)
        extension = Path(ruta).suffix.lower() or ".png"
        destino = RUTA_ADJUNTOS / (
            f"transferencia_{date.today().strftime('%Y%m%d%H%M%S')}"
            f"_{os.getpid()}{extension}")
        shutil.copy2(ruta, destino)
        self._ruta_imagen = str(destino)
        self._etiqueta_imagen.configure(text=Path(ruta).name)

    # ------------------------------------------------------------------
    # Guardar
    # ------------------------------------------------------------------

    def _al_aniadir(self):
        """Valida y guarda la transferencia; conserva los datos si hay error."""
        origen = self._cuenta_por_nombre(self._campo_origen.get())
        destino = self._cuenta_por_nombre(self._campo_destino.get())
        if origen is None or destino is None:
            self._etiqueta_estado.configure(
                text="Seleccione las cuentas de origen y destino.",
                text_color=COLORES["error"])
            return

        try:
            transferencia = self._gestor.crear_transferencia(
                cuenta_origen_id=origen.id,
                cuenta_destino_id=destino.id,
                # El campo envía el valor sin separadores de miles.
                valor_texto=self._campo_valor.obtener_valor(),
                fecha_texto=self._fecha_elegida.isoformat(),
                comentarios=self._campo_comentarios.get(),
                imagen=self._ruta_imagen,
            )
        except ErrorValidacion as error:
            # Regla de la tesis: informar el error y conservar lo diligenciado.
            self._etiqueta_estado.configure(text=str(error),
                                           text_color=COLORES["error"])
            return
        except Exception as error:
            self._etiqueta_estado.configure(
                text=f"No se pudo guardar la transferencia: {error}",
                text_color=COLORES["error"])
            return

        self._al_crear(transferencia)
        self.destroy()
