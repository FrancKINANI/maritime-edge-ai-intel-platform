"""Sentinel-1 GRD SAR Preprocessing and Tiling Framework.

Purpose:
    Implements a modular, composable SAR preprocessing pipeline for
    Sentinel-1 IW GRD products in SAFE format. Supports four benchmark
    pipelines (A/B/C/D) with increasing levels of radiometric correction.

Inputs:
    - Sentinel-1 .SAFE product directory (containing measurement/ and annotation/)
    - Pipeline selection (A, B, C, or D)
    - Optional: polarization channel (VV or VH)

Outputs:
    - 512×512 pixel tiles as .npy arrays in phase0/data/tiles/
    - Optional PNG exports for visual inspection
    - Tile metadata (pixel coordinates, geo-bounds)
    - Diagnostic figures and histograms

Design:
    Each preprocessing stage is an independent function that accepts and
    returns numpy arrays. Stages can be composed freely, enabling fair
    benchmarking of different preprocessing strategies.

References:
    - ESA Sentinel-1 Level-1 Product Specification (S1-RS-MDA-52-7441)
    - ESA Radiometric Calibration Technical Note
    - Rasterio documentation (rasterio.readthedocs.io)
"""

import time
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from scipy.interpolate import RegularGridInterpolator
from scipy.ndimage import uniform_filter

import numpy as np
import rasterio
from rasterio.transform import xy
import matplotlib.pyplot as plt
from tqdm import tqdm

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Constants
NODATA_THRESHOLD = 0.3  # Ignore tiles with >30% NoData pixels
DEFAULT_TILE_SIZE = 512
DEFAULT_OVERLAP = 0.5

# ---------------------------------------------------------------------------
# SAFE product parsing
# ---------------------------------------------------------------------------


def find_safe_files(safe_path: str, polarization: str = "vv") -> Dict[str, str]:
    """Finds necessary file paths in a .SAFE directory.

    Args:
        safe_path: Path to the .SAFE product directory.
        polarization: Desired polarization channel ('vv' or 'vh').

    Returns:
        Dict with keys: 'tiff', 'calibration', 'noise'

    Raises:
        FileNotFoundError: If required files are not found.
    """
    pol = polarization.lower()
    safe_dir = Path(safe_path)
    
    # Find measurement TIFF (prefer COG variant if available)
    measurement_dir = safe_dir / "measurement"
    cog_pattern = f"*-{pol}-*-cog.tiff"
    standard_pattern = f"*-{pol}-*.tiff"
    
    cog_files = list(measurement_dir.glob(cog_pattern))
    standard_files = list(measurement_dir.glob(standard_pattern))
    
    if cog_files:
        tiff_path = str(cog_files[0])
        logger.info(f"Found COG measurement TIFF: {tiff_path}")
    elif standard_files:
        tiff_path = str(standard_files[0])
        logger.info(f"Found standard measurement TIFF: {tiff_path}")
    else:
        raise FileNotFoundError(
            f"No measurement TIFF found for polarization '{pol}' in {safe_path}"
        )
    
    # Find calibration XML
    calibration_dir = safe_dir / "annotation" / "calibration"
    cal_pattern = f"calibration-*-{pol}-*.xml"
    cal_files = list(calibration_dir.glob(cal_pattern))
    
    if not cal_files:
        raise FileNotFoundError(
            f"No calibration XML found for polarization '{pol}' in {safe_path}"
        )
    calibration_path = str(cal_files[0])
    logger.info(f"Found calibration XML: {calibration_path}")
    
    # Find noise XML (optional)
    noise_dir = safe_dir / "annotation" / "calibration"
    noise_pattern = f"noise-*-{pol}-*.xml"
    noise_files = list(noise_dir.glob(noise_pattern))
    
    noise_path = str(noise_files[0]) if noise_files else None
    if noise_path:
        logger.info(f"Found noise XML: {noise_path}")
    else:
        logger.warning(f"No noise XML found for polarization '{pol}'")
    
    return {
        "tiff": tiff_path,
        "calibration": calibration_path,
        "noise": noise_path,
    }


# ---------------------------------------------------------------------------
# GeoTIFF reading with memory management
# ---------------------------------------------------------------------------


