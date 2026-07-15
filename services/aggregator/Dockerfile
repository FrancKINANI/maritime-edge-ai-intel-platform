# =============================================================================
# Aggregator — Detection event aggregation and enrichment
# =============================================================================

FROM maritime-intel-base:latest AS release

COPY services/aggregator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/aggregator/ /app/services/aggregator/
COPY shared/ /app/shared/

EXPOSE 8002

CMD ["uvicorn", "services.aggregator.main:app", "--host", "0.0.0.0", "--port", "8002"]
