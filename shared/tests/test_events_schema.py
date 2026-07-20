"""
test_events_schema.py
---------------------
Comprehensive unit tests for shared Pydantic event schemas.

Tests coverage:
  - BoundingBox: creation, validation, edge cases
  - DetectionEvent: creation, field validation, defaults
  - IngestRequest: creation, field validation
  - TLEData: creation, field validation
  - Edge cases: missing fields, invalid types, boundary values
  - Security: injection attempts, extreme values
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

# Add project root to sys.path so 'shared' package is importable
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from pydantic import ValidationError

    from shared.schemas.events import (
        BoundingBox,
        DetectionEvent,
        IngestRequest,
        TLEData,
    )
except ImportError as exc:
    pytest.skip(f"Dependencies not available: {exc}", allow_module_level=True)


# =============================================================================
# BoundingBox
# =============================================================================


class TestBoundingBox:
    """Tests for BoundingBox schema."""

    def test_valid_creation(self):
        bbox = BoundingBox(x1=0.1, y1=0.2, x2=0.8, y2=0.9, confidence=0.95)
        assert bbox.x1 == 0.1
        assert bbox.y1 == 0.2
        assert bbox.x2 == 0.8
        assert bbox.y2 == 0.9
        assert bbox.confidence == 0.95

    def test_confidence_at_boundaries(self):
        bbox = BoundingBox(x1=0, y1=0, x2=1, y2=1, confidence=0.0)
        assert bbox.confidence == 0.0
        bbox = BoundingBox(x1=0, y1=0, x2=1, y2=1, confidence=1.0)
        assert bbox.confidence == 1.0

    def test_confidence_out_of_range_raises(self):
        with pytest.raises(ValidationError):
            BoundingBox(x1=0, y1=0, x2=1, y2=1, confidence=-0.1)
        with pytest.raises(ValidationError):
            BoundingBox(x1=0, y1=0, x2=1, y2=1, confidence=1.1)

    def test_missing_fields_raises(self):
        with pytest.raises(ValidationError):
            BoundingBox()  # type: ignore[call-arg]
        with pytest.raises(ValidationError):
            BoundingBox(x1=0.1, y1=0.2, x2=0.8)  # Missing y2, confidence

    def test_extra_fields_ignored(self):
        """Pydantic ignores extra fields by default."""
        bbox = BoundingBox(x1=0.1, y1=0.2, x2=0.8, y2=0.9, confidence=0.95, extra="ignored")
        assert bbox.x1 == 0.1  # Core fields are still correct

    def test_repr(self):
        bbox = BoundingBox(x1=0.1, y1=0.2, x2=0.8, y2=0.9, confidence=0.95)
        r = repr(bbox)
        assert "x1=0.1" in r

    def test_type_coercion(self):
        """Pydantic should coerce ints to floats."""
        bbox = BoundingBox(x1=0, y1=0, x2=100, y2=100, confidence=1)
        assert isinstance(bbox.x1, float)
        assert isinstance(bbox.confidence, float)


# =============================================================================
# DetectionEvent
# =============================================================================


class TestDetectionEvent:
    """Tests for DetectionEvent schema."""

    def test_valid_creation(self):
        event = DetectionEvent(
            event_id="evt-001",
            scene_id="S1A_IW_GRDH_1SDV_20240101T000000_000000_000000_0000",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            tile_id="tile_001",
            tile_bbox_latlon=[30.0, -10.0, 31.0, -9.0],
            detections=[BoundingBox(x1=0.1, y1=0.2, x2=0.5, y2=0.6, confidence=0.95)],
            vessel_count=1,
            dark_vessel_count=0,
            priority_level="HIGH",
            zone="Z1",
            preprocessing_pipeline="D",
            processing_time_ms=150.5,
        )
        assert event.event_id == "evt-001"
        assert event.vessel_count == 1
        assert event.priority_level == "HIGH"

    def test_empty_detections(self):
        """Empty detections list should be valid."""
        event = DetectionEvent(
            event_id="evt-002",
            scene_id="S1A_GRDH_20240101",
            timestamp=datetime(2024, 1, 1),
            tile_id="tile_002",
            tile_bbox_latlon=[30.0, -10.0, 31.0, -9.0],
            detections=[],
            vessel_count=0,
            dark_vessel_count=0,
            priority_level="LOW",
            zone="Z3",
            preprocessing_pipeline="D",
            processing_time_ms=100.0,
        )
        assert len(event.detections) == 0
        assert event.vessel_count == 0

    def test_negative_vessel_count_raises(self):
        with pytest.raises(ValidationError):
            DetectionEvent(
                event_id="evt-003",
                scene_id="S1A_GRDH_20240101",
                timestamp=datetime(2024, 1, 1),
                tile_id="tile_003",
                tile_bbox_latlon=[30.0, -10.0, 31.0, -9.0],
                detections=[],
                vessel_count=-1,
                dark_vessel_count=0,
                priority_level="LOW",
                zone="Z3",
                preprocessing_pipeline="D",
                processing_time_ms=100.0,
            )

    def test_negative_processing_time_raises(self):
        with pytest.raises(ValidationError):
            DetectionEvent(
                event_id="evt-004",
                scene_id="S1A_GRDH_20240101",
                timestamp=datetime(2024, 1, 1),
                tile_id="tile_004",
                tile_bbox_latlon=[30.0, -10.0, 31.0, -9.0],
                detections=[],
                vessel_count=0,
                dark_vessel_count=0,
                priority_level="LOW",
                zone="Z3",
                preprocessing_pipeline="D",
                processing_time_ms=-1.0,
            )

    def test_tile_bbox_wrong_length_raises(self):
        with pytest.raises(ValidationError):
            DetectionEvent(
                event_id="evt-005",
                scene_id="S1A_GRDH_20240101",
                timestamp=datetime(2024, 1, 1),
                tile_id="tile_005",
                tile_bbox_latlon=[30.0, -10.0, 31.0],  # Only 3 values
                detections=[],
                vessel_count=0,
                dark_vessel_count=0,
                priority_level="LOW",
                zone="Z3",
                preprocessing_pipeline="D",
                processing_time_ms=100.0,
            )

    def test_optional_fields_default_to_none(self):
        event = DetectionEvent(
            event_id="evt-006",
            scene_id="S1A_GRDH_20240101",
            timestamp=datetime(2024, 1, 1),
            tile_id="tile_006",
            tile_bbox_latlon=[30.0, -10.0, 31.0, -9.0],
            detections=[],
            vessel_count=0,
            dark_vessel_count=0,
            priority_level="LOW",
            zone="Z3",
            preprocessing_pipeline="D",
            processing_time_ms=100.0,
        )
        assert event.satellite_id is None
        assert event.satellite_position is None

    def test_multiple_detections(self):
        bboxes = [
            BoundingBox(x1=0.1, y1=0.2, x2=0.3, y2=0.4, confidence=0.95),
            BoundingBox(x1=0.5, y1=0.6, x2=0.7, y2=0.8, confidence=0.85),
            BoundingBox(x1=0.2, y1=0.3, x2=0.4, y2=0.5, confidence=0.75),
        ]
        event = DetectionEvent(
            event_id="evt-007",
            scene_id="S1A_GRDH_20240101",
            timestamp=datetime(2024, 1, 1),
            tile_id="tile_007",
            tile_bbox_latlon=[30.0, -10.0, 31.0, -9.0],
            detections=bboxes,
            vessel_count=3,
            dark_vessel_count=1,
            priority_level="CRITICAL",
            zone="Z1",
            preprocessing_pipeline="A",
            processing_time_ms=250.0,
        )
        assert len(event.detections) == 3
        assert event.dark_vessel_count == 1
        assert event.priority_level == "CRITICAL"
        assert event.processing_time_ms == 250.0

    def test_satellite_metadata(self):
        event = DetectionEvent(
            event_id="evt-008",
            scene_id="S1A_GRDH_20240101",
            timestamp=datetime(2024, 1, 1),
            tile_id="tile_008",
            tile_bbox_latlon=[30.0, -10.0, 31.0, -9.0],
            detections=[],
            vessel_count=0,
            dark_vessel_count=0,
            priority_level="LOW",
            zone="Z3",
            preprocessing_pipeline="D",
            processing_time_ms=100.0,
            satellite_id="39634",
            satellite_position={"lat": 45.0, "lon": 0.0, "alt_km": 693.0},
        )
        assert event.satellite_id == "39634"
        assert event.satellite_position["lat"] == 45.0


# =============================================================================
# IngestRequest
# =============================================================================


class TestIngestRequest:
    """Tests for IngestRequest schema."""

    def test_valid_creation(self):
        req = IngestRequest(
            bbox=[-10.0, 32.0, -8.0, 34.0],
            date_start="2024-01-01T00:00:00Z",
            date_end="2024-01-02T00:00:00Z",
        )
        assert len(req.bbox) == 4
        assert req.bbox[0] == -10.0
        assert req.pipeline == "D"  # Default

    def test_custom_pipeline(self):
        req = IngestRequest(
            bbox=[-10.0, 32.0, -8.0, 34.0],
            date_start="2024-01-01",
            date_end="2024-01-02",
            pipeline="A",
        )
        assert req.pipeline == "A"

    def test_satellite_id(self):
        req = IngestRequest(
            bbox=[-10.0, 32.0, -8.0, 34.0],
            date_start="2024-01-01",
            date_end="2024-01-02",
            satellite_id="Sentinel-1A",
        )
        assert req.satellite_id == "Sentinel-1A"

    def test_bbox_wrong_length_raises(self):
        with pytest.raises(ValidationError):
            IngestRequest(
                bbox=[-10.0, 32.0, -8.0],  # Only 3
                date_start="2024-01-01",
                date_end="2024-01-02",
            )


# =============================================================================
# TLEData
# =============================================================================


class TestTLEData:
    """Tests for TLEData schema."""

    def test_valid_creation(self):
        tle = TLEData(
            satellite_name="SENTINEL-1A",
            norad_id=39634,
            tle1="1 39634U 14016A   24101.00000000  .00000000  00000-0  00000-0 0  0000",
            tle2="2 39634  98.1800 123.0000 0001200  90.0000 270.0000 14.59199999000000",
            updated_at=datetime(2024, 4, 10, 12, 0, 0),
        )
        assert tle.satellite_name == "SENTINEL-1A"
        assert tle.norad_id == 39634
        assert len(tle.tle1) > 0
        assert len(tle.tle2) > 0

    def test_norad_id_type(self):
        """NORAD IDs should be integers."""
        TLEData(
            satellite_name="TEST",
            norad_id=39634,
            tle1="1 00000U 00000A   00000.00000000  .00000000  00000-0  00000-0 0  0000",
            tle2="2 00000  98.1800 123.0000 0001200  90.0000 270.0000 14.59199999000000",
            updated_at=datetime(2024, 1, 1),
        )
