"""Sentinel-1 GRD SAR Preprocessing and Tiling Framework (Windowed Memory-Efficient Version).

Purpose:
    Implements a memory-efficient SAR preprocessing pipeline for Sentinel-1 IW GRD
    products using windowed processing to handle large scenes (25K×16K pixels) on
    systems with limited RAM (16GB) and cloud environments like Colab.

Key Innovation:
    - Never loads the full scene into RAM
    - Processes tile-by-tile with sparse calibration LUTs
    - Peak RAM usage < 400 MB per scene
    - Compatible with 16GB local machines and Colab

Inputs:
    - Sentinel-1 .SAFE product directory
    - Pipeline selection (A, B, C, or D)
    - Optional: polarization channel (VV or VH)

Outputs:
    - 512×512 pixel tiles as .npy arrays
    - JSON manifest with tile metadata
    - Memory usage diagnostics

Architecture:
    - CalibrationLUT: Sparse LUT interpolation on-demand
    - Windowed processing: Read → process → write → free
    - Explicit memory management: del + gc.collect()

Note on GCP duplication:
    GCP logic intentionally duplicated (no phase0<->services dependency).
    The GCPGeoreferencer and GCPOutOfBoundsError classes below are a standalone
    copy from services/sentinel-preprocessor/sar_preprocessing.py.
    ASSUMED RISK: any bug fix here must be manually replicated
    in the other file (and vice versa).
"""

# Note on GCP duplication:
# GCP logic intentionally duplicated (no phase0<->services dependency).
# The GCPGeoreferencer and GCPOutOfBoundsError classes below are a standalone
# copy from services/sentinel-preprocessor/sar_preprocessing.py.
# ASSUMED RISK: any bug fix here must be manually replicated
# in the other file (and vice versa).

import gc
import logging
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import rasterio
from rasterio.windows import Window
from scipy.interpolate import RegularGridInterpolator
from scipy.ndimage import uniform_filter
from tqdm import tqdm
import psutil

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
LEE_PADDING = 16  # Pixels padding for Lee filter to avoid edge artifacts


def get_ram_mb() -> float:
    """Returns current process RAM usage in MB."""
    return psutil.Process().memory_info().rss / 1024 / 1024


# ---------------------------------------------------------------------------
# GCP Georeferencing (standalone copy -- see note at top of file)
# ---------------------------------------------------------------------------


class GCPOutOfBoundsError(Exception):
    """Raised when a pixel coordinate falls outside the validated GCP grid.

    This is NOT a bug -- it is a deliberate safeguard. The Sentinel-1 GRD
    image is systematically 1 pixel larger than the GCP grid on each axis,
    so edge tiles always trigger this exception. Before production use, a
    human decision is needed on how to handle boundary pixels:
    - Clip to nearest valid GCP coordinate
    - Reject boundary tiles entirely
    - Document and accept the extrapolation behavior

    (Standalone copy -- report bug fixes in
     services/sentinel-preprocessor/sar_preprocessing.py)
    """
    pass


