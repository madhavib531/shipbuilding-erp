"""Materials CRUD endpoints (Phase 1 stub)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.common import SuccessResponse

router = APIRouter(prefix="/api/v1/materials", tags=["materials"])


@router.get("", response_model=SuccessResponse)
def list_materials(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """
    List all materials with pagination.

    Phase 1 stub: returns empty dataset.
    Full implementation in Phase 1 with search, filtering, and real data.
    """
    return SuccessResponse(
        message="Materials list endpoint (Phase 1 stub)",
        data={
            "materials": [],
            "total": 0,
            "skip": skip,
            "limit": limit,
        }
    )
