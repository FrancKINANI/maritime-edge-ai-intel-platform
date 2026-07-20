#!/usr/bin/env python3
"""
Build Fine-Tuning Dataset — Package AIS annotations into YOLO format
=====================================================================

Scans scene directories under ``phase0/data/annotations/``, maps each
YOLO label file to its corresponding PNG image, applies quality filters,
splits by **scene** (configurable), and exports a clean YOLO dataset
ready for Ultralytics fine-tuning.

Usage::

    # Use all available scenes (auto-detect from annotations directory)
    uv run python phase_post0/build_finetune_dataset.py

    # Specify scenes explicitly and custom split
    uv run python phase_post0/build_finetune_dataset.py \\
        --scenes S1D_20260711 S1D_20260716 \\
        --split train val test \\
        --output phase_post0/dataset_5scenes

    # Dry-run (discover scenes and counts without building)
    uv run python phase_post0/build_finetune_dataset.py --dry-run

Output::

    <output>/
    ├── images/
    │   ├── train/   (*.png)
    │   ├── val/     (*.png)
    │   └── test/    (*.png)
    ├── labels/
    │   ├── train/   (*.txt)
    │   ├── val/     (*.txt)
    │   └── test/    (*.txt)
    ├── data.yaml
    └── dataset_summary.json
"""

import argparse
import json
import logging
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
from PIL import Image

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("build_dataset")

TILE_SIZE = 512
NODATA_THRESHOLD = 0.3  # max 30% black/zero pixels


# ---------------------------------------------------------------------------
# Scene discovery
# ---------------------------------------------------------------------------

def discover_scenes(annotations_root: Path, allowed_satellites: Optional[List[str]] = None) -> List[Dict]:
    """Scan annotations root and return list of scene dicts.

    Each scene dict contains::
        {
            "scene_id": str,           # directory name
            "short_id": str,           # short name (first 3 underscore parts)
            "label_dir": Path,         # labels/ with .txt files
            "image_dir": Path,         # cvat_import/images/ with .png files
            "n_labels": int,           # number of label files
            "n_images": int,           # number of PNG images in cvat_import/
            "total_boxes": int,        # total annotation lines across all labels
        }
    """
    scenes = []
    for child in sorted(annotations_root.iterdir()):
        if not child.is_dir():
            continue

        scene_id = child.name
        # Skip non-scene dirs (e.g. hidden, config)
        if scene_id.startswith("."):
            continue

        # Filter by allowed satellites if specified
        scene_platform = get_satellite_platform(scene_id)
        if allowed_satellites and scene_platform not in allowed_satellites:
            logger.info(f"Skipping {scene_id}: platform {scene_platform} not in allowed list {allowed_satellites}")
            continue

        label_dir = child / "labels"
        image_dir = child / "cvat_import" / "images"

        if not label_dir.is_dir() or not image_dir.is_dir():
            logger.debug(f"Skipping {scene_id}: missing labels/ or cvat_import/images/")
            continue

        label_files = sorted(label_dir.glob("*.txt"))
        png_files = sorted(image_dir.glob("*.png"))

        if not label_files:
            logger.debug(f"Skipping {scene_id}: no label files found")
            continue

        # Count total annotation lines
        total_boxes = 0
        for lf in label_files:
            try:
                total_boxes += len(lf.read_text().strip().splitlines())
            except Exception:
                pass

        # Build a short ID from the first 3 parts of the scene name
        parts = scene_id.split("_")
        short_id = "_".join(parts[:3]) if len(parts) >= 3 else scene_id

        scene_info = {
            "scene_id": scene_id,
            "short_id": short_id,
            "label_dir": label_dir,
            "image_dir": image_dir,
            "n_labels": len(label_files),
            "n_images": len(png_files),
            "total_boxes": total_boxes,
        }
        scenes.append(scene_info)
        logger.info(
            f"Discovered {scene_info['short_id']}: {scene_info['n_labels']} labels, "
            f"{scene_info['total_boxes']} boxes, {scene_info['n_images']} images"
        )

    return scenes


# ---------------------------------------------------------------------------
# Quality filters
# ---------------------------------------------------------------------------

