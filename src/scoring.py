# scoring.py
# Agente de puntaje: estima de 0 a 100 qué tan probable es que una pieza funcione,
# usando el historial de publicaciones TAL COMO VIENE (fechas en varios formatos,
# decimales con coma, celdas vacías y filas repetidas). La limpieza la hace el código.
#
# Cómo se calcula (explicable en una frase):
#   1. Se toma la tasa de interacción mediana de todo el historial (la "base").
#   2. Para cada característica de la pieza (formato, tema, si tiene cifra, hora)
#      se mira cuánto se aleja de la base la mediana de las publicaciones parecidas.
#   3. Esas diferencias se suman a la base: es la tasa esperada de la pieza.
#   4. El puntaje es el percentil de esa tasa frente al historial: 70 significa
#      "se espera que le vaya mejor que al 70 % de lo publicado".
# Se usa la mediana (no el promedio) para que un post viral no distorsione todo.

import re
from datetime import date, datetime

import pandas as pd

# Meses abreviados en español, para fechas como "17-mar-2026"
SPANISH_MONTHS = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
                  "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12}

# Cuántas publicaciones "pesa" la base frente a un grupo pequeño (suavizado).
# Con pocos datos de un grupo, su efecto se acerca a cero en vez de exagerarse.
SMOOTHING = 5

# Características que se usan para comparar
FACTORS = ["formato", "tema", "tiene_cifra", "hora"]


# ---------------------------------------------------------------------------
# Limpieza de los datos sucios
# ---------------------------------------------------------------------------

def parse_date(value):
    """Convierte '2026-03-05', '16/03/2026' o '17-mar-2026' en una fecha. None si no se puede."""
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip().lower()
    for pattern in ("%Y-%m-%d", "%d/%m/%Y"):  # formato ISO y formato colombiano día/mes/año
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            pass
    match = re.fullmatch(r"(\d{1,2})-([a-z]{3})-(\d{4})", value)
    if match and match.group(2) in SPANISH_MONTHS:
        return date(int(match.group(3)), SPANISH_MONTHS[match.group(2)], int(match.group(1)))
    return None


def parse_decimal(value):
    """Convierte '0,0338' (coma decimal) en 0.0338. None si la celda está vacía."""
    if not isinstance(value, str) or not value.strip():
        return None
    return float(value.strip().replace(",", "."))


def parse_bool(value):
    """Convierte '1', 'sí', 'Si', 'si' en True y '0', 'no', 'No' en False."""
    text = str(value).strip().lower().replace("í", "i")
    if text in ("1", "si", "true"):
        return True
    if text in ("0", "no", "false"):
        return False
    return None


def load_history(path):
    """Lee el CSV del historial y devuelve (tabla limpia, reporte de limpieza)."""
    raw = pd.read_csv(path, dtype=str)  # todo como texto: nosotros decidimos cómo convertir
    report = {"filas_leidas": len(raw)}

    # Filas repetidas exactas (misma publicación dos veces): se quedan una sola vez
    data = raw.drop_duplicates().copy()
    report["filas_repetidas_eliminadas"] = len(raw) - len(data)

    data["fecha"] = data["fecha"].apply(parse_date)
    data["tiene_cifra"] = data["tiene_cifra"].apply(parse_bool)
    for column in ["impresiones", "reacciones", "comentarios", "clics"]:
        data[column] = pd.to_numeric(data[column], errors="coerce")  # vacío -> NaN
    data["tasa"] = data["tasa_interaccion"].apply(parse_decimal)

    # Si falta la tasa, se recalcula con su fórmula: (reacciones + comentarios + clics) / impresiones
    # (se verificó con las filas completas: P001 -> (29 + 4 + 14) / 1390 = 0,0338)
    missing = data["tasa"].isna()
    interactions = data[["reacciones", "comentarios", "clics"]].sum(axis=1, min_count=3)
    data.loc[missing, "tasa"] = interactions[missing] / data.loc[missing, "impresiones"]
    report["tasas_recalculadas"] = int((missing & data["tasa"].notna()).sum())

    report["fechas_sin_formato_valido"] = int(data["fecha"].isna().sum())
    report["celdas_vacias_comentarios"] = int(data["comentarios"].isna().sum())
    data = data[data["tasa"].notna()]
    report["filas_usadas"] = len(data)
    return data, report


# ---------------------------------------------------------------------------
# Modelo de puntaje
# ---------------------------------------------------------------------------

def build_model(history):
    """Calcula la base y el efecto de cada característica a partir del historial."""
    base = history["tasa"].median()
    effects = {}
    for factor in FACTORS:
        effects[factor] = {}
        for value, group in history.groupby(factor):
            n = len(group)
            # Suavizado: con n publicaciones el grupo pesa n / (n + SMOOTHING)
            effects[factor][value] = (group["tasa"].median() - base) * n / (n + SMOOTHING)
    return {"base": base, "efectos": effects, "tasas": sorted(history["tasa"].tolist())}


def score_piece(piece, model, hour=None):
    """Devuelve (puntaje 0-100 o None, explicación). None = no hay datos para decidir."""
    effects = model["efectos"]
    if piece["formato"] not in effects["formato"]:
        # Regla de Mercadeo: no inventar. Sin historial del formato, no hay puntaje.
        return None, f"Sin historial para el formato '{piece['formato']}': no se calcula puntaje"

    values = {"formato": piece["formato"], "tema": piece["tema"],
              "tiene_cifra": piece["tiene_cifra"], "hora": hour}
    expected = model["base"]
    explanation = [f"base {model['base']:.2%}"]
    for factor, value in values.items():
        effect = effects[factor].get(value)
        if effect is None:
            continue  # valor sin historial (ej. hora aún no asignada): no suma ni resta
        expected += effect
        explanation.append(f"{factor}={value}: {effect:+.2%}")

    # Percentil: qué fracción del historial queda por debajo de la tasa esperada
    rates = model["tasas"]
    below = sum(1 for rate in rates if rate < expected)
    score = round(100 * below / len(rates))
    return score, f"tasa esperada {expected:.2%} ({', '.join(explanation)})"


def traffic_light(score):
    """Semáforo que pidió Mercadeo: verde, amarillo, rojo o gris (sin datos)."""
    if score is None:
        return "gris"
    return "verde" if score >= 66 else "amarillo" if score >= 33 else "rojo"


def format_summary(history):
    """Tasa mediana por formato: responde si "los carruseles siempre funcionan mejor"."""
    table = history.groupby("formato")["tasa"].agg(["median", "count"]).sort_values("median", ascending=False)
    return {fmt: {"tasa_mediana": round(float(row["median"]), 4), "publicaciones": int(row["count"])}
            for fmt, row in table.iterrows()}
