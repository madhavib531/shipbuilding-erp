"""Transfer lifecycle and stock movement.

Each public mutation runs in the caller's session and commits exactly once. Rows are locked with
SELECT ... FOR UPDATE (transfer first, then materials in ID order) so concurrent requests on the same
transfer or batch serialize; the second request re-reads committed state and fails its status or
stock check. Any exception must be followed by a rollback, so stock, transfer state, ledger rows
and audit events are written together or not at all.
"""

import hashlib
import json
from datetime import date, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.errors import ConflictError, InvalidInputError, ItemNotFoundError
from app.models.facility import StorageLocation, Yard
from app.models.material import Material
from app.models.program import Ship
from app.models.transaction import MaterialTransaction, TransactionType
from app.models.transfer import MaterialTransfer, MaterialTransferEvent, TransferStatus as S
from app.schemas.transfer import TransferCreate, TransferReceive

_DETAIL_OPTIONS = (
    selectinload(MaterialTransfer.material),
    selectinload(MaterialTransfer.from_yard),
    selectinload(MaterialTransfer.to_yard),
    selectinload(MaterialTransfer.from_location),
    selectinload(MaterialTransfer.to_location),
    selectinload(MaterialTransfer.events),
)


def _label(transfer_id: int) -> str:
    return f"TR-{transfer_id:05d}"


def get_transfer(db: Session, transfer_id: int) -> MaterialTransfer:
    transfer = db.scalar(
        select(MaterialTransfer).where(MaterialTransfer.id == transfer_id)
        .options(*_DETAIL_OPTIONS).execution_options(populate_existing=True)
    )
    if transfer is None:
        raise ItemNotFoundError("Transfer", _label(transfer_id))
    return transfer


def list_transfers(db: Session, statuses: list[S], material_id: str, yard_id: str, skip: int, limit: int):
    query = select(MaterialTransfer)
    if statuses:
        query = query.where(MaterialTransfer.status.in_(statuses))
    if material_id:
        query = query.where(
            (MaterialTransfer.material_id == material_id) | (MaterialTransfer.destination_material_id == material_id)
        )
    if yard_id:
        query = query.where((MaterialTransfer.from_yard_id == yard_id) | (MaterialTransfer.to_yard_id == yard_id))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(
        query.options(*_DETAIL_OPTIONS)
        .order_by(MaterialTransfer.updated_at.desc(), MaterialTransfer.id.desc())
        .offset(skip).limit(limit)
    ).all()
    return total, items


def summary(db: Session) -> dict:
    counts = dict(db.execute(select(MaterialTransfer.status, func.count()).group_by(MaterialTransfer.status)).all())
    due_today = db.scalar(
        select(func.count()).select_from(MaterialTransfer)
        .where(MaterialTransfer.status == S.DISPATCHED, MaterialTransfer.expected_arrival == date.today())
    )
    received_this_week = db.scalar(
        select(func.count()).select_from(MaterialTransferEvent).where(
            MaterialTransferEvent.to_status == S.RECEIVED.value,
            MaterialTransferEvent.created_at >= datetime.now() - timedelta(days=7),
        )
    )
    return {
        "awaiting_approval": counts.get(S.REQUESTED, 0),
        "ready_to_dispatch": counts.get(S.APPROVED, 0),
        "in_transit": counts.get(S.DISPATCHED, 0),
        "due_today": due_today,
        "received_this_week": received_this_week,
    }


