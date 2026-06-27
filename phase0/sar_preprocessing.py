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

Design:
    Each preprocessing stage is an independent function that accepts and
    returns numpy arrays. Stages can be composed freely, enabling fair
    benchmarking of different preprocessing strategies.

References:
    - ESA Sentinel-1 Level-1 Product Specification (S1-RS-MDA-52-7441)
    - ESA Radiometric Calibration Technical Note
    - Rasterio documentation (rasterio.readthedocs.io)
"""

import glob
import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import rasterio
from scipy.ndimage import uniform_filter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SAFE product reader helpers
# ---------------------------------------------------------------------------


def find_measurement_tiff(
    safe_path: str, polarization: str = "vv"
) -> str:
    """Locates the measurement GeoTIFF for the requested polarization inside a SAFE product.

    Args:
        safe_path: Path to the .SAFE product directory.
        polarization: Desired polarization channel ('vv' or 'vh').

    Returns:
        Absolute path to the measurement GeoTIFF file.

    Raises:
        FileNotFoundError: If no matching TIFF is found.
    """
    pol = polarization.lower()
    pattern = str(Path(safe_path) / "measurement" / f"*-{pol}-*.tiff")
    matches = glob.glob(pattern)
    if not matches:
        raise FileNotFoundError(
            f"No measurement TIFF found for polarization '{pol}' in {safe_path}"
        )
    logger.info(f"Found measurement TIFF: {matches[0]}")
    return matches[0]


def find_calibration_xml(
    safe_path: str, polarization: str = "vv"
) -> str:
    """Locates the calibration annotation XML for the requested polarization.

    Args:
        safe_path: Path to the .SAFE product directory.
        polarization: Desired polarization channel ('vv' or 'vh').

    Returns:
        Absolute path to the calibration XML file.

    Raises:
        FileNotFoundError: If no matching calibration XML is found.
    """
    pol = polarization.lower()
    pattern = str(
        Path(safe_path) / "annotation" / "calibration" / f"calibration-*-{pol}-*.xml"
    )
    matches = glob.glob(pattern)
    if not matches:
        raise FileNotFoundError(
            f"No calibration XML found for polarization '{pol}' in {safe_path}"
        )
    logger.info(f"Found calibration XML: {matches[0]}")
    return matches[0]


def load_measurement(tiff_path: str) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Reads a Sentinel-1 measurement GeoTIFF and returns the data and profile.

    Args:
        tiff_path: Path to the measurement GeoTIFF.

    Returns:
        Tuple of (2D numpy array of DN values as float64, rasterio profile dict).
    """
    with rasterio.open(tiff_path) as src:
        data = src.read(1).astype(np.float64)
        profile = dict(src.profile)
        logger.info(
            f"Loaded measurement: shape={data.shape}, dtype={src.dtypes[0]}, "
            f"CRS={src.crs}"
        )
    return data, profile


def parse_calibration_lut(calibration_xml_path: str) -> np.ndarray:
    """Extracts the sigmaNought calibration LUT from Sentinel-1 calibration XML.

    The LUT is provided as a sub-sampled vector per line. This function parses
    all calibration vectors and builds a 2D LUT array that can be used for
    pixel-level calibration via bi-linear interpolation.

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
    return lut_2d


# ---------------------------------------------------------------------------
# Atomic preprocessing stages
# ---------------------------------------------------------------------------


def calibrate_sigma0(data: np.ndarray, calibration_lut: np.ndarray) -> np.ndarray:
    """Performs radiometric calibration: DN² / LUT² → σ⁰ (linear power).

    The ESA calibration formula for Sentinel-1 GRD is:
        σ⁰ = DN² / A_σ²

    where A_σ is the sigmaNought calibration LUT value interpolated to each pixel.

    Args:
        data: 2D array of raw digital numbers (float64).
        calibration_lut: 2D calibration LUT array (sub-sampled, will be resized).

    Returns:
        2D array of σ⁰ values in linear power scale.
    """
    from scipy.ndimage import zoom

    # Resize LUT to match data dimensions via bilinear interpolation
    zoom_factors = (
        data.shape[0] / calibration_lut.shape[0],
        data.shape[1] / calibration_lut.shape[1],
    )
    lut_full = zoom(calibration_lut, zoom_factors, order=1)

    # Avoid division by zero
    lut_full = np.where(lut_full == 0, 1e-10, lut_full)

    sigma0 = (data ** 2) / (lut_full ** 2)
    logger.info(
        f"Calibrated to σ⁰: min={sigma0.min():.6f}, max={sigma0.max():.6f}"
    )
    return sigma0


def apply_lee_filter(data: np.ndarray, kernel_size: int = 5) -> np.ndarray:
    """Applies an adaptive Lee speckle filter to reduce SAR multiplicative noise.

    The Lee filter estimates the local mean and variance within a sliding
    window and applies an adaptive weight to balance noise reduction against
    detail preservation.

    Formula:
        filtered = mean + k * (pixel - mean)
        where k = max(0, (var - noise_var)) / max(var, noise_var)

    Args:
        data: 2D array of SAR backscatter values (linear or dB scale).
        kernel_size: Size of the square sliding window (must be odd).

    Returns:
        Despeckled 2D array.

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
    local_var = np.maximum(local_var, 0)  # Numerical stability

    # Estimate noise variance from the Equivalent Number of Looks (ENL)
    # For Sentinel-1 IW GRD, ENL ≈ 4.4 (ESA documentation)
    enl = 4.4
    noise_var = local_mean ** 2 / enl

    # Adaptive weight
    k = np.where(
        local_var > 0,
        np.maximum(0, (local_var - noise_var)) / np.maximum(local_var, 1e-10),
        0,
    )

    filtered = local_mean + k * (data - local_mean)
    logger.info(
        f"Lee filter applied: min={filtered.min():.6f}, max={filtered.max():.6f}"
    )
    return filtered


