# Phase 0: Scientific Validation Protocol

This directory contains the scientific validation framework to benchmark the domain transfer performance of the models developed in Phase I (which were trained on simulated SAR images) to real Sentinel-1 SAR GRD images.

## Objective
Validate that the INT8-quantized YOLOv8 object detection model can detect vessels on real Sentinel-1 images without retraining (zero-shot transfer) or identify if fine-tuning is required.

## Preprocessing Pipelines
We evaluate 4 preprocessing variants:
1. **Pipeline A (Raw Baseline)**: Direct conversion of GeoTIFF uint16 intensity to normalised range [0, 255].
2. **Pipeline B (Sigma0 Calibration)**: Radiometric calibration to physical $\sigma^0$ (sigma-nought) backscatter coefficient, followed by [0, 255] normalisation.
3. **Pipeline C (Speckle Filtering)**: $\sigma^0$ calibration, followed by a 5x5 adaptive Lee speckle filter, and [0, 255] normalisation.
4. **Pipeline D (Logarithmic Scaling)**: $\sigma^0$ calibration, 5x5 adaptive Lee speckle filter, logarithmic scaling to decibel (dB), and [0, 255] normalisation. *Recommended pipeline.*

## Validation Criteria
- **GO**: $mAP@0.5 > 0.70$ on at least one preprocessing pipeline.
- **STOP**: $mAP@0.5 < 0.50$ across all pipelines. Requires additional model fine-tuning.

## Directory Structure
- `data/scenes/`: Root directory for downloaded `.SAFE` Sentinel-1 GRD files.
- `data/tiles/`: Generated sub-tiles for model inference.
- `data/annotations/`: Ground truth annotations (e.g. YOLO/CVAT format).
- `data/results/`: Evaluation results (plots, CSVs, JSONs).
