# services/sentinel-preprocessor/main.py
"""Sentinel Preprocessor FastAPI Service.

Exposes endpoints for preprocessing downloaded Sentinel-1 SAFE products into
numpy sub-tiles using multiple pipelines.
"""

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, status

from shared.config import constants

logger = logging.getLogger(__name__)

# Load the local sar_preprocessing module (directory name contains a hyphen)
_sp_path = Path(__file__).resolve().parent / "sar_preprocessing.py"
spec = importlib.util.spec_from_file_location("sentinel_sp", str(_sp_path))
sar_preprocessing = importlib.util.module_from_spec(spec)
sys.modules["sentinel_sp"] = sar_preprocessing
spec.loader.exec_module(sar_preprocessing)


app = FastAPI(
    title="Maritime Edge AI Intel Platform - Sentinel Preprocessor",
    description="Microservice responsible for calibrating, filtering, scaling, and tiling SAR images.",
    version="1.0.0",
)


@app.post("/preprocess", status_code=status.HTTP_200_OK, response_model=Dict[str, Any])
async def preprocess_scene(safe_path: str, pipeline: str = None, output_dir: str = None) -> Dict[str, Any]:
    """Triggers Sentinel-1 scene preprocessing and returns manifest.

    The default pipeline comes from environment configuration. See README.md for
    the note that the default pipeline is provisional pending Phase 0 benchmark.
    """
    # Default to pipeline D when omitted; never assign dict_keys (was a TypeError on .upper()).
    if pipeline is None or pipeline == "":
        pipeline = "D"
    pipeline = str(pipeline).upper()
    if pipeline not in ["A", "B", "C", "D"]:
        raise HTTPException(status_code=400, detail="pipeline must be one of A/B/C/D")

    if output_dir is None:
        # Save under shared/data/tiles by default
        base = Path(__file__).resolve().parents[2] / "phase0" / "data" / "tiles"
        output_dir = str(base)

    try:
        if pipeline == "A":
            result = sar_preprocessing.pipeline_A(safe_path, output_dir)
        elif pipeline == "B":
            result = sar_preprocessing.pipeline_B(safe_path, output_dir)
        elif pipeline == "C":
            result = sar_preprocessing.pipeline_C(safe_path, output_dir)
        else:
            result = sar_preprocessing.pipeline_D(safe_path, output_dir)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        logger.error("Preprocessing failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Preprocessing failed")

    return result


@app.get("/pipelines", response_model=Dict[str, str])
async def list_pipelines() -> Dict[str, str]:
    return {k: v for k, v in constants.PREPROCESSING_PIPELINES.items()}


@app.get("/health", response_model=Dict[str, str])
async def health_check() -> Dict[str, str]:
    return {"status": "healthy"}
