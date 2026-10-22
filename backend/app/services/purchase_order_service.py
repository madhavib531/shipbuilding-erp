"""Purchase-order drafts and lifecycle.

Purchase orders never touch stock or the material ledger; only goods receipts do. Every mutation
locks the order row (SELECT ... FOR UPDATE), checks the caller's expected_version and the current
status, writes an audit event and commits once, so concurrent or stale requests get 409.
"""

import hashlib
import json
import re
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.errors import ConflictError, InvalidInputError, ItemNotFoundError
from app.models.goods_receipt import GoodsReceipt, GoodsReceiptLine
from app.models.material import MaterialCategory
from app.models.purchase_order import (
    OPEN_PURCHASE_ORDER_STATUSES, PurchaseOrder, PurchaseOrderEvent, PurchaseOrderLine, PurchaseOrderStatus as S,
)
from app.models.facility import Yard
from app.models.supplier import Supplier, SupplierStatusEnum
from app.services import currency_service
from app.schemas.purchase_order import (
    PurchaseOrderAction, PurchaseOrderCreate, PurchaseOrderLineIn, PurchaseOrderReasonAction, PurchaseOrderUpdate,
)

INELIGIBLE_SUPPLIER_STATUSES = (SupplierStatusEnum.INACTIVE, SupplierStatusEnum.BLOCKED)
_PO_NUMBER = re.compile(r"^\s*(?:PO-?)?0*(\d{1,9})\s*$", re.IGNORECASE)

_LIST_OPTIONS = (
    selectinload(PurchaseOrder.supplier),
    selectinload(PurchaseOrder.delivery_yard),
    selectinload(PurchaseOrder.lines).selectinload(PurchaseOrderLine.category),
)
_DETAIL_OPTIONS = _LIST_OPTIONS + (
    selectinload(PurchaseOrder.events),
    selectinload(PurchaseOrder.receipts).selectinload(GoodsReceipt.yard),
    selectinload(PurchaseOrder.receipts).selectinload(GoodsReceipt.location),
    selectinload(PurchaseOrder.receipts).selectinload(GoodsReceipt.lines).selectinload(GoodsReceiptLine.purchase_order_line),
    selectinload(PurchaseOrder.receipts).selectinload(GoodsReceipt.lines).selectinload(GoodsReceiptLine.inspection_hold),
)


def _label(order_id: int) -> str:
    return f"PO-{order_id:05d}"


def get_order(db: Session, order_id: int) -> PurchaseOrder:
    order = db.scalar(
        select(PurchaseOrder).where(PurchaseOrder.id == order_id)
        .options(*_DETAIL_OPTIONS).execution_options(populate_existing=True)
    )
    if order is None:
        raise ItemNotFoundError("Purchase order", _label(order_id))
    return order


def list_orders(db: Session, statuses: list[S], supplier_id: str, search: str, overdue: bool,
                skip: int, limit: int, yard: str = "") -> tuple[int, list[PurchaseOrder]]:
    query = select(PurchaseOrder)
    if yard:
        query = query.where(PurchaseOrder.delivery_yard_id == yard)
    if statuses:
        query = query.where(PurchaseOrder.status.in_(statuses))
    if supplier_id:
        query = query.where(PurchaseOrder.supplier_id == supplier_id)
    if overdue:
        query = query.where(
            PurchaseOrder.status.in_(OPEN_PURCHASE_ORDER_STATUSES),
            PurchaseOrder.expected_delivery_date < date.today(),
        )
    if search.strip():
        term = f"%{search.strip()}%"
        conditions = [
            PurchaseOrder.supplier.has(Supplier.name.ilike(term)),
            exists().where(PurchaseOrderLine.purchase_order_id == PurchaseOrder.id,
                           or_(PurchaseOrderLine.description.ilike(term),
                               PurchaseOrderLine.supplier_part_number.ilike(term))),
        ]
        number = _PO_NUMBER.match(search)
        if number:
            conditions.append(PurchaseOrder.id == int(number.group(1)))
        query = query.where(or_(*conditions))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.options(*_LIST_OPTIONS).order_by(PurchaseOrder.id.desc()).offset(skip).limit(limit)).all()
    return total, items


