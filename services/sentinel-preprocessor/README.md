# Sentinel Preprocessor Service

**Purpose**: Radiometric calibration, Lee speckle filtering, dB conversion, normalization, `.npy` tiling, and GCP-based georeferencing for Sentinel-1 GRD products.

## Main Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/preprocess?safe_path=&pipeline=` | POST | Runs a SAR preprocessing pipeline (A/B/C/D), returns a JSON manifest of generated tiles |
| `/pipelines` | GET | Lists available pipelines with descriptions |
| `/health` | GET | Service health |

## Available Pipelines

| Pipeline | Steps | Usage |
|----------|-------|-------|
| **A** | Raw: direct uint16 → [0,255] normalization | Baseline, no SAR processing |
| **B** | Sigma0: radiometric calibration σ⁰ → norm [0,255] | Radiometric correction only |
| **C** | Sigma0 + Lee: calibration + 5×5 adaptive filter → norm | Speckle reduction |
| **D** | Sigma0 + Lee + Log dB: full chain → norm [0,255] | ESA-recommended chain (provisional) |

> ⚠️ Pipeline D is the provisional default. Phase 0 benchmark is not yet conclusive — do not consider D as final.

## GCP Georeferencing

The service implements GCP-based georeferencing (`GCPGeoreferencer`) for Sentinel-1 GRD products:

- **Validated property**: Interpolation error at GCP control points is EXACTLY ZERO (machine precision).
- **Limitation**: Pixels beyond the last recorded GCP (systematic case: the image is 1 pixel larger than the GCP grid on each axis) trigger an explicit `GCPOutOfBoundsError` rather than unaudited extrapolation.
- **Usage**: `extract_gcps_from_geotiff()` reads GCPs from a Sentinel-1 GeoTIFF, and `tile_to_bbox()` computes a tile's geographic bounding box.

See `sar_preprocessing.py` — classes `GCPGeoreferencer`, `GCPOutOfBoundsError`, function `extract_gcps_from_geotiff()`.

## Dependencies

- `scipy` (RegularGridInterpolator), `rasterio` (GeoTIFF reading), `numpy`.

## Local Execution

```bash
uvicorn services.sentinel_preprocessor.main:app --host 0.0.0.0 --port 8002
```

## Example Call

```bash
curl -X POST "http://localhost:8002/preprocess?safe_path=/data/scenes/SCENE.SAFE&pipeline=D"
```

## Output Location

- Default: `phase0/data/tiles/<scene>/<pipeline>/`
- Tiles in `.npy` format (512×512 pixels).
