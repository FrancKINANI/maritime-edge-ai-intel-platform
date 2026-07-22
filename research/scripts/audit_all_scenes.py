"""
audit_all_scenes.py — False Positive visual audit across ALL scenes with tiles + annotations.

Usage (from notebook):
    python audit_all_scenes.py \\
        --tiles-dir research/data/tiles \\
        --annotations-dir research/data/annotations \\
        --model shared/models/yolov8n_mrssd_int8.onnx \\
        --output research/results/fp_audit

This script:
1. Finds all scenes with BOTH tiles AND annotations
2. For each scene: loads GT labels, runs ONNX inference at conf=0.001, finds FPs
3. Generates per-tile visualizations and a combined HTML gallery

Prerequisite:
    The project root must be in sys.path.
"""

import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("audit_all_scenes")

# Constants
CONF_THRESHOLD = 0.001
IOU_MATCH = 0.5
MODEL_INPUT_SIZE = 640


def compute_iou(box1, box2):
    """IoU for YOLO-format [cx, cy, w, h] boxes."""
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


def load_gt_labels(annotations_dir: Path, scene_id: str) -> dict:
    """Load YOLO-format GT labels for a scene.

    Returns: dict mapping tile_id -> list of {"bbox": [cx, cy, w, h]}
    """
    gt_dir = annotations_dir / scene_id / "labels"
    gt = {}
    if not gt_dir.exists():
        return gt
    for f in sorted(gt_dir.glob("*.txt")):
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
    return gt


def load_model(model_path: Path):
    """Load ONNX model, return (session, input_name)."""
    import onnxruntime as ort

    logger.info(f"Loading model: {model_path}")
    session = ort.InferenceSession(str(model_path))
    input_name = session.get_inputs()[0].name
    return session, input_name


def run_inference(session, input_name, tile_uint8):
    """Run ONNX inference on a single tile.

    Returns: list of {"bbox": [cx, cy, w, h] (normalized), "confidence": float}
    """
    tile_rgb = (
        np.stack([tile_uint8] * 3, axis=-1)
        if tile_uint8.ndim == 2
        else tile_uint8
    )
    img = Image.fromarray(tile_rgb)
    img_res = img.resize((MODEL_INPUT_SIZE, MODEL_INPUT_SIZE), Image.Resampling.LANCZOS)
    inp = np.array(img_res, dtype=np.float32) / 255.0
    inp = inp.transpose(2, 0, 1)[np.newaxis, ...]

    outputs = session.run(None, {input_name: inp})
    dets = outputs[0][0].T  # [8400, 5]

    preds = []
    for det in dets:
        cx, cy, w, h, conf = (
            float(det[0]),
            float(det[1]),
            float(det[2]),
            float(det[3]),
            float(det[4]),
        )
        if conf > CONF_THRESHOLD:
            preds.append({
                "bbox": [
                    cx / MODEL_INPUT_SIZE,
                    cy / MODEL_INPUT_SIZE,
                    w / MODEL_INPUT_SIZE,
                    h / MODEL_INPUT_SIZE,
                ],
                "confidence": conf,
            })

    # NMS
    preds.sort(key=lambda d: d["confidence"], reverse=True)
    kept = []
    for p in preds:
        if not any(compute_iou(p["bbox"], k["bbox"]) > IOU_MATCH for k in kept):
            kept.append(p)
    return kept


def find_false_positives(predictions, ground_truth):
    """Return predictions that have no GT match (IoU < threshold)."""
    fps = []
    for pred in predictions:
        is_match = any(
            compute_iou(pred["bbox"], g["bbox"]) >= IOU_MATCH for g in ground_truth
        )
        if not is_match:
            fps.append(pred)
    return fps


