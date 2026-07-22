# research/scripts/benchmark_pipeline.py
"""Pipeline Benchmarking and Domain Shift Evaluation.

Ported from notebook colab_research_pipeline_final.ipynb (cells 20-22).
Compare model inference against ground truth across pipelines, calculating metrics
such as Precision, Recall, mAP@0.5, and KS-distance to evaluate domain transfer.

Known limitations:
- KS test is inter-pipelines only (not compared to real MRSSD dataset)
- estimate_bbox() (legacy notebook artifact) was removed — it was never
  called by inference or metrics code. See center-distance analysis in
  benchmark_summary_post_fix.json for independent validation that the
  mAP=0.0 result is not a bbox artifact.
"""

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from scipy.stats import ks_2samp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (importable from shared/config/constants.py)
# ---------------------------------------------------------------------------

PIPELINES = ["A", "B", "C", "D"]
TILE_SIZE = 512
IOU_THRESHOLD = 0.5  # mAP@0.5
MODEL_INPUT_SIZE = 640  # YOLOv8n ONNX input dimension
NMS_IOU_THRESHOLD = 0.5  # IoU threshold for Non-Maximum Suppression


# ---------------------------------------------------------------------------
# IoU computation
# ---------------------------------------------------------------------------


def compute_iou(box1: list[float], box2: list[float]) -> float:
    """Compute IoU between two bounding boxes in YOLO format [cx, cy, w, h]."""
    # Convert YOLO to corner format [x1, y1, x2, y2]
    b1_x1 = box1[0] - box1[2] / 2
    b1_y1 = box1[1] - box1[3] / 2
    b1_x2 = box1[0] + box1[2] / 2
    b1_y2 = box1[1] + box1[3] / 2

    b2_x1 = box2[0] - box2[2] / 2
    b2_y1 = box2[1] - box2[3] / 2
    b2_x2 = box2[0] + box2[2] / 2
    b2_y2 = box2[1] + box2[3] / 2

    # Intersection
    x1 = max(b1_x1, b2_x1)
    y1 = max(b1_y1, b2_y1)
    x2 = min(b1_x2, b2_x2)
    y2 = min(b1_y2, b2_y2)

    inter = max(0, x2 - x1) * max(0, y2 - y1)

    # Union
    area1 = (b1_x2 - b1_x1) * (b1_y2 - b1_y1)
    area2 = (b2_x2 - b2_x1) * (b2_y2 - b2_y1)
    union = area1 + area2 - inter

    if union <= 0:
        return 0.0
    return inter / union


# ---------------------------------------------------------------------------
# Ground truth loading
# ---------------------------------------------------------------------------


def load_ground_truth(annotations_dir: str) -> dict[str, list[dict[str, Any]]]:
    """Load YOLO format ground truth annotations."""
    labels_dir = Path(annotations_dir)
    if not labels_dir.exists():
        raise FileNotFoundError(f"Annotations directory not found: {labels_dir}")

    ground_truth: dict[str, list[dict[str, Any]]] = {}
    for label_file in sorted(labels_dir.glob("*.txt")):
        tile_id = label_file.stem
        boxes = []
        with open(label_file) as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 5:
                    class_id = int(parts[0])
                    cx, cy, w, h = map(float, parts[1:5])
                    boxes.append(
                        {
                            "class_id": class_id,
                            "bbox": [cx, cy, w, h],
                        }
                    )
        ground_truth[tile_id] = boxes

    logger.info(
        f"Loaded ground truth: {len(ground_truth)} tiles, {sum(len(v) for v in ground_truth.values())} boxes"
    )
    return ground_truth


# ---------------------------------------------------------------------------
# ONNX inference
# ---------------------------------------------------------------------------


def nms_suppress(
    detections: list[dict[str, Any]], iou_threshold: float = NMS_IOU_THRESHOLD
) -> list[dict[str, Any]]:
    """Apply Non-Maximum Suppression to remove duplicate boxes for the same vessel.

    Sorts by confidence descending, keeps the highest-confidence box, and removes
    any remaining box with IoU > threshold. This prevents the benchmark from
    counting multiple overlapping predictions as separate false positives.

    Args:
        detections: List of detection dicts with 'bbox' [cx,cy,w,h] and 'confidence'
        iou_threshold: IoU above which boxes are considered duplicates

    Returns:
        Filtered list with duplicates removed.
    """
    if len(detections) <= 1:
        return detections

    # Sort by confidence descending
    sorted_dets = sorted(detections, key=lambda d: d["confidence"], reverse=True)
    kept = []

    while sorted_dets:
        best = sorted_dets.pop(0)
        kept.append(best)
        # Remove any remaining detection with IoU > threshold against the kept one
        sorted_dets = [
            d for d in sorted_dets if compute_iou(best["bbox"], d["bbox"]) < iou_threshold
        ]

    return kept


