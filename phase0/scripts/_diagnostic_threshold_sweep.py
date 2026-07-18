#!/usr/bin/env python3
"""
Comprehensive Diagnostic: Confidence Sensitivity & Center-Distance at Multiple Thresholds.

Performs three analyses on Pipeline D predictions without modifying the benchmark:

1. VÉRIFICATION 1 — Confidence at GT center locations:
   For each ground-truth vessel, finds the closest of ALL 8400 raw YOLO proposals
   (regardless of confidence), records its distance and confidence score.
   Answers: does the model produce ANY high-confidence proposal near each GT?

2. VÉRIFICATION 2 — Sensitivity across confidence thresholds:
   Re-runs center-distance analysis at thresholds 0.05, 0.1, and 0.25.
   Answers: does lowering the threshold reveal valid detections that are
   suppressed by the domain-shift-induced confidence drop?

3. VISUALISATION — FP overlay on tiles:
   For each FP at threshold 0.25, generates a PNG with tile + prediction bbox
   + nearest GT bbox overlay.

Usage:
    uv run python phase0/scripts/_diagnostic_threshold_sweep.py
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
from PIL import Image, ImageDraw

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("diagnostic")

TILE_SIZE = 512
MODEL_INPUT_SIZE = 640
NMS_IOU_THRESHOLD = 0.5

# Scenes to analyze (scene 2 is the main one with 36 FP)
SCENE_2 = "S1D_IW_GRDH_1SDV_20260716T190458_20260716T190523_003703_006A03_9C83"
SCENE_1 = "S1D_IW_GRDH_1SDV_20260711T061903_20260711T061928_003622_00673D_224C"

TILES_ROOT = Path("phase0/data/tiles")
ANNOTATIONS_ROOT = Path("phase0/data/annotations")
MODEL_PATH = Path("shared/models/yolov8n_int8.onnx")
OUTPUT_DIR = Path("phase0/data/results/diagnostic_threshold_sweep")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
VIZ_DIR = OUTPUT_DIR / "visualizations"
VIZ_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# IoU (for NMS)
# ---------------------------------------------------------------------------

def compute_iou(box1: List[float], box2: List[float]) -> float:
    b1_x1 = box1[0] - box1[2] / 2
    b1_y1 = box1[1] - box1[3] / 2
    b1_x2 = box1[0] + box1[2] / 2
    b1_y2 = box1[1] + box1[3] / 2
    b2_x1 = box2[0] - box2[2] / 2
    b2_y1 = box2[1] - box2[3] / 2
    b2_x2 = box2[0] + box2[2] / 2
    b2_y2 = box2[1] + box2[3] / 2
    x1 = max(b1_x1, b2_x1)
    y1 = max(b1_y1, b2_y1)
    x2 = min(b1_x2, b2_x2)
    y2 = min(b1_y2, b2_y2)
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area1 = (b1_x2 - b1_x1) * (b1_y2 - b1_y1)
    area2 = (b2_x2 - b2_x1) * (b2_y2 - b2_y1)
    union = area1 + area2 - inter
    if union <= 0:
        return 0.0
    return inter / union


def nms_suppress(detections: List[Dict], iou_threshold: float = NMS_IOU_THRESHOLD) -> List[Dict]:
    if len(detections) <= 1:
        return detections
    sorted_dets = sorted(detections, key=lambda d: d["confidence"], reverse=True)
    kept = []
    while sorted_dets:
        best = sorted_dets.pop(0)
        kept.append(best)
        sorted_dets = [d for d in sorted_dets if compute_iou(best["bbox"], d["bbox"]) < iou_threshold]
    return kept


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_ground_truth(gt_dir: Path) -> Dict[str, List[Dict]]:
    gt: Dict[str, List[Dict]] = {}
    for label_file in sorted(gt_dir.glob("*.txt")):
        tile_id = label_file.stem
        boxes = []
        with open(label_file) as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 5:
                    cls_id = int(parts[0])
                    cx, cy, w, h = map(float, parts[1:5])
                    boxes.append({"class_id": cls_id, "bbox": [cx, cy, w, h]})
        gt[tile_id] = boxes
    return gt


def run_inference_raw(tile_paths: List[str]) -> Dict[str, np.ndarray]:
    """Run inference and return ALL 8400 raw proposals per tile (unthresholded).

    Returns {tile_id: np.ndarray of shape [8400, 5]} with [cx, cy, w, h, conf]
    in MODEL_INPUT_SIZE-normalized coordinates.
    """
    import onnxruntime as ort

    session = ort.InferenceSession(str(MODEL_PATH))
    input_name = session.get_inputs()[0].name

    all_raw: Dict[str, np.ndarray] = {}
    for idx, npy_path in enumerate(tile_paths):
        tile_id = Path(npy_path).stem
        tile_uint8 = np.load(npy_path).astype(np.uint8)
        if tile_uint8.ndim == 2:
            tile_rgb = np.stack([tile_uint8] * 3, axis=-1)
        else:
            tile_rgb = tile_uint8
        img = Image.fromarray(tile_rgb)
        img_resized = img.resize((MODEL_INPUT_SIZE, MODEL_INPUT_SIZE), Image.Resampling.LANCZOS)
        resized = np.array(img_resized, dtype=np.float32) / 255.0
        input_tensor = resized.transpose(2, 0, 1)[np.newaxis, ...]
        outputs = session.run(None, {input_name: input_tensor})
        raw = outputs[0][0].T  # [8400, 5]
        all_raw[tile_id] = raw
        if (idx + 1) % 200 == 0:
            logger.info(f"  Inference: {idx + 1}/{len(tile_paths)}")
    logger.info(f"Inference complete: {len(all_raw)} tiles")
    return all_raw


def proposals_from_raw(raw: np.ndarray, conf_threshold: float) -> List[Dict]:
    """Convert raw [8400, 5] to filtered+NMS'd predictions at given threshold."""
    input_size = MODEL_INPUT_SIZE
    preds = []
    for det in raw:
        cx, cy, w, h, conf = float(det[0]), float(det[1]), float(det[2]), float(det[3]), float(det[4])
        if conf > conf_threshold:
            preds.append({
                "bbox": [cx / input_size, cy / input_size, w / input_size, h / input_size],
                "confidence": conf,
                "class_id": 0,
            })
    return nms_suppress(preds)


