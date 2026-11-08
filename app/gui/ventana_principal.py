"""Ventana principal de NexSaldo con barra lateral de navegación y caché de vistas (sin reconstruir la app al cambiar de sección)."""

from pathlib import Path
import threading
from typing import Dict, Optional
import customtkinter as ctk
from PIL import Image

from app.gui.adaptadores_moneda import (
    VistaCuentasConDivisa,
    VistaMovimientosConDivisa,
)
from app.gui.estilos import COLORES, FUENTE, configurar_tabla, configurar_tema
from app.gui.vista_gastos import VistaGastos
from app.gui.vista_ingresos import VistaIngresos
from app.gui.vista_inversiones import VistaInversiones
from app.gui.vista_resumen import VistaResumen

RUTA_LOGO = Path(__file__).resolve().parent / "recursos" / "logo_64.png"

NAVEGACION = [
    ("Resumen", "resumen"),
    ("Cuentas", "cuentas"),
    ("Gastos", "gastos"),
    ("Ingresos", "ingresos"),
    ("Inversiones", "inversiones"),
    ("Reportes", "pendiente"),
    ("Categorías", "pendiente"),
    ("Configuración", "pendiente"),
    ("Modo Oscuro", "tema"),
]

MODULOS_PENDIENTES = {
    "Reportes": "Análisis y gráficos detallados en desarrollo.",
    "Categorías": "Gestión de categorías personalizadas en desarrollo.",
    "Configuración": "Ajustes y exportación de datos en desarrollo.",
}

ANCHO_BARRA = 200


