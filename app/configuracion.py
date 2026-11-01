"""Configuración de conexión de NexSaldo.

Los datos de conexión se leen de variables de entorno, cargadas desde un
archivo .env local que está excluido del repositorio (ver .gitignore y
.env.example). Este módulo no guarda contraseñas en el código.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class ConfiguracionBD:
    """Datos necesarios para conectarse a PostgreSQL local."""

    host: str
    puerto: int
    nombre: str
    usuario: str
    contrasena: str


def cargar_configuracion_bd() -> ConfiguracionBD:
    """Carga la configuración de la base de datos desde variables de entorno.

    Lanza KeyError si falta alguna variable obligatoria.
    """
    return ConfiguracionBD(
        host=os.environ["NEXSALDO_DB_HOST"],
        puerto=int(os.environ["NEXSALDO_DB_PUERTO"]),
        nombre=os.environ["NEXSALDO_DB_NOMBRE"],
        usuario=os.environ["NEXSALDO_DB_USUARIO"],
        contrasena=os.environ["NEXSALDO_DB_CONTRASENA"],
    )