def generate_visualization(tile_uint8, tile_id, scene_id, gt_boxes, fp_boxes, output_dir):
    """Generate a visualization PNG for a tile with GT and FP boxes."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches

    fig, ax = plt.subplots(1, 1, figsize=(10, 10))
    ax.imshow(tile_uint8, cmap="gray", vmin=0, vmax=255)
    h_px, w_px = tile_uint8.shape[:2]

    # GT in GREEN
    for g in gt_boxes:
        cx, cy, bw, bh = g["bbox"]
        x1 = (cx - bw / 2) * w_px
        y1 = (cy - bh / 2) * h_px
        rect = patches.Rectangle(
            (x1, y1),
            bw * w_px,
            bh * h_px,
            linewidth=2,
            edgecolor="lime",
            facecolor="none",
        )
        ax.add_patch(rect)
        ax.plot(cx * w_px, cy * h_px, marker="o", color="lime", markersize=6)

    # FP in RED
    for fp in fp_boxes:
        cx, cy, bw, bh = fp["bbox"]
        x1 = (cx - bw / 2) * w_px
        y1 = (cy - bh / 2) * h_px
        rect = patches.Rectangle(
            (x1, y1),
            bw * w_px,
            bh * h_px,
            linewidth=2,
            edgecolor="red",
            facecolor="none",
        )
        ax.add_patch(rect)
        ax.plot(cx * w_px, cy * h_px, marker="x", color="red", markersize=8)
        ax.text(
            x1,
            y1 - 5,
            f"conf={fp['confidence']:.4f}",
            color="red",
            fontsize=8,
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.7),
        )

    ax.set_title(
        f"Scene: {scene_id} | Tile: {tile_id}\nGreen=GT (AIS)  Red=FP prediction",
        fontsize=12,
    )
    ax.axis("off")

    save_path = output_dir / f"fp_{scene_id}_{tile_id}.png"
    fig.savefig(save_path, dpi=150, bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)
    return save_path


def generate_html(
    all_fps, scene_ids, model_name, conf_threshold, output_dir
):
    """Generate the interactive HTML gallery for FP classification."""
    card_lines = []
    for i, (tid, vpath, n_fp, sid) in enumerate(all_fps):
        rel = vpath.name
        card_lines.append(
            f"""<div class="card" data-idx="{i}" data-tile="{tid}">
    <img src="{rel}" alt="FP {tid}" loading="lazy">
    <div class="tile-id">[{i+1}/{len(all_fps)}] {sid} — {tid} ({n_fp} FP(s))</div>
    <div class="buttons">
        <button class="btn btn-a" onclick="classify({i},'A')">🟢 A — Clearly a vessel</button>
        <button class="btn btn-b" onclick="classify({i},'B')">🔴 B — Not a vessel (noise)</button>
        <button class="btn btn-c" onclick="classify({i},'C')">🟡 C — Ambiguous</button>
    </div>
