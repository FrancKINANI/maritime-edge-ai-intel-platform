"""apply_mvssd_ops.py — Apply MVSSD-style enhancement operations to SAR tiles.

The fine-tuned detector (`yolov8n_mrssd_int8.onnx`) was trained on Sentinel-1
data augmented with the albumentations pipeline used during MVSSD fine-tuning:

    Blur(p=0.01, blur_limit=(3, 7)),
    MedianBlur(p=0.01, blur_limit=(3, 7)),
    ToGray(p=0.01, method='weighted_average', num_output_channels=3),
    CLAHE(p=0.01, clip_limit=(1.0, 4.0), tile_grid_size=(8, 8))

This script re-applies those operations (deterministically, without the
random-probability gating) on top of an existing preprocessed tile tree
(default: pipeline D) and writes a new tile tree (default: pipeline "E",
the "MVSSD-enhanced" variant). It mirrors the same output layout and
metadata.json format as the other pipelines so the tiles remain drop-in
compatible with the rest of the preprocessing tooling.

Dependencies: numpy + opencv-python (cv2). Both are already present in the
project virtualenv. albumentations itself is NOT required.

Usage (from project root):
    python services/sentinel_preprocessor/tools/apply_mvssd_ops.py
    python services/sentinel_preprocessor/tools/apply_mvssd_ops.py --ops clahe,blur,median
    python services/sentinel_preprocessor/tools/apply_mvssd_ops.py --scene S1C_IW_GRDH_1SDV_20260722T190444_20260722T190509_008660_01128F_C18A --limit 500
"""

import argparse
import json
import logging
import time
from pathlib import Path

import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("apply_mvssd_ops")

try:
    import cv2
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "opencv-python (cv2) is required. Install it with: pip install opencv-python"
    ) from e

# MVSSD albumentations configuration (deterministic defaults)
DEFAULT_CLAHE_CLIP_LIMIT = 4.0   # albumentations clip_limit range top (1.0, 4.0)
DEFAULT_CLAHE_TILE_GRID = 8      # albumentations tile_grid_size=(8, 8)
DEFAULT_BLUR_KERNEL = 5          # Blur blur_limit=(3, 7) -> deterministic odd kernel
DEFAULT_MEDIAN_KERNEL = 5        # MedianBlur blur_limit=(3, 7) -> deterministic odd kernel


def apply_clahe(tile: np.ndarray, clip_limit: float, tile_grid: int) -> np.ndarray:
    """CLAHE (Contrast Limited Adaptive Histogram Equalization) on a uint8 tile."""
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile_grid, tile_grid))
    return clahe.apply(tile)


def apply_blur(tile: np.ndarray, kernel: int) -> np.ndarray:
    """Gaussian Blur matching albumentations Blur."""
    if kernel < 3 or kernel % 2 == 0:
        raise ValueError(f"blur kernel must be an odd int >= 3, got {kernel}")
    return cv2.GaussianBlur(tile, (kernel, kernel), 0)


def apply_median_blur(tile: np.ndarray, kernel: int) -> np.ndarray:
    """Median Blur matching albumentations MedianBlur."""
    if kernel < 3 or kernel % 2 == 0:
        raise ValueError(f"median kernel must be an odd int >= 3, got {kernel}")
    return cv2.medianBlur(tile, kernel)


OPS = {
    "clahe": lambda t: apply_clahe(t, DEFAULT_CLAHE_CLIP_LIMIT, DEFAULT_CLAHE_TILE_GRID),
    "blur": lambda t: apply_blur(t, DEFAULT_BLUR_KERNEL),
    "median": lambda t: apply_median_blur(t, DEFAULT_MEDIAN_KERNEL),
}


