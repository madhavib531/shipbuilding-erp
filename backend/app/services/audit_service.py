"""Read-only audit feed: one chronological view over the event records the system already keeps.

Sources: the stock ledger (material_transactions), transfer events, purchase-order events and
inspection events. They are combined with UNION ALL, with every column cast to one explicit type so
SQLite and PostgreSQL resolve the union identically; filters, ordering and pagination run in SQL.

Not covered, because nothing records them: supplier changes, and inventory edits made before stock
adjustments were recorded in the ledger. The application only appends to these tables, but the
database does not enforce immutability, so this is a history view, not a tamper-proof log.
"""

import re
from datetime import date, datetime, time, timedelta
from enum import Enum

from sqlalchemy import Integer, String, Text, and_, cast, func, literal, null, or_, select, union_all
from sqlalchemy.orm import Session

from app.models.inspection import InspectionEvent, InspectionHold
from app.models.material import Material
from app.models.purchase_order import PurchaseOrder, PurchaseOrderEvent
from app.models.supplier import Supplier
from app.models.transaction import MaterialTransaction, TransactionType
from app.models.transfer import MaterialTransfer, MaterialTransferEvent


class AuditSource(str, Enum):
    STOCK = "stock"
    TRANSFER = "transfer"
    PURCHASE_ORDER = "purchase_order"
    INSPECTION = "inspection"


SOURCE_LABELS = {AuditSource.STOCK: "Stock ledger", AuditSource.TRANSFER: "Transfer",
                 AuditSource.PURCHASE_ORDER: "Purchase order", AuditSource.INSPECTION: "Inspection"}
_PREFIX = {AuditSource.TRANSFER: "TR", AuditSource.PURCHASE_ORDER: "PO", AuditSource.INSPECTION: "QI"}
_RECORD_NUMBER = re.compile(r"^\s*(TR|PO|QI)-?0*(\d{1,9})\s*$", re.IGNORECASE)


def _s(column, length: int = 200):
    return cast(column, String(length))


def _union():
    """Every event source as rows of one shape. NULLs are typed so each column has a single SQL type.
    created_at is left uncast: it is already TIMESTAMP in every table, and SQLite's CAST AS DATETIME
    would turn it into a number."""
    no_int, no_str = cast(null(), Integer), cast(null(), String(200))
    stock = (
        select(
            literal(AuditSource.STOCK.value, String(20)).label("source"),
            _s(MaterialTransaction.id, 50).label("event_key"),
            no_int.label("event_seq"),  # ledger IDs are text; ties fall back to event_key
            no_int.label("record_number"),
            _s(MaterialTransaction.material_id, 50).label("material_id"),
            _s(Material.name).label("subject"),
            _s(Material.batch, 50).label("batch"),
            _s(MaterialTransaction.transaction_type, 30).label("action"),
            no_str.label("from_status"),
            no_str.label("to_status"),
            _s(MaterialTransaction.actor, 100).label("actor"),
            cast(MaterialTransaction.reason, Text).label("reason"),
            cast(MaterialTransaction.quantity, Integer).label("quantity"),
            _s(MaterialTransaction.unit, 20).label("unit"),
            _s(MaterialTransaction.reference_id, 50).label("detail"),
            MaterialTransaction.created_at.label("created_at"),
        ).join(Material, Material.id == MaterialTransaction.material_id)
    )
    transfer = (
        select(
            literal(AuditSource.TRANSFER.value, String(20)),
            _s(MaterialTransferEvent.id, 50),
            cast(MaterialTransferEvent.id, Integer),
            cast(MaterialTransferEvent.transfer_id, Integer),
            _s(MaterialTransfer.material_id, 50),
            _s(Material.name),
            _s(Material.batch, 50),
            _s(MaterialTransferEvent.action, 30),
            _s(MaterialTransferEvent.from_status),
            _s(MaterialTransferEvent.to_status),
            _s(MaterialTransferEvent.actor, 100),
            cast(MaterialTransferEvent.reason, Text),
            cast(MaterialTransferEvent.quantity, Integer),
            _s(MaterialTransfer.unit, 20),
            no_str,
            MaterialTransferEvent.created_at,
        ).join(MaterialTransfer, MaterialTransfer.id == MaterialTransferEvent.transfer_id)
        .join(Material, Material.id == MaterialTransfer.material_id)
    )
    order = (
        select(
            literal(AuditSource.PURCHASE_ORDER.value, String(20)),
            _s(PurchaseOrderEvent.id, 50),
            cast(PurchaseOrderEvent.id, Integer),
            cast(PurchaseOrderEvent.purchase_order_id, Integer),
            no_str,
            _s(Supplier.name),
            no_str,
            _s(PurchaseOrderEvent.action, 30),
            _s(PurchaseOrderEvent.from_status),
            _s(PurchaseOrderEvent.to_status),
            _s(PurchaseOrderEvent.actor, 100),
            cast(PurchaseOrderEvent.reason, Text),
            no_int,
            no_str,
            no_str,
            PurchaseOrderEvent.created_at,
        ).join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderEvent.purchase_order_id)
        .join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
    )
    inspection = (
        select(
            literal(AuditSource.INSPECTION.value, String(20)),
            _s(InspectionEvent.id, 50),
            cast(InspectionEvent.id, Integer),
            cast(InspectionEvent.hold_id, Integer),
            _s(InspectionHold.material_id, 50),
            _s(Material.name),
            _s(Material.batch, 50),
            _s(InspectionEvent.action, 30),
            _s(InspectionEvent.from_status),
            _s(InspectionEvent.to_status),
            _s(InspectionEvent.actor, 100),
            cast(InspectionEvent.reason, Text),
            cast(InspectionEvent.quantity, Integer),
            _s(Material.unit, 20),
            _s(InspectionEvent.disposition),
            InspectionEvent.created_at,
        ).join(InspectionHold, InspectionHold.id == InspectionEvent.hold_id)
        .join(Material, Material.id == InspectionHold.material_id)
    )
    return union_all(stock, transfer, order, inspection).subquery("audit")


