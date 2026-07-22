#!/usr/bin/env python3
"""
Export Colab Dataset — Package AIS annotations for Google Colab fine-tuning
============================================================================
Usage::

    # Export dataset (creates ZIP in research/data/colab_export/)
    uv run python research/scripts/export_colab_dataset.py

    # Specify custom input/output paths
    uv run python research/scripts/export_colab_dataset.py \\
        --input research/data/cvat_annotated_only \\
        --output research/data/colab_export \\
        --split 80 10 10

Output::

    research/data/colab_export/
    ├── maritime_dataset.zip          ← Upload this to Colab (~320 MB)
    ├── colab_finetune_yolo.ipynb     ← The Colab notebook
    └── dataset_summary.json          ← Metadata about the dataset
"""

import argparse
import json
import logging
import random
import shutil
import sys
import zipfile
from pathlib import Path

logger = logging.getLogger("export_colab")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLASS_NAMES = [
    "vessel_AIS_confirmed",
    "vessel_visual_only",
    "vessel_dark_vessel_candidate",
]

TEMP_DIR = "_colab_temp"


def parse_yolo_label(txt_path: Path) -> int:
    """Count the number of boxes in a YOLO label file."""
    if not txt_path.exists():
        return 0
    text = txt_path.read_text().strip()
    return len(text.splitlines()) if text else 0


def build_flat_dataset(input_dir: Path, output_dir: Path, split: tuple[float, float, float]):
    """Merge scenes into a flat YOLO dataset with train/val/test split."""
    train_pct, val_pct, test_pct = split
    assert abs(train_pct + val_pct + test_pct - 100) < 0.01, "Split must sum to 100"

    # Collect all image-label pairs
    pairs: list[tuple[Path, Path]] = []
    for scene_dir in sorted(input_dir.iterdir()):
        if not scene_dir.is_dir():
            continue
        images_dir = scene_dir / "images"
        labels_dir = scene_dir / "labels"
        if not images_dir.exists() or not labels_dir.exists():
            continue
        for img_path in sorted(images_dir.glob("*.png")):
            label_path = labels_dir / f"{img_path.stem}.txt"
            if label_path.exists():
                pairs.append((img_path, label_path))

    if not pairs:
        logger.error("No image-label pairs found in %s", input_dir)
        sys.exit(1)

    logger.info(
        "Found %d image-label pairs across %d scenes",
        len(pairs),
        len([d for d in input_dir.iterdir() if d.is_dir()]),
    )

    # Shuffle deterministically
    random.seed(42)
    random.shuffle(pairs)

    # Split
    n = len(pairs)
    n_train = int(n * train_pct / 100)
    n_val = int(n * val_pct / 100)
    n_test = n - n_train - n_val

    splits = {
        "train": pairs[:n_train],
        "val": pairs[n_train : n_train + n_val],
        "test": pairs[n_train + n_val :],
    }

    logger.info(
        "Split: train=%d, val=%d, test=%d",
        len(splits["train"]),
        len(splits["val"]),
        len(splits["test"]),
    )

    # Copy files into flat structure
    temp_path = output_dir / TEMP_DIR
    temp_path.mkdir(parents=True, exist_ok=True)

    total_boxes = 0
    for split_name, split_pairs in splits.items():
        split_images_dir = temp_path / split_name / "images"
        split_labels_dir = temp_path / split_name / "labels"
        split_images_dir.mkdir(parents=True, exist_ok=True)
        split_labels_dir.mkdir(parents=True, exist_ok=True)

        for img_path, label_path in split_pairs:
            shutil.copy2(img_path, split_images_dir / img_path.name)
            shutil.copy2(label_path, split_labels_dir / label_path.name)
            total_boxes += parse_yolo_label(label_path)

    # Write dataset.yaml
    yaml_path = temp_path / "dataset.yaml"
    yaml_path.write_text(
        f"# Maritime Phase 0 — Fine-tuning Dataset\n"
        f"# Generated from: {input_dir.name}\n"
        f"# Total images: {n}, Total boxes: {total_boxes}\n"
        f"# Split: train={n_train}, val={n_val}, test={n_test}\n\n"
        f"path: {temp_path.absolute()}\n"
        f"train: train/images\n"
        f"val: val/images\n"
        f"test: test/images\n\n"
        f"nc: 3\n"
        f"names: {CLASS_NAMES}\n"
    )

    # Write dataset_summary.json inside the temp dir (will be included in ZIP)
    summary_path = temp_path / "dataset_summary.json"
    summary = {
        "total_images": n,
        "total_boxes": total_boxes,
        "classes": CLASS_NAMES,
        "split": {
            "train": n_train,
            "val": n_val,
            "test": n_test,
        },
        "split_pct": {
            "train": train_pct,
            "val": val_pct,
            "test": test_pct,
        },
        "box_count_per_class": {name: 0 for name in CLASS_NAMES},
    }

    # Count per class
    for _, label_path in pairs:
        text = label_path.read_text().strip()
        if not text:
            continue
        for line in text.splitlines():
            cls_id = int(line.split()[0])
            if 0 <= cls_id < len(CLASS_NAMES):
                summary["box_count_per_class"][CLASS_NAMES[cls_id]] += 1

    # Write summary inside temp dir (included in ZIP)
    summary_path.write_text(json.dumps(summary, indent=2))

    return temp_path, summary


