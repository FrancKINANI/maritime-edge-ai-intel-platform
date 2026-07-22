"""
process_all_scenes.py — Batch preprocessing for all downloaded Sentinel-1 scenes.

Usage (from notebook or CLI):
    python process_all_scenes.py --scenes-dir research/data/scenes --tiles-dir research/data/tiles

This script:
1. Finds all downloaded scenes in scenes_dir
2. For each scene that doesn't already have tiles in tiles_dir:
   - Runs process_safe_windowed(pipeline="D")
   - Injects traceability metadata into metadata.json

Prerequisite:
    The project root must be in sys.path (handled if run from the notebook).
"""

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("process_all_scenes")


def find_scenes(scenes_dir: Path) -> list[Path]:
    """Find all valid .SAFE scene directories."""
    scenes = sorted(scenes_dir.glob("*.SAFE"))
    valid = [s for s in scenes if s.is_dir()]
    logger.info(f"Found {len(valid)} scene(s) in {scenes_dir}")
    return valid


def tile_dir_for_scene(scene_path: Path, tiles_dir: Path) -> Path:
    """Return the expected tile output directory for a scene."""
    # Use the scene stem (no .SAFE)
    stem = scene_path.stem
    return tiles_dir / stem / "D"


def scene_already_processed(scene_path: Path, tiles_dir: Path) -> bool:
    """Check if a scene has already been processed into tiles."""
    td = tile_dir_for_scene(scene_path, tiles_dir)
    if not td.exists():
        return False
    # Check for metadata.json and at least some .npy files
    meta = td / "metadata.json"
    if not meta.exists():
        return False
    npy_files = list(td.glob("*.npy"))
    return len(npy_files) > 0


def inject_traceability(scene_path: Path, tiles_dir: Path) -> None:
    """Propagate target_trace.json fields into the tile metadata.json."""
    trace_path = scene_path / "target_trace.json"
    td = tile_dir_for_scene(scene_path, tiles_dir)
    meta_path = td / "metadata.json"

    if not trace_path.exists():
        logger.info(f"  No target_trace.json for {scene_path.name}, skipping trace injection")
        return
    if not meta_path.exists():
        logger.warning(f"  metadata.json not found at {meta_path}, cannot inject trace")
        return

    with open(trace_path, encoding="utf-8") as f:
        trace = json.load(f)

    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)

    # Inject trace fields (do not overwrite existing values)
    changed = False
    for key in ["target_density_cell_index", "target_cell_bbox", "targeting_protocol"]:
        if key in trace and key not in meta:
            meta[key] = trace[key]
            changed = True

    if changed:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        logger.info(f"  Traceability injected into {meta_path.name}")
    else:
        logger.info(f"  Traceability already present in {meta_path.name}")


def process_scene(scene_path: Path, tiles_dir: Path, pipeline: str = "D") -> dict:
    """Process a single scene: run preprocessing + inject traceability.

    Returns a dict with status, tile_count, and processing_time.
    """
    from research.scripts.sar_preprocessing import process_safe_windowed

    start = time.time()
    scene_name = scene_path.name
    logger.info(f"  Processing: {scene_name} ...")

    try:
        result = process_safe_windowed(
            safe_path=str(scene_path),
            pipeline_name=pipeline,
            output_dir=str(tiles_dir),
            polarization="vv",
            tile_size=512,
            overlap=0.5,
        )
    except Exception as e:
        logger.error(f"  FAILED: {scene_name} — {e}")
        return {"scene": scene_name, "status": "failed", "error": str(e)}

    elapsed = time.time() - start
    tile_count = 0
    if isinstance(result, dict):
        tile_count = result.get("valid_tiles", result.get("tile_count", 0))
    elif isinstance(result, int):
        tile_count = result

    # Inject traceability metadata
    inject_traceability(scene_path, tiles_dir)

    logger.info(f"  Done: {scene_name} — {tile_count} tiles in {elapsed:.1f}s")
    return {
        "scene": scene_name,
        "status": "ok",
        "tile_count": tile_count,
        "processing_time_s": round(elapsed, 1),
    }


def process_all_scenes(
    scenes_dir: Path,
    tiles_dir: Path,
    pipeline: str = "D",
    force: bool = False,
) -> list[dict]:
    """Process all downloaded scenes that haven't been processed yet.

    Args:
        scenes_dir: Directory with .SAFE subdirectories.
        tiles_dir: Output directory for tile .npy files.
        pipeline: SAR preprocessing pipeline name (default: "D").
        force: If True, re-process already-processed scenes.

    Returns:
        List of result dicts (one per scene).
    """
    scenes_dir = Path(scenes_dir)
    tiles_dir = Path(tiles_dir)
    tiles_dir.mkdir(parents=True, exist_ok=True)

    scenes = find_scenes(scenes_dir)
    results = []

    for scene_path in scenes:
        if not force and scene_already_processed(scene_path, tiles_dir):
            logger.info(f"  Skipping {scene_path.name} (already processed)")
            results.append({
                "scene": scene_path.name,
                "status": "skipped",
                "tile_count": 0,
            })
            continue

        r = process_scene(scene_path, tiles_dir, pipeline)
        results.append(r)

    # Summary
    ok = sum(1 for r in results if r["status"] == "ok")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    failed = sum(1 for r in results if r["status"] == "failed")
    total_tiles = sum(r.get("tile_count", 0) for r in results)

    logger.info(
        f"\n{'='*50}\n"
        f"PROCESSING SUMMARY\n"
        f"  Total scenes: {len(results)}  |  OK: {ok}  Skipped: {skipped}  Failed: {failed}\n"
        f"  Total tiles generated: {total_tiles}\n"
        f"{'='*50}"
    )

    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Batch SAR preprocessing for all scenes")
    parser.add_argument("--scenes-dir", default="research/data/scenes", help="Scenes directory")
    parser.add_argument("--tiles-dir", default="research/data/tiles", help="Tiles output directory")
    parser.add_argument("--pipeline", default="D", help="SAR pipeline name")
    parser.add_argument("--force", action="store_true", help="Re-process already processed scenes")
    parser.add_argument("--summary", action="store_true", help="Print JSON summary")
    args = parser.parse_args()

    results = process_all_scenes(
        Path(args.scenes_dir),
        Path(args.tiles_dir),
        args.pipeline,
        force=args.force,
    )

    if args.summary:
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