def run_inference(
    tiles: list[Any],
    model_path: str,
    conf_threshold: float = 0.25,
    log_raw_first_n: int = 10,
) -> dict[str, list[dict[str, Any]]]:
    """Run ONNX Runtime INT8 model inference over the generated tiles.

    NOTE: Requires the Phase I ONNX model (yolov8n_int8.onnx).
    If the model is not available, returns empty predictions with a warning.

    Model output format (verified empirically):
        Tensor shape: [1, 5, 8400]
        Axis 1: [cx, cy, w, h, confidence]  (5 rows)
        Axis 2: 8400 candidate detections
        Must TRANSPOSE to [8400, 5] before iterating.
        Single class (vessel) — no class dimension in output.

    Post-processing:
        1. Confidence threshold (default 0.25)
        2. Non-Maximum Suppression (IoU threshold 0.5)

    Args:
        tiles: List of tile file paths or (tile_id, npy_path) tuples.
        model_path: File path to the ONNX model.
        conf_threshold: Minimum confidence to keep a detection.
        log_raw_first_n: Log raw proposal counts (pre-threshold) for the first N tiles.

    Returns:
        Dict mapping tile_id -> list of prediction dicts with:
            - bbox: [cx, cy, w, h] in YOLO format
            - confidence: float
            - class_id: int
    """
    model_path = Path(model_path)
    if not model_path.exists():
        logger.warning(f"ONNX Model not found at {model_path}")
        logger.warning("Skipping inference -- benchmark will use placeholder predictions.")
        return {}

    try:
        import onnxruntime as ort
    except ImportError:
        logger.warning("onnxruntime not installed. Skipping inference.")
        return {}

    logger.info(f"Loading ONNX model: {model_path}")
    session = ort.InferenceSession(str(model_path))
    input_name = session.get_inputs()[0].name
    input_size = MODEL_INPUT_SIZE

    predictions: dict[str, list[dict[str, Any]]] = {}
    for tile_idx, item in enumerate(tiles):
        if isinstance(item, tuple):
            tile_id, npy_path = item
        else:
            tile_id = Path(str(item)).stem
            npy_path = str(item)

        # Load tile uint8, grayscale
        tile_uint8 = np.load(npy_path).astype(np.uint8)
        # Convert grayscale to 3-channel RGB (stack identical channels)
        tile_rgb = np.stack([tile_uint8] * 3, axis=-1) if tile_uint8.ndim == 2 else tile_uint8

        # Real resize 512x512 -> input_size x input_size (not slice assignment)
        img = Image.fromarray(tile_rgb)
        img_resized = img.resize((input_size, input_size), Image.Resampling.LANCZOS)
        resized = np.array(img_resized, dtype=np.float32) / 255.0

        # Format: [1, 3, input_size, input_size] (CHW layout)
        input_tensor = resized.transpose(2, 0, 1)[np.newaxis, ...]
        outputs = session.run(None, {input_name: input_tensor})

        tile_preds = []
        if outputs and len(outputs) > 0:
            # Model output shape: [1, 5, 8400]
            #   5 rows = [cx, cy, w, h, confidence]
            #   8400 cols = candidate detections
            # Must TRANSPOSE to [8400, 5] to iterate over candidates
            raw = outputs[0][0]
            detections = raw.T  # shape [8400, 5]
            n_raw = int(detections.shape[0])

            if tile_idx < log_raw_first_n:
                logger.info(
                    f"Tile {tile_id}: raw output shape={raw.shape}, "
                    f"after transpose={detections.shape}, "
                    f"raw_proposals={n_raw} (expect ~8400, not 5)"
                )

            for det in detections:
                cx, cy, w, h, conf = det[0], det[1], det[2], det[3], det[4]
                if conf > conf_threshold:
                    # Normalize to [0, 1] relative to input_size
                    cx_norm = float(cx) / float(input_size)
                    cy_norm = float(cy) / float(input_size)
                    w_norm = float(w) / float(input_size)
                    h_norm = float(h) / float(input_size)
                    tile_preds.append(
                        {
                            "bbox": [cx_norm, cy_norm, w_norm, h_norm],
                            "confidence": float(conf),
                            "class_id": 0,  # single class (vessel)
                        }
                    )

        # Apply NMS to remove duplicate detections for the same vessel
        tile_preds = nms_suppress(tile_preds)
        predictions[tile_id] = tile_preds

    logger.info(
        f"Inference complete: {sum(len(v) for v in predictions.values())} detections across {len(predictions)} tiles"
    )
    return predictions


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------