def check_bbox_bounds(
    label_path: Path,
) -> Tuple[bool, List[str]]:
    """Check all bboxes in a label file are within [0, 1] bounds.

    Only structural failures cause the tile to be skipped:
    - Missing values, non-numeric data, zero/negative size
    - Values outside [0, 1]

    Minor issues (negative class ID) are logged as warnings
    but do NOT cause tile rejection.

    Returns (is_valid, list_of_issues).
    """
    issues = []
    structural_failure = False
    try:
        lines = label_path.read_text().strip().splitlines()
    except Exception as e:
        return False, [f"Cannot read {label_path}: {e}"]

    for i, line in enumerate(lines):
        parts = line.strip().split()
        if len(parts) != 5:
            issues.append(f"Line {i+1}: expected 5 parts, got {len(parts)}")
            structural_failure = True
            continue
        try:
            cls_id = int(parts[0])
            cx, cy, w, h = map(float, parts[1:5])
        except ValueError:
            issues.append(f"Line {i+1}: non-numeric values")
            structural_failure = True
            continue

        if cls_id < 0:
            issues.append(f"Line {i+1}: negative class ID (will be clamped to 0)")
            # Do NOT mark as structural failure — can be fixed

        # Bbox values must be in [0, 1]
        for name, val in [("cx", cx), ("cy", cy), ("w", w), ("h", h)]:
            if val < 0.0 or val > 1.0:
                issues.append(f"Line {i+1}: {name}={val} outside [0, 1]")
                structural_failure = True

        # Bbox must have positive size
        if w <= 0.0 or h <= 0.0:
            issues.append(f"Line {i+1}: zero or negative size w={w}, h={h}")
            structural_failure = True

    return not structural_failure, issues


def check_nodata_ratio(image_path: Path, threshold: float = NODATA_THRESHOLD) -> Tuple[bool, float]:
    """Check if image has excessive NoData (black/zero) pixels.

    Returns (is_valid, nodata_ratio).
    """
    try:
        img = Image.open(image_path).convert("L")
        arr = np.array(img, dtype=np.uint8)
    except Exception as e:
        logger.warning(f"Cannot read {image_path}: {e}")
        return False, 1.0

    zero_ratio = float(np.sum(arr == 0)) / float(arr.size)
    return zero_ratio <= threshold, zero_ratio


def find_duplicate_boxes(label_path: Path) -> List[str]:
    """Detect duplicate bounding boxes in a label file.

    Two boxes are considered duplicates if their coordinates
    are identical (exact match). Returns list of issue strings.

    NOTE: This detects only exact duplicates. Near-duplicates
    (same location, slightly different size) are not flagged —
    they may represent legitimate overlapping vessels.
    """
    issues = []
    try:
        lines = label_path.read_text().strip().splitlines()
    except Exception:
        return issues

    seen: Set[str] = set()
    for i, line in enumerate(lines):
        parts = line.strip().split()
        if len(parts) == 5:
            coords = " ".join(parts[1:5])  # cx cy w h
            if coords in seen:
                issues.append(f"Line {i+1}: duplicate bbox ({coords})")
            seen.add(coords)

    return issues


def filter_scene_tiles(
    scene: Dict,
    check_nodata: bool = True,
    skip_empty_labels: bool = True,
) -> List[Tuple[str, Path, Path]]:
    """Return list of valid (tile_id, image_path, label_path) for this scene.

    Applies:
    1. Label file must exist (skip if empty)
    2. Corresponding PNG must exist
    3. Bbox bounds check (all coordinates in [0,1])
    4. NoData ratio check (optional)
    5. Duplicate box removal (fixes the file in place)
    """
    valid_tiles: List[Tuple[str, Path, Path]] = []
    label_dir = scene["label_dir"]
    image_dir = scene["image_dir"]

    for label_path in sorted(label_dir.glob("*.txt")):
        tile_id = label_path.stem

        # Skip empty labels
        if skip_empty_labels and label_path.stat().st_size == 0:
            logger.debug(f"  Skip {tile_id}: empty label")
            continue

        # Check bbox bounds — only skip on structural failures
        bounds_ok, bbox_issues = check_bbox_bounds(label_path)
        if not bounds_ok:
            for issue in bbox_issues:
                logger.warning(f"  Bbox issue {tile_id}: {issue}")
            continue  # structural failure, skip tile
        elif bbox_issues:
            for issue in bbox_issues:
                logger.warning(f"  Bbox warning {tile_id}: {issue} (proceeding)")

        # Check for duplicates and fix
        dup_issues = find_duplicate_boxes(label_path)
        if dup_issues:
            # Remove duplicates in-place
            lines = label_path.read_text().strip().splitlines()
            seen: Set[str] = set()
            clean_lines = []
            for line in lines:
                parts = line.strip().split()
                if len(parts) == 5:
                    coords = " ".join(parts[1:5])
                    if coords in seen:
                        logger.warning(f"  Removed duplicate in {tile_id}: {coords}")
                        continue
                    seen.add(coords)
                clean_lines.append(line)
            label_path.write_text("\n".join(clean_lines) + "\n")
            logger.info(f"  Cleaned {len(lines) - len(clean_lines)} duplicate(s) from {tile_id}")

        # Find corresponding PNG
        png_path = image_dir / f"{tile_id}.png"
        if not png_path.exists():
            logger.warning(f"  Skip {tile_id}: PNG not found at {png_path}")
            continue

        # NoData check
        if check_nodata:
            nd_ok, nd_ratio = check_nodata_ratio(png_path)
            if not nd_ok:
                logger.info(
                    f"  Skip {tile_id}: {nd_ratio:.1%} NoData "
                    f"(threshold {NODATA_THRESHOLD:.0%})"
                )
                continue

        valid_tiles.append((tile_id, png_path, label_path))

    return valid_tiles