def read_geotiff(tiff_path: str) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Reads a Sentinel-1 GeoTIFF with rasterio.

    Args:
        tiff_path: Path to the measurement GeoTIFF.

    Returns:
        Tuple of (data array as uint16, rasterio profile dict).

    Raises:
        MemoryError: If image is too large for available RAM.
    """
    with rasterio.open(tiff_path) as src:
        width = src.width
        height = src.height
        dtype = src.dtypes[0]
        
        # Check memory requirements
        # uint16 = 2 bytes per pixel
        estimated_size_mb = (width * height * 2) / (1024 * 1024)
        
        logger.info(
            f"GeoTIFF dimensions: {width}×{height}, dtype={dtype}, "
            f"estimated size: {estimated_size_mb:.1f} MB"
        )
        
        # If image is too large (>1.5 GB), read in windows
        if estimated_size_mb > 1500:
            logger.warning(f"Large image detected ({estimated_size_mb:.1f} MB). "
                          "Reading in windows to manage memory.")
            return read_geotiff_windowed(tiff_path, src)
        
        # Read entire image if it fits in memory
        data = src.read(1)
        profile = {
            "transform": src.transform,
            "crs": src.crs,
            "width": width,
            "height": height,
            "bounds": src.bounds,
        }
        
        logger.info(f"Loaded full image: shape={data.shape}, dtype={data.dtype}")
        return data, profile


def read_geotiff_windowed(tiff_path: str, src: Any) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Reads a large GeoTIFF in windows to manage memory.

    Args:
        tiff_path: Path to the measurement GeoTIFF.
        src: Open rasterio dataset.

    Returns:
        Tuple of (data array, rasterio profile dict).
    """
    height = src.height
    width = src.width
    window_height = 10000  # Process 10000 lines at a time
    
    # Pre-allocate output array
    data = np.zeros((height, width), dtype=src.dtypes[0])
    
    for i in range(0, height, window_height):
        window_height_actual = min(window_height, height - i)
        window = ((i, i + window_height_actual), (0, width))
        
        window_data = src.read(1, window=window)
        data[i:i + window_height_actual, :] = window_data
        
        logger.debug(f"Read window {i}-{i + window_height_actual}/{height}")
    
    profile = {
        "transform": src.transform,
        "crs": src.crs,
        "width": width,
        "height": height,
        "bounds": src.bounds,
    }
    
    logger.info(f"Loaded windowed image: shape={data.shape}, dtype={data.dtype}")
    return data, profile


# ---------------------------------------------------------------------------
# Calibration LUT parsing
# ---------------------------------------------------------------------------


def parse_calibration_lut(calibration_xml_path: str) -> np.ndarray:
    """Parses Sentinel-1 calibration XML to extract sigmaNought vectors.

    Args:
        calibration_xml_path: Path to the calibration annotation XML.

    Returns:
        2D numpy array (lines × samples) of sigma-nought calibration values.

    Raises:
        ValueError: If the XML structure is unexpected or no vectors are found.
    """
    tree = ET.parse(calibration_xml_path)
    root = tree.getroot()

    vectors = root.findall(".//calibrationVector")
    if not vectors:
        raise ValueError(
            f"No calibrationVector elements found in {calibration_xml_path}"
        )

    # Parse each calibration vector (one per azimuth line)
    lines = []
    sigma_values = []
    pixel_indices = None

    for vec in vectors:
        line = int(vec.find("line").text)
        pixels_text = vec.find("pixel").text
        sigma_text = vec.find("sigmaNought").text

        pixels = np.array([int(p) for p in pixels_text.split()])
        sigma = np.array([float(v) for v in sigma_text.split()])

        if pixel_indices is None:
            pixel_indices = pixels
        lines.append(line)
        sigma_values.append(sigma)

    logger.info(
        f"Parsed {len(vectors)} calibration vectors, "
        f"pixel samples per vector: {len(pixel_indices)}"
    )

    # Stack into 2D array (num_vectors × num_pixel_samples)
    lut_2d = np.array(sigma_values)
    
    # Interpolate to full resolution using RegularGridInterpolator
    # This handles the non-uniform sampling in the XML
    lines_array = np.array(lines)
    pixel_array = pixel_indices
    
    # Create interpolator
    interpolator = RegularGridInterpolator(
        (lines_array, pixel_array),
        lut_2d,
        method='linear',
        bounds_error=False,
        fill_value=None
    )
    
    # We'll return the raw LUT for now - interpolation will be done
    # during calibration to match the actual image dimensions
    return lut_2d, lines_array, pixel_array


def parse_noise_lut(noise_xml_path: str) -> np.ndarray:
    """Parses Sentinel-1 noise XML to extract noise vectors.

    Handles both old format (<noiseLut>) and new format (<noiseRangeLut>).

    Args:
        noise_xml_path: Path to the noise annotation XML.

    Returns:
        2D numpy array of noise values.

    Raises:
        ValueError: If the XML structure is unexpected.
    """
    tree = ET.parse(noise_xml_path)
    root = tree.getroot()

    # Try new format first
    noise_range_vectors = root.findall(".//noiseRangeLut")
    if noise_range_vectors:
        logger.info("Found new format noise LUT (noiseRangeLut)")
        vectors = noise_range_vectors
    else:
        # Try old format
        noise_vectors = root.findall(".//noiseLut")
        if noise_vectors:
            logger.info("Found old format noise LUT (noiseLut)")
            vectors = noise_vectors
        else:
            raise ValueError(
                f"No noise LUT elements found in {noise_xml_path}"
            )

    # Parse vectors (similar structure to calibration)
    lines = []
    noise_values = []
    pixel_indices = None

    for vec in vectors:
        line_elem = vec.find("line")
        if line_elem is not None:
            line = int(line_elem.text)
        else:
            continue
            
        pixel_elem = vec.find("pixel")
        noise_elem = vec.find("noiseLut") if vec.find("noiseLut") is not None else vec.find("noiseRangeLut")
        
        if pixel_elem is not None and noise_elem is not None:
            pixels = np.array([int(p) for p in pixel_elem.text.split()])
            noise = np.array([float(v) for v in noise_elem.text.split()])

            if pixel_indices is None:
                pixel_indices = pixels
            lines.append(line)
            noise_values.append(noise)

    if not lines:
        raise ValueError(f"No valid noise vectors found in {noise_xml_path}")

    logger.info(f"Parsed {len(lines)} noise vectors")
    
    lut_2d = np.array(noise_values)
    return lut_2d, np.array(lines), pixel_indices


