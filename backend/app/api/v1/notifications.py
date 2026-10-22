"""The signed-in user's notifications: list (with unread count) and mark as read."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.auth import current_user
from app.database import get_db
from app.models.user import User
from app.schemas.common import SuccessResponse
from app.services import notification_service as service

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    title: str
    body: Optional[str]
    page: Optional[str]
    record: Optional[str]
    created_at: datetime
    read_at: Optional[datetime]


@router.get("", response_model=SuccessResponse)
def list_notifications(limit: int = Query(20, ge=1, le=100), user: User = Depends(current_user), db: Session = Depends(get_db)):
    service.safely(lambda: service.sweep_overdue_orders(db))  # time-based: checked when notifications are read
    items, unread = service.list_for(db, user, limit)
    return SuccessResponse(message="Notifications retrieved", data={
        "notifications": [NotificationRead.model_validate(n).model_dump(mode="json") for n in items],
        "unread": unread, "email_enabled": service.email_enabled()})


@router.post("/{notification_id}/read", response_model=SuccessResponse)
def mark_read(notification_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return SuccessResponse(message="Marked as read", data={"updated": service.mark_read(db, user, notification_id)})


@router.post("/read-all", response_model=SuccessResponse)
def mark_all_read(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return SuccessResponse(message="All marked as read", data={"updated": service.mark_read(db, user)})
