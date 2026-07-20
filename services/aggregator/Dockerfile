# =============================================================================
# Aggregator — Detection event aggregation and enrichment
# =============================================================================

FROM maritime-intel-base:latest AS release

COPY services/aggregator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/aggregator/ /app/services/aggregator/
COPY shared/ /app/shared/

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/health')"

EXPOSE 8002

CMD ["uvicorn", "services.aggregator.main:app", "--host", "0.0.0.0", "--port", "8002"]
