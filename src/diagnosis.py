# diagnosis.py
# Módulo de diagnóstico de la pieza madre.
# Parte A: obtener el HTML (desde la URL o desde un respaldo) y extraer solo el contenido principal.
# Parte B: convertirlo en un documento estructurado y entregar la ficha de diagnóstico
#          (indicadores medibles, alertas según las reglas y formatos que aplican).
# No tiene nada escrito sobre la guía de RPA: funciona con cualquier página.

import re                       # Expresiones regulares: buscar patrones en texto
from datetime import date       # Para calcular la antigüedad del contenido
from pathlib import Path        # Para manejar rutas de archivos

import requests                 # Librería para descargar páginas web
from bs4 import BeautifulSoup   # Librería para leer y recorrer HTML

from src import rules           # Nuestras reglas de negocio (términos prohibidos, etc.)

# Palabras que indican que una cifra tiene fuente ("según X", "fuente: X")
SOURCE_WORDS = re.compile(r"\b(según|fuente|de acuerdo con|reporta|estudio de)\b", re.IGNORECASE)

# Una "cifra" es un número con %, $ o un número de 2+ dígitos que no sea un año
FIGURE_PATTERN = re.compile(r"\d+([.,]\d+)?\s?%|\$\s?\d+|\b(?!19\d\d|20\d\d)\d{2,}\b")

# Etiquetas que NO son contenido de la guía: menús, encabezados, pies de página, scripts, etc.
NOISE_TAGS = ["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "iframe"]


def fetch_html(url, backup_path=None, timeout=15):
    """Descarga el HTML de la URL. Si falla, usa el archivo de respaldo y avisa.

    Devuelve dos valores: el HTML (texto) y el origen ("url" o "backup").
    """
    try:
        # Pide la página. "timeout" evita que el programa se quede esperando para siempre.
        # El User-Agent identifica a nuestro programa ante el servidor.
        response = requests.get(url, timeout=timeout,
                                headers={"User-Agent": "Mozilla/5.0 (content-diagnosis-bot)"})
        # Si el servidor respondió con error (404, 500...), esto lanza una excepción
        response.raise_for_status()
        # Si el servidor no dice la codificación, se asume utf-8 para que las tildes salgan bien
        response.encoding = response.encoding or "utf-8"
        return response.text, "url"

    except requests.RequestException as error:
        # Cualquier problema de red o de servidor cae aquí
        print(f"[WARN] Could not download {url}: {error}")

        # Si hay respaldo y existe, lo usamos y dejamos claro que vino del respaldo
        if backup_path and Path(backup_path).exists():
            print(f"[WARN] Using backup file: {backup_path}")
            return Path(backup_path).read_text(encoding="utf-8"), "backup"

        # Sin respaldo no podemos seguir: volvemos a lanzar el error original
        raise


def extract_main_content(html):
    """Recibe el HTML completo y devuelve solo el bloque principal del contenido."""
    # Convierte el texto HTML en un objeto que podemos recorrer
    soup = BeautifulSoup(html, "html.parser")

    # Elimina todas las etiquetas de "ruido" (menús, pie de página, etc.)
    for tag in soup(NOISE_TAGS):
        tag.decompose()  # decompose() borra la etiqueta y todo lo que tiene dentro

    # Busca el contenido principal: primero <main>, si no hay <article>, si no el <body>
    # (si el HTML no tiene ni <body>, se usa el documento completo)
    main = soup.find("main") or soup.find("article") or soup.body or soup

    # Algunas páginas tienen un <main> dentro de otro <main> (ej. barras laterales).
    # Lo quitamos para no mezclar texto que no es de la pieza.
    for inner in main.find_all("main"):
        inner.decompose()

    return main


# ===========================================================================
# PARTE B
# ===========================================================================

def clean_text(element):
    """Texto de una etiqueta con los espacios normalizados (sin saltos de línea dobles)."""
    # get_text() sin separador respeta los espacios originales; así no se parten
    # palabras que el HTML divide en varias etiquetas <span> (pasa en esta guía).
    return re.sub(r"\s+", " ", element.get_text()).strip()


def split_sentences(text):
    """Divide un texto en frases usando el punto, el signo de interrogación o de exclamación."""
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 1]


