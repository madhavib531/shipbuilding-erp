"""Inspection holds: opened by goods receipts or by hand on existing stock, closed by release or rejection.

Stock rules. A hold's outstanding quantity is on hand but blocked (counted in quantity, never in
available). A hold opened by hand takes its quantity out of the batch's available stock with an
INSPECTION ledger row; on-hand quantity is unchanged. Release moves held stock into available with a
RELEASE ledger row. Rejection removes it from on-hand stock with a RETURN or SCRAP ledger row. For a
receipt hold it also moves the quantity from received to rejected on the purchase-order line so the
supplier still owes it (on a closed order it is cancelled instead, as closing does). A hold opened by
hand has no supplier delivery behind it, so its rejected stock can only be scrapped.

Concurrency. Locks are taken in the same global order as goods receipts and transfers: purchase order,
its lines, the hold, then the batch. Opening a hold by hand locks only the batch. The hold's version is checked under its lock, so a repeated or
stale decision fails instead of applying twice. Each public mutation commits exactly once; callers
roll back on any exception.
"""

import re
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.errors import ConflictError, InvalidInputError, ItemNotFoundError
from app.models.goods_receipt import GoodsReceipt, GoodsReceiptLine
from app.models.inspection import InspectionEvent, InspectionHold, InspectionStatus as S, RejectionDisposition
from app.models.material import Material, MaterialStatusEnum
from app.models.purchase_order import PurchaseOrder, PurchaseOrderStatus
from app.models.transaction import MaterialTransaction, TransactionType
from app.schemas.inspection import InspectionCreate, InspectionReject, InspectionRelease
from app.services import purchase_order_service as orders
from app.services.transfer_service import _lock_materials

_QI_NUMBER = re.compile(r"^\s*(?:QI-?)?0*(\d{1,9})\s*$", re.IGNORECASE)

HOLD_OPTIONS = (
    selectinload(InspectionHold.material).selectinload(Material.yard),
    selectinload(InspectionHold.material).selectinload(Material.location),
    selectinload(InspectionHold.goods_receipt_line).selectinload(GoodsReceiptLine.purchase_order_line),
    selectinload(InspectionHold.goods_receipt_line).selectinload(GoodsReceiptLine.receipt)
    .selectinload(GoodsReceipt.purchase_order).selectinload(PurchaseOrder.supplier),
)
_DETAIL_OPTIONS = HOLD_OPTIONS + (selectinload(InspectionHold.events),)

_DISPOSITION_LEDGER = {
    RejectionDisposition.RETURN_TO_SUPPLIER: TransactionType.RETURN,
    RejectionDisposition.SCRAP: TransactionType.SCRAP,
}


def _label(hold_id: int) -> str:
    return f"QI-{hold_id:05d}"


def get_hold(db: Session, hold_id: int) -> InspectionHold:
    hold = db.scalar(select(InspectionHold).where(InspectionHold.id == hold_id)
                     .options(*_DETAIL_OPTIONS).execution_options(populate_existing=True))
    if hold is None:
        raise ItemNotFoundError("Inspection", _label(hold_id))
    return hold


def list_holds(db: Session, statuses: list[S], search: str, skip: int, limit: int, yard: str = ""):
    query = select(InspectionHold).join(Material, InspectionHold.material_id == Material.id)
    if yard:
        query = query.where(Material.yard_id == yard)
    if statuses:
        query = query.where(InspectionHold.status.in_(statuses))
    if search.strip():
        term = f"%{search.strip()}%"
        clauses = [Material.id.ilike(term), Material.name.ilike(term), Material.batch.ilike(term)]
        number = _QI_NUMBER.match(search)
        if number:
            clauses.append(InspectionHold.id == int(number.group(1)))
        query = query.where(or_(*clauses))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.options(*HOLD_OPTIONS).order_by(InspectionHold.id.desc()).offset(skip).limit(limit)).all()
    return total, items


def summary(db: Session, yard: str = "") -> dict:
    """`yard` limits the counts to holds on batches in that yard."""
    week_ago = datetime.now() - timedelta(days=7)
    in_yard = [InspectionHold.material_id.in_(select(Material.id).where(Material.yard_id == yard))] if yard else []

    def decided_this_week(action: str) -> int:
        return db.scalar(select(func.count(func.distinct(InspectionEvent.hold_id)))
                         .join(InspectionHold, InspectionHold.id == InspectionEvent.hold_id).where(
            InspectionEvent.action == action, InspectionEvent.created_at >= week_ago, *in_yard))

    return {
        "open": db.scalar(select(func.count()).select_from(InspectionHold).where(InspectionHold.status == S.OPEN, *in_yard)),
        "released_this_week": decided_this_week("released"),
        "rejected_this_week": decided_this_week("rejected"),
    }


