"""Goods-receipt posting: the only procurement operation that changes stock.

One transaction locks the purchase order, its lines and every destination batch (in ID order), checks
the order's expected version and status, validates every line against what is still outstanding, then
writes the receipt, the stock increase, a RECEIPT ledger row per accepted line, the order-line
quantities, the recalculated order status and an audit event together. A replayed Idempotency-Key
returns the original receipt instead of adding stock again. A line marked hold_for_inspection puts its
accepted quantity into a new batch on hold (on hand, not available) and opens an inspection hold.
"""

import hashlib
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.errors import ConflictError, InvalidInputError, ItemNotFoundError
from app.models.facility import StorageLocation, Yard
from app.models.goods_receipt import GoodsReceipt, GoodsReceiptLine
from app.models.material import Material, MaterialStatusEnum
from app.models.purchase_order import OPEN_PURCHASE_ORDER_STATUSES, PurchaseOrder
from app.models.transaction import MaterialTransaction, TransactionType
from app.schemas.goods_receipt import GoodsReceiptCreate
from app.services import inspection_service as inspections
from app.services import purchase_order_service as orders
from app.services.transfer_service import _lock_materials

RECEIPT_OPTIONS = (
    selectinload(GoodsReceipt.yard),
    selectinload(GoodsReceipt.location),
    selectinload(GoodsReceipt.lines).selectinload(GoodsReceiptLine.purchase_order_line),
    selectinload(GoodsReceipt.lines).selectinload(GoodsReceiptLine.inspection_hold),
)


def _label(receipt_id: int) -> str:
    return f"GR-{receipt_id:05d}"


def get_receipt(db: Session, receipt_id: int) -> GoodsReceipt:
    receipt = db.scalar(select(GoodsReceipt).where(GoodsReceipt.id == receipt_id)
                        .options(*RECEIPT_OPTIONS).execution_options(populate_existing=True))
    if receipt is None:
        raise ItemNotFoundError("Goods receipt", _label(receipt_id))
    return receipt


def list_receipts(db: Session, order_id: int) -> list[GoodsReceipt]:
    if db.get(PurchaseOrder, order_id) is None:
        raise ItemNotFoundError("Purchase order", orders._label(order_id))
    return list(db.scalars(select(GoodsReceipt).where(GoodsReceipt.purchase_order_id == order_id)
                           .options(*RECEIPT_OPTIONS).order_by(GoodsReceipt.id)))


