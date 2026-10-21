"""Read-only aggregates for the dashboard cards that have no other API."""

from datetime import date

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.models.facility import StorageLocation, Yard
from app.models.material import Material
from app.models.program import Ship
from app.models.transaction import MaterialTransaction, TransactionType as T

# Ledger types that move stock into or out of a batch. Inspection holds and releases only move stock
# between blocked and available, and transit-shortage adjustments record stock that had already left,
# so they are neither.
STOCK_IN = (T.RECEIPT, T.TRANSFER_IN)
STOCK_OUT = (T.TRANSFER_OUT, T.ISSUANCE, T.SCRAP, T.RETURN)


def _month_start(today: date, months_back: int) -> date:
    index = today.year * 12 + today.month - 1 - months_back
    return date(index // 12, index % 12 + 1, 1)


def movements(db: Session, months: int, today: date | None = None) -> dict:
    """Ledger entries per calendar month, oldest first, counted rather than summed because batches use
    different units. Months without entries are included with zeros."""
    today = today or date.today()
    start = _month_start(today, months - 1)
    year, month = extract("year", MaterialTransaction.created_at), extract("month", MaterialTransaction.created_at)
    rows = db.execute(
        select(year, month, MaterialTransaction.transaction_type, func.count())
        .where(MaterialTransaction.created_at >= start,
               MaterialTransaction.transaction_type.in_(STOCK_IN + STOCK_OUT))
        .group_by(year, month, MaterialTransaction.transaction_type)
    ).all()
    counts: dict[tuple[int, int], dict[str, int]] = {}
    for y, m, kind, n in rows:
        bucket = counts.setdefault((int(y), int(m)), {"stock_in": 0, "stock_out": 0})
        bucket["stock_in" if kind in STOCK_IN else "stock_out"] += n
    series = []
    for back in range(months - 1, -1, -1):
        first = _month_start(today, back)
        series.append({"month": f"{first:%Y-%m}", **counts.get((first.year, first.month), {"stock_in": 0, "stock_out": 0})})
    return {
        "months": series,
        "stock_in_types": [t.value for t in STOCK_IN],
        "stock_out_types": [t.value for t in STOCK_OUT],
    }


def ships(db: Session) -> list[dict]:
    """Every ship with its build status and the batches allocated to it."""
    allocated = (
        select(Material.ship_id, func.count(Material.id).label("batches"),
               func.count(Material.id).filter(Material.reserved > 0).label("reserved_batches"))
        .where(Material.ship_id.is_not(None)).group_by(Material.ship_id).subquery()
    )
    rows = db.execute(
        select(Ship, Yard.name, func.coalesce(allocated.c.batches, 0), func.coalesce(allocated.c.reserved_batches, 0))
        .join(Yard, Yard.id == Ship.yard_id)
        .outerjoin(allocated, allocated.c.ship_id == Ship.id)
        .order_by(Ship.name)
    ).all()
    return [
        {"id": s.id, "name": s.name, "yard": yard_name, "build_status": s.build_status.value,
         "build_progress": s.build_progress, "allocated_batches": batches, "reserved_batches": reserved}
        for s, yard_name, batches, reserved in rows
    ]


def yards(db: Session) -> list[dict]:
    """Every yard with its storage locations, batches and ships counted."""
    def per_yard(column, key):
        return select(key.label("yard_id"), func.count(column).label("n")).group_by(key).subquery()

    locations = per_yard(StorageLocation.id, StorageLocation.yard_id)
    batches = per_yard(Material.id, Material.yard_id)
    ship_rows = per_yard(Ship.id, Ship.yard_id)
    rows = db.execute(
        select(Yard, func.coalesce(locations.c.n, 0), func.coalesce(batches.c.n, 0), func.coalesce(ship_rows.c.n, 0))
        .outerjoin(locations, locations.c.yard_id == Yard.id)
        .outerjoin(batches, batches.c.yard_id == Yard.id)
        .outerjoin(ship_rows, ship_rows.c.yard_id == Yard.id)
        .order_by(Yard.name)
    ).all()
    return [
        {"id": y.id, "name": y.name, "location": y.location, "status": y.status.value, "capacity": y.capacity,
         "storage_locations": n_locations, "batches": n_batches, "ships": n_ships}
        for y, n_locations, n_batches, n_ships in rows
    ]
