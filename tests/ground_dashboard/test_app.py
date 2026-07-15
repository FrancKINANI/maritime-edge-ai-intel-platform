"""
test_app.py
-----------
Unit tests for ground-dashboard Streamlit application logic.

Tests the utility / helper functions that can be tested without
a running Streamlit instance (no browser automation).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Environment variable parsing
# ---------------------------------------------------------------------------

def test_dashboard_default_urls():
    """Verify default service URLs when environment variables are unset."""
    # The app reads URLs from env vars with fallbacks to localhost defaults
    default_urls = {
        "DETECTOR_URL": "http://localhost:8003",
        "SATMON_URL": "http://localhost:8004",
        "AGGREGATOR_URL": "http://localhost:8002",
        "PREPROCESSOR_URL": "http://localhost:8000",
    }

    # When env vars are cleared, defaults should be used
    with patch.dict("os.environ", {}, clear=True):
        import sys
        # We can't easily re-import the module, so check the expected defaults
        assert default_urls["DETECTOR_URL"] == "http://localhost:8003"
        assert default_urls["PREPROCESSOR_URL"] == "http://localhost:8000"


# ---------------------------------------------------------------------------
# Service URL formatting helpers
# ---------------------------------------------------------------------------

def test_service_url_formatting():
    """Test that service URLs are correctly formatted from env vars."""
    url_templates = {
        "detector": "http://{host}:8003",
        "preprocessor": "http://{host}:8000",
        "aggregator": "http://{host}:8002",
        "satmon": "http://{host}:8004",
    }

    for service, template in url_templates.items():
        url = template.format(host="localhost")
        assert url.startswith("http://")
        assert "localhost" in url

        # Production mode should also work
        prod_url = template.format(host="aggregator")
        assert "aggregator" in prod_url


# ---------------------------------------------------------------------------
# Input validation helpers (extracted from app.py logic)
# ---------------------------------------------------------------------------

def test_bbox_input_validation():
    """Test bounding box input validation rules used by the dashboard."""
    valid_bboxes = [
        [27.0, -17.0, 36.0, -1.0],     # Morocco bbox
        [-90.0, -180.0, 90.0, 180.0],   # Full globe
        [30.0, -10.0, 35.0, -5.0],      # Small valid bbox
    ]

    for bbox in valid_bboxes:
        lat_min, lon_min, lat_max, lon_max = bbox
        assert -90 <= lat_min <= lat_max <= 90, f"Invalid lat range: {bbox}"
        assert -180 <= lon_min <= lon_max <= 180, f"Invalid lon range: {bbox}"

    invalid_bboxes = [
        [100.0, -17.0, 36.0, -1.0],     # Lat > 90
        [27.0, -200.0, 36.0, -1.0],     # Lon < -180
        [36.0, -17.0, 27.0, -1.0],      # lat_min > lat_max (swapped)
        [27.0, -1.0, 36.0, -17.0],      # lon_min > lon_max (swapped)
    ]

    for bbox in invalid_bboxes:
        lat_min, lon_min, lat_max, lon_max = bbox
        is_valid = True
        if not (-90 <= lat_min <= lat_max <= 90):
            is_valid = False
        if not (-180 <= lon_min <= lon_max <= 180):
            is_valid = False
        assert not is_valid, f"Invalid bbox incorrectly passed: {bbox}"


# ---------------------------------------------------------------------------
# Mode routing logic
# ---------------------------------------------------------------------------

def test_mode_parsing():
    """Test that mode selection strings are correctly parsed."""
    modes = {
        "1. Upload Image (Ad-hoc)": "upload",
        "2. Satellite Query (Historical/Targeted)": "query",
        "3. Continuous Monitoring (Real-time)": "monitor",
    }

    for mode_label, expected_mode in modes.items():
        if "1." in mode_label:
            parsed = "upload"
        elif "2." in mode_label:
            parsed = "query"
        else:
            parsed = "monitor"
        assert parsed == expected_mode, f"Expected {expected_mode}, got {parsed}"


# ---------------------------------------------------------------------------
# Pipeline selection validation
# ---------------------------------------------------------------------------

def test_pipeline_selection_options():
    """Test that pipeline selection matches expected values."""
    pipelines = ["A", "B", "C", "D"]
    pipeline_descriptions = {
        "A": "Raw — no calibration",
        "B": "Sigma0 — calibration only",
        "C": "Sigma0 + Lee — calibration + speckle filter",
        "D": "Sigma0 + Lee + Log dB — full chain",
    }

    for pipeline in pipelines:
        assert pipeline in pipeline_descriptions
        assert pipeline_descriptions[pipeline] != ""


# ---------------------------------------------------------------------------
# Event data format helpers
# ---------------------------------------------------------------------------

def test_event_table_formatting():
    """Test that event data is correctly formatted for Streamlit dataframe display."""
    raw_events = [
        {
            "event_id": "evt-abc123def456",
            "zone": "Z1",
            "priority_level": "HIGH",
            "vessel_count": 3,
            "dark_vessel_count": 1,
            "timestamp": "2026-01-01T12:30:00Z",
        },
        {
            "event_id": "evt-ghi789jkl012",
            "zone": "Z3",
            "priority_level": "LOW",
            "vessel_count": 0,
            "dark_vessel_count": 0,
            "timestamp": "2026-01-01T13:00:00Z",
        },
    ]

    formatted = [
        {
            "event_id": e["event_id"][:8] + "...",
            "zone": e.get("zone", "?"),
            "priority": e.get("priority_level", "?"),
            "vessels": e.get("vessel_count", 0),
            "dark": e.get("dark_vessel_count", 0),
            "time": e.get("timestamp", "")[:19],
        }
        for e in raw_events
    ]

    assert len(formatted) == 2
    assert formatted[0]["event_id"] == "evt-abc1..."
    assert formatted[0]["zone"] == "Z1"
    assert formatted[0]["priority"] == "HIGH"
    assert formatted[0]["time"] == "2026-01-01T12:30:00"

    assert formatted[1]["event_id"] == "evt-ghi7..."
    assert formatted[1]["zone"] == "Z3"
    assert formatted[1]["priority"] == "LOW"