def held_quantity(db: Session, material_id: str) -> int:
    """Quantity of the batch awaiting a decision. Stable while the caller holds the batch's row lock."""
    return db.scalar(select(func.coalesce(func.sum(
        InspectionHold.quantity - InspectionHold.released_quantity - InspectionHold.rejected_quantity), 0))
        .where(InspectionHold.material_id == material_id))


def _event(db: Session, hold: InspectionHold, action: str, from_status: S | None, actor: str, quantity: int,
           reason: str | None = None, disposition: RejectionDisposition | None = None) -> None:
    db.add(InspectionEvent(
        hold_id=hold.id, action=action, from_status=from_status.value if from_status else None,
        to_status=hold.status.value, quantity=quantity, disposition=disposition.value if disposition else None,
        actor=actor, reason=reason, version=hold.version,
    ))


def _ledger(db: Session, kind: TransactionType, hold: InspectionHold, material: Material, quantity: int,
            actor: str, reason: str | None) -> None:
    db.add(MaterialTransaction(
        id=f"TXN-{uuid4().hex[:24]}", material_id=material.id, transaction_type=kind, quantity=quantity,
        unit=material.unit, from_location_id=material.location_id, reference_id=_label(hold.id), actor=actor,
        reason=reason, status="Completed",
    ))


def open_hold(db: Session, material: Material, receipt_line: GoodsReceiptLine, receipt_label: str,
              quantity: int, actor: str) -> InspectionHold:
    """Called by goods receipts inside their transaction, with the batch locked and its stock already
    counted in quantity but not in available. Does not commit."""
    hold = InspectionHold(material_id=material.id, goods_receipt_line_id=receipt_line.id, quantity=quantity,
                          status=S.OPEN, created_by=actor, version=1)
    db.add(hold)
    db.flush()
    _ledger(db, TransactionType.INSPECTION, hold, material, quantity, actor, f"Held on receipt {receipt_label}")
    _event(db, hold, "held", None, actor, quantity, f"Received on {receipt_label}")
    return hold


def create_hold(db: Session, data: InspectionCreate) -> int:
    """Holds part of a batch's available stock for inspection. Returns the new hold's id."""
    material = _lock_materials(db, data.material_id).get(data.material_id)
    if material is None:
        raise ItemNotFoundError("Material", data.material_id)
    if data.quantity > material.available:
        raise InvalidInputError(
            f"Only {material.available} {material.unit} of {material.id} are available; {data.quantity} cannot be "
            f"held for inspection (reserved and already-held stock cannot be held again)")
    material.available -= data.quantity
    material.status = MaterialStatusEnum.INSPECTION
    material.version += 1
    hold = InspectionHold(material_id=material.id, goods_receipt_line_id=None, quantity=data.quantity,
                          status=S.OPEN, created_by=data.actor, version=1)
    db.add(hold)
    db.flush()
    _ledger(db, TransactionType.INSPECTION, hold, material, data.quantity, data.actor,
            f"Held for inspection: {data.reason}")
    _event(db, hold, "held", None, data.actor, data.quantity, data.reason)
    db.commit()
    return hold.id


def _lock_hold(db: Session, hold_id: int, expected_version: int, verb: str) -> InspectionHold:
    hold = db.scalar(select(InspectionHold).where(InspectionHold.id == hold_id)
                     .with_for_update().execution_options(populate_existing=True))
    if hold is None:
        raise ItemNotFoundError("Inspection", _label(hold_id))
    if hold.version != expected_version:
        raise ConflictError(
            f"{_label(hold.id)} was changed by another update (now version {hold.version}, you have version "
            f"{expected_version}). Reload and try again.")
    if hold.status != S.OPEN:
        raise ConflictError(f"{_label(hold.id)} is {hold.status.value.lower()} and cannot be {verb}")
    return hold


def _decide(db: Session, hold: InspectionHold, quantity: int, verb: str) -> Material:
    if quantity > hold.outstanding_quantity:
        raise InvalidInputError(
            f"Only {hold.outstanding_quantity} of {_label(hold.id)} await a decision; {quantity} cannot be {verb}")
    material = _lock_materials(db, hold.material_id).get(hold.material_id)
    if material is None:
        raise ConflictError(f"Batch {hold.material_id} of {_label(hold.id)} no longer exists")
    return material


def _close_if_done(db: Session, hold: InspectionHold, material: Material) -> None:
    hold.version += 1
    material.version += 1
    if hold.outstanding_quantity:
        return
    hold.status = (S.RELEASED if not hold.rejected_quantity else
                   S.REJECTED if not hold.released_quantity else S.PARTIALLY_RELEASED)
    other_open = db.scalar(select(func.count()).select_from(InspectionHold).where(
        InspectionHold.material_id == material.id, InspectionHold.status == S.OPEN, InspectionHold.id != hold.id))
    if not other_open and material.status == MaterialStatusEnum.INSPECTION:
        material.status = MaterialStatusEnum.HEALTHY


