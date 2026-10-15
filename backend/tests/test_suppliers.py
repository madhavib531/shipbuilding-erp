"""Supplier directory API tests."""

import pytest

from app.models.material import Material, MaterialCategory
from app.models.facility import Yard
from app.models.supplier import Supplier, SupplierStatusEnum
from app.models.transaction import MaterialTransaction

BASE = "/api/v1/suppliers"


def body(**over):
    data = {"id": "NMS", "name": "Nordic Marine Steel", "contact_person": "Ann Berg",
            "contact_email": "ann@nordic.example", "contact_phone": "+46 31 000", "country": "Sweden"}
    data.update(over)
    return data


@pytest.fixture
def directory(db):
    db.add_all([
        Supplier(id="NMS", name="Nordic Marine Steel", country="Sweden", contact_person="Ann Berg"),
        Supplier(id="BLC", name="BlueLine Components", country="Norway", status=SupplierStatusEnum.CONDITIONAL),
        Supplier(id="KEY", name="Keystone Electrical", country="United Kingdom", status=SupplierStatusEnum.BLOCKED),
        Supplier(id="OSC", name="OceanShield Coatings", country="Norway", status=SupplierStatusEnum.INACTIVE),
    ])
    db.commit()


class TestCreate:
    def test_create_returns_201_and_defaults_to_approved(self, client):
        r = client.post(BASE, json=body())
        assert r.status_code == 201, r.text
        d = r.json()["data"]
        assert (d["id"], d["name"], d["status"], d["country"]) == ("NMS", "Nordic Marine Steel", "Approved", "Sweden")
        assert d["created_at"] and d["updated_at"]

    def test_whitespace_is_trimmed_and_blank_optionals_become_null(self, client):
        r = client.post(BASE, json=body(id="  X1 ", name="  Acme  ", contact_email="  ", notes=""))
        assert r.status_code == 201, r.text
        d = r.json()["data"]
        assert (d["id"], d["name"], d["contact_email"], d["notes"]) == ("X1", "Acme", None, None)

    def test_duplicate_id_conflicts(self, client):
        client.post(BASE, json=body())
        r = client.post(BASE, json=body(name="Other name"))
        assert r.status_code == 409 and "already exists" in r.json()["detail"]

    def test_duplicate_name_conflicts_case_insensitively(self, client):
        client.post(BASE, json=body())
        r = client.post(BASE, json=body(id="NMS2", name="NORDIC marine steel"))
        assert r.status_code == 409 and "already used" in r.json()["detail"]

    @pytest.mark.parametrize("over", [
        {"id": ""},
        {"id": "x" * 51},
        {"name": "   "},
        {"name": "n" * 151},
        {"contact_email": "not-an-email"},
        {"contact_phone": "1" * 21},
        {"status": "Preferred"},
        {"notes": "n" * 501},
    ])
    def test_invalid_input_rejected(self, client, over):
        assert client.post(BASE, json=body(**over)).status_code == 422

    def test_missing_name_rejected(self, client):
        data = body()
        del data["name"]
        assert client.post(BASE, json=data).status_code == 422


class TestRead:
    def test_get_and_404(self, client, directory):
        assert client.get(f"{BASE}/BLC").json()["data"]["status"] == "Conditional"
        r = client.get(f"{BASE}/NOPE")
        assert r.status_code == 404 and "not found" in r.json()["detail"]

    def test_list_is_sorted_by_name_with_total(self, client, directory):
        d = client.get(BASE).json()["data"]
        assert d["total"] == 4
        assert [s["name"] for s in d["suppliers"]] == [
            "BlueLine Components", "Keystone Electrical", "Nordic Marine Steel", "OceanShield Coatings"]

    def test_empty_directory(self, client):
        assert client.get(BASE).json()["data"] == {"suppliers": [], "total": 0, "skip": 0, "limit": 50}

    def test_pagination(self, client, directory):
        d = client.get(BASE, params={"skip": 1, "limit": 2}).json()["data"]
        assert (d["total"], [s["id"] for s in d["suppliers"]]) == (4, ["KEY", "NMS"])

    @pytest.mark.parametrize("search, expected", [
        ("nordic", ["NMS"]),      # name
        ("ann", ["NMS"]),         # contact person
        ("norway", ["BLC", "OSC"]),  # country
        ("key", ["KEY"]),         # id
        ("zzz", []),
    ])
    def test_search(self, client, directory, search, expected):
        d = client.get(BASE, params={"search": search}).json()["data"]
        assert [s["id"] for s in d["suppliers"]] == expected

    def test_status_filter_accepts_several(self, client, directory):
        d = client.get(BASE, params=[("status", "Approved"), ("status", "Conditional")]).json()["data"]
        assert {s["id"] for s in d["suppliers"]} == {"NMS", "BLC"}

    def test_country_filter_is_exact_and_case_insensitive(self, client, directory):
        d = client.get(BASE, params={"country": "NORWAY"}).json()["data"]
        assert {s["id"] for s in d["suppliers"]} == {"BLC", "OSC"}

    def test_invalid_status_filter_rejected(self, client):
        assert client.get(BASE, params={"status": "Preferred"}).status_code == 422


