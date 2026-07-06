# services/sentinel-preprocessor/sar_preprocessing.py
"""SAR Image Preprocessing and Tiling Operations.

Exposes calibration, speckle filtering, decibel mapping, normalization,
and tiling routines.
"""

import numpy as np
from typing import List, Tuple, Dict, Any, Optional

# Reuse the robust windowed pipeline implementation from phase0 when available.
try:
    from phase0.scripts.sar_preprocessing import (
        process_safe_windowed,
        CalibrationLUT,
        _lee_filter_windowed,
    )
    _HAS_PHASE0 = True
except Exception:
    _HAS_PHASE0 = False


def calibrate_sigma0(data: np.ndarray, calibration_lut: np.ndarray) -> np.ndarray:
    """Simple radiometric calibration: DN^2 / calibration_lut^2

    The full, memory-efficient CalibrationLUT-based interpolation is available
    in `phase0.scripts.sar_preprocessing.CalibrationLUT`. This function performs
    pointwise calibration for already-aligned arrays.
    """
    cal_safe = np.where(calibration_lut == 0, 1e-10, calibration_lut)
    sigma0 = (data.astype(np.float32) ** 2) / (cal_safe.astype(np.float32) ** 2)
    sigma0 = np.maximum(sigma0, 0.0)
    return sigma0


def apply_lee_filter(data: np.ndarray, kernel_size: int = 5) -> np.ndarray:
    """Apply Lee speckle filter to SAR data.

    In SAR imagery, speckle noise is multiplicative and follows a gamma distribution.
    The Lee filter is an adaptive filter that preserves edges while reducing speckle,
    which is critical for vessel detection where ship wakes must remain visible.

    This implementation uses the phase0 windowed version when available for memory
    efficiency on large scenes (25K×16K pixels). Falls back to a simple local-mean
    filter if phase0 is not present.

    Args:
        data: Input SAR array (float32)
        kernel_size: Size of the Lee filter kernel (default 5×5)

    Returns:
        Filtered SAR array (float32)
    """
    if _HAS_PHASE0:
        return _lee_filter_windowed(data.astype(np.float32), kernel_size=kernel_size)
    # Fallback: simple mean filter
    from scipy.ndimage import uniform_filter

    local_mean = uniform_filter(data.astype(np.float32), size=kernel_size, mode="reflect")
    return local_mean.astype(np.float32)


def convert_to_db(data: np.ndarray) -> np.ndarray:
    return 10.0 * np.log10(np.maximum(data.astype(np.float32), 1e-10))


def normalize_to_uint8(data: np.ndarray, db_min: float = -30.0, db_max: float = 0.0) -> np.ndarray:
    clipped = np.clip(data, db_min, db_max)
    norm = ((clipped - db_min) / (db_max - db_min) * 255.0).astype(np.uint8)
    return norm


def tile_image(data: np.ndarray, tile_size: int = 512, overlap: float = 0.5) -> List[Tuple[np.ndarray, Tuple[int, int, int, int]]]:
    h, w = data.shape[:2]
    stride = max(1, int(tile_size * (1 - overlap)))
    tiles = []
    for y in range(0, h, stride):
        for x in range(0, w, stride):
            y_end = min(y + tile_size, h)
            x_end = min(x + tile_size, w)
            tile = data[y:y_end, x:x_end]
            tiles.append((tile, (y, x, y_end, x_end)))
    return tiles


def pipeline_A(safe_path: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
    """Pipeline A: baseline using phase0 implementation when available.
    Returns manifest dictionary with tile metadata.
    """
    if _HAS_PHASE0:
        return process_safe_windowed(safe_path, "A", output_dir or "data/tiles")
    raise NotImplementedError("phase0 implementation not available in workspace")


def pipeline_B(safe_path: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
    if _HAS_PHASE0:
        return process_safe_windowed(safe_path, "B", output_dir or "data/tiles")
    raise NotImplementedError("phase0 implementation not available in workspace")


def pipeline_C(safe_path: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
    if _HAS_PHASE0:
        return process_safe_windowed(safe_path, "C", output_dir or "data/tiles")
    raise NotImplementedError("phase0 implementation not available in workspace")


def pipeline_D(safe_path: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
    if _HAS_PHASE0:
        return process_safe_windowed(safe_path, "D", output_dir or "data/tiles")
    raise NotImplementedError("phase0 implementation not available in workspace")
