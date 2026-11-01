"""Acceso a PostgreSQL local (RepositorioLocal del modelo de la tesis).

Responsabilidades:
- Abrir y cerrar la conexión con PostgreSQL local.
- Aplicar el esquema inicial de la base de datos.
- Guardar, consultar y eliminar movimientos financieros.
- Ejecutar consultas parametrizadas.

No contiene reglas de negocio: la validación y coordinación viven en
GestorFinanciero. Toda consulta usa parámetros (%s), nunca concatenación.
"""

from pathlib import Path

import psycopg2

from app.modelo.movimiento_financiero import MovimientoFinanciero

RUTA_ESQUEMA = Path(__file__).resolve().parents[2] / "sql" / "esquema_inicial.sql"


class RepositorioLocal:
    """Maneja la conexión y las operaciones sobre la base de datos local."""

    def __init__(self, configuracion):
        self._config = configuracion
        self._conexion = None

    def conectar(self):
        """Abre la conexión si no existe o si la anterior fue cerrada."""
        if self._conexion is None or self._conexion.closed:
            self._conexion = psycopg2.connect(
                host=self._config.host,
                port=self._config.puerto,
                dbname=self._config.nombre,
                user=self._config.usuario,
                password=self._config.contrasena,
            )
        return self._conexion

    def cerrar(self):
        """Cierra la conexión si está abierta."""
        if self._conexion is not None and not self._conexion.closed:
            self._conexion.close()

    def aplicar_esquema(self) -> bool:
        """Crea las tablas del esquema inicial si no existen.

        Usa una transacción: si falla, no quedan cambios parciales.
        Devuelve True cuando se aplica sin errores; lanza la excepción de
        PostgreSQL en caso contrario.
        """
        sql = RUTA_ESQUEMA.read_text(encoding="utf-8")
        conexion = self.conectar()
        with conexion:
            with conexion.cursor() as cursor:
                cursor.execute(sql)
        return True

    def ejecutar_consulta(self, sql, parametros=None):
        """Ejecuta una consulta SELECT parametrizada y devuelve las filas.

        Nunca concatene valores al texto SQL: pase siempre `parametros`.
        """
        conexion = self.conectar()
        with conexion.cursor() as cursor:
            cursor.execute(sql, parametros)
            return cursor.fetchall()

    # ------------------------------------------------------------------
    # Movimientos financieros (CU-01)
    # ------------------------------------------------------------------

    def obtener_categorias(self):
        """Devuelve los nombres de las categorías, ordenados alfabéticamente."""
        filas = self.ejecutar_consulta("SELECT nombre FROM categoria ORDER BY nombre")
        return [fila[0] for fila in filas]

    def insertar_movimiento(self, movimiento: MovimientoFinanciero) -> MovimientoFinanciero:
        """Guarda un movimiento en una transacción y devuelve el movimiento con id.

        Si algo falla (categoría inexistente, restricción de la tabla), la
        transacción se revierte: no quedan cambios parciales (RNF-07).
        """
        conexion = self.conectar()
        with conexion:
            with conexion.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM categoria WHERE nombre = %s",
                    (movimiento.categoria,),
                )
                fila = cursor.fetchone()
                if fila is None:
                    raise LookupError(
                        f"La categoría «{movimiento.categoria}» no existe en el catálogo."
                    )
                cursor.execute(
                    """INSERT INTO movimiento_financiero
                           (tipo_movimiento, fecha, valor, moneda, categoria_id, descripcion)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       RETURNING id""",
                    (
                        movimiento.tipo_movimiento,
                        movimiento.fecha,
                        movimiento.valor,
                        movimiento.moneda,
                        fila[0],
                        movimiento.descripcion,
                    ),
                )
                nuevo_id = cursor.fetchone()[0]
        return movimiento.con_id(nuevo_id)

    def obtener_movimientos(self, tipo=None):
        """Devuelve los movimientos guardados, opcionalmente por tipo.

        Ordenados del más reciente al más antiguo. Los importes llegan como
        Decimal (columna NUMERIC), sin pasar por float.
        """
        sql = """SELECT m.id, m.tipo_movimiento, m.fecha, m.valor, m.moneda,
                        c.nombre, m.descripcion
                   FROM movimiento_financiero m
                   JOIN categoria c ON c.id = m.categoria_id"""
        parametros = []
        if tipo is not None:
            sql += " WHERE m.tipo_movimiento = %s"
            parametros.append(tipo)
        sql += " ORDER BY m.fecha DESC, m.id DESC"
        filas = self.ejecutar_consulta(sql, parametros or None)
        return [
            MovimientoFinanciero(
                id=fila[0],
                tipo_movimiento=fila[1],
                fecha=fila[2],
                valor=fila[3],
                moneda=fila[4],
                categoria=fila[5],
                descripcion=fila[6],
            )
            for fila in filas
        ]

    def resumen_mensual(self, anno, mes):
        """Devuelve el total de movimientos de un mes agrupado por tipo,
        moneda y categoría.

        Cada fila es (tipo_movimiento, moneda, categoria, total Decimal).
        Los importes llegan como Decimal (columna NUMERIC), sin pasar por
        float.
        """
        sql = """SELECT m.tipo_movimiento, m.moneda, c.nombre, SUM(m.valor)
                   FROM movimiento_financiero m
                   JOIN categoria c ON c.id = m.categoria_id
                  WHERE EXTRACT(YEAR FROM m.fecha) = %s
                    AND EXTRACT(MONTH FROM m.fecha) = %s
                  GROUP BY m.tipo_movimiento, m.moneda, c.nombre
                  ORDER BY c.nombre"""
        filas = self.ejecutar_consulta(sql, (anno, mes))
        return [(fila[0], fila[1], fila[2], fila[3]) for fila in filas]

    def eliminar_movimiento(self, id_movimiento) -> bool:
        """Elimina un movimiento por su id en una transacción.

        Devuelve True si el movimiento existía y False si no.
        """
        conexion = self.conectar()
        with conexion:
            with conexion.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM movimiento_financiero WHERE id = %s",
                    (id_movimiento,),
                )
                return cursor.rowcount == 1