class TestUpdate:
    def test_partial_update_changes_only_sent_fields(self, client, directory):
        r = client.patch(f"{BASE}/NMS", json={"contact_phone": "+46 31 123"})
        assert r.status_code == 200
        d = r.json()["data"]
        assert (d["contact_phone"], d["name"], d["country"], d["contact_person"]) == ("+46 31 123", "Nordic Marine Steel", "Sweden", "Ann Berg")

    def test_status_change_deactivates_without_deleting(self, client, directory):
        assert client.patch(f"{BASE}/NMS", json={"status": "Blocked"}).json()["data"]["status"] == "Blocked"
        assert client.get(f"{BASE}/NMS").status_code == 200

    def test_clear_optional_field(self, client, directory):
        assert client.patch(f"{BASE}/NMS", json={"contact_person": None}).json()["data"]["contact_person"] is None
        assert client.patch(f"{BASE}/NMS", json={"country": ""}).json()["data"]["country"] is None

    def test_rename_to_own_name_in_other_case_is_allowed(self, client, directory):
        r = client.patch(f"{BASE}/NMS", json={"name": "NORDIC MARINE STEEL"})
        assert r.status_code == 200 and r.json()["data"]["name"] == "NORDIC MARINE STEEL"

    def test_rename_to_another_suppliers_name_conflicts(self, client, directory):
        r = client.patch(f"{BASE}/NMS", json={"name": "blueline components"})
        assert r.status_code == 409
        assert client.get(f"{BASE}/NMS").json()["data"]["name"] == "Nordic Marine Steel"

    @pytest.mark.parametrize("field", ["name", "status"])
    def test_null_for_required_field_rejected(self, client, directory, field):
        assert client.patch(f"{BASE}/NMS", json={field: None}).status_code == 422

    def test_invalid_values_rejected(self, client, directory):
        assert client.patch(f"{BASE}/NMS", json={"contact_email": "bad"}).status_code == 422
        assert client.patch(f"{BASE}/NMS", json={"status": "Preferred"}).status_code == 422

    def test_update_unknown_supplier_404(self, client):
        assert client.patch(f"{BASE}/NOPE", json={"notes": "x"}).status_code == 404

    def test_id_cannot_be_changed(self, client, directory):
        r = client.patch(f"{BASE}/NMS", json={"id": "NEW"})
        assert r.status_code == 200
        assert client.get(f"{BASE}/NMS").status_code == 200
        assert client.get(f"{BASE}/NEW").status_code == 404


def test_supplier_api_never_touches_stock_or_ledger(client, db):
    db.add_all([MaterialCategory(id="C", name="Cat"), Yard(id="Y", name="Y", location="l", capacity=1.0)])
    db.commit()
    db.add(Material(id="M", name="m", category_id="C", batch="b", unit="u", quantity=5, available=5, reserved=0, yard_id="Y"))
    db.commit()
    client.post(BASE, json=body())
    client.patch(f"{BASE}/NMS", json={"status": "Inactive"})
    db.expire_all()
    m = db.get(Material, "M")
    assert (m.quantity, m.available, m.reserved, m.version) == (5, 5, 0, 1)
    assert db.query(MaterialTransaction).count() == 0
