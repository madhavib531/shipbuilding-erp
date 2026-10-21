"""Rule-based analytics endpoint. Read-only."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.common import SuccessResponse
from app.services import analytics_service as service

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/overview", response_model=SuccessResponse)
def analytics_overview(db: Session = Depends(get_db)):
    """Stock by category, batch age, supplier, transfer and inspection performance, and rule-based flags —
    all computed from stored records with fixed rules (no AI model)."""
    return SuccessResponse(message="Analytics computed successfully", data=service.overview(db))
