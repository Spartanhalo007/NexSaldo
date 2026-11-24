"""Script idempotente para aplicar la eliminación de 'Categorías' del sidebar y el menú contextual inline en Ingresos y Gastos."""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

RAIZ_POR_DEFECTO = Path.cwd()


def _respaldar(ruta: Path) -> None:
    respaldo = ruta.with_suffix(ruta.suffix + ".bak")
    if not respaldo.exists():
        shutil.copy2(ruta, respaldo)


def _parchear_ventana_principal(raiz: Path) -> str:
    ruta = raiz / "app" / "gui" / "ventana_principal.py"
    texto = ruta.read_text(encoding="utf-8")
    original = texto

    texto = re.sub(
        r'^[ \t]*\("Categor[íi]as",[ \t]*"pendiente"\),?[ \t]*\r?\n',
        "",
        texto,
        flags=re.MULTILINE,
    )
    texto = re.sub(
        r'^[ \t]*"Categor[íi]as"[ \t]*:[ \t]*"[^"]*",?[ \t]*\r?\n',
        "",
        texto,
        flags=re.MULTILINE,
    )

    if texto == original:
        return "sin cambios (ya aplicado)"
    _respaldar(ruta)
    ruta.write_text(texto, encoding="utf-8")
    return "actualizado"


METODOS_REPO_CATEGORIAS = '''
    def actualizar_categoria(self, categoria: Categoria) -> Categoria:
        """Actualiza nombre, tipo, símbolo, color y programación de una categoría existente por ID."""
        if categoria.id is None:
            raise ValueError("Se requiere el ID de la categoría para actualizarla.")
        with self._lock_bd:
            conexion = self.conectar()
            with conexion.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM categoria WHERE LOWER(nombre) = LOWER(%s) AND id <> %s",
                    (categoria.nombre, categoria.id),
                )
                if cursor.fetchone() is not None:
                    raise ValueError(f"Ya existe otra categoría llamada '{categoria.nombre}'.")
                cursor.execute(
                    """
                    UPDATE categoria
                    SET nombre = %s,
                        tipo = %s,
                        simbolo = %s,
                        color = %s,
                        gasto_programado = %s,
                        frecuencia = %s
                    WHERE id = %s
                    RETURNING id
                    """,
                    (
                        categoria.nombre,
                        categoria.tipo,
                        categoria.simbolo,
                        categoria.color,
                        categoria.gasto_programado,
                        categoria.frecuencia,
                        categoria.id,
                    ),
                )
                fila = cursor.fetchone()
                if fila is None:
                    raise LookupError(f"No se encontró la categoría con ID {categoria.id}.")
            conexion.commit()
        return categoria

    def contar_movimientos_por_categoria(self, categoria_id: int) -> int:
        """Retorna cuántos movimientos financieros están asociados a la categoría indicada."""
        with self._lock_bd:
            conexion = self.conectar()
            with conexion.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM movimiento_financiero WHERE categoria_id = %s",
                    (categoria_id,),
                )
                fila = cursor.fetchone()
                return int(fila[0]) if fila else 0

    def eliminar_categoria(
        self,
        categoria_id: int,
        categoria_destino_id: Optional[int] = None,
    ) -> int:
        """Elimina una categoría de forma segura, reasignando sus movimientos en la misma transacción si existen."""
        with self._lock_bd:
            conexion = self.conectar()
            with conexion.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM movimiento_financiero WHERE categoria_id = %s",
                    (categoria_id,),
                )
                vinculados = int(cursor.fetchone()[0])
                if vinculados > 0:
                    if categoria_destino_id is None or categoria_destino_id == categoria_id:
                        raise ValueError(
                            "La categoría tiene movimientos asociados; indica una categoría destino válida para reasignarlos."
                        )
                    cursor.execute(
                        "UPDATE movimiento_financiero SET categoria_id = %s WHERE categoria_id = %s",
                        (categoria_destino_id, categoria_id),
                    )
                cursor.execute("DELETE FROM categoria WHERE id = %s RETURNING id", (categoria_id,))
                if cursor.fetchone() is None:
                    raise LookupError(f"No se encontró la categoría con ID {categoria_id}.")
            conexion.commit()
        return vinculados
'''


