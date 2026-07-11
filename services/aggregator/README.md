# Aggregator Service

**Purpose**: Enrichment, fusion, and persistence of detection events (`DetectionEvent`). Provides filtered query APIs and global statistics.

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/events` | POST | Receives a `DetectionEvent`, computes the `zone` if missing, persists to SQLite → `201 Created` |
| `/events` | GET | Lists events with optional filters: `since` (ISO timestamp), `zone` (Z1/Z2/Z3), `priority` (LOW/MEDIUM/HIGH/CRITICAL) |
| `/stats` | GET | Aggregated counts by zone and priority level |
| `/health` | GET | Service health |

## Zone Classification

The maritime zone is automatically determined from the tile centroid coordinates:

| Zone | Distance from Moroccan coast | Description |
|------|------------------------------|-------------|
| **Z1** | ≤ 12 NM | Territorial Waters |
| **Z2** | ≤ 200 NM | Exclusive Economic Zone (EEZ) |
| **Z3** | > 200 NM | High Seas |

The calculation uses the tile centroid and the reference bounding box (`MOROCCO_BBOX` in `shared/config/constants.py`). Distances are approximated in decimal degrees (1° ≈ 60 NM).

## Database

- **SQLite** local: `services/aggregator/data/events.db`
- Schema stores detections as JSON for simplicity
- Ready for PostgreSQL migration (Pydantic schemas are backend-independent)
- Table: `events` with 14 columns (event_id PK, scene_id, timestamp, tile_id, tile_bbox_latlon, detections, vessel_count, dark_vessel_count, priority_level, zone, satellite_id, satellite_position, preprocessing_pipeline, processing_time_ms)

## Local Execution

```bash
uvicorn services.aggregator.main:app --host 0.0.0.0 --port 8002
```

## Example Calls

```bash
# Post an event
curl -X POST http://localhost:8002/events \
  -H "Content-Type: application/json" \
  -d '{"event_id":"...", "scene_id":"...", ...}'

# List Z1 events with CRITICAL priority
curl "http://localhost:8002/events?zone=Z1&priority=CRITICAL"

# Global statistics
curl http://localhost:8002/stats
```

## Docker

```bash
docker compose build aggregator
docker compose up -d aggregator
```

Image: `maritime-intelligence-platform-aggregator` — port `:8002`

## Notes

- Data conforms to Pydantic schemas in `shared/schemas/events.py`
- Errors are logged with `exc_info=True` without exposing implementation details to clients
- Uses FastAPI `lifespan` context manager (startup: initializes SQLite DB)
- Built-in pip-audit: 0 vulnerabilities
- 7 unit tests for zone classification (`services/aggregator/tests/`)