def parse_document(main):
    """Recorre el contenido en orden y lo agrupa en secciones (una por cada <h2>).

    Devuelve: {"title", "sections": [{"heading", "paragraphs", "lists", "subheadings"}],
               "headings": [todos los títulos en orden]}
    """
    title_tag = main.find("h1")
    title = clean_text(title_tag) if title_tag else ""

    # La primera "sección" es la introducción, antes del primer <h2>
    sections = [{"heading": title, "paragraphs": [], "lists": [], "subheadings": []}]
    headings = []
    previous_text = None

    for element in main.find_all(["h1", "h2", "h3", "p", "ul", "ol"]):
        # Las listas anidadas dentro de otra lista ya se leen con la lista de afuera
        if element.find_parent(["ul", "ol"]):
            continue
        text = clean_text(element)
        # Se ignoran bloques vacíos y bloques repetidos seguidos (ej. el título copiado en un <p>)
        if not text or text == previous_text:
            continue
        previous_text = text

        if element.name == "h2":
            headings.append(text)
            sections.append({"heading": text, "paragraphs": [], "lists": [], "subheadings": []})
        elif element.name == "h3":
            headings.append(text)
            sections[-1]["subheadings"].append(text)
        elif element.name == "p":
            sections[-1]["paragraphs"].append(text)
        elif element.name in ("ul", "ol"):
            items = [clean_text(li) for li in element.find_all("li", recursive=False)]
            items = [item for item in items if item]
            if items:
                sections[-1]["lists"].append(items)

    return {"title": title, "sections": sections, "headings": headings}


def full_text(document):
    """Une todo el texto del documento en un solo string (para buscar reglas y cifras)."""
    parts = [document["title"]]
    for section in document["sections"]:
        parts.append(section["heading"])
        parts.extend(section["subheadings"])
        parts.extend(section["paragraphs"])
        for items in section["lists"]:
            parts.extend(items)
    return "\n".join(parts)


def find_publication_date(html):
    """Busca la fecha de publicación (formato ISO, ej. 2023-02-13T15:11) dentro del HTML."""
    match = re.search(r"(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}", html)
    return match.group(1) if match else None


def find_product_candidates(main):
    """Nombres cortos de enlaces que apuntan a páginas de servicios o productos.

    Es una heurística: sirve para detectar productos que no están en la lista vigente.
    """
    candidates = []
    for link in main.find_all("a", href=True):
        name = clean_text(link)
        is_product_page = re.search(r"/(servicios?|productos?|soluciones?)[-/]", link["href"])
        # Un nombre de producto va con mayúscula inicial en cada palabra ("Turbo RPA");
        # así se descartan textos de botones como "Conoce más"
        looks_like_name = name and len(name.split()) <= 3 and all(w[0].isupper() for w in name.split())
        if is_product_page and looks_like_name:
            candidates.append(name)
    return candidates


def compute_indicators(document, text, publication_date, today=None):
    """Calcula los indicadores medibles de la ficha de diagnóstico."""
    today = today or date.today()
    sentences = split_sentences(" ".join(
        p for s in document["sections"] for p in s["paragraphs"]))
    figure_sentences = [s for s in split_sentences(text.replace("\n", ". ")) if FIGURE_PATTERN.search(s)]
    all_lists = [items for s in document["sections"] for items in s["lists"]]

    # Títulos repetidos: aparecen más de una vez en el documento
    repeated = sorted({h for h in document["headings"] if document["headings"].count(h) > 1})
    # Secciones vacías: tienen título pero ni párrafos ni listas
    empty = [s["heading"] for s in document["sections"][1:] if not s["paragraphs"] and not s["lists"]]

    age_years = None
    if publication_date:
        age_years = round((today - date.fromisoformat(publication_date)).days / 365, 1)

    return {
        "palabras": len(text.split()),
        "secciones": len(document["sections"]) - 1,  # sin contar la introducción
        "listas": len(all_lists),
        "lista_mas_larga": max((len(items) for items in all_lists), default=0),
        "palabras_promedio_por_frase": round(len(" ".join(sentences).split()) / len(sentences), 1) if sentences else 0,
        "frases_con_cifras": len(figure_sentences),
        "cifras_con_fuente": sum(1 for s in figure_sentences if SOURCE_WORDS.search(s)),
        "titulos_repetidos": repeated,
        "secciones_vacias": empty,
        "fecha_publicacion": publication_date,
        "antiguedad_anios": age_years,
    }


