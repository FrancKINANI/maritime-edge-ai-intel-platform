# services/sentinel-preprocessor/sar_preprocessing.py
"""SAR Image Preprocessing and Tiling Operations.

Exposes calibration, speckle filtering, decibel mapping, normalization,
tiling routines, and GCP-based georeferencing for Sentinel-1 GRD products.
"""

import os
from pathlib import Path
from typing import Any

import numpy as np
from scipy.interpolate import RegularGridInterpolator

# Reuse the robust windowed pipeline implementation from research when available.
try:
    from research.scripts.sar_preprocessing import (
        _lee_filter_windowed,
        process_safe_windowed,
    )

    _HAS_research = True
except Exception:
    _HAS_research = False

# --------------------------------------------------------------------------
# GCP Georeferencing (validated for Sentinel-1 GRD products)
# --------------------------------------------------------------------------


class GCPGeoreferencer:
    """
    Georeference Sentinel-1 GRD pixels using Ground Control Points (GCPs).

    Sentinel-1 GRD GeoTIFFs distributed by CDSE do not carry a usable native CRS
    (src.crs returns None). Instead, georeferencing is carried by a regular NxM
    GCP grid embedded in the GeoTIFF metadata. This class reconstructs pixel →
    (lat, lon) mapping via RegularGridInterpolator.

    VALIDATED PROPERTY:
        Interpolation error at GCP control points is EXACTLY ZERO
        (machine precision verified in research/tests/test_gcp_interpolation.py).

    NOT VALIDATED:
        Behavior when a requested pixel falls beyond the last recorded GCP.
        Sentinel-1 GRD images are exactly 1 pixel larger than the GCP grid
        on each axis, so boundary pixels will trigger extrapolation. This class
        raises an explicit GCPOutOfBoundsError for such cases rather than
        improvising border management.
    """

    def __init__(self, gcps: np.ndarray, image_shape: tuple[int, int]):
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
        # Sentinel-1 GCPs form a regular grid: lines correspond to row indices,
        # pixels to column indices, spaced uniformly across the image.
        self._gcp_lines = np.linspace(0, image_shape[0] - 1, self._n_lines)
        self._gcp_pixels = np.linspace(0, image_shape[1] - 1, self._n_pixels)

        # Separate lat and lon into their own interpolation grids
        self._lat_interpolator = RegularGridInterpolator(
            (self._gcp_lines, self._gcp_pixels),
            self._gcps[:, :, 0],  # lat values
            method="linear",
            bounds_error=False,  # We handle bounds ourselves with explicit check
            fill_value=None,
        )
        self._lon_interpolator = RegularGridInterpolator(
            (self._gcp_lines, self._gcp_pixels),
            self._gcps[:, :, 1],  # lon values
            method="linear",
            bounds_error=False,
            fill_value=None,
        )

    def pixel_to_latlon(self, line: float, pixel: float) -> tuple[float, float]:
        """
        Convert a pixel coordinate to geographic (lat, lon).

        Args:
            line: Image line (row) coordinate.
            pixel: Image pixel (column) coordinate.

        Returns:
            Tuple[float, float]: (latitude, longitude).

        Raises:
            GCPOutOfBoundsError: If the requested pixel falls outside the
                validated GCP grid. This occurs systematically for boundary
                pixels (the image is 1 pixel larger than the GCP grid on
                each axis). This behavior is NOT validated and requires
                human review before production use.
        """
        # Explicit bounds check: strictly within the GCP grid
        line_min, line_max = float(self._gcp_lines[0]), float(self._gcp_lines[-1])
        pixel_min, pixel_max = float(self._gcp_pixels[0]), float(self._gcp_pixels[-1])

        if not (line_min <= line <= line_max and pixel_min <= pixel <= pixel_max):
            raise GCPOutOfBoundsError(
                f"Pixel coordinate ({line:.2f}, {pixel:.2f}) is outside the GCP grid "
                f"bounds: lines [{line_min:.2f}, {line_max:.2f}], "
                f"pixels [{pixel_min:.2f}, {pixel_max:.2f}]. "
                "This boundary behavior is NOT validated and requires human review "
                "before production use. The Sentinel-1 GRD image is exactly 1 pixel "
                "larger than the GCP grid on each axis, so this extrapolation case "
                "occurs systematically for edge tiles."
            )

        lat = float(self._lat_interpolator([[line, pixel]])[0])
        lon = float(self._lon_interpolator([[line, pixel]])[0])
        return lat, lon

    def tile_to_bbox(self, y_start: int, x_start: int, y_end: int, x_end: int) -> list[float]:
        """
        Compute the geographic bounding box of a tile.

        Uses the four corners of the tile. If any corner falls outside the
        GCP grid (which occurs for edge tiles), GCPOutOfBoundsError is raised.

        Args:
            y_start, x_start: Top-left pixel coordinates.
            y_end, x_end: Bottom-right pixel coordinates (exclusive).

        Returns:
            List[float]: [lat_min, lon_min, lat_max, lon_max]
        """
        corners = [
            self.pixel_to_latlon(y_start, x_start),  # top-left
            self.pixel_to_latlon(y_start, x_end - 1),  # top-right
            self.pixel_to_latlon(y_end - 1, x_start),  # bottom-left
            self.pixel_to_latlon(y_end - 1, x_end - 1),  # bottom-right
        ]
        lats = [c[0] for c in corners]
        lons = [c[1] for c in corners]
        return [min(lats), min(lons), max(lats), max(lons)]