def summary(db: Session, yard: str = "") -> dict:
    """Order counts and open value; `yard` limits it to orders delivered to that yard."""
    today = date.today()
    in_yard = [PurchaseOrder.delivery_yard_id == yard] if yard else []
    counts = dict(db.execute(select(PurchaseOrder.status, func.count()).where(*in_yard).group_by(PurchaseOrder.status)).all())
    is_open = PurchaseOrder.status.in_(OPEN_PURCHASE_ORDER_STATUSES)
    overdue = db.scalar(select(func.count()).select_from(PurchaseOrder).where(is_open, PurchaseOrder.expected_delivery_date < today, *in_yard))
    due_this_week = db.scalar(select(func.count()).select_from(PurchaseOrder).where(
        is_open, PurchaseOrder.expected_delivery_date.between(today, today + timedelta(days=6)), *in_yard))
    outstanding = (PurchaseOrderLine.ordered_quantity - PurchaseOrderLine.received_quantity
                   - PurchaseOrderLine.cancelled_quantity)
    open_value = db.execute(
        select(PurchaseOrderLine.currency, func.sum(outstanding * PurchaseOrderLine.unit_price))
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .where(is_open, *in_yard).group_by(PurchaseOrderLine.currency).order_by(PurchaseOrderLine.currency)
    ).all()
    return {
        "by_status": {s.value: counts.get(s, 0) for s in S},
        "open": sum(counts.get(s, 0) for s in OPEN_PURCHASE_ORDER_STATUSES),
        "overdue": overdue,
        "due_this_week": due_this_week,
        "partially_received": counts.get(S.PARTIALLY_RECEIVED, 0),
        "open_value": [
            {"currency": currency, "amount": str(Decimal(str(amount or 0)).quantize(Decimal("0.0001")))}
            for currency, amount in open_value
        ],
        "open_value_base": currency_service.to_base(db, [{"currency": c, "amount": a or 0} for c, a in open_value]),
    }


