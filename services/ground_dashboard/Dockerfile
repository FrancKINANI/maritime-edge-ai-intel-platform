# =============================================================================
# Ground Dashboard — Streamlit visualization
# =============================================================================

FROM maritime-intel-base:latest AS builder

COPY services/ground-dashboard/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM maritime-intel-base:latest AS release

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY services/ground-dashboard/ /app/services/ground-dashboard/
COPY shared/ /app/shared/

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD python -c "import socket; s=socket.create_connection(('localhost', 8501), timeout=5); s.close()"

EXPOSE 8501

CMD ["streamlit", "run", "services/ground-dashboard/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
