# Sentinel Preprocessor Service

**Purpose**: Radiometric calibration, Lee speckle filtering, dB conversion, normalization, `.npy` tiling, and GCP-based georeferencing for Sentinel-1 GRD products.

## Main Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/preprocess` | POST | Runs a SAR preprocessing pipeline (A/B/C/D) on a `.SAFE` product → JSON manifest of generated tiles |
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

## SAR Processing Functions

| Function | Description |
|----------|-------------|
| `calibrate_sigma0(data, lut)` | Radiometric calibration: DN² / LUT² |
| `apply_lee_filter(data, kernel_size=5)` | Adaptive speckle filter (uses phase0 windowed version when available) |
| `convert_to_db(data)` | Logarithmic conversion: 10·log₁₀(x) |
| `normalize_to_uint8(data, db_min, db_max)` | Clip + scale to [0, 255] |
| `tile_image(data, tile_size=512, overlap=0.5)` | Sliding window tiling |

## GCP Georeferencing

The service implements GCP-based georeferencing (`GCPGeoreferencer` class) for Sentinel-1 GRD products. Since CDSE GeoTIFFs do not carry a usable native CRS, georeferencing is reconstructed from the embedded regular NxM GCP grid using `scipy.RegularGridInterpolator`.

- **Validated property**: Interpolation error at GCP control points is EXACTLY ZERO (machine precision).
- **Limitation**: Pixels beyond the last recorded GCP (systematic case: the image is 1 pixel larger than the GCP grid on each axis) trigger an explicit `GCPOutOfBoundsError` rather than unaudited extrapolation.
- **Usage**: `extract_gcps_from_geotiff()` reads GCPs from a Sentinel-1 GeoTIFF, and `tile_to_bbox()` computes a tile's geographic bounding box.

## Dependencies

- `scipy` (RegularGridInterpolator)
- `rasterio` (GeoTIFF reading, locally imported)
- `numpy`

## Local Execution

```bash
uvicorn services.sentinel_preprocessor.main:app --host 0.0.0.0 --port 8000
```

## Example Call

```bash
curl -X POST "http://localhost:8000/preprocess?safe_path=/data/scenes/SCENE.SAFE&pipeline=D"
```

## Output Location

- Default: `phase0/data/tiles/<scene>/<pipeline>/`
- Tiles in `.npy` format (512×512 pixels)

## Docker

```bash
docker compose build sentinel-preprocessor
docker compose up -d sentinel-preprocessor
```

Image: `maritime-intelligence-platform-sentinel-preprocessor` — port `:8000`

## Notes

- 11 unit tests covering calibration, filtering, dB conversion, normalization, and GCP georeferencing
- Multi-stage Docker build with pinned GDAL version (3.8.4+ds-1)
- Built-in pip-audit: 0 vulnerabilities
