#!/usr/bin/env python3
"""
Annotation Server — Web-based interactive AIS annotation tool
=============================================================
Usage::

    # Start the server (default port 8765)
    uv run python research/scripts/annotation_server.py

    # Specify a different port
    uv run python research/scripts/annotation_server.py --port 8080

    # Point to the annotated-only dataset
    uv run python research/scripts/annotation_server.py \\
        --data research/data/cvat_annotated_only

Then open http://localhost:8765 in your browser.

Interactive controls (in the browser):

    [a]      Accept tile (all boxes validated)
    [d]      Delete selected box
    [e]      Mark selected box as "needs edit"
    [1/2/3]  Change class of selected box
    [n]      Next tile
    [p]      Previous tile
    [s]      Save progress
    [q]      Quit

Click on a box to select it. Click on empty area to deselect.
"""

import argparse
import json
import logging
import mimetypes
import sys
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

logger = logging.getLogger("annotation_server")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLASS_NAMES = {
    0: "vessel_AIS_confirmed",
    1: "vessel_visual_only",
    2: "vessel_dark_vessel_candidate",
}

CLASS_COLORS = {
    0: "#4CAF50",  # green
    1: "#FF9800",  # orange
    2: "#F44336",  # red
}

PROGRESS_FILE = "_validation_progress.json"

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def parse_yolo_label(txt_path: Path, img_w: int = 512, img_h: int = 512) -> list[dict[str, Any]]:
    """Parse a YOLO .txt file into annotation dicts with pixel coordinates."""
    boxes = []
    if not txt_path.exists():
        return boxes
    text = txt_path.read_text().strip()
    if not text:
        return boxes
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) < 5:
            continue
        cls_id = int(parts[0])
        cx = float(parts[1]) * img_w
        cy = float(parts[2]) * img_h
        w = float(parts[3]) * img_w
        h = float(parts[4]) * img_h
        boxes.append(
            {
                "class_id": cls_id,
                "class_name": CLASS_NAMES.get(cls_id, "unknown"),
                "x1": int(cx - w / 2),
                "y1": int(cy - h / 2),
                "x2": int(cx + w / 2),
                "y2": int(cy + h / 2),
                "status": "pending",
            }
        )
    return boxes


def load_progress(scene_dir: Path) -> dict[str, Any]:
    """Load validation progress from JSON."""
    prog_path = scene_dir / PROGRESS_FILE
    if prog_path.exists():
        return json.loads(prog_path.read_text())
    return {"completed_tiles": [], "decisions": {}}


