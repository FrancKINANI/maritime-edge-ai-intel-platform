# shared/config/constants.py
"""Shared constants for the maritime intelligence platform.

This module contains configuration values for geographic zones,
SAR preprocessing algorithms, detector specifications, and satellite metadata.

NOTEBOOK <-> SCRIPTS SYNCHRONIZATION:
    The Colab notebook (colab_phase0_pipeline_final.ipynb) should, in the next
    session, IMPORT these constants from this file rather than redefining them
    locally. This file is the single source of truth for all shared constants.
"""

from typing import List, Dict

# Geographic boundaries for Morocco EEZ and Territorial Waters
# format: [lon_min, lat_min, lon_max, lat_max]
MOROCCO_BBOX: List[float] = [-17.0, 27.0, -1.0, 36.0]
ZONE_Z1_NM: int = 12      # Territorial Waters
ZONE_Z2_NM: int = 200     # Exclusive Economic Zone
ZONE_Z3_LABEL: str = "high_seas"

# Preprocessing SAR parameters
TILE_SIZE: int = 512          # pixel dimensions (512x512)
TILE_OVERLAP: float = 0.5       # 50% overlap for sliding window slicing
SPECKLE_FILTER_SIZE: int = 5  # Lee filter kernel size (5x5)
DB_RANGE_MIN: float = -30.0     # Min dB threshold for clipping
DB_RANGE_MAX: float = 0.0       # Max dB threshold for clipping
TARGET_NORM_MIN: int = 0
TARGET_NORM_MAX: int = 255

# ML Models and Inference Configurations
DETECTOR_MODEL: str = "yolov8n_int8.onnx"
SEGMENTER_MODEL: str = "yolov8n_seg_int8.onnx"
MODEL_INPUT_SIZE: int = 640   # Yolov8 input shape (640x640)

# Priority Engine Levels
PRIORITY_LEVELS: List[str] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

# Preprocessing pipeline configurations for Phase 0 validation
PREPROCESSING_PIPELINES: Dict[str, str] = {
    "A": "raw",
    "B": "sigma0",
    "C": "sigma0_lee",
    "D": "sigma0_lee_log",
}

# Orbital tracking constants
TLE_REFRESH_HOURS: int = 24

# Sentinel-1 Product parameters
SENTINEL1_PRODUCT_TYPE: str = "IW_GRDH_1S"
SENTINEL1_POLARIZATION: str = "VV VH"

# GFW API constants (shared between phase0/scripts/ and notebook)
GFW_MARGIN_DEG: float = 0.01         # Margin around bbox for GFW queries
N_EMPTY_TILES_PER_SCENE: int = 80     # Number of empty control tiles per scene
MAX_TILES_PER_SCENE_HARD_CAP: int = 600  # Hard cap on tiles per scene
GFW_SPATIAL_RESOLUTION: str = "HIGH"   # Spatial resolution for GFW queries (LOW or HIGH)

# AIS density map constants
DENSITY_CELL_SIZE_DEG: float = 0.5    # ~55 km -- density map granularity
DENSITY_LOOKBACK_DAYS: int = 30       # Recent period for AIS density query
N_TARGET_ZONES: int = 5               # Number of high-density zones to target
MAX_TEST_SCENES: int = 5              # Strict test batch size

# Benchmark constants
NODATA_THRESHOLD: float = 0.30        # Max NoData ratio to keep a tile
PIPELINES: List[str] = ["A", "B", "C", "D"]
POLARIZATION: str = "vv"
