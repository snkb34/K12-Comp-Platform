# K-12 Compensation Intelligence Platform

Production-style foundation for collecting, extracting, searching, and exporting K-12 compensation data.

## Render settings

Build Command:

```bash
pip install -r requirements.txt
```

Start Command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Environment variable:

```text
PYTHON_VERSION=3.12.7
```

## GitHub structure

Upload the contents of this folder so GitHub shows:

```text
app/
requirements.txt
render.yaml
Procfile
README.md
districts_template.csv
```

Do not upload the files inside `app/` separately. Keep the folder structure intact.

## Current capabilities

- District source management in browser
- CSV upload for sources
- Direct PDF/Excel/CSV downloader
- Basic HTML discovery for salary-related links
- PDF extraction using table extraction plus text fallback
- Excel/CSV extraction
- Search results
- CSV and Excel exports

## Known limitation

PDF salary schedules vary widely. The extractor will capture many salary-like rows but will still need district-specific parsing rules for perfect results.
