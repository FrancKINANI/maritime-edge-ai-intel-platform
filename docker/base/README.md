# Docker Base Image — `maritime-intel-base:2.1.0`

Common base image for all maritime-intelligence-platform microservices.

## Build

```bash
docker build -f docker/base/Dockerfile -t maritime-intel-base:2.1.0 .
```

## Contents

- **Python 3.11-slim** runtime
- **System packages**: libgl1, libglib2.0-0 (OpenCV/ML dependencies)
- **Python packages**: fastapi, uvicorn, pydantic, httpx, numpy

## Multi-stage Build

- `base` — System packages
- `release` — Pip install of shared deps + pyc cleanup

## Purpose

All 6 service Dockerfiles start with `FROM maritime-intel-base:2.1.0`, eliminating duplicate installations of FastAPI, Uvicorn, Pydantic, and other shared dependencies.
