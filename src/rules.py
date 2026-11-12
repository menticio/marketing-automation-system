# rules.py
# Verificación de las reglas de negocio de Mercadeo sobre cualquier texto.
# Lo usan dos agentes: el diagnóstico (revisa la pieza madre) y la transformación
# (revisa cada pieza derivada). Todas las reglas vienen de config.json.

import re            # Expresiones regulares: búsqueda de patrones en texto
import unicodedata   # Para quitar tildes al construir "slugs"


def _term_pattern(term):
    """Construye el patrón de búsqueda de un término como palabra completa."""
    # (?<!\w) y (?!\w) = "no hay una letra justo antes / justo después".
    # Así "GPT" no coincide dentro de otra palabra.
    # re.escape protege símbolos como "%" para que se busquen literalmente.
    return r"(?<!\w)" + re.escape(term) + r"(?!\w)"


def find_prohibited_terms(text, config):
    """Devuelve los términos prohibidos que aparecen en el texto, con su motivo."""
    found = []
    for rule in config["terminos_prohibidos"]:
        term = rule["termino"]
        # Si el término empieza en mayúscula (GPT, OpenAI, Llama) es un nombre propio:
        # se busca respetando mayúsculas, para no confundir "Llama" (modelo de IA)
        # con "se llama" (verbo). Las frases comunes se buscan sin importar mayúsculas.
        flags = 0 if term[0].isupper() else re.IGNORECASE
        if re.search(_term_pattern(term), text, flags):
            found.append({"termino": term, "motivo": rule["motivo"]})
    return found


def find_confidential_names(text, config):
    """Devuelve los nombres de clientes confidenciales que aparecen en el texto."""
    return [name for name in config["nombres_confidenciales"]
            if re.search(_term_pattern(name), text, re.IGNORECASE)]


def find_current_products(text, config):
    """Devuelve los productos vigentes que el texto menciona."""
    return [product for product in config["productos_vigentes"]
            if re.search(_term_pattern(product), text, re.IGNORECASE)]


def find_unlisted_products(candidate_names, config):
    """De una lista de posibles nombres de producto, devuelve los que NO están vigentes."""
    current = {p.lower() for p in config["productos_vigentes"]}
    # set() elimina repetidos; sorted() los deja en orden alfabético para el reporte
    return sorted({name for name in candidate_names if name.lower() not in current})


def check_text(text, config, extra_products=()):
    """Aplica todas las reglas a un texto y devuelve la lista de alertas encontradas."""
    alerts = []
    for item in find_prohibited_terms(text, config):
        alerts.append(f"Término prohibido '{item['termino']}': {item['motivo']}")
    for name in find_confidential_names(text, config):
        alerts.append(f"Nombre confidencial de cliente: '{name}'")
    for name in find_unlisted_products(extra_products, config):
        alerts.append(f"Producto no vigente mencionado: '{name}' (marcar para revisión)")
    return alerts


def slugify(value):
    """Convierte un texto a la regla UTM: minúsculas, sin tildes ni espacios, con guiones."""
    # NFKD separa la letra de su tilde ("é" -> "e" + "´"); luego descartamos las tildes
    value = unicodedata.normalize("NFKD", str(value))
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    # Todo lo que no sea letra o número se vuelve guion, y se quitan guiones de los bordes
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")
