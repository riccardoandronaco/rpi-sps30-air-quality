"""
db.py - SQLite storage for air quality readings
Database file: data/air_quality.db (relative to project root)
"""
import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default DB path: project_root/data/air_quality.db
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "air_quality.db"


class Database:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        """Create tables and indexes if they don't exist."""
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS readings (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT NOT NULL,
                    pm1p0       REAL NOT NULL,
                    pm2p5       REAL NOT NULL,
                    pm4p0       REAL NOT NULL,
                    pm10p0      REAL NOT NULL,
                    nc0p5       REAL NOT NULL,
                    nc1p0       REAL NOT NULL,
                    nc2p5       REAL NOT NULL,
                    nc4p0       REAL NOT NULL,
                    nc10p0      REAL NOT NULL,
                    typical_size REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_readings_timestamp
                ON readings(timestamp)
            """)
            conn.commit()
        logger.info("Database ready at %s", self.db_path)

    def insert(self, reading, timestamp: Optional[str] = None) -> int:
        """Insert a reading. Returns the new row id."""
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        data = reading.to_dict()
        with self._get_conn() as conn:
            cursor = conn.execute("""
                INSERT INTO readings
                  (timestamp, pm1p0, pm2p5, pm4p0, pm10p0,
                   nc0p5, nc1p0, nc2p5, nc4p0, nc10p0, typical_size)
                VALUES
                  (:ts, :pm1p0, :pm2p5, :pm4p0, :pm10p0,
                   :nc0p5, :nc1p0, :nc2p5, :nc4p0, :nc10p0, :typical_size)
            """, {**data, "ts": ts})
            conn.commit()
            return cursor.lastrowid

    def query(self, range_hours: int = 24, limit: int = 10000) -> list[dict]:
        """Fetch readings from the last `range_hours` hours."""
        since = f"datetime('now', '-{range_hours} hours')"
        with self._get_conn() as conn:
            rows = conn.execute(f"""
                SELECT * FROM readings
                WHERE timestamp >= {since}
                ORDER BY timestamp ASC
                LIMIT {limit}
            """).fetchall()
        return [dict(r) for r in rows]

    def query_aggregated(self, range_hours: int, bucket_minutes: int) -> list[dict]:
        """
        Return time-bucketed averages (useful for week/month views).
        Uses SQLite strftime for bucketing.
        """
        since = f"datetime('now', '-{range_hours} hours')"
        # e.g., bucket_minutes=60 -> hourly averages
        with self._get_conn() as conn:
            rows = conn.execute(f"""
                SELECT
                    strftime('%Y-%m-%dT%H:%M:00', timestamp,
                        'unixepoch',
                        '+{bucket_minutes - (bucket_minutes % bucket_minutes)} minutes')
                        AS bucket,
                    AVG(pm1p0)  AS pm1p0,
                    AVG(pm2p5)  AS pm2p5,
                    AVG(pm4p0)  AS pm4p0,
                    AVG(pm10p0) AS pm10p0,
                    AVG(typical_size) AS typical_size
                FROM readings
                WHERE timestamp >= {since}
                GROUP BY strftime('%Y-%m-%dT%H:{"{:02d}".format(0)}:00',
                    datetime(timestamp, 'unixepoch',
                    CAST(CAST(strftime('%M', timestamp) AS INTEGER) / {bucket_minutes} AS INTEGER) * {bucket_minutes} || ' minutes'))
                ORDER BY bucket ASC
            """).fetchall()
        return [dict(r) for r in rows]

    def query_aggregated_simple(self, range_hours: int, bucket_minutes: int) -> list[dict]:
        """
        Simpler aggregation using epoch bucketing.
        """
        since = f"datetime('now', '-{range_hours} hours')"
        bucket_seconds = bucket_minutes * 60
        with self._get_conn() as conn:
            rows = conn.execute(f"""
                SELECT
                    datetime(
                        CAST(strftime('%s', timestamp) AS INTEGER) / {bucket_seconds} * {bucket_seconds},
                        'unixepoch'
                    ) AS bucket,
                    ROUND(AVG(pm1p0),  2) AS pm1p0,
                    ROUND(AVG(pm2p5),  2) AS pm2p5,
                    ROUND(AVG(pm4p0),  2) AS pm4p0,
                    ROUND(AVG(pm10p0), 2) AS pm10p0,
                    ROUND(AVG(typical_size), 2) AS typical_size
                FROM readings
                WHERE timestamp >= {since}
                GROUP BY bucket
                ORDER BY bucket ASC
            """).fetchall()
        return [dict(r) for r in rows]

    def get_latest(self) -> Optional[dict]:
        """Return the most recent reading."""
        with self._get_conn() as conn:
            row = conn.execute("""
                SELECT * FROM readings ORDER BY timestamp DESC LIMIT 1
            """).fetchone()
        return dict(row) if row else None

    def count(self) -> int:
        with self._get_conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0]

