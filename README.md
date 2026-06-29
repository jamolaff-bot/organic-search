---
title: USDA Organic Integrity Ingredient Search
emoji: 🌿
colorFrom: green
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# USDA Organic Integrity — Ingredient Search

Search all 50,000+ USDA-certified organic operations by ingredient or product name. Data comes from the USDA's own monthly Excel snapshots — no scraping required.

## Setup

**Requirements:** Python 3.10+

```bash
# 1. Create a virtual environment
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Download and index the data (~2 min, one-time)
python ingest.py

# 4. Start the server
python app.py
```

Open **http://localhost:8000** in your browser.

## Updating the data

The USDA publishes new snapshots monthly. Re-run `python ingest.py` to refresh:

```bash
source venv/bin/activate
python ingest.py
```

You can also point at a specific month or a local file:

```bash
python ingest.py --date 20260401        # April 2026
python ingest.py --file /path/to/file.xlsx
```

## How it works

- `ingest.py` downloads `INTEGRITY_Export_YYYYMMDD.xlsx` from the USDA's Data History page, parses all operations and their certified product lists, and indexes them into a local SQLite database with full-text search (FTS5).
- `app.py` is a FastAPI server that searches the local database and serves the HTML frontend.
- Searches run entirely against the local SQLite cache — no network calls after ingestion.

## Docker

```bash
docker build -t organic-search .
docker run -p 8000:8000 organic-search
```

The container runs `ingest.py` automatically on first start, then launches the server.

## Data source

[USDA Organic Integrity Database — Data History](https://organic.ams.usda.gov/integrity/Reports/DataHistory)

Data is refreshed monthly by USDA. The search index covers all USDA-NOP certified operations worldwide.
