#!/usr/bin/env python3
"""Visualize False Positive Predictions for Human Audit.

Generates a gallery of prediction vs ground-truth overlay images, one per
false positive (FP) detection, so a human can visually classify each FP as:

    A) Clearly a vessel (model correctly detected a real ship)
    B) Clearly NOT a vessel (noise/artifact)
    C) Ambiguous / uncertain

Usage
-----
    # From a Colab instance with tiles + model + GT available:
    python visualize_false_positives.py \\
        --tiles-dir data/tiles/S1D_20260716/D \\
        --gt-dir data/annotations/S1D_20260716/labels \\
        --model path/to/best.pt \\
        --output research/results/fp_audit

    # Using ONNX model (Phase I):
    python visualize_false_positives.py \\
        --tiles-dir data/tiles/S1D_20260716/D \\
        --gt-dir data/annotations/S1D_20260716/labels \\
        --model shared/models/yolov8n_int8.onnx \\
        --output research/results/fp_audit

Requirements
------------
    ultralytics  (for .pt model)
    Pillow, numpy, matplotlib
"""

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("visualize_fp")

IOU_THRESHOLD = 0.5
MODEL_INPUT_SIZE = 640


def load_model(model_path: str):
    """Load model — supports both .pt (Ultralytics) and .onnx."""
    path = Path(model_path)
    if path.suffix == ".onnx":
        try:
            import onnxruntime as ort
        except ImportError:
            logger.error("onnxruntime not installed. Install with: pip install onnxruntime")
            sys.exit(1)
        logger.info("Loading ONNX model: %s", model_path)
        session = ort.InferenceSession(str(model_path))
        return {"type": "onnx", "session": session, "input_name": session.get_inputs()[0].name}
    elif path.suffix == ".pt":
        try:
            from ultralytics import YOLO
        except ImportError:
            logger.error("ultralytics not installed. Install with: pip install ultralytics")
            sys.exit(1)
        logger.info("Loading Ultralytics model: %s", model_path)
        model = YOLO(str(model_path))
        return {"type": "ultralytics", "model": model}
    else:
        raise ValueError(f"Unsupported model format: {path.suffix}")


def load_ground_truth(gt_dir: str) -> dict[str, list[dict]]:
    """Load YOLO-format ground truth labels."""
    labels_dir = Path(gt_dir)
    if not labels_dir.exists():
        raise FileNotFoundError(f"GT directory not found: {labels_dir}")

    gt = {}
    for f in sorted(labels_dir.glob("*.txt")):
        tile_id = f.stem
        boxes = []
        with open(f) as fh:
            for line in fh:
                parts = line.strip().split()
                if len(parts) == 5:
                    cx, cy, w, h = map(float, parts[1:5])
                    boxes.append({"bbox": [cx, cy, w, h]})
        if boxes:
            gt[tile_id] = boxes
    logger.info("Loaded GT: %d tiles, %d boxes", len(gt), sum(len(v) for v in gt.values()))
    return gt


def compute_iou(box1: list[float], box2: list[float]) -> float:
    """IoU between two YOLO-format [cx, cy, w, h] boxes."""
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
    return inter / union if union > 0 else 0.0


def predict_onnx(session, input_name, tile_uint8, conf_threshold: float):
    """Run ONNX inference on a single tile."""
    tile_rgb = np.stack([tile_uint8] * 3, axis=-1) if tile_uint8.ndim == 2 else tile_uint8
    img = Image.fromarray(tile_rgb)
    img_resized = img.resize((MODEL_INPUT_SIZE, MODEL_INPUT_SIZE), Image.Resampling.LANCZOS)
    resized = np.array(img_resized, dtype=np.float32) / 255.0
    input_tensor = resized.transpose(2, 0, 1)[np.newaxis, ...]
    outputs = session.run(None, {input_name: input_tensor})

    dets = outputs[0][0].T  # [8400, 5]
    results = []
    for det in dets:
        cx, cy, w, h, conf = float(det[0]), float(det[1]), float(det[2]), float(det[3]), float(det[4])
        if conf > conf_threshold:
            results.append({
                "bbox": [cx / MODEL_INPUT_SIZE, cy / MODEL_INPUT_SIZE, w / MODEL_INPUT_SIZE, h / MODEL_INPUT_SIZE],
                "confidence": conf,
            })
    # NMS
    results.sort(key=lambda d: d["confidence"], reverse=True)
    kept = []
    for r in results:
        if not any(compute_iou(r["bbox"], k["bbox"]) > 0.5 for k in kept):
            kept.append(r)
    return kept