def compute_metrics(
    predictions: dict[str, list[dict[str, Any]]], ground_truth: dict[str, list[dict[str, Any]]]
) -> dict[str, float]:
    """Calculate evaluation metrics (Precision, Recall, mAP@0.5).

    Args:
        predictions: Dict mapping tile_id -> list of prediction dicts.
        ground_truth: Dict mapping tile_id -> list of ground truth dicts.

    Returns:
        Dict with precision, recall, and mAP@0.5.
    """
    total_tp = 0
    total_fp = 0
    total_fn = 0

    all_tile_ids = set(predictions.keys()) | set(ground_truth.keys())

    for tile_id in all_tile_ids:
        preds = predictions.get(tile_id, [])
        gts = ground_truth.get(tile_id, [])

        matched_gt = set()
        matched_pred = set()

        for i, pred in enumerate(preds):
            for j, gt in enumerate(gts):
                if j in matched_gt:
                    continue
                iou = compute_iou(pred["bbox"], gt["bbox"])
                if iou >= IOU_THRESHOLD:
                    matched_gt.add(j)
                    matched_pred.add(i)
                    break

        total_tp += len(matched_pred)
        total_fp += len(preds) - len(matched_pred)
        total_fn += len(gts) - len(matched_gt)

    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0

    # mAP@0.5: average precision (simplified as precision at IOU=0.5)
    mAP = precision if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "mAP@0.5": round(mAP, 4),
        "true_positives": total_tp,
        "false_positives": total_fp,
        "false_negatives": total_fn,
    }


# ---------------------------------------------------------------------------
# KS distance for domain shift
# ---------------------------------------------------------------------------


def compute_ks_distance(
    tiles: dict[str, list[dict[str, Any]]], reference_dataset: str | None = None
) -> float:
    """Calculate Kolmogorov-Smirnov distance between intensity distributions.

    Evaluates covariate shift by comparing pixel intensity distributions
    across pipelines (inter-pipeline KS test). Does NOT compare to a
    reference dataset yet -- this is a documented limitation.

    Args:
        tiles: Dict mapping pipeline -> list of tile paths.
        reference_dataset: Not implemented yet (documented limitation).

    Returns:
        KS test statistic (max inter-pipeline distance).
    """
    if reference_dataset:
        logger.warning(
            "Reference dataset comparison not implemented yet. KS test is inter-pipelines only."
        )

    samples: dict[str, list[float]] = {}
    for pipeline, tile_list in tiles.items():
        pixels = []
        for tile_path in tile_list:
            try:
                data = np.load(str(tile_path))
                pixels.extend(data.flatten().tolist())
            except Exception:
                logger.warning("Failed to load tile %s, skipping", tile_path)
                continue
        if pixels:
            samples[pipeline] = pixels

    max_ks = 0.0
    pipeline_names = list(samples.keys())
    for i, p1 in enumerate(pipeline_names):
        for p2 in pipeline_names[i + 1 :]:
            s, pv = ks_2samp(samples[p1], samples[p2])
            max_ks = max(max_ks, s)
            logger.info(f"KS({p1}, {p2}) = {s:.4f} (p={pv:.4e})")

    return round(max_ks, 4)


# ---------------------------------------------------------------------------
# Metadata loading helper
# ---------------------------------------------------------------------------


