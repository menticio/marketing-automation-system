# test_system.py
# Pruebas automatizadas. Se corren con:  python -m pytest -v
# Cada prueba falla si una regla de negocio se rompe. No usan internet:
# trabajan con HTML y datos pequeños escritos aquí mismo o con los archivos de data/.

import copy
from datetime import datetime

import pytest

from src import rules, scoring
from src.config import DATA_DIR, load_config, load_json
from src.diagnosis import extract_main_content, fetch_html, parse_document
from src.scheduler import build_slots, find_conflicts, load_occupied, schedule
from src.transform import build_utm_link, validate_piece


@pytest.fixture
def config():
    """Las reglas reales de config.json (se cargan para cada prueba)."""
    return load_config()


@pytest.fixture
def window():
    return load_json(DATA_DIR / "ventana.json")


def formats(config):
    return {fmt["id"]: fmt for fmt in config["matriz_formatos"]}


# ---------------------------------------------------------------- reglas

def test_prohibited_terms_are_detected(config):
    text = "Nuestro motor con GPT ofrece integración inmediata y cero errores."
    found = [item["termino"] for item in rules.find_prohibited_terms(text, config)]
    assert "GPT" in found
    assert "integración inmediata" in found


def test_llama_verb_is_not_a_false_alarm(config):
    # "se llama" es un verbo, no el modelo de IA "Llama"
    assert rules.find_prohibited_terms("Este proceso se llama conciliación.", config) == []


def test_confidential_client_is_detected(config):
    alerts = rules.check_text("Cerramos con el caso de Banco Andino del Sur.", config)
    assert any("Banco Andino del Sur" in alert for alert in alerts)


def test_unlisted_product_is_flagged(config):
    alerts = rules.check_text("texto", config, extra_products=["Turbo RPA", "Docfly"])
    assert alerts == ["Producto no vigente mencionado: 'Turbo RPA' (marcar para revisión)"]


def test_utm_link_follows_convention(config):
    link = build_utm_link("https://ejemplo.com/Guía de Pruebas/", formats(config)["post_linkedin"], 1, "202611", config)
    assert "utm_source=linkedin" in link
    assert "utm_medium=social-organico" in link
    assert "utm_campaign=guia-de-pruebas-202611" in link   # minúsculas, sin tildes, con guiones
    assert "utm_content=post-linkedin-1" in link


# ---------------------------------------------------------------- diagnóstico

def test_extraction_ignores_navigation_and_nested_main():
    html = """<html><body><nav>Menú</nav><main><h1>Título</h1><p>Contenido real.</p>
              <main><p>Barra lateral</p></main></main><footer>Pie</footer></body></html>"""
    main = extract_main_content(html)
    text = main.get_text()
    assert "Contenido real." in text
    assert "Menú" not in text and "Pie" not in text and "Barra lateral" not in text


def test_backup_is_used_when_url_fails(tmp_path):
    backup = tmp_path / "respaldo.html"
    backup.write_text("<main><h1>Respaldo</h1></main>", encoding="utf-8")
    html, source = fetch_html("http://localhost:9/no-existe", backup_path=backup, timeout=2)
    assert source == "backup"
    assert "Respaldo" in html


def test_document_is_split_by_sections():
    main = extract_main_content("<main><h1>T</h1><p>Intro.</p><h2>A</h2><ol><li>1</li><li>2</li></ol>"
                                "<h2>B</h2><p>Texto B.</p></main>")
    document = parse_document(main)
    assert [s["heading"] for s in document["sections"]] == ["T", "A", "B"]
    assert document["sections"][1]["lists"] == [["1", "2"]]


# ---------------------------------------------------------------- validación de piezas

def test_post_that_is_too_long_is_rejected(config):
    piece = {"partes": {"gancho": "¿Gancho?"}, "texto": "palabra " * 300 + "utm_source=linkedin"}
    problems = validate_piece(piece, formats(config)["post_linkedin"], config)
    assert any("Longitud" in p for p in problems)


def test_carousel_slide_with_too_many_words_is_rejected(config):
    slides = ["una idea corta"] * 5 + ["palabra " * 31]
    piece = {"partes": {"laminas": slides}, "texto": "\n".join(slides)}
    problems = validate_piece(piece, formats(config)["carrusel_linkedin"], config)
    assert any("Lámina 6" in p for p in problems)


