"""Regresiones de paletas, preferencias y cambio de tema en la GUI real."""

import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

import pytest

from app.gui import estilos


@pytest.fixture(autouse=True)
def perfil_temporal(monkeypatch, tmp_path):
    ruta = tmp_path / "NexSaldo" / "tema.txt"
    monkeypatch.setattr(estilos, "_ruta_tema", lambda: ruta)
    yield ruta
    estilos.configurar_tema(estilos.TEMA_PREDETERMINADO)


def test_preferencia_local_y_fallback(perfil_temporal):
    assert estilos.cargar_tema() == "carbon"
    assert estilos.guardar_tema("fiordo")
    assert estilos.cargar_tema() == "fiordo"
    assert not estilos.guardar_tema("desconocido")
    assert estilos.cargar_tema() == "fiordo"
    perfil_temporal.write_text("desconocido", encoding="utf-8")
    assert estilos.cargar_tema() == "carbon"
    perfil_temporal.write_bytes(b"\xff")
    assert estilos.cargar_tema() == "carbon"


def test_clasico_conserva_los_colores_originales():
    estilos.configurar_tema("duna")
    colores = estilos.COLORES
    grafica = estilos.COLORES_GRAFICA
    estilos.configurar_tema("clasico")
    assert estilos.COLORES is colores
    assert estilos.COLORES_GRAFICA is grafica
    assert colores == {
        "fondo_lateral": "#0B3623", "fondo_contenido": "#278960",
        "fondo_tarjeta": "#166246", "boton_lateral": "#103725", "hover_lateral": "#0E2B1C",
        "acento": "#FBB718", "acento_hover": "#E5A512", "texto": "#FFFFFF",
        "texto_secundario": "#CFE8DA", "exito": "#7DC98F", "error": "#F28C8C",
        "campo_fondo": "#F4F7F5", "campo_texto": "#10241C", "borde_tabla": "#2E6B54",
    }
    assert grafica == ["#FBB718", "#408FD1", "#89BF50", "#F28C8C", "#BFD8CC", "#7DC98F"]
    assert estilos.COLORES_PREDETERMINADOS == [*grafica, "#FFFFFF", "#8A8F98"]


def _luminancia(color):
    rgb = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lineal = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
    return sum(peso * v for peso, v in zip((0.2126, 0.7152, 0.0722), lineal))


@pytest.mark.parametrize("tema", ["carbon", "fiordo", "mora", "duna"])
def test_contraste_de_los_temas_nuevos(tema):
    paleta = estilos.TEMAS[tema][2]
    pares = [
        (texto, fondo)
        for texto in ("texto", "texto_secundario", "acento", "exito", "error")
        for fondo in ("fondo_contenido", "fondo_tarjeta", "boton_lateral", "hover_lateral")
    ] + [
        ("campo_texto", "campo_fondo"), ("campo_texto", "acento"),
        ("campo_texto", "acento_hover"), ("texto", "acento_intenso"), ("texto", "intenso_hover"),
    ]
    for texto, fondo in pares:
        bajo, alto = sorted((_luminancia(paleta[texto]), _luminancia(paleta[fondo])))
        assert (alto + 0.05) / (bajo + 0.05) >= 4.5, (tema, texto, fondo)


def _comprobar_categorias_inline(vista, modulo, gestor, paleta):
    from app.gui.dialogo_categoria import DialogoCategoria
    from app.gui.selector_categorias import DialogoEliminarCategoria

    if modulo == "gastos":
        vista._abrir_dialogo_anadir_gasto()
        tipo = "GASTO"
    else:
        vista._abrir_dialogo_anadir_ingreso()
        tipo = "INGRESO"
    dialogo = next(w for w in vista.winfo_children() if isinstance(w, tk.Toplevel))
    try:
        categoria = gestor.obtener_categorias_detalladas(tipo)[0]
        assert categoria.nombre in dialogo._widgets_categorias
        dialogo._abrir_menu_categoria(SimpleNamespace(x_root=0, y_root=0), categoria)
        menu = next(w for w in dialogo.winfo_children() if isinstance(w, tk.Menu))
        assert str(menu.cget("activeforeground")) == paleta["acento"]
        for indice, clase in ((0, DialogoCategoria), (2, DialogoEliminarCategoria)):
            menu.invoke(indice)
            modal = next(w for w in dialogo.winfo_children() if isinstance(w, clase))
            assert modal.cget("fg_color") == paleta["fondo_lateral"]
            modal.destroy()
    finally:
        dialogo.destroy()


