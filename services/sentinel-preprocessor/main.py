# services/sentinel-preprocessor/main.py
"""Sentinel Preprocessor FastAPI Service.

Exposes endpoints for preprocessing downloaded Sentinel-1 SAFE products into
numpy sub-tiles using multiple pipelines.
"""

from fastapi import FastAPI, HTTPException, status
from typing import Dict, Any

app = FastAPI(
    title="Maritime Edge AI Intel Platform - Sentinel Preprocessor",
    description="Microservice responsible for calibrating, filtering, scaling, and tiling SAR images.",
    version="1.0.0",
)


@app.post("/preprocess", status_code=status.HTTP_200_OK, response_model=Dict[str, Any])
async def preprocess_scene(safe_path: str, pipeline: str = "D") -> Dict[str, Any]:
    """Triggers Sentinel-1 scene preprocessing.

    Reads a .SAFE product, runs the requested preprocessing pipeline (A/B/C/D),
    generates overlapping sub-tiles, and saves them to the shared volume directory.

    Args:
        safe_path (str): Absolute or relative file path to the source .SAFE folder.
        pipeline (str): Pipeline variant selector (A, B, C, or D).

    Returns:
        Dict[str, Any]: Information about generated tiles and saving location.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="SAR image preprocessing is not yet implemented.",
    )


@app.get("/pipelines", response_model=Dict[str, str])
async def list_pipelines() -> Dict[str, str]:
    """Lists the names and descriptions of the available preprocessing pipelines.

    Returns:
        Dict[str, str]: Preprocessing pipeline description mapping.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Pipeline list retrieval is not yet implemented.",
    )


@app.get("/health", response_model=Dict[str, str])
async def health_check() -> Dict[str, str]:
    """Service health check endpoint.

    Returns:
        Dict[str, str]: Service status message.
    """
    return {"status": "healthy"}
