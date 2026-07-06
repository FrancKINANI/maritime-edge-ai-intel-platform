# services/detector/main.py
"""Detector FastAPI Service.

Exposes endpoints for running model inference on preprocessed .npy tiles
to detect vessels and output raw detection events.
"""

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Optional, List, Tuple
import time
import base64
import io
import uuid
import logging
import numpy as np
import onnxruntime as ort
from shared.schemas.events import DetectionEvent, BoundingBox
from shared.config import constants
from datetime import datetime

logger = logging.getLogger(__name__)


class DetectRequest(BaseModel):
    tile_path: Optional[str] = None
    tile_b64: Optional[str] = None
    scene_id: Optional[str] = "unknown"
    tile_id: Optional[str] = None
    preprocessing_pipeline: str = "D"


app = FastAPI(
    title="Maritime Edge AI Intel Platform - Detector",
    description="Microservice wrapping the Phase I YOLOv8 ONNX model for ship detection.",
    version="1.0.0",
)


# Load ONNX models once at startup
DETECTOR_SESSION: Optional[ort.InferenceSession] = None
SEGMENTER_SESSION: Optional[ort.InferenceSession] = None


def load_models():
    global DETECTOR_SESSION, SEGMENTER_SESSION
    model_dir = "shared/models"
    detector_path = f"{model_dir}/{constants.DETECTOR_MODEL}"
    segmenter_path = f"{model_dir}/{constants.SEGMENTER_MODEL}"
    try:
        DETECTOR_SESSION = ort.InferenceSession(detector_path, providers=["CPUExecutionProvider"])
    except Exception:
        DETECTOR_SESSION = None
    try:
        SEGMENTER_SESSION = ort.InferenceSession(segmenter_path, providers=["CPUExecutionProvider"])
    except Exception:
        SEGMENTER_SESSION = None


@app.on_event("startup")
def startup_event():
    load_models()


def preprocess_tile(tile: np.ndarray, target_size: int = constants.MODEL_INPUT_SIZE) -> np.ndarray:
    # Accept single-channel or multi-channel; convert to 3-channel float32 and resize
    if tile.dtype != np.float32:
        tile = tile.astype(np.float32)
    if tile.ndim == 2:
        tile = np.stack([tile, tile, tile], axis=2)
    # resize with simple numpy (nearest) if needed
    h, w, c = tile.shape
    if h != target_size or w != target_size:
        tile = np.array(
            np.stack([np.resize(tile[:, :, ch], (target_size, target_size)) for ch in range(c)], axis=2),
            dtype=np.float32,
        )
        tile = np.transpose(tile, (1, 2, 0))
    # normalize 0..1
    tile = (tile - tile.min()) / (tile.max() - tile.min() + 1e-6)
    # HWC -> CHW
    tile = np.transpose(tile, (2, 0, 1))
    tile = np.expand_dims(tile, axis=0)
    return tile


def xywh2xyxy(box: Tuple[float, float, float, float]) -> List[float]:
    x, y, w, h = box
    x1 = x - w / 2
    y1 = y - h / 2
    x2 = x + w / 2
    y2 = y + h / 2
    return [x1, y1, x2, y2]


def nms(boxes: List[List[float]], scores: List[float], iou_threshold: float = 0.45) -> List[int]:
    if len(boxes) == 0:
        return []
    boxes = np.array(boxes)
    scores = np.array(scores)
    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)
        inds = np.where(iou <= iou_threshold)[0]
        order = order[inds + 1]
    return keep


@app.post("/detect", status_code=status.HTTP_200_OK, response_model=DetectionEvent)
async def detect_vessels(req: DetectRequest) -> DetectionEvent:
    if DETECTOR_SESSION is None:
        raise HTTPException(status_code=500, detail="Detector model not loaded")
    # load tile
    tile = None
    if req.tile_path:
        try:
            tile = np.load(req.tile_path)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Unable to load tile from path: {e}")
    elif req.tile_b64:
        try:
            raw = base64.b64decode(req.tile_b64)
            tile = np.load(io.BytesIO(raw))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Unable to decode base64 .npy tile: {e}")
    else:
        raise HTTPException(status_code=400, detail="Either tile_path or tile_b64 must be provided")

    start = time.time()
    inp = preprocess_tile(tile)
    input_name = DETECTOR_SESSION.get_inputs()[0].name
    try:
        outputs = DETECTOR_SESSION.run(None, {input_name: inp})
    except Exception as e:
        logger.error(f"ONNX runtime error during inference: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Model inference error")
    # YOLOv8 style output: (1, n, 85) or list
    preds = outputs[0]
    preds = np.squeeze(preds)
    boxes = []
    scores = []
    conf_thresh = 0.25
    for row in preds:
        conf = float(row[4])
        if conf < conf_thresh:
            continue
        # xywh + class scores
        xywh = row[0:4]
        class_conf = float(np.max(row[5:])) if row.shape[0] > 5 else 0.0
        score = conf * class_conf if class_conf > 0 else conf
        xyxy = xywh2xyxy(xywh)
        boxes.append(xyxy)
        scores.append(score)
    keep = nms(boxes, scores)
    detections: List[BoundingBox] = []
    for i in keep:
        x1, y1, x2, y2 = boxes[i]
        # scale back to original tile size
        h, w = tile.shape[0], tile.shape[1]
        # preds assumed normalized to 0..1 or to input size; try to rescale
        x1_pix = max(0.0, x1 * w)
        y1_pix = max(0.0, y1 * h)
        x2_pix = min(w, x2 * w)
        y2_pix = min(h, y2 * h)
        detections.append(
            BoundingBox(x1=float(x1_pix), y1=float(y1_pix), x2=float(x2_pix), y2=float(y2_pix), confidence=float(scores[i]))
        )

    processing_time_ms = (time.time() - start) * 1000.0
    vessel_count = len(detections)
    dark_vessel_count = vessel_count  # placeholder: no AIS matching implemented here
    # priority heuristic
    if vessel_count >= 10:
        priority = "CRITICAL"
    elif vessel_count >= 5:
        priority = "HIGH"
    elif vessel_count >= 2:
        priority = "MEDIUM"
    else:
        priority = "LOW"

    event = DetectionEvent(
        event_id=str(uuid.uuid4()),
        scene_id=req.scene_id or "unknown",
        timestamp=datetime.utcnow(),
        tile_id=req.tile_id or str(uuid.uuid4()),
        tile_bbox_latlon=[0.0, 0.0, 0.0, 0.0],
        detections=detections,
        vessel_count=vessel_count,
        dark_vessel_count=dark_vessel_count,
        priority_level=priority,
        zone="Z3",
        satellite_id=None,
        satellite_position=None,
        preprocessing_pipeline=req.preprocessing_pipeline,
        processing_time_ms=processing_time_ms,
    )
    return event


@app.get("/health", response_model=Dict[str, str])
async def health_check() -> Dict[str, str]:
    ok = "ok" if DETECTOR_SESSION is not None and SEGMENTER_SESSION is not None else "partial"
    return {"status": "healthy", "models": ok}
