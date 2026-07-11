# Satellite Monitor Service

**Purpose**: Fetches TLE data from SatNOGS and Celestrak APIs, caches them with configurable TTL, and computes satellite positions via SGP4 (Skyfield).

## Main Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/tle/{norad_id}` | GET | Returns the current TLE for a NORAD ID (cached with configurable TTL) |
| `/position` | GET | Computes lat/lon/altitude for a given UTC timestamp using SGP4 |
| `/refresh-tle` | POST | Clears the TLE cache, forcing a refresh on next request |
| `/health` | GET | Service health and number of cached TLE entries |

## TLE Sources (Fallback Chain)

1. **SatNOGS DB** (primary): `https://db.satnogs.org/api/tle/?norad_cat_id={id}`
   - Returns a JSON list of TLE records; the most recent one is used
   - Fields: `tle0` (satellite name), `tle1`, `tle2`
   - ⚠️ SatNOGS may return `[]` for some satellites (e.g., Sentinel-1A) — logged explicitly
2. **Celestrak** (fallback): `https://celestrak.org/NORAD/elements/gp.php?CATNR={id}&FORMAT=tle`
   - Returns plain text (3 lines: name, TLE1, TLE2)
   - Used when SatNOGS returns empty or fails

## TLE Cache

- In-memory cache with configurable TTL (`TLE_REFRESH_HOURS` in `shared/config/constants.py`, default 24h)
- If the cache is expired, a refresh attempt is made
- If both sources are unavailable, the stale cache is used as a fallback (graceful degradation)

## Dependencies

- `skyfield` (SGP4 propagator)
- `httpx` (async HTTP client)

## Local Execution

```bash
uvicorn services.satellite_monitor.main:app --host 0.0.0.0 --port 8000
```

## Example Calls

```bash
# Position of Sentinel-1A (NORAD 39634) at a given time
curl "http://localhost:8004/position?satellite_id=39634&timestamp=2026-07-11T12:00:00"

# Raw TLE for Sentinel-1A
curl http://localhost:8004/tle/39634

# Service health
curl http://localhost:8004/health
```

## Common NORAD IDs

| Satellite | NORAD ID |
|-----------|----------|
| Sentinel-1A | 39634 |
| Sentinel-1B | 41456 |
| ISS | 25544 |

## Docker

```bash
docker compose build satellite-monitor
docker compose up -d satellite-monitor
```

Image: `maritime-intelligence-platform-satellite-monitor` — port `:8004`

## Notes

- Endpoints validate TLE line format (must start with `1 ` and `2 `)
- Querying a non-existent NORAD ID returns a 502 error
- The ground-dashboard (Mode 2) uses `39634` (Sentinel-1A) as the default value
- Built-in pip-audit: 0 vulnerabilities
