# scheduler.py
# Agente de calendario: ubica las piezas derivadas dentro de la ventana de dos
# semanas sin romper ninguna regla del calendario de config.json:
#   - solo días hábiles y que no sean festivos
#   - solo en las franjas de publicación
#   - máximo N piezas por día y M por semana (contando lo que ya estaba agendado)
#   - máximo de piezas por semana de cada formato (ficha del formato)
#   - separación mínima en horas entre piezas del mismo tema
#
# Algoritmo: "voraz" (greedy). Se ordenan las piezas de mayor a menor puntaje y cada
# una toma la primera franja libre que cumpla todas las reglas. Si no cabe en
# ninguna, queda en la lista de "no ubicadas" con el motivo más frecuente.

import csv
from collections import Counter
from datetime import date, datetime, timedelta

# Nombres de los días como aparecen en config.json (lunes = 0 en Python)
WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def load_occupied(path):
    """Lee calendario_ocupado.csv y devuelve una entrada por publicación ya agendada."""
    with open(path, encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    return [{"inicio": datetime.fromisoformat(f"{row['fecha']} {row['hora']}"),
             "formato": row["formato"], "tema": row["tema"], "titulo": row["titulo"],
             "canal": row["canal"], "estado": row["estado"], "ya_agendada": True}
            for row in rows]


def holidays(calendar_rules):
    """Conjunto de fechas festivas (para buscar rápido si un día es festivo)."""
    return {date.fromisoformat(h["fecha"]) for h in calendar_rules["festivos"]}


def is_working_day(day, calendar_rules):
    """True si el día es hábil (según config.json) y no es festivo."""
    return WEEKDAYS[day.weekday()] in calendar_rules["dias_habiles"] and day not in holidays(calendar_rules)


def build_slots(window, calendar_rules):
    """Todas las franjas posibles de la ventana, en orden cronológico."""
    start, end = date.fromisoformat(window["inicio"]), date.fromisoformat(window["fin"])
    slots = []
    day = start
    while day <= end:
        if is_working_day(day, calendar_rules):
            for hour in calendar_rules["franjas_de_publicacion"]:
                slots.append(datetime.fromisoformat(f"{day.isoformat()} {hour}"))
        day += timedelta(days=1)
    return slots


def _week(moment):
    """Identificador de la semana (año ISO, número de semana): lunes a domingo."""
    return moment.isocalendar()[:2]


def check_slot(slot, piece, calendar, calendar_rules, max_per_week_format):
    """Revisa si la pieza puede ir en esa franja. Devuelve None si sí, o el motivo si no."""
    if any(entry["inicio"] == slot for entry in calendar):
        return "franja ya ocupada"
    same_day = [e for e in calendar if e["inicio"].date() == slot.date()]
    if len(same_day) >= calendar_rules["capacidad_max_por_dia"]:
        return "día lleno (capacidad por día)"
    same_week = [e for e in calendar if _week(e["inicio"]) == _week(slot)]
    if len(same_week) >= calendar_rules["capacidad_max_por_semana"]:
        return "semana llena (capacidad por semana)"
    same_format = [e for e in same_week if e["formato"] == piece["formato"]]
    if len(same_format) >= max_per_week_format:
        return f"máximo de {piece['formato']} por semana alcanzado"
    min_gap = timedelta(hours=calendar_rules["separacion_minima_mismo_tema_horas"])
    for entry in calendar:
        if entry["tema"] == piece["tema"] and abs(entry["inicio"] - slot) < min_gap:
            return f"menos de {calendar_rules['separacion_minima_mismo_tema_horas']} h de otra pieza del tema '{piece['tema']}'"
    return None


def schedule(pieces, window, occupied, config):
    """Programa las piezas. Devuelve (calendario completo, piezas no ubicadas)."""
    calendar_rules = config["calendario"]
    max_per_week = {fmt["id"]: fmt.get("max_por_semana", 99) for fmt in config["matriz_formatos"]}
    calendar = list(occupied)  # lo ya agendado cuenta para capacidad y separación
    slots = build_slots(window, calendar_rules)
    unplaced = []

    # Primero las piezas con mejor puntaje; las que no tienen puntaje van al final
    ordered = sorted(pieces, key=lambda p: -1 if p.get("puntaje") is None else p["puntaje"], reverse=True)

    for piece in ordered:
        reasons = Counter()
        for slot in slots:
            reason = check_slot(slot, piece, calendar, calendar_rules, max_per_week[piece["formato"]])
            if reason is None:
                calendar.append({"inicio": slot, "formato": piece["formato"], "tema": piece["tema"],
                                 "titulo": piece["titulo"], "canal": piece["canal"], "pieza_id": piece["id"],
                                 "estado": "programada_pendiente_aprobacion", "ya_agendada": False})
                break
            reasons[reason] += 1
        else:
            # El "else" de un for se ejecuta si el ciclo terminó sin "break": no hubo franja
            main_reason = reasons.most_common(1)[0][0] if reasons else "no hay franjas en la ventana"
            unplaced.append({"pieza_id": piece["id"], "formato": piece["formato"], "motivo": main_reason})

    calendar.sort(key=lambda entry: entry["inicio"])
    return calendar, unplaced


def find_conflicts(calendar, config):
    """Revisa un calendario completo y lista cualquier regla rota (control final).

    Se usa para revisar lo que YA venía agendado y también lo que programó el sistema.
    """
    calendar_rules = config["calendario"]
    max_per_week = {fmt["id"]: fmt.get("max_por_semana", 99) for fmt in config["matriz_formatos"]}
    min_gap = timedelta(hours=calendar_rules["separacion_minima_mismo_tema_horas"])
    conflicts = []

    for entry in calendar:
        label = f"{entry['inicio']:%Y-%m-%d %H:%M} {entry['formato']}"
        if not is_working_day(entry["inicio"].date(), calendar_rules):
            conflicts.append(f"{label}: día no hábil o festivo")
        if f"{entry['inicio']:%H:%M}" not in calendar_rules["franjas_de_publicacion"]:
            conflicts.append(f"{label}: fuera de las franjas de publicación")

    # Separación por tema: se compara cada pareja de piezas una sola vez
    for i, first in enumerate(calendar):
        for second in calendar[i + 1:]:
            if first["tema"] == second["tema"] and abs(first["inicio"] - second["inicio"]) < min_gap:
                conflicts.append(f"{first['inicio']:%Y-%m-%d %H:%M} y {second['inicio']:%Y-%m-%d %H:%M}: "
                                 f"mismo tema '{first['tema']}' a menos de {min_gap.days * 24} h")

    # Capacidad por día, por semana y por formato en la semana
    per_day = Counter(e["inicio"].date() for e in calendar)
    per_week = Counter(_week(e["inicio"]) for e in calendar)
    per_week_format = Counter((_week(e["inicio"]), e["formato"]) for e in calendar)
    conflicts += [f"{day}: {n} piezas (máximo {calendar_rules['capacidad_max_por_dia']} por día)"
                  for day, n in per_day.items() if n > calendar_rules["capacidad_max_por_dia"]]
    conflicts += [f"semana {week[1]}: {n} piezas (máximo {calendar_rules['capacidad_max_por_semana']})"
                  for week, n in per_week.items() if n > calendar_rules["capacidad_max_por_semana"]]
    conflicts += [f"semana {week[1]}: {n} de {fmt} (máximo {max_per_week.get(fmt, 99)})"
                  for (week, fmt), n in per_week_format.items() if n > max_per_week.get(fmt, 99)]
    return conflicts