def quality_alerts(indicators):
    """Alertas de calidad (no de reglas): cosas que una persona debería revisar."""
    alerts = []
    if indicators["palabras_promedio_por_frase"] > 25:
        alerts.append("Frases largas (más de 25 palabras en promedio): la lectura puede ser difícil")
    if indicators["titulos_repetidos"]:
        alerts.append(f"Títulos repetidos en la página: {indicators['titulos_repetidos']}")
    if indicators["secciones_vacias"]:
        alerts.append(f"Secciones sin contenido: {indicators['secciones_vacias']}")
    if indicators["frases_con_cifras"] > indicators["cifras_con_fuente"]:
        alerts.append("Hay cifras sin fuente citada: no se pueden usar como dato en las piezas")
    if indicators["antiguedad_anios"] and indicators["antiguedad_anios"] >= 2:
        alerts.append(f"Contenido publicado hace {indicators['antiguedad_anios']} años: revisar vigencia")
    return alerts


def _sections_with_content(document, min_sentences=2):
    """Secciones (sin la introducción) con al menos N frases de texto propio."""
    return [s for s in document["sections"][1:]
            if len(split_sentences(" ".join(s["paragraphs"]))) >= min_sentences]


def evaluate_formats(document, indicators, has_testimonial=False):
    """Decide qué formatos de la matriz se pueden sacar de la pieza madre y por qué.

    Cada formato pide algo distinto de la pieza madre (campo "requiere_de_pieza_madre").
    """
    developed = _sections_with_content(document)
    longest_list = indicators["lista_mas_larga"]

    checks = {
        "post_linkedin": (len(developed) >= 1, f"{len(developed)} secciones desarrolladas"),
        "carrusel_linkedin": (longest_list >= 5, f"lista más larga con {longest_list} elementos (se piden 5)"),
        "newsletter": (len(developed) >= 3, f"{len(developed)} temas desarrollables (se piden 3)"),
        "guion_video_corto": (len(developed) >= 3 or longest_list >= 3, "al menos 3 puntos claros"),
        "caso_de_exito": (has_testimonial,
                          "hay un testimonio citado (verificar nombre, cargo y cifras)" if has_testimonial
                          else "no hay testimonio de cliente con nombre y cargo"),
        "infografia": (indicators["cifras_con_fuente"] >= 5 or 5 <= longest_list,
                       f"{indicators['cifras_con_fuente']} cifras con fuente; pasos en lista: {longest_list}"),
    }
    return checks


def detect_topic(text, known_topics, default="marca"):
    """Elige el tema de la pieza entre los temas que ya existen en el historial.

    Cuenta cuántas veces aparece cada tema en el texto ("software_factory" se busca
    como "software factory") y elige el más mencionado. Si ninguno aparece, usa "marca".
    """
    counts = {}
    for topic in known_topics:
        if topic == default:
            continue
        words = topic.replace("_", " ")
        counts[topic] = len(re.findall(r"(?<!\w)" + re.escape(words) + r"(?!\w)", text, re.IGNORECASE))
    best = max(counts, key=counts.get, default=None)
    return best if best and counts[best] > 0 else default


def diagnose(url, config, backup_path=None, known_topics=(), today=None):
    """Ejecuta todo el diagnóstico y devuelve (ficha, documento estructurado)."""
    html, source = fetch_html(url, backup_path)
    main = extract_main_content(html)
    document = parse_document(main)
    text = full_text(document)
    publication_date = find_publication_date(html)

    indicators = compute_indicators(document, text, publication_date, today)
    product_candidates = find_product_candidates(main)

    # Formatos: los que no están en nuestras reglas de evaluación quedan para revisión humana.
    # Un testimonio se reconoce por la etiqueta <blockquote> (cita).
    checks = evaluate_formats(document, indicators, has_testimonial=main.find("blockquote") is not None)
    formats = []
    for fmt in config["matriz_formatos"]:
        viable, reason = checks.get(fmt["id"], (False, "formato sin regla de evaluación: revisar a mano"))
        formats.append({"formato": fmt["id"], "viable": viable, "motivo": reason})

    report = {
        "url": url,
        "origen_contenido": source,  # "url" o "backup": queda claro de dónde salió
        "titulo": document["title"],
        "tema": detect_topic(text, known_topics),
        "indicadores": indicators,
        "alertas_reglas": rules.check_text(text, config, product_candidates),
        "alertas_calidad": quality_alerts(indicators),
        "productos_vigentes_mencionados": rules.find_current_products(text, config),
        "formatos": formats,
    }
    if source == "backup":
        report["alertas_calidad"].insert(0, "No se pudo descargar la URL: se usó el archivo de respaldo")
    return report, document