def center_distance(bbox1: List[float], bbox2: List[float], ts: int = TILE_SIZE) -> float:
    """Euclidean distance in pixels between centers of two YOLO boxes."""
    dx = (bbox1[0] - bbox2[0]) * ts
    dy = (bbox1[1] - bbox2[1]) * ts
    return float(np.sqrt(dx ** 2 + dy ** 2))


# ---------------------------------------------------------------------------
# VÉRIFICATION 1 — Confidence at GT centers
# ---------------------------------------------------------------------------

def verify_confidence_at_gt_centers(
    all_raw: Dict[str, np.ndarray],
    ground_truth: Dict[str, List[Dict]],
) -> Dict:
    """For each GT box, find the closest raw proposal (among all 8400).

    Records: distance to closest proposal, confidence of that proposal.
    Answers: does the model fire at all near GT locations, even with low conf?
    """
    records = []
    tile_ids = sorted(set(all_raw.keys()) & set(ground_truth.keys()))

    for tile_id in tile_ids:
        raw = all_raw[tile_id]
        gts = ground_truth[tile_id]
        if not len(gts):
            continue

        # Convert raw proposals to normalized coords for comparison
        proposals_norm = []
        for det in raw:
            cx_n = float(det[0]) / MODEL_INPUT_SIZE
            cy_n = float(det[1]) / MODEL_INPUT_SIZE
            conf = float(det[4])
            proposals_norm.append((cx_n, cy_n, conf))

        for gt in gts:
            gcx, gcy = gt["bbox"][0], gt["bbox"][1]
            best_dist = float("inf")
            best_conf = 0.0
            for p_cx, p_cy, p_conf in proposals_norm:
                dx = (p_cx - gcx) * TILE_SIZE
                dy = (p_cy - gcy) * TILE_SIZE
                dist = np.sqrt(dx ** 2 + dy ** 2)
                if dist < best_dist:
                    best_dist = dist
                    best_conf = p_conf
            records.append({
                "tile_id": tile_id,
                "gt_center": (round(float(gcx), 4), round(float(gcy), 4)),
                "closest_proposal_dist_px": round(float(best_dist), 2),
                "closest_proposal_confidence": round(float(best_conf), 6),
                "inches": best_dist <= 50,  # loosely within 50px
            })

    confidences = [r["closest_proposal_confidence"] for r in records]
    distances = [r["closest_proposal_dist_px"] for r in records]
    within_50px_low_conf = sum(1 for r in records if r["closest_proposal_dist_px"] <= 50)
    high_conf_near_gt = sum(1 for r in records
                            if r["closest_proposal_dist_px"] <= 50 and r["closest_proposal_confidence"] > 0.25)

    # Distribution of best confidence per GT
    conf_bands = {
        "conf > 0.25 (would pass threshold)": 0,
        "conf 0.1 - 0.25": 0,
        "conf 0.05 - 0.1": 0,
        "conf 0.01 - 0.05": 0,
        "conf < 0.01 (near zero)": 0,
    }
    for r in records:
        c = r["closest_proposal_confidence"]
        if c > 0.25:
            conf_bands["conf > 0.25 (would pass threshold)"] += 1
        elif c > 0.1:
            conf_bands["conf 0.1 - 0.25"] += 1
        elif c > 0.05:
            conf_bands["conf 0.05 - 0.1"] += 1
        elif c > 0.01:
            conf_bands["conf 0.01 - 0.05"] += 1
        else:
            conf_bands["conf < 0.01 (near zero)"] += 1

    # Distance distribution
    dist_bands = {"≤10px": 0, "11-20px": 0, "21-50px": 0, "51-100px": 0, ">100px": 0}
    for d in distances:
        if d <= 10: dist_bands["≤10px"] += 1
        elif d <= 20: dist_bands["11-20px"] += 1
        elif d <= 50: dist_bands["21-50px"] += 1
        elif d <= 100: dist_bands["51-100px"] += 1
        else: dist_bands[">100px"] += 1

    return {
        "total_gt_boxes_analyzed": len(records),
        "confidence_at_closest_proposal_per_gt": conf_bands,
        "distance_to_closest_proposal_per_gt": dist_bands,
        "avg_distance_px": round(float(np.mean(distances)), 2),
        "median_distance_px": round(float(np.median(distances)), 2),
        "max_confidence_at_any_gt": round(float(np.max(confidences)), 6),
        "gt_within_50px_of_any_proposal": within_50px_low_conf,
        "gt_with_both_50px_and_conf_gt_0.25": high_conf_near_gt,
        "per_gt": records,
    }


