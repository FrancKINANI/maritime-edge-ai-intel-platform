# Maritime Edge AI Intelligence Platform (Phase II)

[![CI](https://github.com/FrancKINANI/maritime-edge-ai-intel-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/FrancKINANI/maritime-edge-ai-intel-platform/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/Docker-20.10%2B-2496ED.svg)](https://docker.com)

A high-performance microservice platform for **real-time maritime vessel detection** from Copernicus Sentinel-1 SAR satellite imagery. Transitions simulation-trained Edge AI models (Phase I) to a fully operational, containerized architecture consuming real-world radar scenes.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Services](#services)
- [Docker](#docker)
- [Environment Configuration](#environment-configuration)
- [Development](#development)
- [Testing](#testing)
- [CI/CD](#cicd)
- [Makefile](#makefile)
- [Project Structure](#project-structure)

---

## Overview

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
          v                        v (512x512 .npy tiles)
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
- Python 3.11+ (for local validation scripts)
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

### Docker Compose Demo

A standalone demo compose file is also available for quick evaluation:

```bash
docker compose -f docker-compose.demo.yml up --build
```

---

## Services

### 1. Data Ingestor — `:8001`

**Purpose**: API interface for searching and downloading Sentinel-1 products from CDSE.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ingest` | POST | Trigger ingestion (501 - in development) |
| `/status/{job_id}` | GET | Ingestion job status (501 - in development) |
| `/products` | GET | List available Sentinel-1 products (501 - in development) |
| `/health` | GET | Service health |

**Image**: `maritime-intelligence-platform-data-ingestor`

---

### 2. Sentinel Preprocessor — `:8000`

**Purpose**: Radiometric calibration, speckle filtering, dB conversion, tiling, and GCP georeferencing.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/preprocess` | POST | Run SAR pipeline (A/B/C/D) on a `.SAFE` product |
| `/pipelines` | GET | List available pipelines with descriptions |
| `/health` | GET | Service health |

**Pipelines:** A (Raw), B (Sigma0), C (Sigma0+Lee), D (Full chain - default)

**Image**: `maritime-intelligence-platform-sentinel-preprocessor`

---

### 3. Detector — `:8003`

**Purpose**: INT8-quantized YOLOv8 ONNX inference on preprocessed `.npy` tiles.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/detect` | POST | Detect vessels on a tile (file path or base64) |
| `/health` | GET | Service health + model loading status |

**Detection pipeline:** Load → Preprocess → ONNX inference → NMS → Priority heuristic

**Image**: `maritime-intelligence-platform-detector`

---

### 4. Satellite Monitor — `:8004`

**Purpose**: TLE caching and SGP4 satellite position computation.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/tle/{norad_id}` | GET | Current TLE for a NORAD ID (cached, 24h TTL) |
| `/position` | GET | Compute lat/lon/altitude at a given timestamp |
| `/refresh-tle` | POST | Clear TLE cache |
| `/health` | GET | Service health |

**TLE sources:** SatNOGS DB (primary) → Celestrak (fallback) → Stale cache (graceful)

**Common NORAD IDs:** Sentinel-1A (39634), Sentinel-1B (41456), ISS (25544)

**Image**: `maritime-intelligence-platform-satellite-monitor`

---

### 5. Aggregator — `:8002`

**Purpose**: Enrichment, zone classification, GFW AIS matching, event persistence.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/events` | POST | Ingest a detection event (zone auto-computed) |
| `/events` | GET | List events with filters (`since`, `zone`, `priority`) |
| `/stats` | GET | Aggregated statistics by zone and priority |
| `/health` | GET | Service health |

**Zone classification:** Z1 (12NM), Z2 (200NM), Z3 (High Seas)

**Image**: `maritime-intelligence-platform-aggregator`

---

### 6. Ground Dashboard — `:8501`

**Purpose**: Streamlit web UI with 3 operational modes.

| Mode | Description |
|------|-------------|
| **1. Upload** | Upload `.npy` tiles or `.SAFE`/.tiff products |
| **2. Satellite Query** | Query satellite position by NORAD ID |
| **3. Continuous Monitoring** | Real-time event list with filters |

**Image**: `maritime-intelligence-platform-ground-dashboard`

---

## Docker

### Base Image

All services use a shared base image (`maritime-intel-base:latest`) defined in `docker/base/Dockerfile`:

| Package | Version | Purpose |
|---------|---------|---------|
| Python | 3.11-slim | Runtime |
| FastAPI | >=0.110.0 | REST API framework |
| Uvicorn | >=0.29.0 | ASGI server |
| Pydantic | >=2.7.0 | Schema validation |
| httpx | >=0.28.0 | Async HTTP client |
| NumPy | >=1.26.0 | Array operations |

### Duplication Elimination

All 6 service Dockerfiles have been refactored to `FROM maritime-intel-base:latest`, eliminating duplicated system package installations and Python dependencies. The base image is built once and cached for all services.

### Docker Compose

The main `docker-compose.yml` defines 7 services (6 microservices + Redis) with:
- **Project-root build context** — all Dockerfiles use `context: .` + `dockerfile: services/<name>/Dockerfile`
- **Healthchecks** — each service has a `/health` endpoint check
- **Shared volumes** — `tiles-volume`, `scenes-volume` for data exchange
- **Dependency ordering** — services wait for Redis to be healthy before starting

```bash
# Build specific service
docker compose build data-ingestor

# Run all services
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

### Building Individual Services

```bash
# Build base image first
docker build -f docker/base/Dockerfile -t maritime-intel-base:latest .

# Then build all services
docker compose build
```

---

## Environment Configuration

Copy `.env.example` to `.env` and fill in:

| Variable | Required | Description |
|----------|----------|-------------|
| `CDSE_USERNAME` | Yes | Copernicus Data Space account email |
| `CDSE_PASSWORD` | Yes | Copernicus Data Space account password |
| `GFW_API_TOKEN` | For GFW features | Global Fishing Watch JWT bearer token |

Optional region overrides: `ALGERIA_MED_BBOX`, `MAURITANIA_ATL_BBOX`, etc.

---

## Development

### Local Python Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
# or with uv:
uv venv && source .venv/bin/activate
pip install -r research/requirements.txt
```

### Linting & SAST

```bash
make lint   # ruff check services/ research/ shared/
make sast   # bandit security scan
```

### Docker Commands

```bash
make build    # Rebuild all Docker images
make up       # Start all services (detached)
make down     # Stop all services
make logs     # Follow logs
make clean    # Clean generated tiles/scenes/results + coverage
```

---

## Testing

**111 tests** across service tests, integration tests, research tests, and dashboard tests:

```bash
# Run all tests
make test-all

# Run specific suites
make test-services      # 43 service tests
make test-integration   # 9 integration tests (4 skipped for missing deps)
make test-dashboard     # 6 ground dashboard tests
```

### Test Organization

```
shared/tests/                    # 21 tests — Pydantic schemas (BoundingBox, DetectionEvent, etc.)
services/data-ingestor/tests/   # 13 tests — FastAPI endpoints + sentinel fetcher
services/aggregator/tests/      # 8 tests — Zone classification
services/detector/tests/        # 7 tests — NMS, xywh2xyxy
services/satellite-monitor/tests/  # 2 tests — TLE fallback
services/sentinel-preprocessor/tests/ # 13 tests — SAR preprocessing, GCP georeferencing
tests/integration/              # 13 tests — End-to-end pipeline, security (4 skipped)
tests/ground_dashboard/          # 6 tests — Dashboard utility functions
```

### Test Suites Details

| Suite | Tests | Description |
|-------|-------|-------------|
| `shared/tests/` | 21 | BoundingBox, DetectionEvent, IngestRequest, TLEData schemas |
| `services/data-ingestor/tests/` | 13 | `/health`, `/ingest`, credential resolution |
| `services/aggregator/tests/` | 8 | Zone classification (Z1/Z2/Z3, edges, invalid) |
| `services/detector/tests/` | 7 | NMS, xywh2xyxy converison |
| `services/satellite-monitor/tests/` | 2 | SatNOGS + Celestrak fallback |
| `services/sentinel-preprocessor/tests/` | 13 | Calibration, Lee filter, dB, GCP georeferencer |
| `tests/integration/` | 9+4 skipped | Data flow, schema, TLE delegation, security |
| `tests/ground_dashboard/` | 6 | URL formatting, BBox validation, mode parsing |

### Coverage

```bash
make test-coverage   # Generates HTML report, requires 60% minimum
```

Reports are written to `coverage_html/`.

---

## CI/CD

GitHub Actions workflow (`.github/workflows/ci.yml`) with 4 job stages:

| Job | Checks | Status |
|-----|--------|--------|
| `lint-and-sast` | Ruff + Bandit SAST scan | ✅ |
| `structure` | Verify all service directories exist | ✅ |
| `tests` | Matrix across 9 test directories | ✅ |
| `coverage-check` | Verify minimum 60% coverage (non-blocking) | ✅ |

The test matrix runs each suite independently to avoid module path collisions from hyphens in service directory names.

---

## Makefile

```bash
make setup              # Create data directories
make build              # Docker compose build
make up                 # Docker compose up -d
make down               # Docker compose down
make logs               # Docker compose logs -f
make test-all           # Run all test suites
make test-services      # Service tests only
make test-integration   # Integration tests
make test-dashboard     # Dashboard tests
make test-coverage      # Tests with coverage report
make lint               # Ruff check
make sast               # Bandit security scan
make clean              # Clean build artifacts + coverage
```

---

## Project Structure

```
.
├── README.md
├── docker-compose.yml              # Production compose (7 services)
├── docker-compose.demo.yml         # Demo compose with base image build
├── .github/workflows/ci.yml        # CI: lint + SAST + test matrix + coverage
├── Makefile                        # Build, test, lint, sast targets
├── pytest.ini                      # Pytest configuration
├── .env.example                    # Environment template
│
├── docker/
│   └── base/                       # Base image (maritime-intel-base:latest)
│       ├── Dockerfile              #   Multi-stage with shared Python deps
│       └── requirements.txt        #   FastAPI, Pydantic, httpx, NumPy
│
├── shared/                         # Common code for all services
│   ├── __init__.py
│   ├── config/                     #   Shared constants & secrets validation
│   ├── schemas/                    #   Pydantic schemas (DetectionEvent, etc.)
│   ├── models/                     #   ONNX model files (gitignored)
│   └── tests/                      #   Schema unit tests (21 tests)
│
├── research/                       # Research & scientific validation
│   ├── scripts/                    #   CDSE download, SAR preprocessing, GFW, benchmark
│   ├── tests/                      #   Research test suites
│   └── notebooks/                  #   Colab pipeline notebooks
│
├── services/                       # Microservices
│   ├── data_ingestor/              #   CDSE ingestion (:8001)
│   ├── sentinel_preprocessor/      #   SAR preprocessing (:8000)
│   ├── detector/                   #   YOLOv8 ONNX inference (:8003)
│   ├── satellite_monitor/          #   TLE/SGP4 satellite tracking (:8004)
│   ├── aggregator/                 #   Event enrichment + persistence (:8002)
│   └── ground_dashboard/           #   Streamlit UI (:8501)
│
├── tests/                          # Cross-service test suites
│   └── integration/                #   End-to-end + security tests
│
├── docs/                           # Documentation
│   ├── pdf/                        #   Research papers & reports
│   ├── docx/                       #   Word documents
│   ├── pics/                       #   Architecture diagrams
│   └── QA.md                       #   GFW data QA analysis
│
└── docker-compose.yml              # Production compose (7 services)
```