def _parchear_repositorio(raiz: Path) -> str:
    ruta = raiz / "app" / "repositorio" / "repositorio_local.py"
    texto = ruta.read_text(encoding="utf-8")
    if "def actualizar_categoria(" in texto and "def eliminar_categoria(" in texto:
        return "sin cambios (ya aplicado)"

    marcador = "return categoria.con_id(nuevo_id)"
    pos = texto.find(marcador)
    if pos == -1:
        raise RuntimeError(
            "No se encontró el punto de inserción 'return categoria.con_id(nuevo_id)' en repositorio_local.py"
        )
    fin_linea = texto.find("\n", pos)
    if fin_linea == -1:
        fin_linea = len(texto)
    else:
        fin_linea += 1
    nuevo_texto = texto[:fin_linea] + METODOS_REPO_CATEGORIAS + texto[fin_linea:]
    _respaldar(ruta)
    ruta.write_text(nuevo_texto, encoding="utf-8")
    return "actualizado"


METODOS_GESTOR_CATEGORIAS = '''
    def editar_categoria(
        self,
        categoria_id: int,
        nombre: str,
        tipo: str = "GASTO",
        simbolo: str = "mercado",
        color: str = "#FBB718",
        gasto_programado: bool = False,
        frecuencia: Optional[str] = None,
    ) -> Categoria:
        """Actualiza una categoría existente por ID e invalida las cachés de categorías."""
        if not isinstance(nombre, str) or not nombre.strip():
            raise ValueError("El nombre de la categoría no puede estar vacío.")
        nombre_limpio = nombre.strip()
        if len(nombre_limpio) > 50:
            raise ValueError("El nombre de la categoría no puede superar 50 caracteres.")

        tipo_limpio = self._validar_tipo(tipo)
        simbolo_limpio = simbolo.strip()
        if simbolo_limpio not in TODOS_LOS_SIMBOLOS_CATEGORIA:
            raise ValueError(f"Símbolo de categoría no válido: {simbolo_limpio}")
        color_limpio = self._validar_color(color)

        frecuencia_limpia: Optional[str] = None
        if gasto_programado:
            frec = (frecuencia or "MENSUAL").strip().upper()
            if frec not in FRECUENCIAS_VALIDAS:
                raise ValueError(f"Frecuencia no válida: {frec}")
            frecuencia_limpia = frec

        actualizada = Categoria(
            id=categoria_id,
            nombre=nombre_limpio,
            tipo=tipo_limpio,
            simbolo=simbolo_limpio,
            color=color_limpio,
            es_predeterminada=False,
            gasto_programado=bool(gasto_programado),
            frecuencia=frecuencia_limpia,
        )

        if hasattr(self._repositorio, "actualizar_categoria"):
            resultado = self._repositorio.actualizar_categoria(actualizada)
        else:
            clave_anterior = next(
                (k for k, v in self._categorias_memoria_extra.items() if v.id == categoria_id),
                None,
            )
            if clave_anterior is not None:
                self._categorias_memoria_extra.pop(clave_anterior, None)
            self._categorias_memoria_extra[nombre_limpio] = actualizada
            resultado = actualizada

        self._cache_categorias_detalladas.clear()
        self._cache_nombres_categorias = None
        try:
            if hasattr(self._repositorio, "registrar_color_reciente"):
                self._repositorio.registrar_color_reciente(color_limpio)
        except Exception:
            pass
        return resultado

    def contar_movimientos_categoria(self, categoria_id: int) -> int:
        """Retorna el número de movimientos vinculados a una categoría."""
        if hasattr(self._repositorio, "contar_movimientos_por_categoria"):
            return self._repositorio.contar_movimientos_por_categoria(categoria_id)
        return 0

    def eliminar_categoria(
        self,
        categoria_id: int,
        categoria_destino_id: Optional[int] = None,
    ) -> int:
        """Elimina una categoría (reasignando movimientos si corresponde) e invalida cachés."""
        todas = self.obtener_categorias_detalladas(tipo=None)
        objetivo = next((c for c in todas if c.id == categoria_id), None)
        if objetivo is not None:
            mismo_tipo = [c for c in todas if c.tipo == objetivo.tipo]
            if len(mismo_tipo) <= 1:
                raise ValueError(
                    f"No se puede eliminar la última categoría de {objetivo.tipo.lower()}."
                )

        if hasattr(self._repositorio, "eliminar_categoria"):
            reasignados = self._repositorio.eliminar_categoria(
                categoria_id,
                categoria_destino_id=categoria_destino_id,
            )
        else:
            clave = next(
                (k for k, v in self._categorias_memoria_extra.items() if v.id == categoria_id),
                None,
            )
            if clave is not None:
                self._categorias_memoria_extra.pop(clave, None)
            reasignados = 0

        self._cache_categorias_detalladas.clear()
        self._cache_nombres_categorias = None
        return reasignados
'''


