"""Manual stock changes are recorded as signed ADJUSTMENT ledger entries, atomically with the change."""

import uuid

import pytest

from app.models.facility import StorageLocation, Yard
from app.models.material import Material, MaterialCategory
from app.models.transaction import MaterialTransaction, TransactionType as T
from app.services import material_service

URL = "/api/v1/materials"
WHO = {"actor": "Maya Chen"}


@pytest.fixture
def refs(db):
    db.add_all([MaterialCategory(id="C", name="Cat"), Yard(id="Y1", name="Yard 1", location="a", capacity=1.0)])
    db.commit()
    db.add_all([StorageLocation(id="L1", yard_id="Y1", zone="A", aisle="1", capacity=10),
                StorageLocation(id="L2", yard_id="Y1", zone="B", aisle="1", capacity=10)])
    db.commit()
    db.add(Material(id="M", name="Plate", category_id="C", batch="B1", unit="sheets",
                    quantity=10, available=8, reserved=2, yard_id="Y1", location_id="L1"))
    db.commit()


def rows(db, material_id="M"):
    db.expire_all()
    return [(t.transaction_type, t.quantity, t.unit, t.from_location_id, t.to_location_id, t.reference_id, t.actor, t.reason)
            for t in db.query(MaterialTransaction).filter_by(material_id=material_id).order_by(MaterialTransaction.created_at)]


def stock(db, material_id="M"):
    db.expire_all()
    m = db.get(Material, material_id)
    return m.quantity, m.available, m.reserved, m.version


def edit(client, **body):
    return client.patch(f"{URL}/M", json=body)


class TestCreate:
    def new(self, **over):
        body = {"id": "N", "name": "New", "category_id": "C", "batch": "B", "unit": "lengths", "yard_id": "Y1",
                "location_id": "L1", "quantity": 12, "available": 9, "reserved": 3, **WHO}
        body.update(over)
        return body

    def test_creating_with_stock_records_the_opening_balance(self, client, db, refs):
        r = client.post(URL, json=self.new(stock_reason="Migrated from paper stock card"))
        assert r.status_code == 201, r.text
        assert rows(db, "N") == [(T.ADJUSTMENT, 12, "lengths", None, "L1", None, "Maya Chen",
                                  "Opening balance: on hand 12, available 9, reserved 3 — Migrated from paper stock card")]

    def test_opening_balance_note_is_optional(self, client, db, refs):
        assert client.post(URL, json=self.new()).status_code == 201
        assert rows(db, "N")[0][-1] == "Opening balance: on hand 12, available 9, reserved 3"

    def test_creating_empty_needs_no_actor_and_records_nothing(self, client, db, refs):
        body = self.new(quantity=0, available=0, reserved=0)
        del body["actor"]
        assert client.post(URL, json=body).status_code == 201
        assert rows(db, "N") == []

    @pytest.mark.parametrize("actor", [None, "", "   "])
    def test_opening_balance_is_recorded_under_the_signed_in_user(self, client, db, refs, actor):
        # The ledger actor comes from the session (here the test stand-in, "Test Admin"), not the request body.
        r = client.post(URL, json=self.new(actor=actor))
        assert r.status_code == 201, r.text
        assert rows(db, "N")[0][6] == "Test Admin"