def process_scene(
    scene_dir: Path,
    tiles_dir: Path,
    source_pipeline: str,
    output_pipeline: str,
    ops: list[str],
    limit: int | None,
) -> dict:
    """Apply the requested ops to every tile of one scene, writing a new tree."""
    src_dir = tiles_dir / scene_dir.name / source_pipeline
    meta_path = src_dir / "metadata.json"
    if not meta_path.exists():
        logger.warning(f"  No metadata.json in {src_dir}, skipping scene")
        return {"scene": scene_dir.name, "status": "skipped", "reason": "no source metadata"}

    with open(meta_path, encoding="utf-8") as f:
        src_meta = json.load(f)

    out_dir = tiles_dir / scene_dir.name / output_pipeline
    out_dir.mkdir(parents=True, exist_ok=True)

    tiles = src_meta.get("tiles", [])
    if limit:
        tiles = tiles[:limit]
    if not tiles:
        logger.warning(f"  No tiles listed in {meta_path}, skipping scene")
        return {"scene": scene_dir.name, "status": "skipped", "reason": "no tiles in metadata"}

    start = time.perf_counter()
    out_tiles = []
    for _idx, t in enumerate(tiles):
        npy_path = Path(t["npy_path"])
        if not npy_path.exists():
            # Fall back to reconstructing the path inside src_dir
            npy_path = src_dir / npy_path.name
        tile = np.load(npy_path)
        # CLAHE and the blur ops require uint8 input; convert immediately.
        if tile.dtype != np.uint8:
            tile = np.clip(tile, 0, 255).astype(np.uint8)
        for op in ops:
            tile = OPS[op](tile)
        tile = np.ascontiguousarray(tile, dtype=np.uint8)

        # Rebuild the tile id deterministically instead of string-replacing:
        # format is <scene_id>_<pipeline>_tile<NNNN>.
        _prefix, _suffix = t["tile_id"].rsplit("_", 1)
        out_tile_id = f"{_prefix}_{output_pipeline}_{_suffix}"
        out_npy = out_dir / f"{out_tile_id}.npy"
        np.save(out_npy, tile)

        out_tiles.append(
            {
                "tile_id": out_tile_id,
                "scene_id": t.get("scene_id", scene_dir.name),
                "pipeline": output_pipeline,
                "source_pipeline": source_pipeline,
                "pixel_bbox": t.get("pixel_bbox"),
                "geo_bbox": t.get("geo_bbox"),
                "npy_path": str(out_npy),
            }
        )

    elapsed = time.perf_counter() - start
    out_meta = {
        "scene_id": src_meta.get("scene_id", scene_dir.name),
        "pipeline": output_pipeline,
        "source_pipeline": source_pipeline,
        "base_pipeline": source_pipeline,
        "ops": ops,
        "op_config": {
            "clahe": {
                "clip_limit": DEFAULT_CLAHE_CLIP_LIMIT,
                "tile_grid_size": DEFAULT_CLAHE_TILE_GRID,
            },
            "blur": {"kernel": DEFAULT_BLUR_KERNEL},
            "median": {"kernel": DEFAULT_MEDIAN_KERNEL},
        },
        "tile_size": src_meta.get("tile_size"),
        "overlap": src_meta.get("overlap"),
        "polarization": src_meta.get("polarization"),
        "total_tiles": len(out_tiles),
        "valid_tiles": len(out_tiles),
        "processing_time_s": round(elapsed, 2),
        "tiles": out_tiles,
        "target_density_cell_index": src_meta.get("target_density_cell_index"),
        "target_cell_bbox": src_meta.get("target_cell_bbox"),
        "targeting_protocol": src_meta.get("targeting_protocol"),
    }
    with open(out_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(out_meta, f, indent=2)

    logger.info(
        f"  Done: {scene_dir.name} [{output_pipeline}] — {len(out_tiles)} tiles "
        f"in {elapsed:.1f}s"
    )
    return {"scene": scene_dir.name, "status": "ok", "tile_count": len(out_tiles)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply MVSSD-style ops to SAR tiles")
    parser.add_argument("--tiles-dir", default="research/data/tiles", help="Tiles root (default: research/data/tiles)")
    parser.add_argument("--source-pipeline", default="D", help="Source pipeline (default: D)")
    parser.add_argument(
        "--output-pipeline", default="E", help="Output pipeline name (default: E)"
    )
    parser.add_argument(
        "--ops",
        default="clahe",
        help="Comma-separated ops: clahe,blur,median (default: clahe)",
    )
    parser.add_argument("--scene", default=None, help="Process only this scene (optional)")
    parser.add_argument("--limit", type=int, default=None, help="Max tiles per scene (optional)")
    args = parser.parse_args()

    ops = [o.strip().lower() for o in args.ops.split(",") if o.strip()]
    unknown = [o for o in ops if o not in OPS]
    if unknown:
        raise SystemExit(f"Unknown ops: {unknown}. Valid: {sorted(OPS)}")

    tiles_dir = Path(args.tiles_dir)
    if not tiles_dir.exists():
        raise SystemExit(f"tiles dir not found: {tiles_dir}")
    scenes = sorted(tiles_dir.iterdir())
    scenes = [s for s in scenes if s.is_dir()]
    if args.scene:
        scenes = [s for s in scenes if s.name == args.scene]
        if not scenes:
            raise SystemExit(f"Scene {args.scene} not found under {tiles_dir}")

    logger.info(
        f"Applying ops {ops} from pipeline '{args.source_pipeline}' -> '{args.output_pipeline}'"
    )
    results = [
        process_scene(s, tiles_dir, args.source_pipeline, args.output_pipeline, ops, args.limit)
        for s in scenes
    ]
    ok = sum(1 for r in results if r["status"] == "ok")
    logger.info(f"Summary: {ok}/{len(results)} scenes processed successfully")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