def interpolate_lut_to_image(
    lut_2d: np.ndarray,
    lut_lines: np.ndarray,
    lut_pixels: np.ndarray,
    image_shape: Tuple[int, int]
) -> np.ndarray:
    """Interpolates a sub-sampled LUT to full image resolution.

    Args:
        lut_2d: 2D LUT array (num_vectors × num_pixel_samples).
        lut_lines: Array of line indices for each vector.
        lut_pixels: Array of pixel indices for each sample.
        image_shape: Target image shape (height, width).

    Returns:
        2D LUT array interpolated to image dimensions.
    """
    height, width = image_shape
    
    # Create coordinate grids for the image
    line_coords = np.arange(height)
    pixel_coords = np.arange(width)
    
    # Create meshgrid for interpolation
    line_grid, pixel_grid = np.meshgrid(line_coords, pixel_coords, indexing='ij')
    
    # Create interpolator
    interpolator = RegularGridInterpolator(
        (lut_lines, lut_pixels),
        lut_2d,
        method='linear',
        bounds_error=False,
        fill_value=None
    )
    
    # Interpolate
    points = np.column_stack([line_grid.ravel(), pixel_grid.ravel()])
    lut_full = interpolator(points).reshape(image_shape)
    
    logger.info(f"Interpolated LUT from {lut_2d.shape} to {image_shape}")
    return lut_full


# ---------------------------------------------------------------------------
# Radiometric calibration
# ---------------------------------------------------------------------------


def calibrate_sigma0(
    data: np.ndarray,
    calibration_lut: np.ndarray,
    noise_lut: Optional[np.ndarray] = None
) -> np.ndarray:
    """Converts DN uint16 → σ0 linear power.

    Formula: σ0 = (DN² - noise) / calibration²

    Args:
        data: 2D array of raw digital numbers (uint16).
        calibration_lut: 2D calibration LUT array (full resolution).
        noise_lut: Optional 2D noise LUT array (full resolution).

    Returns:
        2D array of σ0 values in linear power scale (float32).
    """
    # Convert to float for calculations
    dn = data.astype(np.float32)
    
    # Apply noise subtraction if noise LUT is provided
    if noise_lut is not None:
        dn_squared = np.maximum(dn ** 2 - noise_lut, 0)
    else:
        dn_squared = dn ** 2
    
    # Avoid division by zero
    cal_lut_safe = np.where(calibration_lut == 0, 1e-10, calibration_lut)
    
    # Calculate sigma0
    sigma0 = dn_squared / (cal_lut_safe ** 2)
    
    # Clip negative values (physically impossible)
    sigma0 = np.maximum(sigma0, 0)
    
    logger.info(
        f"Calibrated to σ0: min={sigma0.min():.6f}, max={sigma0.max():.6f}, "
        f"mean={sigma0.mean():.6f}"
    )
    return sigma0


# ---------------------------------------------------------------------------
# Speckle filtering
# ---------------------------------------------------------------------------


def apply_lee_filter(data: np.ndarray, kernel_size: int = 5) -> np.ndarray:
    """Applies an adaptive Lee speckle filter to reduce SAR multiplicative noise.

    Simplified Lee algorithm:
      1. Calculate local mean μ and local variance σ²
      2. Estimate coefficient of variation CV = σ/μ
      3. Calculate weight W = σ²_signal / σ²
         where σ²_signal = max(0, σ² - σ²_noise)
         and σ²_noise = mean(σ²) (global speckle variance estimate)
      4. Filtered pixel = μ + W * (pixel - μ)

    Args:
        data: 2D array of SAR backscatter values (linear or dB scale).
        kernel_size: Size of the square sliding window (must be odd).

    Returns:
        Despeckled 2D array (float32).

    Raises:
        ValueError: If kernel_size is not a positive odd integer.
    """
    if kernel_size < 1 or kernel_size % 2 == 0:
        raise ValueError(f"kernel_size must be a positive odd integer, got {kernel_size}")

    logger.info(f"Applying Lee filter with {kernel_size}×{kernel_size} kernel...")

    # Local statistics
    local_mean = uniform_filter(data, size=kernel_size, mode="reflect")
    local_sq_mean = uniform_filter(data ** 2, size=kernel_size, mode="reflect")
    local_var = local_sq_mean - local_mean ** 2
    local_var = np.maximum(local_var, 0)  # Ensure non-negative

    # Estimate noise variance (global average of local variance)
    noise_var = np.mean(local_var)

    # Calculate signal variance
    signal_var = np.maximum(local_var - noise_var, 0)

    # Calculate adaptive weight
    # Avoid division by zero
    total_var = np.maximum(local_var, noise_var)
    weight = signal_var / total_var

    # Apply Lee filter
    filtered = local_mean + weight * (data - local_mean)

    logger.info(f"Lee filter applied. Noise variance estimate: {noise_var:.6f}")
    return filtered.astype(np.float32)


