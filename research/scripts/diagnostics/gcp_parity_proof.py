"""Manual diagnostic script -- produces a detailed point-by-point comparison
between the research and service GCP implementations.

Complements test_gcp_cross_implementation.py (which provides an automated
PASS/FAIL verdict) without replacing it. Run manually whenever there is
doubt about a georeferencing divergence.

Usage:
    cd <project-root>
    uv run python research/scripts/diagnostics/gcp_parity_proof.py
"""

import importlib.util
import sys

import numpy as np

sys.path.insert(0, ".")

# 1. Load service module via importlib (hyphen-proof)
spec = importlib.util.spec_from_file_location(
    "service_sar",
    "services/sentinel_preprocessor/sar_preprocessing_module.py",
)
if spec is None:
    print("FATAL: could not locate services/sentinel_preprocessor/sar_preprocessing_module.py")
    sys.exit(1)

mod = importlib.util.module_from_spec(spec)
sys.modules["service_sar"] = mod
spec.loader.exec_module(mod)
print("SUCCESS: Service module loaded via importlib")

ServiceGCPGeoreferencer = mod.GCPGeoreferencer

# 2. Import research implementation
from research.scripts.sar_preprocessing import (  # noqa: E402
    GCPGeoreferencer as researchGCPGeoreferencer,
)

# 3. Same synthetic GCP set as the test
n_lines, n_pixels = 5, 5
image_shape = (100, 100)
gcps = np.zeros((n_lines, n_pixels, 2), dtype=np.float64)
for i in range(n_lines):
    for j in range(n_pixels):
        gcps[i, j, 0] = 30.0 + i * 0.1
        gcps[i, j, 1] = -10.0 + j * 0.1

research_gcp = researchGCPGeoreferencer(gcps, image_shape)
service_gcp = ServiceGCPGeoreferencer(gcps, image_shape)

print()
print("=== GCP CONTROL POINT COMPARISON (research vs service) ===")
test_points = [(0, 0), (0, 25), (0, 99), (25, 0), (25, 25), (50, 50), (75, 25), (99, 99)]
for line, pixel in test_points:
    lat_p0, lon_p0 = research_gcp.pixel_to_latlon(line, pixel)
    lat_svc, lon_svc = service_gcp.pixel_to_latlon(line, pixel)
    dlat = lat_p0 - lat_svc
    dlon = lon_p0 - lon_svc
    is_match = abs(dlat) < 1e-12 and abs(dlon) < 1e-12
    print(
        f"  ({line:2d},{pixel:2d}): lat diff = {dlat:.2e}, lon diff = {dlon:.2e}  MATCH={is_match}"
    )

print()
print("=== ZERO-ERROR AT GCP CONTROL POINTS ===")
all_zero_p0 = True
all_zero_svc = True
for i in range(n_lines):
    for j in range(n_pixels):
        line_gcp = i * (image_shape[0] - 1) / (n_lines - 1)
        pixel_gcp = j * (image_shape[1] - 1) / (n_pixels - 1)
        lat_p0, _ = research_gcp.pixel_to_latlon(line_gcp, pixel_gcp)
        lat_svc, _ = service_gcp.pixel_to_latlon(line_gcp, pixel_gcp)
        err_p0 = abs(lat_p0 - gcps[i, j, 0])
        err_svc = abs(lat_svc - gcps[i, j, 0])
        if err_p0 > 1e-10:
            all_zero_p0 = False
        if err_svc > 1e-10:
            all_zero_svc = False
        print(f"  GCP ({i},{j}): research err = {err_p0:.2e}, service err = {err_svc:.2e}")
print(f"  research ALL zero-error: {all_zero_p0}")
print(f"  service ALL zero-error: {all_zero_svc}")

print()
print("=== tile_to_bbox() COMPARISON ===")
bbox_p0 = research_gcp.tile_to_bbox(25, 25, 75, 75)
bbox_svc = service_gcp.tile_to_bbox(25, 25, 75, 75)
print(f"  research bbox: {bbox_p0}")
print(f"  service bbox: {bbox_svc}")
print(f"  IDENTICAL: {bbox_p0 == bbox_svc}")

print()
print("=== VERDICT ===")
identical = True
for line, pixel in test_points:
    lat_p0, lon_p0 = research_gcp.pixel_to_latlon(line, pixel)
    lat_svc, lon_svc = service_gcp.pixel_to_latlon(line, pixel)
    if abs(lat_p0 - lat_svc) > 1e-12 or abs(lon_p0 - lon_svc) > 1e-12:
        identical = False
if identical and bbox_p0 == bbox_svc:
    print("  PASS: Both implementations produce IDENTICAL results on all inputs.")
else:
    print("  FAIL: Implementations diverge.")
