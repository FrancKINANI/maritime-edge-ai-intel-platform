# shared/config/constants.py
"""Shared constants for the maritime intelligence platform.

This module contains configuration values for geographic zones,
SAR preprocessing algorithms, detector specifications, and satellite metadata.
"""

from typing import List

# Zones géographiques marocaines (Geographic boundaries for Morocco EEZ and Territorial Waters)
# format: [lon_min, lat_min, lon_max, lat_max]
MOROCCO_BBOX: List[float] = [-17.0, 27.0, -1.0, 36.0]
ZONE_Z1_NM: int = 12      # Territorial Waters (Eaux territoriales)
ZONE_Z2_NM: int = 200     # Exclusive Economic Zone (ZEE)
ZONE_Z3_LABEL: str = "haute_mer"

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
PREPROCESSING_PIPELINES = {
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
