"""Inspection holds (M5): hold on receipt, release, rejection, enforcement on every stock path, audit."""

import pytest

from app.models.inspection import InspectionEvent, InspectionHold
from app.models.material import Material
from app.models.transaction import MaterialTransaction, TransactionType as T
from tests.test_goods_receipts import PO, approved_order, order_line, receive, rline, snapshot, world  # noqa: F401

QI = "/api/v1/inspections"
INSPECTOR = "Nadia King"


def held(client, po, n=0, key="gr-h", **over):
    """Receives line n of the order into new batch H-1 on inspection hold."""
    data = {"accepted_quantity": 10, "destination_material_id": "H-1", "batch": "LOT-H", "hold_for_inspection": True}
    data.update(over)
    r = receive(client, po, [rline(po, n, **data)], key=key)
    assert r.status_code == 201, r.text
    return r.json()["data"]


def hold_of(receipt_data, n=0):
    return receipt_data["receipt"]["lines"][n]["inspection_hold"]


def get(client, hid):
    r = client.get(f"{QI}/{hid}")
    assert r.status_code == 200, r.text
    return r.json()["data"]


def decide(client, hid, action, version=None, **body):
    body.setdefault("actor", INSPECTOR)
    body["expected_version"] = version if version is not None else get(client, hid)["version"]
    if action == "reject":
        body.setdefault("reason", "Coating defects")
        body.setdefault("disposition", "Return to supplier")
    return client.post(f"{QI}/{hid}/{action}", json=body)


def material(client, mid):
    return client.get(f"/api/v1/materials/{mid}").json()["data"]


def stock(client, mid):
    m = material(client, mid)
    return m["quantity"], m["available"], m["reserved"], m["held_quantity"], m["status"]


def order(client, po):
    return client.get(f"{PO}/{po['id']}").json()["data"]


def ledger(db, mid):
    db.expire_all()
    return sorted((t.transaction_type, t.quantity, t.reference_id[:3]) for t in
                  db.query(MaterialTransaction).filter(MaterialTransaction.material_id == mid))


class TestHoldOnReceipt:
    def test_held_goods_are_on_hand_but_not_available(self, client, world, db):
        po = approved_order(client)
        d = held(client, po)
        hold = hold_of(d)
        assert (hold["status"], hold["quantity"], hold["outstanding_quantity"]) == ("Open", 10, 10)
        assert stock(client, "H-1") == (10, 0, 0, 10, "Inspection")
        assert ledger(db, "H-1") == sorted([(T.RECEIPT, 10, "GR-"), (T.INSPECTION, 10, "QI-")])
        detail = get(client, hold["id"])
        assert [(e["action"], e["quantity"], e["to_status"]) for e in detail["events"]] == [("held", 10, "Open")]
        assert detail["goods_receipt_line"]["receipt"]["purchase_order"]["display_id"] == po["display_id"]
        o = d["purchase_order"]
        assert (o["status"], o["lines"][0]["received_quantity"]) == ("Received", 10)
        assert o["events"][-1]["changes"]["held"] == 10
        assert o["receipts"][0]["lines"][0]["inspection_hold"]["display_id"] == hold["display_id"]

    def test_only_marked_lines_are_held(self, client, world):
        po = approved_order(client, lines=[order_line(), order_line(description="b", ordered_quantity=5)])
        r = receive(client, po, [rline(po, 0, destination_material_id="H-1", batch="LH", hold_for_inspection=True),
                                 rline(po, 1, accepted_quantity=5, destination_material_id="FREE", batch="LF")])
        assert r.status_code == 201, r.text
        assert stock(client, "H-1") == (10, 0, 0, 10, "Inspection")
        assert stock(client, "FREE") == (5, 5, 0, 0, "Healthy")
        assert r.json()["data"]["receipt"]["lines"][1]["inspection_hold"] is None

    def test_held_goods_need_a_new_batch(self, client, world, db):
        po = approved_order(client)
        before = snapshot(db)
        r = receive(client, po, [rline(po, destination_material_id="EXIST", batch="LOT-1", hold_for_inspection=True)])
        assert r.status_code == 422 and "new batch" in r.json()["detail"]
        assert snapshot(db) == before and db.query(InspectionHold).count() == 0

    def test_hold_needs_an_accepted_quantity(self, client, world):
        po = approved_order(client)
        r = receive(client, po, [rline(po, accepted_quantity=0, rejected_quantity=2, rejection_reason="x",
                                       destination_material_id=None, batch=None, hold_for_inspection=True)])
        assert r.status_code == 422

    def test_material_list_reports_held_quantity(self, client, world):
        po = approved_order(client)
        held(client, po)
        listed = {m["id"]: m["held_quantity"] for m in client.get("/api/v1/materials").json()["data"]["materials"]}
        assert listed == {"H-1": 10, "EXIST": 0, "OTHER": 0}


