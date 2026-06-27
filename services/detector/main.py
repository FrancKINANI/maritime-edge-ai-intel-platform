# services/detector/main.py
"""Detector FastAPI Service.

Exposes endpoints for running model inference on preprocessed .npy tiles
to detect vessels and output raw detection events.
"""

from fastapi import FastAPI, HTTPException, status
from typing import Dict
from shared.schemas.events import DetectionEvent

app = FastAPI(
    title="Maritime Edge AI Intel Platform - Detector",
    description="Microservice wrapping the Phase I YOLOv8 ONNX model for ship detection.",
    version="1.0.0",
)


# Note: This service wraps the Phase I pipeline.
# ONNX INT8 models (e.g. yolov8n_int8.onnx) must be stored in 'shared/models/'
# and mounted via docker-compose volumes.


@app.post("/detect", status_code=status.HTTP_200_OK, response_model=DetectionEvent)
async def detect_vessels(tile_path: str) -> DetectionEvent:
    """Detects vessels inside a preprocessed numpy sub-tile.

    Reads a .npy tile from the shared volume, executes the quantized YOLOv8 ONNX
    model, and formats the output into a DetectionEvent structure.

    Args:
        tile_path (str): File path to the target .npy tile.

    Returns:
        DetectionEvent: Extracted vessel bounding boxes and geospatial context.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Model inference and detection wrapping is not yet implemented.",
    )


@app.get("/health", response_model=Dict[str, str])
async def health_check() -> Dict[str, str]:
    """Service health check endpoint.

    Returns:
        Dict[str, str]: Service status message.
    """
    return {"status": "healthy"}