def convert_to_db(data: np.ndarray) -> np.ndarray:
    """Converts linear power σ⁰ to logarithmic decibel (dB) scale.

    Formula: dB = 10 * log10(σ⁰)

    Values ≤ 0 are clamped to a floor of -50 dB to avoid -inf.

    Args:
        data: 2D array of σ⁰ in linear power scale.

    Returns:
        2D array in dB scale.
    """
    # Clamp to avoid log(0)
    data_safe = np.where(data > 0, data, 1e-10)
    db = 10.0 * np.log10(data_safe)

    # Floor at -50 dB
    db = np.maximum(db, -50.0)
    logger.info(f"Converted to dB: min={db.min():.2f}, max={db.max():.2f}")
    return db


def normalize_to_uint8(
    data: np.ndarray, vmin: float = -30.0, vmax: float = 0.0
) -> np.ndarray:
    """Linearly maps values from [vmin, vmax] to uint8 [0, 255].

    Values outside [vmin, vmax] are clipped.

    Args:
        data: 2D array of values to normalize.
        vmin: Value mapped to 0.
        vmax: Value mapped to 255.

    Returns:
        2D uint8 array.
    """
    clipped = np.clip(data, vmin, vmax)
    normalized = ((clipped - vmin) / (vmax - vmin) * 255.0).astype(np.uint8)
    logger.info(f"Normalized to uint8: range [{vmin}, {vmax}] → [0, 255]")
    return normalized


# ---------------------------------------------------------------------------
# Tiling
# ---------------------------------------------------------------------------


def tile_image(
    data: np.ndarray,
    tile_size: int = 512,
    overlap: float = 0.5,
) -> List[Tuple[np.ndarray, Tuple[int, int, int, int]]]:
    """Slices a 2D image into overlapping square tiles.

    Args:
        data: 2D source image array.
        tile_size: Side length of each square tile in pixels.
        overlap: Fractional overlap between adjacent tiles (0.0–0.99).

    Returns:
        List of (tile_array, (y_start, x_start, y_end, x_end)) tuples.
        Tiles that extend beyond the image are zero-padded.
    """
    h, w = data.shape
    stride = max(1, int(tile_size * (1 - overlap)))

    tiles: List[Tuple[np.ndarray, Tuple[int, int, int, int]]] = []

    for y in range(0, h, stride):
        for x in range(0, w, stride):
            y_end = min(y + tile_size, h)
            x_end = min(x + tile_size, w)

            tile = np.zeros((tile_size, tile_size), dtype=data.dtype)
            tile[: y_end - y, : x_end - x] = data[y:y_end, x:x_end]

            tiles.append((tile, (y, x, y_end, x_end)))

    logger.info(
        f"Generated {len(tiles)} tiles of {tile_size}×{tile_size} "
        f"(stride={stride}) from image {h}×{w}"
    )
    return tiles