# ---------------------------------------------------------------------------
# VÉRIFICATION 2 — Sensitivity at multiple thresholds
# ---------------------------------------------------------------------------

def analyze_threshold_sensitivity(
    all_raw: Dict[str, np.ndarray],
    ground_truth: Dict[str, List[Dict]],
    thresholds: List[float],
) -> Dict:
    """Run center-distance + IoU analysis at each confidence threshold."""
    results = {}
    for thresh in sorted(thresholds, reverse=True):
        # Build predictions at this threshold
        predictions: Dict[str, List[Dict]] = {}
        for tile_id, raw in all_raw.items():
            preds = proposals_from_raw(raw, conf_threshold=thresh)
            predictions[tile_id] = preds

        # Center-distance metrics
        total_preds = sum(len(v) for v in predictions.values())
        dist_bands = {"≤10px": 0, "11-20px": 0, "21-50px": 0, "51-100px": 0, ">100px": 0}
        iou_bands = {"IoU≥0.5": 0, "0.3≤IoU<0.5": 0, "0.1≤IoU<0.3": 0, "IoU<0.1": 0}
        total_analyzed = 0
        tiles_with_preds = 0

        for tile_id in sorted(set(predictions.keys()) & set(ground_truth.keys())):
            preds = predictions.get(tile_id, [])
            gts = ground_truth.get(tile_id, [])
            if not preds:
                continue
            tiles_with_preds += 1

            for pred in preds:
                total_analyzed += 1
                min_dist = float("inf")
                best_iou = 0.0
                for gt in gts:
                    d = center_distance(pred["bbox"], gt["bbox"])
                    iou = compute_iou(pred["bbox"], gt["bbox"])
                    if d < min_dist:
                        min_dist = d
                        best_iou = iou

                if min_dist <= 10: dist_bands["≤10px"] += 1
                elif min_dist <= 20: dist_bands["11-20px"] += 1
                elif min_dist <= 50: dist_bands["21-50px"] += 1
                elif min_dist <= 100: dist_bands["51-100px"] += 1
                else: dist_bands[">100px"] += 1

                if best_iou >= 0.5: iou_bands["IoU≥0.5"] += 1
                elif best_iou >= 0.3: iou_bands["0.3≤IoU<0.5"] += 1
                elif best_iou >= 0.1: iou_bands["0.1≤IoU<0.3"] += 1
                else: iou_bands["IoU<0.1"] += 1

        results[f"threshold_{thresh:.2f}"] = {
            "conf_threshold": thresh,
            "total_predictions_after_nms": total_preds,
            "tiles_with_predictions": tiles_with_preds,
            "predictions_analyzed": total_analyzed,
            "center_distance_bands": dist_bands,
            "iou_bands": iou_bands,
        }
    return results