def save_progress(scene_dir: Path, progress: dict[str, Any]) -> None:
    """Save validation progress to JSON."""
    prog_path = scene_dir / PROGRESS_FILE
    prog_path.write_text(json.dumps(progress, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(data_root: Path) -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(title="Maritime Annotation Server")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Serve HTML UI
    # ------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return _HTML_TEMPLATE

    # ------------------------------------------------------------------
    # API: List scenes
    # ------------------------------------------------------------------

    @app.get("/api/scenes")
    async def list_scenes():
        scenes = []
        for d in sorted(data_root.iterdir()):
            if not d.is_dir():
                continue
            images_dir = d / "images"
            if not images_dir.exists():
                continue
            png_count = len(list(images_dir.glob("*.png")))
            if png_count == 0:
                continue
            progress = load_progress(d)
            scenes.append(
                {
                    "id": d.name,
                    "name": d.name,
                    "tile_count": png_count,
                    "validated": len(progress.get("completed_tiles", [])),
                }
            )
        return {"scenes": scenes}

    # ------------------------------------------------------------------
    # API: List tiles for a scene
    # ------------------------------------------------------------------

    @app.get("/api/scenes/{scene_id}/tiles")
    async def list_tiles(scene_id: str):
        scene_dir = data_root / scene_id
        if not scene_dir.exists() or not (scene_dir / "images").exists():
            raise HTTPException(404, f"Scene {scene_id} not found")

        images_dir = scene_dir / "images"
        labels_dir = scene_dir / "labels"
        progress = load_progress(scene_dir)
        completed = set(progress.get("completed_tiles", []))
        decisions = progress.get("decisions", {})

        png_files = sorted(images_dir.glob("*.png"))
        tiles = []
        for png_path in png_files:
            tile_id = png_path.stem
            txt_path = labels_dir / f"{tile_id}.txt"
            boxes = parse_yolo_label(txt_path)

            # Apply saved decisions
            if tile_id in decisions:
                saved_boxes = decisions[tile_id].get("boxes", {})
                for b in boxes:
                    key = box_key(b)
                    if key in saved_boxes:
                        saved = saved_boxes[key]
                        b["status"] = saved.get("status", "pending")
                        b["class_id"] = saved.get("class_id", b["class_id"])
                        b["class_name"] = CLASS_NAMES.get(b["class_id"], "unknown")

            tiles.append(
                {
                    "id": tile_id,
                    "validated": tile_id in completed,
                    "boxes": boxes,
                }
            )

        total_validated = len(completed)
        return {
            "scene": scene_id,
            "total": len(tiles),
            "validated": total_validated,
            "tiles": tiles,
        }

    # ------------------------------------------------------------------
    # API: Serve tile image
    # ------------------------------------------------------------------

    @app.get("/api/scenes/{scene_id}/tiles/{tile_id}/image")
    async def get_tile_image(scene_id: str, tile_id: str):
        scene_dir = data_root / scene_id
        if not scene_dir.exists():
            raise HTTPException(404, f"Scene {scene_id} not found")

        # Try with .png, .jpg, etc
        images_dir = scene_dir / "images"
        for ext in [".png", ".jpg", ".jpeg", ".tiff"]:
            path = images_dir / f"{tile_id}{ext}"
            if path.exists():
                content = path.read_bytes()
                mime_type, _ = mimetypes.guess_type(str(path))
                return Response(content=content, media_type=mime_type or "image/png")

        raise HTTPException(404, f"Tile image {tile_id} not found")

    # ------------------------------------------------------------------
    # API: Save decision for a tile
    # ------------------------------------------------------------------

    class DecisionRequest(BaseModel):  # noqa: N801 — Pydantic model class name
        validated: bool
        boxes: list[dict[str, Any]]

    @app.post("/api/scenes/{scene_id}/tiles/{tile_id}/decision")
    async def save_decision(scene_id: str, tile_id: str, decision: DecisionRequest):
        scene_dir = data_root / scene_id
        if not scene_dir.exists():
            raise HTTPException(404, f"Scene {scene_id} not found")

        progress = load_progress(scene_dir)

        # Store box decisions
        box_decisions = {}
        for b in decision.boxes:
            key = box_key(b)
            box_decisions[key] = {
                "status": b.get("status", "pending"),
                "class_id": b.get("class_id", 0),
            }
            if b.get("edit"):
                box_decisions[key]["edit"] = b["edit"]

        progress["decisions"][tile_id] = {"boxes": box_decisions}

        # Track validated tiles
        if decision.validated and tile_id not in progress["completed_tiles"]:
            progress["completed_tiles"].append(tile_id)
        elif not decision.validated and tile_id in progress["completed_tiles"]:
            progress["completed_tiles"].remove(tile_id)

        save_progress(scene_dir, progress)

        return {
            "ok": True,
            "scene": scene_id,
            "tile": tile_id,
            "validated": decision.validated,
            "total_validated": len(progress["completed_tiles"]),
        }

    # ------------------------------------------------------------------
    # API: Get progress summary
    # ------------------------------------------------------------------

    @app.get("/api/scenes/{scene_id}/progress")
    async def get_progress(scene_id: str):
        scene_dir = data_root / scene_id
        if not scene_dir.exists():
            raise HTTPException(404, f"Scene {scene_id} not found")

        progress = load_progress(scene_dir)
        images_dir = scene_dir / "images"
        total = len(list(images_dir.glob("*.png")))

        return {
            "scene": scene_id,
            "total": total,
            "validated": len(progress.get("completed_tiles", [])),
            "pending": total - len(progress.get("completed_tiles", [])),
        }

    return app


def box_key(b: dict) -> str:
    return f"{b['x1']}_{b['y1']}_{b['x2']}_{b['y2']}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Annotation Server — Web-based AIS annotation validation tool",
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("research/data/cvat_annotated_only"),
        help="Path to annotated-only dataset (default: research/data/cvat_annotated_only)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Server port (default: 8765)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Bind address (default: 0.0.0.0)",
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

    data_root = args.data.resolve()
    if not data_root.exists():
        logger.error("Data directory not found: %s", data_root)
        sys.exit(1)

    # Verify scenes exist
    scenes = [d for d in sorted(data_root.iterdir()) if d.is_dir() and (d / "images").exists()]
    if not scenes:
        logger.error("No scenes with images found in %s", data_root)
        sys.exit(1)

    logger.info("Starting annotation server")
    logger.info("  Data:  %s", data_root)
    logger.info("  URL:   http://localhost:%d", args.port)
    logger.info("  Scenes: %d found", len(scenes))
    for s in scenes:
        img_count = len(list((s / "images").glob("*.png")))
        logger.info("    %s/  (%d tiles)", s.name, img_count)

    app = create_app(data_root)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


# ---------------------------------------------------------------------------
# HTML Template (minimal annotation validation UI)
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Maritime Annotation Server</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: #1a1a2e; color: #eee; padding: 20px; }
  h1 { color: #4CAF50; margin-bottom: 20px; }
  .container { max-width: 1400px; margin: 0 auto; }
  .scene-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
  .scene-card { background: #16213e; border-radius: 12px; padding: 20px; cursor: pointer; border: 2px solid transparent; transition: all 0.2s; }
  .scene-card:hover { border-color: #4CAF50; transform: translateY(-2px); }
  .scene-card h3 { color: #e94560; margin-bottom: 8px; }
  .scene-card .stats { color: #888; font-size: 14px; }
  .tile-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; margin-top: 20px; }
  .tile-card { background: #16213e; border-radius: 8px; overflow: hidden; position: relative; }
  .tile-card img { width: 100%; display: block; }
  .tile-card .info { padding: 8px 12px; font-size: 12px; color: #aaa; display: flex; justify-content: space-between; }
  .tile-card .badge { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 10px; margin: 1px; }
  .badge-validated { background: #4CAF50; color: #fff; }
  .badge-pending { background: #FF9800; color: #fff; }
  .btn { background: #e94560; color: #fff; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; }
  .btn:hover { opacity: 0.9; }
  .back { margin-bottom: 16px; display: inline-block; color: #4CAF50; cursor: pointer; }
  .back:hover { text-decoration: underline; }
  #progress-bar { height: 4px; background: #333; border-radius: 2px; margin: 12px 0; }
  #progress-fill { height: 100%; background: #4CAF50; border-radius: 2px; transition: width 0.3s; }
</style>
</head>
<body>
<div class="container">
  <h1>📡 Maritime Annotation Validator</h1>
  <div id="app"></div>
</div>
<script>
const API = '';
let currentScene = null;

async function loadScenes() {
  const r = await fetch(API + '/api/scenes');
  const data = await r.json();
  let html = '<div class="scene-grid">';
  data.scenes.forEach(s => {
    const pct = s.tile_count > 0 ? Math.round(s.validated / s.tile_count * 100) : 0;
    html += `<div class="scene-card" onclick="openScene('${s.id}')">
      <h3>${s.name}</h3>
      <div class="stats">${s.validated}/${s.tile_count} validated (${pct}%)</div>
      <div id="progress-bar"><div id="progress-fill" style="width:${pct}%"></div></div>
    </div>`;
  });
  html += '</div>';
  document.getElementById('app').innerHTML = html;
}

async function openScene(sceneId) {
  currentScene = sceneId;
  const r = await fetch(API + '/api/scenes/' + sceneId + '/tiles');
  const data = await r.json();
  let html = `<a class="back" onclick="loadScenes()">← Back to scenes</a>
    <h2>${data.scene} <span style="font-size:14px;color:#888;">(${data.validated}/${data.total} validated)</span></h2>
    <div id="progress-bar"><div id="progress-fill" style="width:${data.total > 0 ? (data.validated/data.total*100) : 0}%"></div></div>
    <div class="tile-grid">`;
  data.tiles.forEach(t => {
    html += `<div class="tile-card">
      <img src="${API}/api/scenes/${sceneId}/tiles/${t.id}/image" alt="${t.id}" loading="lazy">
      <div class="info">
        <span>${t.id}</span>
        <span class="badge ${t.validated ? 'badge-validated' : 'badge-pending'}">${t.validated ? '✅ Validated' : '⏳ Pending'}</span>
      </div>
      <div style="padding:4px 12px 8px">
        <span style="font-size:11px;color:#888;">${t.boxes.length} boxes</span>
      </div>
    </div>`;
  });
  html += '</div>';
  document.getElementById('app').innerHTML = html;
}

loadScenes();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
