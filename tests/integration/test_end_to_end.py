"""
test_end_to_end.py
-------------------
End-to-end integration tests for the maritime-intelligence-platform.

Tests the full data flow: ingestor → preprocessor → detector pipeline,
including zone classification, event schema validation, and TLE handling.
Uses mocking for external HTTP dependencies (CDSE, SatNOGS, Celestrak).
"""

from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Data Ingestor Integration Tests
# ---------------------------------------------------------------------------


def test_ingestor_sentinel_fetcher_integration():
    """Test the ingestor's sentinel fetcher with mocked phase0 functions."""
    import importlib.util
    import sys

    _FETCHER_MAIN = Path(__file__).resolve().parents[2] / "services" / "data-ingestor" / "sentinel_fetcher.py"
    if not _FETCHER_MAIN.exists():
        pytest.skip("sentinel_fetcher.py not found")

    _spec = importlib.util.spec_from_file_location("data_ingestor_fetcher", str(_FETCHER_MAIN))
    _module = importlib.util.module_from_spec(_spec)
    sys.modules["data_ingestor_fetcher"] = _module
    assert _spec.loader is not None
    _spec.loader.exec_module(_module)

    # sentinel_fetcher delegates to phase0.scripts.download_scenes
    # search_cdse_odata needs env vars unless we pass username/password explicitly
    mock_results = [
        {
            "Id": "abc-123",
            "Name": "S1A_IW_GRDH_1SDV_20260101T000000",
            "ContentDate": {
                "Start": "2026-01-01T00:00:00Z",
                "End": "2026-01-01T00:01:00Z",
            },
            "Geometry": {
                "type": "Point",
                "coordinates": [-5.0, 35.0],
            },
        }
    ]

    with (
        patch.object(_module, "get_cdse_token", return_value=("test-token-abc", 9999999999)) as mock_get_token,
        patch.object(_module, "search_sentinel1_products", return_value=mock_results) as mock_search,
    ):
        # Pass credentials explicitly to bypass env var check
        results = _module.search_cdse_odata(
            bbox=[35.0, -5.0, 36.0, -4.0],
            date_start="2026-01-01",
            date_end="2026-01-02",
            username="test-user",
            password="test-pass",
        )
        mock_get_token.assert_called_once()
        mock_search.assert_called_once()
        assert len(results) == 1
        assert results[0]["Id"] == "abc-123"
        assert "S1A_IW" in results[0]["Name"]


@pytest.mark.skip(reason="Requires running FastAPI server")
def test_ingestor_health_endpoint():
    """Test ingestor FastAPI health endpoint (integration with live server)."""
    import httpx

    response = httpx.get("http://localhost:8000/health", timeout=5.0)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# Sentinel Preprocessor Integration
# ---------------------------------------------------------------------------


def test_preprocessing_lee_filter_integration():
    """Test the full preprocessing chain (calibrate → lee → db → normalize)."""
    import sys

    _PREPROC_PATH = (
        Path(__file__).resolve().parents[2] / "services" / "sentinel-preprocessor" / "sar_preprocessing_module.py"
    )
    if not _PREPROC_PATH.exists():
        pytest.skip("sar_preprocessing_module.py not found")

    # Use importlib to avoid mutating global sys.path
    _spec = importlib.util.spec_from_file_location("sar_preproc", str(_PREPROC_PATH))
    _module = importlib.util.module_from_spec(_spec)
    sys.modules["sar_preproc"] = _module
    assert _spec.loader is not None
    _spec.loader.exec_module(_module)
    calibrate_sigma0 = _module.calibrate_sigma0
    apply_lee_filter = _module.apply_lee_filter
    convert_to_db = _module.convert_to_db
    normalize_to_uint8 = _module.normalize_to_uint8

    # Simulate raw SAR intensity data (uint16)
    np.random.seed(7)
    raw = np.random.randint(50, 2000, (100, 100)).astype(np.uint16)
    calibration_lut = np.ones((100, 100), dtype=np.float32) * 0.5

    # Full chain: calibrate → Lee filter → dB → normalize
    sigma0 = calibrate_sigma0(raw, calibration_lut)
    assert not np.any(np.isnan(sigma0)), "NaN after calibration"

    filtered = apply_lee_filter(sigma0, kernel_size=5)
    assert filtered.shape == sigma0.shape, "Shape changed after Lee filter"
    assert not np.any(np.isnan(filtered)), "NaN after Lee filter"

    db = convert_to_db(filtered)
    assert not np.any(np.isinf(db)), "Inf after dB conversion"

    normalized = normalize_to_uint8(db, db_min=-30.0, db_max=0.0)
    assert normalized.dtype == np.uint8, "Not uint8 after normalization"
    assert np.all(normalized <= 255), "Values exceed 255"


# ---------------------------------------------------------------------------
# Detector Integration
# ---------------------------------------------------------------------------