def _parchear_gestor(raiz: Path) -> str:
    """Inserta los métodos de categorías en O(N) justo al final de crear_categoria sin regex costosos."""
    ruta = raiz / "app" / "gestor" / "gestor_financiero.py"
    texto = ruta.read_text(encoding="utf-8")
    if "def editar_categoria(" in texto and "def eliminar_categoria(" in texto:
        return "sin cambios (ya aplicado)"

    lineas = texto.splitlines(keepends=True)
    idx_inicio = next(
        (i for i, linea in enumerate(lineas) if linea.startswith("    def crear_categoria(")),
        None,
    )
    if idx_inicio is None:
        raise RuntimeError("No se encontró '    def crear_categoria(' en gestor_financiero.py")

    # Buscar el final del método crear_categoria: la siguiente definición al nivel de clase (4 espacios o 0 espacios)
    idx_insercion = len(lineas)
    for i in range(idx_inicio + 1, len(lineas)):
        linea = lineas[i]
        if not linea.strip():
            continue
        if (
            linea.startswith("    def ")
            or linea.startswith("    @")
            or linea.startswith("    # ")
            or (not linea[0].isspace())
        ):
            idx_insercion = i
            break

    nuevo_texto = "".join(lineas[:idx_insercion]) + METODOS_GESTOR_CATEGORIAS + "\n" + "".join(lineas[idx_insercion:])
    _respaldar(ruta)
    ruta.write_text(nuevo_texto, encoding="utf-8")
    return "actualizado"


def _reemplazar_llamada_crear_categoria(texto: str) -> str:
    """Reemplaza la llamada `nueva = self._gestor.crear_categoria(...)` balanceando paréntesis en O(N)."""
    marcador = "self._gestor.crear_categoria("
    pos_llamada = texto.find(marcador)
    if pos_llamada == -1:
        return texto

    inicio_linea = texto.rfind("\n", 0, pos_llamada) + 1
    linea_inicio = texto[inicio_linea:pos_llamada]
    indent = linea_inicio[: len(linea_inicio) - len(linea_inicio.lstrip(" \t"))]

    # Balancear paréntesis desde el '(' de crear_categoria(
    pos_abre = pos_llamada + len(marcador) - 1
    profundidad = 0
    pos_cierra = -1
    for i in range(pos_abre, len(texto)):
        ch = texto[i]
        if ch == "(":
            profundidad += 1
        elif ch == ")":
            profundidad -= 1
            if profundidad == 0:
                pos_cierra = i
                break
    if pos_cierra == -1:
        return texto

    bloque_orig = texto[inicio_linea : pos_cierra + 1]
    bloque_indentado = "\n".join(
        ("    " + ln if ln.strip() else ln) for ln in bloque_orig.splitlines()
    )
    reemplazo = (
        f"{indent}if self._categoria_editar is not None and self._categoria_editar.id is not None:\n"
        f"{indent}    nueva = self._gestor.editar_categoria(\n"
        f"{indent}        categoria_id=self._categoria_editar.id,\n"
        f"{indent}        nombre=nombre,\n"
        f"{indent}        tipo=tipo,\n"
        f"{indent}        simbolo=self._simbolo_elegido,\n"
        f"{indent}        color=self._color_elegido,\n"
        f"{indent}        gasto_programado=programado,\n"
        f"{indent}        frecuencia=frecuencia_clave,\n"
        f"{indent}    )\n"
        f"{indent}else:\n"
        f"{bloque_indentado}"
    )
    return texto[:inicio_linea] + reemplazo + texto[pos_cierra + 1 :]


