# Maritime Edge AI Intelligence Platform (Phase II)

[![CI](https://github.com/FrancKINANI/maritime-edge-ai-intel-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/FrancKINANI/maritime-edge-ai-intel-platform/actions/workflows/ci.yml)

A high-performance microservice-based edge platform to ingest, preprocess, and detect marine vessels on real Sentinel-1 SAR imagery.

## Description
This project constitutes **Phase II** of our maritime intelligence platform, transitioning the simulation-trained Edge AI models developed in [Phase I](https://github.com/FrancKINANI/maritime-edge-ai) to a fully operational, containerized, multi-service architecture consuming real-world Copernicus Sentinel-1 radar scenes.

## Prerequisites
- Docker (v20.10+)
- Docker Compose (v2.0+)
- Python 3.10+ (for local validation scripting)

## Architecture
```
                                        +-------------------+
                                        |  SatNOGS TLE API  |
                                        +---------+---------+
                                                  |
                                                  v
+------------------+     +------------+     +-----+-------------+
| Copernicus CDSE  |---->|    data-   |---->|     satellite-    |
| (Sentinel-1 SAR) |     |  ingestor  |     |     monitor       |
+------------------+     +-----+------+     +-------------------+
                               |
                               v
                         +-----+------+
                         |  sentinel- | (Radiometric Calibration,
                         |preprocessor|  Speckle Lee filter, Log dB)
                         +-----+------+
                               |
                               v (Overlapping Tiles .npy)
                         +-----+------+     +-------------------+
                         |  detector  |---->|       Redis       |
                         | (YOLO INT8)|     |   (Shared Cache)  |
                         +-----+------+     +---------+---------+
                               |                      |
                               v                      v
                         +-----+----------------------+---------+
                         |              aggregator              |
                         |      (SQLite/Postgres Alert DB)      |
                         +-----------------+--------------------+
                                           |
                                           v
                         +-----------------+--------------------+
                         |           ground-dashboard           |
                         |             (Streamlit)              |
                         +--------------------------------------+
```

## Quick Start
Get the entire system running locally in 5 simple commands:

```bash
git clone https://github.com/FrancKINANI/maritime-edge-ai-intel-platform.git
cd maritime-edge-ai-intel-platform
cp .env.example .env
make setup
make build
make up
```

## Documentation
- Refer to [Phase 0 Scientific Validation](file:///home/franck/Documents/02_Projets/IA/Projets_IA/cubesat-maritime-project/maritime-intelligence-platform/phase0/README.md) for detailed documentation of the experimental protocol, pipelines A/B/C/D, and zero-shot transfer benchmarks.
- Original Edge AI modeling details can be found at the [Phase I Repository](https://github.com/FrancKINANI/maritime-edge-ai).
