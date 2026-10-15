"""Material transfer endpoints: request, approve, reject, dispatch, receive and cancel."""

from typing import Callable

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.transfer import TransferStatus
from app.schemas.common import SuccessResponse
from app.schemas.transfer import TransferCreate, TransferNote, TransferRead, TransferReason, TransferReceive
from app.services import transfer_service as service

router = APIRouter(prefix="/api/v1/transfers", tags=["transfers"])


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


def _transfer_response(db: Session, transfer_id: int, message: str) -> SuccessResponse:
    transfer = service.get_transfer(db, transfer_id)
    return SuccessResponse(message=message, data=TransferRead.model_validate(transfer).model_dump(mode="json"))


@router.get("", response_model=SuccessResponse)
def list_transfers(
    statuses: list[TransferStatus] = Query(default=[], alias="status", description="Repeat to match several"),
    material_id: str = Query("", description="Source or destination material ID"),
    yard: str = Query("", description="Source or destination yard ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    total, items = service.list_transfers(db, statuses, material_id, yard, skip, limit)
    return SuccessResponse(
        message="Transfers retrieved successfully",
        data={
            "transfers": [TransferRead.model_validate(t).model_dump(mode="json") for t in items],
            "total": total, "skip": skip, "limit": limit,
        },
    )


@router.get("/summary", response_model=SuccessResponse)
def transfer_summary(db: Session = Depends(get_db)):
    return SuccessResponse(message="Transfer summary retrieved successfully", data=service.summary(db))


@router.get("/{transfer_id}", response_model=SuccessResponse)
def get_transfer(transfer_id: int, db: Session = Depends(get_db)):
    return _transfer_response(db, transfer_id, "Transfer retrieved successfully")


@router.post("", response_model=SuccessResponse, status_code=status.HTTP_201_CREATED)
def create_transfer(
    data: TransferCreate,
    response: Response,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=100),
    db: Session = Depends(get_db),
):
    transfer_id, created = _run(db, lambda: service.create_transfer(db, data, idempotency_key))
    if not created:
        response.status_code = status.HTTP_200_OK
    return _transfer_response(
        db, transfer_id, "Transfer requested" if created else "Transfer already exists for this Idempotency-Key"
    )


@router.post("/{transfer_id}/approve", response_model=SuccessResponse)
def approve_transfer(transfer_id: int, body: TransferNote, db: Session = Depends(get_db)):
    _run(db, lambda: service.approve(db, transfer_id, body.actor, body.reason))
    return _transfer_response(db, transfer_id, "Transfer approved")


@router.post("/{transfer_id}/reject", response_model=SuccessResponse)
def reject_transfer(transfer_id: int, body: TransferReason, db: Session = Depends(get_db)):
    _run(db, lambda: service.reject(db, transfer_id, body.actor, body.reason))
    return _transfer_response(db, transfer_id, "Transfer rejected")


@router.post("/{transfer_id}/cancel", response_model=SuccessResponse)
def cancel_transfer(transfer_id: int, body: TransferReason, db: Session = Depends(get_db)):
    _run(db, lambda: service.cancel(db, transfer_id, body.actor, body.reason))
    return _transfer_response(db, transfer_id, "Transfer cancelled")


@router.post("/{transfer_id}/dispatch", response_model=SuccessResponse)
def dispatch_transfer(transfer_id: int, body: TransferNote, db: Session = Depends(get_db)):
    _run(db, lambda: service.dispatch(db, transfer_id, body.actor, body.reason))
    return _transfer_response(db, transfer_id, "Transfer dispatched")


@router.post("/{transfer_id}/receive", response_model=SuccessResponse)
def receive_transfer(transfer_id: int, body: TransferReceive, db: Session = Depends(get_db)):
    _run(db, lambda: service.receive(db, transfer_id, body))
    return _transfer_response(db, transfer_id, "Transfer received")