def test_selector_aplica_todos_los_temas_y_reabre_con_el_ultimo(monkeypatch):
    from app.gestor.gestor_financiero import GestorFinanciero
    from app.gui import ventana_principal
    from app.gui.selector_moneda import BarraFiltroMoneda
    from app.gui.vista_inversiones import VistaInversiones
    from app.modelo.categoria import Categoria
    from pruebas.test_gestor_financiero import RepositorioDeMemoria

    # Prueba la interfaz y sus widgets, sin depender de la red ni de PostgreSQL.
    monkeypatch.setattr(BarraFiltroMoneda, "_verificar_conexion_asincrona", lambda *a, **k: None)
    monkeypatch.setattr(VistaInversiones, "_cargar_curva_montana_asincrona", lambda *a, **k: None)
    gestor = GestorFinanciero(RepositorioDeMemoria([]))
    monkeypatch.setattr(gestor, "obtener_tasa_cambio", lambda *a, **k: None)
    categorias = [
        Categoria(1, "Alimentación"), Categoria(2, "Otros gastos"),
        Categoria(3, "Salario", "INGRESO"), Categoria(4, "Otros ingresos", "INGRESO"),
    ]
    monkeypatch.setattr(gestor, "obtener_categorias_detalladas",
                        lambda tipo=None: [c for c in categorias if tipo is None or c.tipo == tipo])
    monkeypatch.setattr(tk.Menu, "tk_popup", lambda *a: None)
    try:
        ventana = ventana_principal.VentanaPrincipal(gestor)
    except tk.TclError as error:
        if "display" not in str(error):
            raise
        pytest.skip("La interfaz Tk necesita una pantalla (o xvfb-run).")
    try:
        ventana.update_idletasks()
        assert ventana._tema == "carbon"
        assert "Categorías" not in ventana._botones
        enlace = ventana.bind_all("<F7>", lambda _evento: None)
        errores = []
        ventana.report_callback_exception = lambda *error: errores.append(error)
        for tema in estilos.TEMAS:
            reporte_anterior = ventana._vistas_cache.get("reportes")
            ventana._botones["Themes"].invoke()
            selector = ventana._vista_actual
            selector._opciones[tema].invoke()
            ventana.update_idletasks()
            paleta = estilos.TEMAS[tema][2]
            assert ventana._vista_actual._seleccion.get() == tema
            assert ventana.cget("fg_color") == paleta["fondo_contenido"]
            assert ventana._barra.cget("fg_color") == paleta["fondo_lateral"]
            assert ventana._botones["Themes"].cget("fg_color") == paleta["acento"]
            assert ttk.Style(ventana).lookup("Tablita.Treeview", "background") == paleta["fondo_tarjeta"]
            if selector is not ventana._vista_actual:
                assert set(ventana._vistas_cache) == {"tema"}
                assert "_keyboard_shift_press_all" not in ventana.bind_all("<KeyPress-Shift_L>")
                assert enlace in ventana.bind_all("<F7>")
                # Simula una actualización que se encoló desde un hilo al cambiar de tema.
                ventana.after(0, reporte_anterior._renderizar_reporte_actual)
                ventana.update()
                assert not errores
            for nombre, modulo in ventana_principal.NAVEGACION[:6]:
                ventana._botones[nombre].invoke()
                ventana.update_idletasks()
                assert ventana._clave_vista_actual == modulo
                assert ventana._botones[nombre].cget("fg_color") == paleta["acento"]
                if tema in {"clasico", "fiordo"} and modulo in {"gastos", "ingresos"}:
                    _comprobar_categorias_inline(ventana._vista_actual, modulo, gestor, paleta)
    finally:
        ventana.destroy()

    reabierta = ventana_principal.VentanaPrincipal(gestor)
    try:
        assert reabierta._tema == "duna"
        assert reabierta.cget("fg_color") == estilos.TEMAS["duna"][2]["fondo_contenido"]
    finally:
        reabierta.destroy()
