"""Health check and status endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database import get_db
from app.config import settings
from app.schemas.common import HealthCheckResponse

router = APIRouter(tags=["health"])


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
    except Exception as e:
        db_status = f"error: {str(e)}"

    return HealthCheckResponse(
        status="healthy",
        message="Backend service is operational",
        version=settings.app_version,
        database=db_status,
    )