class TestEdit:
    def test_increase_records_a_positive_adjustment(self, client, db, refs):
        r = edit(client, quantity=15, available=13, stock_reason="Cycle count found 5 more", **WHO)
        assert r.status_code == 200, r.text
        assert stock(db)[:3] == (15, 13, 2)
        assert rows(db) == [(T.ADJUSTMENT, 5, "sheets", None, "L1", None, "Maya Chen",
                             "On hand 10→15, available 8→13 — Cycle count found 5 more")]

    def test_decrease_records_a_negative_adjustment(self, client, db, refs):
        assert edit(client, quantity=7, available=5, stock_reason="Water damage", **WHO).status_code == 200
        assert rows(db) == [(T.ADJUSTMENT, -3, "sheets", "L1", None, None, "Maya Chen",
                             "On hand 10→7, available 8→5 — Water damage")]

    def test_allocation_only_change_records_a_zero_quantity_adjustment(self, client, db, refs):
        assert edit(client, available=6, reserved=4, stock_reason="Reserve 2 more for NS Atlas", **WHO).status_code == 200
        assert rows(db) == [(T.ADJUSTMENT, 0, "sheets", None, None, None, "Maya Chen",
                             "available 8→6, reserved 2→4 — Reserve 2 more for NS Atlas")]

    @pytest.mark.parametrize("body, fragment", [
        ({"quantity": 12, **WHO}, "reason is required"),
        ({"quantity": 12, "stock_reason": "", **WHO}, "reason is required"),
        ({"quantity": 12, "stock_reason": "   ", **WHO}, "reason is required"),
        ({"reserved": 1, "stock_reason": None, **WHO}, "reason is required"),
    ])
    def test_stock_change_without_reason_or_actor_is_rejected_and_changes_nothing(self, client, db, refs, body, fragment):
        before = stock(db)
        r = edit(client, **body)
        assert r.status_code == 422 and fragment in r.json()["detail"], r.text
        assert stock(db) == before and rows(db) == []

    def test_stock_change_without_an_actor_is_recorded_under_the_signed_in_user(self, client, db, refs):
        assert edit(client, quantity=12, stock_reason="count").status_code == 200
        assert rows(db)[0][6] == "Test Admin"

    def test_non_stock_edits_need_no_reason_and_record_nothing(self, client, db, refs):
        assert edit(client, name="Plate 12mm", location_id="L2", status="Low stock").status_code == 200
        assert rows(db) == []

    def test_resending_identical_figures_records_nothing(self, client, db, refs):
        assert edit(client, quantity=10, available=8, reserved=2).status_code == 200
        assert edit(client, quantity=10, stock_reason="no change", **WHO).status_code == 200
        assert rows(db) == []

    def test_each_real_change_is_one_entry(self, client, db, refs):
        edit(client, quantity=11, available=9, stock_reason="first", **WHO)
        edit(client, quantity=11, available=9, stock_reason="repeat", **WHO)  # identical figures: no entry
        edit(client, quantity=9, available=7, stock_reason="second", **WHO)
        assert [(r[1], r[-1]) for r in rows(db)] == [(1, "On hand 10→11, available 8→9 — first"),
                                                       (-2, "On hand 11→9, available 9→7 — second")]

    def test_existing_stock_validation_still_applies_before_the_reason(self, client, db, refs):
        before = stock(db)
        r = edit(client, available=9, stock_reason="count", **WHO)  # 9 + 2 reserved > 10 on hand
        assert r.status_code == 422 and "cannot exceed quantity" in r.json()["detail"]
        assert stock(db) == before and rows(db) == []

    def test_stale_version_is_still_refused(self, client, db, refs):
        r = edit(client, quantity=12, stock_reason="count", expected_version=99, **WHO)
        assert r.status_code == 409 and rows(db) == []

    def test_adjustments_appear_in_the_batch_history(self, client, db, refs):
        edit(client, quantity=7, available=5, stock_reason="Water damage", **WHO)
        history = client.get(f"{URL}/M/transactions").json()["data"]["transactions"]
        assert [(t["transaction_type"], t["quantity"], t["actor"]) for t in history] == [("Adjustment", -3, "Maya Chen")]


class TestAtomicity:
    """If the ledger write fails, the stock change must not survive (and vice versa)."""

    @pytest.fixture
    def colliding_ids(self, db, refs, monkeypatch):
        fixed = uuid.UUID(int=0)
        db.add(MaterialTransaction(id=f"TXN-{fixed.hex[:24]}", material_id="M", transaction_type=T.RECEIPT,
                                   quantity=1, unit="sheets", actor="seed"))
        db.commit()
        monkeypatch.setattr(material_service, "uuid4", lambda: fixed)  # the next entry reuses that primary key

    def test_failed_ledger_write_rolls_back_the_edit(self, client, db, colliding_ids):
        before = stock(db)
        r = edit(client, quantity=15, available=13, stock_reason="count", **WHO)
        assert r.status_code == 500
        assert stock(db) == before
        assert [r[0] for r in rows(db)] == [T.RECEIPT]

    def test_failed_ledger_write_rolls_back_the_create(self, client, db, colliding_ids):
        body = {"id": "N", "name": "New", "category_id": "C", "batch": "B", "unit": "u", "yard_id": "Y1",
                "quantity": 4, "available": 4, "reserved": 0, **WHO}
        assert client.post(URL, json=body).status_code == 500
        db.expire_all()
        assert db.get(Material, "N") is None
