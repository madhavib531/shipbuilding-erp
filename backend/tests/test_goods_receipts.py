"""Goods receipts (M3): stock, ledger, order quantities and status, idempotency and validation."""

from datetime import date, timedelta

import pytest

from app.models.facility import StorageLocation, Yard
from app.models.goods_receipt import GoodsReceipt
from app.models.material import Material, MaterialCategory, MaterialStatusEnum
from app.models.supplier import Supplier
from app.models.transaction import MaterialTransaction, TransactionType

PO = "/api/v1/purchase-orders"
ACTOR = "Leo Anders"


@pytest.fixture
def world(db):
    db.add_all([
        Supplier(id="SUP", name="Supplier"),
        MaterialCategory(id="STEEL", name="Steel"), MaterialCategory(id="PIPE", name="Pipe"),
        Yard(id="Y1", name="Yard 1", location="North", capacity=1.0),
        Yard(id="Y2", name="Yard 2", location="South", capacity=1.0),
    ])
    db.commit()
    db.add_all([
        StorageLocation(id="L1", yard_id="Y1", zone="A", aisle="1", capacity=100),
        StorageLocation(id="L1B", yard_id="Y1", zone="B", aisle="1", capacity=100),
        StorageLocation(id="L2", yard_id="Y2", zone="C", aisle="1", capacity=100),
    ])
    db.commit()
    db.add_all([
        Material(id="EXIST", name="AH36 plate", category_id="STEEL", batch="LOT-1", unit="sheets",
                 quantity=5, available=5, reserved=0, yard_id="Y1", location_id="L1"),
        Material(id="OTHER", name="Unrelated", category_id="PIPE", batch="P", unit="m",
                 quantity=7, available=7, reserved=0, yard_id="Y1"),
    ])
    db.commit()


def order_line(**over):
    data = {"category_id": "STEEL", "description": "AH36 plate 12mm", "unit": "sheets",
            "ordered_quantity": 10, "unit_price": "100", "currency": "EUR"}
    data.update(over)
    return data


def approved_order(client, lines=None):
    r = client.post(PO, json={"actor": "Maya", "supplier_id": "SUP", "lines": lines or [order_line()],
                              "expected_delivery_date": str(date.today() + timedelta(days=7))})
    assert r.status_code == 201, r.text
    po = r.json()["data"]
    r = client.post(f"{PO}/{po['id']}/approve", json={"actor": "Maya", "expected_version": 1})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def receive(client, po, lines, key="gr-1", version=None, yard="Y1", location="L1", **extra):
    body = {"actor": ACTOR, "expected_version": version or po["version"], "yard_id": yard, "lines": lines, **extra}
    if location:
        body["location_id"] = location
    return client.post(f"{PO}/{po['id']}/receipts", json=body, headers={"Idempotency-Key": key} if key else {})


def rline(po, n=0, **over):
    data = {"purchase_order_line_id": po["lines"][n]["id"], "accepted_quantity": 10,
            "destination_material_id": "NEW-1", "batch": "LOT-NEW"}
    data.update(over)
    return data


def snapshot(db):
    db.expire_all()
    return {m.id: (m.quantity, m.available, m.reserved) for m in db.query(Material).all()}, \
        sorted((t.transaction_type.name, t.material_id, t.quantity) for t in db.query(MaterialTransaction).all())