def _fingerprint(data: TransferCreate) -> str:
    return hashlib.sha256(json.dumps(data.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()


def _replay(existing: MaterialTransfer, fingerprint: str) -> int:
    if existing.request_fingerprint != fingerprint:
        raise ConflictError("This Idempotency-Key was already used for a different transfer request")
    return existing.id


def _event(db: Session, transfer: MaterialTransfer, action: str, from_status: S | None,
           actor: str, reason: str | None = None, quantity: int | None = None) -> None:
    db.add(MaterialTransferEvent(
        transfer_id=transfer.id, action=action,
        from_status=from_status.value if from_status else None, to_status=transfer.status.value,
        actor=actor, reason=reason, quantity=quantity,
    ))


def _ledger(db: Session, kind: TransactionType, material_id: str, quantity: int, transfer: MaterialTransfer,
            actor: str, reason: str | None = None, from_location: str | None = None,
            to_location: str | None = None) -> None:
    db.add(MaterialTransaction(
        id=f"TXN-{uuid4().hex[:24]}", material_id=material_id, transaction_type=kind,
        quantity=quantity, unit=transfer.unit, from_location_id=from_location, to_location_id=to_location,
        reference_id=_label(transfer.id), actor=actor, reason=reason, status="Completed",
    ))


def _lock_transfer(db: Session, transfer_id: int) -> MaterialTransfer:
    transfer = db.scalar(
        select(MaterialTransfer).where(MaterialTransfer.id == transfer_id)
        .with_for_update().execution_options(populate_existing=True)
    )
    if transfer is None:
        raise ItemNotFoundError("Transfer", _label(transfer_id))
    return transfer


def _lock_materials(db: Session, *material_ids: str) -> dict[str, Material]:
    ids = sorted({m for m in material_ids if m})
    rows = db.scalars(
        select(Material).where(Material.id.in_(ids)).order_by(Material.id)
        .with_for_update().execution_options(populate_existing=True)
    ).all()
    return {m.id: m for m in rows}


def _require_status(transfer: MaterialTransfer, allowed: set[S], verb: str) -> S:
    if transfer.status not in allowed:
        raise ConflictError(
            f"Transfer {_label(transfer.id)} is {transfer.status.value.lower()} and cannot be {verb}"
        )
    return transfer.status


def create_transfer(db: Session, data: TransferCreate, idempotency_key: str | None) -> tuple[int, bool]:
    """Returns (transfer id, created). A replay of the same key and payload returns the original."""
    fingerprint = _fingerprint(data)
    if idempotency_key:
        existing = db.scalar(select(MaterialTransfer).where(MaterialTransfer.idempotency_key == idempotency_key))
        if existing is not None:
            return _replay(existing, fingerprint), False

    material = db.get(Material, data.material_id)
    if material is None:
        raise InvalidInputError(f"Material '{data.material_id}' does not exist")
    if data.quantity > material.available:
        raise InvalidInputError(
            f"Only {material.available} {material.unit} of {material.id} are available; "
            f"{data.quantity} were requested"
        )
    if db.get(Yard, data.to_yard_id) is None:
        raise InvalidInputError(f"Yard '{data.to_yard_id}' does not exist")
    if data.to_location_id:
        location = db.get(StorageLocation, data.to_location_id)
        if location is None:
            raise InvalidInputError(f"Storage location '{data.to_location_id}' does not exist")
        if location.yard_id != data.to_yard_id:
            raise InvalidInputError(
                f"Storage location '{data.to_location_id}' does not belong to yard '{data.to_yard_id}'"
            )
    if data.to_yard_id == material.yard_id and data.to_location_id == material.location_id:
        raise InvalidInputError("The destination is the same yard and location as the source")

    transfer = MaterialTransfer(
        material_id=material.id, quantity=data.quantity, unit=material.unit,
        from_yard_id=material.yard_id, from_location_id=material.location_id,
        to_yard_id=data.to_yard_id, to_location_id=data.to_location_id, status=S.REQUESTED,
        expected_arrival=data.expected_arrival, notes=data.notes, requested_by=data.actor,
        idempotency_key=idempotency_key, request_fingerprint=fingerprint,
    )
    db.add(transfer)
    try:
        db.flush()
        _event(db, transfer, "requested", None, data.actor, data.notes, data.quantity)
        db.commit()
    except IntegrityError:
        db.rollback()
        if idempotency_key:
            existing = db.scalar(select(MaterialTransfer).where(MaterialTransfer.idempotency_key == idempotency_key))
            if existing is not None:
                return _replay(existing, fingerprint), False
        raise
    return transfer.id, True


def _simple_transition(db: Session, transfer_id: int, allowed: set[S], new: S, action: str, verb: str,
                       actor: str, reason: str | None) -> None:
    transfer = _lock_transfer(db, transfer_id)
    previous = _require_status(transfer, allowed, verb)
    transfer.status = new
    _event(db, transfer, action, previous, actor, reason)
    db.commit()


def approve(db: Session, transfer_id: int, actor: str, note: str | None) -> None:
    _simple_transition(db, transfer_id, {S.REQUESTED}, S.APPROVED, "approved", "approved", actor, note)


def reject(db: Session, transfer_id: int, actor: str, reason: str) -> None:
    _simple_transition(db, transfer_id, {S.REQUESTED}, S.REJECTED, "rejected", "rejected", actor, reason)


def cancel(db: Session, transfer_id: int, actor: str, reason: str) -> None:
    _simple_transition(db, transfer_id, {S.REQUESTED, S.APPROVED}, S.CANCELLED, "cancelled", "cancelled",
                       actor, reason)


def dispatch(db: Session, transfer_id: int, actor: str, note: str | None) -> None:
    transfer = _lock_transfer(db, transfer_id)
    previous = _require_status(transfer, {S.APPROVED}, "dispatched")
    source = _lock_materials(db, transfer.material_id).get(transfer.material_id)
    if source is None:
        raise ConflictError(f"Source material {transfer.material_id} no longer exists")
    if source.yard_id != transfer.from_yard_id or source.location_id != transfer.from_location_id:
        raise ConflictError(
            f"Source batch {source.id} has moved since this transfer was requested; "
            f"cancel {_label(transfer.id)} and request a new transfer"
        )
    if source.available < transfer.quantity:
        raise ConflictError(
            f"Only {source.available} {source.unit} of {source.id} are available; "
            f"{_label(transfer.id)} needs {transfer.quantity}"
        )

    transfer.whole_batch = source.quantity == transfer.quantity
    source.quantity -= transfer.quantity
    source.available -= transfer.quantity
    source.version += 1
    transfer.status = S.DISPATCHED
    _ledger(db, TransactionType.TRANSFER_OUT, source.id, transfer.quantity, transfer, actor, note,
            from_location=transfer.from_location_id, to_location=transfer.to_location_id)
    _event(db, transfer, "dispatched", previous, actor, note, transfer.quantity)
    db.commit()


def receive(db: Session, transfer_id: int, data: TransferReceive) -> None:
    transfer = _lock_transfer(db, transfer_id)
    previous = _require_status(transfer, {S.DISPATCHED}, "received")

    received = transfer.quantity if data.received_quantity is None else data.received_quantity
    if received > transfer.quantity:
        raise InvalidInputError(
            f"Received quantity {received} exceeds the dispatched quantity {transfer.quantity}"
        )
    shortage = transfer.quantity - received
    if shortage and not data.discrepancy_reason:
        raise InvalidInputError(
            f"discrepancy_reason is required: {shortage} {transfer.unit} of the dispatched "
            f"{transfer.quantity} were not received"
        )

    destination_id = None
    if received > 0:
        wanted = data.destination_material_id
        locked = _lock_materials(db, transfer.material_id, wanted)
        source = locked.get(transfer.material_id)
        if source is None:
            raise ConflictError(f"Source material {transfer.material_id} no longer exists")

        if wanted is None or wanted == source.id:
            relocatable = (
                transfer.whole_batch
                and source.quantity == 0
                and source.yard_id == transfer.from_yard_id
                and source.location_id == transfer.from_location_id
            )
            if not relocatable:
                raise InvalidInputError(
                    f"destination_material_id is required: {_label(transfer.id)} did not move the whole "
                    f"batch {source.id}, or stock has been added to it since dispatch. Give an existing "
                    f"compatible batch at the destination or a new batch ID"
                )
            source.yard_id = transfer.to_yard_id
            source.location_id = transfer.to_location_id
            if source.ship_id and db.get(Ship, source.ship_id).yard_id != transfer.to_yard_id:
                source.ship_id = None
            destination = source
        else:
            destination = locked.get(wanted)
            if destination is None:
                destination = Material(
                    id=wanted, name=source.name, category_id=source.category_id, batch=source.batch,
                    unit=source.unit, status=source.status, quantity=0, available=0, reserved=0,
                    yard_id=transfer.to_yard_id, location_id=transfer.to_location_id, version=1,
                )
                db.add(destination)
                db.flush()
            else:
                problems = []
                if destination.yard_id != transfer.to_yard_id:
                    problems.append(f"it is in yard {destination.yard_id}, not {transfer.to_yard_id}")
                if transfer.to_location_id and destination.location_id != transfer.to_location_id:
                    problems.append(f"it is at location {destination.location_id or 'none'}, not {transfer.to_location_id}")
                for field in ("category_id", "batch", "unit"):
                    if getattr(destination, field) != getattr(source, field):
                        problems.append(f"its {field} is {getattr(destination, field)!r}, not {getattr(source, field)!r}")
                if problems:
                    raise InvalidInputError(f"Batch {destination.id} cannot receive this transfer: " + "; ".join(problems))
                destination.version += 1

        destination.quantity += received
        destination.available += received
        destination_id = destination.id

    transfer.status = S.RECEIVED
    transfer.received_quantity = received
    transfer.destination_material_id = destination_id
    if received:
        _ledger(db, TransactionType.TRANSFER_IN, destination_id, received, transfer, data.actor,
                from_location=transfer.from_location_id, to_location=transfer.to_location_id)
    if shortage:
        _ledger(db, TransactionType.ADJUSTMENT, transfer.material_id, shortage, transfer, data.actor,
                reason=f"Transit shortage: {data.discrepancy_reason}")
    _event(db, transfer, "received", previous, data.actor, data.discrepancy_reason, received)
    db.commit()
