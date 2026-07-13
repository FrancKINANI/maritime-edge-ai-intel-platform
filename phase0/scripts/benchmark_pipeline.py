# phase0/scripts/benchmark_pipeline.py
"""Pipeline Benchmarking and Domain Shift Evaluation.

Ported from notebook colab_phase0_pipeline_final.ipynb (cells 20-22).
Compare model inference against ground truth across pipelines, calculating metrics
such as Precision, Recall, mAP@0.5, and KS-distance to evaluate domain transfer.

Documented limitations (carried over from the notebook):
- estimate_bbox() uses a fixed size (methodological bias on mAP@0.5:0.95)
- KS test is inter-pipelines only (not compared to real MRSSD dataset)
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.stats import ks_2samp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (importable from shared/config/constants.py)
# ---------------------------------------------------------------------------

PIPELINES = ["A", "B", "C", "D"]
TILE_SIZE = 512
IOU_THRESHOLD = 0.5  # mAP@0.5


# ---------------------------------------------------------------------------
# IoU computation
# ---------------------------------------------------------------------------


def compute_iou(box1: List[float], box2: List[float]) -> float:
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
# Bounding box estimation (fixed-size, acknowledged bias)
# ---------------------------------------------------------------------------


def estimate_bbox(cx: float, cy: float, ts: int = TILE_SIZE, sz: float = 8.0) -> Tuple[float, float, float, float]:
    """Estimate a bounding box with a fixed size.

    NOTE: This uses a fixed size (methodological bias on mAP@0.5:0.95).
    The estimated size assumes ~50m vessel length at 10m/pixel resolution
    with some margin. This is a known limitation documented from the notebook.

    Args:
        cx, cy: Center coordinates in pixels.
        ts: Tile size in pixels.
        sz: Half-size estimate in pixels.

    Returns:
        Tuple (x_center, y_center, width, height) in YOLO normalized format.
    """
    w = sz / ts
    h = sz / ts
    xc = max(0.0, min(1.0, cx / ts))
    yc = max(0.0, min(1.0, cy / ts))
    return xc, yc, w, h


# ---------------------------------------------------------------------------
# Ground truth loading
# ---------------------------------------------------------------------------


def load_ground_truth(annotations_dir: str) -> Dict[str, List[Dict[str, Any]]]:
    """Load YOLO format ground truth annotations."""
    labels_dir = Path(annotations_dir)
    if not labels_dir.exists():
        raise FileNotFoundError(f"Annotations directory not found: {labels_dir}")

    ground_truth: Dict[str, List[Dict[str, Any]]] = {}
    for label_file in sorted(labels_dir.glob("*.txt")):
        tile_id = label_file.stem
        boxes = []
        with open(label_file, "r") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 5:
                    class_id = int(parts[0])
                    cx, cy, w, h = map(float, parts[1:5])
                    boxes.append({
                        "class_id": class_id,
                        "bbox": [cx, cy, w, h],
                    })
        ground_truth[tile_id] = boxes

    logger.info(f"Loaded ground truth: {len(ground_truth)} tiles, "
                f"{sum(len(v) for v in ground_truth.values())} boxes")
    return ground_truth


# ---------------------------------------------------------------------------
# ONNX inference
# ---------------------------------------------------------------------------


def run_inference(tiles: List[Any], model_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Run ONNX Runtime INT8 model inference over the generated tiles.

    NOTE: Requires the Phase I ONNX model (yolov8n_int8.onnx).
    If the model is not available, returns empty predictions with a warning.

    Args:
        tiles: List of tile file paths or (tile_id, npy_path) tuples.
        model_path: File path to the ONNX model.

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

    predictions: Dict[str, List[Dict[str, Any]]] = {}
    for item in tiles:
        if isinstance(item, tuple):
            tile_id, npy_path = item
        else:
            tile_id = Path(str(item)).stem
            npy_path = str(item)

        tile_data = np.load(npy_path).astype(np.float32) / 255.0
        if tile_data.ndim == 2:
            tile_data = np.stack([tile_data] * 3, axis=-1)

        # Resize to model input size
        input_size = 640
        h, w = tile_data.shape[:2]
        scale = min(input_size / h, input_size / w)
        nh, nw = int(h * scale), int(w * scale)
        resized = np.zeros((input_size, input_size, 3), dtype=np.float32)
        resized[:nh, :nw] = tile_data[:nh, :nw]

        input_tensor = resized.transpose(2, 0, 1)[np.newaxis, ...]
        outputs = session.run(None, {input_name: input_tensor})

        tile_preds = []
        if outputs and len(outputs) > 0:
            # YOLOv8 output format: [batch, boxes, 6] where 6 = [cx, cy, w, h, conf, class]
            detections = outputs[0][0]
            for det in detections:
                if det[4] > 0.25:  # confidence threshold
                    cx, cy, w, h = det[:4] / input_size  # normalize
                    tile_preds.append({
                        "bbox": [float(cx), float(cy), float(w), float(h)],
                        "confidence": float(det[4]),
                        "class_id": int(det[5]),
                    })

        predictions[tile_id] = tile_preds

    logger.info(f"Inference complete: {sum(len(v) for v in predictions.values())} detections")
    return predictions


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------


def compute_metrics(predictions: Dict[str, List[Dict[str, Any]]],
                    ground_truth: Dict[str, List[Dict[str, Any]]]) -> Dict[str, float]:
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


def compute_ks_distance(tiles: Dict[str, List[Dict[str, Any]]],
                        reference_dataset: Optional[str] = None) -> float:
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
        logger.warning("Reference dataset comparison not implemented yet. "
                       "KS test is inter-pipelines only.")

    samples: Dict[str, List[float]] = {}
    for pipeline, tile_list in tiles.items():
        pixels = []
        for tile_path in tile_list:
            try:
                data = np.load(str(tile_path))
                pixels.extend(data.flatten().tolist())
            except Exception:
                continue
        if pixels:
            samples[pipeline] = pixels

    max_ks = 0.0
    pipeline_names = list(samples.keys())
    for i, p1 in enumerate(pipeline_names):
        for p2 in pipeline_names[i + 1:]:
            s, pv = ks_2samp(samples[p1], samples[p2])
            max_ks = max(max_ks, s)
            logger.info(f"KS({p1}, {p2}) = {s:.4f} (p={pv:.4e})")

    return round(max_ks, 4)


# ---------------------------------------------------------------------------
# Metadata loading helper
# ---------------------------------------------------------------------------


def load_metadata(metadata_path: str) -> Dict[str, Any]:
    """Load tile metadata from a JSON file."""
    with open(metadata_path, "r") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Full pipeline benchmark
# ---------------------------------------------------------------------------


def benchmark_all_pipelines(metadata_path: str, gt_path: str,
                            model_path: str) -> Dict[str, Any]:
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
    scene_dir = Path(metadata_path).parent

    logger.info(f"=== Benchmark: {scene_id} ===")

    # Load ground truth
    ground_truth = load_ground_truth(gt_path)

    # Collect tiles per pipeline
    tiles_by_pipeline: Dict[str, List[str]] = {}
    for p in PIPELINES:
        pipeline_dir = scene_dir / p
        tile_files = sorted(pipeline_dir.glob("*.npy"))
        tiles_by_pipeline[p] = [str(f) for f in tile_files]
        logger.info(f"Pipeline {p}: {len(tile_files)} tiles")

    # Run inference per pipeline
    predictions_by_pipeline: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for p in PIPELINES:
        tile_paths = tiles_by_pipeline.get(p, [])
        tile_items = [(Path(t).stem, t) for t in tile_paths]
        predictions_by_pipeline[p] = run_inference(tile_items, model_path)

    # Compute metrics per pipeline
    metrics_results: Dict[str, Dict[str, Any]] = {}
    for p in PIPELINES:
        preds = predictions_by_pipeline.get(p, {})
        metrics = compute_metrics(preds, ground_truth)
        metrics_results[p] = metrics
        logger.info(f"Pipeline {p}: P={metrics['precision']:.3f}, "
                    f"R={metrics['recall']:.3f}, "
                    f"mAP@0.5={metrics['mAP@0.5']:.3f}")

    # KS test (inter-pipeline)
    ks_result = compute_ks_distance(tiles_by_pipeline)

    results = {
        "scene_id": scene_id,
        "metrics_by_pipeline": metrics_results,
        "ks_max_distance": ks_result,
        "ground_truth_tiles": len(ground_truth),
        "note": (
            "estimate_bbox() uses a fixed size (methodological bias on "
            "mAP@0.5:0.95). KS test is inter-pipelines only (no comparison "
            "to real MRSSD dataset)."
        ),
    }

    logger.info(f"=== Benchmark Complete: {scene_id} ===")
    return results


# ---------------------------------------------------------------------------
# Results export
# ---------------------------------------------------------------------------


def export_results(results: Dict[str, Any], output_dir: str) -> Dict[str, str]:
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
        fieldnames = ["pipeline", "precision", "recall", "mAP@0.5",
                      "true_positives", "false_positives", "false_negatives"]
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
    parser.add_argument(
        "--metadata", required=True, help="Path to scene metadata.json"
    )
    parser.add_argument(
        "--ground-truth", required=True, help="Directory with YOLO label .txt files"
    )
    parser.add_argument(
        "--model", default="shared/models/yolov8n_int8.onnx",
        help="Path to ONNX model (default: shared/models/yolov8n_int8.onnx)"
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Output directory for results (default: phase0/data/results/)"
    )

    args = parser.parse_args()

    output_dir = args.output_dir or str(
        Path(__file__).parent / "data" / "results"
    )

    results = benchmark_all_pipelines(
        args.metadata, args.ground_truth, args.model
    )
    export_results(results, output_dir)

    logger.info("Benchmark complete.")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
