"""Calculadora para el campo de valor de una transferencia.

Panel pequeño dentro del diálogo de transferencia: el usuario puede
operar sumas, restas, multiplicaciones y divisiones con botones y el
resultado se escribe en el campo de cantidad. Usa Decimal, nunca float.
"""

from decimal import Decimal, InvalidOperation

import customtkinter as ctk

from app.gui.estilos import COLORES, FUENTE

# Operaciones permitidas (nada más: no hay eval de expresiones arbitrarias).
_OPERACIONES = {
    "+": lambda a, b: a + b,
    "-": lambda a, b: a - b,
    "×": lambda a, b: a * b,
    "÷": lambda a, b: a / b if b != 0 else None,
}


class Calculadora(ctk.CTkFrame):
    """Calculadora básica que escribe su resultado en un campo CTkEntry."""

    def __init__(self, master, campo_destino, **kwargs):
        super().__init__(master, fg_color=COLORES["fondo_tarjeta"],
                         corner_radius=12, **kwargs)
        self._campo = campo_destino
        self._acumulado = None      # Decimal parcial o None.
        self._operacion = None      # "+", "-", "×", "÷" o None.
        self._en_binaria = False    # True si el usuario ya digitó un valor.
        self._pantalla = ctk.CTkEntry(self, width=200, justify="right",
                                       state="readonly", corner_radius=8)
        self._pantalla.grid(row=0, column=0, columnspan=4, padx=10, pady=(10, 6),
                            sticky="we")
        self._mostrar("0")

        teclas = [
            ("7", "8", "9", "÷"),
            ("4", "5", "6", "×"),
            ("1", "2", "3", "-"),
            ("0", ".", "=", "+"),
        ]
        for fila, teclas_fila in enumerate(teclas, start=1):
            for columna, tecla in enumerate(teclas_fila):
                es_igual = tecla == "="
                color = COLORES["acento"] if es_igual else COLORES["boton_lateral"]
                texto_color = "#10241C" if es_igual else COLORES["texto"]
                ctk.CTkButton(
                    self, text=tecla, width=44, height=34, corner_radius=8,
                    fg_color=color, hover_color=COLORES["hover_lateral"],
                    text_color=texto_color, font=(FUENTE, 12, "bold"),
                    command=lambda t=tecla: self._al_pulsar(t),
                ).grid(row=fila, column=columna, padx=2, pady=2)

        fila_extra = [("C", 0), ("⌫", 1)]
        for texto, columna in fila_extra:
            ctk.CTkButton(
                self, text=texto, width=44, height=30, corner_radius=8,
                fg_color=COLORES["error"], hover_color="#D96A6A",
                text_color="#10241C", font=(FUENTE, 11, "bold"),
                command=lambda t=texto: self._al_pulsar(t),
            ).grid(row=5, column=columna, padx=2, pady=2)

        for indice in range(4):
            self.columnconfigure(indice, weight=1)

    # ------------------------------------------------------------------
    # Lógica de la calculadora (Decimal, sin eval)
    # ------------------------------------------------------------------

    def _al_pulsar(self, tecla):
        if tecla.isdigit() or tecla == ".":
            self._agregar_digito(tecla)
        elif tecla in _OPERACIONES:
            self._definir_operacion(tecla)
        elif tecla == "=":
            self._calcular()
        elif tecla == "C":
            self._reiniciar()
        elif tecla == "⌫":
            self._borrar_digito()

    def _texto_actual(self):
        return self._pantalla.get().replace(",", ".")

    def _mostrar(self, texto):
        self._pantalla.configure(state="normal")
        self._pantalla.delete(0, "end")
        self._pantalla.insert(0, texto)
        self._pantalla.configure(state="readonly")

    def _agregar_digito(self, digito):
        actual = self._texto_actual()
        if digito == "." and "." in actual:
            return
        if not actual or actual == "0":
            nuevo = "0." if digito == "." else digito
        else:
            nuevo = actual + digito
        self._mostrar(nuevo)

    def _borrar_digito(self):
        actual = self._texto_actual()
        self._mostrar("0" if len(actual) <= 1 else actual[:-1])

    def _definir_operacion(self, tecla):
        try:
            self._acumulado = Decimal(self._texto_actual())
        except InvalidOperation:
            self._mostrar("0")
            return
        self._operacion = tecla
        self._en_binaria = True
        self._mostrar("0")

    def _calcular(self):
        if self._operacion is None or self._acumulado is None:
            return
        try:
            segundo = Decimal(self._texto_actual())
        except InvalidOperation:
            return
        resultado = _OPERACIONES[self._operacion](self._acumulado, segundo)
        if resultado is None:
            self._mostrar("Error: división por cero")
            return
        # Se descarta la parte decimal sobrante (solo dos decimales).
        resultado = resultado.quantize(Decimal("0.01"))
        self._acumulado = resultado
        self._operacion = None
        self._en_binaria = True
        self._mostrar(str(resultado))
        # El resultado se escribe en el campo de cantidad de la transferencia.
        # Con coma decimal (el campo formatea los miles por su cuenta).
        self._campo.delete(0, "end")
        self._campo.insert(0, str(resultado).replace(".", ","))

    def _reiniciar(self):
        self._acumulado = None
        self._operacion = None
        self._en_binaria = False
        self._mostrar("0")