def _contains(column, text: str):
    """Case-insensitive substring match that treats % and _ in the user's text literally."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")


def _record_label(source: AuditSource, number: int | None, material_id: str | None) -> str:
    return f"{_PREFIX[source]}-{number:05d}" if source in _PREFIX else material_id


def _action_label(source: AuditSource, action: str) -> str:
    if source == AuditSource.STOCK:
        return TransactionType[action].value if action in TransactionType.__members__ else action
    return action.replace("_", " ").capitalize()


def _order_change_note(action: str, changes: dict | None) -> str | None:
    """A short, factual summary of a purchase-order event's stored changes."""
    if not changes:
        return None
    if action == "received":
        held = f", {changes['held']} held for inspection" if changes.get("held") else ""
        return f"{changes.get('receipt')}: {changes.get('accepted')} accepted, {changes.get('rejected')} rejected{held}"
    if action == "inspection_rejected":
        return (f"{changes.get('inspection')}: {changes.get('quantity')} rejected on line {changes.get('line')} "
                f"({changes.get('disposition')})")
    if action == "edited":
        parts = [f"changed {', '.join(changes['fields'])}"] if changes.get("fields") else []
        if changes.get("lines"):
            parts.append(f"lines {changes['lines'].get('before')}→{changes['lines'].get('after')}")
        return "; ".join(parts) or None
    if action == "closed" and changes.get("cancelled_by_line"):
        return "Outstanding quantity cancelled on " + ", ".join(f"line {k}: {v}" for k, v in changes["cancelled_by_line"].items())
    return None


def list_events(db: Session, sources: list[AuditSource], search: str, actor: str,
                date_from: date | None, date_to: date | None, skip: int, limit: int) -> tuple[int, list[dict]]:
    audit = _union()
    conditions = []
    if sources:
        conditions.append(audit.c.source.in_([s.value for s in sources]))
    if actor.strip():
        conditions.append(_contains(audit.c.actor, actor.strip()))
    if date_from:
        conditions.append(audit.c.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        conditions.append(audit.c.created_at < datetime.combine(date_to + timedelta(days=1), time.min))
    term = search.strip()
    if term:
        matches = [_contains(audit.c[name], term) for name in
                   ("material_id", "subject", "batch", "action", "actor", "reason", "detail", "to_status")]
        # Actions are stored as TRANSFER_OUT or inspection_rejected but shown as "Transfer out"/"Inspection rejected".
        matches.append(_contains(func.replace(audit.c.action, "_", " "), term))
        number = _RECORD_NUMBER.match(term)
        if number:
            prefix, n = number.group(1).upper(), int(number.group(2))
            source = next(s for s, p in _PREFIX.items() if p == prefix)
            label = f"{prefix}-{n:05d}"
            # The record itself, plus ledger rows and notes that reference it (e.g. "TR-00001", "PO-00001 line 1").
            matches += [and_(audit.c.source == source.value, audit.c.record_number == n),
                        _contains(audit.c.detail, label), _contains(audit.c.reason, label)]
        conditions.append(or_(*matches))

    filtered = select(audit).where(*conditions)
    total = db.scalar(select(func.count()).select_from(filtered.subquery()))
    rows = db.execute(
        # Identical timestamps: by source, then numeric event ID (so event 10 sorts before 9), then key.
        # Within one source event_seq is either always set or always NULL, so NULL placement never matters.
        filtered.order_by(audit.c.created_at.desc(), audit.c.source.asc(), audit.c.event_seq.desc(),
                          audit.c.event_key.desc())
        .offset(skip).limit(limit)
    ).mappings().all()

    order_event_ids = [int(r["event_key"]) for r in rows if r["source"] == AuditSource.PURCHASE_ORDER.value]
    changes = dict(db.execute(select(PurchaseOrderEvent.id, PurchaseOrderEvent.changes)
                              .where(PurchaseOrderEvent.id.in_(order_event_ids))).all()) if order_event_ids else {}

    events = []
    for r in rows:
        source = AuditSource(r["source"])
        detail = r["detail"]
        if source == AuditSource.PURCHASE_ORDER:
            detail = _order_change_note(r["action"], changes.get(int(r["event_key"])))
        events.append({
            "key": f"{source.value}:{r['event_key']}",
            "source": source.value,
            "source_label": SOURCE_LABELS[source],
            "record": _record_label(source, r["record_number"], r["material_id"]),
            "material_id": r["material_id"],
            "subject": r["subject"],
            "batch": r["batch"],
            "action": _action_label(source, r["action"]),
            "from_status": r["from_status"],
            "to_status": r["to_status"],
            "actor": r["actor"],
            "reason": r["reason"],
            "quantity": r["quantity"],
            "unit": r["unit"],
            "detail": detail,
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        })
    return total, events
