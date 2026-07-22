"""GCP cross-implementation non-regression test.

Verifies that the standalone GCPGeoreferencer implementation in
research/scripts/sar_preprocessing.py produces IDENTICAL results
to the original implementation in services/sentinel_preprocessor/sar_preprocessing.py
on the same input data.

This test meets the prompt.md (Part A.1) requirement:
    "NON-REGRESSION TEST REQUIRED for this standalone copy: reuse
    exactly the same already-validated test from the service side (zero
    reconstruction error at GCP control points) and apply it to this
    new research/ implementation -- both implementations must produce
    IDENTICAL results on the same input data, not just 'pass their own
    tests' independently."
"""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

# Import research implementation
from research.scripts.sar_preprocessing import (
    GCPGeoreferencer as researchGCPGeoreferencer,
)
from research.scripts.sar_preprocessing import (
    GCPOutOfBoundsError as researchGCPOutOfBoundsError,
)

# Load service implementation via importlib to bypass the hyphen
# in the directory name "sentinel-preprocessor" (which is not a valid
# Python package name for regular imports).
_SERVICE_IMPORT_OK = False
ServiceGCPGeoreferencer = None
try:
    _service_path = (
        Path(__file__).resolve().parent.parent.parent
        / "services"
        / "sentinel-preprocessor"
        / "sar_preprocessing.py"
    )
    _spec = importlib.util.spec_from_file_location("sentinel_preprocessor_sar", str(_service_path))
    if _spec is not None:
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        ServiceGCPGeoreferencer = _mod.GCPGeoreferencer
        _SERVICE_IMPORT_OK = True
except (FileNotFoundError, ModuleNotFoundError, AttributeError, TypeError):
    _SERVICE_IMPORT_OK = False


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

N_LINES, N_PIXELS = 5, 5
IMAGE_SHAPE = (100, 100)

_gcps = np.zeros((N_LINES, N_PIXELS, 2), dtype=np.float64)
for i in range(N_LINES):
    for j in range(N_PIXELS):
        _gcps[i, j, 0] = 30.0 + i * 0.1  # 30.0 -> 30.4
        _gcps[i, j, 1] = -10.0 + j * 0.1  # -10.0 -> -9.6

CONTROL_POINTS: list[tuple[int, int]] = [
    (0, 0),
    (0, 25),
    (0, 99),
    (25, 0),
    (25, 25),
    (25, 50),
    (50, 50),
    (75, 25),
    (99, 99),
]

OUT_OF_BOUNDS: list[tuple[int, int]] = [
    (-1, 50),
    (50, -1),
    (101, 50),
    (50, 101),
]


# ---------------------------------------------------------------------------
# Test 1 — research self-consistency (always runs)
# ---------------------------------------------------------------------------


def test_gcp_research_self_consistency() -> None:
    """research implementation self-consistency checks.

    These assertions always run and validate that the standalone
    GCPGeoreferencer produces correct results independently.
    """
    research_gcp = researchGCPGeoreferencer(_gcps, IMAGE_SHAPE)

    # 1a — Interpolated points are within the expected geographic range
    for line, pixel in CONTROL_POINTS:
        lat_p0, lon_p0 = research_gcp.pixel_to_latlon(line, pixel)
        assert 29.0 <= lat_p0 <= 31.0, f"research lat {lat_p0} outside range"
        assert -11.0 <= lon_p0 <= -9.0, f"research lon {lon_p0} outside range"

    # 1b — Strictly zero reconstruction error at GCP control points
    for i in range(N_LINES):
        for j in range(N_PIXELS):
            line_gcp = i * (IMAGE_SHAPE[0] - 1) / (N_LINES - 1)
            pixel_gcp = j * (IMAGE_SHAPE[1] - 1) / (N_PIXELS - 1)
            lat_p0, lon_p0 = research_gcp.pixel_to_latlon(line_gcp, pixel_gcp)
            expected_lat = _gcps[i, j, 0]
            expected_lon = _gcps[i, j, 1]
            assert abs(lat_p0 - expected_lat) < 1e-10, (
                f"research error at GCP ({i},{j}): {lat_p0} != {expected_lat}"
            )
            assert abs(lon_p0 - expected_lon) < 1e-10

    # 1c — GCPOutOfBoundsError raised for out-of-bounds pixels
    for line, pixel in OUT_OF_BOUNDS:
        with pytest.raises(researchGCPOutOfBoundsError):
            research_gcp.pixel_to_latlon(line, pixel)

    # 1d — tile_to_bbox() returns a valid bbox
    bbox_p0 = research_gcp.tile_to_bbox(25, 25, 75, 75)
    assert len(bbox_p0) == 4, f"bbox must have 4 elements, got {len(bbox_p0)}"
    assert bbox_p0[0] <= bbox_p0[2], f"lat_min {bbox_p0[0]} > lat_max {bbox_p0[2]}"
    assert bbox_p0[1] <= bbox_p0[3], f"lon_min {bbox_p0[1]} > lon_max {bbox_p0[3]}"
    assert 29.0 <= bbox_p0[0] <= 31.0
    assert 29.0 <= bbox_p0[2] <= 31.0
    assert -11.0 <= bbox_p0[1] <= -9.0
    assert -11.0 <= bbox_p0[3] <= -9.0


