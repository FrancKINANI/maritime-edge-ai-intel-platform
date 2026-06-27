# shared/schemas/events.py
"""Shared event schemas for the maritime intelligence platform.

This module defines Pydantic schemas for data serialization and interface contracts
between the data ingestor, preprocessor, detector, satellite monitor, aggregator,
and dashboard services.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """Bounding box coordinates for detected vessels with confidence score.

    Attributes:
        x1 (float): Normalised or absolute pixel/coordinate start X.
        y1 (float): Normalised or absolute pixel/coordinate start Y.
        x2 (float): Normalised or absolute pixel/coordinate end X.
        y2 (float): Normalised or absolute pixel/coordinate end Y.
        confidence (float): Detection confidence score in range [0.0, 1.0].
    """
    x1: float = Field(..., description="Top-left X coordinate")
    y1: float = Field(..., description="Top-left Y coordinate")
    x2: float = Field(..., description="Bottom-right X coordinate")
    y2: float = Field(..., description="Bottom-right Y coordinate")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Detection confidence score")


class DetectionEvent(BaseModel):
    """Complete representation of a vessel detection event.

    Encapsulates geographic context, processing performance, bounding boxes,
    assigned priority levels, and satellite tracking metadata.
    """
    event_id: str = Field(..., description="Unique event identifier (UUID v4)")
    scene_id: str = Field(..., description="Identifier of the source Sentinel-1 scene")
    timestamp: datetime = Field(..., description="Acquisition timestamp of the SAR image")
    tile_id: str = Field(..., description="Identifier of the processed tile")
    tile_bbox_latlon: List[float] = Field(
        ...,
        min_items=4,
        max_items=4,
        description="Geographic bounding box of the tile: [lat_min, lon_min, lat_max, lon_max]"
    )
    detections: List[BoundingBox] = Field(..., description="List of detected vessels bounding boxes")
    vessel_count: int = Field(..., ge=0, description="Total number of vessels detected")
    dark_vessel_count: int = Field(..., ge=0, description="Number of vessels detected without matching active AIS signals")
    priority_level: str = Field(..., description="Assigned priority level: LOW, MEDIUM, HIGH, CRITICAL")
    zone: str = Field(..., description="Geographical maritime zone: Z1, Z2, Z3")
    satellite_id: Optional[str] = Field(None, description="NORAD ID or name of the observing satellite")
    satellite_position: Optional[Dict[str, Any]] = Field(None, description="Coordinates and altitude of satellite at timestamp")
    preprocessing_pipeline: str = Field(..., description="Identifier of the preprocessing pipeline used (A, B, C, or D)")
    processing_time_ms: float = Field(..., ge=0.0, description="Processing duration in milliseconds")


class IngestRequest(BaseModel):
    """Payload to trigger acquisition and ingestion of satellite scenes."""
    bbox: List[float] = Field(
        ...,
        min_items=4,
        max_items=4,
        description="Bounding box coordinates: [lon_min, lat_min, lon_max, lat_max]"
    )
    date_start: str = Field(..., description="Query start time in ISO8601 format")
    date_end: str = Field(..., description="Query end time in ISO8601 format")
    satellite_id: Optional[str] = Field(None, description="Target satellite name or ID (e.g. Sentinel-1A)")
    pipeline: str = Field("D", description="Preprocessing pipeline to execute (A, B, C, D)")


class TLEData(BaseModel):
    """Two-Line Element (TLE) satellite orbital parameter record."""
    satellite_name: str = Field(..., description="Official name of the satellite")
    norad_id: int = Field(..., description="NORAD Catalog Number")
    tle1: str = Field(..., description="Line 1 of the TLE record")
    tle2: str = Field(..., description="Line 2 of the TLE record")
    updated_at: datetime = Field(..., description="Timestamp of when the TLE was last fetched/refreshed")