# ---------------------------------------------------------------------------
# Dataset assembly
# ---------------------------------------------------------------------------

def get_satellite_platform(scene_id: str) -> str:
    """Extract satellite platform from scene ID (e.g., 'S1C', 'S1D', 'S1A')."""
    parts = scene_id.split("_")
    for p in parts:
        if p.startswith("S1") and len(p) >= 3:
            return p[:3]
    return "UNKNOWN"


def _split_tile_list_geographic(
    tiles: List[Tuple[str, Path, Path]],
    ratios: Tuple[float, float, float],
) -> Tuple[List, List, List]:
    """Split a tile list geographically by contiguous chunks.

    Tiles are sorted by tile_id (which encodes spatial position in
    row-major order). Taking contiguous chunks avoids data leakage
    between adjacent tiles.

    Args:
        tiles: List of (tile_id, png_path, label_path) tuples.
        ratios: (train_pct, val_pct, test_pct) summing to ~1.0.

    Returns:
        (train_tiles, val_tiles, test_tiles).
    """
    if not tiles:
        return [], [], []
    sorted_tiles = sorted(tiles, key=lambda t: t[0])  # sort by tile_id
    n = len(sorted_tiles)
    train_pct, val_pct, test_pct = ratios
    total = train_pct + val_pct + test_pct

    n_train = int(n * train_pct / total)
    n_val = int(n * val_pct / total)

    train = sorted_tiles[:n_train]
    val = sorted_tiles[n_train:n_train + n_val]
    test = sorted_tiles[n_train + n_val:]

    return train, val, test


def _stratify_by_platform(
    scenes: List[Dict],
    valid_by_scene: Dict[str, List],
    ratios: Tuple[float, float, float] = (70, 15, 15),
) -> Dict[str, List[Tuple[str, Path, Path]]]:
    """Stratify split by satellite platform.

    Groups scenes by platform (S1C, S1D, etc.), then applies a geographic
    split within each platform group. This ensures each split (train/val/test)
    has the SAME proportion of each satellite platform, decoupling the
    platform generalization question from the simulated→real domain shift.

    Args:
        scenes: List of scene dicts from discover_scenes().
        valid_by_scene: Dict scene_id -> list of valid (tile_id, png, label).
        ratios: (train_pct, val_pct, test_pct).

    Returns:
        assigned dict with keys 'train', 'val', 'test'.
    """
    assigned: Dict[str, List] = {"train": [], "val": [], "test": []}

    # Group tiles by platform
    platform_tiles: Dict[str, List] = {}
    for scene in scenes:
        sid = scene["scene_id"]
        plat = get_satellite_platform(sid)
        platform_tiles.setdefault(plat, []).extend(valid_by_scene.get(sid, []))

    logger.info(
        f"Stratified split by platform: "
        + ", ".join(f"{p}: {len(t)} tiles" for p, t in sorted(platform_tiles.items()))
    )

    # Apply geo-split within each platform group
    for plat, tiles in sorted(platform_tiles.items()):
        t, v, te = _split_tile_list_geographic(tiles, ratios)
        assigned["train"].extend(t)
        assigned["val"].extend(v)
        assigned["test"].extend(te)
        logger.info(
            f"  {plat}: {len(tiles)} tiles → train({len(t)}) val({len(v)}) test({len(te)})"
        )

    # Log final composition per split
    for split_name in ["train", "val", "test"]:
        tiles = assigned[split_name]
        if not tiles:
            continue
        counts: Dict[str, int] = {}
        for tile_id, _, _ in tiles:
            plat = get_satellite_platform(tile_id)
            counts[plat] = counts.get(plat, 0) + 1
        summary = ", ".join(f"{p}: {c} ({100*c/len(tiles):.0f}%)" for p, c in sorted(counts.items()))
        logger.info(f"  {split_name}: {len(tiles)} tiles → {summary}")

    return assigned


