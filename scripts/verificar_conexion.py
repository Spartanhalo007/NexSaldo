"""Comprobación manual del Incremento 1: conexión y esquema inicial.

Uso (desde la raíz del proyecto, con el entorno virtual activo):
    python scripts\\verificar_conexion.py

Qué hace:
1. Carga la configuración desde variables de entorno (archivo .env).
2. Conecta a PostgreSQL local con la cuenta de la aplicación.
3. Aplica el esquema inicial (tablas categoria y movimiento_financiero).
4. Muestra las categorías guardadas como evidencia.

Este script es una comprobación manual: las pruebas automatizadas se
incorporan a partir del incremento 2.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.configuracion import cargar_configuracion_bd
from app.repositorio.repositorio_local import RepositorioLocal


def main() -> int:
    print("NexSaldo - verificación de conexión y esquema inicial")
    print("-" * 55)

    try:
        configuracion = cargar_configuracion_bd()
    except KeyError as error:
        print(f"[ERROR] Falta la variable de entorno {error}.")
        print("        Copie .env.example a .env y complete los valores.")
        return 1

    repositorio = RepositorioLocal(configuracion)

    try:
        repositorio.conectar()
        print(
            f"[OK] Conexión establecida con {configuracion.usuario}@"
            f"{configuracion.host}:{configuracion.puerto}/{configuracion.nombre}"
        )
    except Exception as error:
        print(f"[ERROR] No se pudo conectar a PostgreSQL: {error}")
        return 1

    try:
        repositorio.aplicar_esquema()
        print("[OK] Esquema inicial aplicado (categoria, movimiento_financiero).")
    except Exception as error:
        print(f"[ERROR] No se pudo aplicar el esquema: {error}")
        repositorio.cerrar()
        return 1

    try:
        filas = repositorio.ejecutar_consulta(
            "SELECT nombre FROM categoria ORDER BY nombre"
        )
        print(f"[OK] Categorías guardadas ({len(filas)}):")
        for (nombre,) in filas:
            print(f"     - {nombre}")
    except Exception as error:
        print(f"[ERROR] No se pudieron consultar las categorías: {error}")
        repositorio.cerrar()
        return 1

    repositorio.cerrar()
    print("-" * 55)
    print("Resultado: verificación completada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