def _parchear_dialogo_categoria(raiz: Path) -> str:
    ruta = raiz / "app" / "gui" / "dialogo_categoria.py"
    texto = ruta.read_text(encoding="utf-8")
    if "categoria_editar" in texto:
        return "sin cambios (ya aplicado)"

    original = texto
    texto = re.sub(
        r'(tipo_inicial:\s*str\s*=\s*"GASTO",\s*\*\*kwargs)',
        r'tipo_inicial: str = "GASTO",\n        categoria_editar: Optional[Categoria] = None,\n        **kwargs',
        texto,
        count=1,
    )
    texto = re.sub(
        r'(self\._al_crear\s*=\s*al_crear\s*\r?\n)',
        r'\1        self._categoria_editar = categoria_editar\n',
        texto,
        count=1,
    )
    texto = re.sub(
        r'self\.title\("Crear categor[íi]a"\)',
        'self.title("Editar categoría" if self._categoria_editar else "Crear categoría")',
        texto,
        count=1,
    )
    texto = re.sub(
        r'self\._simbolo_elegido\s*=\s*"factura"',
        'self._simbolo_elegido = self._categoria_editar.simbolo if self._categoria_editar else "factura"',
        texto,
        count=1,
    )
    texto = re.sub(
        r'self\._color_elegido\s*=\s*COLORES_PREDETERMINADOS\[0\]',
        'self._color_elegido = self._categoria_editar.color if self._categoria_editar else COLORES_PREDETERMINADOS[0]',
        texto,
        count=1,
    )
    texto = re.sub(
        r'(self\._construir_interfaz\(\)\s*\r?\n)',
        r'\1        if self._categoria_editar is not None:\n            self._precargar_edicion()\n',
        texto,
        count=1,
    )
    texto = re.sub(
        r'text="Crear"',
        'text="Guardar cambios" if self._categoria_editar else "Crear"',
        texto,
        count=1,
    )
    texto = _reemplazar_llamada_crear_categoria(texto)

    metodo_precarga = '''
    def _precargar_edicion(self) -> None:
        """Precarga los campos del modal cuando se edita una categoría existente."""
        cat = self._categoria_editar
        if cat is None:
            return
        if hasattr(self, "_campo_nombre"):
            self._campo_nombre.delete(0, "end")
            self._campo_nombre.insert(0, cat.nombre)
        if hasattr(self, "_var_tipo"):
            self._var_tipo.set(cat.tipo)
        if hasattr(self, "_var_programado"):
            self._var_programado.set(bool(cat.gasto_programado))
        if hasattr(self, "_combo_frecuencia") and cat.frecuencia:
            etiqueta = ETIQUETAS_FRECUENCIA.get(cat.frecuencia, "Mensual")
            self._combo_frecuencia.set(etiqueta)
        if hasattr(self, "_actualizar_visibilidad_frecuencia"):
            self._actualizar_visibilidad_frecuencia()
        if hasattr(self, "_actualizar_preview"):
            self._actualizar_preview()
'''
    texto = texto.rstrip() + "\n" + metodo_precarga

    if texto == original:
        raise RuntimeError("No se pudieron aplicar los parches esperados en dialogo_categoria.py")
    _respaldar(ruta)
    ruta.write_text(texto, encoding="utf-8")
    return "actualizado"


