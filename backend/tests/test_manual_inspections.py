"""Inspection holds opened by hand on stock already in a batch: hold, release, scrap, guards, audit."""

import pytest

from app.models.inspection import InspectionHold
from app.models.material import Material
from app.models.transaction import MaterialTransaction, TransactionType as T
from tests.test_goods_receipts import world  # noqa: F401
from tests.test_inspections import INSPECTOR, QI, decide, get, ledger, material, stock

T_INSPECTION, T_RELEASE, T_SCRAP = T.INSPECTION, T.RELEASE, T.SCRAP


def open_hold(client, mid="EXIST", quantity=3, reason="Suspected lamination", **over):
    return client.post(QI, json={"actor": INSPECTOR, "material_id": mid, "quantity": quantity, "reason": reason, **over})


def opened(client, **kw):
    r = open_hold(client, **kw)
    assert r.status_code == 201, r.text
    return r.json()["data"]


def kinds(db, mid="EXIST"):
    return ledger(db, mid)


class TestOpen:
    def test_hold_moves_available_stock_to_held(self, client, world, db):
        hold = opened(client)
        assert (hold["status"], hold["quantity"], hold["outstanding_quantity"], hold["goods_receipt_line"]) == ("Open", 3, 3, None)
        assert hold["created_by"] == INSPECTOR and hold["display_id"].startswith("QI-")
        assert [(e["action"], e["quantity"], e["to_status"], e["reason"]) for e in hold["events"]] == [
            ("held", 3, "Open", "Suspected lamination")]
        assert stock(client, "EXIST") == (5, 2, 0, 3, "Inspection")  # on hand unchanged; 3 blocked
        assert kinds(db) == [(T_INSPECTION, 3, "QI-")]
        listed = client.get(QI, params={"search": "EXIST"}).json()["data"]["inspections"]
        assert [(h["id"], h["goods_receipt_line"]) for h in listed] == [(hold["id"], None)]

    def test_ledger_reason_records_why(self, client, world, db):
        opened(client, reason="Mill certificate missing")
        db.expire_all()
        row = db.query(MaterialTransaction).one()
        assert (row.actor, row.reason, row.reference_id[:3]) == (INSPECTOR, "Held for inspection: Mill certificate missing", "QI-")

    def test_second_hold_on_the_same_batch_adds_up(self, client, world):
        opened(client, quantity=2)
        opened(client, quantity=3)
        assert stock(client, "EXIST") == (5, 0, 0, 5, "Inspection")
        assert open_hold(client, quantity=1).status_code == 422  # nothing left available

    @pytest.mark.parametrize("over, code", [
        ({"quantity": 6}, 422),            # more than on hand
        ({"quantity": 0}, 422),
        ({"reason": "  "}, 422),
        ({"actor": ""}, 422),
        ({"mid": "NOPE"}, 404),
    ])
    def test_invalid_requests_change_nothing(self, client, world, db, over, code):
        r = open_hold(client, **over)
        assert r.status_code == code, r.text
        assert stock(client, "EXIST") == (5, 5, 0, 0, "Healthy")
        assert db.query(InspectionHold).count() == 0

    def test_reserved_stock_cannot_be_held(self, client, world, db):
        m = db.get(Material, "EXIST")
        m.available, m.reserved = 2, 3
        db.commit()
        r = open_hold(client, quantity=3)
        assert r.status_code == 422 and "Only 2 sheets of EXIST are available" in r.json()["detail"]
        assert opened(client, quantity=2)["quantity"] == 2
        assert stock(client, "EXIST") == (5, 0, 3, 2, "Inspection")


class TestDecide:
    def test_release_returns_stock_and_clears_status(self, client, world, db):
        hid = opened(client)["id"]
        r = decide(client, hid, "release", quantity=3, note="UT passed")
        assert r.status_code == 200, r.text
        assert r.json()["data"]["status"] == "Released"
        assert stock(client, "EXIST") == (5, 5, 0, 0, "Healthy")
        assert sorted(kinds(db)) == sorted([(T_INSPECTION, 3, "QI-"), (T_RELEASE, 3, "QI-")])

    def test_scrap_removes_stock_without_a_purchase_order(self, client, world, db):
        hid = opened(client)["id"]
        r = decide(client, hid, "reject", quantity=3, disposition="Scrap", reason="Lamination confirmed")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert (d["status"], d["rejected_quantity"]) == ("Rejected", 3)
        assert [(e["action"], e["disposition"]) for e in d["events"]] == [("held", None), ("rejected", "Scrap")]
        assert stock(client, "EXIST") == (2, 2, 0, 0, "Healthy")
        assert sorted(kinds(db)) == sorted([(T_INSPECTION, 3, "QI-"), (T_SCRAP, 3, "QI-")])

    def test_return_to_supplier_is_refused_and_changes_nothing(self, client, world, db):
        hold = opened(client)
        r = decide(client, hold["id"], "reject", quantity=3, disposition="Return to supplier")
        assert r.status_code == 422 and "choose Scrap" in r.json()["detail"]
        after = get(client, hold["id"])
        assert (after["status"], after["version"], after["rejected_quantity"]) == ("Open", hold["version"], 0)
        assert stock(client, "EXIST") == (5, 2, 0, 3, "Inspection")

    def test_partial_release_then_scrap(self, client, world):
        hid = opened(client)["id"]
        assert decide(client, hid, "release", quantity=1).status_code == 200
        assert decide(client, hid, "reject", quantity=2, disposition="Scrap").json()["data"]["status"] == "Partially released"
        assert stock(client, "EXIST") == (3, 3, 0, 0, "Healthy")

    def test_stale_version_is_refused(self, client, world):
        hold = opened(client)
        assert decide(client, hold["id"], "release", quantity=1).status_code == 200
        r = decide(client, hold["id"], "reject", version=hold["version"], quantity=1, disposition="Scrap")
        assert r.status_code == 409

    def test_unknown_hold_is_not_found(self, client, world):
        assert decide(client, 999, "reject", version=1, quantity=1, disposition="Scrap").status_code == 404


class TestGuardsAndHistory:
    def test_held_stock_is_excluded_from_transfers_and_edits(self, client, world):
        opened(client)
        r = client.post("/api/v1/transfers", json={"actor": "t", "material_id": "EXIST", "quantity": 3, "to_yard_id": "Y2"})
        assert r.status_code == 422 and "Only 2" in r.json()["detail"]
        v = material(client, "EXIST")["version"]
        r = client.patch("/api/v1/materials/EXIST", json={"status": "Healthy", "expected_version": v})
        assert r.status_code == 409 and "inspection hold" in r.json()["detail"]
        r = client.patch("/api/v1/materials/EXIST", json={"available": 5, "expected_version": v, "actor": "QA", "stock_reason": "x"})
        assert r.status_code == 422 and "inspection hold" in r.json()["detail"]

    def test_audit_feed_shows_the_hold(self, client, world):
        hold = opened(client)
        events = client.get("/api/v1/audit-events", params={"search": hold["display_id"]}).json()["data"]["events"]
        assert {(e["source"], e["action"]) for e in events} >= {("inspection", "Held"), ("stock", "Inspection")}
