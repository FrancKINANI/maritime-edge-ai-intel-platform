# services/satellite-monitor/main.py
"""Satellite Monitor FastAPI Service.

Exposes endpoints for tracking satellite positions, fetching TLE parameters
from SatNOGS, and updating orbital coefficients.
"""

import logging
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, status
from typing import Dict, Any, Optional
import httpx
from shared.schemas.events import TLEData
from shared.config.constants import TLE_REFRESH_HOURS
from skyfield.api import EarthSatellite, load, wgs84

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Maritime Edge AI Intel Platform - Satellite Monitor",
    description="Microservice responsible for tracking satellite orbits and fetching TLE files.",
    version="1.0.0",
)


# In-memory TLE cache: norad_id -> {tle1, tle2, name, norad_id, updated_at}
TLE_CACHE: Dict[int, Dict[str, Any]] = {}


def _is_cache_fresh(cached_at_str: Optional[str]) -> bool:
    """Check if cached TLE is within the TTL window."""
    if not cached_at_str:
        return False
    try:
        cached_at = datetime.fromisoformat(cached_at_str)
        return datetime.utcnow() - cached_at < timedelta(hours=TLE_REFRESH_HOURS)
    except (ValueError, TypeError):
        return False


def _validate_tle_entry(entry: Dict[str, Any]) -> None:
    """Validate that a TLE cache entry has all required fields."""
    required = ["tle1", "tle2", "name", "norad_id"]
    missing = [k for k in required if not entry.get(k)]
    if missing:
        raise ValueError(f"TLE cache entry missing required fields: {missing}")


def _validate_tle_lines(tle1: str, tle2: str) -> None:
    """Validate that TLE lines have the expected format."""
    if not tle1.startswith("1 "):
        raise ValueError(f"TLE line 1 does not start with '1 ': {tle1[:30]}...")
    if not tle2.startswith("2 "):
        raise ValueError(f"TLE line 2 does not start with '2 ': {tle2[:30]}...")


async def fetch_tle_from_celestrak(norad_id: int) -> Dict[str, Any]:
    """Fetch TLE from Celestrak as fallback for operational satellites.

    Endpoint: Celestrak GP (General Perturbations) API
    URL: https://celestrak.org/NORAD/elements/gp.php?CATNR={norad_id}&FORMAT=tle

    Returns plain text with 3 lines: satellite name, TLE line 1, TLE line 2.
    """
    url = f"https://celestrak.org/NORAD/elements/gp.php?CATNR={norad_id}&FORMAT=tle"
    logger.info("Fetching TLE from Celestrak for NORAD %s", norad_id)
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.text
    lines = data.strip().split('\n')
    if len(lines) < 3:
        raise ValueError(f"No TLE found for NORAD id {norad_id} in Celestrak")
    name = lines[0].strip()
    tle1 = lines[1].strip()
    tle2 = lines[2].strip()
    _validate_tle_lines(tle1, tle2)
    entry = {
        "name": name,
        "norad_id": norad_id,
        "tle1": tle1,
        "tle2": tle2,
        "updated_at": datetime.utcnow().isoformat(),
        "source": "celestrak",
    }
    TLE_CACHE[norad_id] = entry
    logger.info("Cached TLE for NORAD %s from Celestrak (%s)", norad_id, name)
    return entry


async def fetch_tle_from_satnogs(norad_id: int) -> Dict[str, Any]:
    """Fetch TLE from SatNOGS DB API (primary source).

    Endpoint: SatNOGS DB API /api/tle/
    URL: https://db.satnogs.org/api/tle/?norad_cat_id={norad_id}

    Returns a JSON list of TLE records. Each record contains:
      - tle0: satellite name line (prefixed with "0 ")
      - tle1: TLE line 1
      - tle2: TLE line 2
    """
    url = f"https://db.satnogs.org/api/tle/?norad_cat_id={norad_id}"
    logger.info("Fetching TLE from SatNOGS for NORAD %s", norad_id)
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
    if not data:
        logger.warning(
            "SatNOGS returned empty TLE data for NORAD %s — Celestrak fallback will be used. "
            "Note: SatNOGS DB /api/tle/ endpoint structurally lacks data for Sentinel-1A (NORAD 39634) "
            "and many operational satellites. Celestrak is the reliable source for this project.",
            norad_id,
        )
        raise ValueError(f"No TLE found for NORAD id {norad_id} in SatNOGS")
    # API returns list; take first (most recent)
    rec = data[0]
    # Extract TLE lines — SatNOGS DB API returns tle0 (name line), tle1, tle2
    tle0_raw = rec.get("tle0", "")
    name = tle0_raw.replace("0 ", "", 1).strip() if tle0_raw else f"NORAD-{norad_id}"
    tle1 = rec.get("tle1")
    tle2 = rec.get("tle2")
    if not tle1 or not tle2:
        raise ValueError("TLE lines not found in SatNOGS response")
    _validate_tle_lines(tle1, tle2)
    entry = {
        "name": name,
        "norad_id": norad_id,
        "tle1": tle1,
        "tle2": tle2,
        "updated_at": datetime.utcnow().isoformat(),
        "source": "satnogs",
    }
    TLE_CACHE[norad_id] = entry
    logger.info("Cached TLE for NORAD %s from SatNOGS (%s)", norad_id, name)
    return entry