MIXIN_MENU_CONTEXTUAL = '''
    def _vincular_menu_contextual_categoria(self, widget, categoria) -> None:
        """Enlaza clic derecho en el chip de categoría para mostrar Editar y Eliminar."""
        from app.gui.selector_categorias import _enlazar_clic_derecho

        _enlazar_clic_derecho(widget, lambda e, c=categoria: self._abrir_menu_categoria(e, c))

    def _abrir_menu_categoria(self, evento, categoria) -> None:
        """Despliega el menú contextual con opciones Editar y Eliminar sobre una categoría."""
        import tkinter as tk
        from app.gui.estilos import COLORES, FUENTE

        menu = tk.Menu(
            self,
            tearoff=0,
            bg=COLORES["fondo_lateral"],
            fg=COLORES["texto"],
            activebackground=COLORES["hover_lateral"],
            activeforeground=COLORES["acento"],
            bd=1,
            relief="flat",
            font=(FUENTE, 10),
        )
        menu.add_command(
            label=f"✎  Editar «{categoria.nombre}»",
            command=lambda c=categoria: self._abrir_editar_categoria(c),
        )
        menu.add_separator()
        menu.add_command(
            label=f"✕  Eliminar «{categoria.nombre}»",
            foreground=COLORES["error"],
            activeforeground=COLORES["error"],
            command=lambda c=categoria: self._solicitar_eliminar_categoria(c),
        )
        try:
            menu.tk_popup(evento.x_root, evento.y_root)
        finally:
            menu.grab_release()

    def _abrir_editar_categoria(self, categoria) -> None:
        """Abre DialogoCategoria en modo edición para la categoría seleccionada."""
        nombre_anterior = categoria.nombre

        def _al_editar(actualizada) -> None:
            if self._categoria_elegida == nombre_anterior:
                self._categoria_elegida = actualizada.nombre
            self._renderizar_categorias()
            cb = getattr(self, "_al_modificar_categorias", None)
            if callable(cb):
                cb()

        DialogoCategoria(
            self,
            gestor=self._gestor,
            al_crear=_al_editar,
            tipo_inicial=categoria.tipo,
            categoria_editar=categoria,
        )

    def _solicitar_eliminar_categoria(self, categoria) -> None:
        """Abre confirmación segura (con reasignación si hay movimientos) y elimina la categoría."""
        from app.gui.selector_categorias import DialogoEliminarCategoria

        if categoria.id is None:
            return
        categorias = self._gestor.obtener_categorias_detalladas(categoria.tipo)
        alternativas = [c for c in categorias if c.id is not None and c.id != categoria.id]
        if not alternativas:
            if hasattr(self, "_mostrar_error"):
                self._mostrar_error(f"Debe existir al menos una categoría de {categoria.tipo.lower()}.")
            return

        cantidad = self._gestor.contar_movimientos_categoria(categoria.id)

        def _confirmar(destino_id) -> None:
            try:
                self._gestor.eliminar_categoria(categoria.id, categoria_destino_id=destino_id)
            except Exception as exc:
                if hasattr(self, "_mostrar_error"):
                    self._mostrar_error(str(exc))
                return
            if self._categoria_elegida == categoria.nombre:
                destino = next((c for c in alternativas if c.id == destino_id), alternativas[0])
                self._categoria_elegida = destino.nombre
            self._renderizar_categorias()
            cb = getattr(self, "_al_modificar_categorias", None)
            if callable(cb):
                cb()

        DialogoEliminarCategoria(
            self,
            categoria=categoria,
            cantidad_movimientos=cantidad,
            alternativas=alternativas,
            al_confirmar=_confirmar,
        )
'''


