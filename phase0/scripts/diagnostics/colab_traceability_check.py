"""
COLAB TRACEABILITY VERIFICATION — DO NOT RUN LOCALLY
====================================================

Purpose:
    End-to-end test of the AIS density-targeted scene selection traceability chain.
    Must be executed on Colab (or any machine with CDSE + GFW credentials).

Protocol (PH0-CORR-002 Part B):
    1. Build AIS density map via GFW API
    2. Download ONE scene via select_and_download_scenes_from_density()
    3. Verify target_trace.json is written in the .SAFE directory
    4. Run process_safe_windowed() on that scene
    5. Verify target_density_cell_index and target_cell_bbox are propagated in metadata.json
    6. Confirm correspondence between the two files

Usage:
    Copy each section into its own Colab cell and execute sequentially.
    Do NOT run this script as-is locally -- it requires Colab infrastructure.

Author: Phase 0 diagnostics
"""
# ruff: noqa: E402 — Cells 2 and 3 contain imports that are intentionally
# NOT at the top of the file. This is a Colab script where each cell is
# executed independently, so imports are placed in the cell that needs them.

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║ CELL 1 — Environment setup                                                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

import subprocess
import sys
import os
from pathlib import Path

# Install project dependencies
subprocess.check_call(
    [sys.executable, "-m", "pip", "install",
     "httpx", "numpy", "rasterio", "scipy", "tqdm", "psutil", "python-dotenv"]
)

# Clone the repository (or mount Google Drive if already cloned)
if not Path("maritime-intelligence-platform").exists():
    subprocess.check_call([
        "git", "clone",
        "https://github.com/FrancKINANI/maritime-edge-ai-intel-platform.git"
    ])
    os.chdir("maritime-intelligence-platform")
else:
    os.chdir("maritime-intelligence-platform")
    subprocess.check_call(["git", "pull"])  # Ensure latest version

# Option B: Google Drive mount (faster if already cloned)
# from google.colab import drive
# drive.mount('/content/drive')
# %cd /content/drive/MyDrive/path/to/maritime-intelligence-platform

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║ CELL 2 — Credentials                                                       ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# Set credentials from Colab secrets or user input
# Required: CDSE_USERNAME, CDSE_PASSWORD, GFW_API_TOKEN

import getpass

CDSE_USERNAME = os.getenv("CDSE_USERNAME") or getpass.getpass("CDSE username: ")
CDSE_PASSWORD = os.getenv("CDSE_PASSWORD") or getpass.getpass("CDSE password: ")
GFW_API_TOKEN = os.getenv("GFW_API_TOKEN") or getpass.getpass("GFW API token: ")

os.environ["CDSE_USERNAME"] = CDSE_USERNAME
os.environ["CDSE_PASSWORD"] = CDSE_PASSWORD
os.environ["GFW_API_TOKEN"] = GFW_API_TOKEN

print("Credentials set.")

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║ CELL 3 — Import project modules                                           ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

import sys
sys.path.insert(0, ".")

import json
from pathlib import Path

# NOTE: logging.basicConfig is called by the imported modules themselves
# at import time. Do NOT call it again here to avoid duplicate handlers.

from phase0.scripts.download_scenes import (
    build_ais_density_map,
    select_and_download_scenes_from_density,
    get_cdse_token,
    MOROCCO_BBOX,
)
from phase0.scripts.sar_preprocessing import process_safe_windowed

SCENES_DIR = Path("phase0/data/scenes")
SCENES_DIR.mkdir(parents=True, exist_ok=True)

print("Modules imported.")

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║ CELL 4 — Build AIS density map                                            ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# Query GFW AIS Presence over the Morocco bbox, 30-day lookback
density_map = build_ais_density_map(
    bbox=MOROCCO_BBOX,
    cell_size_deg=0.5,
    lookback_days=30,
    gfw_token=GFW_API_TOKEN,
)

print(f"Total AIS positions retrieved: {density_map.get('total_positions', 0)}")
print(f"Non-empty cells: {density_map.get('n_cells_with_data', 0)}")
print(f"Period: {density_map.get('period', 'N/A')}")

top_cells = density_map.get("cells", [])[:5]
for i, cell in enumerate(top_cells):
    print(f"  Zone {i+1}: cell_index={cell['cell_index']}, "
          f"bbox={cell['cell_bbox']}, AIS count={cell['count']}")

if not density_map.get("cells"):
    raise RuntimeError(
        "Density map empty — GFW returned no AIS positions. "
        "The GFW API token may be expired or the bbox has no recent vessel traffic. "
        "Check the GFW API token and try increasing lookback_days."
    )

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║ CELL 5 — CDSE authentication                                              ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

token, expiry_time = get_cdse_token(CDSE_USERNAME, CDSE_PASSWORD)
print("CDSE authentication successful.")

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║ CELL 6 — Download ONE scene (density-targeted)                            ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# ⚠ Download only 1 scene for the verification test.
# ⚠ If you re-run this cell, delete the existing .SAFE directory first:
#      rm -rf phase0/data/scenes/<scene-name>.SAFE
#    Otherwise select_and_download_scenes_from_density() will skip the
#    download AND NOT write target_trace.json, causing Cell 7 to fail.
downloaded = select_and_download_scenes_from_density(
    token=token,
    density_map=density_map,
    n_scenes=1,  # ← Strictly 1, do NOT change for the verification test
    output_dir=SCENES_DIR,
    username=CDSE_USERNAME,
    password=CDSE_PASSWORD,
)

