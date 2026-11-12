# main.py
# Orquestador: ejecuta los agentes en orden con un solo comando y deja todo en archivos.
#
#   python -m src.main --url https://trycore.com/guia-de-automatizacion-con-rpa/
#
# Flujo: diagnóstico -> transformación (+ validación) -> puntaje -> calendario
#        -> puntaje final con la hora asignada -> página web y archivos de salida.
# Todas las entradas (URL, config, ventana, calendario ocupado, historial) se pueden
# cambiar por parámetro: nada de la pieza madre está escrito en el código.

import argparse
import json
from pathlib import Path

from src import scoring
from src.calendar_view import render_calendar
from src.config import DATA_DIR, load_config, load_json
from src.diagnosis import diagnose
from src.scheduler import find_conflicts, load_occupied, schedule
from src.transform import transform

PROJECT_DIR = DATA_DIR.parent


def parse_args():
    """Lee los parámetros de la línea de comandos (todos tienen un valor por defecto)."""
    parser = argparse.ArgumentParser(description="Sistema de agentes para contenidos de Mercadeo")
    parser.add_argument("--url", help="URL de la pieza madre (por defecto, la de data/url.txt)")
    parser.add_argument("--backup", default=None,
                        help="HTML de respaldo si la URL falla (ej. data/guia_rpa_respaldo.html)")
    parser.add_argument("--config", default=DATA_DIR / "config.json")
    parser.add_argument("--window", default=DATA_DIR / "ventana.json")
    parser.add_argument("--occupied", default=DATA_DIR / "calendario_ocupado.csv")
    parser.add_argument("--history", default=DATA_DIR / "historial_publicaciones.csv")
    parser.add_argument("--output", default=PROJECT_DIR / "output")
    return parser.parse_args()


def save_json(data, path):
    """Guarda datos en JSON legible (con tildes, sin escapar)."""
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def pieces_markdown(pieces):
    """Versión en Markdown de la cola de aprobación, fácil de leer para Mercadeo."""
    lines = ["# Cola de aprobación\n"]
    for piece in pieces:
        lines.append(f"## {piece['id']} — {piece['estado']}\n")
        lines.append(f"- Programada: {piece.get('programada', 'no ubicada')}")
        lines.append(f"- Puntaje: {piece['puntaje']} ({piece['semaforo']}) — {piece['explicacion_puntaje']}")
        lines.append(f"- Problemas: {', '.join(piece['problemas']) or 'ninguno'}\n")
        lines.append(piece["texto"] + "\n")
    return "\n".join(lines)


def run(args):
    """Ejecuta el sistema completo y devuelve un resumen."""
    config = load_config(args.config)
    window = load_json(args.window)
    url = args.url or (DATA_DIR / "url.txt").read_text(encoding="utf-8").strip()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    # 1. Historial: se limpia en memoria (el archivo original no se toca)
    history, cleaning_report = scoring.load_history(args.history)
    model = scoring.build_model(history)

    # 2. Diagnóstico de la pieza madre
    diagnosis, document = diagnose(url, config, args.backup, known_topics=sorted(history["tema"].unique()))

    # 3. Transformación: el mes de campaña (aaaamm) se toma del inicio de la ventana
    campaign_month = window["inicio"][:7].replace("-", "")
    pieces, skipped = transform(document, diagnosis, config, campaign_month)

    # 4. Puntaje preliminar (sin hora) para decidir qué pieza toma primero el calendario
    for piece in pieces:
        piece["puntaje"], piece["explicacion_puntaje"] = scoring.score_piece(piece, model)

    # 5. Calendario: lo ya agendado cuenta; las piezas con problemas también se ubican
    #    (quedan marcadas "requiere_revision" para que la persona decida)
    occupied = load_occupied(args.occupied)
    calendar, unplaced = schedule(pieces, window, occupied, config)
    conflicts = find_conflicts(calendar, config)

    # 6. Puntaje final con la hora real asignada
    slots = {entry["pieza_id"]: entry["inicio"] for entry in calendar if not entry["ya_agendada"]}
    for piece in pieces:
        moment = slots.get(piece["id"])
        hour = f"{moment:%H:%M}" if moment else None
        piece["programada"] = f"{moment:%Y-%m-%d %H:%M}" if moment else None
        piece["puntaje"], piece["explicacion_puntaje"] = scoring.score_piece(piece, model, hour)
        piece["semaforo"] = scoring.traffic_light(piece["puntaje"])

    # 7. Archivos de salida
    save_json(diagnosis, output / "diagnostico.json")
    save_json(pieces, output / "piezas.json")
    (output / "piezas.md").write_text(pieces_markdown(pieces), encoding="utf-8")
    save_json({"calendario": calendar, "no_ubicadas": unplaced, "conflictos": conflicts},
              output / "calendario.json")
    summary = {"limpieza_historial": cleaning_report,
               "tasa_mediana_por_formato": scoring.format_summary(history),
               "formatos_no_generados": skipped}
    save_json(summary, output / "resumen.json")
    (output / "calendario.html").write_text(
        render_calendar(window, calendar, pieces, unplaced, conflicts, diagnosis, skipped, config), encoding="utf-8")
    return summary, pieces, unplaced, conflicts, diagnosis


def main():
    args = parse_args()
    summary, pieces, unplaced, conflicts, diagnosis = run(args)
    print(f"Pieza madre: {diagnosis['titulo']} (origen: {diagnosis['origen_contenido']})")
    print(f"Alertas: {len(diagnosis['alertas_reglas'])} de reglas, {len(diagnosis['alertas_calidad'])} de calidad")
    for piece in pieces:
        print(f"  {piece['id']:<22} {piece['estado']:<22} {piece['programada'] or 'NO UBICADA':<17} "
              f"puntaje {piece['puntaje']} ({piece['semaforo']})")
    for item in unplaced:
        print(f"  No ubicada: {item['pieza_id']} -> {item['motivo']}")
    print(f"Conflictos: {len(conflicts)}")
    print(f"Resultados en: {args.output}/ (abre calendario.html en el navegador)")


if __name__ == "__main__":
    main()
