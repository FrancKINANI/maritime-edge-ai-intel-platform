import json, sys
from pathlib import Path

import numpy as np
from PIL import Image

# === CONFIG ===
ONNX_MODEL_PATH = PROJECT_ROOT / "shared" / "models" / "yolov8n_mrssd_int8.onnx"
CONF_THRESHOLD = 0.001  # Very low to capture any prediction
FP_AUDIT_DIR = PROJECT_ROOT / "research" / "results" / "fp_audit"
IOU_MATCH = 0.5
MODEL_INPUT_SIZE = 640
# ==============

_BAR = "=" * 60
print(_BAR)
print("  CELL 13 — FALSE POSITIVE VISUAL AUDIT")
print(_BAR)

# --- Step 1: Load metadata ---
metadata_path = TILES_DIR / scene_id / pipeline / "metadata.json"
if not metadata_path.exists():
    raise FileNotFoundError(f"Metadata not found: {metadata_path}")
with open(metadata_path) as f:
    metadata = json.load(f)
print(f"Scene: {scene_id}")
print(f"Tiles available: {metadata.get('valid_tiles', '?')}")

# --- Step 2: Generate AIS annotations ---
from research.scripts.gfw_annotations import GFWClient, annotate_scene

ANNOTATIONS_DIR = PROJECT_ROOT / "research" / "data" / "annotations"
ANNOTATIONS_DIR.mkdir(parents=True, exist_ok=True)

print("\n--- Step 2: Generating AIS annotations via GFW ---")
client = GFWClient(GFW_API_TOKEN)
try:
    report = annotate_scene(metadata_path, client, str(ANNOTATIONS_DIR), pipeline=pipeline)
    print(f"  {report['total_annotations']} annotations on {report['annotated_tiles']} tiles")
    print(f"  AIS seeds: {report['ais_presence_seeds']}")
except Exception as e:
    print(f"  ⚠ GFW annotation failed: {e}")
    print("  Continuing with empty annotations — the model may still find false positives.")
    print("  Check your GFW_API_TOKEN and internet connection.")
    report = {
        "total_annotations": 0,
        "annotated_tiles": 0,
        "ais_presence_seeds": 0,
        "dark_vessel_candidates": 0,
        "class_counts": {"AIS_confirmed": 0, "visual_only": 0, "dark_vessel_candidate": 0},
    }

# --- Step 3: Load ONNX model ---
print("\n--- Step 3: Loading ONNX model ---")
if not ONNX_MODEL_PATH.exists():
    raise FileNotFoundError(f"Model not found: {ONNX_MODEL_PATH}")
import onnxruntime as ort  # noqa: E402

session = ort.InferenceSession(str(ONNX_MODEL_PATH))
input_name = session.get_inputs()[0].name
print(f"Model loaded: {ONNX_MODEL_PATH.name}")

# --- Step 4: Load GT labels ---
print("\n--- Step 4: Loading YOLO GT labels ---")
gt_dir = ANNOTATIONS_DIR / scene_id / "labels"
gt = {}
if gt_dir.exists():
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
print(f"Loaded GT: {len(gt)} tiles, {sum(len(v) for v in gt.values())} boxes")

# --- Step 5: Run inference ---
print("\n--- Step 5: Running inference ---")
tile_dir = TILES_DIR / scene_id / pipeline
tile_paths = [tile_dir / f"{tid}.npy" for tid in gt.keys()]
tile_paths = [p for p in tile_paths if p.exists()]
print(f"Tiles to process: {len(tile_paths)}")


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


all_fps = []
tiles_with_zero_preds = 0
total_preds = 0
FP_AUDIT_DIR.mkdir(parents=True, exist_ok=True)

