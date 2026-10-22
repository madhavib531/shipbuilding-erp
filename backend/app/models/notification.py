"""In-app notifications, one row per recipient, with read state."""

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint

from app.models.base import Base


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        # One notification per recipient per event (dedupe_key), so repeated checks never duplicate it.
        UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe"),
        Index("ix_notifications_user_unread", "user_id", "read_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    kind = Column(String(40), nullable=False)        # low_stock, inspection_opened, transfer_requested, ...
    title = Column(String(200), nullable=False)
    body = Column(Text)
    page = Column(String(40))                         # the page that handles it, e.g. "Quality"
    record = Column(String(50))                       # e.g. QI-00003, TR-00002, PO-00001, a batch ID
    dedupe_key = Column(String(120), nullable=False)
    created_at = Column(DateTime, nullable=False)
    read_at = Column(DateTime)
    emailed_at = Column(DateTime)
