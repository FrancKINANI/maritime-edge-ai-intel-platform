# services/aggregator/main.py
"""Data Aggregator FastAPI Service.

Exposes endpoints for enriching detection events with satellite and AIS status,
persisting findings in database storage, and querying aggregated metrics.
"""

from fastapi import FastAPI, HTTPException, status
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional
from shared.schemas.events import DetectionEvent, BoundingBox
import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime
from shared.config import constants

logger = logging.getLogger(__name__)


DB_PATH = Path(__file__).resolve().parent / "data" / "events.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            scene_id TEXT,
            timestamp TEXT,
            tile_id TEXT,
            tile_bbox_latlon TEXT,
            detections TEXT,
            vessel_count INTEGER,
            dark_vessel_count INTEGER,
            priority_level TEXT,
            zone TEXT,
            satellite_id TEXT,
            satellite_position TEXT,
            preprocessing_pipeline TEXT,
            processing_time_ms REAL
        )
        """
    )
    conn.commit()
    conn.close()


def determine_zone(tile_bbox_latlon: List[float]) -> str:
    # Simple heuristic using centroid distance to Morocco bbox (degrees ~ nm/60)
    try:
        lat_min, lon_min, lat_max, lon_max = tile_bbox_latlon
        lat_c = (lat_min + lat_max) / 2.0
        lon_c = (lon_min + lon_max) / 2.0
    except Exception:
        return "Z3"

    bbox = constants.MOROCCO_BBOX  # [lon_min, lat_min, lon_max, lat_max]
    lon0, lat0, lon1, lat1 = bbox
    # If centroid inside Morocco bbox -> Z1
    if lon_c >= lon0 and lon_c <= lon1 and lat_c >= lat0 and lat_c <= lat1:
        return "Z1"
    # Convert NM to degrees (approx)
    z1_deg = constants.ZONE_Z1_NM / 60.0
    z2_deg = constants.ZONE_Z2_NM / 60.0
    # Distance to bbox in degrees (lon/lat separately, approximate)
    dlon = 0.0
    if lon_c < lon0:
        dlon = lon0 - lon_c
    elif lon_c > lon1:
        dlon = lon_c - lon1
    dlat = 0.0
    if lat_c < lat0:
        dlat = lat0 - lat_c
    elif lat_c > lat1:
        dlat = lat_c - lat1
    dist_deg = max(dlon, dlat)
    if dist_deg <= z1_deg:
        return "Z1"
    if dist_deg <= z2_deg:
        return "Z2"
    return "Z3"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Maritime Edge AI Intel Platform - Aggregator",
    description="Microservice aggregating, enriching, and storing detection reports.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.post("/events", status_code=status.HTTP_201_CREATED, response_model=DetectionEvent)
async def ingest_detection_event(event: DetectionEvent) -> DetectionEvent:
    try:
        # Enrich zone if missing
        if not event.zone:
            event.zone = determine_zone(event.tile_bbox_latlon)

        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute(
            "REPLACE INTO events (event_id, scene_id, timestamp, tile_id, tile_bbox_latlon, detections, vessel_count, dark_vessel_count, priority_level, zone, satellite_id, satellite_position, preprocessing_pipeline, processing_time_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                event.event_id,
                event.scene_id,
                event.timestamp.isoformat(),
                event.tile_id,
                json.dumps(event.tile_bbox_latlon),
                json.dumps([d.dict() for d in event.detections]),
                event.vessel_count,
                event.dark_vessel_count,
                event.priority_level,
                event.zone,
                event.satellite_id,
                json.dumps(event.satellite_position) if event.satellite_position else None,
                event.preprocessing_pipeline,
                event.processing_time_ms,
            ),
        )
        conn.commit()
        conn.close()
        return event
    except Exception as e:
        logger.error(f"Database error in ingest_detection_event: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal database error")


@app.get("/events", response_model=List[DetectionEvent])
async def list_events(since: Optional[str] = None, zone: Optional[str] = None, priority: Optional[str] = None) -> List[DetectionEvent]:
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    q = "SELECT * FROM events"
    clauses = []
    params = []
    if since:
        clauses.append("timestamp >= ?")
        params.append(since)
    if zone:
        clauses.append("zone = ?")
        params.append(zone)
    if priority:
        clauses.append("priority_level = ?")
        params.append(priority)
    if clauses:
        q += " WHERE " + " AND ".join(clauses)
    q += " ORDER BY timestamp DESC LIMIT 1000"
    cur.execute(q, params)
    rows = cur.fetchall()
    results: List[DetectionEvent] = []
    for row in rows:
        (_event_id, scene_id, timestamp, tile_id, tile_bbox_latlon, detections, vessel_count, dark_vessel_count, priority_level, zone, satellite_id, satellite_position, preprocessing_pipeline, processing_time_ms) = row
        det_list = []
        if detections:
            try:
                det_json = json.loads(detections)
                for d in det_json:
                    det_list.append(BoundingBox(**d))
            except Exception:
                det_list = []
        ev = DetectionEvent(
            event_id=_event_id,
            scene_id=scene_id,
            timestamp=datetime.fromisoformat(timestamp),
            tile_id=tile_id,
            tile_bbox_latlon=json.loads(tile_bbox_latlon) if tile_bbox_latlon else [0, 0, 0, 0],
            detections=det_list,
            vessel_count=vessel_count,
            dark_vessel_count=dark_vessel_count,
            priority_level=priority_level,
            zone=zone,
            satellite_id=satellite_id,
            satellite_position=json.loads(satellite_position) if satellite_position else None,
            preprocessing_pipeline=preprocessing_pipeline,
            processing_time_ms=processing_time_ms,
        )
        results.append(ev)
    conn.close()
    return results


def dict_to_bb(d: Dict[str, Any]) -> Any:
    return type("BB", (), d)()


@app.get("/stats", response_model=Dict[str, Any])
async def get_global_statistics() -> Dict[str, Any]:
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT zone, COUNT(*) FROM events GROUP BY zone")
    zones = {row[0]: row[1] for row in cur.fetchall()}
    cur.execute("SELECT priority_level, COUNT(*) FROM events GROUP BY priority_level")
    priorities = {row[0]: row[1] for row in cur.fetchall()}
    conn.close()
    return {"by_zone": zones, "by_priority": priorities}


@app.get("/health", response_model=Dict[str, str])
async def health_check() -> Dict[str, str]:
    return {"status": "healthy"}
