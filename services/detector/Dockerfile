# =============================================================================
# Detector — ONNX vessel detection service
# Build stage compiles deps, runtime stage is minimal
# =============================================================================

FROM maritime-intel-base:latest AS builder

COPY services/detector/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM maritime-intel-base:latest AS release

COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY services/detector/ /app/services/detector/
COPY shared/ /app/shared/

EXPOSE 8000

CMD ["uvicorn", "services.detector.main:app", "--host", "0.0.0.0", "--port", "8000"]
