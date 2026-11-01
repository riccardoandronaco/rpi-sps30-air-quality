"""
scheduler.py - Main data collection loop for SPS30.
Run this as a systemd service or standalone:
    python -m collector.scheduler
"""
import logging
import os
import signal
import sys
import time
from pathlib import Path

# Load .env from project root (before reading os.getenv below)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass  # python-dotenv not installed, rely on environment variables

from collector.sensor import SPS30Sensor
from collector.db import Database
from alerts.telegram_bot import TelegramAlerter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Path(__file__).resolve().parent.parent / "data" / "collector.log"),
    ],
)
logger = logging.getLogger("scheduler")

# ── Configuration (overridable via environment variables) ──────────────────────
INTERVAL_SECONDS = int(os.getenv("COLLECTION_INTERVAL", "60"))  # default: 1 reading/min
WARMUP_SECONDS   = int(os.getenv("SENSOR_WARMUP", "5"))
DB_PATH          = os.getenv("DB_PATH", "")          # empty = default path

# WHO PM2.5 alert threshold (µg/m³)
PM25_ALERT_THRESHOLD  = float(os.getenv("PM25_ALERT_THRESHOLD", "25.0"))
PM10_ALERT_THRESHOLD  = float(os.getenv("PM10_ALERT_THRESHOLD", "50.0"))

# ── Global state ───────────────────────────────────────────────────────────────
_running = True


def _signal_handler(sig, frame):
    global _running
    logger.info("Signal %d received — stopping collector…", sig)
    _running = False


signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT,  _signal_handler)


def run():
    from pathlib import Path as _Path
    db_path = _Path(DB_PATH) if DB_PATH else None
    db = Database(db_path) if db_path else Database()

    sensor = SPS30Sensor(warmup_seconds=WARMUP_SECONDS)
    alerter = TelegramAlerter()

    if not sensor.connect():
        logger.critical("Could not connect to SPS30 sensor. Exiting.")
        sys.exit(1)

    logger.info(
        "Collector started — sampling every %ds, PM2.5 alert threshold: %.1f µg/m³",
        INTERVAL_SECONDS, PM25_ALERT_THRESHOLD,
    )

    # Track last alert time to avoid spam (cooldown 30 min per metric)
    _last_alert: dict[str, float] = {}
    ALERT_COOLDOWN = 1800  # 30 minutes

    try:
        while _running:
            reading = sensor.read()
            if reading is not None:
                row_id = db.insert(reading)
                logger.info(
                    "[#%d] PM1.0=%.1f PM2.5=%.1f PM4.0=%.1f PM10=%.1f µg/m³ | AQI: %s",
                    row_id, reading.pm1p0, reading.pm2p5, reading.pm4p0, reading.pm10p0,
                    reading.aqi_category,
                )

                # ── Telegram alerts ────────────────────────────────────────────
                now = time.time()
                if reading.pm2p5 > PM25_ALERT_THRESHOLD:
                    if now - _last_alert.get("pm25", 0) > ALERT_COOLDOWN:
                        alerter.send_alert(
                            f"⚠️ *PM2.5 Alert*\n"
                            f"Current: `{reading.pm2p5} µg/m³` (threshold: {PM25_ALERT_THRESHOLD})\n"
                            f"AQI category: _{reading.aqi_category}_"
                        )
                        _last_alert["pm25"] = now

                if reading.pm10p0 > PM10_ALERT_THRESHOLD:
                    if now - _last_alert.get("pm10", 0) > ALERT_COOLDOWN:
                        alerter.send_alert(
                            f"⚠️ *PM10 Alert*\n"
                            f"Current: `{reading.pm10p0} µg/m³` (threshold: {PM10_ALERT_THRESHOLD})\n"
                            f"AQI category: _{reading.aqi_category}_"
                        )
                        _last_alert["pm10"] = now
            else:
                logger.warning("No reading obtained — skipping this interval")

            # Sleep in 1s chunks to allow clean shutdown
            for _ in range(INTERVAL_SECONDS):
                if not _running:
                    break
                time.sleep(1)

    finally:
        sensor.disconnect()
        logger.info("Collector stopped cleanly.")


if __name__ == "__main__":
    run()