if len(downloaded) == 0:
    raise RuntimeError(
        "No scene downloaded. Possible reasons:\n"
        "  1. No Sentinel-1 products available for the top density zones\n"
        "  2. CDSE credentials are invalid or expired\n"
        "  3. The top density zones fall outside Sentinel-1 coverage\n"
        "Check the logs above and retry."
    )

print(f"Downloaded scene: {downloaded[0]}")

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║ CELL 7 — Show target_trace.json (RAW content)                             ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# json and Path already imported in Cell 3

scene_path = Path(downloaded[0])
trace_path = scene_path / "target_trace.json"

if trace_path.exists():
    with open(trace_path) as f:
        target_trace = json.load(f)
    print("=" * 60)
    print("TARGET_TRACE.JSON (RAW)")
    print("=" * 60)
    print(json.dumps(target_trace, indent=2))
    print("=" * 60)

    # Verify structure
    assert "target_density_cell_index" in target_trace, (
        "Missing target_density_cell_index in target_trace.json"
    )
    assert "target_cell_bbox" in target_trace, (
        "Missing target_cell_bbox in target_trace.json"
    )
    assert len(target_trace["target_cell_bbox"]) == 4, (
        f"target_cell_bbox must have 4 elements, "
        f"got {len(target_trace['target_cell_bbox'])}"
    )
    print("✅ target_trace.json structure valid")
else:
    raise FileNotFoundError(
        f"target_trace.json not found at {trace_path}\n"
        "The density-targeted download did not write the trace file. "
        "Check select_and_download_scenes_from_density() implementation."
    )

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║ CELL 8 — Run SAR preprocessing (Pipeline D) on the downloaded scene       ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# process_safe_windowed already imported in Cell 3

TILES_DIR = Path("phase0/data/tiles")

print("Running process_safe_windowed on the downloaded scene...")
print("This will take several minutes (processing tile-by-tile).")

result = process_safe_windowed(
    safe_path=str(scene_path),
    pipeline_name="D",
    output_dir=str(TILES_DIR),
    polarization="vv",
    tile_size=512,
    overlap=0.5,
)

print(f"Processing complete: {result['valid_tiles']} valid tiles generated.")
print(f"Processing time: {result['processing_time_s']:.2f}s")

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║ CELL 9 — Show metadata.json (RAW content, traceability fields)            ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

scene_id = result["scene_id"]
pipeline = result["pipeline"]
metadata_path = TILES_DIR / scene_id / pipeline / "metadata.json"

if not metadata_path.exists():
    raise FileNotFoundError(f"metadata.json not found at {metadata_path}")

with open(metadata_path) as f:
    metadata = json.load(f)

print("=" * 60)
print("METADATA.JSON — TRACEABILITY FIELDS")
print("=" * 60)
print(f"  target_density_cell_index: {metadata.get('target_density_cell_index')}")
print(f"  target_cell_bbox:           {metadata.get('target_cell_bbox')}")
print(f"  targeting_protocol:         {metadata.get('targeting_protocol')}")
print("=" * 60)

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║ CELL 10 — Verify correspondence                                           ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

print("=" * 60)
print("CORRESPONDENCE VERIFICATION")
print("=" * 60)

# Re-read target_trace for comparison
with open(trace_path) as f:
    target_trace = json.load(f)

print(f"  target_trace.json → target_density_cell_index: {target_trace['target_density_cell_index']}")
print(f"  metadata.json     → target_density_cell_index: {metadata['target_density_cell_index']}")
print(f"  MATCH: {target_trace['target_density_cell_index'] == metadata['target_density_cell_index']}")

print()
print(f"  target_trace.json → target_cell_bbox: {target_trace['target_cell_bbox']}")
print(f"  metadata.json     → target_cell_bbox: {metadata['target_cell_bbox']}")
print(f"  MATCH: {target_trace['target_cell_bbox'] == metadata['target_cell_bbox']}")

print()
print(f"  target_trace.json → protocol: {target_trace.get('protocol')}")
print(f"  metadata.json     → targeting_protocol: {metadata.get('targeting_protocol')}")
print(f"  MATCH: {target_trace.get('protocol') == metadata.get('targeting_protocol')}")

# Assert all correspondences
assert target_trace["target_density_cell_index"] == metadata["target_density_cell_index"], (
    f"MISMATCH: cell_index differs between target_trace.json "
    f"({target_trace['target_density_cell_index']}) and metadata.json "
    f"({metadata['target_density_cell_index']})"
)
assert target_trace["target_cell_bbox"] == metadata["target_cell_bbox"], (
    f"MISMATCH: cell_bbox differs between target_trace.json "
    f"({target_trace['target_cell_bbox']}) and metadata.json "
    f"({metadata['target_cell_bbox']})"
)
assert target_trace.get("protocol") == metadata.get("targeting_protocol"), (
    f"MISMATCH: protocol differs between target_trace.json "
    f"({target_trace.get('protocol')}) and metadata.json "
    f"({metadata.get('targeting_protocol')})"
)

print()
print("=" * 60)
print("✅ TRACEABILITY VERIFICATION PASSED")
print("=" * 60)
print()
print("The AIS density-targeted scene selection chain is fully functional:")
print("  1. AIS density map → identifies high-traffic zones")
print("  2. Density-targeted download → selects scenes in those zones")
print("  3. target_trace.json → records the targeting decision in the .SAFE dir")
print("  4. process_safe_windowed() → propagates trace fields into metadata.json")
print("  5. All 3 trace fields (cell_index, cell_bbox, protocol) match across files")
print()
print("⚠ You can now proceed to download the remaining 16 scenes.")
print("   Adjust n_scenes in CELL 6 and re-run from that cell.")