def _fingerprint(order_id: int, data: GoodsReceiptCreate) -> str:
    payload = {"purchase_order_id": order_id, **data.model_dump(mode="json")}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def post_receipt(db: Session, order_id: int, data: GoodsReceiptCreate, idempotency_key: str | None) -> tuple[int, bool]:
    """Returns (receipt id, created)."""
    if not idempotency_key:
        raise InvalidInputError("An Idempotency-Key header is required to post a goods receipt")
    fingerprint = _fingerprint(order_id, data)

    def replay() -> int | None:
        existing = db.scalar(select(GoodsReceipt).where(GoodsReceipt.idempotency_key == idempotency_key))
        if existing is None:
            return None
        if existing.request_fingerprint != fingerprint:
            raise ConflictError("This Idempotency-Key was already used for a different goods receipt")
        return existing.id

    previous = replay()
    if previous is not None:
        return previous, False

    try:
        order = orders._lock(db, order_id, data.expected_version)
    except ConflictError:
        # A duplicate that passed the lookup above while the original was still in flight waited for the
        # order lock and now sees the original's version bump. The original has committed by the time the
        # lock is granted, so look the key up again: replay it if it matches, otherwise keep the conflict.
        previous = replay()
        if previous is None:
            raise
        db.rollback()  # release the order lock before the caller reads the receipt
        return previous, False
    previous_status = orders._require_status(order, set(OPEN_PURCHASE_ORDER_STATUSES), "received")
    order_lines = {line.id: line for line in orders._lock_lines(db, order)}

    if db.get(Yard, data.yard_id) is None:
        raise InvalidInputError(f"Yard '{data.yard_id}' does not exist")
    if data.location_id:
        location = db.get(StorageLocation, data.location_id)
        if location is None:
            raise InvalidInputError(f"Storage location '{data.location_id}' does not exist")
        if location.yard_id != data.yard_id:
            raise InvalidInputError(f"Storage location '{data.location_id}' does not belong to yard '{data.yard_id}'")

    seen_lines, seen_batches = set(), set()
    for line in data.lines:
        order_line = order_lines.get(line.purchase_order_line_id)
        if order_line is None:
            raise InvalidInputError(f"Line {line.purchase_order_line_id} is not on {orders._label(order.id)}")
        if line.purchase_order_line_id in seen_lines:
            raise InvalidInputError(f"Order line {order_line.line_no} appears more than once in this receipt")
        seen_lines.add(line.purchase_order_line_id)
        delivered = line.accepted_quantity + line.rejected_quantity
        if delivered > order_line.outstanding_quantity:
            raise InvalidInputError(
                f"Line {order_line.line_no}: {delivered} {order_line.unit} delivered but only "
                f"{order_line.outstanding_quantity} outstanding; over-delivery is not accepted")
        if line.accepted_quantity:
            if line.destination_material_id in seen_batches:
                raise InvalidInputError(
                    f"Batch {line.destination_material_id} is used by more than one line; use one batch per line")
            seen_batches.add(line.destination_material_id)

    batches = _lock_materials(db, *seen_batches)
    for line in data.lines:
        if not line.accepted_quantity:
            continue
        order_line = order_lines[line.purchase_order_line_id]
        batch = batches.get(line.destination_material_id)
        if batch is not None and line.hold_for_inspection:
            raise InvalidInputError(
                f"Line {order_line.line_no}: goods held for inspection go into a new batch, and "
                f"{batch.id} already exists. Give a new batch ID")
        if batch is None:
            if not line.batch:
                raise InvalidInputError(
                    f"Line {order_line.line_no}: a batch number is required to create batch {line.destination_material_id}")
            batch = Material(
                id=line.destination_material_id, name=order_line.description, category_id=order_line.category_id,
                batch=line.batch, unit=order_line.unit,
                status=MaterialStatusEnum.INSPECTION if line.hold_for_inspection else MaterialStatusEnum.HEALTHY,
                quantity=0, available=0, reserved=0, yard_id=data.yard_id, location_id=data.location_id, version=1,
            )
            db.add(batch)
            batches[batch.id] = batch
        else:
            problems = []
            if batch.yard_id != data.yard_id:
                problems.append(f"it is in yard {batch.yard_id}, not {data.yard_id}")
            if data.location_id and batch.location_id != data.location_id:
                problems.append(f"it is at location {batch.location_id or 'none'}, not {data.location_id}")
            if batch.category_id != order_line.category_id:
                problems.append(f"its category is {batch.category_id!r}, not {order_line.category_id!r}")
            if batch.unit != order_line.unit:
                problems.append(f"its unit is {batch.unit!r}, not {order_line.unit!r}")
            if line.batch and batch.batch != line.batch:
                problems.append(f"its batch number is {batch.batch!r}, not {line.batch!r}")
            if batch.status == MaterialStatusEnum.INSPECTION:
                problems.append("it is under inspection")
            if problems:
                raise InvalidInputError(f"Batch {batch.id} cannot receive line {order_line.line_no}: " + "; ".join(problems))
        batch.quantity += line.accepted_quantity
        if not line.hold_for_inspection:  # held goods stay blocked until an inspection releases them
            batch.available += line.accepted_quantity
        batch.version += 1

    receipt = GoodsReceipt(
        purchase_order_id=order.id, yard_id=data.yard_id, location_id=data.location_id,
        delivery_note=data.delivery_note, notes=data.notes, received_by=data.actor,
        idempotency_key=idempotency_key, request_fingerprint=fingerprint,
    )
    db.add(receipt)
    try:
        db.flush()
        accepted_total = rejected_total = held_total = 0
        for line in data.lines:
            order_line = order_lines[line.purchase_order_line_id]
            receipt_line = GoodsReceiptLine(
                goods_receipt_id=receipt.id, purchase_order_line_id=order_line.id,
                accepted_quantity=line.accepted_quantity, rejected_quantity=line.rejected_quantity,
                rejection_reason=line.rejection_reason,
                destination_material_id=line.destination_material_id if line.accepted_quantity else None,
            )
            db.add(receipt_line)
            order_line.received_quantity += line.accepted_quantity
            order_line.rejected_quantity += line.rejected_quantity
            accepted_total += line.accepted_quantity
            rejected_total += line.rejected_quantity
            if line.accepted_quantity:
                db.add(MaterialTransaction(
                    id=f"TXN-{uuid4().hex[:24]}", material_id=line.destination_material_id,
                    transaction_type=TransactionType.RECEIPT, quantity=line.accepted_quantity, unit=order_line.unit,
                    to_location_id=data.location_id, reference_id=_label(receipt.id), actor=data.actor,
                    reason=f"{orders._label(order.id)} line {order_line.line_no}", status="Completed",
                ))
            if line.hold_for_inspection:
                db.flush()
                inspections.open_hold(db, batches[line.destination_material_id], receipt_line, _label(receipt.id),
                                      line.accepted_quantity, data.actor)
                held_total += line.accepted_quantity
        order.status = orders.recalculate_status(list(order_lines.values()))
        order.version += 1
        orders._event(db, order, "received", previous_status, data.actor, changes={
            "receipt": _label(receipt.id), "accepted": accepted_total, "rejected": rejected_total,
            "held": held_total})
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = replay()
        if existing is not None:
            return existing, False
        raise
    return receipt.id, True
