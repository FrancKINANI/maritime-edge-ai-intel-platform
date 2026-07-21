# =============================================================================
# Satellite Monitor — TLE tracking and satellite position service
# =============================================================================

FROM maritime-intel-base:latest AS builder

COPY services/satellite-monitor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM maritime-intel-base:latest AS release

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY services/satellite-monitor/ /app/services/satellite-monitor/
COPY shared/ /app/shared/

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

EXPOSE 8000

CMD ["uvicorn", "services.satellite-monitor.main:app", "--host", "0.0.0.0", "--port", "8000"]