def assign_splits_by_scene(
    scenes: List[Dict],
    valid_by_scene: Dict[str, List],
    split_plan: List[str],
    geo_split: Optional[Dict[str, Tuple[float, float, float]]] = None,
    stratify: bool = False,
) -> Dict[str, List[Tuple[str, Path, Path]]]:
    """Assign each scene to a split bucket based on the split plan.

    If ``stratify=True``, scenes are grouped by satellite platform and each
    platform receives its own geo-split, ensuring consistent platform
    proportions across train/val/test.

    The split_plan lists scene IDs in order::
        ["scene1_train", "scene2_train", "scene3_val", "scene4_test"]

    If ``geo_split`` is provided for a scene, its tiles are split
    geographically across splits (train/val/test) according to the
    given ratios, instead of being assigned to a single split.

    Example geo_split::
        {
            "S1D_IW_...9C83": (70, 15, 15),  # 70% train, 15% val, 15% test
        }

    Or uses a proportional split if no plan is given.
    """
    # Build lookup: scene_id -> valid tiles
    scene_tiles = {
        scene["scene_id"]: valid_by_scene[scene["scene_id"]]
        for scene in scenes
    }

    assigned: Dict[str, List] = {"train": [], "val": [], "test": []}

    # Stratified by platform takes highest priority
    if stratify:
        return _stratify_by_platform(scenes, valid_by_scene)

    if split_plan and len(split_plan) == len(scenes):
        for scene_id, split_name in zip(
            [s["scene_id"] for s in scenes], split_plan
        ):
            if scene_id in (geo_split or {}):
                ratios = geo_split[scene_id]
                t, v, te = _split_tile_list_geographic(
                    scene_tiles.get(scene_id, []), ratios
                )
                assigned["train"].extend(t)
                assigned["val"].extend(v)
                assigned["test"].extend(te)
                logger.info(
                    f"  {scene_id[:30]}... → train({len(t)}) val({len(v)}) "
                    f"test({len(te)}) [geo-split {ratios[0]}/{ratios[1]}/{ratios[2]}]"
                )
            else:
                if split_name not in assigned:
                    logger.warning(f"Unknown split '{split_name}', defaulting to train")
                    split_name = "train"
                assigned[split_name].extend(scene_tiles.get(scene_id, []))
                logger.info(
                    f"  {scene_id[:30]}... → {split_name} "
                    f"({len(scene_tiles.get(scene_id, []))} tiles)"
                )
        return assigned

    # Default: proportional split (60/20/20 by scene count)
    n_scenes = len(scenes)
    if n_scenes >= 3:
        n_train = max(1, int(n_scenes * 0.6))
        n_val = max(1, int(n_scenes * 0.2))
        n_test = n_scenes - n_train - n_val
        if n_test < 1:
            n_test = 1
            n_val = n_scenes - n_train - n_test
    elif n_scenes == 2:
        n_train, n_val, n_test = 1, 0, 1
    else:
        n_train, n_val, n_test = 1, 0, 0

    for i, scene in enumerate(scenes):
        sid = scene["scene_id"]
        tiles = scene_tiles.get(sid, [])

        if sid in (geo_split or {}):
            ratios = geo_split[sid]
            t, v, te = _split_tile_list_geographic(tiles, ratios)
            assigned["train"].extend(t)
            assigned["val"].extend(v)
            assigned["test"].extend(te)
            logger.info(
                f"  {sid[:30]}... → train({len(t)}) val({len(v)}) "
                f"test({len(te)}) [geo-split {ratios[0]}/{ratios[1]}/{ratios[2]}]"
            )
        elif i < n_train:
            assigned["train"].extend(tiles)
            logger.info(f"  {sid[:30]}... → train ({len(tiles)} tiles)")
        elif i < n_train + n_val:
            assigned["val"].extend(tiles)
            logger.info(f"  {sid[:30]}... → val ({len(tiles)} tiles)")
        else:
            assigned["test"].extend(tiles)
            logger.info(f"  {sid[:30]}... → test ({len(tiles)} tiles)")

    return assigned