def create_zip(source_dir: Path, output_path: Path):
    """Create a ZIP archive of the dataset."""
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for fpath in sorted(source_dir.rglob("*")):
            if fpath.is_file():
                arcname = fpath.relative_to(source_dir)
                zf.write(fpath, arcname)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info("ZIP created: %s (%.0f MB)", output_path, size_mb)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Export annotated AIS dataset for Google Colab fine-tuning",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("research/data/cvat_annotated_only"),
        help="Input directory with scene subdirectories (default: cvat_annotated_only)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("research/data/colab_export"),
        help="Output directory for ZIP + notebook (default: research/data/colab_export)",
    )
    parser.add_argument(
        "--split",
        type=float,
        nargs=3,
        default=[80, 10, 10],
        help="Train/val/test split percentages (default: 80 10 10)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    input_dir = args.input.resolve()
    output_dir = args.output.resolve()

    if not input_dir.exists():
        logger.error("Input directory not found: %s", input_dir)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Build flat dataset
    logger.info("Building Colab dataset from %s...", input_dir)
    temp_path, summary = build_flat_dataset(input_dir, output_dir, tuple(args.split))

    # Create ZIP
    zip_path = output_dir / "maritime_dataset.zip"
    logger.info("Creating ZIP archive...")
    create_zip(temp_path, zip_path)

    # Save summary
    summary_path = output_dir / "dataset_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    logger.info("Summary saved: %s", summary_path)

    # Copy Colab notebook
    notebook_src = Path(__file__).parent.parent / "notebooks" / "colab_finetune_yolo.ipynb"
    notebook_dst = output_dir / "colab_finetune_yolo.ipynb"
    if notebook_src.exists():
        shutil.copy2(notebook_src, notebook_dst)
        logger.info("Notebook copied: %s", notebook_dst)
    else:
        logger.warning("Notebook not found at %s — copy manually", notebook_src)

    # Cleanup temp
    shutil.rmtree(temp_path)
    logger.info("Temporary files cleaned up")

    # Final summary
    print()
    print("=" * 60)
    print("  COLAB EXPORT COMPLETE")
    print("=" * 60)
    print(f"  Dataset:  {summary['total_images']} images, {summary['total_boxes']} boxes")
    print(
        f"  Split:    train={summary['split']['train']}, val={summary['split']['val']}, test={summary['split']['test']}"
    )
    print(f"  Classes:  {summary['classes']}")
    print()
    print(f"  ZIP:      {zip_path} ({zip_path.stat().st_size / 1024 / 1024:.0f} MB)")
    print(f"  Notebook: {notebook_dst}")
    print(f"  Summary:  {summary_path}")
    print()
    print("  Next steps:")
    print("  1. Upload maritime_dataset.zip to Google Drive")
    print("  2. Open colab_finetune_yolo.ipynb in Colab")
    print("  3. Mount Drive and point to the ZIP")
    print("  4. Run all cells")
    print("=" * 60)


if __name__ == "__main__":
    main()
