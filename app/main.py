"""Punto de entrada de la aplicación NexSaldo.

Ejecutar desde la raíz del proyecto (Windows):
    .venv\\Scripts\\python -m app.main
"""

import sys

from app.configuracion import cargar_configuracion_bd
from app.gestor.gestor_financiero import GestorFinanciero
from app.gui.ventana_principal import VentanaPrincipal
from app.repositorio.repositorio_local import RepositorioLocal


def main() -> int:
    try:
        configuracion = cargar_configuracion_bd()
    except KeyError as error:
        print(f"[ERROR] Falta la variable de entorno {error}.")
        print("        Copie .env.example a .env y complete los valores.")
        return 1
    except ValueError as error:
        print(f"[ERROR] Configuración inválida: {error}")
        return 1

    repositorio = RepositorioLocal(configuracion)
    gestor = GestorFinanciero(repositorio)
    ventana = VentanaPrincipal(gestor)
    ventana.mainloop()
    repositorio.cerrar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
