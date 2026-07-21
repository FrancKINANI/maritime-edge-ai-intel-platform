"""Unit tests for SatNOGS primary + Celestrak fallback TLE fetch.

Engineering non-regression: empty SatNOGS response must trigger Celestrak,
which is the acté solution for Sentinel-1A (NORAD 39634) data absence.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

_MAIN = Path(__file__).resolve().parents[1] / "main.py"
_spec = importlib.util.spec_from_file_location("satmon_main", _MAIN)
satmon = importlib.util.module_from_spec(_spec)
sys.modules["satmon_main"] = satmon
assert _spec.loader is not None
try:
    _spec.loader.exec_module(satmon)
except ModuleNotFoundError as exc:
    pytest.skip(f"satellite-monitor deps unavailable: {exc}", allow_module_level=True)


def test_celestrak_fallback_when_satnogs_empty():
    """Empty SatNOGS list must fall through to Celestrak and cache the result."""
    satmon.TLE_CACHE.clear()
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
            patch.object(satmon, "fetch_tle_from_satnogs", new_callable=AsyncMock) as mock_satnogs,
            patch.object(
                satmon, "fetch_tle_from_celestrak", new_callable=AsyncMock
            ) as mock_celestrak,
        ):
            mock_satnogs.side_effect = ValueError("No TLE found for NORAD id 39634 in SatNOGS")
            mock_celestrak.return_value = celestrak_entry
            entry = await satmon._fetch_tle_with_fallback(39634)
            mock_satnogs.assert_awaited_once_with(39634)
            mock_celestrak.assert_awaited_once_with(39634)
            return entry

    entry = asyncio.run(_run())
    assert entry["source"] == "celestrak"
    assert entry["norad_id"] == 39634


def test_satnogs_success_skips_celestrak():
    satmon.TLE_CACHE.clear()
    satnogs_entry = {
        "name": "TEST-SAT",
        "norad_id": 25544,
        "tle1": "1 25544U 98067A   24101.00000000  .00000000  00000-0  00000-0 0  0000",
        "tle2": "2 25544  51.6400 123.0000 0001200  90.0000 270.0000 15.50000000000000",
        "updated_at": "2026-07-12T00:00:00",
        "source": "satnogs",
    }

    async def _run():
        with (
            patch.object(satmon, "fetch_tle_from_satnogs", new_callable=AsyncMock) as mock_satnogs,
            patch.object(
                satmon, "fetch_tle_from_celestrak", new_callable=AsyncMock
            ) as mock_celestrak,
        ):
            mock_satnogs.return_value = satnogs_entry
            entry = await satmon._fetch_tle_with_fallback(25544)
            mock_satnogs.assert_awaited_once()
            mock_celestrak.assert_not_awaited()
            return entry

    entry = asyncio.run(_run())
    assert entry["source"] == "satnogs"