def build_dataset(
    scenes: List[Dict],
    output_dir: Path,
    split_plan: Optional[List[str]] = None,
    geo_split: Optional[Dict[str, Tuple[float, float, float]]] = None,
    stratify: bool = False,
    check_nodata: bool = True,
    force: bool = False,
) -> Dict:
    """Build the full YOLO dataset.

    Args:
        scenes: List of scene dicts from discover_scenes().
        output_dir: Where to write the YOLO dataset.
        split_plan: Optional explicit split assignment per scene.
                    Length must match len(scenes).
        geo_split: Optional dict scene_id -> (train%, val%, test%) for
                   geographic in-scene splitting.
        stratify: If True, stratify by satellite platform (overrides split_plan).
        check_nodata: Whether to apply NoData filter.
        force: Overwrite output_dir if it exists.

    Returns:
        Summary dict with split counts, class info, etc.
    """
    if output_dir.exists():
        if force:
            shutil.rmtree(output_dir)
        else:
            raise FileExistsError(
                f"Output directory {output_dir} already exists. "
                "Use --force to overwrite."
            )

    # Filter tiles per scene
    valid_by_scene: Dict[str, List] = {}
    total_before = 0
    total_after = 0

    for scene in scenes:
        sid = scene["scene_id"]
        logger.info(f"Filtering {scene['short_id']} ({scene['n_labels']} labels)...")
        valid = filter_scene_tiles(scene, check_nodata=check_nodata)
        valid_by_scene[sid] = valid
        total_before += scene["n_labels"]
        total_after += len(valid)
        logger.info(f"  → {len(valid)}/{scene['n_labels']} tiles passed filters "
                    f"({scene['total_boxes']} boxes)")

    logger.info(f"Total: {total_after}/{total_before} tiles passed filters")

    # Assign splits
    assigned = assign_splits_by_scene(scenes, valid_by_scene, split_plan or [],
                                       geo_split=geo_split, stratify=stratify)

    # Create directory structure and copy files
    for split_name in ["train", "val", "test"]:
        tiles_list = assigned.get(split_name, [])
        if not tiles_list:
            continue

        img_out = output_dir / "images" / split_name
        lbl_out = output_dir / "labels" / split_name
        img_out.mkdir(parents=True, exist_ok=True)
        lbl_out.mkdir(parents=True, exist_ok=True)

        for tile_id, png_path, label_path in tiles_list:
            shutil.copy2(str(png_path), str(img_out / f"{tile_id}.png"))
            shutil.copy2(str(label_path), str(lbl_out / f"{tile_id}.txt"))

        logger.info(f"{split_name}: {len(tiles_list)} tiles → {img_out}")

    # Count total annotations in the output
    total_images = sum(len(v) for v in assigned.values())
    total_boxes = 0
    for split_name in ["train", "val", "test"]:
        for _, _, label_path in assigned.get(split_name, []):
            try:
                total_boxes += len(label_path.read_text().strip().splitlines())
            except Exception:
                pass

    # Write data.yaml
    # NOTE: path='.' makes all paths relative to the YAML file's directory.
    # This is required for Colab compatibility (absolute local paths won't exist).
    yaml_content = (
        f"# Maritime Vessel Detection Dataset\n"
        f"# Generated: {json.dumps({'scenes': [s['scene_id'] for s in scenes]})}\n"
        f"\n"
        f"path: .\n"
        f"train: images/train\n"
        f"val: images/val\n"
        f"test: images/test\n"
        f"\n"
        f"nc: 1\n"
        f"names: ['vessel']\n"
    )
    yaml_path = output_dir / "data.yaml"
    yaml_path.write_text(yaml_content)
    logger.info(f"data.yaml written → {yaml_path}")

    # Write dataset_summary.json
    summary = {
        "total_images": total_images,
        "total_boxes": total_boxes,
        "classes": ["vessel"],
        "class_counts": {"vessel": total_boxes},
        "split": {
            "train": len(assigned.get("train", [])),
            "val": len(assigned.get("val", [])),
            "test": len(assigned.get("test", [])),
        },
        "scenes": [
            {"id": s["scene_id"], "short_id": s["short_id"],
             "labels": s["n_labels"], "boxes": s["total_boxes"]}
            for s in scenes
        ],
        "filters": {
            "nodata_threshold": NODATA_THRESHOLD,
            "check_nodata": check_nodata,
            "tiles_before_filter": total_before,
            "tiles_after_filter": total_after,
        },
        "config": {
            "image_size": TILE_SIZE,
            "format": "YOLO",
            "classes": 1,
        },
    }
    summary_path = output_dir / "dataset_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    logger.info(f"Summary written → {summary_path}")

    # Warn if training set is too small
    n_train = len(assigned.get("train", []))
    if n_train < 30:
        logger.warning(
            f"Training set has only {n_train} images — fine-tuning on so few "
            f"images is unlikely to produce meaningful results. "
            f"Add more scenes (via the download notebook) before training."
        )

    # Print final table
    print()
    print("=" * 60)
    print("  DATASET SUMMARY")
    print("=" * 60)
    print(f"  Total images: {total_images}")
    print(f"  Total boxes:  {total_boxes}")
    print(f"  Classes:      1 (vessel)")
    print(f"  Image size:   {TILE_SIZE}x{TILE_SIZE}")
    for split_name in ["train", "val", "test"]:
        n = len(assigned.get(split_name, []))
        if n > 0:
            print(f"  {split_name}: {n} images")
    print("=" * 60)
    print(f"  Output: {output_dir.resolve()}")
    print(f"  Config: {yaml_path}")
    print("=" * 60)

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build YOLO fine-tuning dataset from AIS annotations"
    )
    parser.add_argument(
        "--annotations", "-a",
        default="phase0/data/annotations",
        help="Root annotations directory (default: phase0/data/annotations/)",
    )
    parser.add_argument(
        "--output", "-o",
        default="phase_post0/dataset_finetune",
        help="Output directory for YOLO dataset (default: phase_post0/dataset_finetune/)",
    )
    parser.add_argument(
        "--split", "-s",
        nargs="+",
        default=None,
        help="Explicit split plan per scene in order: train train val test ... "
             "(must match number of discovered scenes)",
    )
    parser.add_argument(
        "--satellites", "-L",
        nargs="+",
        default=["S1A", "S1B", "S1C", "S1D"],
        help="Allowed satellite platforms (e.g. S1D or S1C,S1D). Scenes from "
             "other platforms are skipped. Default: all Sentinel-1 (S1A/B/C/D).",
    )
    parser.add_argument(
        "--stratify", "-t",
        action="store_true",
        help="Stratify split by satellite platform (S1C, S1D, etc.). Each platform "
             "receives its own geographic split, ensuring consistent platform "
             "proportions across train/val/test. Use this when mixing scenes from "
             "different Sentinel-1 satellites (S1A, S1B, S1C, S1D).",
    )
    parser.add_argument(
        "--geo-split", "-g",
        nargs="+",
        default=None,
        help="Geographic split within a scene: scene_id:train:val:test "
             "(e.g. S1D_scene_id:70:15:15). Splits tiles by contiguous "
             "geographic chunks based on tile ID order.",
    )
    parser.add_argument(
        "--scenes", "-S",
        nargs="+",
        default=None,
        help="Only use specific scenes (by short_id prefix, e.g. S1D_20260711)",
    )
    parser.add_argument(
        "--no-nodata-check",
        action="store_true",
        help="Skip NoData ratio check (speeds up processing)",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Discover scenes and report counts without building",
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Overwrite output directory if it exists",
    )
    parser.add_argument(
        "--zip", "-z",
        action="store_true",
        help="Create a ZIP archive of the dataset for Colab upload",
    )

    args = parser.parse_args()

    # Resolve paths relative to project root
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent  # maritime-intelligence-platform/
    annotations_root = (project_root / args.annotations).resolve()
    output_dir = (project_root / args.output).resolve()

    if not annotations_root.is_dir():
        logger.error(f"Annotations directory not found: {annotations_root}")
        sys.exit(1)

    logger.info(f"Scanning annotations in {annotations_root}")

    # Discover scenes
    all_scenes = discover_scenes(annotations_root, allowed_satellites=args.satellites)

    if not all_scenes:
        logger.error("No valid scenes found. Check --annotations path.")
        sys.exit(1)

    # Filter by --scenes if provided
    if args.scenes:
        filtered = []
        for prefix in args.scenes:
            matched = [s for s in all_scenes if s["short_id"].startswith(prefix)]
            if not matched:
                logger.warning(f"No scene matching '{prefix}'")
            filtered.extend(matched)
        scenes = filtered
    else:
        scenes = all_scenes

    if not scenes:
        logger.error("No scenes match the filter.")
        sys.exit(1)

    logger.info(f"Found {len(scenes)} scene(s) to process")

    # Parse geo-split specs
    geo_split: Optional[Dict[str, Tuple[float, float, float]]] = None
    if args.geo_split:
        geo_split = {}
        for spec in args.geo_split:
            parts = spec.split(":")
            if len(parts) != 4:
                logger.error(f"Invalid geo-split spec: '{spec}'. Use scene_id:train:val:test")
                sys.exit(1)
            scene_id = parts[0]
            try:
                ratios = (float(parts[1]), float(parts[2]), float(parts[3]))
            except ValueError:
                logger.error(f"Invalid ratios in geo-split spec: '{spec}'")
                sys.exit(1)
            geo_split[scene_id] = ratios
            logger.info(f"Geo-split: {scene_id[:30]}... → {ratios[0]:.0f}/{ratios[1]:.0f}/{ratios[2]:.0f}")

    # Validate split plan
    split_plan = args.split
    if split_plan and len(split_plan) != len(scenes):
        logger.error(
            f"Split plan has {len(split_plan)} entries but "
            f"{len(scenes)} scenes found: "
            + ", ".join(s["short_id"] for s in scenes)
        )
        logger.error("Either adjust --split or omit it for auto-assignment.")
        sys.exit(1)

    # Dry-run
    if args.dry_run:
        print()
        print("=" * 60)
        print("  DRY RUN — Scenes discovered")
        print("=" * 60)
        n_images = sum(s["n_labels"] for s in scenes)
        for i, scene in enumerate(scenes):
            split_label = split_plan[i] if split_plan else "auto"
            print(f"  [{i}] {scene['scene_id']}")
            print(f"      Labels:  {scene['n_labels']} files")
            print(f"      Boxes:   {scene['total_boxes']} annotations")
            print(f"      Images:  {scene['n_images']} PNGs in cvat_import/")
            print(f"      Split:   {split_label}")
            print()
        total_boxes = sum(s["total_boxes"] for s in scenes)
        print(f"  Total: {len(scenes)} scenes, {total_boxes} boxes")
        print()
        # Estimate split outcome
        if len(scenes) >= 3:
            n_train = max(1, int(len(scenes) * 0.6))
        else:
            n_train = 1 if len(scenes) >= 1 else 0
        train_scenes = scenes[:n_train]
        train_images = sum(s["n_labels"] for s in train_scenes)
        if train_images < 30:
            logger.warning(
                f"Estimated training set: {train_images} images — too few for "
                f"meaningful fine-tuning. Download at least 3-5 more scenes "
                f"before training (target: 100+ training images)."
            )
        print("=" * 60)
        return

    # Build
    summary = build_dataset(
        scenes,
        output_dir,
        split_plan=split_plan,
        geo_split=geo_split,
        stratify=args.stratify,
        check_nodata=not args.no_nodata_check,
        force=args.force,
    )

    # Optional ZIP creation
    if args.zip:
        zip_path = output_dir.parent / f"{output_dir.name}.zip"
        logger.info(f"Creating ZIP archive: {zip_path}")
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for fpath in output_dir.rglob("*"):
                if fpath.is_file():
                    arcname = fpath.relative_to(output_dir.parent)
                    zf.write(fpath, arcname)
        zip_size = zip_path.stat().st_size / (1024 * 1024)
        logger.info(f"ZIP created: {zip_path} ({zip_size:.0f} MB)")


if __name__ == "__main__":
    main()
