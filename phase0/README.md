# Phase 0 — Scientific Validation Framework

> **Maritime Edge AI Platform · Phase II**
> Zero-shot domain transfer from simulated to real Sentinel-1 SAR imagery

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Sentinel-1](https://img.shields.io/badge/Sentinel--1-GRD%20IW-green.svg)](https://sentinels.copernicus.eu/web/sentinel/missions/sentinel-1)
[![CDSE](https://img.shields.io/badge/CDSE-OData%20v1-orange.svg)](https://documentation.dataspace.copernicus.eu/APIs/OData.html)
[![GFW](https://img.shields.io/badge/Global%20Fishing%20Watch-API%20v3-teal.svg)](https://globalfishingwatch.org/our-apis/)

---

## Objective

Phase 0 is the **scientific validation gate** of the Maritime Edge AI Platform. It answers a single critical question:

> *Can the INT8-quantized YOLOv8 vessel detector, trained exclusively on **simulated** SAR imagery (Phase I), achieve acceptable detection performance on **real** Copernicus Sentinel-1 GRD data — without any fine-tuning?*

This is a **zero-shot domain transfer** experiment. The outcome of this phase determines the entire subsequent development trajectory:

| Decision Criterion | Outcome |
|--------------------|---------|
| `mAP@0.5 > 0.70` on ≥ 1 pipeline | ✅ **GO** — Proceed to Phase 1 microservices |
| `mAP@0.5 ∈ [0.50, 0.70]` | ⚠️ **MARGINAL** — Proceed with caution, plan fine-tuning |
| `mAP@0.5 < 0.50` across all pipelines | 🛑 **STOP** — Fine-tuning required before Phase 1 |

---

## Scientific Motivation

The Phase I detector was trained on the **iVision-MRSSD** dataset (simulated C-band SAR imagery). Real Sentinel-1 GRD data differs in:

- **Calibration**: Raw DN values vs. properly calibrated σ⁰ backscatter
- **Speckle noise**: Statistical multiplicative noise requiring adaptive filtering
- **Dynamic range**: Different contrast and intensity distributions
- **Resolution**: Sentinel-1 IW GRD produces 10m/pixel products

The preprocessing pipeline used prior to inference has a direct impact on domain alignment. Four pipelines are benchmarked to quantify this effect.

---

## Preprocessing Pipelines

| Pipeline | Steps | Expected Benefit |
|----------|-------|-----------------|
| **A — Raw Baseline** | `uint16 → norm [0,255]` | No processing overhead |
| **B — Sigma0** | `σ⁰ calibration → norm [0,255]` | Radiometric correction |
| **C — Sigma0 + Lee** | `σ⁰ → Lee 5×5 → norm [0,255]` | Speckle reduction |
| **D — Sigma0 + Lee + Log** ⭐ | `σ⁰ → Lee 5×5 → log(dB) → norm [0,255]` | Full ESA-recommended chain |

Pipeline D is the recommended configuration based on ESA Sentinel-1 Level-1 documentation and remote sensing best practices.

---

## GFW API Integration

The Global Fishing Watch API v3 is used to fetch **AIS vessel presence** data for ground truth annotation seeding.

### Verified Endpoints

| Endpoint | Status | Purpose |
|----------|--------|---------|
| `POST /v3/4wings/report` | ✅ **STATUS 200** — 28,951 entries parsed | AIS vessel presence (Morocco bbox, June 2025) |
| `POST /v3/events` | ✅ **STATUS 200** | Dark vessel events (AIS-off) |
| `GET /v3/vessels/search` | ✅ Format correct (`datasets[0]`) | Vessel search (501 server-side, non-blocking) |

### API v3 Query Format

Based on empirical testing, the GFW `/v3/4wings/report` endpoint requires this split:

```
Query params:
  datasets[0]=public-global-presence:latest
  date-range=YYYY-MM-DD,YYYY-MM-DD
  spatial-resolution=LOW
  temporal-resolution=DAILY
  format=JSON

Body (JSON):
  {"geojson": {...Polygon...}, "limit": 5}
```

### Response Parsing

The API returns a **grouped nested format** — entries are nested inside a dataset-keyed wrapper:

```json
{
  "entries": [{
    "public-global-presence:v4.0": [
      {"lat": 33.8, "lon": -8.9, "mmsi": "255806505", "shipName": "HELENA", ...}
    ]
  }]
}
```

`_normalize_response_entries()` handles 3 formats:
1. **Standard flat**: `{"entries": [{"lat": ...}]}`
2. **Grouped top-level**: `{"dataset_key": [{"lat": ...}]}`
3. **Grouped nested**: `{"entries": [{"dataset_key": [{"lat": ...}]}]}`

---

## Repository Structure

```
phase0/
│
├── README.md                      ← This file
├── requirements.in                ← High-level dependencies (pip-tools)
├── requirements.txt               ← Pinned dependencies
│
├── scripts/
│   ├── download_scenes.py         ← CDSE OData download + GFW coverage check ✅
│   ├── sar_preprocessing.py       ← 4-pipeline SAR preprocessing module ⚙️
│   ├── gfw_annotations.py         ← GFW API v3 AIS fetch + dark vessels ✅
│   └── benchmark_pipeline.py      ← Orchestrator — runs full validation pipeline ⚙️
│
├── tests/
│   ├── test_download_scenes.py    ← Scene ID normalization, duplicates ✅
│   ├── test_gcp_interpolation.py  ← GCP zero-error property + boundary docs ✅
│   └── test_gfw_annotations.py    ← GFW client, AIS presence, retry logic ✅
│
└── data/
    ├── scenes/                    ← Downloaded .SAFE archives (gitignored)
    ├── tiles/                     ← Generated 512×512 .npy tiles (gitignored)
    ├── annotations/               ← Ground truth in YOLO format (gitignored)
    └── results/                   ← Benchmark CSVs, JSON reports, histograms
```

---

## Data Flow

```
CDSE Catalogue (OData v1)
        │
        │  OData search query (bbox, date, IW_GRDH)
        ▼
download_scenes.py
        │  (checks GFW AIS coverage BEFORE downloading — saves bandwidth)
        │  Streams .SAFE archive → extracts to data/scenes/
        ▼
sar_preprocessing.py
        │
        │  Reads .SAFE → applies Pipeline A/B/C/D → exports 512×512 .npy tiles
        ▼
     Detector (YOLOv8 INT8 ONNX)
        │
        │  Runs inference on each tile → list of BoundingBox detections
        ▼
gfw_annotations.py
        │
        │  Fetches historical AIS positions from GFW for the same bbox+timerange
        ▼
benchmark_pipeline.py
        │
        │  Spatial match detections ↔ AIS → compute P/R/mAP@0.5 → classify dark vessels
        ▼
   data/results/
        │  benchmark_report.csv
        │  benchmark_report.json
        └  summary.txt
```

---

## Installation

**Prerequisites:**
- Python 3.12+
- GDAL / rasterio system libraries

```bash
# 1. Clone and enter the repo root
git clone https://github.com/FrancKINANI/maritime-edge-ai-intel-platform.git
cd maritime-edge-ai-intel-platform

# 2. Create and activate a virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# 3. Install Phase 0 dependencies
uv pip install -r phase0/requirements.txt
```

> **GDAL note (Ubuntu/Debian):** If `rasterio` fails to install, first run:
> ```bash
> sudo apt-get install gdal-bin libgdal-dev
> ```

---

## Configuration

All credentials and parameters are injected via environment variables. Copy `.env.example` at the project root and fill in your values:

```bash
cp .env.example .env
# Then edit .env with your credentials
```

**Required variables for Phase 0:**

| Variable | Description | Status |
|----------|-------------|--------|
| `CDSE_USERNAME` | Copernicus Data Space account email | ✅ Verified |
| `CDSE_PASSWORD` | Copernicus Data Space account password | ✅ Verified |
| `GFW_API_TOKEN` | Global Fishing Watch JWT bearer token | ✅ Verified |
| `MOROCCO_BBOX` | Default AOI: `lon_min,lat_min,lon_max,lat_max` | `-17,27,-1,36` |

### API Connectivity Status

Both external APIs have been validated against the live production endpoints:

```
✅ CDSE Auth     → identity.dataspace.copernicus.eu (Keycloak, grant_type=password)
✅ GFW API       → gateway.api.globalfishingwatch.org/v3 (JWT Bearer, API v3)
```

---

## Usage

### Step 1 — Search and Download Sentinel-1 Scenes

```bash
cd phase0
# Test connection
uv run python3 phase0/scripts/download_scenes.py --test

# Full download (coastal targeting, GFW coverage pre-check)
uv run python3 phase0/scripts/download_scenes.py

# Limited download
uv run python3 phase0/scripts/download_scenes.py --max-scenes 5
```

The script reads `CDSE_USERNAME` and `CDSE_PASSWORD` from `.env`, searches the CDSE catalogue for Sentinel-1 IW GRD products over the Moroccan coastline, and streams them to `data/scenes/`. Each `.SAFE` archive (~3 GB) is streamed in 1 MB chunks with a progress bar, then extracted and the zip is removed automatically.

Key feature: **AIS coverage pre-check** — before downloading, the script queries GFW AIS presence for the candidate zone/date. If zero AIS coverage is detected, the scene is skipped (saves bandwidth on non-exploitable candidates).

```
2026-06-27 23:01 [INFO] Requesting authentication token from CDSE...
2026-06-27 23:01 [INFO] Authentication successful.
2026-06-27 23:01 [INFO] Searching Sentinel-1 products from 2024-01-01T00:00:00.000Z...
2026-06-27 23:01 [INFO] Found 2 matching Sentinel-1 products.
2026-06-27 23:01 [INFO] Starting download for product <uuid>...
a3f1bc2d: 100%|████████████████| 2.87G/2.87G [08:43<00:00, 5.48MB/s]
2026-06-27 23:09 [INFO] Extraction complete. Saved to data/scenes/S1A_IW_GRDH_...SAFE
```

### Step 2 — Run Preprocessing

```bash
python3 sar_preprocessing.py --pipeline D --safe data/scenes/S1A_IW_GRDH_...SAFE
```

### Step 3 — Fetch AIS Ground Truth

```bash
python3 gfw_annotations.py \
  --bbox -17 27 -1 36 \
  --start 2024-01-01 \
  --end 2024-01-07
```

### Step 4 — Run Full Benchmark

```bash
python3 benchmark_pipeline.py
```

Outputs are written to `data/results/`.

---

## Module Implementation Status

| Module | Status | Description |
|--------|--------|-------------|
| `download_scenes.py` | ✅ **Complete** | CDSE OData search + streaming download + ZIP extraction + GFW coverage pre-check + coastal targeting |
| `sar_preprocessing.py` | ✅ **Complete** | 4-pipeline SAR preprocessing (A/B/C/D) + GCP georeferencing + unit tests |
| `gfw_annotations.py` | ✅ **Complete** | GFW API v3 AIS fetch + dark vessel events + search vessels + response normalization |
| `benchmark_pipeline.py` | 🔧 In progress | Full orchestration + metrics computation |

---

## Test Suite

**14 tests** covering GFW API, CDSE downloads, and GCP interpolation:

```bash
cd /project/root
pytest phase0/tests/ -v
```

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_gfw_annotations.py` | 9 | GFW client init, AIS presence, dark vessels, response normalization, retry logic, search vessels |
| `test_download_scenes.py` | 3 | Scene base ID normalization (COG variants), duplicate detection |
| `test_gcp_interpolation.py` | 2 | Zero error at GCP control points, boundary behaviour documented |

All tests use mocked HTTP responses and do **not** depend on real API availability.

---

## Walkthrough: `download_scenes.py`

### Architecture

`download_scenes.py` is the entry point of the Phase 0 data acquisition pipeline. It exposes three composable functions:

| Function | Purpose |
|----------|---------|
| `get_cdse_token(username, password)` | Authenticates with CDSE Keycloak (OAuth2 password grant) and returns a short-lived Bearer token |
| `search_sentinel1_products(token, bbox, start, end, max_results)` | Issues an OData query to filter Sentinel-1 IW GRD scenes by spatial intersection and time range |
| `download_product(token, product_id, output_dir)` | Streams the `.SAFE` archive from CDSE's zipper service, renders a `tqdm` progress bar, extracts the archive, and removes the temporary zip |

### Key Design Decisions

- **Coastal targeting**: Before downloading, `check_ais_coverage_before_download()` queries GFW AIS presence. If coverage is zero, the scene is skipped — reducing bandwidth waste on non-exploitable candidates.
- **Streaming downloads**: Sentinel-1 `.SAFE` products are 1–3 GB. Memory-buffered downloads would crash. Each product is streamed in 1 MB chunks directly to disk.
- **Automatic extraction**: The zip is extracted in-place to `data/scenes/` and deleted, keeping the working directory clean and avoiding doubled storage.
- **OData filter**: Uses `contains(Name,'IW_GRDH')` rather than nested `Attributes/` queries for robustness across CDSE catalogue versions.
- **Zero hardcoded credentials**: All secrets are injected via `python-dotenv` and validated at startup.
- **Idempotent downloads**: Before downloading, the `main()` block checks if the `.SAFE` directory already exists and skips gracefully.

### Pipeline Integration

```
benchmark_pipeline.py
    └─ calls get_cdse_token()
    └─ calls search_sentinel1_products()  → list of product metadata
    └─ for each product:
           calls download_product()      → /phase0/data/scenes/<name>.SAFE
           passes SAFE path to sar_preprocessing.py
```

---

## References

- [ESA Sentinel-1 Level-1 Product Definition](https://sentinels.copernicus.eu/documents/247904/1877131/Sentinel-1-Level-1-Product-Definition)
- [CDSE OData API Documentation](https://documentation.dataspace.copernicus.eu/APIs/OData.html)
- [Global Fishing Watch API v3](https://globalfishingwatch.org/our-apis/documentation)
- [Rasterio Documentation](https://rasterio.readthedocs.io/)
- Phase I Repository: [maritime-edge-ai](https://github.com/FrancKINANI/maritime-edge-ai)
