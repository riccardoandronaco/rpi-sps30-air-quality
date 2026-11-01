"""
sensor.py - SPS30 sensor reader via I2C
Uses the community sps30 Python library (pip install sps30)
SPS30 I2C address: 0x69, connected to /dev/i2c-1
"""
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional
from time import sleep

logger = logging.getLogger(__name__)


@dataclass
class AirQualityReading:
    pm1p0: float       # PM1.0  µg/m³
    pm2p5: float       # PM2.5  µg/m³
    pm4p0: float       # PM4.0  µg/m³
    pm10p0: float      # PM10.0 µg/m³
    nc0p5: float       # NC0.5  1/cm³
    nc1p0: float       # NC1.0  1/cm³
    nc2p5: float       # NC2.5  1/cm³
    nc4p0: float       # NC4.0  1/cm³
    nc10p0: float      # NC10.0 1/cm³
    typical_size: float  # µm

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def aqi_category(self) -> str:
        """
        Simple AQI category based on PM2.5 (WHO guidelines 2021):
        Good < 15, Moderate 15-25, Unhealthy for Sensitive 25-50,
        Unhealthy 50-75, Very Unhealthy > 75 µg/m³
        """
        pm = self.pm2p5
        if pm < 15:
            return "Good"
        elif pm < 25:
            return "Moderate"
        elif pm < 50:
            return "Unhealthy for Sensitive Groups"
        elif pm < 75:
            return "Unhealthy"
        else:
            return "Very Unhealthy"


class SPS30Sensor:
    """Wrapper around the sps30 Python library for I2C communication."""

    I2C_BUS = 1  # Raspberry Pi standard I2C bus

    def __init__(self, warmup_seconds: int = 5):
        self._warmup_seconds = warmup_seconds
        self._sps = None

    def connect(self) -> bool:
        """Initialize the SPS30 sensor. Returns True if successful."""
        try:
            from sps30 import SPS30
            self._sps = SPS30(self.I2C_BUS)
            logger.info("SPS30 connected on I2C bus %d", self.I2C_BUS)

            article = self._sps.read_article_code()
            if article != self._sps.ARTICLE_CODE_ERROR:
                logger.info("Article code: %s", article)

            serial = self._sps.read_device_serial()
            if serial != self._sps.SERIAL_NUMBER_ERROR:
                logger.info("Serial number: %s", serial)

            self._sps.start_measurement()
            logger.info("Measurement started, warming up for %ds…", self._warmup_seconds)
            sleep(self._warmup_seconds)
            return True
        except Exception as exc:
            logger.error("Failed to connect to SPS30: %s", exc)
            return False

    def read(self) -> Optional[AirQualityReading]:
        """
        Read a single measurement from the SPS30.
        Returns None on error or if data is not ready.
        """
        if self._sps is None:
            logger.error("Sensor not initialized. Call connect() first.")
            return None
        try:
            # Poll up to 5 times (each 1s) waiting for data ready
            for _ in range(5):
                if self._sps.read_data_ready_flag():
                    break
                sleep(1)
            else:
                logger.warning("SPS30 data not ready after 5s")
                return None

            if self._sps.read_measured_values() == self._sps.MEASURED_VALUES_ERROR:
                logger.error("CRC error reading SPS30 values")
                return None

            v = self._sps.dict_values
            return AirQualityReading(
                pm1p0=round(v["pm1p0"], 2),
                pm2p5=round(v["pm2p5"], 2),
                pm4p0=round(v["pm4p0"], 2),
                pm10p0=round(v["pm10p0"], 2),
                nc0p5=round(v["nc0p5"], 2),
                nc1p0=round(v["nc1p0"], 2),
                nc2p5=round(v["nc2p5"], 2),
                nc4p0=round(v["nc4p0"], 2),
                nc10p0=round(v["nc10p0"], 2),
                typical_size=round(v["typical_size"], 2),
            )
        except Exception as exc:
            logger.exception("Error reading SPS30: %s", exc)
            return None

    def disconnect(self):
        """Stop measurement and release sensor."""
        if self._sps is not None:
            try:
                self._sps.stop_measurement()
                logger.info("SPS30 measurement stopped")
            except Exception as exc:
                logger.warning("Error stopping SPS30: %s", exc)
            self._sps = None

