# =============================================================================
# Ground Dashboard — Streamlit visualization
# =============================================================================

FROM maritime-intel-base:latest AS builder

COPY services/ground-dashboard/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM maritime-intel-base:latest AS release

COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY services/ground-dashboard/ /app/services/ground-dashboard/
COPY shared/ /app/shared/

EXPOSE 8501

CMD ["streamlit", "run", "services/ground-dashboard/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