def release(db: Session, hold_id: int, data: InspectionRelease) -> None:
    hold = _lock_hold(db, hold_id, data.expected_version, "released")
    material = _decide(db, hold, data.quantity, "released")
    previous = hold.status
    hold.released_quantity += data.quantity
    material.available += data.quantity
    _ledger(db, TransactionType.RELEASE, hold, material, data.quantity, data.actor, data.note or "Passed inspection")
    _close_if_done(db, hold, material)
    _event(db, hold, "released", previous, data.actor, data.quantity, data.note)
    db.commit()


def _lock_order_for(db: Session, hold_id: int) -> tuple[PurchaseOrder, dict]:
    """Locks the hold's source purchase order and its lines before the hold itself (global lock order)."""
    order_id = db.scalar(
        select(GoodsReceipt.purchase_order_id)
        .join(GoodsReceiptLine, GoodsReceiptLine.goods_receipt_id == GoodsReceipt.id)
        .join(InspectionHold, InspectionHold.goods_receipt_line_id == GoodsReceiptLine.id)
        .where(InspectionHold.id == hold_id))
    if order_id is None:
        raise ItemNotFoundError("Inspection", _label(hold_id))
    order = db.scalar(select(PurchaseOrder).where(PurchaseOrder.id == order_id)
                      .with_for_update().execution_options(populate_existing=True))
    return order, {line.id: line for line in orders._lock_lines(db, order)}


def _reject_manual(db: Session, hold_id: int, data: InspectionReject) -> None:
    """Rejects stock from a hold opened by hand: it is scrapped; no purchase order is involved."""
    hold = _lock_hold(db, hold_id, data.expected_version, "rejected")
    if data.disposition != RejectionDisposition.SCRAP:
        raise InvalidInputError(
            f"{_label(hold.id)} was not opened by a goods receipt, so its stock cannot be returned to a supplier; "
            f"choose Scrap")
    material = _decide(db, hold, data.quantity, "rejected")
    previous = hold.status
    hold.rejected_quantity += data.quantity
    material.quantity -= data.quantity  # held stock is blocked, so available + reserved still fit
    _ledger(db, TransactionType.SCRAP, hold, material, data.quantity, data.actor, f"{data.disposition.value}: {data.reason}")
    _close_if_done(db, hold, material)
    _event(db, hold, "rejected", previous, data.actor, data.quantity, data.reason, data.disposition)
    db.commit()


def reject(db: Session, hold_id: int, data: InspectionReject) -> None:
    receipt_line_id = db.scalar(select(InspectionHold.goods_receipt_line_id).where(InspectionHold.id == hold_id))
    if receipt_line_id is None:
        if db.scalar(select(InspectionHold.id).where(InspectionHold.id == hold_id)) is None:
            raise ItemNotFoundError("Inspection", _label(hold_id))
        return _reject_manual(db, hold_id, data)
    order, order_lines = _lock_order_for(db, hold_id)
    hold = _lock_hold(db, hold_id, data.expected_version, "rejected")
    material = _decide(db, hold, data.quantity, "rejected")
    previous = hold.status

    hold.rejected_quantity += data.quantity
    material.quantity -= data.quantity  # held stock is blocked, so available + reserved still fit
    _ledger(db, _DISPOSITION_LEDGER[data.disposition], hold, material, data.quantity, data.actor,
            f"{data.disposition.value}: {data.reason}")

    line = order_lines[db.get(GoodsReceiptLine, hold.goods_receipt_line_id).purchase_order_line_id]
    previous_order_status = order.status
    line.received_quantity -= data.quantity
    line.rejected_quantity += data.quantity
    if order.status == PurchaseOrderStatus.CLOSED:
        line.cancelled_quantity += data.quantity  # a closed order expects no redelivery
    elif order.status in (PurchaseOrderStatus.APPROVED, PurchaseOrderStatus.PARTIALLY_RECEIVED,
                          PurchaseOrderStatus.RECEIVED):
        order.status = orders.recalculate_status(list(order_lines.values()))
    else:
        raise ConflictError(f"{orders._label(order.id)} is {order.status.value.lower()}; its goods cannot be rejected")
    order.version += 1
    orders._event(db, order, "inspection_rejected", previous_order_status, data.actor, data.reason, changes={
        "inspection": _label(hold.id), "line": line.line_no, "quantity": data.quantity,
        "disposition": data.disposition.value})

    _close_if_done(db, hold, material)
    _event(db, hold, "rejected", previous, data.actor, data.quantity, data.reason, data.disposition)
    db.commit()
