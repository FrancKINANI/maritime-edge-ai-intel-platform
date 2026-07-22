#!/usr/bin/env python3
"""
Fix Bounding Box Sizes — Replace fixed-size YOLO labels with realistic variable sizes
======================================================================================

Root cause identified (Phase Post-0):
  All 29,968 boxes in the dataset have IDENTICAL width (0.015625 ≈ 8px) and
  height (0.02 ≈ 10px) because `estimate_bbox_yolo()` in `gfw_annotations.py`
  used a hard-coded minimum size of 8px, clamping every vessel to the same
  tiny box regardless of its actual length.

  This caused mAP@0.5 = 0 during fine-tuning: YOLO predicts boxes of varied
  sizes (from its anchors), but every Ground Truth box is 8×10px. No predicted
  box can achieve IoU > 0.5 against a fixed 8×10 GT box, so mAP stays at 0
  even if the model detects vessels at the correct locations.

Fix (Option B):
  Replace fixed-size boxes with statistically sampled vessel dimensions based
  on a global distribution (60% small 10-40m, 30% medium 40-120m, 10% large
  120-350m), multiplied by a SAR blooming factor (1.8-3.5x) and ±20% jitter,
  with a seeded RNG (seed=42) for reproducibility.

Usage:
    # Fix all scenes in-place
    uv run python phase_post0/fix_bbox_sizes.py

    # Dry-run: show distribution without modifying files
    uv run python phase_post0/fix_bbox_sizes.py --dry-run

    # Only analyze current distribution
    uv run python phase_post0/fix_bbox_sizes.py --analyze
"""

import argparse
import logging
import math
import random
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("fix_bbox_sizes")

TILE_SIZE = 512
RNG_SEED = 42

ANNOTATIONS_ROOT = Path("research/data/annotations")


# ---------------------------------------------------------------------------
# Statistical vessel size model (same as gfw_annotations.py)
# ---------------------------------------------------------------------------


def _sample_vessel_dimensions(rng: random.Random) -> tuple[float, float]:
    """Sample vessel dimensions WITHOUT type info (global distribution).

    Same model as `_sample_vessel_dimensions()` in gfw_annotations.py
    but with vessel_type=None (global 60/30/10 split).

    Returns (effective_length_m, aspect_ratio_length_width).
    """
    roll = rng.random()
    if roll < 0.60:
        length_min, length_max = 10.0, 40.0  # small fishing
    elif roll < 0.90:
        length_min, length_max = 40.0, 120.0  # medium
    else:
        length_min, length_max = 120.0, 350.0  # large tanker/cargo

    log_min = math.log(length_min)
    log_max = math.log(length_max)
    physical_length_m = math.exp(rng.uniform(log_min, log_max))

    # SAR blooming factor
    bloom_factor = rng.uniform(1.8, 3.5)
    jitter = rng.uniform(0.8, 1.2)
    effective_length_m = physical_length_m * bloom_factor * jitter

    aspect_ratio = rng.uniform(3.0, 6.0)

    return effective_length_m, aspect_ratio


def sample_bbox_size(rng: random.Random) -> tuple[float, float]:
    """Sample a realistic (width, height) in YOLO normalized coordinates.

    Returns (w, h) both in [0.001, 1.0].
    """
    effective_length_m, aspect_ratio = _sample_vessel_dimensions(rng)

    # Convert to pixels at 10m/pixel resolution
    length_px = effective_length_m / 10.0
    width_px = length_px / aspect_ratio

    # Enforce minimum size
    length_px = max(3.0, length_px)
    width_px = max(1.5, width_px)

    # Normalize to YOLO coordinates [0, 1]
    w = min(1.0, max(0.001, length_px / TILE_SIZE))
    h = min(1.0, max(0.001, width_px / TILE_SIZE))

    return w, h


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def analyze_distribution() -> dict:
    """Analyze current box size distribution across all scenes.

    Returns dict with statistics.
    """
    widths, heights = [], []
    total_boxes = 0
    fixed_width = None
    fixed_height = None
    is_all_fixed = True

    for scene_dir in sorted(ANNOTATIONS_ROOT.iterdir()):
        if not scene_dir.is_dir() or scene_dir.name.startswith("."):
            continue

        label_dir = scene_dir / "labels"
        if not label_dir.is_dir():
            continue

        for label_path in sorted(label_dir.glob("*.txt")):
            try:
                text = label_path.read_text().strip()
            except Exception as e:
                logger.warning("Failed to read %s: %s", label_path, e)
                continue

            for line in text.splitlines():
                parts = line.strip().split()
                if len(parts) != 5:
                    continue
                try:
                    w, h = float(parts[3]), float(parts[4])
                except ValueError:
                    continue

                widths.append(w)
                heights.append(h)
                total_boxes += 1

                if fixed_width is None:
                    fixed_width = w
                    fixed_height = h
                elif w != fixed_width or h != fixed_height:
                    is_all_fixed = False

    stats = {
        "total_boxes": total_boxes,
        "all_fixed_size": is_all_fixed,
        "fixed_width": fixed_width,
        "fixed_height": fixed_height,
        "unique_widths": len(set(round(w, 6) for w in widths)),
        "unique_heights": len(set(round(h, 6) for h in heights)),
    }

    if widths:
        import numpy as np

        stats.update(
            {
                "w_mean": float(np.mean(widths)),
                "w_std": float(np.std(widths)),
                "w_min": float(np.min(widths)),
                "w_max": float(np.max(widths)),
                "h_mean": float(np.mean(heights)),
                "h_std": float(np.std(heights)),
                "h_min": float(np.min(heights)),
                "h_max": float(np.max(heights)),
            }
        )

    return stats


