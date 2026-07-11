# Detector Service

**Purpose**: FastAPI wrapper around quantized YOLOv8 ONNX (INT8) models for vessel detection in preprocessed SAR tiles.

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/detect` | POST | Detection on a `.npy` tile (base64 or file path). Returns a `DetectionEvent` |
| `/health` | GET | Service health and model loading status |

## Input Formats

- `tile_path`: path to a `.npy` file on disk
- `tile_b64`: base64 content of a `.npy` file (used by ground-dashboard Mode 1)
- `scene_id` / `tile_id`: optional metadata
- `preprocessing_pipeline`: pipeline used (A/B/C/D, for traceability)

## Models

Place ONNX INT8 model files in `shared/models/`:

| Model | File (constant) | Description |
|-------|-----------------|-------------|
| Detector | `DETECTOR_MODEL` (default: `yolov8n_int8.onnx`) | Vessel detection |
| Segmenter | `SEGMENTER_MODEL` (default: `yolov8n_seg_int8.onnx`) | Segmentation (not currently used) |

Exact filenames are defined in `shared/config/constants.py`. Models are loaded at startup (ONNX Runtime, CPU).

## Detection Pipeline

1. Load `.npy` tile
2. Preprocessing: convert to float32, stack to 3 channels if monochrome, resize to `MODEL_INPUT_SIZE` (640), normalize [0,1]
3. ONNX Runtime inference
4. Post-processing: confidence threshold (0.25), NMS (IoU 0.45), xywh → xyxy conversion
5. Priority level calculation (LOW → CRITICAL based on vessel count)
6. Returns a `DetectionEvent`

## Local Execution

```bash
uvicorn services.detector.main:app --host 0.0.0.0 --port 8001
```

## Example Call

```bash
curl -X POST http://localhost:8001/detect \
  -H "Content-Type: application/json" \
  -d '{"tile_path":"/data/tiles/scene_tile0001.npy", "preprocessing_pipeline":"D"}'
```

## Notes

- The result follows the `DetectionEvent` schema (see `shared/schemas/events.py`).
- Priority level is heuristic: CRITICAL ≥ 10 vessels, HIGH ≥ 5, MEDIUM ≥ 2, LOW otherwise.