def test_piece_with_prohibited_term_is_rejected(config):
    text = "Resultados " * 80 + "con 100% de precisión. utm_source=linkedin"
    piece = {"partes": {"gancho": "Gancho"}, "texto": text}
    problems = validate_piece(piece, formats(config)["post_linkedin"], config)
    assert any("100% de precisión" in p for p in problems)


# ---------------------------------------------------------------- calendario

def _pieces(n, topic="rpa", fmt="post_linkedin"):
    return [{"id": f"p{i}", "formato": fmt, "tema": topic, "titulo": f"Pieza {i}",
             "canal": "linkedin", "puntaje": 50} for i in range(n)]


def test_no_slots_on_weekends_or_holidays(config, window):
    slots = build_slots(window, config["calendario"])
    holidays = {h["fecha"] for h in config["calendario"]["festivos"]}
    assert slots, "debe haber franjas en la ventana"
    for slot in slots:
        assert slot.weekday() < 5
        assert slot.date().isoformat() not in holidays   # el 8 de diciembre es festivo


def test_schedule_respects_all_calendar_rules(config, window):
    occupied = load_occupied(DATA_DIR / "calendario_ocupado.csv")
    pieces = _pieces(3, "rpa", "post_linkedin") + _pieces(3, "docfly", "carrusel_linkedin")
    for i, piece in enumerate(pieces):
        piece["id"] = f"pieza{i}"
    calendar, unplaced = schedule(pieces, window, occupied, config)
    assert find_conflicts(calendar, config) == []
    assert len(calendar) - len(occupied) + len(unplaced) == len(pieces)  # ninguna se pierde


def test_same_topic_pieces_are_48_hours_apart(config, window):
    calendar, _ = schedule(_pieces(4), window, [], config)
    times = sorted(e["inicio"] for e in calendar)
    gaps = [(b - a).total_seconds() / 3600 for a, b in zip(times, times[1:])]
    assert all(gap >= config["calendario"]["separacion_minima_mismo_tema_horas"] for gap in gaps)


def test_conflict_checker_catches_a_broken_calendar(config):
    broken = [{"inicio": datetime(2026, 12, 8, 8, 30), "formato": "post_linkedin", "tema": "rpa"},
              {"inicio": datetime(2026, 12, 9, 8, 30), "formato": "post_linkedin", "tema": "rpa"}]
    conflicts = find_conflicts(broken, config)
    assert any("festivo" in c for c in conflicts)
    assert any("mismo tema" in c for c in conflicts)


def test_capacity_comes_from_config(config, window):
    # Si Mercadeo cambia la regla en config.json, el calendario la obedece sin tocar código
    strict = copy.deepcopy(config)
    strict["calendario"]["capacidad_max_por_semana"] = 1
    pieces = _pieces(2, "rpa") + _pieces(2, "docfly")
    for i, piece in enumerate(pieces):
        piece["id"] = f"x{i}"
    calendar, unplaced = schedule(pieces, window, [], strict)
    assert len(calendar) == 2 and len(unplaced) == 2   # una por cada una de las 2 semanas


# ---------------------------------------------------------------- historial y puntaje

def test_dirty_values_are_parsed():
    assert scoring.parse_date("2026-03-05").isoformat() == "2026-03-05"
    assert scoring.parse_date("16/03/2026").isoformat() == "2026-03-16"   # día/mes/año
    assert scoring.parse_date("17-mar-2026").isoformat() == "2026-03-17"
    assert scoring.parse_decimal("0,0338") == pytest.approx(0.0338)
    assert scoring.parse_bool("sí") is True and scoring.parse_bool("No") is False


def test_history_is_cleaned_without_editing_the_file():
    history, report = scoring.load_history(DATA_DIR / "historial_publicaciones.csv")
    assert report["filas_repetidas_eliminadas"] == 3
    assert report["tasas_recalculadas"] == 1
    assert history["id_publicacion"].is_unique
    assert history["fecha"].notna().all()


def test_score_is_between_0_and_100_and_never_invented():
    history, _ = scoring.load_history(DATA_DIR / "historial_publicaciones.csv")
    model = scoring.build_model(history)
    score, _ = scoring.score_piece({"formato": "carrusel_linkedin", "tema": "rpa", "tiene_cifra": True}, model, "08:30")
    assert 0 <= score <= 100
    # No hay newsletters en el historial: el sistema dice que no hay datos en vez de inventar
    score, explanation = scoring.score_piece({"formato": "newsletter", "tema": "rpa", "tiene_cifra": False}, model)
    assert score is None and "Sin historial" in explanation
