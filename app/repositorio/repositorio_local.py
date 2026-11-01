"""Acceso a PostgreSQL local (RepositorioLocal del modelo de la tesis).

Responsabilidades:
- Abrir y cerrar la conexión con PostgreSQL local.
- Aplicar el esquema inicial de la base de datos.
- Ejecutar consultas parametrizadas.

No contiene reglas de negocio: la validación y coordinación viven en
GestorFinanciero (implementación pendiente para el incremento 2).
"""

from pathlib import Path

import psycopg2

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
