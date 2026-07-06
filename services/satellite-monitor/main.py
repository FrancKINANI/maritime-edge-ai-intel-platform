# services/satellite-monitor/main.py
"""Satellite Monitor FastAPI Service.

Exposes endpoints for tracking satellite positions, fetching TLE parameters
from SatNOGS, and updating orbital coefficients.
"""

from datetime import datetime
from fastapi import FastAPI, HTTPException, status
from typing import Dict, Any
import httpx
from shared.schemas.events import TLEData
from skyfield.api import EarthSatellite, load, wgs84


app = FastAPI(
    title="Maritime Edge AI Intel Platform - Satellite Monitor",
    description="Microservice responsible for tracking satellite orbits and fetching TLE files.",
    version="1.0.0",
)


# Simple in-memory TLE cache: norad_id -> {tle1, tle2, name, updated_at}
TLE_CACHE: Dict[int, Dict[str, Any]] = {}


async def fetch_tle_from_satnogs(norad_id: int) -> Dict[str, Any]:
    url = f"https://db.satnogs.org/api/satellites/?norad_cat_id={norad_id}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
    if not data:
        raise ValueError(f"No TLE found for NORAD id {norad_id}")
    # API may return list; take first
    rec = data[0]
    # Try multiple possible field names
    name = rec.get("name") or rec.get("satellite_name") or f"NORAD-{norad_id}"
    tle1 = rec.get("tle1") or rec.get("line1") or rec.get("tle_line1")
    tle2 = rec.get("tle2") or rec.get("line2") or rec.get("tle_line2")
    # Some APIs return combined 'tle' string
    if (not tle1 or not tle2) and rec.get("tle"):
        tle_lines = rec.get("tle").splitlines()
        if len(tle_lines) >= 2:
            tle1, tle2 = tle_lines[0], tle_lines[1]
    if not tle1 or not tle2:
        raise ValueError("TLE lines not found in SatNOGS response")
    entry = {"name": name, "norad_id": norad_id, "tle1": tle1, "tle2": tle2, "updated_at": datetime.utcnow().isoformat()}
    TLE_CACHE[norad_id] = entry
    return entry


@app.get("/tle/{norad_id}", response_model=TLEData)
async def get_current_tle(norad_id: int) -> TLEData:
    if norad_id in TLE_CACHE:
        entry = TLE_CACHE[norad_id]
    else:
        try:
            entry = await fetch_tle_from_satnogs(norad_id)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Failed to fetch TLE: {e}")
    return TLEData(
        satellite_name=entry.get("name"),
        norad_id=int(entry.get("norad_id")),
        tle1=entry.get("tle1"),
        tle2=entry.get("tle2"),
        updated_at=datetime.fromisoformat(entry.get("updated_at")),
    )


@app.get("/position", response_model=Dict[str, Any])
async def get_satellite_position(satellite_id: str, timestamp: datetime) -> Dict[str, Any]:
    # Accept satellite_id as NORAD integer or name
    try:
        norad = int(satellite_id)
    except Exception:
        # try to find by name in cache
        norad = None
        for k, v in TLE_CACHE.items():
            if v.get("name") == satellite_id:
                norad = k
                break
        if norad is None:
            raise HTTPException(status_code=400, detail="satellite_id must be NORAD id or known cached name")

    if norad not in TLE_CACHE:
        try:
            await fetch_tle_from_satnogs(norad)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Failed to fetch TLE: {e}")

    entry = TLE_CACHE[norad]
    tle1 = entry["tle1"]
    tle2 = entry["tle2"]
    name = entry.get("name")

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
        raise HTTPException(status_code=500, detail=f"SGP4 propagation error: {e}")

    return {"satellite_id": norad, "name": name, "timestamp": timestamp.isoformat(), "lat": lat, "lon": lon, "alt_m": alt_m}


@app.post("/refresh-tle", status_code=status.HTTP_200_OK, response_model=Dict[str, str])
async def force_refresh_tles() -> Dict[str, str]:
    TLE_CACHE.clear()
    return {"status": "ok", "detail": "TLE cache cleared"}


@app.get("/health", response_model=Dict[str, str])
async def health_check() -> Dict[str, str]:
    return {"status": "healthy", "cached_tles": str(len(TLE_CACHE))}
