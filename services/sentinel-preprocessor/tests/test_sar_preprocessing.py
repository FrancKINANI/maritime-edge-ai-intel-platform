"""Unit tests for SAR preprocessing functions."""

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest
from sar_preprocessing import (
    calibrate_sigma0,
    apply_lee_filter,
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
    expected = (100.0 ** 2) / (1.0 ** 2)
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
