"""Unit tests for Satellite Monitor health endpoint and input validation.

Covers:
  - /health endpoint response
  - parse_satellite_id validation (success, injection, edge cases)
  - _is_cache_fresh behaviour
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

_MAIN = Path(__file__).resolve().parents[1] / "main.py"
_spec = importlib.util.spec_from_file_location("satmon_health", _MAIN)
satmon = importlib.util.module_from_spec(_spec)
sys.modules["satmon_health"] = satmon
assert _spec.loader is not None
try:
    _spec.loader.exec_module(satmon)
except ModuleNotFoundError as exc:
    pytest.skip(f"satellite-monitor deps unavailable: {exc}", allow_module_level=True)


def test_health_endpoint_returns_healthy():
    """The /health endpoint should return a healthy status."""
    satmon.TLE_CACHE.clear()
    result = asyncio.run(satmon.health_check())
    assert result["status"] == "healthy"
    assert result["cached_tles"] == "0"
    assert result["fresh_tles"] == "0"


def test_health_endpoint_with_cache():
    """/health should report cached and fresh TLE counts."""
    satmon.TLE_CACHE.clear()
    satmon.TLE_CACHE[39634] = {
        "name": "SENTINEL-1A",
        "norad_id": 39634,
        "tle1": "1 39634U 14016A   24101.00000000  .00000000  00000-0  00000-0 0  0000",
        "tle2": "2 39634  98.1800 123.0000 0001200  90.0000 270.0000 14.59199999000000",
        "updated_at": datetime.now(UTC).isoformat(),
    }
    result = asyncio.run(satmon.health_check())
    assert result["cached_tles"] == "1"
    assert result["fresh_tles"] == "1"


def test_health_with_stale_cache_only():
    """Stale cache entries should be counted but not fresh."""
    satmon.TLE_CACHE.clear()
    stale_time = (datetime.now(UTC) - timedelta(hours=48)).isoformat()
    satmon.TLE_CACHE[39634] = {
        "name": "SENTINEL-1A",
        "norad_id": 39634,
        "tle1": "1 39634U 14016A   24101.00000000  .00000000  00000-0  00000-0 0  0000",
        "tle2": "2 39634  98.1800 123.0000 0001200  90.0000 270.0000 14.59199999000000",
        "updated_at": stale_time,
    }
    result = asyncio.run(satmon.health_check())
    assert result["cached_tles"] == "1"
    assert result["fresh_tles"] == "0"


def test_parse_satellite_id_valid():
    """Valid NORAD ID strings should be parsed correctly."""
    assert satmon.parse_satellite_id("39634") == 39634
    assert satmon.parse_satellite_id("25544") == 25544
    assert satmon.parse_satellite_id("1") == 1


def test_parse_satellite_id_leading_zeros():
    """Leading zeros should be stripped correctly."""
    assert satmon.parse_satellite_id("00123") == 123


def test_parse_satellite_id_empty_raises():
    """Empty strings should raise ValueError."""
    with pytest.raises(ValueError, match="must not be empty"):
        satmon.parse_satellite_id("")


def test_parse_satellite_id_whitespace_only_raises():
    """Whitespace-only strings should raise ValueError."""
    with pytest.raises(ValueError, match="must not be empty"):
        satmon.parse_satellite_id("   ")


def test_parse_satellite_id_injection_raises():
    """SQL injection patterns should be rejected."""
    for malicious in ["DROP TABLE", "1; DROP", "SELECT *", "' OR '1'='1"]:
        with pytest.raises(ValueError, match="Invalid NORAD ID"):
            satmon.parse_satellite_id(malicious)


def test_parse_satellite_id_negative_raises():
    """Negative numbers should be rejected."""
    with pytest.raises(ValueError, match="not a valid number"):
        satmon.parse_satellite_id("-123")


def test_parse_satellite_id_non_numeric_raises():
    """Non-numeric strings should be rejected."""
    with pytest.raises(ValueError, match="not a valid number"):
        satmon.parse_satellite_id("abc123")


def test_parse_satellite_id_path_traversal_raises():
    """Path traversal patterns should be rejected."""
    with pytest.raises(ValueError, match="Invalid NORAD ID"):
        satmon.parse_satellite_id("../etc/passwd")


def test_is_cache_fresh_with_none():
    """None timestamp should return False."""
    assert satmon._is_cache_fresh(None) is False


def test_is_cache_fresh_with_valid():
    """Recent timestamp should return True."""
    now = datetime.now(UTC).isoformat()
    assert satmon._is_cache_fresh(now) is True


def test_is_cache_fresh_with_stale():
    """Old timestamp should return False."""
    old = (datetime.now(UTC) - timedelta(hours=48)).isoformat()
    assert satmon._is_cache_fresh(old) is False


def test_force_refresh_tles_clears_cache():
    """POST /refresh-tle should clear all cached entries."""
    satmon.TLE_CACHE.clear()
    satmon.TLE_CACHE[39634] = {"name": "test", "norad_id": 39634}
    satmon.TLE_CACHE[25544] = {"name": "test2", "norad_id": 25544}
    result = asyncio.run(satmon.force_refresh_tles())
    assert "2 entries" in result["detail"]
    assert len(satmon.TLE_CACHE) == 0