def load_metadata(metadata_path: str) -> dict[str, Any]:
    """Load tile metadata from a JSON file."""
    with open(metadata_path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Full pipeline benchmark
# ---------------------------------------------------------------------------


def benchmark_all_pipelines(metadata_path: str, gt_path: str, model_path: str) -> dict[str, Any]:
    """Run performance benchmarks across the 4 pre-processing pipelines (A/B/C/D).

    Args:
        metadata_path: Path to the scene's metadata.json.
        gt_path: Path to YOLO ground truth labels directory.
        model_path: Path to YOLO ONNX weights.

    Returns:
        Dict with per-pipeline metrics and KS test results.
    """
    metadata = load_metadata(metadata_path)
    scene_id = metadata.get("scene_id", "unknown")

    # Real layout from sar_preprocessing.process_safe_windowed():
    #   tiles/<scene_id>/<pipeline_name>/metadata.json
    #   tiles/<scene_id>/<pipeline_name>/*.npy
    # So Path(metadata_path).parent is the pipeline directory (e.g. .../D),
    # NOT the scene root. Using scene_dir / pipeline would yield .../D/D.
    pipeline_meta_dir = Path(metadata_path).parent
    scene_root = pipeline_meta_dir.parent

    logger.info(f"=== Benchmark: {scene_id} ===")
    logger.info(f"Scene root: {scene_root}")
    logger.info(f"Metadata pipeline dir: {pipeline_meta_dir}")

    # Load ground truth
    ground_truth = load_ground_truth(gt_path)
    gt_tile_ids = set(ground_truth.keys())

    # Collect tiles per pipeline (only annotated tiles for evaluation)
    tiles_by_pipeline: dict[str, list[str]] = {}
    for p in PIPELINES:
        pipeline_dir = scene_root / p
        all_npy = sorted(pipeline_dir.glob("*.npy"))
        # Restrict to annotated tiles so load count matches GT tile count
        tile_files = [f for f in all_npy if f.stem in gt_tile_ids]
        tiles_by_pipeline[p] = [str(f) for f in tile_files]
        logger.info(
            f"Pipeline {p}: {len(tile_files)} annotated tiles (of {len(all_npy)} npy) from {pipeline_dir}"
        )

    # Run inference per pipeline
    predictions_by_pipeline: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for p in PIPELINES:
        tile_paths = tiles_by_pipeline.get(p, [])
        if not tile_paths:
            logger.warning(
                f"Pipeline {p}: no tiles found — skipping inference (results will be 0.0)"
            )
            predictions_by_pipeline[p] = {}
            continue
        tile_items = [(Path(t).stem, t) for t in tile_paths]
        predictions_by_pipeline[p] = run_inference(tile_items, model_path)

    # Compute metrics per pipeline
    metrics_results: dict[str, dict[str, Any]] = {}
    for p in PIPELINES:
        preds = predictions_by_pipeline.get(p, {})
        metrics = compute_metrics(preds, ground_truth)
        metrics_results[p] = metrics
        logger.info(
            f"Pipeline {p}: P={metrics['precision']:.3f}, R={metrics['recall']:.3f}, mAP@0.5={metrics['mAP@0.5']:.3f}"
        )

    # KS test (inter-pipeline)
    ks_result = compute_ks_distance(tiles_by_pipeline)

    results = {
        "scene_id": scene_id,
        "metrics_by_pipeline": metrics_results,
        "ks_max_distance": ks_result,
        "ground_truth_tiles": len(ground_truth),
        "note": (
            "estimate_bbox() (legacy notebook artifact) has been removed — "
            "the predictions use the real (w, h) from YOLO output. "
            "Center-distance analysis (see summary report) confirms "
            "the mAP=0.0 result is valid, not a bbox artifact. "
            "KS test is inter-pipelines only (no comparison to real MRSSD "
            "dataset)."
        ),
    }

    logger.info(f"=== Benchmark Complete: {scene_id} ===")
    return results


# ---------------------------------------------------------------------------
# Results export
# ---------------------------------------------------------------------------


def export_results(results: dict[str, Any], output_dir: str) -> dict[str, str]:
    """Export benchmark findings to JSON and CSV formats.

    Args:
        results: Evaluation summary dictionary from benchmark_all_pipelines().
        output_dir: Destination directory for exported files.

    Returns:
        Dict with paths to exported files: {"json": ..., "csv": ...}
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # JSON export
    json_path = output_path / f"benchmark_{results['scene_id']}.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)

    # CSV export (flat table of metrics per pipeline)
    csv_path = output_path / f"benchmark_{results['scene_id']}.csv"
    import csv

    with open(csv_path, "w", newline="") as f:
        fieldnames = [
            "pipeline",
            "precision",
            "recall",
            "mAP@0.5",
            "true_positives",
            "false_positives",
            "false_negatives",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for pipeline, metrics in results.get("metrics_by_pipeline", {}).items():
            row = {"pipeline": pipeline}
            row.update(metrics)
            writer.writerow(row)

    logger.info(f"Results exported to {output_path}")
    return {"json": str(json_path), "csv": str(csv_path)}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Pipeline benchmarking and domain shift evaluation"
    )
    parser.add_argument("--metadata", required=True, help="Path to scene metadata.json")
    parser.add_argument(
        "--ground-truth", required=True, help="Directory with YOLO label .txt files"
    )
    parser.add_argument(
        "--model",
        default="shared/models/yolov8n_int8.onnx",
        help="Path to ONNX model (default: shared/models/yolov8n_int8.onnx)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory for results (default: research/data/results/)",
    )

    args = parser.parse_args()

    output_dir = args.output_dir or str(Path(__file__).parent / "data" / "results")

    results = benchmark_all_pipelines(args.metadata, args.ground_truth, args.model)
    export_results(results, output_dir)

    logger.info("Benchmark complete.")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
