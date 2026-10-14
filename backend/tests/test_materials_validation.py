"""Relationship, quantity and partial-update validation for the Materials API."""

import pytest
from fastapi import status
from app.models.material import Material, MaterialCategory
from app.models.facility import Yard, StorageLocation
from app.models.program import Ship, ShipSeries


@pytest.fixture
def refs(db):
    db.add_all([
        MaterialCategory(id="STEEL", name="Steel"),
        Yard(id="Y1", name="Yard 1", location="North", capacity=1000.0),
        Yard(id="Y2", name="Yard 2", location="South", capacity=1000.0),
        ShipSeries(id="SER", name="Series"),
    ])
    db.commit()
    db.add_all([
        StorageLocation(id="L1", yard_id="Y1", zone="A", aisle="1", capacity=100),
        StorageLocation(id="L2", yard_id="Y2", zone="B", aisle="1", capacity=100),
        Ship(id="S1", name="Ship 1", series_id="SER", yard_id="Y1", allocated_value=0.0),
        Ship(id="S2", name="Ship 2", series_id="SER", yard_id="Y2", allocated_value=0.0),
    ])
    db.commit()


@pytest.fixture
def material(db, refs):
    db.add(Material(
        id="M1", name="Plate", category_id="STEEL", batch="B1", quantity=100,
        available=80, reserved=20, unit="sheets", yard_id="Y1", location_id="L1", ship_id="S1",
    ))
    db.commit()


def payload(**over):
    body = {
        "id": "NEW", "name": "New", "category_id": "STEEL", "batch": "B", "quantity": 10,
        "available": 10, "reserved": 0, "unit": "units", "yard_id": "Y1",
    }
    body.update(over)
    return body


class TestReferenceData:
    def test_empty(self, client):
        data = client.get("/api/v1/reference-data").json()["data"]
        assert data == {"categories": [], "yards": [], "locations": [], "ships": []}

    def test_lists_rows_with_yard_links(self, client, refs):
        data = client.get("/api/v1/reference-data").json()["data"]
        assert [c["id"] for c in data["categories"]] == ["STEEL"]
        assert [y["id"] for y in data["yards"]] == ["Y1", "Y2"]
        assert {(l["id"], l["yard_id"]) for l in data["locations"]} == {("L1", "Y1"), ("L2", "Y2")}
        assert {(s["id"], s["yard_id"]) for s in data["ships"]} == {("S1", "Y1"), ("S2", "Y2")}


class TestCreateRelationships:
    def test_create_with_location_and_ship_in_same_yard(self, client, refs):
        r = client.post("/api/v1/materials", json=payload(location_id="L1", ship_id="S1"))
        assert r.status_code == status.HTTP_201_CREATED
        data = r.json()["data"]
        assert data["location"]["zone"] == "A"
        assert data["ship"]["name"] == "Ship 1"
        assert data["yard"]["name"] == "Yard 1"

    def test_create_location_in_other_yard_rejected(self, client, refs):
        r = client.post("/api/v1/materials", json=payload(location_id="L2"))
        assert r.status_code == 422
        assert "does not belong" in r.json()["detail"]

    def test_create_ship_in_other_yard_rejected(self, client, refs):
        r = client.post("/api/v1/materials", json=payload(ship_id="S2"))
        assert r.status_code == 422
        assert "does not belong" in r.json()["detail"]

    def test_create_unknown_yard_location_ship_rejected(self, client, refs):
        assert client.post("/api/v1/materials", json=payload(yard_id="NOPE")).status_code == 422
        assert client.post("/api/v1/materials", json=payload(location_id="NOPE")).status_code == 422
        assert client.post("/api/v1/materials", json=payload(ship_id="NOPE")).status_code == 422

    def test_create_negative_quantity_rejected(self, client, refs):
        r = client.post("/api/v1/materials", json=payload(quantity=-1, available=0))
        assert r.status_code == 422

    def test_create_missing_required_field_rejected(self, client, refs):
        body = payload()
        del body["batch"]
        assert client.post("/api/v1/materials", json=body).status_code == 422


class TestPartialUpdate:
    def test_update_quantity_and_available_uses_stored_reserved(self, client, material):
        r = client.patch("/api/v1/materials/M1", json={"quantity": 100, "available": 60})
        assert r.status_code == 200, r.text
        assert r.json()["data"]["available"] == 60
        assert r.json()["data"]["reserved"] == 20

    def test_update_available_exceeding_stored_quantity_rejected(self, client, material):
        r = client.patch("/api/v1/materials/M1", json={"available": 90})
        assert r.status_code == 422

    def test_changing_yard_alone_rejected_when_location_and_ship_stay_in_old_yard(self, client, material):
        r = client.patch("/api/v1/materials/M1", json={"yard_id": "Y2"})
        assert r.status_code == 422
        assert client.get("/api/v1/materials/M1").json()["data"]["yard_id"] == "Y1"

    def test_changing_yard_with_matching_location_and_ship_succeeds(self, client, material):
        r = client.patch("/api/v1/materials/M1", json={"yard_id": "Y2", "location_id": "L2", "ship_id": "S2"})
        assert r.status_code == 200, r.text
        assert r.json()["data"]["yard"]["name"] == "Yard 2"

    def test_clearing_optional_location_and_ship_succeeds(self, client, material):
        r = client.patch("/api/v1/materials/M1", json={"location_id": None, "ship_id": None})
        assert r.status_code == 200, r.text
        assert r.json()["data"]["location"] is None
        assert r.json()["data"]["ship"] is None

    @pytest.mark.parametrize("field", ["name", "category_id", "batch", "unit", "yard_id", "quantity", "available", "reserved", "status"])
    def test_null_for_required_field_rejected(self, client, material, field):
        r = client.patch("/api/v1/materials/M1", json={field: None})
        assert r.status_code == 422, r.text
