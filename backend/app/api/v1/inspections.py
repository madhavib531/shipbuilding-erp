"""Inspection-hold endpoints: list, summary, detail, open a hold on existing stock, release and reject."""

from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import require, stamp
from app.database import get_db
from app.models.user import User
from app.models.inspection import InspectionStatus
from app.schemas.common import SuccessResponse
from app.schemas.inspection import (
    InspectionCreate, InspectionHoldDetail, InspectionHoldRead, InspectionReject, InspectionRelease,
)
from app.services import inspection_service as service
from app.services import notification_service as notifications

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
    yard: str = Query("", description="Only holds on batches in this yard"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    total, items = service.list_holds(db, statuses, search, skip, limit, yard)
    return SuccessResponse(
        message="Inspections retrieved successfully",
        data={
            "inspections": [InspectionHoldRead.model_validate(h).model_dump(mode="json") for h in items],
            "total": total, "skip": skip, "limit": limit,
        },
    )


@router.post("", response_model=SuccessResponse, status_code=status.HTTP_201_CREATED)
def create_inspection(data: InspectionCreate, user: User = Depends(require("hold")), db: Session = Depends(get_db)):
    """Holds part of a batch's available stock for inspection; it stays on hand but cannot be used."""
    data = stamp(data, user)
    hold_id = _run(db, lambda: service.create_hold(db, data))
    response = _detail(db, hold_id, "Stock held for inspection")
    notify_hold_opened(db, service.get_hold(db, hold_id), user)
    return response


def notify_hold_opened(db: Session, hold, user: User) -> None:
    notifications.safely(lambda: notifications.notify(
        db, "inspection_opened", f"{hold.display_id}: {hold.quantity} {hold.material.unit} of {hold.material.name} awaiting inspection",
        body=f"Batch {hold.material_id} at {hold.material.yard.name}, held by {user.display_name}.",
        page="Quality", record=hold.display_id, dedupe_key=f"qi-opened:{hold.id}", exclude_user_id=user.id))


@router.get("/summary", response_model=SuccessResponse)
def inspection_summary(yard: str = Query("", description="Only holds on batches in this yard"), db: Session = Depends(get_db)):
    return SuccessResponse(message="Inspection summary retrieved successfully", data=service.summary(db, yard))


@router.get("/{hold_id}", response_model=SuccessResponse)
def get_inspection(hold_id: int, db: Session = Depends(get_db)):
    return _detail(db, hold_id, "Inspection retrieved successfully")


@router.post("/{hold_id}/release", response_model=SuccessResponse)
def release_inspection(hold_id: int, data: InspectionRelease, user: User = Depends(require("inspect")), db: Session = Depends(get_db)):
    """Passed goods become available stock."""
    data = stamp(data, user)
    _run(db, lambda: service.release(db, hold_id, data))
    return _detail(db, hold_id, "Inspection quantity released")


@router.post("/{hold_id}/reject", response_model=SuccessResponse)
def reject_inspection(hold_id: int, data: InspectionReject, user: User = Depends(require("inspect")), db: Session = Depends(get_db)):
    """Failed goods leave stock. From a receipt they are returned or scrapped and stay owed on the purchase
    order; from a hold opened by hand they can only be scrapped."""
    data = stamp(data, user)
    _run(db, lambda: service.reject(db, hold_id, data))
    return _detail(db, hold_id, "Inspection quantity rejected")
