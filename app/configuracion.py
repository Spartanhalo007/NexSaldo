"""Configuración de conexión de NexSaldo.

Los datos de conexión se leen de variables de entorno, cargadas desde el
archivo .env de la raíz del proyecto. Ese archivo está excluido del
repositorio (ver .gitignore y .env.example), de modo que ninguna contraseña
real queda versionada en el código.

Este módulo no registra la contraseña en mensajes de error ni en logs.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Raíz del proyecto: carpeta que contiene este paquete `app` y el archivo .env.
RUTA_RAIZ = Path(__file__).resolve().parents[1]

# Carga el .env de la raíz del proyecto con una ruta explícita, para que el
# programa encuentre la configuración sin importar el directorio desde el que
# se ejecute. Si el archivo no existe, las variables se toman del entorno.
load_dotenv(RUTA_RAIZ / ".env")


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

    Lanza KeyError si falta una variable obligatoria y ValueError si
    NEXSALDO_DB_PUERTO no es un número.
    """
    puerto_texto = os.environ["NEXSALDO_DB_PUERTO"]
    try:
        puerto = int(puerto_texto)
    except ValueError as error:
        raise ValueError(
            f"NEXSALDO_DB_PUERTO debe ser un número de puerto "
            f"(por ejemplo, 5432); se encontró: {puerto_texto!r}"
        ) from error

    return ConfiguracionBD(
        host=os.environ["NEXSALDO_DB_HOST"],
        puerto=puerto,
        nombre=os.environ["NEXSALDO_DB_NOMBRE"],
        usuario=os.environ["NEXSALDO_DB_USUARIO"],
        contrasena=os.environ["NEXSALDO_DB_CONTRASENA"],
    )
