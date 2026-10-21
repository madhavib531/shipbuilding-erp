"""Rule-based analytics over live data. Read-only; no model, no estimates.

Every figure is a count, sum, ratio or duration computed directly from stored records. Ratios are
None when there is nothing to divide by, so an empty dataset never shows a made-up 0% or 100%.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.goods_receipt import GoodsReceipt
from app.models.inspection import InspectionHold, InspectionStatus
from app.models.material import Material, MaterialCategory
from app.models.purchase_order import (
    OPEN_PURCHASE_ORDER_STATUSES, PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus,
)
from app.models.supplier import Supplier
from app.models.transfer import MaterialTransfer, MaterialTransferEvent, TransferStatus

WINDOW_DAYS = 90
AGE_BUCKETS = ((0, 90, "0–90 days"), (91, 180, "91–180 days"), (181, 365, "181–365 days"), (366, None, "Over 365 days"))
STALE_HOLD_DAYS = 7
STALE_REQUEST_DAYS = 3


def _ratio(part: float, whole: float) -> float | None:
    return round(part / whole, 4) if whole else None


def categories(db: Session) -> list[dict]:
    rows = db.execute(
        select(MaterialCategory.name, func.count(Material.id),
               func.count(Material.id).filter(Material.available > 0),
               func.count(Material.id).filter(Material.reserved > 0),
               func.count(Material.id).filter(Material.quantity > 0, Material.available == 0))
        .join(Material, Material.category_id == MaterialCategory.id)
        .group_by(MaterialCategory.name).order_by(func.count(Material.id).desc(), MaterialCategory.name)
    ).all()
    return [{"category": name, "batches": n, "with_available": avail, "with_reserved": reserved,
             "stock_but_none_available": blocked} for name, n, avail, reserved, blocked in rows]


def aging(db: Session, now: datetime) -> list[dict]:
    """Batches holding stock, by how long ago their record was created."""
    out = []
    for low, high, label in AGE_BUCKETS:
        conditions = [Material.quantity > 0, Material.created_at <= now - timedelta(days=low)]
        if high is not None:
            conditions.append(Material.created_at > now - timedelta(days=high + 1))
        out.append({"label": label, "batches": db.scalar(select(func.count()).select_from(Material).where(*conditions))})
    return out


def suppliers(db: Session) -> list[dict]:
    """Per supplier with at least one approved order: orders, deliveries, first-delivery punctuality and
    the share of delivered quantity that was rejected (at receipt or at inspection)."""
    placed = PurchaseOrder.status.notin_([PurchaseOrderStatus.DRAFT, PurchaseOrderStatus.CANCELLED])
    orders = db.execute(
        select(PurchaseOrder.id, Supplier.id, Supplier.name, PurchaseOrder.expected_delivery_date,
               select(func.min(GoodsReceipt.received_at)).where(GoodsReceipt.purchase_order_id == PurchaseOrder.id)
               .scalar_subquery())
        .join(Supplier, Supplier.id == PurchaseOrder.supplier_id).where(placed)
    ).all()
    quantities = dict(((sid, (int(rec or 0), int(rej or 0))) for sid, rec, rej in db.execute(
        select(PurchaseOrder.supplier_id, func.sum(PurchaseOrderLine.received_quantity), func.sum(PurchaseOrderLine.rejected_quantity))
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id).where(placed)
        .group_by(PurchaseOrder.supplier_id)
    ).all()))
    receipts = dict(db.execute(
        select(PurchaseOrder.supplier_id, func.count(GoodsReceipt.id))
        .join(PurchaseOrder, PurchaseOrder.id == GoodsReceipt.purchase_order_id).group_by(PurchaseOrder.supplier_id)
    ).all())

    stats: dict[str, dict] = {}
    for _, supplier_id, name, expected, first_receipt in orders:
        s = stats.setdefault(supplier_id, {"supplier_id": supplier_id, "supplier": name, "orders": 0,
                                           "orders_delivered": 0, "first_delivery_on_time": 0})
        s["orders"] += 1
        if first_receipt is not None:
            s["orders_delivered"] += 1
            if expected is not None and first_receipt.date() <= expected:
                s["first_delivery_on_time"] += 1
    result = []
    for supplier_id, s in stats.items():
        received, rejected = quantities.get(supplier_id, (0, 0))
        result.append({**s, "deliveries": receipts.get(supplier_id, 0),
                       "on_time_rate": _ratio(s["first_delivery_on_time"], s["orders_delivered"]),
                       "received_quantity": received, "rejected_quantity": rejected,
                       "rejection_rate": _ratio(rejected, received + rejected)})
    return sorted(result, key=lambda r: (-r["orders"], r["supplier"]))


def transfers(db: Session, now: datetime, today: date) -> dict:
    since = now - timedelta(days=WINDOW_DAYS)
    events = db.execute(
        select(MaterialTransferEvent.transfer_id, MaterialTransferEvent.action, MaterialTransferEvent.created_at)
        .join(MaterialTransfer, MaterialTransfer.id == MaterialTransferEvent.transfer_id)
        .where(MaterialTransfer.status == TransferStatus.RECEIVED,
               MaterialTransferEvent.action.in_(["dispatched", "received"]))
    ).all()
    moments: dict[int, dict[str, datetime]] = defaultdict(dict)
    for transfer_id, action, at in events:
        moments[transfer_id][action] = at
    lead_hours = [(m["received"] - m["dispatched"]).total_seconds() / 3600 for m in moments.values()
                  if "dispatched" in m and "received" in m and m["received"] >= since]
    received = db.execute(
        select(MaterialTransfer.quantity, MaterialTransfer.received_quantity)
        .where(MaterialTransfer.id.in_([t for t, m in moments.items() if m.get("received", since - timedelta(1)) >= since]))
    ).all() if moments else []
    return {
        "window_days": WINDOW_DAYS,
        "received": len(received),
        "with_shortage": sum(1 for q, r in received if r is not None and r < q),
        "average_lead_time_hours": round(sum(lead_hours) / len(lead_hours), 1) if lead_hours else None,
        "in_transit": db.scalar(select(func.count()).select_from(MaterialTransfer).where(MaterialTransfer.status == TransferStatus.DISPATCHED)),
        "in_transit_overdue": db.scalar(select(func.count()).select_from(MaterialTransfer).where(
            MaterialTransfer.status == TransferStatus.DISPATCHED, MaterialTransfer.expected_arrival < today)),
    }


def inspections(db: Session, now: datetime) -> dict:
    since = now - timedelta(days=WINDOW_DAYS)
    held, released, rejected = db.execute(
        select(func.coalesce(func.sum(InspectionHold.quantity), 0), func.coalesce(func.sum(InspectionHold.released_quantity), 0),
               func.coalesce(func.sum(InspectionHold.rejected_quantity), 0)).where(InspectionHold.created_at >= since)
    ).one()
    return {
        "window_days": WINDOW_DAYS,
        "holds_opened": db.scalar(select(func.count()).select_from(InspectionHold).where(InspectionHold.created_at >= since)),
        "quantity_held": int(held), "quantity_released": int(released), "quantity_rejected": int(rejected),
        "rejection_rate": _ratio(int(rejected), int(released) + int(rejected)),
        "open": db.scalar(select(func.count()).select_from(InspectionHold).where(InspectionHold.status == InspectionStatus.OPEN)),
    }


def attention(db: Session, now: datetime, today: date) -> list[dict]:
    """Fixed rules that flag records needing action. Each item names its rule and links to examples."""
    def flag(key, title, rule, page, rows):
        return {"key": key, "title": title, "rule": rule, "page": page, "count": len(rows), "examples": rows[:5]}

    overdue_orders = db.execute(
        select(PurchaseOrder.id, Supplier.name, PurchaseOrder.expected_delivery_date)
        .join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
        .where(PurchaseOrder.status.in_(OPEN_PURCHASE_ORDER_STATUSES), PurchaseOrder.expected_delivery_date < today)
        .order_by(PurchaseOrder.expected_delivery_date)
    ).all()
    late_transfers = db.execute(
        select(MaterialTransfer.id, MaterialTransfer.material_id, MaterialTransfer.expected_arrival)
        .where(MaterialTransfer.status == TransferStatus.DISPATCHED, MaterialTransfer.expected_arrival < today)
        .order_by(MaterialTransfer.expected_arrival)
    ).all()
    waiting_requests = db.execute(
        select(MaterialTransfer.id, MaterialTransfer.material_id, MaterialTransfer.created_at)
        .where(MaterialTransfer.status == TransferStatus.REQUESTED,
               MaterialTransfer.created_at < now - timedelta(days=STALE_REQUEST_DAYS))
        .order_by(MaterialTransfer.created_at)
    ).all()
    stale_holds = db.execute(
        select(InspectionHold.id, InspectionHold.material_id, InspectionHold.created_at)
        .where(InspectionHold.status == InspectionStatus.OPEN, InspectionHold.created_at < now - timedelta(days=STALE_HOLD_DAYS))
        .order_by(InspectionHold.created_at)
    ).all()
    unavailable = db.execute(
        select(Material.id, Material.name, Material.quantity)
        .where(Material.quantity > 0, Material.available == 0).order_by(Material.id)
    ).all()
    return [
        flag("overdue_orders", "Overdue purchase orders", "Open order past its expected delivery date", "Procurement",
             [f"PO-{i:05d} · {name} · due {d:%Y-%m-%d}" for i, name, d in overdue_orders]),
        flag("late_transfers", "Transfers in transit past expected arrival", "Dispatched, expected arrival has passed", "Movements",
             [f"TR-{i:05d} · {m} · expected {d:%Y-%m-%d}" for i, m, d in late_transfers]),
        flag("waiting_requests", f"Transfer requests waiting over {STALE_REQUEST_DAYS} days", "Requested and not yet approved or rejected", "Movements",
             [f"TR-{i:05d} · {m} · requested {d:%Y-%m-%d}" for i, m, d in waiting_requests]),
        flag("stale_holds", f"Inspection holds open over {STALE_HOLD_DAYS} days", "Held goods without a release or rejection", "Quality",
             [f"QI-{i:05d} · {m} · held since {d:%Y-%m-%d}" for i, m, d in stale_holds]),
        flag("unavailable_stock", "Batches with stock but none available", "On hand above 0, available 0 (reserved, held or blocked)", "Inventory",
             [f"{i} · {name} · {q} on hand" for i, name, q in unavailable]),
    ]


def overview(db: Session, now: datetime | None = None) -> dict:
    now = now or datetime.now()
    today = now.date()
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "categories": categories(db),
        "aging": aging(db, now),
        "suppliers": suppliers(db),
        "transfers": transfers(db, now, today),
        "inspections": inspections(db, now),
        "attention": attention(db, now, today),
    }