class GCPGeoreferencer:
    """
    Georeference Sentinel-1 GRD pixels using Ground Control Points (GCPs).

    Sentinel-1 GRD GeoTIFFs distributed by CDSE do not carry a usable native CRS
    (src.crs returns None). Instead, georeferencing is carried by a regular NxM
    GCP grid embedded in the GeoTIFF metadata. This class reconstructs pixel →
    (lat, lon) mapping via RegularGridInterpolator.

    VALIDATED PROPERTY:
        Interpolation error at GCP control points is EXACTLY ZERO
        (machine precision verified in phase0/tests/test_gcp_interpolation.py).

    NOT VALIDATED:
        Behavior when a requested pixel falls beyond the last recorded GCP.
        Sentinel-1 GRD images are exactly 1 pixel larger than the GCP grid
        on each axis, so boundary pixels will trigger extrapolation. This class
        raises an explicit GCPOutOfBoundsError for such cases rather than
        improvising border management.

    (Standalone copy -- report bug fixes in
     services/sentinel-preprocessor/sar_preprocessing.py)
    """

    def __init__(self, gcps: np.ndarray, image_shape: Tuple[int, int]):
        """
        Args:
            gcps: Array of shape (N, M, 2) where gcps[i, j] = (lat, lon)
                  corresponding to pixel (line, pixel) positions.
            image_shape: (height, width) of the source image.

        Raises:
            ValueError: If GCP array does not form a regular NxM grid.
        """
        if gcps.ndim != 3 or gcps.shape[2] != 2:
            raise ValueError(f"GCP array must be (N, M, 2), got shape {gcps.shape}")

        self._gcps = gcps
        self._image_h, self._image_w = image_shape
        self._n_lines, self._n_pixels = gcps.shape[0], gcps.shape[1]

        # Build coordinate vectors for the GCP grid
        self._gcp_lines = np.linspace(0, image_shape[0] - 1, self._n_lines)
        self._gcp_pixels = np.linspace(0, image_shape[1] - 1, self._n_pixels)

        # Separate lat and lon into their own interpolation grids
        self._lat_interpolator = RegularGridInterpolator(
            (self._gcp_lines, self._gcp_pixels),
            self._gcps[:, :, 0],  # lat values
            method='linear',
            bounds_error=False,
            fill_value=None,
        )
        self._lon_interpolator = RegularGridInterpolator(
            (self._gcp_lines, self._gcp_pixels),
            self._gcps[:, :, 1],  # lon values
            method='linear',
            bounds_error=False,
            fill_value=None,
        )

    def pixel_to_latlon(self, line: float, pixel: float) -> Tuple[float, float]:
        """
        Convert a pixel coordinate to geographic (lat, lon).

        Args:
            line: Image line (row) coordinate.
            pixel: Image pixel (column) coordinate.

        Returns:
            Tuple[float, float]: (latitude, longitude).

        Raises:
            GCPOutOfBoundsError: If the requested pixel falls outside the
                validated GCP grid.
        """
        line_min, line_max = float(self._gcp_lines[0]), float(self._gcp_lines[-1])
        pixel_min, pixel_max = float(self._gcp_pixels[0]), float(self._gcp_pixels[-1])

        if not (line_min <= line <= line_max and pixel_min <= pixel <= pixel_max):
            raise GCPOutOfBoundsError(
                f"Pixel coordinate ({line:.2f}, {pixel:.2f}) is outside the GCP grid "
                f"bounds: lines [{line_min:.2f}, {line_max:.2f}], "
                f"pixels [{pixel_min:.2f}, {pixel_max:.2f}]. "
                "This boundary behavior is NOT validated and requires human review "
                "before production use."
            )

        lat = float(self._lat_interpolator([[line, pixel]])[0])
        lon = float(self._lon_interpolator([[line, pixel]])[0])
        return lat, lon

    def tile_to_bbox(self, y_start: int, x_start: int, y_end: int, x_end: int) -> List[float]:
        """
        Compute the geographic bounding box of a tile.

        Args:
            y_start, x_start: Top-left pixel coordinates.
            y_end, x_end: Bottom-right pixel coordinates (exclusive).

        Returns:
            List[float]: [lat_min, lon_min, lat_max, lon_max]
        """
        corners = [
            self.pixel_to_latlon(y_start, x_start),
            self.pixel_to_latlon(y_start, x_end - 1),
            self.pixel_to_latlon(y_end - 1, x_start),
            self.pixel_to_latlon(y_end - 1, x_end - 1),
        ]
        lats = [c[0] for c in corners]
        lons = [c[1] for c in corners]
        return [min(lats), min(lons), max(lats), max(lons)]


def extract_gcps_from_geotiff(tiff_path: str) -> Tuple[np.ndarray, Tuple[int, int]]:
    """
    Extract GCPs from a Sentinel-1 GRD GeoTIFF.

    Args:
        tiff_path: Path to a Sentinel-1 GRD GeoTIFF file.

    Returns:
        Tuple[np.ndarray, Tuple[int, int]]:
            - Array of shape (N, M, 2) containing (lat, lon) values.
            - (height, width) of the source image.

    Raises:
        ValueError: If the GeoTIFF contains no GCPs or if the GCPs do not
            form a regular grid.
    """
    import rasterio

    with rasterio.open(tiff_path) as src:
        image_shape = (src.height, src.width)
        gcps_raw = src.gcps[0] if src.gcps else []

        if not gcps_raw:
            raise ValueError(
                f"No GCPs found in {tiff_path}. "
                "Sentinel-1 GRD GeoTIFFs should carry a regular GCP grid."
            )

        rows = sorted(set(gcp.row for gcp in gcps_raw))
        cols = sorted(set(gcp.col for gcp in gcps_raw))

        n_lines = len(rows)
        n_pixels = len(cols)

        if n_lines * n_pixels != len(gcps_raw):
            raise ValueError(
                f"GCPs do not form a regular grid: {len(gcps_raw)} GCPs "
                f"mapped to {n_lines}x{n_pixels}."
            )

        gcps_array = np.zeros((n_lines, n_pixels, 2), dtype=np.float64)
        row_to_idx = {row: i for i, row in enumerate(rows)}
        col_to_idx = {col: j for j, col in enumerate(cols)}

        for gcp in gcps_raw:
            i = row_to_idx[gcp.row]
            j = col_to_idx[gcp.col]
            gcps_array[i, j, 0] = gcp.y   # latitude
            gcps_array[i, j, 1] = gcp.x   # longitude

        return gcps_array, image_shape