class TestStockAndStatus:
    def test_full_receipt_into_new_batch(self, client, world, db):
        po = approved_order(client)
        r = receive(client, po, [rline(po)], delivery_note="DN-1")
        assert r.status_code == 201, r.text
        d = r.json()["data"]
        receipt, order = d["receipt"], d["purchase_order"]
        assert receipt["display_id"] == f"GR-{receipt['id']:05d}" and receipt["delivery_note"] == "DN-1"
        assert (order["status"], order["version"], order["lines"][0]["received_quantity"], order["lines"][0]["outstanding_quantity"]) == ("Received", 3, 10, 0)
        assert order["events"][-1]["action"] == "received"
        assert order["events"][-1]["changes"] == {"receipt": receipt["display_id"], "accepted": 10, "rejected": 0, "held": 0}
        new = db.get(Material, "NEW-1")
        assert (new.quantity, new.available, new.reserved, new.status, new.batch, new.unit, new.category_id, new.yard_id, new.location_id, new.name) == \
            (10, 10, 0, MaterialStatusEnum.HEALTHY, "LOT-NEW", "sheets", "STEEL", "Y1", "L1", "AH36 plate 12mm")
        rows = db.query(MaterialTransaction).all()
        assert [(t.transaction_type, t.material_id, t.quantity, t.reference_id, t.to_location_id) for t in rows] == \
            [(TransactionType.RECEIPT, "NEW-1", 10, receipt["display_id"], "L1")]

    def test_partial_then_final_receipt(self, client, world):
        po = approved_order(client)
        first = receive(client, po, [rline(po, accepted_quantity=4)], key="a").json()["data"]["purchase_order"]
        assert (first["status"], first["lines"][0]["outstanding_quantity"]) == ("Partially received", 6)
        second = receive(client, first, [rline(first, accepted_quantity=6, destination_material_id="NEW-1", batch=None)], key="b")
        assert second.status_code == 201, second.text
        assert second.json()["data"]["purchase_order"]["status"] == "Received"
        assert len(client.get(f"{PO}/{po['id']}/receipts").json()["data"]["receipts"]) == 2

    def test_rejected_only_delivery_is_not_fulfilment(self, client, world, db):
        po = approved_order(client)
        before = snapshot(db)
        r = receive(client, po, [rline(po, accepted_quantity=0, rejected_quantity=3, rejection_reason="Corroded",
                                       destination_material_id=None, batch=None)])
        assert r.status_code == 201, r.text
        order = r.json()["data"]["purchase_order"]
        ln = order["lines"][0]
        assert (order["status"], ln["received_quantity"], ln["rejected_quantity"], ln["outstanding_quantity"]) == ("Approved", 0, 3, 10)
        assert snapshot(db) == before, "rejected goods never enter stock or the ledger"
        assert r.json()["data"]["receipt"]["lines"][0]["destination_material_id"] is None

    def test_rejected_quantity_stays_outstanding_for_redelivery(self, client, world, db):
        po = approved_order(client)
        d = receive(client, po, [rline(po, accepted_quantity=7, rejected_quantity=3, rejection_reason="Dented")], key="a").json()["data"]
        order = d["purchase_order"]
        assert (order["status"], order["lines"][0]["outstanding_quantity"]) == ("Partially received", 3)
        assert db.get(Material, "NEW-1").quantity == 7
        redelivery = receive(client, order, [rline(order, accepted_quantity=3, batch=None)], key="b")
        assert redelivery.status_code == 201, redelivery.text
        final = redelivery.json()["data"]["purchase_order"]
        assert (final["status"], final["lines"][0]["received_quantity"], final["lines"][0]["rejected_quantity"]) == ("Received", 10, 3)
        db.expire_all()
        assert db.get(Material, "NEW-1").quantity == 10

    def test_receipt_into_existing_compatible_batch(self, client, world, db):
        po = approved_order(client)
        r = receive(client, po, [rline(po, accepted_quantity=4, destination_material_id="EXIST", batch="LOT-1")])
        assert r.status_code == 201, r.text
        db.expire_all()
        m = db.get(Material, "EXIST")
        assert (m.quantity, m.available, m.version) == (9, 9, 2)

    def test_multi_line_receipt_with_mixed_outcomes(self, client, world, db):
        po = approved_order(client, lines=[order_line(), order_line(description="Cu-Ni pipe", category_id="PIPE", unit="m", ordered_quantity=20)])
        r = receive(client, po, [
            rline(po, 0, accepted_quantity=10),
            rline(po, 1, accepted_quantity=0, rejected_quantity=5, rejection_reason="Wrong grade", destination_material_id=None, batch=None),
        ])
        assert r.status_code == 201, r.text
        order = r.json()["data"]["purchase_order"]
        assert order["status"] == "Partially received"
        assert [(l["received_quantity"], l["rejected_quantity"], l["outstanding_quantity"]) for l in order["lines"]] == [(10, 0, 0), (0, 5, 20)]

    def test_close_after_partial_receipt_and_reopen_refused(self, client, world):
        po = approved_order(client)
        order = receive(client, po, [rline(po, accepted_quantity=4)]).json()["data"]["purchase_order"]
        assert client.post(f"{PO}/{po['id']}/reopen", json={"actor": "Maya", "expected_version": order["version"], "reason": "x"}).status_code == 409
        closed = client.post(f"{PO}/{po['id']}/close", json={"actor": "Maya", "expected_version": order["version"], "reason": "Short"})
        assert closed.json()["data"]["lines"][0]["cancelled_quantity"] == 6

    def test_receiving_allowed_after_supplier_blocked(self, client, world):
        po = approved_order(client)
        client.patch("/api/v1/suppliers/SUP", json={"status": "Blocked"})
        assert receive(client, po, [rline(po)]).status_code == 201

    def test_received_batch_cannot_be_deleted(self, client, world):
        po = approved_order(client)
        receive(client, po, [rline(po)])
        assert client.delete("/api/v1/materials/NEW-1").status_code == 409


