"""Audit feed endpoint. Read-only."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import InvalidInputError
from app.schemas.common import SuccessResponse
from app.services import audit_service as service
from app.services.audit_service import AuditSource

router = APIRouter(prefix="/api/v1/audit-events", tags=["audit"])


@router.get("", response_model=SuccessResponse)
def list_audit_events(
    sources: list[AuditSource] = Query(default=[], alias="source", description="Repeat to match several"),
    search: str = Query("", max_length=200,
                        description="Material ID, name or batch, TR-/PO-/QI-/GR- numbers, actor, action or reason"),
    actor: str = Query("", max_length=100),
    date_from: Optional[date] = Query(None, description="Inclusive, YYYY-MM-DD"),
    date_to: Optional[date] = Query(None, description="Inclusive, YYYY-MM-DD"),
    yard: str = Query("", max_length=50, description="Batches now in this yard, transfers from or to it, orders delivered to it"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Stock ledger, transfer, purchase-order and inspection events, newest first."""
    if date_from and date_to and date_from > date_to:
        raise InvalidInputError("date_from must be on or before date_to")
    total, events = service.list_events(db, sources, search, actor, date_from, date_to, skip, limit, yard)
    return SuccessResponse(
        message="Audit events retrieved successfully",
        data={"events": events, "total": total, "skip": skip, "limit": limit},
    )
