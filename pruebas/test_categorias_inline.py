"""Pruebas unitarias para la eliminación de 'Categorías' del sidebar y CRUD inline de categorías."""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class _CategoriaFake:
    id: Optional[int]
    nombre: str
    tipo: str = "GASTO"
    simbolo: str = "mercado"
    color: str = "#FBB718"
    es_predeterminada: bool = False
    gasto_programado: bool = False
    frecuencia: Optional[str] = None


class _RepositorioCategoriasFake:
    """Repositorio en memoria que emula la tabla categoria y la FK movimiento_financiero."""

    def __init__(self) -> None:
        self.categorias: List[_CategoriaFake] = [
            _CategoriaFake(1, "Alimentación", "GASTO", "mercado", "#FBB718", True),
            _CategoriaFake(2, "Café", "GASTO", "cafe", "#89BF50", False),
            _CategoriaFake(3, "Otros gastos", "GASTO", "otros", "#8A8F98", True),
            _CategoriaFake(4, "Salario", "INGRESO", "salario", "#7DC98F", True),
        ]
        self.movimientos: List[int] = [2, 2, 1]

    def obtener_categorias_detalladas(self, tipo: Optional[str] = None) -> List[_CategoriaFake]:
        if tipo is None:
            return list(self.categorias)
        return [c for c in self.categorias if c.tipo == tipo.upper()]

    def actualizar_categoria(self, categoria: _CategoriaFake) -> _CategoriaFake:
        for c in self.categorias:
            if c.nombre.lower() == categoria.nombre.lower() and c.id != categoria.id:
                raise ValueError(f"Ya existe otra categoría llamada '{categoria.nombre}'.")
        for idx, c in enumerate(self.categorias):
            if c.id == categoria.id:
                self.categorias[idx] = categoria
                return categoria
        raise LookupError(f"No se encontró la categoría con ID {categoria.id}.")

    def contar_movimientos_por_categoria(self, categoria_id: int) -> int:
        return sum(1 for cid in self.movimientos if cid == categoria_id)

    def eliminar_categoria(
        self,
        categoria_id: int,
        categoria_destino_id: Optional[int] = None,
    ) -> int:
        vinculados = self.contar_movimientos_por_categoria(categoria_id)
        if vinculados > 0:
            if categoria_destino_id is None or categoria_destino_id == categoria_id:
                raise ValueError("Se requiere una categoría destino válida para reasignar movimientos.")
            self.movimientos = [
                categoria_destino_id if cid == categoria_id else cid for cid in self.movimientos
            ]
        antes = len(self.categorias)
        self.categorias = [c for c in self.categorias if c.id != categoria_id]
        if len(self.categorias) == antes:
            raise LookupError(f"No se encontró la categoría con ID {categoria_id}.")
        return vinculados


class TestCategoriasInline(unittest.TestCase):
    def test_sidebar_no_incluye_categorias_si_repo_local_disponible(self) -> None:
        ventana = Path("app/gui/ventana_principal.py")
        if not ventana.exists():
            self.skipTest("Ejecutado fuera del repositorio completo de NexSaldo.")
        contenido = ventana.read_text(encoding="utf-8")
        self.assertNotIn('("Categorías", "pendiente")', contenido)
        self.assertNotIn('"Categorías":', contenido)
        self.assertIn('("Configuración", "pendiente")', contenido)

    def test_actualizar_categoria_renombra_y_evita_duplicados(self) -> None:
        repo = _RepositorioCategoriasFake()
        actualizada = repo.actualizar_categoria(
            _CategoriaFake(2, "Cafetería", "GASTO", "cafe", "#408FD1", False)
        )
        self.assertEqual(actualizada.nombre, "Cafetería")
        self.assertTrue(any(c.id == 2 and c.color == "#408FD1" for c in repo.categorias))

        with self.assertRaisesRegex(ValueError, "Ya existe otra categoría"):
            repo.actualizar_categoria(
                _CategoriaFake(2, "Alimentación", "GASTO", "cafe", "#408FD1", False)
            )

    def test_eliminar_categoria_con_movimientos_exige_y_reasigna_destino(self) -> None:
        repo = _RepositorioCategoriasFake()
        self.assertEqual(repo.contar_movimientos_por_categoria(2), 2)

        with self.assertRaisesRegex(ValueError, "categoría destino"):
            repo.eliminar_categoria(2)

        reasignados = repo.eliminar_categoria(2, categoria_destino_id=3)
        self.assertEqual(reasignados, 2)
        self.assertEqual(repo.contar_movimientos_por_categoria(2), 0)
        self.assertEqual(repo.contar_movimientos_por_categoria(3), 2)
        self.assertTrue(all(c.id != 2 for c in repo.categorias))

    def test_eliminar_categoria_sin_movimientos_funciona_directo(self) -> None:
        repo = _RepositorioCategoriasFake()
        reasignados = repo.eliminar_categoria(3)
        self.assertEqual(reasignados, 0)
        self.assertTrue(all(c.id != 3 for c in repo.categorias))


if __name__ == "__main__":
    unittest.main()