# ---------------------------------------------------------------------------
# Logarithmic conversion
# ---------------------------------------------------------------------------


def convert_to_db(data: np.ndarray, epsilon: float = 1e-10) -> np.ndarray:
    """Converts σ0 linear power → dB.

    Formula: dB = 10 * log10(σ0 + epsilon)

    Args:
        data: 2D array of linear power values.
        epsilon: Small value to avoid log(0).

    Returns:
        2D array in dB scale (float32).
    """
    db = 10 * np.log10(data + epsilon)
    logger.info(
        f"Converted to dB: min={db.min():.2f}, max={db.max():.2f}, "
        f"mean={db.mean():.2f}"
    )
    return db.astype(np.float32)


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def normalize_to_uint8(
    data: np.ndarray,
    db_min: float = -30.0,
    db_max: float = 0.0,
    method: str = "linear"
) -> np.ndarray:
    """Normalizes a dB array to uint8 [0, 255].

    Args:
        data: 2D array of dB values.
        db_min: Minimum dB value for linear normalization.
        db_max: Maximum dB value for linear normalization.
        method: Normalization method ('linear', 'percentile', 'equalize').

    Returns:
        2D uint8 array.

    Raises:
        ValueError: If method is not recognized.
    """
    if method == "linear":
        # Linear stretch to specified range
        clipped = np.clip(data, db_min, db_max)
        normalized = ((clipped - db_min) / (db_max - db_min) * 255.0).astype(np.uint8)
        logger.info(f"Normalized (linear): range [{db_min}, {db_max}] → [0, 255]")
        
    elif method == "percentile":
        # Percentile-based normalization (more robust to outliers)
        pmin, pmax = np.percentile(data, [2, 98])
        clipped = np.clip(data, pmin, pmax)
        normalized = ((clipped - pmin) / (pmax - pmin) * 255.0).astype(np.uint8)
        logger.info(f"Normalized (percentile): range [{pmin:.2f}, {pmax:.2f}] → [0, 255]")
        
    elif method == "equalize":
        # Histogram equalization
        # Convert to uint8 range first
        data_min, data_max = data.min(), data.max()
        if data_max > data_min:
            stretched = ((data - data_min) / (data_max - data_min) * 255).astype(np.uint8)
        else:
            stretched = np.zeros_like(data, dtype=np.uint8)
        
        # Histogram equalization
        hist, bins = np.histogram(stretched.flatten(), 256, [0, 256])
        cdf = hist.cumsum()
        cdf_normalized = cdf * 255 / cdf[-1]
        equalized = np.interp(stretched.flatten(), bins[:-1], cdf_normalized)
        normalized = equalized.reshape(stretched.shape).astype(np.uint8)
        logger.info("Normalized (equalize): histogram equalization applied")
        
    else:
        raise ValueError(f"Unknown normalization method: {method}")

    return normalized


def normalize_raw_to_uint8(data: np.ndarray) -> np.ndarray:
    """Normalizes raw uint16 → uint8 without calibration.

    Used by Pipeline A (raw baseline). Uses percentile [1, 99] to avoid
    saturation by extreme values.

    Args:
        data: 2D array of uint16 values.

    Returns:
        2D uint8 array.
    """
    pmin, pmax = np.percentile(data, [1, 99])
    clipped = np.clip(data, pmin, pmax)
    normalized = ((clipped - pmin) / (pmax - pmin) * 255.0).astype(np.uint8)
    logger.info(f"Normalized raw data: range [{pmin}, {pmax}] → [0, 255]")
    return normalized


# ---------------------------------------------------------------------------
# Tiling
# ---------------------------------------------------------------------------


