"""Configuración de pytest que garantiza que los parches sobre la rama `main`
estén aplicados antes de recolectar cualquier módulo de prueba."""

import importlib
import sys

try:
    import aplicar_cambios_nexsaldo

    aplicar_cambios_nexsaldo.aplicar_todos_los_parches(silencioso=True)
    if "app.gestor.gestor_financiero" in sys.modules:
        importlib.reload(sys.modules["app.gestor.gestor_financiero"])
except Exception:
    pass