class TestValidationAndRollback:
    @pytest.mark.parametrize("over, fragment", [
        ({"accepted_quantity": 11}, "over-delivery"),
        ({"accepted_quantity": 8, "rejected_quantity": 3, "rejection_reason": "x"}, "over-delivery"),
        ({"purchase_order_line_id": 999999}, "is not on"),
        ({"destination_material_id": "NEW-2", "batch": None}, "batch number is required"),
        ({"destination_material_id": "OTHER", "batch": None}, "category"),
    ])
    def test_invalid_line_rejected_without_changes(self, client, world, db, over, fragment):
        po = approved_order(client)
        before = snapshot(db)
        r = receive(client, po, [rline(po, **over)])
        assert r.status_code == 422 and fragment in r.json()["detail"], r.text
        assert snapshot(db) == before
        assert db.query(GoodsReceipt).count() == 0
        assert client.get(f"{PO}/{po['id']}").json()["data"]["version"] == po["version"]

    @pytest.mark.parametrize("batch_over, fragment", [
        ({"yard_id": "Y2", "location_id": "L2"}, "yard"),
        ({"location_id": "L1B"}, "location"),
        ({"unit": "plates"}, "unit"),
        ({"batch": "LOT-9"}, "batch number"),
        ({"status": MaterialStatusEnum.INSPECTION}, "under inspection"),
    ])
    def test_incompatible_existing_batch_rejected(self, client, world, db, batch_over, fragment):
        db.add(Material(id="CAND", **{**dict(name="x", category_id="STEEL", batch="LOT-1", unit="sheets", quantity=1,
                                              available=1, reserved=0, yard_id="Y1", location_id="L1"), **batch_over}))
        db.commit()
        po = approved_order(client)
        before = snapshot(db)
        r = receive(client, po, [rline(po, destination_material_id="CAND", batch="LOT-1")])
        assert r.status_code == 422 and fragment in r.json()["detail"], r.text
        assert snapshot(db) == before

    def test_second_line_failure_rolls_back_first_line(self, client, world, db):
        po = approved_order(client, lines=[order_line(), order_line(description="b", ordered_quantity=5)])
        before = snapshot(db)
        r = receive(client, po, [rline(po, 0), rline(po, 1, accepted_quantity=6, destination_material_id="NEW-2")])
        assert r.status_code == 422
        assert snapshot(db) == before
        assert db.get(Material, "NEW-1") is None

    @pytest.mark.parametrize("lines_fn, fragment", [
        (lambda po: [rline(po), rline(po, destination_material_id="NEW-2")], "more than once"),
        (lambda po: [rline(po, 0, accepted_quantity=1), rline(po, 1, accepted_quantity=1)], "more than one line"),
    ])
    def test_duplicate_order_line_or_batch_rejected(self, client, world, lines_fn, fragment):
        po = approved_order(client, lines=[order_line(), order_line(description="b")])
        r = receive(client, po, lines_fn(po))
        assert r.status_code == 422 and fragment in r.json()["detail"]

    @pytest.mark.parametrize("over", [
        {"accepted_quantity": 0},
        {"accepted_quantity": 0, "rejected_quantity": 2},
        {"destination_material_id": None},
        {"accepted_quantity": -1},
    ])
    def test_schema_validation(self, client, world, over):
        po = approved_order(client)
        assert receive(client, po, [rline(po, **over)]).status_code == 422

    @pytest.mark.parametrize("yard, location", [("NOPE", None), ("Y1", "L2"), ("Y1", "NOPE")])
    def test_invalid_receiving_place(self, client, world, yard, location):
        po = approved_order(client)
        assert receive(client, po, [rline(po)], yard=yard, location=location).status_code == 422

    def test_empty_receipt_rejected(self, client, world):
        po = approved_order(client)
        assert receive(client, po, []).status_code == 422


