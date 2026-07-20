# Phase Post-0 — Fine-Tune YOLOv8n on Sentinel-1

> Direct follow-up to Phase 0. The diagnosis is complete: **zero-shot domain transfer failed (mAP@0.5 = 0.0)**.
> The model must be **fine-tuned** on real AIS annotations.

## Folder structure

```
phase_post0/
├── build_finetune_dataset.py   ← NEW: Build YOLO dataset from annotations (scene-level split)
├── colab_finetune_yolo.ipynb   ← Colab Notebook (symlink)
├── dataset_summary.json        ← Dataset metadata (symlink)
├── phase0_closure.md           ← Phase 0 final report (symlink)
├── maritime_dataset.zip        ← Old 80/10/10 random split ZIP (symlink, ~311 MB)
├── regenerate_zip.sh           ← Script to regenerate old ZIP
├── models/                     ← MRSSD-pretrained best.pt checkpoints
│   ├── yolov8n_mrssd_v1_6mb.pt          (6 MB, INT8, 20260612)
│   ├── yolov8n_mrssd_v1_6mb_2.pt        (6 MB, INT8, 20260613)
│   ├── yolov8n_mrssd_v1_6mb_3.pt        (6 MB, INT8, 20260614)
│   ├── yolov8n_mrssd_v1_18mb_fp32.pt    (18 MB, FP32, 20260610)
│   ├── yolov8n_mrssd_v1_18mb_fp32_2.pt  (18 MB, FP32, 20260611)
│   ├── yolov8n_seg_ssdd_v1_6mb.pt       (6 MB, segmentation)
│   └── yolov8n_seg_ssdd_v2_6.5mb.pt     (6.5 MB, segmentation)
└── README.md
```

## Workflow

### 1. Download more scenes (you're doing this)

Open `phase0/notebooks/colab_traceability_check_v2.ipynb` in Colab and download
3–5 additional Sentinel-1 scenes with AIS annotations.

### 2. Build the fine-tuning dataset

Once you have 5+ scenes in `phase0/data/annotations/`, run:

```bash
# Discover scenes and build YOLO dataset (train/val/test split by scene)
uv run python phase_post0/build_finetune_dataset.py --zip

# Dry-run to see which scenes are available
uv run python phase_post0/build_finetune_dataset.py --dry-run

# Explicit split plan (order matches scene discovery order)
uv run python phase_post0/build_finetune_dataset.py \
    --scenes S1D_20260711 S1D_20260716 \
    --split train test

# Custom output location
uv run python phase_post0/build_finetune_dataset.py \
    --force --zip \
    --output phase_post0/dataset_5scenes
```

The script:
- Scans `phase0/data/annotations/` for all scene directories
- Maps YOLO `.txt` labels to `.png` images
- Applies quality filters (NoData >30%, bbox bounds, duplicate removal)
- Splits by **scene** (not tile) to avoid data leakage
- Exports YOLO structure + `data.yaml` + with `--zip` creates a ZIP

> **⚠️ Important**: With < 3 scenes, the split will be degenerate
> (e.g. 10 train / 0 val / 1531 test). Wait until 5+ scenes are available
> before fine-tuning.

### 3. Upload to Google Drive

```
dataset_finetune.zip  →  Google Drive
models/yolov8n_mrssd_v1_6mb.pt  →  Google Drive  (if using MRSSD weights)
```

### 4. Open the notebook in Colab

```python
# 1. Go to https://colab.research.google.com
# 2. File → Upload Notebook → pick colab_finetune_yolo.ipynb
# 3. Update ZIP_PATH in cell 2 if needed
# 4. (Optional) Set USE_MRSSD = True and update MRSSD_PATH
# 5. Runtime → Change runtime type → T4 GPU
# 6. Run all cells (~2-4 hours)
```

### 5. Retrieve the model

After fine-tuning, the notebook saves models to Google Drive:

- `yolov8n_maritime_v1.pt` (PyTorch)
- `yolov8n_maritime_v1.onnx` (ONNX FP32)
- `yolov8n_maritime_v1_int8.onnx` (ONNX INT8)

Copy them to `shared/models/` in this project.

### 6. Validation

```bash
uv run python phase0/scripts/benchmark_pipeline.py \
  --metadata phase0/data/tiles/<scene_id>/D/metadata.json \
  --ground-truth phase0/data/annotations/<scene_id>/labels/ \
  --model shared/models/yolov8n_maritime_v1.onnx
```

## Script comparison

| Script | Purpose | Split method | Quality filters | ZIP? |
|--------|---------|-------------|----------------|------|
| `phase0/scripts/export_colab_dataset.py` | Old 80/10/10 random split | Per tile (data leakage) | None | ✅ |
| `phase_post0/build_finetune_dataset.py` | NEW scene-level split | Per scene (no leakage) | NoData, bbox, duplicates | `--zip` flag |

Use `build_finetune_dataset.py` for all **new** datasets. The old script exists for
backwards compatibility only.

## Key Phase 0 Decisions

- ✅ **CVAT skipped** — AIS labels used directly as Ground Truth
- ✅ **Pipeline D** recommended for fine-tuning (σ⁰+Lee+Log+HistEq)
- ✅ **Split by scene** — no data leakage between train/val/test
- ✅ **MRSSD-pretrained weights** available in `models/`

## Expected Outcome

| mAP@0.5 | Verdict | Action |
|---------|---------|--------|
| > 0.70 | **GO** | Proceed to Phase 1 microservice deployment |
| 0.50–0.70 | **MARGINAL** | More data or epochs needed |
| < 0.50 | **STOP** | Strategic revision required |

---

*Generated July 19, 2026 — Maritime Edge AI Platform*