def tile_image(
    data: np.ndarray,
    meta: Dict[str, Any],
    tile_size: int = 512,
    overlap: float = 0.5
) -> List[Dict[str, Any]]:
    """Slices an image into overlapping square tiles.

    Args:
        data: 2D source image array.
        meta: Metadata dict with 'transform' and 'bounds'.
        tile_size: Side length of each square tile in pixels.
        overlap: Fractional overlap between adjacent tiles (0.0–0.99).

    Returns:
        List of tile dicts with array, coordinates, and metadata.
    """
    h, w = data.shape
    stride = max(1, int(tile_size * (1 - overlap)))
    transform = meta["transform"]

    tiles: List[Dict[str, Any]] = []
    tile_count = 0
    skipped_count = 0

    for y in range(0, h, stride):
        for x in range(0, w, stride):
            y_end = min(y + tile_size, h)
            x_end = min(x + tile_size, w)

            # Extract tile
            tile = np.zeros((tile_size, tile_size), dtype=data.dtype)
            tile[: y_end - y, : x_end - x] = data[y:y_end, x:x_end]

            # Check for NoData (more than 30% zeros)
            zero_ratio = np.sum(tile == 0) / tile.size
            has_data = zero_ratio < NODATA_THRESHOLD

            if not has_data:
                skipped_count += 1
                continue

            # Calculate geographic bounds
            # Use rasterio transform to convert pixel to geo coordinates
            lon_min, lat_max = xy(transform, x, y)
            lon_max, lat_min = xy(transform, x_end, y_end)

            tile_id = f"row{y//stride}_col{x//stride}"

            tile_dict = {
                "array": tile,
                "tile_id": tile_id,
                "pixel_bbox": [x, y, x_end, y_end],
                "geo_bbox": [lat_min, lon_min, lat_max, lon_max],
                "has_data": has_data,
            }
            tiles.append(tile_dict)
            tile_count += 1

    logger.info(
        f"Generated {tile_count} valid tiles of {tile_size}×{tile_size} "
        f"(skipped {skipped_count} NoData tiles) from image {h}×{w}"
    )
    return tiles


# ---------------------------------------------------------------------------
# Pipeline implementations
# ---------------------------------------------------------------------------


