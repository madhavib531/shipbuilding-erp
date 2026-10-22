"""Stored notifications: who is told about what, read state, and optional email.

Each event notifies the active users whose role handles it (never the person who caused it), once per
recipient: a `dedupe_key` makes repeats harmless. Email goes out only when SMTP is configured in the
environment (SMTP_HOST and SMTP_FROM) and the user has an email address; it is sent with the standard
library's smtplib right after the notification is stored, and a failure is logged, never raised.
"""

import logging
import smtplib
from datetime import date, datetime
from email.message import EmailMessage

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.notification import Notification
from app.models.purchase_order import OPEN_PURCHASE_ORDER_STATUSES, PurchaseOrder
from app.models.user import User, UserRole

log = logging.getLogger(__name__)

R = UserRole
RECIPIENTS: dict[str, tuple[UserRole, ...]] = {
    "low_stock": (R.STOREKEEPER, R.PROCUREMENT, R.ADMIN),
    "inspection_opened": (R.INSPECTOR, R.ADMIN),
    "transfer_requested": (R.STOREKEEPER, R.ADMIN),
    "transfer_approved": (R.STOREKEEPER,),
    "transfer_dispatched": (R.STOREKEEPER,),
    "order_overdue": (R.PROCUREMENT, R.ADMIN),
}


def email_enabled() -> bool:
    return bool(settings.smtp_host and settings.smtp_from)


def notify(db: Session, kind: str, title: str, *, body: str | None = None, page: str | None = None,
           record: str | None = None, dedupe_key: str, exclude_user_id: int | None = None) -> list[Notification]:
    """Stores one notification per recipient (skipping those who already have this dedupe_key) and emails them."""
    roles = RECIPIENTS[kind]
    users = db.scalars(select(User).where(User.role.in_(roles), User.is_active.is_(True))).all()
    created = []
    now = datetime.now()
    for user in users:
        if user.id == exclude_user_id:
            continue
        exists = db.scalar(select(Notification.id).where(Notification.user_id == user.id, Notification.dedupe_key == dedupe_key))
        if exists is not None:
            continue
        note = Notification(user_id=user.id, kind=kind, title=title, body=body, page=page, record=record,
                            dedupe_key=dedupe_key, created_at=now)
        db.add(note)
        created.append((note, user))
    try:
        db.commit()
    except IntegrityError:  # a concurrent request stored the same notification first
        db.rollback()
        return []
    if email_enabled():
        _email(db, created)
    return [n for n, _ in created]


def _email(db: Session, created: list[tuple[Notification, User]]) -> None:
    targets = [(n, u) for n, u in created if u.email]
    if not targets:
        return
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password or "")
            for note, user in targets:
                msg = EmailMessage()
                msg["From"] = settings.smtp_from
                msg["To"] = user.email
                msg["Subject"] = f"[Dockyard] {note.title}"
                lines = [note.title, ""] + ([note.body, ""] if note.body else []) + \
                        [f"Open the {note.page} page in Dockyard Materials Command to act on it." if note.page else ""]
                msg.set_content("\n".join(lines))
                smtp.send_message(msg)
                note.emailed_at = datetime.now()
        db.commit()
    except Exception as exc:  # noqa: BLE001 - email is best effort; the in-app notification is stored
        db.rollback()
        log.warning("Notification email failed: %s", type(exc).__name__)


def safely(action) -> None:
    """Runs a notification hook without ever failing the request that triggered it."""
    try:
        action()
    except Exception as exc:  # noqa: BLE001
        log.warning("Notification hook failed: %s", exc)


def sweep_overdue_orders(db: Session) -> None:
    """Notifies about open orders past their expected delivery date, once per order and date."""
    today = date.today()
    orders = db.scalars(select(PurchaseOrder).where(PurchaseOrder.status.in_(OPEN_PURCHASE_ORDER_STATUSES),
                                                    PurchaseOrder.expected_delivery_date < today)).all()
    for order in orders:
        notify(db, "order_overdue", f"{order.display_id} is past its delivery date",
               body=f"Expected {order.expected_delivery_date:%d %b %Y}; follow up with the supplier.",
               page="Procurement", record=order.display_id,
               dedupe_key=f"po-overdue:{order.id}:{order.expected_delivery_date.isoformat()}")


def list_for(db: Session, user: User, limit: int) -> tuple[list[Notification], int]:
    items = db.scalars(select(Notification).where(Notification.user_id == user.id)
                       .order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit)).all()
    unread = db.scalar(select(func.count()).select_from(Notification)
                       .where(Notification.user_id == user.id, Notification.read_at.is_(None)))
    return items, unread


def mark_read(db: Session, user: User, notification_id: int | None = None) -> int:
    query = update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    if notification_id is not None:
        query = query.where(Notification.id == notification_id)
    count = db.execute(query.values(read_at=datetime.now())).rowcount
    db.commit()
    return count
