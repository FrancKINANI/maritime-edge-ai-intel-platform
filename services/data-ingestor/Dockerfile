# =============================================================================
# Data Ingestor — FastAPI service
# =============================================================================

FROM maritime-intel-base:latest AS release

COPY services/data-ingestor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/data-ingestor/ /app/services/data-ingestor/
COPY shared/ /app/shared/

EXPOSE 8001

CMD ["uvicorn", "services.data-ingestor.main:app", "--host", "0.0.0.0", "--port", "8001"]
