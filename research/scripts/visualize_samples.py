#!/usr/bin/env python3
"""Generate visual samples of SAR tiles to verify preprocessing quality."""

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

# Paths (one level up from scripts/ to research/)
DATA_DIR = Path(__file__).parent.parent / "data"
TILES_ROOT = DATA_DIR / "tiles"
ANNOTATIONS_ROOT = DATA_DIR / "annotations"
OUTPUT_DIR = DATA_DIR / "samples"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SCENES = [
    "S1D_IW_GRDH_1SDV_20260711T061903_20260711T061928_003622_00673D_224C",
    "S1D_IW_GRDH_1SDV_20260716T190458_20260716T190523_003703_006A03_9C83",
]


def load_tile_metadata(scene_id: str) -> dict:
    path = TILES_ROOT / scene_id / "D" / "metadata.json"
    with open(path) as f:
        return json.load(f)


def load_annotation_report(scene_id: str) -> dict | None:
    path = ANNOTATIONS_ROOT / scene_id / "annotation_report.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def get_sample_tiles(meta: dict, n: int = 9) -> list[dict]:
    """Get n sample tiles: first tiles + some annotated ones if available."""
    tiles = meta["tiles"]
    samples = tiles[:n]  # First n tiles
    return samples


def create_annotated_png(
    npy_path: str, output_path: Path, tile_info: dict, annotations: list | None = None
) -> None:
    """Create a PNG with optional annotation overlay."""
    arr = np.load(npy_path)
    img = Image.fromarray(arr, mode="L")
    img = img.convert("RGB")  # Convert to RGB for drawing colored boxes

    if annotations:
        draw = ImageDraw.Draw(img)
        for ann in annotations:
            bbox = ann.get("bbox_yolo", [])
            if len(bbox) == 4:
                x_center, y_center, w, h = bbox
                tile_size = 512
                x1 = int((x_center - w / 2) * tile_size)
                y1 = int((y_center - h / 2) * tile_size)
                x2 = int((x_center + w / 2) * tile_size)
                y2 = int((y_center + h / 2) * tile_size)
                # Different colors per label
                label = ann.get("label", "unknown")
                color = {
                    "AIS_confirmed": (0, 255, 0),
                    "visual_only": (255, 255, 0),
                    "dark_vessel_candidate": (255, 0, 0),
                }.get(label, (255, 255, 255))
                draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
                draw.text((x1 + 2, y1 + 2), label, fill=color)

    img.save(str(output_path), format="PNG", optimize=True)