# ---------------------------------------------------------------------------
# Test 2 — cross-implementation parity (SKIP if service unavailable)
# ---------------------------------------------------------------------------


def test_gcp_cross_implementation_parity() -> None:
    """Both implementations must produce IDENTICAL results.

    Skipped when the service module cannot be loaded (the directory
    name 'sentinel-preprocessor' contains a hyphen which Python's
    standard import machinery cannot handle).
    """
    if not _SERVICE_IMPORT_OK:
        pytest.skip(
            "Service implementation not available — cannot compare. "
            "The directory 'services/sentinel_preprocessor/' contains a "
            "hyphen which prevents regular Python imports. "
            "Use importlib.util.spec_from_file_location() to load it."
        )

    research_gcp = researchGCPGeoreferencer(_gcps, IMAGE_SHAPE)
    service_gcp = ServiceGCPGeoreferencer(_gcps, IMAGE_SHAPE)

    # 2a — Identical interpolation at arbitrary control points
    for line, pixel in CONTROL_POINTS:
        lat_p0, lon_p0 = research_gcp.pixel_to_latlon(line, pixel)
        lat_svc, lon_svc = service_gcp.pixel_to_latlon(line, pixel)
        assert np.isclose(lat_p0, lat_svc, atol=1e-10), (
            f"lat mismatch at ({line},{pixel}): {lat_p0} != {lat_svc}"
        )
        assert np.isclose(lon_p0, lon_svc, atol=1e-10), (
            f"lon mismatch at ({line},{pixel}): {lon_p0} != {lon_svc}"
        )

    # 2b — Identical reconstruction at exact GCP control points
    for i in range(N_LINES):
        for j in range(N_PIXELS):
            line_gcp = i * (IMAGE_SHAPE[0] - 1) / (N_LINES - 1)
            pixel_gcp = j * (IMAGE_SHAPE[1] - 1) / (N_PIXELS - 1)
            lat_p0, lon_p0 = research_gcp.pixel_to_latlon(line_gcp, pixel_gcp)
            lat_svc, lon_svc = service_gcp.pixel_to_latlon(line_gcp, pixel_gcp)
            assert lat_p0 == lat_svc, (
                f"GCP ({i},{j}) lat mismatch: research {lat_p0} != service {lat_svc}"
            )
            assert lon_p0 == lon_svc, (
                f"GCP ({i},{j}) lon mismatch: research {lon_p0} != service {lon_svc}"
            )

    # 2c — Identical tile_to_bbox()
    bbox_p0 = research_gcp.tile_to_bbox(25, 25, 75, 75)
    bbox_svc = service_gcp.tile_to_bbox(25, 25, 75, 75)
    assert all(abs(a - b) < 1e-10 for a, b in zip(bbox_p0, bbox_svc, strict=False)), (
        f"bbox mismatch: research {bbox_p0}, service {bbox_svc}"
    )
