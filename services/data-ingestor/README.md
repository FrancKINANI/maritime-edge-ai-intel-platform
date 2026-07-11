# Data Ingestor Service

**Purpose**: API interface for searching and downloading Sentinel-1 products from the Copernicus Data Space Ecosystem (CDSE).

## Main Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ingest` | POST | Triggers asynchronous ingestion of a Sentinel-1 product (⚠️ not implemented — 501) |
| `/status/{job_id}` | GET | Status of an ingestion job (⚠️ not implemented — 501) |
| `/products?bbox=&date_start=&date_end=` | GET | Lists available Sentinel-1 products via CDSE OData API (⚠️ not implemented — 501) |
| `/health` | GET | Service health |

## Core Functions (Phase 0, shared)

Business logic is shared from `phase0/scripts/download_scenes.py`:
- `get_cdse_token()` — Keycloak authentication against CDSE.
- `search_sentinel1_products()` — OData query with bbox/date/product-type filters.
- `download_product()` — Streaming download (8 KB chunks) with automatic ZIP extraction.

## Authentication

Required environment variables:
- `CDSE_USERNAME` — Copernicus Data Space account email
- `CDSE_PASSWORD` — Associated password

## Local Execution

```bash
uvicorn services.data_ingestor.main:app --host 0.0.0.0 --port 8001
```

## Notes

- Downloads use the `zipper.dataspace.copernicus.eu` service with 8 KB streaming to avoid memory issues.
- `.SAFE` products are automatically extracted and the ZIP archive removed.
- Scene selection targets the Moroccan coastal band (optimized for GFW AIS coverage, see Phase 0).
