#!/usr/bin/env python3
"""
Dataset Traceability — Print per-split scene & platform composition.

Usage:
    python phase_post0/dataset_traceability.py <path_to_dataset_dir>
    python phase_post0/dataset_traceability.py phase_post0/dataset_finetune

Output:
    - Scenes included with label/box counts
    - Per-split S1C/S1D breakdown with percentages
    - Dominance alert if any platform > 80% of a split
"""

import json
import os
import sys


def analyze_dataset(dataset_dir: str) -> None:
    """Analyze and print the dataset composition."""
    # Find dataset_summary.json
    for candidate in [
        os.path.join(dataset_dir, "dataset_summary.json"),
        os.path.join(dataset_dir, "dataset_finetune", "dataset_summary.json"),
    ]:
        if os.path.exists(candidate):
            summary_path = candidate
            base_dir = os.path.dirname(candidate)
            break
    else:
        print(f"dataset_summary.json not found under {dataset_dir}")
        return

    with open(summary_path) as f:
        data = json.load(f)

    print("=" * 65)
    print("  DATASET TRACEABILITY")
    print("=" * 65)
    print(f"  Total images: {data['total_images']}")
    print(f"  Total boxes:  {data['total_boxes']}")
    print(f"  Classes:       {data['classes']}")
    print()

    # Scenes
    print("--- Scenes included ---")
    for s in data["scenes"]:
        if "S1C" in s["id"]:
            sat = "S1C"
        elif "S1D" in s["id"]:
            sat = "S1D"
        elif "S1A" in s["id"]:
            sat = "S1A"
        elif "S1B" in s["id"]:
            sat = "S1B"
        else:
            sat = "???"
        short = s["short_id"]
        print(f"  [{sat}] {short}: {s['labels']} labels, {s['boxes']} boxes")
    print()

    # Per-split platform breakdown
    labels_dir = os.path.join(base_dir, "labels")
    if not os.path.isdir(labels_dir):
        # Check alternative path
        labels_dir = os.path.join(base_dir, "dataset_finetune", "labels")
    if not os.path.isdir(labels_dir):
        print("  (labels directory not found for per-split breakdown)")
    else:
        print("--- Per-split composition ---")
        header = (
            f"  {'Split':<8} {'S1C':>6} {'S1D':>6} {'Total':>6}  {'S1C%':>6} {'S1D%':>6}  Dominance"
        )
        print(header)
        print("  " + "-" * (len(header) - 2))

        for split in ["train", "val", "test"]:
            split_dir = os.path.join(labels_dir, split)
            if not os.path.isdir(split_dir):
                continue

            s1c = sum(
                1 for f in os.listdir(split_dir) if f.startswith("S1C") and f.endswith(".txt")
            )
            s1d = sum(
                1 for f in os.listdir(split_dir) if f.startswith("S1D") and f.endswith(".txt")
            )
            other = sum(
                1
                for f in os.listdir(split_dir)
                if not f.startswith("S1C") and not f.startswith("S1D") and f.endswith(".txt")
            )
            total = s1c + s1d + other
            pct_s1c = 100.0 * s1c / total if total > 0 else 0.0
            pct_s1d = 100.0 * s1d / total if total > 0 else 0.0

            alert = ""
            if pct_s1c > 80:
                alert = "⚠️ S1C DOMINATED!"
            elif pct_s1d > 80:
                alert = "⚠️ S1D DOMINATED!"
            if other > 0:
                alert += f" (+{other} OTHER)"

            print(
                f"  {split:<8} {s1c:>6} {s1d:>6} {total:>6}  "
                f"{pct_s1c:>5.0f}% {pct_s1d:>5.0f}% {alert}"
            )

        print()

    # Split counts
    print("--- Split counts ---")
    for split, count in data["split"].items():
        print(f"  {split}: {count} images")
    print("=" * 65)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python dataset_traceability.py <dataset_dir>")
        print("Example: python dataset_traceability.py phase_post0/dataset_finetune")
        sys.exit(1)
    analyze_dataset(sys.argv[1])
