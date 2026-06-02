# TapadosPRI — Contexto para Claude

## Qué es este proyecto

Análisis de redes políticas del sistema del "tapado" en el PRI mexicano (1921–2000): cómo se seleccionaban secretamente los candidatos presidenciales. Compara las elecciones de 1988 y 1994 (ganador vs. perdedor).

Datos base: ~1,200 biógramas del libro *Mexican Political Biographies 1935–2009*.

## Arquitectura de carpetas

Este repo (`TapadosCode`) **solo contiene código**. Los datos, outputs y literatura viven en una carpeta separada de Dropbox:

```
~/Dropbox/TapadosPRI/     ← datos + outputs (Dropbox, NO en git)
  data/                   ← CSVs, parsed_positions.csv, etc.
  output/                 ← PNGs, HTML, visualizaciones
  literature/             ← PDFs de biografías y papers

~/Dropbox/TapadosCode/    ← este repo (git + GitHub)
  code/
    config.py             ← configuración central con rutas
    00-networks/00-preprocess/   ← pipeline ETL (01-05)
    03-descriptive_stats/        ← visualizaciones y stats (06-09)
```

## Configuración de rutas

Las rutas al Dropbox de datos se configuran via variable de entorno cargada automáticamente desde `.env` (gitignoreado):

```
TAPADOSPRI_DB_ROOT=/Users/joaquinbarrutia/Dropbox/TapadosPRI
```

Nunca hardcodear rutas absolutas — usar siempre las constantes de `config.py`:
`DATA_DIR`, `OUTPUT_DIR`, `LITERATURE_DIR`, `BIOGRAPHIES_DIR`.

## Pipeline numerado

| Archivo | Qué hace | Input → Output |
|---|---|---|
| `00-preprocess/01_extract_pdf.py` | Extrae texto del PDF de biografías (pdfplumber, dos columnas) | PDF → `biographies_full.txt` |
| `00-preprocess/02_parse_biographies.py` | Parsea texto en CSV estructurado con marcadores a–l | txt → `biographies.csv` |
| `00-preprocess/04_parse_positions.py` | Extrae estado/org/fechas/cargo de texto semi-estructurado | `biographies.csv` → `parsed_positions.csv` (15K+ filas) |
| `00-preprocess/05_*.py` | Un script por tipo de posición (education, govt, party, labor, public, birthplace, connections) | `parsed_positions.csv` → CSVs especializados |
| `03-descriptive_stats/viz_network.py` | Grafos de red: top conectados al candidato ganador vs. perdedor | CSVs → PNGs |
| `03-descriptive_stats/viz_geo_network.py` | Mapas geográficos por estado pre/post elección | CSVs + GeoJSON → PNGs |
| `03-descriptive_stats/viz_timeline.py` | Timeline Gantt: ubicación de tapados año a año | CSVs → PNGs |
| `03-descriptive_stats/viz_influence_map.py` | Mapa de influencia con gradiente temporal | CSVs → PNGs |

## Convenciones de código

- Todas las rutas van a través de `config.py` — nunca `Path(__file__).parent / "data"` ni rutas absolutas
- Scripts en subdirectorios añaden `CODE_DIR = Path(__file__).resolve().parents[2]` al `sys.path` para encontrar `config.py`
- Outputs siempre a `OUTPUT_DIR` de config, datos siempre de `DATA_DIR`
- El dataset principal es `parsed_positions.csv` (15K+ registros), no editar a mano

## Elecciones analizadas

- **1988**: Salinas de Gortari (ganador) vs. Bartlett Díaz (perdedor)
- **1994**: Colosio Murrieta (ganador) vs. Aspe Armella (perdedor)
- Candidatos definidos en `config.py` → `ELECTION_PAIRS` y `TAPADOS_1988`

## Colaboradores

- `ezagoc` (Emilio Zagoc) — Windows, `C:\Users\Dell\Dropbox\TapadosPRI`
- `quinoba` (Joaquín Barrutia) — Mac, `/Users/joaquinbarrutia/Dropbox/TapadosPRI`

Cada quien tiene su propio `.env` y `settings.local.json` (ambos gitignoreados).

## Workflow git

```bash
git pull origin master        # antes de empezar
# ... editar código ...
git add <archivos>
git commit -m "descripción"
git push origin master
```

Nunca hacer commit de: `.env`, `settings.local.json`, `__pycache__/`, `.pyc`, `.Rhistory`, `.DS_Store`.
