"""Tests for GET /api/v1/materials/summary (dashboard KPI aggregates)."""

import pytest

from app.models.facility import StorageLocation, Yard, YardStatusEnum
from app.models.material import Material, MaterialCategory, MaterialStatusEnum
from app.models.program import Ship, ShipSeries

S = MaterialStatusEnum


def summary(client):
    r = client.get("/api/v1/materials/summary")
    assert r.status_code == 200, r.text
    return r.json()["data"]


@pytest.fixture
def refs(db):
    db.add_all([
        MaterialCategory(id="C", name="Cat"),
        Yard(id="Y1", name="Yard 1", location="a", capacity=1.0),
        Yard(id="Y2", name="Yard 2", location="b", capacity=1.0),
        Yard(id="Y3", name="Yard 3", location="c", capacity=1.0, status=YardStatusEnum.CLOSED),
        ShipSeries(id="SER", name="Series"),
    ])
    db.commit()
    db.add_all([
        StorageLocation(id="L1", yard_id="Y1", zone="A", aisle="1", capacity=10),
        Ship(id="S1", name="Ship 1", series_id="SER", yard_id="Y1", allocated_value=0.0),
    ])
    db.commit()


def batch(db, mid, quantity, available, reserved, status=S.HEALTHY, ship_id=None, yard_id="Y1", location_id="L1"):
    db.add(Material(id=mid, name=mid, category_id="C", batch="B", unit="u", quantity=quantity, available=available,
                    reserved=reserved, status=status, ship_id=ship_id, yard_id=yard_id, location_id=location_id))
    db.commit()


def test_route_is_not_shadowed_by_material_id(client):
    r = client.get("/api/v1/materials/summary")
    assert r.status_code == 200
    assert r.json()["message"] == "Material summary retrieved successfully"


def test_empty_database_returns_zeros_without_dividing_by_zero(client):
    assert summary(client) == {
        "total_batches": 0, "available_batches": 0, "available_percent": 0.0, "reserved_batches": 0,
        "low_stock_batches": 0, "low_stock_ship_allocated": 0, "active_yards": 0,
    }


def test_active_yards_counts_only_active(client, refs):
    assert summary(client)["active_yards"] == 2


def test_mixed_batch_states(client, db, refs):
    batch(db, "A", 10, 10, 0)                                   # available
    batch(db, "B", 10, 4, 6)                                    # available + reserved
    batch(db, "C", 10, 0, 10)                                   # fully reserved
    batch(db, "D", 5, 0, 0)                                     # blocked only (inspection stock)
    batch(db, "E", 0, 0, 0)                                     # empty batch
    batch(db, "F", 8, 2, 3, status=S.LOW_STOCK, ship_id="S1")   # low stock, ship-allocated
    batch(db, "G", 8, 1, 0, status=S.LOW_STOCK)                 # low stock, not allocated
    batch(db, "H", 8, 8, 0, status=S.INSPECTION, ship_id="S1")  # other statuses are not low stock
    batch(db, "I", 8, 0, 8, status=S.RESERVED)
    s = summary(client)
    assert s["total_batches"] == 9
    assert s["available_batches"] == 5          # A, B, F, G, H
    assert s["available_percent"] == round(5 * 100 / 9, 1) == 55.6
    assert s["reserved_batches"] == 4           # B, C, F, I
    assert s["low_stock_batches"] == 2          # F, G — exact status only
    assert s["low_stock_ship_allocated"] == 1   # F
    assert s["active_yards"] == 2


def test_percentage_is_100_when_every_batch_has_available_stock(client, db, refs):
    batch(db, "A", 3, 3, 0)
    batch(db, "B", 3, 1, 2)
    assert summary(client)["available_percent"] == 100.0


def test_low_stock_follows_manual_status_changes(client, db, refs):
    batch(db, "A", 10, 10, 0)
    v = client.get("/api/v1/materials/A").json()["data"]["version"]
    assert client.patch("/api/v1/materials/A", json={"status": "Low stock", "ship_id": "S1", "expected_version": v}).status_code == 200
    s = summary(client)
    assert (s["low_stock_batches"], s["low_stock_ship_allocated"]) == (1, 1)
    assert client.patch("/api/v1/materials/A", json={"ship_id": None, "expected_version": v + 1}).status_code == 200
    s = summary(client)
    assert (s["low_stock_batches"], s["low_stock_ship_allocated"]) == (1, 0)
    assert client.patch("/api/v1/materials/A", json={"status": "Healthy", "expected_version": v + 2}).status_code == 200
    assert summary(client)["low_stock_batches"] == 0


def test_batch_emptied_by_transfer_leaves_available_count(client, db, refs):
    batch(db, "W", 5, 5, 0)
    batch(db, "K", 5, 5, 0)
    assert summary(client)["available_batches"] == 2

    tid = client.post("/api/v1/transfers", json={"material_id": "W", "quantity": 5, "to_yard_id": "Y2", "actor": "t"}).json()["data"]["id"]
    client.post(f"/api/v1/transfers/{tid}/approve", json={"actor": "t"})
    assert client.post(f"/api/v1/transfers/{tid}/dispatch", json={"actor": "t"}).status_code == 200
    s = summary(client)
    assert (s["total_batches"], s["available_batches"], s["available_percent"]) == (2, 1, 50.0)

    assert client.post(f"/api/v1/transfers/{tid}/receive", json={"actor": "t"}).status_code == 200  # whole-batch relocation
    s = summary(client)
    assert (s["total_batches"], s["available_batches"]) == (2, 2)


def test_partial_transfer_receipt_adds_a_batch(client, db, refs):
    batch(db, "P", 10, 10, 0)
    tid = client.post("/api/v1/transfers", json={"material_id": "P", "quantity": 4, "to_yard_id": "Y2", "actor": "t"}).json()["data"]["id"]
    client.post(f"/api/v1/transfers/{tid}/approve", json={"actor": "t"})
    client.post(f"/api/v1/transfers/{tid}/dispatch", json={"actor": "t"})
    assert client.post(f"/api/v1/transfers/{tid}/receive", json={"actor": "t", "destination_material_id": "P-Y2"}).status_code == 200
    s = summary(client)
    assert (s["total_batches"], s["available_batches"]) == (2, 2)
