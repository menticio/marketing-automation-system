# transform.py
# Agente de transformación: convierte la pieza madre (ya estructurada por el
# diagnóstico) en piezas derivadas redactadas y ordenadas por partes.
#
# Decisión de diseño: la redacción es EXTRACTIVA. Cada frase de una pieza sale
# textual de la pieza madre; el sistema solo elige, ordena y recorta. Así no puede
# inventar datos (regla "que el sistema no invente nada"). Lo único que agrega son
# conectores fijos y el llamado a la acción. Toda pieza se valida contra su ficha
# de config.json y contra las reglas antes de pasar a la cola de aprobación.

import re
from urllib.parse import urlencode, urlparse

from src import rules
from src.diagnosis import FIGURE_PATTERN, split_sentences

# Frases típicas de blog que solo invitan a leer otro artículo: no aportan contenido
TEASER_PATTERN = re.compile(
    r"^(te podría interesar|te recomendamos|te invitamos|conoce|lee|descubre|descarga|"
    r"si quieres saber|habla aquí|aprende cómo|obtener)", re.IGNORECASE)

# Secciones cuya lista dice lo contrario de lo que se quiere comunicar (mitos, errores).
# Sacadas de contexto en un carrusel afirmarían algo falso, así que no se usan como láminas.
NEGATIVE_SECTION = re.compile(r"\b(mitos?|errores?|falsos?)\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def safe_sentences(paragraphs, config):
    """Frases de los párrafos que se pueden reutilizar sin romper reglas."""
    selected = []
    # Además de cortar por punto, se corta después de ":" cuando empieza una frase nueva
    # (ej. "...estos consejos: Conoce cada consejo..."), para poder descartar cada parte.
    pieces = [part for sentence in split_sentences(" ".join(paragraphs))
              for part in re.split(r"(?<=:)\s+(?=[A-ZÁÉÍÓÚÑ¿¡])", sentence)]
    skip_next = False
    for sentence in pieces:
        if skip_next:
            # Es el título del enlace que anunciaba la frase anterior. Si también
            # termina en ":", anuncia otra cosa más y se sigue saltando.
            skip_next = sentence.endswith(":")
            continue
        if TEASER_PATTERN.search(sentence) or sentence.endswith(":"):
            # Invitación a otro artículo o frase que anuncia algo: si termina en ":",
            # lo que sigue es el título de un enlace, que tampoco es contenido
            skip_next = sentence.endswith(":")
            continue
        if len(sentence.split()) < 6:
            continue  # frases demasiado cortas para tener sentido solas
        if rules.check_text(sentence, config):
            continue  # la frase tiene un término prohibido o un nombre confidencial
        selected.append(sentence)
    return selected


def shorten_words(text, max_words):
    """Recorta un texto a un máximo de palabras (se queda con la primera frase si cabe)."""
    first = split_sentences(text)[0] if split_sentences(text) else text
    words = first.split()
    if len(words) <= max_words:
        return first
    return " ".join(words[:max_words]).rstrip(",;:") + "…"


def build_utm_link(url, fmt, number, campaign_month, config):
    """Construye el enlace con UTM según la convención de config.json."""
    utm = config["utm"]
    slug = rules.slugify(urlparse(url).path.strip("/").split("/")[-1] or urlparse(url).netloc)
    params = {
        "utm_source": utm["utm_source"][fmt["canal"]],
        "utm_medium": utm["utm_medium"][fmt["canal"]],
        "utm_campaign": rules.slugify(utm["utm_campaign"].format(slug_pieza_madre=slug, aaaamm=campaign_month)),
        "utm_content": rules.slugify(utm["utm_content"].format(formato=fmt["id"], numero=number)),
    }
    base = url.split("?")[0]
    return f"{base}?{urlencode(params)}"


def _developed_sections(document, config, min_sentences=2):
    """Secciones con al menos N frases reutilizables, de la más desarrollada a la menos."""
    sections = []
    for section in document["sections"][1:]:
        sentences = safe_sentences(section["paragraphs"], config)
        if len(sentences) >= min_sentences:
            sections.append((section, sentences))
    return sorted(sections, key=lambda pair: len(pair[1]), reverse=True)


# ---------------------------------------------------------------------------
# Generadores: uno por formato
# ---------------------------------------------------------------------------

def make_post_linkedin(document, fmt, link, config):
    """Post: gancho + una sola idea en párrafos cortos + llamado a la acción + enlace."""
    limits = fmt["longitud"]
    candidates = _developed_sections(document, config)
    # Se prefiere una sección cuyo título sea una pregunta: es un gancho natural
    questions = [pair for pair in candidates if pair[0]["heading"].endswith("?")]
    section, sentences = (questions or candidates)[0]

    hook = section["heading"]
    if len(hook) > fmt["gancho_max_caracteres"]:
        hook = shorten_words(sentences[0], 20)
    cta = "¿Cómo lo están resolviendo en tu equipo? Lee la guía completa aquí:"

    # Se agregan frases (una por párrafo) hasta llegar al mínimo sin pasar el máximo
    body = []
    for sentence in sentences:
        draft = "\n\n".join([hook, *body, sentence, cta, link])
        if len(draft) > limits["max_caracteres"]:
            break
        body.append(sentence)
        if len(draft) >= limits["min_caracteres"]:
            break

    text = "\n\n".join([hook, *body, cta, link])
    return {"titulo": section["heading"],
            "partes": {"gancho": hook, "desarrollo": body, "llamado_a_la_accion": cta, "enlace": link},
            "texto": text}


def make_carrusel_linkedin(document, fmt, link, config):
    """Carrusel: portada con gancho + una idea por lámina + cierre con llamado a la acción."""
    max_inner = fmt["laminas"]["max"] - 2  # se reservan portada y cierre
    min_inner = fmt["laminas"]["min"] - 2
    best = None
    for section in document["sections"]:
        if NEGATIVE_SECTION.search(section["heading"]):
            continue
        for items in section["lists"]:
            clean = [i for i in items if not rules.check_text(i, config)]
            # Se busca la lista más larga que quepa completa en el carrusel
            if min_inner <= len(clean) <= max_inner and (best is None or len(clean) > len(best[1])):
                best = (section, clean)
    if best is None:
        return None
    section, items = best

    cover = f"{section['heading']}: {len(items)} claves en {len(items)} láminas"
    slides = [shorten_words(item, fmt["max_palabras_por_lamina"]) for item in items]
    closing = f"Guarda este carrusel y revisa la guía completa: {link}"
    text = "\n\n".join([cover] + [f"{n}. {s}" for n, s in enumerate(slides, 1)] + [closing])
    return {"titulo": section["heading"],
            "partes": {"portada": cover, "laminas": slides, "cierre": closing, "enlace": link},
            "texto": text}


def make_newsletter(document, fmt, link, config):
    """Newsletter: asunto + introducción + 3 secciones con subtítulo + un llamado a la acción."""
    limits = fmt["longitud"]
    subject = document["title"]
    if len(subject) > fmt["asunto_max_caracteres"]:
        subject = subject[: fmt["asunto_max_caracteres"] - 1].rsplit(" ", 1)[0] + "…"

    intro_sentences = safe_sentences(document["sections"][0]["paragraphs"], config)[:2]
    chosen = _developed_sections(document, config)[:3]
    sections = [{"subtitulo": s["heading"], "frases": sentences[:1]} for s, sentences in chosen]
    cta = f"Lee la guía completa y comparte con tu equipo: {link}"

    def word_count():
        parts = [subject, *intro_sentences, cta] + [x for s in sections for x in [s["subtitulo"], *s["frases"]]]
        return len(" ".join(parts).split())

    # Se agregan frases a cada sección, por turnos, hasta llegar al mínimo de palabras
    added = True
    while word_count() < limits["min_palabras"] and added:
        added = False
        for section, (_, sentences) in zip(sections, chosen):
            if len(section["frases"]) < len(sentences):
                section["frases"].append(sentences[len(section["frases"])])
                added = True
                if word_count() >= limits["min_palabras"]:
                    break
    # Si se pasó del máximo, se quitan frases del final de cada sección
    while word_count() > limits["max_palabras"] and any(len(s["frases"]) > 1 for s in sections):
        max(sections, key=lambda s: len(s["frases"]))["frases"].pop()

    body = [f"## {s['subtitulo']}\n" + " ".join(s["frases"]) for s in sections]
    text = "\n\n".join([f"Asunto: {subject}", " ".join(intro_sentences), *body, cta])
    return {"titulo": subject,
            "partes": {"asunto": subject, "introduccion": " ".join(intro_sentences),
                       "secciones": [{"subtitulo": s["subtitulo"], "texto": " ".join(s["frases"])} for s in sections],
                       "llamado_a_la_accion": cta, "enlace": link},
            "texto": text}


def make_guion_video_corto(document, fmt, link, config):
    """Guion de video: gancho + 3 puntos (uno por bloque) + cierre con llamado a la acción."""
    limits = fmt["palabras"]
    chosen = _developed_sections(document, config)[:3]
    questions = [s["heading"] for s in document["sections"][1:] if s["heading"].endswith("?")]
    hook = questions[0] if questions else document["title"]
    points = [sentences[0] for _, sentences in chosen]
    closing = "Si quieres profundizar, la guía completa está en el enlace."

    # Si faltan palabras, el punto más corto suma su siguiente frase, hasta llegar al mínimo
    def words():
        return len(" ".join([hook, *points, closing]).split())

    used = [1] * len(points)  # cuántas frases de su sección lleva cada punto
    while words() < limits["min"]:
        options = [i for i, (_, sentences) in enumerate(chosen) if used[i] < len(sentences)]
        if not options:
            break  # no hay más material: la validación lo reportará
        shortest = min(options, key=lambda i: len(points[i].split()))
        points[shortest] += " " + chosen[shortest][1][used[shortest]]
        used[shortest] += 1
    # Si se pasó del máximo, se recorta el punto más largo
    while words() > limits["max"]:
        longest = max(range(len(points)), key=lambda i: len(points[i].split()))
        # Se quitan 5 palabras del final (siempre disminuye, así el ciclo termina)
        points[longest] = " ".join(points[longest].split()[:-5]).rstrip(",;:.") + "…"

    blocks = [f"[Gancho] {hook}"] + [f"[Punto {n}] {p}" for n, p in enumerate(points, 1)] + [f"[Cierre] {closing}"]
    return {"titulo": hook,
            "partes": {"gancho": hook, "puntos": points, "cierre": closing, "enlace": link},
            "texto": "\n\n".join(blocks)}


# Qué función redacta cada formato. Los formatos sin generador se reportan como pendientes.
GENERATORS = {
    "post_linkedin": make_post_linkedin,
    "carrusel_linkedin": make_carrusel_linkedin,
    "newsletter": make_newsletter,
    "guion_video_corto": make_guion_video_corto,
}


# ---------------------------------------------------------------------------
# Validación de cada pieza contra su ficha y las reglas
# ---------------------------------------------------------------------------

def validate_piece(piece, fmt, config):
    """Revisa una pieza contra la ficha de su formato y las reglas. Devuelve los problemas."""
    problems = []
    parts = piece["partes"]
    text = piece["texto"]
    # Las etiquetas como "[Punto 1]" o "## " no son palabras del contenido: no se cuentan
    words = len(re.sub(r"\[[^\]]+\]|#+ ", " ", text).split())

    if "longitud" in fmt and "min_caracteres" in fmt["longitud"]:
        low, high = fmt["longitud"]["min_caracteres"], fmt["longitud"]["max_caracteres"]
        if not low <= len(text) <= high:
            problems.append(f"Longitud {len(text)} caracteres (debe estar entre {low} y {high})")
    if "longitud" in fmt and "min_palabras" in fmt["longitud"]:
        low, high = fmt["longitud"]["min_palabras"], fmt["longitud"]["max_palabras"]
        if not low <= words <= high:
            problems.append(f"Longitud {words} palabras (debe estar entre {low} y {high})")
    if "palabras" in fmt and not fmt["palabras"]["min"] <= words <= fmt["palabras"]["max"]:
        problems.append(f"{words} palabras (debe estar entre {fmt['palabras']['min']} y {fmt['palabras']['max']})")
    if "gancho_max_caracteres" in fmt and len(parts.get("gancho", "")) > fmt["gancho_max_caracteres"]:
        problems.append(f"Gancho de {len(parts['gancho'])} caracteres (máximo {fmt['gancho_max_caracteres']})")
    if "asunto_max_caracteres" in fmt and len(parts.get("asunto", "")) > fmt["asunto_max_caracteres"]:
        problems.append(f"Asunto de {len(parts['asunto'])} caracteres (máximo {fmt['asunto_max_caracteres']})")
    if "laminas" in fmt:
        total = len(parts.get("laminas", [])) + 2  # internas + portada + cierre
        if not fmt["laminas"]["min"] <= total <= fmt["laminas"]["max"]:
            problems.append(f"{total} láminas (deben ser entre {fmt['laminas']['min']} y {fmt['laminas']['max']})")
        for n, slide in enumerate(parts.get("laminas", []), 1):
            if len(slide.split()) > fmt["max_palabras_por_lamina"]:
                problems.append(f"Lámina {n} con {len(slide.split())} palabras (máximo {fmt['max_palabras_por_lamina']})")
    if any("3 secciones" in step for step in fmt.get("estructura", [])) and len(parts.get("secciones", [])) != 3:
        problems.append("El newsletter debe tener exactamente 3 secciones")
    if any("UTM" in step for step in fmt.get("estructura", [])) and "utm_source=" not in text:
        problems.append("Falta el enlace con UTM")

    # Reglas de negocio: términos prohibidos, nombres confidenciales
    problems.extend(rules.check_text(text, config))
    return problems


# ---------------------------------------------------------------------------
# Orquestación del agente
# ---------------------------------------------------------------------------

def transform(document, diagnosis_report, config, campaign_month):
    """Genera, valida y deja en cola de aprobación las piezas de los formatos viables.

    Devuelve (piezas, formatos_omitidos). Ninguna pieza queda aprobada: eso lo hace una persona.
    """
    formats_by_id = {fmt["id"]: fmt for fmt in config["matriz_formatos"]}
    pieces, skipped = [], []

    for item in diagnosis_report["formatos"]:
        fmt = formats_by_id[item["formato"]]
        if not item["viable"]:
            skipped.append({"formato": fmt["id"], "motivo": item["motivo"]})
            continue
        generator = GENERATORS.get(fmt["id"])
        if generator is None:
            skipped.append({"formato": fmt["id"], "motivo": "viable, pero sin generador en esta versión"})
            continue

        link = build_utm_link(diagnosis_report["url"], fmt, 1, campaign_month, config)
        piece = generator(document, fmt, link, config)
        if piece is None:
            skipped.append({"formato": fmt["id"], "motivo": "no se encontró material suficiente que cumpla las reglas"})
            continue

        problems = validate_piece(piece, fmt, config)
        piece.update({
            "id": f"{fmt['id']}-1",
            "formato": fmt["id"],
            "canal": fmt["canal"],
            "tema": diagnosis_report["tema"],
            "palabras": len(re.sub(r"\[[^\]]+\]|#+ ", " ", piece["texto"]).split()),
            # ¿La pieza incluye una cifra (%, $, número)? Se ignora el enlace. Lo usa el puntaje.
            "tiene_cifra": bool(FIGURE_PATTERN.search(re.sub(r"https?://\S+", "", piece["texto"]))),
            "problemas": problems,
            # Nada se publica sin aprobación humana: el mejor estado posible es "pendiente"
            "estado": "pendiente_aprobacion" if not problems else "requiere_revision",
        })
        pieces.append(piece)
    return pieces, skipped
