"""Health check and status endpoints."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database import get_db
from app.config import settings
from app.schemas.common import HealthCheckResponse

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="Health Check",
    description="Verify backend service and database connectivity.",
)
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint that verifies database connectivity."""
    try:
        # Simple database query to verify connection
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        # Details (which can include the database host or user) go to the server log, not the response.
        logger.exception("Health check: database query failed")
        db_status = "unavailable"

    return HealthCheckResponse(
        status="healthy",
        message="Backend service is operational",
        version=settings.app_version,
        database=db_status,
    )
