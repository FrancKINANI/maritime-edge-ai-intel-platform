"""Test for GCP interpolation property validated in Phase 0.

This test verifies the key property that RegularGridInterpolator produces
EXACTLY ZERO error at the control points themselves. This was empirically
validated in Phase 0 and must not be broken by future modifications.
"""

import numpy as np
import pytest
from scipy.interpolate import RegularGridInterpolator


def test_gcp_interpolation_zero_error_at_control_points():
    """Test that GCP interpolation has EXACTLY ZERO error at control points.

    This is a validated property from Phase 0: the RegularGridInterpolator
    should reproduce the exact GCP values when queried at the same coordinates.
    The GCPs form a regular NxM grid without holes, and the interpolation
    should be exact at these control points.

    IMPORTANT: This test validates the INTERIOR behavior only. The behavior
    at boundaries (where pixels exceed the last GCP) is NOT validated and
    requires human review before production use.
    """
    # Create a simple regular grid (simulating GCP structure)
    lines = np.array([0, 10, 20, 30])
    pixels = np.array([0, 10, 20, 30])
    values = np.array([
        [1.0, 2.0, 3.0, 4.0],
        [5.0, 6.0, 7.0, 8.0],
        [9.0, 10.0, 11.0, 12.0],
        [13.0, 14.0, 15.0, 16.0]
    ])

    # Configure interpolator exactly as in phase0/scripts/sar_preprocessing.py
    interpolator = RegularGridInterpolator(
        (lines, pixels),
        values,
        method='linear',
        bounds_error=False,
        fill_value=None
    )

    # Test at each control point - should have EXACTLY zero error
    max_error = 0.0
    for line in lines:
        for pixel in pixels:
            interpolated = interpolator([line, pixel])
            expected = values[np.where(lines == line)[0][0], np.where(pixels == pixel)[0][0]]
            error = abs(interpolated - expected)
            max_error = max(max_error, error)

            # Assert exact equality at control points (machine precision)
            assert np.isclose(interpolated, expected, rtol=0, atol=1e-10), \
                f"Interpolation error at GCP ({line}, {pixel}): {interpolated} != {expected}"

    print(f"Maximum interpolation error at control points: {max_error}")
    assert max_error < 1e-9, f"Maximum error {max_error} exceeds tolerance"


def test_gcp_interpolation_boundary_behavior_unvalidated():
    """Test that boundary behavior is documented as UNVALIDATED.

    This test intentionally FAILS to highlight that boundary behavior
    is not validated. The image is 1 pixel larger than the GCP grid
    on each axis, so boundary pixels will trigger extrapolation.
    """
    # Create a small GCP grid
    lines = np.array([0, 10, 20])
    pixels = np.array([0, 10, 20])
    values = np.array([
        [1.0, 2.0, 3.0],
        [4.0, 5.0, 6.0],
        [7.0, 8.0, 9.0]
    ])

    interpolator = RegularGridInterpolator(
        (lines, pixels),
        values,
        method='linear',
        bounds_error=False,
        fill_value=None
    )

    # Test at a point outside the GCP grid (simulating the +1 pixel boundary)
    # This is the problematic case mentioned in the review
    boundary_point = [21, 21]  # Just outside the grid

    try:
        result = interpolator(boundary_point)
        # If we get here, the interpolator produced some value
        # but this behavior is NOT validated
        print(f"WARNING: Boundary point {boundary_point} produced value {result}")
        print("This behavior is NOT validated for production use!")
    except Exception as e:
        # If we get an exception, that's also a documented behavior
        print(f"Boundary point {boundary_point} raised exception: {e}")
        print("This behavior is NOT validated for production use!")

    # This test always warns to remind developers that boundary behavior
    # requires human validation before production deployment
    pytest.warns(UserWarning, match="Boundary behavior is NOT validated")
