# Phase 0 Scripts

Scientific validation scripts for benchmarking the preprocessing pipelines and detector against real Sentinel-1 data.

## Scripts

| Script | Purpose |
|--------|---------|
| `download_scenes.py` | CDSE scene search + streaming download with coastal targeting |
| `sar_preprocessing.py` | SAR calibration, filtering, tiling, and GCP georeferencing |
| `gfw_annotations.py` | GFW API v3 integration for AIS vessel presence and dark vessel detection |
| `benchmark_pipeline.py` | End-to-end benchmark: download → preprocess → detect → evaluate |
| `diagnostics/` | GCP parity proof, Colab traceability check, validation scripts |

## Phase 0 Goal

*Can an INT8-quantized YOLOv8 detector trained on simulated SAR imagery achieve acceptable performance on real Sentinel-1 data — without fine-tuning?*

## Output

- Downloaded scenes → `data/scenes/`
- Preprocessed tiles → `data/tiles/`
- Annotations → `data/annotations/`
- Benchmark results → `data/results/`
