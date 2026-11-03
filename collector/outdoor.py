"""
outdoor.py - Automatic location detection via IP and outdoor air quality fetching
Uses:
  1. IP Geolocation (ip-api.com / ipapi.co) -> automatically detects city, lat, lon
  2. Open-Meteo Air Quality API -> free, no API key required
Cached in memory for 30 minutes to reduce external calls.
"""
import json
import logging
import os
import time
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)


def _european_aqi_label(aqi: Optional[float]) -> str:
    """European Air Quality Index classification (EEA standard)."""
    if aqi is None:
        return "Non disponibile"
    if aqi <= 20:
        return "Molto Buona"
    elif aqi <= 40:
        return "Buona"
    elif aqi <= 60:
        return "Moderata"
    elif aqi <= 80:
        return "Scadente"
    elif aqi <= 100:
        return "Molto Scadente"
    else:
        return "Estremamente Scadente"


class OutdoorAirQuality:
    CACHE_DURATION = 1800  # 30 minutes

    def __init__(self):
        self._cached_data: Optional[dict] = None
        self._last_fetch_time: float = 0.0
        self._cached_coords: Optional[tuple[float, float, str]] = None

    def resolve_location_by_cap(self, cap: str, country: str = "it") -> Optional[tuple[float, float, str]]:
        """
        Resolve coordinates and city name from postal code (CAP) without API keys.
        Primary: api.zippopotam.us
        Fallback: Nominatim (OpenStreetMap)
        """
        clean_cap = cap.strip()
        if not clean_cap:
            return None

        # 1. Zippopotam.us (super-fast, dedicated postal code DB)
        try:
            url = f"https://api.zippopotam.us/{country.lower()}/{clean_cap}"
            req = urllib.request.Request(url, headers={"User-Agent": "rpi-sps30-monitor/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                places = data.get("places", [])
                if places:
                    p = places[0]
                    lat = float(p["latitude"])
                    lon = float(p["longitude"])
                    place = p.get("place name", "")
                    state = p.get("state", "")
                    loc_name = f"{place} ({clean_cap}), {state}" if state else f"{place} ({clean_cap})"
                    logger.info("Resolved CAP %s to %s (%.4f, %.4f)", clean_cap, loc_name, lat, lon)
                    return (lat, lon, loc_name)
        except Exception as exc:
            logger.warning("Zippopotam lookup for CAP '%s' failed: %s", clean_cap, exc)

        # 2. Fallback Nominatim (OpenStreetMap)
        try:
            url = f"https://nominatim.openstreetmap.org/search?postalcode={clean_cap}&country={country}&format=json&limit=1"
            req = urllib.request.Request(url, headers={"User-Agent": "rpi-sps30-monitor-geocoder/1.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                results = json.loads(resp.read().decode("utf-8"))
                if results:
                    r = results[0]
                    lat = float(r["lat"])
                    lon = float(r["lon"])
                    display_name = r.get("display_name", f"CAP {clean_cap}")
                    # Keep short city part
                    short_name = display_name.split(",")[0]
                    loc_name = f"{short_name} ({clean_cap})"
                    logger.info("Nominatim resolved CAP %s to %s (%.4f, %.4f)", clean_cap, loc_name, lat, lon)
                    return (lat, lon, loc_name)
        except Exception as exc:
            logger.warning("Nominatim lookup for CAP '%s' failed: %s", clean_cap, exc)

        return None

    def get_location(self) -> Optional[tuple[float, float, str]]:
        """
        Detect lat, lon and city name with the following priority:
          1. Explicit LATITUDE and LONGITUDE from .env
          2. CAP or POSTAL_CODE from .env (e.g. CAP=20121 or CAP=00185)
          3. Automatic public IP Geolocation (fallback)
        """
        # If already resolved and cached, reuse
        if self._cached_coords is not None:
            return self._cached_coords

        # 1. Manual coordinates override
        env_lat = os.getenv("LATITUDE", "").strip()
        env_lon = os.getenv("LONGITUDE", "").strip()
        env_loc = os.getenv("LOCATION_NAME", "").strip()
        if env_lat and env_lon:
            try:
                lat = float(env_lat)
                lon = float(env_lon)
                name = env_loc or f"{lat:.2f}, {lon:.2f}"
                self._cached_coords = (lat, lon, name)
                return self._cached_coords
            except ValueError:
                pass

        # 2. CAP / Postal Code from .env
        env_cap = os.getenv("CAP", os.getenv("POSTAL_CODE", "")).strip()
        env_country = os.getenv("COUNTRY_CODE", "it").strip() or "it"
        if env_cap:
            res = self.resolve_location_by_cap(env_cap, env_country)
            if res:
                self._cached_coords = res
                return self._cached_coords

        # 3. Fallback to IP Geolocation
        return self._get_location_by_ip()

    def _get_location_by_ip(self) -> Optional[tuple[float, float, str]]:
        """Detect coordinates via public IP."""

        # 1. Try ip-api.com (free, 45 req/min, highly accurate)
        try:
            req = urllib.request.Request(
                "http://ip-api.com/json/?fields=status,city,regionName,country,lat,lon",
                headers={"User-Agent": "rpi-sps30-monitor/1.0"},
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("status") == "success":
                    lat = float(data["lat"])
                    lon = float(data["lon"])
                    city = data.get("city", "")
                    region = data.get("regionName", "")
                    country = data.get("country", "")
                    parts = [p for p in [city, region, country] if p]
                    loc_name = ", ".join(parts) if parts else "Posizione rilevata"
                    self._cached_coords = (lat, lon, loc_name)
                    logger.info("Auto-detected location via IP: %s (%.4f, %.4f)", loc_name, lat, lon)
                    return self._cached_coords
        except Exception as exc:
            logger.warning("ip-api.com lookup failed: %s", exc)

        # 2. Fallback to ipapi.co
        try:
            req = urllib.request.Request(
                "https://ipapi.co/json/",
                headers={"User-Agent": "rpi-sps30-monitor/1.0"},
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if "latitude" in data and "longitude" in data:
                    lat = float(data["latitude"])
                    lon = float(data["longitude"])
                    city = data.get("city", "")
                    region = data.get("region", "")
                    parts = [p for p in [city, region] if p]
                    loc_name = ", ".join(parts) if parts else "Posizione rilevata"
                    self._cached_coords = (lat, lon, loc_name)
                    return self._cached_coords
        except Exception as exc:
            logger.warning("ipapi.co lookup fallback failed: %s", exc)

        return None

    def fetch_outdoor_data(self, force_refresh: bool = False) -> Optional[dict]:
        """
        Fetch outdoor air quality from Open-Meteo API using auto-detected coordinates.
        Data is cached for 30 minutes.
        """
        now = time.time()
        if not force_refresh and self._cached_data and (now - self._last_fetch_time < self.CACHE_DURATION):
            return self._cached_data

        loc = self.get_location()
        if not loc:
            logger.warning("Unable to determine device location for outdoor air quality")
            return self._cached_data

        lat, lon, loc_name = loc
        url = (
            f"https://air-quality-api.open-meteo.com/v1/air-quality?"
            f"latitude={lat:.4f}&longitude={lon:.4f}"
            f"&current=european_aqi,pm10,pm2_5,nitrogen_dioxide,ozone"
        )

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "rpi-sps30-monitor/1.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
                current = raw.get("current", {})

                aqi = current.get("european_aqi")
                pm25 = current.get("pm2_5")
                pm10 = current.get("pm10")
                no2 = current.get("nitrogen_dioxide")
                o3 = current.get("ozone")

                result = {
                    "available": True,
                    "location_name": loc_name,
                    "latitude": lat,
                    "longitude": lon,
                    "european_aqi": aqi,
                    "european_aqi_label": _european_aqi_label(aqi),
                    "pm2p5": round(pm25, 2) if pm25 is not None else None,
                    "pm10p0": round(pm10, 2) if pm10 is not None else None,
                    "no2": round(no2, 2) if no2 is not None else None,
                    "ozone": round(o3, 2) if o3 is not None else None,
                    "time": current.get("time"),
                    "source": "Open-Meteo (CAMS European Air Quality)",
                }

                self._cached_data = result
                self._last_fetch_time = now
                logger.info("Outdoor air quality updated for %s: PM2.5=%.1f, PM10=%.1f", loc_name, pm25 or 0, pm10 or 0)
                return result
        except Exception as exc:
            logger.error("Failed to fetch outdoor air quality from Open-Meteo: %s", exc)
            if self._cached_data:
                return self._cached_data
            return {
                "available": False,
                "location_name": loc_name,
                "error": str(exc),
            }


# Singleton instance
outdoor_service = OutdoorAirQuality()