def save_tiles(
    tiles: List[Tuple[np.ndarray, Tuple[int, int, int, int]]],
    output_dir: str,
    scene_id: str,
    pipeline_label: str,
    save_png: bool = False,
) -> List[Dict[str, Any]]:
    """Saves tiles to disk as .npy files with optional PNG exports.

    Args:
        tiles: List of (tile_array, bbox) tuples from tile_image().
        output_dir: Directory to save tiles to.
        scene_id: Identifier for the source scene (used in filenames).
        pipeline_label: Pipeline identifier (A, B, C, or D).
        save_png: If True, also saves PNG previews.

    Returns:
        List of metadata dicts for each saved tile.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    metadata_list = []
    for idx, (tile, bbox) in enumerate(tiles):
        tile_id = f"{scene_id}_pipe{pipeline_label}_tile{idx:04d}"
        npy_file = out_path / f"{tile_id}.npy"
        np.save(str(npy_file), tile)

        meta = {
            "tile_id": tile_id,
            "scene_id": scene_id,
            "pipeline": pipeline_label,
            "bbox_pixel": list(bbox),
            "shape": list(tile.shape),
            "npy_path": str(npy_file),
        }

        if save_png:
            from PIL import Image

            png_file = out_path / f"{tile_id}.png"
            img = Image.fromarray(tile)
            img.save(str(png_file))
            meta["png_path"] = str(png_file)

        metadata_list.append(meta)

    logger.info(f"Saved {len(metadata_list)} tiles to {out_path}")
    return metadata_list


# ---------------------------------------------------------------------------
# Pipeline orchestrators
# ---------------------------------------------------------------------------


def _load_safe_data(
    safe_path: str, polarization: str = "vv"
) -> Tuple[np.ndarray, Dict[str, Any], str]:
    """Common loader for all pipelines — reads measurement + scene ID.

    Args:
        safe_path: Path to the .SAFE product directory.
        polarization: Desired polarization channel.

    Returns:
        Tuple of (data array, rasterio profile, scene_id string).
    """
    tiff_path = find_measurement_tiff(safe_path, polarization)
    data, profile = load_measurement(tiff_path)
    scene_id = Path(safe_path).stem.replace(".SAFE", "")
    return data, profile, scene_id


def pipeline_A(
    safe_path: str,
    polarization: str = "vv",
    tile_size: int = 512,
    overlap: float = 0.5,
    output_dir: Optional[str] = None,
    save_png: bool = False,
) -> List[Dict[str, Any]]:
    """Pipeline A — Raw Baseline: uint16 DN → normalize [0, 255] → tile.

    No radiometric calibration. Direct min/max stretch of raw DN values.

    Args:
        safe_path: Path to the .SAFE product directory.
        polarization: Polarization channel ('vv' or 'vh').
        tile_size: Tile side length in pixels.
        overlap: Tile overlap fraction.
        output_dir: Directory for tile output (default: phase0/data/tiles/).
        save_png: Whether to save PNG previews.

    Returns:
        List of tile metadata dicts.
    """
    logger.info("=== Pipeline A: Raw Baseline ===")
    data, profile, scene_id = _load_safe_data(safe_path, polarization)

    # Direct normalization of raw DN
    vmin, vmax = float(np.percentile(data, 1)), float(np.percentile(data, 99))
    normalized = normalize_to_uint8(data, vmin=vmin, vmax=vmax)

    tiles = tile_image(normalized, tile_size=tile_size, overlap=overlap)

    if output_dir is None:
        output_dir = str(Path(__file__).parent / "data" / "tiles")

    return save_tiles(tiles, output_dir, scene_id, "A", save_png=save_png)


def pipeline_B(
    safe_path: str,
    polarization: str = "vv",
    tile_size: int = 512,
    overlap: float = 0.5,
    output_dir: Optional[str] = None,
    save_png: bool = False,
) -> List[Dict[str, Any]]:
    """Pipeline B — σ⁰ calibration → normalize [0, 255] → tile.

    Args:
        safe_path: Path to the .SAFE product directory.
        polarization: Polarization channel ('vv' or 'vh').
        tile_size: Tile side length in pixels.
        overlap: Tile overlap fraction.
        output_dir: Directory for tile output.
        save_png: Whether to save PNG previews.

    Returns:
        List of tile metadata dicts.
    """
    logger.info("=== Pipeline B: Sigma0 Calibration ===")
    data, profile, scene_id = _load_safe_data(safe_path, polarization)

    # Parse calibration LUT from SAFE annotations
    cal_xml = find_calibration_xml(safe_path, polarization)
    cal_lut = parse_calibration_lut(cal_xml)

    # Calibrate
    sigma0 = calibrate_sigma0(data, cal_lut)

    # Convert to dB for normalization range, then uint8
    db = convert_to_db(sigma0)
    normalized = normalize_to_uint8(db, vmin=-30.0, vmax=0.0)

    tiles = tile_image(normalized, tile_size=tile_size, overlap=overlap)

    if output_dir is None:
        output_dir = str(Path(__file__).parent / "data" / "tiles")

    return save_tiles(tiles, output_dir, scene_id, "B", save_png=save_png)


def pipeline_C(
    safe_path: str,
    polarization: str = "vv",
    kernel_size: int = 5,
    tile_size: int = 512,
    overlap: float = 0.5,
    output_dir: Optional[str] = None,
    save_png: bool = False,
) -> List[Dict[str, Any]]:
    """Pipeline C — σ⁰ → Lee 5×5 → normalize [0, 255] → tile.

    Args:
        safe_path: Path to the .SAFE product directory.
        polarization: Polarization channel ('vv' or 'vh').
        kernel_size: Lee filter kernel size (must be odd).
        tile_size: Tile side length in pixels.
        overlap: Tile overlap fraction.
        output_dir: Directory for tile output.
        save_png: Whether to save PNG previews.

    Returns:
        List of tile metadata dicts.
    """
    logger.info("=== Pipeline C: Sigma0 + Lee Filter ===")
    data, profile, scene_id = _load_safe_data(safe_path, polarization)

    cal_xml = find_calibration_xml(safe_path, polarization)
    cal_lut = parse_calibration_lut(cal_xml)

    sigma0 = calibrate_sigma0(data, cal_lut)
    filtered = apply_lee_filter(sigma0, kernel_size=kernel_size)

    db = convert_to_db(filtered)
    normalized = normalize_to_uint8(db, vmin=-30.0, vmax=0.0)

    tiles = tile_image(normalized, tile_size=tile_size, overlap=overlap)

    if output_dir is None:
        output_dir = str(Path(__file__).parent / "data" / "tiles")

    return save_tiles(tiles, output_dir, scene_id, "C", save_png=save_png)


def pipeline_D(
    safe_path: str,
    polarization: str = "vv",
    kernel_size: int = 5,
    tile_size: int = 512,
    overlap: float = 0.5,
    output_dir: Optional[str] = None,
    save_png: bool = False,
) -> List[Dict[str, Any]]:
    """Pipeline D — σ⁰ → Lee 5×5 → log(dB) → normalize [0, 255] → tile.

    This is the recommended pipeline per ESA best practices.
    The dB conversion is applied after speckle filtering to maximize
    the signal-to-noise ratio before quantization.

    Args:
        safe_path: Path to the .SAFE product directory.
        polarization: Polarization channel ('vv' or 'vh').
        kernel_size: Lee filter kernel size (must be odd).
        tile_size: Tile side length in pixels.
        overlap: Tile overlap fraction.
        output_dir: Directory for tile output.
        save_png: Whether to save PNG previews.

    Returns:
        List of tile metadata dicts.
    """
    logger.info("=== Pipeline D: Sigma0 + Lee + Log dB (Recommended) ===")
    data, profile, scene_id = _load_safe_data(safe_path, polarization)

    cal_xml = find_calibration_xml(safe_path, polarization)
    cal_lut = parse_calibration_lut(cal_xml)

    sigma0 = calibrate_sigma0(data, cal_lut)
    filtered = apply_lee_filter(sigma0, kernel_size=kernel_size)
    db = convert_to_db(filtered)
    normalized = normalize_to_uint8(db, vmin=-30.0, vmax=0.0)

    tiles = tile_image(normalized, tile_size=tile_size, overlap=overlap)

    if output_dir is None:
        output_dir = str(Path(__file__).parent / "data" / "tiles")

    return save_tiles(tiles, output_dir, scene_id, "D", save_png=save_png)


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
    pipeline_name: str,
    safe_path: str,
    **kwargs: Any,
) -> List[Dict[str, Any]]:
    """Dispatches to the requested preprocessing pipeline.

    Args:
        pipeline_name: One of 'A', 'B', 'C', 'D'.
        safe_path: Path to the .SAFE product directory.
        **kwargs: Additional arguments forwarded to the pipeline function.

    Returns:
        List of tile metadata dicts.

    Raises:
        ValueError: If pipeline_name is not recognized.
    """
    name = pipeline_name.upper()
    if name not in PIPELINES:
        raise ValueError(
            f"Unknown pipeline '{name}'. Must be one of {list(PIPELINES.keys())}"
        )
    return PIPELINES[name](safe_path, **kwargs)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Command-line entry point for standalone preprocessing."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Sentinel-1 GRD SAR Preprocessing Pipeline"
    )
    parser.add_argument(
        "--safe", required=True, help="Path to the .SAFE product directory"
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
        "--save-png", action="store_true", help="Also save PNG previews of tiles"
    )

    args = parser.parse_args()

    results = run_pipeline(
        pipeline_name=args.pipeline,
        safe_path=args.safe,
        polarization=args.polarization,
        tile_size=args.tile_size,
        overlap=args.overlap,
        output_dir=args.output_dir,
        save_png=args.save_png,
    )

    # Save tile metadata index
    out_dir = args.output_dir or str(Path(__file__).parent / "data" / "tiles")
    index_path = Path(out_dir) / f"tile_index_pipe{args.pipeline}.json"
    with open(index_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Tile index saved to {index_path}")
    logger.info(f"Pipeline {args.pipeline} complete: {len(results)} tiles generated.")


if __name__ == "__main__":
    main()