class GCPOutOfBoundsError(Exception):
    """Raised when a pixel coordinate falls outside the validated GCP grid.

    This is NOT a bug — it is a deliberate safeguard. The Sentinel-1 GRD
    image is systematically 1 pixel larger than the GCP grid on each axis,
    so edge tiles always trigger this exception. Before production use, a
    human decision is needed on how to handle boundary pixels:
    - Clip to nearest valid GCP coordinate
    - Reject boundary tiles entirely
    - Document and accept the extrapolation behavior
    """

    pass


def extract_gcps_from_geotiff(tiff_path: str) -> tuple[np.ndarray, tuple[int, int]]:
    """
    Extract GCPs from a Sentinel-1 GRD GeoTIFF.

    Args:
        tiff_path: Path to a Sentinel-1 GRD GeoTIFF file.

    Returns:
        Tuple[np.ndarray, Tuple[int, int]]:
            - Array of shape (N, M, 2) containing (lat, lon) values for
              each GCP.
            - (height, width) of the source image.

    Raises:
        ValueError: If the GeoTIFF contains no GCPs or if the GCPs do not
            form a regular grid.
    """
    # rasterio is imported locally rather than at the top level because:
    # 1. This function is only called when processing raw GeoTIFFs (not .npy tiles)
    # 2. The sentinel-preprocessor may run in environments where rasterio
    #    is not installed (e.g., if only serving preprocessed tiles)
    import rasterio

    with rasterio.open(tiff_path) as src:
        image_shape = (src.height, src.width)
        gcps_raw = src.gcps[0] if src.gcps else []

        if not gcps_raw:
            raise ValueError(
                f"No GCPs found in {tiff_path}. "
                "Sentinel-1 GRD GeoTIFFs should carry a regular GCP grid. "
                "This may indicate an incompatible product type."
            )

        # Determine grid dimensions from unique row/col values
        rows = sorted(set(gcp.row for gcp in gcps_raw))
        cols = sorted(set(gcp.col for gcp in gcps_raw))

        n_lines = len(rows)
        n_pixels = len(cols)

        if n_lines * n_pixels != len(gcps_raw):
            raise ValueError(
                f"GCPs do not form a regular grid: {len(gcps_raw)} GCPs "
                f"mapped to {n_lines}x{n_pixels} = {n_lines * n_pixels} expected. "
                "This is unexpected for Sentinel-1 GRD products."
            )

        # Build the NxM array
        gcps_array = np.zeros((n_lines, n_pixels, 2), dtype=np.float64)
        row_to_idx = {row: i for i, row in enumerate(rows)}
        col_to_idx = {col: j for j, col in enumerate(cols)}

        for gcp in gcps_raw:
            i = row_to_idx[gcp.row]
            j = col_to_idx[gcp.col]
            gcps_array[i, j, 0] = gcp.y  # latitude
            gcps_array[i, j, 1] = gcp.x  # longitude

        return gcps_array, image_shape


