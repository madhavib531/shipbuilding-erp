"""Tests for database models."""

import pytest
from app.models.material import Material, MaterialCategory, MaterialStatusEnum
from app.models.facility import Yard, StorageLocation, YardStatusEnum
from app.models.program import Ship, ShipSeries, ShipBuildStatusEnum
from app.models.supplier import Supplier, SupplierStatusEnum


def test_material_category_creation(db):
    """Test MaterialCategory model creation."""
    category = MaterialCategory(
        id="STRUCT-STEEL",
        name="Structural Steel",
        description="Steel structural components"
    )
    db.add(category)
    db.commit()

    retrieved = db.query(MaterialCategory).filter_by(id="STRUCT-STEEL").first()
    assert retrieved is not None
    assert retrieved.name == "Structural Steel"


def test_material_creation_with_category(db):
    """Test Material model creation with category relationship."""
    category = MaterialCategory(id="STRUCT-STEEL", name="Structural Steel")
    db.add(category)
    db.commit()

    # Create a yard first (foreign key)
    yard = Yard(
        id="HARBOR-NORTH",
        name="Harbor North",
        location="Northern Harbor",
        capacity=5000.0,
    )
    db.add(yard)
    db.commit()

    material = Material(
        id="STL-10084",
        name="AH36 Steel Plate · 12mm",
        category_id="STRUCT-STEEL",
        batch="B-2408-19",
        quantity=284,
        available=212,
        reserved=72,
        unit="sheets",
        yard_id="HARBOR-NORTH",
        status=MaterialStatusEnum.HEALTHY,
    )
    db.add(material)
    db.commit()

    retrieved = db.query(Material).filter_by(id="STL-10084").first()
    assert retrieved is not None
    assert retrieved.available == 212
    assert retrieved.category.name == "Structural Steel"


def test_yard_creation(db):
    """Test Yard model creation."""
    yard = Yard(
        id="HARBOR-NORTH",
        name="Harbor North",
        location="Northern Shipyard",
        capacity=5000.0,
    )
    db.add(yard)
    db.commit()

    retrieved = db.query(Yard).filter_by(id="HARBOR-NORTH").first()
    assert retrieved is not None
    assert retrieved.status == YardStatusEnum.ACTIVE


def test_storage_location_creation(db):
    """Test StorageLocation model creation."""
    yard = Yard(
        id="HARBOR-NORTH",
        name="Harbor North",
        location="Northern Shipyard",
        capacity=5000.0,
    )
    db.add(yard)
    db.commit()

    location = StorageLocation(
        id="LOC-A1-01",
        yard_id="HARBOR-NORTH",
        zone="A1",
        aisle="01",
        bin="AA",
        capacity=100,
    )
    db.add(location)
    db.commit()

    retrieved = db.query(StorageLocation).filter_by(id="LOC-A1-01").first()
    assert retrieved is not None
    assert retrieved.zone == "A1"


def test_ship_series_creation(db):
    """Test ShipSeries model creation."""
    series = ShipSeries(
        id="CALYPSO-CLASS",
        name="MV Calypso Class",
        design_spec="Bulk carrier",
    )
    db.add(series)
    db.commit()

    retrieved = db.query(ShipSeries).filter_by(id="CALYPSO-CLASS").first()
    assert retrieved is not None


def test_ship_creation(db):
    """Test Ship model creation."""
    # Create prerequisites
    series = ShipSeries(id="CALYPSO-CLASS", name="MV Calypso Class")
    yard = Yard(
        id="HARBOR-NORTH",
        name="Harbor North",
        location="Northern Shipyard",
        capacity=5000.0,
    )
    db.add(series)
    db.add(yard)
    db.commit()

    ship = Ship(
        id="MV-CALYPSO",
        name="MV Calypso",
        series_id="CALYPSO-CLASS",
        yard_id="HARBOR-NORTH",
        build_progress=72,
        allocated_value=6400000.0,
    )
    db.add(ship)
    db.commit()

    retrieved = db.query(Ship).filter_by(id="MV-CALYPSO").first()
    assert retrieved is not None
    assert retrieved.build_progress == 72
    assert retrieved.series.name == "MV Calypso Class"


def test_supplier_creation(db):
    """Test Supplier model creation."""
    supplier = Supplier(
        id="NORDIC-MARINE",
        name="Nordic Marine Steel",
        contact_person="John Hansen",
        contact_email="john@nordic-marine.com",
        country="Sweden",
    )
    db.add(supplier)
    db.commit()

    retrieved = db.query(Supplier).filter_by(id="NORDIC-MARINE").first()
    assert retrieved is not None
    assert retrieved.status == SupplierStatusEnum.APPROVED
