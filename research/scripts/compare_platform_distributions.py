#!/usr/bin/env python3
"""Compare S1C vs S1D intensity distributions (Pipeline D) using KS test.

Rationale:
    Before committing to a platform-stratified train/val/test split (mixing
    S1C and S1D tiles), verify that the two satellite platforms produce
    statistically similar pixel intensity distributions after preprocessing.

    If the KS distance is LOW and p-value is NOT significant → S1C and S1D
    are statistically similar after Pipeline D preprocessing. The stratified
    split (Option B) is well-founded; proceed without reservation.

    If the KS distance is HIGH and significant → there is a real radiometric
    difference between platforms. Document as a limitation; the fine-tuned
    model may need explicit cross-platform validation despite the stratified
    split.

Methodology:
    - Loads ALL Pipeline D tiles for each platform (not just annotated ones),
      giving the full distribution comparison.
    - Optionally filters to EMPTY tiles only (tiles without any AIS annotation)
      to isolate the platform effect from the vessel signal.
    - Computes: mean, median, std, min, max, histogram, KS statistic, Cohen's d.
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
from scipy.stats import ks_2samp, mannwhitneyu

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("compare_platforms")


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def collect_pipeline_d_tiles(tiles_root: Path) -> dict[str, list[Path]]:
    """Scan tiles_root/<scene>/D/*.npy grouped by satellite platform.

    Args:
        tiles_root: Path to the tiles directory (e.g., phase0/data/tiles/).

    Returns:
        Dict mapping platform ("S1C" or "S1D") to list of .npy file paths.
    """
    platforms: dict[str, list[Path]] = {}
    for scene_dir in sorted(tiles_root.iterdir()):
        if not scene_dir.is_dir():
            continue
        scene_id = scene_dir.name
        # Extract platform prefix: S1A, S1B, S1C, S1D
        platform = scene_id[:3]
        if platform not in ("S1A", "S1B", "S1C", "S1D"):
            continue

        pipeline_d = scene_dir / "D"
        if not pipeline_d.is_dir():
            logger.info(f"  Skipping {scene_id} (no Pipeline D directory)")
            continue

        npy_files = sorted(pipeline_d.glob("*.npy"))
        if not npy_files:
            logger.info(f"  Skipping {scene_id} (no .npy files in Pipeline D)")
            continue

        platforms.setdefault(platform, []).extend(npy_files)
        logger.info(f"  {scene_id} ({platform}): {len(npy_files)} tiles")

    return platforms


def find_annotated_tiles(annotations_root: Path) -> set:
    """Return set of tile IDs (stems) that have a YOLO label file.

    These tiles contain at least one AIS vessel annotation and should be
    excluded when comparing 'empty' (vessel-free) backgrounds.
    """
    annotated: set = set()
    labels_root = annotations_root
    if not labels_root.is_dir():
        return annotated

    for scene_dir in sorted(labels_root.iterdir()):
        labels_dir = scene_dir / "labels"
        if not labels_dir.is_dir():
            continue
        for label_file in labels_dir.glob("*.txt"):
            # Only count tiles with at least one non-empty label line
            content = label_file.read_text().strip()
            if content:
                annotated.add(label_file.stem)

    logger.info(f"  Found {len(annotated)} annotated tiles across all scenes")
    return annotated


# ---------------------------------------------------------------------------
# Progressive statistics (memory-efficient)
# ---------------------------------------------------------------------------


class RunningStats:
    """Compute mean, variance, min, max progressively without storing all values.

    Uses Welford's parallel algorithm (combines per-batch statistics using
    numpy vectorized tile-level computations). The per-pixel loops are done
    inside numpy C code, not Python for-loops.

    For percentiles (p5, p25, p75, p95), we store a random subsample
    via reservoir sampling during loading.
    """

    def __init__(self, max_subsample: int = 200_000, rng_seed: int = 42):
        self.n = 0
        self.mean = 0.0
        self.M2 = 0.0  # sum of squared differences from current mean
        self.min_val = float("inf")
        self.max_val = float("-inf")
        self._rng = np.random.RandomState(rng_seed)
        self._subsample: list[float] = []
        self._max_subsample = max_subsample

    def add(self, values: np.ndarray) -> None:
        """Update running statistics with a batch of pixel values (vectorized)."""
        flat = values.ravel()
        n_batch = len(flat)
        if n_batch == 0:
            return

        # Min/max (vectorized)
        arr_min = float(flat.min())
        arr_max = float(flat.max())
        if arr_min < self.min_val:
            self.min_val = arr_min
        if arr_max > self.max_val:
            self.max_val = arr_max

        # Batch mean and sum of squared differences (vectorized)
        mean_batch = float(flat.mean())
        # M2_batch = sum((x - mean_batch)^2)  -- vectorized
        diff = flat - mean_batch
        M2_batch = float(np.dot(diff, diff))  # dot product = sum of squares

        # Combine with running stats (Welford's parallel algorithm)
        if self.n == 0:
            self.mean = mean_batch
            self.M2 = M2_batch
        else:
            n_old = self.n
            n_total = n_old + n_batch
            delta = mean_batch - self.mean
            self.mean = (n_old * self.mean + n_batch * mean_batch) / n_total
            self.M2 = self.M2 + M2_batch + delta * delta * n_old * n_batch / n_total
        self.n += n_batch

        # Reservoir sampling for percentiles (vectorized per tile)
        n_remaining = self._max_subsample - len(self._subsample)
        if n_remaining > 0:
            # Fill the reservoir up to capacity
            n_take = min(n_batch, n_remaining)
            self._subsample.extend(float(v) for v in flat[:n_take])
        else:
            # Reservoir replacement: sample random indices from this tile
            replace_idx = self._rng.randint(0, self.n, size=n_batch)
            mask = replace_idx < self._max_subsample
            if mask.any():
                indices = np.where(mask)[0]
                targets = replace_idx[mask]
                for src, tgt in zip(indices, targets, strict=False):
                    self._subsample[tgt] = float(flat[src])

    @property
    def std(self) -> float:
        if self.n < 2:
            return 0.0
        return float(np.sqrt(self.M2 / (self.n - 1)))

    @property
    def count(self) -> int:
        return self.n

    def get_stats(self) -> dict[str, float]:
        subsample = np.array(self._subsample, dtype=np.float64)
        return {
            "count": self.n,
            "mean": round(self.mean, 6),
            "median": round(float(np.median(subsample)), 6),
            "std": round(self.std, 6),
            "min": round(self.min_val, 6),
            "max": round(self.max_val, 6),
            "p5": round(float(np.percentile(subsample, 5)), 6),
            "p25": round(float(np.percentile(subsample, 25)), 6),
            "p75": round(float(np.percentile(subsample, 75)), 6),
            "p95": round(float(np.percentile(subsample, 95)), 6),
        }

    def get_subsample(self) -> np.ndarray:
        """Return the stored subsample for KS testing."""
        return np.array(self._subsample, dtype=np.float64)


def cohens_d_from_stats(
    n1: int,
    mean1: float,
    var1: float,
    n2: int,
    mean2: float,
    var2: float,
) -> float:
    """Compute Cohen's d from summary statistics (no data needed)."""
    pooled = np.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))
    if pooled == 0:
        return 0.0
    return float((mean1 - mean2) / pooled)


# ---------------------------------------------------------------------------
# Main comparison
# ---------------------------------------------------------------------------


def compare_platforms(
    tiles_root: Path,
    annotations_root: Path | None = None,
    sample_limit: int | None = None,
    use_empty_only: bool = False,
) -> None:
    """Compare S1C vs S1D intensity distributions.

    Args:
        tiles_root: Path to the tiles directory.
        annotations_root: Path to annotations root (for filtering empty tiles).
        sample_limit: Optional per-platform tile limit for faster testing.
        use_empty_only: If True, only consider tiles WITHOUT any AIS annotation.
    """
    logger.info("=" * 60)
    logger.info("S1C vs S1D Platform Distribution Comparison (Pipeline D)")
    logger.info("=" * 60)

    # 1. Collect tiles per platform
    logger.info("\n--- Collecting tiles ---")
    platforms = collect_pipeline_d_tiles(tiles_root)

    if "S1C" not in platforms and "S1D" not in platforms:
        logger.error("No S1C or S1D tiles found. Aborting.")
        sys.exit(1)

    # 2. Determine empty tiles if requested
    annotated_tiles: set = set()
    if use_empty_only:
        if annotations_root is None or not annotations_root.is_dir():
            logger.warning("annotations_root not found; falling back to all tiles")
            use_empty_only = False
        else:
            logger.info("\n--- Finding annotated tiles to exclude ---")
            annotated_tiles = find_annotated_tiles(annotations_root)

    # 3. Stream tiles progressively (memory-efficient: ~200k subsample per platform)
    all_stats: dict[str, RunningStats] = {}
    for platform in ("S1C", "S1D"):
        if platform not in platforms:
            logger.warning(f"  Platform {platform}: no tiles found, skipping")
            continue

        tile_paths = platforms[platform]
        if sample_limit and len(tile_paths) > sample_limit:
            # Deterministic subsample: take first N tiles
            tile_paths = tile_paths[:sample_limit]
            logger.info(f"  {platform}: subsampled to {sample_limit} tiles")

        if use_empty_only:
            # Filter to only empty tiles
            empty_paths = [p for p in tile_paths if p.stem not in annotated_tiles]
            n_skipped = len(tile_paths) - len(empty_paths)
            tile_paths = empty_paths
            logger.info(f"  {platform}: excluded {n_skipped} annotated tiles, {len(tile_paths)} empty tiles remaining")

        logger.info(f"  Processing {len(tile_paths)} tiles for {platform} (streaming)...")
        runner = RunningStats(max_subsample=200_000, rng_seed=42)
        for i, npy_path in enumerate(tile_paths):
            try:
                arr = np.load(str(npy_path)).astype(np.float64)
                runner.add(arr)
            except Exception as e:
                logger.warning(f"  Failed to load {npy_path}: {e}")
            if (i + 1) % 10000 == 0:
                n_pixels_so_far = runner.count
                logger.info(f"    ... processed {i + 1} / {len(tile_paths)} tiles ({n_pixels_so_far:,} pixels so far)")

        all_stats[platform] = runner
        logger.info(f"  {platform}: {runner.count:,} total pixels, {len(runner._subsample):,} in subsample")

    # 4. Compute statistics
    if len(all_stats) < 2:
        logger.error("Need both S1C and S1D data to compare. Aborting.")
        sys.exit(1)

    s1c_runner = all_stats["S1C"]
    s1d_runner = all_stats["S1D"]
    s1c_stats = s1c_runner.get_stats()
    s1d_stats = s1d_runner.get_stats()

    logger.info("\n--- Per-platform Statistics ---")
    headers = ["Statistic", "S1C", "S1D"]
    rows = [
        ("Count", f"{s1c_stats['count']:,}", f"{s1d_stats['count']:,}"),
        ("Mean", f"{s1c_stats['mean']:.4f}", f"{s1d_stats['mean']:.4f}"),
        ("Median", f"{s1c_stats['median']:.4f}", f"{s1d_stats['median']:.4f}"),
        ("Std Dev", f"{s1c_stats['std']:.4f}", f"{s1d_stats['std']:.4f}"),
        ("Min", f"{s1c_stats['min']:.4f}", f"{s1d_stats['min']:.4f}"),
        ("Max", f"{s1c_stats['max']:.4f}", f"{s1d_stats['max']:.4f}"),
        ("P5", f"{s1c_stats['p5']:.4f}", f"{s1d_stats['p5']:.4f}"),
        ("P25", f"{s1c_stats['p25']:.4f}", f"{s1d_stats['p25']:.4f}"),
        ("P75", f"{s1c_stats['p75']:.4f}", f"{s1d_stats['p75']:.4f}"),
        ("P95", f"{s1c_stats['p95']:.4f}", f"{s1d_stats['p95']:.4f}"),
    ]

    # Print aligned table
    col_w = max(len(h) for h in headers) + 2
    print(f"\n  {'':>{col_w}}  {'S1C':>15}  {'S1D':>15}")
    print(f"  {'-' * col_w}  {'-' * 15}  {'-' * 15}")
    for label, s1c_v, s1d_v in rows:
        print(f"  {label:>{col_w}}  {s1c_v:>15}  {s1d_v:>15}")

    # 5. KS test on subsamples
    logger.info("\n--- Two-Sample Kolmogorov-Smirnov Test ---")
    s1c_sample = s1c_runner.get_subsample()
    s1d_sample = s1d_runner.get_subsample()
    N_KS = min(len(s1c_sample), len(s1d_sample))

    ks_stat, ks_pval = ks_2samp(s1c_sample, s1d_sample)
    logger.info(f"  KS statistic = {ks_stat:.5f}")
    logger.info(f"  p-value      = {ks_pval:.6e}")
    logger.info(f"  Subsample size  = {N_KS:,} pixels per platform")

    # 6. Mann-Whitney U test (distribution location shift)
    logger.info("\n--- Mann-Whitney U Test ---")
    mw_stat, mw_pval = mannwhitneyu(s1c_sample, s1d_sample, alternative="two-sided")
    logger.info(f"  U statistic  = {mw_stat:,.1f}")
    logger.info(f"  p-value      = {mw_pval:.6e}")

    # 7. Cohen's d (effect size, using running stats for exact variance)
    d = cohens_d_from_stats(
        s1c_stats["count"],
        s1c_stats["mean"],
        s1c_stats["std"] ** 2,
        s1d_stats["count"],
        s1d_stats["mean"],
        s1d_stats["std"] ** 2,
    )
    logger.info("\n--- Effect Size ---")
    logger.info(f"  Cohen's d    = {d:.4f}")
    if abs(d) < 0.2:
        logger.info("  Interpretation: negligible effect size")
    elif abs(d) < 0.5:
        logger.info("  Interpretation: small effect size")
    elif abs(d) < 0.8:
        logger.info("  Interpretation: medium effect size")
    else:
        logger.info("  Interpretation: large effect size")

    # 8. Interpret results
    logger.info("\n--- Interpretation ---")
    significant = ks_pval < 0.05
    if not significant:
        logger.info(
            "  ✅ KS test NOT significant (p > 0.05). S1C and S1D intensity "
            "distributions are\n"
            "     statistically indistinguishable after Pipeline D preprocessing.\n"
            "     The platform-stratified split (Option B) is well-founded."
        )
    elif abs(d) < 0.2:
        logger.info(
            "  ⚠️  KS test significant (p < 0.05) BUT effect size is negligible "
            "(d < 0.2).\n"
            "     The statistical significance is due to the large sample size, "
            "not a meaningful\n"
            "     difference. The stratified split remains acceptable."
        )
    else:
        logger.info(
            "  ❌ KS test significant (p < 0.05) AND non-negligible effect size "
            "(d >= 0.2).\n"
            "     There is a real radiometric difference between S1C and S1D.\n"
            "     Document as a limitation; the fine-tuned model may need\n"
            "     explicit cross-platform validation despite stratified split."
        )

    # 9. Print summary table for documentation
    print("\n" + "=" * 60)
    print("SUMMARY TABLE FOR DOCUMENTATION")
    print("=" * 60)
    note = "(empty tiles only)" if use_empty_only else "(all tiles)"
    print(f"""
| Metric | S1C | S1D |
|--------|-----|-----|
| Count (pixels) | {s1c_stats["count"]:,} | {s1d_stats["count"]:,} |
| Mean ± Std | {s1c_stats["mean"]:.3f} ± {s1c_stats["std"]:.3f} | {s1d_stats["mean"]:.3f} ± {s1d_stats["std"]:.3f} |
| Median | {s1c_stats["median"]:.3f} | {s1d_stats["median"]:.3f} |
| P5 / P95 | {s1c_stats["p5"]:.3f} / {s1c_stats["p95"]:.3f} | {s1d_stats["p5"]:.3f} / {s1d_stats["p95"]:.3f} |
| KS statistic | — | {ks_stat:.5f} |
| KS p-value | — | {ks_pval:.6e} |
| Cohen's d | — | {d:.4f} |
| Condition | {note} | |

Interpretation: {"No significant difference" if ks_pval >= 0.05 else ("Significant but negligible effect" if abs(d) < 0.2 else "Significant with non-negligible effect")}
""")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare S1C vs S1D intensity distributions (Pipeline D)")
    parser.add_argument(
        "--tiles-root",
        default="phase0/data/tiles",
        help="Path to the tiles directory (default: phase0/data/tiles)",
    )
    parser.add_argument(
        "--annotations-root",
        default="phase0/data/annotations",
        help="Path to annotations root (default: phase0/data/annotations)",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=None,
        help="Optional per-platform tile limit for faster testing",
    )
    parser.add_argument(
        "--all-tiles",
        action="store_true",
        help="Compare ALL tiles (default: exclude annotated tiles for a cleaner comparison)",
    )

    args = parser.parse_args()

    tiles_root = Path(args.tiles_root)
    if not tiles_root.is_dir():
        logger.error(f"Tiles root not found: {tiles_root}")
        sys.exit(1)

    use_empty_only = not args.all_tiles
    annotations_root = Path(args.annotations_root) if use_empty_only else None
    if use_empty_only and not annotations_root.is_dir():
        logger.warning(f"Annotations root not found: {annotations_root}; falling back to all-tiles comparison")
        use_empty_only = False
        annotations_root = None

    compare_platforms(
        tiles_root=tiles_root,
        annotations_root=annotations_root,
        sample_limit=args.sample_limit,
        use_empty_only=use_empty_only,
    )


if __name__ == "__main__":
    main()
