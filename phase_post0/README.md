# Phase Post-0 — Fine-Tune YOLOv8n on Sentinel-1

> Direct follow-up to Phase 0. The diagnosis is complete: **zero-shot domain transfer failed (mAP@0.5 = 0.0)**.
> The model must be **fine-tuned** on the 3,321 real AIS annotations.

## Folder contents

| File | Description |
|------|-------------|
| `colab_finetune_yolo.ipynb` | **Colab Notebook** — YOLOv8n fine-tuning, evaluation, ONNX export |
| `dataset_summary.json` | Dataset metadata (1,544 images, 3,321 boxes) |
| `phase0_closure.md` | Phase 0 final report — all analyses |
| `regenerate_zip.sh` | Script to regenerate the ZIP (requires scripts in `phase0/scripts/`) |

## Workflow

### 1. Regenerate the ZIP (optional)

The ZIP already exists at `phase0/data/colab_export/maritime_dataset.zip` (311 MB).
To regenerate:

```bash
cd ..
uv run python phase0/scripts/export_colab_dataset.py
```

### 2. Upload to Google Drive

```
maritime_dataset.zip  (311 MB)  →  Google Drive
```

### 3. Open the notebook in Colab

```python
# 1. Go to https://colab.research.google.com
# 2. File → Upload Notebook → pick colab_finetune_yolo.ipynb
# 3. Update ZIP_PATH in cell 2 if needed
# 4. Runtime → Change runtime type → T4 GPU
# 5. Run all cells (~2-4 hours)
```

### 4. Retrieve the model

After fine-tuning, the notebook saves models to Google Drive:

- `yolov8n_maritime_v1.pt` (PyTorch)
- `yolov8n_maritime_v1.onnx` (ONNX FP32)
- `yolov8n_maritime_v1_int8.onnx` (ONNX INT8)

Copy them to `shared/models/` in this project.

### 5. Validation

```bash
cd ..
# Example using scene 2 (16/07/2026) — 1,534 annotated tiles
uv run python phase0/scripts/benchmark_pipeline.py \
  --metadata phase0/data/tiles/S1D_..._9C83/D/metadata.json \
  --ground-truth phase0/data/annotations/S1D_..._9C83/labels/ \
  --model shared/models/yolov8n_maritime_v1.onnx
#                                    ^^^^^^^^^^^^^^^^^^^^^^^^
#                                    Replace with your freshly fine-tuned model
```

## Key Phase 0 Decisions

- ✅ **CVAT skipped** — AIS labels used directly as Ground Truth
  (reliable GPS positions: 0% on land verified, <10m accuracy)
- ✅ **Pipeline D** recommended for fine-tuning (σ⁰+Lee+Log+HistEq)
- ✅ **3,321 boxes** all class `vessel_AIS_confirmed` (no dark vessels detected)
- ✅ **Dataset split**: 80/10/10 (train=1,235, val=154, test=155)

## Expected Outcome

If fine-tuning works:
- mAP@0.5 > 0.70 → **GO Phase 1** — microservice deployment
- mAP@0.5 0.50–0.70 → **MARGINAL** — more data or epochs
- mAP@0.5 < 0.50 → **STOP** — strategic revision needed

---

*Generated July 19, 2026 — Maritime Edge AI Platform*
