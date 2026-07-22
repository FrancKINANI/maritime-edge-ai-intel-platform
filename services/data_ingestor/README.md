# Data Ingestor Service

**Purpose**: API interface for searching and downloading Sentinel-1 products from the Copernicus Data Space Ecosystem (CDSE).

## Main Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ingest` | POST | Triggers asynchronous ingestion of a Sentinel-1 product (⚠️ 501 — in development) |
| `/status/{job_id}` | GET | Status of an ingestion job (⚠️ 501 — in development) |
| `/products` | GET | Lists available Sentinel-1 products via CDSE OData API (⚠️ 501 — in development) |
| `/health` | GET | Service health |

> ⚠️ The `/ingest`, `/status`, and `/products` endpoints return `501 Not Implemented`. The CDSE ingestion logic is currently implemented in the Phase 0 scripts (`research/scripts/download_scenes.py`) and will be migrated to this service in a future release.

## Core Functions (shared with Phase 0)

Business logic is shared from `research/scripts/download_scenes.py`:

- `get_cdse_token(username, password)` — Keycloak authentication against CDSE
- `search_sentinel1_products(token, bbox, start, end, max_results)` — OData query with bbox/date/product-type filters
- `download_product(token, product_id, output_dir)` — Streaming download (8 KB chunks) with automatic ZIP extraction

## Authentication

Required environment variables:
- `CDSE_USERNAME` — Copernicus Data Space account email
- `CDSE_PASSWORD` — Associated password

## Coastal Targeting

The scene selection targets the Moroccan coastal band. Before downloading, a GFW AIS coverage pre-check is performed (`check_ais_coverage_before_download()`) to avoid downloading scenes with no exploitable AIS ground truth.

## Local Execution

```bash
uvicorn services.data_ingestor.main:app --host 0.0.0.0 --port 8001
```

## Docker

```bash
docker compose build data-ingestor
docker compose up -d data-ingestor
```

Image: `maritime-intelligence-platform-data-ingestor` — port `:8001`

## Notes

- Downloads use the `zipper.dataspace.copernicus.eu` service with 8 KB streaming to avoid memory issues
- `.SAFE` products are automatically extracted and the ZIP archive removed
- Scene selection targets the Moroccan coastal band (optimized for GFW AIS coverage)
- Built-in pip-audit: 0 vulnerabilities