def predict_ultralytics(model, tile_uint8, conf_threshold: float):
    """Run Ultralytics inference on a single tile."""
    tile_rgb = np.stack([tile_uint8] * 3, axis=-1) if tile_uint8.ndim == 2 else tile_uint8
    results = model(tile_rgb, imgsz=MODEL_INPUT_SIZE, conf=conf_threshold, iou=0.5, verbose=False)
    dets = []
    for r in results:
        if r.boxes is not None:
            for box, conf in zip(r.boxes.xywhn, r.boxes.conf):
                dets.append({
                    "bbox": [float(box[0]), float(box[1]), float(box[2]), float(box[3])],
                    "confidence": float(conf),
                })
    return dets


def generate_visualization(
    tile_uint8, tile_id: str,
    ground_truth: list[dict],
    false_positives: list[dict],
    output_dir: Path,
):
    """Generate a single visualization image with GT (green) and FP (red) boxes."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches

    fig, ax = plt.subplots(1, 1, figsize=(10, 10))
    ax.imshow(tile_uint8, cmap="gray", vmin=0, vmax=255)

    h, w = tile_uint8.shape[:2]

    # Draw ground truth boxes in GREEN
    for gt in ground_truth:
        cx, cy, bw, bh = gt["bbox"]
        x1 = (cx - bw / 2) * w
        y1 = (cy - bh / 2) * h
        rect = patches.Rectangle(
            (x1, y1), bw * w, bh * h,
            linewidth=2, edgecolor="lime", facecolor="none", linestyle="-",
        )
        ax.add_patch(rect)
        ax.plot(cx * w, cy * h, marker="o", color="lime", markersize=6)

    # Draw FALSE POSITIVE predictions in RED
    for fp in false_positives:
        cx, cy, bw, bh = fp["bbox"]
        x1 = (cx - bw / 2) * w
        y1 = (cy - bh / 2) * h
        rect = patches.Rectangle(
            (x1, y1), bw * w, bh * h,
            linewidth=2, edgecolor="red", facecolor="none", linestyle="-",
        )
        ax.add_patch(rect)
        ax.plot(cx * w, cy * h, marker="x", color="red", markersize=8)
        ax.text(
            x1, y1 - 5, f"conf={fp['confidence']:.3f}",
            color="red", fontsize=8, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.7),
        )

    ax.set_title(f"Tile: {tile_id}\nGreen=GT (AIS)  Red=FP prediction", fontsize=12)
    ax.axis("off")

    save_path = output_dir / f"fp_{tile_id}.png"
    fig.savefig(save_path, dpi=150, bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)
    return save_path


def generate_html_gallery(visualizations: list[Path], output_dir: Path):
    """Create an HTML page for 3-category visual classification."""
    html_parts = []
    html_parts.append("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>False Positive Visual Audit</title>
<style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
           background: #0f172a; color: #e2e8f0; padding: 20px; }
    h1 { text-align: center; margin-bottom: 8px; font-size: 1.5rem; }
    .progress { text-align: center; margin-bottom: 20px; font-size: 1.1rem; color: #94a3b8; }
    .progress span { font-weight: bold; color: #38bdf8; }
    .card { background: #1e293b; border-radius: 12px; padding: 16px; margin-bottom: 24px;
            max-width: 900px; margin-left: auto; margin-right: auto;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3); }
    .card img { width: 100%; border-radius: 8px; display: block; }
    .card .tile-id { font-family: monospace; font-size: 0.85rem; color: #94a3b8; margin: 8px 0; }
    .buttons { display: flex; gap: 10px; margin-top: 12px; flex-wrap: wrap; }
    .btn { flex: 1; padding: 12px 16px; border: none; border-radius: 8px; font-size: 1rem;
           font-weight: 600; cursor: pointer; transition: all 0.2s; min-width: 120px; }
    .btn-a { background: #22c55e; color: #052e16; }
    .btn-a:hover { background: #16a34a; transform: translateY(-1px); }
    .btn-a.selected { box-shadow: 0 0 0 3px #86efac, 0 0 0 5px #22c55e; }
    .btn-b { background: #ef4444; color: #450a0a; }
    .btn-b:hover { background: #dc2626; transform: translateY(-1px); }
    .btn-b.selected { box-shadow: 0 0 0 3px #fca5a5, 0 0 0 5px #ef4444; }
    .btn-c { background: #f59e0b; color: #451a03; }
    .btn-c:hover { background: #d97706; transform: translateY(-1px); }
    .btn-c.selected { box-shadow: 0 0 0 3px #fcd34d, 0 0 0 5px #f59e0b; }
    .btn-done { background: #3b82f6; color: #fff; flex: 0 0 auto; padding: 12px 32px; }
    .btn-done:hover { background: #2563eb; }
    .actions { text-align: center; margin-top: 20px; }
    .summary { background: #1e293b; border-radius: 12px; padding: 20px; max-width: 900px;
               margin: 20px auto; display: none; }
    .summary table { width: 100%; border-collapse: collapse; margin-top: 12px; }
    .summary th, .summary td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #334155; }
    .summary th { color: #94a3b8; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; }
    .badge-a { background: #22c55e; color: #052e16; }
    .badge-b { background: #ef4444; color: #450a0a; }
    .badge-c { background: #f59e0b; color: #451a03; }
    .badge-pending { background: #475569; color: #cbd5e1; }
</style>
</head>
<body>
<h1>🔍 False Positive Visual Audit</h1>
<p class="progress">Progress: <span id="progress-count">0</span> / <span id="total-count">""" + str(len(visualizations)) + """</span> classified</p>
<div id="gallery">
""")

    for i, vpath in enumerate(visualizations):
        rel = vpath.name
        html_parts.append(f"""
<div class="card" data-idx="{i}" data-tile="{vpath.stem}">
    <img src="{rel}" alt="FP visualization for {vpath.stem}" loading="lazy">
    <div class="tile-id">[{i+1}/{len(visualizations)}] {vpath.stem}</div>
    <div class="buttons">
        <button class="btn btn-a" onclick="classify({i},'A')">🟢 A — Clearly a vessel</button>
        <button class="btn btn-b" onclick="classify({i},'B')">🔴 B — Not a vessel (noise)</button>
        <button class="btn btn-c" onclick="classify({i},'C')">🟡 C — Ambiguous</button>
    </div>
</div>""")

    html_parts.append(f"""
</div>
<div class="actions">
    <button class="btn btn-done" onclick="showSummary()">📊 Show Summary</button>
    <button class="btn btn-done" onclick="exportResults()" style="background:#8b5cf6;">💾 Export JSON</button>
</div>
<div class="summary" id="summary">
    <h2>📋 Audit Summary</h2>
    <table>
        <tr><th>Category</th><th>Count</th><th>Percentage</th></tr>
        <tr><td><span class="badge badge-a">A — Clearly a vessel</span></td><td id="count-a">0</td><td id="pct-a">0%</td></tr>
        <tr><td><span class="badge badge-b">B — Not a vessel</span></td><td id="count-b">0</td><td id="pct-b">0%</td></tr>
        <tr><td><span class="badge badge-c">C — Ambiguous</span></td><td id="count-c">0</td><td id="pct-c">0%</td></tr>
    </table>
    <p id="interpretation" style="margin-top:16px; color:#94a3b8;"></p>
</div>
<script>
const results = {{}};
const TOTAL = {len(visualizations)};

function classify(idx, cat) {{
    results[idx] = cat;
    const card = document.querySelector(`.card[data-idx="${{idx}}"]`);
    card.querySelectorAll('.btn').forEach(b => b.classList.remove('selected'));
    card.querySelector(`.btn-$(cat)`).classList.add('selected');
    const done = Object.keys(results).length;
    document.getElementById('progress-count').textContent = done;
    if (done === TOTAL) {{
        document.querySelector('.btn-done').textContent = '🎉 All classified! Show Summary';
    }}
}}

function showSummary() {{
    const counts = {{A:0, B:0, C:0}};
    Object.values(results).forEach(c => counts[c]++);
    document.getElementById('count-a').textContent = counts.A;
    document.getElementById('count-b').textContent = counts.B;
    document.getElementById('count-c').textContent = counts.C;
    document.getElementById('pct-a').textContent = TOTAL > 0 ? Math.round(counts.A/TOTAL*100) + '%' : '0%';
    document.getElementById('pct-b').textContent = TOTAL > 0 ? Math.round(counts.B/TOTAL*100) + '%' : '0%';
    document.getElementById('pct-c').textContent = TOTAL > 0 ? Math.round(counts.C/TOTAL*100) + '%' : '0%';

    let interp = '';
    if (counts.A + counts.C > TOTAL * 0.3) {{
        interp = '⚠️ Significant proportion of FPs may be real vessels. GT alignment issue likely.';
    }} else if (counts.A + counts.C > TOTAL * 0.1) {{
        interp = '🔶 Some FPs may be real vessels. Further investigation recommended.';
    }} else {{
        interp = '✅ Most FPs are genuine noise. Model detections are truly false positives.';
    }}
    document.getElementById('interpretation').textContent = interp;
    document.getElementById('summary').style.display = 'block';
}}

function exportResults() {{
    const counts = {{A:0, B:0, C:0}};
    const details = {{}};
    document.querySelectorAll('.card').forEach(card => {{
        const idx = parseInt(card.dataset.idx);
        const tile = card.dataset.tile;
        details[tile] = results[idx] || 'unclassified';
        if (results[idx]) counts[results[idx]]++;
    }});
    const data = {{
        total: TOTAL,
        classified: Object.keys(results).length,
        counts: counts,
        per_tile: details,
        interpretation: document.getElementById('interpretation').textContent,
    }};
    const blob = new Blob([JSON.stringify(data, null, 2)], {{type: 'application/json'}});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'fp_audit_results.json';
    a.click();
}}
</script>
</body>
</html>""")

    html_path = output_dir / "fp_audit.html"
    with open(html_path, "w") as f:
        f.write("\n".join(html_parts))
    logger.info("HTML gallery created: %s", html_path)
    return html_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate false positive visualizations for human audit"
    )
    parser.add_argument("--tiles-dir", required=True, help="Directory containing .npy tile files")
    parser.add_argument("--gt-dir", required=True, help="Directory containing YOLO .txt labels")
    parser.add_argument("--model", required=True, help="Path to .pt or .onnx model")
    parser.add_argument("--output", default="research/results/fp_audit", help="Output directory")
    parser.add_argument("--conf", type=float, default=0.001, help="Confidence threshold (default: 0.001 — low to capture any prediction)")
    parser.add_argument("--limit", type=int, default=None, help="Max FPs to visualize (for testing)")
    parser.add_argument("--no-html", action="store_true", help="Skip HTML gallery generation")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load model
    model_info = load_model(args.model)
    logger.info("Model loaded: %s", args.model)

    # Load ground truth
    gt = load_ground_truth(args.gt_dir)

    # Load tiles
    tiles_dir = Path(args.tiles_dir)
    tile_paths = sorted(tiles_dir.glob("*.npy"))
    logger.info("Found %d tiles in %s", len(tile_paths), tiles_dir)

    # Intersect tiles with GT
    gt_tile_ids = set(gt.keys())
    tile_paths = [t for t in tile_paths if t.stem in gt_tile_ids]
    logger.info("Tiles with GT annotations: %d", len(tile_paths))

    # Run inference and find false positives
    conf_threshold = args.conf
    all_fps = []
    total_tiles_with_gt = len(tile_paths)
    tiles_with_zero_preds = 0

    for tile_path in tile_paths:
        tile_id = tile_path.stem
        tile_uint8 = np.load(str(tile_path)).astype(np.uint8)

        # Run inference
        if model_info["type"] == "onnx":
            preds = predict_onnx(model_info["session"], model_info["input_name"], tile_uint8, conf_threshold)
        else:
            preds = predict_ultralytics(model_info["model"], tile_uint8, conf_threshold)

        tile_gt = gt.get(tile_id, [])

        if len(preds) == 0:
            tiles_with_zero_preds += 1
            continue

        # Find false positives (predictions with no GT match)
        fps = []
        for pred in preds:
            is_match = False
            for g in tile_gt:
                if compute_iou(pred["bbox"], g["bbox"]) >= IOU_THRESHOLD:
                    is_match = True
                    break
            if not is_match:
                fps.append(pred)

        if fps:
            fp_path = generate_visualization(
                tile_uint8, tile_id, tile_gt, fps, output_dir
            )
            all_fps.append((tile_id, fp_path, len(fps)))

            if args.limit and len(all_fps) >= args.limit:
                break

    if tiles_with_zero_preds > 0:
        logger.warning(
            "%d/%d tiles with GT had ZERO predictions at conf>%s — try a lower --conf value",
            tiles_with_zero_preds, total_tiles_with_gt, conf_threshold,
        )

    logger.info("=" * 50)
    logger.info("FALSE POSITIVE SUMMARY")
    logger.info("=" * 50)
    logger.info("Tiles with FPs: %d", len(all_fps))
    logger.info("Total FP detections: %d", sum(f[2] for f in all_fps))
    logger.info("Visualizations saved to: %s", output_dir)

    # Save metadata
    metadata = {
        "model": args.model,
        "tiles_dir": args.tiles_dir,
        "gt_dir": args.gt_dir,
        "total_fp_tiles": len(all_fps),
        "total_fp_detections": sum(f[2] for f in all_fps),
        "visualizations": [
            {"tile_id": t, "image": str(p), "fp_count": c}
            for t, p, c in all_fps
        ],
    }
    meta_path = output_dir / "fp_metadata.json"
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)
    logger.info("Metadata saved: %s", meta_path)

    # Generate HTML gallery
    if not args.no_html:
        vis_paths = [p for _, p, _ in all_fps]
        html_path = generate_html_gallery(vis_paths, output_dir)
        logger.info("HTML gallery: %s", html_path)
        logger.info("Open in browser: file://%s", html_path.resolve())

    # Copy this script to output for traceability
    shutil.copy2(__file__, output_dir / "visualize_false_positives.py")

    logger.info("Done. To classify, open the HTML gallery in your browser.")


if __name__ == "__main__":
    main()