def generate_html(scenes_data: list[dict]) -> str:
    """Generate a self-contained HTML page."""
    html = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Échantillons SAR — Pipeline D</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'Inter', -apple-system, sans-serif;
    background: #0a0e17;
    color: #e2e8f0;
    padding: 2rem;
  }
  .header {
    margin-bottom: 2rem;
    padding-bottom: 1.5rem;
    border-bottom: 1px solid #1e293b;
  }
  .header h1 {
    font-size: 1.75rem;
    font-weight: 700;
    background: linear-gradient(135deg, #60a5fa, #a78bfa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 0.5rem;
  }
  .header p { color: #94a3b8; font-size: 0.9rem; }
  .scene-section {
    background: #111827;
    border: 1px solid #1e293b;
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 2rem;
  }
  .scene-title {
    font-size: 1.1rem;
    font-weight: 600;
    color: #f1f5f9;
    margin-bottom: 0.5rem;
  }
  .scene-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    margin-bottom: 1.25rem;
    font-size: 0.85rem;
  }
  .scene-meta .badge {
    background: #1e293b;
    padding: 0.25rem 0.75rem;
    border-radius: 6px;
    color: #94a3b8;
  }
  .scene-meta .badge strong { color: #e2e8f0; }
  .tile-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 1rem;
  }
  .tile-card {
    background: #1a2332;
    border: 1px solid #273548;
    border-radius: 8px;
    overflow: hidden;
    transition: transform 0.15s, box-shadow 0.15s;
    cursor: pointer;
  }
  .tile-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0,0,0,0.4);
  }
  .tile-card img {
    width: 100%;
    display: block;
    image-rendering: auto;
  }
  .tile-card .tile-info {
    padding: 0.5rem;
    font-size: 0.7rem;
    color: #94a3b8;
    line-height: 1.4;
  }
  .tile-card .tile-info .tile-id {
    color: #e2e8f0;
    font-weight: 500;
    word-break: break-all;
  }
  .tile-card .annotation-badge {
    display: inline-block;
    background: #166534;
    color: #86efac;
    font-size: 0.65rem;
    padding: 0.15rem 0.4rem;
    border-radius: 4px;
    margin-top: 0.25rem;
  }
  .tile-card .no-annotation {
    display: inline-block;
    color: #64748b;
    font-size: 0.65rem;
  }
  .lightbox {
    display: none;
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.85);
    z-index: 1000;
    justify-content: center;
    align-items: center;
  }
  .lightbox.active { display: flex; }
  .lightbox img {
    max-width: 90vw;
    max-height: 85vh;
    border-radius: 8px;
    border: 2px solid #334155;
  }
  .lightbox .close {
    position: absolute;
    top: 1rem; right: 1.5rem;
    color: #94a3b8;
    font-size: 2rem;
    cursor: pointer;
    transition: color 0.15s;
  }
  .lightbox .close:hover { color: #f1f5f9; }
  .stats-row {
    display: flex;
    gap: 1.5rem;
    flex-wrap: wrap;
    margin-bottom: 1.5rem;
  }
  .stat-card {
    background: #1a2332;
    border: 1px solid #273548;
    border-radius: 10px;
    padding: 1rem 1.5rem;
    flex: 1;
    min-width: 140px;
  }
  .stat-card .stat-value {
    font-size: 1.5rem;
    font-weight: 700;
    color: #60a5fa;
  }
  .stat-card .stat-label {
    font-size: 0.8rem;
    color: #64748b;
    margin-top: 0.25rem;
  }
  @media (max-width: 640px) {
    body { padding: 1rem; }
    .tile-grid { grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); }
  }
</style>
</head>
<body>

<div class="header">
  <h1>🛰️ Échantillons SAR — Pipeline D</h1>
  <p>Tuiles Sentinel-1 GRD IW · Prétraitées (σ⁰ + Lee 5×5 + Histogram Equalization) · 512×512 px</p>
</div>

<div class="stats-row">
  <div class="stat-card">
    <div class="stat-value">2</div>
    <div class="stat-label">Scènes S1D</div>
  </div>
  <div class="stat-card">
    <div class="stat-value">12,860</div>
    <div class="stat-label">Tuiles .npy</div>
  </div>
  <div class="stat-card">
    <div class="stat-value">12,860</div>
    <div class="stat-label">Images PNG</div>
  </div>
  <div class="stat-card">
    <div class="stat-value">3,321</div>
    <div class="stat-label">Annotations AIS</div>
  </div>
</div>
"""
    for sd in scenes_data:
        html += f"""
<div class="scene-section">
  <div class="scene-title">📡 {sd["scene_id"][:50]}…</div>
  <div class="scene-meta">
    <span class="badge"><strong>Tuiles:</strong> {sd["n_tiles"]:,}</span>
    <span class="badge"><strong>Annotations:</strong> {sd["n_annotations"]:,}</span>
    <span class="badge"><strong>Tuiles annotées:</strong> {sd["n_annotated_tiles"]}</span>
    <span class="badge"><strong>AIS seeds:</strong> {sd["ais_seeds"]}</span>
    <span class="badge"><strong>BBox:</strong> {sd["bbox"]}</span>
  </div>
  <div class="tile-grid">
"""
        for tile in sd["samples"]:
            img_src = tile["img_rel"]
            has_ann = tile["n_annotations"] > 0
            ann_label = f"{tile['n_annotations']} annotation(s)" if has_ann else "Aucune"
            ann_class = "annotation-badge" if has_ann else "no-annotation"
            lon_min, lat_min, lon_max, lat_max = tile["geo_bbox"]
            html += f"""
    <div class="tile-card" onclick="openLightbox('{img_src}')">
      <img src="{img_src}" alt="{tile["tile_id"][:60]}…" loading="lazy">
      <div class="tile-info">
        <div class="tile-id">{tile["tile_id"][:50]}…</div>
        <div>📌 {lat_min:.3f}°N, {lon_min:.3f}°E</div>
        <span class="{ann_class}">{ann_label}</span>
      </div>
    </div>