def _tle_entry_to_TLEData(entry: Dict[str, Any]) -> TLEData:
    """Convert a raw TLE cache entry dict to a validated TLEData Pydantic model."""
    _validate_tle_entry(entry)
    return TLEData(
        satellite_name=entry["name"],
        norad_id=int(entry["norad_id"]),
        tle1=entry["tle1"],
        tle2=entry["tle2"],
        updated_at=datetime.fromisoformat(entry["updated_at"]),
    )


async def _fetch_tle_with_fallback(norad_id: int) -> Dict[str, Any]:
    """Fetch TLE with SatNOGS primary, Celestrak fallback.

    Returns the raw cache entry dict.
    Raises HTTPException 502 if both sources fail.
    """
    # Check cache first
    if norad_id in TLE_CACHE:
        entry = TLE_CACHE[norad_id]
        if _is_cache_fresh(entry.get("updated_at")):
            logger.debug("Cache HIT for NORAD %s", norad_id)
            return entry
        logger.info("Cache STALE for NORAD %s — refreshing", norad_id)

    # Try SatNOGS first, then Celestrak
    satnogs_error: Optional[str] = None
    celestrak_error: Optional[str] = None

    try:
        return await fetch_tle_from_satnogs(norad_id)
    except Exception as e:
        satnogs_error = str(e)
        logger.warning("SatNOGS failed for NORAD %s: %s", norad_id, satnogs_error)

    try:
        return await fetch_tle_from_celestrak(norad_id)
    except Exception as e:
        celestrak_error = str(e)
        logger.warning("Celestrak failed for NORAD %s: %s", norad_id, celestrak_error)

    # Both sources failed — check if we have any cached entry (even stale)
    if norad_id in TLE_CACHE:
        logger.warning("Returning stale TLE for NORAD %s (both sources failed)", norad_id)
        return TLE_CACHE[norad_id]

    error_detail = f"Failed to fetch TLE for NORAD id {norad_id} from both SatNOGS and Celestrak."
    if satnogs_error:
        error_detail += f" SatNOGS error: {satnogs_error}"
    if celestrak_error:
        error_detail += f" Celestrak error: {celestrak_error}"
    raise HTTPException(status_code=502, detail=error_detail)


@app.get("/tle/{norad_id}", response_model=TLEData)
async def get_current_tle(norad_id: int) -> TLEData:
    entry = await _fetch_tle_with_fallback(norad_id)
    return _tle_entry_to_TLEData(entry)


@app.get("/position", response_model=Dict[str, Any])
async def get_satellite_position(satellite_id: str, timestamp: datetime) -> Dict[str, Any]:
    # Resolve satellite_id to NORAD integer
    try:
        norad = int(satellite_id)
    except (ValueError, TypeError):
        # Try to find by name in cache
        norad = None
        for k, v in TLE_CACHE.items():
            if v.get("name") == satellite_id:
                norad = k
                break
        if norad is None:
            raise HTTPException(
                status_code=400,
                detail=f"satellite_id '{satellite_id}' is not a valid NORAD ID and no cached satellite matches this name. "
                       f"Use a numeric NORAD ID (e.g., 39634 for Sentinel-1A) or query /tle/{{norad_id}} first.",
            )

    entry = await _fetch_tle_with_fallback(norad)
    _validate_tle_entry(entry)
    tle1 = entry["tle1"]
    tle2 = entry["tle2"]
    name = entry["name"]

    ts = load.timescale()
    try:
        sat = EarthSatellite(tle1, tle2, name, ts)
        t = ts.from_datetime(timestamp)
        geoc = sat.at(t)
        subpoint = wgs84.subpoint(geoc)
        lat = subpoint.latitude.degrees
        lon = subpoint.longitude.degrees
        alt_m = subpoint.elevation.m
    except Exception as e:
        logger.error("SGP4 propagation error for NORAD %s: %s", norad, e, exc_info=True)
        raise HTTPException(status_code=500, detail="SGP4 propagation error")

    tle_fresh = _is_cache_fresh(entry.get("updated_at"))
    return {
        "satellite_id": norad,
        "name": name,
        "timestamp": timestamp.isoformat(),
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "alt_m": round(alt_m, 2),
        "tle_source": entry.get("source", "cache"),
        "tle_cached_at": entry.get("updated_at"),
        "tle_fresh": tle_fresh,
    }


@app.post("/refresh-tle", status_code=status.HTTP_200_OK, response_model=Dict[str, str])
async def force_refresh_tles() -> Dict[str, str]:
    count = len(TLE_CACHE)
    TLE_CACHE.clear()
    logger.info("TLE cache cleared (%s entries)", count)
    return {"status": "ok", "detail": f"TLE cache cleared ({count} entries flushed)"}


@app.get("/health", response_model=Dict[str, str])
async def health_check() -> Dict[str, str]:
    fresh = sum(1 for e in TLE_CACHE.values() if _is_cache_fresh(e.get("updated_at")))
    return {
        "status": "healthy",
        "cached_tles": str(len(TLE_CACHE)),
        "fresh_tles": str(fresh),
    }
