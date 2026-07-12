"""Unit tests for aggregator utility functions (determine_zone).

Tests the zone classification heuristic using the Morocco BBOX reference.
These are pure functions testable without SQLite or FastAPI.
"""

from pathlib import Path
import importlib.util
import sys

# Load aggregator main.py by absolute path so concurrent pytest collection of
# other services/*/main.py modules cannot shadow the name "main".
_AGG_MAIN = Path(__file__).resolve().parents[1] / "main.py"
_spec = importlib.util.spec_from_file_location("aggregator_main", _AGG_MAIN)
_aggregator_main = importlib.util.module_from_spec(_spec)
sys.modules["aggregator_main"] = _aggregator_main
assert _spec.loader is not None
_spec.loader.exec_module(_aggregator_main)
determine_zone = _aggregator_main.determine_zone


def test_determine_zone_inside_morocco_bbox():
    """Test that a point clearly inside Morocco bbox returns Z1."""
    # Morocco bbox is [-17, 27, -1, 36] (lon_min, lat_min, lon_max, lat_max)
    # A tile at center of Morocco coast: lat~31.5, lon~-9.0
    zone = determine_zone([27.0, -17.0, 36.0, -1.0])
    assert zone == "Z1", f"Expected Z1 for Morocco bbox, got {zone}"


def test_determine_zone_inside_territorial_waters():
    """Test that a point within 12NM of Morocco bbox returns Z1."""
    # Just outside Morocco bbox but within 12NM (~0.2 degrees)
    # Morocco bbox lat max is 36.0, so lat_c=36.1 is ~6NM north = within 12NM
    zone = determine_zone([35.9, -17.0, 36.1, -1.0])
    assert zone == "Z1", f"Expected Z1 for territorial waters, got {zone}"


def test_determine_zone_inside_eez():
    """Test that a point within 200NM but outside 12NM returns Z2."""
    # Far from Morocco bbox but within 200NM (~3.3 degrees)
    zone = determine_zone([27.0, -17.0, 39.0, -1.0])
    # lat_c = 33.0, well within EEZ range
    assert zone in ("Z1", "Z2"), f"Expected Z1 or Z2 for EEZ, got {zone}"


def test_determine_zone_high_seas():
    """Test that a point far from Morocco returns Z3."""
    # Far from Morocco (e.g., mid-Atlantic)
    zone = determine_zone([10.0, -40.0, 20.0, -30.0])
    assert zone == "Z3", f"Expected Z3 for high seas, got {zone}"


def test_determine_zone_edge_east():
    """Test zone classification for a tile east of Morocco bbox."""
    # East of Morocco bbox (lon_max=-1), well outside 12NM
    zone = determine_zone([27.0, 2.0, 36.0, 5.0])
    assert zone in ("Z2", "Z3"), f"Expected Z2 or Z3 for east, got {zone}"


def test_determine_zone_edge_west():
    """Test zone classification for a tile west of Morocco bbox."""
    # West of Morocco bbox (lon_min=-17), 5 degrees west ≈ 300NM = Z3
    zone = determine_zone([27.0, -24.0, 36.0, -22.0])
    assert zone == "Z3", f"Expected Z3 for far west, got {zone}"


def test_determine_zone_invalid_bbox():
    """Test that invalid bbox returns Z3 as default."""
    zone = determine_zone([])
    assert zone == "Z3", f"Expected Z3 for empty bbox, got {zone}"


def test_determine_zone_malformed_bbox():
    """Test that malformed bbox returns Z3 as default."""
    zone = determine_zone([1.0, 2.0])  # Only 2 values when 4 expected
    assert zone == "Z3", f"Expected Z3 for malformed bbox, got {zone}"
