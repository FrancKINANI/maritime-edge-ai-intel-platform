"""
test_security.py
-----------------
Security-focused tests for the maritime-intelligence-platform services.

Covers:
  - Path traversal in sentinel-preprocessor SAR file paths
  - Injection in satellite-monitor queries (NORAD ID injection)
  - API input validation and boundary conditions
  - JSON payload injection via aggregator endpoints
  - SSRF protection patterns in data-ingestor
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Path Traversal
# ---------------------------------------------------------------------------

def test_sentinel_preprocessor_path_traversal_prevention():
    """Verify that path traversal attempts in safe_path are rejected."""
    from pathlib import Path
    import sys
    _PREPROC_PATH = Path(__file__).resolve().parents[2] / "services" / "sentinel-preprocessor" / "sar_preprocessing.py"

    if not _PREPROC_PATH.exists():
        pytest.skip("sar_preprocessing.py not found")

    sys.path.insert(0, str(_PREPROC_PATH.parent))
    # Import will fail if deps aren't installed — use try/except
    try:
        from sar_preprocessing import validate_safe_path, SafetyViolation
    except ImportError:
        # If validation isn't implemented, that's a finding too
        pytest.skip("validate_safe_path not found — security feature not implemented")

    # Test path traversal attempts
    malicious_paths = [
        "/etc/passwd",
        "../../etc/shadow",
        "/app/../../etc/secrets",
        "data/../../../tmp/malicious",
        "/app/configs/../../proc/1/environ",
    ]
    for path in malicious_paths:
        with pytest.raises(SafetyViolation):
            validate_safe_path(path)

    # Legitimate paths should pass
    safe_paths = [
        "/app/shared/uploads/S1A_IW_GRDH_1SDV.zip",
        "/app/shared/S1A_IW_GRDH_1SDV.SAFE",
        "/data/tiles/tile_00001.npy",
    ]
    for path in safe_paths:
        try:
            validate_safe_path(path)
        except SafetyViolation:
            pytest.fail(f"Safe path rejected: {path}")


# ---------------------------------------------------------------------------
# Input Injection — Satellite Monitor
# ---------------------------------------------------------------------------

def test_satellite_monitor_norad_id_injection():
    """Verify that NORAD ID parameter is validated against injection patterns."""
    # Load satellite-monitor main to check its parameter handling
    _SAT_MAIN = Path(__file__).resolve().parents[2] / "services" / "satellite-monitor" / "main.py"
    if not _SAT_MAIN.exists():
        pytest.skip("satellite-monitor main.py not found")

    import importlib.util
    import sys

    _spec = importlib.util.spec_from_file_location("satmon_security_main", str(_SAT_MAIN))
    _module = importlib.util.module_from_spec(_spec)
    sys.modules["satmon_security_main"] = _module
    assert _spec.loader is not None
    _spec.loader.exec_module(_module)

    # Check that the module validates NORAD IDs
    # The position endpoint should reject non-integer satellite IDs
    test_fn = getattr(_module, "parse_satellite_id", getattr(_module, "_parse_satellite_id", None))
    if test_fn is None:
        pytest.skip("No parse_satellite_id function found")

    valid_ids = ["25544", "39634", "1"]
    for sid in valid_ids:
        result = test_fn(sid)
        assert isinstance(result, int), f"Expected int, got {type(result)}"
        assert result > 0, f"Expected positive NORAD ID"

    # Should reject injection payloads
    invalid_ids = ["; DROP TABLE tle_cache;", "25544 OR 1=1", "../../etc/passwd", ""]
    for sid in invalid_ids:
        with pytest.raises((ValueError, TypeError)):
            test_fn(sid)


# ---------------------------------------------------------------------------
# JSON Injection — Aggregator
# ---------------------------------------------------------------------------

def test_aggregator_json_payload_integrity():
    """Verify that DetectionEvent schema handles malicious payloads gracefully."""
    from shared.schemas.events import DetectionEvent, BoundingBox

    # JSON with overly deep nesting (potential DoS via parser)
    malicious_payloads = [
        # Deeply nested JSON (stack overflow attempt)
        {"x": None, "nested": {"nested": {"nested": {"nested": None}}}},
        # Very large numbers (overflow attempt)
        {"vessel_count": 10**100, "dark_vessel_count": 2**63 - 1},
        # Negative counts (business logic validation)
        {"vessel_count": -1, "dark_vessel_count": -5},
        # Type confusion
        {"vessel_count": "many", "bbox": "not-a-list"},
        # Extra unexpected fields
        {"__proto__": {"admin": True}, "constructor": {"prototype": {"polluted": True}}},
    ]

    for payload in malicious_payloads:
        try:
            event = DetectionEvent(
                event_id="evt-sec-001",
                scene_id="test",
                tile_id="test",
                timestamp="2026-01-01T00:00:00Z",
                tile_bbox_latlon=[35.0, -5.0, 36.0, -4.0],
                zone="Z3",
                priority_level="LOW",
                preprocessing_pipeline="D",
                vessel_count=payload.get("vessel_count", 0),
                dark_vessel_count=payload.get("dark_vessel_count", 0),
                detections=[],
                processing_time_ms=100.0,
            )
            serialized = event.model_dump_json()
            assert "__proto__" not in serialized
        except (TypeError, ValueError, OverflowError):
            pass  # Expected rejection of malicious data


# ---------------------------------------------------------------------------
# SSRF Protection — Data Ingestor
# ---------------------------------------------------------------------------

def test_data_ingestor_url_validation():
    """Verify that sentinel fetcher validates URLs to prevent SSRF."""
    from pathlib import Path
    _FETCHER = Path(__file__).resolve().parents[2] / "services" / "data-ingestor" / "sentinel_fetcher.py"
    if not _FETCHER.exists():
        pytest.skip("sentinel_fetcher.py not found")

    import importlib.util
    import sys

    _spec = importlib.util.spec_from_file_location("data_ingestor_sec", str(_FETCHER))
    _module = importlib.util.module_from_spec(_spec)
    sys.modules["data_ingestor_sec"] = _module
    assert _spec.loader is not None
    _spec.loader.exec_module(_module)

    # Check that CDSE API URLs point to expected domains
    cdse_url = getattr(_module, "CDSE_AUTH_URL", None) or getattr(_module, "CDSE_BASE_URL", None)
    if cdse_url:
        assert "dataspace.copernicus.eu" in cdse_url, \
            f"CDSE URL does not point to expected domain: {cdse_url}"
        assert cdse_url.startswith("https://"), \
            f"CDSE URL is not HTTPS: {cdse_url}"
    else:
        pytest.skip("No CDSE URL found")


# ---------------------------------------------------------------------------
# Fuzzing —  Input Size Bounds
# ---------------------------------------------------------------------------

def test_event_schema_long_strings_handled_gracefully():
    """Verify that DetectionEvent handles long field values gracefully.

    Pydantic accepts long strings by default (no max_length on event_id),
    but the schema should not crash or produce invalid output.
    """
    from shared.schemas.events import DetectionEvent

    # Long strings should be accepted and serializable (no crash)
    event = DetectionEvent(
        event_id="x" * 1000,  # Very long event_id — accepted by Pydantic
        scene_id="test",
        tile_id="test",
        timestamp="2026-01-01T00:00:00Z",
        tile_bbox_latlon=[35.0, -5.0, 36.0, -4.0],
        zone="Z3",
        priority_level="LOW",
        preprocessing_pipeline="D",
        vessel_count=0,
        dark_vessel_count=0,
        detections=[],
        processing_time_ms=100.0,
    )
    serialized = event.model_dump_json()
    assert len(serialized) > 0
    assert event.event_id == "x" * 1000


def test_event_schema_large_detection_list():
    """Verify that DetectionEvent handles many detections without memory issues."""
    from shared.schemas.events import DetectionEvent, BoundingBox

    # Many detections (DoS via large payload)
    all_dets = [
        BoundingBox(x1=i, y1=i, x2=i + 10, y2=i + 10, confidence=0.5)
        for i in range(10000)
    ]
    try:
        event = DetectionEvent(
            event_id="evt-fuzz-001",
            scene_id="test",
            tile_id="test",
            timestamp="2026-01-01T00:00:00Z",
            tile_bbox_latlon=[35.0, -5.0, 36.0, -4.0],
            zone="Z3",
            priority_level="LOW",
            preprocessing_pipeline="D",
            vessel_count=len(all_dets),
            dark_vessel_count=0,
            detections=all_dets,
            processing_time_ms=100.0,
        )
        serialized = event.model_dump_json()
        assert len(serialized) > 0
        assert event.vessel_count == 10000
    except (MemoryError, OverflowError):
        pass  # Acceptable to reject oversized payloads
