# Aggregator Service

**Purpose**: Enrichment, fusion, and persistence of detection events (`DetectionEvent`). Provides filtered query APIs and global statistics.

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/events` | POST | Receives a `DetectionEvent`, computes the `zone` if missing, persists to SQLite |
| `/events?since=&zone=&priority=` | GET | Lists events with optional filters (time, zone Z1/Z2/Z3, priority) |
| `/stats` | GET | Aggregates by zone and priority level |
| `/health` | GET | Service health |

## Zone Classification

The maritime zone is automatically determined from tile coordinates:

| Zone | Distance from Moroccan coast | Description |
|------|------------------------------|-------------|
| **Z1** | ≤ 12 NM | Territorial Waters |
| **Z2** | ≤ 200 NM | Exclusive Economic Zone (EEZ) |
| **Z3** | > 200 NM | High Seas |

The calculation uses the tile centroid and the reference bounding box (`MOROCCO_BBOX` in `shared/config/constants.py`).

## Database

- **SQLite** local: `services/aggregator/data/events.db`
- Schema stores detections as JSON for simplicity.
- Ready for PostgreSQL migration (Pydantic schemas are backend-independent).

## Local Execution

```bash
uvicorn services.aggregator.main:app --host 0.0.0.0 --port 8020
```

## Example Calls

```bash
# Post an event
curl -X POST http://localhost:8020/events \
  -H "Content-Type: application/json" \
  -d '{"event_id":"...", "scene_id":"...", ...}'

# List Z1 events with CRITICAL priority
curl "http://localhost:8020/events?zone=Z1&priority=CRITICAL"

# Global statistics
curl http://localhost:8020/stats
```

## Notes

- Data conforms to Pydantic schemas in `shared/schemas/events.py`.
- Errors are logged with `exc_info=True` without exposing implementation details to clients.