"""
        html += """
  </div>
</div>
"""
    html += """
<div class="lightbox" id="lightbox" onclick="this.classList.remove('active')">
  <span class="close">&times;</span>
  <img id="lightbox-img" src="" alt="Zoom">
</div>

<script>
function openLightbox(src) {
  document.getElementById('lightbox-img').src = src;
  document.getElementById('lightbox').classList.add('active');
}
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    document.getElementById('lightbox').classList.remove('active');
  }
});
</script>

</body>
</html>"""
    return html


def main():
    scenes_data = []
    samples_dir = OUTPUT_DIR / "images"
    samples_dir.mkdir(parents=True, exist_ok=True)

    for scene_id in SCENES:
        print(f"Processing {scene_id[:50]}...")
        meta = load_tile_metadata(scene_id)
        report = load_annotation_report(scene_id)

        # Build lookup of tile_id → annotations
        ann_lookup = {}
        if report:
            # Load the YOLO annotations from the annotation files
            ann_dir = ANNOTATIONS_ROOT / scene_id / "labels"
            for ann_file in ann_dir.glob("*.txt"):
                tile_id = ann_file.stem
                annotations = []
                with open(ann_file) as f:
                    for line in f:
                        parts = line.strip().split()
                        if len(parts) == 5:
                            cls_id, xc, yc, w, h = parts
                            label_map = {
                                "0": "AIS_confirmed",
                                "1": "visual_only",
                                "2": "dark_vessel_candidate",
                            }
                            annotations.append(
                                {
                                    "label": label_map.get(cls_id, "unknown"),
                                    "bbox_yolo": [float(xc), float(yc), float(w), float(h)],
                                }
                            )
                if annotations:
                    ann_lookup[tile_id] = annotations

        tiles = meta["tiles"]

        # Select sample tiles: first few + some annotated ones
        sample_tiles = []
        seen = set()
        for t in tiles:
            tid = t["tile_id"]
            if tid not in seen:
                seen.add(tid)
                sample_tiles.append(t)
            if len(sample_tiles) >= 12:
                break

        # If we have annotations, also include some annotated tiles not in first 12
        if ann_lookup:
            for t in tiles:
                tid = t["tile_id"]
                if tid in ann_lookup and tid not in seen:
                    seen.add(tid)
                    sample_tiles.append(t)
                if len(sample_tiles) >= 24:
                    break

        scene_samples = []
        for tile in sample_tiles[:24]:
            tid = tile["tile_id"]
            # Construct npy path directly from scene/tile structure
            # (avoids issues with stored npy_path containing "research/" prefix)
            npy_path = str((TILES_ROOT / scene_id / "D" / f"{tid}.npy").resolve())
            img_name = f"{tid}.png"
            img_path = samples_dir / img_name

            annotations = ann_lookup.get(tid, [])
            create_annotated_png(npy_path, img_path, tile, annotations if annotations else None)

            scene_samples.append(
                {
                    "tile_id": tid,
                    "img_rel": f"images/{img_name}",
                    "n_annotations": len(annotations),
                    "geo_bbox": tile["geo_bbox"],
                }
            )

        scenes_data.append(
            {
                "scene_id": scene_id,
                "n_tiles": len(tiles),
                "n_annotations": sum(len(a) for a in ann_lookup.values()),
                "n_annotated_tiles": len(ann_lookup),
                "ais_seeds": report.get("ais_presence_seeds", 0) if report else 0,
                "bbox": report.get("traceability", {}).get("target_cell_bbox", "N/A")
                if report
                else "N/A",
                "samples": scene_samples,
            }
        )

        print(f"  → {len(scene_samples)} samples generated")

    html = generate_html(scenes_data)
    html_path = OUTPUT_DIR / "index.html"
    with open(html_path, "w") as f:
        f.write(html)

    print(f"\n✅ Page générée: {html_path}")
    print(f"📂 Ouvrir avec: file://{html_path.absolute()}")


if __name__ == "__main__":
    main()