class TestRelease:
    def test_full_release_makes_stock_available(self, client, world, db):
        po = approved_order(client)
        hid = hold_of(held(client, po))["id"]
        r = decide(client, hid, "release", quantity=10, note="Visual and UT passed")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert (d["status"], d["released_quantity"], d["outstanding_quantity"], d["version"]) == ("Released", 10, 0, 2)
        assert [(e["action"], e["from_status"], e["to_status"], e["actor"], e["reason"]) for e in d["events"]][-1] == \
            ("released", "Open", "Released", INSPECTOR, "Visual and UT passed")
        assert stock(client, "H-1") == (10, 10, 0, 0, "Healthy")
        assert ledger(db, "H-1") == sorted([(T.RECEIPT, 10, "GR-"), (T.INSPECTION, 10, "QI-"), (T.RELEASE, 10, "QI-")])
        assert order(client, po)["status"] == "Received", "release does not change the order"

    def test_partial_release_then_scrap_remainder(self, client, world, db):
        po = approved_order(client)
        hid = hold_of(held(client, po))["id"]
        assert decide(client, hid, "release", quantity=6).status_code == 200
        assert get(client, hid)["status"] == "Open"
        assert stock(client, "H-1") == (10, 6, 0, 4, "Inspection")
        r = decide(client, hid, "reject", quantity=4, disposition="Scrap", reason="Cracked flange")
        assert r.status_code == 200, r.text
        assert r.json()["data"]["status"] == "Partially released"
        assert stock(client, "H-1") == (6, 6, 0, 0, "Healthy")
        assert (T.SCRAP, 4, "QI-") in ledger(db, "H-1")

    def test_cannot_release_more_than_outstanding(self, client, world, db):
        po = approved_order(client)
        hid = hold_of(held(client, po))["id"]
        before = snapshot(db)
        r = decide(client, hid, "release", quantity=11)
        assert r.status_code == 422 and "await a decision" in r.json()["detail"]
        assert snapshot(db) == before and get(client, hid)["version"] == 1


