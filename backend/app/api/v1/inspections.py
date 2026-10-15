"""Inspection-hold endpoints: list, summary, detail, release and reject."""

from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.inspection import InspectionStatus
from app.schemas.common import SuccessResponse
from app.schemas.inspection import InspectionHoldDetail, InspectionHoldRead, InspectionReject, InspectionRelease
from app.services import inspection_service as service

router = APIRouter(prefix="/api/v1/inspections", tags=["inspections"])


def _run(db: Session, action: Callable[[], object]):
    try:
        return action()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The change conflicted with a concurrent update. Reload and try again.",
        )
    except Exception:
        db.rollback()
        raise


def _detail(db: Session, hold_id: int, message: str) -> SuccessResponse:
    hold = service.get_hold(db, hold_id)
    return SuccessResponse(message=message, data=InspectionHoldDetail.model_validate(hold).model_dump(mode="json"))


@router.get("", response_model=SuccessResponse)
def list_inspections(
    statuses: list[InspectionStatus] = Query(default=[], alias="status", description="Repeat to match several"),
    search: str = Query("", description="Inspection number, or material ID, name or batch"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    total, items = service.list_holds(db, statuses, search, skip, limit)
    return SuccessResponse(
        message="Inspections retrieved successfully",
        data={
            "inspections": [InspectionHoldRead.model_validate(h).model_dump(mode="json") for h in items],
            "total": total, "skip": skip, "limit": limit,
        },
    )


@router.get("/summary", response_model=SuccessResponse)
def inspection_summary(db: Session = Depends(get_db)):
    return SuccessResponse(message="Inspection summary retrieved successfully", data=service.summary(db))


@router.get("/{hold_id}", response_model=SuccessResponse)
def get_inspection(hold_id: int, db: Session = Depends(get_db)):
    return _detail(db, hold_id, "Inspection retrieved successfully")


@router.post("/{hold_id}/release", response_model=SuccessResponse)
def release_inspection(hold_id: int, data: InspectionRelease, db: Session = Depends(get_db)):
    """Passed goods become available stock."""
    _run(db, lambda: service.release(db, hold_id, data))
    return _detail(db, hold_id, "Inspection quantity released")


@router.post("/{hold_id}/reject", response_model=SuccessResponse)
def reject_inspection(hold_id: int, data: InspectionReject, db: Session = Depends(get_db)):
    """Failed goods leave stock (returned or scrapped) and stay owed on the purchase order."""
    _run(db, lambda: service.reject(db, hold_id, data))
    return _detail(db, hold_id, "Inspection quantity rejected")