def test_detector_nms_xywh_integration():
    """Test NMS pipeline with xywh2xyxy conversion (simulating detector flow)."""
    import importlib.util
    import sys

    _DET_MAIN = Path(__file__).resolve().parents[2] / "services" / "detector" / "main.py"
    if not _DET_MAIN.exists():
        pytest.skip("detector main.py not found")

    _spec = importlib.util.spec_from_file_location("detector_integration_main", str(_DET_MAIN))
    try:
        _module = importlib.util.module_from_spec(_spec)
        sys.modules["detector_integration_main"] = _module
        assert _spec.loader is not None
        _spec.loader.exec_module(_module)
    except ModuleNotFoundError as exc:
        pytest.skip(f"detector deps unavailable: {exc}")

    # Simulate YOLO output: center-format boxes [cx, cy, w, h]
    yolo_outputs = np.array(
        [
            [50, 50, 100, 100, 0.95, 0],  # Ship at center
            [55, 55, 90, 90, 0.85, 0],  # Heavily overlapping (should be suppressed)
            [300, 300, 60, 80, 0.75, 0],  # Far away (should be kept)
            [50, 50, 100, 100, 0.60, 1],  # Same area, different class (should be kept if class-aware)
        ]
    )

    boxes_xywh = yolo_outputs[:, :4]  # [cx, cy, w, h]
    scores = yolo_outputs[:, 4]

    # Convert to xyxy (corner format)
    xyxy_boxes = np.array([_module.xywh2xyxy(b) for b in boxes_xywh])
    assert xyxy_boxes.shape == (4, 4)

    # Run NMS
    keep = _module.nms(xyxy_boxes.tolist(), scores.tolist(), iou_threshold=0.45)
    assert len(keep) >= 2, f"NMS should keep at least 2 boxes, got {keep}"
    assert 0 in keep, "Highest score box should be kept"


# ---------------------------------------------------------------------------
# Zone Classification + Event Schema Integration
# ---------------------------------------------------------------------------


def test_zone_classification_to_event_schema():
    """Test that zone classification results are compatible with event schema."""
    from shared.schemas.events import BoundingBox, DetectionEvent

    # Simulate aggregation of zone + detection data
    event = DetectionEvent(
        event_id="evt-integration-001",
        scene_id="S1A_IW_20260101",
        tile_id="tile_00001",
        timestamp="2026-01-01T00:00:00Z",
        tile_bbox_latlon=[35.0, -5.0, 36.0, -4.0],
        zone="Z1",
        priority_level="HIGH",
        vessel_count=3,
        dark_vessel_count=1,
        preprocessing_pipeline="D",
        detections=[
            BoundingBox(x1=100, y1=150, x2=130, y2=180, confidence=0.92),
            BoundingBox(x1=200, y1=250, x2=240, y2=290, confidence=0.85),
        ],
        processing_time_ms=1234.5,
    )

    serialized = event.model_dump_json()
    deserialized = DetectionEvent.model_validate_json(serialized)
    assert deserialized.event_id == event.event_id
    assert deserialized.zone == "Z1"
    assert deserialized.priority_level == "HIGH"
    assert deserialized.vessel_count == 3
    assert len(deserialized.detections) == 2


# ---------------------------------------------------------------------------
# Aggregator Integration
# ---------------------------------------------------------------------------


def test_aggregator_zone_determination_flow():
    """Test that aggregator's determine_zone works with various bbox types."""
    import importlib.util
    import sys

    _AGG_MAIN = Path(__file__).resolve().parents[2] / "services" / "aggregator" / "main.py"
    if not _AGG_MAIN.exists():
        pytest.skip("aggregator main.py not found")

    _spec = importlib.util.spec_from_file_location("aggregator_integration_main", str(_AGG_MAIN))
    _module = importlib.util.module_from_spec(_spec)
    sys.modules["aggregator_integration_main"] = _module
    assert _spec.loader is not None
    _spec.loader.exec_module(_module)

    # Morocco bbox: lat_min=-17, lat_max=-1, lon_min=27, lon_max=36
    zone = _module.determine_zone([27.0, -17.0, 36.0, -1.0])
    assert zone == "Z1"

    # High seas: far from Morocco
    zone = _module.determine_zone([10.0, -40.0, 20.0, -30.0])
    assert zone == "Z3"


# ---------------------------------------------------------------------------
# TLE + Satellite Monitor Integration
# ---------------------------------------------------------------------------


def test_tle_fallback_pipeline():
    """Test that the TLE fallback flow correctly delegates to Celestrak.

    NOTE: Internal TLE_CACHE behavior is tested in the satellite-monitor's
    own test files (services/satellite_monitor/tests/test_tle_fallback.py).
    This integration test focuses on the delegation logic.
    """
    import importlib.util
    import sys

    _SAT_MAIN = Path(__file__).resolve().parents[2] / "services" / "satellite-monitor" / "main.py"
    if not _SAT_MAIN.exists():
        pytest.skip("satellite-monitor main.py not found")

    _spec = importlib.util.spec_from_file_location("satmon_integration_main", str(_SAT_MAIN))
    try:
        _module = importlib.util.module_from_spec(_spec)
        sys.modules["satmon_integration_main"] = _module
        assert _spec.loader is not None
        _spec.loader.exec_module(_module)
    except ModuleNotFoundError as exc:
        pytest.skip(f"satellite-monitor deps unavailable: {exc}")

    celestrak_entry = {
        "name": "SENTINEL-1A",
        "norad_id": 39634,
        "tle1": "1 39634U 14016A   24101.00000000  .00000000  00000-0  00000-0 0  0000",
        "tle2": "2 39634  98.1800 123.0000 0001200  90.0000 270.0000 14.59199999000000",
        "updated_at": "2026-07-12T00:00:00",
        "source": "celestrak",
    }

    async def _run():
        with (
            patch.object(_module, "fetch_tle_from_satnogs", new_callable=AsyncMock) as mock_satnogs,
            patch.object(_module, "fetch_tle_from_celestrak", new_callable=AsyncMock) as mock_celestrak,
        ):
            mock_satnogs.side_effect = ValueError("No TLE")
            mock_celestrak.return_value = celestrak_entry
            entry = await _module._fetch_tle_with_fallback(39634)
            mock_satnogs.assert_awaited_once_with(39634)
            mock_celestrak.assert_awaited_once_with(39634)
            assert entry["source"] == "celestrak"
            assert entry["norad_id"] == 39634
            return entry

    import asyncio

    entry = asyncio.run(_run())
    assert entry is not None
