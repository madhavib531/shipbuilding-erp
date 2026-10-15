"""Transfer lifecycle, stock movement, ledger, audit history and guard-rail tests."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.facility import StorageLocation, Yard
from app.models.material import Material, MaterialCategory
from app.models.program import Ship, ShipSeries
from app.models.transaction import MaterialTransaction, TransactionType
from app.models.transfer import MaterialTransfer

ACTOR = "Maya Chen"


@pytest.fixture
def world(db):
    db.add_all([
        MaterialCategory(id="STEEL", name="Steel"),
        MaterialCategory(id="PIPE", name="Pipe"),
        Yard(id="Y1", name="Yard 1", location="North", capacity=1.0),
        Yard(id="Y2", name="Yard 2", location="South", capacity=1.0),
        ShipSeries(id="SER", name="Series"),
    ])
    db.commit()
    db.add_all([
        StorageLocation(id="L1", yard_id="Y1", zone="A", aisle="1", capacity=1000),
        StorageLocation(id="L1B", yard_id="Y1", zone="B", aisle="1", capacity=1000),
        StorageLocation(id="L2", yard_id="Y2", zone="C", aisle="1", capacity=1000),
        StorageLocation(id="L3", yard_id="Y2", zone="D", aisle="1", capacity=1000),
        Ship(id="S1", name="Ship 1", series_id="SER", yard_id="Y1", allocated_value=0.0),
    ])
    db.commit()
    # 100 on hand: 70 available, 20 reserved, 10 blocked.
    db.add(Material(id="M1", name="Plate", category_id="STEEL", batch="B1", unit="sheets",
                    quantity=100, available=70, reserved=20, yard_id="Y1", location_id="L1", ship_id="S1"))
    db.commit()


def create(client, key=None, **over):
    body = {"material_id": "M1", "quantity": 30, "to_yard_id": "Y2", "to_location_id": "L2", "actor": ACTOR}
    body.update(over)
    return client.post("/api/v1/transfers", json=body, headers={"Idempotency-Key": key} if key else {})


def act(client, tid, action, **body):
    return client.post(f"/api/v1/transfers/{tid}/{action}", json={"actor": ACTOR, **body})


def approved(client, **over):
    r = create(client, **over)
    assert r.status_code == 201, r.text
    tid = r.json()["data"]["id"]
    assert act(client, tid, "approve").status_code == 200
    return tid


def dispatched(client, **over):
    tid = approved(client, **over)
    r = act(client, tid, "dispatch")
    assert r.status_code == 200, r.text
    return tid


def stock(client, mid):
    r = client.get(f"/api/v1/materials/{mid}")
    if r.status_code == 404:
        return None
    d = r.json()["data"]
    return {k: d[k] for k in ("quantity", "available", "reserved", "yard_id", "location_id", "ship_id", "version")}


def ledger(db, tid):
    db.expire_all()
    rows = db.query(MaterialTransaction).filter_by(reference_id=f"TR-{tid:05d}").all()
    return sorted((r.transaction_type, r.material_id, r.quantity) for r in rows)


def transfer(client, tid):
    return client.get(f"/api/v1/transfers/{tid}").json()["data"]


class TestCreate:
    def test_request_records_snapshot_and_event_without_touching_stock(self, client, world):
        r = create(client)
        assert r.status_code == 201
        t = r.json()["data"]
        assert t["display_id"] == f"TR-{t['id']:05d}"
        assert t["status"] == "Requested"
        assert (t["from_yard"]["id"], t["from_location"]["id"], t["to_yard"]["id"], t["to_location"]["id"]) == ("Y1", "L1", "Y2", "L2")
        assert t["unit"] == "sheets" and t["requested_by"] == ACTOR
        assert [(e["action"], e["to_status"], e["actor"]) for e in t["events"]] == [("requested", "Requested", ACTOR)]
        assert stock(client, "M1")["available"] == 70

    @pytest.mark.parametrize("over, fragment", [
        ({"quantity": 71}, "available"),
        ({"quantity": 0}, ""),
        ({"material_id": "NOPE"}, "does not exist"),
        ({"to_yard_id": "NOPE"}, "does not exist"),
        ({"to_location_id": "L1B", "to_yard_id": "Y2"}, "does not belong"),
        ({"to_yard_id": "Y1", "to_location_id": "L1"}, "same yard and location"),
        ({"actor": "  "}, ""),
    ])
    def test_invalid_requests_rejected(self, client, world, over, fragment):
        r = create(client, **over)
        assert r.status_code == 422, r.text
        assert fragment in str(r.json()["detail"])

    def test_move_within_same_yard_to_other_location_allowed(self, client, world):
        assert create(client, to_yard_id="Y1", to_location_id="L1B").status_code == 201

    def test_idempotency_key_replay_returns_original(self, client, world, db):
        first = create(client, key="k-1")
        again = create(client, key="k-1")
        assert first.status_code == 201 and again.status_code == 200
        assert first.json()["data"]["id"] == again.json()["data"]["id"]
        assert db.query(MaterialTransfer).count() == 1

    def test_idempotency_key_with_different_payload_conflicts(self, client, world, db):
        create(client, key="k-1")
        r = create(client, key="k-1", quantity=5)
        assert r.status_code == 409
        assert db.query(MaterialTransfer).count() == 1


class TestLifecycle:
    def test_partial_transfer_into_new_batch(self, client, world, db):
        tid = approved(client)
        assert stock(client, "M1")["available"] == 70, "approval must not move stock"

        assert act(client, tid, "dispatch").status_code == 200
        src = stock(client, "M1")
        assert (src["quantity"], src["available"], src["reserved"]) == (70, 40, 20)
        assert ledger(db, tid) == [(TransactionType.TRANSFER_OUT, "M1", 30)]

        r = act(client, tid, "receive", destination_material_id="M1-Y2")
        assert r.status_code == 200, r.text
        t = r.json()["data"]
        assert (t["status"], t["received_quantity"], t["shortage_quantity"], t["destination_material_id"]) == ("Received", 30, 0, "M1-Y2")
        dest = stock(client, "M1-Y2")
        assert (dest["quantity"], dest["available"], dest["reserved"], dest["yard_id"], dest["location_id"], dest["ship_id"]) == (30, 30, 0, "Y2", "L2", None)
        new = client.get("/api/v1/materials/M1-Y2").json()["data"]
        assert (new["category_id"], new["batch"], new["unit"], new["name"]) == ("STEEL", "B1", "sheets", "Plate")
        assert ledger(db, tid) == sorted([(TransactionType.TRANSFER_OUT, "M1", 30), (TransactionType.TRANSFER_IN, "M1-Y2", 30)])
        assert [e["action"] for e in t["events"]] == ["requested", "approved", "dispatched", "received"]
        assert all(e["actor"] == ACTOR and e["created_at"] for e in t["events"])

    def test_stock_is_conserved_across_the_lifecycle(self, client, world):
        def total():
            on_hand = sum(m["quantity"] for m in client.get("/api/v1/materials").json()["data"]["materials"])
            in_transit = sum(t["quantity"] for t in client.get("/api/v1/transfers?status=Dispatched").json()["data"]["transfers"])
            return on_hand + in_transit

        assert total() == 100
        tid = dispatched(client)
        assert total() == 100
        act(client, tid, "receive", destination_material_id="M1-Y2")
        assert total() == 100

    def test_whole_batch_relocation_keeps_material_id(self, client, world, db):
        db.add(Material(id="W1", name="Valve", category_id="STEEL", batch="BW", unit="units",
                        quantity=50, available=50, reserved=0, yard_id="Y1", location_id="L1", ship_id="S1"))
        db.commit()
        tid = dispatched(client, material_id="W1", quantity=50)
        assert stock(client, "W1")["quantity"] == 0
        r = act(client, tid, "receive")
        assert r.status_code == 200, r.text
        w = stock(client, "W1")
        assert (w["quantity"], w["available"], w["yard_id"], w["location_id"]) == (50, 50, "Y2", "L2")
        assert w["ship_id"] is None, "ship belongs to the old yard, so the allocation is cleared"
        assert transfer(client, tid)["destination_material_id"] == "W1"

    def test_whole_batch_relocation_refused_when_reserved_or_blocked_stock_remains(self, client, world):
        tid = dispatched(client, quantity=70)  # all available, but 20 reserved + 10 blocked stay at the source
        r = act(client, tid, "receive")
        assert r.status_code == 422
        assert "destination_material_id is required" in r.json()["detail"]
        assert transfer(client, tid)["status"] == "Dispatched"

    def test_two_partials_emptying_a_batch_do_not_count_as_whole_batch(self, client, world, db):
        db.add(Material(id="W2", name="Valve", category_id="STEEL", batch="BW", unit="units",
                        quantity=50, available=50, reserved=0, yard_id="Y1", location_id="L1"))
        db.commit()
        a = dispatched(client, material_id="W2", quantity=30)
        dispatched(client, material_id="W2", quantity=20)
        assert stock(client, "W2")["quantity"] == 0
        assert act(client, a, "receive").status_code == 422

    def test_receive_into_existing_compatible_batch(self, client, world, db):
        db.add(Material(id="M1-Y2", name="Plate", category_id="STEEL", batch="B1", unit="sheets",
                        quantity=5, available=5, reserved=0, yard_id="Y2", location_id="L2"))
        db.commit()
        tid = dispatched(client)
        assert act(client, tid, "receive", destination_material_id="M1-Y2").status_code == 200
        dest = stock(client, "M1-Y2")
        assert (dest["quantity"], dest["available"]) == (35, 35)

    @pytest.mark.parametrize("attrs, fragment", [
        ({"batch": "OTHER"}, "batch"),
        ({"category_id": "PIPE"}, "category_id"),
        ({"unit": "kg"}, "unit"),
        ({"yard_id": "Y1", "location_id": "L1B"}, "yard"),
        ({"location_id": "L3"}, "location"),
    ])
    def test_receive_into_incompatible_batch_rolls_back(self, client, world, db, attrs, fragment):
        base = dict(id="X", name="Plate", category_id="STEEL", batch="B1", unit="sheets",
                    quantity=5, available=5, reserved=0, yard_id="Y2", location_id="L2")
        base.update(attrs)
        db.add(Material(**base))
        db.commit()
        tid = dispatched(client)
        r = act(client, tid, "receive", destination_material_id="X")
        assert r.status_code == 422 and fragment in r.json()["detail"], r.text
        assert transfer(client, tid)["status"] == "Dispatched"
        assert stock(client, "X")["quantity"] == 5
        assert ledger(db, tid) == [(TransactionType.TRANSFER_OUT, "M1", 30)]

    def test_partial_receipt_requires_reason_and_records_shortage(self, client, world, db):
        tid = dispatched(client)
        r = act(client, tid, "receive", destination_material_id="M1-Y2", received_quantity=25)
        assert r.status_code == 422 and "discrepancy_reason" in r.json()["detail"]
        assert stock(client, "M1-Y2") is None

        r = act(client, tid, "receive", destination_material_id="M1-Y2", received_quantity=25,
                discrepancy_reason="5 sheets damaged in transit")
        assert r.status_code == 200, r.text
        t = r.json()["data"]
        assert (t["received_quantity"], t["shortage_quantity"]) == (25, 5)
        assert t["events"][-1]["reason"] == "5 sheets damaged in transit"
        assert stock(client, "M1-Y2")["quantity"] == 25
        assert ledger(db, tid) == sorted([
            (TransactionType.TRANSFER_OUT, "M1", 30),
            (TransactionType.TRANSFER_IN, "M1-Y2", 25),
            (TransactionType.ADJUSTMENT, "M1", 5),
        ])

    def test_nothing_received_writes_off_everything(self, client, world, db):
        tid = dispatched(client)
        r = act(client, tid, "receive", received_quantity=0, discrepancy_reason="Lost")
        assert r.status_code == 200, r.text
        assert r.json()["data"]["destination_material_id"] is None
        assert ledger(db, tid) == sorted([(TransactionType.TRANSFER_OUT, "M1", 30), (TransactionType.ADJUSTMENT, "M1", 30)])

    def test_over_receipt_rejected(self, client, world):
        tid = dispatched(client)
        r = act(client, tid, "receive", destination_material_id="M1-Y2", received_quantity=31)
        assert r.status_code == 422
        assert transfer(client, tid)["status"] == "Dispatched"


class TestGuards:
    @pytest.mark.parametrize("setup, action", [
        ("requested", "dispatch"),
        ("requested", "receive"),
        ("approved", "approve"),
        ("approved", "reject"),
        ("approved", "receive"),
        ("dispatched", "approve"),
        ("dispatched", "cancel"),
        ("dispatched", "dispatch"),
        ("received", "receive"),
        ("received", "cancel"),
        ("cancelled", "approve"),
        ("rejected", "approve"),
    ])
    def test_invalid_transitions_conflict_and_change_nothing(self, client, world, db, setup, action):
        if setup == "requested":
            tid = create(client).json()["data"]["id"]
        elif setup == "approved":
            tid = approved(client)
        elif setup == "dispatched":
            tid = dispatched(client)
        elif setup == "received":
            tid = dispatched(client)
            act(client, tid, "receive", destination_material_id="M1-Y2")
        elif setup == "cancelled":
            tid = create(client).json()["data"]["id"]
            act(client, tid, "cancel", reason="no longer needed")
        else:
            tid = create(client).json()["data"]["id"]
            act(client, tid, "reject", reason="not justified")
        before = (transfer(client, tid), stock(client, "M1"), ledger(db, tid))
        body = {"reason": "x"} if action in ("reject", "cancel") else {}
        if action == "receive":
            body = {"destination_material_id": "M1-Y2"}
        r = act(client, tid, action, **body)
        assert r.status_code == 409, r.text
        assert (transfer(client, tid), stock(client, "M1"), ledger(db, tid)) == before

    def test_duplicate_dispatch_deducts_once(self, client, world, db):
        tid = dispatched(client)
        assert act(client, tid, "dispatch").status_code == 409
        assert stock(client, "M1")["available"] == 40
        assert ledger(db, tid) == [(TransactionType.TRANSFER_OUT, "M1", 30)]

    def test_cannot_oversell_with_two_approved_transfers(self, client, world, db):
        first = approved(client, quantity=40)
        second = approved(client, quantity=40)
        assert act(client, first, "dispatch").status_code == 200
        r = act(client, second, "dispatch")
        assert r.status_code == 409 and "available" in r.json()["detail"]
        assert stock(client, "M1")["available"] == 30
        assert transfer(client, second)["status"] == "Approved"
        assert ledger(db, second) == []

    def test_dispatch_refused_when_source_moved_since_request(self, client, world):
        tid = approved(client)
        v = stock(client, "M1")["version"]
        assert client.patch("/api/v1/materials/M1", json={"location_id": "L1B", "expected_version": v}).status_code == 200
        r = act(client, tid, "dispatch")
        assert r.status_code == 409 and "has moved" in r.json()["detail"]
        assert stock(client, "M1")["available"] == 70

    @pytest.mark.parametrize("state", ["requested", "approved"])
    def test_cancel_before_dispatch_leaves_stock(self, client, world, state):
        tid = create(client).json()["data"]["id"] if state == "requested" else approved(client)
        assert act(client, tid, "cancel").status_code == 422, "reason is required"
        r = act(client, tid, "cancel", reason="Plan changed")
        assert r.status_code == 200
        assert r.json()["data"]["events"][-1]["reason"] == "Plan changed"
        assert stock(client, "M1")["available"] == 70

    def test_reject_requires_reason(self, client, world):
        tid = create(client).json()["data"]["id"]
        assert act(client, tid, "reject").status_code == 422
        assert act(client, tid, "reject", reason="Not needed").json()["data"]["status"] == "Rejected"

    def test_unknown_transfer_404(self, client, world):
        assert client.get("/api/v1/transfers/999").status_code == 404
        assert act(client, 999, "approve").status_code == 404

    def test_material_with_transfers_cannot_be_deleted(self, client, world):
        create(client)
        r = client.delete("/api/v1/materials/M1")
        assert r.status_code == 409 and "transfer" in r.json()["detail"]


class TestStaleEditsAndConstraints:
    def test_stale_version_rejected_and_version_advances(self, client, world):
        v = stock(client, "M1")["version"]
        assert client.patch("/api/v1/materials/M1", json={"name": "Plate A", "expected_version": v}).status_code == 200
        assert stock(client, "M1")["version"] == v + 1
        r = client.patch("/api/v1/materials/M1", json={"name": "Plate B", "expected_version": v})
        assert r.status_code == 409 and "Reload" in r.json()["detail"]

    def test_dispatch_makes_an_open_inventory_edit_stale(self, client, world):
        v = stock(client, "M1")["version"]
        dispatched(client)
        r = client.patch("/api/v1/materials/M1", json={"available": 70, "expected_version": v})
        assert r.status_code == 409
        assert stock(client, "M1")["available"] == 40

    @pytest.mark.parametrize("values", [
        dict(quantity=-1, available=0, reserved=0),
        dict(quantity=10, available=-1, reserved=0),
        dict(quantity=10, available=0, reserved=-1),
        dict(quantity=10, available=8, reserved=3),
    ])
    def test_database_rejects_invalid_stock(self, db, world, values):
        db.add(Material(id="BAD", name="x", category_id="STEEL", batch="b", unit="u", yard_id="Y1", **values))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


class TestQueries:
    def test_status_filter_and_summary(self, client, world):
        create(client)
        approved(client, quantity=5)
        d = dispatched(client, quantity=5, expected_arrival=__import__("datetime").date.today().isoformat())
        done = dispatched(client, quantity=5)
        act(client, done, "receive", destination_material_id="M1-Y2")

        page = client.get("/api/v1/transfers?status=Requested&status=Approved").json()["data"]
        assert page["total"] == 2
        assert {t["status"] for t in page["transfers"]} == {"Requested", "Approved"}
        assert client.get("/api/v1/transfers?material_id=M1-Y2").json()["data"]["total"] == 1

        s = client.get("/api/v1/transfers/summary").json()["data"]
        assert s == {"awaiting_approval": 1, "ready_to_dispatch": 1, "in_transit": 1, "due_today": 1, "received_this_week": 1}
        assert transfer(client, d)["expected_arrival"] == __import__("datetime").date.today().isoformat()
