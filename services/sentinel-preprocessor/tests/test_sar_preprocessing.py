"""Unit tests for SAR preprocessing and GCP georeferencing functions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest
from sar_preprocessing_module import (
    GCPGeoreferencer,
    GCPOutOfBoundsError,
    apply_lee_filter,
    calibrate_sigma0,
    convert_to_db,
    normalize_to_uint8,
)


def test_calibrate_sigma0_pure():
    """Test that calibration produces valid sigma0 values."""
    data = np.array([[100, 200], [300, 400]], dtype=np.uint16)
    calibration_lut = np.array([[1.0, 1.5], [2.0, 2.5]], dtype=np.float32)

    result = calibrate_sigma0(data, calibration_lut)

    # Result should be non-negative
    assert np.all(result >= 0)
    # Result should be float32
    assert result.dtype == np.float32
    # Check specific calculation for one pixel
    expected = (100.0**2) / (1.0**2)
    assert np.isclose(result[0, 0], expected)


def test_calibrate_sigma0_zero_handling():
    """Test that zero values in calibration LUT are handled safely."""
    data = np.array([[100, 200]], dtype=np.uint16)
    calibration_lut = np.array([[0.0, 1.5]], dtype=np.float32)

    result = calibrate_sigma0(data, calibration_lut)

    # Should not produce NaN or inf
    assert not np.any(np.isnan(result))
    assert not np.any(np.isinf(result))


def test_lee_filter_output_shape():
    """Test that Lee filter preserves input shape."""
    data = np.random.rand(100, 100).astype(np.float32)
    result = apply_lee_filter(data, kernel_size=5)

    assert result.shape == data.shape
    assert result.dtype == np.float32


def test_convert_to_db():
    """Test dB conversion produces valid output."""
    data = np.array([[0.01, 0.1, 1.0, 10.0]], dtype=np.float32)
    result = convert_to_db(data)

    # dB values should be negative for values < 1
    assert result[0, 0] < 0
    assert result[0, 1] < 0
    # dB value should be 0 for value == 1
    assert np.isclose(result[0, 2], 0.0, atol=1e-6)
    # dB value should be positive for value > 1
    assert result[0, 3] > 0


def test_convert_to_db_zero_handling():
    """Test that zero values are handled safely in dB conversion."""
    data = np.array([[0.0, 0.01]], dtype=np.float32)
    result = convert_to_db(data)

    # Should not produce NaN or inf
    assert not np.any(np.isnan(result))
    assert not np.any(np.isinf(result))


def test_normalize_to_uint8():
    """Test normalization to uint8 produces valid range."""
    data = np.array([[-30.0, -15.0, 0.0, 15.0]], dtype=np.float32)
    result = normalize_to_uint8(data, db_min=-30.0, db_max=0.0)

    # Result should be uint8
    assert result.dtype == np.uint8
    # Values should be in [0, 255]
    assert np.all(result >= 0)
    assert np.all(result <= 255)
    # -30 dB should map to 0
    assert result[0, 0] == 0
    # 0 dB should map to 255
    assert result[0, 2] == 255


def test_normalize_to_uint8_clipping():
    """Test that values outside range are clipped."""
    data = np.array([[-40.0, -30.0, 0.0, 10.0]], dtype=np.float32)
    result = normalize_to_uint8(data, db_min=-30.0, db_max=0.0)

    # -40 dB should be clipped to 0
    assert result[0, 0] == 0
    # 10 dB should be clipped to 255
    assert result[0, 3] == 255


# ---------------------------------------------------------------------------
# GCP Georeferencer Tests
# ---------------------------------------------------------------------------


def test_gcp_georeferencer_zero_error_at_control_points():
    """Test that GCP interpolation has EXACTLY ZERO error at control points.

    This is a validated property: the RegularGridInterpolator reproduces the
    exact GCP values when queried at the same coordinates. The GCPs form a
    regular NxM grid, and interpolation is exact at control points.
    """
    # Simulate a 4x4 GCP grid over a 30x30 pixel image
    gcps = np.array(
        [
            [[35.0, -5.0], [35.5, -4.5], [36.0, -4.0], [36.5, -3.5]],
            [[35.2, -5.2], [35.7, -4.7], [36.2, -4.2], [36.7, -3.7]],
            [[35.4, -5.4], [35.9, -4.9], [36.4, -4.4], [36.9, -3.9]],
            [[35.6, -5.6], [36.1, -5.1], [36.6, -4.6], [37.1, -4.1]],
        ],
        dtype=np.float64,
    )

    geo = GCPGeoreferencer(gcps, image_shape=(30, 30))

    # Query at GCP positions — error must be zero (machine precision)
    # Use the actual GCP coordinate vectors computed by the georeferencer
    # (np.linspace(0, image_h-1, n_lines) and np.linspace(0, image_w-1, n_pixels))
    gcp_lines = geo._gcp_lines.tolist()
    gcp_pixels = geo._gcp_pixels.tolist()
    for i, line in enumerate(gcp_lines):
        for j, pix in enumerate(gcp_pixels):
            lat, lon = geo.pixel_to_latlon(float(line), float(pix))
            assert np.isclose(lat, gcps[i, j, 0], rtol=0, atol=1e-10), (
                f"Lat error at GCP ({line}, {pix}): {lat} != {gcps[i, j, 0]}"
            )
            assert np.isclose(lon, gcps[i, j, 1], rtol=0, atol=1e-10), (
                f"Lon error at GCP ({line}, {pix}): {lon} != {gcps[i, j, 1]}"
            )


def test_gcp_georeferencer_interior_interpolation():
    """Test that GCP interpolation produces reasonable values between control points."""
    gcps = np.array(
        [
            [[35.0, -5.0], [36.0, -4.0]],
            [[36.0, -6.0], [37.0, -5.0]],
        ],
        dtype=np.float64,
    )

    geo = GCPGeoreferencer(gcps, image_shape=(10, 10))

    # Midpoint between GCPs should be approximately midway in value
    # GCP lines = np.linspace(0, 9, 2) = [0, 9], pixels = [0, 9]
    # At (5,5) bilinear interpolation gives lat = 36.111..., lon = -5.0
    lat, lon = geo.pixel_to_latlon(5.0, 5.0)
    assert 35.5 < lat < 37.0, f"Interior lat {lat} outside expected range [35.5, 37.0]"
    assert -5.5 < lon < -4.5, f"Interior lon {lon} outside expected range [-5.5, -4.5]"


def test_gcp_georeferencer_out_of_bounds_raises():
    """Test that GCPOutOfBoundsError is raised for pixels outside the GCP grid.

    This is the explicit safeguard: boundary behavior is NOT validated, so
    an exception must be raised rather than improvising border management.
    """
    gcps = np.array(
        [
            [[35.0, -5.0], [36.0, -4.0]],
            [[36.0, -6.0], [37.0, -5.0]],
        ],
        dtype=np.float64,
    )

    geo = GCPGeoreferencer(gcps, image_shape=(10, 10))

    # GCP lines = [0, 9], pixels = [0, 9]
    # A pixel at line=10 or pixel=10 is outside the grid
    with pytest.raises(GCPOutOfBoundsError, match="outside the GCP grid"):
        geo.pixel_to_latlon(10.0, 5.0)  # line out of bounds

    with pytest.raises(GCPOutOfBoundsError, match="outside the GCP grid"):
        geo.pixel_to_latlon(5.0, 10.0)  # pixel out of bounds

    with pytest.raises(GCPOutOfBoundsError, match="outside the GCP grid"):
        geo.pixel_to_latlon(-1.0, 5.0)  # line negative

    with pytest.raises(GCPOutOfBoundsError, match="outside the GCP grid"):
        geo.pixel_to_latlon(5.0, -1.0)  # pixel negative


def test_gcp_georeferencer_valid_bounds_are_accepted():
    """Test that pixels strictly within the GCP grid are accepted."""
    gcps = np.array(
        [
            [[35.0, -5.0], [36.0, -4.0]],
            [[36.0, -6.0], [37.0, -5.0]],
        ],
        dtype=np.float64,
    )

    geo = GCPGeoreferencer(gcps, image_shape=(10, 10))

    # GCP lines = [0, 9], pixels = [0, 9]
    # Pixel at (9, 9) is the LAST GCP — should work
    lat, lon = geo.pixel_to_latlon(9.0, 9.0)
    assert np.isclose(lat, 37.0, atol=1e-10)
    assert np.isclose(lon, -5.0, atol=1e-10)

    # Pixel at (0, 0) is the FIRST GCP — should work
    lat, lon = geo.pixel_to_latlon(0.0, 0.0)
    assert np.isclose(lat, 35.0, atol=1e-10)
    assert np.isclose(lon, -5.0, atol=1e-10)


def test_gcp_georeferencer_tile_to_bbox():
    """Test that tile_to_bbox computes geographic bounds from pixel coordinates."""
    gcps = np.array(
        [
            [[35.0, -5.0], [36.0, -4.0]],
            [[36.0, -6.0], [37.0, -5.0]],
        ],
        dtype=np.float64,
    )

    geo = GCPGeoreferencer(gcps, image_shape=(10, 10))

    # Tile covering the full image (0,0) -> (10,10)
    # The top-right corner (0, 9) = GCP[0,1] = (36.0, -4.0)
    # But (9, 9) = GCP[1,1] = (37.0, -5.0)
    # So: lat_min should be 35.0 (from (0,0)), lat_max should be 37.0 (from (9,9))
    # And: lon_min should be -6.0 (from (9,0)), lon_max should be -4.0 (from (0,9))
    bbox = geo.tile_to_bbox(0, 0, 10, 10)
    assert len(bbox) == 4
    assert np.isclose(bbox[0], 35.0, atol=1e-6)  # lat_min
    assert np.isclose(bbox[1], -6.0, atol=1e-6)  # lon_min
    assert np.isclose(bbox[2], 37.0, atol=1e-6)  # lat_max
    assert np.isclose(bbox[3], -4.0, atol=1e-6)  # lon_max


def test_gcp_georeferencer_invalid_gcp_shape():
    """Test that invalid GCP array shapes are rejected."""
    with pytest.raises(ValueError, match=r"GCP array must be \(N, M, 2\)"):
        GCPGeoreferencer(np.array([[1.0, 2.0]]), image_shape=(10, 10))  # 2D, not 3D

    with pytest.raises(ValueError, match=r"GCP array must be \(N, M, 2\)"):
        GCPGeoreferencer(np.ones((5, 5, 3)), image_shape=(10, 10))  # last dim != 2
