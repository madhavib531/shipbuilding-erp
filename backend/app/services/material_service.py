"""Material aggregates for dashboards, and the ledger entries for manual stock changes.

Ledger semantics for manual changes: an inventory create or edit that sets or changes on-hand,
available or reserved writes one ADJUSTMENT row. Its quantity is the signed change in on-hand stock
(+ added, - removed, 0 when only available or reserved moved), and its reason lists every figure's
before -> after value followed by the user's reason. Other ADJUSTMENT rows (transit shortages written
by transfers) keep their existing meaning: a positive write-off referencing the transfer.
"""

from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.facility import Yard, YardStatusEnum
from app.models.material import Material, MaterialStatusEnum
from app.models.transaction import MaterialTransaction, TransactionType

STOCK_FIELDS = ("quantity", "available", "reserved")
_LABELS = {"quantity": "On hand", "available": "available", "reserved": "reserved"}


def stock_figures(material: Material) -> dict[str, int]:
    return {f: getattr(material, f) for f in STOCK_FIELDS}


def _entry(material: Material, change: int, actor: str, reason: str) -> MaterialTransaction:
    return MaterialTransaction(
        id=f"TXN-{uuid4().hex[:24]}", material_id=material.id, transaction_type=TransactionType.ADJUSTMENT,
        quantity=change, unit=material.unit,
        to_location_id=material.location_id if change > 0 else None,
        from_location_id=material.location_id if change < 0 else None,
        reference_id=None, actor=actor, reason=reason, status="Completed",
    )


def opening_balance(material: Material, actor: str, note: str | None) -> MaterialTransaction:
    """The ADJUSTMENT recording the stock a batch is created with."""
    f = stock_figures(material)
    reason = f"Opening balance: on hand {f['quantity']}, available {f['available']}, reserved {f['reserved']}"
    return _entry(material, f["quantity"], actor, f"{reason} — {note}" if note else reason)


def stock_adjustment(material: Material, before: dict[str, int], actor: str, reason: str) -> MaterialTransaction | None:
    """The ADJUSTMENT for an edit, or None when no stock figure actually changed."""
    after = stock_figures(material)
    changed = [f"{_LABELS[f]} {before[f]}→{after[f]}" for f in STOCK_FIELDS if before[f] != after[f]]
    if not changed:
        return None
    return _entry(material, after["quantity"] - before["quantity"], actor, f"{', '.join(changed)} — {reason}")


def summary(db: Session) -> dict:
    """Counts are per batch (material row): quantities use mixed units and cannot be summed.

    Low stock is the manually assigned status, not a computed reorder threshold.
    """
    low_stock = Material.status == MaterialStatusEnum.LOW_STOCK
    total, available, reserved, low, low_on_ship = db.execute(select(
        func.count(Material.id),
        func.count(Material.id).filter(Material.available > 0),
        func.count(Material.id).filter(Material.reserved > 0),
        func.count(Material.id).filter(low_stock),
        func.count(Material.id).filter(low_stock, Material.ship_id.is_not(None)),
    )).one()
    active_yards = db.scalar(select(func.count(Yard.id)).where(Yard.status == YardStatusEnum.ACTIVE))
    return {
        "total_batches": total,
        "available_batches": available,
        # Rounded down to one decimal so it only reads 100% when every batch has available stock.
        "available_percent": (available * 1000 // total) / 10 if total else 0.0,
        "reserved_batches": reserved,
        "low_stock_batches": low,
        "low_stock_ship_allocated": low_on_ship,
        "active_yards": active_yards,
    }
