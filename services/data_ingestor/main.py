# services/data_ingestor/main.py
"""Data Ingestor FastAPI Service.

Exposes endpoints for querying Copernicus Sentinel-1 catalog products, starting ingestion
jobs, and monitoring ingestion tasks.
"""

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, status

from shared.config import SecretsValidationError, validate_service_secrets
from shared.schemas.events import IngestRequest

logger = logging.getLogger(__name__)

# Validate required environment variables at startup
# NOTE: We warn instead of sys.exit() to allow test imports without env vars.
# The service will fail gracefully at runtime if Redis/CDSE credentials are missing.
try:
    validate_service_secrets("data_ingestor")
    logger.info("Secrets validation passed")
except SecretsValidationError as e:
    logger.error("Secrets validation failed: %s", e)
    logger.warning(
        "Service will start but may fail at runtime — set CDSE_USERNAME, CDSE_PASSWORD, REDIS_URL in .env"
    )

app = FastAPI(
    title="Maritime Edge AI Intel Platform - Data Ingestor",
    description="Microservice responsible for Sentinel-1 metadata querying and SAFEs ingestion.",
    version="1.0.0",
)


@app.post("/ingest", status_code=status.HTTP_202_ACCEPTED, response_model=dict[str, str])
async def trigger_ingestion(request: IngestRequest) -> dict[str, str]:
    """Asynchronously triggers the ingestion and acquisition of a Sentinel-1 product.

    Args:
        request (IngestRequest): Ingestion query parameter payload.

    Returns:
        Dict[str, str]: Target job ID reference.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Ingestion workflow is not yet implemented.",
    )


@app.get("/status/{job_id}", response_model=dict[str, Any])
async def get_ingestion_status(job_id: str) -> dict[str, Any]:
    """Retrieves progress status of a running/scheduled ingestion job.

    Args:
        job_id (str): Ingestion job identifier.

    Returns:
        Dict[str, Any]: Ingestion status details.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Status tracking is not yet implemented.",
    )


@app.get("/products", response_model=list[dict[str, Any]])
async def list_available_products(
    bbox: str, date_start: str, date_end: str
) -> list[dict[str, Any]]:
    """Lists Sentinel-1 products matching search criteria from Copernicus Data Space.

    Args:
        bbox (str): Comma-separated bbox coordinates (lon_min,lat_min,lon_max,lat_max).
        date_start (str): Start date string (ISO8601).
        date_end (str): End date string (ISO8601).

    Returns:
        List[Dict[str, Any]]: Metadata list of products.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Product listing queries are not yet implemented.",
    )


@app.get("/health", response_model=dict[str, str])
async def health_check() -> dict[str, str]:
    """Service health check endpoint.

    Returns:
        Dict[str, str]: Service status message.
    """
    return {"status": "healthy"}