class TestReject:
    def test_rejection_removes_stock_and_reopens_the_order_line(self, client, world, db):
        po = approved_order(client)
        hid = hold_of(held(client, po))["id"]
        r = decide(client, hid, "reject", quantity=10, reason="Wrong grade certificate")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert (d["status"], d["rejected_quantity"]) == ("Rejected", 10)
        assert d["events"][-1]["disposition"] == "Return to supplier"
        assert stock(client, "H-1") == (0, 0, 0, 0, "Healthy")
        db.expire_all()
        returned = db.query(MaterialTransaction).filter_by(material_id="H-1", transaction_type=T.RETURN).one()
        assert (returned.quantity, returned.reference_id, returned.actor, returned.reason) == \
            (10, d["display_id"], INSPECTOR, "Return to supplier: Wrong grade certificate")
        o = order(client, po)
        ln = o["lines"][0]
        assert (o["status"], ln["received_quantity"], ln["rejected_quantity"], ln["outstanding_quantity"]) == ("Approved", 0, 10, 10)
        assert o["events"][-1]["action"] == "inspection_rejected"
        assert o["events"][-1]["changes"] == {"inspection": d["display_id"], "line": 1, "quantity": 10,
                                              "disposition": "Return to supplier"}

    def test_rejected_quantity_can_be_redelivered(self, client, world):
        po = approved_order(client)
        hid = hold_of(held(client, po))["id"]
        decide(client, hid, "reject", quantity=3)
        o = order(client, po)
        assert (o["status"], o["lines"][0]["outstanding_quantity"]) == ("Partially received", 3)
        r = receive(client, o, [rline(o, accepted_quantity=3, destination_material_id="R-1", batch="LOT-R")], key="redeliver")
        assert r.status_code == 201, r.text
        assert r.json()["data"]["purchase_order"]["status"] == "Received"

    def test_rejection_on_closed_order_cancels_instead_of_reopening(self, client, world):
        po = approved_order(client)
        o = held(client, po, accepted_quantity=4)["purchase_order"]
        closed = client.post(f"{PO}/{po['id']}/close", json={"actor": "Maya", "expected_version": o["version"], "reason": "Short"})
        assert closed.status_code == 200
        hid = order(client, po)["receipts"][0]["lines"][0]["inspection_hold"]["id"]
        assert decide(client, hid, "reject", quantity=4).status_code == 200
        o = order(client, po)
        ln = o["lines"][0]
        assert (o["status"], ln["received_quantity"], ln["rejected_quantity"], ln["cancelled_quantity"], ln["outstanding_quantity"]) == \
            ("Closed", 0, 4, 10, 0)

    @pytest.mark.parametrize("body", [{"reason": ""}, {"disposition": "Burn"}, {"disposition": None}, {"quantity": 0}])
    def test_rejection_needs_reason_disposition_and_quantity(self, client, world, body):
        po = approved_order(client)
        hid = hold_of(held(client, po))["id"]
        assert decide(client, hid, "reject", **{"quantity": 2, **body}).status_code == 422
        assert get(client, hid)["version"] == 1


class TestGuards:
    def test_duplicate_release_applies_once(self, client, world):
        po = approved_order(client)
        hid = hold_of(held(client, po))["id"]
        assert decide(client, hid, "release", version=1, quantity=5).status_code == 200
        again = decide(client, hid, "release", version=1, quantity=5)
        assert again.status_code == 409 and "version" in again.json()["detail"]
        assert stock(client, "H-1")[:4] == (10, 5, 0, 5)

    @pytest.mark.parametrize("first, second", [("release", "release"), ("release", "reject"), ("reject", "reject"), ("reject", "release")])
    def test_closed_hold_accepts_no_further_decision(self, client, world, first, second):
        po = approved_order(client)
        hid = hold_of(held(client, po))["id"]
        assert decide(client, hid, first, quantity=10).status_code == 200
        before = stock(client, "H-1")
        r = decide(client, hid, second, quantity=1)
        assert r.status_code == 409 and "cannot be" in r.json()["detail"]
        assert stock(client, "H-1") == before

    def test_unknown_inspection(self, client, world):
        assert client.get(f"{QI}/999").status_code == 404
        assert decide(client, 999, "release", version=1, quantity=1).status_code == 404
        assert decide(client, 999, "reject", version=1, quantity=1).status_code == 404