# ---------------------------------------------------------------------------
# VISUALISATION — FP overlays on tiles
# ---------------------------------------------------------------------------

def generate_fp_visualizations(
    all_raw: Dict[str, np.ndarray],
    ground_truth: Dict[str, List[Dict]],
    conf_threshold: float = 0.25,
    max_samples: int = 50,
) -> List[str]:
    """Generate PNG overlays for each false positive prediction."""
    generated = []
    tile_paths_cache: Dict[str, str] = {}

    # Build tile path mapping
    for scene_dir in [SCENE_1, SCENE_2]:
        d = TILES_ROOT / scene_dir / "D"
        for f in d.glob("*.npy"):
            tile_paths_cache[f.stem] = str(f)

    for tile_id in sorted(set(all_raw.keys()) & set(ground_truth.keys())):
        if len(generated) >= max_samples:
            break

        raw = all_raw[tile_id]
        preds = proposals_from_raw(raw, conf_threshold=conf_threshold)
        gts = ground_truth[tile_id]

        if not preds:
            continue

        npy_path = tile_paths_cache.get(tile_id)
        if npy_path is None:
            continue

        # Load tile
        arr = np.load(npy_path).astype(np.uint8)
        if arr.ndim == 2:
            img = Image.fromarray(arr, mode="L").convert("RGB")
        else:
            img = Image.fromarray(arr)

        draw = ImageDraw.Draw(img)
        ts = TILE_SIZE

        for pred in preds:
            if len(generated) >= max_samples:
                break

            pb = pred["bbox"]
            # Prediction box: RED
            px1 = int((pb[0] - pb[2] / 2) * ts)
            py1 = int((pb[1] - pb[3] / 2) * ts)
            px2 = int((pb[0] + pb[2] / 2) * ts)
            py2 = int((pb[1] + pb[3] / 2) * ts)
            draw.rectangle([px1, py1, px2, py2], outline=(255, 0, 0), width=2)

            # Find nearest GT
            min_dist = float("inf")
            best_gt = None
            for gt in gts:
                d = center_distance(pb, gt["bbox"])
                if d < min_dist:
                    min_dist = d
                    best_gt = gt

            # Nearest GT box: GREEN
            if best_gt:
                gb = best_gt["bbox"]
                gx1 = int((gb[0] - gb[2] / 2) * ts)
                gy1 = int((gb[1] - gb[3] / 2) * ts)
                gx2 = int((gb[0] + gb[2] / 2) * ts)
                gy2 = int((gb[1] + gb[3] / 2) * ts)
                draw.rectangle([gx1, gy1, gx2, gy2], outline=(0, 255, 0), width=2)
                # Line connecting centers
                pcx = int(pb[0] * ts)
                pcy = int(pb[1] * ts)
                gcx = int(gb[0] * ts)
                gcy = int(gb[1] * ts)
                draw.line([pcx, pcy, gcx, gcy], fill=(255, 255, 0), width=1)

            # Label
            label = f"FP conf={pred['confidence']:.3f} dist={min_dist:.0f}px"
            draw.text((px1 + 2, py1 - 12), label, fill=(255, 0, 0))

            out_path = VIZ_DIR / f"{tile_id}_fp_conf{pred['confidence']:.3f}_dist{min_dist:.0f}.png"
            img.save(str(out_path))
            generated.append(str(out_path))

    return generated


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("=" * 70)
    logger.info("DIAGNOSTIC COMPLET — Sensibilité au seuil + Confiance aux centres GT")
    logger.info("=" * 70)

    scenes = [SCENE_1, SCENE_2]

    # Load ground truth for both scenes
    all_gt: Dict[str, List[Dict]] = {}
    for scene_id in scenes:
        gt_dir = ANNOTATIONS_ROOT / scene_id / "labels"
        gt = load_ground_truth(gt_dir)
        all_gt.update(gt)
        logger.info(f"  {scene_id[:60]}: {len(gt)} tiles, "
                    f"{sum(len(v) for v in gt.values())} GT boxes")

    # Collect annotated tile npy paths (Pipeline D)
    tile_paths: List[str] = []
    for scene_id in scenes:
        tile_dir = TILES_ROOT / scene_id / "D"
        gt_ids = set(load_ground_truth(ANNOTATIONS_ROOT / scene_id / "labels").keys())
        for f in tile_dir.glob("*.npy"):
            if f.stem in gt_ids:
                tile_paths.append(str(f))
    logger.info(f"Total annotated tiles to analyze: {len(tile_paths)}")

    if not tile_paths:
        logger.error("No tiles found. Exiting.")
        sys.exit(1)

    # Run inference, keep ALL raw proposals
    logger.info("Running inference (saving ALL raw proposals)...")
    all_raw = run_inference_raw(tile_paths)

    total_proposals = sum(raw.shape[0] for raw in all_raw.values())
    logger.info(f"Total raw proposals collected: {total_proposals} "
                f"(~{total_proposals // max(len(all_raw), 1):,} per tile)")

    # === VÉRIFICATION 1 ===
    logger.info("")
    logger.info("=" * 70)
    logger.info("VÉRIFICATION 1 — Confiance au plus proche candidat pour chaque GT")
    logger.info("=" * 70)
    verif1 = verify_confidence_at_gt_centers(all_raw, all_gt)

    logger.info(f"GT boxes analysés: {verif1['total_gt_boxes_analyzed']}")
    logger.info(f"Distance moyenne au meilleur candidat: {verif1['avg_distance_px']}px")
    logger.info(f"Distance médiane: {verif1['median_distance_px']}px")
    logger.info(f"Confiance max observée près d'un GT: {verif1['max_confidence_at_any_gt']}")
    logger.info(f"GT à ≤50px d'un candidat: {verif1['gt_within_50px_of_any_proposal']}/{verif1['total_gt_boxes_analyzed']}")
    logger.info(f"GT à ≤50px AVEC conf>0.25: {verif1['gt_with_both_50px_and_conf_gt_0.25']}")
    logger.info("")
    logger.info("--- Distribution de la confiance du candidat le plus proche ---")
    for band, count in verif1["confidence_at_closest_proposal_per_gt"].items():
        pct = count / max(verif1['total_gt_boxes_analyzed'], 1) * 100
        logger.info(f"  {band}: {count} ({pct:.1f}%)")
    logger.info("")
    logger.info("--- Distribution de la distance au meilleur candidat (parmi 8400) ---")
    for band, count in verif1["distance_to_closest_proposal_per_gt"].items():
        pct = count / max(verif1['total_gt_boxes_analyzed'], 1) * 100
        logger.info(f"  {band}: {count} ({pct:.1f}%)")

    # === VÉRIFICATION 2 ===
    logger.info("")
    logger.info("=" * 70)
    logger.info("VÉRIFICATION 2 — Sensibilité aux seuils de confiance")
    logger.info("=" * 70)
    thresholds = [0.25, 0.1, 0.05]
    verif2 = analyze_threshold_sensitivity(all_raw, all_gt, thresholds)

    for key in sorted(verif2.keys()):
        tdata = verif2[key]
        th = tdata["conf_threshold"]
        logger.info(f"")
        logger.info(f"--- Seuil θ={th:.2f} ---")
        logger.info(f"  Prédictions: {tdata['total_predictions_after_nms']} "
                    f"(sur {tdata['tiles_with_predictions']} tuiles)")
        logger.info(f"  Distance au centre GT le plus proche:")
        for band, count in tdata["center_distance_bands"].items():
            pct = count / max(tdata["predictions_analyzed"], 1) * 100
            logger.info(f"    {band}: {count} ({pct:.1f}%)")
        logger.info(f"  IoU avec le meilleur GT:")
        for band, count in tdata["iou_bands"].items():
            pct = count / max(tdata["predictions_analyzed"], 1) * 100
            logger.info(f"    {band}: {count} ({pct:.1f}%)")

    # === VISUALISATION ===
    logger.info("")
    logger.info("=" * 70)
    logger.info("VISUALISATION — Faux positifs θ=0.25 superposés aux tuiles")
    logger.info("=" * 70)
    viz_files = generate_fp_visualizations(all_raw, all_gt, conf_threshold=0.25, max_samples=50)
    logger.info(f"  {len(viz_files)} visualisations générées dans {VIZ_DIR}")

    # === SAVE RESULTS ===
    results = {
        "verification_1_confidence_at_gt_centers": {
            "total_gt_boxes_analyzed": verif1["total_gt_boxes_analyzed"],
            "avg_distance_px": verif1["avg_distance_px"],
            "median_distance_px": verif1["median_distance_px"],
            "max_confidence_at_any_gt": verif1["max_confidence_at_any_gt"],
            "gt_within_50px_of_any_proposal": verif1["gt_within_50px_of_any_proposal"],
            "gt_with_both_50px_and_conf_gt_0.25": verif1["gt_with_both_50px_and_conf_gt_0.25"],
            "confidence_distribution": verif1["confidence_at_closest_proposal_per_gt"],
            "distance_distribution": verif1["distance_to_closest_proposal_per_gt"],
        },
        "verification_2_threshold_sensitivity": verif2,
        "visualizations": {
            "count": len(viz_files),
            "directory": str(VIZ_DIR),
            "files": viz_files,
        },
    }

    results_path = OUTPUT_DIR / "diagnostic_results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"\nRésultats complets sauvegardés: {results_path}")
    logger.info("Diagnostic terminé.")


if __name__ == "__main__":
    main()
