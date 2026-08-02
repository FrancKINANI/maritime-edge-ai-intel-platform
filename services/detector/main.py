# services/detector/main.py
"""Detector FastAPI Service.

Exposes endpoints for running model inference on preprocessed .npy tiles
to detect vessels and output raw detection events.
"""

import base64
import io
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import numpy as np
import onnxruntime as ort
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

from shared.config import SecretsValidationError, constants, validate_service_secrets
from shared.schemas.events import BoundingBox, DetectionEvent

logger = logging.getLogger(__name__)

# Validate required environment variables at startup
# NOTE: We warn instead of sys.exit() to allow test imports without env vars.
try:
    validate_service_secrets("detector")
    logger.info("Secrets validation passed")
except SecretsValidationError as e:
    logger.error("Secrets validation failed: %s", e)
    logger.warning("Service will start but may fail at runtime — set REDIS_URL in .env")


class DetectRequest(BaseModel):
    tile_path: str | None = None
    tile_b64: str | None = None
    scene_id: str | None = "unknown"
    tile_id: str | None = None
    preprocessing_pipeline: str = "D"


# Load ONNX models once at startup
DETECTOR_SESSION: ort.InferenceSession | None = None
SEGMENTER_SESSION: ort.InferenceSession | None = None


def load_models():
    global DETECTOR_SESSION, SEGMENTER_SESSION
    model_dir = "shared/models"
    detector_path = f"{model_dir}/{constants.DETECTOR_MODEL}"
    segmenter_path = f"{model_dir}/{constants.SEGMENTER_MODEL}"
    try:
        DETECTOR_SESSION = ort.InferenceSession(detector_path, providers=["CPUExecutionProvider"])
    except Exception as e:
        logger.warning("Failed to load detector model %s: %s", detector_path, e)
        DETECTOR_SESSION = None
    try:
        SEGMENTER_SESSION = ort.InferenceSession(segmenter_path, providers=["CPUExecutionProvider"])
    except Exception as e:
        logger.warning("Failed to load segmenter model %s: %s", segmenter_path, e)
        SEGMENTER_SESSION = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_models()
    yield


app = FastAPI(
    title="Maritime Edge AI Intel Platform - Detector",
    description="Microservice wrapping the Phase I YOLOv8 ONNX model for ship detection.",
    version="1.0.0",
    lifespan=lifespan,
)