</div>"""
        )

    cards_joined = "\n".join(card_lines)
    total_fps = len(all_fps)

    HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>False Positive Visual Audit</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
           background: #0f172a; color: #e2e8f0; padding: 20px; }}
    h1 {{ text-align: center; margin-bottom: 8px; font-size: 1.5rem; }}
    .subtitle {{ text-align: center; color: #94a3b8; margin-bottom: 8px; }}
    .progress {{ text-align: center; margin-bottom: 20px; font-size: 1.1rem; color: #94a3b8; }}
    .progress span {{ font-weight: bold; color: #38bdf8; }}
    .card {{ background: #1e293b; border-radius: 12px; padding: 16px; margin-bottom: 24px;
            max-width: 900px; margin: 0 auto 24px auto;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3); }}
    .card img {{ width: 100%; border-radius: 8px; display: block; }}
    .card .tile-id {{ font-family: monospace; font-size: 0.85rem; color: #94a3b8; margin: 8px 0; }}
    .buttons {{ display: flex; gap: 10px; margin-top: 12px; flex-wrap: wrap; }}
    .btn {{ flex: 1; padding: 12px 16px; border: none; border-radius: 8px; font-size: 1rem;
           font-weight: 600; cursor: pointer; transition: all 0.2s; min-width: 120px; }}
    .btn-a {{ background: #22c55e; color: #052e16; }}
    .btn-a:hover {{ background: #16a34a; transform: translateY(-1px); }}
    .btn-a.selected {{ box-shadow: 0 0 0 3px #86efac, 0 0 0 5px #22c55e; }}
    .btn-b {{ background: #ef4444; color: #450a0a; }}
    .btn-b:hover {{ background: #dc2626; transform: translateY(-1px); }}
    .btn-b.selected {{ box-shadow: 0 0 0 3px #fca5a5, 0 0 0 5px #ef4444; }}
    .btn-c {{ background: #f59e0b; color: #451a03; }}
    .btn-c:hover {{ background: #d97706; transform: translateY(-1px); }}
    .btn-c.selected {{ box-shadow: 0 0 0 3px #fcd34d, 0 0 0 5px #f59e0b; }}
    .actions {{ text-align: center; margin: 20px 0; }}
    .btn-summary {{ background: #3b82f6; color: #fff; padding: 12px 32px; border: none;
                   border-radius: 8px; font-size: 1rem; font-weight: 600; cursor: pointer; }}
    .btn-summary:hover {{ background: #2563eb; }}
    .btn-export {{ background: #8b5cf6; color: #fff; padding: 12px 32px; border: none;
                  border-radius: 8px; font-size: 1rem; font-weight: 600; cursor: pointer; margin-left: 10px; }}
    .btn-export:hover {{ background: #7c3aed; }}
    .summary {{ background: #1e293b; border-radius: 12px; padding: 20px;
               max-width: 900px; margin: 20px auto; display: none; }}
    .summary table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
    .summary th, .summary td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #334155; }}
    .summary th {{ color: #94a3b8; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; }}
    .badge-a {{ background: #22c55e; color: #052e16; }}
    .badge-b {{ background: #ef4444; color: #450a0a; }}
    .badge-c {{ background: #f59e0b; color: #451a03; }}
</style>
</head>
<body>
<h1>🔍 False Positive Visual Audit</h1>
<p class="subtitle">Scenes: {', '.join(scene_ids[:3])}{'…' if len(scene_ids) > 3 else ''} &middot; Model: {model_name} &middot; conf&gt;{conf_threshold}</p>
<p class="progress">Progress: <span id="progress-count">0</span> / <span id="total-count">{total_fps}</span> classified</p>
<div id="gallery">
{cards_joined}
</div>
<div class="actions">
    <button class="btn-summary" onclick="showSummary()">📊 Show Summary</button>
    <button class="btn-export" onclick="exportResults()">💾 Export JSON</button>
</div>
<div class="summary" id="summary">
    <h2>📋 Audit Results</h2>
    <table>
        <tr><th>Category</th><th>Count</th><th>Percentage</th></tr>
        <tr><td><span class="badge badge-a">A — Clearly a vessel</span></td><td id="count-a">0</td><td id="pct-a">0%</td></tr>
        <tr><td><span class="badge badge-b">B — Not a vessel</span></td><td id="count-b">0</td><td id="pct-b">0%</td></tr>
        <tr><td><span class="badge badge-c">C — Ambiguous</span></td><td id="count-c">0</td><td id="pct-c">0%</td></tr>
    </table>
    <p id="interpretation" style="margin-top:16px; color:#94a3b8; line-height:1.5;"></p>
</div>
<script>
const results = {{}};
const TOTAL = {total_fps};

function classify(idx, cat) {{
    results[idx] = cat;
    const card = document.querySelector(`.card[data-idx="${{idx}}"]`);
    card.querySelectorAll('.btn').forEach(b => b.classList.remove('selected'));
    card.querySelector(`.btn-${{cat}}`).classList.add('selected');
    const done = Object.keys(results).length;
    document.getElementById('progress-count').textContent = done;
    if (done === TOTAL) {{
        alert('🎉 All ' + TOTAL + ' FPs classified! Click "Show Summary" to see the results.');
    }}
}}

function showSummary() {{
    const counts = {{A:0, B:0, C:0}};
    Object.values(results).forEach(c => counts[c]++);
    document.getElementById('count-a').textContent = counts.A;
    document.getElementById('count-b').textContent = counts.B;
    document.getElementById('count-c').textContent = counts.C;
    const total = Object.keys(results).length;
    document.getElementById('pct-a').textContent = total > 0 ? Math.round(counts.A/total*100) + '%' : '0%';
    document.getElementById('pct-b').textContent = total > 0 ? Math.round(counts.B/total*100) + '%' : '0%';
    document.getElementById('pct-c').textContent = total > 0 ? Math.round(counts.C/total*100) + '%' : '0%';

    let interp = '';
    if (total === 0) {{
        interp = 'No FPs classified yet. Use the buttons above each image to classify.';
    }} else if (counts.A + counts.C >= total * 0.3) {{
        interp = '⚠️ Significant proportion (' + Math.round((counts.A+counts.C)/total*100) + '%) of FPs may be real vessels. GT alignment issue likely.';
    }} else if (counts.A + counts.C >= total * 0.1) {{
        interp = '🔶 Some FPs (' + Math.round((counts.A+counts.C)/total*100) + '%) may be real vessels. Further investigation recommended.';
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
        model: '{model_name}',
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
</html>"""
    html_path = output_dir / "fp_audit.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(HTML)
    logger.info(f"HTML gallery: {html_path}")
    return html_path