def pipeline_A(
    safe_path: str,
    polarization: str = "vv",
    tile_size: int = 512,
    overlap: float = 0.5,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Pipeline A — Raw Baseline: uint16 DN → normalize [0, 255] → tile.

    No radiometric calibration. Direct min/max stretch of raw DN values.
    Serves as lower reference in benchmark.

    Args:
        safe_path: Path to the .SAFE product directory.
        polarization: Polarization channel ('vv' or 'vh').
        tile_size: Tile side length in pixels.
        overlap: Tile overlap fraction.

    Returns:
        Tuple of (tiles list, pipeline metadata dict).
    """
    start_time = time.perf_counter()
    logger.info("=== Pipeline A: Raw Baseline ===")

    # Load data
    files = find_safe_files(safe_path, polarization)
    data, meta = read_geotiff(files["tiff"])

    # Direct normalization of raw DN
    normalized = normalize_raw_to_uint8(data)

    # Tile
    tiles = tile_image(normalized, meta, tile_size=tile_size, overlap=overlap)

    pipeline_meta = {
        "pipeline": "A",
        "polarization": polarization,
        "tile_size": tile_size,
        "overlap": overlap,
        "num_tiles": len(tiles),
        "processing_time": time.perf_counter() - start_time,
    }

    logger.info(f"Pipeline A completed in {pipeline_meta['processing_time']:.2f}s")
    return tiles, pipeline_meta


def pipeline_B(
    safe_path: str,
    polarization: str = "vv",
    tile_size: int = 512,
    overlap: float = 0.5,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Pipeline B — σ0 calibration → normalize [0, 255] → tile.

    Args:
        safe_path: Path to the .SAFE product directory.
        polarization: Polarization channel ('vv' or 'vh').
        tile_size: Tile side length in pixels.
        overlap: Tile overlap fraction.

    Returns:
        Tuple of (tiles list, pipeline metadata dict).
    """
    start_time = time.perf_counter()
    logger.info("=== Pipeline B: Sigma0 Calibration ===")

    # Load data
    files = find_safe_files(safe_path, polarization)
    data, meta = read_geotiff(files["tiff"])

    # Parse calibration LUT
    cal_lut_2d, cal_lines, cal_pixels = parse_calibration_lut(files["calibration"])
    cal_lut_full = interpolate_lut_to_image(cal_lut_2d, cal_lines, cal_pixels, data.shape)

    # Parse noise LUT if available
    noise_lut_full = None
    if files["noise"]:
        try:
            noise_lut_2d, noise_lines, noise_pixels = parse_noise_lut(files["noise"])
            noise_lut_full = interpolate_lut_to_image(
                noise_lut_2d, noise_lines, noise_pixels, data.shape
            )
        except Exception as e:
            logger.warning(f"Failed to parse noise LUT: {e}")

    # Calibrate
    sigma0 = calibrate_sigma0(data, cal_lut_full, noise_lut_full)

    # Normalize
    normalized = normalize_to_uint8(sigma0, method="linear", db_min=-30.0, db_max=0.0)

    # Tile
    tiles = tile_image(normalized, meta, tile_size=tile_size, overlap=overlap)

    pipeline_meta = {
        "pipeline": "B",
        "polarization": polarization,
        "tile_size": tile_size,
        "overlap": overlap,
        "num_tiles": len(tiles),
        "processing_time": time.perf_counter() - start_time,
    }

    logger.info(f"Pipeline B completed in {pipeline_meta['processing_time']:.2f}s")
    return tiles, pipeline_meta


def pipeline_C(
    safe_path: str,
    polarization: str = "vv",
    tile_size: int = 512,
    overlap: float = 0.5,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Pipeline C — σ0 calibration → Lee filter → normalize [0, 255] → tile.

    Args:
        safe_path: Path to the .SAFE product directory.
        polarization: Polarization channel ('vv' or 'vh').
        tile_size: Tile side length in pixels.
        overlap: Tile overlap fraction.

    Returns:
        Tuple of (tiles list, pipeline metadata dict).
    """
    start_time = time.perf_counter()
    logger.info("=== Pipeline C: Sigma0 + Lee Filter ===")

    # Load data
    files = find_safe_files(safe_path, polarization)
    data, meta = read_geotiff(files["tiff"])

    # Parse calibration LUT
    cal_lut_2d, cal_lines, cal_pixels = parse_calibration_lut(files["calibration"])
    cal_lut_full = interpolate_lut_to_image(cal_lut_2d, cal_lines, cal_pixels, data.shape)

    # Parse noise LUT if available
    noise_lut_full = None
    if files["noise"]:
        try:
            noise_lut_2d, noise_lines, noise_pixels = parse_noise_lut(files["noise"])
            noise_lut_full = interpolate_lut_to_image(
                noise_lut_2d, noise_lines, noise_pixels, data.shape
            )
        except Exception as e:
            logger.warning(f"Failed to parse noise LUT: {e}")

    # Calibrate
    sigma0 = calibrate_sigma0(data, cal_lut_full, noise_lut_full)

    # Despeckle
    filtered = apply_lee_filter(sigma0, kernel_size=5)

    # Normalize
    normalized = normalize_to_uint8(filtered, method="linear", db_min=-30.0, db_max=0.0)

    # Tile
    tiles = tile_image(normalized, meta, tile_size=tile_size, overlap=overlap)

    pipeline_meta = {
        "pipeline": "C",
        "polarization": polarization,
        "tile_size": tile_size,
        "overlap": overlap,
        "num_tiles": len(tiles),
        "processing_time": time.perf_counter() - start_time,
    }

    logger.info(f"Pipeline C completed in {pipeline_meta['processing_time']:.2f}s")
    return tiles, pipeline_meta


def pipeline_D(
    safe_path: str,
    polarization: str = "vv",
    tile_size: int = 512,
    overlap: float = 0.5,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Pipeline D — σ0 → Lee filter → log(dB) → equalize → tile.

    Full ESA-recommended preprocessing chain with histogram equalization.
    Reproduces iVision-MRSSD preprocessing for domain alignment.

    Args:
        safe_path: Path to the .SAFE product directory.
        polarization: Polarization channel ('vv' or 'vh').
        tile_size: Tile side length in pixels.
        overlap: Tile overlap fraction.

    Returns:
        Tuple of (tiles list, pipeline metadata dict).
    """
    start_time = time.perf_counter()
    logger.info("=== Pipeline D: Sigma0 + Lee + Log dB + Equalize ===")

    # Load data
    files = find_safe_files(safe_path, polarization)
    data, meta = read_geotiff(files["tiff"])

    # Parse calibration LUT
    cal_lut_2d, cal_lines, cal_pixels = parse_calibration_lut(files["calibration"])
    cal_lut_full = interpolate_lut_to_image(cal_lut_2d, cal_lines, cal_pixels, data.shape)

    # Parse noise LUT if available
    noise_lut_full = None
    if files["noise"]:
        try:
            noise_lut_2d, noise_lines, noise_pixels = parse_noise_lut(files["noise"])
            noise_lut_full = interpolate_lut_to_image(
                noise_lut_2d, noise_lines, noise_pixels, data.shape
            )
        except Exception as e:
            logger.warning(f"Failed to parse noise LUT: {e}")

    # Calibrate
    sigma0 = calibrate_sigma0(data, cal_lut_full, noise_lut_full)

    # Despeckle
    filtered = apply_lee_filter(sigma0, kernel_size=5)

    # Convert to dB
    db = convert_to_db(filtered)

    # Normalize with histogram equalization
    normalized = normalize_to_uint8(db, method="equalize")

    # Tile
    tiles = tile_image(normalized, meta, tile_size=tile_size, overlap=overlap)

    pipeline_meta = {
        "pipeline": "D",
        "polarization": polarization,
        "tile_size": tile_size,
        "overlap": overlap,
        "num_tiles": len(tiles),
        "processing_time": time.perf_counter() - start_time,
    }

    logger.info(f"Pipeline D completed in {pipeline_meta['processing_time']:.2f}s")
    return tiles, pipeline_meta


# ---------------------------------------------------------------------------
# Pipeline dispatcher
# ---------------------------------------------------------------------------


PIPELINES = {
    "A": pipeline_A,
    "B": pipeline_B,
    "C": pipeline_C,
    "D": pipeline_D,
}


def run_pipeline(
    safe_path: str,
    pipeline_name: str,
    polarization: str = "vv",
    output_dir: Optional[str] = None,
    tile_size: int = 512,
    overlap: float = 0.5,
) -> List[Dict[str, Any]]:
    """Dispatches to the requested preprocessing pipeline.

    Args:
        safe_path: Path to the .SAFE product directory.
        pipeline_name: One of 'A', 'B', 'C', 'D'.
        polarization: Polarization channel ('vv' or 'vh').
        output_dir: Optional directory to save tiles.
        tile_size: Tile side length in pixels.
        overlap: Tile overlap fraction.

    Returns:
        List of tile dicts (without arrays if output_dir is provided).

    Raises:
        ValueError: If pipeline_name is not recognized.
    """
    name = pipeline_name.upper()
    if name not in PIPELINES:
        raise ValueError(
            f"Unknown pipeline '{name}'. Must be one of {list(PIPELINES.keys())}"
        )

    # Run pipeline
    tiles, pipeline_meta = PIPELINES[name](
        safe_path, polarization, tile_size, overlap
    )

    # Save to disk if output directory is provided
    if output_dir is not None:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        scene_id = Path(safe_path).stem.replace(".SAFE", "")
        pipeline_dir = output_path / scene_id / name
        pipeline_dir.mkdir(parents=True, exist_ok=True)

        saved_tiles = []
        for tile_dict in tiles:
            tile_id = f"{scene_id}_{name}_{tile_dict['tile_id']}"
            npy_path = pipeline_dir / f"{tile_id}.npy"

            # Save tile array
            np.save(str(npy_path), tile_dict["array"])

            # Create metadata dict without array (to save RAM)
            saved_tile = {
                "tile_id": tile_id,
                "scene_id": scene_id,
                "pipeline": name,
                "pixel_bbox": tile_dict["pixel_bbox"],
                "geo_bbox": tile_dict["geo_bbox"],
                "has_data": tile_dict["has_data"],
                "npy_path": str(npy_path),
            }
            saved_tiles.append(saved_tile)

        # Save metadata JSON
        metadata_path = pipeline_dir / "metadata.json"
        metadata = {
            "scene_id": scene_id,
            "pipeline": name,
            "polarization": polarization,
            "tile_size": tile_size,
            "overlap": overlap,
            "num_tiles": len(saved_tiles),
            "pipeline_meta": pipeline_meta,
            "tiles": saved_tiles,
        }

        with open(metadata_path, "w") as f:
            import json
            json.dump(metadata, f, indent=2)

        logger.info(f"Saved {len(saved_tiles)} tiles to {pipeline_dir}")
        logger.info(f"Metadata saved to {metadata_path}")

        return saved_tiles

    return tiles


# ---------------------------------------------------------------------------
# Diagnostic functions
# ---------------------------------------------------------------------------


def compute_intensity_histogram(tiles: List[Dict[str, Any]], n_bins: int = 256) -> np.ndarray:
    """Computes aggregated intensity histogram across all tiles.

    Args:
        tiles: List of tile dicts with 'array' field.
        n_bins: Number of histogram bins.

    Returns:
        Normalized histogram array (sum = 1).
    """
    all_pixels = []
    for tile in tiles:
        all_pixels.extend(tile["array"].flatten())

    hist, _ = np.histogram(all_pixels, bins=n_bins, range=(0, 256))
    normalized_hist = hist / hist.sum()
    return normalized_hist


def visualize_pipeline_comparison(
    safe_path: str,
    output_path: str,
    polarization: str = "vv",
    sample_tile_idx: int = 0,
) -> None:
    """Generates a 2×2 figure showing the same tile processed by all 4 pipelines.

    Args:
        safe_path: Path to the .SAFE product directory.
        output_path: Path to save the output PNG.
        polarization: Polarization channel.
        sample_tile_idx: Index of tile to visualize.
    """
    logger.info("Generating pipeline comparison figure...")

    # Run all pipelines
    pipelines_data = {}
    for pipeline_name in ["A", "B", "C", "D"]:
        tiles, _ = run_pipeline(safe_path, pipeline_name, polarization)
        if tiles and sample_tile_idx < len(tiles):
            pipelines_data[pipeline_name] = tiles[sample_tile_idx]["array"]
        else:
            logger.warning(f"No tile {sample_tile_idx} for pipeline {pipeline_name}")

    # Create figure
    fig, axes = plt.subplots(2, 2, figsize=(12, 12))
    axes = axes.flatten()

    pipeline_titles = {
        "A": "Pipeline A: Raw Baseline",
        "B": "Pipeline B: σ0 Calibration",
        "C": "Pipeline C: σ0 + Lee Filter",
        "D": "Pipeline D: σ0 + Lee + dB + Equalize",
    }

    for idx, (pipeline_name, ax) in enumerate(zip(["A", "B", "C", "D"], axes)):
        if pipeline_name in pipelines_data:
            ax.imshow(pipelines_data[pipeline_name], cmap="gray")
            ax.set_title(pipeline_titles[pipeline_name])
        else:
            ax.text(0.5, 0.5, "No data", ha="center", va="center")
            ax.set_title(f"{pipeline_titles[pipeline_name]} (N/A)")
        ax.axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    logger.info(f"Comparison figure saved to {output_path}")
    plt.close()


# ---------------------------------------------------------------------------
# Test function
# ---------------------------------------------------------------------------


def test_with_first_scene() -> None:
    """Tests the preprocessing with the first available .SAFE scene.

    Runs Pipeline D on VV and displays statistics.
    """
    logger.info("=== Testing with first available scene ===")

    # Find first .SAFE directory
    scenes_dir = Path(__file__).parent / "data" / "scenes"
    safe_dirs = list(scenes_dir.glob("*.SAFE"))

    if not safe_dirs:
        logger.error("No .SAFE directories found in phase0/data/scenes/")
        return

    safe_path = str(safe_dirs[0])
    logger.info(f"Using scene: {safe_path}")

    try:
        # Run Pipeline D
        start_time = time.perf_counter()
        tiles, pipeline_meta = pipeline_D(safe_path, polarization="vv")
        total_time = time.perf_counter() - start_time

        # Display statistics
        logger.info("=" * 60)
        logger.info(f"Pipeline D Test Results")
        logger.info(f"Scene: {Path(safe_path).name}")
        logger.info(f"Number of tiles generated: {len(tiles)}")
        logger.info(f"Total processing time: {total_time:.2f}s")
        logger.info(f"Tile size: {pipeline_meta['tile_size']}×{pipeline_meta['tile_size']}")
        logger.info(f"Overlap: {pipeline_meta['overlap']}")

        if tiles:
            sample_tile = tiles[0]["array"]
            logger.info(f"Sample tile value range: [{sample_tile.min()}, {sample_tile.max()}]")
            logger.info(f"Sample tile dtype: {sample_tile.dtype}")
            logger.info(f"Sample tile shape: {sample_tile.shape}")

            # Save 3 example tiles as PNG
            output_dir = Path(__file__).parent / "data" / "results"
            output_dir.mkdir(parents=True, exist_ok=True)

            for i in range(min(3, len(tiles))):
                from PIL import Image
                tile_array = tiles[i]["array"]
                img = Image.fromarray(tile_array)
                output_path = output_dir / f"test_tile_{i}.png"
                img.save(output_path)
                logger.info(f"Saved example tile {i} to {output_path}")

        logger.info("=" * 60)
        logger.info("Test completed successfully!")

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Command-line entry point for preprocessing."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Sentinel-1 GRD SAR Preprocessing Pipeline"
    )
    parser.add_argument(
        "--safe", help="Path to the .SAFE product directory (required unless --test)"
    )
    parser.add_argument(
        "--pipeline",
        default="D",
        choices=["A", "B", "C", "D"],
        help="Preprocessing pipeline to run (default: D)",
    )
    parser.add_argument(
        "--polarization",
        default="vv",
        choices=["vv", "vh"],
        help="Polarization channel (default: vv)",
    )
    parser.add_argument(
        "--tile-size", type=int, default=512, help="Tile size in pixels (default: 512)"
    )
    parser.add_argument(
        "--overlap",
        type=float,
        default=0.5,
        help="Tile overlap fraction (default: 0.5)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory for tiles (default: phase0/data/tiles/)",
    )
    parser.add_argument(
        "--all-pipelines",
        action="store_true",
        help="Run all 4 pipelines and generate comparison",
    )
    parser.add_argument(
        "--visualize",
        action="store_true",
        help="Generate pipeline comparison figure",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run test with first available scene",
    )

    args = parser.parse_args()

    # Handle --test flag (doesn't require --safe)
    if args.test:
        test_with_first_scene()
        return

    # For other operations, --safe is required
    if not args.safe:
        parser.error("--safe is required (use --test for automatic scene detection)")
        return

    if args.all_pipelines:
        # Run all pipelines
        logger.info("Running all 4 pipelines...")
        results_dir = Path(__file__).parent / "data" / "tiles"
        results_dir.mkdir(parents=True, exist_ok=True)

        all_results = {}
        for pipeline_name in ["A", "B", "C", "D"]:
            logger.info(f"Running pipeline {pipeline_name}...")
            tiles = run_pipeline(
                args.safe,
                pipeline_name,
                args.polarization,
                str(results_dir),
                args.tile_size,
                args.overlap,
            )
            all_results[pipeline_name] = tiles

        # Generate comparison figure
        if args.visualize:
            output_path = Path(__file__).parent / "data" / "results" / "pipeline_comparison.png"
            visualize_pipeline_comparison(
                args.safe, str(output_path), args.polarization
            )

        # Display summary
        logger.info("=" * 60)
        logger.info("All Pipelines Summary")
        for pipeline_name, tiles in all_results.items():
            logger.info(f"Pipeline {pipeline_name}: {len(tiles)} tiles")
        logger.info("=" * 60)

        return

    if args.visualize:
        # Generate comparison figure only
        output_path = Path(__file__).parent / "data" / "results" / "pipeline_comparison.png"
        visualize_pipeline_comparison(args.safe, str(output_path), args.polarization)
        return

    # Run single pipeline
    if args.output_dir is None:
        args.output_dir = str(Path(__file__).parent / "data" / "tiles")

    results = run_pipeline(
        args.safe,
        args.pipeline,
        args.polarization,
        args.output_dir,
        args.tile_size,
        args.overlap,
    )

    logger.info(f"Pipeline {args.pipeline} completed. Generated {len(results)} tiles.")


if __name__ == "__main__":
    main()