def preprocess_tile(tile: np.ndarray, target_size: int = constants.MODEL_INPUT_SIZE) -> np.ndarray:
    """Convert a tile to a NCHW float32 batch for the ONNX model.

    The model expects (1, 3, H, W) in [0, 1]. Tiles are converted to
    3-channel HWC, resized to target_size, normalized, then transposed to CHW.
    """
    if tile.dtype != np.float32:
        tile = tile.astype(np.float32)
    if tile.ndim == 2:
        tile = np.stack([tile, tile, tile], axis=2)
    h, w, c = tile.shape
    if h != target_size or w != target_size:
        # True nearest-neighbor resize per channel (np.repeat, then crop).
        # NOTE: np.resize would tile the flattened array (mosaic artifact);
        # this scales each channel with an integer upscale factor + center crop.
        resized = np.zeros((target_size, target_size, c), dtype=np.float32)
        for ch in range(c):
            ch_tile = tile[:, :, ch]
            scale_y = max(1, int(np.ceil(target_size / h)))
            scale_x = max(1, int(np.ceil(target_size / w)))
            up = np.repeat(np.repeat(ch_tile, scale_y, axis=0), scale_x, axis=1)
            # Center crop to target size
            y0 = max(0, (up.shape[0] - target_size) // 2)
            x0 = max(0, (up.shape[1] - target_size) // 2)
            resized[:, :, ch] = up[y0 : y0 + target_size, x0 : x0 + target_size]
        tile = resized
    # normalize 0..1
    tile = (tile - tile.min()) / (tile.max() - tile.min() + 1e-6)
    # HWC -> NCHW batch
    tile = np.transpose(tile, (2, 0, 1))  # (C, H, W)
    tile = np.expand_dims(tile, axis=0)  # (1, C, H, W)
    return tile


def xywh2xyxy(box: tuple[float, float, float, float]) -> list[float]:
    x, y, w, h = box
    x1 = x - w / 2
    y1 = y - h / 2
    x2 = x + w / 2
    y2 = y + h / 2
    return [x1, y1, x2, y2]


def nms(boxes: list[list[float]], scores: list[float], iou_threshold: float = 0.45) -> list[int]:
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
            logger.error("Failed to load tile from path %s: %s", req.tile_path, e, exc_info=True)
            raise HTTPException(
                status_code=400,
                detail="Unable to load tile from path. Ensure it is a valid .npy file.",
            ) from e
    elif req.tile_b64:
        try:
            raw = base64.b64decode(req.tile_b64)
            tile = np.load(io.BytesIO(raw))
        except Exception as e:
            logger.error("Failed to decode base64 .npy tile: %s", e, exc_info=True)
            raise HTTPException(
                status_code=400,
                detail="Unable to decode base64 tile. Ensure it is a valid .npy file.",
            ) from e
    else:
        raise HTTPException(status_code=400, detail="Either tile_path or tile_b64 must be provided")

    start = time.time()
    inp = preprocess_tile(tile)
    input_name = DETECTOR_SESSION.get_inputs()[0].name
    try:
        outputs = DETECTOR_SESSION.run(None, {input_name: inp})
    except Exception as e:
        logger.error(f"ONNX runtime error during inference: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Model inference error") from e
    # MRSSD YOLOv8 output: (1, 5, 8400) = [cx, cy, w, h, obj_conf] (single class)
    preds = outputs[0]
    preds = np.squeeze(preds)  # (5, 8400)
    if preds.ndim == 2 and preds.shape[0] == 5:
        boxes = []
        scores = []
        conf_thresh = 0.25
        for i in range(preds.shape[1]):
            cx, cy, bw, bh, conf = preds[:, i]
            conf = float(conf)
            if conf < conf_thresh:
                continue
            xyxy = xywh2xyxy((float(cx), float(cy), float(bw), float(bh)))
            boxes.append(xyxy)
            scores.append(conf)
    else:
        # Fallback: generic (N, 4+1+classes) row format
        boxes = []
        scores = []
        conf_thresh = 0.25
        for row in preds:
            conf = float(row[4])
            if conf < conf_thresh:
                continue
            xywh = row[0:4]
            class_conf = float(np.max(row[5:])) if row.shape[0] > 5 else 0.0
            score = conf * class_conf if class_conf > 0 else conf
            xyxy = xywh2xyxy(xywh)
            boxes.append(xyxy)
            scores.append(score)
    keep = nms(boxes, scores)
    detections: list[BoundingBox] = []
    h, w = tile.shape[0], tile.shape[1]
    # Model coordinates are in input-image pixels (MODEL_INPUT_SIZE x MODEL_INPUT_SIZE).
    # Rescale them back to the original tile size.
    scale_x = w / constants.MODEL_INPUT_SIZE
    scale_y = h / constants.MODEL_INPUT_SIZE
    for i in keep:
        x1, y1, x2, y2 = boxes[i]
        x1_pix = max(0.0, x1 * scale_x)
        y1_pix = max(0.0, y1 * scale_y)
        x2_pix = min(w, x2 * scale_x)
        y2_pix = min(h, y2 * scale_y)
        detections.append(
            BoundingBox(
                x1=float(x1_pix),
                y1=float(y1_pix),
                x2=float(x2_pix),
                y2=float(y2_pix),
                confidence=float(scores[i]),
            )
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
        timestamp=datetime.now(UTC),
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


@app.get("/health", response_model=dict[str, str])
async def health_check() -> dict[str, str]:
    ok = "ok" if DETECTOR_SESSION is not None and SEGMENTER_SESSION is not None else "partial"
    return {"status": "healthy", "models": ok}