def audit_all_scenes(
    tiles_dir: Path,
    annotations_dir: Path,
    model_path: Path,
    output_dir: Path,
    conf_threshold: float = CONF_THRESHOLD,
):
    """Run FP audit across all scenes with both tiles and annotations."""
    tiles_dir = Path(tiles_dir)
    annotations_dir = Path(annotations_dir)
    model_path = Path(model_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")

    # Find scenes with annotations
    annotated_scenes = []
    for scene_dir in sorted(tiles_dir.iterdir()):
        if not scene_dir.is_dir():
            continue
        sid = scene_dir.name
        gt = load_gt_labels(annotations_dir, sid)
        if gt:
            annotated_scenes.append((sid, gt))

    if not annotated_scenes:
        logger.warning("No scenes with both tiles and annotations found!")
        # Generate empty HTML
        generate_html([], [], model_path.name, conf_threshold, output_dir)
        return

    logger.info(f"Found {len(annotated_scenes)} scene(s) with annotations: {[s[0] for s in annotated_scenes]}")

    # Load model once
    session, input_name = load_model(model_path)

    all_fps = []
    total_tiles_processed = 0
    total_predictions = 0
    tiles_with_zero_preds = 0

    for scene_id, gt in annotated_scenes:
        logger.info(f"\n--- Scene: {scene_id} ({len(gt)} tiles, {sum(len(v) for v in gt.values())} boxes) ---")
        tile_dir = tiles_dir / scene_id / "D"

        for tile_id, gboxes in gt.items():
            tile_path = tile_dir / f"{tile_id}.npy"
            if not tile_path.exists():
                continue

            tile_uint8 = np.load(str(tile_path)).astype(np.uint8)
            preds = run_inference(session, input_name, tile_uint8)

            total_predictions += len(preds)

            if not preds:
                tiles_with_zero_preds += 1
                continue

            fps = find_false_positives(preds, gboxes)
            if not fps:
                continue

            viz_path = generate_visualization(
                tile_uint8, tile_id, scene_id, gboxes, fps, output_dir
            )
            all_fps.append((f"{scene_id}_{tile_id}", viz_path, len(fps), scene_id))

            total_tiles_processed += 1
            if total_tiles_processed % 50 == 0:
                logger.info(f"  {scene_id}: {total_tiles_processed} tiles processed, {len(all_fps)} FPs found")

    logger.info(f"\n{'='*50}")
    logger.info(f"FP AUDIT SUMMARY")
    logger.info(f"  Scenes audited: {len(annotated_scenes)}")
    logger.info(f"  Total predictions: {total_predictions}")
    logger.info(f"  Tiles with zero predictions: {tiles_with_zero_preds}")
    logger.info(f"  Tiles with FPs: {len(all_fps)}")
    logger.info(f"  Total FP detections: {sum(f[2] for f in all_fps)}")
    logger.info(f"{'='*50}")

    # Generate HTML
    scene_ids = list(set(s[0] for s in annotated_scenes))
    generate_html(all_fps, scene_ids, model_path.name, conf_threshold, output_dir)
    logger.info(f"Open in browser: file://{output_dir}/fp_audit.html")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="FP audit across all scenes")
    parser.add_argument("--tiles-dir", default="research/data/tiles", help="Tiles directory")
    parser.add_argument("--annotations-dir", default="research/data/annotations", help="Annotations directory")
    parser.add_argument("--model", default="shared/models/yolov8n_mrssd_int8.onnx", help="ONNX model path")
    parser.add_argument("--output", default="research/results/fp_audit", help="Output directory")
    parser.add_argument("--conf", type=float, default=CONF_THRESHOLD, help="Confidence threshold")
    args = parser.parse_args()

    audit_all_scenes(
        Path(args.tiles_dir),
        Path(args.annotations_dir),
        Path(args.model),
        Path(args.output),
        conf_threshold=args.conf,
    )


if __name__ == "__main__":
    main()
