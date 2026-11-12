# Sistema de agentes para contenidos de Mercadeo

Toma una pieza madre (cualquier URL), la **diagnostica**, la **transforma** en piezas
redactadas por formato, las **programa** en un calendario de dos semanas sin conflictos,
les calcula un **puntaje de éxito** con el historial y lo muestra todo en una página web propia.
Nada se publica: todo queda en una **cola de aprobación** para que una persona decida.

> Caso ficticio del reto de Trycore. No se publica nada real.

## Cómo ejecutarlo

Requisitos: Python 3.12+ (probado con 3.14).

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Un solo comando (usa la URL de data/url.txt)
python -m src.main --backup data/guia_rpa_respaldo.html

# Con otra pieza madre
python -m src.main --url https://trycore.com/transformacion-digital/mitos-de-automatizacion-rpa/

# Pruebas automatizadas (20 casos)
python -m pytest -v
```

Resultados en `output/`:

| Archivo | Qué contiene |
|---|---|
| `calendario.html` | Vista semanal: piezas por día, color por formato, tema, estado, puntaje con semáforo, conflictos y piezas no ubicadas resaltadas, cola de aprobación y diagnóstico |
| `diagnostico.json` | Ficha de la pieza madre: indicadores, alertas y formatos viables |
| `piezas.json` / `piezas.md` | Cada pieza redactada por partes, con sus problemas de validación |
| `calendario.json` | Calendario completo, no ubicadas y conflictos |
| `resumen.json` | Limpieza del historial y tasa mediana por formato |

Parámetros opcionales: `--config`, `--window`, `--occupied`, `--history`, `--output`.
Todas las entradas son archivos: nada de la guía de RPA está escrito en el código.

## Diseño: un agente por responsabilidad

```
URL ──► [Diagnóstico] ──► [Transformación + Validación] ──► [Puntaje] ──► [Calendario] ──► [Vista web]
            │                       │                          │              │                │
       config.json            config.json                historial.csv   ventana.json      Persona:
       (reglas)              (fichas de formato)                         ocupado.csv     revisa y aprueba
```

| Módulo | Responsabilidad |
|---|---|
| `src/config.py` | Lee las entradas JSON (reglas y ventana) |
| `src/rules.py` | Reglas de negocio: términos prohibidos, nombres confidenciales, productos, slugs UTM |
| `src/diagnosis.py` | Descarga (con respaldo), extrae el contenido principal, indicadores, alertas, formatos viables, tema |
| `src/transform.py` | Redacta cada formato y valida la pieza contra su ficha y las reglas |
| `src/scoring.py` | Limpia el historial sucio y calcula el puntaje 0–100 |
| `src/scheduler.py` | Algoritmo de calendario y revisión de conflictos |
| `src/calendar_view.py` | Página HTML |
| `src/main.py` | Orquestador de un solo comando |

## Decisiones principales

**Diagnóstico (11 indicadores).** Palabras, secciones, listas, lista más larga, palabras por frase
(claridad), frases con cifras, cifras con fuente, títulos repetidos, secciones vacías, fecha de
publicación y antigüedad. Con la guía de RPA detecta: producto no vigente "Turbo RPA", frases
largas, título repetido, sección vacía, cifras sin fuente y contenido de 2023.

- "Llama" se busca respetando mayúsculas: "se llama" (verbo) no genera falsa alarma.
- La página tiene un `<main>` dentro de otro (barra lateral); se elimina para no mezclar texto.
- Si la URL falla, usa el respaldo y lo dice (`origen_contenido: backup`).

**Transformación extractiva, sin IA generativa en tiempo de ejecución.** Cada frase sale textual
de la pieza madre; el sistema elige, ordena y recorta para cumplir la ficha. Así no puede inventar
datos ("que el sistema no invente nada") y no depende de claves ni de servicios de pago. Además:

- descarta frases con términos prohibidos, nombres confidenciales o que solo enlazan a otro artículo;
- no usa listas de "mitos" o "errores" como láminas: fuera de contexto afirmarían lo contrario;
- cada pieza se valida contra su ficha (longitud, gancho, láminas, palabras por lámina, asunto,
  3 secciones, enlace UTM) y las reglas. El mejor estado posible es `pendiente_aprobacion`.

Formatos: post de LinkedIn, carrusel, newsletter y guion de video. Caso de éxito: no viable
(la guía no tiene testimonio). Infografía: viable, sin generador en esta versión.

**Calendario (algoritmo voraz).** Ordena las piezas por puntaje y cada una toma la primera franja
que cumpla: día hábil, no festivo, franja válida, capacidad por día y semana (contando lo ya
agendado), máximo por formato y semana, y 48 h entre piezas del mismo tema. Al final,
`find_conflicts` revisa todo el calendario como control independiente.

**Puntaje (0–100).** Base = tasa de interacción mediana del historial. Para formato, tema, si tiene
cifra y hora, se suma cuánto se aleja la mediana de ese grupo de la base (suavizado para grupos
pequeños). El puntaje es el percentil de esa tasa esperada en el historial: 53 = "se espera que
supere al 53 % de lo publicado". Se usa la mediana para que el post viral (P038, 55 mil
impresiones) no distorsione. Semáforo: verde ≥ 66, amarillo ≥ 33, rojo < 33.

Limpieza del historial (sin tocar el archivo): fechas en 3 formatos, coma decimal, sí/Si/1/No/0,
3 filas repetidas eliminadas, 1 tasa vacía recalculada con (reacciones + comentarios + clics) / impresiones.

## Hallazgos y preguntas para Mercadeo

- **"Publicar todos los días" choca con las reglas:** máximo 4 por semana y 48 h entre piezas del
  mismo tema. De una sola pieza madre caben 3 piezas en la ventana; el newsletter queda sin ubicar.
- **"Cerrar con el caso de Banco Andino del Sur"**: es un nombre confidencial. No se puede publicar.
- Los **ejemplos** de newsletter y guion en `config.json` usan términos prohibidos
  ("integración inmediata con cualquier ERP", "GPT"): no sirven como plantilla.
- **¿Los carruseles funcionan mejor?** Sí: mediana 4,78 % frente a 3,19 % de los posts.
- No hay historial de newsletters: su puntaje es "sin datos" en vez de un número inventado.
- Preguntas: ¿el mes del UTM es el de inicio de campaña o el de publicación? ¿la capacidad
  diaria incluye el newsletter (otro canal)? ¿quién revisa los guiones de video?

## Límites conocidos

- El puntaje es correlacional, con 60 publicaciones ficticias; suma efectos que pueden solaparse
  (por ejemplo, formato y cifra). No garantiza resultados.
- La redacción extractiva es fiel pero menos natural; el guion suena escrito, no hablado.
- La detección de productos no vigentes es una heurística sobre enlaces a páginas de servicios.
- Con más tiempo: redacción asistida por un LLM con la validación actual como filtro,
  generador de infografía, edición de reglas sin abrir el JSON y aprobación desde la página.

## Uso de IA

Usé un asistente de IA para analizar el reto, proponer el diseño y escribir parte del código.
Lo verifiqué ejecutándolo con la guía y con otras dos páginas, revisando las salidas y con
pruebas que fallan cuando se rompe una regla. Correcciones hechas al revisar: palabras partidas
por `<span>`, el `<main>` anidado, falsa alarma de "Llama", títulos de enlaces que se colaban
en el newsletter y textos de botones ("Conoce más") detectados como productos.