class TestHeldStockIsExcluded:
    def test_held_stock_cannot_be_transferred(self, client, world):
        po = approved_order(client)
        held(client, po)
        r = client.post("/api/v1/transfers", json={"actor": "t", "material_id": "H-1", "quantity": 1, "to_yard_id": "Y2"})
        assert r.status_code == 422 and "Only 0" in r.json()["detail"]

    def test_only_released_stock_can_be_dispatched(self, client, world):
        po = approved_order(client)
        hid = hold_of(held(client, po))["id"]
        decide(client, hid, "release", quantity=6)
        body = {"actor": "t", "material_id": "H-1", "quantity": 6, "to_yard_id": "Y2"}
        assert client.post("/api/v1/transfers", json={**body, "quantity": 7}).status_code == 422
        ids = [client.post("/api/v1/transfers", json=body).json()["data"]["id"] for _ in range(2)]
        for tid in ids:
            assert client.post(f"/api/v1/transfers/{tid}/approve", json={"actor": "a"}).status_code == 200
        results = [client.post(f"/api/v1/transfers/{tid}/dispatch", json={"actor": "d"}).status_code for tid in ids]
        assert results == [200, 409]
        assert stock(client, "H-1") == (4, 0, 0, 4, "Inspection")

    @pytest.mark.parametrize("change, code", [
        ({"available": 2}, 422),                  # would make held stock available
        ({"available": 0, "reserved": 2}, 422),   # would reserve held stock
        ({"quantity": 9}, 422),                   # would cut into held stock while 1 is available
        ({"quantity": 9, "available": 0}, 200),   # removing only non-held stock is a normal correction
        ({"available": 0, "reserved": 1}, 200),
        ({"status": "Healthy"}, 409),
        ({"name": "Renamed plate"}, 200),
    ])
    def test_inventory_edits_cannot_touch_held_stock(self, client, world, change, code):
        po = approved_order(client)
        hid = hold_of(held(client, po))["id"]
        decide(client, hid, "release", quantity=1)  # 1 available, 9 held
        v = material(client, "H-1")["version"]
        r = client.patch("/api/v1/materials/H-1", json={**change, "expected_version": v, "actor": "QA", "stock_reason": "Count correction"})
        assert r.status_code == code, r.text
        if code != 200:
            assert "inspection hold" in r.json()["detail"], "the hold guard, not the reason check, must refuse it"
        assert material(client, "H-1")["held_quantity"] == 9

    def test_inventory_edit_cannot_drop_quantity_below_held(self, client, world):
        po = approved_order(client)
        held(client, po)
        v = material(client, "H-1")["version"]
        r = client.patch("/api/v1/materials/H-1", json={"quantity": 9, "expected_version": v})
        assert r.status_code == 422 and "inspection hold" in r.json()["detail"]

    def test_status_editable_again_after_decision(self, client, world):
        po = approved_order(client)
        hid = hold_of(held(client, po))["id"]
        decide(client, hid, "release", quantity=10)
        v = material(client, "H-1")["version"]
        assert client.patch("/api/v1/materials/H-1", json={"status": "Low stock", "expected_version": v}).status_code == 200

    def test_held_batch_cannot_be_deleted_or_receive_more_goods(self, client, world):
        po = approved_order(client, lines=[order_line(), order_line(description="b")])
        held(client, po)
        assert client.delete("/api/v1/materials/H-1").status_code == 409
        o = order(client, po)
        r = receive(client, o, [rline(o, 1, destination_material_id="H-1", batch="LOT-H")], key="more")
        assert r.status_code == 422 and "under inspection" in r.json()["detail"]


class TestQueries:
    def test_list_filters_search_and_summary(self, client, world):
        po = approved_order(client, lines=[order_line(), order_line(description="b")])
        first = hold_of(held(client, po, 0, key="a", destination_material_id="H-A", batch="LA"))
        o = order(client, po)
        second = hold_of(held(client, o, 1, key="b", destination_material_id="H-B", batch="LB"))
        decide(client, first["id"], "release", quantity=10)

        def ids(**params):
            return [h["id"] for h in client.get(QI, params=params).json()["data"]["inspections"]]

        assert ids() == [second["id"], first["id"]]
        assert ids(status="Open") == [second["id"]]
        assert ids(status=["Released", "Rejected"]) == [first["id"]]
        assert ids(search=first["display_id"]) == [first["id"]]
        assert ids(search="h-b") == [second["id"]]
        assert client.get(f"{QI}/summary").json()["data"] == {"open": 1, "released_this_week": 1, "rejected_this_week": 0}

    def test_events_are_append_only_history(self, client, world, db):
        po = approved_order(client)
        hid = hold_of(held(client, po))["id"]
        decide(client, hid, "release", quantity=3)
        decide(client, hid, "reject", quantity=7, disposition="Scrap")
        db.expire_all()
        rows = db.query(InspectionEvent).filter_by(hold_id=hid).order_by(InspectionEvent.id).all()
        assert [(e.action, e.quantity, e.from_status, e.to_status, e.version, e.disposition) for e in rows] == [
            ("held", 10, None, "Open", 1, None),
            ("released", 3, "Open", "Open", 2, None),
            ("rejected", 7, "Open", "Partially released", 3, "Scrap"),
        ]
        m = db.get(Material, "H-1")
        assert (m.quantity, m.available) == (3, 3)
