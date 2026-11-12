# config.py
# Carga los archivos de entrada que necesita el sistema:
# las reglas de negocio (config.json) y la ventana de programación (ventana.json).
# Las reglas NUNCA se escriben dentro del código: siempre se leen de estos archivos,
# así Mercadeo puede cambiarlas sin tocar el programa.

import json               # Herramienta de Python para leer archivos JSON
from pathlib import Path  # Herramienta de Python para manejar rutas de archivos de forma segura

# Ruta absoluta a la carpeta "data" del proyecto.
# __file__      -> este archivo: .../src/config.py
# .resolve()    -> lo convierte en ruta completa
# .parent       -> sube un nivel: .../src
# .parent       -> sube otro nivel: la raíz del proyecto
# / "data"      -> entra a la carpeta "data"
# Así el programa funciona sin importar desde qué carpeta lo ejecutes.
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_json(path):
    """Lee un archivo JSON y devuelve su contenido como diccionario de Python."""
    # Convierte la ruta recibida (texto o Path) en un objeto Path
    path = Path(path)

    # Si el archivo no existe, se detiene con un mensaje claro
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    # Abre el archivo; "with" lo cierra solo al terminar.
    # encoding="utf-8" hace que las tildes y la "ñ" se lean bien.
    with open(path, encoding="utf-8") as file:
        # Convierte el texto JSON en un diccionario y lo devuelve
        return json.load(file)


def load_config(path=DATA_DIR / "config.json"):
    """Carga las reglas de Mercadeo: productos, términos prohibidos, formatos y calendario."""
    # "path" tiene un valor por defecto: si no se le pasa ruta, usa data/config.json.
    # Las pruebas pueden pasarle otro archivo de configuración para probar otros casos.
    return load_json(path)


def load_window(path=DATA_DIR / "ventana.json"):
    """Carga la ventana de programación: fecha de inicio y fecha de fin."""
    return load_json(path)