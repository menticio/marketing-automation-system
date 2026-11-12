# Sistema de Automatización de Marketing

Sistema automatizado para transformación de contenido, programación y predicción de éxito para equipos de marketing.

## Descripción General

Este sistema automatiza el flujo de trabajo táctico de contenido de marketing:
1. **Diagnostica** el contenido fuente (pieza madre) en cuanto a calidad y viabilidad
2. **Transforma** el contenido en múltiples formatos (posts de LinkedIn, carruseles, newsletters)
3. **Programa** el contenido en un calendario con detección de conflictos
4. **Predice** puntajes de éxito basados en datos históricos

## Stack Tecnológico

- **Lenguaje:** Python 3.14
- **Web Scraping:** requests, BeautifulSoup
- **Procesamiento de Datos:** pandas
- **Motor de Plantillas:** Jinja2
- **Testing:** pytest
- **Integración IA:** Google Gemini (gratuito)

## Estructura del Proyecto

```
marketing-automation-system/
├── data/                    # Archivos de entrada
│   ├── config.json         # Reglas de negocio y especificaciones de formatos
│   ├── ventana.json        # Fechas de ventana del calendario
│   ├── calendario_ocupado.csv  # Contenido ya programado
│   └── historial_publicaciones.csv  # Datos históricos de publicaciones
├── src/                    # Código fuente
│   ├── diagnosis.py        # Módulo de análisis de contenido
│   ├── transformation.py   # Módulo de transformación de formatos
│   ├── scheduler.py        # Módulo de programación de calendario
│   └── scoring.py          # Módulo de predicción de éxito
├── tests/                  # Pruebas automatizadas
├── templates/              # Plantillas HTML
├── output/                 # Resultados generados
└── main.py                # Orquestador principal

```

## Instalación

1. Clonar el repositorio:
```bash
git clone <url-de-tu-repo>
cd marketing-automation-system
```

2. Crear y activar entorno virtual:
```bash
python3 -m venv venv
source venv/bin/activate  # En Linux/Mac
# o
venv\Scripts\activate  # En Windows
```

3. Instalar dependencias:
```bash
pip install -r requirements.txt
```

## Uso

Ejecutar el sistema completo:
```bash
python main.py --url https://trycore.com/guia-de-automatizacion-con-rpa/
```

Ejecutar módulos individuales:
```bash
# Solo diagnóstico
python -m src.diagnosis --url <url-del-contenido>

# Ejecutar pruebas
pytest tests/
```

## Archivos de Salida

Después de la ejecución, revisar el directorio `output/`:
- `diagnosis.json` - Resultados del análisis de contenido
- `derived_pieces.json` - Contenido transformado para cada formato
- `calendar.json` - Datos de publicación programada
- `calendar.html` - Vista visual del calendario (abrir en navegador)
- `scores.json` - Predicciones de éxito con metodología

## Configuración

Todas las reglas de negocio están en `data/config.json`:
- Productos válidos
- Términos prohibidos
- Nombres de clientes confidenciales
- Convenciones UTM
- Especificaciones de formatos (longitud, estructura, técnicas)
- Reglas de calendario (días hábiles, franjas horarias, capacidad)

Para actualizar reglas, editar `config.json` - no se necesitan cambios en el código.

## Pruebas

Ejecutar pruebas automatizadas:
```bash
pytest tests/ -v
```

Las pruebas cubren:
- Validación de reglas (términos prohibidos, nombres confidenciales)
- Restricciones de formatos (longitud, estructura)
- Lógica del calendario (conflictos, capacidad, separación por tema)
- Cálculo de puntajes
- Manejo de errores

## Desarrollo

Decisiones clave de diseño:
- **Arquitectura modular:** Cada módulo es independiente y testeable
- **Dirigido por configuración:** Las reglas de negocio viven en JSON, no en código
- **IA con validación:** La IA genera contenido, el código valida reglas
- **Programación defensiva:** Maneja datos sucios (fechas inconsistentes, formatos variados)

## Licencia

Este es un proyecto de reto técnico con fines de evaluación.

## Autor

Maicol - Reto Técnico para Trycore