def report_distribution(stats: dict, label: str = "Current"):
    """Print a formatted distribution report."""
    print()
    print("=" * 60)
    print(f"  {label} BOX SIZE DISTRIBUTION")
    print("=" * 60)
    print(f"  Total boxes:          {stats['total_boxes']}")
    print(f"  All identical sizes:  {stats['all_fixed_size']}")
    if stats.get("w_mean") is not None:
        print(f"  Width  (norm): {stats['w_mean']:.6f} ± {stats['w_std']:.6f}")
        print(f"           min={stats['w_min']:.6f}  max={stats['w_max']:.6f}")
        print(f"  Height (norm): {stats['h_mean']:.6f} ± {stats['h_std']:.6f}")
        print(f"           min={stats['h_min']:.6f}  max={stats['h_max']:.6f}")
        print(
            f"  Width  (px):   {stats['w_mean'] * TILE_SIZE:.1f} ± {stats['w_std'] * TILE_SIZE:.1f}"
        )
        print(
            f"  Height (px):   {stats['h_mean'] * TILE_SIZE:.1f} ± {stats['h_std'] * TILE_SIZE:.1f}"
        )
        print(f"  Unique widths:  {stats['unique_widths']}")
        print(f"  Unique heights: {stats['unique_heights']}")
    print("=" * 60)
    print()


# ---------------------------------------------------------------------------
# Fix
# ---------------------------------------------------------------------------


def fix_scene_labels(scene_dir: Path, rng: random.Random, dry_run: bool = False) -> int:
    """Fix all YOLO label files in a scene directory.

    Returns number of boxes modified.
    """
    label_dir = scene_dir / "labels"
    if not label_dir.is_dir():
        logger.debug(f"No labels dir in {scene_dir}")
        return 0

    modified = 0
    for label_path in sorted(label_dir.glob("*.txt")):
        try:
            lines = label_path.read_text().strip().splitlines()
        except Exception as e:
            logger.warning("Failed to read %s: %s", label_path, e)
            continue

        new_lines = []
        for line in lines:
            parts = line.strip().split()
            if len(parts) != 5:
                new_lines.append(line)
                continue

            try:
                cls_id = int(parts[0])
                cx, cy = float(parts[1]), float(parts[2])
                _w_old, _h_old = float(parts[3]), float(parts[4])
            except ValueError:
                new_lines.append(line)
                continue

            # Generate new variable-size bbox
            w_new, h_new = sample_bbox_size(rng)
            new_line = f"{cls_id} {cx:.6f} {cy:.6f} {w_new:.6f} {h_new:.6f}"
            new_lines.append(new_line)
            modified += 1

        if not dry_run:
            label_path.write_text("\n".join(new_lines) + "\n")

    return modified


def fix_all_scenes(dry_run: bool = False) -> int:
    """Fix bbox sizes in all scenes.

    Returns total boxes modified.
    """
    rng = random.Random(RNG_SEED)
    total_modified = 0
    fixed_scenes = []

    for scene_dir in sorted(ANNOTATIONS_ROOT.iterdir()):
        if not scene_dir.is_dir() or scene_dir.name.startswith("."):
            continue

        n = fix_scene_labels(scene_dir, rng, dry_run=dry_run)
        if n > 0:
            fixed_scenes.append((scene_dir.name, n))
            total_modified += n

    if dry_run:
        logger.info(
            f"[DRY-RUN] Would modify {total_modified} boxes across {len(fixed_scenes)} scenes"
        )
    else:
        logger.info(f"Fixed {total_modified} boxes across {len(fixed_scenes)} scenes")

    return total_modified


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Fix fixed-size YOLO labels with variable-sized bboxes"
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be changed without modifying files",
    )
    parser.add_argument(
        "--analyze", "-a", action="store_true", help="Only analyze current distribution, don't fix"
    )
    args = parser.parse_args()

    # Step 1: Analyze current distribution
    current_stats = analyze_distribution()
    report_distribution(current_stats, "CURRENT")

    if args.analyze:
        return

    if current_stats["total_boxes"] == 0:
        logger.error("No labels found to fix.")
        sys.exit(1)

    # Step 2: Fix
    if not current_stats["all_fixed_size"]:
        logger.warning(
            "Box sizes are NOT all identical — they may have already been fixed. "
            "Running fix anyway (seeded RNG ensures reproducibility)."
        )

    if args.dry_run:
        logger.info("[DRY-RUN] Running fix without writing...")

    fix_all_scenes(dry_run=args.dry_run)

    # Step 3: Verify fix
    if not args.dry_run:
        new_stats = analyze_distribution()
        report_distribution(new_stats, "FIXED")
        logger.info(
            f"Before: {current_stats['unique_widths']} unique widths, "
            f"{current_stats['unique_heights']} unique heights"
        )
        logger.info(
            f"After:  {new_stats['unique_widths']} unique widths, "
            f"{new_stats['unique_heights']} unique heights"
        )


if __name__ == "__main__":
    main()
