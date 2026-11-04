"""Campo de dinero con separadores de miles automáticos.

Al escribir, los dígitos se separan al estilo colombiano: miles con punto
(1.000, 10.000, 100.000) y millones con comilla arriba (1'000.000). La
coma es el separador decimal (máximo dos cifras). El valor que se envía
a las validaciones no lleva separadores de miles (regla de la tesis:
sin ambigüedad entre 1.500 y mil quinientos).
"""

import re

import customtkinter as ctk


def formatear_dinero(texto_crudo):
    """Convierte '1500000,5' en "1'000.000,5" (estilo colombiano)."""
    parte_entera, coma, decimales = texto_crudo.partition(",")
    if not parte_entera:
        parte_entera = "0"
    return _separar_miles(parte_entera) + coma + decimales


def _separar_miles(entero):
    """Separa los miles con punto y los millones con comilla arriba."""
    if len(entero) <= 3:
        return entero
    trozos = []
    resto = entero
    while resto:
        trozos.append(resto[-3:])
        resto = resto[:-3]
    trozos.reverse()

    # El separador antes de un trozo deja a su derecha 3*(cantidad-j)
    # dígitos: cuando esa cantidad es múltiplo de 6 (millones), se usa
    # comilla arriba; cuando es 3 (miles), punto.
    cantidad = len(trozos)
    partes = [trozos[0]]
    for j in range(1, cantidad):
        separador = "'" if (cantidad - j) % 2 == 0 else "."
        partes.append(separador + trozos[j])
    return "".join(partes)


def limpiar_dinero(texto):
    """Quita separadores de miles: "1'000.000,5" → '1000000,5'."""
    texto = texto.replace(".", "").replace("'", "").replace("’", "")
    return texto.strip()


class CampoMoneda(ctk.CTkEntry):
    """Campo de entrada que formatea los miles mientras se escribe."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.bind("<KeyRelease>", self._al_teclear, add="+")

    def _al_teclear(self, _evento=None):
        """Reformatea el contenido tras cada tecla.

        Los separadores que el usuario borra se recalculan: borrar el
        último dígito de 1.000 deja 100 (no 1.0).
        """
        crudo = limpiar_dinero(self.get())
        # Una sola coma decimal; decimales: máximo dos cifras.
        if crudo.count(",") > 1:
            primera = crudo.index(",")
            crudo = (crudo[:primera + 1]
                     + crudo[primera + 1:].replace(",", ""))
        entero, coma, decimales = crudo.partition(",")
        entero = re.sub(r"\D", "", entero)
        decimales = re.sub(r"\D", "", decimales)[:2]
        crudo = entero + coma + decimales

        formateado = formatear_dinero(crudo)
        if formateado != self.get():
            self.delete(0, "end")
            self.insert(0, formateado)
            self.icursor("end")

    def obtener_valor(self):
        """Valor sin separadores de miles, listo para validar ('1500000,5')."""
        return limpiar_dinero(self.get())
