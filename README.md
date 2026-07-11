# Maritime Edge AI Intelligence Platform (Phase II)

[![CI](https://github.com/FrancKINANI/maritime-edge-ai-intel-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/FrancKINANI/maritime-edge-ai-intel-platform/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/Docker-20.10%2B-2496ED.svg)](https://docker.com)

A high-performance microservice platform for **real-time maritime vessel detection** from Copernicus Sentinel-1 SAR satellite imagery. Transitions simulation-trained Edge AI models (Phase I) to a fully operational, containerized architecture consuming real-world radar scenes.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Services](#services)
  - [Data Ingestor](#1-data-ingestor--8001)
  - [Sentinel Preprocessor](#2-sentinel-preprocessor--8000)
  - [Detector](#3-detector--8003)
  - [Satellite Monitor](#4-satellite-monitor--8004)
  - [Aggregator](#5-aggregator--8002)
  - [Ground Dashboard](#6-ground-dashboard--8501)
- [Environment Configuration](#environment-configuration)
- [Development](#development)
- [Testing](#testing)
- [CI/CD](#cicd)
- [API Overview](#api-overview)
- [Phase 0 — Scientific Validation](#phase-0--scientific-validation)
- [Project Structure](#project-structure)
- [Recent Changelog](#recent-changelog)

---

## Overview

This platform ingests **Sentinel-1 GRD** (Ground Range Detected) products from the Copernicus Data Space Ecosystem, applies SAR-specific preprocessing (radiometric calibration, speckle filtering, dB conversion), runs **INT8-quantized YOLOv8** vessel detection via ONNX Runtime, enriches results with **Global Fishing Watch AIS** data and satellite orbital positions, and exposes everything through a **Streamlit dashboard**.

### Key Features

- **Real SAR data**: Ingests real Sentinel-1 IW GRDH scenes (not simulated)
- **4 preprocessing pipelines**: A (raw), B (Sigma0), C (Sigma0+Lee), D (full chain)
- **INT8 quantized detection**: YOLOv8 ONNX with NMS post-processing
- **GCP georeferencing**: Pixel-to-(lat,lon) via RegularGridInterpolator (zero error at control points)
- **AIS ground truth**: GFW API v3 integration for vessel presence and dark vessel detection
- **Satellite tracking**: TLE-based position computation (SatNOGS + Celestrak fallback)
- **Multi-zone classification**: Territorial waters (Z1), EEZ (Z2), High Seas (Z3)
- **3 operational modes**: Upload, Satellite Query, Continuous Monitoring

---

## Architecture

```
                         +-------------------+
                         |  SatNOGS TLE API  |  (primary)
                         +---------+---------+
                                   |           +-------------------+
                                   |           |  Celestrak TLE     |  (fallback)
                                   |           +-------------------+
                                   v
 +------------------+     +--------+--------+
 | Copernicus CDSE  |---->|   data-ingestor  |
 | (Sentinel-1 SAR) |     |    (:8001)       |
 +------------------+     +--------+---------+
                                   |
                                   v
 +------------------+     +--------+---------+
 | Global Fishing   |     | sentinel-         |
 | Watch API v3     |     | preprocessor      |
 | (AIS Presence)   |     |    (:8000)        |
 +--------+---------+     +--------+---------+
          |                        |
          v                        v (512×512 .npy tiles)
 +--------+---------+     +--------+---------+     +-------------------+
 |  satellite-       |     |    detector       |---->|      Redis        |
 |  monitor          |     |  YOLOv8 INT8      |     |  (Shared Cache)   |
 |    (:8004)        |     |    (:8003)        |     +-------------------+
 +-------------------+     +--------+---------+
                                   |
                                   v
 +------------------+     +--------+---------+
 |  GFW API v3      |     |   aggregator      |
 |  (Dark Vessels)  |---->|   (:8002)         |
 +------------------+     |  SQLite/Postgres  |
                          +--------+---------+
                                   |
                                   v
                          +--------+---------+
                          | ground-dashboard  |
                          |   Streamlit       |
                          |    (:8501)        |
                          +-------------------+
```

**Data flow:**

1. **data-ingestor** searches/fetches Sentinel-1 products from CDSE
2. **sentinel-preprocessor** calibrates, filters, tiles, and georeferences to `.npy`
3. **detector** runs ONNX inference on each tile → `DetectionEvent`
4. **satellite-monitor** provides TLE-based satellite positions (used for enrichment)
5. **aggregator** enriches with zone classification + GFW AIS data, persists to DB
6. **ground-dashboard** operator UI: upload, query, monitor

---

## Quick Start

### Prerequisites

- Docker v20.10+
- Docker Compose v2.0+
- Python 3.10+ (for local validation scripts)
- A [Copernicus Data Space](https://dataspace.copernicus.eu/) account (free)
- A [Global Fishing Watch](https://globalfishingwatch.org/) API token (free tier)

### Setup

```bash
# 1. Clone
git clone https://github.com/FrancKINANI/maritime-edge-ai-intel-platform.git
cd maritime-edge-ai-intel-platform

# 2. Configure environment
cp .env.example .env
# Edit .env with your CDSE_USERNAME, CDSE_PASSWORD, GFW_API_TOKEN

# 3. Create data directories
make setup

# 4. Build & start all services
make build
make up
```

All 6 services + Redis start with health checks. The dashboard is available at **http://localhost:8501**.

### Verify Health

```bash
curl http://localhost:8000/health      # sentinel-preprocessor
curl http://localhost:8001/health      # data-ingestor
curl http://localhost:8002/health      # aggregator
curl http://localhost:8003/health      # detector
curl http://localhost:8004/health      # satellite-monitor
```

---

## Services

### 1. Data Ingestor — `:8001`

**Purpose**: API interface for searching and downloading Sentinel-1 products from CDSE.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ingest` | POST | Trigger ingestion (⚠️ 501 — in development) |
| `/status/{job_id}` | GET | Ingestion job status (⚠️ 501 — in development) |
| `/products` | GET | List available Sentinel-1 products (⚠️ 501 — in development) |
| `/health` | GET | Service health |

Business logic is shared from `phase0/scripts/download_scenes.py`.
- Streaming downloads (8 KB chunks, no memory blowup)
- Automatic ZIP extraction and cleanup
- Coastal targeting optimized for GFW AIS coverage

**Docker**: `maritime-intelligence-platform-data-ingestor`

---

### 2. Sentinel Preprocessor — `:8000`

**Purpose**: Radiometric calibration, speckle filtering, dB conversion, tiling, and GCP georeferencing.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/preprocess` | POST | Run SAR pipeline (A/B/C/D) on a `.SAFE` product → JSON tile manifest |
| `/pipelines` | GET | List available pipelines with descriptions |
| `/health` | GET | Service health |

**Pipelines:**

| Pipeline | Steps |
|----------|-------|
| **A** — Raw | `uint16 → normalize [0,255]` |
| **B** — Sigma0 | `σ⁰ calibration → normalize [0,255]` |
| **C** — Sigma0+Lee | `σ⁰ → Lee 5×5 filter → normalize` |
| **D** — Full chain ⭐ | `σ⁰ → Lee 5×5 → log(dB) → normalize [0,255]` |

**GCP Georeferencing** (`GCPGeoreferencer`):
- Reconstructs pixel → (lat, lon) from Sentinel-1's embedded GCP grid
- **Zero error at control points** (machine precision, validated)
- `GCPOutOfBoundsError` for boundary pixels (safe by design)
- `extract_gcps_from_geotiff()` and `tile_to_bbox()` helpers

**Docker**: `maritime-intelligence-platform-sentinel-preprocessor`

---

### 3. Detector — `:8003`

**Purpose**: INT8-quantized YOLOv8 ONNX inference on preprocessed `.npy` tiles.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/detect` | POST | Detect vessels on a tile (file path or base64) → `DetectionEvent` |
| `/health` | GET | Service health + model loading status |

**Detection pipeline:**
1. Load `.npy` tile
2. Float32 conversion + 3-channel stacking + resize to 640px
3. ONNX Runtime CPU inference
4. Confidence threshold (0.25) + NMS (IoU 0.45)
5. Priority heuristic: CRITICAL (≥10), HIGH (≥5), MEDIUM (≥2), LOW

**Models** (place in `shared/models/`):
- `yolov8n_int8.onnx` — vessel detector
- `yolov8n_seg_int8.onnx` — segmenter (not currently used)

**Docker**: `maritime-intelligence-platform-detector`

---

### 4. Satellite Monitor — `:8004`

**Purpose**: TLE caching and SGP4 satellite position computation.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/tle/{norad_id}` | GET | Current TLE for a NORAD ID (cached, TTL configurable) |
| `/position` | GET | Compute lat/lon/altitude at a given timestamp |
| `/refresh-tle` | POST | Clear TLE cache |
| `/health` | GET | Service health |

**TLE sources (fallback chain):**
1. **SatNOGS DB** (primary) — JSON API, most recent TLE used
2. **Celestrak** (fallback) — plain-text TLE format

**Cache**: In-memory, default 24h TTL (`TLE_REFRESH_HOURS`). Stale cache used if both sources unavailable.

**Common NORAD IDs:** Sentinel-1A (39634), Sentinel-1B (41456), ISS (25544)

**Docker**: `maritime-intelligence-platform-satellite-monitor`

---

### 5. Aggregator — `:8002`

**Purpose**: Enrichment, zone classification, GFW AIS matching, event persistence.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/events` | POST | Ingest a detection event (zone auto-computed) → SQLite |
| `/events` | GET | List events with filters (`since`, `zone`, `priority`) |
| `/stats` | GET | Aggregated statistics by zone and priority |
| `/health` | GET | Service health |

**Zone classification:**
| Zone | Radius | Description |
|------|--------|-------------|
| Z1 | ≤ 12 NM | Territorial Waters |
| Z2 | ≤ 200 NM | Exclusive Economic Zone |
| Z3 | > 200 NM | High Seas |

**Database**: SQLite local (`services/aggregator/data/events.db`). Pydantic schemas are DB-agnostic (PostgreSQL-ready).

**Docker**: `maritime-intelligence-platform-aggregator`

---

### 6. Ground Dashboard — `:8501`

**Purpose**: Streamlit web UI with 3 operational modes.

| Mode | Description |
|------|-------------|
| **1. Upload** | Upload `.npy` tiles (direct detection) or `.SAFE`/`.tiff`/`.zip` (preprocess + detect) |
| **2. Satellite Query** | Query satellite position by NORAD ID and timestamp |
| **3. Continuous Monitoring** | Real-time event list with zone/priority/time filters |

**Configuration** (environment variables):
| Variable | Default | Target |
|----------|---------|--------|
| `DETECTOR_URL` | `http://detector:8000` | Detector service |
| `SATMON_URL` | `http://satellite-monitor:8000` | Satellite Monitor |
| `AGGREGATOR_URL` | `http://aggregator:8002` | Aggregator |
| `PREPROCESSOR_URL` | `http://sentinel-preprocessor:8000` | Preprocessor |

**Docker**: `maritime-intelligence-platform-ground-dashboard`

---

## Environment Configuration

Copy `.env.example` to `.env` and fill in:

| Variable | Required | Description |
|----------|----------|-------------|
| `CDSE_USERNAME` | ✅ Yes | Copernicus Data Space account email |
| `CDSE_PASSWORD` | ✅ Yes | Copernicus Data Space account password |
| `GFW_API_TOKEN` | ⚠️ For GFW features | Global Fishing Watch JWT bearer token |

Optional region overrides: `ALGERIA_MED_BBOX`, `MAURITANIA_ATL_BBOX`, etc.

---

## Development

### Local Python Setup

```bash
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r phase0/requirements.txt
```

### Linting

```bash
uv run ruff check services/ phase0/ shared/
```

### Docker Commands

```bash
make build    # Rebuild all Docker images
make up       # Start all services (detached)
make down     # Stop all services
make logs     # Follow logs
make clean    # Clean generated tiles/scenes/results
```

---

## Testing

**36 unit tests** across 3 test suites:

```bash
# Run all tests
uv run python3 -m pytest phase0/tests/ services/aggregator/tests/ services/sentinel-preprocessor/tests/ -v

# Run specific suites
uv run python3 -m pytest phase0/tests/                          # GFW + GCP + download tests
uv run python3 -m pytest services/aggregator/tests/              # Zone classification tests
uv run python3 -m pytest services/sentinel-preprocessor/tests/   # SAR preprocessing + GCP tests
```

### Test Coverage

| Module | Tests | Description |
|--------|-------|-------------|
| `phase0/tests/test_gfw_annotations.py` | 9 | GFW API client, AIS presence, dark vessels, normalized entries, retry logic |
| `phase0/tests/test_download_scenes.py` | 3 | Scene base ID normalization, duplicate detection |
| `phase0/tests/test_gcp_interpolation.py` | 2 | GCP zero-error property, boundary behavior (not validated) |
| `services/sentinel-preprocessor/tests/` | 11 | Calibration, Lee filter, dB conversion, normalization, GCP georeferencer |
| `services/aggregator/tests/` | 7 | Zone classification (Z1/Z2/Z3, edges, invalid) |

### Security

```bash
# pip-audit on all services — 0 vulnerabilities
docker run --rm maritime-intelligence-platform-aggregator sh -c "pip install pip-audit -q && pip-audit -r /app/requirements.txt"
```

---

## CI/CD

GitHub Actions workflow (`.github/workflows/ci.yml`) with 3 jobs:

| Job | Check | Status |
|-----|-------|--------|
| `lint` | `ruff check services/ phase0/ shared/` | ✅ |
| `structure` | Verify all service directories and config files exist | ✅ |
| `tests` | `pytest` on all 3 test suites (36 tests) | ✅ |

---

## API Overview

### External APIs

| API | Endpoint | Auth | Purpose |
|-----|----------|------|---------|
| **CDSE OData** | `https://catalogue.dataspace.copernicus.eu/odata/v1/` | Keycloak JWT | Search & download Sentinel-1 products |
| **CDSE Zipper** | `https://zipper.dataspace.copernicus.eu/gh/...` | Bearer token | Streaming ZIP download |
| **GFW v3** | `https://gateway.api.globalfishingwatch.org/v3/` | JWT Bearer | AIS vessel presence & dark vessel events |
| **SatNOGS** | `https://db.satnogs.org/api/tle/` | Public | TLE satellite orbital data |
| **Celestrak** | `https://celestrak.org/NORAD/elements/gp.php` | Public | TLE fallback |

### GFW API v3 Integration Notes

Based on empirical validation, the GFW `/v3/4wings/report` endpoint requires:

| Parameter | Placement | Format |
|-----------|-----------|--------|
| `datasets[0]` | Query | `public-global-presence:latest` |
| `date-range` | Query | `YYYY-MM-DD,YYYY-MM-DD` |
| `spatial-resolution` | Query | `LOW` or `HIGH` |
| `temporal-resolution` | Query | `DAILY` or `HOURLY` |
| `format` | Query | `JSON` |
| `geojson` | Body | GeoJSON Polygon |
| `limit` | Body | Integer |

The response uses a **grouped nested format**:
```json
{
  "entries": [{
    "public-global-presence:v4.0": [
      {"lat": ..., "lon": ..., "mmsi": "...", "shipName": "...", ...}
    ]
  }]
}
```

---

## Phase 0 — Scientific Validation

The **Phase 0** validation framework (in `phase0/`) benchmarks 4 preprocessing pipelines against real Sentinel-1 data using GFW AIS as ground truth.

**Key question:** *Can an INT8-quantized YOLOv8 detector trained on simulated SAR imagery achieve acceptable performance on real Sentinel-1 data — without fine-tuning?*

See the [Phase 0 README](./phase0/README.md) for full details on:
- CDSE scene download and selection
- 4-pipeline preprocessing (A/B/C/D)
- GFW AIS annotation seeding
- Benchmark metrics (mAP@0.5, mAP@0.5:0.95)

---

## Project Structure

```
.
├── README.md                           ← This file
├── docker-compose.yml                  ← Production compose (6 services + Redis)
├── docker-compose.demo.yml             ← Demo compose (3 services)
├── .github/workflows/ci.yml            ← CI: lint + structure + tests
├── Makefile                            ─ setup, build, up, down, logs, clean
├── .env.example                        ─ Environment template
│
├── shared/
│   ├── config/constants.py             ─ Shared constants (zones, models, SAR params)
│   └── schemas/events.py               ─ Pydantic schemas (DetectionEvent, etc.)
│
├── phase0/
│   ├── scripts/                        ─ download_scenes.py, sar_preprocessing.py,
│   │                                     gfw_annotations.py, benchmark_pipeline.py
│   ├── tests/                          ─ test suites for all phase0 modules
│   └── notebooks/                      ─ Colab notebooks for full pipeline
│
└── services/
    ├── data-ingestor/                  ─ CDSE ingestion (:8001)
    ├── sentinel-preprocessor/          ─ SAR preprocessing (:8000)
    ├── detector/                       ─ YOLOv8 ONNX inference (:8003)
    ├── satellite-monitor/              ─ TLE/SGP4 satellite tracking (:8004)
    ├── aggregator/                     ─ Event enrichment + persistence (:8002)
    └── ground-dashboard/               ─ Streamlit UI (:8501)
```

---

## Recent Changelog

### July 2026

- **GFW API v3 compliance**: Fixed `datasets[0]` bracket notation (query params), `spatial-resolution`/`temporal-resolution`/`format` as query params, `limit`/`geojson` as body params
- **Response parsing**: `_normalize_response_entries()` supports grouped nested format `{entries: [{dataset_key: [{vessel}]}]}`
- **CI improvements**: Added `tests` job with 36 unit tests; fixed phase0 dependency installation
- **Deprecation fixes**: Pydantic `min_items` → `min_length`; FastAPI `on_event` → `lifespan` context manager
- **Streamlit compatibility**: Updated `st.number_input` API (`min` → `min_value`, `max` → `max_value`)
- **GCP test fix**: Tests now use actual `_gcp_lines/_gcp_pixels` from the georeferencer (avoids `np.linspace` mismatch)
- **Docker build**: 6 images built and published; `pip-audit` — 0 vulnerabilities across all services
- **Satellite-monitor**: Explicit warning log when SatNOGS returns empty (`[]`) for Sentinel-1A