def _parchear_dialogo_movimiento(raiz: Path, nombre_archivo: str) -> str:
    ruta = raiz / "app" / "gui" / nombre_archivo
    texto = ruta.read_text(encoding="utf-8")
    if "def _abrir_menu_categoria(" in texto:
        return "sin cambios (ya aplicado)"

    original = texto
    texto = re.sub(
        r'(al_guardar:\s*Callable[^\n]*,)',
        r'\1\n        al_modificar_categorias: Optional[Callable[[], None]] = None,',
        texto,
        count=1,
    )
    texto = re.sub(
        r'(self\._al_guardar\s*=\s*al_guardar\s*\r?\n)',
        r'\1        self._al_modificar_categorias = al_modificar_categorias\n',
        texto,
        count=1,
    )
    texto = re.sub(
        r'^([ \t]+)(self\._widgets_categorias\[cat\.nombre\]\s*=\s*\(btn,\s*lbl_cat\)\s*\r?\n)',
        (
            r'\1\2'
            r'\1self._vincular_menu_contextual_categoria(btn, cat)\n'
            r'\1self._vincular_menu_contextual_categoria(lbl_cat, cat)\n'
        ),
        texto,
        count=1,
        flags=re.MULTILINE,
    )
    texto = texto.rstrip() + "\n" + MIXIN_MENU_CONTEXTUAL

    if texto == original:
        raise RuntimeError(f"No se pudieron aplicar los parches en {nombre_archivo}")
    _respaldar(ruta)
    ruta.write_text(texto, encoding="utf-8")
    return "actualizado"


def _parchear_vista_movimiento(raiz: Path, nombre_archivo: str, clase_dialogo: str) -> str:
    ruta = raiz / "app" / "gui" / nombre_archivo
    texto = ruta.read_text(encoding="utf-8")
    if "al_modificar_categorias=" in texto:
        return "sin cambios (ya aplicado)"

    patron = re.compile(
        rf"({clase_dialogo}\(\s*self,\s*gestor=self\._gestor,\s*al_guardar=self\._al_guardar_nuevo_[a-z]+,?)",
        flags=re.MULTILINE,
    )
    if not patron.search(texto):
        return "omitido (patrón no encontrado; refresco manual tras guardar)"
    nuevo_texto = patron.sub(
        r"\1\n            al_modificar_categorias=self._refrescar_vista,",
        texto,
        count=1,
    )
    _respaldar(ruta)
    ruta.write_text(nuevo_texto, encoding="utf-8")
    return "actualizado"


def aplicar_todo(raiz: Path) -> None:
    origen_selector = Path(__file__).resolve().parent / "app" / "gui" / "selector_categorias.py"
    destino_selector = raiz / "app" / "gui" / "selector_categorias.py"
    if origen_selector.exists() and origen_selector.resolve() != destino_selector.resolve():
        destino_selector.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen_selector, destino_selector)
        print(f"[OK] Copiado {destino_selector.relative_to(raiz)}")

    pasos = [
        ("app/gui/ventana_principal.py", lambda: _parchear_ventana_principal(raiz)),
        ("app/repositorio/repositorio_local.py", lambda: _parchear_repositorio(raiz)),
        ("app/gestor/gestor_financiero.py", lambda: _parchear_gestor(raiz)),
        ("app/gui/dialogo_categoria.py", lambda: _parchear_dialogo_categoria(raiz)),
        ("app/gui/dialogo_gasto.py", lambda: _parchear_dialogo_movimiento(raiz, "dialogo_gasto.py")),
        ("app/gui/dialogo_ingreso.py", lambda: _parchear_dialogo_movimiento(raiz, "dialogo_ingreso.py")),
        ("app/gui/vista_gastos.py", lambda: _parchear_vista_movimiento(raiz, "vista_gastos.py", "DialogoGasto")),
        ("app/gui/vista_ingresos.py", lambda: _parchear_vista_movimiento(raiz, "vista_ingresos.py", "DialogoIngreso")),
    ]
    for nombre, fn in pasos:
        estado = fn()
        print(f"[OK] {nombre}: {estado}")


if __name__ == "__main__":
    raiz_objetivo = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else RAIZ_POR_DEFECTO
    print(f"Aplicando actualización de categorías inline en: {raiz_objetivo}")
    aplicar_todo(raiz_objetivo)
    print("Listo. Ejecuta `pytest pruebas/test_categorias_inline.py` para validar.")