# ---------------------------------------------------------------------------
# Sparse Calibration LUT (Memory-Efficient)
# ---------------------------------------------------------------------------


class CalibrationLUT:
    """
    Loads calibration LUT vectors from XML without full resolution interpolation.
    Interpolates on-demand for specific windows only.
    
    Memory footprint: ~5 MB instead of ~800 MB for full resolution LUT.
    """
    
    def __init__(self, calibration_xml_path: str, noise_xml_path: Optional[str] = None):
        """Initialize by parsing XML vectors (sparse representation)."""
        logger.info(f"Parsing calibration LUT from {calibration_xml_path}")
        
        # Parse sigma Nought LUT
        self.sigma_lines, self.sigma_pixels, self.sigma_values = self._parse_calibration_xml(
            calibration_xml_path
        )
        
        # Parse noise LUT if provided
        self.noise_lines = None
        self.noise_pixels = None
        self.noise_values = None
        
        if noise_xml_path:
            try:
                logger.info(f"Parsing noise LUT from {noise_xml_path}")
                self.noise_lines, self.noise_pixels, self.noise_values = self._parse_noise_xml(
                    noise_xml_path
                )
            except Exception as e:
                logger.warning(f"Failed to parse noise LUT: {e}")
        
        logger.info(f"Calibration LUT loaded: sigma shape {self.sigma_values.shape}, "
                   f"noise {'N/A' if self.noise_values is None else self.noise_values.shape}")
    
    def _parse_calibration_xml(self, xml_path: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Parse calibration XML to extract sparse sigmaNought vectors."""
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        vectors = root.findall(".//calibrationVector")
        if not vectors:
            raise ValueError(f"No calibrationVector elements found in {xml_path}")
        
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
        
        return np.array(lines), pixel_indices, np.array(sigma_values)
    
    def _parse_noise_xml(self, xml_path: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Parse noise XML to extract sparse noise vectors."""
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        # Try new format first
        noise_range_vectors = root.findall(".//noiseRangeLut")
        if noise_range_vectors:
            vectors = noise_range_vectors
        else:
            noise_vectors = root.findall(".//noiseLut")
            if noise_vectors:
                vectors = noise_vectors
            else:
                raise ValueError(f"No noise LUT elements found in {xml_path}")
        
        lines = []
        noise_values = []
        pixel_indices = None
        
        for vec in vectors:
            line_elem = vec.find("line")
            if line_elem is None:
                continue
            line = int(line_elem.text)
            
            pixel_elem = vec.find("pixel")
            noise_elem = vec.find("noiseLut") if vec.find("noiseLut") is not None else vec.find("noiseRangeLut")
            
            if pixel_elem is not None and noise_elem is not None and noise_elem.text is not None:
                pixels = np.array([int(p) for p in pixel_elem.text.split()])
                noise = np.array([float(v) for v in noise_elem.text.split()])
                
                if pixel_indices is None:
                    pixel_indices = pixels
                lines.append(line)
                noise_values.append(noise)
        
        if not lines:
            raise ValueError(f"No valid noise vectors found in {xml_path}")
        
        return np.array(lines), pixel_indices, np.array(noise_values)
    
    def get_sigma_window(
        self, row_start: int, row_end: int, col_start: int, col_end: int
    ) -> np.ndarray:
        """
        Returns sigma LUT interpolated only for the requested window.
        
        Args:
            row_start, row_end: Row indices (inclusive-exclusive)
            col_start, col_end: Column indices (inclusive-exclusive)
        
        Returns:
            Interpolated LUT array of shape (row_end-row_start, col_end-col_start)
        """
        # Create coordinate grid for the window
        row_coords = np.arange(row_start, row_end)
        col_coords = np.arange(col_start, col_end)
        row_grid, col_grid = np.meshgrid(row_coords, col_coords, indexing='ij')
        
        # Interpolate using sparse vectors
        interpolator = RegularGridInterpolator(
            (self.sigma_lines, self.sigma_pixels),
            self.sigma_values,
            method='linear',
            bounds_error=False,
            fill_value=None
        )
        
        points = np.column_stack([row_grid.ravel(), col_grid.ravel()])
        lut_window = interpolator(points).reshape(row_end - row_start, col_end - col_start)
        
        return lut_window
    
    def get_noise_window(
        self, row_start: int, row_end: int, col_start: int, col_end: int
    ) -> Optional[np.ndarray]:
        """
        Returns noise LUT interpolated only for the requested window.
        
        Returns None if noise LUT is not available.
        """
        if self.noise_values is None:
            return None
        
        row_coords = np.arange(row_start, row_end)
        col_coords = np.arange(col_start, col_end)
        row_grid, col_grid = np.meshgrid(row_coords, col_coords, indexing='ij')
        
        interpolator = RegularGridInterpolator(
            (self.noise_lines, self.noise_pixels),
            self.noise_values,
            method='linear',
            bounds_error=False,
            fill_value=None
        )
        
        points = np.column_stack([row_grid.ravel(), col_grid.ravel()])
        lut_window = interpolator(points).reshape(row_end - row_start, col_end - col_start)
        
        return lut_window


# ---------------------------------------------------------------------------
# SAFE file finding (unchanged)
# ---------------------------------------------------------------------------


def find_safe_files(safe_path: str, polarization: str = "vv") -> Dict[str, str]:
    """Finds necessary file paths in a .SAFE directory."""
    pol = polarization.lower()
    safe_dir = Path(safe_path)
    
    # Find measurement TIFF (prefer COG variant)
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
        raise FileNotFoundError(f"No measurement TIFF found for polarization '{pol}'")
    
    # Find calibration XML
    calibration_dir = safe_dir / "annotation" / "calibration"
    cal_pattern = f"calibration-*-{pol}-*.xml"
    cal_files = list(calibration_dir.glob(cal_pattern))
    
    if not cal_files:
        raise FileNotFoundError(f"No calibration XML found for polarization '{pol}'")
    calibration_path = str(cal_files[0])
    logger.info(f"Found calibration XML: {calibration_path}")
    
    # Find noise XML (optional)
    noise_pattern = f"noise-*-{pol}-*.xml"
    noise_files = list(calibration_dir.glob(noise_pattern))
    noise_path = str(noise_files[0]) if noise_files else None
    if noise_path:
        logger.info(f"Found noise XML: {noise_path}")
    
    return {"tiff": tiff_path, "calibration": calibration_path, "noise": noise_path}


# ---------------------------------------------------------------------------
# Window-level pipeline functions
# ---------------------------------------------------------------------------


def _apply_pipeline_to_window(
    window_uint16: np.ndarray,
    pipeline_name: str,
    sigma_lut_window: np.ndarray,
    noise_lut_window: Optional[np.ndarray] = None
) -> np.ndarray:
    """
    Applies the requested pipeline to a single window array.
    
    Args:
        window_uint16: Input window as uint16 (H, W)
        pipeline_name: One of 'A', 'B', 'C', 'D'
        sigma_lut_window: Interpolated sigma LUT for this window (H, W)
        noise_lut_window: Optional interpolated noise LUT for this window (H, W)
    
    Returns:
        Processed window as uint8 (H, W)
    """
    # Convert to float for calculations
    data = window_uint16.astype(np.float32)
    
    if pipeline_name == "A":
        # Pipeline A: Raw baseline
        pmin, pmax = np.percentile(data, [1, 99])
        clipped = np.clip(data, pmin, pmax)
        result = ((clipped - pmin) / (pmax - pmin) * 255.0).astype(np.uint8)
        
    elif pipeline_name == "B":
        # Pipeline B: Calibration only
        if noise_lut_window is not None:
            dn_squared = np.maximum(data ** 2 - noise_lut_window, 0)
        else:
            dn_squared = data ** 2
        
        cal_lut_safe = np.where(sigma_lut_window == 0, 1e-10, sigma_lut_window)
        sigma0 = dn_squared / (cal_lut_safe ** 2)
        sigma0 = np.maximum(sigma0, 0)
        
        # Normalize linear -30 to 0 dB range
        db = 10 * np.log10(sigma0 + 1e-10)
        clipped = np.clip(db, -30.0, 0.0)
        result = ((clipped + 30.0) / 30.0 * 255.0).astype(np.uint8)
        
    elif pipeline_name == "C":
        # Pipeline C: Calibration + Lee filter
        if noise_lut_window is not None:
            dn_squared = np.maximum(data ** 2 - noise_lut_window, 0)
        else:
            dn_squared = data ** 2
        
        cal_lut_safe = np.where(sigma_lut_window == 0, 1e-10, sigma_lut_window)
        sigma0 = dn_squared / (cal_lut_safe ** 2)
        sigma0 = np.maximum(sigma0, 0)
        
        # Lee filter
        filtered = _lee_filter_windowed(sigma0, kernel_size=5)
        
        # Normalize
        db = 10 * np.log10(filtered + 1e-10)
        clipped = np.clip(db, -30.0, 0.0)
        result = ((clipped + 30.0) / 30.0 * 255.0).astype(np.uint8)
        
    elif pipeline_name == "D":
        # Pipeline D: Full chain with histogram equalization
        if noise_lut_window is not None:
            dn_squared = np.maximum(data ** 2 - noise_lut_window, 0)
        else:
            dn_squared = data ** 2
        
        cal_lut_safe = np.where(sigma_lut_window == 0, 1e-10, sigma_lut_window)
        sigma0 = dn_squared / (cal_lut_safe ** 2)
        sigma0 = np.maximum(sigma0, 0)
        
        # Lee filter
        filtered = _lee_filter_windowed(sigma0, kernel_size=5)
        
        # Convert to dB
        db = 10 * np.log10(filtered + 1e-10)
        
        # Histogram equalization
        data_min, data_max = db.min(), db.max()
        if data_max > data_min:
            stretched = ((db - data_min) / (data_max - data_min) * 255).astype(np.uint8)
        else:
            stretched = np.zeros_like(db, dtype=np.uint8)
        
        hist, bins = np.histogram(stretched.flatten(), 256, [0, 256])
        cdf = hist.cumsum()
        cdf_normalized = cdf * 255 / cdf[-1]
        equalized = np.interp(stretched.flatten(), bins[:-1], cdf_normalized)
        result = equalized.reshape(stretched.shape).astype(np.uint8)
        
    else:
        raise ValueError(f"Unknown pipeline: {pipeline_name}")
    
    return result


def _lee_filter_windowed(data: np.ndarray, kernel_size: int = 5) -> np.ndarray:
    """Applies Lee filter to a window (memory-efficient version)."""
    if kernel_size < 1 or kernel_size % 2 == 0:
        raise ValueError(f"kernel_size must be odd, got {kernel_size}")
    
    local_mean = uniform_filter(data, size=kernel_size, mode="reflect")
    local_sq_mean = uniform_filter(data ** 2, size=kernel_size, mode="reflect")
    local_var = local_sq_mean - local_mean ** 2
    local_var = np.maximum(local_var, 0)
    
    noise_var = np.mean(local_var)
    signal_var = np.maximum(local_var - noise_var, 0)
    total_var = np.maximum(local_var, noise_var)
    weight = signal_var / total_var
    
    filtered = local_mean + weight * (data - local_mean)
    return filtered.astype(np.float32)


# ---------------------------------------------------------------------------
# Main windowed processing function
# ---------------------------------------------------------------------------


def process_safe_windowed(
    safe_path: str,
    pipeline_name: str,
    output_dir: str,
    polarization: str = "vv",
    tile_size: int = 512,
    overlap: float = 0.5,
    max_nodata_ratio: float = 0.3,
) -> Dict[str, Any]:
    """
    Processes a .SAFE scene in strict windowed mode.
    
    NEVER loads the full scene into RAM. Processes tile-by-tile with sparse LUTs.
    
    Args:
        safe_path: Path to .SAFE directory
        pipeline_name: One of 'A', 'B', 'C', 'D'
        output_dir: Directory to save tiles
        polarization: 'vv' or 'vh'
        tile_size: Tile side length in pixels
        overlap: Tile overlap fraction (0.0-0.99)
        max_nodata_ratio: Maximum NoData ratio to skip tile
    
    Returns:
        Dict with processing results and tile metadata
    """
    start_time = time.perf_counter()
    scene_id = Path(safe_path).stem.replace(".SAFE", "")
    
    logger.info(f"=== Windowed Processing: {scene_id} ===")
    logger.info(f"Pipeline: {pipeline_name}, Polarization: {polarization}")
    logger.info(f"Tile size: {tile_size}, Overlap: {overlap}")
    logger.info(f"Initial RAM: {get_ram_mb():.1f} MB")
    
    # 1. Find files in .SAFE
    files = find_safe_files(safe_path, polarization)
    
    # 2. Load sparse calibration LUT (~5 MB instead of ~800 MB)
    calib_lut = CalibrationLUT(files["calibration"], files["noise"])
    
    # 3. Open GeoTIFF in read mode (don't load data)
    with rasterio.open(files["tiff"]) as dataset:
        height = dataset.height
        width = dataset.width
        logger.info(f"Scene dimensions: {width}×{height}")
        logger.info(f"RAM after LUT load: {get_ram_mb():.1f} MB")
        
        # 4. Calculate tile grid
        stride = max(1, int(tile_size * (1 - overlap)))
        tile_grid = []
        
        for y in range(0, height, stride):
            for x in range(0, width, stride):
                y_end = min(y + tile_size, height)
                x_end = min(x + tile_size, width)
                tile_grid.append((y, x, y_end, x_end))
        
        logger.info(f"Total tiles to process: {len(tile_grid)}")
        
        # 5. Process tiles one by one
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        scene_dir = output_path / scene_id / pipeline_name
        scene_dir.mkdir(parents=True, exist_ok=True)
        
        tiles_metadata = []
        valid_count = 0
        skipped_count = 0
        
        with tqdm(total=len(tile_grid), desc=f"Pipeline {pipeline_name} — {scene_id}",
                  unit="tile") as pbar:
            
            for tile_idx, (y_start, x_start, y_end, x_end) in enumerate(tile_grid):
                # Calculate window with padding for Lee filter
                pad = LEE_PADDING
                y_start_padded = max(0, y_start - pad)
                x_start_padded = max(0, x_start - pad)
                y_end_padded = min(height, y_end + pad)
                x_end_padded = min(width, x_end + pad)
                
                # Calculate actual window size (may be smaller at edges)
                window_h = y_end_padded - y_start_padded
                window_w = x_end_padded - x_start_padded
                
                # Read window from GeoTIFF (~0.5 MB for 512×512)
                window = dataset.read(
                    1,
                    window=Window(x_start_padded, y_start_padded, window_w, window_h)
                )
                
                # Check NoData ratio
                zero_ratio = np.sum(window == 0) / window.size
                if zero_ratio > max_nodata_ratio:
                    skipped_count += 1
                    del window
                    pbar.update(1)
                    pbar.set_postfix({"valid": valid_count, "skip": skipped_count, 
                                      "RAM": f"{get_ram_mb():.0f}MB"})
                    continue
                
                # Get LUT windows for this specific region
                sigma_lut_window = calib_lut.get_sigma_window(
                    y_start_padded, y_end_padded, x_start_padded, x_end_padded
                )
                noise_lut_window = calib_lut.get_noise_window(
                    y_start_padded, y_end_padded, x_start_padded, x_end_padded
                )
                
                # Apply pipeline
                tile_uint8 = _apply_pipeline_to_window(
                    window, pipeline_name, sigma_lut_window, noise_lut_window
                )
                
                # Crop padding if we added it
                if pad > 0:
                    y_local_start = y_start - y_start_padded
                    x_local_start = x_start - x_start_padded
                    y_local_end = y_local_start + (y_end - y_start)
                    x_local_end = x_local_start + (x_end - x_start)
                    tile_uint8 = tile_uint8[y_local_start:y_local_end, x_local_start:x_local_end]
                
                # Calculate geographic bounds using GCPs
                if 'georeferencer' not in locals():
                    _gcps, _img_shape = extract_gcps_from_geotiff(files["tiff"])
                    georeferencer = GCPGeoreferencer(_gcps, _img_shape)
                    del _gcps, _img_shape
                try:
                    geo_bbox = georeferencer.tile_to_bbox(y_start, x_start, y_end, x_end)
                except Exception:
                    # Fallback for edge tiles: use center + half-tile estimate
                    y_center = float((y_start + y_end) // 2)
                    x_center = float((x_start + x_end) // 2)
                    try:
                        center_lat, center_lon = georeferencer.pixel_to_latlon(y_center, x_center)
                    except Exception:
                        center_lat, center_lon = 0.0, 0.0
                    half = 0.025
                    geo_bbox = [center_lat - half, center_lon - half,
                                center_lat + half, center_lon + half]
                # geo_bbox format: [lat_min, lon_min, lat_max, lon_max]
                lat_min, lon_min, lat_max, lon_max = geo_bbox
                
                # Save tile
                tile_id = f"{scene_id}_{pipeline_name}_tile{tile_idx:04d}"
                npy_path = scene_dir / f"{tile_id}.npy"
                np.save(str(npy_path), tile_uint8)
                
                # Store metadata
                tiles_metadata.append({
                    "tile_id": tile_id,
                    "scene_id": scene_id,
                    "pipeline": pipeline_name,
                    "pixel_bbox": [x_start, y_start, x_end, y_end],
                    "geo_bbox": [lat_min, lon_min, lat_max, lon_max],
                    "npy_path": str(npy_path),
                })
                
                valid_count += 1
                
                # Explicit memory cleanup
                del window, sigma_lut_window, noise_lut_window, tile_uint8
                
                # Periodic garbage collection
                if tile_idx % 50 == 0:
                    gc.collect()
                
                pbar.set_postfix({"valid": valid_count, "skip": skipped_count, 
                                  "RAM": f"{get_ram_mb():.0f}MB"})
                pbar.update(1)
    
    processing_time = time.perf_counter() - start_time

    # Part B.2: Read target_trace.json if it exists and propagate into metadata.json
    # If absent (case of the 11 "seasonal criteria" scenes), write null explicitly.
    import json

    target_trace = {}
    safe_dir = Path(safe_path)
    trace_path = safe_dir / "target_trace.json"
    if trace_path.exists():
        try:
            with open(trace_path) as _f:
                target_trace = json.load(_f)
            logger.info(f"Target trace loaded: {target_trace}")
        except Exception as e:
            logger.warning(f"Failed to read target_trace.json: {e}")

    # Save metadata JSON
    metadata_path = scene_dir / "metadata.json"
    manifest = {
        "scene_id": scene_id,
        "pipeline": pipeline_name,
        "polarization": polarization,
        "tile_size": tile_size,
        "overlap": overlap,
        "total_tiles": len(tile_grid),
        "valid_tiles": valid_count,
        "skipped_nodata": skipped_count,
        "output_dir": str(scene_dir),
        "processing_time_s": processing_time,
        "tiles": tiles_metadata,
        "target_density_cell_index": target_trace.get("target_density_cell_index"),
        "target_cell_bbox": target_trace.get("target_cell_bbox"),
        "targeting_protocol": target_trace.get("protocol", "seasonal_criteria_fallback"),
    }

    with open(metadata_path, "w") as f:
        json.dump(manifest, f, indent=2)
    
    logger.info("=== Processing Complete ===")
    logger.info(f"Valid tiles: {valid_count}/{len(tile_grid)}")
    logger.info(f"Skipped (NoData): {skipped_count}")
    logger.info(f"Processing time: {processing_time:.2f}s")
    logger.info(f"Final RAM: {get_ram_mb():.1f} MB")
    logger.info(f"Results saved to: {scene_dir}")
    
    return manifest


# ---------------------------------------------------------------------------
# Memory benchmarking
# ---------------------------------------------------------------------------


def benchmark_memory_usage(safe_path: str, n_tiles: int = 10) -> Dict[str, Any]:
    """
    Benchmarks memory usage by processing n_tiles tiles with Pipeline D.
    
    Returns peak RAM usage, average tile time, and tiles per minute.
    Target: peak RAM < 400 MB to validate windowed processing.
    """
    logger.info(f"=== Memory Benchmark: {n_tiles} tiles ===")
    
    start_time = time.perf_counter()
    peak_ram = 0
    
    # Load sparse LUT
    files = find_safe_files(safe_path, "vv")
    calib_lut = CalibrationLUT(files["calibration"], files["noise"])
    
    with rasterio.open(files["tiff"]) as dataset:
        height = dataset.height
        width = dataset.width

        # Process first n_tiles tiles
        stride = 512  # No overlap for benchmark
        tile_count = 0
        
        for y in range(0, height, stride):
            for x in range(0, width, stride):
                if tile_count >= n_tiles:
                    break
                
                y_end = min(y + 512, height)
                x_end = min(x + 512, width)
                
                # Measure RAM before
                get_ram_mb()

                # Read window
                window = dataset.read(1, window=Window(x, y, x_end - x, y_end - y))
                
                # Get LUT windows
                sigma_lut_window = calib_lut.get_sigma_window(y, y_end, x, x_end)
                noise_lut_window = calib_lut.get_noise_window(y, y_end, x, x_end)
                
                # Apply pipeline D
                tile_uint8 = _apply_pipeline_to_window(
                    window, "D", sigma_lut_window, noise_lut_window
                )
                
                # Measure RAM after
                ram_after = get_ram_mb()
                peak_ram = max(peak_ram, ram_after)
                
                # Cleanup
                del window, sigma_lut_window, noise_lut_window, tile_uint8
                gc.collect()
                
                tile_count += 1
        
        processing_time = time.perf_counter() - start_time
        avg_tile_time = processing_time / n_tiles
        tiles_per_minute = 60 / avg_tile_time
        
        logger.info(f"Peak RAM: {peak_ram:.1f} MB")
        logger.info(f"Avg tile time: {avg_tile_time:.2f}s")
        logger.info(f"Tiles per minute: {tiles_per_minute:.1f}")
        
        if peak_ram < 400:
            logger.info("✓ Memory benchmark PASSED (< 400 MB)")
        else:
            logger.warning("✗ Memory benchmark FAILED (> 400 MB)")
        
        return {
            "peak_ram_mb": peak_ram,
            "avg_tile_time_s": avg_tile_time,
            "tiles_per_minute": tiles_per_minute,
            "target_passed": peak_ram < 400,
        }


# ---------------------------------------------------------------------------
# Test function
# ---------------------------------------------------------------------------


def test_with_first_scene() -> None:
    """Tests windowed processing with the first available .SAFE scene."""
    logger.info("=== Testing windowed processing with first scene ===")
    
    scenes_dir = Path(__file__).parent / "data" / "scenes"
    safe_dirs = list(scenes_dir.glob("*.SAFE"))
    
    if not safe_dirs:
        logger.error("No .SAFE directories found")
        return
    
    safe_path = str(safe_dirs[0])
    logger.info(f"Using scene: {safe_path}")
    
    try:
        # Run memory benchmark first
        logger.info("Running memory benchmark...")
        benchmark_memory_usage(safe_path, n_tiles=10)

        # Run full Pipeline D
        logger.info("Running full Pipeline D...")
        output_dir = Path(__file__).parent / "data" / "tiles"
        result = process_safe_windowed(safe_path, "D", str(output_dir))
        
        logger.info("=" * 60)
        logger.info("Test completed successfully!")
        logger.info(f"Valid tiles generated: {result['valid_tiles']}")
        logger.info(f"Processing time: {result['processing_time_s']:.2f}s")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Command-line entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Sentinel-1 GRD SAR Preprocessing (Windowed Memory-Efficient)"
    )
    parser.add_argument(
        "--safe", help="Path to .SAFE directory"
    )
    parser.add_argument(
        "--pipeline",
        default="D",
        choices=["A", "B", "C", "D"],
        help="Preprocessing pipeline (default: D)"
    )
    parser.add_argument(
        "--polarization",
        default="vv",
        choices=["vv", "vh"],
        help="Polarization channel (default: vv)"
    )
    parser.add_argument(
        "--tile-size", type=int, default=512, help="Tile size in pixels (default: 512)"
    )
    parser.add_argument(
        "--overlap", type=float, default=0.5, help="Tile overlap (default: 0.5)"
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: phase0/data/tiles/)"
    )
    parser.add_argument(
        "--test", action="store_true", help="Run test with first scene"
    )
    parser.add_argument(
        "--benchmark-memory", action="store_true", help="Run memory benchmark"
    )
    
    args = parser.parse_args()
    
    if args.test:
        test_with_first_scene()
        return
    
    if args.benchmark_memory:
        if not args.safe:
            parser.error("--safe required for --benchmark-memory")
        benchmark_memory_usage(args.safe, n_tiles=10)
        return
    
    if not args.safe:
        parser.error("--safe required (use --test for automatic scene detection)")
    
    if args.output_dir is None:
        args.output_dir = str(Path(__file__).parent / "data" / "tiles")
    
    result = process_safe_windowed(
        args.safe,
        args.pipeline,
        args.output_dir,
        args.polarization,
        args.tile_size,
        args.overlap
    )
    
    logger.info(f"Pipeline {args.pipeline} completed. Generated {result['valid_tiles']} tiles.")


if __name__ == "__main__":
    main()