for tile_path in tile_paths:
    tile_id = tile_path.stem
    tile_uint8 = np.load(str(tile_path)).astype(np.uint8)

    # Run inference
    tile_rgb = np.stack([tile_uint8] * 3, axis=-1) if tile_uint8.ndim == 2 else tile_uint8
    img = Image.fromarray(tile_rgb)
    img_res = img.resize((MODEL_INPUT_SIZE, MODEL_INPUT_SIZE), Image.Resampling.LANCZOS)
    inp = np.array(img_res, dtype=np.float32) / 255.0
    inp = inp.transpose(2, 0, 1)[np.newaxis, ...]
    outputs = session.run(None, {input_name: inp})

    # Parse detections
    dets = outputs[0][0].T  # [8400, 5]
    preds = []
    for det in dets:
        cx, cy, w, h, conf = (
            float(det[0]), float(det[1]), float(det[2]), float(det[3]), float(det[4])
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

    total_preds += len(preds)

    # NMS
    preds.sort(key=lambda d: d["confidence"], reverse=True)
    kept = []
    for p in preds:
        if not any(compute_iou(p["bbox"], k["bbox"]) > IOU_MATCH for k in kept):
            kept.append(p)
    preds = kept

    if not preds:
        tiles_with_zero_preds += 1
        continue

    # Find false positives (predictions with no GT match)
    tile_gt = gt.get(tile_id, [])
    fps = []
    for pred in preds:
        is_match = False
        for g in tile_gt:
            if compute_iou(pred["bbox"], g["bbox"]) >= IOU_MATCH:
                is_match = True
                break
        if not is_match:
            fps.append(pred)

    if not fps:
        continue

    # --- Generate visualization ---
    import matplotlib  # noqa: E402
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: E402
    import matplotlib.patches as patches  # noqa: E402

    fig, ax = plt.subplots(1, 1, figsize=(10, 10))
    ax.imshow(tile_uint8, cmap="gray", vmin=0, vmax=255)
    h_px, w_px = tile_uint8.shape[:2]

    # GT in GREEN
    for g in tile_gt:
        cx, cy, bw, bh = g["bbox"]
        x1 = (cx - bw / 2) * w_px
        y1 = (cy - bh / 2) * h_px
        rect = patches.Rectangle(
            (x1, y1), bw * w_px, bh * h_px,
            linewidth=2, edgecolor="lime", facecolor="none",
        )
        ax.add_patch(rect)
        ax.plot(cx * w_px, cy * h_px, marker="o", color="lime", markersize=6)

    # FP in RED
    for fp in fps:
        cx, cy, bw, bh = fp["bbox"]
        x1 = (cx - bw / 2) * w_px
        y1 = (cy - bh / 2) * h_px
        rect = patches.Rectangle(
            (x1, y1), bw * w_px, bh * h_px,
            linewidth=2, edgecolor="red", facecolor="none",
        )
        ax.add_patch(rect)
        ax.plot(cx * w_px, cy * h_px, marker="x", color="red", markersize=8)
        ax.text(
            x1, y1 - 5, f"conf={fp['confidence']:.4f}",
            color="red", fontsize=8, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.7),
        )

    ax.set_title(f"Tile: {tile_id}\nGreen=GT (AIS)  Red=FP prediction", fontsize=12)
    ax.axis("off")

    save_path = FP_AUDIT_DIR / f"fp_{tile_id}.png"
    fig.savefig(save_path, dpi=150, bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)
    all_fps.append((tile_id, save_path, len(fps)))

# --- Summary ---
print(f"\n=== FALSE POSITIVE SUMMARY ===")
print(f"Tiles with FPs: {len(all_fps)}")
print(f"Total FP detections: {sum(f[2] for f in all_fps)}")
print(f"Total predictions (all tiles): {total_preds}")
if tiles_with_zero_preds > 0:
    print(f"Tiles with ZERO predictions: {tiles_with_zero_preds} (try lower --conf)")

# --- Step 6: Generate HTML gallery ---
print("\n--- Step 6: Generating HTML gallery ---")

# Build card HTML for each FP visualization
card_html_lines = []
for i, (tid, vpath, n_fp) in enumerate(all_fps):
    rel = vpath.name
    card_html_lines.append(
        f"""<div class="card" data-idx="{i}" data-tile="{tid}">
    <img src="{rel}" alt="FP {tid}" loading="lazy">
    <div class="tile-id">[{i+1}/{len(all_fps)}] {tid} ({n_fp} FP(s))</div>
    <div class="buttons">
        <button class="btn btn-a" onclick="classify({i},'A')">🟢 A — Clearly a vessel</button>
        <button class="btn btn-b" onclick="classify({i},'B')">🔴 B — Not a vessel (noise)</button>
        <button class="btn btn-c" onclick="classify({i},'C')">🟡 C — Ambiguous</button>
    </div>
</div>"""
    )

cards_joined = "\n".join(card_html_lines)
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
<p class="subtitle">Scene: {scene_id} &middot; Model: {ONNX_MODEL_PATH.name} &middot; conf&gt;{CONF_THRESHOLD}</p>
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
        scene: '{scene_id}',
        model: '{ONNX_MODEL_PATH.name}',
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

html_path = FP_AUDIT_DIR / "fp_audit.html"
with open(html_path, "w") as f:
    f.write(HTML)

print(f"\n=== DONE ===")
print(f"HTML gallery: {html_path}")
print(f"Visualizations: {FP_AUDIT_DIR}")
print(f"Total FPs to classify: {len(all_fps)}")
print(f"Open in browser: file://{html_path.resolve()}")
