"""Development-only seed for material reference data (categories, yards, locations, ships).

Run manually from the backend folder:  python -m scripts.seed_reference_data
Inserts rows whose IDs are missing. Never updates or deletes existing rows, and creates no materials.
"""

from app.database import SessionLocal
from app.models.material import MaterialCategory
from app.models.facility import Yard, StorageLocation
from app.models.program import Ship, ShipSeries, ShipBuildStatusEnum

CATEGORIES = [
    ("STRUCTURAL-STEEL", "Structural steel"),
    ("PIPING", "Piping"),
    ("ELECTRICAL", "Electrical"),
    ("MECHANICAL", "Mechanical"),
    ("OUTFITTING", "Outfitting"),
    ("CONSUMABLES", "Consumables"),
]

YARDS = [
    ("HARBOR-NORTH", "Harbor North", "Northern harbor", 50000.0),
    ("EAST-BASIN", "East Basin", "Eastern basin", 35000.0),
    ("DRY-DOCK-4", "Dry Dock 4", "Dry dock complex", 20000.0),
]

LOCATIONS = [
    ("HN-A1-01", "HARBOR-NORTH", "A1", "01", 500),
    ("HN-B2-01", "HARBOR-NORTH", "B2", "01", 500),
    ("EB-C1-01", "EAST-BASIN", "C1", "01", 400),
    ("DD4-D1-01", "DRY-DOCK-4", "D1", "01", 300),
]

SERIES = [
    ("BULK-CARRIER", "Bulk carrier series", "Bulk carrier"),
    ("NAVAL-SUPPORT", "Naval support series", "Naval support vessel"),
    ("OFFSHORE-SUPPORT", "Offshore support series", "Offshore support vessel"),
]

SHIPS = [
    ("MV-CALYPSO", "MV Calypso", "BULK-CARRIER", "HARBOR-NORTH", ShipBuildStatusEnum.ASSEMBLY),
    ("NS-ATLAS", "NS Atlas", "NAVAL-SUPPORT", "EAST-BASIN", ShipBuildStatusEnum.OUTFITTING),
    ("OSV-MERIDIAN", "OSV Meridian", "OFFSHORE-SUPPORT", "DRY-DOCK-4", ShipBuildStatusEnum.SYSTEMS_INTEGRATION),
]


def _add_missing(db, model, rows, build):
    existing = {row_id for (row_id,) in db.query(model.id)}
    added = [build(*row) for row in rows if row[0] not in existing]
    db.add_all(added)
    db.flush()
    print(f"{model.__tablename__}: {len(added)} added, {len(rows) - len(added)} already present")


def main():
    db = SessionLocal()
    try:
        _add_missing(db, MaterialCategory, CATEGORIES, lambda i, n: MaterialCategory(id=i, name=n))
        _add_missing(db, Yard, YARDS, lambda i, n, loc, cap: Yard(id=i, name=n, location=loc, capacity=cap))
        _add_missing(db, StorageLocation, LOCATIONS,
                     lambda i, y, z, a, cap: StorageLocation(id=i, yard_id=y, zone=z, aisle=a, capacity=cap))
        _add_missing(db, ShipSeries, SERIES, lambda i, n, spec: ShipSeries(id=i, name=n, design_spec=spec))
        _add_missing(db, Ship, SHIPS,
                     lambda i, n, s, y, st: Ship(id=i, name=n, series_id=s, yard_id=y, build_status=st, allocated_value=0.0))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