# --------------------------------------------------------------------------
# SAR Processing Functions
# --------------------------------------------------------------------------


def calibrate_sigma0(data: np.ndarray, calibration_lut: np.ndarray) -> np.ndarray:
    """Simple radiometric calibration: DN^2 / calibration_lut^2

    The full, memory-efficient CalibrationLUT-based interpolation is available
    in `research.scripts.sar_preprocessing.CalibrationLUT`. This function performs
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

    This implementation uses the research windowed version when available for memory
    efficiency on large scenes (25K×16K pixels). Falls back to a simple local-mean
    filter if research is not present.

    Args:
        data: Input SAR array (float32)
        kernel_size: Size of the Lee filter kernel (default 5×5)

    Returns:
        Filtered SAR array (float32)
    """
    if _HAS_research:
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


def tile_image(
    data: np.ndarray, tile_size: int = 512, overlap: float = 0.5
) -> list[tuple[np.ndarray, tuple[int, int, int, int]]]:
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


def pipeline_a(safe_path: str, output_dir: str | None = None) -> dict[str, Any]:
    """Pipeline A: baseline using research implementation when available.
    Returns manifest dictionary with tile metadata.
    """
    if _HAS_research:
        return process_safe_windowed(safe_path, "A", output_dir or "data/tiles")
    raise NotImplementedError("research implementation not available in workspace")


def pipeline_b(safe_path: str, output_dir: str | None = None) -> dict[str, Any]:
    if _HAS_research:
        return process_safe_windowed(safe_path, "B", output_dir or "data/tiles")
    raise NotImplementedError("research implementation not available in workspace")


def pipeline_c(safe_path: str, output_dir: str | None = None) -> dict[str, Any]:
    if _HAS_research:
        return process_safe_windowed(safe_path, "C", output_dir or "data/tiles")
    raise NotImplementedError("research implementation not available in workspace")


def pipeline_d(safe_path: str, output_dir: str | None = None) -> dict[str, Any]:
    if _HAS_research:
        return process_safe_windowed(safe_path, "D", output_dir or "data/tiles")
    raise NotImplementedError("research implementation not available in workspace")


# --------------------------------------------------------------------------
# Security & Input Validation
# --------------------------------------------------------------------------


class SafetyViolationError(Exception):
    """Raised when a file path attempts to escape allowed directories."""

    pass


_ALLOWED_BASE_DIRS = [
    Path("/app/shared"),
    Path("/app/uploads"),
    Path("/data/tiles"),
    Path("/data/scenes"),
]
"""Directories that are considered safe for file access."""


def validate_safe_path(path: str) -> str:
    """
    Validate a file path against path traversal attacks.

    Checks that:
    1. The path does not contain '..' components (after normalization)
    2. The resolved path starts with an allowed base directory
    3. The path is not a system file (/etc/, /proc/, /dev/, /tmp/, /var/)

    Args:
        path: File path to validate.

    Returns:
        The resolved absolute path if safe.

    Raises:
        SafetyViolation: If the path is deemed unsafe.
    """
    if not path:
        raise SafetyViolationError("Empty path is not allowed")

    # Normalize the path to resolve any '..' or '.' components
    resolved = Path(path).resolve()

    # Reject paths with unresolved '..' or traversal patterns
    # (Path.resolve() eliminates these, but we also check the raw path)
    if ".." in path.split(os.sep):
        raise SafetyViolationError(f"Path contains '..' traversal: {path}")

    # Reject system file paths
    system_dirs = ["/etc", "/proc", "/dev", "/tmp", "/var", "/sys", "/boot", "/root"]  # noqa: S108
    for sys_dir in system_dirs:
        if str(resolved).startswith(sys_dir) or path.startswith(sys_dir):
            raise SafetyViolationError(f"Path references system directory: {path}")

    # Check that the resolved path falls within an allowed base directory
    # If the path is relative and doesn't start with /, allow it only if
    # it doesn't contain traversal patterns (already checked above)
    if path.startswith("/"):
        allowed = any(
            str(resolved).startswith(str(base_dir.resolve())) for base_dir in _ALLOWED_BASE_DIRS
        )
        if not allowed:
            raise SafetyViolationError(f"Path is outside allowed directories: {path}")

    return str(resolved)
