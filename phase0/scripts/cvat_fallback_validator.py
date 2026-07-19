#!/usr/bin/env python3
"""
CVAT Fallback Validator — Interactive Annotation Validation Tool
================================================================
A lightweight alternative to CVAT for validating 3,321 AIS annotations
on Sentinel-1 Pipeline D tiles (512x512).

Usage::

    # Validate scene 1 (10 tiles — quick test)
    uv run python phase0/scripts/cvat_fallback_validator.py \\
        --scene phase0/data/cvat_annotated_only/S1D_20260711

    # Validate scene 2 (1534 tiles — full validation)
    uv run python phase0/scripts/cvat_fallback_validator.py \\
        --scene phase0/data/cvat_annotated_only/S1D_20260716

    # Resume interrupted validation
    uv run python phase0/scripts/cvat_fallback_validator.py \\
        --scene phase0/data/cvat_annotated_only/S1D_20260716 \\
        --resume

    # Export validated labels
    uv run python phase0/scripts/cvat_fallback_validator.py \\
        --scene phase0/data/cvat_annotated_only/S1D_20260716 \\
        --export-only

    # Generate static HTML overview (no GUI needed)
    uv run python phase0/scripts/cvat_fallback_validator.py \\
        --scene phase0/data/cvat_annotated_only/S1D_20260716 \\
        --generate-report phase0/data/results/cvat_overview.html

Interactive controls::

    [a]      Accept tile (all boxes validated)
    [d]      Delete selected box
    [e]      Mark selected box as "needs edit"
    [E]      Edit box coordinates (click 2 corners)
    [n]      Next tile (skip without validating)
    [p]      Previous tile
    [s]      Save progress
    [q]      Quit and save
    [1/2/3]  Change class of selected box:
             1 = vessel_AIS_confirmed
             2 = vessel_visual_only
             3 = vessel_dark_vessel_candidate
    [Tab]    Select next box
    [Up/Down] Navigate between boxes
"""

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("cvat_fallback")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLASS_NAMES = {
    0: "vessel_AIS_confirmed",
    1: "vessel_visual_only",
    2: "vessel_dark_vessel_candidate",
}

CLASS_IDS = {v: k for k, v in CLASS_NAMES.items()}

CLASS_COLORS = {
    0: "#4CAF50",   # AIS_confirmed — green
    1: "#FF9800",   # visual_only — orange
    2: "#F44336",   # dark_vessel — red
}

PROGRESS_FILE = "_validation_progress.json"
EXPORT_DIR = "labels_validated"


# ---------------------------------------------------------------------------
# Label helpers
# ---------------------------------------------------------------------------


def parse_yolo_label(txt_path: Path, img_w: int = 512, img_h: int = 512) -> List[Dict[str, Any]]:
    """Parse a YOLO .txt label file into a list of annotation dicts with pixel coordinates.

    Supports: cls cx cy w h (normalized).

    Returns empty list if file does not exist or is empty.
    """
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
        x1 = int(cx - w / 2)
        y1 = int(cy - h / 2)
        x2 = int(cx + w / 2)
        y2 = int(cy + h / 2)
        boxes.append({
            "class_id": cls_id,
            "class_name": CLASS_NAMES.get(cls_id, "unknown"),
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "cx": cx, "cy": cy, "w": w, "h": h,
            "status": "pending",
        })
    return boxes