class VentanaPrincipal(ctk.CTk):
    """Ventana raíz con barra de navegación lateral y caché de vistas para transición instantánea."""

    def __init__(self, gestor):
        super().__init__()
        self.title("NexSaldo")
        self.geometry("1100x680")
        self.minsize(960, 600)

        configurar_tema()
        configurar_tabla(self)
        self.configure(fg_color=COLORES["fondo_contenido"])

        self._gestor = gestor
        self._vista_actual: Optional[ctk.CTkFrame] = None
        self._clave_vista_actual: Optional[str] = None
        self._vistas_cache: Dict[str, ctk.CTkFrame] = {}
        self._botones = {}
        self._logo_img = self._cargar_logo()

        self._construir_barra_lateral()
        self._construir_area_contenido()
        self._al_navegar("resumen", "Resumen")

        # Precalentar en segundo plano las tasas principales (USD->COP, EUR->COP) para que
        # al cambiar de moneda en Gastos/Ingresos/Inversiones la conversión sea instantánea (0ms)
        self.after(120, self._precalentar_tasas_principales)

    def _precalentar_tasas_principales(self):
        def _tarea():
            try:
                if hasattr(self._gestor, "obtener_tasa_cambio"):
                    self._gestor.obtener_tasa_cambio("USD", "COP", forzar_actualizacion=False)
            except Exception:
                pass

        threading.Thread(target=_tarea, daemon=True).start()

    def _cargar_logo(self):
        try:
            img = Image.open(RUTA_LOGO)
            return ctk.CTkImage(light_image=img, dark_image=img, size=(48, 48))
        except Exception:
            return None

    def _construir_barra_lateral(self):
        barra = ctk.CTkFrame(
            self,
            width=ANCHO_BARRA,
            fg_color=COLORES["fondo_lateral"],
            corner_radius=0,
        )
        barra.pack(side="left", fill="y")
        barra.pack_propagate(False)

        cabecera = ctk.CTkFrame(barra, fg_color="transparent")
        cabecera.pack(fill="x", pady=(18, 14), padx=14)
        if self._logo_img is not None:
            ctk.CTkLabel(cabecera, image=self._logo_img, text="").pack()
        ctk.CTkLabel(
            cabecera,
            text="NexSaldo",
            font=(FUENTE, 18, "bold"),
            text_color=COLORES["texto"],
        ).pack(pady=(4, 0))

        arriba = NAVEGACION[:6]
        abajo = NAVEGACION[6:]

        marco_arriba = ctk.CTkFrame(barra, fg_color="transparent")
        marco_arriba.pack(fill="x", padx=12)
        for texto, modulo in arriba:
            self._crear_boton_nav(marco_arriba, texto, modulo)

        marco_abajo = ctk.CTkFrame(barra, fg_color="transparent")
        marco_abajo.pack(side="bottom", fill="x", padx=12, pady=(0, 16))
        for texto, modulo in abajo:
            self._crear_boton_nav(marco_abajo, texto, modulo)

    def _crear_boton_nav(self, contenedor, texto, modulo):
        boton = ctk.CTkButton(
            contenedor,
            text=texto,
            anchor="w",
            height=36,
            corner_radius=18,
            fg_color=COLORES["boton_lateral"],
            hover_color=COLORES["hover_lateral"],
            text_color=COLORES["texto"],
            font=(FUENTE, 13, "bold"),
            command=lambda m=modulo, t=texto: self._al_navegar(m, t),
        )
        boton.pack(fill="x", pady=4)
        self._botones[texto] = boton

    def _resaltar_boton(self, texto_activo):
        for texto, boton in self._botones.items():
            if texto == texto_activo:
                boton.configure(
                    fg_color=COLORES["acento"],
                    hover_color=COLORES["acento_hover"],
                    text_color=COLORES["campo_texto"],
                )
            else:
                boton.configure(
                    fg_color=COLORES["boton_lateral"],
                    hover_color=COLORES["hover_lateral"],
                    text_color=COLORES["texto"],
                )

    def _construir_area_contenido(self):
        self._area = ctk.CTkFrame(self, fg_color="transparent")
        self._area.pack(side="left", fill="both", expand=True, padx=18, pady=16)

    def _ocultar_vista_actual(self):
        if self._vista_actual is not None:
            try:
                self._vista_actual.pack_forget()
            except Exception:
                pass
            self._vista_actual = None

    def _activar_vista_cacheada(self, clave: str, fabrica):
        """Muestra una vista reutilizando su instancia en caché en lugar de destruir y recrear widgets."""
        if self._clave_vista_actual == clave and self._vista_actual is not None:
            self._refrescar_instancia_vista(self._vista_actual)
            return

        self._ocultar_vista_actual()
        ya_existia = clave in self._vistas_cache
        if not ya_existia:
            self._vistas_cache[clave] = fabrica()

        vista = self._vistas_cache[clave]
        vista.pack(fill="both", expand=True)
        self._vista_actual = vista
        self._clave_vista_actual = clave

        if ya_existia:
            self._refrescar_instancia_vista(vista)

    @staticmethod
    def _refrescar_instancia_vista(vista):
        if hasattr(vista, "refrescar"):
            vista.refrescar()
        elif hasattr(vista, "_refrescar_vista"):
            vista._refrescar_vista()

    def _al_navegar(self, modulo, texto):
        if modulo == "resumen":
            self._mostrar_resumen()
        elif modulo == "cuentas":
            self._mostrar_cuentas()
        elif modulo == "gastos":
            self._mostrar_gastos()
        elif modulo == "ingresos":
            self._mostrar_ingresos()
        elif modulo == "inversiones":
            self._mostrar_inversiones()
        elif modulo == "movimientos":
            filtro = "GASTO" if texto == "Gastos" else "INGRESO"
            self._mostrar_movimientos(filtro_tipo=filtro, titulo=texto)
        elif modulo == "tema":
            self._mostrar_pendiente(
                "Modo Oscuro", "Cambio de tema visual en desarrollo."
            )
        else:
            mensaje = MODULOS_PENDIENTES.get(texto, "Módulo en desarrollo.")
            self._mostrar_pendiente(texto, mensaje)
        self._resaltar_boton(texto)

    def _mostrar_resumen(self):
        self._activar_vista_cacheada(
            "resumen", lambda: VistaResumen(self._area, self._gestor)
        )

    def _mostrar_cuentas(self):
        self._activar_vista_cacheada(
            "cuentas", lambda: VistaCuentasConDivisa(self._area, self._gestor)
        )

    def _mostrar_gastos(self):
        self._activar_vista_cacheada(
            "gastos", lambda: VistaGastos(self._area, self._gestor)
        )

    def _mostrar_ingresos(self):
        self._activar_vista_cacheada(
            "ingresos", lambda: VistaIngresos(self._area, self._gestor)
        )

    def _mostrar_inversiones(self):
        self._activar_vista_cacheada(
            "inversiones", lambda: VistaInversiones(self._area, self._gestor)
        )

    def _mostrar_movimientos(self, filtro_tipo, titulo):
        clave = f"movimientos_{filtro_tipo}"
        self._activar_vista_cacheada(
            clave,
            lambda: VistaMovimientosConDivisa(
                self._area, self._gestor, filtro_tipo=filtro_tipo, titulo=titulo
            ),
        )

    def _mostrar_pendiente(self, titulo, mensaje):
        clave = f"pendiente_{titulo}"

        def _crear():
            marco = ctk.CTkFrame(
                self._area, fg_color=COLORES["fondo_tarjeta"], corner_radius=14
            )
            ctk.CTkLabel(
                marco,
                text=titulo,
                font=(FUENTE, 24, "bold"),
                text_color=COLORES["texto"],
            ).pack(pady=(80, 10))
            ctk.CTkLabel(
                marco,
                text=mensaje,
                font=(FUENTE, 14),
                text_color=COLORES["texto_secundario"],
            ).pack()
            return marco

        self._activar_vista_cacheada(clave, _crear)