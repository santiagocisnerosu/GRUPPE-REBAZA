# Receipts

Receipts convierte las noticias del día en un boletín de audio para cada oyente.
Cada cifra pronunciada se verifica contra las fuentes y aparece en un ticket con enlaces.

## Pipeline

| Paso | Comando | Resultado |
|---|---|---|
| 1 | `python -m src.ingest` | Normaliza los archivos locales de Newstex. |
| 2 | `python -m src.extract` | Extrae resúmenes y cifras candidatas con evidencia. |
| 3 | `python -m src.verify` | Contrasta cada cifra con su fuente. |
| 4 | `python -m src.cluster` | Agrupa artículos y separa eventos distintos. |
| 5 | `python -m src.script` | Aplica los perfiles y controles, y registra las discrepancias. |
| 6 | `python -m src.audio` | Genera audio con marcas de tiempo y transcripciones. |
| 7 | `python -m src.cost_report` | Calcula el costo observado y las proyecciones. |
| 8 | `python -m src.publish_site` | Revisa la narración y empaqueta la demo y su QR. |

## Ver la demo

La demo incluida en `docs/` se puede reproducir sin claves ni el dataset. Desde la raíz:

```sh
python -m http.server 8000
```

Abre [la demo local](http://localhost:8000/docs/). La [URL del jurado](https://santiagocisnerosu.github.io/GRUPPE-REBAZA/) funciona cuando GitHub Pages está desplegado desde `main` y la carpeta `/docs`.

## Regenerar

Usa Python 3.11 o posterior, instala `requirements.txt`, coloca los archivos autorizados en `data/raw/` y configura `.env` con las claves y modelos de OpenAI y ElevenLabs. Guarda el número de líneas de `data/cache/costs.jsonl` antes de empezar para sustituir `N` en el reporte de costos. Usa cero si el registro todavía no existe.

```sh
python -m pip install -r requirements.txt
python -m src.ingest
python -m src.extract --date 2026-11-18 --overnight
python -m src.verify --date 2026-11-18 --overnight
python -m src.cluster --date 2026-11-18 --threshold 0.45 --overnight
python -m src.script --date 2026-11-18 --overnight --listener all --regenerate
python -m src.audio --listener all
python -m src.cost_report --since-record N
python -m src.publish_site
```

## Costos de la demo en USD

| Scenario | With segment cache | Without segment cache |
|---|---:|---:|
| This run (recorded API usage; lower bound) | $1.8544 | $1.8544 |
| Full dataset (1,740 articles, one day, three profile versions) | $12.3457 | $12.3457 |
| 10x (17,400 articles, one day, three profile versions) | $111.6957 | $111.6957 |
| Per listener per month at 10,000 listeners | $0.8958 | $8.0846 |
| 10,000 listeners per month | $8,957.7933 | $80,846.2203 |

Proyecciones con las tarifas de `prices.yaml`, 30 días al mes y un reparto uniforme de las tres voces. El costo de la corrida mostrada es un mínimo observado porque una línea del registro era ilegible. La reutilización de segmentos es un escenario estimado.

## Licencia de los datos

Los datos y textos de Newstex no se incluyen por licencia. La demo distribuye únicamente sus propios guiones, audios y metadatos de atribución.
