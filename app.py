"""
USDA Organic Integrity Ingredient Search
FastAPI backend + embedded HTML frontend

Run: python app.py
Then open: http://localhost:8000
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import database as db
import ingest
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
import uvicorn


def check_and_update():
    """Re-ingest if USDA has published a newer monthly file than what's loaded."""
    db.init_db()
    s = db.stats()

    loaded = s.get("data_date", "") or ""
    try:
        # loaded is stored as YYYYMMDD; parse it
        loaded_dt = datetime.strptime(loaded[:8], "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        loaded_dt = None

    try:
        latest_url, latest_date = ingest.latest_month_url()
        latest_dt = datetime.strptime(latest_date[:8], "%Y%m%d").replace(tzinfo=timezone.utc)
    except Exception as e:
        print(f"Could not check for updates: {e}")
        return

    if loaded_dt is None or latest_dt > loaded_dt:
        print(f"Newer data available ({latest_date}). Downloading and re-indexing…")
        from pathlib import Path as _Path
        xlsx_path = _Path(f"/tmp/INTEGRITY_Export_{latest_date}.xlsx")
        if not xlsx_path.exists():
            ingest.download(latest_url, xlsx_path)
        ingest.ingest(xlsx_path, latest_date)
    else:
        print(f"✓ Data is current ({loaded}). No update needed.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    check_and_update()
    s = db.stats()
    print(f"✓ {s['total_operations']:,} operations indexed (data: {s['data_date']})")
    yield


app = FastAPI(title="USDA Organic Integrity Search", lifespan=lifespan)

HTML = (Path(__file__).parent / "templates" / "index.html").read_text()


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML


@app.get("/api/search")
def search(q: str = Query(..., min_length=1), limit: int = Query(200, ge=1, le=500)):
    results = db.search_ingredient(q, limit=limit)
    return {"query": q, "count": len(results), "results": results}


@app.get("/api/stats")
def stats():
    return db.stats()


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