def _fingerprint(data: PurchaseOrderCreate) -> str:
    return hashlib.sha256(json.dumps(data.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()


def _event(db: Session, order: PurchaseOrder, action: str, from_status: S | None, actor: str,
           reason: str | None = None, changes: dict | None = None) -> None:
    db.add(PurchaseOrderEvent(
        purchase_order_id=order.id, action=action, from_status=from_status.value if from_status else None,
        to_status=order.status.value, actor=actor, reason=reason, version=order.version, changes=changes,
    ))


def _require_yard(db: Session, yard_id: str | None) -> None:
    if yard_id is not None and db.get(Yard, yard_id) is None:
        raise InvalidInputError(f"Yard '{yard_id}' does not exist")


def _require_eligible_supplier(db: Session, supplier_id: str) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise InvalidInputError(f"Supplier '{supplier_id}' does not exist")
    if supplier.status in INELIGIBLE_SUPPLIER_STATUSES:
        raise InvalidInputError(
            f"Supplier '{supplier.name}' is {supplier.status.value} and cannot be used on purchase orders")
    return supplier


def _line_key(line: PurchaseOrderLineIn) -> tuple:
    return (line.category_id, " ".join(line.description.split()).casefold(), line.unit,
            (line.supplier_part_number or "").casefold())


def _validate_lines(db: Session, lines: list[PurchaseOrderLineIn]) -> None:
    if not lines:
        return
    category_ids = {l.category_id for l in lines}
    known = set(db.scalars(select(MaterialCategory.id).where(MaterialCategory.id.in_(category_ids))))
    missing = sorted(category_ids - known)
    if missing:
        raise InvalidInputError(f"Category does not exist: {', '.join(missing)}")
    currencies = sorted({l.currency for l in lines})
    if len(currencies) > 1:
        raise InvalidInputError(
            f"All lines on one purchase order must use the same currency; found {', '.join(currencies)}")
    seen: dict[tuple, int] = {}
    for number, line in enumerate(lines, start=1):
        key = _line_key(line)
        if key in seen:
            raise InvalidInputError(
                f"Lines {seen[key]} and {number} order the same material (category, description, unit and "
                f"supplier part number); combine them into one line")
        seen[key] = number


def _new_lines(order_id: int, lines: list[PurchaseOrderLineIn]) -> list[PurchaseOrderLine]:
    return [
        PurchaseOrderLine(
            purchase_order_id=order_id, line_no=number, category_id=l.category_id, description=l.description,
            unit=l.unit, supplier_part_number=l.supplier_part_number, ordered_quantity=l.ordered_quantity,
            unit_price=l.unit_price, currency=l.currency,
        )
        for number, l in enumerate(lines, start=1)
    ]


def create_order(db: Session, data: PurchaseOrderCreate, idempotency_key: str | None) -> tuple[int, bool]:
    """Returns (order id, created). Replaying a key with the same body returns the original order."""
    fingerprint = _fingerprint(data)

    def replay() -> int | None:
        if not idempotency_key:
            return None
        existing = db.scalar(select(PurchaseOrder).where(PurchaseOrder.idempotency_key == idempotency_key))
        if existing is None:
            return None
        if existing.request_fingerprint != fingerprint:
            raise ConflictError("This Idempotency-Key was already used for a different purchase-order request")
        return existing.id

    previous = replay()
    if previous is not None:
        return previous, False

    _require_eligible_supplier(db, data.supplier_id)
    _require_yard(db, data.delivery_yard_id)
    _validate_lines(db, data.lines)
    order = PurchaseOrder(
        supplier_id=data.supplier_id, status=S.DRAFT, expected_delivery_date=data.expected_delivery_date,
        delivery_yard_id=data.delivery_yard_id,
        notes=data.notes, created_by=data.actor, version=1, idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
    )
    db.add(order)
    try:
        db.flush()
        db.add_all(_new_lines(order.id, data.lines))
        _event(db, order, "created", None, data.actor, changes={"lines": len(data.lines)})
        db.commit()
    except IntegrityError:
        db.rollback()
        previous = replay()
        if previous is not None:
            return previous, False
        raise
    return order.id, True


def _lock(db: Session, order_id: int, expected_version: int) -> PurchaseOrder:
    order = db.scalar(
        select(PurchaseOrder).where(PurchaseOrder.id == order_id)
        .with_for_update().execution_options(populate_existing=True)
    )
    if order is None:
        raise ItemNotFoundError("Purchase order", _label(order_id))
    if order.version != expected_version:
        raise ConflictError(
            f"{_label(order.id)} was changed by another update (now version {order.version}, you have version "
            f"{expected_version}). Reload and try again."
        )
    return order


def _lock_lines(db: Session, order: PurchaseOrder) -> list[PurchaseOrderLine]:
    return list(db.scalars(
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == order.id)
        .order_by(PurchaseOrderLine.id).with_for_update().execution_options(populate_existing=True)
    ))


def _require_status(order: PurchaseOrder, allowed: set[S], verb: str) -> S:
    if order.status not in allowed:
        raise ConflictError(f"{_label(order.id)} is {order.status.value.lower()} and cannot be {verb}")
    return order.status


def update_draft(db: Session, order_id: int, data: PurchaseOrderUpdate) -> None:
    order = _lock(db, order_id, data.expected_version)
    _require_status(order, {S.DRAFT}, "edited")
    sent = data.model_fields_set
    changed_fields = []

    if "supplier_id" in sent and data.supplier_id != order.supplier_id:
        _require_eligible_supplier(db, data.supplier_id)
        order.supplier_id = data.supplier_id
        changed_fields.append("supplier_id")
    if "delivery_yard_id" in sent:
        _require_yard(db, data.delivery_yard_id)
    for field in ("expected_delivery_date", "delivery_yard_id", "notes"):
        if field in sent and getattr(data, field) != getattr(order, field):
            setattr(order, field, getattr(data, field))
            changed_fields.append(field)

    changes: dict = {}
    if "lines" in sent:
        _validate_lines(db, data.lines)
        old_lines = _lock_lines(db, order)
        for line in old_lines:  # removed draft lines are deleted explicitly
            db.delete(line)
        db.flush()
        db.add_all(_new_lines(order.id, data.lines))
        changes["lines"] = {"before": len(old_lines), "after": len(data.lines)}

    if not changed_fields and not changes:
        db.rollback()
        return
    if changed_fields:
        changes["fields"] = changed_fields
    order.version += 1
    _event(db, order, "edited", S.DRAFT, data.actor, changes=changes)
    db.commit()


def approve(db: Session, order_id: int, data: PurchaseOrderAction) -> None:
    order = _lock(db, order_id, data.expected_version)
    previous = _require_status(order, {S.DRAFT}, "approved")
    lines = _lock_lines(db, order)
    problems = []
    if not lines:
        problems.append("it has no lines")
    if order.expected_delivery_date is None:
        problems.append("it has no expected delivery date")
    supplier = db.get(Supplier, order.supplier_id)
    if supplier.status in INELIGIBLE_SUPPLIER_STATUSES:
        problems.append(f"supplier '{supplier.name}' is {supplier.status.value}")
    if problems:
        raise InvalidInputError(f"{_label(order.id)} cannot be approved: " + "; ".join(problems))
    order.status = S.APPROVED
    order.approved_by = data.actor
    order.approved_at = func.now()  # the database clock, like every other timestamp
    order.version += 1
    _event(db, order, "approved", previous, data.actor, data.reason)
    db.commit()


def reopen(db: Session, order_id: int, data: PurchaseOrderReasonAction) -> None:
    order = _lock(db, order_id, data.expected_version)
    previous = _require_status(order, {S.APPROVED}, "reopened")
    if any(l.received_quantity or l.rejected_quantity for l in _lock_lines(db, order)):
        raise ConflictError(
            f"{_label(order.id)} already has goods receipts and cannot be reopened; close it instead")
    order.status = S.DRAFT
    order.approved_by = None
    order.approved_at = None
    order.version += 1
    _event(db, order, "reopened", previous, data.actor, data.reason)
    db.commit()


def cancel(db: Session, order_id: int, data: PurchaseOrderReasonAction) -> None:
    order = _lock(db, order_id, data.expected_version)
    previous = _require_status(order, {S.DRAFT, S.APPROVED}, "cancelled")
    lines = _lock_lines(db, order)
    if any(l.received_quantity for l in lines):
        raise ConflictError(f"{_label(order.id)} has accepted goods and cannot be cancelled; close it instead")
    for line in lines:
        line.cancelled_quantity = line.ordered_quantity - line.received_quantity
    order.status = S.CANCELLED
    order.version += 1
    _event(db, order, "cancelled", previous, data.actor, data.reason)
    db.commit()


def close(db: Session, order_id: int, data: PurchaseOrderReasonAction) -> None:
    order = _lock(db, order_id, data.expected_version)
    previous = _require_status(order, {S.PARTIALLY_RECEIVED}, "closed")
    cancelled = {}
    for line in _lock_lines(db, order):
        remainder = line.outstanding_quantity
        if remainder:
            line.cancelled_quantity += remainder
            cancelled[str(line.line_no)] = remainder
    order.status = S.CLOSED
    order.version += 1
    _event(db, order, "closed", previous, data.actor, data.reason, changes={"cancelled_by_line": cancelled})
    db.commit()


def recalculate_status(lines: list[PurchaseOrderLine]) -> S:
    """Status after a goods receipt. Rejected-only deliveries never count as fulfilment."""
    if all(l.outstanding_quantity == 0 for l in lines):
        return S.RECEIVED
    if any(l.received_quantity > 0 for l in lines):
        return S.PARTIALLY_RECEIVED
    return S.APPROVED
