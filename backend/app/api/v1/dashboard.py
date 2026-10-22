"""Dashboard aggregates that no other endpoint provides. Read-only."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.common import SuccessResponse
from app.services import dashboard_service as service

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/movements", response_model=SuccessResponse)
def stock_movements(months: int = Query(6, ge=1, le=24), yard: str = Query("", description="Only batches now in this yard"),
                    db: Session = Depends(get_db)):
    """Stock-in and stock-out ledger entries per month (counts, since units differ between batches)."""
    return SuccessResponse(message="Stock movements retrieved successfully", data=service.movements(db, months, yard=yard))


@router.get("/ships", response_model=SuccessResponse)
def ship_programs(yard: str = Query("", description="Only ships built at this yard"), db: Session = Depends(get_db)):
    """Ships with build status and the number of batches allocated to each."""
    return SuccessResponse(message="Ship programs retrieved successfully", data={"ships": service.ships(db, yard)})


@router.get("/yards", response_model=SuccessResponse)
def yard_overview(db: Session = Depends(get_db)):
    """Yards with their storage locations, batches and ships counted."""
    return SuccessResponse(message="Yards retrieved successfully", data={"yards": service.yards(db)})