def boxes_to_yolo(boxes: List[Dict[str, Any]], img_w: int = 512, img_h: int = 512) -> str:
    """Convert annotation dicts back to YOLO format string.

    Deleted boxes are excluded from output.
    """
    lines = []
    for b in boxes:
        if b["status"] == "deleted":
            continue
        cls_id = b["class_id"]
        cx = b["cx"] / img_w
        cy = b["cy"] / img_h
        w = b["w"] / img_w
        h = b["h"] / img_h
        lines.append(f"{cls_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Progress persistence
# ---------------------------------------------------------------------------


def load_progress(scene_dir: Path) -> Dict[str, Any]:
    """Load validation progress JSON from scene directory."""
    prog_path = scene_dir / PROGRESS_FILE
    if prog_path.exists():
        return json.loads(prog_path.read_text())
    return {"completed_tiles": [], "decisions": {}}


def save_progress(scene_dir: Path, progress: Dict[str, Any]) -> None:
    """Save validation progress to JSON file."""
    prog_path = scene_dir / PROGRESS_FILE
    prog_path.write_text(json.dumps(progress, indent=2, ensure_ascii=False))
    logger.info("Progress saved — %d tiles processed", len(progress["completed_tiles"]))


# ---------------------------------------------------------------------------
# Interactive validation (lazy matplotlib import)
# ---------------------------------------------------------------------------


class ValidationSession:
    """Matplotlib-based interactive annotation validation session.

    Imports matplotlib lazily so that non-GUI operations (export, report)
    never touch the GUI backend.
    """

    def __init__(self, scene_dir: Path):
        self.scene_dir = scene_dir
        self.images_dir = scene_dir / "images"
        self.labels_dir = scene_dir / "labels"
        self._setup_gui()

        self.png_files = sorted(self.images_dir.glob("*.png"))
        if not self.png_files:
            logger.error("No images found in %s", self.images_dir)
            sys.exit(1)

        self.progress = load_progress(scene_dir)
        self.total = len(self.png_files)
        self.tile_idx = 0
        self.selected_box = -1
        self.running = True
        self.current_boxes: List[Dict[str, Any]] = []
        self.current_img: Optional[np.ndarray] = None

        # Matplotlib figure
        self.fig, self.ax = plt.subplots(figsize=(10, 10))
        self.fig.canvas.mpl_connect("key_press_event", self.on_key)
        self.fig.canvas.mpl_connect("button_press_event", self.on_click)
        self.fig.canvas.mpl_connect("close_event", self.on_close)
        self.fig.canvas.manager.set_window_title(f"Validation — {scene_dir.name}")

        # Status bar
        self.status_text = self.fig.text(
            0.5, 0.01, "", ha="center", va="bottom",
            fontsize=9, family="monospace",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#333", edgecolor="none"),
            color="white",
        )

        logger.info("Loaded %d tiles for validation in %s", self.total, scene_dir.name)

    def _setup_gui(self):
        """Import matplotlib and set up interactive backend.

        Tries TkAgg first (most common), then Qt backends.
        Exits with instructions if no GUI backend is available.
        """
        import matplotlib

        for backend in ["TkAgg", "QtAgg", "Qt5Agg", "GTK3Agg"]:
            try:
                matplotlib.use(backend, force=True)
                break
            except Exception:
                continue
        else:
            # No GUI backend found
            print()
            print("=" * 60)
            print("  INTERACTIVE MODE UNAVAILABLE")
            print("=" * 60)
            print("  No interactive matplotlib backend found.")
            print()
            print("  Install Tkinter:  sudo apt install python3-tk")
            print("  Or try:           brew install python-tk")
            print()
            print("  Alternatives:")
            print("    --export-only        Export validated labels")
            print("    --generate-report    Generate HTML overview")
            print("=" * 60)
            sys.exit(1)

        global plt, patches, KeyEvent, MouseButton, MouseEvent
        import matplotlib.pyplot as plt
        import matplotlib.patches as patches
        from matplotlib.backend_bases import KeyEvent, MouseButton, MouseEvent

    def run(self):
        """Main validation loop: iterate over tiles."""
        while self.running and self.tile_idx < self.total:
            self._load_tile()

            # Skip already completed tiles
            png_stem = self.png_files[self.tile_idx].stem
            if png_stem in self.progress["completed_tiles"]:
                self.tile_idx += 1
                continue

            self._draw()
            plt.waitforbuttonpress()

            if self.running:
                self.tile_idx += 1

        if self.tile_idx >= self.total and self.running:
            logger.info("")
            logger.info("=" * 60)
            logger.info("  VALIDATION COMPLETE!")
            logger.info("=" * 60)
            logger.info("  Run with --export-only to export validated labels.")
            logger.info("=" * 60)

        self._save()
        plt.close(self.fig)

    def _load_tile(self):
        """Load current tile image and annotations from disk."""
        png_path = self.png_files[self.tile_idx]
        tile_name = png_path.stem

        # Load image
        img = plt.imread(str(png_path))
        if img.max() <= 1.0:
            img = (img * 255).astype(np.uint8)
        if len(img.shape) == 2:
            self.current_img = np.stack([img] * 3, axis=-1)
        else:
            self.current_img = img

        # Parse labels
        txt_path = self.labels_dir / f"{tile_name}.txt"
        self.current_boxes = parse_yolo_label(txt_path)

        # Restore decisions from previous session
        if tile_name in self.progress.get("decisions", {}):
            saved = self.progress["decisions"][tile_name].get("boxes", {})
            for b in self.current_boxes:
                bbox_key = self._box_key(b)
                if bbox_key in saved:
                    b["status"] = saved[bbox_key].get("status", "pending")
                    b["class_id"] = saved[bbox_key].get("class_id", b["class_id"])
                    b["class_name"] = CLASS_NAMES.get(b["class_id"], "unknown")
                    edit = saved[bbox_key].get("edit")
                    if edit:
                        b.update(edit)

        self.selected_box = -1

    @staticmethod
    def _box_key(b: dict) -> str:
        return f"{b['x1']}_{b['y1']}_{b['x2']}_{b['y2']}"

    def _draw(self):
        """Render current tile with annotations and HUD."""
        self.ax.clear()
        self.ax.imshow(self.current_img, cmap="gray")

        tile_name = self.png_files[self.tile_idx].stem
        completed = len(self.progress["completed_tiles"])
        active = sum(1 for b in self.current_boxes if b["status"] != "deleted")
        pending = sum(1 for b in self.current_boxes if b["status"] == "pending")

        self.ax.set_title(
            f"Tile {self.tile_idx + 1}/{self.total} — {tile_name[:40]}\n"
            f"Boxes: {active} active ({pending} pending) | "
            f"Validated: {completed}/{self.total} tiles",
            fontsize=10
        )

        # Draw boxes
        for i, b in enumerate(self.current_boxes):
            if b["status"] == "deleted":
                continue
            color = CLASS_COLORS.get(b["class_id"], "#FFFFFF")
            is_selected = (i == self.selected_box)
            lw = 3 if is_selected else 1.5
            rect = patches.Rectangle(
                (b["x1"], b["y1"]), b["x2"] - b["x1"], b["y2"] - b["y1"],
                linewidth=lw, edgecolor=color, facecolor="none",
                alpha=0.9,
            )
            self.ax.add_patch(rect)

            # Class label tag
            tag = b["class_name"][:10]
            if b["status"] == "edited":
                tag += " ✏️"
            elif b["status"] == "accepted":
                tag += " ✅"
            self.ax.text(
                b["x1"], b["y1"] - 4, tag,
                fontsize=7, color=color, va="bottom",
                bbox=dict(boxstyle="round,pad=0.1", facecolor="#222", alpha=0.7, edgecolor="none"),
            )

            # Center cross for selected box
            if is_selected:
                self.ax.plot(b["cx"], b["cy"], marker="+", color="yellow",
                             markersize=12, mew=2)

        self.ax.set_xlim(0, 512)
        self.ax.set_ylim(512, 0)
        self.ax.set_aspect("equal")

        # Status bar
        controls = (
            "[a]=Accept  [d]=Delete  [e]=✏️Mark  [E]=🖱️Edit  "
            "[1/2/3]=Class  [Tab↑↓]=Select  "
            "[n]=Next  [p]=Prev  [s]=💾Save  [q]=🚪Quit"
        )
        self.status_text.set_text(controls)
        self.fig.canvas.draw_idle()

    def _save(self):
        save_progress(self.scene_dir, self.progress)

    def _accept_tile(self):
        """Mark all non-deleted boxes as accepted."""
        tile_name = self.png_files[self.tile_idx].stem
        for b in self.current_boxes:
            if b["status"] != "deleted":
                b["status"] = "accepted"
        decisions = {}
        for b in self.current_boxes:
            decisions[self._box_key(b)] = {
                "status": b["status"],
                "class_id": b["class_id"],
            }
        self.progress["decisions"][tile_name] = {"boxes": decisions}
        self.progress["completed_tiles"].append(tile_name)
        logger.info("Tile %s accepted (%d boxes)", tile_name, len(self.current_boxes))

    def on_key(self, event):
        """Handle keyboard events for annotation actions."""
        key = event.key

        if key == "q":
            self.running = False
            plt.close(self.fig)

        elif key == "n":
            self.running = False

        elif key == "p":
            if self.tile_idx > 0:
                self.tile_idx -= 2  # -2 because run() will +1
                self.running = False

        elif key == "s":
            self._save()

        elif key == "a":
            self._accept_tile()
            self.running = False  # auto-advance to next tile

        elif key == "d" and self.selected_box >= 0:
            if self.selected_box < len(self.current_boxes):
                self.current_boxes[self.selected_box]["status"] = "deleted"
                logger.info("Box #%d deleted", self.selected_box)
            self._draw()

        elif key == "e" and self.selected_box >= 0:
            if self.selected_box < len(self.current_boxes) and \
                    self.current_boxes[self.selected_box]["status"] != "deleted":
                self.current_boxes[self.selected_box]["status"] = "edited"
                logger.info("Box #%d marked as 'needs edit'", self.selected_box)
            self._draw()

        elif key == "E" and self.selected_box >= 0:
            if self.selected_box < len(self.current_boxes) and \
                    self.current_boxes[self.selected_box]["status"] != "deleted":
                self._edit_box_interactive()

        elif key in ("1", "2", "3") and self.selected_box >= 0:
            if self.selected_box < len(self.current_boxes) and \
                    self.current_boxes[self.selected_box]["status"] != "deleted":
                new_cls = int(key) - 1
                self.current_boxes[self.selected_box]["class_id"] = new_cls
                self.current_boxes[self.selected_box]["class_name"] = CLASS_NAMES[new_cls]
                logger.info("Box #%d → %s", self.selected_box, CLASS_NAMES[new_cls])
            self._draw()

        elif key == "tab":
            active = [i for i, b in enumerate(self.current_boxes) if b["status"] != "deleted"]
            if active:
                current_pos = active.index(self.selected_box) if self.selected_box in active else -1
                self.selected_box = active[(current_pos + 1) % len(active)]
            self._draw()

        elif key == "up":
            active = [i for i, b in enumerate(self.current_boxes) if b["status"] != "deleted"]
            if active:
                current_pos = active.index(self.selected_box) if self.selected_box in active else -1
                self.selected_box = active[(current_pos - 1) % len(active)]
            self._draw()

        elif key == "down":
            active = [i for i, b in enumerate(self.current_boxes) if b["status"] != "deleted"]
            if active:
                current_pos = active.index(self.selected_box) if self.selected_box in active else -1
                self.selected_box = active[(current_pos + 1) % len(active)]
            self._draw()

    def on_click(self, event):
        """Handle mouse click — select nearest box."""
        if event.inaxes != self.ax:
            return
        x, y = event.xdata, event.ydata

        best_idx = -1
        best_dist = float("inf")
        for i, b in enumerate(self.current_boxes):
            if b["status"] == "deleted":
                continue
            dist = np.sqrt((x - b["cx"]) ** 2 + (y - b["cy"]) ** 2)
            if b["x1"] <= x <= b["x2"] and b["y1"] <= y <= b["y2"]:
                dist /= 3  # inside box = priority
            if dist < best_dist:
                best_dist = dist
                best_idx = i

        if best_idx >= 0 and best_dist < 50:
            self.selected_box = best_idx
        else:
            self.selected_box = -1
        self._draw()

    def _edit_box_interactive(self):
        """Let user click two corners to define new box coordinates.

        Uses matplotlib's event loop to capture two mouse clicks.
        Press [Esc] at any time to cancel.
        """
        if self.selected_box < 0:
            return
        box = self.current_boxes[self.selected_box]

        self.status_text.set_text(
            "🖱️  Click two opposite corners for the new box  |  [Esc]=cancel"
        )
        self.fig.canvas.draw_idle()

        corners = []

        def click_handler(event):
            if event.inaxes == self.ax and event.button is MouseButton.LEFT:
                corners.append((int(event.xdata), int(event.ydata)))
                self.ax.plot(event.xdata, event.ydata, "yo", markersize=6)
                self.fig.canvas.draw_idle()
                if len(corners) == 2:
                    self.fig.canvas.stop_event_loop()

        def cancel_handler(event):
            if event.key == "escape":
                corners.clear()
                corners.append(None)
                self.fig.canvas.stop_event_loop()

        cid1 = self.fig.canvas.mpl_connect("button_press_event", click_handler)
        cid2 = self.fig.canvas.mpl_connect("key_press_event", cancel_handler)

        self.fig.canvas.start_event_loop(timeout=30)
        self.fig.canvas.mpl_disconnect(cid1)
        self.fig.canvas.mpl_disconnect(cid2)

        if len(corners) < 2 or corners[0] is None:
            logger.info("Edit cancelled")
            self._draw()
            return

        x1n, y1n = min(corners[0][0], corners[1][0]), min(corners[0][1], corners[1][1])
        x2n, y2n = max(corners[0][0], corners[1][0]), max(corners[0][1], corners[1][1])
        h, w = self.current_img.shape[:2]
        x1n, y1n = max(0, x1n), max(0, y1n)
        x2n, y2n = min(w, x2n), min(h, y2n)

        if x2n - x1n < 4 or y2n - y1n < 4:
            logger.warning("Bounding box too small — cancelled")
        else:
            box["x1"], box["y1"] = x1n, y1n
            box["x2"], box["y2"] = x2n, y2n
            box["cx"] = (x1n + x2n) / 2
            box["cy"] = (y1n + y2n) / 2
            box["w"] = x2n - x1n
            box["h"] = y2n - y1n
            box["status"] = "edited"
            logger.info("Box #%d edited: (%d,%d)-(%d,%d)",
                        self.selected_box, x1n, y1n, x2n, y2n)

        self._draw()

    def on_close(self, event):
        """Handle window close button."""
        self.running = False


# ---------------------------------------------------------------------------
# Export validated labels
# ---------------------------------------------------------------------------


def export_validated(scene_dir: Path) -> None:
    """Export validated labels to YOLO format files.

    Only exports tiles marked as completed in progress.
    Each exported tile gets a .txt label file and a copied .png image.
    """
    progress = load_progress(scene_dir)
    images_dir = scene_dir / "images"
    labels_dir = scene_dir / "labels"
    export_dir = scene_dir / EXPORT_DIR
    export_labels = export_dir / "labels"
    export_images = export_dir / "images"
    export_labels.mkdir(parents=True, exist_ok=True)
    export_images.mkdir(parents=True, exist_ok=True)

    exported = 0
    skipped = 0
    completed = set(progress.get("completed_tiles", []))

    for png_path in sorted(images_dir.glob("*.png")):
        tile_name = png_path.stem
        if tile_name not in completed:
            skipped += 1
            continue

        boxes = parse_yolo_label(labels_dir / f"{tile_name}.txt")

        # Apply saved decisions
        if tile_name in progress.get("decisions", {}):
            saved = progress["decisions"][tile_name].get("boxes", {})
            for b in boxes:
                bbox_key = f"{b['x1']}_{b['y1']}_{b['x2']}_{b['y2']}"
                if bbox_key in saved:
                    b["status"] = saved[bbox_key].get("status", "pending")
                    b["class_id"] = saved[bbox_key].get("class_id", b["class_id"])
                    b["class_name"] = CLASS_NAMES.get(b["class_id"], "unknown")
                    edit = saved[bbox_key].get("edit")
                    if edit:
                        b.update(edit)

        (export_labels / f"{tile_name}.txt").write_text(boxes_to_yolo(boxes))
        shutil.copy2(png_path, export_images / png_path.name)
        exported += 1

    logger.info("Export complete: %d tiles exported, %d skipped (not validated)",
                exported, skipped)
    logger.info("  Labels: %s", export_labels)
    logger.info("  Images: %s", export_images)

    # Dataset config for YOLO training
    config = export_dir / "dataset.yaml"
    config.write_text(
        f"# YOLO Dataset — Maritime Phase 0 (validated)\n"
        f"# {exported} validated tiles out of {len(list(images_dir.glob('*.png')))}\n\n"
        f"path: {export_dir.absolute()}\n"
        f"train: images\n"
        f"val: images\n\n"
        f"nc: 3\n"
        f"names: ['vessel_AIS_confirmed', 'vessel_visual_only', 'vessel_dark_vessel_candidate']\n"
    )
    logger.info("  Config: %s", config)


# ---------------------------------------------------------------------------
# HTML report (batch mode, no GUI needed)
# ---------------------------------------------------------------------------


def generate_report(scene_dir: Path, output_path: Path) -> None:
    """Generate a static HTML overview of all annotations.

    Works in batch mode — no GUI required.
    Each tile is displayed with its bounding boxes and validation status.
    Clicking an image opens it in a new tab (lightbox-style).
    """
    progress = load_progress(scene_dir)
    completed = set(progress.get("completed_tiles", []))

    png_files = sorted((scene_dir / "images").glob("*.png"))
    total_tiles = len(png_files)
    total_boxes = 0
    accepted_count = 0
    edited_count = 0
    pending_count = 0
    deleted_count = 0
    tiles_validated = len(completed)

    # We need images accessible from the HTML. Use relative paths.
    # The HTML is output to an arbitrary location, so we copy images
    # alongside the report.
    report_dir = output_path.parent
    report_dir.mkdir(parents=True, exist_ok=True)
    images_report_dir = report_dir / "report_images"
    images_report_dir.mkdir(exist_ok=True)

    html_parts = [
        "<!DOCTYPE html>",
        '<html lang="en"><head><meta charset="UTF-8">',
        "<title>Validation Report — CVAT Fallback</title>",
        "<style>",
        "body{font-family:sans-serif;margin:20px;background:#1a1a1a;color:#eee}",
        "h1{color:#4CAF50}.stats{display:flex;gap:20px;margin:20px 0}",
        ".stat-card{background:#333;padding:15px;border-radius:8px;flex:1;text-align:center}",
        ".stat-card .num{font-size:2em;font-weight:bold;color:#4CAF50}",
        ".tile-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}",
        ".tile-card{background:#2a2a2a;border-radius:8px;overflow:hidden;position:relative}",
        ".tile-card img{width:100%;display:block}",
        ".tile-card .info{position:absolute;bottom:0;left:0;right:0;background:rgba(0,0,0,0.7);padding:6px 10px;font-size:12px}",
        ".badge{display:inline-block;padding:2px 6px;border-radius:4px;font-size:10px;margin:1px}",
        ".badge-AIS{background:#4CAF50;color:#000}",
        ".badge-visual{background:#FF9800;color:#000}",
        ".badge-dark{background:#F44336;color:#fff}",
        ".badge-pending{background:#666;color:#fff}",
        ".badge-edited{background:#FF9800;color:#000}",
        ".validated-yes{border:2px solid #4CAF50}",
        ".validated-no{border:2px solid #666}",
        "</style></head><body>",
        "<h1>Validation Report — Phase 0</h1>",
        f"<p>Scene: {scene_dir.name} | {total_tiles} tiles</p>",
    ]

    # Process each tile
    html_tiles = []
    for png_path in png_files:
        tile_name = png_path.stem
        txt_path = scene_dir / "labels" / f"{tile_name}.txt"
        boxes = parse_yolo_label(txt_path)

        is_validated = tile_name in completed
        if is_validated and tile_name in progress.get("decisions", {}):
            saved = progress["decisions"][tile_name].get("boxes", {})
            for b in boxes:
                bbox_key = f"{b['x1']}_{b['y1']}_{b['x2']}_{b['y2']}"
                if bbox_key in saved:
                    b["status"] = saved[bbox_key].get("status", "pending")
                    b["class_id"] = saved[bbox_key].get("class_id", b["class_id"])

        active = [b for b in boxes if b["status"] != "deleted"]
        n_accepted = sum(1 for b in active if b["status"] == "accepted")
        n_edited = sum(1 for b in active if b["status"] == "edited")
        n_pending = sum(1 for b in active if b["status"] == "pending")
        n_deleted = sum(1 for b in boxes if b["status"] == "deleted")

        total_boxes += len(boxes)
        accepted_count += n_accepted
        edited_count += n_edited
        pending_count += n_pending
        deleted_count += n_deleted

        # Copy image to report directory
        dest_img = images_report_dir / png_path.name
        shutil.copy2(png_path, dest_img)
        rel_img_path = f"report_images/{png_path.name}"

        # Badge HTML
        badges = []
        for b in active:
            cls_tag = "AIS" if b["class_id"] == 0 else ("visual" if b["class_id"] == 1 else "dark")
            badges.append(f'<span class="badge badge-{cls_tag}">{CLASS_NAMES[b["class_id"]][:10]}</span>')
        if n_pending > 0:
            badges.append(f'<span class="badge badge-pending">{n_pending} pending</span>')

        status_class = f"validated-{is_validated}"
        html_tiles.append(
            f'<div class="tile-card {status_class}">'
            f'<img src="{rel_img_path}" loading="lazy" alt="{tile_name}">'
            '<div class="info">'
            f'<b>{tile_name[:30]}...</b> {"✅" if is_validated else "⏳"}'
            f' {" ".join(badges) if badges else " <i>no boxes</i>"}'
            "</div></div>"
        )

    # Stats cards
    html_parts.extend([
        '<div class="stats">',
        f'<div class="stat-card"><div class="num">{tiles_validated}/{total_tiles}</div>Tiles validated</div>',
        f'<div class="stat-card"><div class="num">{total_boxes}</div>Total boxes</div>',
        f'<div class="stat-card"><div class="num">{accepted_count}</div>Accepted ✅</div>',
        f'<div class="stat-card"><div class="num">{edited_count}</div>Edited ✏️</div>',
        f'<div class="stat-card"><div class="num">{deleted_count}</div>Deleted 🗑️</div>',
        "</div>",
        '<div class="tile-grid">',
        *html_tiles,
        "</div>",
        "<script>",
        "document.querySelectorAll('.tile-card').forEach(c => {",
        "  c.style.cursor = 'pointer';",
        "  c.onclick = function() {",
        "    const img = this.querySelector('img');",
        "    window.open(img.src, '_blank', 'width=512,height=512');",
        "  }",
        "});",
        "</script></body></html>",
    ])

    output_path.write_text("\n".join(html_parts))
    logger.info("Report generated: %s", output_path)
    logger.info("  Tiles: %d (%d validated)", total_tiles, tiles_validated)
    logger.info("  Boxes: %d total, %d accepted, %d edited, %d deleted",
                total_boxes, accepted_count, edited_count, deleted_count)


# ---------------------------------------------------------------------------
# Scene listing helper
# ---------------------------------------------------------------------------


def list_available_scenes(parent: Path) -> None:
    """List available scene directories with tile counts."""
    logger.info("Available scenes:")
    for d in sorted(parent.glob("*/")):
        png_count = len(list(d.glob("images/*.png")))
        if png_count > 0:
            validated = 0
            prog = d / PROGRESS_FILE
            if prog.exists():
                validated = len(json.loads(prog.read_text()).get("completed_tiles", []))
            logger.info("  %s/  (%d tiles, %d validated)", d.name, png_count, validated)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="CVAT Fallback Validator — interactive annotation validation for AIS labels",
    )
    parser.add_argument(
        "--scene", type=Path, required=True,
        help="Path to scene directory (e.g. phase0/data/cvat_annotated_only/S1D_20260716)",
    )
    parser.add_argument(
    "--resume", action="store_true",
    help="Resume an interrupted validation session (auto-detected by default)",
    )
    parser.add_argument(
        "--export-only", action="store_true",
        help="Export validated labels without launching the interactive GUI",
    )
    parser.add_argument(
        "--generate-report", type=Path, default=None, metavar="OUTPUT.html",
        help="Generate a static HTML overview of all tiles (no GUI needed)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Verbose logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Validate scene directory
    if not args.scene.exists():
        logger.error("Scene directory not found: %s", args.scene)
        list_available_scenes(args.scene.parent)
        sys.exit(1)

    if not (args.scene / "images").exists():
        logger.error("No 'images/' directory inside %s", args.scene)
        sys.exit(1)

    images_dir = args.scene / "images"
    labels_dir = args.scene / "labels"
    png_count = len(list(images_dir.glob("*.png")))
    label_count = len(list(labels_dir.glob("*.txt")))
    logger.info("Scene: %s", args.scene.name)
    logger.info("  Images: %d  |  Labels: %d", png_count, label_count)

    # Route to appropriate action
    if args.generate_report:
        # Use Agg backend for batch mode — no GUI needed
        import matplotlib
        matplotlib.use("Agg")
        generate_report(args.scene, args.generate_report)
    elif args.export_only:
        export_validated(args.scene)
    else:
        if args.resume:
            logger.info("Resuming previous validation session...")
        session = ValidationSession(args.scene)
        session.run()


if __name__ == "__main__":
    main()
