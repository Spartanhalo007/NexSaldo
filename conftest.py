# Archivo de configuración de pytest.
# Permite que las pruebas importen el paquete `app` desde la raíz del proyecto.

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
