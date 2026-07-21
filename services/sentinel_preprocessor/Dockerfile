# =============================================================================
# Sentinel Preprocessor — SAR preprocessing with GDAL
# Uses multi-stage to keep final image small
# =============================================================================

FROM maritime-intel-base:latest AS builder

# GDAL is needed at build time for rasterio compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

COPY services/sentinel_preprocessor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Runtime stage — GDAL runtime only (no dev headers)
FROM maritime-intel-base:latest AS release

RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY services/sentinel_preprocessor/ /app/services/sentinel_preprocessor/
COPY shared/ /app/shared/

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

EXPOSE 8000

CMD ["uvicorn", "services.sentinel_preprocessor.main:app", "--host", "0.0.0.0", "--port", "8000"]
