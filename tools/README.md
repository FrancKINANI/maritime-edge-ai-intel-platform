# Tools Directory

This directory contains operational utility scripts organized by purpose.

## Structure

- `maintenance/` - One-time maintenance scripts for data correction and migration
- Service-specific tools are located in each service's `tools/` directory:
  - `services/data_ingestor/tools/` - Data ingestion utilities
  - `services/sentinel_preprocessor/tools/` - SAR preprocessing utilities

## Maintenance Scripts

Scripts in `tools/maintenance/` are designed for one-time data correction tasks:

- `fix_bbox_sizes.py` - Corrects fixed-size YOLO bounding boxes with realistic vessel dimensions

## Service Tools

Each service has its own `tools/` directory containing operational scripts:

### Data Ingestor Tools
- `download_scenes.py` - CDSE Sentinel-1 product downloader
- `gfw_annotations.py` - Global Fishing Watch annotation pipeline

### Sentinel Preprocessor Tools
- `sar_preprocessing.py` - Windowed memory-efficient SAR preprocessing
- `process_all_scenes.py` - Batch preprocessing for all scenes
- `apply_mvssd_ops.py` - MVSSD-style enhancement operations

## Usage

Run scripts from the project root:

```bash
# Maintenance scripts
uv run python tools/maintenance/fix_bbox_sizes.py

# Service tools
uv run python services/data_ingestor/tools/download_scenes.py
uv run python services/sentinel_preprocessor/tools/process_all_scenes.py
```
