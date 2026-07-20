# =============================================================================
# Data Ingestor — FastAPI service
# =============================================================================

FROM maritime-intel-base:latest AS release

COPY services/data-ingestor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/data-ingestor/ /app/services/data-ingestor/
COPY shared/ /app/shared/

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')"

EXPOSE 8001

CMD ["uvicorn", "services.data-ingestor.main:app", "--host", "0.0.0.0", "--port", "8001"]
