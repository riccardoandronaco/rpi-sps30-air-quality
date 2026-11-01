"""
api/main.py - FastAPI REST backend for air quality data.
Run:
    uvicorn api.main:app --host 0.0.0.0 --port 8000
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Literal

# Load .env from project root
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

from fastapi import FastAPI, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from collector.db import Database

app = FastAPI(
    title="SPS30 Air Quality API",
    description="REST API for Raspberry Pi SPS30 particulate matter monitor",
    version="1.0.0",
)

DB_PATH = os.getenv("DB_PATH", "")
_db = Database(Path(DB_PATH)) if DB_PATH else Database()

# ── Range presets ──────────────────────────────────────────────────────────────
RANGE_MAP = {
    "day":   (24,   5),    # last 24h,  5-minute buckets
    "week":  (24*7, 60),   # last 7d,   1-hour buckets
    "month": (24*30, 360), # last 30d,  6-hour buckets
}


@app.get("/api/health")
def health():
    """Liveness check."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_readings": _db.count(),
    }


@app.get("/api/latest")
def latest():
    """Return the most recent reading."""
    reading = _db.get_latest()
    if not reading:
        raise HTTPException(status_code=404, detail="No readings available yet")
    return reading


@app.get("/api/data")
def get_data(
    range: Literal["day", "week", "month"] = Query("day", description="Time range to fetch"),
    raw: bool = Query(False, description="Return raw readings instead of aggregated buckets"),
):
    """
    Fetch air quality data for the given time range.
    - day   → last 24h (raw or 5-min buckets)
    - week  → last 7d  (hourly buckets)
    - month → last 30d (6-hour buckets)
    """
    range_hours, bucket_minutes = RANGE_MAP[range]

    if raw or range == "day":
        data = _db.query(range_hours=range_hours)
    else:
        data = _db.query_aggregated_simple(range_hours=range_hours, bucket_minutes=bucket_minutes)

    return {
        "range": range,
        "bucket_minutes": bucket_minutes,
        "count": len(data),
        "data": data,
    }


@app.get("/api/stats")
def get_stats(range: Literal["day", "week", "month"] = Query("day")):
    """Return min/max/avg statistics for the selected range."""
    range_hours, _ = RANGE_MAP[range]
    rows = _db.query(range_hours=range_hours)
    if not rows:
        return {"range": range, "count": 0, "stats": {}}

    def stat(key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        if not vals:
            return {}
        return {
            "min": round(min(vals), 2),
            "max": round(max(vals), 2),
            "avg": round(sum(vals) / len(vals), 2),
        }

    return {
        "range": range,
        "count": len(rows),
        "stats": {
            "pm1p0":  stat("pm1p0"),
            "pm2p5":  stat("pm2p5"),
            "pm4p0":  stat("pm4p0"),
            "pm10p0": stat("pm10p0"),
            "typical_size": stat("typical_size"),
        },
    }


# Serve the web dashboard as static files
_web_dir = Path(__file__).resolve().parent.parent / "web"
if _web_dir.exists():
    app.mount("/", StaticFiles(directory=str(_web_dir), html=True), name="web")

