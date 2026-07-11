# Ground Dashboard (Streamlit)

**Purpose**: Operator interface with three operational modes: Upload, Satellite Query, and Continuous Monitoring.

## Modes

### Mode 1 — Upload Image / SAR Product

File upload for vessel detection:

| Format | Processing |
|--------|------------|
| **`.npy`** | Direct send to Detector (preprocessed tile) |
| **`.zip` / `.SAFE`** | Save to shared volume → Preprocessing (sentinel-preprocessor) → Detection |
| **`.tiff` / `.tif`** | Same as above (raw GeoTIFF) |

The pipeline selector (A/B/C/D) chooses the SAR preprocessing chain.

### Mode 2 — Satellite Query

Queries the Satellite Monitor for a satellite's position at a given time.
- Default NORAD ID: `39634` (Sentinel-1A).
- UTC timestamp in ISO format.

### Mode 3 — Continuous Monitoring

Queries the Aggregator with filters:
- Maritime zone (Z1/Territorial, Z2/EEZ, Z3/High Seas)
- Priority level (LOW → CRITICAL)
- Time filter (`since`)
- Geographic zone definition (4-corner bbox)

## Configuration

Environment variables:

| Variable | Default | Target Service |
|----------|---------|----------------|
| `DETECTOR_URL` | `http://localhost:8001` | Detector |
| `SATMON_URL` | `http://localhost:8010` | Satellite Monitor |
| `AGGREGATOR_URL` | `http://localhost:8020` | Aggregator |
| `PREPROCESSOR_URL` | `http://localhost:8000` | Sentinel Preprocessor |

## Local Execution

```bash
streamlit run services.ground_dashboard.app:main --server.port 8050
```

## Usage

Open `http://localhost:8050` and select a mode from the sidebar.

## Notes

- Uploaded `.zip` / `.tiff` files are stored on the shared Docker volume (`/app/shared/uploads/`) to be accessible by the preprocessor.
- Pipelines are documented in the UI with their scientific justification (Phase 0 inconclusive — D is provisional).
