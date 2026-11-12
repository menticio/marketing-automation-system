# calendar_view.py
# Genera la página web propia del sistema (un solo archivo HTML, sin internet ni
# librerías externas): vista semanal de la ventana, una tarjeta por pieza con su
# formato (por color), tema, estado y puntaje con semáforo; resalta los conflictos
# y las piezas que no se pudieron ubicar, y muestra la ficha de diagnóstico.

from datetime import date, timedelta
from html import escape   # Evita que un texto con "<" o ">" rompa la página

from src.scheduler import WEEKDAYS, holidays

# Un color por formato (si llega un formato nuevo, se usa gris)
FORMAT_COLORS = {
    "post_linkedin": "#2563eb", "carrusel_linkedin": "#16a34a", "newsletter": "#9333ea",
    "guion_video_corto": "#ea580c", "infografia": "#0891b2", "caso_de_exito": "#be123c",
}
LIGHT_COLORS = {"verde": "#16a34a", "amarillo": "#ca8a04", "rojo": "#dc2626", "gris": "#6b7280"}

STYLE = """
body{font-family:system-ui,sans-serif;margin:24px;color:#1f2937;background:#f9fafb}
h1{margin-bottom:4px} .muted{color:#6b7280}
.week{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:12px 0 28px}
.day{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:8px;min-height:150px}
.day.off{background:#f3f4f6;color:#9ca3af}
.day h3{margin:0 0 6px;font-size:14px}
.card{border-left:6px solid;border-radius:6px;background:#f8fafc;padding:6px 8px;margin-bottom:6px;font-size:13px}
.card.existing{opacity:.65;border-style:dashed}
.badge{display:inline-block;padding:1px 6px;border-radius:10px;color:#fff;font-size:11px}
.alert{background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:10px 14px;margin:8px 0}
.ok{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:10px 14px;margin:8px 0}
.legend span{margin-right:12px;font-size:13px}
details{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:8px 12px;margin:6px 0}
pre{white-space:pre-wrap;font-family:inherit}
table{border-collapse:collapse} td{padding:2px 10px 2px 0;font-size:14px}
"""


def _card(entry, pieces_by_id):
    """Tarjeta de una publicación dentro del día."""
    color = FORMAT_COLORS.get(entry["formato"], "#6b7280")
    piece = pieces_by_id.get(entry.get("pieza_id"))
    if piece is None:  # publicación que ya estaba en calendario_ocupado.csv
        return (f'<div class="card existing" style="border-color:{color}">'
                f'<b>{entry["inicio"]:%H:%M}</b> {escape(entry["formato"])}<br>'
                f'{escape(entry["titulo"])}<br><span class="muted">tema: {escape(entry["tema"])} · ya agendada</span></div>')
    light = piece["semaforo"]
    score = "sin datos" if piece["puntaje"] is None else piece["puntaje"]
    return (f'<div class="card" style="border-color:{color}">'
            f'<b>{entry["inicio"]:%H:%M}</b> {escape(piece["formato"])}<br>{escape(piece["titulo"])}<br>'
            f'<span class="muted">tema: {escape(piece["tema"])} · {escape(entry["estado"])}</span><br>'
            f'<span class="badge" style="background:{LIGHT_COLORS[light]}">puntaje {score}</span></div>')


def render_calendar(window, calendar, pieces, unplaced, conflicts, diagnosis, skipped, config):
    """Devuelve el HTML completo de la página."""
    pieces_by_id = {p["id"]: p for p in pieces}
    rules = config["calendario"]
    festive = holidays(rules)
    start, end = date.fromisoformat(window["inicio"]), date.fromisoformat(window["fin"])
    monday = start - timedelta(days=start.weekday())

    html = [f"<!DOCTYPE html><html lang='es'><head><meta charset='utf-8'>"
            f"<title>Calendario de contenidos</title><style>{STYLE}</style></head><body>",
            f"<h1>Calendario de contenidos</h1>",
            f"<p class='muted'>Pieza madre: <a href='{escape(diagnosis['url'])}'>{escape(diagnosis['titulo'])}</a> · "
            f"ventana {window['inicio']} a {window['fin']} · nada se publica sin aprobación de Mercadeo</p>",
            "<div class='legend'>" + "".join(
                f"<span><b style='color:{c}'>■</b> {f}</span>" for f, c in FORMAT_COLORS.items()) + "</div>"]

    # Conflictos y piezas no ubicadas, arriba y en rojo para que se vean primero
    if conflicts or unplaced:
        items = [f"<li>Conflicto: {escape(c)}</li>" for c in conflicts]
        items += [f"<li>No se pudo ubicar <b>{escape(u['pieza_id'])}</b>: {escape(u['motivo'])}</li>" for u in unplaced]
        html.append(f"<div class='alert'><b>Requiere decisión de una persona</b><ul>{''.join(items)}</ul></div>")
    else:
        html.append("<div class='ok'>Sin conflictos: todas las piezas quedaron ubicadas.</div>")

    # Una fila de 5 días (lunes a viernes) por cada semana de la ventana
    week_start = monday
    while week_start <= end:
        html.append(f"<h2>Semana del {week_start:%d/%m/%Y}</h2><div class='week'>")
        for offset in range(5):
            day = week_start + timedelta(days=offset)
            outside = not start <= day <= end
            off = outside or day in festive or WEEKDAYS[day.weekday()] not in rules["dias_habiles"]
            label = "festivo" if day in festive else "fuera de la ventana" if outside else ""
            cards = "".join(_card(e, pieces_by_id) for e in calendar if e["inicio"].date() == day)
            html.append(f"<div class='day{' off' if off else ''}'><h3>{WEEKDAYS[day.weekday()].capitalize()} "
                        f"{day:%d/%m} <span class='muted'>{label}</span></h3>{cards}</div>")
        html.append("</div>")
        week_start += timedelta(days=7)

    # Contenido de cada pieza (cola de aprobación)
    html.append("<h2>Cola de aprobación</h2>")
    for piece in pieces:
        problems = "".join(f"<li>{escape(p)}</li>" for p in piece["problemas"]) or "<li>Cumple su ficha y las reglas</li>"
        html.append(f"<details><summary><b>{escape(piece['id'])}</b> · {escape(piece['estado'])} · "
                    f"puntaje {piece['puntaje'] if piece['puntaje'] is not None else 'sin datos'}</summary>"
                    f"<p class='muted'>{escape(piece['explicacion_puntaje'])}</p><ul>{problems}</ul>"
                    f"<pre>{escape(piece['texto'])}</pre></details>")
    for item in skipped:
        html.append(f"<p class='muted'>Formato no generado: <b>{escape(item['formato'])}</b> — {escape(item['motivo'])}</p>")

    # Ficha de diagnóstico
    rows = "".join(f"<tr><td>{escape(k)}</td><td>{escape(str(v))}</td></tr>" for k, v in diagnosis["indicadores"].items())
    alerts = "".join(f"<li>{escape(a)}</li>" for a in diagnosis["alertas_reglas"] + diagnosis["alertas_calidad"])
    html.append(f"<h2>Diagnóstico de la pieza madre</h2><p>Origen del contenido: <b>{diagnosis['origen_contenido']}</b> · "
                f"tema detectado: <b>{escape(diagnosis['tema'])}</b></p><table>{rows}</table>"
                f"<h3>Alertas</h3><ul>{alerts or '<li>Sin alertas</li>'}</ul>")
    html.append("</body></html>")
    return "\n".join(html)
