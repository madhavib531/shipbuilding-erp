"""Read-only material aggregates for dashboards."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.facility import Yard, YardStatusEnum
from app.models.material import Material, MaterialStatusEnum


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
