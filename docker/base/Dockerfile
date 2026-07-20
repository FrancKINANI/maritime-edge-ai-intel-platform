# =============================================================================
# Maritime Intelligence Platform — Base Image
# Shared system dependencies for all microservices.
# Every service Dockerfile starts FROM this base.
# =============================================================================

FROM python:3.14-slim AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# ---- Common system deps (minimal) ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# ---- Build stage (compilation dependencies) ----
FROM base AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# ---- Release stage (minimal) ----
FROM base AS release

# Install shared Python dependencies (avoids duplication across all 6 service Dockerfiles)
COPY docker/base/requirements.txt /app/
RUN pip install --no-cache-dir -r /app/requirements.txt

RUN find /usr/local -name '*.pyc' -delete

# Create non-privileged user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

LABEL maintainer="KSF Space Foundation" \
      description="Maritime Intelligence Platform microservice"