class TestGatesAndIdempotency:
    def test_replay_returns_original_and_adds_stock_once(self, client, world, db):
        po = approved_order(client)
        first = receive(client, po, [rline(po, accepted_quantity=4)])
        again = receive(client, po, [rline(po, accepted_quantity=4)])
        assert (first.status_code, again.status_code) == (201, 200)
        assert first.json()["data"]["receipt"]["id"] == again.json()["data"]["receipt"]["id"]
        db.expire_all()
        assert db.get(Material, "NEW-1").quantity == 4
        assert db.query(GoodsReceipt).count() == 1
        assert db.query(MaterialTransaction).count() == 1

    def test_key_reused_with_different_body_conflicts(self, client, world, db):
        po = approved_order(client)
        receive(client, po, [rline(po, accepted_quantity=4)])
        r = receive(client, po, [rline(po, accepted_quantity=5)])
        assert r.status_code == 409
        db.expire_all()
        assert db.get(Material, "NEW-1").quantity == 4

    def test_key_required(self, client, world):
        po = approved_order(client)
        r = receive(client, po, [rline(po)], key=None)
        assert r.status_code == 422 and "Idempotency-Key" in r.json()["detail"]

    def test_stale_order_version_rejected(self, client, world, db):
        po = approved_order(client)
        receive(client, po, [rline(po, accepted_quantity=4)], key="a")
        r = receive(client, po, [rline(po, accepted_quantity=4)], key="b")
        assert r.status_code == 409 and "version" in r.json()["detail"]
        db.expire_all()
        assert db.get(Material, "NEW-1").quantity == 4

    @pytest.mark.parametrize("state", ["draft", "cancelled", "closed", "received"])
    def test_receiving_needs_an_open_order(self, client, world, state):
        if state == "draft":
            po = client.post(PO, json={"actor": "Maya", "supplier_id": "SUP", "lines": [order_line()]}).json()["data"]
        else:
            po = approved_order(client)
            if state == "cancelled":
                po = client.post(f"{PO}/{po['id']}/cancel", json={"actor": "Maya", "expected_version": po["version"], "reason": "x"}).json()["data"]
            elif state == "closed":
                po = receive(client, po, [rline(po, accepted_quantity=2)], key="pre").json()["data"]["purchase_order"]
                po = client.post(f"{PO}/{po['id']}/close", json={"actor": "Maya", "expected_version": po["version"], "reason": "x"}).json()["data"]
            else:
                po = receive(client, po, [rline(po)], key="pre").json()["data"]["purchase_order"]
        r = receive(client, po, [rline(po, accepted_quantity=1, destination_material_id="NEW-9", batch="L")], key="late")
        assert r.status_code == 409, r.text

    def test_unknown_order_404(self, client, world):
        r = client.post(f"{PO}/999/receipts", json={"actor": ACTOR, "expected_version": 1, "yard_id": "Y1",
                                                   "lines": [{"purchase_order_line_id": 1, "accepted_quantity": 1, "destination_material_id": "X", "batch": "B"}]},
                        headers={"Idempotency-Key": "k"})
        assert r.status_code == 404
        assert client.get(f"{PO}/999/receipts").status_code == 404
